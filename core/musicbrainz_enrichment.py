"""
MusicBrainz API for ISRC verification and artist alias lookup.

MusicBrainz is the canonical music metadata database (like Wikipedia for music).
Provides:
- ISRC (International Standard Recording Code) verification
- Artist aliases and name variations
- Recording metadata (country, date, etc.)

CRITICAL: Rate limit is 1 request per second (enforced strictly!)

Based on: RetroMusicPlayer/app/.../musicbrainz/MusicBrainzSearcher.kt
API: https://musicbrainz.org/doc/MusicBrainz_API
"""

import aiohttp
import asyncio
import time
from typing import List, Optional, Dict, Tuple
import logging
import urllib.parse

logger = logging.getLogger(__name__)


class MusicBrainzEnrichment:
    """
    Fetch music metadata from MusicBrainz API.
    
    Rate Limit: 1 request per second (strictly enforced)
    """
    
    API_BASE = "https://musicbrainz.org/ws/2"
    USER_AGENT = "RetroMusic-Server/1.0 ( https://github.com/retromusic )"
    MIN_REQUEST_INTERVAL = 1.1  # 1.1 seconds to be safe (MusicBrainz requires 1s minimum)
    
    def __init__(self):
        self.session = aiohttp.ClientSession(headers={
            'User-Agent': self.USER_AGENT,
            'Accept': 'application/json'
        })
        self.last_request_time = 0.0
        self._lock = asyncio.Lock()  # Ensure serial requests
        self._cache: Dict[str, any] = {}  # Cache to reduce API calls
    
    async def close(self):
        """Close HTTP session"""
        await self.session.close()
    
    async def _enforce_rate_limit(self):
        """
        Enforce MusicBrainz rate limit: 1 request per second.
        
        This MUST be called before every API request!
        """
        async with self._lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            
            if time_since_last < self.MIN_REQUEST_INTERVAL:
                sleep_time = self.MIN_REQUEST_INTERVAL - time_since_last
                logger.debug(f"⏳ MusicBrainz rate limit: sleeping {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
            
            self.last_request_time = time.time()
    
    async def find_artist_aliases(self, artist_name: str) -> List[str]:
        """
        Find artist aliases and name variations.
        
        Args:
            artist_name: Artist name to search
            
        Returns:
            List of alias names (including original)
        """
        cache_key = f"aliases_{artist_name}"
        if cache_key in self._cache:
            logger.debug(f"MusicBrainz cache hit for artist aliases: {artist_name}")
            return self._cache[cache_key]
        
        try:
            await self._enforce_rate_limit()
            
            # Search for artist
            search_url = f"{self.API_BASE}/artist"
            params = {
                'query': f'artist:"{artist_name}"',
                'limit': 1,
                'fmt': 'json'
            }
            
            async with self.session.get(search_url, params=params, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"MusicBrainz artist search failed: {response.status}")
                    return [artist_name]
                
                data = await response.json()
                artists = data.get('artists', [])
                
                if not artists:
                    logger.debug(f"MusicBrainz: No artist found for {artist_name}")
                    return [artist_name]
                
                artist = artists[0]
                artist_id = artist['id']
            
            # Fetch artist with aliases (requires separate request with 'inc' parameter)
            await self._enforce_rate_limit()
            
            artist_url = f"{self.API_BASE}/artist/{artist_id}"
            params = {'inc': 'aliases', 'fmt': 'json'}
            
            async with self.session.get(artist_url, params=params, timeout=15) as response:
                if response.status != 200:
                    return [artist_name]
                
                data = await response.json()
                
                # Collect aliases
                aliases = {artist_name}  # Include original name
                
                # Add primary name
                if 'name' in data:
                    aliases.add(data['name'])
                
                # Add sort name
                if 'sort-name' in data:
                    aliases.add(data['sort-name'])
                
                # Add all aliases
                for alias in data.get('aliases', []):
                    if 'name' in alias:
                        aliases.add(alias['name'])
                
                alias_list = list(aliases)
                
                # Cache result
                self._cache[cache_key] = alias_list
                
                logger.info(f"🎭 MusicBrainz aliases for {artist_name}: {len(alias_list)} found")
                logger.debug(f"   Aliases: {', '.join(alias_list[:5])}")
                
                return alias_list
        
        except asyncio.TimeoutError:
            logger.warning(f"MusicBrainz request timed out for {artist_name}")
        except Exception as e:
            logger.error(f"MusicBrainz aliases error: {e}")
        
        return [artist_name]
    
    async def verify_track_isrc(
        self, 
        track_name: str,
        artist_name: str,
        expected_isrc: Optional[str] = None
    ) -> Optional[str]:
        """
        Verify or find track ISRC code.
        
        ISRC = International Standard Recording Code (unique track identifier)
        
        Args:
            track_name: Track title
            artist_name: Artist name
            expected_isrc: Optional ISRC to verify (from Spotify)
            
        Returns:
            ISRC code or None if not found
        """
        cache_key = f"isrc_{artist_name}_{track_name}"
        if cache_key in self._cache:
            logger.debug(f"MusicBrainz cache hit for ISRC: {track_name}")
            return self._cache[cache_key]
        
        try:
            await self._enforce_rate_limit()
            
            # Search for recording by ISRC if provided
            if expected_isrc:
                search_url = f"{self.API_BASE}/isrc/{expected_isrc}"
                params = {'fmt': 'json'}
                
                async with self.session.get(search_url, params=params, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        recordings = data.get('recordings', [])
                        
                        if recordings:
                            # ISRC verified!
                            logger.info(f"✅ MusicBrainz: ISRC {expected_isrc} verified")
                            self._cache[cache_key] = expected_isrc
                            return expected_isrc
            
            # Search by track and artist
            await self._enforce_rate_limit()
            
            search_url = f"{self.API_BASE}/recording"
            query = f'recording:"{track_name}" AND artist:"{artist_name}"'
            params = {
                'query': query,
                'limit': 5,
                'fmt': 'json'
            }
            
            async with self.session.get(search_url, params=params, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"MusicBrainz recording search failed: {response.status}")
                    return None
                
                data = await response.json()
                recordings = data.get('recordings', [])
                
                if not recordings:
                    logger.debug(f"MusicBrainz: No recording found for {artist_name} - {track_name}")
                    return None
                
                # Try to find a recording with ISRC
                for recording in recordings:
                    if 'isrcs' in recording and recording['isrcs']:
                        isrc = recording['isrcs'][0]
                        
                        # Cache and return
                        self._cache[cache_key] = isrc
                        
                        logger.info(f"🔍 MusicBrainz: ISRC found for {track_name}: {isrc}")
                        return isrc
                
                logger.debug(f"MusicBrainz: No ISRC found in recordings for {track_name}")
        
        except asyncio.TimeoutError:
            logger.warning(f"MusicBrainz request timed out for {track_name}")
        except Exception as e:
            logger.error(f"MusicBrainz ISRC error: {e}")
        
        return None
    
    async def get_recording_info(
        self, 
        track_name: str,
        artist_name: str
    ) -> Optional[Dict]:
        """
        Get comprehensive recording information.
        
        Args:
            track_name: Track title
            artist_name: Artist name
            
        Returns:
            Dict with: title, artist, isrc, length, country, date
        """
        try:
            await self._enforce_rate_limit()
            
            search_url = f"{self.API_BASE}/recording"
            query = f'recording:"{track_name}" AND artist:"{artist_name}"'
            params = {
                'query': query,
                'limit': 1,
                'fmt': 'json',
                'inc': 'artists+isrcs+releases'
            }
            
            async with self.session.get(search_url, params=params, timeout=15) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                recordings = data.get('recordings', [])
                
                if not recordings:
                    return None
                
                recording = recordings[0]
                
                info = {
                    'title': recording.get('title'),
                    'length_ms': recording.get('length'),  # Duration in milliseconds
                    'isrc': recording.get('isrcs', [None])[0],
                    'source': 'MusicBrainz'
                }
                
                # Extract artist name
                if 'artist-credit' in recording:
                    artists = [ac['name'] for ac in recording['artist-credit'] if 'name' in ac]
                    info['artists'] = artists
                
                # Extract release info (country, date)
                if 'releases' in recording and recording['releases']:
                    release = recording['releases'][0]
                    info['country'] = release.get('country')
                    info['date'] = release.get('date')
                
                logger.info(f"✅ MusicBrainz recording info: {info.get('title')} (ISRC: {info.get('isrc')})")
                return info
        
        except asyncio.TimeoutError:
            logger.warning(f"MusicBrainz request timed out for {track_name}")
        except Exception as e:
            logger.error(f"MusicBrainz recording info error: {e}")
        
        return None
    
    def clear_cache(self):
        """Clear all caches"""
        self._cache.clear()
        logger.info("🧹 MusicBrainz cache cleared")
