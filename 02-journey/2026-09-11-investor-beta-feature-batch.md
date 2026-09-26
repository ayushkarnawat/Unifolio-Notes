# A 10-item investor-requested feature batch is built, reviewed twice, and left open

## For stakeholders

An investor asked for 10 specific product changes ahead of a same-day
staging demo, inserted out-of-band ahead of the existing staging-push plan.
The batch covers a new Profile page (account info, email/phone change,
theme toggle, import history with delete, a "Danger Zone" for account
deletion with an exit survey and a 5-day undo grace period, including a
whole-household cascade when the deleted account is the household's
primary member), a real portfolio-return (XIRR) number on the dashboard
header replacing a plainer metric, several smaller UI fixes (a gain/loss
label that reads correctly for both directions, sortable allocation
breakdowns, drill-down detail views, and consistent two-decimal-place
number formatting). All 10 items were built and passed both automated test
suites, but this project runs a mandatory second-pair-of-eyes review on
every batch of work before it counts as finished, and that review — run
twice so far — has each time found real problems worth fixing rather than
rubber-stamping the work: the first pass found 8 issues including two that
could have let a "deleted" account keep working indefinitely, or let an
analytics recompute silently publish stale data after a delete. A second
review round found 5 more, all fixed. As of the material this entry is
based on, a further review of that most recent round of fixes had not yet
been run — so despite two full rounds of real fixes landing, this batch's
own accurate status is **still open, not finished**, and should not be
read as done until that final review closes it.

## Technical detail

### Scope and constraints

Parent plan: `2026-09-10-feat-enhanced-ui-to-staging-push-plan.md` — this
batch is an out-of-band insert ahead of that plan's step 9. TDD mandatory
throughout (red → green → refactor), `Decimal` never `float` for any
money/units/NAV value. Explicit division-of-labor boundaries applied: no
`terraform apply`, no `alembic upgrade head` against a real database, no
`docker build`/`push` or AWS-state-mutating command — author only, the
user applies.

### The 10 items

1. New Profile page (Account Info, Import History, Logout, and a
   visually-separated "Danger Zone" containing account deletion) — extends
   the app's existing plain-state tab pattern (`activeTab` union), no
   routing library added.
2. Account deletion as a single delete/deactivate flow (no separate
   toggle, an explicit product decision) with an exit survey, a 5-day
   grace period during which the account can be reactivated with no side
   effects, a whole-household cascade when the deleted account is the
   household's primary member, and a new daily hard-delete job following
   the existing EventBridge-Scheduler-plus-ECS-RunTask pattern used by the
   other 5 scheduled jobs.
3. Email/phone change via the existing generic OTP service (no second OTP
   mechanism) — verification against the *new* identifier before the
   User row updates.
4. Theme toggle relocated into the Profile page (reusing the existing
   component as-is).
5. Import history with per-import delete, including a specific correction
   made *before* implementation started: delete-import must call the
   existing `invalidate_holdings_cache()` helper (already used by every
   other transaction-mutating flow) or a user would see stale holdings for
   up to 15 minutes; and a resolved ambiguity that `AnalyticsSection` rows
   should be deleted outright (no staleness column exists) rather than
   marked stale.
6. Dashboard header real XIRR, extracted from `benchmark.py`'s existing
   private `_portfolio_xirr` helper into a shared function, kept
   synchronous (not routed through the async Analytics recompute path) —
   Lifetime XIRR by default, with a popover/toggle for Current-Holdings
   XIRR filtered to only presently-held schemes.
7. Conditional "Total Gain"/"Total Loss" header label (was a static
   "Total Gain / Loss" regardless of sign).
8. Portfolio allocation default sort (descending by value — the existing
   code was never actually sorted, contrary to how the UI happened to
   look) plus a client-side ascending/descending toggle.
9. AMC and asset-class drill-down modals, one parameterized component
   reusing the existing `Modal` pattern (rejected building two separate
   modals).
10. Consistent two-decimal-place formatting for four raw-Decimal-string
    fields across `FundDetailModal.tsx` and `DistributorComparisonModal.tsx`
    that had rendered with no formatting at all.

### Round 1

Implemented by Codex (user-run directly, no Agent dispatch, due to a
limited Codex reset budget that day). One handoff-doc correction was
caught and fixed before implementation started (item 5's holdings-cache
invalidation, above). Round 1 passed both full suites, independently
re-verified rather than trusting the implementer's self-report: backend
643 passed/6 deselected/0 failed, frontend 429/429 across 79 files with a
clean `tsc`. The orchestrator spot-checked the highest-risk diffs directly
(delete-import, the account-deletion migration and hard-delete cascade,
the XIRR extraction) but explicitly deferred a full hand-review of all 45
changed files to the mandatory adversarial-review gate.

### Round 1 adversarial review — 8 findings, all confirmed real

Zero Critical, 7 Important, 1 Minor — every one independently re-verified
against the actual code before being accepted (not taken on the reviewer's
word alone):

1. `pending_deletion` was enforced client-side only — a second open tab
   or a direct API call could reach any authenticated endpoint
   indefinitely during the 5-day grace period.
2. An in-flight analytics recompute, already running before a
   delete-import, had no way to be stopped and could re-publish
   pre-delete data afterward — no generation/version coordination existed.
3. A manually-entered opening-balance correction attached itself to
   whatever import happened to be "most recent," so deleting that CAS
   import silently deleted the user's manual correction too.
4. Deleting an import's transactions never revisited the affected
   folios, leaving stale `has_coverage_gap` flags and zero-value ghost
   rows in the distributor-comparison view.
5. The contact-change (email/phone) route selected the identity to
   update via an unqualified `.first()`, risking updating the wrong row.
6. The frontend's allocation sort compared money values via JS `Number()`
   float subtraction — a direct violation of this project's Decimal-only
   money-comparison rule.
7. New Profile-page mutations (contact change, delete, reactivate) had no
   pending/error UI state — a failed reactivate left the user stuck with
   no visible recourse.
8. (Minor) The hard-delete test didn't seed the FK-sensitive data graph
   (imports, transactions, folios, snapshots, analytics rows) it was
   meant to prove safe.

Given the spread across backend auth middleware, a new cross-cutting
generation-counter coordination primitive, folio cleanup logic across
three files, and frontend error-handling, this was written up as a second
full implementation round rather than an inline orchestrator fix (it did
not meet this project's "review-loop fix authorship" small-diff
criterion).

### Round 2 fixes and round 3 review

All 8 round-1 findings were fixed (round 2). A further adversarial review
round then found 5 more issues, all fixed directly by the orchestrator —
Codex's usage limits were exhausted that session, so per explicit user
instruction ("everything that's going to be done is going to be done by
you") the orchestrator implemented every round-3 fix in-context: two
data-race fixes tightening the delete/recompute-generation ordering
around `AnalyticsSection` deletes and holdings-cache invalidation; a fix
ensuring every phone/email identifier a deleted user ever verified has its
matching `OtpRequest` rows cleaned up before the identity/user rows are
gone (since `OtpRequest` carries no `user_id` foreign key); a request-token
guard around the contact-change OTP flow so a stale async response from a
closed/reopened modal can't corrupt state; and `PRAGMA foreign_keys=ON`
enabled on the test SQLite fixtures, which itself surfaced two genuine
pre-existing test-only row-insertion-ordering bugs unrelated to this
batch, fixed alongside.

### PM/tech-lead gap-analysis fixes

A separate, smaller round of UX gap-analysis findings (5 items) was
reviewed with the user directly; 3 were approved for fixing and 2 were
explicit user UX calls rather than defects: the dashboard XIRR popover was
replaced with a segmented Lifetime/Current toggle (reusing the app's
existing tab-switcher visual pattern) per the user's explicit instruction
overriding the original "show both at once" design; the allocation
drill-down modal gained a subtotal line; and a new Postgres-specific
cascade-delete test file was added (skip-if-unconfigured, following the
existing convention), with genuine execution against real Postgres
confirmed as a manual/CI step, not run in this session. The other two
gap-analysis items (a lifetime/current-holdings toggle wording choice, and
adding "type DELETE to confirm" friction to account deletion) were
explicitly decided by the user, not left as open defects.

### Current status — confirmed OPEN, not DONE

The handoff document's own Status field, and the delegation log's own
trailing entries, both state this batch is still **OPEN**: round-3's fixes
and the PM-gap-analysis fixes both have a mandatory adversarial-review
gate still owed before status can move to DONE — deferred/stacked pending
review capacity, not skipped. This journey entry records the batch as it
actually stands in the source material, not as complete.

### Related

- Parent plan: `Docs/superpowers/plans/2026-09-10-feat-enhanced-ui-to-staging-push-plan.md`
  (referenced by the handoff doc; this batch is an out-of-band insert
  ahead of that plan's step 9)
- Evidence: `08-evidence/documents/orchestration/investor-beta-feature-batch-handoff.md`
- Evidence: `08-evidence/documents/orchestration/investor-beta-feature-batch-implementation-prompt.md`
- Evidence: `08-evidence/documents/orchestration/delegation-log.md` (2026-09-11 entries)

## Addendum — 2026-09-24: the review gate never closed, and staging deployment proceeded anyway

### For stakeholders

This entry's original text says this batch was "still open, not finished"
pending a final review of the round-2/round-3 fixes and the PM-gap-analysis
fixes. A later-ingested raw source, covering the same day in more
continuous detail, confirms that final review never happened: work moved
directly from the PM-gap-analysis fixes into full test-suite reruns and
then into actually executing the AWS staging deployment runbook (see the
addendum on that runbook's own journey entry) — with no visible adversarial
review step in between. In other words, this batch's own status stayed
**OPEN** all the way through a real deployment to the shared staging
environment other people can reach. This is recorded as a new risk,
[R-065](../07-risks-and-debt.md), since it's a process gap (a mandatory
quality gate not being enforced before a deploy), not a specific code bug.

### Technical detail

The source material shows, in one continuous session: round-3 review
fixes (5 findings) applied directly by the orchestrator → both full test
suites rerun clean (backend 649/8 skipped, frontend 436/79 files) → a
PM/tech-lead gap-analysis pass (5 findings, 3 approved and fixed: an XIRR
popover replaced with a Lifetime/Current toggle, a subtotal line added to
the allocation drill-down modal, and a Postgres-specific cascade-delete
test added) → both suites rerun again → straight into the AWS staging
runbook's Steps 1-9 (see the 2026-09-11 runbook entry's new addendum for
what was actually executed). At no point in this continuous account does
a review agent re-examine the round-3 fixes or the PM-gap-analysis fixes
before that deployment. This doesn't mean the fixes were wrong — the
orchestrator's own spot-checks and both full suites passing are real
signal — but it does mean this project's own stated rule ("every task/batch
goes through a mandatory adversarial-review gate before it counts as
finished") was not actually followed for this specific batch before it
reached a shared, externally-reachable environment.

### Addendum evidence

- `08-evidence/documents/darshan changes.md` (the entire session, from the
  round-3 review through the AWS staging deployment)
