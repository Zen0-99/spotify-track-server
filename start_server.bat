@echo off
echo Starting Spotify Track Downloader Server...
echo.
echo Server will be available at: http://localhost:8000
echo API docs: http://localhost:8000/docs
echo.
echo Press Ctrl+C to stop the server
echo.
cd /d "%~dp0"
.\venv\Scripts\uvicorn.exe server:app --reload --host 0.0.0.0 --port 8000
