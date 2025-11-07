"""Test complete download workflow."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.spotify_client import SpotifyClient
from core.downloader import TrackDownloader
from utils.logger import setup_logging
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

# Configure logging
setup_logging("INFO")


def progress_callback(percent: int, message: str):
    """Display progress updates."""
    bar_length = 40
    filled_length = int(bar_length * percent / 100)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    print(f"\r[{bar}] {percent:3d}% - {message}", end='', flush=True)
    if percent == 100 or percent == 0:
        print()  # New line when complete or failed


def test_download():
    """Test full download workflow with Mr. Brightside."""
    
    print("\n" + "="*60)
    print("🎵 Testing Complete Download Workflow")
    print("="*60)
    
    # Initialize components
    print("\n🔧 Initializing components...")
    spotify = SpotifyClient(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
    downloader = TrackDownloader(spotify)
    
    print("✅ Components initialized")
    
    # Test download (Mr. Brightside)
    track_id = "3n3Ppam7vgaVa1iaRUc9Lp"  # The Killers - Mr. Brightside
    
    print(f"\n📥 Downloading track: {track_id}")
    print("-" * 60)
    
    result = downloader.download_track(
        track_id=track_id,
        progress_callback=progress_callback,
        include_lyrics=True
    )
    
    if result:
        print("\n" + "="*60)
        print("✅ SUCCESS! Track downloaded:")
        print("="*60)
        print(f"  Location: {result}")
        print(f"  Size: {result.stat().st_size / 1024 / 1024:.2f} MB")
        print("="*60)
        
        # Verify file exists
        if result.exists():
            print("\n✅ File verified on disk")
            
            # Check metadata
            from mutagen.mp4 import MP4
            audio = MP4(result)
            
            print("\n📋 Embedded metadata:")
            title_key = '\xa9nam'
            artist_key = '\xa9ART'
            album_key = '\xa9alb'
            lyrics_key = '\xa9lyr'
            
            print(f"  Title: {audio.get(title_key, ['N/A'])[0]}")
            print(f"  Artist: {audio.get(artist_key, ['N/A'])[0]}")
            print(f"  Album: {audio.get(album_key, ['N/A'])[0]}")
            
            if audio.get('covr'):
                print(f"  Album art: ✅ Embedded ({len(audio['covr'][0])} bytes)")
            else:
                print("  Album art: ❌ Missing")
            
            if audio.get(lyrics_key):
                lyrics_length = len(audio[lyrics_key][0])
                print(f"  Lyrics: ✅ Embedded ({lyrics_length} chars)")
            else:
                print("  Lyrics: ⚠️ Not found")
            
            return True
        else:
            print("\n❌ File not found on disk!")
            return False
    else:
        print("\n❌ FAILED: Download did not complete")
        return False


if __name__ == "__main__":
    try:
        success = test_download()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
