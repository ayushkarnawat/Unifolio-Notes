---
artifact: analytics-phase2-frontend-brief
version: "1.0"
created: 2026-08-14
status: for-review
product: Unifolio
audience: A coding agent (Google Antigravity / Gemini) executing Phase 2 of the Analytics Dashboard frontend
---

# Unifolio — Analytics Dashboard Frontend, Phase 2 Brief

**This document is a handoff, not a suggestion. Read it in full before writing any
code, then read every document it points to in Step 0.**

**Dependency: Phase 1 must already be merged into whatever branch you build
this on.** Phase 2 extends the same S18/S19 screen shell Phase 1 built
(`frontend/src/features/analytics/AnalyticsView.tsx`, `.../MobileAnalyticsView.tsx`)
with two more sections — it does not create a new screen. If Phase 1's work isn't
present in your starting branch, stop and say so rather than rebuilding the
Allocation/TER/Category Ranking shell from this brief's description of it.

**Phase 2 scope**: Fund & Portfolio Scorer (FR-5/FR-5a/FR-5b/FR-6/FR-7), Benchmark
Comparison (FR-8/FR-9), and the Fund Score Detail screen (S20).

## 0. Read these first, in this order

1. `Docs/superpowers/specs/2026-08-14-analytics-frontend-design.md` — the design
   decisions for this whole build (both phases): Bklit UI adoption and its
   allocation carve-out, component reuse inventory, external-agent build approach.
2. `Docs/orchestration/analytics-phase1-frontend-brief.md` — Phase 1's brief. Read
   this even though you're not building Phase 1 — it establishes the screen shell,
   API client pattern, and component conventions you're extending, and its
   completion log (`analytics-phase1-frontend-log.md`) will tell you what actually
   shipped vs. what was planned.
3. `Docs/PRDs/Design-Brief-Unifolio-updated.md` — brand principles, color
   discipline, typography, motion, voice & tone, accessibility baseline.
4. `Docs/PRDs/Design-Schema-Unifolio.md` — exact component specs. **Read the
   Scorer Display and Charts (grouped bar) sections closely** — this is the part
   of the Design Schema Phase 1 didn't need.
5. `Docs/PRD-04-MF-Analytics-Dashboard.md` — FR-5 through FR-9, including the
   Scorer's tier/percentile methodology and the benchmark-comparison edge cases.
6. `Docs/Scorer-Methodology-Unifolio.md` — the stakeholder-facing plain-language
   explanation of the Scorer's methodology (45% Return / 30% downside-only Risk /
   25% rolling-12-month category-beat Consistency). **Read this before designing
   the Scorer UI** — the breakdown you show the user should map onto this
   methodology's own vocabulary, not invent new terminology for the same concepts.
7. `CLAUDE.md` and `session.md` (repo root) — non-negotiables and full history,
   including the Scorer's own backend build notes (three adversarial-review
   findings fixed — worth knowing the shape of the data this UI is displaying was
   itself scrutinized for correctness).
8. `Docs/PRDs/App-Flow-Unifolio.md` — S20 (Fund Score Detail), reached by tapping
   a fund's score from S18/S19's Scorer section.
9. `Docs/MOBILE_APP_EXECUTION.md` — mobile rules, same as Phase 1.

## 1. Why this brief exists

Phase 1 (Allocation, TER, Category Ranking) shipped the Analytics screen shell.
Phase 2 completes PRD-04's frontend with the two remaining, higher-design-risk
areas: the Scorer has no existing UI precedent anywhere in this app (nothing else
in the product shows a composite score), and Benchmark Comparison needs a new
chart type (grouped bars) that Phase 1 didn't require. Same external-build
approach as Phase 1 (Section 1 of that brief) — Claude Code reviews/tests after
you're done, it does not build this itself.

## 2. Non-negotiable guardrails

Identical to Phase 1's Section 2 — repeated here since this may be a different
build session:

- Stack locked (React 19 + Vite, TypeScript, Tailwind + CSS custom properties,
  shadcn/Radix primitives). You may add Bklit UI chart components.
- Do not modify backend code — report gaps in Section 10, don't implement them.
- Never treat money/percentage/score values as JS numbers for calculation — every
  such field is a `Decimal`-serialized string; parse only for display or chart
  plotting.
- Preserve existing test coverage — `npm test` and `npx tsc -b --noEmit` clean
  before and after.
- Work on an isolated branch, no push/PR without explicit go-ahead.
- Do not touch `AllocationDonut.tsx` or re-litigate Phase 1's allocation
  implementation.
- **Never display `final_score` (or any score/percentile) as a bare number with
  no context** — this is a hard requirement from both PRD-04 FR-7 and the Design
  Schema's Scorer Display spec, not a style preference. Every score needs its
  tier/breakdown visible or one tap away.

## 3. Design foundation — the compressed version

### 3.1 Scorer Display

Per Design Schema: the score is shown with its **tier** (a visual band — e.g. a
short horizontal band across the percentile range, not a bare star count implying
false universality) plus an **expandable "why this score" breakdown** showing the
risk-adjusted-return tier and cost adjustment as separate, labeled lines. Map this
directly onto the real backend fields (Section 6):

- `final_score` — the headline number, shown with tier coloring (Bklit gauge/ring,
  Section 3.3), never alone.
- `risk_adjusted_tier` (1–5) — the tier band itself.
- `return_percentile`, `risk_percentile`, `consistency_hit_rate` — the three
  breakdown lines, one per `Scorer-Methodology-Unifolio.md`'s three weighted
  components (Return 45%, Risk 30%, Consistency 25%) — label them using that
  document's own terms, not generic labels.
- `cost_adjustment` — a fourth, smaller-weight breakdown line (TER's effect on the
  score) — make clear this is an adjustment, not one of the three primary
  components.
- `category_unavailable` / `insufficient_history` / `thin_category` — when any is
  `true`, `final_score` and the percentile fields will be `null`. Render the
  Badge + an explanation, never a blank space where a score would be.

**Portfolio roll-up** (`PortfolioScoreSummary.weighted_score`): same treatment as
Cost/TER's `weighted_ter` in Phase 1 — a hero stat, with `uncovered_schemes`
surfaced when non-empty (funds that couldn't be scored, e.g. missing category
data), never silently dropped from the weighting.

### 3.2 Benchmark Comparison

Per Design Schema: grouped bar chart (user's fund vs. its benchmark), absolute
return labeled above each bar. Two distinct views, both backed by real data
(Section 6):

- **Portfolio-level** (`PortfolioBenchmarkSummary`): one group — portfolio XIRR vs.
  all 4 Nifty indices (Nifty 50, Nifty 500, Nifty Largemidcap 250, Nifty Midcap
  150) side by side. This answers "how did my whole portfolio do vs. the market
  broadly," not fund-by-fund.
- **Fund-level** (`FundVsBenchmarkSummary`): one group per held fund, each group
  showing that fund's XIRR against *its own appropriate* benchmark index (a
  large-cap fund vs. Nifty 50, a midcap fund vs. Nifty Midcap 150 — not the same
  index for every fund, per FR-9). Also carries `overall_portfolio_xirr` and
  `overall_broad_market_xirr` as a summary line above the per-fund groups.

Any `xirr` field (`fund_xirr`, `benchmark_xirr`, `portfolio_xirr`) can be `null` —
insufficient transaction history for a meaningful XIRR calculation. Render that
bar/group as explicitly "not enough history yet," not as a zero-height bar (a
zero-height bar reads as "0% return," which is a materially different, misleading
claim).

### 3.3 Chart library — Bklit UI

Same registry as Phase 1 (`components.json` already configured). Suggested
components — confirm exact names against the live registry before using:

| Data | Suggested Bklit component |
|---|---|
| Portfolio vs. 4 indices | `@bklit/bar-chart` (grouped) |
| Per-fund vs. appropriate benchmark | `@bklit/bar-chart` (grouped, one group per fund — consider pagination/scroll if the household holds many funds, don't render an unbounded-width chart) |
| Scorer `final_score` with tier coloring | `@bklit/gauge-chart` or `@bklit/ring-chart`, whichever the live registry offers and reads more clearly as "a score out of some maximum with a tier band," not a generic percentage ring |

No carve-out here — unlike allocation, neither Benchmark Comparison nor the Scorer
has an existing product convention to stay consistent with, so Bklit is used
without qualification for both.

### 3.4 Fund Score Detail (S20)

Reached by tapping a fund's score row in the Scorer section. Build as a **modal**,
consistent with the existing `FundDetailModal` precedent in
`DashboardView.tsx` (tap-a-row → modal is this app's established pattern for
"drill into one fund without a full context switch"), not a new full-screen route.
Content: the same breakdown as the inline Scorer section (Section 3.1) at full
detail/size, plus anything `FundScoreRow` carries that the compact inline view
doesn't have room for.

## 4. Screen inventory & scope

| Screen | Name | Current state (after Phase 1) | Phase 2 job |
|---|---|---|---|
| S18 | Analytics Dashboard (per-member) | Allocation + TER + Category Ranking sections exist | Add: Scorer + Benchmark Comparison sections |
| S19 | Analytics Dashboard (family aggregate) | Same, aggregate | Add: same two sections, aggregate data |
| S20 | Fund Score Detail | Doesn't exist | Build fresh — modal, per Section 3.4 |
| Mobile Analytics | `MobileAnalyticsView.tsx` exists with 3 sections | Add: Scorer + Benchmark sections, same mobile-first treatment |

## 5. Component library

- **Reused, do not modify**: everything Phase 1 built or reused (Section 5 of
  that brief), plus the existing `FundDetailModal` composition pattern (as
  precedent for S20's structure, not literally reused — Fund Score Detail shows
  different data).
- **New**:
  - `frontend/src/features/analytics/ScorerSection.tsx` — per-fund score rows +
    portfolio roll-up hero stat, per Section 3.1.
  - `frontend/src/features/analytics/BenchmarkSection.tsx` — both grouped-bar
    views, per Section 3.2.
  - `frontend/src/features/analytics/FundScoreDetailModal.tsx` — S20, per
    Section 3.4.
  - Extend `frontend/src/features/analytics/api.ts` / `types.ts` with the six
    Phase 2 routes (Section 6) — same `authFetch` pattern as the existing four.
  - Extend `frontend/src/mobile/features/analytics/MobileAnalyticsView.tsx` with
    the two new sections.

## 6. Backend context — the real, exact API surface (Phase 2 routes only)

Same base URL, prefix (`/analytics`), and Bearer-auth convention as Phase 1
(see that brief's Section 6). All money/percentage/score fields are strings.

### Fund & Portfolio Scorer (FR-5/FR-6/FR-7)

| Method | Path | Response model | Shape |
|---|---|---|---|
| GET | `/analytics/funds/{scheme_id}/score` | `FundScoreRow` | see below |
| GET | `/analytics/household-members/{member_id}/score` | `PortfolioScoreSummary` | `{ funds: FundScoreRow[], weighted_score: str \| null, covered_value: str, total_value: str, uncovered_schemes: str[] }` |
| GET | `/analytics/household/aggregate/score` | `AggregatePortfolioScoreResponse` | `{ members: MemberStatus[], score: PortfolioScoreSummary }` |

`FundScoreRow` = `{ scheme_id: str, scheme_name: str, category_unavailable: bool,
insufficient_history: bool, thin_category: bool, risk_adjusted_tier: int | null,
cost_adjustment: str | null, final_score: str | null, return_percentile: str |
null, risk_percentile: str | null, consistency_hit_rate: str | null }`.

### Benchmark Comparison (FR-8/FR-9)

| Method | Path | Response model | Shape |
|---|---|---|---|
| GET | `/analytics/household-members/{member_id}/benchmark` | `PortfolioBenchmarkSummary` | `{ portfolio_xirr: str \| null, benchmarks: IndexXirrRow[] }` |
| GET | `/analytics/household/aggregate/benchmark` | `AggregatePortfolioBenchmarkResponse` | `{ members: MemberStatus[], benchmark: PortfolioBenchmarkSummary }` |
| GET | `/analytics/household-members/{member_id}/benchmark/funds` | `FundVsBenchmarkSummary` | `{ funds: FundBenchmarkRow[], overall_portfolio_xirr: str \| null, overall_broad_market_xirr: str \| null }` |
| GET | `/analytics/household/aggregate/benchmark/funds` | `AggregateFundVsBenchmarkResponse` | `{ members: MemberStatus[], comparison: FundVsBenchmarkSummary }` |

`IndexXirrRow` = `{ index: BenchmarkIndex, xirr: str | null }`.
`BenchmarkIndex` enum values: `"nifty_50"`, `"nifty_500"`,
`"nifty_largemidcap_250"`, `"nifty_midcap_150"` — map these to human-readable
labels ("Nifty 50", "Nifty 500", "Nifty Largemidcap 250", "Nifty Midcap 150") in
the frontend, don't display the raw enum string.
`FundBenchmarkRow` = `{ scheme_id: str, scheme_name: str, benchmark_index:
BenchmarkIndex, fund_xirr: str | null, benchmark_xirr: str | null }`.

## 7. Motion & UX quality bar

Same as Phase 1's Section 7 — staggered reveal on load, `motion-page` on
section/modal transitions, `motion-fast` on hover/focus, `prefers-reduced-motion`
respected including chart animations, `impeccable` shape/critique/audit/polish
workflow targeting Good band (≥28/40) if available, and the same accessibility
checklist. One addition specific to Phase 2: the Scorer's tier/gauge visual is
this app's *second* genuinely novel data-visualization component (after Phase 1's
category-percentile chart) — budget real iteration on whether it reads clearly at
a glance before considering it done, the same caution the original frontend
redesign brief gave the Fund Signal component.

## 8. Adding dependencies

Same guidance as Phase 1's Section 8 — install only the specific Bklit components
you use, watch for `@visx/*` peer-dependency conflicts, justify anything beyond
Bklit in your completion report.

## 9. Testing this locally as you build

Identical commands to Phase 1's Section 9. Note: XIRR and Scorer values require
transaction history with enough time depth to be non-null (per FR-8/FR-9's own
"insufficient history" edge case) — a freshly-imported CAS with very recent
transactions may show `null` XIRR/score values everywhere, which is correct
backend behavior, not a bug — verify your "insufficient history" UI treatment
against this case specifically, since it's likely to be the common case in local
testing rather than an edge case.

## 10. Completion report — what you must hand back

Append to `Docs/orchestration/analytics-phase2-frontend-log.md` (skeleton file,
same convention as Phase 1's), covering the same categories as Phase 1's
Section 10: files touched, dependencies added, test/tsc status, `impeccable`
scores, backend gaps found and not implemented, scope deviations, open
questions, and explicit confirmation that Phase 1's components
(`AllocationDonut`, the Phase 1 sections) were not modified except where this
brief explicitly asked you to extend a file (the shell, the mobile view, `api.ts`/
`types.ts`).

Update `session.md` and `CLAUDE.md`'s Session State per Phase 1's Section 10
pattern, again naming yourself as the author of this work. Leave
`delegation-log.md` to Claude Code, same as Phase 1.

## 11. What "done" looks like

- S18/S19 have all five Analytics sections (Allocation, TER, Category Ranking
  from Phase 1; Scorer, Benchmark Comparison from Phase 2).
- S20 (Fund Score Detail modal) built and reachable from the Scorer section.
- Mobile Analytics view has all five sections.
- `npm test` and `npx tsc -b --noEmit` clean.
- Both light and dark mode verified for every new component.
- Every accessibility checklist item checked.
- No score/percentile ever displayed as a bare unexplained number.
- No `null` XIRR or score rendered as if it were zero.
- `session.md`/`CLAUDE.md` updated; `analytics-phase2-frontend-log.md` filled in.
- No backend files touched.
- Work on its own branch, not merged without review.

## 12. Assumptions made while writing this brief — flag if wrong

- S20 as a modal rather than a full route, per the existing `FundDetailModal`
  precedent — no source document mandates one or the other.
- Exact Bklit component names (Section 3.3) unverified against the live registry
  from this environment.
- Layout of the per-fund benchmark grouped-bar chart for households with many
  holdings (pagination vs. scroll vs. a "top N + see all" pattern) is left to the
  builder's judgment — flagged in Section 3.3 rather than dictated.

---

## Ready-to-paste prompt

> Read `Docs/orchestration/analytics-phase2-frontend-brief.md` in full, and also
> read `Docs/orchestration/analytics-phase1-frontend-brief.md` and its log
> (`analytics-phase1-frontend-log.md`) for context on what Phase 1 actually built.
> This is **Phase 2**: Scorer (FR-5–FR-7), Benchmark Comparison (FR-8/FR-9), and
> the Fund Score Detail modal (S20) — extending the S18/S19 shell Phase 1 already
> shipped, not building a new screen. Follow the brief's guardrails, especially:
> never display a score/percentile as a bare number with no tier/breakdown
> context, never render a `null` XIRR as a zero-height bar. Use Bklit UI
> (`npx shadcn@latest add @bklit/<name>`) for both the grouped benchmark bar chart
> and the Scorer's gauge/ring visual — no allocation-style carve-out applies here.
> Work on a new git branch off Phase 1's merged branch, never on `main` directly,
> and never modify anything under `backend/`. If the `impeccable` skill is
> available, use its shape/critique/audit/polish workflow targeting Good band or
> better. When finished, append your completion report to
> `Docs/orchestration/analytics-phase2-frontend-log.md` and update `session.md`
> and `CLAUDE.md`'s Session State per the brief's Section 10.
