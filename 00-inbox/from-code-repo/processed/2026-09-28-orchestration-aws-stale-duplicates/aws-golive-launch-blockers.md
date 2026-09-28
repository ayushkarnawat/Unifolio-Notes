# AWS Go-Live Launch Blockers

Split out from `Docs/orchestration/aws-golive-readiness-report.md` §4 into its own file for focused tracking. This is the full list of items that must be resolved before real users touch this system — everything else (target architecture, AWS infrastructure design, Terraform strategy, connectivity, private networking, feasibility, decisions/responsibility, and the phased implementation plan) remains in the main report, which cross-references this file as **§4**.

These are code-level facts, independent of the infrastructure-design questions covered in the main report's §3.

## When each of these actually has to be resolved

**Not all of these gate the *start* of the staging process.** The intro line above says "must be resolved before real users touch this system" deliberately — that's before staging is opened for use, not before you're allowed to begin building it. Most items below gate a specific *later* step in the sequence (see the main report's §16/§22), not day one.

**Doesn't block starting at all — begin immediately, in parallel with the code-fix track:**
- Zero AWS infrastructure exists — that's the work itself, not a precondition to it.
- No domain/HTTPS/certificates configured — should start early (ACM validation has real latency) but doesn't block anything else from starting.
- No RDS backup/retention configuration — set at RDS creation time, part of provisioning, not a gate before it.

**Blocks a specific later step, not the start:**
- No Dockerfile / Playwright-Chromium startup crash / CORS hardcoded to localhost / no upload validation on `/imports/parse` — all need to land before the backend can actually be *deployed and used* (main report §22 Phase 3), not before infrastructure provisioning begins.
- Frontend production build-time variables unset — needed before the production frontend *build* (Phase 4), which naturally comes after the backend exists.
- OTP stub-mode guard fix — needed before OTP can work at all against Postgres, i.e. before the backend is deployed against RDS — same timing as the Dockerfile fix.
- No automated migration-run step — inherent to doing this manually per the plan; it's the database phase's own work, not a precondition to reaching it.

**The one genuine "must happen before you touch real RDS" gate**, per the team decision recorded in the main report's §21: the `ImportStatus`/`TransactionType` enum-drift migration must be written and verified against **local Docker Postgres first** — explicitly sequenced *before* it's ever run against the real RDS instance (main report §10 step 5). RDS itself can still be provisioned in parallel; it's specifically the migration-*run* step that waits on this fix.

**Not required at all for staging:**
- The OTP account-takeover risk itself — explicitly accepted, no fix needed (only the guard's crash-on-Postgres behavior needs fixing — a different thing, listed above).
- Google Sign-In's Client ID / Privacy Policy — explicitly marked non-blocking for staging, below.

**Bottom line:** AWS provisioning (VPC, RDS, S3, ECR, networking) can start today, in parallel with the code-fix track. The only hard ordering constraint is that the enum-drift fix must be verified locally before it's run against real RDS, and the backend code fixes need to land before the backend deploy step specifically — not before the whole process kicks off.

---

## BLOCKER for staging (code fix only) / BLOCKER for production (policy) — OTP stub mode

**Team decision (recorded 2026-08-31): staging will keep `otp_delivery_mode="stub"` for both phone and email OTP.** Staging carries no real users and no real user data — it's internal testing only — so the account-takeover risk this finding originally centered on (anyone can request an OTP for an identifier they don't own and read it back out of the response) is accepted for staging specifically. **This acceptance is explicitly scoped to staging and does not carry forward to production** — see the staging-vs-production table in the main report's §15 and the go/no-go gate in §21.

- **Implemented:** In `otp_delivery_mode="stub"`, the raw OTP is returned in the API response body to *any* caller (`app/services/auth/otp.py:101`), for both phone and email OTP requests.
- **The part that's still a hard blocker even for staging:** a guard exists (`otp.py:60-65`) that raises a hard `RuntimeError` whenever stub mode is used against a **non-SQLite** database. Staging runs on RDS PostgreSQL (per ADR-003 — that's the whole point of this migration), so as written today, **every OTP request on staging will hard-fail with a 500**, not just be insecure — nobody, including internal testers, can sign up or log in via phone/email OTP on staging until this guard is changed. This is a real, newly-relevant blocker, distinct from the account-takeover risk.
- **Why the guard exists this way:** it was written to infer "is this a safe environment to use stub mode in" from *which database dialect is active*, on the assumption that SQLite = local/dev and Postgres = production. That assumption is exactly what staging breaks — staging is Postgres, but is not production.
- **Exactly what to do:** replace the dialect-based inference with an explicit environment flag (e.g. `ENVIRONMENT=staging|production`, read from config) and gate the guard on that instead of on `database_url.startswith("sqlite")`. This lets staging run stub-mode OTP against real Postgres deliberately, while keeping a hard block against stub-mode OTP ever running in a config explicitly marked `production`. This is a small, contained code change — recommend making it rather than deleting the guard outright, so the production safety net survives.
- **Missing (still true, unrelated to the staging decision):** No real SMS provider exists at all (no Twilio/SNS/MSG91 integration anywhere). No real email provider exists either — only a stub; Postmark integration is explicitly a separate, later task per its own code comment. Neither is required for staging under this decision; both remain required before production.
- **Completable in the timeline?** Yes — the environment-flag guard fix is a small, well-scoped change, see the main report's §22 Phase 0/3.
- **Residual risk, accepted for staging, to be re-confirmed before production:** anyone with access to the staging URL can take over any staging account by requesting an OTP for its phone/email and reading it back out of the response. Acceptable because staging has no real user data; **must be resolved (real provider, or a permanent product decision to drop phone/email auth) before any real user or real user data touches this system** — this is the single item in this report most likely to be forgotten once staging "just works," so it's called out explicitly here and again in the main report's §15/§19/§21.

## BLOCKER — The app has no working container to deploy

- **Implemented:** A working local dev launcher (`backend/scripts/run_server.py`) that binds `uvicorn` to `127.0.0.1:8000` with a single worker, no process manager.
- **Missing:** **No Dockerfile exists anywhere in the repository** — confirmed by an exhaustive search. The server binds to loopback (`127.0.0.1`), which is unreachable from an ALB on Fargate's `awsvpc` networking mode — it must bind `0.0.0.0`.
- **Why it matters:** ECS Express Mode deploys "from source or container image" — even the source-deploy path would use a generic Python buildpack that has no idea Playwright needs a browser binary installed (see next finding). A hand-written Dockerfile is the only reliable way to get this app running correctly on Fargate.
- **Completable in the timeline?** Yes — this is a few hours of focused work, see the main report's §22.
- **Exactly what to do:** Write a Dockerfile: base Python image → `pip install -r requirements.txt` (pinned) → `playwright install --with-deps chromium` → expose 8000 → entrypoint running uvicorn bound to `0.0.0.0:8000`, no `--reload`.

## BLOCKER — The app crashes on startup — Chromium is launched but never installed

- **Implemented:** `backend/app/main.py:21-28`'s `lifespan` handler calls `start_browser()` unconditionally on *every* app startup (not lazily, not only when PDF export is used) — this launches a Playwright-managed headless Chromium process.
- **Missing:** `pip install playwright` does not download the Chromium binary — that needs a separate `playwright install chromium` step, plus (on Linux) OS-level shared libraries normally installed via `playwright install --with-deps`. Nothing in this repo runs either step.
- **Why it matters:** A freshly built container will boot, hit the `lifespan` startup hook, and fail to launch the browser — the entire API becomes unavailable, not just the PDF-export feature. This would be the first thing discovered on the very first deploy.
- **Completable in the timeline?** Yes, trivially — it's one Dockerfile line, bundled with the previous finding's fix.
- **Risk if skipped:** None if fixed together with the Dockerfile; catastrophic (total outage on first deploy) if missed.

## BLOCKER — CORS is hardcoded to localhost only

- **Implemented:** `app/main.py:32-42` — `allow_origins` is a hardcoded list of localhost ports plus a localhost-only regex. No wildcard, so it fails *closed* today (safe, but non-functional against a real domain).
- **Missing:** No env-driven origin list; nothing reads `frontend_base_url` or any other setting for CORS.
- **Why it matters:** The moment the frontend moves to its real domain (CloudFront or custom), every single API call — including login — will be blocked by the browser's CORS check. This will look like a total outage.
- **Completable in the timeline?** Yes — trivial code change: read an `ALLOWED_ORIGINS` env var (comma-separated) and pass it to `CORSMiddleware`.
- **Note:** Auth here is Bearer-token-in-header, not cookies (confirmed via the frontend's `localStorage`-based session storage) — so `allow_credentials=True` carries no CSRF-via-cookie risk; the fix is purely about adding the real origin, not about credential handling.

## BLOCKER — The app can only safely run as exactly one instance

- **Implemented:** Seven independent in-process, module-level state stores were found: CAS-import password-retry PDF buffer, import-preview sessions, analytics PDF-export payload handoff, the dashboard holdings cache, the distributor-comparison cache, and NAV-warming/TER-backoff/category-ranking caches. Two are explicitly commented in the code as "single-process only."
- **Missing:** A shared (Redis- or DB-backed) store for any of these.
- **Why it matters:** Under 2+ ECS tasks with no sticky routing: PDF export fails on roughly half of all requests (its two-step token handoff crosses the load balancer); CAS password-retry and import-confirm intermittently fail with "session expired"; and — most seriously — **a user can see stale, pre-import portfolio values for up to 15 minutes after importing a statement**, with no error shown, if routed to a different task than the one that processed their import. This last one is a real financial-data correctness bug, not a performance nuisance.
- **Completable in the timeline?** Fixing the caches properly (Redis or DB-backed) is not realistic in this timeline. **The correct move for this launch is operational, not code: pin the ECS service to exactly one task, disable auto-scaling entirely, and use a stop-then-start deploy strategy (never a rolling deploy with 2 tasks briefly live) for every future deploy until these are fixed.**
- **Risk if skipped:** Any auto-scaling event or rolling deploy immediately reproduces the correctness bug and the ~50% PDF-export failure rate.
- **Scale note (~1,000 monthly active users target):** at internal-testing volumes, one task with no failover is a reasonable, deliberate trade-off — an occasional Fargate-managed task replacement is a minor, rare blip. At ~1,000 MAU, that same single point of failure is a real, user-visible outage risk, not a theoretical one; ECS/Fargate can and will replace an unhealthy task even at `desiredCount=1`, and there's no second task to absorb traffic while that happens. **This elevates the cache rewrite from "post-launch, whenever" to "do this before staging is trusted as the ongoing home for real, continuous user traffic"** — it does not need to block the initial staging cutover itself, but it shouldn't be left indefinitely once real users are actually on it. See the main report's §7/§8/§22 Phase 7 for where this now sits in the plan.

## BLOCKER — ImportStatus / TransactionType enum drift will break CAS import on first real migration

- **Implemented:** App code assigns 14 `ImportStatus` values; the database-level constraint was only ever created with 3 (migration `0001`). Similarly, `TransactionType.OPENING_BALANCE` was added to the Postgres enum but never to the SQLite CHECK constraint.
- **Missing:** A migration widening the DB-level constraint to match the Python enum.
- **Why it matters:** Already documented in full, with exact file:line citations and a remediation plan, in `Docs/orchestration/sqlite-postgres-migration-compliance-audit.md` (findings F1/F2). This would very likely break the CAS import flow immediately after the first real `alembic upgrade head` run against fresh RDS.
- **Completable in the timeline?** Yes — this is a single, well-scoped, additive migration. See the main report's §10 for the exact sequencing.
- **Note:** Test it against a real Postgres instance (the local Docker container is sufficient) *before* touching the real RDS — this closes the "never actually verified end-to-end" gap the compliance audit flagged as unverified.

## BLOCKER — No file-size or content validation on one of two live CAS-upload endpoints

- **Implemented:** `POST /cas-imports` correctly enforces a 25MB cap and a PDF magic-byte check (`lifecycle_service.py:52-56`). Its sibling, `POST /imports/parse` (`api/imports.py:64-79`), checks only the filename ends in `.pdf` — trivially spoofable — with no size limit at all.
- **Why it matters:** An unbounded upload buffered fully into memory on a small Fargate task is a real resource-exhaustion risk, and this endpoint is live and reachable from the desktop web import flow today, not dead code.
- **Completable in the timeline?** Yes — apply the same `validate_file_payload()` helper already used by `/cas-imports` to this endpoint. Minutes of work.

## BLOCKER — Zero AWS infrastructure exists

- **Implemented:** Nothing — no RDS instance, no ECS cluster/service, no S3 bucket, no CloudFront distribution, no VPC configuration, no ACM certificates, no Route 53 records, no Secrets Manager secrets. Confirmed by an exhaustive search for Terraform/CDK/CloudFormation/Pulumi files and any AWS CLI provisioning script — none exist.
- **Why it matters:** This is the fundamental gap the whole exercise addresses — everything in the main report's §8 needs to be created from scratch.
- **Completable in the timeline?** Yes — with the Friday deadline's extra 2 days, the main report's §9 now recommends **Terraform-first for the whole stack** (with AI-assisted module authoring and a Tuesday checkpoint), manual-then-import only as the fallback if that checkpoint isn't on track. See §15 for the honest feasibility read.

## BLOCKER — Frontend production build-time variables are unset

- **Implemented:** `VITE_API_BASE_URL` and `VITE_GOOGLE_OAUTH_CLIENT_ID` are correctly read via `import.meta.env` at build time (env-driven, not hardcoded) — but both currently only exist as empty placeholders in `.env.example`.
- **Why it matters:** If `VITE_API_BASE_URL` is left unset, the app falls back to deriving a URL from `window.location` plus `:8000` — which will silently fail to reach the real backend once deployed behind CloudFront/ALB.
- **Completable in the timeline?** Yes — set both as real values in whatever process runs `npm run build` for the production bundle.

## BLOCKER — No domain, HTTPS, or certificates configured

- **Missing:** No ACM certificate, no Route 53 hosted zone confirmed, no HTTPS termination point for either the frontend (CloudFront) or backend (ALB).
- **Why it matters:** Both CloudFront and the ALB need a validated ACM certificate before they can serve HTTPS on a custom domain; certificate DNS validation has non-trivial latency (minutes to hours) — this needs to start early, in parallel with everything else.
- **Completable in the timeline?** Yes, if started immediately — see the main report's §22, Phase 5.

## IMPORTANT (not a staging blocker) — Google Sign-In has no real Client ID, and no Privacy Policy page exists

- **Implemented:** Real, working server-side Google ID-token verification (`app/services/auth/google_oauth.py`) using Google's public keys — this is genuine, not scaffolding.
- **Missing:** A real OAuth Client ID (currently empty in both frontend and backend config).
- **Staging-specific relief:** since staging is internal testers only (not the general public) and stub OTP is now the primary sign-in path anyway (see the finding above), Google's OAuth consent screen can stay in **"Testing" mode** for staging — up to 100 explicitly-added test-user Google accounts can sign in without the app needing a published Privacy Policy page at all. Only needed if Google Sign-In is offered on staging beyond that small, explicitly-added tester list.
- **Still required before production:** if Google Sign-In is to be offered to real users, the consent screen must leave "Testing" mode, which requires a published Privacy Policy page — none exists anywhere in the frontend today. Track this as a production-readiness item, not a staging one.
- **Completable in the timeline?** Registering a Client ID (if Google Sign-In is wanted on staging at all) is a same-day task; the Privacy Policy page can wait until it's actually needed, per the staging-specific relief above.

## BLOCKER — No automated (or ever-executed) migration run against a real target

- **Implemented:** CI runs `alembic upgrade head` against an ephemeral Postgres container as a test fixture only.
- **Missing:** Any script, ECS one-off task, or documented step that runs migrations against a real deployment target. The Migration Plan's own runbook (`Docs/PRDs/Migration-Plan-SQLite-to-Postgres.md`) is written as a manual checklist, not automation.
- **Why it matters:** Someone has to manually run and verify this against the real RDS instance before the app can serve any real request — and per the finding above, it must include the ImportStatus/TransactionType fix first.
- **Completable in the timeline?** Yes — this is a manual, one-time, carefully-sequenced step. See the main report's §10.

## BLOCKER — No RDS backup/retention configuration has been made (because no RDS exists yet)

- **Why it matters:** ADR-003 is explicit: "RDS gives managed backups, point-in-time recovery, and durability guarantees that matter the moment real user financial data is being stored." This must be a deliberate configuration choice at provisioning time (automated backup retention window, not the bare default), not an afterthought discovered after the first user's data is at risk.
- **Completable in the timeline?** Yes — a checkbox/parameter at RDS creation time. See the main report's §8.

---

*Read-only assessment. Part of the AWS go-live handoff for this repository — see `Docs/orchestration/aws-golive-readiness-report.md` for target architecture, AWS infrastructure design, Terraform strategy, connectivity, private networking, feasibility, decisions/responsibility, and the phased implementation plan.*
