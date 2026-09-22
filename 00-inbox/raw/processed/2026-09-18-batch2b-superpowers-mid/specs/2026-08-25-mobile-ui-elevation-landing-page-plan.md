---
artifact: mobile-ui-elevation-landing-page-plan
version: "1.0"
created: 2026-08-25
status: for-review
product: Unifolio
audience: A coding agent (e.g. Google Antigravity) executing the plan
---

# Unifolio — Mobile UI Elevation & Pre-Auth Landing Page: Implementation Plan

**Planning only. No code was written or modified to produce this document.**
Grounded in the `ui-ux-pro-max` skill's style/GSAP/navigation guidance, a
21st.dev inspiration pull, a direct read of the mobile codebase across this
session's prior work, and the "Mobile UI Inspo" reference — with one honest
finding: its 5 static screenshots **do not match** the premium 3D
pedestal/tilt video you described (they're generic dark-hero-photo auth UI
templates, the exact "generic SaaS" look this product avoids elsewhere).
This plan started from your text description of that video (a literal
device-tilt showcase), then moved past it after mockup review — the
landing page's motion concept (§5) ended up **not** being a 3D device tilt
at all; see §5's note. The two narrow, style-independent patterns worth
keeping from the stills (a dot-pagination/arrow-CTA mechanic and a
hero-top/form-below layout split) still stand, not their palette or
photography.

## 0. Relationship to other in-flight mobile plans

This session has two other mobile plans not yet confirmed implemented:
the auth hero-band redesign (`2026-08-19-mobile-auth-onboarding-review-plan.md`)
and the full-screen onboarding redesign
(`2026-08-20-mobile-privacy-onboarding-fullscreen-plan.md`). This plan
treats both as **out of scope** — it does not modify auth or onboarding
screens further. The landing→auth handoff in §6 references the auth
hero-band's illustration *if* that work has landed, and degrades gracefully
to a plain crossfade into whatever `AuthEntryFlow` currently renders if it
hasn't — Antigravity should check current state before assuming either.

## 1. Existing screen-by-screen UI audit

| Screen | Current motion/polish state |
|---|---|
| Mobile shell (header, bottom nav, device frame, app shell) | Functional, mature. Generic loading/error/empty mechanism exists but is under-used. No press-feedback micro-interaction on nav items. |
| Mobile Dashboard | Mature content (hero value, allocation donut, searchable holdings list) — **zero motion of any kind**. |
| Mobile Holdings list / Fund Detail (view + sheet) / Distributor Comparison | Mature, complete — **zero motion, zero illustration**. |
| Mobile Import History | Functional, plain list — no motion, no illustration (empty-state illustration already flagged as an open item in an earlier plan, still unimplemented as far as this audit can confirm). |
| CAS Import (choice/request/upload/waiting/history) | Already redesigned this session (v2) — illustration- and motion-aware, mature. Not touched by this plan. |
| CAS Review (`MobileReviewView`) | Mature, one container-level fade-in only, deliberately calm per an earlier plan's "review should feel stable, not staggered" reasoning. Not touched by this plan. |
| Auth / Onboarding | Covered by the two separate in-flight plans in §0. Not touched here. |
| Landing (pre-auth) | **Does not exist.** New surface, §5. |

## 2. What stays unchanged vs. what gets elevated

**Unchanged, explicitly**: all business logic, data-fetching, state
machines, existing content/copy/information-hierarchy on Dashboard/
Holdings/Fund Detail/Distributor Comparison/Import History. The 3-item
bottom-nav structure. Backend/API. CAS import/review (already recently
elevated). This is an execution pass, not a redesign — per your explicit
framing.

**Elevated**:
- Entrance/reveal motion on Dashboard/Holdings/Fund Detail/Distributor
  Comparison, using the **same** `lib/motion.ts` tokens already proven
  elsewhere in this codebase (onboarding, CAS import) — not new bespoke
  motion, just finally applied here.
- A modest, consistent elevation/shadow scale for cards (currently minimal/
  flat) — extends existing `--shadow-sm`/`--shadow-md` tokens, doesn't
  replace them.
- Shell press-feedback on bottom-nav taps.
- Import History's still-open empty-state illustration (from an earlier
  plan — folded in here since it's the same category of work).
- The entirely new landing page (§5).

## 3. Adapting the reference visual language

- **Environment**: a soft radial-gradient neutral field (cream/white base)
  with faint architectural ribbed background forms and a subtle **green**-
  tinted ambient glow — translating the video's lilac/pink/orange/cyan
  palette into Unifolio's own accent color, not copying it. Reserved for
  the landing page only; the rest of the app keeps its established tokens
  unchanged.
- **Depth/shadow language**: soft, directional, layered shadows (matching
  the described phone's soft shadow interacting with light) — informs the
  card elevation refinement in §2, tuned to existing tokens, not a new
  design-system style category.
- **Device-as-hero-object**: a static phone frame, used once, on the
  landing page. Not reused inside the app itself — a phone mockup doesn't
  belong inside a screen that already *is* the phone. The device itself
  stays visually still (no 3D tilt, per §5's validated direction) — the
  motion lives inside its screen instead.
- **Convergence narrative, reused rather than invented**: the landing page's
  motion (§5) reprises the exact "scattered data becoming one clear
  picture" story the desktop auth screen's illustration already tells —
  this ties the landing page to Unifolio's own established visual language
  instead of importing a generic 3D-product-showcase trope from the video
  reference.
- **From the static stills, filtered**: the dot-pagination + circular-arrow
  CTA mechanic is compatible with (not a replacement for) onboarding's
  existing dash-based progress indicator from the separate onboarding plan
  — a refinement to flag there, not act on here. The hero-top/form-below
  split is already effectively what the auth hero-band plan does — no new
  action needed.

## 4. Motion opportunities, per screen

- **Landing**: a static phone frame; scattered data fragments drift in from
  the screen's edges and converge into the portfolio-value/brand reveal —
  not a 3D device tilt. §5/§6/§9.
- **Dashboard**: Tier-1 stagger reveal on mount — hero value → donut →
  holding cards — using `staggerContainerVariants`/`staggerItemVariants`
  exactly as already used elsewhere, not new tokens.
- **Holdings list**: Tier-2 row-level stagger on mount/filter-change,
  matching the existing pattern already proven in `ImportFileProgressList`.
- **Fund Detail (view/sheet)**: `pageTransition` slide/fade on entry,
  matching the existing convention. A shared-element continuity animation
  (the tapped card's `FundSignal` growing into the detail hero) is a
  genuine nice-to-have — flagged as feasibility-gated, not mandatory; don't
  block the rest of this plan on it.
- **Distributor Comparison**: `pageTransition` on drill-down, row stagger
  for the comparison table.
- **Import History**: empty-state illustration entrance (§2); row stagger
  if the list is long enough to warrant it.
- **Bottom nav**: press feedback (scale/opacity, 80–150ms per
  `ui-ux-pro-max`'s tap-feedback guidance) — the one new shell interaction.

## 5. New landing page (pre-auth)

**Validated through mockup.** A full-bleed mobile screen, shown before
`AuthEntryFlow` for unauthenticated users:

- Soft neutral environment per §3 and a static phone-mockup hero object
  (built from CSS/SVG + the existing brand glyph — zero new image assets).
  No pedestal, no 3D tilt/rotation of the device itself — validated as the
  wrong direction through mockup review (an earlier pass tried a literal
  3D device-tilt sequence per the video reference; the product owner
  reviewed three alternative directions and picked this one instead).
- **Sequence (validated)**: the phone frame holds still throughout. A
  handful of small, loose fragments (representing scattered holdings/
  statements — thin outlined rectangles, not literal document icons) drift
  in from the screen's edges, converging toward the center as they move,
  fading from a neutral/desaturated tone toward Unifolio's accent green as
  they approach. They resolve into a calm, settled reveal — the brand mark
  and/or a real product preview (e.g. a portfolio-value card, drawn from
  the same visual language as the actual Dashboard, not stock art). This
  is the exact "scattered becoming one clear picture" story the desktop
  auth screen's illustration already tells, reused here rather than a new
  motif invented for this screen.
- Headline, subtext, and a primary CTA ("Get Started") anchored at the
  bottom, plus a secondary "Log in" affordance for returning users —
  mirroring the two entry points `AuthEntryFlow`'s own landing step already
  has.
- **"Get Started"** advances into `AuthEntryFlow`'s existing signup path.
  **"Log in"** advances directly into its existing email/phone entry,
  skipping signup. `AuthEntryFlow` itself is not modified — this page is
  purely a new step prepended to the flow.

**Open scope decision, not silently resolved**: gate this to mobile only
(`!me && isMobile`, matching this session's overall mobile-only framing) —
desktop continues straight to `AuthEntryFlow` as today, unless you want a
landing page on desktop too, which is a separate, larger decision this plan
doesn't make for you.

## 6. Landing → authentication transition

On CTA tap, a brief (300–400ms, matching the existing `--motion-page`
convention), calm crossfade/scale-out — not a second elaborate sequence.
The landing page **is** the cinematic moment; the handoff into auth should
be quick and clean, not competing with it. If the auth hero-band redesign
(§0) has landed, the landing page's product-preview card can visually hand
off into that hero band's illustration for continuity; if not, this is a
plain crossfade into whatever `AuthEntryFlow` currently renders — check
current state before assuming either.

## 7. Shared visual/motion system across the app

One motion vocabulary throughout, landing page included: `lib/motion.ts`'s
existing tokens (`DURATION_FAST`/`REVEAL`/`PAGE`, the stagger variants,
`pageTransition`). Because the validated landing concept (§5) is
fragment-position/opacity choreography rather than a literal 3D-transform
sequence, it no longer needs a separate motion system — it's built with
`motion` (Framer Motion), the same library already driving every other
reveal in this codebase, just with its own bespoke fragment-convergence
timing (individual fragments' delays/durations), not a shared token, since
nothing else needs this exact choreography. No new color tokens, no new
typography. The elevation/shadow extension in §2 is additive to existing
tokens. Every new/changed motion respects `prefers-reduced-motion`: the
landing page collapses straight to its settled/resolved state with an
immediate CTA; all stagger reveals collapse per the existing convention
used elsewhere.

## 8. Components/assets to create or modify

**New**:
- `MobileLandingPage.tsx` — the new pre-auth screen.
- A phone-mockup hero sub-component (e.g. `PhoneShowcaseHero.tsx`) —
  CSS/SVG-built, no image assets, static frame (no 3D transform).
- A fragment-convergence sub-component/set of `motion`-driven elements
  scoped locally to the landing component (no shared utility needed unless
  a second use case emerges later — don't build one speculatively).

**Modify** (motion/press-feedback only, per §2/§4 — no content changes):
`App.tsx` (new mobile-gated landing view state), `MobileDashboardView.tsx`,
`MobileHoldingCard.tsx`, `MobileHoldingsView.tsx`, `MobileFundDetailView.tsx`,
`MobileFundDetailSheet.tsx`, `MobileDistributorComparisonView.tsx`,
`MobileImportHistory.tsx`, `MobileBottomNav.tsx`.

**Assets**: none required anywhere in this plan — motion-only additions to
existing screens, and the landing page's hero is generative, not an image.

## 9. Recommended animation approach (existing dependencies only)

- `motion` (Framer Motion) — already the established pattern for
  component-level reveals, stagger, and page transitions (§4/§7), and now
  also the primary tool for the landing page itself (§5's validated
  fragment-convergence concept is per-element position/opacity/color
  animation, exactly Framer Motion's strength — the same technique already
  used for `OnboardingCardStack`'s card choreography elsewhere in this
  codebase). Extend its existing use, don't replace it.
- `gsap` — already installed, currently unused anywhere in this codebase.
  Not needed for the validated landing concept. Keep in mind only if a
  future motion need genuinely requires GSAP's timeline/`ScrollTrigger`
  capabilities beyond what `motion` covers — don't reach for it here.
- **No new dependencies of any kind** — no Three.js/WebGL, no Lottie, no
  video library, and (per above) no need for `gsap` either. The entire
  landing page is CSS/SVG plus `motion`-driven element animation.

## 10. Implementation phases

1. **Landing page** — self-contained, doesn't touch any existing screen.
   Build `MobileLandingPage.tsx` + `PhoneShowcaseHero.tsx` + the
   `motion`-driven fragment-convergence sequence; wire into `App.tsx` as a
   new mobile-gated pre-auth state; implement the landing→auth handoff (§6).
2. Confirm `lib/motion.ts`'s existing tokens are sufficient for §4; extend
   the elevation/shadow scale per §2/§3 if needed.
3. Apply motion to Dashboard (stagger reveal).
4. Apply motion to Holdings list, Fund Detail (view + sheet), Distributor
   Comparison.
5. Apply motion to Import History, including its still-open empty-state
   illustration.
6. Shell polish — bottom-nav press feedback.
7. Verify: 320/375/430px, `prefers-reduced-motion`, desktop completely
   unaffected, existing tests pass, no new dependencies in `package.json`.

## 11. Acceptance criteria

- [ ] Landing page renders before `AuthEntryFlow` for unauthenticated users
      (mobile-gated per §5's decision, or app-wide if that's been
      confirmed instead), plays its fragment-convergence sequence once,
      calmly, with a static (non-tilting) phone frame throughout.
- [ ] `prefers-reduced-motion` collapses the landing sequence straight to
      its settled/resolved state with an immediate CTA.
- [ ] "Get Started"/"Log in" hand off correctly into `AuthEntryFlow`'s
      existing signup/login paths, with zero modification to
      `AuthEntryFlow` itself.
- [ ] Zero new npm dependencies (`git diff` on `package.json` is empty
      besides lockfile churn).
- [ ] Zero content/copy/functional changes to Dashboard, Holdings, Fund
      Detail, Distributor Comparison, Import History, CAS import/review, or
      onboarding — motion/press-feedback additions only.
- [ ] All existing mobile tests pass; `npx tsc -b` clean.
- [ ] Desktop rendering is completely unaffected — no `isMobile`-gated code
      path touches the desktop render tree.
- [ ] Every new or changed motion respects `prefers-reduced-motion`.
- [ ] Touch targets stay ≥44×44px throughout.
- [ ] Verified at 320px, 375px, and 430px.

---

## Ready-to-paste prompt

> Read `Docs/superpowers/specs/2026-08-25-mobile-ui-elevation-landing-page-plan.md`
> in full before writing any code. §0 is explicit that the auth hero-band
> and full-screen-onboarding plans from earlier this session are out of
> scope here — check their actual current implementation state before
> assuming either is done, especially for §6's landing→auth handoff. This
> is an execution-elevation pass, not a redesign (§2) — Dashboard/Holdings/
> Fund Detail/Distributor Comparison/Import History/CAS import/review/
> onboarding get motion and press-feedback only, zero content or logic
> changes. Build the new landing page (§5) first per §10's phase order —
> it's self-contained. §5's validated concept is a **static** phone frame
> with scattered fragments drifting in and converging into the reveal —
> not a 3D device tilt (an earlier direction that was tried and rejected;
> don't build that instead). Use `motion` (Framer Motion, already
> installed) for the fragment choreography per §9 — do not add `gsap`
> usage, Three.js, WebGL, Lottie, or any other new dependency. Reuse
> `lib/motion.ts`'s existing tokens for
> every other screen's motion (§4/§7) rather than inventing new ones. Gate
> the landing page to mobile only unless told otherwise (§5). Verify every
> acceptance criterion in §11 before considering this done, including that
> desktop is completely unaffected and no new dependencies were added.
> Work on a new git branch, never on `main` directly. When finished, update
> `session.md` and `CLAUDE.md`'s Session State section.
