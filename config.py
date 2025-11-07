"""
Server configuration.
All secrets should be set via environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Spotify API credentials
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    raise ValueError("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in environment variables")

# Optional: Genius API token
GENIUS_TOKEN = os.getenv('GENIUS_TOKEN')  # Can be None

# Output directory for downloads
# On Render free tier, use /tmp (ephemeral but writable)
# On local dev, use ./downloads
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', '/tmp/downloads' if os.getenv('RENDER') else './downloads'))
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# Cache directories
# On Render free tier, use /tmp (ephemeral but writable)
CACHE_DIR = Path(os.getenv('CACHE_DIR', '/tmp/cache' if os.getenv('RENDER') else './cache'))
CACHE_DIR.mkdir(exist_ok=True, parents=True)

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Rate limiting
RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv('RATE_LIMIT_RPM', '60'))

# File cleanup (delete after X minutes)
CLEANUP_AFTER_MINUTES = int(os.getenv('CLEANUP_AFTER_MINUTES', '10'))
