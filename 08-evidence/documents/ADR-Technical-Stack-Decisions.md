---
artifact: adr-set
version: "1.3"
created: 2026-07-22
updated: 2026-07-22
status: draft
product: Unifolio
---

# Architecture Decision Records: Core Technical Stack

Six related decisions, evaluated together since they interact. Two of the original four
(frontend framework, backend framework) propose changing something already built and
working — that tension is called out explicitly in each rather than glossed over, per
Nygard ADR discipline: an ADR should be honest about trade-offs, and "we already built
it the other way" is a real trade-off, not a reason to skip the analysis. The two added
later (ADR-005, ADR-006) formalize deployment and job-scheduling decisions the TDD
had initially only proposed.

---

# ADR-001: Frontend Application Architecture

## Status

**Accepted** (2026-07-22 — confirmed: React/Vite, no Next.js, no micro-frontends)

**Date:** 2026-07-22
**Deciders:** Ayush, Claude (PM partner)

## Amendment (2026-08-05)

This ADR's Context and "Positive Consequences" originally assumed the CAS Parser v2
Import Review screen was existing, in-progress React work that this decision would
preserve. That assumption was checked against the actual prototype during Phase 1 and
was **false**: the code at `CAS Parsers/mf-import/frontend` is vanilla TypeScript +
Vite — no React, no JSX, plain `.ts` page files driving the DOM directly. There was no
in-progress React Import Review screen to keep intact.

This does not change the **Decision** (React SPA via Vite, no Next.js, no
micro-frontends) — that call stands on its own architectural merits (team size, no
public/SEO surface, design-system consistency) independent of whether prior React work
existed. It only corrects the framing: Phase 1's Import Review UI (see
`Docs/superpowers/plans/`) was built as new React code, not a port of anything. The
"No rework of the CAS Parser v2 frontend already in progress" positive consequence
below should be read as moot rather than as a realized benefit — there was nothing to
avoid reworking.

## Context

The frontend for CAS Parser v2's Import Review screen was scoped as a Vite + React SPA
per the original build spec (`Planning-V1.MD`/`MF_CAS_Parsers.md`) — the actual
prototype frontend, however, was vanilla TypeScript, not React (see Amendment above).
The product proposal on the table now is Next.js, and separately, "pure React + MFE
(micro-frontend) components" as a structural pattern.

These are two different axes and need separating: (1) Next.js vs. a plain React SPA
(Vite) is a framework choice; (2) micro-frontends vs. a single modular application is an
*organizational* architecture choice, largely independent of which framework sits under
it. Both need their own answer.

**Relevant constraints:** Unifolio is a logged-in, authenticated dashboard product — no
public marketing pages or SEO-dependent content are in scope for this MVP (per the PRD
set, everything lives behind phone+OTP auth). The team is two founders plus one
incoming engineer — not a multi-team organization. The mid-August MVP target means
framework churn has a real, non-abstract cost right now, not a hypothetical one.

## Decision

**We will continue with a React SPA (Vite), not adopt Next.js, and will not adopt
micro-frontends.** Frontend stays a single modular React application with clear internal
component/feature boundaries (by module: Import Review, Onboarding, Main Dashboard,
Analytics Dashboard), not multiple independently-deployed applications.

This keeps the already-in-progress Import Review work intact rather than restarting it
on a different framework.

## Consequences

### Positive
- No rework of the CAS Parser v2 frontend already in progress.
- Simpler deployment (single build, single pipeline) — appropriate for a 2–3 person team,
  consistent with current industry guidance that micro-frontend overhead isn't justified
  below roughly 8–10 frontend developers.
- Vite's dev server and build times stay fast without Next.js's SSR/routing machinery,
  which this product doesn't need given there's no public/SEO surface.
- Simpler shared state and design-system consistency (Design Schema tokens) across
  the whole app — the exact problem multiple 2025–2026 case studies flag as materially
  harder under micro-frontends (shared theming, cross-cutting features spanning
  "modules" like the Fund Signal component appearing on both the Main Dashboard and
  Import Review).

### Negative
- Forgoes Next.js's built-in image optimization, file-based routing convenience, and
  easier path to server-side rendering if a future public-facing surface (marketing site,
  SEO-dependent content) is ever needed — would require a separate project/framework
  at that point rather than extending this one.
- No independent deploy/release cadence per module — a bug fix to Analytics Dashboard
  requires the same build/deploy pipeline as everything else. Acceptable at current team
  size; worth revisiting only if the team grows well past 10 frontend engineers.

### Neutral
- If a marketing/landing site is needed later, it can reasonably be a separate, small
  Next.js (or even static) site rather than folding into the authenticated app — that's a
  different product with different constraints (SEO matters there, doesn't here).

## Alternatives Considered

### Next.js
Strong general-purpose choice, but its core advantages (SSR/SSG for SEO, image
optimization for content-heavy public pages, file-based routing) target problems
Unifolio doesn't have in this MVP — everything is behind auth. Adopting it now means
rewriting in-progress work for benefits that don't apply yet. Worth reconsidering only if
a public, SEO-relevant surface enters scope.

### Pure React + Micro-Frontend Components
Research is consistent and current (multiple 2025–2026 sources, including documented
case studies of small teams adopting MFE "to prepare for scale" and reverting within
months): micro-frontends solve a *team-coordination* problem — independent teams
needing independent deploys — that doesn't exist at 2–3 people. The stated guidance
across sources is "start with a well-structured monolith, split later if organizational
scaling pain becomes the dominant bottleneck," which is exactly the situation here in
reverse (no scaling pain yet).

## References
- PRD-01: CAS Parser v2 (Import Review is the current in-progress frontend work)
- Design Schema: Unifolio (component-based tokens assume a single application)
- Research: monolith-vs-microfrontend team-size guidance (AlterSquare, DEV Community,
  Steve Kinney, GitNexa — 2025–2026 sources, consistent across all)

---

# ADR-002: Backend API Framework

## Status

**Accepted** (2026-07-22 — confirmed: FastAPI. Django was reconsidered specifically for
its data-storage/admin conveniences, but the final call was to keep FastAPI — flagging
this explicitly since it was a closer call in discussion than ADR-001; revisit if a specific
need for Django's admin tooling emerges, see Neutral consequence below)

**Date:** 2026-07-22
**Deciders:** Ayush, Claude (PM partner)

## Context

The backend is already substantially built on **FastAPI**: scaffold, `calc.py` (Decimal
math), SQLAlchemy models, the `casparser` wrapper, `mfapi.in` enrichment, and the
two-phase parse/confirm API routes are all complete per the current build tracker
(`MF_CAS_Parsers.md`). Only the frontend Import Review screen and README remain.

The product proposal on the table is Python Django (implicitly with Django REST
Framework for the API layer, given the product is API-first, not template-rendered).

**What Unifolio's backend actually is, shape-wise:** a pure API service — no server-
rendered HTML, no need for Django's template engine — consumed by a React SPA, with
async-friendly I/O-bound work (CAS parsing, external calls to `mfapi.in`, and per ADR-003/
ADR-004, AWS RDS and S3). This shape is closer to what current guidance identifies as
FastAPI's strength than Django's.

## Decision

**We will continue with FastAPI**, not migrate to Django. The already-built parser,
models, and API routes stay as-is; RDS/S3 integration (ADR-003, ADR-004) is added on
top of the existing FastAPI service rather than as part of a framework migration.

## Consequences

### Positive
- No rework of completed, tested backend logic (parser, Decimal-safe calc, two-phase
  import flow) — this is the single largest sunk-cost consideration in this whole ADR set,
  and it's a real one against the mid-August target, not just inertia.
- FastAPI's async model fits the actual workload: I/O-bound calls to `mfapi.in`, and (once
  ADR-003/004 land) to RDS and S3 — current framework guidance specifically flags
  FastAPI as the stronger fit for "async-heavy workloads" and "API-first" products,
  which is exactly Unifolio's shape.
- Lighter operational footprint than Django — no admin app, no template engine, no ORM
  layer beyond what's already chosen (SQLAlchemy) to carry along unused.

### Negative
- Forgoes Django's batteries-included ecosystem: built-in admin panel (would otherwise
  give a free internal ops/support tool for looking up user data, imports, etc.), built-in
  auth scaffolding, and Django REST Framework's more opinionated conventions, which
  can help a growing team stay consistent as more engineers join.
- FastAPI requires assembling more pieces individually (auth, background jobs, admin
  tooling) that Django would provide out of the box — a real cost if internal tooling needs
  grow faster than expected.

### Neutral
- Nothing prevents a small, separate internal Django or Django-admin-style tool later
  purely for internal ops (support/debugging dashboards) without migrating the
  user-facing API — this is a legitimate way to get Django's admin-panel convenience
  without touching the production API framework, worth keeping in mind rather than
  reopening this whole decision if an internal tooling need shows up.

## Alternatives Considered

### Django / Django REST Framework
The stronger choice when a product needs a full batteries-included platform (admin,
auth, templated pages) fast, or when the team explicitly values Django's conventions for
consistency as it scales. Neither applies as strongly here: no templated pages exist in
scope, and the team is currently too small for "framework conventions to keep many
engineers consistent" to be the binding constraint — the binding constraint right now is
shipping by mid-August without discarding working code. Current 2026 guidance
consistently frames the FastAPI-vs-Django choice as "MVP speed → Django, API-first/
async-heavy → FastAPI or hybrid" — and this MVP already has its API-first backend built.

### Hybrid (FastAPI for core API, Django for a future admin/internal tool)
Not rejected — flagged as a legitimate future option (see Neutral consequence above),
just not needed as part of this decision right now.

## References
- `MF_CAS_Parsers.md` (project knowledge) — current build-status tracker showing
  FastAPI backend substantially complete
- PRD-01: CAS Parser v2 — technical constraints already built against FastAPI/SQLAlchemy
- Research: FastAPI vs. Django 2026 guidance (Capital Numbers, Zestminds, Codism,
  DevelopersVoice — consistent "API-first/async → FastAPI, batteries-included/templated
  → Django" framing across sources)

---

# ADR-003: Primary Database — AWS RDS for PostgreSQL

## Status

**Accepted**

**Date:** 2026-07-22
**Deciders:** Ayush, Claude (PM partner)

## Context

The current prototype uses SQLite with `Numeric` column types, deliberately chosen to
be Postgres-portable — this was an explicit design decision from early in the build, not
an accident, anticipating exactly this migration. The product proposal (AWS RDS +
PostgreSQL) is not in tension with existing work — it's the intended next step.

**To state plainly, since this is the permanent home for the product's actual value:**
every user profile, every family/household member, every parsed holding, every
transaction, every import event, and every computed analytics result lives here,
indefinitely, from first import onward. A user uploads a CAS once and their portfolio is
there every time they open the app — no re-upload required to simply view data. Users
add more data over time (a new statement, a new family member) via the Ongoing Data
Addition capability below, which appends to this store rather than replacing anything.
This has been the plan since the schema was first made Postgres-portable; nothing in
this ADR set changes it.

**What needs deciding here is really the *timing and shape* of the migration** off
SQLite: at what point does SQLite stop being sufficient (single local prototype vs.
multi-user, deployed, needs real backups/durability), and does anything in the schema
(Decimal/Numeric handling, the JSON raw-parser-output field from PRD-01) need
adjustment for Postgres specifically.

## Decision

**We will use AWS RDS for PostgreSQL as the production database**, migrating off the
SQLite prototype once the backend is deployed beyond local development — practically,
this should happen before any real user data is being collected (i.e., before or at MVP
launch, not after). SQLite remains fine for continued local development in the meantime.

## Consequences

### Positive
- No schema redesign needed — `Numeric` types translate directly, and this was
  anticipated from the start.
- RDS gives managed backups, point-in-time recovery, and durability guarantees that
  matter the moment real user financial data is being stored — SQLite was always
  understood as a prototype choice, not a production one.
- Postgres's native JSON/JSONB support is a clean fit for PRD-01's requirement to
  persist full raw parser output for debugging (FR-4) — better than SQLite's more limited
  JSON handling.

### Negative
- RDS has an ongoing cost from day one of deployment, unlike SQLite (free, file-based) —
  a real budget line item to plan for, even at small scale.
- Adds one more piece of AWS infrastructure to configure and secure (VPC placement,
  credentials management, backup retention policy) before launch — this is real setup
  work, not zero-cost just because the decision itself is easy.

### Neutral
- Connection pooling (e.g., via PgBouncer or RDS Proxy) becomes a relevant
  consideration once FastAPI's async workers are talking to Postgres under real load —
  not needed at launch scale, but worth knowing this is a future tuning knob, not a
  launch blocker.

## Alternatives Considered

### Continue with SQLite in production
Rejected — fine for a single-developer prototype, not appropriate once real user
financial data and multi-user access are live; no meaningful case for this beyond local
dev.

### Self-managed PostgreSQL on EC2 (rather than RDS)
Rejected for this team's size — RDS's managed backups, patching, and failover remove
operational burden that a 2–3 person team shouldn't be carrying manually pre-launch.
Revisit only if AWS cost optimization becomes a priority at meaningfully larger scale.

## References
- PRD-01: CAS Parser v2 — `Numeric` column type constraint, JSON raw-parser-output
  requirement (FR-4)
- Prior build notes confirming SQLite was chosen as explicitly Postgres-portable

---

# ADR-004: Object Storage — AWS S3 (scoped)

## Status

**Accepted**

**Date:** 2026-07-22
**Deciders:** Ayush, Claude (PM partner)

## Context

**This ADR is about files, not about whether portfolio/user/family data persists.** That
distinction matters enough to state plainly: every holding, transaction, family member,
and user profile is structured, relational data — it belongs in AWS RDS/PostgreSQL
(ADR-003), permanently, from the moment it's first imported. A user uploads their CAS
once; the parsed result lives in Postgres from then on. They come back and see their
portfolio without re-uploading anything. They only upload again to *add* new data (a
new statement, a family member's CAS) — see the new Ongoing Data Addition
requirement below. None of that is what this ADR decides.

What this ADR actually scopes is: what, if anything, belongs in **S3 specifically** — an
object/blob store, suited to files and large cached datasets, not to the kind of relational,
queryable, joined data (a family's holdings across members, XIRR computed across a
transaction history) that Postgres is built for. Two candidates: (1) the raw uploaded CAS
PDF file itself, and (2) cached copies of public reference data (AMFI TER/AAUM, NSE
index history) and future generated exports.

On (1) — the raw PDF file — PRD-01 currently specifies it's deleted after parsing, not
retained anywhere (S3 or otherwise). Given the wealth-management-platform direction
being confirmed here, **whether to retain the original PDF long-term (in S3) is a real,
open product decision** — not something this ADR should silently resolve either way. See
Open Decision below.

## Decision

**We will use AWS S3** for: (1) cached copies of public reference data (AMFI TER/AAUM,
NSE index history, `mfapi.in` NAV snapshots) supporting PRD-04's analytics, and
(2) future generated user-facing exports (PDF/CSV statements), if and when that feature
is built.

**The original uploaded CAS PDF is not retained.** PRD-01's existing delete-after-parse
behavior stands, unchanged, as a final decision — not reopened. The parsed, structured
data (holdings, transactions, folios) is what persists in Postgres, permanently; the source
PDF itself is discarded once that data is extracted, keeping the amount of sensitive raw
data (unmasked PAN, original formatting) stored to the minimum the product actually
needs to function.

**None of this affects portfolio, transaction, family, or user data** — that's Postgres,
permanently, unconditionally, per ADR-003.

## Consequences

### Positive
- Gives PRD-04's data-source integrations (TER, AAUM, NSE index history) a durable,
  cheap cache layer, reducing repeated calls to AMFI/NSE and lowering the automation-
  frequency risk already flagged in those PRDs' Dependencies sections.
- Clean separation of concerns: Postgres for structured, queryable, permanent user data;
  S3 for files and reference-data caching. Each store does the job it's actually good at.

### Negative
- Requires explicit bucket policy and access controls to be set up correctly from day
  one (private by default, scoped IAM roles) — a real setup task, not a default-safe
  service out of the box.
- Adds a second piece of AWS infrastructure (alongside RDS) to configure and secure
  before launch.

### Neutral
- If this decision is ever revisited (e.g., a future feature genuinely requires the original
  document), that would need its own fresh product/security review, including a legal
  read on DPDP-Act implications — not something to casually reopen as an infrastructure
  afterthought.

## Decision: CAS PDF Is Not Retained

PRD-01's delete-after-parse rule (data extracted, source document discarded) stands as
final: **the original CAS PDF is not stored anywhere — not in S3, not elsewhere.** This
was weighed against retaining it (which would've enabled re-download and an audit
trail) and resolved in favor of deletion:

- Minimizes stored PII — the parsed, structured data is everything the product actually
  needs to function; the raw document (full PAN, original formatting) adds sensitive
  surface area without a corresponding product need.
- Cleaner compliance posture under India's DPDP Act — data-minimization principles
  favor not retaining more than necessary, and this avoids the legal-review overhead
  that retaining PAN-bearing documents would have required.
- Consistent with the product's actual value proposition: the platform's value is the
  structured portfolio data, analytics, and tracking — not document storage. A user who
  wants their original CAS can always re-request it from CAMS/KFintech directly.

This decision does not change anything about portfolio, transaction, family, or user
data — all of that persists permanently in Postgres regardless (ADR-003).

## Alternatives Considered

### No object storage (keep everything in RDS/Postgres)
Rejected — cached reference datasets (full NAV history across the scheme universe, TER
data) don't belong in the relational database's primary storage path at the volumes
PRD-04 implies; S3 (or a similar blob store) is the standard fit.

### Store CAS PDFs in S3 temporarily during processing (rather than local temp storage)
Considered, not adopted for v1 — local temp storage with guaranteed deletion is simpler
to reason about and audit than an S3 upload-then-delete cycle, and doesn't introduce a
network hop for a file that's supposed to be short-lived. This is separate from the Open
Decision above (temporary processing storage vs. permanent retention are different
questions) — revisit only if the processing architecture changes.

## References
- PRD-01: CAS Parser v2 — PDF deletion requirement (confirmed final), PAN-masking
  constraint
- PRD-04: MF Analytics Dashboard — TER/AAUM/NSE index data-source dependencies that
  benefit from a cache layer
- ADR-003: Primary Database — the actual, permanent home for all structured user data

---

# ADR-005: Deployment Architecture

## Status

**Accepted**

**Date:** 2026-07-22
**Deciders:** Ayush, Claude (PM partner)

## Context

The TDD needed *something* concrete to build against and initially proposed AWS App
Runner (backend) plus S3 + CloudFront (frontend) as a sensible, unformalized default.
Formalizing it properly surfaced a material fact that changes the recommendation:
**AWS App Runner stopped accepting new customers as of April 30, 2026** and is now in
maintenance mode, with AWS's own migration guidance pointing existing customers to
**ECS Express Mode** (launched at re:Invent, November 2025) as the direct replacement.
Since Unifolio would be a *new* App Runner customer, the service isn't available to
provision at all right now — this isn't a "which is better" choice anymore, it's ruled out
by availability.

ECS Express Mode is described consistently across current sources as delivering
App Runner's original value proposition (single-resource deploy from source or
container image, automatic ALB/security-group/scaling provisioning, no manual cluster
management) while running on real ECS/Fargate underneath — meaning, unlike App
Runner, it natively supports the background/scheduled task patterns ADR-006 needs,
without bolting on a separate mechanism.

## Decision

**Backend**: **Amazon ECS Express Mode** (Fargate-backed) — matches the original
App-Runner-level simplicity the team wanted, without building on a service that's
closed to new customers. **Standard ECS Fargate** (full manual configuration) remains
the documented fallback if Express Mode's abstraction proves limiting (e.g., needing
custom task placement, multi-container sidecars, or blue-green deployment patterns it
doesn't expose) — this mirrors the original App-Runner-to-Fargate fallback logic, just
one rung up the ladder since the top rung is no longer available.

**Frontend**: **S3 + CloudFront**, unchanged from the original proposal — this part had
no availability issue and remains the standard, low-effort pattern for a static React/Vite
build.

**Database**: RDS for PostgreSQL, per ADR-003 — unaffected by this decision, included
here only to confirm no conflict.

## Consequences

### Positive
- Avoids provisioning a service (App Runner) that's functionally end-of-life for new
  adopters — this would have been a costly mistake to discover after building against it.
- ECS Express Mode gives real ECS/Fargate capability (background tasks, full IAM/VPC
  control when needed) from day one, rather than needing a disruptive migration later
  the way existing App Runner customers are now facing.
- Fallback path (standard ECS Fargate) is the same underlying compute either way —
  moving from Express Mode to full Fargate control later is a configuration change, not a
  platform migration.

### Negative
- ECS Express Mode is newer (November 2025) than App Runner was — less battle-tested
  in the wild, fewer Stack Overflow answers and community tooling maturity at this
  point, though it's positioned as AWS's primary strategic direction, not an experiment.
- Slightly more initial setup surface than App Runner's original "just point at a repo"
  simplicity, though sources consistently describe it as close to that experience.

### Neutral
- Worth a light check-in closer to actual implementation time, given how recently
  Express Mode launched — if AWS documentation or tooling has matured further by
  then, that's good news, not a reason to revisit this decision now.

## Alternatives Considered

### AWS App Runner (original proposal)
Ruled out — not available to new customers as of April 30, 2026, per multiple
independent sources including AWS's own service-availability announcements. Not a
close call once this fact was established.

### Standard ECS Fargate (full manual configuration) as the primary choice, not fallback
Considered — gives maximum control (custom task definitions, blue-green deploys,
fine-grained IAM) but requires manually configuring VPCs, ALBs, target groups, and
security groups, which is meaningfully more operational surface than a 2–3 person team
should take on before it's needed. Kept as the documented fallback rather than the
starting point, consistent with the team-size reasoning already established in
ADR-001–003.

### Elastic Beanstalk
Not seriously considered — dated relative to ECS Express Mode's newer, more
container-native abstraction, and doesn't offer a clear advantage for this workload
shape.

## References
- ADR-002: Backend API Framework (FastAPI — this ADR decides where it runs, not what it is)
- ADR-006: Background Job Scheduling (depends on this ADR's compute choice)
- Research: AWS App Runner maintenance-mode announcements (AWS service-availability
  page, March–April 2026; Terraform AWS provider deprecation issue #47161; multiple
  independent technical write-ups confirming ECS Express Mode as the AWS-recommended
  successor, April 2026 sources)

---

# ADR-006: Background Job Scheduling

## Status

**Accepted**

**Date:** 2026-07-22
**Deciders:** Ayush, Claude (PM partner)

## Context

The TDD's Background Jobs section lists five jobs (NAV daily refresh, TER monthly, AAUM
quarterly, benchmark index daily, ARN resolution on-demand) that need a scheduling
mechanism. The original proposal — EventBridge Scheduler triggering ECS tasks or
Lambda — needed confirming as current, documented AWS practice rather than an
assumption, especially now that it's running on ECS Express Mode (ADR-005) rather than
whatever App Runner would have offered (which, notably, had no native scheduled-task
support at all — one more reason ADR-005's outcome matters here directly).

## Decision

**AWS EventBridge Scheduler triggering ECS Fargate `RunTask`**, for the four genuinely
periodic jobs (NAV, TER, AAUM, benchmark index refresh) — this is a documented,
current AWS pattern (AWS's own Serverless Land publishes a reference architecture for
exactly this combination), sharing the same FastAPI codebase's job modules as
one-off task invocations rather than a separately deployed scheduler service.

**ARN resolution stays on-demand, not scheduled** — triggered directly by the Import
Service when a new, previously-unseen ARN code appears (per PRD-03 FR-11a), invoked
as a synchronous or lightweight async call within that request path rather than through
EventBridge at all. Confirmed as correctly scoped in the original TDD — no change here.

## Consequences

### Positive
- No separate scheduling infrastructure beyond EventBridge (already an AWS-native,
  serverless, pay-per-use service) — consistent with the managed-service-first pattern
  from ADR-002/003/005.
- Running on ECS Express Mode (ADR-005) means these scheduled tasks share
  infrastructure and IAM context with the main application, rather than needing a
  separate Lambda deployment pipeline for jobs that are naturally container-shaped
  (they reuse the same Python codebase, dependencies, and DB connection logic as the
  main API).

### Negative
- Fargate task cold-start (container spin-up) adds latency to each scheduled job
  compared to a warm Lambda — irrelevant for daily/monthly/quarterly cadences, where a
  few seconds of startup time is noise, but worth knowing as a general trade-off.
- AWS's own support forums document occasional Fargate capacity-availability
  transients causing a scheduled task to silently not start in rare cases — mitigated by
  configuring a retry/alert path (e.g., an EventBridge rule watching for
  `SERVICE_TASK_PLACEMENT_FAILURE`), a known, documented pattern, not a novel
  problem to solve from scratch.

### Neutral
- Lambda remains a reasonable choice for genuinely short, lightweight jobs if any
  emerge later (e.g., if ARN resolution's on-demand call ever needed to move off the
  request path into an async trigger) — not needed for the four scheduled jobs as
  currently scoped, since none of them are lightweight enough to meaningfully benefit
  from Lambda's faster cold start over Fargate's.

## Alternatives Considered

### AWS Lambda for all five jobs
Considered — Lambda's per-invocation pricing and fast cold start suit short jobs well,
but NAV refresh (full scheme universe, thousands of schemes) and the historical
backfill work these jobs sometimes need to do risk running past Lambda's execution
time limits for anything beyond a simple daily incremental update. Fargate's no-duration-
limit model removes this as a future constraint without needing to re-architect a job
that outgrows Lambda's ceiling.

### A dedicated task queue (e.g., Celery/Redis) instead of EventBridge + Fargate
Not adopted — adds an entire additional piece of infrastructure (a message broker) for
a job set that's fundamentally time-triggered, not event-triggered from application
activity (aside from ARN resolution, which is correctly handled inline instead). Would be
worth reconsidering only if job volume or complexity grows well past what four
scheduled jobs plus one on-demand call represent today.

## References
- ADR-005: Deployment Architecture (this ADR's compute target)
- Research: AWS Serverless Land's EventBridge-Scheduler-to-ECS reference pattern;
  AWS ECS documentation on scheduled tasks; AWS re:Post threads on Fargate capacity
  transients and mitigation (2025–2026 sources)
- PRD-04: source of the four periodic jobs' cadence requirements
- PRD-03 FR-11a: source of the on-demand (not scheduled) ARN resolution requirement

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-07-22 | Claude (PM partner) | Initial draft — ADR-001 (frontend), ADR-002 (backend), ADR-003 (database), ADR-004 (storage) |
| 1.1 | 2026-07-22 | Claude (PM partner) | All four ADRs moved to Accepted per Ayush's confirmation (React/Vite, FastAPI, RDS/Postgres). ADR-004 substantially rewritten to clarify the Postgres-vs-S3 distinction and add the CAS-PDF-retention question as an explicit open decision. Corresponding scope additions made to PRD-01 and PRD-03. |
| 1.2 | 2026-07-22 | Claude (PM partner) | ADR-004's PDF-retention decision resolved: CAS PDF is not retained anywhere. All four original ADRs fully resolved. |
| 1.3 | 2026-07-22 | Claude (PM partner) | Added ADR-005 (Deployment Architecture) and ADR-006 (Background Job Scheduling), both Accepted. ADR-005 corrects the TDD's original App Runner proposal after research found App Runner closed to new customers as of April 30, 2026 — recommendation moved to ECS Express Mode. ADR-006 confirms EventBridge Scheduler + ECS Fargate `RunTask` as current, documented AWS practice for the four periodic reference-data jobs, with ARN resolution confirmed correctly scoped as on-demand rather than scheduled. Removed the now-stale "What's Needed Before the TDD" section, since the TDD already exists and all six ADRs are Accepted with no open items. |
