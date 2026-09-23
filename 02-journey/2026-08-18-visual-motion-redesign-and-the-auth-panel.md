# A visual and motion redesign, and four concepts for one auth panel

## For stakeholders

Over roughly 48 hours the team produced three design documents covering the
sign-in, onboarding and import-review screens. The first is a full visual and
motion specification handed to an external coding agent. The second and third
narrow onto a single decorative panel on the sign-in screen — and in doing so
reveal that this one panel went through four different creative concepts in
two days, two of which were built out and then dropped after mockup review.
The work is high quality and the rejections were made for defensible reasons,
but the pattern is worth naming: a decorative element with no functional
requirement consumed several rounds of design and implementation effort, and
at the end of the batch there is no single accepted design record for it.

## Technical detail

### Intended outcome

Raise the visual and motion quality of the authentication, onboarding and
import-review surfaces to a premium standard, without changing product
behaviour, and hand the implementation to an external coding agent.

### What actually happened

**The 2026-08-18 spec (v1.0)** is a full design system application, written
explicitly for a coding agent such as Google Antigravity. Its discipline is
notable:

- **Zero design-token value changes.** The one stated exception is a
  cream-and-gold pairing that exists only inside `OnboardingIllustration.tsx`'s
  SVG fills.
- **State machines frozen**, with exactly two named structural exceptions:
  `AuthShell` (§4.2) and `OnboardingCardStack` (§4.6). Everything else keeps
  its existing local step machine — the no-router position holds.
- New components: `components/ui/otp-input.tsx`, `AuthShell.tsx`,
  `ImportFileProgressList.tsx`, `OnboardingIllustration.tsx`,
  `OnboardingCardStack.tsx`.
- **The motion system is three existing tokens** (`--motion-fast` 150ms,
  `--motion-reveal` 400ms, `--motion-page` 300ms), two stagger tiers, and
  exactly two shared-element anchors (`fund-signal-ring`, `brand-mark`).
- `ReviewTable` is deliberately left calm — the spec's position is that a data
  table under review is not a place for motion.
- §9 records that **no mobile-specific onboarding views exist** in the codebase.
- It ends with a ready-to-paste agent prompt that requires the agent to name
  itself in `session.md` and `CLAUDE.md`, preserving provenance.

**The 2026-08-19 auth-left visual redesign (v2.0)** opens by superseding §4.3
and §5.5 of the previous day's spec for that component specifically, and
explains why: the "fund-signal ring" that spec described **was never what got
built**. What actually shipped (identified in the document by commit
`75a1925`) is a chaos-loop-to-grid performance-path graphic with milestone
hover tooltips. The document also records that its own v1 — particles
converging into the brand arc — "was built out through several mockup rounds
and ultimately dropped", because it kept reading as decorative rather than as
the product's story.

v2's concept is "fragments align and sharpen into one view", rendered as four
plain rounded rectangles. It removes the chaos-loop constants, the path
definition, the grid row/column constants, a rocket glyph, an inner "screen
card", the five-point milestone tooltip system, and a green-to-gold gradient.
It keeps the once-per-session animation guard, the reduced-motion and
test-environment guards, the dark backdrop, and the `AuthShell` visual slot.
It also prefers framer-motion's declarative `animate` prop over the
hand-rolled `requestAnimationFrame` loop, which existed only to drive SVG path
sampling — a net simplification rather than a rewrite. The visual is
`aria-hidden`; the bottom vignette is a hard requirement.

**The 2026-08-19 editorial refinement plan** then takes a fourth direction —
"Direction B", an editorial and typographic treatment of
`AuthShowcasePanel.tsx`. It is aimed at Google Antigravity explicitly, not at
Claude Code's own subagent tooling. Notable content:

- It adds new tokens: `--auth-panel-bg`, `--auth-panel-bg-2`,
  `--auth-panel-ink`, `--auth-panel-ink-soft`, `--auth-panel-glow`,
  `--auth-panel-ghost`, `--auth-panel-ghost-soft`, plus `--motion-hero-reveal`
  and `--motion-hero-stagger`.
- It records the panel as **an intentional, documented exception to the app's
  light/dark theme system — it is always dark**.
- The component had **zero test coverage**; Task 2 closes that gap before the
  visual change lands, test-first.
- Three small cleanups are bundled in: `rounded-3xl` to `rounded-lg`, dropping
  `select-none` from prose, and demoting an `<h1>` to a `<p>` so the page has
  one true heading.
- It states product positioning directly: Unifolio is positioned as a
  materially better, more premium alternative to Mprofit; and "No points,
  badges, streaks, or confetti anywhere in this product."

**The 2026-08-19 CAS-import illustration redesign (v2.0)** belongs to the same
push. Its v1 — decorating the existing tab-bar-and-dense-card layout — was
reviewed against mockups and rejected as not enough visual change, though v1's
diagnosis of the UX problem was kept as accurate. v2 adds an
`ImportPathChoice.tsx` screen mirroring the existing `Q4Household.tsx`
pattern, corrects the CAMS-request instructions (detailed statement, ten-year
duration, include zero-balance folios), makes `onBack` optional on
`UploadForm`, and adds a "waiting" screen with a collapsed "Already got the
email? Upload it now" affordance. Three findings are recorded along the way:
the "Step 1 / Step 2" framing in the existing UI is a mislabel;
`CoverageGapBanner` is still on an older visual system; and
`OnboardingIllustration`'s `"upload"` variant **already exists, was built for
this flow, and was never wired in**.

### Deviation — decision or response taken

Four concepts for one decorative panel in 48 hours: fund-signal ring (specified
2026-08-18, never built) → chaos-loop-to-grid (actually shipped, commit
`75a1925`) → particles-into-arc (2026-08-19 v1, built through several mockup
rounds, dropped) → fragments-align-and-sharpen (2026-08-19 v2) → editorial
"Direction B" (2026-08-19 plan, tasks 1–2 executed). No document in this batch
reconciles the last two. Recorded as R-033.

The always-dark exception to the theme system is a real architectural
carve-out and is proposed as a dated decision and a reference-doc update
rather than left in a plan file.

### Result

The 2026-08-18 spec was handed off; the editorial plan's first two tasks are
ticked (test coverage added, then the visual change) with its verification
task unticked. The two 2026-08-19 design specs carry no execution record in
this batch at all. The 2026-08-25 mobile plan later states plainly that these
should not be assumed implemented and that the agent should check current
state first — a caution this vault should repeat rather than resolve.

### Related

- ADR-011 — model orchestration (external agents remain outside its scope, R-029)
- R-033 — four concepts for one panel, with no accepted design record
- R-034 — `OnboardingIllustration`'s `"upload"` variant is built but unwired
- `05-docs/reference/design-tokens.md` — update proposed for the new tokens
- Evidence: `08-evidence/documents/specs/2026-08-18-auth-onboarding-import-review-visual-motion-redesign.md`
- Evidence: `08-evidence/documents/specs/2026-08-19-auth-left-visual-redesign.md`
- Evidence: `08-evidence/documents/plans/2026-08-19-auth-left-panel-editorial-refinement.md`
- Evidence: `08-evidence/documents/specs/2026-08-19-cas-import-illustration-redesign.md`

## Addendum — 2026-09-22: the chaos-loop-to-grid panel's build event is directly evidenced, plus new same-day execution

This stage's "Result" states the two 2026-08-19 design specs ("fragments-
align-and-sharpen" and editorial "Direction B") "carry no execution record
in this batch at all" — that remains true; neither is corroborated by this
later-ingested material either. What this material does add: a direct
build-event record (not merely the v2.0 spec's own claim) for the earlier
chaos-loop-to-grid graphic itself (commit `75a1925`) — a session titled
"Left Auth Panel Motion, Auth Validation Engine, and Hand-Drawn Hero
Illustrations Integration" describes building "one deliberate continuous
trajectory drawing smoothly along its actual SVG path from chaotic
waveform to structured compounding" with a `hasAnimatedInSession` guard and
cursor-hover milestone tooltips at exactly `+14.8%`, `+28.4%`, `+41.2%`,
`+56.8%` — consistent with, and more specific than, this entry's existing
"chaos-loop-to-grid ... with milestone hover tooltips" description. The
same session also executed a comprehensive email/phone frontend validation
engine (typo suggestions, Indian mobile normalization, 30/30 unit tests)
and integrated the hand-drawn hero illustrations into
`OnboardingIllustration.tsx`, `Q4Household.tsx` and `TrustPrimer.tsx` —
both previously only specified, now confirmed built. R-033's core finding
is unchanged: no document reconciles which of the later concepts, if any,
superseded this one.

### Addendum evidence

- `08-evidence/documents/engineering-loop/log.md`, "2026-08-19 — Left Auth
  Panel Motion, Auth Validation Engine, and Hand-Drawn Hero Illustrations
  Integration" section
- `08-evidence/documents/engineering-loop/decisions.md`, "2026-08-19 — Left
  Auth Showcase Panel: Single Continuous Deliberate SVG Path Motion",
  "Comprehensive Frontend Validation & Typo Detection Engine", and
  "Hand-Drawn Hero Illustrations & Bespoke Option Card SVGs" entries
