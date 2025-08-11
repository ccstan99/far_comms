#!/usr/bin/env python

import logging
import glob
import os
import base64
from langchain_community.document_loaders import AssemblyAIAudioTranscriptLoader, PyPDFLoader
from langchain_community.document_loaders.assemblyai import TranscriptFormat

logger = logging.getLogger(__name__)


def _decode_qr_codes_from_image(img_data: bytes) -> list:
    """
    Decode QR codes from image data using pyzbar.
    
    Args:
        img_data: PNG image bytes
        
    Returns:
        List of QR code URLs found
    """
    try:
        from pyzbar import pyzbar
        from PIL import Image
        import io
        
        # Convert bytes to PIL Image
        image = Image.open(io.BytesIO(img_data))
        
        # Decode QR codes
        qr_codes = []
        decoded_objects = pyzbar.decode(image)
        
        for obj in decoded_objects:
            if obj.type == 'QRCODE':
                qr_data = obj.data.decode('utf-8')
                qr_codes.append(qr_data)
                
        return qr_codes
        
    except ImportError:
        logger.warning("pyzbar not available - cannot decode QR codes")
        return []
    except Exception as e:
        logger.warning(f"QR code decoding failed: {e}")
        return []


def _analyze_pdf_visually(pdf_path: str) -> dict:
    """
    Analyze PDF visually using multimodal LLM to extract QR codes and describe images.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        dict with qr_codes, images, and visual_elements
    """
    try:
        import fitz  # PyMuPDF
        from anthropic import Anthropic
        import os
        
        # Initialize Anthropic client
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            # Try loading from .env file
            try:
                from dotenv import load_dotenv
                load_dotenv()
                api_key = os.getenv("ANTHROPIC_API_KEY")
            except ImportError:
                pass
                
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not found - skipping visual analysis")
            return {"qr_codes": [], "visual_elements": [], "page_analyses": []}
        client = Anthropic(api_key=api_key)
        
        doc = fitz.open(pdf_path)
        results = {
            "qr_codes": [],
            "visual_elements": [],
            "page_analyses": []
        }
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Convert page to image
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
            img_data = pix.tobytes("png")
            img_base64 = base64.b64encode(img_data).decode()
            
            # First try to decode QR codes directly using pyzbar
            qr_urls = _decode_qr_codes_from_image(img_data)
            
            # Analyze with multimodal LLM
            prompt = """Analyze this slide image and extract:
1. QR codes: If you see any QR codes, try to read the URL they contain
2. Visual elements: Describe any charts, diagrams, tables, or images with brief alt text
3. Important text: Any key text that might be missed by OCR

Format your response as JSON:
{
  "qr_codes": [{"url": "detected_url", "location": "description of where on slide"}],
  "visual_elements": [{"type": "chart|diagram|table|image", "description": "brief alt text"}],
  "key_text": ["any important text visible"]
}"""

            try:
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1024,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image", "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": img_base64
                            }}
                        ]
                    }]
                )
                
                # Parse response
                import json
                analysis_text = response.content[0].text
                
                # Extract JSON from response
                if "{" in analysis_text and "}" in analysis_text:
                    json_start = analysis_text.find("{")
                    json_end = analysis_text.rfind("}") + 1
                    json_str = analysis_text[json_start:json_end]
                    
                    analysis = json.loads(json_str)
                    
                    # Add decoded QR codes (real URLs from pyzbar)
                    for qr_url in qr_urls:
                        results["qr_codes"].append({
                            "url": qr_url,
                            "location": f"QR code on page {page_num + 1}",
                            "page": page_num + 1,
                            "source": "pyzbar_decoded"
                        })
                    
                    # Add any QR codes detected by Claude (for location info)
                    for qr in analysis.get("qr_codes", []):
                        if not qr_urls:  # Only add if pyzbar didn't find any
                            qr["page"] = page_num + 1
                            qr["source"] = "claude_detected"
                            results["qr_codes"].append(qr)
                    
                    for element in analysis.get("visual_elements", []):
                        element["page"] = page_num + 1
                        results["visual_elements"].append(element)
                    
                    results["page_analyses"].append({
                        "page": page_num + 1,
                        "analysis": analysis
                    })
                
            except Exception as e:
                logger.warning(f"Failed to analyze page {page_num + 1} of PDF: {e}")
                # Still add QR codes even if visual analysis fails
                for qr_url in qr_urls:
                    results["qr_codes"].append({
                        "url": qr_url,
                        "location": f"QR code on page {page_num + 1}",
                        "page": page_num + 1,
                        "source": "pyzbar_decoded"
                    })
                # Add a note about failed analysis
                results["page_analyses"].append({
                    "page": page_num + 1,
                    "analysis": {"error": f"Visual analysis failed: {str(e)}", "qr_codes": qr_urls}
                })
                continue
        
        doc.close()
        
        logger.info(f"Visual analysis complete: {len(results['qr_codes'])} QR codes, {len(results['visual_elements'])} visual elements found")
        return results
        
    except ImportError:
        logger.warning("PyMuPDF not available - skipping visual analysis")
        return {"qr_codes": [], "visual_elements": [], "page_analyses": []}
    except Exception as e:
        logger.error(f"Error in visual analysis: {e}")
        return {"qr_codes": [], "visual_elements": [], "page_analyses": []}


def find_matching_pdf(speaker_name: str) -> str:
    """Find PDF file that best matches speaker name"""
    pdf_files = glob.glob("data/slides/*.pdf")
    if not pdf_files:
        return None
        
    # Split speaker name into individual words
    speaker_words = [word.lower() for word in speaker_name.replace("-", " ").replace("_", " ").split() if len(word) > 2]
    
    best_match = None
    best_score = 0
    
    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path).lower()
        score = 0
        
        # Score based on how many speaker name words appear in filename
        for word in speaker_words:
            if word in filename:
                score += len(word)
        
        if score > best_score:
            best_score = score
            best_match = pdf_path
    
    return best_match if best_score > 0 else None


def extract_pdf_content(pdf_path: str) -> dict:
    """Extract both text and visual content from PDF"""
    try:
        # Extract text content
        text_loader = PyPDFLoader(pdf_path)
        text_docs = text_loader.load()
        text_content = "\n\n".join([doc.page_content for doc in text_docs])
        
        logger.info(f"PyPDFLoader extracted {len(text_docs)} pages with {len(text_content)} chars")
        
        # Extract visual content (QR codes, images, charts)
        visual_analysis = _analyze_pdf_visually(pdf_path)
        
        # Check for missing pages by comparing PDF page count with extracted pages
        import fitz
        doc = fitz.open(pdf_path)
        total_pdf_pages = len(doc)
        doc.close()
        
        if len(text_docs) != total_pdf_pages:
            logger.warning(f"Page count mismatch: PDF has {total_pdf_pages} pages but PyPDFLoader extracted {len(text_docs)} pages")
        
        # Combine text with visual descriptions
        enhanced_content = text_content
        if visual_analysis["visual_elements"]:
            enhanced_content += "\n\n--- VISUAL ELEMENTS ---\n"
            for element in visual_analysis["visual_elements"]:
                enhanced_content += f"[Page {element['page']}] {element['type']}: {element['description']}\n"
        
        return {
            "text_content": text_content,
            "enhanced_content": enhanced_content,
            "visual_analysis": visual_analysis,
            "qr_codes": visual_analysis["qr_codes"],
            "visual_elements": visual_analysis["visual_elements"],
            "page_count_info": f"PDF: {total_pdf_pages} pages, Extracted: {len(text_docs)} pages"
        }
    except Exception as e:
        logger.error(f"Error extracting PDF content from {pdf_path}: {e}")
        return {
            "text_content": "",
            "enhanced_content": "",
            "visual_analysis": {"qr_codes": [], "visual_elements": [], "page_analyses": []},
            "qr_codes": [],
            "visual_elements": []
        }


def find_matching_video(speaker_name: str) -> str:
    """Find video file that best matches speaker name"""
    video_patterns = ["*.mp4", "*.mkv", "*.avi", "*.mov", "*.webm", "*.m4a", "*.wav"]
    video_files = []
    
    for pattern in video_patterns:
        video_files.extend(glob.glob(f"data/videos/{pattern}"))
    
    if not video_files:
        return None
        
    # Split speaker name into individual words
    speaker_words = [word.lower() for word in speaker_name.replace("-", " ").replace("_", " ").split() if len(word) > 2]
    
    best_match = None
    best_score = 0
    
    for video_path in video_files:
        filename = os.path.basename(video_path).lower()
        score = 0
        
        # Score based on how many speaker name words appear in filename
        for word in speaker_words:
            if word in filename:
                score += len(word)
        
        if score > best_score:
            best_score = score
            best_match = video_path
    
    return best_match if best_score > 0 else None


def extract_youtube_transcript(youtube_url: str) -> dict:
    """Extract transcript from YouTube using AssemblyAI with yt-dlp fallback"""
    try:
        # First try direct URL with AssemblyAI
        loader = AssemblyAIAudioTranscriptLoader(
            file_path=youtube_url,
            transcript_format=TranscriptFormat.SUBTITLES_SRT
        )
        docs = loader.load()
        
        if docs:
            srt_content = docs[0].page_content
            return {
                "success": True,
                "srt_content": srt_content,
                "source": "youtube_url_direct"
            }
        else:
            return {"success": False, "error": "No content returned from AssemblyAI"}
            
    except Exception as e:
        error_str = str(e)
        logger.warning(f"Direct YouTube URL failed: {error_str}")
        
        # If we get HTML/text error, try yt-dlp download first
        if "text/html" in error_str or "HTML document" in error_str:
            try:
                import yt_dlp
                import tempfile
                import os
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    audio_path = os.path.join(temp_dir, "audio.%(ext)s")
                    
                    ydl_opts = {
                        'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best[height<=480]',
                        'outtmpl': audio_path,
                        'extract_flat': False,
                        'ignoreerrors': True,
                        'no_warnings': False,
                        'extractaudio': True,
                        'audioformat': 'mp3',
                        'embed_subs': False,
                        'writesubtitles': False,
                        'writeautomaticsub': False,
                        # Anti-bot measures
                        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'referer': 'https://www.youtube.com/',
                        'http_chunk_size': 10485760,
                        'retries': 3,
                        'fragment_retries': 3,
                        'skip_unavailable_fragments': True,
                    }
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([youtube_url])
                    
                    # Find the downloaded file
                    audio_files = [f for f in os.listdir(temp_dir) if f.startswith("audio.")]
                    if not audio_files:
                        return {"success": False, "error": "yt-dlp download failed - no audio file created"}
                    
                    downloaded_file = os.path.join(temp_dir, audio_files[0])
                    
                    # Now transcribe the downloaded file
                    loader = AssemblyAIAudioTranscriptLoader(
                        file_path=downloaded_file,
                        transcript_format=TranscriptFormat.SUBTITLES_SRT
                    )
                    docs = loader.load()
                    
                    if docs:
                        return {
                            "success": True,
                            "srt_content": docs[0].page_content,
                            "source": "youtube_url_yt-dlp"
                        }
                    else:
                        return {"success": False, "error": "AssemblyAI transcription failed on downloaded file"}
                        
            except ImportError:
                logger.error("yt-dlp not available for YouTube download fallback")
                return {"success": False, "error": f"YouTube URL failed: {error_str} (yt-dlp not available)"}
            except Exception as fallback_error:
                logger.error(f"yt-dlp fallback failed: {fallback_error}")
                return {"success": False, "error": f"Both direct and yt-dlp failed: {error_str}, {str(fallback_error)}"}
        else:
            return {"success": False, "error": error_str}


def extract_local_video_transcript(video_path: str) -> dict:
    """Extract transcript from local video file using AssemblyAI"""
    try:
        # Use SRT format for timestamps
        loader = AssemblyAIAudioTranscriptLoader(
            file_path=video_path,
            transcript_format=TranscriptFormat.SUBTITLES_SRT
        )
        docs = loader.load()
        
        if docs:
            srt_content = docs[0].page_content
            return {
                "success": True,
                "srt_content": srt_content,
                "source": "local_video"
            }
        else:
            return {"success": False, "error": "No content returned from AssemblyAI"}
            
    except Exception as e:
        logger.error(f"Error extracting local video transcript: {e}")
        return {"success": False, "error": str(e)}