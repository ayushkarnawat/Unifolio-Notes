# Handoff: adr006-scheduler-terraform

**Status:** DONE (2026-09-10) — reviewed, PASS, zero findings. Not yet applied.
**Parent plan:** `Docs/orchestration/adr006-background-jobs-handoff.md` (piece 1 — job
scripts — DONE 2026-09-03; this doc is piece 2, deliberately deferred there until an
AWS account/ECR/ECS cluster existed) · `Docs/orchestration/phase7-production-hardening-plan.md`
item 1 (pulled forward from Phase 7, ahead of the rest of it, per 2026-09-10 decision) ·
`AWS Readiness/aws-golive-readiness-report.md` §22 Phase 3's note: "ADR-006's background
jobs (once built) are scheduled via EventBridge Scheduler targeting this same ECS
cluster (`ecs:RunTask` against the existing task definition) — confirmed with the cloud
engineer 2026-09-08, no separate Lambda/compute target."
**Depends on:** Phases 1–5 all applied and live (confirmed). This task adds new resources
alongside the existing `infra/modules/backend`; it does not modify anything Phase 5 built.

## Task

Wire the 4 already-built job scripts (`backend/scripts/jobs/refresh_{nav_daily,
benchmark_daily,ter_monthly,aaum_quarterly}.py`) up to run automatically on a schedule
against the real staging ECS cluster, via EventBridge Scheduler → `ecs:RunTask`. Two
parts: (1) two small application-code fixes that are genuine blockers, found by reading
the current `Dockerfile`/`docker-entrypoint.sh` before writing this doc — without them
the scheduled tasks would fail immediately; (2) a new Terraform module.

**This is authoring only, same boundary as every prior phase — do not run `terraform
apply`, and do not build/push a new Docker image.** Both are separate manual steps
after this is reviewed (see the implementation prompt's manual-steps section).

### Part 1 — two prerequisite code fixes (not infra, but required first)

1. **`backend/Dockerfile`** does not copy `scripts/` into the image at all — only
   `COPY app ./app`. Add `COPY scripts ./scripts` (alongside the existing `COPY app
   ./app` line) so `backend/scripts/jobs/*.py` actually exist inside the container.
   Without this, `ecs:RunTask` would fail with "no such file" the instant it tried to
   run any job script.

2. **`backend/docker-entrypoint.sh`** unconditionally `exec`s `uvicorn app.main:app
   --host 0.0.0.0 --port 8000` — it ignores any arguments ECS passes via a task
   definition's `command`. Change the final line so it runs the passed-in command if
   one was given, and falls back to the existing uvicorn default otherwise:
   ```sh
   if [ "$#" -gt 0 ]; then
     exec "$@"
   else
     exec uvicorn app.main:app --host 0.0.0.0 --port 8000
   fi
   ```
   Keep everything above that line (the `DATABASE_URL` construction/export) exactly as
   is — the job scripts need that same env var, built the same way, before they run;
   don't duplicate that logic into the job task definitions themselves.

Both fixes are small and additive — don't restructure the Dockerfile or entrypoint
beyond these two changes.

### Part 2 — new Terraform module: `infra/modules/scheduler`

**Design decision (already made, don't re-derive):** each of the 4 jobs gets its own
lightweight `aws_ecs_task_definition` (same image as the backend service, different
`command` baked directly into each task definition's container definition — e.g.
`["python", "scripts/jobs/refresh_nav_daily.py"]`). This is deliberate, not a
placeholder: the Terraform AWS provider's `aws_scheduler_schedule` resource's
`ecs_parameters` block has no container-command-override field, only
`task_definition_arn` — so a per-job task definition is the correct mechanism here, not
a corner cut. Four small, near-identical task definitions is the right shape (same
reasoning the original ADR-006 handoff gave for 4 similar job scripts over a shared
abstraction — don't build one for this either).

```
infra/modules/scheduler/          (NEW)
  main.tf
  variables.tf
  outputs.tf
```

**`main.tf` — required resources:**

- 4x `aws_ecs_task_definition` (`nav_daily`, `benchmark_daily`, `ter_monthly`,
  `aaum_quarterly`): `family = "${var.project}-${var.environment}-job-<name>"`,
  `requires_compatibilities = ["FARGATE"]`, `network_mode = "awsvpc"`, `cpu = "512"`,
  `memory = "1024"` (lighter than the backend service's 512/2048 — these are
  short-lived batch jobs, not a long-running web server), `execution_role_arn =
  var.ecs_task_execution_role_arn` (reuse the existing backend execution role — see
  variables below, don't create a second one; it already has ECR pull, CloudWatch Logs,
  and the RDS-secret-read/KMS-decrypt inline policy every job needs).
  Container definition per task: same image (`"${var.repository_url}:${var.image_tag}"`),
  same `environment`/`secrets` shape the backend module's task definition uses for DB
  connectivity (`DB_USERNAME`, `DB_HOST`, `DB_PORT`, `DB_NAME` as plain env vars,
  `DB_PASSWORD` from `${var.master_user_secret_arn}:password::` as a `secrets` entry —
  copy this shape from `infra/modules/backend/main.tf`, don't invent a different one),
  plus `command = ["python", "scripts/jobs/refresh_<name>.py"]`. No `portMappings`
  needed (these aren't network-reachable services). `logConfiguration` →
  `awslogs`, its own log group per job (see below).
- 4x `aws_cloudwatch_log_group` (one per job, `/ecs/${var.environment}-job-<name>`,
  `retention_in_days = 7` — matches the backend module's existing convention exactly,
  don't pick a different retention here).
- One `aws_iam_role` for EventBridge Scheduler to assume (`assume_role_policy` trusting
  `scheduler.amazonaws.com`), with an inline policy granting:
  - `ecs:RunTask`, resource-scoped to the 4 job task definition ARNs (not `*`).
  - `iam:PassRole` for `var.ecs_task_execution_role_arn`, with a
    `Condition { StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" } }`
    — the standard, least-privilege pattern for this, not a blanket PassRole.
- 4x `aws_scheduler_schedule` (`nav_daily`, `benchmark_daily`, `ter_monthly`,
  `aaum_quarterly`): `flexible_time_window { mode = "OFF" }` (required field, no
  flexibility needed for these), `schedule_expression_timezone = "Asia/Kolkata"` (so
  the cron expressions below can be written directly in IST rather than hand-computed
  UTC offsets — this resource attribute supports an explicit timezone, use it).
  Cadence — **defaults chosen here, easily changed later via the cron strings, not
  blocking on further input:**
  - `nav_daily` / `benchmark_daily`: `cron(0 6 * * ? *)` — every morning at 6:00 AM IST.
  - `ter_monthly`: `cron(0 6 1 * ? *)` — 6:00 AM IST on the 1st of every month.
  - `aaum_quarterly`: `cron(0 6 1 1,4,7,10 ? *)` — 6:00 AM IST on the 1st of
    Jan/Apr/Jul/Oct.
  Each schedule's `target` block: `arn = var.ecs_cluster_arn`, `role_arn =
  <the scheduler role above>.arn`, `ecs_parameters { task_definition_arn =
  <matching task definition>.arn, launch_type = "FARGATE", task_count = 1,
  network_configuration { subnets = var.private_app_subnet_ids, security_groups =
  [var.ecs_security_group_id], assign_public_ip = false } }` — same private-subnet,
  no-public-IP shape the backend ECS service already uses.

**`variables.tf`:** `project`, `environment`, `aws_region`, `ecs_cluster_arn`,
`repository_url`, `image_tag`, `ecs_task_execution_role_arn` (NEW — see
`infra/modules/backend/outputs.tf` change below), `master_user_secret_arn`,
`db_address`, `db_port`, `db_name`, `private_app_subnet_ids`, `ecs_security_group_id`.

**`outputs.tf`:** not required externally — leave empty or omit unless a genuinely
useful output surfaces while writing this (e.g. schedule ARNs, only if trivial).

### Part 3 — wiring changes to existing files

- **`infra/modules/backend/outputs.tf`:** add one new output,
  `ecs_task_execution_role_arn = aws_iam_role.ecs_task_execution.arn` — the scheduler
  module needs this to reuse the existing execution role rather than duplicating its
  IAM policies.
- **`infra/envs/staging/main.tf`:** add a new `module "scheduler"` block, sourced from
  `../../modules/scheduler`, wiring in the same values the existing `module "backend"`
  block already sources from `module.networking`/`module.ecr`/`module.database`/
  `module.security`, plus `ecs_cluster_arn = module.backend.<new output — see below>`
  and `ecs_task_execution_role_arn = module.backend.ecs_task_execution_role_arn`.
  **The backend module doesn't currently output its cluster ARN either** (only
  `alb_dns_name`, `alb_zone_id`, `ecs_cluster_name`, `ecs_service_name`) — add
  `ecs_cluster_arn = aws_ecs_cluster.this.arn` alongside the new execution-role output
  in the same `outputs.tf` edit, rather than deriving the ARN from the name string in
  the scheduler module.

## Constraints

- Keep changes scoped to: `backend/Dockerfile`, `backend/docker-entrypoint.sh`,
  `infra/modules/scheduler/` (new), `infra/modules/backend/outputs.tf` (2 new outputs
  only — don't touch anything else in that module), `infra/envs/staging/main.tf`
  (extended, not rewritten). Do not touch `infra/modules/networking`,
  `infra/modules/security`, `infra/modules/database`, `infra/modules/dns`,
  `infra/modules/frontend`, `infra/modules/ecr`, or `backend/app/`. Do not touch
  `frontend/`. Do not touch any doc.
- Reuse the existing ECS task execution role — do not create a second IAM role for the
  job tasks beyond the one new scheduler-assume role described above.
- Four small, near-identical task definitions/schedules is the intended design, not a
  gap to abstract away — do not build a shared module/for_each-driven generator unless
  it turns out to be trivially simple; if it does turn out clean via `for_each` over a
  local map of job configs (name/command/cron), that's fine too — either shape is
  acceptable, don't agonize over it.

## Action safety

This is authoring only — you are not provisioning real AWS infrastructure and not
building/pushing a Docker image. Never run `terraform apply`, `terraform destroy`,
`docker build`, `docker push`, or any `aws ecs`/`aws scheduler` CLI command. You may run
`terraform fmt` and `terraform validate` freely. Skip `terraform plan` entirely.

## Default follow-through policy

Default to the most reasonable low-risk interpretation and keep going. Only stop and
ask if you hit an actual technical conflict with this doc's design (not a style
preference) — in particular, if `aws_scheduler_schedule`'s actual current schema in the
pinned provider version doesn't match what's described above (e.g. a field renamed),
adapt to the real schema and note the discrepancy in your report; don't guess further
than that without flagging it.
