# Unifolio Mobile App Execution

## Purpose

Defines mobile-specific implementation decisions for the Unifolio frontend.

The existing Unifolio PRDs, Design Brief, Design Schema, App Flow, TDD, and `FRONTEND_EXECUTION.md` remain the source of truth. This document must not duplicate them.

## Architecture

- Mobile UI lives under `frontend/src/mobile/`.
- Web and mobile presentation layers remain isolated.
- Reuse existing API clients, types, utilities, hooks, and design tokens where applicable.
- Do not modify approved web components to satisfy mobile requirements.
- Use the existing backend and API contracts.

## Mobile-Specific UI

- Design mobile screens as mobile-first experiences; do not simply shrink web layouts.
- Minimum interactive target: 44px.
- Account for mobile safe areas and dynamic viewport height.
- Use mobile-appropriate navigation, sheets, gestures, and touch interactions where required.
- Mobile-specific presentation may differ from the web while preserving the same product semantics.

## Web vs Mobile

The approved web UI and mobile UI are separate presentation experiences.

Mobile-specific UX decisions must not modify or compromise the approved web experience.

## Development

- Mobile preview: `/mobile`
- Mobile preview must not automatically replace the web experience based on viewport/device detection.
- Use the existing frontend test/build infrastructure.
- Validate mobile layouts at 320px, 375px, and 430px.

## Mobile-Specific Decisions

Record only decisions that intentionally differ from the web experience.

### Holdings

Mobile holdings use a summary-first presentation:

- FundSignal
- Scheme name
- Member
- Current Value

Selecting a holding opens its detailed mobile view containing the full existing holding information.

The approved web Holdings presentation remains unchanged.