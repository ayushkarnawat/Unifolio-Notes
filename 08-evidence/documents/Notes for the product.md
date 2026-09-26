How to start the localhost - 

Backend - cd "D:\Unifolio code\backend"
.\.venv-win\Scripts\uvicorn.exe app.main:app --reload --port 8000 --loop asyncio:ProactorEventLoop

Frontend - cd "D:\Unifolio code\frontend"
npm run dev


Confirmed: 185.8s for a single isolated TER request, matching a genuine backend bottleneck, not a frontend artifact. Let's verify it's cache-driven (fast on repeat) and now test the other three suspect endpoints.

Stopping here — that tool call was rejected. Quick status check-in: I've been dynamically reproducing BUG-001 against a seeded portfolio in the worktree's backend (real AMFI codes, real category universes), and have confirmed two concrete, timed root causes so far:

1. TER endpoint: 185.8s on a cold request, and still running past 2+ minutes on a second "should be cached" retry — amfi_ter_client.py's _fetch_ter_rows paginates AMFI's entire national TER feed sequentially (no concurrency), and _missing_current_month_ter re-triggers this full refetch on every request whenever any held scheme lacks a matched current-month row (which can be permanent for an unmatched scheme — no negative-caching/backoff).
2. Category Ranking: 42.8s cold / 8.3s with NAV warm, against a single real 143-scheme category universe — driven by _scheme_return's sequential per-scheme DB-query loop.

I was about to fire /score concurrently with the still-running TER request to test whether it's the frontend firing 5 parallel requests against a single-worker event loop that's compounding these individually-slow endpoints into the reported multi-minute total hang. Let me know how you'd like me to proceed (continue as planned, hold off on more live requests, or something else).

The current status already flags four analytics correctness gaps that I’ll verify directly rather than simply repeat: an XIRR percentage-scaling defect, TER missing-data being represented as zero, Beta and AAUM refresh being unimplemented, and a CAS name-to-AMFI-code lineage risk. I’m now checking those findings against the merged code and documenting any places where the notes have become stale.

A direct code trace has uncovered an additional scaling problem beyond the previously documented XIRR defect: category CAGR values are also returned by the backend as decimal fractions, while the frontend appends `%` without multiplying by 100. I’m expanding the review to distinguish arithmetic correctness from display correctness and from data-lineage reliability, because those are three different stakeholder claims.

ACTIVE SIPS - 
Confirmed the backend piece is fully built: compute_active_sips (backend/app/services/dashboard/sip.py) detects a SIP as "active" if its most recent PURCHASE_SIP transaction is within the last 40 days, exposed via GET /household-members/{id}/sips and GET /household/aggregate/sips, both tested (test_sip.py, test_dashboard_sips_route.py). The frontend even has the typed API client functions (getMemberSips, getAggregateSips) and types (SipRow, AggregateSipsResponse) already sitting in dashboard/api.ts/types.ts — just never called from any component. So the gap is purely: no UI section renders it.

One nuance: the backend's sip_date field is the last executed SIP transaction date, not a forecasted next date. You asked for "upcoming SIPs... which date" — I'd project the next due date client-side (last_date + 1 month, same day-of-month) rather than showing the stale last-run date. No new dependency needed for that.

Proposed design (bounded — extends the existing dashboard, no new backend work)

- Data: add getAggregateSips/getMemberSips to the existing Promise.all fetch in DashboardView.tsx (same pattern as holdings/allocation), store in a sips state array.
- Section: new <section> in DashboardView.tsx between Allocation and Holdings Table — "Upcoming SIPs" card list: fund name, member name (aggregate view only), projected next SIP date, amount (via existing formatIndianCurrency). Sorted soonest-first. Hidden entirely if empty (same pattern as the Allocation section).
- No new file — inlined as a section like the hero/allocation blocks already are, not a separate component (it's a short list, not complex enough to warrant one).
- Test: extend DashboardView.test.tsx with one case asserting the section renders SIP rows from a mocked response.

Skipped: no backend schema change, no new "next SIP date" field persisted server-side (computed client-side from existing sip_date), no SIP amount editing/management UI (out of scope — PRD-03 FR-5 is display-only).

ACTIVE SIPS UPDATED - 

Good — recommending one approach, with two alternatives considered:

Approach: server-computed cadence, one new endpoint

Rejected alternatives: (B) doing all rollover math client-side — rejected because date-rollover has real edge cases (month-end clamping, multi-month gaps) that deserve backend test coverage like everything else money/date-adjacent in this codebase, not untested JS; (C) skip a new endpoint and have the frontend reconstruct "this month" from data it already fetches — rejected because "this month" needs each folio's actual past transactions, which the existing SIP endpoint deliberately never carries (it only ever returns the single most-recent transaction) — the frontend would end up re-fetching and correlating full transaction history itself anyway, which is messier than one backend function with direct DB access to both concerns.

Design:

1. sip.py rewrite: drop the 40-day filter. A folio counts as an active SIP if it has ≥1 PURCHASE_SIP transaction ever, and currently has units_held > 0 (excludes fully-redeemed schemes — a real fact, not a guess). Add a next_due_date field to SipRow, computed by rolling the last transaction's date forward one month at a time (day-of-month clamped to the target month's actual length, e.g. day 31 in Feb → Feb 28/29) until it lands on or after today. Monthly cadence is assumed, not inferred from transaction-interval history — Indian SIPs are near-universally monthly, and this matches PRD-03's original ~30-40 day assumption; noted as a deliberate simplification if you ever see a non-monthly SIP show up wrong.
2. New endpoint GET /household-members/{id}/sips/monthly?year=&month= (+ aggregate equivalent): for the requested month, per folio, returns the actual transaction if one exists in that month (past/current), otherwise the projected due date if it falls in that month (current/future). No "missed" flag or special styling — just a date and an amount, same as the Upcoming list.
3. Frontend: the existing "Upcoming SIPs" section keeps its current visual treatment, now reading next_due_date from the API instead of computing it client-side (deleting that logic). Add a second tab, "This Month," with prev/next month arrows, calling the new endpoint.

Testing: backend TDD on the rollover math directly (multi-month gaps, Feb 29/31-day clamping, exactly-today edge), on the redeemed-fund exclusion, and on the monthly endpoint's actual-vs-projected reconciliation; frontend tests on tab switching and rendering.

PRD note: I'll add a short note to PRD-03-Main-Dashboard.md's SIP section flagging that FR-6's 40-day cutoff was superseded by this session's decision, so it's traceable later rather than silently contradicted — not a full rewrite of the doc.


ADD THIS IN THE DEFERED ITEMS - 
Item 4 (Category Ranking bulk query) — remaining Medium finding:
_bulk_nav_on_or_before now uses one MAX(date) GROUP BY scheme_id query per target date (3 total per category), returning exactly one row per scheme — no more full-history ORM materialization (that part's fully fixed and confirmed). The reviewer's remaining point: without an index structure that supports a per-group "skip scan" (e.g. a LATERAL join doing an index-seek + LIMIT 1 per scheme), the database still has to scan every historical row per scheme to compute each MAX(date) — it's bounded in what Python touches, not in what the DB reads.

I'd recommend accepting this as a documented limitation rather than dispatching a third round, because:
- It's correctness-safe — no data-loss/corruption risk, just DB-side read cost.
- That cost is now bounded to once per 15-minute TTL window per category (this same fix's cache), not per-request — the original per-request cost is what's actually gone.
- Closing it fully needs a LATERAL/index-seek primitive not used anywhere else in this codebase, and verifying it actually helps requires a real Postgres query plan — dev is still SQLite (per Migration-Plan-SQLite-to-Postgres.md, Postgres parity isn't live yet), so I can't even confirm the "fix" would help before AWS readiness.

Want me to accept this as documented and move on, or dispatch a third round to pursue the LATERAL approach anyway?

Item 5's re-review returned one more finding — a real but pre-existing gap unrelated to the redirect fix itself: _fetch_index_history's Decimal(entry["CLOSE"]) can raise decimal.InvalidOperation on a malformed value, which isn't in ensure_index_history_fresh's catch tuple, so it'd escape instead of degrading to stale cache. Cheap, adjacent, and in the same file already open — fixing it now rather than leaving a half-verified revert.

Root cause: AMFI's NAVAll.txt feed (the source category_ranking.py/scorer.py use to build each SEBI-category peer universe) changed its row format — it used to be 6 semicolon-delimited fields (code;isin;isin;name;nav;date), but as of the live feed today it's 8 fields (AMFI split a Plan and Option column out of the scheme name). scheme_universe.py's parser had a hardcoded len(fields) != 6 check, so it silently dropped every single row from the file. That zeroed out every category universe for every user — nothing to do with your CAS data's real transaction dates. That's why even Parag Parikh Flexi Cap Fund, which has ~6 years of genuine history in your CAS (and is confirmed present in the live AMFI feed with full history), still showed "Insufficient History": there was simply no peer universe for anything to rank or score against.

Fix (backend/app/services/analytics/scheme_universe.py): _parse_nav_all now accepts both the old 6-field and new 8-field row shapes, reconstructing the same "Name - Plan - Option" string the rest of the code already expects when it hits the new 8-field format.

Found the real root causes — three distinct factors, not one. Let me lay out the evidence before touching code.

1. One category is a monster. Your three index-fund holdings (Nippon India Index Fund, Edelweiss Nifty Smallcap 250, Motilal Oswal Nifty Midcap 150) all get grouped under AMFI's single umbrella category "Other Scheme - Index Funds" — which contains 1,150+ schemes, everything from Nifty 50 trackers to gilt/debt index funds to gold-linked funds. Every other category your funds touch (Flexi Cap, Mid Cap, Small Cap, Arbitrage, etc.) has 94–165 schemes. This one category alone is ~7–10x the size of a normal one, and every scheme in it needs its full NAV history fetched and processed.

2. Your local dev database sits on a WSL-mounted Windows drive, and that's a real, measurable problem: unifolio_dev.db lives at /mnt/d/Unifolio code/backend/, which goes through WSL2's DrvFs (9P) layer instead of a native Linux filesystem. I benchmarked it directly

I even reproduced a genuine disk I/O error running the real Scorer code path against that 1,150-scheme category on this drive — WSL's DrvFs doesn't fully support the file-locking semantics SQLite relies on under sustained write load. That's a real stability risk, not just a speed one.

3. warm_nav_history commits once per scheme, not once per batch. For a 1,150-scheme category, that's 1,150+ individual fsync-bound commits — exactly the operation that's 57x slower on this drive.

4. Scorer's build_monthly_series was never bulk-ified the way category_ranking.py's NAV lookups were in the BUG-001 fix — it still runs 2 sequential queries per scheme (up to ~2,300 queries for the mega category), which is almost certainly why Scorer (5–6 min) is so much slower than Category Ranking (1.5–2 min), which already got that fix.

I'll fix #3 and #4 now — pure engineering wins, no product tradeoff, help both localhost and Postgres. Let me write the failing tests first.

Both fixes done, benchmarked against your real dev DB

Fix A — warm_nav_history batches to one commit per category instead of one per scheme (nav.py). This is the big one for your scenario: on a cold cache (new family member, new category), the old code did a db.commit() per scheme inside a 1000+-scheme category — each commit is an fsync round-trip, and your dev DB sits on a WSL-mounted Windows drive where commits measured 57x slower than a native filesystem (76/sec vs 4351/sec). One category-wide commit removes that multiplier entirely.

Fix B — Scorer's per-scheme NAV series build is now one bulk query pair instead of 2 queries × scheme count (risk_metrics.py + scorer.py), mirroring the fix Category Ranking already got. Benchmarked live against your real "Other Scheme - Index Funds" category (1,232 schemes, already-warm cache): 14.5s → 12.2s for the series-build step — real but modest, because on this WSL/SQLite setup the bottleneck is raw row-scan I/O, not query round-trip count (same pattern as the earlier Category Ranking LATERAL benchmark). Results verified byte-identical to the old per-scheme output.

Your three questions

1. Does cost multiply per family member? No — it multiplies per distinct SEBI category the household doesn't already hold, not per member or per transaction. Both Category Ranking's and the Scorer's category computations are cached for 15 minutes, keyed by category string, shared across the whole household. If member 2 holds funds in categories member 1 already triggered, that's free. Your 7-minute run was dominated by a cold NAV cache doing live network fetches for ~1,232 schemes in one oversized AMFI category — that's a one-time cost per category, not per member.

2. Is this WSL-specific, or will it persist on AWS/Postgres? Partly localhost-specific. The 57x commit penalty (Fix A's target) is a WSL DrvFs artifact — gone on real Postgres/AWS storage. But the algorithmic fixes (batching, bulk queries) help both environments equally, and production's actual design is a daily pre-warm background job (per nav.py's own docstring), not this on-demand cold-cache path at all — so first-load-after-CAS-upload shouldn't even hit this cost in production the way it does in dev today.

3. Can we get to 1-2 minutes on localhost? These two fixes should meaningfully cut a cold-cache run (the commit-batching fix alone removes the dominant WSL-specific tax). I can't give you a new end-to-end wall-clock number without re-running a live cold-cache CAS import through the UI, since simulating it standalone would just re-fetch real data from mfapi.in — want me to do that next (re-upload the same 10-year CAS file after clearing the warm-cache TTL) to get a real before/after total?

On the two flagged items: neither is done — both are decisions I need from you, not code I've already written.

1. Relocating the dev SQLite DB off /mnt/d

Nothing to build here beyond a .env/config path change — the work itself is trivial (move unifolio_dev.db to somewhere on the native WSL filesystem, e.g. ~/unifolio-dev/unifolio_dev.db, and point DATABASE_URL at it). What I need from you is just a go-ahead, because it's an environment change with a couple of side effects worth flagging:
- The file would live outside /mnt/d/Unifolio code, so it won't show up in Windows Explorer or get backed up/synced the way the rest of the repo does (it's already gitignored, so nothing repo-wise changes).
- Any of your own tooling/scripts that assume the DB's current path would need updating.

If that's fine, say go and I'll do it now — it's a 5-minute change, not a research task.

2. AMFI's "Other Scheme - Index Funds" mega-category correctness

This one isn't mine to just decide and fix — it's a product call. Right now every index fund (Nifty 50, Nifty Midcap 150, Sensex, sectoral indices, international index funds, gold ETFs-as-index-funds, etc.) gets lumped into one SEBI category, so Category Ranking/Scorer peer-compares a Nifty 50 index fund against a Nifty Midcap 150 fund — apples to oranges, both labeled "index fund." AMFI's own categorization doesn't split further than this.

What I'd need from you to move on it:
- Confirm this is worth fixing at all (it's correctness, not a crash — rankings are still computed, just against a noisier peer set)
- If yes, a call on the re-categorization approach — the natural one is grouping by underlying tracked index/benchmark (parseable from scheme name text, e.g. "Nifty 50", "Nifty Midcap 150", "Sensex") rather than AMFI's category string, which means introducing a benchmark-detection heuristic that doesn't exist anywhere in the codebase today — worth checking /Docs first for whether this was already considered and deferred, since it changes what "SEBI category" means for this one bucket only.

Want me to check /Docs for prior discussion of this before you decide?

Instrumentation is in and the full suite is still green (443/2). Confirmed via /Docs (PRD-04's FR-3/FR-5a, Edge Cases table) that the mega-category question was never raised or decided before — "compute its category" was written assuming AMFI's category tag is granular enough (Large Cap, Flexi Cap, Debt), and nobody anticipated AMFI's own catch-all bucket lumping every unrelated index fund together. So that item isn't something I'd already built — it's genuinely open.

On the regression first, since it should be resolved before touching anything else:

I added timing logs (not a fix — pure instrumentation, logging.info calls) to the three real phases that matter: network NAV fetch, DB commit, and the NAV-lookup/series-build compute step, in nav.py, category_ranking.py, and scorer.py. This lets us see hard numbers instead of guessing again.

To use it: fully kill and restart the backend process (not just re-upload in the browser — uvicorn --reload's file-watcher depends on inotify, which is known to be unreliable for files on /mnt/d's DrvFs mount, so there's a real chance your second run silently executed the pre-fix code, which alone would explain "no improvement"). Then re-run the same test and paste back the console lines starting with:
- warm_nav_history:
- _compute_category_returns[
- _compute_category_component_scores[

That'll show exactly where the time is actually going (network vs. DB vs. compute) and whether the fixes are even running. Once we see that, we'll know whether to keep debugging the fixes or whether it was a stale-reload false alarm.

On the mega-category fix: confirmed via /Docs this is genuinely undecided territory, and yes — splitting it would very plausibly also help load time for anyone holding index funds specifically, since warm_nav_history/the bulk queries would then run against a ~50-150-scheme group instead of 1,150+. It needs a benchmark-detection heuristic from scheme-name text (no such thing exists in the codebase today, since AMFI's feed has no benchmark field) — real but bounded work. I'll hold off starting that until we've closed out the regression mystery above, since I don't want to layer a new change on top of an unexplained performance result.


This is exactly the evidence needed — and it points somewhere completely different from Fix A/B. Look at the timestamps: the scorer's actual work (_compute_category_component_scores) only runs from 11:02:40 to 11:03:10 — about 30 seconds total, and the "Other Scheme - Index Funds" line shows series_build=13.15s, matching our benchmark almost exactly. Fix B is working correctly.

The real time sink is the ~4 minutes between 10:58:55 and 11:02:30 — hundreds of sequential AMFI TER-data page fetches (populate-te-rdata-revised, pages 131→380+), which is a completely separate subsystem (ter.py) neither Fix A nor Fix B touched. That's almost certainly your "8 minutes," not the Scorer itself. Let me look at why it's re-fetching all of that.

  Ran 1 shell command

That backoff mechanism has a documented weak spot — if even one held scheme's TER can never be fuzzy-matched, the freshness check stays permanently "missing" and re-triggers a full AMFI scan every 15 minutes. Let's check the fetch client itself and whether it's even scoped to your held schemes or pulling the entire AMFI universe.

  Ran 1 shell command

Found it — _fetch_ter_rows sequentially paginates through what looks like AMFI's entire national TER dataset (380+ pages, no concurrency), just to find the ~13 schemes this household actually holds. That's almost certainly your real "8 minutes." Let me check whether this is a one-time cost or whether something is actually stuck permanently re-triggering it (the module's own docstring flags a known risk: if even one held scheme never gets fuzzy-matched, this re-runs every 15 minutes, forever).


Root cause confirmed with hard evidence. Two of your held schemes have no current-month TER match at all:

- SBI PSU Fund - Regular Plan - Growth
- Tata FMP Series 61 Scheme A (91 days) Regular Plan IDCW

The second one is a closed-ended fixed maturity plan — those mature and drop out of AMFI's monthly TER feed entirely, so it will likely never match again. That means _missing_current_month_ter returns True forever for your household, and per the module's own documented risk, every 15 minutes (the backoff window) it re-triggers a full, sequential, un-parallelized scan of AMFI's entire national TER dataset (380+ pages) just to re-confirm those 2 schemes still can't be matched. That's your recurring ~4-minute tax — separate from and much larger than anything Fix A/B touch. The log actually shows Fix A/B working correctly (Scorer's real compute was ~30s total, Other Scheme - Index Funds bulk series build at 13.15s matching the benchmark).

Two separate things to decide:

1. Parallelize the TER page fetch (mechanical, low-risk, mirrors nav.py's existing concurrent-fetch pattern) — turns every future ~4-minute occurrence into probably single-digit seconds, regardless of the recurrence question. I'd like to do this now — any objection?

2. Why it keeps recurring at all — that's a data-modeling gap: there's currently no way to record "checked this scheme against this month's feed, confirmed no match" vs. "never checked," so a permanently-unmatchable scheme (like a matured FMP) forces a full re-scan every 15 minutes indefinitely. Fixing that needs a small schema/logic change (e.g., persist a negative-match marker per scheme/period) — separate, slightly bigger decision, not just a mechanical fix. Want me to do that too, or park it?

Root cause found — confirmed with data, not guesswork.

What actually happened: Nothing in the backend code changed to cause this. The bug is in two household-member records created today, both from re-importing your same CAMS statement:

┌───────────┬──────────────┬──────────────────┬───────────────────────────────────────┐
│  Member   │ User account │     Created      │         Jio scheme mapped to          │
├───────────┼──────────────┼──────────────────┼───────────────────────────────────────┤
│ "Prateek" │ 668d6a8e...  │ 2026-08-07       │ JioBlackRock Flexi Cap Fund (correct) │
├───────────┼──────────────┼──────────────────┼───────────────────────────────────────┤
│ "cv"      │ 04112cdc...  │ 2026-08-20 05:56 │ UTI Children's Equity Fund (wrong)    │
├───────────┼──────────────┼──────────────────┼───────────────────────────────────────┤
│ "AS"      │ 5f5cd205...  │ 2026-08-20 06:10 │ UTI Children's Equity Fund (wrong)    │
└───────────┴──────────────┴──────────────────┴───────────────────────────────────────┘

Your original "Prateek" member (the one from Aug 7) is untouched and correct. The dashboard you're looking at right now must be one of the two brand-new throwaway members ("cv" or "AS") — both were created minutes apart today, both are full re-imports of the identical CAS, and both got the exact same wrong scheme mapping.

Why JioBlackRock → UTI Children's: casparser parses the Jio row correctly (ISIN INF22M001093, amfi 153859 — verified from the stored raw parser output). The problem is downstream, in scheme confirmation:

- mfapi.in's canonical name for code 153859 is "JioBlackRock Flexi Cap Fund - Direct Plan - Growth Option".
- Your CAS prints it as "JioBlackRock Flexi Cap Fund - Direct - Growth" (missing "Plan"/"Option").
- Similarity between those two strings is 0.872 — just under the 0.92 auto-confirm gate (PRD-01 FR-10's "never silently guess below 0.92"). Because JioBlackRock only launched Oct 2025, this is the first scheme whose CAS-vs-mfapi naming gap happens to straddle that threshold.
- So this scheme correctly fell into "pending" — requiring a manual scheme pick — and whoever confirmed the import today picked the wrong scheme (UTI Children's Equity Fund) for it. Not a backend bug; a bad manual selection during today's test.

This exactly explains both symptoms:
- The extra "holding" isn't a new scheme — it's your real Jio transactions (12,359.539 units, ₹1,25,000 cost) now priced at UTI's NAV (₹92.04) instead of Jio's (~₹10.10).
- 41,84,567 (your correct CAS total) + (11,37,515 − 1,23,695 fake gain from that mispricing) = 51,98,387 — matches "52,000" (lakhs, truncated) vs. your earlier correct "42–43,000".

Next step, your call: these are two disposable test accounts, not your real data — cleanest fix is deleting "cv" and "AS" (or their imports) rather than patching anything. Want me to do that, or would you rather I fix the scheme mapping in place first so you can inspect it?



1. Cleaned up test data — deleted the two throwaway accounts ("cv", "AS") and their folios/transactions/imports/users. unifolio_dev.db now only has your real "Prateek" data.
2. Fixed the resolution gap — resolve_scheme now cross-checks isin (from casparser, already 100% correctly resolved) against mfapi.in's isinGrowth/isinDivReinvestment for the CAS-supplied AMFI code, before falling back to name-similarity. ISIN is globally unique and format-independent, so this fixes the whole class of problem — any scheme where CAS naming diverges even slightly from mfapi.in's, not just Jio's. It's purely additive: only activates when both sides actually have ISIN data (mfapi.in only publishes it for ~24% of schemes, verified zero collisions), so it can only rescue matches, never weaken the existing 0.92 gate or the DATA-001 corrupted-pairing protection.

Answering "what about other funds": don't lower the threshold — that would blanket-weaken protection against genuine bad matches. The ISIN check is the better fix because it replaces a fragile text-similarity proxy with an authoritative identifier for the specific case where we already trust the code. Any future scheme with the same CAS-vs-mfapi wording drift, and mfapi has ISIN data for it, now auto-confirms correctly; when mfapi lacks ISIN data, it falls back to today's behavior (still-correct pending-for-manual-review). Added 2 new tests + fixed 4 existing test mocks for the new isin param; full suite (446 passed, 2 skipped) is green.

On the mega-category split: yes, that's next as discussed. To recap the shape of it before I start:

- Problem: AMFI's "Other Scheme - Index Funds" category lumps ~1,150+ schemes together, so every category-relative computation (ranking, Scorer's peer-group percentiles) runs its bulk NAV/series queries against that whole set — including for someone holding a single index fund.
- Fix shape: split it into sub-groups (e.g., Nifty 50 index funds, Nifty Next 50, sectoral index funds, international/FoF index funds, debt index funds, etc.) using a benchmark-detection heuristic parsed from scheme name text, since AMFI's feed has no benchmark field to key off directly.
- Why held off: you didn't want to layer this on top of the still-unexplained load-time regression — that's now closed (root-caused and fixed above), so it's unblocked.


Pulled up everything relevant — here's what exists and what doesn't.

Docs confirm: no existing plan. I searched PRD-04 (analytics spec), the Scorer methodology doc, the BUG-001/DATA-001 findings and post-implementation performance assessment, and every phase-4 design doc. Zero mentions of "mega-category," category-size limits, or a benchmark-detection heuristic anywhere. PRD-04's only category-size note is the opposite problem — FR-4's "thin category" handling (too few peers, flag as small-sample). This really is undecided territory, exactly as you found.

What the docs do establish, that constrains the design:
- scheme_universe.py's category grouping is a direct pass-through of AMFI/mfapi's own SEBI category text (NAVAll.txt's category header) — "Other Scheme - Index Funds" is SEBI's real regulatory bucket, not something we introduced. Any splitting we do is our own invention on top of it, not a correction to AMFI's data.
- I confirmed the live scale: 1,150 schemes currently in this category (pulled from the cached NAVAll.txt).
- Sampled 30 real scheme names — naming is consistent enough for a regex/keyword heuristic to be genuinely bounded work: "<AMC> <Index Name> Index Fund - <Plan> - <Option>", e.g. Nifty 50, Nifty Bank, Nifty Midcap 150, BSE Sensex, Nifty500 Momentum 50, various G-Sec/debt maturity-series funds.
- PRD-04's existing "excluded with a clear label, not silently dropped" posture (for unresolvable categories) gives us a precedent to reuse for the heuristic's catch-all bucket — a scheme with a naming pattern we don't recognize shouldn't disappear, it should land in a labeled "Other Index Funds" bucket.

Proposed shape, given no existing guidance to follow:
1. A pure function mapping a scheme name → benchmark bucket key (Nifty 50, Nifty Bank, Nifty Midcap 150, Sensex, debt/G-Sec index funds, sectoral/thematic, catch-all "Other Index Funds"), most-specific-pattern-first to avoid substring false positives (e.g. "Nifty 50 Value 20" shouldn't fall into plain "Nifty 50").
2. Only category_ranking.py/scorer.py's internal cache-key and peer-universe-narrowing use the sub-bucket, and only when sebi_category == "Other Scheme - Index Funds". Scheme.sebi_category itself, Allocation's category breakdown, and anything user-facing keep showing the real SEBI category unchanged — this is an internal peer-grouping detail, not a new taxonomy we're presenting to you.
3. No schema/DB change — computed on the fly from Scheme.name, same as any other pure lookup in this codebase.

Main risk worth flagging: a heuristic on free-text names can mis-bucket a genuinely novel index family into the catch-all, or (worse, more subtly) a badly-ordered regex could pull a scheme into the wrong real bucket rather than the catch-all. Mitigated by most-specific-first ordering + reusing the existing thin-category flag for small buckets, but it's a new fuzziness surface that didn't exist before, in exchange for the load-time and peer-comparison-quality wins.

Here's the concrete bucket list, computed from the real 1,150 scheme names in the cached NAVAll.txt (not hypothetical).

Option A — Fine-grained, per-benchmark (regex on scheme name)

┌──────────────────────────────────────────────────┬───────┬─────────────────────────────────────────────────────────────┐
│                      Bucket                      │ Count │                           Sample                            │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Debt/Bond/SDL/CPSE index                         │   219 │ Aditya Birla SL Crisil IBX 60:40 SDL+AAA PSU Apr 2026       │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Gilt/G-Sec/target-maturity                       │   173 │ Aditya Birla SL Crisil IBX 50:50 Gilt+SDL Apr 2028          │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Sectoral/thematic index                          │   124 │ Axis Nifty IT Index Fund                                    │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Nifty 50 family                                  │   103 │ Aditya Birla SL Nifty 50 Index Fund                         │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Nifty 500 family                                 │    72 │ Axis Nifty 500 / Nifty500 Momentum 50                       │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Nifty Midcap 150                                 │    54 │ Bandhan Nifty Midcap 150                                    │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Nifty 200                                        │    50 │ Bandhan Nifty 200 Quality 30                                │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Smart-beta factor (Alpha/Momentum/Quality/Value) │    48 │ Bandhan Nifty Alpha 50                                      │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Nifty Next 50                                    │    48 │ Axis Nifty Next 50                                          │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ BSE Sensex                                       │    45 │ Axis BSE Sensex                                             │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Nifty 100                                        │    40 │ Axis Nifty 100                                              │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Nifty Smallcap 250                               │    38 │ Bandhan Nifty Smallcap 250                                  │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Nifty Bank                                       │    24 │ Axis Nifty Bank                                             │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Nifty LargeMidcap 250                            │    19 │ Edelweiss Nifty Large Midcap 250                            │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Nifty Midcap 50 / Smallcap 50                    │    16 │ Axis Nifty Midcap 50 / Smallcap 50                          │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ International (Nasdaq/S&P/Hang Seng)             │     6 │ ICICI Pru Nasdaq 100                                        │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ BSE 100/200/500/1000                             │     4 │ HDFC BSE 500, Motilal Oswal BSE 1000                        │
├──────────────────────────────────────────────────┼───────┼─────────────────────────────────────────────────────────────┤
│ Catch-all (unmatched)                            │    67 │ Angel One Nifty Total Market, Axis BSE India Sector Leaders │
└──────────────────────────────────────────────────┴───────┴─────────────────────────────────────────────────────────────┘

18 buckets, largest is 219 (debt index), catch-all is a clean 5.8% of the category — real perf win (1,150 → ~50-220 per bucket) but every bucket boundary is a heuristic I invented, on regex over free text, with real mis-bucketing risk (e.g. "Nifty200 Momentum 30" landed in Nifty 200 not Smart-beta — a specificity-ordering call I made, not an AMFI fact) and ongoing maintenance every time a new index family launches (happens ~monthly right now — see the SDL/target-maturity debt series alone).

Option B — Coarse, AMFI-precedented (asset class only)

AMFI's own NAVAll.txt already carries a separate, parallel taxonomy for index funds, independent of the SEBI-recategorization "Other Scheme - Index Funds" bucket:

┌───────────────────────────────────────────────────────────┬───────┐
│                    AMFI header (as-is)                    │ Count │
├───────────────────────────────────────────────────────────┼───────┤
│ Index Funds - Equity Funds                                │   133 │
├───────────────────────────────────────────────────────────┼───────┤
│ Index Funds - Debt Funds                                  │    43 │
├───────────────────────────────────────────────────────────┼───────┤
│ Index Funds - Hybrid Fund                                 │     4 │
├───────────────────────────────────────────────────────────┼───────┤
│ (current SEBI bucket, unsplit) Other Scheme - Index Funds │ 1,150 │
└───────────────────────────────────────────────────────────┴───────┘

3-way split, nothing invented — it's AMFI's own recognized category label, not our regex. But it barely moves the needle: Equity Index alone would still be a ~500+ scheme bucket by extrapolation (since only 133 of ~800 likely-equity index schemes carry the legacy label), and Debt/Hybrid don't map back cleanly to the 1,150 either — the legacy headers and the "Other Scheme" header aren't the same schemes counted twice, they're additional, mostly-non-overlapping AMFI feed rows. Worth flagging as a side finding regardless of the mega-category decision: scheme_universe.py's get_category_universe currently does exact string match on sebi_category, so any live scheme tagged with one of these three legacy headers is invisible to comparison against schemes tagged "Other Scheme - Index Funds" even when they track the identical index — a separate, possibly pre-existing data-completeness gap, independent of whether you build the mega-category split.

The tradeoff for your peers

- A gives a real perf/UX win but is a bespoke taxonomy Unifolio owns and must maintain — the thing your peers are likely reacting to ("why is a fintech startup inventing its own index classification instead of using SEBI's").
- B is defensible (AMFI's own words) but doesn't actually solve the mega-category problem — it's a data-completeness fix, not a scoping fix.

There's no coarse option that's both AMFI-native and actually shrinks "Other Scheme - Index Funds" to non-mega size — that's the real finding here, not a compromise I've missed. Building this well requires Option A, which is exactly the "inventing a taxonomy" concern your peers are raising. No code written; this is purely for your review.

Three ways to build it

Approach 1 — Server-side headless-browser render (recommended). Add a dedicated, unauthenticated-by-cookie "print" route in the frontend (e.g. /print/analytics?scope=...) that renders every section linearly, fully expanded — including every held fund's score breakdown inline instead of behind the S20 modal — using the exact same React components as the live dashboard. A new backend endpoint launches a headless Chromium (Playwright), navigates it to that route (authenticated via a short-lived signed export token, since a headless browser has no session cookie), calls page.pdf(), and streams the result back as a real file download.
- Why recommended: page.pdf() produces genuinely vector, crisp text — not a screenshot — and it reuses 100% of the existing formatting logic (Decimal handling, tier/badge rules, "Unavailable"/uncovered-scheme states) with zero risk of the PDF quietly drifting out of sync with the live dashboard as it evolves.
- Cost: one new backend dependency (Playwright + a Chromium binary in the deploy image — a well-worn pattern for "export view to PDF" features, but real added image size), plus building the new print-layout route and the export-token auth path.

Approach 2 — Browser-native print (window.print() + a dedicated print stylesheet). Same idea (a linear, fully-expanded print layout reusing existing components) but triggered via the browser's own print dialog with @media print CSS, letting the user "Save as PDF" themselves.
- Pros: zero new dependencies, zero new backend code — pure frontend.
- Cons: not a true one-click download (a system print dialog in between), and cross-browser print-CSS quirks (page breaks splitting a table/chart awkwardly) are historically fiddly to fully control.

Approach 3 — Backend-native PDF builder (e.g. WeasyPrint/HTML-to-PDF) from the same data models. A new Analytics Service module pulls data via the same internal functions the JSON API already uses (compute_holdings, allocation, ter, category_ranking, scorer, benchmark) and renders it into its own independent HTML/CSS template.
- Pros: most "designed as a real document" (headers/footers, pagination, branding fully under your control), no Chromium dependency.
- Cons: duplicates every bit of formatting/edge-case logic (Decimal display, tier boundaries, sentinel/"Unavailable" handling) in a second, backend-only template — a second place that can silently drift from the live dashboard's business rules over time. Most work of the three.

My recommendation: Approach 1. It's the only option that gets you a real one-click file download and never re-implements the dashboard's formatting/edge-case rules a second time — which matters a lot here given how much of this codebase's correctness (Decimal-never-float, tier boundaries, uncovered-scheme labeling) already lives in that formatting logic.

Good news: this isn't actually a three-way tradeoff — you're right that all three have something you want, but two of those "somethings" aren't actually in conflict. Here's the resolution:

Approach 3's real strength isn't the rendering technology — it's that the print output is a purpose-built document, not a screenshot of the live app's card-based UI. Approach 1 doesn't force you to give that up. The route Playwright renders (/print/analytics?scope=...) doesn't have to reuse the dashboard's on-screen layout at all — it's a brand-new React page you design specifically as a report: cover page ("Prepared for [Name] — Household Analytics Report — [date]"), Unifolio wordmark/branding, one section per page with real headers/footers/page numbers, closing with a "Powered by Unifolio" footer. It's still built with the exact same design tokens the rest of the app already uses (Docs/PRDs/Design-Schema-Unifolio.md's color/typography tokens — color-accent, color-positive/negative, the tabular-figure font rules — are just CSS variables, already wired into every component you saw in FundScoreDetailModal.tsx), so it reads as unmistakably Unifolio's document, not a generic export. Playwright then just does the mechanical "print this exact HTML to a real vector PDF" step.

So the merged approach is: Approach 1's mechanism (headless-browser render → one-click file download, zero duplicated formatting logic) + Approach 3's intent (a bespoke, branded, document-shaped template — not a live-UI screenshot). You don't have to choose between "feels personal" and "one click" — the personal/branded feel comes from how the new print route is designed, which is independent of how it gets converted to a PDF file.

This also explains why Approach 2 doesn't buy you much, as you suspected — window.print() still needs a dedicated print stylesheet to look good, so it doesn't save real design work, and it adds the print-dialog friction with none of Approach 1's upside.



Here's the full design, in sections — flag anything that's off before I write it up as a spec.

Architecture

[Analytics Dashboard] --"Download PDF"--> POST /analytics/export/token
                                              (mints short-lived export token)
       |
       v
window.location = GET /analytics/export/pdf?token=...
                                              |
                                              v
                                   Backend launches/reuses a
                                   warm headless Chromium (Playwright)
                                              |
                                              v
                          navigates to frontend's own
                          /print/analytics?token=...&scope=...
                                              |
                                              v
                          print route calls setToken(token) then
                          renders every section via the SAME
                          api.ts calls + section components as
                          the live dashboard, fully expanded
                                              |
                                              v
                          waits for a data-print-ready flag,
                          then page.pdf() -> streamed back as
                          a real file download (Content-Disposition: attachment)

Components

- New frontend route, frontend/src/features/analytics/print/PrintAnalyticsView.tsx — no nav/sidebar chrome, just a cover page (Unifolio branding, scope's display name, generation date — sourced from the already-fetched MemberStatus data, no new backend field needed) followed by every section.
- Reused as-is: AllocationSection, TerSection, CategoryRankingSection, BenchmarkSection — I checked, and all four already render their entire per-fund list unconditionally (fundRows/funds.map(...)) with nothing gated behind a click. Only the Scorer section's per-fund detail is click-gated (behind FundScoreDetailModal, opened per scheme).
- One small refactor: extract FundScoreDetailModal.tsx's inner content (the score/tier/three-ingredient breakdown) into a shared FundScoreCard.tsx. The modal wraps it in a Dialog; the print route instead maps scoreSummary.funds and renders one FundScoreCard per fund in a plain stacked list, no dialog, no click. This is the piece that makes "every fund's full breakdown, defaulted open" true — and I confirmed PortfolioScoreSummary.funds already carries every field the modal needs, so this needs zero new backend endpoint, just a frontend rendering change.
- Backend: two new routes in app/api/analytics.py, backed by a new app/services/analytics/pdf_export.py (mint-token + Playwright orchestration), reusing the same ownership checks the existing analytics routes already do.

Auth for the headless browser

The headless Chromium has no cookies/localStorage from the user's real session, so it needs its own credential:
- POST /analytics/export/token (normal session-authenticated, same as any analytics route): validates the requested scope belongs to the caller, mints an opaque random token (mirrors session.py's existing secrets.token_urlsafe + sha256-hash-for-storage pattern exactly — new export_tokens table, new Alembic migration, household_member_id nullable = aggregate scope).
- That same raw token is used twice: once by /analytics/export/pdf to authorize launching the render, and again by the print route itself (setToken(token) on mount) as the Authorization bearer for its own api.ts calls — so get_current_session's token resolution gets one small additive change: check sessions first (unchanged), then export_tokens if not found.
- Single-use, but scoped to the whole render, not per-request: the token is marked used only when /analytics/export/pdf finishes (success or failure), not on first read — otherwise the print page's own several internal fetches during that one render would invalidate it after the first one. A short absolute expiry (~2 minutes) is the backstop against a render that never completes. # ponytail:-flagged as accepting "any of this user's own read-only analytics for ≤2 minutes" as the scoped risk, rather than building narrower per-route token scoping — not worth it for an internal, single-consumer, short-lived credential.

Rendering + readiness signal

Playwright can't just navigate and immediately print — the print route's data fetches (allocation/TER/ranking/score/benchmark) are async, same five loading flags AnalyticsView.tsx already tracks. The print route sets document.documentElement.dataset.printReady = "true" once all five have settled (success or error — an errored section still has to show something in the PDF, same as it does live). The backend does page.wait_for_selector('[data-print-ready="true"]') before calling page.pdf({format: "A4", printBackground: true}).

A shared, warm Chromium instance (launched once at FastAPI startup via the lifespan hook, one new page/tab per render, not a fresh browser process per download) — spinning up a full browser per PDF request would be genuinely wasteful, not gold-plating.

Error handling

- Mint-token route 403s if the requested scope isn't the caller's own household member (same check pattern as existing analytics routes).
- Export/pdf route: expired/already-used/unknown token → 400; Playwright navigation or render failure → 500 with a generic message, token still marked used (no retry loop that could pile up warm-browser pages).
- Frontend: "Download PDF" button shows a loading state (this will take a few seconds — same cold-path cost as a first Category Ranking/Scorer load) and surfaces failure via the existing ApiError pattern.

Testing

- Backend: token mint/validate/expiry/single-use-after-render as unit tests (no real Playwright needed); one live-Playwright integration test that a real PDF byte stream comes back with the right content-type, gated the way slow/external-dependent tests already are in this repo if such a gate exists (I'll check pytest.ini/markers when writing the plan).
- Frontend: PrintAnalyticsView and FundScoreCard extraction get the same unit-test treatment as any other component here — mocked api.ts, assert every fund renders without a click.

Look right? If so I'll write this up as the spec doc and commit it, then hand off to writing-plans for the implementation plan.

You're right, and it's a better design than what I had — worth stating precisely why: Playwright's headless browser is a separate browser process from the one showing the live dashboard, so it never had access to that in-memory/cache state to begin with. My original design was quietly making Playwright redo all the same API calls (including the expensive Scorer/Category Ranking computation) a second time — genuinely double work, exactly what you're flagging.

Fix: instead of Playwright's print route re-fetching from the live analytics endpoints, the already-loaded frontend hands over the data it already has, once, and nothing gets recomputed.

What changes

- "Download PDF" button is gated on full load — disabled/hidden until all five sections' loading flags (already tracked in AnalyticsView.tsx) are false. Directly does what you asked: no download option exists until the dashboard has genuinely finished loading.
- One endpoint, not two: POST /analytics/export/pdf, body = the exact JSON already sitting in AnalyticsView's state (allocation/ter/ranking/score/benchmark — same shape as what the GET endpoints already returned, zero new serialization). Backend only validates that the caller owns the claimed scope (same ownership check as any analytics route) — it does not recompute anything.
- Backend stores that payload behind a short-lived, single-use token (in-process TTL dict, same pattern already accepted elsewhere per the ADR-006 process-local-cache precedent — no new table/migration needed for this part), launches/reuses warm Playwright, navigates to /print/analytics?token=....
- The print route makes exactly one fetch — GET /analytics/export/payload?token=... — to retrieve that stored JSON verbatim, then renders straight from it as props. No calls to getMemberAllocation/getAggregateScore/etc. from the print route at all.
- This removes the auth problem I was solving before. No export_tokens table, no new Alembic migration, no touching get_current_session/get_current_user. The token only ever guards one narrow "give me back this blob" endpoint, not the whole analytics API surface — smaller blast radius than my original design, not just less work.
- Readiness signal is still needed (data-print-ready) but now waits on one fast local fetch + render, not five independent slow computations.
- # ponytail: note for the spec: the payload is trusted as-is from the client rather than re-verified against the DB, since it's the same authenticated user immediately re-submitting data they were already legitimately shown — re-deriving it server-side would defeat the entire point of this optimization.

Everything else — the FundScoreCard extraction so every fund's breakdown renders inline, scope-follows-current-view, the bespoke branded template, components/error-handling/testing shape — stays as already agreed.

Good question to press on — and the payload-POST redesign actually answers it: we don't need a session-equivalent auth system at all anymore, and cookies would be a step backward, not forward.

Why no auth system is needed: In the revised design, the headless browser's print route makes exactly one call — fetch its own stored payload blob. It never calls any protected analytics endpoint (getMemberAllocation, getAggregateScore, etc.), so there's nothing left needing get_current_user/get_current_session to recognize it as "logged in." What it needs isn't authentication (proving who it is) — it's authorization to read one specific blob, which is a much narrower thing. That's just a capability token: a random opaque string (secrets.token_urlsafe) that's the lookup key into an in-process {token: (payload, expires_at, used)} dict, short TTL, single-use, marked used when the render finishes. No new DB table, no Alembic migration, no export_tokens, no touching get_current_session at all — smaller than what I proposed two turns ago, for the same reason the payload-POST change was smaller: nothing left to re-authenticate against.

Why cookies would be worse, not simpler:
- This app doesn't use cookies anywhere today — auth is an opaque bearer token in localStorage, sent via Authorization headers (confirmed in session.ts/apiClient.ts). Adding cookies means running two parallel auth mechanisms for two call sites, not zero.
- Cookies are automatically attached by the browser to every matching-origin request — that's exactly the CSRF surface the bearer-token-in-header design avoids by construction. Introducing cookies reopens a security tradeoff the app currently doesn't have to think about.
- It wouldn't actually remove work: you'd still mint something server-side, still need an endpoint to set it, still need expiry/cleanup (via Set-Cookie instead of a query param) — same moving parts, worse fit with the rest of the codebase.

So: keep the opaque one-time capability token, drop everything else (table/migration/get_current_session change) — that part of the earlier design was already made unnecessary once the print route stopped calling live analytics endpoints.

TASL DEFERENCE FOR THE PDF IMPLEMENTATION 

From the file - .superpowers/sdd/2026-08-20-analytics-pdf-export/progress.md)

Task 2 produces `start_browser`/`stop_browser`/`get_shared_browser`; Task 2's `main.py` lifespan and Task 3's `render_analytics_pdf`
consume them | Consistent | - Task 2: complete (commits 2f77e4b..c2d19c5, review clean; 2 minors deferred: no double-start guard on start_browser, no cleanup on partial-startup failure — both inherited verbatim from plan's reference code, negligible blast radius given single lifespan start/stop usage)
Task 3 produces `render_analytics_pdf(token: str) -> bytes`; Task 4's route consumes with matching signature | Consistent | - Task 3: complete (commits c2d19c5..bf59d1c, review clean; 1 minor deferred: import-inside-with-block in test matches brief's own reference
code verbatim, not an implementer deviation)
Task 4: complete (commits bf59d1c..788c89b, review clean; 3 minors deferred: bare str scope field vs Literal, no inline comment explaining
deliberate unauthenticated payload route, member_id has no default — confirmed already handled correctly by the plan's frontend postExportP
df/AnalyticsView wiring in Tasks 7/9, no ruling needed) - Task 4 test imports `from app.services.auth.session import get_current_user` — verified against actual `app/api/analytics.py:51` import | Matches current code |
| 5 | Task 3 config code (`SettingsConfigDict(env_file=".env", extra="ignore")`) — verified against actual `app/config.py` | Matches current code exactly | - Ruling: Task 5's brief test has no skip guard for "frontend dev server unreachable" — verified the codebase's existing environment-gated-te
st convention (tests/functional_postgres/test_partitioning.py:15-18, `pytest.mark.postgres` + a fixture that calls `pytest.skip(...)` when
TEST_DATABASE_URL is unset) always self-skips rather than erroring in a plain `pytest` run, which is how the current baseline shows "2 skip
ped" rather than failures. The brief's Playwright test as written would instead raise a real navigation error against localhost:5173 with n
o server running, breaking the full-suite baseline. Dispatching Task 5 with an added instruction: mirror the postgres-marker pattern with a
 fixture that does a quick reachability check against `settings.frontend_base_url` and `pytest.skip(...)` if unreachable, before calling `r
ender_analytics_pdf`. Cost if wrong: a slightly different skip mechanism than a hypothetical alternate design, but zero risk to correctness
 — the test still exercises the real path once the frontend is up (Task 10's manual verification step covers that).Task 5: complete (commit 788c89b..be03eec, review clean; ruling above applied — httpx-based reachability guard added, `playwright` marker r
egistered; full suite 455 passed/3 skipped, new test correctly skipped in this environment; 2 minors deferred: guard fixture has no return
value unlike `postgres_url`'s pattern, no dedicated unit test of the skip guard itself — both negligible, mirror `test_partitioning.py`'s own convention exactly)
| 6 | Task 6 produces `FundScoreCard({data: FundScoreRow})`; Task 8 consumes it with a `FundScoreRow` from `scoreSummary.funds` | Consistent |Task 6: complete (commit be03eec..4ddcda5, review clean, zero findings — `FundScoreCard` extracted as a pure presentational component match
ing brief's exact prop signature, Thin Category badge correctly not duplicated since already present in modal's `DialogHeader`, all now-unu
sed imports removed, `AlertCircle` retained, zero duplicated formatting/tier logic; 5/5 tests pass, tsc clean) Good, cachedFetch only caches GET requests, so authFetch is safe to reuse for the POST
| 7 | Task 7 produces `AnalyticsExportPayload` type, `postExportPdf`/`getExportPayload`; Tasks 8 and 9 consume both | Consistent | - Task 7: complete (commit 4ddcda5..cb4fffe, review clean, zero findings — `AnalyticsExportPayload` type + `postExportPdf`/`getExportPayload`
 added verbatim per brief; dispatched implementer hit a session/API limit mid-task after writing all code but before committing — controlle
r verified the uncommitted diff matched the brief byte-for-byte, ran tests/tsc/full-suite itself, then committed; 227/227 frontend tests pa
ss, tsc clean, no re-dispatch needed)
| 8 | Task 8's `main.tsx` route branch and Task 9's `AnalyticsView` button are independent (no shared file conflict) | No conflict | - Task 8: complete (commit cb4fffe..5ef8937, review APPROVED, zero Critical/Important findings — `PrintAnalyticsView`/`print.css`/`main.tsx`
routing added verbatim per brief; reviewer independently confirmed byte-for-byte match against brief reference code, no section-component s
ource files touched, scope-agnostic rendering, no click-gating on mapped `FundScoreCard`s, and `main.tsx` genuinely bypasses `<App />` for
the print route; brief's Step 7 literal-browser-visit was substituted with a dev-server module-resolution check since no browser binary exi
sted in the implementer's sandbox — reviewer ruled this adequate given Task 5's real-Playwright test and Task 10's later manual pass both c
over real-browser rendering of this same route; 2/2 new tests pass, 19/19 full analytics suite passes, tsc clean; 1 minor deferred: Step 7'
s exact expected-text outcome not independently reproduced against a live backend, fully subsumed by the existing jsdom error-path assertion)
Task 9: complete (commit 5ef8937..d2396b9, review APPROVED, zero findings — Download PDF button wired into `AnalyticsView.tsx`'s hero heade
r, gated on `allSectionsLoaded`/`isExporting`; payload built purely from existing component state, no re-fetch; `activeMemberName` threaded
 from `MainDashboardFlow.tsx`'s `members` list; test-mock syntax adapted to this file's existing `vi.mock`/`vi.mocked` convention instead o
f the brief's literal `vi.spyOn` — reviewer confirmed assertions preserved verbatim, no weakening; only the three brief-scoped files touche
d; 7/7 targeted tests pass, 59 files/231 tests full suite pass, both independently reproduced by the reviewer)

Task 10 is blocked on something only you can unblock: the backend's lifespan calls start_browser() on startup (from Task 2), and in this worktree's environment Chromium's binary is present but missing OS-level shared libraries (libnspr4.so and friends) — so the backend fails to start entirely right now, not just the PDF export path. I confirmed this by actually running uvicorn app.main:app and watching it crash on TargetClosedError.

playwright install chromium (what the plan calls for, and what's already been run) only downloads the browser binary — it doesn't install the OS packages Chromium needs to actually launch on Linux. That's a separate step (playwright install-deps chromium), and it needs sudo, which requires an interactive password I don't have.

Two ways to unblock this:
1. You run it: cd backend && sudo .venv/bin/python -m playwright install-deps chromium (or if that fails, sudo apt-get install -y libnspr4 libnss3 libasound2t64 covers the specific missing lib). Once that's done, tell me and I'll run all of Task 10's steps (start both servers, exercise the download flow, run the real Playwright test).
2. I substitute a code-level/API-level verification (hit the export routes directly with curl/httpx bypassing the browser render step, confirm payload storage/retrieval and route wiring work, and document that the actual PDF-rendering path and the visual/branding checks remain unverified in this sandbox) — mirroring the same documented-limitation pattern already accepted for Task 5 and Task 8.

Which would you like? Given Task 10 also has genuinely visual steps (comparing PDF branding to the live dashboard by eye), even with option 1 the very last visual judgment call may still want your own look at the output.

Root-caused: React 18 StrictMode (wrapping the print route too, in main.tsx) double-invokes PrintAnalyticsView's fetch effect in dev, and the backend's export-payload token is single-use by design — so the second getExportPayload call always 404s in dev mode. This is a real, deterministic bug for anyone verifying this feature via npm run dev. Fixing with a ref guard (the standard fix for this exact StrictMode class of bug) rather than weakening the token's single-use security property.

Root cause found: this repo lives on a WSL /mnt/d (DrvFs) mount, where Vite's file watcher often can't get inotify events, so it kept serving a stale in-memory transform of PrintAnalyticsView.tsx from before my fix — that's why the fix never actually reached the browser. Restarting the dev server (forcing a fresh read) should resolve it.

IMP ON WHY THIS WAS FIXED PROPER DECISION FOR THIS - Confirmed the discrepancy is a real content gap, not moot: compute_fund_vs_benchmark populates fundBenchmark.funds with a row for every held fund with fund-level transactions — including the seeded fund — so the "Per-Fund vs Benchmark" data genuinely exists but is hidden by the tab toggle in the PDF. Let me see the rest of the "funds" tab render block to design the minimal fix.Now applying the minimal edits: hide the tab toggle, force both blocks to render, and show all fund rows in print mode.

The fix works — the PDF is now 5 pages (was 4) and includes the previously-hidden "Verification Flexi Cap Fund Benchmark: Nifty 500 (Price Return) +28.38%... Fund XIRR +35.80%" row, with no tab-toggle button labels present. Let me verify the backend file has no residual debug instrumentation.

Good. The current dev DB already has the earlier single-member seed data; I need to wipe/reset it for a clean re-seed, since a second run would duplicate the user/phone number. Let's check for uniqueness constraints and reset the sqlite DB cleanly.

IMP FOR A PRE EXIXITNG BUG FROM DIFF SOMETHING FIXEED HERE WHILE FIXING  - This surfaced a genuine pre-existing backend bug — decimal.InvalidOperation (0/0) in _cagr (category_ranking.py:76), triggered by the aggregate-scope 3-year CAGR calculation when NAV history doesn't reach back far enough. Confirmed it's not print/export-specific: the same 500s hit the live (non-exported) dashboard's getAggregateScore/getAggregateCategoryRanking calls too, which is why the PDF correctly mirrors the degraded empty state rather than crashing. This is out of scope for the PDF-export plan — it's a pre-existing scorer/category-ranking bug, equally present on-screen. I'll ledger it for a future ticket rather than fix it here, and continue Task 10 with member-scope verification.

Both scopes verified correctly: member view shows only "Dev User"'s own holdings (excludes spouse's fund), and the BenchmarkSection fix generalizes correctly to single-fund scope too. Now running the Task 5 Playwright integration test.

TASK 10 - Task 10: complete (manual E2E verification, plus 2 real bugs found and fixed, plus 1 pre-existing out-of-scope bug found and ledgered — no
plan-file commits since this task is verification-only, but its fixes are committed on top of Task 9's HEAD).

- **Real bug 1 (fixed): React 18 StrictMode double-fetch vs. single-use export token.** `main.tsx` wraps the print route in `<StrictMode>`,
 which double-invokes `PrintAnalyticsView`'s data-fetch effect in dev mode. The export token is deliberately single-use (`consume_export_pa
yload` pops on read, by design from Task 1), so the second invocation's fetch always 404'd, and every dev-mode PDF export failed with "Expo
rt token not found or expired." **Fix:** added a `hasFetchedRef` `useRef` guard in `PrintAnalyticsView.tsx`'s fetch effect — the standard R
eact fix for this class of bug, preserving the token's single-use security property. Root-caused via `page.on("request"/"framenavigated"/"c
onsole")` instrumentation (added then fully removed from `pdf_export.py`, confirmed via `git diff` showing zero residual changes to that fi
le) plus a WSL2/DrvFs-specific detour: this repo's `/mnt/d` mount doesn't reliably deliver file-watch events to Vite, so the dev server kep
t serving a stale cached transform of the file even after editing it — a full Vite process restart (not relying on HMR) was required to mak
e the fix take effect for testing. Verified via `npx vitest run` (2/2 pass) and via live network/console instrumentation showing only one r
eal fetch.
- **Real bug 2 (fixed): `BenchmarkSection`'s per-fund tab was click-gated, contradicting the design doc.** The design doc explicitly claims
 "`AllocationSection`, `TerSection`, `CategoryRankingSection`, and `BenchmarkSection` already render their entire per-fund list uncondition
ally — nothing in those four sections is click-gated" — but `BenchmarkSection.tsx` has an internal `tab` state (`"portfolio" | "funds"`) de
faulting to `"portfolio"`, so the "Per-Fund vs Benchmark" content (and, separately, the `displayCount`-based "Show More" pagination past 5
funds) never rendered in a static/headless print render. Confirmed via `compute_fund_vs_benchmark` (`backend/app/services/analytics/benchma
rk.py:224`) that `fundBenchmark.funds` genuinely contains a row per held fund (not empty/moot for this scenario) and via the first exported
 PDF's extracted text showing the tab *label* but no per-fund row data. **Ruling:** this is a genuine design-doc/implementation conflict (f
lagged per CLAUDE.md's "stop and say so"), not a moot/theoretical one — fixed via the same pattern Tasks 6/8 used for the Scorer section's
click-gating: added an opt-in `printMode?: boolean` prop (default `false`, so the live dashboard's tab-toggle UX is untouched) that renders
 both tab panels unconditionally and shows every fund row with no pagination; `PrintAnalyticsView.tsx` passes `printMode`. Added a new test
 (`BenchmarkSection.test.tsx`) asserting both panels render with no clickable tab button present in `printMode`. Verified end-to-end: the e
xported PDF grew from 4 to 5 pages and now includes the previously-hidden per-fund benchmark row(s); confirmed again in both a 1-fund and a
 2-member/2-fund seed scenario. `npx tsc --noEmit` clean; all touched test files pass (BenchmarkSection 3/3, PrintAnalyticsView 2/2, Analyt
icsView 6/6).
- **Cover-page scope name confirmed correct, not a bug:** a single-member household showed "Dev User (Me)" (not "Family Aggregate") on the
cover page. Traced to `MainDashboardFlow.tsx`'s existing (pre-plan) logic: `viewMode` only defaults to `"aggregate"` when `household member
s.length > 1`; a lone member auto-selects `"member"` view. This is correct, pre-existing dashboard behavior the print route faithfully mirr
ors, not an export-feature defect — verified by re-seeding with a second household member and confirming the cover page correctly reads "Fa
mily Aggregate" with combined data in that case.
- **Pre-existing bug found, ledgered, NOT fixed (out of scope for this plan):** aggregate-scope `GET /household/aggregate/score` and `GET /
household/aggregate/category-ranking` both 500 with `decimal.InvalidOperation` (`DivisionUndefined`, i.e. `0/0`) in `_cagr` (`backend/app/s
ervices/analytics/category_ranking.py:76`, reached via `scorer.py`'s `compute_portfolio_score` → `_category_component_scores` → `_category_
returns`), when the aggregate household holds funds in multiple SEBI categories with NAV history shorter than the 3-year CAGR lookback wind
ow. Reproduced with a 2-member seed (one equity, one debt fund, ~2 years of NAV history each). **Ruling:** out of scope for the PDF-export
plan — confirmed via backend log that this 500 fires identically for the live (non-exported) `AnalyticsView`'s own `getAggregateScore`/`get
AggregateCategoryRanking` calls, already caught by its existing `.catch(logSectionError(...))` and rendered as a degraded empty state ("No
category ranking data available"); the exported PDF correctly and faithfully mirrors that same degraded state rather than crashing, so no e
xport-side code is at fault. Recommend a follow-up ticket against `category_ranking.py`'s `_cagr`/`_category_returns` to return `None` (mir
roring this codebase's existing `insufficient_history` pattern) instead of a bare `Decimal("0")` when no NAV data exists at a lookback date
, rather than dividing two zero values.
- **Verification performed:** seeded a minimal real household (initially 1 member/1 fund, later extended to 2 members/2 funds across two SE
BI categories) directly against the running dev backend's real sqlite DB; logged in via the real dev-mode OTP flow; drove a real non-mocked
 headless Chromium browser (Playwright, not the plan's own integration test) through the live UI's Analytics tab → Download PDF flow for bo
th aggregate and member scopes; extracted and read the actual downloaded PDF bytes via `pypdf` each time. Confirmed: cover page with correc
t scope name in both scopes; all 5 sections present (once bug 2 was fixed); every held fund's score/benchmark breakdown visible with zero c
licks; member-scope PDF correctly excluded the other member's holdings/fund entirely (allocation, TER, and benchmark sections all scoped to
 the one member only). Ran Task 5's real (non-skipped) Playwright integration test: `pytest tests/services/analytics/test_pdf_export_integr
ation.py -v -m playwright` → **1 passed**. All seed data and the one-off seed script (`backend/scripts/seed_pdf_export_verification.py`, de
leted per its own docstring) removed from the dev DB after verification; `git status` on `backend/app/services/analytics/pdf_export.py` con
firmed zero residual diff from debug instrumentation.

Codex's review surfaced two genuine, spec-confirmed defects and one finding I need to rule on. The design spec explicitly says (line 157-158): "Playwright navigation/render failure → 500 with a generic message; the token is cleaned up... regardless of success or failure" — so the print-ready/error-marker conflation and the missing failure-path token cleanup are both real, spec-mandated bugs. The third finding (FundScoreCard's parseFloat/toFixed) I'm ruling as not a defect: frontend/src/lib/decimal.ts's own docstring — an established, pre-existing repo convention — explicitly exempts a single, non-accumulating final-value-to-display conversion; FundScoreCard does exactly that (no summing), and it's the same pre-existing component the live dashboard already renders this way.

Review round 1 result: Not ready to merge — 2 real, spec-confirmed defects found (both traced to explicit text in the design spec, lines 157-158): a false-success PDF when the export payload fetch fails (error and success states shared the same "ready" marker), and export tokens never getting cleaned up when rendering fails before the frontend's own payload fetch. A third finding (FundScoreCard's display-only parseFloat) I ruled not a defect — it matches an established, pre-existing repo convention documented in decimal.ts that explicitly exempts single, non-accumulating display conversions.

Just dispatched: the two confirmed fixes to Codex, with exact code changes specified, plus a requirement to add regression tests and run the full backend/frontend suites before reporting done. All findings, the ruling, and the fix instructions are committed to Docs/orchestration/analytics-pdf-export-final-review-handoff.md (commit 04487df) so this survives if my session ends before Codex reports back.

The scoped re-review found one real gap: Finding 1 is fully fixed, but Finding 2 only catches except Exception — asyncio.CancelledError derives from BaseException in Python 3.8+, so a cancelled render (client disconnect, timeout) still skips token cleanup. This is small enough to fix directly rather than round-tripping through Codex again.

Quick status update while that final review runs in the background:

- Fixed the cancellation-cleanup gap directly, added a regression test, full backend suite green (458 passed, 3 skipped), committed as 86c60c5.
- Merge-conflict check already done: git merge-tree between feat/enhanced-ui and worktree-analytics-pdf-export resolves clean with zero conflicts (feat/enhanced-ui gained two unrelated Distributor Comparison commits since this branch forked, but they don't touch any file this branch touches).
- One last scoped re-review (of just this cancellation fix) is running now — once it confirms clean, I'll merge into feat/enhanced-ui immediately and report back on whether we're fully done.


Done this turn:
- Confirmed all Task 10 fixes were already committed (4ce4561) and the worktree is clean.
- Wrote a handoff doc (Docs/orchestration/analytics-pdf-export-final-review-handoff.md) covering what to review, what's already settled (don't re-litigate the StrictMode fix, the BenchmarkSection printMode fix, or the ledgered-but-out-of-scope category_ranking.py bug), and the read-only/no-merge constraints.
- Updated session.md and CLAUDE.md's status pointer, logged the delegation decision in delegation-log.md, and committed all of it (650d049).
- Dispatched the final whole-branch review to Codex (not a Claude subagent) to keep this off your Claude quota — I'll get a notification when it reports back.

Rulings made this session/branch, for your record:
1. BenchmarkSection's tab/pagination gating was a real bug vs. the design doc → fixed with an opt-in printMode prop, live UX unchanged.
2. StrictMode double-fetch against the single-use export token → fixed with a useRef guard.
3. category_ranking.py:76's _cagr 0/0 crash on aggregate multi-category scoring → confirmed it also breaks the live dashboard (not PDF-export-specific) → ruled out of scope, ledgered for a follow-up ticket, not fixed here.
4. Single-member cover page reading "Dev User (Me)" → confirmed correct existing behavior, not a bug.

Are we done? Yes — all 10 plan tasks, both review rounds (2 Important export-failure gaps + 1 Medium CancelledError cleanup gap), and the final "Ready to merge? Yes" verdict are all closed out and merged. The only pre-existing, explicitly out-of-scope item found along the way is the category_ranking.py:76 DivisionUndefined bug — ledgered for a follow-up ticket, not blocking anything here. Safe to close this session.


An error that I was able to identify working with this PDF for while trying to test the PDF feature we have just made in Localhost is that First section
  that needs to be coming that is the portfolio allocation section is not currently getting shown in the PDF. Let me give you a screenshot for the same
  [Image #19] I can see the separate category allocation and not the AMC. Again, I think this is a tab issue where switching between both of them is run
  through the cab as you can see in the screenshot is AMCM category. So maybe that's an issue because of which I only can see this distribution or the
  category and I cannot see the graph clearly as well. So fractal isolis what I'm trying to show you to understand which kind of I am trying to talk about

Another error identified - 

That matches the exact bug class already found/fixed once in this feature (Task 10: BenchmarkSection's click-gated tabs being invisible in a static PDF render) — looks like AllocationSection's Category/AMC toggle never got the same printMode treatment. Let me check the code.

  Read 7 files, ran 6 shell commands

Root-caused both errors — this is one bug report with two distinct causes:

1. AMC tab invisible: AllocationSection.tsx has a Category/AMC toggle driven by pure click state (useState), same bug class already found and fixed once in this feature (Task 10's BenchmarkSection fix) — but AllocationSection never got the same printMode treatment PrintAnalyticsView.tsx gives BenchmarkSection. Since Playwright never clicks anything, only the default "category" tab ever renders into the PDF.
2. Donut barely visible: PieSlice.tsx's entrance animation draws each slice from 0% via a motion/react spring with a per-slice stagger delay. The backend's render_analytics_pdf (pdf_export.py) captures the PDF the instant data-print-ready appears — before that animation finishes — so Playwright snapshots the donut mid-draw (matches your screenshot: a thin sliver, not a full circle). PieSlice already has a built-in static/instant render path (animate={false}), just never wired through.

Let me check the existing tests before fixing.

  Read 3 files, ran 4 shell commands

Now implementing the fix — adding a printMode prop to AllocationSection (mirrors BenchmarkSection's existing pattern: hide the toggle, show both breakdowns) and forwarding a non-animated render path through AllocationDonut → PieSlice so the donut is fully drawn instantly instead of mid-animation. Writing regression tests first.

Both root causes are fixed:

1. AMC breakdown invisible — AllocationSection.tsx gained a printMode prop (mirrors BenchmarkSection's existing pattern): hides the Category/AMC toggle and renders both donuts stacked instead of tab-gated. Wired into PrintAnalyticsView.tsx.
2. Donut barely visible — AllocationDonut/PieSlice were animating the arc in from 0% via a staggered spring; Playwright's page.pdf() captured before that animation finished. Added an animate prop threaded through to PieSlice's existing (already-built, just unused) static render path, set animate={false} for both print-mode donuts so they draw fully instantly.

Verified: new regression tests (AllocationDonut.test.tsx, new AllocationSection.test.tsx) red→green, full frontend suite 335/335 passing, tsc -b --noEmit clean.


------------------------------------------------------------------------------------------------------------------------------------------------------------------------

NEW DISTRIBUTOR ANAYSIS



Architecture - For the new portfolio level distributor analysis

No new subsystem, no DB schema change (ARN is already captured per-folio) — this is a restructuring of one existing service into the same "member-list-in, aggregate-or-single" shape every other dashboard section already uses (aggregate.py's pattern: compute_holdings(db, [member_ids]), wrapped once for a single member's route and once for the family-aggregate route). distributor_comparison.py is the only outlier still scoped to (member_id, scheme_id) — this brings it in line.

Data model / backend

- Old: compute_distributor_comparison(db, household_member_id, scheme_id) → flat list of DistributorComparisonRow for one scheme. Removed entirely.
- New: compute_distributor_comparison(db, household_member_ids: list[uuid.UUID]) → groups all folios for those members by (arn_code, scheme_id, household_member_id) — same granularity compute_holdings already uses, so cross-member combining follows the exact existing convention (never silently merged; member identity carried on each row, showMemberName-style). Two-level result:
  - DistributorPortfolioRow — one per distributor (ARN or Direct): name, ARN code, status, totals only (invested, current value, realized/unrealized gain, total profit) — no units/avg NAV, since those aren't meaningful summed across different schemes.
  - nested schemes: list[DistributorSchemeBreakdown] — one per (scheme, member) under that distributor: scheme name, member name, units, avg NAV, invested, current value, gains (this level keeps units/avg NAV since it's single-scheme).
- Current NAVs for all distinct held schemes fetched via the existing batch helper (get_navs_on_or_before in nav.py, from the earlier dashboard-load-time fix) instead of one-NAV-per-call — avoids re-introducing the N+1 pattern that was already fixed elsewhere for holdings.
- Missing-NAV behavior: if one scheme's NAV can't be resolved, only that scheme's breakdown row is excluded — not the whole distributor comparison (old code returned [] entirely on a NAV miss, fine when scoped to one scheme; not fine now that one request spans the whole portfolio). This mirrors the pre-existing "NAV-unavailable holding vanishes silently" behavior already accepted elsewhere in the app (CLAUDE.md's open item #1) — not solving that open question here, just staying consistent with it.
- Routes: replace the old /household-members/{member_id}/schemes/{scheme_id}/distributor-comparison with /household-members/{member_id}/distributor-comparison (single member, all schemes) and /household/aggregate/distributor-comparison (all members) — same members: list[MemberStatus] envelope every other aggregate response already uses.

Frontend

- Remove: the "Compare Distributors" trigger and onCompareDistributors callback from FundDetailModal.tsx and MobileFundDetailView.tsx entirely.
- Add: a "Compare Distributors" button in DashboardView.tsx's Holdings section header (next to the existing member filter), opening DistributorComparisonModal — now driven by the page's existing viewMode/memberId, same as every other section, no new state.
- Modal content: table of distributor rows, each row expandable (click/chevron) to reveal its nested per-scheme breakdown rows underneath — member name column shown only when viewMode === "aggregate", matching HoldingsTable's existing showMemberName convention.
- Mobile: MobileDistributorComparisonView.tsx gets a real mobile-appropriate layout, not a shrunk table — an accordion/expandable-card list (one card per distributor, tap to expand into per-scheme rows), consistent with the rest of the mobile holdings UI. New trigger point analogous to desktop's, off the mobile Holdings screen rather than the fund detail view.

Testing

TDD throughout per AGENTS.md. Backend: rewritten unit tests for the new grouping/aggregation (single-member, multi-member combine, missing-NAV partial-exclusion, Direct-plan and unresolved-ARN cases carried over from existing tests), route tests for both new endpoints, confirming the old route is gone. Frontend: DistributorComparisonModal.test.tsx rewritten for the new fetch shape and expand/collapse behavior; FundDetailModal.test.tsx/DashboardView.test.tsx/mobile equivalents updated to drop the removed trigger and cover the new one.

Does this all look right? If so, I'll write it up as a spec doc and then hand off to the writing-plans skill for the implementation plan (per model-orchestration, likely delegated to Codex with the mandatory review gate).

Good catch — let me verify whether the existing compute_holdings/compute_distributor_comparison code already batches transaction fetches, or does one DB query per folio (a real N+1 risk that gets worse once this spans the whole portfolio instead of one scheme).

  Read 1 file

Good — this exposes something important: compute_holdings itself still does a per-folio Transaction query inside its loop (a real N+1, not yet fixed), and its 15-min TTL cache is at (member, scheme, plan_type) granularity — which collapses across ARN, so it can't directly supply the per-distributor breakdown data (that needs a finer (member, scheme, arn_code) split the holdings cache doesn't carry). Let me check how that cache gets invalidated so I can reuse the same signal rather than invent a new one.

  Searched for 2 patterns

Good instinct — this surfaces a real fix. Here's what changes in the design based on your feedback:

1. Compute all distributors together, one pass — not one at a time.
Already the plan structurally (group all folios first, then loop), but I'll tighten the actual DB access pattern: fetch all folios for the relevant members in one query (already planned), then fetch all transactions for those folios in one query (Transaction.folio_id.in_(all_folio_ids)) instead of looping and querying per folio. Worth flagging: I checked, and this per-folio transaction query is actually already an N+1 pattern in the existing code (compute_holdings and the old compute_distributor_comparison both do it) — never fixed before because a single scheme's folio count is small. It matters more now since one distributor-comparison call spans every folio in the portfolio, so I'll fix it here rather than carry it forward.

2. NAVs batched, not per-scheme — confirmed, using the existing get_navs_on_or_before batch helper, one call for every distinct held scheme.

3. Reusing the caching that's already built — one honest caveat first: compute_holdings's existing 15-min cache stores rows collapsed to (member, scheme, plan_type) — it doesn't keep the per-ARN split, so its rows can't be reused directly as the distributor breakdown's data source (finer granularity is unavoidable — that's the whole point of this feature). But two things genuinely are reusable, and I'll use both:
- The exact same caching pattern (TTL lock + generation-keyed cache) holdings.py already has, applied to the new distributor-comparison result itself, so a second dashboard load/toggle within 15 minutes skips recomputation entirely.
- holdings.py's existing invalidation signal (_holdings_cache_generation, already bumped on every import-confirm) — reused as-is for the new cache's key, so no new invalidation wiring is needed anywhere.

4. Missing-NAV partial exclusion — confirmed as discussed.


Understood — cautious, scoped correctly. I'll build the new distributor-comparison function batched from the start (no N+1 to begin with, since it's new code), but leave compute_holdings's existing N+1 untouched — it's a working, already-heavily-reviewed path outside this feature's scope, and fixing it carries regression risk you didn't ask me to take on. I'll note it as a flagged follow-up in the spec rather than touch it now. Caching: confirmed, reusing the pattern + existing invalidation signal, nothing new.

Now I need to store generation on publish, since the dataclass gained that field.

IS THIS PROBABALY AN ISSUE TO FIX - Implementer reported BLOCKED (9/10 passing): the brief's own prescribed implementation and its own test contradict each other. `_distributo
r_cache`'s read path returns any TTL-fresh cached entry without consulting `_holdings_cache_generation`, so `invalidate_holdings_cache(memb
er.id)` (which only physically purges holdings.py's OWN `_holdings_cache` dict, per holdings.py:62-68) cannot make `test_..._invalidated_by
_holdings_cache_generation_bump`'s `assert (...) not in _distributor_cache` pass — no code path ever deletes that key on invalidation as pr
escribed. Implementer correctly declined to fix this itself (would mean inventing logic beyond "apply the brief verbatim") and correctly de
clined to touch holdings.py (forbidden by the brief).

The review found a genuine cross-lock race: the fix reads _holdings_cache_generation under _distributor_cache_lock, but invalidate_holdings_cache writes it under _holdings_cache_lock — a different lock guarding the same dict. Rather than accepting this as a documented limitation, I can close it cleanly by importing holdings.py's own lock object (zero modification to that file) and reading the generation dict under it, matching holdings.py's own discipline exactly.

The re-review found the lock-discipline fix introduced a new race: reading the generation snapshot and checking/publishing the cache as two separate lock scopes leaves a window where a concurrent invalidation can slip in between them, letting a stale cache entry be served or overwrite a fresh one. This is a genuine correctness issue, not just a coverage gap — starting fix round 2.

Current state: Task 1 is fully complete (implementation + 2 fix rounds, all re-reviewed clean). Task 2 (backend routes + aggregate endpoint) is in progress — Codex implementer job task-mt1t0832-zies7s is still running (in its "verifying" phase, ~11 minutes in), already reporting collection errors dropped from 85 to 0 across 457 tests. I have a bounded monitor polling it every 30s and will pick up the report, commit, and dispatch the task-scoped review as soon as it finishes — no action needed from you right now.

Task 2 review: Approved, spec-compliant, only one Minor finding (mixed CRLF/LF line endings in dashboard.py, non-functional). Let me check if that's easy to normalize before closing out Confirmed — 31 lines use bare LF against 194 CRLF elsewhere in the file. Trivial to normalize; fixing inline rather than looping back to Codex for a cosmetic one-liner.Same issue as Task 2 — Codex rewrote these files as pure LF, but they were CRLF originally, which inflated the diff to touch every line. Normalizing back to CRLF before staging.This CRLF-normalization issue has now hit twice in a row (Task 2 review finding, Task 3 pre-empted) — worth logging as a recurring pattern for the model-orchestration skill.All CRLF. Instructing the implementer explicitly to preserve line endings, and flagging the Fragment-key bug in the plan's code as a ruling.All CRLF preserved. Verifying the Fragment-key ruling was applied correctly before committing.Line-ending styles correctly preserved per-file (.tsx stays pure LF, .test.tsx stays pure CRLF). Re-running the focused test file and tsc myself.


All remaining errors are in mobile files not yet touched — exactly as the brief predicted (resolved by Tasks 7-8). No DashboardView.tsx errors remain. Diff verified clean, committing as orchestrator.

The reviewer's finding is a real artifact — my own delegation-log dispatch commit (130fca0) landed between the BASE I recorded and the implementation commit, so it got swept into the diff range. Not a code defect; a review-scoping mistake on my part. Correcting and re-dispatching with the proper narrow range.

The brief's brokeredRow test fixture is an untyped object literal with arn_status: "ACTIVE" — the same defect Task 5 hit and fixed (widens to string, fails tsc against the literal-union type). Pre-empting that in the dispatch instructions rather than letting it recur through a review round-trip.


Progress: Tasks 1–9 of 11 are complete and merged into this worktree's branch, each with a clean task-scoped review (Task 7 needed a ruling on a review-scoping artifact, not a code fix — documented in the ledger). Task 10 (mobile MobileDashboardView wiring — likely just prop-threading viewMode/memberId into MobileHoldingsView, given Task 9 already added the trigger there) is staged and ready to dispatch. Remaining after that: Task 11 (full-suite verification + docs) and Task 12 (final whole-branch review).

That confirms the full expected file set: backend service/schema/routes, desktop + mobile frontend files, plan/spec/docs. Total: 28 files, 4269 insertions, 521 deletions — exactly matching this feature's scope. Generating the review package.

The final review returned "Ready to merge? No" — one Critical, one Important, one Minor finding. Per SDD process this gets one fix dispatch + one scoped re-review. Let me inspect the flagged code before writing the fix brief.Let me check whether the codebase already has a decimal-safe currency formatter elsewhere (the desktop HoldingsTable/other views must format money without floats too).TTL is 900s (cache_age <= 900), so expiry needs now[0] += 901. Now let me fix all three: the two frontend files, the backend test, and session.md's stale text.

NAV TTL Update - I'll add a TTL-expiry test right after the reuse-inside-TTL test, mirroring its structure with now[0] += 901.0 and asserting the NAV lookup runs again.

This re-review found a real Minor edge case: -0E-8 (Decimal scientific notation) misclassified as negative. Let me check whether the backend can actually emit that format for unrealized_gain.The re-review surfaced one legitimate residual: -0E-8 (Decimal scientific notation for a negative-signed exact zero) would misfire the digit-presence regex. Per SDD's "ONE fix dispatch, one scoped re-review, adjudicate residuals" — this is the adjudication step. It's trivial and money-correctness-adjacent, so I'll close it directly rather than spin another full review round.

Task 12's ledger entry is now committed. Here's the full accounting before any merge/push action, per the SDD stop condition on side effects outside this worktree.

Rulings made across this plan (13 total)

Setup/process:
1. Satisfied model-orchestration's handoff-doc requirement with the SDD task-brief file instead of a separate doc (brief is a strict superset).
2. Task 1: treated the plan's code block (10 tests) as authoritative over its prose ("11 tests") — no missing scenario.

Cache-invalidation correctness (Task 4-5, 3 fix rounds):
3. Fixed generation-field cache invalidation inline (reject-and-recompute on generation mismatch).
4. Fixed a lock-import contradiction inline (reused holdings.py's existing _holdings_cache_lock).
5. Fixed lock-atomicity inline (widened lock scope to cover the full capture-then-check/publish span).
6. Accepted the resulting Minor (no deterministic concurrency test for the now-fixed race) as a documented limitation — the fix itself was independently re-verified twice; a real test needs thread-barrier scaffolding unused elsewhere in this codebase.

Task 7 (routes):
7. Accepted a "2 observed vs ~85 expected" collection-error count discrepancy as immaterial — collection errors are 0 post-fix, directly re-verified.
8. Fixed a CRLF/LF inconsistency inline (cosmetic, zero functional risk).
9. Review-scoping artifact: regenerated a corrected review package excluding an incidentally-committed docs entry so the re-review targeted only the real code change.

Frontend (Tasks 7-8):
10. Fixed 3 orphaned-code defects inline; left one purely cosmetic formatting deviation as-is.
11. Plan defect: instructed the implementer to use <Fragment key={key}> instead of the brief's shorthand <> (which can't take a key, a real React console-warning defect).

Task 12 (final review):
12. Fixed all 3 final-review findings (Critical float-usage, Important missing TTL test, Minor stale docs) directly as orchestrator rather than a fresh Codex round.
13. Adjudicated the re-review's single Minor residual (scientific-notation zero sign-check) directly rather than a third Codex round — backed by direct Python reachability testing.

Branch divergence — needs your call before merge

feat/enhanced-ui has moved 133 commits ahead of this worktree's branch point since it was created (git merge-base HEAD feat/enhanced-ui → 1620149). This feature branch (28 files, +4269/-521 against that merge-base) will need a rebase or merge-conflict resolution against feat/enhanced-ui's current tip before it can land — it won't fast-forward.

Final scope: commits 848a1fd, b01ef0d, 0f3fafd close out Task 12. Full review chain: 1 whole-branch review (3 findings) → 1 fix → 1 scoped re-review (1 residual) → adjudicated. All backend (456/2 skipped) and frontend (230/56 files) tests green, tsc clean.

How would you like to proceed with the merge — rebase this branch onto feat/enhanced-ui's current tip myself, or would you rather handle that integration yourself?

The merge is complete and fully verified. Summary:

- Resolved all 3 real conflicts (CLAUDE.md, session.md, Docs/orchestration/delegation-log.md — docs only; every code file auto-merged clean), merge commit 7e668f2.
- Verification on the merged tree: backend pytest 563 passed/3 skipped, frontend vitest 332 passed across 71 files, tsc --noEmit clean (had to install the new google-auth dependency feat/enhanced-ui's auth work introduced).
- Logged the merge and verification to Docs/orchestration/delegation-log.md (commit cea923d).

One open item I haven't acted on: feat/enhanced-ui's own branch pointer still needs advancing to include this work, and that branch is checked out in a different worktree (your main checkout), outside this session's isolation boundary. This branch (worktree-distributor-comparison-portfolio-level, now at cea923d) is merge-ready but I haven't touched feat/enhanced-ui itself — how would you like that done (e.g. fast-forward feat/enhanced-ui to this commit from the main checkout, or something else)?

All checks pass — everything defined for this task is done.

Verified from this side:
- feat/enhanced-ui (local) is at f0aed4a, with cea923d (this branch's merge + verification commit) confirmed as an ancestor — a clean fast-forward, not a divergent merge.
- origin/feat/enhanced-ui already matches local exactly (f0aed4a, 0 commits ahead/behind either way) — it's already pushed, nothing outstanding there.
- The one commit on top of cea923d (f0aed4a, "chore: add package-lock.json to gitignore") is a small unrelated commit you made directly afterward — not something from this task, no conflict with it.

Full task status:
- Merge-conflict resolution (not rebase, per your instruction) — done, merge commit 7e668f2, only 3 real conflicts (all docs), everything else auto-merged clean.
- Full verification gate on the merged tree — done: backend 563 passed/3 skipped, frontend 332 passed/71 files, tsc --noEmit clean.
- feat/enhanced-ui branch ref advanced — done, fast-forwarded and pushed to origin.
- No release action was taken, consistent with "prepare for beta/h2, not a release."

Nothing outstanding on my end for this task.

--------------------______________________________________________________________________________________________________

Current state - 24-08-26

This worktree (worktree-distributor-comparison-portfolio-level, off feat/enhanced-ui) just finished the portfolio-wide Distributor Comparison rewrite (PRD-03 FR-11): the old per-fund "Compare Distributors" CTA is now one portfolio-wide trigger (desktop + mobile) showing every distributor across the whole household with expandable per-scheme breakdowns.

- Built via superpowers:subagent-driven-development, 12 tasks total, each through Codex-implements/orchestrator-verifies/task-scoped-review.
- Final whole-branch review: 1 fix round (Decimal-float violation, missing TTL-expiry test, stale docs — 848a1fd), 1 scoped residual fix (Decimal scientific-notation sign-check gap — b01ef0d).
- Already merged into feat/enhanced-ui via conflict resolution (not rebase — that branch had moved 133 commits ahead). Only 3 conflicts, all docs; everything else auto-merged clean.
- That merge also pulled in feat/enhanced-ui's other recent work: the authsetup merge (Auth/Onboarding/CAS-import-v2/Mobile polish, 100% done) and the Analytics PDF export feature (all 10 tasks, reviewed, merged).
- Working tree is clean (only the untracked, pre-existing backend/.venv).

Not done here: .ua/knowledge-graph.json is stale as of commit 35fedd3 — predates this rewrite and everything else merged in. Worth an incremental /understand re-run before trusting it for other tasks.

Six known open items carried forward (none new, none blocking): silently-vanishing NAV-less holdings, missing DB uniqueness constraint on "self" household member, a dead HoldingsTable.tsx field reference, a non-index-seek-bounded SQLite scan in category ranking (Postgres follow-up), an incomplete ARIA tabpanel pairing on the SIP tab control, and compute_holdings's pre-existing per-folio N+1 query (found as a side effect of this task, out of scope). Full detail on each is in CLAUDE.md's "Still open" list.

Nothing is currently in-flight — this looks like a natural stopping point. Let me know if you want me to look at any of the open items, refresh the knowledge graph, or pick up the next piece of work.

___________________________________________________________________________________________________________________________

TER ERROR - 

Read amfi_ter_client.py + ter.py and confirmed the mechanism the antigravity write-up described is real — but that write-up missed the actual reason it differs between your two laptops, which is the actual root cause of your confusion. Here's what's going on:

Why they diverge — it's not the same backend

localhost:5173/localhost:8000 on each of your machines is not the same running server. Each of you is running your own independent backend process against your own local SQLite file:

app/config.py:7:  database_url: str = "sqlite:///./unifolio_dev.db"

That's the local-dev-first architecture (per AGENTS.md): every dev runs their own backend + their own SQLite DB. Two consequences follow directly:

1. scheme_ter is a per-machine table. Your machine has presumably already run a successful TER refresh at some point, so your local scheme_ter has rows. Your colleague's local DB is a separate file — if her backend's first refresh attempt hit AMFI's 429, her scheme_ter stayed empty.
2. The 15-minute backoff timer is an in-memory Python global, per-process:
_last_ter_refresh_attempt: float | None = None   # ter.py:49
2. It isn't in the DB, isn't shared, and resets to None the instant her uvicorn process restarts. So it's entirely possible for her backend to be sitting in a 429-triggered backoff window while yours never even needed a refresh recently (your _missing_current_month_ter check comes back "already covered" and skips the fetch entirely).

So "same code, same localhost, different result" is expected here — "localhost" means "my own machine" for each of you, not a shared server. Nothing is broken; you're just looking at two independent, out-of-sync caches.

Immediate unblock for her

Restart her backend (or touch a file under backend/app/ if using --reload) — that resets the in-memory backoff instantly and it'll retry the AMFI fetch on her next Analytics load.

Actual root cause worth fixing

_TER_FETCH_CONCURRENCY = 20 was a documented judgment call — the comment in amfi_ter_client.py explicitly says "this endpoint has no documented rate limit" (2026-08-20). Your colleague's session just falsified that assumption with a live 429. That's a real finding, not just bad luck.

Want me to lower the concurrency (e.g. to 5) and add a retry-with-backoff on 429 specifically, so this stops being a coin-flip for whoever's laptop happens to fetch first? That's the actual fix — restarting her backend only papers over it until the next cold fetch.

All 62 TER tests pass. The concurrency change is committed to your working tree (not yet git-committed — say if you want that as a separate commit).

Recommendation

Lower concurrency (done above) — not retry-on-429. Adding a retry loop inside amfi_ter_client.py would duplicate what ter.py already does: any failed refresh is automatically retried on the next Analytics load after the 15-min backoff. Two retry layers stacked on each other is complexity you don't need. Cutting _TER_FETCH_CONCURRENCY from 20 → 5 fixes the actual cause (AMFI's limiter) so the first attempt just succeeds.

Short answer: no meaningful impact on normal usage — this only touches a rare, background-ish refresh path, not per-request loading.

Where the cost actually lands

_TER_FETCH_CONCURRENCY only matters when refresh_ter_data actually runs, which only happens when _missing_current_month_ter is true — i.e. at most once per 15-minute backoff window, and only if some held scheme's current-month TER isn't cached yet. Once it's cached, every dashboard load is a plain DB read — concurrency is irrelevant to that path entirely.

When it does run, how much slower

From the existing comment's own numbers: concurrency 1 (fully sequential) took ~4 minutes for ~380 pages, concurrency 20 got that down to roughly 10-15s. Concurrency 5 lands in between — back-of-envelope, ~4x the pages-per-batch of 20, so somewhere around 40-60s instead of 10-15s. Still a huge improvement over sequential, just not as fast as 20.

Scaling

This isn't tied to your app's scale at all — it's one shared national AMFI bulk endpoint (~380 pages, grows only as slowly as AMFI's own scheme count industry-wide), not per-user or per-portfolio. More users or bigger portfolios don't make this fetch bigger. And _ensure_ter_fresh's lock already coalesces concurrent requests so only one caller ever pays this cost at a time, not one per request.

Net effect: whoever's request happens to trigger a refresh (rare — first load after a new month rolls over, or a fresh install/empty DB) waits an extra ~30-40s that one time. Everyone else, every other load, is unaffected. Worth it to stop the 429/empty-TER problem from recurring.

___________________________________________________________________________________________________________________________


Updated Fund scorer - 

Docs/Updated_and_Approved_Unifolio_Fund_Scoring_Methodology.md

The next task is related to the fun score methodology that we have built. According to my current knowledge My current understanding:
  - Fund score ingredients: Return 45%, downside-risk 30%, consistency 25%.
  - Return uses peer percentile of blended 3-year/5-year CAGR, weighted 40%/60%.
  - Risk uses five years of monthly downside deviation; lower downside ranks higher.
  - Consistency is the percentage of rolling 12-month periods in which the fund meets or beats its category median.
  - The blended component score is re-ranked against eligible category peers.
  - Current tiers use equal percentile bands: 80/60/40/20.
  - TER adds ±0.25 outside a ±0.05 percentage-point dead zone.
  - Final scores are clamped to 0–100.
  - Portfolio scores are current-value-weighted and disclose covered versus total value. Primary references:
  - [Scorer methodology](D:/Unifolio code/Docs/Scorer-Methodology-Unifolio.md)
  - [Canonical PRD-04](D:/Unifolio code/Docs/PRDs/PRD-04-MF-Analytics-Dashboard.md)
  - [Formula review](D:/Unifolio code/Docs/Analytics-Dashboard-Formula-Implementation-Review.md)
  - [Correction plan](D:/Unifolio code/Docs/Analytics-Dashboard-Internal-Correction-Plan.md)
  - [Current scorer implementation](D:/Unifolio code/backend/app/services/analytics/scorer.py) What I now want you to do is go through the doc that I've just updated which is the Docs/Updated_and_Approved_Unifolio_Fund_Scoring_Methodology.md What I have provided you above is the approved scorer methodology that has been updated by my financial lead, my financial founder who has experience in CA and all that stuff in finance. This is the approved fund scorer that has come from this side. What I want you to dnd score The approved methodology is not a small adjustmentto the existing scorer. It is a scorer v2: the surrounding infrastructure remains useful, but the scoring engine, stored breakdown, UI explanation, and several data pipelines must change. Using codecs, I reviewed a methodology and here are some reviews The approvedmethodology is not a small adjustment to the existing scorer. It is a scorer v2: the surrounding infrastructure remains useful, but the scoring engine, stored breakdown, UI explanation, and several data pipelines mnt
  - Overall difficulty: high, but quite achievable.
  - Formula-only difficulty: medium.
  - Full approved methodology difficulty: high because of missing external data—not because the math is unusu
  ──── (129 lines hidden) ────────────────────────────────────────────────────────────────────────────────────────────────────
  ny minimum available-weight threshold below which renormalization should not produce a score?
  Recommended change order
  1. Freeze the calculation annex. Resolve the fourteen definitions above and correct the component/bucket count.
  2. Run data-source feasibility spikes. Validate category bench and AAUM—especially valuation, the critical path.
  3. Design scorer v2 persistence and versioning. Migration, component breakdown, confidence status, data dates, and cutover strategy.
  4. Build a golden financial dataset. Finance-approved examplesercentiles, missing-data normalization, and final scores.
  5. Build the pure NAV metric engine using TDD. Return, consistency, drawdown, and Sortino first.
  6. Add benchmark-relative metrics. Down capture, Information Rnchmark policy is locked.
  7. Add cost-level and cost-trend history.
  8. Add valuation last. It has the largest external dependency ailable under the approved gating rule if product accepts that rollout.                                                                                                                                                  9. Build the scheduled/category-level precomputation path.
  10. Change APIs and UI. Desktop, mobile, fund detail, portfolio roll-up, and PDF export.                                                                  11. Run numerical reconciliation and performance tests.
  12. Release behind a version/feature flag, compare v1 and v2, then cut over.                                                                              Bottom line: this is a substantial scorer rebuild, but not a ghe difficult part is acquiring and governing the newbenchmark, valuation, and historical cost data. If those inputs are solved and scoring is precomputed, the user-facing loading time does not need to      increase. This is all the planning I've done till now for thisl the planning and suggest me this planning is actually notdone by me by Codex. So suggest what this is correct and this is how should we go forward with this will be built as a completely different I do not want to say worktree because I do want to test it out so maybe a di substantially big feature so it needs to be built out as acompletely different branch That is one thing that I want to make sure I do not want to currently interfere in the current schooler let's just maintain a
  different branch for that and yeah just go through all of thiss and what should we do and how should we do it and if Codexhas said something wrong or given something wrong because all of this is provided by Codex


I read the approved-methodology doc, scorer.py, schemas.py, benchmark.py, the fund_scores schema entry, and PRD-04's FR-5 section directly rather than taking Codex's summary at face value. Here's where that lands.

Codex's assessment is largely right — verified, not just trusted

- The 10-vs-11 component discrepancy is real, not a Codex nitpick. I read the doc myself: the overview says "ten weighted components across six buckets," but the table has 11 rows across 7 buckets (Return; Consistency split into BeatsAvg 12% + TopQuartile 8%; Downside Risk split into Drawdown 7.5% + DownCapture 7.5%; Risk-Adjusted Efficiency; Upside Participation; Valuation; Cost split into Level 6% + Trend 4%), summing to exactly 100%. The table is internally consistent; the prose summary sentence is just wrong. That's a one-line question back to your finance lead, not an engineering judgment call — don't let anyone guess at it.

 The schema conflict is real and correctly flagged. fund_scores (confirmed in both models/reference.py and Docs/PRDs/Database-Schema-Unifolio.md:235) stores exactly scheme_id, computed_at, risk_adjusted_tier, cost_adjustment, final_score — nothing else. scorer.py's own docstring even says the FR-7 breakdown "is never persisted" today, by design, for the 3-component version. Storing 11 component percentiles, per-component availability, effective weight, confidence status, peer count, methodology version isn't a tweak to that table — it needs new columns/tables. AGENTS.md line 19 does say the schema is "exact and final," so per CLAUDE.md's own working-style rule ("when a PRD, ADR, or the schema seems to conflict with what you're about to build, stop and say so") — this is precisely that situation, correctly identified. Good catch on Codex's part.
- Current scorer confirmed: 45/30/25 weights, TER ±0.25 nudge with a 0.05pp dead zone, blend-then-rerank-then-add-TER, tier via equal 80/60/40/20 bands, clamp 0–100 — matches your stated understanding and scorer.py:44-77 exactly.
- Benchmark coverage confirmed thin: benchmark.py:201-221 — literally only 4 indices exist, everything that isn't Large/Mid/Large&Mid falls back to Nifty 500. Debt, hybrid, gold, international, sectoral all get a broad-equity-index proxy today. Down-capture/up-capture/Information Ratio need a real category-appropriate benchmark, so this is a genuine gap, not overstated.
- Precompute-and-store architecture recommendation isn't Codex inventing new design — it's actually already the documented intent. Database-Schema-Unifolio.md:235-240 explicitly says portfolio-level scores are "an AUM-weighted roll-up computed on read from a member's holdings plus this [fund_scores] table, not separately stored." The current on-demand-with-15-min-cache scorer is already a shortcut relative to spec; scorer v2 moving to scheduled precompute is bringing the system closer to its own documented design, not a new architectural risk.

Where I'd push back or add nuance

1. Not all 14 "decisions needed" are equally blocking. A few (exact rolling horizons, monthly/weekly/daily sampling, category-average definition, PE/PB combination formula, benchmark-per-category mapping, provisional-fund component eligibility) genuinely need your finance lead's sign-off — don't let engineering guess financial policy. But others are silent in the doc precisely because the doc doesn't intend to change them — e.g. tier bands and "is the result re-ranked again": the approved doc never mentions tiers at all, which most plausibly means "keep whatever tier presentation exists" rather than "this is undefined." I'd bucket the 14 into true policy blockers (~6-7) vs. defaults we propose and get a one-line yes/no on (~6-7), so this doesn't stall on a 14-item RFC before any code gets written.
2. PRD-04 itself is already stale against the live scorer, independent of v2: FR-5a specifies unequal tier bands (10/22.5/35/22.5/10%), but scorer.py implements equal 20-point bands. That's pre-existing drift Codex didn't flag. Worth knowing going in — PRD-04 needs a real rewrite for v2, not a patch, since even its v1 description doesn't match v1's code today.
3. Codex's phased order is sound, and I'd keep it, with one change: move "freeze the calculation annex" and "data-source feasibility spike for PE/PB" to run in parallel, not sequentially — the PE/PB source question is the actual critical path per Codex's own analysis, so don't wait on all 14 formula questions before starting to find out if PE/PB data is even obtainable at reasonable cost/latency. If it isn't, that reshapes the annex questions too (e.g. whether valuation ships gated-unavailable at launch).

How I'd set this up

Agreed on a dedicated branch, not a worktree, since you want to test it interactively yourself rather than have it run headless. Base it off feat/enhanced-ui, not main — main is 410 commits behind and doesn't have the peer-universe/NAV-cache/benchmark/TER infrastructure v2 depends on. I'll create feat/scorer-v2 off feat/enhanced-ui now.

For the build itself, this still fits the model-orchestration skill's Claude/Codex split and handoff-doc/adversarial-review discipline used for the last two big features (just anchored on a plain branch instead of a worktree) — I'd invoke that when we're ready to actually start dispatching tasks, not before the annex is resolved.


Noted for your notes: Analytics caching layer = Postgres table, not Redis.Call: no Redis. Postgres-as-shared-cache.

Reasoning: every Fargate task already has an RDS Postgres connection — a precomputed-results table there is visible to all replicas for free, refreshed by the same EventBridge-scheduled job mechanism ADR-006 already approved. Redis would mean a new service to provision, secure (VPC/security-group work), pay for, and keep available — for a workload (analytics recompute) that's read-heavy, tolerates minutes-to-a-day of staleness (NAV itself only updates once a day), and isn't latency-sensitive at the millisecond level Redis exists for. Postgres reads on an indexed precomputed-results table will be single-digit milliseconds either way — nowhere near the bottleneck the current bug actually is (which is expensive computation, not cache-read latency). Add Redis later only if a real, measured latency problem shows up that Postgres can't solve — not preemptively.

Next question: for the precomputed data itself, what should trigger a recompute — pick whichever fits, or tell me if it's a mix:

A. Time-based only (EventBridge daily job, matching the NAV refresh cadence) — analytics can be up to ~24h stale.
B. Event-based (recompute triggered right after a CAS import / new transaction for that household, so their own numbers are always fresh) plus a daily job as backstop for market-driven changes (NAV moves even with no new transactions).
C. On-demand with dedup (first request after data goes stale triggers a background recompute, cached for next time) — no data changes until someone actually looks.

Here are the pros/cons, then my pick.

A. Time-based only (daily EventBridge job)
- Pros: simplest, predictable cost, one full recompute a day, matches the NAV refresh cadence already decided in ADR-006, zero risk of recompute storms.
- Cons: freshness gap — a user who just imports a CAS statement or adds a transaction sees stale/empty analytics for up to a day. Bad first impression right when someone's most likely to be watching closely (onboarding). Also no answer for a brand-new household with nothing computed yet until the next scheduled run.

B. Event-based (recompute after CAS import/transaction) + daily backstop
- Pros: a user's own changes show up in analytics almost immediately; daily job still catches market-driven drift (NAV moves, category peer-universe changes) that no transaction triggers.
- Cons: more moving parts — needs an event trigger at the end of import/transaction-write, plus debouncing so importing 5 folios back-to-back doesn't fire 5 full recomputes.

C. On-demand with dedup (lazy, on first stale request)
- Pros: zero wasted work for inactive households — nothing computes until someone actually looks.
- Cons: if done naively, this reintroduces the exact bug we just fixed — the first viewer after staleness still pays the multi-minute compute cost synchronously. Only safe as "stale-while-revalidate" (serve old cached data instantly, refresh in the background) — never as a blocking compute-on-request.

My call: layer B as the primary mechanism, A as the backstop, and keep one narrow piece of C as a bootstrap fallback — not "run all three as independent triggers," but:

1. Every dashboard/analytics read is always a fast Postgres read of precomputed rows — never a live compute. This alone is what makes "move between dashboards easily" true, and it's also what kills the original bug: reads are now cheap, so duplicate/abandoned requests from rapid tab-switching stop compounding into connection-pool exhaustion.
2. Event-triggered background recompute after CAS import / new transactions (B) — fires async, doesn't block the import response, gives near-immediate freshness for a user's own changes.
3. Daily EventBridge job as backstop (A) — catches NAV/market drift with no transaction involved.
4. Bootstrap fallback (the one useful piece of C): if a household has literally never been computed (brand new), the read endpoint fires an async compute and returns a "still computing" status instead of hanging — not a general on-demand path, just the cold-start case.

Noted for your notes: B (event-triggered) + A (daily backstop) + reads always served from precomputed Postgres, with an async "still computing" bootstrap for brand-new households.

Picking back up on the architectural clarifying questions — starting with the one the Option 5 mockup just exposed, since it affects the data model underneath everything else.

Precompute granularity: one row per household+scope, or one row per section?

AnalyticsView fetches 7 sections independently today (allocation, TER, TER direct/regular, category-ranking, score, benchmark, benchmark/funds), and Option 5 just committed us to showing each section the moment its own data is ready. That only works if the precompute store can answer "is allocation ready?" separately from "is category-ranking ready?" — which means:

- (A) Per-section rows — 7 separate precomputed rows per household/member scope (one per analytics section). Recompute can finish and publish the fast sections (allocation, TER) independently of the slow one (category-ranking/score), and the frontend can show real per-card data as soon as each row lands — Option 5 works exactly as mocked up.
- (B) One bundled row per scope — a single JSON blob with all 7 sections' results, written atomically once the whole computation finishes. Simpler to write and reason about, but the whole card grid would flip from "computing" to "done" all at once — Option 5's per-card staggered reveal wouldn't actually happen; it'd look more like Option 4 (one block) in practice.

Given you approved Option 5's per-card behavior, I'd lean (A) per-section rows — but it's a real complexity trade-off (7x the rows, 7x the recompute-completion bookkeeping) so I want your call before it becomes the foundation everything else builds on. Which do you want?

Next question, building directly on that.

Scope granularity: which combinations get their own precomputed rows?

AnalyticsView supports both "Family Combined" and "Per Member" views. With per-section rows now decided, each section needs a row per scope too. For a household with, say, 3 members, that's:

- (A) Every scope, always precomputed — 1 combined-household row + 1 row per member, × 7 sections = 28 rows per household, all kept fresh by the same recompute triggers (CAS import, daily backstop). Switching between "Family Combined" and any member's view is always an instant cached read, no exceptions.
- (B) Combined household precomputed always; per-member computed lazily on first view — only the aggregate is proactively kept warm; a specific member's analytics gets computed (and cached) the first time anyone actually opens that member's view, then stays warm via the same recompute triggers after that. Cuts the background recompute workload for households where some members are rarely checked individually, at the cost of a "still computing" moment the first time you ever open a given member's tab.

Given the whole point of this rebuild is eliminating "still computing" surprises during navigation, I lean (A) — precompute everything proactively, since recompute cost is the thing EventBridge/background jobs exist to absorb off the request path anyway. But (A) does mean real, ongoing compute cost that scales with household size × member count, so I want to check that's an acceptable trade-off before locking it in. Which do you want?

Here's the cost breakdown, and it's better than the naive "35 rows = 35x work" read suggests, because the expensive part isn't per-row.

The 7 sections split into two cost tiers:
- Cheap (allocation, TER, TER direct/regular, benchmark, benchmark/funds): pure aggregation/XIRR math over data already in Postgres (holdings, transactions, NAV history already cached). Milliseconds to low-single-digit seconds even summed across all 35 rows.
- Expensive (category-ranking, score): this is the one that was root-causing the original bug — it requires NAV history for the entire SEBI category peer universe of every scheme held (30-150+ schemes per category), fetched over the network if not already cached. Your own log evidence showed this taking 38-73s fetch + 44-74s commit for ~1150 schemes.

The key fact that makes Option A cheap: that expensive NAV-warm step is keyed by distinct scheme/category, not by scope. A household of 4 members holds some bounded set of distinct schemes (realistically 10-40 across a family), spanning some bounded set of SEBI categories (realistically 5-15). Warming NAV for the union of those categories once per household recompute pass, then computing category-ranking/score for all 5 scopes (combined + 4 members) off that same warm cache, means the expensive part is paid once per household per recompute, not once per member. The 35-row fan-out on top of it is cheap local arithmetic.

So the real cost of Option A ≈ the cost of today's single slowest request (the peer-universe NAV warm), done once in the background instead of live on the request path — plus a rounding error of extra arithmetic for the other 34 rows. This has to be an explicit implementation constraint, though, not something that happens automatically: the precompute job must compute the household's full scheme/category union upfront and warm once, then fan out — not naively loop "for each scope, run today's existing per-scope compute function," which would actually multiply the expensive part by 5×.

With that constraint stated as a hard requirement in the design, I'm confident Option A's cost is acceptable at your stated household-size cap (owner + 3 members). Confirm and I'll log it and move to the next question?

Logged. Next question.

Prefetch-on-load: when does Analytics data actually get fetched while the user is still on the Main Dashboard?

Since reads are now cheap Postgres reads (not live compute), prefetching is low-risk — but timing still matters:

- (A) Immediately on Dashboard mount, in parallel with Dashboard's own data — fires all 5×7 scope/section reads the instant Dashboard loads, racing Dashboard's own fetches for connections/bandwidth. Fastest possible Analytics tab-switch, but competes with the view the user is actually looking at.
- (B) After Dashboard's own data has finished loading — Dashboard fetches resolve first, then Analytics prefetch fires in the background while the user reads the Dashboard. Slightly delays prefetch completion, but never contends with what's currently on-screen.
- (C) On hover/focus intent — only prefetch when the user's cursor hits the Analytics tab (or on a short idle timer), not unconditionally on every Dashboard visit. Cheapest in aggregate request volume, but the "instant" tab-switch guarantee weakens for fast/decisive clickers.

Given the reads are now cheap precomputed-row lookups (not the expensive live compute that caused the original bug), I'd lean (B) — sequenced after Dashboard's own load so it never competes with the primary view, with no real downside since a few hundred ms of extra delay before prefetch starts is invisible against how long a user typically dwells on the Dashboard before switching tabs. Which do you want?

Recompute-trigger debounce: how long do we wait after a CAS import/transaction before firing the background recompute?

CAS imports typically insert a batch of transactions at once, and a user might re-import or add another transaction shortly after. Without debouncing, each transaction/import could fire its own full household recompute (the expensive NAV-warm-once-per-household pass), stacking redundant work if several land close together.

- (A) Short fixed debounce (e.g., 30-60s after the last transaction/import event) — collapses back-to-back imports into one recompute, still finishes well within a session so the user sees fresh data soon after.
- (B) Debounce keyed to import completion, not per-transaction — CAS import is already a single logical event (one job inserting N transactions); trigger recompute once when that job finishes, no debounce needed there at all. Only manual single-transaction entry (if the product supports adding one transaction by hand) needs a short debounce (e.g., 10-15s) to absorb a user adding several transactions in quick succession.
- (C) No debounce — always fire immediately, rely on recompute being idempotent/cheap and let overlapping recomputes just race — simplest to implement, but risks the same "stack up expensive work" pattern the original bug came from if a user imports multiple CAS files back to back.

I'd lean (B) — CAS import already batches everything into one job, so debouncing there solves nothing real; the actual risk is manual entry or rapid repeat imports, which a short debounce on the transaction-mutation event (not the import job itself) handles cleanly. Which do you want?

No worries — here's what "debounce" means in plain terms, then I'll make the call.

The plain-language version: "recompute" means re-running the expensive background calculation for a household after something changes (like a new CAS import). "Debounce" just means: wait a little before reacting, and if the same thing happens again during that wait, only react once at the end — like an elevator that waits a few seconds with the doors open in case one more person is walking up, instead of closing and reopening for each person individually.

The risk we're avoiding: if you import two CAS files back-to-back, and each import immediately triggers its own full recompute, you'd pay the expensive cost (the multi-minute NAV-warm-once-per-household pass) twice in a row for no benefit — the second recompute makes the first one's result stale before anyone even saw it. Debouncing means: wait a short pause after the last change, then recompute once, using all the changes together.

Why I'm ruling out "wait a bit" for the CAS import itself: a CAS import is already one single, complete event — the import job reads the whole statement and inserts all its transactions in one shot, then it's done. There's nothing to "wait for more of" within that one import — it's already atomic. So debouncing that specific trigger buys nothing.

Where debouncing actually matters: if you import a second CAS file two minutes after the first, or (if the product ever lets you add a transaction by hand) add several transactions in a row — those are genuinely separate events close together in time, and that's where a short wait-and-collapse makes sense.

My call: Option B — recompute fires once when a CAS import job finishes (no debounce needed, it's already one event), and a short debounce (~15s) sits on manual transaction edits specifically, so several quick manual edits collapse into one recompute instead of one each. Logging this and moving to the next question.

Next one — I'll keep it simple since it's really just "what do we need to remember about each row so the frontend knows what to show."

Freshness signal: per-row status, or one flag per household?

The frontend needs to distinguish three situations per the UX we already locked in: "I have fresh data, show it normally," "I have data but it's a bit stale and being refreshed right now, show the dimmed-pill state (Option 3)," and "I have no data at all yet, show the per-card spinner (Option 5)."

Given the recompute job already works at the household level (warm-once, fan out to all 35 rows together), the natural fit is: one small "is this household currently recomputing?" flag (household_id + started_at), separate from the 35 data rows — plus each data row just carries a plain computed_at timestamp. The frontend logic becomes simple: no row → cold start (Option 5); row exists + household flag says "recomputing" → Option 3's dimmed/pill state; row exists + no active recompute → normal. This avoids putting a status column on all 35 rows individually when the thing that's actually "in progress" or "not" is the household's recompute job, not each row separately.

That's the option I'd go with — one household-level in-flight flag + a timestamp on each row, rather than a per-row status enum. Locking it in and moving to the next question unless you want to weigh in.

Last of the remaining clarifying questions.

Failure handling: what happens if a section's background recompute fails?

This can genuinely happen — e.g. mfapi.in (the NAV data source) is down or slow when the daily job or an import-triggered recompute runs, and the peer-universe NAV warm partially fails for some schemes.

In plain terms: the background job tries to calculate one of the 35 rows, hits an error partway through, and now has to decide what to leave behind for the frontend to read.

- (A) Keep serving the last-known-good row, silently retry the failed section on the next trigger — the user never sees an error at all; worst case they see slightly older data a bit longer than expected. Matches the existing degrade-gracefully posture already in nav.py (a scheme whose fetch fails is just left unwarmed, best-effort, same pattern used everywhere else in that module).
- (B) Mark that section's row as "failed" and show an explicit error state in that card — more honest about a real problem, but surfaces a plumbing failure (a third-party API being flaky) as a user-facing error for something that's genuinely not the user's fault and will very likely resolve itself on the next scheduled retry.

Given the codebase's existing convention (best-effort, keep last-known-good, retry silently — this is the same posture warm_nav_history and get_nav_on_or_before already use today) and that showing a scary error for a transient upstream flakiness isn't useful to the user, I'd go with (A). Locking it in unless you want to weigh in.



All nine clarifying decisions are locked. Here are 2-3 named approaches for how it all actually gets built.

Approach 1 (recommended): Consolidated read + ECS Fargate RunTask recompute

Read side: Collapse today's 7 per-scope HTTP requests into 1 request per scope (GET /analytics/{scope}), returning all 7 sections' precomputed rows plus the household's recomputing-flag in one payload. It's a single indexed Postgres query, not 7 round trips — and it's a natural fit for Option 5's per-card reveal, since the frontend just renders whichever rows are present in that one response instead of tracking 7 independent client-side loading states.

Recompute side: One function, recompute_household_analytics(household_id) — warms NAV once across the household's full scheme/category union, then fans out to write all 35 rows, setting/clearing the household in-flight flag around itself. This one function gets called from three places: the daily EventBridge → ECS Fargate RunTask backstop (the exact pattern already approved and in use for the AMFI/NSE jobs), a FastAPI background task fired right after CAS import completes or the manual-edit debounce elapses, and once, async, on a household's very first-ever read (the bootstrap case).

Trade-off: Zero new infrastructure — no queue, no worker fleet, nothing outside what ADR-005/006 already approved. The one soft spot: the event-triggered path runs inline on a web-serving Fargate replica rather than an isolated worker, so it borrows some CPU from request-serving capacity during a recompute — acceptable given the per-household cost is bounded to roughly "one NAV-warm pass," as established earlier.

Approach 2: Queue-backed recompute via a Postgres jobs table

Same consolidated read API as Approach 1. But instead of triggers firing the recompute inline, they just insert a row into a recompute_jobs table; a separate always-on worker claims and processes pending jobs. This decouples "requested" from "executed" and gives duplicate-request collapsing for free (a second CAS import can just no-op if a pending job already exists).

Trade-off: More moving parts than Approach 1 for a benefit we don't currently need — the debouncing already handles duplicate-request collapsing at the trigger level, so the queue's main advantage is redundant here. It also requires a new always-on ECS service, which isn't a deployment pattern ADR-005/006 currently cover, so it's a bigger infra ask for no corresponding win.

Approach 3: Minimal-diff — keep today's 7 endpoints, just make them read precomputed rows

Leaves the read API untouched (7 separate endpoints), each swapped internally to read a precomputed row instead of computing live. Recompute orchestration same as Approach 1.

Trade-off: Smallest frontend diff (AnalyticsView.tsx's existing fetch structure barely changes). But it keeps the exact 7-concurrent-requests-per-view shape that was part of the original bug's blast radius — harmless now that reads are cheap, but still 7x the HTTP overhead for nothing, and pushes more complexity onto the frontend (7 independent loading states instead of iterating one response) to reproduce Option 5's per-card behavior.

My recommendation: Approach 1. It fixes the actual bug (fewer, cheaper requests instead of 7 concurrent ones), needs no new infrastructure beyond what's already approved, and the consolidated response is the natural data shape for the per-card UX we already locked in. Approach 3 is a reasonable fallback if you want the smallest possible frontend diff, but I don't think it's worth carrying 7x the request volume forward once we're touching this code anyway.

Which one do you want to go with?

CPU isn't actually the number to worry about here — the real answer changes the design, so let me walk through both.

How much CPU does a recompute pass actually use?

warm_nav_history's cost (the 38-73s fetch + 44-74s commit logged in the original bug) is almost entirely I/O wait — network round-trips to mfapi.in and DB commit latency — not CPU-bound computation. Actual CPU-seconds consumed during that window is small; the process spends most of that time blocked, not computing. So in isolation, "how many more vCPUs" is the wrong question — a recompute pass doesn't burn meaningful CPU.

The real risk isn't CPU — it's the event loop freeze you already have logged

Your session.md "still open" item 7 already documents this exact mechanism: a blocking sync db.commit() inside an async def (which is what warm_nav_history does) freezes FastAPI's entire single-worker event loop for the full duration of that commit — not just the request that triggered it. Every other concurrent request hitting that same Fargate replica stalls too, regardless of how much CPU headroom the task has. That's not "borrowing some capacity," that's "this replica serves zero requests for up to a minute."

If Approach 1's event-triggered recompute runs as an inline FastAPI background task on a request-serving replica (what I proposed), it inherits this exact bug on every recompute. That's a real problem, not a rounding
                                                                                                                                                          Revised recommendation: never run recompute inline on a reques
                                                                                                                                                          Route both the daily backstop and the event-triggered recomputate RunTask — the same ADR-006 pattern already approved andrunning for the AMFI/NSE jobs, just triggered on-demand (via EventBridge PutEvents or a direct RunTask call from the request-serving app) instead of only on a schedule. This is a short-lived task: it spins up, does te, writes the 35 rows, and exits.
                                                                                                                                                 This sidesteps the question entirely rather than accepting a t
- Zero CPU contention with request-serving replicas — it's a completely separate task.                                                           - Zero event-loop-freeze risk on the app tier — the blocking ctask, not inside a process handling live traffic.
- No new infrastructure pattern — you already run this exact mechanism today.                                                                    
Cost, roughly: a 0.5 vCPU / 1GB task running ~1-2 minutes for one household's recompute, at Fargate's ~$0.04-0.05/vCPU-hour (us-east-1 baseline, Mumbai/ap-south-1 typically 10-30% higher — I couldn't confirmhe official pricing page doesn't expose it via search), landsaround $0.0005-0.001 per recompute run. Even at a few hundred recomputes a day across your whole user base, that's cents, not dollars. Not a real cost
concern at your stage — worth re-checking once you're at a scasomething to design around now.

This is a change to Approach 1 as I described it earlier — log

Section 1: Architecture Overview

Read path. Frontend calls one endpoint per scope — GET /analytics/{household_id}/{scope} where scope is household or a specific member_id. It's a single indexed Postgres query returning all 7 precomputed sections for that scope in one payload, plus the household's recomputing flag. No live computation ever happens on this path.

Write path. One function, recompute_household_analytics(household_id), is the sole writer. It:
1. Sets the household's recomputing flag.
2. Computes the union of schemes/categories held anywhere in the household, and does the NAV/peer-universe warm once for that union (the expensive leg).
3. Fans out cheap local arithmetic across all 5 scopes × 7 sections, upserting each of the 35 rows with a fresh computed_at as it finishes (not all-at-once — this is what lets the frontend's per-card reveal work).
4. Clears the recomputing flag.

This function never runs inline inside a request-serving process. It only ever runs inside a dedicated, short-lived ECS Fargate RunTask invocation — reusing the exact ADR-006 mechanism already running for the AMFI/NSE reference-data jobs, just invoked on-demand instead of only on a schedule. Three triggers dispatch it:
- CAS import completion (event-triggered, no debounce — import is already one atomic job).
- Manual transaction edit (event-triggered, ~15s debounce, once that flow exists).
- Daily EventBridge Scheduler (backstop, for NAV/market drift with no user activity).

A 4th path — a household's very first-ever read, before any row exists — triggers the same RunTask asynchronously and the frontend shows Option 5 (per-card progressive reveal) until rows land.

Why this shape: it fully separates "serve fast reads" from "do expensive background work," using only infrastructure ADR-005/006 already approved — no new service, no queue, no Redis. The Fargate-RunTask-only rule (never inline on a web replica) is what closes off the event-loop-freeze risk from the "still open" item 7 bug, discussed last turn.

Does this overall shape look right before I go into components (the DB schema for the 35 rows, the recompute function's internals, the read endpoint) and data flow next?

Good question to pin down before going further — and digging into it surfaced a real gap in the current code that changes how I'd build this, not just what it costs. Let me walk through both.

What actually drives cost

Finding: NAV data is already a global cache, not a per-household one. I checked nav.py — nav_history is keyed by scheme_id only, shared across every household on the platform. So the truly expensive leg (network fetch to mfapi.in) is bounded by total distinct schemes across the whole platform, not by household count. India has roughly 2,500-3,000 total MF schemes in existence; realistically only a few hundred will ever be actually held by your user base. That number doesn't grow meaningfully as you add households — it grows (slowly) as you add scheme diversity, which saturates fast. This is the single biggest reason cost stays flat as you scale.

But there's a bug in the current caching that the new architecture would otherwise inherit and make worse. warm_nav_history's "don't re-fetch what's already fresh" check (_NAV_WARM_TTL_SECONDS) lives in a process-local Python dict, not in the database. That's fine today because the FastAPI server is one long-running process. It breaks the moment recompute runs as short-lived Fargate RunTasks — every task starts as a brand-new process with an empty cache, so it will unconditionally re-fetch full NAV history over the network for every scheme it touches, even if another task fetched the same scheme 30 seconds ago and it's sitting fresh in Postgres. Left as-is, a busy day of CAS imports would hammer mfapi.in with redundant fetches for the same handful of popular schemes, over and over.

Fix, which I'm folding into the design: make the "is this scheme fresh enough" check consult the DB (nav_history's latest row + a freshness window) instead of the in-process dict. This also changes Section 1 slightly — the daily backstop should be one RunTask that loops every household in a single process run, not one task per household, so the in-process warm cache is actually useful for the run it's in. Event-triggered recomputes (CAS import, manual edit) stay one task per event, but with the DB-backed freshness check, they'll mostly find their schemes already warm from the daily run or a sibling household's recent import, and skip the network fetch entirely.

Rough numbers

- Fargate compute: daily backstop, one task (~0.5-1 vCPU / 1-2GB) doing one platform-wide NAV warm (a few hundred schemes, seconds to ~1 min per the logged fetch rates) + fanning arithmetic across every household's 35 rows — even at thousands of households this is a single-digit-minutes run. At Fargate's ~$0.04-0.05/vCPU-hr baseline, that's well under $1/month. Event-triggered tasks are short (mostly cache hits after the fix above) and bounded by actual user activity, not household count — also sub-dollar/month at any MVP-to-early-growth scale.
- RDS writes: 35 rows/household per recompute, cheap batched upserts — noise next to your existing DB costs.
- Networking (NAT Gateway), unconfirmed: if these Fargate tasks run in a private subnet needing outbound internet to reach mfapi.in, a NAT Gateway's flat ~$32-35/month hourly charge would actually dwarf everything above — it'd be the real cost driver, not compute. I couldn't find this decided anywhere in the ADRs (checked ADR-005/006 and grepped /Docs for NAT/subnet — nothing), and since you haven't deployed to AWS yet, there's no existing setup to point to either. This needs to be resolved once when you set up the VPC (a public-subnet task with a public IP avoids it entirely, if your security posture allows it) — it applies equally to the already-approved AMFI/NSE jobs, so it's not new scope created by this design, just an open item worth deciding once for all of ADR-006's jobs together.

Bottom line: the precompute feature itself is a rounding error in AWS cost — under $1-2/month in compute/DB at realistic scale, thanks to the global-NAV-cache finding. The one real cost risk (NAT Gateway) is pre-existing to ADR-006, not created by this design, and worth flagging to whoever's doing your VPC setup rather than solving here.


Section 2: Components

New table analytics_sections — the 35-row-per-household precompute store. Primary key (user_id, scope_key, section):
- user_id — the household (matches the existing convention in aggregate.py, where "household" is always just user_id, never a separate household entity).
- scope_key: str — "combined" for the household-aggregate row, or the member's UUID as text otherwise. I'm using a plain string discriminator rather than a nullable household_member_id in the primary key, because Postgres treats each NULL as distinct for uniqueness purposes — a nullable PK column would let every recompute insert a new "combined" row instead of updating the existing one via ON CONFLICT. A separate nullable household_member_id FK column (not part of the PK) stays alongside it for cascade-delete when a member is removed.
- section: str — one of the 7: allocation, ter, ter_direct_regular, benchmark, benchmark_funds, category_ranking, score.
- payload: JSONB — the exact response body today's corresponding endpoint returns (same Pydantic shape), so the read endpoint can hand it back as-is with zero reshaping.
- computed_at: DateTime(timezone=True).

New table analytics_recompute_status — one row per user_id, just started_at: DateTime | NULL. Non-null means "a recompute is currently running for this household" (decision 8's single household-level flag, not a per-row enum).

recompute_household_analytics(db, user_id) (app/services/analytics/recompute.py) — the sole writer, called only from inside an ECS RunTask, never from a request-serving process:
1. Sets analytics_recompute_status.started_at.
2. Loads every scheme/category held anywhere across the household's members, calls warm_nav_history once for that union.
3. For each of the 5 scopes × 7 sections, runs today's existing compute function (allocation.py, ter.py, etc. — unchanged, they're already correct) and upserts the row into analytics_sections, computed_at = now() — one section's write lands as soon as that section's compute finishes, not batched at the end, so Option 5's per-card reveal has something to show early.
4. Clears started_at.

get_nav_on_or_before / warm_nav_history freshness fix — swap the process-local _nav_warm_cache TTL check for a query against nav_history's latest row per scheme (the DB-backed fix from Section 1's revision). Same file, same function signatures — internal change only, nothing else in the codebase that calls these needs to change.

Read endpoint — GET /analytics/{scope} (scope = "combined" or a member UUID), replacing the 14 existing per-section/per-scope GETs. One analytics_sections query filtered by user_id + scope_key, plus one analytics_recompute_status lookup, assembled into a single response keyed by section name.

Trigger wiring — confirm_import (service.py:137, where ImportStatus.CONFIRMED is set) gets one line dispatching the RunTask after its existing commit. The manual-edit debounce (once that flow exists) and the daily EventBridge backstop both call the same dispatch path.

Does this component breakdown look right, or should any of these pieces be shaped differently before I move to data flow?

Section 3: Data Flow

Cold start (brand-new household, no rows yet). User finishes onboarding/first CAS import → confirm_import dispatches a RunTask → frontend's first GET /analytics/combined finds zero rows and no analytics_recompute_status entry yet (or one that just started) → renders Option 5, one ring-spinner per section card. Frontend polls the same endpoint every few seconds; each poll picks up whichever sections have landed since recompute_household_analytics writes them incrementally, so cards fill in one by one rather than all at once. Polling stops once all 7 sections have a row.

Steady state, existing data. Dashboard loads first (its own existing fetch path, unchanged). Once that resolves, the frontend prefetches GET /analytics/{scope} for the scopes it's likely to need (decision 6, Option B) — cheap reads, real data, no spinners. Tab-switching between household/member views is now just re-rendering already-fetched or trivially-fetched cached rows — no live compute ever sits on this path, which is what eliminates the original pool-exhaustion bug at the root.

Background refresh (returning visit, recompute in flight). A trigger fires (import, edit, or the daily backstop) while the user is looking at Analytics with existing data on screen. analytics_recompute_status.started_at goes non-null. The next read the frontend does picks that up and switches to Option 3 — dimmed last-known values plus the "Updating with latest data…" pill — while recompute_household_analytics overwrites rows underneath. Each section flips back to normal the moment its own row's computed_at moves past when the pill first appeared; no full-page reload, no flash of blank state, since the old row is never deleted before the new one lands (ON CONFLICT DO UPDATE, not delete-then-insert).

Daily backstop. EventBridge Scheduler fires once daily → one RunTask loops every household in a single process (Section 1's batching revision) → each household's 35 rows refresh in place, same upsert path as any other trigger. From the frontend's perspective this is indistinguishable from any other background refresh — same started_at flag, same Option 3 treatment for anyone looking at Analytics when their household's turn comes up in the loop.

Section 3: Data Flow

Cold start (brand-new household, no rows yet). User finishes onboarding/first CAS import → confirm_import dispatches a RunTask → frontend's first GET /analytics/combined finds zero rows and no analytics_recompute_status entry yet (or one that just started) → renders Option 5, one ring-spinner per section card. Frontend polls the same endpoint every few seconds; each poll picks up whichever sections have landed since recompute_household_analytics writes them incrementally, so cards fill in one by one rather than all at once. Polling stops once all 7 sections have a row.

Steady state, existing data. Dashboard loads first (its own existing fetch path, unchanged). Once that resolves, the frontend prefetches GET /analytics/{scope} for the scopes it's likely to need (decision 6, Option B) — cheap reads, real data, no spinners. Tab-switching between household/member views is now just re-rendering already-fetched or trivially-fetched cached rows — no live compute ever sits on this path, which is what eliminates the original pool-exhaustion bug at the root.

Background refresh (returning visit, recompute in flight). A trigger fires (import, edit, or the daily backstop) while the user is looking at Analytics with existing data on screen. analytics_recompute_status.started_at goes non-null. The next read the frontend does picks that up and switches to Option 3 — dimmed last-known values plus the "Updating with latest data…" pill — while recompute_household_analytics overwrites rows underneath. Each section flips back to normal the moment its own row's computed_at moves past when the pill first appeared; no full-page reload, no flash of blank state, since the old row is never deleted before the new one lands (ON CONFLICT DO UPDATE, not delete-then-insert).

Daily backstop. EventBridge Scheduler fires once daily → one RunTask loops every household in a single process (Section 1's batching revision) → each household's 35 rows refresh in place, same upsert path as any other trigger. From the frontend's perspective this is indistinguishable from any other background refresh — same started_at flag, same Option 3 treatment for anyone looking at Analytics when their household's turn comes up in the loop.

Does this flow look right before error handling?

Section 4: Error Handling

A single section's compute fails (e.g., benchmark's NSE index fetch times out) inside recompute_household_analytics. Per decision 9, the function doesn't fail the whole run — it logs, leaves that section's existing row untouched (stale computed_at, still valid data), and moves on to the next section. The household's started_at flag still clears normally once the loop finishes, so the frontend drops back to normal display for every section that did succeed; only the failed section keeps showing its last-known value with no error banner, no retry button. The next trigger (next CAS import, or tomorrow's backstop) retries it silently — same posture nav.py already uses for a single scheme's failed fetch.

The whole RunTask fails or is killed (OOM, Fargate capacity transient, unhandled exception before the loop starts). Nothing is corrupted — no in-progress row was ever partially written — but started_at is left non-null forever, which would wrongly pin every affected household in the dimmed/pill state indefinitely. Fix: recompute_household_analytics wraps its body in try/finally so started_at clears even on an unhandled exception; belt-and-suspenders, the daily backstop's own trigger path also treats any started_at older than a generous ceiling (e.g. 2 hours — far beyond any real run's length) as stale and clears it before starting a fresh run, so a truly wedged flag can't outlive one more day's backstop even if the finally somehow doesn't run (process killed with SIGKILL, not a catchable exception).

A trigger fires while a recompute for that household is already running (e.g., two CAS imports in quick succession, or an import landing mid-backstop). The dispatch call is a no-op if analytics_recompute_status.started_at is already non-null for that user_id — the in-flight run will pick up whatever's latest by the time it queries each section's source data, so a second dispatch adds no value, only a redundant RunTask launch. This is the same collapsing behavior the debounce (decision 7) gives manual edits, just extended to overlapping triggers generally rather than only rapid-fire ones.

GET /analytics/{scope} for a household with zero rows and no recompute in flight — the narrow bootstrap case from decision 2(d): the read endpoint dispatches the RunTask itself (same no-op-if-already-running guard) before returning an empty response, so the frontend's cold-start view always has something moving toward completion rather than a dead end requiring a page refresh.

Does this look right before testing strategy?


Fair — passive-only retry means a user staring at one stale card has to just wait. Revised:

A single section's compute fails. Same as before — logs, leaves the existing row's data on screen untouched, no full-page error. But now the row also gets a failed_at timestamp (small addition to analytics_sections: nullable failed_at: datetime, cleared on the next successful compute of that row). The frontend uses that to show a small inline "Retry" affordance on that one card instead of nothing.

Retry button's behavior: it doesn't need a new compute path — it just calls the same household-level dispatch used by every other trigger (CAS import, edit, backstop), which is already guarded to no-op if a recompute is already running for that household. So clicking Retry either kicks off a fresh full recompute (cheap — NAV is likely already warm from the failed attempt or the daily run, only the failed leg actually redoes real work) or, if one's already in flight, does nothing and the card just switches to the normal "recompute in progress" pill instead. No new backend endpoint beyond a thin POST /analytics/{scope}/retry that calls the existing dispatch function — no separate single-section-only recompute mechanism, which would need to fight the warm-once/fan-out design for a marginal win.

I'll fold this into decision 9 and the schema note.

Section 5: Testing Strategy

recompute_household_analytics (tests/services/analytics/test_recompute.py, new): the core of the new behavior, so it gets the most coverage — a household with 2+ members produces all 35 rows with correct scope_keys; NAV warming happens exactly once for the union of held schemes, not once per scope (the thing decision 4's whole cost argument depends on — worth a test that literally asserts warm_nav_history is called once, not 5 times); a section that raises leaves its existing row untouched and sets failed_at; a fresh run clears a stale failed_at on success; the started_at flag sets at the start and clears in finally even when a section raises mid-loop.

DB-backed NAV freshness fix (tests/services/dashboard/test_nav.py, extends existing): a scheme already fresh in nav_history isn't re-fetched even from a cold process (empty _nav_warm_cache) — this is the regression test for the exact bug found in Section 1; existing tests there already cover the old TTL-cache behavior and need updating to the DB-backed check.

Read endpoint (tests/api/test_analytics_route.py, replaces the 7 route test files above): returns exactly what's in analytics_sections for the given scope with no live compute (assert the underlying compute functions are never called on this path); zero rows + no started_at triggers a dispatch and still returns a well-formed empty response; started_at set surfaces in the response so the frontend can render Option 3.

Retry endpoint (new, small): no-ops (200, no new dispatch) when a recompute is already in flight; dispatches when it isn't.

Trigger wiring (tests/services/import_/test_service.py, extends existing): confirm_import dispatches exactly once per confirmation; a second import for the same household while one's still running doesn't double-dispatch.

Explicitly not testing: the actual EventBridge Scheduler/RunTask AWS wiring itself — that's infra configuration (Terraform/CDK, whatever ADR-006's jobs already use), verified by deploying it, not by a unit test. Same treatment the existing AMFI/NSE jobs already get.