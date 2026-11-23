# LabLink

University laboratory resource-sharing: discover equipment across departments, match projects, request access, book 15-minute slots, faculty review, waitlist/offers, and analytics from stored records. Catalog and bookings in this repo are **synthetic**.

**This repository has not been deployed.** There is no Cloud Run or Hosting URL from this work.

## Architecture

```text
Browser  ->  React (Vite) + Firebase Auth client (@firebase/app, @firebase/auth)
HTTP     ->  FastAPI Bearer ID token
Admin SDK ->  Auth verify + Firestore (production). Memory store is pytest-only.
```

- Roles come from the server `UserStore`, never from the client.
- `X-LabLink-Demo-User` and `Bearer test:` work only when `LABLINK_AUTH_MODE=test` (pytest).
- Production (`LABLINK_ENV=production`) requires `LABLINK_AUTH_MODE=firebase`, `LABLINK_PERSISTENCE=firestore`, `FIREBASE_PROJECT_ID`, and explicit `LABLINK_CORS_ORIGINS` (no `*`).
- `/docs` and `/redoc` are disabled. Use `GET /openapi.json`.
- `GET /health` → `{"status":"ok","service":"lablink-api"}`.

## Setup (local)

Frontend (`frontend/`):

```bash
npm install
cp .env.example .env   # fill VITE_FIREBASE_* for sign-in; never put GEMINI_API_KEY here
npm test
npm run dev            # 127.0.0.1:5173
```

Backend (`backend/`):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Emulators (project `demo-lablink` only):

```bash
firebase emulators:start --only auth,firestore --project demo-lablink
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 FIREBASE_PROJECT_ID=demo-lablink \
  python -m app.cli_seed --confirm SYNTHETIC-DEV-ONLY --emulator-only
```

## Environment variables

Backend (`backend/.env.example`): `LABLINK_ENV`, `LABLINK_AUTH_MODE`, `LABLINK_PERSISTENCE`, `FIREBASE_PROJECT_ID`, `LABLINK_CORS_ORIGINS`, `LABLINK_SERVICE_NAME`, `GOOGLE_APPLICATION_CREDENTIALS` (server path, never committed), `GEMINI_API_KEY` (server only).

Frontend (`frontend/.env.example`): `VITE_API_BASE_URL`, `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_APP_ID`, optional `VITE_FIREBASE_AUTH_EMULATOR_URL` for local Auth emulator only.

## Security

- Slot locks: `slot_locks/{equipment_id}_{timestamp}` read-before-write in Firestore transactions. Overlap → 409. Memory tests do not prove production locking.
- Faculty `decide` on Firestore is one transaction (request status, approval `decided_at`, optional booking+locks). Slot conflict aborts the decision; the request stays pending.
- Faculty department scope; students cannot approve; self-approve forbidden.
- Firestore rules: client cannot write bookings, requests, approvals, locks, waitlist, offers.
- CORS `*` is ignored. Production requires explicit https origins.
- Do not put secrets in Vite env, git, or the Docker image. Dockerfile runs as uid 10001.

## Tests

```bash
cd frontend && npm test && npm run build
cd backend && python -m pytest
```

Critical coverage: equipment, matching, bookings (overlap/adjacent/concurrent), access requests, faculty scope, waitlist/promote, analytics (no invented utilization %), Firebase auth fixtures, CORS, AI 503 without a key, Firestore emulator transactions when the emulator is up.

## Known limits

- No Cloud Run / Hosting / Secret Manager in this workspace (see `docs/PHASE12_DEPLOYMENT.md`).
- Gemini is 503 until `GEMINI_API_KEY` is set on the server. Not a live integration.
- Utilization **percent** is unavailable (no operating-hours schedule). Occupied minutes are returned.
- Browser register/sign-in is UNVERIFIED until `VITE_FIREBASE_*` is filled.
- AI rate limit is process-local. Analytics uses existing repository snapshots (seed-scale).
- No WCAG/browser accessibility audit was run.

## Submission checklist

- [ ] Firebase/GCP project, Auth, Firestore, Hosting, Cloud Run created **by you**
- [ ] Production env: firebase + firestore, not test/memory, not CORS `*`
- [ ] `GEMINI_API_KEY` in Secret Manager if AI is required
- [ ] SPA built with real `VITE_API_BASE_URL` (Cloud Run)
- [ ] Production smoke: `/health`, `/equipment`, `/openapi.json`; `/docs` 404
- [ ] Emulator concurrency tests green before relying on slot locks
- [ ] No secrets in git
- [ ] Do not copy emulator data into production

If any box is unchecked, do not claim the project is submitted or publicly live.

## Docs

- `docs/PHASE11_AUDIT.md` — Phase 11 audit
- `docs/PHASE12_DEPLOYMENT.md` — deploy plan and what was **not** deployed
- `docs/FINAL_AUDIT.md` — six criteria, matrix, residual risk

## Technologies

React 19, TypeScript strict, Vite 8, Tailwind 4, React Router 8, `@firebase/app` 0.13.2, `@firebase/auth` 1.10.8. Python 3.12, FastAPI, Pydantic, Uvicorn, firebase-admin 7.1.0, google-genai 1.52.0, pytest, httpx 0.28.1.
