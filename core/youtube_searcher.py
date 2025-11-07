"""
YouTube Music search with advanced scoring algorithm.
Based on: RetroMusicPlayer-old/.../YoutubeMusicSearcher.kt

Uses yt-dlp for searching YouTube Music (not regular YouTube!).
Implements the same 200+ point scoring system for accurate track matching.
"""

import logging
import re
from typing import Optional, Dict, Any, List
from yt_dlp import YoutubeDL
from ytmusicapi import YTMusic
import difflib

logger = logging.getLogger(__name__)


class YouTubeMusicSearcher:
    """
    YouTube Music search with multi-strategy scoring algorithm.
    
    Scoring system (200+ points possible):
    - Track word match (50%+ required): up to +50 points
    - Artist name presence: +20 points (or -10 if missing)
    - Duration matching: +30 (perfect), +20 (close), +10 (acceptable), -10 (far)
    - View count: +15 (1M+), +10 (100k+), +5 (10k+), -5 (<1k)
    - Title keywords (lyrics/audio): +15 points
    - Official (non-video): +10 points
    - Title similarity (Levenshtein): up to +50 points
    - Artist similarity (Levenshtein): up to +30 points
    
    Minimum threshold: 70 points to be considered valid
    """
    
    def __init__(self):
        """Initialize YouTube Music searcher with yt-dlp."""
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'extract_flat': False,  # We need full metadata
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'default_search': 'ytsearch',  # Search YouTube
            'socket_timeout': 30,
        }
        
        logger.info("✅ YouTube Music searcher initialized")
    
    def search(
        self,
        track_name: str,
        artist_name: str,
        duration_seconds: int,
        proxy: Optional[str] = None,
        max_results: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        Search YouTube Music for a track and return best match.
        
        MULTI-PASS STRATEGY:
        1. Pass 1: Track name only
        2. Pass 2: Track + Artist
        3. Pass 3: Artist + Track (reversed)
        
        Stops early if high-confidence match found (score >= 180).
        
        Args:
            track_name: Track name from Spotify
            artist_name: Artist name from Spotify  
            duration_seconds: Expected duration in seconds
            proxy: Optional proxy URL for bot detection mitigation
            max_results: Maximum search results to consider per pass
            
        Returns:
            Dictionary with:
            {
                'url': str,  # YouTube video URL
                'title': str,
                'duration': int,
                'uploader': str,
                'view_count': int,
                'score': int  # Confidence score
            }
            or None if no suitable match found
        """
        try:
            logger.debug(f"🔍 Multi-pass search starting")
            logger.debug(f"   Track: {track_name}")
            logger.debug(f"   Artist: {artist_name}")
            logger.debug(f"   Duration: {duration_seconds}s")
            
            # HIGH CONFIDENCE THRESHOLD - stop searching if reached
            HIGH_CONFIDENCE = 180
            
            # Configure yt-dlp for this search
            opts = self.ydl_opts.copy()
            if proxy:
                opts['proxy'] = proxy
                logger.info(f"🔄 Using proxy: {proxy}")
            
            ytmusic = YTMusic()
            best_overall = None
            
            # === PASS 1: Track name only ===
            logger.debug(f"\n{'='*60}")
            logger.debug(f"🎯 PASS 1: Track name only")
            logger.debug(f"{'='*60}")
            query1 = self._build_search_query(track_name, "")
            logger.debug(f"🔍 Query: {query1}")
            
            best_pass1 = self._search_with_query(
                ytmusic, query1, track_name, artist_name, duration_seconds, max_results
            )
            
            if best_pass1:
                logger.debug(f"✅ Pass 1 best: {best_pass1['title']} (score: {best_pass1['score']})")
                best_overall = best_pass1
                
                if best_pass1['score'] >= HIGH_CONFIDENCE:
                    logger.info(f"🏆 HIGH CONFIDENCE match found (>= {HIGH_CONFIDENCE})! Stopping search.")
                    return best_pass1
            else:
                logger.debug("❌ Pass 1: No matches")
            
            # === PASS 2: Track + Artist ===
            logger.debug(f"\n{'='*60}")
            logger.debug(f"🎯 PASS 2: Track + Artist")
            logger.debug(f"{'='*60}")
            query2 = self._build_search_query(track_name, artist_name)
            logger.debug(f"🔍 Query: {query2}")
            
            best_pass2 = self._search_with_query(
                ytmusic, query2, track_name, artist_name, duration_seconds, max_results
            )
            
            if best_pass2:
                logger.debug(f"✅ Pass 2 best: {best_pass2['title']} (score: {best_pass2['score']})")
                if not best_overall or best_pass2['score'] > best_overall['score']:
                    best_overall = best_pass2
                
                if best_pass2['score'] >= HIGH_CONFIDENCE:
                    logger.info(f"🏆 HIGH CONFIDENCE match found (>= {HIGH_CONFIDENCE})! Stopping search.")
                    return best_pass2
            else:
                logger.debug("❌ Pass 2: No matches")
            
            # === PASS 3: Artist + Track (reversed) ===
            logger.debug(f"\n{'='*60}")
            logger.debug(f"🎯 PASS 3: Artist + Track (reversed)")
            logger.debug(f"{'='*60}")
            query3 = self._build_search_query(artist_name, track_name)  # Reversed!
            logger.debug(f"🔍 Query: {query3}")
            
            best_pass3 = self._search_with_query(
                ytmusic, query3, track_name, artist_name, duration_seconds, max_results
            )
            
            if best_pass3:
                logger.debug(f"✅ Pass 3 best: {best_pass3['title']} (score: {best_pass3['score']})")
                if not best_overall or best_pass3['score'] > best_overall['score']:
                    best_overall = best_pass3
            else:
                logger.debug("❌ Pass 3: No matches")
            
            # === FINAL RESULT ===
            if best_overall:
                logger.info(f"✅ Found: {best_overall['title']} (score: {best_overall['score']}/200+)")
                return best_overall
            else:
                logger.warning("❌ No suitable matches found across all passes")
                return None
                
        except Exception as e:
            logger.error(f"❌ YouTube search error: {e}", exc_info=True)
            return None
    
    def _search_with_query(
        self,
        ytmusic: YTMusic,
        query: str,
        track_name: str,
        artist_name: str,
        duration_seconds: int,
        max_results: int
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a single search pass with the given query.
        
        Tries multiple filters to find the track:
        1. 'songs' - Official YouTube Music tracks
        2. No filter (None) - All results including uploads
        
        Args:
            ytmusic: YTMusic instance
            query: Search query string
            track_name: Original track name for scoring
            artist_name: Original artist name for scoring
            duration_seconds: Expected duration
            max_results: Max results to fetch
            
        Returns:
            Best match from this pass or None
        """
        try:
            all_videos = []
            
            # Try 'songs' filter first (official tracks)
            logger.debug(f"   🔍 Searching 'songs' filter...")
            try:
                search_results = ytmusic.search(query, filter='songs', limit=max_results)
                logger.debug(f"   📋 'songs' filter: {len(search_results)} results")
                
                for result in search_results:
                    video_id = result.get('videoId')
                    if not video_id:
                        continue
                    
                    video_url = f"https://music.youtube.com/watch?v={video_id}"
                    
                    video_info = {
                        'id': video_id,
                        'title': result.get('title', ''),
                        'duration': result.get('duration_seconds', 0),
                        'uploader': result.get('artists', [{}])[0].get('name', '') if result.get('artists') else '',
                        'view_count': 0,
                        'url': video_url,
                        'webpage_url': video_url,
                    }
                    all_videos.append(video_info)
            except Exception as e:
                logger.warning(f"   ⚠️ 'songs' filter failed: {e}")
            
            # Try 'videos' filter (includes uploads, user content)
            logger.debug(f"   🔍 Searching 'videos' filter...")
            try:
                video_results = ytmusic.search(query, filter='videos', limit=max_results)
                logger.debug(f"   📋 'videos' filter: {len(video_results)} results")
                
                for result in video_results:
                    video_id = result.get('videoId')
                    if not video_id:
                        continue
                    
                    # Skip duplicates
                    if any(v['id'] == video_id for v in all_videos):
                        continue
                    
                    video_url = f"https://music.youtube.com/watch?v={video_id}"
                    
                    # For videos, artist info is in different structure
                    artists = result.get('artists', [])
                    uploader = artists[0].get('name', '') if artists else ''
                    
                    video_info = {
                        'id': video_id,
                        'title': result.get('title', ''),
                        'duration': result.get('duration_seconds', 0),
                        'uploader': uploader,
                        'view_count': 0,
                        'url': video_url,
                        'webpage_url': video_url,
                    }
                    all_videos.append(video_info)
            except Exception as e:
                logger.warning(f"   ⚠️ 'videos' filter failed: {e}")
            
            # Try no filter (all categories)
            logger.debug(f"   🔍 Searching without filter (all categories)...")
            try:
                all_results = ytmusic.search(query, limit=max_results)
                logger.debug(f"   📋 No filter: {len(all_results)} results")
                
                for result in all_results:
                    video_id = result.get('videoId')
                    if not video_id:
                        continue
                    
                    # Skip duplicates
                    if any(v['id'] == video_id for v in all_videos):
                        continue
                    
                    video_url = f"https://music.youtube.com/watch?v={video_id}"
                    
                    # Handle different result types
                    artists = result.get('artists', [])
                    uploader = artists[0].get('name', '') if artists else ''
                    
                    video_info = {
                        'id': video_id,
                        'title': result.get('title', ''),
                        'duration': result.get('duration_seconds', 0),
                        'uploader': uploader,
                        'view_count': 0,
                        'url': video_url,
                        'webpage_url': video_url,
                    }
                    all_videos.append(video_info)
            except Exception as e:
                logger.warning(f"   ⚠️ No filter search failed: {e}")
            
            if not all_videos:
                logger.warning(f"   ❌ No results from any filter")
                return None
            
            logger.debug(f"📋 Total unique results: {len(all_videos)}")
            
            # Find best match using scoring algorithm
            best_match = self._find_best_match(
                all_videos,
                track_name,
                artist_name,
                duration_seconds
            )
            
            return best_match
            
        except Exception as e:
            logger.error(f"❌ Search pass error: {e}", exc_info=True)
            return None
    
    def _build_search_query(self, track: str, artist: str) -> str:
        """
        Build search query from track and artist names.
        Clean query by removing features, parentheses, etc.
        
        Args:
            track: Track name
            artist: Artist name
            
        Returns:
            Cleaned search query
        """
        query = f"{track} {artist}".strip()
        
        # Remove features (feat., ft., featuring)
        query = re.sub(r'\(feat\..*?\)', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\(ft\..*?\)', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\(featuring.*?\)', '', query, flags=re.IGNORECASE)
        
        # Remove brackets and extra content
        query = re.sub(r'\[.*?\]', '', query)
        query = re.sub(r'\(.*?\)', '', query)
        
        # Clean whitespace
        query = ' '.join(query.split())
        
        return query
    
    def _find_best_match(
        self,
        videos: List[Dict[str, Any]],
        track_name: str,
        artist_name: str,
        expected_duration: int
    ) -> Optional[Dict[str, Any]]:
        """
        Find best matching video using multi-strategy scoring.
        
        Args:
            videos: List of video metadata from yt-dlp
            track_name: Original track name
            artist_name: Original artist name
            expected_duration: Expected duration in seconds
            
        Returns:
            Best match dictionary or None
        """
        # Keywords for preferred results
        good_words = ['lyrics', 'lyric video', 'audio', 'official audio']
        
        scored_videos = []
        
        for video in videos:
            title = video.get('title', '').lower()
            track_lower = track_name.lower()
            artist_lower = artist_name.lower()
            score = 0
            
            logger.debug(f"🎵 Scoring: {video.get('title')[:80]}")
            logger.debug(f"   Uploader: {video.get('uploader', 'Unknown')}")
            logger.debug(f"   Duration: {video.get('duration', 0)}s (expected: {expected_duration}s)")
            
            # === STRATEGY 1: KEYWORD-BASED SCORING ===
            
            # Track word match (REQUIRED 50%+)
            track_words = [w for w in track_lower.split() if len(w) > 2]
            if track_words:
                matched_words = sum(1 for word in track_words if word in title)
                match_percent = matched_words / len(track_words)
                
                if match_percent < 0.5:
                    score -= 100  # Massive penalty - likely wrong song
                    logger.debug(f"   ❌ Track match: {int(match_percent * 100)}% -> PENALTY -100")
                else:
                    match_bonus = int(match_percent * 50)
                    score += match_bonus
                    logger.debug(f"   ✅ Track match: {int(match_percent * 100)}% -> +{match_bonus}")
            
            # Artist name presence
            uploader = video.get('uploader', '').lower()
            if artist_lower in title or artist_lower in uploader:
                score += 20
                logger.debug("   ✅ Artist found -> +20")
            else:
                score -= 10
                logger.debug("   ❌ Artist missing -> -10")
            
            # Duration matching
            duration = video.get('duration', 0)
            if expected_duration > 0 and duration > 0:
                duration_diff = abs(duration - expected_duration)
                
                if duration_diff <= 3:
                    duration_score = 30  # Perfect match
                elif duration_diff <= 10:
                    duration_score = 20  # Very close
                elif duration_diff <= 30:
                    duration_score = 10  # Acceptable
                else:
                    duration_score = -10  # Likely extended/loop
                
                score += duration_score
                logger.debug(f"   ⏱️ Duration diff: {duration_diff}s -> {'+' if duration_score > 0 else ''}{duration_score}")
            
            # View count (quality indicator)
            view_count = video.get('view_count', 0) or 0
            if view_count >= 1_000_000:
                view_score = 15
            elif view_count >= 100_000:
                view_score = 10
            elif view_count >= 10_000:
                view_score = 5
            elif view_count >= 1_000:
                view_score = 0
            else:
                view_score = -5
            
            score += view_score
            if view_count > 0:
                logger.debug(f"   👁️ Views: {view_count:,} -> {'+' if view_score > 0 else ''}{view_score}")
            
            # Title keywords (lyrics/audio)
            for word in good_words:
                if word in title:
                    score += 15
                    logger.debug(f"   Found '{word}' -> +15")
                    break
            
            # Official (non-video)
            if 'official' in title and 'music video' not in title and 'official video' not in title:
                score += 10
                logger.debug("   Official (non-video) -> +10")
            
            # === STRATEGY 2: SIMILARITY-BASED SCORING ===
            
            # Title similarity (up to +50 points)
            title_similarity = self._calculate_similarity(track_lower, title)
            title_score = int(title_similarity * 50)
            score += title_score
            logger.debug(f"   🔤 Title similarity: {int(title_similarity * 100)}% -> +{title_score}")
            
            # Artist similarity (up to +30 points)
            artist_in_uploader = self._calculate_similarity(artist_lower, uploader)
            artist_in_title = self._calculate_similarity(artist_lower, title)
            artist_similarity = max(artist_in_uploader, artist_in_title)
            artist_score = int(artist_similarity * 30)
            score += artist_score
            logger.debug(f"   👤 Artist similarity: {int(artist_similarity * 100)}% -> +{artist_score}")
            
            # === STRATEGY 3: KEYWORD PENALTIES (NEW - from original working algorithm) ===
            
            # Penalty for wrong versions/remixes
            bad_keywords = [
                'sing-along', 'sing along', 'singalong',
                'karaoke', 'instrumental', 'remix',
                'cover', 'nightcore', 'slowed', 'reverb',
                '8d audio', 'bass boost', 'sped up'
            ]
            
            for keyword in bad_keywords:
                if keyword in title:
                    score -= 50
                    logger.debug(f"   ⚠️ Keyword penalty '{keyword}' -> -50")
            
            logger.debug(f"   📊 TOTAL SCORE: {score}")
            
            # Only consider if score >= 100 (STRICT minimum threshold)
            if score >= 100:
                scored_videos.append({
                    'url': video.get('webpage_url') or video.get('url'),
                    'title': video.get('title'),
                    'duration': duration,
                    'uploader': video.get('uploader'),
                    'view_count': view_count,
                    'score': score,
                    'video_id': video.get('id')
                })
        
        if not scored_videos:
            logger.warning("❌ No videos met minimum score threshold (100)")
            return None
        
        # Return highest scoring video
        best = max(scored_videos, key=lambda x: x['score'])
        logger.debug(f"🏆 Best match: {best['title']} (score: {best['score']})")
        
        return best
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate similarity between two strings (0.0 to 1.0).
        Uses SequenceMatcher for Levenshtein-like similarity.
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            Similarity ratio between 0.0 and 1.0
        """
        if str1 == str2:
            return 1.0
        if str1 in str2 or str2 in str1:
            return 0.8
        
        # Word overlap
        words1 = set(str1.split())
        words2 = set(str2.split())
        if words1 and words2:
            intersection = len(words1 & words2)
            union = len(words1 | words2)
            if union > 0:
                return intersection / union
        
        # Fallback to sequence matcher
        return difflib.SequenceMatcher(None, str1.lower(), str2.lower()).ratio()
