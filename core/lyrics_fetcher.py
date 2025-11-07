"""
Multi-provider lyrics fetcher with fallback strategy.

Providers (in order of preference):
1. LrcLib - Best for synced LRC lyrics (free, no API key)
2. Genius - Good for plain text lyrics (requires API token)
3. Musixmatch - Fallback for popular tracks (web scraping)

Based on:
- RetroMusicPlayer: app/.../lyrics/LyricsFetcher.kt
- spotify-downloader: spotdl/providers/lyrics/genius.py
"""

import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import Optional, Dict
import logging
import re
from urllib.parse import quote

logger = logging.getLogger(__name__)


class LyricsFetcher:
    """
    Fetches lyrics from multiple providers with automatic fallback.
    """
    
    LRCLIB_API = "https://lrclib.net/api"
    GENIUS_API = "https://api.genius.com"
    MUSIXMATCH_SEARCH = "https://www.musixmatch.com/search"
    
    def __init__(self, genius_token: Optional[str] = None):
        """
        Initialize lyrics fetcher.
        
        Args:
            genius_token: Optional Genius API token (for better rate limits)
        """
        self.genius_token = genius_token
        self.session = aiohttp.ClientSession(headers={
            'User-Agent': 'RetroMusic-Server/1.0 (https://github.com/retromusic)'
        })
    
    async def close(self):
        """Close HTTP session"""
        await self.session.close()
    
    async def fetch_lyrics(
        self, 
        track_name: str, 
        artist_name: str,
        album_name: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        prefer_synced: bool = True
    ) -> Optional[Dict[str, str]]:
        """
        Fetch lyrics with fallback strategy.
        
        Args:
            track_name: Track title
            artist_name: Artist name
            album_name: Optional album name (improves LrcLib matching)
            duration_seconds: Optional track duration (improves LrcLib matching)
            prefer_synced: Prefer synced LRC format over plain text
            
        Returns:
            Dict with keys: 'lyrics' (text), 'synced' (bool), 'source' (provider name)
            Returns None if no lyrics found
        """
        logger.info(f"🎵 Fetching lyrics for: {artist_name} - {track_name}")
        
        # Try LrcLib first (best for synced lyrics)
        if prefer_synced:
            lrclib_result = await self._fetch_from_lrclib(
                track_name, 
                artist_name, 
                album_name, 
                duration_seconds
            )
            if lrclib_result:
                logger.info(f"✅ Lyrics found on LrcLib (synced: {lrclib_result['synced']})")
                return lrclib_result
        
        # Try Genius (good quality plain text)
        if self.genius_token:
            genius_result = await self._fetch_from_genius(track_name, artist_name)
            if genius_result:
                logger.info("✅ Lyrics found on Genius")
                return genius_result
        else:
            logger.debug("⚠️ Genius token not provided, skipping Genius")
        
        # Try Musixmatch as last resort
        musixmatch_result = await self._fetch_from_musixmatch(track_name, artist_name)
        if musixmatch_result:
            logger.info("✅ Lyrics found on Musixmatch")
            return musixmatch_result
        
        # If prefer_synced=True and we didn't find synced, try LrcLib for plain text
        if prefer_synced:
            lrclib_plain = await self._fetch_from_lrclib(
                track_name, 
                artist_name, 
                album_name, 
                duration_seconds,
                accept_plain=True
            )
            if lrclib_plain:
                logger.info("✅ Lyrics found on LrcLib (plain text fallback)")
                return lrclib_plain
        
        logger.warning(f"❌ No lyrics found for: {artist_name} - {track_name}")
        return None
    
    async def _fetch_from_lrclib(
        self, 
        track: str, 
        artist: str,
        album: Optional[str] = None,
        duration: Optional[int] = None,
        accept_plain: bool = False
    ) -> Optional[Dict]:
        """
        Fetch from LrcLib API (https://lrclib.net/api).
        
        LrcLib provides both synced (.lrc) and plain text lyrics.
        Free, no API key required!
        """
        try:
            # Build search URL
            params = {
                'track_name': track,
                'artist_name': artist
            }
            if album:
                params['album_name'] = album
            if duration:
                params['duration'] = duration
            
            url = f"{self.LRCLIB_API}/get"
            
            async with self.session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Prefer synced lyrics
                    if data.get('syncedLyrics'):
                        return {
                            'lyrics': data['syncedLyrics'],
                            'synced': True,
                            'source': 'LrcLib'
                        }
                    
                    # Fall back to plain lyrics if available
                    if accept_plain and data.get('plainLyrics'):
                        return {
                            'lyrics': data['plainLyrics'],
                            'synced': False,
                            'source': 'LrcLib'
                        }
                elif response.status == 404:
                    logger.debug(f"LrcLib: No lyrics found for {artist} - {track}")
                else:
                    logger.warning(f"LrcLib API error: {response.status}")
        
        except asyncio.TimeoutError:
            logger.warning("LrcLib request timed out")
        except Exception as e:
            logger.error(f"LrcLib error: {e}")
        
        return None
    
    async def _fetch_from_genius(self, track: str, artist: str) -> Optional[Dict]:
        """
        Fetch from Genius API + scrape lyrics page.
        
        Requires API token (self.genius_token).
        """
        if not self.genius_token:
            return None
        
        try:
            # Step 1: Search for track
            search_url = f"{self.GENIUS_API}/search"
            headers = {'Authorization': f'Bearer {self.genius_token}'}
            params = {'q': f"{track} {artist}"}
            
            async with self.session.get(
                search_url, 
                headers=headers, 
                params=params,
                timeout=10
            ) as response:
                if response.status != 200:
                    logger.warning(f"Genius search failed: {response.status}")
                    return None
                
                data = await response.json()
                hits = data.get('response', {}).get('hits', [])
                
                if not hits:
                    logger.debug(f"Genius: No results for {artist} - {track}")
                    return None
                
                # Get first result's URL
                song_url = hits[0]['result']['url']
            
            # Step 2: Scrape lyrics from song page
            async with self.session.get(song_url, timeout=10) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Find lyrics container (Genius uses multiple div classes)
                lyrics_divs = soup.find_all('div', attrs={'data-lyrics-container': 'true'})
                
                if not lyrics_divs:
                    logger.warning("Genius: Could not find lyrics on page")
                    return None
                
                # Extract text from all lyrics divs
                lyrics_parts = []
                for div in lyrics_divs:
                    # Get text with line breaks preserved
                    for br in div.find_all('br'):
                        br.replace_with('\n')
                    lyrics_parts.append(div.get_text())
                
                lyrics = '\n'.join(lyrics_parts).strip()
                
                if lyrics:
                    return {
                        'lyrics': lyrics,
                        'synced': False,
                        'source': 'Genius'
                    }
        
        except asyncio.TimeoutError:
            logger.warning("Genius request timed out")
        except Exception as e:
            logger.error(f"Genius error: {e}")
        
        return None
    
    async def _fetch_from_musixmatch(self, track: str, artist: str) -> Optional[Dict]:
        """
        Fetch from Musixmatch (web scraping - last resort).
        
        Note: Musixmatch may block scrapers, use sparingly!
        """
        try:
            # Search for track
            search_query = f"{artist} {track}"
            search_url = f"{self.MUSIXMATCH_SEARCH}/{quote(search_query)}"
            
            async with self.session.get(search_url, timeout=10) as response:
                if response.status != 200:
                    logger.warning(f"Musixmatch search failed: {response.status}")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Find first track result
                track_link = soup.find('a', class_=re.compile(r'track-card'))
                if not track_link or not track_link.get('href'):
                    logger.debug(f"Musixmatch: No results for {artist} - {track}")
                    return None
                
                # Get lyrics page URL
                lyrics_url = f"https://www.musixmatch.com{track_link['href']}"
            
            # Fetch lyrics page
            async with self.session.get(lyrics_url, timeout=10) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Find lyrics spans
                lyrics_spans = soup.find_all('span', class_=re.compile(r'lyrics__content__\w+'))
                
                if not lyrics_spans:
                    logger.warning("Musixmatch: Could not find lyrics on page")
                    return None
                
                # Extract text
                lyrics_parts = []
                for span in lyrics_spans:
                    text = span.get_text().strip()
                    if text:
                        lyrics_parts.append(text)
                
                lyrics = '\n'.join(lyrics_parts).strip()
                
                # Musixmatch often truncates lyrics for non-premium users
                if lyrics and len(lyrics) > 100:  # Minimum length check
                    return {
                        'lyrics': lyrics,
                        'synced': False,
                        'source': 'Musixmatch'
                    }
                else:
                    logger.warning("Musixmatch: Lyrics truncated (premium required)")
        
        except asyncio.TimeoutError:
            logger.warning("Musixmatch request timed out")
        except Exception as e:
            logger.error(f"Musixmatch error: {e}")
        
        return None


# Utility function for cleaning lyrics
def clean_lyrics(lyrics: str) -> str:
    """
    Clean up lyrics text.
    
    - Remove extra whitespace
    - Normalize line breaks
    - Remove common artifacts
    """
    # Remove \r characters
    lyrics = lyrics.replace('\r', '')
    
    # Remove multiple consecutive blank lines
    lyrics = re.sub(r'\n{3,}', '\n\n', lyrics)
    
    # Remove leading/trailing whitespace
    lyrics = lyrics.strip()
    
    return lyrics
