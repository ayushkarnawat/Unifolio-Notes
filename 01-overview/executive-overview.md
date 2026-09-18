# Executive Overview — Unifolio Documentation Vault

## For stakeholders

This is the working documentation system for Unifolio: the project's
delivery journey, major decisions (including paths that were tried and
abandoned), current architecture, and open risks — built from the same
material the engineering team works from, processed into a form a
non-technical reader can follow.

## Status as of 2026-09-17

Two batches of six are ingested. Batch 1 was the product and architecture
foundation — four product requirement documents, the technical design, the
database schema, the app flow, the design system, and the architecture
decision set. Batch 2a is the first eleven days of the build itself
(2026-08-04 to 2026-08-14): fourteen engineering plans and eleven paired
design specifications.

Together they now exist here as eleven decision records, four investigations,
eight journey stages, an eight-section architecture description, ten
supporting reference and how-to documents, and a risk register carrying
thirty open items.

Four batches remain: the rest of the implementation plans and specs, the
engineering-loop working files, the AWS readiness notes, and the scattered
personal notes.

**What changed in this batch, in one line each:**
- The product is further along than batch 1 suggested — import, onboarding,
  the whole main dashboard, distributor comparison and two analytics
  subsystems are built.
- Nothing can actually log a real user in yet: neither the SMS nor the email
  one-time-code channel sends a real message.
- A Privacy Policy page does not exist and blocks Google sign-in from
  launching.
- Two incompatible versions of the fund-score methodology are now on record
  and need a product decision.

## Where to look

- Current snapshot: `01-overview/current-status.md`
- What's planned next: `01-overview/roadmap.md`
- What Unifolio is and why it's built this way: `06-architecture/goals-and-context.md`
- Major decisions and why: `03-decisions/`
- The delivery narrative: `02-journey/00-index.md`
- What's unresolved: `07-risks-and-debt.md`
- Unfamiliar terms: `06-architecture/glossary.md`
- Investigations — how a specific problem was actually diagnosed: `04-investigations/`
