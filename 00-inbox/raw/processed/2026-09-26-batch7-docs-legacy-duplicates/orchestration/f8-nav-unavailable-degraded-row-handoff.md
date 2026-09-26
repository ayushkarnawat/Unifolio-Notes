# Handoff: f8-nav-unavailable-degraded-row

**Status:** DONE (2026-09-03)
**Parent:** `CLAUDE.md` Session State "F8" / `AWS Readiness/sqlite-postgres-migration-compliance-audit.md`
**Dispatch mode:** User is running this directly in their own Codex CLI/app session (not via Claude's `codex:codex-rescue` Agent dispatch) — this doc is the source of truth both sides read; update `Status` here after Codex finishes and report back.

## Task

A held scheme whose NAV can't be fetched (AMFI/mfapi outage, a delisted/unmapped scheme, etc.) currently vanishes silently from holdings/allocation/aggregates — `compute_holdings`'s `if nav_result is None: continue` (`backend/app/services/dashboard/holdings.py:189-190`) just drops the row. User decision (2026-09-02, confirmed): replace this with **a degraded row that stays visible, flagged `nav_unavailable`, with NAV-dependent fields null** — not an error state, not a silent exclusion. Transaction/FIFO-derived fields (units held, invested amount, realized gain, average NAV) are always known regardless of NAV availability and must stay populated even on a degraded row.

### 1. Backend schema — `backend/app/services/dashboard/schemas.py`

`HoldingRow` (currently lines 23-39): make the NAV-dependent fields optional and add the flag:
```python
class HoldingRow(BaseModel):
    scheme_id: str
    scheme_name: str
    amc_name: str
    household_member_id: str
    household_member_name: str
    plan_type: PlanType
    units_held: str
    average_nav: str | None
    current_nav: str | None
    current_nav_date: date | None
    amount_invested: str
    current_value: str | None
    current_profit_total: str | None
    realized_gain: str
    unrealized_gain: str | None
    today_gain: str | None
    nav_unavailable: bool = False
```
(`units_held`, `amount_invested`, `realized_gain` stay required — those never depend on NAV. `average_nav` was already optional for the unrelated "zero units held" edge case; leave as-is.)

`AllocationSummary` (currently lines 74-77): add a count so the UI/API consumer can tell "total_value excludes N holdings" instead of a silently smaller number:
```python
class AllocationSummary(BaseModel):
    by_asset_class: list[AllocationBucket]
    by_amc: list[AllocationBucket]
    total_value: str
    nav_unavailable_count: int = 0
```

### 2. `backend/app/services/dashboard/holdings.py`

In `compute_holdings`, replace the drop (lines 188-190):
```python
nav_result = nav_results[scheme.id]
if nav_result is None:
    continue
current_nav, current_nav_date = nav_result
```
with a branch that still appends a `HoldingRow`, just with the NAV-dependent fields set to `None` and `nav_unavailable=True`:
```python
nav_result = nav_results[scheme.id]
average_nav = (total_cost / total_units) if total_units else None
if nav_result is None:
    rows.append(
        HoldingRow(
            scheme_id=str(scheme.id),
            scheme_name=scheme.name,
            amc_name=scheme.amc_name,
            household_member_id=str(member_id),
            household_member_name=members[member_id].name,
            plan_type=plan_type,
            units_held=str(total_units),
            average_nav=str(average_nav) if average_nav is not None else None,
            current_nav=None,
            current_nav_date=None,
            amount_invested=str(total_cost),
            current_value=None,
            current_profit_total=None,
            realized_gain=str(total_realized),
            unrealized_gain=None,
            today_gain=None,
            nav_unavailable=True,
        )
    )
    continue
current_nav, current_nav_date = nav_result
```
Note `average_nav` gets computed once, ahead of the branch (it's needed on both the degraded and normal path) — pull the existing `average_nav = (total_cost / total_units) if total_units else None` line (currently line 199, inside the normal path) up above the `if nav_result is None` check instead of leaving it below, and delete the now-duplicate line further down. Everything else in the normal (non-degraded) path is unchanged.

### 3. `backend/app/services/dashboard/allocation.py`

`compute_allocation` will crash (`decimal.InvalidOperation`) the moment a degraded row exists, because line 33 does `Decimal(h.current_value)` unconditionally across all holdings. Fix: exclude `nav_unavailable` rows from every summation (`total_value`, `by_class`, `by_amc`), and surface their count instead of just shrinking the total silently:
```python
async def compute_allocation(db: Session, household_member_ids: list[uuid.UUID]) -> AllocationSummary:
    holdings = await compute_holdings(db, household_member_ids)

    valued_holdings = [h for h in holdings if not h.nav_unavailable]
    nav_unavailable_count = len(holdings) - len(valued_holdings)

    total_value = sum((Decimal(h.current_value) for h in valued_holdings), Decimal("0"))

    scheme_ids = {uuid.UUID(h.scheme_id) for h in valued_holdings}
    categories = {s.id: s.sebi_category for s in db.query(Scheme).filter(Scheme.id.in_(scheme_ids)).all()} if scheme_ids else {}

    by_class: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_amc: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for holding in valued_holdings:
        value = Decimal(holding.current_value)
        by_amc[holding.amc_name] += value
        category = categories.get(uuid.UUID(holding.scheme_id), "")
        by_class[_asset_class_bucket(category)] += value

    def _to_buckets(grouped: dict[str, Decimal]) -> list[AllocationBucket]:
        buckets = []
        for label, value in grouped.items():
            percentage = (value / total_value * 100) if total_value else Decimal("0")
            buckets.append(AllocationBucket(label=label, current_value=str(value), percentage=str(percentage.quantize(Decimal("0.01")))))
        return buckets

    return AllocationSummary(
        by_asset_class=_to_buckets(by_class),
        by_amc=_to_buckets(by_amc),
        total_value=str(total_value),
        nav_unavailable_count=nav_unavailable_count,
    )
```

### 4. `backend/app/services/dashboard/aggregate.py`

No change needed — confirmed it's a thin per-member→family-wide wrapper around `compute_holdings`/`compute_allocation` with no independent NAV logic of its own; the fix in items 2-3 cascades through automatically. Read it during implementation to double-check this holds (don't just take this doc's word for it), but don't add speculative changes here if it does.

### 5. Frontend — `frontend/src/components/HoldingsTable.tsx`

`HoldingRowData` (lines 8-27): mirror the backend schema's optionality:
```typescript
export interface HoldingRowData {
  scheme_id: string;
  scheme_name: string;
  amc_name?: string;
  household_member_id?: string;
  household_member_name?: string;
  plan_type: string; // "DIRECT" | "REGULAR" | "UNKNOWN"
  units_held: string;
  average_nav: string;
  current_nav: string | null;
  current_nav_date?: string | null;
  amount_invested: string;
  current_value: string | null;
  current_profit_total: string | null;
  realized_gain: string;
  unrealized_gain: string | null;
  today_gain: string | null;
  nav_unavailable?: boolean;
  stale_nav?: boolean;
  return_percentage_1y?: number;
}
```
In the row-rendering body (~lines 169-296): guard every NAV-dependent read behind `row.nav_unavailable` rather than letting `formatCurrency`/`formatNumber` silently coerce `null` to `"0"` (their current `isNaN(num) → return "0"` fallback would otherwise render a degraded holding as if it were genuinely worth ₹0, which is worse than the current silent-drop bug, not better). Concretely:
- The `unrealized`/`returnPct` derivation (lines 170-178) must special-case `row.nav_unavailable` — don't feed `null` through `parseFloat`.
- Current NAV cell (~247-260): reuse the existing `stale_nav`-badge pattern (line 253-257) for a new `nav_unavailable` badge — e.g. `{row.nav_unavailable ? <Badge variant="warning">NAV unavailable</Badge> : <span>₹{formatNumber(row.current_nav, 2)}</span>}`. Pick whatever exact copy/badge variant matches this codebase's existing warning-badge conventions (`stale_nav`'s "stale" badge is the direct precedent — match its styling, don't invent a new visual language).
- Current Value cell (~270-276) and Gain/Loss cell (~278-294): render an explicit placeholder (e.g. `"—"` or "Unavailable") instead of `₹{formatCurrency(...)}` / the gain arrow+amount when `row.nav_unavailable` is true.
- Sorting (`sortedHoldings`, lines 58-64): degraded rows' NAV-dependent fields are `null`; `parseFloat(null)` → `NaN` → the existing `|| a[sortField] || 0` fallback already sends them to `0`, which sorts them to the bottom under the default desc-by-`current_value` sort — this is acceptable default behavior, no special-case needed, but don't regress it while editing this function.

Any other consumer of `HoldingRowData`/the holdings API response (search for `current_value`, `unrealized_gain`, etc. across `frontend/src/`) that assumes these fields are always non-null must get the same guard — grep before finishing, don't assume `HoldingsTable.tsx` is the only reader.

## Constraints

- Decimal, never float — the backend changes above only add `None`-handling branches, no new arithmetic; don't introduce any float coercion while touching this code.
- Don't touch `get_navs_on_or_before`/`get_nav_on_or_before`/`get_previous_nav_from_cache` (`app/services/dashboard/nav.py`) — this task is entirely about what `compute_holdings` does with an already-`None` NAV result, not about the fetch/cache layer itself.
- `distributor_comparison.py` (`app/services/dashboard/distributor_comparison.py:~157-158`) has an **identical independent** no-NAV `continue` bug (`get_navs_on_or_before` result checked, dropped silently) but was **not named in F8's original finding scope** — leave it untouched in this task. Flag it back explicitly as a related-but-separate follow-up rather than silently fixing it as a "while we're here" bonus or silently leaving it unmentioned.
- Run the full backend test suite (add/adjust tests for the new degraded-row branch — at minimum: a `compute_holdings` test asserting a scheme with no NAV result produces a `nav_unavailable=True` row with the FIFO fields still populated and NAV fields `None`; a `compute_allocation` test asserting a degraded holding is excluded from `total_value`/buckets but counted in `nav_unavailable_count`) and the full frontend suite (Vitest) — both must stay green.
- Existing tests that assert a no-NAV scheme is absent from `compute_holdings`'s/`compute_allocation`'s output (if any exist — grep `tests/services/dashboard/test_holdings.py` and `test_allocation.py` for a `None`-NAV case) need to be updated to assert the new degraded-row shape instead of absence, not deleted.

## Approaches considered and rejected

- **Explicit error state (option a)** — rejected per user's stated preference (2026-09-02): a per-row error breaks the "one dashboard, one snapshot" mental model and would need new error-rendering UI with no precedent elsewhere in the holdings table.
- **Documented silent exclusion (option c, i.e. keep current behavior but document it)** — rejected; a real held investment quietly disappearing from a portfolio view is the actual bug being fixed, documenting it doesn't address the user-facing problem (a user has no way to know their portfolio total is understated).
- **Falling back to a stale cached NAV instead of `None`** — not pursued; `get_nav_on_or_before` already returns a stale cached value when available (see its own fallback logic in `nav.py`) — a genuine `None` result specifically means *no NAV was ever cached at all* for this scheme, so there's nothing to fall back to. This task only handles the true "never had any NAV" case.

## Open questions

- Exact copy/visual treatment for the new "NAV unavailable" badge — this doc specifies the mechanism (mirror `stale_nav`'s existing badge pattern) but the exact wording/color is a small enough call to make directly during implementation; flag back only if the existing `warning` badge variant doesn't read sensibly for this case.
- Whether any other frontend surface beyond `HoldingsTable.tsx` (allocation charts, aggregate/family dashboard views) reads `current_value`/`unrealized_gain` directly and needs the same null-guard — must be checked by grep during implementation, not assumed to be scoped to this one file.

## Review-gate note (2026-09-03, orchestrator)

Codex reported implementation complete but held Status at OPEN because the full backend suite showed 1 failure: `test_refresh_session_extends_expiry` (`tests/services/auth/test_session.py`), self-diagnosed as an unrelated Windows clock-resolution flake. Independently verified before ruling: `create_session`/`refresh_session` (`app/services/auth/session.py`) both compute `datetime.now(timezone.utc) + timedelta(days=30)` independently — two calls a few lines apart in the test can land on the same clock tick, making the strict `>` assertion a coin flip. Confirmed unrelated to this task's diff (different subsystem entirely). Fixed directly, test-only, one file (`tests/services/auth/test_session.py`): backdate `original_expiry` by 1 day before refreshing, mirroring the sibling expired-session test's existing backdating pattern. Full backend suite reran twice after the fix: first run hit 4 different, unrelated failures, all of which passed in isolation and all of which passed on a second full-suite rerun (600 passed/6 skipped/0 failed) — confirmed environment-level timing flakiness under load, not a regression from this task. Status moved to REVIEW on this basis.

## Review-gate round 1 findings (2026-09-03) — FAIL, fixed inline

Mandatory adversarial-review gate returned FAIL with 2 findings, both confirmed correct on independent read:

- **[P1] "Total Invested" understated degraded holdings' known principal.** `DashboardView.tsx`'s and `MobileDashboardView.tsx`'s totals both filtered to `valuedHoldings`/`continue`d on `nav_unavailable` *before* summing `amount_invested` — but `amount_invested` is FIFO-derived and always known regardless of NAV availability (this doc's own Task section says so explicitly). Only NAV-dependent figures (current value, gain) should exclude degraded rows. Fixed directly (small, isolated, both files already read in full this round): moved the `amount_invested` summation ahead of/outside the `nav_unavailable` filter in both files, leaving `current_value`/`unrealized_gain`/`current_profit_total` summation still correctly filtered.
- **[P2] `nav_unavailable_count` computed and typed but never surfaced.** No production frontend read it, so a shrunk-but-correct total had no "excludes N holdings" explanation anywhere. Fixed directly: added a small caption under the Total Portfolio Value figure on both desktop (`DashboardView.tsx`) and mobile (`MobileDashboardView.tsx`), conditionally rendered when `allocation.nav_unavailable_count > 0`.
- Two existing tests (`DashboardView.test.tsx`, `MobileDashboardView.test.tsx`) asserted the old (incorrect) understated-total behavior — updated to assert the corrected total and the new caption, not deleted.

Verified: scoped rerun (both dashboard test files) green, then full frontend suite rerun clean (390 passed / 75 files). Backend untouched this round (no backend files in scope for these findings) — its clean 600 passed/6 skipped/0 failed from the round-1 dispatch still holds. `distributor_comparison.py`'s sibling bug reconfirmed still present and untouched, per this doc's own scope boundary.

Status remains REVIEW pending a scoped re-review of this fix (diff confirmed narrow via `git diff --stat`: `DashboardView.tsx`, `MobileDashboardView.tsx`, and their two test files only).

## Review-gate round 2 finding (2026-09-03) — FAIL, fixed inline

Mandatory scoped re-review of round 1's fix returned FAIL with 1 P1 finding, confirmed correct on independent read:

- **[P1] Gain-percentage mixed incompatible populations.** After round 1's fix, `gainPercentage` divided `profitVal` (summed over `valuedHoldings` only, correctly excluding NAV-unavailable rows) by `investedVal` (summed over *all* holdings, including the NAV-unavailable one) — e.g. ₹5,000 valued invested + ₹2,500 profit + ₹4,000 unavailable invested reported `2500 / 9000 = 27.78%` instead of the correct `2500 / 5000 = 50%` for the return that's actually known. A degraded holding's return literally cannot be computed (no NAV to derive it from), so it must be excluded from both sides of the ratio, not just the numerator. Fixed directly (small, isolated, both files already in context): added a second, valued-only invested total (`valuedInvestedVal`) computed alongside `investedVal`, and changed `gainPercentage`'s denominator to `valuedInvestedVal`. `investedVal` (all-holdings) is unchanged and still feeds "Total Invested" per round 1's fix — the two totals now serve their own distinct purposes rather than one being reused for both.
- No existing test asserted a specific `gainPercentage` value (confirmed by grep on both test files), so no test needed updating for the old, incorrect behavior — only the two production files changed.

Verified: scoped rerun (both dashboard test files) green (22 passed), then full frontend suite rerun clean (390 passed / 75 files) since this round is expected to close the gate. `distributor_comparison.py`'s sibling bug (same denominator-mixing shape, if present) not checked this round — out of this task's file scope, consistent with round 1's scope boundary; flagging here in case a future pass on that file should check for the same class of bug.

Status remains REVIEW pending a scoped re-review of this fix.

## Review-gate round 2 re-review (2026-09-03) — PASS, performed by orchestrator directly

The Codex dispatch for this re-review hit Codex's usage limit mid-run (partial output only, no verdict — see `delegation-log.md`). Per explicit user instruction, the orchestrator performed the scoped re-review directly instead of waiting for Codex's limit reset — a deviation from this project's default "Codex reviews, orchestrator implements" split, done this once on explicit direction, not a standing change to the gate's dispatch mode.

Verified directly: (1) `gainPercentage` in both files now divides by `valuedInvestedVal` (valued-holdings-only invested total), not all-holdings `investedVal` — confirmed via `git diff` read and a manual walkthrough of the prior round's own example numbers (₹5,000 valued invested / ₹2,500 profit / ₹4,000 unavailable invested → `50%`, matching the expected correct figure, not the prior incorrect 27.78%). (2) "Total Invested" still renders `totals.investedVal` (all-holdings, unfiltered) in both files — round 1's fix not regressed. (3) Grepped both files for any other percentage/ratio computation (`Percentage`, `toFixed`, `/ total`, `Val /`) — `gainPercentage` is the only one in each file, no sibling instance of the same bug class. (4) Divide-by-zero guard (`valuedInvestedVal > 0`) intact in both. Scoped test rerun: 22/22 passed, 2 files.

**Verdict: PASS, zero findings.** Status moved to DONE.
