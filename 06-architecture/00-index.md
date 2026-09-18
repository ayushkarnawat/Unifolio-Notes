# Architecture Index

Sections are created only once there's real content for them — this
list grows as batches are ingested, it does not start pre-filled.

| Section | What it covers |
|---|---|
| [Goals and context](goals-and-context.md) | What Unifolio is, who it serves, the business constraints the architecture answers to |
| [Building blocks](building-blocks.md) | The components — SPA, four logical backend services, background jobs, two data stores, five external sources |
| [Frontend composition](frontend-composition.md) | How the SPA is actually put together — feature boundaries, why there is no router, and the rules that hold across every flow |
| [Runtime and data flow](runtime-and-data-flow.md) | How a CAS import, a dashboard load, and a scheduled refresh actually run |
| [Data model](data-model.md) | The five design principles behind the schema and what each entity is for |
| [Deployment](deployment.md) | Where each piece runs in AWS |
| [Quality and constraints](quality-and-constraints.md) | Non-functional targets, security posture, hard rules the code must not break |
| [Glossary](glossary.md) | CAS, RTA, ARN, TER, AAUM, XIRR, Direct vs Regular, and the rest |

Decisions behind these sections live in [`03-decisions/`](../03-decisions/) —
ADR-001 through ADR-007 cover the stack and data handling, ADR-008 through
ADR-011 cover identity, email delivery, the fund score, and how the project
delegates implementation work between models. This section describes what
*is*; the ADRs explain *why*.
