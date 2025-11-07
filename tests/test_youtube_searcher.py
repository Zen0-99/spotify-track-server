"""Test YouTube Music searcher with real tracks."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.youtube_searcher import YouTubeMusicSearcher
from utils.logger import setup_logging

# Configure logging
setup_logging("INFO")


def test_search():
    """Test YouTube Music search with The Killers - Mr. Brightside."""
    
    print("\n" + "="*60)
    print("🎵 Testing YouTube Music Search")
    print("="*60)
    
    # Initialize searcher
    print("\n🔧 Initializing YouTube Music searcher...")
    searcher = YouTubeMusicSearcher()
    
    # Test with Mr. Brightside (we know the metadata from Spotify test)
    track_name = "Mr. Brightside"
    artist_name = "The Killers"
    duration_seconds = 222  # From Spotify metadata
    
    print(f"\n🎤 Searching for: {track_name} by {artist_name}")
    print(f"📏 Expected duration: {duration_seconds}s ({duration_seconds // 60}m {duration_seconds % 60}s)")
    
    result = searcher.search(
        track_name=track_name,
        artist_name=artist_name,
        duration_seconds=duration_seconds,
        max_results=15  # Get more results for better matching
    )
    
    if result:
        print("\n" + "="*60)
        print("✅ SUCCESS! Found matching video:")
        print("="*60)
        print(f"  Title: {result['title']}")
        print(f"  URL: {result['url']}")
        print(f"  Uploader: {result['uploader']}")
        print(f"  Duration: {result['duration']}s ({result['duration'] // 60}m {result['duration'] % 60}s)")
        print(f"  Views: {result['view_count']:,}" if result['view_count'] else "  Views: Unknown")
        print(f"  Score: {result['score']}/200+ points")
        print(f"  Duration diff: {abs(result['duration'] - duration_seconds)}s")
        print("="*60)
        
        # Validate result
        if result['score'] >= 100:
            print("\n✅ EXCELLENT match (score >= 100)")
        elif result['score'] >= 70:
            print("\n⚠️ ACCEPTABLE match (score >= 70)")
        else:
            print("\n❌ LOW CONFIDENCE match (score < 70)")
        
        return True
    else:
        print("\n❌ FAILED: No suitable match found")
        return False


if __name__ == "__main__":
    try:
        success = test_search()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
