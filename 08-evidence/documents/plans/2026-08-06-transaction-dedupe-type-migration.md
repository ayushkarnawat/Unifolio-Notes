# Transaction Dedupe Key Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Widen the `transactions` table's dedupe key — both the DB
`UniqueConstraint` and the app-side check in `confirm_import` — from
`(folio_id, date, amount, units)` to `(folio_id, date, amount, units, type)`,
closing a real silent-data-loss gap: a same-day purchase and redemption of
equal magnitude can now collide on the narrower key (their signs used to
differ, disambiguating them, before an earlier fix normalized both to
positive magnitudes) and would be silently dropped as a false duplicate.

**Architecture:** A new, additive Alembic migration (`0002`, never editing
the frozen `0001`) with a SQLite path (via `batch_alter_table`, since
SQLite can't `ALTER` a constraint in place) and a Postgres path (via
`ALTER TABLE` on the partitioned parent, which propagates to every
partition automatically), both looking up the actual existing constraint
name at migration time rather than guessing it. Paired with a two-line
widening of `confirm_import`'s existing dedupe logic in `service.py`.

**Tech Stack:** Alembic, SQLAlchemy 2.0, pytest — already in place, no new
dependencies.

## Global Constraints

- **Migration `0001_initial_schema.py` is frozen — never edit it.** This
  plan adds a new file, `0002_transaction_dedupe_includes_type.py`.
- **`Decimal`, never `float`**, in every test fixture touching
  money/units/NAV, matching this project's existing test conventions.
- **Never guess a DB-generated constraint name.** Both the SQLite and
  Postgres paths look the actual name up at migration time (`PRAGMA
  index_list` for SQLite, `information_schema.table_constraints` for
  Postgres) rather than hardcoding an assumed name — migration 0001 let
  both dialects auto-generate the original constraint's name, so a
  hardcoded guess in this migration would be a real risk of failing to
  drop it, or dropping the wrong thing.
- **No data transformation.** This migration only widens what counts as a
  duplicate going forward — existing rows are untouched.

---

### Task 1: Migration `0002` — widen the DB constraint

**Files:**
- Create: `backend/alembic/versions/0002_transaction_dedupe_includes_type.py`
- Modify: `backend/tests/test_migrations.py`

**Interfaces:**
- Produces: the new constraint name `uq_transactions_folio_date_amount_units_type`
  on the `transactions` table (5 columns: `folio_id, date, amount, units, type`)
  after `alembic upgrade head` — Task 2's `service.py` change relies on this
  being in place (its own dedupe query doesn't reference the constraint by
  name, but the whole point of this plan is that both layers agree on the
  same 5-column key).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_migrations.py` (this file already has
`BACKEND_DIR`, `subprocess`, and `sys` imported at the top — reuse them):

```python
def test_transaction_dedupe_constraint_includes_type_after_upgrade(tmp_path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "dedupe_migration_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR, capture_output=True, text=True,
    )
    assert upgrade.returncode == 0, upgrade.stderr

    def _unique_constraint_columns(conn) -> set[str]:
        for row in conn.execute("PRAGMA index_list('transactions')").fetchall():
            # row: (seq, name, unique, origin, partial) — origin 'u' means
            # the index backs a UNIQUE constraint (not a plain CREATE INDEX
            # or the PRIMARY KEY).
            if row[2] == 1 and row[3] == "u":
                index_name = row[1]
                return {r[2] for r in conn.execute(f"PRAGMA index_info('{index_name}')").fetchall()}
        return set()

    conn = sqlite3.connect(db_path)
    assert _unique_constraint_columns(conn) == {"folio_id", "date", "amount", "units", "type"}
    conn.close()

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0001"],
        cwd=BACKEND_DIR, capture_output=True, text=True,
    )
    assert downgrade.returncode == 0, downgrade.stderr

    conn = sqlite3.connect(db_path)
    assert _unique_constraint_columns(conn) == {"folio_id", "date", "amount", "units"}
    conn.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_migrations.py::test_transaction_dedupe_constraint_includes_type_after_upgrade -v`
Expected: FAIL — `alembic upgrade head` succeeds (migration 0001 alone still
runs), but the constraint only has 4 columns, so the first assertion fails.

- [ ] **Step 3: Create the migration**

```python
# backend/alembic/versions/0002_transaction_dedupe_includes_type.py
"""widen transaction dedupe key to include type

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-06

Real bug, not a preemptive hardening: a same-day purchase and redemption of
equal amount/units used to have opposite signs (a CAS-parser normalization
bug, since fixed at its own root cause) and couldn't collide on the old
4-column key. Once both were normalized to positive magnitudes, they could
— and the import pipeline would silently drop the second one as a false
duplicate. This migration widens the key to (folio_id, date, amount, units,
type) so type-distinct transactions are never conflated. No data
transformation — existing rows are untouched, this only changes what counts
as a duplicate going forward.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NEW_CONSTRAINT_NAME = "uq_transactions_folio_date_amount_units_type"
OLD_CONSTRAINT_NAME_FALLBACK = "uq_transactions_folio_date_amount_units"


def _sqlite_unique_constraint_name(conn) -> str | None:
    for row in conn.exec_driver_sql("PRAGMA index_list('transactions')").fetchall():
        # row: (seq, name, unique, origin, partial) — origin 'u' means this
        # index backs a UNIQUE constraint, not a plain index or the PK.
        if row[2] == 1 and row[3] == "u":
            return row[1]
    return None


def _postgres_unique_constraint_name(conn) -> str | None:
    result = conn.exec_driver_sql(
        """
        SELECT constraint_name FROM information_schema.table_constraints
        WHERE table_name = 'transactions' AND constraint_type = 'UNIQUE'
        """
    ).fetchall()
    return result[0][0] if result else None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _upgrade_postgres(bind)
    else:
        _upgrade_sqlite(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _downgrade_postgres()
    else:
        _downgrade_sqlite(bind)


def _upgrade_sqlite(bind) -> None:
    old_name = _sqlite_unique_constraint_name(bind)
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        if old_name:
            batch_op.drop_constraint(old_name, type_="unique")
        batch_op.create_unique_constraint(
            NEW_CONSTRAINT_NAME, ["folio_id", "date", "amount", "units", "type"]
        )


def _downgrade_sqlite(bind) -> None:
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.drop_constraint(NEW_CONSTRAINT_NAME, type_="unique")
        batch_op.create_unique_constraint(
            OLD_CONSTRAINT_NAME_FALLBACK, ["folio_id", "date", "amount", "units"]
        )


def _upgrade_postgres(bind) -> None:
    old_name = _postgres_unique_constraint_name(bind)
    if old_name:
        op.execute(f'ALTER TABLE transactions DROP CONSTRAINT "{old_name}"')
    op.execute(
        f"ALTER TABLE transactions ADD CONSTRAINT {NEW_CONSTRAINT_NAME} "
        "UNIQUE (folio_id, date, amount, units, type)"
    )


def _downgrade_postgres() -> None:
    op.execute(f"ALTER TABLE transactions DROP CONSTRAINT {NEW_CONSTRAINT_NAME}")
    op.execute(
        f"ALTER TABLE transactions ADD CONSTRAINT {OLD_CONSTRAINT_NAME_FALLBACK} "
        "UNIQUE (folio_id, date, amount, units)"
    )
```

Note: `sa` is imported but not directly referenced by name in this file's
final form (the batch/DDL operations use `op` and raw SQL strings) — leave
the import in place anyway, matching migration 0001's own top-of-file
import block exactly, for consistency with the established pattern in this
directory.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_migrations.py::test_transaction_dedupe_constraint_includes_type_after_upgrade -v`
Expected: PASS

- [ ] **Step 5: Run the full migration test file to confirm no regressions**

Run: `cd backend && .venv/bin/pytest tests/test_migrations.py -v`
Expected: All pass, including the pre-existing
`test_alembic_upgrade_and_downgrade_round_trip` (which now exercises both
migrations in sequence) and `test_alembic_upgrade_creates_all_tables`.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0002_transaction_dedupe_includes_type.py backend/tests/test_migrations.py
git commit -m "fix: widen transaction dedupe constraint to include type"
```

---

### Task 2: Widen `confirm_import`'s dedupe check

**Files:**
- Modify: `backend/app/services/import_/service.py`
- Test: `backend/tests/services/import_/test_service.py`

**Interfaces:**
- Consumes: nothing new — this task only widens two existing expressions in
  already-present code (`confirm_import`'s `dedupe_key` tuple and its
  matching `db.query(Transaction).filter_by(...)` lookup).
- Depends on: Task 1's migration must be applied for the DB-level
  constraint to actually enforce the same 5-column key this task's
  in-memory/query-level check now uses — if Task 1 hasn't run, this task's
  own tests (which use an in-memory SQLite DB built via
  `Base.metadata.create_all`, not via Alembic) still pass, since
  `Base.metadata` already reflects the ORM model's constraint definition
  independent of migration state. Task order in this plan is Task 1 then
  Task 2, but the two are not runtime-dependent on each other's migration
  having actually been applied to any given database — they agree by
  construction, not by sequencing.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/services/import_/test_service.py` (this file already
imports `NormalizedTransaction`, `ParsedInvestor`, `ParsedScheme`,
`ParseResult`, `TransactionType`, `date`, `Decimal`, `asyncio` — reuse them;
follow the exact pattern of the existing
`test_confirm_import_dedupes_same_key_transactions_within_one_upload`,
directly above where this new test should be added):

```python
def test_confirm_import_does_not_dedupe_across_different_transaction_types():
    """Regression test: before the redemption sign-normalization fix, a
    same-day purchase and redemption of equal amount/units had opposite
    signs and couldn't collide on the old 4-column dedupe key. After that
    fix normalized both to positive magnitudes, they could — and the
    second one would be silently dropped as a false duplicate. Both must
    now be inserted; only `type` distinguishes them here."""
    db = _session()
    member = _household_member(db)
    client = _mocked_client()

    txn1 = NormalizedTransaction(
        folio="123/45", amc="HDFC AMC", scheme_name="HDFC Flexi Cap Fund - Direct Plan - Growth",
        isin="INF123", amfi="125497", scheme_type="EQUITY", txn_date=date(2024, 1, 1),
        txn_type=TransactionType.PURCHASE, description="Purchase",
        amount=Decimal("5000.00"), units=Decimal("10.000"), nav=Decimal("500.0000"),
    )
    txn2 = NormalizedTransaction(
        folio="123/45", amc="HDFC AMC", scheme_name="HDFC Flexi Cap Fund - Direct Plan - Growth",
        isin="INF123", amfi="125497", scheme_type="EQUITY", txn_date=date(2024, 1, 1),
        txn_type=TransactionType.REDEMPTION, description="Same-day redemption, same amount/units",
        amount=Decimal("5000.00"), units=Decimal("10.000"), nav=Decimal("500.0000"),
    )
    scheme = ParsedScheme(
        name="HDFC Flexi Cap Fund - Direct Plan - Growth", isin="INF123", amfi="125497",
        scheme_type="EQUITY", folio="123/45", amc="HDFC AMC", transaction_count=2,
        arn_code=None, plan_name_variant="direct", plan_type="direct",
    )
    parse_result = ParseResult(
        investor=ParsedInvestor(name="Test Investor", email="t@example.com", pan_masked="ABCDE****F"),
        schemes=[scheme], transactions=[txn1, txn2], raw_json="{}",
        parse_warnings=[], cas_type="DETAILED", file_type="FileType.CAMS",
    )

    preview = asyncio.run(build_import_preview(parse_result, "test.pdf", client=client))
    result = confirm_import(db, preview.session_id, member.id, scheme_confirmations=[])

    assert result.added == 2
    assert result.skipped == 0
    assert db.query(Transaction).count() == 2
    types = {t.type for t in db.query(Transaction).all()}
    assert types == {TransactionType.PURCHASE, TransactionType.REDEMPTION}
```

Note: the pre-existing `test_confirm_import_deduped_on_reupload` test
(same file, already passing) already covers "a genuine re-upload — same
type, same everything, both times — is still correctly deduped." It
doesn't need a new test; once this task's code change lands, that existing
test continues to prove the widened key didn't break real-duplicate
detection, since it never varies `type` between its two confirm calls.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/services/import_/test_service.py::test_confirm_import_does_not_dedupe_across_different_transaction_types -v`
Expected: FAIL — `result.added == 1` and `result.skipped == 1` (the
redemption is currently, incorrectly, deduped against the purchase).

- [ ] **Step 3: Widen the dedupe check in `service.py`**

In `backend/app/services/import_/service.py`, inside `confirm_import`,
change:

```python
        dedupe_key = (folio.id, norm.txn_date, norm.amount, norm.units)
```

to:

```python
        dedupe_key = (folio.id, norm.txn_date, norm.amount, norm.units, norm.txn_type)
```

And change:

```python
        dup = (
            db.query(Transaction)
            .filter_by(folio_id=folio.id, date=norm.txn_date, amount=norm.amount, units=norm.units)
            .first()
        )
```

to:

```python
        dup = (
            db.query(Transaction)
            .filter_by(folio_id=folio.id, date=norm.txn_date, amount=norm.amount, units=norm.units, type=norm.txn_type)
            .first()
        )
```

No other change — the surrounding logic (the `added_keys` in-memory set,
the reason both checks exist, per the existing comment above this code)
stays exactly as-is.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/services/import_/test_service.py::test_confirm_import_does_not_dedupe_across_different_transaction_types -v`
Expected: PASS

- [ ] **Step 5: Run the full service test file to confirm no regressions**

Run: `cd backend && .venv/bin/pytest tests/services/import_/test_service.py -v`
Expected: All pass, including
`test_confirm_import_deduped_on_reupload` and
`test_confirm_import_dedupes_same_key_transactions_within_one_upload`
(both use the same `type` on every transaction they construct, so the
widened key doesn't change their outcome).

- [ ] **Step 6: Run the full backend test suite**

Run: `cd backend && .venv/bin/pytest -m "not postgres" -v`
Expected: All pass (140 pre-existing + this plan's 2 new tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/import_/service.py backend/tests/services/import_/test_service.py
git commit -m "fix: include transaction type in confirm_import's dedupe check"
```

---

## Self-Review Notes (completed during plan authoring)

**Spec coverage:** both spec requirements are covered — Task 1 is the
migration (both dialects, dynamic constraint-name lookup, no guessing),
Task 2 is the `service.py` widening. The spec's third testing requirement
("a genuine re-upload is still correctly deduped") is satisfied by an
already-existing, already-passing test (`test_confirm_import_deduped_on_reupload`)
rather than a new one — noted explicitly in Task 2 rather than duplicating
coverage that already exists.

**Placeholder scan:** no TBD/TODO. The migration file's `sa` import being
unused-by-name is called out explicitly with its rationale (matching
migration 0001's own import block), not left as an unexplained oddity.

**Type consistency:** `NEW_CONSTRAINT_NAME`/`OLD_CONSTRAINT_NAME_FALLBACK`
are defined once and reused identically across `_upgrade_sqlite`,
`_downgrade_sqlite`, `_upgrade_postgres`, `_downgrade_postgres` — no risk
of the upgrade and downgrade paths drifting to different literal strings.
`dedupe_key`'s 5-tuple shape and the `filter_by`'s five keyword arguments
in Task 2 both add exactly `type=norm.txn_type` to what was already there
— no mismatch between the two.

**Scope check:** two tasks, tightly coupled (the migration and the app
code must land together per the spec's own "together" requirement), sized
appropriately as one small plan — no further decomposition needed.
