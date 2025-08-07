#!/usr/bin/env python

import requests
import json
import os
from datetime import datetime
from typing import Dict, List, Any
from dotenv import load_dotenv
from pydantic import BaseModel
from far_comms.utils.project_paths import get_output_dir


class CodaIds(BaseModel):
    """Coda document, table, and row identifiers"""
    doc_id: str
    table_id: str
    row_id: str


class CodaTool:
    """
    Read and write data from Coda tables. Can fetch row data, column information, 
    and update cells. Useful for getting context about talks, speakers, events,
    and updating processing status.
    
    Available operations:
    - get_row: Get specific row data by rowId
    - get_table: Get all rows from a table 
    - get_columns: Get column information for a table
    - update_row: Update one or more rows (single row or batch across multiple rows)
    - search_rows: Search for rows matching criteria
    """

    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        self.name = "coda_tool"
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
        """Get specific row data with human-readable column names"""
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
            "data": {}
        }
        
        for col_id, value in row_data.get("values", {}).items():
            column_name = columns.get(col_id, col_id)
            readable_data["data"][column_name] = value
        
        return json.dumps(readable_data, indent=2, default=str)

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

    def update_row(self, doc_id: str, table_id: str, row_id: str, column_name: str, value: str) -> str:
        """Update a single cell in a single row"""
        # Get column mapping
        columns_data = json.loads(self.get_columns(doc_id, table_id))
        columns = columns_data["columns"]
        
        # Find column ID by name
        column_id = None
        for col_id, name in columns.items():
            if name == column_name:
                column_id = col_id
                break
        
        if not column_id:
            return f"Error: Column '{column_name}' not found in table"
        
        # Update the cell
        uri = f'https://coda.io/apis/v1/docs/{doc_id}/tables/{table_id}/rows/{row_id}'
        payload = {
            "row": {
                "cells": [{"column": column_id, "value": value}]
            }
        }
        
        response = requests.put(uri, headers=self.coda_headers, json=payload)
        
        if response.ok:
            return f"Successfully updated '{column_name}' to '{value}'"
        else:
            return f"Error updating cell: {response.status_code} - {response.text}"

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
            
            # Update each column by calling the single update method
            for column_name, value in row_updates.items():
                try:
                    result = self.update_row(doc_id, table_id, row_id, column_name, value)
                    if "Successfully" in result:
                        successful_updates += 1
                    results.append(f"Row {row_id}, {column_name}: {result}")
                except Exception as e:
                    results.append(f"✗ Error updating row {row_id}, {column_name}: {str(e)}")
        
        return json.dumps({
            "total_updates_attempted": sum(len(item.get("updates", {})) for item in updates),
            "successful_updates": successful_updates,
            "results": results
        }, indent=2)


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

