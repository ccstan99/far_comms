#!/usr/bin/env python

import asyncio
import base64
import json 
import logging
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from far_comms.utils.coda_client import CodaClient
from far_comms.models.requests import CodaIds
from far_comms.utils.slide_processor import process_slides, titles_equivalent, is_placeholder_text
from far_comms.utils.transcript_processor import process_transcript, _reconstruct_srt

logger = logging.getLogger(__name__)


def get_input(raw_data: dict) -> dict:
    """Parse raw Coda data for prepare_talk - needs speaker name and YouTube URL"""
    return {
        "speaker": raw_data.get("Speaker", ""),
        "yt_full_link": raw_data.get("YT full link", "")
    }


def clean_slide_formatting(slides_content: str) -> str:
    """Clean up excessive newlines in slides content.
    
    Rules:
    - Replace all \\n\\n with \\n 
    - Add back extra \\n before headers (\\n#)
    """
    if not slides_content or not slides_content.strip():
        return slides_content
    
    # Replace all double newlines with single newlines
    cleaned = slides_content.replace('\n\n', '\n')
    
    # Add back extra newline before headers
    cleaned = cleaned.replace('\n#', '\n\n#')
    
    return cleaned


def display_input(function_data: dict) -> dict:
    """Format function input for webhook display - no long fields to truncate"""
    return function_data


async def prepare_talk(function_data: dict, coda_ids: CodaIds) -> dict:
    """
    Simplified prepare_talk handler that calls two independent functions.
    Maintains current functionality and quality without CrewAI.
    
    Returns:
        dict: {"status": "success|skipped|failed", "message": "details", "speaker": "name"}
    """
    try:
        logger.info(f"Starting simplified prepare_talk for row {coda_ids.row_id}")
        
        # Get speaker name and YouTube URL from function_data
        speaker_name = function_data.get("speaker", "")
        yt_url = function_data.get("yt_full_link", "")
        
        if not speaker_name:
            logger.error("No speaker name found in function_data")
            return {"status": "failed", "message": "No speaker name found in function_data", "speaker": ""}
            
        logger.info(f"Processing speaker: {speaker_name}")
        if yt_url:
            logger.info(f"YouTube URL provided: {yt_url}")
        
        # Initialize Coda client for updates
        coda_client = CodaClient()
        
        # Check existing content to determine what needs processing
        try:
            row_data_str = coda_client.get_row(coda_ids.doc_id, coda_ids.table_id, coda_ids.row_id)
            row_data = json.loads(row_data_str)
            row_values = row_data.get("data", {})
            
            # Check what content already exists
            existing_slides = row_values.get("Slides", "")
            existing_transcript = row_values.get("Transcript", "")
            
            slides_exist = existing_slides and existing_slides.strip()
            transcript_exists = existing_transcript and existing_transcript.strip()
            
            # If both exist, skip entirely
            if slides_exist and transcript_exists:
                logger.info(f"Skipping {speaker_name} - both Slides and Transcript exist, content is complete")
                return {"status": "skipped", "message": "slides skipped, transcript skipped", "speaker": speaker_name}
            
            # Log what needs processing
            needs_processing = []
            if not slides_exist:
                needs_processing.append("slides")
            if not transcript_exists:
                needs_processing.append("transcript")
            
            logger.info(f"Processing needed for {speaker_name}: {', '.join(needs_processing)}")
                
        except Exception as e:
            logger.warning(f"Could not check existing content for {speaker_name}: {e}")
            # Continue anyway in case it was just a temporary error - assume both need processing
            row_values = {}
            slides_exist = False
            transcript_exists = False
        
        # Process slides and transcript synchronously (we're already in background thread)
        slides_result = {"success": True, "cleaned_slides": "", "speaker_validation": {}}  # Default empty result
        transcript_result = {"success": True, "transcript_formatted": "", "transcript_srt": ""}  # Default empty result
        
        if not slides_exist:
            logger.info("Processing slides...")
            slides_result = process_slides(
                speaker_name,
                affiliation=row_values.get("Affiliation", ""),
                coda_speaker=row_values.get("Speaker", ""), 
                coda_affiliation=row_values.get("Affiliation", ""), 
                coda_title=row_values.get("Title", ""),
                table_id=coda_ids.table_id
            )
            
            # Update Coda immediately after slides processing
            if slides_result.get("success"):
                logger.info("Updating Coda with slides results immediately...")
                raw_slides = slides_result.get("cleaned_slides", "")
                cleaned_slides_formatted = clean_slide_formatting(raw_slides)
                slides_updates = {"Slides": cleaned_slides_formatted}
                
                # Handle speaker validation immediately
                speaker_validation = slides_result.get("speaker_validation", {})
                slide_1_metadata = slides_result.get("slide_1_metadata", {})
                
                # Use string search result if available, otherwise use LLM validation
                if slide_1_metadata.get("validation_method") == "string_search":
                    logger.info("Using string search validation result (faster than LLM)")
                    speaker_validation = {
                        "slide_speaker": slide_1_metadata.get("slide_speaker", ""),
                        "slide_affiliation": slide_1_metadata.get("slide_affiliation", ""),
                        "slide_title": slide_1_metadata.get("slide_title", ""),
                        "validation_result": slide_1_metadata.get("validation_result", "exact_match"),
                        "validation_notes": f"Speaker name found via string search in markdown: '{slide_1_metadata.get('slide_speaker', '')}'"
                    }
                
                if speaker_validation:
                    validation_result = speaker_validation.get("validation_result", "")
                    slide_speaker = speaker_validation.get("slide_speaker", "")
                    slide_affiliation = speaker_validation.get("slide_affiliation", "") 
                    slide_title = speaker_validation.get("slide_title", "")
                    
                    # Debug validation comparison
                    logger.info(f"Validation result: {validation_result}")
                    logger.info(f"Slide data: speaker='{slide_speaker}', affiliation='{slide_affiliation}', title='{slide_title}'")
                    coda_affiliation_val = row_values.get("Affiliation", "")
                    coda_title_val = row_values.get("Title", "")
                    logger.info(f"Coda data: speaker='{speaker_name}', affiliation='{coda_affiliation_val}', title='{coda_title_val}'")
                    
                    # Title is already in proper case from Haiku analysis
                    # No additional processing needed
                    
                    # Only show mismatch banner for actual conflicting data, not missing data
                    if validation_result == "major_mismatch" and slide_speaker and slide_speaker.strip():
                        if "Slides" in slides_updates:
                            slides_updates["Slides"] = "[*** BEWARE: MISMATCH BETWEEN SPEAKER & SLIDES ***]\n" + slides_updates["Slides"]
                        logger.warning(f"Major speaker mismatch detected: slide='{slide_speaker}' vs coda='{speaker_name}'")
                    elif validation_result == "major_mismatch":
                        logger.info(f"Speaker info not found in slides (not a mismatch): slide='{slide_speaker}' vs coda='{speaker_name}'")
                    elif validation_result in ["exact_match", "minor_differences"]:
                        prefix = "" if validation_result == "exact_match" else "* "
                        # Only update if slide data is valid and different (never replace good data with placeholders)
                        if slide_speaker and slide_speaker != speaker_name and not is_placeholder_text(slide_speaker):
                            slides_updates["Speaker"] = f"{prefix}{slide_speaker}"
                        original_affiliation = row_values.get("Affiliation", "")
                        if slide_affiliation and slide_affiliation != original_affiliation and not is_placeholder_text(slide_affiliation):
                            slides_updates["Affiliation"] = f"{prefix}{slide_affiliation}"
                        original_title = row_values.get("Title", "")
                        # Only update title if there are meaningful differences beyond case and it's not placeholder text
                        if slide_title and not titles_equivalent(slide_title, original_title) and not is_placeholder_text(slide_title):
                            slides_updates["Title"] = f"{prefix}{slide_title}"
                
                # Update slides in Coda immediately
                updates = [{"row_id": coda_ids.row_id, "updates": slides_updates}]
                result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                logger.info(f"Immediate slides update: {result}")
            else:
                logger.error(f"Slides processing failed: {slides_result.get('error', 'Unknown error')}")
        else:
            logger.info("Skipping slides processing - Slides column already has content")
            
        if not transcript_exists:
            logger.info("Processing transcript...")
            # Use slide context for transcript processing (from existing or newly processed slides)
            if slides_exist:
                slide_context = existing_slides[:2000]  # Use existing slides for context
            else:
                slide_context = slides_result.get("cleaned_slides", "")[:2000]  # Use newly processed slides
            transcript_result = process_transcript(speaker_name, yt_url, slide_context)
            
            # Update Coda immediately after transcript processing
            if transcript_result.get("success"):
                logger.info("Updating Coda with transcript results immediately...")
                formatted_transcript = transcript_result.get("transcript_formatted", "")
                # Post-process: convert double newlines to single newlines
                formatted_transcript = formatted_transcript.replace("\n\n", "\n")
                
                transcript_updates = {"Transcript": formatted_transcript}
                
                # Reconstruct SRT with original timestamps
                original_srt = transcript_result.get("transcript_srt", "")
                if original_srt and formatted_transcript:
                    reconstructed_srt = _reconstruct_srt(original_srt, formatted_transcript)
                    if reconstructed_srt:
                        # Combine every 2 lines for better readability
                        from far_comms.utils.transcript_processor import combine_srt_lines
                        combined_srt = combine_srt_lines(reconstructed_srt)
                        transcript_updates["SRT"] = combined_srt
                        logger.info(f"Reconstructed and combined SRT lines")
                    else:
                        logger.warning("SRT reconstruction failed, using original SRT with line combining")
                        from far_comms.utils.transcript_processor import combine_srt_lines
                        combined_srt = combine_srt_lines(original_srt)
                        transcript_updates["SRT"] = combined_srt
                elif original_srt:
                    # Apply line combining even to original SRT
                    from far_comms.utils.transcript_processor import combine_srt_lines
                    combined_srt = combine_srt_lines(original_srt)
                    transcript_updates["SRT"] = combined_srt
                
                # Update transcript in Coda immediately
                updates = [{"row_id": coda_ids.row_id, "updates": transcript_updates}]
                result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                logger.info(f"Immediate transcript update: {result}")
            else:
                logger.error(f"Transcript processing failed: {transcript_result.get('error', 'Unknown error')}")
        else:
            logger.info("Skipping transcript processing - Transcript column already has content")
        
        # Check if we have enough content to proceed
        if not slides_result.get("success") and not transcript_result.get("success"):
            error_msg = f"Cannot process {speaker_name} - both slides and transcript processing failed"
            logger.error(error_msg)
            
            # Update Coda with error
            coda_updates = {
                "Webhook status": "Error",
                "Webhook progress": error_msg
            }
            updates = [{"row_id": coda_ids.row_id, "updates": coda_updates}]
            coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
            
            return {"status": "failed", "message": error_msg, "speaker": speaker_name}
        
        # Set final status since processing is complete
        status_parts = []
        
        if not slides_exist:
            slides_status = "processed" if slides_result.get("success") else "FAILED"
            status_parts.append(f"slides {slides_status}")
        else:
            status_parts.append("slides skipped")
            
        if not transcript_exists:
            transcript_status = "processed" if transcript_result.get("success") else "FAILED"
            status_parts.append(f"transcript {transcript_status}")
        else:
            status_parts.append("transcript skipped")
        
        status_msg = f"{speaker_name}: {', '.join(status_parts)}"
        
        # Update final webhook status
        final_updates = {
            "Webhook progress": status_msg,
            "Webhook status": "Done"
        }
        updates = [{"row_id": coda_ids.row_id, "updates": final_updates}]
        result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
        logger.info(f"Final status update: {result}")
        
        # Count successful processes
        successful_processes = sum([
            1 for result_obj in [slides_result, transcript_result] 
            if result_obj.get("success")
        ])
        
        if successful_processes > 0:
            return {"status": "success", "message": status_msg, "speaker": speaker_name}
        else:
            return {"status": "failed", "message": "No processing succeeded", "speaker": speaker_name}
            
    except Exception as e:
        logger.error(f"Error in prepare_talk: {e}", exc_info=True)
        
        # Try to update Coda with error status
        try:
            coda_client = CodaClient()
            error_updates = {
                "Webhook status": "Error",
                "Webhook progress": f"Prepare talk failed: {str(e)}"
            }
            updates = [{
                "row_id": coda_ids.row_id,
                "updates": error_updates
            }]
            coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
        except Exception as update_error:
            logger.error(f"Failed to update Coda with error status: {update_error}")
        
        return {"status": "failed", "message": f"Prepare talk error: {str(e)}", "speaker": function_data.get("speaker", "")}