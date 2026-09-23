# TRI Benchmark — Deferred Implementation Plan

**Status:** Deferred. Decided 2026-08-19 (round 2 of the Analytics Dashboard Internal
Correction Plan cross-reference — see `Docs/orchestration/analytics-correction-plan-status.md`'s
P0.3 entry for the underlying investigation this plan responds to).

## What's shipped instead, right now

`frontend/src/features/analytics/BenchmarkSection.tsx`'s `INDEX_LABELS` map now appends
`" (Price Return)"` to all 4 benchmark index labels (e.g. "Nifty 50" → "Nifty 50 (Price
Return)"). No backend or data-sourcing change. This is a disclosure fix, not a correctness
fix — it makes the benchmark comparison honest about what it actually is today, rather than
silently implying total-return comparability it can't currently back up.

## Why this was deferred rather than fixed properly

The correction plan's P0.3 requirement is that the benchmark identifier and series type be
explicitly recorded and a "TRI" designation displayed with the name, on the premise that a
fund's own XIRR (computed from real cash flows against NAV, which *does* reflect
distributions/dividends via reinvestment or lot accounting) should be compared against a
benchmark that likewise reflects reinvested distributions — a plain price index that excludes
dividends is not a fair like-for-like comparison.

Two separate things would be needed to actually fix this, and neither is confirmed feasible
today:

1. **Does NSE's endpoint this codebase already uses even serve a TRI series?**
   `nse_indices_client.py`'s `_TRADING_INDEX_NAME` map points at
   `https://www.niftyindices.com/BackPage/getHistoricaldatatabletoString` with plain index
   names ("Nifty 50", "Nifty 500", "NIFTY LARGEMID250", "Nifty Midcap 150") — confirmed via
   live requests during the original Item 5 build (see that file's own module docstring).
   Nobody has checked whether this same endpoint accepts a TRI-variant name (NSE does publish
   TRI series for some indices, e.g. "Nifty 50 TRI", under index names that may or may not be
   queryable through this exact undocumented endpoint) or whether TRI access requires NSE's
   paid/licensed data products instead.
2. **What does the endpoint actually return today?** Separately from the naming question,
   nothing in this codebase inspects the retrieved `CLOSE` values against independently-known
   TRI/price-index figures to confirm which series NSE is serving under the current plain
   names — this was flagged and deliberately left unconfirmed during the P0.3 investigation
   (see the status doc's P0.3 entry: "narrower claim" correction after an earlier draft
   overclaimed "confirmed price-only" without a value-level check).

Per CLAUDE.md's MVP-scoping principle ("don't gold-plate... build what's scoped, don't build
what isn't scoped yet"), sourcing a new data feed on a speculative "TRI might be reachable
through this endpoint" basis — before confirming it's reachable at all — is exactly the kind
of premature infra investment this project explicitly avoids. The labeling fix is the
proportionate response until the sourcing question has an answer.

## What a real fix requires, when picked up

In order, so a future session doesn't have to re-derive this:

1. **Confirm reachability.** Live-probe `niftyindices.com`'s endpoint (and/or check NSE's
   published `IndexMapping.json` / index-name list, referenced but not fetched by the current
   client per its own "no need to fetch IndexMapping.json at runtime" comment) for a
   TRI-variant name per benchmark index (e.g. "Nifty 50 TRI"). If the same
   `getHistoricaldatatabletoString` path accepts it and returns real historical values, that's
   the cheapest possible path — no new client, just a second `_TRADING_INDEX_NAME`-style map.
2. **If not reachable for free:** identify whether NSE Indices' paid data products, or a
   third-party aggregator, expose TRI series — this is a genuine sourcing/cost decision for
   the product owner, not an engineering one, and should stop here pending that decision.
3. **Confirm the response's economic content**, not just its name — spot-check a handful of
   returned values for a known index/date against an independently published TRI or price
   figure (Value Research, moneycontrol, or NSE's own factsheets typically publish both) to
   verify the endpoint is actually returning what its name claims, closing the second
   unconfirmed question above at the same time.
4. **Schema/API change:** `IndexXirrRow`/`FundBenchmarkRow` (`analytics/schemas.py`) would need
   a series-type field (e.g. `series_type: Literal["price_return", "total_return"]`) so the
   frontend can render the correct label from data instead of a hardcoded string suffix —
   replacing this round's static `" (Price Return)"` label with a real, response-driven one.
   This also gives a path to mixed states (e.g. TRI available for Nifty 50/500 but not for
   the two narrower indices) without an all-or-nothing switch.
5. **Re-verify `_benchmark_xirr_for_transactions`'s replay logic is series-agnostic** — it
   already just divides amount by whatever index level it's given (`benchmark.py` lines
   93-98), so switching the underlying series to TRI values should require no changes there;
   confirm this holds once real TRI data is in hand rather than assuming it.

## Revisit trigger

Re-open this when either: (a) the product owner decides TRI comparability is worth a paid
data source, or (b) a free/already-licensed TRI feed is identified independently of this
investigation (e.g. during unrelated data-sourcing work). Not time-boxed otherwise — this is
a scope/cost question, not a ready-to-schedule engineering task.
