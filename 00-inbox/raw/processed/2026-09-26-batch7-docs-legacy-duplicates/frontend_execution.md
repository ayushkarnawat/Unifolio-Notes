# Unifolio — Frontend Execution Specification

> Tool-independent implementation contract for the Unifolio frontend redesign.

---

## 1. Purpose

This document defines how the Unifolio frontend redesign must be executed.

It is intentionally tool-independent.

It applies regardless of whether implementation is performed using:

- Antigravity
- Claude Code
- Codex
- another coding agent
- human developers

This document does NOT replace the existing Unifolio product or design documentation.

It defines implementation rules, scope, architecture decisions, workflow constraints, and quality expectations for the frontend redesign.

---

# 2. Source of Truth

The following existing project documents remain the authoritative sources for their respective domains:

### Product requirements
- PRDs

### Visual/product design
- Design Brief
- Design Schema

### User flows and screen behavior
- App Flow

### Technical architecture and API contracts
- TDD

### Repository/project conventions
- CLAUDE.md
- SESSION.md, where applicable

This document must not duplicate those documents.

When a conflict exists:

1. Explicit product requirements take precedence for product behavior.
2. Design Schema takes precedence for visual/design-system decisions.
3. App Flow takes precedence for screen and navigation behavior.
4. TDD takes precedence for technical architecture and API boundaries.
5. This document governs frontend implementation workflow and scope.

If a requirement is unclear or contradictory, stop and surface the ambiguity rather than inventing behavior.

---

# 3. Current Objective

The current objective is:

> Transform the existing Unifolio MVP frontend from its current basic UI into a premium, production-quality financial application interface while preserving existing product functionality.

The redesign should improve:

- visual hierarchy
- typography
- spacing
- component consistency
- information density
- data visualization
- interaction quality
- responsive behavior
- accessibility
- loading/empty/error states
- perceived product quality

The redesign must remain faithful to the existing Unifolio product and design direction.

This is a UI enhancement project, not a product rewrite.

---

# 4. Current Git Scope

All frontend redesign work must happen on:

`feat/enhanced-ui`

Do not perform frontend redesign work directly on:

- `main`
- `dev_intern`

Do not modify or rewrite unrelated branches.

Changes made on this branch should remain focused on the frontend redesign.

---

# 5. Explicit Scope

## In scope

The current frontend redesign includes:

- existing MVP screens
- application shell
- navigation
- dashboard UI
- portfolio presentation
- holdings presentation
- fund detail UI
- distributor comparison UI
- CAS/import UI
- onboarding UI
- reusable UI components
- visual states
- responsive behavior
- accessibility
- data visualization used by existing MVP screens
- design-system implementation
- UI polish and interaction refinement

The objective is to improve the existing product experience without changing its underlying business behavior.

---

# 6. Explicitly Out of Scope

## Analytics Dashboard

The PRD-04 Analytics Dashboard frontend is explicitly OUT OF SCOPE for this phase.

Do NOT:

- build Analytics frontend screens
- create Analytics routes
- create Analytics components
- integrate Analytics frontend APIs
- redesign Analytics UI
- modify Analytics backend
- modify PRD-04 backend implementation

The Analytics backend is currently being developed separately.

Analytics frontend work will begin only after the Analytics backend is complete and explicitly brought into scope.

Do not use the existence of Analytics backend endpoints as justification for implementing Analytics UI now.

---

## Other feature development

Do not expand the MVP merely because backend functionality exists.

Do not implement new product capabilities unless explicitly required by the current product/design documents or separately requested.

Examples of potentially out-of-scope feature expansion include:

- new portfolio functionality
- new analytics functionality
- new financial calculations
- new workflows
- new API endpoints
- new backend services

The goal is premium frontend execution of the existing product.

---

# 7. Preserve Existing Functionality

The redesign must preserve:

- existing API contracts
- existing backend behavior
- existing financial calculations
- existing authentication behavior
- existing import behavior
- existing navigation behavior unless visual restructuring requires it
- existing business rules

Do not change backend contracts merely to simplify frontend implementation.

Do not move financial calculations from the backend into the frontend.

Do not introduce client-side approximations of authoritative financial values.

---

# 8. Financial Data Safety

Financial data must be treated as high-integrity data.

Preserve the existing backend/frontend handling of:

- Decimal values
- BigInt values
- monetary values
- units
- percentages
- dates
- timestamps
- financial identifiers

Do not introduce JavaScript floating-point calculations where authoritative backend values already exist.

Do not silently round or transform financial values.

Formatting for presentation is allowed only when it does not alter the underlying value.

---

# 9. Planned Frontend Stack

The planned UI implementation stack is:

### Core
- React
- Vite
- TypeScript

### Styling
- Tailwind CSS

### UI primitives
- shadcn/ui

### Data visualization
- Bklit UI

### Product-specific UI
- custom Unifolio components

### Visual QA
- browser-based testing and screenshot/visual inspection where appropriate

The exact versions and configuration must be determined from the existing project before installation.

Do not blindly replace the existing frontend architecture.

---

# 10. Library Responsibilities

## shadcn/ui

Use shadcn/ui as a foundation for general-purpose accessible UI primitives.

Appropriate examples include:

- Button
- Input
- Label
- Select
- Dialog
- Dropdown
- Tabs
- Tooltip
- Card
- Table
- Sheet
- Alert
- Skeleton

shadcn/ui provides implementation primitives.

It does NOT define Unifolio's visual identity.

All shadcn components must be themed according to the Unifolio Design Schema.

Do not leave default shadcn styling unchanged where it conflicts with Unifolio's design system.

---

## Bklit UI

Use Bklit UI for appropriate data-visualization requirements.

Potential uses include:

- allocation visualization
- performance charts
- NAV trends
- sparklines
- other financial data visualizations

Bklit is a visualization implementation layer.

It does NOT define Unifolio's visual identity.

Charts must follow the Unifolio Design Schema for:

- colors
- typography
- spacing
- visual density
- interaction
- motion
- semantic meaning

Do not introduce unnecessary chart types.

Do not use multiple chart libraries for the same purpose without a clear technical reason.

---

# 11. Custom Unifolio Components

Some UI must remain custom because it represents Unifolio-specific product identity.

Examples include:

- Fund Signal
- portfolio-specific summary components
- specialized financial data displays
- product-specific cards
- unique interactions
- signature visual elements

Do not replace a distinctive Unifolio component with a generic library component simply because a similar primitive exists.

---

# 12. Fund Signal

Fund Signal is a signature Unifolio visual component.

It must remain a custom Unifolio component.

Do NOT replace it with:

- a generic circular progress bar
- a generic gauge
- a generic ring chart
- a generic progress component

The implementation must follow the Design Schema's specified relationship to the Unifolio visual identity and logo arc geometry.

Any significant change to its conceptual design requires explicit review before implementation.

---

# 13. Design System Rules

The Design Schema is the authoritative source for:

- colors
- typography
- spacing
- radii
- elevation
- component styling
- charts
- motion
- accessibility

Do not invent competing design tokens.

Do not introduce arbitrary colors, spacing values, radii, shadows, or typography without justification.

Prefer existing design tokens over hardcoded values.

If an existing implementation conflicts with the Design Schema, migrate it toward the Design Schema rather than creating another parallel token system.

---

# 14. Typography

Follow the typography system defined in the Design Schema.

Do not introduce arbitrary fonts.

Use the designated Unifolio typography roles consistently for:

- headings
- body text
- captions
- financial data
- labels
- navigation
- controls

Financial/data values should retain appropriate tabular-number behavior where specified.

---

# 15. Existing Design Tokens

The current frontend already contains a design-token/CSS-variable foundation.

Do not discard it blindly.

Before replacing styling infrastructure:

1. inspect the existing tokens
2. compare them with the Design Schema
3. identify gaps
4. preserve compatible tokens
5. migrate systematically

Avoid creating duplicate sources of truth.

The final implementation should have one coherent design-token system.

---

# 16. Styling Migration Strategy

The redesign must be incremental.

Do NOT:

- delete all existing CSS
- rewrite every component simultaneously
- replace all CSS Modules blindly
- rewrite the entire frontend
- migrate every screen before validating the foundation

Preferred strategy:

1. establish the design-system foundation
2. integrate Tailwind
3. initialize/configure shadcn
4. establish Unifolio-themed primitives
5. introduce Bklit where appropriate
6. migrate reusable components
7. migrate screens incrementally
8. remove obsolete styles only after replacement is verified

Existing functionality must remain operational throughout the migration.

---

# 17. Routing

Do not introduce a routing rewrite solely as part of the visual redesign.

Preserve the current routing/navigation architecture unless a separate requirement explicitly calls for routing changes.

Visual improvements should not require unnecessary architectural changes.

---

# 18. API Boundaries

The frontend must consume the existing backend APIs according to the TDD.

Do not:

- change API contracts
- rename API fields
- change backend response structures
- create duplicate calculation logic
- add backend endpoints as part of a UI-only task

If the current API is insufficient for a required existing screen, document the gap instead of silently changing the backend.

---

# 19. Component Architecture

Prefer reusable components over page-specific duplication.

Components should have clear responsibilities.

Avoid:

- giant page components
- duplicated UI patterns
- hardcoded screen-specific variants when a reusable abstraction is appropriate
- unnecessary abstraction before repetition exists

Create abstractions when there is a real repeated pattern.

Do not build a massive generic design system beyond what Unifolio needs.

---

# 20. Screen Implementation Strategy

Implement screens incrementally.

Preferred order:

1. Design-system foundation
2. Application shell/navigation
3. Core reusable primitives
4. Data-visualization primitives
5. Fund Signal
6. Main Dashboard
7. Fund Detail
8. Distributor Comparison
9. CAS/import experience
10. Onboarding
11. Secondary/edge states
12. Responsive and accessibility refinement
13. Final visual QA

Analytics is excluded from this sequence.

---

# 21. UI States

Every relevant screen/component should account for appropriate:

- default
- loading
- empty
- error
- disabled
- success
- stale-data
- partial-data

states where applicable.

Do not only implement the happy path.

States must follow the Design Schema and existing product behavior.

---

# 22. Responsive Design

Responsive behavior is part of the implementation, not a final optional polish step.

Consider:

- desktop
- tablet
- mobile

during component and screen implementation.

Do not simply shrink desktop layouts for mobile.

Tables, navigation, charts, cards, financial data, and controls should receive appropriate responsive treatment.

---

# 23. Accessibility

Preserve and improve accessibility.

Pay attention to:

- semantic HTML
- keyboard navigation
- focus states
- accessible labels
- contrast
- non-color-only communication
- form accessibility
- table accessibility
- reduced motion

Accessibility should not be sacrificed for visual polish.

---

# 24. Motion

Motion must follow the Design Schema.

Prefer:

- subtle transitions
- purposeful state changes
- restrained animation

Avoid:

- decorative animation everywhere
- excessive spring effects
- animation that delays usability
- motion that conflicts with reduced-motion preferences

---

# 25. Visual Quality Standard

The target is:

> premium financial-product UI

not:

> generic AI dashboard

The interface should feel:

- intentional
- restrained
- trustworthy
- polished
- spacious
- data-focused
- premium
- consistent

Avoid:

- excessive gradients
- excessive glassmorphism
- rainbow charts
- unnecessary shadows
- excessive rounded containers
- decorative clutter
- generic AI/SaaS visual patterns
- inconsistent component styling

The Design Brief defines the intended visual personality.

---

# 26. Implementation Workflow

For significant UI work, follow:

1. Inspect existing implementation.
2. Identify the relevant Design Brief/Schema requirements.
3. Identify reusable components.
4. Implement the smallest appropriate change.
5. Run the application.
6. Verify functionality.
7. Inspect visual result.
8. Check responsive behavior.
9. Check accessibility.
10. Review for consistency with the Design Schema.
11. Only then move to the next component/screen.

Do not make large unverified batches of UI changes.

---

# 27. Visual QA

Visual quality should be evaluated using the running application rather than source code alone.

For significant screens:

- inspect desktop
- inspect mobile
- inspect important states
- verify typography
- verify spacing
- verify alignment
- verify component consistency
- verify chart readability
- verify financial data formatting

Where visual QA tooling is available, use browser screenshots and visual inspection.

---

# 28. Impeccable / Design-Critique Tools

If an AI design-critique tool such as Impeccable is available, it may be used for visual critique and refinement.

However:

- critique must remain subordinate to the Unifolio Design Schema
- recommendations that conflict with the Design Schema should not be adopted automatically
- visual polish must not change product behavior
- critique tools should not introduce a competing design language

---

## Apple Design Principles

When available, the Apple Design skill may be used as a design reference for interaction quality, hierarchy, motion, feedback, spatial consistency, restraint, depth, and accessibility.

Apple-inspired principles must be adapted to Unifolio rather than copied literally.

The Unifolio Design Brief and Design Schema remain authoritative for:
- brand identity
- colors
- typography
- spacing
- radii
- component styling
- data visualization
- overall visual language

Do not introduce Apple-specific branding, UI patterns, typography, or visual materials when they conflict with Unifolio's design system.

---

## Responsive & Mobile-Ready Design

Responsive behavior is part of component design, not a final QA step.

Every new or modified frontend component should consider:
- small mobile: 320px
- mobile: 375–430px
- tablet: 768px
- small desktop: 1024px
- desktop: 1440px+

Requirements:
- No unintended horizontal page overflow.
- Desktop layouts must reflow rather than simply shrink on mobile.
- Dense financial tables should use an appropriate mobile presentation rather than forcing desktop tables into narrow screens.
- Navigation and controls must adapt to available space.
- Charts and visualizations must resize/reflow appropriately.
- Typography, spacing, and hierarchy should remain intentional at each breakpoint.

The future Unifolio mobile app should share the web application's:
- design tokens
- visual language
- semantic hierarchy
- product terminology
- interaction principles

However, mobile-app components should be implemented according to their native/platform requirements rather than forcing web components to be reused directly.

Responsive behavior should be considered during initial component implementation for every future screen.

---

# 29. AI Coding Agent Rules

Any AI coding agent working on this branch must:

1. Read this document before implementation.
2. Read the relevant source-of-truth documents before changing a screen.
3. Inspect existing code before creating replacements.
4. Preserve existing functionality.
5. Avoid unnecessary architectural changes.
6. Avoid scope expansion.
7. Ask/surface ambiguity rather than inventing product behavior.
8. Keep changes focused on the current task.
9. Verify changes before declaring the task complete.
10. Never assume that a library's default styling is the Unifolio design.
11. Treat responsive behavior as a first-class implementation requirement; do not defer mobile adaptation to a final cleanup phase.

---

# 30. Git Rules

All UI work must remain on:

`feat/enhanced-ui`

Before significant changes:

```bash
git status