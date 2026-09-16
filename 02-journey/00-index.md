# Journey Index

Ordered list of delivery stages. Each links to a `<date>-<stage>.md`
file with the full for-stakeholders/technical-detail record.

_No stages recorded yet — populated as batches 1-2 are ingested._

```mermaid
flowchart LR
    A[A — Initial state] --> B[Planned path]
    B --> C{Blocker or discovery?}
    C -->|No| D[B — Final state]
    C -->|Yes| E[Decision]
    E --> F[Alternative implemented]
    F --> D
```
