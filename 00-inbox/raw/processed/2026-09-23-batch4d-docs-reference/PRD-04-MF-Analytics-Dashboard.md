---
artifact: prd
version: "1.0"
created: 2026-07-22
status: draft
product: Unifolio
module: MF Analytics Dashboard
---

# PRD: MF Analytics Dashboard

## Overview

### Problem Statement

The Main Dashboard (PRD-03) answers "what do I own and how is it doing." This screen
answers the harder question: "is what I own actually any good, and what am I paying for
it?" — category/AMC allocation, fund and portfolio scoring, benchmark comparison, and
cost transparency (TER). This is the analytical depth that separates a tracker from a
spreadsheet, and it's also where data availability varies sharply feature-to-feature — this
PRD is explicit about which pieces are buildable now versus genuinely data-gated, based
on a research pass into what's actually publicly available (below), rather than assuming
everything is equally reachable.

### Solution Summary

A dedicated analytics screen (per member and family-aggregate, same pattern as the
Main Dashboard) covering: category and AMC-level allocation, SEBI-category fund
ranking, a fund/portfolio scorer, category-average comparison, benchmark comparison
(portfolio XIRR vs. Nifty 50/500/LargeMidcap 250/Midcap 150), and AUM-weighted TER.
Two features from the original brief — true cap-wise (large/mid/small) composition
*within* a fund and stock-level fund overlap — require data Unifolio doesn't have a
source for yet and are scoped as a dependency-gated fast-follow, not a v1 commitment.

### Target Users

Same as the platform overall — this screen matters most to users who've moved past
"what do I own" into "should I keep owning it," which likely skews toward more engaged
DIY investors and HNI users comparing their own picks against benchmarks.

## Goals & Success Metrics

### Goals

1. Give a fund-by-fund and portfolio-level verdict on cost (TER) and performance
   (vs. category and vs. benchmark) without requiring the user to look anything up
   externally.
2. Be explicit, in the product itself, about which numbers are exact and which are
   estimates — never present a number with false precision.
3. Ship what's genuinely buildable now; don't let the two data-gated features (cap-wise
   composition, overlap) hold up everything else.

### Success Metrics

| Metric | Current Baseline | Target | Timeline |
|--------|-------------------|--------|----------|
| Category-average comparison coverage | Not built | Available for every scheme with a resolvable SEBI category tag (expected ≥95% of schemes typically held) | Before MVP close |
| Benchmark/XIRR comparison accuracy | Not built | Matches hand-verified test cases exactly (same accuracy-definition question as PRD-01/PRD-03) | Before MVP close |
| Weighted portfolio TER coverage | Not built | Available for every scheme with a resolvable AMFI TER record | Before MVP close |
| Cap-wise composition / overlap | Not built | Explicitly deferred — see Scope | Fast-follow, not MVP |

### Non-Goals

- This screen does not give investment advice or recommendations ("sell this fund") —
  it shows comparative data; interpretation stays with the user, consistent with the
  non-regulated-advice posture established in PRD-02.
- Equity-specific analytics (stock-level metrics) are out of scope — MF-only per the
  overall MVP scope.

## User Stories

| ID | User Story | Priority |
|----|-----------|----------|
| US-1 | As an investor, I want to see my portfolio broken down by AMC and by SEBI category | P0 |
| US-2 | As an investor, I want to know how each of my funds ranks against others in its category | P0 |
| US-3 | As an investor, I want a simple score for each fund and my portfolio overall | P1 |
| US-4 | As an investor, I want to compare my fund's returns against its category average | P0 |
| US-5 | As an investor, I want to see my portfolio's XIRR against Nifty 50, 500, LargeMidcap 250, and Midcap 150 | P0 |
| US-6 | As an investor, I want to know the weighted-average cost (TER) I'm paying across my whole portfolio | P0 |
| US-7 | As an investor, I want to know how much of my portfolio is genuinely large-cap vs. mid-cap vs. small-cap, and where my funds overlap in the same stocks | P2 — data-gated, see Scope |

## Scope

### In Scope (v1 — buildable on data confirmed available)

- AMC allocation (what share of the portfolio sits with each fund house) — computable
  from scheme metadata already captured in PRD-01, no new data source needed.
- SEBI category allocation (what share is in Flexicap, Large Cap, Debt, etc.) — same, uses
  the scheme category tag already present in AMFI/`mfapi.in` scheme metadata.
- SEBI-category fund ranking and category-average comparison — computable from NAV
  history across all schemes in a category (via `mfapi.in`, which covers the full scheme
  universe, not just what the user holds).
- Fund and portfolio scorer — a composite metric from return, volatility (NAV-based
  standard deviation), and cost (TER) — see Functional Requirements for the proposed
  formula and its limits.
- Benchmark comparison — portfolio XIRR vs. Nifty 50 / Nifty 500 / Nifty LargeMidcap 250
  / Nifty Midcap 150 XIRR, AUM-weighted across holdings.
- AUM-weighted portfolio TER, sourced from AMFI's published TER disclosures.
- Direct vs. Regular cost visualization at the analytics level (aggregate, complementing
  the per-holding badge already on the Main Dashboard).

### Out of Scope / Data-Gated (not v1)

- **True cap-wise composition within a fund** (how much of this Flexicap fund is actually
  in large-cap vs. mid-cap vs. small-cap stocks) and **stock-level fund overlap** both
  require the fund's underlying portfolio holdings — SEBI mandates AMCs disclose this
  monthly, but there's no single aggregated public feed; each AMC publishes separately
  (varying formats, mostly PDF/Excel factsheets), the same gap already flagged as a
  Future Consideration in PRD-03 for equity look-through. This is a real
  data-engineering project (scrape/aggregate 40+ AMCs' monthly disclosures, or evaluate
  a paid data vendor), not something to build inside this PRD's timeline.
- Deep multi-year rolling-return analysis beyond what's needed for the scorer and
  category comparison (e.g., full rolling-return heatmaps) — possible future enrichment
  once the core scorer ships.

### Future Considerations

- Cap-wise composition and overlap detection — revisit once the portfolio-holdings data
  question (shared with PRD-03's equity look-through gap) is resolved, ideally as a single
  combined data-sourcing effort rather than solving it twice.
- Fund scorer weighting could evolve from the v1 formula (Functional Requirements) into
  something more sophisticated once real usage data exists.

## Solution Design

### Research Summary

A short research pass to confirm what's actually publicly available before committing to
scope, since "100% accuracy" is the stated bar and false confidence here would be worse
than an honest gap:

**TER is publicly available, scheme-wise, from AMFI.** SEBI regulation requires every
AMC to disclose TER daily on both their own site and AMFI's, and AMFI runs a dedicated,
filterable TER report page (by financial year, month, fund type, category, and AMC) at
`amfiindia.com/ter-of-mf-schemes`. The page is filter-driven (client-rendered), so the
exact automation approach (finding the underlying data endpoint vs. driving the filter
UI) is an implementation detail to confirm, not a data-availability question — the data
itself is confirmed to exist and be free.

**Nifty benchmark data is available from NSE Indices.** The four indices in the brief map
to real, named NSE indices: **Nifty 50**, **Nifty 500**, **Nifty LargeMidcap 250**, and
**Nifty Midcap 150** (the "250" and "150" in the original brief refer to these — worth
confirming that mapping is what you intended, flagged in Open Questions). NSE Indices'
own site (niftyindices.com) publishes historical daily closing levels for all of these,
free to access. Benchmark XIRR is then computed the standard way: simulate the same
cash-flow timing and amounts as the user's actual transactions, but priced at the index
level instead of NAV, and compute XIRR on that hypothetical stream — an accepted
method for benchmarking irregular (SIP-style) investment timing against an index.

**Category classification and category-universe returns don't need portfolio
holdings.** This was the key scoping question for this PRD: ranking a fund against its
category, and computing category averages, only needs (a) each scheme's SEBI category
tag — already in AMFI/`mfapi.in` scheme metadata — and (b) NAV history for every
scheme in that category, which `mfapi.in` also covers for the full scheme universe, not
just what a given user holds. **What genuinely isn't available without new
infrastructure is the fund's actual underlying stock composition** — that's the
distinction driving the Scope split above (AMC/category allocation: buildable now;
true cap-wise composition and stock-level overlap: data-gated).

### Functional Requirements

#### Allocation
- FR-1: AMC allocation — % of portfolio value by fund house, computed from existing
  holdings data (no new source).
- FR-2: SEBI category allocation — % of portfolio value by category tag (Large Cap, Flexi
  Cap, Debt, etc.), same data source.

#### Category Ranking & Comparison
- FR-3: For each held scheme, compute its category and rank it against all other schemes
  in that category using a defined return window (e.g., 1yr/3yr/5yr CAGR — exact
  window(s) need your input, see Open Questions).
- FR-4: Category-average comparison — show the held scheme's return against the
  simple or AUM-weighted average of its category (needs your input on which — see
  Open Questions, since AUM-weighting requires category-wide AUM data which may not
  be as readily available as NAV history).

#### Fund & Portfolio Scorer
- FR-5: A composite score per fund, combining: relative return within category, volatility
  (NAV-based standard deviation over a defined window), and cost (TER) — proposed
  starting formula and exact weighting need your sign-off, since this is a genuine product
  opinion, not a neutral calculation (see Open Questions).
- FR-6: Portfolio-level score as an AUM-weighted roll-up of FR-5's per-fund scores.
- FR-7: The scorer must be explained, not just displayed — a short "why this score"
  breakdown per fund, so it doesn't read as an unexplained black-box number (this
  matters especially given the "100% accuracy" bar — a scorer is inherently a modeling
  choice, not a fact, and needs to be presented that way).

#### Benchmark Comparison
- FR-8: Portfolio XIRR computed from the full transaction history (already available from
  PRD-01), alongside XIRR for Nifty 50, Nifty 500, Nifty LargeMidcap 250, and Nifty
  Midcap 150, each computed via the same cash-flow-timing method described in
  Research above.
- FR-9: AUM-weighted view — where the user holds funds benchmarked against different
  indices (e.g., a large-cap fund vs. Nifty 50, a midcap fund vs. Nifty Midcap 150), show
  both the per-fund-appropriate benchmark and the overall portfolio-vs-broad-market
  (Nifty 500) comparison — avoids the common but misleading practice of comparing
  every fund to the same single index regardless of what it actually invests in.

#### Cost (TER)
- FR-10: AUM-weighted portfolio TER, sourced from AMFI's TER disclosure, refreshed on
  whatever cadence AMFI updates it (monthly reference periods per the page's own
  disclaimer — see Research).
- FR-11: Direct vs. Regular cost view — using PRD-01's classification, show the aggregate
  TER difference between the user's Direct and Regular holdings (complements, doesn't
  duplicate, the per-holding badge already on the Main Dashboard).

### User Experience

As with PRD-03, this document specifies what the screen computes and shows, not its
visual layout — that's a Design Brief/Design Schema concern, following the same
established pattern.

### Edge Cases

| Scenario | Expected Behavior |
|----------|--------------------|
| Scheme's SEBI category can't be resolved (rare, but possible for older/merged schemes) | Excluded from category ranking/comparison with a clear "category unavailable" label, not silently dropped |
| TER not yet published for the current reference period | Show most recent available TER with its reference period clearly labeled, same pattern as PRD-03's stale-NAV handling |
| User holds a scheme with insufficient NAV history for the scorer's return window (e.g., a very new fund) | Scorer shows "insufficient history" rather than a misleading score |
| Fund category has very few peer schemes (thin category) | Category average/ranking still shown, but flagged as based on a small sample |

## Technical Considerations

### Constraints
- Same `Decimal` math and accuracy-definition question carried over from PRD-01/PRD-03
  — this PRD doesn't reopen that question, just inherits it (see Open Questions there).
- Category ranking and benchmark computation both require NAV history for schemes
  the user doesn't hold (the full category universe, and index levels) — meaningfully
  different data footprint than PRD-01/PRD-03, which only needed data for the user's
  own holdings.

### Integration Points
- `mfapi.in` — NAV history, now needed for the full category universe, not just held
  schemes (new usage pattern, same data source).
- AMFI TER disclosure page — new integration, automation approach TBD (see Research).
- NSE Indices (niftyindices.com) — new integration for benchmark index history.
- PRD-01's transaction ledger and classification data — reused directly for XIRR and
  Direct/Regular cost comparison, no duplicate logic.

### Data Requirements
- New: category-universe NAV cache (beyond just held schemes), TER-by-scheme table,
  benchmark index history table.

## Dependencies & Risks

### Dependencies

| Dependency | Owner | Status | Impact if Delayed |
|------------|-------|--------|--------------------|
| AMFI TER page automation approach | Claude (technical) | Data source confirmed public; exact scraping/endpoint approach not yet implemented | FR-10/FR-11 blocked until resolved — but data existing (vs. not existing) is the hard part, and that's confirmed |
| NSE Indices historical data automation approach | Claude (technical) | Data source confirmed public (niftyindices.com); exact download/automation mechanism not yet implemented | FR-8/FR-9 blocked until resolved, same category of risk as TER |
| Portfolio-holdings data source (cap-wise composition, overlap) | Unresolved, shared with PRD-03 | Open — recommend a dedicated research/build spike, not folded into this PRD's timeline | US-7 stays deferred until resolved |
| Scorer formula and weighting sign-off (FR-5) | Ayush | Not decided | Blocks FR-5–FR-7 build start |

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| AMFI/NSE Indices sites restrict automated access at any real volume (same category of risk as the ARN lookup in PRD-03) | Low–Medium | Medium | Same posture as PRD-03: confirm ToS for lightweight, infrequent (not bulk-realtime) automated access before building; these are monthly/daily-refresh needs, not high-frequency polling |
| Scorer (FR-5) is inherently a modeling opinion presented next to "100% accuracy" language elsewhere in the product | Medium | Medium | FR-7's explicit "why this score" breakdown — never present the scorer as a neutral fact |
| Category comparison thin for niche categories with few peer schemes | Low | Low | Edge case handling flags small-sample categories |

## Timeline & Milestones

| Milestone | Description | Target Date |
|-----------|--------------|--------------|
| Allocation views (FR-1–FR-2) | No new data source, fastest to ship | TBD |
| Category ranking + comparison (FR-3–FR-4) | Depends on category-universe NAV caching | TBD |
| TER integration (FR-10–FR-11) | Depends on AMFI automation approach | TBD |
| Benchmark comparison (FR-8–FR-9) | Depends on NSE Indices automation approach | TBD |
| Scorer (FR-5–FR-7) | Depends on your sign-off on formula/weighting | TBD |
| Cap-wise composition + overlap | Deferred fast-follow | Post-MVP |

## Open Questions

- [ ] Confirm "Nifty 250" and "Nifty 150" in the original brief map to **Nifty LargeMidcap
      250** and **Nifty Midcap 150** as assumed here — these are the real NSE index names
      that fit — Owner: Ayush
- [ ] Category ranking/comparison return window(s) — 1yr, 3yr, 5yr, or a blend? — Owner: Ayush
- [ ] Category-average comparison: simple average across category schemes, or
      AUM-weighted? AUM-weighting is more representative but needs category-wide AUM
      data, which may be a harder get than NAV history — Owner: Ayush + Claude (feasibility)
- [ ] Scorer formula and weighting (return vs. volatility vs. cost) — this is a product
      opinion, needs your direct input, not just a technical default — Owner: Ayush
- [ ] Should the two data-gated features (cap-wise composition, overlap) get their own
      dedicated research spike now (in parallel with this build) or wait until the rest of
      this PRD ships? — Owner: Ayush

## Appendix

### Related Documents
- PRD-01: CAS Parser v2 — source of holdings, transactions, and classification data
- PRD-03: Main Dashboard — shares the portfolio-holdings data-gap dependency for
  equity look-through; scope boundary between the two dashboards defined there
- Combined Feature-Parity Matrix (project knowledge) — competitive context for which of
  these analytics are differentiators vs. table-stakes

### Research Sources
- AMFI TER disclosure: amfiindia.com/ter-of-mf-schemes (official, confirmed structure)
- NSE Indices historical data: niftyindices.com (official NSE Indices site); Nifty index
  family and constituent structure via Wikipedia (NIFTY 50, NIFTY Next 50, NIFTY 500,
  NSE Indices pages, 2025–2026)
- TER regulatory basis: SEBI (Mutual Funds) Regulations, 1996, Regulation 52; general TER
  explainer sources (Outlook Money, Zerodha Fund House, AMFI's own investor knowledge
  center, 2025–2026)

### Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-07-22 | Claude (PM partner) | Initial draft, includes research pass on data-source feasibility |
