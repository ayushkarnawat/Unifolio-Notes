# The mobile track pulls ahead of desktop

## For stakeholders

Between 19 and 25 August the mobile experience got its own design system
survey, an auth and onboarding treatment, a full-screen privacy-primer screen,
and a landing-page visual direction. The most consequential thing the survey
found was not a design problem at all: **the mobile dashboard is the mature
one, and the desktop main dashboard is still a placeholder stub.** That
reverses the assumption running through the earlier specs, where mobile is the
adaptation and desktop is the reference. The survey's recommendation is that
when the desktop dashboard is eventually built it should follow the product
semantics already established on mobile, not the other way round. Two design
directions were reviewed against mockups and rejected in this stretch, which
is recorded because the rejected option and the reason are part of the record.

## Technical detail

### Intended outcome

Establish a coherent mobile design system, decide what is shared with the web
app and what is mobile-specific, and bring the mobile auth, onboarding and
landing surfaces to the same standard as the desktop work.

### What actually happened

**The mobile UI/UX system plan (2026-08-19, v1.0)** is a survey first and a
plan second, and it surfaces four things that matter beyond mobile.

- **§0.1 — a real routing contradiction already in the code.** The code repo's
  `Docs/MOBILE_APP_EXECUTION.md` states that mobile must not automatically
  replace the web experience based on viewport or device detection. `App.tsx`
  renders `MobileRoot` when the route is a mobile route **or** when a
  `max-width: 767px` media query matches — that is exactly viewport-based
  auto-switching. The plan's recommendation is to keep the code and update the
  document, and it says explicitly that it is flagging this rather than
  silently picking a side. Recorded as R-035; not resolved here.
- **§0.3 — mobile is ahead of web.** The desktop Main Dashboard is
  `DashboardPlaceholder.tsx`, a literal stub, while `MobileDashboardView.tsx`
  is a 666-line mature implementation. Recorded as R-037; this is a
  stakeholder-visible status fact and is reflected in `01-overview/`.
- **§4.5 — `MobileFundDetailView` and `MobileFundDetailSheet` duplicate each
  other.** The plan escalates this as a product and maintenance decision to
  raise, not to resolve unilaterally. Recorded as R-036, still open.
- **§4.9 — empty, loading and error states are the one real cross-cutting
  gap.** §3 adds a second, smaller gap: missing `inputmode` attributes on
  numeric inputs. Recorded as R-038.

Its sharing rule is worth preserving as architecture: share device-agnostic
screens, keep mobile-specific components only where density, input mode or
layout genuinely differ, and navigate with `onBack` props rather than routes —
the no-router position again. §4.3 records that auth and onboarding are purely
shared responsive web components with no mobile-specific tree at all. §3
confirms the mobile work needs no new design tokens. §0.2 notes the mobile
inspiration folder is entirely auth and onboarding screens, which is why the
survey had to reason about the rest from the code.

**The mobile auth/onboarding review plan (2026-08-19, v2.0)** records a
rejection in its own opening: v1 proposed a blurred, dark-scrimmed version of
the auth illustration as a full-bleed mobile background, and the product owner
reviewed that via mockup and rejected it — no blur, the real illustration
crisp and clearly visible. v2 is a crisp hero band using `left-panel-visual.svg`
with cover sizing and the focal point biased toward the top, which
intentionally crops the SVG's own baked-in headline, plus an overlapping white
card. The plan's most useful finding is how little needs to change: only the
`AuthShell` treatment below the `lg` breakpoint (the OTP screen inherits it
automatically, so there is zero OTP-specific work) and
`OnboardingCardStack.tsx`'s fixed placeholder offsets, which clip at 320–375px
widths. Two open items: the dark-mode treatment of the hero band is
undecided, and the 543KB SVG's paint cost still needs a check — a smaller risk
now that the blur is gone.

**The mobile privacy-onboarding full-screen plan (2026-08-20)** covers the
`TrustPrimer` privacy-points screen. This is **not** the legal Privacy Policy
tracked as R-023 — a distinction worth stating, because the filenames invite
the confusion. It adds `MobileOnboardingScreen.tsx` and validates a fixed
element order — top bar, headline, illustration, subtext, content, call to
action, with no eyebrow text — arrived at after two iterations with the
product owner. §5 splits the two privacy points client-side inside
`TrustPrimer.tsx` using internal state, and rejects the alternative of adding
a `trust_primer_2` onboarding step, because the backend's `onboarding_step`
persistence would have to accept a new value. The trade-off is stated: a user
who drops off mid-point-two resumes at point one. Two open items: privacy
point two has no dedicated illustration (the default is to reuse the existing
inline icon at illustration scale), and `AddFamilyMembers.tsx` uses the
`household` illustration variant while an unused `family` variant exists.

**The mobile UI elevation / landing page plan (2026-08-25)** is the most
candid document in the batch about its own inputs. It records that the five
stills in the "Mobile UI Inspo" folder **do not match** the premium 3D
pedestal/tilt video they were described as representing, and that the 3D
device-tilt direction was tried and rejected through mockup review — the
product owner reviewed three alternatives and picked this one. The validated
direction is a static phone frame with fragments drifting in and converging,
which the plan explicitly ties back to the desktop auth illustration's story:
scattered becoming one clear picture. §9 holds the dependency line — `gsap` is
already installed and currently unused anywhere in the codebase, and the plan
says not to reach for it here; zero new dependencies. §0 treats the 2026-08-19
auth hero band and the 2026-08-20 onboarding plan as out of scope and **not
confirmed implemented**, instructing the agent to check current state first.

### Deviation — decision or response taken

Two mockup-stage rejections (blurred hero band; 3D device tilt) are recorded
as dated decisions so the rejected alternatives survive. The doc-versus-code
routing contradiction is flagged, with the plan's own recommendation noted and
not applied — the document in question lives in the code repo, which this
vault does not modify.

### Result

Four documents, none with an execution record in this batch. The survey's
status findings — desktop dashboard still a stub, mobile mature, two
duplicated fund-detail components — are the durable output and are carried
into the risk register and the overview.

### Related

- R-035 — viewport auto-switch contradicts `MOBILE_APP_EXECUTION.md`
- R-036 — `MobileFundDetailView` / `MobileFundDetailSheet` duplication
- R-037 — the desktop Main Dashboard is still a placeholder
- R-038 — mobile empty/loading/error states and missing `inputmode`
- R-049 — small unresolved UI decisions from the mobile plans
- `06-architecture/frontend-composition.md` — update proposed
- Evidence: `08-evidence/documents/specs/2026-08-19-mobile-uiux-system-plan.md`
- Evidence: `08-evidence/documents/specs/2026-08-19-mobile-auth-onboarding-review-plan.md`
- Evidence: `08-evidence/documents/specs/2026-08-20-mobile-privacy-onboarding-fullscreen-plan.md`
- Evidence: `08-evidence/documents/specs/2026-08-25-mobile-ui-elevation-landing-page-plan.md`
