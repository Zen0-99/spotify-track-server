"""
Kworb.net scraper for Spotify stream statistics.

Fetches numerical stream data:
- Total plays (all-time Spotify streams)
- Daily plays (24-hour stream count)

Based on: RetroMusicPlayer/app/.../spotify/scraper/KworbScraper.kt
"""

import aiohttp
from bs4 import BeautifulSoup
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict
import logging
import hashlib
import json
import difflib

logger = logging.getLogger(__name__)


class KworbScraper:
    """
    Scrapes Spotify stream statistics from Kworb.net.
    
    Features:
    - 7-day cache (minimize requests)
    - 5-second rate limiting
    - User-agent rotation
    - Fuzzy track matching
    """
    
    # Caching to minimize requests
    CACHE_DURATION_DAYS = 7
    RATE_LIMIT_SECONDS = 5
    
    def __init__(self, cache_dir: str = "./cache/kworb"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.session: Optional[aiohttp.ClientSession] = None
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_time = 0.0
        
        logger.info("✅ Kworb scraper initialized")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
        return self.session
    
    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_track_streams(
        self,
        track_name: str,
        artist_name: str,
        spotify_id: str
    ) -> Optional[Dict[str, int]]:
        """
        Get stream statistics for a track.
        
        Args:
            track_name: Track name
            artist_name: Artist name
            spotify_id: Spotify track ID
            
        Returns:
            Dictionary with:
            {
                'total_plays': int,  # All-time streams
                'daily_plays': int   # 24-hour streams
            }
            or None if not found
        """
        # Check cache first
        cached = self._get_cached_streams(spotify_id)
        if cached:
            logger.info(f"📊 Kworb cache hit for {track_name}")
            return cached
        
        # Scrape from Kworb
        logger.info(f"📊 Fetching Kworb stats for {track_name} by {artist_name}")
        
        try:
            streams = await self._scrape_streams(track_name, artist_name)
            
            if streams:
                # Cache result
                self._cache_streams(spotify_id, streams)
                logger.info(f"✅ Kworb stats: {streams['total_plays']:,} total, {streams['daily_plays']:,} daily")
                return streams
            else:
                logger.warning(f"⚠️ Kworb: Track not found")
                return None
                
        except Exception as e:
            logger.error(f"❌ Kworb scraping failed: {e}")
            return None
    
    async def _scrape_streams(
        self,
        track_name: str,
        artist_name: str
    ) -> Optional[Dict[str, int]]:
        """
        Scrape Kworb.net for stream statistics.
        
        Args:
            track_name: Track name
            artist_name: Artist name
            
        Returns:
            Stream statistics or None
        """
        # Rate limiting
        async with self._rate_limit_lock:
            now = asyncio.get_event_loop().time()
            time_since_last = now - self._last_request_time
            
            if time_since_last < self.RATE_LIMIT_SECONDS:
                wait_time = self.RATE_LIMIT_SECONDS - time_since_last
                logger.info(f"⏳ Kworb rate limit: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
            
            self._last_request_time = asyncio.get_event_loop().time()
        
        # Kworb URL for artist's tracks
        # Format: https://kworb.net/spotify/artist/{artist_id}.html
        # We'll search by artist name first
        
        session = await self._get_session()
        
        # Clean artist name for URL
        artist_slug = artist_name.lower().replace(' ', '_').replace('&', 'and')
        artist_slug = ''.join(c for c in artist_slug if c.isalnum() or c == '_')
        
        # Try multiple URL patterns
        urls = [
            f"https://kworb.net/spotify/artist/{artist_slug}.html",
            f"https://kworb.net/spotify/artist/{artist_name.replace(' ', '_')}.html"
        ]
        
        for url in urls:
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        continue
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')
                    
                    # Find table rows
                    table = soup.find('table')
                    if not table:
                        continue
                    
                    rows = table.find_all('tr')
                    
                    # Search for matching track
                    for row in rows[1:]:  # Skip header
                        cols = row.find_all('td')
                        if len(cols) < 4:
                            continue
                        
                        # Column structure (typical):
                        # 0: Rank
                        # 1: Track name (with link)
                        # 2: Total plays
                        # 3: Daily plays
                        
                        row_track_name = cols[1].get_text(strip=True)
                        
                        # Fuzzy match track name
                        if self._fuzzy_match(track_name, row_track_name, threshold=0.7):
                            # Extract numbers
                            total_plays_str = cols[2].get_text(strip=True).replace(',', '')
                            daily_plays_str = cols[3].get_text(strip=True).replace(',', '')
                            
                            try:
                                total_plays = int(total_plays_str)
                                daily_plays = int(daily_plays_str) if daily_plays_str.isdigit() else 0
                                
                                return {
                                    'total_plays': total_plays,
                                    'daily_plays': daily_plays
                                }
                            except ValueError:
                                continue
                
            except Exception as e:
                logger.debug(f"Kworb URL failed: {url} - {e}")
                continue
        
        return None
    
    def _fuzzy_match(self, str1: str, str2: str, threshold: float = 0.8) -> bool:
        """
        Fuzzy string matching.
        
        Args:
            str1: First string
            str2: Second string
            threshold: Similarity threshold (0-1)
            
        Returns:
            True if strings match above threshold
        """
        # Normalize strings
        s1 = str1.lower().strip()
        s2 = str2.lower().strip()
        
        # Remove common noise
        for noise in ['(official audio)', '(official video)', 'hq', 'official']:
            s1 = s1.replace(noise, '').strip()
            s2 = s2.replace(noise, '').strip()
        
        # Calculate similarity
        ratio = difflib.SequenceMatcher(None, s1, s2).ratio()
        
        return ratio >= threshold
    
    def _get_cached_streams(self, spotify_id: str) -> Optional[Dict[str, int]]:
        """Get cached stream statistics if not expired"""
        cache_file = self.cache_dir / f"{spotify_id}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            
            # Check expiration
            cached_time = datetime.fromisoformat(data['timestamp'])
            age = datetime.now() - cached_time
            
            if age > timedelta(days=self.CACHE_DURATION_DAYS):
                logger.debug(f"Kworb cache expired for {spotify_id}")
                cache_file.unlink()  # Delete expired cache
                return None
            
            return {
                'total_plays': data['total_plays'],
                'daily_plays': data['daily_plays']
            }
            
        except Exception as e:
            logger.debug(f"Kworb cache read error: {e}")
            return None
    
    def _cache_streams(self, spotify_id: str, streams: Dict[str, int]):
        """Cache stream statistics with timestamp"""
        cache_file = self.cache_dir / f"{spotify_id}.json"
        
        data = {
            'total_plays': streams['total_plays'],
            'daily_plays': streams['daily_plays'],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.debug(f"Kworb cache write error: {e}")
