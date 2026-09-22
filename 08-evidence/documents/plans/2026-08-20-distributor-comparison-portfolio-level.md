# Distributor Comparison — Portfolio-Level Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reframe Distributor Comparison from fund-scoped (one member + one
scheme) to portfolio-wide (every held scheme, per member and family
aggregate), with expandable per-scheme breakdown rows, on both desktop and
mobile, without reintroducing an N+1 query pattern or breaking
`compute_holdings`'s existing cache.

**Architecture:** `compute_distributor_comparison(db, household_member_ids)`
is rewritten to batch-fetch folios/transactions/NAVs in one pass each (no
per-folio or per-scheme round trips), group by `(arn_code, scheme_id,
member_id)`, roll grouped `DistributorSchemeBreakdown` rows up into
`DistributorPortfolioRow` totals per ARN, and cache the result with a
TTL/lock pattern that reuses `holdings.py`'s existing
`_holdings_cache_generation` invalidation signal. Two new routes
(member-scoped, aggregate) replace the one old fund-scoped route. The
desktop modal and mobile view are both rebuilt around expandable
distributor rows, triggered from the Holdings section header instead of
from inside a single fund's detail view.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic (backend), React + Vite +
TypeScript + Tailwind (frontend), pytest (backend tests), Vitest +
Testing Library (frontend tests).

**Spec:** `Docs/superpowers/specs/2026-08-20-distributor-comparison-portfolio-level-design.md`

## Global Constraints

- `Decimal`, never `float`, for every money/units/NAV value, including all
  new rollup arithmetic and every test fixture.
- No DB schema change — `folios.arn_code` already exists; this is
  service/schema/route/frontend restructuring only.
- Do not modify `compute_holdings`'s own pre-existing per-folio
  `Transaction` N+1 query — explicitly out of scope (see spec's Scope
  section). The new `compute_distributor_comparison` must be batched from
  the start, but `holdings.py` itself is untouched except for exporting
  `_holdings_cache_generation` for reuse (it's already a module-level name,
  no code change needed there — just imported by the new module).
- `resolve_arn`/`arn_lookup.py` reused exactly as-is, no changes.
- The old fund-scoped route
  (`/household-members/{member_id}/schemes/{scheme_id}/distributor-comparison`)
  and `DistributorComparisonRow` schema/TS type are deleted, not deprecated
  — nothing else references them once removed.

---

## File Structure

**Backend:**
- Modify: `backend/app/services/dashboard/schemas.py` — replace
  `DistributorComparisonRow` with `DistributorSchemeBreakdown` +
  `DistributorPortfolioRow`; add `AggregateDistributorComparisonResponse`.
- Modify: `backend/app/services/dashboard/distributor_comparison.py` —
  full rewrite: batched fetch, per-ARN grouping/rollup, new TTL cache.
- Modify: `backend/app/services/dashboard/aggregate.py` — add
  `get_aggregate_distributor_comparison`.
- Modify: `backend/app/api/dashboard.py` — remove old route, add two new
  routes.
- Modify: `backend/tests/services/dashboard/test_distributor_comparison.py`
  — full rewrite for the new signature/behavior.
- Modify: `backend/tests/api/test_dashboard_distributor_comparison_route.py`
  — full rewrite for the two new routes + old-route-gone assertion.

**Frontend:**
- Modify: `frontend/src/features/dashboard/types.ts` — replace
  `DistributorComparisonRow` with `DistributorSchemeBreakdown` +
  `DistributorPortfolioRow` + `AggregateDistributorComparisonResponse`.
- Modify: `frontend/src/features/dashboard/api.ts` — replace
  `getDistributorComparison` with `getMemberDistributorComparison` +
  `getAggregateDistributorComparison`.
- Modify: `frontend/src/features/dashboard/FundDetailModal.tsx` — remove
  the "Compare Distributors" trigger and `onCompareDistributors` prop.
- Modify: `frontend/src/features/dashboard/FundDetailModal.test.tsx` —
  drop the removed prop/assertions.
- Modify: `frontend/src/features/dashboard/DistributorComparisonModal.tsx`
  — rebuilt around `viewMode`/`memberId` fetch + expandable distributor
  rows.
- Modify: `frontend/src/features/dashboard/DistributorComparisonModal.module.css`
  — add expand/collapse and nested-row styles.
- Modify: `frontend/src/features/dashboard/DistributorComparisonModal.test.tsx`
  — rewritten for the new props/fetch/expand behavior.
- Modify: `frontend/src/features/dashboard/DashboardView.tsx` — remove old
  `comparisonModalState`/`onCompareDistributors` plumbing; add a Holdings-
  header trigger button + simplified modal wiring.
- Modify: `frontend/src/features/dashboard/DashboardView.test.tsx` —
  replace the old fund-scoped trigger test with a Holdings-header-button
  test.
- Modify: `frontend/src/mobile/features/holdings/MobileFundDetailView.tsx`
  — remove the trigger button, state, and embedded view.
- Modify: `frontend/src/mobile/features/holdings/MobileDistributorComparisonView.tsx`
  — rebuilt around `viewMode`/`memberId` fetch + expandable cards.
- Modify: `frontend/src/mobile/features/holdings/MobileDistributorComparisonView.test.tsx`
  — rewritten for the new props/fetch/expand behavior.
- Modify: `frontend/src/mobile/features/holdings/MobileHoldingsView.tsx` —
  add a Holdings-header trigger + state + view render, using its own
  existing `viewMode`/`selectedMemberId`.
- Modify: `frontend/src/mobile/features/holdings/MobileHoldingsView.test.tsx`
  — add a test for the new trigger.
- Modify: `frontend/src/mobile/features/dashboard/MobileDashboardView.tsx`
  — same trigger addition, off its own embedded Holdings section header.
- Modify: `frontend/src/mobile/features/dashboard/MobileDashboardView.test.tsx`
  — add a test for the new trigger.

---

### Task 1: Backend — rewrite `compute_distributor_comparison` (schemas + service + cache)

**Files:**
- Modify: `backend/app/services/dashboard/schemas.py:42-53` (the existing
  `DistributorComparisonRow` class)
- Modify: `backend/app/services/dashboard/distributor_comparison.py` (full
  rewrite)
- Test: `backend/tests/services/dashboard/test_distributor_comparison.py`
  (full rewrite)

**Interfaces:**
- Consumes: `_process_folio_lots(transactions: list[Transaction]) ->
  tuple[Decimal, Decimal, Decimal]` and `_LOT_CONSUMING_TYPES: set[TransactionType]`
  and `_holdings_cache_generation: dict[uuid.UUID, int]` (all from
  `app.services.dashboard.holdings`, unchanged); `resolve_arn(db, arn_code)
  -> ArnDirectory | None` (from `app.services.dashboard.arn_lookup`,
  unchanged); `get_navs_on_or_before(db, scheme_date_pairs: list[tuple[Scheme,
  date]]) -> dict[uuid.UUID, tuple[Decimal, date] | None]` (from
  `app.services.dashboard.nav`, unchanged).
- Produces: `compute_distributor_comparison(db: Session,
  household_member_ids: list[uuid.UUID]) -> list[DistributorPortfolioRow]`
  — consumed by Task 2's routes. `DistributorSchemeBreakdown` and
  `DistributorPortfolioRow` Pydantic models — consumed by Task 2's route
  response models and Task 3's frontend types (field-for-field mirror).

- [ ] **Step 1: Replace the schema in `schemas.py`**

In `backend/app/services/dashboard/schemas.py`, replace lines 42-53
(the existing `class DistributorComparisonRow(BaseModel): ...` block) with:

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

Then, at the end of the file (after `class AggregateSnapshotsResponse`),
add:

```python


class AggregateDistributorComparisonResponse(BaseModel):
    members: list[MemberStatus]
    rows: list[DistributorPortfolioRow]
```

- [ ] **Step 2: Write the failing tests**

Replace the entire contents of
`backend/tests/services/dashboard/test_distributor_comparison.py` with:

```python
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import ArnStatus, PlanType, Relationship, TransactionType
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.models.user import HouseholdMember, User
from app.services.dashboard.distributor_comparison import (
    _distributor_cache,
    compute_distributor_comparison,
    invalidate_holdings_cache,
)


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
        id=uuid.uuid4(), amfi_code=amfi_code or uuid.uuid4().hex[:6], isin=uuid.uuid4().hex[:12], name=name,
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


def _mock_nav_batch(results_by_scheme_id):
    async def lookup(_db, scheme_date_pairs):
        return {scheme.id: results_by_scheme_id[scheme.id] for scheme, _ in scheme_date_pairs}
    return AsyncMock(side_effect=lookup)


def test_compute_distributor_comparison_rolls_up_scheme_breakdowns_by_arn_with_known_answer_fifo():
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
      lookup for this bucket.
    Each ARN's DistributorPortfolioRow totals must equal the sum of its
    (single, here) DistributorSchemeBreakdown, since each ARN only has one
    scheme group in this fixture."""
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

    with (
        patch(
            "app.services.dashboard.distributor_comparison.get_navs_on_or_before",
            new=_mock_nav_batch({scheme.id: (Decimal("60.0000"), date(2024, 6, 1))}),
        ),
        patch("app.services.dashboard.distributor_comparison.resolve_arn", new=resolve_mock),
    ):
        rows = asyncio.run(compute_distributor_comparison(db, [member.id]))

    assert len(rows) == 3
    assert resolve_mock.await_count == 2  # never called for the Direct (arn_code=None) bucket

    by_arn = {row.arn_code: row for row in rows}

    row_a = by_arn["ARN-11111"]
    assert row_a.distributor_name == "Alpha Distributors"
    assert row_a.arn_status == ArnStatus.ACTIVE
    assert len(row_a.schemes) == 1
    assert row_a.schemes[0].units_held == "60.000"
    assert Decimal(row_a.amount_invested) == Decimal("3000.00")
    assert Decimal(row_a.realized_gain) == Decimal("800.00")
    assert Decimal(row_a.current_value) == Decimal("3600.00")
    assert Decimal(row_a.unrealized_gain) == Decimal("600.00")
    assert Decimal(row_a.current_profit_total) == Decimal("1400.00")
    assert Decimal(row_a.schemes[0].average_nav) == Decimal("50")

    row_b = by_arn["ARN-22222"]
    assert row_b.distributor_name == "Beta Advisors"
    assert row_b.arn_status == ArnStatus.SUSPENDED
    assert Decimal(row_b.current_profit_total) == Decimal("1000.00")

    row_c = by_arn[None]
    assert row_c.distributor_name is None
    assert row_c.arn_status is None
    assert Decimal(row_c.current_profit_total) == Decimal("450.00")


def test_compute_distributor_comparison_never_merges_across_members():
    """Two members holding the SAME scheme via the SAME ARN must stay as two
    separate DistributorSchemeBreakdown rows under that one
    DistributorPortfolioRow, mirroring compute_holdings' existing (member,
    scheme, plan_type) convention — grouping never silently combines
    different members' holdings into one breakdown row."""
    import asyncio

    db = _session()
    member_a = _household_member(db, name="Mom")
    member_b = _household_member(db, name="Dad")
    scheme = _scheme(db)

    folio_a = _folio(db, member_a, scheme, "AAA", "ARN-99999")
    _txn(db, folio_a, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))
    folio_b = _folio(db, member_b, scheme, "BBB", "ARN-99999")
    _txn(db, folio_b, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("3000.00"), Decimal("60.000"), Decimal("50.0000"))

    resolve_mock = AsyncMock(side_effect=_fake_resolve_arn({
        "ARN-99999": SimpleNamespace(distributor_name="Shared Distributor", status=ArnStatus.ACTIVE),
    }))

    with (
        patch(
            "app.services.dashboard.distributor_comparison.get_navs_on_or_before",
            new=_mock_nav_batch({scheme.id: (Decimal("50.0000"), date(2024, 1, 1))}),
        ),
        patch("app.services.dashboard.distributor_comparison.resolve_arn", new=resolve_mock),
    ):
        rows = asyncio.run(compute_distributor_comparison(db, [member_a.id, member_b.id]))

    assert len(rows) == 1
    row = rows[0]
    assert len(row.schemes) == 2
    names = {b.household_member_name for b in row.schemes}
    assert names == {"Mom", "Dad"}
    assert Decimal(row.amount_invested) == Decimal("8000.00")  # 5000 + 3000


def test_compute_distributor_comparison_excludes_only_the_scheme_with_missing_nav():
    """A member holds two schemes, one via an ARN whose NAV cannot be
    resolved and one that resolves fine. Only the unresolvable scheme's
    breakdown row is dropped — the distributor row and the other scheme's
    breakdown still render, unlike the old fund-scoped version's
    all-or-nothing empty-list behavior."""
    import asyncio

    db = _session()
    member = _household_member(db)
    scheme_ok = _scheme(db, name="Resolvable Fund", amfi_code="AAA111")
    scheme_missing = _scheme(db, name="Unresolvable Fund", amfi_code="BBB222")

    folio_ok = _folio(db, member, scheme_ok, "AAA", "ARN-55555")
    _txn(db, folio_ok, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))
    folio_missing = _folio(db, member, scheme_missing, "BBB", "ARN-55555")
    _txn(db, folio_missing, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("2000.00"), Decimal("40.000"), Decimal("50.0000"))

    resolve_mock = AsyncMock(side_effect=_fake_resolve_arn({
        "ARN-55555": SimpleNamespace(distributor_name="Gamma Wealth", status=ArnStatus.ACTIVE),
    }))

    async def lookup(_db, scheme_date_pairs):
        results = {}
        for scheme, _on_date in scheme_date_pairs:
            results[scheme.id] = (Decimal("60.0000"), date(2024, 6, 1)) if scheme.id == scheme_ok.id else None
        return results

    with (
        patch("app.services.dashboard.distributor_comparison.get_navs_on_or_before", new=AsyncMock(side_effect=lookup)),
        patch("app.services.dashboard.distributor_comparison.resolve_arn", new=resolve_mock),
    ):
        rows = asyncio.run(compute_distributor_comparison(db, [member.id]))

    assert len(rows) == 1
    row = rows[0]
    assert row.distributor_name == "Gamma Wealth"
    assert len(row.schemes) == 1
    assert row.schemes[0].scheme_name == "Resolvable Fund"


def test_compute_distributor_comparison_keeps_distributor_row_when_every_scheme_nav_missing():
    """A distributor whose every scheme is NAV-unavailable still renders,
    with an empty schemes list and zero totals — not dropped entirely, per
    the design spec's Error Handling section."""
    import asyncio

    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme, "AAA", "ARN-77777")
    _txn(db, folio, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))

    resolve_mock = AsyncMock(side_effect=_fake_resolve_arn({
        "ARN-77777": SimpleNamespace(distributor_name="Delta Partners", status=ArnStatus.ACTIVE),
    }))

    with (
        patch(
            "app.services.dashboard.distributor_comparison.get_navs_on_or_before",
            new=_mock_nav_batch({scheme.id: None}),
        ),
        patch("app.services.dashboard.distributor_comparison.resolve_arn", new=resolve_mock),
    ):
        rows = asyncio.run(compute_distributor_comparison(db, [member.id]))

    assert len(rows) == 1
    row = rows[0]
    assert row.distributor_name == "Delta Partners"
    assert row.schemes == []
    assert Decimal(row.amount_invested) == Decimal("0")
    assert Decimal(row.current_value) == Decimal("0")


def test_compute_distributor_comparison_includes_fully_redeemed_distributor_group():
    """Deliberate divergence from holdings.py: a scheme group with zero
    units held (fully redeemed through that ARN) still appears here, since
    this view compares historical performance across distributors, not just
    what's currently held. holdings.py.compute_holdings would drop this row
    entirely (units_held == 0); this function must not."""
    import asyncio

    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)

    folio = _folio(db, member, scheme, "AAA", "ARN-11111")
    _txn(db, folio, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))
    _txn(db, folio, TransactionType.REDEMPTION, date(2024, 3, 1), Decimal("6000.00"), Decimal("100.000"), Decimal("60.0000"))

    resolve_mock = AsyncMock(side_effect=_fake_resolve_arn({
        "ARN-11111": SimpleNamespace(distributor_name="Alpha Distributors", status=ArnStatus.ACTIVE),
    }))

    with (
        patch(
            "app.services.dashboard.distributor_comparison.get_navs_on_or_before",
            new=_mock_nav_batch({scheme.id: (Decimal("70.0000"), date(2024, 6, 1))}),
        ),
        patch("app.services.dashboard.distributor_comparison.resolve_arn", new=resolve_mock),
    ):
        rows = asyncio.run(compute_distributor_comparison(db, [member.id]))

    assert len(rows) == 1
    row = rows[0]
    assert len(row.schemes) == 1
    assert row.schemes[0].units_held == "0"
    assert row.schemes[0].average_nav is None
    assert Decimal(row.realized_gain) == Decimal("1000.00")  # 100*(60-50)
    assert Decimal(row.current_profit_total) == Decimal("1000.00")


def test_compute_distributor_comparison_returns_empty_for_member_with_no_folios():
    import asyncio

    db = _session()
    member = _household_member(db)

    rows = asyncio.run(compute_distributor_comparison(db, [member.id]))
    assert rows == []


def test_compute_distributor_comparison_returns_empty_for_no_member_ids():
    import asyncio

    db = _session()
    rows = asyncio.run(compute_distributor_comparison(db, []))
    assert rows == []


def test_compute_distributor_comparison_batches_transaction_fetch_regardless_of_folio_count():
    """Guards against reintroducing the per-folio Transaction N+1 this
    rewrite is specifically designed to avoid — asserts exactly one SELECT
    against the transactions table regardless of folio count, not one per
    folio."""
    import asyncio

    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)

    for i in range(5):
        folio = _folio(db, member, scheme, f"FOLIO-{i}", "ARN-11111")
        _txn(db, folio, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("1000.00"), Decimal("10.000"), Decimal("100.0000"))

    statements: list[str] = []
    engine = db.get_bind()

    def _capture(conn, cursor, statement, parameters, context, executemany):
        if "transactions" in statement.lower() and statement.strip().lower().startswith("select"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        with patch(
            "app.services.dashboard.distributor_comparison.get_navs_on_or_before",
            new=_mock_nav_batch({scheme.id: (Decimal("100.0000"), date(2024, 6, 1))}),
        ):
            asyncio.run(compute_distributor_comparison(db, [member.id]))
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert len(statements) == 1


def test_compute_distributor_comparison_reuses_entry_inside_ttl_window():
    import asyncio

    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme, "AAA", "ARN-11111")
    _txn(db, folio, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))
    now = [1000.0]
    nav_lookup = _mock_nav_batch({scheme.id: (Decimal("60.0000"), date.today())})

    with (
        patch("app.services.dashboard.distributor_comparison._distributor_cache_clock", side_effect=lambda: now[0]),
        patch("app.services.dashboard.distributor_comparison.get_navs_on_or_before", new=nav_lookup),
        patch(
            "app.services.dashboard.distributor_comparison.resolve_arn",
            new=AsyncMock(side_effect=_fake_resolve_arn({"ARN-11111": SimpleNamespace(distributor_name="Alpha", status=ArnStatus.ACTIVE)})),
        ),
    ):
        first = asyncio.run(compute_distributor_comparison(db, [member.id]))
        now[0] += 899.0
        second = asyncio.run(compute_distributor_comparison(db, [member.id]))

    assert second == first
    nav_lookup.assert_awaited_once()


def test_compute_distributor_comparison_invalidated_by_holdings_cache_generation_bump():
    """The distributor cache is invalidated by the SAME signal
    (invalidate_holdings_cache) that already invalidates compute_holdings'
    own cache — no new invalidation call site is wired anywhere."""
    import asyncio

    db = _session()
    member = _household_member(db)
    scheme = _scheme(db)
    folio = _folio(db, member, scheme, "AAA", "ARN-11111")
    _txn(db, folio, TransactionType.PURCHASE, date(2024, 1, 1), Decimal("5000.00"), Decimal("100.000"), Decimal("50.0000"))

    resolve = AsyncMock(side_effect=_fake_resolve_arn({"ARN-11111": SimpleNamespace(distributor_name="Alpha", status=ArnStatus.ACTIVE)}))

    with (
        patch("app.services.dashboard.distributor_comparison.get_navs_on_or_before", new=_mock_nav_batch({scheme.id: (Decimal("60.0000"), date.today())})),
        patch("app.services.dashboard.distributor_comparison.resolve_arn", new=resolve),
    ):
        first = asyncio.run(compute_distributor_comparison(db, [member.id]))

    invalidate_holdings_cache(member.id)
    assert (( (member.id,), date.today() )) not in _distributor_cache

    with (
        patch("app.services.dashboard.distributor_comparison.get_navs_on_or_before", new=_mock_nav_batch({scheme.id: (Decimal("70.0000"), date.today())})),
        patch("app.services.dashboard.distributor_comparison.resolve_arn", new=resolve),
    ):
        second = asyncio.run(compute_distributor_comparison(db, [member.id]))

    assert Decimal(second[0].current_value) != Decimal(first[0].current_value)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && pytest tests/services/dashboard/test_distributor_comparison.py -v`
Expected: FAIL/ERROR — `compute_distributor_comparison` still has the old
`(db, household_member_id, scheme_id)` signature and `_distributor_cache`
doesn't exist yet.

- [ ] **Step 4: Write the implementation**

Replace the entire contents of
`backend/app/services/dashboard/distributor_comparison.py` with:

```python
"""Distributor comparison — PRD-03 FR-11, reframed portfolio-wide (2026-08-20
redesign, see Docs/superpowers/specs/2026-08-20-distributor-comparison-
portfolio-level-design.md). Groups every held scheme, across every
requested household member, by which ARN (distributor) it was bought
through — one DistributorPortfolioRow per ARN (or the Direct bucket), each
carrying a nested per-(scheme, member) breakdown so a distributor's
contribution to the whole portfolio can be inspected, not just one fund at
a time.

Batched by construction (folios, transactions, and NAVs are each fetched in
one query/call for the whole request) — this is new code, so it never
introduces the per-folio N+1 query pattern that compute_holdings still has.
That pre-existing pattern is deliberately left untouched in holdings.py —
see the design spec's Scope section for why.

Unlike holdings.py, a (scheme, member, ARN) group with zero units held
(e.g. fully redeemed through one distributor) is still included, not
dropped — this view compares performance across distributors, including
ones you've since fully exited, not just what's currently held.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.models.user import HouseholdMember
from app.services.dashboard.arn_lookup import resolve_arn
from app.services.dashboard.holdings import (
    _LOT_CONSUMING_TYPES,
    _holdings_cache_generation,
    _process_folio_lots,
    invalidate_holdings_cache,
)
from app.services.dashboard.nav import get_navs_on_or_before
from app.services.dashboard.schemas import DistributorPortfolioRow, DistributorSchemeBreakdown

# Independent from holdings.py's _HOLDINGS_CACHE_TTL_SECONDS by value only
# (same 15-minute posture) — kept as its own constant since these are two
# separate data stores that happen to share a policy, not shared state.
_DISTRIBUTOR_CACHE_TTL_SECONDS = 15 * 60
_distributor_cache_clock = time.monotonic


@dataclass(frozen=True)
class _DistributorCacheEntry:
    rows: list[DistributorPortfolioRow]
    cached_at: float


_distributor_cache: dict[tuple[tuple[uuid.UUID, ...], date], _DistributorCacheEntry] = {}
_distributor_cache_lock = threading.Lock()


async def compute_distributor_comparison(
    db: Session, household_member_ids: list[uuid.UUID]
) -> list[DistributorPortfolioRow]:
    if not household_member_ids:
        return []

    cache_key = (tuple(sorted(household_member_ids)), date.today())
    with _distributor_cache_lock:
        cached_entry = _distributor_cache.get(cache_key)
        if cached_entry is not None:
            cache_age = _distributor_cache_clock() - cached_entry.cached_at
            if cache_age <= _DISTRIBUTOR_CACHE_TTL_SECONDS:
                return cached_entry.rows
            del _distributor_cache[cache_key]
        # Reuses holdings.py's own generation counter — this cache is
        # invalidated by the exact same signal ("this member's transactions
        # changed") already bumped by invalidate_holdings_cache on import
        # confirm / opening-balance resolution, not a parallel one.
        generation = tuple(_holdings_cache_generation[member_id] for member_id in cache_key[0])

    def _publish_if_current(rows: list[DistributorPortfolioRow]) -> None:
        with _distributor_cache_lock:
            if generation == tuple(_holdings_cache_generation[m] for m in cache_key[0]):
                _distributor_cache[cache_key] = _DistributorCacheEntry(
                    rows=rows, cached_at=_distributor_cache_clock()
                )

    members = {
        m.id: m
        for m in db.query(HouseholdMember).filter(HouseholdMember.id.in_(household_member_ids)).all()
    }
    folios = db.query(Folio).filter(Folio.household_member_id.in_(household_member_ids)).all()
    if not folios:
        _publish_if_current([])
        return []

    folio_ids = [folio.id for folio in folios]
    transactions = (
        db.query(Transaction)
        .filter(Transaction.folio_id.in_(folio_ids))
        .order_by(
            Transaction.date,
            # Same same-date purchase-before-redemption tiebreak as
            # holdings.py — reused via the shared constant, not redefined.
            case((Transaction.type.in_(_LOT_CONSUMING_TYPES), 1), else_=0),
            Transaction.id,
        )
        .all()
    )
    txns_by_folio: dict[uuid.UUID, list[Transaction]] = defaultdict(list)
    for txn in transactions:
        txns_by_folio[txn.folio_id].append(txn)

    grouped: dict[tuple[str | None, uuid.UUID, uuid.UUID], list[Folio]] = defaultdict(list)
    for folio in folios:
        grouped[(folio.arn_code, folio.scheme_id, folio.household_member_id)].append(folio)

    scheme_ids = {scheme_id for _, scheme_id, _ in grouped}
    schemes = {s.id: s for s in db.query(Scheme).filter(Scheme.id.in_(scheme_ids)).all()}

    on_date = date.today()
    nav_results = await get_navs_on_or_before(db, [(schemes[sid], on_date) for sid in scheme_ids])

    # Pre-seed every distinct ARN so a distributor whose every scheme
    # misses NAV still produces a row with an empty breakdown, instead of
    # silently vanishing entirely (see design spec's Error Handling
    # section).
    breakdowns_by_arn: dict[str | None, list[DistributorSchemeBreakdown]] = {
        arn_code: [] for arn_code, _, _ in grouped
    }

    for (arn_code, scheme_id, member_id), group_folios in grouped.items():
        nav_result = nav_results.get(scheme_id)
        if nav_result is None:
            continue
        current_nav, _current_nav_date = nav_result

        total_units = Decimal("0")
        total_cost = Decimal("0")
        total_realized = Decimal("0")
        for folio in group_folios:
            units_held, cost_basis, realized_gain = _process_folio_lots(txns_by_folio[folio.id])
            total_units += units_held
            total_cost += cost_basis
            total_realized += realized_gain

        current_value = total_units * current_nav
        unrealized_gain = current_value - total_cost
        current_profit_total = total_realized + unrealized_gain
        average_nav = (total_cost / total_units) if total_units else None
        scheme = schemes[scheme_id]

        breakdowns_by_arn[arn_code].append(
            DistributorSchemeBreakdown(
                scheme_id=str(scheme_id),
                scheme_name=scheme.name,
                household_member_id=str(member_id),
                household_member_name=members[member_id].name,
                units_held=str(total_units),
                average_nav=str(average_nav) if average_nav is not None else None,
                amount_invested=str(total_cost),
                current_value=str(current_value),
                current_profit_total=str(current_profit_total),
                realized_gain=str(total_realized),
                unrealized_gain=str(unrealized_gain),
            )
        )

    rows: list[DistributorPortfolioRow] = []
    for arn_code, schemes_breakdown in breakdowns_by_arn.items():
        distributor_name = None
        arn_status = None
        if arn_code is not None:
            resolved = await resolve_arn(db, arn_code)
            if resolved is not None:
                distributor_name = resolved.distributor_name
                arn_status = resolved.status

        amount_invested = sum((Decimal(b.amount_invested) for b in schemes_breakdown), Decimal("0"))
        current_value = sum((Decimal(b.current_value) for b in schemes_breakdown), Decimal("0"))
        realized_gain = sum((Decimal(b.realized_gain) for b in schemes_breakdown), Decimal("0"))
        unrealized_gain = sum((Decimal(b.unrealized_gain) for b in schemes_breakdown), Decimal("0"))
        current_profit_total = sum((Decimal(b.current_profit_total) for b in schemes_breakdown), Decimal("0"))

        rows.append(
            DistributorPortfolioRow(
                arn_code=arn_code,
                distributor_name=distributor_name,
                arn_status=arn_status,
                amount_invested=str(amount_invested),
                current_value=str(current_value),
                current_profit_total=str(current_profit_total),
                realized_gain=str(realized_gain),
                unrealized_gain=str(unrealized_gain),
                schemes=schemes_breakdown,
            )
        )

    _publish_if_current(rows)
    return rows
```

Note: `invalidate_holdings_cache` is imported here purely so the test
module can import it from `app.services.dashboard.distributor_comparison`
for convenience (matching the test file's import line) — it is re-exported,
not re-implemented; the only invalidation logic lives in `holdings.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/services/dashboard/test_distributor_comparison.py -v`
Expected: PASS (all 11 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dashboard/schemas.py backend/app/services/dashboard/distributor_comparison.py backend/tests/services/dashboard/test_distributor_comparison.py
git commit -m "feat(dashboard): rewrite distributor comparison as portfolio-wide, batched, cached"
```

---

### Task 2: Backend — new routes + aggregate wrapper

**Files:**
- Modify: `backend/app/services/dashboard/aggregate.py`
- Modify: `backend/app/api/dashboard.py:1-52,98-111`
- Test: `backend/tests/api/test_dashboard_distributor_comparison_route.py`
  (full rewrite)

**Interfaces:**
- Consumes: `compute_distributor_comparison(db, household_member_ids:
  list[uuid.UUID]) -> list[DistributorPortfolioRow]` (Task 1).
- Produces: `get_aggregate_distributor_comparison(db: Session, user_id:
  uuid.UUID) -> AggregateDistributorComparisonResponse` — consumed by the
  new aggregate route in this same task. Two live routes:
  `GET /household-members/{member_id}/distributor-comparison` and
  `GET /household/aggregate/distributor-comparison`.

- [ ] **Step 1: Write the failing route tests**

Replace the entire contents of
`backend/tests/api/test_dashboard_distributor_comparison_route.py` with:

```python
import uuid


def _authed_headers_and_member(client, phone: str) -> tuple[dict[str, str], str]:
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    member = client.post("/household-members", json={"name": "Self", "relationship": "self"}, headers=headers).json()
    return headers, member["id"]


def test_member_distributor_comparison_route_requires_auth(client):
    response = client.get("/household-members/00000000-0000-0000-0000-000000000000/distributor-comparison")
    assert response.status_code == 401


def test_member_distributor_comparison_route_404s_for_another_users_member(client):
    _, other_member_id = _authed_headers_and_member(client, "+919000000004")
    headers, _ = _authed_headers_and_member(client, "+919000000005")

    response = client.get(f"/household-members/{other_member_id}/distributor-comparison", headers=headers)
    assert response.status_code == 404


def test_member_distributor_comparison_route_returns_empty_list_for_member_with_no_holdings(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000006")

    response = client.get(f"/household-members/{member_id}/distributor-comparison", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_aggregate_distributor_comparison_route_requires_auth(client):
    response = client.get("/household/aggregate/distributor-comparison")
    assert response.status_code == 401


def test_aggregate_distributor_comparison_route_returns_members_and_empty_rows(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000007")

    response = client.get("/household/aggregate/distributor-comparison", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["rows"] == []
    assert len(body["members"]) == 1
    assert body["members"][0]["id"] == member_id


def test_old_fund_scoped_distributor_comparison_route_is_gone(client):
    headers, member_id = _authed_headers_and_member(client, "+919000000008")
    scheme_id = uuid.uuid4()

    response = client.get(
        f"/household-members/{member_id}/schemes/{scheme_id}/distributor-comparison", headers=headers
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/api/test_dashboard_distributor_comparison_route.py -v`
Expected: FAIL — old route still exists at the `.../schemes/{scheme_id}/...`
path (so the "is gone" test fails) and the new paths don't exist yet
(404/other failures on the rest).

- [ ] **Step 3: Add the aggregate wrapper**

In `backend/app/services/dashboard/aggregate.py`, add this import to the
existing import block (alongside `from app.services.dashboard.holdings
import compute_holdings`):

```python
from app.services.dashboard.distributor_comparison import compute_distributor_comparison
```

Add `AggregateDistributorComparisonResponse` to the existing
`from app.services.dashboard.schemas import (...)` import block.

Add this function after `get_aggregate_holdings`:

```python
async def get_aggregate_distributor_comparison(
    db: Session, user_id: uuid.UUID
) -> AggregateDistributorComparisonResponse:
    members = list_household_members(db, user_id)
    statuses = get_member_statuses(db, user_id)
    rows = await compute_distributor_comparison(db, [m.id for m in members])
    return AggregateDistributorComparisonResponse(members=statuses, rows=rows)
```

- [ ] **Step 4: Replace the route in `dashboard.py`**

In `backend/app/api/dashboard.py`, update the import block: add
`get_aggregate_distributor_comparison` to the `from
app.services.dashboard.aggregate import (...)` block, and replace
`DistributorComparisonRow` with `AggregateDistributorComparisonResponse` and
`DistributorPortfolioRow` in the `from app.services.dashboard.schemas
import (...)` block.

Replace lines 98-110 (the old
`@router.get("/household-members/{member_id}/schemes/{scheme_id}/distributor-comparison", ...)`
route) with:

```python
@router.get(
    "/household-members/{member_id}/distributor-comparison",
    response_model=list[DistributorPortfolioRow],
)
async def get_member_distributor_comparison(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if get_household_member_for_user(db, user.id, member_id) is None:
        raise HTTPException(status_code=404, detail="Household member not found.")
    return await compute_distributor_comparison(db, [member_id])
```

Then, in the aggregate routes section (after
`get_household_aggregate_holdings`), add:

```python
@router.get(
    "/household/aggregate/distributor-comparison",
    response_model=AggregateDistributorComparisonResponse,
)
async def get_household_aggregate_distributor_comparison(
    user: User = Depends(get_current_user), db: DbSession = Depends(get_db)
):
    return await get_aggregate_distributor_comparison(db, user.id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/api/test_dashboard_distributor_comparison_route.py -v`
Expected: PASS (all 6 tests)

Also run the full backend suite to confirm nothing else broke:
Run: `cd backend && pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dashboard/aggregate.py backend/app/api/dashboard.py backend/tests/api/test_dashboard_distributor_comparison_route.py
git commit -m "feat(dashboard): add portfolio-wide distributor comparison routes, remove fund-scoped route"
```

---

### Task 3: Frontend — types + API client

**Files:**
- Modify: `frontend/src/features/dashboard/types.ts:106-117`
- Modify: `frontend/src/features/dashboard/api.ts:16,78-86`

**Interfaces:**
- Consumes: nothing (leaf types/functions).
- Produces: `DistributorSchemeBreakdown`, `DistributorPortfolioRow`,
  `AggregateDistributorComparisonResponse` TS interfaces — consumed by
  Tasks 5 and 8. `getMemberDistributorComparison(memberId: string, signal?:
  AbortSignal): Promise<DistributorPortfolioRow[]>` and
  `getAggregateDistributorComparison(signal?: AbortSignal):
  Promise<AggregateDistributorComparisonResponse>` — consumed by Tasks 5
  and 8.

No backend server round-trip in this task's own tests — `types.ts` has no
test file (type-only), and `api.ts`'s new functions are exercised via the
mocked-fetch tests in Tasks 5 and 8. This task is verified by a type-check
pass, per the plan's TDD posture applied to a types-only change (see Step
2's `tsc` run in place of a unit test cycle for the pure-interface parts).

- [ ] **Step 1: Update `types.ts`**

In `frontend/src/features/dashboard/types.ts`, replace lines 106-117
(the `DistributorComparisonRow` interface) with:

```ts
export interface DistributorSchemeBreakdown {
  scheme_id: string;
  scheme_name: string;
  household_member_id: string;
  household_member_name: string;
  units_held: string;
  average_nav: string | null;
  amount_invested: string;
  current_value: string;
  current_profit_total: string;
  realized_gain: string;
  unrealized_gain: string;
}

export interface DistributorPortfolioRow {
  arn_code: string | null;
  distributor_name: string | null;
  arn_status: "ACTIVE" | "SUSPENDED" | "INVALID" | "UNRESOLVED" | null;
  amount_invested: string;
  current_value: string;
  current_profit_total: string;
  realized_gain: string;
  unrealized_gain: string;
  schemes: DistributorSchemeBreakdown[];
}

export interface AggregateDistributorComparisonResponse {
  members: FamilyMemberStatus[];
  rows: DistributorPortfolioRow[];
}
```

- [ ] **Step 2: Update `api.ts`**

In `frontend/src/features/dashboard/api.ts`, replace `DistributorComparisonRow`
on line 16 with `DistributorPortfolioRow, AggregateDistributorComparisonResponse,`
in the `import type { ... } from "./types"` block.

Replace lines 78-86 (the `getDistributorComparison` function) with:

```ts
export async function getMemberDistributorComparison(
  memberId: string,
  signal?: AbortSignal
): Promise<DistributorPortfolioRow[]> {
  const res = await authFetch(`/household-members/${memberId}/distributor-comparison`, { signal });
  return res.json();
}

export async function getAggregateDistributorComparison(
  signal?: AbortSignal
): Promise<AggregateDistributorComparisonResponse> {
  const res = await authFetch(`/household/aggregate/distributor-comparison`, { signal });
  return res.json();
}
```

- [ ] **Step 3: Verify with a type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: errors ONLY in the files Tasks 4-9 haven't touched yet
(`FundDetailModal.tsx`, `DistributorComparisonModal.tsx`,
`DashboardView.tsx`, `MobileFundDetailView.tsx`,
`MobileDistributorComparisonView.tsx` — all still reference the now-removed
`DistributorComparisonRow`/`getDistributorComparison`). This confirms
Task 3's own new exports compile; the remaining errors are resolved by
Tasks 4-9.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/dashboard/types.ts frontend/src/features/dashboard/api.ts
git commit -m "feat(dashboard): add portfolio-wide distributor comparison types and API client functions"
```

---

### Task 4: Frontend — remove the fund-scoped trigger from `FundDetailModal`

**Files:**
- Modify: `frontend/src/features/dashboard/FundDetailModal.tsx`
- Modify: `frontend/src/features/dashboard/FundDetailModal.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `FundDetailModalProps` with `onCompareDistributors` removed —
  consumed by Task 6 (`DashboardView.tsx` stops passing it).

- [ ] **Step 1: Update the test first**

In `frontend/src/features/dashboard/FundDetailModal.test.tsx`, remove the
`onCompareDistributors={vi.fn()}` line (line 32) from the first test, and
delete the entire second test block (lines 43-58, `"triggers
onCompareDistributors callback when CTA is clicked"`). The file becomes:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FundDetailModal } from "./FundDetailModal";
import type { HoldingRow } from "./types";

describe("FundDetailModal", () => {
  const sampleHolding: HoldingRow = {
    scheme_id: "scheme-42",
    scheme_name: "PPFAS Flexi Cap Fund",
    amc_name: "PPFAS Mutual Fund",
    household_member_id: "m-1",
    household_member_name: "Ayush",
    plan_type: "DIRECT",
    units_held: "150.250",
    average_nav: "42.50",
    current_nav: "65.80",
    current_nav_date: "2026-08-06",
    amount_invested: "6385.63",
    current_value: "9886.45",
    current_profit_total: "3500.82",
    realized_gain: "0.00",
    unrealized_gain: "3500.82",
    today_gain: "45.00",
  };

  it("renders scheme details and financial metrics when modal is open", () => {
    render(
      <FundDetailModal isOpen={true} onClose={vi.fn()} holding={sampleHolding} />
    );

    expect(screen.getByText("PPFAS Flexi Cap Fund")).toBeInTheDocument();
    expect(screen.getByText("PPFAS Mutual Fund")).toBeInTheDocument();
    expect(screen.getByText("₹9,886")).toBeInTheDocument();
    expect(screen.getByText("₹6,386")).toBeInTheDocument();
    expect(screen.getByText("150.250")).toBeInTheDocument();
  });

  it("no longer renders a Compare Distributors trigger — moved to the Holdings section header", () => {
    render(
      <FundDetailModal isOpen={true} onClose={vi.fn()} holding={sampleHolding} />
    );

    expect(
      screen.queryByRole("button", { name: /compare returns by distributor/i })
    ).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/dashboard/FundDetailModal.test.tsx`
Expected: FAIL — `FundDetailModal` still requires `onCompareDistributors`
(TS type error surfaced as a test failure/build error) and still renders
the button.

- [ ] **Step 3: Update `FundDetailModal.tsx`**

In `frontend/src/features/dashboard/FundDetailModal.tsx`:
- Remove the `import { BarChart2 } from "lucide-react";`-sourced icon
  import (it's part of the combined `lucide-react` import on line 6 —
  remove the whole line since `BarChart2` is the only icon used from it).
- Remove `onCompareDistributors: (schemeId: string, schemeName: string) =>
  void;` from `FundDetailModalProps` (line 14).
- Remove `onCompareDistributors,` from the destructured props (line 21).
- Remove the entire `<div className={styles.actionFooter}>...</div>` block
  (lines 72-83).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/dashboard/FundDetailModal.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/dashboard/FundDetailModal.tsx frontend/src/features/dashboard/FundDetailModal.test.tsx
git commit -m "refactor(dashboard): remove fund-scoped Compare Distributors trigger from FundDetailModal"
```

---

### Task 5: Frontend — rebuild `DistributorComparisonModal` around expandable portfolio rows

**Files:**
- Modify: `frontend/src/features/dashboard/DistributorComparisonModal.tsx`
- Modify: `frontend/src/features/dashboard/DistributorComparisonModal.module.css`
- Modify: `frontend/src/features/dashboard/DistributorComparisonModal.test.tsx`

**Interfaces:**
- Consumes: `getMemberDistributorComparison(memberId, signal?)`,
  `getAggregateDistributorComparison(signal?)` (Task 3);
  `DistributorPortfolioRow`, `DistributorSchemeBreakdown` (Task 3).
- Produces: `DistributorComparisonModalProps = { isOpen: boolean; onClose:
  () => void; viewMode: "aggregate" | "member"; memberId: string | null }`
  — consumed by Task 6.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of
`frontend/src/features/dashboard/DistributorComparisonModal.test.tsx` with:

```tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { DistributorComparisonModal } from "./DistributorComparisonModal";
import * as api from "./api";

vi.mock("./api", () => ({
  getMemberDistributorComparison: vi.fn(),
  getAggregateDistributorComparison: vi.fn(),
}));

const directRow = {
  arn_code: null,
  distributor_name: null,
  arn_status: null,
  amount_invested: "5000.00",
  current_value: "7500.00",
  current_profit_total: "2500.00",
  realized_gain: "0.00",
  unrealized_gain: "2500.00",
  schemes: [
    {
      scheme_id: "s-1",
      scheme_name: "PPFAS Flexi Cap Fund",
      household_member_id: "m-1",
      household_member_name: "Ayush",
      units_held: "100.00",
      average_nav: "50.00",
      amount_invested: "5000.00",
      current_value: "7500.00",
      current_profit_total: "2500.00",
      realized_gain: "0.00",
      unrealized_gain: "2500.00",
    },
  ],
};

const brokeredRow = {
  arn_code: "ARN-12345",
  distributor_name: "ABC Wealth",
  arn_status: "ACTIVE",
  amount_invested: "2600.00",
  current_value: "3750.00",
  current_profit_total: "1150.00",
  realized_gain: "0.00",
  unrealized_gain: "1150.00",
  schemes: [
    {
      scheme_id: "s-2",
      scheme_name: "Mirae Asset Large Cap",
      household_member_id: "m-1",
      household_member_name: "Ayush",
      units_held: "50.00",
      average_nav: "52.00",
      amount_invested: "2600.00",
      current_value: "3750.00",
      current_profit_total: "1150.00",
      realized_gain: "0.00",
      unrealized_gain: "1150.00",
    },
  ],
};

describe("DistributorComparisonModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches the member-scoped endpoint in member view", async () => {
    vi.mocked(api.getMemberDistributorComparison).mockResolvedValue([directRow, brokeredRow]);

    render(
      <DistributorComparisonModal isOpen={true} onClose={vi.fn()} viewMode="member" memberId="m-1" />
    );

    await waitFor(() => {
      expect(api.getMemberDistributorComparison).toHaveBeenCalledWith("m-1", expect.anything());
      expect(screen.getByText("Direct Plan (No Broker)")).toBeInTheDocument();
      expect(screen.getByText("ABC Wealth")).toBeInTheDocument();
    });
    expect(api.getAggregateDistributorComparison).not.toHaveBeenCalled();
  });

  it("fetches the aggregate endpoint in aggregate view", async () => {
    vi.mocked(api.getAggregateDistributorComparison).mockResolvedValue({
      members: [{ id: "m-1", name: "Ayush", has_data: true }],
      rows: [directRow],
    });

    render(
      <DistributorComparisonModal isOpen={true} onClose={vi.fn()} viewMode="aggregate" memberId={null} />
    );

    await waitFor(() => {
      expect(api.getAggregateDistributorComparison).toHaveBeenCalled();
      expect(screen.getByText("Direct Plan (No Broker)")).toBeInTheDocument();
    });
    expect(api.getMemberDistributorComparison).not.toHaveBeenCalled();
  });

  it("does not render a scheme breakdown row until the distributor row is expanded", async () => {
    vi.mocked(api.getMemberDistributorComparison).mockResolvedValue([brokeredRow]);

    render(
      <DistributorComparisonModal isOpen={true} onClose={vi.fn()} viewMode="member" memberId="m-1" />
    );

    await waitFor(() => {
      expect(screen.getByText("ABC Wealth")).toBeInTheDocument();
    });
    expect(screen.queryByText("Mirae Asset Large Cap")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("ABC Wealth"));

    await waitFor(() => {
      expect(screen.getByText("Mirae Asset Large Cap")).toBeInTheDocument();
    });
  });

  it("shows the empty state when there are no rows", async () => {
    vi.mocked(api.getMemberDistributorComparison).mockResolvedValue([]);

    render(
      <DistributorComparisonModal isOpen={true} onClose={vi.fn()} viewMode="member" memberId="m-1" />
    );

    await waitFor(() => {
      expect(screen.getByText("No distributor comparison data found.")).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/dashboard/DistributorComparisonModal.test.tsx`
Expected: FAIL — `getMemberDistributorComparison`/
`getAggregateDistributorComparison` don't exist on the current component's
imports and the current props shape (`schemeId`/`schemeName`) doesn't
match.

- [ ] **Step 3: Add nested-row styles**

Append to `frontend/src/features/dashboard/DistributorComparisonModal.module.css`:

```css

.expandButton {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  color: var(--color-text-secondary);
  transition: transform 150ms ease-out;
}

.expandButtonOpen {
  transform: rotate(90deg);
}

.breakdownRow td {
  background: var(--color-bg);
  padding-top: var(--space-2);
  padding-bottom: var(--space-2);
}

.breakdownScheme {
  display: flex;
  flex-direction: column;
  padding-left: var(--space-5);
}

.breakdownMemberName {
  color: var(--color-text-secondary);
}
```

- [ ] **Step 4: Rewrite `DistributorComparisonModal.tsx`**

Replace the entire contents of
`frontend/src/features/dashboard/DistributorComparisonModal.tsx` with:

```tsx
import { useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";
import { Modal } from "../../components/Modal";
import { Badge } from "../../components/Badge";
import { Skeleton } from "../../components/Skeleton";
import { cn, toTitleCase } from "../../lib/utils";
import { getAggregateDistributorComparison, getMemberDistributorComparison } from "./api";
import type { DistributorPortfolioRow } from "./types";
import styles from "./DistributorComparisonModal.module.css";

export interface DistributorComparisonModalProps {
  isOpen: boolean;
  onClose: () => void;
  viewMode: "aggregate" | "member";
  memberId: string | null;
}

function rowKey(row: DistributorPortfolioRow, idx: number): string {
  return row.arn_code || `direct-${idx}`;
}

export function DistributorComparisonModal({
  isOpen,
  onClose,
  viewMode,
  memberId,
}: DistributorComparisonModalProps) {
  const [rows, setRows] = useState<DistributorPortfolioRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!isOpen) return;
    if (viewMode === "member" && !memberId) return;

    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setExpanded(new Set());

    const fetchRows = viewMode === "aggregate"
      ? getAggregateDistributorComparison(controller.signal).then((res) => res.rows)
      : getMemberDistributorComparison(memberId as string, controller.signal);

    fetchRows
      .then((data) => {
        setRows(data);
        setLoading(false);
      })
      .catch((err) => {
        if (err?.name === "AbortError") return;
        setError(err.message || "Failed to load distributor comparison");
        setLoading(false);
      });

    return () => controller.abort();
  }, [isOpen, viewMode, memberId]);

  const toggleExpanded = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Distributor Comparison">
      <div className={styles.container}>
        <div className={styles.schemeHeader}>
          <p className="type-caption">
            Compare returns across Direct plans and Regular distributors, across every fund you hold
          </p>
        </div>

        {loading ? (
          <div className={styles.loadingSkeleton}>
            <Skeleton height="40px" />
            <Skeleton height="40px" />
            <Skeleton height="40px" />
          </div>
        ) : error ? (
          <div className={styles.errorBox}>
            <p className="type-body">{error}</p>
          </div>
        ) : rows.length === 0 ? (
          <p className="type-body">No distributor comparison data found.</p>
        ) : (
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th></th>
                  <th>Distributor / Channel</th>
                  <th>ARN Code</th>
                  <th>Status</th>
                  <th className={styles.numTh}>Invested</th>
                  <th className={styles.numTh}>Current Value</th>
                  <th className={styles.numTh}>Unrealized Gain</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => {
                  const key = rowKey(row, idx);
                  const isDirect = !row.arn_code;
                  const gain = parseFloat(row.unrealized_gain || "0");
                  const isPositive = gain >= 0;
                  const isExpanded = expanded.has(key);

                  return (
                    <>
                      <tr
                        key={key}
                        className={styles.row}
                        onClick={() => toggleExpanded(key)}
                        style={{ cursor: "pointer" }}
                      >
                        <td>
                          <button
                            type="button"
                            className={cn(styles.expandButton, isExpanded && styles.expandButtonOpen)}
                            aria-label={isExpanded ? "Collapse breakdown" : "Expand breakdown"}
                            aria-expanded={isExpanded}
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpanded(key);
                            }}
                          >
                            <ChevronRight className="h-4 w-4" />
                          </button>
                        </td>
                        <td>
                          <div className={styles.distributorNameCell}>
                            <span className={`type-body-medium ${styles.nameText}`}>
                              {isDirect
                                ? "Direct Plan (No Broker)"
                                : row.distributor_name || "Regular Broker"}
                            </span>
                          </div>
                        </td>
                        <td className="type-data">
                          {isDirect ? "—" : row.arn_code}
                        </td>
                        <td>
                          {isDirect ? (
                            <Badge variant="positive">Direct</Badge>
                          ) : row.arn_status === "ACTIVE" ? (
                            <Badge variant="positive">{toTitleCase(row.arn_status)}</Badge>
                          ) : row.arn_status === "SUSPENDED" || row.arn_status === "INVALID" ? (
                            <Badge variant="warning">{toTitleCase(row.arn_status)}</Badge>
                          ) : (
                            <Badge variant="neutral">Unresolved</Badge>
                          )}
                        </td>
                        <td className={`type-data ${styles.numTd}`}>
                          ₹{formatCurrency(row.amount_invested)}
                        </td>
                        <td className={`type-data ${styles.numTd} ${styles.boldText}`}>
                          ₹{formatCurrency(row.current_value)}
                        </td>
                        <td className={`type-data ${styles.numTd}`}>
                          <span className={isPositive ? styles.positiveText : styles.negativeText}>
                            {isPositive ? "↑ " : "↓ "}₹{formatCurrency(Math.abs(gain))}
                          </span>
                        </td>
                      </tr>
                      {isExpanded &&
                        row.schemes.map((scheme) => {
                          const schemeGain = parseFloat(scheme.unrealized_gain || "0");
                          const schemeIsPositive = schemeGain >= 0;
                          return (
                            <tr key={`${key}-${scheme.scheme_id}-${scheme.household_member_id}`} className={styles.breakdownRow}>
                              <td></td>
                              <td colSpan={2}>
                                <div className={styles.breakdownScheme}>
                                  <span className="type-body">{scheme.scheme_name}</span>
                                  {viewMode === "aggregate" && (
                                    <span className={`type-caption ${styles.breakdownMemberName}`}>
                                      {scheme.household_member_name}
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="type-caption">
                                {scheme.units_held} units @ ₹{scheme.average_nav ?? "—"}
                              </td>
                              <td className={`type-data ${styles.numTd}`}>
                                ₹{formatCurrency(scheme.amount_invested)}
                              </td>
                              <td className={`type-data ${styles.numTd}`}>
                                ₹{formatCurrency(scheme.current_value)}
                              </td>
                              <td className={`type-data ${styles.numTd}`}>
                                <span className={schemeIsPositive ? styles.positiveText : styles.negativeText}>
                                  {schemeIsPositive ? "↑ " : "↓ "}₹{formatCurrency(Math.abs(schemeGain))}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Modal>
  );
}

function formatCurrency(valStr: string | number): string {
  const num = typeof valStr === "string" ? parseFloat(valStr) : valStr;
  if (isNaN(num)) return "0";
  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: 0,
  }).format(num);
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/dashboard/DistributorComparisonModal.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/dashboard/DistributorComparisonModal.tsx frontend/src/features/dashboard/DistributorComparisonModal.module.css frontend/src/features/dashboard/DistributorComparisonModal.test.tsx
git commit -m "feat(dashboard): rebuild DistributorComparisonModal as portfolio-wide with expandable rows"
```

---

### Task 6: Frontend — `DashboardView.tsx` trigger + wiring

**Files:**
- Modify: `frontend/src/features/dashboard/DashboardView.tsx:6-8,39,52-92,609-692`
- Modify: `frontend/src/features/dashboard/DashboardView.test.tsx:212-261`

**Interfaces:**
- Consumes: `DistributorComparisonModalProps` (Task 5).
- Produces: nothing new (page-level component, terminal consumer).

- [ ] **Step 1: Rewrite the affected test**

In `frontend/src/features/dashboard/DashboardView.test.tsx`:
- Update the `vi.mock("./api", ...)` block (lines 7-17) to replace
  `getDistributorComparison: vi.fn(),` with
  `getMemberDistributorComparison: vi.fn(),` and
  `getAggregateDistributorComparison: vi.fn(),`.
- Replace the entire test at lines 212-261 (`"compares distributors using
  the clicked holding's own member id..."`) with:

```tsx
  it("opens the portfolio-wide distributor comparison from the Holdings section header", async () => {
    vi.mocked(api.getAggregateHoldings).mockResolvedValue({
      members: [
        { id: "m-1", name: "Alice", has_data: true },
        { id: "m-2", name: "Bob", has_data: true },
      ],
      holdings: [
        {
          scheme_id: "scheme-A", scheme_name: "Alice Fund", household_member_id: "m-1", household_member_name: "Alice",
          plan_type: "DIRECT", units_held: "50.00", average_nav: "60.00", current_nav: "80.00",
          amount_invested: "3000.00", current_value: "4000.00", current_profit_total: "1000.00",
          realized_gain: "0.00", unrealized_gain: "1000.00", today_gain: "20.00",
        },
      ],
    } as any);
    vi.mocked(api.getAggregateAllocation).mockResolvedValue({
      members: [
        { id: "m-1", name: "Alice", has_data: true },
        { id: "m-2", name: "Bob", has_data: true },
      ],
      allocation: { by_asset_class: [], by_amc: [], total_value: "4000.00" },
    } as any);
    vi.mocked(api.getAggregateDistributorComparison).mockResolvedValue({
      members: [],
      rows: [],
    });

    render(<DashboardView viewMode="aggregate" memberId="m-1" />);

    await waitFor(() => {
      expect(screen.getByText("Alice Fund")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /compare distributors/i }));

    await waitFor(() => {
      expect(api.getAggregateDistributorComparison).toHaveBeenCalled();
      expect(screen.getByText("No distributor comparison data found.")).toBeInTheDocument();
    });
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/dashboard/DashboardView.test.tsx`
Expected: FAIL — no "Compare Distributors" button exists yet in the
Holdings section header, and `getAggregateDistributorComparison` is
unmocked-but-unused on the real component.

- [ ] **Step 3: Update `DashboardView.tsx`**

Replace the import on line 8:
```tsx
import { DistributorComparisonModal } from "./DistributorComparisonModal";
```
(unchanged import path, just noting it stays — no edit needed here beyond
what Step 3 below removes).

Add `BarChart2` is already imported on line 39
(`import { ArrowUpRight, ArrowDownRight, User, Users, AlertTriangle,
BarChart2 } from "lucide-react";` — already present, no change needed) and
add a `Button` import: change line 6 from:
```tsx
import { Badge } from "../../components/Badge";
```
to:
```tsx
import { Badge } from "../../components/Badge";
import { Button } from "@/components/ui/button";
```

Replace the modal state block (lines 79-85):
```tsx
  const [selectedHolding, setSelectedHolding] = useState<HoldingRow | null>(null);
  const [comparisonModalState, setComparisonModalState] = useState<{
    isOpen: boolean;
    memberId: string;
    schemeId: string;
    schemeName: string;
  }>({ isOpen: false, memberId: "", schemeId: "", schemeName: "" });
```
with:
```tsx
  const [selectedHolding, setSelectedHolding] = useState<HoldingRow | null>(null);
  const [isDistributorComparisonOpen, setIsDistributorComparisonOpen] = useState(false);
```

Replace the Holdings section header block (lines 610-635):
```tsx
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h2 className="font-display text-lg font-semibold tracking-tight text-[var(--color-ink)]">
            Holdings ({displayedHoldings.length})
          </h2>

          {viewMode === "aggregate" && membersStatus.length > 0 && (
            <Select value={holdingsMemberFilter} onValueChange={setHoldingsMemberFilter}>
              <SelectTrigger
                className="h-8 w-auto min-w-[160px] gap-1.5 rounded-full border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1 text-xs font-medium text-[var(--color-text-secondary)] [&>span]:line-clamp-1"
                aria-label="Filter holdings by family member"
              >
                <User className="h-3.5 w-3.5 text-[var(--color-accent)] flex-shrink-0" />
                <SelectValue placeholder="All Members" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Members</SelectItem>
                {membersStatus.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
```
with:
```tsx
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h2 className="font-display text-lg font-semibold tracking-tight text-[var(--color-ink)]">
            Holdings ({displayedHoldings.length})
          </h2>

          <div className="flex items-center gap-2 flex-wrap">
            {viewMode === "aggregate" && membersStatus.length > 0 && (
              <Select value={holdingsMemberFilter} onValueChange={setHoldingsMemberFilter}>
                <SelectTrigger
                  className="h-8 w-auto min-w-[160px] gap-1.5 rounded-full border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1 text-xs font-medium text-[var(--color-text-secondary)] [&>span]:line-clamp-1"
                  aria-label="Filter holdings by family member"
                >
                  <User className="h-3.5 w-3.5 text-[var(--color-accent)] flex-shrink-0" />
                  <SelectValue placeholder="All Members" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Members</SelectItem>
                  {membersStatus.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setIsDistributorComparisonOpen(true)}
              className="gap-1.5 inline-flex items-center"
            >
              <BarChart2 className="h-3.5 w-3.5" />
              <span>Compare Distributors</span>
            </Button>
          </div>
        </div>
```

Replace the `FundDetailModal` + `DistributorComparisonModal` block (lines
647-692):
```tsx
      {/* S15: Fund Detail Modal */}
      <FundDetailModal
        isOpen={!!selectedHolding}
        onClose={() => setSelectedHolding(null)}
        holding={selectedHolding}
        onCompareDistributors={(schemeId, schemeName) => {
          // Captured now, before setSelectedHolding(null) below clears it —
          // both updates land in the same batch, so reading it at render
          // time would always see null. No fallback to the page-level
          // memberId here: that's a different member than the one who
          // actually owns this holding, and silently substituting it sends
          // the wrong id instead of failing loudly (the render gate below
          // treats an empty ownerId as "don't open").
          const ownerId = selectedHolding?.household_member_id || "";
          setSelectedHolding(null);
          setComparisonModalState({
            isOpen: true,
            memberId: ownerId,
            schemeId,
            schemeName,
          });
        }}
      />

      {/* S17: Distributor Comparison Modal — gated on its OWN captured
          memberId (the clicked holding's actual owner), not the page-level
          memberId. That page-level value is a different concept (which
          member/aggregate the dashboard is currently viewing) and can be
          null or point at a different member than the one being compared;
          falling back to it here would silently resend the wrong id. */}
      {comparisonModalState.memberId && (
        <DistributorComparisonModal
          isOpen={comparisonModalState.isOpen}
          onClose={() =>
            setComparisonModalState({
              isOpen: false,
              memberId: "",
              schemeId: "",
              schemeName: "",
            })
          }
          memberId={comparisonModalState.memberId}
          schemeId={comparisonModalState.schemeId}
          schemeName={comparisonModalState.schemeName}
        />
      )}
```
with:
```tsx
      {/* S15: Fund Detail Modal */}
      <FundDetailModal
        isOpen={!!selectedHolding}
        onClose={() => setSelectedHolding(null)}
        holding={selectedHolding}
      />

      {/* S17: Distributor Comparison Modal — portfolio-wide, driven by the
          page's own viewMode/memberId (same conditional every other
          section on this page already uses), not by a specific clicked
          holding. */}
      <DistributorComparisonModal
        isOpen={isDistributorComparisonOpen}
        onClose={() => setIsDistributorComparisonOpen(false)}
        viewMode={viewMode}
        memberId={memberId}
      />
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/dashboard/DashboardView.test.tsx`
Expected: PASS (all tests, including the new one)

Also run the full frontend suite plus type check to confirm no regression
elsewhere:
Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: remaining `tsc` errors ONLY in
`MobileFundDetailView.tsx`/`MobileDistributorComparisonView.tsx` (not yet
touched — resolved by Tasks 7-8).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/dashboard/DashboardView.tsx frontend/src/features/dashboard/DashboardView.test.tsx
git commit -m "feat(dashboard): move Compare Distributors trigger to Holdings section header"
```

---

### Task 7: Frontend (mobile) — remove the fund-scoped trigger from `MobileFundDetailView`

**Files:**
- Modify: `frontend/src/mobile/features/holdings/MobileFundDetailView.tsx:1-20,63-65,266-276,472-481`

**Interfaces:**
- Consumes: nothing new.
- Produces: `MobileFundDetailViewProps` unchanged (already just `{
  holding, onBack }`) — no signature change, so no consumer update needed.

`MobileFundDetailView.test.tsx` has no assertions on the removed trigger
(verified during planning) — no test file changes needed for this task;
its existing 4 tests double as the regression check.

- [ ] **Step 1: Run the existing test to confirm current baseline**

Run: `cd frontend && npx vitest run src/mobile/features/holdings/MobileFundDetailView.test.tsx`
Expected: PASS (current baseline, before this task's edit)

- [ ] **Step 2: Remove the trigger from `MobileFundDetailView.tsx`**

Remove line 14: `import { MobileDistributorComparisonView } from
"./MobileDistributorComparisonView";`.

Remove `BarChart2,` from the `lucide-react` import block (lines 6-12) —
it's used only by the removed button.

Remove line 65: `const [showDistributorComparison, setShowDistributorComparison] = useState(false);`.

Remove the entire button block (lines 266-275):
```tsx
        {/* Compare Returns by Distributor — placed right after key stats,
            same as the web Fund Details modal's ordering */}
        <Button
          variant="secondary"
          onClick={() => setShowDistributorComparison(true)}
          className="w-full h-11 gap-1.5 inline-flex items-center justify-center rounded-xl text-xs font-semibold"
        >
          <BarChart2 className="h-4 w-4" />
          <span>Compare Returns by Distributor</span>
        </Button>

```

Remove the embedded view block (lines 474-480):
```tsx
      <MobileDistributorComparisonView
        isOpen={showDistributorComparison}
        onClose={() => setShowDistributorComparison(false)}
        memberId={holding.household_member_id}
        schemeId={holding.scheme_id}
        schemeName={holding.scheme_name}
      />
```

`Button` (from `@/components/ui/button`) stays imported — it's still used
elsewhere in this file for the timeframe-independent parts... actually
verify: check remaining `Button` usages in the file. If the removed block
was the only `<Button` usage, remove that import too. (It is not — this
file has no other `<Button` element; grep confirms only the removed one.
Remove the `import { Button } from "@/components/ui/button";` line as
well, since it becomes unused.)

- [ ] **Step 3: Run tests to verify no regression**

Run: `cd frontend && npx vitest run src/mobile/features/holdings/MobileFundDetailView.test.tsx`
Expected: PASS (same 4 tests, unaffected)

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors referencing `MobileFundDetailView.tsx` (unused-import
and removed-prop errors gone).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/mobile/features/holdings/MobileFundDetailView.tsx
git commit -m "refactor(mobile): remove fund-scoped Compare Distributors trigger from MobileFundDetailView"
```

---

### Task 8: Frontend (mobile) — rebuild `MobileDistributorComparisonView` around expandable cards

**Files:**
- Modify: `frontend/src/mobile/features/holdings/MobileDistributorComparisonView.tsx`
- Modify: `frontend/src/mobile/features/holdings/MobileDistributorComparisonView.test.tsx`

**Interfaces:**
- Consumes: `getMemberDistributorComparison`,
  `getAggregateDistributorComparison` (Task 3); `DistributorPortfolioRow`
  (Task 3).
- Produces: `MobileDistributorComparisonViewProps = { isOpen: boolean;
  onClose: () => void; viewMode: "aggregate" | "member"; memberId: string |
  null }` — consumed by Tasks 9 and 10.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of
`frontend/src/mobile/features/holdings/MobileDistributorComparisonView.test.tsx`
with:

```tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MobileDistributorComparisonView } from "./MobileDistributorComparisonView";
import * as dashboardApi from "@/features/dashboard/api";

vi.mock("@/features/dashboard/api", () => ({
  getMemberDistributorComparison: vi.fn(),
  getAggregateDistributorComparison: vi.fn(),
}));

const brokeredRow = {
  arn_code: "ARN-12345",
  distributor_name: "ABC Wealth",
  arn_status: "ACTIVE",
  amount_invested: "2600.00",
  current_value: "3750.00",
  current_profit_total: "1150.00",
  realized_gain: "0.00",
  unrealized_gain: "1150.00",
  schemes: [
    {
      scheme_id: "s-2",
      scheme_name: "Mirae Asset Large Cap",
      household_member_id: "m-1",
      household_member_name: "Ayush",
      units_held: "50.00",
      average_nav: "52.00",
      amount_invested: "2600.00",
      current_value: "3750.00",
      current_profit_total: "1150.00",
      realized_gain: "0.00",
      unrealized_gain: "1150.00",
    },
  ],
};

describe("MobileDistributorComparisonView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches the member-scoped endpoint and renders distributor cards", async () => {
    vi.mocked(dashboardApi.getMemberDistributorComparison).mockResolvedValue([brokeredRow]);

    render(
      <MobileDistributorComparisonView isOpen={true} onClose={vi.fn()} viewMode="member" memberId="m-1" />
    );

    await waitFor(() => {
      expect(screen.getByText("ARN: ARN-12345")).toBeInTheDocument();
      expect(screen.getByText("Active")).toBeInTheDocument();
      expect(screen.getByText("₹2,600")).toBeInTheDocument();
      expect(screen.getByText("₹3,750")).toBeInTheDocument();
      expect(screen.getByText("↑ ₹1,150")).toBeInTheDocument();
    });

    expect(dashboardApi.getMemberDistributorComparison).toHaveBeenCalledWith("m-1", expect.anything());
  });

  it("fetches the aggregate endpoint in aggregate view", async () => {
    vi.mocked(dashboardApi.getAggregateDistributorComparison).mockResolvedValue({
      members: [],
      rows: [brokeredRow],
    });

    render(
      <MobileDistributorComparisonView isOpen={true} onClose={vi.fn()} viewMode="aggregate" memberId={null} />
    );

    await waitFor(() => {
      expect(dashboardApi.getAggregateDistributorComparison).toHaveBeenCalled();
      expect(screen.getByText("ABC Wealth")).toBeInTheDocument();
    });
  });

  it("expands a distributor card to reveal its scheme breakdown", async () => {
    vi.mocked(dashboardApi.getMemberDistributorComparison).mockResolvedValue([brokeredRow]);

    render(
      <MobileDistributorComparisonView isOpen={true} onClose={vi.fn()} viewMode="member" memberId="m-1" />
    );

    await waitFor(() => {
      expect(screen.getByText("ABC Wealth")).toBeInTheDocument();
    });
    expect(screen.queryByText("Mirae Asset Large Cap")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("ABC Wealth"));

    await waitFor(() => {
      expect(screen.getByText("Mirae Asset Large Cap")).toBeInTheDocument();
    });
  });

  it("shows the empty state when the API returns no rows", async () => {
    vi.mocked(dashboardApi.getMemberDistributorComparison).mockResolvedValue([]);

    render(
      <MobileDistributorComparisonView isOpen={true} onClose={vi.fn()} viewMode="member" memberId="m-1" />
    );

    await waitFor(() => {
      expect(screen.getByText("No distributor comparison data found.")).toBeInTheDocument();
    });
  });

  it("calls onClose when the back button is clicked", async () => {
    vi.mocked(dashboardApi.getMemberDistributorComparison).mockResolvedValue([]);
    const handleClose = vi.fn();

    render(
      <MobileDistributorComparisonView isOpen={true} onClose={handleClose} viewMode="member" memberId="m-1" />
    );

    await waitFor(() => {
      expect(screen.getByText("No distributor comparison data found.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText("Back to holdings"));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/mobile/features/holdings/MobileDistributorComparisonView.test.tsx`
Expected: FAIL — current component takes `memberId`/`schemeId`/`schemeName`
props and calls the now-removed `getDistributorComparison`.

- [ ] **Step 3: Rewrite `MobileDistributorComparisonView.tsx`**

Replace the entire contents of
`frontend/src/mobile/features/holdings/MobileDistributorComparisonView.tsx`
with:

```tsx
import { useEffect, useState } from "react";
import { Badge } from "@/components/Badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn, toTitleCase } from "@/lib/utils";
import { getAggregateDistributorComparison, getMemberDistributorComparison } from "@/features/dashboard/api";
import type { DistributorPortfolioRow } from "@/features/dashboard/types";

export interface MobileDistributorComparisonViewProps {
  isOpen: boolean;
  onClose: () => void;
  viewMode: "aggregate" | "member";
  memberId: string | null;
}

function rowKey(row: DistributorPortfolioRow, idx: number): string {
  return row.arn_code || `direct-${idx}`;
}

/** Mobile full-screen equivalent of DistributorComparisonModal — portfolio-
 * wide, same fetch source (getMemberDistributorComparison /
 * getAggregateDistributorComparison) as desktop, but built around the
 * mobile shell's own card idiom: each distributor is a card that expands
 * in place to reveal its per-scheme breakdown, rather than a table. */
export function MobileDistributorComparisonView({
  isOpen,
  onClose,
  viewMode,
  memberId,
}: MobileDistributorComparisonViewProps) {
  const [rows, setRows] = useState<DistributorPortfolioRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!isOpen) return;
    if (viewMode === "member" && !memberId) return;

    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setExpanded(new Set());

    const fetchRows = viewMode === "aggregate"
      ? getAggregateDistributorComparison(controller.signal).then((res) => res.rows)
      : getMemberDistributorComparison(memberId as string, controller.signal);

    fetchRows
      .then((data) => {
        setRows(data);
        setLoading(false);
      })
      .catch((err) => {
        if (err?.name === "AbortError") return;
        setError(err.message || "Failed to load distributor comparison");
        setLoading(false);
      });

    return () => controller.abort();
  }, [isOpen, viewMode, memberId]);

  const toggleExpanded = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col min-h-dvh bg-[var(--color-bg)] animate-in fade-in duration-200">
      {/* Top Header with Back Navigation */}
      <header className="sticky top-0 z-30 w-full h-14 bg-[var(--color-surface)]/85 backdrop-blur-md border-b border-[var(--color-border)] px-4 grid grid-cols-3 items-center transition-colors duration-200 select-none">
        <div className="flex items-center justify-start">
          <button
            onClick={onClose}
            className="h-11 w-11 -ml-2 rounded-full flex items-center justify-center text-[var(--color-ink)] hover:bg-[var(--color-bg)] active:scale-90 transition-all duration-150 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            type="button"
            aria-label="Back to holdings"
          >
            <ChevronLeft className="h-6 w-6 stroke-[2.2]" />
          </button>
        </div>

        <div className="flex items-center justify-center text-center">
          <h1 className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-secondary)] truncate">
            DISTRIBUTOR COMPARISON
          </h1>
        </div>

        <div />
      </header>

      {/* Main Content View */}
      <div className="p-4 space-y-4 overflow-y-auto">
        <div className="space-y-1">
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
            Compare returns across Direct plans and Regular distributors, across every fund you hold
          </p>
        </div>

        {loading ? (
          <div className="space-y-2.5">
            <Skeleton className="h-16 w-full rounded-2xl" />
            <Skeleton className="h-16 w-full rounded-2xl" />
            <Skeleton className="h-16 w-full rounded-2xl" />
          </div>
        ) : error ? (
          <div className="p-4 rounded-2xl bg-[color-mix(in_srgb,var(--color-negative)_8%,transparent)] border border-[color-mix(in_srgb,var(--color-negative)_25%,transparent)]">
            <p className="text-xs text-[var(--color-negative)]">{error}</p>
          </div>
        ) : rows.length === 0 ? (
          <p className="text-xs text-[var(--color-text-secondary)]">
            No distributor comparison data found.
          </p>
        ) : (
          <div className="space-y-2.5">
            {rows.map((row, idx) => {
              const key = rowKey(row, idx);
              const isDirect = !row.arn_code;
              const gain = parseFloat(row.unrealized_gain || "0");
              const isPositive = gain >= 0;
              const isExpanded = expanded.has(key);

              return (
                <div
                  key={key}
                  className="rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border)] shadow-xs overflow-hidden"
                >
                  <button
                    type="button"
                    onClick={() => toggleExpanded(key)}
                    aria-expanded={isExpanded}
                    className="w-full text-left p-4 space-y-3 cursor-pointer"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 flex items-center gap-2">
                        <ChevronRight
                          className={cn(
                            "h-4 w-4 flex-shrink-0 text-[var(--color-text-secondary)] transition-transform duration-150",
                            isExpanded && "rotate-90"
                          )}
                        />
                        <div className="min-w-0">
                          <span className="text-sm font-semibold text-[var(--color-ink)] truncate block">
                            {isDirect
                              ? "Direct Plan (No Broker)"
                              : row.distributor_name || "Regular Broker"}
                          </span>
                          {!isDirect && (
                            <span className="text-[11px] text-[var(--color-text-secondary)] tabular-nums">
                              ARN: {row.arn_code}
                            </span>
                          )}
                        </div>
                      </div>

                      {isDirect ? (
                        <Badge variant="positive">Direct</Badge>
                      ) : row.arn_status === "ACTIVE" ? (
                        <Badge variant="positive">{toTitleCase(row.arn_status)}</Badge>
                      ) : row.arn_status === "SUSPENDED" || row.arn_status === "INVALID" ? (
                        <Badge variant="warning">{toTitleCase(row.arn_status)}</Badge>
                      ) : (
                        <Badge variant="neutral">Unresolved</Badge>
                      )}
                    </div>

                    <div className="pt-2.5 border-t border-[var(--color-border)]/60 grid grid-cols-3 gap-2 text-xs">
                      <div className="space-y-0.5">
                        <span className="text-[10px] uppercase font-semibold text-[var(--color-text-secondary)] tracking-wide block">
                          Invested
                        </span>
                        <span className="font-semibold text-[var(--color-ink)] tabular-nums">
                          ₹{formatCurrency(row.amount_invested)}
                        </span>
                      </div>
                      <div className="space-y-0.5">
                        <span className="text-[10px] uppercase font-semibold text-[var(--color-text-secondary)] tracking-wide block">
                          Current
                        </span>
                        <span className="font-semibold text-[var(--color-ink)] tabular-nums">
                          ₹{formatCurrency(row.current_value)}
                        </span>
                      </div>
                      <div className="space-y-0.5">
                        <span className="text-[10px] uppercase font-semibold text-[var(--color-text-secondary)] tracking-wide block">
                          Gain
                        </span>
                        <span
                          className={
                            "font-semibold tabular-nums " +
                            (isPositive
                              ? "text-[var(--color-positive)]"
                              : "text-[var(--color-negative)]")
                          }
                        >
                          {isPositive ? "↑ " : "↓ "}₹{formatCurrency(Math.abs(gain))}
                        </span>
                      </div>
                    </div>
                  </button>

                  {isExpanded && (
                    <div className="border-t border-[var(--color-border)]/60 divide-y divide-[var(--color-border)]/40">
                      {row.schemes.map((scheme) => {
                        const schemeGain = parseFloat(scheme.unrealized_gain || "0");
                        const schemeIsPositive = schemeGain >= 0;
                        return (
                          <div
                            key={`${scheme.scheme_id}-${scheme.household_member_id}`}
                            className="p-3 pl-9 bg-[var(--color-bg)] space-y-1.5"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-xs font-medium text-[var(--color-ink)] truncate">
                                {scheme.scheme_name}
                              </span>
                              {viewMode === "aggregate" && (
                                <span className="text-[10px] text-[var(--color-text-secondary)] flex-shrink-0">
                                  {scheme.household_member_name}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center justify-between text-[11px] text-[var(--color-text-secondary)]">
                              <span>
                                {scheme.units_held} units @ ₹{scheme.average_nav ?? "—"}
                              </span>
                              <span
                                className={
                                  "font-semibold tabular-nums " +
                                  (schemeIsPositive
                                    ? "text-[var(--color-positive)]"
                                    : "text-[var(--color-negative)]")
                                }
                              >
                                {schemeIsPositive ? "↑ " : "↓ "}₹{formatCurrency(Math.abs(schemeGain))}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function formatCurrency(valStr: string | number): string {
  const num = typeof valStr === "string" ? parseFloat(valStr) : valStr;
  if (isNaN(num)) return "0";
  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: 0,
  }).format(num);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/mobile/features/holdings/MobileDistributorComparisonView.test.tsx`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/mobile/features/holdings/MobileDistributorComparisonView.tsx frontend/src/mobile/features/holdings/MobileDistributorComparisonView.test.tsx
git commit -m "feat(mobile): rebuild MobileDistributorComparisonView as portfolio-wide with expandable cards"
```

---

### Task 9: Frontend (mobile) — trigger on `MobileHoldingsView`

**Files:**
- Modify: `frontend/src/mobile/features/holdings/MobileHoldingsView.tsx`
- Modify: `frontend/src/mobile/features/holdings/MobileHoldingsView.test.tsx`

**Interfaces:**
- Consumes: `MobileDistributorComparisonView` (Task 8), the view's own
  existing `viewMode`/`selectedMemberId` state.
- Produces: nothing new (leaf screen component).

- [ ] **Step 1: Check the existing test file's mock shape**

Read `frontend/src/mobile/features/holdings/MobileHoldingsView.test.tsx`
first to confirm its existing `vi.mock` blocks for `@/features/dashboard/api`
and `@/features/auth/api`, so the new test fits the established mocking
pattern in that file (getAggregateHoldings/getMemberHoldings/listHouseholdMembers
are already mocked there). Add
`getAggregateDistributorComparison: vi.fn(), getMemberDistributorComparison: vi.fn(),`
to that file's existing `vi.mock("@/features/dashboard/api", ...)` block if
present, or add a new one following the same pattern as the other mobile
test files in this plan if the file mocks per-test instead.

- [ ] **Step 2: Write the failing test**

Add this test to
`frontend/src/mobile/features/holdings/MobileHoldingsView.test.tsx`
(inside the existing `describe` block, using whatever holdings-fixture
setup pattern the file's other tests already use to get past the loading
state — e.g. mocking `getAggregateHoldings`/`listHouseholdMembers` to
resolve with at least one holding, matching the file's existing tests):

```tsx
  it("opens the portfolio-wide distributor comparison from the Holdings header", async () => {
    vi.mocked(authApi.listHouseholdMembers).mockResolvedValue([
      { id: "m-1", name: "Ayush", relationship: "self" } as any,
    ]);
    vi.mocked(dashboardApi.getAggregateHoldings).mockResolvedValue({
      members: [{ id: "m-1", name: "Ayush", has_data: true }],
      holdings: [
        {
          scheme_id: "s-1", scheme_name: "PPFAS Flexi Cap Fund", household_member_id: "m-1", household_member_name: "Ayush",
          plan_type: "DIRECT", units_held: "10.00", average_nav: "50.00", current_nav: "60.00",
          amount_invested: "500.00", current_value: "600.00", current_profit_total: "100.00",
          realized_gain: "0.00", unrealized_gain: "100.00", today_gain: "5.00",
        },
      ],
    } as any);
    vi.mocked(dashboardApi.getAggregateDistributorComparison).mockResolvedValue({
      members: [],
      rows: [],
    });

    render(<MobileHoldingsView />);

    await waitFor(() => {
      expect(screen.getByText("PPFAS Flexi Cap Fund")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /compare distributors/i }));

    await waitFor(() => {
      expect(dashboardApi.getAggregateDistributorComparison).toHaveBeenCalled();
      expect(screen.getByText("DISTRIBUTOR COMPARISON")).toBeInTheDocument();
    });
  });
```

(Import `fireEvent` and the module aliases used above — `authApi`,
`dashboardApi` — matching whatever aliasing the existing test file already
uses for its `vi.mock` imports; adjust the exact import names to match the
file's established convention rather than introducing new ones.)

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/mobile/features/holdings/MobileHoldingsView.test.tsx`
Expected: FAIL — no "Compare Distributors" button exists in
`MobileHoldingsView` yet.

- [ ] **Step 4: Add the trigger to `MobileHoldingsView.tsx`**

Add imports:
```tsx
import { MobileDistributorComparisonView } from "./MobileDistributorComparisonView";
import { Button } from "@/components/ui/button";
import { BarChart2 } from "lucide-react";
```
(add `BarChart2` into the existing `lucide-react` import line rather than
a separate line; add `Button` and `MobileDistributorComparisonView` as new
import lines.)

Add state, alongside the existing `selectedHolding` state:
```tsx
  const [isDistributorComparisonOpen, setIsDistributorComparisonOpen] = useState(false);
```

Replace the "Holdings Header Bar" block:
```tsx
      {/* Holdings Header Bar */}
      <div className="flex items-center justify-between px-1 text-xs">
        <span className="font-display text-sm font-bold text-[var(--color-ink)]">
          All Holdings
        </span>
        <span className="text-xs font-semibold text-[var(--color-text-secondary)] tabular-nums">
          {filteredHoldings.length} holding{filteredHoldings.length !== 1 ? "s" : ""}
        </span>
      </div>
```
with:
```tsx
      {/* Holdings Header Bar */}
      <div className="flex items-center justify-between gap-2 px-1 text-xs flex-wrap">
        <span className="font-display text-sm font-bold text-[var(--color-ink)]">
          All Holdings
        </span>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-[var(--color-text-secondary)] tabular-nums">
            {filteredHoldings.length} holding{filteredHoldings.length !== 1 ? "s" : ""}
          </span>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setIsDistributorComparisonOpen(true)}
            className="h-7 gap-1 rounded-full px-2.5 text-[11px]"
          >
            <BarChart2 className="h-3.5 w-3.5" />
            <span>Compare Distributors</span>
          </Button>
        </div>
      </div>
```

Add the view render just before the final closing `</div>` of the
component's main return block (immediately after the
"Summary-First Holding Cards List" section, still inside the outermost
`<div className="flex flex-col space-y-4 ...">`):
```tsx
      <MobileDistributorComparisonView
        isOpen={isDistributorComparisonOpen}
        onClose={() => setIsDistributorComparisonOpen(false)}
        viewMode={viewMode}
        memberId={selectedMemberId}
      />
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/mobile/features/holdings/MobileHoldingsView.test.tsx`
Expected: PASS (all tests, including the new one)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/mobile/features/holdings/MobileHoldingsView.tsx frontend/src/mobile/features/holdings/MobileHoldingsView.test.tsx
git commit -m "feat(mobile): add portfolio-wide Compare Distributors trigger to MobileHoldingsView"
```

---

### Task 10: Frontend (mobile) — trigger on `MobileDashboardView`

**Files:**
- Modify: `frontend/src/mobile/features/dashboard/MobileDashboardView.tsx`
- Modify: `frontend/src/mobile/features/dashboard/MobileDashboardView.test.tsx`

**Interfaces:**
- Consumes: `MobileDistributorComparisonView` (Task 8), the view's own
  existing `viewMode`/`selectedMemberId` state (same pattern as Task 9,
  applied to this file's embedded Holdings section instead of
  `MobileHoldingsView`'s dedicated one).
- Produces: nothing new (leaf screen component).

- [ ] **Step 1: Check the existing test file's mock shape**

Read `frontend/src/mobile/features/dashboard/MobileDashboardView.test.tsx`
first to confirm its established `vi.mock` pattern for
`@/features/dashboard/api`, matching Task 9's Step 1 approach.

- [ ] **Step 2: Write the failing test**

Add this test to
`frontend/src/mobile/features/dashboard/MobileDashboardView.test.tsx`
(inside the existing `describe` block, reusing whatever fixture-setup
helper the file's other tests already use to reach the loaded Holdings
section):

```tsx
  it("opens the portfolio-wide distributor comparison from the embedded Holdings header", async () => {
    vi.mocked(dashboardApi.getAggregateDistributorComparison).mockResolvedValue({
      members: [],
      rows: [],
    });

    render(<MobileDashboardView />);

    await waitFor(() => {
      expect(screen.getByText("Holdings")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /compare distributors/i }));

    await waitFor(() => {
      expect(dashboardApi.getAggregateDistributorComparison).toHaveBeenCalled();
      expect(screen.getByText("DISTRIBUTOR COMPARISON")).toBeInTheDocument();
    });
  });
```

(Adjust fixture mocking calls above to match whatever `beforeEach`/fixture
setup the rest of the file already relies on to get past loading and reach
the Holdings section — follow the file's own established pattern rather
than introducing a new one.)

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/mobile/features/dashboard/MobileDashboardView.test.tsx`
Expected: FAIL — no "Compare Distributors" button exists yet.

- [ ] **Step 4: Add the trigger to `MobileDashboardView.tsx`**

Add imports:
```tsx
import { MobileDistributorComparisonView } from "../holdings/MobileDistributorComparisonView";
```
Add `BarChart2` to the existing `lucide-react` import block (it currently
imports `ArrowDownRight, ArrowUpRight, Users, AlertTriangle, UploadCloud,
Search` — add `BarChart2` alongside them). `Button` is already imported
(line 22: `import { Button } from "@/components/ui/button";`).

Add state, alongside the existing `holdingsMemberFilter` state:
```tsx
  const [isDistributorComparisonOpen, setIsDistributorComparisonOpen] = useState(false);
```

Replace the "Holdings Header Bar" block (lines 618-647):
```tsx
        {/* Holdings Header Bar */}
        <div className="flex items-center justify-between gap-2 px-1 text-xs flex-wrap">
          <span className="font-display text-sm font-bold text-[var(--color-ink)]">
            Holdings
          </span>

          <div className="flex items-center gap-2">
            {viewMode === "aggregate" && membersStatus.length > 0 && (
              <Select value={holdingsMemberFilter} onValueChange={setHoldingsMemberFilter}>
                <SelectTrigger
                  className="h-8 w-auto min-w-[130px] gap-1.5 rounded-full border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-xs font-medium text-[var(--color-text-secondary)] [&>span]:line-clamp-1"
                  aria-label="Filter holdings by family member"
                >
                  <SelectValue placeholder="All Members" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Members</SelectItem>
                  {membersStatus.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <span className="text-xs font-semibold text-[var(--color-text-secondary)] tabular-nums">
              {filteredHoldings.length} holding{filteredHoldings.length !== 1 ? "s" : ""}
            </span>
          </div>
        </div>
```
with:
```tsx
        {/* Holdings Header Bar */}
        <div className="flex items-center justify-between gap-2 px-1 text-xs flex-wrap">
          <span className="font-display text-sm font-bold text-[var(--color-ink)]">
            Holdings
          </span>

          <div className="flex items-center gap-2 flex-wrap">
            {viewMode === "aggregate" && membersStatus.length > 0 && (
              <Select value={holdingsMemberFilter} onValueChange={setHoldingsMemberFilter}>
                <SelectTrigger
                  className="h-8 w-auto min-w-[130px] gap-1.5 rounded-full border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-xs font-medium text-[var(--color-text-secondary)] [&>span]:line-clamp-1"
                  aria-label="Filter holdings by family member"
                >
                  <SelectValue placeholder="All Members" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Members</SelectItem>
                  {membersStatus.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <span className="text-xs font-semibold text-[var(--color-text-secondary)] tabular-nums">
              {filteredHoldings.length} holding{filteredHoldings.length !== 1 ? "s" : ""}
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setIsDistributorComparisonOpen(true)}
              className="h-7 gap-1 rounded-full px-2.5 text-[11px]"
            >
              <BarChart2 className="h-3.5 w-3.5" />
              <span>Compare Distributors</span>
            </Button>
          </div>
        </div>
```

Add the view render just before the final closing `</div>` of the
`<section>`'s parent (immediately after the "Summary-First Holding Cards
List" section's closing, inside the outermost returned `<div>`):
```tsx
      <MobileDistributorComparisonView
        isOpen={isDistributorComparisonOpen}
        onClose={() => setIsDistributorComparisonOpen(false)}
        viewMode={viewMode}
        memberId={selectedMemberId}
      />
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/mobile/features/dashboard/MobileDashboardView.test.tsx`
Expected: PASS (all tests, including the new one)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/mobile/features/dashboard/MobileDashboardView.tsx frontend/src/mobile/features/dashboard/MobileDashboardView.test.tsx
git commit -m "feat(mobile): add portfolio-wide Compare Distributors trigger to MobileDashboardView"
```

---

### Task 11: Full-suite verification

**Files:** none (verification-only task).

**Interfaces:** none.

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && pytest -q`
Expected: PASS, 0 failures.

- [ ] **Step 2: Run the full frontend suite and type check**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: PASS, 0 failures, 0 type errors.

- [ ] **Step 3: Grep for any remaining dead references**

Run: `cd "/mnt/d/Unifolio code" && grep -rn "DistributorComparisonRow\|getDistributorComparison\b\|onCompareDistributors" backend frontend --include="*.py" --include="*.ts" --include="*.tsx" | grep -v node_modules`
Expected: no output (all references to the deleted schema/type/function/prop
are gone).

- [ ] **Step 4: Update `CLAUDE.md`'s Session State pointer**

This is a documentation-only step, not a code change — update
`/mnt/d/Unifolio code/CLAUDE.md`'s Session State section (and/or
`session.md`, per that section's own pointer convention) to note this
feature shipped and to log the `compute_holdings` N+1 follow-up item (per
the spec's Follow-up section) into the "Still open" list, following
whatever numbering the list is at by the time this task executes.

- [ ] **Step 5: Final commit (if Step 4 produced changes)**

```bash
git add CLAUDE.md session.md
git commit -m "docs: log portfolio-level distributor comparison ship + compute_holdings N+1 follow-up"
```

---

## Self-Review

**1. Spec coverage:**
- Batched service rewrite + cache reuse → Task 1. ✓
- Two new routes + old route removed → Task 2. ✓
- Schema split (`DistributorSchemeBreakdown`/`DistributorPortfolioRow`/
  `AggregateDistributorComparisonResponse`) → Task 1 (backend), Task 3
  (frontend). ✓
- Old fund-scoped trigger removed from `FundDetailModal` and
  `MobileFundDetailView` → Tasks 4, 7. ✓
- New Holdings-header trigger, desktop → Task 6. ✓
- New Holdings-header trigger, mobile (both `MobileHoldingsView` and
  `MobileDashboardView`, since both present an independent Holdings
  section on the mobile shell) → Tasks 9, 10. ✓
- Expandable distributor rows with nested per-scheme breakdown, desktop →
  Task 5. ✓
- Expandable distributor cards with nested per-scheme breakdown, mobile,
  built around the mobile shell's own card idiom rather than a ported
  table → Task 8. ✓
- Partial NAV-miss exclusion (only the affected scheme dropped, not the
  whole response) and "every scheme missing → empty schemes list, row
  still renders" → Task 1's tests. ✓
- Cross-member no-merge grouping → Task 1's test. ✓
- Batched-query regression guard → Task 1's test. ✓
- `compute_holdings`'s own N+1 left untouched → confirmed nowhere in this
  plan is `holdings.py`'s `compute_holdings` function body modified (only
  read/imported from); flagged as a follow-up in Task 11. ✓
- `Decimal` used throughout all new rollup arithmetic and fixtures → Task
  1's implementation and tests use `Decimal` exclusively, matching the
  Global Constraints. ✓

**2. Placeholder scan:** No "TBD"/"TODO"/"implement later" markers. Task
9 and 10's Step 1/2 ask the executor to read an existing test file's
established mocking convention before writing the new test rather than
guessing it blind — this is a deliberate "read existing code" instruction
per the writing-plans skill's "In existing codebases, follow established
patterns" guidance, not an unresolved placeholder; the test's assertions
and behavior are fully specified, only the exact mock-import aliasing is
left to match the file's own convention (which the executor can read
directly, unlike content that doesn't exist anywhere).

**3. Type consistency:** `DistributorPortfolioRow`/`DistributorSchemeBreakdown`
field names and types match exactly between `schemas.py` (Task 1),
`types.ts` (Task 3), and every place they're consumed (Tasks 5, 6, 8, 9,
10). `compute_distributor_comparison(db, household_member_ids: list[uuid.UUID])
-> list[DistributorPortfolioRow]` signature is consistent between Task 1's
implementation, Task 2's route/aggregate-wrapper usage, and Task 1's own
tests. `getMemberDistributorComparison`/`getAggregateDistributorComparison`
names and signatures match between Task 3's definition and every caller in
Tasks 5, 6, 8, 9, 10. `DistributorComparisonModalProps`/
`MobileDistributorComparisonViewProps` (`{ isOpen, onClose, viewMode,
memberId }`) match between Task 5/8's definitions and Task 6/9/10's usage.

---

## Execution Handoff

Plan complete and saved to
`Docs/superpowers/plans/2026-08-20-distributor-comparison-portfolio-level.md`.
Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per
task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using
executing-plans, batch execution with checkpoints.

Which approach?
