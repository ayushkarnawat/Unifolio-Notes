# Analytics Precompute Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all 7 live-compute Analytics endpoints with precomputed
`analytics_sections` rows read by one consolidated `GET /analytics/{scope}`,
recomputed out-of-process via ECS Fargate `RunTask` after CAS import and on a
daily backstop — eliminating the SQLAlchemy connection-pool exhaustion caused
by rapid tab-switching firing concurrent multi-minute live-compute requests.

**Architecture:** A new `app/services/analytics/recompute.py::recompute_household_analytics(db, user_id)`
computes all 7 sections × 5 scopes (household-combined + up to 4 members) and
upserts each into `analytics_sections`, wrapped by a household-level
`analytics_recompute_status.started_at` in-flight flag. Every trigger (CAS
import, the daily backstop, a cold-start read, a manual retry) dispatches this
work as a separate ECS Fargate `RunTask` (never inline on a request-serving
replica) via a small `RecomputeDispatcher` abstraction. The 14 old per-section
GET routes are replaced by one `GET /analytics/{scope}` that only reads
`analytics_sections` — never computes live.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Pydantic, boto3 (new), pytest.

**Spec:** `Docs/superpowers/specs/2026-09-02-analytics-precompute-architecture-design.md`

## Global Constraints

- Every `analytics_sections` write goes through `ON CONFLICT DO UPDATE`
  (upsert), never delete-then-insert — a reader must never see a momentary
  empty state for a section that already has data.
- `recompute_household_analytics` reuses the 7 sections' existing compute
  functions (`allocation.py`, `ter.py`, `benchmark.py`, `category_ranking.py`,
  `scorer.py`) completely unchanged — this plan is a pure orchestration/read
  layer around them, never a rewrite of their logic.
- Recompute is dispatched as a separate ECS Fargate `RunTask`, never run
  inline inside a request-serving FastAPI route or background task — an
  inline recompute would hold SQLAlchemy connections across its NAV-warm +
  35-row write for the same pool live requests draw from, reproducing the
  exact pool-exhaustion bug this design exists to fix (spec's Architecture
  Overview). Note: an earlier version of this rationale also cited a
  blocking-event-loop risk from `session.md`'s "still open" item 7 (a
  blocking `db.commit()` inside `async def`) — the spec records that this
  was already fixed in commit `bb5225f` (2026-08-27, predates this design)
  via `commit_off_loop`/`asyncio.to_thread`, and flags `session.md`'s
  "still open" section as stale on that point. `session.md`/`CLAUDE.md`
  should be updated to drop that item; not done as part of this plan since
  it's a docs-only change unrelated to this feature's code.
- A single section's recompute failure keeps its last-known-good row intact
  and sets `failed_at`; it never blocks the other 6 sections or the other 4
  scopes in the same run.
- The exact AWS RunTask invocation contract (cluster ARN, task-definition ARN,
  subnet/security-group ids, container name) is being finalized in a parallel
  AWS-migration session as of 2026-09-02 and is explicitly out of scope here.
  All related settings default to empty strings; `EcsRunTaskDispatcher`
  degrades to a logged no-op when unconfigured, so this plan's code runs and
  is testable before that session's ARNs exist.
- Frontend integration (`frontend/src/features/analytics/api.ts` and its
  callers) is explicitly OUT OF SCOPE for this plan — see the note at the end
  of Task 9.

## Three implementation-level refinements to the literal spec text (flagged per CLAUDE.md's "stop and say so" rule)

Both preserve every guarantee the spec states; neither changes behavior the
spec promised. Flagging them here rather than silently building something
different from the literal spec wording.

1. **No explicit "compute the union, warm once" step.** The spec's
   Architecture Overview describes `recompute_household_analytics` as first
   computing "the union of schemes/categories held anywhere across the
   household's members" and warming NAV for that union once, then fanning out
   to scopes. Task 3 instead processes scopes in **"combined" first, then each
   member**, and adds no new union/warm step. Because every member's holdings
   are a strict subset of the combined household's holdings, and
   `category_ranking.py`/`scorer.py` already carry process-local, TTL'd
   caches (`_category_returns_cache`, `_category_score_cache`) keyed by SEBI
   category, the combined pass alone populates those caches — every
   subsequent per-member scope call for a category already seen becomes a
   free in-process cache hit, with `warm_nav_history` invoked for each
   distinct category/scheme only once. Same cost guarantee (spec's stated
   "not once per scope"), reached via scope ordering + code that already
   exists instead of new orchestration.
2. **No new `nav_fetch_attempts` table.** The spec says to "swap the
   process-local dict check for a query against `nav_history`'s latest row
   per scheme" — Task 2 does exactly this (a windowed freshness check
   against `nav_history`), so this one is consistent with the literal spec
   text, but is flagged here because an earlier draft of this plan
   (documented in this session's prior working notes, never shown to the
   user) considered a heavier `nav_fetch_attempts` table to preserve the old
   in-memory cache's "record an attempt even on failed fetch" behavior. That
   heavier design was rejected: `warm_nav_history` is now called only from
   `recompute_household_analytics` (at most a handful of times per household
   per day), not from interactive per-page-load traffic (the original bug's
   actual frequency) — so the "re-fetch storm during an outage" risk the old
   dict-based backoff protected against no longer applies at this call
   volume. The residual edge case (a scheme's fetch fails during an outage,
   then gets retried again within the same daily-backstop run) is bounded
   and accepted, documented as a code comment matching `holdings.py`'s
   existing "known, accepted limitation" comment style.
3. **CAS-import dispatch lives in `confirm_import_route` (`app/api/imports.py`),
   not in `confirm_import` itself (`app/services/import_/service.py:137`)**
   as the spec's Architecture Overview literally states ("one line added to
   `confirm_import`"). `confirm_import` doesn't receive a `BackgroundTasks`
   instance — only its route handler does, and `background_tasks.add_task`
   is the mechanism the dispatch needs so the request isn't held open for
   the `boto3` `run_task` round-trip. This exactly mirrors the route's
   already-existing `_prefetch_member_nav_history` background task, which
   is scheduled from the same route for the same reason. Task 6's test also
   lives in `tests/api/test_imports_routes.py` rather than the spec's
   `tests/services/import_/test_service.py`, consistent with the dispatch
   call's actual location.

---

### Task 1: `analytics_sections` / `analytics_recompute_status` models + migration

**Files:**
- Create: `backend/app/models/analytics.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0010_analytics_sections.py`
- Test: `backend/tests/models/test_analytics_models.py`

**Interfaces:**
- Produces: `AnalyticsSection` (PK `(user_id, scope_key, section)`, plus
  `household_member_id: uuid.UUID | None`, `payload: dict`,
  `computed_at: datetime`, `failed_at: datetime | None`) and
  `AnalyticsRecomputeStatus` (PK `user_id`, `started_at: datetime | None`) —
  both imported from `app.models.analytics` by every later task.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/models/test_analytics_models.py
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.analytics import AnalyticsRecomputeStatus, AnalyticsSection
from app.models.user import User


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[User.__table__, AnalyticsSection.__table__, AnalyticsRecomputeStatus.__table__]
    )
    return sessionmaker(autoflush=False, bind=engine)()


def _user(db) -> User:
    user = User(id=uuid.uuid4(), phone_number="+919999999999", created_at=datetime.now(timezone.utc))
    db.add(user)
    db.commit()
    return user


def test_analytics_section_round_trip_for_combined_scope():
    db = _session()
    user = _user(db)
    now = datetime.now(timezone.utc)

    row = AnalyticsSection(
        user_id=user.id, scope_key="combined", section="allocation", household_member_id=None,
        payload={"by_category": [], "by_amc": [], "total_value": "0"}, computed_at=now, failed_at=None,
    )
    db.add(row)
    db.commit()

    fetched = db.get(AnalyticsSection, (user.id, "combined", "allocation"))
    assert fetched is not None
    assert fetched.payload == {"by_category": [], "by_amc": [], "total_value": "0"}
    assert fetched.household_member_id is None
    assert fetched.failed_at is None


def test_analytics_section_scope_key_is_the_member_id_as_a_string():
    db = _session()
    user = _user(db)
    member_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    row = AnalyticsSection(
        user_id=user.id, scope_key=str(member_id), section="ter", household_member_id=member_id,
        payload={"weighted_ter": None, "covered_value": "0", "total_value": "0", "reference_period": None, "uncovered_schemes": []},
        computed_at=now, failed_at=None,
    )
    db.add(row)
    db.commit()

    fetched = db.get(AnalyticsSection, (user.id, str(member_id), "ter"))
    assert fetched.household_member_id == member_id


def test_analytics_recompute_status_defaults_to_no_started_at():
    db = _session()
    user = _user(db)

    status = AnalyticsRecomputeStatus(user_id=user.id, started_at=None)
    db.add(status)
    db.commit()

    fetched = db.get(AnalyticsRecomputeStatus, user.id)
    assert fetched.started_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/models/test_analytics_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.analytics'`

- [ ] **Step 3: Write the models**

```python
# backend/app/models/analytics.py
"""Precomputed per-scope, per-section Analytics results (see
Docs/superpowers/specs/2026-09-02-analytics-precompute-architecture-design.md).
Every GET /analytics/{scope} read is a plain row lookup here — never a live
call into allocation.py/ter.py/benchmark.py/category_ranking.py/scorer.py."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalyticsSection(Base):
    __tablename__ = "analytics_sections"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    # "combined" or a household_members.id rendered as str — deliberately
    # NOT the nullable household_member_id FK below: Postgres treats NULL as
    # distinct-from-every-other-NULL, so a nullable column can't anchor a
    # composite PK's uniqueness the way a literal "combined" string can.
    scope_key: Mapped[str] = mapped_column(String, primary_key=True)
    section: Mapped[str] = mapped_column(String, primary_key=True)
    # NULL for the "combined" scope; set for a member scope. Not part of the
    # PK — kept only so a future member-deletion feature has a column to
    # cascade against. No such feature exists yet (YAGNI: no cascade logic
    # is wired up here, there is nothing to cascade from).
    household_member_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("household_members.id"))
    payload: Mapped[dict] = mapped_column(JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Cleared (set back to NULL) on the next successful recompute of this
    # exact row. A row with no prior success is simply absent (see
    # recompute.py's _mark_section_failed) rather than present-with-NULL-
    # payload — the frontend's cold-start "no row yet" state covers that.
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalyticsRecomputeStatus(Base):
    """One row per user: is a recompute currently running for this
    household? A household-level fact, not per-section — matches the
    warm-once/fan-out design where "in progress" naturally applies to the
    whole recompute run, not any one of its 35 output rows."""

    __tablename__ = "analytics_recompute_status"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 4: Register the module on `Base.metadata`**

```python
# backend/app/models/__init__.py
"""Importing this module registers every model on Base.metadata."""

from app.models import (  # noqa: F401
    analytics,
    auth,
    folio,
    imports,
    reference,
    snapshot,
    transaction,
    user,
)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/models/test_analytics_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Write the migration**

```python
# backend/alembic/versions/0010_analytics_sections.py
"""analytics_sections + analytics_recompute_status

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-02

Backs Docs/superpowers/specs/2026-09-02-analytics-precompute-architecture-design.md.
Replaces on-request live compute for the 7 Analytics sections with
precomputed rows, one per (user, scope, section); analytics_recompute_status
is a one-row-per-user "is a recompute currently running" flag consulted
before dispatching a new one.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_sections",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("scope_key", sa.String(), primary_key=True),
        sa.Column("section", sa.String(), primary_key=True),
        sa.Column("household_member_id", sa.Uuid(), sa.ForeignKey("household_members.id"), nullable=True),
        sa.Column("payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "analytics_recompute_status",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("analytics_recompute_status")
    op.drop_table("analytics_sections")
```

- [ ] **Step 7: Run the migration against the local dev DB**

Run: `cd backend && .venv/bin/alembic upgrade head`
Expected: applies revision 0010 with no errors.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/analytics.py backend/app/models/__init__.py backend/alembic/versions/0010_analytics_sections.py backend/tests/models/test_analytics_models.py
git commit -m "feat: add analytics_sections and analytics_recompute_status models"
```

---

### Task 2: DB-backed NAV freshness fix in `nav.py`

**Files:**
- Modify: `backend/app/services/dashboard/nav.py`
- Modify: `backend/app/services/analytics/ter.py` (comment only, line ~44)
- Modify: `backend/app/services/analytics/scorer.py` (comment only, line ~54)
- Test: `backend/tests/services/dashboard/test_nav.py`

**Interfaces:**
- Produces: `warm_nav_history(db, schemes)` — same signature, same
  behavior/docstring contract as today, but its "already fresh, skip" check
  now reads `nav_history` instead of an in-process dict. `_NAV_WARM_TTL_SECONDS`,
  `_nav_warm_clock`, `_nav_warm_cache`, `_nav_warm_lock` are removed.

- [ ] **Step 1: Write the failing tests (replace the two TTL-coupled tests)**

Replace `test_warm_nav_history_skips_scheme_refetched_within_ttl` and
`test_warm_nav_history_refetches_scheme_once_ttl_has_expired` in
`backend/tests/services/dashboard/test_nav.py` (currently lines 351-385) with:

```python
def test_warm_nav_history_skips_scheme_with_a_fresh_nav_history_row():
    import asyncio
    from app.models.reference import NavHistory

    db = _session()
    scheme = _scheme(db)
    db.add(NavHistory(scheme_id=scheme.id, date=date.today(), nav=Decimal("50.0000")))
    db.commit()

    fetch = AsyncMock(return_value=[(date.today(), Decimal("51.0000"))])

    with patch("app.services.dashboard.nav._fetch_nav_history", new=fetch):
        asyncio.run(warm_nav_history(db, [scheme]))

    fetch.assert_not_awaited()


def test_warm_nav_history_refetches_scheme_with_a_stale_nav_history_row():
    import asyncio
    from datetime import timedelta
    from app.models.reference import NavHistory

    db = _session()
    scheme = _scheme(db)
    stale_date = date.today() - timedelta(days=nav_module._NAV_FRESHNESS_WINDOW_DAYS + 1)
    db.add(NavHistory(scheme_id=scheme.id, date=stale_date, nav=Decimal("50.0000")))
    db.commit()

    fetch = AsyncMock(return_value=[(date.today(), Decimal("51.0000"))])

    with patch("app.services.dashboard.nav._fetch_nav_history", new=fetch):
        asyncio.run(warm_nav_history(db, [scheme]))

    fetch.assert_awaited_once()


def test_warm_nav_history_refetches_scheme_with_no_nav_history_row_at_all():
    import asyncio

    db = _session()
    scheme = _scheme(db)

    fetch = AsyncMock(return_value=[(date.today(), Decimal("51.0000"))])

    with patch("app.services.dashboard.nav._fetch_nav_history", new=fetch):
        asyncio.run(warm_nav_history(db, [scheme]))

    fetch.assert_awaited_once()
```

`test_warm_nav_history_commits_once_for_the_whole_batch_not_once_per_scheme`
(lines 388-415) references neither `_nav_warm_clock` nor
`_NAV_WARM_TTL_SECONDS` — leave it exactly as-is.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_nav.py -v -k warm_nav_history`
Expected: FAIL — `AttributeError: module 'app.services.dashboard.nav' has no attribute '_NAV_FRESHNESS_WINDOW_DAYS'`

- [ ] **Step 3: Replace the TTL cache with a DB-backed freshness check**

In `backend/app/services/dashboard/nav.py`, replace lines 34-47 (the comment
block plus `_NAV_WARM_TTL_SECONDS`/`_nav_warm_clock`/`_nav_warm_cache`/`_nav_warm_lock`):

```python
# `warm_nav_history` is now called only from recompute.py's
# recompute_household_analytics, run as a short-lived ECS Fargate RunTask —
# a fresh process per invocation, sometimes several times a day for the same
# household. A process-local "already warmed" cache doesn't survive across
# those invocations, so the freshness check instead queries nav_history
# itself: any scheme with a row dated within this window is treated as
# fresh regardless of which process fetched it. The window (rather than
# requiring exactly today's row) tolerates weekends/holidays when NSE/AMFI
# simply hasn't published a new NAV yet.
#
# Known, accepted limitation (mirrors holdings.py's posture): if mfapi.in is
# down for an entire daily-backstop run, every household in that run will
# retry the fetch and fail again rather than backing off after the first
# failure — bounded to at most one wasted retry per household per day, not
# worth a dedicated attempts-tracking table at this call frequency.
_NAV_FRESHNESS_WINDOW_DAYS = 3
```

Add `timedelta` to the existing `from datetime import date, datetime` import
(becomes `from datetime import date, datetime, timedelta`).

Add a new function directly above `warm_nav_history` (after `_upsert_nav_history`/`_latest_cached_on_or_before`, before `get_nav_on_or_before`):

```python
def _fresh_scheme_ids(db: Session, scheme_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    scheme_ids = list(scheme_ids)
    if not scheme_ids:
        return set()
    cutoff = date.today() - timedelta(days=_NAV_FRESHNESS_WINDOW_DAYS)
    rows = (
        db.query(NavHistory.scheme_id)
        .filter(NavHistory.scheme_id.in_(scheme_ids), NavHistory.date >= cutoff)
        .distinct()
        .all()
    )
    return {row[0] for row in rows}
```

Replace `warm_nav_history`'s body (keep its signature and opening docstring
paragraph, rewrite the second paragraph and the "skips" logic):

```python
async def warm_nav_history(db: Session, schemes: Iterable[Scheme]) -> None:
    """Concurrently fetch and cache full NAV history for a batch of
    schemes, deduplicated by scheme id. Lets a subsequent sequential
    per-scheme, per-window lookup loop (category-ranking/scorer's 3yr+5yr
    CAGR calc across an entire SEBI-category peer universe, which can be
    30-150+ schemes) resolve from the local cache instead of one live
    network round-trip per scheme per window — the difference between a
    single concurrent batch and a multi-minute sequential hang. Best-
    effort: a scheme whose fetch fails is simply left unwarmed, same
    degrade-gracefully posture as `get_nav_on_or_before`.

    Skips any scheme with a nav_history row within `_NAV_FRESHNESS_WINDOW_DAYS`
    of today — without this, repeat calls (e.g. two scopes in the same
    household recompute, or two households' recomputes minutes apart)
    re-fetch the entire category universe's NAV history from the network
    every time."""
    unique = {scheme.id: scheme for scheme in schemes}

    fresh_ids = _fresh_scheme_ids(db, unique.keys())
    to_fetch = {scheme_id: scheme for scheme_id, scheme in unique.items() if scheme_id not in fresh_ids}

    async def fetch(scheme: Scheme) -> tuple[Scheme, list[tuple[date, Decimal]] | None]:
        try:
            return scheme, await _fetch_nav_history(scheme.amfi_code)
        except httpx.HTTPError:
            return scheme, None

    # Instrumented 2026-08-20 to root-cause a reported regression (Category
    # Ranking/Scorer got slower, not faster, after the commit-batching and
    # bulk-query fixes) — logs which phase (network fetch vs DB write)
    # actually dominates a given run instead of guessing from wall-clock
    # alone. Cheap enough (a handful of time.perf_counter calls) to leave in
    # permanently rather than strip out once this is root-caused.
    fetch_start = time.perf_counter()
    fetched = await asyncio.gather(*(fetch(scheme) for scheme in to_fetch.values()))
    fetch_elapsed = time.perf_counter() - fetch_start

    commit_start = time.perf_counter()
    any_rows = False
    for scheme, rows in fetched:
        if rows:
            any_rows = True
            await _upsert_nav_history(db, scheme.id, rows, commit=False)
    # One commit for the whole batch, not one per scheme — a category
    # universe can be 1000+ schemes, and a per-scheme commit means
    # 1000+ fsync-bound round trips (57x slower measured on a WSL
    # DrvFs-mounted dev DB than a native filesystem, live 2026-08-19).
    if any_rows:
        await commit_off_loop(db)
    commit_elapsed = time.perf_counter() - commit_start

    logger.info(
        "warm_nav_history: %d schemes total, %d fetched over network, "
        "fetch=%.2fs commit=%.2fs",
        len(unique), len(to_fetch), fetch_elapsed, commit_elapsed,
    )
```

`threading` stays imported (`_nav_http_client_lock`, `_nav_fetches_in_flight_lock`
still use it); `time` stays imported (`time.perf_counter` still used).

- [ ] **Step 4: Fix the two dangling comment references**

`backend/app/services/analytics/ter.py` (~line 44), change
`` (mirrors nav.py's `_NAV_WARM_TTL_SECONDS` pattern) `` to
`` (mirrors nav.py's warm-cache posture) ``.

`backend/app/services/analytics/scorer.py` (~line 54), change
`` Mirrors nav.py's warm-cache posture (`_NAV_WARM_TTL_SECONDS`): this `` to
`` Mirrors nav.py's warm-cache posture: this ``.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/services/dashboard/test_nav.py -v`
Expected: PASS (all tests, including the untouched batch-commit and
concurrency tests)

- [ ] **Step 6: Run the full backend test suite to check for other breakage**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS — confirms no other file referenced the removed symbols
(already grepped clean: only `nav.py` itself and the two comment-only
mentions above did).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/dashboard/nav.py backend/app/services/analytics/ter.py backend/app/services/analytics/scorer.py backend/tests/services/dashboard/test_nav.py
git commit -m "fix: make warm_nav_history's freshness check DB-backed, not process-local"
```

---

### Task 3: `recompute_household_analytics`

**Files:**
- Create: `backend/app/services/analytics/recompute.py`
- Test: `backend/tests/services/analytics/test_recompute.py`

**Interfaces:**
- Consumes: `AnalyticsSection`, `AnalyticsRecomputeStatus` (Task 1);
  `list_household_members(db, user_id) -> list[HouseholdMember]`,
  `get_member_statuses(db, user_id) -> list[MemberStatus]` (existing,
  `app.services.dashboard.household_members` / `app.services.dashboard.aggregate`);
  the 7 existing `compute_*(db, member_ids: list[uuid.UUID])` functions from
  `allocation.py`/`ter.py`/`benchmark.py`/`category_ranking.py`/`scorer.py`
  (all `async def`, unchanged); `commit_off_loop(db)` (`app.db.session`).
- Produces: `async def recompute_household_analytics(db: Session, user_id: uuid.UUID) -> None`
  and `def should_dispatch_recompute(db: Session, user_id: uuid.UUID) -> bool`
  — both imported by Task 6 (import trigger), Task 7 (read endpoint), Task 8
  (retry endpoint), and Task 5 (script entrypoint).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/analytics/test_recompute.py
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.analytics import AnalyticsRecomputeStatus, AnalyticsSection
from app.models.enums import Relationship
from app.models.user import HouseholdMember, User
from app.services.analytics.recompute import (
    _SECTIONS,
    recompute_household_analytics,
    should_dispatch_recompute,
)
from app.services.analytics.schemas import (
    AnalyticsAllocationSummary,
    CategoryRankingSummary,
    DirectRegularTerComparison,
    FundVsBenchmarkSummary,
    PortfolioBenchmarkSummary,
    PortfolioScoreSummary,
    WeightedTerSummary,
)


def _session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(autoflush=False, bind=engine)()


def _user_with_members(db, n_members=2) -> tuple[User, list[HouseholdMember]]:
    user = User(id=uuid.uuid4(), phone_number=f"+9199{uuid.uuid4().hex[:8]}", created_at=datetime.now(timezone.utc))
    db.add(user)
    db.flush()
    members = []
    for i in range(n_members):
        member = HouseholdMember(
            id=uuid.uuid4(), user_id=user.id, name=f"Member {i}", relationship=Relationship.SELF,
            created_at=datetime.now(timezone.utc),
        )
        db.add(member)
        members.append(member)
    db.commit()
    return user, members


_MOCK_RESULTS = {
    "allocation": AnalyticsAllocationSummary(by_category=[], by_amc=[], total_value="0"),
    "ter": WeightedTerSummary(weighted_ter=None, covered_value="0", total_value="0", reference_period=None, uncovered_schemes=[]),
    "ter_direct_regular": DirectRegularTerComparison(
        direct=WeightedTerSummary(weighted_ter=None, covered_value="0", total_value="0", reference_period=None, uncovered_schemes=[]),
        regular=WeightedTerSummary(weighted_ter=None, covered_value="0", total_value="0", reference_period=None, uncovered_schemes=[]),
    ),
    "benchmark": PortfolioBenchmarkSummary(portfolio_xirr=None, benchmarks=[]),
    "benchmark_funds": FundVsBenchmarkSummary(funds=[], overall_portfolio_xirr=None, overall_broad_market_xirr=None),
    "category_ranking": CategoryRankingSummary(funds=[]),
    "score": PortfolioScoreSummary(funds=[], weighted_score=None, covered_value="0", total_value="0", uncovered_schemes=[]),
}


def _patched_computes():
    return [
        patch(f"app.services.analytics.recompute._SECTIONS", _SECTIONS)  # placeholder, replaced below
    ]


def test_recompute_writes_one_row_per_scope_per_section():
    db = _session()
    user, members = _user_with_members(db, n_members=2)

    mocks = {
        section.name: AsyncMock(return_value=_MOCK_RESULTS[section.name]) for section in _SECTIONS
    }
    patches = [patch.object(section, "compute", mocks[section.name]) for section in _SECTIONS]
    for p in patches:
        p.start()
    try:
        import asyncio
        asyncio.run(recompute_household_analytics(db, user.id))
    finally:
        for p in patches:
            p.stop()

    rows = db.query(AnalyticsSection).filter(AnalyticsSection.user_id == user.id).all()
    # 3 scopes (combined + 2 members) x 7 sections
    assert len(rows) == 21
    scope_keys = {row.scope_key for row in rows}
    assert scope_keys == {"combined", str(members[0].id), str(members[1].id)}
    combined_allocation = db.get(AnalyticsSection, (user.id, "combined", "allocation"))
    assert combined_allocation.payload["members"][0]["id"] in {str(members[0].id), str(members[1].id)}
    member_allocation = db.get(AnalyticsSection, (user.id, str(members[0].id), "allocation"))
    assert "members" not in member_allocation.payload


def test_recompute_clears_started_at_when_done():
    db = _session()
    user, _members = _user_with_members(db, n_members=1)

    mocks_active = [patch.object(section, "compute", AsyncMock(return_value=_MOCK_RESULTS[section.name])) for section in _SECTIONS]
    for p in mocks_active:
        p.start()
    try:
        import asyncio
        asyncio.run(recompute_household_analytics(db, user.id))
    finally:
        for p in mocks_active:
            p.stop()

    status = db.get(AnalyticsRecomputeStatus, user.id)
    assert status.started_at is None


def test_recompute_leaves_existing_row_and_sets_failed_at_when_a_section_raises():
    db = _session()
    user, _members = _user_with_members(db, n_members=1)

    # Seed a prior successful "score" row for combined scope.
    db.add(AnalyticsSection(
        user_id=user.id, scope_key="combined", section="score", household_member_id=None,
        payload={"funds": [], "weighted_score": "50", "covered_value": "0", "total_value": "0", "uncovered_schemes": []},
        computed_at=datetime.now(timezone.utc), failed_at=None,
    ))
    db.commit()

    def failing_score(*args, **kwargs):
        raise RuntimeError("boom")

    patches = []
    for section in _SECTIONS:
        if section.name == "score":
            patches.append(patch.object(section, "compute", AsyncMock(side_effect=failing_score)))
        else:
            patches.append(patch.object(section, "compute", AsyncMock(return_value=_MOCK_RESULTS[section.name])))
    for p in patches:
        p.start()
    try:
        import asyncio
        asyncio.run(recompute_household_analytics(db, user.id))
    finally:
        for p in patches:
            p.stop()

    combined_score = db.get(AnalyticsSection, (user.id, "combined", "score"))
    assert combined_score.payload["weighted_score"] == "50"  # unchanged
    assert combined_score.failed_at is not None

    status = db.get(AnalyticsRecomputeStatus, user.id)
    assert status.started_at is None  # still cleared despite the mid-loop failure


def test_recompute_clears_a_stale_failed_at_on_next_success():
    db = _session()
    user, _members = _user_with_members(db, n_members=1)

    db.add(AnalyticsSection(
        user_id=user.id, scope_key="combined", section="allocation", household_member_id=None,
        payload={"by_category": [], "by_amc": [], "total_value": "0"},
        computed_at=datetime.now(timezone.utc), failed_at=datetime.now(timezone.utc),
    ))
    db.commit()

    patches = [patch.object(section, "compute", AsyncMock(return_value=_MOCK_RESULTS[section.name])) for section in _SECTIONS]
    for p in patches:
        p.start()
    try:
        import asyncio
        asyncio.run(recompute_household_analytics(db, user.id))
    finally:
        for p in patches:
            p.stop()

    combined_allocation = db.get(AnalyticsSection, (user.id, "combined", "allocation"))
    assert combined_allocation.failed_at is None


def test_should_dispatch_recompute_true_when_no_status_row():
    db = _session()
    user, _members = _user_with_members(db, n_members=0)
    assert should_dispatch_recompute(db, user.id) is True


def test_should_dispatch_recompute_false_while_recently_started():
    db = _session()
    user, _members = _user_with_members(db, n_members=0)
    db.add(AnalyticsRecomputeStatus(user_id=user.id, started_at=datetime.now(timezone.utc)))
    db.commit()
    assert should_dispatch_recompute(db, user.id) is False


def test_should_dispatch_recompute_true_once_started_at_is_stale():
    db = _session()
    user, _members = _user_with_members(db, n_members=0)
    stale = datetime.now(timezone.utc) - timedelta(hours=3)
    db.add(AnalyticsRecomputeStatus(user_id=user.id, started_at=stale))
    db.commit()
    assert should_dispatch_recompute(db, user.id) is True


def test_recompute_does_not_refetch_nav_over_network_for_a_category_shared_across_scopes():
    """Regression test for the spec's Testing Strategy: `warm_nav_history`
    must be effectively invoked at most once, network-fetch-wise, for the
    union of schemes/categories touched across the whole recompute run --
    not once per scope -- even though this module (deliberately, see this
    plan's flagged refinement (a)) has no explicit union/warm step of its
    own. Uses the real, unmocked `compute_category_ranking` so the
    assertion exercises category_ranking.py's actual process-local
    `_category_returns_cache` plus Task 2's DB-backed NAV freshness check --
    together, these are what deliver the spec's cost guarantee here."""
    import asyncio

    import app.services.analytics.category_ranking as category_ranking_module
    from app.models.enums import PlanType, TransactionType
    from app.models.folio import Folio
    from app.models.reference import Scheme
    from app.models.transaction import Transaction

    category_ranking_module._category_returns_cache.clear()

    db = _session()
    user, members = _user_with_members(db, n_members=2)

    scheme = Scheme(
        id=uuid.uuid4(), amfi_code="SHARED1", isin="INF999", name="Shared Fund",
        amc_name="Test AMC", sebi_category="Equity Scheme - Flexi Cap Fund",
    )
    db.add(scheme)
    db.flush()
    # Both members hold the SAME scheme, so its category is touched by
    # every scope in this run (combined, member 0, member 1) -- exactly the
    # cross-scope overlap the spec's "not once per scope" claim is about.
    for member in members:
        folio = Folio(
            id=uuid.uuid4(), household_member_id=member.id, scheme_id=scheme.id,
            folio_number=uuid.uuid4().hex[:6], plan_type=PlanType.DIRECT,
        )
        db.add(folio)
        db.flush()
        db.add(Transaction(
            id=uuid.uuid4(), folio_id=folio.id, import_id=uuid.uuid4(), type=TransactionType.PURCHASE,
            date=date(2020, 1, 1), amount=Decimal("1000"), units=Decimal("100"), nav=Decimal("10"),
        ))
    db.commit()

    other_section_patches = [
        patch.object(section, "compute", AsyncMock(return_value=_MOCK_RESULTS[section.name]))
        for section in _SECTIONS if section.name != "category_ranking"
    ]
    for p in other_section_patches:
        p.start()

    fetch = AsyncMock(return_value=[(date.today(), Decimal("11.0000"))])
    try:
        with patch("app.services.dashboard.nav._fetch_nav_history", new=fetch), \
             patch("app.services.analytics.category_ranking.get_category_universe", return_value=[scheme]):
            asyncio.run(recompute_household_analytics(db, user.id))
    finally:
        for p in other_section_patches:
            p.stop()

    assert fetch.await_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/services/analytics/test_recompute.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.analytics.recompute'`

- [ ] **Step 3: Write `recompute.py`**

```python
# backend/app/services/analytics/recompute.py
"""Orchestration layer for Docs/superpowers/specs/2026-09-02-analytics-precompute-architecture-design.md.
Computes all 7 Analytics sections for all 5 scopes (household-combined + up
to 4 members) and upserts each into analytics_sections. Reuses every
section's existing compute_*(db, member_ids) function completely unchanged
-- this module is pure orchestration, never a rewrite of section logic.

Scope order is combined-first, then each member, deliberately (see this
plan's "implementation-level refinements to the literal spec text" note):
category_ranking.py/scorer.py's own process-local, TTL'd caches
(_category_returns_cache, _category_score_cache) are populated by the
combined pass and naturally serve every subsequent per-member scope's
repeat categories as free cache hits, so warm_nav_history is still invoked
at most once per distinct category/scheme across the whole run -- without
this module needing its own separate union-then-warm step.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db.session import commit_off_loop
from app.models.analytics import AnalyticsRecomputeStatus, AnalyticsSection
from app.services.analytics.allocation import compute_category_allocation
from app.services.analytics.benchmark import compute_fund_vs_benchmark, compute_portfolio_vs_benchmarks
from app.services.analytics.category_ranking import compute_category_ranking
from app.services.analytics.schemas import (
    AggregateAnalyticsAllocationResponse,
    AggregateCategoryRankingResponse,
    AggregateDirectRegularTerResponse,
    AggregateFundVsBenchmarkResponse,
    AggregatePortfolioBenchmarkResponse,
    AggregatePortfolioScoreResponse,
    AggregateWeightedTerResponse,
)
from app.services.analytics.scorer import compute_portfolio_score
from app.services.analytics.ter import compute_direct_regular_ter_comparison, compute_weighted_ter
from app.services.dashboard.aggregate import get_member_statuses
from app.services.dashboard.household_members import list_household_members
from app.services.dashboard.schemas import MemberStatus

logger = logging.getLogger(__name__)

_STALE_RECOMPUTE_CEILING = timedelta(hours=2)


@dataclass(frozen=True)
class _SectionSpec:
    name: str
    compute: Callable[[Session, list[uuid.UUID]], Awaitable[BaseModel]]
    wrap_combined: Callable[[list[MemberStatus], BaseModel], BaseModel]


_SECTIONS: list[_SectionSpec] = [
    _SectionSpec("allocation", compute_category_allocation, lambda statuses, result: AggregateAnalyticsAllocationResponse(members=statuses, allocation=result)),
    _SectionSpec("ter", compute_weighted_ter, lambda statuses, result: AggregateWeightedTerResponse(members=statuses, ter=result)),
    _SectionSpec("ter_direct_regular", compute_direct_regular_ter_comparison, lambda statuses, result: AggregateDirectRegularTerResponse(members=statuses, ter=result)),
    _SectionSpec("benchmark", compute_portfolio_vs_benchmarks, lambda statuses, result: AggregatePortfolioBenchmarkResponse(members=statuses, benchmark=result)),
    _SectionSpec("benchmark_funds", compute_fund_vs_benchmark, lambda statuses, result: AggregateFundVsBenchmarkResponse(members=statuses, comparison=result)),
    _SectionSpec("category_ranking", compute_category_ranking, lambda statuses, result: AggregateCategoryRankingResponse(members=statuses, ranking=result)),
    _SectionSpec("score", compute_portfolio_score, lambda statuses, result: AggregatePortfolioScoreResponse(members=statuses, score=result)),
]


def should_dispatch_recompute(db: Session, user_id: uuid.UUID) -> bool:
    """True if no recompute is currently in flight for this household, or
    the recorded one is old enough to be a crashed/killed run rather than
    one still working -- recompute_household_analytics's own try/finally
    clears started_at on every normal exit, so a flag this old means the
    process that set it is gone."""
    status = db.get(AnalyticsRecomputeStatus, user_id)
    if status is None or status.started_at is None:
        return True
    return datetime.now(timezone.utc) - status.started_at > _STALE_RECOMPUTE_CEILING


def _upsert_section(
    db: Session, user_id: uuid.UUID, scope_key: str, household_member_id: uuid.UUID | None,
    section_name: str, payload: BaseModel,
) -> None:
    values = {
        "user_id": user_id,
        "scope_key": scope_key,
        "section": section_name,
        "household_member_id": household_member_id,
        "payload": payload.model_dump(mode="json"),
        "computed_at": datetime.now(timezone.utc),
        "failed_at": None,
    }
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "sqlite":
        insert_fn = sqlite_insert
    elif dialect_name == "postgresql":
        insert_fn = postgresql_insert
    else:
        raise RuntimeError(f"Unsupported database dialect for analytics_sections upsert: {dialect_name}")

    statement = insert_fn(AnalyticsSection).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=[AnalyticsSection.user_id, AnalyticsSection.scope_key, AnalyticsSection.section],
        set_={"payload": statement.excluded.payload, "computed_at": statement.excluded.computed_at, "failed_at": None},
    )
    db.execute(statement)


def _mark_section_failed(db: Session, user_id: uuid.UUID, scope_key: str, section_name: str) -> None:
    existing = db.get(AnalyticsSection, (user_id, scope_key, section_name))
    if existing is None:
        # No prior success to preserve -- leave no row, matching the
        # frontend's "no row yet" cold-start state rather than inventing a
        # placeholder payload for a section that has never once succeeded.
        return
    existing.failed_at = datetime.now(timezone.utc)


async def recompute_household_analytics(db: Session, user_id: uuid.UUID) -> None:
    status = db.get(AnalyticsRecomputeStatus, user_id)
    if status is None:
        status = AnalyticsRecomputeStatus(user_id=user_id, started_at=datetime.now(timezone.utc))
        db.add(status)
    else:
        status.started_at = datetime.now(timezone.utc)
    await commit_off_loop(db)

    try:
        members = list_household_members(db, user_id)
        statuses = get_member_statuses(db, user_id)
        all_member_ids = [m.id for m in members]

        scopes: list[tuple[str, uuid.UUID | None, list[uuid.UUID]]] = [("combined", None, all_member_ids)]
        scopes += [(str(m.id), m.id, [m.id]) for m in members]

        for scope_key, household_member_id, scoped_member_ids in scopes:
            for section in _SECTIONS:
                try:
                    result = await section.compute(db, scoped_member_ids)
                    payload = section.wrap_combined(statuses, result) if scope_key == "combined" else result
                except Exception:
                    logger.exception(
                        "recompute_household_analytics: section=%s failed for user=%s scope=%s",
                        section.name, user_id, scope_key,
                    )
                    _mark_section_failed(db, user_id, scope_key, section.name)
                    await commit_off_loop(db)
                    continue

                _upsert_section(db, user_id, scope_key, household_member_id, section.name, payload)
                await commit_off_loop(db)
    finally:
        status.started_at = None
        await commit_off_loop(db)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/services/analytics/test_recompute.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/analytics/recompute.py backend/tests/services/analytics/test_recompute.py
git commit -m "feat: add recompute_household_analytics orchestration layer"
```

---

### Task 4: `RecomputeDispatcher` (ECS Fargate RunTask)

**Files:**
- Create: `backend/app/services/analytics/dispatch.py`
- Modify: `backend/app/config.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/services/analytics/test_dispatch.py`

**Interfaces:**
- Produces: `dispatcher: RecomputeDispatcher` (module-level singleton,
  `app.services.analytics.dispatch`), where `RecomputeDispatcher` is a
  `Protocol` with `def dispatch(self, user_id: uuid.UUID) -> None`. Imported
  by Task 6, Task 7, Task 8.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/analytics/test_dispatch.py
import uuid
from unittest.mock import MagicMock, patch

from app.services.analytics.dispatch import EcsRunTaskDispatcher


def test_dispatch_is_a_noop_when_ecs_not_configured():
    dispatcher = EcsRunTaskDispatcher()
    with patch("app.services.analytics.dispatch.settings") as mock_settings, \
         patch("app.services.analytics.dispatch.boto3.client") as mock_client:
        mock_settings.ecs_cluster_arn = ""
        mock_settings.ecs_task_definition_arn = ""
        dispatcher.dispatch(uuid.uuid4())
    mock_client.assert_not_called()


def test_dispatch_calls_ecs_run_task_when_configured():
    dispatcher = EcsRunTaskDispatcher()
    user_id = uuid.uuid4()
    mock_ecs = MagicMock()

    with patch("app.services.analytics.dispatch.settings") as mock_settings, \
         patch("app.services.analytics.dispatch.boto3.client", return_value=mock_ecs) as mock_client:
        mock_settings.ecs_cluster_arn = "arn:aws:ecs:ap-south-1:123:cluster/unifolio"
        mock_settings.ecs_task_definition_arn = "arn:aws:ecs:ap-south-1:123:task-definition/analytics-recompute"
        mock_settings.ecs_container_name = "analytics-recompute"
        mock_settings.ecs_subnet_ids = "subnet-1,subnet-2"
        mock_settings.ecs_security_group_ids = "sg-1"
        mock_settings.aws_region = "ap-south-1"

        dispatcher.dispatch(user_id)

    mock_client.assert_called_once_with("ecs", region_name="ap-south-1")
    mock_ecs.run_task.assert_called_once()
    call_kwargs = mock_ecs.run_task.call_args.kwargs
    assert call_kwargs["cluster"] == "arn:aws:ecs:ap-south-1:123:cluster/unifolio"
    assert call_kwargs["taskDefinition"] == "arn:aws:ecs:ap-south-1:123:task-definition/analytics-recompute"
    command = call_kwargs["overrides"]["containerOverrides"][0]["command"]
    assert str(user_id) in command
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/services/analytics/test_dispatch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.analytics.dispatch'`

- [ ] **Step 3: Add settings and the `boto3` dependency**

```python
# backend/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./unifolio_dev.db"
    test_database_url: str | None = None
    otp_delivery_mode: str = "stub"
    frontend_base_url: str = "http://localhost:5173"
    google_oauth_client_id: str = ""

    # ECS Fargate RunTask invocation for the analytics recompute dispatcher
    # (see Docs/superpowers/specs/2026-09-02-analytics-precompute-architecture-design.md).
    # Empty defaults are deliberate: the exact ARNs are being finalized in a
    # parallel AWS-migration session as of 2026-09-02. EcsRunTaskDispatcher
    # degrades to a logged no-op when any required value is unset.
    aws_region: str = ""
    ecs_cluster_arn: str = ""
    ecs_task_definition_arn: str = ""
    ecs_container_name: str = ""
    ecs_subnet_ids: str = ""  # comma-separated subnet ids
    ecs_security_group_ids: str = ""  # comma-separated security group ids


settings = Settings()
```

Add `boto3>=1.35.0` to `backend/requirements.txt` (alphabetically, after
`bcrypt<4.1.0`), then run `cd backend && .venv/bin/pip install -r requirements.txt`.

- [ ] **Step 4: Write `dispatch.py`**

```python
# backend/app/services/analytics/dispatch.py
"""Dispatches a household's analytics recompute as a short-lived ECS
Fargate RunTask, never inline on a request-serving replica (see this plan's
Global Constraints and Docs/superpowers/specs/2026-09-02-analytics-precompute-architecture-design.md).

The exact RunTask invocation contract (cluster/task-definition ARNs,
container name, subnet/security-group ids) is being finalized in a parallel
AWS-migration session as of 2026-09-02 -- built against config settings with
empty defaults rather than concrete ARNs, so this code lands and is testable
before that session's values exist. `dispatch` degrades to a logged no-op
when unconfigured."""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

import boto3

from app.config import settings

logger = logging.getLogger(__name__)


class RecomputeDispatcher(Protocol):
    def dispatch(self, user_id: uuid.UUID) -> None: ...


class EcsRunTaskDispatcher:
    def dispatch(self, user_id: uuid.UUID) -> None:
        if not settings.ecs_cluster_arn or not settings.ecs_task_definition_arn:
            logger.info(
                "EcsRunTaskDispatcher: ECS not configured, skipping recompute dispatch "
                "for user %s (set ecs_cluster_arn/ecs_task_definition_arn to enable)",
                user_id,
            )
            return

        client = boto3.client("ecs", region_name=settings.aws_region or None)
        client.run_task(
            cluster=settings.ecs_cluster_arn,
            taskDefinition=settings.ecs_task_definition_arn,
            launchType="FARGATE",
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": [s for s in settings.ecs_subnet_ids.split(",") if s],
                    "securityGroups": [g for g in settings.ecs_security_group_ids.split(",") if g],
                    "assignPublicIp": "DISABLED",
                }
            },
            overrides={
                "containerOverrides": [
                    {
                        "name": settings.ecs_container_name,
                        "command": ["python", "scripts/run_analytics_recompute.py", "--household", str(user_id)],
                    }
                ]
            },
        )
        logger.info("EcsRunTaskDispatcher: dispatched recompute RunTask for user %s", user_id)


dispatcher: RecomputeDispatcher = EcsRunTaskDispatcher()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/services/analytics/test_dispatch.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/analytics/dispatch.py backend/app/config.py backend/requirements.txt backend/tests/services/analytics/test_dispatch.py
git commit -m "feat: add EcsRunTaskDispatcher for analytics recompute"
```

---

### Task 5: `scripts/run_analytics_recompute.py` entrypoint

**Files:**
- Create: `backend/scripts/run_analytics_recompute.py`
- Test: `backend/tests/scripts/test_run_analytics_recompute.py`

**Interfaces:**
- Consumes: `recompute_household_analytics(db, user_id)` (Task 3),
  `SessionLocal` (`app.db.session`), `User` (`app.models.user`).
- Produces: a CLI runnable as
  `python scripts/run_analytics_recompute.py --household <uuid>` (single
  household — the argument passed by `EcsRunTaskDispatcher`'s
  `containerOverrides` command) or `--all` (daily backstop — loops every
  user with a household member in one process run, so `nav.py`'s in-process
  HTTP fetch dedup and freshly warmed `nav_history` rows benefit every
  household in the run, not just the first).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/scripts/test_run_analytics_recompute.py
import uuid
from unittest.mock import AsyncMock, patch

import pytest


def test_run_one_calls_recompute_with_the_given_user_id():
    from scripts.run_analytics_recompute import _run_one

    user_id = uuid.uuid4()
    fake_db = object()

    with patch("scripts.run_analytics_recompute.SessionLocal", return_value=fake_db), \
         patch("scripts.run_analytics_recompute.recompute_household_analytics", new=AsyncMock()) as mock_recompute:
        import asyncio
        asyncio.run(_run_one(user_id))

    mock_recompute.assert_awaited_once_with(fake_db, user_id)


def test_run_all_recomputes_every_user_and_keeps_going_after_one_failure():
    from scripts.run_analytics_recompute import _run_all

    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    class _FakeQuery:
        def all(self):
            return [(user_a,), (user_b,)]

    class _FakeDb:
        def query(self, *_args):
            return _FakeQuery()

        def close(self):
            pass

    recompute_calls = []

    async def _fake_run_one(user_id):
        recompute_calls.append(user_id)
        if user_id == user_a:
            raise RuntimeError("boom")

    with patch("scripts.run_analytics_recompute.SessionLocal", return_value=_FakeDb()), \
         patch("scripts.run_analytics_recompute._run_one", new=_fake_run_one):
        import asyncio
        asyncio.run(_run_all())

    assert recompute_calls == [user_a, user_b]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/scripts/test_run_analytics_recompute.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.run_analytics_recompute'`
(create `backend/tests/scripts/__init__.py` empty if the `scripts` package
needs an `__init__.py` for pytest's import mode — check `backend/scripts/`
for an existing one first and mirror it.)

- [ ] **Step 3: Write the script**

```python
# backend/scripts/run_analytics_recompute.py
"""Entrypoint for the ECS Fargate RunTask that runs analytics recompute
out-of-process (Docs/superpowers/specs/2026-09-02-analytics-precompute-architecture-design.md).

Two modes:
  --household <uuid>  One event-triggered recompute (CAS import, retry) --
                       the exact argument EcsRunTaskDispatcher passes.
  --all                Daily EventBridge backstop: loops every user with a
                       household member in this one process run, so nav.py's
                       in-process NAV HTTP-fetch dedup and freshly warmed
                       nav_history rows benefit every household in the run,
                       not just the first.

Run from backend/: .venv/bin/python scripts/run_analytics_recompute.py --household <uuid>
                    .venv/bin/python scripts/run_analytics_recompute.py --all
"""
import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.user import User
from app.services.analytics.recompute import recompute_household_analytics

logger = logging.getLogger(__name__)


async def _run_one(user_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        await recompute_household_analytics(db, user_id)
    finally:
        db.close()


async def _run_all() -> None:
    db = SessionLocal()
    try:
        user_ids = [row[0] for row in db.query(User.id).all()]
    finally:
        db.close()

    for user_id in user_ids:
        try:
            await _run_one(user_id)
        except Exception:
            logger.exception("run_analytics_recompute: recompute failed for user %s", user_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--household", type=uuid.UUID, help="Recompute one household (user id).")
    group.add_argument("--all", action="store_true", help="Recompute every household, one process run.")
    args = parser.parse_args()

    if args.all:
        asyncio.run(_run_all())
    else:
        asyncio.run(_run_one(args.household))


if __name__ == "__main__":
    main()
```

Note: `_run_all` deliberately does not call `should_dispatch_recompute` —
it's the daily backstop's own authoritative sequential run, not a second
concurrent trigger to guard against, and `recompute_household_analytics`
already unconditionally overwrites/clears any leftover stale `started_at`
for each household it visits (a day is far past the 2-hour staleness
ceiling by construction). This satisfies the spec's "daily job clears a
stale started_at before starting a fresh run" requirement without extra code.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/scripts/test_run_analytics_recompute.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/run_analytics_recompute.py backend/tests/scripts/test_run_analytics_recompute.py
git commit -m "feat: add run_analytics_recompute.py RunTask entrypoint"
```

---

### Task 6: Wire the CAS-import trigger

**Files:**
- Modify: `backend/app/api/imports.py`
- Modify: `backend/tests/api/test_imports_routes.py`

**Interfaces:**
- Consumes: `should_dispatch_recompute(db, user_id)` (Task 3),
  `dispatcher` (Task 4).

- [ ] **Step 1: Update the existing test to expect the new dispatch call**

In `backend/tests/api/test_imports_routes.py`, modify
`test_confirm_route_schedules_nav_prefetch_after_successful_confirm`:

```python
def test_confirm_route_schedules_nav_prefetch_after_successful_confirm():
    from app.api.imports import confirm_import_route
    from app.services.import_.schemas import ImportConfirmRequest, ImportConfirmResponse

    member_id = uuid.uuid4()
    body = ImportConfirmRequest(
        session_id="session-1",
        household_member_id=str(member_id),
        scheme_confirmations=[],
    )
    background_tasks = BackgroundTasks()
    user = MagicMock(id=uuid.uuid4())
    request_db = MagicMock()
    response = ImportConfirmResponse(added=1, skipped=0, import_id=str(uuid.uuid4()))

    with (
        patch("app.api.imports.get_household_member_for_user", return_value=MagicMock()),
        patch("app.api.imports.confirm_import", return_value=response),
        patch("app.api.imports.should_dispatch_recompute", return_value=True),
    ):
        result = confirm_import_route(body, background_tasks, user, request_db)

    assert result == response
    assert len(background_tasks.tasks) == 2
    prefetch_task, dispatch_task = background_tasks.tasks
    assert prefetch_task.func.__name__ == "_prefetch_member_nav_history"
    assert prefetch_task.args == (member_id,)
    assert dispatch_task.args == (user.id,)


def test_confirm_route_does_not_dispatch_recompute_when_one_already_in_flight():
    from app.api.imports import confirm_import_route
    from app.services.import_.schemas import ImportConfirmRequest, ImportConfirmResponse

    member_id = uuid.uuid4()
    body = ImportConfirmRequest(
        session_id="session-1",
        household_member_id=str(member_id),
        scheme_confirmations=[],
    )
    background_tasks = BackgroundTasks()
    user = MagicMock(id=uuid.uuid4())
    request_db = MagicMock()
    response = ImportConfirmResponse(added=1, skipped=0, import_id=str(uuid.uuid4()))

    with (
        patch("app.api.imports.get_household_member_for_user", return_value=MagicMock()),
        patch("app.api.imports.confirm_import", return_value=response),
        patch("app.api.imports.should_dispatch_recompute", return_value=False),
    ):
        confirm_import_route(body, background_tasks, user, request_db)

    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func.__name__ == "_prefetch_member_nav_history"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_imports_routes.py -v -k confirm_route_schedules`
Expected: FAIL — `assert 1 == 2` (only the prefetch task is scheduled today)

- [ ] **Step 3: Wire the dispatch call**

```python
# backend/app/api/imports.py — add imports
from app.services.analytics.dispatch import dispatcher
from app.services.analytics.recompute import should_dispatch_recompute
```

```python
# backend/app/api/imports.py — confirm_import_route body
    try:
        response = confirm_import(db, body.session_id, household_member_id, body.scheme_confirmations)
        background_tasks.add_task(_prefetch_member_nav_history, household_member_id)
        if should_dispatch_recompute(db, user.id):
            background_tasks.add_task(dispatcher.dispatch, user.id)
        return response
    except SchemeConfidenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_imports_routes.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/imports.py backend/tests/api/test_imports_routes.py
git commit -m "feat: dispatch analytics recompute after a confirmed CAS import"
```

---

### Task 7: Consolidated `GET /analytics/{scope}` read endpoint

**Files:**
- Modify: `backend/app/api/analytics.py`
- Modify: `backend/app/services/analytics/schemas.py`
- Test: `backend/tests/api/test_analytics_route.py` (new)

**Interfaces:**
- Consumes: `AnalyticsSection`, `AnalyticsRecomputeStatus` (Task 1);
  `should_dispatch_recompute`, `dispatcher` (Tasks 3, 4);
  `get_household_member_for_user` (existing).
- Produces: `AnalyticsSectionState`, `AnalyticsScopeResponse` (new Pydantic
  models in `schemas.py`) and `GET /analytics/{scope}`.

- [ ] **Step 1: Add the response schema**

```python
# backend/app/services/analytics/schemas.py — append at the end
from datetime import datetime


class AnalyticsSectionState(BaseModel):
    payload: dict | None
    computed_at: datetime | None
    failed_at: datetime | None


class AnalyticsScopeResponse(BaseModel):
    scope: str
    recomputing: bool
    sections: dict[str, AnalyticsSectionState]
```

(Move the `from datetime import date` import already at the top of the file
to `from datetime import date, datetime` instead of re-importing at the
bottom — keep all imports at the top of the file per the file's existing
style.)

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/api/test_analytics_route.py
from datetime import datetime, timezone
from unittest.mock import patch

import pytest


def _authed_headers_and_member(client, phone: str):
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    member = client.post("/household-members", json={"name": "Self", "relationship": "self"}, headers=headers).json()
    return headers, member["id"]


def test_analytics_scope_route_requires_auth(client):
    response = client.get("/analytics/combined")
    assert response.status_code == 401


def test_analytics_scope_route_404_for_unknown_member(client):
    headers, _ = _authed_headers_and_member(client, "+919000000030")
    response = client.get(
        "/analytics/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert response.status_code == 404


def test_analytics_scope_route_400_for_malformed_scope(client):
    headers, _ = _authed_headers_and_member(client, "+919000000031")
    response = client.get("/analytics/not-a-uuid-and-not-combined", headers=headers)
    assert response.status_code == 400


def test_analytics_scope_route_zero_rows_dispatches_and_returns_empty_response(client):
    headers, _ = _authed_headers_and_member(client, "+919000000032")
    with patch("app.api.analytics.dispatcher.dispatch") as mock_dispatch:
        response = client.get("/analytics/combined", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["sections"] == {}
    assert body["recomputing"] is True
    mock_dispatch.assert_called_once()


def test_analytics_scope_route_returns_stored_rows_with_no_live_compute(client, db_session):
    headers, member_id = _authed_headers_and_member(client, "+919000000033")

    from app.models.analytics import AnalyticsSection
    from app.models.user import User

    user = db_session.query(User).filter_by(phone_number="+919000000033").first()
    db_session.add(AnalyticsSection(
        user_id=user.id, scope_key=member_id, section="allocation", household_member_id=member_id,
        payload={"by_category": [], "by_amc": [], "total_value": "42.00"},
        computed_at=datetime.now(timezone.utc), failed_at=None,
    ))
    db_session.commit()

    with patch("app.api.analytics.compute_category_allocation") as mock_compute:
        response = client.get(f"/analytics/{member_id}", headers=headers)

    mock_compute.assert_not_called()
    assert response.status_code == 200
    body = response.json()
    assert body["sections"]["allocation"]["payload"]["total_value"] == "42.00"
    assert body["recomputing"] is False


def test_analytics_scope_route_surfaces_a_failed_section(client, db_session):
    headers, member_id = _authed_headers_and_member(client, "+919000000034")

    from app.models.analytics import AnalyticsSection
    from app.models.user import User

    user = db_session.query(User).filter_by(phone_number="+919000000034").first()
    db_session.add(AnalyticsSection(
        user_id=user.id, scope_key=member_id, section="score", household_member_id=member_id,
        payload={"funds": [], "weighted_score": "10", "covered_value": "0", "total_value": "0", "uncovered_schemes": []},
        computed_at=datetime.now(timezone.utc), failed_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    response = client.get(f"/analytics/{member_id}", headers=headers)
    body = response.json()
    assert body["sections"]["score"]["failed_at"] is not None
```

Note: `db_session` and `client` are two independent in-memory SQLite
engines per `conftest.py` — `db_session` won't see rows the `client`'s
requests create via its own override, but a test that seeds via `db_session`
and reads via `client` still works here IF (and only if) both fixtures are
patched to share one engine, which they are not today. This plan therefore
seeds through the same `client`-backed session instead where a route test
needs pre-existing rows: replace `db_session` usage above with a direct
insert via `app.db.session.SessionLocal` is wrong too (a third, unrelated
engine). The correct approach, matching this codebase's existing convention
for API tests needing DB setup beyond what routes expose (see
`tests/api/test_imports_routes.py`'s `test_parse_then_confirm_lands_a_transaction_in_the_real_db`),
is to seed by monkeypatching `app.db.session.get_db`'s override directly.
Fix the two seeding tests to route through the app's own overridden session:

```python
def _seed_section(client, user_id, scope_key, section, payload, *, failed=False):
    from app.db.session import get_db
    from app.main import app
    from app.models.analytics import AnalyticsSection

    override = app.dependency_overrides[get_db]
    db = next(override())
    db.add(AnalyticsSection(
        user_id=user_id, scope_key=scope_key, section=section,
        household_member_id=None if scope_key == "combined" else user_id,
        payload=payload, computed_at=datetime.now(timezone.utc),
        failed_at=datetime.now(timezone.utc) if failed else None,
    ))
    db.commit()
    db.close()
```

Replace the two `db_session`-seeded tests above to call `_seed_section`
instead, dropping the `db_session` fixture parameter, and look up `user.id`
via a lightweight authenticated `/me`-style call already available in this
codebase's auth flow, or simply capture it from the OTP-verify response if
it's already returned there — check `app/api/auth.py`'s verify response
shape before finalizing this test's exact `user_id` lookup, since it wasn't
directly confirmed in this plan's research.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_analytics_route.py -v`
Expected: FAIL — route doesn't exist yet (404 instead of expected codes)

- [ ] **Step 4: Replace the 14 old routes with the consolidated route**

In `backend/app/api/analytics.py`, delete all 14 `@router.get("/household-members/{member_id}/...")`
and `@router.get("/household/aggregate/...")` route functions (everything
from `get_member_category_allocation` through
`get_household_aggregate_portfolio_score`, i.e. lines 69-210 in the current
file) and their now-unused imports (`compute_category_allocation`,
`get_aggregate_category_allocation`, `compute_portfolio_vs_benchmarks`,
`get_aggregate_portfolio_vs_benchmarks`, `compute_category_ranking`,
`get_aggregate_category_ranking`, `compute_direct_regular_ter_comparison`,
`compute_weighted_ter`, `get_aggregate_direct_regular_ter_comparison`,
`get_aggregate_weighted_ter`, `compute_portfolio_score`,
`get_aggregate_portfolio_score`, and the now-unused response schema imports
`AggregateAnalyticsAllocationResponse`, `AggregateCategoryRankingResponse`,
`AggregateDirectRegularTerResponse`, `AggregatePortfolioBenchmarkResponse`,
`AggregatePortfolioScoreResponse`, `AggregateWeightedTerResponse`,
`AnalyticsAllocationSummary`, `CategoryRankingSummary`,
`DirectRegularTerComparison`, `PortfolioBenchmarkSummary`,
`PortfolioScoreSummary`, `WeightedTerSummary`). Keep
`compute_fund_vs_benchmark`'s import only if `/funds/.../score` doesn't need
it — it doesn't; also remove it. Keep `AggregateFundVsBenchmarkResponse`,
`FundVsBenchmarkSummary` only if still referenced — they are not, remove
them too. Keep `compute_fund_score`, `FundScoreRow` (the surviving
`/funds/{scheme_id}/score` route still uses them), and keep all
`export`/`pdf` imports untouched.

Add the new imports and route:

```python
from app.models.analytics import AnalyticsRecomputeStatus, AnalyticsSection
from app.services.analytics.dispatch import dispatcher
from app.services.analytics.recompute import should_dispatch_recompute
from app.services.analytics.schemas import AnalyticsScopeResponse, AnalyticsSectionState
```

```python
@router.get("/{scope}", response_model=AnalyticsScopeResponse)
def get_analytics_scope(
    scope: str,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if scope != "combined":
        try:
            member_uuid = uuid.UUID(scope)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail='scope must be "combined" or a household member id.'
            ) from exc
        if get_household_member_for_user(db, user.id, member_uuid) is None:
            raise HTTPException(status_code=404, detail="Household member not found.")

    rows = (
        db.query(AnalyticsSection)
        .filter(AnalyticsSection.user_id == user.id, AnalyticsSection.scope_key == scope)
        .all()
    )
    sections = {
        row.section: AnalyticsSectionState(payload=row.payload, computed_at=row.computed_at, failed_at=row.failed_at)
        for row in rows
    }

    status = db.get(AnalyticsRecomputeStatus, user.id)
    recomputing = status is not None and status.started_at is not None

    if not rows and not recomputing:
        if should_dispatch_recompute(db, user.id):
            dispatcher.dispatch(user.id)
        recomputing = True

    return AnalyticsScopeResponse(scope=scope, recomputing=recomputing, sections=sections)
```

Note this route is a plain sync `def`, not `async def` — deliberately,
matching `confirm_import_route`'s existing convention: `dispatcher.dispatch`
makes a blocking `boto3` network call (the `run_task` call in `dispatch.py`),
and FastAPI runs sync `def` routes in Starlette's own threadpool, so that
blocking call never freezes the single-worker event loop the way it would if
this were `async def` and called synchronously from within it.

Place `@router.get("/{scope}", ...)` after the existing `/funds/{scheme_id}/score`
route (which has 2 path segments and so never collides with this
single-segment `{scope}` route), and before `/export/pdf`/`/export/payload/{token}`
purely for readability — FastAPI's path matching by segment count means
registration order doesn't affect correctness here.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_analytics_route.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/analytics.py backend/app/services/analytics/schemas.py backend/tests/api/test_analytics_route.py
git commit -m "feat: replace 14 per-section analytics routes with GET /analytics/{scope}"
```

---

### Task 8: `POST /analytics/{scope}/retry`

**Files:**
- Modify: `backend/app/api/analytics.py`
- Modify: `backend/app/services/analytics/schemas.py`
- Test: `backend/tests/api/test_analytics_route.py`

**Interfaces:**
- Produces: `AnalyticsRetryResponse` (schema), `POST /analytics/{scope}/retry`.

- [ ] **Step 1: Add the response schema**

```python
# backend/app/services/analytics/schemas.py — append after AnalyticsScopeResponse
class AnalyticsRetryResponse(BaseModel):
    dispatched: bool
```

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/api/test_analytics_route.py — append
def test_analytics_retry_route_requires_auth(client):
    response = client.post("/analytics/combined/retry")
    assert response.status_code == 401


def test_analytics_retry_route_404_for_unknown_member(client):
    headers, _ = _authed_headers_and_member(client, "+919000000035")
    response = client.post(
        "/analytics/00000000-0000-0000-0000-000000000000/retry", headers=headers
    )
    assert response.status_code == 404


def test_analytics_retry_route_dispatches_when_nothing_in_flight(client):
    headers, _ = _authed_headers_and_member(client, "+919000000036")
    with patch("app.api.analytics.dispatcher.dispatch") as mock_dispatch:
        response = client.post("/analytics/combined/retry", headers=headers)
    assert response.status_code == 200
    assert response.json()["dispatched"] is True
    mock_dispatch.assert_called_once()


def test_analytics_retry_route_is_a_noop_while_one_is_already_in_flight(client):
    headers, _ = _authed_headers_and_member(client, "+919000000037")
    with (
        patch("app.api.analytics.should_dispatch_recompute", return_value=False),
        patch("app.api.analytics.dispatcher.dispatch") as mock_dispatch,
    ):
        response = client.post("/analytics/combined/retry", headers=headers)
    assert response.status_code == 200
    assert response.json()["dispatched"] is False
    mock_dispatch.assert_not_called()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/api/test_analytics_route.py -v -k retry`
Expected: FAIL — route doesn't exist (404 for all)

- [ ] **Step 4: Add the route**

```python
# backend/app/api/analytics.py
from app.services.analytics.schemas import AnalyticsRetryResponse  # add to existing schemas import


@router.post("/{scope}/retry", response_model=AnalyticsRetryResponse)
def retry_analytics_scope(
    scope: str,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if scope != "combined":
        try:
            member_uuid = uuid.UUID(scope)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail='scope must be "combined" or a household member id.'
            ) from exc
        if get_household_member_for_user(db, user.id, member_uuid) is None:
            raise HTTPException(status_code=404, detail="Household member not found.")

    dispatched = should_dispatch_recompute(db, user.id)
    if dispatched:
        dispatcher.dispatch(user.id)
    return AnalyticsRetryResponse(dispatched=dispatched)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/api/test_analytics_route.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/analytics.py backend/app/services/analytics/schemas.py backend/tests/api/test_analytics_route.py
git commit -m "feat: add POST /analytics/{scope}/retry"
```

---

### Task 9: Delete superseded route tests, verify no dangling references

**Files:**
- Delete: `backend/tests/api/test_analytics_allocation_route.py`
- Delete: `backend/tests/api/test_analytics_benchmark_route.py`
- Delete: `backend/tests/api/test_analytics_category_ranking_route.py`
- Delete: `backend/tests/api/test_analytics_ter_route.py`
- Modify: `backend/tests/api/test_analytics_scorer_route.py`

`test_analytics_export_route.py` is untouched — `/export/pdf` and
`/export/payload/{token}` are unaffected by this plan.

`test_analytics_scorer_route.py` needs a partial edit, not deletion: it has
3 tests, 2 of which (`test_get_fund_score_404_when_scheme_not_found`,
`test_get_fund_score_returns_row_for_existing_scheme`) cover the
`/funds/{scheme_id}/score` route, which is NOT being removed (it's
fund-scoped, outside the 5-scope grid). Only its third test,
`test_get_member_score_404_when_member_not_found`, covers a route this plan
removes.

- [ ] **Step 1: Delete the 4 fully-superseded test files**

```bash
git rm backend/tests/api/test_analytics_allocation_route.py \
       backend/tests/api/test_analytics_benchmark_route.py \
       backend/tests/api/test_analytics_category_ranking_route.py \
       backend/tests/api/test_analytics_ter_route.py
```

- [ ] **Step 2: Remove only the superseded test from `test_analytics_scorer_route.py`**

Delete this function (lines 59-69 of the current file) from
`backend/tests/api/test_analytics_scorer_route.py`, leaving the two
fund-score tests and their imports/helpers untouched:

```python
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

- [ ] **Step 3: Grep for any remaining references to the removed routes/functions**

Run:
```bash
cd backend && grep -rn "household-members/{member_id}/allocation\|household-members/{member_id}/ter\|household-members/{member_id}/benchmark\|household-members/{member_id}/category-ranking\|household-members/{member_id}/score\|household/aggregate/allocation\|household/aggregate/ter\|household/aggregate/benchmark\|household/aggregate/category-ranking\|household/aggregate/score" --include="*.py" .
```
Expected: no output (all matches were in the deleted/edited test files and
the now-rewritten `app/api/analytics.py`).

- [ ] **Step 4: Run the full backend test suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS, with the total test count reduced by exactly the number of
deleted/removed tests and increased by the new ones added in Tasks 1-8.

- [ ] **Step 5: Commit**

```bash
git add -A backend/tests/api/
git commit -m "test: remove tests for the 14 superseded per-section analytics routes"
```

---

## Necessary follow-up (explicitly out of scope for this plan)

Once this plan lands, the frontend's single integration point for the old
routes — `frontend/src/features/analytics/api.ts` and its callers across the
Analytics dashboard's cards — will be calling 14 routes that no longer
exist. This is a hard dependency, not an optional enhancement: removing the
old routes is what actually fixes the pool-exhaustion bug, so the frontend
follow-up should be scheduled immediately after this plan, sized as its own
bounded task, and should implement the per-card progressive-reveal /
dimmed-refresh-pill / inline-retry UX already approved and mocked in
`Docs/superpowers/specs/2026-08-27-analytics-loading-state-mockups.html`
(spec Decision 5) against the new `GET /analytics/{scope}` and
`POST /analytics/{scope}/retry` endpoints this plan built.
