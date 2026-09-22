# Second-Brain Documentation Vault — Architecture Design

Status: Approved
Date: 2026-09-16
Owner: Ayush

## Context and problem

This directory ("Unifolio notes") has accumulated as an unversioned, ad-hoc
collection of raw notes, copied code-repo docs, and abandoned Obsidian
config — `AWS Readiness/`, `Docs/` (PRDs, CAS Parsers, Competitor Analysis,
superpowers plans+specs copied from the code repo, etc.), `More .md files/`,
`Notes for Unifolio/`. There is no structure, no versioning, and no way to
tell current truth from superseded thinking.

Separately, the actual Unifolio code repo (`D:\Unifolio code`) already runs
a working engineering-memory loop — `decisions.md`, `log.md`, `session.md`,
`AGENTS.md`/`CLAUDE.md`, and `Docs/superpowers/plans/` + `specs/` populated
by Claude Code's own brainstorming/writing-plans workflow. That loop works
and is not being touched.

The goal: turn this vault into a structured second brain that (a) captures
the full A → B delivery journey including detours and rejected alternatives,
(b) serves both engineers/QA and a non-technical, experienced investor from
the same records, (c) updates incrementally as new raw material arrives
rather than being rebuilt from scratch each time, and (d) requires no app
beyond a text editor + Git — no Obsidian, no Notion.

## Goals

- One append-only historical record (decisions, investigations, journey) that is never silently rewritten.
- One continuously-updated current-state layer (architecture, status, risks) that always reflects what's true now.
- Every substantive claim traceable to evidence (a conversation, a commit, a test, a log).
- A single recurring workflow — drop raw material in, run one command, approve a proposed change-set — instead of re-deriving the documentation prompt each time.
- Readable by two audiences from the same files: a plain-English section for stakeholders, technical detail below it for engineers/QA.
- Kept separate from the code repo; the code repo is a read-only evidence source, pulled in manually.

## Non-goals

- No arc42-style mandatory section set filled in ahead of need.
- No multi-prefix ID taxonomy (FEAT/INC/RISK/REL) — start with `ADR-XXX` and `INV-XXX` only.
- No automatic/hook-triggered ingestion from the code repo — pulls are manual, user-initiated.
- No PDF/HTML/Notion export in this phase — plain Markdown, viewed in VS Code/GitHub.
- No new application — Markdown + Git + Claude Code only.

## Vault structure

```
Unifolio-Second-Brain/
├── MAP.md                        — index: what's where, current-state doc links, vault diagram
├── 00-inbox/
│   ├── from-code-repo/           — manually pulled code-repo docs, one dated subfolder per pull
│   │   └── processed/            — pulls already ingested, kept (not deleted) for evidence
│   └── raw/                      — pasted Claude sessions, meeting notes, screenshots, and the
│                                    initial one-time dump of every pre-existing file in this vault
├── 01-overview/
│   ├── executive-overview.md     — stakeholder front door: starting state, target, current
│   │                                status, major decisions/deviations, remaining risk
│   ├── current-status.md         — living snapshot, overwritten each update
│   └── roadmap.md
├── 02-journey/
│   ├── 00-index.md               — ordered list of stages, one line each, links out
│   └── <date>-<stage-name>.md    — one file per stage/phase (mirrors the code repo's
│                                    Docs/superpowers/plans/ one-file-per-phase convention)
├── 03-decisions/
│   ├── decisions-log.md          — lightweight append-only log for small decisions
│   │                                (mirrors the code repo's decisions.md pattern)
│   └── ADR-001-<slug>.md ...     — one file per major decision, full alternatives-considered
├── 04-investigations/
│   └── INV-001-<slug>.md ...     — one file per investigation (covers incidents too)
├── 05-docs/                      — Diátaxis; subfolders created only once a doc of that kind exists
│   ├── tutorials/
│   ├── how-to/
│   ├── reference/
│   └── explanation/
├── 06-architecture/
│   ├── 00-index.md               — lists which sections exist
│   └── <section>.md              — goals-and-context, building-blocks, runtime-and-data-flow,
│                                    deployment, quality-and-constraints, glossary — created
│                                    one at a time, only when there's real content
├── 07-risks-and-debt.md          — single running file; splits into per-risk files only if it
│                                    outgrows a single-file size
├── 08-evidence/
│   ├── conversations/
│   ├── logs/
│   ├── test-results/
│   └── screenshots/
└── 09-archive/                   — completed/retired sub-projects only; superseded ADRs/
                                     investigations stay where they are with a status flag,
                                     never moved here
```

## Two reading levels, one document

Every ADR and every journey stage file carries two labeled sections instead
of two parallel documents:

```markdown
## For stakeholders
One paragraph: what we were trying to do, what got in the way, what we
chose, what it costs/changes, what's done, what's left.

## Technical detail
Context, decision drivers, options considered (with trade-offs), decision,
consequences, validation, evidence links.
```

This keeps business truth and technical truth from drifting apart without
maintaining duplicate documents.

## Templates

**ADR** (`03-decisions/ADR-XXX-<slug>.md`):

```markdown
# ADR-XXX: <title>

Status: Proposed | Accepted | Superseded by ADR-YYY
Date: YYYY-MM-DD
Related: <journey stage, investigation, feature>

## For stakeholders
<one paragraph>

## Technical detail

### Context
### Decision drivers
### Options considered
(each: description, advantages, disadvantages)
### Decision
### Consequences
(positive / negative)
### Validation
### Evidence
- Conversation: <link into 08-evidence/conversations/>
- Commit/log: <link>
```

**Investigation** (`04-investigations/INV-XXX-<slug>.md`):

```markdown
# Investigation: <title>

## Trigger
## Expected behavior
## Observed behavior
## Hypotheses
## Experiments
| Experiment | Expected signal | Actual result | Conclusion |
## Root cause
## Resolution
## Remaining uncertainty
## Related records
```

**Journey stage** (`02-journey/<date>-<stage>.md`):

```markdown
# <Stage name>

## For stakeholders
<what this stage was meant to achieve, what happened, in one paragraph>

## Technical detail
### Intended outcome
### What actually happened
### Deviation (if any) — decision or response taken
### Result
### Related
- ADR-XXX, INV-XXX, evidence links
```

Small decisions that don't warrant a full ADR get one dated entry appended
to `decisions-log.md` (never trimmed or rewritten), same convention as the
code repo's `decisions.md`.

## Ingestion workflow

Two raw-material sources, same downstream handling:

1. **Code-repo pull (manual, user-initiated):**
   - Copy `decisions.md`, `log.md`, `session.md`, `AGENTS.md`, `CLAUDE.md`,
     and the entire `Docs/` folder from `D:\Unifolio code` into a new dated
     folder: `00-inbox/from-code-repo/<YYYY-MM-DD>/`. Never overwrite a
     previous pull — always a fresh dated folder.
   - No source code, no build artifacts, ever copied in.

2. **Everything else (raw Claude sessions, meeting notes, screenshots, and
   — for the one-time initial migration — every pre-existing file already
   in this vault: `AWS Readiness/`, the current `Docs/`, `More .md files/`,
   `Notes for Unifolio/`, all of it):** dropped into `00-inbox/raw/`.

Then, run `/sync-documentation` (a Claude Code skill, built as part of this
project):

1. Scan `00-inbox/from-code-repo/*` (unprocessed dated folders) and
   `00-inbox/raw/*` (unprocessed files).
2. Extract facts, decisions, alternatives rejected, experiments, results,
   open questions, evidence references from each item.
3. Compare against existing vault content; detect contradictions with
   current documentation.
4. Propose a change-set: new/updated ADRs, journey stage entries,
   investigations, architecture/current-status updates, stakeholder-facing
   changes — each tagged with its supporting evidence.
5. Show the change-set to the user for approval before writing anything.
6. On approval: write the changes, copy/link cited raw material into
   `08-evidence/`, and mark the source inbox item processed (move
   code-repo pulls to `00-inbox/from-code-repo/processed/`; raw items get
   a processed marker) — never delete the original raw material.
7. Flag contradictions (e.g., a conversation claims something is resolved
   but no passing evidence exists) for explicit user review rather than
   silently picking a side.

Nothing publishes automatically; every write is approved. **No file is ever
discarded or skipped as "not worth keeping."** Every source item must land
somewhere traceable — a decision, an investigation, a journey entry, an
architecture/reference doc, or, if nothing else fits, a one-line pointer
plus the original in `08-evidence/`. Near-duplicate content (e.g. the same
file copied into two folders) may be merged/linked to a single record
rather than filed twice — that's deduplication, not discarding.

## Git

`git init` this vault, separate from the code repo. Enables real diff/
history on every sync, and recovery if a sync proposal is approved in error.

## Visualization

Mermaid diagrams as inline code blocks inside the relevant `.md` files
(rendered natively by GitHub; VS Code needs one lightweight markdown-mermaid
extension) — no new application. `02-journey/00-index.md` gets an A→B→C→D
flowchart per stage; `06-architecture/building-blocks.md` gets a component
diagram when it exists; `MAP.md` gets one diagram of the vault itself.

## Initial migration scope

Every file currently in this directory — not just the obviously "raw notes"
folders — is in scope for the first `/sync-documentation` run: `AWS
Readiness/`, all of `Docs/` (PRDs, CAS Parsers, Competitor Analysis, Intern,
agents, brand, demo, investigations, orchestration, superpowers plans and
specs), `More .md files/`, `Notes for Unifolio/`. Nothing is hand-migrated;
all of it goes through the same inbox → propose → approve pipeline as any
future raw material, so the same classification logic is exercised from day
one instead of being special-cased for the backlog.

**Batch order** (one source folder per round, each producing one change-set
to review before the next folder is added to `00-inbox/raw/`):

1. `Docs/PRDs/` — foundational/stable, seeds `06-architecture/*` and `05-docs/reference/`
2. `Docs/superpowers/plans/` + `specs/` — richest source, seeds `02-journey/*` and `03-decisions/ADR-*`
3. Root engineering-loop files (`decisions.md`, `log.md`, `session.md`, `AGENTS.md`, `CLAUDE.md`) and their near-duplicates in `More .md files/` — reconciled against batches 1-2
4. Remaining `Docs/` subfolders (CAS Parsers, Competitor Analysis, Intern, agents, brand, demo, investigations, orchestration)
5. `AWS Readiness/`
6. `Notes for Unifolio/` and the rest of `More .md files/` — most scattered, reviewed last

## Open risks

- Volume: the first sync run processes ~200 pre-existing files across the
  6 batches above — several rounds of change-set review, not one giant
  approval.
- Every file must be filed, none discarded — the skill's classification
  step needs a fallback destination (evidence + one-line pointer) for
  content that doesn't cleanly fit a decision/investigation/journey/
  architecture bucket, so "no clean fit" never becomes "skip it."
