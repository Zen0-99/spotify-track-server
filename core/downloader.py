"""
Main downloader orchestrator.
Combines Spotify metadata + YouTube search + yt-dlp download + metadata writing.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from yt_dlp import YoutubeDL

from core.spotify_client import SpotifyClient
from core.youtube_searcher import YouTubeMusicSearcher
from core.metadata_writer import MetadataWriter
from core.pytube_downloader import PyTubeDownloader
from config import OUTPUT_DIR, CACHE_DIR

logger = logging.getLogger(__name__)


class TrackDownloader:
    """
    Orchestrates full track download workflow:
    
    1. Fetch metadata from Spotify
    2. Search YouTube Music for matching audio
    3. Download audio with yt-dlp
    4. Write metadata tags + album art
    5. Move to output directory
    """
    
    def __init__(
        self,
        spotify_client: SpotifyClient,
        youtube_searcher: Optional[YouTubeMusicSearcher] = None,
        metadata_writer: Optional[MetadataWriter] = None
    ):
        """
        Initialize downloader.
        
        Args:
            spotify_client: Initialized Spotify client
            youtube_searcher: Optional YouTube searcher (creates if None)
            metadata_writer: Optional metadata writer (creates if None)
        """
        self.spotify = spotify_client
        self.youtube = youtube_searcher or YouTubeMusicSearcher()
        self.metadata_writer = metadata_writer or MetadataWriter()
        self.pytube_downloader = PyTubeDownloader()  # Add PyTube downloader
        
        # Ensure output directory exists
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        logger.info("✅ Track downloader initialized")
    
    def download_track(
        self,
        track_id: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        include_lyrics: bool = True
    ) -> Optional[Path]:
        """
        Download a track by Spotify ID.
        
        Args:
            track_id: Spotify track ID
            progress_callback: Optional callback(percent: int, message: str)
            include_lyrics: Whether to fetch and embed lyrics
            
        Returns:
            Path to downloaded file, or None if failed
        """
        try:
            logger.info(f"📥 Starting download: {track_id}")
            
            # Step 1: Fetch Spotify metadata (0-20%)
            self._report_progress(progress_callback, 5, "Fetching Spotify metadata...")
            metadata = self.spotify.get_track_metadata(track_id)
            
            if not metadata:
                logger.error("❌ Failed to fetch Spotify metadata")
                self._report_progress(progress_callback, 0, "Failed: Could not fetch metadata")
                return None
            
            logger.info(f"🎵 Track: {metadata['title']} by {', '.join(metadata['artists'])}")
            self._report_progress(progress_callback, 20, f"Found: {metadata['title']}")
            
            # Step 2: Search YouTube Music (20-40%)
            self._report_progress(progress_callback, 25, "Searching YouTube Music...")
            
            youtube_result = self.youtube.search(
                track_name=metadata['title'],
                artist_name=', '.join(metadata['artists']),
                duration_seconds=metadata['duration_ms'] // 1000
            )
            
            if not youtube_result:
                logger.error("❌ No matching YouTube Music video found")
                self._report_progress(progress_callback, 0, "Failed: No YouTube match found")
                return None
            
            logger.info(f"🎬 Found video: {youtube_result['title']} (score: {youtube_result['score']})")
            self._report_progress(progress_callback, 40, f"Found YouTube match (score: {youtube_result['score']})")
            
            # Step 3: Download audio (40-80%)
            self._report_progress(progress_callback, 45, "Downloading audio...")
            
            audio_file = self._download_audio(
                youtube_url=youtube_result['url'],
                track_name=metadata['title'],
                artist_name=metadata['artists'][0],
                progress_callback=progress_callback
            )
            
            if not audio_file:
                logger.error("❌ Audio download failed")
                self._report_progress(progress_callback, 0, "Failed: Download error")
                return None
            
            logger.info(f"📦 Downloaded: {audio_file.name}")
            self._report_progress(progress_callback, 80, "Audio downloaded")
            
            # Step 4: Fetch lyrics (optional, 80-85%)
            lyrics = None
            if include_lyrics:
                self._report_progress(progress_callback, 82, "Fetching lyrics...")
                try:
                    from syncedlyrics import search
                    lyrics = search(f"{metadata['title']} {', '.join(metadata['artists'])}")
                    if lyrics:
                        logger.info("📄 Lyrics found")
                except Exception as e:
                    logger.warning(f"⚠️ Lyrics fetch failed: {e}")
            
            # Step 5: Write metadata (85-95%)
            self._report_progress(progress_callback, 85, "Writing metadata...")
            
            if not self.metadata_writer.write_metadata(audio_file, metadata, lyrics):
                logger.error("❌ Metadata writing failed")
                self._report_progress(progress_callback, 0, "Failed: Metadata error")
                return None
            
            logger.info("📝 Metadata written")
            self._report_progress(progress_callback, 95, "Metadata written")
            
            # Step 6: Move to output directory (95-100%)
            self._report_progress(progress_callback, 97, "Finalizing...")
            
            final_path = self._move_to_output(audio_file, metadata)
            
            if not final_path:
                logger.error("❌ Failed to move file to output")
                self._report_progress(progress_callback, 0, "Failed: File move error")
                return None
            
            logger.info(f"✅ Download complete: {final_path}")
            self._report_progress(progress_callback, 100, "Complete!")
            
            return final_path
            
        except Exception as e:
            logger.error(f"❌ Download failed: {e}", exc_info=True)
            self._report_progress(progress_callback, 0, f"Failed: {str(e)}")
            return None
    
    def _download_audio(
        self,
        youtube_url: str,
        track_name: str,
        artist_name: str,
        progress_callback: Optional[Callable[[int, str], None]]
    ) -> Optional[Path]:
        """
        Download audio from YouTube using multiple methods.
        
        Tries in order:
        1. PyTubefix (most reliable, works with current YouTube)
        2. yt-dlp with iOS client
        3. yt-dlp with browser cookies
        
        Args:
            youtube_url: YouTube video URL
            track_name: Track name for filename
            artist_name: Artist name for filename
            progress_callback: Progress callback
            
        Returns:
            Path to downloaded file in cache
        """
        # Sanitize filename
        safe_filename = self._sanitize_filename(f"{artist_name} - {track_name}")
        
        # Method 1: Try PyTubefix first (most reliable)
        try:
            logger.info("🔄 Trying download method: PyTubefix")
            self._report_progress(progress_callback, 45, "Downloading with PyTube...")
            
            downloaded_file = self.pytube_downloader.download_audio(
                youtube_url=youtube_url,
                output_path=CACHE_DIR,
                filename=safe_filename,
                progress_callback=lambda percent, msg: self._report_progress(progress_callback, percent, msg)
            )
            
            if downloaded_file and downloaded_file.exists():
                logger.info(f"✅ Download successful with: PyTubefix")
                
                # Convert MP4 to M4A if needed using ffmpeg
                if downloaded_file.suffix == '.mp4':
                    m4a_file = downloaded_file.with_suffix('.m4a')
                    try:
                        import subprocess
                        subprocess.run([
                            'ffmpeg', '-i', str(downloaded_file),
                            '-c:a', 'copy',  # Copy audio codec (no re-encoding)
                            '-y',  # Overwrite
                            str(m4a_file)
                        ], check=True, capture_output=True)
                        
                        # Remove original MP4
                        downloaded_file.unlink()
                        downloaded_file = m4a_file
                        logger.info("✅ Converted MP4 to M4A")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to convert to M4A, using MP4: {e}")
                        # Rename to m4a anyway (M4A and MP4 with AAC are compatible)
                        m4a_file = downloaded_file.with_suffix('.m4a')
                        downloaded_file.rename(m4a_file)
                        downloaded_file = m4a_file
                
                return downloaded_file
            else:
                logger.warning("⚠️ PyTubefix - file not found after download")
                
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"⚠️ PyTubefix failed: {error_msg}")
        
        # Method 2: Try yt-dlp methods as fallback
        logger.info("🔄 PyTubefix failed, trying yt-dlp fallback methods...")
        
        output_template = str(CACHE_DIR / f"{safe_filename}.%(ext)s")
        
        # yt-dlp progress hook
        def progress_hook(d):
            if d['status'] == 'downloading':
                # Map 40-80% (download phase)
                if 'downloaded_bytes' in d and 'total_bytes' in d:
                    percent = int(d['downloaded_bytes'] / d['total_bytes'] * 100)
                    # Scale to 40-80 range
                    scaled_percent = 40 + int(percent * 0.4)
                    self._report_progress(
                        progress_callback,
                        scaled_percent,
                        f"Downloading: {percent}%"
                    )
            elif d['status'] == 'finished':
                self._report_progress(progress_callback, 80, "Processing audio...")
        
        # Base options
        base_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',  # M4A for better quality
            }],
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [progress_hook],
        }
        
        # Try yt-dlp methods
        download_methods = [
            {
                'name': 'iOS client (yt-dlp)',
                'opts': {
                    **base_opts,
                    'extractor_args': {'youtube': {'player_client': ['ios']}},
                }
            },
            {
                'name': 'Browser cookies - Edge (yt-dlp)',
                'opts': {
                    **base_opts,
                    'cookiesfrombrowser': ('edge',),
                    'extractor_args': {'youtube': {'player_client': ['mweb']}},
                }
            },
        ]
        
        for method in download_methods:
            try:
                logger.info(f"🔄 Trying download method: {method['name']}")
                
                with YoutubeDL(method['opts']) as ydl:
                    ydl.download([youtube_url])
                
                # Find downloaded file
                downloaded_file = CACHE_DIR / f"{safe_filename}.m4a"
                
                if downloaded_file.exists():
                    logger.info(f"✅ Download successful with: {method['name']}")
                    return downloaded_file
                else:
                    logger.warning(f"⚠️ File not found after download: {method['name']}")
                    
            except Exception as e:
                error_msg = str(e)
                
                # Check if it's a 403 error
                if '403' in error_msg or 'Forbidden' in error_msg:
                    logger.warning(f"⚠️ {method['name']} failed with 403 - trying next method")
                    continue
                # Check if cookies not found (expected for some browsers)
                elif 'cookie' in error_msg.lower() and 'not found' in error_msg.lower():
                    logger.warning(f"⚠️ {method['name']} - browser not found, skipping")
                    continue
                else:
                    logger.error(f"❌ {method['name']} failed: {error_msg}")
                    continue
        
        # All methods failed
        logger.error(f"❌ All download methods failed")
        return None
    
    def _move_to_output(self, audio_file: Path, metadata: Dict[str, Any]) -> Optional[Path]:
        """
        Move file from cache to output directory with proper naming.
        
        Args:
            audio_file: Path to audio file in cache
            metadata: Track metadata
            
        Returns:
            Final path in output directory
        """
        try:
            # Create artist/album directory structure
            artist = metadata['artists'][0] if metadata['artists'] else 'Unknown Artist'
            album = metadata['album'] or 'Unknown Album'
            
            artist_dir = OUTPUT_DIR / self._sanitize_filename(artist)
            album_dir = artist_dir / self._sanitize_filename(album)
            album_dir.mkdir(parents=True, exist_ok=True)
            
            # Build filename: "01 - Track Name.m4a"
            track_num = metadata.get('track_number', 1)
            track_name = metadata['title']
            filename = f"{track_num:02d} - {self._sanitize_filename(track_name)}{audio_file.suffix}"
            
            final_path = album_dir / filename
            
            # Move file
            shutil.move(str(audio_file), str(final_path))
            
            logger.info(f"📁 Moved to: {final_path}")
            return final_path
            
        except Exception as e:
            logger.error(f"❌ File move failed: {e}", exc_info=True)
            return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename for filesystem.
        
        Args:
            filename: Filename to sanitize
            
        Returns:
            Safe filename
        """
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '')
        
        # Remove leading/trailing dots and spaces
        filename = filename.strip('. ')
        
        # Limit length
        if len(filename) > 200:
            filename = filename[:200]
        
        return filename
    
    def _report_progress(
        self,
        callback: Optional[Callable[[int, str], None]],
        percent: int,
        message: str
    ):
        """
        Report progress via callback.
        
        Args:
            callback: Progress callback
            percent: Progress percent (0-100)
            message: Status message
        """
        if callback:
            try:
                callback(percent, message)
            except Exception as e:
                logger.error(f"❌ Progress callback error: {e}")
