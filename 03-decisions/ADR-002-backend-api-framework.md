# ADR-002: Backend API framework — keep FastAPI, do not migrate to Django

Status: Accepted
Date: 2026-07-22
Related: ADR-003 (database), ADR-005 (where it runs), `06-architecture/building-blocks.md`

## For stakeholders

The backend that reads a statement, does the money maths, and serves the dashboards was
already substantially built on FastAPI. A proposal came in to rebuild it on Django,
mainly for Django's free built-in admin panel — a ready-made internal tool for looking
up a user's data when supporting them. We kept FastAPI. The work already done is real
and tested, the product is an API consumed by a React app rather than a set of
server-rendered pages, and the work it does is mostly waiting on external services,
which is the shape FastAPI is strongest at. This was a closer call than the frontend
one, and it is recorded as such: the cost is that we will assemble admin tooling,
auth plumbing, and background jobs ourselves rather than getting them free. If an
internal-ops tool becomes genuinely necessary, the agreed answer is a small separate
Django admin app alongside — not a migration of the production API.

## Technical detail

### Context

The backend is already substantially built on FastAPI: the scaffold, `calc.py`
(Decimal-safe money maths), SQLAlchemy models, the `casparser` wrapper, `mfapi.in` NAV
enrichment, and the two-phase parse/confirm API routes are all complete per the build
tracker. Only the frontend Import Review screen and the README remained at the time of
this decision.

The proposal on the table was Django, implicitly with Django REST Framework, since the
product is API-first rather than template-rendered.

Shape-wise, Unifolio's backend is a pure API service — no server-rendered HTML, no need
for a template engine — consumed by a React SPA, doing async-friendly I/O-bound work:
CAS parsing, calls to `mfapi.in`, and (per ADR-003/ADR-004) calls to RDS and S3.

### Decision drivers

- Substantial, working, tested backend code already exists; the binding constraint at
  the time was shipping by mid-August without discarding it.
- The workload is I/O-bound and API-first, not template-rendered.
- The team is too small for "framework conventions keep many engineers consistent" to
  be the binding constraint.
- Django's admin panel is a genuine, named want — not dismissed, but weighed.

### Options considered

#### Option 1: Continue with FastAPI (chosen)
**Advantages:** no rework of completed, tested logic — the largest sunk-cost
consideration in the whole ADR set, and a real one against the ship date; the async
model fits I/O-bound calls to `mfapi.in`, RDS, and S3, which current guidance
specifically flags as FastAPI's strength; lighter operational footprint — no admin app,
no template engine, no second ORM layer carried along unused.
**Disadvantages:** forgoes Django's batteries — admin panel, auth scaffolding, DRF's
opinionated conventions; more pieces to assemble individually (auth, background jobs,
admin tooling).

#### Option 2: Django / Django REST Framework
**Advantages:** batteries-included — a free internal ops/support tool via the admin
panel, built-in auth scaffolding, conventions that keep a growing team consistent.
**Disadvantages:** no templated pages exist in scope; adopting it means discarding
working code for benefits that are not yet binding. 2026 guidance consistently frames
the choice as "MVP speed → Django, API-first/async-heavy → FastAPI" — and this MVP's
API-first backend is already built.

#### Option 3: Hybrid — FastAPI for the core API, Django for a future admin tool
**Advantages:** gets the admin-panel convenience without touching the production API.
**Disadvantages:** none identified; it is simply not needed yet.
**Not rejected** — explicitly retained as the answer if internal tooling need appears.

### Decision

Continue with **FastAPI**. Do not migrate to Django. The already-built parser, models,
and API routes stay as they are; RDS and S3 integration (ADR-003, ADR-004) is added on
top of the existing service rather than as part of a framework migration.

### Consequences

**Positive:**
- No rework of completed, tested backend logic.
- Async model matches the actual workload shape.
- Lighter operational footprint.

**Negative:**
- No free admin panel for internal ops/support lookups.
- Auth, background jobs, and admin tooling must be assembled individually — a real cost
  if internal tooling needs grow faster than expected.

**Neutral:**
- A small separate internal Django or Django-admin-style tool remains available later,
  for support/debugging dashboards only, without migrating the user-facing API. This is
  the intended response to an admin-tooling need — not reopening this decision.

### Validation

Validated if internal support requests can be handled without an admin panel through
MVP. The revisit trigger is named and specific: internal ops tooling becoming a
recurring time sink — and the response is Option 3, not a migration.

### Evidence

- Source document: `08-evidence/documents/ADR-Technical-Stack-Decisions.md` (ADR-002)
- Referenced but not held in this vault: `MF_CAS_Parsers.md` build-status tracker.
