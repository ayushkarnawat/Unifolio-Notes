---
artifact: mobile-auth-onboarding-review-plan
version: "2.0"
created: 2026-08-19
status: for-review
product: Unifolio
audience: A coding agent (e.g. Google Antigravity) executing the plan
---

# Unifolio — Mobile Auth, OTP, Onboarding, CAS Import & Review

**Planning only. No code was written or modified to produce this document.**
Scoped narrowly to five areas by explicit request: auth screen, OTP screens,
onboarding, CAS import, and CAS review. This supersedes those five areas'
treatment in the broader `Docs/superpowers/specs/2026-08-19-mobile-uiux-system-plan.md`
(which still stands for Dashboard/Holdings/Fund Detail/Import History/Navigation).

**Version note**: v1 proposed a blurred, dark-scrim version of the auth
illustration as a full-bleed mobile background. The product owner reviewed
that direction via mockup and rejected it (no blur, wanted the real
illustration crisp and clearly visible). v2 (this version) replaces §1
entirely with a crisp, non-blurred hero-band-plus-overlapping-card
composition, validated through several mockup rounds, grounded in
`ui-ux-pro-max`'s design intelligence (the current web auth screen's serif
headline + illustration already matches the "Editorial Grid/Magazine" +
"Classic Elegant" luxury pairing) and a 21st.dev inspiration pull that
mostly surfaced generic glassmorphism/gradient-orb SaaS auth patterns —
useful only as confirmation of what to avoid.

## 0. Honest scope — most of these five need no new work

Recon (direct file reads, this session) found real work needed in only two
places. Say so plainly rather than padding out the other three with
unnecessary changes:

| Area | Current state | Work needed |
|---|---|---|
| **Auth screen** | Mobile hides the entire visual panel (`hidden lg:flex` in `AuthShell.tsx`) — nothing replaces it. Bare form, no brand storytelling. | **Yes — §1 (v2: crisp hero band + overlapping card, no blur).** |
| **OTP screens** | Already correct: segmented cells at 44×48px (48×56px above `sm`), `inputMode="numeric"` already set. Renders inside the same `AuthShell`, so it inherits whatever the shell does. | No new work — inherits §1's background automatically. |
| **Onboarding** | `OnboardingCardStack`'s two peeking placeholder cards use fixed rotation/offset/scale values (`rotate: -3/2`, `y: -10/-5`, `scale: 0.94/0.97`) with no responsive override — a real clipping risk at 320–375px, not a design gap. Keep every illustration, animation, and transition exactly as they are today, per explicit instruction. | **Yes, but only the fix in §2 — nothing else changes.** |
| **CAS import** | Fully redesigned this session (v2), full mobile parity already shipped. | None. |
| **CAS review** | `MobileReviewView.tsx` is already mature — card-per-scheme, 44px+ touch targets throughout, sticky confirm bar with backdrop blur. | None. |

## 1. Auth screen (and everything that renders inside `AuthShell` — OTP included)

**v2 — validated through several mockup rounds after v1's blur was
rejected.** Instead of blurring the visual panel, reuse the real,
already-shipped illustration and copy from `AuthShowcasePanel.tsx`/
`left-panel-visual.svg` as a **crisp, non-blurred hero band** at the top of
the mobile screen, with the white auth-form card overlapping its bottom
edge for depth — an editorial layering technique, not a glass/blur effect.
No blur filter, no glassmorphism, anywhere in this design.

- **Where**: applies to the mobile presentation of `AuthShell.tsx` (below
  `lg`), replacing the current `hidden lg:flex` (nothing shown) approach.
  Desktop's split-screen layout is completely unaffected.
- **Hero band**: full-bleed width, the real `left-panel-visual.svg` filling
  it edge-to-edge via `object-fit: cover` — no empty margins, no
  letterboxing. `object-position` biased toward the top ~15–20% of the
  image so the actual graphic (the converging-papers/chart illustration)
  reads fully; the bottom of the image, where the illustration's own
  baked-in headline text lives, is allowed to crop off — that's
  intentional, confirmed with the product owner, since the real headline is
  already rendered as HTML text in the card below, not needed twice.
  Validated height in mockup: roughly 380px tall at a 320–320px-wide phone
  frame — treat as a starting point to confirm against real device widths,
  not a value to copy blindly.
- **Overlapping card**: the white auth-card surface rises up to overlap the
  hero band's bottom edge (rounded top corners, small negative top margin,
  a soft shadow) — this is where the actual depth comes from, not from any
  blur or transparency effect.
- **Headline/subtext**: real HTML text inside the card, matching the exact
  current web copy ("Unify. Consolidate. Build Wealth." / "Your fragmented
  investments, curated into one complete picture.", or whatever the live
  copy is at implementation time — read it from the current
  `AuthShowcasePanel.tsx`/web screen directly, don't guess).
- **Applies uniformly to every step rendered inside `AuthShell`** — landing,
  email/phone entry, OTP verification, link-account — since the shell
  itself, not each step, owns this treatment. This is what makes OTP need
  zero separate work: it inherits the same hero band automatically.
- **Design grounding**: `ui-ux-pro-max`'s style/typography search confirms
  the current web screen (serif display headline, editorial illustration,
  cream background) already matches the "Editorial Grid/Magazine" style
  category and the "Classic Elegant" (Playfair-Display-class serif +
  clean sans) typography pairing it recommends for luxury/premium — carry
  that same language to mobile rather than introducing a different one.
- **Light vs. dark app theme**: the illustration's own light/cream colors
  were only validated in the app's light theme. Confirm visually how the
  hero band and overlapping card should read in dark mode before shipping —
  flagged as open, not decided, rather than guessed.
- **Reference asset**: `frontend/src/assets/left-panel-visual.svg` — the
  exact same asset `AuthShowcasePanel.tsx` already imports on desktop.
  Reuse it as-is; don't duplicate or re-export a second copy for mobile.
- **Performance flag, reduced from v1**: the asset is 543KB with complex
  vector paths, but this design no longer applies a runtime `filter:
  blur()` (the main GPU-cost concern in v1) — still worth a basic paint-cost
  check on real devices given the file's size/complexity, but no longer the
  primary risk it was.

## 2. Onboarding — one bug fix, nothing else

`OnboardingCardStack.tsx`'s placeholder-card offsets are fixed regardless of
viewport width. Add a narrow-viewport adjustment (e.g. a `sm:` breakpoint
reducing the rotation/`y`-offset magnitude below ~640px, or increasing the
outer container's horizontal padding at those widths) so the peeking card
corners don't clip against the container edge at 320–375px. This is the
**only** change to onboarding — every illustration, every animation, every
transition stays exactly as built today, per explicit instruction. Verify
visually at 320px specifically, since that's where the risk is concrete.

## 3. CAS import & CAS review

No changes. Both are already complete and mature (§0's table). Reference
only — Antigravity should not touch these two areas under this plan.

## 4. Implementation steps

1. Add the hero-band-plus-overlapping-card treatment to `AuthShell.tsx` for
   the below-`lg` case, per §1. Use the existing `left-panel-visual.svg`
   import already available in `AuthShowcasePanel.tsx` — don't duplicate
   the asset. Pull the exact current headline/subtext copy from the live
   web screen, don't guess it.
2. Verify OTP, landing, email/phone entry, and link-account screens all
   inherit the new hero band correctly with no per-screen changes needed.
3. Tune the hero band's height and `object-position` against real device
   widths (320/375/430px) so the illustration's actual graphic reads
   clearly and the crop only cuts into the illustration's own baked-in
   text, never its core imagery.
4. Confirm how the hero band and overlapping card should look in dark mode
   (only light mode was validated) — this needs a visual decision, not a
   guess.
5. Fix `OnboardingCardStack.tsx`'s placeholder-card clipping at narrow
   widths per §2. Do not change anything else in this component.
6. Verify at 320px, 375px, and 430px for both changes.
7. Confirm `prefers-reduced-motion` behavior is unaffected by either change
   (the hero band is static, not animated; the card-stack fix only changes
   resting values, not motion).
8. Do a basic paint-cost check on the 543KB SVG on a real/representative
   mobile device — no longer the primary risk now that blur is removed,
   but still worth confirming.
9. Do not modify CAS import or CAS review under this plan (§3).
10. Work on a new git branch, never on `main` directly. Update `session.md`
    and `CLAUDE.md`'s Session State when done.

---

## Ready-to-paste prompt

> Read `Docs/superpowers/specs/2026-08-19-mobile-auth-onboarding-review-plan.md`
> in full before writing any code — it's v2; the version note explains that
> v1's blurred background was rejected and replaced. Only two things
> actually need work: (1) the mobile auth hero-band-plus-overlapping-card
> treatment in §1 — reuse the existing `left-panel-visual.svg` asset,
> crisp, no blur, `object-fit: cover` filling the band edge-to-edge, the
> real auth card overlapping its bottom edge, real HTML headline/subtext
> copy pulled from the current live web screen — applies uniformly across
> every step rendered inside `AuthShell`, including OTP, so don't build
> anything OTP-specific separately; and (2) the one-line-item bug fix to
> `OnboardingCardStack.tsx`'s placeholder-card clipping at narrow widths in
> §2 — do not touch anything else in that component; every illustration,
> animation, and transition it already has must stay exactly as built. Do
> not touch CAS import or CAS review — both are already complete (§3). Get
> the hero band's `object-position` and height right against real device
> widths (320/375/430px) rather than copying the mockup's values blindly,
> and confirm the dark-mode treatment visually since only light mode was
> validated. Work on a new git branch, never on `main` directly. When
> finished, update `session.md` and `CLAUDE.md`'s Session State section.
