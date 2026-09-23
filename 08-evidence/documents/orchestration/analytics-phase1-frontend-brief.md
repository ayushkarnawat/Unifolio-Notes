---
artifact: analytics-phase1-frontend-brief
version: "1.0"
created: 2026-08-14
status: for-review
product: Unifolio
audience: A coding agent (Google Antigravity / Gemini) executing Phase 1 of the Analytics Dashboard frontend
---

# Unifolio — Analytics Dashboard Frontend, Phase 1 Brief

**This document is a handoff, not a suggestion. Read it in full before writing any
code, then read every document it points to in Step 0. Do not build from memory of
this brief alone — it compresses those documents; it does not replace them.**

**Phase 1 scope only**: Allocation (FR-1/FR-2), Cost/TER (FR-10/FR-11), Category
Ranking (FR-3/FR-4). **Do not build the Scorer (FR-5–FR-7) or Benchmark Comparison
(FR-8/FR-9)** — those are Phase 2, briefed separately in
`Docs/orchestration/analytics-phase2-frontend-brief.md`, not yet dispatched. If your
Analytics screen shell has room for a "coming next" placeholder for those two
sections, that's fine; do not implement their logic or call their endpoints.

## 0. Read these first, in this order

1. `Docs/superpowers/specs/2026-08-14-analytics-frontend-design.md` — the design
   decisions specific to this build: the two-phase split, the Bklit UI charting
   decision and its one carve-out (allocation reuses the existing donut, doesn't
   move to Bklit), the component reuse inventory, and why this is built externally
   rather than by Claude Code/Codex.
2. `Docs/PRDs/Design-Brief-Unifolio-updated.md` — the *why*: brand principles, color
   discipline, typography, motion principles, voice & tone, accessibility baseline.
   Read the `-updated.md` file, not `Design-Brief-Unifolio.md` (1.0, superseded).
3. `Docs/PRDs/Design-Schema-Unifolio.md` — the *exact system*: color tokens, type
   scale, spacing, every component spec (Badge, Charts, Scorer Display — Scorer is
   Phase 2 but read it now for full context), motion tokens, dark/light mode rule,
   accessibility checklist.
4. `Docs/PRD-04-MF-Analytics-Dashboard.md` — full functional requirements. Phase 1
   only needs FR-1, FR-2, FR-3, FR-4, FR-10, FR-11 plus their edge cases; the rest
   (FR-5–FR-9) is Phase 2, read for context only.
5. `CLAUDE.md` (repo root) — project-wide non-negotiables and Session State.
6. `session.md` (repo root) — full working-notes history.
7. `Docs/PRDs/App-Flow-Unifolio.md` — screens S18 (per-member Analytics) and S19
   (family aggregate Analytics); Phase 1 builds these two screens with a
   three-section scope (Allocation, TER, Category Ranking), not the full five
   sections S18/S19 eventually have.
8. `Docs/MOBILE_APP_EXECUTION.md` — mobile-specific rules (mobile lives under
   `frontend/src/mobile/`, mobile-first, 44px touch targets, no viewport-based
   auto-replacement of the mobile preview, validate at 320/375/430px).
9. `Docs/frontend_execution.md` — the general redesign execution contract already
   governing this branch; Section 6's "Analytics is out of scope" gate is satisfied
   as of this brief (backend complete, explicitly brought into scope) — read the
   rest of the document for the general component/styling conventions already in
   force product-wide.

Everything below compresses those documents plus the real, already-built,
already-tested backend API surface (357 backend tests passing) — cite the source
documents for anything this brief seems to contradict or under-specify, don't guess.

## 1. Why this brief exists, and why an external agent

PRD-04's backend (Allocation, Category Ranking, Cost/TER — the Phase 1 subset, plus
Phase 2's Scorer and Benchmark Comparison, already built but out of scope here) is
complete and tested. `frontend/src/features/analytics/` is currently a single
`.gitkeep` — nothing built. Meanwhile a colleague has substantially revamped the
rest of the app's frontend (shadcn/Tailwind foundation, mobile app shell, Radix
`Select` componentry, a CAS import lifecycle redesign) on this same branch
(`feat/enhanced-ui`) — verified: 190/190 frontend tests passing across 49 files,
`tsc -b --noEmit` clean. This brief's job is to bring the Analytics Dashboard to
that same visual/interaction standard, matching it exactly rather than introducing
a third visual language into the product.

This build is being handed to an external coding agent (you) rather than built by
Claude Code or delegated through this project's Codex-based `model-orchestration`
skill, by explicit product-owner decision. Claude Code's role after you finish is
purely to test, review, and compare your output against this brief and the Design
Schema — not to have built it first. Section 10 tells you exactly what to hand back
so that review can happen without Claude Code re-deriving your work from a diff.

## 2. Non-negotiable guardrails

- **Stack is locked**: React 19 + Vite, TypeScript, Tailwind CSS + CSS custom
  properties (see `frontend/src/index.css`), shadcn/Radix component primitives
  under `frontend/src/components/ui/`. No Next.js, no framework swap, no CSS-in-JS
  runtime library. You **may** add Bklit UI chart components (Section 8) — this is
  expected, not optional latitude.
- **Do not modify backend code.** `backend/` is complete, tested, and merged. This
  brief is frontend only. If you discover the frontend needs a backend change (a
  new field, a new endpoint, a shape mismatch) — **stop and report it in your
  completion report (Section 10), do not implement it.**
- **Never treat a money/units/NAV/percentage value as a JS number for
  calculation.** Every such value arrives from the API as a **string** (backend
  `Decimal`, JSON-serialized as `str` — see every schema in Section 6). Parse only
  for *display formatting* or for feeding a chart's plotting/axis props (Bklit
  chart components take numeric props for rendering position) — never for
  arithmetic whose *result* is displayed as if it were exact. If a screen needs a
  derived number the API doesn't already provide, that's a backend gap to report
  (previous bullet), not something to compute client-side with floats.
- **Preserve existing test coverage.** Run `npm test` and `npx tsc -b --noEmit` in
  `frontend/` before and after your changes. All existing tests must still pass
  unless a specific, documented reason a *behavior* (not just presentation)
  changed — list any such change explicitly in Section 10's report.
- **Work in an isolated branch off `feat/enhanced-ui`**, not directly on `main` or
  `feat/enhanced-ui` itself. Do not push to `origin` or open a PR without the
  product owner's explicit go-ahead.
- **Do not touch `frontend/src/components/AllocationDonut.tsx`.** Reuse it exactly
  as it is for Phase 1's allocation view (Section 3's carve-out) — do not rebuild
  it in Bklit, do not refactor its internals "while you're in there."
- **Do not build Phase 2 sections** (Scorer, Benchmark Comparison) or call their
  endpoints (`/analytics/.../benchmark*`, `/analytics/.../score`,
  `/analytics/funds/{scheme_id}/score`) — out of scope per this brief's header.

## 3. Design foundation — the compressed version

Full detail is in Section 0's documents; this section exists so you don't have to
cross-reference constantly, but it is a **compression** — when in doubt, the source
document wins.

### 3.1 Visual language — match the existing revamp exactly

Colors: Ink `#111111`, near-white `#FCFCFC`, accent green `#22C55E` (sparing use —
one primary action per screen, never a large fill). Typography: DM Sans
(headings/display numbers), Manrope (body, including all tabular data),
`font-feature-settings: "tnum"` mandatory on every data value. All styling flows
through Tailwind classes plus the CSS custom properties already declared in
`frontend/src/index.css` (`var(--color-bg)`, `var(--color-ink)`,
`var(--color-surface)`, `var(--color-border)`, `var(--color-accent)`,
`var(--color-positive)`, `var(--color-negative)`, `var(--color-warning)`,
`var(--color-text-secondary)`, `var(--color-neutral-badge)`) — do not invent new
color tokens; if Analytics needs a color the existing token set doesn't cover,
report it (Section 10), don't hardcode a hex value.

Match `frontend/src/features/dashboard/DashboardView.tsx`'s composition
conventions directly — read that file before building anything:
- Card convention: `rounded-xl border border-[var(--color-border)] shadow-2xs
  bg-[var(--color-surface)]`.
- `type-display` / `type-data-large` / tabular-nums for hero and standalone
  numbers.
- `formatIndianCurrency` (`Intl.NumberFormat("en-IN")`) for all currency display.
- `sumDecimalStrings` (from `frontend/src/lib/decimal`) for any client-side summing
  of decimal-string values before display — never `parseFloat` + `+`.
- The aggregate/per-member `viewMode` segmented switcher already built into
  `NavigationShell.tsx` — reuse it as the Analytics screen's own toggle
  mechanism, don't build a second one.

### 3.2 Chart library — Bklit UI, with one carve-out

`frontend/components.json` already has the Bklit registry configured:
```json
"registries": { "@bklit": "https://ui.bklit.com/r/{name}.json" }
```
Install components via `npx shadcn@latest add @bklit/<component-name>` (this is a
shadcn registry component, not an npm package — it drops source into
`frontend/src/components/ui/` like any other shadcn component, fully editable
afterward). **Confirm the exact component names against the live registry before
using this table** — treat these as your starting point, not guaranteed-correct
final names:

| Data (Phase 1) | Suggested Bklit component |
|---|---|
| Direct vs. Regular weighted TER comparison | `@bklit/bar-chart` |
| Category percentile position (one fund's rank within its category) | `@bklit/bar-chart` (horizontal) or `@bklit/gauge-chart` if the registry has one — your call, whichever reads more clearly as "where does this fund sit in its category" |

**Carve-out — do not use Bklit for allocation.** The Design Brief has an existing,
locked rule: one consistent donut/bar convention for allocation views product-wide,
not different chart types per screen for the same kind of data
(`Design-Schema-Unifolio.md` §Charts). The Main Dashboard's `AllocationDonut`
already is that convention, and its prop shape
(`{ label, current_value, percentage }[]`) is structurally identical to what the
Analytics allocation endpoints return (`AllocationBucket[]`, Section 6) — so
Phase 1's allocation view **imports and reuses `AllocationDonut` unchanged**. This
was an explicit product-owner decision (see the design spec, Section 3) — not an
open question.

### 3.3 Motion

`motion-fast` (150ms, hover/focus), `motion-reveal` (400ms, data reveals — use this
for chart entrance/fill and section reveal on load), `motion-page` (300ms, section/
screen transitions). All three already collapse to instant under
`prefers-reduced-motion: reduce` — verify this actually holds for whatever
animation Bklit's chart components do internally too (some chart libraries animate
regardless of this media query by default; if Bklit's charts don't respect it
out of the box, wrap/configure them so they do — don't ship a chart that ignores
the user's reduced-motion preference).

## 4. Screen inventory & scope

| Screen | Name | Current state | Phase 1 job |
|---|---|---|---|
| S18 | Analytics Dashboard (per-member) | `.gitkeep` only | Build: Allocation + TER + Category Ranking sections, per-member data |
| S19 | Analytics Dashboard (family aggregate) | `.gitkeep` only | Build: same three sections, aggregate data + per-member `MemberStatus[]` placeholder handling |
| Nav | "Analytics" nav item in `NavigationShell.tsx` | Disabled, "Soon" badge, stale tooltip | Enable it — remove the `disabled`/tooltip, wire it to the new Analytics screen, following the same click-to-switch pattern as the existing "Dashboard" nav button |
| Mobile Analytics | New — matches `MobileDashboardView.tsx`'s pattern | Doesn't exist | Build `frontend/src/mobile/features/analytics/MobileAnalyticsView.tsx` — same three sections, same API client, mobile-first layout per `MOBILE_APP_EXECUTION.md` |
| S20 (Fund Score Detail) | N/A | Out of scope | Phase 2 — do not build |

## 5. Component library

- **Reused, do not modify**: `AllocationDonut` (Section 3.2), `Badge` (variants:
  `warning` for `category_unavailable`/`insufficient_history`/`thin_category`
  flags, `neutral` for anything unclassified), `Card`, `Tabs`, `Select`, `Tooltip`,
  `Skeleton`, `Table` (all under `frontend/src/components/ui/`), `NavigationShell`,
  the aggregate/per-member `viewMode` switcher pattern.
- **New**:
  - `frontend/src/features/analytics/AnalyticsView.tsx` — screen shell, mirrors
    `DashboardView.tsx`'s composition pattern (hero/header + section cards +
    viewMode switcher).
  - `frontend/src/features/analytics/api.ts` — API client, mirrors
    `frontend/src/features/dashboard/api.ts`'s `authFetch` pattern exactly (same
    file structure: one function per route, named `getMember<Thing>` /
    `getAggregate<Thing>`).
  - `frontend/src/features/analytics/types.ts` — TypeScript types matching
    Section 6's schemas exactly (field-for-field, including which fields are
    nullable).
  - `frontend/src/features/analytics/AllocationSection.tsx` — wraps
    `AllocationDonut`, tabbed or side-by-side `by_category`/`by_amc` (your call
    on layout; `DashboardView.tsx`'s existing tab pattern is a reasonable
    precedent).
  - `frontend/src/features/analytics/TerSection.tsx` — weighted TER stat display
    (reuse the existing stat-tile/hero-number visual language) plus the
    Direct-vs-Regular Bklit bar chart. Handle `weighted_ter: null` (no coverage) and
    a non-empty `uncovered_schemes` list per PRD-04's edge cases — this must be
    visually distinguishable from "TER is exactly zero," never silently omitted.
  - `frontend/src/features/analytics/CategoryRankingSection.tsx` — a row per held
    fund showing `scheme_name`, `sebi_category`, percentile/rank visualization
    (Bklit chart per Section 3.2), and `category_avg_return` for comparison. Rows
    with `category_unavailable`, `insufficient_history`, or `thin_category` true
    get the appropriate `Badge` and a materially different (not just re-labeled)
    treatment — e.g. no percentile bar rendered at all if `percentile` is `null`,
    per PRD-04's edge cases table.
  - `frontend/src/mobile/features/analytics/MobileAnalyticsView.tsx` — mobile
    composition of the same three sections, following
    `MobileDashboardView.tsx`'s "shared data/API, different layout" convention.

Every component: verify in both light and dark mode, verify keyboard-focus states,
before considering it done (Design Schema's explicit rule).

## 6. Backend context — the real, exact API surface (Phase 1 routes only)

Base URL: `import.meta.env.VITE_API_BASE_URL` (see `frontend/src/lib/apiClient.ts`),
defaults to `http://localhost:8000`. Router prefix: `/analytics`. Auth: Bearer
token in `Authorization` header (same session token the rest of the app already
uses — see `frontend/src/features/auth/session.ts`'s `getToken()`). All routes
require it and 404 if `member_id` doesn't exist or isn't owned by the caller.

All money/percentage/TER fields are **strings** (`Decimal`-serialized), exactly
like every other API response in this app — never parse-and-recompute, only
parse-to-display or parse-for-chart-plotting.

### Allocation (FR-1/FR-2)

| Method | Path | Response model | Shape |
|---|---|---|---|
| GET | `/analytics/household-members/{member_id}/allocation` | `AnalyticsAllocationSummary` | `{ by_category: AllocationBucket[], by_amc: AllocationBucket[], total_value: str }` |
| GET | `/analytics/household/aggregate/allocation` | `AggregateAnalyticsAllocationResponse` | `{ members: MemberStatus[], allocation: AnalyticsAllocationSummary }` |

`AllocationBucket` = `{ label: str, current_value: str, percentage: str }` — same
shape as the Main Dashboard's existing allocation buckets, which is exactly why
`AllocationDonut` (built against that shape) is reused unchanged.

### Cost / TER (FR-10/FR-11)

| Method | Path | Response model | Shape |
|---|---|---|---|
| GET | `/analytics/household-members/{member_id}/ter` | `WeightedTerSummary` | see below |
| GET | `/analytics/household/aggregate/ter` | `AggregateWeightedTerResponse` | `{ members: MemberStatus[], ter: WeightedTerSummary }` |
| GET | `/analytics/household-members/{member_id}/ter/direct-regular` | `DirectRegularTerComparison` | `{ direct: WeightedTerSummary, regular: WeightedTerSummary }` |
| GET | `/analytics/household/aggregate/ter/direct-regular` | `AggregateDirectRegularTerResponse` | `{ members: MemberStatus[], ter: DirectRegularTerComparison }` |

`WeightedTerSummary` = `{ weighted_ter: str | null, covered_value: str,
total_value: str, reference_period: date | null, uncovered_schemes: str[] }`.
`weighted_ter: null` means no coverage at all (not zero) — render this as an
explicit "not available" state, never as "0.00%". `uncovered_schemes` (a list of
scheme names/ids) must be surfaced somewhere in the UI when non-empty, not
silently dropped — this is the mechanism by which a user learns "your TER number
excludes these N funds."

### Category Ranking (FR-3/FR-4)

| Method | Path | Response model | Shape |
|---|---|---|---|
| GET | `/analytics/household-members/{member_id}/category-ranking` | `CategoryRankingSummary` | `{ funds: CategoryRankRow[] }` |
| GET | `/analytics/household/aggregate/category-ranking` | `AggregateCategoryRankingResponse` | `{ members: MemberStatus[], ranking: CategoryRankingSummary }` |

`CategoryRankRow` = `{ scheme_id: str, scheme_name: str, sebi_category: str |
null, category_unavailable: bool, insufficient_history: bool, scheme_return: str |
null, category_rank: int | null, category_size: int, percentile: str | null,
category_avg_return: str | null, thin_category: bool }`. When
`category_unavailable` or `insufficient_history` is `true`, `scheme_return`,
`category_rank`, and `percentile` will be `null` — the row must render a Badge and
an explanatory short label instead of a blank/zero value in those cells.

`MemberStatus` (shared with the Main Dashboard, from
`app/services/dashboard/schemas.py`) — check its exact fields directly in that file
before use; the aggregate responses' `members` array follows the same
present-but-`has_data: false` placeholder convention as the Main Dashboard's own
aggregate endpoints (a member with no data is still listed, contributes nothing to
totals, never silently excluded).

## 7. Motion & UX quality bar

Follow the same discipline already applied to the rest of this app's revamp:

1. Dashboard/Analytics section load: staggered reveal (`motion-reveal`), not an
   instant paint — including chart entrance.
2. Screen/section transitions: `motion-page`.
3. Hover/focus micro-interactions: `motion-fast`.
4. `prefers-reduced-motion: reduce`: every reveal (including Bklit's own chart
   animations) collapses to instant final-state rendering — verify by actually
   toggling the OS/browser setting, not by trusting the CSS alone.
5. If the `impeccable` skill is available in your environment, use its
   shape → critique → audit → polish workflow as your own build-verification loop
   (invoke it via its typed command if your harness supports one, plain language
   otherwise) — target Good band or better (≥28/40) on both S18 and S19 before
   calling Phase 1 done. This is the same bar the rest of this app's revamp was
   held to.
6. Accessibility checklist (Design Schema, verbatim — a gate, not a wishlist):
   - [ ] Every `color-positive`/`color-negative` usage paired with an icon or label
   - [ ] All text/background pairs meet WCAG AA in both light and dark mode
   - [ ] Keyboard focus states defined for every interactive component
   - [ ] `prefers-reduced-motion` respected on every motion token and chart animation
   - [ ] Tabular figures confirmed on every numeric value

## 8. Adding dependencies

- **Bklit UI chart components** (Section 3.2): install only the specific
  components you actually use (`npx shadcn@latest add @bklit/bar-chart`, etc.) —
  don't bulk-install the full catalog. Bklit is built on Visx under the hood (same
  rendering engine as the existing `AllocationDonut`'s custom pie primitives at a
  lower level, even though Bklit's own composable API is different) — if you hit
  a peer-dependency conflict with the already-installed `@visx/*` packages, resolve
  it by version-aligning rather than removing either.
- No other new dependencies should be necessary for Phase 1 — if you find you
  need one, justify it in your completion report (Section 10).

## 9. Testing this locally as you build

```bash
# Terminal 1 — backend
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install   # after adding Bklit components
npm run dev
```

Sign in with a household that already has a completed CAS import (needed to see
real allocation/TER/category-ranking data — an empty portfolio will only exercise
your empty-state handling, not the real charts). Run the suite after every
meaningful change:

```bash
cd frontend
npm test              # vitest run — all existing tests must stay green (190/190 at time of writing)
npx tsc -b --noEmit    # must stay clean
```

## 10. Completion report — what you must hand back

At the end of Phase 1, produce a report (append it to
`Docs/orchestration/analytics-phase1-frontend-log.md`, which exists as a skeleton
file for exactly this purpose — see its own header for the expected format)
covering, at minimum:

- Every file created or modified, grouped by new-vs-modified.
- Every new dependency added (Bklit components and anything else) and why.
- Final `npm test` and `npx tsc -b --noEmit` output/status.
- `impeccable critique` scores achieved per screen (S18, S19, mobile), if the
  skill was available in your environment — if not available, say so explicitly
  rather than silently skipping the quality-bar step.
- Any backend gap found and *not* implemented (Section 2's guardrail) — exact
  field/endpoint, why it's needed, what you did instead (if anything) to work
  around it in the meantime.
- Any deviation from this brief's component/screen scope, with reasoning.
- Any open design question you couldn't resolve from the source documents.
- Confirmation of the `AllocationDonut` reuse (Section 3.2's carve-out) — state
  explicitly that it was not modified.

Also update, per this repo's established convention (a fresh session needs to
know what happened without re-deriving it from a diff):

- **`session.md`** (repo root): a new dated section, following the exact style of
  existing entries, explicitly noting **which agent did this work** ("built via
  Google Antigravity, not Claude Code") so a future Claude Code session treats it
  as external, already-integrated work.
- **`CLAUDE.md`**'s Session State section: the condensed pointer version, updating
  the "Updated <date>" line, following the existing entries' exact style.
- **`Docs/orchestration/delegation-log.md`**: do not edit this yourself — it's
  Claude Code's own dispatch ledger and Claude Code will add the corresponding
  entry when it reviews your work. Leave it alone.

## 11. What "done" looks like

- S18 and S19 exist, function against the real Phase 1 backend routes (Section 6),
  and pass `impeccable critique` at Good band or better (or the quality-bar step
  is explicitly reported as skipped-for-lack-of-tooling, not silently skipped).
- Mobile Analytics view exists and matches `MobileDashboardView.tsx`'s pattern.
- The Analytics nav item is enabled and routes correctly.
- `AllocationDonut` untouched; Bklit UI used for TER and Category Ranking charts.
- `npm test` and `npx tsc -b --noEmit` both clean.
- Both light and dark mode verified for every new/changed component.
- Every accessibility checklist item (Section 7) checked, not assumed.
- `session.md` and `CLAUDE.md` updated per Section 10.
- No backend files touched. No Phase 2 (Scorer/Benchmark) code written.
- `Docs/orchestration/analytics-phase1-frontend-log.md` filled in per Section 10.
- Work sits on its own branch, not merged to `feat/enhanced-ui` or `main` — the
  product owner and Claude Code review before integration.

## 12. Assumptions made while writing this brief — flag if wrong

- Allocation/TER/Category Ranking layout within S18/S19 (stacked sections vs.
  tabs) is left to your judgment — no source document mandates one; follow
  whatever `DashboardView.tsx` already establishes as this app's convention for
  multi-section screens.
- The exact Bklit component names in Section 3.2's table are best-effort, not
  verified against the live registry from this environment — confirm against
  `https://ui.bklit.com/r/{name}.json` or the registry's own listing before use.
- `MemberStatus`'s exact fields weren't re-verified in this brief (only that the
  aggregate `members` array convention matches the Main Dashboard's) — read
  `app/services/dashboard/schemas.py` directly for its exact shape.

---

## Ready-to-paste prompt

> Read `Docs/orchestration/analytics-phase1-frontend-brief.md` in full. It is your
> complete brief for this task — it tells you which documents to read first and in
> what order (Section 0), starting with
> `Docs/superpowers/specs/2026-08-14-analytics-frontend-design.md`. Follow the
> brief's guardrails, screen inventory, component list, backend API contract
> (Section 6), and motion/accessibility requirements exactly. This is **Phase 1
> only** — Allocation, Cost/TER, and Category Ranking. Do not build the Scorer or
> Benchmark Comparison (Phase 2, briefed separately, not yet dispatched). Reuse
> `AllocationDonut` unchanged for the allocation view; use Bklit UI
> (`npx shadcn@latest add @bklit/<name>`, registry already configured in
> `components.json`) for the TER and Category Ranking charts. Work on a new git
> branch off `feat/enhanced-ui`, never on `main` directly, and never modify
> anything under `backend/`. If the `impeccable` skill is available in your
> environment, use its shape/critique/audit/polish workflow as your own
> build-verification loop per the brief's Section 7, targeting a Good-band score or
> better on both S18 and S19. When you're finished, append your completion report
> to `Docs/orchestration/analytics-phase1-frontend-log.md` and update `session.md`
> and `CLAUDE.md`'s Session State section, per the brief's Section 10 — that update
> is part of the deliverable, not an afterthought.
