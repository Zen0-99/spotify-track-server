"""Quick test of server functionality"""
import asyncio
import aiohttp
import json
from pathlib import Path
from mutagen.mp4 import MP4

SERVER_URL = "http://localhost:8000"

async def test_download_and_verify():
    """Test download and verify metadata"""
    track_id = "3n3Ppam7vgaVa1iaRUc9Lp"  # Mr. Brightside
    
    async with aiohttp.ClientSession() as session:
        print("\n[1/3] Starting download...")
        payload = {"spotify_track_id": track_id}
        
        async with session.post(f"{SERVER_URL}/api/download", json=payload) as response:
            data = await response.json()
            download_id = data['download_id']
            print(f"  Download ID: {download_id}")
        
        print("\n[2/3] Monitoring progress...")
        last_progress = 0
        async with session.get(f"{SERVER_URL}/api/progress/{download_id}") as response:
            async for line in response.content:
                line_str = line.decode('utf-8').strip()
                if line_str.startswith('data: '):
                    try:
                        progress_data = json.loads(line_str[6:])
                        progress = progress_data.get('progress', 0)
                        
                        # Print every 20%
                        if progress >= last_progress + 20 or progress == 100:
                            status = progress_data.get('status', '')
                            print(f"  [{progress}%] {status}")
                            last_progress = progress
                        
                        if progress_data.get('completed'):
                            break
                    except:
                        pass
        
        print("\n[3/3] Downloading file...")
        async with session.get(f"{SERVER_URL}/api/download/{download_id}") as response:
            temp_file = Path("test_quick.m4a")
            with open(temp_file, 'wb') as f:
                async for chunk in response.content.iter_chunked(1024):
                    f.write(chunk)
        
        # Verify
        print("\n" + "="*60)
        print("VERIFICATION")
        print("="*60)
        
        audio = MP4(temp_file)
        title = audio.get('\xa9nam', ['N/A'])[0]
        artist = audio.get('\xa9ART', ['N/A'])[0]
        genre = audio.get('\xa9gen', ['N/A'])[0]
        has_cover = 'covr' in audio
        has_lyrics = '\xa9lyr' in audio
        
        print(f"Title: {title}")
        print(f"Artist: {artist}")
        print(f"Genre: {genre}")
        print(f"Album art: {'YES' if has_cover else 'NO'}")
        print(f"Lyrics: {'YES' if has_lyrics else 'NO'}")
        
        temp_file.unlink()
        print("\n[OK] Test complete!")

if __name__ == "__main__":
    asyncio.run(test_download_and_verify())
