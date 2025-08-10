#!/usr/bin/env python

import logging
import glob
import os
from langchain_community.document_loaders import AssemblyAIAudioTranscriptLoader, PyPDFLoader
from langchain_community.document_loaders.assemblyai import TranscriptFormat

logger = logging.getLogger(__name__)


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


def extract_pdf_content(pdf_path: str) -> str:
    """Extract text content from PDF using PyPDFLoader"""
    try:
        loader = PyPDFLoader(pdf_path)
        docs = loader.load()
        return "\n\n".join([doc.page_content for doc in docs])
    except Exception as e:
        logger.error(f"Error extracting PDF content from {pdf_path}: {e}")
        return ""


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
                        'format': 'bestaudio/best',
                        'outtmpl': audio_path,
                        'extract_flat': False,
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