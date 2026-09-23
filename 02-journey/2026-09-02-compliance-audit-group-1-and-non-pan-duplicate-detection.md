# A first group of compliance-audit findings is fixed, and a non-PAN duplicate-person-detection design is built in two rounds

## For stakeholders

A batch of smaller correctness and data-integrity issues, found during an
internal compliance review, was worked through and closed out — a missing
uniqueness rule that could let two "primary" household records exist for
the same person, a background-job wiring gap, a schema-documentation
refresh, and a slow-query fix. Separately, and more substantively, a design
was built for spotting when the same real person might have created two
household records without using PAN (an Indian tax ID) as the matching
signal, since the product does not store PAN today — the previous session's
idea of matching people by PAN was explicitly rejected on that basis and
replaced with a same-user/cross-user distinction using only data the
product already keeps.

## Technical detail

### Intended outcome

Work through a first group of items from an internal compliance audit
("Group 1": F3, F5, F6, F7, F9, F10) and close the still-open design
question around detecting duplicate-person household records without a PAN
field.

### What actually happened

- **F7 — `compute_holdings`'s per-folio N+1 query pattern, fixed.**
  Discovered as a side effect of the 2026-08-21 distributor-comparison
  rewrite and confirmed pre-existing at the time, explicitly out of scope
  for that change. Fixed here: one batched `Transaction` query across all
  folios, grouped by folio in application code to preserve the per-folio
  chronological order the FIFO lot processor requires. 42 targeted tests
  plus the full backend suite pass unchanged. This resolves the item
  tracked as [R-040](../07-risks-and-debt.md).
- **F9 — a background-job wiring gap fixed.** `amfi_aaum_client.py`'s
  `refresh_aaum_data` had no caller anywhere in the codebase; wired into a
  real entrypoint as part of the ADR-006 job-scripts handoff.
- **F5 — the internal schema-reference document refreshed** to reflect the
  current migration chain.
- **F6, F10 — smaller correctness/cosmetic items** (Postgres `ON CONFLICT`
  test coverage; a JSONB migration alignment fix).
- **F8 — a held scheme with no obtainable NAV silently vanishing from
  holdings/allocation/aggregates, resolved.** Replaced with a degraded row
  plus a `nav_unavailable` flag, so the holding still appears with an
  explicit "unavailable" marker instead of disappearing. Went through two
  review rounds before being accepted.
- **F3 — no database-level uniqueness constraint on the "self"
  `household_members` row, resolved.** Migration `0011` adds a partial
  unique index enforcing at most one "self" row per user; a
  `DuplicateSelfMemberError` mapped to a 409 response guards the
  application-level path. Zero pre-existing violations were found when the
  constraint was added.
- **Non-PAN duplicate-person detection, designed and built in two
  rounds.** A prior session had proposed matching people across households
  by PAN; this was rejected because the product does not persist PAN
  (`tests/models/test_no_pan_field.py` enforces this), and no new PII is
  introduced to work around that. The chosen design instead distinguishes
  two cases using data the product already keeps: a **same-user**
  cross-household signal (folio-number match as the primary signal, a
  weaker name-match as a secondary one — never leaking the other
  account's identity) and a separate, advisory-only **cross-user**
  duplicate check. Round 1 designed it; round 2 (2026-09-03) wired it into
  the actual production import paths — a shared confirmation gate added at
  all three backend commit sites, a structured 409 response, and a
  desktop/mobile "Switch" vs. "Continue anyway" confirmation UI. This
  wiring surfaced a separate architectural finding: two parallel import
  backends had independently drifted to need the identical fix wired in
  twice — recorded as its own open item, not fixed as part of this pass,
  tracked as [R-059](../07-risks-and-debt.md).
  An adversarial review round returned a bare pass whose own test-execution
  claim was independently re-verified rather than trusted at face value
  (the reviewer's own sandbox lacked the dependency needed to actually run
  the tests it claimed to have run); the three highest-risk points were
  independently re-checked directly against the code, and both full test
  suites were independently rerun (614 backend/1 skipped, 397 frontend/75
  files), matching the implementer's self-report exactly.

### Deviation (if any) — decision or response taken

The prior session's PAN-based duplicate-detection idea was explicitly
rejected in favour of the non-PAN design above — a deliberate course
correction, not a silent substitution.

### Result

Six compliance-audit findings closed (F3, F5, F6, F7, F9, F10), one design
built and wired into production in two rounds (non-PAN duplicate
detection), and one standalone architectural gap (two parallel import
backends needing the same fix twice) surfaced and flagged, not fixed.

### Related

- R-040 — `compute_holdings` N+1 (resolved by this stage — see the dated
  note appended there)
- R-043 — the open PAN question (this stage does not resolve it; it
  demonstrates a real feature built specifically to avoid needing PAN)
- ADR-006 — background job scheduling (F9's wiring is part of that
  handoff)
- Evidence: `08-evidence/documents/engineering-loop/session.md` (2026-09-02
  section and the "Still open" carry-forward list), `08-evidence/documents/engineering-loop/CLAUDE.md`

## Addendum — 2026-09-23 (from batch 4a orchestration ingestion)

Two more same-day (2026-09-02), same-audit-cycle items are evidenced by
later-ingested delegation material, both completed the same day as the
items above and not previously recorded in this vault:

**Six staging-code blockers fixed** (scoped from
`AWS Readiness/aws-golive-launch-blockers.md`, status COMPLETE 2026-09-02):
CORS origins moved from a hardcoded localhost list to an `ALLOWED_ORIGINS`
env var (falling back to the old localhost list when unset, so local dev
is unaffected); the container's uvicorn entrypoint set to bind `0.0.0.0`
(the local-dev launcher `run_server.py`, including its Windows-only
Playwright/`ProactorEventLoop` handling, was deliberately left untouched
— container boot bypasses it entirely); `POST /imports/parse` gained the
same file-size-cap-plus-PDF-magic-byte validation its sibling
`POST /cas-imports` route already had; the OTP stub-mode guard was changed
from inferring safety off the DB dialect (SQLite vs. Postgres) to an
explicit `ENVIRONMENT` flag, so staging (Postgres, `environment="staging"`)
can run stub-mode OTP without tripping a guard meant for production — a
deliberate, already-approved decision, not relitigated here; a Dockerfile
was written for the first time (`playwright install --with-deps chromium`
included, since `app/main.py`'s lifespan handler launches Chromium
unconditionally on boot); and backend dependencies were pinned to a
lockfile with the dead `passlib` dependency removed. All five/six changes
together unblocked building and deploying the backend container at all —
none had existed before this date. Full 578-test backend suite stayed
green.

**Migration `0010` — two Postgres ENUM types widened to match drifted
Python model enums** (status DONE, verified against local Docker Postgres
16, 2026-09-02): `importstatus` was missing 11 of 14 values the live
`ImportStatus` Python enum already had, and `transactiontype` was missing
1 of 12 (`opening_balance`) — both widened additively
(`ALTER TYPE ... ADD VALUE`, no data migration, since nothing could yet
have written the missing values). This is the same migration chain later
found to have a numbering gap; see the dated resolution note appended to
[R-050](../07-risks-and-debt.md) and the
[2026-08-21 entry](2026-08-21-post-merge-migration-head-collision-and-windows-playwright-crash.md)
covering how migration `0009` was renumbered — migration `0010` (this
item) is the enum-widening change, distinct from the demat-import plans'
own unbuilt, never-executed "migration 0010" naming (see R-051), which is
a coincidental collision in a planning document, not evidence of two real
migrations sharing one revision number.

Evidence: `08-evidence/documents/orchestration/staging-code-blockers-handoff.md`,
`08-evidence/documents/orchestration/enum-drift-migration-handoff.md`
