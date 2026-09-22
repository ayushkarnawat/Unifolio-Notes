# Active SIPs — Cadence Redesign & Monthly View

## Purpose

The "Upcoming SIPs" dashboard section (shipped this session) surfaces each
active SIP's projected next due date. Its underlying detection function,
`compute_active_sips` (`backend/app/services/dashboard/sip.py`), currently
follows PRD-03 FR-6 literally: a SIP is "active" only if its most recent
`PURCHASE_SIP` transaction is within the last 40 days. A user who skips one
month's SIP (e.g. runs in July, skipped in August) silently drops off the
active list around mid-September, and only reappears once a fresh CAS
re-import ingests a new transaction confirming the SIP resumed.

Ayush has explicitly rejected this behavior for this MVP: no "you missed
your SIP" messaging (unlike Groww), and no dependency on re-importing a CAS
file to keep a SIP visible. The user already knows what date their SIP runs
on — the product should keep projecting it forward indefinitely once
detected, and only implementation-approved user action should ever have the
system need a resolution. This is an explicit experiment: if it doesn't hold
up in use, PRD-03's original 40-day-cutoff behavior is the documented
fallback.

This also adds a "SIPs for the month" view (e.g., "these are your SIPs for
August") alongside the existing forward-looking "Upcoming SIPs" list, using
the same detection engine.

## Scope

**In scope:**
- Remove the 40-day active-SIP cutoff from `compute_active_sips`.
- Exclude SIPs on fully-redeemed folios (`units_held <= 0`, computed via the
  existing FIFO engine) from the active/upcoming list — this is the only
  remaining exclusion condition.
- Add a `next_due_date` field to `SipRow`, computed server-side as a
  month-clamped roll-forward projection from the most recent transaction to
  the first occurrence on or after today.
- Add a "SIPs for the month" query: for a given `(year, month)`, one row per
  active SIP-bearing folio, showing that folio's actual transaction if one
  occurred in the requested month, otherwise the projected due date if it
  falls in that month.
- New API routes: `GET /household-members/{id}/sips/monthly` and
  `GET /household/aggregate/sips/monthly`, both taking `year`/`month` query
  params (default: current month).
- Frontend: a two-tab switcher ("Upcoming" / "This Month") in the existing
  Upcoming SIPs section, reusing the tab-switcher pattern already used by
  Portfolio Allocation. Month navigation (prev/next arrows) for the "This
  Month" tab. Delete the client-side `nextDueDate` projection `useMemo` in
  `DashboardView.tsx` in favor of the server-provided `next_due_date` field.
- A short superseding note added to PRD-03's FR-6/edge-case table, per
  CLAUDE.md's instruction to flag rather than silently resolve a PRD
  conflict.

**Explicitly out of scope:**
- No "missed SIP" flag, badge, or distinguishing visual treatment anywhere
  in the API or UI — a projected date and an actual date render identically
  from the user's perspective. (An `is_actual` boolean is a trivial future
  addition if this changes; not built now, per YAGNI.)
- No detection of SIP *amount* changes or step-up SIPs — cadence and amount
  both still anchor to the single most recent `PURCHASE_SIP` transaction,
  same as today.
- No explicit "cancelled" state or manual dismiss action — per the user's
  explicit answer, every SIP ever detected keeps rolling forward forever
  until a future session revisits this.
- No change to how a SIP is first *detected* (still: does this folio have at
  least one `PURCHASE_SIP` transaction, ever).

## Architecture

### `backend/app/services/dashboard/sip.py` (rewritten)

```python
"""Active-SIP detection and cadence projection.

A SIP is "active" if the folio has at least one PURCHASE_SIP transaction,
ever, and the folio is not fully redeemed. There is deliberately no
recency cutoff: once detected, a SIP keeps projecting its next due date
forward indefinitely, regardless of gaps in the transaction history. See
Docs/superpowers/specs/2026-08-18-active-sips-cadence-redesign-design.md
for the product rationale (supersedes PRD-03 FR-6's 40-day window).
"""

import calendar
from datetime import date

def _add_months_clamped(anchor: date, months: int) -> date:
    """anchor's day-of-month, `months` months later, clamped to the
    target month's actual length (e.g. Jan 31 + 1 month -> Feb 28)."""
    month_index = anchor.month - 1 + months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _next_due_on_or_after(anchor: date, today: date) -> date:
    """First monthly-cadence occurrence of `anchor`'s day-of-month that
    falls on or after `today`. Loop bound is small in practice (a SIP
    that's run for N years without a fresh transaction is at most ~12N
    iterations; MVP portfolio scale, not a hot path)."""
    months = 0
    candidate = anchor
    while candidate < today:
        months += 1
        candidate = _add_months_clamped(anchor, months)
    return candidate


def compute_active_sips(db: Session, household_member_ids: list[uuid.UUID]) -> list[SipRow]:
    """Unchanged signature/return shape (SipRow now carries next_due_date).
    For each folio with >=1 PURCHASE_SIP transaction ever, excluding
    fully-redeemed folios (units_held <= 0 via _process_folio_lots),
    returns the most recent PURCHASE_SIP transaction plus its rolled-
    forward next_due_date."""


def compute_sips_for_month(
    db: Session, household_member_ids: list[uuid.UUID], year: int, month: int
) -> list[SipMonthlyRow]:
    """For each active SIP-bearing folio (same eligibility as
    compute_active_sips for determining PROJECTION eligibility only —
    see redemption-exclusion note below):

    Two separate reference points are needed per folio — conflating them
    was a bug caught in spec review (see change log below):
      - `latest_txn`: the most recent PURCHASE_SIP transaction ever (same
        anchor compute_active_sips uses for forward projection).
      - `first_txn`: the EARLIEST PURCHASE_SIP transaction ever — the
        real "did this SIP exist yet" bound. Needed because `latest_txn`
        can be AFTER the requested month (e.g. browsing back to August
        once an October transaction exists as the new latest) — in that
        case months-since-latest is negative, which is valid (projecting
        backward), not a sentinel for "doesn't exist yet".

    1. Look for an actual PURCHASE_SIP transaction dated within
       [year, month]. If found (latest one, if duplicates), use its
       real date/amount.
    2. Otherwise, if (year, month) is before first_txn's (year, month),
       the SIP didn't exist yet this month -> omit.
    3. Otherwise, months_diff = (year, month) minus latest_txn's
       (year, month) (may be negative — projecting backward from a more
       recent anchor is valid and expected). The projected date is
       _add_months_clamped(latest_txn.date, months_diff); its (year,
       month) matches the requested month by construction -> include it
       as a projected row.
    4. A fully-redeemed folio still shows its own real past-month
       transactions (they really happened) but is never used to
       fabricate a projected row for a month with no real transaction —
       redemption only suppresses projection, never real history.

    Projected rows are shown with no visual distinction from actual ones
    even in hindsight (e.g. browsing back to a skipped August after a
    real October transaction exists) — consistent with the no-"missed
    SIP"-messaging decision; the row states what the cadence implies for
    that month, not a judgment on what happened.
    """
```

**Redemption-exclusion detail:** `units_held` is computed once per folio via
`_process_folio_lots(transactions)` (reused from `holdings.py`, already
imported cross-module by `distributor_comparison.py` — established
precedent). This requires no NAV fetch; it's pure transaction-ledger
arithmetic. `compute_active_sips` excludes a folio outright when
`units_held <= 0`. `compute_sips_for_month` uses the same check only to
decide whether to *fabricate a projected row* for the requested month; it
never suppresses an actual transaction that's really in the ledger for that
month, even for a folio that was later fully redeemed.

**Multiple SIP transactions in the same requested month** (rare — e.g. two
manual top-ups): the most recent one in that month is used as "the" row.
This mirrors the existing simplification of anchoring projection to a
single most-recent transaction.

### Schema additions (`backend/app/services/dashboard/schemas.py`)

```python
class SipRow(BaseModel):
    scheme_id: str
    scheme_name: str
    household_member_id: str
    household_member_name: str
    sip_date: date
    sip_amount: str
    next_due_date: date  # NEW


class SipMonthlyRow(BaseModel):
    scheme_id: str
    scheme_name: str
    household_member_id: str
    household_member_name: str
    date: date
    amount: str


class AggregateSipsMonthlyResponse(BaseModel):
    members: list[MemberStatus]
    sips: list[SipMonthlyRow]
```

### API routes (`backend/app/api/dashboard.py`)

```python
@router.get("/household-members/{member_id}/sips/monthly", response_model=list[SipMonthlyRow])
def member_sips_monthly(member_id: uuid.UUID, year: int | None = None, month: int | None = None, ...):
    today = date.today()
    y, m = year or today.year, month or today.month
    return compute_sips_for_month(db, [member_id], y, m)

@router.get("/household/aggregate/sips/monthly", response_model=AggregateSipsMonthlyResponse)
def aggregate_sips_monthly(year: int | None = None, month: int | None = None, ...):
    ...
```

`year`/`month` default to the server's current month when omitted, matching
how the "Upcoming" tab needs no params today.

### `backend/app/services/dashboard/aggregate.py`

Add `get_aggregate_sips_monthly(db, user_id, year, month)`, mirroring the
existing `get_aggregate_sips` wrapper.

### Frontend

- `frontend/src/features/dashboard/types.ts`: add `next_due_date: string` to
  `SipRow`; add `SipMonthlyRow` and `AggregateSipsMonthlyResponse`
  interfaces mirroring the backend schemas.
- `frontend/src/features/dashboard/api.ts`: add
  `getMemberSipsMonthly(memberId, year, month, signal)` and
  `getAggregateSipsMonthly(year, month, signal)`.
- `frontend/src/features/dashboard/DashboardView.tsx`:
  - Delete the client-side `upcomingSips` projection `useMemo` entirely;
    sort `sips` by the server's `next_due_date` field directly.
  - Add local state: `sipTab: "upcoming" | "month"` (default `"upcoming"`),
    `sipMonth: { year: number; month: number }` (default: current
    year/month).
  - When `sipTab === "month"`, lazily fetch monthly data (not part of the
    page's initial `Promise.all` — fetched on first switch to the tab, and
    refetched on month navigation) into a `monthlySips` state.
  - Render prev/next month arrows only when the "This Month" tab is active;
    label as e.g. "August 2026".
  - Reuse the existing segmented-tab-switcher classnames/pattern already
    used for the Allocation section's view toggle, for visual consistency.

## Performance

The dashboard's load-time work (`nav-fetch-connection-reuse-handoff.md`,
`import-preview-concurrency-handoff.md`) is a standing constraint — this
change must not reintroduce a load-time regression.

- **No NAV/network calls anywhere in this feature.** Detection, the
  redemption check, and both projection functions are pure DB-transaction
  arithmetic — no `httpx` calls, no `mfapi.in` dependency. Unaffected by the
  NAV-fetch bottlenecks the earlier perf work fixed.
- **Fixing, not introducing, an N+1 query pattern.** The *current*
  `compute_active_sips` already runs one query per folio (`most_recent =
  db.query(Transaction).filter(folio_id == folio.id, ...).first()` inside a
  `for folio in folios` loop). Adding the redemption check naively (another
  per-folio query for `_process_folio_lots`' input) would double this. The
  rewrite instead fetches **all transactions for all the household's folios
  in a single query** (`Transaction.folio_id.in_([f.id for f in folios])`,
  ordered by date), groups them in Python by `folio_id`, and derives both
  the most-recent/first SIP transaction and the FIFO units-held check from
  that one in-memory batch per folio. Net result: 2 queries total
  (`folios`, `transactions`) regardless of folio count, replacing what was
  previously O(folios) queries — a strict improvement over the current code,
  not just cost-neutral.
- **The roll-forward loop is bounded and cheap.** Worst case (a SIP anchor
  a decade stale) is on the order of ~120 loop iterations of pure date
  arithmetic — not a measurable cost next to a DB round-trip.
- **The monthly endpoint is not part of the initial dashboard load.** Per
  the frontend design above, `/sips/monthly` is fetched lazily only when
  the "This Month" tab is opened or navigated, exactly like other
  on-demand-only dashboard data — it cannot add latency to first paint.

## Error Handling & Edge Cases

| Scenario | Expected Behavior |
|----------|--------------------|
| SIP transaction history has a multi-month gap (e.g. paused 6 months) | Still shown as active; `next_due_date` rolls forward to the nearest future occurrence, no visual distinction from a never-missed SIP |
| Folio fully redeemed | Excluded from "Upcoming" entirely; still shows its real past transactions when browsing "This Month" for a month before the redemption, never a projected row for a month with no real transaction |
| Requested month is before the folio's first-ever `PURCHASE_SIP` | Folio omitted from that month's response — no fabricated pre-history row |
| Requested month is *before* the folio's most recent `PURCHASE_SIP` but *after* its first (e.g. browsing back to a skipped August once October's real transaction is the new anchor) | Projected row shown (backward-projected from the latest anchor), not omitted |
| SIP anchor day doesn't exist in target month (e.g. anchor day 31, target month has 30 days) | Clamped to the target month's last day, consistent with `next_due_date`'s own clamping |
| Leap-year Feb 29 anchor | Clamped via `calendar.monthrange`, same mechanism, no special-case code |
| Two `PURCHASE_SIP` transactions land in the same requested month | Most recent one in that month is shown as the single row |
| No household members / no folios | Both endpoints return an empty list, same as the existing `/sips` endpoints |

## Testing

Backend (`backend/tests/services/dashboard/test_sip.py`, TDD, red-green-refactor):
- `test_sip_shown_regardless_of_last_transaction_age` — replaces the old
  `test_sip_older_than_40_days_is_not_active` (inverted premise).
- `test_next_due_date_rolls_forward_multiple_months_when_gap_exceeds_one_cycle`
- `test_next_due_date_clamps_day_for_shorter_target_month` (e.g. Jan 31 →
  Feb 28)
- `test_next_due_date_handles_leap_year_feb_29_anchor`
- `test_sip_excluded_when_folio_fully_redeemed`
- `test_sips_for_month_uses_actual_transaction_when_one_exists_in_month`
- `test_sips_for_month_uses_projected_date_when_no_actual_transaction`
- `test_sips_for_month_omits_folio_before_its_first_sip`
- `test_sips_for_month_shows_real_past_transaction_even_if_folio_later_redeemed`
- `test_sips_for_month_projects_backward_correctly_when_a_later_transaction_exists`
  — anchor is October (latest), browse back to August (real gap, no actual
  August transaction): must show a projected August row, not omit it.
- `test_sips_for_month_omits_month_before_first_ever_transaction` — browsing
  a month earlier than the SIP's true first transaction must omit, using
  `first_txn`, not `latest_txn`.
- `test_compute_active_sips_uses_constant_query_count_regardless_of_folio_count`
  — no existing query-count test infra in this codebase, so this test adds
  a small inline `sqlalchemy.event.listen(engine, "before_cursor_execute",
  ...)` counter (stdlib SQLAlchemy feature, no new dependency) and asserts
  the count is identical for 1 folio vs. many, guarding the batched-query
  fix above.

`backend/tests/api/test_dashboard_sips_route.py`:
- New tests for both `/sips/monthly` routes (member + aggregate), default
  params (current month) and explicit `year`/`month` query params.

Frontend (`DashboardView.test.tsx`):
- Existing "Upcoming SIPs" tests updated: fixtures gain a `next_due_date`
  field (mocked directly, no client-side projection math to test anymore).
- New test: switching to "This Month" tab calls `getMemberSipsMonthly`/
  `getAggregateSipsMonthly` and renders returned rows.
- New test: clicking next/prev month arrow refetches with the adjusted
  year/month.

## Global Constraints (carried from CLAUDE.md / prior specs)

- `Decimal`-string arithmetic for `sip_amount`/`amount` — no float, ever.
- TDD: red-green-refactor for every backend change, no exceptions.
- No raw CAS PDF storage, no PAN persistence — unaffected by this change,
  noted for completeness.
- This is an explicitly flagged deviation from PRD-03 FR-6 (see PRD-03 note
  below) — not a silent resolution of the conflict.
