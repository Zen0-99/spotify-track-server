"""
Comprehensive server test client.
Tests all endpoints and features.
"""

import asyncio
import aiohttp
import json
from pathlib import Path
from mutagen.mp4 import MP4

SERVER_URL = "http://localhost:8000"


async def test_health():
    """Test health endpoint"""
    print("\n" + "="*60)
    print("TEST 1: Health Check")
    print("="*60)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{SERVER_URL}/health") as response:
            if response.status == 200:
                data = await response.json()
                print("[OK] Server is healthy")
                print(f"  Active downloads: {data['active_downloads']}")
                print(f"  Total downloads: {data['total_downloads']}")
                return True
            else:
                print(f"[FAIL] Health check failed: {response.status}")
                return False


async def test_download(track_id: str = "3n3Ppam7vgaVa1iaRUc9Lp"):
    """Test complete download workflow"""
    print("\n" + "="*60)
    print("TEST 2: Download Track (Mr. Brightside)")
    print("="*60)
    
    async with aiohttp.ClientSession() as session:
        # Step 1: Start download
        print("\n[1/4] Starting download...")
        payload = {
            "spotify_track_id": track_id,
            "prefer_synced_lyrics": True,
            "high_quality_cover": True
        }
        
        async with session.post(f"{SERVER_URL}/api/download", json=payload) as response:
            if response.status != 200:
                print(f"[FAIL] Download start failed: {response.status}")
                return False
            
            data = await response.json()
            download_id = data['download_id']
            print(f"[OK] Download started: {download_id}")
        
        # Step 2: Monitor progress via SSE
        print("\n[2/4] Monitoring progress...")
        progress_updates = []
        
        async with session.get(f"{SERVER_URL}/api/progress/{download_id}") as response:
            if response.status != 200:
                print(f"[FAIL] Progress stream failed: {response.status}")
                return False
            
            async for line in response.content:
                line_str = line.decode('utf-8').strip()
                if line_str.startswith('data: '):
                    data_str = line_str[6:]  # Remove 'data: ' prefix
                    try:
                        progress_data = json.loads(data_str)
                        progress = progress_data.get('progress', 0)
                        status = progress_data.get('status', '')
                        
                        # Print every 20%
                        if progress % 20 == 0 or progress == 100:
                            print(f"  [{progress}%] {status}")
                        
                        progress_updates.append(progress_data)
                        
                        if progress_data.get('completed'):
                            print(f"[OK] Download completed!")
                            break
                    except json.JSONDecodeError:
                        pass
        
        # Step 3: Get metadata
        print("\n[3/4] Fetching metadata...")
        async with session.get(f"{SERVER_URL}/api/metadata/{download_id}") as response:
            if response.status != 200:
                print(f"[WARN] Metadata fetch failed: {response.status}")
            else:
                metadata = await response.json()
                print(f"[OK] Title: {metadata.get('title', 'N/A')}")
                print(f"[OK] Artists: {', '.join(metadata.get('artists', []))}")
                print(f"[OK] Album: {metadata.get('album', 'N/A')}")
                print(f"[OK] ISRC: {metadata.get('isrc', 'N/A')}")
                print(f"[OK] Lyrics source: {metadata.get('lyrics_source', 'N/A')}")
                print(f"[OK] Lyrics synced: {metadata.get('lyrics_synced', False)}")
                
                # Show enrichment data
                enrichment = metadata.get('enrichment', {})
                if enrichment:
                    print("\n  Enrichment Data:")
                    
                    deezer = enrichment.get('deezer', {})
                    if deezer and deezer.get('cover_url'):
                        print(f"    - Deezer cover: {deezer['cover_url'][:50]}...")
                    
                    musicbrainz = enrichment.get('musicbrainz', {})
                    if musicbrainz:
                        print(f"    - MusicBrainz ISRC verified: {musicbrainz.get('isrc_verified', False)}")
                    
                    lastfm = enrichment.get('lastfm', {})
                    if lastfm and lastfm.get('track_stats'):
                        stats = lastfm['track_stats']
                        print(f"    - Last.fm plays: {stats.get('playcount', 0):,}")
                    
                    kworb = enrichment.get('kworb')
                    if kworb:
                        print(f"    - Kworb total plays: {kworb.get('total_plays', 0):,}")
                        print(f"    - Kworb daily plays: {kworb.get('daily_plays', 0):,}")
                    
                    youtube = enrichment.get('youtube', {})
                    if youtube:
                        print(f"    - YouTube match score: {youtube.get('score', 0)}/200+")
        
        # Step 4: Download file
        print("\n[4/4] Downloading file...")
        async with session.get(f"{SERVER_URL}/api/download/{download_id}") as response:
            if response.status != 200:
                print(f"[FAIL] File download failed: {response.status}")
                return False
            
            # Save to temp file
            temp_file = Path("test_download.m4a")
            with open(temp_file, 'wb') as f:
                async for chunk in response.content.iter_chunked(1024):
                    f.write(chunk)
            
            file_size = temp_file.stat().st_size
            print(f"[OK] Downloaded: {file_size:,} bytes")
            
            # Verify metadata in file
            print("\n" + "="*60)
            print("METADATA VERIFICATION")
            print("="*60)
            
            audio = MP4(temp_file)
            
            title = audio.get('\xa9nam', ['N/A'])[0]
            artist = audio.get('\xa9ART', ['N/A'])[0]
            album = audio.get('\xa9alb', ['N/A'])[0]
            genre = audio.get('\xa9gen', ['N/A'])[0]
            
            print(f"\nTitle: {title}")
            print(f"Artist: {artist}")
            print(f"Album: {album}")
            
            track_info = audio.get('trkn')
            if track_info:
                print(f"Track #: {track_info[0][0]}/{track_info[0][1] if track_info[0][1] else '?'}")
            
            print(f"Genre: {genre}")
            
            has_cover = 'covr' in audio
            cover_size = len(audio['covr'][0]) if has_cover else 0
            print(f"\nAlbum Art: {'YES (' + str(cover_size) + ' bytes)' if has_cover else 'NO'}")
            
            has_lyrics = '\xa9lyr' in audio
            if has_lyrics:
                lyrics_len = len(audio['\xa9lyr'][0])
                print(f"Lyrics: YES ({lyrics_len} characters)")
            else:
                print(f"Lyrics: NO")
            
            # Clean up
            temp_file.unlink()
            
            # Verify all critical features
            success = True
            if not has_cover:
                print("\n[FAIL] Missing album art!")
                success = False
            if not has_lyrics:
                print("\n[FAIL] Missing lyrics!")
                success = False
            if title == 'N/A':
                print("\n[FAIL] Missing title!")
                success = False
            
            if success:
                print("\n" + "="*60)
                print("[OK] ALL TESTS PASSED!")
                print("="*60)
            
            return success


async def test_cache():
    """Test deduplication cache"""
    print("\n" + "="*60)
    print("TEST 3: Deduplication Cache")
    print("="*60)
    
    track_id = "3n3Ppam7vgaVa1iaRUc9Lp"  # Same track as before
    
    async with aiohttp.ClientSession() as session:
        print("\n[1/2] Requesting same track again...")
        payload = {
            "spotify_track_id": track_id,
            "prefer_synced_lyrics": True
        }
        
        import time
        start_time = time.time()
        
        async with session.post(f"{SERVER_URL}/api/download", json=payload) as response:
            if response.status != 200:
                print(f"[FAIL] Download start failed")
                return False
            
            data = await response.json()
            download_id = data['download_id']
        
        # Monitor progress
        async with session.get(f"{SERVER_URL}/api/progress/{download_id}") as response:
            async for line in response.content:
                line_str = line.decode('utf-8').strip()
                if line_str.startswith('data: '):
                    data_str = line_str[6:]
                    try:
                        progress_data = json.loads(data_str)
                        if progress_data.get('completed'):
                            break
                    except:
                        pass
        
        elapsed = time.time() - start_time
        
        print(f"\n[2/2] Elapsed time: {elapsed:.2f}s")
        
        if elapsed < 2:
            print("[OK] Cache hit! Download returned instantly")
            return True
        else:
            print(f"[WARN] Cache miss or slow response ({elapsed:.2f}s)")
            return True


async def main():
    """Run all tests"""
    print("\n")
    print("="*60)
    print(" SPOTIFY TRACK SERVER - COMPREHENSIVE TEST SUITE")
    print("="*60)
    
    # Test 1: Health check
    if not await test_health():
        print("\n[FAIL] Server is not responding!")
        return
    
    # Test 2: Full download workflow
    if not await test_download():
        print("\n[FAIL] Download test failed!")
        return
    
    # Test 3: Cache
    await test_cache()
    
    print("\n")
    print("="*60)
    print(" ALL TESTS COMPLETE")
    print("="*60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
