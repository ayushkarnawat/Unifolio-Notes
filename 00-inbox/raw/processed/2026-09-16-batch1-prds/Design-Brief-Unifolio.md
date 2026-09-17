---
artifact: design-brief
version: "1.0"
created: 2026-07-22
status: draft
product: Unifolio
scope: Cross-product (all MF MVP modules)
---

# Design Brief: Unifolio

## Purpose & Scope

This document sets the visual and interaction *direction* for Unifolio — the principles
every screen should follow and why. It intentionally does not specify exact hex values
beyond what's already locked, spacing scales, or component-by-component specs — that's
the Design Schema's job (next document). Think of this as "what Unifolio should feel like
and why," and the Design Schema as "the exact system that produces that feeling,
consistently, across every screen."

It covers all four MF MVP modules (CAS Parser v2 / Import, Signup & Onboarding, Main
Dashboard, MF Analytics Dashboard) as one product, not four separate visual languages.

## Brand Foundation

**Name:** Unifolio

**Colors** (from brand identity, locked):
- `#111111` — Ink. Primary text, primary UI elements on light backgrounds.
- `#FCFCFC` — Near-white. Primary background, not pure white — this softness is part of
  the brand, not an accident, and should carry through to the dark-mode counterpart
  (an equivalent near-black rather than pure `#000000` — see Open Questions).
- `#22C55E` — Accent green. Used deliberately and sparingly (see Color Discipline below)
  — this is Unifolio's *one* signature color, not a palette to build variations from casually.

**Typography** (from brand identity, locked):
- **DM Sans** — headings and subheadings.
- **Manrope** — body copy, accents, taglines, subtext.

**Logo:** wordmark "Unifolio" with the accent green appearing as a small arc inside the
"o" — reads as a dial/gauge motif. This detail matters: it's the one place the brand
identity already introduces a shape language (an arc, a partial circle, a sense of
measurement/progress) beyond flat color blocks — worth carrying into the product's
visual vocabulary (see Signature Element below), not treating as logo-only decoration.

## Design Philosophy

Five principles, each traceable back to a decision already locked in the PRDs — this
section exists so the Design Schema and every screen built after it has a single source
of truth to check against, rather than each designer/screen re-deriving intent.

### 1. Apple-inspired, not Apple-generic
"Simple, crisp, self-explanatory, not childish, classy and rounded" was the original brief.
In practice this means: generous whitespace over dense data-dumping, one clear visual
hierarchy per screen (not three competing ones), rounded corners as the default shape
language (not sharp/newspaper-style, not the near-black-plus-acid-accent look that's
become a generic "AI-generated" default — Unifolio's near-white, ink, and *muted* green
should read as considered, not templated). "Rounded and classy" also means restraint:
the accent green is a signal color, not a decoration — see Color Discipline.

### 2. Game-like pacing, never game-like mechanics
Locked in PRD-02: no points, badges, streaks, or confetti anywhere in the product, not
just onboarding. "Game-like" means the *feel* of a well-crafted setup sequence — deliberate
reveals, a clear sense of progress, a satisfying moment when real data appears — expressed
through motion and sequencing, not through gamification UI elements. This applies
product-wide: the same restraint that keeps onboarding from feeling unserious to an HNI
user should govern how the Main Dashboard reveals data after a CAS import, how the
Analytics Dashboard reveals a fund score, and so on.

### 3. One flow, not two
Also locked in PRD-02, but a product-wide principle: Unifolio does not fork its interface
by user segment (retail vs. HNI) in this version. The single flow has to read as premium
and serious to a demanding HNI user *and* approachable to a first-time retail investor —
that tension gets resolved through tone and content, not through visual variants.

### 4. Numbers are the product — treat them that way
This is a financial data product; the holdings table, allocation views, and scorer are the
actual value being delivered, not decoration around a marketing page. That means:
tabular (monospaced-width) figures for all numeric data so columns of numbers align
and are scannable at a glance; a strict, semantic color convention for gains/losses (see
Color Discipline); and every number that's shown needs to be traceable back to something
real — per PRD-01/03/04's shared "100% accuracy" commitment, the visual design itself
should never imply more precision or confidence than the underlying data actually has
(e.g., a stale-NAV or unclassified-status number needs to look visually distinct from a
fresh, confirmed one — this is a design requirement flowing directly from those PRDs'
edge-case handling, not just a data requirement).

### 5. Proven structure, distinctive execution
Per PRD-03: the Main Dashboard and Analytics Dashboard follow the functional pattern
already validated by Mprofit and the broader 11-competitor set (holdings table +
allocation + SIPs + gains) — the *information architecture* is not the place to take risks.
The distinctiveness Unifolio is going for lives in *execution*: typography, color discipline,
motion, and the "innovative, unique way" of displaying holdings the original product brief
asked for (see Signature Element) — not in reinventing what data goes where.

## Color Discipline

- Ink (`#111111`) and near-white (`#FCFCFC`) do the vast majority of the work — text,
  surfaces, borders, structure.
- Accent green (`#22C55E`) is reserved for: the one primary action per screen, the
  brand's own mark, and (see below) positive-value semantics. It should never appear as
  a background fill for large areas or as decorative color — if a screen has more than one
  or two accent-green elements competing for attention, that's a signal something's
  over-designed, not under-designed.
- **Semantic gain/loss color is a separate system from the brand accent**, not the same
  green reused. Reusing the brand accent for "positive" would overload its meaning (is it
  the primary action, or is it "this fund is up"?) and would leave no clean brand-distinct
  color for losses. Recommend a semantic green (can coordinate with `#22C55E` in hue
  family but should be treated as functionally distinct) paired with a semantic red for
  losses — the exact red value is not yet defined and is a real open item (see Open
  Questions), not something to default silently.
- Dark mode needs its own near-black (not pure `#000000`, matching the near-white
  background's intentional softness) and its own calibration of the accent and semantic
  colors for contrast — this is Design Schema work, flagged here as a requirement, not
  specified here.

## Typography Discipline

- DM Sans for headings/subheadings carries the brand's geometric, confident character —
  use it for screen titles, section headers, and the large "hero" numbers (e.g., total
  portfolio value) where a number itself functions as a heading.
- Manrope for everything else — body text, table contents, captions, form labels, button
  text — needs to stay legible at small sizes since a data-dense holdings table will push
  it there.
- **Tabular (fixed-width) numerals are a hard requirement**, not a nice-to-have, anywhere
  numbers appear in a column (holdings table, allocation percentages, XIRR comparisons).
  Both DM Sans and Manrope need to be confirmed to support tabular figure variants — a
  technical check for the Design Schema stage, flagged here so it isn't discovered late.

## Layout & Information Density

Baseline: Mprofit's and the broader competitive set's proven holdings-table-plus-
allocation-plus-gains pattern (per PRD-03) — dense enough to show real portfolio data
without forcing drill-downs for the core numbers, but with more breathing room than a
typical Indian fintech dashboard tends to allow, consistent with the Apple-inspired
principle. Exact grid, spacing scale, and breakpoints are Design Schema work.

## Motion & Interaction Principles

- Reveals over pop-ins: when real data appears (import complete, dashboard loads,
  analytics compute), it should feel like an intentional reveal, not an instant swap — this
  is where "game-like pacing" (Principle 2) actually shows up visually.
- Micro-interactions (hover states, confirmations) stay quiet and fast — motion earns its
  place by clarifying what happened, not by being noticed for its own sake.
- Respect reduced-motion preferences — a straightforward accessibility baseline, not
  optional.

## Data Visualization Language

Given three of four modules are fundamentally about presenting financial data
correctly and legibly:
- Allocation views (AMC, category — per PRD-04) should use a consistent chart language
  across the product (e.g., one donut/bar convention, not different chart types per
  screen for the same kind of data).
- Gain/loss, direct/regular, and confidence-badge indicators (per PRD-01's Import Review
  and PRD-03's holdings table) need a single, consistent badge/tag visual system used
  everywhere the same concept appears — a "Direct" badge should look identical whether
  it's on the Import Review screen or the Main Dashboard.
- The fund/portfolio scorer (PRD-04, FR-5–FR-7) needs a visual treatment that
  communicates "this is a modeling judgment, shown with its reasoning" — not a bare
  number or star rating presented as objective fact, per that PRD's explicit requirement.

## Signature Element

The original product brief asked to "display mutual funds in a very innovative, unique
way, if possible, not just a static name." The logo's arc/dial motif (see Brand Foundation)
is a natural seed for this: a small, consistent visual device — built from the same
arc/gauge language as the logomark — that gives each fund or allocation a glanceable
visual identity beyond a name and a number, without becoming decorative gamification
(which Principle 2 rules out). This needs actual exploration/prototyping, not just
description in prose — flagged as the first concrete thing to prototype in the Design
Schema stage, not resolved here.

## Voice & Tone

- Active voice, plain terms, named by what the person controls — not system internals
  (e.g., "Import your CAS," not "Initiate CAS parsing job").
- Errors are specific and direct, never apologetic filler — say what happened and what to
  do next, in the interface's voice.
- Empty states are invitations to act, not dead ends — especially relevant given PRD-03's
  "family member with no CAS yet" and PRD-04's "insufficient history" states, which need
  to read as next steps, not failures.
- Consistent vocabulary end-to-end: whatever a button calls an action, the confirmation
  and result use the same word (a pattern already implicit in PRD-01's confirm-flow
  language and worth stating explicitly here so it's followed everywhere).

## Accessibility Baseline

- Responsive down to mobile — non-negotiable given the target users are consumer
  investors, not enterprise desktop users.
- Visible keyboard focus states throughout.
- Color is never the sole carrier of meaning (gain/loss, direct/regular, confidence level)
  — needs a secondary signal (icon, label, position) alongside color, especially important
  given how central the green/red semantic system is to this product.
- Dark/light mode both need to meet contrast standards independently, not just the
  light mode.

## What This Document Does Not Cover (Design Schema's job)

- Exact hex values for semantic colors, dark-mode palette, and any secondary/tertiary
  colors beyond the three locked brand colors.
- Spacing scale, grid system, breakpoints.
- Component-by-component specs (button states, input states, badge system exact
  visual spec, chart component library).
- The actual prototyped Signature Element design.
- Type scale (exact sizes/weights/line-heights for each DM Sans/Manrope role).

## Open Questions

- [ ] Semantic loss color (red) — not defined in the brand identity provided; needs a
      value that works alongside `#22C55E` without visually competing with the brand
      accent — Owner: Ayush (direction) + Claude (execution options)
- [ ] Dark-mode near-black and full dark-mode palette — brand identity only specifies the
      light-mode trio — Owner: Claude to propose, Ayush to confirm
- [ ] You mentioned additional design references, a "design skeleton," and design values
      beyond the brand identity PDF already shared — if there's more to share (mood
      boards, competitor screens you specifically like/dislike, existing sketches), this is
      the right moment, before the Design Schema locks specifics — Owner: Ayush
- [ ] Signature Element (arc/dial motif applied to fund display) needs actual visual
      exploration, not just this description — first prototyping task for Design Schema
      stage — Owner: Claude, with Ayush review

## Appendix

### Related Documents
- PRD-01: CAS Parser v2 — Import Review confidence-badge pattern
- PRD-02: Signup & Onboarding — Design Handoff Alignment section (source of Principles
  2 and 3 above)
- PRD-03: Main Dashboard — competitive baseline pattern, badge/status display needs
- PRD-04: MF Analytics Dashboard — scorer visual-treatment requirement, allocation
  chart needs
- `Unifolio_Brand_Identity.pdf` (uploaded) — source of all locked brand foundation values

### Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-07-22 | Claude (PM partner) | Initial draft, synthesizing brand identity and all Design Handoff Alignment notes from PRDs 1–4 |
