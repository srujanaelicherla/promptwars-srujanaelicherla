# LabLink

University laboratory resource-sharing: discover equipment across departments, match projects, request access, book 15-minute slots, faculty review, waitlist/offers, and analytics from stored records. Catalog and bookings in this repo are **synthetic**.

**This repository has not been deployed.** There is no Render or Hosting URL from this work.

## Architecture

```text
Browser  ->  React (Vite) on Firebase Hosting
HTTP     ->  FastAPI on Render (no sign-in; demo student identity)
Admin SDK ->  Firestore (production). Memory store is pytest-only.
```

- Browser requests do not send Authorization. Bookings use the existing demo student `user-student-physics`.
- `X-LabLink-Demo-User` and `Bearer test:` work only when `LABLINK_AUTH_MODE=test` (pytest).
- Production (`LABLINK_ENV=production`) requires `LABLINK_PERSISTENCE=firestore`, `FIREBASE_PROJECT_ID`, and explicit `LABLINK_CORS_ORIGINS` (no `*`). The API host is Render, not Cloud Run.
- `/docs` and `/redoc` are disabled. Use `GET /openapi.json`.
- `GET /health` → `{"status":"ok","service":"lablink-api"}`.

## Setup (local)

Frontend (`frontend/`):

```bash
npm install
cp .env.example .env   # VITE_API_BASE_URL only; never put GEMINI_API_KEY here
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

Backend (`backend/.env.example`): `LABLINK_ENV`, `LABLINK_AUTH_MODE`, `LABLINK_PERSISTENCE`, `FIREBASE_PROJECT_ID`, `LABLINK_CORS_ORIGINS` (Firebase Hosting origins plus `https://YOUR_RENDER_SERVICE.onrender.com`), `LABLINK_SERVICE_NAME`, `GOOGLE_APPLICATION_CREDENTIALS` (server path, never committed), `GEMINI_API_KEY` (Render env only).

Frontend (`frontend/.env.example`): `VITE_API_BASE_URL` (local `http://127.0.0.1:8000` or the Render URL at build time).

## Security

- Slot locks: `slot_locks/{equipment_id}_{timestamp}` read-before-write in Firestore transactions. Overlap → 409. Memory tests do not prove production locking.
- Faculty `decide` on Firestore is one transaction (request status, approval `decided_at`, optional booking+locks). Slot conflict aborts the decision; the request stays pending.
- Faculty department scope; students cannot approve; self-approve forbidden.
- Firestore rules: client cannot write bookings, requests, approvals, locks, waitlist, offers.
- CORS `*` is ignored. Production requires explicit https origins.
- Do not put secrets in Vite env, git, or the Docker image. Dockerfile runs as uid 10001. `GEMINI_API_KEY` is a Render dashboard env var, not Secret Manager.

## Tests

```bash
cd frontend && npm test && npm run build
cd backend && python -m pytest
```

Critical coverage: equipment, matching, bookings (overlap/adjacent/concurrent), access requests, faculty scope, waitlist/promote, analytics (no invented utilization %), Firebase auth fixtures, CORS, AI 503 without a key, Firestore emulator transactions when the emulator is up.

## Known limits

- No Render / Hosting deploy in this workspace (see `docs/PHASE12_DEPLOYMENT.md`). Cloud Run is unused.
- Gemini is 503 until `GEMINI_API_KEY` is set on the Render service. Not a live integration.
- Utilization **percent** is unavailable (no operating-hours schedule). Occupied minutes are returned.
- There is no browser sign-in. Bookings use the demo student identity.
- AI rate limit is process-local. Analytics uses existing repository snapshots (seed-scale).
- No WCAG/browser accessibility audit was run.

## Submission checklist

- [ ] Firebase project + Firestore + Hosting created **by you** (no Cloud Run)
- [ ] Render free Web Service created **by you** from this repo (Docker)
- [ ] Production env: firestore, not test/memory, not CORS `*`
- [ ] `GEMINI_API_KEY` set on Render if AI is required
- [ ] SPA built with real `VITE_API_BASE_URL` (the Render URL)
- [ ] Production smoke: `/health`, `/equipment`, `/openapi.json`; `/docs` 404
- [ ] Emulator concurrency tests green before relying on slot locks
- [ ] No secrets in git
- [ ] Do not copy emulator data into production

If any box is unchecked, do not claim the project is submitted or publicly live.

## Docs

- `docs/PHASE11_AUDIT.md` — Phase 11 audit
- `docs/PHASE12_DEPLOYMENT.md` — Render deploy steps and what was **not** deployed
- `docs/FINAL_AUDIT.md` — six criteria, matrix, residual risk

## Technologies

React 19, TypeScript strict, Vite 8, Tailwind 4, React Router 8. Python 3.12, FastAPI, Pydantic, Uvicorn, firebase-admin 7.1.0, google-genai 1.52.0, pytest, httpx 0.28.1. Hosting: Firebase Hosting (frontend) + Render (API).
