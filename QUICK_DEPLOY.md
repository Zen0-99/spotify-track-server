# 🚀 Quick Deploy to Render - TL;DR

## 5-Minute Setup

### 1. Push to GitHub
```powershell
cd c:\Users\karol\Documents\GitHub\spotify-track-server
git init
git add .
git commit -m "Deploy FastAPI server"
git remote add origin https://github.com/YOUR_USERNAME/spotify-track-server.git
git push -u origin main
```

### 2. Create Render Service
- Go to https://dashboard.render.com
- New + → Web Service
- Connect GitHub repo: `spotify-track-server`

### 3. Add Environment Variables
```
SPOTIFY_CLIENT_ID = your_client_id_here
SPOTIFY_CLIENT_SECRET = your_secret_here
CLEANUP_AFTER_MINUTES = 10
```

Get credentials: https://developer.spotify.com/dashboard → Create App

### 4. Deploy!
Click "Create Web Service" → Wait 3 minutes

You'll get: `https://your-app-xyz.onrender.com`

### 5. Update Android App
Edit `app/build.gradle.kts` line ~38:
```kotlin
buildConfigField("String", "SPOTIFY_SERVER_URL", "\"https://your-app-xyz.onrender.com\"")
```

Rebuild:
```powershell
cd c:\Users\karol\Documents\GitHub\RetroMusicPlayer-old
.\gradlew assembleNormalDebug
adb install -r app\build\outputs\apk\normal\debug\app-normal-debug.apk
```

### 6. Test
Visit: `https://your-app-xyz.onrender.com/health`

Should return: `{"status": "healthy", ...}`

## Done! 🎉

**Keep-alive runs automatically** - server stays awake 24/7 on free tier!

Check logs for: `💓 Keep-alive ping successful` every 4 minutes.

---

## Common Issues

**Build failed?** → Check `requirements.txt` exists

**Server spins down?** → Check logs for keep-alive messages

**Android can't connect?** → Verify URL in build.gradle.kts (no trailing slash!)

**Spotify auth fails?** → Double-check Client ID/Secret in Render environment variables

---

Full guide: See `RENDER_DEPLOYMENT_GUIDE.md` for detailed instructions.
