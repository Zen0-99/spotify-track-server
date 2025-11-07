"""
Spotify Web API client for fetching track/album metadata.
Based on: spotify-downloader/spotdl/utils/spotify.py

Simplified for server-side use (no user auth, caching handled separately).
"""

import logging
from typing import Dict, Any, Optional, List
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials

logger = logging.getLogger(__name__)


class SpotifyClient:
    """
    Spotify API client for fetching track and album metadata.
    Uses client credentials flow (no user authentication required).
    """
    
    def __init__(self, client_id: str, client_secret: str):
        """
        Initialize Spotify API client with credentials.
        
        Args:
            client_id: Spotify application client ID
            client_secret: Spotify application client secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
        
        # Initialize Spotipy client with credentials
        credential_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
        
        self.sp = Spotify(
            auth_manager=credential_manager,
            status_forcelist=(429, 500, 502, 503, 504),  # Retry on these status codes
            retries=3
        )
        
        logger.info("✅ Spotify client initialized")
    
    def get_track(self, track_id: str) -> Dict[str, Any]:
        """
        Fetch track metadata from Spotify API.
        
        Args:
            track_id: Spotify track ID (e.g., "3n3Ppam7vgaVa1iaRUc9Lp")
            
        Returns:
            Dictionary with track metadata
            
        Raises:
            Exception: If track not found or API error
        """
        try:
            track = self.sp.track(track_id)
            logger.info(f"🎵 Fetched track: {track['name']} by {track['artists'][0]['name']}")
            return track
        except Exception as e:
            logger.error(f"❌ Failed to fetch track {track_id}: {e}")
            raise
    
    def get_album_art(self, track_id: str) -> Optional[str]:
        """
        Get highest quality album art URL (640x640 preferred).
        
        Args:
            track_id: Spotify track ID
            
        Returns:
            Album art URL (640x640 if available) or None
        """
        try:
            track = self.get_track(track_id)
            album = track.get('album', {})
            images = album.get('images', [])
            
            if not images:
                logger.warning(f"⚠️ No album art found for track {track_id}")
                return None
            
            # Spotify returns images sorted by size (largest first)
            # Prefer 640x640 (index 0) or 300x300 (index 1)
            best_image = images[0]
            url = best_image.get('url')
            
            logger.info(f"🖼️ Album art: {best_image.get('width')}x{best_image.get('height')} - {url}")
            return url
            
        except Exception as e:
            logger.error(f"❌ Failed to get album art for {track_id}: {e}")
            return None
    
    def get_track_metadata(self, track_id: str) -> Dict[str, Any]:
        """
        Get comprehensive track metadata formatted for downloader.
        
        Args:
            track_id: Spotify track ID
            
        Returns:
            Dictionary with formatted metadata:
            {
                'id': str,
                'title': str,
                'artists': List[str],
                'album': str,
                'album_artist': str,
                'duration_ms': int,
                'release_date': str,
                'track_number': int,
                'disc_number': int,
                'isrc': Optional[str],
                'album_type': str,
                'album_art_url': Optional[str],
                'explicit': bool
            }
        """
        try:
            track = self.get_track(track_id)
            
            # Extract artist names
            artists = [artist['name'] for artist in track.get('artists', [])]
            
            # Get album info
            album = track.get('album', {})
            album_artists = [artist['name'] for artist in album.get('artists', [])]
            
            # Format metadata
            metadata = {
                'id': track['id'],
                'title': track['name'],
                'artists': artists,
                'album': album.get('name', 'Unknown Album'),
                'album_artist': album_artists[0] if album_artists else artists[0] if artists else 'Unknown',
                'duration_ms': track.get('duration_ms', 0),
                'release_date': album.get('release_date', ''),
                'track_number': track.get('track_number', 1),
                'disc_number': track.get('disc_number', 1),
                'isrc': track.get('external_ids', {}).get('isrc'),
                'album_type': album.get('album_type', 'album'),
                'album_art_url': self.get_album_art(track_id),
                'explicit': track.get('explicit', False),
                'popularity': track.get('popularity', 0)
            }
            
            logger.info(f"📋 Metadata extracted: {metadata['title']} - {metadata['artists']}")
            return metadata
            
        except Exception as e:
            logger.error(f"❌ Failed to get metadata for {track_id}: {e}")
            raise
    
    def get_album_metadata(self, album_id: str) -> Dict[str, Any]:
        """
        Get album metadata (useful for batch downloads).
        
        Args:
            album_id: Spotify album ID
            
        Returns:
            Dictionary with album metadata including all tracks
        """
        try:
            album = self.sp.album(album_id)
            logger.info(f"💿 Fetched album: {album['name']} by {album['artists'][0]['name']}")
            return album
        except Exception as e:
            logger.error(f"❌ Failed to fetch album {album_id}: {e}")
            raise
