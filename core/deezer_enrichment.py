"""
Deezer API for artist images and genre enrichment.

Deezer provides:
- High-quality artist images (up to 1000x1000)
- Artist genres/styles
- No API key required!

Based on: RetroMusicPlayer/app/.../network/DeezerService.kt
"""

import aiohttp
import asyncio
from typing import Optional, List, Dict
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)


class DeezerEnrichment:
    """
    Fetch artist metadata from Deezer API.
    
    API Documentation: https://developers.deezer.com/api
    """
    
    BASE_URL = "https://api.deezer.com"
    
    def __init__(self):
        self.session = aiohttp.ClientSession(headers={
            'User-Agent': 'RetroMusic-Server/1.0 (https://github.com/retromusic)',
            'Accept': 'application/json'
        })
        self._cache: Dict[str, Dict] = {}  # artist_name -> artist_data
    
    async def close(self):
        """Close HTTP session"""
        await self.session.close()
    
    async def get_artist_image(
        self, 
        artist_name: str,
        size: str = 'xl'  # 'small', 'medium', 'big', 'xl' (1000x1000)
    ) -> Optional[str]:
        """
        Get high-quality artist image URL from Deezer.
        
        Args:
            artist_name: Artist name to search
            size: Image size ('xl' = 1000x1000, 'big' = 500x500)
            
        Returns:
            Image URL or None if not found
        """
        try:
            artist_data = await self._search_artist(artist_name)
            if not artist_data:
                return None
            
            # Get image URL based on size
            size_key = f'picture_{size}'
            image_url = artist_data.get(size_key) or artist_data.get('picture_big')
            
            if image_url:
                logger.info(f"🖼️ Deezer artist image found: {artist_name} ({size})")
                return image_url
            else:
                logger.debug(f"Deezer: No image for artist {artist_name}")
                return None
        
        except Exception as e:
            logger.error(f"Deezer artist image error: {e}")
            return None
    
    async def get_artist_genres(self, artist_name: str) -> List[str]:
        """
        Get artist genres from Deezer.
        
        Args:
            artist_name: Artist name to search
            
        Returns:
            List of genre names
        """
        try:
            artist_data = await self._search_artist(artist_name)
            if not artist_data:
                return []
            
            # Fetch full artist details (includes genres)
            artist_id = artist_data['id']
            artist_url = f"{self.BASE_URL}/artist/{artist_id}"
            
            async with self.session.get(artist_url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Extract genres (Deezer doesn't always provide this)
                    # We'll use the artist's top albums to infer genres
                    albums_url = f"{self.BASE_URL}/artist/{artist_id}/albums"
                    async with self.session.get(albums_url, params={'limit': 5}, timeout=10) as albums_response:
                        if albums_response.status == 200:
                            albums_data = await albums_response.json()
                            genres = set()
                            
                            for album in albums_data.get('data', [])[:5]:
                                # Get album details to find genre
                                album_id = album['id']
                                album_url = f"{self.BASE_URL}/album/{album_id}"
                                async with self.session.get(album_url, timeout=10) as album_response:
                                    if album_response.status == 200:
                                        album_data = await album_response.json()
                                        if 'genres' in album_data:
                                            for genre in album_data['genres'].get('data', []):
                                                genres.add(genre['name'])
                            
                            if genres:
                                genre_list = list(genres)
                                logger.info(f"🎼 Deezer genres for {artist_name}: {', '.join(genre_list)}")
                                return genre_list
        
        except asyncio.TimeoutError:
            logger.warning(f"Deezer request timed out for {artist_name}")
        except Exception as e:
            logger.error(f"Deezer genres error: {e}")
        
        return []
    
    async def get_artist_info(self, artist_name: str) -> Optional[Dict]:
        """
        Get comprehensive artist information from Deezer.
        
        Args:
            artist_name: Artist name to search
            
        Returns:
            Dict with: name, image_url, nb_fan, nb_album, genres
        """
        try:
            artist_data = await self._search_artist(artist_name)
            if not artist_data:
                return None
            
            # Fetch full artist details
            artist_id = artist_data['id']
            artist_url = f"{self.BASE_URL}/artist/{artist_id}"
            
            async with self.session.get(artist_url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    info = {
                        'name': data.get('name'),
                        'image_url': data.get('picture_xl') or data.get('picture_big'),
                        'nb_fan': data.get('nb_fan', 0),
                        'nb_album': data.get('nb_album', 0),
                        'source': 'Deezer'
                    }
                    
                    logger.info(f"✅ Deezer info for {artist_name}: {info['nb_fan']:,} fans, {info['nb_album']} albums")
                    return info
        
        except asyncio.TimeoutError:
            logger.warning(f"Deezer request timed out for {artist_name}")
        except Exception as e:
            logger.error(f"Deezer artist info error: {e}")
        
        return None
    
    async def get_album_cover(
        self, 
        artist_name: str, 
        album_name: str,
        size: str = 'xl'  # 'small', 'medium', 'big', 'xl' (1000x1000)
    ) -> Optional[str]:
        """
        Get high-quality album cover from Deezer.
        
        Args:
            artist_name: Artist name
            album_name: Album name
            size: Cover size ('xl' = 1000x1000)
            
        Returns:
            Cover URL or None
        """
        try:
            # Search for album
            search_query = f"{artist_name} {album_name}"
            search_url = f"{self.BASE_URL}/search/album"
            params = {'q': search_query, 'limit': 5}
            
            async with self.session.get(search_url, params=params, timeout=10) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                results = data.get('data', [])
                
                if not results:
                    logger.debug(f"Deezer: No album found for {artist_name} - {album_name}")
                    return None
                
                # Find best match (first result is usually best)
                album = results[0]
                size_key = f'cover_{size}'
                cover_url = album.get(size_key) or album.get('cover_big')
                
                if cover_url:
                    logger.info(f"🖼️ Deezer album cover found: {album_name} ({size})")
                    return cover_url
        
        except asyncio.TimeoutError:
            logger.warning(f"Deezer request timed out for {album_name}")
        except Exception as e:
            logger.error(f"Deezer album cover error: {e}")
        
        return None
    
    async def _search_artist(self, artist_name: str) -> Optional[Dict]:
        """
        Search for artist on Deezer.
        
        Returns artist data dict or None.
        Caches results to avoid redundant API calls.
        """
        # Check cache first
        if artist_name in self._cache:
            logger.debug(f"Deezer cache hit for {artist_name}")
            return self._cache[artist_name]
        
        try:
            search_url = f"{self.BASE_URL}/search/artist"
            params = {'q': artist_name, 'limit': 5}
            
            async with self.session.get(search_url, params=params, timeout=10) as response:
                if response.status != 200:
                    logger.warning(f"Deezer search failed: {response.status}")
                    return None
                
                data = await response.json()
                results = data.get('data', [])
                
                if not results:
                    logger.debug(f"Deezer: No artist found for {artist_name}")
                    return None
                
                # Return first result (usually best match)
                artist_data = results[0]
                
                # Cache result
                self._cache[artist_name] = artist_data
                
                logger.debug(f"Deezer: Found artist '{artist_data['name']}' for query '{artist_name}'")
                return artist_data
        
        except asyncio.TimeoutError:
            logger.warning(f"Deezer search timed out for {artist_name}")
        except Exception as e:
            logger.error(f"Deezer search error: {e}")
        
        return None
    
    def clear_cache(self):
        """Clear artist cache"""
        self._cache.clear()
        logger.info("🧹 Deezer cache cleared")
