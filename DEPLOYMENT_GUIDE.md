# 🚀 SERVER DEPLOYMENT GUIDE - Render.com

## Overview
Deploy the FastAPI server to Render.com free tier for personal use (5-10 users).

---

## ⚙️ PREREQUISITES

1. **GitHub Account**: Server code must be in GitHub repo
2. **Render.com Account**: Sign up at https://render.com (free tier)
3. **Spotify Developer Credentials**: Get from https://developer.spotify.com/dashboard

---

## 📋 DEPLOYMENT STEPS

### Step 1: Prepare Server Repository (5 minutes)

1. **Ensure `render.yaml` is committed**:
```powershell
cd C:\Users\karol\Documents\GitHub\spotify-track-server
git add render.yaml requirements.txt
git commit -m "Add Render deployment configuration"
git push origin main
```

2. **Verify `requirements.txt` includes all dependencies**:
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
python-dotenv==1.0.0
spotipy==2.23.0
yt-dlp==2024.11.0
mutagen==1.47.0
httpx==0.25.2
aiofiles==23.2.1
sse-starlette==1.8.2
python-Levenshtein==0.23.0
```

### Step 2: Connect to Render.com (10 minutes)

1. **Go to**: https://dashboard.render.com
2. **Click**: "New +" → "Web Service"
3. **Connect GitHub repository**:
   - Click "Connect account" (first time)
   - Select repository: `spotify-track-server`
   - Branch: `main`
4. **Render will auto-detect `render.yaml`**:
   - Click "Apply" to use configuration

### Step 3: Configure Environment Variables (5 minutes)

In Render dashboard, navigate to **Environment** tab:

#### Required Variables:
```
SPOTIFY_CLIENT_ID = <your-client-id>
SPOTIFY_CLIENT_SECRET = <your-client-secret>
```

#### Optional Variables (pre-configured in render.yaml):
```
GENIUS_TOKEN = <optional-for-lyrics>
LOG_LEVEL = INFO
CLEANUP_AFTER_MINUTES = 10
```

**Important**: Copy credentials from `spotify.properties` in your local project.

### Step 4: Deploy (15 minutes)

1. **Render automatically deploys on first connection**
2. **Monitor build logs** in Render dashboard
3. **Wait for "Live" status** (usually 5-10 minutes)
4. **Your server URL** will be: `https://spotify-track-server-XXXX.onrender.com`

### Step 5: Test Deployment (5 minutes)

#### Test health endpoint:
```powershell
curl https://your-server-url.onrender.com/health
# Expected: {"status": "healthy"}
```

#### Test download endpoint:
```powershell
curl -X POST https://your-server-url.onrender.com/api/download `
  -H "Content-Type: application/json" `
  -d '{"spotify_track_id":"3n3Ppam7vgaVa1iaRUc9Lp"}'

# Expected: {"download_id":"abc-123","status":"processing","message":"Download started"}
```

#### Test progress endpoint:
```powershell
curl -N https://your-server-url.onrender.com/api/progress/abc-123

# Expected: SSE stream with progress updates
```

### Step 6: Update Android App (5 minutes)

Update production server URL in `app/build.gradle.kts`:

```kotlin
getByName("release") {
    // ... existing config ...
    
    // Replace with your actual Render URL
    buildConfigField("String", "SPOTIFY_SERVER_URL", 
        "\"https://spotify-track-server-XXXX.onrender.com\"")
}
```

Build release APK:
```powershell
cd C:\Users\karol\Documents\GitHub\RetroMusicPlayer-old
.\gradlew assembleNormalRelease
```

---

## 🔒 SECURITY CHECKLIST

- [ ] Never commit `SPOTIFY_CLIENT_SECRET` to Git
- [ ] Use Render's environment variables for secrets
- [ ] HTTPS is automatic (Render provides SSL)
- [ ] Rate limiting enabled (10 downloads/hour on free tier - configure in server.py)

---

## 📊 MONITORING

### View Logs:
1. Go to Render dashboard
2. Select your service
3. Click "Logs" tab
4. Real-time logs with emoji indicators:
   - 📥 Download started
   - 🎵 YouTube search
   - ✅ Download complete
   - ❌ Errors

### Metrics (Free Tier):
- **Requests/day**: Check "Metrics" tab
- **Build time**: ~2-3 minutes
- **Cold start**: ~30 seconds after 15min inactivity
- **Disk usage**: Monitor downloads folder size

---

## ⚠️ FREE TIER LIMITATIONS

| Limit | Value | Impact |
|-------|-------|--------|
| **Hours/month** | 750 | ~31 days (no limit for personal use) |
| **RAM** | 512MB | Sufficient for 4 concurrent downloads |
| **CPU** | 0.5 vCPU | Downloads take ~30-60s per track |
| **Disk** | 1GB | 10-minute cleanup keeps usage low |
| **Cold Starts** | 15min inactivity | First request after idle takes ~30s |
| **Bandwidth** | Unlimited | Free for personal projects |

---

## 🛠️ TROUBLESHOOTING

### Build Fails:
- Check `requirements.txt` matches server dependencies
- Verify Python version (3.10+) in logs

### 500 Errors:
- Check environment variables are set correctly
- View logs for stack traces
- Common issue: Missing `SPOTIFY_CLIENT_ID`

### Downloads Fail:
- YouTube bot detection: Server may need proxy rotation (add ProxyRotator)
- Spotify API rate limit: Wait 1 hour or use different credentials

### Server Sleeps:
- Expected behavior after 15min inactivity
- First request wakes server (~30s delay)
- Acceptable for personal use (5-10 users)

---

## 🚀 POST-DEPLOYMENT TESTING

### Test Matrix:
1. **Single download**: "Mr. Brightside" by The Killers
2. **Album download**: 10+ tracks from same album
3. **Cache hit**: Download same track twice (instant return)
4. **Error handling**: Invalid Spotify ID (should return 404)
5. **Lyrics**: Track with synced lyrics (LrcLib)
6. **Album art**: 1000x1000 Deezer cover embedded

### Expected Results:
- ✅ Download completes in 30-60s
- ✅ M4A file has all metadata (art, lyrics, genres)
- ✅ File appears in Android app's library
- ✅ MediaStore scanned automatically

---

## 📈 PERFORMANCE OPTIMIZATION (Optional)

### For Higher Traffic:
1. **Upgrade to paid tier** ($7/month) for:
   - No cold starts
   - 2GB RAM (8 concurrent downloads)
   - Faster CPU

2. **Add Caching**:
   - Redis for metadata cache (reduces Spotify API calls)
   - CDN for album art (not available on free tier)

3. **Scale Horizontally**:
   - Multiple server instances
   - Load balancer (paid feature)

---

## ✅ DEPLOYMENT CHECKLIST

- [ ] GitHub repo pushed with render.yaml
- [ ] Render.com account created
- [ ] Repository connected to Render
- [ ] Environment variables set (Spotify credentials)
- [ ] Build successful (check logs)
- [ ] Health endpoint returns 200 OK
- [ ] Test download endpoint works
- [ ] Server URL updated in Android app
- [ ] Release APK built and tested
- [ ] End-to-end test: App → Server → File → MediaStore

---

**Estimated Total Time**: 45 minutes  
**Next Steps**: Update Android app with production URL, build release APK, test with physical device
