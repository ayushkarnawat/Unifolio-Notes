# Phase 7 — Production Hardening: detailed plan and sequencing

**Status:** IN PROGRESS (2026-09-10) — this doc supersedes the terse Phase 7 bullet
list in `AWS Readiness/aws-golive-readiness-report.md` §22 with per-item status,
sequencing, and the beta-scale reasoning behind what's pulled forward vs. deferred.
Update this doc directly as items close — it's the source of truth for "what's left
to close out staging," not a one-time snapshot.

**Context driving sequencing below:** a beta cohort of 5→30 users, ramping over
~20 days, starting once Phase 6 validation passes. Not the ~1,000 MAU target the
original readiness report was written against — several items that report flagged
as "elevated priority" are elevated *for that target*, not for this one. Each item
below states which case applies and why.

## Pulled forward, ahead of the rest of Phase 7

### 1. ADR-006 background jobs — EventBridge Scheduler + ECS Fargate Terraform

- **Why now:** the job *code* (`backend/scripts/jobs/*.py`) has been done since
  2026-09-03; only the scheduling infra was deferred, pending an AWS
  account/ECR/ECS cluster existing. Those now exist (Phase 3). Beta users expect
  a populated analytics dashboard (category rank, benchmark comparison, AAUM/TER),
  not a documented-as-acceptable empty state — the original Phase 6 bar ("confirm
  empty-state renders gracefully") is no longer sufficient once real testers are
  involved.
- **Scope:** EventBridge Scheduler rules (one per job: daily NAV, daily benchmark,
  monthly TER, quarterly AAUM) targeting `ecs:RunTask` against the existing
  `unifolio-staging-backend` task definition/cluster — no new Lambda or compute
  target, confirmed 2026-09-08.
- **Status:** handoff + implementation prompt authored 2026-09-10
  (`Docs/orchestration/adr006-scheduler-terraform-handoff.md` /
  `-implementation-prompt.md`). Not yet dispatched to Codex.

### 2. CI/CD — GitHub Actions deploy pipeline to staging

- **Why now:** ~15 planned updates in the next 2-3 days, with live beta feedback
  expected to turn into fast follow-up fixes. Manual `terraform apply`/`npm run
  build`/`aws s3 sync`/`aws cloudfront create-invalidation` on every change doesn't
  scale to that cadence and risks a skipped step under time pressure.
- **Scope:**
  - Branch-strategy prerequisite (see below) — `main` becomes the trunk that
    deploys to staging.
  - Extend the existing `.github/workflows/ci.yml` test jobs (backend-fast,
    backend-postgres, frontend) to gate two new deploy jobs, rather than
    replacing them.
  - New `deploy-backend` job: build image → push to ECR → `aws ecs
    update-service --force-new-deployment` → wait for service stable.
  - New `deploy-frontend` job: `npm ci && npm run build` (with
    `VITE_API_BASE_URL=https://staging-api.unifolio.in`) → `aws s3 sync --delete`
    → `aws cloudfront create-invalidation`.
  - Auth: GitHub OIDC → a scoped IAM role (not static access keys in GitHub
    Secrets) — deliberately closes the exact class of risk that caused the
    2026-09-09 exposed-access-key incident, rather than reintroducing it via a
    new secret.
  - Database migrations: needs an explicit decision on how `alembic upgrade
    head` runs in the pipeline (e.g., a pre-deploy one-off ECS task) — flagged as
    an open design question, not yet resolved.
- **Status:** not started. Branch-strategy decision (below) blocks starting this.

## Branch-strategy decision (blocked item 2 above)

- **Decision confirmed by user 2026-09-10:** `main` is the trunk that
  auto-deploys to `staging.unifolio.in`. A `production` branch, merged into
  deliberately (not automatically), deploys to `app.unifolio.in` — keeping a
  real user-facing release an explicit, gated action.
- **Status:** DONE. Fast-forward merged `feat/enhanced-ui` → `main`
  (zero-conflict, `main` was a strict ancestor). `production` branch created
  from `main` and pushed to `origin/production` — currently inert
  (identical content to `main`, no CI/CD workflow targets it yet; nothing
  auto-deploys to `app.unifolio.in` until both the CI/CD pipeline (item 2)
  is extended to cover it and real production AWS infrastructure exists —
  see the separately-tracked "production infra" item below). This no
  longer blocks item 2 — CI/CD authoring can start once ADR-006 is
  dispatched/reviewed, per the sequencing summary.

## Deferred, with explicit reasoning tied to the 5→30-user/20-day window

### 3. In-process cache → shared store rewrite

- **Readiness report's stated reason for elevated priority:** removes the
  single-ECS-task constraint, needed before staging is trusted as the ongoing
  home for ~1,000 real users.
- **Why deferred here:** 30 concurrent-ish beta testers does not approach the
  scale that constraint exists for. Single ECS task, desired count = 1, no
  autoscaling, is correct and sufficient at this scale — matches the existing
  Phase 3 design intentionally (multi-task correctness bugs from §4 are avoided
  entirely by staying on 1 task).
- **Revisit trigger:** when there's a concrete need for a 2nd ECS task —
  either approaching the real ~1,000 MAU target, or a specific availability
  requirement for this beta batch that a single task can't meet (neither is
  true today).

### 4. Real SMS/email OTP provider

- **Why deferred:** staging's stub OTP mode is a deliberate, already-resolved
  decision (§4) for this environment, not a placeholder gap. Beta testers don't
  need real SMS/email delivery to exercise the product end to end.
- **Revisit trigger:** moving beyond a beta/staging audience to a broader/public
  sign-up flow, or if Google Sign-In alone doesn't cover the beta cohort's needs.

### 5. NAT Gateway upgrade (fck-nat → managed NAT Gateway)

- **Why deferred:** fck-nat was chosen specifically to avoid the NAT Gateway
  cost-approval step for a traffic volume that doesn't justify it (§19,
  2026-09-07 decision) — 30 beta users doesn't change that math.
- **Revisit trigger:** production go-live, or an uptime/HA requirement for
  fck-nat's single EC2 instance that becomes concrete (e.g. an observed outage).

### 6. Structured logging, correlation IDs, error-tracking SDK

- **Why deferred:** valuable but not blocking for a 30-user beta; CloudWatch
  logs (already flowing) are being watched actively during Phase 6 validation
  per its own task list, which covers the immediate observability need.
- **Revisit trigger:** beta feedback surfaces a bug that's hard to diagnose from
  raw CloudWatch logs alone — that's the concrete signal this is now worth the
  investment, not a calendar date.

### 7. Terraform-drift reconciliation (`terraform import` for anything manual)

- **Why deferred:** not currently applicable — every resource so far has gone
  through Terraform (the Tuesday-checkpoint manual-fallback path was never
  triggered), so there's no drift to reconcile yet. Kept on this list only in
  case that changes.

### 8. Production AWS infrastructure (separate from this beta-staging push)

- **Why deferred:** the `production` branch created as part of the
  branch-strategy decision above is intentionally inert — no RDS/ECS/ALB/
  S3/CloudFront/ACM exists yet for `app.unifolio.in`. Standing that up is a
  full parallel replay of Phases 1-5 against a new `production` environment,
  which is out of scope for closing out the 5→30-user staging beta this doc
  otherwise tracks.
- **Revisit trigger:** a decision to move beyond staging beta toward a real
  production launch — needs its own scoping pass, not folded silently into
  this plan.

## Sequencing summary

1. ~~Branch-strategy decision (merge `feat/enhanced-ui` → `main`, create
   `production`)~~ — DONE 2026-09-10.
2. ADR-006 scheduler Terraform — handoff authored 2026-09-10, ready to
   dispatch to Codex, then reviewed, applied, run once to seed data.
3. CI/CD pipeline — authored, reviewed, first deploy verified end to end.
4. Phase 6 full `§17` validation pass — run against real, seeded data.
5. Beta opens.
6. Items 3-7 above stay parked until their stated revisit triggers fire —
   re-evaluate this doc when that happens, not on a fixed schedule. Item 8
   (production infra) is a distinct future decision, not part of this
   staging-beta close-out.
