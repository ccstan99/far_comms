#!/usr/bin/env python

import asyncio
import base64
import json 
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from far_comms.utils.json_repair import json_repair

logger = logging.getLogger(__name__)

def titles_equivalent(title1: str, title2: str) -> bool:
    """Check if two titles are equivalent (ignoring case differences)."""
    if not title1 or not title2:
        return title1 == title2
    
    # Normalize both titles: strip, normalize whitespace, convert to lowercase for comparison
    norm1 = ' '.join(title1.strip().split()).lower()
    norm2 = ' '.join(title2.strip().split()).lower()
    
    return norm1 == norm2


def is_placeholder_text(text: str) -> bool:
    """Check if text is missing/empty and shouldn't overwrite good Coda data."""
    # LLM should return empty string for missing data, not placeholder text
    return not text or not text.strip()


def process_slides(speaker_name: str, affiliation: str = "", coda_speaker: str = "", coda_affiliation: str = "", coda_title: str = "", table_id: str = "unknown") -> Dict[str, Any]:
    """
    Process slides independently - extract, clean, validate speaker, find resources.
    Maintains current functionality without CrewAI.
    
    Returns:
        dict: Processed slides data with validation and resources
    """
    try:
        logger.info(f"Processing slides for speaker: {speaker_name}")
        
        # Import here to avoid circular imports
        from far_comms.utils.content_preprocessor import find_pdf, extract_pdf
        from anthropic import Anthropic
        import os
        
        # Find and extract PDF content
        pdf_path = find_pdf(speaker_name)
        if not pdf_path:
            logger.warning(f"No matching PDF found for speaker: {speaker_name}")
            return {
                "success": False,
                "error": f"No PDF found for {speaker_name}",
                "cleaned_slides": "",
                "speaker_validation": {}
            }
        
        logger.info(f"Found matching PDF: {pdf_path}")
        
        # Extract markdown and images using pymupdf4llm as primary method
        import pymupdf4llm
        import pymupdf
        from pathlib import Path
        
        # Create organized output directory structure: output/{table_id}/{speaker_name}/
        output_base = Path(__file__).parent.parent.parent.parent / "output" 
        speaker_output_dir = output_base / table_id / speaker_name.replace(" ", "_")
        images_dir = speaker_output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract markdown using pymupdf4llm (no image fragments needed)
        slides_md_baseline = pymupdf4llm.to_markdown(
            pdf_path,
            write_images=False,
            ignore_images=True
        )
        logger.info(f"Extracted markdown baseline: {len(slides_md_baseline)} chars")
        
        # Initialize Anthropic client for image analysis
        api_key = os.getenv("ANTHROPIC_API_KEY")
        client = None
        if api_key:
            try:
                from anthropic import Anthropic
                client = Anthropic(api_key=api_key)
            except Exception as e:
                logger.warning(f"Anthropic client setup failed: {e}")
        
        # Open document for slide 1 analysis only
        doc = pymupdf.open(pdf_path)
        
        # Quick string search for speaker name validation (faster than LLM analysis)
        slide_1_metadata = {}
        speaker_name_found = False
        
        # Search for speaker name in first 1000 chars (likely title slide area)
        md_beginning = slides_md_baseline[:1000].lower()
        speaker_parts = speaker_name.lower().split()
        
        # Check if all parts of speaker name appear in the markdown beginning
        if len(speaker_parts) >= 2:  # Full name (first + last)
            first_name, last_name = speaker_parts[0], speaker_parts[-1]
            if first_name in md_beginning and last_name in md_beginning:
                speaker_name_found = True
                logger.info(f"Speaker name found via string search: '{speaker_name}' in markdown")
                slide_1_metadata = {
                    "validation_result": "exact_match",
                    "validation_method": "string_search",
                    "slide_speaker": speaker_name,  # Use confirmed name
                    "slide_affiliation": "",  # Will be found by LLM if needed
                    "slide_title": ""  # Will be found by LLM if needed
                }
        
        # Fallback to LLM analysis if string search didn't find speaker name
        if not speaker_name_found and not any(word in slides_md_baseline.lower() for word in ["author", "title"]):
            logger.info("Title/author not found in pymupdf4llm output, analyzing slide 1")
            try:
                page_1 = doc[0]
                pix_1 = page_1.get_pixmap(matrix=pymupdf.Matrix(2, 2))
                img_data_1 = pix_1.tobytes('png')
                img_base64_1 = base64.b64encode(img_data_1).decode()
                
                if client:
                    response = client.messages.create(
                        model="claude-3-haiku-20240307",
                        max_tokens=400,
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"Analyze this title slide and extract speaker information.\n\nExpected speaker from database: {coda_speaker}\n\nTasks:\n1. Extract speaker name and compare with expected name using these rules:\n   - \"exact\": Same person (ignore titles, punctuation, \"and others\")\n   - \"variation\": Same person, different format (Robert vs Bob, missing middle name)\n   - \"different\": Clearly different people\n   - \"not_found\": No speaker name visible\n2. Extract talk title and convert to proper title case (lowercase articles, preserve technical acronyms like AI, LLM, GPU)\n3. Extract affiliation/institution\n\nReturn JSON format: {{\"speaker_name\": \"exact name as written\", \"speaker_match\": \"exact|variation|different|not_found\", \"affiliation\": \"institution\", \"talk_title\": \"Title In Proper Title Case With Preserved Acronyms\"}}"},
                                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_base64_1}}
                            ]
                        }]
                    )
                    
                    metadata_text = response.content[0].text.strip()
                    # Try to parse JSON response
                    analysis = json_repair(metadata_text, fallback_value={})
                    if analysis and analysis.get("speaker_name"):
                        speaker_match = analysis.get("speaker_match", "not_found")
                        validation_result = "exact_match" if speaker_match == "exact" else \
                                          "minor_differences" if speaker_match == "variation" else \
                                          "major_mismatch" if speaker_match == "different" else "major_mismatch"
                        
                        slide_1_metadata = {
                            "slide_speaker": analysis.get("speaker_name", ""),
                            "slide_affiliation": analysis.get("affiliation", ""),
                            "slide_title": analysis.get("talk_title", ""),  # Already in proper title case
                            "validation_result": validation_result,
                            "validation_method": "haiku_visual_analysis"
                        }
                        logger.info(f"Extracted slide 1 metadata - Speaker: {analysis.get('speaker_name')} ({speaker_match}), Title: {analysis.get('talk_title')}")
                    else:
                        logger.warning(f"Could not parse slide 1 metadata JSON: {metadata_text}")
                        
            except Exception as e:
                logger.warning(f"Slide 1 metadata extraction failed: {e}")
        
        # Generate comprehensive visual context for ALL slides 
        visual_context = ""
        qr_codes = []
        if client and len(doc) > 0:
            logger.info("Analyzing all slides for visual context")
            try:
                # Analyze ALL slides for comprehensive visual analysis
                slides_to_analyze = len(doc)
                
                for page_num in range(slides_to_analyze):
                    page = doc[page_num]
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
                    img_data = pix.tobytes('png')
                    img_base64 = base64.b64encode(img_data).decode()
                    
                    if page_num == 0:
                        # First slide: extract speaker info + visual description
                        prompt_text = f"""Analyze this slide (slide {page_num + 1}).

If this is a title slide, extract speaker information:
Expected speaker: {coda_speaker}
- Extract speaker name, compare using rules: "exact"|"variation"|"different"|"not_found"
- If you can't find 1 clear author, leave author blank
- Extract affiliation and talk title

Also describe any visual elements briefly for accessibility:
- Diagrams, charts, tables, important images

Format as JSON:
{{
  "slide_type": "title|content",
  "speaker_name": "name if title slide, empty otherwise",  
  "speaker_match": "exact|variation|different|not_found if title slide",
  "affiliation": "institution if title slide", 
  "talk_title": "title if title slide",
  "visual_elements": "brief description of key visual elements for alt text"
}}"""
                    else:
                        # Content slides: just visual description
                        prompt_text = f"""Analyze slide {page_num + 1} and describe visual elements briefly for accessibility.
                        
Focus on: diagrams, charts, tables, important images that would need alt text.

Format as JSON:
{{
  "slide_type": "content",
  "visual_elements": "brief description of key visual elements for alt text"  
}}"""
                    
                    response = client.messages.create(
                        model="claude-3-haiku-20240307",
                        max_tokens=300,
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text},
                                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_base64}}
                            ]
                        }]
                    )
                    
                    response_text = response.content[0].text.strip()
                    
                    # Parse JSON response
                    try:
                        analysis = json_repair(response_text, fallback_value={})
                        
                        if analysis:
                            # Handle title slide speaker extraction
                            if page_num == 0 and analysis.get("speaker_name") and not speaker_name_found:
                                speaker_match = analysis.get("speaker_match", "not_found")
                                validation_result = "exact_match" if speaker_match == "exact" else \
                                                  "minor_differences" if speaker_match == "variation" else \
                                                  "major_mismatch" if speaker_match == "different" else "major_mismatch"
                                
                                slide_1_metadata.update({
                                    "slide_speaker": analysis.get("speaker_name", ""),
                                    "slide_affiliation": analysis.get("affiliation", ""),
                                    "slide_title": analysis.get("talk_title", ""),
                                    "validation_result": validation_result,
                                    "validation_method": "haiku_visual_analysis"
                                })
                                logger.info(f"Title slide - Speaker: {analysis.get('speaker_name')} ({speaker_match}), Title: {analysis.get('talk_title')}")
                            
                            # Collect visual context for all slides
                            visual_desc = analysis.get("visual_elements", "")
                            if visual_desc:
                                visual_context += f"Slide {page_num + 1}: {visual_desc}\n"
                    except Exception as je:
                        logger.warning(f"JSON parsing failed for slide {page_num + 1}: {je}")
                        # Fallback: use raw response as visual context
                        visual_context += f"Slide {page_num + 1}: {response_text[:100]}\n"
                
            except Exception as e:
                logger.warning(f"Visual analysis failed: {e}")
        
        logger.info(f"Processing complete: analyzed {slides_to_analyze if 'slides_to_analyze' in locals() else 0} slides")
        
        # Load prompt from docs/clean_slides.md
        docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        prompt_path = docs_dir / "clean_slides.md"
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"clean_slides.md not found at {prompt_path}")
        
        prompt_template = prompt_path.read_text()
        
        # Use string replacement to avoid conflicts with JSON braces in template  
        slides_prompt = prompt_template.replace("{speaker}", f"{speaker_name} ({affiliation})")
        slides_prompt = slides_prompt.replace("{slides_md_baseline}", slides_md_baseline)
        slides_prompt = slides_prompt.replace("{qr_codes}", "None detected")
        slides_prompt = slides_prompt.replace("{visual_elements}", visual_context if visual_context else "None processed")
        slides_prompt = slides_prompt.replace("{pdf_path}", pdf_path)
        slides_prompt = slides_prompt.replace("{coda_speaker}", coda_speaker)
        slides_prompt = slides_prompt.replace("{coda_affiliation}", coda_affiliation)
        slides_prompt = slides_prompt.replace("{coda_title}", coda_title)
        
        # Use LLM to process slides
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY required for slide processing")
        
        client = Anthropic(api_key=api_key)
        
        # Call LLM with Sonnet (better for complex JSON output than Haiku)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",  # Use Sonnet for better JSON reliability
                    max_tokens=8000,
                    messages=[{
                        "role": "user",
                        "content": slides_prompt
                    }]
                )
                break  # Success, exit retry loop
            except Exception as e:
                logger.warning(f"API call attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt == max_retries - 1:  # Last attempt
                    logger.error(f"All {max_retries} API attempts failed for {speaker_name}")
                    # Return fallback result instead of raising
                    fallback_result = {
                        "success": False,
                        "error": f"API error after {max_retries} attempts: {str(e)}",
                        "cleaned_slides": slides_md_baseline[:2000],
                        "slide_structure": {"title": "API Error", "main_sections": [], "slide_count": 0},
                        "speaker_validation": {},
                        "resources_found": [],
                        "technical_terms": [],
                        "qr_codes": qr_codes or [],
                        "visual_elements": []
                    }
                    return fallback_result
                import time
                time.sleep(2 ** attempt)  # Exponential backoff
        
        result_text = response.content[0].text
        logger.info(f"LLM slide processing completed: {len(result_text)} characters")
        
        # Process plain text response (markdown directly)
        cleaned_slides = result_text.strip()
        
        # Basic validation - ensure we got reasonable content  
        if len(cleaned_slides) < len(slides_md_baseline) * 0.3:
            logger.warning(f"LLM response seems too short, using baseline")
            cleaned_slides = slides_md_baseline[:2000]
        
        # Create result with plain text markdown
        result = {
            "success": True,
            "cleaned_slides": cleaned_slides,
            "speaker_validation": {}  # Will be populated from visual analysis
        }
        
        # Add metadata from visual analysis if available
        if slide_1_metadata:
            result["speaker_validation"] = {
                "slide_speaker": slide_1_metadata.get("slide_speaker", ""),
                "slide_affiliation": slide_1_metadata.get("slide_affiliation", ""),
                "slide_title": slide_1_metadata.get("slide_title", ""),
                "validation_result": slide_1_metadata.get("validation_result", ""),
                "validation_notes": f"Extracted via {slide_1_metadata.get('validation_method', 'analysis')}"
            }
        
        result["slide_1_metadata"] = slide_1_metadata
        
        # Write cleaned slides to file for easy inspection
        try:
            output_base = Path(__file__).parent.parent.parent.parent / "output" 
            speaker_output_dir = output_base / table_id / speaker_name.replace(" ", "_")
            speaker_output_dir.mkdir(parents=True, exist_ok=True)
            
            slides_file = speaker_output_dir / f"{speaker_name.replace(' ', '_')}_slides_cleaned.md"
            slides_file.write_text(cleaned_slides, encoding='utf-8')
            logger.info(f"Cleaned slides saved to: {slides_file}")
        except Exception as e:
            logger.warning(f"Failed to save slides file: {e}")
            
        logger.info(f"Successfully processed slides for {speaker_name}")
        
        doc.close()  # Close document at the very end
        return result
            
    except Exception as e:
        logger.error(f"Error processing slides for {speaker_name}: {e}", exc_info=True)
        try:
            doc.close()
        except:
            pass
        return {
            "success": False,
            "error": str(e),
            "cleaned_slides": "",
            "speaker_validation": {}
        }