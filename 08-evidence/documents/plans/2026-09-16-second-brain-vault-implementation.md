# Second-Brain Documentation Vault — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the vault skeleton, templates, the `sync-documentation` skill, and the operating rules described in the spec — so the vault is ready for the first real ingestion batch, but the batches themselves are not part of this plan (they require reading and judging real content, not mechanical steps).

**Architecture:** Everything lives directly at the vault root (`/mnt/d/Unifolio notes/`) — no nested subfolder, alongside the existing raw folders (`Docs/`, `AWS Readiness/`, `More .md files/`, `Notes for Unifolio/`) which remain in place until consumed batch-by-batch per the spec's migration order, after this plan is done.

**Tech Stack:** Markdown files, a Claude Code project skill (`.claude/skills/sync-documentation/SKILL.md`), Git. No code, no test framework — "testable deliverable" here means verifiable file/directory state (`ls`, `grep`, `git log`) plus one manual smoke test of the skill's classification logic (the one piece of actual branching logic in this plan).

**Spec:** `Docs/superpowers/specs/2026-09-16-second-brain-vault-architecture-design.md`

## Global Constraints

- No source code from the code repo (`D:\Unifolio code`) is ever copied into this vault.
- No write happens without the user seeing a proposed change-set first and approving it.
- No file dropped into `00-inbox/` is ever discarded — every item lands in a structured record, or at minimum an evidence copy plus a pointer.
- Every `ADR-XXX` and every `02-journey/<stage>.md` file has both a `## For stakeholders` and a `## Technical detail` section.
- Folders/files are created only once there is real content for them — except the structural skeleton (`00`-`09`) built in Task 1, which is needed immediately for the workflow to function.
- This vault is its own git repository, separate from `D:\Unifolio code`.

---

### Task 1: Vault skeleton + git

**Files:**
- Create: `.gitignore`
- Create: `00-inbox/from-code-repo/.gitkeep`
- Create: `00-inbox/from-code-repo/processed/.gitkeep`
- Create: `00-inbox/raw/.gitkeep`
- Create: `00-inbox/raw/processed/.gitkeep`
- Create: `08-evidence/conversations/.gitkeep`
- Create: `08-evidence/logs/.gitkeep`
- Create: `08-evidence/test-results/.gitkeep`
- Create: `08-evidence/screenshots/.gitkeep`
- Create: `09-archive/.gitkeep`

**Interfaces:**
- Produces: the directory skeleton every later task writes into (`00-inbox/`, `08-evidence/`, `09-archive/` as empty-but-tracked; `01-overview/` through `07-risks-and-debt.md` get created with real content in Task 3).

- [ ] **Step 1: Initialize git**

  Run:
  ```bash
  cd "/mnt/d/Unifolio notes"
  git init
  ```
  Expected: `Initialized empty Git repository in /mnt/d/Unifolio notes/.git/`

- [ ] **Step 2: Create `.gitignore`**

  ```
  .DS_Store
  Thumbs.db
  .obsidian/
  ```

- [ ] **Step 3: Create the tracked-empty skeleton folders**

  Run:
  ```bash
  cd "/mnt/d/Unifolio notes"
  mkdir -p "00-inbox/from-code-repo/processed" "00-inbox/raw/processed" \
           "08-evidence/conversations" "08-evidence/logs" "08-evidence/test-results" "08-evidence/screenshots" \
           "09-archive"
  touch "00-inbox/from-code-repo/.gitkeep" "00-inbox/from-code-repo/processed/.gitkeep" \
        "00-inbox/raw/.gitkeep" "00-inbox/raw/processed/.gitkeep" \
        "08-evidence/conversations/.gitkeep" "08-evidence/logs/.gitkeep" \
        "08-evidence/test-results/.gitkeep" "08-evidence/screenshots/.gitkeep" \
        "09-archive/.gitkeep"
  ```

- [ ] **Step 4: Verify**

  Run: `find "/mnt/d/Unifolio notes" -maxdepth 3 -iname ".gitkeep" | sort`
  Expected: 9 lines, matching the Files list above.

- [ ] **Step 5: Commit**

  ```bash
  cd "/mnt/d/Unifolio notes"
  git add .gitignore 00-inbox 08-evidence 09-archive
  git commit -m "chore: initialize second-brain vault skeleton"
  ```

---

### Task 2: Record templates

**Files:**
- Create: `templates/adr.md`
- Create: `templates/investigation.md`
- Create: `templates/journey-stage.md`
- Create: `templates/decisions-log-entry.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the exact shape Task 4's `sync-documentation` skill points to when writing `03-decisions/ADR-XXX-*.md`, `04-investigations/INV-XXX-*.md`, `02-journey/<date>-<stage>.md`, and `03-decisions/decisions-log.md` entries.

- [ ] **Step 1: Create `templates/adr.md`**

  ```markdown
  # ADR-XXX: <title>

  Status: Proposed | Accepted | Superseded by ADR-YYY
  Date: YYYY-MM-DD
  Related: <journey stage, investigation, or feature this decision affects>

  ## For stakeholders

  <One paragraph: what we were trying to do, what got in the way, what we
  chose, what it costs/changes, what's done, what's left.>

  ## Technical detail

  ### Context

  ### Decision drivers

  ### Options considered

  #### Option 1: <name>
  Advantages:
  Disadvantages:

  #### Option 2: <name>
  Advantages:
  Disadvantages:

  ### Decision

  ### Consequences

  Positive:
  Negative:

  ### Validation

  ### Evidence

  - Conversation: `08-evidence/conversations/<file>`
  - Commit/log: `08-evidence/logs/<file>`
  ```

- [ ] **Step 2: Create `templates/investigation.md`**

  ```markdown
  # Investigation: <title>

  ## Trigger

  ## Expected behavior

  ## Observed behavior

  ## Hypotheses

  1.
  2.

  ## Experiments

  | Experiment | Expected signal | Actual result | Conclusion |
  |---|---|---|---|
  |  |  |  |  |

  ## Root cause

  ## Resolution

  ## Remaining uncertainty

  ## Related records

  -
  ```

- [ ] **Step 3: Create `templates/journey-stage.md`**

  ```markdown
  # <Stage name>

  ## For stakeholders

  <What this stage was meant to achieve, what happened, in one paragraph.>

  ## Technical detail

  ### Intended outcome

  ### What actually happened

  ### Deviation (if any) — decision or response taken

  ### Result

  ### Related

  - ADR-XXX
  - INV-XXX
  - Evidence: `08-evidence/...`
  ```

- [ ] **Step 4: Create `templates/decisions-log-entry.md`**

  ```markdown
  ## YYYY-MM-DD — <short decision title>

  <What was decided, in 1-3 sentences.> **Why:** <the reason>. <If this
  reverses/supersedes an earlier entry, say so here and leave the earlier
  entry untouched.>
  ```

- [ ] **Step 5: Verify**

  Run: `ls templates/` from `/mnt/d/Unifolio notes`
  Expected: `adr.md  decisions-log-entry.md  investigation.md  journey-stage.md`

- [ ] **Step 6: Commit**

  ```bash
  cd "/mnt/d/Unifolio notes"
  git add templates
  git commit -m "docs: add ADR, investigation, journey-stage, and decisions-log templates"
  ```

---

### Task 3: Core current-state docs, MAP, and vault-level CLAUDE.md

**Files:**
- Create: `01-overview/executive-overview.md`
- Create: `01-overview/current-status.md`
- Create: `01-overview/roadmap.md`
- Create: `02-journey/00-index.md`
- Create: `03-decisions/decisions-log.md`
- Create: `06-architecture/00-index.md`
- Create: `07-risks-and-debt.md`
- Create: `MAP.md`
- Create: `CLAUDE.md`

**Interfaces:**
- Consumes: `templates/decisions-log-entry.md` header convention (Task 2).
- Produces: `MAP.md` as the link target every other doc and the skill's own instructions point back to.

- [ ] **Step 1: Create `01-overview/executive-overview.md`**

  ```markdown
  # Executive Overview — Unifolio Documentation Vault

  ## For stakeholders

  This is the working documentation system for Unifolio: the project's
  delivery journey, major decisions (including paths that were tried and
  abandoned), current architecture, and open risks — built from the same
  material the engineering team works from, processed into a form a
  non-technical reader can follow.

  ## Status as of 2026-09-16

  Vault structure just created. Content has not yet been migrated in — the
  existing raw notes (PRDs, engineering session logs, AWS readiness notes,
  personal working notes) are queued for ingestion in 6 batches, starting
  with the product/architecture foundation (PRDs) and ending with the most
  scattered personal notes. See `02-journey/00-index.md` once the first
  batches land.

  ## Where to look

  - Current snapshot: `01-overview/current-status.md`
  - What's planned next: `01-overview/roadmap.md`
  - Major decisions and why: `03-decisions/`
  - What's unresolved: `07-risks-and-debt.md`
  ```

- [ ] **Step 2: Create `01-overview/current-status.md`**

  ```markdown
  # Current Status

  _Overwritten each update — this is a snapshot, not a history. For
  history, see `02-journey/`._

  **As of 2026-09-16:** Vault skeleton created (folders, templates, the
  `sync-documentation` skill, this file). No content has been ingested
  yet. Next step: run batch 1 (`Docs/PRDs/`) through `/sync-documentation`.
  ```

- [ ] **Step 3: Create `01-overview/roadmap.md`**

  ```markdown
  # Roadmap

  1. Ingest batch 1 — `Docs/PRDs/` → architecture + reference docs
  2. Ingest batch 2 — `Docs/superpowers/plans/` + `specs/` → journey + ADRs
  3. Ingest batch 3 — root engineering-loop files (`decisions.md`, `log.md`,
     `session.md`, `AGENTS.md`, `CLAUDE.md`) → reconciled against batches 1-2
  4. Ingest batch 4 — remaining `Docs/` subfolders
  5. Ingest batch 5 — `AWS Readiness/`
  6. Ingest batch 6 — `Notes for Unifolio/` and remaining `More .md files/`
  7. Ongoing: manual code-repo pulls + `/sync-documentation` as new work happens
  ```

- [ ] **Step 4: Create `02-journey/00-index.md`**

  ```markdown
  # Journey Index

  Ordered list of delivery stages. Each links to a `<date>-<stage>.md`
  file with the full for-stakeholders/technical-detail record.

  _No stages recorded yet — populated as batches 1-2 are ingested._

  ```mermaid
  flowchart LR
      A[A — Initial state] --> B[Planned path]
      B --> C{Blocker or discovery?}
      C -->|No| D[B — Final state]
      C -->|Yes| E[Decision]
      E --> F[Alternative implemented]
      F --> D
  ```
  ```

- [ ] **Step 5: Create `03-decisions/decisions-log.md`**

  ```markdown
  # Decisions Log

  > Append-only, dated log of smaller decisions. Distinct from `ADR-XXX`
  > files, which are reserved for major decisions with full
  > alternatives-considered writeups — this file covers everything else,
  > and links to an ADR by reference rather than restating it once a
  > decision graduates to one. Never trim or rewrite past entries — append
  > corrections/reversals as new dated entries instead.

  _No entries yet — populated as batches are ingested._
  ```

- [ ] **Step 6: Create `06-architecture/00-index.md`**

  ```markdown
  # Architecture Index

  Sections are created only once there's real content for them — this
  list grows as batches are ingested, it does not start pre-filled.

  _No sections yet._

  Likely sections once populated (per the design spec): goals-and-context,
  building-blocks, runtime-and-data-flow, deployment,
  quality-and-constraints, glossary.
  ```

- [ ] **Step 7: Create `07-risks-and-debt.md`**

  ```markdown
  # Risks and Technical Debt

  > Single running file until it outgrows a comfortable single-file size,
  > then splits into per-risk files. Never trim past entries — mark
  > resolved, don't delete.

  _No entries yet — populated as batches are ingested._
  ```

- [ ] **Step 8: Create `MAP.md`**

  ```markdown
  # Map

  This file is the index — what's where, and what to read first.

  ## Start here

  - [Executive overview](01-overview/executive-overview.md) — front door for anyone new to this project
  - [Current status](01-overview/current-status.md) — living snapshot, overwritten each update
  - [Roadmap](01-overview/roadmap.md)
  - [Journey index](02-journey/00-index.md) — the A→B→C→D delivery narrative

  ## Records

  - [Decisions](03-decisions/) — `decisions-log.md` for small calls, `ADR-XXX` files for major ones with alternatives considered
  - [Investigations](04-investigations/) — troubleshooting and root-cause digs, including incidents
  - [Risks and technical debt](07-risks-and-debt.md)

  ## Reference

  - [Architecture](06-architecture/00-index.md)
  - [Docs](05-docs/) — tutorials, how-to guides, reference, explanation (Diátaxis)

  ## Raw material

  - [Inbox](00-inbox/) — unprocessed raw material; run `/sync-documentation` to process it
  - [Evidence](08-evidence/) — conversation exports, logs, screenshots, test output cited by records above

  ## How this vault works

  ```mermaid
  flowchart LR
      A["Raw material: code-repo pull\nor pasted conversation"] --> B[00-inbox]
      B -->|"/sync-documentation"| C{Classify}
      C --> D[02-journey]
      C --> E[03-decisions]
      C --> F[04-investigations]
      C --> G["05-docs / 06-architecture"]
      C --> H[07-risks-and-debt]
      D --> I["01-overview\nstakeholder summary"]
      E --> I
      F --> I
      G --> I
      H --> I
      C --> J[08-evidence]
  ```

  Nothing here is edited directly for routine updates — raw material goes
  into `00-inbox/`, gets processed by `/sync-documentation`, and every
  write is approved before it lands.
  ```

- [ ] **Step 9: Create `CLAUDE.md`**

  ```markdown
  # CLAUDE.md — Unifolio Second-Brain Vault

  This directory is a documentation vault, not the Unifolio code
  repository (that's `D:\Unifolio code`, untouched by anything here).
  Read `MAP.md` first, every session.

  ## What this vault is for

  A second-brain-plus-documentation system: the delivery journey
  (including detours and rejected alternatives), decision records,
  investigations, current architecture/reference docs, and a
  stakeholder-facing overview — built incrementally from raw material
  (pulled code-repo docs, pasted Claude conversations, notes) rather than
  rewritten from scratch each time.

  ## Required behavior

  - Read `MAP.md` before making any change.
  - Treat everything under `00-inbox/` as unprocessed evidence, not fact —
    use the `sync-documentation` skill to process it, don't hand-edit
    structured records to match a raw file.
  - Never overwrite or delete a past `decisions-log.md` entry, ADR, or
    investigation. Mark superseded, append corrections as new dated
    entries.
  - Every substantive claim in a decision, journey entry, or investigation
    needs an evidence link.
  - Every ADR and journey entry needs both a `## For stakeholders` and a
    `## Technical detail` section.
  - Never treat an unverified statement from a raw conversation as settled
    fact — flag it as a hypothesis if it isn't backed by evidence.
  - Never publish a change to `01-overview/` (or any file) without showing
    the proposed change-set first and getting approval.
  - No source code, ever, from the code repo — documentation and evidence
    only.
  - No file from `00-inbox/` is ever discarded — everything lands in a
    structured record or, at minimum, an evidence copy with a pointer.
  ```

- [ ] **Step 10: Verify**

  Run: `find "/mnt/d/Unifolio notes" -maxdepth 2 -newer templates -iname "*.md" | sort`
  Expected: the 9 files created above are listed.

- [ ] **Step 11: Commit**

  ```bash
  cd "/mnt/d/Unifolio notes"
  git add 01-overview 02-journey 03-decisions 06-architecture 07-risks-and-debt.md MAP.md CLAUDE.md
  git commit -m "docs: add current-state docs, vault map, and vault-level CLAUDE.md"
  ```

---

### Task 4: `sync-documentation` skill + smoke test

**Files:**
- Create: `.claude/skills/sync-documentation/SKILL.md`
- Create (temporary, deleted in Step 4): `00-inbox/raw/_smoketest-decision.md`

**Interfaces:**
- Consumes: `templates/*.md` (Task 2), the classification table and rules defined here, `MAP.md` (Task 3) as the doc it must never bypass.
- Produces: the `/sync-documentation` invocation the how-to doc (Task 5) instructs the user to run.

- [ ] **Step 1: Create `.claude/skills/sync-documentation/SKILL.md`**

  ```markdown
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
     - Files directly in `00-inbox/raw/` not yet moved under
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
     | A stage of work completed, blocked, or redirected | New or updated `02-journey/<date>-<stage>.md`, plus an updated line in `02-journey/00-index.md` |
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

  9. **Commit** the result with a message summarizing the batch (e.g.
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
  ```

- [ ] **Step 2: Write a smoke-test fixture**

  This is a synthetic, throwaway file to prove the classification logic
  above actually routes something correctly — not real vault content, so
  it's fine to delete it once verified (unlike real inbox material, which
  is never discarded).

  Create `00-inbox/raw/_smoketest-decision.md`:
  ```markdown
  # Smoke test

  We considered using Postgres full-text search for the fund-name lookup,
  but switched to a precomputed trigram index instead because full-text
  search returned poor results for partial fund-name matches during
  manual testing. This is a final decision, not up for revisiting without
  new evidence.
  ```

- [ ] **Step 3: Run the smoke test**

  Invoke the `sync-documentation` skill (as Claude, following the
  procedure above) against just this one file. Confirm:
  - It reads the file in full (not just the filename).
  - It classifies this as a **small decision with a stated alternative**
    → proposes a `decisions-log.md` entry (not an ADR, since there's only
    one alternative mentioned and no multi-option trade-off table — if the
    skill instead proposes an ADR, that's also acceptable as long as it's
    consistent with the classification table's judgment call, but it must
    justify which row it used).
  - It shows a change-set and stops for approval rather than writing
    immediately.

  Expected: a change-set is printed proposing a `decisions-log.md` entry
  (or ADR) referencing the smoke-test file, and nothing is written to
  `03-decisions/` until approved.

- [ ] **Step 4: Clean up the fixture**

  Do not approve the proposed write. Delete the fixture instead:
  ```bash
  rm "/mnt/d/Unifolio notes/00-inbox/raw/_smoketest-decision.md"
  ```
  Verify: `ls "/mnt/d/Unifolio notes/00-inbox/raw/"` shows only `processed/` and `.gitkeep`.

- [ ] **Step 5: Commit**

  ```bash
  cd "/mnt/d/Unifolio notes"
  git add .claude/skills/sync-documentation/SKILL.md
  git commit -m "feat: add sync-documentation skill"
  ```

---

### Task 5: How-to doc for the manual pull procedure

**Files:**
- Create: `05-docs/how-to/pull-and-sync-from-code-repo.md`

**Interfaces:**
- Consumes: the `/sync-documentation` skill (Task 4) it instructs the user to run.
- Produces: the first real file under `05-docs/`, proving the Diátaxis split is in use from day one.

- [ ] **Step 1: Create `05-docs/how-to/pull-and-sync-from-code-repo.md`**

  ```markdown
  # How to pull code-repo docs and sync them into this vault

  Goal: bring new content from the Unifolio code repo's docs into this
  vault, and turn it into structured records.

  ## Prerequisites

  - The code repo is at `D:\Unifolio code`.
  - This vault has the `sync-documentation` skill available
    (`.claude/skills/sync-documentation/`).

  ## Steps

  1. Open File Explorer, go to `D:\Unifolio code`.
  2. In this vault, create a new folder:
     `00-inbox/from-code-repo/<today's date, YYYY-MM-DD>/`. Always a fresh
     dated folder — never overwrite a previous pull.
  3. Copy these into that new folder:
     - `decisions.md`
     - `log.md`
     - `session.md`
     - `AGENTS.md`
     - `CLAUDE.md`
     - the entire `Docs\` folder

     Nothing else — no source code, no build artifacts.
  4. Open this vault in Claude Code.
  5. Run `/sync-documentation`.
  6. Review the proposed change-set (new/updated decisions, journey
     entries, architecture updates, stakeholder summary changes, anything
     flagged as unclassified or contradictory).
  7. Approve, edit, or answer its questions.
  8. It writes the changes and moves the dated folder from
     `00-inbox/from-code-repo/<date>/` to
     `00-inbox/from-code-repo/processed/<date>/` — the pulled files stay
     there as evidence, they are not deleted.

  ## For pasted Claude conversations, meeting notes, or screenshots (not
  from the code repo)

  Same idea, simpler: drop the file(s) directly into `00-inbox/raw/`, then
  run `/sync-documentation`.
  ```

- [ ] **Step 2: Verify**

  Run: `cat "05-docs/how-to/pull-and-sync-from-code-repo.md" | head -5` from `/mnt/d/Unifolio notes`
  Expected: shows the `# How to pull code-repo docs...` heading.

- [ ] **Step 3: Commit**

  ```bash
  cd "/mnt/d/Unifolio notes"
  git add 05-docs
  git commit -m "docs: add how-to guide for pulling and syncing code-repo docs"
  ```

---

## After this plan

The vault is ready but empty of real content. Next (not part of this
plan, since it requires reading and judging ~200 real files rather than
mechanical steps): run batch 1 (`Docs/PRDs/` → `00-inbox/raw/`, then
`/sync-documentation`) per `01-overview/roadmap.md`, and continue through
batches 2-6.
