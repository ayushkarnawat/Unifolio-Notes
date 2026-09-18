# Main Dashboard — Backend Design (Phase 3)

## Purpose

PRD-03's Main Dashboard is the first screen answering "what do I own and how
is it doing" — every prior phase (CAS import, auth, onboarding) has been
plumbing leading up to this. This is the backend: FIFO-based holdings
computation, allocation, SIP detection, cash flow, monthly value snapshots,
and family aggregation, all read paths over data Phase 0/1 already parse and
store. The frontend consuming these endpoints (PRD-03's S13-S16, S21-S22
screens) is a separate, follow-up phase (3b), matching the Phase 1/1b and
Phase 2/2b precedent.

## Scope

**In scope:** PRD-03 FR-1 through FR-10a — holdings table, shallow
allocation summary, active-SIP list, investment cash flow, monthly value
snapshots (backfillable), family aggregate + per-member drill-down, and the
data-layer support for an "Add Data" entry point (no new backend work there
— `/imports/parse`/`/imports/confirm` already accept a real
`household_member_id`, per Phase 2b's auth wiring).

**Explicitly out of scope, decided during brainstorming:**
- **Distributor Comparison (FR-11, App-Flow S17)** — P1, separable, pulls in
  an external AMFI ARN-lookup integration with its own risk profile. Builds
  as its own small follow-up phase once this core dashboard ships.
- **Frontend** — Phase 3b, separate spec/plan.
- **Deep analytics** (sector/category allocation, overlap, scoring,
  benchmark comparison) — explicitly PRD-04's job per PRD-03's own
  Non-Goals section.
- **Real scheduled NAV-refresh job** (EventBridge Scheduler + Fargate) — that's
  deployment-phase infrastructure per `CLAUDE.md`'s local-development-first
  non-negotiable. This phase uses on-demand fetch-and-cache instead (see
  below) — the scheduled job replaces it outright once deployment readiness
  is met, not something this phase needs to anticipate further than "the
  cache is keyed the same way regardless of what populates it."

## Resolved Design Decisions (from brainstorming)

1. **NAV data source: on-demand fetch-and-cache.** `nav.py` checks
   `nav_history` first; on a miss (or a stale "today"), fetches
   `mfapi.in`'s `/mf/{amfi_code}` (returns the scheme's full historical NAV
   series in one call — a single fetch typically satisfies both
   current-NAV and historical-snapshot-backfill needs for that scheme) and
   upserts it. Separate client from Import Service's `MfApiClient`, whose
   own docstring already scopes it to scheme *metadata*, not valuation
   history.
2. **Allocation is Dashboard's, not Analytics'.** PRD-03 FR-4 explicitly
   scopes a shallow asset-class/AMC split as this screen's job; the TDD's
   API-surface table listing `/household-members/{id}/allocation` under
   Analytics was a documentation slip, corrected here. Analytics (PRD-04,
   unbuilt) will own a *deeper* sector/category breakdown as a separate,
   more detailed endpoint later — no conflict once corrected.
3. **SIP active window: 40 days.**
4. **Cost-basis methodology: FIFO.** First lot purchased is the first lot
   considered redeemed — matches Indian capital-gains convention and how
   CAMS/KFintech CAS statements themselves report gains, and is more
   precisely traceable to actual purchase lots than a weighted-average
   blend (serving PRD-03's Goal #2: "no silent estimates").

## Architecture

```
backend/app/services/dashboard/
  household_members.py   # existing, unchanged
  schemas.py              # existing, extended with this phase's response models
  nav.py                    # NEW — on-demand NAV fetch-and-cache (mfapi.in /mf/{code})
  holdings.py                 # NEW — FIFO lot engine + per-scheme holding rows
  allocation.py                  # NEW — shallow asset-class/AMC grouping
  sip.py                            # NEW — active-SIP detection (40-day window)
  cash_flow.py                        # NEW — investment cash flow from transactions
  snapshots.py                           # NEW — monthly value backfill/compute
  aggregate.py                              # NEW — placeholder-aware family merging
backend/app/api/dashboard.py                  # extended — 10 new GET routes
```

**One implementation per concern, parameterized by a list of member IDs —
not two code paths for "family" vs "per-member."** PRD-03's Goal #3 is
explicit about this. Every service function in `holdings.py`/`allocation.py`/
`sip.py`/`cash_flow.py`/`snapshots.py` takes
`household_member_ids: list[uuid.UUID]` and merges across however many it's
given. A per-member route calls it with a single-item list; the aggregate
route calls it with every member the authenticated user owns (resolved via
the existing `list_household_members`).

**`aggregate.py` is the one place that's genuinely different between the two
views** — not the computation, but the response shape. FR-10 requires a
family member with zero imports to show as a clear placeholder, not vanish
silently. So every aggregate endpoint's response is
`{members: [{id, name, has_data: bool}], <data>: [...]}` — the frontend
renders a placeholder card for any `has_data: false` member alongside the
real combined data from the rest. Per-member endpoints don't need this
wrapper; they return `<data>` directly, since there's exactly one member and
either they have data or the response is empty (no placeholder ambiguity).

**FIFO engine, the core of this phase (`holdings.py`):**

For one folio, process its `transactions` ordered by `(date, id)` ascending,
maintaining a FIFO queue of lots:

```python
@dataclass
class Lot:
    date: date
    units: Decimal
    nav: Decimal  # this lot's purchase NAV — never changes
    # cost of what remains in this lot = units * nav, computed on read, not stored

def process_folio(transactions: list[Transaction]) -> tuple[Decimal, Decimal, Decimal]:
    lots: list[Lot] = []
    realized_gain = Decimal("0")

    for txn in transactions:
        if txn.type in {"purchase", "purchase_sip", "switch_in", "dividend_reinvest"}:
            lots.append(Lot(date=txn.date, units=txn.units, nav=txn.nav))
        elif txn.type in {"redemption", "switch_out"}:
            remaining = txn.units
            while remaining > 0 and lots:
                lot = lots[0]
                take = min(lot.units, remaining)
                realized_gain += take * (txn.nav - lot.nav)
                lot.units -= take
                remaining -= take
                if lot.units == 0:
                    lots.pop(0)
        # dividend_payout, stt, stamp_duty, misc: no effect on units/lots —
        # cash-flow-only, per the transaction taxonomy's own typing. This is
        # a stated simplification: STT/stamp duty are separate transaction
        # rows in this schema (not modifiers on a purchase row), so they
        # don't adjust cost basis here — flagged in Open Items below.

    units_held = sum(lot.units for lot in lots)
    cost_basis = sum(lot.units * lot.nav for lot in lots)
    # returns (units_held, cost_basis, realized_gain) — exact return type
    # (dataclass vs. tuple) is a plan-level detail, not specified further here
    return units_held, cost_basis, realized_gain
```

**Per-scheme holding row (FR-1 fields), merging a member's folios of the
same scheme:**

- `units_held` = sum of `units_held` across the member's folios for this scheme
- `average_nav` (cost basis) = `cost_basis / units_held` (None if `units_held == 0` — scheme has been fully redeemed, drops out of the holdings table per the edge-case table, though it still appears in cash-flow/snapshot history)
- `amount_invested` = `cost_basis` — what's still invested in *currently-held* units, not lifetime gross (lifetime gross would double-count money that's already come back out via redemption)
- `current_value` = `units_held * current_nav` (from `nav.py`)
- `unrealized_gain` = `current_value - cost_basis`
- `realized_gain` = sum of `realized_gain` across the member's folios for this scheme (all-time, survives even after a folio is fully redeemed)
- `current_profit_total` = `realized_gain + unrealized_gain` — the scheme's whole-lifetime performance, cashed-out and still-held combined
- `today_gain` = `(current_nav - previous_available_nav) * units_held`, `previous_available_nav` being the most recent `nav_history` row strictly before the one used for `current_nav`
- `plan_type` badge — reused verbatim from `folios.plan_type` (PRD-01's classification), "unverified" label when `unclassified`

**Family aggregate holdings response** keeps each row tagged with its
`household_member_id`/name (not blended across members even when two
members hold the identical scheme) — this is a wealth-management context
where whose money is whose matters. The response also includes
portfolio-level summary totals (sum of `current_value`, `current_profit_total`,
etc. across every row) for the dashboard's top-of-screen numbers.

**Allocation (`allocation.py`):** group current per-scheme holding rows
(after merging folios, before merging across members for aggregate) by
`schemes.sebi_category` mapped to a shallow bucket (Equity / Debt / Hybrid /
Other — exact bucket mapping is an implementation detail for the plan, not
specified further here) and separately by `schemes.amc_name`; each bucket's
`current_value` as an amount and as a percentage of total portfolio value.

**Active SIPs (`sip.py`):** group `purchase_sip` transactions by folio,
take the most recent one per folio; "active" if its `date` is within 40 days
of "now." Returns fund name, SIP date (most recent), SIP amount.

**Cash flow (`cash_flow.py`):** `purchase`/`purchase_sip` amounts as debit
(outflow); `redemption`/`dividend_payout` amounts as credit (inflow).
`switch_in`/`switch_out` are excluded — they're intra-portfolio movements
between schemes, not money entering or leaving the platform, and FR-7's own
wording ("purchases/SIP debits as outflow, redemptions and dividend payouts
as inflow") doesn't mention switches. `stt`/`stamp_duty`/`misc` also
excluded from this view (informational, not a cash movement in the sense
FR-7 describes).

**Monthly snapshots (`snapshots.py`):** for each month-end from the
member's first transaction to the current month, compute total value as
sum-across-folios of (units held as of that date, via the FIFO engine
truncated to transactions ≤ that date) × (NAV on/before that date, via
`nav.py`). First request for a member backfills every missing month into
`portfolio_snapshots`; subsequent requests just read the table. A month
before the member's first transaction has no data point (not a zero), per
PRD-03's own edge-case table.

## API Surface

```
GET /household-members/{id}/holdings      -> list[HoldingRow]
GET /household-members/{id}/allocation    -> AllocationSummary
GET /household-members/{id}/sips          -> list[SipRow]
GET /household-members/{id}/cash-flow     -> list[CashFlowEntry]
GET /household-members/{id}/snapshots     -> list[SnapshotRow]

GET /household/aggregate/holdings         -> AggregateResponse[HoldingRow]
GET /household/aggregate/allocation       -> AggregateResponse[AllocationSummary]
GET /household/aggregate/sips             -> AggregateResponse[SipRow]
GET /household/aggregate/cash-flow        -> AggregateResponse[CashFlowEntry]
GET /household/aggregate/snapshots        -> AggregateResponse[SnapshotRow]
```

All ten routes require `Depends(get_current_user)`. Per-member routes
additionally verify the `{id}` belongs to the authenticated user via the
existing `get_household_member_for_user` scoped lookup (same ownership
pattern already established for Import Service in Phase 2b's auth-wiring
fix) — a 404 for a member that doesn't exist or belongs to someone else,
same as `/imports/confirm` already does.

`AggregateResponse[T]` = `{members: [{id, name, has_data}], data: list[T] | T}`
(the exact per-endpoint shape — list vs. single summary object — is a
plan-level detail; `allocation`/`cash-flow` are naturally single aggregated
objects/lists while `holdings`/`sips`/`snapshots` are naturally per-item
lists tagged by member).

## Error Handling & Edge Cases

- **mfapi.in outage during NAV fetch:** degrade gracefully — same pattern
  Import Service already established (`resolve_scheme`'s `httpx.HTTPError`
  → `(None, "pending")`). If a scheme's current NAV can't be fetched at
  all, fall back to the most recent cached `nav_history` row with a clear
  stale-data label; never crash a dashboard load over a third-party outage.
- **Today's NAV not yet published** (FR-3): same fallback — most recent
  available NAV, dated, not presented as today's.
- **Fully redeemed scheme:** drops out of `holdings` (zero units), stays in
  `cash-flow` and `snapshots` (historical, not point-in-time views).
- **`unclassified` plan_type:** "unverified" badge, never silently defaulted
  to Direct or Regular.
- **Snapshot month before first transaction:** absent from the response,
  not a zero or an error.
- **Member not found / not owned by caller:** 404, matching the Import
  Service ownership-check pattern.

## Testing

**FIFO lot-tracking gets hand-built known-answer fixtures**, not just
round-trip tests — a folio with a purchase, a partial redemption, another
purchase, checked against manually-computed realized/unrealized gains and
remaining cost basis. This is the one place in this phase with real
algorithmic risk; everything else (allocation grouping, the 40-day SIP
window, cash-flow classification, family-aggregate merging and the
placeholder wrapper) is straightforward unit testing against seeded
`transactions`/`folios` rows.

`nav.py`'s `mfapi.in` calls are mocked at the HTTP boundary, same pattern as
Import Service's existing enrichment tests (`MfApiClient._get_json` mocked,
not the whole client).

Ownership checks (404 on a member that isn't the caller's) get one test per
endpoint family (per-member and aggregate), reusing the pattern already
proven in `test_imports_routes.py`'s IDOR test.

## Open Items Not Resolved Here

- **STT/stamp duty's effect on cost basis** is explicitly simplified: these
  are separate transaction rows in this schema (not modifiers on a purchase
  row), and this phase's FIFO engine treats them as cash-flow-only, not a
  cost-basis adjustment. If a future pass decides they should adjust
  realized/unrealized gain, that's a `holdings.py` change, not a schema
  change — flagging now so it isn't mistaken for an oversight later.
- **Exact asset-class bucket mapping** (which `sebi_category` values map to
  Equity/Debt/Hybrid/Other) is a small, mechanical lookup table left to the
  implementation plan, not specified here.
- **Distributor Comparison (FR-11)** — its own follow-up phase, as decided
  above.
