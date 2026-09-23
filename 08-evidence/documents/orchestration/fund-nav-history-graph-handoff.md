# Handoff: fund-nav-history-graph

**Status:** DONE — Tasks 1-4 complete (backend, web, mobile, final
verification/review/docs).
**Parent plan:** none (small, fully-specified feature; no separate plan doc)

## Task

Replace the fake/stub "Fund Details" performance graph (both web modal and
mobile view) with a real one backed by actual NAV history. Currently:

- **Web** (`frontend/src/components/FundSignal.tsx`'s `FundSignalGraph`):
  renders a hardcoded 7-point fallback array
  (`[10,12,11,15,14,18,20]`/`[20,18,16,17,13,12,10]`). The 30D/90D/1Y period
  buttons are a no-op — `points` never depends on `selectedPeriod`.
- **Mobile** (`frontend/src/mobile/features/holdings/MobileFundDetailView.tsx`):
  generates an illustrative `Math.sin`-noise curve interpolated between
  `average_nav` and `current_nav` — not real history. It also renders a
  disclaimer: "Historical NAV timeseries API unavailable — displaying
  portfolio baseline trajectory." (line ~389) — remove this once wired to
  real data.

Both need to instead call a new backend endpoint and render the real
series, with the period set unified to **1M / 1Y / 3Y / 5Y / MAX** on both
platforms (web currently has 30D/90D/1Y, mobile has 1M/3M/6M/1Y/ALL — both
are being replaced, not extended).

This doc covers three sub-tasks, dispatched separately:
- **Task 1 (backend):** new endpoint + service (do this first, alone).
- **Task 2 (web) / Task 3 (mobile):** independent of each other, dispatched
  in parallel once Task 1 is merged, since both only depend on Task 1's
  fixed response contract below, not on each other.

---

## Task 1 — Backend: `GET /funds/{scheme_id}/nav-history`

**Status: DONE** (commits `abc1347`, `248daae` — service + route + 11 tests,
full backend suite 574 passed/3 skipped/0 failed, adversarial review clean
after one fix round; see `delegation-log.md` 2026-08-27 entries.)

### Files
- `backend/app/services/dashboard/schemas.py` — add response models.
- `backend/app/services/dashboard/fund_detail.py` — **new file**, service
  function.
- `backend/app/api/dashboard.py` — add route (add `Scheme` import from
  `app.models.reference` — not currently imported there).
- `backend/tests/services/dashboard/test_fund_detail.py` — **new file**.
- `backend/tests/api/test_dashboard_fund_nav_history_route.py` — **new
  file**.

### Schemas (add to `schemas.py`, follow the file's existing convention:
money/Decimal fields are always `str`, never `float` or `Decimal` directly
on a Pydantic model — see `FundScoreRow` for the pattern)

```python
class NavHistoryPoint(BaseModel):
    date: date
    nav: str
    return_pct: str  # cumulative % return vs. the series' first point, 2dp


class SchemeNavHistoryResponse(BaseModel):
    scheme_id: str
    period: str            # actual period served: "1M" | "1Y" | "3Y" | "5Y" | "MAX"
    requested_period: str  # what the client asked for
    clamped: bool           # True if requested_period exceeded available history
    points: list[NavHistoryPoint]
    overall_return_pct: str | None  # None if fewer than 2 points
```

### Service (`fund_detail.py`)

Signature: `async def get_fund_nav_history(db: Session, scheme: Scheme, period: str) -> SchemeNavHistoryResponse`

Logic:
1. Call `await warm_nav_history(db, [scheme])` (from
   `app.services.dashboard.nav`) first — this is the existing,
   already-tested fetch-and-cache path (TTL-guarded, so calling it on every
   request is cheap once warmed; it's what `category_ranking`/`scorer`
   already use for the same purpose). Do not reimplement fetching —
   `nav.py`'s `_fetch_nav_history`/`_upsert_nav_history` already handle the
   mfapi.in call, dedupe, and DB upsert.
2. Query `min(NavHistory.date)` and `max(NavHistory.date)` for
   `scheme.id`. If either is `None` (no NAV data at all, e.g. mfapi.in
   fetch failed and nothing was ever cached), return an empty response:
   `SchemeNavHistoryResponse(scheme_id=str(scheme.id), period="MAX",
   requested_period=period, clamped=(period != "MAX"), points=[],
   overall_return_pct=None)`.
3. Compute the window:
   - `period == "MAX"` → `start = earliest`.
   - Otherwise, `requested_start = latest - timedelta(days=N)` where
     `N = {"1M": 31, "1Y": 366, "3Y": 3*366, "5Y": 5*366}[period]` (use the
     +1-padded values shown — cheap leap/month-length safety margin, not
     that a resulting single extra day matters). If `requested_start <
     earliest` (fund doesn't have that much history), **clamp**: serve the
     full available range instead — `start = earliest`, `served_period =
     "MAX"`, `clamped = True`. Otherwise `start = requested_start`,
     `served_period = period`, `clamped = False`.
4. Query `NavHistory` rows for `scheme.id` with `date >= start` and
   `date <= latest`, ordered by `date`.
5. **Downsample** if `len(rows) > 400`: uniform stride sampling that always
   keeps the first and last row exactly (a fund with 10+ years of daily
   NAV on `MAX` can be 2500+ rows — no reason to ship that whole payload
   for a ~300px-wide chart). Write this as a small standalone helper
   function, e.g.:
   ```python
   def _downsample(rows: list[NavHistory], max_points: int = 400) -> list[NavHistory]:
       if len(rows) <= max_points:
           return rows
       stride = len(rows) / max_points
       indices = sorted({int(i * stride) for i in range(max_points)} | {len(rows) - 1})
       return [rows[i] for i in indices]
   ```
6. Compute `return_pct` per point as cumulative % vs. the **first row in
   the (possibly downsampled) series**, in `Decimal`, quantized to 2dp
   (`Decimal("0.01")`), using `ROUND_HALF_UP` — same rounding convention as
   the rest of the money path (check `lib/decimal.ts`'s backend
   counterpart / existing `Decimal(...).quantize(...)` call sites in
   `scorer.py`/`ter.py` for the exact idiom used elsewhere in this
   codebase and match it, don't introduce a new rounding convention).
   `overall_return_pct` is just the last point's `return_pct` (or `None`
   if `points` is empty).
7. **This whole function must never touch `float`** — everything is
   `Decimal` until the final `str()` conversion into the Pydantic model,
   per the project's non-negotiable.

### Route (`dashboard.py`)

```python
from typing import Literal
# add: from app.models.reference import Scheme
# add: from app.services.dashboard.fund_detail import get_fund_nav_history
# add SchemeNavHistoryResponse to the existing schemas import block

@router.get("/funds/{scheme_id}/nav-history", response_model=SchemeNavHistoryResponse)
async def get_fund_nav_history_route(
    scheme_id: uuid.UUID,
    period: Literal["1M", "1Y", "3Y", "5Y", "MAX"] = "1Y",
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    scheme = db.get(Scheme, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Scheme not found.")
    return await get_fund_nav_history(db, scheme, period)
```

Auth pattern: match `analytics.py`'s `get_fund_score` exactly — any
authenticated user, no household-member/ownership scoping (schemes are
shared reference data, same as `get_fund_score`'s existing precedent — do
not add an ownership check that doesn't exist for the equivalent endpoint).

### Tests (TDD — write these first, red before green)

`test_fund_detail.py` (service-level, in-memory sqlite, follow
`backend/tests/services/dashboard/test_nav.py`'s `_session()`/`_scheme()`
helpers and its `patch.object(nav_module, "_fetch_nav_history_uncached",
new=AsyncMock(...))` mocking convention — do not hit real mfapi.in in
tests):
- Returns points covering the requested period when enough history exists.
- Clamps to MAX (and sets `clamped=True`, `period="MAX"`) when requested
  period exceeds available history (e.g. `period="5Y"` on a fund with only
  8 months of NAV history).
- `overall_return_pct` matches the last point's `return_pct`.
- Empty history (no NAV rows at all, fetch also returns nothing) →
  `points=[]`, `overall_return_pct=None`, no exception raised.
- Downsampling: feed 1000+ synthetic rows, assert result has ≤400 points
  and the first/last original rows are preserved exactly.
- `return_pct` values are computed correctly against a known NAV series
  (hand-computed expected % for at least 2-3 points, not just "some
  string").

`test_dashboard_fund_nav_history_route.py` (route-level, follow
`test_dashboard_holdings_route.py`'s `_authed_headers_and_member` /
`client` fixture pattern):
- 401 without auth.
- 404 for a nonexistent `scheme_id`.
- 200 with a real scheme + mocked NAV history, correct shape.
- `period` query param defaults to `"1Y"` when omitted.
- Invalid `period` value → 422 (FastAPI's `Literal` validation, free —
  just confirm it, don't hand-roll validation).

### Constraints (from `AGENTS.md`/`CLAUDE.md`, not restated in full)
- `Decimal`, never `float`, anywhere in this path.
- No new dependency — everything needed already exists in the codebase
  (`nav.py`'s fetch/cache, SQLAlchemy, FastAPI's `Literal` validation).
- Reuse `warm_nav_history`, do not write a second NAV-fetch path.

### Approaches considered and rejected
- **Returning raw NAV only, computing % client-side:** rejected — the
  Decimal-never-float non-negotiable makes this a backend job; JS numbers
  are floats, so any % computation must happen server-side in `Decimal`.
- **A dedicated `inception_date` column check for clamping:** `Scheme` has
  no `inception_date` field (checked the model) — clamping is decided
  purely from `nav_history`'s own `min(date)`, which is simpler and
  already necessarily correct (there's no NAV before the earliest cached
  row regardless of what an inception date would say).
- **No downsampling:** rejected — a 20-year-old fund's `MAX` daily series
  is thousands of points for a ~300-400px-wide chart; pure bandwidth/render
  waste with zero visual benefit. 400 is a reasonable default, not exposed
  as a tunable — no evidence yet that it needs to be.

### Open questions
None — this section is fully specified. If something here contradicts
what's actually in `schemas.py`/`dashboard.py`/`nav.py` when you open them
(e.g. an import already exists, a helper already does something similar),
prefer what's actually there and flag the discrepancy in your report
rather than guessing which is right.

---

## Task 2 — Web: wire `FundSignalGraph` to real data

**Status: DONE** (commits `b868947`, `9be0e2e`, `c38b37e` — implementation + two
review-fix rounds, full frontend suite 355 passing, `tsc` clean; see
`delegation-log.md` 2026-08-27 entries.)

**Depends on Task 1 being merged** (needs the real endpoint to exist).

### Files
- `frontend/src/features/dashboard/api.ts` — add `getFundNavHistory`.
- `frontend/src/features/dashboard/types.ts` — add `NavHistoryPoint` /
  `SchemeNavHistoryResponse` types mirroring the backend response exactly.
- `frontend/src/components/FundSignal.tsx` — rewire `FundSignalGraph`.
- `frontend/src/components/FundSignal.module.css` — add classes for the
  new loading/error/clamped states (small additions, match existing token
  usage — `var(--color-*)`, `var(--space-*)`, `var(--radius-*)`, no new
  hardcoded colors).
- `frontend/src/features/dashboard/FundDetailModal.tsx` — pass `schemeId`
  through to `FundSignalGraph` (currently only passes
  `returnPercentage`).
- Existing test file for `FundSignal` (find it — likely
  `frontend/src/components/FundSignal.test.tsx` or similar; if none
  exists, create one) and `FundDetailModal`'s test file.

### API client (`api.ts`)

```typescript
export async function getFundNavHistory(
  schemeId: string,
  period: NavHistoryPeriod,
  signal?: AbortSignal
): Promise<SchemeNavHistoryResponse> {
  const res = await authFetch(`/funds/${schemeId}/nav-history?period=${period}`, { signal });
  return res.json();
}
```
Follow the exact `authFetch`/`cachedFetch` pattern already used by every
other function in this file — nothing new needed, `cachedFetch` already
gives this free client-side caching per URL (which includes `period` in
the query string, so each period is cached separately, which is correct).

### Types (`types.ts`)

```typescript
export type NavHistoryPeriod = "1M" | "1Y" | "3Y" | "5Y" | "MAX";

export interface NavHistoryPoint {
  date: string;
  nav: string;
  return_pct: string;
}

export interface SchemeNavHistoryResponse {
  scheme_id: string;
  period: NavHistoryPeriod;
  requested_period: NavHistoryPeriod;
  clamped: boolean;
  points: NavHistoryPoint[];
  overall_return_pct: string | null;
}
```

### `FundSignalGraph` rewire — UI/UX spec (this is the part that must be
genuinely polished, not a bare functional swap)

Current state: a static, non-interactive sparkline with a period toggle
that doesn't do anything. Target state:

1. **Props change:** add `schemeId: string` (required) to
   `FundSignalGraphProps`; drop `sparklineData` (no longer needed, real
   data is fetched internally) — check `FundDetailModal.tsx` isn't passing
   `sparklineData` anywhere else before removing it (it currently isn't).
2. **Period toggle is now real.** Buttons are `["1M", "1Y", "3Y", "5Y",
   "MAX"]` (replacing `["30D", "90D", "1Y"]`). Clicking one sets
   `selectedPeriod` and triggers a refetch via a `useEffect` keyed on
   `[schemeId, selectedPeriod]` — mirror the fetch/abort/error pattern in
   `DistributorComparisonModal.tsx` (lines ~33-56: `AbortController`,
   `setLoading(true)`/`setError(null)` at fetch start, `.catch` with an
   `err?.name === "AbortError"` early-return guard, `setLoading(false)` in
   both branches).
3. **Loading state:** while fetching, render the existing shared
   `Skeleton` component (`frontend/src/components/Skeleton.tsx`) sized to
   match `.sparklineWrapper`'s dimensions (`height="96px"`, full width) in
   place of the SVG — not a spinner, not a custom loader; this codebase
   already has a shared `Skeleton` and every other modal
   (`DistributorComparisonModal`) uses it for exactly this.
4. **Error state:** on fetch failure, render `<p className="type-body">{error}</p>`
   inside a small `.errorBox`-style container (add the class to
   `FundSignal.module.css`, matching `DistributorComparisonModal.module.css`'s
   existing `.errorBox` visually — check that file for the exact
   border/padding/color values and mirror them for consistency across the
   app, not a divergent new error style), with a `message = "Failed to
   load performance history"` fallback if `err.message` is empty.
5. **Empty state** (`points.length === 0`, e.g. a brand-new fund with zero
   cached NAV yet): render `<p className="type-body">No performance history available yet.</p>`
   in place of the chart — do not render an empty/broken SVG.
6. **Chart data:** plot `points.map(p => Number(p.return_pct))` — i.e. the
   **cumulative % return series**, not raw NAV rupees. This keeps the
   chart on the same 0-anchored scale as the return badge already shown
   below it, and means "up" on the chart always visually means "gained
   money", regardless of the underlying NAV's absolute value. Existing
   `d3Line`/`d3Area` + `curveMonotoneX` smoothing logic (lines ~123-150)
   is unchanged — it already generically handles an arbitrary-length
   `points` array (up to 400, from Task 1's downsampling — confirm the
   curve renders smoothly at that density; it should, `curveMonotoneX`
   scales fine).
7. **Interactivity — currently there is none** (the sparkline is a static
   line with zero hover feedback, unlike the mobile view's already-good
   interactive treatment in `MobileFundDetailView.tsx`). Bring web up to
   the same bar, adapted to the compact modal size:
   - Add hover/touch point-target circles (invisible, generous hit-radius,
     same technique as `MobileFundDetailView.tsx` lines ~371-379) over
     each plotted point.
   - On hover/touch, show a small active-point marker (filled circle,
     `stroke: var(--color-surface)`, matching the mobile treatment) and a
     thin dashed vertical guide line in `var(--color-border)`.
   - Add a one-line readout above the chart showing the hovered (or, when
     nothing is hovered, the *last*) point's date and `return_pct`, e.g.
     `Aug 25, 2026: +15.20%` — reuse the existing `.popoutHeader` row's
     available space or add a line directly below it; keep it visually
     quiet (`type-caption`-equivalent sizing, not competing with
     `.popoutTitle`).
8. **Clamped-to-MAX note:** when the response's `clamped === true`, show a
   small inline note below the chart: `Showing full history since
   inception — not enough data for {requestedPeriod}` (substitute the
   actual requested period, e.g. "5Y"). Keep it visually consistent with
   the `errorBox`/info-note treatment already established
   elsewhere in the app (check `MobileFundDetailView.tsx`'s existing
   info-note box, lines ~386-390, for the icon+text pattern to mirror —
   `lucide-react`'s `Info` icon, small muted text) rather than inventing a
   new visual language for this one case.
9. **`returnBadge` at the bottom:** now driven by `overall_return_pct`
   from the real response instead of the `returnPercentage` prop passed
   in from `FundDetailModal` (which was the *holding's* total return, not
   the *period's* return — these are conceptually different numbers once
   the chart is period-scoped, and showing the wrong one would be
   confusing/wrong, not just a style nit). Keep the existing up/down arrow
   + color logic, just source the number from the fetched series.

### `FundDetailModal.tsx` change
Pass `holding.scheme_id` as the new `schemeId` prop to `FundSignalGraph`;
the `returnPercentage` prop it currently passes can stay for other uses of
`FundSignalGraph` if any exist (check — grep for other callers before
deciding whether to keep or drop that prop entirely).

### Tests
Cover: period toggle triggers a refetch with the right query param;
loading/error/empty states render correctly; clamped note renders when
`clamped: true`; hover sets the active point and readout text updates. Use
this codebase's existing frontend test conventions (check a sibling
test file, e.g. `DistributorComparisonModal`'s test file if one exists,
for the mocking pattern used for `api.ts` functions in tests — likely
`vi.mock`).

### Constraints
- No `float`/`parseFloat` accumulation on money values — display-only
  `Number(p.return_pct)` for plotting screen-pixel positions is fine (this
  mirrors the codebase's own documented exception in `lib/decimal.ts` for
  final, non-accumulating display conversions), but never feed a
  `parseFloat`'d value back into further arithmetic that matters.
- Reuse `d3-shape` (already a dependency, already imported here) — do not
  add a new charting library.

### Open questions
None. Already confirmed (orchestrator grep): `FundSignalGraph`'s only
caller is `FundDetailModal.tsx` (plus its own `FundSignal.test.tsx`) — its
prop contract is safe to change freely, no other caller to preserve
compatibility with.

---

## Task 3 — Mobile: wire `MobileFundDetailView`'s chart to real data

**Status: DONE** (commits `4378679`, `750f189`, `2d7e72b` — implementation +
two review-fix rounds, full narrative in `Docs/orchestration/delegation-log.md`)

**Depends on Task 1 being merged. Independent of Task 2** (different
files) — can be dispatched in parallel with it.

### Files
- `frontend/src/mobile/features/holdings/MobileFundDetailView.tsx`
- `frontend/src/mobile/features/holdings/MobileFundDetailView.test.tsx`
  (already exists — extend it)
- `frontend/src/features/dashboard/api.ts` /
  `frontend/src/features/dashboard/types.ts` — reuse the exact same
  `getFundNavHistory`/`SchemeNavHistoryResponse`/`NavHistoryPeriod`
  additions from Task 2. **If Task 2 has already landed these, do not
  duplicate them — import and reuse.** If dispatched in parallel with Task
  2 before it lands, add them here too; the orchestrator will de-duplicate
  at merge time (flag this in your report either way so it's not missed).

### Rewire — UI/UX spec

This view's interactive chart *scaffold* (hover/touch targets, gradient
area, dashed guide line, active-point circle, `d3`-free hand-rolled SVG
polyline) is already good — keep the rendering JSX (lines ~301-384)
structurally as-is. What changes is the data source and the states around
it:

1. **Remove** the `Math.sin`-based `chartData` generator (lines ~76-120)
   entirely — replace with a real fetch.
2. **Timeframe set:** change `Timeframe` type and the rendered pills
   (line ~283) from `["1M", "3M", "6M", "1Y", "ALL"]` to `["1M", "1Y",
   "3Y", "5Y", "MAX"]` — matching Task 2's set and the new backend
   contract's `NavHistoryPeriod` type exactly (reuse that type instead of
   this file's local `Timeframe` type, to avoid the two silently drifting
   apart again the way web/mobile already had before this task).
3. **Fetch on `[holding.scheme_id, selectedTimeframe]` change** — same
   `AbortController`/loading/error pattern as Task 2 and
   `DistributorComparisonModal.tsx`.
4. **Loading state:** replace the chart `<svg>` with a `Skeleton` sized to
   the existing chart container (`h-[150px]`, full width) while loading —
   same shared component as Task 2, do not hand-roll a mobile-specific
   loader.
5. **Error state:** replace the chart with a small error message in the
   same visual language as the existing "Historical Data Transparency
   Note" box (lines ~386-390) — reuse that box's exact classes for an
   error instead of inventing new ones, swap the icon/text for the error
   case (keep the `Info` icon or swap for an appropriate one already used
   elsewhere in this file/its imports — check before adding a new
   `lucide-react` icon import if one already fits).
6. **Empty state** (no NAV history yet): same message/treatment as Task 2.
7. **`chartData` now comes from `points.map(p => ({ date: <formatted>,
   value: Number(p.return_pct), label: `${p.return_pct}%` }))`** — i.e.
   the chart continues to plot `value` exactly as before, just sourced
   from the real `return_pct` series instead of the synthetic curve. The
   existing `minVal`/`maxVal`/`pointsString`/`areaPathString` computation
   (lines ~128-147) needs no changes — it already generically scales
   whatever `chartData` it's given.
8. **`activePoint`'s date formatting:** the real API returns an ISO date
   string (`"2026-08-25"`); format it the same way the old generator did
   (`toLocaleDateString("en-IN", { month: "short", day: "numeric" })`) when
   building each `ChartPoint`, so the existing tooltip/readout JSX doesn't
   need to change.
9. **Remove the disclaimer** ("Historical NAV timeseries API unavailable —
   displaying portfolio baseline trajectory", lines ~386-390) — replace it
   with the clamped-to-MAX note (only rendered when `clamped === true`),
   same copy as Task 2: `Showing full history since inception — not
   enough data for {requestedPeriod}`.
10. **Header return %** (`totalReturnPct`, used elsewhere in this view for
    the KPI cards, line ~72) is unrelated to this chart's own
    `overall_return_pct` — do not conflate them. `totalReturnPct` stays
    computed from `profit`/`invested` exactly as today (that's the
    holding's all-time return, a different number from the currently
    period-scoped chart's return) — only the chart's own numbers switch to
    the fetched series.

### Tests
Extend the existing `MobileFundDetailView.test.tsx`: timeframe pill click
triggers a refetch with the right period; loading/error/empty states;
clamped note renders correctly; existing hover/touch interaction tests (if
any) still pass against real fetched data instead of the synthetic curve.

### Constraints
Same as Task 2 (Decimal-never-float in the data path, display-only
`Number()` conversion is fine, no new dependencies).

### Open questions
None specified — same "if something contradicts what's actually in the
schema" rule as Task 2.

## Task 4 — Final verification + whole-diff review + docs update

**Status: DONE** — see delegation log entries dated 2026-08-27 under
`fund-nav-history-graph Task 4` for full detail.

Whole-diff review (job `task-mtb5xejv-kwscz6`) found 3 Important + 1 Minor.
Fixed and committed: the web render-time stale-state reset (`c58c55b`,
porting Task 3's mobile pattern), mobile's contradictory clamped+empty
message (`83cfacc`), and the CRLF/trailing-whitespace Minor (`d7d06d5`).

**Resolved by user decision:** `values = points.map((p) =>
Number(p.return_pct))` in both `FundSignal.tsx` and
`MobileFundDetailView.tsx` float-coerces the Decimal-string `return_pct`
for chart-geometry (min/max/range) math — flagged as ambiguous against the
"Decimal-never-float in the data path" constraint above. Confirmed
`return_pct` is always server-side quantized to exactly `Decimal("0.01")`
(`fund_detail.py`'s `_RETURN_QUANTUM`), so float rounding error is ~1e-15,
undetectable at any chart pixel scale — Decimal-based geometry math would
be pixel-identical. No visual upside; kept as-is (float for layout is an
accepted exception to the data-path rule here, since no downstream number
is ever displayed or persisted from this calculation).

Also fixed this session, found only after implementation via user-reported
screenshots (not part of the original whole-diff review): web's chart
distorted non-uniformly on real desktop/laptop widths (`viewBox="0 0 100
44" preserveAspectRatio="none"` inside a fluid-width wrapper forced
anisotropic scaling at realistic modal widths). Fixed by measuring the
wrapper's live rendered width via `ResizeObserver` and using it directly as
the viewBox width, with viewBox height fixed to match the CSS wrapper
height exactly — commit `d6b367e`. Visually confirmed by the user on both
web (desktop/laptop) and mobile after the fix — round marker renders as a
true circle, no curve warping.
file, flag it rather than guess" rule as Task 1/2.
