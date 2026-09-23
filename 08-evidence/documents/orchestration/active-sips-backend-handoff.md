# Handoff: active-sips-backend

**Status:** DONE
**Parent plan:** `Docs/superpowers/plans/2026-08-18-active-sips-cadence-redesign.md` (Tasks 1-5)

## Task

Implement Tasks 1 through 5 of the parent plan, in order, exactly as written —
each task's steps already contain the real test code and real implementation
code to use verbatim. This covers:

1. Two pure date-math helpers (`_add_months_clamped`, `_next_due_on_or_after`)
   in `backend/app/services/dashboard/sip.py`.
2. Rewriting `compute_active_sips` to remove the 40-day cutoff, add a
   redemption exclusion (`units_held <= 0` via `_process_folio_lots`, reused
   from `holdings.py`), and add a `next_due_date` field to `SipRow`.
3. A new `compute_sips_for_month` function with two-anchor
   (`first_txn`/`latest_txn`) actual-vs-projected reconciliation, plus new
   `SipMonthlyRow`/`AggregateSipsMonthlyResponse` schemas.
4. A query-count regression test guarding against reintroducing the N+1
   per-folio query pattern.
5. Two new API routes (`GET /household-members/{id}/sips/monthly`,
   `GET /household/aggregate/sips/monthly`) plus `get_aggregate_sips_monthly`
   in `aggregate.py`.

Follow TDD exactly as each task's steps specify: write the test, run it,
confirm it fails for the stated reason, implement, run again, confirm it
passes, commit. Do not skip the "verify it fails" step for any task.

Run the full backend suite (`cd backend && pytest -q`) after Task 2 and again
after Task 5, and paste both result lines into your final report.

## Constraints

- `Decimal`-string arithmetic for every money value (`sip_amount`/`amount`) —
  never float, per CLAUDE.md's non-negotiables.
- TDD mandatory — red before green, for every task.
- No NAV/network calls anywhere in this feature.
- `compute_active_sips`/`compute_sips_for_month` must issue a constant number
  of queries regardless of folio count — this is what Task 4's regression
  test exists to guard, per an explicit user load-time constraint this
  session. Do not silently reintroduce a per-folio query loop while
  implementing Tasks 2-3.
- Reuse `_process_folio_lots` and `_LOT_CONSUMING_TYPES` from
  `app.services.dashboard.holdings` by import — do not reimplement lot
  processing. `distributor_comparison.py` already does this same cross-module
  import; it's an established, accepted pattern in this codebase, not a
  layering violation.

## Approaches considered and rejected

- A single ambiguous "anchor" transaction for `compute_sips_for_month`'s
  projection logic was tried and rejected during spec review — it incorrectly
  omitted genuinely-skipped past months once a later real transaction became
  the new "most recent" anchor. The plan's `first_txn`/`latest_txn` split
  fixes this; implement it exactly as Task 3 Step 4 specifies, don't
  simplify back to a single anchor.
- A per-folio transaction query (matching the *old* `compute_active_sips`)
  was rejected for load-time reasons — Task 2 Step 4's
  `_folio_transactions_by_id` batched-query helper replaces it and must be
  reused by Task 3 as well, not reimplemented per-function.

## Open questions

None — every task's code is fully specified in the plan. If SQLAlchemy
version specifics make the `case(...)` import signature used in
`_folio_transactions_by_id` (`case((condition, value), else_=...)`) not
compile, check `holdings.py`'s existing usage of the same import for the
exact working signature in this codebase rather than guessing — do not
change the ordering logic itself.
