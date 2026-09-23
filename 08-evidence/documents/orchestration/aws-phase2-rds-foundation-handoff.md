# Handoff: aws-phase2-rds-foundation

**Status:** DONE — reviewed 2026-09-08, PASS zero findings, see `delegation-log.md`.
**Parent plan:** `AWS Readiness/aws-golive-readiness-report.md` §9 (Terraform strategy), §11 (KMS), §19 (resolved decisions), §22 Phase 2 (Database)

## Task

Author (do not apply) the Terraform for the staging RDS Postgres instance: a new
`infra/modules/database` module, wired into `infra/envs/staging` alongside the
Phase 1 networking/security modules already merged (`826cfb4`).

**This is authoring only.** Same boundary as Phase 1 — see Constraints.

**Explicitly out of scope, even though §22 Phase 2 lists them as part of "Phase 2"
in the readiness report:** running `alembic upgrade head` against the real RDS
instance, and verifying the `transactions`/`nav_history` partitioning actually
applied. Both require a live, applied RDS instance and bastion access, which
don't exist yet after an authoring-only dispatch — those are manual follow-up
steps for the account owner once Phase 2's Terraform is actually applied. Do not
attempt to run Alembic against anything in this dispatch.

### Directory layout to add

```
infra/
  modules/
    database/
      main.tf        (DB subnet group, aws_db_instance)
      variables.tf
      outputs.tf      (endpoint, port, db name, master secret ARN)
  envs/
    staging/
      main.tf         (add a `module "database"` block, wire its inputs from
                        the existing networking/security module outputs)
```

Don't touch anything under `infra/modules/networking` or `infra/modules/security`
— Phase 1 is done and reviewed; this dispatch only adds the database module and
extends `envs/staging/main.tf`.

### RDS instance

All of the following are already-resolved decisions (§19, §22 Phase 2) — implement
them as given, don't re-derive or second-guess:

- Engine: PostgreSQL, major version 16 (matches the project's `postgres:16-alpine`
  Docker image and CI service container — see `docker-compose.yml`, `.github/workflows/ci.yml`).
  Look up the current latest available 16.x engine version via an `aws_rds_engine_version`
  data source (`preferred_versions`, latest) rather than hardcoding a minor version
  that may already be stale — same reasoning as Phase 1's `aws_ami` lookup pattern,
  don't repeat that mistake by guessing a fixed string here.
- Instance class: `db.t4g.small`. Single instance, `multi_az = false` (§19 — resizable
  later, not a hard commitment).
- Storage: `gp3`, `allocated_storage = 20`, `max_allocated_storage = 100` (this is what
  turns on RDS storage autoscaling — per §19's "storage autoscaling enabled").
- `storage_encrypted = true`, `kms_key_id` = the Phase 1 customer-managed KMS key's ARN
  (`module.security.kms_key_arn` — **not** the default `aws/rds` key, per §11). This is
  why the database module needs the KMS key ARN as an input variable.
- `publicly_accessible = false`. Private subnet only — use the Phase 1 private data
  subnets (`module.networking.private_data_subnet_ids`) for the DB subnet group.
- `vpc_security_group_ids` = the Phase 1 RDS security group (`module.networking.rds_security_group_id`)
  — that SG already has the correct ingress rules from ECS/bastion; don't create a new one.
- `backup_retention_period = 3` (§19 — resolved for staging; production needs a real
  7–35 day/PITR answer later, deferred to Phase 7, not this dispatch's concern).
  `backup_window` and `maintenance_window` can use sane defaults (stagger them so they
  don't overlap) — pick reasonable off-peak UTC times and say what you picked.
- `manage_master_user_password = true` (§19/§11 — RDS/Secrets Manager generates and
  owns the credential; Terraform state never contains a plaintext password). Master
  username: `unifolio` (matches the existing `TEST_DATABASE_URL` convention in
  `backend/.env.example`). DB name: `unifolio`.
- `deletion_protection = false` and `skip_final_snapshot = true` — staging-only choice,
  makes teardown/rebuild cheap during iteration; this would be the wrong call for
  production (Phase 7 territory, not now).
- `apply_immediately = true` — staging doesn't need to wait for a maintenance window
  for Terraform-driven changes to take effect.
- No custom `aws_db_parameter_group` — the default family parameter group is fine for
  staging; don't add one speculatively.

### Outputs (`modules/database/outputs.tf`)

Phase 3 (backend/Secrets Manager wiring) needs these as module outputs, surfaced
through `envs/staging/main.tf` the same way Phase 1's networking/security outputs
already are:

- `db_endpoint` (host:port) and `db_address` (host only)
- `db_port`
- `db_name`
- `master_user_secret_arn` — the Secrets Manager secret ARN RDS creates automatically
  when `manage_master_user_password = true` (`aws_db_instance.this.master_user_secret[0].secret_arn`).
  Phase 3 needs this to grant the ECS task execution role `kms:Decrypt` on the Phase 1
  CMK and read access to this specific secret — don't build that IAM policy now, it's
  Phase 3's own task-role module, same boundary as Phase 1's KMS section.

### Tagging and naming

Same convention as Phase 1 (§9): `Environment = "staging"`, `Project = "unifolio"`
tags (already applied account-wide via `envs/staging/providers.tf`'s `default_tags`
— don't redeclare them per-resource unless a resource type doesn't support
`default_tags` inheritance), `staging-` name prefix (e.g. `staging-rds`,
`staging-rds-subnet-group`).

## Constraints

- **Never run `terraform apply` or `terraform destroy`.** Same boundary as Phase 1
  — see `AWS Readiness/aws-golive-readiness-report.md` §20. Applies even if AWS
  credentials happen to be configured in your environment.
- You may and should run `terraform fmt` and `terraform validate` (per module and
  for the full `envs/staging` root) to confirm syntax. Do not run `terraform plan`
  unless you've confirmed no real AWS credentials are configured — same caution as
  Phase 1, and this dispatch is riskier to `plan` against by mistake since the
  Phase 1 resources it depends on might already exist for real if the account owner
  has applied Phase 1 in the meantime; if in doubt, skip `plan` entirely.
- Do not modify `infra/modules/networking` or `infra/modules/security` — only add
  `infra/modules/database` and extend `infra/envs/staging/main.tf`'s existing file.
- Do not touch `AWS Readiness/aws-golive-readiness-report.md`, the Migration Plan,
  or any other doc — code-only dispatch. Report anything that looks wrong back to
  the reviewer instead of editing docs yourself.
- Do not touch anything under `backend/` — the SQLAlchemy pool sizing note in §19's
  RDS row (`pool_size=10, max_overflow=20`) is an application-code change for a
  separate Phase 3 dispatch, not Terraform, not this task.
- Do not run `alembic upgrade head` or attempt any partitioning verification — see
  "Task" above, both require a live applied instance this dispatch does not create.
- Scope is Phase 2 only. Do not start Phase 3 (ECS/backend, Secrets Manager wiring,
  the ECS task execution role's KMS/Secrets Manager IAM policy).

## Approaches considered and rejected

- **A custom parameter group tuned for the workload:** rejected for staging — the
  default family parameter group is sufficient at this stage; revisit only if a real
  performance problem shows up under actual traffic (Phase 7 territory, not a
  speculative Phase 2 addition).
- **Multi-AZ RDS:** rejected — §19 explicitly resolved single-AZ for staging,
  matching the already-accepted single-AZ fck-nat trade-off from Phase 1. Don't
  "improve" this into Multi-AZ; if you think it's actually warranted, say so back to
  the reviewer rather than silently building it.
- **A literal master password variable instead of `manage_master_user_password`:**
  rejected — §11/§19 already decided this specifically to keep the plaintext
  password out of Terraform state entirely; don't reintroduce it.

## Open questions

- The exact current latest 16.x RDS engine version isn't known as of this handoff's
  writing — resolve via the `aws_rds_engine_version` data source lookup described
  above, not a hardcoded guess.
- If you find a genuine technical conflict between this spec and the existing Phase 1
  module outputs (e.g. a naming mismatch, a missing output Phase 2 needs that Phase 1
  didn't expose), stop and flag it back to the reviewer rather than silently
  papering over it or editing Phase 1's modules to fix it yourself.
