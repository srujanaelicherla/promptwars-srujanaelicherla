# LabLink Phase 12 deployment plan

Nothing in this phase was deployed. No `gcloud`, no `firebase deploy`, no Cloud Run service, no Artifact Registry, no Hosting site, no Secret Manager secret, and no Firebase/GCP project was created here.

## Plan

1. Keep production fail-closed: Firebase token verification + Firestore only (`LABLINK_ENV=production`).
2. Ship config files only: `Dockerfile`, `deploy/cloudrun.service.yaml`, Firebase Hosting SPA rewrites in `firebase.json`.
3. Faculty decide on Firestore is one transaction (request + approval + optional slot locks). Slot-lock reads still happen before writes.
4. Frontend depends on `@firebase/app` and `@firebase/auth` only (no Firestore client, no `@grpc/grpc-js`).
5. Utilization percent stays unavailable. Occupied minutes remain.

## Exact user steps before any deploy

Do these in a real Google account. This workspace did not run them.

1. Create a Firebase/GCP project. Enable Email/Password Authentication and Cloud Firestore. Note the project ID.
2. Create a Hosting site and a web app. Copy the web config into `frontend/.env` (`VITE_FIREBASE_*` only). Never put `GEMINI_API_KEY` or Admin JSON in Vite env.
3. Create a runtime service account with Firebase Admin + Firestore access. Do not commit the JSON. On Cloud Run, attach the service account instead of baking `GOOGLE_APPLICATION_CREDENTIALS` into the image.
4. Store `GEMINI_API_KEY` in Secret Manager if AI is required. Without it, `/ai/*` stays 503. That is an AI blocker, not a successful integration.
5. Set `LABLINK_CORS_ORIGINS` to the Hosting origin only (https). Do not use `*`.
6. Build the API image from the repo root (`docker build -t lablink-api .`). Push to Artifact Registry in **your** project. Deploy Cloud Run from `deploy/cloudrun.service.yaml` after replacing `YOUR_*` placeholders. Set `LABLINK_ENV=production`, `LABLINK_AUTH_MODE=firebase`, `LABLINK_PERSISTENCE=firestore`, `FIREBASE_PROJECT_ID`, `LABLINK_CORS_ORIGINS`.
7. Build the SPA with `VITE_API_BASE_URL` equal to the Cloud Run URL, then `firebase deploy --only hosting` from your machine. Hosting rewrites all routes to `index.html`.
8. Seed **production** Firestore only with an explicit, reviewed procedure. Do not copy emulator data. `cli_seed` is emulator-oriented.
9. Provision faculty with `cli_provision` or `POST /admin/users/{id}/role` as an admin. Self-register is student-only.
10. Smoke: `GET /health`, `GET /equipment`, `GET /openapi.json`. Confirm `/`, `/docs`, and `/redoc` are 404. Confirm a student cannot approve. Confirm overlapping bookings 409.

## What this phase added (not deployed)

- `Dockerfile` (non-root uid 10001, `PORT`, production env, no secrets)
- `deploy/cloudrun.service.yaml` (placeholders only)
- `firebase.json` Hosting `public: frontend/dist` and SPA rewrite `** → /index.html`
- `.env.example` production notes
- Firestore atomic `decide` + emulator concurrency tests
- Firebase JS client narrowed to Auth packages

## What was not deployed

No public URL exists from this work. No Cloud Run revision, no Hosting release, no container registry image, no production Firestore data.

## Residual before go-live

- `GEMINI_API_KEY` absent in this environment
- Browser register/sign-in still UNVERIFIED here (`VITE_FIREBASE_*` empty)
- AI rate limit is process-local
- Analytics still snapshots existing repositories (seed-scale)
- Utilization percent remains unavailable (no operating-hours schedule)
