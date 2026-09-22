# Frontend catches up to the precompute merge, and a staging push is sequenced

## For stakeholders

The backend precompute rebuild (2026-09-02 stage) deleted the old Analytics
endpoints the frontend still called — so before anything could go live, the
frontend needed a matching update, or the Analytics dashboard would have
returned errors for every staging user. That frontend work was completed
this stage. A 9-step plan to actually get the app onto the staging
environment was also laid out, and along the way an unrelated bug was found
and fixed in one of the scheduled background jobs, and a stale status note
about infrastructure Terraform state was caught and corrected.

## Technical detail

### Intended outcome

Bring `feat/enhanced-ui` fully up to date, fix the frontend/backend
mismatch left by the 2026-09-02 merge, and sequence the remaining steps to
staging.

### What actually happened

The precompute merge deleted `backend/app/api/analytics.py`'s 14 old
per-section routes; `frontend/src/features/analytics/api.ts` still called
them, meaning every Analytics fetch would 404 against the merged backend.
A 9-task frontend migration plan — recovered from a deleted worktree left
behind by another agent during the same session and committed (`4c4e394`)
before that worktree was deleted — closed this gap. It was explicitly
frontend-only, zero backend changes, and ended with its own mandatory
adversarial-review gate. The 2026-09-11 AWS staging doc later confirmed
this was done (`b972e65`), with both desktop and mobile consumers now
using a consolidated `useAnalyticsScope` hook.

Along the way, all 4 EventBridge-scheduled AMFI/NSE jobs were run manually
for the first time on staging. Three succeeded; `aaum-quarterly` crashed on
a `TypeError`, root-caused and fixed the same day (see
[INV-008](../04-investigations/INV-008-amfi-aaum-period-selection-bug.md)).
Separately, a stale line in `session.md` claiming Phase 5's Terraform
(ACM/Route53/ALB HTTPS) was "drafted, not yet dispatched" was corrected —
it had actually been authored and reviewed later the same day it was
written, confirmed against both the handoff doc's own `Status: DONE` and
the `infra/modules/dns/` module existing in git.

The 10-step staging push plan sequenced: execute the frontend migration
(done, above); push `feat/enhanced-ui` and fast-forward `main`/`production`
(no merge conflicts — confirmed zero divergence); rebuild/push the backend
image; apply Phase 4 (S3+CloudFront) and Phase 5 (ACM/DNS/ALB HTTPS)
Terraform; rebuild the frontend against the real staging API URL; wire the
analytics-recompute dispatcher's ECS task definition and config; run the
existing Phase 6 smoke-test checklist; stand up a staging CI/CD pipeline;
and only then open beta. Google Sign-In and real OTP delivery were
explicitly, deliberately excluded from this pass — staging targets
beta/friends-and-family users, and both are tracked as future Phase 7
hardening, not blockers.

### Deviation (if any) — decision or response taken

None of the deployment steps in this plan were themselves executed by
Claude — every AWS-state-mutating step is marked `[user-run]` per this
project's established division of labor, and this document is superseded
the next day by a more detailed runbook (2026-09-11 stage) once more of the
plan's steps had actually happened.

### Result

Frontend migration done and confirmed. The remaining 9 sequencing steps
were handed off as a plan, not executed within this stage — see the
following (2026-09-11) stage for what had actually happened by the next
day.

### Related

- ADR-015 — analytics precompute architecture (the backend half this stage's frontend work completes)
- INV-008 — the `aaum-quarterly` min/max bug found during this stage's manual job runs
- Evidence: `08-evidence/documents/plans/2026-09-10-analytics-frontend-precompute-migration.md`
- Evidence: `08-evidence/documents/plans/2026-09-10-feat-enhanced-ui-to-staging-push-plan.md`
