# Roadmap

1. Ingest batch 1 — `Docs/PRDs/` → architecture + reference docs (done)
2. Ingest batch 2 — `Docs/superpowers/plans/` + `specs/` → journey + ADRs (done)
3. Ingest batch 3 — root engineering-loop files (`decisions.md`, `log.md`,
   `session.md`, `AGENTS.md`, `CLAUDE.md`, `backend.md`, `database.md`,
   `PRODUCT.md`, `README.md`, `DEFERRED_FEATURES.md`,
   `CAS-IMPORT-UPDATE-PLAN.md`) → reconciled against batches 1-2 (done,
   2026-09-22)
4. Ingest batch 4 — remaining `Docs/` subfolders
5. Ingest batch 5 — `AWS Readiness/` (its `aws-golive-readiness-report.md` is
   already referenced second-hand by this vault — see R-054 — and should be
   prioritized in this batch)
6. Ingest batch 6 — `Notes for Unifolio/` and remaining `More .md files/`
7. Ongoing: manual code-repo pulls + `/sync-documentation` as new work happens

**Built since, confirmed as of batch 3 (2026-09-22).** Three of the four items
this roadmap previously listed as "designed and waiting, as of 2026-08-31" are
now confirmed executed: cadence-based active-SIP detection (ADR-012, built
2026-08-19); analytics PDF export (ADR-013, merged `ed149bf`); and
portfolio-level distributor comparison (both through the mandatory
adversarial-review gate). The fourth, Phase 2 direct-equity/demat import
(ADR-014), remains unconfirmed by any batch-3 source material — still
designed and waiting, still additionally blocked on the PAN decision (R-043)
for its email-ingestion half. See the addenda on ADR-012/ADR-013 and the
2026-08-18/2026-08-20 journey entries.

**Built since, confirmed 2026-09-10.** The Analytics precompute architecture
(ADR-015) — designed 2026-09-02, merged to `feat/enhanced-ui` the same week.
This was a separate thread from the four items above; it replaced
live-compute-on-read for Analytics.

**Built since, confirmed as of batch 3 (2026-09-22).** The Fund Score card
redesign (ADR-017), designed 2026-09-11, was fully executed the following day
— all 9 tasks, both suites passing, mandatory review closed clean (R-053
resolved).

**New this batch: the CAS import lifecycle was rebuilt** (11-state machine,
coverage-gap detection, opening-balance resolution, CAMS mailback) — built by
a separate contributor, merged in via branch reconciliation on 2026-08-14,
passing its full test suite but still missing its mandatory independent
review pass as of this batch's material (ADR-018, R-004 update).

**New this batch: real AWS infrastructure now exists.** An AWS account,
`unifolio.in` cut over to Route 53 (2026-09-07), and Terraform Phases 1-3
applied to a real network/database/container registry/service (2026-09-09) —
this roadmap's batches 4-6 are no longer purely aspirational against an
account that didn't exist yet.

**Not on the roadmap and load-bearing:** the desktop Main Dashboard, which is
still a placeholder (R-037). Phone-OTP's silent-account-creation gap for
unrecognized numbers (R-056) and the SIP tab switcher's low-severity ARIA gap
(R-055) are deliberately deferred, not roadmap items.
