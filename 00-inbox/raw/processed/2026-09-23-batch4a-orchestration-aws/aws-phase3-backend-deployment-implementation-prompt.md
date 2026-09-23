# Implementation session prompt — AWS Phase 3 backend deployment

Paste everything below this line into your Codex session (`codex` CLI or the
Codex app) to start this task. This is a user-run dispatch — not run through
Claude Code's own Agent tool — per this project's established pattern (see
`Docs/orchestration/delegation-log.md`'s `worker=codex (user-run, direct
CLI/app — not Agent-dispatched)` entries). Do not self-review when done —
report back what you did and stop; a separate adversarial review pass runs
afterward, driven by the user relaying your output back into the main Claude
Code session.

---

<task>
Repo: Unifolio (mutual fund portfolio tracking platform, MF-only MVP),
branch `feat/enhanced-ui`. Author the Terraform for the staging ECS Fargate
backend deployment (ECR repository, ECS cluster/task definition/service, an
HTTP-only ALB, IAM, CloudWatch logging) plus one small Docker change (an
entrypoint script) that lets the container assemble `DATABASE_URL` from
RDS-managed pieces without Terraform ever touching the plaintext password.

Full spec, exact resource settings, and the reasoning behind the
password-handling design (a real conflict with Phase 2's own security goal
that was explicitly discussed and resolved with the user before this
dispatch was written): `Docs/orchestration/aws-phase3-backend-deployment-handoff.md`.
Read it in full, especially the "Secrets design" section, before writing any
code — this prompt does not restate its contents.

Also read `AWS Readiness/aws-golive-readiness-report.md` §11, §19, and §22
Phase 3, and `AWS Readiness/aws-golive-launch-blockers.md`'s single-task/
no-autoscaling section, for the reasoning behind decisions the handoff doc
encodes. Skim `infra/envs/staging/main.tf` and the `outputs.tf` files in
`infra/modules/networking`, `infra/modules/security`, and
`infra/modules/database` so the new modules' inputs line up exactly with
what Phases 1 and 2 already expose — don't guess output names.
</task>

<action_safety>
This is authoring only — you are not provisioning real AWS infrastructure
and not publishing a container image. Never run `terraform apply`,
`terraform destroy`, `docker build`, `docker push`, or any `aws ecr` CLI
command. This holds even if AWS/Docker credentials happen to be configured
in your environment. You may run `terraform fmt` and `terraform validate`
freely. Skip `terraform plan` entirely for this dispatch — Phase 1/2
resources this depends on may already be real if the account owner has
applied them since the last session.

Keep Terraform changes scoped to `infra/modules/ecr` (new),
`infra/modules/backend` (new), and `infra/envs/staging/main.tf` (extended,
not rewritten). Do not modify `infra/modules/networking`,
`infra/modules/security`, or `infra/modules/database` — those are done and
already reviewed. Under `backend/`, touch only `backend/Dockerfile` (one
edit: add the entrypoint) and the new `backend/docker-entrypoint.sh` — do
not touch `backend/app/**`, any test file, or `requirements.txt`. Do not
touch any doc. Do not start Phase 4 (frontend/S3/CloudFront) or Phase 5
(ACM/HTTPS/real domains) — no ACM certificate, no HTTPS listener, no Route
53 records here.
</action_safety>

<default_follow_through_policy>
Default to the most reasonable low-risk interpretation and keep going. Only
stop and ask if you hit an actual technical conflict with the handoff doc's
design or with what Phases 1/2 already expose as module outputs (not a
style preference), per the handoff doc's own "Open questions" section.
</default_follow_through_policy>

<completeness_contract>
Resolve the full Phase 3 scope from the handoff doc before stopping: the ECR
repository with scan-on-push and an untagged-image lifecycle policy; the ECS
cluster, CloudWatch log group, IAM execution role with the exact scoped
Secrets Manager + KMS grants described (not `*`-scoped, not
`kms:GenerateDataKey*`); the task definition with the full environment/secrets
wiring from "Secrets design"; the ECS service with `desired_count = 1`, the
specific `deployment_maximum_percent`/`deployment_minimum_healthy_percent`
stop-then-start values (with the required comment citing the launch-blockers
doc), and explicitly no autoscaling resources at all; the ALB/target
group/HTTP listener; all three listed outputs; the `envs/staging` wiring;
and the Dockerfile + entrypoint script with the password URL-encoding step.
Don't stop after just the Terraform without the Docker-side entrypoint
script, or vice versa.
</completeness_contract>

<verification_loop>
Run `terraform fmt -recursive` and `terraform validate` against the new
`modules/ecr`, `modules/backend`, and against `envs/staging` before
finalizing. If validate fails, fix and re-check. Also sanity-check the
entrypoint script's syntax (e.g. `sh -n backend/docker-entrypoint.sh`) since
it can't be run for real without a built image and a live database. Note in
your final report which checks you ran and their results.
</verification_loop>

<compact_output_contract>
When done, report back compactly: what you built (directory tree is enough,
don't paste every file), the exact IAM policy scoping you used for the
execution role, the exact `terraform fmt`/`validate` and `sh -n` results,
and anything from the handoff doc's "Open questions" section you had to
resolve yourself vs. anything you're flagging back unresolved. Do not run or
offer to run a self-review — that step happens separately, on the Claude
Code side, after this report is relayed back.
</compact_output_contract>
