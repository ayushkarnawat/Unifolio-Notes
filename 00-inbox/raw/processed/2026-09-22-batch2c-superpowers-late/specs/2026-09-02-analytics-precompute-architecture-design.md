# Analytics + Dashboard Precompute Architecture

**Date:** 2026-09-02
**Status:** Design approved in chat, pending user review of this document
**Branch:** `feat/enhanced-ui` (implementation branch TBD via `writing-plans`)

## Context and root cause

Rapid tab/view-switching in the Analytics dashboard fires new batches of 7 concurrent
analytics requests on top of still-running abandoned previous batches — the backend
never checks `request.is_disconnected()`, so client-side `AbortController` cancellation
on tab-switch doesn't actually stop backend execution. Several of those requests do
multi-minute uncached NAV-warming and DB commits (category ranking / scorer's SEBI
peer-universe compute), which exhausts SQLAlchemy's default 15-connection `QueuePool`
(`QueuePool limit of size 5 overflow 10 reached, timeout 30.00`). Once the pool is
exhausted, even the request for the view currently on-screen times out with a 500.

**Explicit mandate:** the fix is the full precompute/caching architecture described
below, not a stopgap (a pool-size bump or an `is_disconnected()` check alone, in
isolation, is explicitly ruled out as the delivered fix).

## Named approaches considered

**Approach 1 — Consolidated read + ECS Fargate `RunTask` recompute (chosen).**
Collapse the 7 per-scope read endpoints into one per scope; a single
`recompute_household_analytics()` function, invoked only via short-lived ECS Fargate
`RunTask`s, is the sole writer of precomputed rows. Reuses ADR-006's already-approved
EventBridge Scheduler → ECS Fargate `RunTask` pattern (currently running for AMFI/NSE
reference-data jobs) for both the daily backstop and on-demand event triggers. No new
infrastructure.

**Approach 2 — Queue-backed recompute via a Postgres jobs table.** Same read side;
triggers insert into a `recompute_jobs` table instead of dispatching directly, consumed
by a separate always-on worker. Rejected — needs a new always-on ECS service (a
deployment pattern ADR-005/006 don't cover), for duplicate-request collapsing that the
debounce (Decision 7) and the in-flight guard (Decision 9 / Error Handling) already
provide without it.

**Approach 3 — Keep the 7 endpoints, swap each to read a precomputed row.** Smallest
frontend diff. Rejected as the primary approach — perpetuates 7x request volume and 7
independent frontend loading states for no benefit, once the per-card UX (Decision 5)
needs one consolidated response shape anyway. Noted as a fallback if the consolidated
read API turns out to be a bigger lift than expected.

## Architecture overview

**Read path.** `GET /analytics/{scope}` where `scope` is `"combined"` or a household
member's UUID. One indexed Postgres query returns all 7 precomputed sections for that
scope plus the household's in-flight recompute status. No live computation ever runs on
this path — this is what removes the pool-exhaustion risk at the root.

**Write path.** `recompute_household_analytics(db, user_id)` is the sole writer:
1. Marks the household as recomputing (`analytics_recompute_status.started_at`).
2. Computes the union of schemes/categories held anywhere across the household's
   members, and warms NAV for that union **once** (the expensive leg).
3. Fans out cheap local arithmetic across all 5 scopes (household-combined + up to 4
   members) × 7 sections, upserting each row as its own compute finishes — not
   batched at the end, so the frontend's per-card reveal (Decision 5 / Option 5) has
   something to show early.
4. Clears the in-flight flag in a `finally` block.

This function **only ever runs inside a dedicated ECS Fargate `RunTask`**, never inline
in a request-serving process. This is a hard rule, not an optimization: an inline
recompute would still contend with live requests for the same SQLAlchemy connection
pool while it holds connections across the NAV warm + 35-row write — the *original*
pool-exhaustion bug this whole redesign exists to fix — and it keeps recompute's
resource usage isolated from the app tier, consistent with ADR-006's existing pattern.

Note: an earlier draft of this rationale also cited a blocking-event-loop risk
(`session.md`'s "still open" item 7). Checked against current code while writing the
implementation plan (2026-09-02) — that's already fixed (commit `bb5225f`,
2026-08-27, predates this design work): `commit_off_loop` routes every reachable
`db.commit()` through `asyncio.to_thread`, across all 8 affected files including
`nav.py`, with a regression test. `session.md`'s "still open" section is stale and
should be updated to drop item 7. The connection-pool-contention argument above still
holds independently, so the RunTask-only decision is unchanged.

Four triggers dispatch the same `RunTask`:
- **CAS import completion** — one line added to `confirm_import` (`service.py:137`),
  no debounce (import is already one atomic job).
- **Manual transaction edit**, once that flow exists — ~15s debounce, collapsing rapid
  successive edits into one recompute.
- **Daily EventBridge Scheduler backstop** — for NAV/market drift with no user
  activity. Dispatches **one** `RunTask` that loops every household in a single
  process run (not one task per household — see Cost and the NAV-cache bug below).
- **A household's first-ever read** (zero rows, no recompute in flight) — the read
  endpoint dispatches the `RunTask` itself before returning an empty response.

All four dispatch calls are no-ops if `analytics_recompute_status.started_at` is
already set for that household — the in-flight run will pick up the latest source
data by the time it queries each section, so a second dispatch adds nothing but a
redundant task launch.

## Components

**`analytics_sections`** (new table) — the precomputed-row store. Primary key
`(user_id, scope_key, section)`:
- `user_id` — the household (matches the existing convention in `aggregate.py`, where
  "household" is always just `user_id`; there is no separate household entity).
- `scope_key: str NOT NULL` — `"combined"` for the household-aggregate row, or a
  member's UUID as text otherwise. A plain string discriminator, not a nullable
  `household_member_id` in the primary key — Postgres treats each `NULL` as distinct
  for uniqueness purposes, which would let every recompute insert a *new* "combined"
  row instead of `ON CONFLICT`-updating the existing one.
- `household_member_id: UUID NULL` — separate FK column (not part of the PK), kept
  alongside `scope_key` purely for cascade-delete when a member is removed.
- `section: str` — one of `allocation`, `ter`, `ter_direct_regular`, `benchmark`,
  `benchmark_funds`, `category_ranking`, `score` (the 7 existing analytics endpoints,
  minus `/funds/{scheme_id}/score`, which is fund-scoped rather than
  household/member-scoped and stays outside this grid).
- `payload: JSONB` — the exact response body the corresponding endpoint returns today
  (same Pydantic shape), so the read endpoint hands it back with zero reshaping.
- `computed_at: DateTime(timezone=True)`.
- `failed_at: DateTime(timezone=True) NULL` — set when this row's compute raises,
  cleared on the next successful compute. Drives the per-section "Retry" affordance
  (see Error Handling).

At the stated household cap (owner + 3 members = 4 members), that's 5 scopes × 7
sections = 35 rows per household.

**`analytics_recompute_status`** (new table) — one row per `user_id`:
`started_at: DateTime NULL`. Non-null means a recompute is currently running for that
household (Decision 8: one household-level flag, not a per-row status enum).

**`recompute_household_analytics(db, user_id)`** — `app/services/analytics/recompute.py`
(new). Reuses today's existing per-section compute functions (`allocation.py`,
`ter.py`, `benchmark.py`, `category_ranking.py`, `scorer.py` — unchanged, they're
already correct) as the actual per-scope arithmetic; this function is purely the
orchestration/upsert layer around them.

**NAV freshness fix** — `warm_nav_history`'s "already fresh, skip fetch" check
currently lives in a process-local dict (`_nav_warm_cache` in `nav.py`), correct for
today's one long-running FastAPI process but wrong once recompute runs as short-lived
`RunTask`s (every task is a fresh process with an empty cache, so it would
unconditionally re-fetch every scheme's NAV history even if a sibling task fetched it
moments ago and it's already fresh in Postgres). Fix: swap the process-local dict check
for a query against `nav_history`'s latest row per scheme. Same function signature,
internal change only — `get_nav_on_or_before` and every existing caller are unaffected.

**Read endpoint** — `GET /analytics/{scope}`, replacing the 14 existing per-section
GETs (7 sections × member/aggregate variant). One `analytics_sections` query filtered
by `user_id` + `scope_key`, plus one `analytics_recompute_status` lookup, assembled
into a response keyed by section name.

**Retry endpoint** — `POST /analytics/{scope}/retry` (new, thin). Calls the same
household-level dispatch every trigger uses; no new compute path.

## Data flow

**Cold start.** First CAS import confirms → `confirm_import` dispatches a `RunTask` →
the first `GET /analytics/combined` finds zero rows (or a `started_at` that just began)
→ frontend renders Option 5 (one ring-spinner per still-computing card), polling the
same endpoint every few seconds. Cards fill in independently as
`recompute_household_analytics` writes each section's row; polling stops once all 7
have landed.

**Steady state.** Dashboard loads first (unchanged). Once it resolves, the frontend
prefetches `GET /analytics/{scope}` for likely-needed scopes (Decision 6) — cheap reads
of real data, no spinners. Tab-switching is now pure re-render of already-fetched or
trivially-fetched cached rows; nothing on this path performs live compute.

**Background refresh.** A trigger fires while the user has existing Analytics data on
screen → `started_at` goes non-null → the next read picks that up and the frontend
shows Option 3 (dimmed data + "Updating with latest data…" pill) while rows are
overwritten underneath (`ON CONFLICT DO UPDATE`, never delete-then-insert, so nothing
flashes blank). Each section flips back to normal the moment its own row's
`computed_at` advances past when the pill appeared.

**Daily backstop.** EventBridge fires once daily → one `RunTask` loops every household
in a single process → each household's 35 rows refresh via the same upsert path as any
other trigger. Indistinguishable from any other background refresh from the frontend's
perspective.

## Error handling

**A single section's compute fails.** The row's existing data stays on screen
untouched; `failed_at` is set (cleared on next success); the frontend shows a small
inline "Retry" on just that card instead of a full-page error. Retry calls the same
household-level dispatch as every other trigger (already no-op-guarded if a recompute
is already in flight) — no dedicated single-section recompute path, which would fight
the warm-once/fan-out design for a marginal win. Matches the degrade-gracefully
convention already in `nav.py` (a scheme whose fetch fails is simply left unwarmed).

**The whole `RunTask` fails or is killed.** No partial row is ever written mid-compute,
so nothing is corrupted, but `started_at` could be left non-null indefinitely, wrongly
pinning the household in the dimmed/pill state. `recompute_household_analytics` wraps
its body in `try/finally` so the flag clears even on an unhandled exception; as a
backstop against a `SIGKILL` that skips even the `finally`, the daily job also treats
any `started_at` older than a generous ceiling (2 hours) as stale and clears it before
starting a fresh run.

**A trigger fires while a recompute is already running for that household.** No-op —
covered under Architecture Overview's dispatch guard above.

**A household with zero rows and no recompute in flight reads Analytics.** The read
endpoint dispatches the `RunTask` itself (same guard) before returning an empty
response, so cold start always has something moving toward completion.

## Testing strategy

- **`recompute_household_analytics`** (`tests/services/analytics/test_recompute.py`,
  new): a 2+ member household produces all 35 rows with correct `scope_key`s;
  `warm_nav_history` is called exactly once for the union of held schemes, not once
  per scope (the assumption Decision 4's entire cost argument rests on); a raising
  section leaves its existing row untouched and sets `failed_at`; a subsequent
  successful run clears a stale `failed_at`; `started_at` clears in `finally` even
  when a section raises mid-loop.
- **NAV freshness fix** (`tests/services/dashboard/test_nav.py`, extends existing): a
  scheme already fresh in `nav_history` isn't re-fetched even from a cold process
  (empty `_nav_warm_cache`) — the regression test for the bug this design fixes.
- **Read endpoint** (`tests/api/test_analytics_route.py`, replaces the 7 existing route
  test files): returns exactly what's in `analytics_sections` with no live compute
  invoked; zero rows + no `started_at` triggers a dispatch and still returns a
  well-formed empty response; `started_at` surfaces correctly for Option 3.
- **Retry endpoint** (new, small): no-ops when a recompute is already in flight;
  dispatches when it isn't.
- **Trigger wiring** (`tests/services/import_/test_service.py`, extends existing):
  `confirm_import` dispatches exactly once per confirmation; a second import for the
  same household while one is still running doesn't double-dispatch.
- **Explicitly not unit-tested here:** the EventBridge Scheduler / ECS Fargate
  `RunTask` AWS wiring itself — infra configuration, verified by deployment, same
  treatment the existing AMFI/NSE jobs already get.

  **Note (2026-09-02):** this AWS infra (EventBridge Scheduler, `RunTask` wiring, VPC/
  NAT networking) is being built out concurrently in a separate session as part of the
  broader AWS migration. That work isn't blocking this design, but the two threads need
  to be reconciled once both land — specifically: the `RunTask` invocation contract
  (task definition ARN, how `user_id`/"all households" is passed as an argument to the
  daily-loop vs. single-household dispatch modes) isn't nailed down here and should be
  confirmed against whatever the parallel session already decided for the AMFI/NSE jobs
  before implementation starts.

## Cost (AWS)

`nav_history` is already a platform-global cache keyed by `scheme_id`, not
per-household (confirmed by reading `nav.py`), so the expensive leg (mfapi.in network
fetch) is bounded by total distinct schemes actually held across the whole platform —
a few hundred realistically, not multiplied by household count. Fargate compute and
RDS write cost for this feature is estimated well under $1-2/month at realistic
MVP-to-early-growth scale. NAT Gateway/egress cost (potentially the dominant line item,
~$32-35/month flat if tasks need private-subnet outbound internet) is out of scope for
this design — it applies equally to the pre-existing AMFI/NSE jobs and is being
resolved in the parallel AWS-migration session referenced above.

## Out of scope / deferred

- Single-section-only retry recompute (Retry re-runs the whole household; acceptable
  given NAV is usually already warm by the time a retry is clicked).
- The manual-transaction-edit trigger's actual implementation (only the debounce
  behavior is specified here, in anticipation of that flow existing).
- Any change to the 7 sections' underlying compute logic — this design only changes
  when/where they run, not what they compute.
