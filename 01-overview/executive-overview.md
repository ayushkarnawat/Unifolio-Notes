# Executive Overview — Unifolio Documentation Vault

## For stakeholders

This is the working documentation system for Unifolio: the project's
delivery journey, major decisions (including paths that were tried and
abandoned), current architecture, and open risks — built from the same
material the engineering team works from, processed into a form a
non-technical reader can follow.

## Status as of 2026-09-18

Three ingestion passes are complete: batch 1 (the product and architecture
foundation — four product requirement documents, the technical design, the
database schema, the app flow, the design system, and the architecture
decision set), batch 2a (the first eleven days of the build itself,
2026-08-04 to 2026-08-14), and batch 2b (the second half of August,
2026-08-17 to 2026-08-31 — eight engineering plans and sixteen paired design
specifications, continuing the same `Docs/superpowers/{plans,specs}` source
batch 2a began). Nine files from that same folder remain unprocessed, tracked
as batch 2c.

Together they now exist here as fourteen decision records, seven
investigations, fifteen journey stages, an eight-section architecture
description, ten supporting reference and how-to documents, and a risk
register carrying fifty-one open items.

Batch 2c and four further batches remain: the rest of the implementation
plans and specs, the engineering-loop working files, the AWS readiness notes,
and the scattered personal notes.

**What changed in this batch, in one line each:**
- The second half of August produced far more design than build: of eight
  implementation plans, only two were executed in full — and both were for a
  feature that was reversed the same day. Five were never started (R-051).
- The desktop Main Dashboard is still a placeholder stub while the mobile
  dashboard is a mature, built implementation — the product's primary screen,
  on its primary platform, does not exist yet.
- Whether and how Unifolio stores PAN now has five different recorded
  positions across five dates; most recently reaffirmed live but not yet
  backed by written documentation (R-043).
- A marketing brief handed to an external builder on 2026-08-31 claims CAS
  import is "powered by MFCentral" — it is not, and the claim contradicts how
  the product actually ingests statements (R-046).

## Where to look

- Current snapshot: `01-overview/current-status.md`
- What's planned next: `01-overview/roadmap.md`
- What Unifolio is and why it's built this way: `06-architecture/goals-and-context.md`
- Major decisions and why: `03-decisions/`
- The delivery narrative: `02-journey/00-index.md`
- What's unresolved: `07-risks-and-debt.md`
- Unfamiliar terms: `06-architecture/glossary.md`
- Investigations — how a specific problem was actually diagnosed: `04-investigations/`
- Everything designed but not yet built as of 2026-08-31 — ADR-012, ADR-013,
  ADR-014 and R-051, which lists the execution status of every plan in the
  fortnight.
