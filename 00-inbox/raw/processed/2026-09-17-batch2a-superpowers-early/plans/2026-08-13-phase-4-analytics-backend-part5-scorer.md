# Phase 4 Part 5 — Analytics Backend — Scorer (FR-5, FR-6, FR-7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Additionally required for this plan:** use the `model-orchestration` skill for every
> task's implementation dispatch — this plan's tasks are transcription-plus-testing work
> once written out below (mechanical implementation tasks per that skill's Model Selection
> guidance), the default case for Codex delegation. Claude (orchestrator) stays on
> coordination, the adversarial-review gate, and any judgment call a reviewer surfaces —
> never on writing the task code itself for this plan.

**Goal:** Implement the Unifolio Scorer — a composite per-fund quality score (FR-5),
an AUM-weighted portfolio-level roll-up of it (FR-6), and a fully-explained breakdown
so it's never shown as a bare number or a single-word label (FR-7).

**Architecture:** Two new modules under `backend/app/services/analytics/`:
`risk_metrics.py` (pure, DB-read-only functions: monthly NAV series construction,
downside deviation, rolling 12-month consistency) and `scorer.py` (orchestration:
combines `risk_metrics.py`'s output with the already-built `category_ranking.py`
(Return) and `ter.py`/`amfi_aaum_client.py` (cost overlay) into one composite score,
persists it to `fund_scores`, and rolls it up per-portfolio). Two new API routes
follow the exact pattern already established by every other analytics route in
`backend/app/api/analytics.py`.

**Tech Stack:** FastAPI, SQLAlchemy ORM, Pydantic, `decimal.Decimal` throughout
(never `float`), stdlib `statistics`/`calendar` only (no new dependency).

## Global Constraints

- **`Decimal`, never `float`**, for every score, percentile, NAV, or return value
  (CLAUDE.md non-negotiable).
- **No schema changes.** `fund_scores` (scheme_id, computed_at, risk_adjusted_tier,
  cost_adjustment, final_score) is exact and final per `Database-Schema-Unifolio.md`
  — the FR-7 breakdown (return/risk/consistency percentiles) is **not** part of that
  table and must never be persisted; it's recomputed fresh on every read (see Task 2's
  design note for why this is the deliberate, schema-respecting choice, not an
  oversight).
- **Reuse existing private helpers across analytics modules** — this codebase's own
  test suite already imports underscore-prefixed helpers across module boundaries
  (e.g. `test_category_ranking.py` imports `_aum_weighted_average`, `_blend_returns`,
  `_cagr`, `_rank_and_percentile` directly). Follow that convention: import
  `_category_returns`, `_rank_and_percentile`, `_aum_weighted_average`,
  `_latest_aaum_by_scheme`, `_THIN_CATEGORY_THRESHOLD` from `category_ranking.py`,
  and `_ensure_ter_fresh`, `_latest_ter_for_scheme` from `ter.py`. Do not duplicate
  their logic.
- **Formula weights (fixed, from the design doc, resolved with the user
  2026-08-13):** Return 45%, Risk (downside deviation, inverted) 30%, Consistency
  (rolling 12-month category-beat rate) 25%. Cost overlay unchanged from the
  already-resolved ±0.25 TER nudge (0.05 percentage-point dead zone).
- **Tier boundaries are inclusive on the lower bound of each tier**
  (`percentile >= 80` → tier 5, `>= 60` → tier 4, `>= 40` → tier 3, `>= 20` → tier 2,
  else tier 1) — not a strict `>`. `category_ranking.py`'s own percentile formula
  (`(total - rank) / total * 100`) means the *best possible* score in a
  minimum-non-thin category of exactly 5 schemes is exactly `80`, not `> 80` — a
  strict `>` boundary would incorrectly deny that fund tier 5.
- **history window:** month-end anchors span from `today - 5 years` to `today`
  (`risk_metrics.month_end_dates`), regardless of how much history a given scheme
  actually has — schemes with less history naturally get leading `None`s in their
  monthly series (see Task 1). This mirrors the already-resolved Return rule (3yr
  minimum, 5yr blended in when available, no 10yr window) without a second window
  decision.
- Every new function needs a docstring only when the *why*, not the *what*, needs
  explaining (per CLAUDE.md) — follow the terse-but-non-obvious style already used in
  `category_ranking.py` and `ter.py`.

---

### Task 1: `risk_metrics.py` — monthly NAV series, downside deviation, rolling consistency

**Files:**
- Create: `backend/app/services/analytics/risk_metrics.py`
- Test: `backend/tests/services/analytics/test_risk_metrics.py`

**Interfaces:**
- Produces (consumed by Task 2):
  - `month_end_dates(start: date, end: date) -> list[date]`
  - `build_monthly_series(db: Session, scheme_id: uuid.UUID, month_ends: list[date]) -> list[Decimal | None]`
  - `monthly_returns(series: list[Decimal | None]) -> list[Decimal | None]`
  - `compute_downside_deviation(returns: list[Decimal | None]) -> Decimal | None`
  - `rolling_12m_returns(series: list[Decimal | None]) -> list[Decimal | None]`
  - `category_medians(rolling_by_scheme: list[list[Decimal | None]]) -> list[Decimal | None]`
  - `compute_consistency_hit_rate(scheme_rolling: list[Decimal | None], medians: list[Decimal | None]) -> Decimal | None`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/analytics/test_risk_metrics.py
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.reference import NavHistory, Scheme
from app.services.analytics.risk_metrics import (
    build_monthly_series,
    category_medians,
    compute_consistency_hit_rate,
    compute_downside_deviation,
    month_end_dates,
    monthly_returns,
    rolling_12m_returns,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autoflush=False, bind=engine)()


def _scheme(db):
    scheme = Scheme(
        id=uuid.uuid4(), amfi_code=uuid.uuid4().hex[:6], isin="INF123",
        name="Test Fund", amc_name="HDFC AMC", sebi_category="Equity Scheme - Flexi Cap Fund",
    )
    db.add(scheme)
    db.commit()
    return scheme


def test_month_end_dates_spans_start_to_last_complete_month():
    dates = month_end_dates(date(2024, 1, 15), date(2024, 4, 10))
    assert dates == [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31)]


def test_month_end_dates_excludes_current_partial_month():
    dates = month_end_dates(date(2024, 3, 1), date(2024, 3, 15))
    assert dates == []


def test_build_monthly_series_uses_nav_on_or_before_each_anchor():
    db = _session()
    scheme = _scheme(db)
    db.add(NavHistory(scheme_id=scheme.id, date=date(2024, 1, 10), nav=Decimal("10")))
    db.add(NavHistory(scheme_id=scheme.id, date=date(2024, 2, 5), nav=Decimal("11")))
    db.commit()

    month_ends = [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31)]
    series = build_monthly_series(db, scheme.id, month_ends)
    # Jan-end -> last NAV on/before it (Jan 10 = 10). Feb-end -> Feb 5 = 11.
    # Mar-end -> still 11 (nothing newer).
    assert series == [Decimal("10"), Decimal("11"), Decimal("11")]


def test_build_monthly_series_none_before_first_nav_row():
    db = _session()
    scheme = _scheme(db)
    db.add(NavHistory(scheme_id=scheme.id, date=date(2024, 2, 5), nav=Decimal("11")))
    db.commit()

    month_ends = [date(2024, 1, 31), date(2024, 2, 29)]
    series = build_monthly_series(db, scheme.id, month_ends)
    assert series == [None, Decimal("11")]


def test_build_monthly_series_empty_month_ends():
    db = _session()
    scheme = _scheme(db)
    assert build_monthly_series(db, scheme.id, []) == []


def test_monthly_returns_first_entry_always_none():
    series = [Decimal("10"), Decimal("11"), Decimal("9.9")]
    returns = monthly_returns(series)
    assert returns[0] is None
    assert returns[1] == Decimal("11") / Decimal("10") - Decimal(1)
    assert returns[2] == Decimal("9.9") / Decimal("11") - Decimal(1)


def test_monthly_returns_none_when_either_side_missing():
    series = [None, Decimal("10"), None, Decimal("12")]
    returns = monthly_returns(series)
    assert returns == [None, None, None, None]


def test_compute_downside_deviation_only_counts_negative_returns():
    # Returns: +10%, -10%, +5%, -20%. Downside deviation over all 4 (MAR=0):
    # sqrt((0.10^2 + 0.20^2) / 4)
    returns = [Decimal("0.10"), Decimal("-0.10"), Decimal("0.05"), Decimal("-0.20")]
    result = compute_downside_deviation(returns)
    expected = ((Decimal("0.10") ** 2 + Decimal("0.20") ** 2) / Decimal(4)).sqrt()
    assert result == expected


def test_compute_downside_deviation_zero_when_no_negative_returns():
    result = compute_downside_deviation([Decimal("0.10"), Decimal("0.05")])
    assert result == Decimal("0")


def test_compute_downside_deviation_none_when_no_usable_returns():
    assert compute_downside_deviation([None, None]) is None


def test_rolling_12m_returns_needs_twelve_prior_points():
    series = [Decimal(str(100 + i)) for i in range(13)]  # 13 monthly points
    rolling = rolling_12m_returns(series)
    assert rolling[:12] == [None] * 12
    assert rolling[12] == Decimal(str(112)) / Decimal(str(100)) - Decimal(1)


def test_rolling_12m_returns_none_when_either_side_missing():
    series = [None] * 12 + [Decimal("110")]
    rolling = rolling_12m_returns(series)
    assert rolling[12] is None


def test_category_medians_per_index_across_schemes():
    scheme_a = [Decimal("0.10"), Decimal("0.20")]
    scheme_b = [Decimal("0.30"), None]
    scheme_c = [Decimal("0.05"), Decimal("0.40")]
    medians = category_medians([scheme_a, scheme_b, scheme_c])
    assert medians[0] == Decimal("0.10")  # median of 0.10, 0.30, 0.05
    assert medians[1] == Decimal("0.30")  # median of 0.20, 0.40 (0.30's peer is None)


def test_category_medians_empty_input():
    assert category_medians([]) == []


def test_compute_consistency_hit_rate_counts_beats_at_or_above_median():
    scheme_rolling = [Decimal("0.10"), Decimal("0.05"), Decimal("0.30"), None]
    medians = [Decimal("0.08"), Decimal("0.08"), Decimal("0.20"), Decimal("0.10")]
    # index0: 0.10 >= 0.08 -> hit. index1: 0.05 >= 0.08 -> miss.
    # index2: 0.30 >= 0.20 -> hit. index3: scheme value None -> skipped.
    result = compute_consistency_hit_rate(scheme_rolling, medians)
    assert result == Decimal(2) / Decimal(3) * Decimal(100)


def test_compute_consistency_hit_rate_none_when_no_comparable_windows():
    assert compute_consistency_hit_rate([None, None], [Decimal("0.1"), None]) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/services/analytics/test_risk_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.analytics.risk_metrics'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/analytics/risk_metrics.py
"""Risk (downside deviation) and Consistency (rolling 12-month peer-beat
rate) — PRD-04 FR-5a. Both operate on a shared monthly-NAV-series
abstraction so a scheme's NAV history is fetched and bucketed once and
reused for both components.

**Why downside deviation, not plain standard deviation:** Morningstar and
CRISIL both essentially measure symmetric volatility (up-swings count as
"risk" the same as down-swings). An investor doesn't experience a fund's
good months as risk — only the bad ones. Downside deviation (MAR = 0, i.e.
only negative months contribute) is closer to how risk is actually felt,
and is a deliberate point of difference from those two named competitors
per the Phase 4 design doc §6.

**Why rolling-12-month Consistency exists at all:** this is Unifolio's own
differentiating ingredient (user's explicit requirement — see design doc
§6) — no cited competitor scores "how often did this fund beat its peers,
not just by how much" as its own visible axis.

**Unannualized by design:** downside deviation here stays in monthly units.
Annualizing (multiplying by sqrt(12)) is a constant scalar applied equally
to every scheme in a category, so it would not change the relative
percentile ranking this feeds into — skipped as unnecessary work for a
value that's never displayed on its own, only used for ranking.
"""

from __future__ import annotations

import calendar
import statistics
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.reference import NavHistory

_ROLLING_WINDOW_MONTHS = 12


def month_end_dates(start: date, end: date) -> list[date]:
    """Calendar month-end dates from `start`'s month through the last
    complete month at or before `end`. Never includes a partial/current
    month — a volatility measure over years doesn't need this month's
    still-incomplete data point."""
    dates: list[date] = []
    year, month = start.year, start.month
    while True:
        last_day = calendar.monthrange(year, month)[1]
        month_end = date(year, month, last_day)
        if month_end > end:
            break
        dates.append(month_end)
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return dates


def build_monthly_series(
    db: Session, scheme_id: uuid.UUID, month_ends: list[date]
) -> list[Decimal | None]:
    """One NAV-on-or-before value per `month_ends` anchor, position-aligned
    so index i means the same calendar month across every scheme in a
    category — required for Consistency's cross-scheme median comparison.
    `None` for anchors before the scheme's first cached NAV row. Assumes
    the caller has already ensured NAV cache warmth (Task 2's caller
    triggers this as a side effect of the Return computation it runs
    first) — reads the cache only, no network call."""
    if not month_ends:
        return []
    rows = (
        db.query(NavHistory)
        .filter(NavHistory.scheme_id == scheme_id, NavHistory.date <= month_ends[-1])
        .order_by(NavHistory.date)
        .all()
    )
    values: list[Decimal | None] = []
    idx = 0
    last_nav: Decimal | None = None
    for month_end in month_ends:
        while idx < len(rows) and rows[idx].date <= month_end:
            last_nav = rows[idx].nav
            idx += 1
        values.append(last_nav)
    return values


def monthly_returns(series: list[Decimal | None]) -> list[Decimal | None]:
    """Month-over-month % change, position-aligned with `series` (index 0
    is always `None` — no prior point to compare the first anchor to)."""
    result: list[Decimal | None] = [None] * len(series)
    for i in range(1, len(series)):
        prev, curr = series[i - 1], series[i]
        if prev is not None and curr is not None:
            result[i] = curr / prev - Decimal(1)
    return result


def compute_downside_deviation(returns: list[Decimal | None]) -> Decimal | None:
    """Population downside deviation (MAR = 0): sqrt(sum(min(r, 0)^2) / n),
    n = count of usable (non-None) returns. `None` if there are none."""
    values = [r for r in returns if r is not None]
    if not values:
        return None
    sum_sq_downside = sum((v * v for v in values if v < 0), Decimal(0))
    return (sum_sq_downside / Decimal(len(values))).sqrt()


def rolling_12m_returns(series: list[Decimal | None]) -> list[Decimal | None]:
    """Trailing 12-month return ending at each anchor, position-aligned
    with `series` (the first 12 entries are always `None` — no 12 months
    of prior data yet)."""
    result: list[Decimal | None] = [None] * len(series)
    for i in range(_ROLLING_WINDOW_MONTHS, len(series)):
        prev, curr = series[i - _ROLLING_WINDOW_MONTHS], series[i]
        if prev is not None and curr is not None:
            result[i] = curr / prev - Decimal(1)
    return result


def category_medians(rolling_by_scheme: list[list[Decimal | None]]) -> list[Decimal | None]:
    """Per-index median across every scheme's rolling-return series (all
    position-aligned to the same month-end anchors). `None` at an index
    with no data from any scheme."""
    if not rolling_by_scheme:
        return []
    length = len(rolling_by_scheme[0])
    medians: list[Decimal | None] = []
    for i in range(length):
        values = [series[i] for series in rolling_by_scheme if series[i] is not None]
        medians.append(statistics.median(values) if values else None)
    return medians


def compute_consistency_hit_rate(
    scheme_rolling: list[Decimal | None], medians: list[Decimal | None]
) -> Decimal | None:
    """% of rolling 12-month windows where the scheme's return was at or
    above its category's median for that same window. `None` if there are
    no comparable windows (e.g. a fund too new to overlap the category's
    shared history)."""
    hits = 0
    total = 0
    for value, median in zip(scheme_rolling, medians):
        if value is None or median is None:
            continue
        total += 1
        if value >= median:
            hits += 1
    if total == 0:
        return None
    return Decimal(hits) / Decimal(total) * Decimal(100)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/services/analytics/test_risk_metrics.py -v`
Expected: PASS, all tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/analytics/risk_metrics.py backend/tests/services/analytics/test_risk_metrics.py
git commit -m "feat: add risk_metrics (downside deviation, rolling consistency) for Scorer"
```

---

### Task 2: `scorer.py` — composite fund score (FR-5, FR-7) + `fund_scores` persistence

**Files:**
- Create: `backend/app/services/analytics/scorer.py`
- Modify: `backend/app/services/analytics/schemas.py` (add `FundScoreRow`)
- Test: `backend/tests/services/analytics/test_scorer.py`

**Interfaces:**
- Consumes (from Task 1): all seven `risk_metrics.py` functions.
- Consumes (from existing `category_ranking.py`): `_category_returns(db, universe, today) -> dict[uuid.UUID, Decimal]`,
  `_rank_and_percentile(scores: dict[uuid.UUID, Decimal], target_id: uuid.UUID) -> tuple[int, Decimal] | None`,
  `_aum_weighted_average(values: dict[uuid.UUID, Decimal], weights: dict[uuid.UUID, Decimal]) -> Decimal | None`,
  `_latest_aaum_by_scheme(db, scheme_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]`,
  `_THIN_CATEGORY_THRESHOLD` (constant, currently `5`).
- Consumes (from existing `ter.py`): `_ensure_ter_fresh(db, scheme_ids: set[uuid.UUID]) -> None` (async),
  `_latest_ter_for_scheme(db, scheme_id: uuid.UUID) -> tuple[Decimal, date] | None`.
- Consumes (from existing `scheme_universe.py`): `get_category_universe(db, sebi_category: str) -> list[Scheme]` (async).
- Produces (consumed by Task 3 and Task 4):
  - `async def compute_fund_score(db: Session, scheme: Scheme) -> FundScoreRow`

**Design note — why the FR-7 breakdown is never persisted:** `fund_scores`
stores only `risk_adjusted_tier`, `cost_adjustment`, `final_score` (one
historical row per day, per the schema's composite PK) — the per-component
percentiles FR-7 needs to explain a score are not schema columns, and the
schema is exact-and-final (CLAUDE.md — no "just in case" column). So this
task always recomputes the breakdown fresh on every call, and only skips
the `fund_scores` **insert** when a row already exists for today (so
repeated reads within a day don't multiply history rows). This is the
schema-respecting choice, not a caching oversight — every other *derived*
analytics result in this codebase (`category_ranking.py`,
`benchmark.py`) already recomputes fully on every read with zero caching;
only raw *external* data (NAV, TER, AAUM) is cached. `fund_scores` is the
one exception, and only for the terminal tier/cost/final numbers it's
schema-designed to keep history for.

- [ ] **Step 1: Add `FundScoreRow` to `schemas.py`**

Add to `backend/app/services/analytics/schemas.py`:

```python
class FundScoreRow(BaseModel):
    """PRD-04 FR-5/FR-7 — one fund's composite score plus the full
    breakdown (return_percentile, risk_percentile, consistency_hit_rate)
    so it's never displayed as a bare number or a single-word label."""

    scheme_id: str
    scheme_name: str
    category_unavailable: bool
    insufficient_history: bool
    thin_category: bool
    risk_adjusted_tier: int | None
    cost_adjustment: str | None
    final_score: str | None
    return_percentile: str | None
    risk_percentile: str | None
    consistency_hit_rate: str | None
```

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/services/analytics/test_scorer.py
import asyncio
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.reference import FundScore, NavHistory, Scheme, SchemeAaum, SchemeTer
from app.services.analytics.scorer import _tier_from_percentile, compute_fund_score

_TODAY = date.today()
_START_3Y = _TODAY.replace(year=_TODAY.year - 3)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autoflush=False, bind=engine)()


def _scheme(db, name="Test Fund", sebi_category="Equity Scheme - Flexi Cap Fund"):
    scheme = Scheme(
        id=uuid.uuid4(), amfi_code=uuid.uuid4().hex[:6], isin="INF123",
        name=name, amc_name="HDFC AMC", sebi_category=sebi_category,
    )
    db.add(scheme)
    db.commit()
    return scheme


def _seed_monthly_nav(db, scheme, months, start_nav=Decimal("10"), monthly_growth=Decimal("0.01")):
    """Seeds one NAV row per month for `months` months ending today, simple
    compounding growth — enough for build_monthly_series to have real data
    without constructing 5 years of daily rows in a test."""
    nav = start_nav
    for i in range(months, 0, -1):
        row_date = _TODAY.replace(year=_TODAY.year - (i // 12), month=((_TODAY.month - 1 - (i % 12)) % 12) + 1)
        db.add(NavHistory(scheme_id=scheme.id, date=row_date, nav=nav))
        nav *= Decimal(1) + monthly_growth
    db.commit()


def test_tier_from_percentile_boundaries_are_inclusive_lower_bound():
    assert _tier_from_percentile(Decimal("80")) == 5
    assert _tier_from_percentile(Decimal("79.99")) == 4
    assert _tier_from_percentile(Decimal("60")) == 4
    assert _tier_from_percentile(Decimal("40")) == 3
    assert _tier_from_percentile(Decimal("20")) == 2
    assert _tier_from_percentile(Decimal("19.99")) == 1
    assert _tier_from_percentile(Decimal("0")) == 1


def test_compute_fund_score_category_unavailable_when_no_sebi_category():
    db = _session()
    scheme = _scheme(db, sebi_category="")
    row = asyncio.run(compute_fund_score(db, scheme))
    assert row.category_unavailable is True
    assert row.risk_adjusted_tier is None


def test_compute_fund_score_insufficient_history_when_no_return():
    db = _session()
    scheme = _scheme(db)

    async def _no_return(db_, universe, today):
        return {}

    with (
        patch("app.services.analytics.scorer._category_returns", new=AsyncMock(side_effect=_no_return)),
        patch("app.services.analytics.scorer.get_category_universe", new=AsyncMock(return_value=[scheme])),
    ):
        row = asyncio.run(compute_fund_score(db, scheme))
    assert row.insufficient_history is True
    assert row.risk_adjusted_tier is None


def test_compute_fund_score_persists_one_row_per_day():
    db = _session()
    held = _scheme(db, "Held Fund")
    peer = _scheme(db, "Peer Fund")
    _seed_monthly_nav(db, held, 24, monthly_growth=Decimal("0.02"))
    _seed_monthly_nav(db, peer, 24, monthly_growth=Decimal("0.005"))

    async def _returns(db_, universe, today):
        return {held.id: Decimal("0.30"), peer.id: Decimal("0.05")}

    with (
        patch("app.services.analytics.scorer._category_returns", new=AsyncMock(side_effect=_returns)),
        patch("app.services.analytics.scorer.get_category_universe", new=AsyncMock(return_value=[held, peer])),
        patch("app.services.analytics.scorer._ensure_ter_fresh", new=AsyncMock(return_value=None)),
    ):
        row1 = asyncio.run(compute_fund_score(db, held))
        row2 = asyncio.run(compute_fund_score(db, held))

    assert row1.risk_adjusted_tier is not None
    assert row2.risk_adjusted_tier == row1.risk_adjusted_tier
    stored = db.query(FundScore).filter(FundScore.scheme_id == held.id).all()
    assert len(stored) == 1  # second call didn't insert a duplicate for the same day


def test_compute_fund_score_best_return_in_min_category_gets_tier_five():
    db = _session()
    held = _scheme(db, "Held Fund")
    peers = [_scheme(db, f"Peer {i}") for i in range(4)]
    all_schemes = [held, *peers]
    for s in all_schemes:
        _seed_monthly_nav(db, s, 24, monthly_growth=Decimal("0.01"))

    async def _returns(db_, universe, today):
        returns = {held.id: Decimal("0.50")}
        for i, p in enumerate(peers):
            returns[p.id] = Decimal("0.10") - Decimal(str(i)) * Decimal("0.01")
        return returns

    with (
        patch("app.services.analytics.scorer._category_returns", new=AsyncMock(side_effect=_returns)),
        patch("app.services.analytics.scorer.get_category_universe", new=AsyncMock(return_value=all_schemes)),
        patch("app.services.analytics.scorer._ensure_ter_fresh", new=AsyncMock(return_value=None)),
    ):
        row = asyncio.run(compute_fund_score(db, held))

    assert row.risk_adjusted_tier == 5
    assert row.return_percentile is not None
    assert row.risk_percentile is not None
    assert row.consistency_hit_rate is not None


def test_compute_fund_score_cost_adjustment_nudges_final_score():
    db = _session()
    held = _scheme(db, "Held Fund")
    peer = _scheme(db, "Peer Fund")
    _seed_monthly_nav(db, held, 24, monthly_growth=Decimal("0.01"))
    _seed_monthly_nav(db, peer, 24, monthly_growth=Decimal("0.01"))

    db.add(SchemeTer(scheme_id=held.id, reference_period=date(2026, 3, 1), ter_value=Decimal("0.50")))
    db.add(SchemeTer(scheme_id=peer.id, reference_period=date(2026, 3, 1), ter_value=Decimal("1.50")))
    db.add(SchemeAaum(scheme_id=held.id, reference_period=date(2026, 3, 31), aaum_value=Decimal("100")))
    db.add(SchemeAaum(scheme_id=peer.id, reference_period=date(2026, 3, 31), aaum_value=Decimal("100")))
    db.commit()

    async def _returns(db_, universe, today):
        return {held.id: Decimal("0.20"), peer.id: Decimal("0.20")}

    with (
        patch("app.services.analytics.scorer._category_returns", new=AsyncMock(side_effect=_returns)),
        patch("app.services.analytics.scorer.get_category_universe", new=AsyncMock(return_value=[held, peer])),
        patch("app.services.analytics.scorer._ensure_ter_fresh", new=AsyncMock(return_value=None)),
    ):
        row = asyncio.run(compute_fund_score(db, held))

    # held's TER (0.50) is well below the AUM-weighted category average
    # (1.00) -> +0.25 nudge.
    assert row.cost_adjustment == "0.25"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && pytest tests/services/analytics/test_scorer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.analytics.scorer'`

- [ ] **Step 4: Write the implementation**

```python
# backend/app/services/analytics/scorer.py
"""Scorer (FR-5, FR-7) — PRD-04. Composite fund score combining Return
(45%), Risk/downside-deviation (30%, inverted — lower deviation ranks
higher), and Consistency (25%, Unifolio's own differentiating ingredient —
see the Phase 4 design doc §6), plus the already-resolved TER-based cost
overlay (±0.25, 0.05pp dead zone). Computed on-demand; persists one history
row to `fund_scores` per scheme per day (see this task's design note in the
plan for why the FR-7 breakdown itself is never persisted).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.reference import FundScore, Scheme
from app.services.analytics.category_ranking import (
    _THIN_CATEGORY_THRESHOLD,
    _aum_weighted_average,
    _category_returns,
    _latest_aaum_by_scheme,
    _rank_and_percentile,
)
from app.services.analytics.risk_metrics import (
    build_monthly_series,
    category_medians,
    compute_consistency_hit_rate,
    compute_downside_deviation,
    month_end_dates,
    monthly_returns,
    rolling_12m_returns,
)
from app.services.analytics.schemas import FundScoreRow
from app.services.analytics.scheme_universe import get_category_universe
from app.services.analytics.ter import _ensure_ter_fresh, _latest_ter_for_scheme

_RETURN_WEIGHT = Decimal("0.45")
_RISK_WEIGHT = Decimal("0.30")
_CONSISTENCY_WEIGHT = Decimal("0.25")
_TER_DEAD_ZONE = Decimal("0.05")
_TER_NUDGE = Decimal("0.25")
_HISTORY_YEARS = 5


def _tier_from_percentile(percentile: Decimal) -> int:
    if percentile >= Decimal("80"):
        return 5
    if percentile >= Decimal("60"):
        return 4
    if percentile >= Decimal("40"):
        return 3
    if percentile >= Decimal("20"):
        return 2
    return 1


async def _category_component_scores(
    db: Session, universe: list[Scheme], today: date
) -> dict[uuid.UUID, dict[str, Decimal | None]]:
    returns = await _category_returns(db, universe, today)
    if not returns:
        return {}

    month_ends = month_end_dates(today.replace(year=today.year - _HISTORY_YEARS), today)
    series_by_scheme = {
        scheme_id: build_monthly_series(db, scheme_id, month_ends) for scheme_id in returns
    }
    rolling_by_scheme = {
        scheme_id: rolling_12m_returns(series) for scheme_id, series in series_by_scheme.items()
    }
    medians = category_medians(list(rolling_by_scheme.values()))

    downside_by_scheme: dict[uuid.UUID, Decimal] = {}
    for scheme_id, series in series_by_scheme.items():
        deviation = compute_downside_deviation(monthly_returns(series))
        if deviation is not None:
            # Lower deviation is safer -> negate so `_rank_and_percentile`'s
            # "higher value ranks better" ordering favors the lowest
            # deviation.
            downside_by_scheme[scheme_id] = -deviation

    consistency_by_scheme = {
        scheme_id: compute_consistency_hit_rate(rolling_by_scheme[scheme_id], medians)
        for scheme_id in returns
    }

    scores: dict[uuid.UUID, dict[str, Decimal | None]] = {}
    for scheme_id in returns:
        return_rank = _rank_and_percentile(returns, scheme_id)
        risk_rank = (
            _rank_and_percentile(downside_by_scheme, scheme_id)
            if scheme_id in downside_by_scheme
            else None
        )
        return_pct = return_rank[1] if return_rank else None
        risk_pct = risk_rank[1] if risk_rank else None
        consistency = consistency_by_scheme.get(scheme_id)

        composite = None
        if return_pct is not None and risk_pct is not None and consistency is not None:
            composite = (
                _RETURN_WEIGHT * return_pct + _RISK_WEIGHT * risk_pct + _CONSISTENCY_WEIGHT * consistency
            )

        scores[scheme_id] = {
            "return_percentile": return_pct,
            "risk_percentile": risk_pct,
            "consistency_hit_rate": consistency,
            "composite": composite,
        }
    return scores


async def _cost_adjustment(db: Session, scheme: Scheme, universe: list[Scheme]) -> Decimal:
    scheme_ids = {s.id for s in universe}
    await _ensure_ter_fresh(db, scheme_ids)
    ter_by_scheme = {
        s.id: info[0] for s in universe if (info := _latest_ter_for_scheme(db, s.id)) is not None
    }
    own_ter = ter_by_scheme.get(scheme.id)
    if own_ter is None:
        return Decimal("0")
    aaum_by_scheme = _latest_aaum_by_scheme(db, list(ter_by_scheme.keys()))
    category_avg = _aum_weighted_average(ter_by_scheme, aaum_by_scheme)
    if category_avg is None:
        return Decimal("0")
    diff = own_ter - category_avg
    if abs(diff) <= _TER_DEAD_ZONE:
        return Decimal("0")
    return _TER_NUDGE if diff < 0 else -_TER_NUDGE


def _empty_row(scheme: Scheme, *, category_unavailable: bool, insufficient_history: bool) -> FundScoreRow:
    return FundScoreRow(
        scheme_id=str(scheme.id),
        scheme_name=scheme.name,
        category_unavailable=category_unavailable,
        insufficient_history=insufficient_history,
        thin_category=False,
        risk_adjusted_tier=None,
        cost_adjustment=None,
        final_score=None,
        return_percentile=None,
        risk_percentile=None,
        consistency_hit_rate=None,
    )


async def compute_fund_score(db: Session, scheme: Scheme) -> FundScoreRow:
    if not scheme.sebi_category:
        return _empty_row(scheme, category_unavailable=True, insufficient_history=False)

    now = datetime.now(timezone.utc)
    today = now.date()
    universe = await get_category_universe(db, scheme.sebi_category)
    scores = await _category_component_scores(db, universe, today)
    scheme_scores = scores.get(scheme.id)

    if scheme_scores is None or scheme_scores["composite"] is None:
        return _empty_row(scheme, category_unavailable=False, insufficient_history=True)

    composite_by_scheme = {
        sid: s["composite"] for sid, s in scores.items() if s["composite"] is not None
    }
    composite_rank = _rank_and_percentile(composite_by_scheme, scheme.id)
    if composite_rank is None:
        return _empty_row(scheme, category_unavailable=False, insufficient_history=True)

    tier = _tier_from_percentile(composite_rank[1])
    cost_adjustment = await _cost_adjustment(db, scheme, universe)
    final_score = (composite_rank[1] + cost_adjustment).quantize(Decimal("0.01"))

    today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    existing_today = (
        db.query(FundScore)
        .filter(FundScore.scheme_id == scheme.id, FundScore.computed_at >= today_start)
        .first()
    )
    if existing_today is None:
        db.add(
            FundScore(
                scheme_id=scheme.id,
                computed_at=now,
                risk_adjusted_tier=tier,
                cost_adjustment=cost_adjustment,
                final_score=final_score,
            )
        )
        db.commit()

    return FundScoreRow(
        scheme_id=str(scheme.id),
        scheme_name=scheme.name,
        category_unavailable=False,
        insufficient_history=False,
        thin_category=len(universe) < _THIN_CATEGORY_THRESHOLD,
        risk_adjusted_tier=tier,
        cost_adjustment=str(cost_adjustment),
        final_score=str(final_score),
        return_percentile=str(scheme_scores["return_percentile"]),
        risk_percentile=str(scheme_scores["risk_percentile"]),
        consistency_hit_rate=str(scheme_scores["consistency_hit_rate"]),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/services/analytics/test_scorer.py -v`
Expected: PASS, all tests green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/analytics/scorer.py backend/app/services/analytics/schemas.py backend/tests/services/analytics/test_scorer.py
git commit -m "feat: add Scorer composite fund score (FR-5, FR-7)"
```

---

### Task 3: Portfolio-level score roll-up (FR-6)

**Files:**
- Modify: `backend/app/services/analytics/scorer.py`
- Modify: `backend/app/services/analytics/schemas.py` (add `PortfolioScoreSummary`, `AggregatePortfolioScoreResponse`)
- Test: `backend/tests/services/analytics/test_scorer.py` (append)

**Interfaces:**
- Consumes: `compute_fund_score` (Task 2); `compute_holdings(db, household_member_ids) -> list[HoldingRow]`
  from `app.services.dashboard.holdings` (existing — `HoldingRow` has `scheme_id: str`, `current_value: str`);
  `list_household_members`, `get_member_statuses` (existing, same pattern as every other `get_aggregate_*`
  function in this package).
- Produces: `async def compute_portfolio_score(db, household_member_ids: list[uuid.UUID]) -> PortfolioScoreSummary`,
  `async def get_aggregate_portfolio_score(db, user_id: uuid.UUID) -> AggregatePortfolioScoreResponse`.

- [ ] **Step 1: Add schemas**

Add to `backend/app/services/analytics/schemas.py`:

```python
class PortfolioScoreSummary(BaseModel):
    """PRD-04 FR-6 — AUM-weighted (by the member's own holding value, same
    convention as FR-10's weighted TER) roll-up of held funds' final_score,
    computed on-read, never stored."""

    funds: list[FundScoreRow]
    weighted_score: str | None
    covered_value: str
    total_value: str
    uncovered_schemes: list[str]


class AggregatePortfolioScoreResponse(BaseModel):
    members: list[MemberStatus]
    score: PortfolioScoreSummary
```

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/services/analytics/test_scorer.py`:

```python
from app.models.enums import PlanType, Relationship, TransactionType
from app.models.folio import Folio
from app.models.transaction import Transaction
from app.models.user import HouseholdMember, User
from app.services.analytics.scorer import compute_portfolio_score


def _household_member(db):
    user = User(id=uuid.uuid4(), phone_number=f"+9199999{uuid.uuid4().hex[:5]}", created_at=datetime.now(timezone.utc))
    db.add(user)
    db.flush()
    member = HouseholdMember(id=uuid.uuid4(), user_id=user.id, name="Self", relationship=Relationship.SELF, created_at=datetime.now(timezone.utc))
    db.add(member)
    db.commit()
    return member


def _folio_with_purchase(db, member, scheme, amount, units, nav, txn_date):
    folio = Folio(id=uuid.uuid4(), household_member_id=member.id, scheme_id=scheme.id, folio_number=uuid.uuid4().hex[:6], plan_type=PlanType.DIRECT)
    db.add(folio)
    db.commit()
    db.add(Transaction(id=uuid.uuid4(), folio_id=folio.id, import_id=uuid.uuid4(), type=TransactionType.PURCHASE, date=txn_date, amount=amount, units=units, nav=nav))
    db.commit()
    return folio


def test_compute_portfolio_score_empty_when_no_holdings():
    db = _session()
    member = _household_member(db)
    summary = asyncio.run(compute_portfolio_score(db, [member.id]))
    assert summary.funds == []
    assert summary.weighted_score is None


def test_compute_portfolio_score_weights_by_holding_value():
    db = _session()
    member = _household_member(db)
    held = _scheme(db, "Held Fund")
    _seed_monthly_nav(db, held, 24, monthly_growth=Decimal("0.01"))
    _folio_with_purchase(db, member, held, Decimal("1000"), Decimal("100"), Decimal("10"), _START_3Y)

    async def _returns(db_, universe, today):
        return {held.id: Decimal("0.20")}

    async def _nav_lookup(db_, scheme, on_date):
        return Decimal("11"), on_date

    with (
        patch("app.services.analytics.scorer._category_returns", new=AsyncMock(side_effect=_returns)),
        patch("app.services.analytics.scorer.get_category_universe", new=AsyncMock(return_value=[held])),
        patch("app.services.analytics.scorer._ensure_ter_fresh", new=AsyncMock(return_value=None)),
        patch("app.services.dashboard.holdings.get_nav_on_or_before", new=AsyncMock(side_effect=_nav_lookup)),
        patch("app.services.dashboard.holdings.get_previous_nav_from_cache", return_value=None),
    ):
        summary = asyncio.run(compute_portfolio_score(db, [member.id]))

    assert len(summary.funds) == 1
    assert summary.weighted_score == summary.funds[0].final_score
    assert summary.uncovered_schemes == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && pytest tests/services/analytics/test_scorer.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_portfolio_score'`

- [ ] **Step 4: Write the implementation**

Append to `backend/app/services/analytics/scorer.py`:

```python
from app.services.dashboard.aggregate import get_member_statuses
from app.services.dashboard.holdings import compute_holdings
from app.services.dashboard.household_members import list_household_members
from app.services.analytics.schemas import AggregatePortfolioScoreResponse, PortfolioScoreSummary

_EMPTY_PORTFOLIO_SCORE = PortfolioScoreSummary(
    funds=[], weighted_score=None, covered_value="0", total_value="0", uncovered_schemes=[]
)


async def compute_portfolio_score(db: Session, household_member_ids: list[uuid.UUID]) -> PortfolioScoreSummary:
    holdings = await compute_holdings(db, household_member_ids)
    if not holdings:
        return _EMPTY_PORTFOLIO_SCORE

    unique_scheme_ids = {h.scheme_id for h in holdings}
    schemes_by_id = {
        str(s.id): s
        for s in db.query(Scheme).filter(Scheme.id.in_([uuid.UUID(sid) for sid in unique_scheme_ids])).all()
    }

    rows: list[FundScoreRow] = []
    row_by_scheme: dict[str, FundScoreRow] = {}
    for scheme_id_str in unique_scheme_ids:
        row = await compute_fund_score(db, schemes_by_id[scheme_id_str])
        rows.append(row)
        row_by_scheme[scheme_id_str] = row

    total_value = Decimal("0")
    covered_value = Decimal("0")
    weighted_sum = Decimal("0")
    uncovered: set[str] = set()

    for holding in holdings:
        value = Decimal(holding.current_value)
        total_value += value
        row = row_by_scheme[holding.scheme_id]
        if row.final_score is None:
            uncovered.add(holding.scheme_name)
            continue
        covered_value += value
        weighted_sum += value * Decimal(row.final_score)

    weighted_score = (weighted_sum / covered_value).quantize(Decimal("0.01")) if covered_value else None

    return PortfolioScoreSummary(
        funds=rows,
        weighted_score=str(weighted_score) if weighted_score is not None else None,
        covered_value=str(covered_value),
        total_value=str(total_value),
        uncovered_schemes=sorted(uncovered),
    )


async def get_aggregate_portfolio_score(db: Session, user_id: uuid.UUID) -> AggregatePortfolioScoreResponse:
    members = list_household_members(db, user_id)
    statuses = get_member_statuses(db, user_id)
    score = await compute_portfolio_score(db, [m.id for m in members])
    return AggregatePortfolioScoreResponse(members=statuses, score=score)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/services/analytics/test_scorer.py -v`
Expected: PASS, all tests green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/analytics/scorer.py backend/app/services/analytics/schemas.py backend/tests/services/analytics/test_scorer.py
git commit -m "feat: add portfolio-level score roll-up (FR-6)"
```

---

### Task 4: API routes

**Files:**
- Modify: `backend/app/api/analytics.py`
- Test: `backend/tests/api/test_analytics_scorer_route.py`

**Interfaces:**
- Consumes: `compute_fund_score`, `compute_portfolio_score`, `get_aggregate_portfolio_score` (Tasks 2-3);
  `get_current_user`, `get_household_member_for_user` (existing, same as every other route in this file).
- Produces: three new routes, matching the TDD's documented API surface
  (`TDD-Unifolio.md`: `/funds/{scheme_id}/score` GET Analytics PRD-04 FR-5–FR-7) plus the
  member/aggregate pair every other analytics feature in this file already has.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/api/test_analytics_scorer_route.py
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.analytics.schemas import FundScoreRow


def _client():
    return TestClient(app)


def _fake_row(scheme_id):
    return FundScoreRow(
        scheme_id=str(scheme_id), scheme_name="Test Fund", category_unavailable=False,
        insufficient_history=False, thin_category=False, risk_adjusted_tier=4,
        cost_adjustment="0.25", final_score="72.25", return_percentile="70",
        risk_percentile="65", consistency_hit_rate="80",
    )


def test_get_fund_score_404_when_scheme_not_found(monkeypatch):
    from app.db.session import get_db
    from app.services.auth.session import get_current_user

    fake_db = type("DB", (), {"get": lambda self, model, sid: None})()
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": uuid.uuid4()})()
    app.dependency_overrides[get_db] = lambda: fake_db
    client = _client()
    try:
        response = client.get(f"/analytics/funds/{uuid.uuid4()}/score")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_get_fund_score_returns_row_for_existing_scheme():
    from app.db.session import get_db
    from app.services.auth.session import get_current_user

    scheme_id = uuid.uuid4()
    fake_scheme = type("S", (), {"id": scheme_id})()
    fake_db = type("DB", (), {"get": lambda self, model, sid: fake_scheme if sid == scheme_id else None})()

    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": uuid.uuid4()})()
    app.dependency_overrides[get_db] = lambda: fake_db
    client = _client()
    try:
        with patch("app.api.analytics.compute_fund_score", new=AsyncMock(return_value=_fake_row(scheme_id))):
            response = client.get(f"/analytics/funds/{scheme_id}/score")
        assert response.status_code == 200
        assert response.json()["risk_adjusted_tier"] == 4
        assert response.json()["return_percentile"] == "70"
    finally:
        app.dependency_overrides.clear()


def test_get_member_score_404_when_member_not_found():
    from app.services.auth.session import get_current_user

    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": uuid.uuid4()})()
    client = _client()
    try:
        with patch("app.api.analytics.get_household_member_for_user", return_value=None):
            response = client.get(f"/analytics/household-members/{uuid.uuid4()}/score")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/api/test_analytics_scorer_route.py -v`
Expected: FAIL — routes don't exist yet (404 on all, including the "should be 200" case).

- [ ] **Step 3: Write the implementation**

Add to `backend/app/api/analytics.py` imports:

```python
from app.models.reference import Scheme
from app.services.analytics.schemas import (
    AggregatePortfolioScoreResponse,
    FundScoreRow,
    PortfolioScoreSummary,
)
from app.services.analytics.scorer import (
    compute_fund_score,
    compute_portfolio_score,
    get_aggregate_portfolio_score,
)
```

Add routes at the end of `backend/app/api/analytics.py`:

```python
@router.get("/funds/{scheme_id}/score", response_model=FundScoreRow)
async def get_fund_score(
    scheme_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    scheme = db.get(Scheme, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Scheme not found.")
    return await compute_fund_score(db, scheme)


@router.get("/household-members/{member_id}/score", response_model=PortfolioScoreSummary)
async def get_member_portfolio_score(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if get_household_member_for_user(db, user.id, member_id) is None:
        raise HTTPException(status_code=404, detail="Household member not found.")
    return await compute_portfolio_score(db, [member_id])


@router.get("/household/aggregate/score", response_model=AggregatePortfolioScoreResponse)
async def get_household_aggregate_portfolio_score(
    user: User = Depends(get_current_user), db: DbSession = Depends(get_db)
):
    return await get_aggregate_portfolio_score(db, user.id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/api/test_analytics_scorer_route.py -v`
Expected: PASS, all tests green.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && pytest -q`
Expected: PASS, 0 failures, count increased from the pre-Part-5 baseline (verify against the
number reported in the plan's Task 0 pre-flight, i.e. no regressions anywhere else).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/analytics.py backend/tests/api/test_analytics_scorer_route.py
git commit -m "feat: add Scorer API routes (fund-level, portfolio-level, aggregate)"
```

---

### Task 5: Stakeholder-facing Scorer methodology doc (last task — do not start until Tasks 1-4 are merged/green)

**Files:**
- Create: `Docs/Scorer-Methodology-Unifolio.md`

**Interfaces:** None — pure documentation, no code.

This task is explicitly last per the user's own instruction: write it only once the
Scorer is actually built, so every claim in it describes real, tested behavior rather
than an aspirational design.

- [ ] **Step 1: Write the doc**

Write `Docs/Scorer-Methodology-Unifolio.md` — audience is a non-technical stakeholder
(product/business, not an engineer), plain language throughout, no code or Decimal/DB
implementation detail. Structure:

1. **What the score answers** — one paragraph: "how good is this fund, really" boiled
   down to one number and tier, without hiding the reasoning.
2. **The three ingredients** — Return (45%), Risk (30%), Consistency (25%) explained
   exactly as they were explained to the user during design (see this plan's
   companion design doc §6 and the conversation it was approved in) — no jargon,
   analogy-first ("a report card with three subjects").
3. **Why it's different from Morningstar, CRISIL, and apps like PowerUp** — the
   downside-only risk measure and the Consistency ingredient, stated plainly as the
   two concrete points of difference.
4. **The cost adjustment** — the small ±0.25 nudge, in plain terms ("a small bonus or
   penalty based on whether the fund is cheaper or pricier than similar funds").
5. **How to read a score** — walk through one worked example end-to-end (composite
   percentile → tier 1-5 → final score number), using realistic sample values.
6. **What it deliberately is not** — explicitly state the score is a modeling
   opinion, not a guarantee or a neutral fact (mirrors PRD-04's own Risk-table
   language: "never present the scorer as a neutral fact") — one short paragraph.
7. **Where it lives in the product** — the two places a user sees it: a fund's own
   score breakdown, and the portfolio-level rolled-up score.

- [ ] **Step 2: Self-review**

Read the doc once more with fresh eyes: no engineering jargon (Decimal, percentile
rank algorithm internals, table names), no placeholder sections, consistent with what
was actually built (spot-check the weights/thresholds against `scorer.py`'s constants).

- [ ] **Step 3: Commit**

```bash
git add Docs/Scorer-Methodology-Unifolio.md
git commit -m "docs: add stakeholder-facing Scorer methodology explanation"
```
