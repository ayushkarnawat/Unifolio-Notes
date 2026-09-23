# Dashboard load time: connection reuse and import-preview concurrency

## For stakeholders

A colleague reported that the very first dashboard load after signing up
still took around 30 seconds, even after an earlier round of fixes
(`dashboard-nav-perf-handoff.md`, see the 2026-08-13→08-18 cache-race
journey entry) had already addressed a different set of problems in the
same area. Investigating this fresh, the team found two more causes, both
about how the app talks to the outside government NAV data source rather
than anything wrong with the cached-race fixes already shipped: every fetch
of a fund's price history was opening a brand-new network connection
instead of reusing one, and three different parts of the app were
independently re-fetching the same fund's data at the same time instead of
sharing one request. Fixing both (reusing connections, and having
duplicate simultaneous requests share one answer instead of each doing the
work) made the affected operations roughly 5-25 times faster in
controlled benchmarks. A closely related sibling problem was found and
fixed the same day in the CAS-import preview screen, which had the same
"open a new connection every time" pattern plus a fully sequential,
non-parallel fetch loop. Both fixes were merged together into one pull
request the same day.

## Technical detail

### Investigation

Live-verified against the real `api.mfapi.in` NAV data source. Root cause
1: `_fetch_nav_history` (`backend/app/services/dashboard/nav.py`) opened a
new `httpx.AsyncClient()` per call — no connection reuse across requests.
Root cause 2: three real callers of the same NAV-fetch path (background
prefetch, `/holdings`, `/allocation`) could race on identical schemes with
zero de-duplication, each independently re-fetching the same data.
Benchmarked: 3.60s vs 0.63s for a shared client across 20 schemes
(~5-6x), and 13.39s vs 0.69s for a 50-scheme/3-caller race simulation with
single-flight de-dup added (~19x).

A second, sibling bottleneck was root-caused in the same investigation
session: the CAS-upload/preview path's `build_import_preview` ran a fully
sequential per-scheme loop (no `asyncio.gather`), `enrich.py`'s
`MfApiClient` had the same new-client-per-call pattern as the pre-fix
`nav.py`, and `get_scheme_category` fetched a full-history endpoint when it
only needed to read the `meta` field (live-confirmed the `/latest`
endpoint returns the same tiny `meta` payload). Live-benchmarked 7.74s vs
0.31s for 30 schemes (~25x).

### Fix

`nav.py`: a module-level, lazily-created shared `httpx.AsyncClient` guarded
by a double-checked `asyncio.Lock`, with `httpx.Limits(max_connections=100,
max_keepalive_connections=100)`, plus a per-`amfi_code` single-flight
de-duplication registry cleaned up on completion (success or failure).

`enrich.py`/import preview: the same lazy shared-client pattern (adapted
for `enrich.py`'s already-async `_get_json` accessor, unlike `nav.py`'s
sync one), `get_scheme_category` switched to the `/latest` endpoint, and
`build_import_preview`'s per-scheme loop parallelized via `asyncio.gather`
while preserving input order.

### Review and correction rounds

Both fixes went through this project's mandatory adversarial-review gate,
each surfacing genuine findings that were fixed before being marked done:

- **`nav-fetch-connection-reuse`**: implementation round found 2 missing
  test-coverage gaps (exception-path, cancellation-path/`asyncio.shield`,
  `asyncio.Event`-overlap); closed, full suite 369 passed/2 skipped. A
  scoped re-review then returned approve with zero new findings (both
  prior nits confirmed closed).
- **`import-preview-concurrency`**: the orchestrator's own direct review of
  Codex's diff, before merging, found one Decimal-discipline style
  inconsistency (a new test used `Decimal("1.0")` for a plain `float`
  confidence field) and fixed it before committing. The subsequent
  adversarial review then found **1 Major**: parallelizing `resolve_scheme`
  via `asyncio.gather` introduced a new race, where concurrent no-AMFI-code
  schemes could all observe `self._schemes is None` before any one
  finished fetching, causing each to independently download the entire
  ~20k-scheme AMFI directory — directly undermining the fix's own goal —
  plus 2 Minor findings (missing tests for partial-failure exception
  propagation and concurrent first-access client-lock safety). The Major
  was fixed with the same double-checked-lock pattern already used for the
  shared HTTP client; the exception-propagation Minor was fixed with a new
  test; the concurrent-client-lock Minor was deliberately deferred as
  lower-value, flagged for the re-review to confirm acceptable. A first
  re-review attempt returned a stale verdict (contradicted by direct file
  inspection — traced to a reused Codex session thread rather than a
  genuine re-read) and was discarded; a fresh re-review dispatch correctly
  confirmed the Major closed and accepted the deferred Minor as a
  documented gap.

### Result

Both branches (`perf/nav-fetch-connection-reuse`,
`perf/import-preview-concurrency`) merged cleanly (disjoint files, no
conflicts) into one combined branch `perf/dashboard-load-time`. Full
backend suite re-verified on the combined branch: 374 passed / 2 skipped,
zero regressions. This sandbox had no git push credentials and no `gh`
CLI; the exact push and `gh pr create` commands were handed to the user to
run from a credentialed machine. The user opened **PR #4**
(`https://github.com/ayushkarnawat/MVP_V1_MF_only/pull/4`) against
`feat/enhanced-ui`. Both bottlenecks were root-caused, implemented, tested,
adversarially reviewed across two rounds each, and merged the same day
(2026-08-17).

### Related

- Overlaps with, and follows on from, the [2026-08-13 → 2026-08-18
  dashboard NAV and holdings cache race hardening](2026-08-13-dashboard-nav-and-holdings-cache-race-hardening.md)
  journey entry — that work fixed a different set of concurrency races in
  the same caching layer; this entry's investigation found the *remaining*
  ~30s first-load cause was a connection-reuse/de-dup gap, not a repeat of
  the earlier bugs.
- The `import-preview-concurrency` fix and the [2026-08-18 → 2026-08-19
  BUG-001/DATA-001 analytics load-time and correctness fixes](2026-08-17-bug-001-data-001-analytics-load-and-correctness-fixes.md)
  journey entry both target performance in the Analytics/dashboard area of
  the app in the same general window, but are independent investigations
  targeting different endpoints — not duplicates of each other.
- Evidence: `08-evidence/documents/orchestration/nav-fetch-connection-reuse-handoff.md`
- Evidence: `08-evidence/documents/orchestration/import-preview-concurrency-handoff.md`
- Evidence: `08-evidence/documents/orchestration/delegation-log.md` (2026-08-17 entries)
