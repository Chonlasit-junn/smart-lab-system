# Shared access rules, Login and registration AI

This change requires no migration. It changes source code only; deployment
secrets, real user records and production configuration have not been changed.

## Access contract

`backend/access_policy.py` is the read-only source for account eligibility,
active bans and the current Lab booking. It is used by Login, password recovery,
web booking/point status, Agent session start/recovery/heartbeat and Gatekeeper.

| Condition | Login / recovery | New booking | Gatekeeper / Agent start |
| --- | --- | --- | --- |
| Guest pending or missing approval | Deny | Deny | Deny |
| No role and no approved passport | Deny | Deny | Deny |
| Inactive student or inactive passport | Deny | Deny | Deny |
| Active ban | Allow profile/support/recovery | Deny | Deny |
| Approved, no ban | Allow | Existing slot/capacity rules | Current booking required |

- Role priority is Admin, Student, Guest, then custom roles. Login and profile
  agree; Admin is still subject to Lab admission rules when using a Lab.
- Bangkok booking start is inclusive; end is exclusive. Reserved and attended
  bookings allow entry; only a reserved booking can start a new Agent session.
  Recovery must belong to that same current booking and registered workstation.
- Gatekeeper still records the denial/grant and still requires face/liveness.
- Heartbeat revocation returns 409 so existing Agents lock back to Login. A
  revoked session has no completion bonus; normal booking expiry uses the
  existing idempotent completion event. Queued authenticated telemetry can still
  upload after closure. The Agent also handles a revoked device's 403.
- Account eligibility is checked on actions, not encoded permanently in a JWT.
  Existing tokens cannot bypass later withdrawal of Guest approval or a ban.

## Login and runtime configuration

`backend/login_security.py` limits attempts before user lookup/password hashing:

- Per normalized account: 10 attempts / 300 seconds, across IP addresses.
- Per IP: 60 attempts / 60 seconds, across accounts.
- Whole API process: 300 attempts / 60 seconds.
- HTTP 429 includes `Retry-After`. Successful attempts count too; they do not
  reset another caller's budget. Counters use monotonic time, a lock, hashed
  identifiers and at most 4,096 entries. Exhausted capacity fails closed.
- Unknown users still run a dummy password verification. Wrong credentials and
  malformed stored hashes return the same 401 message. Login does not impose
  the new-password minimum on existing passwords, but rejects over 72 UTF-8 bytes.

The limiter is **per process and resets on restart**. It fits the current single
Uvicorn worker. Before adding workers/replicas, move these budgets to a shared
gateway/store. The application trusts only `request.client`, never arbitrary
`X-Forwarded-For`. Configure Uvicorn's trusted proxy addresses for the deployment
before relying on distinct client IPs; do not trust every internet peer.

`backend/security_config.py` owns JWT configuration for both signing and reading.
The Docker image marks `SMART_LAB_ENV=production`; `SPACE_ID` also identifies HF.
Any non-development mode requires production settings:

1. `SECRET_KEY`: stable, private random key, at least 32 UTF-8 bytes. An existing
   compliant key is used unchanged. Missing/short values stop startup; the old
   hardcoded fallback is removed. No code can prove that a long key is random.
2. `CORS_ALLOWED_ORIGINS`: comma-separated exact frontend origins, for example
   `https://web.example.com,https://preview.example.com`. Production requires
   HTTPS; no wildcard, path, credentials, query or fragment. Include every
   custom domain/preview origin users will actually open. CORS is browser policy,
   not a replacement for API authentication.

These values must be checked **before deploying** this patch. No production
values were read or changed for this task. Retaining a compliant JWT key keeps
current sessions; replacing it invalidates existing tokens and needs a planned
login transition. Do not rotate `OTP_SECRET_KEY` as part of this change.

Local development with no JWT key uses a random key for that process (restart
requires login again); default CORS allows localhost/127.0.0.1 on 5173 and 5174.
An explicitly configured short key is rejected in development too.

### Origin enforcement behind the Hugging Face proxy

Live read-only checks on 2026-10-28 found that `hf.space` returned an echoed
`Access-Control-Allow-Origin` for an unlisted origin on both OPTIONS and GET.
Therefore browser CORS response headers alone do not establish enforcement.

`backend/cors_middleware.py` now checks the incoming HTTP `Origin` against the
same `CORS_ALLOWED_ORIGINS` before routing, authentication, request-body parsing
or database work. An unlisted, empty, opaque (`null`) or repeated Origin receives
403 with a generic JSON error and `Cache-Control: no-store`. Allowed origins
keep the existing CORS preflight, response headers and request behavior.

Requests without Origin remain supported for native Agent/Gatekeeper clients,
health checks and server calls. They still require the existing credentials on
protected routes. Origin is a browser safeguard, not proof of client identity:
custom clients can omit or forge it, so JWT/device/session checks remain required.
Browser tools on another origin, including Swagger's Try it out on the backend
domain, require that exact origin in the configured list if they send Origin.

The upstream may continue to return 200 for OPTIONS or permissive CORS headers.
After deployment, verify actual GET requests: `/` with an allowed origin must
return 200; an unlisted origin must return 403 and no application data. Requests
to `/users/me` without credentials must still return 401 when the Origin is
allowed or absent. These probes need no login, data changes or migration.

Regression tests simulate an edge that answers every preflight and overwrites
CORS response headers, then confirm that untrusted GET/POST requests still return
403 without invoking authentication or endpoint handlers. They also cover
allowed browser requests, native form/file uploads, missing credentials,
ambiguous origins, unchanged lifespan events and rejection without reading bodies.

From `backend`, using the isolated environment described below:

```powershell
.\venv\Scripts\python.exe -B -m unittest discover -s tests -p test_cors_middleware.py
.\venv\Scripts\python.exe -B -m unittest discover -s tests -p test_security_config.py
.\venv\Scripts\python.exe -B -m unittest discover -s tests -p test_access_policy.py
```

## Registration AI

Image decoding/resizing, DeepFace and password hashing run in a worker via
`run_in_threadpool`. Registration and Gatekeeper share one bounded inference
slot per process, with a 250 ms acquisition timeout instead of an unbounded queue.
Busy requests receive 503 + `Retry-After: 1`; the client can retry with the same
OTP if it remains valid. Recognition thresholds and the model are unchanged.

OTP preflight commits and releases the DB connection before waiting for AI.
The worker never uses the DB session. Temporary inference images are removed in
`finally`. Account creation rechecks the exact OTP issuance at commit, preserving
expiry/replacement/consumption rules and storage rollback. Avatars remain small.

Web Login/Register and Agent Login show the new errors appropriately. The web
keeps Thai/English translations and does not send AI-busy errors back to OTP entry.

## Regression checks

Use an isolated process with a synthetic `SECRET_KEY`,
`SMART_LAB_ENV=development`, `SQLALCHEMY_DATABASE_URL=sqlite:///:memory:` and an
empty `SMART_LAB_TEST_POSTGRES_URL`. Never use application production credentials.

From `backend`:

```powershell
.\venv\Scripts\python.exe -B -m unittest discover -s tests
```

From `smart-lab-agent` (set TEMP/TMP to the workspace `tmp` folder if the Windows
sandbox's system temp directory blocks SQLite):

```powershell
.\venv\Scripts\python.exe -B -m unittest discover -s tests -p test_agent_http_policy_grace.py
```

From `frontend`:

```powershell
node --test tests/loginFeedback.test.js tests/registrationOtp.test.js
node node_modules/eslint/bin/eslint.js src/pages/Login.jsx src/utils/loginFeedback.js src/utils/registrationOtp.js src/utils/locales.js tests/loginFeedback.test.js tests/registrationOtp.test.js
npm run build
```

Coverage includes cross-surface denials, stale tokens, exact booking/ban bounds,
session recovery/revocation, completion idempotency, limiter concurrency and
expiry, safe configuration/CORS, AI busy/failure cleanup, event-loop responsiveness
and released DB transactions while inference waits. PostgreSQL concurrency tests
remain opt-in and are not run against a real database by this workflow. Real
camera accuracy, production proxy behavior and load capacity still need QA.

### Results on 2026-10-28

- Backend full discovery: 260 cases, 250 passed, 10 opt-in PostgreSQL cases skipped.
  After adding the commit-race regression, all 13 access-policy cases passed
  again (251 distinct Backend cases verified in total).
- Agent HTTP/policy/grace suite: 53 passed. The first run encountered a Windows
  sandbox temp-directory permission error in the SQLite outbox test; rerunning
  with TEMP/TMP in the workspace passed without changing outbox behavior.
- Frontend targeted tests: 8 passed; targeted ESLint passed.
- `npm run build`: passed. Vite reported plugin timing overhead; no >500 kB
  chunk warning. No visual/animation changes were made in this patch.
- `git diff --check`: passed. No migration or real database operation was run.

### Release snapshot verification on 2026-10-28

The release includes the required Agent booking checks and Login/heartbeat
feedback. Unrelated pending UI, executable-name tracking and repeat-violation
changes remain in the working tree and are not part of this commit.

An isolated copy of exactly the selected source files was checked:

- Backend: 249 distinct tests passed; 10 PostgreSQL cases skipped. The first
  discovery found a missing shared-domain fixture in the temporary copy; after
  copying the existing tracked fixture, all four affected domain tests passed.
  No application change was needed for that test setup issue.
- Agent HTTP/policy/grace: 38 passed against the selected source version.
- Frontend Login/Register: 8 passed; targeted ESLint and production build passed.
  The largest build chunk was 283.49 kB (86.06 kB gzip).
- Existing dependency folders were reused; no dependencies or lockfiles changed.

### Files changed for this task

- Shared/security modules: `backend/access_policy.py`, `login_security.py`,
  `security_config.py`, `face_service.py`, `utils.py`, `main.py`, `Dockerfile`.
- API integration: `backend/routers/auth.py`, `users.py`, `password_reset.py`,
  `labs.py`, `points.py`, `agent.py`, `gatekeeper.py`.
- Backend tests: new `test_access_policy.py`, `test_login_security.py`,
  `test_security_config.py`; updated registration OTP, password reset (including
  the opt-in PostgreSQL fixture), email normalization, booking, points, device
  registration and Agent telemetry fixtures/checks.
- Web: `frontend/src/pages/Login.jsx`, `src/utils/loginFeedback.js`,
  `src/utils/registrationOtp.js`, `src/utils/locales.js`, and their two targeted
  test files.
- Agent: `smart-lab-agent/agent.pyw` and
  `smart-lab-agent/tests/test_agent_http_policy_grace.py`.
- This document. Earlier uncommitted Agent/UI changes were preserved.

Background references: [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)
and [OWASP Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).
