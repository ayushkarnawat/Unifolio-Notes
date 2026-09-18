# Phase 4 Part 1: Analytics Category Allocation (FR-2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add granular SEBI-category allocation to the Analytics service (PRD-04
FR-2) — the first of five Phase 4 subsystems (see the companion design doc,
`2026-08-10-phase-4-analytics-backend-design.md`, for full research and the
overall build order). AMC allocation (FR-1) already exists at Dashboard's
`GET /household-members/{id}/allocation` (`by_amc`) — this plan does not rebuild
it, only adds the granular category view, and re-exposes `by_amc` alongside it
under the Analytics service's own route for a single analytics-tab response.

**Architecture:** One new service module, `app/services/analytics/allocation.py`,
computing holdings once via the existing `compute_holdings` engine and bucketing
by two dimensions in a single pass (raw `sebi_category` string, and `amc_name`).
Two new routes on the existing (currently-empty) `analytics.router`: per-member
and family-aggregate, mirroring `app/api/dashboard.py`'s exact structure
(auth dependency, 404-on-unknown-member check, family aggregate wrapping
`MemberStatus` per PRD-03 FR-10's "never silently exclude a member" rule).

**Tech Stack:** FastAPI, SQLAlchemy 2.0 ORM, Pydantic, pytest — no new
dependencies.

## Global Constraints

- `Decimal`, never `float`, for every money value (CLAUDE.md non-negotiable) —
  all money fields cross the API boundary as `str`, matching every existing
  Dashboard schema.
- TDD: write the failing test before the implementation for every step below.
- Reuse `compute_holdings` (`app/services/dashboard/holdings.py`) — do not
  duplicate the FIFO engine or NAV-fetch logic.
- Reuse `AllocationBucket` (`app/services/dashboard/schemas.py`) for bucket
  shape — it is already generic (`label`, `current_value`, `percentage`), no
  reason to redefine it in the Analytics service.
- Family aggregation is parameterized by a list of member IDs on the same
  function — no separate per-member/family code path for the computation
  itself (established project pattern, e.g. `compute_holdings`,
  `compute_allocation`).

---

### Task 1: `compute_category_allocation` service function

**Files:**
- Create: `backend/app/services/analytics/__init__.py` (empty)
- Create: `backend/app/services/analytics/schemas.py`
- Create: `backend/app/services/analytics/allocation.py`
- Test: `backend/tests/services/analytics/__init__.py` (empty)
- Test: `backend/tests/services/analytics/test_allocation.py`

**Interfaces:**
- Consumes: `compute_holdings(db, household_member_ids) -> list[HoldingRow]`
  (`app.services.dashboard.holdings`); `AllocationBucket`
  (`app.services.dashboard.schemas`); `Scheme` (`app.models.reference`).
- Produces: `AnalyticsAllocationSummary` (Pydantic model, fields
  `by_category: list[AllocationBucket]`, `by_amc: list[AllocationBucket]`,
  `total_value: str`) and
  `async def compute_category_allocation(db: Session, household_member_ids: list[uuid.UUID]) -> AnalyticsAllocationSummary`
  in `app.services.analytics.allocation` — Task 2 and Task 3 both import these
  exact names.

- [ ] **Step 1: Write the failing test for the empty case**

```python
# backend/tests/services/analytics/test_allocation.py
import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import Relationship
from app.models.user import HouseholdMember, User
from app.services.analytics.allocation import compute_category_allocation


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


def test_compute_category_allocation_empty_when_no_holdings():
    db = _session()
    member = _household_member(db)
    summary = asyncio.run(compute_category_allocation(db, [member.id]))
    assert summary.by_category == []
    assert summary.by_amc == []
    assert Decimal(summary.total_value) == Decimal("0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/services/analytics/test_allocation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.analytics'`

- [ ] **Step 3: Create the package and schema**

```python
# backend/app/services/analytics/__init__.py
```

```python
# backend/app/services/analytics/schemas.py
from __future__ import annotations

from pydantic import BaseModel

from app.services.dashboard.schemas import AllocationBucket, MemberStatus


class AnalyticsAllocationSummary(BaseModel):
    by_category: list[AllocationBucket]
    by_amc: list[AllocationBucket]
    total_value: str


class AggregateAnalyticsAllocationResponse(BaseModel):
    members: list[MemberStatus]
    allocation: AnalyticsAllocationSummary
```

- [ ] **Step 4: Write minimal implementation**

```python
# backend/app/services/analytics/allocation.py
"""Granular SEBI-category allocation — PRD-04 FR-2. AMC allocation (FR-1)
already exists at Dashboard's compute_allocation (by_amc); re-exposed here
alongside the new by_category view so the Analytics tab has one response to
render, without duplicating the holdings/NAV computation to get it."""

from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.reference import Scheme
from app.services.analytics.schemas import AnalyticsAllocationSummary
from app.services.dashboard.holdings import compute_holdings
from app.services.dashboard.schemas import AllocationBucket


def _to_buckets(grouped: dict[str, Decimal], total_value: Decimal) -> list[AllocationBucket]:
    buckets = []
    for label, value in grouped.items():
        percentage = (value / total_value * 100) if total_value else Decimal("0")
        buckets.append(
            AllocationBucket(
                label=label,
                current_value=str(value),
                percentage=str(percentage.quantize(Decimal("0.01"))),
            )
        )
    return buckets


async def compute_category_allocation(
    db: Session, household_member_ids: list[uuid.UUID]
) -> AnalyticsAllocationSummary:
    holdings = await compute_holdings(db, household_member_ids)
    total_value = sum((Decimal(h.current_value) for h in holdings), Decimal("0"))

    # sebi_category isn't on HoldingRow — one batch query for every scheme in
    # this holding set, same pattern as dashboard/allocation.py.
    scheme_ids = {uuid.UUID(h.scheme_id) for h in holdings}
    categories = (
        {s.id: s.sebi_category for s in db.query(Scheme).filter(Scheme.id.in_(scheme_ids)).all()}
        if scheme_ids
        else {}
    )

    by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_amc: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for holding in holdings:
        value = Decimal(holding.current_value)
        by_amc[holding.amc_name] += value
        category = categories.get(uuid.UUID(holding.scheme_id), "Unclassified")
        by_category[category] += value

    return AnalyticsAllocationSummary(
        by_category=_to_buckets(by_category, total_value),
        by_amc=_to_buckets(by_amc, total_value),
        total_value=str(total_value),
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/services/analytics/test_allocation.py -v`
Expected: PASS

- [ ] **Step 6: Write the failing test for granular category bucketing**

Append to `backend/tests/services/analytics/test_allocation.py`:

```python
from unittest.mock import AsyncMock, patch
from datetime import date

from app.models.enums import PlanType, TransactionType
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction


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


def test_compute_category_allocation_buckets_by_granular_sebi_category():
    db = _session()
    member = _household_member(db)
    flexicap = _scheme(db, amc_name="HDFC AMC", sebi_category="Equity Scheme - Flexi Cap Fund")
    largecap = _scheme(db, amc_name="HDFC AMC", sebi_category="Equity Scheme - Large Cap Fund")
    _folio_with_purchase(db, member, flexicap, Decimal("6000.00"), Decimal("100.000"), Decimal("60.0000"))
    _folio_with_purchase(db, member, largecap, Decimal("4000.00"), Decimal("100.000"), Decimal("40.0000"))

    with patch(
        "app.services.dashboard.holdings.get_nav_on_or_before",
        new=AsyncMock(side_effect=lambda db_, scheme, on_date: (Decimal("60.0000"), date(2024, 6, 1)) if scheme.id == flexicap.id else (Decimal("40.0000"), date(2024, 6, 1))),
    ), patch("app.services.dashboard.holdings.get_previous_nav_from_cache", return_value=None):
        summary = asyncio.run(compute_category_allocation(db, [member.id]))

    by_category = {b.label: Decimal(b.current_value) for b in summary.by_category}
    assert by_category["Equity Scheme - Flexi Cap Fund"] == Decimal("6000.00")
    assert by_category["Equity Scheme - Large Cap Fund"] == Decimal("4000.00")
    # Both schemes share an AMC — by_amc collapses to one bucket, distinct
    # from the two granular category buckets above.
    assert len(summary.by_amc) == 1
    assert Decimal(summary.by_amc[0].current_value) == Decimal("10000.00")
```

- [ ] **Step 7: Run test to verify it fails first, confirming the test is real**

Run: `cd backend && pytest tests/services/analytics/test_allocation.py::test_compute_category_allocation_buckets_by_granular_sebi_category -v`
Expected: PASS immediately (Step 4's implementation already handles this case) —
if it fails, fix `allocation.py` before proceeding; do not skip this
verification just because Step 4 looks sufficient.

- [ ] **Step 8: Run the full test file**

Run: `cd backend && pytest tests/services/analytics/test_allocation.py -v`
Expected: 2 passed

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/analytics backend/tests/services/analytics
git commit -m "feat: add Analytics category allocation service (PRD-04 FR-2)"
```

---

### Task 2: Per-member analytics allocation route

**Files:**
- Modify: `backend/app/api/analytics.py`
- Test: `backend/tests/api/test_analytics_allocation_route.py`

**Interfaces:**
- Consumes: `compute_category_allocation` and `AnalyticsAllocationSummary` from
  Task 1; `get_current_user` (`app.services.auth.session`);
  `get_household_member_for_user` (`app.services.dashboard.household_members`) —
  same 404-on-unknown-member pattern as every existing Dashboard route.
- Produces: `GET /analytics/household-members/{member_id}/allocation` — Task 3's
  tests hit the sibling aggregate route, not this one, so no direct code
  dependency, but both live in the same router file.

- [ ] **Step 1: Write the failing route test**

```python
# backend/tests/api/test_analytics_allocation_route.py
def _authed_headers_and_member(client, phone: str):
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    member = client.post("/household-members", json={"name": "Self", "relationship": "self"}, headers=headers).json()
    return headers, member["id"]


def test_analytics_allocation_route_requires_auth(client):
    response = client.get("/analytics/household-members/00000000-0000-0000-0000-000000000000/allocation")
    assert response.status_code == 401


def test_analytics_allocation_route_404_for_unknown_member(client):
    headers, _ = _authed_headers_and_member(client, "+919000000020")
    response = client.get(
        "/analytics/household-members/00000000-0000-0000-0000-000000000000/allocation", headers=headers
    )
    assert response.status_code == 404


def test_analytics_allocation_route_returns_empty_summary_for_member_with_no_holdings(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000021")
    response = client.get(f"/analytics/household-members/{member_id}/allocation", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["by_category"] == []
    assert body["by_amc"] == []
    assert body["total_value"] == "0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_analytics_allocation_route.py -v`
Expected: FAIL — all three requests 404 (route doesn't exist yet) instead of
the expected 401/404/200.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/api/analytics.py
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.db.session import get_db
from app.models.user import User
from app.services.analytics.allocation import compute_category_allocation
from app.services.analytics.schemas import AnalyticsAllocationSummary
from app.services.auth.session import get_current_user
from app.services.dashboard.household_members import get_household_member_for_user

router = APIRouter(prefix="/analytics", tags=["analytics"])  # for analytics related endpoints


@router.get(
    "/household-members/{member_id}/allocation", response_model=AnalyticsAllocationSummary
)
async def get_member_category_allocation(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if get_household_member_for_user(db, user.id, member_id) is None:
        raise HTTPException(status_code=404, detail="Household member not found.")
    return await compute_category_allocation(db, [member_id])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/api/test_analytics_allocation_route.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/analytics.py backend/tests/api/test_analytics_allocation_route.py
git commit -m "feat: add per-member analytics category allocation route"
```

---

### Task 3: Family aggregate analytics allocation

**Files:**
- Modify: `backend/app/services/analytics/allocation.py`
- Modify: `backend/app/api/analytics.py`
- Test: `backend/tests/services/analytics/test_allocation.py`
- Test: `backend/tests/api/test_analytics_allocation_route.py`

**Interfaces:**
- Consumes: `get_member_statuses` (`app.services.dashboard.aggregate`) —
  reused as-is, not duplicated; `list_household_members`
  (`app.services.dashboard.household_members`); `AggregateAnalyticsAllocationResponse`
  from Task 1's `schemas.py`.
- Produces: `async def get_aggregate_category_allocation(db: Session, user_id: uuid.UUID) -> AggregateAnalyticsAllocationResponse`
  and route `GET /analytics/household/aggregate/allocation`.

- [ ] **Step 1: Write the failing service test**

Append to `backend/tests/services/analytics/test_allocation.py`:

```python
from app.services.analytics.allocation import get_aggregate_category_allocation


def test_get_aggregate_category_allocation_lists_member_status_with_no_data():
    db = _session()
    member = _household_member(db)
    result = asyncio.run(get_aggregate_category_allocation(db, member.user_id))
    assert len(result.members) == 1
    assert result.members[0].has_data is False
    assert result.allocation.by_category == []
    assert Decimal(result.allocation.total_value) == Decimal("0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/services/analytics/test_allocation.py::test_get_aggregate_category_allocation_lists_member_status_with_no_data -v`
Expected: FAIL with `ImportError: cannot import name 'get_aggregate_category_allocation'`

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/services/analytics/allocation.py` (below
`compute_category_allocation`):

```python
from app.services.analytics.schemas import AggregateAnalyticsAllocationResponse
from app.services.dashboard.aggregate import get_member_statuses
from app.services.dashboard.household_members import list_household_members


async def get_aggregate_category_allocation(
    db: Session, user_id: uuid.UUID
) -> AggregateAnalyticsAllocationResponse:
    members = list_household_members(db, user_id)
    statuses = get_member_statuses(db, user_id)
    allocation = await compute_category_allocation(db, [m.id for m in members])
    return AggregateAnalyticsAllocationResponse(members=statuses, allocation=allocation)
```

(Add the two new imports to the top of the file alongside the existing ones,
rather than inline — shown inline here only to make the diff obvious.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/services/analytics/test_allocation.py -v`
Expected: 3 passed

- [ ] **Step 5: Write the failing route test**

Append to `backend/tests/api/test_analytics_allocation_route.py`:

```python
def test_analytics_aggregate_allocation_route_lists_members(client):
    headers, _ = _authed_headers_and_member(client, "+919000000022")
    response = client.get("/analytics/household/aggregate/allocation", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["members"]) == 1
    assert body["members"][0]["has_data"] is False
    assert body["allocation"]["by_category"] == []


def test_analytics_aggregate_allocation_route_requires_auth(client):
    response = client.get("/analytics/household/aggregate/allocation")
    assert response.status_code == 401
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_analytics_allocation_route.py -v`
Expected: the two new tests FAIL with 404 (route not registered yet); the
three existing tests from Task 2 still pass.

- [ ] **Step 7: Write minimal implementation**

Add to `backend/app/api/analytics.py`:

```python
from app.services.analytics.allocation import (
    compute_category_allocation,
    get_aggregate_category_allocation,
)
from app.services.analytics.schemas import (
    AggregateAnalyticsAllocationResponse,
    AnalyticsAllocationSummary,
)


@router.get(
    "/household/aggregate/allocation", response_model=AggregateAnalyticsAllocationResponse
)
async def get_household_aggregate_category_allocation(
    user: User = Depends(get_current_user), db: DbSession = Depends(get_db)
):
    return await get_aggregate_category_allocation(db, user.id)
```

(Merge the two import blocks with Task 2's existing ones at the top of the
file — one `from app.services.analytics.allocation import ...` line and one
`from app.services.analytics.schemas import ...` line, not two of each.)

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && pytest tests/api/test_analytics_allocation_route.py -v`
Expected: 5 passed

- [ ] **Step 9: Run the full backend suite**

Run: `cd backend && pytest -v`
Expected: all tests pass (156 pre-existing + this task's new tests), 0
failures, 0 errors.

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/analytics/allocation.py backend/app/api/analytics.py backend/tests/services/analytics/test_allocation.py backend/tests/api/test_analytics_allocation_route.py
git commit -m "feat: add family-aggregate analytics category allocation route"
```

---

## Self-Review

**1. Spec coverage.** FR-2 (granular SEBI category allocation, per-member and
family): Task 1 + Task 2 + Task 3. FR-1 (AMC allocation) is not rebuilt — Task
1 re-exposes it (`by_amc`) inside the same Analytics response for a single
analytics-tab payload, sourced from the same holdings computation, not
duplicated logic. No other FR is in scope for this plan (see the design doc's
build order — TER, benchmark, category ranking, and the scorer are separate
plan files).

**2. Placeholder scan.** No TBD/TODO, no "add error handling", every step has
real code, no reference to a function not defined earlier in this plan.

**3. Type consistency.** `AnalyticsAllocationSummary`, `AggregateAnalyticsAllocationResponse`,
`compute_category_allocation`, `get_aggregate_category_allocation` are each
defined once (Task 1 or Task 3) and referenced identically in every later
step.
