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
