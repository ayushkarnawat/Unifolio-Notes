# Phase 4/5 (frontend hosting, HTTPS, real domains) are confirmed applied and live, background jobs get real scheduling infrastructure, and Phase 7 is rescoped around a small beta

## For stakeholders

The previous stage left it unconfirmed whether the frontend hosting and
HTTPS/domain work (Phases 4-5) had actually been applied to real AWS
infrastructure. Later material confirms they had: the staging site and its
API both resolve over HTTPS at their real subdomains. With a real,
reachable environment now confirmed, two things moved: the four scheduled
background jobs (market-data refreshes) that had only existed as code
since early September were wired up to actually run automatically, and the
remaining hardening work before opening the door to real users was
re-planned — not against the original ~1,000-user target, but against a
much smaller first beta of 5 to 30 people. Several items the original plan
called urgent were explicitly re-classified as not urgent yet, each with a
stated condition for revisiting. A trunk-based branching decision was also
made: the main line of development now deploys automatically to staging,
while a separate, deliberately inert branch is reserved for an eventual
real production environment.

## Technical detail

### Intended outcome

Confirm the state of the frontend/HTTPS infrastructure, get the four
already-written background job scripts actually running on a schedule
against the real staging environment, and produce a concrete, sequenced
plan for what still blocks opening a small beta.

### What actually happened

**Phase 4 and 5 confirmed applied and live.** The dispatch that authors
the EventBridge Scheduler Terraform (below) states as a precondition that
"Phases 1-5 [are] all applied and live (confirmed)," and its own
implementation prompt requires "Phase 5 (`infra/modules/dns`) has already
been applied — confirmed live: `staging.unifolio.in` /
`staging-api.unifolio.in` both resolve over HTTPS" before it can even be
dispatched. This corroborates, and narrows, the previous stage's
unconfirmed status for Phase 4 (private S3 + CloudFront via Origin Access
Control, with both 403 and 404 mapped to `/index.html` for client-side
routing) and Phase 5 (two ACM certificates — one in `us-east-1` for
CloudFront, one in `ap-south-1` for the ALB — an HTTPS listener with an
HTTP→HTTPS redirect, and Route 53 alias records for both subdomains). Both
phases' own handoff documents describe them as authored, reviewed, and
designed to be applied as in-place, additive changes to Phase 3/4's
already-live resources specifically so this sequence would work without a
resource being torn down and recreated. See the update appended to
[R-052](../07-risks-and-debt.md) and to
[`deployment.md`](../06-architecture/deployment.md).

**ADR-006's remaining piece — real job scheduling — is authored.** The
four job scripts (NAV daily, benchmark daily, TER monthly, AAUM quarterly)
had existed as tested code since 2026-09-03, deliberately deferred from
scheduling infrastructure until a real AWS account/ECS cluster existed.
With Phase 3's cluster live, a new `infra/modules/scheduler` module was
authored: one lightweight ECS task definition per job (reusing the
existing backend execution role rather than a new one), four
`aws_scheduler_schedule` resources on `Asia/Kolkata`-timezone cron
expressions, and a scheduler IAM role scoped to exactly those four task
definitions. Two small prerequisite code fixes were required first — the
Dockerfile did not copy `scripts/` into the image at all, and the
container entrypoint unconditionally ran the web server regardless of
what command ECS passed it — both found by reading the existing
Dockerfile/entrypoint before writing the scheduling spec, not discovered
later during implementation. Reviewed PASS, zero findings, 2026-09-10; not
yet confirmed applied by this batch's material. See the addendum on
[ADR-006](../03-decisions/ADR-006-background-job-scheduling.md).

**Branch strategy decided.** `main` becomes the trunk that auto-deploys to
`staging.unifolio.in`; a `production` branch was created from `main` (a
zero-conflict fast-forward, since `main` was a strict ancestor) and pushed,
but is deliberately inert — no CI/CD workflow targets it and no production
AWS infrastructure exists for it yet. A real production release stays an
explicit, gated action, not an automatic one.

**Phase 7 rescoped around a 5→30-user beta, not the original ~1,000 MAU
target.** The original readiness report's Phase 7 priorities were written
for a much larger user base; several items it flagged as elevated-priority
were re-examined against a beta ramping from 5 to roughly 30 users over
about 20 days, and explicitly deferred with a named condition for
revisiting rather than silently dropped:

- The in-process-cache/single-ECS-task constraint (already the current
  design — desired count 1, no autoscaling) is deferred until there is a
  concrete need for a second task.
- A real SMS/email OTP provider stays deferred — staging's stub mode is
  a deliberate decision for this audience, not a placeholder gap.
- The fck-nat → managed NAT Gateway upgrade stays deferred to production
  go-live or a concrete availability need.
- Structured logging/correlation IDs/an error-tracking SDK are deferred
  until a bug proves hard to diagnose from CloudWatch logs alone.
- Terraform-drift reconciliation is not currently applicable — no
  resource so far exists outside Terraform.
- Standing up real production AWS infrastructure (a full parallel replay
  of Phases 1-5 for `app.unifolio.in`) is out of scope for this staging
  beta close-out and needs its own future scoping pass.

Pulled **forward**, ahead of the rest of Phase 7, specifically because a
real beta cohort needs it: the EventBridge scheduler work above (an
analytics dashboard that shows real data, not a documented-as-acceptable
empty state), and next in sequence, a GitHub Actions CI/CD pipeline
(build/push/redeploy on merge to `main`, authenticated via GitHub OIDC to a
scoped IAM role rather than static access keys in GitHub Secrets —
explicitly chosen to avoid reintroducing the class of risk that caused the
2026-09-09 exposed-IAM-key incident). The database-migration step of that
pipeline (how `alembic upgrade head` runs automatically) is named as an
open design question, not yet resolved.

### Deviation (if any) — decision or response taken

The Phase 7 rescoping is itself the deviation worth naming: several items
the original readiness report treated as elevated-priority are explicitly
downgraded for this smaller beta scope, each with a stated reason and a
named condition for revisiting — not a silent narrowing of the bar.

### Result

Staging is confirmed reachable over HTTPS at its real domains; background
jobs have real (not yet confirmed applied) scheduling infrastructure; a
concrete, sequenced path to opening a small beta exists, with the larger
production-scale hardening work explicitly parked rather than either done
prematurely or silently dropped.

### Related

- ADR-006 — background job scheduling (both pieces now addressed — see its addenda)
- R-052 — Terraform state can drift ahead of documented status (this stage narrows that finding for Phase 4/5 specifically)
- R-058 — the in-process-cache/single-task architectural constraint (this stage's beta-scope reasoning for why it stays deferred)
- [2026-09-09](2026-09-09-terraform-applied-and-iam-key-incident.md) — the IAM key incident this stage's OIDC decision is designed to avoid repeating
- [2026-09-11](2026-09-11-aws-staging-deployment-runbook.md) — the runbook that, written the next day, found this same infrastructure already applied via a stray plan file — this stage is very likely the explanation for that, though no single document in this batch states the exact apply date
- Evidence: `08-evidence/documents/orchestration/aws-phase4-frontend-deployment-implementation-prompt.md`,
  `aws-phase5-networking-domains-handoff.md`, `aws-phase5-networking-domains-implementation-prompt.md`,
  `adr006-scheduler-terraform-handoff.md`, `adr006-scheduler-terraform-implementation-prompt.md`,
  `phase7-production-hardening-plan.md`

## Addendum — 2026-09-24 (batch 6b): Phase 4, Phase 5, and the scheduler/dispatcher apply are now directly confirmed, with real resource counts and outputs

This entry's own text corroborated Phase 4/5 only indirectly (via a
scheduler dispatch's stated precondition) and named ADR-006's scheduler
piece as "reviewed PASS... not yet confirmed applied by this batch's
material." A later-ingested raw source (`Move to Cloud.md`) closes both
gaps with first-hand `terraform apply` output from the same live session:

- **Phase 4** (S3 + CloudFront): applied cleanly, `5 added, 0 changed, 0
  destroyed`. Outputs: `s3_bucket_name =
  unifolio-staging-frontend-811364789032`, `cloudfront_distribution_id =
  E2SF2SFE80NW54`, `cloudfront_domain_name = d4vemdkml3wey.cloudfront.net`.
- **Phase 5** (ACM/DNS/ALB HTTPS): applied cleanly, `9 added, 2 changed, 0
  destroyed` (the "2 changed" was Terraform reconciling an S3 policy whose
  content already matched, not a real behavior change). Both ACM
  certificates confirmed `ISSUED`; both `staging.unifolio.in` and
  `staging-api.unifolio.in` confirmed resolving correctly.
- **The analytics-recompute dispatcher's scheduler wiring** (this entry's
  ADR-006 "remaining piece"): applied, `8 added, 2 changed, 1 destroyed`
  (the destroy was an expected backend ECS task-definition revision
  replacement, not data loss). Rollout confirmed `COMPLETED` via `aws ecs
  describe-services`, closing this entry's "not yet confirmed applied" note
  for ADR-006's second piece.

This is separate from, and does not resolve, the distinct migration-drift
finding recorded in
[INV-015](../04-investigations/INV-015-staging-rds-missing-analytics-migration.md)
and the apparent contradiction flagged on the
[2026-09-11 runbook entry](2026-09-11-aws-staging-deployment-runbook.md) —
those concern the database schema, not the Terraform-managed
infrastructure this addendum confirms.

### Addendum evidence

- `08-evidence/documents/Move to Cloud.md`
