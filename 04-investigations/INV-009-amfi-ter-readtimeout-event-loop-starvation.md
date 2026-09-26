# INV-009: AMFI TER `ReadTimeout`s root-caused to event-loop starvation from a blocking `db.commit()`

Status: Root cause found and fixed (`bb5225f`, 2026-08-27); one stopgap also
applied; the underlying architectural vulnerability is explicitly **not**
fully closed — see "Residual risk" below.
Date investigated: 2026-08-25/26
Related: [R-040](../07-risks-and-debt.md) (`compute_holdings` N+1, a related
but distinct performance item); [ADR-003](../03-decisions/ADR-003-primary-database-rds-postgresql.md)

## For stakeholders

A colleague's Analytics dashboard kept showing "data unavailable" for TER
and holdings, on the same codebase that worked fine on the product owner's
own machine. Two false leads were ruled out with real evidence before the
true cause was found: a blocking database write inside a request handler —
one that took over a minute on the colleague's slower disk — was freezing
every other request the server was handling at the same moment, including
an unrelated one that then timed out waiting for a government data feed
that had actually already answered. Because this backend runs as a single
worker with one shared task queue, any sufficiently slow database operation
can currently stall every logged-in user at once, not just the person who
triggered it. The specific case was fixed and confirmed working live. The
general shape of the problem — a slow database write can freeze the whole
app for everyone — has been fixed for the writes we know about today, but
is not fixed as a rule for every future one, and is flagged as something to
finish properly once the app moves off its current development database
technology.

## Technical detail

### Symptom

A colleague's Analytics dashboard persistently showed "TER Data
Unavailable" / "No Direct Holdings" / "No Regular Holdings" with a growing
TER-exclusion list, while the same codebase on the product owner's own
machine returned correct data.

### Investigation (via `superpowers:systematic-debugging`, three rounds)

1. **First hypothesis, confirmed real but insufficient**: AMFI's TER-page
   endpoint was being rate-limited at a fetch concurrency of 20 (raised
   there in an earlier session on the unverified assumption AMFI had no
   rate limit). Lowered to 5 (`bb9f507`). The colleague re-tested; the
   symptom recurred.
2. **No diagnosability**: the refresh function had zero logging on any
   failure path. Two `logger.warning` calls added, no behaviour change
   (`142eb6b`). The next live run immediately captured the real failure:
   `ReadTimeout('')` — a genuinely different failure mode from the
   already-fixed rate limit (every AMFI page in that run returned `200
   OK`).
3. **Root cause**: this backend's database engine is fully synchronous and
   runs as a single worker — one event loop shared by every concurrent
   request. A blocking `db.commit()` called directly inside an `async def`
   handler (a NAV-history warming operation, measured at 63.67s then
   66.69s for the same operation minutes apart on the colleague's slower
   disk) freezes that entire event loop for its full duration — including
   an unrelated AMFI TER request already waiting on its own socket in a
   concurrently-running task, which then exceeded its own client-side
   timeout even though AMFI itself had already answered normally. Not a
   repeat of the rate-limit issue, and not the caching-divergence theory
   originally suspected — direct evidence of event-loop starvation.

### Fix applied

A stopgap raised the TER client's own timeout from 30s to 90s (`945b271`),
giving margin against the observed 63-66s stall — this addresses TER's
all-or-nothing batch failure mode, not the underlying starvation. The
underlying vulnerability was then properly fixed, not just worked around:
commit `bb5225f` (2026-08-27) added a `commit_off_loop` helper that routes
`db.commit()` through a background thread, and rewired every reachable
commit across all 8 affected service files, with a regression test proving
a slow commit no longer starves the event loop. All three fixes were
live-tested together on the colleague's machine on 2026-08-26 and confirmed
working (correctly slower than the product owner's machine, not incorrect).

### Residual risk — explicitly not closed

The *trigger* (60-120 second SQLite commits) is specific to this
development environment (SQLite on a WSL filesystem mount) and is expected
to mostly disappear once the app runs on Postgres. The *vulnerability*
itself — any blocking synchronous database call inside an async handler
stalls every concurrent user sharing that event loop, not just the slow
request — is architectural and will still exist in production under real
concurrent traffic (a lock wait, a large batch commit, connection-pool
exhaustion, or a large CAS re-import could all still freeze every logged-in
user's request simultaneously). Three remediation options were identified
and deliberately not chosen yet, to avoid bundling a large cross-cutting
database-layer refactor into unrelated debugging work: wrap only the known
heavy batch commits in a background thread (targeted); wrap every
synchronous database call inside an async handler (blanket, needs
auditing for cross-thread session use); or migrate to SQLAlchemy's native
async engine (the correct long-term fix, a dedicated project of its own).
Revisit deliberately, ideally paired with the Postgres migration. Tracked
as its own dedicated entry: [R-058](../07-risks-and-debt.md).

### Evidence

- `08-evidence/documents/engineering-loop/session.md`, "AMFI TER `ReadTimeout` root-caused to event-loop starvation from blocking `db.commit()` (2026-08-25/26)" section
- `08-evidence/documents/engineering-loop/CLAUDE.md`, "Resolved, dropped from this list" (2026-09-02 entry, records the fix landed without the tracking doc being updated at the time)

### Addendum, 2026-09-24 (batch 6c) — full call-graph audit, exact file/line list

This entry's "Fix applied" section says commit `bb5225f` "rewired every
reachable commit across all 8 affected service files" but did not previously
record which 8 files, or how "reachable" was actually determined. A separate
raw note (unrelated task: designing an Analytics-prefetch feature, which
first had to check whether adding more concurrent async work was safe given
this fix) traced every call chain by hand rather than trusting the original
session.md list, and found session.md's own list was partly wrong: of its
3 named "known-heavy" sites, `nav.py`'s `warm_nav_history` and
`amfi_ter_client.py`'s `refresh_ter_data` were confirmed genuinely async and
exposed, but CAS import's `confirm_import_route` is actually a plain `def`,
not `async def` — FastAPI/Starlette auto-runs sync route handlers in a
threadpool off the main event loop automatically, so its slow commit was
never actually part of this bug. The real exposure was broader: every route
in `app/api/analytics.py` is `async def`, and none of those were on
session.md's original list.

**Exact fix list** — every `db.commit()` confirmed reachable from an
`async def` route, by tracing each call chain to its route decorator:

| # | File : function | Commit line(s) | Reached via |
|---|---|---|---|
| 1 | `app/services/dashboard/nav.py` : `_upsert_nav_history`, `warm_nav_history` | 121, 222 | async NAV/dashboard routes + `_prefetch_member_nav_history` background task |
| 2 | `app/services/analytics/amfi_ter_client.py` : `refresh_ter_data` | 332 | async TER routes (`analytics.py`) |
| 3 | `app/services/analytics/scorer.py` : `_finish_fund_score` | 271 | async score routes (`analytics.py`) |
| 4 | `app/services/analytics/nse_indices_client.py` : `_upsert_index_history` | 91 | async benchmark routes (`analytics.py`) |
| 5 | `app/services/dashboard/snapshots.py` | 124 | async `get_member_snapshots` / aggregate-snapshots routes |
| 6 | `app/services/analytics/scheme_universe.py` : `SchemeUniverseClient.get_category_universe` | 174 | `category_ranking.py` + `scorer.py` → async `analytics.py` routes |
| 7 | `app/services/dashboard/arn_lookup.py` : `resolve_arn` | 101 | `distributor_comparison.py` → async `get_member_distributor_comparison` / aggregate distributor routes |
| 8 | `app/services/import_/lifecycle_service.py` : `create_cas_import` only | 205, 227 | async `upload_cas_import` route (`cas_imports.py`) |

That is 8 files, one shared helper (`commit_off_loop` in
`app/db/session.py`), 9 call sites total (`nav.py` has 2).

**Confirmed safe, deliberately left untouched** (sync-routed; Starlette
auto-threads the whole handler): `app/api/auth.py` and everything it calls
(`session.py`, `otp.py`, `identity.py`, `google_oauth.py`); `import_/service.py`'s
`confirm_import`; `import_/cams_portal.py` (both functions);
`import_/coverage_gap.py`'s `create_opening_balance`;
`lifecycle_service.py`'s `retry_cas_import_password` (a sibling of #8, but
called only from the sync retry-password route); `dashboard/household_members.py`'s
`create_member`. `amfi_aaum_client.py` is `async def` but has no live route
or job calling it — dead code, not an exposure, left as-is.

The helper itself carries a documented ceiling, added as a code comment
(not a design flaw): `asyncio.to_thread` shares Python's default
thread-pool executor, which is bounded — many slow commits piling up at
once would queue on a thread rather than freeze the event loop (strictly
better than the pre-fix behavior, since only the slow-commit requests
wait, not every user), but the pool has a ceiling not yet sized or tuned.
Not scoped as a fix here; revisit if ever observed to matter.

This audit does not change this investigation's resolution — it documents
the granular provenance behind the "all 8 affected service files" phrase
already in the "Fix applied" section above. See also
[R-058](../07-risks-and-debt.md)'s 2026-09-24 update, which notes this
audit closes more ground than R-058's original "option 1/2/3" framing
anticipated, but does not close the risk itself (no structural guard
prevents a *future* new async route from reintroducing the bug).

Evidence: `08-evidence/documents/Mid Load Tab Switch and Tab Preloading.md`.
