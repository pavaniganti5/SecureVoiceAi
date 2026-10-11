# SecureVoice AI

SecureVoice AI is a safety prototype for observable person-entry events. It analyzes uploaded video with OpenCV/YOLO, stores alert metadata in MongoDB, and can generate spoken messages with Murf AI. It does not identify people, assess intent, or contact emergency services. Live webcam monitoring is not connected. This prototype is not a substitute for a professional security system.

## Local setup

Use Python 3.12 for the deployed backend and Node.js 20.19+ or 22.12+ for the Vite frontend.

From the project root in PowerShell:

```powershell
Set-Location backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Set `MONGODB_URI` to your MongoDB Atlas connection string. Set `MONGODB_DATABASE` if you want a database name other than `securevoice`. Add a Murf API key to `MURF_API_KEY` only if you want paid voice generation; the key remains backend-only. Set `FRONTEND_ORIGIN=http://localhost:5173` for local development.

If PowerShell blocks environment activation, run the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the backend from `backend`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

In a separate terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open the Vite URL, normally `http://localhost:5173`. API documentation is at `http://127.0.0.1:8000/docs`. If MongoDB is not configured or reachable, the backend starts in an unavailable state and returns a clear 503 for persistence and health checks. It does not fall back to SQLite.

## MongoDB Atlas setup and alert migration

1. Create a MongoDB Atlas cluster and a database user with read/write access to the database you selected.
2. Add the backend service's outbound IP addresses to Atlas Network Access. Avoid a global `0.0.0.0/0` allow-list for a production database.
3. Put the Atlas connection string in `MONGODB_URI`; URL-encode special characters in the username/password. Never put this value in frontend variables, source code, or logs.
4. Set `MONGODB_DATABASE=securevoice` (or your preferred name). The app creates an `alerts` collection and indexes on timestamp, source, and event type when the backend starts.
5. The existing `backend/data/alerts.db` is never removed or modified by this app. First inspect the source record count without connecting to MongoDB:

   ```powershell
   Set-Location backend
   .\.venv\Scripts\python.exe -m scripts.migrate_sqlite_to_mongodb --dry-run
   ```

6. After configuring `MONGODB_URI`, run the migration:

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.migrate_sqlite_to_mongodb
   ```

   It uses deterministic MongoDB IDs for imported SQLite rows. Running it again skips already-copied records instead of duplicating them. Existing unknown/legacy metadata remains labelled `legacy` / `unknown`. The SQLite file stays available for rollback and comparison.
7. Verify the first run reports inserted records, the second reports `0 inserted` and the same number already present, `/api/health` returns `{"status":"ok","database":"connected"}`, and `/api/alerts` returns the expected history. Do not remove the original SQLite database until you have verified the MongoDB documents and history through the API.

The API keeps the existing alert routes and response fields. New alert IDs are UUID strings; imported SQLite event IDs remain integers. Timestamps are stored as UTC BSON dates and serialized as ISO-8601 strings. History is paginated (`limit` 1–200) and sorted newest-first.

## Detection and privacy

`POST /api/detection/video` accepts MP4, MOV, AVI, MKV, and WebM uploads up to 100 MB and 120 seconds. YOLO inference runs on the backend in batches of up to four frames. Inference sampling defaults to two frames per second and can be set from one to ten frames per second in Detection settings: lower rates are faster but can miss brief entries, while higher rates inspect more detail and take longer. The result reports backend analysis processing time separately from upload and voice-generation time. The detector uses the configured normalized monitored region and confidence threshold, and applies an entry-edge cooldown before producing an alert. Temporary upload files are removed after success, error, or cancellation. Only alert metadata is stored in MongoDB; footage and snapshots are not retained by the application.

`GET /api/health` checks MongoDB availability and is suitable as a deployment health check. `GET /api/alerts` returns real saved events. `GET /api/voice/status` returns only Murf configuration status, voice ID, and model, never a key.

Murf receives only alert text, not video or frames. Generation may consume paid Murf usage. The existing user-initiated audio playback and playback-status update are preserved. Ordinary tests mock Murf and MongoDB; they do not use paid services or production credentials.

## Tests

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover Mongo-backed create/list/order/pagination, empty history, field validation, safe database errors, repeat-safe migration IDs, the existing detection/Murf route, and Murf failure handling.

## Deployment environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `MONGODB_URI` | Yes | MongoDB Atlas connection string; secret. |
| `MONGODB_DATABASE` | No | Database name; defaults to `securevoice`. |
| `MURF_API_KEY` | No | Murf key for spoken alerts; secret. Omit to disable generation. |
| `MURF_VOICE_ID` | No | Murf voice; defaults to `en-US-natalie`. |
| `FRONTEND_ORIGIN` | Yes in production | Exact Vercel frontend origin, e.g. `https://securevoice-ai.vercel.app`. Separate explicitly approved origins with commas. |
| `SECUREVOICE_YOLO_MODEL` | No | Local YOLO model path/name; defaults to `yolo11n.pt`. |
| `PORT` | Render-provided | Render's HTTP port; used in the Uvicorn start command. |

The backend `.env.example` contains placeholders only. The frontend uses `VITE_API_BASE_URL`, which is public configuration and must point to the deployed backend. Production builds do not default to localhost.

## Render resource and model notes

`render.yaml` sets the Python working directory to `backend`, installs `requirements.txt`, binds Uvicorn to `0.0.0.0:$PORT`, and uses `/api/health`. The Blueprint selects Render's legacy `standard` compute name, which Render documents as 1 CPU and 2 GB RAM. This is a paid plan; change it only after reviewing the current Render pricing and testing the workload. Render documents that Free web services spin down when idle and have an ephemeral filesystem, so they are not suitable for persistent SQLite data or dependable low-latency detection.

The YOLO `yolo11n.pt` weights are about 5.6 MB in this project and can be downloaded on first use. PyTorch, Ultralytics, and OpenCV make the installed runtime substantially larger than the model file. CPU inference may be slow and can use enough memory to pressure a 2 GB instance, especially with concurrent uploads. The configured standard instance has no GPU guarantee. Expect cold model downloads after some deployments/restarts, and benchmark the actual clip sizes and concurrency before relying on this service. Larger compute may be necessary; no reliable real-time performance is claimed.

The service filesystem is not used for persistent alert data. MongoDB Atlas provides alert persistence. Uploaded video is sent to the Render backend for analysis but is held temporarily and removed afterward.

## Deployment checklist

### Render backend

1. Push this repository to GitHub and create a Render Blueprint from it. Confirm the detected Blueprint is `render.yaml`.
2. Enter `MONGODB_URI` and `FRONTEND_ORIGIN` in the Render environment settings. Enter `MURF_API_KEY` only if you want paid voice alerts. Do not commit `.env`.
3. Confirm `MONGODB_DATABASE=securevoice`, then deploy. Wait for `/api/health` to return HTTP 200 with the MongoDB connected status.
4. If migrating old events, run the documented migration command from a secure machine with the SQLite file and the production MongoDB URI, then verify history in `/api/alerts`.
5. Test video processing on the deployed plan and review memory/CPU before sharing it.

### Vercel frontend

1. Import the GitHub repository into Vercel and set **Root Directory** to `frontend`.
2. Use build command `npm run build` and output directory `dist` (Vercel detects Vite automatically). `frontend/vercel.json` supplies the SPA fallback.
3. Add `VITE_API_BASE_URL=https://<your-render-service>.onrender.com` in Vercel project environment settings for Production (and Preview if needed), then redeploy. This value is public and contains no credentials.
4. Set Render's `FRONTEND_ORIGIN` to the exact deployed Vercel origin, including `https://` and no trailing slash. Redeploy the backend after changing CORS.
5. Verify the dashboard health card, alert history, upload analysis, and voice settings. A successful build is not proof of successful cloud connectivity.
