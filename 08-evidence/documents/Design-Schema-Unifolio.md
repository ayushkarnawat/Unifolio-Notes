---
artifact: design-schema
version: "1.0"
created: 2026-07-22
status: draft
product: Unifolio
scope: Cross-product (all MF MVP modules)
---

# Design Schema: Unifolio

## Purpose

This is the executable design system the Design Brief pointed to: exact tokens and
component specs, so every screen built after this is consistent by construction rather
than by careful manual matching. Where the Design Brief said "this is a decision, not
specified here," this document makes that decision.

## Color Tokens

### Light mode (primary — brand identity locked)

| Token | Value | Usage |
|---|---|---|
| `color-bg` | `#FCFCFC` | Primary background |
| `color-ink` | `#111111` | Primary text, primary UI elements |
| `color-surface` | `#FFFFFF` | Cards/elevated surfaces sitting on `color-bg` — pure white, one step lighter than the near-white background, so cards read as raised without a heavy shadow |
| `color-border` | `#E5E5E5` | Hairline dividers, input borders, table row separators |
| `color-text-secondary` | `#5C5C5C` | Captions, secondary labels, timestamps — never below WCAG AA against `color-bg` |
| `color-accent` | `#22C55E` | Brand accent — primary actions, brand mark, links. Reserved per Design Brief's Color Discipline; not reused for gain semantics |

### Semantic tokens (resolved — new)

| Token | Value | Usage | Rationale |
|---|---|---|---|
| `color-positive` | `#16A34A` | Gains, "up" indicators | Deliberately a *different* green from `color-accent` (`#22C55E`) — darker/more muted, so a gain number never gets mistaken for a brand action, per Design Brief's rule that these must stay functionally distinct even within the same hue family |
| `color-negative` | `#EF4444` | Losses, "down" indicators | Same saturation/lightness family as `color-positive` so the pair reads as one deliberate system, not two unrelated colors bolted together |
| `color-neutral-badge` | `#94A3B8` | "Unclassified" / "unverified" status (Direct-Regular, AMFI-match confidence) | Explicitly not red or green — those are reserved for gain/loss; an unresolved classification is a different kind of information and needs its own visual language so it's never misread as a loss |
| `color-warning` | `#F59E0B` | Stale-data labels (old NAV, old TER reference period) | Distinct from negative-red — stale data isn't a loss, it's a freshness flag, per PRD-03's stale-NAV edge case |

### Dark mode (resolved — new)

| Token | Value | Usage |
|---|---|---|
| `color-bg-dark` | `#0F0F0F` | Primary background — near-black, not pure `#000000`, mirroring the light mode's intentional softness |
| `color-ink-dark` | `#F5F5F5` | Primary text on dark |
| `color-surface-dark` | `#1A1A1A` | Elevated cards on dark bg |
| `color-border-dark` | `#2A2A2A` | Dividers on dark |
| `color-text-secondary-dark` | `#A3A3A3` | Secondary text on dark |
| `color-accent-dark` | `#22C55E` | Same hex as light mode — verify contrast against `#0F0F0F` at implementation time; if contrast testing fails, fall back to a slightly brightened variant (`#34D399`) rather than changing the brand color casually |
| `color-positive-dark` | `#22C55E` | Slightly brightened vs. light mode's `#16A34A` for dark-background legibility |
| `color-negative-dark` | `#F87171` | Slightly brightened vs. light mode's `#EF4444` for dark-background legibility |

**Every semantic color pairs with a non-color signal** (arrow icon, label text, or position)
per the Design Brief's accessibility baseline — color is never the sole carrier.

## Typography

| Token | Family | Weight | Size | Line Height | Usage |
|---|---|---|---|---|---|
| `type-display` | DM Sans | 700 | 32px | 1.2 | Hero numbers (total portfolio value) |
| `type-h1` | DM Sans | 700 | 24px | 1.3 | Screen titles |
| `type-h2` | DM Sans | 600 | 18px | 1.4 | Section headers |
| `type-body` | Manrope | 400 | 15px | 1.5 | Default body text |
| `type-body-medium` | Manrope | 500 | 15px | 1.5 | Emphasized body (row labels) |
| `type-caption` | Manrope | 400 | 13px | 1.4 | Timestamps, secondary labels |
| `type-data` | Manrope | 500 | 15px | 1.4, **tabular-nums** | Every number in a table/column — units, NAV, amounts, percentages |
| `type-data-large` | DM Sans | 600 | 20px | 1.2, **tabular-nums** | Standalone large numbers (per-fund current value) |

`font-feature-settings: "tnum"` (or the equivalent tabular-figure OpenType feature) is
mandatory on every `type-data*` token — confirm both DM Sans and Manrope's shipped
font files include tabular figure support before implementation; if either doesn't, that's
a blocking finding to raise, not something to silently work around with a different font.

## Spacing Scale

4px base unit: `4 / 8 / 12 / 16 / 24 / 32 / 48 / 64`. Table rows and form fields use the
`12–16` range for internal padding; section-to-section spacing uses `32–48`; page-level
margins use `24` (mobile) / `48` (desktop) as starting points, adjusted during build.

## Shape & Elevation

- `radius-sm` = 8px — badges, small buttons, input fields
- `radius-md` = 12px — cards, table containers
- `radius-lg` = 20px — modals, larger surfaces
- Elevation is mostly achieved through `color-surface` vs. `color-bg` contrast, not heavy
  drop shadows — consistent with the Apple-inspired, restrained direction. Where a
  shadow is needed: `0 1px 2px rgba(0,0,0,0.06)` for resting cards, slightly stronger only
  on active/hover states.

## Component Specs

### Badge / Status Tag
Single component used everywhere a status appears (Direct/Regular, AMFI-match
confidence, unclassified, stale-data flag, ARN-invalid flag) — per Design Brief's rule that
the same concept must look identical everywhere it appears.
- Shape: `radius-sm`, `type-caption` weight 500, horizontal padding 8px, vertical 2px.
- Variants: `positive` (Direct, high-confidence), `negative` (n/a for badges — losses live
  in data cells, not badges), `neutral` (unclassified/unverified, `color-neutral-badge`),
  `warning` (stale data, invalid ARN, `color-warning`).
- Always paired with a 1–2 word label, never color-only.

### Fund Signal (from Design Brief's Signature Element)
- Structure: a small arc (SVG, using the logomark's exact arc geometry/stroke-width
  ratio, not a generic circular progress ring) at a fixed size in the holdings table row
  (proposed 24×24px at row-scale, confirm during prototyping), expanding to arc +
  sparkline (last 30/90/365 days NAV trend, user-selectable period) on tap/hover or in a
  wider viewport.
- Fill/color: `color-positive`/`color-negative` matching the period's gain/loss direction —
  never `color-accent`, keeping brand and performance signal separated per Color
  Discipline.
- Motion: arc fills from empty on data load (the "reveal," per Motion Principles), not an
  instant paint — respects `prefers-reduced-motion` by skipping straight to final state.
- **Status: needs prototyping** (per Design Brief) — this spec is a starting point for that
  work, not a final, implementation-ready component.

### Holdings Table Row
Columns per PRD-03 FR-1–FR-3: Fund Signal, fund name (`type-body-medium`), Direct/
Regular badge, avg NAV, units, current NAV, invested, current value, current profit,
realized/unrealized/today's gain (all `type-data`, positive/negative colored, paired with
↑/↓ icon per accessibility rule), last-updated date (`type-caption`, `color-warning` badge
if stale per PRD-03's edge case).

### Charts
- Allocation: single donut-chart convention product-wide (per Design Brief), segments
  labeled with both absolute value and percentage (not percentage alone), using
  `color-accent` plus a small extended palette for multi-segment allocation (AMC/category)
  — extended palette is a Design Schema gap to fill during prototyping, not yet specified
  beyond "derive from the same restrained, muted family as the semantic colors, not
  a generic rainbow chart palette."
- Benchmark comparison: grouped bar chart (user fund vs. benchmark), absolute return
  labeled above each bar, per PRD-04's FR-8/FR-9.

### Scorer Display
Per PRD-04 FR-7 and Design Brief's data-visualization principle: the score is shown with
its tier (visual, e.g. a short horizontal band across the percentile range, not a bare star
count that implies false universality) plus an expandable "why this score" breakdown
showing the risk-adjusted-return tier and cost adjustment as separate, labeled lines —
never a single unexplained number.

## Motion Tokens

| Token | Value | Usage |
|---|---|---|
| `motion-fast` | 150ms, ease-out | Hover/focus micro-interactions |
| `motion-reveal` | 400ms, ease-in-out | Data reveals (Fund Signal arc fill, dashboard load-in) |
| `motion-page` | 300ms, ease-in-out | Screen transitions |

All respect `prefers-reduced-motion: reduce` — reveals collapse to instant final-state
rendering, no exceptions.

## Dark/Light Mode Rule

Mode follows system preference by default, with a manual override available in settings
— both modes are first-class (per Design Brief's accessibility baseline), not a light-mode
product with a dark mode bolted on. Every component spec above must be verified in
both modes before being called complete, not just designed once and assumed to
translate.

## Accessibility Checklist (inherited from Design Brief, made concrete here)

- [ ] All `color-positive`/`color-negative` usages paired with icon or label
- [ ] All text/background pairs meet WCAG AA (AAA where feasible, per the research
      note in the Design Brief on investment-dashboard accessibility practice)
- [ ] Keyboard focus states defined for every interactive component (buttons, badges if
      tappable, table rows if expandable)
- [ ] `prefers-reduced-motion` respected on every motion token
- [ ] Tabular figures confirmed available in both typefaces before build

## What Still Needs Prototyping (not resolved by this document)

- Fund Signal at actual table density (30+ row list) — the single highest-risk open item,
  since it's the product's one genuine visual differentiator and hasn't been visually
  tested yet.
- Extended chart palette beyond the core semantic/accent colors.
- Dark-mode accent color contrast verification (`color-accent-dark` fallback if needed).

## Appendix

### Related Documents
- Design Brief: Unifolio — source of all principles this schema executes
- PRD-01, PRD-02, PRD-03, PRD-04 — functional requirements each component serves

### Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-07-22 | Claude (PM partner) | Initial draft — resolves loss-color and dark-mode palette from Design Brief's open questions, specifies Fund Signal, badge, table, chart, and scorer components |
