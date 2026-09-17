# Current Status

_Overwritten each update — this is a snapshot, not a history. For
history, see `02-journey/`._

**As of 2026-09-16:** Batch 1 ingested — the product and architecture foundation. The
vault now holds the six stack decisions (ADR-001 to ADR-006), a seven-section
architecture description, reference docs for the schema, API surface, external data
sources, design tokens and screen flows, the SQLite-to-Postgres migration runbook, and
one journey stage covering 2026-07-22 to 2026-09-02.

**Where the product stands, per that material:** the specification set is build-ready and
implementation is underway — the Import Review UI, the ARN lookup, and the analytics
backend are described as built, with three external data integrations live-verified on
2026-08-10. The database still runs on SQLite; the move to AWS RDS PostgreSQL is
specified, has a runbook, and has not been executed. It must happen before the first real
user signs up.

**The two things most worth attention:** the parse-accuracy targets for the core import
feature have no test fixtures behind them yet (R-009), and there is a newly resolved
direction on whether a user's PAN is stored — Unifolio will store it, encrypted at rest,
per [ADR-007](../03-decisions/ADR-007-pan-storage-and-encryption.md), confirmed
2026-09-16 but not yet implemented. Both are in
[`07-risks-and-debt.md`](../07-risks-and-debt.md), along with twelve other open items.

**Next:** batch 2 — `Docs/superpowers/plans/` and `specs/`, which should supply the
implementation journey these specifications only reference.
