# ADR-005: Deployment architecture — ECS Express Mode for the backend, S3 + CloudFront for the frontend

Status: Accepted
Date: 2026-07-22
Related: ADR-002 (what runs), ADR-003 (database), ADR-006 (scheduled jobs it enables),
`06-architecture/deployment.md`

## For stakeholders

The technical design originally assumed we would run the backend on AWS App Runner — a
service that takes your code and runs it without you managing servers. Formalising that
assumption turned up a fact that changed the answer: **AWS stopped accepting new App
Runner customers on 30 April 2026**, and now points people at ECS Express Mode instead.
Since we would be a new customer, App Runner is not something we can sign up for at all
— this stopped being a preference question and became an availability one. We are
therefore using ECS Express Mode, which AWS positions as the direct replacement and
which, usefully, can also run our scheduled background jobs natively — something App
Runner could not do at all. The website itself is served as static files from S3 behind
CloudFront, which was never in question. The one caveat worth knowing: ECS Express Mode
launched in November 2025, so it is newer and less battle-tested than what it replaces.

## Technical detail

### Context

The TDD needed something concrete to build against and proposed AWS App Runner (backend)
plus S3 + CloudFront (frontend) as a sensible, unformalised default. Formalising it
surfaced a material fact: **AWS App Runner stopped accepting new customers as of
2026-04-30** and is in maintenance mode, with AWS's own migration guidance pointing
existing customers to **ECS Express Mode** (launched at re:Invent, November 2025) as the
direct replacement. Unifolio would be a new customer, so the service cannot be
provisioned at all. This is ruled out by availability, not by comparison.

ECS Express Mode is described consistently across current sources as delivering App
Runner's original value proposition — single-resource deploy from source or container
image, automatic ALB/security-group/scaling provisioning, no manual cluster management —
while running on real ECS/Fargate underneath. That matters directly for ADR-006: unlike
App Runner, it natively supports scheduled and background task patterns without bolting
on a separate mechanism.

### Decision drivers

- Availability: App Runner cannot be provisioned by a new customer.
- ADR-006 needs a compute platform that supports scheduled tasks natively.
- Team size: operational surface must stay small.
- The fallback should be a configuration change, not a platform migration.

### Options considered

#### Option 1: Amazon ECS Express Mode, Fargate-backed (chosen)
**Advantages:** matches the App-Runner-level simplicity the team wanted without
building on a service closed to new customers; gives real ECS/Fargate capability —
background tasks, full IAM/VPC control when needed — from day one rather than requiring
a disruptive migration later, which is exactly what existing App Runner customers now
face; the fallback path (standard Fargate) runs on the same underlying compute, so
moving is a configuration change.
**Disadvantages:** newer (November 2025) and therefore less battle-tested, with fewer
community answers and less tooling maturity, though AWS positions it as its primary
strategic direction rather than an experiment; slightly more initial setup surface than
App Runner's "just point at a repo," though sources describe it as close to that.

#### Option 2: AWS App Runner (the original proposal)
**Advantages:** the simplest possible deploy experience; what the TDD assumed.
**Disadvantages:** **ruled out** — not available to new customers as of 2026-04-30 per
multiple independent sources including AWS's own service-availability announcements.
Also had no native scheduled-task support, which ADR-006 requires.

#### Option 3: Standard ECS Fargate with full manual configuration, as the primary choice
**Advantages:** maximum control — custom task definitions, blue-green deploys,
fine-grained IAM.
**Disadvantages:** requires manually configuring VPCs, ALBs, target groups, and
security groups — meaningfully more operational surface than a 2–3 person team should
take on before it is needed. **Kept as the documented fallback** if Express Mode's
abstraction proves limiting (custom task placement, multi-container sidecars, blue-green
patterns it does not expose).

#### Option 4: Elastic Beanstalk
**Advantages:** long-established, well-documented.
**Disadvantages:** not seriously considered — dated relative to ECS Express Mode's more
container-native abstraction, with no clear advantage for this workload shape.

### Decision

- **Backend:** Amazon **ECS Express Mode** (Fargate-backed). **Standard ECS Fargate**
  remains the documented fallback.
- **Frontend:** **S3 + CloudFront**, unchanged from the original proposal — no
  availability issue, and the standard low-effort pattern for a static React/Vite build.
- **Database:** RDS for PostgreSQL per ADR-003 — unaffected, noted here only to confirm
  no conflict. Single instance at MVP scale, no read replica (premature at current
  volume).
- **Secrets:** AWS Secrets Manager for DB credentials and any API keys.

### Consequences

**Positive:**
- Avoids building on a service that is functionally end-of-life for new adopters — a
  costly thing to discover after the fact.
- Real ECS/Fargate capability from day one; no disruptive migration later.
- The fallback is the same underlying compute, so it is a config change, not a platform
  move.

**Negative:**
- Newer platform, less battle-tested, thinner community tooling.
- Slightly more setup surface than App Runner's original simplicity.

**Neutral:**
- Worth a light check-in closer to implementation given how recently Express Mode
  launched — maturing docs and tooling would be good news, not a reason to revisit now.

### Validation

Validated when the backend deploys and serves traffic on Express Mode without needing
capabilities it does not expose. The named fallback trigger is concrete: needing custom
task placement, multi-container sidecars, or blue-green deployment patterns.

### Evidence

- Source document: `08-evidence/documents/ADR-Technical-Stack-Decisions.md` (ADR-005)
- Corroborating: `TDD-Unifolio.md`, Deployment Architecture section
- Research cited in the source, **not independently re-verified during this ingest**:
  AWS service-availability announcements (March–April 2026), Terraform AWS provider
  deprecation issue #47161, independent write-ups naming ECS Express Mode as the
  successor.
