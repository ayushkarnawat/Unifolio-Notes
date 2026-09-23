# Terraform Phases 1-3 applied to real AWS, two follow-up issues fixed same session, and a real IAM key is briefly exposed and rotated

## For stakeholders

The infrastructure decided on paper over the previous two years of design
work went live for the first time: a real network, database, container
registry, and web service now exist in AWS, not just in Terraform files.
Two problems surfaced immediately after the first apply — the running
service was crash-looping because no application image had been pushed
yet, and the database had no schema — both were root-caused and fixed in
the same session, with the result checked four different ways rather than
trusted on a single health check. Separately, during credential setup, a
real AWS access key was briefly exposed in plaintext and was rotated
before it could be misused; the full incident is recorded as its own
investigation rather than folded quietly into this entry.

## Technical detail

### Intended outcome

Apply the first three phases of the staging Terraform configuration
(network, database, container platform) to the AWS account created on
2026-09-07, and confirm the result actually works end to end.

### What actually happened

57 AWS resources were created via Terraform: a VPC, the `fck-nat`
self-hosted NAT instance, an SSM-accessible bastion host, a KMS customer
managed key, an RDS PostgreSQL 16 instance, an ECR repository, and an ECS
cluster/service/Application Load Balancer.

Two follow-up problems were found and fixed the same session, not left for
a later pass:

1. The ECS service was crash-looping because no application container
   image had ever been pushed to the new ECR repository. Fixed by
   building and pushing the image.
2. The RDS database had no schema — expected, since this was its first
   deployment — fixed via an SSM Session Manager port-forward through the
   bastion host, fetching the Terraform-generated database master
   credential from Secrets Manager, and running the migration chain
   directly against the tunnel. `alembic current` confirmed all 11
   migrations applied cleanly on the real RDS instance. **A real bug was
   hit and fixed while doing this**: the fetched database password
   contained shell metacharacters that a naive double-quoted shell string
   would silently mangle, producing a confusing authentication failure
   further downstream. Fixed by piping the credential through an
   environment variable instead of embedding it literally in a shell
   string — general lesson, not specific to this one password: never place
   a real secret value literally inside a double-quoted shell string.

The deployed result was verified four independent ways, not trusted from a
single health-check request, before being called working (exact checks
not itemised further in this batch's source material beyond that count).

**A separate incident, during the same session's credential setup**: a
real AWS IAM access key and secret were pasted into the chat/session
transcript in plaintext while running a local AWS CLI configuration
command, and the access key ID was also accidentally written into a file
about to be committed. GitHub's push protection blocked the push before it
reached the remote, which is what surfaced the exposure. The key was
deactivated and replaced in the IAM console, and the offending commit was
rewritten to remove the literal value before it was ever pushed — no
shared history was affected. Full incident record:
[INV-010](../04-investigations/INV-010-aws-iam-key-pasted-in-chat-and-rotated.md).

### Deviation (if any) — decision or response taken

The IAM key exposure was not a planned deviation but an incident response
carried out mid-session, recorded here and in its own investigation rather
than treated as a footnote.

Phase 4 (frontend S3+CloudFront Terraform) was authored and reviewed but
deliberately not applied this session. Phase 5 (ACM/Route 53/HTTPS
handoff documentation) was drafted but not dispatched. Both were sequenced
for a later session, not abandoned.

### Result

Real AWS infrastructure exists for the first time — the deployment target
described in [`06-architecture/deployment.md`](../06-architecture/deployment.md)
(previously "the decided target, not a description of a running
production system") is now partially a description of a real, running
system, though frontend hosting and HTTPS are not yet applied. See the
dated correction appended to that file. A single AWS access key was
exposed and rotated within the same session with no evidence it reached a
shared or public location.

### Related

- ADR-005 — deployment architecture
- ADR-003 — RDS PostgreSQL
- ADR-006 — background job scheduling (the EventBridge/ECS Fargate
  Terraform for this piece specifically remains not yet built, per the 2026-09-07
  "still open" note — job scripts themselves were already done)
- INV-010 — the IAM key exposure and rotation
- R-052 — Terraform state can silently drift ahead of documented status
  (this apply is the infrastructure R-052's own gap concerns)
- Evidence: `08-evidence/documents/engineering-loop/session.md` (2026-09-09
  section), `08-evidence/documents/engineering-loop/CLAUDE.md`
