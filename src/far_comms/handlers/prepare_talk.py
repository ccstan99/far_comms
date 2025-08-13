#!/usr/bin/env python

import asyncio
import base64
import json 
import logging
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from far_comms.utils.coda_client import CodaClient
from far_comms.models.requests import CodaIds
from far_comms.utils.json_repair import json_repair
# Removed LangChain PromptTemplate due to conflicts with JSON braces in templates

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


def get_input(raw_data: dict) -> dict:
    """Parse raw Coda data for prepare_talk - needs speaker name and YouTube URL"""
    return {
        "speaker": raw_data.get("Speaker", ""),
        "yt_url": raw_data.get("YT url", "")
    }


def display_input(function_data: dict) -> dict:
    """Format function input for webhook display - no long fields to truncate"""
    return function_data


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
        
        # Extract markdown with images using pymupdf4llm
        slides_md_baseline = pymupdf4llm.to_markdown(
            pdf_path,
            write_images=True,
            image_path=str(images_dir),
            ignore_images=False
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
        for page_num in [0, len(doc)-1]:  # First and last page
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
                slide_path = speaker_output_dir / slide_filename
                pix.save(str(slide_path))
            logger.info(f"Generated {len(doc)} full slide images")
        except Exception as e:
            logger.warning(f"Failed to generate full slide images: {e}")
        
        doc.close()  # Close document after using it
        
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
                                {"type": "text", "text": f"Analyze this title slide. Extract: 1) Presentation title 2) Speaker name(s) 3) Affiliation(s). Return JSON format: {{\"title\": \"...\", \"authors\": [\"name1\", \"name2\"], \"affiliations\": [\"aff1\", \"aff2\"]}}. If not visible, use empty string/array. Expected speaker: {speaker_name}"},
                                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_base64_1}}
                            ]
                        }]
                    )
                    
                    metadata_text = response.content[0].text.strip()
                    # Try to parse JSON response
                    try:
                        slide_1_metadata = json.loads(metadata_text)
                        logger.info(f"Extracted slide 1 metadata: {slide_1_metadata}")
                    except:
                        logger.warning(f"Could not parse slide 1 metadata JSON: {metadata_text}")
                        
            except Exception as e:
                logger.warning(f"Slide 1 metadata extraction failed: {e}")
        
        doc.close()
        
        # Generate basic image descriptions using Haiku on full slide images (better than fragments)
        visual_elements = []
        saved_images = []
        
        # Find full slide images we just generated
        slide_files = list(speaker_output_dir.glob("slide_*.png"))
        if slide_files:
            logger.info(f"Found {len(slide_files)} full slide images for analysis")
            
            # Also keep pymupdf4llm fragments for fallback
            image_files = list(images_dir.glob("*.png"))
            if image_files:
                logger.info(f"Found {len(image_files)} pymupdf4llm image fragments as fallback")
            
            # Analyze key slides with Haiku for descriptions (prioritize full slides over fragments)
            if client:
                    # Analyze a few representative full slides (title, middle, end)
                    key_slides = []
                    if len(slide_files) >= 3:
                        key_slides = [slide_files[0], slide_files[len(slide_files)//2], slide_files[-1]]
                    else:
                        key_slides = slide_files[:3]
                    
                    for img_file in key_slides:  # Analyze key full slides
                        try:
                            with open(img_file, 'rb') as f:
                                img_data = f.read()
                            img_base64 = base64.b64encode(img_data).decode()
                            
                            response = client.messages.create(
                                model="claude-3-haiku-20240307",  # 20x cheaper than Sonnet
                                max_tokens=500,
                                messages=[{
                                    "role": "user", 
                                    "content": [
                                        {"type": "text", "text": """Analyze this full slide image and determine if it's "image-rich" for social media.

STRICT CRITERIA FOR "is_image_rich": Only mark as "true" if slide contains:
✅ Complex workflow diagrams with arrows/boxes/connections (like process flows)
✅ Data tables with numbers/results/metrics (not just text lists)  
✅ Charts/graphs with data visualization or performance comparisons
✅ Technical system diagrams with visual components
✅ Comparison tables showing quantitative results

❌ DO NOT mark as image-rich:
❌ Title slides with just names/affiliations/logos
❌ Bullet point lists (even with fancy formatting)
❌ Text-heavy slides with minimal visuals
❌ Simple layouts that are mostly text

Format response as JSON:
{
  "visual_elements": [{"type": "chart|diagram|table|image", "description": "brief description"}],
  "is_image_rich": "true|false - ONLY true for slides with quantitative data, complex diagrams, or rich visual content",
  "social_media_potential": "brief explanation of visual complexity and data value"
}"""},
                                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_base64}}
                                    ]
                                }]
                            )
                            
                            response_text = response.content[0].text.strip()
                            
                            # Parse JSON response
                            try:
                                import json
                                # Extract JSON from response
                                if "{" in response_text and "}" in response_text:
                                    json_start = response_text.find("{")
                                    json_end = response_text.rfind("}") + 1
                                    json_str = response_text[json_start:json_end]
                                    analysis = json.loads(json_str)
                                    
                                    # Add slide analysis
                                    slide_analysis = {
                                        "type": "full_slide_analysis",
                                        "description": f"Visual elements: {len(analysis.get('visual_elements', []))}, Image-rich: {analysis.get('is_image_rich', 'false')}",
                                        "file": img_file.name,
                                        "is_image_rich": analysis.get("is_image_rich", "false").lower() == "true",
                                        "social_media_potential": analysis.get("social_media_potential", ""),
                                        "visual_elements_detail": analysis.get("visual_elements", [])
                                    }
                                    visual_elements.append(slide_analysis)
                                    
                                    # Save image-rich slides for social media use
                                    if slide_analysis["is_image_rich"]:
                                        saved_images.append(str(img_file))
                                        logger.info(f"Identified image-rich slide: {img_file.name}")
                                    
                                else:
                                    # Fallback if no JSON
                                    visual_elements.append({
                                        "type": "image_analysis",
                                        "description": response_text,
                                        "file": img_file.name
                                    })
                            except json.JSONDecodeError as je:
                                logger.warning(f"JSON parsing failed for {img_file.name}: {je}")
                                visual_elements.append({
                                    "type": "image_analysis", 
                                    "description": response_text,
                                    "file": img_file.name
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
        response = client.messages.create(
            model="claude-sonnet-4-20250514",  # Use Sonnet for better JSON reliability
            max_tokens=8000,
            messages=[{
                "role": "user",
                "content": slides_prompt
            }]
        )
        
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
            
            # Create simplified copies prioritizing image-rich slides
            try:
                simplified_copies = []
                image_rich_count = 0
                
                for i, visual_element in enumerate(visual_elements, 1):
                    if "file" in visual_element and visual_element.get("type") == "full_slide_analysis":
                        # Copy full slide images (not fragments)
                        original_filename = visual_element["file"] 
                        original_path = speaker_output_dir / original_filename
                        
                        if original_path.exists():
                            # Prioritize image-rich slides in naming
                            if visual_element.get("is_image_rich", False):
                                image_rich_count += 1
                                simplified_name = f"{speaker_name.replace(' ', '_')}_rich_{image_rich_count}.png"
                                logger.info(f"Created image-rich slide copy: {simplified_name}")
                            else:
                                simplified_name = f"{speaker_name.replace(' ', '_')}_slide_{i}.png"
                            
                            simplified_path = speaker_output_dir / simplified_name
                            
                            import shutil
                            shutil.copy2(original_path, simplified_path)
                            simplified_copies.append(str(simplified_path))
                
                result["simplified_image_copies"] = simplified_copies
                result["image_rich_slides"] = image_rich_count
                logger.info(f"Created {len(simplified_copies)} simplified copies ({image_rich_count} image-rich for social media)")
                
            except Exception as e:
                logger.warning(f"Failed to create simplified image copies: {e}")
                result["simplified_image_copies"] = []
            
            result["processing_stats"] = {
                "markdown_baseline_chars": len(slides_md_baseline),
                "qr_codes_found": len(qr_codes),
                "visual_elements": len(visual_elements),
                "images_saved": len(saved_images)
            }
            
            # Save debug JSON file for debugging purposes
            try:
                from datetime import datetime
                debug_json_path = speaker_output_dir / f"{speaker_name.replace(' ', '_')}_slides_debug.json"
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
        
        return result
            
    except Exception as e:
        logger.error(f"Error processing slides for {speaker_name}: {e}", exc_info=True)
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
        output_dir = Path(__file__).parent.parent.parent / "output"
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


async def prepare_talk(function_data: dict, coda_ids: CodaIds) -> dict:
    """
    Simplified prepare_talk handler that calls two independent functions.
    Maintains current functionality and quality without CrewAI.
    
    Returns:
        dict: {"status": "success|skipped|failed", "message": "details", "speaker": "name"}
    """
    try:
        logger.info(f"Starting simplified prepare_talk for row {coda_ids.row_id}")
        
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
        
        # Check existing content to determine what needs processing
        try:
            row_data_str = coda_client.get_row(coda_ids.doc_id, coda_ids.table_id, coda_ids.row_id)
            row_data = json.loads(row_data_str)
            row_values = row_data.get("data", {})
            
            # Check what content already exists
            existing_slides = row_values.get("Slides", "")
            existing_transcript = row_values.get("Transcript", "")
            
            slides_exist = existing_slides and existing_slides.strip()
            transcript_exists = existing_transcript and existing_transcript.strip()
            
            # If both exist, skip entirely
            if slides_exist and transcript_exists:
                logger.info(f"Skipping {speaker_name} - both Slides and Transcript exist, content is complete")
                return {"status": "skipped", "message": "Both Slides and Transcript exist - content complete", "speaker": speaker_name}
            
            # Log what needs processing
            needs_processing = []
            if not slides_exist:
                needs_processing.append("slides")
            if not transcript_exists:
                needs_processing.append("transcript")
            
            logger.info(f"Processing needed for {speaker_name}: {', '.join(needs_processing)}")
                
        except Exception as e:
            logger.warning(f"Could not check existing content for {speaker_name}: {e}")
            # Continue anyway in case it was just a temporary error - assume both need processing
            row_values = {}
            slides_exist = False
            transcript_exists = False
        
        # Call functions conditionally based on what's missing
        slides_result = {"success": True, "cleaned_slides": "", "speaker_validation": {}}  # Default empty result
        transcript_result = {"success": True, "transcript_formatted": "", "transcript_srt": ""}  # Default empty result
        
        if not slides_exist:
            logger.info("Processing slides...")
            slides_result = process_slides(
                speaker_name,
                affiliation=row_values.get("Affiliation", ""),
                coda_speaker=row_values.get("Speaker", ""), 
                coda_affiliation=row_values.get("Affiliation", ""), 
                coda_title=row_values.get("Title", ""),
                table_id=coda_ids.table_id
            )
            
            # Update Coda immediately after slides processing
            if slides_result.get("success"):
                logger.info("Updating Coda with slides results immediately...")
                slides_updates = {"Slides": slides_result.get("cleaned_slides", "")}
                
                # Handle speaker validation immediately
                speaker_validation = slides_result.get("speaker_validation", {})
                slide_1_metadata = slides_result.get("slide_1_metadata", {})
                
                # Use string search result if available, otherwise use LLM validation
                if slide_1_metadata.get("validation_method") == "string_search":
                    logger.info("Using string search validation result (faster than LLM)")
                    speaker_validation = {
                        "slide_speaker": slide_1_metadata.get("slide_speaker", ""),
                        "slide_affiliation": slide_1_metadata.get("slide_affiliation", ""),
                        "slide_title": slide_1_metadata.get("slide_title", ""),
                        "validation_result": slide_1_metadata.get("validation_result", "exact_match"),
                        "validation_notes": f"Speaker name found via string search in markdown: '{slide_1_metadata.get('slide_speaker', '')}'"
                    }
                
                if speaker_validation:
                    validation_result = speaker_validation.get("validation_result", "")
                    slide_speaker = speaker_validation.get("slide_speaker", "")
                    slide_affiliation = speaker_validation.get("slide_affiliation", "") 
                    slide_title = speaker_validation.get("slide_title", "")
                    
                    # Debug validation comparison
                    logger.info(f"Validation result: {validation_result}")
                    logger.info(f"Slide data: speaker='{slide_speaker}', affiliation='{slide_affiliation}', title='{slide_title}'")
                    coda_affiliation_val = row_values.get("Affiliation", "")
                    coda_title_val = row_values.get("Title", "")
                    logger.info(f"Coda data: speaker='{speaker_name}', affiliation='{coda_affiliation_val}', title='{coda_title_val}'")
                    
                    # Smart title case that preserves acronyms
                    if slide_title:
                        slide_title = smart_title_case(slide_title)
                    
                    # Only show mismatch banner for actual conflicting data, not missing data
                    if validation_result == "major_mismatch" and slide_speaker and slide_speaker.strip():
                        if "Slides" in slides_updates:
                            slides_updates["Slides"] = "[*** BEWARE: MISMATCH BETWEEN SPEAKER & SLIDES ***]\n" + slides_updates["Slides"]
                        logger.warning(f"Major speaker mismatch detected: slide='{slide_speaker}' vs coda='{speaker_name}'")
                    elif validation_result == "major_mismatch":
                        logger.info(f"Speaker info not found in slides (not a mismatch): slide='{slide_speaker}' vs coda='{speaker_name}'")
                    elif validation_result in ["exact_match", "minor_differences"]:
                        prefix = "" if validation_result == "exact_match" else "* "
                        # Only update if slide data is valid and different (never replace good data with placeholders)
                        if slide_speaker and slide_speaker != speaker_name and not is_placeholder_text(slide_speaker):
                            slides_updates["Speaker"] = f"{prefix}{slide_speaker}"
                        original_affiliation = row_values.get("Affiliation", "")
                        if slide_affiliation and slide_affiliation != original_affiliation and not is_placeholder_text(slide_affiliation):
                            slides_updates["Affiliation"] = f"{prefix}{slide_affiliation}"
                        original_title = row_values.get("Title", "")
                        # Only update title if there are meaningful differences beyond case and it's not placeholder text
                        if slide_title and not titles_equivalent(slide_title, original_title) and not is_placeholder_text(slide_title):
                            slides_updates["Title"] = f"{prefix}{slide_title}"
                
                # Update slides in Coda immediately
                updates = [{"row_id": coda_ids.row_id, "updates": slides_updates}]
                result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                logger.info(f"Immediate slides update: {result}")
            else:
                logger.error(f"Slides processing failed: {slides_result.get('error', 'Unknown error')}")
        else:
            logger.info("Skipping slides processing - Slides column already has content")
            
        if not transcript_exists:
            logger.info("Processing transcript...")
            # Use slide context for transcript processing (from existing or newly processed slides)
            if slides_exist:
                slide_context = existing_slides[:2000]  # Use existing slides for context
            else:
                slide_context = slides_result.get("cleaned_slides", "")[:2000]  # Use newly processed slides
            transcript_result = process_transcript(speaker_name, yt_url, slide_context)
            
            # Update Coda immediately after transcript processing
            if transcript_result.get("success"):
                logger.info("Updating Coda with transcript results immediately...")
                formatted_transcript = transcript_result.get("transcript_formatted", "")
                # Post-process: convert double newlines to single newlines
                formatted_transcript = formatted_transcript.replace("\n\n", "\n")
                
                transcript_updates = {"Transcript": formatted_transcript}
                
                # Reconstruct SRT with original timestamps
                original_srt = transcript_result.get("transcript_srt", "")
                if original_srt and formatted_transcript:
                    reconstructed_srt = _reconstruct_srt(original_srt, formatted_transcript)
                    if reconstructed_srt:
                        transcript_updates["SRT"] = reconstructed_srt
                        logger.info(f"Reconstructed SRT with original timestamps")
                    else:
                        logger.warning("SRT reconstruction failed, using original SRT")
                        transcript_updates["SRT"] = original_srt
                elif original_srt:
                    transcript_updates["SRT"] = original_srt
                
                # Update transcript in Coda immediately
                updates = [{"row_id": coda_ids.row_id, "updates": transcript_updates}]
                result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
                logger.info(f"Immediate transcript update: {result}")
            else:
                logger.error(f"Transcript processing failed: {transcript_result.get('error', 'Unknown error')}")
        else:
            logger.info("Skipping transcript processing - Transcript column already has content")
        
        # Check if we have enough content to proceed
        if not slides_result.get("success") and not transcript_result.get("success"):
            error_msg = f"Cannot process {speaker_name} - both slides and transcript processing failed"
            logger.error(error_msg)
            
            # Update Coda with error
            coda_updates = {
                "Webhook status": "Error",
                "Webhook progress": error_msg
            }
            updates = [{"row_id": coda_ids.row_id, "updates": coda_updates}]
            coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
            
            return {"status": "failed", "message": error_msg, "speaker": speaker_name}
        
        # Set final status since immediate updates were done
        status_parts = []
        
        if not slides_exist:
            slides_status = "processed" if slides_result.get("success") else "failed"
            status_parts.append(f"slides {slides_status}")
        else:
            status_parts.append("slides skipped (existing)")
            
        if not transcript_exists:
            transcript_status = "processed" if transcript_result.get("success") else "failed"
            status_parts.append(f"transcript {transcript_status}")
        else:
            status_parts.append("transcript skipped (existing)")
        
        status_msg = f"Processed {speaker_name}: {', '.join(status_parts)}"
        
        # Update final webhook status
        final_updates = {
            "Webhook progress": status_msg,
            "Webhook status": "Done"
        }
        updates = [{"row_id": coda_ids.row_id, "updates": final_updates}]
        result = coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
        logger.info(f"Final status update: {result}")
        
        # Count successful processes
        successful_processes = sum([
            1 for result_obj in [slides_result, transcript_result] 
            if result_obj.get("success")
        ])
        
        if successful_processes > 0:
            return {"status": "success", "message": status_msg, "speaker": speaker_name}
        else:
            return {"status": "failed", "message": "No processing succeeded", "speaker": speaker_name}
            
    except Exception as e:
        logger.error(f"Error in prepare_talk: {e}", exc_info=True)
        
        # Try to update Coda with error status
        try:
            coda_client = CodaClient()
            error_updates = {
                "Webhook status": "Error",
                "Webhook progress": f"Prepare talk failed: {str(e)}"
            }
            updates = [{
                "row_id": coda_ids.row_id,
                "updates": error_updates
            }]
            coda_client.update_rows(coda_ids.doc_id, coda_ids.table_id, updates)
        except Exception as update_error:
            logger.error(f"Failed to update Coda with error status: {update_error}")
        
        return {"status": "failed", "message": f"Prepare talk error: {str(e)}", "speaker": function_data.get("speaker", "")}