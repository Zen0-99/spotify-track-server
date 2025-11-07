"""
Test complete download workflow and verify metadata.
"""

import asyncio
from core.spotify_client import SpotifyClient
from core.youtube_searcher import YouTubeMusicSearcher
from core.pytube_downloader import PyTubeDownloader
from core.metadata_writer import MetadataWriter
from core.lyrics_fetcher import LyricsFetcher
from core.deezer_enrichment import DeezerEnrichment
from core.musicbrainz_enrichment import MusicBrainzEnrichment
from core.lastfm_enrichment import LastFmEnrichment
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, GENIUS_TOKEN, OUTPUT_DIR
from pathlib import Path
from mutagen.mp4 import MP4

async def test_download():
    """Download a track and verify all metadata"""
    
    # Initialize all components
    spotify = SpotifyClient(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
    youtube = YouTubeMusicSearcher()
    pytube = PyTubeDownloader()
    metadata_writer = MetadataWriter()
    lyrics_fetcher = LyricsFetcher(genius_token=GENIUS_TOKEN)
    deezer = DeezerEnrichment()
    musicbrainz = MusicBrainzEnrichment()
    lastfm = LastFmEnrichment()
    
    # Test track: Mr. Brightside
    track_id = "3n3Ppam7vgaVa1iaRUc9Lp"
    
    print("="*60)
    print("COMPLETE DOWNLOAD TEST")
    print("="*60)
    
    # Step 1: Fetch Spotify metadata
    print("\n[1/9] Fetching Spotify metadata...")
    metadata = spotify.get_track_metadata(track_id)
    print(f"  [OK] Track: {metadata['title']} by {metadata['artists'][0]}")
    print(f"  [OK] Album: {metadata['album']}")
    print(f"  [OK] Duration: {metadata['duration_ms'] // 1000}s")
    print(f"  [OK] Album art URL: {metadata.get('album_art_url', 'N/A')[:50]}...")
    
    # Step 2: Deezer enrichment
    print("\n[2/9] Deezer enrichment...")
    deezer_cover = await deezer.get_album_cover(
        metadata['artists'][0], 
        metadata['album'], 
        size='xl'
    )
    if deezer_cover:
        print(f"  âœ“ Deezer 1000x1000 cover: {deezer_cover[:50]}...")
        album_art_url = deezer_cover  # Use Deezer instead
    else:
        album_art_url = metadata.get('album_art_url')
        print(f"  âš  Using Spotify cover: {album_art_url[:50] if album_art_url else 'None'}...")
    
    # Step 3: MusicBrainz enrichment
    print("\n[3/9] MusicBrainz enrichment...")
    mb_isrc = await musicbrainz.verify_track_isrc(
        metadata['title'], 
        metadata['artists'][0]
    )
    print(f"  âœ“ ISRC: {mb_isrc or 'Not found'}")
    
    # Step 4: Last.fm enrichment
    print("\n[4/9] Last.fm enrichment...")
    lastfm_genres = await lastfm.get_artist_genres(metadata['artists'][0])
    print(f"  âœ“ Genres: {', '.join(lastfm_genres[:3]) if lastfm_genres else 'None'}")
    
    # Step 5: YouTube Music search
    print("\n[5/9] Searching YouTube Music...")
    youtube_result = youtube.search(
        track_name=metadata['title'],
        artist_name=metadata['artists'][0],
        duration_seconds=metadata['duration_ms'] // 1000
    )
    if not youtube_result:
        print("  âœ— No YouTube match found!")
        return
    print(f"  âœ“ Found: {youtube_result['title']}")
    print(f"  âœ“ Score: {youtube_result['score']}/200+")
    
    # Step 6: Download audio
    print("\n[6/9] Downloading audio...")
    temp_dir = OUTPUT_DIR / "temp_test"
    temp_dir.mkdir(exist_ok=True)
    
    def progress(percent, message):
        if percent % 10 == 0:
            print(f"  {percent}% - {message}")
    
    audio_file = pytube.download_audio(
        youtube_result['url'],
        temp_dir,
        f"{metadata['title']} - {metadata['artists'][0]}",
        progress
    )
    
    if not audio_file or not audio_file.exists():
        print("  âœ— Download failed!")
        return
    
    print(f"  âœ“ Downloaded: {audio_file.name} ({audio_file.stat().st_size:,} bytes)")
    
    # Convert MP4 to M4A if needed
    if audio_file.suffix.lower() == '.mp4':
        print("\n[7/9] Converting to M4A...")
        import subprocess
        m4a_file = audio_file.with_suffix('.m4a')
        result = subprocess.run(
            ['ffmpeg', '-i', str(audio_file), '-c', 'copy', '-y', str(m4a_file)],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and m4a_file.exists():
            audio_file.unlink()
            audio_file = m4a_file
            print(f"  âœ“ Converted to M4A")
    else:
        print("\n[7/9] Already M4A format")
    
    # Step 7: Fetch lyrics
    print("\n[8/9] Fetching lyrics...")
    lyrics_result = await lyrics_fetcher.fetch_lyrics(
        track_name=metadata['title'],
        artist_name=metadata['artists'][0],
        album_name=metadata['album'],
        duration_seconds=metadata['duration_ms'] // 1000,
        prefer_synced=True
    )
    
    lyrics_text = None
    if lyrics_result:
        lyrics_text = lyrics_result['lyrics']
        print(f"  âœ“ Source: {lyrics_result['source']}")
        print(f"  âœ“ Synced: {lyrics_result['synced']}")
        print(f"  âœ“ Length: {len(lyrics_text)} characters")
    else:
        print("  âš  No lyrics found")
    
    # Step 8: Write metadata
    print("\n[9/9] Writing metadata...")
    enriched_metadata = {
        'title': metadata['title'],
        'artist': metadata['artists'][0],
        'artists': metadata['artists'],
        'album': metadata['album'],
        'track_number': metadata.get('track_number'),
        'disc_number': metadata.get('disc_number'),
        'date': metadata.get('release_date'),
        'genre': ', '.join(lastfm_genres[:3]) if lastfm_genres else None,
        'isrc': mb_isrc or metadata.get('isrc'),
        'album_type': metadata.get('album_type'),
        'album_art_url': album_art_url  # â† THIS WAS MISSING!
    }
    
    print(f"  Writing metadata with keys: {list(enriched_metadata.keys())}")
    success = metadata_writer.write_metadata(
        audio_file=audio_file,
        metadata=enriched_metadata,
        lyrics=lyrics_text
    )
    
    if success:
        print("  âœ“ Metadata written successfully")
    else:
        print("  âœ— Metadata writing failed!")
        return
    
    # Step 9: Organize file
    print("\n[10/10] Organizing file...")
    final_dir = OUTPUT_DIR / metadata['artists'][0] / metadata['album']
    final_dir.mkdir(parents=True, exist_ok=True)
    
    track_num = metadata.get('track_number')
    if track_num:
        filename = f"{track_num:02d} - {metadata['title']}.m4a"
    else:
        filename = f"{metadata['title']}.m4a"
    
    # Sanitize filename
    filename = filename.replace('/', '-').replace('\\', '-').replace(':', '-')
    filename = filename.replace('*', '').replace('?', '').replace('"', "'")
    filename = filename.replace('<', '').replace('>', '').replace('|', '')
    
    output_file = final_dir / filename
    if output_file.exists():
        output_file.unlink()  # Delete existing file
    audio_file.rename(output_file)
    
    # Clean up temp directory
    try:
        temp_dir.rmdir()
    except:
        pass
    
    print(f"  âœ“ Final file: {output_file}")
    
    # VERIFICATION
    print("\n" + "="*60)
    print("METADATA VERIFICATION")
    print("="*60)
    
    audio = MP4(output_file)
    
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
    else:
        print("Track #: N/A")
    
    print(f"Genre: {genre}")
    print(f"ISRC: {mb_isrc or 'N/A'}")
    
    has_cover = 'covr' in audio
    cover_size = len(audio['covr'][0]) if has_cover else 0
    print(f"\nâœ“ Album Art: {'YES (' + str(cover_size) + ' bytes)' if has_cover else 'NO'}")
    
    has_lyrics = '\xa9lyr' in audio
    if has_lyrics:
        lyrics_len = len(audio['\xa9lyr'][0])
        print(f"âœ“ Lyrics: YES ({lyrics_len} characters)")
    else:
        print(f"âœ— Lyrics: NO")
    
    print("\n" + "="*60)
    print(f"âœ… COMPLETE! File: {output_file.name}")
    print(f"   Size: {output_file.stat().st_size:,} bytes")
    print("="*60)
    
    # Close async sessions
    await lyrics_fetcher.close()
    await deezer.close()
    await musicbrainz.close()
    await lastfm.close()

if __name__ == "__main__":
    asyncio.run(test_download())

