#!/usr/bin/env python

import os
import logging
import glob
from urllib.parse import urlparse, parse_qs
import re

try:
    import assemblyai as aai
    ASSEMBLYAI_AVAILABLE = True
except ImportError:
    ASSEMBLYAI_AVAILABLE = False

logger = logging.getLogger(__name__)


def extract_youtube_video_id(url: str) -> str | None:
    """
    Extract YouTube video ID from various YouTube URL formats
    
    Args:
        url: YouTube URL (youtube.com/watch?v=..., youtu.be/..., etc.)
    
    Returns:
        Video ID string or None if not found
    """
    if not url:
        return None
    
    # Handle different YouTube URL formats
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/.*[?&]v=([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def find_matching_video_file(speaker_name: str) -> str | None:
    """
    Find local video file that matches speaker name using shared matching logic
    
    Args:
        speaker_name: Speaker name to match against video filenames
    
    Returns:
        Path to matching video file or None if not found
    """
    from .file_matcher import find_best_matching_file
    
    # Get all video files in data/videos/
    video_patterns = ["*.mp4", "*.mkv", "*.avi", "*.mov", "*.webm", "*.m4a", "*.wav"]
    video_files = []
    
    for pattern in video_patterns:
        video_files.extend(glob.glob(f"data/videos/{pattern}"))
    
    if not video_files:
        logger.warning("No video files found in data/videos/")
        return None
    
    # Use shared file matching logic
    return find_best_matching_file(speaker_name, video_files, min_score=40)


def get_youtube_transcript_srt(youtube_url: str, local_video_path: str = None) -> dict:
    """
    Get SRT-formatted transcript from local video file using AssemblyAI
    
    Args:
        youtube_url: YouTube video URL (used for video_id extraction)
        local_video_path: Path to local video file (preferred over YouTube URL)
    
    Returns:
        Dict with 'success', 'srt_content', 'error' keys
    """
    if not ASSEMBLYAI_AVAILABLE:
        return {
            "success": False,
            "srt_content": "",
            "error": "AssemblyAI not available. Install with: pip install assemblyai"
        }
    
    # Get API key from environment
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        return {
            "success": False,
            "srt_content": "",
            "error": "ASSEMBLYAI_API_KEY environment variable not set"
        }
    
    try:
        # Prefer local video file over YouTube URL
        if local_video_path and os.path.exists(local_video_path):
            logger.info(f"Transcribing local video file: {local_video_path}")
            source_file = local_video_path
            video_id = extract_youtube_video_id(youtube_url) or "local_video"
        else:
            # Extract video ID and try YouTube URL (fallback)
            video_id = extract_youtube_video_id(youtube_url)
            if not video_id:
                return {
                    "success": False,
                    "srt_content": "",
                    "error": f"No local video file found and could not extract video ID from URL: {youtube_url}"
                }
            
            logger.info(f"No local file found, attempting YouTube transcription for video: {video_id}")
            source_file = f"https://www.youtube.com/watch?v={video_id}"
        
        # Set up AssemblyAI
        aai.settings.api_key = api_key
        
        # Configure transcription with best model and speaker labels
        config = aai.TranscriptionConfig(
            speech_model=aai.SpeechModel.best,
            speaker_labels=True  # Enable speaker diarization
        )
        
        # Transcribe from source file (local or YouTube)
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(source_file)
        
        if not transcript or transcript.status == "error":
            return {
                "success": False,
                "srt_content": "",
                "error": f"AssemblyAI transcription failed: {transcript.error if transcript else 'Unknown error'}"
            }
        
        # Get SRT format
        srt_content = transcript.export_subtitles_srt()
        
        logger.info(f"Successfully transcribed YouTube video {video_id}: {len(srt_content)} characters")
        
        return {
            "success": True,
            "srt_content": srt_content,
            "video_id": video_id,
            "duration_ms": transcript.audio_duration,
            "processing_time": "N/A"  # AssemblyAI doesn't provide this directly
        }
        
    except Exception as e:
        logger.error(f"Error transcribing YouTube video {youtube_url}: {e}")
        return {
            "success": False,
            "srt_content": "",
            "error": f"Transcription error: {str(e)}"
        }


def format_transcript_summary(result: dict) -> str:
    """
    Get a concise summary of transcript extraction result
    
    Args:
        result: Result from get_youtube_transcript_srt()
    
    Returns:
        Human-readable summary string
    """
    if not result.get("success"):
        return f"Transcript extraction failed: {result.get('error', 'Unknown error')}"
    
    video_id = result.get("video_id", "unknown")
    srt_length = len(result.get("srt_content", ""))
    duration = result.get("duration_ms", 0)
    
    # Convert duration to minutes
    duration_min = duration / 60000 if duration else 0
    
    return f"Extracted transcript for video {video_id}: {srt_length} chars, {duration_min:.1f} min"


# Example usage and testing
if __name__ == "__main__":
    # Test with a sample YouTube URL
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Roll for testing
    
    print("Testing YouTube transcript extraction...")
    result = get_youtube_transcript_srt(test_url)
    
    print(f"Success: {result.get('success')}")
    if result.get("success"):
        print(format_transcript_summary(result))
        print(f"\nFirst 200 characters of SRT:")
        print(result.get("srt_content", "")[:200])
    else:
        print(f"Error: {result.get('error')}")