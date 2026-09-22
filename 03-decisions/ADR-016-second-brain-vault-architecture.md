# ADR-016: This documentation vault's own architecture — flat Markdown + Git, manual pull, propose-then-approve sync

Status: Accepted — designed and implemented
Date: 2026-09-16
Related: [2026-09-16 journey stage](../02-journey/2026-09-16-second-brain-vault-built.md)

## For stakeholders

This is a decision about the documentation system you are reading right
now, not about the Unifolio product. Before this, the vault's raw notes
(PRDs, engineering logs, AWS notes, personal working notes) had no
structure, no version history, and no way to tell current truth from
superseded thinking. The chosen design is deliberately unambitious: plain
Markdown files, one Git repository, and one repeatable workflow — drop raw
material in, run a sync step, approve a proposed set of changes — instead
of a new app or a rebuild-from-scratch each time. It keeps a permanent,
never-silently-edited history (decisions, investigations, the delivery
journey) alongside a small set of always-current-state files, written so a
non-technical reader and an engineer can read the same document at two
depths.

## Technical detail

### Context

The vault directory had accumulated as an unversioned, ad-hoc collection of
raw notes, copied code-repo docs, and abandoned Obsidian config, with no
structure, no versioning, and no way to distinguish current truth from
superseded thinking. Separately, the actual Unifolio code repo already runs
a working engineering-memory loop (`decisions.md`, `log.md`, `session.md`,
`Docs/superpowers/plans/`+`specs/`) that was not to be touched or
duplicated.

### Decision drivers

- One append-only historical record, never silently rewritten.
- One continuously-updated current-state layer that always reflects what's
  true now.
- Every substantive claim traceable to evidence.
- A single recurring workflow instead of re-deriving the documentation
  prompt each time.
- Readable by two audiences (stakeholder and engineer) from the same files.
- No app beyond a text editor + Git.

### Options considered

The design doc frames these as explicit non-goals rather than a numbered
options table, but each is a real alternative weighed and rejected:

#### Option 1: A dedicated app (Obsidian, Notion)

Rejected — adds a tool dependency and an export/sync problem for no benefit
over plain Markdown viewed in VS Code/GitHub, which every contributor
already has.

#### Option 2: Mandatory arc42-style section set, filled in ahead of need

Rejected — sections would be scaffolded empty and stay empty; the vault's
own governing principle is that folders/files are created only once there
is real content for them.

#### Option 3: A multi-prefix ID taxonomy (FEAT/INC/RISK/REL) from day one

Rejected in favor of starting with only `ADR-XXX` and `INV-XXX` — a larger
taxonomy can be added later if it earns its place, not guessed at up front.

#### Option 4: Automatic, hook-triggered ingestion from the code repo

Rejected — pulls are manual and user-initiated. An automatic pull risks
publishing unreviewed content; every write in this vault requires an
approved change-set first.

### Decision

Flat Markdown, one Git repository (`git init`, separate from the code
repo), no new application. Structure: `00-inbox/` (unprocessed raw
material, two sources — manual code-repo pulls and everything else),
`01-overview/` (stakeholder front door + living status), `02-journey/`
(one file per delivery stage), `03-decisions/` (`decisions-log.md` for
small calls, `ADR-XXX` files for major ones), `04-investigations/`,
`05-docs/` (Diátaxis, created lazily), `06-architecture/` (created lazily),
`07-risks-and-debt.md`, `08-evidence/` (conversation/log/test/screenshot
copies cited by records above), `09-archive/` (completed sub-projects only
— superseded ADRs/investigations stay in place with a status flag, never
moved here). Every ADR and journey-stage file carries both a `## For
stakeholders` paragraph and a `## Technical detail` section instead of two
parallel documents. A `sync-documentation` Claude Code skill implements the
recurring workflow: scan the inbox, extract facts/decisions/experiments,
compare against existing vault content, classify each item against a fixed
destination table, propose a change-set, and only write after explicit
approval — never publishing a stakeholder-facing change, and never
discarding a source file (an item that fits nowhere still gets an evidence
copy and a pointer). The initial backlog of ~200 pre-existing files is
processed through the same pipeline in 6 ordered batches, not
hand-migrated, so the same classification logic is exercised from day one.

### Consequences

Positive:
- No tool dependency beyond Git and a text editor.
- History and current-state are structurally separated, so "what's true
  now" never has to be reconstructed by reading a changelog.
- The propose-then-approve loop means nothing publishes without a human
  seeing the change-set first.

Negative:
- Manual, human-run ingestion — no automatic sync, so the vault can lag
  the code repo until someone runs a pull.
- Classification judgment calls (which bucket does an item belong in, is
  something a hypothesis or a verified fact) rest on the agent running the
  sync each time; the skill's rules constrain but don't eliminate this.
- Processing ~200 pre-existing files in one initial backlog is a real
  volume risk, called out in the design doc itself as needing several
  rounds of change-set review rather than one giant approval.

### Validation

Fully built, not merely designed — this ADR describes the plan that
produced the vault this file lives in. All 5 tasks of the implementation
plan (skeleton + git, templates, current-state docs + `MAP.md` + vault
`CLAUDE.md`, the `sync-documentation` skill + a smoke test, the how-to
guide) were executed and committed: `d782bbc` (skeleton), `eb6d747`
(templates), `f292cf8` (current-state docs/MAP/CLAUDE.md), `647da76`
(sync-documentation skill), `bba8664` (how-to guide) — confirmed via this
repository's own `git log`, which is permissible evidence here since it is
the vault's own history, not source code from the Unifolio code repo. A
subsequent review-and-fix pass (`df38829`) and 3 real ingestion batches
(PRDs, then two superpowers sub-batches) followed, all visible in the same
log.

### Evidence

- Design: `08-evidence/documents/specs/2026-09-16-second-brain-vault-architecture-design.md`
- Plan: `08-evidence/documents/plans/2026-09-16-second-brain-vault-implementation.md`
- Build confirmation: this vault's own `git log` (commits `d782bbc` through
  `bba8664`, and the batch-ingestion commits that followed)
