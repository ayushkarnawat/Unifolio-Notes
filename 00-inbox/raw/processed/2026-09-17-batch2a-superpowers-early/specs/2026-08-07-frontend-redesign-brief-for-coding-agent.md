---
artifact: frontend-redesign-brief
version: "1.0"
created: 2026-08-07
status: for-review
product: Unifolio
audience: A coding agent (e.g. Google Antigravity) executing the frontend UI/UX redesign
---

# Unifolio — Frontend Redesign Brief

**This document is a handoff, not a suggestion. Read it in full before writing any
code, then read the two documents it points to in Step 0. Do not start building
from memory of this brief alone — the brief compresses those documents; it does
not replace them.**

## 0. Read these first, in this order

1. `Docs/PRDs/Design-Brief-Unifolio-updated.md` — the *why*: brand principles,
   color discipline, typography discipline, motion principles, the Fund Signal
   signature-element concept, voice & tone, accessibility baseline. **Read the
   `-updated.md` file, not `Design-Brief-Unifolio.md`** — the non-`-updated`
   file is version 1.0, superseded; `-updated` is 1.1, current.
2. `Docs/PRDs/Design-Schema-Unifolio.md` — the *exact system*: color tokens,
   type scale, spacing scale, shape/elevation, every component spec (Badge,
   Fund Signal, Holdings Table Row, Charts, Scorer Display), motion tokens,
   dark/light mode rule, accessibility checklist.
3. `CLAUDE.md` (repo root) — project-wide non-negotiables (stack is locked,
   `Decimal` discipline, no gold-plating) and the Session State section for
   what's built and merged so far.
4. `session.md` (repo root) — full working-notes detail behind CLAUDE.md's
   summary: what shipped, what bugs were found and fixed, what's still open.
5. `Docs/PRDs/App-Flow-Unifolio.md` — the full screen inventory (S0–S26) and
   navigation graph this brief's Screen Inventory (Section 4) is built from.

Everything below is a working compression of those five documents plus the
real, already-built backend API surface — cite the source documents for
anything this brief seems to contradict or under-specify, don't guess.

## 1. Why this brief exists

The backend (FastAPI, four services: Auth, Import, Dashboard, Analytics-not-yet-
built) is substantially complete and tested — CAS import, phone+OTP auth,
household-member management, and a full Main Dashboard backend (holdings,
allocation, SIPs, cash flow, monthly snapshots, family aggregation, distributor
comparison) are all merged to `main`. A frontend exists for Onboarding and
Import Review (React + Vite, functionally complete, tested, 81 passing tests)
but the visual/interaction layer does not yet reflect the Design Brief/Design
Schema — the product owner's own assessment: "not up to the mark." Concretely,
verified by inspection before this brief was written:

- `frontend/src/index.css` and `frontend/src/styles/tokens.css` declare DM Sans
  and Manrope as font families but **never load them** — no `@font-face`, no
  Google Fonts/self-hosted `<link>`, no font files in `frontend/public/`. The
  app is currently rendering in fallback system sans-serif.
- No `font-feature-settings: "tnum"` (tabular figures) anywhere, despite the
  Design Schema calling this a **hard requirement**, not optional, for every
  `type-data*` token.
- `tokens.css`'s dark-mode block only overrides `bg/ink/surface/border/
  text-secondary/positive/negative` — `color-accent-dark`, `color-warning`,
  and `color-neutral-badge` have no dark-mode override at all yet.
- No `type-display`, `type-data-large`, or explicit line-height/weight tokens
  beyond font-size — the Design Schema's full type scale (8 tokens) isn't
  represented in code yet, just a partial subset.
- No chart library, no animation library, no router in `package.json` — the
  Fund Signal (arc + sparkline), the donut allocation chart, and every motion
  token in the Design Schema are unbuilt.
- `frontend/src/features/dashboard/DashboardPlaceholder.tsx` is a literal
  one-line stub (`<h1>Welcome to Unifolio</h1><p>...coming soon.</p>`) — this
  is intentional (Phase 3b was always going to replace it outright, never
  extend it), not a bug, but it means the Main Dashboard has **zero** existing
  visual design to preserve — full creative latitude within the Design Brief's
  constraints.

So this redesign has two parts that are different in kind:

- **Onboarding (S0–S12, S23–S26) and Import Review**: functionally complete
  and tested. This is a **refinement**, not a redesign, in the Design Brief's
  own vocabulary distinction (see `impeccable`'s `new-work.md` for the same
  distinction) — keep the state machine, the API calls, the validation logic,
  the copy (unless copy is factually wrong), and the test coverage. Replace
  only the visual/interaction layer: components, tokens, motion, layout.
- **Main Dashboard + Fund Detail + Distributor Comparison (S13–S17, S21–S22)**:
  no existing frontend at all. This is greenfield **new-work** against a
  backend that already exists and is already tested — build the real UI
  directly against the real API surface (Section 6), no mock-data placeholder
  phase needed.

**Analytics Dashboard (S18–S20) is explicitly out of scope.** PRD-04's backend
does not exist yet (see CLAUDE.md's Session State — Analytics is "fully
unbuilt" as of this brief). Do not build S18/S19/S20. Do not add a live nav
link to them; if the redesigned dashboard shell has an Analytics nav item,
it should be visibly present-but-disabled or simply absent — a broken link to
a nonexistent route is worse than no link.

## 2. Non-negotiable guardrails

These come directly from `CLAUDE.md` and apply to this redesign exactly as
they applied to every backend phase:

- **Stack is locked**: React 19 + Vite, TypeScript, CSS Modules (the existing
  pattern — see `Badge.module.css`). No Next.js, no framework swap, no CSS-in-
  JS runtime library, no server-side rendering. You **may** add focused
  frontend dependencies this redesign genuinely needs (a charting library for
  the donut chart, a lightweight animation library, font files) — see Section
  8 for guidance on what to add and how to choose.
- **Do not modify backend code.** `backend/` is complete, tested (156 passing),
  and merged. This brief is UI/UX only. If you discover the redesign needs a
  backend change (a new field, a new endpoint) — **stop and report it, do not
  implement it.** Flag it in your completion report (Section 10) instead.
- **Never treat a money/units/NAV value as a JS number for calculation.**
  Every such value arrives from the API as a **string** (backend Decimal,
  JSON-serialized as `str` — see every schema in Section 6). Parse only for
  *display formatting* (e.g. via a formatting library or `Intl.NumberFormat`
  fed a string-derived value with no intermediate float math that could lose
  precision on large portfolios), never for arithmetic the UI performs itself.
  If the UI needs a derived number the API doesn't already provide, that's a
  backend gap to report (previous bullet), not something to compute client-side
  with floats.
- **Preserve existing test coverage.** Run `npm test` in `frontend/` before
  and after your changes. Every one of the 81 existing tests should still
  pass unless you have a specific, documented reason a *behavior* changed
  (not just its visual presentation) — list any such change explicitly in
  your completion report.
- **Work in an isolated branch**, not directly on `main`. This repo's
  established convention (see `git log`) is a dedicated feature branch per
  body of work, reviewed/merged deliberately — follow the same discipline
  here even though you're a different agent. Do not push to `origin` or open
  a PR without the product owner's explicit go-ahead.
- **`Decimal`-grade correctness of *display*, not just data.** The Design
  Brief's Principle 4 ("Numbers are the product") means a stale NAV, an
  unclassified plan type, or an unresolved distributor name must be
  *visually* distinguishable from a fresh/confirmed one — this is a design
  requirement flowing from the same PRDs that drove the backend's own
  handling of these states, not decoration.

## 3. Design foundation — the compressed version

Full detail is in the two source documents (Section 0). This section exists
so you don't have to cross-reference constantly, but it is a **compression**
— when in doubt, the source document wins.

### 3.1 Brand & principles

- Colors (locked): Ink `#111111`, near-white `#FCFCFC`, accent green `#22C55E`
  (used sparingly — one primary action per screen, never a large fill).
- Type: **DM Sans** for headings/display numbers, **Manrope** for everything
  else, including all tabular data.
- Five design principles (Design Brief, full rationale there):
  1. **Apple-inspired, not Apple-generic** — generous whitespace, one clear
     hierarchy per screen, rounded corners as default, restraint over the
     "near-black + acid accent" generic-AI look.
  2. **Game-like pacing, never game-like mechanics** — no points/badges/
     streaks/confetti anywhere. "Game-like" means deliberate reveals and
     sequencing (motion), not gamification UI.
  3. **One flow, not two** — no retail/HNI visual fork; the same interface
     reads premium to a demanding investor and approachable to a first-timer.
  4. **Numbers are the product** — tabular figures everywhere numeric, strict
     gain/loss color semantics, visual honesty about data freshness/confidence.
  5. **Proven structure, distinctive execution** — information architecture
     follows the validated Mprofit/competitor pattern (`/App Flow References`
     is a *functional pattern* reference only — table layout, what goes where
     — **never** a visual-style reference; Unifolio's look is the Design
     Schema, full stop). Distinctiveness lives in typography, color, motion,
     and the Fund Signal.

### 3.2 Color tokens — fill the gaps

Current `frontend/src/styles/tokens.css` has the light-mode and *partial*
dark-mode tokens. Add what's missing (values from Design Schema §Color
Tokens):

```css
/* Currently missing from the dark-mode block in tokens.css */
--color-accent-dark: #22C55E; /* verify contrast vs #0F0F0F at build time;
  fall back to #34D399 ONLY if contrast testing genuinely fails — this is a
  brand color, don't change it casually */
--color-neutral-badge-dark: /* not specified in Design Schema — derive a
  dark-mode-appropriate desaturated slate that keeps the same "unresolved,
  not red or green" meaning as light mode's #94A3B8; verify AA contrast */
--color-warning-dark: /* same treatment — Design Schema doesn't give an
  explicit dark value for #F59E0B; verify AA contrast against #0F0F0F,
  brighten only if needed */
```

Every `color-positive`/`color-negative` usage must pair with a non-color
signal (↑/↓ icon or label) — color alone is never sufficient, in either mode.

### 3.3 Typography — full 8-token scale

Design Schema's complete type scale (only a subset exists in `tokens.css`
today — add the rest):

| Token | Family | Weight | Size | Line height | Usage |
|---|---|---|---|---|---|
| `type-display` | DM Sans | 700 | 32px | 1.2 | Hero numbers (total portfolio value) |
| `type-h1` | DM Sans | 700 | 24px | 1.3 | Screen titles |
| `type-h2` | DM Sans | 600 | 18px | 1.4 | Section headers |
| `type-body` | Manrope | 400 | 15px | 1.5 | Default body text |
| `type-body-medium` | Manrope | 500 | 15px | 1.5 | Emphasized body (row labels) |
| `type-caption` | Manrope | 400 | 13px | 1.4 | Timestamps, secondary labels |
| `type-data` | Manrope | 500 | 15px | 1.4, **tabular-nums** | Every number in a table/column |
| `type-data-large` | DM Sans | 600 | 20px | 1.2, **tabular-nums** | Standalone large numbers (per-fund value) |

`font-feature-settings: "tnum"` (or `font-variant-numeric: tabular-nums`) is
**mandatory** on every `type-data*` token. Before implementation: confirm the
actual DM Sans/Manrope font files you load ship tabular-figure support. If
either doesn't, that's a blocking finding — report it (Section 10), don't
silently substitute a different font.

**Font loading**: self-host or use a font-display strategy that avoids FOUC/
layout shift (`font-display: swap` at minimum) — this app targets consumer
investors on real-world connections, not just desktop broadband.

### 3.4 Spacing, shape, motion

Already fully in `tokens.css`, correct as-is — reuse, don't redefine:
- Spacing: 4px base, `4/8/12/16/24/32/48/64`.
- Radius: `radius-sm` 8px (badges, small buttons, inputs), `radius-md` 12px
  (cards, table containers), `radius-lg` 20px (modals).
- Elevation: `color-surface` vs `color-bg` contrast does most of the work;
  shadows are minimal (`0 1px 2px rgba(0,0,0,0.06)` resting, slightly
  stronger on hover/active only).
- Motion: `motion-fast` 150ms ease-out (hover/focus), `motion-reveal` 400ms
  ease-in-out (data reveals), `motion-page` 300ms ease-in-out (screen
  transitions). All three already collapse to `0ms` under
  `prefers-reduced-motion: reduce` in `tokens.css` — preserve this, and
  **verify it actually works** (toggle the OS/browser setting and confirm no
  animation plays) rather than trusting the CSS variable alone.

### 3.5 Fund Signal — the flagship component

From the Design Brief's Signature Element and Design Schema's component spec:
a small radial arc (reusing the logomark's exact arc geometry — the arc
inside Unifolio's "o," not a generic circular progress ring), ~24×24px at
holdings-table row scale, filling from empty on data load (`motion-reveal`,
not an instant paint) to represent that fund's performance over a selectable
period. Expands to arc + sparkline (30/90/365-day NAV trend, user-selectable)
on tap/hover or in a wider viewport. Fill color uses `color-positive`/
`color-negative` — **never** `color-accent` — keeping brand and performance
signal separated per Color Discipline.

**This is flagged in both source documents as needing real prototyping, not
a finished spec** — the single highest-design-risk item in the whole redesign,
since it's the product's one genuine visual differentiator and has never been
visually tested. Budget real iteration here: does it read clearly at a dense
30+ row table, does it hold up in dark mode, does the sparkline-on-expand
feel like the "reveal" principle or like clutter. If real prototyping shows
the concept doesn't work at table density, that's worth reporting honestly
rather than shipping a version that technically matches the spec but doesn't
read well in practice — the Design Brief's own principles (restraint,
legibility) outrank literal spec compliance if the two conflict in practice.

## 4. Screen inventory & scope

| Screen | Name | Current state | This redesign's job |
|---|---|---|---|
| S23 | Landing (Sign Up/Log In) | Built (`Landing.tsx`) | Refine: tokens, typography, motion |
| S0 | Phone Entry | Built (`PhoneEntry.tsx`) | Refine |
| S1 | OTP Verify | Built (`OtpVerify.tsx`) | Refine |
| S2 | Trust Primer | Built (`TrustPrimer.tsx`) | Refine |
| S3–S6 | Q1–Q4 Questionnaire | Built (`Q1Name.tsx`…`Q4Household.tsx`) | Refine, preserve back-nav/skip logic exactly |
| S7 | Add Family Member(s) | Built (`AddFamilyMembers.tsx`) | Refine |
| S24 | Family CAS Upload | Built (`FamilyCasUpload.tsx`) | Refine, preserve per-member queue/sequential-parse logic |
| S25 | Upload My CAS? Now/Later | Built (`UploadMyCas.tsx`) | Refine |
| S26 | Parse Queue | Built (`ParseQueue.tsx`) | Refine |
| S8 | CAS Upload | Built (`SoloCasUpload.tsx`) | Refine |
| S9 | Import Parsing (loading) | Built (`ParsingIndicator.tsx`) | Refine — this is a prime "reveal, not instant swap" motion opportunity |
| S10 | Import Review | Built (`ReviewTable.tsx`) | Refine — apply the shared Badge system here (Direct/Regular, AMFI-match confidence) exactly as it'll appear on the dashboard |
| S11 | Import Error | Built (`ImportError.tsx`) | Refine — voice & tone: specific, direct, never apologetic filler |
| S12 | Import Confirmed (payoff) | Built (`ImportConfirmed.tsx`) | Refine — this is the "satisfying moment when real data appears" the Design Brief calls out by name |
| **S13** | **Main Dashboard (per-member)** | **Placeholder stub only** | **Build fresh** against `/household-members/{id}/*` routes (Section 6) |
| **S14** | **Main Dashboard (family aggregate)** | **Placeholder stub only** | **Build fresh** against `/household/aggregate/*` routes — default landing for returning users with family set up (per App-Flow's resolved open question) |
| **S15** | **Fund Detail** | **Doesn't exist** | **Build fresh** — tap a holding row |
| **S16** | **Add Data (re-entry)** | **Doesn't exist** | **Build fresh** — routes back into S8's existing upload flow with a real `household_member_id`, not a new upload implementation |
| **S17** | **Distributor Comparison** | **Doesn't exist** | **Build fresh** against `/household-members/{id}/schemes/{scheme_id}/distributor-comparison` — reachable only from S15 when a scheme has >1 distinct `arn_code` |
| **S21** | **Empty State — No Holdings Yet** | **Doesn't exist** | **Build fresh** — reached instead of S13/S14 when no import has completed. Voice & Tone: an invitation to act, not a dead end |
| **S22** | **Family Member Placeholder** | **Doesn't exist** | **Build fresh** — within S14, per member with `has_data: false` in the aggregate response's `members` array |
| S18–S20 | Analytics Dashboard, Fund Score Detail | N/A | **Out of scope** — PRD-04 backend unbuilt, do not build |

## 5. Component library

Build/refine as a shared library (`frontend/src/components/`, following the
existing `Badge.tsx` + `Badge.module.css` pairing pattern), consumed by both
the refined Onboarding/Import screens and the new Dashboard screens — the
whole point of a design system is that a "Direct" badge looks identical on
the Import Review screen and the Main Dashboard, per the Design Brief's own
explicit rule.

- **Badge / Status Tag** (exists, refine to match full spec): `radius-sm`,
  `type-caption` weight 500, 8px/2px padding. Variants: `positive`
  (Direct/high-confidence), `neutral` (unclassified/unverified,
  `color-neutral-badge`), `warning` (stale data, invalid/suspended ARN,
  `color-warning`). Always paired with a label, never color-only.
- **Fund Signal** (new — see Section 3.5).
- **Holdings Table Row**: Fund Signal, fund name (`type-body-medium`),
  Direct/Regular badge, avg NAV, units, current NAV, invested, current value,
  current profit, realized/unrealized/today's gain (all `type-data`,
  positive/negative colored with ↑/↓ icon), last-updated date (`type-caption`,
  `color-warning` badge if stale).
- **Allocation Donut Chart**: one consistent donut convention for both
  `by_asset_class` and `by_amc` breakdowns (same `AllocationSummary` response
  powers both). Segments labeled with absolute value **and** percentage, not
  percentage alone. Extended multi-segment palette: derive from the same
  restrained/muted family as the semantic colors — not a generic rainbow.
- **Empty State**: reusable pattern for S21 (no holdings), S22 (family member
  placeholder), and any "no data yet" state within a widget (e.g. no active
  SIPs) — an invitation with a clear next action, never a bare "No data."
- **Button**: primary (accent green, one per screen), secondary, ghost/text.
- **Card / Surface**: `radius-md`, `color-surface` on `color-bg`.
- **Modal**: `radius-lg`, used for Distributor Comparison if it reads better
  as an overlay than a full screen (your call — App-Flow doesn't mandate
  either, use the Operate-mode judgment: whichever keeps the user oriented
  without a full context switch for a "compare within this one fund" task).
- **Loading/Skeleton states**: Nielsen heuristic #1 (Visibility of System
  Status) — every async operation (dashboard load, family-member switch,
  import parsing) needs a state between "nothing" and "final content" that
  isn't a bare spinner if the content shape is predictable (skeleton rows for
  the holdings table, not a spinner over a blank page).
- **Dashboard shell / nav**: doesn't exist yet, needs designing — persistent
  chrome for: per-member ↔ family-aggregate switch (App-Flow's resolved
  default-landing logic), the Add Data (S16) entry point, and an Analytics
  nav slot that is visibly disabled/absent (Section 1) rather than a dead link.
- **Toast/inline confirmation**: for actions like "Add Data" completing,
  matching the vocabulary-consistency rule (whatever a button calls an
  action, the confirmation uses the same word).

Every component: verify in **both** light and dark mode before considering it
done (Design Schema's explicit rule — "not just designed once and assumed to
translate"), and verify keyboard-focus states (Accessibility Baseline).

## 6. Backend context — the real, exact API surface

Base URL: `import.meta.env.VITE_API_BASE_URL` (frontend env var), defaults to
`http://localhost:8000` (see `frontend/src/lib/apiClient.ts`). No dev-server
proxy is configured (`vite.config.ts` is plain `react()`, no `server.proxy`)
— the frontend calls the backend cross-origin directly; CORS is already
enabled backend-side for the frontend dev origin (verified:
`backend/tests/test_health.py::test_cors_allows_frontend_dev_origin`).

Auth: Bearer token in `Authorization` header, obtained from `POST
/auth/otp/verify`'s `session_token`. All Dashboard and Import routes require
it (`Depends(get_current_user)`).

### Auth (`/auth/*`)

| Method | Path | Response | Notes |
|---|---|---|---|
| POST | `/otp/request` | `{message, otp?}` | `otp` only populated in dev-stub delivery — no real SMS in local dev |
| POST | `/otp/verify` | `{session_token, user_id, onboarding_step, onboarding_completed}` | |
| POST | `/session/refresh` | `{expires_at}` | |
| GET | `/me` | `{user_id, phone_number, email, onboarding_step, onboarding_completed, investor_type, primary_goal}` | |
| PATCH | `/me` | same as GET | body: any subset of `onboarding_step, investor_type, primary_goal, onboarding_completed` |

### Household members (`/household-members`)

| Method | Path | Response |
|---|---|---|
| POST | `/household-members` | `{id, name, relationship, relationship_other_label}` |
| GET | `/household-members` | `list[...]` of the same shape |

### Dashboard — per member (`/household-members/{member_id}/...`)

All 404 if `member_id` doesn't exist or isn't owned by the caller.

| Path | Response shape | Key fields |
|---|---|---|
| `/holdings` | `list[HoldingRow]` | `scheme_id, scheme_name, amc_name, household_member_id, household_member_name, plan_type, units_held, average_nav, current_nav, current_nav_date, amount_invested, current_value, current_profit_total, realized_gain, unrealized_gain, today_gain` — **all money/units/NAV fields are strings** |
| `/schemes/{scheme_id}/distributor-comparison` | `list[DistributorComparisonRow]` | `arn_code, distributor_name, arn_status (active/suspended/invalid/unresolved/null), units_held, average_nav, amount_invested, current_value, current_profit_total, realized_gain, unrealized_gain` — a row with `arn_code: null` is the "Direct" bucket (no distributor); `distributor_name`/`arn_status` are `null` until AMFI resolution completes — **never block rendering on this, show the raw `arn_code`** |
| `/allocation` | `AllocationSummary` | `{by_asset_class: [{label, current_value, percentage}], by_amc: [...], total_value}` |
| `/sips` | `list[SipRow]` | `scheme_id, scheme_name, household_member_id, household_member_name, sip_date, sip_amount` |
| `/cash-flow` | `list[CashFlowEntry]` | `date, type, amount, direction ("debit"/"credit"), scheme_name, household_member_id, household_member_name` |
| `/snapshots` | `list[SnapshotRow]` | `household_member_id, household_member_name, snapshot_month, total_value` |

### Dashboard — family aggregate (`/household/aggregate/...`)

Every response wraps the per-member shape with a `members` array for
placeholder rendering (S22):

```
members: [{id, name, has_data: bool}]
```

| Path | Response shape |
|---|---|
| `/holdings` | `{members, holdings: list[HoldingRow]}` |
| `/allocation` | `{members, allocation: AllocationSummary}` |
| `/sips` | `{members, sips: list[SipRow]}` |
| `/cash-flow` | `{members, cash_flow: list[CashFlowEntry]}` |
| `/snapshots` | `{members, snapshots: list[SnapshotRow]}` |

A member with `has_data: false` is S22 (Family Member Placeholder) — still
present in the array, contributes nothing to the combined totals, never
silently excluded.

### Import (`/imports/*`)

Already fully consumed by the existing, tested Import Review flow (see
`frontend/src/features/import/api.ts`) — no new integration needed here
except S16 (Add Data) routing an already-onboarded user back into this same
flow with their real `household_member_id`. Don't reimplement upload/parse
logic; reuse `frontend/src/features/import/` as-is, entered from a new
Dashboard nav action instead of the onboarding flow.

## 7. Motion & UX quality bar

### 7.1 Choreography (not just "use the tokens")

- **Dashboard load**: holdings rows reveal with a subtle staggered entrance
  (`motion-reveal`), not an instant table paint — this is where "game-like
  pacing, never game-like mechanics" (Principle 2) is supposed to be *felt*,
  product-wide, not just in onboarding.
- **Fund Signal arc**: fills from empty on every data load, using
  `motion-reveal`.
- **Screen-to-screen nav** (member switch, drill into Fund Detail, Add Data
  entry): `motion-page`.
- **Hover/focus micro-interactions**: `motion-fast`, quiet and fast — earns
  its place by clarifying what happened, never noticed for its own sake.
- **`prefers-reduced-motion: reduce`**: every reveal collapses to instant
  final-state rendering, no exceptions. Test this by actually toggling the
  OS setting, not just trusting the CSS.

### 7.2 Operationalize the `impeccable` plugin's own quality rubric

This plugin (already installed for this project, at whichever of
`.agent/skills/impeccable/` or `.agents/skills/impeccable/` your install
landed in) scores interfaces against Nielsen's 10 usability heuristics (0–4
each, 40 total) and flags P0–P3 issues. Use it as your own build-verification
loop, not just something the product owner runs afterward.

**A note on invocation**: this skill's commands are written below as
`/impeccable <command>` because that's how the skill's own reference docs
name them, and it's exactly how to invoke them in a harness that supports
`user-invocable` slash commands (Claude Code, Cursor, Copilot, and several
others). Antigravity's frontmatter support does not include
`user-invocable` — there may be no literal typed-slash affordance for it in
your environment. If `/impeccable <command>` doesn't work as a typed command,
the skill still applies: it auto-loads based on task-description matching
(standard Agent Skills spec behavior), and once loaded you can direct it in
plain language ("use the impeccable skill to critique this screen," "run an
impeccable audit here") — it'll follow its own internal command routing
either way. Try the literal slash form first; fall back to plain language if
it's not recognized.

1. Before writing code for a surface, invoke `shape` on it (owns task
   discovery and UX planning per the skill's own routing) — the Main
   Dashboard and Distributor Comparison, having no existing implementation,
   are exactly the "new surface" case its `new-work.md` playbook covers.
2. Every screen in this brief is **Operate mode** in `impeccable`'s own
   terminology ("the visitor completes a task... scanability, consistency,
   native expectations... outrank expression") — not Persuade/Read/
   Experience. Design and self-evaluate accordingly: this is a financial
   tool, not a marketing surface.
3. `impeccable`'s own persona-selection table recommends **Alex (power user)**
   and **Sam (accessibility-dependent)** for "Dashboard / admin" interfaces —
   design against both explicitly. Alex needs the primary task completable
   fast with no forced hand-holding; Sam needs the entire flow keyboard-
   navigable with correct ARIA and WCAG AA contrast in both modes.
4. After building each major surface, invoke `critique` on it. **Target: Good
   band or better (≥28/40, or ≥70% when a heuristic is validly `n/a`)** before
   considering that surface done. If a critique comes back Acceptable or
   below, treat every P0/P1 finding as blocking before moving to the next
   surface — don't accumulate design debt across five screens and try to fix
   it all at the end.
5. Invoke `audit` for the technical checks (accessibility, performance,
   responsive) `critique`'s design review doesn't cover.
6. End with `polish` as the final pass before calling the redesign complete,
   per the skill's own recommended sequence.

### 7.3 Cognitive load discipline (Design Schema + `impeccable` both require this)

- ≤4 visible options at any single decision point.
- The family-aggregate view (S14) is the highest cognitive-load risk in this
  whole redesign — potentially many members × many holdings on one screen.
  Chunk by member, use progressive disclosure (collapsed member summaries
  expanding to full holdings), don't render every member's full table
  simultaneously by default.
- The onboarding questionnaire (S3–S6) already respects one-decision-per-
  screen — preserve this structure exactly, don't consolidate screens to
  "reduce clicks" at the cost of this principle.

### 7.4 Accessibility checklist (Design Schema, verbatim — treat as a gate, not a wishlist)

- [ ] Every `color-positive`/`color-negative` usage paired with an icon or label
- [ ] All text/background pairs meet WCAG AA in **both** light and dark mode
- [ ] Keyboard focus states defined for every interactive component, including
      tappable badges and expandable table rows
- [ ] `prefers-reduced-motion` respected on every motion token, verified by
      actually toggling the setting
- [ ] Tabular figures confirmed available in both typefaces before build

## 8. Adding dependencies

You may add frontend dependencies this redesign genuinely needs. Guidance,
not a mandate — you have better current-ecosystem visibility than this brief:

- **Charting** (donut allocation, Fund Signal sparkline): prefer something
  small, SVG-based, and tree-shakeable over a heavy full-featured charting
  suite — this product's chart needs are narrow and specific (one donut
  convention, one sparkline pattern), not a general-purpose chart library's
  full surface area.
- **Motion**: CSS transitions/animations cover most of Section 7.1's
  choreography without a library at all (the existing motion tokens are
  plain CSS custom properties). Only reach for a JS animation library if a
  specific effect (the Fund Signal arc fill, a staggered list reveal)
  genuinely needs orchestration CSS can't express cleanly.
- **Fonts**: self-hosted `.woff2` files (DM Sans, Manrope) checked into
  `frontend/public/fonts/` or fetched at build time — verify license terms
  allow self-hosting (both are open-source Google Fonts, so this should be
  straightforward, but confirm).
- **Routing**: `App.tsx` currently does manual conditional rendering
  (`AuthEntryFlow` → `OnboardingFlow` → `DashboardPlaceholder`), no router.
  The Dashboard now needs real navigation (member switch, Fund Detail
  drill-down, Distributor Comparison, Add Data) — introducing a lightweight
  router (e.g. one that works cleanly with Vite + React 19, your choice) is
  reasonable scope for this redesign; a hand-rolled state-based router is
  also acceptable if you judge the navigation surface small enough not to
  need one. Either way, preserve the existing top-level gating logic
  (no-session → auth, onboarding-incomplete → onboarding, else → dashboard).

Whatever you add: keep it minimal, justify it in your completion report
(Section 10), and don't add a dependency for something 20 lines of CSS/JS
already does.

## 9. Testing this locally as you build

Both servers must run simultaneously (backend for real API responses, no
mocking — the backend is real and already tested):

```bash
# Terminal 1 — backend
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
# or: source .venv/bin/activate && uvicorn app.main:app --reload

# Terminal 2 — frontend
cd frontend
npm install   # first time / after adding dependencies
npm run dev   # Vite dev server, default port 5173
```

Open the printed Vite URL. Sign up with any phone number — OTP delivery is a
dev-stub, the OTP is returned directly in `/otp/request`'s response body
(`otp` field) rather than sent by SMS, so you can read it straight from the
network tab or a `console.log` during development.

Run the frontend test suite after every meaningful change:

```bash
cd frontend
npm test          # vitest run — all 81+ existing tests
npx tsc -b --noEmit   # type-check, must stay clean
```

To see real dashboard data instead of an empty state, complete a CAS import
through the Import Review flow first (a sample CAS PDF is needed — check
`CAS Parsers/` in the repo root for any test fixtures, or use a real
statement if the product owner provides one).

## 10. When you're done — update the project's own memory

This repo's convention (established across every prior phase — see `git log`
on `session.md`/`CLAUDE.md`) is that **`session.md` and `CLAUDE.md`'s Session
State section are the persistent memory a fresh coding session reads before
touching anything else.** You are a different agent than the one that built
the backend; the next session (which might be back in Claude Code, might be
you again) needs to know what you did without re-deriving it from a diff.

Update both files, following their existing structure exactly:

- **`session.md`** (repo root): add a new dated section (don't delete prior
  sections — this file accumulates across phases) describing: what was
  redesigned vs. built fresh, every new component added and where it lives,
  every new dependency added and why, the final `npm test`/`tsc` status,
  the `impeccable critique` scores achieved per major surface (Section 7.2),
  any surface where the score came in below Good and why, any backend gap
  you found and flagged rather than fixed (Section 2's guardrail), and any
  open design questions you couldn't resolve from the source documents.
  Explicitly note **which agent/tool did this work** (e.g. "built via Google
  Antigravity, not Claude Code") so a future Claude Code session knows to
  treat this as external, already-integrated work rather than something it
  planned.
- **`CLAUDE.md`**'s Session State section (repo root): the condensed,
  one-paragraph-plus-bullets pointer version of the same update — update the
  "Updated <date>" line and the summary paragraph, following the exact style
  of the existing entries there (see how the Phase 3/Distributor Comparison
  entries are written: what shipped, one or two things worth knowing before
  touching this code again, pointer to `session.md` for full detail).

Do not delete or rewrite prior phases' entries in either file — append,
matching the existing pattern.

## 11. What "done" looks like

- Every screen in Section 4's "Build fresh" and "Refine" rows exists,
  functions against the real backend, and passes its own `impeccable
  critique` at Good band or better.
- `npm test` and `npx tsc -b --noEmit` both clean.
- Both light and dark mode verified for every new/changed component.
- Every accessibility checklist item (Section 7.4) checked, not assumed.
- `session.md` and `CLAUDE.md` updated per Section 10.
- No backend files touched.
- Work sits on its own branch, not merged to `main` — the product owner
  reviews before integration, same as every backend phase this project has
  gone through.

## 12. Assumptions made while writing this brief — flag if wrong

- "Redesign the entire frontend" was read as: yes, including the already-
  shipped, already-tested Onboarding and Import Review screens, not just the
  net-new Main Dashboard — refined in place, not rebuilt from scratch, per
  Section 1's refinement/new-work distinction.
- Distributor Comparison (S17) rendering as a modal vs. a full screen is left
  to the builder's judgment (Section 5) since neither source document
  mandates one.
- No specific charting/animation/routing library is mandated (Section 8) —
  latitude given deliberately, on the assumption the product owner wants
  design judgment applied here, not a package name dictated by a document
  that can't see the current npm ecosystem.
- The dashboard nav shell (member switch, Add Data entry, disabled Analytics
  slot) has no prior design to preserve or contradict — treat it as
  greenfield within the Design Schema's constraints.

---

## Ready-to-paste prompt

Paste the block below as your first message to the coding agent (e.g.
Antigravity), after it has access to this repository:

> Read `Docs/superpowers/specs/2026-08-07-frontend-redesign-brief-for-coding-agent.md`
> in full. It is your complete brief for this task — it tells you which two
> other documents to read first (`Docs/PRDs/Design-Brief-Unifolio-updated.md`
> and `Docs/PRDs/Design-Schema-Unifolio.md`) and in what order. Follow the
> brief's guardrails, screen inventory, component list, backend API contract,
> and motion/accessibility requirements exactly. Work on a new git branch,
> never on `main` directly, and never modify anything under `backend/`. Use
> the `impeccable` skill's shape/critique/audit/polish workflow as your own
> build-verification loop per the brief's Section 7.2 (invoke it however
> your harness supports — a typed `/impeccable <command>` if available, plain
> language otherwise), targeting a Good-band score or better on every major
> screen. When you're finished, update
> `session.md` and `CLAUDE.md`'s Session State section per the brief's
> Section 10 before stopping — that update is part of the deliverable, not
> an afterthought.
