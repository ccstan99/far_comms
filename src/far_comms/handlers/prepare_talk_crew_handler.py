#!/usr/bin/env python

import json
import logging
import re
from far_comms.crews.prepare_talk_crew import PrepareTalkCrew
from far_comms.utils.coda_client import CodaClient
from far_comms.models.requests import CodaIds

logger = logging.getLogger(__name__)


def _reconstruct_srt(original_srt: str, cleaned_text: str) -> str:
    """
    Reconstruct SRT format using original timestamps with cleaned text content.
    
    Args:
        original_srt: Original SRT content with timestamps from AssemblyAI
        cleaned_text: Cleaned transcript text (paragraphs with corrected technical terms)
    
    Returns:
        Reconstructed SRT with original timestamps and cleaned text
    """
    try:
        # Parse original SRT to extract timestamps and text segments
        srt_pattern = r'(\d+)\n([\d:,]+ --> [\d:,]+)\n(.*?)(?=\n\d+\n|\n*$)'
        srt_matches = re.findall(srt_pattern, original_srt, re.DOTALL)
        
        if not srt_matches:
            logger.warning("No SRT segments found in original transcript")
            return None
            
        # Extract just the text from original SRT
        original_text_segments = []
        for _, _, text in srt_matches:
            # Clean the text segment (remove extra whitespace, newlines)
            clean_segment = re.sub(r'\s+', ' ', text.strip())
            if clean_segment:
                original_text_segments.append(clean_segment)
        
        original_text = ' '.join(original_text_segments)
        
        # Clean the cleaned_text for comparison (remove paragraph breaks, extra spaces)
        cleaned_text_normalized = re.sub(r'\s+', ' ', cleaned_text.strip())
        
        # Simple approach: if the texts are similar length and content, map word by word
        original_words = original_text.split()
        cleaned_words = cleaned_text_normalized.split()
        
        logger.info(f"Original words: {len(original_words)}, Cleaned words: {len(cleaned_words)}")
        
        # If word counts are very different, fall back to original
        if abs(len(original_words) - len(cleaned_words)) > len(original_words) * 0.1:
            logger.warning(f"Word count difference too large, using original SRT")
            return None
        
        # Map cleaned words back to SRT segments proportionally
        reconstructed_srt = []
        cleaned_word_idx = 0
        
        for seq_num, timestamp, original_segment_text in srt_matches:
            original_segment_words = re.sub(r'\s+', ' ', original_segment_text.strip()).split()
            segment_word_count = len(original_segment_words)
            
            if segment_word_count == 0:
                continue
                
            # Take corresponding words from cleaned text
            end_idx = min(cleaned_word_idx + segment_word_count, len(cleaned_words))
            segment_cleaned_words = cleaned_words[cleaned_word_idx:end_idx]
            cleaned_word_idx = end_idx
            
            if segment_cleaned_words:
                cleaned_segment_text = ' '.join(segment_cleaned_words)
                reconstructed_srt.append(f"{seq_num}\n{timestamp}\n{cleaned_segment_text}\n")
        
        return '\n'.join(reconstructed_srt)
        
    except Exception as e:
        logger.error(f"Error reconstructing SRT: {e}")
        return None


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
        
        # Simple "all or nothing" check: if Transcript exists, content is complete
        try:
            row_data_str = coda_client.get_row(coda_ids.doc_id, coda_ids.table_id, coda_ids.row_id)
            row_data = json.loads(row_data_str)
            row_values = row_data.get("data", {})
            existing_transcript = row_values.get("Transcript", "")
            
            if existing_transcript and existing_transcript.strip():
                logger.info(f"Skipping {speaker_name} - Transcript exists, content is complete")
                return {"status": "skipped", "message": "Transcript exists - content complete", "speaker": speaker_name}
            else:
                # Clear all related fields before reprocessing to ensure consistency
                logger.info(f"No transcript found for {speaker_name} - clearing all fields and reprocessing")
                clear_fields = {
                    "Slides": "",
                    "SRT": "", 
                    "Transcript": "",
                    "Resources": "",
                    "Webhook progress": "Reprocessing from scratch..."
                }
                updates = [{"row_id": coda_ids.row_id, "updates": clear_fields}]
                coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                logger.info(f"Cleared fields for fresh processing: {list(clear_fields.keys())}")
                
        except Exception as e:
            logger.warning(f"Could not check/clear existing content for {speaker_name}: {e}")
            # Continue anyway in case it was just a temporary error
        
        # Preprocess content before running crew
        from far_comms.utils.content_preprocessor import (
            find_matching_pdf, extract_pdf_content, 
            find_matching_video, extract_youtube_transcript, extract_local_video_transcript
        )
        
        # Preprocess slides
        logger.info(f"Preprocessing slides for speaker: {speaker_name}")
        pdf_path = find_matching_pdf(speaker_name)
        slides_data = None
        slides_raw = ""
        qr_codes = []
        visual_elements = []
        
        if pdf_path:
            logger.info(f"Found matching PDF: {pdf_path}")
            slides_data = extract_pdf_content(pdf_path)
            slides_raw = slides_data["enhanced_content"]  # Use enhanced content with visual descriptions
            qr_codes = slides_data["qr_codes"]
            visual_elements = slides_data["visual_elements"]
            logger.info(f"Extracted slides: {len(slides_raw)} chars, {len(qr_codes)} QR codes, {len(visual_elements)} visual elements")
        else:
            logger.warning(f"No matching PDF found for speaker: {speaker_name}")
        
        # Preprocess transcript
        logger.info(f"Preprocessing transcript for speaker: {speaker_name}")
        transcript_raw = ""
        transcript_source = ""
        
        # Try local video first (faster and more reliable)
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
        else:
            # No local video found, try YouTube download if URL provided
            if yt_url:
                logger.info(f"No local video found, trying YouTube: {yt_url}")
                transcript_result = extract_youtube_transcript(yt_url)
                if transcript_result["success"]:
                    transcript_raw = transcript_result["srt_content"]
                    transcript_source = "youtube"
                    logger.info(f"Extracted YouTube transcript: {len(transcript_raw)} characters")
                else:
                    logger.warning(f"YouTube transcript extraction failed: {transcript_result.get('error', 'Unknown error')}")
            else:
                logger.warning(f"No local video found and no YouTube URL provided for {speaker_name}")
        
        if not transcript_raw:
            if not video_path and not yt_url:
                logger.warning(f"No video source found for speaker: {speaker_name} (no local video or YouTube URL)")
            elif video_path and not yt_url:
                logger.warning(f"Local video failed and no YouTube URL provided for speaker: {speaker_name}")
            else:
                logger.warning(f"Both local video and YouTube failed for speaker: {speaker_name}")
        
        # Initialize crew after preprocessing
        logger.info("Initializing PrepareTalkCrew")
        crew = PrepareTalkCrew()
        
        # Load style guides for transcript processing
        from pathlib import Path
        docs_dir = Path(__file__).parent.parent.parent / "docs"
        style_transcript = (docs_dir / "prompt_transcript.md").read_text() if (docs_dir / "prompt_transcript.md").exists() else ""
        
        # Prepare crew input with preprocessed data (always fresh processing)
        crew_input = {
            "speaker": speaker_name,
            "yt_url": yt_url or "",
            "slides_raw": slides_raw,
            "transcript_raw": transcript_raw,
            "transcript_source": transcript_source,
            "pdf_path": pdf_path or "",
            "qr_codes": qr_codes,
            "visual_elements": visual_elements,
            "style_transcript": style_transcript,
            "processing_notes": f"Slides: {len(slides_raw)} chars, QR codes: {len(qr_codes)}, Visual elements: {len(visual_elements)}, Transcript: {len(transcript_raw)} chars from {transcript_source}",
            # Pass Coda row data for speaker validation
            "coda_speaker": row_values.get("Speaker", ""),
            "coda_affiliation": row_values.get("Affiliation", ""), 
            "coda_title": row_values.get("Title", "")
        }
        
        # Check if we have enough content to proceed
        if not slides_raw and not transcript_raw:
            error_msg = f"Cannot process {speaker_name} - no slides or transcript found (no PDF, no local video, YouTube failed)"
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
            # Clean result_text - remove code blocks if present
            cleaned_text = result_text.strip()
            if cleaned_text.startswith('```json'):
                cleaned_text = cleaned_text[7:]  # Remove ```json
            if cleaned_text.startswith('```'):
                cleaned_text = cleaned_text[3:]  # Remove ```
            if cleaned_text.endswith('```'):
                cleaned_text = cleaned_text[:-3]  # Remove trailing ```
            cleaned_text = cleaned_text.strip()
            
            if cleaned_text.startswith('{') and cleaned_text.endswith('}'):
                crew_output = json.loads(cleaned_text)
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
        
        # Post-process transcript formatting: convert double newlines to single newlines
        if "Transcript" in coda_updates and coda_updates["Transcript"]:
            coda_updates["Transcript"] = coda_updates["Transcript"].replace("\n\n", "\n")
            logger.info(f"Post-processed transcript formatting: converted \\n\\n to \\n, length: {len(coda_updates['Transcript'])} chars")
        
        # Reconstruct SRT with original timestamps if we have both raw SRT and cleaned text
        if transcript_raw and "Transcript" in coda_updates:
            # Extract word counts for validation
            original_srt_words = len(re.sub(r'\d+\n[\d:,]+ --> [\d:,]+\n', '', transcript_raw).split())
            cleaned_transcript_words = len(coda_updates["Transcript"].split())
            word_retention_pct = (cleaned_transcript_words / original_srt_words * 100) if original_srt_words > 0 else 0
            
            logger.info(f"Word count validation: Original SRT: {original_srt_words} words, Cleaned: {cleaned_transcript_words} words, Retention: {word_retention_pct:.1f}%")
            
            if word_retention_pct < 90:
                logger.error(f"TRANSCRIPT TRUNCATION DETECTED: Only {word_retention_pct:.1f}% of words retained! Agent failed to preserve verbatim content.")
            
            try:
                reconstructed_srt = _reconstruct_srt(transcript_raw, coda_updates["Transcript"])
                if reconstructed_srt:
                    coda_updates["SRT"] = reconstructed_srt
                    logger.info(f"Reconstructed SRT with original timestamps, length: {len(reconstructed_srt)} chars")
                else:
                    logger.warning("SRT reconstruction failed, using original SRT")
                    coda_updates["SRT"] = transcript_raw
            except Exception as e:
                logger.warning(f"Failed to reconstruct SRT: {e}")
                # Fallback to original SRT if reconstruction fails
                coda_updates["SRT"] = transcript_raw
        
        # Ensure we have required status fields
        if "Webhook progress" not in coda_updates:
            coda_updates["Webhook progress"] = f"Processed {speaker_name}: crew completed"
        if "Webhook status" not in coda_updates:
            coda_updates["Webhook status"] = "Done"
        
        # Log content lengths for debugging truncation issues
        for key, value in coda_updates.items():
            if isinstance(value, str):
                logger.info(f"Coda update '{key}': {len(value)} chars")
                if len(value) > 10000:
                    logger.warning(f"Large content in '{key}': {len(value)} chars - may be truncated by Coda")
        
        # Update Coda in separate batches to handle large content better
        if coda_updates:
            total_successful = 0
            update_results = []
            
            # Batch 1: Large content (Slides, SRT, Transcript)
            large_content_updates = {}
            for key in ["Slides", "SRT", "Transcript"]:
                if key in coda_updates:
                    large_content_updates[key] = coda_updates[key]
            
            if large_content_updates:
                logger.info(f"Updating large content columns: {list(large_content_updates.keys())}")
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": large_content_updates
                }]
                result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                update_results.append(f"Large content: {result}")
                if "successful_updates" in result:
                    result_data = json.loads(result)
                    total_successful += result_data.get("successful_updates", 0)
                else:
                    total_successful += len(large_content_updates)  # Assume success if no error
            
            # Batch 2: Small content (Resources, status fields)
            small_content_updates = {}
            for key in ["Resources", "Webhook progress", "Webhook status"]:
                if key in coda_updates:
                    small_content_updates[key] = coda_updates[key]
            
            if small_content_updates:
                logger.info(f"Updating small content columns: {list(small_content_updates.keys())}")
                updates = [{
                    "row_id": coda_ids.row_id,
                    "updates": small_content_updates
                }]
                result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                update_results.append(f"Small content: {result}")
                if "successful_updates" in result:
                    result_data = json.loads(result)
                    total_successful += result_data.get("successful_updates", 0)
                else:
                    total_successful += len(small_content_updates)  # Assume success if no error
            
            logger.info(f"Updated Coda for {speaker_name} in {len(update_results)} batches: {update_results}")
            
            # Check overall success
            if total_successful > 0:
                return {"status": "success", "message": f"PrepareTalkCrew completed successfully, updated {total_successful} columns", "speaker": speaker_name}
            else:
                return {"status": "failed", "message": f"Crew succeeded but Coda updates failed: {update_results}", "speaker": speaker_name}
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