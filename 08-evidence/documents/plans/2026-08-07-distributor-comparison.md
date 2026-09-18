# Distributor Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement PRD-03's FR-11/FR-11a/FR-11b/FR-11c — a per-scheme,
per-member "returns by distributor" comparison, backed by a real,
independently-verified AMFI ARN-lookup integration with platform-wide
caching and a never-blocks-on-failure fallback.

**Architecture:** Two new service modules under
`backend/app/services/dashboard/` (`arn_lookup.py` for the AMFI client +
`arn_directory` cache, `distributor_comparison.py` for the per-ARN FIFO
grouping) plus one new route in `backend/app/api/dashboard.py`. Both new
modules reuse existing building blocks rather than reimplementing them:
`holdings._process_folio_lots` for cost-basis/gain math, `nav.py`'s
`get_nav_on_or_before` for current NAV, and the exact
`Depends(get_current_user)` + `get_household_member_for_user` ownership
pattern every sibling Dashboard route already uses.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 ORM, Pydantic, httpx (async),
pytest, SQLite in-memory for tests (matches every existing Dashboard test).

## Global Constraints

- `Decimal`, never `float`, for every money/units/NAV value, including test
  fixtures.
- No raw AMFI response payload persisted anywhere — only `arn_directory`'s
  four existing columns (`arn_code`, `distributor_name`, `status`,
  `last_checked_at`). No new tables, no migration — `arn_directory` and
  `ArnStatus` already exist from Phase 0.
- `_fetch_arn_record` is mocked via `unittest.mock.patch` in every test —
  no real network calls in the suite, even though the endpoint is real
  and was independently verified by hand during design (documented in a
  comment near the mock, not exercised live).
- Every new route follows the existing per-member ownership pattern
  exactly: `Depends(get_current_user)`, then
  `get_household_member_for_user(db, user.id, member_id) is None` → 404.
- A transient AMFI lookup failure must never be cached as a permanent
  value in `arn_directory` — same lesson as Phase 3's NAV-outage fix
  (`session.md`, bug #3). Only a definitive result (found-with-status, or
  confirmed-not-found) gets written.

---

### Task 1: AMFI ARN lookup client + `arn_directory` cache

**Files:**
- Create: `backend/app/services/dashboard/arn_lookup.py`
- Test: `backend/tests/services/dashboard/test_arn_lookup.py`

**Interfaces:**
- Consumes: `app.models.reference.ArnDirectory` (existing model —
  `arn_code: str` PK, `distributor_name: str | None`,
  `status: ArnStatus`, `last_checked_at: datetime | None`),
  `app.models.enums.ArnStatus` (existing enum — `ACTIVE`, `SUSPENDED`,
  `INVALID`, `UNRESOLVED`).
- Produces (for Task 2):
  - `async def resolve_arn(db: Session, arn_code: str) -> ArnDirectory | None`
    — `arn_code` is the full, `"ARN-"`-prefixed form as stored on
    `folios.arn_code`. Returns the cached-or-newly-resolved row, or `None`
    if resolution couldn't complete this time (never raises).

- [ ] **Step 1: Write the failing tests for the bare-ARN-digits helper and `resolve_arn`'s five branches**

Create `backend/tests/services/dashboard/test_arn_lookup.py`:

```python
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import ArnStatus
from app.models.reference import ArnDirectory
from app.services.dashboard.arn_lookup import _bare_arn_digits, resolve_arn


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autoflush=False, bind=engine)()


def test_bare_arn_digits_strips_arn_prefix_case_insensitively():
    assert _bare_arn_digits("ARN-0671") == "0671"
    assert _bare_arn_digits("arn-0671") == "0671"
    assert _bare_arn_digits("0671") == "0671"


# Real response captured live against AMFI's distributor-search endpoint
# during design (2026-08-07):
# GET https://www.amfiindia.com/api/distributor-agent?strOpt=ALL&search=0671&page=1&pageSize=1
# -> {"data": [{"ARN": "0671", "ARNHolderName": "Multiplize Investment
#     Services", "ARNValidTill": "2027-10-18T00:00:00.000Z", ...}],
#     "meta": {"total": 1, ...}}
# Confirms the endpoint is real and this shape is correct. Every test below
# mocks _fetch_arn_record directly (same convention as test_nav.py mocking
# _fetch_nav_history) — no live network call in the suite.
#
# The captured ARNValidTill (2027-10-18) is real but not permanently in the
# future — hardcoding it as an "ACTIVE" fixture would make this test start
# failing the day that date passes. _REAL_ACTIVE_RECORD stays as the
# verified example only; test payloads below use a synthetic 2099 date for
# "definitely active" and a synthetic 2020 date for "definitely expired".
_REAL_ACTIVE_RECORD = {
    "ARN": "0671",
    "ARNHolderName": "Multiplize Investment Services",
    "ARNValidTill": "2027-10-18T00:00:00.000Z",
}


def test_resolve_arn_returns_cached_row_without_fetching():
    import asyncio

    db = _session()
    db.add(ArnDirectory(arn_code="ARN-0671", distributor_name="Cached Name", status=ArnStatus.ACTIVE))
    db.commit()

    with patch(
        "app.services.dashboard.arn_lookup._fetch_arn_record",
        new=AsyncMock(side_effect=AssertionError("should not fetch")),
    ):
        result = asyncio.run(resolve_arn(db, "ARN-0671"))

    assert result.distributor_name == "Cached Name"
    assert result.status == ArnStatus.ACTIVE


def test_resolve_arn_writes_active_when_found_with_future_valid_till():
    import asyncio

    db = _session()
    active_record = {**_REAL_ACTIVE_RECORD, "ARNValidTill": "2099-01-01T00:00:00.000Z"}

    with patch(
        "app.services.dashboard.arn_lookup._fetch_arn_record",
        new=AsyncMock(return_value=active_record),
    ):
        result = asyncio.run(resolve_arn(db, "ARN-0671"))

    assert result.status == ArnStatus.ACTIVE
    assert result.distributor_name == "Multiplize Investment Services"
    cached = db.get(ArnDirectory, "ARN-0671")
    assert cached is not None and cached.status == ArnStatus.ACTIVE


def test_resolve_arn_writes_suspended_when_found_with_past_valid_till():
    import asyncio

    db = _session()
    expired_record = {**_REAL_ACTIVE_RECORD, "ARN": "0999", "ARNValidTill": "2020-01-01T00:00:00.000Z"}

    with patch(
        "app.services.dashboard.arn_lookup._fetch_arn_record",
        new=AsyncMock(return_value=expired_record),
    ):
        result = asyncio.run(resolve_arn(db, "ARN-0999"))

    assert result.status == ArnStatus.SUSPENDED


def test_resolve_arn_writes_invalid_when_amfi_has_no_record():
    import asyncio

    db = _session()

    with patch(
        "app.services.dashboard.arn_lookup._fetch_arn_record",
        new=AsyncMock(return_value=None),
    ):
        result = asyncio.run(resolve_arn(db, "ARN-9999999"))

    assert result.status == ArnStatus.INVALID
    assert result.distributor_name is None


def test_resolve_arn_writes_nothing_and_returns_none_on_fetch_failure():
    import asyncio

    db = _session()

    with patch(
        "app.services.dashboard.arn_lookup._fetch_arn_record",
        new=AsyncMock(side_effect=httpx.ConnectError("boom")),
    ):
        result = asyncio.run(resolve_arn(db, "ARN-5555"))

    assert result is None
    assert db.get(ArnDirectory, "ARN-5555") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `python -m pytest tests/services/dashboard/test_arn_lookup.py -v`
Expected: FAIL — `ModuleNotFoundError` / `ImportError`, `arn_lookup` module doesn't exist yet.

- [ ] **Step 3: Implement `arn_lookup.py`**

Create `backend/app/services/dashboard/arn_lookup.py`:

```python
"""On-demand AMFI ARN (distributor) name/status resolution — PRD-03 FR-11a.
A separate, small integration from nav.py's mfapi.in client, following the
identical shape: an isolated, mockable fetch function plus a cache-aware
wrapper. Unlike NAV there is no future scheduled refresh job replacing this
— on-demand, resolve-once-cache-forever is the permanent mechanism, per
the TDD's Background Jobs table ("ARN resolution stays on-demand...").

The endpoint below is real and was independently verified with live HTTP
calls during design (see the design spec and test_arn_lookup.py's captured
example) — not a guess. It is, however, undocumented/reverse-engineered
(same category of risk this project already accepts for AMFI's TER/AAUM
integrations per the TDD), which is exactly why every failure mode here
degrades to the raw ARN code (FR-11b) rather than blocking or erroring.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.models.enums import ArnStatus
from app.models.reference import ArnDirectory

AMFI_DISTRIBUTOR_SEARCH_URL = "https://www.amfiindia.com/api/distributor-agent"
AMFI_LOCATE_DISTRIBUTOR_REFERER = "https://www.amfiindia.com/locate-distributor"


def _bare_arn_digits(arn_code: str) -> str:
    """AMFI's endpoint matches on the bare numeric ARN, not the "ARN-"
    prefixed form this codebase stores in folios.arn_code — verified live:
    search=0671 returns an exact match, search=ARN-0671 returns zero
    results."""
    return re.sub(r"(?i)^ARN-", "", arn_code)


async def _fetch_arn_record(arn_code: str) -> dict | None:
    """Single-item lookup — never bulk/paginated (pageSize=1, one specific
    ARN per call). Returns AMFI's matched record dict, or None if AMFI has
    no record of this ARN at all (meta.total == 0)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            AMFI_DISTRIBUTOR_SEARCH_URL,
            params={"strOpt": "ALL", "search": _bare_arn_digits(arn_code), "page": 1, "pageSize": 1},
            headers={"Referer": AMFI_LOCATE_DISTRIBUTOR_REFERER},
        )
        resp.raise_for_status()
        payload = resp.json()

    records = payload.get("data", [])
    return records[0] if records else None


def _parse_amfi_valid_till(raw: str) -> date:
    # AMFI's ARNValidTill looks like "2027-10-18T00:00:00.000Z".
    return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%fZ").date()


async def resolve_arn(db: Session, arn_code: str) -> ArnDirectory | None:
    """Cache-first, resolve-once-forever (FR-11a: 'looked up once per ARN
    ever encountered platform-wide, not once per user') — an existing
    arn_directory row is returned as-is, no re-fetch, no TTL.

    On a cache miss, calls _fetch_arn_record and writes a definitive
    result. A transient failure (network/HTTP error) writes nothing and
    returns None, so the caller falls back to the raw ARN this one time
    and the next request retries — never cache a transient failure as a
    permanent value."""
    cached = db.get(ArnDirectory, arn_code)
    if cached is not None:
        return cached

    try:
        record = await _fetch_arn_record(arn_code)
    except httpx.HTTPError:
        return None

    if record is None:
        status = ArnStatus.INVALID
        distributor_name = None
    else:
        valid_till = _parse_amfi_valid_till(record["ARNValidTill"])
        status = ArnStatus.ACTIVE if valid_till >= date.today() else ArnStatus.SUSPENDED
        distributor_name = record["ARNHolderName"]

    row = ArnDirectory(
        arn_code=arn_code,
        distributor_name=distributor_name,
        status=status,
        last_checked_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return row
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/dashboard/test_arn_lookup.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dashboard/arn_lookup.py backend/tests/services/dashboard/test_arn_lookup.py
git commit -m "feat: AMFI ARN lookup client with arn_directory caching (PRD-03 FR-11a)"
```

---

### Task 2: Per-distributor FIFO comparison computation

**Files:**
- Create: `backend/app/services/dashboard/distributor_comparison.py`
- Modify: `backend/app/services/dashboard/schemas.py` (add `DistributorComparisonRow`)
- Test: `backend/tests/services/dashboard/test_distributor_comparison.py`

**Interfaces:**
- Consumes:
  - `app.services.dashboard.arn_lookup.resolve_arn(db, arn_code) -> ArnDirectory | None` (Task 1)
  - `app.services.dashboard.holdings._process_folio_lots(transactions: list[Transaction]) -> tuple[Decimal, Decimal, Decimal]` (existing — `(units_held, cost_basis, realized_gain)`)
  - `app.services.dashboard.holdings._LOT_CONSUMING_TYPES` (existing module constant — reused for the same-date ordering fix, never redefined)
  - `app.services.dashboard.nav.get_nav_on_or_before(db, scheme, on_date) -> tuple[Decimal, date] | None` (existing)
  - `app.models.folio.Folio` (existing — `household_member_id`, `scheme_id`, `arn_code: str | None`, `id`)
- Produces (for Task 3):
  - `async def compute_distributor_comparison(db: Session, household_member_id: uuid.UUID, scheme_id: uuid.UUID) -> list[DistributorComparisonRow]`
  - `DistributorComparisonRow` Pydantic model in `schemas.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/dashboard/test_distributor_comparison.py`:

```python
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import ArnStatus, PlanType, Relationship, TransactionType
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.models.user import HouseholdMember, User
from app.services.dashboard.distributor_comparison import compute_distributor_comparison


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


def _scheme(db):
    scheme = Scheme(
        id=uuid.uuid4(), amfi_code=uuid.uuid4().hex[:6], isin="INF123", name="HDFC Flexi Cap Fund",
        amc_name="HDFC AMC", sebi_category="Equity Scheme - Flexi Cap Fund",
    )
    db.add(scheme)
    db.commit()
    return scheme


def _folio(db, member, scheme, folio_number, arn_code):
    folio = Folio(
        id=uuid.uuid4(), household_member_id=member.id, scheme_id=scheme.id,
        folio_number=folio_number, arn_code=arn_code, plan_type=PlanType.REGULAR if arn_code else PlanType.DIRECT,
    )
    db.add(folio)
    db.commit()
    return folio


def _txn(db, folio, type_, on_date, amount, units, nav):
    txn = Transaction(id=uuid.uuid4(), folio_id=folio.id, import_id=uuid.uuid4(), type=type_, date=on_date, amount=amount, units=units, nav=nav)
    db.add(txn)
    db.commit()
    return txn


def _fake_resolve_arn(mapping):
    async def _resolve(db, arn_code):
        return mapping[arn_code]
    return _resolve


def test_compute_distributor_comparison_groups_by_arn_with_known_answer_fifo():
    """Known-answer test, hand-computed:
    ARN-11111: purchase 100u @ NAV 50 (cost 5000), redeem 40u @ NAV 70.
      FIFO: realized_gain = 40*(70-50) = 800. Remaining: 60u @ NAV 50 ->
      cost_basis 3000, units_held 60.
      current_nav=60 -> current_value=3600, unrealized=3600-3000=600,
      current_profit_total=800+600=1400, average_nav=3000/60=50.
    ARN-22222: purchase 50u @ NAV 40 (cost 2000), no redemption.
      units_held=50, cost_basis=2000, realized=0, current_value=3000,
      unrealized=1000, current_profit_total=1000, average_nav=40.
    Direct (arn_code=None): purchase 30u @ NAV 45 (cost 1350), no
      redemption. units_held=30, cost_basis=1350, current_value=1800,
      unrealized=450, current_profit_total=450, average_nav=45. No AMFI
      lookup for this bucket."""
    import asyncio

    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)

    folio_a = _folio(db, member, scheme, "AAA", "ARN-11111")
    _txn(db, folio_a, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))
    _txn(db, folio_a, TransactionType.REDEMPTION, date(2024, 6, 1), Decimal("2800.00"), Decimal("40.000"), Decimal("70.0000"))

    folio_b = _folio(db, member, scheme, "BBB", "ARN-22222")
    _txn(db, folio_b, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("2000.00"), Decimal("50.000"), Decimal("40.0000"))

    folio_c = _folio(db, member, scheme, "CCC", None)
    _txn(db, folio_c, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("1350.00"), Decimal("30.000"), Decimal("45.0000"))

    resolve_mock = AsyncMock(side_effect=_fake_resolve_arn({
        "ARN-11111": SimpleNamespace(distributor_name="Alpha Distributors", status=ArnStatus.ACTIVE),
        "ARN-22222": SimpleNamespace(distributor_name="Beta Advisors", status=ArnStatus.SUSPENDED),
    }))

    with patch(
        "app.services.dashboard.distributor_comparison.get_nav_on_or_before",
        new=AsyncMock(return_value=(Decimal("60.0000"), date(2024, 6, 1))),
    ), patch("app.services.dashboard.distributor_comparison.resolve_arn", new=resolve_mock):
        rows = asyncio.run(compute_distributor_comparison(db, member.id, scheme.id))

    assert len(rows) == 3
    assert resolve_mock.await_count == 2  # never called for the Direct (arn_code=None) bucket

    by_arn = {row.arn_code: row for row in rows}

    row_a = by_arn["ARN-11111"]
    assert row_a.distributor_name == "Alpha Distributors"
    assert row_a.arn_status == ArnStatus.ACTIVE
    assert row_a.units_held == "60.000"
    assert Decimal(row_a.amount_invested) == Decimal("3000.00")
    assert Decimal(row_a.realized_gain) == Decimal("800.00")
    assert Decimal(row_a.current_value) == Decimal("3600.00")
    assert Decimal(row_a.unrealized_gain) == Decimal("600.00")
    assert Decimal(row_a.current_profit_total) == Decimal("1400.00")
    assert Decimal(row_a.average_nav) == Decimal("50")

    row_b = by_arn["ARN-22222"]
    assert row_b.distributor_name == "Beta Advisors"
    assert row_b.arn_status == ArnStatus.SUSPENDED
    assert row_b.units_held == "50.000"
    assert Decimal(row_b.current_profit_total) == Decimal("1000.00")

    row_c = by_arn[None]
    assert row_c.distributor_name is None
    assert row_c.arn_status is None
    assert row_c.units_held == "30.000"
    assert Decimal(row_c.current_profit_total) == Decimal("450.00")


def test_compute_distributor_comparison_returns_empty_when_member_holds_nothing_of_scheme():
    import asyncio

    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)

    rows = asyncio.run(compute_distributor_comparison(db, member.id, scheme.id))
    assert rows == []


def test_compute_distributor_comparison_returns_empty_when_nav_unavailable():
    import asyncio

    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme, "AAA", "ARN-11111")
    _txn(db, folio, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))

    with patch(
        "app.services.dashboard.distributor_comparison.get_nav_on_or_before",
        new=AsyncMock(return_value=None),
    ):
        rows = asyncio.run(compute_distributor_comparison(db, member.id, scheme.id))

    assert rows == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/dashboard/test_distributor_comparison.py -v`
Expected: FAIL — `distributor_comparison` module and `DistributorComparisonRow` don't exist yet.

- [ ] **Step 3: Add `DistributorComparisonRow` to `schemas.py`**

In `backend/app/services/dashboard/schemas.py`, add near `HoldingRow` (after its definition), and update the top import line to include `ArnStatus`:

```python
from app.models.enums import ArnStatus, PlanType, Relationship, TransactionType
```

```python
class DistributorComparisonRow(BaseModel):
    arn_code: str | None
    distributor_name: str | None
    arn_status: ArnStatus | None
    units_held: str
    average_nav: str | None
    amount_invested: str
    current_value: str
    current_profit_total: str
    realized_gain: str
    unrealized_gain: str
```

- [ ] **Step 4: Implement `distributor_comparison.py`**

Create `backend/app/services/dashboard/distributor_comparison.py`:

```python
"""Distributor comparison — PRD-03 FR-11. Groups a member's holdings of one
scheme by which ARN (distributor) they were bought through, reusing the
same FIFO engine as holdings.py one level finer: by (member, scheme, ARN)
instead of just (member, scheme).

Unlike holdings.py, a group with zero units held (e.g. fully redeemed
through one distributor) is still included, not dropped — this view is
about comparing performance across distributors, including a distributor
you've since fully exited, not just what's currently held (holdings.py's
own zero-unit drop is specific to that live-holdings-table's purpose).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.services.dashboard.arn_lookup import resolve_arn
from app.services.dashboard.holdings import _LOT_CONSUMING_TYPES, _process_folio_lots
from app.services.dashboard.nav import get_nav_on_or_before
from app.services.dashboard.schemas import DistributorComparisonRow


async def compute_distributor_comparison(
    db: Session, household_member_id: uuid.UUID, scheme_id: uuid.UUID
) -> list[DistributorComparisonRow]:
    folios = (
        db.query(Folio)
        .filter(Folio.household_member_id == household_member_id, Folio.scheme_id == scheme_id)
        .all()
    )
    if not folios:
        return []

    scheme = db.get(Scheme, scheme_id)
    nav_result = await get_nav_on_or_before(db, scheme, date.today())
    if nav_result is None:
        return []
    current_nav, _current_nav_date = nav_result

    grouped: dict[str | None, list[Folio]] = defaultdict(list)
    for folio in folios:
        grouped[folio.arn_code].append(folio)

    rows: list[DistributorComparisonRow] = []
    for arn_code, group_folios in grouped.items():
        total_units = Decimal("0")
        total_cost = Decimal("0")
        total_realized = Decimal("0")

        for folio in group_folios:
            transactions = (
                db.query(Transaction)
                .filter(Transaction.folio_id == folio.id)
                .order_by(
                    Transaction.date,
                    # Same same-date purchase-before-redemption tiebreak as
                    # holdings.py — reused via the shared constant, not
                    # redefined, so the two stay in lockstep by construction.
                    case((Transaction.type.in_(_LOT_CONSUMING_TYPES), 1), else_=0),
                    Transaction.id,
                )
                .all()
            )
            units_held, cost_basis, realized_gain = _process_folio_lots(transactions)
            total_units += units_held
            total_cost += cost_basis
            total_realized += realized_gain

        current_value = total_units * current_nav
        unrealized_gain = current_value - total_cost
        current_profit_total = total_realized + unrealized_gain
        average_nav = (total_cost / total_units) if total_units else None

        distributor_name = None
        arn_status = None
        if arn_code is not None:
            resolved = await resolve_arn(db, arn_code)
            if resolved is not None:
                distributor_name = resolved.distributor_name
                arn_status = resolved.status

        rows.append(
            DistributorComparisonRow(
                arn_code=arn_code,
                distributor_name=distributor_name,
                arn_status=arn_status,
                units_held=str(total_units),
                average_nav=str(average_nav) if average_nav is not None else None,
                amount_invested=str(total_cost),
                current_value=str(current_value),
                current_profit_total=str(current_profit_total),
                realized_gain=str(total_realized),
                unrealized_gain=str(unrealized_gain),
            )
        )
    return rows
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/services/dashboard/test_distributor_comparison.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full dashboard test suite to confirm no regression in shared code**

Run: `python -m pytest tests/services/dashboard/ -v`
Expected: PASS (all existing dashboard tests plus the new ones — confirms
reusing `_process_folio_lots`/`_LOT_CONSUMING_TYPES`/`get_nav_on_or_before`
didn't disturb `holdings.py`/`nav.py`'s own tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/dashboard/distributor_comparison.py backend/app/services/dashboard/schemas.py backend/tests/services/dashboard/test_distributor_comparison.py
git commit -m "feat: per-distributor FIFO comparison computation (PRD-03 FR-11)"
```

---

### Task 3: API route

**Files:**
- Modify: `backend/app/api/dashboard.py`
- Test: `backend/tests/api/test_dashboard_distributor_comparison_route.py`

**Interfaces:**
- Consumes:
  - `app.services.dashboard.distributor_comparison.compute_distributor_comparison(db, household_member_id, scheme_id) -> list[DistributorComparisonRow]` (Task 2)
  - `app.services.dashboard.schemas.DistributorComparisonRow` (Task 2)
  - `app.services.dashboard.household_members.get_household_member_for_user` (existing, already imported in `dashboard.py`)
- Produces: `GET /household-members/{member_id}/schemes/{scheme_id}/distributor-comparison`

- [ ] **Step 1: Write the failing route tests**

Create `backend/tests/api/test_dashboard_distributor_comparison_route.py`:

```python
import uuid


def _authed_headers_and_member(client, phone: str) -> tuple[dict[str, str], str]:
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    member = client.post("/household-members", json={"name": "Self", "relationship": "self"}, headers=headers).json()
    return headers, member["id"]


def test_distributor_comparison_route_requires_auth(client):
    scheme_id = uuid.uuid4()
    response = client.get(f"/household-members/00000000-0000-0000-0000-000000000000/schemes/{scheme_id}/distributor-comparison")
    assert response.status_code == 401


def test_distributor_comparison_route_404s_for_another_users_member(client):
    _, other_member_id = _authed_headers_and_member(client, "+919000000004")
    headers, _ = _authed_headers_and_member(client, "+919000000005")
    scheme_id = uuid.uuid4()

    response = client.get(f"/household-members/{other_member_id}/schemes/{scheme_id}/distributor-comparison", headers=headers)
    assert response.status_code == 404


def test_distributor_comparison_route_returns_empty_list_for_scheme_member_does_not_hold(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000006")
    scheme_id = uuid.uuid4()

    response = client.get(f"/household-members/{member_id}/schemes/{scheme_id}/distributor-comparison", headers=headers)
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_dashboard_distributor_comparison_route.py -v`
Expected: FAIL — 404 route not found (or similar) since the route doesn't exist yet.

- [ ] **Step 3: Add the route to `dashboard.py`**

In `backend/app/api/dashboard.py`, update the imports:

```python
from app.services.dashboard.distributor_comparison import compute_distributor_comparison
from app.services.dashboard.holdings import compute_holdings
```

(insert the new import in alphabetical position among the existing
`app.services.dashboard.*` imports), and add `DistributorComparisonRow` to
the existing `from app.services.dashboard.schemas import (...)` block:

```python
from app.services.dashboard.schemas import (
    AggregateAllocationResponse,
    AggregateCashFlowResponse,
    AggregateHoldingsResponse,
    AggregateSipsResponse,
    AggregateSnapshotsResponse,
    AllocationSummary,
    CashFlowEntry,
    DistributorComparisonRow,
    HoldingRow,
    HouseholdMemberCreate,
    HouseholdMemberResponse,
    SipRow,
    SnapshotRow,
)
```

Then add the route, immediately after `get_member_holdings` (i.e. right
before the `/household-members/{member_id}/allocation` route):

```python
@router.get(
    "/household-members/{member_id}/schemes/{scheme_id}/distributor-comparison",
    response_model=list[DistributorComparisonRow],
)
async def get_member_distributor_comparison(
    member_id: uuid.UUID,
    scheme_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if get_household_member_for_user(db, user.id, member_id) is None:
        raise HTTPException(status_code=404, detail="Household member not found.")
    return await compute_distributor_comparison(db, member_id, scheme_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_dashboard_distributor_comparison_route.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full backend test suite**

Run (from `backend/`): `python -m pytest -m "not postgres" -v`
Expected: PASS — every existing test plus this plan's new tests, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/dashboard.py backend/tests/api/test_dashboard_distributor_comparison_route.py
git commit -m "feat: distributor comparison API route (PRD-03 FR-11)"
```

## Self-Review

**Spec coverage:**
- FR-11 (comparison by distributor) — Task 2/3.
- FR-11a (on-demand lookup + platform-wide cache) — Task 1.
- FR-11b (never blocks, raw ARN fallback) — Task 1's `resolve_arn` returning
  `None` on failure, Task 2 rendering the row regardless.
- FR-11c (suspended/invalid trust signal) — Task 1's status mapping,
  surfaced via `arn_status` on every row in Task 2/3.
- Spec's endpoint contract, caching policy, status-mapping, and error
  handling sections are each implemented by a specific step above — no gaps
  found.

**Placeholder scan:** none — every step has complete, runnable code.

**Time-bomb check:** the real captured `ARNValidTill` (2027-10-18) is used
only in a doc comment and the not-yet-fetched/cached test — the ACTIVE and
SUSPENDED test payloads use synthetic 2099/2020 dates instead, so neither
test starts failing once the real captured date passes.

**Type consistency:** `resolve_arn(db, arn_code) -> ArnDirectory | None`
(Task 1) matches its only caller in Task 2 exactly. `DistributorComparisonRow`'s
fields (Task 2, `schemas.py`) match every field Task 2's implementation
constructs and every field Task 3's route test implicitly exercises via the
response model. `_LOT_CONSUMING_TYPES`/`_process_folio_lots` imported from
`holdings.py`, never redefined, in both Task 2's implementation and its
inline same-date-ordering comment.
