#!/usr/bin/env python

import json
import logging
from far_comms.crews.prepare_talk_crew import PrepareTalkCrew
from far_comms.utils.coda_client import CodaClient
from far_comms.models.requests import CodaIds

logger = logging.getLogger(__name__)


def get_prepare_talk_input(raw_data: dict) -> dict:
    """Parse raw Coda data for prepare_talk crew - needs speaker name and YouTube URL"""
    return {
        "speaker": raw_data.get("Speaker", ""),
        "yt_url": raw_data.get("YT url", "")
    }


def display_prepare_talk_input(function_data: dict) -> dict:
    """Format function input for webhook display - no long fields to truncate"""
    return function_data


async def prepare_talk_crew(function_data: dict, coda_ids: CodaIds) -> dict:
    """Prepare a talk using PrepareTalkCrew multi-agent system
    
    Returns:
        dict: {"status": "success|skipped|failed", "message": "details", "speaker": "name"}
    """
    try:
        logger.info(f"Starting PrepareTalkCrew for row {coda_ids.row_id}")
        
        # Get speaker name and YouTube URL from function_data
        speaker_name = function_data.get("speaker", "")
        yt_url = function_data.get("yt_url", "")
        
        if not speaker_name:
            logger.error("No speaker name found in function_data")
            return {"status": "failed", "message": "No speaker name found in function_data", "speaker": ""}
            
        logger.info(f"Processing speaker: {speaker_name}")
        if yt_url:
            logger.info(f"YouTube URL provided: {yt_url}")
        
        # Initialize Coda client for updates
        coda_client = CodaClient()
        
        # Check if Slides and SRT columns already have content - skip if both do
        try:
            row_data_str = coda_client.get_row(coda_ids.doc_id, coda_ids.table_id, coda_ids.row_id)
            row_data = json.loads(row_data_str)
            row_values = row_data.get("data", {})
            existing_slides = row_values.get("Slides", "")
            existing_srt = row_values.get("SRT", "")
            
            # Check what needs to be processed
            slides_exist = existing_slides and existing_slides.strip()
            srt_exists = existing_srt and existing_srt.strip()
            
            if slides_exist and srt_exists:
                logger.info(f"Skipping {speaker_name} - both Slides and SRT columns already populated")
                return {"status": "skipped", "message": "Both Slides and SRT already populated", "speaker": speaker_name}
                
        except Exception as e:
            logger.warning(f"Could not check existing content for {speaker_name}: {e}")
            # Continue anyway in case it was just a temporary error
        
        # Preprocess content before running crew
        from far_comms.utils.content_preprocessor import (
            find_matching_pdf, extract_pdf_content, 
            find_matching_video, extract_youtube_transcript, extract_local_video_transcript
        )
        
        # Preprocess slides
        logger.info(f"Preprocessing slides for speaker: {speaker_name}")
        pdf_path = find_matching_pdf(speaker_name)
        slides_raw = ""
        if pdf_path:
            logger.info(f"Found matching PDF: {pdf_path}")
            slides_raw = extract_pdf_content(pdf_path)
            logger.info(f"Extracted slides content: {len(slides_raw)} characters")
        else:
            logger.warning(f"No matching PDF found for speaker: {speaker_name}")
        
        # Preprocess transcript
        logger.info(f"Preprocessing transcript for speaker: {speaker_name}")
        transcript_raw = ""
        transcript_source = ""
        
        # First try local video (faster and more reliable)
        video_path = find_matching_video(speaker_name)
        if video_path:
            logger.info(f"Found matching local video: {video_path}")
            transcript_result = extract_local_video_transcript(video_path)
            if transcript_result["success"]:
                transcript_raw = transcript_result["srt_content"]
                transcript_source = "local_video"
                logger.info(f"Extracted local video transcript: {len(transcript_raw)} characters")
            else:
                logger.warning(f"Local video transcript extraction failed: {transcript_result.get('error', 'Unknown error')}")
        
        # If no local video transcript and YouTube URL provided, try YouTube
        if not transcript_raw and yt_url:
            logger.info(f"No local video transcript, trying YouTube: {yt_url}")
            transcript_result = extract_youtube_transcript(yt_url)
            if transcript_result["success"]:
                transcript_raw = transcript_result["srt_content"]
                transcript_source = "youtube"
                logger.info(f"Extracted YouTube transcript: {len(transcript_raw)} characters")
            else:
                logger.warning(f"YouTube transcript extraction failed: {transcript_result.get('error', 'Unknown error')}")
        
        if not transcript_raw:
            if not video_path and not yt_url:
                logger.warning(f"No video source found for speaker: {speaker_name} (no local video or YouTube URL)")
            elif not video_path:
                logger.warning(f"No matching local video found for speaker: {speaker_name}")
            elif not yt_url:
                logger.warning(f"Local video failed and no YouTube URL provided for speaker: {speaker_name}")
        
        # Initialize crew after preprocessing
        logger.info("Initializing PrepareTalkCrew")
        crew = PrepareTalkCrew()
        
        # Prepare crew input with preprocessed data
        crew_input = {
            "speaker": speaker_name,
            "yt_url": yt_url or "",
            "slides_raw": slides_raw,
            "transcript_raw": transcript_raw,
            "transcript_source": transcript_source,
            "pdf_path": pdf_path or "",
            "processing_notes": f"Slides: {len(slides_raw)} chars, Transcript: {len(transcript_raw)} chars from {transcript_source}"
        }
        
        # Check if we have enough content to proceed
        if not slides_raw and not transcript_raw:
            error_msg = f"No content found for speaker {speaker_name} - no matching slides or transcript"
            logger.error(error_msg)
            
            # Update Coda with error
            coda_updates = {
                "Webhook status": "Failed",
                "Webhook progress": error_msg
            }
            updates = [{"row_id": coda_ids.row_id, "updates": coda_updates}]
            coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
            
            return {"status": "failed", "message": error_msg, "speaker": speaker_name}
        
        logger.info(f"Running PrepareTalkCrew with preprocessed content")
        logger.debug(f"Crew input keys: {list(crew_input.keys())}")
        
        # Execute the crew with preprocessed data
        crew_result = crew.crew().kickoff(inputs=crew_input)
        
        logger.info("PrepareTalkCrew completed successfully")
        logger.debug(f"Crew result type: {type(crew_result)}")
        
        # Parse the crew result
        if hasattr(crew_result, 'raw'):
            result_text = crew_result.raw
        elif isinstance(crew_result, str):
            result_text = crew_result
        else:
            result_text = str(crew_result)
        
        logger.info(f"Crew result length: {len(result_text)}")
        
        # Try to parse as JSON (expected from final_assembly_task)
        try:
            if result_text.strip().startswith('{') and result_text.strip().endswith('}'):
                crew_output = json.loads(result_text)
                logger.info("Successfully parsed crew output as JSON")
            else:
                # If not JSON, wrap in a basic structure
                logger.warning("Crew output is not JSON, creating basic structure")
                crew_output = {
                    "coda_updates": {
                        "Webhook progress": f"Processed {speaker_name}: crew completed",
                        "Webhook status": "Done"
                    },
                    "raw_output": result_text
                }
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse crew output as JSON: {e}")
            crew_output = {
                "coda_updates": {
                    "Webhook progress": f"Processed {speaker_name}: crew completed (parse warning)",
                    "Webhook status": "Done"
                },
                "raw_output": result_text
            }
        
        # Extract Coda updates from crew output
        coda_updates = crew_output.get("coda_updates", {})
        
        # Ensure we have required status fields
        if "Webhook progress" not in coda_updates:
            coda_updates["Webhook progress"] = f"Processed {speaker_name}: crew completed"
        if "Webhook status" not in coda_updates:
            coda_updates["Webhook status"] = "Done"
        
        # Update Coda row if we have updates
        if coda_updates:
            updates = [{
                "row_id": coda_ids.row_id,
                "updates": coda_updates
            }]
            
            update_result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
            logger.info(f"Updated Coda for {speaker_name}: {update_result}")
            
            # Check if update was successful
            if "successful_updates" in update_result:
                update_data = json.loads(update_result)
                if update_data.get("successful_updates", 0) > 0:
                    return {"status": "success", "message": f"PrepareTalkCrew completed successfully", "speaker": speaker_name}
                else:
                    return {"status": "failed", "message": f"Crew succeeded but Coda update failed: {update_result}", "speaker": speaker_name}
            else:
                # Old format, assume success if no error
                return {"status": "success", "message": f"PrepareTalkCrew completed successfully", "speaker": speaker_name}
        else:
            # No updates from crew
            return {"status": "failed", "message": "Crew completed but produced no Coda updates", "speaker": speaker_name}
            
    except Exception as e:
        logger.error(f"Error in prepare_talk_crew: {e}", exc_info=True)
        
        # Try to update Coda with error status
        try:
            coda_client = CodaClient()
            error_updates = {
                "Webhook status": "Failed",
                "Webhook progress": f"PrepareTalkCrew failed: {str(e)}"
            }
            updates = [{
                "row_id": coda_ids.row_id,
                "updates": error_updates
            }]
            coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
        except Exception as update_error:
            logger.error(f"Failed to update Coda with error status: {update_error}")
        
        return {"status": "failed", "message": f"PrepareTalkCrew error: {str(e)}", "speaker": function_data.get("speaker", "")}