# Executive Overview — Unifolio Documentation Vault

## For stakeholders

This is the working documentation system for Unifolio: the project's
delivery journey, major decisions (including paths that were tried and
abandoned), current architecture, and open risks — built from the same
material the engineering team works from, processed into a form a
non-technical reader can follow.

## Status as of 2026-09-22

Four ingestion passes are complete: batch 1 (the product and architecture
foundation), batch 2a (2026-08-04 to 2026-08-14), batch 2b (2026-08-17 to
2026-08-31), and batch 2c (2026-09-02 to 2026-09-16 — six engineering plans
and three paired design specs, closing out the `Docs/superpowers/{plans,specs}`
source folder batches 2a/2b began).

Together they now exist here as seventeen decision records, eight
investigations, twenty journey stages, an eight-section architecture
description, ten supporting reference and how-to documents, and a risk
register carrying fifty-four open items.

Four further batches remain: the engineering-loop working files, the
remaining `Docs/` subfolders, the AWS readiness notes, and the scattered
personal notes.

**What changed in this batch, in one line each:**
- The Analytics precompute rework was designed 2026-09-02 and confirmed
  merged and tested by 2026-09-10 — resolving a risk this vault had
  carried open since batch 2b, that the mechanism behind a loading-state
  decision was undocumented (R-042).
- A Fund Score card redesign was fully designed and planned on 2026-09-11
  but has no execution evidence anywhere in this batch (R-053) — the
  opposite pattern from the analytics work in the same fortnight.
- Preparing a detailed AWS staging runbook, infrastructure was found already
  applied ahead of what the team's own notes described — caught and fixed
  once, but nothing prevents a repeat (R-052).
- This vault itself — its structure, templates, and sync workflow — was
  designed and built the same day, 2026-09-16 (ADR-016), and is recorded
  here like any other piece of delivered work.
- Nothing in this batch bears on the open PAN storage question (R-043); it
  remains exactly where batch 2b left it.

## Where to look

- Current snapshot: `01-overview/current-status.md`
- What's planned next: `01-overview/roadmap.md`
- What Unifolio is and why it's built this way: `06-architecture/goals-and-context.md`
- Major decisions and why: `03-decisions/`
- The delivery narrative: `02-journey/00-index.md`
- What's unresolved: `07-risks-and-debt.md`
- Unfamiliar terms: `06-architecture/glossary.md`
- Investigations — how a specific problem was actually diagnosed: `04-investigations/`
- Everything designed but not yet built as of 2026-09-16 — ADR-012, ADR-013,
  ADR-014, ADR-017 and R-051/R-053, which list the execution status of the
  plans in question.
