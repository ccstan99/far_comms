#!/usr/bin/env python

import re
import logging
from typing import Dict, List, Tuple
from crewai import LLM

logger = logging.getLogger(__name__)


def load_transcript_guidelines() -> str:
    """Load transcript processing guidelines from docs/prompt_transcript.md"""
    try:
        with open('docs/prompt_transcript.md', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("Transcript guidelines not found at docs/prompt_transcript.md")
        return ""


def extract_srt_text_only(srt_content: str) -> str:
    """
    Extract just the text content from SRT format, removing timestamps
    
    Args:
        srt_content: Full SRT content with timestamps
    
    Returns:
        Plain text content from the transcript
    """
    if not srt_content:
        return ""
    
    # Split into blocks and extract text (skip sequence numbers and timestamps)
    blocks = srt_content.strip().split('\n\n')
    text_lines = []
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:  # Valid SRT block has: number, timestamp, text
            # Everything after the timestamp line is text
            text_content = '\n'.join(lines[2:]).strip()
            if text_content:
                text_lines.append(text_content)
    
    return ' '.join(text_lines)


def reconstruct_srt_with_clean_text(original_srt: str, cleaned_text: str) -> str:
    """
    Reconstruct SRT format using cleaned text while preserving original timestamps
    
    Args:
        original_srt: Original SRT with timestamps
        cleaned_text: Cleaned transcript text
    
    Returns:
        SRT format with original timestamps but cleaned text
    """
    if not original_srt or not cleaned_text:
        return original_srt
    
    # Extract timestamp information
    blocks = original_srt.strip().split('\n\n')
    timestamps = []
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 2 and '-->' in lines[1]:
            timestamps.append({
                'number': lines[0].strip(),
                'timestamp': lines[1].strip()
            })
    
    if not timestamps:
        logger.warning("No valid SRT timestamps found")
        return original_srt
    
    # Split cleaned text into roughly equal segments for each timestamp
    words = cleaned_text.split()
    if not words:
        return original_srt
    
    words_per_segment = max(1, len(words) // len(timestamps))
    
    # Reconstruct SRT
    srt_blocks = []
    word_index = 0
    
    for i, ts_info in enumerate(timestamps):
        # Get words for this segment
        if i == len(timestamps) - 1:  # Last segment gets remaining words
            segment_words = words[word_index:]
        else:
            segment_words = words[word_index:word_index + words_per_segment]
            word_index += words_per_segment
        
        if segment_words:  # Only add if there are words
            text = ' '.join(segment_words)
            srt_blocks.append(f"{ts_info['number']}\n{ts_info['timestamp']}\n{text}")
    
    return '\n\n'.join(srt_blocks) + '\n'


def clean_transcript_with_llm(transcript_text: str, slides_content: str = "") -> Dict[str, str]:
    """
    Clean transcript text using LLM with guidelines and slides context
    
    Args:
        transcript_text: Raw transcript text to clean
        slides_content: Related slide content for context
    
    Returns:
        Dict with 'cleaned_text' and 'processing_notes'
    """
    if not transcript_text or not transcript_text.strip():
        return {
            "cleaned_text": transcript_text,
            "processing_notes": "No transcript content to clean"
        }
    
    try:
        # Load guidelines
        guidelines = load_transcript_guidelines()
        
        # Create cleaning prompt
        cleaning_prompt = f"""Clean this video transcript following the exact guidelines provided. This is from an academic AI safety talk.

GUIDELINES:
{guidelines}

SLIDES CONTEXT (for technical term accuracy):
{slides_content[:1000] if slides_content else 'No slides available'}

TRANSCRIPT TO CLEAN:
{transcript_text}

INSTRUCTIONS:
1. Fix spelling, grammar, and punctuation errors common in speech-to-text
2. Apply ALL style guidelines exactly (AI model names, hyphenated terms, etc.)
3. Remove filler words (um, uh, you know) unless contextually important
4. Clean up false starts and repetitions
5. Preserve all technical accuracy and meaning
6. Keep the academic tone appropriate for the content
7. Use slides context to ensure technical terms are correct

Return only the cleaned transcript text. Do not add explanations or commentary."""

        llm = LLM(
            model="anthropic/claude-3-5-sonnet-20241022",  # Higher quality for better cleaning
            max_retries=2
        )
        
        logger.info(f"Cleaning transcript with LLM: {len(transcript_text)} characters")
        
        # Get cleaned content from LLM
        cleaned_result = llm.call(cleaning_prompt)
        
        # Extract the actual text response
        if hasattr(cleaned_result, 'content'):
            cleaned_text = cleaned_result.content
        elif isinstance(cleaned_result, str):
            cleaned_text = cleaned_result
        else:
            cleaned_text = str(cleaned_result)
        
        cleaned_text = cleaned_text.strip()
        
        # Basic validation - make sure we didn't lose too much content
        if len(cleaned_text) < len(transcript_text) * 0.3:  # Lost more than 70%
            logger.warning("LLM cleaning removed too much content, using original")
            return {
                "cleaned_text": transcript_text,
                "processing_notes": "LLM cleaning removed too much content, kept original"
            }
        
        processing_notes = f"Cleaned transcript: {len(transcript_text)} → {len(cleaned_text)} characters"
        logger.info(processing_notes)
        
        return {
            "cleaned_text": cleaned_text,
            "processing_notes": processing_notes
        }
        
    except Exception as e:
        logger.error(f"Error cleaning transcript: {e}")
        return {
            "cleaned_text": transcript_text,
            "processing_notes": f"Cleaning failed: {str(e)}, kept original"
        }


def format_transcript_for_reading(srt_content: str, slides_content: str = "") -> Dict[str, str]:
    """
    Convert SRT content to human-readable paragraphs using LLM to find logical breaks
    
    Args:
        srt_content: SRT format content with timestamps
        slides_content: Related slide content for context on topic transitions
    
    Returns:
        Dict with 'formatted_transcript' and 'processing_notes'
    """
    if not srt_content or not srt_content.strip():
        return {
            "formatted_transcript": "",
            "processing_notes": "No SRT content to format"
        }
    
    # Extract text-only version first
    text_only = extract_srt_text_only(srt_content)
    
    if not text_only or len(text_only.strip()) < 50:
        return {
            "formatted_transcript": text_only,
            "processing_notes": "Content too short, no formatting needed"
        }
    
    try:
        # Use Haiku to find logical paragraph breaks based on content structure
        llm = LLM(
            model="anthropic/claude-3-haiku-20240307",  # Fast and cost-effective
            max_retries=2
        )
        
        # Create paragraph break detection prompt
        paragraph_prompt = f"""Add paragraph breaks to this transcript by inserting [BREAK] markers at logical topic transitions.

SLIDES CONTEXT (for understanding topic flow):
{slides_content[:800] if slides_content else 'No slides available'}

INSTRUCTIONS:
1. Insert [BREAK] markers where natural paragraph breaks should occur
2. Look for topic transitions, new concepts, or shifts in discussion
3. Use slides context to understand the presentation flow
4. Keep sentences completely unchanged - ONLY add [BREAK] markers
5. Don't add breaks too frequently - aim for substantial paragraphs (50-150 words)
6. Don't add [BREAK] at the very beginning or end

TRANSCRIPT TO FORMAT:
{text_only}

Return the transcript with [BREAK] markers inserted at logical paragraph boundaries. Change NO words - only add [BREAK] markers."""
        
        logger.info(f"Using Haiku to find logical paragraph breaks: {len(text_only)} characters")
        
        # Get paragraph breaks from LLM
        formatted_result = llm.call(paragraph_prompt)
        
        # Extract the actual text response
        if hasattr(formatted_result, 'content'):
            marked_text = formatted_result.content
        elif isinstance(formatted_result, str):
            marked_text = formatted_result
        else:
            marked_text = str(formatted_result)
        
        marked_text = marked_text.strip()
        
        # Split on [BREAK] markers and create paragraphs
        if '[BREAK]' in marked_text:
            paragraphs = [p.strip() for p in marked_text.split('[BREAK]') if p.strip()]
            formatted_transcript = '\n\n'.join(paragraphs)
        else:
            # Fallback to simple formatting if no breaks were added
            logger.warning("LLM didn't add paragraph breaks, using simple formatting")
            formatted_transcript = text_only
        
        processing_notes = f"Formatted transcript using Haiku: {len(text_only)} chars → {len(paragraphs) if '[BREAK]' in marked_text else 1} paragraphs"
        logger.info(processing_notes)
        
        return {
            "formatted_transcript": formatted_transcript,
            "processing_notes": processing_notes
        }
        
    except Exception as e:
        logger.error(f"Error formatting transcript with LLM: {e}")
        # Fallback to simple text-only version
        return {
            "formatted_transcript": text_only,
            "processing_notes": f"LLM formatting failed: {str(e)}, kept text-only version"
        }


def clean_srt_transcript(srt_content: str, slides_content: str = "") -> Dict[str, str]:
    """
    Clean SRT transcript while preserving timestamps
    
    Args:
        srt_content: Original SRT content with timestamps
        slides_content: Related slide content for context
    
    Returns:
        Dict with 'cleaned_srt', 'cleaned_text', and 'processing_notes'
    """
    if not srt_content or not srt_content.strip():
        return {
            "cleaned_srt": srt_content,
            "cleaned_text": "",
            "processing_notes": "No SRT content to clean"
        }
    
    # Extract text-only version
    text_only = extract_srt_text_only(srt_content)
    
    # Clean the text
    cleaning_result = clean_transcript_with_llm(text_only, slides_content)
    cleaned_text = cleaning_result["cleaned_text"]
    
    # Reconstruct SRT with cleaned text
    cleaned_srt = reconstruct_srt_with_clean_text(srt_content, cleaned_text)
    
    return {
        "cleaned_srt": cleaned_srt,
        "cleaned_text": cleaned_text,
        "processing_notes": cleaning_result["processing_notes"]
    }


# Example usage and testing
if __name__ == "__main__":
    # Test with sample SRT content
    sample_srt = """1
00:00:05,200 --> 00:00:07,840
Thank you very much for inviting me to this workshop.

2
00:00:08,400 --> 00:00:12,000
So here I'll be presenting some of our efforts that

3
00:00:12,500 --> 00:00:16,160
we have been continuing in the lines of safety algorithms in"""
    
    print("Testing SRT cleaning...")
    result = clean_srt_transcript(sample_srt, "")
    
    print(f"Processing notes: {result['processing_notes']}")
    print(f"\nCleaned text: {result['cleaned_text'][:200]}...")
    print(f"\nCleaned SRT: {result['cleaned_srt'][:300]}...")