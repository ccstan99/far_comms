#!/usr/bin/env python

import json
import logging
import glob
import os
from far_comms.utils.slide_extractor import get_slide_content
from far_comms.utils.slide_formatter import get_cleaned_text
from far_comms.utils.youtube_transcript import get_youtube_transcript_srt, format_transcript_summary, find_matching_video_file
from far_comms.utils.transcript_cleaner import clean_srt_transcript, format_transcript_for_reading
from far_comms.utils.coda_client import CodaClient
from far_comms.models.requests import CodaIds

logger = logging.getLogger(__name__)


def get_prepare_talk_input(raw_data: dict) -> dict:
    """Parse raw Coda data for prepare_talk - needs speaker name and YouTube URL"""
    return {
        "speaker": raw_data.get("Speaker", ""),
        "yt_full_link": raw_data.get("YT url", "")
    }


def display_prepare_talk_input(function_data: dict) -> dict:
    """Format function input for webhook display - no long fields to truncate"""
    return function_data


def extract_topic_flow_from_slides(slide_content: str) -> str:
    """Extract key topic flow information from slides to help with paragraph formatting"""
    if not slide_content:
        return ""
    
    # Extract headers, section titles, and key transition phrases
    import re
    lines = slide_content.split('\n')
    
    topic_flow_elements = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Look for markdown headers
        if line.startswith('#'):
            topic_flow_elements.append(line)
        # Look for potential section titles (short lines that look like titles)
        elif (len(line) < 100 and 
              (line.isupper() or line.istitle()) and 
              not line.endswith('.') and
              any(word in line.lower() for word in ['method', 'approach', 'results', 'conclusion', 'introduction', 'background', 'experiment', 'evaluation', 'related work', 'future work'])):
            topic_flow_elements.append(f"Section: {line}")
        # Look for bullet points that might indicate topic transitions
        elif line.startswith(('- ', '• ', '* ')) and len(line) < 150:
            topic_flow_elements.append(line)
    
    # Limit to first 20 elements to stay within context
    return '\n'.join(topic_flow_elements[:20])


def find_matching_slide(speaker_name: str, slide_files: list) -> str | None:
    """Find slide file that matches speaker name using shared matching logic"""
    from far_comms.utils.file_matcher import find_best_matching_file
    
    if not slide_files:
        logger.warning("No slide files provided")
        return None
    
    # Use shared file matching logic
    return find_best_matching_file(speaker_name, slide_files, min_score=40)


async def prepare_talk(function_data: dict, coda_ids: CodaIds) -> dict:
    """Prepare a single talk by extracting and updating slide content
    
    Returns:
        dict: {"status": "success|skipped|failed", "message": "details", "speaker": "name"}
    """
    try:
        logger.info(f"Starting prepare_talk for row {coda_ids.row_id}")
        
        # Get speaker name and YouTube URL from function_data (already parsed)
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
            slides_exist = False
            srt_exists = False
        
        # Prepare updates for Coda
        coda_updates = {}
        processing_messages = []
        
        # Process slides if not already done
        if not slides_exist:
            slide_files = glob.glob("data/slides/*.pdf")
            matched_file = find_matching_slide(speaker_name, slide_files)
            
            if matched_file:
                logger.info(f"Found matching file: {matched_file}")
                
                # Extract slide content (text + images for multimodal analysis)
                slide_result = get_slide_content(matched_file, max_slides=-1)  # Process all slides
                
                if slide_result.get("success"):
                    # Clean the extracted text content using LLM
                    cleaned_result = get_cleaned_text(slide_result)
                    
                    # Use markdown formatted version if available, otherwise fall back to content
                    slide_content = cleaned_result.get("content_markdown") or cleaned_result.get("content", "")
                    logger.info(f"Extracted and cleaned {len(slide_content)} characters from slides")
                    
                    coda_updates["Slides"] = slide_content
                    processing_messages.append(f"extracted slides ({len(slide_content)} chars)")
                    
                    # Add resources if found
                    resources_formatted = cleaned_result.get("resources_formatted")
                    if resources_formatted:
                        coda_updates["Resources"] = resources_formatted
                        resource_count = len(cleaned_result.get("resources", []))
                        logger.info(f"Found {resource_count} resources in slides")
                        processing_messages.append(f"{resource_count} resources found")
                else:
                    error_msg = slide_result.get('error', 'Unknown extraction error')
                    logger.error(f"Failed to extract slides for {speaker_name}: {error_msg}")
                    processing_messages.append(f"slide extraction failed: {error_msg}")
            else:
                logger.warning(f"No matching slide file found for speaker: {speaker_name}")
                processing_messages.append("no matching slide file found")
        else:
            logger.info(f"Slides already exist for {speaker_name}, skipping slide extraction")
            processing_messages.append("slides already exist")
        
        # Process video transcript if not already done
        if not srt_exists:
            # Find matching local video file
            matched_video = find_matching_video_file(speaker_name)
            
            if matched_video:
                logger.info(f"Found matching video: {matched_video}")
                logger.info(f"Extracting transcript from local video file")
                transcript_result = get_youtube_transcript_srt(yt_url or "", matched_video)
                
                if transcript_result.get("success"):
                    raw_srt_content = transcript_result.get("srt_content", "")
                    logger.info(f"Successfully extracted raw transcript: {len(raw_srt_content)} characters")
                    
                    # Clean the transcript using LLM with slides context
                    logger.info("Cleaning transcript with LLM using slides context")
                    slide_content = coda_updates.get("Slides", "") or row_values.get("Slides", "")
                    
                    cleaning_result = clean_srt_transcript(raw_srt_content, slide_content)
                    
                    if cleaning_result.get("cleaned_srt"):
                        cleaned_srt = cleaning_result.get("cleaned_srt")
                        logger.info(f"Successfully cleaned transcript: {cleaning_result.get('processing_notes', '')}")
                        
                        # Format cleaned SRT into readable paragraphs for Transcript column
                        logger.info("Formatting cleaned transcript for readability")
                        # Extract key topic flow info from slides for better paragraph breaks
                        topic_context = extract_topic_flow_from_slides(slide_content) if slide_content else ""
                        formatting_result = format_transcript_for_reading(cleaned_srt, topic_context or slide_content)
                        
                        if formatting_result.get("formatted_transcript"):
                            formatted_transcript = formatting_result.get("formatted_transcript")
                            logger.info(f"Successfully formatted transcript: {formatting_result.get('processing_notes', '')}")
                            
                            # Store both SRT (with timestamps) and Transcript (readable paragraphs)
                            coda_updates["SRT"] = cleaned_srt
                            coda_updates["Transcript"] = formatted_transcript
                            processing_messages.append(f"extracted, cleaned & formatted transcript ({len(cleaned_srt)} chars SRT, {len(formatted_transcript)} chars text)")
                        else:
                            # Just store SRT if formatting failed
                            logger.warning("Transcript formatting failed, storing only SRT")
                            coda_updates["SRT"] = cleaned_srt
                            processing_messages.append(f"extracted & cleaned transcript - formatting failed ({len(cleaned_srt)} chars)")
                    else:
                        # Fallback to raw SRT if cleaning failed
                        logger.warning("Transcript cleaning failed, using raw SRT")
                        coda_updates["SRT"] = raw_srt_content
                        processing_messages.append(f"extracted transcript - cleaning failed ({len(raw_srt_content)} chars)")
                else:
                    error_msg = transcript_result.get("error", "Unknown transcript error")
                    logger.error(f"Failed to extract transcript for {speaker_name}: {error_msg}")
                    processing_messages.append(f"transcript extraction failed: {error_msg}")
            else:
                logger.warning(f"No matching video file found for speaker: {speaker_name}")
                processing_messages.append("no matching video file found")
        else:
            logger.info(f"SRT already exists for {speaker_name}, skipping transcript extraction")
            processing_messages.append("transcript already exists")
        
        # Update Webhook progress column with processing summary and mark as done
        if processing_messages:
            progress_message = f"Processed {speaker_name}: " + ", ".join(processing_messages)
            coda_updates["Webhook progress"] = progress_message
            coda_updates["Webhook status"] = "Done"
        
        # Update Coda row if we have any updates
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
                    return {"status": "success", "message": ", ".join(processing_messages), "speaker": speaker_name}
                else:
                    return {"status": "failed", "message": f"Processing succeeded but Coda update failed: {update_result}", "speaker": speaker_name}
            else:
                # Old format, assume success if no error
                return {"status": "success", "message": ", ".join(processing_messages), "speaker": speaker_name}
        else:
            # Nothing to process
            return {"status": "skipped", "message": "No processing needed - all content already exists", "speaker": speaker_name}
            
    except Exception as e:
        logger.error(f"Error in prepare_talk: {e}", exc_info=True)
        return {"status": "failed", "message": f"Unexpected error: {str(e)}", "speaker": function_data.get("speaker", "")}