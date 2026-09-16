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
