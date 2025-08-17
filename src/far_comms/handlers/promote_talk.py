#!/usr/bin/env python

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from far_comms.crews.promote_talk_crew import PromoteTalkCrew
from far_comms.utils.coda_client import CodaClient
from far_comms.models.requests import TalkRequest, CodaIds
from far_comms.utils.project_paths import get_docs_dir
from far_comms.utils.json_repair import json_repair
from far_comms.utils.social_assembler import assemble_socials
from far_comms.handlers.prepare_talk import prepare_talk, get_input as get_prepare_talk_input

logger = logging.getLogger(__name__)


def _wait_for_coda_update(coda_client: CodaClient, coda_ids: CodaIds, expected_fields: list, max_retries: int = 2) -> dict:
    """
    Wait for Coda to propagate updates with sleep-retry pattern.
    
    Args:
        coda_client: CodaClient instance
        coda_ids: Coda document/table/row identifiers
        expected_fields: List of field names that should have content
        max_retries: Number of retry attempts (default: 2 for 10s + 20s)
    
    Returns:
        dict: Fresh row data from Coda
    """
    retry_delays = [10, 20]  # 10 seconds, then 20 seconds
    
    for attempt in range(max_retries + 1):
        try:
            # Fetch fresh data from Coda
            row_data_str = coda_client.get_row(coda_ids.doc_id, coda_ids.table_id, coda_ids.row_id)
            row_data = json.loads(row_data_str)
            coda_values = row_data.get("data", {})
            
            # Check if expected fields have content
            fields_ready = []
            fields_missing = []
            
            for field in expected_fields:
                field_value = coda_values.get(field, "")
                if field_value and field_value.strip():
                    fields_ready.append(field)
                else:
                    fields_missing.append(field)
            
            if not fields_missing:
                logger.info(f"Coda content ready after {attempt} retries: {fields_ready}")
                return coda_values
            
            if attempt < max_retries:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                logger.info(f"Coda content not ready (missing: {fields_missing}), waiting {delay}s (attempt {attempt + 1}/{max_retries + 1})")
                time.sleep(delay)
            else:
                logger.warning(f"Coda content still not ready after {max_retries} retries (missing: {fields_missing}), continuing anyway")
                return coda_values
                
        except Exception as e:
            logger.error(f"Error checking Coda content (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                logger.info(f"Retrying Coda check in {delay}s...")
                time.sleep(delay)
            else:
                logger.error("Failed to verify Coda updates, continuing without verification")
                return {}
    
    return {}


def get_promote_talk_input(raw_data: dict) -> dict:
    """Parse raw Coda data for integrated promote_talk crew with preprocessing capabilities"""
    return {
        "speaker": raw_data.get("Speaker", ""),
        "title": raw_data.get("Title", ""),
        "talk_title": raw_data.get("Title", ""),  # Alias for YAML compatibility
        "event": raw_data.get("Event", ""),
        "event_name": raw_data.get("Event", ""),  # Alias for YAML compatibility
        "affiliation": raw_data.get("Affiliation", ""),
        "yt_full_link": raw_data.get("YT full link", ""),
        "transcript": raw_data.get("Transcript", ""),
        "transcript_content": raw_data.get("Transcript", ""),  # Alias for YAML compatibility
        "slides_content": raw_data.get("Slides", ""),
        "resource_url": raw_data.get("Resource URL", ""),
        "speaker_x_handle": raw_data.get("X handle", ""),
    }


def display_promote_talk_input(function_data: dict) -> dict:
    """Format function input for webhook display - truncates long fields"""
    display_data = function_data.copy()
    
    # Truncate long fields for display
    for field in ["transcript", "transcript_content", "slides_content"]:
        if len(display_data.get(field, "")) > 100:
            display_data[field] = display_data[field][:100] + "..."
    
    return display_data


async def run_promote_talk(function_data: dict, coda_ids: CodaIds = None):
    """Run integrated promote_talk crew with automatic prepare_talk and assemble_socials"""
    try:
        speaker = function_data.get("speaker", "")
        title = function_data.get("title", "")
        logger.info(f"Starting integrated PromoteTalk crew for {speaker}: {title}")
        
        # Check if slides/transcript are actually missing from Coda (not just input data)
        slides_missing_in_coda = False
        transcript_missing_in_coda = False
        
        if coda_ids:
            # Check actual Coda values to see what's missing
            try:
                coda_client = CodaClient()
                row_data_str = coda_client.get_row(coda_ids.doc_id, coda_ids.table_id, coda_ids.row_id)
                row_data = json.loads(row_data_str)
                coda_values = row_data.get("data", {})
                
                coda_slides = coda_values.get("Slides", "")
                coda_transcript = coda_values.get("Transcript", "")
                
                slides_missing_in_coda = not coda_slides or not coda_slides.strip()
                transcript_missing_in_coda = not coda_transcript or not coda_transcript.strip()
                
                logger.info(f"Coda content check - Slides missing: {slides_missing_in_coda}, Transcript missing: {transcript_missing_in_coda}")
                
                # If content exists in Coda but missing from function_data, use Coda values
                if not slides_missing_in_coda and (not function_data.get("slides_content") or not function_data.get("slides_content").strip()):
                    function_data["slides_content"] = coda_slides
                    logger.info(f"Using existing Coda slides content ({len(coda_slides)} chars)")
                
                if not transcript_missing_in_coda and (not function_data.get("transcript") or not function_data.get("transcript").strip()):
                    function_data["transcript"] = coda_transcript
                    function_data["transcript_content"] = coda_transcript
                    logger.info(f"Using existing Coda transcript content ({len(coda_transcript)} chars)")
                    
            except Exception as e:
                logger.warning(f"Could not check Coda values: {e}, will proceed based on input data")
                # Fall back to checking input data if Coda check fails
                slides_content = function_data.get("slides_content", "")
                transcript_content = function_data.get("transcript", "") or function_data.get("transcript_content", "")
                slides_missing_in_coda = not slides_content or not slides_content.strip()
                transcript_missing_in_coda = not transcript_content or not transcript_content.strip()
        else:
            # No Coda IDs, check input data directly
            slides_content = function_data.get("slides_content", "")
            transcript_content = function_data.get("transcript", "") or function_data.get("transcript_content", "")
            slides_missing_in_coda = not slides_content or not slides_content.strip()
            transcript_missing_in_coda = not transcript_content or not transcript_content.strip()
        
        if slides_missing_in_coda or transcript_missing_in_coda:
            missing_items = []
            if slides_missing_in_coda:
                missing_items.append("slides")
            if transcript_missing_in_coda:
                missing_items.append("transcript")
                
            logger.info(f"Missing content detected: {', '.join(missing_items)}. Running prepare_talk first...")
            
            if coda_ids:
                # Update status to show we're running prepare_talk
                coda_client = CodaClient()
                status_updates = {
                    "Webhook status": "In progress",
                    "Webhook progress": f"Missing {', '.join(missing_items)}, running prepare_talk first..."
                }
                coda_client.update_row(**coda_ids.model_dump(), column_updates=status_updates)
            
            # Run prepare_talk to get missing content
            prepare_talk_data = get_prepare_talk_input({
                "Speaker": speaker,
                "YT full link": function_data.get("yt_full_link", "")
            })
            
            prepare_result = await prepare_talk(prepare_talk_data, coda_ids)
            
            if prepare_result.get("status") != "success":
                error_msg = f"prepare_talk failed: {prepare_result.get('message', 'Unknown error')}"
                logger.error(error_msg)
                
                if coda_ids:
                    error_updates = {
                        "Webhook status": "Error", 
                        "Webhook progress": error_msg
                    }
                    coda_client.update_row(**coda_ids.model_dump(), column_updates=error_updates)
                
                return {"status": "failed", "message": error_msg}
            
            # Use processed content directly from prepare_talk return values
            processed_content = prepare_result.get("processed_content", {})
            
            if slides_missing_in_coda and "slides" in processed_content:
                function_data["slides_content"] = processed_content["slides"]
                logger.info(f"Updated function_data with slides from prepare_talk ({len(processed_content['slides'])} chars)")
            
            if transcript_missing_in_coda and "transcript" in processed_content:
                function_data["transcript"] = processed_content["transcript"]
                function_data["transcript_content"] = processed_content["transcript"]  # alias
                logger.info(f"Updated function_data with transcript from prepare_talk ({len(processed_content['transcript'])} chars)")
                
            logger.info(f"Data flow corrected - using prepare_talk return values instead of Coda refresh")
        
        # Final check - we must have transcript to proceed
        transcript_content = function_data.get("transcript", "") or function_data.get("transcript_content", "")
        if not transcript_content or not transcript_content.strip():
            error_msg = f"Still no transcript available after prepare_talk. Cannot generate social content."
            logger.error(error_msg)
            
            if coda_ids:
                coda_client = CodaClient()
                error_updates = {
                    "Webhook status": "Error", 
                    "Webhook progress": error_msg
                }
                coda_client.update_row(**coda_ids.model_dump(), column_updates=error_updates)
            
            return {"status": "failed", "message": error_msg}
        
        # Log data availability - QA orchestrator will handle conditional processing
        available_data = []
        if function_data.get("resources_existing"): available_data.append("Resources")
        if function_data.get("analysis_existing"): available_data.append("Analysis") 
        if function_data.get("summaries_existing"): available_data.append("Summaries")
        if function_data.get("li_content_existing"): available_data.append("LI content")
        if function_data.get("x_content_existing"): available_data.append("X + Bsky content")
        
        logger.info(f"Available Coda data: {', '.join(available_data) if available_data else 'None - will generate all'}")
        
        # Load style guides and add to crew data
        docs_dir = get_docs_dir()
        style_shared = (docs_dir / "style_shared.md").read_text() if (docs_dir / "style_shared.md").exists() else ""
        style_li = (docs_dir / "style_li.md").read_text() if (docs_dir / "style_li.md").exists() else ""
        style_x = (docs_dir / "style_x.md").read_text() if (docs_dir / "style_x.md").exists() else ""
        
        # Add style guides to crew data
        crew_data = function_data.copy()
        crew_data.update({
            "style_shared": style_shared,
            "style_li": style_li, 
            "style_x": style_x
        })
        
        logger.info(f"Prepared crew data with {len(crew_data.get('transcript', ''))} char transcript")
        
        # Add Coda IDs if provided (for error reporting)
        if coda_ids:
            crew_data.update(coda_ids.model_dump())
            logger.debug(f"Added Coda IDs for error reporting: {coda_ids}")
        
        logger.debug(f"Final crew data keys: {list(crew_data.keys())}")
        logger.debug(f"Final transcript length being sent to crew: {len(crew_data.get('transcript', ''))}")
        
        # Run the crew and capture results
        result = PromoteTalkCrew().crew().kickoff(inputs=crew_data)
        logger.info("Crew completed successfully!")
        
        # Save crew output to consistent directory structure
        from far_comms.utils.project_paths import get_output_dir
        output_dir = get_output_dir()
        speaker_clean = speaker.replace(" ", "_").replace(".", "")
        
        # Use consistent directory: output/grid-LcVoQIcUB2/{speaker}/
        if coda_ids:
            speaker_dir = output_dir / coda_ids.table_id / speaker_clean
        else:
            speaker_dir = output_dir / "grid-LcVoQIcUB2" / speaker_clean  # fallback
        speaker_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = speaker_dir / f"{speaker_clean}_crew_output.json"
        
        try:
            crew_output = result.raw if hasattr(result, 'raw') else str(result)
            
            # Try to parse the crew output for easier access
            from far_comms.utils.json_repair import json_repair
            parsed_output = json_repair(crew_output, fallback_value={"content": crew_output})
            
            output_data = {
                "speaker": speaker,
                "timestamp": datetime.now().isoformat(),
                "parsed_output": parsed_output
            }
            
            with open(output_file, 'w') as f:
                json.dump(output_data, f, indent=2)
            logger.info(f"Saved crew output to: {output_file}")
            
        except Exception as save_error:
            logger.warning(f"Failed to save crew output to file: {save_error}")
            # Continue processing - this shouldn't block Coda updates
        
        # Update Coda with final results if Coda IDs provided
        if coda_ids and result:
            coda_client = CodaClient()
            
            # Parse QA orchestrator output
            try:
                # Extract structured data from crew result
                crew_output = result.raw if hasattr(result, 'raw') else str(result)
                
                # Parse the output using json_repair for robust handling
                parsed_output = json_repair(crew_output, fallback_value={"content": crew_output})
                
                logger.info(f"QA Orchestrator output keys: {list(parsed_output.keys()) if isinstance(parsed_output, dict) else 'Not a dict'}")
                
                # Extract content directly from Coda column structure
                li_content = parsed_output.get("LI content", "")
                x_content = parsed_output.get("X + Bsky content", "")
                paragraph_summary = parsed_output.get("Paragraph", "")  # Updated to match crew output
                webhook_progress = parsed_output.get("Webhook progress", "")
                
                # Extract preprocessing results
                resources_result = parsed_output.get("Resources", "")
                analysis_result = parsed_output.get("Analysis", "")
                
                # Extract final decision from webhook progress text
                publication_decision = "NEEDS_REVISION"  # Default
                if "Status: APPROVED" in webhook_progress:
                    publication_decision = "APPROVED"
                elif "Status: REJECTED" in webhook_progress:
                    publication_decision = "REJECTED"
                
                logger.info(f"Publication decision: {publication_decision}")
                logger.info(f"Webhook progress: {webhook_progress}")
                
                # Map publication decision to Coda status (valid options: Done, Error, Needs Review)
                status_mapping = {
                    "APPROVED": "Done",
                    "NEEDS_REVISION": "Needs Review",  # Content needs human review for quality
                    "REJECTED": "Needs Review"  # Content failed quality standards
                }
                coda_status = status_mapping.get(publication_decision, "Error")  # Default to Error for system failures
                logger.info(f"Setting Coda status: {coda_status}")
                
                # Prepare comprehensive Coda updates (excluding formula-bound columns)
                coda_updates = {
                    "Webhook status": coda_status,
                    "Webhook progress": webhook_progress,
                    # Content outputs
                    "LI content": li_content,
                    "X + Bsky content": x_content, 
                    "Paragraph": paragraph_summary,  # Paragraph summary for Coda
                    # Always update preprocessing results
                    "Resources": resources_result,
                    "Analysis": analysis_result
                }
                
                # Update Coda with crew results first
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": coda_updates
                }]
                
                logger.info(f"Updating Coda with crew results: {list(updates[0]['updates'].keys())}")
                result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                logger.info(f"Crew results update result: {result}")
                
                # Wait for Coda to propagate updates, then fetch fresh data for assemble_socials
                logger.info("Waiting for Coda updates to propagate before running assemble_socials...")
                expected_fields = ["LI content", "X + Bsky content", "Resources"]
                fresh_coda_data = _wait_for_coda_update(coda_client, coda_ids, expected_fields)
                
                # Prepare data for assemble_socials using fresh Coda data (consistent with standalone)
                crew_output = {
                    "LI content": fresh_coda_data.get("LI content", ""),
                    "X + Bsky content": fresh_coda_data.get("X + Bsky content", ""), 
                    "Resources": fresh_coda_data.get("Resources", "")
                }
                
                coda_data = {
                    "event_name": fresh_coda_data.get("Event", "") or function_data.get("event_name", ""),
                    "yt_full_link": fresh_coda_data.get("YT full link", "") or function_data.get("yt_full_link", ""),
                    "speaker": fresh_coda_data.get("Speaker", "") or function_data.get("speaker", "")
                }
                
                # Now run assemble_socials using Coda as single source of truth
                logger.info("Running assemble_socials with fresh Coda data (consistent with standalone)")
                assembled_posts = assemble_socials(crew_output, coda_data)
                
                # Update Coda with assembled social media posts
                social_updates = {
                    "LI post": assembled_posts.get("LI post", ""),
                    "X post": assembled_posts.get("X post", ""),
                    "Bsky post": assembled_posts.get("Bsky post", "")
                }
                
                social_update_list = [{
                    "row_id": coda_ids.row_id,
                    "updates": social_updates
                }]
                
                logger.info(f"Updating Coda with assembled social posts: {list(social_updates.keys())}")
                result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, social_update_list)
                logger.info(f"Social posts update result: {result}")
                logger.info(f"Successfully completed promote_talk with automatic assemble_socials using Coda as single source of truth")
                
                return {"status": "success", "message": f"Completed promote_talk workflow for {speaker}"}
                
            except Exception as update_error:
                logger.error(f"Failed to update Coda with results: {update_error}")
                logger.error(f"Crew output was saved to: {output_file}")
                # Mark as error and put details in Progress
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": {
                        "Webhook status": "Error",
                        "Webhook progress": f"Coda update failed: {str(update_error)}. Crew output saved to file for recovery."
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