# Journey Index

Ordered list of delivery stages. Each links to a `<date>-<stage>.md`
file with the full for-stakeholders/technical-detail record.

| Date | Stage | Outcome |
|---|---|---|
| 2026-07-22 → 2026-09-02 | [Product and architecture definition](2026-07-22-product-and-architecture-definition.md) | Build-ready spec set, six Accepted ADRs, schema reconciled to migration 0011. Three course corrections: deployment platform, auth method, schema drift |

_Later stages populate as batches 2-6 are ingested — implementation work
(`Docs/superpowers/plans/`) is batch 2 and is not yet recorded here._

```mermaid
flowchart LR
    A["Product idea:\nMF portfolio tracker"] --> B["Spec set:\n4 PRDs, TDD, schema,\napp flow, design system"]
    B --> C{"Formalising the\nstack surfaced\nproblems?"}
    C -->|"App Runner closed\nto new customers"| D["ADR-005:\nECS Express Mode"]
    C -->|"Auth reversed twice\n2026-08-17"| E["Passwordless throughout;\npassword tables dropped\n(migrations 0007-0008)"]
    C -->|"Schema doc 3-4\nmigrations stale"| F["Compliance audit;\nschema v1.4 then v1.5"]
    D --> G["Six ADRs Accepted;\nspec build-ready"]
    E --> G
    F --> G
    G --> H["Open conflicts carried\nforward, not papered over\n(07-risks-and-debt)"]
```
