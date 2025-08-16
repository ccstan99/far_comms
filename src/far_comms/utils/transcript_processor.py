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
                "transcript_srt": ""
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
        
        # Process plain text response (no JSON parsing needed)
        # Extract text from SRT for fallback formatting
        srt_text = re.sub(r'\d+\n[\d:,]+ --> [\d:,]+\n', '', transcript_raw)
        srt_text = re.sub(r'\n+', ' ', srt_text).strip()
        
        # Use the LLM response directly as formatted transcript
        transcript_formatted = result_text.strip()
        
        # Basic validation - ensure we got reasonable content
        if len(transcript_formatted) < len(srt_text) * 0.5:
            logger.warning(f"LLM response seems too short, using fallback")
            transcript_formatted = srt_text
        
        result = {
            "success": True,
            "transcript_formatted": transcript_formatted,
            "transcript_srt": transcript_raw
        }
        
        # Write cleaned transcript to file for easy inspection
        try:
            output_dir = get_output_dir()
            transcript_file = output_dir / f"{speaker_name.replace(' ', '_')}_transcript_cleaned.txt"
            transcript_file.write_text(transcript_formatted, encoding='utf-8')
            logger.info(f"Cleaned transcript saved to: {transcript_file}")
        except Exception as e:
            logger.warning(f"Failed to save transcript file: {e}")
            
        logger.info(f"Successfully processed transcript for {speaker_name}")
        
        return result
            
    except Exception as e:
        logger.error(f"Error processing transcript for {speaker_name}: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "transcript_formatted": "",
            "transcript_srt": ""
        }


def combine_srt_lines(srt_content: str) -> str:
    """
    Combine every 2 SRT entries into 1 to create longer, more readable subtitles.
    Adjusts timestamps to span from first entry start to second entry end.
    """
    try:
        # Parse SRT entries
        srt_pattern = r'(\d+)\n([\d:,]+ --> [\d:,]+)\n(.*?)(?=\n\d+\n|\n*$)'
        srt_matches = re.findall(srt_pattern, srt_content, re.DOTALL)
        
        if not srt_matches:
            logger.warning("No SRT segments found")
            return srt_content
            
        combined_srt = []
        new_seq_num = 1
        
        # Process entries in pairs
        for i in range(0, len(srt_matches), 2):
            first_entry = srt_matches[i]
            
            # If there's a second entry, combine them
            if i + 1 < len(srt_matches):
                second_entry = srt_matches[i + 1]
                
                # Extract timestamps
                first_timestamp = first_entry[1]  # "00:00:05,200 --> 00:00:08,640"
                second_timestamp = second_entry[1]
                
                # Get start time from first entry and end time from second entry
                first_start = first_timestamp.split(' --> ')[0]
                second_end = second_timestamp.split(' --> ')[1]
                combined_timestamp = f"{first_start} --> {second_end}"
                
                # Combine text content
                first_text = first_entry[2].strip()
                second_text = second_entry[2].strip()
                combined_text = f"{first_text} {second_text}"
                
                combined_srt.append(f"{new_seq_num}\n{combined_timestamp}\n{combined_text}\n")
                
            else:
                # Odd number of entries, keep the last one as-is
                seq_num, timestamp, text = first_entry
                combined_srt.append(f"{new_seq_num}\n{timestamp}\n{text.strip()}\n")
            
            new_seq_num += 1
        
        result = '\n'.join(combined_srt)
        logger.info(f"Combined {len(srt_matches)} entries into {len(combined_srt)} entries")
        return result
        
    except Exception as e:
        logger.error(f"Error combining SRT lines: {e}")
        return srt_content


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