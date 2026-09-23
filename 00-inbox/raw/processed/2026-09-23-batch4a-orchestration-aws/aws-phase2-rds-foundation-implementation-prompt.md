# Implementation session prompt — AWS Phase 2 RDS foundation

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
branch `feat/enhanced-ui`. Author the Terraform for the staging RDS Postgres
instance: a new `infra/modules/database` module, wired into the existing
`infra/envs/staging` root module alongside the already-reviewed Phase 1
networking/security modules.

Full spec, exact instance settings, and every resource-level decision already
made: `Docs/orchestration/aws-phase2-rds-foundation-handoff.md`. Read it in
full before writing any code — this prompt does not restate its contents, it
points at the single source of truth both sides re-read.

Also read `AWS Readiness/aws-golive-readiness-report.md` §11, §19, and §22
Phase 2 for the reasoning behind the decisions the handoff doc encodes, and
skim `infra/envs/staging/main.tf` and `infra/modules/networking/outputs.tf` /
`infra/modules/security/outputs.tf` so the new database module's inputs line
up exactly with what Phase 1 already exposes — don't guess output names.
</task>

<action_safety>
This is authoring only — you are not provisioning real AWS infrastructure.
Never run `terraform apply` or `terraform destroy`. This holds even if AWS
credentials happen to be configured in your environment. You may run
`terraform fmt` and `terraform validate` freely — neither needs real
credentials or touches the account. Skip `terraform plan` entirely for this
dispatch — the Phase 1 resources this module depends on may already be real
if the account owner has applied them since the last session, so a `plan`
here carries more risk of touching real state than Phase 1's did.

Keep changes scoped to `infra/modules/database` (new) and
`infra/envs/staging/main.tf` (extended, not rewritten). Do not modify
`infra/modules/networking` or `infra/modules/security` — those are done and
already reviewed. Do not touch `backend/`, `AWS Readiness/aws-golive-readiness-report.md`,
the Migration Plan doc, or any other doc — if something looks wrong, report
it back instead of editing it. Do not run `alembic upgrade head` or attempt
any database migration/partitioning work — this dispatch only authors
Terraform, it does not touch application code or a live database. Do not
start Phase 3 (ECS/backend, Secrets Manager wiring, the ECS task execution
role's IAM policy) even if it looks like a natural next step.
</action_safety>

<default_follow_through_policy>
Default to the most reasonable low-risk interpretation and keep going — e.g.
look up the current latest 16.x RDS engine version yourself via an
`aws_rds_engine_version` data source rather than asking or hardcoding a
guess. Only stop and ask if you hit an actual technical conflict with the
handoff doc's design or with what Phase 1 already exposes as module outputs
(not a style preference), per the handoff doc's own "Open questions" section.
</default_follow_through_policy>

<completeness_contract>
Resolve the full Phase 2 scope from the handoff doc before stopping: the DB
subnet group, the `aws_db_instance` with every setting the handoff doc lists
(engine version via data source lookup, `db.t4g.small`, single-AZ, gp3 with
storage autoscaling, KMS-encrypted with the Phase 1 CMK, private/not-publicly-
accessible, correct security group, 3-day backup retention,
`manage_master_user_password = true`, staging-appropriate deletion/snapshot/
apply-immediately settings), all four listed outputs, and the `envs/staging`
wiring that passes the Phase 1 KMS key ARN / subnet IDs / security group ID
into the new module. Don't stop after just the resource block without the
outputs and the root-module wiring.
</completeness_contract>

<verification_loop>
Run `terraform fmt -recursive` and `terraform validate` against the new
`modules/database` and against `envs/staging` before finalizing. If validate
fails, fix and re-check — don't report syntax errors as "done, just needs
review." Note in your final report which checks you ran and their results.
</verification_loop>

<compact_output_contract>
When done, report back compactly: what you built (directory tree is enough,
don't paste every file), the engine version you resolved and how, the exact
`terraform fmt`/`validate` results, and anything from the handoff doc's "Open
questions" section you had to resolve yourself vs. anything you're flagging
back unresolved. Do not run or offer to run a self-review — that step happens
separately, on the Claude Code side, after this report is relayed back.
</compact_output_contract>
