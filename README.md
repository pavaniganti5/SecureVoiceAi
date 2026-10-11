# SecureVoice AI

> Privacy-first smart security monitoring prototype combining **YOLOv11** computer vision, **Murf AI** dynamic voice generation, and **MongoDB Atlas** alert auditing.

---

## 🎬 Sample Demo Video Included

For project evaluation, review, and demonstration, a sample security video is included directly within the project:

- **Repository Path**: [`demo/demo-security-video.mp4`](demo/demo-security-video.mp4)
- **Frontend Public Asset**: [`frontend/public/demo-security-video.mp4`](frontend/public/demo-security-video.mp4)
- **Specifications**: 10.0 seconds, MP4 (H.264), 768×576, 10 FPS, ~703 KB.
- **Benchmark**: Detects 237 person bounding boxes and 1 monitored region entry event in under 3 seconds.

### Testing with 1 Click in the App
1. Open the web application (local or deployed on Vercel).
2. Under **Video Analysis**, click **"Load Sample Video"**.
3. The video immediately loads into the built-in HTML5 player.
4. Click **"Start analysis"** to run YOLO detection and voice alert synthesis.
5. You can also click **"Download Clip"** to save the video locally.

---

## 🚀 Deployed Architecture

- **Frontend**: Deployed on **Vercel** (React + Vite single-page dashboard).
- **Backend API**: Deployed on **Render** (FastAPI, Uvicorn, YOLOv11 inference, Murf AI, OpenCV Headless).
- **Database**: **MongoDB Atlas** for persistent security event logs.

---

## 🛠️ Resolving "Fail to Fetch" on Deployed Sites

If your deployed Vercel frontend displays `Failed to fetch` or `Unable to connect to backend`, check the following:

### 1. Render Free-Tier Spin-Down (Cold Start)
- On Render's free tier, services automatically go to sleep after 15 minutes of inactivity.
- The first request after sleeping takes **40–60 seconds** to wake up.
- **Solution**: In the web app under **Integration Settings**, click **"Test & Wake Backend"**. This pings the server and wakes it up. Once connected (green status), run video analysis.

### 2. CORS (Cross-Origin Resource Sharing)
- The backend in `backend/app/main.py` is configured with `allow_origins=["*"]` by default when `FRONTEND_ORIGIN` is not set or set to `*`.
- In `render.yaml`, `FRONTEND_ORIGIN` is set to `*`.
- If you have set `FRONTEND_ORIGIN` in the Render dashboard, ensure it includes your Vercel URL (e.g. `https://your-site.vercel.app`) without trailing slashes.

### 3. Backend API URL Configuration
- In the web app under **Integration Settings**, you can view and edit the Backend API URL live.
- If you didn't configure `VITE_API_BASE_URL` in Vercel project settings, simply paste your Render URL (e.g. `https://securevoice-api.onrender.com`) into the **Configure URL** input and click **Save URL**. It will save to your browser's local storage and connect immediately.

---

## 💻 Local Setup

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.
