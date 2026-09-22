# Investigation: the `aaum-quarterly` job crashed because "latest period" was chosen with `max()`

Status: Closed — root-caused and fixed on `feat/enhanced-ui`; fix not yet in the deployed staging image at investigation time
Date: 2026-09-10
Related: ADR-006 (background job scheduling), [2026-09-10 journey stage](../02-journey/2026-09-10-frontend-migration-and-staging-push-plan.md)

## Trigger

On 2026-09-10, all 4 EventBridge-scheduled AMFI/NSE reference-data jobs
were run manually for the first time on staging
(`unifolio-staging-job-{aaum-quarterly,benchmark-daily,nav-daily,ter-monthly}`).
Three succeeded cleanly. `aaum-quarterly` crashed at 08:50 UTC with
`TypeError: string indices must be integers, not 'str'`.

## Expected behavior

The job should identify AMFI's most recently published AAUM reporting
period and fetch that period's data.

## Observed behavior

The job crashed with a type error partway through, consistent with having
selected a response shape it didn't expect.

## Hypotheses

1. AMFI's period/year `id` values are assumed to count *up* (so the
   original code picks the "latest" period with `max()`), but actually
   count *down* from the most recent period — `max()` would then pick the
   oldest year, which may have an incompatible response shape.

## Experiments

| Experiment | Expected signal | Actual result | Conclusion |
|---|---|---|---|
| Inspect AMFI's period/year `id` ordering against the code's `max()` selection | If ids count down, `max()` picks the wrong (oldest) year | AMFI's period/year `id` counts down from most recent; the original code used `max()` to pick "latest," so it usually picked the wrong (oldest) year and occasionally hit an incompatible response shape | Confirms hypothesis 1 |

## Root cause

AMFI's period/year `id` counts down from the most recent period, not up.
The code's `max()` call to select "the latest period" therefore usually
selected the oldest year in the response, and that year's response shape
was occasionally incompatible with what the parser expected, producing the
`TypeError`.

## Resolution

Fixed same day on `feat/enhanced-ui`: switched the selection from `max()`
to `min()`, with the rationale documented as a code comment (commit
`037aa4c`).

## Remaining uncertainty

**The fix was not yet in the deployed image at the time this was found.**
`unifolio-staging-backend:latest` was pushed to ECR at 09:02 UTC, before the
09:47 UTC fix commit — so the job wired to the live EventBridge schedule
still carried the bug after this investigation closed; it had "succeeded"
twice after the initial crash by luck (a compatible year was hit by chance),
not because it was fixed. The 2026-09-10 push plan records this as riding
along in the next backend image rebuild, not requiring a separate action —
not independently confirmed in this batch whether that rebuild/push has
actually happened yet. **To verify:** confirm the deployed image's digest
postdates commit `037aa4c`, and confirm a subsequent `aaum-quarterly` run
succeeded against real (not lucky) data.

## Related records

- ADR-006 — background job scheduling (the EventBridge Scheduler → ECS
  Fargate `RunTask` pattern this job runs under)
- ADR-015 — analytics precompute architecture (the same RunTask pattern,
  reused)
- Evidence: `08-evidence/documents/plans/2026-09-10-feat-enhanced-ui-to-staging-push-plan.md`
