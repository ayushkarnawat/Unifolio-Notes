# Mobile polish continues past the mobile track's prior end date, and a Fund Details performance graph is added

## For stakeholders

Two separate pieces of work landed on the same day, after the mobile track
this vault had previously recorded as ending on 2026-08-25: further mobile
polish (roadmap milestone animations, scrolling fixes, layout centering), and
a new performance graph on the Fund Details screen, backed by a new backend
endpoint. The graph work also documents a deliberate, narrow exception to
the product's usual rule of never using ordinary floating-point numbers for
money — used only for chart pixel positioning, never for any number shown to
the user.

## Technical detail

### Intended outcome

Continue mobile UI polish beyond the prior mobile-track stage, and add a
per-fund NAV history performance graph to the Fund Details screen.

### What actually happened

**Mobile UI polish**: roadmap milestone state-logic animations, a
comprehensive pass on mobile scrolling issues, import-screen centering
fixes, and a call-to-action layout audit across mobile screens.

**Fund Details performance graph**: a new backend endpoint,
`GET /funds/{scheme_id}/nav-history`, serves the NAV history a fund's
performance graph needs. A `ResizeObserver`-based fix addresses chart
distortion that occurred without it. The chart's own geometry math uses
ordinary floating-point numbers rather than `Decimal` — documented as a
deliberate, narrow exception to the project's `Decimal`-never-`float`
non-negotiable, on the reasoning that pixel/SVG-path coordinates are a
display-geometry concern, not a money or percentage value shown to the
user; no monetary or percentage figure in this feature uses float.

### Deviation (if any) — decision or response taken

The float-for-chart-geometry exception is a deliberate, documented
deviation from the project's usual `Decimal`-never-`float` rule, scoped
narrowly to pixel/path coordinates.

### Result

Mobile polish continues past the previously-recorded end of the mobile
track; a new Fund Details performance graph exists, backed by a new
endpoint.

### Related

- [2026-08-19 → 2026-08-25 journey stage](2026-08-19-the-mobile-track-pulls-ahead.md) (the mobile track this stage continues past)
- [Quality and constraints](../06-architecture/quality-and-constraints.md) (the `Decimal`-never-`float` rule this stage carves a narrow, documented exception into)
- Evidence: `08-evidence/documents/engineering-loop/session.md` (2026-08-27 sections)

## Addendum — 2026-09-23: per-task detail behind the NAV history graph build

The new `GET /funds/{scheme_id}/nav-history` endpoint (Task 1, commits
`abc1347`/`248daae`, 574/3 suite) replaced hardcoded fallback data on web
(`FundSignalGraph`'s static 7-point array) and a `Math.sin`-noise synthetic
curve on mobile (`MobileFundDetailView`, which had shipped with a visible
disclaimer: "Historical NAV timeseries API unavailable — displaying
portfolio baseline trajectory") with one real, shared series. The two
platforms' period sets, previously divergent (web: 30D/90D/1Y; mobile:
1M/3M/6M/1Y/ALL), were unified to 1M/1Y/3Y/5Y/MAX on both. The backend
downsamples to at most 400 points (uniform stride, always keeping the
first/last row exactly) so a fund with 10+ years of daily NAV doesn't ship
thousands of points for a ~300px chart, and clamps to the fund's full
available history (`clamped: true`) when a requested period exceeds it,
rather than erroring.

Task 2 (web, commits `b868947`/`9be0e2e`/`c38b37e`) brought the previously
non-interactive web sparkline up to mobile's existing interactive bar —
hover/touch point targets, an active-point marker, a dashed guide line, and
a date+return readout — rather than a bare functional swap. Task 3
(mobile, commits `4378679`/`750f189`/`2d7e72b`) kept the existing
interactive chart scaffold as-is and only swapped its data source.

**Task 4's whole-diff review** found 3 Important + 1 Minor, all fixed: a
web render-time stale-state reset (`c58c55b`, porting Task 3's mobile
pattern), mobile's contradictory clamped-and-empty message shown
simultaneously (`83cfacc`), and a CRLF/trailing-whitespace Minor
(`d7d06d5`). The float-for-chart-geometry exception this journey entry's
original text already names was reasoned through explicitly during this
review, not assumed: `return_pct` is always server-side quantized to
exactly `Decimal("0.01")`, so the float-conversion rounding error for
chart pixel math is ~1e-15 — undetectable at any pixel scale, with no
downstream number ever displayed or persisted from that calculation.

**A separate, user-reported bug** (not part of the whole-diff review) was
found and fixed the same session: the web chart distorted non-uniformly at
real desktop/laptop widths, because a fixed `viewBox` inside a fluid-width
wrapper forced anisotropic scaling. Fixed by measuring the wrapper's live
rendered width via `ResizeObserver` and using it directly as the viewBox
width (`d6b367e`), visually confirmed by the user on both web and mobile.

Evidence: `08-evidence/documents/orchestration/fund-nav-history-graph-handoff.md`
