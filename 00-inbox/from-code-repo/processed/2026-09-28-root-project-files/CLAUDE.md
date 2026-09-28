# CLAUDE.md — Unifolio (MF MVP)

## What this project is

Unifolio is a mutual fund portfolio tracking and wealth-management platform for the
Indian market — a genuinely superior, free-core alternative to Mprofit. This build
covers the MF-only MVP: CAS import, onboarding, a main holdings dashboard, and an
analytics dashboard.

Setup commands, doc read-order, non-negotiables, and architecture: see `AGENTS.md` —
that file is the single source of truth for both Claude Code and Codex, read it first,
every session, before this one. Don't re-add any of that content here; edit `AGENTS.md`
and let this file point to it, so nothing drifts out of sync between agents.

## Working style

- Ask before assuming on anything the docs mark as an open question or "needs your
  input" — check `/Docs` for unresolved items before guessing.
- When a PRD, ADR, or the schema seems to conflict with what you're about to build, stop
  and say so — don't silently resolve the conflict in either direction.
- Explain non-obvious decisions inline as code comments where the *why* isn't in the
  docs (e.g., a specific edge case handled a specific way) — don't restate what's already
  in `/Docs`.

## Skill Observation

At the start of any task-oriented session — any interaction where you will
use tools and produce deliverables — invoke the task-observer skill before
beginning work. This ensures skill improvement opportunities are captured
throughout the session.

When loading any skill, check the observation log for OPEN observations
tagged to that skill. Apply their insights to the current work, even if
the skill file hasn't been updated yet. This enables immediate application
of observations before they're permanently integrated during the weekly
review.

## Model Orchestration

When delegating non-trivial implementation, refactor, boilerplate, or
research/lookup work — or dispatching parallelizable independent
subtasks that would otherwise mean multiple Claude subagents — invoke
the model-orchestration skill first. It governs the Claude
(orchestrator) / Codex (default worker) split, the mandatory per-task
handoff doc, and the mandatory adversarial-review gate before any
Codex-implemented change is considered done. Full design:
`Docs/superpowers/specs/2026-08-12-model-orchestration-skill-design.md`.

## Agent skills

### Issue tracker

GitHub Issues on `ayushkarnawat/MVP_V1_MF_only`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Domain docs

Not the generic `CONTEXT.md`/`docs/adr/` layout — points at this repo's existing `/Docs`
system (schema, TDD, ADRs, PRDs, dated specs under `Docs/superpowers/`, `session.md`)
instead. See `docs/agents/domain.md`.

## Session State

*(Updated 2026-09-26. This section is a one-line current-status pointer, not a log —
do not append session narrative here again. Full current status: `session.md` at repo
root, overwritten each session. Full permanent history: `log.md` (append-only, never
trimmed), `backend.md`/`database.md` (backend/schema changes only), `decisions.md`
(product/technical decisions). Full per-task Codex-delegation history:
`Docs/orchestration/delegation-log.md`. Deferred/not-yet-built features:
`DEFERRED_FEATURES.md`.)*

**Latest (2026-09-24):** CAS import PAN check moved from Confirm-time to upload-time
(`pan_claims.py` replaces `attribution.py`; migration `0016`) — fixes every first import
on a fresh account failing to match a family member. Fully committed
(`11f7dfc`/`b8d88a8`/`b8901e4`/`bdfa2ba`), not uncommitted as this section previously
(incorrectly) said. Full detail: `session.md`'s "Latest" section.

**2026-09-15 → 2026-09-24, previously undocumented in any doc, backfilled this pass:**
real email-OTP delivery went live (Postmark first, then fully replaced by Amazon SES —
Postmark removed entirely, not kept dormant); ADR-004 reopened 2026-09-18 — PAN is now
persisted encrypted per household member and the raw CAS PDF is retained 30 days,
superseding the original "no PAN, ever" decision; cross-account PAN conflicts surface as
a UI popup instead of a silent freeze; a phone-gate collision bug fixed (distinct from
the still-open phone-OTP item below). Full detail: `session.md`'s "previously
undocumented gap" section, `log.md`'s dated entries, `decisions.md`.

**Still open (detail in `session.md`'s "Still open" section):** a dead
`HoldingsTable.tsx` field reference; a non-index-seek-bounded SQLite scan in
`category_ranking.py` (Postgres has been live in staging since 2026-09-09 — worth
revisiting now, not just a hypothetical future follow-up); an ARIA IDREF gap on the SIP
tab switcher (accepted documented limitation); ADR-006's actual EventBridge Scheduler +
ECS Fargate Terraform (the AWS account/ECR/ECS cluster this was blocked on now exist as
of 2026-09-08/09 — no longer infra-blocked, just not yet picked up; the 4 job scripts
themselves are done); the backend API domain naming decision (§19/§22 Phase 5); phone-OTP
login silently creating a new account for an unrecognized phone number instead of
erroring like email does (found on staging 2026-09-11, root-caused, explicitly deferred
by user decision, re-confirmed still present 2026-09-26 — see session.md item 9).

**Resolved, dropped from this list:**
- **2026-09-24**: the PAN-attribution-timing bug and the "still uncommitted" tracking
  gap — see "Latest" above.
- **2026-09-18**: the ADR-004 "no PAN persistence" constraint — superseded by design, see
  above.
- **2026-09-07**: NAT-approach/region/domain decisions that were blocking Terraform
  Phase 0/1 planning; Phase 0/1 itself started and Phases 1-3 are now live in AWS
  (2026-09-08/09) — see `session.md`.
- **2026-09-02**: the blocking `db.commit()` inside an `async def` freezing the
  single-worker event loop — fixed commit `bb5225f` (2026-08-27): `commit_off_loop`
  routes every reachable `db.commit()` through `asyncio.to_thread` across all 8 affected
  files, with a regression test.

Knowledge graph (`.ua/knowledge-graph.json`) is stale as of commit `35fedd3` — re-run
`/understand` (incremental) before trusting it. This has not been re-run as part of this
documentation pass; still needs doing.


