# Executive Overview — Unifolio Documentation Vault

## For stakeholders

This is the working documentation system for Unifolio: the project's
delivery journey, major decisions (including paths that were tried and
abandoned), current architecture, and open risks — built from the same
material the engineering team works from, processed into a form a
non-technical reader can follow.

## Status as of 2026-09-22

Five ingestion passes are complete: batch 1 (the product and architecture
foundation), batch 2a (2026-08-04 to 2026-08-14), batch 2b (2026-08-17 to
2026-08-31), batch 2c (2026-09-02 to 2026-09-16 — six engineering plans and
three paired design specs, closing out the `Docs/superpowers/{plans,specs}`
source folder batches 2a/2b began), and batch 3 (the code repo's own root
engineering-loop working files — `decisions.md`, `log.md`, `session.md`,
`AGENTS.md`, `CLAUDE.md`, `backend.md`, `database.md`, `PRODUCT.md`,
`README.md`, `DEFERRED_FEATURES.md`, `CAS-IMPORT-UPDATE-PLAN.md`).

Together they now exist here as eighteen decision records, ten
investigations, twenty-five journey stages, an eight-section architecture
description, ten supporting reference and how-to documents, and a risk
register carrying fifty-six items.

Three further batches remain: the remaining `Docs/` subfolders, the AWS
readiness notes, and the scattered personal notes.

**What changed in this batch, in one line each:**
- Three of the six plans batch 2b/2c found unexecuted are now directly
  corroborated as built: the SIP cadence redesign, the analytics PDF
  export, and the portfolio-level distributor comparison. The other three
  (an auth-panel verification task, both Phase 2 demat-import plans) remain
  uncorroborated — R-051 is updated, not closed.
- The Fund Score card redesign (ADR-017), previously "designed and planned,
  no execution evidence," is now confirmed fully executed the very next day
  (R-053 resolved).
- Real AWS infrastructure now exists: an account, a domain cut over to
  Route 53, and Terraform Phases 1-3 actually applied to a live network,
  database, and container service — this vault's infrastructure
  description is no longer describing only authored, unapplied Terraform.
- A real AWS IAM access key was briefly exposed in plaintext and rotated
  before misuse; handled, root-caused, and closed the same session
  (INV-010). No literal credential value appears anywhere in this vault.
- A second, independent branch — a CAS import lifecycle rebuild (ADR-018),
  a new UI foundation, and the fund Scorer's backend — was found and merged
  the same day as the already-known 2026-08-14 multi-method-auth work. It
  passes its tests but is still missing its mandatory independent review
  pass, recorded as an open gap rather than assumed clean.
- Two items are on record as explicitly deferred by product-owner decision,
  not oversights: phone-OTP login silently creating a new account for an
  unrecognized number (R-056), and a low-severity ARIA gap on the SIP tab
  switcher (R-055).

## Where to look

- Current snapshot: `01-overview/current-status.md`
- What's planned next: `01-overview/roadmap.md`
- What Unifolio is and why it's built this way: `06-architecture/goals-and-context.md`
- Major decisions and why: `03-decisions/`
- The delivery narrative: `02-journey/00-index.md`
- What's unresolved: `07-risks-and-debt.md`
- Unfamiliar terms: `06-architecture/glossary.md`
- Investigations — how a specific problem was actually diagnosed: `04-investigations/`
- Everything still designed but not yet built as of 2026-09-22 — ADR-014
  (Phase 2 demat import) and R-051's remaining three uncorroborated plans,
  which list the execution status of the plans in question.
