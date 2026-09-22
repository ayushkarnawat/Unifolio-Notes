---
artifact: auth-onboarding-import-review-visual-motion-redesign
version: "1.0"
created: 2026-08-18
status: for-review
product: Unifolio
audience: A coding agent (e.g. Google Antigravity) executing the visual/motion redesign
---

# Unifolio — Auth → Onboarding → CAS Import → Review: Visual & Motion System Design

**This document is a handoff, not a suggestion. Read it in full before writing any
code.** It is narrower and more prescriptive than a general UI brief: it does not
ask you to invent a visual direction — the direction is decided (below) — it asks
you to execute a specific, already-scoped visual/motion continuity pass across four
existing, functioning flows.

## 0. Read these first, in this order

1. `CLAUDE.md` (repo root) — non-negotiables (stack locked, `Decimal` discipline,
   no gold-plating) and Session State for what's built/merged.
2. `frontend/src/styles/tokens.css` — the actual, current token source of truth.
   This spec changes **zero** values in this file. Read it so you use the real
   token names, not approximations.
3. `Docs/PRDs/Design-Schema-Unifolio.md` / `Design-Brief-Unifolio-updated.md` —
   background on why these tokens exist. Useful context, not a source of new
   requirements for this task.
4. This spec is otherwise self-contained — it does not depend on an inspiration
   folder or external references you need to go find; every visual decision it
   makes is already resolved below.

## 1. Why this spec exists, and what it is not

Four flows already exist, are functionally complete, and are not being
restructured: `AuthEntryFlow.tsx` (auth), `OnboardingFlow.tsx` (onboarding, with
its steps co-located in `features/auth/`), `ImportFlow.tsx` (CAS import), and
`ReviewTable.tsx` (review). Verified by inspection before writing this spec:

- `AuthEntryFlow.tsx` **already** renders a persistent split-screen shell (a
  rounded-3xl surface container, logo top-left, form content centered, a static
  `AuthShowcasePanel` on the right) — Direction A's split-screen idea is already
  half-built. What it does *not* do: every step swap is a flat `animate-in
  fade-in duration-200` full-content replacement with no exit animation and no
  directional logic, and `AuthShowcasePanel` renders **identical** content
  regardless of which step is active.
- `OtpVerify.tsx` uses one plain `<input type="text">` for the 6-digit code —
  no segmented cells.
- `TrustPrimer.tsx` and the `Q1Name`–`Q4Household.tsx` steps use icon-in-circle
  bullets (lucide-react icons), no illustration artwork at all.
- `ReviewTable.tsx` has no motion of any kind.
- `motion` (Framer Motion v12) and `gsap` are installed dependencies, but only
  `motion` is actually imported anywhere, and only inside
  `components/ui/charts/` (pie-chart mount animation). Nothing in auth,
  onboarding, import, or review uses either library today.

So this spec's job is **refinement and completion of an already-started visual
direction**, not a re-skin and not greenfield work. Scope:

- **In scope**: visual/motion/component-layer changes to the four flows above,
  on both `frontend/src/features/*` (web/desktop) and `frontend/src/mobile/*`
  (mobile shell).
- **Out of scope**: any change to `AuthEntryFlow`'s `Step` union, `OnboardingFlow`'s
  step sequence, `ImportFlow`'s `Step` union, `ReviewTable`'s confirm/override
  logic, or any backend code. Two narrow, named exceptions to "no structural
  change" are called out in §4.2 and §4.6.
- **Out of scope**: new color tokens, new fonts, new spacing/radius values.
  `tokens.css` is the only UI palette everywhere in this redesign, with exactly
  one controlled exception (§2, bullet 1).

## 2. Non-negotiable guardrails

- **One color-system exception, tightly scoped**: a warm cream/gold tone may
  appear **only** inside onboarding illustration artwork (`OnboardingIllustration`,
  §4.5) — baked into that component's own SVG `fill`/`stop-color` attributes.
  It must never appear as a Tailwind utility class, a CSS custom property, a
  button/border/focus-ring/badge color, or in any component outside that one
  illustration slot, in either light or dark mode. A reviewer should be able to
  verify this by grepping for warm hex values and finding them nowhere but
  inside `OnboardingIllustration.tsx`'s own markup.
- **State machines and business logic are frozen.** Exactly two structural
  exceptions are permitted, both purely to enable visual continuity: (1)
  hoisting the auth shell above the step switch inside `AuthEntryFlow.tsx`
  (§4.2), and (2) extracting each questionnaire step's outer full-page wrapper
  so it can be slotted into a shared card-stack shell (§4.6). Neither changes
  a `Step` union, a handler, or any piece of state. If executing this spec
  visually seems to require any other structural change, stop and report it
  rather than implementing it.
- **No backend changes.** If a visual requirement here seems to need one
  (it shouldn't), stop and report it.
- **Preserve existing test coverage.** Run `npm test` and `npx tsc -b --noEmit`
  clean before and after. Existing flow tests (`AuthEntryFlow.test.tsx`,
  `OnboardingFlow.test.tsx`, `ImportFlow.test.tsx`, `ReviewTable.test.tsx`, etc.)
  should keep passing unless a specific, documented behavior changed — list any
  such change in your completion report.
- **Work on its own branch**, not `main`, per this repo's established
  convention. Do not push or open a PR without explicit go-ahead.
- **Respect `prefers-reduced-motion`** on every transition this spec adds,
  consistent with `tokens.css`'s existing collapse-to-instant convention —
  verify by actually toggling the setting.

## 3. Cross-journey design system — what's persistent, what evolves

The goal is that Auth, Onboarding, CAS Import, and Review read as one continuous
Unifolio product, not four separately redesigned screens. This table is the
contract:

| Property | Persistent everywhere | Evolves per flow |
|---|---|---|
| Color tokens (`--color-*`) | ✅ identical in all four flows | — |
| Typography (DM Sans display / Manrope body, full 8-token scale) | ✅ | — |
| Spacing (4px scale) / radius (`sm`/`md`/`lg`) / shadow tokens | ✅ | — |
| Motion timing/easing vocabulary (`motion-fast`/`reveal`/`page`) | ✅ same three values used everywhere, never a bespoke duration | — |
| Motion philosophy: calm, progressive construction, continuity over flashy fade/slide | ✅ | — |
| Container chrome (rounded-3xl surface, `--color-border` hairline, shadow) | ✅ same card language wherever a "screen in a card" pattern applies | — |
| Layout shape | — | Auth: split-screen (form + visual anchor). Onboarding (questionnaire steps only): a card-stack deck — the active step as a front card with 1–2 blank placeholder cards tilted behind it (§4.6); `add_family`/CAS-upload onboarding steps keep their current full-page treatment, unchanged. CAS Import: tabbed two-path container → wizard-style step swap. Review: full-width dense data table. |
| The "visual anchor" per flow | — | Auth: `AuthShowcasePanel`'s Fund Signal ring, evolving step-to-step (§4.3). Onboarding: the card stack itself (§4.6) plus `OnboardingIllustration` inside the front card, the one place warm color lives. CAS Import: drop-zone + `ImportFileProgressList`. Review: the table itself + status badges — no illustration, no decorative visual anchor; density and legibility *are* the visual language here. |
| Reveal intensity | — | Auth: full section-level staggered reveal (form is the entire content). Onboarding questionnaire steps: a "dealt card" transition (§4.6, §5.2) instead of a plain reveal. CAS Import: staggered only where content is genuinely list-like (file rows). Review: deliberately muted — container-level only, per §4.7. |

## 4. Component changes

### 4.1 `OtpInput` (new)

New file: `components/ui/otp-input.tsx`. Segmented 6-cell input replacing the
raw `<input>` in `OtpVerify.tsx` (lines 79–89 today). Auto-advance on digit
entry, backspace moves to and clears the previous cell, paste of a full 6-digit
string fills all cells, numeric-only (`inputMode="numeric"`). Active cell uses
the same focus treatment already established elsewhere
(`focus:ring-2 focus:ring-[var(--color-accent)]/20`, `border-[var(--color-accent)]`)
— no new visual vocabulary. One component, used identically for both the phone
and email OTP channel (the existing `channel` prop on `OtpVerify` is unaffected).

### 4.2 Auth shell — formalize what already exists (structural exception 1 of 2)

`AuthEntryFlow.tsx` already renders a persistent outer container (lines
227–357): logo, footnote, and `AuthShowcasePanel` never unmount between steps —
only the inner `<div className="my-auto w-full">` content (line 253) is
conditionally swapped. This is extracted into an explicit `AuthShell` component
so the persistence is structural and intentional rather than incidental, and so
the transition logic in §5 has one home:

- Extract the outer grid/container, logo block, and footnote (currently inline
  JSX at lines 234–251 and 347–356) into `AuthShell.tsx`, accepting a
  `visualSlot` (the evolving `AuthShowcasePanel`, §4.3) and a `formSlot`
  (the current step's form component) plus a `step` identifier for
  directionality (§5.2).
- This is the one place this spec touches control flow: `AuthEntryFlow.tsx`'s
  `Step` union, handlers, and state are untouched — only the JSX that currently
  renders the shell inline moves into `AuthShell`, called with the same
  step-driven conditional that already exists today.

### 4.3 `AuthShowcasePanel` — evolves, is not replaced per step

Keep the existing ring/headline/metrics/footer structure exactly as built
(same Fund Signal ring geometry, same DOM shape) as the one continuous visual
anchor for the whole auth flow. What changes is content, driven by a new `step`
prop instead of the panel being static:

| Step | Headline tone | Ring fill fraction |
|---|---|---|
| `landing` | Current copy, unchanged ("A unified view of everything you own.") | Current default (0.8) |
| `email` / `phone` | Progress-toned ("Almost there — verifying your identity") | Ticks up slightly (e.g. 0.85) |
| `otp` / `email_otp` | ("One code away") | Higher still (e.g. 0.92) |
| `link_account` | Closing-state copy | Final fraction (1.0) |

This is a literal implementation of the motion reference's "left panel
progressively builds" cue as **one element evolving**, not four different
panels being swapped — see §5.5 for how the ring fill itself animates as a
shared element, not a re-render.

### 4.4 `ImportFileProgressList` (new)

New file: `features/import/ImportFileProgressList.tsx`, mounted inside the
existing dashed drop-zone in `UploadForm.tsx`. One row per file: filename,
status icon (pending/uploading/done/error, reusing the existing lucide-react
icon set already used in `ReviewTable.tsx`), progress bar. Reuses `Badge` for
status where a badge (not just an icon) reads more clearly.

### 4.5 `OnboardingIllustration` (new)

New file: `features/auth/OnboardingIllustration.tsx` (co-located with the other
onboarding step components — confirmed they all live in `features/auth/`,
there is no separate `features/onboarding/`). Inline SVG, soft rounded shapes,
the warm cream/gold palette lives **only** inside this file's own SVG `fill`/
`stop-color` values (§2). Slotted into `TrustPrimer.tsx` (supplementing, not
necessarily replacing, the existing icon-in-circle bullets at lines 32–59) and
`Q1Name.tsx`–`Q4Household.tsx`. This is new territory, not a refinement — these
screens currently have zero illustration.

### 4.6 `OnboardingCardStack` — card-deck structure (structural exception 2 of 2)

Per your reference images (a stacked-deck teaser and a tilted-card layout),
the questionnaire portion of onboarding — `trust_primer`, `q1_name`,
`q2_investing`, `q3_purpose`, `q4_household` only — moves from today's
full-page-per-step layout to a card-deck: the active step renders as a front
card, with exactly 2 blank placeholder cards tilted and dimmed behind it
(matching the depth shown in the approved mockup), inside a shared,
persistently-positioned deck container. **Explicitly out of scope for the
card-stack treatment**: `add_family`, `cas_upload`, `family_cas_upload`,
`upload_my_cas`, `parse_queue` — these are multi-field/upload surfaces, not
single-question cards, and keep their current full-page layout untouched
(section-level `motion-reveal` only, per §5.3 tier 1).

**Why this is a named structural exception**: today, `TrustPrimer.tsx` and
`Q1Name.tsx`–`Q4Household.tsx` each render their own full-page wrapper
(`min-h-dvh w-full ... flex items-center justify-center`) plus their own
centered card — there is no shared shell to slot into yet
(`OnboardingFlow.tsx`'s `renderStep()` is a plain switch, confirmed by
inspection). Implementing the deck requires:

- A new `OnboardingCardStack.tsx` that owns the full-page positioning,
  container sizing, and the two dimmed background card layers — the
  equivalent of `AuthShell` (§4.2) for these five steps.
- `TrustPrimer.tsx` and `Q1Name.tsx`–`Q4Household.tsx` each stop rendering
  their own outer page wrapper and instead render only their card *content*
  (heading, body, `OnboardingIllustration` slot, CTA) to be placed inside
  `OnboardingCardStack`'s front-card slot.
- `OnboardingFlow.tsx`'s `renderStep()` wraps these five cases in
  `OnboardingCardStack` instead of returning each component directly. No
  change to `history`, `advance`/`back`/`skip`, or any prop each step already
  receives.

**Placeholder cards show no real content** — they are blank card silhouettes
(same chrome: radius, border, shadow) at fixed tilt angles, not pre-rendered
previews of upcoming questions. This avoids revealing question order/content
out of sequence and avoids mounting components for steps the user hasn't
reached.

**The "dealt card" transition** (extends §5.2's directional slide with
rotation, using `--motion-page` for duration): on forward navigation, the
front card exits by rotating further (toward ±10–12°) while sliding off in
the forward direction; the placeholder card that was directly behind it
straightens toward 0° and becomes the new front card; a new blank placeholder
appears at the back of the stack. Back navigation mirrors this exactly — the
front card "returns" to a background tilt position and the previous front
card un-deals back into place. Direction (forward vs. back) is derived from
`history.cursor` (already exists in `onboardingHistory.ts`) increasing or
decreasing, the same comparison-based approach as §5.2, not from which
handler fired.

### 4.7 `ReviewTable` — calm, not staggered

No new component. Targeted changes to the existing file:

- **Container-level only**: one `motion-reveal` settle for the table region
  (header + table together) on mount. Rows do not stagger in individually —
  dense financial data should read as stable and already-there, not as
  something performing for the user.
- **Localized motion, scoped to meaningful state changes only**: an inline
  edit (`Input`/`Select` value committed) gets a brief highlight-and-settle on
  that cell; a match-status icon transitioning (e.g. `HelpCircle` →
  `CheckCircle2` when an override resolves an unmatched scheme) animates that
  icon only; the existing `confirming` prop's submit state gets a `motion-fast`
  button treatment. Nothing else in the table moves.

## 5. Motion specification

The reference motion (a ~7s split-screen auth recording) establishes the
layout first, builds the visual panel progressively, and reveals the form in
staggered layers, ending calm — restrained, drawing/continuity-based, not
fade/slide-as-decoration. This section makes that concrete and repeatable.

### 5.1 Stationary vs. transitioning, per flow

- **Auth**: stationary across every step — the `AuthShell` container (position,
  size, radius, border, shadow), the logo, the footnote, the theme toggle, and
  `AuthShowcasePanel`'s DOM structure (ring geometry, layout). Transitions:
  only the form-slot content, and only the *content* inside
  `AuthShowcasePanel` (headline text, ring fill fraction).
- **Onboarding (questionnaire steps)**: stationary — the deck container's
  position/size and the two background placeholder cards' resting tilt
  angles. Transitions — the front card's content (question, illustration,
  CTA) and each card layer's depth-position during the dealt-card transition
  (§4.6). `add_family`/CAS-upload onboarding steps are unaffected — stationary
  chrome, section-level reveal on content only.
- **CAS Import**: `TwoPathImportContainer`'s tab chrome is stationary while the
  user is on the upload step. `ImportFlow`'s step swap (upload → parsing →
  review → confirmed) is a full context change, not a sub-state of one
  persistent shell like auth — treat each as a `motion-page` crossfade, not a
  directional slide.
- **Review**: table structure and rows are stationary; only container mount
  and the localized interactions in §4.7 move.

### 5.2 Directionality (forward / back)

Forward navigation (any "next"/submit action advancing a step) enters new
content from the right and exits old content to the left
(`x: 24px → 0`, opacity `0 → 1` in; `x: 0 → -24px`, opacity `1 → 0` out). Back
navigation (every existing `onBack` handler — `EmailEntry`, `PhoneEntry`,
`OtpVerify`, etc. already have one) is the mirror: enters from the left, exits
to the right. Direction is derived by comparing the outgoing and incoming
step's position in a fixed, declared step order — not by which handler fired
— so it stays correct regardless of the entry path. Implement with
`framer-motion`'s `AnimatePresence` plus a `custom` direction value fed to
`variants`, keyed on the step name.

For the onboarding card-stack (§4.6), this same forward/back logic — keyed on
`history.cursor` instead of a step-name comparison — drives the "dealt card"
variant specifically: rotation plus slide instead of a plain x-offset. Auth
and CAS-import context swaps use the plain slide above; only the onboarding
questionnaire steps use the rotated variant.

### 5.3 Stagger hierarchy (exactly two levels, nothing else)

1. **Section-level**, once per screen/step mount: heading → primary content
   (fields/question) → primary CTA → secondary options, ~40–60ms offset
   between elements, each using `motion-reveal`.
2. **Row-level**, `ImportFileProgressList` only: each file row staggers in at
   ~30ms offset as files are added — this is a genuinely list-building
   surface. `ReviewTable` rows are explicitly exempt (§4.7).

Do not introduce a third tier or stagger decorative chrome (borders, badges,
icons in isolation) — stagger is reserved for content the user reads in
sequence.

### 5.4 Timing & easing (existing tokens only, no new values)

| Token | Value | Used for |
|---|---|---|
| `--motion-fast` | 150ms ease-out | Hover/focus/press, OTP cell auto-advance, inline-edit highlight-and-settle |
| `--motion-reveal` | 400ms ease-in-out | Section-level staggered reveals, `AuthShowcasePanel` ring-fraction changes, `ReviewTable` container mount, `OnboardingIllustration` entrance |
| `--motion-page` | 300ms ease-in-out | Step-to-step content transitions within a persistent shell (auth, onboarding); full-context swaps in CAS import |

### 5.5 Shared-element / layout continuity — exactly two anchors

Reserve `framer-motion`'s `layoutId` (true shared-element continuity, the
reference video's actual principle — not a generic fade/slide standing in for
it) for exactly two elements:

1. The Fund Signal ring inside `AuthShowcasePanel` — as its fill fraction
   changes step-to-step (§4.3), it animates as one continuous element
   (`layoutId="fund-signal-ring"`), never re-rendered from scratch.
2. The Unifolio brand mark (top-left in `AuthShell`, and anywhere it recurs
   during onboarding/import headers) — `layoutId="brand-mark"` if it is ever
   simultaneously mounted in two places during a transition, so it never
   visibly jumps.

Do not apply `layoutId` more broadly than these two — everything else uses the
enter/exit variants from §5.2.

### 5.6 Reduced motion

Every transition and reveal above must collapse to an instant or opacity-only
state under `prefers-reduced-motion: reduce`, matching `tokens.css`'s existing
convention. Verify by toggling the OS/browser setting, not by inspecting the
media query alone.

## 6. Per-flow file map

- **Auth**: `AuthEntryFlow.tsx`, new `AuthShell.tsx` (§4.2), `AuthShowcasePanel.tsx`
  (§4.3), new `components/ui/otp-input.tsx` (§4.1) consumed by `OtpVerify.tsx`,
  `Landing.tsx`, `EmailEntry.tsx`, `PhoneEntry.tsx`, `LinkAccountPrompt.tsx`.
- **Onboarding**: new `OnboardingCardStack.tsx` (§4.6) wraps `TrustPrimer.tsx`
  and `Q1Name.tsx`–`Q4Household.tsx`, each of which loses its own outer
  full-page wrapper (§4.6) and gains a new `OnboardingIllustration.tsx` slot
  (§4.5). `AddFamilyMembers.tsx` and the CAS-upload onboarding steps are
  unaffected. `OnboardingFlow.tsx`'s step orchestration (`history`,
  `advance`/`back`/`skip`) is untouched — only `renderStep()`'s five
  questionnaire-case return values are wrapped in `OnboardingCardStack`.
- **CAS Import**: `UploadForm.tsx` + new `ImportFileProgressList.tsx` (§4.4),
  `TwoPathImportContainer.tsx`, `ParsingIndicator.tsx`, `CoverageGapBanner.tsx`.
  `ImportFlow.tsx`'s step swap gets a `motion-page` crossfade only (§5.1) — no
  shell-persistence work needed here, since upload/parsing/review/confirmed
  are legitimately separate contexts, not sub-states of one shell the way
  auth's steps are.
- **Review**: `ReviewTable.tsx` per §4.7.
- **Mobile** (`src/mobile/*`): same tokens/components/motion values apply.
  `AuthShell` already collapses to single-column on mobile — `AuthShowcasePanel`
  is already `hidden` below the `lg` breakpoint (`AuthEntryFlow.tsx` line 354) —
  keep it hidden on mobile rather than building a compact variant; mobile auth
  stays full-column, just gains the same `OtpInput` and directional
  step-transitions. `mobile/features/import/MobileUploadForm.tsx` gets
  `ImportFileProgressList`; `mobile/features/import/MobileReviewView.tsx` gets
  the same calm-review treatment as `ReviewTable.tsx`. **Flag while
  implementing**: no mobile-specific onboarding/questionnaire views were found
  under `mobile/features/` — if onboarding is currently reached only through
  the web components regardless of viewport, confirm that's intentional before
  assuming a mobile onboarding surface exists to modify.

## 7. Testing (kept concise — this document's job is the visual/motion/component
system, not a test plan)

- TDD, per `CLAUDE.md`, for the new logic-bearing components: `OtpInput`
  (auto-advance, backspace, paste-fill, validation), `ImportFileProgressList`
  (status transitions), and `OnboardingCardStack` (forward/back direction
  derived correctly from `history.cursor`, correct card advances to front).
- Everything else here is primarily visual — verified by existing flow tests
  continuing to pass plus a manual browser pass (light + dark, reduced-motion
  toggled, forward/back navigation through auth) rather than new
  animation-timing unit tests.
- `npm test` and `npx tsc -b --noEmit` clean before and after.

## 8. Done criteria

- `OtpInput`, `AuthShell`, evolving `AuthShowcasePanel`, `ImportFileProgressList`,
  `OnboardingCardStack`, and `OnboardingIllustration` exist and are wired into
  their respective flows per §4 and §6.
- The onboarding card deck matches the approved reference: front card + 2
  tilted blank placeholders at rest, "dealt card" rotation+slide transition
  forward and back, driven by `history.cursor` — verified visually.
- Motion behavior matches §5 exactly: correct stationary/transitioning split,
  correct forward/back directionality (including the onboarding rotated
  variant), no stagger beyond the two declared tiers, only the two named
  `layoutId` anchors, reduced-motion verified.
- `ReviewTable` reads as calm on mount — no per-row stagger — verified visually,
  not just by absence of a stagger prop in code.
- Zero warm/cream/gold color usage anywhere outside `OnboardingIllustration.tsx`
  — verified by grep, not assumption.
- `npm test` and `npx tsc -b --noEmit` both clean.
- No backend files touched. No changes to any `Step` union, state machine, or
  confirm/override logic beyond the two named exceptions (§4.2, §4.6).
- Work sits on its own branch, not merged to `main`.

## 9. Open items carried from the recon that produced this spec

- No review-screen visual inspiration existed anywhere — §4.7 is original
  design work in the existing token language, not an adaptation of a reference.
- Onboarding previously had zero illustration — §4.5 introduces it fresh.
- The card-stack/dealt-transition treatment (§4.6) is new territory too, added
  after the initial design pass per your reference images — not a refinement
  of anything that existed before this spec.
- No mobile-specific onboarding views were found (§6) — confirm before assuming
  one exists to modify.

---

## Ready-to-paste prompt

Paste the block below as your first message to the coding agent (e.g.
Antigravity), after it has access to this repository:

> Read `Docs/superpowers/specs/2026-08-18-auth-onboarding-import-review-visual-motion-redesign.md`
> in full before writing any code. It is your complete, implementation-ready
> spec for a visual/motion continuity redesign across Auth, Onboarding, CAS
> Import, and Review — both web (`frontend/src/features/*`) and mobile
> (`frontend/src/mobile/*`). Follow its guardrails exactly: no new color
> tokens anywhere except the one named illustration exception (§2), no changes
> to state machines or step logic beyond the two named structural exceptions
> (`AuthShell` in §4.2, `OnboardingCardStack` in §4.6), no backend changes.
> Build the components in §4 — including the onboarding card-deck and its
> "dealt card" transition (§4.6) — implement the motion system in §5 exactly
> as specified (stationary/transitioning split, forward/back directionality,
> the two-tier stagger hierarchy, only the two named `layoutId` shared-element
> anchors), and verify against §8's done criteria before considering any
> surface finished. Work on a new git branch,
> never on `main` directly. When finished, update `session.md` and
> `CLAUDE.md`'s Session State section noting this was executed by [agent name],
> what changed, and any open item from §9 you resolved or left open.
