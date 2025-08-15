#!/usr/bin/env python

import logging
from far_comms.crews.analyze_talk_crew import AnalyzeTalkCrew
from far_comms.utils.coda_client import CodaClient
from far_comms.models.requests import CodaIds
from far_comms.utils.json_repair import json_repair
# Slide and transcript processing utilities now available:
# from far_comms.utils.slide_processor import process_slides
# from far_comms.utils.transcript_processor import process_transcript

logger = logging.getLogger(__name__)


def get_analyze_talk_input(raw_data: dict) -> dict:
    """Parse raw Coda data for analyze_talk crew - needs slides and transcript content"""
    return {
        "speaker": raw_data.get("Speaker", ""),
        "affiliation": raw_data.get("Affiliation", ""),
        "talk_title": raw_data.get("Title", ""),
        "slides_content": raw_data.get("Slides", ""),
        "transcript_content": raw_data.get("Transcript", "")
    }


def display_analyze_talk_input(function_data: dict) -> dict:
    """Format function input for webhook display - truncate long fields"""
    display_data = function_data.copy()
    
    # Truncate long fields for display
    for field in ["slides_content", "transcript_content"]:
        if len(display_data.get(field, "")) > 100:
            display_data[field] = display_data[field][:100] + "..."
    
    return display_data


async def run_analyze_talk(function_data: dict, coda_ids: CodaIds = None):
    """Run analyze_talk crew in background"""
    try:
        speaker = function_data.get("speaker", "")
        logger.info(f"Starting AnalyzeTalk crew for {speaker}")
        
        # Get all available data - let the agent decide what to do with missing content
        slides_content = function_data.get("slides_content", "").strip()
        transcript_content = function_data.get("transcript_content", "").strip()
        
        # Log what data is available for the agent
        available_data = []
        if slides_content: available_data.append("slides")
        if transcript_content: available_data.append("transcript")
        if not available_data: available_data.append("speaker+title only")
        
        logger.info(f"Resource research will use: {', '.join(available_data)}")
        
        # Always proceed - let the agent handle missing data gracefully
        
        # Prepare crew input with slides and transcript content
        crew_data = {
            "speaker": speaker,
            "affiliation": function_data.get("affiliation", ""),
            "talk_title": function_data.get("talk_title", ""),
            "slides_content": slides_content,  # Will be blank if no slides available
            "transcript_content": transcript_content  # Will be blank if no transcript available
        }
        
        
        # Add Coda IDs if provided (for error reporting)
        if coda_ids:
            crew_data.update(coda_ids.model_dump())
            logger.debug(f"Added Coda IDs for error reporting: {coda_ids}")
        
        logger.debug(f"Final crew data keys: {list(crew_data.keys())}")
        logger.debug(f"Slides available: {len(crew_data['slides_content'])} chars")
        
        # Run the crew and capture results (no CodaRowTool needed)
        crew_instance = AnalyzeTalkCrew()
        result = crew_instance.crew().kickoff(inputs=crew_data)
        logger.info("AnalyzeTalk crew completed successfully!")
        
        # Update Coda with final results if Coda IDs provided
        if coda_ids and result:
            coda_client = CodaClient()
            
            # Handle direct markdown output from transcript analysis task
            try:
                crew_output = result.raw if hasattr(result, 'raw') else str(result)
                logger.info(f"Crew output: {crew_output[:200]}...")
                
                # Direct markdown output from analyze_transcript_task
                analysis_content = crew_output.strip()
                
                # Prepare Coda updates for transcript analysis
                coda_updates = {
                    "Analysis": analysis_content,
                    "Webhook progress": f"Transcript analysis completed: {len(analysis_content)} chars",
                    "Webhook status": "Done"
                }
                
                # Log content lengths for debugging
                for key, value in coda_updates.items():
                    if isinstance(value, str):
                        logger.info(f"Coda update '{key}': {len(value)} chars")
                
                # Update Coda with results
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": coda_updates
                }]
                
                logger.info(f"Updating Coda columns: {list(coda_updates.keys())}")
                
                result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                logger.info(f"Coda update result: {result}")
                logger.info(f"Updated Coda with analysis results")
                
            except Exception as update_error:
                logger.error(f"Failed to update Coda with results: {update_error}")
                # Mark as error and put details in Progress
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": {
                        "Webhook status": "Error",
                        "Webhook progress": f"Analysis error: {str(update_error)}"
                    }
                }]
                coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
        
    except Exception as e:
        logger.error(f"Background crew error: {e}", exc_info=True)
        # If crew fails, update status via CodaClient
        if coda_ids:
            coda_client = CodaClient()
            updates = [{
                "row_id": coda_ids.row_id,
                "updates": {
                    "Webhook status": "Error",
                    "Webhook progress": f"AnalyzeTalk crew error: {str(e)}"
                }
            }]
            coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
            logger.info(f"Updated Coda row with error status")