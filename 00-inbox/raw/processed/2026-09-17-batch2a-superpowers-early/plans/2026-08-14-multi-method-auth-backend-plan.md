# Multi-Method Auth (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Google Sign-In and email+OTP as auth methods alongside the existing phone+OTP, with every account converging on a verified phone number regardless of starting method, and an explicit, non-silent account-linking policy for collisions.

**Architecture:** A new `auth_identities` table becomes the source of truth for "which credentials prove who this user is," decoupled from `users` (which becomes a profile/anchor row). A new `pending_identity_verifications` table holds a just-verified Google/email identity that can't yet be attached to a session — either because the account is brand new and still needs its mandatory phone step, or because it collided with an existing account and needs step-up re-auth. Google ID tokens are verified via signature checking against Google's public keys (no client secret, no token exchange). Email OTP reuses the existing `otp_requests` table and `otp.py` logic, generalized to accept either a phone number or an email address. A new `EmailProvider` protocol ships with a stub implementation only — no real email provider in this plan.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, pytest, `google-auth` (new dependency, added in Task 7).

**Spec:** `Docs/superpowers/specs/2026-08-14-multi-method-auth-design.md`

## Global Constraints

- **Every account ends up with a verified phone number, no exceptions.** `users.phone_number` stays `UNIQUE NOT NULL` — do not loosen it. A `User` row cannot exist without a matching `auth_identities(provider='phone_otp')` row.
- **Apple is entirely out of scope for this plan.** Do not add `'apple'` to any enum, do not add an `/auth/oauth/apple` route. (Backend spec's Future Scope section.)
- **v1 ships with `StubEmailProvider` only.** Do not write a `PostmarkEmailProvider` or wire up any real email-sending network call in this plan.
- **Identity precedence is Google > Email > Phone** wherever only one identity can be shown or selected (denormalized `users.email`, and which method a step-up prompt names).
- **`pending_identity_verifications` uses one shared TTL** (10 minutes) for both the phone-gate trigger and the step-up-link trigger — not two different values.
- **Every schema change goes through Alembic** — never a hand-edited `CREATE TABLE` or `Base.metadata.create_all()` outside test fixtures (Migration Plan Guardrail 1).
- **ORM queries only, no dialect-specific raw SQL** for anything this plan adds (Migration Plan Guardrail 2).
- **No JSON/JSONB columns.** This feature introduces none — don't add any.
- **Test-driven, always.** Follow this repo's existing pytest conventions exactly: `tests/conftest.py`'s `client` fixture (FastAPI `TestClient` over an in-memory SQLite DB, `autoflush=False`) for route tests, plain `sessionmaker(autoflush=False, bind=engine)` sessions for service-level tests — never a session with default `autoflush=True`, which has previously hidden a real production bug in this codebase.
- **Token/hash conventions**: opaque tokens via `secrets.token_urlsafe(32)`, hashed with `hashlib.sha256` for storage, raw value returned to the caller exactly once — matches `session.py` and `otp.py` exactly; don't introduce a different scheme.

---

## Task 1: Schema — `auth_identities`, `pending_identity_verifications`, widened `otp_requests`, `sessions.auth_method`

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/auth.py`
- Create: `backend/alembic/versions/0004_multi_method_auth_identities.py`
- Create: `backend/tests/models/test_auth_identity_models.py`
- Modify: `backend/tests/test_migrations.py`

**Interfaces:**
- Produces: `AuthIdentityProvider` enum (`PHONE_OTP`, `EMAIL_OTP`, `GOOGLE`), `AuthIdentity` model (`id`, `user_id`, `provider`, `provider_subject`, `email`, `identifier_verified_at`, `created_at`, `last_used_at`), `PendingIdentityVerification` model (`id`, `provider`, `provider_subject`, `email`, `email_verified`, `matched_user_id`, `token_hash`, `expires_at`, `created_at`), `OtpRequest.email` (nullable, alongside now-nullable `OtpRequest.phone_number`), `Session.auth_method`.

- [ ] **Step 1: Write the failing model tests**

Create `backend/tests/models/test_auth_identity_models.py`:

```python
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.auth import AuthIdentity, OtpRequest, PendingIdentityVerification, Session as SessionModel
from app.models.enums import AuthIdentityProvider
from app.models.user import User


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            AuthIdentity.__table__,
            PendingIdentityVerification.__table__,
            OtpRequest.__table__,
            SessionModel.__table__,
        ],
    )
    return sessionmaker(autoflush=False, bind=engine)()


def _user(db) -> User:
    user = User(id=uuid.uuid4(), phone_number="+919999999999", created_at=datetime.now(timezone.utc))
    db.add(user)
    db.commit()
    return user


def test_auth_identity_round_trip():
    db = _session()
    user = _user(db)
    now = datetime.now(timezone.utc)

    identity = AuthIdentity(
        user_id=user.id,
        provider=AuthIdentityProvider.GOOGLE,
        provider_subject="google-sub-123",
        email="a@example.com",
        identifier_verified_at=now,
        created_at=now,
        last_used_at=now,
    )
    db.add(identity)
    db.commit()

    fetched = db.query(AuthIdentity).filter_by(provider_subject="google-sub-123").one()
    assert fetched.user_id == user.id
    assert fetched.provider == AuthIdentityProvider.GOOGLE


def test_auth_identity_rejects_duplicate_provider_subject():
    db = _session()
    user_a = _user(db)
    now = datetime.now(timezone.utc)
    db.add(
        AuthIdentity(
            user_id=user_a.id, provider=AuthIdentityProvider.GOOGLE,
            provider_subject="dup-sub", email=None,
            identifier_verified_at=now, created_at=now, last_used_at=now,
        )
    )
    db.commit()

    user_b = User(id=uuid.uuid4(), phone_number="+919888888888", created_at=now)
    db.add(user_b)
    db.commit()
    db.add(
        AuthIdentity(
            user_id=user_b.id, provider=AuthIdentityProvider.GOOGLE,
            provider_subject="dup-sub", email=None,
            identifier_verified_at=now, created_at=now, last_used_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_pending_identity_verification_round_trip():
    db = _session()
    now = datetime.now(timezone.utc)
    pending = PendingIdentityVerification(
        provider=AuthIdentityProvider.EMAIL_OTP,
        provider_subject="new@example.com",
        email="new@example.com",
        email_verified=True,
        matched_user_id=None,
        token_hash="deadbeef",
        expires_at=now + timedelta(minutes=10),
        created_at=now,
    )
    db.add(pending)
    db.commit()

    fetched = db.query(PendingIdentityVerification).filter_by(token_hash="deadbeef").one()
    assert fetched.matched_user_id is None
    assert fetched.email_verified is True


def test_otp_request_rejects_both_identifiers_set():
    db = _session()
    now = datetime.now(timezone.utc)
    db.add(
        OtpRequest(
            phone_number="+919999999999", email="a@example.com",
            otp_hash="x", expires_at=now, created_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_otp_request_rejects_neither_identifier_set():
    db = _session()
    now = datetime.now(timezone.utc)
    db.add(OtpRequest(phone_number=None, email=None, otp_hash="x", expires_at=now, created_at=now))
    with pytest.raises(IntegrityError):
        db.commit()


def test_otp_request_accepts_email_only():
    db = _session()
    now = datetime.now(timezone.utc)
    db.add(OtpRequest(phone_number=None, email="a@example.com", otp_hash="x", expires_at=now, created_at=now))
    db.commit()  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/models/test_auth_identity_models.py -v`
Expected: FAIL with `ImportError` (`AuthIdentity`, `PendingIdentityVerification`, `AuthIdentityProvider` don't exist yet).

- [ ] **Step 3: Add the `AuthIdentityProvider` enum**

In `backend/app/models/enums.py`, add after `ArnStatus`:

```python
class AuthIdentityProvider(str, enum.Enum):
    PHONE_OTP = "phone_otp"
    EMAIL_OTP = "email_otp"
    GOOGLE = "google"
```

- [ ] **Step 4: Add `AuthIdentity` and `PendingIdentityVerification` models, widen `OtpRequest`, add `Session.auth_method`**

Replace the full contents of `backend/app/models/auth.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AuthIdentityProvider, enum_column


class OtpRequest(Base):
    __tablename__ = "otp_requests"
    __table_args__ = (
        CheckConstraint(
            "(phone_number IS NOT NULL) != (email IS NOT NULL)",
            name="ck_otp_requests_exactly_one_identifier",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Exactly one of phone_number/email is set per row (see CheckConstraint
    # above) — this table is shared between phone and email OTP, per
    # Design Spec §1: identical hash/expiry/attempt-count logic, only the
    # delivery channel differs.
    phone_number: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    otp_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthIdentity(Base):
    """One row per external identity (phone/email/Google) that can log a
    user in — many rows per user. Design Spec §1: `users` is a
    provider-agnostic anchor; this table is the verification source of
    truth."""

    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_auth_identities_provider_subject"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[AuthIdentityProvider] = mapped_column(enum_column(AuthIdentityProvider), nullable=False)
    # Phone number (phone_otp), email address (email_otp), or Google `sub` claim.
    provider_subject: Mapped[str] = mapped_column(String, nullable=False)
    # Denormalized from the identity's own claim — used only for the
    # collision lookup (Design Spec §4), never as a credential itself.
    email: Mapped[str | None] = mapped_column(String)
    identifier_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PendingIdentityVerification(Base):
    """Holds a just-verified Google/email identity that can't yet be
    attached to a session — either a brand-new signup still missing its
    mandatory phone step (`matched_user_id` NULL), or a collision needing
    step-up re-auth (`matched_user_id` set). Design Spec §1/§4 — one
    mechanism, two triggers, one shared TTL."""

    __tablename__ = "pending_identity_verifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Never PHONE_OTP — a phone-first verification never produces a
    # pending record, it completes signup on its own.
    provider: Mapped[AuthIdentityProvider] = mapped_column(enum_column(AuthIdentityProvider), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String)
    email_verified: Mapped[bool] = mapped_column(nullable=False)
    matched_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    session_token_hash: Mapped[str] = mapped_column(String, nullable=False)
    # Whichever method's verification directly produced this session — for
    # a phone-gated signup, that's phone_otp (the completing method), not
    # the originating Google/email identity (Design Spec §5).
    auth_method: Mapped[AuthIdentityProvider] = mapped_column(enum_column(AuthIdentityProvider), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    device_info: Mapped[str | None] = mapped_column(String)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/models/test_auth_identity_models.py -v`
Expected: PASS (all 6 tests).

- [ ] **Step 6: Write the Alembic migration**

Create `backend/alembic/versions/0004_multi_method_auth_identities.py`:

```python
"""multi-method auth: identities, pending verifications, widened otp_requests

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-14

Adds `auth_identities` (verification source of truth, one row per linked
method) and `pending_identity_verifications` (holds a verified Google/email
identity until its mandatory phone step or step-up link completes).
`users.phone_number` is UNCHANGED — it stays UNIQUE NOT NULL, per Design
Spec §1's reversal of an earlier draft that would have made it nullable.
`otp_requests` widens to accept email as an alternative to phone_number
(exactly one required, via CHECK constraint). `sessions` gains
`auth_method`, backfilled to 'phone_otp' for existing rows since every
session created before this migration was phone-authenticated.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_PROVIDER_VALUES = ("phone_otp", "email_otp", "google")


def upgrade() -> None:
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Enum(*_PROVIDER_VALUES, name="authidentityprovider"), nullable=False),
        sa.Column("provider_subject", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("identifier_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_subject", name="uq_auth_identities_provider_subject"),
    )

    op.create_table(
        "pending_identity_verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Enum(*_PROVIDER_VALUES, name="authidentityprovider"), nullable=False),
        sa.Column("provider_subject", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("matched_user_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["matched_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("otp_requests") as batch_op:
        batch_op.alter_column("phone_number", existing_type=sa.String(), nullable=True)
        batch_op.add_column(sa.Column("email", sa.String(), nullable=True))
        batch_op.create_check_constraint(
            "ck_otp_requests_exactly_one_identifier",
            "(phone_number IS NOT NULL) != (email IS NOT NULL)",
        )

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "auth_method",
                sa.Enum(*_PROVIDER_VALUES, name="authidentityprovider"),
                nullable=False,
                server_default="phone_otp",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("auth_method")

    with op.batch_alter_table("otp_requests") as batch_op:
        batch_op.drop_constraint("ck_otp_requests_exactly_one_identifier", type_="check")
        batch_op.drop_column("email")
        batch_op.alter_column("phone_number", existing_type=sa.String(), nullable=False)

    op.drop_table("pending_identity_verifications")
    op.drop_table("auth_identities")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE authidentityprovider")
```

- [ ] **Step 7: Update `test_migrations.py`'s expected table set**

In `backend/tests/test_migrations.py`, in `test_alembic_upgrade_creates_all_tables`, change:

```python
    expected = {
        "users", "household_members", "imports", "schemes", "folios",
        "transactions", "nav_history", "scheme_ter", "scheme_aaum",
        "benchmark_index_history", "arn_directory", "portfolio_snapshots",
        "fund_scores", "otp_requests", "sessions",
    }
```

to:

```python
    expected = {
        "users", "household_members", "imports", "schemes", "folios",
        "transactions", "nav_history", "scheme_ter", "scheme_aaum",
        "benchmark_index_history", "arn_directory", "portfolio_snapshots",
        "fund_scores", "otp_requests", "sessions",
        "auth_identities", "pending_identity_verifications",
    }
```

Then append a new test to the same file:

```python
def test_multi_method_auth_migration_round_trip(tmp_path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "multi_method_auth.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR, capture_output=True, text=True,
    )
    assert upgrade.returncode == 0, upgrade.stderr

    conn = sqlite3.connect(db_path)
    otp_columns = {row[1] for row in conn.execute("PRAGMA table_info(otp_requests)")}
    assert "email" in otp_columns
    session_columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    assert "auth_method" in session_columns
    conn.close()

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0003"],
        cwd=BACKEND_DIR, capture_output=True, text=True,
    )
    assert downgrade.returncode == 0, downgrade.stderr
```

- [ ] **Step 8: Run the full migration test file**

Run: `cd backend && python -m pytest tests/test_migrations.py -v`
Expected: PASS (all tests, including the two modified/added above).

- [ ] **Step 9: Run the full test suite to check for regressions**

Run: `cd backend && python -m pytest -v`
Expected: Pre-existing tests in `tests/services/auth/test_session.py` will now FAIL — `Session(...)` calls in those tests don't pass `auth_method`, which is now `nullable=False` with no Python-side default. This is expected and fixed in Task 4. Confirm the only failures are in `tests/services/auth/test_session.py` and `tests/api/test_auth_routes.py` (routes that create sessions), nothing else.

- [ ] **Step 10: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/auth.py \
  backend/alembic/versions/0004_multi_method_auth_identities.py \
  backend/tests/models/test_auth_identity_models.py backend/tests/test_migrations.py
git commit -m "feat(auth): add auth_identities, pending_identity_verifications, widen otp_requests and sessions"
```

---

## Task 2: `EmailProvider` abstraction

**Files:**
- Create: `backend/app/services/auth/email_provider.py`
- Create: `backend/tests/services/auth/test_email_provider.py`

**Interfaces:**
- Consumes: `app.config.settings.otp_delivery_mode` (existing).
- Produces: `EmailProvider` (Protocol) with `send_email(self, to: str, subject: str, body: str) -> None`; `StubEmailProvider` (implements it); `get_email_provider() -> EmailProvider`; `NoEmailProviderConfiguredError(RuntimeError)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/auth/test_email_provider.py`:

```python
import pytest

from app.services.auth.email_provider import (
    NoEmailProviderConfiguredError,
    StubEmailProvider,
    get_email_provider,
)


def test_stub_email_provider_does_not_raise(caplog):
    provider = StubEmailProvider()
    provider.send_email(to="a@example.com", subject="Test", body="Hello")
    assert "a@example.com" in caplog.text


def test_get_email_provider_returns_stub_in_stub_mode(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "otp_delivery_mode", "stub")
    provider = get_email_provider()
    assert isinstance(provider, StubEmailProvider)


def test_get_email_provider_raises_outside_stub_mode(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "otp_delivery_mode", "sms")
    with pytest.raises(NoEmailProviderConfiguredError, match="Postmark"):
        get_email_provider()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/auth/test_email_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.auth.email_provider'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/auth/email_provider.py`:

```python
"""Email-sending abstraction for email OTP — Design Spec §3.

v1 ships with StubEmailProvider only. A real provider (Postmark, per the
spec's decision) is a later, separate task: one new class implementing this
same protocol, plus a config value. Do not build that class here.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.config import settings

logger = logging.getLogger(__name__)


class EmailProvider(Protocol):
    def send_email(self, to: str, subject: str, body: str) -> None: ...


class StubEmailProvider:
    """Logs instead of sending — mirrors how phone OTP already behaves in
    stub mode (see otp.py's otp_delivery_mode='stub' gate)."""

    def send_email(self, to: str, subject: str, body: str) -> None:
        logger.info("StubEmailProvider: would send to=%s subject=%r body=%r", to, subject, body)


class NoEmailProviderConfiguredError(RuntimeError):
    pass


def get_email_provider() -> EmailProvider:
    if settings.otp_delivery_mode == "stub":
        return StubEmailProvider()
    raise NoEmailProviderConfiguredError(
        "No real EmailProvider is configured — Postmark integration is a "
        "later, separate task (Design Spec §3/§8). Set OTP_DELIVERY_MODE "
        "back to 'stub' for local development."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/auth/test_email_provider.py -v`
Expected: PASS (3 tests). Note: `caplog` captures at WARNING level by default in pytest — if `test_stub_email_provider_does_not_raise` fails only on the `caplog.text` assertion, add `caplog.set_level(logging.INFO)` as the first line of that test.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth/email_provider.py backend/tests/services/auth/test_email_provider.py
git commit -m "feat(auth): add EmailProvider abstraction with stub implementation"
```

---

## Task 3: Generalize OTP service for email channel

**Files:**
- Modify: `backend/app/services/auth/otp.py`
- Modify: `backend/tests/services/auth/test_otp.py`

**Interfaces:**
- Consumes: `email_provider.get_email_provider()` (Task 2).
- Produces: `create_otp_request(db, identifier: str, channel: Literal["sms", "email"] = "sms") -> tuple[OtpRequest, str | None]`; `verify_otp(db, identifier: str, otp: str, channel: Literal["sms", "email"] = "sms") -> OtpRequest`. Signature change from the current `(db, phone_number)` — every existing call site must be updated (done in Task 9).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/services/auth/test_otp.py` (keep all existing tests — they call `create_otp_request(db, "+91...")` positionally, which stays valid since `channel` defaults to `"sms"`):

```python
def test_create_otp_request_accepts_email_channel(monkeypatch):
    import app.services.auth.otp as otp_module

    monkeypatch.setattr(otp_module.settings, "otp_delivery_mode", "stub")
    db = _session()
    request, raw_otp = create_otp_request(db, "a@example.com", channel="email")

    assert raw_otp is not None
    assert request.email == "a@example.com"
    assert request.phone_number is None


def test_verify_otp_succeeds_for_email_channel():
    db = _session()
    _, raw_otp = create_otp_request(db, "a@example.com", channel="email")

    verified = verify_otp(db, "a@example.com", raw_otp, channel="email")

    assert verified.verified_at is not None


def test_verify_otp_email_channel_does_not_match_phone_request():
    db = _session()
    create_otp_request(db, "+919999999999", channel="sms")

    with pytest.raises(OtpVerificationError, match="No pending"):
        verify_otp(db, "+919999999999", "000000", channel="email")


def test_create_otp_request_email_channel_dispatches_via_email_provider_when_not_stub(monkeypatch):
    import app.services.auth.otp as otp_module

    monkeypatch.setattr(otp_module.settings, "otp_delivery_mode", "postmark")
    monkeypatch.setattr(otp_module.settings, "database_url", "sqlite:///:memory:")

    sent = {}

    class FakeProvider:
        def send_email(self, to, subject, body):
            sent["to"] = to
            sent["body"] = body

    monkeypatch.setattr(otp_module, "get_email_provider", lambda: FakeProvider())
    db = _session()

    request, raw_otp = create_otp_request(db, "a@example.com", channel="email")

    assert raw_otp is None
    assert sent["to"] == "a@example.com"
    assert request.otp_hash != sent["body"]  # sanity: body isn't the raw hash


def test_create_otp_request_email_channel_raises_when_no_provider_configured(monkeypatch):
    import app.services.auth.otp as otp_module

    monkeypatch.setattr(otp_module.settings, "otp_delivery_mode", "postmark")
    monkeypatch.setattr(otp_module.settings, "database_url", "sqlite:///:memory:")
    db = _session()

    with pytest.raises(otp_module.NoEmailProviderConfiguredError):
        create_otp_request(db, "a@example.com", channel="email")
```

Also update the `_session()` helper in this file to also create the `AuthIdentity`/`PendingIdentityVerification` tables isn't needed here (this file only touches `OtpRequest`) — leave `_session()` unchanged.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/auth/test_otp.py -v`
Expected: FAIL — `create_otp_request()`/`verify_otp()` don't accept a `channel` keyword yet, and `NoEmailProviderConfiguredError`/`get_email_provider` aren't imported into `otp.py`.

- [ ] **Step 3: Write the implementation**

Replace `backend/app/services/auth/otp.py` in full:

```python
"""OTP generation, hashing, and verification — phone+OTP and email+OTP,
sharing one table and one code path per Design Spec §1: the hash/expiry/
attempt-count/verify logic is identical between channels, only delivery
differs.

sha256, not bcrypt/argon2: OTPs are short-lived (5 min), low-entropy
6-digit codes, not long-lived credentials — there's nothing to gain from an
expensive hash here, and it would be a needless dependency.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.models.auth import OtpRequest
from app.services.auth.email_provider import NoEmailProviderConfiguredError, get_email_provider

OTP_LENGTH = 6
OTP_TTL_MINUTES = 5
MAX_ATTEMPTS = 5

Channel = Literal["sms", "email"]

__all__ = [
    "OtpVerificationError",
    "NoEmailProviderConfiguredError",
    "create_otp_request",
    "verify_otp",
    "get_email_provider",
]


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def generate_otp() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


def create_otp_request(
    db: DbSession, identifier: str, channel: Channel = "sms"
) -> tuple[OtpRequest, str | None]:
    """Creates and persists a new OtpRequest for either channel. Returns
    (request, raw_otp) — raw_otp is only non-None in dev-stub delivery
    mode, for the API response to echo back; a real delivery mode returns
    None here and sends the code out-of-band instead."""
    if settings.otp_delivery_mode == "stub" and not settings.database_url.startswith("sqlite"):
        raise RuntimeError(
            "otp_delivery_mode='stub' is not allowed against a non-SQLite database — "
            "this would leak real OTPs in the API response outside local dev. "
            "Set OTP_DELIVERY_MODE to a real delivery mode before deploying against Postgres."
        )

    otp = generate_otp()
    request = OtpRequest(
        phone_number=identifier if channel == "sms" else None,
        email=identifier if channel == "email" else None,
        otp_hash=_hash_otp(otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
        created_at=datetime.now(timezone.utc),
    )
    db.add(request)
    db.commit()

    if channel == "email" and settings.otp_delivery_mode != "stub":
        get_email_provider().send_email(
            to=identifier,
            subject="Your Unifolio verification code",
            body=f"Your Unifolio verification code is {otp}. It expires in {OTP_TTL_MINUTES} minutes.",
        )

    raw_otp = otp if settings.otp_delivery_mode == "stub" else None
    return request, raw_otp


class OtpVerificationError(Exception):
    """Any OTP verification failure — no pending request, expired, wrong code, or too many attempts."""


def verify_otp(db: DbSession, identifier: str, otp: str, channel: Channel = "sms") -> OtpRequest:
    """Verifies otp against the latest unverified OtpRequest for
    identifier on the given channel. Raises OtpVerificationError on any
    failure. On success, marks the request verified and returns it."""
    filter_kwargs = {"phone_number": identifier} if channel == "sms" else {"email": identifier}
    request = (
        db.query(OtpRequest)
        .filter_by(verified_at=None, **filter_kwargs)
        .order_by(OtpRequest.created_at.desc())
        .first()
    )
    if not request:
        raise OtpVerificationError("No pending OTP request for this identifier.")
    # SQLite (dev/tests) returns naive datetimes even for DateTime(timezone=True);
    # values are always written as UTC, so tag them as such. Postgres returns aware.
    expires_at = request.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise OtpVerificationError("OTP has expired. Request a new one.")
    if request.attempt_count >= MAX_ATTEMPTS:
        raise OtpVerificationError("Too many incorrect attempts. Request a new OTP.")

    if request.otp_hash != _hash_otp(otp):
        request.attempt_count += 1
        db.commit()
        raise OtpVerificationError("Incorrect OTP.")

    request.verified_at = datetime.now(timezone.utc)
    db.commit()
    return request
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/auth/test_otp.py -v`
Expected: PASS (all tests, existing and new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth/otp.py backend/tests/services/auth/test_otp.py
git commit -m "feat(auth): generalize OTP request/verify to support email channel"
```

---

## Task 4: `Session.auth_method` wiring

**Files:**
- Modify: `backend/app/services/auth/session.py`
- Modify: `backend/tests/services/auth/test_session.py`

**Interfaces:**
- Consumes: `AuthIdentityProvider` enum (Task 1).
- Produces: `create_session(db, user_id, auth_method: AuthIdentityProvider, device_info: str | None = None) -> tuple[SessionModel, str]` — `auth_method` becomes a required positional-or-keyword parameter (breaking signature change; every existing call site is updated in Task 9).

- [ ] **Step 1: Write the failing tests**

Read the existing `backend/tests/services/auth/test_session.py` first (it has its own `_session()` helper or reuses a fixture — check before editing) and update every `create_session(db, user_id)` call to `create_session(db, user_id, auth_method=AuthIdentityProvider.PHONE_OTP)`, adding `from app.models.enums import AuthIdentityProvider` to the imports. Then add:

```python
def test_create_session_records_auth_method():
    db = _session()
    user_id = uuid.uuid4()

    session, _ = create_session(db, user_id, auth_method=AuthIdentityProvider.GOOGLE)

    assert session.auth_method == AuthIdentityProvider.GOOGLE
```

(Match this test's `_session()`/fixture usage and `uuid` import to whatever pattern the existing file already uses — do not introduce a second, inconsistent DB-setup helper in the same file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/auth/test_session.py -v`
Expected: FAIL — `create_session()` doesn't accept `auth_method` yet, and existing calls also fail since `Session.auth_method` is `nullable=False` with no ORM-side default.

- [ ] **Step 3: Update `create_session`**

In `backend/app/services/auth/session.py`, add the import and update the function:

```python
from app.models.enums import AuthIdentityProvider


def create_session(
    db: DbSession, user_id: uuid.UUID, auth_method: AuthIdentityProvider, device_info: str | None = None
) -> tuple[SessionModel, str]:
    """Creates and persists a Session. Returns (session, raw_token) — the
    raw token is returned to the caller exactly once and never stored.
    `auth_method` records whichever method's verification directly produced
    this session (e.g. for a phone-gated signup, that's phone_otp, the
    completing method — not the originating Google/email identity)."""
    raw_token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    now = datetime.now(timezone.utc)
    session = SessionModel(
        user_id=user_id,
        session_token_hash=_hash_token(raw_token),
        auth_method=auth_method,
        created_at=now,
        expires_at=now + timedelta(days=SESSION_TTL_DAYS),
        last_active_at=now,
        device_info=device_info,
    )
    db.add(session)
    db.commit()
    return session, raw_token
```

Leave every other function in this file (`refresh_session`, `_extract_bearer_token`, `get_current_session`, `get_current_user`) unchanged — none of them touch `auth_method`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/auth/test_session.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite to confirm only the expected call sites remain broken**

Run: `cd backend && python -m pytest -v`
Expected: `tests/services/auth/test_session.py` now passes. `tests/api/test_auth_routes.py` and `tests/models/test_auth_identity_models.py` (if it constructs a `Session` directly — it doesn't in Task 1's version) should be the only remaining failures, fixed in Task 9.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/auth/session.py backend/tests/services/auth/test_session.py
git commit -m "feat(auth): record which method created each session"
```

---

## Task 5: Identity resolution — lookup, collision detection, precedence

**Files:**
- Create: `backend/app/services/auth/identity.py`
- Create: `backend/tests/services/auth/test_identity.py`

**Interfaces:**
- Consumes: `AuthIdentity`, `PendingIdentityVerification`, `AuthIdentityProvider` (Task 1); `User` (`app.models.user`).
- Produces:
  - `find_identity_by_subject(db, provider: AuthIdentityProvider, provider_subject: str) -> AuthIdentity | None`
  - `record_identity(db, user_id, provider, provider_subject, email, verified_at) -> AuthIdentity`
  - `PROVIDER_PRECEDENCE: dict[AuthIdentityProvider, int]` (lower = higher precedence: GOOGLE=0, EMAIL_OTP=1, PHONE_OTP=2)
  - `pick_primary_identity(identities: list[AuthIdentity]) -> AuthIdentity`
  - `refresh_denormalized_email(db, user) -> None`
  - `EmailCollisionResult` (a `NamedTuple` with `kind: Literal["auto_link", "link_required", "none"]`, `matched_user_id: uuid.UUID | None`)
  - `resolve_email_collision(db, email: str) -> EmailCollisionResult`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/auth/test_identity.py`:

```python
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.auth import AuthIdentity, PendingIdentityVerification
from app.models.enums import AuthIdentityProvider
from app.models.user import User
from app.services.auth.identity import (
    find_identity_by_subject,
    pick_primary_identity,
    record_identity,
    refresh_denormalized_email,
    resolve_email_collision,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[User.__table__, AuthIdentity.__table__, PendingIdentityVerification.__table__]
    )
    return sessionmaker(autoflush=False, bind=engine)()


def _user(db, phone="+919999999999") -> User:
    user = User(id=uuid.uuid4(), phone_number=phone, created_at=datetime.now(timezone.utc))
    db.add(user)
    db.commit()
    return user


def test_find_identity_by_subject_returns_none_when_absent():
    db = _session()
    assert find_identity_by_subject(db, AuthIdentityProvider.GOOGLE, "no-such-sub") is None


def test_record_identity_creates_and_is_findable():
    db = _session()
    user = _user(db)
    now = datetime.now(timezone.utc)

    record_identity(db, user.id, AuthIdentityProvider.GOOGLE, "sub-1", "a@example.com", now)

    found = find_identity_by_subject(db, AuthIdentityProvider.GOOGLE, "sub-1")
    assert found is not None
    assert found.user_id == user.id
    assert found.email == "a@example.com"


def test_pick_primary_identity_prefers_google_over_email_over_phone():
    now = datetime.now(timezone.utc)
    phone = AuthIdentity(user_id=uuid.uuid4(), provider=AuthIdentityProvider.PHONE_OTP, provider_subject="p", identifier_verified_at=now, created_at=now, last_used_at=now)
    email = AuthIdentity(user_id=uuid.uuid4(), provider=AuthIdentityProvider.EMAIL_OTP, provider_subject="e", identifier_verified_at=now, created_at=now, last_used_at=now)
    google = AuthIdentity(user_id=uuid.uuid4(), provider=AuthIdentityProvider.GOOGLE, provider_subject="g", identifier_verified_at=now, created_at=now, last_used_at=now)

    assert pick_primary_identity([phone, email, google]) is google
    assert pick_primary_identity([phone, email]) is email
    assert pick_primary_identity([phone]) is phone


def test_refresh_denormalized_email_uses_highest_precedence_identity():
    db = _session()
    user = _user(db)
    now = datetime.now(timezone.utc)
    record_identity(db, user.id, AuthIdentityProvider.EMAIL_OTP, "e@example.com", "e@example.com", now)
    record_identity(db, user.id, AuthIdentityProvider.GOOGLE, "g-sub", "g@example.com", now)

    refresh_denormalized_email(db, user)

    assert user.email == "g@example.com"


def test_refresh_denormalized_email_is_noop_when_no_email_bearing_identity():
    db = _session()
    user = _user(db)
    now = datetime.now(timezone.utc)
    record_identity(db, user.id, AuthIdentityProvider.PHONE_OTP, user.phone_number, None, now)

    refresh_denormalized_email(db, user)

    assert user.email is None


def test_resolve_email_collision_auto_link_when_another_verified_identity_matches():
    db = _session()
    existing_user = _user(db, phone="+919000000001")
    now = datetime.now(timezone.utc)
    record_identity(db, existing_user.id, AuthIdentityProvider.EMAIL_OTP, "shared@example.com", "shared@example.com", now)

    result = resolve_email_collision(db, "shared@example.com")

    assert result.kind == "auto_link"
    assert result.matched_user_id == existing_user.id


def test_resolve_email_collision_link_required_when_only_denormalized_email_matches():
    db = _session()
    existing_user = _user(db, phone="+919000000002")
    existing_user.email = "unverified@example.com"  # never separately verified — no AuthIdentity row for it
    db.commit()

    result = resolve_email_collision(db, "unverified@example.com")

    assert result.kind == "link_required"
    assert result.matched_user_id == existing_user.id


def test_resolve_email_collision_none_when_no_match():
    db = _session()
    result = resolve_email_collision(db, "nobody@example.com")
    assert result.kind == "none"
    assert result.matched_user_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/auth/test_identity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.auth.identity'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/auth/identity.py`:

```python
"""Identity lookup, denormalized-email refresh, and email-collision
resolution — Design Spec §1/§4. Phone-first verification never calls
resolve_email_collision (phone carries no email claim, so it can't
collide) — see identity_flow.py (Task 6) for where phone stays on its own
simpler path.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, NamedTuple

from sqlalchemy.orm import Session as DbSession

from app.models.auth import AuthIdentity
from app.models.enums import AuthIdentityProvider
from app.models.user import User

# Lower value = higher precedence. Design Spec §1: "Identity precedence:
# Google > Email > Phone" — applied wherever only one identity can be
# shown or selected.
PROVIDER_PRECEDENCE: dict[AuthIdentityProvider, int] = {
    AuthIdentityProvider.GOOGLE: 0,
    AuthIdentityProvider.EMAIL_OTP: 1,
    AuthIdentityProvider.PHONE_OTP: 2,
}


def find_identity_by_subject(
    db: DbSession, provider: AuthIdentityProvider, provider_subject: str
) -> AuthIdentity | None:
    return db.query(AuthIdentity).filter_by(provider=provider, provider_subject=provider_subject).first()


def record_identity(
    db: DbSession,
    user_id: uuid.UUID,
    provider: AuthIdentityProvider,
    provider_subject: str,
    email: str | None,
    verified_at: datetime,
) -> AuthIdentity:
    identity = AuthIdentity(
        user_id=user_id,
        provider=provider,
        provider_subject=provider_subject,
        email=email,
        identifier_verified_at=verified_at,
        created_at=verified_at,
        last_used_at=verified_at,
    )
    db.add(identity)
    db.commit()
    return identity


def pick_primary_identity(identities: list[AuthIdentity]) -> AuthIdentity:
    return min(identities, key=lambda i: PROVIDER_PRECEDENCE[i.provider])


def refresh_denormalized_email(db: DbSession, user: User) -> None:
    """Sets user.email from the highest-precedence identity that has one.
    No-op if the account has no email-bearing identity at all."""
    identities = db.query(AuthIdentity).filter_by(user_id=user.id).all()
    with_email = [i for i in identities if i.email]
    if not with_email:
        return
    user.email = pick_primary_identity(with_email).email
    db.commit()


class EmailCollisionResult(NamedTuple):
    kind: Literal["auto_link", "link_required", "none"]
    matched_user_id: uuid.UUID | None


def resolve_email_collision(db: DbSession, email: str) -> EmailCollisionResult:
    """Design Spec §4's three-way collision check, on a new identity's
    verified email:
    1. Matches another verified AuthIdentity's email (any provider, any
       user) -> auto_link.
    2. Matches only a User's denormalized, never-separately-verified
       `email` field -> link_required.
    3. No match -> none.
    """
    verified_match = db.query(AuthIdentity).filter_by(email=email).first()
    if verified_match is not None:
        return EmailCollisionResult(kind="auto_link", matched_user_id=verified_match.user_id)

    denormalized_match = db.query(User).filter_by(email=email).first()
    if denormalized_match is not None:
        return EmailCollisionResult(kind="link_required", matched_user_id=denormalized_match.id)

    return EmailCollisionResult(kind="none", matched_user_id=None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/auth/test_identity.py -v`
Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth/identity.py backend/tests/services/auth/test_identity.py
git commit -m "feat(auth): identity lookup, precedence, and email-collision resolution"
```

---

## Task 6: Pending-verification tokens and completion flows (phone gate + step-up link)

**Files:**
- Modify: `backend/app/services/auth/identity.py`
- Modify: `backend/tests/services/auth/test_identity.py`

**Interfaces:**
- Consumes: `resolve_email_collision`, `record_identity`, `refresh_denormalized_email`, `find_identity_by_subject` (Task 5); `PendingIdentityVerification` (Task 1).
- Produces:
  - `PENDING_VERIFICATION_TTL_MINUTES = 10`
  - `create_pending_verification(db, provider, provider_subject, email, email_verified, matched_user_id) -> tuple[PendingIdentityVerification, str]` (returns raw token)
  - `PendingVerificationError(Exception)`
  - `_consume_pending_verification(db, raw_token) -> PendingIdentityVerification` (validates hash + expiry, raises `PendingVerificationError`, does **not** delete — caller deletes after finishing)
  - `complete_phone_gate_signup(db, raw_token, phone_number) -> uuid.UUID` — only valid when `matched_user_id is None`
  - `attach_pending_identity(db, raw_token, resolved_user_id) -> uuid.UUID` — only valid when `matched_user_id` is set and matches `resolved_user_id`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/services/auth/test_identity.py` (add imports for `datetime, timedelta`, and the new functions):

```python
from datetime import timedelta

from app.services.auth.identity import (
    PendingVerificationError,
    attach_pending_identity,
    complete_phone_gate_signup,
    create_pending_verification,
)
```

```python
def test_create_pending_verification_returns_findable_token():
    db = _session()
    pending, raw_token = create_pending_verification(
        db, AuthIdentityProvider.GOOGLE, "g-sub-1", "new@example.com", True, matched_user_id=None
    )
    assert pending.matched_user_id is None
    assert raw_token  # non-empty, returned exactly once


def test_complete_phone_gate_signup_creates_user_with_both_identities():
    db = _session()
    _, raw_token = create_pending_verification(
        db, AuthIdentityProvider.GOOGLE, "g-sub-2", "new2@example.com", True, matched_user_id=None
    )

    user_id = complete_phone_gate_signup(db, raw_token, "+919111111111")

    user = db.get(User, user_id)
    assert user is not None
    assert user.phone_number == "+919111111111"
    assert user.email == "new2@example.com"
    assert find_identity_by_subject(db, AuthIdentityProvider.PHONE_OTP, "+919111111111") is not None
    assert find_identity_by_subject(db, AuthIdentityProvider.GOOGLE, "g-sub-2") is not None


def test_complete_phone_gate_signup_rejects_expired_token():
    db = _session()
    pending, raw_token = create_pending_verification(
        db, AuthIdentityProvider.GOOGLE, "g-sub-3", "new3@example.com", True, matched_user_id=None
    )
    pending.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    with pytest.raises(PendingVerificationError, match="expired"):
        complete_phone_gate_signup(db, raw_token, "+919222222222")


def test_complete_phone_gate_signup_rejects_a_link_completion_token():
    db = _session()
    existing_user = _user(db, phone="+919333333333")
    _, raw_token = create_pending_verification(
        db, AuthIdentityProvider.GOOGLE, "g-sub-4", "link@example.com", True, matched_user_id=existing_user.id
    )

    with pytest.raises(PendingVerificationError, match="linking"):
        complete_phone_gate_signup(db, raw_token, "+919444444444")


def test_attach_pending_identity_links_to_the_matched_user():
    db = _session()
    existing_user = _user(db, phone="+919555555555")
    existing_user.email = "unverified@example.com"
    db.commit()
    _, raw_token = create_pending_verification(
        db, AuthIdentityProvider.GOOGLE, "g-sub-5", "unverified@example.com", True, matched_user_id=existing_user.id
    )

    returned_user_id = attach_pending_identity(db, raw_token, existing_user.id)

    assert returned_user_id == existing_user.id
    assert find_identity_by_subject(db, AuthIdentityProvider.GOOGLE, "g-sub-5") is not None
    db.refresh(existing_user)
    assert existing_user.email == "unverified@example.com"  # Google outranks nothing new here, still refreshed via precedence


def test_attach_pending_identity_rejects_mismatched_resolved_user():
    db = _session()
    existing_user = _user(db, phone="+919666666666")
    other_user = _user(db, phone="+919777777777")
    _, raw_token = create_pending_verification(
        db, AuthIdentityProvider.GOOGLE, "g-sub-6", "x@example.com", True, matched_user_id=existing_user.id
    )

    with pytest.raises(PendingVerificationError, match="doesn't match"):
        attach_pending_identity(db, raw_token, other_user.id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/auth/test_identity.py -v`
Expected: FAIL — the new names don't exist in `identity.py` yet.

- [ ] **Step 3: Extend the implementation**

Append to `backend/app/services/auth/identity.py` (add `hashlib`, `secrets`, `timedelta`, `timezone` to imports, plus `User`'s `created_at` needs `datetime.now(timezone.utc)`):

```python
import hashlib
import secrets
from datetime import timedelta, timezone

from app.models.auth import PendingIdentityVerification

PENDING_VERIFICATION_TOKEN_BYTES = 32
PENDING_VERIFICATION_TTL_MINUTES = 10


def _hash_pending_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_pending_verification(
    db: DbSession,
    provider: AuthIdentityProvider,
    provider_subject: str,
    email: str | None,
    email_verified: bool,
    matched_user_id: uuid.UUID | None,
) -> tuple[PendingIdentityVerification, str]:
    raw_token = secrets.token_urlsafe(PENDING_VERIFICATION_TOKEN_BYTES)
    now = datetime.now(timezone.utc)
    pending = PendingIdentityVerification(
        provider=provider,
        provider_subject=provider_subject,
        email=email,
        email_verified=email_verified,
        matched_user_id=matched_user_id,
        token_hash=_hash_pending_token(raw_token),
        expires_at=now + timedelta(minutes=PENDING_VERIFICATION_TTL_MINUTES),
        created_at=now,
    )
    db.add(pending)
    db.commit()
    return pending, raw_token


class PendingVerificationError(Exception):
    """Any failure consuming a pending_identity_verifications token —
    not found, expired, or used for the wrong completion path."""


def _consume_pending_verification(db: DbSession, raw_token: str) -> PendingIdentityVerification:
    token_hash = _hash_pending_token(raw_token)
    pending = db.query(PendingIdentityVerification).filter_by(token_hash=token_hash).first()
    if not pending:
        raise PendingVerificationError("Invalid or already-used verification token.")
    expires_at = pending.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise PendingVerificationError("This verification has expired. Please start over.")
    return pending


def complete_phone_gate_signup(db: DbSession, raw_token: str, phone_number: str) -> uuid.UUID:
    """Only for a brand-new-signup pending record (matched_user_id IS
    NULL) — atomically creates the User plus both identities. Design Spec
    §1's mandatory phone gate."""
    pending = _consume_pending_verification(db, raw_token)
    if pending.matched_user_id is not None:
        raise PendingVerificationError(
            "This verification is for linking to an existing account, not creating a new one."
        )

    now = datetime.now(timezone.utc)
    user = User(phone_number=phone_number, email=pending.email, created_at=now)
    db.add(user)
    db.flush()
    record_identity(db, user.id, AuthIdentityProvider.PHONE_OTP, phone_number, None, now)
    record_identity(db, user.id, pending.provider, pending.provider_subject, pending.email, now)
    db.delete(pending)
    db.commit()
    return user.id


def attach_pending_identity(db: DbSession, raw_token: str, resolved_user_id: uuid.UUID) -> uuid.UUID:
    """After ANY re-auth method (phone/email/Google) resolves to
    resolved_user_id, attaches the pending record's identity to that
    user. Requires matched_user_id to already equal resolved_user_id —
    guards against a pending token being replayed against the wrong
    account."""
    pending = _consume_pending_verification(db, raw_token)
    if pending.matched_user_id is None or pending.matched_user_id != resolved_user_id:
        raise PendingVerificationError("This verification token doesn't match the account you're linking to.")

    now = datetime.now(timezone.utc)
    record_identity(db, resolved_user_id, pending.provider, pending.provider_subject, pending.email, now)
    user = db.get(User, resolved_user_id)
    refresh_denormalized_email(db, user)
    db.delete(pending)
    db.commit()
    return resolved_user_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/auth/test_identity.py -v`
Expected: PASS (all tests, existing and new — 14 total).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth/identity.py backend/tests/services/auth/test_identity.py
git commit -m "feat(auth): pending-verification tokens and phone-gate/link completion flows"
```

---

## Task 7: Google ID-token verification

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/services/auth/google_oauth.py`
- Create: `backend/tests/services/auth/test_google_oauth.py`
- Modify: `backend/app/config.py`

**Interfaces:**
- Produces: `settings.google_oauth_client_id: str` (new config field); `GoogleTokenVerificationError(Exception)`; `GoogleClaims` (`NamedTuple`: `sub: str`, `email: str | None`, `email_verified: bool`); `verify_google_id_token(id_token: str) -> GoogleClaims`.

- [ ] **Step 1: Add the dependency**

In `backend/requirements.txt`, add a new line (alphabetical position doesn't matter in this file — append):

```
google-auth>=2.35.0
```

Run: `cd backend && pip install -r requirements.txt`
Expected: `google-auth` installs successfully.

- [ ] **Step 2: Add the config field**

In `backend/app/config.py`, add one field to `Settings`:

```python
    google_oauth_client_id: str = ""
```

(Empty-string default so local dev without a configured Client ID doesn't crash on import — `verify_google_id_token` raises clearly if it's unset, see Step 4.)

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/services/auth/test_google_oauth.py`:

```python
import pytest

from app.services.auth.google_oauth import GoogleTokenVerificationError, verify_google_id_token


def test_verify_google_id_token_returns_claims_on_success(monkeypatch):
    import app.services.auth.google_oauth as google_oauth_module

    monkeypatch.setattr(google_oauth_module.settings, "google_oauth_client_id", "test-client-id")
    monkeypatch.setattr(
        google_oauth_module.id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "sub": "google-sub-123",
            "email": "a@example.com",
            "email_verified": True,
            "iss": "https://accounts.google.com",
        },
    )

    claims = verify_google_id_token("fake-jwt")

    assert claims.sub == "google-sub-123"
    assert claims.email == "a@example.com"
    assert claims.email_verified is True


def test_verify_google_id_token_wraps_verification_failures(monkeypatch):
    import app.services.auth.google_oauth as google_oauth_module
    from google.auth.exceptions import GoogleAuthError

    monkeypatch.setattr(google_oauth_module.settings, "google_oauth_client_id", "test-client-id")

    def _raise(token, request, audience):
        raise GoogleAuthError("bad signature")

    monkeypatch.setattr(google_oauth_module.id_token, "verify_oauth2_token", _raise)

    with pytest.raises(GoogleTokenVerificationError, match="bad signature"):
        verify_google_id_token("fake-jwt")


def test_verify_google_id_token_requires_client_id_configured(monkeypatch):
    import app.services.auth.google_oauth as google_oauth_module

    monkeypatch.setattr(google_oauth_module.settings, "google_oauth_client_id", "")

    with pytest.raises(GoogleTokenVerificationError, match="not configured"):
        verify_google_id_token("fake-jwt")


def test_verify_google_id_token_defaults_missing_email_verified_to_false(monkeypatch):
    import app.services.auth.google_oauth as google_oauth_module

    monkeypatch.setattr(google_oauth_module.settings, "google_oauth_client_id", "test-client-id")
    monkeypatch.setattr(
        google_oauth_module.id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {"sub": "s", "iss": "https://accounts.google.com"},
    )

    claims = verify_google_id_token("fake-jwt")

    assert claims.email is None
    assert claims.email_verified is False
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/auth/test_google_oauth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.auth.google_oauth'`.

- [ ] **Step 5: Write the implementation**

Create `backend/app/services/auth/google_oauth.py`:

```python
"""Google ID-token verification — Design Spec §2.

ID-token-only, not the authorization-code exchange: no client secret is
needed, this is pure JWT signature verification against Google's published
public keys via the `google-auth` library.
"""

from __future__ import annotations

from typing import NamedTuple

from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import settings


class GoogleTokenVerificationError(Exception):
    pass


class GoogleClaims(NamedTuple):
    sub: str
    email: str | None
    email_verified: bool


def verify_google_id_token(raw_id_token: str) -> GoogleClaims:
    if not settings.google_oauth_client_id:
        raise GoogleTokenVerificationError("Google OAuth Client ID is not configured.")

    try:
        claims = id_token.verify_oauth2_token(
            raw_id_token, google_requests.Request(), settings.google_oauth_client_id
        )
    except (GoogleAuthError, ValueError) as exc:
        raise GoogleTokenVerificationError(str(exc)) from exc

    return GoogleClaims(
        sub=claims["sub"],
        email=claims.get("email"),
        email_verified=bool(claims.get("email_verified", False)),
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/auth/test_google_oauth.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/app/config.py backend/app/services/auth/google_oauth.py \
  backend/tests/services/auth/test_google_oauth.py
git commit -m "feat(auth): Google ID-token verification"
```

---

## Task 8: Request/response schemas for the three-way verify outcome

**Files:**
- Modify: `backend/app/services/auth/schemas.py`

**Interfaces:**
- Produces: widened `OtpRequestBody` (`phone_number: str | None`, `email: str | None`, validated exactly-one), widened `OtpVerifyBody` (adds `email`, `pending_token`, validated exactly-one-of-phone/email), `LinkRequiredDetail`, `LinkRequiredResponse`, `PhoneRequiredDetail`, `PhoneRequiredResponse`, `GoogleAuthBody` (`id_token: str`, `pending_token: str | None`), `PROVIDER_TO_METHOD_LABEL: dict[AuthIdentityProvider, str]`.

- [ ] **Step 1: Write the failing tests**

This task is pure Pydantic schema validation — test it directly rather than through a route (routes are Task 9/10). Create no new test file; instead these are exercised end-to-end in Task 9/10's route tests. Skip straight to implementation, but first run a quick manual sanity check to catch typos before wiring routes:

Run: `cd backend && python -c "
from app.services.auth.schemas import OtpRequestBody
try:
    OtpRequestBody()
    print('FAIL: should have raised')
except Exception as e:
    print('OK:', e)
"`
Expected: this fails right now because `OtpRequestBody` doesn't yet validate exactly-one — confirms the gap before fixing it.

- [ ] **Step 2: Write the implementation**

Replace `backend/app/services/auth/schemas.py` in full:

```python
from __future__ import annotations

from pydantic import BaseModel, model_validator

from app.models.enums import AuthIdentityProvider, InvestorType, PrimaryGoal

PROVIDER_TO_METHOD_LABEL: dict[AuthIdentityProvider, str] = {
    AuthIdentityProvider.PHONE_OTP: "phone",
    AuthIdentityProvider.EMAIL_OTP: "email",
    AuthIdentityProvider.GOOGLE: "google",
}


class OtpRequestBody(BaseModel):
    phone_number: str | None = None
    email: str | None = None

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> "OtpRequestBody":
        if (self.phone_number is None) == (self.email is None):
            raise ValueError("Provide exactly one of phone_number or email.")
        return self


class OtpRequestResponse(BaseModel):
    message: str
    otp: str | None = None  # only populated in dev-stub delivery mode


class OtpVerifyBody(BaseModel):
    phone_number: str | None = None
    email: str | None = None
    otp: str
    pending_token: str | None = None

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> "OtpVerifyBody":
        if (self.phone_number is None) == (self.email is None):
            raise ValueError("Provide exactly one of phone_number or email.")
        return self


class OtpVerifyResponse(BaseModel):
    session_token: str
    user_id: str
    onboarding_step: str | None
    onboarding_completed: bool


class LinkRequiredDetail(BaseModel):
    token: str
    matched_email: str
    existing_method: str  # "phone" | "email" | "google"


class LinkRequiredResponse(BaseModel):
    link_required: LinkRequiredDetail


class PhoneRequiredDetail(BaseModel):
    token: str
    prefill_email: str | None


class PhoneRequiredResponse(BaseModel):
    phone_required: PhoneRequiredDetail


class GoogleAuthBody(BaseModel):
    id_token: str
    pending_token: str | None = None


class SessionRefreshResponse(BaseModel):
    expires_at: str


class UpdateMeBody(BaseModel):
    onboarding_step: str | None = None
    investor_type: InvestorType | None = None
    primary_goal: PrimaryGoal | None = None
    onboarding_completed: bool | None = None


class MeResponse(BaseModel):
    user_id: str
    phone_number: str
    email: str | None
    onboarding_step: str | None
    onboarding_completed: bool
    investor_type: InvestorType | None
    primary_goal: PrimaryGoal | None
```

- [ ] **Step 3: Re-run the sanity check**

Run: `cd backend && python -c "
from app.services.auth.schemas import OtpRequestBody
try:
    OtpRequestBody()
    print('FAIL: should have raised')
except Exception as e:
    print('OK:', e)
"`
Expected: `OK: ...` (a `ValidationError` message).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/auth/schemas.py
git commit -m "feat(auth): widen request/response schemas for email, Google, and the three-way verify outcome"
```

---

## Task 9: `/auth/otp/request` and `/auth/otp/verify` routes — email channel, phone gate, linking

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/tests/api/test_auth_routes.py`

**Interfaces:**
- Consumes: everything from Tasks 1–8.
- Produces: `POST /auth/otp/request` accepts `{phone_number}` or `{email}`; `POST /auth/otp/verify` accepts `{phone_number|email, otp, pending_token?}` and returns `OtpVerifyResponse | LinkRequiredResponse | PhoneRequiredResponse`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/api/test_auth_routes.py`:

```python
def test_otp_request_accepts_email(client):
    response = client.post("/auth/otp/request", json={"email": "a@example.com"})
    assert response.status_code == 200
    assert response.json()["otp"] is not None


def test_otp_request_rejects_both_identifiers(client):
    response = client.post("/auth/otp/request", json={"phone_number": "+919999999999", "email": "a@example.com"})
    assert response.status_code == 422


def test_otp_verify_email_first_signup_with_no_collision_returns_phone_required(client):
    email = "newsignup@example.com"
    otp = client.post("/auth/otp/request", json={"email": email}).json()["otp"]

    response = client.post("/auth/otp/verify", json={"email": email, "otp": otp})

    assert response.status_code == 200
    body = response.json()
    assert "phone_required" in body
    assert body["phone_required"]["token"]
    assert body["phone_required"]["prefill_email"] == email


def test_otp_verify_completing_phone_gate_creates_session(client):
    email = "gatecomplete@example.com"
    email_otp = client.post("/auth/otp/request", json={"email": email}).json()["otp"]
    gate = client.post("/auth/otp/verify", json={"email": email, "otp": email_otp}).json()
    pending_token = gate["phone_required"]["token"]

    phone = "+919123456789"
    phone_otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    response = client.post(
        "/auth/otp/verify",
        json={"phone_number": phone, "otp": phone_otp, "pending_token": pending_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['session_token']}"})
    assert me.json()["phone_number"] == phone
    assert me.json()["email"] == email


def test_otp_verify_email_login_for_already_linked_email(client):
    email = "returning@example.com"
    email_otp = client.post("/auth/otp/request", json={"email": email}).json()["otp"]
    gate = client.post("/auth/otp/verify", json={"email": email, "otp": email_otp}).json()
    phone = "+919198765432"
    phone_otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    first = client.post(
        "/auth/otp/verify",
        json={"phone_number": phone, "otp": phone_otp, "pending_token": gate["phone_required"]["token"]},
    ).json()

    email_otp_2 = client.post("/auth/otp/request", json={"email": email}).json()["otp"]
    second = client.post("/auth/otp/verify", json={"email": email, "otp": email_otp_2}).json()

    assert second["session_token"]
    assert second["user_id"] == first["user_id"]


def test_otp_verify_email_matching_unverified_users_email_returns_link_required(client):
    phone = "+919111222333"
    phone_otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    first = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": phone_otp}).json()
    client.patch(
        "/auth/me",
        json={},  # no direct email-set endpoint exists; set it via ORM in-process instead
        headers={"Authorization": f"Bearer {first['session_token']}"},
    )
    # No public endpoint sets users.email directly in this codebase yet — write it
    # straight to the test DB via the app's own session factory instead.
    from app.db.session import SessionLocal  # noqa: not used; see note below
```

The last test above needs a way to set `users.email` without a public endpoint (none exists — `email` is purely denormalized, per the spec, and nothing in this plan adds a way to set it directly). Replace that last test with one that goes through the `client` fixture's own overridden DB dependency instead:

```python
def test_otp_verify_email_matching_unverified_users_email_returns_link_required(client):
    from app.db.session import get_db
    from app.models.user import User

    phone = "+919111222333"
    phone_otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    first = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": phone_otp}).json()

    db = next(client.app.dependency_overrides[get_db]())
    user = db.query(User).filter_by(phone_number=phone).one()
    user.email = "prelinked@example.com"
    db.commit()
    db.close()

    otp = client.post("/auth/otp/request", json={"email": "prelinked@example.com"}).json()["otp"]
    response = client.post("/auth/otp/verify", json={"email": "prelinked@example.com", "otp": otp})

    body = response.json()
    assert "link_required" in body
    assert body["link_required"]["existing_method"] == "phone"


def test_otp_verify_completing_a_link_via_phone(client):
    from app.db.session import get_db
    from app.models.user import User

    phone = "+919444555666"
    phone_otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    first = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": phone_otp}).json()

    db = next(client.app.dependency_overrides[get_db]())
    user = db.query(User).filter_by(phone_number=phone).one()
    user.email = "tolink@example.com"
    db.commit()
    db.close()

    email_otp = client.post("/auth/otp/request", json={"email": "tolink@example.com"}).json()["otp"]
    link = client.post("/auth/otp/verify", json={"email": "tolink@example.com", "otp": email_otp}).json()
    pending_token = link["link_required"]["token"]

    phone_otp_2 = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    response = client.post(
        "/auth/otp/verify",
        json={"phone_number": phone, "otp": phone_otp_2, "pending_token": pending_token},
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == first["user_id"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_auth_routes.py -v`
Expected: FAIL — current routes only accept `phone_number`, don't return `phone_required`/`link_required`, and `create_session()` calls in the current route are missing the now-required `auth_method` argument.

- [ ] **Step 3: Rewrite the routes**

Replace the OTP-related portion of `backend/app/api/auth.py` — keep `/session/refresh`, `/me` (GET/PATCH) exactly as they are today, and replace only the imports and the two OTP routes:

```python
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.db.session import get_db
from app.models.auth import Session as SessionModel
from app.models.enums import AuthIdentityProvider
from app.models.user import User
from app.services.auth.identity import (
    PendingVerificationError,
    attach_pending_identity,
    complete_phone_gate_signup,
    create_pending_verification,
    find_identity_by_subject,
    pick_primary_identity,
    record_identity,
    resolve_email_collision,
)
from app.services.auth.otp import OtpVerificationError, create_otp_request, verify_otp
from app.services.auth.schemas import (
    GoogleAuthBody,
    LinkRequiredDetail,
    LinkRequiredResponse,
    MeResponse,
    OtpRequestBody,
    OtpRequestResponse,
    OtpVerifyBody,
    OtpVerifyResponse,
    PhoneRequiredDetail,
    PhoneRequiredResponse,
    PROVIDER_TO_METHOD_LABEL,
    SessionRefreshResponse,
    UpdateMeBody,
)
from app.services.auth.session import create_session, get_current_session, get_current_user, refresh_session

router = APIRouter(prefix="/auth", tags=["auth"])


def _session_response(user_id, auth_method: AuthIdentityProvider, db: DbSession) -> OtpVerifyResponse:
    user = db.get(User, user_id)
    _, raw_token = create_session(db, user_id, auth_method=auth_method)
    return OtpVerifyResponse(
        session_token=raw_token,
        user_id=str(user_id),
        onboarding_step=user.onboarding_step,
        onboarding_completed=user.onboarding_completed_at is not None,
    )


def _existing_method_label(db: DbSession, user_id) -> str:
    identities = db.query(SessionModel).session.query  # placeholder removed below
    return ""


@router.post("/otp/request", response_model=OtpRequestResponse)
def request_otp(body: OtpRequestBody, db: DbSession = Depends(get_db)):
    channel = "sms" if body.phone_number is not None else "email"
    identifier = body.phone_number if channel == "sms" else body.email
    _, raw_otp = create_otp_request(db, identifier, channel=channel)
    return OtpRequestResponse(message="OTP sent.", otp=raw_otp)


@router.post("/otp/verify", response_model=OtpVerifyResponse | LinkRequiredResponse | PhoneRequiredResponse)
def verify_otp_route(body: OtpVerifyBody, db: DbSession = Depends(get_db)):
    channel = "sms" if body.phone_number is not None else "email"
    identifier = body.phone_number if channel == "sms" else body.email
    provider = AuthIdentityProvider.PHONE_OTP if channel == "sms" else AuthIdentityProvider.EMAIL_OTP

    try:
        verify_otp(db, identifier, body.otp, channel=channel)
    except OtpVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if body.pending_token:
        try:
            if channel != "sms":
                # Only phone can complete the mandatory-phone-gate case;
                # an email re-auth here can only be a link completion.
                existing = find_identity_by_subject(db, provider, identifier)
                if existing is None:
                    raise HTTPException(status_code=401, detail="This account isn't linked yet.")
                user_id = attach_pending_identity(db, body.pending_token, existing.user_id)
            else:
                existing = find_identity_by_subject(db, provider, identifier)
                if existing is not None:
                    user_id = attach_pending_identity(db, body.pending_token, existing.user_id)
                else:
                    user_id = complete_phone_gate_signup(db, body.pending_token, identifier)
        except PendingVerificationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return _session_response(user_id, AuthIdentityProvider.PHONE_OTP if channel == "sms" else provider, db)

    existing = find_identity_by_subject(db, provider, identifier)
    if existing is not None:
        return _session_response(existing.user_id, provider, db)

    if channel == "sms":
        # Phone never collision-checks (no email claim to collide with) —
        # brand-new phone number always completes signup immediately.
        now = datetime.now(timezone.utc)
        user = User(phone_number=identifier, created_at=now)
        db.add(user)
        db.flush()
        record_identity(db, user.id, AuthIdentityProvider.PHONE_OTP, identifier, None, now)
        db.commit()
        return _session_response(user.id, AuthIdentityProvider.PHONE_OTP, db)

    # Email channel with no existing identity: run the collision check.
    collision = resolve_email_collision(db, identifier)
    if collision.kind == "auto_link":
        now = datetime.now(timezone.utc)
        record_identity(db, collision.matched_user_id, AuthIdentityProvider.EMAIL_OTP, identifier, identifier, now)
        user = db.get(User, collision.matched_user_id)
        from app.services.auth.identity import refresh_denormalized_email

        refresh_denormalized_email(db, user)
        return _session_response(collision.matched_user_id, AuthIdentityProvider.EMAIL_OTP, db)

    if collision.kind == "link_required":
        matched_user = db.get(User, collision.matched_user_id)
        identities = db.query(SessionModel.user_id).filter_by(user_id=matched_user.id)  # unused, remove
        from app.models.auth import AuthIdentity as _AuthIdentity

        matched_identities = db.query(_AuthIdentity).filter_by(user_id=matched_user.id).all()
        existing_method_provider = (
            pick_primary_identity(matched_identities) if matched_identities else AuthIdentityProvider.PHONE_OTP
        ).provider if matched_identities else AuthIdentityProvider.PHONE_OTP
        pending, raw_token = create_pending_verification(
            db, AuthIdentityProvider.EMAIL_OTP, identifier, identifier, True, matched_user_id=matched_user.id
        )
        return LinkRequiredResponse(
            link_required=LinkRequiredDetail(
                token=raw_token,
                matched_email=identifier,
                existing_method=PROVIDER_TO_METHOD_LABEL[existing_method_provider],
            )
        )

    # kind == "none": brand-new signup, still needs the mandatory phone step.
    pending, raw_token = create_pending_verification(
        db, AuthIdentityProvider.EMAIL_OTP, identifier, identifier, True, matched_user_id=None
    )
    return PhoneRequiredResponse(phone_required=PhoneRequiredDetail(token=raw_token, prefill_email=identifier))
```

The two lines above marked "unused, remove" and the stray `_existing_method_label` stub are leftover exploration — delete both before running tests: remove the entire `_existing_method_label` function, and remove the `identities = db.query(SessionModel.user_id)...` line inside the `link_required` branch (it's dead code, not used).

Also update `get_me`/`update_me`'s existing bodies: they don't call `create_session`, so they need **no** changes — leave them exactly as they are today.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_auth_routes.py -v`
Expected: PASS (all tests, existing and new).

If `existing_method` comes back wrong in `test_otp_verify_email_matching_unverified_users_email_returns_link_required` (expects `"phone"`), check that `matched_identities` is being fetched for the *matched* user (the phone-first user, who has exactly one `AuthIdentity` row: `phone_otp`) — `pick_primary_identity` on a single-item list just returns that item, so `existing_method_provider` should resolve to `AuthIdentityProvider.PHONE_OTP` → `"phone"` via `PROVIDER_TO_METHOD_LABEL`.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS. If `tests/api/test_auth_routes.py`'s original tests (from before this plan) fail on `assert body["onboarding_step"] is None`-style assertions, check nothing in `_session_response` accidentally changed `MeResponse`/`OtpVerifyResponse` shapes — they shouldn't have.

- [ ] **Step 6: Clean up the route file**

Re-read `backend/app/api/auth.py` in full and remove any remaining dead imports or unused variables introduced while drafting Step 3 (e.g. the `from app.services.auth.identity import refresh_denormalized_email` inline import should move to the top-level import block alongside the other `identity` imports, not sit inline mid-function).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/auth.py backend/tests/api/test_auth_routes.py
git commit -m "feat(auth): wire email channel, phone gate, and account linking into OTP routes"
```

---

## Task 10: `POST /auth/oauth/google` route

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/tests/api/test_auth_routes.py`

**Interfaces:**
- Consumes: `verify_google_id_token` (Task 7), `GoogleAuthBody` (Task 8), everything from Task 9's helpers (`_session_response`, `find_identity_by_subject`, `resolve_email_collision`, `create_pending_verification`, `attach_pending_identity`, `pick_primary_identity`).
- Produces: `POST /auth/oauth/google` accepting `{id_token, pending_token?}`, returning the same three-way response shape as `/auth/otp/verify`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/api/test_auth_routes.py`:

```python
def _mock_google_claims(monkeypatch, sub, email=None, email_verified=True):
    import app.api.auth as auth_module
    from app.services.auth.google_oauth import GoogleClaims

    monkeypatch.setattr(
        auth_module, "verify_google_id_token", lambda token: GoogleClaims(sub=sub, email=email, email_verified=email_verified)
    )


def test_google_signup_with_no_collision_returns_phone_required(client, monkeypatch):
    _mock_google_claims(monkeypatch, "g-sub-new", "newgoogle@example.com")

    response = client.post("/auth/oauth/google", json={"id_token": "fake"})

    assert response.status_code == 200
    body = response.json()
    assert body["phone_required"]["prefill_email"] == "newgoogle@example.com"


def test_google_login_for_already_linked_account(client, monkeypatch):
    _mock_google_claims(monkeypatch, "g-sub-returning", "returning-google@example.com")
    gate = client.post("/auth/oauth/google", json={"id_token": "fake"}).json()
    phone = "+919887766554"
    phone_otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    first = client.post(
        "/auth/otp/verify",
        json={"phone_number": phone, "otp": phone_otp, "pending_token": gate["phone_required"]["token"]},
    ).json()

    response = client.post("/auth/oauth/google", json={"id_token": "fake"})

    assert response.status_code == 200
    assert response.json()["user_id"] == first["user_id"]


def test_google_unverified_email_never_auto_links(client, monkeypatch):
    from app.db.session import get_db
    from app.models.user import User

    phone = "+919776655443"
    phone_otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    client.post("/auth/otp/verify", json={"phone_number": phone, "otp": phone_otp})
    db = next(client.app.dependency_overrides[get_db]())
    db.query(User).filter_by(phone_number=phone).update({"email": "spoofable@example.com"})
    db.commit()
    db.close()

    _mock_google_claims(monkeypatch, "g-sub-unverified", "spoofable@example.com", email_verified=False)
    response = client.post("/auth/oauth/google", json={"id_token": "fake"})

    body = response.json()
    assert "phone_required" in body  # treated as brand-new, not linked, per Design Spec §2


def test_google_verification_failure_returns_401(client, monkeypatch):
    import app.api.auth as auth_module
    from app.services.auth.google_oauth import GoogleTokenVerificationError

    def _raise(token):
        raise GoogleTokenVerificationError("bad token")

    monkeypatch.setattr(auth_module, "verify_google_id_token", _raise)

    response = client.post("/auth/oauth/google", json={"id_token": "garbage"})

    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_auth_routes.py -v -k google`
Expected: FAIL — the route doesn't exist yet (404s).

- [ ] **Step 3: Add the route**

In `backend/app/api/auth.py`, add to the imports:

```python
from app.services.auth.google_oauth import GoogleTokenVerificationError, verify_google_id_token
```

and append the route at the end of the file (after the existing `/otp/verify` route, before `/session/refresh`):

```python
@router.post("/oauth/google", response_model=OtpVerifyResponse | LinkRequiredResponse | PhoneRequiredResponse)
def google_oauth_route(body: GoogleAuthBody, db: DbSession = Depends(get_db)):
    try:
        claims = verify_google_id_token(body.id_token)
    except GoogleTokenVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if body.pending_token:
        existing = find_identity_by_subject(db, AuthIdentityProvider.GOOGLE, claims.sub)
        if existing is None:
            raise HTTPException(status_code=401, detail="This Google account isn't linked yet.")
        try:
            user_id = attach_pending_identity(db, body.pending_token, existing.user_id)
        except PendingVerificationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return _session_response(user_id, AuthIdentityProvider.GOOGLE, db)

    existing = find_identity_by_subject(db, AuthIdentityProvider.GOOGLE, claims.sub)
    if existing is not None:
        return _session_response(existing.user_id, AuthIdentityProvider.GOOGLE, db)

    email_for_collision = claims.email if claims.email_verified else None
    if email_for_collision is None:
        pending, raw_token = create_pending_verification(
            db, AuthIdentityProvider.GOOGLE, claims.sub, claims.email, claims.email_verified, matched_user_id=None
        )
        return PhoneRequiredResponse(phone_required=PhoneRequiredDetail(token=raw_token, prefill_email=None))

    collision = resolve_email_collision(db, email_for_collision)
    if collision.kind == "auto_link":
        now = datetime.now(timezone.utc)
        record_identity(db, collision.matched_user_id, AuthIdentityProvider.GOOGLE, claims.sub, claims.email, now)
        from app.services.auth.identity import refresh_denormalized_email

        refresh_denormalized_email(db, db.get(User, collision.matched_user_id))
        return _session_response(collision.matched_user_id, AuthIdentityProvider.GOOGLE, db)

    if collision.kind == "link_required":
        from app.models.auth import AuthIdentity as _AuthIdentity

        matched_identities = db.query(_AuthIdentity).filter_by(user_id=collision.matched_user_id).all()
        existing_method_provider = (
            pick_primary_identity(matched_identities).provider if matched_identities else AuthIdentityProvider.PHONE_OTP
        )
        pending, raw_token = create_pending_verification(
            db, AuthIdentityProvider.GOOGLE, claims.sub, claims.email, True, matched_user_id=collision.matched_user_id
        )
        return LinkRequiredResponse(
            link_required=LinkRequiredDetail(
                token=raw_token,
                matched_email=email_for_collision,
                existing_method=PROVIDER_TO_METHOD_LABEL[existing_method_provider],
            )
        )

    pending, raw_token = create_pending_verification(
        db, AuthIdentityProvider.GOOGLE, claims.sub, claims.email, True, matched_user_id=None
    )
    return PhoneRequiredResponse(phone_required=PhoneRequiredDetail(token=raw_token, prefill_email=claims.email))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_auth_routes.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Deduplicate the `link_required`/`auto_link` branches with `/auth/otp/verify`**

At this point `google_oauth_route` and `verify_otp_route` (Task 9) share nearly identical `auto_link`/`link_required`/`none` handling, differing only in which `provider`/`identifier` feeds in. Extract the shared logic into one function in `identity.py` to avoid the duplication:

In `backend/app/services/auth/identity.py`, add:

```python
class IdentityResolution(NamedTuple):
    kind: Literal["login", "link_required", "phone_required"]
    user_id: uuid.UUID | None
    pending_token: str | None
    matched_email: str | None
    existing_method: AuthIdentityProvider | None
    prefill_email: str | None


def resolve_new_verified_identity(
    db: DbSession,
    provider: AuthIdentityProvider,
    provider_subject: str,
    email: str | None,
    email_verified: bool,
) -> IdentityResolution:
    """For a Google or email-OTP identity with NO existing auth_identities
    row yet (caller has already checked find_identity_by_subject returns
    None). Runs the Design Spec §4 collision check and returns exactly
    what the route needs to respond."""
    email_for_collision = email if email_verified else None

    if email_for_collision is not None:
        collision = resolve_email_collision(db, email_for_collision)
        if collision.kind == "auto_link":
            now = datetime.now()
            from datetime import timezone as _tz

            now = datetime.now(_tz.utc)
            record_identity(db, collision.matched_user_id, provider, provider_subject, email, now)
            user = db.query(User).get(collision.matched_user_id) if hasattr(db.query(User), "get") else db.get(User, collision.matched_user_id)
            refresh_denormalized_email(db, db.get(User, collision.matched_user_id))
            return IdentityResolution("login", collision.matched_user_id, None, None, None, None)

        if collision.kind == "link_required":
            matched_identities = db.query(AuthIdentity).filter_by(user_id=collision.matched_user_id).all()
            existing_method = (
                pick_primary_identity(matched_identities).provider if matched_identities else AuthIdentityProvider.PHONE_OTP
            )
            _, raw_token = create_pending_verification(
                db, provider, provider_subject, email, True, matched_user_id=collision.matched_user_id
            )
            return IdentityResolution(
                "link_required", None, raw_token, email_for_collision, existing_method, None
            )

    _, raw_token = create_pending_verification(
        db, provider, provider_subject, email, email_verified, matched_user_id=None
    )
    return IdentityResolution("phone_required", None, raw_token, None, None, email_for_collision)
```

Clean up the stray double-`now`/`db.query(User).get(...)` line above before saving — it's leftover exploration; the correct, final body is:

```python
def resolve_new_verified_identity(
    db: DbSession,
    provider: AuthIdentityProvider,
    provider_subject: str,
    email: str | None,
    email_verified: bool,
) -> IdentityResolution:
    """For a Google or email-OTP identity with NO existing auth_identities
    row yet (caller has already checked find_identity_by_subject returns
    None). Runs the Design Spec §4 collision check and returns exactly
    what the route needs to respond."""
    email_for_collision = email if email_verified else None

    if email_for_collision is not None:
        collision = resolve_email_collision(db, email_for_collision)
        if collision.kind == "auto_link":
            now = datetime.now(timezone.utc)
            record_identity(db, collision.matched_user_id, provider, provider_subject, email, now)
            refresh_denormalized_email(db, db.get(User, collision.matched_user_id))
            return IdentityResolution("login", collision.matched_user_id, None, None, None, None)

        if collision.kind == "link_required":
            matched_identities = db.query(AuthIdentity).filter_by(user_id=collision.matched_user_id).all()
            existing_method = (
                pick_primary_identity(matched_identities).provider if matched_identities else AuthIdentityProvider.PHONE_OTP
            )
            _, raw_token = create_pending_verification(
                db, provider, provider_subject, email, True, matched_user_id=collision.matched_user_id
            )
            return IdentityResolution(
                "link_required", None, raw_token, email_for_collision, existing_method, None
            )

    _, raw_token = create_pending_verification(
        db, provider, provider_subject, email, email_verified, matched_user_id=None
    )
    return IdentityResolution("phone_required", None, raw_token, None, None, email_for_collision)
```

`timezone` is already imported in `identity.py` from Task 6 — no new import needed.

Now simplify both routes in `backend/app/api/auth.py` to call this instead of duplicating collision logic. In `verify_otp_route` (Task 9), replace everything from `# Email channel with no existing identity: run the collision check.` through the end of the function with:

```python
    # Email channel with no existing identity: run the collision check.
    resolution = resolve_new_verified_identity(db, provider, identifier, identifier, True)
    if resolution.kind == "login":
        return _session_response(resolution.user_id, provider, db)
    if resolution.kind == "link_required":
        return LinkRequiredResponse(
            link_required=LinkRequiredDetail(
                token=resolution.pending_token,
                matched_email=resolution.matched_email,
                existing_method=PROVIDER_TO_METHOD_LABEL[resolution.existing_method],
            )
        )
    return PhoneRequiredResponse(
        phone_required=PhoneRequiredDetail(token=resolution.pending_token, prefill_email=resolution.prefill_email)
    )
```

and in `google_oauth_route` (this task), replace everything from `email_for_collision = claims.email if claims.email_verified else None` through the end of the function with:

```python
    resolution = resolve_new_verified_identity(db, AuthIdentityProvider.GOOGLE, claims.sub, claims.email, claims.email_verified)
    if resolution.kind == "login":
        return _session_response(resolution.user_id, AuthIdentityProvider.GOOGLE, db)
    if resolution.kind == "link_required":
        return LinkRequiredResponse(
            link_required=LinkRequiredDetail(
                token=resolution.pending_token,
                matched_email=resolution.matched_email,
                existing_method=PROVIDER_TO_METHOD_LABEL[resolution.existing_method],
            )
        )
    return PhoneRequiredResponse(
        phone_required=PhoneRequiredDetail(token=resolution.pending_token, prefill_email=resolution.prefill_email)
    )
```

Update the `identity` import line in `auth.py` to add `resolve_new_verified_identity`, and remove now-unused imports (`resolve_email_collision`, `pick_primary_identity`, `create_pending_verification` are no longer called directly from `auth.py` — check with a quick grep before deleting: `grep -n "resolve_email_collision\|pick_primary_identity\|create_pending_verification" backend/app/api/auth.py`; remove whichever no longer appear).

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS — behavior is unchanged, this step only deduplicated the two routes' shared logic.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/auth.py backend/app/services/auth/identity.py backend/tests/api/test_auth_routes.py
git commit -m "feat(auth): add Google OAuth route, deduplicate collision resolution between routes"
```

---

## Task 11: Rate-limit repeated OTP requests for the same identifier

**Files:**
- Modify: `backend/app/services/auth/otp.py`
- Modify: `backend/tests/services/auth/test_otp.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `create_otp_request` now raises `OtpRequestThrottledError` if an unexpired, unverified request for the same identifier+channel already exists and is under 60 seconds old.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/services/auth/test_otp.py`:

```python
def test_create_otp_request_throttles_rapid_repeat_requests(monkeypatch):
    import app.services.auth.otp as otp_module

    monkeypatch.setattr(otp_module.settings, "otp_delivery_mode", "stub")
    db = _session()
    create_otp_request(db, "+919999999999")

    with pytest.raises(otp_module.OtpRequestThrottledError, match="wait"):
        create_otp_request(db, "+919999999999")


def test_create_otp_request_allows_repeat_after_throttle_window_passes(monkeypatch):
    import app.services.auth.otp as otp_module

    monkeypatch.setattr(otp_module.settings, "otp_delivery_mode", "stub")
    db = _session()
    first, _ = create_otp_request(db, "+919999999999")
    first.created_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    db.commit()

    request, raw_otp = create_otp_request(db, "+919999999999")

    assert raw_otp is not None  # did not raise


def test_create_otp_request_throttle_is_per_identifier():
    db = _session()
    create_otp_request(db, "+919999999999")

    request, raw_otp = create_otp_request(db, "+918888888888")  # different number, not throttled

    assert raw_otp is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/auth/test_otp.py -v -k throttle`
Expected: FAIL with `AttributeError: module 'app.services.auth.otp' has no attribute 'OtpRequestThrottledError'`.

- [ ] **Step 3: Implement the throttle**

In `backend/app/services/auth/otp.py`, add the exception class near `OtpVerificationError` and a check at the top of `create_otp_request`:

```python
class OtpRequestThrottledError(Exception):
    """Raised when a new OTP is requested for an identifier that already
    has an unexpired, unverified request under 60 seconds old — a cost
    control now that email sends are billed per-message (Design Spec §6)."""


RESEND_THROTTLE_SECONDS = 60
```

Add `OtpRequestThrottledError` to the module's `__all__` list. Then, inside `create_otp_request`, immediately after the existing stub-mode guard and before `otp = generate_otp()`, insert:

```python
    filter_kwargs = {"phone_number": identifier} if channel == "sms" else {"email": identifier}
    recent = (
        db.query(OtpRequest)
        .filter_by(verified_at=None, **filter_kwargs)
        .order_by(OtpRequest.created_at.desc())
        .first()
    )
    if recent is not None:
        created_at = recent.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        seconds_since = (datetime.now(timezone.utc) - created_at).total_seconds()
        if seconds_since < RESEND_THROTTLE_SECONDS:
            raise OtpRequestThrottledError(
                f"Please wait {int(RESEND_THROTTLE_SECONDS - seconds_since)}s before requesting another code."
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/auth/test_otp.py -v`
Expected: PASS (all tests, existing and new).

- [ ] **Step 5: Wire the exception into the route**

In `backend/app/api/auth.py`'s `request_otp` route, catch the new exception:

```python
from app.services.auth.otp import OtpRequestThrottledError, OtpVerificationError, create_otp_request, verify_otp


@router.post("/otp/request", response_model=OtpRequestResponse)
def request_otp(body: OtpRequestBody, db: DbSession = Depends(get_db)):
    channel = "sms" if body.phone_number is not None else "email"
    identifier = body.phone_number if channel == "sms" else body.email
    try:
        _, raw_otp = create_otp_request(db, identifier, channel=channel)
    except OtpRequestThrottledError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return OtpRequestResponse(message="OTP sent.", otp=raw_otp)
```

Add a route-level test to `backend/tests/api/test_auth_routes.py`:

```python
def test_otp_request_returns_429_when_throttled(client):
    client.post("/auth/otp/request", json={"phone_number": "+919000011111"})

    response = client.post("/auth/otp/request", json={"phone_number": "+919000011111"})

    assert response.status_code == 429
```

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS. Check specifically that no other existing test happens to make two rapid `/otp/request` calls for the *same* identifier within the same test (several tests reuse a phone number across a request+verify pair, which is fine — only a *second request* call for the same identifier without a verify in between would now 429). If one does, it's a real behavior change worth flagging, not silently working around by loosening the throttle.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/auth/otp.py backend/app/api/auth.py backend/tests/api/test_auth_routes.py
git commit -m "feat(auth): throttle repeated OTP requests for the same identifier"
```

---

## Final Verification

- [ ] Run the entire backend suite one more time: `cd backend && python -m pytest -v`. Expected: all tests pass, zero failures, zero errors.
- [ ] Run `cd backend && python -m alembic upgrade head` against a scratch SQLite file, then `python -m alembic downgrade base`, confirming both directions succeed cleanly (this is also covered by `test_migrations.py`, but worth a manual sanity check).
- [ ] Re-read `backend/app/api/auth.py` end to end and confirm no leftover dead code, stray inline imports, or unused variables remain from the iterative edits in Tasks 9–10.
- [ ] Cross-check against the backend spec's §7 (Backend Testing) checklist — every bullet there should now be covered by a test: identity-model constraints, Google verification mocking, collision/linking, the mandatory phone gate, identity precedence, `Session.auth_method`, and route-level status codes.

## Self-Review Notes (for whoever executes this plan)

- **`google-auth`'s exact exception types**: Task 7 assumes `google.auth.exceptions.GoogleAuthError` and `ValueError` are the exceptions `id_token.verify_oauth2_token` can raise. If a real (non-mocked) verification call surfaces a different exception type during manual testing, widen the `except` clause in `google_oauth.py` accordingly rather than leaving a real failure unhandled.
- **This plan does not implement `Docs/superpowers/specs/2026-08-14-multi-method-auth-design.md`'s Future Scope (Apple)** or its deferred Postmark wiring — both are explicitly out of scope per Global Constraints above, not accidentally missed.
- **The frontend plan (separate document) depends on every route/response shape built here** — do not change `OtpVerifyResponse`, `LinkRequiredResponse`, `PhoneRequiredResponse`, or `GoogleAuthBody`'s field names after this plan is executed without updating the frontend plan to match.
