# BUG-001 — Analytics load investigation

Status: REVIEW

## Scope and repro

Investigation only; no application code was changed. The live setup used the seeded
`backend/unifolio_dev.db`, member `6f9e78bf-68dd-4d25-b248-e31c8a4d5c17`, the
seeded bearer session, and single-worker `uvicorn app.main:app --port 8001`.
The portfolio holds three real AMFI-coded direct-growth Large Cap schemes. The
Large Cap universe contained 143 real schemes and the warmed database contained
approximately 410,000 NAV-history rows.

## Result summary

The strongest dynamically confirmed cause is TER refresh: one missing current-month
row launches a sequential, whole-country AMFI pagination, and an unresolved/missed
scheme has no negative cache or backoff. Category Ranking has a separate category-wide
cost: it calculates two returns sequentially for every scheme after warming NAV; its
four runs alternate between about 43s and about 8s rather than settling at a stable
warm floor. Scorer contains a third, structurally
blocking category-wide path: it synchronously builds full-history monthly series for
every returning scheme without yielding — and, unlike TER/Category Ranking, this cost
**never drops on repeat calls** (262.02–262.68s warm vs 332.2s cold), because nothing
about the category-wide series build is cached across requests.

Codex's sandbox could not open sockets to `127.0.0.1` (`curl: (7) Operation not
permitted`), so the orchestrator ran the remaining `/score`/`/benchmark` timings and
the concurrent-load test directly against the same live server after Codex's pass
completed. All numbers below are real, backend-measured.

## Measured waterfall

| Endpoint | Cold / observed range | Warm floor | Run 1 | Run 2 | Run 3 | Run 4 / additional sample | Verification result |
|---|---:|---:|---:|---:|---:|---:|---|
| `/allocation` | 0.0099–4.01 s | — | 1.78 s | 4.01 s (forward-order concurrent test) | 1.21 s | 0.0099 s (reverse-order concurrent test) | Consistently cheap |
| `/ter` | 185.8–277.0 s while cold/re-fetching | **0.0297 s** | 185.8 s | 277.0 s | 0.0297 s | — | Severe while cold/re-fetching; negligible once the feed is fully cached/ingested |
| `/category-ranking` | 8.31–43.56 s | Not stable | 42.77 s | 8.31 s | 43.56 s | 8.71 s | Alternates between about 43s and about 8s; not a clean cold/warm split |
| `/score` | 332.2–394.21 s cold/concurrent; **262.0–262.7 s** repeated | **262.0–262.7 s** | 332.2 s | 262.68 s | 262.02 s | 394.21 s (reverse-order concurrent test) | **Never gets cheap** — the category-wide series build re-runs its full cost on every call |
| `/benchmark` | 63.0 s | 1.5–2.8 s | 63.0 s | 2.81 s | 1.51 s | — | Measured pattern confirms a one-time cold cost; drops ~40x once cached |

For a portfolio spanning the real ticket's ~8 SEBI categories, Category Ranking's
single-category timings suggest category count may amplify its cost, but any claim of
~8s per category and linear scaling to ~260s across eight categories is an unverified
extrapolation, not a multi-category measurement. Scorer's ~260s-per-request repeated
cost does cover category-wide work — Scorer in particular would not improve with repeat
navigation the way the other four endpoints do, matching the ticket's report that
Scorer specifically "does not load at all."

## Concurrent-load verification

Executed directly because Codex's sandbox network restriction did not apply to the
orchestrator's environment. Two independent samples, in both start orders, show no
observed cross-request blocking: forward-order, `/allocation` completed in 4.01s
while a ~262s `/score` request was in flight; reverse-order, `/score` started first,
then `/allocation` started 2s later and completed in 0.0099s while the 394.21s
`/score` request was still in flight.

This is consistent with — but does not conclusively prove — the hypothesis that the
slow request's genuine `await` points (`warm_nav_history` via `asyncio.gather`, and
httpx calls) let other requests interleave despite `get_db`
(`backend/app/db/session.py:13`) being a synchronous generator dependency and the
routes being `async def`. It rules out simple total blocking for the full request
duration, but does not rule out blocking during specific synchronous stretches within
the request. Probing more offsets across `/score` remains the conclusive follow-up.

## Blocking paths and evidence

### 1. TER: confirmed primary timing cause

Request path (stack-trace level):

`GET /ter` → `_weighted_ter_for_holdings` (`backend/app/services/analytics/ter.py:101-106`)
→ `_ensure_ter_fresh` (`ter.py:60-68`) → `refresh_ter_data`
(`backend/app/services/analytics/amfi_ter_client.py:205-232`) →
`_fetch_ter_rows` (`amfi_ter_client.py:118-154`).

The trigger counts held schemes covered in the current month and refreshes whenever
coverage is short (`ter.py:47-68`). The fetch uses `MF_ID=All`, 500 rows per page,
and advances `page += 1` in one awaited loop (`amfi_ter_client.py:125-153`), so
portfolio size does not bound the national scan. Persistence skips unresolved plan
variants and fuzzy matches below `MIN_MATCH_CONFIDENCE = 0.55`
(`amfi_ter_client.py:61,221-230`). There is no record of a failed/missing match, so
the next request sees the same gap and repeats the scan.

Timing evidence: run 1 was 185.8s cold, run 2 was 277.0s while the feed was evidently
still cold/re-fetching, and run 3 was 0.0297s once the feed was fully cached/ingested.
Thus 277.0s is not a stable warm floor; the true measured warm floor is negligible.

### 2. Category Ranking: confirmed independent category-wide cost

Request path:

`GET /category-ranking` → `compute_category_ranking`
(`backend/app/services/analytics/category_ranking.py:132-194`) → once per unique held
category, `get_category_universe` then `_category_returns` (`:168-170`) →
`warm_nav_history` then a sequential universe loop calling `_scheme_return` for 3y
and 5y (`:82-91`).

Timing evidence across four runs was 42.77s / 8.31s / 43.56s / 8.71s for 143 Large
Cap schemes and approximately 410,000 NAV rows. The alternating ~43s/~8s pattern is
not a clean cold-then-warm model and is not yet explained: the 15-minute NAV warm TTL
in `nav.py` does not account for alternation within one TTL window. The in-request per-category cache avoids
repeating one category for multiple held funds (`:143-171`), but does not remove the
per-scheme loop or persist computed returns across requests.

`build_monthly_series` adds an amplifying query defect used by Scorer's risk work:
its NAV query has only an upper bound (`backend/app/services/analytics/risk_metrics.py:83-87`),
so it loads each scheme's entire cached history since inception even though callers
provide a bounded month-end window.

### 3. Scorer: strong unverified event-loop-blocking hypothesis

Request path:

`GET /score` → portfolio scoring grouped by held category →
`_category_component_scores` (`backend/app/services/analytics/scorer.py:61-115`) →
`_category_returns` → the synchronous comprehension
`series_by_scheme = { ... build_monthly_series(...) for scheme_id in returns }`
(`scorer.py:68-71`). Each `build_monthly_series` performs the unbounded synchronous
query above. There is no `await` in the comprehension, so on a single Uvicorn event
loop this stretch cannot yield to other requests. The work covers the entire category
universe, not merely the three held schemes.

Scorer also calls `_category_ter_context` once per unique category, which invokes
`_ensure_ter_fresh` for every scheme in that universe (`scorer.py:118-133`), inheriting
the TER refresh problem. Grouping shared category work is already present and is not
a missing optimization.

Confirmed timing: 332.2s / 262.68s / 262.02s across three runs — the only endpoint of
the five whose cost does not meaningfully drop once "warm." The concurrent-load test
(above) did not catch it stalling a concurrent fast request in this one sample, but
per the caveat above that does not rule out blocking during its synchronous stretches.

### 4. Benchmark/NSE: confirmed cold-only cost, not a hang

`compute_portfolio_vs_benchmarks` iterates the four indices sequentially
(`backend/app/services/analytics/benchmark.py:121-143`). Each calls
`ensure_index_history_fresh` (`benchmark.py:75-83`), whose POST uses a 30 s timeout
but an `httpx.AsyncClient` without `follow_redirects=True`
(`backend/app/services/analytics/nse_indices_client.py:45-58`).

The measured pattern (**63.0s / 2.81s / 1.51s across three runs**) confirms a one-time
cold cost rather than a recurring hang. The most likely mechanism, based on
`benchmark.py`'s four sequential index calls and `nse_indices_client.py`'s 30s
timeouts without `follow_redirects=True`, is a slow or redirected first fetch per
index that is then cached. Response-level tracing did not confirm that mechanism this
session, so the timing conclusion is confirmed but the mechanism remains the leading
hypothesis. This rules out Benchmark as a contributor to
the ticket's "still spinning after 10+ minutes" symptom on repeat views, though the
first cold load of a session does cost real time. Whether the cached data is
*correct* (given the observed 302/no-redirect-follow behavior) is a DATA-001 concern,
not a BUG-001 timing one.

### 5. Suspects ruled out

- Allocation measured 1.78 s and has no category-universe expansion.
- `amfi_aaum_client.py` is not invoked by these live endpoint paths; analytics reads
  already-populated `scheme_aaum` data.
- `xirr.py` is bounded to 100 Newton-Raphson iterations and showed no performance
  concern in code review.

## Frontend orchestration

The frontend is not a single waterfall gate. Analytics exports independent fetch
functions for allocation, TER, category ranking, score, and benchmark
(`frontend/src/features/analytics/api.ts:41-116`); each calls `authFetch`/`cachedFetch`
independently (`api.ts:21-38`). There is no one `Promise.all` in this API layer that
must resolve before all sections render. Successful GET responses have a 60-second
cache (`frontend/src/lib/apiClient.ts:31-50`). Thus the observed section delays arise
from their backend request paths; frontend caching can mask a repeat for 60 seconds
but does not cause the cold delays.

## Smallest proposed fixes (independently shippable; no code implemented)

1. **TER refresh suppression.** Persist a time-bounded negative result/backoff for a
   scheme/month when its plan variant is unresolved or its AMFI match fails. Coalesce
   concurrent whole-feed refreshes and avoid re-running the national scan while that
   result is valid. This directly targets the measured 185.8/277.0 s path.
2. **Category-return query reduction.** Replace the sequential two-lookups-per-scheme
   loop with a bulk pair-of-dates NAV lookup for the category/window and reuse computed
   category returns across requests with an explicit freshness key. This targets the
   measured 42.77s / 8.31s / 43.56s / 8.71s path without depending on the Scorer
   change. Investigate the unexplained within-TTL alternation as part of this fix.
3. **Scorer: cache category-wide series across requests + bounded series build.**
   This is the single highest-priority fix — it's the only one of the five endpoints
   whose cost never drops on repeat calls (confirmed 262s floor across 2 warm runs).
   Cache `series_by_scheme`/category-level scoring results with an explicit freshness
   key (mirroring the fix already proposed for Category Ranking), add the missing
   lower date bound to `build_monthly_series`, and consider moving the remaining
   synchronous CPU/DB work off the event loop as a secondary, structural
   risk-reduction step (the two concurrent-load samples did not catch it stalling a
   concurrent request, but did not rule out stalls in specific stretches — see caveat
   above).
4. **Benchmark: verify NSE redirect handling.** Cold cost (63s) is real but one-time
   and self-resolving (2.8s/1.5s warm) — lower priority than TER/Category
   Ranking/Scorer for BUG-001 specifically. Whether the cached result is *correct*
   given the observed 302 is DATA-001's concern (see `data-001-findings.md`).

## Open questions and data notes

- Two concurrent-load samples, one in each start order, did not catch cross-request
  blocking; a more exhaustive test firing a fast probe at several offsets across
  score's ~262s duration would be needed to fully rule blocking in or out. Flagged as
  a cheap follow-up, not pursued further here since the confirmed per-endpoint costs
  already justify prioritizing a fix regardless of the answer.
- The seeded ICICI Prudential Bluechip `scheme_ter` value was exactly `0`, versus
  HDFC 1.02% and Nippon 0.14%. DATA-001's findings cover this (see
  `data-001-findings.md`) — note DATA-001 also found the seed script's AMFI
  code→name pairs were themselves wrong, so treat any TER-identity conclusions there
  with that caveat in mind.
- Benchmark data correctness (as opposed to timing) remains open — see DATA-001.

## Verification checklist against handoff

1. Score/Benchmark three runs: **completed** by the orchestrator directly (Codex's
   sandbox couldn't reach localhost) — 332.2s/262.68s/262.02s and 63.0s/2.81s/1.51s
   respectively.
2. Concurrent test: **completed in both start orders** — forward-order allocation
   completed in 4.01s during a ~262s score request; reverse-order score started first,
   allocation started 2s later and completed in 0.0099s during the 394.21s score run.
3. Three full five-endpoint passes: **completed at the endpoint-measurement level** —
   allocation has 1.78s / 4.01s / 1.21s plus the 0.0099s reverse-order sample; TER has
   185.8s / 277.0s / 0.0297s; Category Ranking has 42.77s / 8.31s / 43.56s / 8.71s;
   Score has 332.2s / 262.68s / 262.02s plus 394.21s; Benchmark has
   63.0s / 2.81s / 1.51s. Category Ranking alternates rather than cleanly separating
   into cold and warm buckets.
4. Frontend orchestration: **verified earlier and documented** with file/line evidence.
5. Deliverable: **completed**, including waterfall, dependency paths, suspects,
   affected functions, separate proposed fixes, and open questions.
