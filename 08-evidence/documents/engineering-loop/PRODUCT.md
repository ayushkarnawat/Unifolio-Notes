# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Indian mutual fund investors, spanning two segments deliberately served by
one single flow, not two: demanding, sophisticated HNI users who expect a
premium, serious tool, and first-time retail investors who need it to be
approachable. Both see the identical interface; the tension between the two
is resolved through tone/content, never through visual or flow variants
(PRD-02, "One flow, not two").

## Product Purpose

Unifolio is a mutual fund portfolio tracking and wealth-management platform
for the Indian market — positioned as a genuinely superior, free-core
alternative to Mprofit. It consolidates a user's Consolidated Account
Statement (CAS) data across AMCs/RTAs (CAMS, KFintech) into one holdings
view, and layers analytics on top (category allocation, direct-vs-regular
alpha, benchmark comparison, a proprietary fund/portfolio quality scorer).
Success is measured by accurate, trustworthy consolidation and genuinely
differentiated analytics, not by feature count.

## Positioning

Two things a neighboring product (Mprofit, or any of the 11 competitors
reviewed in this project's own competitive research) could not truthfully
copy: (1) the Scorer — a composite fund-quality score with a fixed,
disclosed methodology (45% return / 30% downside-risk / 25% category-beat
consistency) that is deliberately not a clone of any single existing
agency's formula; (2) the "Fund Signal" — extending the brand's own
logomark arc motif into an actual per-holding visual (a small radial arc
representing performance, expanding to a sparkline), something no reviewed
competitor does. More broadly: an Apple-inspired restraint in execution
(typography, color discipline, motion) applied to a data-dense holdings
product, where every other reviewed competitor in this market defaults to
a generic, cluttered fintech-dashboard look.

## Operating Context

Core workflows: CAS import (upload/parse CAMS or KFintech PDFs, review and
confirm parsed holdings), signup/onboarding, a main holdings dashboard, and
an analytics dashboard. Authentication is phone+OTP, Google, and email+OTP
— explicitly passwordless across all three methods (a 2026-08-17 reversal
of a same-day password experiment; see this repo's `decisions.md`), with
every account converging on a verified phone number as a mandatory second
step regardless of which method started signup.

## Capabilities and Constraints

- `Decimal`, never `float`, for every money/units/NAV value anywhere in the
  system — a repeated, non-negotiable requirement.
- No raw CAS PDF storage, ever. No PAN persistence, ever.
- Backend: one FastAPI monolith (four logical services: Auth, Import,
  Dashboard, Analytics — not four deployments). Frontend: one React 19 +
  Vite + TypeScript + Tailwind SPA, shadcn/ui component primitives already
  in place (`components.json` configured). No second frontend/backend
  framework, no microfrontends/microservices at this team size.
- Local-development-first: SQLite (dev) + local Postgres container for
  functional-test parity; AWS deployment is explicitly out of scope until
  a separate migration-readiness checklist is met.
- This is an MVP prototype: build what's scoped solidly (including real
  schema concerns like table partitioning and reference-data separation),
  but deliberately do not gold-plate features the product's own PRDs have
  scoped out for this phase.

## Brand Commitments

- Name: **Unifolio**. Wordmark with the accent green appearing as a small
  arc inside the "o" of "folio" — reads as a dial/gauge motif, and is the
  one place the existing brand identity already introduces a shape
  language (an arc/partial-circle, a sense of measurement) beyond flat
  color blocks.
- Locked brand colors (from `Docs/brand/Unifolio Brand Identity.pdf`):
  `#111111` (ink), `#FCFCFC` (near-white, not pure white), `#22C55E`
  (accent green) — the accent is the brand's one signature color, used
  deliberately and sparingly (primary actions, the brand mark, positive-
  value semantics), never as a large decorative fill.
- Typography: DM Sans (headings/display) and Manrope (body/data/captions),
  as implemented in this codebase's design tokens.
- Design philosophy (from this project's own Design Brief, locked):
  Apple-inspired, not Apple-generic — generous whitespace, one clear
  visual hierarchy, rounded-not-sharp shape language, and explicit
  rejection of "the near-black-plus-acid-accent look that's become a
  generic AI-generated default." Motion follows "reveals over pop-ins":
  data appearing should feel like a deliberate reveal, never gamified
  (no points, badges, streaks, or confetti anywhere in the product).
- Full token system (exact hex/spacing/type-scale values) is implemented
  in this codebase already: `frontend/src/styles/tokens.css` and
  `frontend/tailwind.config.js`.

## Evidence on Hand

- `Docs/brand/Unifolio Brand Identity.pdf` — source logo, color, and font
  assets.
- `Docs/PRDs/Design-Brief-Unifolio-updated.md` and
  `Docs/PRDs/Design-Schema-Unifolio.md` — the locked visual-direction and
  executable-token documents for this product; authoritative over any
  new visual proposal that conflicts with them.
- `Docs/PRDs/PRD-01` through `PRD-04` — functional requirements per
  module (CAS import, onboarding, main dashboard, analytics).
- `decisions.md` (repo root) — append-only dated decision log; the most
  recent entries reverse a same-day password-auth experiment back to
  passwordless email+OTP.
- No customer testimonials, case studies, press mentions, or usage
  metrics exist yet — none should be fabricated or implied by any new
  design work.

## Product Principles

1. **Numbers are the product.** Financial data (the holdings table,
   allocation views, the scorer) is the actual value delivered, not
   decoration around a marketing page — precision and traceability matter
   more than visual flourish, and the design must never imply more
   confidence than the underlying data has.
2. **Apple-inspired restraint over generic-AI-fintech styling.** Generous
   whitespace, one hierarchy per screen, the near-white/ink/muted-accent
   palette read as considered — explicitly not the near-black-plus-glow
   look this project has repeatedly identified as the anti-pattern to
   avoid.
3. **One flow, not segmented by user type.** No retail-vs-HNI visual or
   flow variants; the same screens serve both.
4. **Game-like pacing, never game-like mechanics.** Deliberate reveals and
   a sense of progress, expressed through motion and sequencing only —
   never gamification UI (points, badges, streaks, confetti).
5. **Proven structure, distinctive execution.** Information architecture
   for data-heavy screens follows the validated competitive pattern
   (holdings + allocation + gains); the product's distinctiveness lives in
   typography, color discipline, motion, and the Fund Signal/Scorer — not
   in reinventing what data goes where.

## Accessibility & Inclusion

Responsive down to mobile is non-negotiable (target users are consumer
investors, not enterprise desktop users). Visible keyboard focus states
throughout. Color is never the sole carrier of meaning (gain/loss,
verification status) — always paired with a secondary signal (icon, label,
position). Light and dark mode must each independently meet contrast
standards.
