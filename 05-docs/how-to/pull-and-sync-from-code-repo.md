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

## For pasted Claude conversations, meeting notes, or screenshots (not from the code repo)

Same idea, simpler: drop the file(s) directly into `00-inbox/raw/`, then
run `/sync-documentation`.

## For the initial migration batches (pre-existing vault content)

`01-overview/roadmap.md` lists 6 batches of pre-existing files already in
this vault (e.g. `Docs/PRDs/`, `AWS Readiness/`) that need to go through
the same inbox → sync pipeline. To stage one batch:

1. Move (don't copy — these files already live in this vault, no need to
   duplicate them) the batch's folder or files into `00-inbox/raw/`.
2. Run `/sync-documentation`.
3. Review and approve the change-set as above.
4. Only move the next batch in after this one is fully processed — the
   roadmap's batch order is deliberate (foundational content seeds later
   batches' cross-references).
