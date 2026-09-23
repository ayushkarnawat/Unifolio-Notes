# Deployment

Everything runs in AWS. The shape below is the decided target, not a description of a
running production system — at the time of this record the migration runbook in
[`05-docs/how-to/migrate-sqlite-to-postgres.md`](../05-docs/how-to/migrate-sqlite-to-postgres.md)
has not been executed.

| Piece | Where it runs | Decision |
|---|---|---|
| Backend (FastAPI) | **ECS Express Mode**, Fargate-backed | [ADR-005](../03-decisions/ADR-005-deployment-architecture.md) |
| Frontend (React/Vite static build) | **S3 + CloudFront** | ADR-005 |
| Database | **RDS PostgreSQL**, single instance at MVP scale | [ADR-003](../03-decisions/ADR-003-primary-database-rds-postgresql.md) |
| Object storage | **S3**, private, scoped IAM | [ADR-004](../03-decisions/ADR-004-object-storage-scope-and-cas-pdf-retention.md) |
| Background jobs | **EventBridge Scheduler → ECS Fargate `RunTask`** | [ADR-006](../03-decisions/ADR-006-background-job-scheduling.md) |
| Secrets | **AWS Secrets Manager** — DB credentials and any API keys | ADR-005 |

## Notes that matter

**No read replica.** Deliberately premature at current volume. A single RDS instance is
the MVP target.

**AWS App Runner is not available.** It was the TDD's original proposal and stopped
accepting new customers on 2026-04-30. This is an availability fact, not a preference —
see ADR-005.

**The documented fallback is standard ECS Fargate**, with full manual configuration of
VPCs, ALBs, target groups, and security groups. Because Express Mode runs on the same
underlying compute, moving to it is a configuration change rather than a platform
migration. The named triggers: needing custom task placement, multi-container sidecars,
or blue-green deployment patterns Express Mode does not expose.

**Scheduled tasks share the application's container image and IAM context.** Jobs are
not a separately deployed service; they are the same codebase invoked as one-off tasks.

**One piece of setup is easy to forget and has a silent failure mode:** an EventBridge
rule watching for `SERVICE_TASK_PLACEMENT_FAILURE`. Fargate capacity transients can
cause a scheduled task to not start at all, with no error anywhere unless this is wired
up. Tracked in [`07-risks-and-debt.md`](../07-risks-and-debt.md).

**S3 is not default-safe.** Private-by-default bucket policy and scoped IAM roles are a
day-one setup task, not something inherited from the service.

## Related

- [Building blocks](building-blocks.md) — what is being deployed
- [Quality and constraints](quality-and-constraints.md) — the targets it must meet

## Update — 2026-09-22: this is now partly a description of a running system

The opening line above — "the decided target, not a description of a
running production system" — was accurate through 2026-09-16 and is left
unchanged above rather than rewritten. As of 2026-09-09, part of it is no
longer true: a real AWS account exists, `unifolio.in` was cut over from
GoDaddy to a Route 53-hosted zone (2026-09-07, mail records preserved), and
Terraform Phases 1-3 were applied to real infrastructure — a VPC/network, an
RDS PostgreSQL instance, an ECR repository, and an ECS Express Mode service.
Two follow-up problems (the service crash-looping with no application image
pushed yet; the database having no schema applied) were root-caused and
fixed the same session, and the result was checked four different ways
rather than trusted on a single health check.

**Still matching the "not yet applied" description, as of this batch's
material:** Phase 4 (S3 + CloudFront for the frontend) and Phase 5 (ACM
certificates, Route 53 records, and an HTTPS ALB listener) were authored and
reviewed but — per the runbook's own draft going into a 2026-09-11 session —
believed not yet applied; a `terraform plan` run during that session then
found the dispatcher's task definition, the HTTPS listener, both ACM certs,
the CloudFront distribution, and the Route 53 records already present in
Terraform state, refreshed rather than newly created, traced to a stray
plan file from earlier the same day. Only 2 EventBridge jobs and one IAM
policy change were genuinely outstanding at that point, and those applied
cleanly. Staging networking uses **fck-nat** (a self-hosted EC2 instance),
not a managed NAT Gateway, specifically to avoid the cost-approval step a
managed gateway would trigger.

Whether the 2026-09-11 runbook's own remaining steps (applying the three
pending Alembic migrations to real RDS, pushing a real application image,
rebuilding and deploying the frontend, running the Phase 6 smoke test,
standing up CI/CD) were carried out is not evidenced anywhere in this
batch's source material — treat as unconfirmed, not as done.

### Update evidence

- `08-evidence/documents/engineering-loop/session.md`, 2026-09-07,
  2026-09-09 and 2026-09-11 sections
- `08-evidence/documents/engineering-loop/CLAUDE.md`, "Session State" section
- See also [ADR-005](../03-decisions/ADR-005-deployment-architecture.md),
  [ADR-006](../03-decisions/ADR-006-background-job-scheduling.md),
  [INV-010](../04-investigations/INV-010-aws-iam-key-pasted-in-chat-and-rotated.md),
  and [R-052](../07-risks-and-debt.md)
