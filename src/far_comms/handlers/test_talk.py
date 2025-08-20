#!/usr/bin/env python

from far_comms.crews.test_talk_crew import TestTalkCrew
from far_comms.utils.coda_client import CodaClient
import logging
import json
from pathlib import Path
import os
from far_comms.utils.project_paths import get_project_root, get_docs_dir

logger = logging.getLogger(__name__)

async def run_test_talk(coda_data: dict, coda_ids, output_dir: Path = None) -> dict:
    """
    Test talk crew runner - generates social content using existing Coda Resources and Analysis
    
    Only runs if Paragraph, LI content AND X content are ALL blank in Coda
    Only updates those 3 columns: Paragraph, LI content, X content
    """
    
    try:
        # Check if required Coda fields exist and have content
        analysis_content = coda_data.get('analysis', '').strip()
        resources_content = coda_data.get('resources', '').strip()
        
        if not analysis_content:
            error_msg = "Cannot run test_talk: Coda Analysis field is empty. Need existing analysis to generate content."
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'data': coda_data
            }
        
        # Check if target fields are ALL blank (don't overwrite existing content)
        paragraph_content = coda_data.get('paragraph', '').strip()
        li_content = coda_data.get('li_content', '').strip()
        x_content = coda_data.get('x_+_bsky_content', '').strip()
        
        if paragraph_content or li_content or x_content:
            error_msg = f"Cannot run test_talk: Target fields not all blank. Found content in: {[k for k, v in [('Paragraph', paragraph_content), ('LI content', li_content), ('X content', x_content)] if v]}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'data': coda_data
            }
        
        logger.info(f"Running test_talk crew for {coda_data.get('speaker', 'Unknown')}")
        
        # Load style guides
        docs_dir = get_docs_dir()
        style_shared = (docs_dir / 'style_shared.md').read_text()
        style_li = (docs_dir / 'style_LI.md').read_text() 
        style_x = (docs_dir / 'style_X.md').read_text()
        
        # Prepare crew inputs - using existing Coda data
        crew_inputs = {
            'speaker': coda_data.get('speaker', ''),
            'affiliation': coda_data.get('affiliation', ''),
            'talk_title': coda_data.get('title', ''),
            'event_name': coda_data.get('event_name', ''),
            'speaker_x_handle': coda_data.get('x_handle', ''),
            'analysis_content': analysis_content,  # Use existing Coda Analysis
            'resources_content': resources_content,  # Use existing Coda Resources
            'transcript_content': coda_data.get('transcript', ''),  # Still needed for fact-checker
            'slides_content': coda_data.get('slides', ''),  # Still needed for fact-checker
            'style_shared': style_shared,
            'style_li': style_li,
            'style_x': style_x
        }
        
        logger.info(f"Starting test_talk crew with Resources: {len(resources_content)} chars, Analysis: {len(analysis_content)} chars")
        
        # Run the test_talk crew (modified workflow)
        test_talk_crew = TestTalkCrew()
        crew_result = test_talk_crew.crew().kickoff(inputs=crew_inputs)
        
        logger.info("Test_talk crew completed successfully")
        
        # Parse crew result
        try:
            if hasattr(crew_result, 'raw'):
                result_text = crew_result.raw
            else:
                result_text = str(crew_result)
            
            logger.info(f"Parsing crew result: {len(result_text)} characters")
            
            # Try to parse as JSON
            if result_text.strip().startswith('{'):
                crew_output = json.loads(result_text)
            else:
                # If not JSON, create a structured response
                crew_output = {
                    "Resources": resources_content,  # Keep existing
                    "Analysis": analysis_content,    # Keep existing
                    "Paragraph": "",
                    "LI content": "",
                    "X + Bsky content": "",
                    "Webhook progress": f"Raw result length: {len(result_text)} chars"
                }
                logger.warning("Crew result not in expected JSON format")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse crew result as JSON: {e}")
            crew_output = {
                "Resources": resources_content,  # Keep existing
                "Analysis": analysis_content,    # Keep existing  
                "Paragraph": "",
                "LI content": "",
                "X + Bsky content": "",
                "Webhook progress": f"Parse error: {str(e)}"
            }
        
        # Update Coda with crew results (only the 3 target fields)
        if coda_ids:
            from far_comms.utils.coda_client import CodaClient
            from far_comms.utils.social_assembler import assemble_socials
            
            try:
                coda_client = CodaClient()
                
                # Prepare updates for only the 3 target fields
                updates = {}
                if crew_output.get("Paragraph"):
                    updates["Paragraph"] = crew_output["Paragraph"]
                if crew_output.get("LI content"):
                    updates["LI content"] = crew_output["LI content"]  
                if crew_output.get("X + Bsky content"):
                    updates["X + Bsky content"] = crew_output["X + Bsky content"]
                
                # Add progress update
                updates["Webhook progress"] = crew_output.get("Webhook progress", "Test_talk completed")
                
                if updates:
                    update_list = [{
                        "row_id": coda_ids.row_id,
                        "updates": updates
                    }]
                    
                    logger.info(f"Updating Coda with test_talk results: {list(updates.keys())}")
                    result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, update_list)
                    logger.info(f"Test_talk results update result: {result}")
                    
                    # Wait for Coda to propagate updates, then run assemble_socials
                    logger.info("Waiting for Coda updates to propagate before running assemble_socials...")
                    import time
                    time.sleep(2)  # Brief wait for propagation
                    
                    # Fetch fresh data for assemble_socials
                    fresh_coda_data_str = coda_client.get_row(coda_ids.doc_id, coda_ids.table_id, coda_ids.row_id)
                    fresh_coda_data = json.loads(fresh_coda_data_str)
                    
                    # Prepare data for assemble_socials using fresh Coda data
                    crew_output_for_assembly = {
                        "LI content": fresh_coda_data.get("LI content", ""),
                        "X + Bsky content": fresh_coda_data.get("X + Bsky content", ""), 
                        "Resources": fresh_coda_data.get("Resources", "")
                    }
                    
                    coda_data_for_assembly = {
                        "event_name": fresh_coda_data.get("Event", "") or coda_data.get("event_name", ""),
                        "yt_full_link": fresh_coda_data.get("YT full link", "") or coda_data.get("yt_full_link", ""),
                        "speaker": fresh_coda_data.get("Speaker", "") or coda_data.get("speaker", "")
                    }
                    
                    # Run assemble_socials
                    logger.info("Running assemble_socials with fresh Coda data")
                    assembled_posts = assemble_socials(crew_output_for_assembly, coda_data_for_assembly)
                    
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
                    logger.info(f"Successfully completed test_talk with automatic assemble_socials")
                    
            except Exception as update_error:
                logger.error(f"Failed to update Coda with test_talk results: {update_error}")
                # Mark as error and put details in Progress
                error_updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": {
                        "Webhook progress": f"Error updating Coda: {str(update_error)}"
                    }
                }]
                try:
                    coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, error_updates)
                except:
                    pass  # Best effort
                
                return {
                    'success': False,
                    'error': f"Coda update failed: {str(update_error)}",
                    'data': coda_data,
                    'crew_output': crew_output
                }
        
        # Create output data for return (for non-Coda usage)
        output_data = coda_data.copy()
        
        # Only update these 3 fields if crew generated content
        if crew_output.get("Paragraph"):
            output_data['paragraph'] = crew_output["Paragraph"]
        if crew_output.get("LI content"):
            output_data['li_content'] = crew_output["LI content"]  
        if crew_output.get("X + Bsky content"):
            output_data['x_+_bsky_content'] = crew_output["X + Bsky content"]
        
        # Update progress
        output_data['webhook_progress'] = crew_output.get("Webhook progress", "Test_talk completed")
        
        # Save output file if directory provided
        if output_dir:
            output_file = output_dir / f"{coda_data.get('speaker', 'unknown').replace(' ', '_')}_test_talk_output.json"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump({
                    'speaker': coda_data.get('speaker'),
                    'timestamp': crew_result.timestamp if hasattr(crew_result, 'timestamp') else None,
                    'parsed_output': crew_output
                }, f, indent=2)
            logger.info(f"Output saved to {output_file}")
        
        return {
            'success': True,
            'data': output_data,
            'crew_output': crew_output
        }
        
    except Exception as e:
        error_msg = f"Test_talk crew failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Update progress with error
        error_data = coda_data.copy()
        error_data['webhook_progress'] = f"Error: {str(e)}"
        
        return {
            'success': False,
            'error': error_msg,
            'data': error_data
        }

def get_test_talk_input(raw_data: dict) -> dict:
    """Extract and validate test_talk input data"""
    return {
        'speaker': raw_data.get('Speaker', ''),
        'affiliation': raw_data.get('Affiliation', ''),
        'title': raw_data.get('Title', ''),
        'event_name': raw_data.get('Event name', ''),
        'x_handle': raw_data.get('X handle', ''),
        'analysis': raw_data.get('Analysis', ''),
        'resources': raw_data.get('Resources', ''),
        'transcript': raw_data.get('Transcript', ''),  # Still needed for fact-checker
        'slides': raw_data.get('Slides', ''),  # Still needed for fact-checker  
        'paragraph': raw_data.get('Paragraph', ''),
        'li_content': raw_data.get('LI content', ''),
        'x_+_bsky_content': raw_data.get('X + Bsky content', '')
    }

def display_test_talk_input(function_data: dict) -> dict:
    """Display test_talk input data for user confirmation"""
    return {
        'Speaker': function_data.get('speaker', ''),
        'Title': function_data.get('title', ''),
        'Analysis Available': 'Yes' if function_data.get('analysis', '').strip() else 'No',
        'Resources Available': 'Yes' if function_data.get('resources', '').strip() else 'No',
        'Target Fields Status': {
            'Paragraph': 'Blank' if not function_data.get('paragraph', '').strip() else 'Has Content',
            'LI content': 'Blank' if not function_data.get('li_content', '').strip() else 'Has Content', 
            'X content': 'Blank' if not function_data.get('x_+_bsky_content', '').strip() else 'Has Content'
        }
    }