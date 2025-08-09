#!/usr/bin/env python

import json
import logging
import glob
import os
from far_comms.utils.slide_extractor import extract_slide_content
from far_comms.utils.slide_cleaner import clean_full_slide_content
from far_comms.utils.coda_client import CodaClient
from far_comms.models.requests import CodaIds

logger = logging.getLogger(__name__)


def get_prepare_talk_input(raw_data: dict) -> dict:
    """Parse raw Coda data for prepare_talk - just needs speaker name"""
    return {
        "speaker": raw_data.get("Speaker", "")
    }


def display_prepare_talk_input(function_data: dict) -> dict:
    """Format function input for webhook display - no long fields to truncate"""
    return function_data


def find_matching_slide(speaker_name: str, slide_files: list) -> str | None:
    """Find slide file that matches speaker name using progressive matching strategies"""
    import re
    
    def clean_name(name: str) -> str:
        """Remove all non-alphanumeric characters and convert to lowercase"""
        return re.sub(r'[^a-zA-Z0-9]', '', name.lower())
    
    def score_match(speaker_parts: list, filename: str) -> tuple[int, str, str]:
        """Score how well speaker name matches filename. Returns (score, match_type, details)"""
        clean_filename = clean_name(filename)
        first_name = clean_name(speaker_parts[0]) if speaker_parts else ""
        last_name = clean_name(speaker_parts[-1]) if len(speaker_parts) > 1 else ""
        
        # Strategy 1: Full name exact match (highest score)
        full_name = "".join(clean_name(part) for part in speaker_parts)
        if full_name in clean_filename:
            return (100, "full_exact", f"full:{full_name}")
        
        # Strategy 2: First + Last exact match
        if first_name and last_name and first_name in clean_filename and last_name in clean_filename:
            return (90, "first_last_exact", f"first:{first_name},last:{last_name}")
        
        # Strategy 3: Single name exact match (first or last)
        exact_matches = []
        if first_name and first_name in clean_filename:
            exact_matches.append(f"first:{first_name}")
        if last_name and last_name in clean_filename:
            exact_matches.append(f"last:{last_name}")
        if exact_matches:
            return (80, "single_exact", ",".join(exact_matches))
        
        # Strategy 4: Long partial matches (6+ chars)
        partial_matches = []
        if len(first_name) >= 6 and first_name[:6] in clean_filename:
            partial_matches.append(f"first:{first_name[:6]}+")
        if len(last_name) >= 6 and last_name[:6] in clean_filename:
            partial_matches.append(f"last:{last_name[:6]}+")
        if partial_matches:
            return (60, "long_partial", ",".join(partial_matches))
        
        # Strategy 5: Medium partial matches (4-5 chars) - only if name is longer
        medium_matches = []
        if len(first_name) >= 5 and first_name[:4] in clean_filename:
            medium_matches.append(f"first:{first_name[:4]}+")
        if len(last_name) >= 5 and last_name[:4] in clean_filename:
            medium_matches.append(f"last:{last_name[:4]}+")
        if medium_matches:
            return (40, "medium_partial", ",".join(medium_matches))
        
        return (0, "no_match", "")
    
    speaker_parts = speaker_name.strip().split()
    if not speaker_parts:
        return None
    
    # Score all files and find best match
    best_score = 0
    best_match = None
    best_details = ""
    
    for file_path in slide_files:
        filename = os.path.basename(file_path)
        score, match_type, details = score_match(speaker_parts, filename)
        
        if score > best_score:
            best_score = score
            best_match = file_path
            best_details = f"{match_type}({details})"
    
    if best_match and best_score >= 40:  # Require at least medium partial match
        logger.info(f"Matched '{speaker_name}' to '{os.path.basename(best_match)}' via: {best_details} (score: {best_score})")
        return best_match
    
    logger.warning(f"No good match found for '{speaker_name}' (best score: {best_score})")
    return None


async def prepare_talk(function_data: dict, coda_ids: CodaIds) -> dict:
    """Prepare a single talk by extracting and updating slide content
    
    Returns:
        dict: {"status": "success|skipped|failed", "message": "details", "speaker": "name"}
    """
    try:
        logger.info(f"Starting prepare_talk for row {coda_ids.row_id}")
        
        # Get speaker name from function_data (already parsed)
        speaker_name = function_data.get("speaker", "")
        if not speaker_name:
            logger.error("No speaker name found in function_data")
            return {"status": "failed", "message": "No speaker name found in function_data", "speaker": ""}
            
        logger.info(f"Processing speaker: {speaker_name}")
        
        # Initialize Coda client for updates
        coda_client = CodaClient()
        
        # Check if Slides column already has content - skip if it does
        try:
            row_data_str = coda_client.get_row(coda_ids.doc_id, coda_ids.table_id, coda_ids.row_id)
            row_data = json.loads(row_data_str)
            existing_slides = row_data.get("data", {}).get("Slides", "")
            
            if existing_slides and existing_slides.strip():
                logger.info(f"Skipping {speaker_name} - Slides column already has content")
                return {"status": "skipped", "message": "Slides column already populated", "speaker": speaker_name}
        except Exception as e:
            logger.warning(f"Could not check existing slides for {speaker_name}: {e}")
            # Continue anyway in case it was just a temporary error
        
        # Get all PDF files in data/slides/
        slide_files = glob.glob("data/slides/*.pdf")
        matched_file = find_matching_slide(speaker_name, slide_files)
        
        if matched_file:
            logger.info(f"Found matching file: {matched_file}")
            
            # Extract slide content
            slide_result = extract_slide_content(matched_file)
            
            if slide_result.get("success"):
                # Clean the extracted content using LLM
                cleaned_result = clean_full_slide_content(slide_result)
                slide_content = cleaned_result.get("content", "")
                logger.info(f"Extracted and cleaned {len(slide_content)} characters from slides")
                
                # Update Coda row with slide content
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": {
                        "Slides": slide_content
                    }
                }]
                
                update_result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                logger.info(f"Updated Coda for {speaker_name}: {update_result}")
                
                # Check if update was successful
                if "successful_updates" in update_result:
                    update_data = json.loads(update_result)
                    if update_data.get("successful_updates", 0) > 0:
                        return {"status": "success", "message": f"Extracted slides from {matched_file} and updated Coda", "speaker": speaker_name}
                    else:
                        return {"status": "failed", "message": f"Slide extraction succeeded but Coda update failed: {update_result}", "speaker": speaker_name}
                else:
                    # Old format, assume success if no error
                    return {"status": "success", "message": f"Extracted slides from {matched_file} and updated Coda", "speaker": speaker_name}
            else:
                error_msg = slide_result.get('error', 'Unknown extraction error')
                logger.error(f"Failed to extract slides for {speaker_name}: {error_msg}")
                return {"status": "failed", "message": f"Slide extraction failed: {error_msg}", "speaker": speaker_name}
        else:
            logger.warning(f"No matching slide file found for speaker: {speaker_name}")
            return {"status": "failed", "message": "No matching slide file found", "speaker": speaker_name}
            
    except Exception as e:
        logger.error(f"Error in prepare_talk: {e}", exc_info=True)
        return {"status": "failed", "message": f"Unexpected error: {str(e)}", "speaker": function_data.get("speaker", "")}