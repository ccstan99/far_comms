#!/usr/bin/env python

import re
import logging
from pathlib import Path
from typing import Dict, Any
from far_comms.utils.json_repair import json_repair
from far_comms.utils.project_paths import get_output_dir

logger = logging.getLogger(__name__)


def process_transcript(speaker_name: str, yt_url: str = "", slide_context: str = "") -> Dict[str, Any]:
    """
    Process transcript independently - extract, clean with LLM, preserve verbatim content.
    Maintains current functionality without CrewAI.
    
    Returns:
        dict: Processed transcript data with SRT and formatted versions
    """
    try:
        logger.info(f"Processing transcript for speaker: {speaker_name}")
        
        # Import here to avoid circular imports
        from far_comms.utils.content_preprocessor import (
            find_video, extract_youtube, extract_video
        )
        from anthropic import Anthropic
        import os
        
        # Get transcript using same logic as current implementation (with caching)
        output_dir = get_output_dir()
        output_dir.mkdir(exist_ok=True)
        cache_path = output_dir / f"{speaker_name}.srt"
        
        transcript_raw = ""
        transcript_source = ""
        
        if cache_path.exists():
            logger.info(f"Found cached transcript: {cache_path}")
            transcript_raw = cache_path.read_text(encoding='utf-8')
            transcript_source = "cached_assemblyai"
            logger.info(f"Loaded cached transcript: {len(transcript_raw)} characters")
        else:
            # Try local video first (faster and more reliable)
            video_path = find_video(speaker_name)
            if video_path:
                logger.info(f"Found matching local video: {video_path}")
                transcript_result = extract_video(video_path)
                if transcript_result["success"]:
                    transcript_raw = transcript_result["srt_content"]
                    transcript_source = "local_video"
                    logger.info(f"Extracted local video transcript: {len(transcript_raw)} characters")
                    # Cache the transcript
                    cache_path.write_text(transcript_raw, encoding='utf-8')
                    logger.info(f"Cached transcript to: {cache_path}")
                else:
                    logger.warning(f"Local video transcript extraction failed: {transcript_result.get('error', 'Unknown error')}")
            else:
                # No local video found, try YouTube if URL provided
                if yt_url:
                    logger.info(f"No local video found, trying YouTube: {yt_url}")
                    transcript_result = extract_youtube(yt_url)
                    if transcript_result["success"]:
                        transcript_raw = transcript_result["srt_content"]
                        transcript_source = "youtube"
                        logger.info(f"Extracted YouTube transcript: {len(transcript_raw)} characters")
                        # Cache the transcript
                        cache_path.write_text(transcript_raw, encoding='utf-8')
                        logger.info(f"Cached transcript to: {cache_path}")
                    else:
                        logger.warning(f"YouTube transcript extraction failed: {transcript_result.get('error', 'Unknown error')}")
                else:
                    logger.warning(f"No local video found and no YouTube URL provided for {speaker_name}")
        
        if not transcript_raw:
            logger.warning(f"No transcript found for {speaker_name}")
            return {
                "success": False,
                "error": f"No transcript found for {speaker_name}",
                "transcript_formatted": "",
                "transcript_srt": "",
                "transcript_stats": {},
                "cleaning_notes": "No transcript to process",
                "processing_status": "failed"
            }
        
        # Load docs directory path
        docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        
        # Load prompt from docs/clean_transcript.md
        prompt_path = docs_dir / "clean_transcript.md"
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"clean_transcript.md not found at {prompt_path}")
        
        prompt_template = prompt_path.read_text()
        
        # Use string replacement to avoid conflicts with JSON braces in template
        transcript_prompt = prompt_template.replace("{speaker}", speaker_name)
        transcript_prompt = transcript_prompt.replace("{transcript_raw}", transcript_raw)
        transcript_prompt = transcript_prompt.replace("{transcript_source}", transcript_source)
        transcript_prompt = transcript_prompt.replace("{slide_context}", slide_context[:2000])
        
        # Use LLM to process transcript
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY required for transcript processing")
        
        client = Anthropic(api_key=api_key)
        
        # Call LLM with Sonnet (better for complex JSON output than Haiku)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            messages=[{
                "role": "user",
                "content": transcript_prompt
            }]
        )
        
        result_text = response.content[0].text
        logger.info(f"LLM transcript processing completed: {len(result_text)} characters")
        
        # Parse JSON response using json_repair utility
        # Extract text from SRT for fallback formatting
        srt_text = re.sub(r'\d+\n[\d:,]+ --> [\d:,]+\n', '', transcript_raw)
        srt_text = re.sub(r'\n+', ' ', srt_text).strip()
        
        fallback_result = {
            "success": False,
            "error": "JSON parsing failed",
            "transcript_formatted": srt_text,
            "transcript_srt": transcript_raw,
            "transcript_stats": {
                "original_word_count": len(srt_text.split()),
                "output_word_count": len(srt_text.split()),
                "word_count_percentage": 100.0,
                "paragraph_count": 1
            },
            "cleaning_notes": "LLM processing failed, using raw SRT text",
            "processing_status": "failed",
            "transcript_source": transcript_source
        }
        
        result = json_repair(result_text, max_attempts=3, fallback_value=fallback_result)
        
        # Debug: Check if result is the expected type
        if not isinstance(result, dict):
            logger.error(f"json_repair returned {type(result)} instead of dict. Content: {str(result)[:200]}")
            # If it's a list with one dict, extract the dict
            if isinstance(result, list):
                logger.info(f"Result is list with {len(result)} items")
                if len(result) == 1 and isinstance(result[0], dict):
                    logger.info("Extracting dict from single-item list")
                    result = result[0]
                    logger.info(f"Successfully extracted dict with keys: {list(result.keys())}")
                else:
                    logger.error(f"List format not supported - length: {len(result)}, first item type: {type(result[0]) if result else 'empty'}")
                    result = fallback_result
            else:
                logger.error(f"Unexpected result type: {type(result)}")
                result = fallback_result
        
        # Add success metadata if parsing succeeded
        if result != fallback_result:
            result["transcript_srt"] = transcript_raw
            result["success"] = True
            result["transcript_source"] = transcript_source
            
            # Validate word count retention
            word_count_raw = result.get("transcript_stats", {}).get("word_count_percentage", 0)
            # Handle both float and string formats (e.g., "100.0%" or 100.0)
            if isinstance(word_count_raw, str):
                word_count_pct = float(word_count_raw.rstrip('%'))
            else:
                word_count_pct = float(word_count_raw)
            if word_count_pct < 95:
                logger.error(f"TRANSCRIPT TRUNCATION DETECTED: Only {word_count_pct:.1f}% of words retained!")
                result["processing_status"] = "failed"
            
            logger.info(f"Successfully processed transcript for {speaker_name}, word retention: {word_count_pct:.1f}%")
        else:
            logger.error(f"Failed to parse transcript processing JSON after repair attempts")
        
        return result
            
    except Exception as e:
        logger.error(f"Error processing transcript for {speaker_name}: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "transcript_formatted": "",
            "transcript_srt": "",
            "transcript_stats": {},
            "cleaning_notes": f"Transcript processing failed: {e}",
            "processing_status": "failed",
            "transcript_source": ""
        }


def _reconstruct_srt(original_srt: str, cleaned_text: str) -> str:
    """
    Reconstruct SRT format using original timestamps with cleaned text content.
    (Copied from original handler to maintain functionality)
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