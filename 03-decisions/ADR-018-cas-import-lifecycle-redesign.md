# ADR-018: CAS import rebuilt around an 11-state lifecycle, coverage-gap detection, and opening-balance resolution

Status: Accepted — built and merged; passes the full test suite; **not yet independently reviewed by Claude Code against this vault's non-negotiables**
Date: 2026-08-1X (exact build date imprecise in source material; discovered and reconciled into shared history 2026-08-14)
Related: [2026-08-14 journey stage — CAS import lifecycle and branch reconciliation](../02-journey/2026-08-14-cas-import-lifecycle-and-branch-reconciliation.md); [ADR-004](ADR-004-object-storage-scope-and-cas-pdf-retention.md) (no raw CAS PDF persistence); [R-004](../07-risks-and-debt.md)

## For stakeholders

The original CAS import flow only handled the simple case: one statement,
fully covering a folio's history, parsed once. Real usage surfaces harder
cases — a statement that only covers part of a folio's history, a user who
needs to tell the system what a folio's opening balance was before the gap,
a household member the imported data needs to be attributed to, and a path
for requesting a fresh statement from CAMS by email when the user doesn't
have one handy. An intern-authored rework, built independently of the main
Claude-Code-led workstream, adds all of this as an explicit state machine
with defined legal transitions, so an import's status is always one of a
known set of states rather than an implicit combination of flags. It passes
every automated test. It has not yet had the same independent review pass
against this project's own rules (no raw PDF storage, no PAN persistence,
`Decimal`-never-`float`, TDD) that every Claude-Code-led feature gets before
being considered done — that gap is the main thing this record exists to
flag, not to paper over.

## Technical detail

### Context

The vault has carried an open risk (R-004) since batch 2b: two
unreconciled generations of the CAS import flow, one described in earlier
PRD/spec material and one implied by later evidence, with no document
bridging them. `CAS-IMPORT-UPDATE-PLAN.md` (the planning document behind
this work) is that bridge — a gap-analysis (FR-1 through FR-9) against the
existing flow, an 11-state transition table, a data-model change list, and
an explicit "Conflicts, Ambiguities & Proposed Resolutions" section working
through exactly the tensions this vault had flagged as unresolved.

The implementation was authored by a different contributor
(`aditishanbhag`) on a separate branch that had drifted from the main
Claude-Code-led branch (`feat/enhanced-ui`) since roughly 2026-08-13. It
surfaced when the two branches were reconciled on 2026-08-14 — not
discovered through the normal handoff/plan/review cycle used elsewhere in
this project.

### Decision drivers

- R-004's two-generations gap needed resolving with a real design, not
  another workaround.
- A statement that doesn't cover a folio's full history needs an explicit
  representation — silently importing a partial history as if it were
  complete would misstate holdings.
- ADR-004's zero-raw-PDF-persistence rule and a "let the user retry with
  the right password" flow are in direct tension — a password retry needs
  the bytes somewhere, but nothing may be written to durable storage.
- The existing async import work needed to stay compatible with the two
  already-shipped endpoints (`/imports/parse`, `/imports/confirm`) and
  their 156 existing tests — a breaking rewrite was not acceptable.
- Folio-to-household-member attribution must never rely on PAN, per
  ADR-004/ADR-007's no-PAN-persisted-today constraint.

### Options considered (from the plan's own conflicts/resolutions table)

#### Password retry vs. zero raw-PDF persistence
- **Option A — persist encrypted CAS bytes until confirmed.** Simplest to
  implement. Rejected: directly contradicts ADR-004.
- **Option B — 15-minute TTL encrypted in-memory buffer, purged after use,
  410 Gone once expired (chosen).** Lets a user retry a wrong password
  without re-uploading, without ever writing the PDF to disk or S3.

#### Processing model
- **Option A — dedicated async job queue.** More scalable, but a new piece
  of infrastructure this monolith doesn't otherwise have.
- **Option B — FastAPI `BackgroundTasks`, 202 Accepted + client polling
  (chosen).** Matches the existing single-process-monolith shape; no new
  infrastructure.

#### Attribution vs. the no-PAN rule
- **Option A — match imported folios to household members by PAN.**
  Rejected outright: no PAN field exists in the schema
  (`tests/models/test_no_pan_field.py` enforces this), and this would
  reopen the exact question R-043 is already tracking unresolved.
- **Option B — match on name/email only, never persist plaintext PAN
  (chosen).** Weaker matching signal, accepted as the cost of the
  no-PAN-today constraint.

#### Compatibility with the existing sync endpoints
- **Option A — replace `/imports/parse`/`/imports/confirm` outright.**
  Rejected: breaks existing frontend callers and their test coverage with
  no migration path.
- **Option B — keep them as sync wrappers around the new lifecycle
  service, zero regression on the existing 156 tests (chosen).**

### Decision

Adopt the 11-state import lifecycle as designed and built:

1. A new `state_machine.py` enforces legal state transitions per the
   plan's FR-5 table; a new `OPENING_BALANCE` transaction type and
   Alembic migration `0003` (`Import`/`Folio` schema changes) support it.
2. A 15-minute TTL encrypted in-memory buffer holds CAS bytes only long
   enough for a password retry, never durable storage.
3. Coverage-gap detection flags a folio whose imported history doesn't
   reach back far enough, and an opening-balance resolution flow lets the
   user supply a starting point instead of an inferred one.
4. A CAMS-portal mailback URL generator and a pending-request lifecycle
   support "request my statement from CAMS by email, wait for it" as a
   first-class path, not a dead end.
5. `/imports/parse` and `/imports/confirm` remain as sync wrappers,
   unchanged in behaviour for existing callers.
6. Attribution matches on name/email; no PAN field is read, stored, or
   compared anywhere in this feature.

### Consequences

Positive:
- R-004's two-generations gap is resolved with a concrete bridging design,
  not left open.
- Coverage gaps and opening balances — previously silent failure modes —
  are now explicit, user-facing states.
- Zero regression on the 156 existing `/imports/parse`/`/imports/confirm`
  tests; the whole test suite passes with this feature included.
- No new tension with ADR-004 (no raw PDF persistence) or the current
  no-PAN-persisted position.

Negative / open:
- **This is the single largest piece of state-machine and
  money-adjacent logic (opening balances, coverage gaps) in the codebase
  to land without the independent Claude Code review pass every other
  feature of this size gets before being called done.** "Passes the full
  test suite" and "independently reviewed against this project's
  non-negotiables" are explicitly different claims in the source material
  itself — this ADR preserves that distinction rather than treating a
  green test suite as equivalent to review.
- Built on a branch that had silently diverged from the main workstream
  for roughly a day before being caught at reconciliation — a process gap
  worth naming even though the reconciliation itself went cleanly (see the
  journey entry for the reconciliation detail).

### Validation

Automated: full backend suite passes with this feature included (see the
journey entry for the exact commit range). **Not validated:** an
independent review pass against this vault's non-negotiables
(`Decimal`-never-`float`, no raw PDF persistence, no PAN persistence, TDD
discipline) of the kind every Claude-Code-authored feature in this vault
otherwise receives before being marked built-and-reviewed.

### Evidence

- Plan/architecture doc: `08-evidence/documents/engineering-loop/CAS-IMPORT-UPDATE-PLAN.md`
- Corroborating changelog entries: `08-evidence/documents/engineering-loop/backend.md`, `08-evidence/documents/engineering-loop/database.md`, `08-evidence/documents/engineering-loop/log.md`
- Narrative: `08-evidence/documents/engineering-loop/session.md`, "Branch reconciliation — final check..." section
