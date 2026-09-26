# BUG-001 — remaining verification + deliverable doc

Status: DONE

## Task

BUG-001: Analytics dashboard loads indefinitely or only partially after CAS
import + navigation from main dashboard → Analytics. **Investigation only —
do not implement a fix, do not modify any application code.** Finish the
dynamic-verification legwork below, then write the ticket's deliverable doc.

Live repro environment (already set up, do not re-seed unless it's gone):
- Worktree: `/mnt/d/Unifolio code/.claude/worktrees/bug-001-analytics-load-investigation/backend`
- Dev DB: `unifolio_dev.db` (SQLite), migrations applied through `0003`.
- Seed script: `/tmp/claude-1000/-mnt-d-Unifolio-code/72d699f6-8a5e-488b-b29c-003675174be1/scratchpad/seed_bug001.py` — seeds household member holding 3 real AMFI-coded large-cap direct-growth schemes (HDFC 120503, ICICI Pru Bluechip 120716, Nippon India Growth 118989), all `sebi_category="Equity Scheme - Large Cap Fund"`. Already run; DB already has 3 `scheme_ter` rows and ~410K `nav_history` rows warmed for the Large Cap universe from prior calls this session.
- Household member id: `6f9e78bf-68dd-4d25-b248-e31c8a4d5c17`
- Bearer token (seeded session, bypasses OTP): `bug001-repro-token-000000000000000000000000000`
- Start server: `uvicorn app.main:app --port 8001` from the `backend/` dir (use the project's existing venv).
- Example authenticated request:
  `curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" -H "Authorization: Bearer bug001-repro-token-000000000000000000000000000" http://127.0.0.1:8001/analytics/household-members/6f9e78bf-68dd-4d25-b248-e31c8a4d5c17/ter`
- All 5 Analytics endpoints (member-scoped, same base path):
  `/allocation`, `/ter`, `/category-ranking`, `/score`, `/benchmark`

## Findings already confirmed this session (do not re-derive — build on these)

1. **TER (`amfi_ter_client.py`)** — `_fetch_ter_rows(month)` paginates AMFI's
   `populate-te-rdata-revised` endpoint sequentially (500 rows/page, no
   concurrency), scanning the ENTIRE national feed regardless of portfolio
   size. Triggered any time `_missing_current_month_ter` (in `ter.py`) is
   true, with **no negative-caching or backoff** — a scheme whose
   `plan_name_variant` is unresolved, or whose fuzzy name-match against
   `MIN_MATCH_CONFIDENCE = 0.55` fails, re-triggers the full national refresh
   on every subsequent request. Measured live: **185.8s** (cold) and
   **277.0s** (immediate retry). This is the confirmed root cause of the
   "TER & Cost Analysis ~30s" symptom being a severe understatement in the
   real ticket, and a strong candidate root cause for the "does not load at
   all" endpoints if a request happens to overlap with this on the same
   Uvicorn worker (see hypothesis #3 below).
2. **Category Ranking (`category_ranking.py`)** — `_category_returns` warms
   NAV concurrently but then loops **sequentially per scheme** (2 DB reads
   each) to compute returns; caches only within a single request. Measured
   live: **42.77s cold** (includes full AMFI universe fetch: 143 real
   Large-Cap-category schemes, ~410K NAV rows fetched) / **8.31s warm**
   (floor cost once NAV is cached). For 3 held holdings in 1 SEBI category —
   would scale materially across a real portfolio's ~8 categories.
3. **Scorer (`scorer.py`) — strong hypothesis, not yet dynamically
   confirmed.** `_category_component_scores`'s
   `series_by_scheme = {scheme_id: build_monthly_series(db, scheme_id, month_ends) for scheme_id in returns}`
   is a fully synchronous, unyielding dict comprehension iterating the
   ENTIRE category universe (not just held schemes), with no `await` inside
   the loop. On a single-worker Uvicorn process, a long unyielding
   synchronous stretch blocks the event loop for ALL concurrently-in-flight
   requests, not just the one that triggered it — this is the leading
   structural explanation for why Category Ranking, Scorer, and Benchmark
   appear to hang **together** in the real ticket. `compute_portfolio_score`
   already groups by unique held category (a prior fix, confirmed still in
   place — not a new finding). `_category_ter_context` also triggers
   `_ensure_ter_fresh` once per unique held category, meaning Scorer's
   request path additionally inherits TER's full refresh cost from finding
   #1 above.
4. **`risk_metrics.py`'s `build_monthly_series`** has **no lower-bound date
   filter** on its NAV query — it fetches a scheme's entire NAV history
   since inception rather than just the window needed (e.g. last 5 years),
   multiplied across every scheme in a category universe. Confirmed
   inefficiency by code read; contributes to both Category Ranking and
   Scorer cost.
5. **Ruled out**: `amfi_aaum_client.py` (not invoked by any of the 5
   Analytics endpoints' live request paths — only reads pre-populated
   `scheme_aaum`), `xirr.py` (correctness-clean, bounded 100-iteration
   Newton-Raphson, no perf concern), `allocation.py` (measured cheap,
   1.78s).
6. **Weakened but not fully ruled out**: NSE (`nse_indices_client.py`)
   fetches as a multi-minute-hang cause for Benchmark. Live curl test
   against `niftyindices.com` showed a fast 302 redirect (not followed by
   httpx — no `follow_redirects=True` set), meaning a real request likely
   fails fast (JSON-parse error on redirect body, caught by the broad
   `except (httpx.HTTPError, KeyError, ValueError, TypeError)` in
   `ensure_index_history_fresh`) rather than hanging. This may explain
   incorrect/missing benchmark *data* rather than a *hang* — flag as a
   DATA-001-adjacent note in the deliverable, not a BUG-001 timing cause.
7. A minor incidental data-quality observation surfaced while confirming
   #1: one of the 3 seeded schemes' `scheme_ter` row persisted with a TER
   value of exactly `0` (ICICI Prudential Bluechip, vs. HDFC's 1.02% and
   Nippon's 0.14%). Not investigated further this session — flag it as an
   open question in the BUG-001 doc for DATA-001 to pick up (it's a
   correctness question, not a load-time one), don't investigate its root
   cause as part of this handoff.

## Remaining work (in order)

1. Measure `/score` and `/benchmark` directly against the live repro
   server, same curl pattern as above, 3 runs each, record every timing.
   Expect `/score` to be slow (confirm or refute hypothesis #3) and
   `/benchmark` to be fast-but-possibly-wrong (per finding #6).
2. **Concurrent-load test** (the one interrupted mid-session): fire a
   request to one of the slow endpoints (e.g. `/ter` or `/score`) and,
   while it's still in flight, fire a request to a *different*, normally-fast
   endpoint (e.g. `/allocation`) against the same running server. If the
   second request also stalls until the first completes, that's direct
   confirmation of the single-worker event-loop-blocking hypothesis (#3
   above) — this is the single most important remaining piece of evidence
   for the ticket. Record exact timings for both requests in both orders.
3. Re-run the full 5-endpoint set at least 3 times total (per the ticket's
   explicit "run at least 3 times, record timing" requirement) — you may
   reuse timings already gathered this session (allocation, ter×2,
   category-ranking×2) rather than re-running those, but the 3-run
   requirement must be satisfied for every endpoint in the final table,
   including score/benchmark once measured.
4. Frontend orchestration note for the doc (already reviewed this session,
   just needs folding into the deliverable — do not re-derive): each
   Analytics section fetches independently (`frontend/src/features/analytics/api.ts`),
   there is a 60s GET-response cache in `frontend/src/lib/apiClient.ts`
   (`cachedFetch`, `GET_CACHE_TTL_MS`), and no single `Promise.all` blocks
   all sections on each other — so the frontend itself is not the
   bottleneck; the per-endpoint backend timings above are.
5. Write the deliverable doc at `Docs/orchestration/bug-001-findings.md`
   with: a waterfall table (endpoint, cold time, warm time, run 1/2/3),
   the exact blocking dependency identified (cite file:line), stack-trace-
   level evidence/timing quotes for each suspect above, affected
   files/functions, and a smallest-proposed-fix section **split into
   separate, independently-shippable items** if there are multiple
   independent causes (there appear to be at least 3: TER's missing
   negative-cache, Category Ranking's sequential per-scheme loop +
   unbounded NAV query, and Scorer's synchronous full-universe series
   build). Do not write any code — describe the fix, don't implement it.

## Constraints

- Do not modify any application code under `app/`.
- Do not commit anything to git.
- Every timing claim in the final doc must be a real measured number from
  this repro setup, not an estimate.

## Approaches considered and rejected

- Browser-based waterfall via Playwright/devtools — rejected earlier this
  session: no CAS PDF fixture available to drive a real import through the
  UI, and curl-based direct endpoint timing against a seeded DB satisfies
  the ticket's "real, not assumed" requirement without needing a browser.

## Open questions

- Whether the Scorer's synchronous-blocking hypothesis (#3) is the actual
  cause of Category Ranking/Benchmark appearing to hang *together*, or
  whether they're independently slow for their own reasons and only
  *appear* correlated because a user navigates to the page once and all
  fire at once. The concurrent-load test (remaining step 2) is designed to
  resolve this — report the raw evidence either way, don't force a
  conclusion if the test is ambiguous.
