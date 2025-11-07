"""
Last.fm API for play counts and listener statistics.

Last.fm provides:
- Track play counts (scrobbles)
- Track listener counts
- Artist statistics
- Track/artist tags (genres)

API Key: Public, no authentication required!
Based on: RetroMusicPlayer/app/.../spotify/lastfm/LastFmEnrichment.kt
API: https://www.last.fm/api
"""

import aiohttp
import asyncio
from typing import Optional, Tuple, List, Dict
import logging

logger = logging.getLogger(__name__)


class LastFmEnrichment:
    """
    Fetch music statistics from Last.fm API.
    
    Uses public API key (no authentication required).
    """
    
    # Public API key from RetroMusicPlayer
    API_KEY = "c679c8d3efa84613dc7dcb2e8d42da4c"
    BASE_URL = "https://ws.audioscrobbler.com/2.0/"
    
    def __init__(self):
        self.session = aiohttp.ClientSession(headers={
            'User-Agent': 'RetroMusic-Server/1.0 (https://github.com/retromusic)',
            'Accept': 'application/json'
        })
        self._cache: Dict[str, any] = {}
    
    async def close(self):
        """Close HTTP session"""
        await self.session.close()
    
    async def get_artist_stats(self, artist_name: str) -> Optional[Tuple[int, int]]:
        """
        Get artist statistics from Last.fm.
        
        Args:
            artist_name: Artist name to search
            
        Returns:
            Tuple of (listeners, playcount) or None
        """
        cache_key = f"artist_stats_{artist_name}"
        if cache_key in self._cache:
            logger.debug(f"Last.fm cache hit for artist stats: {artist_name}")
            return self._cache[cache_key]
        
        try:
            params = {
                'method': 'artist.getInfo',
                'artist': artist_name,
                'api_key': self.API_KEY,
                'format': 'json'
            }
            
            async with self.session.get(self.BASE_URL, params=params, timeout=10) as response:
                if response.status != 200:
                    logger.warning(f"Last.fm artist request failed: {response.status}")
                    return None
                
                data = await response.json()
                
                if 'error' in data:
                    logger.debug(f"Last.fm: Artist not found: {artist_name}")
                    return None
                
                artist = data.get('artist', {})
                stats = artist.get('stats', {})
                
                listeners = int(stats.get('listeners', 0))
                playcount = int(stats.get('playcount', 0))
                
                result = (listeners, playcount)
                
                # Cache result
                self._cache[cache_key] = result
                
                logger.info(f"📊 Last.fm artist stats: {artist_name} - {listeners:,} listeners, {playcount:,} plays")
                return result
        
        except asyncio.TimeoutError:
            logger.warning(f"Last.fm request timed out for artist {artist_name}")
        except Exception as e:
            logger.error(f"Last.fm artist stats error: {e}")
        
        return None
    
    async def get_track_stats(
        self, 
        track_name: str,
        artist_name: str
    ) -> Optional[Tuple[int, int]]:
        """
        Get track statistics from Last.fm.
        
        Args:
            track_name: Track title
            artist_name: Artist name
            
        Returns:
            Tuple of (listeners, playcount) or None
        """
        cache_key = f"track_stats_{artist_name}_{track_name}"
        if cache_key in self._cache:
            logger.debug(f"Last.fm cache hit for track stats: {track_name}")
            return self._cache[cache_key]
        
        try:
            params = {
                'method': 'track.getInfo',
                'track': track_name,
                'artist': artist_name,
                'api_key': self.API_KEY,
                'format': 'json'
            }
            
            async with self.session.get(self.BASE_URL, params=params, timeout=10) as response:
                if response.status != 200:
                    logger.warning(f"Last.fm track request failed: {response.status}")
                    return None
                
                data = await response.json()
                
                if 'error' in data:
                    logger.debug(f"Last.fm: Track not found: {artist_name} - {track_name}")
                    return None
                
                track = data.get('track', {})
                
                # Last.fm provides listeners and playcount
                listeners = int(track.get('listeners', 0))
                playcount = int(track.get('playcount', 0))
                
                result = (listeners, playcount)
                
                # Cache result
                self._cache[cache_key] = result
                
                logger.info(f"📊 Last.fm track stats: {track_name} - {listeners:,} listeners, {playcount:,} plays")
                return result
        
        except asyncio.TimeoutError:
            logger.warning(f"Last.fm request timed out for {track_name}")
        except Exception as e:
            logger.error(f"Last.fm track stats error: {e}")
        
        return None
    
    async def get_artist_genres(self, artist_name: str) -> List[str]:
        """
        Get artist genres (tags) from Last.fm.
        
        Args:
            artist_name: Artist name to search
            
        Returns:
            List of genre/tag names
        """
        cache_key = f"artist_genres_{artist_name}"
        if cache_key in self._cache:
            logger.debug(f"Last.fm cache hit for artist genres: {artist_name}")
            return self._cache[cache_key]
        
        try:
            params = {
                'method': 'artist.getTopTags',
                'artist': artist_name,
                'api_key': self.API_KEY,
                'format': 'json'
            }
            
            async with self.session.get(self.BASE_URL, params=params, timeout=10) as response:
                if response.status != 200:
                    logger.warning(f"Last.fm artist tags request failed: {response.status}")
                    return []
                
                data = await response.json()
                
                if 'error' in data:
                    logger.debug(f"Last.fm: No tags for artist: {artist_name}")
                    return []
                
                toptags = data.get('toptags', {})
                tags = toptags.get('tag', [])
                
                # Extract tag names (limit to top 10)
                genres = []
                for tag in tags[:10]:
                    if isinstance(tag, dict) and 'name' in tag:
                        genres.append(tag['name'])
                
                # Cache result
                self._cache[cache_key] = genres
                
                if genres:
                    logger.info(f"🎼 Last.fm genres for {artist_name}: {', '.join(genres[:5])}")
                
                return genres
        
        except asyncio.TimeoutError:
            logger.warning(f"Last.fm request timed out for artist {artist_name}")
        except Exception as e:
            logger.error(f"Last.fm artist genres error: {e}")
        
        return []
    
    async def get_track_tags(
        self, 
        track_name: str,
        artist_name: str
    ) -> List[str]:
        """
        Get track tags (genres) from Last.fm.
        
        Args:
            track_name: Track title
            artist_name: Artist name
            
        Returns:
            List of tag names
        """
        cache_key = f"track_tags_{artist_name}_{track_name}"
        if cache_key in self._cache:
            logger.debug(f"Last.fm cache hit for track tags: {track_name}")
            return self._cache[cache_key]
        
        try:
            params = {
                'method': 'track.getTopTags',
                'track': track_name,
                'artist': artist_name,
                'api_key': self.API_KEY,
                'format': 'json'
            }
            
            async with self.session.get(self.BASE_URL, params=params, timeout=10) as response:
                if response.status != 200:
                    logger.warning(f"Last.fm track tags request failed: {response.status}")
                    return []
                
                data = await response.json()
                
                if 'error' in data:
                    logger.debug(f"Last.fm: No tags for track: {track_name}")
                    return []
                
                toptags = data.get('toptags', {})
                tags = toptags.get('tag', [])
                
                # Extract tag names (limit to top 5)
                tag_names = []
                for tag in tags[:5]:
                    if isinstance(tag, dict) and 'name' in tag:
                        tag_names.append(tag['name'])
                
                # Cache result
                self._cache[cache_key] = tag_names
                
                if tag_names:
                    logger.info(f"🎼 Last.fm tags for {track_name}: {', '.join(tag_names)}")
                
                return tag_names
        
        except asyncio.TimeoutError:
            logger.warning(f"Last.fm request timed out for {track_name}")
        except Exception as e:
            logger.error(f"Last.fm track tags error: {e}")
        
        return []
    
    async def get_similar_artists(
        self, 
        artist_name: str,
        limit: int = 5
    ) -> List[Dict[str, str]]:
        """
        Get similar artists from Last.fm.
        
        Args:
            artist_name: Artist name to search
            limit: Maximum number of similar artists to return
            
        Returns:
            List of dicts with 'name' and 'match' (similarity score 0-1)
        """
        try:
            params = {
                'method': 'artist.getSimilar',
                'artist': artist_name,
                'api_key': self.API_KEY,
                'format': 'json',
                'limit': limit
            }
            
            async with self.session.get(self.BASE_URL, params=params, timeout=10) as response:
                if response.status != 200:
                    logger.warning(f"Last.fm similar artists request failed: {response.status}")
                    return []
                
                data = await response.json()
                
                if 'error' in data:
                    logger.debug(f"Last.fm: No similar artists for: {artist_name}")
                    return []
                
                similar_artists = data.get('similarartists', {}).get('artist', [])
                
                results = []
                for artist in similar_artists[:limit]:
                    if isinstance(artist, dict):
                        results.append({
                            'name': artist.get('name', ''),
                            'match': float(artist.get('match', 0))
                        })
                
                if results:
                    logger.info(f"🎭 Last.fm similar artists for {artist_name}: {', '.join(r['name'] for r in results[:3])}")
                
                return results
        
        except asyncio.TimeoutError:
            logger.warning(f"Last.fm request timed out for {artist_name}")
        except Exception as e:
            logger.error(f"Last.fm similar artists error: {e}")
        
        return []
    
    def clear_cache(self):
        """Clear all caches"""
        self._cache.clear()
        logger.info("🧹 Last.fm cache cleared")
