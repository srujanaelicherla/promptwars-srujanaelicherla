# LabLink API deployment (Render)

Nothing in this phase was deployed. This workspace did not create a Render service, Firebase Hosting release, or GCP resource.

The supported API host is a **Render free Web Service**. Do not use Cloud Run, Artifact Registry, Cloud Build, or Secret Manager. `deploy/cloudrun.service.yaml` is unused. Firebase Hosting remains the frontend host (`firebase.json`).

The Docker image already runs FastAPI with `uvicorn` on `0.0.0.0:$PORT`.

## Exact user steps (Render dashboard)

1. Open [Render](https://dashboard.render.com) and sign in.
2. **New +** → **Web Service**.
3. Connect this GitHub repository.
4. Runtime: **Docker**. Leave the Dockerfile path as `./Dockerfile` (repo root). Instance: **Free**.
5. Create the service. Render builds the image and sets `PORT`.
6. In **Environment**, set (names only here; values stay in the dashboard, never in git):
   - `LABLINK_ENV` = `production`
   - `LABLINK_AUTH_MODE` = `firebase`
   - `LABLINK_PERSISTENCE` = `firestore`
   - `FIREBASE_PROJECT_ID` = your Firebase project id
   - `LABLINK_CORS_ORIGINS` = `https://lablink-6f3a6.web.app,https://lablink-6f3a6.firebaseapp.com,https://YOUR_RENDER_SERVICE.onrender.com`
   - `GEMINI_API_KEY` = your Gemini key (optional; `/ai/*` is 503 without it)
   - `GOOGLE_APPLICATION_CREDENTIALS` = path to a Firebase Admin JSON **secret file** you upload in Render (not Secret Manager)
7. Copy the `*.onrender.com` URL. Put that same URL in `LABLINK_CORS_ORIGINS` and in `frontend/.env` as `VITE_API_BASE_URL`.
8. Build the SPA (`npm run build` in `frontend/`) and deploy Hosting from your machine: `firebase deploy --only hosting`. Do not deploy the API to Hosting.
9. Smoke: `GET /health`, `GET /equipment`, `GET /openapi.json`. `/docs` and `/redoc` stay 404.

Python-native alternative (if you skip Docker): root directory `backend`, start command `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`, same env vars.

## What this phase added (not deployed)

- `Dockerfile` (non-root uid 10001, `PORT`, no secrets)
- `render.yaml` Blueprint (not applied here)
- `firebase.json` Hosting `public: frontend/dist` and SPA rewrite `** → /index.html`
- `deploy/cloudrun.service.yaml` marked unused

## What was not deployed

No public URL exists from this work. No Render service, no Hosting release, no Cloud Run revision.
