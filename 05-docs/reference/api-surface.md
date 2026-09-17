# Reference: API Surface

Representative, not exhaustive. The full OpenAPI spec is an implementation artifact in
the code repo. This exists to confirm that every PRD requirement has an endpoint home.

## Auth

| Endpoint | Method | Source |
|---|---|---|
| `/auth/otp/request` | POST | PRD-02 FR-2 |
| `/auth/otp/verify` | POST | PRD-02 FR-2 — creates a session |

## Import — two-phase parse/confirm (TDD generation)

| Endpoint | Method | Source |
|---|---|---|
| `/imports` | POST | PRD-01 — upload |
| `/imports/{id}/parse` | POST | PRD-01 FR-9 — preview, **no database write** |
| `/imports/{id}/confirm` | POST | PRD-01 FR-9–FR-11 — the only write path |

## Import — queue-driven (Updated-CAS generation)

`Updated-CAS-App-Flow.md` specifies a different, newer set for the server-backed queue
model. **These two sets are not reconciled with each other** — see
[`07-risks-and-debt.md`](../../07-risks-and-debt.md).

| Endpoint | Method | Purpose |
|---|---|---|
| `/cas-imports/pending` | POST | Record a "requested from CAMS" pending state |
| `/cas-imports` | POST | Submit a file |
| `/cas-imports/{id}/password` | PATCH | Resubmit a password **without re-uploading the file** |
| `/cas-imports/{id}` | GET | Poll import state |
| `/cas-imports/{id}/attribution` | PATCH | Assign or reassign an import to a household member |
| `/family-members/{id}/cas-imports` | GET | Imports for one member |
| `/family-members/{id}/coverage-gaps` | GET | Periods not covered by any statement |
| `/folios/{id}/opening-balance` | POST | Supply an opening balance where history is missing |

**Naming conflict:** this set says `family-members`, the TDD set says `household-members`,
and the schema table is `household_members`. Flagged, not resolved.

## Dashboard

| Endpoint | Method | Source |
|---|---|---|
| `/household-members` | GET/POST | PRD-02 FR-5 |
| `/household-members/{id}/holdings` | GET | PRD-03 FR-1–FR-3 |
| `/household-members/{id}/cash-flow` | GET | PRD-03 FR-7 |
| `/household-members/{id}/snapshots` | GET | PRD-03 FR-8 |
| `/household/aggregate` | GET | PRD-03 FR-9 — the default landing view |
| `/funds/{scheme_id}/distributor-comparison` | GET | PRD-03 FR-11 |
| `/household-members/{id}/allocation` | GET | Pre-existing coarse view: `by_asset_class` / `by_amc` |

## Analytics

| Endpoint | Method | Source |
|---|---|---|
| `/analytics/household-members/{id}/allocation` | GET | PRD-04 FR-1–FR-2 — granular `by_category` plus re-exposed `by_amc`. **Built 2026-08-10** |
| `/analytics/household/aggregate/allocation` | GET | PRD-04 FR-1–FR-2, family aggregate. Built 2026-08-10 |
| `/funds/{scheme_id}/category-rank` | GET | PRD-04 FR-3–FR-4 |
| `/funds/{scheme_id}/score` | GET | PRD-04 FR-5–FR-7 |
| `/household-members/{id}/benchmark-comparison` | GET | PRD-04 FR-8–FR-9 |

**On the two `/allocation` routes:** the Dashboard's coarse
`/household-members/{id}/allocation` and the Analytics service's granular
`/analytics/household-members/{id}/allocation` are **intentionally separate**, on distinct
prefixes, serving different granularities. This is documented explicitly in the TDD
because it looks like a route collision and is not one.

## Related

- [Building blocks](../../06-architecture/building-blocks.md)
- [Runtime and data flow](../../06-architecture/runtime-and-data-flow.md)
