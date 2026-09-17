# ADR-003: Primary database — AWS RDS for PostgreSQL

Status: Accepted
Date: 2026-07-22
Related: ADR-004 (what goes in S3 instead), ADR-005 (deployment),
`05-docs/how-to/migrate-sqlite-to-postgres.md`, `06-architecture/data-model.md`

## For stakeholders

This is the permanent home for everything the product is actually worth: every user
profile, every household member, every holding, every transaction, every import event,
every computed result. A user uploads a statement once and their portfolio is there
every time they open the app — they never re-upload to simply look at it; they only
upload again to *add* something new. We are using Amazon's managed PostgreSQL service
(RDS) for this. The prototype ran on SQLite, a single local file, which was always
understood as a prototype choice and was deliberately written to be portable to
PostgreSQL from the start. The real decision here was *when* to move: the answer is
before any real user data exists, never after. The cost is a monthly AWS bill from the
first day of deployment and some one-off setup work to configure and secure it.

## Technical detail

### Context

The prototype uses SQLite with `Numeric` column types, deliberately chosen to be
Postgres-portable — an explicit early design decision anticipating exactly this
migration, not an accident. The proposal (AWS RDS + PostgreSQL) is therefore not in
tension with existing work; it is the intended next step.

Stated plainly because this is the permanent home for the product's value: every user
profile, household member, parsed holding, transaction, import event, and computed
analytics result lives here indefinitely from first import onward. Ongoing Data
Addition appends to this store rather than replacing anything.

What actually needed deciding was the **timing and shape** of the migration off SQLite:
at what point SQLite stops being sufficient (single local prototype vs. multi-user,
deployed, needing real backups and durability), and whether anything in the schema —
`Decimal`/`Numeric` handling, the JSON raw-parser-output field from PRD-01 FR-4 —
needs Postgres-specific adjustment.

### Decision drivers

- Real user financial data requires managed backups, point-in-time recovery, and
  durability guarantees that a local file does not provide.
- The schema was already designed to be portable; no redesign is required.
- PRD-01 FR-4 requires persisting full raw parser output as JSON for debugging.
- A 2–3 person team should not be hand-operating a database.

### Options considered

#### Option 1: AWS RDS for PostgreSQL (chosen)
**Advantages:** no schema redesign — `Numeric` translates directly, as anticipated;
managed backups, point-in-time recovery, and durability from day one; native
JSON/JSONB is a clean fit for PRD-01's raw-parser-output requirement, better than
SQLite's more limited JSON handling.
**Disadvantages:** ongoing cost from the first day of deployment, unlike a free
file-based database; one more piece of AWS infrastructure to configure and secure —
VPC placement, credential management, backup retention — before launch.

#### Option 2: Continue with SQLite in production
**Advantages:** free, zero setup, already working.
**Disadvantages:** rejected — fine for a single-developer prototype, not appropriate
once real user financial data and multi-user access are live. No meaningful case for it
beyond local development.

#### Option 3: Self-managed PostgreSQL on EC2
**Advantages:** lower running cost at meaningfully larger scale; full control.
**Disadvantages:** rejected for this team's size — RDS's managed backups, patching, and
failover remove operational burden a 2–3 person team should not carry manually
pre-launch. Revisit only if AWS cost optimisation becomes a priority at scale.

### Decision

Use **AWS RDS for PostgreSQL** as the production database, migrating off the SQLite
prototype once the backend is deployed beyond local development — practically, **before
any real user data is being collected** (before or at MVP launch, not after). SQLite
remains fine for continued local development in the meantime.

### Consequences

**Positive:**
- No schema redesign needed.
- Managed backups, PITR, and durability from the moment real financial data exists.
- Native JSONB suits the raw-parser-output requirement.

**Negative:**
- Ongoing cost from day one of deployment — a real budget line item even at small scale.
- Real pre-launch setup work: VPC placement, credentials management, backup retention.

**Neutral:**
- Connection pooling (PgBouncer or RDS Proxy) becomes relevant once FastAPI's async
  workers talk to Postgres under real load. Not needed at launch scale — a known future
  tuning knob, not a launch blocker.

### Validation

The migration is validated by the checklist and validation steps in
`05-docs/how-to/migrate-sqlite-to-postgres.md`: schema parity diffed against the
schema document, explicit verification that `transactions` and `nav_history` are
genuinely partitioned rather than silently created as plain tables, and the
Postgres-specific test subset passing against RDS itself rather than only against local
Docker Postgres.

### Evidence

- Source document: `08-evidence/documents/ADR-Technical-Stack-Decisions.md` (ADR-003)
- Migration plan: `08-evidence/documents/Migration-Plan-SQLite-to-Postgres.md`
