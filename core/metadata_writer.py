"""
Metadata writer for audio files using Mutagen.
Supports ID3 tags (MP3/M4A) with album art embedding.
Last updated: 2025-11-06 18:20
"""

import logging
import os
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TDRC, TRCK, TPOS, USLT, APIC, TSRC
from mutagen.mp3 import MP3

logger = logging.getLogger(__name__)


class MetadataWriter:
    """
    Write ID3 metadata to audio files.
    
    Supports formats:
    - M4A (AAC from YouTube)
    - MP3
    
    Metadata written:
    - Title, artist(s), album, album artist
    - Release date, track number, disc number
    - ISRC code
    - Lyrics (if available)
    - Album art (embedded from URL)
    """
    
    def __init__(self):
        """Initialize metadata writer."""
        logger.info("✅ Metadata writer initialized")
    
    def write_metadata(
        self,
        audio_file: Path,
        metadata: Dict[str, Any],
        lyrics: Optional[str] = None
    ) -> bool:
        """
        Write metadata to audio file.
        
        Args:
            audio_file: Path to audio file (M4A or MP3)
            metadata: Metadata dictionary from Spotify (get_track_metadata)
            lyrics: Optional lyrics text
            
        Returns:
            True if successful, False otherwise
        """
        try:
            file_ext = audio_file.suffix.lower()
            
            if file_ext == '.m4a':
                return self._write_m4a_metadata(audio_file, metadata, lyrics)
            elif file_ext == '.mp3':
                return self._write_mp3_metadata(audio_file, metadata, lyrics)
            else:
                logger.error(f"❌ Unsupported format: {file_ext}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to write metadata: {e}", exc_info=True)
            return False
    
    def _write_m4a_metadata(
        self,
        audio_file: Path,
        metadata: Dict[str, Any],
        lyrics: Optional[str]
    ) -> bool:
        """
        Write metadata to M4A file.
        
        Args:
            audio_file: Path to M4A file
            metadata: Spotify metadata
            lyrics: Optional lyrics
            
        Returns:
            True if successful
        """
        logger.info(f"📝 Writing M4A metadata: {audio_file.name}")
        
        audio = MP4(audio_file)
        
        # Title
        if metadata.get('title'):
            audio['\xa9nam'] = [metadata['title']]
        
        # Artists (primary)
        if metadata.get('artists'):
            # Join multiple artists
            artists_str = ', '.join(metadata['artists'])
            audio['\xa9ART'] = [artists_str]
        
        # Album
        if metadata.get('album'):
            audio['\xa9alb'] = [metadata['album']]
        
        # Album artist
        if metadata.get('album_artist'):
            audio['aART'] = [metadata['album_artist']]
        
        # Release date (year)
        if metadata.get('release_date'):
            year = metadata['release_date'][:4]  # YYYY
            audio['\xa9day'] = [year]
        
        # Track number
        if metadata.get('track_number'):
            track_num = metadata['track_number']
            total_tracks = metadata.get('total_tracks', 0)
            audio['trkn'] = [(track_num, total_tracks)]
        
        # Disc number
        if metadata.get('disc_number'):
            disc_num = metadata['disc_number']
            total_discs = metadata.get('total_discs', 0)
            audio['disk'] = [(disc_num, total_discs)]
        
        # Genre (if available)
        if metadata.get('genre'):
            audio['\xa9gen'] = [metadata['genre']]
        
        # Lyrics
        if lyrics:
            audio['\xa9lyr'] = [lyrics]
            logger.info("📄 Embedded lyrics")
        
        # Album art
        if metadata.get('album_art_url'):
            if self._embed_m4a_album_art(audio, metadata['album_art_url']):
                logger.info("🖼️ Embedded album art")
        
        # Save
        audio.save()
        logger.info(f"✅ M4A metadata written successfully")
        return True
    
    def _write_mp3_metadata(
        self,
        audio_file: Path,
        metadata: Dict[str, Any],
        lyrics: Optional[str]
    ) -> bool:
        """
        Write metadata to MP3 file using ID3.
        
        Args:
            audio_file: Path to MP3 file
            metadata: Spotify metadata
            lyrics: Optional lyrics
            
        Returns:
            True if successful
        """
        logger.info(f"📝 Writing MP3 metadata: {audio_file.name}")
        
        # Load or create ID3 tags
        try:
            audio = ID3(audio_file)
        except:
            audio = ID3()
        
        # Title
        if metadata.get('title'):
            audio['TIT2'] = TIT2(encoding=3, text=metadata['title'])
        
        # Artists
        if metadata.get('artists'):
            artists_str = ', '.join(metadata['artists'])
            audio['TPE1'] = TPE1(encoding=3, text=artists_str)
        
        # Album
        if metadata.get('album'):
            audio['TALB'] = TALB(encoding=3, text=metadata['album'])
        
        # Album artist
        if metadata.get('album_artist'):
            audio['TPE2'] = TPE2(encoding=3, text=metadata['album_artist'])
        
        # Release date
        if metadata.get('release_date'):
            audio['TDRC'] = TDRC(encoding=3, text=metadata['release_date'])
        
        # Track number
        if metadata.get('track_number'):
            track_num = metadata['track_number']
            total_tracks = metadata.get('total_tracks', 0)
            track_str = f"{track_num}/{total_tracks}" if total_tracks else str(track_num)
            audio['TRCK'] = TRCK(encoding=3, text=track_str)
        
        # Disc number
        if metadata.get('disc_number'):
            disc_num = metadata['disc_number']
            total_discs = metadata.get('total_discs', 0)
            disc_str = f"{disc_num}/{total_discs}" if total_discs else str(disc_num)
            audio['TPOS'] = TPOS(encoding=3, text=disc_str)
        
        # ISRC
        if metadata.get('isrc'):
            audio['TSRC'] = TSRC(encoding=3, text=metadata['isrc'])
        
        # Lyrics
        if lyrics:
            audio['USLT'] = USLT(encoding=3, lang='eng', desc='', text=lyrics)
            logger.info("📄 Embedded lyrics")
        
        # Album art
        if metadata.get('album_art_url'):
            if self._embed_mp3_album_art(audio, metadata['album_art_url']):
                logger.info("🖼️ Embedded album art")
        
        # Save
        audio.save(audio_file)
        logger.info(f"✅ MP3 metadata written successfully")
        return True
    
    def _embed_m4a_album_art(self, audio: MP4, album_art_url: str) -> bool:
        """
        Download and embed album art in M4A file.
        
        Args:
            audio: MP4 audio object
            album_art_url: URL to album art image
            
        Returns:
            True if successful
        """
        try:
            # Download album art
            response = requests.get(album_art_url, timeout=10)
            response.raise_for_status()
            
            image_data = response.content
            
            # Determine format
            if image_data[:4] == b'\xff\xd8\xff\xe0' or image_data[:3] == b'\xff\xd8\xff':
                image_format = MP4Cover.FORMAT_JPEG
            elif image_data[:8] == b'\x89PNG\r\n\x1a\n':
                image_format = MP4Cover.FORMAT_PNG
            else:
                logger.warning("⚠️ Unknown image format, assuming JPEG")
                image_format = MP4Cover.FORMAT_JPEG
            
            # Embed
            audio['covr'] = [MP4Cover(image_data, imageformat=image_format)]
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to embed M4A album art: {e}")
            return False
    
    def _embed_mp3_album_art(self, audio: ID3, album_art_url: str) -> bool:
        """
        Download and embed album art in MP3 file.
        
        Args:
            audio: ID3 audio object
            album_art_url: URL to album art image
            
        Returns:
            True if successful
        """
        try:
            # Download album art
            response = requests.get(album_art_url, timeout=10)
            response.raise_for_status()
            
            image_data = response.content
            
            # Determine MIME type
            if image_data[:4] == b'\xff\xd8\xff\xe0' or image_data[:3] == b'\xff\xd8\xff':
                mime_type = 'image/jpeg'
            elif image_data[:8] == b'\x89PNG\r\n\x1a\n':
                mime_type = 'image/png'
            else:
                logger.warning("⚠️ Unknown image format, assuming JPEG")
                mime_type = 'image/jpeg'
            
            # Embed (type 3 = front cover)
            audio['APIC'] = APIC(
                encoding=3,
                mime=mime_type,
                type=3,
                desc='Cover',
                data=image_data
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to embed MP3 album art: {e}")
            return False
