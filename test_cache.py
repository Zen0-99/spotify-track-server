"""Test cache hit scenario"""
import requests
import time

SERVER = "http://localhost:8000"
TRACK_ID = "3n3Ppam7vgaVa1iaRUc9Lp"

print("Testing cache hit...")
print("="*60)

# Start download
resp = requests.post(f"{SERVER}/api/download", json={"spotify_track_id": TRACK_ID})
data = resp.json()
download_id = data["download_id"]
print(f"Download ID: {download_id}")

# Wait for completion
time.sleep(3)

# Get metadata
meta_resp = requests.get(f"{SERVER}/api/metadata/{download_id}")
print(f"Status code: {meta_resp.status_code}")

if meta_resp.status_code == 200:
    metadata = meta_resp.json()
    print(f"\n✅ SUCCESS!")
    print(f"Title: {metadata['title']}")
    print(f"Artist: {metadata['artists'][0]}")
    print(f"Cached: {metadata.get('cached', False)}")
else:
    print(f"\n❌ FAILED!")
    print(f"Response: {meta_resp.text}")
