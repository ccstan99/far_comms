#!/usr/bin/env python3
"""
Manual YouTube video downloader for FAR.AI content processing.
Use this when automated downloads fail due to YouTube restrictions.
"""

import os
import sys
import yt_dlp
from pathlib import Path

def download_youtube_video(url: str, speaker_name: str = None, output_dir: str = "data/videos"):
    """
    Download YouTube video with optimized settings for transcript extraction.
    
    Args:
        url: YouTube URL
        speaker_name: Optional speaker name for filename
        output_dir: Directory to save video
    """
    
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Configure filename
    if speaker_name:
        filename = f"{speaker_name}_%(title)s.%(ext)s"
    else:
        filename = "%(uploader)s_%(title)s.%(ext)s"
    
    output_path = os.path.join(output_dir, filename)
    
    # Optimized yt-dlp options for audio extraction
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best[height<=720]',
        'outtmpl': output_path,
        'extract_flat': False,
        'ignoreerrors': False,
        'no_warnings': False,
        # Audio extraction
        'extractaudio': True,
        'audioformat': 'mp3',
        'audioquality': '192K',
        # Anti-bot measures
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'http_chunk_size': 10485760,
        'retries': 5,
        'fragment_retries': 5,
        'skip_unavailable_fragments': True,
        # Cookies (if available)
        # 'cookiefile': 'cookies.txt',  # Uncomment if you have YouTube cookies
        # Rate limiting
        'sleep_interval': 1,
        'max_sleep_interval': 5,
        'sleep_interval_subtitles': 1,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Downloading: {url}")
            print(f"Output: {output_path}")
            ydl.download([url])
            print("✅ Download completed successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Download failed: {e}")
        print("\n💡 Troubleshooting tips:")
        print("1. Update yt-dlp: pip install -U yt-dlp")
        print("2. Try a different video URL")
        print("3. Check if video is private/restricted")
        print("4. Consider using cookies.txt from browser")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python download_youtube.py <youtube_url> [speaker_name]")
        print("Example: python download_youtube.py https://youtu.be/xcU9lZ0QcXI 'Huiqi Deng'")
        sys.exit(1)
    
    url = sys.argv[1]
    speaker_name = sys.argv[2] if len(sys.argv) > 2 else None
    
    success = download_youtube_video(url, speaker_name)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()