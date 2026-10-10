# SecureVoice AI frontend

React + Vite dashboard for SecureVoice AI.

## Run locally

```powershell
npm install
Copy-Item .env.example .env.local
```

Set `VITE_API_BASE_URL=http://127.0.0.1:8000` in `.env.local`, start the FastAPI backend separately, then run:

```powershell
npm run dev
```

The app uses real API history and integration status. It contains no sample alert rows. Live webcam monitoring is explicitly shown as not connected.

## Deploy to Vercel

Set the Vercel project root directory to `frontend`, build command to `npm run build`, and output directory to `dist`. Configure `VITE_API_BASE_URL` to the deployed Render backend origin, then redeploy. The Vite config uses localhost only for development; a production build without this setting displays a configuration error instead of calling localhost. `vercel.json` provides the single-page-app fallback.

```powershell
npm run lint
npm run build
```
