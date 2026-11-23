# LabLink Phase 11 audit

Evidence from files, pytest, live HTTP, and npm/pip checks on 23 Nov 2026 (IST). No Cloud Run deploy. No Gemini live pass. No WCAG/browser audit (computer-use agent unavailable). `.cursor/rules` not modified. Not committed.

## A. Executive verdict

LabLink implements the core laboratory workflow in this workspace: discovery, deterministic matching, project access requests, slot-locked booking, faculty scope, conflict ranking, waitlist/offers, and honest analytics (occupied minutes; utilization **percent unavailable**). It is **not submission-ready**.

Most dangerous remaining issues: missing `GEMINI_API_KEY` (AI is 503, not a working integration); Cloud Run / public production unbuilt (Phase 12); Firestore `AccessStore.decide` is not a single transaction; frontend `firebase` pulls `@grpc/grpc-js` advisories (high) with no non-breaking fix; browser register/sign-in **UNVERIFIED** because `VITE_FIREBASE_*` is empty.

Biggest scoring weaknesses: GenAI cannot be demonstrated live; utilization cannot be a percentage without operating hours; no production host.

**Verdict:** competitive prototype with real booking/auth tests; **not** a complete deployed GenAI platform.

## B. Prioritized defect list

| ID | Sev | Criterion | Status | Files | Evidence | Defect | Impact | Fix / verification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P11-001 | High | Security | Resolved | `backend/app/config.py`, `tests/test_cors.py` | `LABLINK_CORS_ORIGINS=*` was ignored but localhost was still merged with extra origins | Production extra origins still allowed Vite localhost | Browser CORS from a local page to a hosted API | Use extra origins exclusively; `*` still dropped. Tests: preflight Authorization, unknown origin, `*`, localhost excluded when extra set |
| P11-002 | Medium | Alignment | Resolved | `frontend/src/pages/EquipmentDetailPage.tsx` | Book / waitlist / request buttons only checked `signedIn` | Faculty/admin could click student-only actions and get API 403 | Dead-looking buttons | Disabled unless student (admin may book). No new browser test; API 403 already covered |
| P11-003 | High | Security / Testing | Resolved | `tests/test_bookings.py`, `tests/test_access.py` | Cancel/approve scope existed in stores; no pytest for IDOR cancel or physics→engineering approve | Gap could hide a regression | Cross-user cancel / cross-dept approve | `test_student_cannot_cancel_another_users_booking` 403; `test_physics_faculty_cannot_approve_engineering_request` 403 |
| P11-004 | Medium | Testing | Resolved | `tests/test_cors.py`, `app/main.py` | No CORS tests before Phase 11 | Connectivity regressions silent | UI “API could not be reached” on failed preflight | Authorization preflight 200 from `http://127.0.0.1:5173`; Accept listed in `allow_headers` |
| P11-005 | High | Alignment | Unresolved | `backend/app/gemini.py`, live `/ai/assistant/query` | Live POST → 503 `AI is not configured.`; pytest skip `No Gemini credentials` | No live Gemini | AI scoring / demo | Set server `GEMINI_API_KEY`. **Deployment blocker, not a successful integration** |
| P11-006 | High | Security | Unresolved | `backend/app/firestore_store.py` `FirestoreAccessStore.decide` | `get` then `bookings.create` then `set` without a request transaction | Two concurrent approves of the same request can duplicate approval writes (slot locks still block double-book) | Approval/booking consistency on Firestore | Wrap request status in a Firestore transaction; emulator race test. Memory `AccessStore` uses a lock |
| P11-007 | High | Security | Unresolved | `frontend/package.json` firebase 11.10.0 | `npm audit --omit=dev`: 4 high, `@grpc/grpc-js` via `@firebase/firestore`. Force-fix installs firebase@9 | Supply-chain advisory | Theoretical gRPC auth context issues; frontend only imports `firebase/auth` | Wait for firebase JS release; do not `audit fix --force` |
| P11-008 | Medium | Efficiency | Unresolved | `backend/app/api/analytics.py` | `snapshot()` of bookings/requests/waitlist | Unbounded reads on existing repositories | Cost at scale | Date-bounded queries (new store APIs; out of smallest-fix scope) |
| P11-009 | Medium | Accessibility | Unresolved | frontend shell | Phase 10 focus/labels/reduced-motion present; no axe/browser pass this phase | Cannot claim WCAG 2.2 AA | Scoring if judges require a live a11y run | Run axe on 5173 after Firebase is configured |
| P11-010 | High | Alignment | Unresolved | README, no Cloud Run config | Competition asks Cloud Run, Secret Manager, public deploy | Missing | Submission gate | Phase 12. Not started |
| P11-011 | Medium | Efficiency / Connectivity | Partial | `frontend/vite.config.ts` | Extra Vite on `::1:5174` was not in CORS (OPTIONS 400). Config now `host 127.0.0.1` `strictPort 5173` | Second Vite origin → fetch throws “could not be reached” | Local UI | Stop stray 5174; use 5173 only |
| P11-012 | Low | Code quality | Unresolved | `firestore_store.py`, `EquipmentDetailPage.tsx` | Large modules | Maintainability | Split later |
| P11-013 | High | Testing | Unresolved | `frontend/.env.example`, `utilities/firebase.ts` | `firebaseConfigured()` false without `VITE_FIREBASE_*`. Login shows unconfigured copy | Browser register/sign-in/sign-out **UNVERIFIED** | Journeys | Local emulator `.env` (gitignored). Not added here to avoid pretending Firebase is configured |
| P11-014 | Medium | Security | Unresolved | `backend/app/rate_limit.py` | Process-local 20/min AI limit | Not distributed | Abuse on multi-instance | Gateway quota in production |
| P11-015 | Low | Security | Unresolved | `backend/app/ai_service.py` `_INJECTION` | Regex refusal; system prompt treats retrieved docs as data | Heuristic jailbreak filter | Weak against novel injections; AI still cannot book | Keep deterministic auth |

## C. Six criterion assessments

### 1. Code quality — **Good, not excellent**

Strengths: FastAPI routers, store protocols, Pydantic `extra=forbid`, test auth vs Firebase split, seed labeled synthetic.

Defects: P11-012; `app = create_app()` at import (stale uvicorn without `--reload` served pre-analytics routes until restart).

Unverified: Cloud Run packaging.

### 2. Security — **Good locally, incomplete for production**

Strengths: Roles from `UserStore` not client; test tokens rejected in firebase mode (`test_auth.py`); booking cancel/waitlist accept IDOR checks; faculty `require_faculty_scope`; firestore.rules deny client writes on bookings/locks/waitlist; `*` CORS ignored; 16 KB body limit; `/docs` `/redoc` off; errors omit secrets.

Defects: P11-006, P11-007, P11-014, P11-015. Local uvicorn was `LABLINK_AUTH_MODE=test` (intentional for API journeys; must not be production).

### 3. Efficiency — **Acceptable for seed scale**

Strengths: no chart library; dashboard `Promise.all` of three GETs; slot keys not full-table overlap scans for booking.

Defects: P11-008; JS bundle **438.90 kB** (gzip 129.53 kB), CSS 14.96 kB; firebase dominates.

### 4. Testing — **Strong API, weak live AI/browser**

Baseline (before edits): **108 passed, 1 skipped**. After fixes, first full run: **114 passed, 1 skipped**. Repeat: **114 passed, 1 skipped**. Skip: `tests/test_ai.py::test_live_gemini_smoke` — No Gemini credentials. Emulator tests ran (host up). Non-emulator isolation still in `conftest.py`. Frontend: **8 passed**. No coverage of browser Firebase.

### 5. Accessibility — **Partial**

Strengths: skip link, `aria-expanded` menu, Escape returns focus, `min-h-11`, `:focus-visible`, `prefers-reduced-motion`, labeled dashboard dates, login `aria-describedby` on error.

Defects: P11-009; no dialogs to trap; EquipmentDetail booking form still shown while disabled for faculty.

### 6. Problem statement alignment — **Partial**

Core booking/approval/matching exist. Utilization percent honestly omitted. Gemini not live. Cloud Run missing. Metrics labeled `demo`/`synthetic`.

## D. Requirement matrix (11 items)

| Requirement | Implementation | Evidence/Files | Status | Gap | Recommended fix |
| --- | --- | --- | --- | --- | --- |
| Cross-department discovery | `GET /equipment` filters | Live 200, 9 items, 3 departments; `api/equipment.py` | FULL | Catalog is synthetic | Keep `demo` labeling |
| Intelligent matching | Deterministic `rank_matches` | `GET /projects/proj-raman/equipment-matches` 200; `app/matching.py` | FULL | Not live availability | Do not replace with unconstrained LLM ranking |
| Project-based access requests | `POST/GET /access-requests` | Live 201 laser request; `api/access.py` | FULL | Justification quality not graded | — |
| Slot booking | Slot locks 15 min | Live 201/409/adjacent 201; emulator overlap/concurrent | FULL | Memory lock ≠ production | Emulator remains the distributed proof |
| Faculty approvals | Approve/reject + scope | Live reject 200; physics cannot approve engineering (pytest 403) | FULL | Firestore decide race P11-006 | Transaction |
| Fair conflict resolution | Weighted rank | `test_access.py` deadline order; `conflicts.py` WEIGHTS | FULL | Scores catalog-only | Keep explanation text |
| Deadline-aware scheduling | Recommendations + waitlist | Live cancel→auto-promote offer; `waitlist.py` | PARTIAL | No operating hours; promote is not a job | Do not invent calendars |
| Resource utilization | Analytics occupied minutes | `GET /analytics/*` 200 admin, 403 student; percent null | PARTIAL | Denominator unknown | Configure hours or keep unavailable |
| Specialized resource access | Restricted equipment 403 without prerequisites | `test_bookings.py`; faculty verify via approval | PARTIAL | No training-record store | Keep faculty loop |
| Cross-department collaboration | Discovery + scoped faculty | Physics analytics only `dept-physics` live | PARTIAL | No shared production tenant | Phase 12 |
| GenAI + RAG | Routes + fake tests + corpus | Live 503; pytest skip live smoke; `ai_service.py` | PARTIAL / **blocker** | No `GEMINI_API_KEY` | Provision secret; do not fake success |

## E. Risk matrix

| Risk | Criterion | Severity | Likelihood | Impact | Files | Mitigation |
| --- | --- | --- | --- | --- | --- | --- |
| Submit without Gemini | Alignment | High | Certain now | AI criterion fail | gemini.py | Blocker |
| Submit without Cloud Run | Alignment | High | Certain now | Competition constraint fail | README | Phase 12 |
| Firestore dual approve | Security | High | Medium on emulator load | Duplicate approvals | firestore_store.py | Transaction |
| `LABLINK_AUTH_MODE=test` in prod | Security | Critical if shipped | Low if default firebase | Token impersonation | authn.py | Default firebase; never test on Cloud Run |
| npm grpc advisory | Security | High advisory / low exploit here | Unknown | Supply chain | firebase | Pin until upstream |
| CORS miss on odd Vite port | Connectivity | Medium | Seen on :5174 | Blank catalog | config.py | strictPort 5173 |
| Unbounded analytics | Efficiency | Medium | High at scale | Timeout/cost | analytics.py | Bounded queries |

## F. Changes made (Phase 11)

- CORS: extra origins exclusive; `*` ignored; Accept on allow_headers; tests.
- Equipment detail: disable book/waitlist/request unless role allows.
- Regression: cancel IDOR, faculty department approve, CORS, AI 503 message (`answer` absent).
- Vite server pinned `127.0.0.1:5173` strictPort.
- Restarted local uvicorn so `/analytics/*`, `/waitlist`, `/scheduling/*` match current OpenAPI (25 paths). Stale process had been 404 for those routes.

## G. Verification summary

**Inspected (non-exhaustive):** `app/{main,config,authn,security,errors,bookings,access,waitlist,analytics,ai_service,gemini,conflicts,matching,rate_limit,firestore_store}.py`, `api/*`, `tests/{conftest,test_firestore_emulator,test_analytics,test_cors,test_access,test_bookings,test_ai,test_auth,test_health}.py`, `firestore.rules`, `firestore.indexes.json`, `firebase.json`, frontend `api.ts`, `config.ts`, `firebase.ts`, `Auth.tsx`, `App.tsx`, `EquipmentDetailPage.tsx`, `AccessRequestsPage.tsx`, `DashboardPage.tsx`, `AssistantPage.tsx`, `vite.config.ts`, `package.json`, README.

**Tests executed**

| Run | When (IST) | Result |
| --- | --- | --- |
| Baseline pytest (before edits) | 15:24 | **108 passed, 1 skipped** |
| Focused new tests | 15:27 | **27 passed** |
| Full pytest after edits | 15:28 | **114 passed, 1 skipped** |
| Repeat full pytest | 15:28 | **114 passed, 1 skipped** |
| Skip reason | both full runs | No Gemini credentials |
| Frontend vitest | 15:28 | **8 passed** |
| `tsc -b && vite build` | 15:28 | success; JS 438.90 kB / gzip 129.53 kB |

**Live HTTP (after restart, `127.0.0.1:8000`, auth_mode=test, memory):** `/health` 200; `/` `/docs` `/redoc` 404; `/openapi.json` 25 paths including analytics/waitlist/scheduling; `/equipment` 200 CORS ACAO `http://127.0.0.1:5173`; `/me` 401 without token, 200 test student; booking 201, overlap 409, adjacent 201; waitlist 201; physics promote engineering 403; cancel 200 then offer present (cancel path auto-promotes); faculty reject 200; student analytics 403; AI 503; student role POST 403; bootstrap extra `role` 422. Vite `127.0.0.1:5173` HTML 200.

**Emulator:** Firestore+Auth up; pytest emulator cases included in 114.

**Dependencies:** `pip check` clean. `npm audit --omit=dev` 4 high (P11-007).

**Not executed:** browser register/sign-in, axe, live Gemini, Cloud Run, Secret Manager, production URL.

## Remaining blockers / submission readiness

1. `GEMINI_API_KEY` absent — AI deployment blocker.
2. No Cloud Run / public URL — competition constraint (Phase 12).
3. Browser Firebase unconfigured — student UI auth UNVERIFIED.
4. P11-006 Firestore decide race.
5. P11-007 npm high advisories.
6. Utilization percent unavailable (honest).

**Submission-ready: no.**
