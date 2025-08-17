#!/usr/bin/env python

import requests
import json
import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
from far_comms.utils.project_paths import get_output_dir


class CodaIds:
    """Coda document, table, and row identifiers"""
    def __init__(self, doc_id: str, table_id: str, row_id: str):
        self.doc_id = doc_id
        self.table_id = table_id
        self.row_id = row_id
    
    @classmethod
    def from_this_row(cls, doc_id: str, this_row: str) -> 'CodaIds':
        """Create CodaIds by splitting this_row into table_id/row_id"""
        table_id, row_id = this_row.split('/')
        return cls(doc_id=doc_id, table_id=table_id, row_id=row_id)
    
    def model_dump(self):
        """For compatibility with existing code"""
        return {
            "doc_id": self.doc_id,
            "table_id": self.table_id,
            "row_id": self.row_id
        }


class CodaClient:
    """
    Client for reading and writing data from Coda tables. Can fetch row data, column information, 
    and update cells. Useful for getting context about talks, speakers, events,
    and updating processing status.
    
    Available operations:
    - get_row: Get specific row data by rowId
    - get_table: Get all rows from a table 
    - get_columns: Get column information for a table
    - update_row: Update one or more rows (single row or batch across multiple rows)
    - search_rows: Search for rows matching criteria
    - get_x_handle: Look up speaker's X/Twitter handle
    """

    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Set instance attributes
        self.coda_headers = {'Authorization': f'Bearer {os.getenv("CODA_API_TOKEN")}'}
        self.output_dir = get_output_dir()

    def get_table(self, doc_id: str, table_id: str, filters: dict = None) -> str:
        """Get all rows from a table with optional filtering"""
        # Get column mapping
        columns_data = json.loads(self.get_columns(doc_id, table_id))
        columns = columns_data["columns"]
        
        # Get table rows
        uri = f'https://coda.io/apis/v1/docs/{doc_id}/tables/{table_id}/rows'
        params = {}
        if filters:
            # Add any query parameters for filtering
            params.update(filters)
            
        response = requests.get(uri, headers=self.coda_headers, params=params)
        response.raise_for_status()
        rows_data = response.json()
        
        # Convert to human-readable format
        readable_rows = []
        for row in rows_data.get("items", []):
            row_readable = {
                "row_id": row["id"],
                "data": {}
            }
            for col_id, value in row.get("values", {}).items():
                column_name = columns.get(col_id, col_id)
                row_readable["data"][column_name] = value
            readable_rows.append(row_readable)
        
        return json.dumps({
            "table_name": columns_data["table_name"],
            "total_rows": len(readable_rows),
            "rows": readable_rows
        }, indent=2, default=str)

    def get_columns(self, doc_id: str, table_id: str, force_refresh: bool = False) -> str:
        """Get and cache column information for a table"""
        cache_file = self.output_dir / f"{table_id}.json"
        
        # Check cache first (unless forcing refresh)
        if cache_file.exists() and not force_refresh:
            cached = json.loads(cache_file.read_text())
            
            # Only refresh if cache is old (> 24 hours)
            cached_at = cached.get("cached_at")
            if cached_at:
                try:
                    cached_time = datetime.fromisoformat(cached_at.replace('Z', '+00:00'))
                    now = datetime.now(cached_time.tzinfo) if cached_time.tzinfo else datetime.now()
                    cache_age_hours = (now - cached_time).total_seconds() / 3600
                except Exception:
                    cache_age_hours = float('inf')  # Treat as very old if can't parse
            else:
                cache_age_hours = float('inf')  # No timestamp = very old
                
            if cache_age_hours > 24:  # Refresh cache if older than 24 hours
                return self._refresh_column_cache(doc_id, table_id, cache_file)
            
            return json.dumps({
                "table_name": cached.get("table_name"),
                "columns": cached.get("columns"),
                "cached_at": cached.get("cached_at")
            }, indent=2)
        
        # Fetch fresh data
        return self._refresh_column_cache(doc_id, table_id, cache_file)

    def get_row(self, doc_id: str, table_id: str, row_id: str) -> str:
        """Get specific row data with human-readable column names, always fetch fresh and cache"""
        cache_file = self.output_dir / f"{table_id}_{row_id}.json"
        
        # Always fetch fresh data and cache it
        return self._refresh_row_cache(doc_id, table_id, row_id, cache_file)

    def search_rows(self, doc_id: str, table_id: str, filters: dict) -> str:
        """Search for rows matching specific criteria"""
        # Get all rows first
        all_rows_data = json.loads(self.get_table(doc_id, table_id))
        
        # Apply filters
        matching_rows = []
        for row in all_rows_data["rows"]:
            matches = True
            for filter_key, filter_value in filters.items():
                if filter_key in row["data"]:
                    row_value = str(row["data"][filter_key]).lower()
                    if str(filter_value).lower() not in row_value:
                        matches = False
                        break
                else:
                    matches = False
                    break
            
            if matches:
                matching_rows.append(row)
        
        return json.dumps({
            "table_name": all_rows_data["table_name"],
            "total_matches": len(matching_rows),
            "matching_rows": matching_rows
        }, indent=2, default=str)

    def update_row(self, doc_id: str, table_id: str, row_id: str, column_updates: dict) -> str:
        """Update multiple columns in a single row with one API call"""
        # Get column mapping
        columns_data = json.loads(self.get_columns(doc_id, table_id))
        columns = columns_data["columns"]
        
        # Build cells array for all columns
        cells = []
        not_found_columns = []
        
        for column_name, value in column_updates.items():
            # Find column ID by name
            column_id = None
            for col_id, name in columns.items():
                if name == column_name:
                    column_id = col_id
                    break
            
            if column_id:
                cells.append({"column": column_id, "value": value})
            else:
                not_found_columns.append(column_name)
        
        if not cells:
            return f"Error: No valid columns found. Missing: {not_found_columns}"
        
        # Update all cells in one API call
        uri = f'https://coda.io/apis/v1/docs/{doc_id}/tables/{table_id}/rows/{row_id}'
        payload = {
            "row": {
                "cells": cells
            }
        }
        
        # Retry logic for 429 rate limit errors
        max_retries = 3
        for attempt in range(max_retries):
            response = requests.put(uri, headers=self.coda_headers, json=payload)
            
            if response.ok:
                updated_columns = [col for col in column_updates.keys() if col not in not_found_columns]
                result = f"Successfully updated {len(updated_columns)} columns: {updated_columns}"
                if not_found_columns:
                    result += f". Not found: {not_found_columns}"
                return result
            elif response.status_code == 429:
                # Rate limit hit - wait with exponential backoff
                wait_time = (2 ** attempt) + 1  # 2, 5, 9 seconds
                if attempt < max_retries - 1:  # Don't wait on the last attempt
                    print(f"Rate limited, retrying in {wait_time} seconds (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    return f"Error updating cells: {response.status_code} - {response.text} (failed after {max_retries} retries)"
            else:
                # Non-429 error, don't retry
                return f"Error updating cells: {response.status_code} - {response.text}"
        
        return f"Unexpected error - should not reach this point"

    def update_rows(self, doc_id: str, table_id: str, updates: List[Dict[str, Any]]) -> str:
        """
        Batch update by making multiple calls to update_row
        
        updates format: [
            {
                "row_id": "i-abc123",
                "updates": {"Column Name": "new_value", "Another Column": "value2"}
            }
        ]
        """
        if not updates:
            return "No updates provided"
            
        results = []
        successful_updates = 0
        
        for update_item in updates:
            row_id = update_item.get("row_id")
            row_updates = update_item.get("updates", {})
            
            if not row_id or not row_updates:
                results.append(f"Skipped invalid update item: {update_item}")
                continue
            
            # Update all columns for this row in a single API call
            try:
                result = self.update_row(doc_id, table_id, row_id, row_updates)
                if "Successfully" in result:
                    # Count successful updates (rough estimate based on result string)
                    successful_updates += len(row_updates)
                results.append(f"Row {row_id}: {result}")
            except Exception as e:
                results.append(f"✗ Error updating row {row_id}: {str(e)}")
        
        return json.dumps({
            "total_updates_attempted": sum(len(item.get("updates", {})) for item in updates),
            "successful_updates": successful_updates,
            "results": results
        }, indent=2)


    def get_x_handle(self, speaker_name: str, contacts_doc_id: str = "-igBsvSR-f", contacts_table_id: str = "grid-rDp4tK3BXf") -> str:
        """
        Find speaker's X handle using hybrid approach:
        1. Try exact query first (fast)
        2. Fall back to cached fuzzy matching if no exact match
        3. Safe fallback to speaker name
        """
        if not speaker_name or not speaker_name.strip():
            return ""
        
        speaker_name = speaker_name.strip()
        
        # Step 1: Try exact query match (fast)
        try:
            params = {"query": f'"name":"{speaker_name}"', "limit": 1}
            uri = f'https://coda.io/apis/v1/docs/{contacts_doc_id}/tables/{contacts_table_id}/rows'
            
            response = requests.get(uri, headers=self.coda_headers, params=params)
            if response.ok:
                data = response.json()
                if data.get("items"):
                    x_handle = data["items"][0]["values"].get("c-eZzZN-hJYk", "")
                    if x_handle and x_handle.strip():
                        return x_handle.strip()  # Already includes @
        except Exception as e:
            print(f"Query lookup failed: {e}")
        
        # Step 2: Fall back to cached fuzzy matching
        try:
            contacts_cache = self._get_contacts_cache(contacts_doc_id, contacts_table_id)
            return self._fuzzy_match_speaker(speaker_name, contacts_cache)
        except Exception as e:
            print(f"Cache lookup failed: {e}")
        
        # Step 3: Safe fallback
        return speaker_name

    def get_linkedin_profile(self, speaker_name: str, contacts_doc_id: str = "-igBsvSR-f", contacts_table_id: str = "grid-rDp4tK3BXf") -> str:
        """
        Find speaker's LinkedIn profile using the same approach as X handle lookup
        Returns empty string if not found
        """
        if not speaker_name or not speaker_name.strip():
            return ""
        
        speaker_name = speaker_name.strip()
        
        # Try cached fuzzy matching 
        try:
            contacts_cache = self._get_contacts_cache(contacts_doc_id, contacts_table_id)
            return self._fuzzy_match_speaker_field(speaker_name, contacts_cache, "linkedin_profile")
        except Exception as e:
            print(f"LinkedIn lookup failed: {e}")
        
        return ""

    def get_bsky_handle(self, speaker_name: str, contacts_doc_id: str = "-igBsvSR-f", contacts_table_id: str = "grid-rDp4tK3BXf") -> str:
        """
        Find speaker's Bluesky handle using the same approach as X handle lookup
        Returns empty string if not found
        """
        if not speaker_name or not speaker_name.strip():
            return ""
        
        speaker_name = speaker_name.strip()
        
        # Try cached fuzzy matching
        try:
            contacts_cache = self._get_contacts_cache(contacts_doc_id, contacts_table_id)
            return self._fuzzy_match_speaker_field(speaker_name, contacts_cache, "bsky_handle")
        except Exception as e:
            print(f"Bluesky lookup failed: {e}")
        
        return ""

    def _fuzzy_match_speaker_field(self, speaker_name: str, contacts_cache: list, field_name: str) -> str:
        """
        Enhanced version of _fuzzy_match_speaker that can return any field
        """
        # Step 1: Try exact match
        for contact in contacts_cache:
            if contact.get("name", "").strip().lower() == speaker_name.lower():
                field_value = contact.get(field_name, "")
                if field_value and field_value.strip():
                    return field_value.strip()
        
        # Step 2: Try partial match (existing logic but for any field)
        for contact in contacts_cache:
            contact_name = contact.get("name", "").strip().lower()
            if contact_name and speaker_name.lower() in contact_name:
                field_value = contact.get(field_name, "")
                if field_value and field_value.strip():
                    return field_value.strip()
        
        # Step 3: Try fuzzy matching (same as x_handle logic)
        from difflib import SequenceMatcher
        best_match = None
        best_ratio = 0.8  # Minimum threshold
        
        for contact in contacts_cache:
            contact_name = contact.get("name", "").strip()
            if contact_name:
                ratio = SequenceMatcher(None, speaker_name.lower(), contact_name.lower()).ratio()
                if ratio > best_ratio:
                    field_value = contact.get(field_name, "")
                    if field_value and field_value.strip():
                        best_match = field_value.strip()
                        best_ratio = ratio
        
        return best_match or ""

    def _get_contacts_cache(self, doc_id: str, table_id: str) -> list:
        """Get contacts cache, refresh if older than 24 hours"""
        cache_file = self.output_dir / f"contacts_cache_{doc_id}_{table_id}.json"
        
        # Check if cache exists and is fresh (< 24 hours)
        if cache_file.exists():
            try:
                cached_data = json.loads(cache_file.read_text())
                cached_at = datetime.fromisoformat(cached_data.get("cached_at", ""))
                now = datetime.now()
                cache_age_hours = (now - cached_at).total_seconds() / 3600
                
                if cache_age_hours < 24:
                    return cached_data.get("contacts", [])
            except Exception:
                pass  # Invalid cache, will refresh
        
        # Refresh cache
        return self._refresh_contacts_cache(doc_id, table_id, cache_file)

    def _refresh_contacts_cache(self, doc_id: str, table_id: str, cache_file) -> list:
        """Fetch all contacts and cache them"""
        # Get column mapping using the same caching system as other tables
        try:
            columns_data = json.loads(self.get_columns(doc_id, table_id))
            columns = columns_data.get("columns", {})
            
            # Find column IDs for known fields
            name_col_id = "c-zL3WLW9EK1"  # Known Name column ID
            x_handle_col_id = "c-eZzZN-hJYk"  # Known X handle column ID
            linkedin_col_id = None
            bsky_col_id = None
            
            # Search for LinkedIn and Bluesky columns by name
            for col_id, col_name in columns.items():
                col_name_lower = col_name.lower().strip()
                if col_name_lower == "linkedin":
                    linkedin_col_id = col_id
                elif col_name_lower in ["bluesky", "bsky", "bluesky handle", "bsky handle"]:
                    bsky_col_id = col_id
                    
            logger.info(f"Contacts table columns: LinkedIn={linkedin_col_id}, Bluesky={bsky_col_id}")
            
        except Exception as e:
            logger.warning(f"Could not fetch columns for contacts lookup: {e}")
            name_col_id = "c-zL3WLW9EK1"
            x_handle_col_id = "c-eZzZN-hJYk" 
            linkedin_col_id = None
            bsky_col_id = None
        
        uri = f'https://coda.io/apis/v1/docs/{doc_id}/tables/{table_id}/rows'
        params = {"limit": 500}  # Adjust as needed
        
        response = requests.get(uri, headers=self.coda_headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        contacts = []
        
        for item in data.get("items", []):
            values = item.get("values", {})
            contact = {
                "name": values.get(name_col_id, ""),
                "x_handle": values.get(x_handle_col_id, ""),
                "linkedin_profile": values.get(linkedin_col_id, "") if linkedin_col_id else "",
                "bsky_handle": values.get(bsky_col_id, "") if bsky_col_id else ""
            }
            contacts.append(contact)
        
        # Cache the results
        cache_data = {
            "cached_at": datetime.now().isoformat(),
            "contacts": contacts
        }
        cache_file.write_text(json.dumps(cache_data, indent=2))
        
        return contacts

    def _fuzzy_match_speaker(self, speaker_name: str, contacts: list) -> str:
        """Fuzzy match speaker name against contacts cache"""
        speaker_lower = speaker_name.lower()
        speaker_parts = speaker_lower.split()
        
        # Try exact match (case insensitive)
        for contact in contacts:
            contact_name = contact.get("name", "").lower()
            if contact_name == speaker_lower:
                x_handle = contact.get("x_handle", "")
                if x_handle and x_handle.strip():
                    return x_handle.strip()
        
        # Try partial matching - all speaker parts in contact name
        for contact in contacts:
            contact_name = contact.get("name", "").lower()
            if all(part in contact_name for part in speaker_parts):
                x_handle = contact.get("x_handle", "")
                if x_handle and x_handle.strip():
                    return x_handle.strip()
        
        # Try reverse - contact name parts in speaker name (for nicknames)
        for contact in contacts:
            contact_name = contact.get("name", "").lower()
            contact_parts = contact_name.split()
            if len(contact_parts) >= 2:  # At least first + last name
                if all(part in speaker_lower for part in contact_parts[:2]):
                    x_handle = contact.get("x_handle", "")
                    if x_handle and x_handle.strip():
                        return x_handle.strip()
        
        # Safe fallback
        return speaker_name

    def _refresh_row_cache(self, doc_id: str, table_id: str, row_id: str, cache_file) -> str:
        """Refresh row cache with fresh data from API"""
        # Get column mapping
        columns_data = json.loads(self.get_columns(doc_id, table_id))
        columns = columns_data["columns"]
        
        # Get row data
        uri = f'https://coda.io/apis/v1/docs/{doc_id}/tables/{table_id}/rows/{row_id}'
        response = requests.get(uri, headers=self.coda_headers)
        response.raise_for_status()
        row_data = response.json()
        
        # Convert to human-readable format
        readable_data = {
            "row_id": row_id,
            "table_name": columns_data["table_name"],
            "data": {},
            "cached_at": datetime.now().isoformat()
        }
        
        for col_id, value in row_data.get("values", {}).items():
            column_name = columns.get(col_id, col_id)
            readable_data["data"][column_name] = value
        
        # Cache the data
        cache_file.write_text(json.dumps(readable_data, indent=2, default=str))
        
        return json.dumps(readable_data, indent=2, default=str)

    def _refresh_column_cache(self, doc_id: str, table_id: str, cache_file) -> str:
        """Refresh column cache with fresh data from API"""
        # Fetch table info and columns
        table_uri = f'https://coda.io/apis/v1/docs/{doc_id}/tables/{table_id}'
        table_response = requests.get(table_uri, headers=self.coda_headers)
        table_response.raise_for_status()
        table_name = table_response.json().get('name', table_id)
        
        columns_uri = f'https://coda.io/apis/v1/docs/{doc_id}/tables/{table_id}/columns'
        columns_response = requests.get(columns_uri, headers=self.coda_headers)
        columns_response.raise_for_status()
        
        columns_data = columns_response.json()
        
        # Create mapping: column_id -> human_name
        column_mapping = {}
        for column in columns_data.get('items', []):
            column_mapping[column['id']] = column['name']
        
        # Cache with table metadata
        cache_data = {
            'table_name': table_name,
            'table_id': table_id,
            'columns': column_mapping,
            'cached_at': datetime.now().isoformat()
        }
        cache_file.write_text(json.dumps(cache_data, indent=2))
        
        return json.dumps({
            "table_name": table_name,
            "columns": column_mapping,
            "cache_refreshed": True
        }, indent=2)