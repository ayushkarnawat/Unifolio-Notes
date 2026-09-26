# ADR-013: Analytics PDF export renders server-side in a headless browser, authorised by a capability token

Status: Proposed
Date: 2026-08-20
Related: [2026-08-20 journey stage](../02-journey/2026-08-20-analytics-deepening-and-a-deferred-split.md)

## For stakeholders

Users need to take their analytics dashboard away as a document — to a
spreadsheet-free conversation with a spouse, or to an advisor. The chosen
approach renders the real dashboard in a real browser on the server and asks
that browser to produce a PDF, which means the output is genuine selectable,
scalable PDF rather than a picture of a screen, and the formatting logic that
was already built and tested for the live view is reused instead of rebuilt.
The awkward part is authorisation: the server's browser is not the logged-in
user. Rather than give the headless browser the user's credentials, the server
issues a single-use, short-lived ticket that grants access to one specific
export payload and nothing else. The design is complete; the implementation
plan has not been started.

## Technical detail

### Context

The analytics dashboard's formatting, number rules and section layout are
already implemented and tested in React. Its one piece of click-gated content
is the Scorer section's per-fund detail modal. The application holds its bearer
token in browser local storage and uses no cookies anywhere.

### Decision drivers

- Output must be real PDF — selectable text, vector, printable — not a raster
  capture.
- Formatting logic must not be duplicated; a second implementation would drift.
- The export must contain exactly what the user can already see, which also
  keeps one household member's data out of another's document.
- Nothing about the export may widen the application's authentication surface.

### Options considered

#### Option 1: Client-side `window.print()` with print stylesheets

Advantages:
- No server work, no new dependency, no new authorisation problem.
- The user's own session is already authenticated.

Disadvantages:
- Pagination, headers and page breaks are barely controllable across browsers.
- Output quality varies by browser and printer driver.
- Expanding every click-gated detail section before printing is fragile.

#### Option 2: A backend-native PDF template (e.g. WeasyPrint)

Advantages:
- Fully server-controlled output, no browser process to manage.
- Deterministic rendering, easy to test.

Disadvantages:
- Duplicates formatting, number-presentation and section-layout logic that is
  already built and tested in the React view — two implementations to keep in
  step.
- Any dashboard change needs a matching template change or the PDF silently
  goes stale.

#### Option 3: Server-side headless browser rendering the real view

Advantages:
- Reuses the live view verbatim; no second formatting implementation.
- True vector PDF output from the browser's own print pipeline.
- A change to the dashboard is reflected in the export automatically.

Disadvantages:
- Adds a browser automation dependency and a long-lived browser process.
- Needs an authorisation mechanism for a client that is not the user.
- Cold-start latency unless a warm browser instance is kept.

### Decision

Option 3. Render with Playwright's page-to-PDF path, keeping a shared warm
Chromium started from a new FastAPI lifespan hook, and add a
`settings.frontend_base_url` for the server to point the browser at. Two
routes: `POST /analytics/export/pdf`, authenticated as the user's session, and
`GET /analytics/export/payload`, which takes a token in the query string and
deliberately carries **no** current-user dependency — it is a capability, not
a credential. A `playwright` pytest marker mirrors the existing `postgres`
marker so the suite can skip browser-dependent tests.

Cookie-based authentication for the headless browser was considered and
rejected separately from the three options above: the application has no
cookies anywhere, and introducing them for this one feature would reopen a
CSRF surface.

On the frontend, `FundScoreCard` is extracted from the score detail modal so
the same card renders in both the live view and the print view; a
`PrintAnalyticsView` is mounted directly by `main.tsx` on `/print/analytics`,
bypassing the application shell and the auth provider — which is how a
deliberately router-free application serves a second entry point. The download
control is gated on all sections having finished loading.

### Consequences

Positive:
- No new backend data-shape work: the design confirmed the only click-gated
  content in the dashboard is the per-fund score detail, which the print view
  renders expanded by default.
- Export scope mirrors the live view, so cross-member data leakage is
  structurally impossible rather than prevented by a filter.
- The capability token never carries user identity, so a leaked export URL
  exposes one payload, not an account.

Negative:
- A browser process in the API container: memory footprint, a new failure mode,
  and a heavier deployment image.
- The token store is an in-process dictionary — it does not survive a restart
  and does not work across multiple workers. The plan requires this to be
  recorded inline at the point of implementation; tracked as R-039.
- A second frontend entry point outside the app shell is a maintenance
  surface that will not be exercised by normal use.

### Validation

Not yet validated — the implementation plan is entirely unticked. Validation
requires the two routes live, a generated PDF containing selectable text, the
`playwright` marker honoured in CI, and a decision on the token store before
the API runs with more than one worker.

### Evidence

- Design: `08-evidence/documents/specs/2026-08-20-analytics-pdf-export-design.md`
- Plan: `08-evidence/documents/plans/2026-08-20-analytics-pdf-export.md`

## Addendum — 2026-09-22: fully executed, reviewed, and merged, 2026-08-20/21

This ADR's own "Validation" section, as originally written, stated the
implementation plan was entirely unticked. Later-ingested source material
confirms all 10 plan tasks were executed via subagent-driven development,
task-reviewed, and committed. Manual end-to-end verification (Task 10)
found and fixed two real bugs: a print-view fetch effect double-firing
under React 18 Strict Mode, always failing its second call against the
single-use export token; and a per-fund comparison tab/pagination gated
behind client-side click state, invisible to a static PDF render (fixed
with an opt-in `printMode` prop, addressing the exact tension the
"Consequences" section above did not yet have concrete evidence against).
The mandatory whole-branch review found and fixed two further findings
against the spec's own "evict the token regardless of success or failure"
line, plus one further gap where the fix's own exception handling didn't
catch `asyncio.CancelledError`. Merged into `feat/enhanced-ui` as commit
`ed149bf`, both full suites confirmed passing on the merged tree.

A separate, pre-existing backend bug was found during this work and
explicitly ruled out of scope, not fixed here: `category_ranking.py`'s
CAGR calculation raises a division error for an aggregate multi-category
portfolio when a category's NAV history is shorter than the CAGR lookback
window — confirmed to identically affect the live dashboard's own scoring
calls, not introduced by or specific to PDF export. Not yet tracked as its
own numbered risk in this vault; flagged here as a known open follow-up.

The R-039 in-process token-store limitation named in this ADR's original
"Consequences" section is **not resolved** by this addendum — no source
material in this batch shows a persistent, multi-worker-safe token store
being built.

### Addendum evidence

- `08-evidence/documents/engineering-loop/session.md`, "Analytics PDF export: all 10 plan tasks done, reviewed clean, merged to feat/enhanced-ui (2026-08-20/21)" section

## Addendum — 2026-09-23: the mandatory whole-branch review's round-1 findings and rulings, in detail

Supplementary provenance behind the 2026-09-22 addendum above, not a
correction to it. The mandatory final whole-branch review (git range
`321b6ed..4ce4561`, 10 commits) was dispatched to Codex rather than a
Claude subagent, because the session running it was at ~93% of its weekly
Claude usage limit — this repo's model-orchestration convention treats
Codex as the default worker for a bounded, well-specified review task like
this one, not just for implementation. Review round 1 (2026-08-21)
returned "Ready to merge? No" with exactly 3 Important findings, adjudicated
as follows:

1. **Confirmed real, fixed** — `PrintAnalyticsView.tsx`'s success and error
   fetch paths both set the same `data-print-ready="true"` marker, so a
   payload-fetch failure rendered a "successful" 200 PDF of an error page
   instead of the design spec's required 500.
2. **Confirmed real, fixed** — the same root cause meant the export token
   was only ever cleaned up by the frontend's own payload fetch; if the
   browser never reached that fetch (nav failure, timeout, pre-fetch render
   crash), the token sat unswept past its 120-second TTL, contrary to the
   spec's "cleaned up regardless of success or failure."
3. **Ruled NOT a defect** — `FundScoreCard`'s `parseScore` (`parseFloat`/
   `toFixed`) was flagged against the plan's Decimal-safety constraint
   ("byte-for-byte, never parsed to float"). Ruling: that constraint targets
   *accumulation and transport*, not a single non-accumulating final-value
   conversion for display rounding — an exemption `frontend/src/lib/decimal.ts`'s
   own docstring already documents and that predates this plan.
   `FundScoreCard` itself pre-existed this branch (Task 4 only extracted it
   from `FundScoreDetailModal`, logic unchanged) and the live dashboard
   already rendered it this way. Not re-raised in re-review.

Findings 1 and 2 were fixed in a single dispatched round: splitting the
print-ready marker into distinct success/error markers, making the PDF
renderer raise instead of returning a PDF of the error page, and having
the export route explicitly evict the token via `consume_export_payload`
(idempotent) before returning a generic 500. Committed as `d59542e` after
the orchestrator independently confirmed both full suites clean outside
Codex's own sandbox (which had hit an unrelated AnyIO/TestClient hang on
the full backend suite — judged an environment flake, not a regression):
backend 457 passed/3 skipped, frontend 233 passed/0 failed across 59 files.

This addendum does not narrate the subsequent scoped re-review or the
`86c60c5` cancellation-cleanup fix named in the same source handoff's
status line — those aren't detailed in the ingested source material for
this addendum and remain covered only by the 2026-09-22 addendum's
`session.md`-sourced summary above.

### Addendum evidence

- `08-evidence/documents/orchestration/analytics-pdf-export-final-review-handoff.md`

## Addendum — 2026-09-24: a second, post-launch bug round — the Allocation section and its donut chart weren't print-safe either

### For stakeholders

After the PDF export feature above had shipped, a user reported that a
generated PDF's portfolio-allocation section wasn't rendering correctly:
it showed the Category breakdown tab but not the AMC tab, and the donut
chart appeared as a thin, incomplete sliver rather than a full circle.
Root cause was two separate gaps in features this ADR's original design
didn't extend far enough to cover: the allocation section's own
Category/AMC toggle hadn't been given the same "show everything, hide the
interactive toggle" treatment already built for the Benchmark section
(this ADR's Task 10 finding), and the donut chart's slice-by-slice
entrance animation was being captured mid-draw because the PDF-ready
signal fired the instant it appeared, before the animation finished. Both
were fixed by extending the same patterns already used elsewhere in this
feature (a `printMode` prop, and turning the animation off for print
specifically) rather than inventing anything new.

### Technical detail

Two independent causes, found together:

1. `AllocationSection.tsx`'s Category/AMC toggle is driven by local
   `useState` and had never received the `printMode` treatment already
   applied to `BenchmarkSection` (this ADR's original Task 10 finding, "the
   click-gated tab/pagination invisible to static PDF" bug) — so only
   whichever tab was selected client-side at capture time rendered, and
   the AMC tab was invisible in the PDF.
2. `PieSlice.tsx`'s entrance animation (a staggered `motion/react` spring
   per slice) fires the moment the `data-print-ready` marker appears,
   which is before the animation has finished — Playwright's `page.pdf()`
   captured the donut mid-draw, rendering as a thin sliver. `PieSlice`
   already had an unused, instant/static `animate={false}` render path
   from its original build — this bug was that print mode never set it.

Fix: added a `printMode` prop to `AllocationSection` mirroring
`BenchmarkSection`'s existing pattern (hides the toggle, shows both
Category and AMC donuts stacked instead of one at a time), wired into
`PrintAnalyticsView.tsx`; threaded a new `animate` prop through
`AllocationDonut` → `PieSlice`, set `animate={false}` for both donuts in
print mode. New regression tests added (`AllocationDonut.test.tsx`, a new
`AllocationSection.test.tsx`); full frontend suite reported green
(335/335) with a clean `tsc`. No backend change.

This is a distinct, later bug round from the Task 10 fix recorded above in
this ADR (which covered `BenchmarkSection`'s equivalent toggle problem but
not `AllocationSection`'s) — the same bug class recurred because the
`printMode` pattern wasn't applied everywhere it was needed the first time.

### Addendum evidence

- `08-evidence/documents/Notes for the product.md` (the section immediately
  preceding "NEW DISTRIBUTOR ANAYSIS," describing this bug report and fix)
