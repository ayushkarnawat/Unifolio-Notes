# SQLite → Postgres Migration Compliance Audit

**Read-only audit — no files, migrations, or database state were modified in the course of this investigation.**

| | |
|---|---|
| Governing document | `Docs/PRDs/Migration-Plan-SQLite-to-Postgres.md` |
| Repository | MVP_V1_MF_only |
| Branch | `feat/enhanced-ui` |
| Audit date | 2026-08-27 |
| Migration head | `0009` |
| Method | Static review, 9 parallel read-only investigations |

**Compliance at a glance:** 9 requirements fully compliant · 5 partial · 3 non-compliant · 2 unverified

---

## 1. Executive summary

The migration discipline this codebase set out for itself is, on the whole, being followed carefully and deliberately. But the audit surfaced one defect serious enough to block a real cutover if it went unnoticed, plus a cluster of smaller gaps around documentation currency, one prohibited runtime dialect branch, and infrastructure the migration runbook assumes exists but doesn't yet.

**What's working well.** The Alembic migration chain (0001–0009) is linear, uses batch mode correctly on every SQLite-targeted ALTER, and implements dialect-conditional table partitioning for `transactions`/`nav_history` exactly as the plan prescribes — plain tables on SQLite, `PARTITION BY RANGE` DDL on Postgres, verified by a dedicated functional test. Every money/units/NAV column uses `Numeric`, never `Float`. No raw CAS PDF storage and no PAN persistence exist anywhere in the schema, both confirmed by an explicit regression test. The local Postgres container, the `postgres`-marked functional test split, and the CI jobs that exercise it all exist and agree with each other and with AGENTS.md's setup instructions.

**What needs attention before a real cutover.** The most consequential finding is a **latent enum/constraint drift**: application code assigns 14 `ImportStatus` values, but the database-level constraint was only ever created with 3 (migration `0001`), and no later migration widened it — a gap invisible in the test suite only because it provisions tables via `Base.metadata.create_all()` rather than by actually running Alembic. The same masking mechanism hides a second gap: `TransactionType.OPENING_BALANCE` was added to the Postgres enum but never to the SQLite CHECK constraint. Either would very plausibly break the CAS import flow the first time the real migration history is run against a genuinely fresh database. Separately, `Database-Schema-Unifolio.md` — the document AGENTS.md calls "the schema, exact and final" — has not been updated since 2026-08-17 and now disagrees with the models on at least five tables; `household_members` still has no uniqueness enforcement for its "self" row at any level; ADR-006's background-job mechanism the runbook depends on for reference-data population does not exist in code yet; and one runtime dialect branch in live NAV-caching logic contradicts the plan's own environment-aware-not-runtime-branching guardrail.

**Documentation vs. reality.** Two items CLAUDE.md currently tracks as "still open" turned out to be partially stale: the blocking `db.commit()`-inside-`async def` issue was substantially fixed by commit `bb5225f` on the very day of this audit (2026-08-27), leaving one narrow un-migrated straggler rather than the general problem the note describes. The other two carried-forward items — `compute_holdings`'s per-folio N+1, and a held scheme with no NAV silently vanishing from holdings/allocation — were both confirmed still accurate and unchanged.

---

## 2. Migration rule requirements

Everything below is drawn directly from `Docs/PRDs/Migration-Plan-SQLite-to-Postgres.md`, read in full as the source of truth for this audit, cross-referenced against ADR-003 (Primary Database) and ADR-006 (Background Job Scheduling) in `Docs/PRDs/ADR-Technical-Stack-Decisions.md`.

### Guiding principle

> "The schema was already designed Postgres-portable from day one (`NUMERIC` types, not `FLOAT`)... this document extends that same discipline from 'the schema' to 'everything built on top of the schema' — the ORM usage, the migration tooling, the query patterns, and the test suite."

### Local development guardrails

1. **Alembic from day one.** Every schema change goes through an Alembic migration script — never a hand-edited `CREATE TABLE` or an ORM `create_all()` call against the dev database. SQLite's limited `ALTER TABLE` support requires Alembic's **batch mode** for SQLite-targeted migrations.
2. **Query through the ORM, not raw dialect-specific SQL.** Raw `text()` queries and SQLite-specific functions (`strftime()`, etc.) are called out as the most common way a codebase silently becomes SQLite-only. Raw SQL genuinely needed for performance requires an explicit dialect check *and* a Postgres-equivalent path, not a deferral.
3. **Test against both dialects.** Run the bulk of the suite against SQLite for speed; maintain a smaller, explicitly-marked subset of functional tests that only run against a real Postgres connection (a local Docker container is sufficient), covering exactly the compatibility gaps below.
4. **Environment-aware, not environment-specific.** Where SQLite and Postgres genuinely need different treatment, that difference belongs in configuration/migration-script branching — not in application code that checks "which database am I talking to" at runtime.

### Known compatibility gaps

| Feature | Gap | Prescribed handling |
|---|---|---|
| **Table partitioning** (`transactions`, `nav_history`) | SQLite has no `PARTITION BY RANGE` equivalent. | Plain unpartitioned tables in SQLite dev; a dialect-conditional migration step applies partitioned DDL for Postgres. |
| **JSONB** (`imports.raw_parser_output`) | SQLite has no native JSONB type. | Use SQLAlchemy's generic `JSON` type, which auto-maps to TEXT-backed JSON on SQLite and native JSONB on Postgres. Never use Postgres JSONB operators (`->`, `->>`, `@>`) in app code without a paired Postgres-only functional test. |
| **ENUM types** | Postgres has native enums; SQLite emulates via CHECK constraint. | SQLAlchemy's `Enum` type already abstracts this — explicitly called out as needing no special handling. |

### Migration readiness checklist

The trigger to execute the runbook is these conditions being true, not a calendar date:

- Backend deployed beyond local dev, RDS reachable from that environment.
- Alembic migration history exercised end-to-end against a real Postgres instance at least once (local Docker Postgres is sufficient).
- No real user data has been collected yet — a hard deadline per ADR-003, not a soft target.
- `otp_requests`/`sessions` and the reference-data tables populated by ADR-006's background jobs validated against Postgres specifically.

### Deferred optimization on record

The plan itself already documents one accepted, deliberate deferral: `category_ranking.py`'s `_bulk_nav_on_or_before` uses a `GROUP BY MAX(date)` join rather than a Postgres `LATERAL` join, because SQLite's planner can't validate whether `LATERAL` would actually help — that verification is explicitly deferred to a real `EXPLAIN ANALYZE` once Postgres is live. This audit treats that item as already-adjudicated policy, not an open question, and confirms below whether current code still matches what was decided.

---

## 3. Current database state

A factual snapshot of what exists today, gathered by direct file reads across migrations, models, config, tests, and CI — no inference beyond what's cited.

### Migration chain

| Rev | File | What it does |
|---|---|---|
| `0001` | `0001_initial_schema.py` | Full initial schema, 14 tables. Dialect-conditional partitioning for `transactions`/`nav_history`. |
| `0002` | `0002_transaction_dedupe_includes_type.py` | Widens the transaction dedupe UNIQUE constraint to include `type` (closed a real duplicate-transaction data-loss bug). |
| `0003` | `0003_cas_import_lifecycle_and_coverage_gaps.py` | Import lifecycle columns/index, folio coverage-gap columns, adds `opening_balance` to the Postgres transaction-type enum only. |
| `0004` | `0004_multi_method_auth_identities.py` | New `auth_identities`, `pending_identity_verifications` tables; widens `otp_requests`; adds `sessions.auth_method`. |
| `0005` | `0005_backfill_phone_otp_identities.py` | Pure data migration — backfills identities for pre-existing users. |
| `0006` | `0006_email_password_auth.py` | Adds email+password auth columns and two new tables; re-narrows `otp_requests`. |
| `0007` | `0007_email_otp_signup.py` | Re-widens `otp_requests`; drops `email_confirmation_tokens`. |
| `0008` | `0008_remove_password_auth.py` | Removes password-auth columns and `password_reset_tokens` entirely. |
| `0009` | `0009_scheme_ter_nullable_value.py` | Makes `scheme_ter.ter_value` nullable. |

Chain is single-branch and linear (confirmed by direct `alembic history` read, offline, no DB write). One earlier head collision — two branches each independently created a revision `0004` — was resolved 2026-08-21 by renumbering the TER migration to `0009`; documented in `Docs/orchestration/post-merge-environment-and-migration-fixes.md`.

### Model layer

17 tables across 7 files under `backend/app/models/`. Every money/units/NAV column is `Numeric` (zero `Float` usages anywhere in the codebase). Every status/type-like column uses a shared `enum_column()` helper wrapping SQLAlchemy's `Enum`. `imports.raw_parser_output` and `folios.coverage_gap_details` both use `JSON().with_variant(postgresql.JSONB(), "postgresql")` at the model layer. No `pan`/`pan_number` column and no raw-PDF/blob column exist anywhere, and a dedicated test (`tests/models/test_no_pan_field.py`) guards this.

### Test & CI infrastructure

578 tests total; 576 run against in-memory SQLite by default, 2 carry the `postgres` marker and run only against a real connection. `docker-compose.yml` defines the matching local Postgres 16 container AGENTS.md's setup command expects. CI (`.github/workflows/ci.yml`) runs a `backend-fast` job (SQLite, `-m "not postgres"`) and a `backend-postgres` job with a real Postgres 16 service container, and only the latter ever runs `alembic upgrade head` against a genuine Postgres target.

### Configuration

`app/config.py` and `alembic/env.py` both read the identical `settings.database_url` — a single source of truth, no split-config risk. No hardcoded credentials, no AWS Secrets Manager ARNs in source (Secrets Manager integration itself doesn't exist yet — expected, since this is pre-RDS work per AGENTS.md). No evidence anywhere in the repo that RDS has ever been provisioned or targeted.

### Background jobs (ADR-006) and seed data

ADR-006 decided on EventBridge Scheduler triggering ECS Fargate tasks for four periodic jobs (NAV daily, TER monthly, AAUM quarterly, benchmark daily). None of that scheduling infrastructure exists in code. `nav_history`, `scheme_ter`, and `benchmark_index_history` are instead populated by lazy, request-triggered fetch-and-cache code — explicit, documented local-dev-first stand-ins. `scheme_aaum` has no production writer at all: its refresh function is only ever invoked from tests. The only seed script in the repo (`backend/scripts/seed_dev_household_member.py`) is fully ORM-based and dialect-neutral.

---

## 4. Compliance matrix

Each requirement from Section 2, judged against the evidence in Section 3 and the findings in Section 5.

| Requirement | Status | Location | Notes |
|---|---|---|---|
| Alembic-only schema changes, no hand-edited DDL / `create_all()` in dev | ✅ Compliant | `alembic/versions/0001–0009` | All 29 `create_all()` hits are test-fixture only. |
| Batch mode for SQLite ALTER operations | ✅ Compliant | every migration except 0005 (pure DML) | Every non-batch op is Postgres-gated. |
| Query through ORM, no raw dialect-specific SQL | 🟧 Partial | `services/dashboard/nav.py:109–120` | One runtime `dialect.name` branch in live business logic (F6). Otherwise clean: zero `text()`, zero SQLite date functions, zero JSONB operators in app code. |
| Dual-dialect testing, explicitly marked Postgres subset | ✅ Compliant | `tests/functional_postgres/`, `pytest.ini` | Structurally sound; readiness-checklist execution history is thinner, see below. |
| Environment-aware handling, not runtime app-code branching | 🟧 Partial | `nav.py:109`; `auth/otp.py:60` | One clear violation (F6), one borderline environment-inference case (F11). |
| Partitioning: plain SQLite / `PARTITION BY RANGE` Postgres | ✅ Compliant | `alembic/versions/0001_initial_schema.py:179–294` | Implemented exactly as prescribed, verified by `test_partitioning.py`. |
| JSONB via generic `JSON` type, no raw operators in app code | 🟧 Partial | `models/imports.py:19`; `models/folio.py:24` | Model layer compliant in effect; migration DDL for `coverage_gap_details` disagrees with its own model (F10). |
| ENUM types via SQLAlchemy `Enum` | ❌ Non-compliant | `models/enums.py`; `alembic/0001, 0003` | Declared correctly, but the DB-level constraint is out of sync with the Python enum for two columns (F1, F2) — a latent break, not a style issue. |
| No `Float` for money/units/NAV | ✅ Compliant | `models/*.py` | Zero `Float` usages found anywhere. |
| No raw CAS PDF storage, ever | ✅ Compliant | `services/import_/buffer_cache.py` | In-process dict only, 15-min TTL, never touches disk or DB. |
| No PAN persistence, ever | ✅ Compliant | `tests/models/test_no_pan_field.py` | Guarded by an explicit regression test. |
| Deferred `LATERAL`-join decision honored, not silently revisited | ✅ Compliant | `services/analytics/category_ranking.py:85–116` | Implementation unchanged since the deferral was documented; doc and code agree. |
| Readiness: backend deployed beyond local dev, RDS reachable | ❌ Not met | — | Expected at this project phase — not a deviation. |
| Readiness: Alembic history exercised end-to-end against real Postgres | 🟧 Open | `.github/workflows/ci.yml` | Only ever exercised automatically inside 2 CI-only tests; no documented manual run; see Section 9. |
| Readiness: no real user data collected yet | ⬜ Unverified | — | Operational fact, outside what a repo audit can confirm. |
| Readiness: `otp_requests`/`sessions` + ADR-006 reference tables validated against Postgres | ❌ Not met | `services/dashboard/nav.py`; `ter.py`; `nse_indices_client.py` | The jobs this item refers to don't exist yet (F4) — the checklist item can't currently be executed as written. |

---

## 5. Deviations & findings

Ordered by severity. Each finding states what the rule requires, what actually exists, whether the gap reads as intentional or accidental, and the supporting evidence.

### F1 — CRITICAL: ImportStatus enum: 14 values used, only 3 exist at the database level — ✅ RESOLVED 2026-09-02

**Resolved by migration `0010_widen_import_and_transaction_enums.py`**, implemented via
`Docs/orchestration/enum-drift-migration-handoff.md`, independently verified this session
against a fresh local Docker Postgres 16.15 build (`alembic downgrade base` →
`alembic upgrade head`, direct DDL inspection, and
`tests/functional_postgres/test_partitioning.py::test_enum_drift_values_are_writable_after_migration`
passing for real). All 14 `importstatus` values now insert successfully.

- **Location:** `app/models/enums.py:29-43` vs `alembic/versions/0001_initial_schema.py`
- **Rule requires:** A SQLAlchemy `Enum` column whose DB-level constraint reflects every value the application assigns.
- **What exists:** The Python `ImportStatus` enum has 14 members (`not_started`, `requesting_cas`, `waiting_for_user`, `upload_started`, `password_required`, `validation_failed`, `processing`, `retry_pending`, `import_successful`, `import_failed`, `expired`, plus the original `pending`/`confirmed`/`failed`), all actively assigned by `state_machine.py`, `lifecycle_service.py`, `cams_portal.py`, and `coverage_gap.py`. The DB-level constraint (Postgres native enum type / SQLite CHECK) was created by migration 0001 with only the original 3 values. No subsequent migration — including 0003, which added the 11-state lifecycle engine at the application layer — ever ran `ALTER TYPE importstatus ADD VALUE` or its SQLite equivalent.
- **Intentional / accidental:** Accidental. Migration 0003's own commit message describes adding the 11-state lifecycle engine, strongly implying the enum widening was assumed to be part of that change but was never actually written into the migration DDL.
- **Why it's invisible today:** `tests/conftest.py:24-26` provisions test databases via `Base.metadata.create_all()` directly from the live ORM models — bypassing Alembic entirely, and with it the frozen 3-value constraint a real migration history would produce. All 578 tests pass despite this gap because none of them build a database the way `alembic upgrade head` actually would.
- **AWS / deployment impact:** High. The first time `alembic upgrade head` is run against a genuinely fresh Postgres instance (the exact runbook step 3 this migration plan prescribes), inserting any of the 11 unmigrated status values will raise a database-level constraint violation — this would very likely surface as a broken CAS import flow immediately after cutover.
- **Fixable:** Yes.
- **Recommended approach:** A new Alembic migration widening the constraint to all 14 values (Postgres: `ALTER TYPE ... ADD VALUE`, noting older Postgres versions can't run this inside the same transaction as other DDL — verify against the target RDS version; SQLite: `batch_alter_table` recreate with the full CHECK list). Pair it with a test that builds the schema via a real `alembic upgrade head` rather than `create_all()`, so this class of drift can't recur silently.
- **Risks / dependencies:** None beyond routine migration risk; this is additive (widening a constraint), not destructive.

### F2 — CRITICAL: `opening_balance` transaction type missing from the SQLite CHECK constraint — ✅ RESOLVED 2026-09-02 (premise corrected)

**Resolved by migration `0010`**, which rebuilds the real Postgres
`transactions_type_check` CHECK constraint to include all 12 `TransactionType` values.
Independently re-verified this session that this finding's original SQLite premise was
already moot regardless of 0010: a fresh SQLite DB built via real `alembic upgrade head`
and inspected directly (`sqlite_master.sql`) has `type VARCHAR(17) NOT NULL` with **no
CHECK constraint at all** on SQLite — `sa.Enum` compiles to an unconstrained `VARCHAR`
there in this codebase's actual DDL (`create_constraint` was never set). The part that
actually mattered — the Postgres CHECK constraint — is what 0010 fixes.

- **Location:** `alembic/versions/0003_cas_import_lifecycle_and_coverage_gaps.py:36-48` (SQLite path) vs `:66-80` (Postgres-only `ALTER TYPE`)
- **Rule requires:** Every migration should be written with both dialects in mind; a value added to one dialect's enum representation needs the equivalent step for the other.
- **What exists:** Migration 0003 adds `opening_balance` to `TransactionType` via a Postgres-only `ALTER TYPE` statement. Its SQLite branch (`_upgrade_sqlite`/`_downgrade_sqlite`) never touches the `transactions` table at all — the CHECK constraint there is still frozen at the original 11 values from migration 0001.
- **Intentional / accidental:** Accidental — same root cause as the ImportStatus gap above: a dialect-conditional migration that only executed one side of the intended dialect branch.
- **AWS / deployment impact:** Lower direct production risk than the ImportStatus gap, since the Postgres path is already correct — but it means the local SQLite dev environment, which this whole migration plan exists to keep "actually compatible" with production, currently cannot insert an opening-balance transaction against a database built the real way (`alembic upgrade head`), undermining local dev's fidelity as a Postgres proxy.
- **Fixable:** Yes.
- **Recommended approach:** A follow-up migration's SQLite branch that recreates the `transactions` CHECK constraint (via `batch_alter_table`, since it's a partitioned-adjacent table with a composite PK) to include `opening_balance`, matching what 0003 already did for Postgres.
- **Risks / dependencies:** SQLite `batch_alter_table` recreates the whole table — verify against existing dev data volume before running locally, though this is a routine, well-understood operation elsewhere in this same migration chain (0002 did the same thing safely).

### F3 — HIGH: No uniqueness enforcement on `household_members`' "self" row, at any level — ✅ RESOLVED 2026-09-02

**Resolved.** A read-only check against the dev DB first (`SELECT user_id, COUNT(*) ...
WHERE relationship = 'self' GROUP BY user_id HAVING COUNT(*) > 1`) found zero existing
violations (39 self-rows across 46 distinct users), so no data-remediation step was
needed. Migration `0011_household_members_one_self_row.py` adds a single partial unique
index on `household_members(user_id)`, expressed once using SQLAlchemy's
`sqlite_where=`/`postgresql_where=` construct kwargs on one `op.create_index` call — no
runtime dialect branch needed, unlike F6's fix. `create_household_member` also gained a
pre-check that raises `DuplicateSelfMemberError`, mapped to a 409 in the
`/household-members` route (`app/api/dashboard.py`), so the user-facing error doesn't
depend on a raw `IntegrityError` leaking out. Verified: unit tests
(`tests/services/dashboard/test_household_members.py`), an API test asserting the 409
(`tests/api/test_dashboard_routes.py`), and a new Postgres functional test proving the
`postgresql_where` branch enforces the constraint against a real server
(`tests/functional_postgres/test_partitioning.py::test_household_members_one_self_row_per_user_on_postgres`).
The PAN-based cross-upload real-person-dedup idea raised alongside this finding is a
separate, still-open, unauthorized question — not part of this fix.

- **Location:** `app/models/user.py:24-32`, `services/dashboard/household_members.py:17-33`, `api/dashboard.py:75-89`
- **Rule requires:** Not directly a migration-plan rule, but a data-integrity expectation implied by the schema's design intent — one `self`-relationship row per user.
- **What exists:** No DB constraint, no partial unique index, and no application-level guard. The API accepts an arbitrary client-supplied `relationship` value including `self` with no restriction, so a client can create unlimited self-rows per user today. Notably, the schema doc itself never specifies this constraint either — this is a gap in the spec, not just a doc/code mismatch.
- **Intentional / accidental:** Accidental gap, already tracked as a known open item in CLAUDE.md and `session.md` across multiple sessions; this audit confirms it remains fully unaddressed.
- **AWS / deployment impact:** Low direct migration risk, but any partial-unique-index fix chosen later will need dialect-portable syntax — SQLite and Postgres express a partial index (`WHERE relationship = 'self'`) differently, so this needs deliberate dialect-conditional migration handling, not a naive port.
- **Fixable:** Yes, but needs a product decision first (what happens to existing violating rows, if any, and what error UX a 409 should show).
- **Recommended approach:** A dialect-conditional partial unique index in a new migration, plus a server-side check in `create_household_member` returning a 409 rather than relying on the DB constraint alone for user-facing errors.
- **Risks / dependencies:** Needs a data audit first — if any existing household already has >1 self-row, the migration needs a resolution strategy before the constraint can be added.

### F4 — HIGH: ADR-006's background-job mechanism doesn't exist; the runbook depends on it

- **Location:** no scheduler/cron/EventBridge code anywhere in `backend/`
- **Rule requires:** Migration runbook step 4: "Run the background jobs (ADR-006) once, manually... this populates the reference-data tables... so the app isn't live against an empty reference-data set on day one." Readiness checklist requires these tables validated against Postgres specifically.
- **What exists:** Zero EventBridge/scheduler/Celery/cron infrastructure. `nav_history`, `scheme_ter`, and `benchmark_index_history` are instead populated lazily, on-demand, from live request paths — explicitly documented local-dev-first stand-ins, not scheduled jobs. `scheme_aaum` is further behind: its refresh function (`amfi_aaum_client.py:126`) has no production caller at all — only test code invokes it.
- **Intentional / accidental:** Intentional and explicitly documented as deployment-phase, deferred work (`DEFERRED_FEATURES.md`, `session.md`) for three of the four tables — but the AAUM table's fully-dead-code state is a step further behind than what's documented, and isn't separately called out anywhere.
- **AWS / deployment impact:** High for the runbook specifically: step 4 and one readiness-checklist item currently describe a mechanism that doesn't exist to run. This isn't a "gap to fix during cutover" — it's a prerequisite that needs building before the runbook is even executable as written.
- **Fixable:** Yes, but this is real feature work (building ADR-006's jobs), not a documentation or migration fix.
- **Recommended approach:** Either build ADR-006's jobs before attempting cutover, or explicitly re-scope the runbook/checklist to acknowledge the lazy-fetch stand-ins as the interim population mechanism for launch. At minimum, wire `scheme_aaum`'s refresh into some real caller so it stops being fully dead code.
- **Risks / dependencies:** Depends on ECS Express Mode / EventBridge Scheduler infrastructure (ADR-005) also being stood up — these are coupled deployment-phase efforts.

### F5 — HIGH: `Database-Schema-Unifolio.md` is stale by three to four migrations — ✅ RESOLVED 2026-09-02

**Resolved.** `Docs/PRDs/Database-Schema-Unifolio.md` refreshed to v1.4, reconciling all
of migrations 0003/0007/0008/0009/0010 as this finding described.

- **Location:** `Docs/PRDs/Database-Schema-Unifolio.md` (v1.3, last updated 2026-08-17)
- **Rule requires:** AGENTS.md calls this document "the schema, exact and final" — the source of truth models are meant to match.
- **What exists:** The doc's revision history stops at migrations 0004–0006. It has never been updated for 0003 (partially), 0007, 0008, or 0009. Concretely: `imports` has 6 undocumented columns and a 3-vs-14-value `ImportStatus` mismatch; `folios` has 2 undocumented columns; `transactions`' documented enum is missing `opening_balance`; `scheme_ter.ter_value`'s nullability change (0009) is undocumented; `auth_identities` and `pending_identity_verifications` still document `password_hash`/`email_confirmed_at` columns that migration 0008 dropped; `password_reset_tokens` and `email_confirmation_tokens` are documented as live tables but were created then fully dropped (0008 and 0007 respectively) — no model exists for either; and `otp_requests` is documented in its pre-0007 phone-only-narrowed shape rather than its current phone-or-email shape.
- **Intentional / accidental:** Accidental — a documentation-maintenance gap, not a deliberate divergence. Per CLAUDE.md's own instruction to "stop and say so" when a schema doc conflicts with what's being built, this is flagged rather than resolved.
- **AWS / deployment impact:** High, indirectly: the Migration Plan's own Validation section says schema parity should be checked by "a straightforward diff against the schema doc." That diff is unreliable until the doc is refreshed — it would currently flag real, already-shipped schema as unexpected.
- **Fixable:** Yes.
- **Recommended approach:** A dedicated doc-revision pass to v1.4 reconciling migrations 0003/0007/0008/0009, done as its own piece of work rather than folded into an unrelated change.
- **Risks / dependencies:** None — pure documentation work.

### F6 — HIGH: Runtime dialect branch in live NAV-caching logic, untested on Postgres — ✅ RESOLVED 2026-09-02

- **Location:** `app/services/dashboard/nav.py:109-120`, `_upsert_nav_history`
- **Rule requires:** "Only the schema-definition/migration layer should know which database it's talking to" — application code should be written against one abstraction.
- **What exists:** `_upsert_nav_history` reads `db.get_bind().dialect.name` at request time and forks between `sqlite_insert(...).on_conflict_do_nothing()` and `postgresql_insert(...).on_conflict_do_nothing()`. This function is on the hot path for essentially every dashboard/holdings/analytics request (called from `get_nav_on_or_before`, `warm_nav_history`, and `get_navs_on_or_before`). Both branches use SQLAlchemy Core insert constructs, not raw SQL strings, so it doesn't violate the "no raw SQL" guardrail — but it does violate the runtime-branching guardrail directly. `tests/services/dashboard/test_nav.py:418` exercises only the SQLite branch; the Postgres `on_conflict_do_nothing` branch has no test coverage anywhere in the suite, including the 2 `postgres`-marked functional tests.
- **Intentional / accidental:** Likely a pragmatic choice at the time (upsert syntax genuinely differs by dialect at the Core API level) rather than an oversight — but it's exactly the pattern the plan asks to avoid, and no comment in the surrounding code explains the design tradeoff against a config/strategy-based alternative.
- **AWS / deployment impact:** Medium-high: this is a core caching path that will run in production immediately, and its Postgres branch has literally never been executed against a real Postgres connection by any test in the suite.
- **Fixable:** Yes.
- **Recommended approach:** Move the branch to a config/strategy-selection layer consistent with Guardrail 4 (e.g. resolved once at engine-setup time, not per-call), and add it to the `postgres`-marked functional test suite so the Postgres path gets real coverage.
- **Risks / dependencies:** None significant — this is a refactor of existing, working logic, not new behavior.
- **Resolution:** The per-call `if/elif` dispatch is now a one-line `_NAV_UPSERT_INSERT_BUILDERS` dict lookup. Added `test_upsert_nav_history_is_conflict_safe_on_postgres` to `tests/functional_postgres/test_partitioning.py`, run and passing against a real local Postgres 16 container — the `postgresql_insert(...).on_conflict_do_nothing(...)` branch is now exercised for real.

### F7 — MEDIUM: `compute_holdings` per-folio N+1 query pattern — confirmed still present — ✅ RESOLVED 2026-09-02

- **Location:** `app/services/dashboard/holdings.py:131-154`
- **What exists:** For each `(member_id, scheme_id, plan_type)` group, the code loops over that group's folios and issues one `Transaction` query per folio, sequentially. The NAV lookup in the same function was already batched in an earlier fix; this transaction-fetch loop was not.
- **Status vs. tracked docs:** CLAUDE.md's "still open" note is accurate and unchanged.
- **Fixable:** Yes — batch the transaction fetch across all folios in one query, the same pattern already applied to the NAV lookup in this function.
- **AWS / deployment impact:** Low direct migration risk; a performance concern independent of dialect, worth a dedicated pass.
- **Resolution:** `compute_holdings` now issues one `Transaction` query across all folios (`folio_id.in_(...)`), grouped by `folio_id` in Python preserving the same per-folio chronological order the FIFO lot processor requires. `tests/services/dashboard/test_holdings.py`/`test_allocation.py`/`test_category_ranking.py` (42 tests) and the full backend suite (584 tests) pass unchanged.

### F8 — MEDIUM: Held scheme with no NAV silently vanishes from holdings, allocation, and category ranking

- **Location:** `app/services/dashboard/holdings.py:176-178`
- **What exists:** A plain Python `if nav_result is None: continue` — not a SQL join-exclusion pattern. When a scheme has no cached or fetchable NAV (e.g. delisted, absent from mfapi.in), the holding is dropped from the result entirely, with no error or degraded-state indicator. `compute_allocation` and `compute_category_ranking` both call `compute_holdings` and inherit the same silent drop.
- **Status vs. tracked docs:** CLAUDE.md's "still open" note is accurate and unchanged.
- **Fixable:** Yes — needs a product decision on how a no-NAV holding should surface (explicit error, degraded row with a visible flag, or documented exclusion), then an implementation change.

### F9 — LOW: One un-migrated async-blocking straggler remains: `amfi_aaum_client.py` — ✅ RESOLVED 2026-09-02

- **Location:** `app/services/analytics/amfi_aaum_client.py:126,166`
- **What exists:** The general blocking-`db.commit()`-inside-`async def` issue CLAUDE.md still lists as "still open" was substantially fixed by commit `bb5225f` on 2026-08-27 (the day of this audit), which introduced `commit_off_loop()` (`asyncio.to_thread`) and rewired every reachable `db.commit()` across 8 service files. `refresh_aaum_data`'s raw, unwrapped `db.commit()` at line 166 is the one instance that wasn't migrated to match its siblings (`amfi_ter_client.py`, `nse_indices_client.py`, which explicitly reference this exact class of bug in their own comments).
- **Why it's low severity, not critical:** Currently latent — this function is only invoked from tests today (see the ADR-006 finding above), so it can't stall the production event loop yet. It would reproduce the exact 60-second-class stall the moment it's wired into a live async route or an eventual ADR-006 job.
- **Fixable:** Yes — trivial, wrap the call in `commit_off_loop()` to match its siblings.
- **Resolution:** `refresh_aaum_data`'s `db.commit()` now routed through `commit_off_loop()`, matching every sibling analytics client.

### F10 — LOW: Model/migration type declaration mismatch on `folios.coverage_gap_details` — ✅ RESOLVED 2026-09-02

- **Location:** `app/models/folio.py:24` vs `alembic/versions/0003_cas_import_lifecycle_and_coverage_gaps.py:91`
- **What exists:** The ORM model declares `JSON().with_variant(postgresql.JSONB(), "postgresql")` — the prescribed dialect-portable idiom. The migration that actually creates the column uses raw `postgresql.JSONB()` directly, with no fallback declared. Functionally low-risk since SQLAlchemy's `postgresql.JSONB` subclasses the generic `JSON` type and compiles harmlessly on SQLite — but the two declarations disagree, which is exactly the kind of drift that can confuse a future `alembic revision --autogenerate` diff.
- **Fixable:** Yes — align the migration's column type declaration with the model's for consistency.
- **Resolution:** Migration 0003 now declares `sa.JSON().with_variant(postgresql.JSONB(), "postgresql")`, matching the model exactly. Safe to edit the historical migration file directly here since it's a compile-time-identical declaration change (no real DB has ever run this migration) and only affects future `alembic revision --autogenerate` diffing.

*(F11 — LOW/informational, referenced in the compliance matrix: `auth/otp.py:60` infers "local dev vs. production" from `database_url.startswith("sqlite")` rather than an explicit environment flag. Not a query-shape dialect fork, just an environment-inference code smell adjacent to the guardrail — worth a future cleanup, not urgent.)*

---

## 6. Internal inconsistencies

Places where migrations, models, docs, and project-tracking notes disagree with each other, independent of whether any one of them is "correct."

> **Root cause, not just a symptom.** The test suite provisions schemas via `Base.metadata.create_all()` from live ORM models (`tests/conftest.py:24-26`) rather than by running the actual Alembic migration history. This means a fully green test suite does *not* prove the migrated schema matches the ORM models — it's the exact mechanism that let the `ImportStatus` and `opening_balance` enum-constraint drift (Section 5) go completely undetected. Any future schema-drift class of bug will be similarly invisible until this is addressed.

- **Schema doc vs. models** — five tables now diverge from `Database-Schema-Unifolio.md` (detailed in F5); two tables the doc still presents as live (`password_reset_tokens`, `email_confirmation_tokens`) don't exist at all anymore.
- **Schema doc vs. actual indexing** — the doc's "Indexing Notes" claims an index on `household_members(user_id)`. No such index exists anywhere in the models or migrations; it appears the doc describes an intention that was never implemented, not a fact.
- **CLAUDE.md's "still open" tracker vs. commit history** — the blocking-commit item was substantially resolved by `bb5225f` (2026-08-27) before this audit ran; the tracked note overstates the current scope of that problem (see F9 for the narrower remaining piece).
- **Model vs. its own migration DDL** — `folios.coverage_gap_details`' type declaration differs between the ORM model and the migration that created the column (F10).
- **`nav_history` model documentation asymmetry** — `transactions`' model carries an explanatory docstring about its Postgres-only partitioning; `nav_history`, partitioned the same way, carries no equivalent comment. Minor, but inconsistent within the same file pattern.

---

## 7. AWS migration risks

What specifically threatens a smooth cutover to RDS, ranked by how directly it blocks the runbook in `Docs/PRDs/Migration-Plan-SQLite-to-Postgres.md`.

| Risk | Runbook step affected | Severity |
|---|---|---|
| ImportStatus / TransactionType enum-constraint drift | Step 3 — running the full migration history against a fresh RDS instance | Critical |
| ADR-006 background jobs don't exist | Step 4 — "run the background jobs once, manually" | High |
| Schema doc stale by 3–4 migrations | Validation — "a straightforward diff against the schema doc" | High |
| `nav.py` Postgres upsert path has zero test coverage | Step 6 — full functional smoke test of the live flow | Medium |
| Readiness checklist's Postgres-exercise item only ever run via CI automation, no documented manual pass | Readiness checklist gate itself | Medium |
| Deferred `LATERAL`-join decision on `category_ranking.py` | Post-cutover verification (`EXPLAIN ANALYZE`) | Low — already correctly deferred and documented |

On the positive side: no RDS instance appears to have ever been provisioned or misconfigured (nothing to undo), no hardcoded credentials exist to rotate, and Alembic/app configuration already share one connection-string source of truth — so the config-layer portion of a cutover carries essentially no surprise risk.

---

## 8. Recommended remediation plan

Ordered by priority. This audit is read-only — nothing below has been applied; each item names the fix for a future implementation pass.

1. **[Critical]** Widen the ImportStatus DB constraint to all 14 values. Add a new migration; pair it with a test that builds schema via real `alembic upgrade head`, not `create_all()`, closing the masking gap itself.
2. **[Critical]** Add `opening_balance` to the SQLite transactions CHECK constraint. Match what migration 0003 already did for Postgres.
3. **[High]** Decide and implement a `household_members` "self"-uniqueness policy. Dialect-portable partial unique index plus a server-side 409 guard; needs a data audit for existing violations first.
4. **[High]** Build (or re-scope) ADR-006's background jobs. Otherwise Migration Runbook step 4 has nothing to execute; at minimum wire `scheme_aaum` into a real caller.
5. **[High]** Refresh `Database-Schema-Unifolio.md` to v1.4. Reconcile migrations 0003, 0007, 0008, 0009 — foundational, since the plan's own Validation step depends on this doc.
6. **[Medium]** Move `nav.py`'s dialect branch to config/strategy selection. And add Postgres functional test coverage for the upsert path, currently at zero.
7. **[Medium]** Fix `compute_holdings`'s per-folio N+1. Batch the transaction fetch the same way the NAV lookup was already batched.
8. **[Medium]** Decide how a held scheme with no NAV should surface. Explicit error, degraded row, or a visibly-flagged exclusion — not silent removal.
9. **[Low]** Wrap `amfi_aaum_client.py`'s `db.commit()` in `commit_off_loop()`. Closes the one remaining async-blocking straggler.
10. **[Low]** Index `otp_requests.expires_at` / `sessions.expires_at`, consider a cleanup job. Relevant given these are the exact tables the readiness checklist flags for write-heavy Postgres validation.
11. **[Low]** Align `folios.coverage_gap_details`' migration DDL with its model declaration. Low functional risk today, but prevents future autogenerate confusion.
12. **[Low]** Correct CLAUDE.md's "still open" tracker. The async-commit item is resolved in its general form as of `bb5225f` — narrow the note to the one remaining straggler instead of carrying the old wording forward.

---

## 9. Unverified items

Explicitly out of reach for a static, read-only audit — flagged rather than guessed at.

- Whether `alembic upgrade head` has ever actually succeeded against a genuinely fresh Postgres instance outside of CI's automated job — no local/manual run is documented anywhere, and this audit did not execute the migration itself.
- Whether CI's `backend-postgres` job has historically run green — the workflow config was confirmed to exist and be correctly wired, but run history/logs weren't accessible to this audit. It's possible the 2 Postgres-marked tests have never happened to insert an out-of-range enum value, which would explain why F1/F2 haven't already surfaced as a CI failure.
- "No real user data has been collected yet" (readiness checklist item) — an operational fact outside what a repository can confirm.
- Whether `scheme_aaum`'s fully-dead-code state is a deliberate, already-known deferral or an accidental gap that fell through — `DEFERRED_FEATURES.md` names the NAV job by name but doesn't call out AAUM specifically as further behind than its siblings.
- Whether the `folios.coverage_gap_details` model/migration type mismatch has any actual runtime consequence — inferred harmless from SQLAlchemy's type hierarchy (Postgres `JSONB` subclasses the generic `JSON` type), but not empirically confirmed by running the migration against SQLite.
- The exact commit that introduced the extra 11 `ImportStatus` Python-enum values without a corresponding constraint migration — evidence points to migration 0003's session, but a precise git-blame confirmation wasn't completed.

---

## 10. Final assessment

The engineering discipline behind this migration plan is real, not aspirational — the Alembic chain, the partitioning implementation, the dual-dialect test infrastructure, and the Numeric/Enum/JSON type choices all show careful, documented reasoning, and the project's own delegation log shows deviations being caught and debated rather than waved through. That discipline is exactly what makes the two critical findings here worth taking seriously: they aren't the product of a careless build, they're a specific, narrow blind spot — the test suite's use of `create_all()` instead of a real migration history — that let two otherwise-solid dialect-aware migrations (0001 and 0003) ship with an incomplete second half.

None of the findings in this report require a redesign. The critical items are additive migrations; the high items are a documentation refresh, a well-scoped constraint addition, a small refactor, and a piece of already-planned feature work (ADR-006) whose absence is currently understated rather than unknown. Closing the critical pair before any real Postgres cutover — and fixing the `create_all()` testing gap that hid them — should be treated as the two highest-priority items ahead of everything else in the remediation plan.

---

*Read-only audit. No files, migrations, or database state were modified in the course of this investigation. All findings are sourced from direct file reads and static analysis; items in Section 9 are marked unverified rather than assumed.*
