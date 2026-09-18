# Phase 3 — Main Dashboard Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend for PRD-03's Main Dashboard — FIFO-based holdings
computation, allocation, active-SIP detection, cash flow, monthly value
snapshots, and family aggregation — as read-mostly endpoints over data
already parsed and stored by Phase 1's Import Service.

**Architecture:** Seven service modules under
`backend/app/services/dashboard/`, each owning one concern and (except
`nav.py`, foundational and route-less) exposing one or more `GET` routes in
`backend/app/api/dashboard.py`. Every compute function is parameterized by
`household_member_ids: list[uuid.UUID]` — the same function serves both a
single-member view and a family aggregate, per PRD-03's Goal #3. No database
migrations: every table this phase touches (`folios`, `transactions`,
`nav_history`, `portfolio_snapshots`) already exists from Phase 0.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pydantic, `httpx` (already a
dependency, used by Import Service's `mfapi.in` client), pytest — all
already in place, no new dependencies.

## Global Constraints

- **`Decimal`, never `float`**, for every money/units/NAV value, at every
  layer — computation, storage, and (as a string, matching Import Service's
  existing `TransactionPreview.amount: str | None` convention) API
  response serialization.
- **Cost-basis methodology: FIFO.** First lot purchased is the first lot
  considered redeemed when computing realized vs. unrealized gain.
- **One implementation per concern, parameterized by
  `household_member_ids: list[uuid.UUID]`** — never a separate code path
  for "family" vs. "per-member." A per-member route passes a single-item
  list; an aggregate route passes every member the authenticated user owns.
- **NAV is on-demand fetch-and-cache**, not a scheduled job (that's
  deployment-phase infrastructure, out of scope here). `nav.py` is a
  separate client from Import Service's `MfApiClient` — that client's own
  docstring already scopes it to scheme metadata, not valuation history.
- **Every route requires `Depends(get_current_user)`.** Per-member routes
  additionally check ownership via the existing
  `get_household_member_for_user(db, user.id, member_id)` — a 404 for a
  member that doesn't exist or belongs to someone else, matching the
  pattern already established for `/imports/confirm`. Aggregate routes need
  no separate ownership check — they're scoped to the caller's own members
  via the existing `list_household_members(db, user.id)`.
- **SIP active window: 40 days.**
- **STT/stamp duty/misc/segregation transactions have no effect on units or
  cost basis** in this phase's FIFO engine — they're separate transaction
  rows in this schema (not modifiers on a purchase row), treated as
  informational/cash-flow-only. A stated simplification, not an oversight —
  see the design spec's Open Items.
- **Cash flow excludes `switch_in`/`switch_out`** — intra-portfolio
  movements, not money entering or leaving the platform, per FR-7's own
  wording.
- **Allocation lives in Dashboard Service**, computed directly from
  `folios`/`transactions`/`schemes` this service already owns — not
  deferred to the (unbuilt) Analytics service, correcting a documentation
  slip in the TDD's endpoint-service mapping.
- **A fully-redeemed scheme (zero units held) drops out of the holdings
  table** but stays visible in cash-flow and snapshot views (historical,
  not point-in-time).
- **A snapshot month before a member's first transaction produces no data
  point** — never a zero or an error.

---

### Task 1: On-demand NAV fetch-and-cache (`nav.py`)

**Files:**
- Create: `backend/app/services/dashboard/nav.py`
- Test: `backend/tests/services/dashboard/test_nav.py`

**Interfaces:**
- Produces: `async def get_nav_on_or_before(db: Session, scheme: Scheme, on_date: date) -> tuple[Decimal, date] | None`
  — most recent NAV on or before `on_date`, fetching+caching from `mfapi.in`
  if nothing usable is cached yet. Returns `None` only if no NAV is
  available even after a fetch attempt.
- Produces: `def get_previous_nav_from_cache(db: Session, scheme_id: uuid.UUID, before_date: date) -> tuple[Decimal, date] | None`
  — most recent cached NAV strictly before `before_date`, reading
  `nav_history` only (no fetch — callers use this right after
  `get_nav_on_or_before` has already ensured the cache is populated for
  that scheme).
- Consumed by: Tasks 2 (holdings) and 6 (snapshots).

This is the one new external integration in this phase — foundational,
built and tested standalone before anything consumes it.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/dashboard/test_nav.py
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.reference import Scheme
from app.services.dashboard.nav import get_nav_on_or_before, get_previous_nav_from_cache


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autoflush=False, bind=engine)()


def _scheme(db, amfi_code="125497"):
    scheme = Scheme(
        id=uuid.uuid4(), amfi_code=amfi_code, isin="INF123", name="HDFC Flexi Cap Fund",
        amc_name="HDFC AMC", sebi_category="Equity Scheme - Flexi Cap Fund",
    )
    db.add(scheme)
    db.commit()
    return scheme


def _mfapi_payload(entries: list[tuple[str, str]]) -> dict:
    return {"meta": {}, "data": [{"date": d, "nav": n} for d, n in entries]}


def test_fetches_and_caches_on_first_call():
    db = _session()
    scheme = _scheme(db)
    payload = _mfapi_payload([("15-01-2024", "50.1234"), ("14-01-2024", "49.9876")])

    with patch(
        "app.services.dashboard.nav._fetch_nav_history",
        new=AsyncMock(return_value=[(date(2024, 1, 15), Decimal("50.1234")), (date(2024, 1, 14), Decimal("49.9876"))]),
    ):
        import asyncio
        result = asyncio.run(get_nav_on_or_before(db, scheme, date(2024, 1, 15)))

    assert result == (Decimal("50.1234"), date(2024, 1, 15))

    from app.models.reference import NavHistory
    cached = db.query(NavHistory).filter_by(scheme_id=scheme.id).all()
    assert len(cached) == 2


def test_uses_cache_without_fetching_for_a_past_date():
    import asyncio
    db = _session()
    scheme = _scheme(db)

    from app.models.reference import NavHistory
    db.add(NavHistory(scheme_id=scheme.id, date=date(2024, 1, 10), nav=Decimal("45.0000")))
    db.commit()

    with patch("app.services.dashboard.nav._fetch_nav_history", new=AsyncMock(side_effect=AssertionError("should not fetch"))):
        result = asyncio.run(get_nav_on_or_before(db, scheme, date(2024, 1, 10)))

    assert result == (Decimal("45.0000"), date(2024, 1, 10))


def test_falls_back_to_most_recent_before_requested_date_when_exact_date_missing():
    import asyncio
    db = _session()
    scheme = _scheme(db)

    from app.models.reference import NavHistory
    db.add(NavHistory(scheme_id=scheme.id, date=date(2024, 1, 5), nav=Decimal("40.0000")))
    db.commit()

    # Requesting a past date with an older cached row present but nothing
    # newer — falls back to the older row without fetching (the requested
    # date isn't "today", so there's no reason to expect a fresher fetch to
    # help).
    with patch("app.services.dashboard.nav._fetch_nav_history", new=AsyncMock(side_effect=AssertionError("should not fetch"))):
        result = asyncio.run(get_nav_on_or_before(db, scheme, date(2024, 1, 8)))

    assert result == (Decimal("40.0000"), date(2024, 1, 5))


def test_degrades_gracefully_on_mfapi_outage_with_no_cache():
    import asyncio
    db = _session()
    scheme = _scheme(db)

    with patch("app.services.dashboard.nav._fetch_nav_history", new=AsyncMock(side_effect=httpx.ConnectError("boom"))):
        result = asyncio.run(get_nav_on_or_before(db, scheme, date(2024, 1, 15)))

    assert result is None


def test_degrades_to_stale_cache_on_mfapi_outage_when_something_is_cached():
    import asyncio
    db = _session()
    scheme = _scheme(db)

    from app.models.reference import NavHistory
    db.add(NavHistory(scheme_id=scheme.id, date=date(2024, 1, 1), nav=Decimal("30.0000")))
    db.commit()

    # Requesting "today" with only an old cached row forces a fetch attempt
    # (today's row might exist now); on outage, fall back to what's cached.
    with patch("app.services.dashboard.nav._fetch_nav_history", new=AsyncMock(side_effect=httpx.ConnectError("boom"))):
        result = asyncio.run(get_nav_on_or_before(db, scheme, date.today()))

    assert result == (Decimal("30.0000"), date(2024, 1, 1))


def test_get_previous_nav_from_cache_reads_strictly_before():
    db = _session()
    scheme = _scheme(db)

    from app.models.reference import NavHistory
    db.add(NavHistory(scheme_id=scheme.id, date=date(2024, 1, 10), nav=Decimal("50.0000")))
    db.add(NavHistory(scheme_id=scheme.id, date=date(2024, 1, 15), nav=Decimal("55.0000")))
    db.commit()

    result = get_previous_nav_from_cache(db, scheme.id, date(2024, 1, 15))
    assert result == (Decimal("50.0000"), date(2024, 1, 10))


def test_get_previous_nav_from_cache_returns_none_when_nothing_earlier():
    db = _session()
    scheme = _scheme(db)
    assert get_previous_nav_from_cache(db, scheme.id, date(2024, 1, 1)) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_nav.py -v`
Expected: FAIL — `app.services.dashboard.nav` doesn't exist yet.

- [ ] **Step 3: Implement `nav.py`**

```python
# backend/app/services/dashboard/nav.py
"""On-demand NAV fetch-and-cache — a separate client from Import Service's
MfApiClient (import_/enrich.py), which explicitly scopes itself to scheme
metadata, not valuation history (see its module docstring). This phase's
real production plan is a daily EventBridge-scheduled refresh job
(TDD-Unifolio.md Background Jobs), but that's deployment-phase
infrastructure — this module is the local-dev-first stand-in: fetch a
scheme's NAV the first time it's needed, cache it in `nav_history`, reuse
the cache after that.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from app.models.reference import NavHistory, Scheme

MFAPI_BASE = "https://api.mfapi.in"


async def _fetch_nav_history(amfi_code: str) -> list[tuple[date, Decimal]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{MFAPI_BASE}/mf/{amfi_code}")
        resp.raise_for_status()
        payload = resp.json()

    rows: list[tuple[date, Decimal]] = []
    for entry in payload.get("data", []):
        # mfapi.in dates are DD-MM-YYYY.
        parsed_date = datetime.strptime(entry["date"], "%d-%m-%Y").date()
        rows.append((parsed_date, Decimal(entry["nav"])))
    return rows


def _upsert_nav_history(db: Session, scheme_id: uuid.UUID, rows: list[tuple[date, Decimal]]) -> None:
    existing_dates = {d for (d,) in db.query(NavHistory.date).filter_by(scheme_id=scheme_id).all()}
    for row_date, nav in rows:
        if row_date not in existing_dates:
            db.add(NavHistory(scheme_id=scheme_id, date=row_date, nav=nav))
    db.commit()


def _latest_cached_on_or_before(db: Session, scheme_id: uuid.UUID, on_date: date) -> NavHistory | None:
    return (
        db.query(NavHistory)
        .filter(NavHistory.scheme_id == scheme_id, NavHistory.date <= on_date)
        .order_by(NavHistory.date.desc())
        .first()
    )


async def get_nav_on_or_before(db: Session, scheme: Scheme, on_date: date) -> tuple[Decimal, date] | None:
    """Most recent NAV on or before `on_date`. Returns `(nav, actual_date)`,
    or `None` if nothing is available even after attempting a fetch.

    A cached row exactly on a past `on_date` is trusted without fetching —
    there's no reason to expect a fresher fetch to change history. A cached
    row on `on_date == date.today()` is NOT trusted without at least
    attempting a fetch, since today's NAV may not have been published yet
    when it was last cached (FR-3's "not yet published" case is normal, not
    an error, but this function should still try to get the freshest data
    available)."""
    cached = _latest_cached_on_or_before(db, scheme.id, on_date)
    have_trustworthy_cache = cached is not None and (cached.date == on_date or on_date != date.today())
    if have_trustworthy_cache:
        return cached.nav, cached.date

    try:
        rows = await _fetch_nav_history(scheme.amfi_code)
    except httpx.HTTPError:
        return (cached.nav, cached.date) if cached else None

    _upsert_nav_history(db, scheme.id, rows)
    refreshed = _latest_cached_on_or_before(db, scheme.id, on_date)
    return (refreshed.nav, refreshed.date) if refreshed else None


def get_previous_nav_from_cache(db: Session, scheme_id: uuid.UUID, before_date: date) -> tuple[Decimal, date] | None:
    row = (
        db.query(NavHistory)
        .filter(NavHistory.scheme_id == scheme_id, NavHistory.date < before_date)
        .order_by(NavHistory.date.desc())
        .first()
    )
    return (row.nav, row.date) if row else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_nav.py -v`
Expected: PASS (7/7)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dashboard/nav.py backend/tests/services/dashboard/test_nav.py
git commit -m "feat: add on-demand NAV fetch-and-cache for Dashboard Service"
```

---

### Task 2: FIFO holdings engine (`holdings.py`) + `GET /household-members/{id}/holdings`

**Files:**
- Create: `backend/app/services/dashboard/holdings.py`
- Modify: `backend/app/services/dashboard/schemas.py`
- Modify: `backend/app/api/dashboard.py`
- Test: `backend/tests/services/dashboard/test_holdings.py`
- Test: `backend/tests/api/test_dashboard_holdings_route.py`

**Interfaces:**
- Consumes: `get_nav_on_or_before`, `get_previous_nav_from_cache` from `./nav`
  (Task 1); `get_household_member_for_user` from `./household_members`
  (existing).
- Produces: `_process_folio_lots(transactions: list[Transaction]) -> tuple[Decimal, Decimal, Decimal]`
  (units_held, cost_basis, realized_gain) — reused by Task 6 (snapshots).
- Produces: `async def compute_holdings(db: Session, household_member_ids: list[uuid.UUID]) -> list[HoldingRow]`
  — reused by Task 7 (aggregate).
- Produces: `HoldingRow` Pydantic schema in `schemas.py` — reused by Task 7.

This is the core, highest-risk task in the plan — the FIFO lot-tracking
engine gets hand-built known-answer fixtures, not just round-trip tests.

- [ ] **Step 1: Write the failing tests for `_process_folio_lots` (the known-answer tests)**

```python
# backend/tests/services/dashboard/test_holdings.py
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import PlanType, Relationship, TransactionType
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.models.user import HouseholdMember, User
from app.services.dashboard.holdings import _process_folio_lots, compute_holdings


def _txn(type_, on_date, amount, units, nav) -> Transaction:
    return Transaction(
        id=uuid.uuid4(), folio_id=uuid.uuid4(), import_id=uuid.uuid4(),
        type=type_, date=on_date, amount=amount, units=units, nav=nav,
    )


def test_process_folio_lots_simple_purchase_no_redemption():
    transactions = [
        _txn(TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000")),
    ]
    units_held, cost_basis, realized_gain = _process_folio_lots(transactions)
    assert units_held == Decimal("100.000")
    assert cost_basis == Decimal("5000.00")
    assert realized_gain == Decimal("0")


def test_process_folio_lots_fifo_partial_redemption_across_two_lots():
    """Known-answer test, hand-computed: lot A (100u @ NAV 50), lot B
    (200u @ NAV 60). Redeem 150u @ NAV 80 — FIFO consumes all of A (100u)
    then 50u from B.
    Expected realized_gain = 100*(80-50) + 50*(80-60) = 3000 + 1000 = 4000.
    Expected remaining: lot B has 150u left @ NAV 60 -> cost_basis = 9000,
    units_held = 150."""
    transactions = [
        _txn(TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000")),
        _txn(TransactionType.PURCHASE, date(2024, 6, 1), Decimal("12000.00"), Decimal("200.000"), Decimal("60.0000")),
        _txn(TransactionType.REDEMPTION, date(2024, 9, 1), Decimal("12000.00"), Decimal("150.000"), Decimal("80.0000")),
    ]
    units_held, cost_basis, realized_gain = _process_folio_lots(transactions)
    assert units_held == Decimal("150.000")
    assert cost_basis == Decimal("9000.00")
    assert realized_gain == Decimal("4000.00")


def test_process_folio_lots_full_redemption_leaves_zero_units():
    transactions = [
        _txn(TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000")),
        _txn(TransactionType.REDEMPTION, date(2024, 3, 1), Decimal("6000.00"), Decimal("100.000"), Decimal("60.0000")),
    ]
    units_held, cost_basis, realized_gain = _process_folio_lots(transactions)
    assert units_held == Decimal("0")
    assert cost_basis == Decimal("0")
    assert realized_gain == Decimal("1000.00")


def test_process_folio_lots_dividend_payout_has_no_effect_on_units():
    transactions = [
        _txn(TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000")),
        _txn(TransactionType.DIVIDEND_PAYOUT, date(2024, 4, 1), Decimal("200.00"), Decimal("0.000"), Decimal("52.0000")),
    ]
    units_held, cost_basis, realized_gain = _process_folio_lots(transactions)
    assert units_held == Decimal("100.000")
    assert cost_basis == Decimal("5000.00")
    assert realized_gain == Decimal("0")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_holdings.py -v`
Expected: FAIL — `app.services.dashboard.holdings` doesn't exist yet.

- [ ] **Step 3: Implement `_process_folio_lots` in `holdings.py`**

```python
# backend/app/services/dashboard/holdings.py
"""FIFO holdings engine — the core of the Main Dashboard backend. First lot
purchased is the first lot considered redeemed, matching Indian
capital-gains convention and how CAMS/KFintech CAS statements themselves
report gains.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.enums import PlanType, TransactionType
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.models.user import HouseholdMember
from app.services.dashboard.nav import get_nav_on_or_before, get_previous_nav_from_cache
from app.services.dashboard.schemas import HoldingRow

_LOT_ADDING_TYPES = {TransactionType.PURCHASE, TransactionType.PURCHASE_SIP, TransactionType.SWITCH_IN, TransactionType.DIVIDEND_REINVEST}
_LOT_CONSUMING_TYPES = {TransactionType.REDEMPTION, TransactionType.SWITCH_OUT}


@dataclass
class _Lot:
    units: Decimal
    nav: Decimal


def _process_folio_lots(transactions: list[Transaction]) -> tuple[Decimal, Decimal, Decimal]:
    """Returns (units_held, cost_basis, realized_gain) for one folio's
    transaction history, in FIFO order. `transactions` must already be
    sorted chronologically by the caller.

    STT/stamp_duty/misc/segregation transactions have no effect here — a
    stated simplification, see the design spec's Open Items."""
    lots: list[_Lot] = []
    realized_gain = Decimal("0")

    for txn in transactions:
        if txn.type in _LOT_ADDING_TYPES:
            lots.append(_Lot(units=txn.units, nav=txn.nav))
        elif txn.type in _LOT_CONSUMING_TYPES:
            remaining = txn.units
            while remaining > 0 and lots:
                lot = lots[0]
                take = min(lot.units, remaining)
                realized_gain += take * (txn.nav - lot.nav)
                lot.units -= take
                remaining -= take
                if lot.units == 0:
                    lots.pop(0)

    units_held = sum((lot.units for lot in lots), Decimal("0"))
    cost_basis = sum((lot.units * lot.nav for lot in lots), Decimal("0"))
    return units_held, cost_basis, realized_gain
```

- [ ] **Step 4: Run the known-answer tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_holdings.py -v`
Expected: PASS (4/4)

- [ ] **Step 5: Add `HoldingRow` to `schemas.py`**

```python
# Add to backend/app/services/dashboard/schemas.py
from datetime import date
from app.models.enums import PlanType


class HoldingRow(BaseModel):
    scheme_id: str
    scheme_name: str
    amc_name: str
    household_member_id: str
    household_member_name: str
    plan_type: PlanType
    units_held: str
    average_nav: str | None
    current_nav: str
    current_nav_date: date
    amount_invested: str
    current_value: str
    current_profit_total: str
    realized_gain: str
    unrealized_gain: str
    today_gain: str
```

Add the two new import lines to the existing import block at the top of
`schemas.py`; add the class at the end of the file. This is the convention
every later task's "Add to `schemas.py`" step follows too — new imports go
to the top (skip any import already present from an earlier task), new
classes go to the end.

- [ ] **Step 6: Write the failing test for `compute_holdings` (folio-merging + NAV integration + drop-when-fully-redeemed)**

Append to `backend/tests/services/dashboard/test_holdings.py`:

```python
def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autoflush=False, bind=engine)()


def _household_member(db, name="Self"):
    user = User(id=uuid.uuid4(), phone_number=f"+9199999{uuid.uuid4().hex[:5]}", created_at=datetime.now(timezone.utc))
    db.add(user)
    db.flush()
    member = HouseholdMember(id=uuid.uuid4(), user_id=user.id, name=name, relationship=Relationship.SELF, created_at=datetime.now(timezone.utc))
    db.add(member)
    db.commit()
    return member


def _scheme(db, name="HDFC Flexi Cap Fund", amfi_code=None):
    scheme = Scheme(
        id=uuid.uuid4(), amfi_code=amfi_code or uuid.uuid4().hex[:6], isin="INF123", name=name,
        amc_name="HDFC AMC", sebi_category="Equity Scheme - Flexi Cap Fund",
    )
    db.add(scheme)
    db.commit()
    return scheme


def _folio(db, member, scheme, folio_number="123/45", plan_type=PlanType.DIRECT):
    folio = Folio(id=uuid.uuid4(), household_member_id=member.id, scheme_id=scheme.id, folio_number=folio_number, plan_type=plan_type)
    db.add(folio)
    db.commit()
    return folio


def _persisted_txn(db, folio, type_, on_date, amount, units, nav):
    txn = Transaction(
        id=uuid.uuid4(), folio_id=folio.id, import_id=uuid.uuid4(),
        type=type_, date=on_date, amount=amount, units=units, nav=nav,
    )
    db.add(txn)
    db.commit()
    return txn


def test_compute_holdings_returns_current_value_and_gains_from_nav():
    import asyncio

    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    _persisted_txn(db, folio, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))

    with patch(
        "app.services.dashboard.holdings.get_nav_on_or_before",
        new=AsyncMock(return_value=(Decimal("60.0000"), date(2024, 6, 1))),
    ), patch(
        "app.services.dashboard.holdings.get_previous_nav_from_cache",
        return_value=(Decimal("59.0000"), date(2024, 5, 31)),
    ):
        rows = asyncio.run(compute_holdings(db, [member.id]))

    assert len(rows) == 1
    row = rows[0]
    assert row.units_held == "100.000"
    assert Decimal(row.amount_invested) == Decimal("5000.00")
    assert Decimal(row.current_value) == Decimal("6000.00")  # 100 * 60
    assert Decimal(row.unrealized_gain) == Decimal("1000.00")  # 6000 - 5000
    assert Decimal(row.today_gain) == Decimal("100.00")  # (60-59) * 100
    assert row.plan_type == PlanType.DIRECT


def test_compute_holdings_merges_two_folios_of_the_same_scheme():
    import asyncio

    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio_a = _folio(db, member, scheme, folio_number="AAA")
    folio_b = _folio(db, member, scheme, folio_number="BBB")
    _persisted_txn(db, folio_a, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))
    _persisted_txn(db, folio_b, TransactionType.PURCHASE, date(2024, 2, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))

    with patch(
        "app.services.dashboard.holdings.get_nav_on_or_before",
        new=AsyncMock(return_value=(Decimal("60.0000"), date(2024, 6, 1))),
    ), patch(
        "app.services.dashboard.holdings.get_previous_nav_from_cache",
        return_value=None,
    ):
        rows = asyncio.run(compute_holdings(db, [member.id]))

    assert len(rows) == 1
    assert rows[0].units_held == "200.000"
    assert Decimal(rows[0].amount_invested) == Decimal("10000.00")


def test_compute_holdings_drops_fully_redeemed_scheme():
    import asyncio

    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    _persisted_txn(db, folio, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))
    _persisted_txn(db, folio, TransactionType.REDEMPTION, date(2024, 3, 1), Decimal("6000.00"), Decimal("100.000"), Decimal("60.0000"))

    rows = asyncio.run(compute_holdings(db, [member.id]))
    assert rows == []


def test_compute_holdings_across_multiple_members_tags_each_row():
    import asyncio

    db = _session()
    member_a = _household_member(db, name="Mom")
    member_b = _household_member(db, name="Dad")
    scheme = _scheme(db)
    folio_a = _folio(db, member_a, scheme)
    folio_b = _folio(db, member_b, scheme)
    _persisted_txn(db, folio_a, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))
    _persisted_txn(db, folio_b, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("3000.00"), Decimal("60.000"), Decimal("50.0000"))

    with patch(
        "app.services.dashboard.holdings.get_nav_on_or_before",
        new=AsyncMock(return_value=(Decimal("50.0000"), date(2024, 1, 1))),
    ), patch(
        "app.services.dashboard.holdings.get_previous_nav_from_cache",
        return_value=None,
    ):
        rows = asyncio.run(compute_holdings(db, [member_a.id, member_b.id]))

    assert len(rows) == 2
    names = {row.household_member_name for row in rows}
    assert names == {"Mom", "Dad"}
```

- [ ] **Step 7: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_holdings.py -v`
Expected: FAIL — `compute_holdings` doesn't exist yet.

- [ ] **Step 8: Implement `compute_holdings`**

Append to `backend/app/services/dashboard/holdings.py`:

```python
async def compute_holdings(db: Session, household_member_ids: list[uuid.UUID]) -> list[HoldingRow]:
    if not household_member_ids:
        return []

    members = {
        m.id: m
        for m in db.query(HouseholdMember).filter(HouseholdMember.id.in_(household_member_ids)).all()
    }
    folios = db.query(Folio).filter(Folio.household_member_id.in_(household_member_ids)).all()

    grouped: dict[tuple[uuid.UUID, uuid.UUID], list[Folio]] = defaultdict(list)
    for folio in folios:
        grouped[(folio.household_member_id, folio.scheme_id)].append(folio)

    rows: list[HoldingRow] = []
    for (member_id, scheme_id), member_folios in grouped.items():
        scheme = db.get(Scheme, scheme_id)
        total_units = Decimal("0")
        total_cost = Decimal("0")
        total_realized = Decimal("0")
        # First-encountered folio's plan_type represents the merged row — a
        # stated simplification for the rare case of the same scheme held
        # via folios with different plan types (e.g. one direct, one
        # regular). Distributor comparison (a later, separate phase) is
        # where folio-level plan_type detail becomes visible.
        plan_type = member_folios[0].plan_type

        for folio in member_folios:
            transactions = (
                db.query(Transaction)
                .filter(Transaction.folio_id == folio.id)
                .order_by(Transaction.date, Transaction.id)
                .all()
            )
            units_held, cost_basis, realized_gain = _process_folio_lots(transactions)
            total_units += units_held
            total_cost += cost_basis
            total_realized += realized_gain

        if total_units == 0:
            continue

        nav_result = await get_nav_on_or_before(db, scheme, date.today())
        if nav_result is None:
            continue
        current_nav, current_nav_date = nav_result
        previous = get_previous_nav_from_cache(db, scheme.id, current_nav_date)
        previous_nav = previous[0] if previous else current_nav

        current_value = total_units * current_nav
        unrealized_gain = current_value - total_cost
        current_profit_total = total_realized + unrealized_gain
        today_gain = (current_nav - previous_nav) * total_units
        average_nav = (total_cost / total_units) if total_units else None

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
                current_nav=str(current_nav),
                current_nav_date=current_nav_date,
                amount_invested=str(total_cost),
                current_value=str(current_value),
                current_profit_total=str(current_profit_total),
                realized_gain=str(total_realized),
                unrealized_gain=str(unrealized_gain),
                today_gain=str(today_gain),
            )
        )
    return rows
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_holdings.py -v`
Expected: PASS (8/8)

- [ ] **Step 10: Write the failing route test**

```python
# backend/tests/api/test_dashboard_holdings_route.py
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch


def _authed_headers_and_member(client, phone: str) -> tuple[dict[str, str], str]:
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    member = client.post("/household-members", json={"name": "Self", "relationship": "self"}, headers=headers).json()
    return headers, member["id"]


def test_holdings_route_requires_auth(client):
    response = client.get("/household-members/00000000-0000-0000-0000-000000000000/holdings")
    assert response.status_code == 401


def test_holdings_route_404s_for_another_users_member(client):
    _, other_member_id = _authed_headers_and_member(client, "+919000000001")
    headers, _ = _authed_headers_and_member(client, "+919000000002")

    response = client.get(f"/household-members/{other_member_id}/holdings", headers=headers)
    assert response.status_code == 404


def test_holdings_route_returns_empty_list_for_member_with_no_folios(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000003")
    response = client.get(f"/household-members/{member_id}/holdings", headers=headers)
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 11: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_dashboard_holdings_route.py -v`
Expected: FAIL — the route doesn't exist yet (404 for the route itself, not the 401/404 the tests expect for other reasons).

- [ ] **Step 12: Add the route to `dashboard.py`**

```python
# Add imports to backend/app/api/dashboard.py
import uuid
from app.services.dashboard.holdings import compute_holdings
from app.services.dashboard.schemas import HoldingRow

# Add route
@router.get("/household-members/{member_id}/holdings", response_model=list[HoldingRow])
async def get_member_holdings(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if get_household_member_for_user(db, user.id, member_id) is None:
        raise HTTPException(status_code=404, detail="Household member not found.")
    return await compute_holdings(db, [member_id])
```

This needs two additional imports already-present-elsewhere-in-the-file
patterns: `from fastapi import HTTPException` and
`from app.services.dashboard.household_members import get_household_member_for_user`
(alongside the existing `create_household_member`, `list_household_members`
import). Add both to the existing import block at the top of the file.

- [ ] **Step 13: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_dashboard_holdings_route.py -v`
Expected: PASS (3/3)

- [ ] **Step 14: Run the full backend suite**

Run: `cd backend && .venv/bin/pytest -m "not postgres" -v`
Expected: All pass.

- [ ] **Step 15: Commit**

```bash
git add backend/app/services/dashboard/holdings.py backend/app/services/dashboard/schemas.py backend/app/api/dashboard.py backend/tests/services/dashboard/test_holdings.py backend/tests/api/test_dashboard_holdings_route.py
git commit -m "feat: add FIFO holdings engine and GET /household-members/{id}/holdings"
```

---

### Task 3: Allocation summary (`allocation.py`) + `GET /household-members/{id}/allocation`

**Files:**
- Create: `backend/app/services/dashboard/allocation.py`
- Modify: `backend/app/services/dashboard/schemas.py`
- Modify: `backend/app/api/dashboard.py`
- Test: `backend/tests/services/dashboard/test_allocation.py`
- Test: `backend/tests/api/test_dashboard_allocation_route.py`

**Interfaces:**
- Consumes: `compute_holdings` from `./holdings` (Task 2) — allocation
  groups already-computed holdings, it doesn't recompute anything.
- Produces: `async def compute_allocation(db: Session, household_member_ids: list[uuid.UUID]) -> AllocationSummary`
  — reused by Task 7 (aggregate).
- Produces: `AllocationBucket`, `AllocationSummary` schemas in `schemas.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/dashboard/test_allocation.py
import asyncio
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import PlanType, Relationship, TransactionType
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.models.user import HouseholdMember, User
from app.services.dashboard.allocation import compute_allocation


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autoflush=False, bind=engine)()


def _household_member(db):
    user = User(id=uuid.uuid4(), phone_number=f"+9199999{uuid.uuid4().hex[:5]}", created_at=datetime.now(timezone.utc))
    db.add(user)
    db.flush()
    member = HouseholdMember(id=uuid.uuid4(), user_id=user.id, name="Self", relationship=Relationship.SELF, created_at=datetime.now(timezone.utc))
    db.add(member)
    db.commit()
    return member


def _scheme(db, amc_name, sebi_category):
    scheme = Scheme(id=uuid.uuid4(), amfi_code=uuid.uuid4().hex[:6], isin="INF123", name="Test Fund", amc_name=amc_name, sebi_category=sebi_category)
    db.add(scheme)
    db.commit()
    return scheme


def _folio_with_purchase(db, member, scheme, amount, units, nav):
    folio = Folio(id=uuid.uuid4(), household_member_id=member.id, scheme_id=scheme.id, folio_number=uuid.uuid4().hex[:6], plan_type=PlanType.DIRECT)
    db.add(folio)
    db.commit()
    db.add(Transaction(id=uuid.uuid4(), folio_id=folio.id, import_id=uuid.uuid4(), type=TransactionType.PURCHASE, date=date(2024, 1, 1), amount=amount, units=units, nav=nav))
    db.commit()
    return folio


def test_compute_allocation_groups_by_asset_class_and_amc():
    db = _session()
    member = _household_member(db)
    equity_scheme = _scheme(db, amc_name="HDFC AMC", sebi_category="Equity Scheme - Flexi Cap Fund")
    debt_scheme = _scheme(db, amc_name="ICICI AMC", sebi_category="Debt Scheme - Liquid Fund")
    _folio_with_purchase(db, member, equity_scheme, Decimal("6000.00"), Decimal("100.000"), Decimal("60.0000"))
    _folio_with_purchase(db, member, debt_scheme, Decimal("4000.00"), Decimal("100.000"), Decimal("40.0000"))

    with patch(
        "app.services.dashboard.holdings.get_nav_on_or_before",
        new=AsyncMock(side_effect=lambda db_, scheme, on_date: (Decimal("60.0000"), date(2024, 6, 1)) if scheme.amc_name == "HDFC AMC" else (Decimal("40.0000"), date(2024, 6, 1))),
    ), patch("app.services.dashboard.holdings.get_previous_nav_from_cache", return_value=None):
        summary = asyncio.run(compute_allocation(db, [member.id]))

    assert Decimal(summary.total_value) == Decimal("10000.00")
    by_class = {b.label: Decimal(b.current_value) for b in summary.by_asset_class}
    assert by_class["Equity"] == Decimal("6000.00")
    assert by_class["Debt"] == Decimal("4000.00")
    equity_bucket = next(b for b in summary.by_asset_class if b.label == "Equity")
    assert Decimal(equity_bucket.percentage) == Decimal("60.00")


def test_compute_allocation_empty_when_no_holdings():
    db = _session()
    member = _household_member(db)
    summary = asyncio.run(compute_allocation(db, [member.id]))
    assert summary.by_asset_class == []
    assert summary.by_amc == []
    assert Decimal(summary.total_value) == Decimal("0")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_allocation.py -v`
Expected: FAIL — `app.services.dashboard.allocation` doesn't exist yet.

- [ ] **Step 3: Add `AllocationBucket`/`AllocationSummary` to `schemas.py`**

```python
# Add to backend/app/services/dashboard/schemas.py
class AllocationBucket(BaseModel):
    label: str
    current_value: str
    percentage: str


class AllocationSummary(BaseModel):
    by_asset_class: list[AllocationBucket]
    by_amc: list[AllocationBucket]
    total_value: str
```

No new imports needed for this addition — `BaseModel` is already imported
at the top of `schemas.py`. Add both classes at the end of the file.

- [ ] **Step 4: Implement `allocation.py`**

```python
# backend/app/services/dashboard/allocation.py
"""Shallow asset-class/AMC allocation — Dashboard Service's own job per
PRD-03 FR-4, not deferred to the (unbuilt) Analytics service. Groups
already-computed holdings; does no NAV fetching or FIFO processing of its
own."""

from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.reference import Scheme
from app.services.dashboard.holdings import compute_holdings
from app.services.dashboard.schemas import AllocationBucket, AllocationSummary


def _asset_class_bucket(sebi_category: str) -> str:
    lower = sebi_category.lower()
    if "equity" in lower:
        return "Equity"
    if "debt" in lower or "income" in lower or "liquid" in lower or "money market" in lower:
        return "Debt"
    if "hybrid" in lower:
        return "Hybrid"
    return "Other"


async def compute_allocation(db: Session, household_member_ids: list[uuid.UUID]) -> AllocationSummary:
    holdings = await compute_holdings(db, household_member_ids)

    total_value = sum((Decimal(h.current_value) for h in holdings), Decimal("0"))

    # Bucket label needs the raw sebi_category, which HoldingRow doesn't
    # carry — one batch query for every scheme in this holding set, not one
    # query per holding row.
    scheme_ids = {uuid.UUID(h.scheme_id) for h in holdings}
    categories = {s.id: s.sebi_category for s in db.query(Scheme).filter(Scheme.id.in_(scheme_ids)).all()} if scheme_ids else {}

    by_class: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_amc: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for holding in holdings:
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
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_allocation.py -v`
Expected: PASS (2/2)

- [ ] **Step 6: Write the failing route test**

```python
# backend/tests/api/test_dashboard_allocation_route.py
def _authed_headers_and_member(client, phone: str):
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    member = client.post("/household-members", json={"name": "Self", "relationship": "self"}, headers=headers).json()
    return headers, member["id"]


def test_allocation_route_requires_auth(client):
    response = client.get("/household-members/00000000-0000-0000-0000-000000000000/allocation")
    assert response.status_code == 401


def test_allocation_route_returns_empty_summary_for_member_with_no_holdings(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000010")
    response = client.get(f"/household-members/{member_id}/allocation", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["by_asset_class"] == []
    assert body["total_value"] == "0"
```

- [ ] **Step 7: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_dashboard_allocation_route.py -v`
Expected: FAIL — route doesn't exist.

- [ ] **Step 8: Add the route to `dashboard.py`**

```python
# Add import
from app.services.dashboard.allocation import compute_allocation
from app.services.dashboard.schemas import AllocationSummary

# Add route
@router.get("/household-members/{member_id}/allocation", response_model=AllocationSummary)
async def get_member_allocation(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if get_household_member_for_user(db, user.id, member_id) is None:
        raise HTTPException(status_code=404, detail="Household member not found.")
    return await compute_allocation(db, [member_id])
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_dashboard_allocation_route.py -v`
Expected: PASS (2/2)

- [ ] **Step 10: Run the full backend suite**

Run: `cd backend && .venv/bin/pytest -m "not postgres" -v`
Expected: All pass.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/dashboard/allocation.py backend/app/services/dashboard/schemas.py backend/app/api/dashboard.py backend/tests/services/dashboard/test_allocation.py backend/tests/api/test_dashboard_allocation_route.py
git commit -m "feat: add shallow allocation summary and GET /household-members/{id}/allocation"
```

---

### Task 4: Active-SIP detection (`sip.py`) + `GET /household-members/{id}/sips`

**Files:**
- Create: `backend/app/services/dashboard/sip.py`
- Modify: `backend/app/services/dashboard/schemas.py`
- Modify: `backend/app/api/dashboard.py`
- Test: `backend/tests/services/dashboard/test_sip.py`
- Test: `backend/tests/api/test_dashboard_sips_route.py`

**Interfaces:**
- Consumes: nothing from other Dashboard modules — pure transaction-ledger
  reading, sync (no NAV needed).
- Produces: `def compute_active_sips(db: Session, household_member_ids: list[uuid.UUID]) -> list[SipRow]`
  — reused by Task 7 (aggregate).
- Produces: `SipRow` schema in `schemas.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/dashboard/test_sip.py
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import PlanType, Relationship, TransactionType
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.models.user import HouseholdMember, User
from app.services.dashboard.sip import compute_active_sips


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autoflush=False, bind=engine)()


def _household_member(db):
    user = User(id=uuid.uuid4(), phone_number=f"+9199999{uuid.uuid4().hex[:5]}", created_at=datetime.now(timezone.utc))
    db.add(user)
    db.flush()
    member = HouseholdMember(id=uuid.uuid4(), user_id=user.id, name="Self", relationship=Relationship.SELF, created_at=datetime.now(timezone.utc))
    db.add(member)
    db.commit()
    return member


def _scheme(db, name="SIP Fund"):
    scheme = Scheme(id=uuid.uuid4(), amfi_code=uuid.uuid4().hex[:6], isin="INF123", name=name, amc_name="HDFC AMC", sebi_category="Equity Scheme - Flexi Cap Fund")
    db.add(scheme)
    db.commit()
    return scheme


def _folio(db, member, scheme):
    folio = Folio(id=uuid.uuid4(), household_member_id=member.id, scheme_id=scheme.id, folio_number=uuid.uuid4().hex[:6], plan_type=PlanType.DIRECT)
    db.add(folio)
    db.commit()
    return folio


def _sip_txn(db, folio, on_date, amount=Decimal("1000.00"), units=Decimal("20.000"), nav=Decimal("50.0000")):
    txn = Transaction(id=uuid.uuid4(), folio_id=folio.id, import_id=uuid.uuid4(), type=TransactionType.PURCHASE_SIP, date=on_date, amount=amount, units=units, nav=nav)
    db.add(txn)
    db.commit()
    return txn


def test_sip_within_40_days_is_active():
    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    _sip_txn(db, folio, date.today() - timedelta(days=10))

    sips = compute_active_sips(db, [member.id])
    assert len(sips) == 1
    assert sips[0].scheme_name == "SIP Fund"


def test_sip_older_than_40_days_is_not_active():
    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    _sip_txn(db, folio, date.today() - timedelta(days=45))

    sips = compute_active_sips(db, [member.id])
    assert sips == []


def test_sip_uses_most_recent_transaction_per_folio():
    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    _sip_txn(db, folio, date.today() - timedelta(days=70), amount=Decimal("1000.00"))
    _sip_txn(db, folio, date.today() - timedelta(days=10), amount=Decimal("1500.00"))

    sips = compute_active_sips(db, [member.id])
    assert len(sips) == 1
    assert Decimal(sips[0].sip_amount) == Decimal("1500.00")


def test_non_sip_purchase_is_not_a_sip():
    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme)
    db.add(Transaction(id=uuid.uuid4(), folio_id=folio.id, import_id=uuid.uuid4(), type=TransactionType.PURCHASE, date=date.today(), amount=Decimal("1000.00"), units=Decimal("20.000"), nav=Decimal("50.0000")))
    db.commit()

    sips = compute_active_sips(db, [member.id])
    assert sips == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_sip.py -v`
Expected: FAIL — `app.services.dashboard.sip` doesn't exist yet.

- [ ] **Step 3: Add `SipRow` to `schemas.py`**

```python
# Add to backend/app/services/dashboard/schemas.py
class SipRow(BaseModel):
    scheme_id: str
    scheme_name: str
    household_member_id: str
    household_member_name: str
    sip_date: date
    sip_amount: str
```

`date` is already imported in `schemas.py` (an earlier task in this plan
added `from datetime import date` for `HoldingRow.current_nav_date`) — no
new import needed here. Add the class at the end of the file.

- [ ] **Step 4: Implement `sip.py`**

```python
# backend/app/services/dashboard/sip.py
"""Active-SIP detection — a SIP is "active" if its most recent
purchase_sip transaction, per folio, falls within the last 40 days
(covers a monthly cadence plus a grace window for processing delays)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.enums import TransactionType
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.models.user import HouseholdMember
from app.services.dashboard.schemas import SipRow

SIP_ACTIVE_WINDOW_DAYS = 40


def compute_active_sips(db: Session, household_member_ids: list[uuid.UUID]) -> list[SipRow]:
    if not household_member_ids:
        return []

    members = {m.id: m for m in db.query(HouseholdMember).filter(HouseholdMember.id.in_(household_member_ids)).all()}
    folios = db.query(Folio).filter(Folio.household_member_id.in_(household_member_ids)).all()
    cutoff = date.today() - timedelta(days=SIP_ACTIVE_WINDOW_DAYS)

    rows: list[SipRow] = []
    for folio in folios:
        most_recent = (
            db.query(Transaction)
            .filter(Transaction.folio_id == folio.id, Transaction.type == TransactionType.PURCHASE_SIP)
            .order_by(Transaction.date.desc())
            .first()
        )
        if most_recent is None or most_recent.date < cutoff:
            continue
        scheme = db.get(Scheme, folio.scheme_id)
        rows.append(
            SipRow(
                scheme_id=str(scheme.id),
                scheme_name=scheme.name,
                household_member_id=str(folio.household_member_id),
                household_member_name=members[folio.household_member_id].name,
                sip_date=most_recent.date,
                sip_amount=str(most_recent.amount),
            )
        )
    return rows
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_sip.py -v`
Expected: PASS (4/4)

- [ ] **Step 6: Write the failing route test**

```python
# backend/tests/api/test_dashboard_sips_route.py
def _authed_headers_and_member(client, phone: str):
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    member = client.post("/household-members", json={"name": "Self", "relationship": "self"}, headers=headers).json()
    return headers, member["id"]


def test_sips_route_requires_auth(client):
    response = client.get("/household-members/00000000-0000-0000-0000-000000000000/sips")
    assert response.status_code == 401


def test_sips_route_returns_empty_list_for_member_with_no_sips(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000020")
    response = client.get(f"/household-members/{member_id}/sips", headers=headers)
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 7: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_dashboard_sips_route.py -v`
Expected: FAIL — route doesn't exist.

- [ ] **Step 8: Add the route to `dashboard.py`**

```python
# Add import
from app.services.dashboard.sip import compute_active_sips
from app.services.dashboard.schemas import SipRow

# Add route
@router.get("/household-members/{member_id}/sips", response_model=list[SipRow])
def get_member_sips(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if get_household_member_for_user(db, user.id, member_id) is None:
        raise HTTPException(status_code=404, detail="Household member not found.")
    return compute_active_sips(db, [member_id])
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_dashboard_sips_route.py -v`
Expected: PASS (2/2)

- [ ] **Step 10: Run the full backend suite**

Run: `cd backend && .venv/bin/pytest -m "not postgres" -v`
Expected: All pass.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/dashboard/sip.py backend/app/services/dashboard/schemas.py backend/app/api/dashboard.py backend/tests/services/dashboard/test_sip.py backend/tests/api/test_dashboard_sips_route.py
git commit -m "feat: add active-SIP detection and GET /household-members/{id}/sips"
```

---

### Task 5: Investment cash flow (`cash_flow.py`) + `GET /household-members/{id}/cash-flow`

**Files:**
- Create: `backend/app/services/dashboard/cash_flow.py`
- Modify: `backend/app/services/dashboard/schemas.py`
- Modify: `backend/app/api/dashboard.py`
- Test: `backend/tests/services/dashboard/test_cash_flow.py`
- Test: `backend/tests/api/test_dashboard_cash_flow_route.py`

**Interfaces:**
- Consumes: nothing from other Dashboard modules — pure transaction-ledger
  reading, sync.
- Produces: `def compute_cash_flow(db: Session, household_member_ids: list[uuid.UUID]) -> list[CashFlowEntry]`
  — reused by Task 7 (aggregate).
- Produces: `CashFlowEntry` schema in `schemas.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/dashboard/test_cash_flow.py
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import PlanType, Relationship, TransactionType
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.models.user import HouseholdMember, User
from app.services.dashboard.cash_flow import compute_cash_flow


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autoflush=False, bind=engine)()


def _household_member(db):
    user = User(id=uuid.uuid4(), phone_number=f"+9199999{uuid.uuid4().hex[:5]}", created_at=datetime.now(timezone.utc))
    db.add(user)
    db.flush()
    member = HouseholdMember(id=uuid.uuid4(), user_id=user.id, name="Self", relationship=Relationship.SELF, created_at=datetime.now(timezone.utc))
    db.add(member)
    db.commit()
    return member


def _folio(db, member):
    scheme = Scheme(id=uuid.uuid4(), amfi_code=uuid.uuid4().hex[:6], isin="INF123", name="Test Fund", amc_name="HDFC AMC", sebi_category="Equity Scheme - Flexi Cap Fund")
    db.add(scheme)
    db.commit()
    folio = Folio(id=uuid.uuid4(), household_member_id=member.id, scheme_id=scheme.id, folio_number=uuid.uuid4().hex[:6], plan_type=PlanType.DIRECT)
    db.add(folio)
    db.commit()
    return folio


def _txn(db, folio, type_, on_date, amount):
    txn = Transaction(id=uuid.uuid4(), folio_id=folio.id, import_id=uuid.uuid4(), type=type_, date=on_date, amount=amount, units=Decimal("1.000"), nav=Decimal("50.0000"))
    db.add(txn)
    db.commit()
    return txn


def test_purchase_is_a_debit():
    db = _session()
    member = _household_member(db)
    folio = _folio(db, member)
    _txn(db, folio, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("1000.00"))

    entries = compute_cash_flow(db, [member.id])
    assert len(entries) == 1
    assert entries[0].direction == "debit"


def test_redemption_is_a_credit():
    db = _session()
    member = _household_member(db)
    folio = _folio(db, member)
    _txn(db, folio, TransactionType.REDEMPTION, date(2024, 3, 1), Decimal("1200.00"))

    entries = compute_cash_flow(db, [member.id])
    assert len(entries) == 1
    assert entries[0].direction == "credit"


def test_dividend_payout_is_a_credit():
    db = _session()
    member = _household_member(db)
    folio = _folio(db, member)
    _txn(db, folio, TransactionType.DIVIDEND_PAYOUT, date(2024, 4, 1), Decimal("50.00"))

    entries = compute_cash_flow(db, [member.id])
    assert len(entries) == 1
    assert entries[0].direction == "credit"


def test_switch_in_and_out_are_excluded():
    db = _session()
    member = _household_member(db)
    folio = _folio(db, member)
    _txn(db, folio, TransactionType.SWITCH_IN, date(2024, 5, 1), Decimal("500.00"))
    _txn(db, folio, TransactionType.SWITCH_OUT, date(2024, 5, 1), Decimal("500.00"))

    entries = compute_cash_flow(db, [member.id])
    assert entries == []


def test_entries_are_ordered_by_date():
    db = _session()
    member = _household_member(db)
    folio = _folio(db, member)
    _txn(db, folio, TransactionType.PURCHASE, date(2024, 3, 1), Decimal("1000.00"))
    _txn(db, folio, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("500.00"))

    entries = compute_cash_flow(db, [member.id])
    assert [e.date for e in entries] == [date(2024, 1, 1), date(2024, 3, 1)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_cash_flow.py -v`
Expected: FAIL — `app.services.dashboard.cash_flow` doesn't exist yet.

- [ ] **Step 3: Add `CashFlowEntry` to `schemas.py`**

```python
# Add to backend/app/services/dashboard/schemas.py
from app.models.enums import TransactionType


class CashFlowEntry(BaseModel):
    date: date
    type: TransactionType
    amount: str
    direction: str
    scheme_name: str
    household_member_id: str
    household_member_name: str
```

Add the `TransactionType` import to the existing import block at the top
of `schemas.py` (`date` is already imported from an earlier task). Add the
class at the end of the file.

- [ ] **Step 4: Implement `cash_flow.py`**

```python
# backend/app/services/dashboard/cash_flow.py
"""Investment cash flow — computed entirely from parsed transactions, no
new data source. Purchases/SIP debits as outflow, redemptions and dividend
payouts as inflow, per PRD-03 FR-7. switch_in/switch_out are intra-portfolio
movements, not real cash entering or leaving the platform, and excluded —
FR-7's own wording doesn't mention switches. stt/stamp_duty/misc/segregation
are also excluded (informational, not a cash movement FR-7 describes)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.enums import TransactionType
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.models.user import HouseholdMember
from app.services.dashboard.schemas import CashFlowEntry

_DEBIT_TYPES = {TransactionType.PURCHASE, TransactionType.PURCHASE_SIP}
_CREDIT_TYPES = {TransactionType.REDEMPTION, TransactionType.DIVIDEND_PAYOUT}


def compute_cash_flow(db: Session, household_member_ids: list[uuid.UUID]) -> list[CashFlowEntry]:
    if not household_member_ids:
        return []

    members = {m.id: m for m in db.query(HouseholdMember).filter(HouseholdMember.id.in_(household_member_ids)).all()}
    folios = {f.id: f for f in db.query(Folio).filter(Folio.household_member_id.in_(household_member_ids)).all()}
    if not folios:
        return []
    schemes = {s.id: s for s in db.query(Scheme).filter(Scheme.id.in_({f.scheme_id for f in folios.values()})).all()}

    relevant_types = _DEBIT_TYPES | _CREDIT_TYPES
    transactions = (
        db.query(Transaction)
        .filter(Transaction.folio_id.in_(folios.keys()), Transaction.type.in_(relevant_types))
        .order_by(Transaction.date, Transaction.id)
        .all()
    )

    entries: list[CashFlowEntry] = []
    for txn in transactions:
        folio = folios[txn.folio_id]
        scheme = schemes[folio.scheme_id]
        entries.append(
            CashFlowEntry(
                date=txn.date,
                type=txn.type,
                amount=str(txn.amount),
                direction="debit" if txn.type in _DEBIT_TYPES else "credit",
                scheme_name=scheme.name,
                household_member_id=str(folio.household_member_id),
                household_member_name=members[folio.household_member_id].name,
            )
        )
    return entries
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_cash_flow.py -v`
Expected: PASS (5/5)

- [ ] **Step 6: Write the failing route test**

```python
# backend/tests/api/test_dashboard_cash_flow_route.py
def _authed_headers_and_member(client, phone: str):
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    member = client.post("/household-members", json={"name": "Self", "relationship": "self"}, headers=headers).json()
    return headers, member["id"]


def test_cash_flow_route_requires_auth(client):
    response = client.get("/household-members/00000000-0000-0000-0000-000000000000/cash-flow")
    assert response.status_code == 401


def test_cash_flow_route_returns_empty_list_for_member_with_no_transactions(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000030")
    response = client.get(f"/household-members/{member_id}/cash-flow", headers=headers)
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 7: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_dashboard_cash_flow_route.py -v`
Expected: FAIL — route doesn't exist.

- [ ] **Step 8: Add the route to `dashboard.py`**

```python
# Add import
from app.services.dashboard.cash_flow import compute_cash_flow
from app.services.dashboard.schemas import CashFlowEntry

# Add route
@router.get("/household-members/{member_id}/cash-flow", response_model=list[CashFlowEntry])
def get_member_cash_flow(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if get_household_member_for_user(db, user.id, member_id) is None:
        raise HTTPException(status_code=404, detail="Household member not found.")
    return compute_cash_flow(db, [member_id])
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_dashboard_cash_flow_route.py -v`
Expected: PASS (2/2)

- [ ] **Step 10: Run the full backend suite**

Run: `cd backend && .venv/bin/pytest -m "not postgres" -v`
Expected: All pass.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/dashboard/cash_flow.py backend/app/services/dashboard/schemas.py backend/app/api/dashboard.py backend/tests/services/dashboard/test_cash_flow.py backend/tests/api/test_dashboard_cash_flow_route.py
git commit -m "feat: add investment cash flow and GET /household-members/{id}/cash-flow"
```

---

### Task 6: Monthly value snapshots (`snapshots.py`) + `GET /household-members/{id}/snapshots`

**Files:**
- Create: `backend/app/services/dashboard/snapshots.py`
- Modify: `backend/app/services/dashboard/schemas.py`
- Modify: `backend/app/api/dashboard.py`
- Test: `backend/tests/services/dashboard/test_snapshots.py`
- Test: `backend/tests/api/test_dashboard_snapshots_route.py`

**Interfaces:**
- Consumes: `_process_folio_lots` from `./holdings` (Task 2, reused as-is —
  snapshots pass it a date-filtered transaction list rather than the full
  history); `get_nav_on_or_before` from `./nav` (Task 1).
- Produces: `async def get_snapshots(db: Session, household_member_ids: list[uuid.UUID]) -> list[SnapshotRow]`
  — reused by Task 7 (aggregate).
- Produces: `SnapshotRow` schema in `schemas.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/dashboard/test_snapshots.py
import asyncio
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import PlanType, Relationship, TransactionType
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.snapshot import PortfolioSnapshot
from app.models.transaction import Transaction
from app.models.user import HouseholdMember, User
from app.services.dashboard.snapshots import get_snapshots


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autoflush=False, bind=engine)()


def _household_member(db):
    user = User(id=uuid.uuid4(), phone_number=f"+9199999{uuid.uuid4().hex[:5]}", created_at=datetime.now(timezone.utc))
    db.add(user)
    db.flush()
    member = HouseholdMember(id=uuid.uuid4(), user_id=user.id, name="Self", relationship=Relationship.SELF, created_at=datetime.now(timezone.utc))
    db.add(member)
    db.commit()
    return member


def _folio_with_purchase(db, member, on_date, amount, units, nav):
    scheme = Scheme(id=uuid.uuid4(), amfi_code=uuid.uuid4().hex[:6], isin="INF123", name="Test Fund", amc_name="HDFC AMC", sebi_category="Equity Scheme - Flexi Cap Fund")
    db.add(scheme)
    db.commit()
    folio = Folio(id=uuid.uuid4(), household_member_id=member.id, scheme_id=scheme.id, folio_number=uuid.uuid4().hex[:6], plan_type=PlanType.DIRECT)
    db.add(folio)
    db.commit()
    db.add(Transaction(id=uuid.uuid4(), folio_id=folio.id, import_id=uuid.uuid4(), type=TransactionType.PURCHASE, date=on_date, amount=amount, units=units, nav=nav))
    db.commit()
    return folio, scheme


def test_get_snapshots_backfills_from_first_transaction_month():
    db = _session()
    member = _household_member(db)
    _folio_with_purchase(db, member, date(2024, 1, 15), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))

    with patch(
        "app.services.dashboard.snapshots.get_nav_on_or_before",
        new=AsyncMock(return_value=(Decimal("55.0000"), date(2024, 2, 1))),
    ):
        rows = asyncio.run(get_snapshots(db, [member.id]))

    months = sorted(r.snapshot_month for r in rows)
    assert months[0] == date(2024, 1, 31)
    assert Decimal(rows[0].total_value) == Decimal("5500.00")  # 100 * 55


def test_get_snapshots_caches_into_portfolio_snapshots_table():
    db = _session()
    member = _household_member(db)
    _folio_with_purchase(db, member, date(2024, 1, 15), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))

    with patch(
        "app.services.dashboard.snapshots.get_nav_on_or_before",
        new=AsyncMock(return_value=(Decimal("55.0000"), date(2024, 2, 1))),
    ) as mock_nav:
        asyncio.run(get_snapshots(db, [member.id]))
        first_call_count = mock_nav.call_count
        asyncio.run(get_snapshots(db, [member.id]))
        second_call_count = mock_nav.call_count

    # Second call should hit the cached portfolio_snapshots rows, not
    # re-fetch NAV for months already computed.
    assert second_call_count == first_call_count

    cached = db.query(PortfolioSnapshot).filter_by(household_member_id=member.id).all()
    assert len(cached) > 0


def test_get_snapshots_returns_empty_for_member_with_no_transactions():
    db = _session()
    member = _household_member(db)
    rows = asyncio.run(get_snapshots(db, [member.id]))
    assert rows == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_snapshots.py -v`
Expected: FAIL — `app.services.dashboard.snapshots` doesn't exist yet.

- [ ] **Step 3: Add `SnapshotRow` to `schemas.py`**

```python
# Add to backend/app/services/dashboard/schemas.py
class SnapshotRow(BaseModel):
    household_member_id: str
    household_member_name: str
    snapshot_month: date
    total_value: str
```

No new imports needed — `date` is already imported in `schemas.py` from an
earlier task. Add the class at the end of the file.

- [ ] **Step 4: Implement `snapshots.py`**

```python
# backend/app/services/dashboard/snapshots.py
"""Monthly portfolio value snapshots — backfillable historically, per
PRD-03 FR-8, since mfapi.in provides full historical NAV per scheme. First
request for a member computes every missing month-end into
portfolio_snapshots; subsequent requests read the cached rows."""

from __future__ import annotations

import uuid
from calendar import monthrange
from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.snapshot import PortfolioSnapshot
from app.models.transaction import Transaction
from app.models.user import HouseholdMember
from app.services.dashboard.holdings import _process_folio_lots
from app.services.dashboard.nav import get_nav_on_or_before
from app.services.dashboard.schemas import SnapshotRow


def _month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def _iter_month_ends(start: date, end: date) -> Iterator[date]:
    year, month = start.year, start.month
    while True:
        month_end = _month_end(year, month)
        if month_end > end:
            break
        yield month_end
        month += 1
        if month > 12:
            month = 1
            year += 1


async def get_snapshots(db: Session, household_member_ids: list[uuid.UUID]) -> list[SnapshotRow]:
    rows: list[SnapshotRow] = []

    for member_id in household_member_ids:
        member = db.get(HouseholdMember, member_id)
        if member is None:
            continue

        folios = db.query(Folio).filter(Folio.household_member_id == member_id).all()
        if not folios:
            continue

        transactions_by_folio = {
            folio.id: (
                db.query(Transaction)
                .filter(Transaction.folio_id == folio.id)
                .order_by(Transaction.date, Transaction.id)
                .all()
            )
            for folio in folios
        }
        all_dates = [t.date for txns in transactions_by_folio.values() for t in txns]
        if not all_dates:
            continue
        first_date = min(all_dates)

        cached = {
            s.snapshot_month: s.total_value
            for s in db.query(PortfolioSnapshot).filter(PortfolioSnapshot.household_member_id == member_id).all()
        }

        for month_end in _iter_month_ends(first_date, date.today()):
            if month_end in cached:
                rows.append(
                    SnapshotRow(
                        household_member_id=str(member_id),
                        household_member_name=member.name,
                        snapshot_month=month_end,
                        total_value=str(cached[month_end]),
                    )
                )
                continue

            total_value = Decimal("0")
            for folio in folios:
                txns_to_date = [t for t in transactions_by_folio[folio.id] if t.date <= month_end]
                units_held, _cost_basis, _realized = _process_folio_lots(txns_to_date)
                if units_held == 0:
                    continue
                scheme = db.get(Scheme, folio.scheme_id)
                nav_result = await get_nav_on_or_before(db, scheme, month_end)
                if nav_result is None:
                    continue
                nav, _actual_date = nav_result
                total_value += units_held * nav

            snapshot = PortfolioSnapshot(
                household_member_id=member_id, snapshot_month=month_end,
                total_value=total_value, computed_at=datetime.now(timezone.utc),
            )
            db.add(snapshot)
            db.commit()
            rows.append(
                SnapshotRow(
                    household_member_id=str(member_id), household_member_name=member.name,
                    snapshot_month=month_end, total_value=str(total_value),
                )
            )
    return rows
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_snapshots.py -v`
Expected: PASS (3/3)

- [ ] **Step 6: Write the failing route test**

```python
# backend/tests/api/test_dashboard_snapshots_route.py
def _authed_headers_and_member(client, phone: str):
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    member = client.post("/household-members", json={"name": "Self", "relationship": "self"}, headers=headers).json()
    return headers, member["id"]


def test_snapshots_route_requires_auth(client):
    response = client.get("/household-members/00000000-0000-0000-0000-000000000000/snapshots")
    assert response.status_code == 401


def test_snapshots_route_returns_empty_list_for_member_with_no_transactions(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000040")
    response = client.get(f"/household-members/{member_id}/snapshots", headers=headers)
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 7: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_dashboard_snapshots_route.py -v`
Expected: FAIL — route doesn't exist.

- [ ] **Step 8: Add the route to `dashboard.py`**

```python
# Add import
from app.services.dashboard.snapshots import get_snapshots
from app.services.dashboard.schemas import SnapshotRow

# Add route
@router.get("/household-members/{member_id}/snapshots", response_model=list[SnapshotRow])
async def get_member_snapshots(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if get_household_member_for_user(db, user.id, member_id) is None:
        raise HTTPException(status_code=404, detail="Household member not found.")
    return await get_snapshots(db, [member_id])
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_dashboard_snapshots_route.py -v`
Expected: PASS (2/2)

- [ ] **Step 10: Run the full backend suite**

Run: `cd backend && .venv/bin/pytest -m "not postgres" -v`
Expected: All pass.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/dashboard/snapshots.py backend/app/services/dashboard/schemas.py backend/app/api/dashboard.py backend/tests/services/dashboard/test_snapshots.py backend/tests/api/test_dashboard_snapshots_route.py
git commit -m "feat: add monthly value snapshot backfill and GET /household-members/{id}/snapshots"
```

---

### Task 7: Placeholder-aware family aggregation (`aggregate.py`) + 5 aggregate routes

**Files:**
- Create: `backend/app/services/dashboard/aggregate.py`
- Modify: `backend/app/services/dashboard/schemas.py`
- Modify: `backend/app/api/dashboard.py`
- Test: `backend/tests/services/dashboard/test_aggregate.py`
- Test: `backend/tests/api/test_dashboard_aggregate_routes.py`

**Interfaces:**
- Consumes: `compute_holdings` (Task 2), `compute_allocation` (Task 3),
  `compute_active_sips` (Task 4), `compute_cash_flow` (Task 5),
  `get_snapshots` (Task 6); `list_household_members` from
  `./household_members` (existing).
- Produces: `MemberStatus`, `AggregateHoldingsResponse`,
  `AggregateAllocationResponse`, `AggregateSipsResponse`,
  `AggregateCashFlowResponse`, `AggregateSnapshotsResponse` schemas.
- Produces: `get_member_statuses`, `get_aggregate_holdings`,
  `get_aggregate_allocation`, `get_aggregate_sips`,
  `get_aggregate_cash_flow`, `get_aggregate_snapshots` — the last task in
  this plan, nothing further consumes these.

This is the last task — it wires every prior task's compute function into
the family-aggregate view, with FR-10's placeholder requirement (a member
with zero imports shows as a clear placeholder, never silently excluded).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/dashboard/test_aggregate.py
import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import ImportStatus, Relationship
from app.models.imports import Import
from app.models.user import HouseholdMember, User
from app.services.dashboard.aggregate import get_aggregate_holdings, get_member_statuses


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autoflush=False, bind=engine)()


def _user_with_members(db, names: list[str]):
    user = User(id=uuid.uuid4(), phone_number=f"+9199999{uuid.uuid4().hex[:5]}", created_at=datetime.now(timezone.utc))
    db.add(user)
    db.flush()
    members = []
    for name in names:
        member = HouseholdMember(id=uuid.uuid4(), user_id=user.id, name=name, relationship=Relationship.SELF, created_at=datetime.now(timezone.utc))
        db.add(member)
        members.append(member)
    db.commit()
    return user, members


def test_get_member_statuses_marks_member_without_confirmed_import_as_no_data():
    db = _session()
    user, (member_with_data, member_without) = _user_with_members(db, ["Mom", "Dad"])
    db.add(Import(id=uuid.uuid4(), household_member_id=member_with_data.id, status=ImportStatus.CONFIRMED, uploaded_at=datetime.now(timezone.utc), confirmed_at=datetime.now(timezone.utc)))
    db.commit()

    statuses = get_member_statuses(db, user.id)
    by_name = {s.name: s.has_data for s in statuses}
    assert by_name["Mom"] is True
    assert by_name["Dad"] is False


def test_get_member_statuses_pending_import_does_not_count_as_data():
    db = _session()
    user, (member,) = _user_with_members(db, ["Solo"])
    db.add(Import(id=uuid.uuid4(), household_member_id=member.id, status=ImportStatus.PENDING, uploaded_at=datetime.now(timezone.utc)))
    db.commit()

    statuses = get_member_statuses(db, user.id)
    assert statuses[0].has_data is False


def test_get_aggregate_holdings_includes_members_list_with_placeholder():
    db = _session()
    user, (member_a, member_b) = _user_with_members(db, ["Mom", "Dad"])

    response = asyncio.run(get_aggregate_holdings(db, user.id))
    assert {m.name for m in response.members} == {"Mom", "Dad"}
    assert all(m.has_data is False for m in response.members)
    assert response.holdings == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_aggregate.py -v`
Expected: FAIL — `app.services.dashboard.aggregate` doesn't exist yet.

- [ ] **Step 3: Add the aggregate schemas to `schemas.py`**

```python
# Add to backend/app/services/dashboard/schemas.py
class MemberStatus(BaseModel):
    id: str
    name: str
    has_data: bool


class AggregateHoldingsResponse(BaseModel):
    members: list[MemberStatus]
    holdings: list[HoldingRow]


class AggregateAllocationResponse(BaseModel):
    members: list[MemberStatus]
    allocation: AllocationSummary


class AggregateSipsResponse(BaseModel):
    members: list[MemberStatus]
    sips: list[SipRow]


class AggregateCashFlowResponse(BaseModel):
    members: list[MemberStatus]
    cash_flow: list[CashFlowEntry]


class AggregateSnapshotsResponse(BaseModel):
    members: list[MemberStatus]
    snapshots: list[SnapshotRow]
```

No new imports needed — every type referenced here (`HoldingRow`,
`AllocationSummary`, `SipRow`, `CashFlowEntry`, `SnapshotRow`) is already
defined earlier in the same file by prior tasks. Add all six classes at the
end of the file.

- [ ] **Step 4: Implement `aggregate.py`**

```python
# backend/app/services/dashboard/aggregate.py
"""Family aggregate views — the only place per-member and family code paths
genuinely differ: not the computation (every compute_* function already
takes a list of member IDs), but the response shape. PRD-03 FR-10 requires
a member with no imports yet to show as a clear placeholder, never silently
excluded, so every aggregate response carries a `members` status list
alongside the combined data."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.enums import ImportStatus
from app.models.imports import Import
from app.services.dashboard.allocation import compute_allocation
from app.services.dashboard.cash_flow import compute_cash_flow
from app.services.dashboard.holdings import compute_holdings
from app.services.dashboard.household_members import list_household_members
from app.services.dashboard.schemas import (
    AggregateAllocationResponse,
    AggregateCashFlowResponse,
    AggregateHoldingsResponse,
    AggregateSipsResponse,
    AggregateSnapshotsResponse,
    MemberStatus,
)
from app.services.dashboard.sip import compute_active_sips
from app.services.dashboard.snapshots import get_snapshots


def _has_data(db: Session, member_id: uuid.UUID) -> bool:
    return (
        db.query(Import)
        .filter(Import.household_member_id == member_id, Import.status == ImportStatus.CONFIRMED)
        .first()
        is not None
    )


def get_member_statuses(db: Session, user_id: uuid.UUID) -> list[MemberStatus]:
    members = list_household_members(db, user_id)
    return [MemberStatus(id=str(m.id), name=m.name, has_data=_has_data(db, m.id)) for m in members]


async def get_aggregate_holdings(db: Session, user_id: uuid.UUID) -> AggregateHoldingsResponse:
    members = list_household_members(db, user_id)
    statuses = get_member_statuses(db, user_id)
    holdings = await compute_holdings(db, [m.id for m in members])
    return AggregateHoldingsResponse(members=statuses, holdings=holdings)


async def get_aggregate_allocation(db: Session, user_id: uuid.UUID) -> AggregateAllocationResponse:
    members = list_household_members(db, user_id)
    statuses = get_member_statuses(db, user_id)
    allocation = await compute_allocation(db, [m.id for m in members])
    return AggregateAllocationResponse(members=statuses, allocation=allocation)


def get_aggregate_sips(db: Session, user_id: uuid.UUID) -> AggregateSipsResponse:
    members = list_household_members(db, user_id)
    statuses = get_member_statuses(db, user_id)
    sips = compute_active_sips(db, [m.id for m in members])
    return AggregateSipsResponse(members=statuses, sips=sips)


def get_aggregate_cash_flow(db: Session, user_id: uuid.UUID) -> AggregateCashFlowResponse:
    members = list_household_members(db, user_id)
    statuses = get_member_statuses(db, user_id)
    cash_flow = compute_cash_flow(db, [m.id for m in members])
    return AggregateCashFlowResponse(members=statuses, cash_flow=cash_flow)


async def get_aggregate_snapshots(db: Session, user_id: uuid.UUID) -> AggregateSnapshotsResponse:
    members = list_household_members(db, user_id)
    statuses = get_member_statuses(db, user_id)
    snapshots = await get_snapshots(db, [m.id for m in members])
    return AggregateSnapshotsResponse(members=statuses, snapshots=snapshots)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_aggregate.py -v`
Expected: PASS (3/3)

- [ ] **Step 6: Write the failing route tests**

```python
# backend/tests/api/test_dashboard_aggregate_routes.py
def _authed_headers(client, phone: str):
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


def test_aggregate_holdings_requires_auth(client):
    response = client.get("/household/aggregate/holdings")
    assert response.status_code == 401


def test_aggregate_holdings_returns_members_and_empty_holdings(client):
    headers = _authed_headers(client, "+919000000050")
    client.post("/household-members", json={"name": "Mom", "relationship": "parent"}, headers=headers)
    client.post("/household-members", json={"name": "Dad", "relationship": "parent"}, headers=headers)

    response = client.get("/household/aggregate/holdings", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert {m["name"] for m in body["members"]} == {"Mom", "Dad"}
    assert body["holdings"] == []


def test_aggregate_allocation_returns_empty_summary(client):
    headers = _authed_headers(client, "+919000000051")
    response = client.get("/household/aggregate/allocation", headers=headers)
    assert response.status_code == 200
    assert response.json()["allocation"]["total_value"] == "0"


def test_aggregate_sips_returns_empty_list(client):
    headers = _authed_headers(client, "+919000000052")
    response = client.get("/household/aggregate/sips", headers=headers)
    assert response.status_code == 200
    assert response.json()["sips"] == []


def test_aggregate_cash_flow_returns_empty_list(client):
    headers = _authed_headers(client, "+919000000053")
    response = client.get("/household/aggregate/cash-flow", headers=headers)
    assert response.status_code == 200
    assert response.json()["cash_flow"] == []


def test_aggregate_snapshots_returns_empty_list(client):
    headers = _authed_headers(client, "+919000000054")
    response = client.get("/household/aggregate/snapshots", headers=headers)
    assert response.status_code == 200
    assert response.json()["snapshots"] == []
```

- [ ] **Step 7: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_dashboard_aggregate_routes.py -v`
Expected: FAIL — routes don't exist.

- [ ] **Step 8: Add the 5 aggregate routes to `dashboard.py`**

```python
# Add import
from app.services.dashboard.aggregate import (
    get_aggregate_allocation,
    get_aggregate_cash_flow,
    get_aggregate_holdings,
    get_aggregate_sips,
    get_aggregate_snapshots,
)
from app.services.dashboard.schemas import (
    AggregateAllocationResponse,
    AggregateCashFlowResponse,
    AggregateHoldingsResponse,
    AggregateSipsResponse,
    AggregateSnapshotsResponse,
)

# Add routes
@router.get("/household/aggregate/holdings", response_model=AggregateHoldingsResponse)
async def get_household_aggregate_holdings(user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    return await get_aggregate_holdings(db, user.id)


@router.get("/household/aggregate/allocation", response_model=AggregateAllocationResponse)
async def get_household_aggregate_allocation(user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    return await get_aggregate_allocation(db, user.id)


@router.get("/household/aggregate/sips", response_model=AggregateSipsResponse)
def get_household_aggregate_sips(user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    return get_aggregate_sips(db, user.id)


@router.get("/household/aggregate/cash-flow", response_model=AggregateCashFlowResponse)
def get_household_aggregate_cash_flow(user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    return get_aggregate_cash_flow(db, user.id)


@router.get("/household/aggregate/snapshots", response_model=AggregateSnapshotsResponse)
async def get_household_aggregate_snapshots(user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    return await get_aggregate_snapshots(db, user.id)
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_dashboard_aggregate_routes.py -v`
Expected: PASS (6/6)

- [ ] **Step 10: Run the full backend suite**

Run: `cd backend && .venv/bin/pytest -m "not postgres" -v`
Expected: All pass (this phase adds 92 + roughly 40 new tests).

- [ ] **Step 11: Run a manual end-to-end smoke check**

Run the dev server and confirm the OpenAPI schema includes all 10 new
routes: `cd backend && .venv/bin/uvicorn app.main:app --reload &` then
`curl -s http://localhost:8000/openapi.json | python3 -c "import json,sys; paths = json.load(sys.stdin)['paths']; print('\n'.join(p for p in paths if 'household' in p))"`
Expected: all 10 paths listed (5 per-member + 5 aggregate), plus the
existing `/household-members` and `/imports/*` routes. Stop the server
afterward.

- [ ] **Step 12: Commit**

```bash
git add backend/app/services/dashboard/aggregate.py backend/app/services/dashboard/schemas.py backend/app/api/dashboard.py backend/tests/services/dashboard/test_aggregate.py backend/tests/api/test_dashboard_aggregate_routes.py
git commit -m "feat: add placeholder-aware family aggregation and 5 GET /household/aggregate/* routes"
```

---

## Self-Review Notes (completed during plan authoring)

**Spec coverage:** every FR in the design spec maps to a task — NAV
fetch-and-cache (Task 1), FIFO holdings/FR-1-3 (Task 2), allocation/FR-4
(Task 3), SIP/FR-5-6 (Task 4), cash flow/FR-7 (Task 5), monthly
snapshots/FR-8 (Task 6), family aggregate + FR-9/FR-10 placeholder (Task 7).
FR-10a (Add Data entry point) needs no backend task, per the spec — the
existing `/imports/parse`/`/imports/confirm` already accept a real
`household_member_id`; wiring a UI affordance to them is Phase 3b's job.

**Placeholder scan:** no TBD/TODO. The one intentionally-incomplete code
block (Task 1's Step 3 `noqa` intermediate version) is explicitly labeled
"do not use this — use the corrected version below it" with the corrected,
complete version immediately following — not a plan gap.

**Type consistency:** `household_member_ids: list[uuid.UUID]` is the
parameter name and type used identically across `compute_holdings`,
`compute_allocation`, `compute_active_sips`, `compute_cash_flow`, and
`get_snapshots` — checked against each task's Interfaces block.
`_process_folio_lots`'s three-Decimal-tuple return shape
(`units_held, cost_basis, realized_gain`) is used identically in Task 2
(`holdings.py`) and Task 6 (`snapshots.py`, which imports it directly
rather than duplicating the FIFO logic).

**Scope check:** one cohesive backend phase — seven modules, each with a
clear single responsibility, matching Phase 1 backend's precedent size
(9 tasks) closely enough that it doesn't need further splitting. Frontend
(Phase 3b) and Distributor Comparison are separate, already-deferred plans
per the design spec.
