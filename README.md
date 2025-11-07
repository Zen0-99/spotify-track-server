# Spotify Track Downloader Server

FastAPI server for downloading Spotify tracks with complete metadata enrichment.

## Features

- **YouTube Music Search**: Superior scoring algorithm (200+ points) for accurate track matching
- **Complete Metadata**: Spotify metadata + Deezer images + MusicBrainz ISRC + LastFM stats + Kworb stream counts
- **Multi-Provider Lyrics**: LrcLib → Genius → Musixmatch fallback with synced LRC support
- **Server-Side Processing**: All downloads, metadata writing, and enrichment happen on server
- **Real-Time Progress**: Server-Sent Events (SSE) for live progress updates (0-100%)
- **Smart Caching**: 24-hour download cache + aggressive 10-minute file cleanup
- **Error Handling**: Proxy rotation for bot detection, exponential backoff for network errors

## Architecture

```
Client (Android App) → FastAPI Server → YouTube Music + Spotify API
                                     ↓
                          Fully Tagged M4A File (album art + lyrics + metadata)
```

## Quick Start

### Prerequisites

- Python 3.10+
- Spotify Developer Account (for API credentials)
- Optional: Genius API token (for lyrics)

### Installation

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/spotify-track-server.git
cd spotify-track-server

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your Spotify credentials
```

### Running Locally

```bash
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Server will be available at `http://localhost:8000`

### API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API Endpoints

### POST /api/download
Start a track download.

**Request:**
```json
{
  "spotify_track_id": "3n3Ppam7vgaVa1iaRUc9Lp",
  "prefer_synced_lyrics": true
}
```

**Response:**
```json
{
  "download_id": "uuid-here",
  "status": "processing",
  "message": "Download started"
}
```

### GET /api/progress/{download_id}
Server-Sent Events stream for real-time progress.

**Response (SSE stream):**
```
data: {"progress": 5}
data: {"progress": 15}
data: {"progress": 50}
data: {"progress": 100}
```

### GET /api/download/{download_id}
Download the completed file.

**Response:** M4A file with full metadata

### GET /health
Health check endpoint.

## Deployment (Render.com)

1. Push to GitHub
2. Connect repository to Render.com
3. Set environment variables in Render dashboard
4. Deploy automatically on push

See `render.yaml` for configuration.

## Environment Variables

```bash
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
GENIUS_TOKEN=your_genius_token  # Optional
LOG_LEVEL=INFO
CLEANUP_AFTER_MINUTES=10
```

## License

GPLv3 - Same as RetroMusicPlayer

## Credits

- Based on [spotify-downloader](https://github.com/spotDL/spotify-downloader) infrastructure
- YouTube search algorithm from [RetroMusicPlayer](https://github.com/retromusic/RetroMusicPlayer)
