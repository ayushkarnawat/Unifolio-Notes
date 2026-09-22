# ADR-015: Analytics moves from live-compute-on-read to a per-household precompute, dispatched via ECS Fargate RunTask

Status: Accepted — designed and implemented, merged to `feat/enhanced-ui`
Date: 2026-09-02
Related: [2026-09-02 journey stage](../02-journey/2026-09-02-analytics-precompute-architecture.md), R-042, ADR-006 (background job scheduling)

## For stakeholders

Rapidly switching between Analytics tabs was crashing the dashboard for the
tab a user was actually looking at. The cause: every tab switch fired seven
new slow calculations on top of ones still running from the previous tab,
and the database ran out of connections to serve anyone. The fix rebuilds
Analytics so the numbers are calculated once, in the background, and every
screen just reads the already-calculated result — never recalculates on the
spot. This removes the crash at its root rather than papering over it, and
it also answers a question this vault had flagged as an unverified rumor
(R-042): the "calculate once and fill in cards as they finish" behavior
promised by an earlier loading-state design turned out to be real, not
aspirational — it is what this decision built. Both the backend piece and
its matching frontend piece were implemented and merged.

## Technical detail

### Context

Rapid tab/view-switching in the Analytics dashboard fired new batches of 7
concurrent analytics requests on top of still-running abandoned previous
batches — the backend never checked `request.is_disconnected()`, so
client-side cancellation on tab-switch didn't stop backend execution.
Several of those requests performed multi-minute uncached NAV-warming and DB
commits, exhausting SQLAlchemy's default connection pool
(`QueuePool limit of size 5 overflow 10 reached, timeout 30.00`). Once
exhausted, even the request for the on-screen tab timed out with a 500.

The explicit mandate (design doc, 2026-09-02): the fix must be the full
precompute/caching architecture below, not a stopgap — a pool-size bump or
an `is_disconnected()` check alone was explicitly ruled out as the delivered
fix.

### Decision drivers

- Eliminate the root cause (concurrent live compute contending for the same
  connection pool), not just its symptom.
- Reuse ADR-006's already-approved EventBridge Scheduler → ECS Fargate
  `RunTask` pattern (already running for AMFI/NSE reference-data jobs) —
  no new infrastructure pattern.
- Keep the 7 sections' underlying compute logic (`allocation.py`, `ter.py`,
  `benchmark.py`, `category_ranking.py`, `scorer.py`) completely unchanged —
  this is a where/when-it-runs change, not a what-it-computes change.

### Options considered

#### Option 1: Consolidated read + ECS Fargate `RunTask` recompute (chosen)

Collapse the 7 per-scope read endpoints into one per scope; a single
`recompute_household_analytics()` function, invoked only via short-lived ECS
Fargate `RunTask`s, is the sole writer of precomputed rows.

Advantages: no new infrastructure (reuses ADR-006's pattern); recompute
isolated from the request-serving connection pool, which is the actual bug.

Disadvantages: adds a new precompute write path and two new tables to
reason about.

#### Option 2: Queue-backed recompute via a Postgres jobs table

Same read side; triggers insert into a `recompute_jobs` table, consumed by a
separate always-on worker.

Rejected — needs a new always-on ECS service, a deployment pattern
ADR-005/006 don't cover, to solve duplicate-request collapsing that a
15s debounce plus an in-flight guard already provide without it.

#### Option 3: Keep the 7 endpoints, swap each to read a precomputed row

Smallest frontend diff.

Rejected as the primary approach — perpetuates 7x request volume and 7
independent frontend loading states for no benefit, once the per-card UX
needs one consolidated response shape anyway. Noted as a fallback only.

### Decision

Option 1. New tables `analytics_sections` (precomputed rows, PK
`(user_id, scope_key, section)`, `ON CONFLICT DO UPDATE` upsert only, never
delete-then-insert) and `analytics_recompute_status` (one row per user,
household-level in-flight flag). `recompute_household_analytics(db, user_id)`
is the sole writer, reusing the 5 existing per-section compute functions
unchanged, and runs **only** inside a dedicated ECS Fargate `RunTask` — never
inline in a request-serving process, which is a hard rule (an inline
recompute would reproduce the exact pool-contention bug this design exists
to fix). Four triggers dispatch the same `RunTask`: CAS import completion,
a future manual-transaction-edit (debounced ~15s, not yet built), the daily
EventBridge Scheduler backstop, and a household's first-ever cold-start
read. All four are no-ops if a recompute is already in flight for that
household. `GET /analytics/{scope}` replaces the 14 old per-section GET
routes with one read per scope, never computing live; `POST
/analytics/{scope}/retry` re-dispatches on the same guard for a single
failed section (the whole household is recomputed, not just one section —
accepted, since NAV is usually already warm by retry time).

A DB-backed NAV freshness check (`nav_history`'s latest row per scheme,
3-day window) replaces the old process-local TTL cache in `nav.py`, because
`RunTask`s are fresh processes each time and a process-local cache would
never see a sibling task's recent fetch.

Three implementation-level refinements were flagged (not silent deviations)
during planning: scope processing order (combined, then each member) reuses
existing in-process category caches instead of adding an explicit
union/warm step; no new `nav_fetch_attempts` table was added, since
`warm_nav_history` is now called only a handful of times per household per
day rather than on every page load; and the CAS-import dispatch call lives
in the import route handler (which has a `BackgroundTasks` instance),
not inside `confirm_import` itself as the design doc's prose literally
said.

### Consequences

Positive:
- Removes the pool-exhaustion bug at its root — the read path never runs
  live compute.
- Resolves [R-042](../07-risks-and-debt.md): the per-household precompute
  the 2026-08-27 loading-state decision assumed was real infrastructure was
  in fact undesigned at the time; this ADR designed and built it.
- A single section's compute failure keeps the other 6 sections' and 4
  scopes' data intact (`failed_at`, per-section retry affordance).

Negative:
- Two new tables and a dispatch abstraction (`RecomputeDispatcher`) to
  operate and reason about.
- The exact AWS RunTask invocation contract (cluster/task-definition ARNs)
  was finalized in a parallel, concurrently-running AWS-migration session —
  this design shipped against empty-string defaults that degrade to a
  logged no-op, reconciled afterward (see the 2026-09-10/11 journey
  stages).
- The migration's actual applied number (`0012_analytics_sections`, per the
  2026-09-11 AWS staging doc) does not match the number the design/plan
  documents wrote at design time (`0010`) — two unrelated migrations
  (`0010`/`0011`) landed on the branch first. Ordinary plan drift, not a
  contradiction; flagged here since the vault's evidence copies show the
  earlier number.

### Validation

Confirmed built and merged, not merely designed: the 2026-09-10 staging push
plan records a 26-commit worktree (`analytics_sections`/
`analytics_recompute_status` read/write split) merged into `feat/enhanced-ui`
(`f2daf84`), a post-merge regression found and fixed (missing exception
handling in `_dispatch_recompute_and_release_claim_on_failure`, `8c2f0ef`),
and the full backend suite passing (628 passed, 6 skipped) verified fresh
after the fix. The matching frontend migration (consuming the new
consolidated endpoints) is tracked separately — see the 2026-09-10 journey
stage and its own evidence.

### Evidence

- Design: `08-evidence/documents/specs/2026-09-02-analytics-precompute-architecture-design.md`
- Plan: `08-evidence/documents/plans/2026-09-02-analytics-precompute-architecture.md`
- Build/merge confirmation: `08-evidence/documents/plans/2026-09-10-feat-enhanced-ui-to-staging-push-plan.md`
