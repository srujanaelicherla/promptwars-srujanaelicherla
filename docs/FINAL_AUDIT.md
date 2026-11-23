# LabLink final audit (Phase 12)

Evidence from this workspace on 23 Nov 2026 (IST). **Not submission-ready. Nothing was deployed.** No WCAG claim. No live Gemini pass. `.cursor/rules` unchanged. Not committed.

## A. Executive verdict

Core laboratory workflows are implemented and tested locally, including atomic Firestore faculty decisions on the emulator. Production is **not** live. Gemini is 503 without a server key. Browser Firebase UI is unconfigured in this environment.

**Verdict: NOT ready to submit.**

## B. Six criteria

| Criterion | Rating | Evidence |
| --- | --- | --- |
| Code quality | Good | Routers, stores, Pydantic `extra=forbid`, production fail-closed |
| Security | Good locally | Token roles from UserStore; CORS `*` rejected; production refuses test auth and memory; decide is transactional on Firestore |
| Efficiency | Acceptable | Auth-only Firebase client; JS rebuild after dep change; analytics still full snapshots |
| Testing | Strong API | Pytest twice after Phase 12 edits; emulator decide races; vitest; no browser E2E (no Playwright/computer-use) |
| Accessibility | Partial | Phase 10/11 shell work; no axe/browser pass this phase |
| Alignment | Partial | Booking/matching/approvals/waitlist/analytics exist; GenAI and Render undemonstrated |

## C. Defects

| ID | Sev | Status | Notes |
| --- | --- | --- | --- |
| P11-006 | High | **Resolved** | `FirestoreAccessStore._decide_in_transaction`: request + approval + slot locks in one txn; reads before writes; slot conflict leaves request pending. Emulator tests 200/409 |
| P11-007 | High | **Resolved in tree** | `firebase@11.10.0` → `@firebase/firestore@4.8.0` → `@grpc/grpc-js@1.9.16` (4 high). Code imported only `firebase/auth`. Replaced with `@firebase/app@0.13.2` + `@firebase/auth@1.10.8` (same versions firebase 11.10.0 already used). `npm ls @grpc/grpc-js` empty. `npm audit --omit=dev`: 0. Did **not** run `npm audit fix --force`. Did **not** jump to firebase 13 (major) |
| P11-005 | High | Unresolved | No `GEMINI_API_KEY`; `/ai/*` 503; live pytest skipped |
| P11-010 | High | Config only | Dockerfile + Render Web Service + Hosting rewrites. Cloud Run YAML unused. **Not deployed** |
| P11-013 | High | Unresolved | `VITE_FIREBASE_*` empty; browser auth UNVERIFIED |
| P11-008 | Medium | Unresolved | Analytics `snapshot()` unbounded |
| P11-009 | Medium | Unresolved | No WCAG/browser audit |
| P11-014 | Medium | Unresolved | Process-local AI rate limit |
| Utilization % | — | Honest | Still unavailable; occupied minutes only |

## D. Requirement matrix

| Requirement | Status | Evidence |
| --- | --- | --- |
| Cross-department discovery | FULL | `GET /equipment`; tests |
| Intelligent matching | FULL | Deterministic matcher tests; not live availability |
| Project-based access requests | FULL | Access API tests |
| Slot booking | FULL | Memory + emulator overlap/concurrent |
| Faculty approvals | FULL | Memory tests + emulator concurrent decide |
| Fair conflict resolution | FULL | Weighted rank tests |
| Deadline-aware scheduling | PARTIAL | Recommendations/waitlist; no operating hours; promote is not a job |
| Resource utilization | PARTIAL | Occupied minutes; percent unavailable |
| Specialized resource access | PARTIAL | Restricted 403; faculty loop; no training store |
| Cross-department collaboration | PARTIAL | Scoped faculty; no production tenant |
| GenAI + RAG | PARTIAL / blocker | Fake tests; live 503; skip `test_live_gemini_smoke` |

FULL only where tests/HTTP in this repo support it.

## E. Risks

| Risk | Mitigation left to the user |
| --- | --- |
| Submit without Render URL | Deploy per `docs/PHASE12_DEPLOYMENT.md` |
| Submit without Gemini | Render env `GEMINI_API_KEY` |
| `LABLINK_AUTH_MODE=test` on Render | Image defaults firebase + `LABLINK_ENV=production` refuse test/memory |
| Copying emulator data to prod | Do not; seed explicitly |
| Browser auth untested here | Configure `VITE_FIREBASE_*` and walk register/sign-in |

## F. Tests (this phase, IST 23 Nov 2026)

| Run | Result |
| --- | --- |
| First full pytest (clean env, emulator host set, `demo-lablink`) | **121 passed, 1 skipped** (9.31s) |
| Second full pytest (same clean env) | **121 passed, 1 skipped** (7.04s) |
| Skip | `tests/test_ai.py::test_live_gemini_smoke` — No Gemini credentials |
| Frontend vitest | **8 passed** (3 files) |
| `tsc -b && vite build` | success; JS 438.87 kB / gzip 129.52 kB |
| `npm audit --omit=dev` | **0 vulnerabilities** |

Emulator decide tests included in both full runs: concurrent same-request approve, student/out-of-scope 403, approve vs existing slot lock (request stays pending), concurrent approve+reject. Focused emulator+production-config run earlier: 10 passed.

## G. npm audit investigation (P11-007)

| Item | Value |
| --- | --- |
| Before | `firebase@11.10.0` → `@firebase/firestore@4.8.0` → `@grpc/grpc-js@1.9.16` |
| Advisories | GHSA-m9gg-hp2v-232j, GHSA-f596-whhp-79r4 (high); `npm audit fix --force` wanted firebase@9 |
| Reachable? | **No** from LabLink TS: only `@firebase/app` / `@firebase/auth` imports. No `firebase/firestore` |
| Safe bump | Drop the `firebase` meta-package; pin the Auth packages firebase 11.10.0 already used. Not firebase 13 (major). Not `--force` |
| After | `@grpc/grpc-js` absent; `npm audit --omit=dev` 0 |

Residual: if someone re-adds `firebase` (full SDK), grpc-js returns.

## H. Submission readiness

**NOT ready.** No public URL. No Gemini live. Browser auth UNVERIFIED. Utilization percent unavailable by design until a real schedule exists.
