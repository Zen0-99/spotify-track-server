"""
Test the FastAPI server endpoints.

Tests:
1. Health check
2. Start download
3. Monitor progress (SSE)
4. Get metadata
5. Download file
"""

import asyncio
import aiohttp
import sys
import json
from pathlib import Path

SERVER_URL = "http://localhost:8000"


async def test_health_check():
    """Test health endpoint"""
    print("\n" + "="*60)
    print("TEST 1: Health Check")
    print("="*60)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{SERVER_URL}/health") as response:
            if response.status == 200:
                data = await response.json()
                print("✅ Server is healthy")
                print(f"   Active downloads: {data['active_downloads']}")
                print(f"   Total downloads: {data['total_downloads']}")
                print(f"   Tracker stats: {data['tracker_stats']}")
                return True
            else:
                print(f"❌ Health check failed: {response.status}")
                return False


async def test_start_download(track_id: str = "3n3Ppam7vgaVa1iaRUc9Lp"):
    """Test starting a download"""
    print("\n" + "="*60)
    print("TEST 2: Start Download")
    print("="*60)
    print(f"Track ID: {track_id} (Mr. Brightside)")
    
    async with aiohttp.ClientSession() as session:
        payload = {
            "spotify_track_id": track_id,
            "prefer_synced_lyrics": True,
            "high_quality_cover": True
        }
        
        async with session.post(f"{SERVER_URL}/api/download", json=payload) as response:
            if response.status == 200:
                data = await response.json()
                download_id = data['download_id']
                print(f"✅ Download started")
                print(f"   Download ID: {download_id}")
                print(f"   Status: {data['status']}")
                print(f"   Message: {data['message']}")
                return download_id
            else:
                error = await response.text()
                print(f"❌ Failed to start download: {response.status}")
                print(f"   Error: {error}")
                return None


async def test_progress_stream(download_id: str):
    """Test SSE progress stream"""
    print("\n" + "="*60)
    print("TEST 3: Monitor Progress (SSE)")
    print("="*60)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{SERVER_URL}/api/progress/{download_id}") as response:
            if response.status != 200:
                print(f"❌ Failed to connect to progress stream: {response.status}")
                return False
            
            print("📡 Connected to SSE stream\n")
            
            async for line in response.content:
                line = line.decode('utf-8').strip()
                
                if line.startswith('data: '):
                    data_str = line[6:]  # Remove 'data: ' prefix
                    try:
                        data = json.loads(data_str)
                        progress = data.get('progress', 0)
                        status = data.get('status', '')
                        
                        print(f"[{progress:3d}%] {status}")
                        
                        # Check if completed
                        if data.get('completed'):
                            success = data.get('success', False)
                            if success:
                                print("\n✅ Download completed successfully!")
                            else:
                                error = data.get('error', 'Unknown error')
                                print(f"\n❌ Download failed: {error}")
                            return success
                    
                    except json.JSONDecodeError as e:
                        print(f"⚠️ Failed to parse SSE data: {e}")
            
            return False


async def test_get_metadata(download_id: str):
    """Test getting metadata"""
    print("\n" + "="*60)
    print("TEST 4: Get Metadata")
    print("="*60)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{SERVER_URL}/api/metadata/{download_id}") as response:
            if response.status == 200:
                data = await response.json()
                print("✅ Metadata retrieved")
                print(f"\n   Track Info:")
                print(f"   - Title: {data['title']}")
                print(f"   - Artists: {', '.join(data['artists'])}")
                print(f"   - Album: {data['album']}")
                print(f"   - Duration: {data['duration_ms']}ms")
                print(f"   - ISRC: {data.get('isrc', 'N/A')}")
                print(f"   - File size: {data.get('file_size_bytes', 0):,} bytes")
                
                if data.get('lyrics_source'):
                    print(f"\n   Lyrics:")
                    print(f"   - Source: {data['lyrics_source']}")
                    print(f"   - Synced: {data['lyrics_synced']}")
                
                if data.get('enrichment'):
                    print(f"\n   Enrichment:")
                    enrichment = data['enrichment']
                    
                    # Deezer
                    if enrichment.get('deezer'):
                        deezer = enrichment['deezer']
                        print(f"   - Deezer genres: {', '.join(deezer.get('genres', []))}")
                    
                    # MusicBrainz
                    if enrichment.get('musicbrainz'):
                        mb = enrichment['musicbrainz']
                        print(f"   - ISRC verified: {mb.get('isrc_verified')}")
                        print(f"   - Artist aliases: {len(mb.get('artist_aliases', []))}")
                    
                    # Last.fm
                    if enrichment.get('lastfm'):
                        lastfm = enrichment['lastfm']
                        if lastfm.get('track_stats'):
                            stats = lastfm['track_stats']
                            print(f"   - Track listeners: {stats['listeners']:,}")
                            print(f"   - Track playcount: {stats['playcount']:,}")
                    
                    # YouTube
                    if enrichment.get('youtube'):
                        youtube = enrichment['youtube']
                        print(f"   - YouTube score: {youtube.get('score')}/200")
                
                return True
            
            elif response.status == 425:
                print("⚠️ Download still in progress")
                return False
            else:
                error = await response.text()
                print(f"❌ Failed to get metadata: {response.status}")
                print(f"   Error: {error}")
                return False


async def test_download_file(download_id: str, output_path: str = "test_download.m4a"):
    """Test downloading the file"""
    print("\n" + "="*60)
    print("TEST 5: Download File")
    print("="*60)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{SERVER_URL}/api/download/{download_id}") as response:
            if response.status == 200:
                file_data = await response.read()
                
                Path(output_path).write_bytes(file_data)
                
                print(f"✅ File downloaded")
                print(f"   Path: {output_path}")
                print(f"   Size: {len(file_data):,} bytes")
                
                return True
            
            elif response.status == 425:
                print("⚠️ Download still in progress")
                return False
            else:
                error = await response.text()
                print(f"❌ Failed to download file: {response.status}")
                print(f"   Error: {error}")
                return False


async def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("FASTAPI SERVER TEST SUITE")
    print("="*60)
    print("\nMake sure server is running: python server.py")
    print("Testing with 'Mr. Brightside' by The Killers")
    
    try:
        # Test 1: Health check
        if not await test_health_check():
            print("\n❌ Server is not running. Start with: python server.py")
            return 1
        
        # Test 2: Start download
        download_id = await test_start_download()
        if not download_id:
            print("\n❌ Failed to start download")
            return 1
        
        # Test 3: Monitor progress (SSE)
        success = await test_progress_stream(download_id)
        if not success:
            print("\n❌ Download failed")
            return 1
        
        # Wait a moment for metadata to be ready
        await asyncio.sleep(1)
        
        # Test 4: Get metadata
        if not await test_get_metadata(download_id):
            print("\n❌ Failed to get metadata")
            return 1
        
        # Test 5: Download file
        if not await test_download_file(download_id, "test_output.m4a"):
            print("\n❌ Failed to download file")
            return 1
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nServer is working correctly!")
        print("Downloaded file: test_output.m4a")
        print("\nNext steps:")
        print("1. Check test_output.m4a has all metadata")
        print("2. Deploy server to Render.com")
        print("3. Update Android app to use server")
        
        return 0
    
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
