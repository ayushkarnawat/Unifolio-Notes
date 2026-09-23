# Handoff: staging-code-blockers

**Status:** COMPLETE (2026-09-02 — all six scoped items implemented and verified)
**Parent plan:** `AWS Readiness/aws-golive-readiness-report.md` (§4, §16 step 2, §18 Monday/Tuesday "Backend code" rows), `AWS Readiness/aws-golive-launch-blockers.md`
**Dispatch mode:** User is running this directly in their own Codex CLI/app session (not via Claude's `codex:codex-rescue` Agent dispatch) — this doc is still the source of truth both sides read; update `Status` here after Codex finishes and report back.

## Task

Five independent, bounded code fixes that unblock building and deploying the backend to AWS staging. All five are described in full, with exact file:line evidence, in `AWS Readiness/aws-golive-launch-blockers.md` — read that file first for the "why," this doc scopes exactly what to change.

1. **CORS: read allowed origins from an env var, not a hardcoded localhost list.**
   `backend/app/main.py:30-42` currently hardcodes `allow_origins` to a fixed list of localhost ports plus a localhost-only regex. Add an `allowed_origins: str = ""` field to `Settings` in `backend/app/config.py` (comma-separated string, matching the existing pattern of `frontend_base_url`/`google_oauth_client_id` in that same file), and pass `[o.strip() for o in settings.allowed_origins.split(",") if o.strip()]` as `allow_origins` in `main.py`. Keep the existing localhost list as the *default* when the env var is unset, so local dev is unaffected — don't just replace it outright. `allow_credentials=True` stays as-is (this app uses Bearer-token-in-header auth via `localStorage`, never cookies, so no CSRF-via-cookie implication).

2. **Host bind: the container must bind `0.0.0.0`, not `127.0.0.1`.**
   `backend/scripts/run_server.py:22` hardcodes `host="127.0.0.1"`. This script is the local-dev launcher and its Windows-specific `ProactorEventLoop` handling (lines 14-19) is there for Playwright subprocess support on Windows — do not touch that. For the container path: the Dockerfile's entrypoint (item 5 below) should invoke `uvicorn app.main:app --host 0.0.0.0 --port 8000` directly, bypassing `run_server.py` entirely, since on Linux the default asyncio event loop already supports Playwright's subprocess creation (the Windows-specific loop swap in `run_server.py` exists specifically because Windows' default loop does NOT support subprocesses — Linux has no such restriction). Confirm this assumption holds (i.e. that plain `uvicorn` CLI on Linux boots Playwright's Chromium subprocess fine) as part of the Dockerfile smoke-test in item 5. Do not change `run_server.py`'s bind address — it's correct for local dev.

3. **Upload validation: `/imports/parse` has none.**
   `backend/app/api/imports.py`'s `parse_import` route (~line 64) only checks the filename ends in `.pdf` — trivially spoofable, no size cap. Its sibling `POST /cas-imports` already does this correctly via `validate_file_payload()` in `backend/app/services/import_/lifecycle_service.py:52` (checks `MAX_FILE_SIZE_BYTES` and the `%PDF-` magic-byte prefix, raising `FileTooLargeError`/`InvalidFileFormatError`). Call that same helper from `parse_import` right after reading `pdf_bytes = await file.read()`, and map its exceptions to the same `HTTPException` shape the route already uses for `ParseError` (400/422 with a `{"code", "message"}` detail body — match whatever status codes `FileTooLargeError`/`InvalidFileFormatError` already map to elsewhere in the codebase for consistency; grep `cas_imports.py` for the existing mapping and mirror it exactly rather than inventing a new one).

4. **OTP stub-mode guard: replace DB-dialect inference with an explicit `ENVIRONMENT` flag.**
   `backend/app/services/auth/otp.py:60-65` currently raises `RuntimeError` whenever `otp_delivery_mode == "stub"` and `not settings.database_url.startswith("sqlite")` — this was written to infer "is this safe" from the DB dialect (SQLite = safe/local, Postgres = unsafe/production), which breaks staging (Postgres, but not production). Add an `environment: str = "development"` field to `Settings` in `backend/app/config.py`. Change the guard to raise only when `settings.environment == "production"` (regardless of DB dialect) — staging (`environment="staging"`) with `otp_delivery_mode="stub"` against Postgres must be allowed to boot and serve requests normally. This is a deliberate, team-approved decision (staging carries no real users/data) — see the launch-blockers file's OTP section for the full reasoning; don't relitigate it, just implement the flag-based gate.

5. **Write the Dockerfile.**
   No Dockerfile exists anywhere in the repo. Base: an official Python image matching the version this backend already targets (check `backend/requirements.txt`/CI config for the pinned Python version — `.github/workflows/ci.yml` is the source of truth). Steps: `pip install -r requirements.txt` (using the pinned lockfile from item 6, not the current loose `>=` ranges), `playwright install --with-deps chromium` (installs both the Chromium binary and its Linux shared-library dependencies — without this the app crashes on startup, since `app/main.py`'s `lifespan` handler launches Chromium unconditionally on every boot), `EXPOSE 8000`, entrypoint `uvicorn app.main:app --host 0.0.0.0 --port 8000` (no `--reload`, no dev flags). Smoke-test locally: `docker build`, then `docker run` and confirm the container boots without crashing (Chromium launches successfully) and `GET /health` returns 200 from inside/against the container.

6. **Pin backend dependencies; drop the dead `passlib` dependency.**
   `backend/requirements.txt` is entirely `>=` with no lockfile — what gets built could differ from what's tested. Generate a pinned lockfile (e.g. `pip freeze` from the existing working `.venv`, or `pip-compile` if the project already has tooling for this — check for a `requirements.in` or similar first rather than assuming). Also remove `passlib[bcrypt]>=1.7.4` — it's an unused leftover from removed password auth (confirmed: no live code path uses it; grep to double-check before removing). Leave `bcrypt<4.1.0` alone unless grepping confirms it's also unused (it may still be a transitive need — verify, don't assume).

## Constraints

- Decimal, never float, in any money-adjacent code path — none of these five fixes touch money math, but don't introduce any incidentally.
- Don't touch `run_server.py`'s bind address or its Windows event-loop handling (item 2) — that script is for local dev only and its current behavior is correct there.
- Don't relitigate the stub-OTP-for-staging decision (item 4) — it's a recorded team decision, not an open question.
- Follow existing patterns in `backend/app/config.py` for new `Settings` fields (plain typed field with a sane default, no validation logic beyond what's already there).
- Run the full backend test suite (578 tests) after all five fixes — must stay green. These are additive/config-driven changes; nothing here should require touching existing tests, but if a test asserts the old hardcoded CORS list or the old OTP guard behavior directly, update it to match the new env-driven behavior rather than deleting coverage.
- No new dependencies beyond what's already in `requirements.txt`, except whatever `pip freeze`/lockfile tooling itself requires (which shouldn't ship in the runtime image).

## Approaches considered and rejected

- **Deleting the OTP stub-mode guard outright** instead of making it environment-aware — rejected per the launch-blockers doc: keeping a guard (now gated on `ENVIRONMENT=production`) preserves a real safety net against stub-mode ever running in production by accident; deleting it removes that protection entirely.
- **Making CORS wide-open (`allow_origins=["*"]`) for staging** instead of an explicit env var — rejected; the point is each environment (staging/production) sets its own real origin(s) explicitly, not a wildcard.
- **Fixing `run_server.py`'s bind address directly** instead of having the Dockerfile invoke `uvicorn` directly — rejected; `run_server.py` is purpose-built for local Windows dev (the Playwright/Proactor loop handling), and conflating "local dev launcher" with "container entrypoint" is exactly the kind of coupling that caused the current gap. Keep them separate.

## Open questions

- Confirm the Python version to base the Dockerfile on (should be derivable from CI config — flag back if ambiguous rather than guessing).
- Confirm whether `bcrypt<4.1.0` is still a genuine transitive dependency of anything live, or dead alongside `passlib` — verify via grep, don't assume either way.
- If `/imports/parse`'s existing error-response shape for `ParseError` doesn't cleanly accommodate `FileTooLargeError`/`InvalidFileFormatError`, flag back the mismatch rather than inventing a new response shape unilaterally.
