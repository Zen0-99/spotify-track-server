import requests
from pathlib import Path
from mutagen.mp4 import MP4
import time

# Config
SERVER = "http://localhost:8000"
TRACK_ID = "3n3Ppam7vgaVa1iaRUc9Lp"  # Mr. Brightside

print("="*60)
print("SIMPLE VERIFICATION TEST")
print("="*60)

# Step 1: Initiate download
print("\n[1/3] Starting download...")
resp = requests.post(f"{SERVER}/api/download", json={"spotify_track_id": TRACK_ID}, timeout=60)
data = resp.json()
download_id = data["download_id"]
print(f"  Download ID: {download_id}")

# Step 2: Wait for completion
print(f"\n[2/3] Waiting for completion...")
time.sleep(1)  # Brief initial wait
max_wait = 60  # 60 seconds max
waited = 0
while waited < max_wait:
    time.sleep(1)
    waited += 1
    
    # Check metadata endpoint
    meta_resp = requests.get(f"{SERVER}/api/metadata/{download_id}")
    if meta_resp.status_code == 200:
        print(f"  Completed in {waited} seconds!")
        break
    elif meta_resp.status_code == 425:  # Still in progress
        if waited % 5 == 0:
            print(f"  Still waiting... ({waited}s)")
        continue
    elif meta_resp.status_code == 500:
        try:
            error_detail = meta_resp.json().get('detail', meta_resp.text)
        except:
            error_detail = meta_resp.text
        print(f"  Download failed: {error_detail}")
        exit(1)
    else:
        print(f"  Error: {meta_resp.status_code}")
        print(f"  {meta_resp.text}")
        exit(1)
else:
    print(f"  Timeout after {max_wait} seconds")
    exit(1)

# Step 3: Get the file
print(f"\n[3/3] Downloading file...")
get_resp = requests.get(
    f"{SERVER}/api/download/{download_id}",
    timeout=120,
    stream=True
)

if get_resp.status_code == 200:
    # Save temporarily
    temp_file = Path("test_temp.m4a")
    temp_file.write_bytes(get_resp.content)
    size_mb = temp_file.stat().st_size / (1024**2)
    print(f"  File downloaded: {size_mb:.2f} MB")
    
    # Verify metadata
    print("\n" + "="*60)
    print("METADATA VERIFICATION")
    print("="*60)
    
    audio = MP4(temp_file)
    title = audio.get('\xa9nam', ['N/A'])[0]
    artist = audio.get('\xa9ART', ['N/A'])[0]
    album = audio.get('\xa9alb', ['N/A'])[0]
    genre = audio.get('\xa9gen', ['N/A'])[0]
    
    has_cover = 'covr' in audio
    cover_size = len(audio['covr'][0]) if has_cover else 0
    
    has_lyrics = '\xa9lyr' in audio
    lyrics_len = len(str(audio.get('\xa9lyr', [''])[0])) if has_lyrics else 0
    
    print(f"Title: {title}")
    print(f"Artist: {artist}")
    print(f"Album: {album}")
    print(f"Genre: {genre}")
    print(f"Album art: {'YES' if has_cover else 'NO'} ({cover_size:,} bytes)")
    print(f"Lyrics: {'YES' if has_lyrics else 'NO'} ({lyrics_len:,} chars)")
    
    # Clean up
    temp_file.unlink()
    print("\n[OK] Test complete!")
    
else:
    print(f"  Error: {get_resp.status_code}")
    print(f"  {get_resp.text}")
