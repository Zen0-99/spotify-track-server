"""
Test the new preview search endpoint.
"""

import requests
import json

SERVER_URL = "http://localhost:8000"

def test_preview_search():
    """Test preview URL search"""
    print("🧪 Testing preview search endpoint...")
    
    # Test data
    request_data = {
        "track_name": "Mr. Brightside",
        "artist_name": "The Killers",
        "duration_ms": 223000
    }
    
    print(f"\n📤 Request: POST {SERVER_URL}/api/preview/search")
    print(f"   Track: {request_data['track_name']}")
    print(f"   Artist: {request_data['artist_name']}")
    print(f"   Duration: {request_data['duration_ms']}ms")
    
    try:
        response = requests.post(
            f"{SERVER_URL}/api/preview/search",
            json=request_data,
            timeout=30
        )
        
        print(f"\n📥 Response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ SUCCESS!")
            print(f"   Match Score: {data['match_score']}/200+")
            print(f"   Video Title: {data['video_title']}")
            print(f"   Duration: {data['duration_seconds']}s")
            print(f"   Video URL: {data['video_url']}")
            print(f"\n   Audio Stream URL (first 100 chars):")
            print(f"   {data['audio_url'][:100]}...")
            
            # Verify URL is accessible
            print(f"\n🔍 Verifying stream URL...")
            stream_response = requests.head(data['audio_url'], timeout=10)
            print(f"   Stream HEAD: {stream_response.status_code}")
            if stream_response.status_code == 200:
                print(f"   ✅ Stream URL is accessible!")
                content_type = stream_response.headers.get('Content-Type', 'unknown')
                content_length = stream_response.headers.get('Content-Length', 'unknown')
                print(f"   Content-Type: {content_type}")
                print(f"   Content-Length: {content_length} bytes")
            else:
                print(f"   ⚠️  Stream URL returned {stream_response.status_code}")
        else:
            print(f"\n❌ FAILED")
            print(f"   {response.text}")
    
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    print("="*60)
    print("Preview Search Endpoint Test")
    print("="*60)
    test_preview_search()
    print("\n" + "="*60)
