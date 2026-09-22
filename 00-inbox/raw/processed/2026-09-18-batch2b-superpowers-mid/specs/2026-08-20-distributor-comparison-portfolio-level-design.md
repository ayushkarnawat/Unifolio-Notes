# Distributor Comparison — Fund-Level to Portfolio-Level — Design

## Purpose

The existing Distributor Comparison feature (PRD-03 FR-11, see
`2026-08-07-distributor-comparison-design.md`) is scoped to one member +
one scheme: it only answers "how did my distributors compare *on this one
fund*?". Ayush wants this reframed as a portfolio-wide view: "how did my
distributors compare *across everything I hold*?", available at both the
per-member level and the family-aggregate level — matching how every other
Main Dashboard section (Holdings, Allocation, SIPs, Cash Flow) already
offers both scopes via the existing `viewMode: "aggregate" | "member"`
toggle. The fund-scoped variant is fully removed, not kept alongside the
new one — confirmed redundant once the portfolio-wide view exists.

## Scope

**In scope:**
- Backend: `compute_distributor_comparison` regrouped from
  `(member_id, scheme_id) -> flat rows` to
  `(household_member_ids: list[uuid.UUID]) -> distributor rows, each with a
  nested per-scheme/per-member breakdown`.
- Two new routes (`/household-members/{member_id}/distributor-comparison`,
  `/household/aggregate/distributor-comparison`), replacing the one old
  route entirely.
- A process-local TTL cache for the new function, reusing `holdings.py`'s
  existing cache pattern and invalidation signal (no new invalidation
  wiring).
- Frontend: remove the old trigger (`FundDetailModal` /
  `MobileFundDetailView`'s "Compare Distributors" button); add a new
  trigger in `DashboardView.tsx`'s Holdings section header (desktop) and
  the mobile Holdings screen; redesign both `DistributorComparisonModal`
  (desktop) and `MobileDistributorComparisonView` (mobile) around
  expandable distributor rows with a nested per-scheme breakdown.

**Explicitly out of scope:**
- Fixing `compute_holdings`'s own pre-existing per-folio `Transaction`
  N+1 query pattern. Discovered as a side effect of this work (both the
  old `compute_distributor_comparison` and `compute_holdings` do it), but
  `compute_holdings` is a working, already-heavily-reviewed, cached,
  performance-sensitive path (see `session.md`'s "Dashboard load-time
  performance fix" — 4 review rounds to get right) that this feature does
  not need to touch to do its own job correctly. Explicit instruction:
  don't risk regressing a working path for an unrelated cleanup. Flagged
  below as a follow-up candidate, not built here.
- Any change to `resolve_arn`/`arn_lookup.py` (AMFI name/status
  resolution) — reused exactly as-is.
- Any change to the Direct/Regular badge, plan-type classification, or any
  other FR-11 sibling feature.

## Architecture

```
backend/app/services/dashboard/
  distributor_comparison.py   # REWRITTEN — portfolio-wide, batched, cached
backend/app/services/dashboard/schemas.py  # DistributorComparisonRow split
                                            # into DistributorPortfolioRow +
                                            # DistributorSchemeBreakdown
backend/app/services/dashboard/aggregate.py  # +1 wrapper, same pattern as
                                              # get_aggregate_holdings etc.
backend/app/api/dashboard.py  # old route removed, 2 new routes added
```

### `distributor_comparison.py`

```python
async def compute_distributor_comparison(
    db: Session, household_member_ids: list[uuid.UUID]
) -> list[DistributorPortfolioRow]:
```

Batched, single-pass computation — no per-scheme or per-distributor
round trips:

1. One query: all folios for `household_member_ids`
   (`Folio.household_member_id.in_(...)`) — same as `compute_holdings`.
2. One query: all transactions for every folio fetched above
   (`Transaction.folio_id.in_(all_folio_ids)`), ordered the same way the
   existing lot-processing tiebreak requires. This is new code, so it's
   written batched from the start — no per-folio query loop is
   introduced (unlike the pre-existing pattern in `compute_holdings`,
   left untouched per Scope above). Transactions are grouped into a
   `dict[folio_id, list[Transaction]]` in Python after the single fetch.
3. Group folios by `(arn_code, scheme_id, household_member_id)` — the
   same three-key granularity `compute_holdings` uses for
   `(member, scheme, plan_type)`, with `arn_code` added as the outer
   grouping key. `arn_code is None` (Direct plans) groups together, same
   convention as the original fund-scoped version.
4. Per `(arn_code, scheme_id, member_id)` group: run
   `_process_folio_lots` (reused unchanged from `holdings.py`) per folio
   in the group and sum — one `DistributorSchemeBreakdown` per group.
5. Batch-fetch current NAVs for every distinct `scheme_id` encountered, via
   the existing `get_navs_on_or_before` batch helper (`nav.py`) — one call
   for the whole computation, not one per scheme and not one per
   distributor. Same helper `compute_holdings` already uses for this exact
   purpose.
6. A `DistributorSchemeBreakdown` whose scheme has no resolvable NAV is
   **dropped from that distributor's breakdown list only** — the
   distributor row itself, and every other scheme's breakdown under it,
   still renders. (Old behavior: a NAV miss dropped the *entire* response,
   acceptable when scoped to one scheme; not acceptable now that one
   response spans the whole portfolio.)
7. Roll up: for each distinct `arn_code`, sum `amount_invested`,
   `current_value`, `realized_gain`, `unrealized_gain`, and
   `current_profit_total` across that ARN's surviving breakdown rows into
   the parent `DistributorPortfolioRow`. `units_held`/`average_nav` are
   **not** carried at this level — not meaningful once summed across
   schemes with different NAVs (kept only on `DistributorSchemeBreakdown`,
   where they're still single-scheme).
8. Call `resolve_arn` once per distinct non-null `arn_code` (unchanged
   from the original design) to attach `distributor_name`/`arn_status`.

### Caching

Mirrors `holdings.py`'s existing `_holdings_cache` pattern exactly — same
shape, same TTL, same lock discipline — applied to this function's own
result:

```python
_distributor_cache: dict[tuple[tuple[uuid.UUID, ...], date], _CacheEntry]
_distributor_cache_lock = threading.Lock()
_DISTRIBUTOR_CACHE_TTL_SECONDS = 15 * 60  # same TTL constant/value as holdings
```

Cache key: `(tuple(sorted(household_member_ids)), date.today())`, generation
tuple built from **`holdings.py`'s own, already-exported**
`_holdings_cache_generation` dict — not a new counter. Every place that
already calls `invalidate_holdings_cache(member_id)` (import confirm,
opening-balance resolution) transparently invalidates this cache too, with
zero new call sites. This is a deliberate reuse of the existing signal
("this member's transactions changed"), not a new invalidation mechanism —
directly per Ayush's instruction to use the caching system that's already
built rather than add a parallel one.

Note the honest limit here: `compute_holdings`'s own cached *rows* can't be
reused as this function's data source — they're collapsed to
`(member, scheme, plan_type)` and don't retain the per-ARN split this
feature needs. What's reused is the cache *pattern* and the *invalidation
signal*, not the cached data itself, which is unavoidable given the two
functions answer different-granularity questions from the same underlying
transactions.

### Schema changes (`schemas.py`)

```python
class DistributorSchemeBreakdown(BaseModel):
    scheme_id: str
    scheme_name: str
    household_member_id: str
    household_member_name: str
    units_held: str
    average_nav: str | None
    amount_invested: str
    current_value: str
    current_profit_total: str
    realized_gain: str
    unrealized_gain: str

class DistributorPortfolioRow(BaseModel):
    arn_code: str | None
    distributor_name: str | None
    arn_status: ArnStatus | None
    amount_invested: str
    current_value: str
    current_profit_total: str
    realized_gain: str
    unrealized_gain: str
    schemes: list[DistributorSchemeBreakdown]
```

`DistributorComparisonRow` (the old flat schema) is deleted, not kept
alongside — nothing else references it once the fund-scoped route is gone.

### API routes (`dashboard.py`, `aggregate.py`)

```
GET /household-members/{member_id}/distributor-comparison
    -> list[DistributorPortfolioRow]          # calls compute_distributor_comparison(db, [member_id])

GET /household/aggregate/distributor-comparison
    -> AggregateDistributorComparisonResponse # members: list[MemberStatus], rows: list[DistributorPortfolioRow]
```

The aggregate route follows the exact envelope every other
`/household/aggregate/*` route already returns (`members` status list +
data), via a new one-line wrapper in `aggregate.py`
(`get_aggregate_distributor_comparison`), same shape as
`get_aggregate_holdings`.

The old route
(`/household-members/{member_id}/schemes/{scheme_id}/distributor-comparison`)
is deleted, not deprecated-and-kept — confirmed no longer needed.

Ownership checks (`get_household_member_for_user`, 404 for a member that
doesn't exist or isn't the caller's) carried over unchanged for the
per-member route; the aggregate route follows the existing
`/household/aggregate/*` pattern (scoped to `get_current_user`, no
per-member 404 check needed since it always operates on the caller's own
household).

## Frontend

### Desktop (`DashboardView.tsx`, `DistributorComparisonModal.tsx`)

- Remove the "Compare Distributors" button and `onCompareDistributors`
  prop from `FundDetailModal.tsx` entirely, and the
  `comparisonModalState`/`onCompareDistributors` plumbing currently in
  `DashboardView.tsx` that threads a `(memberId, schemeId, schemeName)`
  triple from the fund modal into the comparison modal.
- Add a new "Compare Distributors" button in the Holdings section header
  (next to the existing member-filter `Select`), always visible (not
  gated on a specific holding being selected).
- `DistributorComparisonModal` no longer takes `schemeId`/`schemeName`
  props. It fetches using the page's existing `viewMode`/`memberId`:
  `viewMode === "aggregate" ? getAggregateDistributorComparison() :
  getMemberDistributorComparison(memberId)` — the same conditional every
  other section on this page already uses, no new state.
- Table becomes two-level: top-level rows are distributors (name, ARN,
  status badge, invested, current value, gain), each with a
  chevron/click-to-expand control revealing its `schemes` breakdown as
  nested sub-rows (scheme name, invested, current value, gain, units,
  avg NAV) directly underneath. A `household_member_name` column on the
  breakdown sub-rows is shown only when `viewMode === "aggregate"` —
  same convention `HoldingsTable`'s `showMemberName` already uses.

### Mobile (`MobileDistributorComparisonView.tsx`)

- Same trigger removal from `MobileFundDetailView.tsx`.
- New trigger from the mobile Holdings screen (mirroring wherever the
  desktop Holdings-section button lives, adapted to the mobile shell's
  existing header/action pattern).
- Content redesigned around the mobile shell's existing card idiom (it
  already uses a card-per-row list, not a table) — each distributor is a
  card; tapping it expands in place to reveal per-scheme breakdown rows
  nested inside the same card (consistent with how the rest of the mobile
  app expands detail inline rather than pushing a new screen for one more
  level of detail). Not a straight port of the desktop table — this is
  built for the mobile shell's own patterns, since this same approach is
  the template for future mobile-native work in this app.

### API client (`api.ts`)

`getDistributorComparison(memberId, schemeId)` is replaced by:
```ts
getMemberDistributorComparison(memberId: string): Promise<DistributorPortfolioRow[]>
getAggregateDistributorComparison(): Promise<AggregateDistributorComparisonResponse>
```
matching the existing `getMemberHoldings`/`getAggregateHoldings` naming
convention exactly.

## Error Handling & Edge Cases

- **Scheme with no obtainable current NAV:** excluded from that
  distributor's `schemes` breakdown only; the distributor row and its
  other schemes still render (see Architecture step 6). A distributor
  whose *every* scheme is NAV-unavailable would render with an empty
  `schemes` list and zero totals — same silent-omission behavior already
  accepted elsewhere in this app (`CLAUDE.md` open item #1), not
  re-decided here.
- **AMFI ARN lookup fails / ARN invalid or suspended / Direct-plan
  bucket:** unchanged from the existing design (see the original spec's
  Error Handling section) — `resolve_arn` reused as-is.
- **A member/household with zero holdings across every distributor:**
  empty list, not an error — same as the original fund-scoped version's
  empty-list behavior.
- **Member not found / not owned by caller:** 404, same pattern as every
  other per-member Dashboard route.

## Testing

TDD throughout, per `AGENTS.md`. Backend:
- `compute_distributor_comparison`: rewritten fixtures covering (a) a
  single member holding one scheme via two ARNs plus a Direct folio
  (verifies rollup math: distributor totals = sum of their scheme
  breakdowns), (b) multiple members holding overlapping schemes via the
  same and different ARNs (verifies cross-member grouping never silently
  merges — each `(scheme, member)` stays its own breakdown row, per
  `compute_holdings`' existing convention), (c) one scheme's NAV
  unavailable while others resolve (verifies partial exclusion, not a
  blanket empty response), (d) cache hit/miss/TTL-expiry/generation-bump
  behavior (same test shape as `test_holdings.py`'s existing cache tests).
- Route tests for both new endpoints (member-scoped, aggregate), plus a
  test confirming the old route path now 404s/is gone.
- Batched-query assertion: a test confirming the transaction fetch issues
  a bounded number of queries regardless of folio count (e.g. via SQLAlchemy
  event counting or a query-count assertion), guarding against the N+1
  this rewrite is specifically designed to avoid.

Frontend:
- `DistributorComparisonModal.test.tsx` rewritten for the new
  no-`schemeId` fetch (both `viewMode` branches) and expand/collapse
  interaction.
- `MobileDistributorComparisonView.test.tsx` rewritten similarly for the
  new trigger and card-expansion behavior.
- `FundDetailModal.test.tsx`, `MobileFundDetailView` tests, and
  `DashboardView.test.tsx` updated to drop assertions on the removed
  trigger and cover the new Holdings-header button.

## Follow-up (not built here)

- `compute_holdings`'s pre-existing per-folio `Transaction` N+1 query
  (discovered during this work, confirmed pre-existing and out of scope —
  see Scope section) — worth a dedicated, isolated perf pass of its own,
  given how much review rigor that function's caching already went
  through. Should be logged in `CLAUDE.md`'s "Still open" list once this
  feature ships.

## Global Constraints (carried from CLAUDE.md / prior specs)

- `Decimal`, never `float`, for every money/units/NAV value, including all
  new rollup arithmetic (summing breakdown rows into a distributor total)
  and every test fixture.
- No DB schema change required — `folios.arn_code` already exists;
  everything here is service/schema/route/frontend restructuring only.
