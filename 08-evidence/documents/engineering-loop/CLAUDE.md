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

*(Updated 2026-09-07. This section is a one-line current-status pointer, not a log —
do not append session narrative here again. Full current status: `session.md` at repo
root, overwritten each session. Full per-task history: `Docs/orchestration/delegation-log.md`.
Deferred/not-yet-built features: `DEFERRED_FEATURES.md`.)*

**Latest (2026-09-07):** AWS account created (root MFA, budget alert, `ayush-admim`
IAM admin user), region `ap-south-1` confirmed, and `unifolio.in` cut over to a Route 53
public hosted zone (GoDaddy nameservers switched, propagation verified via `dig`/
`nslookup`, existing Microsoft 365 mail records — MX/SPF/DMARC/autodiscover — preserved).
Domain architecture decided: `unifolio.in` (apex) is the marketing/overview site with
Login/Sign Up CTAs, `app.unifolio.in` is the production web app, `staging.unifolio.in` is
the staging web app. Networking decision: staging uses **fck-nat** (self-hosted EC2, not
a managed NAT Gateway) to avoid the NAT Gateway cost-approval step. All of this is folded
into `AWS Readiness/aws-golive-readiness-report.md` (§12 Option C, §19, §22 Phase 5).
Backend API domain naming (dedicated subdomain vs. path-based CloudFront routing) is
still open, needed before §22 Phase 5, not before Phase 0/1.

Before starting Phase 0/1 Terraform work, independently re-verified — not trusted from
the prior session's self-report — that 2026-09-03's F8/F4/non-PAN-dedup work (previously
flagged here as "still uncommitted") was in fact already committed, as `9fe21fe`, and
that every code-level item `AWS Readiness/aws-golive-launch-blockers.md` still listed as
an open BLOCKER (Dockerfile, the OTP stub-mode guard, CORS, `/imports/parse` upload
validation, the enum-widening migrations, the ADR-006 job scripts) is actually present
in the code — that doc was stale, not the code; corrected in this pass. Full test suites
reran fresh: 614 backend passed (6 skipped), 397 frontend passed (75 files), `tsc -b
--noEmit` clean.

**Still open (detail in `session.md`'s "Still open" section):** a dead
`HoldingsTable.tsx` field reference; a non-index-seek-bounded SQLite scan in
`category_ranking.py` (Postgres follow-up, deferred until a real Postgres target
exists); an ARIA IDREF gap on the SIP tab switcher (accepted documented limitation);
ADR-006's actual EventBridge Scheduler + ECS Fargate Terraform (deferred until an AWS
account/ECR/ECS cluster exist — the 4 job scripts themselves are done); the backend API
domain naming decision (§19/§22 Phase 5); the AWS Terraform infra itself — region/domain/
NAT decisions are now resolved (see above), so Phase 0/1 is unblocked and ready to start;
phone-OTP login silently creating a new account for an unrecognized phone number instead
of erroring like email does (found on staging 2026-09-11, root-caused, explicitly
deferred by user decision — see session.md item 9 for the fix direction and the
account-enumeration tradeoff of the broader request-time-check version).

**Resolved, dropped from this list:**
- **2026-09-07**: NAT-approach/region/domain decisions that were blocking Terraform
  Phase 0/1 planning — see "Latest" above.
- **2026-09-02**: the blocking `db.commit()` inside an `async def` freezing the
  single-worker event loop — fixed commit `bb5225f` (2026-08-27): `commit_off_loop`
  routes every reachable `db.commit()` through `asyncio.to_thread` across all 8 affected
  files, with a regression test. This list wasn't updated when that commit landed;
  caught while writing the Analytics precompute implementation plan, which had cited
  this item as load-bearing for a design decision.

Knowledge graph (`.ua/knowledge-graph.json`) is stale as of commit `35fedd3` — re-run
`/understand` (incremental) before trusting it.


