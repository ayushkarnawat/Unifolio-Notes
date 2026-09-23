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

## Update — 2026-09-23: Phases 4-5 confirmed applied and live; architecture detail filled in

The previous update above left Phase 4 (S3+CloudFront) and Phase 5
(ACM/DNS/HTTPS) as "unconfirmed" by that batch's material. Later-ingested
delegation material resolves this: a scheduler-Terraform dispatch dated
2026-09-10 states as a hard precondition that Phases 1-5 are "all applied
and live (confirmed)," and its implementation prompt confirms
`staging.unifolio.in` and `staging-api.unifolio.in` both resolve over
HTTPS. No document pins the exact apply date/command — only that it was
true by 2026-09-10 — so this is treated as confirmed-live-by-that-date,
not a fully reconstructed apply history. See the addenda on the
[2026-09-09](../02-journey/2026-09-09-terraform-applied-and-iam-key-incident.md)
and
[2026-09-11](../02-journey/2026-09-11-aws-staging-deployment-runbook.md)
journey entries and the dated update on [R-052](../07-risks-and-debt.md).

**Architecture detail authored 2026-09-08 through 2026-09-10, not previously recorded here:**

- **KMS.** A single customer-managed KMS key (not the default `aws/rds`
  key) encrypts both RDS storage and Secrets Manager, sharing one key for
  staging rather than splitting into two. Its key policy grants the AWS
  account root full `kms:*`, deliberately not a specific IAM role ARN —
  specific access (the ECS task execution role's `kms:Decrypt`/
  `kms:DescribeKey`) is delegated afterward via an ordinary IAM policy on
  that role, once it exists, avoiding a circular dependency between a
  Phase 1 resource and a Phase 3 role.
- **Database credentials never touch Terraform state.** RDS's
  `manage_master_user_password = true` generates and owns the master
  password entirely inside AWS Secrets Manager. The application needs one
  `DATABASE_URL` connection string, which created a real tension: composing
  that string in Terraform would put the plaintext password into state
  after all (and go stale on rotation). The chosen alternative: a new
  `backend/docker-entrypoint.sh` script fetches the password directly from
  the RDS-managed secret via ECS's native `secrets` block (`valueFrom`
  pointing at the secret ARN's `:password::` JSON-key selector) at
  container-start time, URL-encodes it (RDS-generated passwords can
  contain `:`, `#`, `%`, which would otherwise corrupt the connection
  string), assembles `DATABASE_URL`, and `exec`s uvicorn. Terraform only
  ever handles the secret's ARN, never its value.
- **Egress-all override on the ECS task and bastion security groups.**
  The original design scoped ECS task egress to 443-only and bastion
  egress to 5432-only; both were overridden 2026-09-08 to unrestricted
  (`0.0.0.0/0`, all ports) egress. The ALB and RDS security groups were
  not affected and keep their original scoped rules.
- **Stop-then-start deploys, no autoscaling — enforced in Terraform, not
  just policy.** `deployment_maximum_percent = 100`,
  `deployment_minimum_healthy_percent = 0` on the ECS service, and no
  `aws_appautoscaling_target`/`policy` resource exists at all — both are
  the direct Terraform implementation of the single-task/no-concurrent-
  tasks constraint (the app's in-process caches produce data-correctness
  bugs under 2+ concurrently-running tasks; see R-058).
- **CloudFront uses Origin Access Control (OAC), not the legacy OAI**, in
  front of a private S3 bucket, with both HTTP 403 and 404 responses
  mapped to `/index.html` — client-side-routed SPAs otherwise show a raw
  CloudFront error page on a deep-link refresh or an unknown path, and a
  private OAC-fronted bucket returns 403 (not 404) for a missing key,
  so both status codes need the same custom-error-response mapping.
- **Two ACM certificates, two regions, both required.** CloudFront only
  accepts a certificate issued in `us-east-1` regardless of the stack's
  primary region; the ALB's HTTPS listener needs one issued in
  `ap-south-1` (the stack's primary region). An HTTP→HTTPS redirect
  listener was added on the ALB alongside the HTTPS one.
- **Backend API domain resolved 2026-09-08**: a dedicated
  `staging-api.unifolio.in` subdomain routed directly to the ALB via a
  Route 53 alias record, not path-based CloudFront routing — the option
  this vault's 2026-09-07 entry had left open.

### Update evidence

- `08-evidence/documents/orchestration/aws-phase1-terraform-foundation-handoff.md`,
  `aws-phase2-rds-foundation-handoff.md`, `aws-phase3-backend-deployment-handoff.md`,
  `aws-phase4-frontend-deployment-handoff.md`, `aws-phase5-networking-domains-handoff.md`,
  `aws-phase5-networking-domains-implementation-prompt.md`,
  `adr006-scheduler-terraform-handoff.md`
