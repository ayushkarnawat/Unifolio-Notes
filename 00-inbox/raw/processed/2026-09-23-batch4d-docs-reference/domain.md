# Domain Docs

This repo does **not** use the generic `CONTEXT.md` / `docs/adr/` layout the engineering
skills default to. It already has an established documentation system under `/Docs` —
skills should read *that*, not create the generic scaffold alongside it.

## Before exploring, read these (in this order)

This is the same order `CLAUDE.md`'s own "Read this first, every session" section
specifies — that section is authoritative; this file just points skills at it.

1. `Docs/PRDs/Database-Schema-Unifolio.md` — the schema, exact and final
2. `Docs/PRDs/TDD-Unifolio.md` — architecture, API surface, external integrations
3. `Docs/PRDs/ADR-Technical-Stack-Decisions.md` — the Accepted ADRs (stack is locked,
   don't relitigate)
4. The specific `Docs/PRDs/PRD-0X-*.md` for whatever module is in scope
5. `Docs/PRDs/App-Flow-Unifolio.md` — screen-to-screen navigation for the module
6. `Docs/PRDs/Design-Brief-Unifolio.md` and `Docs/PRDs/Design-Schema-Unifolio.md` — for
   anything UI

## Per-feature design decisions (this repo's ADR-equivalent for feature-level work)

Dated design/spec docs live in `Docs/superpowers/specs/` and `Docs/superpowers/plans/`
(e.g. `2026-08-14-analytics-frontend-design.md`) — check these for the area about to be
touched, the way `docs/adr/` would be checked elsewhere. They're named by date and
feature, not numbered.

## Session history / current status

`session.md` at the repo root, plus the "Session State" section of `CLAUDE.md`, are the
running log of what's built, what's in flight, and what's still open. Read `CLAUDE.md`'s
Session State pointer before starting new work — don't assume it from code alone.

## Use the glossary's vocabulary

Match terminology to what's used in the PRDs, TDD, and Scorer methodology doc (e.g.
"Scorer", "TER", "NAV warming", "distributor comparison") — don't drift to synonyms
these docs don't use.

## Flag conflicts

If a proposed change contradicts an existing PRD, ADR, or schema decision, follow
`CLAUDE.md`'s own non-negotiable: stop and say so — don't silently resolve the conflict
in either direction.

## Don't create the generic layout

Do not create `CONTEXT.md`, `CONTEXT-MAP.md`, or `docs/adr/` for this repo. If a skill
(e.g. `/domain-modeling`) would normally create one of these lazily, add the material to
the relevant existing `Docs/PRDs/*.md` file instead, or propose a new file under
`Docs/superpowers/specs/` following that folder's existing dated-spec convention.
