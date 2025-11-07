"""
Alternative YouTube downloader using pytubefix (works better than yt-dlp for some videos).
"""

import logging
from pathlib import Path
from typing import Optional
from pytubefix import YouTube
from pytubefix.cli import on_progress

logger = logging.getLogger(__name__)


class PyTubeDownloader:
    """
    Download YouTube audio using pytubefix library.
    More reliable than yt-dlp for some videos that return 403 errors.
    """
    
    def __init__(self):
        """Initialize PyTube downloader."""
        logger.info("✅ PyTube downloader initialized")
    
    def download_audio(
        self,
        youtube_url: str,
        output_path: Path,
        filename: str,
        progress_callback=None
    ) -> Optional[Path]:
        """
        Download audio from YouTube video.
        
        Args:
            youtube_url: YouTube video URL
            output_path: Directory to save the file
            filename: Filename (without extension)
            progress_callback: Optional callback for progress updates
            
        Returns:
            Path to downloaded file or None if failed
        """
        try:
            logger.info(f"🎬 Downloading from YouTube (pytubefix): {youtube_url}")
            
            # Create YouTube object
            yt = YouTube(
                youtube_url,
                on_progress_callback=lambda stream, chunk, bytes_remaining: 
                    self._progress_hook(stream, chunk, bytes_remaining, progress_callback)
                    if progress_callback else None
            )
            
            logger.info(f"📺 Video: {yt.title}")
            logger.info(f"⏱️  Duration: {yt.length}s")
            
            # Get audio stream (best quality)
            audio_stream = yt.streams.filter(
                only_audio=True,
                file_extension='mp4'  # Usually AAC in MP4 container
            ).order_by('abr').desc().first()
            
            if not audio_stream:
                logger.error("❌ No audio stream available")
                return None
            
            logger.info(f"🎵 Audio stream: {audio_stream.abr} ({audio_stream.filesize / 1024 / 1024:.1f} MB)")
            
            # Download
            output_path.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"📥 Downloading...")
            downloaded_file = audio_stream.download(
                output_path=str(output_path),
                filename=f"{filename}.mp4"  # pytubefix adds extension
            )
            
            result_path = Path(downloaded_file)
            logger.info(f"✅ Downloaded: {result_path.name}")
            
            return result_path
            
        except Exception as e:
            logger.error(f"❌ PyTube download failed: {e}", exc_info=True)
            return None
    
    def _progress_hook(self, stream, chunk, bytes_remaining, callback):
        """
        Progress callback for pytubefix.
        
        Args:
            stream: PyTube stream object
            chunk: Downloaded chunk
            bytes_remaining: Remaining bytes
            callback: User callback
        """
        try:
            total_size = stream.filesize
            bytes_downloaded = total_size - bytes_remaining
            percent = int((bytes_downloaded / total_size) * 100)
            
            # Map to 40-80% range (download phase in main workflow)
            scaled_percent = 40 + int(percent * 0.4)
            
            if callback:
                callback(scaled_percent, f"Downloading: {percent}%")
                
        except Exception as e:
            logger.error(f"❌ Progress callback error: {e}")
    
    async def get_audio_stream_url(self, youtube_url: str) -> Optional[str]:
        """
        Get direct audio stream URL WITHOUT downloading the file.
        Used by preview player to stream audio directly.
        
        Args:
            youtube_url: YouTube video URL
            
        Returns:
            Direct audio stream URL or None if failed
        """
        try:
            logger.info(f"🔗 Extracting stream URL: {youtube_url}")
            
            # Create YouTube object
            yt = YouTube(youtube_url)
            
            # Get best audio stream
            audio_stream = yt.streams.filter(
                only_audio=True,
                file_extension='mp4'
            ).order_by('abr').desc().first()
            
            if not audio_stream:
                logger.error("❌ No audio stream available")
                return None
            
            # Get direct URL (expires after ~6 hours)
            stream_url = audio_stream.url
            logger.info(f"✅ Stream URL extracted (expires in ~6 hours)")
            
            return stream_url
            
        except Exception as e:
            logger.error(f"❌ Failed to extract stream URL: {e}")
            return None
