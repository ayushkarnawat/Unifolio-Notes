---
artifact: prd
version: "1.0"
created: 2026-07-22
status: draft
product: Unifolio
module: Main Dashboard
---

# PRD: Main Dashboard (Mutual Fund Holdings View)

## Overview

### Problem Statement

Once a user has imported their CAS (PRD-01) and completed onboarding (PRD-02), they
need a single home screen that answers "what do I actually own, and how is it doing?"
without clicking into every fund individually. This is the screen every competitor in the
11-player set converges on — Mprofit included — because it's the load-bearing screen of
any portfolio tracker: get it wrong and nothing else in the product matters.

This PRD deliberately follows the proven functional pattern already validated by Mprofit
and the broader competitive set (holdings table + allocation + SIPs + gains), rather than
inventing new information architecture. The differentiation opportunities specific to
Unifolio — direct-vs-regular visibility, distributor comparison, a genuinely unique visual
treatment — layer on top of that proven base rather than replacing it.

### Solution Summary

A single-screen (per-member, with a family aggregate view) dashboard showing every
mutual fund holding with valuation, gain/loss, and allocation, plus SIP status, investment
cash flow, and (where data allows) direct-vs-regular and distributor context. Deep
analytical breakdowns (sector/category/AMC allocation, overlap, scoring, benchmark
comparison) are explicitly **not** this screen's job — see Scope.

### Target Users

Same as the platform overall: retail DIY investors and HNI/affluent users, individually or
viewing a family's aggregated holdings, per the family structure established in
onboarding.

## Goals & Success Metrics

### Goals

1. One screen answers "what do I own and how is it doing" with no clicking required for
   the core numbers.
2. Every figure shown is traceable back to parsed CAS data — no silent estimates.
3. Family and per-member views both work from the same underlying data without
   separate code paths.

### Success Metrics

| Metric | Current Baseline | Target | Timeline |
|--------|-------------------|--------|----------|
| Dashboard load time (holdings visible) | Not built | Under 2 seconds for a typical portfolio (≤50 holdings) | Before MVP close |
| Gain/loss figures match hand-verified calculation | Not built | 100% match against known-answer test portfolios (see Open Questions carried from PRD-01 on what "100%" means) | Before MVP close |
| Holdings with resolved Direct/Regular status visible | Depends on PRD-01 classification work | Matches PRD-01's classification-accuracy target | Before MVP close |

### Non-Goals

- Sector, category, and AMC-level allocation breakdowns, fund overlap detection, fund/
  portfolio scoring, category-average comparison, and benchmark/XIRR-vs-index
  comparison are **explicitly the MF Analytics Dashboard's job**, not this screen's. This
  boundary is stated here so the two PRDs don't duplicate or contradict each other.
- Equity-holdings-via-mutual-fund look-through (which stocks a fund actually holds) is
  not committed in this version — see Future Considerations; it needs a data source we
  don't currently have.
- Real bank-account cash flow integration is out of scope — the cash flow shown here is
  **investment cash flow only**, derived entirely from already-parsed CAS transactions
  (purchases as outflow, redemptions/dividends as inflow), not a bank feed.

## User Stories

| ID | User Story | Priority |
|----|-----------|----------|
| US-1 | As an investor, I want to see every fund I hold with current value and gain/loss at a glance | P0 |
| US-2 | As an investor, I want to know today's change, not just all-time gain, so I know what happened recently | P0 |
| US-3 | As an investor, I want to see my active SIPs and when they run | P0 |
| US-4 | As an investor, I want to know which of my holdings are Direct vs Regular plans right where I'm looking at them, not buried in a settings screen | P0 |
| US-5 | As an investor with family members set up, I want a combined view and the ability to drill into one person's holdings | P0 |
| US-6 | As an investor, I want to see the cash that's moved in and out of my mutual fund investments over time | P1 |
| US-7 | As an investor who bought the same fund through different distributors, I want to compare how each distributor relationship has performed | P2 — blocked, see Dependencies |
| US-8 | As an investor, I want a monthly snapshot of my portfolio value (e.g., "what was I worth at the end of April") | P1 |

## Scope

### In Scope

- Holdings table: fund name, average NAV (cost basis), units held, current NAV, amount
  invested, current value, current profit (total), realized gain, unrealized gain, today's
  gain, Direct/Regular badge, last-updated date.
- Top-level allocation summary (asset class and/or AMC split — high-level only; see
  Non-Goals for what's deferred to Analytics).
- Active SIP list: fund name, SIP date, SIP amount.
- Investment cash flow view (debit/credit derived from parsed transactions).
- Monthly portfolio value snapshots (e.g., month-end closing value history).
- Family aggregate view + per-member drill-down, built on the family data model from
  PRD-02.
- Distributor comparison view — **included as a requirement, but explicitly gated**: it
  cannot ship until the ARN-to-distributor-identity data source question (open since
  PRD-01) is resolved. This PRD specifies the requirement now so it isn't forgotten, not
  because it's unblocked.

### Out of Scope

- Everything listed under Non-Goals above (deep analytics — separate PRD).
- Equity look-through holdings (data source not yet identified).
- Bank account integration.
- Visual/interaction design specifics — this PRD defines what the screen must show and
  compute; how it looks and feels is the Design Brief and Design Schema's job, following
  the same proven-pattern baseline (Mprofit + the 11-competitor set) referenced above.

### Future Considerations

- Equity-holdings-via-MF look-through — needs a constituent-holdings data source per
  scheme, which isn't part of CAS parsing or the current `mfapi.in` enrichment. Worth
  researching (AMFI/AMC factsheet data, third-party APIs) once the core dashboard ships.
- Distributor analytics — unblocks once the ARN-mapping data source is resolved (see
  Dependencies).

## Solution Design

### Functional Requirements

#### Holdings Table
- FR-1: Every holding shows: fund name, average NAV, units held, current NAV, amount
  invested, current value, current profit, realized gain, unrealized gain, today's gain, and
  a last-updated date.
- FR-2: Direct/Regular badge shown inline per holding, reusing the classification and
  `unclassified` fallback logic already specified in PRD-01 (FR-5/FR-6) — no new
  classification logic here, just surfacing what PRD-01 already computes.
- FR-3: "Today's gain" requires same-day NAV; if the current trading day's NAV isn't yet
  published (common before evening AMFI updates), show the most recent available NAV
  with its date clearly labeled rather than a stale number presented as current.

#### Allocation Summary
- FR-4: Show a top-level allocation split (asset class and/or AMC) — intentionally shallow.
  Anything sector/category-level belongs to the Analytics Dashboard PRD, not here.

#### SIP Visualization
- FR-5: List active SIPs detected from the transaction pattern (recurring `PURCHASE_SIP`
  entries at a consistent interval/amount per PRD-01's transaction taxonomy) — fund
  name, SIP date, SIP amount.
- FR-6: An "active" SIP is one with a `PURCHASE_SIP` transaction within the last ~35–40
  days (covers monthly cadence plus a grace window) — exact threshold needs your
  input, flagged in Open Questions.
  **Superseded 2026-08-18** (explicit product experiment, not a silent
  resolution — see `Docs/superpowers/specs/2026-08-18-active-sips-cadence-redesign-design.md`):
  the 40-day cutoff has been removed. A SIP stays "active" indefinitely once
  detected (excluding fully-redeemed folios), with a server-computed rolling
  `next_due_date` projection and no "missed SIP" messaging. If this doesn't
  hold up in use, FR-6's original 40-day window is the documented fallback.

#### Investment Cash Flow
- FR-7: Cash flow view computed entirely from existing parsed transactions — no new
  data source. Purchases/SIP debits as outflow, redemptions and dividend payouts as
  inflow. This is a computed view, not an integration.

#### Monthly Value Snapshots
- FR-8: Month-end portfolio value can be **backfilled historically**, not just tracked going
  forward — `mfapi.in` provides full historical NAV per scheme, so a month-end snapshot
  is computable as (units held as of that date, from the transaction ledger) × (that
  scheme's NAV on that date). This removes what would otherwise be a hard dependency
  on having been live since the start of the user's investing history.

#### Family View
- FR-9: Family aggregate view sums holdings across all members with imported CAS data;
  per-member drill-down shows that member's holdings table alone, same components as
  FR-1–FR-3.
- FR-10: A family member who hasn't yet uploaded their CAS shows as a clear placeholder
  in the aggregate (not silently excluded, not an error state) — consistent with PRD-02's
  onboarding handling of the same case.

#### Distributor Comparison (gated)
- FR-11: For a scheme held via multiple folios/distributors, show a comparison of
  performance by distributor (ARN-linked). **This requirement cannot be built until the
  ARN-to-distributor-identity mapping data source is resolved** (open since PRD-01) — it's
  specified here so scope isn't lost, not as a committed v1 deliverable.

### User Experience

This PRD defines the data and functional requirements above; visual layout, information
density, and interaction design follow the proven pattern already established across
Mprofit and the broader competitive set, refined through the upcoming Design Brief and
Design Schema work — that level of detail isn't specified here.

### Edge Cases

| Scenario | Expected Behavior |
|----------|--------------------|
| NAV not yet published for the current day | Show most recent available NAV, clearly dated, not presented as "today's" figure |
| Holding has `unclassified` Direct/Regular status from PRD-01 | Badge shows "unverified" per PRD-01's FR-10-equivalent handling, not silently defaulted to one or the other |
| Family member added but no CAS uploaded yet | Placeholder in aggregate view, not excluded or errored |
| Monthly snapshot requested for a month before the user's first transaction | No data point shown for that month, not a zero or an error |
| Scheme redeemed in full (zero units held) | Moves out of active holdings but remains in cash-flow and historical snapshot views |
| SIP stopped (no `PURCHASE_SIP` within the active window) | **Superseded 2026-08-18** — no longer applies; a SIP stays active indefinitely once detected (see FR-6 note above), only dropping out if its folio is fully redeemed |

## Technical Considerations

### Constraints
- Reuses PRD-01's data model directly (Direct/Regular classification, transaction
  taxonomy, ARN capture) — no duplicate classification logic on the dashboard side.
- `Decimal` math throughout, consistent with PRD-01's constraint — no floating-point
  drift in aggregated family-level totals.

### Integration Points
- `mfapi.in` — both current NAV (for today's gain) and historical NAV (for monthly
  snapshot backfill, FR-8).
- PRD-01's parsed transaction ledger — sole source for cash flow (FR-7) and SIP detection
  (FR-5/FR-6); no separate data entry.

### Data Requirements
- No new raw data beyond what PRD-01 already parses and stores; this PRD is primarily a
  computation/presentation layer over that data, with one new requirement: a materialized
  or on-demand monthly snapshot value (FR-8) — implementation (stored vs. computed
  on-the-fly) is an engineering call, not specified here.

## Dependencies & Risks

### Dependencies

| Dependency | Owner | Status | Impact if Delayed |
|------------|-------|--------|--------------------|
| PRD-01's Direct/Regular classification and ARN capture | N/A (upstream PRD) | In progress per PRD-01 | Badge (FR-2) and distributor comparison (FR-11) both depend on this |
| ARN-to-distributor-identity data source | Unresolved since PRD-01 | Open | FR-11 stays unbuilt/gated until resolved |
| Family data model from PRD-02 | N/A (upstream PRD) | Structure decided, not yet reconciled with dashboard needs | FR-9/FR-10 need this settled first |

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| "Today's gain" is misleading before evening NAV publication (common in Indian markets — NAVs typically post end-of-day) | High | Medium | FR-3's explicit dated-fallback labeling |
| Monthly snapshot backfill (FR-8) undercounts for schemes where `mfapi.in` lacks full historical NAV coverage (rare, but possible for very old or merged schemes) | Low | Low | Show snapshot as unavailable for that specific month/scheme rather than guessing |
| Distributor comparison (FR-11) becomes a permanent "coming soon" if the ARN-mapping data source question never gets resolved | Medium | Low (feature is P2) | Revisit as a dedicated research spike separate from this PRD's build |

## Timeline & Milestones

| Milestone | Description | Target Date |
|-----------|--------------|--------------|
| Holdings table + allocation summary | FR-1–FR-4 | TBD |
| SIP + cash flow views | FR-5–FR-7 | TBD |
| Monthly snapshot | FR-8 | TBD |
| Family aggregate + drill-down | FR-9–FR-10 | TBD |
| Distributor comparison | FR-11 — gated on external dependency | TBD, likely post-MVP |

## Open Questions

- [ ] Exact SIP "active" window threshold (FR-6 proposes ~35–40 days as a starting point)
      — Owner: Ayush
    
    Answer - Lets keep it like ~35–40 days as a starting point

- [ ] ARN-to-distributor-identity data source — carried over from PRD-01, now blocking
      FR-11 specifically — Owner: Ayush (research) / Claude (technical feasibility)

      Sharing My rsearch for the same and lets make this added here

- [ ] Should the family aggregate view be the default landing screen, or does it land on
      the primary user's own holdings with family as a switch? Functional decision, not a
      visual one — affects FR-9's default state — Owner: Ayush

      family aggregate view be the default landing screen



## Appendix

### Related Documents
- PRD-01: CAS Parser v2 — source of all holdings, transaction, and classification data
- PRD-02: Signup & Onboarding — source of the family/household data model
- Combined Feature-Parity Matrix (project knowledge) — competitive baseline for this
  screen's functional pattern
- Mprofit Case Study (project knowledge) — closest direct functional precedent

### Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-07-22 | Claude (PM partner) | Initial draft |
