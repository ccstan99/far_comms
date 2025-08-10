#!/usr/bin/env python

import logging
import json
import base64
import os
from pathlib import Path
from typing import Dict, List, Any
from crewai import LLM
from far_comms.utils.project_paths import get_output_dir

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import cv2
    import numpy as np
    from pyzbar import pyzbar
    QR_DETECTION_AVAILABLE = True
except ImportError:
    QR_DETECTION_AVAILABLE = False

logger = logging.getLogger(__name__)


def analyze_images_with_claude(images_data: List[Dict]) -> List[Dict]:
    """Get image captions from Claude"""
    client = anthropic.Anthropic()
    results = []
    
    for img_data in images_data[:5]:  # Max 5 slides
        base64_data = img_data.get('image_base64', '')
        if not base64_data:
            continue
            
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this slide in 1-2 sentences."},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64_data}}
                ]
            }]
        )
        
        results.append({
            'page': img_data.get('page'),
            'caption': response.content[0].text.strip()
        })
        
    return results


def detect_qr_codes_in_images(images_data: List[Dict]) -> List[Dict]:
    """
    Detect QR codes in slide images and extract their URLs
    
    Args:
        images_data: List of image dictionaries with base64 data
    
    Returns:
        List of QR code detection results with URLs and slide numbers
    """
    if not QR_DETECTION_AVAILABLE:
        logger.warning("QR code detection unavailable - install: pip install opencv-python pyzbar")
        return []
    
    qr_results = []
    
    for img_data in images_data:
        try:
            page_num = img_data.get('page', 0)
            base64_data = img_data.get('image_base64', '')
            
            if not base64_data:
                continue
                
            # Decode base64 image
            img_bytes = base64.b64decode(base64_data)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                continue
            
            # Convert to grayscale for better QR detection
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Detect QR codes
            qr_codes = pyzbar.decode(gray)
            
            for qr in qr_codes:
                try:
                    # Decode QR data
                    qr_data = qr.data.decode('utf-8')
                    
                    # Check if it's a URL
                    if qr_data.startswith(('http://', 'https://', 'www.')):
                        # Clean URL
                        clean_url = qr_data.strip()
                        if not clean_url.startswith('http'):
                            clean_url = 'https://' + clean_url
                        
                        qr_results.append({
                            'page': page_num,
                            'url': clean_url,
                            'raw_data': qr_data,
                            'type': 'url'
                        })
                        
                        logger.info(f"Found QR code URL on slide {page_num}: {clean_url}")
                    
                    else:
                        # Non-URL QR code (text, contact, etc.)
                        qr_results.append({
                            'page': page_num,
                            'data': qr_data,
                            'type': 'text'
                        })
                        
                        logger.info(f"Found QR code text on slide {page_num}: {qr_data[:50]}...")
                        
                except UnicodeDecodeError:
                    logger.warning(f"Could not decode QR code on slide {page_num}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error detecting QR codes on slide {img_data.get('page', '?')}: {e}")
            continue
    
    return qr_results


def analyze_slide_images(images_data: List[Dict], file_name: str = "", speaker_name: str = "") -> Dict[str, Any]:
    """
    Analyze slide images using multimodal LLM to extract visual insights
    
    Args:
        images_data: List of image dictionaries with base64 data
        file_name: Name of the original file for context
    
    Returns:
        Dictionary containing visual analysis results
    """
    if not images_data:
        return {
            "success": False,
            "error": "No images provided for analysis",
            "visual_insights": "",
            "slide_quality": "unknown"
        }
    
    try:
        # Use Claude Haiku for cost-effective visual analysis
        llm = LLM(
            model="anthropic/claude-haiku-3-20240307",
            max_retries=2
        )
        
        # Prepare the analysis prompt
        slide_count = len(images_data)
        analysis_prompt = f"""Analyze these {slide_count} presentation slides from "{file_name}". Focus on:

1. **Visual Quality Assessment:**
   - Professional design and layout
   - Readability and clarity
   - Chart/diagram quality

2. **Content Type Analysis:**
   - Charts, graphs, diagrams present
   - Text density vs. visual elements
   - Key visual insights or data

3. **Social Media Suitability:**
   - Would these work well as LinkedIn PDF posts?
   - Are there standout images good for Twitter/X?
   - Overall visual appeal for social sharing

4. **Media Recommendation:**
   - Best format: "slides_pdf", "key_images", "text_only"
   - Reasoning for recommendation

Provide analysis in this JSON format:
```json
{{
  "visual_quality": "excellent|good|fair|poor",
  "content_types": ["charts", "diagrams", "text-heavy", "images"],
  "key_insights": ["insight 1", "insight 2", "insight 3"],
  "linkedin_suitable": true/false,
  "twitter_images": 2,
  "recommended_media": "slides_pdf|key_images|text_only",
  "reasoning": "explanation of recommendation",
  "standout_slides": [1, 3, 5]
}}
```

Images to analyze:"""

        # Add images to the prompt (Claude can handle multiple images)
        image_messages = []
        for i, img_data in enumerate(images_data[:10]):  # Limit to 10 slides max
            image_messages.append(f"Slide {img_data.get('page', i+1)}")
        
        # Create the full prompt
        full_prompt = analysis_prompt + f"\n\nAnalyzing {len(image_messages)} slides..."
        
        # Get captions from Claude
        claude_analysis = analyze_images_with_claude(images_data)
        qr_codes = detect_qr_codes_in_images(images_data)
        
        # Format captions
        captions = [f"Slide {a['page']}: {a['caption']}" for a in claude_analysis]
        
        # Save all analyzed slides (since we're analyzing max 5 anyway)
        saved_files = []
        if claude_analysis and speaker_name:
            slide_numbers = [a['page'] for a in claude_analysis]
            saved_files = save_shareable_slides(images_data, speaker_name, slide_numbers)
        
        return {
            "success": True,
            "key_insights": captions,
            "saved_slide_files": saved_files,
            "qr_codes": qr_codes
        }
        
    except Exception as e:
        logger.error(f"Error in visual analysis: {e}")
        return {
            "success": False,
            "error": str(e),
            "visual_insights": "",
            "slide_quality": "unknown"
        }


def save_shareable_slides(images_data: List[Dict], speaker_name: str, shareable_slide_numbers: List[int]) -> List[str]:
    """
    Save shareable slide images to disk for social media use
    
    Args:
        images_data: List of image dictionaries with base64 data
        speaker_name: Name of speaker for file naming
        shareable_slide_numbers: Which slide numbers to save (1-indexed)
    
    Returns:
        List of saved file paths
    """
    if not images_data or not speaker_name or not shareable_slide_numbers:
        return []
    
    output_dir = get_output_dir()
    saved_files = []
    
    # Clean speaker name for filename
    clean_speaker = "".join(c for c in speaker_name if c.isalnum() or c in (' ', '-', '_')).strip()
    clean_speaker = clean_speaker.replace(' ', '_').lower()
    
    try:
        for slide_num in shareable_slide_numbers:
            # Find the corresponding image (slide_num is 1-indexed, list is 0-indexed)
            slide_index = slide_num - 1
            if 0 <= slide_index < len(images_data):
                image_data = images_data[slide_index]
                base64_data = image_data.get("image_base64", "")
                
                if base64_data:
                    # Decode base64 image
                    image_bytes = base64.b64decode(base64_data)
                    
                    # Create filename: speaker_name_#.png
                    filename = f"{clean_speaker}_{slide_num}.png"
                    filepath = output_dir / filename
                    
                    # Save image to disk
                    with open(filepath, 'wb') as f:
                        f.write(image_bytes)
                    
                    saved_files.append(str(filepath))
                    logger.info(f"Saved shareable slide: {filename}")
                    
    except Exception as e:
        logger.error(f"Error saving slide images: {e}")
    
    return saved_files


def format_visual_insights(analysis_result: Dict[str, Any]) -> str:
    """
    Format visual analysis results into readable text for Coda storage
    
    Args:
        analysis_result: Result from analyze_slide_images()
    
    Returns:
        Formatted string with visual insights
    """
    if not analysis_result.get("success"):
        return f"Visual analysis failed: {analysis_result.get('error', 'Unknown error')}"
    
    insights = []
    
    # Quality assessment
    quality = analysis_result.get("visual_quality", "unknown")
    insights.append(f"**Visual Quality:** {quality.title()}")
    
    # Key insights
    key_insights = analysis_result.get("key_insights", [])
    if key_insights:
        insights.append("**Key Visual Elements:**")
        for insight in key_insights:
            insights.append(f"• {insight}")
    
    # Media recommendation
    media_rec = analysis_result.get("recommended_media", "unknown")
    reasoning = analysis_result.get("reasoning", "")
    insights.append(f"**Recommended Media Format:** {media_rec}")
    if reasoning:
        insights.append(f"**Reasoning:** {reasoning}")
    
    # Platform suitability
    linkedin_ok = analysis_result.get("linkedin_suitable", False)
    twitter_imgs = analysis_result.get("twitter_images", 0)
    insights.append(f"**LinkedIn PDF Suitable:** {'Yes' if linkedin_ok else 'No'}")
    insights.append(f"**Twitter Images Available:** {twitter_imgs}")
    
    # Standout slides
    standout = analysis_result.get("standout_slides", [])
    if standout:
        insights.append(f"**Best Slides for Social:** {', '.join(map(str, standout))}")
    
    # Saved files
    saved_files = analysis_result.get("saved_slide_files", [])
    if saved_files:
        filenames = [os.path.basename(f) for f in saved_files]
        insights.append(f"**Saved Images:** {', '.join(filenames)}")
    
    return "\n".join(insights)


def get_media_recommendation(analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract media recommendation data for future media evaluation agent
    
    Args:
        analysis_result: Result from analyze_slide_images()
    
    Returns:
        Structured media recommendation
    """
    if not analysis_result.get("success"):
        return {
            "primary_media": "text_only",
            "reasoning": f"Analysis failed: {analysis_result.get('error', 'Unknown')}",
            "confidence": "low",
            "platform_specific": {
                "linkedin": "text_only",
                "twitter": "text_only"
            }
        }
    
    primary = analysis_result.get("recommended_media", "text_only")
    linkedin_suitable = analysis_result.get("linkedin_suitable", False)
    twitter_images = analysis_result.get("twitter_images", 0)
    
    return {
        "primary_media": primary,
        "reasoning": analysis_result.get("reasoning", ""),
        "confidence": "medium",  # Will improve with real visual analysis
        "visual_quality": analysis_result.get("visual_quality", "unknown"),
        "platform_specific": {
            "linkedin": "slides_pdf" if linkedin_suitable else "text_only",
            "twitter": "key_images" if twitter_images > 0 else "text_only"
        },
        "standout_slides": analysis_result.get("standout_slides", []),
        "slide_count": analysis_result.get("slide_count", 0)
    }