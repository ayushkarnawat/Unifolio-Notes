# PAN Persistence, CAS File Storage & PAN-Based Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the real PAN (encrypted) and the raw CAS file (30-day retention) per import, and rewrite the household-member attribution engine to match by PAN instead of name/email.

**Architecture:** Two new, independently-testable modules (`crypto.py` for envelope encryption + lookup hashing, `file_storage.py` for a swappable local/S3 file backend) plug into a rewritten `attribution.py` that matches by a PAN hash first, folio-number second, and blocks cross-account PAN reuse outright. Both existing import pipelines (`service.py`'s sync confirm path and `lifecycle_service.py`'s async path) call the same shared attribution/backfill/file-save logic.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, `cryptography` (already a dependency, `cryptography==50.0.0`), pytest.

**Spec:** `Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md`

## Global Constraints

- No raw PAN is ever returned by any API response — only `pan_masked`, exactly as today. (Spec §"Explicitly out of scope.")
- No raw PAN is ever logged, or included in `raw_parser_output` or any exception message. (Spec, carrying forward the existing `parser.py` invariant.)
- The stored CAS file is retained for exactly 30 days from upload, then deleted. (Spec §"Scope.")
- `EnvVarKeyProvider` and `LocalFileStorage` are explicit dev/demo stand-ins for production Secrets-Manager/S3 equivalents — built behind interfaces so the swap doesn't touch calling code. (Spec §"Production mapping.")
- Name and email are never read by attribution matching after this change — they remain display-only fields. (Spec §"Attribution algorithm.")

---

## Task 1: Migration + ORM model changes

**Files:**
- Create: `backend/alembic/versions/0015_pan_and_cas_file_storage.py`
- Modify: `backend/app/models/user.py` (add columns to `HouseholdMember`)
- Modify: `backend/app/models/imports.py` (add columns to `Import`)
- Test: `backend/tests/models/test_no_pan_field.py` (rewritten in Task 10, not here — this task only needs the migration to apply cleanly)

**Interfaces:**
- Produces: `HouseholdMember.pan_encrypted: str | None`, `HouseholdMember.pan_lookup_hash: str | None` (indexed); `Import.file_reference: str | None`, `Import.file_expires_at: datetime | None`.

- [ ] **Step 1: Write the migration**

```python
"""pan persistence and cas file storage

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("household_members", sa.Column("pan_encrypted", sa.Text(), nullable=True))
    op.add_column("household_members", sa.Column("pan_lookup_hash", sa.Text(), nullable=True))
    op.create_index(
        "ix_household_members_pan_lookup_hash",
        "household_members",
        ["pan_lookup_hash"],
    )
    op.add_column("imports", sa.Column("file_reference", sa.Text(), nullable=True))
    op.add_column("imports", sa.Column("file_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("imports", "file_expires_at")
    op.drop_column("imports", "file_reference")
    op.drop_index("ix_household_members_pan_lookup_hash", table_name="household_members")
    op.drop_column("household_members", "pan_lookup_hash")
    op.drop_column("household_members", "pan_encrypted")
```

- [ ] **Step 2: Update `HouseholdMember`**

In `backend/app/models/user.py`, add to the imports line `from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Uuid` → add `Index` is already there; add nothing new to imports. Modify the `HouseholdMember` class (currently lines 27-35):

```python
class HouseholdMember(Base):
    __tablename__ = "household_members"
    __table_args__ = (Index("ix_household_members_pan_lookup_hash", "pan_lookup_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    relationship: Mapped[Relationship] = mapped_column(enum_column(Relationship), nullable=False)
    relationship_other_label: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pan_encrypted: Mapped[str | None] = mapped_column(String)
    pan_lookup_hash: Mapped[str | None] = mapped_column(String)
```

(The `__table_args__` index here is declarative metadata only — the migration in Step 1 is what actually creates it in the DB. Both must name the index identically, `ix_household_members_pan_lookup_hash`, or `alembic check`/autogenerate will see drift.)

- [ ] **Step 3: Update `Import`**

In `backend/app/models/imports.py`, add two lines after `expires_at` (currently line 30):

```python
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_reference: Mapped[str | None] = mapped_column(String)
    file_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 4: Run the migration against the dev DB and verify**

Run: `cd backend && alembic upgrade head`
Expected: applies `0015` cleanly with no errors.

Run: `cd backend && alembic downgrade -1 && alembic upgrade head`
Expected: downgrade then upgrade both succeed (round-trip check).

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0015_pan_and_cas_file_storage.py backend/app/models/user.py backend/app/models/imports.py
git commit -m "feat(import): add pan_encrypted/pan_lookup_hash and file_reference/file_expires_at columns"
```

---

## Task 2: `crypto.py` — envelope encryption + lookup hash

**Files:**
- Create: `backend/app/services/import_/crypto.py`
- Modify: `backend/app/config.py` (add `pan_encryption_key`, `pan_lookup_pepper` settings)
- Modify: `backend/.env.example` (document the two new vars)
- Test: `backend/tests/services/import_/test_crypto.py`

**Interfaces:**
- Produces: `normalize_pan(pan: str) -> str`, `encrypt_pan(pan: str, key_provider: KeyProvider = default_key_provider) -> str`, `decrypt_pan(pan_encrypted: str, key_provider: KeyProvider = default_key_provider) -> str`, `hash_pan(pan: str, key_provider: KeyProvider = default_key_provider) -> str`, `class KeyProvider(Protocol)`, `class EnvVarKeyProvider`, `default_key_provider: EnvVarKeyProvider`.

- [ ] **Step 1: Add settings**

In `backend/app/config.py`, add after `allowed_origins: str = ""`:

```python
    # PAN encryption (ADR-004 reopened 2026-09-18). Dev/demo key source —
    # production maps this to a Secrets Manager secret encrypted by the
    # already-staged KMS key (infra/modules/security), injected the same
    # way the RDS password already is. See
    # Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md.
    pan_encryption_key: str = ""
    pan_lookup_pepper: str = ""
    cas_file_storage_dir: str = "var/cas_files"
```

- [ ] **Step 2: Add env vars to `.env.example`**

Append to `backend/.env.example`:

```
PAN_ENCRYPTION_KEY=
PAN_LOOKUP_PEPPER=
CAS_FILE_STORAGE_DIR=var/cas_files
```

- [ ] **Step 3: Generate local dev key values**

Run: `python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"`
Run it twice, and put the two different 32-byte base64 values into your local `backend/.env` (not `.env.example`, which stays blank) as `PAN_ENCRYPTION_KEY` and `PAN_LOOKUP_PEPPER`.

- [ ] **Step 4: Write the failing tests**

Create `backend/tests/services/import_/test_crypto.py`:

```python
import base64
import os

import pytest

from app.services.import_.crypto import (
    EnvVarKeyProvider,
    decrypt_pan,
    encrypt_pan,
    hash_pan,
    normalize_pan,
)


class FixedKeyProvider:
    def __init__(self, key: bytes, pepper: bytes):
        self._key = key
        self._pepper = pepper

    def encryption_key(self) -> bytes:
        return self._key

    def lookup_pepper(self) -> bytes:
        return self._pepper


@pytest.fixture
def key_provider():
    return FixedKeyProvider(os.urandom(32), os.urandom(32))


def test_normalize_pan_strips_whitespace_and_uppercases():
    assert normalize_pan(" abcde1234f ") == "ABCDE1234F"
    assert normalize_pan("ABCDE1234F") == "ABCDE1234F"


def test_encrypt_then_decrypt_round_trips(key_provider):
    ciphertext = encrypt_pan("ABCDE1234F", key_provider)
    assert decrypt_pan(ciphertext, key_provider) == "ABCDE1234F"


def test_encryption_is_nondeterministic(key_provider):
    first = encrypt_pan("ABCDE1234F", key_provider)
    second = encrypt_pan("ABCDE1234F", key_provider)
    assert first != second


def test_decrypt_with_wrong_key_raises(key_provider):
    ciphertext = encrypt_pan("ABCDE1234F", key_provider)
    wrong_provider = FixedKeyProvider(os.urandom(32), key_provider.lookup_pepper())
    with pytest.raises(Exception):
        decrypt_pan(ciphertext, wrong_provider)


def test_hash_pan_is_deterministic(key_provider):
    assert hash_pan("ABCDE1234F", key_provider) == hash_pan("abcde1234f", key_provider)


def test_hash_pan_differs_for_different_pans(key_provider):
    assert hash_pan("ABCDE1234F", key_provider) != hash_pan("ZYXWV9876G", key_provider)


def test_env_var_key_provider_rejects_missing_key(monkeypatch):
    monkeypatch.setattr("app.services.import_.crypto.settings.pan_encryption_key", "")
    with pytest.raises(RuntimeError, match="PAN_ENCRYPTION_KEY"):
        EnvVarKeyProvider().encryption_key()


def test_env_var_key_provider_rejects_wrong_length_key(monkeypatch):
    short_key = base64.b64encode(b"too-short").decode()
    monkeypatch.setattr("app.services.import_.crypto.settings.pan_encryption_key", short_key)
    with pytest.raises(RuntimeError, match="32 bytes"):
        EnvVarKeyProvider().encryption_key()
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd backend && pytest tests/services/import_/test_crypto.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.import_.crypto'`

- [ ] **Step 6: Implement `crypto.py`**

Create `backend/app/services/import_/crypto.py`:

```python
"""Envelope encryption and deterministic lookup hashing for PAN persistence.

ADR-004 reopened 2026-09-18: PAN is now persisted, encrypted, recoverable.
Matching uses pan_lookup_hash (an HMAC, never reversible) so the app never
needs to decrypt another household's PAN just to check for a match. See
Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


class KeyProvider(Protocol):
    def encryption_key(self) -> bytes: ...
    def lookup_pepper(self) -> bytes: ...


def _decode_key(value: str, var_name: str) -> bytes:
    if not value:
        raise RuntimeError(f"{var_name} is not set.")
    key = base64.b64decode(value)
    if len(key) != 32:
        raise RuntimeError(f"{var_name} must decode to 32 bytes, got {len(key)}.")
    return key


class EnvVarKeyProvider:
    """Local/demo key source. Production maps this to a Secrets Manager
    secret encrypted by the KMS key already staged in infra/modules/security
    — swap the provider, not the callers (see design spec's "Production
    mapping")."""

    def encryption_key(self) -> bytes:
        return _decode_key(settings.pan_encryption_key, "PAN_ENCRYPTION_KEY")

    def lookup_pepper(self) -> bytes:
        return _decode_key(settings.pan_lookup_pepper, "PAN_LOOKUP_PEPPER")


default_key_provider = EnvVarKeyProvider()


def normalize_pan(pan: str) -> str:
    return "".join(pan.split()).upper()


def encrypt_pan(pan: str, key_provider: KeyProvider = default_key_provider) -> str:
    aesgcm = AESGCM(key_provider.encryption_key())
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, normalize_pan(pan).encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_pan(pan_encrypted: str, key_provider: KeyProvider = default_key_provider) -> str:
    raw = base64.b64decode(pan_encrypted)
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(key_provider.encryption_key())
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


def hash_pan(pan: str, key_provider: KeyProvider = default_key_provider) -> str:
    digest = hmac.new(
        key_provider.lookup_pepper(),
        normalize_pan(pan).encode("utf-8"),
        hashlib.sha256,
    )
    return digest.hexdigest()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && pytest tests/services/import_/test_crypto.py -v`
Expected: PASS (9 tests)

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/import_/crypto.py backend/app/config.py backend/.env.example backend/tests/services/import_/test_crypto.py
git commit -m "feat(import): add PAN envelope encryption and lookup-hash module"
```

---

## Task 3: `file_storage.py` — swappable CAS file retention

**Files:**
- Create: `backend/app/services/import_/file_storage.py`
- Test: `backend/tests/services/import_/test_file_storage.py`

**Interfaces:**
- Consumes: `app.models.imports.Import` (for `expire_stored_files`).
- Produces: `class FileStorage(Protocol)`, `class LocalFileStorage`, `default_file_storage: LocalFileStorage`, `storage_key_for_import(user_id, import_id) -> str`, `store_cas_file(import_rec, user_id, pdf_bytes, storage=default_file_storage) -> None` (sets `import_rec.file_reference`/`file_expires_at`), `expire_stored_files(db, storage=default_file_storage) -> int`, `CAS_FILE_RETENTION_DAYS = 30`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/import_/test_file_storage.py`:

```python
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import ImportStatus
from app.models.imports import Import
from app.services.import_.file_storage import (
    CAS_FILE_RETENTION_DAYS,
    LocalFileStorage,
    expire_stored_files,
    storage_key_for_import,
    store_cas_file,
)


@pytest.fixture
def storage(tmp_path):
    return LocalFileStorage(base_dir=str(tmp_path))


def test_storage_key_is_scoped_by_user_and_import():
    user_id = uuid.uuid4()
    import_id = uuid.uuid4()
    key = storage_key_for_import(user_id, import_id)
    assert key == f"{user_id}/{import_id}.pdf"


def test_save_then_read_round_trips_bytes(storage):
    key = storage.save("some/key.pdf", b"%PDF-1.4 fake bytes")
    assert storage.read(key) == b"%PDF-1.4 fake bytes"


def test_delete_is_idempotent(storage):
    key = storage.save("a/b.pdf", b"data")
    storage.delete(key)
    storage.delete(key)  # must not raise


def test_store_cas_file_sets_reference_and_expiry(storage):
    import_rec = Import(
        id=uuid.uuid4(),
        household_member_id=uuid.uuid4(),
        status=ImportStatus.PROCESSING,
        uploaded_at=datetime.now(timezone.utc),
    )
    user_id = uuid.uuid4()
    store_cas_file(import_rec, user_id, b"%PDF-1.4 fake bytes", storage=storage)

    assert import_rec.file_reference == f"{user_id}/{import_rec.id}.pdf"
    assert storage.read(import_rec.file_reference) == b"%PDF-1.4 fake bytes"
    expected_expiry = datetime.now(timezone.utc) + timedelta(days=CAS_FILE_RETENTION_DAYS)
    assert abs((import_rec.file_expires_at - expected_expiry).total_seconds()) < 5


def test_expire_stored_files_deletes_only_past_expiry_rows(db_session, storage):
    now = datetime.now(timezone.utc)
    expired = Import(
        id=uuid.uuid4(), household_member_id=uuid.uuid4(), status=ImportStatus.IMPORT_SUCCESSFUL,
        uploaded_at=now, file_reference="expired/file.pdf", file_expires_at=now - timedelta(days=1),
    )
    not_expired = Import(
        id=uuid.uuid4(), household_member_id=uuid.uuid4(), status=ImportStatus.IMPORT_SUCCESSFUL,
        uploaded_at=now, file_reference="fresh/file.pdf", file_expires_at=now + timedelta(days=29),
    )
    storage.save("expired/file.pdf", b"old")
    storage.save("fresh/file.pdf", b"new")
    db_session.add_all([expired, not_expired])
    db_session.commit()

    deleted_count = expire_stored_files(db_session, storage=storage)

    assert deleted_count == 1
    db_session.refresh(expired)
    db_session.refresh(not_expired)
    assert expired.file_reference is None
    assert expired.file_expires_at is None
    assert not_expired.file_reference == "fresh/file.pdf"
    with pytest.raises(FileNotFoundError):
        storage.read("expired/file.pdf")
    assert storage.read("fresh/file.pdf") == b"new"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/services/import_/test_file_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.import_.file_storage'`

- [ ] **Step 3: Implement `file_storage.py`**

Create `backend/app/services/import_/file_storage.py`:

```python
"""Local-disk CAS file retention (30-day window) for dispute/re-parse support.

ADR-004 reopened 2026-09-18: the source CAS PDF is now retained for a bounded
window instead of always being discarded immediately after parsing. This
module is deliberately swappable — LocalFileStorage is the dev/demo backend;
production maps this same protocol onto S3 + a Lifecycle rule (see design
spec's "Production mapping") without changing any caller. This is separate
from, and does not change, the existing temp-file-delete-immediately-after-
parse behavior in parser.py (that temp file only ever exists to hand
casparser a filesystem path) — this module's copy is the new, deliberate
30-day retention.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from app.config import settings
from app.models.imports import Import

CAS_FILE_RETENTION_DAYS = 30


class FileStorage(Protocol):
    def save(self, key: str, data: bytes) -> str: ...
    def read(self, reference: str) -> bytes: ...
    def delete(self, reference: str) -> None: ...


class LocalFileStorage:
    def __init__(self, base_dir: str | None = None):
        self._base_dir = Path(base_dir if base_dir is not None else settings.cas_file_storage_dir)

    def save(self, key: str, data: bytes) -> str:
        path = self._base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, reference: str) -> bytes:
        return (self._base_dir / reference).read_bytes()

    def delete(self, reference: str) -> None:
        (self._base_dir / reference).unlink(missing_ok=True)


default_file_storage = LocalFileStorage()


def storage_key_for_import(user_id: uuid.UUID, import_id: uuid.UUID) -> str:
    return f"{user_id}/{import_id}.pdf"


def store_cas_file(
    import_rec: Import,
    user_id: uuid.UUID,
    pdf_bytes: bytes,
    storage: FileStorage = default_file_storage,
) -> None:
    key = storage_key_for_import(user_id, import_rec.id)
    import_rec.file_reference = storage.save(key, pdf_bytes)
    import_rec.file_expires_at = datetime.now(timezone.utc) + timedelta(days=CAS_FILE_RETENTION_DAYS)


def expire_stored_files(db: Session, storage: FileStorage = default_file_storage) -> int:
    now = datetime.now(timezone.utc)
    expired = (
        db.query(Import)
        .filter(Import.file_reference.isnot(None), Import.file_expires_at < now)
        .all()
    )
    for import_rec in expired:
        storage.delete(import_rec.file_reference)
        import_rec.file_reference = None
        import_rec.file_expires_at = None
    if expired:
        db.commit()
    return len(expired)
```

- [ ] **Step 4: Add `var/` to `.gitignore`**

Add a line to `backend/.gitignore` (create the file if it doesn't exist): `var/cas_files/`

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/services/import_/test_file_storage.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/import_/file_storage.py backend/tests/services/import_/test_file_storage.py backend/.gitignore
git commit -m "feat(import): add local CAS file storage with 30-day expiry"
```

---

## Task 4: `parser.py` — carry the raw PAN through `ParseResult` (still never persisted verbatim)

**Files:**
- Modify: `backend/app/services/import_/parser.py:121-125` (`ParsedInvestor`), `:182-188` (`_normalize_cas_data`)
- Test: `backend/tests/services/import_/test_parser.py` (add one test; check the file exists first — if not, add to whichever existing parser test file covers `_normalize_cas_data`)

**Interfaces:**
- Produces: `ParsedInvestor.pan: str | None` (new field, default `None`, keyword-compatible with every existing call site — confirmed no positional `ParsedInvestor(...)` calls exist in the codebase).

- [ ] **Step 1: Find the existing parser test file**

Run: `cd backend && find tests -iname "*parser*"`
Use whatever file that finds; if none exists, create `backend/tests/services/import_/test_parser.py` with a `from app.services.import_.parser import ...` import block matching the style of `test_attribution.py`.

- [ ] **Step 2: Write the failing test**

Add to that file:

```python
def test_normalize_cas_data_carries_raw_pan_alongside_masked():
    from app.services.import_.parser import _normalize_cas_data
    from casparser.types import CASData

    # Build the minimal CASData shape _normalize_cas_data reads from.
    # (If a fixture/helper already builds CASData in this test file, reuse
    # it and just assert on investor.pan / investor.pan_masked below —
    # do not duplicate fixture-building code.)
    ...
    result = _normalize_cas_data(data)
    assert result.investor.pan == "ABCDE1234F"
    assert result.investor.pan_masked == "A*********F"
```

(If this test file has no existing `CASData`-building helper to reuse, skip writing this as a new standalone test and instead add the two assertion lines above to whichever existing test in this file already exercises `_normalize_cas_data` with a real `CASData` fixture — do not hand-construct casparser's `CASData` from scratch here.)

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && pytest tests/services/import_/test_parser.py -v -k pan`
Expected: FAIL — `AttributeError: 'ParsedInvestor' object has no attribute 'pan'`

- [ ] **Step 4: Implement**

In `backend/app/services/import_/parser.py`, modify `ParsedInvestor` (lines 121-125):

```python
@dataclass
class ParsedInvestor:
    name: str | None
    email: str | None
    pan_masked: str | None
    pan: str | None = None
```

Modify `_normalize_cas_data` (lines 182-188):

```python
    investor_info = data.investor_info
    pan = data.folios[0].PAN if data.folios and data.folios[0].PAN else None
    investor = ParsedInvestor(
        name=investor_info.name if investor_info else None,
        email=investor_info.email if investor_info else None,
        pan_masked=mask_pan(pan),
        pan=pan,
    )
```

The existing redaction block (lines 239-245, `redacted = data.model_copy(deep=True)` ... `f.PAN = None`) is untouched — it redacts a *separate deep copy* used only for `raw_json`, so `investor.pan` on the returned `ParseResult` is unaffected by it and still carries the real value in memory for this request only.

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && pytest tests/services/import_/test_parser.py -v -k pan`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/import_/parser.py backend/tests/services/import_/test_parser.py
git commit -m "feat(import): carry raw PAN on ParsedInvestor for attribution matching"
```

---

## Task 5: Rewrite `attribution.py` — PAN-hash matching, cross-account block, backfill

**Files:**
- Modify: `backend/app/services/import_/attribution.py` (full rewrite)
- Test: `backend/tests/services/import_/test_attribution.py` (full rewrite)

**Interfaces:**
- Consumes: `app.services.import_.crypto.hash_pan`, `encrypt_pan`; `ParseResult.investor.pan`.
- Produces: `AttributionStatus` (now `AUTO_MATCHED`, `MISMATCH_CONFIRMATION_REQUIRED`, `UNRECOGNIZED_MEMBER` — `MULTI_MEMBER_CONFIRMATION_REQUIRED` removed, it was unused dead code in the original), `AttributionDecision` (adds `matched_by_pan: bool = False`), `resolve_attribution(db, user_id, selected_member_id, parse_result) -> AttributionDecision` (now raises `CrossAccountPanBlockedError`), `backfill_pan_if_missing(db, member, parse_result) -> None`, `CrossAccountPanBlockedError`, `CROSS_ACCOUNT_PAN_BLOCKED_MESSAGE`. **Removed:** `detect_cross_account_duplicate`, `CrossAccountDuplicateWarning`, `CROSS_ACCOUNT_DUPLICATE_WARNING` (folded into the PAN-hash check in `resolve_attribution`).

- [ ] **Step 1: Write the new failing tests (full replacement of the file)**

Replace `backend/tests/services/import_/test_attribution.py` entirely:

```python
from datetime import datetime, timezone
import uuid

import pytest

from app.models.enums import Relationship
from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.user import HouseholdMember, User
from app.services.import_.attribution import (
    AttributionConfirmationRequiredError,
    AttributionDecision,
    AttributionStatus,
    CrossAccountPanBlockedError,
    backfill_pan_if_missing,
    enforce_attribution_confirmation,
    resolve_attribution,
)
from app.services.import_.crypto import encrypt_pan, hash_pan
from app.services.import_.parser import ParsedInvestor, ParsedScheme, ParseResult


def _parse_result(*, pan: str | None = None, folio: str | None = None, amc: str | None = None) -> ParseResult:
    schemes = (
        [ParsedScheme(name="Test Fund", isin=None, amfi="123456", scheme_type="Equity", folio=folio, amc=amc, transaction_count=0)]
        if folio and amc
        else []
    )
    return ParseResult(
        investor=ParsedInvestor(name="Some Investor", email=None, pan_masked=None, pan=pan),
        schemes=schemes,
        transactions=[],
        raw_json="{}",
    )


def _existing_folio(db_session, member: HouseholdMember, *, folio: str, amc: str) -> None:
    scheme = Scheme(id=uuid.uuid4(), amfi_code=uuid.uuid4().hex, name="Existing Fund", amc_name=amc, sebi_category="Equity")
    db_session.add(scheme)
    db_session.flush()
    from app.models.enums import PlanType
    db_session.add(Folio(id=uuid.uuid4(), household_member_id=member.id, scheme_id=scheme.id, folio_number=folio, plan_type=PlanType.DIRECT))
    db_session.commit()


def _user_with_member(db_session, *, name: str, pan: str | None = None) -> tuple[User, HouseholdMember]:
    now = datetime.now(timezone.utc)
    user = User(id=uuid.uuid4(), phone_number=f"+91{uuid.uuid4().int % 10_000_000_000:010d}", created_at=now)
    member = HouseholdMember(
        id=uuid.uuid4(), user_id=user.id, name=name, relationship=Relationship.SELF, created_at=now,
        pan_encrypted=encrypt_pan(pan) if pan else None,
        pan_lookup_hash=hash_pan(pan) if pan else None,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(member)
    db_session.commit()
    return user, member


@pytest.fixture
def household_setup(db_session):
    now = datetime.now(timezone.utc)
    user = User(id=uuid.uuid4(), phone_number="+919876543210", email="rajesh.kumar@example.com", created_at=now)
    db_session.add(user)
    db_session.flush()

    member_self = HouseholdMember(
        id=uuid.uuid4(), user_id=user.id, name="Rajesh Kumar", relationship=Relationship.SELF, created_at=now,
        pan_encrypted=encrypt_pan("ABCDE1111A"), pan_lookup_hash=hash_pan("ABCDE1111A"),
    )
    member_spouse = HouseholdMember(
        id=uuid.uuid4(), user_id=user.id, name="Priya Kumar", relationship=Relationship.SPOUSE, created_at=now,
        pan_encrypted=encrypt_pan("BCDEF2222B"), pan_lookup_hash=hash_pan("BCDEF2222B"),
    )
    member_child_no_pan = HouseholdMember(
        id=uuid.uuid4(), user_id=user.id, name="Aarav Kumar", relationship=Relationship.CHILD, created_at=now,
    )
    db_session.add_all([member_self, member_spouse, member_child_no_pan])
    db_session.commit()
    return {"user": user, "self": member_self, "spouse": member_spouse, "child": member_child_no_pan}


def test_pan_match_within_household_auto_attributes_with_disclaimer(db_session, household_setup):
    decision = resolve_attribution(
        db=db_session, user_id=household_setup["user"].id,
        selected_member_id=household_setup["self"].id,
        parse_result=_parse_result(pan="BCDEF2222B"),
    )
    assert decision.status == AttributionStatus.AUTO_MATCHED
    assert decision.resolved_member_id == household_setup["spouse"].id
    assert decision.requires_confirmation is False
    assert decision.matched_by_pan is True
    assert "Priya Kumar" in decision.prompt_message


def test_pan_match_to_different_account_is_blocked(db_session, household_setup):
    _user_with_member(db_session, name="Someone Else", pan="ZZZZZ9999Z")

    with pytest.raises(CrossAccountPanBlockedError):
        resolve_attribution(
            db=db_session, user_id=household_setup["user"].id,
            selected_member_id=household_setup["self"].id,
            parse_result=_parse_result(pan="ZZZZZ9999Z"),
        )


def test_no_pan_parsed_falls_back_to_folio_match(db_session, household_setup):
    _existing_folio(db_session, household_setup["spouse"], folio="12345/67", amc="ICICI Prudential Mutual Fund")

    decision = resolve_attribution(
        db=db_session, user_id=household_setup["user"].id,
        selected_member_id=household_setup["self"].id,
        parse_result=_parse_result(pan=None, folio="12345/67", amc="ICICI Prudential Mutual Fund"),
    )
    assert decision.status == AttributionStatus.MISMATCH_CONFIRMATION_REQUIRED
    assert decision.resolved_member_id == household_setup["spouse"].id


def test_no_pan_and_no_folio_match_prompts_unrecognized_member(db_session, household_setup):
    decision = resolve_attribution(
        db=db_session, user_id=household_setup["user"].id,
        selected_member_id=household_setup["self"].id,
        parse_result=_parse_result(pan=None),
    )
    assert decision.status == AttributionStatus.UNRECOGNIZED_MEMBER
    assert decision.resolved_member_id is None


def test_name_on_the_cas_never_affects_matching(db_session, household_setup):
    # Investor name is "Some Investor" (see _parse_result) -- matches no
    # household member's name at all, but the PAN belongs to "self".
    decision = resolve_attribution(
        db=db_session, user_id=household_setup["user"].id,
        selected_member_id=household_setup["spouse"].id,
        parse_result=_parse_result(pan="ABCDE1111A"),
    )
    assert decision.status == AttributionStatus.AUTO_MATCHED
    assert decision.resolved_member_id == household_setup["self"].id


def test_backfill_stores_pan_on_first_successful_match(db_session, household_setup):
    member = household_setup["child"]
    assert member.pan_lookup_hash is None

    backfill_pan_if_missing(db_session, member, _parse_result(pan="CDEFG3333C"))

    assert member.pan_lookup_hash == hash_pan("CDEFG3333C")
    from app.services.import_.crypto import decrypt_pan
    assert decrypt_pan(member.pan_encrypted) == "CDEFG3333C"


def test_backfill_does_not_overwrite_an_existing_pan(db_session, household_setup):
    member = household_setup["self"]
    original_hash = member.pan_lookup_hash

    backfill_pan_if_missing(db_session, member, _parse_result(pan="DIFFERENT99Z"))

    assert member.pan_lookup_hash == original_hash


def test_backfill_no_ops_when_cas_has_no_pan(db_session, household_setup):
    member = household_setup["child"]
    backfill_pan_if_missing(db_session, member, _parse_result(pan=None))
    assert member.pan_lookup_hash is None
    assert member.pan_encrypted is None


def test_attribution_confirmation_gate_requires_an_explicit_override():
    decision = AttributionDecision(
        status=AttributionStatus.MISMATCH_CONFIRMATION_REQUIRED, resolved_member_id=uuid.uuid4(),
        matched_member_name="Priya Kumar", requires_confirmation=True, prompt_message="Confirm this member mismatch.",
    )
    with pytest.raises(AttributionConfirmationRequiredError, match="Confirm this member mismatch."):
        enforce_attribution_confirmation(decision, confirmed_override=False)


def test_attribution_confirmation_gate_allows_an_explicit_override():
    decision = AttributionDecision(
        status=AttributionStatus.UNRECOGNIZED_MEMBER, resolved_member_id=None,
        matched_member_name="Unknown Investor", requires_confirmation=True, prompt_message="Confirm this unmatched investor.",
    )
    enforce_attribution_confirmation(decision, confirmed_override=True)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/services/import_/test_attribution.py -v`
Expected: FAIL (import errors — `CrossAccountPanBlockedError`, `backfill_pan_if_missing` don't exist yet; old tests referencing name-matching are gone)

- [ ] **Step 3: Rewrite `attribution.py`**

Replace `backend/app/services/import_/attribution.py` entirely:

```python
"""Family Member Attribution Engine — PAN-based (ADR-004 reopened 2026-09-18).

Matches an imported CAS to a household member by PAN, not name/email:
- PAN match to a member of the SAME household -> auto-attributed, disclaimer shown.
- PAN match to a member of a DIFFERENT account -> blocked outright, no override
  (CrossAccountPanBlockedError) -- see Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md.
- No PAN parsed -> falls back to folio-number+AMC reuse (unchanged from before).
- No match anywhere -> unrecognized member prompt (add new member).
Name is display-only from here on -- it is never read for matching.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.folio import Folio
from app.models.reference import Scheme
from app.models.user import HouseholdMember
from app.services.import_.crypto import encrypt_pan, hash_pan
from app.services.import_.parser import ParseResult


class AttributionStatus(str, enum.Enum):
    AUTO_MATCHED = "auto_matched"
    MISMATCH_CONFIRMATION_REQUIRED = "mismatch_confirmation_required"
    UNRECOGNIZED_MEMBER = "unrecognized_member"


@dataclass
class AttributionDecision:
    status: AttributionStatus
    resolved_member_id: uuid.UUID | None
    matched_member_name: str | None
    requires_confirmation: bool
    prompt_message: str | None = None
    candidate_members: list[dict[str, Any]] = field(default_factory=list)
    matched_by_pan: bool = False


class AttributionConfirmationRequiredError(Exception):
    """Raised when attribution needs an explicit user confirmation."""

    def __init__(self, attribution: AttributionDecision):
        self.attribution = attribution
        super().__init__(attribution.prompt_message or "Confirm which family member this statement belongs to.")


class CrossAccountPanBlockedError(Exception):
    """Raised when the parsed CAS's PAN already belongs to a member of a
    different Unifolio account. This is a hard stop, not a confirmable
    decision -- there is no self-serve override or merge path (see design
    spec's "Scope decisions")."""


CROSS_ACCOUNT_PAN_BLOCKED_MESSAGE = (
    "This PAN is already tracked under a different Unifolio account. "
    "Contact support if you believe this is a mistake."
)


def enforce_attribution_confirmation(attribution: AttributionDecision, confirmed_override: bool) -> None:
    if attribution.requires_confirmation and not confirmed_override:
        raise AttributionConfirmationRequiredError(attribution)


def _find_member_by_pan_hash(db: Session, pan_hash: str) -> HouseholdMember | None:
    return db.query(HouseholdMember).filter(HouseholdMember.pan_lookup_hash == pan_hash).first()


def _find_folio_matched_member(
    db: Session, members: list[HouseholdMember], parse_result: ParseResult
) -> tuple[HouseholdMember | None, tuple[str, str] | None]:
    parsed_folio_keys = {(s.folio, s.amc) for s in parse_result.schemes if s.folio and s.amc}
    if not parsed_folio_keys or not members:
        return None, None
    try:
        with db.begin_nested():
            existing_folios = (
                db.query(Folio.household_member_id, Folio.folio_number, Scheme.amc_name)
                .join(Scheme, Folio.scheme_id == Scheme.id)
                .filter(Folio.household_member_id.in_([m.id for m in members]))
                .all()
            )
    except SQLAlchemyError:
        return None, None

    folio_key_to_member_id = {(fn, amc): mid for mid, fn, amc in existing_folios}
    for key in parsed_folio_keys:
        member_id = folio_key_to_member_id.get(key)
        if member_id is None:
            continue
        member = next((m for m in members if m.id == member_id), None)
        if member:
            return member, key
    return None, None


def resolve_attribution(
    db: Session,
    user_id: uuid.UUID,
    selected_member_id: uuid.UUID | None,
    parse_result: ParseResult,
) -> AttributionDecision:
    """Resolve attribution for a parsed CAS statement against the household roster.

    Raises CrossAccountPanBlockedError immediately, before returning any
    decision, if the parsed PAN belongs to a member of a different account.
    """
    members = db.query(HouseholdMember).filter(HouseholdMember.user_id == user_id).all()
    candidates = [{"id": str(m.id), "name": m.name, "relationship": m.relationship.value} for m in members]

    pan = parse_result.investor.pan
    matched_member: HouseholdMember | None = None
    matched_by_pan = False
    folio_matched_key: tuple[str, str] | None = None

    if pan:
        pan_hash = hash_pan(pan)
        system_match = _find_member_by_pan_hash(db, pan_hash)
        if system_match is not None:
            if system_match.user_id != user_id:
                raise CrossAccountPanBlockedError(CROSS_ACCOUNT_PAN_BLOCKED_MESSAGE)
            matched_member = system_match
            matched_by_pan = True

    if matched_member is None:
        matched_member, folio_matched_key = _find_folio_matched_member(db, members, parse_result)

    if not matched_member:
        return AttributionDecision(
            status=AttributionStatus.UNRECOGNIZED_MEMBER,
            resolved_member_id=None,
            matched_member_name=parse_result.investor.name,
            requires_confirmation=True,
            prompt_message="We couldn't match this statement to an existing family member. Would you like to add a new member?",
            candidate_members=candidates,
        )

    if matched_by_pan:
        return AttributionDecision(
            status=AttributionStatus.AUTO_MATCHED,
            resolved_member_id=matched_member.id,
            matched_member_name=matched_member.name,
            requires_confirmation=False,
            prompt_message=f"Matched to {matched_member.name} by PAN — attaching this statement to their account.",
            candidate_members=candidates,
            matched_by_pan=True,
        )

    if selected_member_id and matched_member.id == selected_member_id:
        return AttributionDecision(
            status=AttributionStatus.AUTO_MATCHED,
            resolved_member_id=matched_member.id,
            matched_member_name=matched_member.name,
            requires_confirmation=False,
            candidate_members=candidates,
        )

    prompt_message = (
        f"This folio ({folio_matched_key[0]} at {folio_matched_key[1]}) is already linked to "
        f"{matched_member.name} — import for {matched_member.name} instead?"
    )
    return AttributionDecision(
        status=AttributionStatus.MISMATCH_CONFIRMATION_REQUIRED,
        resolved_member_id=matched_member.id,
        matched_member_name=matched_member.name,
        requires_confirmation=True,
        prompt_message=prompt_message,
        candidate_members=candidates,
    )


def backfill_pan_if_missing(db: Session, member: HouseholdMember, parse_result: ParseResult) -> None:
    """Stores this member's PAN on first successful attribution, if not
    already on file. This is the only place PAN gets written -- there is no
    separate backfill/migration script (see design spec)."""
    if member.pan_lookup_hash is not None:
        return
    pan = parse_result.investor.pan
    if not pan:
        return
    member.pan_encrypted = encrypt_pan(pan)
    member.pan_lookup_hash = hash_pan(pan)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/services/import_/test_attribution.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/import_/attribution.py backend/tests/services/import_/test_attribution.py
git commit -m "feat(import): rewrite attribution to match by PAN, block cross-account reuse"
```

---

## Task 6: Wire PAN backfill + file storage into the sync path (`service.py`, `api/imports.py`)

**Files:**
- Modify: `backend/app/services/import_/service.py` (`build_import_preview`, `confirm_import`)
- Modify: `backend/app/api/imports.py` (`parse_import`, `confirm_import_route`)
- Test: `backend/tests/services/import_/test_service.py`, `backend/tests/api/test_imports_routes.py`

**Interfaces:**
- Consumes: `backfill_pan_if_missing`, `store_cas_file` (Tasks 3 & 5).
- Produces: preview sessions now also hold `pdf_bytes: bytes`; `confirm_import` now calls `backfill_pan_if_missing` and `store_cas_file` before `db.commit()`.

- [ ] **Step 1: Update `build_import_preview` to accept and stash the raw bytes**

In `backend/app/services/import_/service.py`, change the signature (currently line 79-81):

```python
async def build_import_preview(
    parse_result: ParseResult, filename: str, pdf_bytes: bytes, client: MfApiClient | None = None
) -> ImportPreviewResponse:
```

In the `_preview_sessions[session_id] = {...}` block (currently lines 123-128), add `"pdf_bytes": pdf_bytes,`:

```python
    _preview_sessions[session_id] = {
        "created_at": datetime.now(timezone.utc),
        "filename": filename, "parse_result": parse_result, "pdf_bytes": pdf_bytes,
        "key_to_temp": key_to_temp,
        "scheme_previews": {s.temp_id: s for s in scheme_previews},
    }
```

- [ ] **Step 2: Update `confirm_import` to backfill PAN and store the file**

In `backend/app/services/import_/service.py`, replace the existing `from app.services.import_.attribution import (...)` import block (currently importing `CROSS_ACCOUNT_DUPLICATE_WARNING`, `detect_cross_account_duplicate`, `enforce_attribution_confirmation`, `resolve_attribution`) with exactly this final form — drop `CROSS_ACCOUNT_DUPLICATE_WARNING` and `detect_cross_account_duplicate` (both were removed from `attribution.py` in Task 5), and add `backfill_pan_if_missing`:

```python
from app.services.import_.attribution import (
    backfill_pan_if_missing,
    enforce_attribution_confirmation,
    resolve_attribution,
)
from app.services.import_.file_storage import store_cas_file
```

In `confirm_import` (currently lines 143-162), right after `target_member_id` is computed and before the schemes-validation loop, add:

```python
    target_member = db.get(HouseholdMember, target_member_id)
    backfill_pan_if_missing(db, target_member, parse_result)
```

This needs `from app.models.user import HouseholdMember` added to the imports.

Then, right before `db.commit()` (currently line 347), add:

```python
    pdf_bytes = session["pdf_bytes"]
    store_cas_file(import_rec, user_id, pdf_bytes)
    db.commit()
```

- [ ] **Step 3: Remove the now-dead cross-account warning block**

In `confirm_import`, delete these lines entirely (currently lines 350-353):

```python
    warnings: list[str] = []
    cross_account = detect_cross_account_duplicate(db, user_id, parse_result)
    if cross_account is not None and cross_account.detected:
        warnings.append(CROSS_ACCOUNT_DUPLICATE_WARNING)
```

And change the final `return` (currently lines 356-361) to drop the `warnings=warnings` kwarg (the schema's `warnings` field already defaults to `[]`):

```python
    del _preview_sessions[session_id]
    return ImportConfirmResponse(
        added=added,
        skipped=skipped,
        import_id=str(import_rec.id),
    )
```

(This is a deliberate, documented consequence of the redesign: cross-account collisions are now a hard block raised earlier by `resolve_attribution`, not a post-hoc advisory warning — see the design spec's discussion of `detect_cross_account_duplicate` being folded into the PAN-hash check.)

- [ ] **Step 4: Update the `/imports/parse` route to pass `pdf_bytes` through**

In `backend/app/api/imports.py`, change the last line of `parse_import` (currently line 225):

```python
    return await build_import_preview(parse_result, file.filename, pdf_bytes)
```

- [ ] **Step 5: Catch `CrossAccountPanBlockedError` in `confirm_import_route`**

In `backend/app/api/imports.py`, add to the import line (currently line 26):

```python
from app.services.import_.attribution import AttributionConfirmationRequiredError, CrossAccountPanBlockedError
```

In `confirm_import_route` (currently the `try`/`except` block ending at line 275), add a new `except` clause before `except ValueError`:

```python
    except CrossAccountPanBlockedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "cross_account_pan_blocked", "message": str(exc)},
        ) from exc
```

- [ ] **Step 6: Fix existing tests broken by the signature/behavior changes**

Run: `cd backend && pytest tests/services/import_/test_service.py tests/api/test_imports_routes.py -v`

Expected failures and fixes, applied one at a time (re-run the specific failing test after each fix):

- Any direct call to `build_import_preview(parse_result, filename)` → add a third positional argument, e.g. `b"%PDF-1.4 fake"`, for the raw bytes.
- Any assertion on `ImportConfirmResponse(...).warnings` expecting a cross-account warning string → that field is now always `[]`; update the assertion to `assert response.warnings == []` (cross-account is now a blocking error raised during `resolve_attribution`, tested separately in `test_attribution.py`, not observable as a soft warning here anymore).
- Any test that relied on name-based matching to reach a particular household member (e.g., asserting `AUTO_MATCHED` because the parsed investor name matched a member's name) will now get `UNRECOGNIZED_MEMBER` or fall through to folio-matching instead, since name is no longer read. Fix by either: (a) passing `selected_member_id` equal to the intended member — folio-less, PAN-less resolution auto-matches to the selected member only when a PAN/folio match also confirms it, so check whether the test actually needs the household member to already have a `pan_lookup_hash` set to reach `AUTO_MATCHED` (construct it with `pan_lookup_hash=hash_pan(...)` and `pan_encrypted=encrypt_pan(...)` the way `test_attribution.py`'s `household_setup` fixture now does), or (b) if the test's intent was really about the transaction-commit logic rather than attribution, use `confirmed_member_override=True` to bypass attribution matching entirely and go straight to `target_member_id = household_member_id`.

- [ ] **Step 7: Run the full suite for this task's files to confirm everything is green**

Run: `cd backend && pytest tests/services/import_/test_service.py tests/api/test_imports_routes.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/import_/service.py backend/app/api/imports.py backend/tests/services/import_/test_service.py backend/tests/api/test_imports_routes.py
git commit -m "feat(import): wire PAN backfill and file storage into the sync confirm path"
```

---

## Task 7: Wire PAN backfill + file storage into the async path (`lifecycle_service.py`, `api/cas_imports.py`)

**Files:**
- Modify: `backend/app/services/import_/lifecycle_service.py` (`create_cas_import`, `retry_cas_import_password`)
- Modify: `backend/app/api/cas_imports.py` (`upload_cas_import`, `retry_password`)
- Test: `backend/tests/services/import_/test_lifecycle_service.py`, `backend/tests/api/test_cas_imports_routes.py`

**Interfaces:**
- Consumes: `backfill_pan_if_missing`, `store_cas_file` (Tasks 3 & 5).

- [ ] **Step 1: Update imports in `lifecycle_service.py`**

Replace the attribution import block (currently lines 27-34):

```python
from app.services.import_.attribution import (
    AttributionDecision,
    AttributionStatus,
    backfill_pan_if_missing,
    enforce_attribution_confirmation,
    resolve_attribution,
)
from app.services.import_.file_storage import store_cas_file
```

- [ ] **Step 2: Remove `_attach_cross_account_warning` and its call sites**

Delete the function entirely (currently lines 66-78):

```python
def _attach_cross_account_warning(
    db: Session,
    import_rec: Import,
    user_id: uuid.UUID,
    parse_result: ParseResult,
) -> None:
    """Attach an identity-free, response-only advisory without changing import flow."""
    warning = detect_cross_account_duplicate(db, user_id, parse_result)
    import_rec.parse_warnings = (
        [CROSS_ACCOUNT_DUPLICATE_WARNING]
        if warning is not None and warning.detected
        else []
    )
```

Delete its two call sites: `_attach_cross_account_warning(db, import_rec, user_id, parse_result)` in `create_cas_import` (currently line 246) and in `retry_cas_import_password` (currently line 307).

(This mirrors Task 6 Step 3's reasoning: cross-account is now a hard block raised by `resolve_attribution` itself, so this advisory is dead code. `CASImportStatusResponse.parse_warnings` in `api/cas_imports.py` keeps its `Field(default_factory=list)` default and will now always serialize as `[]` — left in place rather than removing the field, to avoid an unrelated frontend response-contract change under this plan's time budget. Flag this as a known follow-up cleanup.)

- [ ] **Step 3: Add PAN backfill + file storage to `create_cas_import`**

In `create_cas_import` (currently lines 237-246), after `target_member_id` is computed and `import_rec.household_member_id = target_member_id` is set, replace the `_attach_cross_account_warning(...)` line (just deleted) with:

```python
    target_member = db.query(HouseholdMember).filter_by(id=target_member_id).first()
    backfill_pan_if_missing(db, target_member, parse_result)
    store_cas_file(import_rec, user_id, file_bytes)
```

This needs `from app.models.user import HouseholdMember` added to the imports at the top of the file.

- [ ] **Step 4: Add the same to `retry_cas_import_password`**

In `retry_cas_import_password` (currently lines 299-307), after `import_rec.household_member_id = target_member_id`, replace the deleted `_attach_cross_account_warning(...)` line with:

```python
    target_member = db.query(HouseholdMember).filter_by(id=target_member_id).first()
    backfill_pan_if_missing(db, target_member, parse_result)
    store_cas_file(import_rec, user_id, pdf_bytes)
```

(`pdf_bytes` here is already in scope — it's the variable read from `get_pdf_buffer(str(import_id))` earlier in this same function.)

- [ ] **Step 5: Catch `CrossAccountPanBlockedError` in both routes**

In `backend/app/api/cas_imports.py`, update the import line (currently line 15):

```python
from app.services.import_.attribution import AttributionConfirmationRequiredError, CrossAccountPanBlockedError
```

In `upload_cas_import` (currently the `try`/`except` ending at line 136), add before `except InvalidFileFormatError`:

```python
    except CrossAccountPanBlockedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "cross_account_pan_blocked", "message": str(exc)},
        ) from exc
```

In `retry_password` (currently the `try`/`except` ending at line 197), add the same clause before `except SessionExpiredError`.

- [ ] **Step 6: Fix existing tests broken by the changes**

Run: `cd backend && pytest tests/services/import_/test_lifecycle_service.py tests/api/test_cas_imports_routes.py -v`

Apply the same three fix patterns as Task 6 Step 6 (household members need `pan_lookup_hash`/`pan_encrypted` set up front to reach `AUTO_MATCHED` via PAN now that name-matching is gone; any assertion reading `rec.parse_warnings` for a cross-account case should instead assert a `CrossAccountPanBlockedError`/409 is raised; use `confirmed_member_override=True` where the test's real intent is unrelated to attribution).

- [ ] **Step 7: Run the full suite for this task's files to confirm everything is green**

Run: `cd backend && pytest tests/services/import_/test_lifecycle_service.py tests/api/test_cas_imports_routes.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/import_/lifecycle_service.py backend/app/api/cas_imports.py backend/tests/services/import_/test_lifecycle_service.py backend/tests/api/test_cas_imports_routes.py
git commit -m "feat(import): wire PAN backfill and file storage into the async import path"
```

---

## Task 8: Rewrite the CI guard test

**Files:**
- Modify: `backend/tests/models/test_no_pan_field.py` (full rewrite)

**Interfaces:** none new — this is a pure invariant test.

- [ ] **Step 1: Replace the file entirely**

```python
"""Guards the ADR-004 (reopened 2026-09-18) invariant: PAN is persisted only
in encrypted/hashed form, never as plaintext, and only on HouseholdMember —
never on Scheme, Folio, or Import.

Original guard (pre-2026-09-18) asserted no PAN-shaped column existed
anywhere. That decision was formally reopened -- see
Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md and the
updated Docs/PRDs/ADR-Technical-Stack-Decisions.md (ADR-004). This test now
guards the *replacement* invariant instead of the original one.
"""

from app.models.folio import Folio
from app.models.imports import Import
from app.models.reference import Scheme
from app.models.user import HouseholdMember


def test_no_pan_shaped_column_on_non_household_member_models():
    for model in (Scheme, Folio, Import):
        for column_name in model.__table__.columns.keys():
            assert "pan" not in column_name.lower(), (
                f"{model.__name__}.{column_name} looks PAN-related — PAN must only ever "
                "live on HouseholdMember (encrypted), per ADR-004 as reopened 2026-09-18."
            )


def test_household_member_pan_columns_are_named_for_encrypted_or_hashed_storage_only():
    pan_columns = [c for c in HouseholdMember.__table__.columns.keys() if "pan" in c.lower()]
    assert set(pan_columns) == {"pan_encrypted", "pan_lookup_hash"}, (
        "HouseholdMember must expose exactly pan_encrypted and pan_lookup_hash for PAN — "
        "a column named just 'pan' (or anything else PAN-shaped) would suggest plaintext "
        "storage, which ADR-004 (as reopened) still forbids."
    )
```

- [ ] **Step 2: Run to verify it passes**

Run: `cd backend && pytest tests/models/test_no_pan_field.py -v`
Expected: PASS (2 tests)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/models/test_no_pan_field.py
git commit -m "test(import): rewrite PAN guard test for the reopened ADR-004 invariant"
```

---

## Task 9: Documentation — reopen ADR-004 and update dependent docs

**Files:**
- Modify: `Docs/PRDs/ADR-Technical-Stack-Decisions.md`
- Modify: `Docs/PRDs/Database-Schema-Unifolio.md`
- Modify: `Docs/PRDs/PRD-01-CAS-Parser-v2.md`
- Modify: `AGENTS.md`, `PRODUCT.md`, `decisions.md`, `database.md`, `backend.md` (repo root)
- Modify: `Docs/orchestration/non-pan-duplicate-person-detection-handoff.md` (add a superseded pointer, not a rewrite — see Step 5)

No tests apply to this task — it's documentation only. Each step is a targeted find-and-replace; run `grep -n "No raw CAS PDF storage\|No PAN persistence\|PAN never persisted\|PAN persistence: not stored" <file>` on each file first to find the exact current line before editing, since exact line numbers may have drifted since this plan was written.

- [ ] **Step 1: ADR-004**

In `Docs/PRDs/ADR-Technical-Stack-Decisions.md`, find the ADR-004 section (its "Decision: CAS PDF Is Not Retained" subsection and the "No raw CAS PDF storage, ever. No PAN persistence, ever." line). Replace that decision with:

```markdown
### Decision: CAS PDF and PAN Are Retained, Encrypted, Time-Bounded (supersedes the original ADR-004 decision, 2026-09-18)

The original decision above (no PAN persistence, no raw CAS PDF storage) is
superseded. As of 2026-09-18:

- **PAN** is persisted per household member, encrypted at rest (AES-256-GCM
  envelope encryption; see `backend/app/services/import_/crypto.py`), plus a
  separate deterministic lookup hash (HMAC-SHA256) used for matching so the
  application never needs to decrypt another household's PAN to check for a
  duplicate. PAN is used server-side only, for attribution matching — it is
  never returned by any API response (the masked form, `pan_masked`,
  continues to be the only PAN-shaped value any client ever sees).
- **The raw CAS PDF** is retained for 30 days from upload (for re-parsing and
  dispute resolution), then deleted. It is stored outside the primary
  database (locally on disk in development; a private, SSE-KMS-encrypted S3
  bucket with a native Lifecycle expiry rule in production — see the
  Production Mapping section of
  `Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md`).

**Why reopened:** PAN-based attribution eliminates the fragility of
name/email matching (nicknames, transliteration, similar family names) and
enables a hard block on a PAN already tracked under a different account —
neither is possible without persisting PAN in some recoverable form.

**DPDP-Act consideration:** the replacement design still minimizes exposure
relative to the rejected alternative (indefinite plaintext retention): PAN is
always encrypted at rest and never returned in plaintext by any API surface;
the CAS file has a hard 30-day retention ceiling rather than indefinite
storage. This reopening was done as a fresh, explicit decision — see
`Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md` — per this
ADR's own original stated reopening requirement.

**Status:** Accepted, 2026-09-18.
```

- [ ] **Step 2: `Database-Schema-Unifolio.md`**

Find "Design Principle 3" (the "No raw CAS PDF storage anywhere" line) and replace with:

```markdown
3. Raw CAS PDF and PAN are retained in bounded, encrypted form only — the
   source PDF for 30 days (outside the primary DB, deleted after), and PAN
   as `household_members.pan_encrypted` (AES-256-GCM) plus
   `household_members.pan_lookup_hash` (HMAC-SHA256, for matching only).
   Reopened from the original "never persisted" decision — see ADR-004 and
   `Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md`.
```

Find the Data Classification & Security table's `Parsed PAN` and `CAS PDF` rows and replace with:

```markdown
| Parsed PAN | Highly sensitive | Persisted on `household_members.pan_encrypted` (AES-256-GCM, application-level envelope encryption) plus `pan_lookup_hash` (HMAC-SHA256, one-way, used only for equality matching). Never returned by any API — masked display (`ABCDE****F`) only. See ADR-004 (reopened 2026-09-18). |
| CAS PDF | Highly sensitive | Retained 30 days from upload for dispute/re-parse support, then deleted — local disk in dev, private SSE-KMS-encrypted S3 bucket with a Lifecycle expiry rule in production. Per ADR-004, reopened 2026-09-18. |
```

Find the "Open Questions" section's PAN-persistence resolution line and append:

```markdown
**Reopened 2026-09-18:** the "PAN persistence: not stored anywhere" resolution above was itself reopened — see ADR-004's 2026-09-18 update and `Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md`. PAN is now stored, encrypted, per household member.
```

- [ ] **Step 3: `PRD-01-CAS-Parser-v2.md`**

Find FR-2's "PAN is never persisted" line and replace with:

```markdown
PAN is persisted per household member (encrypted; see ADR-004 as reopened
2026-09-18) for attribution matching, and remains masked (`ABCDE****F`) in
every UI/log/API surface — the encrypted/hashed form is never returned to
any client.
```

Find FR-4 (attribution) and append:

```markdown
**Updated 2026-09-18:** attribution now matches by PAN (a deterministic
lookup hash, never by decrypting), not by investor name/email. A PAN match
within the same household auto-attributes with a disclaimer; a PAN match
under a different Unifolio account blocks the import outright (no
in-app override or merge). Folio-number+AMC reuse remains a fallback signal
for the rare case where a CAS has no parseable PAN. See
`Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md`.
```

- [ ] **Step 4: Repo-root one-liners**

In `AGENTS.md` (the "No raw CAS PDF storage, ever. No PAN persistence, ever." line, currently line 57) and `PRODUCT.md` (currently line 58), find that exact sentence and replace with:

```
PAN and the raw CAS PDF are now persisted in bounded, encrypted form (ADR-004 reopened 2026-09-18) — PAN encrypted per household member for attribution matching, the PDF for 30 days for dispute/re-parse support. See Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md.
```

In `database.md`, find the exact sentence "No PAN column anywhere; no raw-CAS-PDF table or column anywhere." (currently line 7, at the end of the `0001_initial_schema` migration description) and replace it with:

```
PAN is now persisted on `household_members.pan_encrypted`/`pan_lookup_hash` (migration `0015`); the raw CAS PDF is retained 30 days then deleted, outside the primary DB. ADR-004 reopened 2026-09-18 — see Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md.
```

In `backend.md`, find the parenthetical "(Decimal-never-float, no PAN persistence)" (currently line 41, in the sentence about `state_machine.py`/attribution logic not yet being independently reviewed) and replace just that parenthetical with:

```
(Decimal-never-float; PAN now persisted encrypted per ADR-004 as reopened 2026-09-18 — see migration 0015 and Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md)
```

In `decisions.md` specifically, add a new dated entry rather than editing the old 2026-07-22 one in place (that file is a decision log — preserve its history):

```markdown
**2026-09-18 — PAN persistence and CAS file retention (reopens 2026-07-22 decision):** ADR-004's original "no PAN, no raw file, ever" is superseded. PAN is now stored encrypted per household member (attribution matching); the raw CAS PDF is retained 30 days then deleted. Why: name/email-based attribution was fragile (nicknames, similar family names) and couldn't detect the same PAN already tracked under a different account. See `Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md`.
```

- [ ] **Step 5: Add a superseded pointer to the handoff doc this change replaces**

`Docs/orchestration/non-pan-duplicate-person-detection-handoff.md` is the completed (DONE, 2026-09-03) design record for the exact folio-matching and cross-account name-matching logic that Task 5 deletes from `attribution.py`. It's a historical handoff doc, so don't rewrite its content — but a future reader hitting it (searching for why `attribution.py` looks the way it does) needs to know it no longer describes the current code. Add this line immediately under its `**Status:** DONE (2026-09-03)` line:

```markdown
**Superseded 2026-09-18:** the name/email/folio-based matching this doc describes was replaced by PAN-hash-based matching once ADR-004 was reopened. `detect_cross_account_duplicate` (built by this task) no longer exists — folded into `resolve_attribution`'s PAN-hash check, which now blocks a cross-account match outright instead of issuing an advisory warning. See `Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md`.
```

- [ ] **Step 6: Commit**

```bash
git add "Docs/PRDs/ADR-Technical-Stack-Decisions.md" "Docs/PRDs/Database-Schema-Unifolio.md" "Docs/PRDs/PRD-01-CAS-Parser-v2.md" AGENTS.md PRODUCT.md decisions.md database.md backend.md "Docs/orchestration/non-pan-duplicate-person-detection-handoff.md"
git commit -m "docs: reopen ADR-004 for PAN persistence and bounded CAS file retention"
```

---

## Task 10: Full suite verification + expiry sweep CLI entry point

**Files:**
- Create: `backend/app/scripts/expire_cas_files.py`
- No new tests (this task verifies the whole plan, plus adds one small callable script covered by Task 3's existing `expire_stored_files` tests).

**Interfaces:**
- Consumes: `expire_stored_files` (Task 3).

- [ ] **Step 1: Add a thin CLI entry point for the sweep**

Create `backend/app/scripts/expire_cas_files.py`:

```python
"""Manual/cron entry point for CAS file expiry sweeping.

Run as: python -m app.scripts.expire_cas_files
Production maps this to a scheduled EventBridge Scheduler + ECS Fargate task
using the already-staged infra/modules/scheduler module (not wired up in
this pass — see Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md's
"Explicitly out of scope").
"""
from app.db.session import SessionLocal
from app.services.import_.file_storage import expire_stored_files


def main() -> None:
    db = SessionLocal()
    try:
        deleted_count = expire_stored_files(db)
        print(f"Expired {deleted_count} CAS file(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it manually to confirm it executes cleanly against the dev DB**

Run: `cd backend && python -m app.scripts.expire_cas_files`
Expected: prints `Expired 0 CAS file(s).` (nothing should be expired yet on a fresh dev DB)

- [ ] **Step 3: Run the entire backend test suite**

Run: `cd backend && pytest -v`
Expected: all tests pass. If anything outside the files this plan already touched fails, it's almost certainly one of the `ParsedInvestor(...)` call sites listed at the top of this plan's research (`test_cas_imports_routes.py`, `test_imports_routes.py`, `test_service.py`, `test_lifecycle_service.py`) that Tasks 6/7 didn't happen to touch — apply the same three fix patterns from Task 6 Step 6.

- [ ] **Step 4: Run the frontend test suite to confirm no contract break**

Run: `cd frontend && npm test -- --run`
Expected: all pass — no frontend code was touched, and no API response schema changed (only new HTTP error codes were added, which existing tests shouldn't be asserting against unless they specifically test cross-account behavior, which didn't exist as a blocking case before).

- [ ] **Step 5: Commit**

```bash
git add backend/app/scripts/expire_cas_files.py
git commit -m "feat(import): add manual CLI entry point for the CAS file expiry sweep"
```

---

## Self-Review Notes (completed while writing this plan)

- **Spec coverage:** every section of `Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md` maps to a task — data model (Task 1), encryption (Task 2), file storage (Task 3), parser carry-through (Task 4), attribution rewrite (Task 5), both import pipelines (Tasks 6-7), guard test (Task 8), docs (Task 9), sweep entry point + full verification (Task 10).
- **Known, deliberate scope cut carried from the spec:** no live AWS deployment, no scheduled job wiring — both called out explicitly in Tasks 3 and 10 rather than silently dropped.
- **Type/signature consistency checked:** `ParsedInvestor.pan` (Task 4) is read by `resolve_attribution` and `backfill_pan_if_missing` (Task 5) using the same attribute name throughout; `store_cas_file(import_rec, user_id, pdf_bytes, storage=...)` signature is identical across Tasks 3, 6, and 7; `CrossAccountPanBlockedError` is defined once (Task 5) and imported identically in both API route files (Tasks 6-7).
- **Known gap flagged, not silently fixed:** `CASImportStatusResponse.parse_warnings` and `ImportConfirmResponse.warnings` become permanently `[]` after this change (their only producer, cross-account soft-warnings, is removed) but the fields aren't deleted, to avoid an unrelated frontend contract change under this plan's time budget — called out explicitly in Tasks 6 and 7 as a follow-up, not hidden.
