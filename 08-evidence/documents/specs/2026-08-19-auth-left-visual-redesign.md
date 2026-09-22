---
artifact: auth-left-visual-redesign
version: "2.0"
created: 2026-08-19
status: for-review
product: Unifolio
audience: A coding agent (e.g. Google Antigravity) executing the redesign
---

# Unifolio — Auth Screen Left Visual: Redesign Plan

**Scope: one file, one component.** `frontend/src/features/auth/AuthShowcasePanel.tsx`
only. No other file needs a new file created — this is a targeted internal
rewrite, not new architecture.

## 0. Supersedes note — read this first

An earlier document, `Docs/superpowers/specs/2026-08-18-auth-onboarding-import-review-visual-motion-redesign.md`,
describes a different concept for this same component in its §4.3/§5.5 (a
Fund-Signal-ring that evolves per step). That was never what got built — the
component that actually shipped (commit `75a1925`) is a chaos-loop-to-grid
performance-path graphic with milestone hover tooltips. **This document
supersedes §4.3 and §5.5 of the 2026-08-18 spec for this component
specifically** — everything else in that spec is unaffected.

**Version note**: v1 of this document proposed a different concept (scattered
particles converging along one circle into the brand-mark arc). That idea was
built out through several mockup rounds and ultimately dropped — not because
it was flawed technically, but because it kept reading as decorative rather
than as *the* story, and it leaned on the brand arc more than the actual
narrative needed. v2 (this version) replaces it entirely with a different
concept, below. If Antigravity has already started on the v1 concept, stop
and switch — v2 is the current direction, not an addition to v1.

## 1. Why this redesign, and what's wrong with the current version

The current panel tells a "chaos → order" story (scattered wireframe loops
resolving into a grid) but executes it in a way that reads as busy and
generic: a rocket icon glyph, a diamond-grid texture, a boxed "screen card"
container, a 5-point hover-tooltip system, and a green→gold gradient across
the path. It also doesn't fully deliver the story it's going for — "chaos"
and "order" are two disconnected visual zones side by side, not one thing
becoming another.

## 2. Recommended concept and story

**"Fragments align and sharpen into one view."** A handful (4) of thin,
rounded-rectangle panels — plain, unornamented, each just a soft outline —
start scattered: offset from center, tilted at small angles, faded, and
visibly out of focus (blurred). Over one deliberate motion, they glide toward
center, straighten to 0° rotation, and sharpen from blurred to crisp,
stacking into a single, perfectly aligned, fully-resolved plane. The other
three settle into faint, sharp, perfectly-aligned ghosts just behind it —
present, orderly, but no longer the focus.

This tells both halves of the brief in one motion: **scattered sources
coming together** (several panels → one) and **clarity resolving from
confusion** (blur → sharp). It needs no arc, no icon, no chart — the shapes
themselves, and what happens to them, are the entire story. It's also the
most minimal option considered: four plain rectangles, no generative
particle math, no procedural geometry.

## 3. Composition and key elements

- **Full-bleed, single scene.** The four panels *are* the visual — there's
  no separate outer "screen card" wrapper around them the way the current
  version boxes its graphic. Whatever was previously the outer bordered
  container is gone; the resolved panel itself is the focal shape.
- **Four panels, one clear role each**: three become quiet, aligned,
  sharp-but-faint background sheets; one becomes the fully opaque, crisp,
  green-bordered front sheet — the "one view."
- **No separate focal glow, icon, or decorative graphic** — the resolved
  front panel is the single focal point by virtue of being the only fully
  opaque, fully sharp element on screen once the motion completes.
- **Headline and subtitle live inside the same visual field**, bottom-
  anchored over a subtle vignette for legibility, not in their own separate
  header/footer strip.
- Optional, minor: a single thin accent line inside the front panel (like
  one clean row) — purely to keep the resolved shape from feeling like an
  empty box. Skippable if it reads as unnecessary once built.

## 4. Animation/motion concept

Reuse the existing play-once-per-session mechanism (`hasAnimatedInSession`
module flag) verbatim.

Sequence, over roughly the existing 3.2s duration:
1. Brief hold (roughly the first third) on the scattered state — four
   panels visibly offset, rotated, faded, blurred — long enough to actually
   register as "before," not just a flicker.
2. All four glide toward center, de-rotate to 0°, and sharpen from blurred
   to crisp, converging into perfect alignment. One panel (defined as the
   "front" one) lands fully opaque and crisp; the other three land at a low,
   quiet opacity directly behind it, still sharp and aligned — merged into
   the stack, not vanished.
3. Settle: hold the resolved state completely still. No looping pulse, no
   idle drift — the calm, static end-state *is* the payoff here, more so
   than in a particle-based concept, since "coming into focus and staying
   still" is the whole point.

`prefers-reduced-motion` / test environments: skip straight to the fully
resolved, aligned, sharp end-state — exactly as the current guards already
do (this concept makes that guard *simpler* to implement than the previous
one, since there's no path-length geometry to special-case, just transform/
opacity/blur values snapping straight to their end state).

## 5. Color treatment (existing palette only)

Two tones only:
- **Unresolved** = a cool, desaturated slate/grey outline, low opacity, blurred.
- **Resolved (front panel)** = Unifolio's own accent green outline (the same
  green used everywhere else in the product), full opacity, fully sharp.
- The three background ghosts resolve to a quiet neutral (not bright green —
  reserve full accent color for the one "front" panel only, so there's no
  ambiguity about which one is "the view").

No gold, no additional accent, no gradient fills — outlines only, on the
existing dark near-black backdrop (unchanged, intentional).

## 6. How it responds to the auth experience

`AuthShowcasePanel` already accepts a `step: AuthStep` prop and ignores it
(destructured as `_step`). Light-touch wiring for this concept: as the user
advances landing → email/phone → otp → link_account, allow the front panel's
border to gain very slight additional presence (e.g. a marginally stronger
glow, or the single internal accent line appearing only once the user is
past the first step) — small enough not to distract, enough that the panel
reads as responding to progress rather than being a static backdrop. This is
a nice-to-have: **don't let it block or complicate the core rebuild** in §8;
land the resolved concept first, wire this in only if it stays simple.

## 7. Assets/components to create

**None.** Four plain rounded rectangles, styled and animated in code — no
image, icon, or illustration files.

## 8. Exact implementation steps

1. **Remove**: `CHAOS_LOOPS`, `PATH_DEFINITION` and the whole SVG
   performance-path system, `GRID_COLUMNS`/`GRID_ROWS` + axis labels, the
   rocket icon glyph, the bordered inner "screen card" wrapper, the 5-point
   `MILESTONES` hover-tooltip system (state, handlers, markup), and the
   green→gold gradient. This concept needs essentially none of the current
   file's SVG machinery.
2. **Keep, reuse as-is**: `hasAnimatedInSession`, the `shouldReduceMotion`/
   `isTestEnv` guard pattern (simplified per §4), the outer dark
   radial-gradient backdrop, the bottom two-line subtitle copy pairing.
3. **Build the four panels** as simple absolutely-positioned elements (plain
   divs are sufficient — no SVG needed for this concept) with `transform`
   (translate + rotate), `opacity`, and `filter: blur()` each animating from
   a scattered starting value to their resolved value (three quiet-aligned,
   one front-and-crisp).
4. **Prefer `framer-motion`'s `animate` prop over hand-rolled
   `requestAnimationFrame`** for this concept specifically — the previous
   concept's manual rAF loop existed because it needed SVG path-length
   measurement (`getTotalLength`/`getPointAtLength`), which no longer
   applies here. Plain transform/opacity/blur transitions are exactly what
   `motion` (already an installed, imported dependency in this file) is
   for, and its own `useReducedMotion` (already imported) covers the
   reduced-motion guard natively — this should be a net simplification, not
   just a style swap.
5. Add the bottom vignette gradient behind the headline/subtitle for
   legibility, and mark the decorative visual `aria-hidden="true"`.
6. Optionally wire the `step` prop per §6, only once the core rebuild is
   solid.
7. **Verify**: reduced-motion jumps straight to the resolved state; mobile
   is unaffected (panel stays `hidden` below the `lg` breakpoint); the panel
   still reads well against the dark backdrop in both the light and dark
   app themes (the panel itself stays intentionally always-dark either way).

## 9. Replace vs. preserve — summary

| Replace | Preserve |
|---|---|
| Chaos-loop wireframe + performance-path SVG | `hasAnimatedInSession` play-once convention |
| Grid-matrix box + axis labels | `shouldReduceMotion`/`isTestEnv` guard pattern (simplified) |
| Rocket icon glyph | Dark backdrop treatment |
| Bordered inner "screen card" | Bottom subtitle copy |
| 5-point hover-tooltip system | `AuthShell` `visualSlot` integration |
| Gold/amber accent, all SVG path/particle math | — |

## 10. UX/performance concerns

- Four animated elements, transform/opacity/blur only — cheaper than the
  previous concept's per-frame SVG path-length measurement and hover
  mouse-tracking, with no interaction handlers needed at all.
- Keep blur radius modest (a few px) on the scattered state — heavy blur
  values can be costlier to composite on some browsers/GPUs than the visual
  benefit justifies at this small an element count.
- Mark the visual `aria-hidden="true"` — purely decorative, headline/subtitle
  already carry the real content.
- Treat the bottom vignette as a hard requirement — legibility over the
  resolved front panel must hold regardless of exact final positioning.
- Nothing about this concept needs testing beyond: reduced-motion end-state
  correctness, and that the "front" panel is unambiguously distinguishable
  from the three background ghosts at every viewport size this panel
  renders at (`lg` and above).

---

## Ready-to-paste prompt

> Read `Docs/superpowers/specs/2026-08-19-auth-left-visual-redesign.md` in
> full before writing any code — note its "Version note" in §0: this is v2,
> and it fully replaces the v1 concept (particles converging into an arc) if
> any work on that was started. It replaces the current implementation of
> `frontend/src/features/auth/AuthShowcasePanel.tsx` only — no other files
> need to change or be created. Build the "fragments align and sharpen"
> concept exactly as described in §2–§5: four plain rounded-rectangle panels,
> scattered/rotated/blurred/faded at rest, gliding into one crisp aligned
> stack with exactly one fully-opaque green "front" panel and three quiet
> aligned ghosts behind it. Prefer `framer-motion`'s `animate` prop over
> hand-rolled animation per §8.4 — this concept doesn't need the previous
> version's SVG path-length machinery. Follow §9's replace/preserve table.
> Wire the `step` prop per §6 only as a light-touch addition once the core
> rebuild works. Verify reduced-motion and mobile behavior per §8.7 before
> considering this done. Work on a new git branch, never on `main` directly.
> When finished, update `session.md` and `CLAUDE.md`'s Session State section
> noting this replaced the prior chaos-loop/grid version of the panel.
