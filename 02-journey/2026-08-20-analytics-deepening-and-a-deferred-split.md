# Analytics deepening, and a category split that was deferred

## For stakeholders

Three analytics workstreams ran between 20 and 27 August. The first designed a
PDF export of the analytics dashboard, using a real headless browser on the
server so the output is genuine vector PDF rather than a screenshot. The
second moved the distributor-comparison feature from a single-fund view to a
whole-portfolio view, replacing the old version outright. The third
investigated whether the index-fund category — which holds 1,150 schemes and
slows down comparisons for anyone who owns one — could be split into smaller
groups, and concluded that it cannot be done both honestly and effectively; it
was deferred with a written trigger for revisiting. On 27 August the team also
settled how the dashboard should behave while it is still computing. None of
the implementation plans in this stretch were executed.

## Technical detail

### Intended outcome

Make the analytics dashboard exportable, make distributor comparison
portfolio-wide, and remove a known performance cliff for index-fund holders.

### What actually happened

**PDF export (2026-08-20).** The design chose server-side Playwright page
rendering. Three alternatives were weighed and rejected with reasons:
client-side `window.print()` with print stylesheets (no real control over
pagination or fidelity); a backend-native WeasyPrint template (would duplicate
formatting logic that is already built and tested in the React view); and
cookie-based authentication for the headless browser (the application has no
cookies anywhere — the bearer token lives in `localStorage` — and adding them
would reopen a CSRF surface for one feature). Instead the browser is handed a
short-lived capability token.

The design's most useful finding is a negative one: **no new backend data-shape
work is needed**, because the only click-gated content in the entire dashboard
is the Scorer section's per-fund detail modal. Export scope mirrors the live
view exactly, which also settles a privacy point — one member's PDF can never
contain another member's data.

The plan adds a capability-token store, a `playwright` dependency with a warm
shared Chromium started from a new FastAPI lifespan hook, a
`settings.frontend_base_url`, `POST /analytics/export/pdf` (session-authed)
and `GET /analytics/export/payload` (token in the query string, with **no**
user dependency — it is a capability, not a credential), and a `playwright`
pytest marker mirroring the existing `postgres` marker. `FundScoreCard` is
extracted from the detail modal so both the live view and the print view can
use it. A `PrintAnalyticsView` is mounted directly by `main.tsx` on
`/print/analytics`, bypassing the app shell and the auth provider entirely —
which is how a no-router application serves a second entry point. The download
control is gated on all sections having loaded. The plan requires an inline
note recording that the in-process token dictionary does not survive a restart
or a multi-worker deployment; recorded here as R-039.

**Portfolio-level distributor comparison (2026-08-20).** The fund-scoped
variant is removed entirely rather than kept alongside — the old route is
deleted, not deprecated. Computation becomes a single batched pass
(`compute_distributor_comparison` over a member-id list, two queries), and the
cache reuses the existing holdings-cache generation signal for invalidation,
adding no new call sites. The design is honest about a limit it cannot design
away: the cached holdings rows cannot serve as the data source, because their
granularity is wrong for this question. One behavioural change is called out
explicitly — when a scheme has no NAV, it is now dropped from that
distributor's breakdown only, where previously the whole response was dropped.
The triggers move out of the fund detail views into the Holdings section
header on desktop and into the mobile holdings and dashboard views.

The design also **declines** to fix `compute_holdings`' own pre-existing
per-folio N+1, on the stated grounds of not risking a regression in a working
path for an unrelated cleanup after four review rounds of prior performance
work. It asks for the item to be logged as a follow-up. Recorded as R-040.
The plan itself is unexecuted and ends on an unanswered question — "Which
approach?" — so even the implementation shape is not settled.

**The index-fund mega-category (2026-08-20).** Marked "Deferred, not built".
AMFI's `"Other Scheme - Index Funds"` heading holds 1,150 schemes. Two options
were costed and both rejected; the full working is preserved in
[INV-005](../04-investigations/INV-005-index-fund-mega-category.md). The
finding that closes it: there is no split that is both AMFI-native and
actually shrinks the category to a non-mega size. A side finding is more
consequential than the deferral —
`get_category_universe`'s exact-string category match means schemes filed
under legacy AMFI headers are invisible to comparison, a possible pre-existing
data-completeness gap (R-041). The revisit trigger is written down: only if
load time for index-fund holders becomes a demonstrated user-facing problem,
which is currently mitigated by the fifteen-minute per-category cache added by
the earlier BUG-001 fix.

**Loading states (2026-08-27).** Five mockup options were produced for the
"still computing" state and two were chosen: stale-while-revalidate for
returning visits (last-known data dimmed, with a single background-refresh
pill) and per-card progressive reveal with one spinning ring for a genuine
cold start. The progress bar in the original version of the latter was dropped
as redundant. The rationale rejects the other options in one line — both were
"pretend it's fast" treatments for a wait that, on cold start, genuinely is
not fast. The rationale also names a mechanism that appears nowhere else in
this batch: on cold start, a **per-household precompute writes each section's
row as it finishes**. Recorded as R-042, because the vault has no record of
that mechanism being designed or built.

### Deviation — decision or response taken

The index-fund split was deferred rather than forced, with an explicit revisit
trigger. The holdings N+1 was deliberately left in place. Both are recorded as
decisions with reasons rather than as oversights.

The 2026-09-17 status banner on
`05-docs/explanation/fund-scoring-methodology.md` concerns two coexisting
fund-*scoring* methodologies (R-015). The index-fund work concerns the
*peer-universe scoping* used by category ranking, not a second scoring
formula. **It neither corroborates nor conflicts with R-015.** This is stated
because it is a plausible-looking connection that does not hold.

### Result

All three designs complete; no implementation plan in this stretch executed.
The 2026-08-27 loading-state decision is the only thing in this stage that is
settled rather than planned.

### Related

- ADR-013 — analytics PDF export architecture
- INV-005 — the index-fund mega-category
- R-039 — in-process capability-token store
- R-040 — `compute_holdings` per-folio N+1 left in place
- R-041 — `get_category_universe` exact-string match and legacy headers
- R-042 — an undocumented per-household analytics precompute
- Evidence: `08-evidence/documents/specs/2026-08-20-analytics-pdf-export-design.md`
- Evidence: `08-evidence/documents/plans/2026-08-20-analytics-pdf-export.md`
- Evidence: `08-evidence/documents/specs/2026-08-20-distributor-comparison-portfolio-level-design.md`
- Evidence: `08-evidence/documents/plans/2026-08-20-distributor-comparison-portfolio-level.md`
- Evidence: `08-evidence/documents/specs/2026-08-20-index-fund-mega-category-split-deferred.md`
- Evidence: `08-evidence/documents/specs/2026-08-27-analytics-loading-state-mockups.html`
