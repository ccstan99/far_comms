#!/usr/bin/env python

import json
import logging
from pathlib import Path
from far_comms.crews.promote_talk_crew import PromoteTalkCrew
from far_comms.utils.coda_client import CodaClient
from far_comms.models.requests import TalkRequest, CodaIds
from far_comms.utils.project_paths import get_docs_dir

logger = logging.getLogger(__name__)


def get_promote_talk_input(raw_data: dict) -> TalkRequest:
    """Parse raw Coda data into TalkRequest structure"""
    talk_request_data = {
        "speaker": raw_data.get("Speaker", ""),
        "title": raw_data.get("Title", ""),
        "event": raw_data.get("Event", ""),
        "affiliation": raw_data.get("Affiliation", ""),
        "yt_full_link": raw_data.get("YT full link", ""),
        "transcript": raw_data.get("Transcript", ""),
        "resource_url": raw_data.get("Resource URL", ""),
    }
    return TalkRequest(**talk_request_data)


def display_promote_talk_input(function_data: TalkRequest) -> dict:
    """Format function input for webhook display - truncates long fields"""
    display_data = function_data.model_dump()
    
    # Truncate long fields for display
    if len(display_data.get("transcript", "")) > 100:
        display_data["transcript"] = display_data["transcript"][:100] + "..."
    
    return display_data


async def run_promote_talk(talk_request: TalkRequest, coda_ids: CodaIds = None):
    """Run crew in background - accepts TalkRequest directly"""
    try:
        logger.info(f"Starting PromoteTalk crew for {talk_request.speaker}: {talk_request.title}")
        logger.debug(f"Input transcript length: {len(talk_request.transcript or '')}")
        
        # Check if transcript and analysis are available - both required for content generation
        if not talk_request.transcript or not talk_request.transcript.strip():
            error_msg = f"Cannot generate social media content without transcript. Please run 'prepare_talk' first to extract transcript from slides/video."
            logger.error(error_msg)
            
            # Update Coda with error status
            if coda_ids:
                try:
                    coda_client = CodaClient()
                    error_updates = {
                        "Webhook status": "Failed", 
                        "Webhook progress": error_msg
                    }
                    coda_client.update_row(**coda_ids.model_dump(), column_updates=error_updates)
                except Exception as update_error:
                    logger.error(f"Failed to update Coda with error status: {update_error}")
            
            return  # Exit early - cannot proceed without transcript
        
        # Get Analysis from Coda (from prepare-talk processing) - required for content generation
        coda_client = CodaClient()
        analysis_data = ""
        if coda_ids:
            try:
                row_data_str = coda_client.get_row(coda_ids.doc_id, coda_ids.table_id, coda_ids.row_id)
                row_data = json.loads(row_data_str)
                analysis_data = row_data["data"].get("Analysis", "")
                if analysis_data:
                    logger.info(f"Retrieved transcript analysis from prepare-talk: {len(analysis_data)} chars")
                else:
                    logger.warning("No analysis data found - prepare_talk may not have been run yet")
            except Exception as e:
                logger.warning(f"Failed to retrieve analysis data: {e}")
        
        # Check if analysis is available - now required since we moved transcript analysis to prepare-talk
        if not analysis_data or not analysis_data.strip():
            error_msg = f"Cannot generate social media content without transcript analysis. Please run 'prepare_talk' first to generate analysis data."
            logger.error(error_msg)
            
            # Update Coda with error status
            if coda_ids:
                try:
                    error_updates = {
                        "Webhook status": "Failed", 
                        "Webhook progress": error_msg
                    }
                    coda_client.update_row(**coda_ids.model_dump(), column_updates=error_updates)
                except Exception as update_error:
                    logger.error(f"Failed to update Coda with error status: {update_error}")
            
            return  # Exit early - cannot proceed without analysis
        
        logger.info(f"Transcript available ({len(talk_request.transcript)} characters) and analysis available ({len(analysis_data)} characters) - proceeding with content generation")
        
        # Load style guides
        docs_dir = get_docs_dir()
        style_shared = (docs_dir / "style_shared.md").read_text() if (docs_dir / "style_shared.md").exists() else ""
        style_li = (docs_dir / "style_li.md").read_text() if (docs_dir / "style_li.md").exists() else ""
        style_x = (docs_dir / "style_x.md").read_text() if (docs_dir / "style_x.md").exists() else ""
        
        # Lookup speaker's X handle for Twitter/X content attribution
        speaker_x_handle = ""
        try:
            speaker_x_handle = coda_client.get_x_handle(talk_request.speaker)
            logger.info(f"Retrieved X handle for {talk_request.speaker}: {speaker_x_handle}")
        except Exception as e:
            logger.warning(f"X handle lookup failed for {talk_request.speaker}: {e}")
            speaker_x_handle = talk_request.speaker  # Fallback to speaker name
        
        # Convert TalkRequest to crew data format
        crew_data = {
            "transcript": talk_request.transcript or "",
            "analysis": analysis_data,
            "speaker": talk_request.speaker or "",
            "speaker_x_handle": speaker_x_handle,
            "yt_full_link": str(talk_request.yt_full_link) if talk_request.yt_full_link else "",
            "resource_url": str(talk_request.resource_url) if talk_request.resource_url else "",
            "event_name": talk_request.event or "",
            "affiliation": talk_request.affiliation or "",
            # Style guide content
            "style_shared": style_shared,
            "style_li": style_li,
            "style_x": style_x
        }
        
        # Add Coda IDs if provided (for error reporting)
        if coda_ids:
            crew_data.update(coda_ids.model_dump())
            logger.debug(f"Added Coda IDs for error reporting: {coda_ids}")
        
        logger.debug(f"Final crew data keys: {list(crew_data.keys())}")
        logger.debug(f"Final transcript length being sent to crew: {len(crew_data.get('transcript', ''))}")
        
        # Run the crew and capture results
        result = PromoteTalkCrew().crew().kickoff(inputs=crew_data)
        logger.info("Crew completed successfully!")
        
        # Update Coda with final results if Coda IDs provided
        if coda_ids and result:
            coda_client = CodaClient()
            
            # Parse crew output - assuming result has the content we need
            # You may need to adjust these field names based on actual crew output structure
            try:
                # Extract structured data from crew result
                crew_output = result.raw if hasattr(result, 'raw') else str(result)
                
                # Parse the output if it's JSON, otherwise use as string
                try:
                    parsed_output = json.loads(crew_output) if isinstance(crew_output, str) else crew_output
                except (json.JSONDecodeError, TypeError):
                    parsed_output = {"content": crew_output}
                
                logger.info(f"Parsed crew output keys: {list(parsed_output.keys()) if isinstance(parsed_output, dict) else 'Not a dict'}")
                
                # Extract from new clean structure - Coda fields at top level
                paragraph_summary = parsed_output.get("paragraph_ai", "")
                # Skip hooks_ai - raw JSON is unreadable in Coda interface
                li_content = parsed_output.get("li_content", "")
                x_content = parsed_output.get("x_content", "")
                
                # X handle attribution is now handled by the X writer agent during content creation
                
                # Notes section contains all intermediate work
                notes = parsed_output.get("notes", {})
                publication_decision = notes.get("publication_decision", "NEEDS_REVISION")
                
                logger.info(f"Publication decision: {publication_decision}")
                
                # Map publication decision to Coda status
                status_mapping = {
                    "APPROVED": "Done",
                    "NEEDS_REVISION": "Needs review", 
                    "REJECTED": "Error",
                    "NEEDS_MANUAL_REVIEW": "Needs review"
                }
                coda_status = status_mapping.get(publication_decision, "Needs review")
                logger.info(f"Setting Coda status: {coda_status}")
                
                # Prepare final updates for Coda columns
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": {
                        "Webhook status": coda_status,
                        "Webhook progress": json.dumps(parsed_output, indent=2),
                        # Map assembled content to Coda columns:
                        "Paragraph (AI)": paragraph_summary,
                        # Skip "Hooks (AI)" - raw JSON is unreadable in Coda
                        "LI content": li_content,
                        "X content": x_content,
                        "Eval notes": notes.get("eval_notes", "")
                    }
                }]
                
                logger.info(f"Updating Coda columns: {list(updates[0]['updates'].keys())}")
                
                result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                logger.info(f"Coda update result: {result}")
                logger.info(f"Updated Coda with crew results")
                
            except Exception as update_error:
                logger.error(f"Failed to update Coda with results: {update_error}")
                # Mark as error and put details in Progress
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": {
                        "Webhook status": "Error",
                        "Webhook progress": f"Update error: {str(update_error)}"
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
                    "Webhook progress": f"Crew error: {str(e)}"
                }
            }]
            coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
            logger.info(f"Updated Coda row with error status")