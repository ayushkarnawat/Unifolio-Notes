# Handoff: investor-beta-feature-batch

**Status:** OPEN
**Parent plan:** `Docs/superpowers/plans/2026-09-10-feat-enhanced-ui-to-staging-push-plan.md`
(this batch is an out-of-band insert ahead of that plan's step 9 — an investor
requested these 10 changes for a same-day staging demo; the plan's step 9/10/11
resume once this lands and is verified on staging)

## Task

A batch of 10 changes, one-shotted in a single implementation pass. Work
top-to-bottom; each numbered item below is independently testable and should get
its own passing test(s) before moving to the next (TDD per `AGENTS.md` — red,
green, refactor, no exceptions).

### 1. Profile page (new — everything else in this batch lives inside it)

- No router exists in this app. View switching is plain state:
  `frontend/src/features/dashboard/MainDashboardFlow.tsx`'s
  `activeTab: "dashboard" | "analytics"`, synced to `window.history.state` for
  back-button support (see its `useState` initializer and `popstate` handler).
  Extend that union to `"dashboard" | "analytics" | "profile"` — do not add a
  routing library.
- Add a new icon button to the header action row in
  `frontend/src/features/dashboard/NavigationShell.tsx` (the `{/* Action
  Buttons: Add Data, Theme & Logout */}` block, ~line 144), opening the Profile
  tab. Place it next to the existing `ThemeToggle`.
- **Move (don't duplicate) the Logout button**: it currently lives in that same
  header action row (`NavigationShell.tsx` ~lines 156-165, the `<button
  onClick={logout}>` with `LogOut` icon). Remove it from the header entirely;
  render the equivalent logout control inside the new Profile page instead.
- Profile page sections, top to bottom:
  1. **Account Info** — user's name (read-only, not editable in this batch),
     email with a "Change" action, phone with a "Change" action, the existing
     `<ThemeToggle />` component (reused as-is, not rebuilt).
  2. **Import History** (item 5 below).
  3. **Logout** button.
  4. **Danger Zone** — visually separated (e.g. red-bordered card), containing
     "Delete Account" (item 2 below). Comes last, deliberately below Logout.

### 2. Account deletion: exit survey + 5-day grace period (new)

- **Deliberately one flow, not two.** "Delete" and "deactivate" are the same
  state transition — do not build a separate standalone deactivate toggle.
  Clicking "Delete Account":
  1. Shows a short exit survey: single-select reason (`Not using it enough` /
     `Missing a feature` / `Found an alternative` / `Data or trust concern` /
     `Other`) plus an optional free-text field. Store the response (new small
     table, one row per deletion request — worth keeping for product
     visibility into churn reasons).
  2. Shows a confirmation screen stating plainly: "Your account and all
     household data will be permanently deleted in 5 days. You can cancel
     anytime before then." No further "are you sure" beyond this one screen.
  3. On confirm: the user's account (and, per below, the whole household) is
     marked `pending_deletion` with a `deletion_scheduled_at = now + 5 days`.
     Needs a new nullable column/state on the relevant user/household model —
     your call on exact schema shape, but it must be queryable ("give me every
     account whose grace period has expired").
- **While `pending_deletion`:** the user can still log in, but sees *only* a
  "Your account is scheduled for deletion on `<date>` — Reactivate" screen (no
  dashboard, no analytics, nothing else reachable). "Reactivate" clears the
  `pending_deletion` state entirely, no side effects.
- **Household cascade:** if the account being deleted is the household's
  primary/self account (not a dependent household member), the entire
  household — every member, every row of their data — goes into
  `pending_deletion` together and is hard-deleted together after the grace
  period. Confirmed product decision, not open for reinterpretation.
- **Hard delete job:** a new daily scheduled job, following the *exact*
  existing pattern of the other 5 EventBridge Scheduler + ECS RunTask jobs
  (`backend/scripts/jobs/refresh_nav_daily.py` is the simplest reference for
  script shape; `infra/modules/scheduler` is the existing Terraform module —
  add this job to it the same way the other 4 were added, do not invent a
  second scheduling mechanism). It queries every account/household past its
  `deletion_scheduled_at` and permanently deletes all of their data (imports,
  transactions, folios, household members, analytics sections/recompute
  status, the user row itself). **Write the Terraform, do not `terraform
  apply` it** — same division of labor as every other infra change in this
  project; the user applies it themselves once reviewed.
- **Do not run `alembic upgrade head` against any real database** for the new
  survey-response table's migration (or any other migration in this batch).
  Author the migration only — same reason a missing-migration-application gap
  already caused a live staging incident earlier today (`0012_analytics_sections`
  was authored but never applied and 500'd the Analytics tab for hours). The
  user runs migrations against staging RDS themselves, via the bastion tunnel,
  exactly as done today.

### 3. Email / phone change (new, via existing OTP infra)

- Reuse `backend/app/services/auth/otp.py`'s existing `create_otp_request` /
  `verify_otp` — both are already generic over `channel`/`identifier`, not
  hardcoded to signup/login. Do not write a second OTP mechanism.
- Flow: user requests a change to a new email or phone → OTP sent to the *new*
  identifier (not the old one) → user verifies → the User row's email/phone is
  updated only on successful verification. Never allow an unverified direct
  edit.

### 4. Theme toggle in Profile

- Render the existing `<ThemeToggle />` component (already used in
  `NavigationShell.tsx`, `MainDashboardFlow.tsx`, `MobileRoot.tsx`) inside the
  Account Info section. Nothing new to build here — this line item exists only
  so it isn't missed from the page layout.

### 5. Import history + delete-import (new)

- New section in the Profile page listing every `Import` row
  (`backend/app/models/imports.py`) scoped to the user's household, showing
  fields already on the model: `uploaded_at`, `statement_from_date`/
  `statement_to_date`, `status`, `new_transactions_count`.
- Each row gets a "Delete" action → confirm ("This removes N transactions tied
  to this import from your holdings.") → backend deletes every `Transaction`
  row with that `import_id` (safe: `Transaction.import_id` is a non-nullable FK,
  so this is unambiguous — no risk of deleting another import's data) and then
  marks that user's existing `AnalyticsSection` rows stale (or deletes them
  outright — whichever this codebase's existing staleness convention already
  uses in `app/services/analytics/recompute.py`) so the next Analytics load
  triggers a fresh recompute reflecting the removed data.
- **Correction (caught in review before implementation started):** holdings
  ARE computed live from transactions on every request — there is no separate
  `Holding` table — but `app/services/dashboard/holdings.py` wraps that
  computation in a process-local, 15-minute TTL cache keyed by
  `(household_member_ids, date)`. Every other transaction-mutating flow in
  this codebase (CAS import, import rollback) already calls
  `invalidate_holdings_cache(household_member_id)` after the mutation — see
  `app/api/imports.py` and `app/services/import_/service.py` for the existing
  call-site pattern. Delete-import must do the same: call
  `invalidate_holdings_cache(household_member_id)` right after deleting the
  `Transaction` rows, in the same request/transaction as the delete, or a
  user can delete an import and still see the stale (pre-delete) holdings on
  their next Dashboard load for up to 15 minutes.
  `distributor_comparison.py`'s own cache needs no separate call — it reuses
  `holdings.py`'s generation counter and rejects stale entries on next read,
  so the single `invalidate_holdings_cache()` call covers both.
- **Resolved ambiguity:** "mark stale (or delete outright)" above — checked,
  `AnalyticsSection` has no staleness/dirty column, so there's only one real
  option: delete the rows outright. `GET /analytics/{scope}` already treats
  zero rows as "needs recompute" and auto-dispatches (`app/api/analytics.py`),
  so deleting is both correct and sufficient — do not add a staleness field.
- **Expected user-visible timing, write this into the delete-import
  confirmation UX so support doesn't get "did my delete work?" tickets:**
  Dashboard reflects the delete on the very next fetch after the request
  completes — no wait, since cache invalidation is synchronous in the same
  request. Analytics does not update immediately: deleting the rows makes
  the next `GET /analytics/{scope}` dispatch a fresh ECS Fargate recompute,
  same `recomputing: true` spinner state already used for a first-time user,
  realistically tens of seconds to a couple minutes before it resolves. This
  is expected, not a bug — do not try to make analytics synchronous here,
  the precompute architecture doc explicitly rules out inlining recompute on
  a request-serving replica.
- **Delete-all-imports (zero-transaction end state) — not a new edge case,**
  confirmed it's the same zero-holdings/empty-portfolio path a brand-new
  user hits before their first import, already covered by existing tests
  (e.g. `compute_portfolio_score` early-returns `_EMPTY_PORTFOLIO_SCORE` for
  `not holdings`). No new empty-state handling needed on either the
  Dashboard or Analytics side — reuse what's already there.

### 6. Dashboard header: real XIRR (replacing the current gain % metric)

- `backend/app/services/analytics/benchmark.py` already has a private
  `_portfolio_xirr(transactions, current_value)` helper built on the pure
  Decimal `xirr()` in `backend/app/services/analytics/xirr.py` — no network
  calls, no dependency on the slow NAV-warming precompute path. Extract it into
  a shared, non-private function callable from the Dashboard holdings
  endpoints (both the combined/household-aggregate one and the per-member one)
  — do not route this through the Analytics recompute/dispatcher path; it must
  stay synchronous and fast, matching the Dashboard's existing performance
  posture.
- Header shows **Lifetime XIRR** by default:
  - Family/combined view → XIRR over the whole household's transactions +
    current total value.
  - Single-member view → that member's own transactions + current value only.
  - "Lifetime" = every transaction ever, including from schemes now fully
    redeemed (zero current units) — i.e. pass the complete transaction list,
    don't filter anything out.
- Clicking the XIRR value opens a small popover with two numbers:
  - **Lifetime XIRR** (as above).
  - **Current-Holdings XIRR** — same calculation, but the transaction list
    filtered to only schemes with nonzero units held today, and `current_value`
    likewise restricted to just those schemes.

### 7. Header gain/loss label: conditional on sign

- `frontend/src/features/dashboard/DashboardView.tsx` (~line 327) currently
  renders a static label "Total Gain / Loss" regardless of sign. Change to:
  **"Total Gain"** when the total is ≥ 0, **"Total Loss"** when negative. Drop
  the combined slash-label. Small, self-contained, no backend change.

### 8. Portfolio allocation: default sort + ascending/descending toggle

- `backend/app/services/dashboard/allocation.py`'s `_to_buckets` helper
  (~line 52) currently returns buckets in arbitrary dict-insertion order —
  contrary to how the current UI happens to look, it is not actually sorted
  today. Fix: sort by `current_value` descending before returning, for both
  `by_asset_class` and `by_amc`.
- Frontend (`DashboardView.tsx`'s allocation section, `allocationTab: "asset" |
  "amc"`) adds a sort-direction toggle control. It only needs to flip the
  already-fetched array client-side — no re-fetch, no backend parameter needed.

### 9. AMC and asset-class drill-down modals (new, same component for both)

- Clicking an AMC in the "By AMC" breakdown, or an asset class in the "By Asset
  Class" breakdown, opens a modal listing every holding in that
  AMC/asset-class. Reuse the existing `Modal` component
  (`frontend/src/components/Modal.tsx`) and follow the same structural pattern
  already used by `frontend/src/features/dashboard/FundDetailModal.tsx` /
  `DistributorComparisonModal.tsx` in the same directory — this should be one
  parameterized modal component (grouped-by AMC or grouped-by asset-class),
  not two separately-built modals.

### 10. Fix inconsistent decimal formatting in the fund detail modal (and its
sibling)

- `frontend/src/features/dashboard/FundDetailModal.tsx` renders three fields
  directly from raw backend Decimal strings with no formatting at all:
  `holding.units_held` (line 78), `holding.average_nav` (line 82),
  `holding.current_nav` (line 90). `DistributorComparisonModal.tsx` line 189
  has the same issue (`scheme.average_nav`). All four should render to exactly
  two decimal places (e.g. `26.29`, never `26.2900000` or `26.3`). Add one
  shared formatting helper (this file already has a `formatCurrency` at the
  bottom of `FundDetailModal.tsx` with `maximumFractionDigits: 0` — add a
  sibling, e.g. `formatDecimal(val, { minimumFractionDigits: 2,
  maximumFractionDigits: 2 })`, or extend `formatCurrency` with an options
  param) and apply it at all four call sites, plus anywhere the new
  drill-down modal (item 9) renders the same kind of raw decimal field. Do not
  fix only `FundDetailModal.tsx` and leave `DistributorComparisonModal.tsx`
  inconsistent — same root cause, same fix, both call sites.

## Constraints

- `AGENTS.md` non-negotiables apply in full: TDD (red → green → refactor, no
  implementation before a failing test), `Decimal` never `float` for any
  money/units/NAV value anywhere in this batch's backend code.
- Follow this codebase's existing patterns exactly where one already exists
  (listed per-item above) — do not introduce a second modal system, a second
  OTP mechanism, a second job-scheduling mechanism, or a routing library.
- Backend deploy strategy on staging is single-task, stop-then-start
  (`deployment_minimum_healthy_percent = 0`) — not relevant to this batch's
  code, just don't be surprised by it if you read the Terraform.
- Per this project's division of labor: **do not run `terraform apply`,
  `docker build`/`push`, `aws ecs update-service`, or `alembic upgrade head`
  against any real database.** Author all of that; the user runs it.

## Approaches considered and rejected

- **Separate manual deactivate/reactivate toggle, independent of deletion** —
  rejected per explicit product decision; folded into the single delete/grace
  flow to keep the state machine simple (one state transition, not two
  overlapping ones).
- **Routing library (react-router etc.) for the new Profile page** — rejected;
  this app has no router anywhere and the existing plain-state tab pattern
  already handles back-button support correctly. Adding a router for one page
  would be a second navigation system living alongside the first.
- **Routing email/phone change through the Analytics-style async
  dispatch/recompute path** — not applicable; XIRR (item 6) was specifically
  checked against this and confirmed cheap enough to stay synchronous. Don't
  add unnecessary async machinery to what's pure in-process Decimal math.
- **Two separate drill-down modals (AMC vs asset-class)** — rejected; same
  shape of data, same interaction, parameterize one component instead.

## Open questions

- Exact survey reason options and confirmation-screen copy are a first draft
  above (item 2) — flag back if you think a materially different set/wording
  is warranted, otherwise proceed with what's specified rather than blocking on
  wording.
- Exact schema shape for tracking `pending_deletion` + `deletion_scheduled_at`
  (new columns on an existing table vs. a new small table) is left to your
  judgment — just make sure it's cleanly queryable by the daily hard-delete job
  and cleanly reversible by "Reactivate."
- Daily hard-delete job's schedule time: pick a time that doesn't collide with
  the existing 5 jobs (`benchmark-daily`/`nav-daily` run ~00:30 UTC,
  `analytics-recompute-daily` runs 06:30 IST/01:00 UTC, `ter-monthly`/
  `aaum-quarterly` are monthly/quarterly) — anything clear of those windows is
  fine, state your choice in the PR/handoff update rather than asking first.

## Round 2 — mandatory adversarial-review fixes

Round 1 passed both full test suites (backend 643 passed/6 deselected/0
failed, frontend 429/429 + clean `tsc`, independently re-verified — not
self-report), but the mandatory adversarial-review gate found 7 real
Important-severity issues and 1 Minor, all independently re-confirmed against
the actual code before being added here. TDD applies to every fix below the
same as round 1 — red test proving the bug, then the fix. Do not weaken or
delete any round-1 test to make a round-2 fix pass; if a round-1 test's
*expectation* was actually wrong given a round-2 fix, say so explicitly
rather than silently loosening it.

### R2-1. Pending-deletion is frontend-only — enforce it server-side too
`get_current_user` (`app/services/auth/session.py`) never checks
`user.pending_deletion`; only `App.tsx` gates on it client-side. A second
already-open tab, or a direct API call, reaches every authenticated endpoint
indefinitely during the 5-day grace period.
Fix: add a dependency (e.g. `get_active_user`, wrapping `get_current_user`)
that raises 403 for `pending_deletion` users, and swap it in everywhere
*except* the small allow-list that must keep working during the grace
period: login/session refresh, `GET /auth/me`, `POST /auth/reactivate`,
logout. Audit every router for which one it currently depends on.

### R2-2. In-flight analytics recompute can republish pre-delete data after a delete-import
`app/api/imports.py`'s delete-import route deletes `AnalyticsSection` rows
but has no way to stop a recompute that was *already running* before the
delete from re-upserting sections computed from pre-delete data afterward
(`recompute.py`'s `_upsert_section` loop, `analytics.py`'s `GET` only
re-dispatches when `not rows` — which is false again once the stale run
finishes writing).
Fix direction (consistent with `holdings.py`'s existing generation-counter
pattern — reuse the idea, this doesn't need a new primitive): add a
`generation` column to `AnalyticsRecomputeStatus`, bumped by delete-import
(and by the hard-delete job, for the same reason) in the same transaction as
the row deletes. `recompute_household_analytics` captures the generation
once when it starts: before each `_upsert_section` call, re-check the
current DB generation against the captured one — if it no longer matches,
stop writing further sections for this run immediately (don't just log and
continue) and release its own claim so the next `GET` can dispatch a correct
run. Write a test that proves the race: claim held, generation bumped
mid-run (simulating a concurrent delete), assert the stale run stops writing
and the next `GET` dispatches fresh.

### R2-3. Deleting an import can delete a manually-entered opening balance
`app/services/import_/coverage_gap.py`'s opening-balance entry attaches
itself to whatever the household's *most recent* `Import` row is, rather
than getting a dedicated marker — so deleting that CAS import deletes the
user's manual correction too, silently. The delete-import confirmation
count (`new_transactions_count`) also doesn't reflect this, so "removes 10
transactions" can actually remove 11.
Fix: opening-balance entries should always get their own dedicated `Import`
marker row (the existing "create one if none exists" branch, unconditionally
— never attach to a real CAS import), fully decoupling manual entries from
any CAS import's lifecycle. Check callers of this association first in case
something else depends on opening balances being tied to a real import for
display purposes; if so, say so instead of guessing.

### R2-4. Orphaned/stale folios after a transaction delete
Deleting an import's transactions never revisits the affected `Folio` rows.
An emptied folio keeps its stale `has_coverage_gap` flag (still listed by
`cas_imports.py`'s coverage-gap endpoint) and still gets pre-seeded as a
zero-value ghost row by `distributor_comparison.py`.
Fix: after deleting transactions, for each folio that had a transaction tied
to the deleted import: if it now has zero remaining transactions, delete the
folio; if it still has transactions, re-run whatever existing function
already (re)computes `has_coverage_gap`/`coverage_gap_details` for a folio —
reuse it, don't reimplement the coverage-gap logic a second time.

### R2-5. Contact-change can update the wrong identity row
`app/api/auth.py`'s `verify_contact_change` selects the identity to update
via `.first()` on `(user_id, provider)` with no further tie-break. If a user
can have more than one identity row for the same provider, this can update
an unrelated one and/or hit a uniqueness violation when the target
identifier is one the same user already owns (e.g. re-linking a previously
used email).
Fix: look up the identity explicitly by the user's *current* denormalized
`email`/`phone_number` value, not a bare `.first()`. Handle the
already-owned-by-same-user case as a no-op/consolidation rather than letting
it hit a uniqueness error.

### R2-6. Allocation sort compares money as a JS float
`DashboardView.tsx`'s allocation sort does
`Number(b.current_value) - Number(a.current_value)`, a float subtraction
over Decimal-string money values — this repo's own rule is Decimal/exact
string comparison for any money value, never float. Add an exact
decimal-string comparator to `frontend/src/lib/decimal.ts` (reuse its
existing BigInt-based machinery from item 10, don't hand-roll a second
approach) and use it here instead of `Number()`.

### R2-7. No pending/error UI state on new Profile mutations
`ProfileView.tsx` and `PendingDeletionScreen.tsx` don't surface OTP
throttling/rejection, delete/deactivation failures, or a failed reactivate —
promises are discarded or left to become unhandled rejections. Reactivate is
the worst case: on failure the user is stuck on that screen with no
alternative action shown.
Fix: add loading/disabled states and a visible error message for
account-deletion request, contact-change request/verify, delete-import, and
especially reactivate. Add rejection-path tests for each.

### R2-8 (Minor). Hard-delete test doesn't exercise the graph it's meant to prove
`tests/services/auth/test_account_deletion.py`'s hard-delete test only seeds
user/member/identity/session/survey — not imports, transactions, folios,
snapshots, analytics sections/status, or pending identity links, i.e. not
the FK-sensitive deletion ordering the service actually has to get right.
Expand it to seed the full graph and assert full cleanup with no FK errors.

When done: re-run both full suites yourself and report real counts (as
round 1), then this goes through another mandatory adversarial-review round
before Status can move to DONE.
