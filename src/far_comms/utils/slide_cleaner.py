#!/usr/bin/env python

import logging
from crewai import LLM

logger = logging.getLogger(__name__)


def clean_slide_content(raw_content: str) -> str:
    """
    Use LLM to clean up messy slide text extraction artifacts
    
    Args:
        raw_content: Raw text extracted from PDF/PPTX slides
    
    Returns:
        Cleaned, readable text suitable for content generation
    """
    if not raw_content or not raw_content.strip():
        return raw_content
    
    # If content is too short, probably clean enough already
    if len(raw_content.strip()) < 100:
        return raw_content.strip()
    
    try:
        llm = LLM(
            model="anthropic/claude-haiku-3-20240307",  # Fast, cheap model for cleaning
            max_retries=2
        )
        
        # Create cleaning prompt
        cleaning_prompt = f"""Clean up this slide text that was extracted from a PDF. Remove:
- Math equation artifacts and garbled symbols
- Repeated headers/footers 
- Random formatting characters
- Broken table layouts
- Page numbers and slide metadata

Keep the meaningful content and structure. Make it readable and coherent:

---SLIDE TEXT---
{raw_content}
---END SLIDE TEXT---

Return only the cleaned text, no explanations."""

        logger.info(f"Cleaning {len(raw_content)} characters of slide content")
        
        # Get cleaned content from LLM
        cleaned_result = llm.invoke(cleaning_prompt)
        
        # Extract the actual text response
        if hasattr(cleaned_result, 'content'):
            cleaned_content = cleaned_result.content
        elif isinstance(cleaned_result, str):
            cleaned_content = cleaned_result
        else:
            cleaned_content = str(cleaned_result)
        
        cleaned_content = cleaned_content.strip()
        
        # Basic validation - make sure we didn't lose too much content
        if len(cleaned_content) < len(raw_content) * 0.3:  # Lost more than 70%
            logger.warning("LLM cleaning removed too much content, using original")
            return raw_content
        
        logger.info(f"Cleaned content: {len(raw_content)} → {len(cleaned_content)} characters")
        return cleaned_content
        
    except Exception as e:
        logger.error(f"Error cleaning slide content: {e}")
        logger.info("Falling back to original content")
        return raw_content


def clean_slide_content_batch(slides: list) -> list:
    """
    Clean content for multiple slides while preserving structure
    
    Args:
        slides: List of slide dicts with 'content' field
    
    Returns:
        List of slides with cleaned content
    """
    cleaned_slides = []
    
    for slide in slides:
        if isinstance(slide, dict) and 'content' in slide:
            cleaned_slide = slide.copy()
            cleaned_slide['content'] = clean_slide_content(slide['content'])
            cleaned_slides.append(cleaned_slide)
        else:
            cleaned_slides.append(slide)  # Pass through unchanged
    
    return cleaned_slides


def clean_full_slide_content(content_dict: dict) -> dict:
    """
    Clean both individual slides and full content in a slide extraction result
    
    Args:
        content_dict: Result from extract_slide_content()
    
    Returns:
        Same dict with cleaned content
    """
    if not content_dict.get('success'):
        return content_dict
    
    result = content_dict.copy()
    
    # Clean full content
    if 'content' in result:
        result['content'] = clean_slide_content(result['content'])
    
    # Clean individual slides
    if 'slides' in result:
        result['slides'] = clean_slide_content_batch(result['slides'])
    
    logger.info(f"Cleaned slide extraction for {result.get('file_name', 'unknown file')}")
    
    return result