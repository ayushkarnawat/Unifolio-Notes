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
