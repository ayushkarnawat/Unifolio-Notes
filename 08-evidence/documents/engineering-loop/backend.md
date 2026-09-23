# Backend Changelog

> Running changelog of backend changes only — endpoints added/changed, services touched, migrations run, dependencies added. Distinct from `Docs/PRDs/TDD-Unifolio.md`, which stays the current-state architecture reference, not a change history. Backfilled 2026-08-14 from `session.md` and `Docs/superpowers/plans/`/`specs/`; append new entries at the bottom, dated, never rewrite past ones.

## 2026-08-04 — Phase 0: foundation

Project scaffold, `Decimal`-safe `calc.py`, SQLAlchemy models, `Base`/`SessionLocal` setup, Alembic wired from day one.

## 2026-08-04 — Phase 1: CAS import backend

`casparser` wrapper, `mfapi.in` enrichment client, two-phase parse/confirm API routes (`backend/app/services/import_/`, `backend/app/api/imports.py`). Migration `0001_initial_schema` — full initial schema (all reference + user-data tables per Database Schema doc, including `otp_requests`/`sessions` as foundational auth tables even though Phase 2's auth logic hadn't landed yet).

## 2026-08-05 — Phase 2: Auth + Onboarding backend

`backend/app/services/auth/` (`otp.py`, `session.py`, `schemas.py`), `backend/app/api/auth.py`: `POST /auth/otp/request`, `POST /auth/otp/verify`, `POST /auth/session/refresh`, `GET`/`PATCH /auth/me`. `POST`/`GET /household-members` (owned by Dashboard service per the TDD's API-ownership table, not Auth). Session tokens: opaque bearer, SHA-256-hashed, 30-day TTL refreshed on activity. OTP: 6-digit, SHA-256-hashed, 5-min expiry, dev-stub delivery mode (`otp_delivery_mode` setting) gating whether the raw code is echoed in the API response.

## 2026-08-06 — Phase 3: Main Dashboard backend

Holdings/allocation compute services and routes (FIFO engine, Decimal throughout).

## 2026-08-06 — Migration 0002: transaction dedupe key widened

`0002_transaction_dedupe_includes_type` — dedupe unique constraint widened to `(folio_id, date, amount, units, type)`, fixing a real duplicate-detection bug (see `decisions.md`).

## 2026-08-07 — Distributor comparison (PRD-03 FR-11)

`GET /household-members/{id}/schemes/{scheme_id}/distributor-comparison` and ARN-directory resolution logic.

## 2026-08-10 to 2026-08-13 — Phase 4: Analytics backend, all 5 parts

- **Part 1 (allocation, FR-1/FR-2):** `analytics/allocation.py`, `analytics/schemas.py`; `GET /analytics/household-members/{id}/allocation`, `GET /analytics/household/aggregate/allocation`.
- **Part 2 (TER/AAUM, FR-10/FR-11):** `analytics/amfi_ter_client.py`, `analytics/amfi_aaum_client.py`, `analytics/ter.py`; `GET .../ter`, `.../ter/direct-regular` (+ aggregate variants).
- **Part 3 (NSE benchmark, FR-8/FR-9):** `analytics/nse_indices_client.py`, `analytics/xirr.py` (pure-Decimal Newton-Raphson, no numpy), `analytics/benchmark.py`; `GET .../benchmark`, `.../benchmark/funds` (+ aggregate variants).
- **Part 4 (category ranking, FR-3/FR-4):** `analytics/scheme_universe.py` (AMFI bulk `NAVAll.txt` ingestion), `analytics/category_ranking.py`; `GET .../category-ranking` (+ aggregate variant).
- **Part 5 (Scorer, FR-5/FR-6/FR-7):** `analytics/risk_metrics.py`, `analytics/scorer.py` (composite fund score + portfolio roll-up); `GET /funds/{scheme_id}/score`, `GET /household-members/{id}/score`, `GET /household/aggregate/score`.

Backend suite grew 156 → 357 passing (2 skipped) across all five parts, verified after each.

## 2026-08-1X — CAS Import lifecycle redesign (intern-authored)

`backend/app/services/import_/state_machine.py` — 11-state import lifecycle enforcing legal transitions; a buffer cache, lifecycle service, and member-attribution logic; coverage-gap detection and opening-balance resolution; a CAMS-portal mailback URL generator and pending-request lifecycle. New `OPENING_BALANCE` transaction type. Migration `0003_cas_import_lifecycle_and_coverage_gaps`. **Not yet independently reviewed by Claude Code** against CLAUDE.md's non-negotiables (Decimal-never-float, no PAN persistence) — passes the test suite, which is a distinct claim from "reviewed."

## 2026-08-13/14 — Dashboard load-time performance fixes

`backend/app/api/imports.py`'s `confirm_import_route`: background `BackgroundTasks` NAV prefetch on import confirm (Fix A). `backend/app/services/dashboard/nav.py`: new batch function `get_navs_on_or_before`, parallelizing only the pure-network fetch leg via `asyncio.gather` while keeping all DB reads/writes sequential on one `Session` (Fix B); dialect-native `ON CONFLICT DO NOTHING` upsert closing a concurrent-insert race. `backend/app/services/dashboard/holdings.py`: process-local per-day cache for `compute_holdings`, keyed by `(household_member_ids, date.today())`, with a generation-counter + single process-local lock spanning capture/publish/invalidate, and a bounded 15-minute self-healing TTL (Fix D — took 4 review rounds to close correctly, see `decisions.md`/`log.md`). Fix C (the real fix — ADR-006's scheduled recurring NAV-refresh job) remains deferred to deployment phase. Backend suite grew 156 → 326 passing, 2 skipped, across all four rounds.

## 2026-08-14 — Multi-method auth (planned, not yet implemented)

Design finalized (`Docs/superpowers/specs/2026-08-14-multi-method-auth-design.md`) and a full TDD implementation plan written (`Docs/superpowers/plans/2026-08-14-multi-method-auth-backend-plan.md`), covering: new `auth_identities` and `pending_identity_verifications` tables; widened `otp_requests` (nullable `phone_number`/`email`, exactly-one check constraint); new `Session.auth_method` column; a generalized `otp.py` (phone + email channels, one shared code path); a new `EmailProvider` protocol with only a `StubEmailProvider` implementation (Postmark deferred, see `decisions.md`); Google ID-token verification (`google-auth` — new dependency, no client secret needed); an identity/collision-resolution service implementing the account-linking policy and Google > Email > Phone precedence; a mandatory phone-gate signup-completion flow; a new `POST /auth/oauth/google` route; widened `/auth/otp/request`/`/auth/otp/verify` routes; and per-identifier OTP-request throttling. **Not yet executed as of this entry** — this is a plan, not a shipped change; update this entry (or add a new one) once the plan is actually implemented and merged.

## 2026-08-14 — Multi-method auth backend plan: finalized (still unexecuted); five design refinements folded in

The backend implementation plan referenced in the entry above is now complete and self-reviewed (11 tasks) — still not executed as of this entry. Refinements folded into the design before the plan was written: Postmark confirmed as the email provider (SES-vs-Postmark closed, wiring still deferred but now a firm prerequisite before this feature reaches Postgres/production, not open-ended); `pending_identity_verifications` uses one shared ~10-minute TTL for both its triggers; `Session.auth_method` is now a firm part of the plan (Task 4), not an optional follow-up. See `decisions.md` for each "why." The companion frontend implementation plan (`Docs/superpowers/plans/2026-08-14-multi-method-auth-frontend-plan.md`) is also complete — out of this file's backend-only scope, see `log.md`.

## 2026-08-14 — Multi-method auth backend: all 11 tasks implemented via subagent-driven-development

All 11 tasks from the backend plan built via TDD, fresh-subagent-per-task, task-scoped review, on branch `authsetup`: `39db87d` (schema/migration 0004), `0486e64` (`EmailProvider` abstraction, stub-only), `c79757d` (OTP service generalized to email+phone), `c93d0d4` (`Session.auth_method`), `4492202`→`20398d0` (identity resolution + precedence, one fix round for a non-atomic commit bug — see below), `a79ea25`→`cefa32e` (Google ID-token verification, one CRLF fix), `851dab9` (three-way verify-outcome schemas), `332fe6c` (OTP request/verify routes rewrite), `76ee569` (Google OAuth route + dedup), `35781ee` (per-identifier OTP throttling). A small out-of-plan fix (`6165403`, explicitly approved by the user rather than decided unilaterally) updated 3 CAS-import test fixtures still calling the old 2-arg `create_session` signature.

Two review findings worth recording as real bugs, not process noise:
- **Task 6 (identity resolution) — Critical, fixed same-task:** `complete_phone_gate_signup`/`attach_pending_identity` were not atomic — each call inside them independently committed, so a failure partway through could leave a user row without its identity row. Fixed by adding an optional `commit: bool = True` param to `record_identity`/`refresh_denormalized_email` so callers can defer the commit to one outer transaction; verified with a regression test forcing a real unique-constraint failure mid-flow and confirming full rollback.
- **Task 8 (schemas) — a false positive worth remembering:** a reviewer claimed `MeResponse` had been dropped entirely, based on a `git diff -U10` hunk that only *looked* like it omitted the class (limited context window, not actual absence). Verified via direct `git show`/`wc -l` that the class was present all along. Lesson carried into every later reviewer dispatch: never conclude "class X is absent" from a context-limited diff alone — confirm with `git show` first.

**Final whole-branch review** (dispatched on the most capable available model per the skill's model-selection rule) found 2 Critical + 4 Important findings that no single task's review could have caught, since they only emerge across tasks:
- **Critical 1 — unverified-email auto-link laundering:** a Google account with an *unverified* email claim could get that email written into `AuthIdentity.email` during phone-gate completion. Since `resolve_email_collision` treats any matching `AuthIdentity.email` as proof of verified ownership, a later legitimate owner's real email-OTP signup would silently auto-link into the attacker's account instead of creating its own. Fix: gate both write sites in `complete_phone_gate_signup` (and `attach_pending_identity`, extended the same way) on `pending.email_verified`.
- **Critical 2 — no backfill migration for pre-existing users:** the design spec explicitly called for backfilling existing users into `auth_identities` as a one-time migration, flagged there as "planning-phase work, not built here" — but this never actually became a plan task. Combined with Task 9 removing the old direct-phone-lookup path, any pre-existing user would 500 on next login against real data. This is a genuine gap in the plan itself, not an implementer slip — see `database.md`'s 2026-08-14 migration-0004 entry. Fix: new migration `0005_backfill_phone_otp_identities.py`.
- 4 Important findings bundled into the same fix wave: an overly-strict guard in `attach_pending_identity` created a dead end for an existing user's *first* Google sign-in; total absence of email normalization (case/whitespace) defeated the collision-matching system entirely; `create_otp_request` committed the OTP row before attempting the email send, so a provider failure left an orphaned row that self-throttled the user's retry; and 4 of the design spec's own §7 test scenarios had zero actual coverage, contradicting the plan's Final Verification claim.

## 2026-08-14 — Multi-method auth backend: fix wave complete, final review CLEAN, plan done

All 6 findings from the final whole-branch review (2 Critical, 4 Important) fixed in commit `2784b61` (12 files, +1118/-24, 33 net new tests) and independently re-verified twice — once directly by the controller (full suite re-run, direct diff read of every touched file, CRLF check), once by an independent scoped re-review dispatched per the skill's no-second-fix-wave rule. Both passes confirmed all 6 findings genuinely closed, not just claimed closed:
- Critical 1 (unverified-email laundering): every `users.email`/`AuthIdentity.email` write site enumerated and confirmed guarded on `email_verified`.
- Critical 2 (no backfill): new migration `0005_backfill_phone_otp_identities.py` (Core-literals-only, re-runnable, documented no-op downgrade) plus a runtime `find_or_backfill_phone_identity` safety net wired into both phone-channel route lookups.
- The 4 Important findings (dead-end guard, no email normalization, commit-before-send, missing §7 test coverage) all fixed with real, non-vacuous regression tests.
- One additional latent bug found and fixed beyond the 6 findings' literal text: `attach_pending_identity` never flushed before `refresh_denormalized_email` queried for the identity it had just added (both prod and test sessions are `autoflush=False`), so linking silently never updated `users.email` — fixed with an explicit `db.flush()`, which also corrected a second bug where linking a higher-precedence Google identity onto an existing lower-precedence email identity left `users.email` stuck on the old value.

The re-review surfaced 4 new Minor findings in the fix-wave diff itself (a duplicate-pending-token edge case now 500s instead of a clean 401; a narrow check-then-insert race in the new backfill safety net; a real transient email-provider failure would still 500 instead of 503, currently unreachable since Postmark isn't wired up; one cosmetic dead assertion in a new test). All 4 explicitly assessed as not load-bearing and parked with rulings in the SDD ledger rather than triggering a second fix wave, per the skill's process. **Backend suite: 441 passed, 2 skipped, 0 failed, 0 errors.** Full plan (11 tasks + 1 out-of-plan fixture fix + the final review's fix wave) is complete — no further backend work outstanding on this plan. The companion frontend implementation plan remains unexecuted (see `log.md`).

**Clarification confirmed against the frontend plan's assumptions (2026-08-14):** the 503/`NoEmailProviderConfiguredError` path referenced just above is correctly described as "currently unreachable" — verified this is true under the app's actual default config, not just true in principle. `otp_delivery_mode` defaults to `"stub"` and is one setting shared by both channels; in stub mode `create_otp_request` never calls into `EmailProvider` at all (same short-circuit phone's channel already takes), so email's stub behavior is byte-for-byte identical to phone's — OTP generated, stored, and returned in the response's `otp` field, a 200 every time. The 503 only fires if `OTP_DELIVERY_MODE` is deliberately set to a real value (exercised only via explicit test monkeypatching). See `decisions.md`'s matching 2026-08-14 entry for the full trace — the frontend plan needs no special-case error handling for this case as a result.

## 2026-08-17 — `requests` declared as an explicit backend dependency

`backend/app/services/auth/google_oauth.py` imports `google.auth.transport.requests`, which needs the `requests` package — it had only ever been present as `google-auth`'s transitive dependency, never pinned directly in `requirements.txt`. Added `requests>=2.31.0` explicitly (commit `5bb63c3`), verified with a genuinely fresh virtualenv (not the existing dev environment): clean `pip install -r requirements.txt`, then a full `uvicorn` boot with zero `ImportError`s. **Why:** relying on a transitive dependency for something a module directly imports is fragile — a future `google-auth` version could drop or restructure that dependency without warning, silently breaking Google sign-in in a way `pip install` wouldn't catch until runtime.

## 2026-08-17 — Multi-method auth frontend plan: complete, final review clean

All 10 tasks + 1 out-of-plan `App.test.tsx` fix + the final whole-branch review's 1 Critical/6 Important findings, fixed and independently re-verified twice. Full detail in `log.md`'s 2026-08-15–17 entry and `decisions.md`. **Both multi-method-auth plans (backend and frontend) are now fully complete** — the auth remodel started earlier this session is done end to end: Google Sign-In, email+OTP, and phone+OTP all work as equal entry points, backed by the mandatory phone-gate invariant and step-up-only account linking, verified end-to-end against a real running backend with real (pre-existing, non-synthetic) user data.

## 2026-08-17 — Email+password auth backend complete (Superseded)

Replaces email+OTP with email+password (Google and phone+OTP unchanged).
New: `password.py` (bcrypt hashing), `password_reset.py` and
`email_confirmation.py`. Migration `0006_email_password_auth`.
*(Superseded by 2026-08-17/18 reversal below).*

## 2026-08-17/18 — Pure Email-OTP Auth restoration & Password removal

Reversed password auth completely across all backend routes and schema.
Migration `0007_email_otp_signup` and `0008_remove_password_auth`:
- Reactivated `EMAIL_OTP` as the active email auth provider in `AuthIdentity`.
- Removed `password.py`, `password_reset.py`, `email_confirmation.py`, and dropped `password_reset_tokens` / `email_confirmation_tokens` tables.
- Generalized `otp.py` across email and phone channels with SHA-256 hashed 6-digit codes and per-identifier 60s cooldowns.
- Endpoints: `POST /auth/signup/email` (initiates email OTP send), `POST /auth/email-otp/request`, `POST /auth/email-otp/verify` (verifies code, attaches identity or transitions to mandatory phone gate).
- Step-up account linking verified with `peek_pending_matched_user_id` security check against pre-emptive identity takeover.
- Backend suite: 449 passed, 2 skipped, 0 failed.

## 2026-08-19 — CORS Multi-Port Dev Support & Regex Configuration

Updated `backend/app/main.py` `CORSMiddleware`:
- Added `allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"` alongside the standard origin list (`http://localhost:5173`, `http://localhost:5174`, `http://localhost:5175`, `http://localhost:3000`).
- Prevents CORS preflight `OPTIONS` failure when the frontend dev server auto-allocates port 5174 or 5175.
- Automated tests added to `backend/tests/test_health.py` covering multi-port preflight headers.
