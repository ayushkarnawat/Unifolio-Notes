# Reference: Design Tokens

The executable half of the design system. The reasoning behind these choices is in
[the design language explanation](../explanation/design-language.md).

## Colour — light mode (brand identity locked)

| Token | Value | Usage |
|---|---|---|
| `color-bg` | `#FCFCFC` | Primary background |
| `color-ink` | `#111111` | Primary text and UI elements |
| `color-surface` | `#FFFFFF` | Cards on `color-bg` — pure white, one step lighter, so cards read as raised without a heavy shadow |
| `color-border` | `#E5E5E5` | Hairlines, input borders, table row separators |
| `color-text-secondary` | `#5C5C5C` | Captions, secondary labels, timestamps — never below WCAG AA against `color-bg` |
| `color-accent` | `#22C55E` | **Brand only** — primary actions, brand mark, links. Not reused for gain semantics |

## Colour — semantic

| Token | Value | Usage |
|---|---|---|
| `color-positive` | `#16A34A` | Gains, "up" indicators |
| `color-negative` | `#EF4444` | Losses, "down" indicators |
| `color-neutral-badge` | `#94A3B8` | "Unclassified" / "unverified" — Direct-vs-Regular, AMFI match confidence |
| `color-warning` | `#F59E0B` | Stale-data labels — old NAV, old TER period |

Three rules live in these four rows and each one is deliberate:

- `color-positive` is a **different green** from `color-accent`, darker and more muted,
  so a gain number is never mistaken for a brand action. Same hue family, functionally
  distinct — the Design Brief's colour-discipline rule made concrete.
- `color-neutral-badge` is explicitly **not** red or green. An unresolved classification
  is a different kind of information from a loss and must not be misread as one.
- `color-warning` is distinct from negative-red. Stale data is a freshness flag, not a
  loss.

## Colour — dark mode

| Token | Value | Usage |
|---|---|---|
| `color-bg-dark` | `#0F0F0F` | Near-black, not pure black — mirrors light mode's intentional softness |
| `color-ink-dark` | `#F5F5F5` | Primary text |
| `color-surface-dark` | `#1A1A1A` | Elevated cards |
| `color-border-dark` | `#2A2A2A` | Dividers |
| `color-text-secondary-dark` | `#A3A3A3` | Secondary text |
| `color-accent-dark` | `#22C55E` | Same hex as light. **Verify contrast against `#0F0F0F` at implementation.** If it fails, fall back to `#34D399` rather than casually changing the brand colour |
| `color-positive-dark` | `#22C55E` | Brightened from `#16A34A` for dark legibility |
| `color-negative-dark` | `#F87171` | Brightened from `#EF4444` |

**Every semantic colour pairs with a non-colour signal** — an arrow icon, label text, or
position. Colour is never the sole carrier of meaning.

## Typography

| Token | Family | Weight | Size | Line height | Usage |
|---|---|---|---|---|---|
| `type-display` | DM Sans | 700 | 32px | 1.2 | Hero numbers — total portfolio value |
| `type-h1` | DM Sans | 700 | 24px | 1.3 | Screen titles |
| `type-h2` | DM Sans | 600 | 18px | 1.4 | Section headers |
| `type-body` | Manrope | 400 | 15px | 1.5 | Default body |
| `type-body-medium` | Manrope | 500 | 15px | 1.5 | Emphasised body, row labels |
| `type-caption` | Manrope | 400 | 13px | 1.4 | Timestamps, secondary labels |
| `type-data` | Manrope | 500 | 15px | 1.4, **tabular-nums** | Every number in a table — units, NAV, amounts, percentages |
| `type-data-large` | DM Sans | 600 | 20px | 1.2, **tabular-nums** | Standalone large numbers — per-fund current value |

`font-feature-settings: "tnum"` is **mandatory** on every `type-data*` token. Numbers in
a column must line up. Confirm that the shipped DM Sans and Manrope files actually
include tabular figures before implementation — **if either does not, that is a blocking
finding to raise, not something to silently work around by swapping the font.**

## Spacing, shape, elevation

- 4px base unit: `4 / 8 / 12 / 16 / 24 / 32 / 48 / 64`. Table rows and form fields use
  12–16 internal padding; section-to-section uses 32–48; page margins start at 24
  (mobile) / 48 (desktop).
- `radius-sm` 8px — badges, small buttons, inputs. `radius-md` 12px — cards, table
  containers. `radius-lg` 20px — modals and larger surfaces.
- Elevation comes mostly from `color-surface` against `color-bg`, not from heavy drop
  shadows. Where a shadow is needed: `0 1px 2px rgba(0,0,0,0.06)` at rest, slightly
  stronger only on active/hover.

## Auth panel — a deliberate exception to the theme system

`AuthShowcasePanel` does not follow the application's light/dark theme. It is
**always dark**, and the 2026-08-19 editorial refinement records that as an
intentional, documented exception rather than an inconsistency. It is an
editorial hero surface, not application chrome; making it theme-aware would
mean designing and maintaining two of it.

It carries its own token family rather than overriding semantic tokens:

| Token | Role |
|---|---|
| `--auth-panel-bg` | Panel base |
| `--auth-panel-bg-2` | Secondary panel base, for the layered backdrop |
| `--auth-panel-ink` | Primary text on the panel |
| `--auth-panel-ink-soft` | Secondary text on the panel |
| `--auth-panel-glow` | Accent glow behind the editorial type |
| `--auth-panel-ghost` | Ghosted decorative element |
| `--auth-panel-ghost-soft` | Ghosted decorative element, lower emphasis |

Two motion tokens were added alongside them, extending rather than replacing
the existing three-token motion scale:

| Token | Role |
|---|---|
| `--motion-hero-reveal` | Reveal duration for the hero editorial sequence |
| `--motion-hero-stagger` | Per-line delay within that sequence |

The wider 2026-08-18 redesign of auth, onboarding and import review **changed
no token values at all**, and built its entire motion system from the three
pre-existing motion tokens (`--motion-fast` 150ms, `--motion-reveal` 400ms,
`--motion-page` 300ms), two stagger tiers, and exactly two shared-element
anchors (`fund-signal-ring`, `brand-mark`). The one stated visual exception is
a cream-and-gold pairing that exists only inside `OnboardingIllustration.tsx`'s
SVG fills and is not a token.

The 2026-08-19 mobile system survey separately confirmed that the mobile work
needs **no new design tokens**.

*Evidence: `08-evidence/documents/plans/2026-08-19-auth-left-panel-editorial-refinement.md`; `08-evidence/documents/specs/2026-08-18-auth-onboarding-import-review-visual-motion-redesign.md`; `08-evidence/documents/specs/2026-08-19-mobile-uiux-system-plan.md`*

## Still needs prototyping

The source document names its own unfinished work, and it is worth keeping visible: the
Fund Signal arc has not been tested at holdings-table row size, in a dense list of 30+
funds, or for dark-mode legibility. The *direction* is settled; the *execution* is not.
- **The dark-mode treatment of the mobile auth hero band** — the band shows the
  auth illustration crisp over an overlapping white card; how it behaves in
  dark mode was left open on 2026-08-19 (R-049).

## Related

- [Design language](../explanation/design-language.md)
