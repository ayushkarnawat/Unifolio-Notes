# Analytics Dashboard PDF export — design (2026-08-20)

## Status: Approved by Ayush. Ready for `writing-plans`.

## Problem

Users want to download the Analytics Dashboard as a PDF to share with their CA or
peers. Not previously scoped in any PRD (confirmed via grep across PRD-01 through
PRD-04, the TDD, and `DEFERRED_FEATURES.md` — no mention anywhere).

## Goals

- One-click PDF download of the **entire** Analytics Dashboard for whatever scope is
  currently active — not just the visible viewport, no manual interaction required.
- **Scope mirrors the live view**: aggregate view → household-wide PDF; a specific
  member's view → that member's PDF only. Chosen for both lower effort and privacy
  (a member's PDF never includes another member's data).
- Every held fund's full Score Detail (the S20 modal's content) appears **inline,
  defaulted open** for every fund in scope — a PDF has no click-to-reveal, so nothing
  can be gated behind an interaction the way the live modal is.
- Feels like a real, branded Unifolio document (cover page, report layout) suitable to
  hand to a CA — not a screenshot of the live card-based dashboard UI.
- Dynamic template: gracefully handles few funds vs. many, missing benchmark data,
  unscored funds, uncovered TER schemes — same "Unavailable" edge-case handling the
  live dashboard already has, not a happy-path-only design.

## Non-goals

- Main Dashboard export (explicitly deferred to a possible future, separate task).
- Persisted PDF history/storage — generated on demand, not saved to any bucket or DB.
- A background job queue — render time is short enough (see Data flow) for a
  synchronous request/response.

## Approach

Server-side headless-browser render (Playwright's `page.pdf()` — real vector output,
not a raster screenshot) of a **new, bespoke print/report layout** (cover page +
per-section report pages, built with the app's existing design tokens from
`Docs/PRDs/Design-Schema-Unifolio.md`), reusing the live dashboard's existing section
components and formatting/Decimal/tier/badge logic with zero duplication.

Rejected: client-side `window.print()` + `@media print` (dismissed — browsers are
mostly Chromium anyway so no real quality differentiation, plus print-dialog friction);
a fully independent backend-native HTML-to-PDF template (e.g. WeasyPrint) maintained
separately from the live components (would duplicate formatting logic that already
exists and is tested).

## Key finding: no new backend data-shape work needed

`PortfolioScoreSummary.funds`, `CategoryRankingSummary.funds`, and
`FundVsBenchmarkSummary.funds` (`backend/app/services/analytics/schemas.py`) already
carry one full row per held fund with every field the S20 modal
(`FundScoreDetailModal.tsx`) needs. `AllocationSection`, `TerSection`,
`CategoryRankingSection`, and `BenchmarkSection` already render their entire per-fund
list unconditionally — nothing in those four sections is click-gated. The **only**
click-gated content anywhere in the dashboard is the Scorer section's per-fund
breakdown, opened per-scheme via `FundScoreDetailModal`. So "every fund's full
breakdown, defaulted open" is purely a frontend rendering change, not a new endpoint.

## Architecture

```
[Live AnalyticsView, already fully loaded]
        | user clicks "Download PDF" (enabled only once all 5 sections have loaded)
        v
POST /analytics/export/pdf
  body: { scope, member_id?, allocation, ter, terComparison,
          ranking, scoreSummary, benchmark, fundBenchmark }
  (the exact data AnalyticsView already has in React state — no re-fetch, no recompute)
        |
        v
Backend: validate scope ownership (same check as existing analytics routes)
        |
        v
Store payload behind a one-time opaque token (in-process TTL dict, ~2 min expiry)
        |
        v
Launch/reuse a warm headless Chromium (Playwright)
        |
        v
Navigate to frontend's own /print/analytics?token=...
        |
        v
Print route makes ONE fetch: GET /analytics/export/payload?token=...
  (token consumed on this single read — no further calls, no live analytics endpoints)
        |
        v
Renders the same section components + a new FundScoreCard per fund from that data,
sets data-print-ready once painted
        |
        v
Backend waits for [data-print-ready], calls page.pdf(), streams PDF bytes back
as the POST's response (Content-Disposition: attachment)
        |
        v
Frontend saves the blob as a file
```

## Components

**Frontend**
- `frontend/src/features/analytics/print/PrintAnalyticsView.tsx` (new) — no nav/sidebar
  chrome; cover page (Unifolio branding, scope's display name sourced from the
  already-available `MemberStatus` data, generation timestamp) followed by every
  section, rendered from the fetched payload as props.
- `frontend/src/features/analytics/FundScoreCard.tsx` (new, extracted from
  `FundScoreDetailModal.tsx`'s inner content — the tier band, three ingredient cards,
  cost-adjustment nudge, methodology footnote). `FundScoreDetailModal` becomes a thin
  `Dialog` wrapper around it (live UI, click-to-open, one fund); the print route maps
  `scoreSummary.funds` and renders one `FundScoreCard` per fund in a plain stacked list
  (no dialog, no click). One shared component, zero duplicated formatting/tier logic.
- `AllocationSection`, `TerSection`, `CategoryRankingSection`, `BenchmarkSection`
  reused unchanged — they already take fetched data as props (confirmed in
  `AnalyticsView.tsx`), so the print route passes payload-sourced data instead of
  live-fetched data with no component changes needed.
- "Download PDF" button (in `AnalyticsView.tsx`) — disabled/hidden until all five
  section loading flags are `false`. Loading state while the export POST is in flight;
  errors surfaced via the existing `ApiError` pattern.

**Backend**
- `backend/app/services/analytics/pdf_export.py` (new) — the in-process TTL token
  store (`{token: (payload_json, expires_at, used: bool)}`), the Playwright
  orchestration (shared warm Chromium instance, launched once via a new FastAPI
  lifespan hook in `main.py` — no lifespan hook exists there today, this adds one), and
  the render function.
- Two new routes in `app/api/analytics.py`:
  - `POST /analytics/export/pdf` — normal session-authenticated, same ownership check
    pattern as existing analytics routes; returns PDF bytes.
  - `GET /analytics/export/payload?token=...` — token-only, no session auth; serves the
    stored blob once and marks it used. Not exposed to the live app UI at all — only
    ever called by the headless Chromium instance itself.

## Auth

No new auth system. The print route makes exactly one call, and that call isn't
proving *who* it is — it's a capability to read *one specific stored blob*. So: a
single opaque `secrets.token_urlsafe` string is the lookup key into the in-process TTL
dict above. No `sessions`-mirroring table, no Alembic migration, no change to
`get_current_session`/`get_current_user`. Single-use is now simply "mark used on that
one read" (previously more complicated when the print route was going to make several
live analytics calls per render — no longer applicable now that it makes exactly one
fetch). ~2 minute absolute expiry as a backstop against an abandoned/failed render.

Rejected: cookie-based auth for the headless browser. This app has no cookie-based
auth anywhere (bearer token in `localStorage` + `Authorization` header only, confirmed
in `session.ts`/`apiClient.ts`) — introducing cookies would mean two parallel auth
mechanisms, reopens CSRF surface the bearer-token design avoids by construction, and
doesn't remove any implementation work (still need to mint/expire/clean up a
server-side value either way).

## Error handling

- `POST /analytics/export/pdf`: 403 if the claimed scope isn't the caller's own
  household/member (reuse existing ownership-check helper); 400 on a malformed/missing
  payload.
- `GET /analytics/export/payload`: 404/410 on unknown, expired, or already-used token.
- Playwright navigation/render failure → 500 with a generic message; the token is
  cleaned up (marked used) regardless of success or failure, no retry loop.
- `# ponytail:` the POST payload is trusted as-is rather than re-verified against the
  DB — it's the same authenticated user immediately re-submitting data they were
  already legitimately shown seconds earlier; re-deriving it server-side would defeat
  the entire point of avoiding a second computation.

## Testing

- Backend: unit tests for the token store (create → single read succeeds → second read
  404s; expiry), ownership check on the POST route (unit, no real Playwright).
- One integration test exercising real Playwright end-to-end (byte stream comes back
  with `Content-Type: application/pdf` and a non-trivial size) — gated the way
  slow/environment-dependent tests already are in this repo (mirroring the existing
  `postgres` pytest marker convention in `backend/pytest.ini`) so it doesn't block
  environments without the Chromium binary installed.
- Frontend: `FundScoreCard` extraction covered by updating the existing
  `FundScoreDetailModal` tests to exercise the shared component; `PrintAnalyticsView`
  gets a render test with mocked payload data asserting every fund appears without any
  click.

## Dependencies

New: `playwright` (Python package) + its Chromium binary (`playwright install
chromium`) — needed in the backend's dev environment and deploy image (Dockerfile
change is an implementation-plan-level detail, not designed here). No existing
dependency in this codebase does headless-browser PDF rendering; this is the smallest
addition that produces real vector PDF output rather than a raster screenshot.

## Follow-ups (not building now)

- Main Dashboard PDF export — same mechanism would apply, separate task.
