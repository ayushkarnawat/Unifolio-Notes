# BUG-001/DATA-001 — Post-implementation performance assessment

**Date:** 2026-08-19
**Status:** DONE (investigation/documentation only, no code changed)
**Scope:** pre-merge sanity check of the Analytics dashboard's loading time,
scalability, and efficiency, on branch `bug-001-data-001-implementation`,
requested before merging into `feat/enhanced-ui`.

## Why this exists

`Docs/orchestration/bug-001-findings.md` documents the *original* three
performance causes found during the BUG-001 investigation (TER negative-cache
full-feed refetch, Category Ranking's sequential per-scheme loop, Scorer's
synchronous full-category-universe rebuild). This doc is the follow-up check,
done after all 7 implementation items plus the Analytics Correction Plan
round 2 work landed on this branch: does the code, read fresh today, actually
back up the "fixed" claim, and is anything new left over? It is a direct
re-read of the current service files — not a re-statement of memory or the
original findings doc.

## Method

Full read of every Analytics backend service file plus both orchestration
layers, no edits made during the read:
`backend/app/api/analytics.py`,
`frontend/src/features/analytics/AnalyticsView.tsx`,
`backend/app/services/analytics/{allocation,ter,scorer,category_ranking,
risk_metrics,scheme_universe,benchmark,nse_indices_client}.py`,
`backend/app/services/dashboard/nav.py`.

## Findings

### 1. Loading time — no waterfall, no shared spinner

`AnalyticsView.tsx` fires 5 independent fetch groups in one `useEffect`
(allocation alone; `Promise.all([ter, direct-regular-ter])`; category-ranking
alone; score alone; `Promise.all([benchmark, fund-benchmark])`), each with its
own boolean loading state and its own `.catch(logSectionError(...))`. A slow
section can never block a fast one. Only allocation's failure surfaces as a
full-page error, since it drives the hero "Total Portfolio Value." This is
the direct fix for the original BUG-001 symptom (a single shared loading
state blocking the whole page behind the slowest section).

`backend/app/api/analytics.py` backs this with 15 independent REST endpoints
under `/analytics` — no monolithic combined-fetch endpoint exists, so the
frontend's per-section independence has a matching per-section backend
round-trip.

### 2. Caching — expensive work happens at most once per TTL window

- `scorer.py` / `category_ranking.py`: 15-minute TTL cache keyed by
  `sebi_category`, day-aware invalidation. **Shared across endpoints** —
  Category Ranking's own endpoint and Scorer's `_compute_category_component_scores`
  both read the same `_category_returns` cache, so a category computed for
  one section is free for the other.
- `nav.py`: 15-minute NAV warm-cache, single-flight `asyncio.Task`-based
  dedup keyed per `amfi_code` (concurrent callers for the same scheme
  collapse into one in-flight fetch, `asyncio.shield`-protected), and a
  lazily-constructed shared `httpx.AsyncClient` with
  `httpx.Limits(max_connections=100, max_keepalive_connections=100)`.
- `ter.py`: the previously-documented Item 3 fix — a 15-minute cross-thread/
  cross-loop refresh backoff via `_claim_ter_refresh_slot()` — is intact; TER
  refresh is one bulk AMFI-feed fetch, never per-scheme.
- `scheme_universe.py`: the ~40k-row AMFI universe file is disk-cached with a
  24h TTL and memoized in-process (`self._rows`) after first load per
  process lifetime.
- `nse_indices_client.py`: `ensure_index_history_fresh` skips the network
  fetch entirely once the DB's cached date bounds already cover the
  requested range — in practice, at most one real NSE fetch per index per
  day.

### 3. Scalability — bulk/bounded SQL, N+1s replaced

- `category_ranking.py`'s `_bulk_nav_on_or_before` is one `MAX(date) GROUP BY`
  query per target date across the whole category universe, not one query
  per scheme × date (the original BUG-001 finding for this file).
- `scorer.py`'s `compute_portfolio_score` groups held schemes by
  `sebi_category` so category-wide work (`get_category_universe`,
  `_category_component_scores`, `_category_ter_context`) runs once per
  **distinct category held**, not once per held fund — this was the original
  Scorer build's High-severity review finding, already fixed and reconfirmed
  intact here.
- `benchmark.py`: `_investment_transactions`/`_fund_level_transactions` are
  each exactly one `Folio.id` query + one `Transaction` query for the whole
  household (no per-scheme querying); `ensure_index_history_fresh` is called
  once per `(index, request)` combination — repeat calls for schemes sharing
  an index just hit the in-memory cache-bounds check, never repeat network
  I/O.
- `allocation.py` is the cheapest section end-to-end: one (already cached)
  `compute_holdings` call, one bulk `Scheme.id.in_()` query, zero external
  network calls, pure in-memory `defaultdict` aggregation.

### 4. Two low-severity, not-yet-fixed observations (new this pass)

Neither was previously documented; neither blocks the merge — both are
optional follow-ups under CLAUDE.md's "don't gold-plate" MVP scoping.

1. `nse_indices_client.py`'s `_fetch_index_history` opens a fresh
   `httpx.AsyncClient` per call rather than reusing a shared client the way
   `nav.py` does. Low impact: only 4 indices exist, and most calls never
   reach the network at all due to the cache-bounds short-circuit in
   Finding 2 above.
2. `scheme_universe.py`'s in-process `self._rows` memoization means the 24h
   disk-cache TTL is only re-checked on first access per process lifetime,
   not continuously. A staleness nuance (a long-lived process could serve a
   >24h-stale universe file), not a correctness bug — the AMFI universe file
   changes rarely enough that this is unlikely to matter within an MVP's
   process-restart cadence.

## Conclusion

Every performance cause `bug-001-findings.md` originally identified (TER's
negative-cache full-feed refetch, Category Ranking's sequential per-scheme
loop, Scorer's per-fund category rescan, and the frontend's shared-spinner
hang) has a corresponding, verified-in-place fix on this branch. The
resulting architecture — per-section independent fetch/loading, shared
category-wide TTL caching, bulk/bounded SQL, and a connection-pooled/
deduplicated HTTP client for NAV fetches — is solid for the MVP's scale. The
two items in Finding 4 are optional, low-severity follow-ups, not gaps in
what was scoped. No further work is required before merging this branch into
`feat/enhanced-ui`.
