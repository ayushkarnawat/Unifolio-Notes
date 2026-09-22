---
artifact: mobile-privacy-onboarding-fullscreen-plan
version: "1.0"
created: 2026-08-20
status: for-review
product: Unifolio
audience: A coding agent (e.g. Google Antigravity) executing the plan
---

# Unifolio — Mobile Privacy Screen & Onboarding: Full-Screen Redesign Plan

**Planning only. No code was written or modified to produce this document.**
Grounded in a direct read of every file in §1, the `ui-ux-pro-max` skill's
onboarding/navigation guidance, and the "mobile onboarding inspo" reference
(a tilted-card onboarding carousel — used only for composition cues: bold
headline, one illustration per concept, single CTA, a progress accent;
never its colors/branding, per your instruction).

**Scope boundary, stated explicitly rather than assumed**: "all existing
onboarding screens" is read here as the screens that are actually
card-presented today — `trust_primer` through `q4_household` (wrapped in
`OnboardingCardStack`) plus `add_family` (already full-page, but
visually inconsistent with the rest). `cas_upload`/`family_cas_upload`/
`upload_my_cas`/`parse_queue` are **not** included — they're already
full-page today and were already addressed by the separate CAS-import
mobile redesign completed earlier this session. If you meant those too,
say so before implementation starts.

## 1. Current flow and relevant files/components

- `OnboardingFlow.tsx` — orchestrator. Reads `history`/`cursor` from
  `onboardingHistory.ts`, calls `renderStep()` which switches on the current
  `OnboardingStep` (from `onboardingSteps.ts`'s `ONBOARDING_STEPS`) and
  renders the matching component.
- Step components: `TrustPrimer.tsx`, `Q1Name.tsx`, `Q2Investing.tsx`,
  `Q3Purpose.tsx`, `Q4Household.tsx`, `AddFamilyMembers.tsx` (all in
  `frontend/src/features/auth/`).
- `OnboardingCardStack.tsx` — wraps `trust_primer` through `q4_household`
  (not `add_family`) in the centered card-deck visual.
- `onboardingHistory.ts`/`onboardingSteps.ts` — the step-name state machine
  (`{order, cursor, skipped}`, `goNext`/`goBack`/`skipToNext`).
- `OnboardingIllustration.tsx` — the shared hand-drawn illustration
  component and its `IllustrationVariant` union.
- `lib/motion.ts` — shared motion tokens, already used inside step
  components (`staggerContainerVariants`/`staggerItemVariants`).
- `App.tsx`'s `MainApp` — computes `isMobileViewport`/`isMobileRoute`/
  `isMobile` today, but only consumes it *after* the onboarding-incomplete
  branch (`!me.onboarding_completed ? <OnboardingFlow /> : ...`) — `isMobile`
  is in scope but never passed to `OnboardingFlow` today.
- No mobile-specific onboarding or auth files exist anywhere in
  `frontend/src/mobile/` — confirmed by direct search.

## 2. How the current mobile card layout works

Because `OnboardingFlow`/`OnboardingCardStack` have zero viewport branching,
mobile sees exactly what desktop sees: a centered, padded `rounded-3xl`
card (with two absolutely-positioned, fixed-offset placeholder cards tilted
behind it) holding whatever the active step renders as `children` — there
is no defined slot contract, each step's own root element just becomes the
card's content. `add_family` isn't in the card-stack at all — it's already
a full `min-h-dvh` page, just without the header/progress/illustration
treatment the other steps get, so it reads as inconsistent with the rest of
the sequence. On mobile, this produces a small, padded, shrunken-desktop
card with wasted screen space around it — exactly the "shrunken desktop
layout" problem you named, not a genuinely mobile-composed screen.

## 3. Proposed screen-by-screen mobile structure

One shared full-screen template, applied to every step in scope:

- **Top bar**: back chevron (when `history.cursor > 0`), a real step-progress
  indicator (dashes/dots, not the card-stack's tilted-card metaphor), and a
  skip link (only where skip already exists today).
- **Headline** (no eyebrow label — validated via mockup and removed): same
  copy as today, comes first, restyled for full-bleed width instead of a
  padded card.
- **Illustration**: sits between the headline and the subtext — not above
  the headline, and not after the subtext. Larger than the card-constrained
  size today — a proper hero moment, matching the inspo's "one illustration,
  one concept" energy without its colors/branding.
- **Subtext**: same copy as today, follows the illustration.
- **Content**: the step's existing choice-buttons or input field, unchanged
  logic, just laid out full-width instead of card-constrained.
- **Primary CTA**: anchored near the bottom, in the thumb-reach zone.

**Validated ordering, top to bottom**: top bar → headline → illustration →
subtext → content → CTA. (Iterated twice: first tried eyebrow → illustration
→ headline/subtext → content; the product owner asked for headline first,
no eyebrow, illustration after the headline; then refined once more to put
the illustration between the headline and the subtext specifically, not
after the subtext.)

`add_family` gets the same top bar/illustration/typography treatment for
visual cohesion, while its roster list + add-member form (name input,
relationship `Select`, conditional "other" label) stays exactly as built —
this screen has more real content than the others and needs its own
careful layout pass, not a blind copy of the choice-button template.

Desktop's `OnboardingCardStack` presentation is completely unchanged —
this redesign only adds a second, mobile-specific presentation path.

## 4. Modify vs. new components

**New:**
- `MobileOnboardingScreen.tsx` (or similar name) — the shared full-screen
  template (top bar, illustration slot, headline/subtext slot, content
  slot, CTA slot). This is the mobile equivalent of `OnboardingCardStack`,
  minus the stacked-card visual — screen-to-screen transitions use a plain
  directional slide/crossfade (reuse `lib/motion.ts`'s existing
  `pageTransition`, not a new motion system).

**Modify:**
- `App.tsx`: thread `isMobile` into `<OnboardingFlow isMobile={isMobile} />`
  — a one-line change, since `isMobile` is already computed in scope.
- `OnboardingFlow.tsx`: accept the `isMobile` prop; in `renderStep()`, choose
  `MobileOnboardingScreen` instead of `OnboardingCardStack` for the
  `trust_primer`→`q4_household` range when `isMobile` is true; apply the same
  template treatment to `add_family`'s existing wrapper.
- `TrustPrimer.tsx`: add internal two-point pagination (§5) — content
  unchanged, just split into two renders of the same component.
- `Q1Name.tsx`/`Q2Investing.tsx`/`Q3Purpose.tsx`/`Q4Household.tsx`: **no
  content or logic changes.** Their existing root content renders inside
  `MobileOnboardingScreen` on mobile instead of inside
  `OnboardingCardStack` — a wrapper swap, not a rewrite.
- `AddFamilyMembers.tsx`: wrap in the same header/progress treatment; roster
  and add-member form logic untouched.

**Unmodified, out of scope**: `onboardingHistory.ts`, `onboardingSteps.ts`,
any backend code, `cas_upload`/`family_cas_upload`/`upload_my_cas`/
`parse_queue` (§0's scope boundary).

## 5. How the privacy points transition into onboarding

**Recommended: keep this entirely client-side, inside `TrustPrimer.tsx`,
with no change to the shared step state machine.** Add a small internal
`point: 1 | 2` state to `TrustPrimer`. Point 1's action button reads "Next"
and advances the internal state to point 2 (no history/backend call at
all). Point 2's action button reads "Continue" and calls the *existing*
`onContinue` prop exactly as today, advancing the shared history to
`q1_name`. Back navigation: from point 2, "back" returns to point 1
(internal state); from point 1, "back" behaves exactly as today (exits
`trust_primer` via the existing history mechanism).

**Why not add a new `trust_primer_2` step to `onboardingSteps.ts` instead**
(the alternative — confirmed technically easy in isolation): doing so would
mean the backend's `onboarding_step` persistence (`updateMe({onboarding_step:
step})`, called on every step change) needs to accept a new value — a
backend-adjacent change this plan hasn't verified, and unnecessary
architecture for what's a two-screen, low-stakes privacy notice. The
internal-substep approach avoids touching the backend, `onboardingHistory.ts`,
or `onboardingSteps.ts` at all. Trade-off, stated plainly: a user who drops
off mid-point-2 and returns later resumes at point 1, not point 2 — minor,
and reasonable to accept for a two-screen notice. Flag if you'd rather have
server-tracked resume into point 2 specifically; that's the one case where
the state-machine-addition alternative would be worth its backend cost.

## 6. Illustration requirements

**Reused as-is, no new work**: `trust` (privacy point 1), `name`
(Q1Name), `investing` (Q2Investing), `purpose` (Q3Purpose), `household`
(Q4Household) — all already exist and already fit their screens.

**Open decision, not silently resolved**: privacy point 2 ("No raw CAS PDF
storage") has no dedicated illustration today, only a small inline SVG
icon. Default recommendation (per your "continue" — proceeding with the
lower-cost option rather than blocking on this): reuse that existing icon
at illustration scale, zero new asset work. If you want full visual parity
with every other step's proper hand-drawn illustration, commissioning one
for point 2 is real, separate design/asset work — flagged, not assumed.

**Separately spotted, optional, not required for this redesign**:
`AddFamilyMembers.tsx` currently reuses the `household` illustration
variant, even though a distinct `family` variant already exists in the
codebase and is completely unused. Worth a one-line fix (swap the variant),
but note this is a correctness fix that would apply to *both* platforms,
not a mobile-only change — call it out separately if you want it bundled
into this work or done independently.

## 7. Responsive/layout considerations

- Validate at 320px, 375px, and 430px, per this codebase's existing
  convention.
- `min-h-dvh`, not `100vh` (already the pattern elsewhere).
- At short viewport heights (small-height phones, landscape), the
  illustration is the least essential element for task completion —
  constrain its max-height and let it shrink first, never let it push the
  CTA below the fold or force scrolling to reach it.
- Prefer the CTA in natural document flow at the end of short content
  rather than a `position: sticky/fixed` bar, to avoid the "sticky nav
  obscuring content" anti-pattern — each screen's content is short enough
  that this should hold up; revisit only if `add_family`'s longer content
  makes a fixed CTA genuinely necessary there.
- Progress dots, back, and skip controls all meet the existing ≥44×44px
  touch-target convention.
- Respect `prefers-reduced-motion` for the new screen-to-screen transition,
  consistent with every other motion addition in this codebase.

## 8. State/routing changes required

Minimal, by design (§5's reasoning): `isMobile` prop threading from
`App.tsx` → `OnboardingFlow.tsx`; a wrapper-choice branch inside
`OnboardingFlow.tsx`'s `renderStep()`; `TrustPrimer.tsx`'s new internal
`point` state. **No changes** to `onboardingHistory.ts`, `onboardingSteps.ts`,
or any backend endpoint/schema.

## 9. Risks or edge cases

- **`add_family`'s form complexity**: it has real inputs (name, relationship
  select, conditional label) and a dynamic roster list, not just choice
  buttons — give it real layout attention inside the new template rather
  than assuming the simple-choice-screen pattern drops in cleanly.
- **Point-2 resume behavior** (§5): accepted trade-off, not a bug, but
  worth the product owner's explicit sign-off since it's a real behavior
  difference from a server-tracked-step approach.
- **`OnboardingCardStack`'s existing narrow-viewport clipping risk** (flagged
  in an earlier session's plan) is irrelevant to *this* redesign, since
  mobile no longer uses `OnboardingCardStack` at all under this plan — but
  desktop still does, and that fix (if not already shipped) remains a
  separate, still-open item, unaffected by this work.
- **Desktop regression risk**: since `OnboardingCardStack`'s children have
  no defined slot contract today, double-check that making `Q1Name`/etc.'s
  root content "wrapper-agnostic" (so it works inside either
  `OnboardingCardStack` or `MobileOnboardingScreen`) doesn't require
  changing anything about how they render *inside* `OnboardingCardStack` —
  the goal is a second consumer of the same content, not a change to the
  first one.

## 10. Implementation plan, in order

1. Thread `isMobile` from `App.tsx` into `OnboardingFlow.tsx`.
2. Build `MobileOnboardingScreen.tsx` per §3/§4.
3. Add internal two-point pagination to `TrustPrimer.tsx` per §5.
4. Wire `OnboardingFlow.tsx`'s `renderStep()` to choose
   `MobileOnboardingScreen` vs. `OnboardingCardStack` based on `isMobile`
   for `trust_primer`→`q4_household`, with zero content changes to
   `Q1Name`/`Q2Investing`/`Q3Purpose`/`Q4Household`.
5. Apply the same template treatment to `add_family`, preserving its form/
   roster logic exactly; give its layout the extra attention §9 flags.
6. Implement privacy point 2's illustration per §6's default (reuse the
   existing icon) unless the product owner has asked for a commissioned
   illustration instead.
7. (Optional, separate) fix `AddFamilyMembers`'s illustration variant from
   `household` to the unused `family` variant, if wanted alongside this work.
8. Verify at 320/375/430px; verify back/skip/progress across the full
   sequence; verify `prefers-reduced-motion`; verify desktop
   (`OnboardingCardStack` path) renders completely unchanged.
9. Do not touch backend code, `cas_upload`/`family_cas_upload`/
   `upload_my_cas`/`parse_queue`, or any auth-entry screen (separate,
   already-planned work).
10. Work on a new git branch, never on `main` directly. Update `session.md`
    and `CLAUDE.md`'s Session State when done.

---

## Ready-to-paste prompt

> Read `Docs/superpowers/specs/2026-08-20-mobile-privacy-onboarding-fullscreen-plan.md`
> in full before writing any code. Its scope boundary in §0 is explicit —
> this covers `trust_primer` (split into two internal points per §5) through
> `q4_household`, plus `add_family`; it does **not** cover `cas_upload`/
> `family_cas_upload`/`upload_my_cas`/`parse_queue` or any auth-entry screen.
> Follow §4's file-by-file plan and §10's implementation order exactly. §3's
> validated element order for `MobileOnboardingScreen` is top bar → headline
> → illustration → subtext → content → CTA (no eyebrow label) — the
> illustration sits between the headline and the subtext specifically, not
> above the headline and not after the subtext. Build that exact order. The
> privacy-point split is deliberately client-side-only inside
> `TrustPrimer.tsx` (§5) — do not add a new step to `onboardingSteps.ts` or
> touch the backend's `onboarding_step` persistence unless you've confirmed
> that trade-off with the product owner first. `Q1Name`/`Q2Investing`/
> `Q3Purpose`/`Q4Household` need zero content or logic changes — only a
> different wrapper on mobile. Desktop's `OnboardingCardStack` presentation
> must render completely unchanged. Use the default illustration choice in
> §6 for privacy point 2 unless told otherwise. Verify at 320/375/430px and
> confirm reduced-motion behavior. Work on a new git branch, never on `main`
> directly. When finished, update `session.md` and `CLAUDE.md`'s Session
> State section.
