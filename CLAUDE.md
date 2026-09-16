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
