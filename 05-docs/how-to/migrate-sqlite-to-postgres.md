# How to: Migrate from SQLite to AWS RDS PostgreSQL

Implements [ADR-003](../../03-decisions/ADR-003-primary-database-rds-postgresql.md). The
trigger is **not a calendar date** — it is the readiness checklist below being true.

## The guiding principle

Portable by construction. The prototype was written against SQLite with `Numeric` column
types *specifically* so this migration would be a cutover rather than a rewrite. The
guardrails below are what keep that true between now and then.

## Local development guardrails

1. **Alembic from day one, not "when we're closer to launch."** Every schema change is a
   migration, always. A schema that only exists as ORM models has no migration history
   to replay against a fresh Postgres instance.
2. **Query through the ORM, not raw dialect-specific SQL.** Raw SQL is where portability
   quietly dies.
3. **Test against both dialects, not just SQLite.** A local Docker Postgres is sufficient
   and does not need to wait for RDS.
4. **Environment-aware handling, not environment-specific code paths.** Dialect
   differences are handled by conditional migration steps, not by branching application
   logic.

## Three known compatibility gaps

| Feature | The gap | How to handle it in dev |
|---|---|---|
| **Partitioning** — `transactions`, `nav_history` | SQLite has no `PARTITION BY RANGE` | Create them as plain unpartitioned tables on SQLite; the Alembic migration applies partitioned DDL on Postgres. A dialect-conditional migration step (guardrail 4), not a schema redesign — columns, types, and constraints are identical either way |
| **`JSONB`** — `imports.raw_parser_output` | SQLite stores JSON as `TEXT` via JSON1 | Use SQLAlchemy's generic `JSON` type, which maps to `TEXT`-backed JSON on SQLite and native `JSONB` on Postgres automatically. **Avoid Postgres-specific JSONB operators (`->`, `->>`, `@>`) in application code** — if querying into raw parser output is ever needed, that logic needs a Postgres-only test, because it will not run against SQLite at all |
| **`ENUM` types** | Postgres has native enums; SQLite emulates them with `CHECK` | SQLAlchemy's `Enum` type already abstracts this. Listed only so it is not mistaken for work that needs doing |

## Readiness checklist

- [ ] Backend is deployed beyond local development (ADR-005's ECS Express Mode target),
      and RDS exists and is reachable from that environment.
- [ ] Alembic migration history is clean and has been exercised end to end against a real
      Postgres instance at least once — local Docker Postgres is sufficient.
- [ ] **No real user data has been collected yet.** This is the hard deadline per
      ADR-003, not a soft target. If the checklist is not complete before the first real
      user signs up, that is a launch blocker, not something to migrate around later.
- [ ] `otp_requests` / `sessions` and the reference tables populated by ADR-006's
      background jobs have been validated against Postgres specifically — those jobs are
      the first genuinely write-heavy, partition-touching workload the schema sees.

## Runbook

1. **Provision RDS for PostgreSQL** per ADR-003, at an instance size appropriate for MVP.
2. **Point Alembic at the RDS connection string**, via AWS Secrets Manager.
3. **Run the full Alembic migration history** — `alembic upgrade head` — against the
   fresh instance.
4. **Run the background jobs once, manually**, before flipping any real traffic. This
   populates reference data and is the first real exercise of the partitioned tables.
5. **Point the deployed backend's database configuration at RDS** and redeploy.
6. **Smoke-test the full CAS import → dashboard → analytics flow** against live RDS.
7. **Decommission local SQLite as the source of truth.** It remains fine for individual
   local development.

## Validation

- **Schema parity** — every table, column, type, constraint, and index in the schema
  document exists in RDS exactly as specified. A deliberate diff, not "the app seems to
  work."
- **Partitioning specifically** — confirm `transactions` and `nav_history` are genuinely
  partitioned and were not silently created as plain tables by an incorrectly written
  migration step. This is the one part of the schema with no SQLite equivalent to
  sanity-check against, so it gets explicit verification rather than assumed correctness.
- **The Postgres-specific test subset passes against RDS itself**, not only against the
  local Docker Postgres used in development.

## Rollback

Low-risk by construction. This is a fresh-schema cutover with no real user data at stake
— point the backend's configuration back at SQLite or at a corrected RDS instance and
re-run. There is no data-loss scenario to protect against, which is precisely why ADR-003
insisted this happen *before* real users rather than after. Once real user data exists,
future schema changes go through RDS's backup and point-in-time-recovery mechanisms
instead of this runbook's simpler assumptions.

## Ownership

Ayush and Siddhartha jointly own the go/no-go call once the checklist is met — it is a
launch-sequencing decision as much as a technical one.

## One deferred optimisation to pick up here

`category_ranking.py`'s `_bulk_nav_on_or_before` has a deferred `LATERAL`-join
optimisation that can only be properly closed out once Postgres is live. The full
context, including a benchmark that contradicts the obvious assumption, is in
[`07-risks-and-debt.md`](../../07-risks-and-debt.md). **Do not skip the measurement
step** — on the dev dataset the "obviously faster" shape measured slower.

## Related

- [ADR-003](../../03-decisions/ADR-003-primary-database-rds-postgresql.md),
  [ADR-005](../../03-decisions/ADR-005-deployment-architecture.md),
  [ADR-006](../../03-decisions/ADR-006-background-job-scheduling.md)
- [Data model](../../06-architecture/data-model.md)
