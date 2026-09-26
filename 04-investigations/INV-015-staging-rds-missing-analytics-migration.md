# INV-015: Staging Analytics 500s traced to a precompute migration that was never applied to the real RDS instance

Status: Root cause confirmed and fixed live on staging; verified end to end
Date investigated: 2026-09-11
Related: [ADR-015](../03-decisions/ADR-015-analytics-precompute-architecture.md)
(the `analytics_sections`/`analytics_recompute_status` schema this migration
creates); [2026-09-11 AWS staging deployment runbook](../02-journey/2026-09-11-aws-staging-deployment-runbook.md)
(which had already flagged this exact migration as unapplied, before this
session confirmed it as the live cause of a real outage); [R-063](../07-risks-and-debt.md)
(a related but distinct NAV cold-start finding surfaced in the same session)

## For stakeholders

After the first real staging deployment, every Analytics page request
failed outright. The cause was simple once found: a database change needed
for the new Analytics precompute design had been written and merged into the
code weeks earlier, but had never actually been run against the real
staging database — only against local development databases. The main
Dashboard worked fine because it doesn't depend on that change; only
Analytics touched the missing database table. It was fixed the same way the
original staging database setup was done (a secure, no-open-ports tunnel,
no SSH), and the fix was confirmed working end to end: the page loaded, and
a real background job ran and computed real numbers.

## Technical detail

### Symptom

`GET /analytics/*` returned HTTP 500 on `staging.unifolio.in` immediately
after the Phase 4/5 Terraform applies and frontend rebuild/redeploy (see the
[2026-09-11 runbook](../02-journey/2026-09-11-aws-staging-deployment-runbook.md)
addendum below for those applies). The main Dashboard, holdings, and
allocation views loaded correctly on the same request — ruling out CORS,
DNS, and ALB routing as the cause, since those would affect every endpoint
equally, not just Analytics.

### Root cause

Live backend logs showed the real error:
`psycopg2.errors.UndefinedTable: relation "analytics_sections" does not
exist`. Migration `0012_analytics_sections`
(`backend/alembic/versions/0012_analytics_sections.py`, `down_revision =
"0011"`) creates that table as part of the analytics precompute
architecture ([ADR-015](../03-decisions/ADR-015-analytics-precompute-architecture.md)).
The migration existed in the repo and had been applied locally, but the
staging RDS instance had last been migrated to `0011` (during the original
Task B schema bootstrap — see the
[2026-09-09 journey entry](../02-journey/2026-09-09-terraform-applied-and-iam-key-incident.md))
and was never re-migrated afterward. Dashboard, holdings, and allocation
endpoints don't touch `analytics_sections`, which is why only Analytics
broke.

### Fix applied

Same SSM Session Manager bastion-tunnel pattern as the original schema
bootstrap (no SSH, no open ports, IAM-authenticated port-forward to RDS's
private-subnet endpoint):

1. `alembic current` on the tunnel confirmed `0011`, not `0012`.
2. `alembic upgrade head` applied `0012`, creating `analytics_sections` and
   `analytics_recompute_status`.
3. `alembic current` confirmed `0012` (head).

### Verification (live, not just assumed)

- `GET /analytics/{scope}` went from `500` (`UndefinedTable`) to `200 OK`.
- The on-demand dispatcher
  ([ADR-015](../03-decisions/ADR-015-analytics-precompute-architecture.md)'s
  `EcsRunTaskDispatcher`) logged a real dispatch: `dispatched recompute
  RunTask for user 68c4298e-...` — not a stub or a cached response.
  Dashboard/holdings/allocation were unaffected throughout, confirming the
  migration gap was Analytics-specific.
- The dispatched ECS task exited cleanly (code 0); CloudWatch logs
  confirmed it computed category returns and scores for all 3 fund
  categories present in the test portfolio, not just one.
- A follow-up screenshot confirmed the dashboard rendering real allocation,
  TER, category ranking, fund score, and benchmark comparison data.

### Scope note — what this fix does and does not cover

Only the missing-table 500 was fixed and verified here. A separate,
already-tracked finding from the same live-testing session — that a
category nobody has ever ranked before triggers a slow (~113s) cold NAV
fetch on first touch — is a distinct, pre-existing scope gap in the daily
NAV-warming job, not something this migration fix touches either way; see
[R-063](../07-risks-and-debt.md) for that item (already recorded from a
separate raw source with the same underlying numbers). This investigation
also does not attempt to confirm whether migrations `0013` and `0014`
(named as also-unapplied in the 2026-09-11 runbook, at that earlier point
in the sequence) have since been applied — only `0012` was hit by a live
symptom and fixed here.

### Apparent contradiction with other already-ingested material — flagged, not resolved

A different raw source ingested in a concurrent batch (`darshan changes.md`)
describes this same 2026-09-11 runbook session and states that the three
then-pending migrations (`0012_analytics_sections`,
`0013_account_deletion_grace_period`, `0014_analytics_recompute_generation`)
"were applied" as part of the runbook's Step 2 — recorded on
[R-052](../07-risks-and-debt.md)'s 2026-09-24 update and the matching
addendum on the
[2026-09-11 runbook entry](../02-journey/2026-09-11-aws-staging-deployment-runbook.md).
This batch's source (`Move to Cloud.md`) directly contradicts that for
`0012` specifically: it shows a live `psycopg2.errors.UndefinedTable`
failure for exactly this table when Analytics was actually first exercised
against the deployed staging environment, with an explicit `alembic
current` check confirming the database was still at `0011`, not `0012`,
before this investigation's fix was applied. **Both accounts are preserved
per this vault's append-only convention; this discrepancy is not
adjudicated here** — possible explanations include the two source
documents describing different points in time that got conflated when
summarized, or one account being second-hand/unverified at the moment it
was written. What is independently, directly verified in this batch's own
source material (before-state, exact error text, and after-state) is that
`0012` was missing and then fixed live, on 2026-09-11, via the steps above.
See the corresponding new updates on
[R-052](../07-risks-and-debt.md) and the
[2026-09-11 runbook entry](../02-journey/2026-09-11-aws-staging-deployment-runbook.md).

### Evidence

- `08-evidence/documents/Move to Cloud.md`, "Root cause found — analytics_sections
  never migrated on staging RDS" section onward (redacted copy; see the
  batch ingestion report for the redaction/secrets-verification note)
