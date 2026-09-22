# Roadmap

1. Ingest batch 1 — `Docs/PRDs/` → architecture + reference docs
2. Ingest batch 2 — `Docs/superpowers/plans/` + `specs/` → journey + ADRs
3. Ingest batch 3 — root engineering-loop files (`decisions.md`, `log.md`,
   `session.md`, `AGENTS.md`, `CLAUDE.md`) → reconciled against batches 1-2
4. Ingest batch 4 — remaining `Docs/` subfolders
5. Ingest batch 5 — `AWS Readiness/`
6. Ingest batch 6 — `Notes for Unifolio/` and remaining `More .md files/`
7. Ongoing: manual code-repo pulls + `/sync-documentation` as new work happens

**Designed and waiting, as of 2026-08-31.** In the order they were specified:
cadence-based active-SIP detection (ADR-012); analytics PDF export (ADR-013);
portfolio-level distributor comparison; and Phase 2 — direct equity imported
from depository statements, with automatic email ingestion behind it
(ADR-014). None is built. Phase 2's email ingestion is additionally blocked on
the PAN decision (R-043).

**Not on the roadmap and load-bearing:** the desktop Main Dashboard, which is
still a placeholder (R-037).
