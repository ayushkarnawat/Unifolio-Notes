# AWS Go-Live Launch Blockers

Split out from `Docs/orchestration/aws-golive-readiness-report.md` §4 into its own file for focused tracking. This is the full list of items that must be resolved before real users touch this system — everything else (target architecture, AWS infrastructure design, Terraform strategy, connectivity, private networking, feasibility, decisions/responsibility, and the phased implementation plan) remains in the main report, which cross-references this file as **§4**.

These are code-level facts, independent of the infrastructure-design questions covered in the main report's §3.

## Status as of 2026-09-07

**All of this section's original code-level items are now RESOLVED** (Dockerfile, Playwright/Chromium install, CORS, `/imports/parse` upload validation, the OTP stub-mode guard, and the enum-drift migration — all shipped in commit `c7ba70a`, verified present in code and covered by a fully passing test suite: 614 backend/6 skipped, 397 frontend, `tsc -b --noEmit` clean). AWS account/region/DNS decisions are also resolved (see below). What remains is genuinely infrastructure work, not code fixes:

- Zero AWS *application* infrastructure exists yet (VPC, RDS, ECS, S3, CloudFront, ACM, Secrets Manager) — that's Phase 0 onward, the work itself, not a precondition to it.
- ACM/HTTPS certificates — not yet requested; can start as soon as Phase 5 is reached, no DNS-propagation risk left in the way since Route 53 is already authoritative.
- No RDS backup/retention configuration — set at RDS creation time, part of provisioning, not a gate before it.
- Frontend production build-time variables (`VITE_API_BASE_URL`, `VITE_GOOGLE_OAUTH_CLIENT_ID`) — still unset; needed before the production frontend *build* (Phase 4), naturally after the backend exists and its domain is known.
- No automated migration-run step against real RDS — inherent to doing this manually per the plan; the database phase's own work (Phase 2), not a precondition to reaching it.
- Google Sign-In's Client ID / Privacy Policy — explicitly marked non-blocking for staging, below.

**Bottom line:** nothing below still gates the *start* of Phase 0/1. AWS provisioning (VPC, RDS, S3, ECR, networking) can proceed now.

---

## RESOLVED (2026-09-07, fixed in commit `c7ba70a`) — OTP stub mode

**Team decision (recorded 2026-08-31): staging will keep `otp_delivery_mode="stub"` for both phone and email OTP.** Staging carries no real users and no real user data — it's internal testing only — so the account-takeover risk this finding originally centered on (anyone can request an OTP for an identifier they don't own and read it back out of the response) is accepted for staging specifically. **This acceptance is explicitly scoped to staging and does not carry forward to production** — see the staging-vs-production table in the main report's §15 and the go/no-go gate in §21.

- **Fixed:** `otp.py:60` now gates the stub-mode guard on `settings.environment == "production"` (an explicit config flag) instead of inferring safety from the database dialect (`database_url.startswith("sqlite")`). Staging can run `otp_delivery_mode="stub"` against real RDS Postgres deliberately, while a config explicitly marked `production` still hard-blocks it. Verified present in code and covered by the full passing test suite, independent of the original handoff doc's self-report.
- **Still missing, unrelated to this fix, unchanged from the original finding:** No real SMS provider exists (no Twilio/SNS/MSG91). No real email provider exists either, only a stub. Neither is required for staging; both remain required before production.
- **Residual risk, accepted for staging, to be re-confirmed before production:** anyone with access to the staging URL can take over any staging account by requesting an OTP for its phone/email and reading it back out of the response. Acceptable because staging has no real user data; **must be resolved (real provider, or a permanent product decision to drop phone/email auth) before any real user or real user data touches this system** — this is the single item in this report most likely to be forgotten once staging "just works," so it's called out explicitly here and again in the main report's §15/§19/§21.

## RESOLVED (2026-09-07, fixed in commit `c7ba70a`) — The app had no working container to deploy

- **Fixed:** `backend/Dockerfile` exists — base Python image → `pip install -r requirements.txt` (pinned) → `playwright install --with-deps chromium` → uvicorn bound to `0.0.0.0:8000` (not the local dev launcher's `127.0.0.1`, which would have been unreachable from an ALB on Fargate's `awsvpc` networking mode). Verified present in the repo.

## RESOLVED (2026-09-07, fixed alongside the Dockerfile in commit `c7ba70a`) — The app crashed on startup — Chromium was launched but never installed

- **Fixed:** the Dockerfile's `playwright install --with-deps chromium` step installs the browser binary and its OS-level shared libraries, so `main.py`'s unconditional `start_browser()` on startup no longer fails.

## RESOLVED (2026-09-07, fixed in commit `c7ba70a`) — CORS was hardcoded to localhost only

- **Fixed:** `app/main.py` now builds `allow_origins` via `_allowed_cors_origins(settings.allowed_origins)`, an env-driven, comma-separated origin list, replacing the old hardcoded localhost-only list/regex. Verified present in code.
- **Note:** Auth here is Bearer-token-in-header, not cookies (confirmed via the frontend's `localStorage`-based session storage) — so `allow_credentials=True` carries no CSRF-via-cookie risk.

## BLOCKER — The app can only safely run as exactly one instance

- **Implemented:** Seven independent in-process, module-level state stores were found: CAS-import password-retry PDF buffer, import-preview sessions, analytics PDF-export payload handoff, the dashboard holdings cache, the distributor-comparison cache, and NAV-warming/TER-backoff/category-ranking caches. Two are explicitly commented in the code as "single-process only."
- **Missing:** A shared (Redis- or DB-backed) store for any of these.
- **Why it matters:** Under 2+ ECS tasks with no sticky routing: PDF export fails on roughly half of all requests (its two-step token handoff crosses the load balancer); CAS password-retry and import-confirm intermittently fail with "session expired"; and — most seriously — **a user can see stale, pre-import portfolio values for up to 15 minutes after importing a statement**, with no error shown, if routed to a different task than the one that processed their import. This last one is a real financial-data correctness bug, not a performance nuisance.
- **Completable in the timeline?** Fixing the caches properly (Redis or DB-backed) is not realistic in this timeline. **The correct move for this launch is operational, not code: pin the ECS service to exactly one task, disable auto-scaling entirely, and use a stop-then-start deploy strategy (never a rolling deploy with 2 tasks briefly live) for every future deploy until these are fixed.**
- **Risk if skipped:** Any auto-scaling event or rolling deploy immediately reproduces the correctness bug and the ~50% PDF-export failure rate.
- **Scale note (~1,000 monthly active users target):** at internal-testing volumes, one task with no failover is a reasonable, deliberate trade-off — an occasional Fargate-managed task replacement is a minor, rare blip. At ~1,000 MAU, that same single point of failure is a real, user-visible outage risk, not a theoretical one; ECS/Fargate can and will replace an unhealthy task even at `desiredCount=1`, and there's no second task to absorb traffic while that happens. **This elevates the cache rewrite from "post-launch, whenever" to "do this before staging is trusted as the ongoing home for real, continuous user traffic"** — it does not need to block the initial staging cutover itself, but it shouldn't be left indefinitely once real users are actually on it. See the main report's §7/§8/§22 Phase 7 for where this now sits in the plan.

- **DECISION (2026-09-02):** confirmed — the Redis/DB-backed cache rewrite is explicitly
  deferred past the staging cutover, not silently dropped. Staging launches with the
  operational mitigation only: ECS service `desiredCount = 1`, autoscaling disabled, and a
  stop-then-start deploy strategy (no rolling deploys). This is a Terraform/ECS config
  decision, not application code — it becomes parameters on the ECS service resource
  (`desired_count = 1`, no `aws_appautoscaling_target`, `deployment_minimum_healthy_percent
  = 0` / `deployment_maximum_percent = 100` to force stop-then-start) written when the ECS
  Terraform module is authored (see F4's job-infrastructure work, same authoring phase).
  **Revisit trigger:** before staging is trusted as the ongoing home for continuous real
  user traffic (not a fixed date) — i.e. before scaling past internal-testing usage, or the
  first time a second task is genuinely needed for capacity or zero-downtime deploys. Until
  then this stays a single point of failure by design, accepted for the reasons above.

## RESOLVED (2026-09-07, fixed in commit `c7ba70a`) — ImportStatus / TransactionType enum drift would have broken CAS import on first real migration

- **Fixed:** migration `0010_widen_import_and_transaction_enums.py` widens the `importstatus` DB-level constraint to match the Python enum's full 14 values and rebuilds the `transactions_type_check` CHECK constraint to include `opening_balance`. Full original finding detail remains in `AWS Readiness/sqlite-postgres-migration-compliance-audit.md` (F1/F2).
- **Verified:** present in `backend/alembic/versions/`, and per session.md, tested against local Docker Postgres before this was ever a concern for real RDS (the sequencing this doc originally called for).
- **Separately, also present:** migration `0011_household_members_one_self_row.py` (a different, later fix — the "self" household-member uniqueness constraint, compliance-audit finding F3).

## RESOLVED (2026-09-07, fixed in commit `c7ba70a`) — No file-size or content validation on one of two live CAS-upload endpoints

- **Fixed:** `POST /imports/parse` (`api/imports.py`) now calls the same `validate_file_payload()` helper `POST /cas-imports` already used, closing the gap where it previously only checked the filename ended in `.pdf` with no size limit. Verified present in code.

## IN PROGRESS (2026-09-07) — Zero AWS infrastructure exists

- **Implemented:** Nothing yet on the infrastructure side itself — no RDS instance, no ECS cluster/service, no S3 bucket, no CloudFront distribution, no VPC configuration, no ACM certificates, no Secrets Manager secrets. Terraform authoring for all of this is Phase 0/1 onward (main report §22), starting now.
- **Newly resolved as of 2026-09-07, unblocking this phase:** AWS account exists (root MFA, budget alert, IAM admin user), region (`ap-south-1`), and DNS (Route 53 hosted zone for `unifolio.in`, live and propagated, existing mail records preserved) — see the main report §12/§19 and `CLAUDE.md`'s Session State. A public Route 53 hosted zone with 7 records (MX, 2 TXT, `_dmarc` TXT, 2 CNAMEs, plus auto-generated NS/SOA) already exists, so this is no longer "no Route 53 records" for the domain's core mail/ownership records — it's specifically the *application* infrastructure (VPC, RDS, ECS, S3, CloudFront, ACM, staging/app subdomain records) that's still unbuilt.
- **Why it matters:** This is the fundamental gap the whole exercise addresses — everything in the main report's §8 needs to be created from scratch.
- **Completable in the timeline?** Yes — see the main report's §9/§22 for the Terraform-first approach and phased plan.

## BLOCKER — Frontend production build-time variables are unset

- **Implemented:** `VITE_API_BASE_URL` and `VITE_GOOGLE_OAUTH_CLIENT_ID` are correctly read via `import.meta.env` at build time (env-driven, not hardcoded) — but both currently only exist as empty placeholders in `.env.example`.
- **Why it matters:** If `VITE_API_BASE_URL` is left unset, the app falls back to deriving a URL from `window.location` plus `:8000` — which will silently fail to reach the real backend once deployed behind CloudFront/ALB.
- **Completable in the timeline?** Yes — set both as real values in whatever process runs `npm run build` for the production bundle.

## PARTIALLY RESOLVED (2026-09-07) — No domain, HTTPS, or certificates configured

- **Resolved:** the Route 53 hosted zone for `unifolio.in` now exists and is authoritative (GoDaddy nameservers switched, propagation confirmed). Subdomain naming decided: `staging.unifolio.in` (staging app), `app.unifolio.in` (production app), `unifolio.in` (marketing site).
- **Still missing:** No ACM certificate requested or validated yet, no HTTPS termination point for either the frontend (CloudFront) or backend (ALB), and the backend API's own domain naming (dedicated subdomain vs. path-based routing) is still an open decision — see the main report §19.
- **Why it matters:** Both CloudFront and the ALB need a validated ACM certificate before they can serve HTTPS on a custom domain; certificate DNS validation has non-trivial latency (minutes to hours) — now that Route 53 is authoritative, this can start as soon as Phase 5 is reached, with no DNS-propagation risk left in the way.
- **Completable in the timeline?** Yes — see the main report's §22, Phase 5.

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
