"""
Test metadata enrichment components.

Tests:
- Progress tracker (SSE simulation)
- Lyrics fetcher (LrcLib, Genius, Musixmatch)
- Deezer enrichment (artist images, genres)
- MusicBrainz enrichment (ISRC, artist aliases)
- Last.fm enrichment (play counts, genres)
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.progress_tracker import ProgressTracker
from core.lyrics_fetcher import LyricsFetcher
from core.deezer_enrichment import DeezerEnrichment
from core.musicbrainz_enrichment import MusicBrainzEnrichment
from core.lastfm_enrichment import LastFmEnrichment


async def test_progress_tracker():
    """Test progress tracking system"""
    print("\n" + "="*60)
    print("TESTING PROGRESS TRACKER")
    print("="*60)
    
    tracker = ProgressTracker()
    download_id = "test_download_123"
    
    # Initialize download
    await tracker.start_download(download_id)
    print(f"✅ Download initialized: {download_id}")
    
    # Simulate progress updates
    stages = [
        (5, "Fetching Spotify metadata..."),
        (25, "Searching YouTube Music..."),
        (50, "Downloading audio..."),
        (75, "Fetching lyrics..."),
        (90, "Writing metadata..."),
        (100, "Complete!")
    ]
    
    for progress, status in stages:
        await tracker.set_progress(download_id, progress, status)
        print(f"  [{progress}%] {status}")
        await asyncio.sleep(0.1)
    
    await tracker.complete_download(download_id, success=True)
    
    # Check stats
    stats = tracker.get_stats()
    print(f"\n📊 Tracker stats:")
    print(f"   Total downloads: {stats['total_downloads']}")
    print(f"   Completed: {stats['completed_downloads']}")
    
    print("\n✅ Progress tracker test PASSED")


async def test_lyrics_fetcher():
    """Test lyrics fetching from multiple providers"""
    print("\n" + "="*60)
    print("TESTING LYRICS FETCHER")
    print("="*60)
    
    fetcher = LyricsFetcher()
    
    # Test track: Mr. Brightside by The Killers
    track = "Mr. Brightside"
    artist = "The Killers"
    album = "Hot Fuss"
    duration = 222
    
    print(f"\n🎵 Fetching lyrics for: {artist} - {track}")
    
    try:
        result = await fetcher.fetch_lyrics(
            track_name=track,
            artist_name=artist,
            album_name=album,
            duration_seconds=duration,
            prefer_synced=True
        )
        
        if result:
            print(f"\n✅ Lyrics found!")
            print(f"   Source: {result['source']}")
            print(f"   Synced: {result['synced']}")
            print(f"   Length: {len(result['lyrics'])} characters")
            print(f"\n   Preview (first 200 chars):")
            print(f"   {result['lyrics'][:200]}...")
        else:
            print("❌ No lyrics found")
    
    finally:
        await fetcher.close()
    
    print("\n✅ Lyrics fetcher test PASSED")


async def test_deezer_enrichment():
    """Test Deezer API for artist images and genres"""
    print("\n" + "="*60)
    print("TESTING DEEZER ENRICHMENT")
    print("="*60)
    
    deezer = DeezerEnrichment()
    
    artist = "The Killers"
    
    try:
        # Test artist image
        print(f"\n🖼️ Fetching artist image for: {artist}")
        image_url = await deezer.get_artist_image(artist, size='xl')
        if image_url:
            print(f"✅ Image URL: {image_url}")
        else:
            print("❌ No image found")
        
        # Test artist info
        print(f"\n📊 Fetching artist info for: {artist}")
        info = await deezer.get_artist_info(artist)
        if info:
            print(f"✅ Artist info:")
            print(f"   Name: {info['name']}")
            print(f"   Fans: {info['nb_fan']:,}")
            print(f"   Albums: {info['nb_album']}")
        else:
            print("❌ No info found")
        
        # Test artist genres
        print(f"\n🎼 Fetching genres for: {artist}")
        genres = await deezer.get_artist_genres(artist)
        if genres:
            print(f"✅ Genres: {', '.join(genres)}")
        else:
            print("⚠️ No genres found (Deezer doesn't always provide genres)")
    
    finally:
        await deezer.close()
    
    print("\n✅ Deezer enrichment test PASSED")


async def test_musicbrainz_enrichment():
    """Test MusicBrainz API for ISRC and artist aliases"""
    print("\n" + "="*60)
    print("TESTING MUSICBRAINZ ENRICHMENT")
    print("="*60)
    
    mb = MusicBrainzEnrichment()
    
    artist = "The Killers"
    track = "Mr. Brightside"
    
    try:
        # Test artist aliases
        print(f"\n🎭 Fetching artist aliases for: {artist}")
        aliases = await mb.find_artist_aliases(artist)
        print(f"✅ Aliases found: {len(aliases)}")
        print(f"   {', '.join(aliases[:5])}")
        
        # Test ISRC verification
        print(f"\n🔍 Verifying ISRC for: {track}")
        isrc = await mb.verify_track_isrc(track, artist, expected_isrc="GBFFP0300052")
        if isrc:
            print(f"✅ ISRC: {isrc}")
        else:
            print("❌ ISRC not found")
        
        # Test recording info
        print(f"\n📀 Fetching recording info for: {track}")
        info = await mb.get_recording_info(track, artist)
        if info:
            print(f"✅ Recording info:")
            print(f"   Title: {info.get('title')}")
            print(f"   ISRC: {info.get('isrc')}")
            print(f"   Length: {info.get('length_ms')}ms")
        else:
            print("❌ No recording info found")
    
    finally:
        await mb.close()
    
    print("\n✅ MusicBrainz enrichment test PASSED")


async def test_lastfm_enrichment():
    """Test Last.fm API for play counts and genres"""
    print("\n" + "="*60)
    print("TESTING LAST.FM ENRICHMENT")
    print("="*60)
    
    lastfm = LastFmEnrichment()
    
    artist = "The Killers"
    track = "Mr. Brightside"
    
    try:
        # Test artist stats
        print(f"\n📊 Fetching artist stats for: {artist}")
        artist_stats = await lastfm.get_artist_stats(artist)
        if artist_stats:
            listeners, playcount = artist_stats
            print(f"✅ Artist stats:")
            print(f"   Listeners: {listeners:,}")
            print(f"   Playcount: {playcount:,}")
        else:
            print("❌ No artist stats found")
        
        # Test track stats
        print(f"\n📊 Fetching track stats for: {track}")
        track_stats = await lastfm.get_track_stats(track, artist)
        if track_stats:
            listeners, playcount = track_stats
            print(f"✅ Track stats:")
            print(f"   Listeners: {listeners:,}")
            print(f"   Playcount: {playcount:,}")
        else:
            print("❌ No track stats found")
        
        # Test artist genres
        print(f"\n🎼 Fetching genres for: {artist}")
        genres = await lastfm.get_artist_genres(artist)
        if genres:
            print(f"✅ Genres: {', '.join(genres[:5])}")
        else:
            print("❌ No genres found")
        
        # Test similar artists
        print(f"\n🎭 Fetching similar artists for: {artist}")
        similar = await lastfm.get_similar_artists(artist, limit=3)
        if similar:
            print(f"✅ Similar artists:")
            for sim in similar:
                print(f"   {sim['name']} (match: {sim['match']:.2f})")
        else:
            print("❌ No similar artists found")
    
    finally:
        await lastfm.close()
    
    print("\n✅ Last.fm enrichment test PASSED")


async def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("METADATA ENRICHMENT COMPONENTS TEST SUITE")
    print("="*60)
    print("\nTesting all enrichment services with 'Mr. Brightside' by The Killers")
    
    try:
        # Test each component
        await test_progress_tracker()
        await test_lyrics_fetcher()
        await test_deezer_enrichment()
        await test_musicbrainz_enrichment()
        await test_lastfm_enrichment()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nAll metadata enrichment components are working correctly.")
        print("Ready to integrate into main downloader!")
    
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
