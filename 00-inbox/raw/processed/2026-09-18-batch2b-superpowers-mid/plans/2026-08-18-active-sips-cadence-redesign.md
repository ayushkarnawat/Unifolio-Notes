# Active SIPs — Cadence Redesign & Monthly View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the 40-day active-SIP cutoff so a detected SIP keeps projecting its
next due date forward indefinitely (excluding fully-redeemed folios), and add a
"SIPs for the month" view with actual-vs-projected reconciliation.

**Architecture:** Two pure date-math helpers plus a single batched per-household
transaction fetch (replacing the current per-folio N+1 query pattern) drive both
`compute_active_sips` (rewritten) and a new `compute_sips_for_month` in
`backend/app/services/dashboard/sip.py`. Two new read-only API routes expose the
monthly view. The frontend adds a lazy-fetched "This Month" tab next to the existing
"Upcoming SIPs" list and deletes its now-redundant client-side projection math in
favor of the server-provided `next_due_date` field.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest (backend); React, TypeScript,
Vitest, React Testing Library (frontend).

**Spec:** `Docs/superpowers/specs/2026-08-18-active-sips-cadence-redesign-design.md`

## Global Constraints

- `Decimal`-string arithmetic for every money value (`sip_amount`/`amount`) — never
  float, at any point in the money path.
- TDD: red-green-refactor for every backend change, no exceptions — write the failing
  test, watch it fail, then write minimal code to pass.
- No NAV/network calls anywhere in this feature — detection, the redemption check,
  and both projection functions are pure DB-transaction arithmetic.
- `compute_active_sips`/`compute_sips_for_month` must issue a constant number of
  queries regardless of folio count (single batched transaction fetch, not one query
  per folio) — this is a correctness-of-plan requirement, not an optional nicety, per
  the explicit load-time constraint this session.
- The `/sips/monthly` endpoints must never be called as part of the dashboard's
  initial page-load `Promise.all` — fetched lazily only when the "This Month" tab is
  opened or navigated.

---

### Task 1: Date-math helpers (`_add_months_clamped`, `_next_due_on_or_after`)

**Files:**
- Modify: `backend/app/services/dashboard/sip.py`
- Test: `backend/tests/services/dashboard/test_sip.py`

**Interfaces:**
- Produces: `_add_months_clamped(anchor: date, months: int) -> date`,
  `_next_due_on_or_after(anchor: date, today: date) -> date` — both pure functions,
  no DB access. Later tasks import and call these directly within `sip.py` (same
  module, no cross-file import needed for these two).

- [ ] **Step 1: Write failing tests**

Add to the top of `backend/tests/services/dashboard/test_sip.py` (after the existing
imports, before `_session`):

```python
from app.services.dashboard.sip import _add_months_clamped, _next_due_on_or_after


def test_add_months_clamped_same_day_next_month():
    assert _add_months_clamped(date(2026, 6, 5), 1) == date(2026, 7, 5)


def test_add_months_clamped_clamps_to_shorter_month():
    assert _add_months_clamped(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_add_months_clamped_handles_leap_year_feb_29_anchor():
    assert _add_months_clamped(date(2028, 2, 29), 12) == date(2029, 2, 28)


def test_add_months_clamped_rolls_year_boundary():
    assert _add_months_clamped(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_add_months_clamped_supports_negative_months():
    assert _add_months_clamped(date(2026, 10, 5), -2) == date(2026, 8, 5)


def test_next_due_on_or_after_returns_anchor_when_already_future():
    anchor = date(2026, 9, 5)
    today = date(2026, 8, 1)
    assert _next_due_on_or_after(anchor, today) == anchor


def test_next_due_on_or_after_rolls_forward_one_cycle():
    anchor = date(2026, 7, 5)
    today = date(2026, 8, 1)
    assert _next_due_on_or_after(anchor, today) == date(2026, 8, 5)


def test_next_due_on_or_after_rolls_forward_multiple_cycles_after_a_gap():
    anchor = date(2025, 7, 5)
    today = date(2026, 8, 18)
    assert _next_due_on_or_after(anchor, today) == date(2026, 9, 5)


def test_next_due_on_or_after_returns_today_when_anchor_is_today():
    today = date(2026, 8, 18)
    assert _next_due_on_or_after(today, today) == today
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && pytest tests/services/dashboard/test_sip.py -v -k "add_months_clamped or next_due_on_or_after"`
Expected: FAIL — `ImportError: cannot import name '_add_months_clamped'`

- [ ] **Step 3: Add the two helpers to `sip.py`**

At the top of `backend/app/services/dashboard/sip.py`, replace the existing module
docstring and imports with:

```python
"""Active-SIP detection and cadence projection.

A SIP is "active" if the folio has at least one PURCHASE_SIP transaction,
ever, and the folio is not fully redeemed. There is deliberately no
recency cutoff: once detected, a SIP keeps projecting its next due date
forward indefinitely, regardless of gaps in the transaction history. See
Docs/superpowers/specs/2026-08-18-active-sips-cadence-redesign-design.md
for the product rationale (supersedes PRD-03 FR-6's original 40-day
window).
"""

from __future__ import annotations

import calendar
import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models.enums import TransactionType
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.models.user import HouseholdMember
from app.services.dashboard.holdings import _LOT_CONSUMING_TYPES, _process_folio_lots
from app.services.dashboard.schemas import SipMonthlyRow, SipRow


def _add_months_clamped(anchor: date, months: int) -> date:
    """anchor's day-of-month, `months` months later (negative allowed, for
    projecting backward), clamped to the target month's actual length."""
    month_index = anchor.month - 1 + months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _next_due_on_or_after(anchor: date, today: date) -> date:
    """First monthly-cadence occurrence of anchor's day-of-month that
    falls on or after today. Loop bound is small in practice — an anchor
    a decade stale is ~120 iterations of pure date arithmetic."""
    months = 0
    candidate = anchor
    while candidate < today:
        months += 1
        candidate = _add_months_clamped(anchor, months)
    return candidate
```

Leave the rest of the file (the existing `SIP_ACTIVE_WINDOW_DAYS` constant and
`compute_active_sips`) unchanged for now — Task 2 rewrites it.

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && pytest tests/services/dashboard/test_sip.py -v`
Expected: PASS — all 9 new tests pass, all 4 existing `compute_active_sips` tests
still pass unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dashboard/sip.py backend/tests/services/dashboard/test_sip.py
git commit -m "feat: add month-clamped roll-forward date helpers for SIP projection"
```

---

### Task 2: Rewrite `compute_active_sips` — remove cutoff, add redemption exclusion, add `next_due_date`

**Files:**
- Modify: `backend/app/services/dashboard/sip.py`
- Modify: `backend/app/services/dashboard/schemas.py`
- Test: `backend/tests/services/dashboard/test_sip.py`

**Interfaces:**
- Consumes: `_add_months_clamped`, `_next_due_on_or_after` (Task 1); `_process_folio_lots(transactions: list[Transaction]) -> tuple[Decimal, Decimal, Decimal]` and `_LOT_CONSUMING_TYPES` from `app.services.dashboard.holdings` (existing, cross-module precedent already established by `distributor_comparison.py`).
- Produces: `SipRow.next_due_date: date` (schema field); `compute_active_sips(db, household_member_ids) -> list[SipRow]` (signature unchanged, behavior changed); `_folio_transactions_by_id(db, folios) -> dict[uuid.UUID, list[Transaction]]` (new private helper, reused by Task 3).

- [ ] **Step 1: Add `next_due_date` to the `SipRow` schema**

In `backend/app/services/dashboard/schemas.py`, find the existing `SipRow` class
and add the new field:

```python
class SipRow(BaseModel):
    scheme_id: str
    scheme_name: str
    household_member_id: str
    household_member_name: str
    sip_date: date
    sip_amount: str
    next_due_date: date
```

- [ ] **Step 2: Write failing tests — replace the old cutoff tests, add new ones**

In `backend/tests/services/dashboard/test_sip.py`, delete
`test_sip_within_40_days_is_active` and `test_sip_older_than_40_days_is_not_active`
entirely (their premise — a 40-day cutoff — no longer holds) and replace with:

```python
def test_sip_shown_regardless_of_last_transaction_age():
    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    _sip_txn(db, folio, date.today() - timedelta(days=400))

    sips = compute_active_sips(db, [member.id])
    assert len(sips) == 1
    assert sips[0].scheme_name == "SIP Fund"


def test_sip_next_due_date_rolls_forward_from_last_transaction():
    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    last_run = date.today() - timedelta(days=100)
    _sip_txn(db, folio, last_run)

    sips = compute_active_sips(db, [member.id])
    assert len(sips) == 1
    assert sips[0].next_due_date >= date.today()


def test_sip_excluded_when_folio_fully_redeemed():
    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    _sip_txn(db, folio, date.today() - timedelta(days=60), units=Decimal("20.000"), nav=Decimal("50.0000"))
    db.add(Transaction(
        id=uuid.uuid4(), folio_id=folio.id, import_id=uuid.uuid4(),
        type=TransactionType.REDEMPTION, date=date.today() - timedelta(days=10),
        amount=Decimal("1000.00"), units=Decimal("20.000"), nav=Decimal("50.0000"),
    ))
    db.commit()

    sips = compute_active_sips(db, [member.id])
    assert sips == []
```

Keep `test_sip_uses_most_recent_transaction_per_folio` and
`test_non_sip_purchase_is_not_a_sip` as-is (both still pass unchanged with the
rewrite).

- [ ] **Step 3: Run tests, verify the new/changed ones fail correctly**

Run: `cd backend && pytest tests/services/dashboard/test_sip.py -v`
Expected: `test_sip_shown_regardless_of_last_transaction_age` FAILS (current code
still applies the 40-day cutoff — the test's 400-day-old transaction gets dropped);
`test_sip_next_due_date_rolls_forward_from_last_transaction` FAILS with
`AttributeError: 'SipRow' object has no attribute 'next_due_date'` before Step 1's
schema addition takes effect in `compute_active_sips`'s construction call (it will
error on missing kwarg, or Pydantic will reject the extra unused schema field
silently populating nothing — confirm the failure is about the missing
`next_due_date` value, not a typo); `test_sip_excluded_when_folio_fully_redeemed`
FAILS (current code has no redemption check at all — the SIP still appears).

- [ ] **Step 4: Rewrite `compute_active_sips`**

Replace the existing `SIP_ACTIVE_WINDOW_DAYS` constant and `compute_active_sips`
function in `backend/app/services/dashboard/sip.py` with:

```python
def _folio_transactions_by_id(
    db: Session, folios: list[Folio]
) -> dict[uuid.UUID, list[Transaction]]:
    """Single batched query for every given folio's transactions, ordered
    exactly like holdings.py's per-folio query (same-date redemptions
    sorted after purchases, so _process_folio_lots gets correctly-ordered
    input) — replaces what would otherwise be one query per folio."""
    folio_ids = [f.id for f in folios]
    if not folio_ids:
        return {}
    transactions = (
        db.query(Transaction)
        .filter(Transaction.folio_id.in_(folio_ids))
        .order_by(
            Transaction.date,
            case((Transaction.type.in_(_LOT_CONSUMING_TYPES), 1), else_=0),
            Transaction.id,
        )
        .all()
    )
    by_folio: dict[uuid.UUID, list[Transaction]] = defaultdict(list)
    for txn in transactions:
        by_folio[txn.folio_id].append(txn)
    return by_folio


def compute_active_sips(db: Session, household_member_ids: list[uuid.UUID]) -> list[SipRow]:
    if not household_member_ids:
        return []

    members = {
        m.id: m
        for m in db.query(HouseholdMember).filter(HouseholdMember.id.in_(household_member_ids)).all()
    }
    folios = db.query(Folio).filter(Folio.household_member_id.in_(household_member_ids)).all()
    by_folio = _folio_transactions_by_id(db, folios)
    today = date.today()

    rows: list[SipRow] = []
    for folio in folios:
        transactions = by_folio.get(folio.id, [])
        sip_txns = [t for t in transactions if t.type == TransactionType.PURCHASE_SIP]
        if not sip_txns:
            continue

        units_held, _, _ = _process_folio_lots(transactions)
        if units_held <= 0:
            continue

        latest = sip_txns[-1]  # transactions is chronologically ordered
        scheme = db.get(Scheme, folio.scheme_id)
        rows.append(
            SipRow(
                scheme_id=str(scheme.id),
                scheme_name=scheme.name,
                household_member_id=str(folio.household_member_id),
                household_member_name=members[folio.household_member_id].name,
                sip_date=latest.date,
                sip_amount=str(latest.amount),
                next_due_date=_next_due_on_or_after(latest.date, today),
            )
        )
    return rows
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `cd backend && pytest tests/services/dashboard/test_sip.py -v`
Expected: PASS — all tests in the file pass, including the two kept-unchanged ones.

- [ ] **Step 6: Run the full backend suite to check for regressions**

Run: `cd backend && pytest -q`
Expected: PASS, no new failures. `backend/tests/api/test_dashboard_sips_route.py`
should still pass unchanged (it only checks empty-list/auth behavior, not the
cutoff).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/dashboard/sip.py backend/app/services/dashboard/schemas.py backend/tests/services/dashboard/test_sip.py
git commit -m "feat: remove 40-day SIP cutoff, add redemption exclusion and next_due_date"
```

---

### Task 3: Add `compute_sips_for_month` and monthly schemas

**Files:**
- Modify: `backend/app/services/dashboard/sip.py`
- Modify: `backend/app/services/dashboard/schemas.py`
- Test: `backend/tests/services/dashboard/test_sip.py`

**Interfaces:**
- Consumes: `_add_months_clamped`, `_folio_transactions_by_id`, `_process_folio_lots` (all from this file / Task 1-2).
- Produces: `SipMonthlyRow` schema; `compute_sips_for_month(db, household_member_ids, year, month) -> list[SipMonthlyRow]` — consumed by Task 5's API routes.

- [ ] **Step 1: Add `SipMonthlyRow` and `AggregateSipsMonthlyResponse` schemas**

In `backend/app/services/dashboard/schemas.py`, add after the existing `SipRow`
class:

```python
class SipMonthlyRow(BaseModel):
    scheme_id: str
    scheme_name: str
    household_member_id: str
    household_member_name: str
    date: date
    amount: str
```

And after the existing `AggregateSipsResponse` class:

```python
class AggregateSipsMonthlyResponse(BaseModel):
    members: list[MemberStatus]
    sips: list[SipMonthlyRow]
```

- [ ] **Step 2: Write failing tests**

Add to `backend/tests/services/dashboard/test_sip.py`:

```python
from app.services.dashboard.sip import compute_sips_for_month


def test_sips_for_month_uses_actual_transaction_when_one_exists_in_month():
    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    _sip_txn(db, folio, date(2026, 7, 5), amount=Decimal("1000.00"))
    _sip_txn(db, folio, date(2026, 8, 7), amount=Decimal("1200.00"))

    rows = compute_sips_for_month(db, [member.id], 2026, 8)
    assert len(rows) == 1
    assert rows[0].date == date(2026, 8, 7)
    assert Decimal(rows[0].amount) == Decimal("1200.00")


def test_sips_for_month_uses_projected_date_when_no_actual_transaction():
    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    _sip_txn(db, folio, date(2026, 7, 5), amount=Decimal("1000.00"))
    # August skipped entirely — no actual transaction.

    rows = compute_sips_for_month(db, [member.id], 2026, 8)
    assert len(rows) == 1
    assert rows[0].date == date(2026, 8, 5)
    assert Decimal(rows[0].amount) == Decimal("1000.00")


def test_sips_for_month_omits_month_before_first_ever_transaction():
    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    _sip_txn(db, folio, date(2026, 7, 5))

    rows = compute_sips_for_month(db, [member.id], 2026, 3)
    assert rows == []


def test_sips_for_month_projects_backward_correctly_when_a_later_transaction_exists():
    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    _sip_txn(db, folio, date(2026, 7, 5), amount=Decimal("1000.00"))
    # August skipped, SIP resumes in October — October becomes the latest anchor.
    _sip_txn(db, folio, date(2026, 10, 5), amount=Decimal("1000.00"))

    rows = compute_sips_for_month(db, [member.id], 2026, 8)
    assert len(rows) == 1
    assert rows[0].date == date(2026, 8, 5)


def test_sips_for_month_shows_real_past_transaction_even_if_folio_later_redeemed():
    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    _sip_txn(db, folio, date(2026, 7, 5), amount=Decimal("1000.00"), units=Decimal("20.000"), nav=Decimal("50.0000"))
    db.add(Transaction(
        id=uuid.uuid4(), folio_id=folio.id, import_id=uuid.uuid4(),
        type=TransactionType.REDEMPTION, date=date(2026, 9, 1),
        amount=Decimal("1000.00"), units=Decimal("20.000"), nav=Decimal("50.0000"),
    ))
    db.commit()

    rows = compute_sips_for_month(db, [member.id], 2026, 7)
    assert len(rows) == 1
    assert rows[0].date == date(2026, 7, 5)

    # But no fabricated projected row for a later, unpaid month post-redemption.
    rows_later = compute_sips_for_month(db, [member.id], 2026, 11)
    assert rows_later == []
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `cd backend && pytest tests/services/dashboard/test_sip.py -v -k sips_for_month`
Expected: FAIL — `ImportError: cannot import name 'compute_sips_for_month'`

- [ ] **Step 4: Implement `compute_sips_for_month`**

Append to `backend/app/services/dashboard/sip.py`:

```python
def compute_sips_for_month(
    db: Session, household_member_ids: list[uuid.UUID], year: int, month: int
) -> list[SipMonthlyRow]:
    if not household_member_ids:
        return []

    members = {
        m.id: m
        for m in db.query(HouseholdMember).filter(HouseholdMember.id.in_(household_member_ids)).all()
    }
    folios = db.query(Folio).filter(Folio.household_member_id.in_(household_member_ids)).all()
    by_folio = _folio_transactions_by_id(db, folios)

    rows: list[SipMonthlyRow] = []
    for folio in folios:
        transactions = by_folio.get(folio.id, [])
        sip_txns = [t for t in transactions if t.type == TransactionType.PURCHASE_SIP]
        if not sip_txns:
            continue

        first_txn = sip_txns[0]
        latest_txn = sip_txns[-1]
        actual = next(
            (t for t in reversed(sip_txns) if t.date.year == year and t.date.month == month),
            None,
        )
        scheme = db.get(Scheme, folio.scheme_id)
        member_name = members[folio.household_member_id].name

        if actual is not None:
            rows.append(
                SipMonthlyRow(
                    scheme_id=str(scheme.id),
                    scheme_name=scheme.name,
                    household_member_id=str(folio.household_member_id),
                    household_member_name=member_name,
                    date=actual.date,
                    amount=str(actual.amount),
                )
            )
            continue

        units_held, _, _ = _process_folio_lots(transactions)
        if units_held <= 0:
            # Redeemed, and no real transaction landed in this month —
            # never fabricate a projected row for a dead folio.
            continue

        if (year, month) < (first_txn.date.year, first_txn.date.month):
            continue

        months_diff = (year - latest_txn.date.year) * 12 + (month - latest_txn.date.month)
        projected_date = _add_months_clamped(latest_txn.date, months_diff)
        rows.append(
            SipMonthlyRow(
                scheme_id=str(scheme.id),
                scheme_name=scheme.name,
                household_member_id=str(folio.household_member_id),
                household_member_name=member_name,
                date=projected_date,
                amount=str(latest_txn.amount),
            )
        )
    return rows
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `cd backend && pytest tests/services/dashboard/test_sip.py -v`
Expected: PASS — all tests in the file pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dashboard/sip.py backend/app/services/dashboard/schemas.py backend/tests/services/dashboard/test_sip.py
git commit -m "feat: add compute_sips_for_month with actual-vs-projected reconciliation"
```

---

### Task 4: Query-count regression test (load-time guard)

**Files:**
- Test: `backend/tests/services/dashboard/test_sip.py`

**Interfaces:**
- Consumes: `compute_active_sips` (Task 2), the `_session` SQLite fixture already in
  this test file.

- [ ] **Step 1: Write the test**

Add to `backend/tests/services/dashboard/test_sip.py`:

```python
from sqlalchemy import event


def test_compute_active_sips_uses_constant_query_count_regardless_of_folio_count():
    db = _session()
    member = _household_member(db)

    def _make_folio_with_sip():
        scheme = _scheme(db, name=f"Fund {uuid.uuid4().hex[:6]}")
        folio = _folio(db, member, scheme)
        _sip_txn(db, folio, date.today() - timedelta(days=10))
        return folio

    _make_folio_with_sip()

    counts: list[int] = []

    def _count_queries(n_folios: int) -> int:
        for _ in range(n_folios - 1):
            _make_folio_with_sip()
        count = 0

        def _on_execute(*args, **kwargs):
            nonlocal count
            count += 1

        event.listen(db.get_bind(), "before_cursor_execute", _on_execute)
        try:
            compute_active_sips(db, [member.id])
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", _on_execute)
        return count

    counts.append(_count_queries(1))
    counts.append(_count_queries(5))

    assert counts[0] == counts[1], f"query count grew with folio count: {counts}"
```

- [ ] **Step 2: Run the test, verify it passes**

Run: `cd backend && pytest tests/services/dashboard/test_sip.py -v -k constant_query_count`
Expected: PASS — since Task 2 already implemented the batched-query fix, this test
should be green immediately (it is a regression guard, not new red-green
implementation work; the "TDD" step here is confirming the guard actually catches
what it claims to, not driving new production code).

**Verify the guard actually works** (sanity check, not a permanent step): temporarily
revert `_folio_transactions_by_id`'s single query to a per-folio loop (e.g. paste the
old per-folio `db.query(...).filter(Transaction.folio_id == folio.id)...` call
inline) and re-run this one test — confirm it now FAILS. Then restore the batched
version and confirm it passes again. This proves the assertion is meaningful before
moving on.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/services/dashboard/test_sip.py
git commit -m "test: guard compute_active_sips against reintroducing N+1 queries"
```

---

### Task 5: API routes for the monthly view

**Files:**
- Modify: `backend/app/api/dashboard.py`
- Modify: `backend/app/services/dashboard/aggregate.py`
- Test: `backend/tests/api/test_dashboard_sips_route.py`

**Interfaces:**
- Consumes: `compute_sips_for_month` (Task 3), `SipMonthlyRow`/
  `AggregateSipsMonthlyResponse` schemas (Task 3), `get_member_statuses` (existing,
  from `aggregate.py`).
- Produces: `GET /household-members/{member_id}/sips/monthly`,
  `GET /household/aggregate/sips/monthly`; `get_aggregate_sips_monthly(db, user_id, year, month) -> AggregateSipsMonthlyResponse`.

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/api/test_dashboard_sips_route.py`:

```python
def test_sips_monthly_route_requires_auth(client):
    response = client.get(
        "/household-members/00000000-0000-0000-0000-000000000000/sips/monthly"
    )
    assert response.status_code == 401


def test_sips_monthly_route_defaults_to_current_month(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000021")
    response = client.get(f"/household-members/{member_id}/sips/monthly", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_sips_monthly_route_accepts_explicit_year_and_month(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000022")
    response = client.get(
        f"/household-members/{member_id}/sips/monthly",
        params={"year": 2026, "month": 3},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == []


def test_aggregate_sips_monthly_route_returns_member_statuses(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000023")
    response = client.get("/household/aggregate/sips/monthly", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["sips"] == []
    assert len(body["members"]) == 1
    assert body["members"][0]["id"] == member_id
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && pytest tests/api/test_dashboard_sips_route.py -v`
Expected: FAIL with 404 (routes don't exist yet).

- [ ] **Step 3: Add `get_aggregate_sips_monthly` to `aggregate.py`**

In `backend/app/services/dashboard/aggregate.py`, add the import and function.
Modify the existing import block:

```python
from app.services.dashboard.schemas import (
    AggregateAllocationResponse,
    AggregateCashFlowResponse,
    AggregateHoldingsResponse,
    AggregateSipsMonthlyResponse,
    AggregateSipsResponse,
    AggregateSnapshotsResponse,
    MemberStatus,
)
from app.services.dashboard.sip import compute_active_sips, compute_sips_for_month
```

Add after the existing `get_aggregate_sips` function:

```python
def get_aggregate_sips_monthly(
    db: Session, user_id: uuid.UUID, year: int, month: int
) -> AggregateSipsMonthlyResponse:
    members = list_household_members(db, user_id)
    statuses = get_member_statuses(db, user_id)
    sips = compute_sips_for_month(db, [m.id for m in members], year, month)
    return AggregateSipsMonthlyResponse(members=statuses, sips=sips)
```

- [ ] **Step 4: Add the two routes to `dashboard.py`**

Modify the existing imports in `backend/app/api/dashboard.py`:

```python
from app.services.dashboard.aggregate import (
    get_aggregate_allocation,
    get_aggregate_cash_flow,
    get_aggregate_holdings,
    get_aggregate_sips,
    get_aggregate_sips_monthly,
    get_aggregate_snapshots,
)
```

```python
from app.services.dashboard.schemas import (
    AggregateAllocationResponse,
    AggregateCashFlowResponse,
    AggregateHoldingsResponse,
    AggregateSipsMonthlyResponse,
    AggregateSipsResponse,
    AggregateSnapshotsResponse,
    AllocationSummary,
    CashFlowEntry,
    DistributorComparisonRow,
    HoldingRow,
    HouseholdMemberCreate,
    HouseholdMemberResponse,
    SipMonthlyRow,
    SipRow,
    SnapshotRow,
)

from app.services.dashboard.sip import compute_active_sips, compute_sips_for_month
```

Add after the existing `get_member_sips` route:

```python
@router.get("/household-members/{member_id}/sips/monthly", response_model=list[SipMonthlyRow])
def get_member_sips_monthly(
    member_id: uuid.UUID,
    year: int | None = None,
    month: int | None = None,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if get_household_member_for_user(db, user.id, member_id) is None:
        raise HTTPException(status_code=404, detail="Household member not found.")
    today = date.today()
    return compute_sips_for_month(db, [member_id], year or today.year, month or today.month)
```

Add `from datetime import date` to the top of `dashboard.py` (not currently
imported there).

Add after the existing `get_household_aggregate_sips` route:

```python
@router.get("/household/aggregate/sips/monthly", response_model=AggregateSipsMonthlyResponse)
def get_household_aggregate_sips_monthly(
    year: int | None = None,
    month: int | None = None,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    today = date.today()
    return get_aggregate_sips_monthly(db, user.id, year or today.year, month or today.month)
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `cd backend && pytest tests/api/test_dashboard_sips_route.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/dashboard.py backend/app/services/dashboard/aggregate.py backend/tests/api/test_dashboard_sips_route.py
git commit -m "feat: add /sips/monthly API routes (member + aggregate)"
```

---

### Task 6: Frontend types and API client

**Files:**
- Modify: `frontend/src/features/dashboard/types.ts`
- Modify: `frontend/src/features/dashboard/api.ts`

**Interfaces:**
- Produces: `SipRow.next_due_date: string` (updated), `SipMonthlyRow`,
  `AggregateSipsMonthlyResponse` types; `getMemberSipsMonthly`,
  `getAggregateSipsMonthly` functions — consumed by Task 7.

No test file for this task — pure type/thin-wrapper additions with no branching
logic, consistent with how the sibling `getMemberSips`/`getAggregateSips` functions
already have no dedicated unit test (they're exercised indirectly through
`DashboardView.test.tsx`'s mocks in Task 8).

- [ ] **Step 1: Update `types.ts`**

In `frontend/src/features/dashboard/types.ts`, modify the existing `SipRow`
interface:

```typescript
export interface SipRow {
  scheme_id: string;
  scheme_name: string;
  household_member_id: string;
  household_member_name: string;
  sip_date: string;
  sip_amount: string;
  next_due_date: string;
}
```

Add after it:

```typescript
export interface SipMonthlyRow {
  scheme_id: string;
  scheme_name: string;
  household_member_id: string;
  household_member_name: string;
  date: string;
  amount: string;
}
```

Add after the existing `AggregateSipsResponse` interface:

```typescript
export interface AggregateSipsMonthlyResponse {
  members: FamilyMemberStatus[];
  sips: SipMonthlyRow[];
}
```

- [ ] **Step 2: Update `api.ts`**

In `frontend/src/features/dashboard/api.ts`, add `SipMonthlyRow` and
`AggregateSipsMonthlyResponse` to the existing type-only import block from
`./types`.

Add after the existing `getMemberSips` function:

```typescript
export async function getMemberSipsMonthly(
  memberId: string,
  year: number,
  month: number,
  signal?: AbortSignal
): Promise<SipMonthlyRow[]> {
  const res = await authFetch(
    `/household-members/${memberId}/sips/monthly?year=${year}&month=${month}`,
    { signal }
  );
  return res.json();
}
```

Add after the existing `getAggregateSips` function:

```typescript
export async function getAggregateSipsMonthly(
  year: number,
  month: number,
  signal?: AbortSignal
): Promise<AggregateSipsMonthlyResponse> {
  const res = await authFetch(
    `/household/aggregate/sips/monthly?year=${year}&month=${month}`,
    { signal }
  );
  return res.json();
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors (these two files compile cleanly in isolation; `DashboardView.tsx`
won't reference the new functions until Task 7, so no downstream breakage yet).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/dashboard/types.ts frontend/src/features/dashboard/api.ts
git commit -m "feat: add SipMonthlyRow types and monthly-SIPs API client functions"
```

---

### Task 7: `DashboardView.tsx` — server-provided `next_due_date`, "This Month" tab

**Files:**
- Modify: `frontend/src/features/dashboard/DashboardView.tsx`

**Interfaces:**
- Consumes: `SipRow.next_due_date`, `SipMonthlyRow`, `getMemberSipsMonthly`,
  `getAggregateSipsMonthly` (Task 6).

- [ ] **Step 1: Delete the client-side projection `useMemo`, sort by server field**

In `frontend/src/features/dashboard/DashboardView.tsx`, replace the existing
`upcomingSips` `useMemo` (currently computing `nextDueDate` client-side) with:

```typescript
const upcomingSips = useMemo(() => {
  return [...sips].sort(
    (a, b) => new Date(a.next_due_date).getTime() - new Date(b.next_due_date).getTime()
  );
}, [sips]);
```

- [ ] **Step 2: Update the JSX that reads `sip.nextDueDate`**

In the "Upcoming SIPs Section" JSX block, change:

```typescript
{sip.nextDueDate.toLocaleDateString("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
})}
```

to:

```typescript
{new Date(sip.next_due_date).toLocaleDateString("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
})}
```

- [ ] **Step 3: Add imports, state, and a fetch function for the monthly view**

Add `SipMonthlyRow` to the existing `import type { ... } from "./types"` block.
Add `getMemberSipsMonthly, getAggregateSipsMonthly` to the existing
`import { ... } from "./api"` block.

Add new state, near the existing `allocationTab` state declaration:

```typescript
const [sipTab, setSipTab] = useState<"upcoming" | "month">("upcoming");
const today = new Date();
const [sipMonth, setSipMonth] = useState<{ year: number; month: number }>({
  year: today.getFullYear(),
  month: today.getMonth() + 1,
});
const [monthlySips, setMonthlySips] = useState<SipMonthlyRow[]>([]);
const [monthlySipsLoading, setMonthlySipsLoading] = useState(false);
```

Add a new `useEffect` after the existing data-fetching `useEffect`, fetching the
monthly view only when the "This Month" tab is active (lazy — never part of the
initial page-load `Promise.all`):

```typescript
useEffect(() => {
  if (sipTab !== "month") return;
  let isMounted = true;
  const controller = new AbortController();
  setMonthlySipsLoading(true);

  const fetchMonthly = async () => {
    try {
      const rows =
        viewMode === "aggregate"
          ? (await getAggregateSipsMonthly(sipMonth.year, sipMonth.month, controller.signal)).sips
          : memberId
            ? await getMemberSipsMonthly(memberId, sipMonth.year, sipMonth.month, controller.signal)
            : [];
      if (isMounted) {
        setMonthlySips(rows);
        setMonthlySipsLoading(false);
      }
    } catch (err: unknown) {
      if (isMounted && !(err instanceof DOMException && err.name === "AbortError")) {
        setMonthlySips([]);
        setMonthlySipsLoading(false);
      }
    }
  };

  fetchMonthly();
  return () => {
    isMounted = false;
    controller.abort();
  };
}, [sipTab, sipMonth, viewMode, memberId]);
```

- [ ] **Step 4: Add the tab switcher and month navigation to the Upcoming SIPs JSX**

Replace the "Upcoming SIPs Section" JSX block's header (currently just an `<h2>`)
and body with a tab switcher plus conditional content. Replace:

```typescript
{/* Upcoming SIPs Section (PRD-03 FR-5/FR-6) */}
{upcomingSips.length > 0 && (
  <section className="flex flex-col space-y-4" data-testid="upcoming-sips">
    <h2 className="font-display text-lg font-semibold tracking-tight text-[var(--color-ink)]">
      Upcoming SIPs
    </h2>

    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] divide-y divide-[var(--color-border)]">
      {upcomingSips.map((sip) => (
```

with:

```typescript
{/* Upcoming SIPs Section (PRD-03 FR-5/FR-6) */}
{upcomingSips.length > 0 && (
  <section className="flex flex-col space-y-4" data-testid="upcoming-sips">
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <h2 className="font-display text-lg font-semibold tracking-tight text-[var(--color-ink)]">
        SIPs
      </h2>

      <div className="inline-flex items-center p-1 rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] self-start sm:self-auto shadow-2xs">
        <button
          className={cn(
            "px-3 py-1 text-xs font-medium rounded-lg transition-colors duration-150 cursor-pointer",
            sipTab === "upcoming"
              ? "bg-[var(--color-bg)] text-[var(--color-ink)] font-semibold shadow-xs"
              : "text-[var(--color-text-secondary)] hover:text-[var(--color-ink)]"
          )}
          onClick={() => setSipTab("upcoming")}
          type="button"
        >
          Upcoming
        </button>
        <button
          className={cn(
            "px-3 py-1 text-xs font-medium rounded-lg transition-colors duration-150 cursor-pointer",
            sipTab === "month"
              ? "bg-[var(--color-bg)] text-[var(--color-ink)] font-semibold shadow-xs"
              : "text-[var(--color-text-secondary)] hover:text-[var(--color-ink)]"
          )}
          onClick={() => setSipTab("month")}
          type="button"
        >
          This Month
        </button>
      </div>
    </div>

    {sipTab === "month" && (
      <div className="flex items-center justify-center gap-4">
        <button
          type="button"
          aria-label="Previous month"
          className="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-ink)] cursor-pointer"
          onClick={() =>
            setSipMonth((prev) =>
              prev.month === 1
                ? { year: prev.year - 1, month: 12 }
                : { year: prev.year, month: prev.month - 1 }
            )
          }
        >
          &larr;
        </button>
        <span className="text-sm font-medium text-[var(--color-ink)] tabular-nums">
          {new Date(sipMonth.year, sipMonth.month - 1, 1).toLocaleDateString("en-IN", {
            month: "long",
            year: "numeric",
          })}
        </span>
        <button
          type="button"
          aria-label="Next month"
          className="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-ink)] cursor-pointer"
          onClick={() =>
            setSipMonth((prev) =>
              prev.month === 12
                ? { year: prev.year + 1, month: 1 }
                : { year: prev.year, month: prev.month + 1 }
            )
          }
        >
          &rarr;
        </button>
      </div>
    )}

    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] divide-y divide-[var(--color-border)]">
      {sipTab === "upcoming" && upcomingSips.map((sip) => (
```

Then, after the existing closing of that `.map()` call (the original code's
`))}` for `upcomingSips.map`), add the "This Month" tab's own rendering, before the
outer `</div></section>` close:

```typescript
      {sipTab === "month" && !monthlySipsLoading && monthlySips.length === 0 && (
        <div className="px-4 py-6 text-center text-sm text-[var(--color-text-secondary)]">
          No SIPs for this month.
        </div>
      )}
      {sipTab === "month" &&
        monthlySips.map((sip) => (
          <div
            key={sip.scheme_id + sip.household_member_id}
            className="flex items-center justify-between gap-4 px-4 py-3"
          >
            <div className="flex flex-col min-w-0">
              <span className="text-sm font-medium text-[var(--color-ink)] truncate">
                {sip.scheme_name}
              </span>
              {viewMode === "aggregate" && (
                <span className="text-xs text-[var(--color-text-secondary)]">
                  {sip.household_member_name}
                </span>
              )}
            </div>
            <div className="flex items-center gap-6 flex-shrink-0">
              <span className="text-xs text-[var(--color-text-secondary)] tabular-nums">
                {new Date(sip.date).toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </span>
              <span className="text-sm font-semibold text-[var(--color-ink)] tabular-nums">
                ₹{formatIndianCurrency(sip.amount)}
              </span>
            </div>
          </div>
        ))}
```

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/dashboard/DashboardView.tsx
git commit -m "feat: add This Month SIP tab, use server-provided next_due_date"
```

---

### Task 8: Frontend tests

**Files:**
- Modify: `frontend/src/features/dashboard/DashboardView.test.tsx`
- Modify: `frontend/src/features/dashboard/MainDashboardFlow.test.tsx`

**Interfaces:**
- Consumes: everything from Tasks 6-7.

- [ ] **Step 1: Update the mock factory and existing SIP fixtures (fix, don't skip, the break this will otherwise cause)**

In `frontend/src/features/dashboard/DashboardView.test.tsx`, add
`getMemberSipsMonthly: vi.fn(), getAggregateSipsMonthly: vi.fn(),` to the existing
`vi.mock("./api", ...)` factory, and default resolved values in `beforeEach`:

```typescript
vi.mocked(api.getMemberSipsMonthly).mockResolvedValue([]);
vi.mocked(api.getAggregateSipsMonthly).mockResolvedValue({ members: [], sips: [] });
```

In the existing test `"renders an Upcoming SIPs section with the projected next SIP
date, sorted soonest-first"`, add `next_due_date` to both fixture SIP rows (values
chosen so the existing sort-order assertion — Axis before HDFC — still holds, now
driven by the server field instead of client computation):

```typescript
vi.mocked(api.getMemberSips).mockResolvedValue([
  {
    scheme_id: "scheme-101",
    scheme_name: "HDFC Top 100 Fund",
    household_member_id: "m-1",
    household_member_name: "John",
    sip_date: "2026-08-20",
    sip_amount: "5000.00",
    next_due_date: "2026-09-20",
  },
  {
    scheme_id: "scheme-202",
    scheme_name: "Axis Long Term Equity",
    household_member_id: "m-1",
    household_member_name: "John",
    sip_date: "2026-08-05",
    sip_amount: "2500.00",
    next_due_date: "2026-09-05",
  },
]);
```

Delete the comment above the sort assertion that described the now-removed
client-side projection math ("Projected next date = last sip_date + 1 month...")
and replace it with:

```typescript
// next_due_date is now server-provided directly — Axis (closer date) sorts
// before HDFC (farther date).
```

The "hides the Upcoming SIPs section when there are no active SIPs" test needs no
changes (it never mocks `getMemberSips` with data, so it's unaffected).

- [ ] **Step 2: Run the two existing tests, verify they still pass**

Run: `cd frontend && npx vitest run src/features/dashboard/DashboardView.test.tsx`
Expected: PASS.

- [ ] **Step 3: Write failing tests for the "This Month" tab**

Add to `frontend/src/features/dashboard/DashboardView.test.tsx`, after the "hides
the Upcoming SIPs section..." test:

```typescript
it("switches to This Month tab and renders monthly SIP rows", async () => {
  vi.mocked(api.getMemberHoldings).mockResolvedValue([
    {
      scheme_id: "scheme-101",
      scheme_name: "HDFC Top 100 Fund",
      amc_name: "HDFC Mutual Fund",
      household_member_id: "m-1",
      household_member_name: "John",
      plan_type: "DIRECT",
      units_held: "100.00",
      average_nav: "50.00",
      current_nav: "75.00",
      amount_invested: "5000.00",
      current_value: "7500.00",
      current_profit_total: "2500.00",
      realized_gain: "0.00",
      unrealized_gain: "2500.00",
      today_gain: "50.00",
    },
  ]);
  vi.mocked(api.getMemberAllocation).mockResolvedValue({
    by_asset_class: [{ label: "Equity", current_value: "7500.00", percentage: 100 }],
    by_amc: [{ label: "HDFC", current_value: "7500.00", percentage: 100 }],
    total_value: "7500.00",
  });
  vi.mocked(api.getMemberSips).mockResolvedValue([
    {
      scheme_id: "scheme-101",
      scheme_name: "HDFC Top 100 Fund",
      household_member_id: "m-1",
      household_member_name: "John",
      sip_date: "2026-08-05",
      sip_amount: "5000.00",
      next_due_date: "2026-09-05",
    },
  ]);
  vi.mocked(api.getMemberSipsMonthly).mockResolvedValue([
    {
      scheme_id: "scheme-101",
      scheme_name: "HDFC Top 100 Fund",
      household_member_id: "m-1",
      household_member_name: "John",
      date: "2026-08-05",
      amount: "5000.00",
    },
  ]);

  render(<DashboardView viewMode="member" memberId="m-1" />);

  await waitFor(() => {
    expect(screen.getByTestId("upcoming-sips")).toBeInTheDocument();
  });

  expect(api.getMemberSipsMonthly).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "This Month" }));

  await waitFor(() => {
    expect(api.getMemberSipsMonthly).toHaveBeenCalledWith(
      "m-1",
      expect.any(Number),
      expect.any(Number),
      expect.anything()
    );
  });

  const sipSection = screen.getByTestId("upcoming-sips");
  await waitFor(() => {
    expect(within(sipSection).getByText("₹5,000")).toBeInTheDocument();
  });
});

it("navigates to the previous month and refetches monthly SIPs", async () => {
  vi.mocked(api.getMemberHoldings).mockResolvedValue([
    {
      scheme_id: "scheme-101",
      scheme_name: "HDFC Top 100 Fund",
      amc_name: "HDFC Mutual Fund",
      household_member_id: "m-1",
      household_member_name: "John",
      plan_type: "DIRECT",
      units_held: "100.00",
      average_nav: "50.00",
      current_nav: "75.00",
      amount_invested: "5000.00",
      current_value: "7500.00",
      current_profit_total: "2500.00",
      realized_gain: "0.00",
      unrealized_gain: "2500.00",
      today_gain: "50.00",
    },
  ]);
  vi.mocked(api.getMemberAllocation).mockResolvedValue({
    by_asset_class: [{ label: "Equity", current_value: "7500.00", percentage: 100 }],
    by_amc: [{ label: "HDFC", current_value: "7500.00", percentage: 100 }],
    total_value: "7500.00",
  });
  vi.mocked(api.getMemberSips).mockResolvedValue([
    {
      scheme_id: "scheme-101",
      scheme_name: "HDFC Top 100 Fund",
      household_member_id: "m-1",
      household_member_name: "John",
      sip_date: "2026-08-05",
      sip_amount: "5000.00",
      next_due_date: "2026-09-05",
    },
  ]);
  vi.mocked(api.getMemberSipsMonthly).mockResolvedValue([]);

  render(<DashboardView viewMode="member" memberId="m-1" />);

  await waitFor(() => {
    expect(screen.getByTestId("upcoming-sips")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByRole("button", { name: "This Month" }));
  await waitFor(() => {
    expect(api.getMemberSipsMonthly).toHaveBeenCalledTimes(1);
  });

  fireEvent.click(screen.getByRole("button", { name: "Previous month" }));

  await waitFor(() => {
    expect(api.getMemberSipsMonthly).toHaveBeenCalledTimes(2);
  });

  const [, callArgs] = vi.mocked(api.getMemberSipsMonthly).mock.calls;
  const [firstCallArgs] = vi.mocked(api.getMemberSipsMonthly).mock.calls;
  expect(callArgs[1]).not.toBe(firstCallArgs[1]); // year or month changed
});
```

- [ ] **Step 4: Run tests, verify they fail**

Run: `cd frontend && npx vitest run src/features/dashboard/DashboardView.test.tsx`
Expected: FAIL — `getMemberSipsMonthly` mock not called (tab switcher doesn't exist
yet if Task 7 weren't already done; since Task 7 IS already done at this point in
plan order, these should actually already pass here — this task's real "red" state
is verifying the tests are correctly written, so instead: temporarily comment out
the `onClick` handlers in `DashboardView.tsx`'s tab buttons, confirm both new tests
fail, then restore — same "prove the test can fail" discipline as Task 4).

- [ ] **Step 5: Run tests, verify they pass**

Run: `cd frontend && npx vitest run src/features/dashboard/DashboardView.test.tsx`
Expected: PASS — all tests in the file, including the 2 new ones and the 2 updated
ones.

- [ ] **Step 6: Fix `MainDashboardFlow.test.tsx`'s separate mock factory**

`DashboardView.tsx` now has a static import of `getMemberSipsMonthly` and
`getAggregateSipsMonthly` from `./api`. `MainDashboardFlow.test.tsx` has its own
independent `vi.mock("./api", ...)` factory that does not declare them —
exactly the same "No export is defined on mock" break encountered earlier this
session when `getAggregateSips`/`getMemberSips` were first added. Fix it the same
way: add both functions to that file's mock factory and default resolved values in
its `beforeEach`.

In `frontend/src/features/dashboard/MainDashboardFlow.test.tsx`, modify the
`vi.mock("./api", ...)` call:

```typescript
vi.mock("./api", () => ({
  getMemberHoldings: vi.fn(),
  getMemberAllocation: vi.fn(),
  getMemberSips: vi.fn(),
  getMemberSipsMonthly: vi.fn(),
  getAggregateHoldings: vi.fn(),
  getAggregateAllocation: vi.fn(),
  getAggregateSips: vi.fn(),
  getAggregateSipsMonthly: vi.fn(),
  getDistributorComparison: vi.fn(),
}));
```

And in its `beforeEach`:

```typescript
vi.mocked(dashboardApi.getMemberSipsMonthly).mockResolvedValue([]);
vi.mocked(dashboardApi.getAggregateSipsMonthly).mockResolvedValue({ members: [], sips: [] });
```

- [ ] **Step 7: Run the full frontend suite**

Run: `cd frontend && npx vitest run`
Expected: PASS, no regressions (allow for the pre-existing sandbox flakiness noted
in `Docs/orchestration/analytics-phase2-frontend-log.md` — different unrelated
files occasionally crash on `vitest` worker-pool timeouts under full parallelism;
re-run any such failure once before treating it as real).

- [ ] **Step 8: Type-check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/features/dashboard/DashboardView.test.tsx frontend/src/features/dashboard/MainDashboardFlow.test.tsx
git commit -m "test: cover This Month SIP tab, month navigation, and fix mock factory drift"
```
