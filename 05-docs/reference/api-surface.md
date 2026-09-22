# Reference: API Surface

Representative, not exhaustive. The full OpenAPI spec is an implementation artifact in
the code repo. This exists to confirm that every PRD requirement has an endpoint home.

## Auth

| Endpoint | Method | Source |
|---|---|---|
| `/auth/otp/request` | POST | PRD-02 FR-2 — accepts a phone number or, since 2026-08-14, an email address |
| `/auth/otp/verify` | POST | PRD-02 FR-2 — returns one of three outcomes: session created, phone required, or link required |
| `/auth/google/verify` | POST | ADR-008 — verifies a Google ID token; same three-way outcome |
| `/auth/pending/{id}/phone` | POST | ADR-008 — completes the mandatory phone step for a pending verification |
| `/auth/pending/{id}/link` | POST | ADR-008 — step-up re-authentication, then links the new identity |
| `/onboarding` | PATCH | PRD-02 — onboarding field updates on the acting user, resolved from the session |

**There is deliberately no `GET /auth/me`.** It was considered on 2026-08-05
and not added, because it was not in the approved design. Recorded because
the restraint is the point, not because the route is missing by oversight.

**No IDOR by construction:** every onboarding and household-member write
resolves the acting user from the session token via a shared dependency,
never from a request body or query parameter.

The following were added on 2026-08-17 and **removed again the same day** when
the email-and-password decision was reversed; password storage was dropped by
migrations `0007`–`0008`. Listed because they were built, not because they
exist: `POST /auth/signup/email`, `POST /auth/login/email`,
`POST /auth/password/forgot`, `POST /auth/password/reset`,
`POST /auth/email/confirm`. Behavioural rules that were specified with them and
are worth carrying forward if password auth ever returns: reset requests always
answer 200 regardless of whether the address exists; failed logins answer a
generic 401; and "correct password, email unconfirmed" answers a distinct 403.

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
| `/household-members` | GET/POST | PRD-02 FR-5. **No PATCH exists** — callers resolve the `self` row list-then-create |
| `/household-members/{id}/holdings` | GET | PRD-03 FR-1–FR-3 — FIFO cost basis |
| `/household-members/{id}/allocation` | GET | Coarse view: `by_asset_class` / `by_amc` |
| `/household-members/{id}/sips` | GET | PRD-03 — active-SIP detection, 40-day window |
| `/household-members/{id}/cash-flow` | GET | PRD-03 FR-7 — switch transactions excluded |
| `/household-members/{id}/snapshots` | GET | PRD-03 FR-8 |
| `/household-members/{id}/distributor-comparison` | GET | PRD-03 FR-11 — **as implemented 2026-08-07**. Contested; see below |
| `/funds/{scheme_id}/distributor-comparison` | GET | PRD-03 FR-11 — the TDD's shape, recorded in this file since batch 1 |
| `/household/aggregate` | GET | PRD-03 FR-9 — the default landing view |

**Two shapes are recorded for distributor comparison, and only one can be
right.** The TDD's fund-global route is what this reference has carried since
batch 1. The 2026-08-07 design corrected it to sit under the household
member, on the reasoning that "your returns by distributor" is meaningless
without knowing whose returns — and that is what was built. Both rows are
left here rather than one being deleted. See
[R-017](../../07-risks-and-debt.md) — unresolved.

**Family-aggregate response shape, uniformly:** aggregate responses wrap a
per-member status list, so a member with no data is returned as
present-but-empty rather than silently dropped. Every compute function behind
these routes takes a list of member IDs, so the per-member and aggregate
paths are one implementation.

**Planned, not built (ADR-012, 2026-08-18):**

| Route | Returns |
|---|---|
| `GET /household-members/{member_id}/sips/monthly` | Expected SIP contributions for a given month for one member, projected from each plan's own cadence |
| `GET /household/aggregate/sips/monthly` | The same, aggregated across the household |

**Planned, not built (2026-08-20):** the fund-scoped distributor-comparison
route is to be **deleted, not deprecated**, and replaced by a portfolio-level
computation over a member-id list returning per-distributor rows each carrying
a per-scheme breakdown. One behavioural change comes with it: a scheme with no
available NAV is dropped from that distributor's breakdown only, rather than
causing the whole response to be dropped. The implementation plan was never
started and ends on an unanswered design question.

## Analytics

**Superseded 2026-09-02 (ADR-015).** The seven per-section routes below were
the live-compute-on-read design through batch 2b, and are historically
accurate for that period. As of the analytics precompute rework, they are
replaced by one consolidated read route and one retry route, both reading
from the new `analytics_sections` table rather than computing on request:

| Endpoint | Method | Source |
|---|---|---|
| `/analytics/{scope}` | GET | Consolidated read across all analytics sections for one scope (household member or aggregate), from precomputed, persisted rows. [ADR-015](../../03-decisions/ADR-015-analytics-precompute-architecture.md) — **built, merged 2026-09-10** |
| `/analytics/{scope}/retry` | POST | Re-dispatches recomputation for a scope via ECS Fargate `RunTask`, for a section stuck in a failed/stale state. [ADR-015](../../03-decisions/ADR-015-analytics-precompute-architecture.md) — **built, merged 2026-09-10** |

The routes below are the pre-2026-09-02 shape, kept for historical accuracy
(and because the underlying computations — allocation, category rank,
score, benchmark comparison — still exist, just behind the consolidated
route now):

| Endpoint | Method | Source |
|---|---|---|
| `/analytics/household-members/{id}/allocation` | GET | PRD-04 FR-1–FR-2 — granular `by_category` plus re-exposed `by_amc`. **Built 2026-08-10, superseded 2026-09-02** |
| `/analytics/household/aggregate/allocation` | GET | PRD-04 FR-1–FR-2, family aggregate. Built 2026-08-10, superseded 2026-09-02 |
| `/funds/{scheme_id}/category-rank` | GET | PRD-04 FR-3–FR-4 |
| `/funds/{scheme_id}/score` | GET | PRD-04 FR-5–FR-7 — three-ingredient composite, **built 2026-08-13**. Formula in [ADR-010](../../03-decisions/ADR-010-fund-scorer-composite-formula.md); the FR-7 breakdown was recomputed on read and never persisted through batch 2b — as of ADR-015 it is persisted in `analytics_sections` |
| `/household-members/{id}/benchmark-comparison` | GET | PRD-04 FR-8–FR-9 |

**On the two `/allocation` routes:** the Dashboard's coarse
`/household-members/{id}/allocation` and the Analytics service's granular
`/analytics/household-members/{id}/allocation` are **intentionally separate**, on distinct
prefixes, serving different granularities. This is documented explicitly in the TDD
because it looks like a route collision and is not one.

Confirmed by implementation on 2026-08-06 and 2026-08-10. One further
correction: the TDD's API table listed the **coarse** allocation endpoint
under the Analytics service. Phase 3 recorded that as a documentation slip
and placed it in Dashboard, where the holdings engine it depends on already
lives. The Analytics service re-exposes the coarse `by_amc` view inside its
own response rather than recomputing it, so the analytics tab is one request
over one holdings computation.

**Planned, not built (ADR-013, 2026-08-20):**

| Route | Auth | Returns |
|---|---|---|
| `POST /analytics/export/pdf` | Session bearer token | A rendered PDF of the analytics dashboard, produced by a server-side headless browser |
| `GET /analytics/export/payload` | **Capability token in the query string — deliberately no current-user dependency** | The export payload for one issued token |

The second route's lack of a user dependency is a design decision, not an
oversight: the token is a capability, not a credential. The token store is
in-process and does not survive a restart or a multi-worker deployment (R-039).

## Demat and equities — planned, not built (ADR-014, 2026-08-26)

A pipeline parallel to CAS import, not an extension of it. The existing
`/cas-imports` lifecycle is untouched and continues to reject demat statements.

| Route | Purpose |
|---|---|
| `POST /demat-imports/parse` | Parse an uploaded depository statement into a reviewable set of holdings |
| `POST /demat-imports/confirm` | Commit a reviewed parse to the member's holdings |
| `GET /household-members/{member_id}/equity-holdings` | Equity holdings for one member |

No household-level aggregate equity endpoint exists in this cut, so equities
are member-view only (R-045).

## Related

- [Building blocks](../../06-architecture/building-blocks.md)
- [Runtime and data flow](../../06-architecture/runtime-and-data-flow.md)
