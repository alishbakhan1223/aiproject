# Camera Source Configuration Guide

## Testing Local Webcam (Windows)

### Option 1: Try these source values in order (most to least likely to work)
Add camera with these sources one at a time:

1. **`0`** — Standard webcam index (may or may not work on Windows)
2. **`1`** — Secondary webcam (if multiple cameras connected)
3. **`cv2.CAP_DSHOW + 0`** — Windows DirectShow backend with camera 0
4. **`dshow://video="your_camera_name"`** — DirectShow with camera name (see below to find name)

### Option 2: Find your actual camera name on Windows
Run this in PowerShell:
```powershell
Get-PnpDevice -Class Camera
```
Look for the camera name, then use it like:
```
dshow://video="Integrated Webcam"
```

### Option 3: Use ffmpeg URI (if camera still doesn't work)
```
ffmpeg://dshow?video=0
```

---

## Testing RTSP Stream (Public Test Camera)

### Ready-to-use RTSP test streams:

| Camera | RTSP URL | Notes |
|--------|----------|-------|
| **Wowza Demo** | `rtsp://wowzaec2demo.streaming.media.azure.net/rtspv2/sass` | High-quality, stable |
| **NIST Test** | `rtsp://nist.intuitive-machines.com:554/stream` | Real surveillance camera |
| **YSCam Demo** | `rtsp://184.72.239.149/rtplive/470011e600fc1d27d60741e5e114606e` | Often works |
| **FLIR Demo** | `rtsp://192.0.2.1:554/stream` | Test setup (may be offline) |

**Recommended:** Use the **Wowza Demo** URL above — it's stable and always available.

---

## How to Test

### Step 1: Restart Backend
```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Watch the terminal for logs when you start a camera.

### Step 2: Add and Test Local Webcam
1. Go to http://localhost:5173 (dashboard)
2. Log in with `admin` / `cctv2024`
3. Go to **Dashboard** → **Cameras**
4. Click **Add Camera**
   - **Name:** `Local Webcam`
   - **Source:** `0`
5. Click **Add**
6. Click **Start** next to the camera
7. **Check backend terminal for logs:**
   - ✅ `Camera opened successfully` — click **View** to see it
   - ❌ `FAILED to open camera source` — try the next source value

**If `0` fails, try:** `1`, then `dshow://video="Integrated Webcam"`, etc.

### Step 3: Add and Test RTSP Stream
1. In dashboard **Cameras** section
2. Click **Add Camera**
   - **Name:** `Wowza RTSP Test`
   - **Source:** `rtsp://wowzaec2demo.streaming.media.azure.net/rtspv2/sass`
3. Click **Add**
4. Click **Start**
5. Click **View** — should show the remote camera's video in seconds

---

## Troubleshooting

### Camera starts then immediately stops
1. Check backend logs for the error message
2. Common causes:
   - Source invalid → fix source path
   - Camera permissions denied → restart computer or try different source
   - Camera already in use by another app → close other apps

### RTSP stream won't connect
1. Check internet connection
2. Try the Wowza URL — if it works, your network is fine
3. For custom RTSP URLs, verify:
   - URL syntax: `rtsp://ip:port/path`
   - No authentication required (add username:password if needed: `rtsp://user:pass@ip:554/stream`)
   - Firewall allows RTSP port (usually 554)

### Webcam never works
1. Try different indices: `0`, `1`, `2`, `3`
2. Restart your computer (releases camera locks)
3. Try the DirectShow syntax: `dshow://video="Your Camera Name"`
4. Check if another app is using the camera (close it)

---

## Frontend Video Feed URL

Once a camera is running, the frontend constructs this URL:
```
http://localhost:8000/video_feed/1?token={jwt_token}
```

The backend streams MJPEG frames at ~12 FPS. If you see:
- ✅ Video loading → camera is working
- ❌ Blank/loading forever → check JWT token is valid
- ❌ 401 error → token expired, refresh the page

---

## Expected Behavior

Once working:
1. **Local webcam:** You'll see your face/surroundings live in the dashboard
2. **RTSP stream:** You'll see the remote camera's feed
3. **Frame rate:** ~12 FPS is normal (smooth enough for monitoring)
4. **Detection:** After 5 frames, YOLOv8 runs — check **Events** tab to see detections

Happy testing! 🎥
