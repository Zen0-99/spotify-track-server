# 🚀 Render.com Deployment Checklist

## Prerequisites
- [ ] GitHub account
- [ ] Render.com account (sign up at https://render.com)
- [ ] Spotify Developer credentials (Client ID + Secret)

---

## Step 1: Push Server to GitHub

```powershell
cd c:\Users\karol\Documents\GitHub\spotify-track-server

# Initialize git if not already done
git init

# Add all files
git add .

# Commit
git commit -m "Add FastAPI server with keep-alive for Render deployment"

# Create repo on GitHub: https://github.com/new
# Name: spotify-track-server

# Add remote and push
git remote add origin https://github.com/YOUR_USERNAME/spotify-track-server.git
git branch -M main
git push -u origin main
```

---

## Step 2: Get Spotify API Credentials

1. Go to https://developer.spotify.com/dashboard
2. Click **"Create App"**
3. Fill in:
   - **App name**: RetroMusic Track Server
   - **App description**: Download server for RetroMusic Player
   - **Redirect URI**: https://your-app.onrender.com/callback
   - **APIs used**: Web API
4. Click **"Save"**
5. Copy **Client ID** and **Client Secret** (you'll need these in Step 4)

---

## Step 3: Create Render Web Service

1. Go to https://dashboard.render.com
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub account (if first time)
4. Select repository: **`spotify-track-server`**
5. Click **"Connect"**

---

## Step 4: Configure Service Settings

### Basic Configuration
- **Name**: `spotify-track-server` (or any name you prefer)
- **Region**: `Oregon (US West)` or closest to your location
- **Branch**: `main`
- **Root Directory**: _(leave blank)_

### Build Settings ✅ (Auto-filled from render.yaml)
- **Environment**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`

### Instance Type
- **Plan**: `Free` (⚠️ Spins down after 15 min - our keep-alive prevents this!)

---

## Step 5: Add Environment Variables

Click **"Advanced"** and add these:

| Variable | Value | Required |
|----------|-------|----------|
| `SPOTIFY_CLIENT_ID` | Your Spotify Client ID | ✅ Yes |
| `SPOTIFY_CLIENT_SECRET` | Your Spotify Client Secret | ✅ Yes |
| `GENIUS_TOKEN` | Your Genius API token | ❌ Optional (for lyrics) |
| `CLEANUP_AFTER_MINUTES` | `10` | ❌ Optional (default: 10) |
| `LOG_LEVEL` | `INFO` | ❌ Optional (default: INFO) |

**Where to get Genius Token** (optional):
1. Go to https://genius.com/api-clients
2. Click "New API Client"
3. Generate Access Token
4. Copy token

---

## Step 6: Configure Persistent Disk (Optional)

Scroll to **"Disk"** section:
- **Mount Path**: `/opt/render/project/src/downloads`
- **Name**: `downloads`
- **Size**: `1 GB` (free tier max)

> **Note**: Files are auto-deleted after 10 minutes anyway, so this is optional.

---

## Step 7: Deploy!

1. Click **"Create Web Service"** at bottom
2. Wait 2-5 minutes for deployment
3. Watch build logs - should see:
   ```
   🚀 Starting Spotify Track Downloader Server
   💓 Keep-alive task started - pinging https://your-app.onrender.com/health every 4 minutes
   ```

4. Once deployed, you'll get a URL like:
   ```
   https://spotify-track-server-xyz123.onrender.com
   ```
   **COPY THIS URL!** You'll need it for the Android app.

---

## Step 8: Test Your Deployment

### Test Health Endpoint
Open in browser or use PowerShell:
```powershell
curl https://your-app.onrender.com/health
```

Should return:
```json
{
  "status": "healthy",
  "active_downloads": 0,
  "total_downloads": 0,
  "timestamp": "2025-11-07T..."
}
```

### Test API Documentation
Visit: `https://your-app.onrender.com/` in browser

Should show:
```json
{
  "name": "Spotify Track Downloader Server",
  "version": "1.0.0",
  "endpoints": { ... }
}
```

### Test Download (via curl or Postman)
```powershell
# Start a download
curl -X POST https://your-app.onrender.com/api/download `
  -H "Content-Type: application/json" `
  -d '{"spotify_track_id":"3n3Ppam7vgaVa1iaRUc9Lp","prefer_synced_lyrics":true}'

# Should return: {"download_id":"uuid...","status":"processing"}
```

---

## Step 9: Update Android App

### Update Server URL in build.gradle.kts

Replace the placeholder with your actual Render URL:

```kotlin
// In app/build.gradle.kts, line ~38
buildConfigField("String", "SPOTIFY_SERVER_URL", "\"https://YOUR-ACTUAL-URL.onrender.com\"")
```

**Example:**
```kotlin
buildConfigField("String", "SPOTIFY_SERVER_URL", "\"https://spotify-track-server-xyz123.onrender.com\"")
```

### Rebuild Android App
```powershell
cd c:\Users\karol\Documents\GitHub\RetroMusicPlayer-old
.\gradlew assembleNormalDebug
adb install -r app\build\outputs\apk\normal\debug\app-normal-debug.apk
```

---

## Step 10: Verify Keep-Alive is Working

### Check Render Logs
1. Go to Render dashboard
2. Click on your service
3. Click **"Logs"** tab
4. Wait 4 minutes after deployment
5. Should see logs like:
   ```
   💓 Keep-alive ping successful - 0 active downloads
   💓 Keep-alive ping successful - 0 active downloads
   💓 Keep-alive ping successful - 0 active downloads
   ```

### Verify Server Stays Awake
- Leave server alone for 20+ minutes
- Visit `https://your-app.onrender.com/health` in browser
- Should load instantly (not spin up from sleep)
- ✅ If it loads fast, keep-alive is working!
- ❌ If it takes 30+ seconds to load, keep-alive failed (check logs)

---

## Troubleshooting

### ❌ Build Failed - "Module not found"
**Solution**: Check `requirements.txt` is present and valid
```powershell
# Test locally first
cd c:\Users\karol\Documents\GitHub\spotify-track-server
pip install -r requirements.txt
```

### ❌ "Spotify authentication failed"
**Solution**: Double-check environment variables
1. Go to Render dashboard → Your service → "Environment"
2. Verify `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` are correct
3. Re-deploy after fixing (click "Manual Deploy" → "Deploy latest commit")

### ❌ Keep-Alive Not Working (Server Still Sleeps)
**Solution**: Check RENDER environment variable is set
1. Render automatically sets `RENDER=true` and `RENDER_EXTERNAL_URL`
2. Check logs for: `💓 Keep-alive task started...`
3. If not present, the task didn't start (check for Python errors)

### ❌ "Failed to connect to server" from Android app
**Solutions**:
1. Check server URL in `build.gradle.kts` is correct (no trailing slash!)
2. Verify server is running: visit URL in browser
3. Check Android app has internet permission (already included)
4. Test with WiFi first, then mobile data

### ❌ Downloads Fail with "No YouTube match found"
**Solutions**:
1. This is expected for some tracks (YouTube Music search not perfect)
2. Check server logs for scoring details
3. Try a different track to verify server is working
4. May need to adjust YouTube search algorithm later

---

## Free Tier Limitations

### Render Free Tier
- ✅ 750 hours/month (always-on with keep-alive)
- ✅ 100 GB bandwidth/month
- ✅ 512 MB RAM (sufficient for FastAPI)
- ✅ 1 GB persistent disk
- ⚠️ Spins down after 15 min inactivity (our keep-alive prevents this)
- ⚠️ Cold start: ~30 seconds if it does spin down

### When to Upgrade
Consider paid plan ($7/month) if:
- You have many users (>100 downloads/day)
- You need faster response times (no spin-down ever)
- You need more disk space (>1 GB)

---

## Maintenance

### Monitor Usage
1. Render dashboard → Your service → "Metrics"
2. Watch:
   - **CPU usage**: Should be <50% normally
   - **Memory usage**: Should be <400 MB normally
   - **Bandwidth**: Check you're under 100 GB/month
   - **Build minutes**: Check you're under 500 min/month

### Update Server Code
```powershell
cd c:\Users\karol\Documents\GitHub\spotify-track-server

# Make changes to server.py or other files
git add .
git commit -m "Update: ..."
git push origin main

# Render auto-deploys within 2-3 minutes!
```

### View Logs
```powershell
# Real-time logs in Render dashboard
# Or use Render CLI (optional)
render logs -f
```

---

## Success Checklist

- [ ] Server deployed successfully on Render
- [ ] Health endpoint returns `{"status": "healthy"}`
- [ ] Keep-alive logs appear every 4 minutes
- [ ] Android app updated with Render URL
- [ ] Android app successfully downloads a test track
- [ ] Server stays awake after 20+ minutes (no cold start)
- [ ] Mobile data toggle works in app settings

---

## Your Deployment Details

Fill in after deployment:

- **Render URL**: https://_____________________.onrender.com
- **Deployed Date**: __________
- **Spotify App Name**: ___________________
- **Spotify Client ID**: ___________________
- **Genius Token**: _________________ (optional)

---

## Support & Resources

- **Render Docs**: https://render.com/docs
- **Render Status**: https://status.render.com
- **FastAPI Docs**: https://fastapi.tiangolo.com
- **Spotify Web API**: https://developer.spotify.com/documentation/web-api

---

## Next Steps After Deployment

1. **Test extensively**: Download various tracks, test edge cases
2. **Monitor logs**: Check for errors in Render dashboard
3. **Share with beta testers**: Get feedback on download quality
4. **Optimize as needed**: Adjust YouTube search scoring if needed
5. **Consider upgrading**: If usage grows beyond free tier limits

**🎉 Congratulations! Your server is live on Render!**
