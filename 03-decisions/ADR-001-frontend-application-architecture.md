# ADR-001: Frontend application architecture — React SPA on Vite, no Next.js, no micro-frontends

Status: Accepted
Date: 2026-07-22
Related: Amended 2026-08-05 (see Context); `06-architecture/building-blocks.md`;
`05-docs/reference/design-tokens.md`; ADR-005 (where the build is served from)

## For stakeholders

We needed to settle what the Unifolio web app is built on before the team grew,
because changing that later is expensive. Two proposals were on the table: move to
Next.js, and split the app into independently-deployed "micro-frontends." We kept the
existing choice — one React application built with Vite — because Unifolio is entirely
behind a login, so the search-engine and public-page advantages Next.js is built for do
not apply, and because micro-frontends solve a coordination problem that appears at
roughly eight to ten frontend engineers, not at a team of three. The cost of this
choice is that if we ever want a public marketing site, it will be a separate small
project rather than an extension of this one, and every module ships on the same
release train. The decision is made and in force; the only follow-up is that a
correction was logged on 2026-08-05 about why it was made, not about what was chosen.

## Technical detail

### Context

The Import Review screen for CAS Parser v2 was scoped as a Vite + React SPA in the
original build spec. A later proposal suggested Next.js, and separately "pure React +
micro-frontend components" as a structural pattern. These are two independent axes and
were separated deliberately: (1) Next.js vs. a plain React SPA is a *framework* choice;
(2) micro-frontends vs. one modular application is an *organisational* architecture
choice that is largely independent of the framework underneath it.

**Amendment, 2026-08-05 — a factual correction, not a change of decision.** The
original Context and the first "Positive consequence" assumed the Import Review screen
was existing, in-progress React work this decision would preserve. Checked against the
actual prototype during Phase 1, that assumption was **false**: the code at
`CAS Parsers/mf-import/frontend` was vanilla TypeScript + Vite — no React, no JSX,
plain `.ts` page files driving the DOM. There was no in-progress React screen to keep.
Phase 1's Import Review UI was therefore written as new React code, not ported. The
decision stands unchanged on its own merits; the "no rework" benefit below should be
read as **moot**, not as a benefit that was realised.

### Decision drivers

- Unifolio is a logged-in, authenticated dashboard. No public marketing pages and no
  SEO-dependent content are in MVP scope — everything sits behind OTP auth.
- The team is two founders plus one incoming engineer, not a multi-team organisation.
- A mid-August MVP target made framework churn a concrete, immediate cost.
- Design-system consistency: the Design Schema's tokens and cross-cutting components
  (the Fund Signal appears on both the Main Dashboard and Import Review) assume one
  application.

### Options considered

#### Option 1: React SPA on Vite, single modular application (chosen)
**Advantages:** one build and one deployment pipeline, appropriate for a 2–3 person
team; fast dev server and build times without SSR/routing machinery the product does
not need; shared state and design tokens are trivially consistent across modules;
internal boundaries by feature (Import Review, Onboarding, Main Dashboard, Analytics)
give most of the modularity benefit at none of the operational cost.
**Disadvantages:** no per-module release cadence — an Analytics-only fix goes through
the same pipeline as everything else; no built-in path to SSR if that is ever needed.

#### Option 2: Next.js
**Advantages:** strong general-purpose framework; built-in image optimisation,
file-based routing, and a straightforward path to server-side rendering.
**Disadvantages:** its core advantages target SEO and content-heavy public pages —
problems Unifolio does not have in this MVP, since everything is behind auth. Adopting
it meant rewriting in-progress work for benefits that do not apply yet.

#### Option 3: Pure React + micro-frontend components
**Advantages:** independent deploys per module; team autonomy at scale.
**Disadvantages:** micro-frontends address a *team-coordination* problem — independent
teams needing independent deploys — that does not exist at three people. Multiple
2025–2026 sources, including documented cases of small teams adopting MFE "to prepare
for scale" and reverting within months, converge on "start with a well-structured
monolith, split later if organisational scaling pain becomes the dominant bottleneck."
Shared theming and cross-cutting components are specifically flagged as materially
harder under MFE — which is exactly what the Design Schema depends on.

### Decision

Continue with a **React SPA built by Vite**. Do not adopt Next.js. Do not adopt
micro-frontends. The frontend stays one modular React application with clear internal
component/feature boundaries by module: Import Review, Onboarding, Main Dashboard,
Analytics Dashboard.

### Consequences

**Positive:**
- Single build, single pipeline — consistent with current guidance that micro-frontend
  overhead is not justified below roughly 8–10 frontend developers.
- Vite's dev server and build stay fast without Next.js's SSR/routing layer.
- Shared state and Design Schema token consistency across the whole app.
- *(Originally listed: "no rework of the CAS Parser v2 frontend already in progress."
  Per the 2026-08-05 Amendment this is moot — there was no React work to preserve.)*

**Negative:**
- Forgoes Next.js image optimisation, file-based routing, and an easy SSR path. A
  future public-facing surface would need a separate project.
- No independent deploy/release cadence per module. Acceptable at current team size;
  revisit only well past ~10 frontend engineers.

**Neutral:**
- A future marketing/landing site can reasonably be a separate small Next.js or static
  site rather than folded into the authenticated app — different product, different
  constraints.

### Validation

The decision is validated if the single-pipeline model stays comfortable through MVP:
no module blocked waiting on another module's release, and no design-token divergence
between Import Review and the dashboards. The trigger to revisit is organisational, not
technical — sustained pain from teams blocking each other on deploys.

### Evidence

- Source document: `08-evidence/documents/ADR-Technical-Stack-Decisions.md`
  (ADR-001 and the 2026-08-05 Amendment)
- Referenced but **not held in this vault**: `Planning-V1.MD` / `MF_CAS_Parsers.md`
  (original build spec), `Docs/superpowers/plans/` (Phase 1 plan). Queued for a later
  batch.
