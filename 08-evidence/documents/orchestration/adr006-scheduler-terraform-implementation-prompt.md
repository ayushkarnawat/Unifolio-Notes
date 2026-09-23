# Implementation session prompt — ADR-006 EventBridge Scheduler + ECS Fargate

Paste everything below this line into your Codex session (`codex` CLI or the
Codex app) to start this task. This is a user-run dispatch — not run through
Claude Code's own Agent tool — per this project's established pattern (see
`Docs/orchestration/delegation-log.md`'s `worker=codex (user-run, direct
CLI/app — not Agent-dispatched)` entries). Do not self-review when done —
report back what you did and stop; a separate adversarial review pass runs
afterward, driven by the user relaying your output back into the main Claude
Code session.

**Only start this if Phase 5 (`infra/modules/dns`) has already been applied**
— confirmed live: `staging.unifolio.in` / `staging-api.unifolio.in` both
resolve over HTTPS. This task adds new resources alongside the existing
`infra/modules/backend`; it does not modify anything Phase 5 built.

## Manual steps for you, before and after Codex's part (not for Codex)

**Before dispatching this prompt:** none beyond Phase 5 already being live —
no local setup needed.

**After Codex reports back and the Claude Code review passes (Status moves
to `DONE`):**

1. Rebuild and push the backend image with the two Dockerfile/entrypoint
   fixes baked in:
   ```
   cd backend
   aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin $(terraform -chdir=../infra/envs/staging output -raw ecr_repository_url | cut -d/ -f1)
   docker build -t $(terraform -chdir=../infra/envs/staging output -raw ecr_repository_url):latest .
   docker push $(terraform -chdir=../infra/envs/staging output -raw ecr_repository_url):latest
   ```
2. `cd infra/envs/staging && terraform plan -out=tfplan`. Expect: new
   resources only in a new `module.scheduler` (4 task definitions, 4 log
   groups, 1 IAM role + inline policy, 4 schedules), plus 2 new outputs on
   `module.backend` (no changes to any existing backend resource). If the
   plan shows anything destroyed/recreated on the existing ALB, ECS service,
   or CloudFront distribution — stop and paste the plan output back here
   before applying.
3. `terraform apply "tfplan"`.
4. Force the existing backend ECS service to pick up the new image (it
   still needs the Dockerfile fixes even though it doesn't run job
   scripts itself):
   ```
   aws ecs update-service --cluster $(terraform -chdir=infra/envs/staging output -raw ecs_cluster_name) --service $(terraform -chdir=infra/envs/staging output -raw ecs_service_name) --force-new-deployment
   ```
5. Seed real data immediately rather than waiting for tomorrow's 6 AM IST
   schedule — run each job once manually:
   ```
   for job in nav_daily benchmark_daily ter_monthly aaum_quarterly; do
     aws scheduler get-schedule --name <schedule-name-for-$job> --group-name default \
       | jq -r '.target.EcsParameters, .target.RoleArn' # confirm target before running
     aws ecs run-task --cluster <cluster-name> --task-definition <task-def-family-for-$job> \
       --launch-type FARGATE --network-configuration "awsvpcConfiguration={subnets=[...],securityGroups=[...],assignPublicIp=DISABLED}"
   done
   ```
   (Fill in the exact task definition families/subnet/security-group values
   from the `terraform apply` output or `terraform show` — Codex's report
   should name the exact resource names/ARNs to use here.)
6. Watch CloudWatch Logs (`/ecs/staging-job-nav_daily` etc.) for each
   one-off run to confirm it completes without error, then reload
   `https://staging.unifolio.in`'s analytics dashboard and confirm real
   data now renders (category rank, benchmark comparison, AAUM/TER).

---

<task>
Repo: Unifolio (mutual fund portfolio tracking platform, MF-only MVP),
branch `main`. Wire the 4 already-built background job scripts
(`backend/scripts/jobs/refresh_{nav_daily,benchmark_daily,ter_monthly,
aaum_quarterly}.py`) to run on an automatic schedule against the live
staging ECS cluster, via EventBridge Scheduler → `ecs:RunTask`. This needs
two small application-code fixes (`backend/Dockerfile`,
`backend/docker-entrypoint.sh`) plus a new `infra/modules/scheduler`
Terraform module (4 lightweight ECS task definitions, one per job, plus 4
`aws_scheduler_schedule` resources and a scheduler IAM role), wired into
`infra/envs/staging/main.tf`.

Full spec, exact resource settings, the design rationale for per-job task
definitions over a shared one, cron/timezone settings, and file-scope
constraints: read `Docs/orchestration/adr006-scheduler-terraform-handoff.md`
in full before writing any code — this prompt does not restate its
contents.

Also read the current `backend/Dockerfile`, `backend/docker-entrypoint.sh`,
`infra/modules/backend/main.tf`, `infra/modules/backend/outputs.tf`, and the
`module "backend"` block in `infra/envs/staging/main.tf` before editing
anything — you're extending live, already-reviewed infrastructure and a
live image build, not building from scratch, so match existing conventions
exactly (task definition shape, environment/secrets wiring, IAM policy
style, log group retention) rather than guessing.
</task>

<action_safety>
This is authoring only — you are not provisioning real AWS infrastructure
and not building/pushing a Docker image. Never run `terraform apply`,
`terraform destroy`, `docker build`, `docker push`, or any `aws ecs`/
`aws scheduler` CLI command. This holds even if AWS credentials happen to be
configured in your environment. You may run `terraform fmt` and
`terraform validate` freely. Skip `terraform plan` entirely.

Keep changes scoped to `backend/Dockerfile`, `backend/docker-entrypoint.sh`,
`infra/modules/scheduler` (new), `infra/modules/backend/outputs.tf` (2 new
outputs only), and `infra/envs/staging/main.tf` (extended, not rewritten).
Do not modify `infra/modules/networking`, `infra/modules/security`,
`infra/modules/database`, `infra/modules/dns`, `infra/modules/frontend`,
`infra/modules/ecr`, or anything under `backend/app/`. Do not touch
`frontend/`. Do not touch any doc.
</action_safety>

<default_follow_through_policy>
Default to the most reasonable low-risk interpretation and keep going. Only
stop and ask if you hit an actual technical conflict with the handoff doc's
design (not a style preference) — in particular, if `aws_scheduler_schedule`'s
actual current schema in the pinned provider version doesn't match what the
handoff doc describes (e.g. a field renamed), adapt to the real schema and
note the discrepancy in your report rather than guessing further.
</default_follow_through_policy>

<completeness_contract>
Resolve the full scope from the handoff doc before stopping: both Dockerfile/
entrypoint fixes; all 4 task definitions with correct execution role reuse,
environment/secrets wiring matching the existing backend task definition's
shape, and per-job `command`; all 4 log groups; the scheduler IAM role with
scoped `ecs:RunTask` and conditioned `iam:PassRole` (not a blanket grant);
all 4 `aws_scheduler_schedule` resources with the specified cron expressions
and `Asia/Kolkata` timezone; the 2 new outputs on
`infra/modules/backend/outputs.tf` (execution role ARN, cluster ARN); and
the new `module "scheduler"` block in `infra/envs/staging/main.tf` wired
correctly to both the new backend outputs and the existing networking/
database/ECR module outputs. Flag in your report (don't silently skip) if
you deviated from the handoff doc's per-job-task-definition approach or its
IAM scoping.
</completeness_contract>

<verification_loop>
Run `terraform fmt -recursive` and `terraform validate` against the new
`modules/scheduler`, the modified `modules/backend`, and `envs/staging`
before finalizing. If validate fails, fix and re-check.
</verification_loop>

<compact_output_contract>
When done, report back compactly: what you built/changed (directory tree
plus a one-line summary of each changed file's diff is enough, don't paste
full file contents), the exact task definition family names and schedule
names you chose (the user needs these for the one-off manual `aws ecs
run-task` seeding step), the exact `terraform fmt`/`validate` results, and
anything from the handoff doc you had to resolve yourself vs. anything
you're flagging back unresolved. Do not run or offer to run a self-review —
that step happens separately, on the Claude Code side, after this report is
relayed back.
</compact_output_contract>
