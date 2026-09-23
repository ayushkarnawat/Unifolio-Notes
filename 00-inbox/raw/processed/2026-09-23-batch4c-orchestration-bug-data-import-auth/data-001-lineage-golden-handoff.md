# DATA-001 — field lineage, golden dataset, XIRR complaint

Status: DONE

## Task

DATA-001: Validate AUM, beta, TER, and cost-analysis correctness.
**Investigation only — do not implement a fix, do not modify any
application code.** Produce a per-metric field-level lineage table and a
small masked golden dataset with hand-calculated expected values, compared
within documented tolerances. Also investigate a specific user complaint:
a screenshot showing portfolio XIRR of **+0.10%**, which the user believes
is implausibly low for what they consider "a good portfolio."

Screenshot: `/home/ayush/.claude-unifolio/image-cache/72d699f6-8a5e-488b-b29c-003675174be1/7.png`

Repro environment (shared with the BUG-001 handoff — read-only use, this
task must not collide with BUG-001's server/DB use; if both are dispatched
concurrently, start a second uvicorn instance on a different port against
a copy of `unifolio_dev.db` rather than sharing the live one):
- Worktree: `/mnt/d/Unifolio code/.claude/worktrees/bug-001-analytics-load-investigation/backend`
- Seed script (reference, already run once): `/tmp/claude-1000/-mnt-d-Unifolio-code/72d699f6-8a5e-488b-b29c-003675174be1/scratchpad/seed_bug001.py`

## Relevant source files (already read this session — use directly, don't re-derive from scratch)

- `backend/app/services/analytics/xirr.py` — pure-Decimal Newton-Raphson,
  bounded 100 iterations. Read in full this session; no float anywhere, no
  correctness red flag found on read alone — but this was a static read
  only, not verified against a hand-calculated golden case. That
  verification is this task's job.
- `backend/app/services/analytics/ter.py`, `amfi_ter_client.py` — TER
  computation and AMFI ingestion. Note from BUG-001 investigation: one
  seeded scheme (ICICI Prudential Bluechip) persisted a `scheme_ter` row
  with value exactly `0` after a successful AMFI fuzzy-match refresh —
  flagged there as a correctness question for DATA-001, not resolved.
  Check whether `0` is a real AMFI-reported value for that scheme/month or
  a silent-zero bug (e.g. a failed parse defaulting to zero instead of
  leaving the row absent).
- `backend/app/services/analytics/amfi_aaum_client.py` — AAUM ingestion
  (3 sequential AMFI calls: financial-years → periods → rows). Confirmed
  NOT invoked by any live Analytics endpoint request path this session
  (only reads pre-populated `scheme_aaum`) — trace where/how `scheme_aaum`
  actually gets populated (a scheduled job? manual trigger? check
  `EventBridge`/`app/services/` for a refresh entrypoint) since that's the
  real lineage path for AUM, not the request-time path.
- `backend/app/services/analytics/benchmark.py`, `nse_indices_client.py` —
  beta/benchmark computation. Note from BUG-001 investigation: a live curl
  test against `niftyindices.com` returned a fast, unfollowed 302 redirect
  (`httpx` call has no `follow_redirects=True`), meaning `ensure_index_history_fresh`
  likely fails fast into its broad except clause and silently falls back
  to stale/empty index history rather than hanging — check whether this
  produces silently wrong or silently missing beta/benchmark values rather
  than an honest "unavailable" state.
- `backend/app/services/analytics/risk_metrics.py` — beta/risk calculation
  inputs (`build_monthly_series`, confirmed to have no lower-bound date
  filter — fetches full NAV history since inception; check whether this
  affects beta's calculation window/correctness, not just its performance).
- CLAUDE.md non-negotiable: `Decimal`, never `float`, for every
  money/units/NAV value — treat any float found in a money/percentage path
  as a real finding, not a style nit.

## Required deliverable structure

1. **Field-level lineage table**, one row per metric (AUM, beta, TER,
   weighted-cost/TER-analysis, XIRR), columns: source (which external feed
   or DB table), units (%, ₹, decimal fraction — be explicit, this is
   where percent-vs-decimal bugs hide), as-of-date semantics, fallback
   behavior when data is missing/stale, and a one-line methodology summary
   pointing at the exact function.
2. Explicit checks, per metric, for: percent-vs-decimal scaling errors,
   staleness (is the "as of" date shown to the user the same date the
   number was actually computed from?), direct-vs-regular plan mixing,
   growth-vs-IDCW mixing, missing scheme→category/ISIN mapping fallback
   behavior, and silent-zero behavior (a `0` or `None` that got treated as
   a real value instead of "unavailable").
3. **A small masked golden dataset**: pick 2-3 real, publicly-known scheme
   NAV histories (mfapi.in is reachable and free — use it directly) plus a
   couple of manually-defined purchase transactions (dates/amounts your
   choice, clearly documented as synthetic), hand-calculate the expected
   XIRR and weighted TER for that portfolio independently (i.e. compute it
   in a scratch script using a well-known reference method, not by calling
   the app's own `xirr.py`), then compare against what the actual seeded
   endpoint returns. Document the tolerance used (e.g. XIRR within 0.01
   percentage points) and whether it passes.
4. **XIRR complaint investigation**: using the golden dataset above (or a
   variant deliberately shaped to mimic the screenshot's scenario — a
   long-held, currently-small-gain portfolio), determine whether +0.10%
   XIRR is *mathematically correct* for a portfolio with modest/flat
   returns over its holding period (XIRR is annualized — a portfolio held
   a long time with a small total gain will show a very low XIRR even if
   NAV performance was fine over shorter windows) versus a real
   calculation bug. State a clear conclusion either way with the numbers
   that support it — this may well turn out to be correct-but-confusing
   behavior rather than a bug; say so plainly if that's what the evidence
   shows, don't strain to find a bug that isn't there.
5. Write the deliverable doc at `Docs/orchestration/data-001-findings.md`
   with all of the above, plus a top-level summary of which metrics
   passed/failed golden-value comparison and which are confirmed-correct
   vs. still-open.

## Constraints

- Do not modify any application code under `app/`.
- Do not commit anything to git.
- All golden-value comparisons must show your independent hand-calculation
  method, not just "app returned X, looks reasonable."
- Do not use any real user's PAN or CAS PDF data — synthetic transactions
  and real-but-public scheme NAV data only, consistent with CLAUDE.md's
  no-PAN-persistence rule.

## Approaches considered and rejected

- Trusting `xirr.py`'s clean static read as sufficient — rejected: a
  correctness bug in inputs (wrong date, wrong amount sign, wrong NAV
  lookup) can produce a wrong XIRR even with perfect Newton-Raphson math;
  only an independent golden-value comparison catches that class of bug.

## Open questions

- Whether `scheme_aaum` has any real ingested data in this dev DB at all,
  or whether AUM is currently always empty/fallback in this environment —
  check before concluding anything about AUM correctness; if there's no
  real data path exercised yet, say that explicitly rather than reporting
  a false pass.
