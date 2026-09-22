# Email Signup: OTP → Password (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace email+OTP with email+password as the email signup/login method. Google and phone+OTP are untouched. Every account still converges on a mandatory verified phone as step 2, reusing the exact `pending_identity_verifications`/phone-gate mechanism Google and email-OTP already use.

**Architecture:** Extends the `auth_identities`/`pending_identity_verifications` identity model built in `Docs/superpowers/plans/2026-08-14-multi-method-auth-backend-plan.md` (already complete and merged — read that plan and its spec, `Docs/superpowers/specs/2026-08-14-multi-method-auth-design.md`, for the identity model this one assumes without re-deriving). This plan does NOT edit that plan or its ledger — it's a new, separate body of work on the same codebase. Adds `EMAIL_PASSWORD` as a new `AuthIdentityProvider`; removes the email channel from the OTP system entirely (kept: the enum value, the `EmailProvider` sending abstraction — reused for two new email flows); adds two new token tables (`password_reset_tokens`, `email_confirmation_tokens`) mirroring the existing `pending_identity_verifications` token pattern; adds four new routes (`/auth/signup/email`, `/auth/login/email`, `/auth/password/forgot`, `/auth/password/reset`, `/auth/email/confirm`).

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (Mapped/mapped_column), Alembic, Pydantic v2, pytest — same as the existing backend. New dependency: `passlib[bcrypt]`.

**Spec:** `Docs/superpowers/specs/2026-08-17-email-password-signup-design.md`

## Global Constraints

- **Google and phone+OTP are completely unchanged.** Do not modify `google_oauth.py`, `PhoneEntry`-side routes' phone-only behavior, or anything under `AuthIdentityProvider.GOOGLE`/`PHONE_OTP`.
- **`Decimal`/`float` is not relevant here** (no money fields), but the project's other non-negotiables apply: no raw secret storage (passwords always hashed, tokens always sha256-hashed before storage, same as every existing token in this codebase), Alembic-only schema changes, ORM-only queries elsewhere.
- **Migrations use SQLAlchemy Core `sa.table()`/`sa.column()` literals only** — no `app.models` imports — matching the convention in every migration since `0001` (see `0005_backfill_phone_otp_identities.py` for the most recent example).
- **`EMAIL_OTP` the enum value is never removed or renamed** — Postgres enum values can't be cheaply dropped. `EMAIL_PASSWORD` is added alongside it.
- **bcrypt via `passlib[bcrypt]`** for password hashing — no other hashing library.
- **Minimum password length: 8 characters.** No other complexity rules.
- **Anti-enumeration**: `/auth/password/forgot` always returns 200 regardless of whether the email matches an account. `/auth/login/email` returns the same generic message for both "no such identity" and "wrong password" (401) — but a DISTINCT message (403) for "correct password, email not yet confirmed" (§4c of the spec — safe to disclose distinctly since reaching that check already required a correct password match).
- **`create_pending_verification` gains one new optional parameter, `password_hash: str | None = None`** — Google's and phone's call sites are unaffected (default `None`).
- **Test runner:** `cd backend && python3 -m pytest` (or scoped to a file/dir). Full suite must pass before every commit, not just the new test.
- **CRLF discipline:** this session has repeatedly hit an issue where edits silently convert LF files to CRLF. Before every commit, run `file <every touched path>` and compare against `git show HEAD:<path> | file -` for modified files (new files should just come out clean). Fix with `sed -i 's/\r$//' <path>` if a regression appears.
- **Never `git add -A`/`git add .`** — this repo has ~295 pre-existing files with unrelated line-ending noise. Only `git add` the exact files each task touches.

---

## Task 1: Migration 0006 — schema changes (additive + the otp_requests narrowing)

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/auth.py`
- Create: `backend/alembic/versions/0006_email_password_auth.py`
- Modify: `backend/tests/test_migrations.py`
- Create: `backend/tests/models/test_password_auth_models.py`

**Interfaces:**
- Produces: `AuthIdentityProvider.EMAIL_PASSWORD`; `AuthIdentity.password_hash: str | None`, `AuthIdentity.email_confirmed_at: datetime | None`; `PendingIdentityVerification.password_hash: str | None`; new model `PasswordResetToken` (table `password_reset_tokens`); new model `EmailConfirmationToken` (table `email_confirmation_tokens`) — this second table isn't named in the spec's own §5 list (the spec described the confirmation *link* but didn't spell out its storage), so it's added here as the minimum implementation-level detail needed, mirroring `password_reset_tokens`'s exact shape.

This is EXPECTED to break existing email-OTP tests (`test_otp.py`'s email-channel tests, `test_auth_routes.py`'s email-OTP-request/verify tests, any `test_identity.py` test exercising an email-OTP path) — `otp_requests.email` disappears in this same migration, per spec §5's explicit instruction that all five schema changes land in one revision. **Do not fix those tests in this task** — Task 3 removes the email-OTP code path entirely (including its now-broken tests). Note the exact failure count in your report so it can be sanity-checked in Task 3.

- [x] **Step 1: Update `AuthIdentityProvider` enum**

In `backend/app/models/enums.py`, change:

```python
class AuthIdentityProvider(str, enum.Enum):
    PHONE_OTP = "phone_otp"
    EMAIL_OTP = "email_otp"
    GOOGLE = "google"
```

to:

```python
class AuthIdentityProvider(str, enum.Enum):
    PHONE_OTP = "phone_otp"
    EMAIL_OTP = "email_otp"  # kept, unused going forward — Postgres enums can't cheaply drop a value (Design Spec §1)
    GOOGLE = "google"
    EMAIL_PASSWORD = "email_password"
```

- [x] **Step 2: Update models — `AuthIdentity`, `PendingIdentityVerification`, `OtpRequest`, and two new models**

In `backend/app/models/auth.py`:

Change the `OtpRequest` class (revert to phone-only — the `email` column and its check constraint are dropped by this migration, so the model must match):

```python
class OtpRequest(Base):
    __tablename__ = "otp_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    phone_number: Mapped[str] = mapped_column(String, nullable=False)
    otp_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

(This drops the `email` column, the `CheckConstraint`, and the now-unused `CheckConstraint`/`UniqueConstraint` import if `CheckConstraint` isn't used elsewhere in this file — check the rest of the file before removing the import; `AuthIdentity`/`PendingIdentityVerification` don't currently use `CheckConstraint`, so remove it from the `sqlalchemy` import line if nothing else in this file needs it.)

Add `password_hash`/`email_confirmed_at` to `AuthIdentity` (insert after the existing `email` column):

```python
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
    provider_subject: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String)
    # Only populated for EMAIL_PASSWORD rows — NULL for every other provider,
    # which are inherently verified/proven at creation time and have no
    # password concept. 2026-08-17 email-password design spec §5.
    password_hash: Mapped[str | None] = mapped_column(String)
    # Only meaningful for EMAIL_PASSWORD rows: NULL until the mailbox owner
    # clicks the confirmation link (or completes a password reset — spec
    # §4c). /auth/login/email refuses to authenticate while this is NULL.
    email_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    identifier_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Add `password_hash` to `PendingIdentityVerification` (insert after `email_verified`):

```python
class PendingIdentityVerification(Base):
    """Holds a just-verified Google/email identity that can't yet be
    attached to a session — either a brand-new signup still missing its
    mandatory phone step (`matched_user_id` NULL), or a collision needing
    step-up re-auth (`matched_user_id` set). Design Spec §1/§4 — one
    mechanism, two triggers, one shared TTL."""

    __tablename__ = "pending_identity_verifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider: Mapped[AuthIdentityProvider] = mapped_column(enum_column(AuthIdentityProvider), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String)
    email_verified: Mapped[bool] = mapped_column(nullable=False)
    # Only set for an EMAIL_PASSWORD pending record — already hashed by the
    # route before this row is created, never the raw password. NULL for
    # every other provider. 2026-08-17 email-password design spec §4b.
    password_hash: Mapped[str | None] = mapped_column(String)
    matched_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Add two new models at the end of the file (after `Session`):

```python
class PasswordResetToken(Base):
    """Single-use, email-delivered password-reset link — same
    hash-before-storage pattern as `pending_identity_verifications.
    token_hash`, but its own table since a reset link is a fundamentally
    different mechanism from the 10-minute pending-verification window
    (2026-08-17 email-password design spec §3)."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EmailConfirmationToken(Base):
    """Single-use, email-delivered confirmation link sent once after an
    EMAIL_PASSWORD signup completes its phone gate. Same shape as
    `PasswordResetToken` — a separate table rather than a shared one with
    a purpose flag, so each table's meaning stays obvious from its name
    (2026-08-17 email-password design spec §4c)."""

    __tablename__ = "email_confirmation_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [x] **Step 2b: Write the model tests**

Create `backend/tests/models/test_password_auth_models.py`:

```python
import uuid
from datetime import datetime, timedelta, timezone

from app.models.auth import AuthIdentity, EmailConfirmationToken, PasswordResetToken, PendingIdentityVerification
from app.models.enums import AuthIdentityProvider
from app.models.user import User


def _now():
    return datetime.now(timezone.utc)


def test_auth_identity_supports_email_password_provider(db_session):
    user = User(phone_number="+919999999999", created_at=_now())
    db_session.add(user)
    db_session.flush()

    identity = AuthIdentity(
        user_id=user.id,
        provider=AuthIdentityProvider.EMAIL_PASSWORD,
        provider_subject="a@example.com",
        email=None,
        password_hash="hashed-value",
        email_confirmed_at=None,
        identifier_verified_at=_now(),
        created_at=_now(),
        last_used_at=_now(),
    )
    db_session.add(identity)
    db_session.commit()

    fetched = db_session.query(AuthIdentity).filter_by(provider_subject="a@example.com").one()
    assert fetched.provider == AuthIdentityProvider.EMAIL_PASSWORD
    assert fetched.password_hash == "hashed-value"
    assert fetched.email_confirmed_at is None


def test_pending_identity_verification_supports_password_hash(db_session):
    pending = PendingIdentityVerification(
        provider=AuthIdentityProvider.EMAIL_PASSWORD,
        provider_subject="a@example.com",
        email="a@example.com",
        email_verified=False,
        password_hash="hashed-value",
        matched_user_id=None,
        token_hash="tokhash",
        expires_at=_now() + timedelta(minutes=10),
        created_at=_now(),
    )
    db_session.add(pending)
    db_session.commit()

    fetched = db_session.query(PendingIdentityVerification).filter_by(token_hash="tokhash").one()
    assert fetched.password_hash == "hashed-value"


def test_password_reset_token_round_trip(db_session):
    user = User(phone_number="+919999999998", created_at=_now())
    db_session.add(user)
    db_session.flush()

    token = PasswordResetToken(
        user_id=user.id,
        token_hash="resethash",
        expires_at=_now() + timedelta(minutes=30),
        used_at=None,
        created_at=_now(),
    )
    db_session.add(token)
    db_session.commit()

    fetched = db_session.query(PasswordResetToken).filter_by(token_hash="resethash").one()
    assert fetched.user_id == user.id
    assert fetched.used_at is None


def test_email_confirmation_token_round_trip(db_session):
    user = User(phone_number="+919999999997", created_at=_now())
    db_session.add(user)
    db_session.flush()

    token = EmailConfirmationToken(
        user_id=user.id,
        token_hash="confirmhash",
        expires_at=_now() + timedelta(minutes=30),
        used_at=None,
        created_at=_now(),
    )
    db_session.add(token)
    db_session.commit()

    fetched = db_session.query(EmailConfirmationToken).filter_by(token_hash="confirmhash").one()
    assert fetched.user_id == user.id
```

Check `backend/tests/models/test_auth_identity_models.py` (the existing model test file from the original multi-method-auth plan) for the exact `db_session` fixture name/shape used there — match it exactly. If the fixture is named differently or lives in a different conftest, use that name instead.

- [x] **Step 3: Run the new model tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/models/test_password_auth_models.py -v`
Expected: FAIL — `EMAIL_PASSWORD` doesn't exist yet, `password_hash`/`email_confirmed_at` aren't columns yet, `PasswordResetToken`/`EmailConfirmationToken` don't exist yet.

- [x] **Step 4: Write migration 0006**

Create `backend/alembic/versions/0006_email_password_auth.py`:

```python
"""email+password auth: EMAIL_PASSWORD provider, password_hash/email_confirmed_at
on auth_identities and pending_identity_verifications, password_reset_tokens,
email_confirmation_tokens, and narrowing otp_requests back to phone-only.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-17

Design Spec: Docs/superpowers/specs/2026-08-17-email-password-signup-design.md §5.

One migration, not several — all changes are part of the same product
change and land together, matching how 0004 bundled the original
multi-method-auth schema in one revision.

EMAIL_OTP is never removed or renamed (§1) — Postgres enum values can't be
cheaply dropped, so EMAIL_PASSWORD is added alongside it via ADD VALUE,
additive-only.

Deliberately no imports from `app.models` — SQLAlchemy Core table literals
only, same convention as every migration since 0001.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. Add EMAIL_PASSWORD to the AuthIdentityProvider enum ---
    if bind.dialect.name == "postgresql":
        # ALTER TYPE ... ADD VALUE cannot run inside a transaction block on
        # older Postgres versions; op.execute here matches how this repo has
        # no prior enum-widening migration to pattern-match against, so this
        # is the standard, documented Postgres approach for additive enum
        # values.
        op.execute("ALTER TYPE authidentityprovider ADD VALUE IF NOT EXISTS 'email_password'")
    # SQLite stores the enum as a plain VARCHAR (see app.models.enums.enum_column's
    # docstring) — no schema change needed there for a new allowed value.

    # --- 2. auth_identities: password_hash, email_confirmed_at ---
    with op.batch_alter_table("auth_identities") as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("email_confirmed_at", sa.DateTime(timezone=True), nullable=True))

    # --- 3. pending_identity_verifications: password_hash ---
    with op.batch_alter_table("pending_identity_verifications") as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(), nullable=True))

    # --- 4. New table: password_reset_tokens ---
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- 5. New table: email_confirmation_tokens ---
    op.create_table(
        "email_confirmation_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- 6. Narrow otp_requests back to phone-only ---
    # Confirm no non-empty email rows exist before dropping the column — this
    # is a genuine narrowing (Design Spec §5). Safe on every environment this
    # migration has actually run against so far (dev SQLite has none), and
    # becomes a real pre-deploy check once Postgres is live per the Migration
    # Plan's readiness checklist.
    otp_requests = sa.table("otp_requests", sa.column("email", sa.String()))
    non_empty_emails = bind.execute(
        sa.select(sa.func.count()).select_from(otp_requests).where(otp_requests.c.email.isnot(None))
    ).scalar()
    if non_empty_emails:
        raise RuntimeError(
            f"otp_requests has {non_empty_emails} row(s) with a non-NULL email — "
            "cannot safely drop the column. Investigate before re-running this migration."
        )

    with op.batch_alter_table("otp_requests") as batch_op:
        batch_op.drop_constraint("ck_otp_requests_exactly_one_identifier", type_="check")
        batch_op.drop_column("email")
        batch_op.alter_column("phone_number", existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("otp_requests") as batch_op:
        batch_op.alter_column("phone_number", existing_type=sa.String(), nullable=True)
        batch_op.add_column(sa.Column("email", sa.String(), nullable=True))
        batch_op.create_check_constraint(
            "ck_otp_requests_exactly_one_identifier",
            "(phone_number IS NOT NULL) != (email IS NOT NULL)",
        )

    op.drop_table("email_confirmation_tokens")
    op.drop_table("password_reset_tokens")

    with op.batch_alter_table("pending_identity_verifications") as batch_op:
        batch_op.drop_column("password_hash")

    with op.batch_alter_table("auth_identities") as batch_op:
        batch_op.drop_column("email_confirmed_at")
        batch_op.drop_column("password_hash")

    # EMAIL_PASSWORD is NOT removed from the Postgres enum type on downgrade —
    # Postgres has no DROP VALUE, only a full type recreation, which risks
    # destroying live data if any row still uses it. Leaving the enum value
    # defined is harmless (same reasoning as never removing EMAIL_OTP).
```

- [x] **Step 5: Run the migration and confirm the model tests pass**

Run: `cd backend && python3 -m alembic upgrade head`
Then: `cd backend && python3 -m pytest tests/models/test_password_auth_models.py -v`
Expected: PASS (4 tests).

- [x] **Step 6: Update `test_migrations.py`'s expected schema**

Open `backend/tests/test_migrations.py`. Find wherever it lists expected tables (likely a set/list checked after `alembic upgrade head`) and add `"password_reset_tokens"` and `"email_confirmation_tokens"`. Find wherever it checks `otp_requests`' columns (if it does) and update to remove `email` from the expected column set, matching the same pattern the file already used when `0004` widened this table. Add one round-trip test matching `0005`'s own round-trip test pattern (`head -> 0005 -> head` or similar), adapted to `0006`:

```python
def test_email_password_auth_migration_upgrade_downgrade_upgrade(alembic_config, tmp_sqlite_db):
    # Match whatever fixture names test_migrations.py's existing 0005
    # round-trip test uses for alembic_config/tmp_sqlite_db — read that test
    # first and copy its exact fixture usage, only changing the target
    # revisions to 0006/0005/0006.
    ...
```

(This step's exact code depends on `test_migrations.py`'s existing fixture conventions — read the file's current 0005 round-trip test in full before writing this one, and mirror it precisely rather than guessing the fixture shape.)

- [x] **Step 7: Run the full backend suite and confirm the EXPECTED breakage matches what Task 1's brief predicted**

Run: `cd backend && python3 -m pytest`
Expected: model/migration tests pass; email-OTP-related tests in `test_otp.py`, `test_auth_routes.py`, and any email-OTP-specific test in `test_identity.py`/`test_schemas.py` FAIL (column no longer exists / code paths reference a dropped column). Record the exact failure count and file list in your report — Task 3 must account for every one of them, either by fixing or by deliberately deleting the test (since the feature is being removed, not just moved).

- [x] **Step 8: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/auth.py \
  backend/alembic/versions/0006_email_password_auth.py \
  backend/tests/test_migrations.py backend/tests/models/test_password_auth_models.py
git commit -m "feat(auth): add email+password schema, narrow otp_requests back to phone-only"
```

---

## Task 2: `password.py` — bcrypt hashing service

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/services/auth/password.py`
- Create: `backend/tests/services/auth/test_password.py`

**Interfaces:**
- Produces: `hash_password(raw: str) -> str`; `verify_password(raw: str, hashed: str) -> bool`.

- [x] **Step 1: Add the dependency**

In `backend/requirements.txt`, add a new line after `requests>=2.31.0`:

```
passlib[bcrypt]>=1.7.4
```

Run: `cd backend && pip install -r requirements.txt`

- [x] **Step 2: Write the failing tests**

Create `backend/tests/services/auth/test_password.py`:

```python
from app.services.auth.password import hash_password, verify_password


def test_hash_password_returns_a_different_string_than_the_input():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert len(hashed) > 20


def test_verify_password_succeeds_for_the_correct_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_fails_for_the_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_hash_password_produces_different_hashes_for_the_same_input():
    # bcrypt salts automatically — two hashes of the same password must
    # differ, or verify_password would be trivially exploitable via
    # hash-equality timing/comparison shortcuts.
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second
    assert verify_password("correct horse battery staple", first) is True
    assert verify_password("correct horse battery staple", second) is True
```

- [x] **Step 3: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/services/auth/test_password.py -v`
Expected: FAIL — `app.services.auth.password` doesn't exist yet.

- [x] **Step 4: Write the implementation**

Create `backend/app/services/auth/password.py`:

```python
"""Password hashing for email+password auth — bcrypt via passlib. A
single cost-factor knob (unlike Argon2's three), the most battle-tested,
zero-surprise choice for a standard FastAPI backend (Design Spec §2).
"""

from __future__ import annotations

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw: str) -> str:
    return _pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return _pwd_context.verify(raw, hashed)
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/services/auth/test_password.py -v`
Expected: PASS (4 tests).

- [x] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/services/auth/password.py backend/tests/services/auth/test_password.py
git commit -m "feat(auth): add bcrypt password hashing service"
```

---

## Task 3: Revert `otp.py`/schemas/routes to phone-only, remove email-OTP entirely

**Files:**
- Modify: `backend/app/services/auth/otp.py`
- Modify: `backend/app/services/auth/schemas.py`
- Modify: `backend/app/api/auth.py`
- Modify: `backend/tests/services/auth/test_otp.py`
- Modify: `backend/tests/services/auth/test_schemas.py`
- Modify: `backend/tests/api/test_auth_routes.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `create_otp_request(db, phone_number: str) -> tuple[OtpRequest, str | None]` (channel parameter removed); `verify_otp(db, phone_number: str, otp: str) -> OtpRequest` (channel parameter removed); `OtpRequestBody`/`OtpVerifyBody` become phone-only (no `email` field).

This task fixes the breakage Task 1 caused (email-OTP's column is gone) by removing the email-OTP code path entirely, per Design Spec §1: "remove the email channel's code path entirely; do not leave it 'just in case'." `EmailProvider`/`StubEmailProvider`/`get_email_provider` are NOT touched — they're reused unchanged in Task 6 for password-reset delivery and Task 7 for confirmation-link delivery.

- [x] **Step 1: Revert `otp.py` to phone-only**

Replace `backend/app/services/auth/otp.py` in full:

```python
"""OTP generation, hashing, and verification — phone+OTP only. Email OTP
was removed per the 2026-08-17 email-password design spec §1: email
signup now uses email+password (see password.py), and email-OTP had zero
remaining callers once that landed.

sha256, not bcrypt/argon2: OTPs are short-lived (5 min), low-entropy
6-digit codes, not long-lived credentials — there's nothing to gain from an
expensive hash here, and it would be a needless dependency.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.models.auth import OtpRequest

OTP_LENGTH = 6
OTP_TTL_MINUTES = 5
MAX_ATTEMPTS = 5

__all__ = [
    "OtpVerificationError",
    "OtpRequestThrottledError",
    "create_otp_request",
    "verify_otp",
]


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def generate_otp() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


def create_otp_request(db: DbSession, phone_number: str) -> tuple[OtpRequest, str | None]:
    """Creates and persists a new OtpRequest. Returns (request, raw_otp) —
    raw_otp is only non-None in dev-stub delivery mode, for the API
    response to echo back; a real delivery mode returns None here and
    sends the code out-of-band instead."""
    if settings.otp_delivery_mode == "stub" and not settings.database_url.startswith("sqlite"):
        raise RuntimeError(
            "otp_delivery_mode='stub' is not allowed against a non-SQLite database — "
            "this would leak real OTPs in the API response outside local dev. "
            "Set OTP_DELIVERY_MODE to a real delivery mode before deploying against Postgres."
        )

    recent = (
        db.query(OtpRequest)
        .filter_by(verified_at=None, phone_number=phone_number)
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

    otp = generate_otp()
    request = OtpRequest(
        phone_number=phone_number,
        otp_hash=_hash_otp(otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
        created_at=datetime.now(timezone.utc),
    )
    db.add(request)
    db.commit()

    raw_otp = otp if settings.otp_delivery_mode == "stub" else None
    return request, raw_otp


class OtpRequestThrottledError(Exception):
    """Raised when a new OTP is requested for a phone number that already
    has an unexpired, unverified request under 60 seconds old."""


RESEND_THROTTLE_SECONDS = 60


class OtpVerificationError(Exception):
    """Any OTP verification failure — no pending request, expired, wrong code, or too many attempts."""


def verify_otp(db: DbSession, phone_number: str, otp: str) -> OtpRequest:
    """Verifies otp against the latest unverified OtpRequest for
    phone_number. Raises OtpVerificationError on any failure. On success,
    marks the request verified and returns it."""
    request = (
        db.query(OtpRequest)
        .filter_by(verified_at=None, phone_number=phone_number)
        .order_by(OtpRequest.created_at.desc())
        .first()
    )
    if not request:
        raise OtpVerificationError("No pending OTP request for this identifier.")
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

- [x] **Step 2: Revert `OtpRequestBody`/`OtpVerifyBody` in `schemas.py` to phone-only**

In `backend/app/services/auth/schemas.py`, replace:

```python
class OtpRequestBody(BaseModel):
    phone_number: str | None = None
    email: str | None = None

    # mode="before" so the canonical value is what _exactly_one_identifier
    # (a mode="after" validator) and every downstream consumer sees.
    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: object) -> object:
        return normalize_email(value)

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> "OtpRequestBody":
        if (self.phone_number is None) == (self.email is None):
            raise ValueError("Provide exactly one of phone_number or email.")
        return self
```

with:

```python
class OtpRequestBody(BaseModel):
    phone_number: str
```

and replace:

```python
class OtpVerifyBody(BaseModel):
    phone_number: str | None = None
    email: str | None = None
    otp: str
    pending_token: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: object) -> object:
        return normalize_email(value)

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> "OtpVerifyBody":
        if (self.phone_number is None) == (self.email is None):
            raise ValueError("Provide exactly one of phone_number or email.")
        return self
```

with:

```python
class OtpVerifyBody(BaseModel):
    phone_number: str
    otp: str
    pending_token: str | None = None
```

Update `PROVIDER_TO_METHOD_LABEL` to add the new provider (Task 5 needs this too, but adding it now keeps the enum/label mapping complete as soon as the enum value exists):

```python
PROVIDER_TO_METHOD_LABEL: dict[AuthIdentityProvider, str] = {
    AuthIdentityProvider.PHONE_OTP: "phone",
    AuthIdentityProvider.EMAIL_OTP: "email",
    AuthIdentityProvider.GOOGLE: "google",
    AuthIdentityProvider.EMAIL_PASSWORD: "email",
}
```

**Do not remove `normalize_email`** — Task 5's new `SignupEmailBody`/`LoginEmailBody` schemas reuse it. Only its two call sites inside `OtpRequestBody`/`OtpVerifyBody` are removed (along with the now-unused `field_validator`/`model_validator` imports IF nothing else in the file uses them — check before removing; `normalize_email` itself is a plain function, not a validator, so it stays regardless).

- [x] **Step 3: Revert `/auth/otp/request`/`/auth/otp/verify` routes in `api/auth.py` to phone-only**

In `backend/app/api/auth.py`, replace `request_otp`:

```python
@router.post("/otp/request", response_model=OtpRequestResponse)
def request_otp(body: OtpRequestBody, db: DbSession = Depends(get_db)):
    try:
        _, raw_otp = create_otp_request(db, body.phone_number)
    except OtpRequestThrottledError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return OtpRequestResponse(message="OTP sent.", otp=raw_otp)
```

Replace `verify_otp_route`:

```python
@router.post("/otp/verify", response_model=OtpVerifyResponse | LinkRequiredResponse | PhoneRequiredResponse)
def verify_otp_route(body: OtpVerifyBody, db: DbSession = Depends(get_db)):
    try:
        verify_otp(db, body.phone_number, body.otp)
    except OtpVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if body.pending_token:
        try:
            existing = find_or_backfill_phone_identity(db, body.phone_number)
            if existing is not None:
                user_id = attach_pending_identity(db, body.pending_token, existing.user_id)
            else:
                user_id = complete_phone_gate_signup(db, body.pending_token, body.phone_number)
        except PendingVerificationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return _session_response(user_id, AuthIdentityProvider.PHONE_OTP, db)

    # Phone uses find_or_backfill_phone_identity so a pre-0005-backfill `users`
    # row (identity row missing) logs in normally instead of falling through to
    # the brand-new-signup INSERT below and violating users.phone_number UNIQUE.
    existing = find_or_backfill_phone_identity(db, body.phone_number)
    if existing is not None:
        return _session_response(existing.user_id, AuthIdentityProvider.PHONE_OTP, db)

    # Phone never collision-checks (no email claim to collide with) —
    # brand-new phone number always completes signup immediately.
    now = datetime.now(timezone.utc)
    user = User(phone_number=body.phone_number, created_at=now)
    db.add(user)
    db.flush()
    record_identity(db, user.id, AuthIdentityProvider.PHONE_OTP, body.phone_number, None, now)
    db.commit()
    return _session_response(user.id, AuthIdentityProvider.PHONE_OTP, db)
```

Update the `otp` import block at the top of the file. Change:

```python
from app.services.auth.otp import (
    NoEmailProviderConfiguredError,
    OtpRequestThrottledError,
    OtpVerificationError,
    create_otp_request,
    verify_otp,
)
```

to:

```python
from app.services.auth.otp import OtpRequestThrottledError, OtpVerificationError, create_otp_request, verify_otp
```

(`NoEmailProviderConfiguredError` is dropped — `otp.py`'s Step 1 replacement above no longer raises it, since it has no email code path left at all. Task 6 later imports `get_email_provider` directly from `app.services.auth.email_provider` instead of via `otp.py`, since `otp.py` no longer re-exports it either.)

Leave `resolve_new_verified_identity` imported from `app.services.auth.identity` — Google's route (`google_oauth_route`, untouched by this plan) still calls it; Task 5's new email+password signup route calls `create_pending_verification` directly instead (per spec §4), not `resolve_new_verified_identity`.

- [x] **Step 4: Delete or rewrite the now-obsolete email-OTP tests**

Open `backend/tests/services/auth/test_otp.py`. Delete every test whose name contains `email_channel` or that exercises `channel="email"` (these test a feature that no longer exists): `test_create_otp_request_accepts_email_channel`, `test_verify_otp_succeeds_for_email_channel`, `test_verify_otp_email_channel_does_not_match_phone_request`, `test_create_otp_request_email_channel_dispatches_via_email_provider_when_not_stub`, `test_create_otp_request_email_channel_raises_when_no_provider_configured`, `test_create_otp_request_persists_nothing_when_the_email_provider_fails`, `test_create_otp_request_retry_is_not_throttled_after_an_email_provider_failure` (check the actual current file for the exact full list — these are the ones the email-OTP finding/fix-wave added across this session's history; delete anything channel-parameterized). Update the remaining phone-only tests to call `create_otp_request(db, "+919999999999")`/`verify_otp(db, "+919999999999", otp)` without a `channel=` keyword argument (drop the keyword entirely, since the parameter no longer exists).

Open `backend/tests/services/auth/test_schemas.py`. Remove any test exercising `OtpRequestBody`/`OtpVerifyBody` with an `email` field or expecting the exactly-one-identifier validator's error message — those cases are gone. Keep/add a test confirming `OtpRequestBody(phone_number="+919999999999")` and `OtpVerifyBody(phone_number="+919999999999", otp="123456")` construct successfully with no `email` field accepted (Pydantic v2 raises `ValidationError` on an unexpected extra field only if `model_config` sets `extra="forbid"` — check the existing `BaseModel` config; if it's the default `extra="ignore"`, add a small test confirming an `email` kwarg is silently ignored rather than accepted, so a stale frontend call doesn't silently succeed in a confusing way — if this reveals `extra="ignore"` is the actual behavior and that's undesirable, flag it in your report rather than silently changing global model config, since that's a broader decision than this task's scope).

Open `backend/tests/api/test_auth_routes.py`. Remove every test targeting `/auth/otp/request`/`/auth/otp/verify` with `{"email": ...}` in the request body, and any test specifically about the 503/`NoEmailProviderConfiguredError` mapping for that route (that whole scenario is gone — email requests through `/auth/otp/*` no longer exist at all). Do NOT remove phone-only tests for these two routes.

- [x] **Step 5: Run the full backend suite**

Run: `cd backend && python3 -m pytest`
Expected: PASS, zero failures — this should resolve every failure Task 1's report predicted. If anything else still fails, investigate before proceeding (don't assume it's unrelated).

- [x] **Step 6: Check for CRLF, then commit**

```bash
file backend/app/services/auth/otp.py backend/app/services/auth/schemas.py backend/app/api/auth.py \
  backend/tests/services/auth/test_otp.py backend/tests/services/auth/test_schemas.py backend/tests/api/test_auth_routes.py
# fix any CRLF regression with sed -i 's/\r$//' <path> before committing

git add backend/app/services/auth/otp.py backend/app/services/auth/schemas.py backend/app/api/auth.py \
  backend/tests/services/auth/test_otp.py backend/tests/services/auth/test_schemas.py backend/tests/api/test_auth_routes.py
git commit -m "feat(auth): remove email-OTP code path, otp.py/routes back to phone-only"
```

---

## Task 4: `PROVIDER_PRECEDENCE` for `EMAIL_PASSWORD`, and thread `password_hash` through the phone gate

**Files:**
- Modify: `backend/app/services/auth/identity.py`
- Modify: `backend/tests/services/auth/test_identity.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `PROVIDER_PRECEDENCE` gains `AuthIdentityProvider.EMAIL_PASSWORD: 1` (same rank `EMAIL_OTP` already occupies — see Step 0); `create_pending_verification(db, provider, provider_subject, email, email_verified, matched_user_id, password_hash: str | None = None) -> tuple[PendingIdentityVerification, str]` (new optional parameter, default `None`, appended last so existing positional call sites are unaffected).

- [x] **Step 0: Add `EMAIL_PASSWORD` to `PROVIDER_PRECEDENCE` — fixes a real `KeyError` this plan's own new provider would otherwise cause**

`identity.py`'s `PROVIDER_PRECEDENCE` dict currently has no entry for `EMAIL_PASSWORD` (it predates this plan). Traced concretely, not hypothetically: `resolve_new_verified_identity`'s `link_required` branch calls `pick_primary_identity(matched_identities)` on the FULL, unfiltered list of a matched user's identities — including any `EMAIL_PASSWORD` one, regardless of whether it carries an email claim. `pick_primary_identity` does `min(identities, key=lambda i: PROVIDER_PRECEDENCE[i.provider])`, which raises `KeyError` the first time this runs against an account that has an `EMAIL_PASSWORD` identity. This is a real, reachable crash: any account created via this plan's `/auth/signup/email` — which always has one, since it's the whole point of the route — hits this the moment a *different* new signup (Google, say) later collides with that account's denormalized email.

In `backend/app/services/auth/identity.py`, change:

```python
PROVIDER_PRECEDENCE: dict[AuthIdentityProvider, int] = {
    AuthIdentityProvider.GOOGLE: 0,
    AuthIdentityProvider.EMAIL_OTP: 1,
    AuthIdentityProvider.PHONE_OTP: 2,
}
```

to:

```python
PROVIDER_PRECEDENCE: dict[AuthIdentityProvider, int] = {
    AuthIdentityProvider.GOOGLE: 0,
    AuthIdentityProvider.EMAIL_OTP: 1,  # kept, unused going forward — see EMAIL_PASSWORD below
    AuthIdentityProvider.EMAIL_PASSWORD: 1,  # occupies EMAIL_OTP's old precedence slot — same concept (an email-based method), just password- instead of OTP-verified
    AuthIdentityProvider.PHONE_OTP: 2,
}
```

Add a regression test to `backend/tests/services/auth/test_identity.py` proving this doesn't crash:

```python
def test_pick_primary_identity_handles_email_password_without_a_keyerror(db_session):
    now = datetime.now(timezone.utc)
    user = User(phone_number="+919777777770", created_at=now)
    db_session.add(user)
    db_session.flush()
    email_password_identity = AuthIdentity(
        user_id=user.id,
        provider=AuthIdentityProvider.EMAIL_PASSWORD,
        provider_subject="precedence@example.com",
        email=None,
        password_hash="hashed",
        email_confirmed_at=None,
        identifier_verified_at=now,
        created_at=now,
        last_used_at=now,
    )
    phone_identity = AuthIdentity(
        user_id=user.id,
        provider=AuthIdentityProvider.PHONE_OTP,
        provider_subject="+919777777770",
        email=None,
        identifier_verified_at=now,
        created_at=now,
        last_used_at=now,
    )
    db_session.add_all([email_password_identity, phone_identity])
    db_session.commit()

    result = pick_primary_identity([email_password_identity, phone_identity])

    assert result.provider == AuthIdentityProvider.EMAIL_PASSWORD
```

(Match the file's existing imports for `datetime`/`timezone`/`User`/`AuthIdentity`/`pick_primary_identity` — these are almost certainly already imported for other tests in this file; only add what's missing.)

Run: `cd backend && python3 -m pytest tests/services/auth/test_identity.py -k precedence -v` — expect FAIL (KeyError) before this step's dict change, PASS after.

**Known limitation, explicitly out of scope for this plan — do not silently build a fix:** `users.email` (the denormalized field) is never backfilled once an `EMAIL_PASSWORD` identity's `email_confirmed_at` gets set, because `complete_phone_gate_signup` always sets `user.email = None` for password signups (§4a: nothing is verified at signup time) and nothing subsequently updates it after confirmation — `refresh_denormalized_email` only considers identities with a non-`NULL` `AuthIdentity.email`, which an `EMAIL_PASSWORD` row never has (its own email claim is never "verified" in that collision-check sense, by design). Concretely: a user who signs up and fully confirms their email+password account will still see `email: null` from `/auth/me`. This is a real, visible gap the design spec didn't address — flagging it here rather than silently fixing it, since the correct fix touches `refresh_denormalized_email`'s precedence logic (whether a confirmed `EMAIL_PASSWORD`'s `provider_subject` should count as an "email claim" for denormalization, and how it should rank against a `Google` identity's already-verified email if both exist on one account) and deserves its own decision, not an inline judgment call made this deep into a task.

- [x] **Step 1: Write the failing tests**

Add to `backend/tests/services/auth/test_identity.py` (match the existing file's imports/fixtures — read the file first for its exact `db_session`/helper conventions before writing these):

```python
def test_create_pending_verification_stores_password_hash(db_session):
    pending, raw_token = create_pending_verification(
        db_session,
        AuthIdentityProvider.EMAIL_PASSWORD,
        "a@example.com",
        "a@example.com",
        False,
        matched_user_id=None,
        password_hash="hashed-value",
    )
    assert pending.password_hash == "hashed-value"


def test_create_pending_verification_defaults_password_hash_to_none(db_session):
    pending, raw_token = create_pending_verification(
        db_session,
        AuthIdentityProvider.GOOGLE,
        "google-sub-123",
        "a@example.com",
        True,
        matched_user_id=None,
    )
    assert pending.password_hash is None


def test_complete_phone_gate_signup_copies_password_hash_onto_the_new_identity(db_session):
    pending, raw_token = create_pending_verification(
        db_session,
        AuthIdentityProvider.EMAIL_PASSWORD,
        "a@example.com",
        "a@example.com",
        False,
        matched_user_id=None,
        password_hash="hashed-value",
    )

    user_id = complete_phone_gate_signup(db_session, raw_token, "+919999999999")

    identity = (
        db_session.query(AuthIdentity)
        .filter_by(user_id=user_id, provider=AuthIdentityProvider.EMAIL_PASSWORD)
        .one()
    )
    assert identity.password_hash == "hashed-value"
    assert identity.provider_subject == "a@example.com"


def test_attach_pending_identity_copies_password_hash_onto_the_new_identity(db_session):
    # Existing user (phone-first) later adds an email+password credential
    # via the phone gate's attach path — same mechanic phone-only accounts
    # already use for adding a Google/email-OTP identity.
    existing_user_id = complete_phone_gate_signup(
        db_session,
        create_pending_verification(
            db_session, AuthIdentityProvider.GOOGLE, "google-sub-456", None, False, matched_user_id=None
        )[1],
        "+919888888888",
    )

    pending, raw_token = create_pending_verification(
        db_session,
        AuthIdentityProvider.EMAIL_PASSWORD,
        "b@example.com",
        "b@example.com",
        False,
        matched_user_id=None,
        password_hash="hashed-value-2",
    )

    attach_pending_identity(db_session, raw_token, existing_user_id)

    identity = (
        db_session.query(AuthIdentity)
        .filter_by(user_id=existing_user_id, provider=AuthIdentityProvider.EMAIL_PASSWORD)
        .one()
    )
    assert identity.password_hash == "hashed-value-2"
```

(Adjust the exact `create_pending_verification` call shape in these tests to match its ACTUAL current parameter order in `identity.py` — read the function signature directly before writing these tests, since positional-vs-keyword argument order matters and must match exactly.)

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/services/auth/test_identity.py -k password_hash -v`
Expected: FAIL — `create_pending_verification` doesn't accept `password_hash` yet, and the new `AuthIdentity` rows it creates won't have it set.

- [x] **Step 3: Update `create_pending_verification`**

In `backend/app/services/auth/identity.py`, change:

```python
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
```

to:

```python
def create_pending_verification(
    db: DbSession,
    provider: AuthIdentityProvider,
    provider_subject: str,
    email: str | None,
    email_verified: bool,
    matched_user_id: uuid.UUID | None,
    password_hash: str | None = None,
) -> tuple[PendingIdentityVerification, str]:
    raw_token = secrets.token_urlsafe(PENDING_VERIFICATION_TOKEN_BYTES)
    now = datetime.now(timezone.utc)
    pending = PendingIdentityVerification(
        provider=provider,
        provider_subject=provider_subject,
        email=email,
        email_verified=email_verified,
        password_hash=password_hash,
        matched_user_id=matched_user_id,
        token_hash=_hash_pending_token(raw_token),
        expires_at=now + timedelta(minutes=PENDING_VERIFICATION_TTL_MINUTES),
        created_at=now,
    )
    db.add(pending)
    db.commit()
    return pending, raw_token
```

- [x] **Step 4: Thread `password_hash` through `complete_phone_gate_signup`**

Change:

```python
    now = datetime.now(timezone.utc)
    user = User(phone_number=phone_number, email=verified_email, created_at=now)
    db.add(user)
    db.flush()
    record_identity(db, user.id, AuthIdentityProvider.PHONE_OTP, phone_number, None, now, commit=False)
    record_identity(db, user.id, pending.provider, pending.provider_subject, verified_email, now, commit=False)
    db.delete(pending)
    db.commit()
    return user.id
```

to:

```python
    now = datetime.now(timezone.utc)
    user = User(phone_number=phone_number, email=verified_email, created_at=now)
    db.add(user)
    db.flush()
    record_identity(db, user.id, AuthIdentityProvider.PHONE_OTP, phone_number, None, now, commit=False)
    new_identity = record_identity(
        db, user.id, pending.provider, pending.provider_subject, verified_email, now, commit=False
    )
    # password_hash is only ever non-None on an EMAIL_PASSWORD pending
    # record (2026-08-17 email-password design spec §4b); harmless no-op
    # for every other provider.
    new_identity.password_hash = pending.password_hash
    db.delete(pending)
    db.commit()
    return user.id
```

- [x] **Step 5: Thread `password_hash` through `attach_pending_identity`**

Change:

```python
    now = datetime.now(timezone.utc)
    record_identity(db, resolved_user_id, pending.provider, pending.provider_subject, verified_email, now, commit=False)
    # Explicit flush: production and test sessions are both autoflush=False, so
    # without this the identity we just added is invisible to
    # refresh_denormalized_email's own query and users.email is silently never
    # updated — the account would gain a verified Google/email identity while
    # /auth/me kept reporting email=None. Still one transaction: the single
    # db.commit() below covers the flush, the delete, and the email update.
    db.flush()
    user = db.get(User, resolved_user_id)
    refresh_denormalized_email(db, user, commit=False)
    db.delete(pending)
    db.commit()
    return resolved_user_id
```

to:

```python
    now = datetime.now(timezone.utc)
    new_identity = record_identity(
        db, resolved_user_id, pending.provider, pending.provider_subject, verified_email, now, commit=False
    )
    new_identity.password_hash = pending.password_hash
    # Explicit flush: production and test sessions are both autoflush=False, so
    # without this the identity we just added is invisible to
    # refresh_denormalized_email's own query and users.email is silently never
    # updated — the account would gain a verified Google/email identity while
    # /auth/me kept reporting email=None. Still one transaction: the single
    # db.commit() below covers the flush, the delete, and the email update.
    db.flush()
    user = db.get(User, resolved_user_id)
    refresh_denormalized_email(db, user, commit=False)
    db.delete(pending)
    db.commit()
    return resolved_user_id
```

- [x] **Step 6: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/services/auth/test_identity.py -v`
Expected: PASS, all tests including the 4 new ones.

- [x] **Step 7: Run the full backend suite**

Run: `cd backend && python3 -m pytest`
Expected: PASS, zero failures (this task's change is additive/backward-compatible — Google's and phone's call sites don't pass `password_hash`, defaulting to `None`, so their existing behavior is unaffected).

- [x] **Step 8: Commit**

```bash
file backend/app/services/auth/identity.py backend/tests/services/auth/test_identity.py
# fix CRLF if needed

git add backend/app/services/auth/identity.py backend/tests/services/auth/test_identity.py
git commit -m "feat(auth): thread password_hash through the phone gate's identity creation"
```

---

## Task 5: `/auth/signup/email` and `/auth/login/email` routes

**Files:**
- Modify: `backend/app/services/auth/schemas.py`
- Modify: `backend/app/api/auth.py`
- Create: `backend/tests/api/test_auth_email_password_routes.py`

**Interfaces:**
- Consumes: `hash_password`/`verify_password` (Task 2), `create_pending_verification` with `password_hash` (Task 4), `find_identity_by_subject`, `normalize_email` (existing, `schemas.py`).
- Produces: `POST /auth/signup/email`, `POST /auth/login/email`.

- [x] **Step 1: Add the new schemas**

In `backend/app/services/auth/schemas.py`, add (after `OtpVerifyBody`, before `OtpVerifyResponse` — or anywhere logical; exact position doesn't matter, just keep related schemas grouped):

```python
class SignupEmailBody(BaseModel):
    email: str
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: object) -> object:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def _min_length(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return value


class LoginEmailBody(BaseModel):
    email: str
    password: str
    pending_token: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: object) -> object:
        return normalize_email(value)
```

(`LoginEmailBody` deliberately has no minimum-length check — an existing password that happens to be shorter than the current minimum, e.g. from a policy change, must still be checkable; only `SignupEmailBody` enforces the floor for new passwords. `pending_token` mirrors `OtpVerifyBody`/`GoogleAuthBody`'s own optional field — this is what makes email password login usable as a step-up re-authentication method: `LinkAccountPrompt`'s email branch re-authenticates via `/auth/login/email` with a pending token attached, exactly like phone/Google's re-auth branches already do via `/auth/otp/verify`/`/auth/oauth/google`.)

- [x] **Step 2: Write the failing tests**

Create `backend/tests/api/test_auth_email_password_routes.py` (check `test_auth_routes.py`'s existing `client` fixture/imports first and match its conventions exactly):

```python
from app.models.auth import AuthIdentity
from app.models.enums import AuthIdentityProvider


def test_signup_email_returns_phone_required(client, db_session):
    response = client.post("/auth/signup/email", json={"email": "new@example.com", "password": "correcthorse"})

    assert response.status_code == 200
    body = response.json()
    assert "phone_required" in body
    assert body["phone_required"]["token"]


def test_signup_email_rejects_short_passwords(client):
    response = client.post("/auth/signup/email", json={"email": "new2@example.com", "password": "short"})

    assert response.status_code == 422


def test_signup_email_conflicts_when_email_already_has_a_password_identity(client, db_session):
    first = client.post("/auth/signup/email", json={"email": "dup@example.com", "password": "correcthorse"})
    assert first.status_code == 200
    gate_token = first.json()["phone_required"]["token"]
    client.post("/auth/otp/request", json={"phone_number": "+919111111111"})
    # Read the dev-stub OTP directly rather than re-requesting, since a
    # second request would hit the resend throttle.
    otp = db_session.query.__self__  # placeholder marker removed below

    response = client.post("/auth/signup/email", json={"email": "dup@example.com", "password": "anotherpassword"})

    assert response.status_code == 409


def test_signup_email_normalizes_case_and_whitespace(client):
    first = client.post("/auth/signup/email", json={"email": "  Mixed@Example.COM  ", "password": "correcthorse"})
    assert first.status_code == 200

    second = client.post("/auth/signup/email", json={"email": "mixed@example.com", "password": "different"})
    assert second.status_code == 409


def test_signup_email_then_phone_gate_creates_an_email_password_identity_with_the_hash(client, db_session):
    signup = client.post("/auth/signup/email", json={"email": "gate@example.com", "password": "correcthorse"})
    gate_token = signup.json()["phone_required"]["token"]

    otp_request = client.post("/auth/otp/request", json={"phone_number": "+919222222222"})
    otp = otp_request.json()["otp"]
    verify = client.post(
        "/auth/otp/verify",
        json={"phone_number": "+919222222222", "otp": otp, "pending_token": gate_token},
    )

    assert verify.status_code == 200
    assert "session_token" in verify.json()
    identity = (
        db_session.query(AuthIdentity)
        .filter_by(provider=AuthIdentityProvider.EMAIL_PASSWORD, provider_subject="gate@example.com")
        .one()
    )
    assert identity.password_hash is not None
    assert identity.password_hash != "correcthorse"


def test_login_email_succeeds_after_confirmation(client, db_session):
    # This test's exact "confirm the email" step depends on Task 7's
    # confirmation endpoint, which doesn't exist yet in this task — write
    # this test now with a TODO-free direct DB write confirming the
    # identity (setting email_confirmed_at directly via db_session), since
    # Task 5 doesn't yet build the confirm-email endpoint. Replace this
    # direct DB manipulation with a real confirm-endpoint call once Task 7
    # lands, if you're executing tasks in order and want the test to stay
    # accurate to the full flow.
    signup = client.post("/auth/signup/email", json={"email": "login@example.com", "password": "correcthorse"})
    gate_token = signup.json()["phone_required"]["token"]
    otp_request = client.post("/auth/otp/request", json={"phone_number": "+919333333333"})
    otp = otp_request.json()["otp"]
    client.post(
        "/auth/otp/verify",
        json={"phone_number": "+919333333333", "otp": otp, "pending_token": gate_token},
    )
    identity = (
        db_session.query(AuthIdentity)
        .filter_by(provider=AuthIdentityProvider.EMAIL_PASSWORD, provider_subject="login@example.com")
        .one()
    )
    from datetime import datetime, timezone
    identity.email_confirmed_at = datetime.now(timezone.utc)
    db_session.commit()

    response = client.post("/auth/login/email", json={"email": "login@example.com", "password": "correcthorse"})

    assert response.status_code == 200
    assert "session_token" in response.json()


def test_login_email_rejects_wrong_password_generically(client, db_session):
    signup = client.post("/auth/signup/email", json={"email": "wrongpw@example.com", "password": "correcthorse"})
    gate_token = signup.json()["phone_required"]["token"]
    otp_request = client.post("/auth/otp/request", json={"phone_number": "+919444444444"})
    otp = otp_request.json()["otp"]
    client.post(
        "/auth/otp/verify",
        json={"phone_number": "+919444444444", "otp": otp, "pending_token": gate_token},
    )

    response = client.post("/auth/login/email", json={"email": "wrongpw@example.com", "password": "wrongpassword"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_email_rejects_unknown_email_with_the_same_generic_message(client):
    response = client.post("/auth/login/email", json={"email": "neverexisted@example.com", "password": "whatever1"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_email_returns_403_when_not_yet_confirmed(client, db_session):
    signup = client.post("/auth/signup/email", json={"email": "unconfirmed@example.com", "password": "correcthorse"})
    gate_token = signup.json()["phone_required"]["token"]
    otp_request = client.post("/auth/otp/request", json={"phone_number": "+919555555555"})
    otp = otp_request.json()["otp"]
    client.post(
        "/auth/otp/verify",
        json={"phone_number": "+919555555555", "otp": otp, "pending_token": gate_token},
    )

    response = client.post("/auth/login/email", json={"email": "unconfirmed@example.com", "password": "correcthorse"})

    assert response.status_code == 403


def test_login_email_with_a_pending_token_attaches_the_pending_identity(client, db_session):
    # Step-up linking: an existing email+password account (fully confirmed)
    # re-authenticates via password, attaching a pending Google identity
    # that collided with it — same mechanic verify_otp_route/
    # google_oauth_route already exercise for their own re-auth branches.
    from datetime import datetime, timezone
    from app.services.auth.identity import create_pending_verification

    _signup_and_complete_gate(client, "stepup@example.com", "+919666666601")
    identity = (
        db_session.query(AuthIdentity)
        .filter_by(provider=AuthIdentityProvider.EMAIL_PASSWORD, provider_subject="stepup@example.com")
        .one()
    )
    identity.email_confirmed_at = datetime.now(timezone.utc)
    db_session.commit()

    _, pending_token = create_pending_verification(
        db_session,
        AuthIdentityProvider.GOOGLE,
        "google-sub-stepup",
        "stepup@example.com",
        True,
        matched_user_id=identity.user_id,
    )

    response = client.post(
        "/auth/login/email",
        json={"email": "stepup@example.com", "password": "correcthorse", "pending_token": pending_token},
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == str(identity.user_id)
    linked = (
        db_session.query(AuthIdentity)
        .filter_by(provider=AuthIdentityProvider.GOOGLE, provider_subject="google-sub-stepup")
        .one()
    )
    assert linked.user_id == identity.user_id


def test_login_email_rejects_a_pending_token_for_a_different_account(client, db_session):
    from datetime import datetime, timezone
    from app.services.auth.identity import create_pending_verification

    _signup_and_complete_gate(client, "stepupmismatch@example.com", "+919666666602")
    identity = (
        db_session.query(AuthIdentity)
        .filter_by(provider=AuthIdentityProvider.EMAIL_PASSWORD, provider_subject="stepupmismatch@example.com")
        .one()
    )
    identity.email_confirmed_at = datetime.now(timezone.utc)
    db_session.commit()

    import uuid
    _, pending_token = create_pending_verification(
        db_session,
        AuthIdentityProvider.GOOGLE,
        "google-sub-mismatch",
        "someone-else@example.com",
        True,
        matched_user_id=uuid.uuid4(),  # a different account entirely
    )

    response = client.post(
        "/auth/login/email",
        json={"email": "stepupmismatch@example.com", "password": "correcthorse", "pending_token": pending_token},
    )

    assert response.status_code == 401
```

`_signup_and_complete_gate` isn't defined yet in this file at this point in the plan — it's the same small helper Task 6's tests define independently for their own file. Define it once at the top of `test_auth_email_password_routes.py` (after the imports, before the first test) rather than duplicating the phone-gate boilerplate inline in every test that needs an existing confirmed account:

```python
def _signup_and_complete_gate(client, email, phone):
    signup = client.post("/auth/signup/email", json={"email": email, "password": "correcthorse"})
    gate_token = signup.json()["phone_required"]["token"]
    otp_request = client.post("/auth/otp/request", json={"phone_number": phone})
    otp = otp_request.json()["otp"]
    client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp, "pending_token": gate_token})
```

Retrofit the earlier tests in this same file that repeat this exact sequence inline (`test_signup_email_then_phone_gate_creates_an_email_password_identity_with_the_hash`, `test_login_email_succeeds_after_confirmation`, `test_login_email_rejects_wrong_password_generically`, `test_login_email_returns_403_when_not_yet_confirmed`) to call the helper instead, for consistency — functionally identical, just less duplicated boilerplate across the file.

Remove the placeholder `otp = db_session.query.__self__` line from `test_signup_email_conflicts_when_email_already_has_a_password_identity` before running — it was left in as a marker; that test doesn't actually need the phone-gate to complete at all, since the 409 fires at signup-request time regardless of whether the first signup ever finishes its gate. Simplify that test to just two `POST /auth/signup/email` calls with the same email, dropping the phone-OTP lines entirely.

- [x] **Step 3: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/api/test_auth_email_password_routes.py -v`
Expected: FAIL — routes don't exist yet (404s).

- [x] **Step 4: Add the routes**

In `backend/app/api/auth.py`, add imports at the top:

```python
from app.services.auth.identity import (
    PendingVerificationError,
    attach_pending_identity,
    complete_phone_gate_signup,
    create_pending_verification,
    find_identity_by_subject,
    find_or_backfill_phone_identity,
    record_identity,
    resolve_new_verified_identity,
)
from app.services.auth.password import hash_password, verify_password
from app.services.auth.schemas import (
    GoogleAuthBody,
    LinkRequiredDetail,
    LinkRequiredResponse,
    LoginEmailBody,
    MeResponse,
    OtpRequestBody,
    OtpRequestResponse,
    OtpVerifyBody,
    OtpVerifyResponse,
    PhoneRequiredDetail,
    PhoneRequiredResponse,
    PROVIDER_TO_METHOD_LABEL,
    SessionRefreshResponse,
    SignupEmailBody,
    UpdateMeBody,
)
```

(`create_pending_verification` joins the existing `identity` import block; `LoginEmailBody`/`SignupEmailBody` join the existing `schemas` import block — merge into the existing import statements rather than duplicating them.)

Add the two routes (near the existing `/otp/*` routes):

```python
@router.post("/signup/email", response_model=PhoneRequiredResponse)
def signup_email(body: SignupEmailBody, db: DbSession = Depends(get_db)):
    existing = find_identity_by_subject(db, AuthIdentityProvider.EMAIL_PASSWORD, body.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists — log in instead.")

    # email_verified=False unconditionally: nothing cryptographically proves
    # mailbox control at signup time (Design Spec §4a) — same reasoning that
    # fixed Critical Finding 1 for Google's unverified-email case. Called
    # directly rather than through resolve_new_verified_identity, since that
    # function's collision-check branch can never fire when email_verified is
    # False (§4).
    _, raw_token = create_pending_verification(
        db,
        AuthIdentityProvider.EMAIL_PASSWORD,
        body.email,
        body.email,
        False,
        matched_user_id=None,
        password_hash=hash_password(body.password),
    )
    return PhoneRequiredResponse(phone_required=PhoneRequiredDetail(token=raw_token, prefill_email=body.email))


@router.post("/login/email", response_model=OtpVerifyResponse)
def login_email(body: LoginEmailBody, db: DbSession = Depends(get_db)):
    existing = find_identity_by_subject(db, AuthIdentityProvider.EMAIL_PASSWORD, body.email)
    if existing is None or existing.password_hash is None or not verify_password(body.password, existing.password_hash):
        # Same generic message either way — don't leak whether the email
        # exists (Design Spec §4, anti-enumeration).
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if existing.email_confirmed_at is None:
        # 403, not 401: the password already matched, so this is safe to
        # disclose distinctly (Design Spec §4c) — only someone who already
        # knows the correct password ever reaches this branch.
        raise HTTPException(
            status_code=403,
            detail="Please confirm your email before signing in with a password — check your inbox, or resend the link.",
        )

    if body.pending_token:
        # Step-up re-authentication: LinkAccountPrompt's email branch calls
        # this route with a pending token when an existing account's
        # highest-precedence method is email+password, exactly matching how
        # verify_otp_route/google_oauth_route already handle their own
        # pending_token branches. Without this, a password re-auth would log
        # the user into their existing account but never attach the new
        # Google/phone-gate-originating identity that triggered the
        # collision in the first place.
        try:
            user_id = attach_pending_identity(db, body.pending_token, existing.user_id)
        except PendingVerificationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return _session_response(user_id, AuthIdentityProvider.EMAIL_PASSWORD, db)

    return _session_response(existing.user_id, AuthIdentityProvider.EMAIL_PASSWORD, db)
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/api/test_auth_email_password_routes.py -v`
Expected: PASS, all tests.

- [x] **Step 6: Run the full backend suite**

Run: `cd backend && python3 -m pytest`
Expected: PASS, zero failures.

- [x] **Step 7: Commit**

```bash
file backend/app/services/auth/schemas.py backend/app/api/auth.py backend/tests/api/test_auth_email_password_routes.py
# fix CRLF if needed

git add backend/app/services/auth/schemas.py backend/app/api/auth.py backend/tests/api/test_auth_email_password_routes.py
git commit -m "feat(auth): add /auth/signup/email and /auth/login/email routes"
```

---

## Task 6: Password reset — reuses `EmailProvider`, sets `email_confirmed_at` on success

**Files:**
- Create: `backend/app/services/auth/password_reset.py`
- Modify: `backend/app/services/auth/schemas.py`
- Modify: `backend/app/api/auth.py`
- Create: `backend/tests/services/auth/test_password_reset.py`
- Create: `backend/tests/api/test_password_reset_routes.py`

**Interfaces:**
- Consumes: `hash_password` (Task 2), `get_email_provider`/`EmailProvider` (existing, unchanged), `PasswordResetToken` (Task 1).
- Produces: `create_password_reset_token(db, user_id) -> tuple[PasswordResetToken, str]`; `consume_password_reset_token(db, raw_token, new_password) -> None`; `PasswordResetTokenError` exception; `POST /auth/password/forgot`, `POST /auth/password/reset`.

- [x] **Step 1: Write the failing service-level tests**

Create `backend/tests/services/auth/test_password_reset.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from app.models.auth import AuthIdentity, PasswordResetToken
from app.models.enums import AuthIdentityProvider
from app.models.user import User
from app.services.auth.password import verify_password
from app.services.auth.password_reset import (
    PasswordResetTokenError,
    consume_password_reset_token,
    create_password_reset_token,
)


def _make_user_with_identity(db_session, email="reset@example.com"):
    now = datetime.now(timezone.utc)
    user = User(phone_number="+919666666666", created_at=now)
    db_session.add(user)
    db_session.flush()
    identity = AuthIdentity(
        user_id=user.id,
        provider=AuthIdentityProvider.EMAIL_PASSWORD,
        provider_subject=email,
        email=None,
        password_hash="old-hash",
        email_confirmed_at=None,
        identifier_verified_at=now,
        created_at=now,
        last_used_at=now,
    )
    db_session.add(identity)
    db_session.commit()
    return user, identity


def test_create_password_reset_token_persists_a_hashed_token(db_session):
    user, _ = _make_user_with_identity(db_session)

    token, raw_token = create_password_reset_token(db_session, user.id)

    assert token.token_hash != raw_token
    assert token.used_at is None


def test_consume_password_reset_token_updates_the_hash_and_confirms_the_email(db_session):
    user, identity = _make_user_with_identity(db_session)
    _, raw_token = create_password_reset_token(db_session, user.id)

    consume_password_reset_token(db_session, raw_token, "brand-new-password")

    db_session.refresh(identity)
    assert verify_password("brand-new-password", identity.password_hash)
    assert identity.email_confirmed_at is not None


def test_consume_password_reset_token_marks_the_token_used(db_session):
    user, _ = _make_user_with_identity(db_session)
    token, raw_token = create_password_reset_token(db_session, user.id)

    consume_password_reset_token(db_session, raw_token, "brand-new-password")

    db_session.refresh(token)
    assert token.used_at is not None


def test_consume_password_reset_token_rejects_a_reused_token(db_session):
    user, _ = _make_user_with_identity(db_session)
    _, raw_token = create_password_reset_token(db_session, user.id)
    consume_password_reset_token(db_session, raw_token, "first-new-password")

    with pytest.raises(PasswordResetTokenError):
        consume_password_reset_token(db_session, raw_token, "second-new-password")


def test_consume_password_reset_token_rejects_an_expired_token(db_session):
    user, _ = _make_user_with_identity(db_session)
    token, raw_token = create_password_reset_token(db_session, user.id)
    token.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    with pytest.raises(PasswordResetTokenError):
        consume_password_reset_token(db_session, raw_token, "brand-new-password")


def test_consume_password_reset_token_rejects_an_unknown_token(db_session):
    with pytest.raises(PasswordResetTokenError):
        consume_password_reset_token(db_session, "not-a-real-token", "brand-new-password")


def test_consume_password_reset_token_does_not_overwrite_an_existing_confirmation_timestamp(db_session):
    # If the email was already confirmed before the reset, the original
    # confirmation timestamp should be preserved, not bumped forward.
    user, identity = _make_user_with_identity(db_session)
    original_confirmed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    identity.email_confirmed_at = original_confirmed_at
    db_session.commit()
    _, raw_token = create_password_reset_token(db_session, user.id)

    consume_password_reset_token(db_session, raw_token, "brand-new-password")

    db_session.refresh(identity)
    assert identity.email_confirmed_at == original_confirmed_at
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/services/auth/test_password_reset.py -v`
Expected: FAIL — `app.services.auth.password_reset` doesn't exist yet.

- [x] **Step 3: Write the implementation**

Create `backend/app/services/auth/password_reset.py`:

```python
"""Password reset — single-use, email-delivered link. Same
hash-before-storage pattern as `identity.py`'s pending-verification
tokens (raw `secrets.token_urlsafe(32)`, sha256-hashed for storage, never
stored raw). Design Spec 2026-08-17 §3/§4c.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as DbSession

from app.models.auth import AuthIdentity, PasswordResetToken
from app.models.enums import AuthIdentityProvider
from app.services.auth.password import hash_password

RESET_TOKEN_BYTES = 32
RESET_TOKEN_TTL_MINUTES = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_password_reset_token(db: DbSession, user_id: uuid.UUID) -> tuple[PasswordResetToken, str]:
    raw_token = secrets.token_urlsafe(RESET_TOKEN_BYTES)
    now = datetime.now(timezone.utc)
    token = PasswordResetToken(
        user_id=user_id,
        token_hash=_hash_token(raw_token),
        expires_at=now + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),
        used_at=None,
        created_at=now,
    )
    db.add(token)
    db.commit()
    return token, raw_token


class PasswordResetTokenError(Exception):
    """Any failure consuming a password reset token — not found, expired, or already used."""


def consume_password_reset_token(db: DbSession, raw_token: str, new_password: str) -> None:
    token_hash = _hash_token(raw_token)
    token = db.query(PasswordResetToken).filter_by(token_hash=token_hash).first()
    if token is None:
        raise PasswordResetTokenError("This reset link is invalid or has expired.")
    if token.used_at is not None:
        raise PasswordResetTokenError("This reset link is invalid or has expired.")
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise PasswordResetTokenError("This reset link is invalid or has expired.")

    identity = (
        db.query(AuthIdentity)
        .filter_by(user_id=token.user_id, provider=AuthIdentityProvider.EMAIL_PASSWORD)
        .first()
    )
    if identity is None:
        # Shouldn't happen (a reset token is only ever created for a user
        # with an EMAIL_PASSWORD identity), but fail loudly rather than
        # silently no-op if the data is ever in an inconsistent state.
        raise PasswordResetTokenError("This reset link is invalid or has expired.")

    identity.password_hash = hash_password(new_password)
    # A successful reset is exactly as strong a proof of mailbox control as
    # the initial confirmation link — completing it also confirms the email
    # if it wasn't already (Design Spec §4c), without overwriting an earlier
    # genuine confirmation timestamp.
    if identity.email_confirmed_at is None:
        identity.email_confirmed_at = datetime.now(timezone.utc)

    token.used_at = datetime.now(timezone.utc)
    db.commit()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/services/auth/test_password_reset.py -v`
Expected: PASS, all 7 tests.

- [x] **Step 5: Add the request/response schemas**

In `backend/app/services/auth/schemas.py`, add:

```python
class ForgotPasswordBody(BaseModel):
    email: str

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: object) -> object:
        return normalize_email(value)


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordBody(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _min_length(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return value


class ResetPasswordResponse(BaseModel):
    message: str
```

- [x] **Step 6: Write the failing route tests**

Create `backend/tests/api/test_password_reset_routes.py`:

```python
import re

from app.models.auth import AuthIdentity
from app.models.enums import AuthIdentityProvider


def _signup_and_complete_gate(client, email, phone):
    signup = client.post("/auth/signup/email", json={"email": email, "password": "correcthorse"})
    gate_token = signup.json()["phone_required"]["token"]
    otp_request = client.post("/auth/otp/request", json={"phone_number": phone})
    otp = otp_request.json()["otp"]
    client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp, "pending_token": gate_token})


def test_forgot_password_always_returns_200(client):
    known = client.post("/auth/password/forgot", json={"email": "unknown-entirely@example.com"})
    assert known.status_code == 200


def test_forgot_password_sends_a_reset_link_for_a_known_email(client, db_session, caplog):
    _signup_and_complete_gate(client, "forgot@example.com", "+919777777771")

    with caplog.at_level("INFO"):
        response = client.post("/auth/password/forgot", json={"email": "forgot@example.com"})

    assert response.status_code == 200
    # otp_delivery_mode=stub logs instead of sending (same as every other
    # EmailProvider caller) — the stub log line is the observable signal
    # that send_email was actually invoked.
    assert any("StubEmailProvider" in record.message for record in caplog.records)


def test_reset_password_with_a_valid_token_succeeds_and_allows_login(client, db_session):
    _signup_and_complete_gate(client, "resetflow@example.com", "+919777777772")
    identity = (
        db_session.query(AuthIdentity)
        .filter_by(provider=AuthIdentityProvider.EMAIL_PASSWORD, provider_subject="resetflow@example.com")
        .one()
    )
    from app.services.auth.password_reset import create_password_reset_token
    _, raw_token = create_password_reset_token(db_session, identity.user_id)

    reset = client.post("/auth/password/reset", json={"token": raw_token, "new_password": "brandnewpassword"})
    assert reset.status_code == 200

    login = client.post("/auth/login/email", json={"email": "resetflow@example.com", "password": "brandnewpassword"})
    assert login.status_code == 200
    assert "session_token" in login.json()


def test_reset_password_rejects_an_invalid_token(client):
    response = client.post("/auth/password/reset", json={"token": "not-a-real-token", "new_password": "brandnewpassword"})
    assert response.status_code == 401


def test_reset_password_rejects_a_short_new_password(client, db_session):
    _signup_and_complete_gate(client, "shortpw@example.com", "+919777777773")
    identity = (
        db_session.query(AuthIdentity)
        .filter_by(provider=AuthIdentityProvider.EMAIL_PASSWORD, provider_subject="shortpw@example.com")
        .one()
    )
    from app.services.auth.password_reset import create_password_reset_token
    _, raw_token = create_password_reset_token(db_session, identity.user_id)

    response = client.post("/auth/password/reset", json={"token": raw_token, "new_password": "short"})
    assert response.status_code == 422
```

- [x] **Step 7: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/api/test_password_reset_routes.py -v`
Expected: FAIL — routes don't exist yet.

- [x] **Step 8: Add the routes**

In `backend/app/api/auth.py`, add imports:

```python
from app.services.auth.otp import OtpRequestThrottledError, OtpVerificationError, create_otp_request, verify_otp
from app.services.auth.password_reset import PasswordResetTokenError, consume_password_reset_token, create_password_reset_token
from app.services.auth.email_provider import get_email_provider
```

(Merge `PasswordResetTokenError`/`consume_password_reset_token`/`create_password_reset_token` into a new import line, or alongside existing ones — keep imports grouped by module as the file already does. `get_email_provider` is newly imported here since Task 3 removed it from `otp.py`'s exports for this route's purposes — check whether `otp.py` still exports it for anything else after Task 3; if not, import directly from `app.services.auth.email_provider` as shown.)

Add `ForgotPasswordBody`, `ForgotPasswordResponse`, `ResetPasswordBody`, `ResetPasswordResponse` to the existing `from app.services.auth.schemas import (...)` block.

Add the two routes:

```python
@router.post("/password/forgot", response_model=ForgotPasswordResponse)
def forgot_password(body: ForgotPasswordBody, db: DbSession = Depends(get_db)):
    # Always 200 regardless of whether the email matches an account —
    # anti-enumeration (Design Spec §3).
    identity = find_identity_by_subject(db, AuthIdentityProvider.EMAIL_PASSWORD, body.email)
    if identity is not None:
        _, raw_token = create_password_reset_token(db, identity.user_id)
        reset_link = f"https://app.unifolio.in/reset-password?token={raw_token}"
        get_email_provider().send_email(
            to=body.email,
            subject="Reset your Unifolio password",
            body=f"Click this link to reset your password: {reset_link}. It expires in 30 minutes.",
        )
    return ForgotPasswordResponse(message="If that email is registered, a reset link has been sent.")


@router.post("/password/reset", response_model=ResetPasswordResponse)
def reset_password(body: ResetPasswordBody, db: DbSession = Depends(get_db)):
    try:
        consume_password_reset_token(db, body.token, body.new_password)
    except PasswordResetTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return ResetPasswordResponse(message="Your password has been reset.")
```

- [x] **Step 9: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/api/test_password_reset_routes.py -v`
Expected: PASS, all 5 tests.

- [x] **Step 10: Run the full backend suite**

Run: `cd backend && python3 -m pytest`
Expected: PASS, zero failures.

- [x] **Step 11: Commit**

```bash
file backend/app/services/auth/password_reset.py backend/app/services/auth/schemas.py backend/app/api/auth.py \
  backend/tests/services/auth/test_password_reset.py backend/tests/api/test_password_reset_routes.py
# fix CRLF if needed

git add backend/app/services/auth/password_reset.py backend/app/services/auth/schemas.py backend/app/api/auth.py \
  backend/tests/services/auth/test_password_reset.py backend/tests/api/test_password_reset_routes.py
git commit -m "feat(auth): add password reset flow, reusing EmailProvider"
```

---

## Task 7: Email confirmation — send the link, confirm endpoint, wire into the phone gate

**Files:**
- Create: `backend/app/services/auth/email_confirmation.py`
- Modify: `backend/app/services/auth/schemas.py`
- Modify: `backend/app/services/auth/identity.py`
- Modify: `backend/app/api/auth.py`
- Create: `backend/tests/services/auth/test_email_confirmation.py`
- Create: `backend/tests/api/test_email_confirmation_routes.py`

**Interfaces:**
- Consumes: `get_email_provider` (existing), `EmailConfirmationToken` (Task 1).
- Produces: `create_email_confirmation_token(db, user_id) -> tuple[EmailConfirmationToken, str]`; `consume_email_confirmation_token(db, raw_token) -> None`; `send_confirmation_email(db, user_id, email) -> None` (generates the token AND sends it — a single call site for both routes that create an EMAIL_PASSWORD identity); `EmailConfirmationTokenError`; `POST /auth/email/confirm`.

- [x] **Step 1: Write the failing service-level tests**

Create `backend/tests/services/auth/test_email_confirmation.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from app.models.auth import AuthIdentity
from app.models.enums import AuthIdentityProvider
from app.models.user import User
from app.services.auth.email_confirmation import (
    EmailConfirmationTokenError,
    consume_email_confirmation_token,
    create_email_confirmation_token,
    send_confirmation_email,
)


def _make_user_with_identity(db_session, email="confirm@example.com"):
    now = datetime.now(timezone.utc)
    user = User(phone_number="+919888888881", created_at=now)
    db_session.add(user)
    db_session.flush()
    identity = AuthIdentity(
        user_id=user.id,
        provider=AuthIdentityProvider.EMAIL_PASSWORD,
        provider_subject=email,
        email=None,
        password_hash="hashed",
        email_confirmed_at=None,
        identifier_verified_at=now,
        created_at=now,
        last_used_at=now,
    )
    db_session.add(identity)
    db_session.commit()
    return user, identity


def test_create_email_confirmation_token_persists_a_hashed_token(db_session):
    user, _ = _make_user_with_identity(db_session)

    token, raw_token = create_email_confirmation_token(db_session, user.id)

    assert token.token_hash != raw_token
    assert token.used_at is None


def test_consume_email_confirmation_token_sets_email_confirmed_at(db_session):
    user, identity = _make_user_with_identity(db_session)
    _, raw_token = create_email_confirmation_token(db_session, user.id)

    consume_email_confirmation_token(db_session, raw_token)

    db_session.refresh(identity)
    assert identity.email_confirmed_at is not None


def test_consume_email_confirmation_token_marks_the_token_used(db_session):
    user, _ = _make_user_with_identity(db_session)
    token, raw_token = create_email_confirmation_token(db_session, user.id)

    consume_email_confirmation_token(db_session, raw_token)

    db_session.refresh(token)
    assert token.used_at is not None


def test_consume_email_confirmation_token_rejects_a_reused_token(db_session):
    user, _ = _make_user_with_identity(db_session)
    _, raw_token = create_email_confirmation_token(db_session, user.id)
    consume_email_confirmation_token(db_session, raw_token)

    with pytest.raises(EmailConfirmationTokenError):
        consume_email_confirmation_token(db_session, raw_token)


def test_consume_email_confirmation_token_rejects_an_expired_token(db_session):
    user, _ = _make_user_with_identity(db_session)
    token, raw_token = create_email_confirmation_token(db_session, user.id)
    token.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    with pytest.raises(EmailConfirmationTokenError):
        consume_email_confirmation_token(db_session, raw_token)


def test_consume_email_confirmation_token_rejects_an_unknown_token(db_session):
    with pytest.raises(EmailConfirmationTokenError):
        consume_email_confirmation_token(db_session, "not-a-real-token")


def test_send_confirmation_email_logs_via_the_stub_provider(db_session, caplog):
    user, _ = _make_user_with_identity(db_session)

    with caplog.at_level("INFO"):
        send_confirmation_email(db_session, user.id, "confirm@example.com")

    assert any("StubEmailProvider" in record.message for record in caplog.records)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/services/auth/test_email_confirmation.py -v`
Expected: FAIL — `app.services.auth.email_confirmation` doesn't exist yet.

- [x] **Step 3: Write the implementation**

Create `backend/app/services/auth/email_confirmation.py`:

```python
"""Email confirmation for EMAIL_PASSWORD identities — decoupled from
signup so the phone gate completes with zero added friction (Design Spec
2026-08-17 §4c). Same single-use, hash-before-storage token pattern as
`password_reset.py`.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as DbSession

from app.models.auth import AuthIdentity, EmailConfirmationToken
from app.models.enums import AuthIdentityProvider
from app.services.auth.email_provider import get_email_provider

CONFIRMATION_TOKEN_BYTES = 32
CONFIRMATION_TOKEN_TTL_MINUTES = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_email_confirmation_token(db: DbSession, user_id: uuid.UUID) -> tuple[EmailConfirmationToken, str]:
    raw_token = secrets.token_urlsafe(CONFIRMATION_TOKEN_BYTES)
    now = datetime.now(timezone.utc)
    token = EmailConfirmationToken(
        user_id=user_id,
        token_hash=_hash_token(raw_token),
        expires_at=now + timedelta(minutes=CONFIRMATION_TOKEN_TTL_MINUTES),
        used_at=None,
        created_at=now,
    )
    db.add(token)
    db.commit()
    return token, raw_token


class EmailConfirmationTokenError(Exception):
    """Any failure consuming an email confirmation token — not found, expired, or already used."""


def consume_email_confirmation_token(db: DbSession, raw_token: str) -> None:
    token_hash = _hash_token(raw_token)
    token = db.query(EmailConfirmationToken).filter_by(token_hash=token_hash).first()
    if token is None or token.used_at is not None:
        raise EmailConfirmationTokenError("This confirmation link is invalid or has expired.")
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise EmailConfirmationTokenError("This confirmation link is invalid or has expired.")

    identity = (
        db.query(AuthIdentity)
        .filter_by(user_id=token.user_id, provider=AuthIdentityProvider.EMAIL_PASSWORD)
        .first()
    )
    if identity is None:
        raise EmailConfirmationTokenError("This confirmation link is invalid or has expired.")

    if identity.email_confirmed_at is None:
        identity.email_confirmed_at = datetime.now(timezone.utc)
    token.used_at = datetime.now(timezone.utc)
    db.commit()


def send_confirmation_email(db: DbSession, user_id: uuid.UUID, email: str) -> None:
    """Generates a token and sends it — the single call site both
    `complete_phone_gate_signup` and `attach_pending_identity` use once
    they've created an EMAIL_PASSWORD identity, so the send always happens
    exactly once per signup regardless of which phone-gate path fired."""
    _, raw_token = create_email_confirmation_token(db, user_id)
    confirm_link = f"https://app.unifolio.in/confirm-email?token={raw_token}"
    get_email_provider().send_email(
        to=email,
        subject="Confirm your Unifolio email",
        body=f"Click this link to enable password sign-in: {confirm_link}. It expires in 30 minutes.",
    )
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/services/auth/test_email_confirmation.py -v`
Expected: PASS, all 7 tests.

- [x] **Step 5: Wire `send_confirmation_email` into the phone gate**

In `backend/app/services/auth/identity.py`, at the top of the file, add the import:

```python
from app.services.auth.email_confirmation import send_confirmation_email
```

In `complete_phone_gate_signup`, after `new_identity.password_hash = pending.password_hash` and before `db.delete(pending)`, add:

```python
    if pending.provider == AuthIdentityProvider.EMAIL_PASSWORD:
        # Sent after the identity row is fully written but before the
        # final commit below — if send_confirmation_email's own internal
        # commit (it creates+commits an EmailConfirmationToken) succeeds
        # but something later in this function failed, the token would
        # still be valid for an account that technically doesn't exist yet
        # in a fully-committed sense. This is an accepted, narrow edge case
        # matching this codebase's existing tolerance for equivalent races
        # elsewhere (see decisions.md's FundScore/backfill-identity race
        # entries) — not worth a two-phase-commit for an email send.
        send_confirmation_email(db, user.id, pending.provider_subject)
```

Apply the identical addition to `attach_pending_identity`, after `new_identity.password_hash = pending.password_hash` and before `db.flush()`:

```python
    if pending.provider == AuthIdentityProvider.EMAIL_PASSWORD:
        send_confirmation_email(db, resolved_user_id, pending.provider_subject)
```

- [x] **Step 6: Write the failing test for the phone-gate wiring**

Add to `backend/tests/services/auth/test_identity.py`:

```python
def test_complete_phone_gate_signup_sends_a_confirmation_email_for_password_identities(db_session, caplog):
    pending, raw_token = create_pending_verification(
        db_session,
        AuthIdentityProvider.EMAIL_PASSWORD,
        "confirmflow@example.com",
        "confirmflow@example.com",
        False,
        matched_user_id=None,
        password_hash="hashed-value",
    )

    with caplog.at_level("INFO"):
        complete_phone_gate_signup(db_session, raw_token, "+919888888882")

    assert any("StubEmailProvider" in record.message for record in caplog.records)


def test_complete_phone_gate_signup_does_not_send_email_for_google_identities(db_session, caplog):
    pending, raw_token = create_pending_verification(
        db_session, AuthIdentityProvider.GOOGLE, "google-sub-789", "g@example.com", True, matched_user_id=None
    )

    with caplog.at_level("INFO"):
        complete_phone_gate_signup(db_session, raw_token, "+919888888883")

    assert not any("StubEmailProvider" in record.message for record in caplog.records)
```

Run: `cd backend && python3 -m pytest tests/services/auth/test_identity.py -k confirmation_email -v`
Expected: FAIL first (before Step 5's wiring lands — if you're executing this task's steps in order, this will actually already PASS since Step 5 runs before this point; if so, that's correct, not a problem — the "write failing test first" step is satisfied by the tests failing against a checkout that doesn't yet have Step 5's change, which is how this task is TDD-ordered in the plan even though the steps are listed with implementation before this specific test for readability; run the test against a git stash of Step 5's changes if you want to see the literal red state, or accept that Step 4 already exercises the underlying send function directly and this integration test's real value is confirming the wiring, not re-proving the send itself).

Then run: `cd backend && python3 -m pytest tests/services/auth/test_identity.py -v`
Expected: PASS, all tests.

- [x] **Step 7: Add the confirm-email schema and route**

In `backend/app/services/auth/schemas.py`, add:

```python
class ConfirmEmailBody(BaseModel):
    token: str


class ConfirmEmailResponse(BaseModel):
    message: str
```

In `backend/app/api/auth.py`, import `ConfirmEmailBody`/`ConfirmEmailResponse` (merge into the existing schemas import) and `EmailConfirmationTokenError`/`consume_email_confirmation_token` from `app.services.auth.email_confirmation`. Add the route:

```python
@router.post("/email/confirm", response_model=ConfirmEmailResponse)
def confirm_email(body: ConfirmEmailBody, db: DbSession = Depends(get_db)):
    try:
        consume_email_confirmation_token(db, body.token)
    except EmailConfirmationTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return ConfirmEmailResponse(message="Your email has been confirmed. You can now sign in with your password.")
```

- [x] **Step 8: Write the failing route tests**

Create `backend/tests/api/test_email_confirmation_routes.py`:

```python
from app.models.auth import AuthIdentity
from app.models.enums import AuthIdentityProvider
from app.services.auth.email_confirmation import create_email_confirmation_token


def _signup_and_complete_gate(client, email, phone):
    signup = client.post("/auth/signup/email", json={"email": email, "password": "correcthorse"})
    gate_token = signup.json()["phone_required"]["token"]
    otp_request = client.post("/auth/otp/request", json={"phone_number": phone})
    otp = otp_request.json()["otp"]
    client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp, "pending_token": gate_token})


def test_confirm_email_with_a_valid_token_enables_password_login(client, db_session):
    _signup_and_complete_gate(client, "confirmroute@example.com", "+919999999011")
    identity = (
        db_session.query(AuthIdentity)
        .filter_by(provider=AuthIdentityProvider.EMAIL_PASSWORD, provider_subject="confirmroute@example.com")
        .one()
    )
    _, raw_token = create_email_confirmation_token(db_session, identity.user_id)

    confirm = client.post("/auth/email/confirm", json={"token": raw_token})
    assert confirm.status_code == 200

    login = client.post(
        "/auth/login/email", json={"email": "confirmroute@example.com", "password": "correcthorse"}
    )
    assert login.status_code == 200


def test_confirm_email_rejects_an_invalid_token(client):
    response = client.post("/auth/email/confirm", json={"token": "not-a-real-token"})
    assert response.status_code == 401


def test_signup_and_gate_completion_actually_dispatches_a_confirmation_email(client, caplog):
    with caplog.at_level("INFO"):
        _signup_and_complete_gate(client, "dispatch@example.com", "+919999999012")

    assert any("StubEmailProvider" in record.message for record in caplog.records)
```

- [x] **Step 9: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/api/test_email_confirmation_routes.py -v`
Expected: PASS, all 3 tests.

- [x] **Step 10: Run the full backend suite**

Run: `cd backend && python3 -m pytest`
Expected: PASS, zero failures.

- [x] **Step 11: Commit**

```bash
file backend/app/services/auth/email_confirmation.py backend/app/services/auth/schemas.py \
  backend/app/services/auth/identity.py backend/app/api/auth.py \
  backend/tests/services/auth/test_email_confirmation.py backend/tests/api/test_email_confirmation_routes.py \
  backend/tests/services/auth/test_identity.py
# fix CRLF if needed

git add backend/app/services/auth/email_confirmation.py backend/app/services/auth/schemas.py \
  backend/app/services/auth/identity.py backend/app/api/auth.py \
  backend/tests/services/auth/test_email_confirmation.py backend/tests/api/test_email_confirmation_routes.py \
  backend/tests/services/auth/test_identity.py
git commit -m "feat(auth): add email confirmation, wire into the phone gate"
```

---

## Task 8: Documentation — PRD-02, decisions.md, Database-Schema-Unifolio.md

**Files:**
- Modify: `Docs/PRDs/PRD-02-Signup-Onboarding.md`
- Modify: `decisions.md`
- Modify: `backend.md`
- Modify: `database.md`
- Modify: `Docs/PRDs/Database-Schema-Unifolio.md`

**Interfaces:** none (documentation only).

This task has no tests — it's a documentation-sync task, matching how the 2026-08-14 multi-method-auth plans handled their own doc updates. Run the full suite at the end anyway to confirm nothing was accidentally touched.

- [x] **Step 1: Update PRD-02 FR-2**

In `Docs/PRDs/PRD-02-Signup-Onboarding.md`, find the FR-2 section (`#### Authentication (decided)`, the line starting `- FR-2: Phone number + OTP is the sole signup/login method. No password, ever.`). Replace it with:

```
- FR-2 (updated 2026-08-17): Phone+OTP and Google remain fully passwordless.
  Email signup uses email+password — the one path where password-manager
  autofill removes more friction than an inbox-check step would save. Every
  account still converges on a verified phone as a mandatory second step
  regardless of which method started signup. See decisions.md's 2026-08-17
  entry for the full "why" and what this reverses.
```

Leave FR-2a (the PIN/biometric return-visit note) as-is — it's about phone's own login pattern, unaffected by this change.

- [x] **Step 2: Add the `decisions.md` entry**

Append to `decisions.md` (check the file's current tail for the exact date-heading format used by the most recent entries, and match it):

```markdown
## 2026-08-17 — Email signup reverses to email+password (was email+OTP)

Email signup moves from email+OTP to email+password — reverses the
2026-08-14 multi-method-auth decision that made email one of three
transparent-OTP-style methods (that entry is marked superseded, not
edited — this file is append-only). **Why:** password-manager autofill
removes more real friction on email than email-OTP's inbox-check step
saves — phone+OTP and Google both keep their zero-friction, instant-
verification advantage, so the passwordless principle stays intact
everywhere it was actually earning its keep. Google and phone+OTP are
unchanged. Full design: `Docs/superpowers/specs/2026-08-17-email-password-signup-design.md`.

Two real findings surfaced during design review, not just implementation:
(1) a genuine namespace-squatting gap where an unverified signup email
could occupy the `EMAIL_PASSWORD` identity slot before its real owner ever
tries — traced explicitly (no real-account hijack is possible; a fresh
signup only attaches to an existing account if the entered *phone number*
matches) and closed with a decoupled email-confirmation step that gates
only `/auth/login/email`, never signup or the phone gate itself, so there's
zero added friction on the happy path; (2) a successful password reset
also confirms the email if it wasn't already, since clicking a link mailed
to that exact address is equally strong proof of mailbox control — this is
what makes squatting self-service-recoverable without a support ticket.
```

- [x] **Step 3: Add the `backend.md` entry**

Append to `backend.md`:

```markdown
## 2026-08-17 — Email+password auth backend complete

Replaces email+OTP with email+password (Google and phone+OTP unchanged).
New: `password.py` (bcrypt hashing), `password_reset.py` and
`email_confirmation.py` (both reusing the existing `EmailProvider`
abstraction, same single-use hashed-token pattern `pending_identity_
verifications` already uses), `POST /auth/signup/email`, `POST
/auth/login/email`, `POST /auth/password/forgot`, `POST /auth/password/
reset`, `POST /auth/email/confirm`. Removed: the entire email-OTP code
path (`otp.py`'s channel generalization, `otp_requests.email`) — the
`EMAIL_OTP` enum value itself stays defined but unused, since Postgres
enums can't cheaply drop a value. `AuthIdentity` gains `password_hash`/
`email_confirmed_at`; `pending_identity_verifications` gains
`password_hash` to thread it through the mandatory phone gate exactly the
way Google's identity already does. Full design and the two real findings
closed during review: `decisions.md`'s 2026-08-17 entry and
`Docs/superpowers/specs/2026-08-17-email-password-signup-design.md`.
```

- [x] **Step 4: Add the `database.md` entry**

Append to `database.md`:

```markdown
## 2026-08-17 — Migration 0006: email+password auth

`0006_email_password_auth` — adds `EMAIL_PASSWORD` to the
`AuthIdentityProvider` enum (additive-only `ADD VALUE`, `EMAIL_OTP` never
removed/renamed); `auth_identities` gains `password_hash`/
`email_confirmed_at` (both nullable, populated only for `EMAIL_PASSWORD`
rows); `pending_identity_verifications` gains `password_hash` (nullable,
threads a hashed password through the mandatory phone gate); two new
tables, `password_reset_tokens` and `email_confirmation_tokens` (identical
shape: `id`, `user_id` FK, `token_hash`, `expires_at`, `used_at`,
`created_at` — same single-use hashed-token pattern as
`pending_identity_verifications`); `otp_requests` narrows back to
phone-only — `email` column and its exactly-one-identifier check
constraint dropped, `phone_number` back to `NOT NULL` (confirmed no
non-empty `email` rows existed before dropping — the migration itself
enforces this with a runtime check, not just a manual confirmation).
```

- [x] **Step 5: Update `Database-Schema-Unifolio.md`**

This doc went stale when `0004`/`0005` landed (per the 2026-08-14 `database.md` entry flagging it) and is now further out of date after this plan's `0006`. Update the `users` table section's `phone_number` row note (currently reads "Sole login credential, per PRD-02 FR-2" — no longer accurate, since `auth_identities` is now the actual login-resolution source of truth) and the `otp_requests`/schema description to match the CURRENT real schema: `auth_identities` (with `password_hash`/`email_confirmed_at`), `pending_identity_verifications` (with `password_hash`), `password_reset_tokens`, `email_confirmation_tokens`, and narrowed `otp_requests` (phone-only again). Match this doc's existing table-description format exactly (see the `users`/`household_members` sections for the column-table style to replicate) — read the current file in full before editing, since it needs a genuine content refresh, not just a note pointing elsewhere.

- [x] **Step 6: Run the full backend suite one more time**

Run: `cd backend && python3 -m pytest`
Expected: PASS, zero failures (this task touches no code).

- [x] **Step 7: Check for CRLF, then commit**

```bash
file "Docs/PRDs/PRD-02-Signup-Onboarding.md" decisions.md backend.md database.md "Docs/PRDs/Database-Schema-Unifolio.md"
# fix any CRLF regression with sed -i 's/\r$//' <path> before committing — this
# session has hit this exact failure mode on nearly every doc edit

git add "Docs/PRDs/PRD-02-Signup-Onboarding.md" decisions.md backend.md database.md "Docs/PRDs/Database-Schema-Unifolio.md"
git commit -m "docs: update PRD-02, decisions.md, backend.md, database.md for email+password auth"
```

---

## Final Verification

- [x] `cd backend && python3 -m pytest` — full suite passes, zero failures.
- [x] `cd backend && python3 -m alembic current` shows `0006 (head)`.
- [x] Manually confirm, via a fresh venv install (`python3 -m venv /tmp/verify && /tmp/verify/bin/pip install -r backend/requirements.txt`), that `passlib[bcrypt]` installs cleanly and `python3 -c "from app.services.auth.password import hash_password; print(hash_password('test'))"` runs with zero `ImportError`s — this session has already hit one missing-explicit-dependency bug (`requests`) that only surfaced this way, so don't skip this check.
- [x] Cross-check every numbered section of `Docs/superpowers/specs/2026-08-17-email-password-signup-design.md` against this plan's tasks: §1 (Task 3), §2 (Task 2), §3 (Task 6), §4/§4a/§4b (Tasks 4, 5), §4c (Task 7), §4d (out of scope, confirmed not silently built), §5 (Task 1), §6 (Task 8).
