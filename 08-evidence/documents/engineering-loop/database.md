# Database Changelog

> Running changelog of database/schema changes only — tables/columns added or changed, migrations, index/constraint changes. Distinct from `Docs/PRDs/Database-Schema-Unifolio.md`, which stays the current schema as it stands today, not a change history. This file records changes that have actually been migrated, not designed/planned changes still awaiting implementation — see `backend.md`/`decisions.md` for in-progress schema work not yet landed. Backfilled 2026-08-14; append new entries at the bottom, dated, never rewrite past ones.

## 2026-08-04 — Migration 0001: initial schema

`0001_initial_schema` — every table from the Database Schema doc's v1.1: `users`, `household_members`, `imports`, `schemes`, `folios`, `transactions` (partitioned by `RANGE(date)`, yearly), `nav_history` (partitioned, yearly), `scheme_ter`, `scheme_aaum`, `benchmark_index_history`, `arn_directory`, `portfolio_snapshots`, `fund_scores`, `otp_requests`, `sessions`. `users.phone_number`: `UNIQUE NOT NULL` from day one. All money/units/NAV columns `NUMERIC`, never `FLOAT`. No PAN column anywhere; no raw-CAS-PDF table or column anywhere.

## 2026-08-06 — Migration 0002: transaction dedupe constraint widened

`0002_transaction_dedupe_includes_type` — `transactions`' dedupe unique constraint widened from `(folio_id, date, amount, units)` to `(folio_id, date, amount, units, type)`. No data transformation; existing rows untouched, only the duplicate-detection rule going forward changes. Dialect-aware migration (SQLite batch-mode table recreation vs. Postgres `DROP`/`ADD CONSTRAINT`).

## 2026-08-1X — Migration 0003: CAS import lifecycle and coverage gaps

`0003_cas_import_lifecycle_and_coverage_gaps` — `imports` gains `error_code`, `error_message`, `source_tab`, `statement_from_date`, `statement_to_date`, `expires_at` (all nullable). `folios` gains `has_coverage_gap` (`BOOLEAN NOT NULL`, default false) and `coverage_gap_details` (JSON — Postgres `JSONB`, SQLite generic `JSON`; note this predates the Migration Plan guardrail doc's explicit "no dialect-specific JSON literal" guidance being checked against new work, see `decisions.md`'s 2026-08-14 entry on the multi-method-auth schema being the first design explicitly confirmed compliant). New `TransactionType` enum value: `opening_balance`.

## 2026-08-14 — Migration 0004 landed: multi-method auth schema

Built, tested, and committed as Task 1 of `Docs/superpowers/plans/2026-08-14-multi-method-auth-backend-plan.md` (commit `39db87d`, migration `0004_multi_method_auth_identities`), with an upgrade/downgrade round-trip test. Actual changes:
- New table `auth_identities` — one row per linked auth method (`phone_otp`/`email_otp`/`google`) per user; `UNIQUE(provider, provider_subject)`.
- New table `pending_identity_verifications` — holds a verified-but-not-yet-attached Google/email identity during the mandatory phone-gate or account-linking step-up flow.
- `otp_requests`: `phone_number` becomes nullable, new nullable `email` column, new check constraint enforcing exactly one of the two is set.
- `sessions`: new `auth_method` column (`NOT NULL`, backfilled to `phone_otp` for pre-existing rows).
- `users.phone_number` is explicitly **unchanged** — stays `UNIQUE NOT NULL` as it has been since migration 0001 (an earlier design draft would have loosened this; reversed before implementation — see `decisions.md`).

Landing this migration also removed every OTP/session-related route's old direct-phone-lookup code path (Task 9) — every login now resolves through `auth_identities`. That created a real gap the implementation plan itself missed: **no migration was ever written to backfill existing `users` rows into `auth_identities`.** Flagged as Critical Finding 2 of the final whole-branch review (see `backend.md` and `log.md`'s 2026-08-14 entries) and closed in the same session: migration `0005_backfill_phone_otp_identities.py` now does the one-time backfill (Core-literals-only, re-runnable, documented no-op downgrade), landed as part of commit `2784b61`, independently re-verified clean.

**Local-dev gotcha confirmed 2026-08-15:** a pre-existing `unifolio_dev.db` (SQLite) that predates this feature stays pinned at whatever revision it was last migrated to — starting the backend against it does NOT auto-apply new migrations. This surfaced as a real `/auth/otp/request` failure for the email channel (`otp_requests.email` didn't exist on disk yet, `alembic current` showed `0003` against a `0005` head). Fixed by running `alembic upgrade head`, confirmed directly against the SQLite schema (not just alembic's own bookkeeping) — `otp_requests` gained `email`/lost its `phone_number NOT NULL`, both new tables and `sessions.auth_method` all present. Then confirmed end-to-end against the running server: a genuine pre-2026-08-14 user (created before this feature existed) logged in successfully via phone — direct proof the 0005 backfill correctly protects real, not just synthetic, data — and a fresh email signup correctly triggered `phone_required`. **Why this matters:** anyone picking up `authsetup` fresh with an existing dev DB needs `alembic upgrade head` before testing this feature, not just `pip install`+ run.

## 2026-08-17 — Migration 0006: email+password auth (Superseded)

`0006_email_password_auth` — added `EMAIL_PASSWORD` to enum, `password_hash` columns, and password reset/email confirmation tables. *(Superseded by migrations 0007/0008 below).*

## 2026-08-17/18 — Migration 0007 & 0008: Email-OTP Signup and Full Password Removal

- **`0007_email_otp_signup`**: Widened `otp_requests` check constraint to support both email and phone channels; generalized `otp_requests` for inline email OTP verification.
- **`0008_remove_password_auth`**: Fully dropped `password_reset_tokens` and `email_confirmation_tokens` tables. Dropped `password_hash` and `email_confirmed_at` from `auth_identities` and `pending_identity_verifications`.
- Enum state: `EMAIL_OTP` is active; `EMAIL_PASSWORD` remains defined in the DB enum as an unused benched value (since Postgres cannot cheaply drop enum values).
- Schema is 100% clean, verified with `alembic upgrade head` and 449 passing tests.

