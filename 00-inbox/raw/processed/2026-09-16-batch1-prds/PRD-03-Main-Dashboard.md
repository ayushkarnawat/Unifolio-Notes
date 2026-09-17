---
artifact: prd
version: "1.3"
created: 2026-07-22
updated: 2026-07-22
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
| US-7 | As an investor who bought the same fund through different distributors, I want to compare how each distributor relationship has performed | P1 — unblocked, see Dependencies |
| US-8 | As an investor, I want a monthly snapshot of my portfolio value (e.g., "what was I worth at the end of April") | P1 |
| US-9 | As an investor, I want to add a new or updated CAS statement any time after my initial setup, without redoing onboarding | P0 |

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
- **New:** An "Add data" entry point on the dashboard (per member or per family) that
  launches PRD-01's import flow at any time post-onboarding — this is the dashboard-side
  half of PRD-01's Ongoing Data Addition requirement. Foundational for v1: a clear,
  reachable entry point and a straightforward re-run of the existing import flow, not a
  reimagined multi-import management UI — that can grow later without changing the
  underlying approach.
- Distributor comparison view — **now unblocked for v1**. The comparison math (a
  user's own returns split by which ARN/folio a holding was bought through) only needs
  the ARN code, which PRD-01 already captures — it doesn't need a resolved distributor
  *name* to function. AMFI's public "Locate a Mutual Fund Distributor" tool resolves an
  ARN code to a registered name/address/status on demand. See Solution Design for the
  approach and Dependencies for the one remaining (non-blocking) item.

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
- FR-10a: An "Add data" action is reachable from both the family aggregate view and
  each per-member view, launching PRD-01's import flow scoped to that member (or, from
  the aggregate, prompting which member first) — this covers both a placeholder member
  uploading their first CAS and an existing member adding an updated/additional
  statement, using the same flow and dedupe logic either way.

#### Distributor Comparison (unblocked)
- FR-11: For a scheme held via multiple folios/distributors, show a comparison of the
  user's own returns by distributor. The comparison itself runs on ARN code alone
  (already captured per PRD-01) — no external dependency required to compute it.
- FR-11a: Display name resolution — when a new, previously-unseen ARN code appears in
  a user's imported data, look it up against AMFI's public "Locate a Mutual Fund
  Distributor" tool (amfiindia.com) to resolve the registered distributor name, and cache
  the result in a small internal `arn_directory` table (`arn_code → name, status`) so it's
  looked up once per ARN ever encountered platform-wide, not once per user.
- FR-11b: If a lookup hasn't resolved yet (first time an ARN is seen, or the lookup fails),
  show the raw ARN code as the label rather than blocking the comparison view — the
  feature is never gated on name resolution succeeding.
- FR-11c: Where AMFI's suspended/invalid-ARN lists show a distributor's ARN is no longer
  valid, surface that as a small trust signal next to the comparison (e.g., a flag noting the
  ARN is no longer active) — low-effort, high-relevance addition given the data is already
  public and structured.

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
| SIP stopped (no `PURCHASE_SIP` within the active window) | Drops out of "active SIPs" list automatically, no manual state to maintain |

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
| AMFI Locate-Distributor lookup mechanism (FR-11a) | Claude (technical) | Public tool confirmed to exist; exact automation approach (API-style call vs. lightweight scraping of the public search page) not yet implemented — low-risk since it's a single-item lookup on a small, slow-growing set of ARNs, not bulk scraping | Non-blocking — FR-11b's raw-ARN fallback means the feature ships either way |
| Family data model from PRD-02 | N/A (upstream PRD) | Structure decided, not yet reconciled with dashboard needs | FR-9/FR-10 need this settled first |

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| "Today's gain" is misleading before evening NAV publication (common in Indian markets — NAVs typically post end-of-day) | High | Medium | FR-3's explicit dated-fallback labeling |
| Monthly snapshot backfill (FR-8) undercounts for schemes where `mfapi.in` lacks full historical NAV coverage (rare, but possible for very old or merged schemes) | Low | Low | Show snapshot as unavailable for that specific month/scheme rather than guessing |
| Distributor comparison (FR-11) shows unresolved raw ARN codes for a while if name-lookup automation lags behind build | Medium | Low | FR-11b's graceful fallback — feature ships and is useful even before every ARN has a resolved name |
| AMFI's Terms of Use may restrict automated querying of the Locate-Distributor tool at any meaningful volume | Low (single-item lookups on a small ARN set, not bulk scraping) | Low–Medium if it becomes an issue | Quick compliance check before implementing FR-11a; worst case, fall back permanently to FR-11b's raw-ARN display, which still delivers the comparison feature |

## Timeline & Milestones

| Milestone | Description | Target Date |
|-----------|--------------|--------------|
| Holdings table + allocation summary | FR-1–FR-4 | TBD |
| SIP + cash flow views | FR-5–FR-7 | TBD |
| Monthly snapshot | FR-8 | TBD |
| Family aggregate + drill-down | FR-9–FR-10 | TBD |
| Distributor comparison | FR-11–FR-11c, in scope for v1 | TBD, same window as other P1 items |

## Open Questions

- [ ] Exact SIP "active" window threshold (FR-6 proposes ~35–40 days as a starting point)
      — Owner: Ayush
- [ ] Confirm AMFI's Terms of Use permit automated single-item ARN lookups (not bulk
      scraping) for FR-11a — quick compliance check, not expected to block the build given
      FR-11b's fallback — Owner: Ayush (legal/ToS review) / Claude (implementation)
- [x] ~~Should the family aggregate view be the default landing screen, or does it land on
      the primary user's own holdings with family as a switch?~~ **Resolved** (via the App
      Flow document): family aggregate is the default landing for returning users who
      have family members set up; per-member view remains default for users without
      family set up. Affects FR-9's default state as specified.

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
| 1.1 | 2026-07-22 | Claude (PM partner) | Distributor comparison (FR-11) unblocked for v1 — research found AMFI's public ARN-lookup tool resolves distributor names on demand; comparison math itself only needs the ARN code already captured in PRD-01. Added FR-11a–c (lookup + cache, graceful fallback, suspended/invalid-ARN trust signal). Updated US-7 to P1, Dependencies, Risks, Timeline, Open Questions accordingly. |
| 1.2 | 2026-07-22 | Claude (PM partner) | Added "Add data" entry point (FR-10a, US-9) — ongoing CAS import is a first-class dashboard capability, not onboarding-only, matching PRD-01's Ongoing Data Addition scope addition |
| 1.3 | 2026-07-22 | Claude (PM partner) | Resolved default-landing-screen open question (family aggregate default when family exists) via the App Flow document |
