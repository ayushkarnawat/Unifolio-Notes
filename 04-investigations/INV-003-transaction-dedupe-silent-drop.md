# Investigation: A same-day buy and sell of equal size was silently dropped on import

Status: Resolved
Date: 2026-08-06
Related: `02-journey/2026-08-06-onboarding-frontend-dashboard-backend-and-a-silent-data-loss-fix.md`; R-003; migration `0002`

## Trigger

While working through the dedupe behaviour of the CAS import path, a case
was identified where two genuinely distinct transactions in the same folio
would be treated as duplicates of one another and one of them discarded —
with no error, no warning, and no trace in the import record.

## Expected behavior

The import path deduplicates so that re-uploading the same statement does
not double-count transactions. Two *different* transactions should never be
collapsed into one.

## Observed behavior

A purchase and a redemption occurring in the same folio, on the same date,
for the same amount and the same number of units are indistinguishable under
the four-column duplicate key in use — folio, date, amount, units — and the
second one encountered is dropped as a duplicate.

The failure is silent by design of the dedupe mechanism: dropping a
duplicate is the normal, correct path, so nothing about the drop looks
wrong from inside the import.

## Hypotheses

1. The case is theoretical and does not occur in real CAS statements.
2. The four-column key was always insufficient and this was never noticed.
3. Something changed that made a previously-sufficient key insufficient.

## Experiments

| Experiment | Expected signal | Actual result | Conclusion |
|---|---|---|---|
| Construct a same-date, equal-magnitude purchase/redemption pair in one folio and run it through the confirm path | Two rows persisted | One row persisted; the second silently skipped | The defect is real and reproducible |
| Review the history of how amounts and units are stored | Consistent storage from the start | An earlier fix **normalised both amounts and units to positive magnitudes** | Hypothesis 3 confirmed |
| Re-read the four-column key against pre-normalisation data | Pair distinguishable | Before normalisation the two rows differed by sign, so the four-column key *did* separate them | The key was sufficient until the normalisation change, and silently stopped being sufficient |
| Check whether widening only the database constraint would fix it | Fix | It would convert silent drops into integrity errors surfacing as 500s, because the application-side check would still consider the second row a duplicate and attempt a conflicting write path | Both sides must change together |
| Check whether re-upload deduplication still works after widening | Still deduped | Covered by an already-existing, already-passing test | Widening does not regress the case dedupe exists for |

## Root cause

A correctness fix caused a correctness regression elsewhere. Normalising
transaction amounts and units to positive magnitudes removed the sign that
had been — incidentally, not by design — the only thing distinguishing a
purchase from a redemption of identical size on the same day under the
duplicate key. Nothing connected the two changes, because the duplicate key
was never written down as depending on sign.

## Resolution

Migration `0002_transaction_dedupe_includes_type` widens the unique
constraint from `(folio_id, date, amount, units)` to
`(folio_id, date, amount, units, type)`, and the application-side duplicate
check in the import confirm path is widened in the same change.

Two implementation notes worth preserving:
- Migration `0001` is frozen and was not edited; the fix is a new additive
  migration.
- Neither dialect's path hardcodes the existing constraint's name. Migration
  `0001` let each dialect auto-generate that name, so both the SQLite path
  (via a batch table rebuild, since SQLite cannot alter a constraint in
  place) and the PostgreSQL path (an alter on the partitioned parent, which
  propagates to every partition) **look the real name up at migration time**.
  A hardcoded guess risked failing to drop the constraint, or dropping the
  wrong one.
- No data transformation. Existing rows are untouched; only what counts as a
  duplicate going forward changes.

## Remaining uncertainty

- **The PostgreSQL path was never executed.** No live PostgreSQL instance
  existed in the development environment, so that branch was written and
  reviewed but not run. See [R-021](../07-risks-and-debt.md).
- Rows already lost to this defect in any statement imported before the fix
  are not recoverable by the migration — it changes future behaviour only.
  Whether any real import was affected was not established.
- The general lesson — that an invariant depended on a property nobody had
  written down — has no mechanism preventing recurrence, in the same way
  [R-014](../07-risks-and-debt.md) has none for documentation drift.

## Related records

- [2026-08-06 journey entry](../02-journey/2026-08-06-onboarding-frontend-dashboard-backend-and-a-silent-data-loss-fix.md)
- [Risks and debt](../07-risks-and-debt.md) — **R-003** records three
  competing dedupe-key definitions across the PRDs and the schema; this
  investigation is the evidence for why the five-column key is the correct
  one, and supports R-003's recommended resolution
- [Database schema reference](../05-docs/reference/database-schema.md)
- Evidence: `08-evidence/documents/specs/2026-08-06-transaction-dedupe-type-migration-design.md`,
  `08-evidence/documents/plans/2026-08-06-transaction-dedupe-type-migration.md`
