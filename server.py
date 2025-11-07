"""
FastAPI server for Spotify track downloading with full metadata enrichment.

Endpoints:
- POST /api/download - Start track download
- GET /api/progress/{download_id} - SSE progress stream
- GET /api/download/{download_id} - Get download result (fully tagged file!)
- GET /api/metadata/{download_id} - Get track metadata JSON
- GET /health - Health check
- DELETE /api/download/{download_id} - Cancel download

Based on: SERVER_MIGRATION_PLAN.md - Days 8-10
"""

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
import uvicorn

from core.spotify_client import SpotifyClient
from core.youtube_searcher import YouTubeMusicSearcher
from core.pytube_downloader import PyTubeDownloader
from core.downloader import TrackDownloader
from core.metadata_writer import MetadataWriter
from core.progress_tracker import ProgressTracker
from core.lyrics_fetcher import LyricsFetcher
from core.deezer_enrichment import DeezerEnrichment
from core.musicbrainz_enrichment import MusicBrainzEnrichment
from core.lastfm_enrichment import LastFmEnrichment
from config import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    GENIUS_TOKEN,
    OUTPUT_DIR,
    CLEANUP_AFTER_MINUTES
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Spotify Track Downloader Server",
    description="Download Spotify tracks with full metadata enrichment",
    version="1.0.0"
)

# Initialize components
spotify_client = SpotifyClient(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
youtube_searcher = YouTubeMusicSearcher()
pytube_downloader = PyTubeDownloader()
track_downloader = TrackDownloader(OUTPUT_DIR)
metadata_writer = MetadataWriter()
progress_tracker = ProgressTracker()

# Metadata enrichment services (initialized on startup)
lyrics_fetcher = None
deezer = None
musicbrainz = None
lastfm = None

# Store download results: download_id -> {file_path, metadata, status}
download_results: Dict[str, Dict] = {}

# Active downloads: download_id -> task
active_downloads: Dict[str, asyncio.Task] = {}

# Download deduplication cache: spotify_track_id -> (file_path, timestamp)
from datetime import timedelta
download_cache: Dict[str, tuple[Path, datetime]] = {}
CACHE_DURATION = timedelta(hours=24)


# ============================================================================
# Helper Functions
# ============================================================================

async def get_cached_download(spotify_track_id: str) -> Optional[Path]:
    """Check if track was downloaded in last 24 hours"""
    if spotify_track_id not in download_cache:
        return None
    
    file_path, timestamp = download_cache[spotify_track_id]
    age = datetime.now() - timestamp
    
    if age > CACHE_DURATION:
        # Cache expired
        del download_cache[spotify_track_id]
        return None
    
    if file_path.exists():
        logger.info(f"📦 Cache hit for {spotify_track_id} (age: {age.total_seconds()/3600:.1f}h)")
        return file_path
    else:
        # File was deleted
        del download_cache[spotify_track_id]
        return None


async def cache_download(spotify_track_id: str, file_path: Path):
    """Cache successful download"""
    download_cache[spotify_track_id] = (file_path, datetime.now())
    logger.info(f"📦 Cached download for {spotify_track_id}")


# ============================================================================
# Request/Response Models
# ============================================================================

class DownloadRequest(BaseModel):
    """Request to download a Spotify track"""
    spotify_track_id: str
    prefer_synced_lyrics: bool = True
    high_quality_cover: bool = True  # Use Deezer 1000x1000 if available


class CustomUrlDownloadRequest(BaseModel):
    """Request to download from a custom YouTube URL (for wrong song replacement)"""
    youtube_url: str
    spotify_track_id: Optional[str] = None  # Optional: for metadata enrichment
    prefer_synced_lyrics: bool = True
    high_quality_cover: bool = True


class DownloadResponse(BaseModel):
    """Response when download is started"""
    download_id: str
    status: str
    message: str


class MetadataResponse(BaseModel):
    """Track metadata response"""
    download_id: str
    track_id: str
    title: str
    artists: list
    album: str
    duration_ms: int
    isrc: Optional[str] = None
    file_size_bytes: Optional[int] = None
    lyrics_source: Optional[str] = None
    lyrics_synced: Optional[bool] = None
    enrichment: Optional[dict] = None


# ============================================================================
# Background Download Task
# ============================================================================

async def _download_task(
    download_id: str,
    spotify_track_id: str,
    prefer_synced_lyrics: bool,
    high_quality_cover: bool
):
    """
    Background task for downloading and enriching a track.
    
    Workflow:
    1. [0-5%] Fetch Spotify metadata
    2. [5-10%] Enrich with Deezer (artist image, album cover)
    3. [10-15%] Enrich with MusicBrainz (ISRC verification, aliases)
    4. [15-20%] Enrich with Last.fm (play counts, genres)
    5. [20-30%] Search YouTube Music
    6. [30-70%] Download audio
    7. [70-75%] Convert to M4A
    8. [75-85%] Fetch lyrics
    9. [85-95%] Write metadata (all enrichments)
    10. [95-100%] Organize file
    """
    try:
        await progress_tracker.start_download(download_id)
        
        # Step 0: Check cache for deduplication (24-hour TTL)
        cached_file = await get_cached_download(spotify_track_id)
        if cached_file:
            logger.info(f"🎯 [{download_id}] Cache hit! Returning existing file")
            await progress_tracker.set_progress(download_id, 100, "Retrieved from cache")
            
            # Fetch minimal Spotify metadata for API response
            metadata = spotify_client.get_track_metadata(spotify_track_id)
            
            # Store result with full metadata for API compatibility
            download_results[download_id] = {
                'file_path': str(cached_file),
                'metadata': {
                    'track_id': spotify_track_id,
                    'title': metadata['title'],
                    'artists': metadata['artists'],
                    'album': metadata['album'],
                    'duration_ms': metadata['duration_ms'],
                    'isrc': metadata.get('isrc'),
                    'file_size_bytes': cached_file.stat().st_size,
                    'cached': True
                },
                'status': 'completed',
                'completed_at': datetime.now().isoformat()
            }
            
            await progress_tracker.complete_download(download_id, success=True)
            return
        
        # Step 1: Fetch Spotify metadata
        await progress_tracker.set_progress(download_id, 2, "Fetching Spotify metadata...")
        logger.info(f"🎵 [{download_id}] Fetching Spotify metadata for {spotify_track_id}")
        
        metadata = spotify_client.get_track_metadata(spotify_track_id)
        if not metadata:
            raise Exception("Failed to fetch Spotify metadata")
        
        track_name = metadata['title']
        artist_name = metadata['artists'][0] if metadata['artists'] else "Unknown"
        album_name = metadata['album']
        duration_seconds = metadata['duration_ms'] // 1000
        isrc = metadata.get('isrc')
        album_art_url = metadata.get('album_art_url')
        
        await progress_tracker.set_progress(download_id, 5, f"Found: {track_name} by {artist_name}")
        
        # Step 2: Deezer enrichment
        await progress_tracker.set_progress(download_id, 7, "Enriching with Deezer...")
        logger.info(f"🖼️ [{download_id}] Fetching Deezer data")
        
        deezer_cover = None
        deezer_artist_image = None
        deezer_genres = []
        
        if high_quality_cover:
            # Try to get higher quality album cover from Deezer (1000x1000)
            deezer_cover = await deezer.get_album_cover(artist_name, album_name, size='xl')
            if deezer_cover:
                logger.info(f"✅ Deezer: Found 1000x1000 album cover")
                album_art_url = deezer_cover  # Use Deezer cover instead
        
        # Get artist image
        deezer_artist_image = await deezer.get_artist_image(artist_name, size='xl')
        
        # Get genres
        deezer_genres = await deezer.get_artist_genres(artist_name)
        
        await progress_tracker.set_progress(download_id, 10, "Deezer enrichment complete")
        
        # Step 3: MusicBrainz enrichment
        await progress_tracker.set_progress(download_id, 12, "Enriching with MusicBrainz...")
        logger.info(f"🔍 [{download_id}] Fetching MusicBrainz data")
        
        mb_isrc = None
        mb_aliases = []
        
        # Verify ISRC
        if isrc:
            mb_isrc = await musicbrainz.verify_track_isrc(track_name, artist_name, expected_isrc=isrc)
        else:
            mb_isrc = await musicbrainz.verify_track_isrc(track_name, artist_name)
        
        # Get artist aliases
        mb_aliases = await musicbrainz.find_artist_aliases(artist_name)
        
        await progress_tracker.set_progress(download_id, 15, "MusicBrainz enrichment complete")
        
        # Step 4: Last.fm enrichment (genres only)
        await progress_tracker.set_progress(download_id, 17, "Enriching with Last.fm...")
        logger.info(f"📊 [{download_id}] Fetching Last.fm genres")
        
        lastfm_genres = []
        
        # Get genres only (no stats needed - stats are for app display, not metadata)
        lastfm_genres = await lastfm.get_artist_genres(artist_name)
        
        await progress_tracker.set_progress(download_id, 20, "Last.fm enrichment complete")
        
        # Step 5: Search YouTube Music
        await progress_tracker.set_progress(download_id, 22, "Searching YouTube Music...")
        logger.info(f"🔎 [{download_id}] Searching YouTube for {track_name}")
        
        youtube_result = youtube_searcher.search(
            track_name=track_name,
            artist_name=artist_name,
            duration_seconds=duration_seconds
        )
        
        if not youtube_result:
            raise Exception("No YouTube Music match found")
        
        youtube_url = youtube_result['url']
        youtube_score = youtube_result['score']
        
        await progress_tracker.set_progress(
            download_id, 
            30, 
            f"YouTube match found (score: {youtube_score}/200)"
        )
        
        # Step 6-10: Download using downloader (tries PyTube first, then yt-dlp fallbacks)
        await progress_tracker.set_progress(download_id, 35, "Downloading audio from YouTube...")
        logger.info(f"📥 [{download_id}] Downloading: {youtube_url}")
        
        # Download using downloader._download_audio (has yt-dlp fallbacks)
        temp_output = OUTPUT_DIR / f"temp_{download_id}"
        temp_output.mkdir(exist_ok=True)
        
        # Create progress callback wrapper
        def download_progress(percent, message):
            loop = asyncio.get_event_loop()
            loop.create_task(progress_tracker.set_progress(download_id, percent, message))
        
        # Use downloader's _download_audio which has pytubefix + yt-dlp fallbacks
        audio_file = track_downloader._download_audio(
            youtube_url,
            f"{metadata['title']}",
            metadata['artists'][0],
            download_progress
        )
        
        if not audio_file or not audio_file.exists():
            raise Exception("Audio download failed - all methods exhausted")
        
        await progress_tracker.set_progress(download_id, 70, f"Downloaded: {audio_file.name}")
        logger.info(f"📦 Downloaded: {audio_file.name} ({audio_file.stat().st_size:,} bytes)")
        
        # Step 7: Convert MP4 to M4A if needed
        if audio_file.suffix.lower() == '.mp4':
            await progress_tracker.set_progress(download_id, 72, "Converting MP4 to M4A...")
            import subprocess
            
            m4a_file = audio_file.with_suffix('.m4a')
            result = subprocess.run(
                ['ffmpeg', '-i', str(audio_file), '-c', 'copy', '-y', str(m4a_file)],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0 and m4a_file.exists():
                audio_file.unlink()  # Delete MP4
                audio_file = m4a_file
                logger.info(f"✅ Converted to M4A: {m4a_file.name}")
            else:
                logger.warning(f"⚠️ FFmpeg conversion failed, keeping MP4")
        
        await progress_tracker.set_progress(download_id, 75, "Fetching lyrics...")
        
        # Step 8: Fetch lyrics
        logger.info(f"📝 [{download_id}] Fetching lyrics")
        
        lyrics_result = await lyrics_fetcher.fetch_lyrics(
            track_name=track_name,
            artist_name=artist_name,
            album_name=album_name,
            duration_seconds=duration_seconds,
            prefer_synced=prefer_synced_lyrics
        )
        
        lyrics_text = None
        lyrics_synced = False
        lyrics_source = None
        
        if lyrics_result:
            lyrics_text = lyrics_result['lyrics']
            lyrics_synced = lyrics_result['synced']
            lyrics_source = lyrics_result['source']
            logger.info(f"✅ Lyrics found: {lyrics_source} (synced: {lyrics_synced})")
        
        await progress_tracker.set_progress(download_id, 85, "Writing metadata...")
        
        # Step 9: Write all metadata (including enrichments)
        logger.info(f"✏️ [{download_id}] Writing enriched metadata")
        
        # Prepare enriched metadata
        enriched_metadata = {
            'title': track_name,
            'artist': artist_name,
            'artists': metadata['artists'],
            'album': album_name,
            'track_number': metadata.get('track_number'),
            'disc_number': metadata.get('disc_number'),
            'date': metadata.get('release_date'),
            'genre': ', '.join(lastfm_genres[:3]) if lastfm_genres else None,
            'isrc': mb_isrc or isrc,
            'album_type': metadata.get('album_type'),
            'album_art_url': deezer_cover or album_art_url  # Use Deezer 1000x1000 if available, else Spotify
        }
        
        # Write metadata with album art and lyrics
        logger.info(f"🔍 DEBUG: Calling write_metadata with audio_file={audio_file}, metadata keys={list(enriched_metadata.keys())}")
        metadata_writer.write_metadata(
            audio_file=audio_file,
            metadata=enriched_metadata,
            lyrics=lyrics_text
        )
        
        await progress_tracker.set_progress(download_id, 95, "Organizing file...")
        
        # Step 10: Organize file into proper directory structure
        final_dir = OUTPUT_DIR / artist_name / album_name
        final_dir.mkdir(parents=True, exist_ok=True)
        
        # Build filename: TrackNumber - Title.m4a
        track_num = metadata.get('track_number')
        if track_num:
            filename = f"{track_num:02d} - {track_name}.m4a"
        else:
            filename = f"{track_name}.m4a"
        
        # Sanitize filename (remove invalid characters)
        filename = filename.replace('/', '-').replace('\\', '-').replace(':', '-')
        filename = filename.replace('*', '').replace('?', '').replace('"', "'")
        filename = filename.replace('<', '').replace('>', '').replace('|', '')
        
        output_file = final_dir / filename
        
        # Move file to final location (replace if exists)
        if output_file.exists():
            output_file.unlink()  # Delete existing file
        audio_file.rename(output_file)
        
        # Clean up temp directory
        try:
            temp_output.rmdir()
        except:
            pass  # Directory might not be empty or already deleted
        
        file_size = output_file.stat().st_size
        
        logger.info(f"✅ [{download_id}] Download complete: {output_file.name} ({file_size:,} bytes)")
        
        # Store result
        download_results[download_id] = {
            'file_path': str(output_file),
            'metadata': {
                'track_id': spotify_track_id,
                'title': track_name,
                'artists': metadata['artists'],
                'album': album_name,
                'duration_ms': metadata['duration_ms'],
                'isrc': mb_isrc or isrc,
                'file_size_bytes': file_size,
                'lyrics_source': lyrics_source,
                'lyrics_synced': lyrics_synced,
                'enrichment': {
                    'deezer': {
                        'cover_url': deezer_cover,
                        'artist_image_url': deezer_artist_image,
                        'genres': deezer_genres
                    },
                    'musicbrainz': {
                        'isrc_verified': mb_isrc is not None,
                        'artist_aliases': mb_aliases
                    },
                    'lastfm': {
                        'genres': lastfm_genres  # Only genres - stats are for app UI, not embedded
                    },
                    'youtube': {
                        'url': youtube_url,
                        'score': youtube_score
                    }
                }
            },
            'status': 'completed',
            'completed_at': datetime.now().isoformat()
        }
        
        # Cache download for 24 hours
        await cache_download(spotify_track_id, output_file)
        
        await progress_tracker.complete_download(download_id, success=True)
        
    except Exception as e:
        logger.error(f"❌ [{download_id}] Download failed: {e}")
        import traceback
        traceback.print_exc()
        
        download_results[download_id] = {
            'status': 'failed',
            'error': str(e),
            'completed_at': datetime.now().isoformat()
        }
        
        await progress_tracker.complete_download(download_id, success=False, error=str(e))
    
    finally:
        # Remove from active downloads
        if download_id in active_downloads:
            del active_downloads[download_id]


async def _download_custom_url_task(
    download_id: str,
    youtube_url: str,
    spotify_track_id: Optional[str],
    prefer_synced_lyrics: bool,
    high_quality_cover: bool
):
    """
    Background task for downloading from a custom YouTube URL.
    Used for "Wrong Song?" replacement feature.
    
    If spotify_track_id is provided, enriches with Spotify metadata.
    Otherwise, extracts metadata from YouTube video info.
    """
    try:
        await progress_tracker.set_progress(download_id, 0, "Starting custom URL download...")
        logger.info(f"🔗 [{download_id}] Custom URL download: {youtube_url}")
        
        # Step 1: Get metadata (from Spotify if provided, otherwise from YouTube)
        metadata = {}
        album_art_url = None
        
        if spotify_track_id:
            # Use Spotify metadata
            await progress_tracker.set_progress(download_id, 5, "Fetching Spotify metadata...")
            spotify_metadata = await spotify_client.get_track_metadata(spotify_track_id)
            
            metadata = {
                'title': spotify_metadata['name'],
                'artists': [artist['name'] for artist in spotify_metadata['artists']],
                'album': spotify_metadata['album']['name'],
                'track_number': spotify_metadata['track_number'],
                'duration_ms': spotify_metadata['duration_ms'],
                'release_date': spotify_metadata['album'].get('release_date'),
                'isrc': spotify_metadata.get('external_ids', {}).get('isrc')
            }
            
            album_art_url = spotify_metadata['album']['images'][0]['url'] if spotify_metadata['album']['images'] else None
            
            # Enrich with Deezer/MusicBrainz/Last.fm if available
            if high_quality_cover and deezer:
                deezer_cover = await deezer.get_album_cover(
                    metadata['artists'][0],
                    metadata['album'],
                    size='xl'
                )
                if deezer_cover:
                    album_art_url = deezer_cover
            
            await progress_tracker.set_progress(download_id, 15, "Metadata enrichment complete")
        else:
            # Extract basic metadata from YouTube (title/artist from video title)
            await progress_tracker.set_progress(download_id, 5, "Extracting metadata from YouTube...")
            # This will be filled by pytube video info
            metadata = {
                'title': 'Unknown Title',
                'artists': ['Unknown Artist'],
                'album': 'Unknown Album',
                'track_number': 1,
                'duration_ms': 0
            }
            await progress_tracker.set_progress(download_id, 15, "Using YouTube video metadata")
        
        # Step 2: Download audio
        await progress_tracker.set_progress(download_id, 20, "Downloading audio from YouTube...")
        
        temp_output = OUTPUT_DIR / f"temp_{download_id}"
        temp_output.mkdir(exist_ok=True)
        
        def download_progress(percent, message):
            loop = asyncio.get_event_loop()
            loop.create_task(progress_tracker.set_progress(download_id, percent, message))
        
        audio_file = pytube_downloader.download_audio(
            youtube_url,
            temp_output,
            f"{metadata['title']} - {metadata['artists'][0]}",
            download_progress
        )
        
        if not audio_file or not audio_file.exists():
            raise Exception("Audio download failed from custom URL")
        
        await progress_tracker.set_progress(download_id, 70, f"Downloaded: {audio_file.name}")
        
        # Step 3: Convert to M4A if needed
        if audio_file.suffix.lower() == '.mp4':
            await progress_tracker.set_progress(download_id, 72, "Converting to M4A...")
            import subprocess
            
            m4a_file = audio_file.with_suffix('.m4a')
            result = subprocess.run(
                ['ffmpeg', '-i', str(audio_file), '-c', 'copy', '-y', str(m4a_file)],
                capture_output=True
            )
            
            if result.returncode == 0 and m4a_file.exists():
                audio_file.unlink()
                audio_file = m4a_file
        
        await progress_tracker.set_progress(download_id, 75, "Writing metadata...")
        
        # Step 4: Write metadata tags
        if album_art_url:
            import requests
            album_art_data = requests.get(album_art_url).content
        else:
            album_art_data = None
        
        lyrics_text = None
        lyrics_source = None
        lyrics_synced = False
        
        # Try to fetch lyrics if we have Spotify metadata
        if spotify_track_id and lyrics_fetcher and prefer_synced_lyrics:
            await progress_tracker.set_progress(download_id, 78, "Fetching lyrics...")
            lyrics_result = await lyrics_fetcher.fetch_lyrics(
                track_name=metadata['title'],
                artist_name=metadata['artists'][0],
                duration_seconds=metadata.get('duration_ms', 0) // 1000,
                isrc=metadata.get('isrc')
            )
            
            if lyrics_result:
                lyrics_text = lyrics_result['lyrics']
                lyrics_source = lyrics_result['source']
                lyrics_synced = lyrics_result['synced']
        
        await progress_tracker.set_progress(download_id, 85, "Writing tags to audio file...")
        
        metadata_writer.write_metadata(
            audio_file=audio_file,
            title=metadata['title'],
            artists=metadata['artists'],
            album=metadata['album'],
            track_number=metadata.get('track_number', 1),
            release_date=metadata.get('release_date'),
            isrc=metadata.get('isrc'),
            album_art_data=album_art_data,
            lyrics=lyrics_text
        )
        
        # Step 5: Move to final location
        await progress_tracker.set_progress(download_id, 95, "Finalizing...")
        
        safe_filename = "".join(c for c in f"{metadata['title']} - {metadata['artists'][0]}" if c.isalnum() or c in (' ', '-', '_')).rstrip()
        output_file = OUTPUT_DIR / f"{safe_filename}.m4a"
        
        # Handle duplicates
        counter = 1
        while output_file.exists():
            output_file = OUTPUT_DIR / f"{safe_filename}_{counter}.m4a"
            counter += 1
        
        import shutil
        shutil.move(str(audio_file), str(output_file))
        
        # Cleanup temp directory
        if temp_output.exists():
            shutil.rmtree(temp_output, ignore_errors=True)
        
        await progress_tracker.set_progress(download_id, 100, "Complete!")
        
        # Store results
        download_results[download_id] = {
            'status': 'completed',
            'file_path': str(output_file),
            'file_size': output_file.stat().st_size,
            'metadata': metadata,
            'lyrics_source': lyrics_source,
            'lyrics_synced': lyrics_synced,
            'completed_at': datetime.now().isoformat()
        }
        
        logger.info(f"✅ [{download_id}] Custom URL download complete: {output_file}")
        
        await progress_tracker.complete_download(download_id, success=True)
        
    except Exception as e:
        logger.error(f"❌ [{download_id}] Custom URL download failed: {e}")
        import traceback
        traceback.print_exc()
        
        download_results[download_id] = {
            'status': 'failed',
            'error': str(e),
            'completed_at': datetime.now().isoformat()
        }
        
        await progress_tracker.complete_download(download_id, success=False, error=str(e))
    
    finally:
        if download_id in active_downloads:
            del active_downloads[download_id]


# ============================================================================
# API Endpoints
# ============================================================================

@app.post("/api/download", response_model=DownloadResponse)
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks):
    """
    Start downloading a Spotify track with FULL metadata enrichment.
    
    Server processes:
    - Spotify metadata (title, artists, album, track number)
    - Deezer enrichment (1000x1000 album cover, artist image, genres)
    - MusicBrainz enrichment (ISRC verification, artist aliases)
    - Last.fm enrichment (play counts, genres)
    - YouTube Music search (superior algorithm)
    - Audio download (PyTube + yt-dlp fallback)
    - Lyrics (LrcLib → Genius → Musixmatch)
    - Metadata writing (all fields + album art + lyrics)
    
    Returns download_id for tracking progress.
    """
    download_id = str(uuid.uuid4())
    
    logger.info(f"🚀 New download request: {request.spotify_track_id} -> {download_id}")
    
    # Start background task
    task = asyncio.create_task(
        _download_task(
            download_id,
            request.spotify_track_id,
            request.prefer_synced_lyrics,
            request.high_quality_cover
        )
    )
    
    active_downloads[download_id] = task
    
    return DownloadResponse(
        download_id=download_id,
        status="processing",
        message=f"Download started for track {request.spotify_track_id}"
    )


@app.post("/api/download/custom-url", response_model=DownloadResponse)
async def start_custom_url_download(request: CustomUrlDownloadRequest, background_tasks: BackgroundTasks):
    """
    Start downloading from a custom YouTube/YouTube Music URL.
    
    Used for "Wrong Song?" replacement feature in the app.
    
    If spotify_track_id is provided:
    - Fetches Spotify metadata
    - Enriches with Deezer/MusicBrainz/Last.fm
    - Downloads from provided YouTube URL
    - Writes full metadata + lyrics
    
    If no spotify_track_id:
    - Downloads from YouTube URL
    - Extracts metadata from YouTube video info
    - Basic tagging only
    
    Returns download_id for tracking progress.
    """
    download_id = str(uuid.uuid4())
    
    logger.info(f"🔗 New custom URL download: {request.youtube_url} -> {download_id}")
    
    # Start background task
    task = asyncio.create_task(
        _download_custom_url_task(
            download_id,
            request.youtube_url,
            request.spotify_track_id,
            request.prefer_synced_lyrics,
            request.high_quality_cover
        )
    )
    
    active_downloads[download_id] = task
    
    return DownloadResponse(
        download_id=download_id,
        status="processing",
        message=f"Custom URL download started: {request.youtube_url}"
    )


@app.get("/api/progress/{download_id}")
async def progress_stream(download_id: str):
    """
    Server-Sent Events (SSE) stream for real-time progress updates.
    
    Event data format:
    {
        "progress": 0-100,
        "status": "status message",
        "timestamp": "ISO timestamp"
    }
    
    Final event includes:
    {
        "progress": 100,
        "status": "Complete!" or "Failed: error",
        "completed": true,
        "success": true/false,
        "error": "error message" (if failed)
    }
    """
    async def event_generator():
        # Subscribe to progress updates
        queue = await progress_tracker.subscribe(download_id)
        
        try:
            while True:
                # Wait for progress update
                update = await queue.get()
                
                # Send as SSE event (must be JSON string)
                import json
                yield {
                    "data": json.dumps(update)
                }
                
                # Stop if download completed
                if update.get('completed'):
                    break
        
        except asyncio.CancelledError:
            logger.info(f"📡 SSE connection closed for {download_id}")
        
        finally:
            await progress_tracker.unsubscribe(download_id, queue)
    
    return EventSourceResponse(event_generator())


@app.get("/api/download/{download_id}")
async def get_download_result(download_id: str):
    """
    Get the downloaded file.
    
    Returns the fully tagged M4A file with all metadata embedded.
    """
    if download_id not in download_results:
        raise HTTPException(status_code=404, detail="Download not found")
    
    result = download_results[download_id]
    
    if result['status'] == 'failed':
        raise HTTPException(status_code=500, detail=result.get('error', 'Download failed'))
    
    if result['status'] != 'completed':
        raise HTTPException(status_code=425, detail="Download still in progress")
    
    file_path = Path(result['file_path'])
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Return file for download
    return FileResponse(
        path=file_path,
        media_type='audio/mp4',
        filename=file_path.name
    )


@app.get("/api/metadata/{download_id}", response_model=MetadataResponse)
async def get_metadata(download_id: str):
    """
    Get track metadata without downloading the file.
    
    Useful for displaying track info before downloading.
    """
    if download_id not in download_results:
        raise HTTPException(status_code=404, detail="Download not found")
    
    result = download_results[download_id]
    
    if result['status'] == 'failed':
        raise HTTPException(status_code=500, detail=result.get('error', 'Download failed'))
    
    if result['status'] != 'completed':
        raise HTTPException(status_code=425, detail="Download still in progress")
    
    metadata = result['metadata']
    
    return MetadataResponse(
        download_id=download_id,
        **metadata
    )


@app.delete("/api/download/{download_id}")
async def cancel_download(download_id: str):
    """
    Cancel an in-progress download.
    """
    if download_id in active_downloads:
        task = active_downloads[download_id]
        task.cancel()
        del active_downloads[download_id]
        
        await progress_tracker.complete_download(
            download_id, 
            success=False, 
            error="Cancelled by user"
        )
        
        return {"status": "cancelled", "download_id": download_id}
    
    raise HTTPException(status_code=404, detail="Download not found or already completed")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "active_downloads": len(active_downloads),
        "total_downloads": len(download_results),
        "tracker_stats": progress_tracker.get_stats(),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "name": "Spotify Track Downloader Server",
        "version": "1.0.0",
        "description": "Download Spotify tracks with full metadata enrichment",
        "endpoints": {
            "POST /api/download": "Start track download",
            "GET /api/progress/{download_id}": "SSE progress stream",
            "GET /api/download/{download_id}": "Download completed file",
            "GET /api/metadata/{download_id}": "Get track metadata",
            "DELETE /api/download/{download_id}": "Cancel download",
            "POST /api/preview/search": "Search YouTube for preview stream URL (preview player only)",
            "GET /health": "Health check"
        }
    }


@app.post("/api/preview/search")
async def search_preview_url(request: dict):
    """
    Search YouTube Music for a preview stream URL (for app's preview player).
    This is a lightweight endpoint that ONLY returns the audio stream URL,
    NOT a full download with metadata.
    
    Request body:
    {
        "track_name": "Mr. Brightside",
        "artist_name": "The Killers",
        "duration_ms": 223000
    }
    
    Returns:
    {
        "audio_url": "https://...",
        "match_score": 179,
        "video_title": "The Killers - Mr. Brightside (Official Music Video)"
    }
    """
    try:
        track_name = request.get('track_name')
        artist_name = request.get('artist_name')
        duration_ms = request.get('duration_ms', 0)
        
        if not track_name or not artist_name:
            raise HTTPException(status_code=400, detail="Missing track_name or artist_name")
        
        logger.info(f"🎵 Preview search: {track_name} by {artist_name}")
        
        # Use YouTube searcher to find best match
        search_result = await youtube_searcher.search_track(
            track_name=track_name,
            artist_name=artist_name,
            expected_duration_ms=duration_ms
        )
        
        if not search_result:
            logger.warning(f"❌ No preview found for: {track_name}")
            raise HTTPException(status_code=404, detail="No matching video found")
        
        # Extract audio stream URL using PyTube
        video_url = search_result['url']
        audio_url = await pytube_downloader.get_audio_stream_url(video_url)
        
        if not audio_url:
            logger.error(f"❌ Failed to extract audio URL from: {video_url}")
            raise HTTPException(status_code=500, detail="Failed to extract audio stream")
        
        logger.info(f"✅ Preview URL found (score: {search_result['score']})")
        
        return {
            "audio_url": audio_url,
            "match_score": search_result['score'],
            "video_title": search_result['title'],
            "video_url": video_url,
            "duration_seconds": search_result.get('duration', 0)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Preview search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Startup/Shutdown Events
# ============================================================================# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global lyrics_fetcher, deezer, musicbrainz, lastfm
    
    logger.info("🚀 Starting Spotify Track Downloader Server")
    logger.info(f"📁 Output directory: {OUTPUT_DIR}")
    logger.info(f"🧹 File cleanup after: {CLEANUP_AFTER_MINUTES} minutes")
    logger.info(f"📦 Download cache duration: 24 hours")
    
    # Initialize async enrichment services
    lyrics_fetcher = LyricsFetcher(genius_token=GENIUS_TOKEN)
    deezer = DeezerEnrichment()
    musicbrainz = MusicBrainzEnrichment()
    lastfm = LastFmEnrichment()
    
    # Start cleanup task (create task in background)
    loop = asyncio.get_event_loop()
    loop.create_task(cleanup_old_files())
    
    # Start keep-alive task for Render.com (prevents server from sleeping)
    loop.create_task(keep_alive_task())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down server")
    
    # Cancel all active downloads
    for download_id, task in active_downloads.items():
        logger.info(f"Cancelling download: {download_id}")
        task.cancel()
    
    # Close HTTP sessions
    await lyrics_fetcher.close()
    await deezer.close()
    await musicbrainz.close()
    await lastfm.close()


# ============================================================================
# Background Cleanup Task
# ============================================================================

async def cleanup_old_files():
    """
    Delete files older than CLEANUP_AFTER_MINUTES.
    Runs every 5 minutes.
    """
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            
            logger.info("🧹 Running cleanup task")
            
            now = datetime.now()
            to_delete = []
            
            for download_id, result in download_results.items():
                if result['status'] != 'completed':
                    continue
                
                completed_at = datetime.fromisoformat(result['completed_at'])
                age_minutes = (now - completed_at).total_seconds() / 60
                
                if age_minutes > CLEANUP_AFTER_MINUTES:
                    to_delete.append(download_id)
            
            for download_id in to_delete:
                result = download_results[download_id]
                file_path = Path(result['file_path'])
                
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"🗑️ Deleted old file: {file_path.name}")
                
                del download_results[download_id]
            
            # Clean up progress tracker
            await progress_tracker.cleanup_old_downloads(max_age_hours=24)
            
            if to_delete:
                logger.info(f"🧹 Cleanup complete: {len(to_delete)} file(s) deleted")
        
        except Exception as e:
            logger.error(f"Cleanup task error: {e}")


async def keep_alive_task():
    """
    Keep-alive task for Render.com free tier.
    Pings the /health endpoint every 4 minutes to prevent server from going idle.
    
    Render free tier spins down inactive servers after 15 minutes of no requests.
    By pinging every 4 minutes, we ensure the server stays active.
    """
    import aiohttp
    import os
    
    # Only run keep-alive on Render (detect by RENDER environment variable)
    if 'RENDER' not in os.environ:
        logger.info("🏠 Running locally - keep-alive task disabled")
        return
    
    # Get the public URL from Render environment
    render_external_url = os.environ.get('RENDER_EXTERNAL_URL')
    
    if not render_external_url:
        logger.warning("⚠️ RENDER_EXTERNAL_URL not set - keep-alive disabled")
        return
    
    health_url = f"{render_external_url}/health"
    
    logger.info(f"💓 Keep-alive task started - pinging {health_url} every 4 minutes")
    
    # Wait 4 minutes before first ping (server needs time to fully start)
    await asyncio.sleep(240)
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"💓 Keep-alive ping successful - {data.get('active_downloads', 0)} active downloads")
                    else:
                        logger.warning(f"⚠️ Keep-alive ping failed with status {response.status}")
            
            except asyncio.TimeoutError:
                logger.warning("⚠️ Keep-alive ping timed out")
            except Exception as e:
                logger.error(f"❌ Keep-alive ping error: {e}")
            
            # Wait 4 minutes before next ping (240 seconds)
            await asyncio.sleep(240)


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
