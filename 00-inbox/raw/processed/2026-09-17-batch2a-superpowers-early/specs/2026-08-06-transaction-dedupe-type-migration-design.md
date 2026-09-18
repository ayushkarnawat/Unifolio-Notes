# Transaction Dedupe Key Migration — Design

## Purpose

Phase 3's final whole-branch review flagged a real, time-sensitive bug:
`transactions`' dedupe key — the DB `UniqueConstraint` and the matching
app-side check in `confirm_import` — is `(folio_id, date, amount, units)`,
missing `type`. Before this session's Phase 3 work, a same-day purchase and
redemption of equal magnitude had opposite signs (a real bug in the CAS
parser, since fixed at its own root cause) and couldn't collide on this
key. Now that both are normalized to positive magnitudes at parse time, a
same-day purchase and redemption of the same amount/units **can** collide —
and the import pipeline would silently drop the second one as a false
duplicate. Real, silent data loss, flagged to land before Phase 2b's Family
CAS Upload starts processing real CAS files.

## Scope

**In scope:** add `type` to both the DB-level `UniqueConstraint` on
`transactions` (a new Alembic migration — `0001_initial_schema.py` is
frozen, already applied, never edited) and the app-side dedupe tuple/query
in `backend/app/services/import_/service.py`'s `confirm_import`. Both
together — fixing only one side turns silent drops into unhandled
`IntegrityError` 500s instead of fixing the bug.

**Out of scope:** any other schema change, any change to the dedupe
*logic* beyond widening the key, any change to `parser.py`'s already-fixed
sign normalization.

## Migration

`backend/alembic/versions/0002_transaction_dedupe_includes_type.py`.
Two dialect paths, matching 0001's own precedent (the `transactions` table
is Postgres-partitioned — `RANGE (date)` — so its Postgres DDL is
hand-written raw SQL rather than SQLAlchemy's constraint API, which can't
reach into `PARTITION BY RANGE` tables):

- **SQLite** (what's actually exercised in this sandbox, via the existing
  real-subprocess Alembic round-trip test): SQLite can't `ALTER` a
  constraint in place. Use Alembic's `batch_alter_table` — the standard
  pattern that recreates the table under the hood with the new constraint,
  copies data, swaps names. Drop the old 4-column `UniqueConstraint`, add
  the 5-column one.
- **Postgres**: `ALTER TABLE transactions DROP CONSTRAINT ... ADD
  CONSTRAINT ... UNIQUE (folio_id, date, amount, units, type)` on the
  parent table — Postgres propagates a unique constraint to every existing
  partition automatically as long as the partition key (`date`) stays in
  the constraint, which it does. The one wrinkle: migration 0001's inline
  `UNIQUE (...)` in a raw `CREATE TABLE ... PARTITION BY RANGE` statement
  let Postgres auto-generate the constraint's name rather than naming it
  explicitly, so this migration can't safely hardcode a guessed name. It
  looks the actual name up from `information_schema.table_constraints` at
  migration time instead of assuming one.
- No data transformation — existing rows keep their values, this only
  widens what counts as a duplicate going forward. `downgrade()` reverses
  both paths back to the 4-column constraint.

## `service.py`

`confirm_import`'s two same-purpose checks both widen to include type:

```python
dedupe_key = (folio.id, norm.txn_date, norm.amount, norm.units, norm.txn_type)
...
dup = (
    db.query(Transaction)
    .filter_by(folio_id=folio.id, date=norm.txn_date, amount=norm.amount, units=norm.units, type=norm.txn_type)
    .first()
)
```

No other change to the surrounding logic — the in-memory `added_keys` set
and the DB lookup are still the same two-layer check the code already has
(explained in the existing comment: `autoflush=False` means a same-call
duplicate needs the in-memory set, since the DB lookup alone can't see a
row `db.add()`-ed earlier in the same loop).

## Testing

- Extend `backend/tests/test_migrations.py` (already runs real subprocess
  `alembic upgrade head` / `downgrade base` against a real SQLite file) with
  an assertion that the new constraint genuinely includes `type` — read it
  back via `PRAGMA index_list`/`index_info` after upgrading, confirm it's
  gone after downgrading.
- A `service.py`-level test proving the exact scenario the bug report
  described: a same-day purchase and redemption of equal amount/units are
  both correctly inserted (not one silently dropped) — the regression this
  whole migration exists to fix. A second test confirms a genuine
  re-upload (same type, same everything) is still correctly deduped as
  before — proving the widened key didn't accidentally make real
  duplicates pass through.

## Open Items Not Resolved Here

- The Postgres DDL path is written carefully (dynamic constraint-name
  lookup, not a guess) but isn't exercised by this sandbox's test suite —
  no live Postgres instance is available here. It follows 0001's own
  already-established pattern for the same table, so the risk is
  consistent with what's already shipped, not new.
