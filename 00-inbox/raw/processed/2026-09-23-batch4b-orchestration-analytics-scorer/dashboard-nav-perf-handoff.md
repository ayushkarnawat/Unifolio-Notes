# Handoff: dashboard-nav-perf

**Status:** DONE
**Parent plan:** none (direct diagnosis this session, not from a superpowers plan doc)

## Round 1 adversarial review findings (2026-08-13, `/codex:adversarial-review`, verdict: needs-attention)

All three are real correctness races, not nitpicks — must be fixed before this doc's
Status can move to `DONE`:

1. **[High]** Stale/incomplete holdings can get cached for the whole day
   (`holdings.py:79-82`). If a dashboard request runs while Fix A's background NAV
   prefetch is still in flight (or before today's NAV is even published), `compute_holdings`
   caches that incomplete/stale result under Fix D's day-keyed cache — nothing
   invalidates it once the prefetch finishes or once NAV data later changes. A fund can
   show stale or missing values for the rest of the day.
2. **[High]** A race lets a stale pre-import snapshot survive cache invalidation
   (`holdings.py:180`). If a `compute_holdings` call is in flight when an import commits,
   it can finish and write its (now-stale) result to the cache *after*
   `confirm_import`'s invalidation already ran, permanently shadowing fresh data for
   that day. Membership-aware deletion alone isn't atomic against this.
3. **[High]** `_upsert_nav_history` has a check-then-insert race across sessions
   (`nav.py:40-45`). Two separate `Session`s (e.g. a background prefetch overlapping a
   live dashboard request) can both observe a date missing and both attempt to insert
   the same `(scheme_id, date)` row — one commit raises an uncaught `IntegrityError`
   (500 on the dashboard-request side), the other (background prefetch) just logs and
   drops the batch. Fix B's network-only `asyncio.gather` isolation does not protect
   against this — it's a race between two *separate* Sessions, not within one.

Codex's own suggested directions (not mandates — use judgment on the simplest correct
fix for each): a generation-counter or atomic check-generation-then-publish scheme so a
cache write from a stale computation never overwrites a fresher invalidation; and a
DB-native conflict-safe upsert (`ON CONFLICT DO NOTHING` equivalent for this project's
target DBs — SQLite locally, Postgres in prod, per the Migration Plan) for
`_upsert_nav_history`, reading back the authoritative row after.

Add tests for all three: a test that runs `compute_holdings` before prefetch/NAV
completes and asserts a later call is NOT stuck serving the stale cached result; a test
that starts a `compute_holdings` computation, lets an import commit + invalidate happen
"underneath" it (deterministically paused, not a real thread race), and asserts the
late-arriving stale write does not persist; and a two-session concurrent-insert test for
`_upsert_nav_history` asserting no uncaught `IntegrityError`.

## Round 2 fix + round 2 adversarial review (2026-08-13)

Round 2 closed finding 3 correctly (dialect-native `ON CONFLICT DO NOTHING` upsert,
verified by a two-session test). It attempted findings 1+2 with a per-member cache
**generation counter** (capture generation before computing, publish only if unchanged)
plus a rule that **holdings are only cached when every returned NAV is dated
`date.today()`**. Round 2's own review (`/codex:adversarial-review`, verdict:
needs-attention, "Do not ship") found this incomplete:

1. **[High] Generation check + cache publish still isn't atomic**
   (`holdings.py:193-197`). `compute_holdings` evaluates `generation_is_current` and
   then separately writes `_holdings_cache[cache_key]` — a synchronous
   `invalidate_holdings_cache` (from an import confirming) can run in the gap between
   those two steps: bump the generation and delete the entry, and then the stale
   computation still publishes its now-stale result right after, because it already
   passed its generation check before the bump. Narrower window than round 1, but not
   closed.
   **Direction for round 3:** protect generation-capture, invalidation/deletion, and the
   final compare-and-publish with the *same* process-local lock (e.g. one
   `threading.Lock` per cache, held across "check generation → publish" as a single
   critical section, and also held by `invalidate_holdings_cache` while it bumps the
   generation and deletes the entry) so the two can never interleave. Add a test that
   deterministically pauses a computation after its generation check but before
   publish, invalidates from "another" execution in that gap, and asserts the stale
   entry never gets installed.
2. **[Medium] "Today-only" cache eligibility defeats the cache's purpose during normal
   delayed-NAV periods** (`holdings.py:185-197`). Requiring every NAV to be dated
   exactly `date.today()` means the cache essentially never activates on weekends,
   market holidays, or before the day's NAV is published (routinely true for hours at a
   time — mfapi.in/AMFI typically publish evening) — precisely when Fix D was meant to
   stop the same-dashboard-load `/holdings` + `/allocation` double-`compute_holdings`
   problem from Fix D's original motivation. During those periods every request falls
   through to a full recompute.
   **Direction for round 3:** decouple cache eligibility from "is the NAV dated today."
   Cache the computed snapshot regardless of how fresh the underlying NAV is — staleness
   is already handled by (a) the generation bump on import, and (b) a **new** generation
   bump the background NAV-prefetch task (Fix A) should trigger for the affected
   members once it actually upserts newer NAV rows than what was cached, not on a
   calendar-date rule. If the prefetch fetches and finds nothing newer (e.g. NAV
   genuinely not published yet), don't bump — the existing cached snapshot remains
   correct to serve. This keeps the cache useful in the common case (delayed NAV) while
   still invalidating exactly when data actually changes. Add tests: a normal business
   day with delayed NAV publication where the cache still serves the same value across
   both `/holdings` and `/allocation` in one load; and a case where the background
   prefetch lands a genuinely newer NAV and the next request recomputes.

## Round 3 fix (2026-08-13)

Closed both remaining findings from round 2:

1. **Finding 1 (atomicity)** — added one process-local lock shared by cache
   lookup/generation-capture, compare-and-publish, *and* `invalidate_holdings_cache`'s
   generation bump + entry deletion, so the two can never interleave. New deterministic
   test pauses a computation after its generation check but before publish, invalidates
   from another thread in that gap, and asserts the stale entry never gets installed.
2. **Finding 2 (today-only eligibility)** — removed the "every NAV dated `date.today()`"
   cache-eligibility rule entirely; delayed/weekend/holiday snapshots are now cached
   normally. Staleness is instead handled by: (a) the existing generation bump on
   import, and (b) a new check in Fix A's background prefetch (`imports.py`) that
   compares each affected scheme's max stored NAV date before/after the prefetch and
   bumps the holdings-cache generation for that member only if the max date actually
   advanced — a prefetch that finds nothing newer does not bump, and the existing cached
   snapshot keeps serving. New tests cover a delayed-NAV business day (cache serves the
   same value across a `/holdings`-shaped and `/allocation`-shaped call) and a
   genuinely-newer-NAV-lands case (generation bumps, next call recomputes).

Files touched (all within the pre-agreed 4 implementation files + their existing test
files — confirmed via `git diff --stat`, no unrelated files touched):
`backend/app/api/imports.py`, `backend/app/services/dashboard/holdings.py`,
`backend/app/services/dashboard/nav.py`, `backend/app/services/import_/service.py`,
plus `backend/tests/api/test_imports_routes.py`,
`backend/tests/services/dashboard/test_holdings.py`,
`backend/tests/services/dashboard/test_nav.py`,
`backend/tests/services/import_/test_service.py`. 497 insertions / 36 deletions.

Independently verified (not just Codex's self-report): full backend suite
**324 passed, 2 skipped**, 23.07s, zero regressions (was 322/2 after round 2). Codex's
own run hit the same previously-documented sandbox-specific `TestClient` hang on the
first API test in its environment and could not complete a full-suite run itself —
noted per the completeness contract, not treated as a real issue (round 1 and round 2
both hit the identical sandbox artifact; it does not reproduce outside Codex's own
sandbox).

## Round 3 adversarial review (2026-08-13, verdict: needs-attention)

One new high-severity finding — a real design gap, not a coding slip:

1. **[High] One-shot prefetch can't catch NAV published later in the day**
   (`imports.py`'s prefetch date-advance check). The date-advance detection that bumps
   the holdings-cache generation only runs once, immediately after `confirm_import`. If
   the dashboard is first loaded before that day's NAV is published (the common case —
   mfapi.in/AMFI typically publish in the evening) and the user has already imported
   (so no further prefetch will ever run for them that day), nothing re-triggers the
   date-advance check once NAV does publish. Round 3's "cache regardless of freshness"
   fix (closing round 2's medium finding) means a snapshot computed before publication
   gets cached and then serves stale (yesterday's) NAV for the rest of that calendar
   day, with no self-correction. Root cause: Fix A's prefetch is one-shot by design
   (Fix C — the real recurring refresh job — is explicitly deferred), so there's no
   periodic hook left to catch a later publication.
   **Direction for round 4:** don't try to rebuild Fix C's recurring job (out of scope).
   Add a short, bounded TTL to Fix D's cache entries (e.g. ~15 minutes) so a stale entry
   self-heals on its own without needing an external invalidation trigger — short enough
   that the same dashboard load's back-to-back `/holdings` + `/allocation` calls (seconds
   apart) still hit the warm cache (preserving Fix D's original purpose), long enough
   that a user who keeps a dashboard tab open or revisits during the day gets a fresh
   compute well within the same session once NAV actually publishes. Add a test: cache
   a snapshot, advance monotonic/wall time past the TTL (via the same clock-injection
   pattern already used elsewhere in this cache's tests, if any — otherwise inject a
   clock), assert the next call recomputes rather than serving the expired entry; and a
   test that two calls inside the TTL window still share one cached computation
   (guarding against accidentally breaking Fix D's original same-load-dedup purpose
   while adding the TTL).

## Round 4 fix (2026-08-13)

Closed the round-3 review's finding: added a bounded TTL (15 minutes,
`_HOLDINGS_CACHE_TTL_SECONDS` in `holdings.py`) to Fix D's cache entries so a stale
entry self-heals without needing an external invalidation trigger. Each cache entry now
carries a `time.monotonic()` timestamp (via a patchable module-level
`_holdings_cache_clock`, not a real sleep in tests); expiration is checked while holding
the round-3 cache lock, and an expired entry is deleted and falls through the normal
miss path (capture generation → recompute → atomic compare-and-publish under the same
lock) — a TTL-triggered recompute is not a special case, it reuses round 3's atomicity
fix exactly. Calls inside the TTL window still share one cached computation (Fix D's
original same-load dedup purpose, unregressed). Cache comment extended to explain the
TTL exists to self-heal staleness in the absence of Fix C, not to replace it.

Files touched (still within the same 4 implementation files + their existing test
files): `backend/app/services/dashboard/holdings.py`,
`backend/tests/services/dashboard/test_holdings.py` (round 4 itself only needed these
two; `imports.py`/`nav.py`/`import_/service.py` were untouched this round, already
correct from round 3). 589 insertions / 36 deletions cumulative across all 4 rounds'
diff on the 8 files.

Independently verified: full backend suite **326 passed, 2 skipped**, 21.61s, zero
regressions (was 324/2 after round 3). Codex's own sandbox again hit the same
previously-documented `TestClient` hang on the first API test and reported focused
suite results instead (35 passed in touched-area suites) — consistent with rounds 1-3,
not treated as a real issue.

## Round 4 adversarial review (2026-08-13, verdict: needs-attention → accepted as documented limitation)

One new finding, severity dropped from high to **medium** (correctness-safe):

1. **[Medium] No per-key single-flight coordination for concurrent cold/expired
   misses** (`holdings.py`). The round-3/round-4 lock guarantees a stale computation
   can never *publish* over a fresher one, but it's released before the actual
   recompute runs — so two concurrent callers on the same cache key (exactly Fix D's
   original motivating scenario: the dashboard firing `/holdings` and `/allocation`
   together) can both observe a miss (cold cache, or an entry that just expired) and
   both run a full independent computation; the second publish just overwrites the
   first. No data corruption, no stale write survives — purely a redundant-computation
   cost, bounded to at most once per TTL window per key.

**Decision (user, 2026-08-13): accept as a documented limitation, do not dispatch a
round 5.** Closing this fully requires per-key single-flight coordination (one caller
computes, concurrent callers await and reuse its result) — a materially bigger
primitive than anything built across rounds 1-4, and judged not worth the added
complexity for this MVP given: severity is now medium and correctness-safe (all 3
original high-severity races from round 1 are fully closed and re-verified through
round 4); the cost is bounded and occasional, not sustained; and the real fix for
sustained dashboard-load performance is Fix C's deferred recurring job, not a more
elaborate process-local cache. Documented directly in code
(`backend/app/services/dashboard/holdings.py`, next to the existing cache-scope
comment) so it isn't silently forgotten.

## Final status

**Status: DONE.** Fix A (background NAV prefetch on import confirm), Fix B
(parallelized per-scheme NAV network fetch, DB access kept strictly sequential), and
Fix D (process-local per-day holdings cache with TTL-based self-healing and
lock-guarded atomic invalidation) are all implemented, tested, and independently
verified across 4 rounds of dispatch + mandatory adversarial review. All 3 round-1
high-severity findings and the round-3 high-severity finding are fully closed; the one
remaining round-4 medium finding is an accepted, documented limitation, not an open
defect. Full backend suite: **326 passed, 2 skipped**, zero regressions from the
pre-task baseline (was 156 before this task began; growth reflects new tests added
across all 4 rounds, not scope creep). Fix C (the real ADR-006 EventBridge+ECS
scheduled NAV refresh job) remains explicitly deferred to deployment phase, per the
original task scope.

## Round 5 (2026-08-14) — `warm_nav_history` had no TTL, and the frontend had no caching layer at all

Not a re-review of rounds 1-4's work (all of which held up, re-verified) — a **newly
introduced** gap in the same file, plus a previously-unexamined frontend root cause,
both surfaced by the user reporting that switching between Main Dashboard <->
Analytics Dashboard, and between family-combined <-> per-member views on both, stayed
slow on every repeat switch even once the underlying NAV/TER caches were warm.
Diagnosed via `superpowers:systematic-debugging` (Phase 1 root-cause investigation
before any fix):

1. **Backend:** `warm_nav_history` (`nav.py`, added after round 4 to fix the
   Category Ranking/Scorer multi-minute hang — see
   `analytics-phase2-frontend-log.md` and commit `15c03e1`) unconditionally did a full
   concurrent network re-fetch of NAV history for every scheme in a SEBI-category peer
   universe (30-150+ schemes) on **every** call, with none of `compute_holdings`'s
   TTL-cache treatment from rounds 1-4 of this same doc. Every repeat visit to Category
   Ranking/Scorer re-downloaded the entire peer universe from `mfapi.in` from scratch.
   **Fix:** added a 15-minute process-local TTL cache (`_nav_warm_cache`,
   `_nav_warm_lock`, `_nav_warm_clock`, `_NAV_WARM_TTL_SECONDS`) to `warm_nav_history`,
   mirroring `holdings.py`'s exact pattern from this doc's rounds 1-4 — a scheme warmed
   within the TTL window is skipped on a subsequent call. Timestamp is recorded even on
   a failed fetch (best-effort, matching this module's existing degrade-gracefully
   posture) so an mfapi.in outage can't turn every request into a re-fetch storm. Two
   new tests in `test_nav.py` (TTL-window dedup, TTL-expiry re-fetch); full backend
   suite 362 passed, 2 skipped, zero regressions (was 360/2 before this round).
2. **Frontend:** there was no caching layer anywhere in the frontend (confirmed —
   no react-query/SWR, `lib/apiClient.ts` was a bare `fetch` wrapper). `AnalyticsView`/
   `DashboardView` refetch their full GET set on every mount via `useEffect`, and
   `MainDashboardFlow.tsx`'s `activeTab === "dashboard" ? <DashboardView/> :
   <AnalyticsView/>` ternary fully unmounts/remounts the inactive view on every tab
   switch — so every dashboard<->analytics switch, and every family-combined<->
   per-member switch, re-issued the entire GET set from scratch regardless of how
   recently the same data had already loaded.
   **Fix:** added a short (60s), session-only, in-memory GET-response cache
   (`cachedFetch`/`invalidateApiCache` in `lib/apiClient.ts`, using `Response.clone()`
   so the cached body can be read more than once), wired into `dashboard/api.ts`'s and
   `analytics/api.ts`'s shared `authFetch` helpers (mobile views reuse these same
   modules, so they're covered without separate changes). `invalidateApiCache()` is
   called from `import/api.ts`'s `confirmImport` and `postOpeningBalance` — the two
   mutations that change dashboard/analytics-visible data — so a fresh import or
   opening-balance resolution is never masked by the cache window. Deliberately did
   **not** change `MainDashboardFlow.tsx`'s unmount/remount architecture itself
   (bigger, riskier change than this fix needed) — the response cache alone means a
   remount's refetch resolves from memory instead of the network, which is what
   actually made repeat switches feel slow. 5 new tests in a new
   `lib/apiClient.test.ts`; full frontend suite 202/202 passing (1 unrelated,
   confirmed-transient sandbox module-resolution flake on `ImportFlow.test.tsx`, passes
   7/7 in isolation), `tsc -b --noEmit` clean.

Files touched: `backend/app/services/dashboard/nav.py`,
`backend/tests/services/dashboard/test_nav.py`, `frontend/src/lib/apiClient.ts`,
`frontend/src/lib/apiClient.test.ts` (new), `frontend/src/features/dashboard/api.ts`,
`frontend/src/features/analytics/api.ts`, `frontend/src/features/import/api.ts`.

**Deferred, not in scope for this round:** `analytics/ter.py`'s
`_ensure_ter_fresh`/`_missing_current_month_ter` has a latent design flaw where a
single held scheme that can never resolve a fuzzy AMFI TER match (closed-end fund,
FMP, discontinued scheme) causes a full bulk AMFI TER refresh on *every* TER-related
request forever, not just once. Confirmed not currently active for any real holdings
in this build (all schemes resolve), so left as a documented latent issue rather than
fixed speculatively — revisit if a real portfolio ever hits it.

## Round 6 (2026-08-17/18) — split into two sibling handoff docs, PR #4 merged

The user's first-login "still 30s" report led to two further, independent fixes in the
*same* end-to-end NAV-fetch pipeline, tracked in their own dedicated handoff docs rather
than appended here (each got its own worktree, Codex dispatch, and adversarial-review
cycle): `Docs/orchestration/nav-fetch-connection-reuse-handoff.md` (this file's own
`nav.py` opening a brand-new `httpx.AsyncClient` per call with no de-dup across its 3
concurrent callers — this doc's rounds 1-5 never addressed connection reuse, only
prefetch timing/parallelization/caching) and
`Docs/orchestration/import-preview-concurrency-handoff.md` (an earlier, up-until-then
undiagnosed bottleneck in the CAS-upload preview step, before the user even reaches the
dashboard this doc covers). Both merged as
[PR #4](https://github.com/ayushkarnawat/MVP_V1_MF_only/pull/4) — see
`session.md`'s "First-login dashboard load-time fix" section for the full narrative.

## Task

Fix three related performance issues in the Main Dashboard backend, all rooted in
`backend/app/services/dashboard/nav.py`'s on-demand NAV fetch (the local-dev-first
stand-in for the not-yet-built ADR-006 EventBridge NAV refresh job — that real job is
explicitly OUT of scope here, deployment-phase work, do not build it).

**Fix A — background NAV prefetch on import confirm.**
`backend/app/api/imports.py`'s `confirm_import_route` (`POST /imports/confirm`) returns
as soon as `confirm_import()` commits. The first dashboard load after a signup/import
is the first time any of the member's schemes' NAVs get fetched from `mfapi.in` — so
the user's *first* dashboard view pays for every scheme's full historical-NAV fetch,
serially, inline in the request. Add a `BackgroundTasks` param to the route; after a
successful `confirm_import`, schedule a task that prefetches NAV history (as of
`date.today()`) for every scheme now held by that household member, using a **fresh**
`SessionLocal()` (from `backend/app/db/session.py`) — never the request-scoped `db`,
which closes when the response returns. The background task must never raise into
FastAPI's task runner: catch and swallow/log, matching `get_nav_on_or_before`'s existing
"degrade gracefully, never crash the request" convention. `ImportConfirmResponse`'s
schema (`added`, `skipped`, `import_id`) does not change — this is fire-and-forget,
not something the client waits on or gets a result from.

**Fix B — parallelize the per-scheme NAV fetch inside `compute_holdings`.**
`backend/app/services/dashboard/holdings.py::compute_holdings` loops over every
`(member_id, scheme_id)` group and does `await get_nav_on_or_before(db, scheme,
date.today())` **sequentially** (line 115) — each iteration is a full round trip to
`mfapi.in` if not cached. For a member with N holdings, this is N sequential external
HTTP calls on every dashboard load until Fix D's cache is warm. Restructure this so the
*network* fetches for schemes needing one happen concurrently, while all
`Session`/DB access stays strictly sequential (see Constraints below for why this
split matters — it is the one non-obvious part of this task).

**Fix D — process-local per-day cache for `compute_holdings`.**
`compute_holdings` is invoked independently by `/holdings` and by `/allocation`
(`allocation.py` line 31 calls `compute_holdings` again) on the same dashboard load —
today's `DashboardView.tsx` fires both `getMemberHoldings`/`getAggregateHoldings` and
`getMemberAllocation`/`getAggregateAllocation` in one `Promise.all` on mount, so the
full FIFO+NAV computation runs twice, back to back, for the same member set and the
same day. Add an in-memory cache in `holdings.py` keyed by
`(tuple(sorted(household_member_ids)), date.today())`, invalidated explicitly by a new
hook called from `confirm_import` (`backend/app/services/import_/service.py`) right
after its commit succeeds — a fresh import must never serve a stale cached holdings
snapshot. No DB schema change. No change to any response shape.

## Constraints

- **`Decimal`, never `float`** (CLAUDE.md non-negotiable) — every value already flowing
  through `nav.py`/`holdings.py` is `Decimal`; keep it that way through any refactor.
- **This is local-dev-first, not the real fix** — Fix C (the actual ADR-006
  EventBridge+ECS scheduled job) is explicitly deferred to deployment phase. Don't
  attempt it, don't add cloud-specific code paths, don't gate behavior on an
  environment flag for it.
- **SQLAlchemy `Session` concurrency**: a single synchronous `Session` (this project
  uses sync `Session`, not `AsyncSession`, inside `async def` routes/services — see
  `nav.py`'s existing pattern) must never have its reads/writes interleaved across
  concurrently-running coroutines. For Fix B, `asyncio.gather` (or equivalent) may ONLY
  wrap the pure-network leg — i.e. something shaped like `_fetch_nav_history(amfi_code)`
  — never the DB-touching legs (`_latest_cached_on_or_before`, `_upsert_nav_history`).
  The safe shape is: (1) sequentially decide, per scheme, whether a trustworthy cache
  hit already exists (DB reads, sequential); (2) `asyncio.gather` the network fetches
  only for schemes that need one; (3) sequentially upsert every fetched result into the
  DB and read back the final NAVs (DB writes, sequential). This likely means adding a
  new function (e.g. `get_navs_on_or_before(db, scheme_date_pairs)`) to `nav.py` rather
  than trying to retrofit `get_nav_on_or_before` in place — your call on the exact
  shape, but the network/DB isolation rule is not negotiable.
- **Fix D's cache is deliberately process-local (in-memory), not a new DB table, not
  Redis** — acceptable per CLAUDE.md's "don't gold-plate" principle because it becomes
  moot once Fix C's real background job exists; it does NOT need to be multi-instance
  safe. State this limitation in a code comment where the cache is defined.
- **No raw CAS PDF storage, no PAN persistence** — not directly touched by this task,
  but don't introduce anything that violates it while wiring the background task
  (e.g. don't pass PAN-bearing objects into the background task's closure).
- **Test-driven, always** — red/green/refactor. `compute_holdings`, `get_nav_on_or_before`
  / the new batched function, and `confirm_import`'s background scheduling all need
  tests. Existing test fixtures for the holdings engine are hand-built known-answer
  fixtures (per session.md) — follow that existing style, don't introduce a new mocking
  framework/pattern for this.
- Full backend suite must stay green (currently 156 passing — confirm the actual current
  count with `pytest` before starting, since this may be stale) with zero regressions.

## Approaches considered and rejected

- **Reworking `nav.py`'s existing `get_nav_on_or_before` to itself do the gather
  internally, called once per scheme as before**: rejected — the caller
  (`compute_holdings`) is the one that knows the full batch of schemes needing a
  lookup in one dashboard load; batching has to happen at the call site, not by making
  the single-scheme function secretly concurrent with itself (it isn't called
  concurrently with itself under the current per-scheme loop, so there'd be nothing to
  batch).
- **A DB-level or Redis-backed cache for Fix D instead of in-memory**: rejected as
  gold-plating for this MVP phase per CLAUDE.md — a new table/cache-service adds
  migration and infra surface for a problem that Fix C's real scheduled job will make
  moot. Revisit only if deployment reveals multi-instance staleness is a real problem.
  Do not build this now.
- **Making `compute_holdings`'s DB session itself async (`AsyncSession`)**: rejected —
  out of scope; ADR-Technical-Stack-Decisions and the existing codebase use sync
  `Session` throughout the dashboard services layer; switching one function to
  `AsyncSession` while everything around it stays sync would be a bigger, riskier change
  than this task calls for, and isn't what's blocking performance here (the DB queries
  themselves are fast — the external HTTP calls are the bottleneck).

## Open questions

- None outstanding for Fix A/B. Flag back rather than guess if the FIFO holdings engine
  test fixtures use a mocking strategy for `httpx`/`mfapi.in` calls that doesn't
  obviously extend to a batched/gathered fetch — describe what you find rather than
  inventing a new test double pattern.
