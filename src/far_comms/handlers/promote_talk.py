#!/usr/bin/env python

import json
import logging
from datetime import datetime
from pathlib import Path
from far_comms.crews.promote_talk_crew import PromoteTalkCrew
from far_comms.utils.coda_client import CodaClient
from far_comms.models.requests import TalkRequest, CodaIds
from far_comms.utils.project_paths import get_docs_dir
from far_comms.utils.json_repair import json_repair
from far_comms.utils.social_assembler import assemble_socials

logger = logging.getLogger(__name__)


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
    """Run integrated promote_talk crew with preprocessing capabilities"""
    try:
        speaker = function_data.get("speaker", "")
        title = function_data.get("title", "")
        logger.info(f"Starting integrated PromoteTalk crew for {speaker}: {title}")
        
        # Check minimum requirements - only transcript is essential
        if not function_data.get("transcript") or not function_data.get("transcript").strip():
            error_msg = f"Cannot generate social media content without transcript. Please run 'prepare_talk' first."
            logger.error(error_msg)
            
            # Update Coda with error status
            if coda_ids:
                try:
                    coda_client = CodaClient()
                    error_updates = {
                        "Webhook status": "Error", 
                        "Webhook progress": error_msg
                    }
                    coda_client.update_row(**coda_ids.model_dump(), column_updates=error_updates)
                except Exception as update_error:
                    logger.error(f"Failed to update Coda with error status: {update_error}")
            
            return  # Exit early - cannot proceed without transcript
        
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
        
        # Save crew output to file before attempting Coda updates
        from far_comms.utils.project_paths import get_output_dir
        output_dir = get_output_dir() / "promote_talk"
        output_dir.mkdir(exist_ok=True)
        
        speaker_clean = speaker.replace(" ", "_").replace(".", "").lower()
        output_file = output_dir / f"{speaker_clean}_crew_output.json"
        
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
                
                # Assemble platform-specific social media posts
                assembled_posts = assemble_socials(parsed_output, function_data)
                
                # Prepare comprehensive Coda updates (excluding formula-bound columns)
                coda_updates = {
                    "Webhook status": coda_status,
                    "Webhook progress": webhook_progress,
                    # Content outputs
                    "LI content": li_content,
                    "X + Bsky content": x_content, 
                    "Paragraph": paragraph_summary,  # Paragraph summary for Coda
                    # Assembled social media posts
                    "LI post": assembled_posts.get("LI post", ""),
                    "X post": assembled_posts.get("X post", ""),
                    "Bsky post": assembled_posts.get("Bsky post", ""),
                    # Always update preprocessing results
                    "Resources": resources_result,
                    "Analysis": analysis_result
                }
                
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": coda_updates
                }]
                
                logger.info(f"Updating Coda columns: {list(updates[0]['updates'].keys())}")
                
                result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                logger.info(f"Coda update result: {result}")
                logger.info(f"Updated Coda with crew results")
                
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