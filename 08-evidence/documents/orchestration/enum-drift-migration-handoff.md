# Handoff: enum-drift-migration

**Status:** DONE — migration `0010` implemented and verified against local Docker PostgreSQL 16.15 (2026-09-02)
**Parent plan:** `AWS Readiness/aws-golive-readiness-report.md` §10 (steps 1-2), §21; `AWS Readiness/aws-golive-launch-blockers.md` (ImportStatus/TransactionType enum-drift blocker)
**Dispatch mode:** User is running this directly in their own Codex CLI/app session (not via Claude's `codex:codex-rescue` Agent dispatch) — this doc is still the source of truth both sides read; update `Status` here after Codex finishes and report back.

## Task

Write an Alembic migration that widens two Postgres ENUM types to match the Python model enums they've drifted from. This is a **must-happen-before-real-RDS** gate: the migration must be written and verified against the local Docker Postgres container (`docker compose up postgres`) *before* it is ever run against real RDS — do not run it against any real/remote database as part of this task, local Docker Postgres only.

**Confirmed drift** (verified directly against `backend/alembic/versions/0001_initial_schema.py` and `backend/app/models/enums.py`):

1. **`importstatus`** — the Postgres ENUM type created in migration `0001` (line ~158) has only 3 values: `pending`, `confirmed`, `failed`. The live `ImportStatus` Python enum (`backend/app/models/enums.py:29-43`) has 14. Missing 11: `not_started`, `requesting_cas`, `waiting_for_user`, `upload_started`, `password_required`, `validation_failed`, `processing`, `retry_pending`, `import_successful`, `import_failed`, `expired`.

2. **`transactiontype`** — the Postgres ENUM type created in migration `0001` (line ~225, built from the frozen `_TRANSACTION_TYPES` tuple at the top of that file) has 11 values. The live `TransactionType` Python enum (`backend/app/models/enums.py:70-82`) has 12. Missing 1: `opening_balance`.

Write a new Alembic revision (next in sequence after `0009_scheme_ter_nullable_value.py`) that adds exactly these 12 missing values to the two existing Postgres ENUM types. Do not recreate the types from scratch — widen them additively (`ALTER TYPE ... ADD VALUE ...`), so this stays a safe, backward-compatible schema change with zero data migration involved (no existing rows use these values yet, so there's no backfill concern — this is purely making the DB-level constraint match what the app has already been writing/expecting).

## Constraints

- **This migration file is immutable schema history once merged** — same discipline as every existing migration in `backend/alembic/versions/`: no importing live model definitions, no reading `app.models.enums` from inside the migration file (see `0001`'s own module docstring for why — replaying history from empty must reproduce the schema each revision was written against, independent of what the models look like today or in the future). Write the ENUM value literals directly in the migration, the same way `0001` does.
- **Postgres transactional-DDL gotcha:** `ALTER TYPE ... ADD VALUE` cannot be used in the same transaction it was added in, on older Postgres server versions, and Alembic wraps each migration in a transaction by default. Confirm the target Postgres version (check `docker-compose.yml` at the repo root for the pinned Postgres image tag, and match the RDS engine version referenced in `AWS Readiness/aws-golive-readiness-report.md` §8 — "PostgreSQL 16"). If the migration needs to run outside Alembic's default transaction wrapping (e.g. via `op.execute("COMMIT")` before the `ALTER TYPE` statements, or by setting the revision to non-transactional), implement whichever approach is correct for Postgres 16 and is the established pattern for this kind of change — verify by actually running it against local Docker Postgres, not by assumption.
- **SQLite compatibility:** the project's fast test suite (576 of 578 tests) runs against SQLite, where `sa.Enum` columns compile to a CHECK constraint rather than a native type — there is no `ALTER TYPE` equivalent. Check how the two Postgres-marked functional tests (mentioned in the readiness report as "2 Postgres-marked" tests) currently handle dialect-specific migration behavience elsewhere in this migration chain (grep other migrations for `op.get_bind().dialect.name` or similar dialect branching) and follow the same established pattern — this migration likely needs to be a no-op (or a `batch_alter_table` CHECK-constraint rebuild, if the project's convention requires SQLite schema parity) on SQLite, matching whatever precedent already exists in `0002`-`0009`.
- Do not touch any other enum type — only `importstatus` and `transactiontype` are confirmed drifted. Don't "fix" others speculatively.
- Do not run this migration against any database except local Docker Postgres as part of this task.

## Approaches considered and rejected

- **Dropping and recreating the ENUM types from scratch** — rejected; unnecessarily destructive for an additive change, and would require dropping/recreating every column that references them plus any dependent objects, when `ALTER TYPE ... ADD VALUE` does the same job with zero blast radius.
- **Backfilling or data-migrating existing rows** — not applicable; this is a constraint-widening only, no existing data uses the new values (nothing could have, since the app-level enum already rejected them at the DB layer before this fix).

## Open questions

- If migrations `0002`-`0009` don't already establish a dialect-branching (Postgres vs. SQLite) convention for this kind of DDL, flag that back explicitly rather than inventing a new pattern unilaterally — this is exactly the kind of cross-dialect subtlety the parent plan wants caught now, on staging, rather than discovered later.
- Confirm against `docker-compose.yml` and the readiness report that Postgres 16 is indeed the target version before assuming any specific transaction-handling workaround is necessary — if Postgres 16 already allows `ALTER TYPE ... ADD VALUE` inside a transaction with no special handling (check current Postgres docs/changelog for when this restriction was lifted), say so plainly rather than adding unnecessary complexity.

## Verification required before reporting done

- New migration applies cleanly against local Docker Postgres (`docker compose up postgres`, then `alembic upgrade head`).
- A test insert (or existing test, if one already exercises this) confirms every one of the 12 new enum values can now actually be written to the respective columns without a DB-level rejection.
- `alembic downgrade -1` from the new head works cleanly (removing added enum values isn't generally supported by Postgres without recreating the type — if a clean downgrade isn't possible, document that explicitly in the migration's downgrade function rather than silently no-op'ing or raising an unhelpful error).
- Full backend test suite (578 tests) still green, including the 2 real-Postgres-marked functional tests run against the same local Docker Postgres container.
