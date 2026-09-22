# Analytics Dashboard PDF Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user download the currently-active Analytics Dashboard scope
(aggregate or a single member) as a branded, print-quality PDF, with every held
fund's full Score Detail rendered inline, using data the dashboard already has
loaded — no re-fetch, no recompute, no new session-auth mechanism.

**Architecture:** The already-loaded `AnalyticsView` POSTs its in-memory data to a
new backend endpoint, which stores it behind a one-time capability token, drives a
warm headless Chromium (Playwright) to a new `/print/analytics?token=...` frontend
route that fetches that one stored blob and renders a bespoke report layout, then
streams the resulting PDF bytes back as the original POST's response.

**Tech Stack:** FastAPI (Python), Playwright (Python, headless Chromium), React +
TypeScript (frontend), existing Tailwind design tokens.

**Spec:** `Docs/superpowers/specs/2026-08-20-analytics-pdf-export-design.md`

## Global Constraints

- Decimal-safe fields (all `string`-typed money/percentage/score fields already
  coming from the backend) must be passed through byte-for-byte, never parsed to
  `float` and reformatted, in both the export payload and the print render.
- No new DB table, no Alembic migration — the capability-token store is an
  in-process dict (per the approved spec's rejection of a `sessions`-mirroring
  design).
- The print route must not call any `get_current_user`-protected analytics endpoint.
- `# ponytail:` comment required on the in-process token-store dict noting it does
  not survive a process restart and does not work across multiple backend worker
  processes — acceptable now since this repo has no multi-process deployment yet
  (single Uvicorn process, per current `main.py`/Migration Plan state).

---

### Task 1: Capability-token payload store

**Files:**
- Create: `backend/app/services/analytics/pdf_export.py`
- Test: `backend/tests/services/analytics/test_pdf_export.py`

**Interfaces:**
- Produces: `store_export_payload(payload: dict[str, Any]) -> str`,
  `consume_export_payload(token: str) -> dict[str, Any] | None`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/services/analytics/test_pdf_export.py
import time

from app.services.analytics.pdf_export import (
    _export_payloads,
    consume_export_payload,
    store_export_payload,
)


def test_store_then_consume_returns_payload_once():
    _export_payloads.clear()
    token = store_export_payload({"scope": "aggregate"})
    assert consume_export_payload(token) == {"scope": "aggregate"}
    assert consume_export_payload(token) is None


def test_consume_unknown_token_returns_none():
    _export_payloads.clear()
    assert consume_export_payload("does-not-exist") is None


def test_consume_expired_token_returns_none(monkeypatch):
    _export_payloads.clear()
    token = store_export_payload({"scope": "aggregate"})
    # push the stored expiry into the past without waiting out the real TTL
    payload, _expires_at, used = _export_payloads[token]
    _export_payloads[token] = (payload, time.monotonic() - 1, used)
    assert consume_export_payload(token) is None
```

- [ ] **Step 2: Run tests, verify they fail**
  Run: `cd backend && pytest tests/services/analytics/test_pdf_export.py -v`
  Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.analytics.pdf_export'`

- [ ] **Step 3: Implement the store**

```python
# backend/app/services/analytics/pdf_export.py
import secrets
import time
from typing import Any

_TOKEN_TTL_SECONDS = 120

# ponytail: in-process dict, not shared across worker processes and lost on
# restart — fine for a single-Uvicorn-process deployment (current state);
# move to Redis/similar if/when this backend ever runs multiple workers.
_export_payloads: dict[str, tuple[dict[str, Any], float, bool]] = {}


def store_export_payload(payload: dict[str, Any]) -> str:
    token = secrets.token_urlsafe(32)
    _export_payloads[token] = (payload, time.monotonic() + _TOKEN_TTL_SECONDS, False)
    return token


def consume_export_payload(token: str) -> dict[str, Any] | None:
    entry = _export_payloads.pop(token, None)
    if entry is None:
        return None
    payload, expires_at, _used = entry
    if time.monotonic() > expires_at:
        return None
    return payload
```

- [ ] **Step 4: Run tests, verify they pass**
  Run: `cd backend && pytest tests/services/analytics/test_pdf_export.py -v`
  Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/analytics/pdf_export.py backend/tests/services/analytics/test_pdf_export.py
git commit -m "feat(analytics): add one-time capability-token payload store for PDF export"
```

---

### Task 2: `playwright` dependency + shared browser lifecycle

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/services/analytics/pdf_export.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/services/analytics/test_pdf_export.py` (append)

**Interfaces:**
- Consumes: nothing new
- Produces: `async def start_browser() -> None`, `async def stop_browser() -> None`,
  `def get_shared_browser() -> Browser` (raises `RuntimeError` if not started),
  used by Task 3 and by `main.py`'s lifespan hook.

- [ ] **Step 1: Add the dependency**

```
# backend/requirements.txt — append
playwright>=1.48.0
```

Run: `cd backend && pip install -r requirements.txt && playwright install chromium`

- [ ] **Step 2: Write failing test for lifecycle guard**

```python
# append to backend/tests/services/analytics/test_pdf_export.py
import pytest

from app.services.analytics.pdf_export import get_shared_browser


def test_get_shared_browser_raises_before_started():
    with pytest.raises(RuntimeError, match="not started"):
        get_shared_browser()
```

- [ ] **Step 3: Run test, verify it fails**
  Run: `cd backend && pytest tests/services/analytics/test_pdf_export.py::test_get_shared_browser_raises_before_started -v`
  Expected: FAIL with `ImportError: cannot import name 'get_shared_browser'`

- [ ] **Step 4: Implement browser lifecycle in `pdf_export.py`**

```python
# add to backend/app/services/analytics/pdf_export.py
from playwright.async_api import Browser, Playwright, async_playwright

_playwright: Playwright | None = None
_browser: Browser | None = None


async def start_browser() -> None:
    global _playwright, _browser
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch()


async def stop_browser() -> None:
    global _playwright, _browser
    if _browser is not None:
        await _browser.close()
        _browser = None
    if _playwright is not None:
        await _playwright.stop()
        _playwright = None


def get_shared_browser() -> Browser:
    if _browser is None:
        raise RuntimeError("Playwright browser not started")
    return _browser
```

- [ ] **Step 5: Run test, verify it passes**
  Run: `cd backend && pytest tests/services/analytics/test_pdf_export.py -v`
  Expected: PASS (4 tests)

- [ ] **Step 6: Wire the lifespan hook into `main.py`**

```python
# backend/app/main.py — replace the top of the file
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analytics, auth, cas_imports, dashboard, imports
from app.services.analytics.pdf_export import start_browser, stop_browser

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_browser()
    yield
    await stop_browser()


app = FastAPI(title="Unifolio API", lifespan=lifespan)
```

(Leave the rest of `main.py` — CORS middleware, router includes, `/health` — unchanged.)

- [ ] **Step 7: Verify the app still boots**
  Run: `cd backend && python -c "from app.main import app; print('ok')"`
  Expected: prints `ok` with no import errors

- [ ] **Step 8: Commit**

```bash
git add backend/requirements.txt backend/app/services/analytics/pdf_export.py backend/app/main.py backend/tests/services/analytics/test_pdf_export.py
git commit -m "feat(analytics): add Playwright dependency and shared-browser lifecycle"
```

---

### Task 3: `frontend_base_url` setting + PDF render function

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/analytics/pdf_export.py`
- Test: `backend/tests/services/analytics/test_pdf_export.py` (append)

**Interfaces:**
- Consumes: `get_shared_browser()` from Task 2, `settings.frontend_base_url`
- Produces: `async def render_analytics_pdf(token: str) -> bytes`, used by Task 4's route.

- [ ] **Step 1: Add the setting**

```python
# backend/app/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./unifolio_dev.db"
    test_database_url: str | None = None
    otp_delivery_mode: str = "stub"
    frontend_base_url: str = "http://localhost:5173"
```

- [ ] **Step 2: Write failing test (mocked browser, no real Chromium)**

```python
# append to backend/tests/services/analytics/test_pdf_export.py
from unittest.mock import AsyncMock, patch

from app.services.analytics import pdf_export


def test_render_analytics_pdf_navigates_and_returns_bytes():
    fake_page = AsyncMock()
    fake_page.pdf = AsyncMock(return_value=b"%PDF-1.4 fake bytes")
    fake_browser = AsyncMock()
    fake_browser.new_page = AsyncMock(return_value=fake_page)

    with patch.object(pdf_export, "get_shared_browser", return_value=fake_browser):
        import asyncio

        result = asyncio.run(pdf_export.render_analytics_pdf("tok-123"))

    assert result == b"%PDF-1.4 fake bytes"
    fake_page.goto.assert_awaited_once_with(
        "http://localhost:5173/print/analytics?token=tok-123"
    )
    fake_page.wait_for_selector.assert_awaited_once_with(
        '[data-print-ready="true"]', timeout=15000
    )
    fake_page.close.assert_awaited_once()
```

- [ ] **Step 3: Run test, verify it fails**
  Run: `cd backend && pytest tests/services/analytics/test_pdf_export.py::test_render_analytics_pdf_navigates_and_returns_bytes -v`
  Expected: FAIL with `AttributeError: module ... has no attribute 'render_analytics_pdf'`

- [ ] **Step 4: Implement `render_analytics_pdf`**

```python
# add to backend/app/services/analytics/pdf_export.py
from app.config import settings


async def render_analytics_pdf(token: str) -> bytes:
    browser = get_shared_browser()
    page = await browser.new_page()
    try:
        await page.goto(f"{settings.frontend_base_url}/print/analytics?token={token}")
        await page.wait_for_selector('[data-print-ready="true"]', timeout=15000)
        return await page.pdf(format="A4", print_background=True)
    finally:
        await page.close()
```

- [ ] **Step 5: Run test, verify it passes**
  Run: `cd backend && pytest tests/services/analytics/test_pdf_export.py -v`
  Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/services/analytics/pdf_export.py backend/tests/services/analytics/test_pdf_export.py
git commit -m "feat(analytics): add render_analytics_pdf using the shared Playwright browser"
```

---

### Task 4: Export routes — `POST /analytics/export/pdf` and `GET /analytics/export/payload`

**Files:**
- Modify: `backend/app/api/analytics.py`
- Test: `backend/tests/api/test_analytics_export_route.py` (new)

**Interfaces:**
- Consumes: `store_export_payload`, `consume_export_payload`, `render_analytics_pdf`
  from `app.services.analytics.pdf_export`; `get_household_member_for_user` (existing,
  same ownership-check pattern as every other route in this file).
- Produces: two routes other tasks don't call directly (the frontend calls them over
  HTTP in Tasks 6 and 8).

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/api/test_analytics_export_route.py
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


def _client():
    return TestClient(app)


def test_export_pdf_404_when_member_not_owned():
    from app.db.session import get_db
    from app.services.auth.session import get_current_user

    fake_db = type("DB", (), {"query": lambda self, *a: type(
        "Q", (), {"filter_by": lambda self, **kw: type("F", (), {"first": lambda self: None})()}
    )()})()
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": uuid.uuid4()})()
    app.dependency_overrides[get_db] = lambda: fake_db
    client = _client()
    try:
        response = client.post(
            "/analytics/export/pdf",
            json={"scope": "member", "member_id": str(uuid.uuid4()), "payload": {}},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_export_pdf_aggregate_scope_skips_member_ownership_check():
    from app.db.session import get_db
    from app.services.auth.session import get_current_user

    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": uuid.uuid4()})()
    app.dependency_overrides[get_db] = lambda: object()
    client = _client()
    try:
        with patch(
            "app.api.analytics.render_analytics_pdf",
            new=AsyncMock(return_value=b"%PDF-1.4 fake"),
        ):
            response = client.post(
                "/analytics/export/pdf",
                json={"scope": "aggregate", "member_id": None, "payload": {"allocation": {}}},
            )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content == b"%PDF-1.4 fake"
    finally:
        app.dependency_overrides.clear()


def test_get_export_payload_returns_stored_blob_once():
    from app.services.analytics.pdf_export import store_export_payload

    token = store_export_payload({"scope": "aggregate", "allocation": {"total_value": "100"}})
    client = _client()
    first = client.get(f"/analytics/export/payload/{token}")
    assert first.status_code == 200
    assert first.json() == {"scope": "aggregate", "allocation": {"total_value": "100"}}

    second = client.get(f"/analytics/export/payload/{token}")
    assert second.status_code == 404


def test_get_export_payload_404_for_unknown_token():
    client = _client()
    response = client.get("/analytics/export/payload/does-not-exist")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests, verify they fail**
  Run: `cd backend && pytest tests/api/test_analytics_export_route.py -v`
  Expected: FAIL with 404s from FastAPI's default "not found" for the not-yet-registered routes (or `AttributeError` if patch targets don't exist yet)

- [ ] **Step 3: Implement the routes**

```python
# add imports to backend/app/api/analytics.py
from fastapi import Response
from pydantic import BaseModel

from app.services.analytics.pdf_export import (
    consume_export_payload,
    render_analytics_pdf,
    store_export_payload,
)


class AnalyticsExportRequest(BaseModel):
    scope: str  # "aggregate" | "member"
    member_id: uuid.UUID | None
    payload: dict


# append routes at the end of the file
@router.post("/export/pdf")
async def export_analytics_pdf(
    body: AnalyticsExportRequest,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if body.scope == "member":
        if body.member_id is None or get_household_member_for_user(db, user.id, body.member_id) is None:
            raise HTTPException(status_code=404, detail="Household member not found.")

    token = store_export_payload(body.payload)
    pdf_bytes = await render_analytics_pdf(token)
    return Response(content=pdf_bytes, media_type="application/pdf")


@router.get("/export/payload/{token}")
async def get_export_payload(token: str):
    payload = consume_export_payload(token)
    if payload is None:
        raise HTTPException(status_code=404, detail="Export token not found or expired.")
    return payload
```

Note: `get_export_payload` deliberately has no `Depends(get_current_user)` — it's
gated by possession of the opaque token only, per the approved spec's "no new auth
system" decision (the token is a capability, not a session credential).

- [ ] **Step 4: Run tests, verify they pass**
  Run: `cd backend && pytest tests/api/test_analytics_export_route.py -v`
  Expected: PASS (4 tests)

- [ ] **Step 5: Run the full backend test suite to check for regressions**
  Run: `cd backend && pytest -v`
  Expected: PASS (all tests, including pre-existing ones)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/analytics.py backend/tests/api/test_analytics_export_route.py
git commit -m "feat(analytics): add export/pdf and export/payload routes"
```

---

### Task 5: Real-Playwright integration test (marked, opt-in)

**Files:**
- Modify: `backend/pytest.ini`
- Create: `backend/tests/services/analytics/test_pdf_export_integration.py`

**Interfaces:**
- Consumes: `start_browser`, `stop_browser`, `render_analytics_pdf`,
  `store_export_payload` from Task 1-3.

- [ ] **Step 1: Register a `playwright` marker (mirrors the existing `postgres` marker)**

```ini
# backend/pytest.ini
[pytest]
testpaths = tests
markers =
    postgres: requires a real Postgres connection (TEST_DATABASE_URL) — see functional_postgres/
    playwright: requires a real Chromium binary (playwright install chromium) and a running frontend dev server
```

- [ ] **Step 2: Write the integration test**

```python
# backend/tests/services/analytics/test_pdf_export_integration.py
import asyncio

import pytest

from app.services.analytics.pdf_export import (
    render_analytics_pdf,
    start_browser,
    stop_browser,
    store_export_payload,
)


@pytest.mark.playwright
def test_render_analytics_pdf_produces_real_pdf_bytes():
    """Requires `playwright install chromium` and the Vite dev server running
    at settings.frontend_base_url (see Task 8's /print/analytics route)."""

    async def run():
        await start_browser()
        try:
            token = store_export_payload(
                {
                    "scope": "aggregate",
                    "scopeName": "Test Household",
                    "allocation": None,
                    "ter": None,
                    "terComparison": None,
                    "ranking": None,
                    "scoreSummary": None,
                    "portfolioBenchmark": None,
                    "fundBenchmark": None,
                }
            )
            return await render_analytics_pdf(token)
        finally:
            await stop_browser()

    pdf_bytes = asyncio.run(run())
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500
```

- [ ] **Step 3: Run it manually once the frontend route exists (Task 8), skip otherwise**
  Run: `cd backend && pytest tests/services/analytics/test_pdf_export_integration.py -v -m playwright`
  Expected: PASS once the frontend dev server and `/print/analytics` route (Task 8) exist; this test is intentionally not part of the default `pytest` run (excluded the same way `postgres`-marked tests are, per this repo's existing convention) since it needs an external browser binary + running frontend.

- [ ] **Step 4: Commit**

```bash
git add backend/pytest.ini backend/tests/services/analytics/test_pdf_export_integration.py
git commit -m "test(analytics): add opt-in Playwright integration test for PDF export"
```

---

### Task 6: Extract `FundScoreCard` from `FundScoreDetailModal`

**Files:**
- Create: `frontend/src/features/analytics/FundScoreCard.tsx`
- Modify: `frontend/src/features/analytics/FundScoreDetailModal.tsx`
- Test: `frontend/src/features/analytics/FundScoreCard.test.tsx` (new)
- Test: `frontend/src/features/analytics/FundScoreDetailModal.test.tsx` (existing — verify still passes, do not need to rewrite)

**Interfaces:**
- Produces: `export function FundScoreCard({ data }: { data: FundScoreRow })` — a pure
  presentational component with no fetch/loading/error state, used by both
  `FundScoreDetailModal` (Task 6) and `PrintAnalyticsView` (Task 8).

- [ ] **Step 1: Write a failing test for the extracted component**

```tsx
// frontend/src/features/analytics/FundScoreCard.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { FundScoreCard } from "./FundScoreCard";
import type { FundScoreRow } from "./types";

const baseRow: FundScoreRow = {
  scheme_id: "s-1",
  scheme_name: "Test Flexi Cap Fund",
  category_unavailable: false,
  insufficient_history: false,
  thin_category: false,
  risk_adjusted_tier: 4,
  cost_adjustment: "0.25",
  final_score: "72.5",
  return_percentile: "70",
  risk_percentile: "65",
  consistency_hit_rate: "80",
};

describe("FundScoreCard", () => {
  it("renders the overall score and all three ingredient cards", () => {
    render(<FundScoreCard data={baseRow} />);
    expect(screen.getByText("72.5")).toBeInTheDocument();
    expect(screen.getByText("Return")).toBeInTheDocument();
    expect(screen.getByText("Risk")).toBeInTheDocument();
    expect(screen.getByText("Consistency")).toBeInTheDocument();
  });

  it("shows the category-unavailable notice instead of ingredient cards", () => {
    render(<FundScoreCard data={{ ...baseRow, category_unavailable: true }} />);
    expect(screen.getByText("Category Data Unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Return")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test, verify it fails**
  Run: `cd frontend && npx vitest run src/features/analytics/FundScoreCard.test.tsx`
  Expected: FAIL with a module-not-found error for `./FundScoreCard`

- [ ] **Step 3: Create `FundScoreCard.tsx` from the modal's inner content**

```tsx
// frontend/src/features/analytics/FundScoreCard.tsx
import { Badge } from "@/components/ui/badge";
import type { FundScoreRow } from "./types";
import { ShieldAlert, Info, Sparkles, TrendingUp, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface FundScoreCardProps {
  data: FundScoreRow;
}

function parseScore(val: string | null): number | null {
  if (val === null || val === undefined) return null;
  const num = parseFloat(val);
  return isNaN(num) ? null : num;
}

export function FundScoreCard({ data }: FundScoreCardProps) {
  const finalScoreNum = parseScore(data.final_score);
  const returnPct = parseScore(data.return_percentile);
  const riskPct = parseScore(data.risk_percentile);
  const consistencyPct = parseScore(data.consistency_hit_rate);
  const costAdjNum = parseScore(data.cost_adjustment);
  const tier = data.risk_adjusted_tier;

  return (
    <div className="space-y-6 pt-2">
      {data.category_unavailable ? (
        <div className="rounded-xl border border-[var(--color-warning)]/40 bg-[var(--color-warning)]/5 p-4 flex items-center gap-3">
          <ShieldAlert className="h-5 w-5 text-[var(--color-warning)] flex-shrink-0" />
          <div className="text-xs">
            <p className="font-bold text-[var(--color-ink)]">Category Data Unavailable</p>
            <p className="text-[var(--color-text-secondary)]">
              This scheme cannot be scored because SEBI category classification data is not available.
            </p>
          </div>
        </div>
      ) : data.insufficient_history ? (
        <div className="rounded-xl border border-[var(--color-warning)]/40 bg-[var(--color-warning)]/5 p-4 flex items-center gap-3">
          <Info className="h-5 w-5 text-[var(--color-warning)] flex-shrink-0" />
          <div className="text-xs">
            <p className="font-bold text-[var(--color-ink)]">Insufficient Track Record</p>
            <p className="text-[var(--color-text-secondary)]">
              This fund does not have enough historical NAV data to evaluate downside risk and 12-month rolling consistency.
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]/60 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-[11px] font-medium text-[var(--color-text-secondary)] uppercase tracking-wider block">
                Overall Unifolio Score
              </span>
              <div className="flex items-baseline gap-2 mt-0.5">
                <span className="font-display text-3xl font-bold text-[var(--color-ink)] tabular-nums type-display">
                  {finalScoreNum !== null ? finalScoreNum.toFixed(1) : "N/A"}
                </span>
                <span className="text-xs font-semibold text-[var(--color-text-secondary)]">/ 100</span>
              </div>
            </div>
            {tier !== null && (
              <div className="text-right">
                <Badge className="bg-[var(--color-accent)] text-white font-bold text-xs px-3 py-1 shadow-xs">
                  Tier {tier} of 5
                </Badge>
                <span className="text-[10px] text-[var(--color-text-secondary)] block mt-1">
                  {tier >= 4 ? "Top Tier Performer" : tier === 3 ? "Average Category Rank" : "Below Category Average"}
                </span>
              </div>
            )}
          </div>
          <div className="space-y-1.5 pt-1">
            <div className="flex justify-between text-[10px] text-[var(--color-text-secondary)] font-medium">
              <span>Tier 1 (Lower)</span>
              <span>Tier 3</span>
              <span>Tier 5 (Top 20%)</span>
            </div>
            <div className="grid grid-cols-5 gap-1.5">
              {[1, 2, 3, 4, 5].map((t) => {
                const isActive = tier === t;
                const isPassed = tier !== null && tier >= t;
                return (
                  <div
                    key={t}
                    className={cn(
                      "h-2.5 rounded-full transition-all duration-300",
                      isActive
                        ? "bg-[var(--color-accent)] ring-2 ring-[var(--color-accent)]/30 ring-offset-1"
                        : isPassed
                        ? "bg-[var(--color-accent)]/50"
                        : "bg-[var(--color-border)]"
                    )}
                  />
                );
              })}
            </div>
          </div>
        </div>
      )}

      {!data.category_unavailable && !data.insufficient_history && (
        <div className="space-y-3">
          <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-secondary)] flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-[var(--color-accent)]" />
            <span>The 3 Core Methodology Ingredients</span>
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5 space-y-2 shadow-2xs">
              <div className="flex items-center justify-between text-xs font-semibold text-[var(--color-ink)]">
                <span>Return</span>
                <Badge variant="outline" className="text-[9px] px-1 py-0 border-[var(--color-border)]">45% Wt</Badge>
              </div>
              <div>
                <span className="font-display text-xl font-bold text-[var(--color-ink)] tabular-nums type-data">
                  {returnPct !== null ? `${returnPct.toFixed(1)}%` : "N/A"}
                </span>
                <span className="text-[10px] text-[var(--color-text-secondary)] block mt-0.5">Category Return Percentile</span>
              </div>
              <p className="text-[10px] text-[var(--color-text-secondary)]/80 leading-relaxed border-t border-[var(--color-border)]/60 pt-1.5">
                Medium/long-term CAGR growth vs category peers.
              </p>
            </div>
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5 space-y-2 shadow-2xs">
              <div className="flex items-center justify-between text-xs font-semibold text-[var(--color-ink)]">
                <span>Risk</span>
                <Badge variant="outline" className="text-[9px] px-1 py-0 border-[var(--color-border)]">30% Wt</Badge>
              </div>
              <div>
                <span className="font-display text-xl font-bold text-[var(--color-positive)] tabular-nums type-data">
                  {riskPct !== null ? `${riskPct.toFixed(1)}%` : "N/A"}
                </span>
                <span className="text-[10px] text-[var(--color-text-secondary)] block mt-0.5">Downside Deviation Grade</span>
              </div>
              <p className="text-[10px] text-[var(--color-text-secondary)]/80 leading-relaxed border-t border-[var(--color-border)]/60 pt-1.5">
                Downside-only loss protection in bad months.
              </p>
            </div>
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5 space-y-2 shadow-2xs">
              <div className="flex items-center justify-between text-xs font-semibold text-[var(--color-ink)]">
                <span>Consistency</span>
                <Badge variant="outline" className="text-[9px] px-1 py-0 border-[var(--color-border)]">25% Wt</Badge>
              </div>
              <div>
                <span className="font-display text-xl font-bold text-[var(--color-accent)] tabular-nums type-data">
                  {consistencyPct !== null ? `${consistencyPct.toFixed(1)}%` : "N/A"}
                </span>
                <span className="text-[10px] text-[var(--color-text-secondary)] block mt-0.5">12M Rolling Beat Rate</span>
              </div>
              <p className="text-[10px] text-[var(--color-text-secondary)]/80 leading-relaxed border-t border-[var(--color-border)]/60 pt-1.5">
                Frequency of beating category median over 12M windows.
              </p>
            </div>
          </div>
          {costAdjNum !== null && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]/40 p-3 flex items-center justify-between text-xs">
              <span className="font-medium text-[var(--color-text-secondary)] flex items-center gap-1.5">
                <TrendingUp className="h-3.5 w-3.5 text-[var(--color-accent)]" />
                <span>TER Fee Cost Adjustment Nudge:</span>
              </span>
              <span className={cn("font-bold tabular-nums type-data", costAdjNum >= 0 ? "text-[var(--color-positive)]" : "text-[var(--color-negative)]")}>
                {costAdjNum >= 0 ? `+${costAdjNum.toFixed(2)} pts (Low Fee Bonus)` : `${costAdjNum.toFixed(2)} pts (High Fee Penalty)`}
              </span>
            </div>
          )}
        </div>
      )}

      <div className="rounded-xl border border-[var(--color-border)]/80 bg-[var(--color-bg)]/30 p-3.5 text-[11px] text-[var(--color-text-secondary)] space-y-1">
        <p className="font-bold text-[var(--color-ink)] flex items-center gap-1">
          <CheckCircle2 className="h-3.5 w-3.5 text-[var(--color-positive)]" />
          <span>Transparent Methodology Commitment</span>
        </p>
        <p className="leading-relaxed">
          Unifolio Fund Scores are modeling judgments built on historical data using a fixed 45% Return / 30% Downside Risk / 25% Consistency formula with TER fee nudges. They are comparative analytical insights, not regulated investment advice or guarantees.
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test, verify it passes**
  Run: `cd frontend && npx vitest run src/features/analytics/FundScoreCard.test.tsx`
  Expected: PASS (2 tests)

- [ ] **Step 5: Make `FundScoreDetailModal` a thin wrapper around `FundScoreCard`**

Replace the modal's inline content block (everything from `{loading ? (` through the
closing of the `data ? (...)` branch, i.e. the JSX previously duplicated into
`FundScoreCard`) with:

```tsx
        ) : data ? (
          <>
            <div className="flex items-center gap-2 -mt-2 mb-2">
              {data.thin_category && (
                <Badge variant="warning" className="text-[10px]">Thin Category</Badge>
              )}
            </div>
            <FundScoreCard data={data} />
          </>
        ) : null}
```

Remove the now-unused `Sparkles`, `TrendingUp`, `CheckCircle2`, `ShieldAlert`, `Info`
imports from `FundScoreDetailModal.tsx` if no longer referenced there directly (keep
`AlertCircle` — still used by the error branch), and add
`import { FundScoreCard } from "./FundScoreCard";`.

Note: the `Thin Category` badge already exists in the modal's `DialogHeader` (line
88-92 of the original file) — check before duplicating; if it's already shown there,
skip re-adding it in the body and just delete the duplicated inline JSX above without
the extra badge div.

- [ ] **Step 6: Run the existing modal test suite, verify no regressions**
  Run: `cd frontend && npx vitest run src/features/analytics/FundScoreDetailModal.test.tsx`
  Expected: PASS (all existing tests, unchanged)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/analytics/FundScoreCard.tsx frontend/src/features/analytics/FundScoreCard.test.tsx frontend/src/features/analytics/FundScoreDetailModal.tsx
git commit -m "refactor(analytics): extract FundScoreCard from FundScoreDetailModal"
```

---

### Task 7: Export payload type + `api.ts` functions

**Files:**
- Modify: `frontend/src/features/analytics/types.ts`
- Modify: `frontend/src/features/analytics/api.ts`
- Test: `frontend/src/features/analytics/api.test.ts` (create if it doesn't exist, else append)

**Interfaces:**
- Produces: `AnalyticsExportPayload` type, `postExportPdf(request: {scope, memberId, scopeName, payload: AnalyticsExportPayload}): Promise<Blob>`,
  `getExportPayload(token: string): Promise<AnalyticsExportPayload>` — consumed by
  Task 8 (`PrintAnalyticsView`) and Task 9 (`AnalyticsView`'s Download button).

- [ ] **Step 1: Add the type**

```typescript
// append to frontend/src/features/analytics/types.ts
export interface AnalyticsExportPayload {
  scopeName: string;
  allocation: AnalyticsAllocationSummary | null;
  ter: WeightedTerSummary | null;
  terComparison: DirectRegularTerComparison | null;
  ranking: CategoryRankingSummary | null;
  scoreSummary: PortfolioScoreSummary | null;
  portfolioBenchmark: PortfolioBenchmarkSummary | null;
  fundBenchmark: FundVsBenchmarkSummary | null;
}
```

- [ ] **Step 2: Write failing tests for the two new `api.ts` functions**

```typescript
// frontend/src/features/analytics/api.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { postExportPdf, getExportPayload } from "./api";
import * as session from "../auth/session";

describe("postExportPdf", () => {
  beforeEach(() => {
    vi.spyOn(session, "getToken").mockReturnValue("session-tok");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(new Blob(["%PDF-1.4"], { type: "application/pdf" })),
      }),
    );
  });

  it("POSTs the payload with the session bearer token and returns a Blob", async () => {
    const payload = { scopeName: "Family Aggregate" } as any;
    const blob = await postExportPdf({ scope: "aggregate", memberId: null, payload });
    expect(blob).toBeInstanceOf(Blob);
    const [, options] = (fetch as any).mock.calls[0];
    expect(options.method).toBe("POST");
    expect(options.headers.get("Authorization")).toBe("Bearer session-tok");
    expect(JSON.parse(options.body)).toEqual({ scope: "aggregate", member_id: null, payload });
  });
});

describe("getExportPayload", () => {
  it("GETs the payload by token with no Authorization header", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ scopeName: "Family Aggregate" }),
      }),
    );
    const result = await getExportPayload("tok-123");
    expect(result).toEqual({ scopeName: "Family Aggregate" });
    const [url, options] = (fetch as any).mock.calls[0];
    expect(url).toContain("/analytics/export/payload/tok-123");
    expect(options?.headers).toBeUndefined();
  });
});
```

- [ ] **Step 3: Run tests, verify they fail**
  Run: `cd frontend && npx vitest run src/features/analytics/api.test.ts`
  Expected: FAIL — `postExportPdf`/`getExportPayload` not exported from `./api`

- [ ] **Step 4: Implement the functions**

```typescript
// append to frontend/src/features/analytics/api.ts
import type { AnalyticsExportPayload } from "./types";

export async function postExportPdf(request: {
  scope: "aggregate" | "member";
  memberId: string | null;
  payload: AnalyticsExportPayload;
}): Promise<Blob> {
  const res = await authFetch(`/analytics/export/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scope: request.scope, member_id: request.memberId, payload: request.payload }),
  });
  return res.blob();
}

// Deliberately NOT authFetch: the headless print route has no session bearer
// token available to it — this endpoint is gated by possession of the opaque,
// single-use `token` itself (see the backend design spec's "Auth" section).
export async function getExportPayload(token: string): Promise<AnalyticsExportPayload> {
  const res = await fetch(`${API_BASE_URL}/analytics/export/payload/${token}`);
  if (!res.ok) {
    const errorPayload = await parseErrorDetail(res);
    throw new ApiError(res.status, errorPayload);
  }
  return res.json();
}
```

- [ ] **Step 5: Run tests, verify they pass**
  Run: `cd frontend && npx vitest run src/features/analytics/api.test.ts`
  Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/analytics/types.ts frontend/src/features/analytics/api.ts frontend/src/features/analytics/api.test.ts
git commit -m "feat(analytics): add AnalyticsExportPayload type and export API functions"
```

---

### Task 8: `PrintAnalyticsView` + print stylesheet + routing

**Files:**
- Create: `frontend/src/features/analytics/print/PrintAnalyticsView.tsx`
- Create: `frontend/src/features/analytics/print/print.css`
- Create: `frontend/src/features/analytics/print/PrintAnalyticsView.test.tsx`
- Modify: `frontend/src/main.tsx`

**Interfaces:**
- Consumes: `getExportPayload` (Task 7), `AllocationSection`/`TerSection`/
  `CategoryRankingSection`/`BenchmarkSection` (existing, unchanged props),
  `FundScoreCard` (Task 6).
- Produces: `export function PrintAnalyticsView()` — reads `?token=` from
  `window.location.search`, mounted directly by `main.tsx` for the `/print/analytics`
  path (no other file depends on this component being importable elsewhere).

- [ ] **Step 1: Write failing render test**

```tsx
// frontend/src/features/analytics/print/PrintAnalyticsView.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { PrintAnalyticsView } from "./PrintAnalyticsView";
import * as api from "../api";
import type { AnalyticsExportPayload } from "../types";

const payload: AnalyticsExportPayload = {
  scopeName: "Family Aggregate",
  allocation: { by_category: [], by_amc: [], total_value: "100000" },
  ter: null,
  terComparison: null,
  ranking: null,
  scoreSummary: {
    funds: [
      {
        scheme_id: "s-1",
        scheme_name: "Test Flexi Cap Fund",
        category_unavailable: false,
        insufficient_history: false,
        thin_category: false,
        risk_adjusted_tier: 4,
        cost_adjustment: "0.25",
        final_score: "72.5",
        return_percentile: "70",
        risk_percentile: "65",
        consistency_hit_rate: "80",
      },
    ],
    weighted_score: "72.5",
    covered_value: "100000",
    total_value: "100000",
    uncovered_schemes: [],
  },
  portfolioBenchmark: null,
  fundBenchmark: null,
};

describe("PrintAnalyticsView", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/print/analytics?token=tok-123");
    vi.spyOn(api, "getExportPayload").mockResolvedValue(payload);
  });

  it("renders every fund's score card inline, with no click required", async () => {
    render(<PrintAnalyticsView />);
    await waitFor(() => expect(screen.getByText("Test Flexi Cap Fund")).toBeInTheDocument());
    expect(screen.getByText("72.5")).toBeInTheDocument();
    expect(screen.getByText("Family Aggregate")).toBeInTheDocument();
  });

  it("sets the print-ready marker once rendered", async () => {
    render(<PrintAnalyticsView />);
    await waitFor(() =>
      expect(document.documentElement.dataset.printReady).toBe("true"),
    );
  });
});
```

- [ ] **Step 2: Run test, verify it fails**
  Run: `cd frontend && npx vitest run src/features/analytics/print/PrintAnalyticsView.test.tsx`
  Expected: FAIL — module not found

- [ ] **Step 3: Implement `print.css`**

```css
/* frontend/src/features/analytics/print/print.css */
@page {
  size: A4;
  margin: 16mm 14mm;
}

.print-section {
  break-inside: avoid;
}

.print-cover {
  break-after: page;
}
```

- [ ] **Step 4: Implement `PrintAnalyticsView.tsx`**

```tsx
// frontend/src/features/analytics/print/PrintAnalyticsView.tsx
import { useEffect, useState } from "react";
import { getExportPayload } from "../api";
import { AllocationSection } from "../AllocationSection";
import { TerSection } from "../TerSection";
import { CategoryRankingSection } from "../CategoryRankingSection";
import { BenchmarkSection } from "../BenchmarkSection";
import { FundScoreCard } from "../FundScoreCard";
import type { AnalyticsExportPayload } from "../types";
import "./print.css";

function useQueryToken(): string | null {
  const [token] = useState(() => new URLSearchParams(window.location.search).get("token"));
  return token;
}

export function PrintAnalyticsView() {
  const token = useQueryToken();
  const [payload, setPayload] = useState<AnalyticsExportPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setError("Missing export token.");
      return;
    }
    getExportPayload(token)
      .then(setPayload)
      .catch((err) => setError(err.message || "Failed to load export data."));
  }, [token]);

  useEffect(() => {
    if (payload || error) {
      document.documentElement.dataset.printReady = "true";
    }
  }, [payload, error]);

  if (error) {
    return <div data-testid="print-error">{error}</div>;
  }

  if (!payload) {
    return <div>Loading report…</div>;
  }

  return (
    <div className="p-10 space-y-10 bg-[var(--color-bg)]">
      <div className="print-cover space-y-2 py-24 text-center">
        <p className="text-xs font-bold uppercase tracking-widest text-[var(--color-accent)]">Unifolio</p>
        <h1 className="font-display text-3xl font-bold text-[var(--color-ink)]">Analytics Report</h1>
        <p className="text-sm text-[var(--color-text-secondary)]">{payload.scopeName}</p>
        <p className="text-xs text-[var(--color-text-secondary)]">
          Generated {new Date().toLocaleDateString("en-IN", { year: "numeric", month: "long", day: "numeric" })}
        </p>
      </div>

      <div className="print-section">
        <AllocationSection summary={payload.allocation} isLoading={false} />
      </div>
      <div className="print-section">
        <TerSection ter={payload.ter} comparison={payload.terComparison} isLoading={false} />
      </div>
      <div className="print-section">
        <CategoryRankingSection ranking={payload.ranking} isLoading={false} />
      </div>
      <div className="print-section">
        <BenchmarkSection
          portfolioBenchmark={payload.portfolioBenchmark}
          fundBenchmark={payload.fundBenchmark}
          isLoading={false}
        />
      </div>

      {payload.scoreSummary && payload.scoreSummary.funds.length > 0 && (
        <div className="space-y-6">
          <h2 className="font-display text-xl font-bold text-[var(--color-ink)]">Fund Score Detail — every held fund</h2>
          {payload.scoreSummary.funds.map((fund) => (
            <div key={fund.scheme_id} className="print-section rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
              <h3 className="font-display text-base font-bold text-[var(--color-ink)] mb-3">{fund.scheme_name}</h3>
              <FundScoreCard data={fund} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run test, verify it passes**
  Run: `cd frontend && npx vitest run src/features/analytics/print/PrintAnalyticsView.test.tsx`
  Expected: PASS (2 tests)

- [ ] **Step 6: Wire the route into `main.tsx`**, following the same
  `window.location.pathname` check `App.tsx` already uses for `/mobile`:

```tsx
// frontend/src/main.tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { PrintAnalyticsView } from './features/analytics/print/PrintAnalyticsView.tsx'

const isPrintRoute =
  typeof window !== "undefined" && window.location.pathname.startsWith("/print/analytics")

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isPrintRoute ? <PrintAnalyticsView /> : <App />}
  </StrictMode>,
)
```

The print route deliberately bypasses `<App />`/`AuthProvider` entirely — it never
calls a session-authenticated endpoint, so it doesn't need auth/onboarding state.

- [ ] **Step 7: Manually verify the route renders**
  Run: `cd frontend && npm run dev`, then visit
  `http://localhost:5173/print/analytics?token=anything` in a browser — expect the
  "Missing export token"/error state to NOT show (token is present) and instead see
  either "Loading report…" or a 404-driven error message (since no real token exists
  yet) — confirms the route mounts `PrintAnalyticsView` instead of the normal app shell.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features/analytics/print/ frontend/src/main.tsx
git commit -m "feat(analytics): add /print/analytics route for PDF export rendering"
```

---

### Task 9: "Download PDF" button in `AnalyticsView`

**Files:**
- Modify: `frontend/src/features/analytics/AnalyticsView.tsx`
- Modify: `frontend/src/features/dashboard/MainDashboardFlow.tsx`
- Test: `frontend/src/features/analytics/AnalyticsView.test.tsx` (append)

**Interfaces:**
- Consumes: `postExportPdf` (Task 7).
- Produces: a new optional `AnalyticsViewProps.activeMemberName?: string`, set by
  `MainDashboardFlow.tsx` from its already-fetched `members` list.

- [ ] **Step 1: Write failing tests**

```tsx
// append to frontend/src/features/analytics/AnalyticsView.test.tsx
// (adjust the mock setup below to match this file's existing mocking pattern
// for the `./api` module — reuse whatever mock scaffolding earlier tests in
// this file already use for getAggregateAllocation etc.)

it("disables the Download PDF button while any section is still loading", () => {
  render(<AnalyticsView viewMode="aggregate" memberId={null} />);
  const button = screen.getByRole("button", { name: /download pdf/i });
  expect(button).toBeDisabled();
});

it("enables Download PDF once all sections have loaded, and posts the assembled payload", async () => {
  const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });
  const postExportPdfMock = vi.spyOn(api, "postExportPdf").mockResolvedValue(blob);
  // createObjectURL/revokeObjectURL don't exist in jsdom by default
  vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:fake"), revokeObjectURL: vi.fn() });

  render(<AnalyticsView viewMode="aggregate" memberId={null} />);
  const button = await screen.findByRole("button", { name: /download pdf/i });
  await waitFor(() => expect(button).toBeEnabled());

  fireEvent.click(button);

  await waitFor(() => expect(postExportPdfMock).toHaveBeenCalledTimes(1));
  const call = postExportPdfMock.mock.calls[0][0];
  expect(call.scope).toBe("aggregate");
  expect(call.payload.scopeName).toBe("Family Aggregate");
});
```

- [ ] **Step 2: Run tests, verify they fail**
  Run: `cd frontend && npx vitest run src/features/analytics/AnalyticsView.test.tsx`
  Expected: FAIL — no "Download PDF" button exists yet

- [ ] **Step 3: Implement the button in `AnalyticsView.tsx`**

Add to the imports:

```tsx
import { postExportPdf } from "./api";
import type { AnalyticsExportPayload } from "./types";
```

Add to `AnalyticsViewProps`:

```tsx
export interface AnalyticsViewProps {
  viewMode: "aggregate" | "member";
  memberId: string | null;
  onAddDataForMember?: (memberId?: string) => void;
  activeMemberName?: string;
}
```

Add state and a handler inside the component body (near the other `useState` calls):

```tsx
const [isExporting, setIsExporting] = useState(false);
const [exportError, setExportError] = useState<string | null>(null);

const allSectionsLoaded =
  !allocationLoading && !terLoading && !rankingLoading && !scoreLoading && !benchmarkLoading;

const handleDownloadPdf = async () => {
  setIsExporting(true);
  setExportError(null);
  try {
    const payload: AnalyticsExportPayload = {
      scopeName: viewMode === "aggregate" ? "Family Aggregate" : activeMemberName ?? "Member",
      allocation,
      ter,
      terComparison,
      ranking,
      scoreSummary,
      portfolioBenchmark,
      fundBenchmark,
    };
    const blob = await postExportPdf({ scope: viewMode, memberId, payload });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `unifolio-analytics-${viewMode === "aggregate" ? "family" : memberId}.pdf`;
    anchor.click();
    URL.revokeObjectURL(url);
  } catch (err: any) {
    setExportError(err.message || "Failed to generate PDF");
  } finally {
    setIsExporting(false);
  }
};
```

Add the button to the hero header JSX (inside the `Card` at the top, next to the
Total Portfolio Value block):

```tsx
<button
  type="button"
  onClick={handleDownloadPdf}
  disabled={!allSectionsLoaded || isExporting}
  className="text-xs font-semibold px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white disabled:opacity-40 disabled:cursor-not-allowed"
>
  {isExporting ? "Generating…" : "Download PDF"}
</button>
```

Optionally render `exportError` near the button (a small `<p>` in the negative color
token, following the same pattern as the page-level error block already in this file).

- [ ] **Step 4: Pass `activeMemberName` from `MainDashboardFlow.tsx`**

```tsx
// frontend/src/features/dashboard/MainDashboardFlow.tsx
<AnalyticsView
  viewMode={viewMode}
  memberId={selectedMemberId}
  onAddDataForMember={handleAddDataTrigger}
  activeMemberName={members.find((m) => m.id === selectedMemberId)?.name}
/>
```

- [ ] **Step 5: Run tests, verify they pass**
  Run: `cd frontend && npx vitest run src/features/analytics/AnalyticsView.test.tsx`
  Expected: PASS (including the two new tests)

- [ ] **Step 6: Run the full frontend test suite to check for regressions**
  Run: `cd frontend && npx vitest run`
  Expected: PASS (all tests, including `MainDashboardFlow.test.tsx`)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/analytics/AnalyticsView.tsx frontend/src/features/analytics/AnalyticsView.test.tsx frontend/src/features/dashboard/MainDashboardFlow.tsx
git commit -m "feat(analytics): add Download PDF button, gated on full dashboard load"
```

---

### Task 10: End-to-end manual verification

**Files:** none (verification only)

- [ ] **Step 1:** Start the backend (`cd backend && uvicorn app.main:app --reload`) and
  confirm the startup logs show no Playwright launch error.
- [ ] **Step 2:** Start the frontend (`cd frontend && npm run dev`).
- [ ] **Step 3:** Log in, open the Analytics Dashboard on a household with at least
  one held fund with a real score, wait for all five sections to finish loading, click
  "Download PDF", and confirm a PDF file downloads.
- [ ] **Step 4:** Open the downloaded PDF and confirm: a cover page with the correct
  scope name; all five sections present; every held fund's full score breakdown
  visible without any click; branding/design tokens match the live dashboard's colors.
- [ ] **Step 5:** Switch to a specific member's view, repeat, and confirm the PDF only
  contains that member's data.
- [ ] **Step 6:** Run the opt-in Playwright integration test from Task 5 for real:
  Run: `cd backend && pytest tests/services/analytics/test_pdf_export_integration.py -v -m playwright`
  Expected: PASS

---

## Self-Review Notes

- **Spec coverage:** scope-follows-view (Task 9's `scope`/`memberId`/`activeMemberName`
  wiring), every-fund-inline (Task 8's `scoreSummary.funds.map(...)`), no-recompute
  (Task 9 assembles the payload from already-fetched state, no new fetch calls),
  no-new-auth-system (Task 4's unauthenticated `GET /export/payload/{token}`), branded
  cover page (Task 8), gated download button (Task 9's `allSectionsLoaded`) — all
  covered.
- **Type consistency checked:** `AnalyticsExportPayload` (Task 7) field names match
  exactly what `AnalyticsView` already holds in state and what `PrintAnalyticsView`
  (Task 8) destructures; `postExportPdf`'s `{ scope, memberId, payload }` argument
  shape matches the `AnalyticsExportRequest` Pydantic model's `scope`/`member_id`/
  `payload` fields in Task 4 (snake_case only at the JSON-serialization boundary,
  same convention `api.ts` already uses elsewhere in this file).
- **Non-goal confirmed excluded:** no Main Dashboard export task exists in this plan.
