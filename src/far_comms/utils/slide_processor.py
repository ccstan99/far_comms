#!/usr/bin/env python

import asyncio
import base64
import json 
import logging
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from far_comms.utils.json_repair import json_repair

logger = logging.getLogger(__name__)


def smart_title_case(title: str) -> str:
    """Convert to title case while preserving acronyms like LLMs, AI, ML, etc."""
    if not title:
        return title
    
    # Common acronyms that should stay uppercase
    acronyms = {'AI', 'ML', 'LLM', 'LLMS', 'NLP', 'GPT', 'API', 'URL', 'HTTP', 'HTTPS', 'PDF', 'JSON', 'XML', 'SQL', 'GPU', 'CPU', 'RAM', 'SSD', 'HDD', 'USB', 'WiFi', 'IoT', 'VR', 'AR', 'UI', 'UX', 'CEO', 'CTO', 'PhD', 'MSc', 'BSc'}
    
    # First apply standard title case
    title_cased = title.title()
    
    # Then fix known acronyms back to uppercase
    for acronym in acronyms:
        # Replace title-cased version with uppercase version
        title_cased = re.sub(r'\b' + re.escape(acronym.capitalize()) + r'\b', acronym, title_cased)
        # Also handle plural forms
        if acronym.endswith('S'):
            singular = acronym[:-1]
            title_cased = re.sub(r'\b' + re.escape(singular.capitalize()) + r's\b', acronym, title_cased)
    
    return title_cased


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
                "slide_structure": {"title": "", "main_sections": [], "slide_count": 0},
                "speaker_validation": {},
                "resources_found": [],
                "technical_terms": []
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
        
        # Extract QR codes from first and last slides using pyzbar
        qr_codes = []
        doc = pymupdf.open(pdf_path)
        for page_num in range(len(doc)):  # All pages
            page = doc[page_num]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            img_data = pix.tobytes('png')
            
            # Convert to PIL Image for pyzbar
            from PIL import Image
            from io import BytesIO
            try:
                from pyzbar import pyzbar
                img = Image.open(BytesIO(img_data))
                detected_qrs = pyzbar.decode(img)
                for qr in detected_qrs:
                    qr_url = qr.data.decode('utf-8')
                    qr_codes.append({
                        "url": qr_url,
                        "page": page_num + 1,
                        "location": f"Page {page_num + 1} ({'first' if page_num == 0 else 'last'} slide)"
                    })
                    logger.info(f"Found QR code: {qr_url} on page {page_num + 1}")
            except ImportError:
                logger.warning("pyzbar not available for QR code detection")
            except Exception as e:
                logger.warning(f"QR code detection failed on page {page_num + 1}: {e}")
        
        # Generate full slide images (much more useful than pymupdf4llm fragments)
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
                slide_filename = f"slide_{page_num + 1:02d}.png"
                slide_path = images_dir / slide_filename  # Save in images/ subdirectory
                pix.save(str(slide_path))
            logger.info(f"Generated {len(doc)} full slide images in images/ directory")
        except Exception as e:
            logger.warning(f"Failed to generate full slide images: {e}")
        
        # Keep document open for potential slide 1 analysis
        
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
                                {"type": "text", "text": f"Analyze this title slide. Extract: 1) Presentation title 2) Speaker name(s) 3) Affiliation(s). Return JSON format: {{\"speaker_name\": \"exact name as written\", \"affiliation\": \"institution\", \"talk_title\": \"presentation title\"}}. Expected speaker: {speaker_name}"},
                                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_base64_1}}
                            ]
                        }]
                    )
                    
                    metadata_text = response.content[0].text.strip()
                    # Try to parse JSON response
                    slide_1_metadata = json_repair(metadata_text, fallback_value={})
                    if slide_1_metadata:
                        logger.info(f"Extracted slide 1 metadata: {slide_1_metadata}")
                    else:
                        logger.warning(f"Could not parse slide 1 metadata JSON: {metadata_text}")
                        
            except Exception as e:
                logger.warning(f"Slide 1 metadata extraction failed: {e}")
        
        # Generate basic image descriptions using Haiku on full slide images (better than fragments)
        visual_elements = []
        saved_images = []
        
        # Find full slide images we just generated (now in images/ directory)
        slide_files = list(images_dir.glob("slide_*.png"))  
        if slide_files:
            logger.info(f"Found {len(slide_files)} full slide images for analysis")
            
            # Also keep pymupdf4llm fragments for fallback
            fragment_files = [f for f in images_dir.glob("*.png") if not f.name.startswith("slide_")]
            if fragment_files:
                logger.info(f"Found {len(fragment_files)} pymupdf4llm image fragments as fallback")
            
            # Analyze ALL slides with Haiku (cheap/fast, much better than fragments)
            if client:
                    # Analyze every slide - with Haiku it's fast and cheap
                    for slide_num, img_file in enumerate(slide_files, 1):
                        is_first_slide = slide_num == 1
                        try:
                            with open(img_file, 'rb') as f:
                                img_data = f.read()
                            img_base64 = base64.b64encode(img_data).decode()
                            
                            # Different prompts for first slide vs others
                            if is_first_slide:
                                prompt_text = """Analyze this title slide and extract speaker information.

Extract the following information exactly as it appears:
- Speaker name (full name as written)
- Affiliation/Institution 
- Talk title

Format response as JSON:
{
  "speaker_name": "exact name as written on slide",
  "affiliation": "institution/affiliation as written", 
  "talk_title": "presentation title as written",
  "slide_type": "title"
}"""
                            else:
                                prompt_text = """Analyze this slide and provide a brief description.

Format response as JSON:
{
  "visual_elements": [{"type": "chart|diagram|table|image", "description": "brief description"}],
  "description": "brief description of slide content",
  "slide_type": "content"
}"""

                            response = client.messages.create(
                                model="claude-3-haiku-20240307",  # 20x cheaper than Sonnet
                                max_tokens=500,
                                messages=[{
                                    "role": "user", 
                                    "content": [
                                        {"type": "text", "text": prompt_text},
                                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_base64}}
                                    ]
                                }]
                            )
                            
                            response_text = response.content[0].text.strip()
                            
                            # Parse JSON response with better error handling
                            try:
                                # Extract JSON from response using json_repair for robustness
                                analysis = json_repair(response_text, max_attempts=2, fallback_value={})
                                
                                if analysis and isinstance(analysis, dict):
                                    # Handle title slide differently
                                    if is_first_slide:
                                        slide_analysis = {
                                            "type": "title_slide_analysis",
                                            "description": f"Title slide: {analysis.get('speaker_name', 'Unknown')} - {analysis.get('talk_title', 'Unknown')}",
                                            "file": img_file.name,
                                            "speaker_name": analysis.get("speaker_name", ""),
                                            "affiliation": analysis.get("affiliation", ""),
                                            "talk_title": analysis.get("talk_title", ""),
                                            "slide_qr_codes": analysis.get("qr_codes", []),
                                            "description": f"Title slide: {analysis.get('speaker_name', '')}",
                                            "slide_type": "title"
                                        }
                                        
                                        # Update slide_1_metadata if we found speaker info
                                        if analysis.get("speaker_name"):
                                            slide_1_metadata.update({
                                                "slide_speaker": analysis.get("speaker_name", ""),
                                                "slide_affiliation": analysis.get("affiliation", ""),
                                                "slide_title": analysis.get("talk_title", ""),
                                                "validation_method": "haiku_visual_analysis"
                                            })
                                            logger.info(f"Extracted from title slide - Speaker: {analysis.get('speaker_name')}, Affiliation: {analysis.get('affiliation')}")
                                    else:
                                        # Content slide analysis
                                        slide_analysis = {
                                            "type": "full_slide_analysis", 
                                            "description": analysis.get("description", f"Slide {slide_num}"),
                                            "file": img_file.name,
                                            "slide_number": slide_num,
                                            "visual_elements": analysis.get("visual_elements", []),
                                            "slide_type": "content"
                                        }
                                        
                                        # Save all slides for potential social media use
                                        saved_images.append(str(img_file))
                                    
                                    visual_elements.append(slide_analysis)
                                    
                                    # QR codes only detected via pyzbar (actual image analysis)
                                    
                                else:
                                    # Empty or invalid analysis result
                                    logger.warning(f"No valid analysis for slide {slide_num} ({img_file.name})")
                                    visual_elements.append({
                                        "type": "image_analysis",
                                        "description": response_text[:200] + ("..." if len(response_text) > 200 else ""),
                                        "file": img_file.name,
                                        "slide_number": slide_num
                                    })
                            except Exception as parse_error:
                                logger.warning(f"JSON parsing failed for slide {slide_num} ({img_file.name}): {parse_error}")
                                visual_elements.append({
                                    "type": "image_analysis", 
                                    "description": response_text[:200] + ("..." if len(response_text) > 200 else ""),
                                    "file": img_file.name,
                                    "slide_number": slide_num
                                })
                            
                        except Exception as e:
                            logger.warning(f"Haiku analysis failed for {img_file.name}: {e}")
                            # Fallback to basic file info
                            visual_elements.append({
                                "type": "image",
                                "description": f"Full slide image: {img_file.name}",
                                "file": img_file.name
                            })
        
        logger.info(f"Processing complete: {len(qr_codes)} QR codes, {len(visual_elements)} visual elements, {len(saved_images)} images")
        
        # Load prompt from docs/clean_slides.md
        docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        prompt_path = docs_dir / "clean_slides.md"
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"clean_slides.md not found at {prompt_path}")
        
        prompt_template = prompt_path.read_text()
        
        # Use string replacement to avoid conflicts with JSON braces in template  
        slides_prompt = prompt_template.replace("{speaker}", f"{speaker_name} ({affiliation})")
        slides_prompt = slides_prompt.replace("{slides_md_baseline}", slides_md_baseline)
        slides_prompt = slides_prompt.replace("{qr_codes}", json.dumps(qr_codes, indent=2) if qr_codes else "None found")
        slides_prompt = slides_prompt.replace("{visual_elements}", json.dumps(visual_elements, indent=2) if visual_elements else "None processed")
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
                        "visual_elements": visual_elements or []
                    }
                    return fallback_result
                import time
                time.sleep(2 ** attempt)  # Exponential backoff
        
        result_text = response.content[0].text
        logger.info(f"LLM slide processing completed: {len(result_text)} characters")
        
        # Parse JSON response using json_repair utility
        fallback_result = {
            "success": False,
            "error": "JSON parsing failed",
            "cleaned_slides": slides_md_baseline[:2000],  # Truncated markdown baseline as fallback
            "slide_structure": {"title": "Processing failed", "main_sections": [], "slide_count": 0},
            "speaker_validation": {},
            "resources_found": [],
            "technical_terms": [],
            "processing_notes": f"LLM processing failed, using markdown baseline"
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
            result["success"] = True
            result["pdf_path"] = pdf_path
            result["qr_codes"] = qr_codes
            result["visual_elements"] = visual_elements  
            result["saved_images"] = saved_images
            result["slide_1_metadata"] = slide_1_metadata
            
            # Copy all slides to social media directory for analysis step to evaluate
            try:
                social_media_slides = []
                
                # Get all slides (analysis step will do better ranking)
                all_slides = [
                    ve for ve in visual_elements 
                    if ve.get("type") == "full_slide_analysis"
                ]
                
                if all_slides:
                    logger.info(f"Found {len(all_slides)} total slides - all available for analysis step")
                    
                    # Just record all slides as available for social media evaluation
                    for slide in all_slides:
                        social_media_slides.append({
                            "file": slide["file"],
                            "slide_number": slide.get("slide_number", 0),
                            "description": slide.get("description", "")
                        })
                
                result["social_media_slides"] = [s["file"] for s in social_media_slides]
                result["total_slides"] = len(all_slides)
                logger.info(f"All {len(all_slides)} slides available for analysis step ranking")
                
            except Exception as e:
                logger.warning(f"Failed to create social media slides: {e}")
                result["social_media_slides"] = []
                result["total_slides"] = 0
            
            result["processing_stats"] = {
                "markdown_baseline_chars": len(slides_md_baseline),
                "qr_codes_found": len(qr_codes),
                "visual_elements": len(visual_elements),
                "images_saved": len(saved_images)
            }
            
            # Save debug JSON file for debugging purposes
            try:
                from datetime import datetime
                debug_json_path = speaker_output_dir / f"{speaker_name.replace(' ', '_')}_slides.json"
                debug_data = {
                    "timestamp": datetime.now().isoformat(),
                    "input": {
                        "speaker_name": speaker_name,
                        "pdf_path": pdf_path,
                        "table_id": table_id,
                        "coda_speaker": coda_speaker,
                        "coda_affiliation": coda_affiliation,
                        "coda_title": coda_title
                    },
                    "extraction_results": {
                        "markdown_baseline_length": len(slides_md_baseline),
                        "qr_codes": qr_codes,
                        "visual_elements": visual_elements,
                        "slide_1_metadata": slide_1_metadata,
                        "saved_images": saved_images
                    },
                    "llm_processing": {
                        "raw_response": result_text,
                        "parsed_result": result,
                        "processing_stats": result["processing_stats"]
                    }
                }
                
                with open(debug_json_path, 'w', encoding='utf-8') as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
                
                # Save pymupdf4llm raw output for reference
                pymupdf4llm_path = speaker_output_dir / f"{speaker_name.replace(' ', '_')}_pymupdf4llm.md"
                with open(pymupdf4llm_path, 'w', encoding='utf-8') as f:
                    f.write(slides_md_baseline)
                
                # Save cleaned slides markdown (what goes to Coda)
                cleaned_slides_path = speaker_output_dir / f"{speaker_name.replace(' ', '_')}_slides.md"
                with open(cleaned_slides_path, 'w', encoding='utf-8') as f:
                    f.write(result.get("cleaned_slides", ""))
                
                logger.info(f"Debug files saved: {debug_json_path.name}, {pymupdf4llm_path.name}, {cleaned_slides_path.name}")
                
            except Exception as e:
                logger.warning(f"Failed to save debug JSON: {e}")
                
            logger.info(f"Successfully processed slides for {speaker_name}")
        else:
            logger.error(f"Failed to parse slide processing JSON after repair attempts")
        
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
            "slide_structure": {"title": "", "main_sections": [], "slide_count": 0},
            "speaker_validation": {},
            "resources_found": [],
            "technical_terms": [],
            "processing_notes": f"Slide processing failed: {e}"
        }