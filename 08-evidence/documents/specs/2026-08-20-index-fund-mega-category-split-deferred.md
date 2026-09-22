# Index-fund mega-category split — investigated, deferred (2026-08-20)

## Status: **Deferred, not built.** Reviewed with Ayush + finance-domain peers; decision was not to build this now. Kept here so it isn't re-investigated from scratch if revisited later.

## Problem

AMFI's SEBI-recategorization taxonomy (`NAVAll.txt`) puts **1,150 schemes** under one
category, `"Other Scheme - Index Funds"` — by far the largest single category in the
feed. `category_ranking.py`/`scorer.py` run bulk NAV/series queries against the *entire*
category universe for every held scheme in that category (bounded per-category by the
BUG-001 fix's 15-min cache, but still 1,150+ schemes worth of work per cache refresh,
vs. ~50-150 for a properly-scoped sub-bucket). Splitting the category into smaller
peer-groups would improve both load time for anyone holding index funds and
comparison quality (ranking a Nifty Bank index fund against 1,150 unrelated index
funds, including debt index funds, is not a meaningful peer comparison).

No such split exists anywhere in the codebase or in PRD-04 today — PRD-04's only
category-size guidance is the opposite concern (FR-4's thin-category flagging), and its
Open Questions section has zero mention of category-size caps or benchmark heuristics.
`scheme_universe.py`'s `get_category_universe(db, sebi_category)` does an exact-string
filter on `sebi_category`; any sub-bucketing would be a pure computed function layered
on top, used only internally by `category_ranking.py`/`scorer.py`'s cache-key and
peer-universe-narrowing logic — no schema change, and `Scheme.sebi_category` plus every
user-facing category label (including the Allocation dashboard breakdown) would stay
untouched, still showing the true SEBI category.

## Option A — fine-grained, per-benchmark buckets (regex on scheme name)

Computed from the real 1,150 scheme names in the cached `NAVAll.txt` (not hypothetical):

| Bucket | Count | Sample |
|---|---:|---|
| Debt/Bond/SDL/CPSE index | 219 | Aditya Birla SL Crisil IBX 60:40 SDL+AAA PSU Apr 2026 |
| Gilt/G-Sec/target-maturity | 173 | Aditya Birla SL Crisil IBX 50:50 Gilt+SDL Apr 2028 |
| Sectoral/thematic index | 124 | Axis Nifty IT Index Fund |
| Nifty 50 family | 103 | Aditya Birla SL Nifty 50 Index Fund |
| Nifty 500 family | 72 | Axis Nifty 500 / Nifty500 Momentum 50 |
| Nifty Midcap 150 | 54 | Bandhan Nifty Midcap 150 |
| Nifty 200 | 50 | Bandhan Nifty 200 Quality 30 |
| Smart-beta factor (Alpha/Momentum/Quality/Value) | 48 | Bandhan Nifty Alpha 50 |
| Nifty Next 50 | 48 | Axis Nifty Next 50 |
| BSE Sensex | 45 | Axis BSE Sensex |
| Nifty 100 | 40 | Axis Nifty 100 |
| Nifty Smallcap 250 | 38 | Bandhan Nifty Smallcap 250 |
| Nifty Bank | 24 | Axis Nifty Bank |
| Nifty LargeMidcap 250 | 19 | Edelweiss Nifty Large Midcap 250 |
| Nifty Midcap 50 / Smallcap 50 | 16 | Axis Nifty Midcap 50 / Smallcap 50 |
| International (Nasdaq/S&P/Hang Seng) | 6 | ICICI Pru Nasdaq 100 |
| BSE 100/200/500/1000 | 4 | HDFC BSE 500, Motilal Oswal BSE 1000 |
| **Catch-all (unmatched)** | **67** | Angel One Nifty Total Market, Axis BSE India Sector Leaders |

18 buckets, largest 219 (debt index), catch-all a clean 5.8% of the category — a real
perf win (1,150 → ~50-220 per bucket). But every bucket boundary is a heuristic
invented for this codebase, on regex over free text, most-specific-pattern-first (e.g.
"Nifty 200 Quality 30" must not fall into a bare "Nifty 200" bucket before a more
specific smart-beta rule gets a chance) — real mis-bucketing risk, and ongoing
maintenance every time a new index family launches (happens roughly monthly right now —
see the SDL/target-maturity debt series alone, which is really a family of dated
maturity products, not one index).

## Option B — coarse, AMFI-precedented split (asset class only)

AMFI's own `NAVAll.txt` already carries a **separate, parallel taxonomy** for index
funds, independent of the SEBI-recategorization `"Other Scheme - Index Funds"` bucket:

| AMFI header (as-is, no regex) | Count |
|---|---:|
| Index Funds - Equity Funds | 133 |
| Index Funds - Debt Funds | 43 |
| Index Funds - Hybrid Fund | 4 |
| (current SEBI bucket, unsplit) Other Scheme - Index Funds | 1,150 |

3-way split, nothing invented — it's AMFI's own recognized category label. But it
doesn't solve the actual problem: these legacy-header rows and the 1,150
"Other Scheme" rows are mostly-non-overlapping AMFI feed rows, not the same schemes
counted twice, so an Equity Index bucket built this way would still be several hundred
schemes by extrapolation, and Debt/Hybrid don't map back cleanly onto the mega-category
either. **There is no split that is both AMFI-native and actually shrinks
"Other Scheme - Index Funds" to a non-mega size** — that is the real finding here, not
a compromise that was missed.

## Side finding (separate from this decision, worth flagging)

`scheme_universe.py`'s `get_category_universe` does an exact-string match on
`sebi_category`. Any live scheme tagged with one of the three legacy
`"Index Funds - Equity/Debt/Hybrid Funds"` headers (Option B's table) is therefore
currently invisible to comparison against schemes tagged `"Other Scheme - Index Funds"`,
even when they track the identical index — a possible pre-existing data-completeness
gap, independent of whether the mega-category split above is ever built. Not confirmed
as high-impact (depends on whether any currently-held scheme's `sebi_category` value
actually uses one of the legacy strings) and not investigated further as part of this
pass — flagged for whoever next touches category-ranking/comparison coverage.

## Decision

Presented both options above, with real counts, to Ayush for review with finance-domain
peers. Peer feedback: building a bespoke, AMFI-unrecognized index taxonomy (Option A)
is not a good idea for a product whose credibility depends on category comparisons
being trustworthy — and Option B doesn't actually fix the mega-category problem.
**Decision: don't build this now.** Tracked in `DEFERRED_FEATURES.md`'s PRD-04 table.

## Revisit trigger

Only reconsider this if category-ranking/Scorer load time for index-fund holders
becomes a demonstrated user-facing problem — it's currently mitigated (not solved) by
the existing 15-min per-category cache from the BUG-001 fix
(`category_ranking.py`'s `_bulk_nav_on_or_before`). If revisited, this doc's Option A
bucket list and Option B counts don't need to be recomputed from scratch — re-verify
against the then-current `NAVAll.txt` (index families are added roughly monthly) rather
than assuming these exact counts still hold.
