# Batch 7 triage note — `Docs/` leftover source copies (2026-09-26)

## What this is

This vault's root previously had a top-level `Docs/` folder alongside
`00-inbox/`, `08-evidence/`, etc. — a leftover from earlier ingestion
batches (1, 2, 4a-4e), which staged material by *copying* it into
`00-inbox/raw/` rather than moving it, leaving the originals sitting in
`Docs/` untouched and untracked even after their content was fully
ingested elsewhere in the vault.

58 files remained in `Docs/` as of 2026-09-26. Every one was checked
individually before this archival — none were assumed duplicate by
name alone.

## Method

For each of the 58 files, searched `00-inbox/raw/processed/` and
`08-evidence/documents/` for a file of the same basename, then ran a
byte-for-byte `diff` against any match (not just a filename check).

## Result

- **56 of 58 — byte-identical** to an already-ingested copy. Confirmed
  duplicates, no new content.
- **2 of 58 — textually differ, but both are strictly older,
  pre-resolution drafts**, fully superseded by the ingested copy:
  - `PRD-03-Main-Dashboard.md` — this copy is `version: "1.0"`, no
    changelog. The ingested copy (`08-evidence/documents/PRD-03-Main-Dashboard.md`)
    is `version: "1.3"` with an explicit changelog (entries 1.1-1.3,
    all dated 2026-07-22) showing this exact draft's open items were
    later resolved: distributor comparison (FR-11) unblocked via
    AMFI's public ARN-lookup tool (FR-11a-c added), an "Add data"
    entry point added (FR-10a/US-9), and the family-default-landing
    open question resolved via the App Flow document. Every open
    item in this older draft is a closed item in the ingested copy —
    no information here that isn't already captured, and more
    current, in the vault.
  - `PRD-04-MF-Analytics-Dashboard.md` — same pattern. This copy is
    `version: "1.0"`; the ingested copy is `version: "1.1"`, already
    resolving this draft's open scorer-weighting and index-mapping
    questions (AUM-weighted category averaging, confirmed via AMFI's
    public AAUM disclosures; the Nifty 250/150 index mapping
    confirmed) — content already reflected in `ADR-010` (fund scorer
    composite formula).
- **Secrets check**: `grep -rlE 'AKIA[0-9A-Z]{16}|vtxAy'` across the
  full `Docs/` tree before this archival — no matches.

## Disposition

No new ADR, investigation, journey entry, or risk was drafted from
this batch — there was nothing in it not already reflected, and in
two cases already superseded, in existing vault records. This folder
exists solely to satisfy the vault's "nothing is ever discarded"
principle for the 58 source files, now that the redundant top-level
`Docs/` folder has been removed from the vault root.
