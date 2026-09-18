# Analytics Dashboard Frontend — Design Spec

**Date:** 2026-08-14
**Status:** Approved by Ayush
**Author:** Claude Code (orchestrator role — this build is externally implemented, see §6)

## 1. Context

PRD-04's backend is fully complete (357 backend tests passing): Allocation
(FR-1/FR-2), Category Ranking (FR-3/FR-4), Scorer (FR-5–FR-7), Benchmark
Comparison (FR-8/FR-9), Cost/TER (FR-10/FR-11) — 15 API routes across
`backend/app/api/analytics.py`. `frontend/src/features/analytics/` is an
empty placeholder (`.gitkeep` only). Meanwhile a colleague has substantially
revamped the rest of the app's UI (shadcn/Tailwind foundation, mobile shell,
Radix `Select` componentry, CAS import lifecycle redesign) on
`feat/enhanced-ui`. This spec plans the Analytics frontend build to match
that revamped vibe exactly, and to be handed to an external coding agent
(Google Antigravity / Gemini) rather than built by Claude Code or Codex —
see §6 for why and what that changes about the deliverable shape.

## 2. Scope: two phases, both planned before either is built

**Phase 1 — Allocation + TER + Category Ranking** (web + mobile). Lower
design risk: allocation reuses an existing component outright, TER and
category-ranking visuals are simple compositions. Screens: S18 (per-member
Analytics) and S19 (family aggregate Analytics) from `App-Flow-Unifolio.md`,
restricted to these three feature areas.

**Phase 2 — Scorer + Benchmark Comparison** (web + mobile). Higher design
risk: the Scorer has no existing UI precedent anywhere in the app, and
Benchmark Comparison needs a new grouped-bar chart. Adds S20 (Fund Score
Detail) and extends S18/S19 with the remaining two sections.

Both phases share one nav entry point (enabling the currently-disabled
"Analytics" button in `NavigationShell.tsx`) and one screen shell; Phase 2
adds sections to that shell rather than creating a second screen.

## 3. Chart library decision — Bklit UI, with one carve-out

The user's explicit direction: use Bklit UI for "mostly everything" in the
Analytics dashboard. Bklit UI is a shadcn-registry chart library (not an npm
package — installed per-component via `npx shadcn add @bklit/<name>`),
built on Visx + Tailwind v4 + Motion, MIT-licensed. Confirmed
**already configured** in `frontend/components.json`:
```json
"registries": { "@bklit": "https://ui.bklit.com/r/{name}.json" }
```
— the colleague's setup already anticipated this, independent confirmation
this is the right call.

**One documented carve-out, flagged rather than silently resolved either
way per CLAUDE.md's working-style rule:** the Design Brief has an existing,
locked rule — *"Allocation views should use a consistent chart language
across the product... one donut/bar convention, not different chart types
per screen for the same kind of data"* (`Design-Schema-Unifolio.md`
§Charts). The Main Dashboard's `AllocationDonut` (`frontend/src/components/
AllocationDonut.tsx`) is that convention, and its `AllocationItem` prop
shape (`label`/`current_value`/`percentage`) is structurally identical to
the backend's `AllocationBucket` that Analytics' allocation endpoints
return — so Phase 1's allocation view **reuses `AllocationDonut` unchanged**,
not a Bklit ring/pie, to stay compliant with that rule. Ayush confirmed this
resolution.

Every other Analytics visual — none of which has an existing product
convention to conflict with — uses Bklit UI:

| Data | Phase | Bklit chart type |
|---|---|---|
| Direct vs. Regular weighted TER (`DirectRegularTerComparison`) | 1 | `@bklit/bar-chart` |
| Category percentile position (`CategoryRankRow.percentile`) | 1 | `@bklit/gauge-chart` or `@bklit/bar-chart` (horizontal) |
| Portfolio vs. 4 indices (`PortfolioBenchmarkSummary`) | 2 | `@bklit/bar-chart` (grouped) |
| Per-fund vs. appropriate benchmark (`FundVsBenchmarkSummary`) | 2 | `@bklit/bar-chart` (grouped, one group per fund) |
| Scorer final_score with tier coloring (`FundScoreRow.final_score`) | 2 | `@bklit/gauge-chart` or `@bklit/ring-chart` |

Both phase briefs (§6) instruct Antigravity to confirm the exact Bklit
component name against the live registry at build time (`bklit-ui` skill /
`npx shadcn add @bklit/<name> --dry-run` or the registry JSON) rather than
trusting this table's names blindly — the registry's exact catalog wasn't
directly inspectable from this environment.

## 4. Component reuse inventory

Reused as-is, no changes:
- `AllocationDonut` (allocation, per §3)
- `Badge` (all status flags: `category_unavailable`, `insufficient_history`,
  `thin_category` → `warning`/`neutral` variants per existing convention)
- `Card`, `Tabs`, `Select`, `Tooltip`, `Skeleton`, `Table` (shadcn primitives)
- `NavigationShell` (enable the disabled Analytics nav button; no structural
  change)
- The family/member `viewMode` switcher pattern already in
  `DashboardView.tsx` (aggregate vs. per-member), reused for Analytics'
  own aggregate/per-member split (same `MemberStatus[]` shape backs both)
- `formatIndianCurrency`, `lib/decimal`'s `sumDecimalStrings` and friends —
  every value in the analytics schemas is a `Decimal`-as-`string`
  (`"weighted_ter": str | None`, etc.); the frontend must format, never
  parse-to-float-and-recompute

New, built this phase:
- `frontend/src/features/analytics/AnalyticsView.tsx` — the screen shell
  (mirrors `DashboardView.tsx`'s composition pattern: hero/header + section
  cards + viewMode switcher), replacing the `.gitkeep` placeholder
- `frontend/src/features/analytics/api.ts` + `types.ts` — API client and
  TypeScript types for all 15 routes, mirroring `dashboard/api.ts`'s
  `authFetch` pattern exactly
- Section components: `AllocationSection`, `TerSection`,
  `CategoryRankingSection` (Phase 1); `ScorerSection`, `BenchmarkSection`,
  `FundScoreDetailModal` (Phase 2, modal per the existing `FundDetailModal`
  precedent — S20 is reached by tapping a fund's score, not a new route)
- `frontend/src/mobile/features/analytics/MobileAnalyticsView.tsx` — mobile
  layout, same data/API client, composition following
  `MobileDashboardView.tsx`'s "shared data, different layout" convention

## 5. Data flow

No new backend work. Each section component calls its own `api.ts`
function per the aggregate/per-member toggle (`getMemberAllocation(id)` /
`getAggregateAllocation()`, etc., named identically to the existing
`dashboard/api.ts` convention). All money/percentage fields arrive as
strings and are formatted for display only — never coerced to JS `number`
for anything but chart positioning (Bklit's chart props take numbers for
plotting; the *displayed* label text must still come from the original
string, per the pattern already established in `AllocationDonut`'s
`formattedValue` field).

## 6. Build approach: external agent, Claude Code as orchestrator/reviewer

Per explicit user direction, this build is **not** delegated through
`model-orchestration` (Codex) and not built directly by Claude Code.
Instead: Claude Code produces a complete, self-contained handoff brief per
phase (structural precedent: `Docs/superpowers/specs/
2026-08-07-frontend-redesign-brief-for-coding-agent.md`, which produced the
current UI revamp via the same mechanism), Ayush hands each brief to Google
Antigravity (Gemini) directly, Antigravity implements, and Claude Code
returns afterward purely as **tester, reviewer, and comparator** — running
the test suite, checking the diff against the brief's guardrails and the
Design Schema, and optionally making targeted fixes.

This is a third worker category the `model-orchestration` skill doesn't
document (its worker roles are Codex, a rare Claude-subagent fallback, and
Opus escalation — all invoked via `Agent()`; this is a human-relayed
external agent with no `Agent()` call at all). Flagged as a task-observer
observation (undocumented use case) rather than silently stretched into an
existing category — logged separately, see delegation-log entry below.

Deliverables per phase (both written this session, Phase 1 and Phase 2):
1. `Docs/orchestration/analytics-phase{1,2}-frontend-brief.md` — the
   Antigravity-facing handoff brief (read-order, guardrails, exact API
   surface, component scope, Bklit setup, testing commands, required
   completion-report format, ready-to-paste prompt).
2. A `delegation-log.md` entry recording the dispatch, `worker=external-agent`.
3. Instructions inside each brief for Antigravity to update `session.md`
   and `CLAUDE.md`'s Session State itself at hand-back time (same pattern
   as the 2026-08-07 precedent's Section 10), naming itself as the author
   of the work so the record stays accurate.

## 7. Testing / acceptance (Claude Code's job on hand-back)

For each phase, once Antigravity reports done: run `npm test` and
`tsc -b --noEmit` (must stay green — the branch is currently 190/190 +
clean `tsc`), diff review against this spec's component-reuse inventory
(§4 — confirm `AllocationDonut` wasn't rebuilt, confirm no `float` parsing
of money/percentage fields for anything but chart-axis positioning), Design
Schema Accessibility Checklist spot-check, and a manual local run at
320/375/430px per `MOBILE_APP_EXECUTION.md`. Findings handled the same way
the `model-orchestration` skill's adversarial-review gate handles Codex
findings: presented ordered by severity, no auto-applied fixes, user
decides what's worth fixing.

## 8. Self-review

- No placeholders/TBDs remain in this spec.
- Internal consistency: §3's carve-out is reflected consistently in §4's
  reuse inventory and will be repeated verbatim in both phase briefs.
- Scope: two phases as previously agreed; this doc covers both at the
  design level, each phase brief is its own separate, focused document —
  no further decomposition needed.
- Ambiguity: the exact Bklit component names are flagged as
  build-time-to-confirm rather than guessed, since the live registry
  catalog wasn't directly inspectable here — this is the one open item and
  it's explicitly assigned to the builder, not left silently ambiguous.
