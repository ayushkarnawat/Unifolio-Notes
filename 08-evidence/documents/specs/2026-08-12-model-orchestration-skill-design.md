# Design: Model Orchestration Skill

**Date:** 2026-08-12
**Status:** Approved by user, pending write-up as an implementation plan.

## Problem

The user runs two Claude accounts (personal Pro + work) side by side, plus a
ChatGPT Plus / Codex account, and just finished setting up the official
`openai/codex-plugin-cc` plugin in this Claude Code session (`/codex:setup`,
`codex login` — verified ready, ChatGPT login active). Their goal: preserve
token/quota across all these accounts by making Claude Code the primary
interactive orchestrator (architecture, multi-file design, complex
debugging, final assembly) and pushing the bulk of token-heavy,
mechanical, or repetitive sub-work to Codex, with Opus reserved as a rare,
user-approved escalation rather than a default.

The hard part isn't the delegation itself — it's **context loss at the
handoff boundary**. A plan Claude produces carries reasoning about why
certain approaches were rejected; a plain prompt summary handed to Codex
loses that nuance, so Codex re-derives (or gets wrong) decisions Claude
already made. The skill's core job is making that handoff durable and
re-readable, not just describing a delegation policy.

This skill is scoped to this project (`.claude/skills/`, project-level per
the user's explicit choice) even though the underlying workflow is
personal/cross-project — the user chose to build and validate it here
first rather than at `~/.claude/skills/`.

## Existing plumbing this design builds on (not reinvents)

The `openai/codex-plugin-cc` plugin, already installed and authenticated
this session, provides real mechanics this skill must sit on top of rather
than duplicate:

- **`codex:codex-rescue` subagent** — a thin Sonnet forwarder. Its only job
  is one call to `codex-companion.mjs task ...`; it must not inspect the
  repo, reason independently, or do follow-up work. Dispatched via the
  `Agent` tool like any other subagent — including **in parallel**, N
  independent calls at once.
- **`codex-cli-runtime` skill** — the internal contract `codex-rescue` must
  follow (flag handling, `--resume-last`/`--fresh`, `--write` default,
  model/effort pass-through).
- **`gpt-5-4-prompting` skill** — prompt-shaping guidance for turning a
  request into a tight, block-structured Codex prompt before the single
  `task` call.
- **`codex-result-handling` skill** — presentation rules for whatever comes
  back: preserve verdict/summary/findings structure, never auto-apply
  fixes from a review, stop and ask first.
- **`/codex:review` / `/codex:adversarial-review`** — built-in review
  commands against local git state; adversarial mode explicitly tries to
  break confidence in a change (auth/data-loss/race-condition/rollback
  focus), returns structured findings, never edits code itself.
- **`/codex:transfer`** — hands the *entire* current Claude Code session to
  a resumable Codex thread. Considered and rejected as the primary handoff
  mechanism (see Alternatives) in favor of a curated per-task doc, but
  still available as an escape hatch for genuinely whole-session handoffs.
- **Concurrency, verified live this session** by reading
  `codex-companion.mjs` directly (not assumed from docs): a fresh
  (non-`--resume-last`) `task --background` launch gets its own job ID and
  tracked PID via `enqueueBackgroundTask`; the only "already running" guard
  in the code (`resolveLatestTrackedTaskThread`) fires solely on the
  `--resume-last` path. Multiple concurrent fresh background dispatches are
  structurally supported. **Not yet live-tested with a real 2-parallel-task
  run** — flagged as a verify-before-fully-relying-on-it item, per this
  project's own standing convention of live-verifying integrations rather
  than trusting code-reading alone.

## Roles

- **Orchestrator — Claude Code (Sonnet by default).** Architecture,
  multi-file interface design, complex debugging, final assembly, all
  planning. Never delegated away. Escalates to Opus only per the named
  triggers below, always with the user's explicit approval first — no
  silent model switch.
- **Worker, default (~90%+) — Codex.** For one delegated subtask: a single
  `Agent(subagent_type: codex:codex-rescue)` call. For **parallelizable
  independent subtasks** — the case that would otherwise mean spinning up N
  Claude subagents — dispatch **N parallel `codex:codex-rescue` Agent
  calls instead**, each forwarding its own prompt to a separate Codex
  background job. This is the primary token-saving mechanism on both
  sides: real generation cost lands on Codex/ChatGPT quota, Claude only
  pays for N thin-forwarder calls plus later collecting results.
- **Worker, fallback (rare) — a genuine Claude subagent** (`Explore`,
  `general-purpose`). Used only when: (a) the subtask is read-only
  codebase exploration cheap enough Claude-native that a Codex round-trip
  isn't worth it, (b) Codex has already failed or looped on this exact
  subtask across ≥2 rounds with a rewritten handoff doc, or (c) the task is
  too nuanced to specify in a forwarded prompt without losing reasoning
  that only holds together inside Claude's own context.
- **Two-Claude-account setup — context only, not orchestration logic.** The
  skill documents that this setup exists (heavy Codex delegation is *why*
  quota lasts longer on whichever Claude account is active) but does not
  prescribe which account handles which kind of work — the user explicitly
  wants to keep making that call themselves, session to session.

## Delegation-rules table (task-type classification)

| Task type | Default worker | Notes |
|---|---|---|
| Boilerplate/repetitive codegen | Codex | e.g. test scaffolding across similar files |
| Mechanical refactor | Codex | rename, extract, pattern-apply across files |
| Isolated bug-fix implementation | Codex | once root cause is diagnosed by Claude |
| Research/lookup (docs, API shapes, live endpoint verification) | Codex | matches how the user already used Codex-style live-verification work (AMFI/NSE endpoints) |
| Architecture/multi-file interface design | Claude (orchestrator) | never delegated |
| Final assembly / integration | Claude (orchestrator) | never delegated |
| Read-only codebase exploration | Claude subagent (`Explore`) | cheap, no Codex round-trip needed |

This table is the first thing consulted when a delegable subtask appears;
ambiguous cases default to Codex unless one of the fallback conditions
above is met.

## Handoff-doc lifecycle

Before delegating any non-trivial subtask to Codex, Claude writes
`Docs/orchestration/<task-slug>-handoff.md`:

```markdown
# Handoff: <task-slug>
**Status:** OPEN | IN_PROGRESS | REVIEW | DONE
**Parent plan:** <link to Docs/superpowers/plans/... if applicable>

## Task
What Codex needs to build/fix — concrete and bounded.

## Constraints
Non-negotiables that apply (Decimal-never-float, schema rules, etc. —
pulled from CLAUDE.md, not restated in full).

## Approaches considered and rejected
Why, briefly — the exact nuance that dies in a plain prompt summary.

## Open questions
Anything Codex should flag back rather than guess on.
```

The Codex-facing prompt (built via `gpt-5-4-prompting`) **references this
file's path** rather than restating its contents inline — the doc is the
single source of truth both sides re-read, not a paraphrase that drifts
out of sync turn to turn. Claude updates `Status` and appends findings
after each round. The file is git-tracked, so it survives context
compaction on either side, unlike a fact folded only into a prompt string.

`Docs/orchestration/` sits alongside the existing `Docs/superpowers/plans/`
convention rather than replacing it: a handoff doc is *delegation-scoped*
(one per Codex task), while `Docs/superpowers/plans/` stays the
*implementation-plan* artifact (one per build phase). A handoff doc
typically links back to its parent plan rather than duplicating it.

## Session-level delegation log

`Docs/orchestration/delegation-log.md` — one append-only line per
delegation decision (task slug, worker chosen, one-line why). Lightweight
by explicit user choice: no `ledger.jsonl`-style structured event log, no
digest-pinning, no phase-folder hierarchy (all present in `kiln`, the
closest reference project, and explicitly rejected here as more machinery
than this project's existing `session.md` / `Docs/superpowers/plans/`
conventions warrant).

## Adversarial review gate (mandatory)

Every Codex-implemented change gets `/codex:review` or
`/codex:adversarial-review` before its handoff doc's Status moves to
`DONE` — mirrors `kiln`'s "whoever builds it, the other family judges it"
rule, applied here as Codex-builds/Claude-or-Codex-adversarial-reviews
rather than a true dual-model-family review (Claude doesn't have a
symmetric "review Claude's own plan" step, since planning never leaves the
orchestrator). Per `codex-result-handling`'s existing rule, findings are
presented and the user decides what gets fixed — never auto-applied,
regardless of how obvious a fix looks.

## Opus-escalation triggers

Ask-before-switch, never silent, fires only on named conditions:

1. Architecture-level ambiguity spanning subsystems the orchestrator can't
   resolve from `/Docs` alone.
2. Codex has failed or looped on the same subtask across ≥2 rounds, even
   after the handoff doc was rewritten to close the gap.
3. A cross-cutting design conflict between PRD/ADR/schema — this already
   triggers a stop-and-ask per CLAUDE.md's existing "Working style" rule;
   this skill extends that by naming Opus as a candidate resolution path
   the user can choose, not just a flag-and-wait.

## No-Codex fallback

On the first delegation attempt in a session where `/codex:setup` reports
not-ready (no Codex CLI, or not authenticated), ask once — not per
delegation attempt — offering three options: (a) run this session
Claude-only via subagents, using the same delegation-rules table but with
the Claude-subagent fallback lane as the only worker, (b) name a different
tool already configured (e.g. Gemini CLI) if the user wants the skill
adapted around it, or (c) **skip this skill entirely for the session** —
explicitly offered per the user's instruction not to force the workflow on
someone who doesn't want it. Whichever is chosen, remember it for the rest
of the session; don't re-ask.

## Skill file structure

```
.claude/skills/model-orchestration/
  SKILL.md                        # frontmatter, roles, trigger conditions, core workflow
  references/
    delegation-rules.md           # the task-type table, loaded on demand
    handoff-doc-template.md       # the structured handoff format + lifecycle rules
    escalation-triggers.md        # the three named Opus triggers
    no-codex-fallback.md          # the ask-once / opt-out flow
```

Follows `superpowers:writing-skills` conventions (lean `SKILL.md`,
reference files loaded on demand rather than always-loaded bulk).

## Documentation updates (part of this same piece of work, not deferred)

- `CLAUDE.md` gets a new short section pointing at this skill, same
  pattern as the existing "Skill Observation" section — a structural
  trigger, not reliance on description-matching alone.
- `session.md` gets a note recording that this skill was designed/built,
  consistent with the file's existing "working notes for picking this
  project back up cold" role.

## Alternatives considered and rejected

- **Lean entirely on `/codex:transfer`** for context handoff instead of a
  curated doc. Rejected: `transfer` hands over the *whole* session
  verbatim, which is the opposite failure mode from what the user is
  solving (token-heavy on Codex's side, an unbounded and hard-to-navigate
  context on Codex's side) — the user specifically wants an *curated*
  plan/constraints/rejected-approaches artifact, not a full-session dump.
  Kept as an escape hatch for cases that genuinely warrant whole-session
  continuity, not as the default mechanism.
- **kiln-equivalent heavy machinery** (ledger.jsonl, digest-pinned routing
  file, phase-scoped folders). Rejected: explicitly, by the user, as more
  overhead than this project's existing lightweight conventions justify —
  a routing file with one project and one clear default split (90% Codex)
  doesn't need digest-pinning, and a full event ledger duplicates what
  `session.md` + git history + the handoff docs themselves already cover.
- **Claude subagents as the default parallel-dispatch worker** (the
  original framing before the user's correction). Rejected: burns Claude
  quota on work that could just as well run on Codex quota via parallel
  `codex:codex-rescue` dispatches — directly opposed to the "save tokens
  on both sides" goal that drove this design.

## Open item carried into implementation

Live-verify genuine 2+ parallel `codex:codex-rescue` dispatches actually
complete independently (no silent collision on job files, log files, or
the workspace-root job-listing state) before the skill's docs assert
parallel Codex dispatch as a relied-upon capability rather than a
theoretical one from reading the script.
