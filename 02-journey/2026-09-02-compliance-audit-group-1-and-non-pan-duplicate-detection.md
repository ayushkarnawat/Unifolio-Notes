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

## Addendum — 2026-09-23 (from batch 4c orchestration ingestion): F8's review detail and the two-parallel-backends git archaeology

**F8 went through three review rounds, not two.** The entry above
undercounted this. The source handoff
(`f8-nav-unavailable-degraded-row-handoff.md`, Status DONE, 2026-09-03)
records: round 1 (FAIL, 2 P1s — "Total Invested" wrongly excluded a
degraded holding's known FIFO principal from the total, and
`nav_unavailable_count` was computed but never actually surfaced in the
UI; both fixed in `DashboardView.tsx`/`MobileDashboardView.tsx`); round 2
(FAIL, 1 P1 — `gainPercentage` divided the valued-only profit by *all*
holdings' invested amount including degraded ones, mixing two incompatible
populations; fixed by introducing a separate `valuedInvestedVal`); round 2
re-review (PASS, zero findings). That closing re-review was performed by
the orchestrator directly rather than dispatched to the usual reviewer,
because Codex had hit its own usage limit mid-dispatch — an explicit,
one-time deviation from the default "Codex reviews, orchestrator
implements" split, done on explicit user instruction for that specific
occasion, not a standing process change.

A related, explicitly out-of-scope sibling bug was flagged rather than
silently fixed or silently ignored: `distributor_comparison.py` has the
same no-NAV `continue`-drops-the-row defect that F8 fixed elsewhere, left
untouched as a named follow-up.

**The two-parallel-import-backends gap's git archaeology**, establishing
exactly how and when the split arose (from
`two-parallel-import-backends-architectural-gap.md`, confirmed via
`git log --diff-filter=A` per file):

| Commit | Date | What it added |
|---|---|---|
| `5c81231` / `1e823d1` | 2026-08-04 | `service.py` / `app/api/imports.py` — the production parse-preview + confirm path |
| `038342a` | 2026-08-05 | `ImportFlow.tsx` wired to `/imports/*` (the live, exercised frontend) |
| `4d60c8e` | 2026-08-10 | `lifecycle_service.py` + `cas_imports.py` + `attribution.py` (the newer, more capable backend rewrite) |
| `e7db4c1` | 2026-08-10, same day | `ImportLifecycleView.tsx` (its intended frontend) |

The cutover from `ImportFlow.tsx`/`/imports/*` to
`ImportLifecycleView.tsx`/`/cas-imports/*` was started but never
completed — `ImportFlow.tsx` was never repointed, and
`ImportLifecycleView.tsx` was never mounted into any route or parent
component (referenced only by its own test file). The two backends then
drifted apart, undetected, for roughly 3.5 weeks (2026-08-10 to
2026-09-03) — `/imports/*` because it is what real users and every
manual/localhost test actually exercise, `/cas-imports/*` because nothing
called it, so it could not fail visibly. It took the non-PAN dedup task's
own mandatory adversarial-review gate — one that checked the actual
production call chain rather than trusting the task's stated scope — to
surface it on 2026-09-03.

**Why this wasn't caught earlier**, per the source material's own stated
process lesson: no integration test exercises the actual route-to-frontend
wiring (existing tests hit either backend or either frontend directly,
never end-to-end through "which component does the app actually render");
and the original non-PAN dedup handoff doc (written by the orchestrator)
named `lifecycle_service.py` as the target without first confirming it was
the production path — an assumption stated as fact rather than verified.
Named explicitly as a process gap in how handoff docs get written, not
just a one-off mistake: a handoff doc that names a specific file as "the"
implementation target should state how that was confirmed (a grep for the
frontend call site, or a route/`main.py` mount check).

**Resolution, already summarized above, restated for cross-reference**:
user decision 2026-09-03 was option (a) — wire the dedup/confirmation-gate
logic into `service.py`/`/imports/*` (the live production path), and also
route `lifecycle_service.py`'s two call sites through the same shared
`enforce_attribution_confirmation` helper (Ponytail's "fix once, where all
callers route through" doctrine, cited by that name in the source
material) rather than leaving the same invariant violated twice. See the
dated update appended to [R-059](../07-risks-and-debt.md) for this
addendum's corresponding risk-entry status change.

### Addendum evidence

- `08-evidence/documents/orchestration/f8-nav-unavailable-degraded-row-handoff.md`
- `08-evidence/documents/orchestration/two-parallel-import-backends-architectural-gap.md`
- `08-evidence/documents/orchestration/non-pan-duplicate-person-detection-handoff.md`
