# ADR-006: Background job scheduling — EventBridge Scheduler triggering ECS Fargate RunTask

Status: Accepted
Date: 2026-07-22
Related: ADR-005 (the compute target this depends on),
`06-architecture/runtime-and-data-flow.md`, `05-docs/reference/external-data-sources.md`

## For stakeholders

Unifolio needs to refresh public market data on a schedule — fund prices daily, expense
ratios monthly, fund sizes quarterly, index levels daily — plus compute monthly
portfolio snapshots and fund scores. We are using AWS's own scheduler to start a
short-lived container on the same platform the main application runs on, reusing the
same codebase. We did not add a separate queueing system, because these jobs are
time-triggered, not event-triggered, and a message broker would be a whole extra piece
of infrastructure for no gain. We did not use Lambda, because the fund-price refresh
covers thousands of schemes and historical backfills can run long enough to hit
Lambda's time limit. One thing to look up separately: distributor names are resolved on
demand the first time an unfamiliar distributor code appears, not on a schedule.

## Technical detail

### Context

The TDD lists jobs needing a scheduling mechanism: NAV daily refresh, TER monthly, AAUM
quarterly, benchmark index daily, plus ARN resolution on demand — and, per the TDD's own
table, two internally-computed jobs (monthly portfolio snapshots, monthly fund score
computation aligned to the TER refresh since cost is an input). The original proposal —
EventBridge Scheduler triggering ECS tasks or Lambda — needed confirming as current,
documented AWS practice rather than an assumption, particularly now that it runs on ECS
Express Mode (ADR-005) rather than App Runner, which had no native scheduled-task
support at all.

### Decision drivers

- Cadences are slow (daily/monthly/quarterly), so cold-start latency is irrelevant.
- Jobs are naturally container-shaped: they reuse the main app's Python codebase,
  dependencies, and DB connection logic.
- Managed-service-first, consistent with ADR-002/003/005.
- Some jobs (full-universe NAV refresh, historical backfill) can run long.

### Options considered

#### Option 1: EventBridge Scheduler → ECS Fargate `RunTask` (chosen)
**Advantages:** documented current AWS practice — AWS's own Serverless Land publishes a
reference architecture for exactly this combination; no scheduling infrastructure beyond
EventBridge, which is AWS-native, serverless, and pay-per-use; tasks share
infrastructure and IAM context with the main application, reusing the same codebase
rather than needing a separate deployment pipeline; no execution-duration ceiling.
**Disadvantages:** Fargate container cold start adds latency versus a warm Lambda —
noise at daily/monthly/quarterly cadence, but a real trade-off to know; AWS support
forums document occasional Fargate capacity-availability transients causing a scheduled
task to silently not start, mitigated by an EventBridge rule watching for
`SERVICE_TASK_PLACEMENT_FAILURE` with a retry/alert path — a known documented pattern,
not a novel problem.

#### Option 2: AWS Lambda for all jobs
**Advantages:** per-invocation pricing and fast cold start suit short jobs well.
**Disadvantages:** NAV refresh across the full scheme universe (thousands of schemes)
and the historical backfill work these jobs sometimes do risk running past Lambda's
execution-time limit for anything beyond a simple daily incremental update. Fargate's
no-duration-limit model removes that as a future constraint without re-architecting a
job that outgrows the ceiling.

#### Option 3: A dedicated task queue (Celery/Redis)
**Advantages:** full task-queue semantics, retries, fan-out.
**Disadvantages:** not adopted — adds an entire message broker for a job set that is
fundamentally time-triggered rather than event-triggered from application activity
(aside from ARN resolution, which is correctly handled inline). Worth reconsidering only
if job volume or complexity grows well past four scheduled jobs plus one on-demand call.

### Decision

**AWS EventBridge Scheduler triggering ECS Fargate `RunTask`** for the periodic jobs —
NAV, TER, AAUM, and benchmark index refresh, plus the two internally-computed jobs
(monthly portfolio snapshots, monthly fund scores) per the TDD's table — sharing the
same FastAPI codebase's job modules as one-off task invocations rather than a separately
deployed scheduler service.

**ARN resolution stays on demand, not scheduled** — triggered directly by the Import
Service when a new, previously-unseen ARN code appears (PRD-03 FR-11a), invoked
synchronously or as a lightweight async call within that request path rather than
through EventBridge at all.

### Consequences

**Positive:**
- No scheduling infrastructure beyond EventBridge.
- Jobs share infrastructure, IAM context, codebase, dependencies, and DB connection
  logic with the main API.

**Negative:**
- Fargate cold start on every scheduled run — irrelevant at these cadences.
- Fargate capacity transients can cause a task to silently not start; requires the
  `SERVICE_TASK_PLACEMENT_FAILURE` retry/alert path to be actually configured. **This is
  a setup obligation, not a theoretical note** — see `07-risks-and-debt.md`.

**Neutral:**
- Lambda remains reasonable for genuinely short, lightweight jobs if any emerge later —
  for instance if ARN resolution ever needs to move off the request path into an async
  trigger.

### Validation

Validated when each scheduled job runs unattended on its cadence and a deliberately
failed placement raises an alert rather than passing silently. Every job's failure mode
is a stale-data label in the UI, never an error state — see
`06-architecture/quality-and-constraints.md`.

### Evidence

- Source document: `08-evidence/documents/ADR-Technical-Stack-Decisions.md` (ADR-006)
- Job list and cadences: `TDD-Unifolio.md`, Background Jobs table
- Research cited in the source, not independently re-verified during this ingest: AWS
  Serverless Land EventBridge-Scheduler-to-ECS reference pattern; AWS re:Post threads on
  Fargate capacity transients.

## Addendum — 2026-09-23 (piece 1, job-scripts execution): DONE 2026-09-03

This ADR's job list splits into two genuinely different pieces of work
(user-confirmed 2026-09-02): application-code job entrypoints, and the
actual scheduling infrastructure. Piece 1 shipped first, deliberately
decoupled from the AWS account not existing yet at the time.

Four standalone job-entrypoint scripts were built under
`backend/scripts/jobs/` — `refresh_nav_daily.py`, `refresh_ter_monthly.py`,
`refresh_aaum_quarterly.py`, `refresh_benchmark_daily.py` — each a thin
wrapper around an already-existing, already-tested fetch/refresh function;
none of the four wrapped functions were modified. Two design decisions
worth recording: the NAV job's scheme universe is deliberately scoped to
schemes actually held by at least one folio, not the full AMFI reference
catalog (`warm_nav_history` fetches full history per call, so sweeping
every known scheme daily would be a wasteful full-history fetch for
schemes nobody holds — unlike TER/AAUM, which upsert cheaply across the
whole reference table). The `refresh_aaum_quarterly.py` job fixes a real
gap this ADR's list implied: `refresh_aaum_data` had zero production
callers anywhere in the codebase before this. The benchmark job's lookback
window, previously undecided, was resolved to a fixed 10 calendar years
back from today (leap-year-safe), not a naive `days=3650`. A shared
`app/jobs/` base-class framework across the four scripts was explicitly
rejected as premature — piece 2 (below) wasn't yet built, so the shape
EventBridge would eventually invoke these under wasn't known yet.
Independently rerun full backend suite: 600 passed/6 skipped/0 failed.
Mandatory adversarial-review gate: PASS, zero findings.

Evidence: `08-evidence/documents/orchestration/adr006-background-jobs-handoff.md`

## Addendum — 2026-09-23 (piece 2, scheduler Terraform): authored 2026-09-10

With Phases 1-5 of the staging AWS infrastructure confirmed applied and
live (see the dated update on
[`06-architecture/deployment.md`](../06-architecture/deployment.md)), the
remaining EventBridge Scheduler + ECS Fargate Terraform for the four job
scripts above was authored: a new `infra/modules/scheduler` module, one
lightweight ECS task definition per job (reusing the existing backend ECS
task execution role rather than a new one), four `aws_scheduler_schedule`
resources on `Asia/Kolkata`-timezone cron expressions, and a scheduler IAM
role scoped to exactly those four task definitions. Two prerequisite
container fixes were required and found by reading the existing
Dockerfile/entrypoint before writing the scheduling spec: the Dockerfile
did not copy `backend/scripts/` into the image at all, and the container
entrypoint unconditionally ran the web server regardless of what command
ECS passed it. Reviewed PASS, zero findings, 2026-09-10; this batch's
source material authors the Terraform but does not confirm it was
applied — treat "applied and running on schedule" as unconfirmed, not
done, per this vault's "authoring only" boundary convention for this
delegation pattern (ADR-011).

Evidence: `08-evidence/documents/orchestration/adr006-scheduler-terraform-handoff.md`,
`adr006-scheduler-terraform-implementation-prompt.md`
