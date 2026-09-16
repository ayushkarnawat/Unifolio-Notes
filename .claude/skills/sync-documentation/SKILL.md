---
name: sync-documentation
description: Use when the user asks to sync, ingest, or process new raw material sitting in 00-inbox/ (pulled code-repo docs, pasted Claude conversations, meeting notes, screenshots) into this vault's structured decisions, investigations, journey entries, and current-state docs. Triggers on "/sync-documentation", "sync the docs", "process the inbox", "run the ingestion", "sync documentation".
---

# Sync Documentation

Turns raw material sitting in `00-inbox/` into this vault's structured
records — decisions, investigations, journey entries,
architecture/reference updates, stakeholder summary updates — through a
propose-then-approve loop. Never writes without approval. Never discards
a source file.

## Procedure

1. **Scan for unprocessed material.**
   - `00-inbox/from-code-repo/<date>/` folders not yet moved under
     `00-inbox/from-code-repo/processed/`.
   - Files and folders under `00-inbox/raw/` (recursively — batches may
     be nested folder trees, not just loose files) not yet moved under
     `00-inbox/raw/processed/`.
   - If nothing unprocessed, say so and stop.
   - If more than ~15-20 files are unprocessed at once, tell the user
     this is large and ask whether to process all of it or just the
     next logical batch — don't silently chew through everything in one
     shot.

2. **Read every unprocessed file in full.** Do not classify from
   filenames alone.

3. **Extract, per file:** objective/topic, facts established, decisions
   made, alternatives rejected and why, experiments/investigations and
   their results, open questions, files/systems referenced, evidence
   worth preserving.

4. **Compare against existing vault content** (`01-overview/`,
   `02-journey/`, `03-decisions/`, `04-investigations/`, `05-docs/`,
   `06-architecture/`, `07-risks-and-debt.md`). For each extracted item,
   note whether it's new, a duplicate/near-duplicate of something already
   in the vault, or a contradiction of something already there.

5. **Classify each item to a destination:**

   | Extracted item | Destination |
   |---|---|
   | Major decision with real alternatives considered | New or updated `03-decisions/ADR-XXX-<slug>.md` |
   | Small decision, no real alternatives weighed | Appended dated entry in `03-decisions/decisions-log.md` |
   | A stage of work completed, blocked, or redirected | New or updated `02-journey/<date>-<stage>.md`, plus an updated line AND an updated/extended flowchart node in `02-journey/00-index.md` |
   | Troubleshooting / root-cause digging (including incidents) | New or updated `04-investigations/INV-XXX-<slug>.md` |
   | Current system behavior, component, or data flow | `06-architecture/<section>.md` (create the section file only if it doesn't exist) |
   | Step-by-step procedure someone must repeat | `05-docs/how-to/<slug>.md` |
   | Learning-oriented walkthrough | `05-docs/tutorials/<slug>.md` |
   | Factual reference (schema, API surface, field list) | `05-docs/reference/<slug>.md` |
   | "Why does it work this way" explanation | `05-docs/explanation/<slug>.md` |
   | Known unresolved problem, deferred item, or debt | `07-risks-and-debt.md` |
   | Stakeholder-visible outcome or status change | `01-overview/current-status.md` (overwrite) and/or `01-overview/executive-overview.md` |
   | Doesn't cleanly fit any of the above | A one-line pointer in `08-evidence/`, next to the copied source, plus a flag in the change-set — never silently dropped |
   | Raw conversation, log, screenshot, test output cited as support | Copied into the matching `08-evidence/` subfolder, linked from whatever record cites it |

   Near-duplicate content already in the vault: link/merge into the
   existing record instead of creating a second one — note this as a
   merge in the change-set, don't file it twice.

6. **Write ADRs and journey entries with both required sections** —
   `## For stakeholders` (one paragraph, plain English) and
   `## Technical detail` (full context/options/consequences/evidence).
   Use `templates/adr.md`, `templates/investigation.md`,
   `templates/journey-stage.md`, `templates/decisions-log-entry.md` as
   the exact shape.

7. **Present the change-set before writing anything:**
   ```
   Processed: <N files/folders>

   Proposed:
   - Create ADR-00X: <title>
   - Create journey entry: <stage>
   - Update 01-overview/current-status.md: <what changes>
   - Merge into existing INV-00X instead of new record: <why>

   Unclassified (need your call):
   - <file>: doesn't fit an existing bucket — file as evidence-only, or
     is it something I'm missing?

   Contradictions found:
   - <file> claims X, but <existing record> says Y — which is current?
   ```
   Wait for explicit approval, edits, or answers before writing
   anything.

8. **On approval:** write the files, copy cited evidence into
   `08-evidence/`, then mark sources processed — move the processed
   `00-inbox/from-code-repo/<date>/` folder (or individual
   `00-inbox/raw/` files) into the sibling `processed/` folder,
   preserving relative paths. Never delete originals.

9. **Commit** only the files touched by the approved change-set plus the
   moved inbox sources — never `git add -A` or a blanket `git add .`,
   which would sweep unrelated unprocessed inbox material into this
   batch's commit. Use a message summarizing the batch (e.g.
   `sync: ingest Docs/PRDs batch — ADR-001, ADR-002,
   architecture goals+building-blocks`).

## Rules

- Never publish a stakeholder-facing change without showing the
  change-set first.
- Never rewrite or delete a past `decisions-log.md` entry, ADR, or
  investigation — supersede with `Status: Superseded by ADR-YYY`, append
  corrections as new dated entries.
- Never copy source code from the code repo — docs and Markdown/PDF/text
  only.
- Never leave a source file unprocessed-but-silently-ignored — if it's
  not going into a structured record, it still gets an evidence copy and
  a pointer.
- If unsure whether something is a verified fact or a hypothesis/guess
  from a conversation, say so explicitly in the change-set rather than
  writing it into a record as settled fact.
