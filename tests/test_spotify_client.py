"""
Test Spotify client initialization and basic functionality.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.spotify_client import SpotifyClient
from utils.logger import setup_logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_spotify_client():
    """Test Spotify client with a known track."""
    # Setup logging
    setup_logging("INFO")
    
    # Get credentials from environment
    client_id = os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("❌ ERROR: Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env file")
        return False
    
    try:
        # Initialize client
        print("\n🔧 Initializing Spotify client...")
        client = SpotifyClient(client_id, client_secret)
        
        # Test with "Mr. Brightside" by The Killers
        test_track_id = "3n3Ppam7vgaVa1iaRUc9Lp"
        
        print(f"\n🎵 Fetching metadata for track: {test_track_id}")
        metadata = client.get_track_metadata(test_track_id)
        
        # Display results
        print("\n✅ SUCCESS! Metadata fetched:")
        print(f"  Title: {metadata['title']}")
        print(f"  Artists: {', '.join(metadata['artists'])}")
        print(f"  Album: {metadata['album']}")
        print(f"  Duration: {metadata['duration_ms'] // 1000}s")
        print(f"  Track #: {metadata['track_number']}")
        print(f"  ISRC: {metadata.get('isrc', 'N/A')}")
        print(f"  Album Art: {metadata['album_art_url'][:50]}..." if metadata['album_art_url'] else "  Album Art: None")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_spotify_client()
    sys.exit(0 if success else 1)
