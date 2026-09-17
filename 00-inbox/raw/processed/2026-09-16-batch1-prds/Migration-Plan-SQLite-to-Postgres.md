---
artifact: migration-plan
version: "1.0"
created: 2026-08-04
status: draft
product: Unifolio
scope: Data layer (SQLite local development → AWS RDS PostgreSQL production)
---

# Data Layer Migration Plan: SQLite → AWS RDS PostgreSQL

## Purpose

ADR-003 already decided *that* Unifolio moves off SQLite onto RDS/PostgreSQL, and *when*
(before or at MVP launch, never after real user data starts flowing). What ADR-003 didn't
cover — and what this document exists to answer — is two things: **how to keep every day
of local development actually compatible with that future move** (so the migration is a
non-event, not a scramble), and **the concrete runbook for the day you execute it**.

## Guiding Principle: Portable by Construction

The schema was already designed Postgres-portable from day one (`NUMERIC` types, not
`FLOAT`; the whole reason SQLite was chosen as the prototype database in the first
place). This document extends that same discipline from "the schema" to "everything
built on top of the schema" — the ORM usage, the migration tooling, the query patterns,
and the test suite. If this is followed, the actual cutover becomes a deployment step, not
a rewrite.

## Local Development Guardrails

These are not one-time setup tasks — they're standing practices for every schema
change and every query written between now and cutover.

### 1. Alembic from day one, not "when we're closer to launch"
Every schema change — even during local SQLite prototyping — goes through an Alembic
migration script, never a hand-edited `CREATE TABLE` or an ORM `create_all()` call
against the dev database. This is the single highest-leverage guardrail: it means the
full history of schema evolution exists as versioned, reviewable scripts from the start,
and the migration to Postgres becomes "run the same migration history against a new
target" rather than "reverse-engineer what the current schema even is."

- SQLite's limited `ALTER TABLE` support (it can't drop/modify columns or constraints the
  way Postgres can) means Alembic's **batch mode** is required for SQLite-targeted
  migrations — Alembic creates a new table with the desired shape, copies data, and
  swaps it in. This is automatic in Alembic once configured, not something to hand-roll.
- Every migration script should be written with both dialects in mind, even before a real
  Postgres target exists locally — see Known Compatibility Gaps below for the specific
  places this matters.

### 2. Query through the ORM, not raw dialect-specific SQL
SQLAlchemy's query layer abstracts most dialect differences automatically. Raw SQL
strings (`text()` queries, hand-written `WHERE` clauses using SQLite-specific functions
like `strftime()`) are the most common way a codebase silently becomes SQLite-only
without anyone noticing until cutover day. Where raw SQL is genuinely needed for
performance, it needs an explicit dialect check and a Postgres-equivalent path written
alongside it, not deferred.

### 3. Test against both dialects, not just SQLite
SQLAlchemy's own maintainer guidance (and standard practice across the ecosystem) is
consistent: run the bulk of the test suite against SQLite for speed, but maintain a
smaller, explicitly-marked subset of "functional" tests that only run when a real
PostgreSQL connection is available (a local Docker Postgres container is the standard
way to do this cheaply). These functional tests should cover exactly the features flagged
in Known Compatibility Gaps below — the things that behave differently, not the whole
suite duplicated.

### 4. Environment-aware handling, not environment-specific code paths
Where SQLite and Postgres genuinely need different treatment (see below), that
difference should live in configuration/migration-script branching (Alembic supports
dialect-conditional migration steps), not in application code that checks "am I running
on SQLite or Postgres" at runtime. The application code should be written against one
abstraction; only the schema-definition layer should know which database it's talking to.

## Known Compatibility Gaps to Manage

Three specific places where the Database Schema's design choices don't translate
automatically, called out explicitly rather than discovered at cutover:

| Feature | Gap | How to Handle in Dev |
|---|---|---|
| **Table partitioning** (`transactions`, `nav_history` — Database Schema v1.1) | SQLite has no native `PARTITION BY RANGE` equivalent | These tables are created as plain, unpartitioned tables in the SQLite dev environment; the Alembic migration targeting Postgres applies the partitioned `CREATE TABLE` DDL instead. This is a dialect-conditional migration step (see Guardrail 4), not a schema redesign — the columns, types, and constraints are identical either way, only the physical partitioning differs |
| **`JSONB`** (`imports.raw_parser_output`) | SQLite has no native `JSONB` type — it stores JSON as `TEXT` via its JSON1 extension | Use SQLAlchemy's generic `JSON` type in models, which maps to `TEXT`-backed JSON on SQLite and native `JSONB` on Postgres automatically. The one thing to avoid in application code: don't write queries that rely on Postgres-specific JSONB operators (`->`, `->>`, `@>`) directly — if querying into the raw parser output is ever needed, that logic needs a Postgres-only functional test per Guardrail 3, since it won't run against SQLite at all |
| **`ENUM` types** (`import.status`, `transactions.type`, `folios.plan_type`, and others throughout the schema) | Postgres has native enum types; SQLite emulates them via a `CHECK` constraint | SQLAlchemy's `Enum` type handles this abstraction already — no special handling needed, just confirmed here so it's not mistaken for a gap that needs manual work |

## Deferred Postgres-Only Optimizations (Verify Once Postgres Is Live)

Findings from BUG-001/DATA-001 fix work (2026-08-18) that are correctness-safe on
SQLite today but can only be *properly* closed out — implemented and verified via a
real query plan — once Postgres is the dev/prod target, per this doc's own guardrails.
Listed here so they aren't lost between now and cutover, rather than living only in a
review thread.

- **`category_ranking.py`'s `_bulk_nav_on_or_before` (PRD-04 FR-3/FR-4, Category
  Ranking).** Rewritten from a per-(scheme, date) N+1 query pattern to one
  `MAX(date) GROUP BY scheme_id` join per target date (3 queries total per category,
  each returning exactly one row per scheme) — this closed the original BUG-001 defect
  (100+ *sequential* per-request ORM round-trips, the same class of bug
  `risk_metrics.build_monthly_series` was fixed for earlier in the same investigation).
  A scoped adversarial re-review confirmed ORM-side materialization is now correctly
  bounded, but flagged a narrower residual: without an index structure that supports a
  per-group skip-scan (a `LATERAL` join doing an index-seek + `LIMIT 1` per scheme,
  rather than a plain `GROUP BY`), the database still has to scan every historical row
  per scheme to compute each `MAX(date)` — bounded in what Python touches, not in what
  the DB reads.
  - **Why this is deferred, not fixed now:** the cost is already bounded to once per
    15-minute TTL window per category (this same fix's cache), not per-request — the
    original per-request cost is what's actually gone. A `LATERAL` join is a primitive
    not used anywhere else in this codebase, and its benefit can't be confirmed without
    a real Postgres query plan (`EXPLAIN ANALYZE`) — SQLite has no `LATERAL` semantics
    to compare against, so implementing it now would be unverifiable guesswork against
    this doc's own "test against both dialects, don't code blind for one" guardrail.
  - **Empirically measured, not just theoretical (2026-08-19):** rather than accept the
    `LATERAL`-would-be-faster claim on faith, both query shapes were benchmarked directly
    against the real dev SQLite DB (`backend/unifolio_dev.db`, 410,845 NAV rows, 143
    schemes sharing one SEBI category, per-scheme history up to 5,020 rows / ~20 years).
    Current `GROUP BY MAX(date)` approach: ~3.5s total across the 3 real target dates
    (`start_3y`/`start_5y`/`today`). A hand-written per-scheme correlated-subquery
    reformulation (SQLite's closest equivalent to the `LATERAL` shape below — `CO-ROUTINE`
    scan of schemes, `CORRELATED SCALAR SUBQUERY` doing the per-scheme index seek) measured
    **slower**, ~4.6s total, confirmed via `EXPLAIN QUERY PLAN` that it does perform the
    seek-per-scheme shape the reviewer described. On this dataset/engine, per-row
    correlated-subquery invocation overhead outweighs the row-scan savings — the seek
    shape is not a free win here. This does not contradict the deferral decision (SQLite's
    planner and cost model aren't Postgres's — the doc's own guardrail against coding
    blind for one dialect cuts both ways), but it does mean: don't treat "`LATERAL` is
    obviously faster" as a given when the Postgres `EXPLAIN ANALYZE` step below finally
    runs — measure it there too, since the SQLite result shows the theoretical direction
    can be wrong in practice at this data scale.
  - **Action once Postgres is live (Guardrail 3's local Docker Postgres is sufficient,
    doesn't need to wait for RDS):** run `EXPLAIN ANALYZE` against `_bulk_nav_on_or_before`'s
    three queries with a realistic category-universe size (100+ schemes, multi-year NAV
    history per scheme — mirror `nav_history`'s expected production row counts). If the
    planner isn't already using an index-backed skip-scan for the `GROUP BY`, rewrite the
    per-target-date query as a `LATERAL` join (`SELECT ... FROM schemes s, LATERAL
    (SELECT nav, date FROM nav_history WHERE scheme_id = s.id AND date <= :target ORDER
    BY date DESC LIMIT 1) nh`) backed by a composite index on `(scheme_id, date)` (already
    present per the Database Schema's `nav_history` indexing — confirm before assuming).
    Re-run the same `EXPLAIN ANALYZE` after the change to confirm the plan actually
    switched to an index seek before calling this closed.

## Migration Readiness Checklist

The signal to execute the runbook below isn't a calendar date — it's these conditions
being true, per ADR-003's "before or at MVP launch, never after real user data" framing:

- [ ] Backend is deployed beyond local development (per ADR-005's ECS Express Mode
      target) — RDS should exist and be reachable from that environment before this
      matters at all.
- [ ] Alembic migration history is clean and has been exercised end-to-end against a real
      Postgres instance at least once (the local Docker Postgres from Guardrail 3 is
      sufficient for this — it doesn't need to be RDS itself yet).
- [ ] No real user data has been collected yet — this is the hard deadline per ADR-003,
      not a soft target. If this checklist isn't complete before the first real user signs up,
      that's a launch blocker, not something to migrate around later.
- [ ] `otp_requests`/`sessions` (Database Schema's foundational auth tables) and the
      reference-data tables populated by ADR-006's background jobs have been validated
      against Postgres specifically, given ADR-006's jobs are the first real write-heavy,
      partition-touching workload the schema sees.

## Migration Runbook

Given the Readiness Checklist requires this to happen *before* real user data exists, this
is a **fresh-schema cutover, not a data migration** — there's no production SQLite data
to transfer, which simplifies this considerably versus a typical "migrate live data" runbook.

1. **Provision RDS for PostgreSQL** per ADR-003 — appropriate instance size for MVP
   scale (not over-provisioned; this is a small-team MVP, not a scaling exercise yet),
   within the VPC ADR-005's ECS Express Mode deployment uses.
2. **Point Alembic at the RDS connection string** (via AWS Secrets Manager, per the
   TDD's secrets-handling note) instead of the local SQLite file.
3. **Run the full Alembic migration history** (`alembic upgrade head`) against the fresh
   RDS instance — this creates every table, including the partitioned `transactions` and
   `nav_history` tables per their Postgres-specific migration steps (Known Compatibility
   Gaps above).
4. **Run the background jobs (ADR-006) once, manually**, before flipping any real traffic
   over — this populates the reference-data tables (`nav_history`, `scheme_ter`,
   `scheme_aaum`, `benchmark_index_history`) so the app isn't live against an empty
   reference-data set on day one.
5. **Point the deployed backend's database configuration at RDS** and redeploy.
6. **Smoke-test the full CAS import → dashboard → analytics flow** against the live RDS
   instance before considering this done — not just a schema check, an actual
   end-to-end functional pass.
7. **Decommission local SQLite as the "source of truth"** — it remains fine for individual
   developers' local iteration going forward (Guardrail 3's testing pattern doesn't change),
   it's just no longer where anyone's real work lives.

## Validation

- Schema parity: every table, column, type, constraint, and index in the Database Schema
  document exists in RDS exactly as specified — a straightforward diff against the schema
  doc, not just "the app seems to work."
- Partitioning verification specifically: confirm `transactions` and `nav_history` are
  genuinely partitioned in RDS (not silently created as plain tables if a migration step
  was written incorrectly) — this is the one piece of the schema that has no SQLite
  equivalent to sanity-check against, so it deserves explicit verification rather than
  assumed correctness.
- Full functional test suite (Guardrail 3's Postgres-specific subset) passes against RDS
  itself, not just the local Docker Postgres used during development.

## Rollback

Because this is a fresh-schema cutover with no real user data at stake (per the
Readiness Checklist), rollback is low-risk by construction: if something is wrong,
point the backend's configuration back at SQLite (or a corrected RDS instance) and
re-run the runbook — there's no data-loss scenario to protect against yet, which is
exactly why ADR-003 was firm about this happening *before* real users, not after. Once
real user data exists post-launch, any future schema changes go through RDS's standard
backup/point-in-time-recovery mechanisms instead of this runbook's simpler assumptions
— that's a different, future document if/when it's needed.

## Ownership & Timing

Per ADR-003: this happens before or at MVP launch, triggered by the Readiness Checklist
above being satisfied, not by a calendar date in isolation. Recommend Ayush and
Siddhartha jointly own the go/no-go call once the checklist is met, since it's a launch-
sequencing decision as much as a technical one.

## Appendix

### Related Documents
- ADR-003: Primary Database — the decision this plan implements
- Database Schema: Unifolio — the exact schema, including partitioning design (v1.1)
  that this plan's Known Compatibility Gaps section addresses
- ADR-005: Deployment Architecture — the ECS Express Mode environment RDS connects to
- ADR-006: Background Job Scheduling — the jobs that populate reference data as part
  of the runbook's Step 4
- TDD: Unifolio — secrets-handling approach referenced in Step 2

### Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-04 | Claude (PM partner) | Initial draft |
