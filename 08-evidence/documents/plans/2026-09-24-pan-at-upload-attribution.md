u# PAN Check at Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the CAS→member PAN check from Confirm Import to upload time, so Confirm Import never prompts or blocks, and give the Family onboarding flow a "This PAN already exists" popup with Change CAS file / Skip.

**Architecture:** A new `pan_claims.py` module owns the single upload-time rule (claim a PAN for a member as *pending* or *permanent*, or raise a typed conflict). It replaces `attribution.py` entirely. `/imports/parse` now takes the member id, claims the PAN as pending, and records member/user on the in-memory preview session; `/imports/confirm` just makes that claim permanent; a new discard endpoint releases it. The one-step `/cas-imports` path claims as permanent inline. The frontend drops all "Continue anyway / Switch to" UI and handles three 409 codes at upload time.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, pytest (backend); React + TypeScript, Vitest + Testing Library, Radix Dialog (frontend).

**Spec:** `Docs/superpowers/specs/2026-09-24-pan-at-upload-attribution-design.md`

## Global Constraints

- **Do not commit.** The user reviews and commits manually. Every task ends with a "checkpoint" step (run tests, leave changes uncommitted), not a `git commit`.
- Do not touch `backend/app/services/auth/email_templates.py` or `backend/tests/services/auth/test_email_templates.py`. They carry the user's own uncommitted work.
- PAN storage is unchanged: `pan_encrypted` (AES-GCM via `encrypt_pan`), `pan_lookup_hash` (HMAC via `hash_pan`), unique index `ix_household_members_pan_lookup_hash`. The only schema change is the new nullable `pan_pending_until`.
- No raw PAN in any log line, exception message or API response. Logs may name member ids only.
- Confirm Import must never raise or return an error because of PAN or attribution.
- 409 error codes, exactly: `cross_account_pan_blocked`, `pan_belongs_to_other_member`, `pan_mismatch_for_member`. The response body is `{"detail": {"code": <code>, "message": <text>}}`.
- Pending PAN TTL is 65 minutes (preview-session TTL of 60 plus a 5-minute margin).
- Popup copy never names or identifies another Unifolio account.
- Backend test command (Windows venv on a WSL/drvfs mount; `backend/.pytest_tmp` is unremovable, so always pass `--basetemp`), run from `backend/`:
  `.venv/Scripts/python.exe -m pytest <paths> -q -p no:cacheprovider --basetemp=C:/Users/Dell/AppData/Local/Temp/uf_pt`
- Frontend test command, run from `frontend/`: `npx vitest run <paths>`. Typecheck: `npx tsc -b --noEmit`.

## Review Focus

1. **Two open review sessions for the same member and PAN** (two tabs, or re-upload without discard). Discarding one clears the pending PAN the other relies on. Expected: confirming the other still imports and stores the PAN permanently. Pinned in Task 3 (`test_confirm_after_sibling_session_discard_still_stores_pan`).
2. **Confirm after the pending claim was taken by someone else** (only reachable through a bug or clock skew). Expected: the import still succeeds, and the PAN is simply not stored on this member. Pinned in Task 2 (`test_confirm_claim_that_lost_its_pan_imports_without_it`).
3. **SQLite returns `pan_pending_until` as a naive datetime** after a commit/refresh. Expected: expiry comparisons still work, with no `TypeError: can't compare offset-naive and offset-aware`. Pinned in Task 2 (`test_expired_pending_claim_on_other_member_is_reclaimable`, which commits first so it reads back naive).
4. **Family "Change CAS file" with a wrong password.** Expected: the member's normal per-item error screen with Try again / Skip, not a dead end. Pinned in Task 9 (`change CAS file with a wrong password lands on the per-item error screen`).
5. **Discard for an unknown, expired or other user's session.** Expected: 204 with no error, and another user's session is never touched. Pinned in Task 3 (`test_discard_ignores_other_users_session`, `test_discard_unknown_session_is_a_noop`) and Task 4 (route 204).

---

## Task 1: `pan_pending_until` column, migration and PAN-column guard

**Files:**
- Create: `backend/alembic/versions/0016_pending_pan_claims.py`
- Modify: `backend/app/models/user.py` (`HouseholdMember`, after `pan_lookup_hash`)
- Modify: `backend/tests/models/test_no_pan_field.py` (`test_household_member_pan_columns_are_named_for_encrypted_or_hashed_storage_only`)

**Interfaces:**
- Produces: `HouseholdMember.pan_pending_until: datetime | None` (timezone-aware column; SQLite reads it back naive).

- [ ] **Step 1: Update the guard test (red)**

In `backend/tests/models/test_no_pan_field.py`, replace the body of `test_household_member_pan_columns_are_named_for_encrypted_or_hashed_storage_only` with:

```python
def test_household_member_pan_columns_are_named_for_encrypted_or_hashed_storage_only():
    pan_columns = [c for c in HouseholdMember.__table__.columns.keys() if "pan" in c.lower()]
    # pan_pending_until (2026-09-24) holds a timestamp, not PAN data: it marks
    # an upload-time claim that becomes permanent on Confirm Import. See
    # Docs/superpowers/specs/2026-09-24-pan-at-upload-attribution-design.md.
    assert set(pan_columns) == {"pan_encrypted", "pan_lookup_hash", "pan_pending_until"}, (
        "HouseholdMember must expose exactly pan_encrypted, pan_lookup_hash and "
        "pan_pending_until for PAN — a column named just 'pan' (or anything else "
        "PAN-shaped) would suggest plaintext storage, which ADR-004 (as reopened) "
        "still forbids."
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/models/test_no_pan_field.py -q -p no:cacheprovider --basetemp=C:/Users/Dell/AppData/Local/Temp/uf_pt`
Expected: FAIL. The set is missing `pan_pending_until`.

- [ ] **Step 3: Add the model column**

In `backend/app/models/user.py` (`DateTime` is already imported), add below `pan_lookup_hash` in `HouseholdMember`:

```python
    # Non-null = the PAN above is a *pending* upload-time claim that becomes
    # permanent on Confirm Import (set back to NULL) or is released on
    # discard/expiry. NULL with a PAN set = permanent. See
    # app/services/import_/pan_claims.py.
    pan_pending_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 4: Write the migration**

Create `backend/alembic/versions/0016_pending_pan_claims.py`:

```python
"""pending pan claims

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, no backfill: every existing PAN is permanent (NULL here).
    op.add_column(
        "household_members",
        sa.Column("pan_pending_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("household_members", "pan_pending_until")
```

- [ ] **Step 5: Run the guard and migration tests**

Run: `.venv/Scripts/python.exe -m pytest tests/models/test_no_pan_field.py tests/test_migrations.py -q -p no:cacheprovider --basetemp=C:/Users/Dell/AppData/Local/Temp/uf_pt`
Expected: all PASS (the migration round-trip test covers upgrade and downgrade to base).

- [ ] **Step 6: Checkpoint.** Leave the changes uncommitted.

---

## Task 2: `pan_claims.py`, the upload-time rule

**Files:**
- Create: `backend/app/services/import_/pan_claims.py`
- Test: `backend/tests/services/import_/test_pan_claims.py`

**Interfaces:**
- Consumes: `HouseholdMember.pan_pending_until` (Task 1); `encrypt_pan`, `hash_pan` from `app/services/import_/crypto.py`.
- Produces:
  - `PENDING_PAN_TTL: timedelta` (65 min)
  - `class PanConflictError(Exception)`, which has `.code: str` and `.message: str`. Subclasses: `CrossAccountPanBlockedError` (`code="cross_account_pan_blocked"`), `PanBelongsToOtherMemberError` (`"pan_belongs_to_other_member"`), `PanMismatchForMemberError` (`"pan_mismatch_for_member"`)
  - `CROSS_ACCOUNT_PAN_BLOCKED_MESSAGE: str`
  - `claim_pan_for_member(db: Session, member: HouseholdMember, pan: str | None, *, pending: bool, now: datetime | None = None) -> str | None`. Returns the claimed hash or `None` when no PAN was parsed. It flushes but never commits. On a lost unique-index race it calls `db.rollback()` and raises the matching conflict.
  - `confirm_pan_claim(db: Session, member: HouseholdMember, pan: str | None) -> None`. Never raises.
  - `release_pending_pan_claim(member: HouseholdMember, pan: str | None) -> None`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/import_/test_pan_claims.py`:

```python
from datetime import datetime, timedelta, timezone
import uuid

import pytest

from app.models.enums import Relationship
from app.models.user import HouseholdMember, User
from app.services.import_ import pan_claims
from app.services.import_.crypto import decrypt_pan, encrypt_pan, hash_pan
from app.services.import_.pan_claims import (
    PENDING_PAN_TTL,
    CrossAccountPanBlockedError,
    PanBelongsToOtherMemberError,
    PanMismatchForMemberError,
    claim_pan_for_member,
    confirm_pan_claim,
    release_pending_pan_claim,
)

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def _aware(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


def _user(db):
    user = User(id=uuid.uuid4(), phone_number=f"+91{uuid.uuid4().int % 10**10:010d}", created_at=NOW)
    db.add(user)
    db.flush()
    return user


def _member(db, user, name="Ayush", *, pan=None, pending_until=None, relationship=Relationship.SELF):
    member = HouseholdMember(
        id=uuid.uuid4(), user_id=user.id, name=name, relationship=relationship, created_at=NOW,
        pan_encrypted=encrypt_pan(pan) if pan else None,
        pan_lookup_hash=hash_pan(pan) if pan else None,
        pan_pending_until=pending_until,
    )
    db.add(member)
    db.commit()
    return member


def test_no_parsed_pan_claims_nothing(db_session):
    member = _member(db_session, _user(db_session))
    assert claim_pan_for_member(db_session, member, None, pending=True, now=NOW) is None
    assert member.pan_lookup_hash is None


def test_fresh_member_gets_a_pending_claim(db_session):
    member = _member(db_session, _user(db_session))
    claimed = claim_pan_for_member(db_session, member, "abcde1234f", pending=True, now=NOW)
    assert claimed == hash_pan("ABCDE1234F")
    assert member.pan_lookup_hash == hash_pan("ABCDE1234F")
    assert decrypt_pan(member.pan_encrypted) == "ABCDE1234F"
    assert _aware(member.pan_pending_until) == NOW + PENDING_PAN_TTL


def test_fresh_member_gets_a_permanent_claim_on_the_one_step_path(db_session):
    member = _member(db_session, _user(db_session))
    claim_pan_for_member(db_session, member, "ABCDE1234F", pending=False, now=NOW)
    assert member.pan_lookup_hash == hash_pan("ABCDE1234F")
    assert member.pan_pending_until is None


def test_reimport_of_own_permanent_pan_stays_permanent(db_session):
    member = _member(db_session, _user(db_session), pan="ABCDE1234F")
    claim_pan_for_member(db_session, member, "ABCDE1234F", pending=True, now=NOW)
    assert member.pan_pending_until is None


def test_reupload_of_own_pending_pan_refreshes_expiry(db_session):
    member = _member(db_session, _user(db_session), pan="ABCDE1234F", pending_until=NOW + timedelta(minutes=1))
    claim_pan_for_member(db_session, member, "ABCDE1234F", pending=True, now=NOW)
    assert _aware(member.pan_pending_until) == NOW + PENDING_PAN_TTL


def test_own_pending_pan_becomes_permanent_on_one_step_claim(db_session):
    member = _member(db_session, _user(db_session), pan="ABCDE1234F", pending_until=NOW + timedelta(minutes=1))
    claim_pan_for_member(db_session, member, "ABCDE1234F", pending=False, now=NOW)
    assert member.pan_pending_until is None


def test_pan_held_by_another_member_of_same_account_conflicts(db_session):
    user = _user(db_session)
    _member(db_session, user, "Priya", pan="BCDEF2222B", relationship=Relationship.SPOUSE)
    mom = _member(db_session, user, "Mom", relationship=Relationship.PARENT)
    with pytest.raises(PanBelongsToOtherMemberError) as exc:
        claim_pan_for_member(db_session, mom, "BCDEF2222B", pending=True, now=NOW)
    assert exc.value.code == "pan_belongs_to_other_member"
    assert "Mom" in exc.value.message
    assert "Priya" not in exc.value.message
    assert mom.pan_lookup_hash is None


def test_pan_held_by_another_account_is_blocked_without_leaking_it(db_session):
    _member(db_session, _user(db_session), "Someone Else", pan="ZZZZZ9999Z")
    member = _member(db_session, _user(db_session))
    with pytest.raises(CrossAccountPanBlockedError) as exc:
        claim_pan_for_member(db_session, member, "ZZZZZ9999Z", pending=True, now=NOW)
    assert exc.value.code == "cross_account_pan_blocked"
    assert "Someone Else" not in exc.value.message
    assert member.pan_lookup_hash is None


def test_different_pan_on_member_with_permanent_pan_conflicts(db_session):
    member = _member(db_session, _user(db_session), "Mom", pan="ABCDE1234F", relationship=Relationship.PARENT)
    with pytest.raises(PanMismatchForMemberError) as exc:
        claim_pan_for_member(db_session, member, "QWERT5678Y", pending=True, now=NOW)
    assert exc.value.code == "pan_mismatch_for_member"
    assert "Mom" in exc.value.message
    assert member.pan_lookup_hash == hash_pan("ABCDE1234F")


def test_different_pan_replaces_members_own_abandoned_pending_claim(db_session):
    member = _member(db_session, _user(db_session), pan="ABCDE1234F", pending_until=NOW + timedelta(minutes=30))
    claim_pan_for_member(db_session, member, "QWERT5678Y", pending=True, now=NOW)
    assert member.pan_lookup_hash == hash_pan("QWERT5678Y")


def test_expired_pending_claim_on_other_member_is_reclaimable(db_session):
    # _member commits, so pan_pending_until reads back from SQLite as a naive
    # datetime -- this also pins the naive/aware comparison (Review Focus 3).
    user = _user(db_session)
    stale = _member(db_session, user, "Mom", pan="ABCDE1234F", pending_until=NOW - timedelta(minutes=1),
                    relationship=Relationship.PARENT)
    db_session.expire_all()
    me = _member(db_session, user)
    claim_pan_for_member(db_session, me, "ABCDE1234F", pending=True, now=NOW)
    assert me.pan_lookup_hash == hash_pan("ABCDE1234F")
    assert stale.pan_lookup_hash is None
    assert stale.pan_encrypted is None
    assert stale.pan_pending_until is None


def test_unexpired_pending_claim_on_other_member_still_conflicts(db_session):
    user = _user(db_session)
    _member(db_session, user, "Mom", pan="ABCDE1234F", pending_until=NOW + timedelta(minutes=5),
            relationship=Relationship.PARENT)
    me = _member(db_session, user)
    with pytest.raises(PanBelongsToOtherMemberError):
        claim_pan_for_member(db_session, me, "ABCDE1234F", pending=True, now=NOW)


def test_losing_a_unique_index_race_surfaces_as_a_conflict(db_session, monkeypatch):
    user = _user(db_session)
    _member(db_session, user, "Priya", pan="BCDEF2222B", relationship=Relationship.SPOUSE)
    me = _member(db_session, user)
    real_holder_of = pan_claims._holder_of
    calls = {"n": 0}

    def misses_on_first_call(db, pan_hash, now):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_holder_of(db, pan_hash, now)

    monkeypatch.setattr(pan_claims, "_holder_of", misses_on_first_call)
    with pytest.raises(PanBelongsToOtherMemberError):
        claim_pan_for_member(db_session, me, "BCDEF2222B", pending=True, now=NOW)
    db_session.refresh(me)
    assert me.pan_lookup_hash is None


def test_confirm_makes_pending_claim_permanent(db_session):
    member = _member(db_session, _user(db_session), pan="ABCDE1234F", pending_until=NOW + timedelta(minutes=30))
    confirm_pan_claim(db_session, member, "ABCDE1234F")
    assert member.pan_pending_until is None
    assert member.pan_lookup_hash == hash_pan("ABCDE1234F")


def test_confirm_without_parsed_pan_is_a_noop(db_session):
    member = _member(db_session, _user(db_session))
    confirm_pan_claim(db_session, member, None)
    assert member.pan_lookup_hash is None


def test_confirm_reclaims_a_pan_whose_pending_claim_vanished(db_session):
    member = _member(db_session, _user(db_session))
    confirm_pan_claim(db_session, member, "ABCDE1234F")
    assert member.pan_lookup_hash == hash_pan("ABCDE1234F")
    assert member.pan_pending_until is None


def test_confirm_claim_that_lost_its_pan_imports_without_it(db_session):
    user = _user(db_session)
    _member(db_session, user, "Priya", pan="BCDEF2222B", relationship=Relationship.SPOUSE)
    me = _member(db_session, user)
    confirm_pan_claim(db_session, me, "BCDEF2222B")  # must not raise
    assert me.pan_lookup_hash is None


def test_release_clears_only_a_matching_pending_claim(db_session):
    user = _user(db_session)
    pending = _member(db_session, user, "Mom", pan="ABCDE1234F", pending_until=NOW + timedelta(minutes=30),
                      relationship=Relationship.PARENT)
    permanent = _member(db_session, user, pan="QWERT5678Y")

    release_pending_pan_claim(pending, "ZZZZZ9999Z")
    assert pending.pan_lookup_hash == hash_pan("ABCDE1234F")

    release_pending_pan_claim(permanent, "QWERT5678Y")
    assert permanent.pan_lookup_hash == hash_pan("QWERT5678Y")

    release_pending_pan_claim(pending, "ABCDE1234F")
    assert pending.pan_lookup_hash is None
    assert pending.pan_encrypted is None
    assert pending.pan_pending_until is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/services/import_/test_pan_claims.py -q -p no:cacheprovider --basetemp=C:/Users/Dell/AppData/Local/Temp/uf_pt`
Expected: collection error, `ModuleNotFoundError: No module named 'app.services.import_.pan_claims'`.

- [ ] **Step 3: Implement the module**

Create `backend/app/services/import_/pan_claims.py`:

```python
"""Upload-time PAN claims: the one rule that ties a CAS to a household member.

Replaces the confirm-time attribution engine (attribution.py, removed
2026-09-24). A PAN is claimed for the member the file was uploaded for at
parse time -- *pending* on the two-step /imports/parse -> /imports/confirm
path, *permanent* on the one-step /cas-imports path. Confirm only ever
finalizes a claim; it never prompts or blocks. See
Docs/superpowers/specs/2026-09-24-pan-at-upload-attribution-design.md.

Storage is unchanged from ADR-004 (reopened): pan_encrypted + pan_lookup_hash
under the unique index. A pending claim occupies that index like a permanent
one, so no one else can take a PAN while its review session is open.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import HouseholdMember
from app.services.import_.crypto import encrypt_pan, hash_pan

logger = logging.getLogger(__name__)

# Must outlive the preview session that created the claim
# (service.SESSION_TTL_MINUTES = 60): while a session can still be confirmed,
# its pending PAN can never have expired and been taken by someone else.
PENDING_PAN_TTL = timedelta(minutes=65)

CROSS_ACCOUNT_PAN_BLOCKED_MESSAGE = (
    "This PAN is already tracked under a different Unifolio account. "
    "Contact support if you believe this is a mistake."
)


class PanConflictError(Exception):
    """Base for every upload-time PAN conflict. `code` is the 409 detail code."""

    code = "pan_conflict"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CrossAccountPanBlockedError(PanConflictError):
    code = "cross_account_pan_blocked"


class PanBelongsToOtherMemberError(PanConflictError):
    code = "pan_belongs_to_other_member"


class PanMismatchForMemberError(PanConflictError):
    code = "pan_mismatch_for_member"


def _as_aware(value: datetime | None) -> datetime | None:
    # SQLite hands DateTime(timezone=True) back naive; values are always
    # written as UTC, so tagging them UTC is exact.
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _is_expired_pending(member: HouseholdMember, now: datetime) -> bool:
    until = _as_aware(member.pan_pending_until)
    return until is not None and until <= now


def _clear_pan(member: HouseholdMember) -> None:
    member.pan_encrypted = None
    member.pan_lookup_hash = None
    member.pan_pending_until = None


def _holder_of(db: Session, pan_hash: str, now: datetime) -> HouseholdMember | None:
    """The member currently holding this PAN, or None. An expired pending
    claim is cleared here (lazily -- there is no sweep job) and reported as
    no holder."""
    holder = db.query(HouseholdMember).filter(HouseholdMember.pan_lookup_hash == pan_hash).first()
    if holder is not None and _is_expired_pending(holder, now):
        _clear_pan(holder)
        db.flush()
        return None
    return holder


def _raise_for_holder(member: HouseholdMember, holder: HouseholdMember) -> None:
    if holder.user_id != member.user_id:
        raise CrossAccountPanBlockedError(CROSS_ACCOUNT_PAN_BLOCKED_MESSAGE)
    raise PanBelongsToOtherMemberError(
        f"The statement you uploaded for {member.name} belongs to a PAN that's already "
        f"in Unifolio. Please choose {member.name}'s own CAS."
    )


def claim_pan_for_member(
    db: Session,
    member: HouseholdMember,
    pan: str | None,
    *,
    pending: bool,
    now: datetime | None = None,
) -> str | None:
    """Claims `pan` for `member` or raises a PanConflictError. Flushes, never
    commits: the caller commits with the rest of its unit of work, so a later
    failure in the same request rolls the claim back too."""
    if not pan:
        return None
    now = now or datetime.now(timezone.utc)
    pan_hash = hash_pan(pan)

    holder = _holder_of(db, pan_hash, now)
    if holder is not None and holder.id != member.id:
        _raise_for_holder(member, holder)

    if holder is not None:
        # Already this member's PAN. Never downgrade a permanent claim.
        if not pending:
            member.pan_pending_until = None
        elif member.pan_pending_until is not None:
            member.pan_pending_until = now + PENDING_PAN_TTL
        db.flush()
        return pan_hash

    if member.pan_lookup_hash is not None and member.pan_pending_until is None:
        raise PanMismatchForMemberError(
            f"This statement's PAN doesn't match {member.name}'s. "
            f"Please choose {member.name}'s own CAS."
        )

    # No holder: either a fresh member, or this member's own pending claim
    # for a different PAN (an abandoned earlier upload), which is replaced.
    member.pan_encrypted = encrypt_pan(pan)
    member.pan_lookup_hash = pan_hash
    member.pan_pending_until = now + PENDING_PAN_TTL if pending else None
    try:
        db.flush()
    except IntegrityError:
        # Lost a race for the unique index between _holder_of and flush.
        # Full rollback (not a savepoint -- pysqlite savepoints are
        # unreliable): every caller aborts its request with a 409 on this
        # path, and claims run before any other write in that request.
        db.rollback()
        winner = _holder_of(db, pan_hash, now)
        if winner is not None and winner.id != member.id:
            _raise_for_holder(member, winner)
        raise
    return pan_hash


def confirm_pan_claim(db: Session, member: HouseholdMember, pan: str | None) -> None:
    """Makes the upload-time claim permanent. Never raises: Confirm Import
    must not be blocked by PAN (spec Goal 3). Call before any other write in
    the confirm transaction -- the fallback claim may roll back."""
    if not pan:
        return
    if member.pan_lookup_hash == hash_pan(pan):
        member.pan_pending_until = None
        return
    # The pending claim vanished (e.g. a sibling session for the same member
    # was discarded). Re-claim permanently; if someone else holds it now,
    # import without storing the PAN rather than failing the confirm.
    try:
        claim_pan_for_member(db, member, pan, pending=False)
    except PanConflictError:
        logger.warning(
            "PAN claim for household member %s lost before confirm; importing without storing PAN",
            member.id,
        )


def release_pending_pan_claim(member: HouseholdMember, pan: str | None) -> None:
    """Drops this member's *pending* claim for `pan`. A permanent PAN, or a
    pending claim for a different PAN, is left alone."""
    if not pan or member.pan_pending_until is None:
        return
    if member.pan_lookup_hash == hash_pan(pan):
        _clear_pan(member)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/services/import_/test_pan_claims.py -q -p no:cacheprovider --basetemp=C:/Users/Dell/AppData/Local/Temp/uf_pt`
Expected: 18 passed.

If `test_losing_a_unique_index_race_surfaces_as_a_conflict` fails because `db.rollback()` also discarded the fixture's committed rows, it didn't: `_member` commits every row before the claim. Re-read the test before changing the implementation.

- [ ] **Step 5: Checkpoint.** Leave the changes uncommitted.

---

## Task 3: Two-step service path (`service.py`): start, confirm and discard

**Files:**
- Modify: `backend/app/services/import_/service.py` (imports; `build_import_preview`; `confirm_import`; new `start_import_session`, `discard_import_session`, `_is_session_expired`)
- Modify: `backend/tests/services/import_/test_service.py`

**Interfaces:**
- Consumes: `claim_pan_for_member`, `confirm_pan_claim`, `release_pending_pan_claim`, `PENDING_PAN_TTL` (Task 2); `commit_off_loop` from `app.db.session`.
- Produces:
  - `build_import_preview(parse_result, filename, pdf_bytes, client=None, *, household_member_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None) -> ImportPreviewResponse`. It stores both ids on the session.
  - `async start_import_session(db: Session, user_id: uuid.UUID, member: HouseholdMember, parse_result: ParseResult, filename: str, pdf_bytes: bytes, client: MfApiClient | None = None) -> ImportPreviewResponse`. It claims the PAN as pending, builds the preview, then commits. It raises `PanConflictError` before creating any session.
  - `confirm_import(db, session_id, household_member_id, scheme_confirmations, user_id) -> ImportConfirmResponse`. The `confirmed_member_override` parameter is removed.
  - `discard_import_session(db: Session, session_id: str, user_id: uuid.UUID) -> None`

- [ ] **Step 1: Remove the attribution-era tests and the override argument**

In `backend/tests/services/import_/test_service.py`:
- Delete these four test functions entirely: `test_confirm_import_requires_attribution_confirmation_before_writing`, `test_confirm_import_continue_override_keeps_selected_member_for_persistence`, `test_confirm_import_switch_override_uses_submitted_matched_member_for_persistence`, `test_confirm_import_cross_account_pan_match_blocks_even_with_override`.
- In `test_confirm_import_returns_generic_cross_account_warning`, delete the six-line comment starting `# Cross-account collisions are now a hard block`. Keep its assertions.
- Replace line 17 (`from app.services.import_.attribution import ...`) with:

```python
from app.services.import_.pan_claims import PENDING_PAN_TTL, PanBelongsToOtherMemberError
```

- Remove every `confirmed_member_override=True,` argument line:

```bash
sed -i '/^\s*confirmed_member_override=True,\?\s*$/d' tests/services/import_/test_service.py
grep -n "confirmed_member_override\|attribution" tests/services/import_/test_service.py
```

Expected grep output: none.

- Extend the import on line 20 to:

```python
from app.services.import_.service import (
    SESSION_TTL_MINUTES,
    SchemeConfidenceError,
    _preview_sessions,
    build_import_preview,
    confirm_import,
    discard_import_session,
    start_import_session,
)
```

- [ ] **Step 2: Write the new failing tests**

Append to `backend/tests/services/import_/test_service.py`. These use the conftest `db_session` fixture, not `_session()`: `start_import_session` commits through `commit_off_loop` (a worker thread), and only `db_session`'s engine allows cross-thread use.

```python
from dataclasses import replace as _replace


def _with_pan(parse_result, pan):
    return _replace(parse_result, investor=_replace(parse_result.investor, pan=pan))


def _db_member(db, *, name="Self", relationship=Relationship.SELF, user=None):
    if user is None:
        user = User(id=uuid.uuid4(), phone_number=f"+91{uuid.uuid4().int % 10**10:010d}",
                    created_at=datetime.now(timezone.utc))
        db.add(user)
        db.flush()
    member = HouseholdMember(id=uuid.uuid4(), user_id=user.id, name=name,
                             relationship=relationship, created_at=datetime.now(timezone.utc))
    db.add(member)
    db.commit()
    return member


def _start(db, member, parse_result):
    return asyncio.run(start_import_session(
        db, member.user_id, member, parse_result, "cas.pdf", b"%PDF-1.4 fake", client=_mocked_client(),
    ))


def test_pending_pan_ttl_outlives_the_preview_session():
    assert PENDING_PAN_TTL > timedelta(minutes=SESSION_TTL_MINUTES)


def test_start_import_session_claims_pan_as_pending_and_binds_session(db_session):
    member = _db_member(db_session)
    preview = _start(db_session, member, _with_pan(_sample_parse_result(), "ABCDE1234F"))

    db_session.refresh(member)
    assert member.pan_lookup_hash == hash_pan("ABCDE1234F")
    assert member.pan_pending_until is not None
    session = _preview_sessions[preview.session_id]
    assert session["household_member_id"] == member.id
    assert session["user_id"] == member.user_id


def test_start_import_session_conflict_creates_no_session(db_session):
    me = _db_member(db_session)
    spouse = _db_member(db_session, name="Priya", relationship=Relationship.SPOUSE,
                        user=db_session.get(User, me.user_id))
    spouse.pan_encrypted = encrypt_pan("BCDEF2222B")
    spouse.pan_lookup_hash = hash_pan("BCDEF2222B")
    db_session.commit()
    before = set(_preview_sessions)

    with pytest.raises(PanBelongsToOtherMemberError):
        _start(db_session, me, _with_pan(_sample_parse_result(), "BCDEF2222B"))

    assert set(_preview_sessions) == before
    db_session.refresh(me)
    assert me.pan_lookup_hash is None


def test_fresh_account_first_import_confirms_straight_through(db_session):
    # Regression for the 2026-09-23 staging bug: a brand-new member with no
    # PAN and no folios, CAS name unrelated to the member name -> no prompt.
    member = _db_member(db_session, name="Me")
    preview = _start(db_session, member, _with_pan(_sample_parse_result(), "ABCDE1234F"))

    result = confirm_import(db_session, preview.session_id, member.id, scheme_confirmations=[],
                            user_id=member.user_id)

    assert result.added == 1
    db_session.refresh(member)
    assert member.pan_lookup_hash == hash_pan("ABCDE1234F")
    assert member.pan_pending_until is None


def test_confirm_rejects_session_bound_to_another_member(db_session):
    member = _db_member(db_session)
    other = _db_member(db_session, name="Mom", relationship=Relationship.PARENT,
                       user=db_session.get(User, member.user_id))
    preview = _start(db_session, member, _sample_parse_result())

    with pytest.raises(ValueError):
        confirm_import(db_session, preview.session_id, other.id, scheme_confirmations=[],
                       user_id=member.user_id)


def test_confirm_rejects_expired_session(db_session):
    member = _db_member(db_session)
    preview = _start(db_session, member, _sample_parse_result())
    _preview_sessions[preview.session_id]["created_at"] -= timedelta(minutes=SESSION_TTL_MINUTES + 1)

    with pytest.raises(ValueError):
        confirm_import(db_session, preview.session_id, member.id, scheme_confirmations=[],
                       user_id=member.user_id)
    assert preview.session_id not in _preview_sessions


def test_discard_releases_pending_pan_and_drops_session(db_session):
    member = _db_member(db_session)
    preview = _start(db_session, member, _with_pan(_sample_parse_result(), "ABCDE1234F"))

    discard_import_session(db_session, preview.session_id, member.user_id)

    assert preview.session_id not in _preview_sessions
    db_session.refresh(member)
    assert member.pan_lookup_hash is None


def test_discard_ignores_other_users_session(db_session):
    member = _db_member(db_session)
    preview = _start(db_session, member, _with_pan(_sample_parse_result(), "ABCDE1234F"))

    discard_import_session(db_session, preview.session_id, uuid.uuid4())

    assert preview.session_id in _preview_sessions
    db_session.refresh(member)
    assert member.pan_lookup_hash == hash_pan("ABCDE1234F")


def test_discard_unknown_session_is_a_noop(db_session):
    discard_import_session(db_session, "does-not-exist", uuid.uuid4())


def test_confirm_after_sibling_session_discard_still_stores_pan(db_session):
    # Review Focus 1: two review sessions for the same member + PAN.
    member = _db_member(db_session)
    first = _start(db_session, member, _with_pan(_sample_parse_result(), "ABCDE1234F"))
    second = _start(db_session, member, _with_pan(_sample_parse_result(), "ABCDE1234F"))

    discard_import_session(db_session, first.session_id, member.user_id)
    confirm_import(db_session, second.session_id, member.id, scheme_confirmations=[],
                   user_id=member.user_id)

    db_session.refresh(member)
    assert member.pan_lookup_hash == hash_pan("ABCDE1234F")
    assert member.pan_pending_until is None
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/services/import_/test_service.py -q -p no:cacheprovider --basetemp=C:/Users/Dell/AppData/Local/Temp/uf_pt`
Expected: collection error, `ImportError: cannot import name 'discard_import_session'`.

- [ ] **Step 4: Implement**

In `backend/app/services/import_/service.py`:

1. Replace the `from app.services.import_.attribution import (...)` block with:

```python
from app.db.session import commit_off_loop
from app.services.import_.pan_claims import (
    claim_pan_for_member,
    confirm_pan_claim,
    release_pending_pan_claim,
)
```

2. Below `_sweep_expired_sessions`, add:

```python
def _is_session_expired(session: dict[str, Any], ttl_minutes: int = SESSION_TTL_MINUTES) -> bool:
    # Checked at confirm time too, not only swept on the next parse: a pending
    # PAN claim lives PENDING_PAN_TTL (65 min), so a session must never be
    # confirmable past its own 60-minute TTL.
    return session["created_at"] < datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
```

3. Change `build_import_preview`'s signature and session dict:

```python
async def build_import_preview(
    parse_result: ParseResult,
    filename: str,
    pdf_bytes: bytes,
    client: MfApiClient | None = None,
    *,
    household_member_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> ImportPreviewResponse:
```

and in `_preview_sessions[session_id] = {...}` add two keys after `"pdf_bytes": pdf_bytes,`:

```python
        # Set by start_import_session (the only production caller); None only
        # when tests build a preview directly.
        "household_member_id": household_member_id, "user_id": user_id,
```

4. Add after `build_import_preview`:

```python
async def start_import_session(
    db: Session,
    user_id: uuid.UUID,
    member: HouseholdMember,
    parse_result: ParseResult,
    filename: str,
    pdf_bytes: bytes,
    client: MfApiClient | None = None,
) -> ImportPreviewResponse:
    """Upload-time step of the two-step import: claims the CAS's PAN for
    `member` as pending (raising PanConflictError before any session exists),
    builds the preview, then commits the claim. If the preview fails, the
    uncommitted claim is rolled back with the request's session."""
    claim_pan_for_member(db, member, parse_result.investor.pan, pending=True)
    preview = await build_import_preview(
        parse_result, filename, pdf_bytes, client,
        household_member_id=member.id, user_id=user_id,
    )
    await commit_off_loop(db)
    return preview
```

5. Replace the start of `confirm_import`, from its signature through `backfill_pan_if_missing(db, target_member, parse_result)`, with:

```python
def confirm_import(
    db: Session,
    session_id: str,
    household_member_id: uuid.UUID,
    scheme_confirmations: list[SchemeConfirmation],
    user_id: uuid.UUID,
) -> ImportConfirmResponse:
    session = _preview_sessions.get(session_id)
    if session and _is_session_expired(session):
        del _preview_sessions[session_id]
        session = None
    if (
        not session
        or session.get("user_id") not in (None, user_id)
        or session.get("household_member_id") not in (None, household_member_id)
    ):
        raise ValueError("Import session not found or expired.")

    parse_result: ParseResult = session["parse_result"]
    # The member was fixed and the PAN checked at upload (start_import_session);
    # confirm only finalizes. First write in this transaction on purpose --
    # confirm_pan_claim's fallback path may roll back.
    target_member_id = household_member_id
    target_member = db.get(HouseholdMember, target_member_id)
    confirm_pan_claim(db, target_member, parse_result.investor.pan)
```

Leave the rest of `confirm_import` unchanged. It already uses `target_member_id`.

6. Add after `confirm_import`:

```python
def discard_import_session(db: Session, session_id: str, user_id: uuid.UUID) -> None:
    """Abandons a preview session on purpose (Back / reset / Cancel) and
    releases its pending PAN claim. Idempotent; never touches another user's
    session."""
    session = _preview_sessions.get(session_id)
    if session is None or session.get("user_id") != user_id:
        return
    del _preview_sessions[session_id]
    member_id = session.get("household_member_id")
    member = db.get(HouseholdMember, member_id) if member_id else None
    if member is not None:
        release_pending_pan_claim(member, session["parse_result"].investor.pan)
        db.commit()
```

- [ ] **Step 5: Run the service tests**

Run: `.venv/Scripts/python.exe -m pytest tests/services/import_/test_service.py tests/services/import_/test_pan_claims.py -q -p no:cacheprovider --basetemp=C:/Users/Dell/AppData/Local/Temp/uf_pt`
Expected: all PASS.

- [ ] **Step 6: Checkpoint.** Leave the changes uncommitted. (`app/api/imports.py` still imports `attribution` and still passes `confirmed_member_override`. Task 4 fixes that, so don't run the whole suite yet.)

---

## Task 4: `/imports` routes: parse takes the member, confirm has no override, new discard

**Files:**
- Modify: `backend/app/api/imports.py` (imports; `parse_import`; `confirm_import_route`; new `discard_import_session_route`)
- Modify: `backend/app/services/import_/schemas.py:59-63` (`ImportConfirmRequest`)
- Modify: `backend/tests/api/test_imports_routes.py`

**Interfaces:**
- Consumes: `start_import_session`, `discard_import_session`, the new `confirm_import` signature (Task 3); `PanConflictError` (Task 2).
- Produces (HTTP):
  - `POST /imports/parse`. It now requires the form field `household_member_id`, answers 400 `invalid_id` for a malformed id and 404 for another user's member, and 409 `{code, message}` for any `PanConflictError`.
  - `POST /imports/confirm`. The body no longer accepts `confirmed_member_override` (it's ignored if a client still sends it).
  - `POST /imports/sessions/{session_id}/discard` → 204.

- [ ] **Step 1: Update the existing route tests**

In `backend/tests/api/test_imports_routes.py`:
- Delete `test_confirm_route_maps_member_mismatch_to_structured_409`.
- In `test_parse_route_rejects_non_pdf`, `test_parse_route_rejects_spoofed_pdf_content`, `test_parse_route_rejects_oversized_pdf` and `test_parse_route_surfaces_parse_error_as_422`:
  - Replace `headers = _authed_headers(client, "<phone>")` with `headers, member_id = _authed_headers_and_member(client, "<same phone>")`.
  - Change `data={"password": ...}` to `data={"password": ..., "household_member_id": member_id}`.
- In `test_parse_then_confirm_lands_a_transaction_in_the_real_db`, add `"household_member_id": member_id` to the parse `data=` and delete the `"confirmed_member_override": True,` line from the confirm JSON.
- Check nothing else references the removed names:

```bash
grep -n "member_mismatch\|confirmed_member_override\|attribution" tests/api/test_imports_routes.py
```

Expected: none.

- [ ] **Step 2: Write the new failing route tests**

Append to `backend/tests/api/test_imports_routes.py`:

```python
def _parse(client, headers, member_id, parse_result, cache_dir):
    from app.services.import_.enrich import mfapi_client

    async def _fake_get_json(_self, url):
        if url.endswith("/latest"):
            return {"meta": {"scheme_category": "Equity Scheme - Flexi Cap Fund"}}
        return [{"schemeCode": "125497", "schemeName": "HDFC Flexi Cap Fund - Direct Plan - Growth"}]

    with (
        patch("app.api.imports.parse_cas_pdf_bytes", return_value=parse_result),
        patch("app.services.import_.enrich.MfApiClient._get_json", new=_fake_get_json),
        # Same isolation as test_parse_then_confirm_lands_a_transaction_in_the_real_db:
        # keep the mfapi disk cache out of backend/.cache.
        patch.object(mfapi_client, "cache_dir", cache_dir),
        patch.object(mfapi_client, "_schemes", None),
    ):
        return client.post(
            "/imports/parse",
            files={"file": ("cas.pdf", b"%PDF-fake", "application/pdf")},
            data={"password": "x", "household_member_id": member_id},
            headers=headers,
        )


def _sample_with_pan(pan):
    from dataclasses import replace

    sample = _sample_parse_result()
    return replace(sample, investor=replace(sample.investor, pan=pan))


def test_parse_route_requires_household_member_id(client):
    headers = _authed_headers(client, "+919999999971")
    response = client.post(
        "/imports/parse",
        files={"file": ("cas.pdf", b"%PDF-fake", "application/pdf")},
        data={"password": "x"},
        headers=headers,
    )
    assert response.status_code == 422


def test_parse_route_404s_for_another_users_member(client):
    _, other_member_id = _authed_headers_and_member(client, "+919999999972")
    headers = _authed_headers(client, "+919999999973")
    response = client.post(
        "/imports/parse",
        files={"file": ("cas.pdf", b"%PDF-fake", "application/pdf")},
        data={"password": "x", "household_member_id": other_member_id},
        headers=headers,
    )
    assert response.status_code == 404


def test_parse_route_maps_cross_account_pan_to_409_without_leaking(client, tmp_path):
    headers_a, member_a = _authed_headers_and_member(client, "+919999999974")
    assert _parse(client, headers_a, member_a, _sample_with_pan("ZZZZZ9999Z"), tmp_path).status_code == 200

    headers_b, member_b = _authed_headers_and_member(client, "+919999999975")
    response = _parse(client, headers_b, member_b, _sample_with_pan("ZZZZZ9999Z"), tmp_path)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "cross_account_pan_blocked"
    assert member_a not in response.text


def test_parse_route_maps_same_account_pan_to_409(client, tmp_path):
    headers, self_id = _authed_headers_and_member(client, "+919999999976")
    mom_id = client.post(
        "/household-members", json={"name": "Mom", "relationship": "parent"}, headers=headers,
    ).json()["id"]
    assert _parse(client, headers, self_id, _sample_with_pan("ABCDE1234F"), tmp_path).status_code == 200

    response = _parse(client, headers, mom_id, _sample_with_pan("ABCDE1234F"), tmp_path)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "pan_belongs_to_other_member"


def test_discard_route_returns_204_and_frees_the_pan(client, tmp_path):
    headers, self_id = _authed_headers_and_member(client, "+919999999977")
    mom_id = client.post(
        "/household-members", json={"name": "Mom", "relationship": "parent"}, headers=headers,
    ).json()["id"]
    session_id = _parse(client, headers, self_id, _sample_with_pan("ABCDE1234F"), tmp_path).json()["session_id"]

    discard = client.post(f"/imports/sessions/{session_id}/discard", headers=headers)

    assert discard.status_code == 204
    # Freed: the same PAN can now be claimed for another member.
    assert _parse(client, headers, mom_id, _sample_with_pan("ABCDE1234F"), tmp_path).status_code == 200


def test_discard_route_is_idempotent_for_unknown_sessions(client):
    headers = _authed_headers(client, "+919999999978")
    assert client.post("/imports/sessions/nope/discard", headers=headers).status_code == 204
```

`_sample_parse_result` already exists in this file (used by `test_parse_then_confirm_lands_a_transaction_in_the_real_db`); reuse it.

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/api/test_imports_routes.py -q -p no:cacheprovider --basetemp=C:/Users/Dell/AppData/Local/Temp/uf_pt`
Expected: the new tests FAIL (parse ignores `household_member_id`; discard route 404/405).

- [ ] **Step 4: Implement**

In `backend/app/services/import_/schemas.py`, delete the line `    confirmed_member_override: bool = False` from `ImportConfirmRequest`.

In `backend/app/api/imports.py`:

1. Change the fastapi import to include `Response`. Replace the `from app.services.import_.attribution import (...)` block with:

```python
from app.services.import_.pan_claims import PanConflictError
```

and replace the service import line with:

```python
from app.services.import_.service import (  # logic to process & confirm import
    SchemeConfidenceError,
    confirm_import,
    discard_import_session,
    start_import_session,
)
```

2. Replace `parse_import` with:

```python
@router.post("/parse", response_model=ImportPreviewResponse)
async def parse_import(
    file: UploadFile = File(...),
    password: str = Form(...),
    household_member_id: str = Form(...),
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail={"code": "invalid_file", "message": "Please upload a PDF file."})

    try:
        member_uuid = uuid.UUID(household_member_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail={"code": "invalid_id", "message": "Invalid household_member_id."}
        ) from exc
    # Ownership gate: the PAN is claimed for this member at upload, so it
    # must be one of the caller's own members (IDOR).
    member = get_household_member_for_user(db, user.id, member_uuid)
    if member is None:
        raise HTTPException(status_code=404, detail="Household member not found.")

    pdf_bytes = await file.read()
    try:
        validate_file_payload(pdf_bytes)
    except InvalidFileFormatError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_file", "message": str(exc)},
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail={"code": "file_too_large", "message": str(exc)},
        ) from exc

    try:
        parse_result = parse_cas_pdf_bytes(pdf_bytes, password)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc

    try:
        return await start_import_session(db, user.id, member, parse_result, file.filename, pdf_bytes)
    except PanConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message}) from exc
```

3. In `confirm_import_route`: delete `confirmed_member_override=body.confirmed_member_override,` from the `confirm_import(...)` call, and delete the three `except` blocks for `AttributionConfirmationRequiredError`, `CrossAccountPanBlockedError` and `PanAlreadyAttributedError`. Keep the `SchemeConfidenceError` and `ValueError` handlers.

4. Add after `confirm_import_route`:

```python
@router.post("/sessions/{session_id}/discard", status_code=204)
def discard_import_session_route(
    session_id: str,
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> Response:
    discard_import_session(db, session_id, user.id)
    return Response(status_code=204)
```

- [ ] **Step 5: Run the route tests**

Run: `.venv/Scripts/python.exe -m pytest tests/api/test_imports_routes.py tests/services/import_/test_service.py -q -p no:cacheprovider --basetemp=C:/Users/Dell/AppData/Local/Temp/uf_pt`
Expected: all PASS.

- [ ] **Step 6: Checkpoint.** Leave the changes uncommitted.

---

## Task 5: One-step `/cas-imports` path claims the PAN permanently; remove `attribution.py`

**Files:**
- Modify: `backend/app/services/import_/lifecycle_service.py` (imports; `create_cas_import`; `retry_cas_import_password`; module docstring line "Attribution resolution & confirmation gating (FR-4).")
- Modify: `backend/app/api/cas_imports.py`
- Modify: `backend/app/services/import_/parser.py` (docstring lines 6-13 and comment lines 248-254)
- Delete: `backend/app/services/import_/attribution.py`, `backend/tests/services/import_/test_attribution.py`
- Modify: `backend/tests/services/import_/test_lifecycle_service.py`, `backend/tests/api/test_cas_imports_routes.py`

**Interfaces:**
- Consumes: `claim_pan_for_member`, `PanConflictError` (Task 2).
- Produces: `create_cas_import(db, user_id, household_member_id, file_bytes, filename, password, source_tab="upload") -> Import` and `retry_cas_import_password(db, import_id, user_id, new_password) -> Import`. The `confirmed_member_override` parameter is gone from both. They raise `PanConflictError` before committing anything new. The HTTP routes map it to 409 `{code, message}`.

- [ ] **Step 1: Rewrite the lifecycle tests**

In `backend/tests/services/import_/test_lifecycle_service.py`:
- Delete these tests: `test_cross_account_pan_match_blocks_import_even_with_override`, `test_create_cas_import_requires_attribution_confirmation`, `test_create_cas_import_accepts_attribution_confirmation_override`, `test_retry_cas_import_password_requires_attribution_confirmation`, `test_retry_cas_import_password_accepts_attribution_confirmation_override`. Also delete any helper they alone used (`_confirmation_required_decision`, and `_empty_parse_result` if nothing else uses it; check with grep).
- Replace the `from app.services.import_.attribution import (...)` block with:

```python
from app.services.import_.pan_claims import CrossAccountPanBlockedError, PanMismatchForMemberError
```

- Rename `test_cross_account_pan_match_blocks_import` to `test_cross_account_pan_blocks_one_step_import`, and replace its docstring with `"""A PAN held by another account is refused before anything commits."""`. Keep its body; it still raises `CrossAccountPanBlockedError`.
- Remove override lines and stale comments:

```bash
sed -i '/^\s*confirmed_member_override=True,\?\s*$/d' tests/services/import_/test_lifecycle_service.py
grep -n "confirmed_member_override\|attribution\|resolve_attribution" tests/services/import_/test_lifecycle_service.py
```

Delete any remaining comment lines the grep shows (for example the "`# confirmed_member_override=True: this test's intent is...`" comments at the old lines 188 and 404).

- Append:

```python
def test_one_step_import_stores_pan_permanently(db_session, sample_user_and_member, monkeypatch):
    user, member = sample_user_and_member
    parse_result = ParseResult(
        investor=ParsedInvestor(name="Anyone", email=None, pan_masked="A*****1F", pan="ABCDE1234F"),
        schemes=[], transactions=[], raw_json="{}",
    )
    monkeypatch.setattr("app.services.import_.lifecycle_service.parse_cas_pdf_bytes", lambda _b, _p: parse_result)

    rec = asyncio.run(create_cas_import(
        db=db_session, user_id=user.id, household_member_id=member.id,
        file_bytes=b"%PDF-1.4 statement", filename="statement.pdf", password="PASS",
    ))

    assert rec.status == ImportStatus.IMPORT_SUCCESSFUL
    db_session.refresh(member)
    assert member.pan_lookup_hash == hash_pan("ABCDE1234F")
    assert member.pan_pending_until is None


def test_one_step_import_refuses_a_different_pan_for_the_member(db_session, sample_user_and_member, monkeypatch):
    user, member = sample_user_and_member
    member.pan_encrypted = encrypt_pan("ABCDE1234F")
    member.pan_lookup_hash = hash_pan("ABCDE1234F")
    db_session.commit()
    parse_result = ParseResult(
        investor=ParsedInvestor(name="Anyone", email=None, pan_masked="Q*****8Y", pan="QWERT5678Y"),
        schemes=[], transactions=[], raw_json="{}",
    )
    monkeypatch.setattr("app.services.import_.lifecycle_service.parse_cas_pdf_bytes", lambda _b, _p: parse_result)

    with pytest.raises(PanMismatchForMemberError):
        asyncio.run(create_cas_import(
            db=db_session, user_id=user.id, household_member_id=member.id,
            file_bytes=b"%PDF-1.4 statement", filename="statement.pdf", password="PASS",
        ))
    db_session.rollback()
    assert db_session.query(Import).count() == 0
```

- [ ] **Step 2: Rewrite the `/cas-imports` route tests**

In `backend/tests/api/test_cas_imports_routes.py`:
- Delete `_member_mismatch_error`, `test_post_cas_imports_maps_member_mismatch_to_structured_409` and `test_retry_password_maps_member_mismatch_and_threads_override`.
- In `test_post_cas_imports_wrong_password_returns_password_required_and_allows_patch`, change the PATCH body to `json={"password": "CORRECT_PASS"}`. Delete the four-line comment above it that starts `# confirmed_member_override=True:`. Replace the four-line comment above `assert patch_data["parse_warnings"] == []` with `# No other account holds this statement's folios.`
- In `test_post_cas_imports_blocks_cross_account_pan_reuse_without_leaking_other_account`, replace the docstring's first two sentences with `"""A PAN held by another account is refused with a 409 at upload, without leaking that account and without writing anything."""`. Keep the body; `cross_account_pan_blocked` is still the code.
- Check:

```bash
grep -n "member_mismatch\|confirmed_member_override\|attribution\|pan_already_attributed" tests/api/test_cas_imports_routes.py
```

Expected: none.

- [ ] **Step 3: Run to verify failures**

Run: `.venv/Scripts/python.exe -m pytest tests/services/import_/test_lifecycle_service.py tests/api/test_cas_imports_routes.py -q -p no:cacheprovider --basetemp=C:/Users/Dell/AppData/Local/Temp/uf_pt`
Expected: FAIL/ERROR. `pan_claims` exceptions are not what lifecycle raises yet, and `create_cas_import` still calls `resolve_attribution`.

- [ ] **Step 4: Implement the lifecycle change**

In `backend/app/services/import_/lifecycle_service.py`:

1. Replace the `from app.services.import_.attribution import (...)` block with:

```python
from app.services.import_.pan_claims import claim_pan_for_member
```

2. In the module docstring, change `- Attribution resolution & confirmation gating (FR-4).` to `- Upload-time PAN claim for the chosen member (pan_claims.py).`

3. In `create_cas_import`: remove the `confirmed_member_override: bool = False,` parameter. Then replace everything from `# Attribution resolution` through `backfill_pan_if_missing(db, target_member, parse_result)` with:

```python
    # One-step path: the PAN is checked and claimed permanently right here,
    # before any transaction is written. A PanConflictError propagates
    # uncommitted and the route answers 409.
    target_member_id = household_member_id
    target_member = db.get(HouseholdMember, target_member_id)
    claim_pan_for_member(db, target_member, parse_result.investor.pan, pending=False)
```

Keep `store_cas_file(import_rec, user_id, file_bytes)` and everything after it.

4. In `retry_cas_import_password`: remove the `confirmed_member_override: bool = False,` parameter. Replace everything from `attribution = resolve_attribution(...)` through `backfill_pan_if_missing(db, target_member, parse_result)` with:

```python
    target_member_id = import_rec.household_member_id
    target_member = db.get(HouseholdMember, target_member_id)
    claim_pan_for_member(db, target_member, parse_result.investor.pan, pending=False)
```

Keep `store_cas_file(import_rec, user_id, pdf_bytes)` and everything after it.

- [ ] **Step 5: Implement the route change**

In `backend/app/api/cas_imports.py`:
1. Replace the `from app.services.import_.attribution import (...)` block with `from app.services.import_.pan_claims import PanConflictError`.
2. Delete `confirmed_member_override: bool = False` from `PasswordRetryRequest`.
3. Delete the `_member_mismatch_detail` function.
4. In `upload_cas_import`: delete the `confirmed_member_override: bool = Form(False),` parameter and the `confirmed_member_override=confirmed_member_override,` argument. Replace its three `except` blocks for `AttributionConfirmationRequiredError`, `CrossAccountPanBlockedError` and `PanAlreadyAttributedError` with:

```python
    except PanConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
```

5. In `retry_password`: delete the `confirmed_member_override=body.confirmed_member_override,` argument, and replace the same three `except` blocks with the identical `except PanConflictError` block above.

- [ ] **Step 6: Delete the old engine and fix the parser docs**

```bash
rm app/services/import_/attribution.py tests/services/import_/test_attribution.py
grep -rn "import_.attribution\|resolve_attribution\|backfill_pan_if_missing\|member_mismatch\|confirmed_member_override" app tests scripts
```

Expected grep output: none. (Use plain `rm`, not `git rm`: nothing is staged, and the user commits manually.)

In `backend/app/services/import_/parser.py`, replace the phrase `persistence via backfill_pan_if_missing for attribution matching` (docstring) with `persistence via pan_claims.claim_pan_for_member at upload time`. Replace `backfill_pan_if_missing reaches persistence for attribution matching.` (comment near line 254) with `pan_claims.claim_pan_for_member reaches persistence at upload time.`

- [ ] **Step 7: Run the full backend suite**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp=C:/Users/Dell/AppData/Local/Temp/uf_pt`
Expected: all pass. The last recorded baseline was 649 passed / 8 skipped. The count changes by the tests deleted and added here; there must be zero failures.

- [ ] **Step 8: Checkpoint.** Leave the changes uncommitted.

---

## Task 6: Frontend API, types and conflict helper

**Files:**
- Modify: `frontend/src/features/import/api.ts` (`parseImport`, `confirmImport`; new `discardImportSession`)
- Modify: `frontend/src/features/import/types.ts` (delete `MemberMismatchErrorPayload`)
- Create: `frontend/src/features/import/panConflict.ts`
- Test: `frontend/src/features/import/api.test.ts`, `frontend/src/features/import/panConflict.test.ts`

**Interfaces:**
- Produces:
  - `parseImport(file: File, password: string, householdMemberId: string): Promise<ImportPreviewResponse>`
  - `confirmImport(sessionId: string, householdMemberId: string, schemeConfirmations: SchemeConfirmation[]): Promise<ImportConfirmResponse>`
  - `discardImportSession(sessionId: string): Promise<void>`. It never throws.
  - `type PanConflictCode = "cross_account_pan_blocked" | "pan_belongs_to_other_member" | "pan_mismatch_for_member"`
  - `getPanConflict(err: unknown): { code: PanConflictCode; message: string } | null`

- [ ] **Step 1: Write the failing tests**

In `frontend/src/features/import/api.test.ts`, replace the test `"sends the explicit member-attribution override on a confirmation retry"` with:

```ts
  it("sends only session, member and confirmations on confirm", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ added: 1, skipped: 0, import_id: "imp1", warnings: [] }), { status: 200 }),
    );
    vi.stubGlobal("fetch", mockFetch);

    await confirmImport("sess1", "member-2", []);

    const [, options] = mockFetch.mock.calls[0];
    expect(JSON.parse(options.body as string)).toEqual({
      session_id: "sess1",
      household_member_id: "member-2",
      scheme_confirmations: [],
    });
  });

  it("sends the household member id on parse", async () => {
    const mockFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ session_id: "s1" }), { status: 200 }));
    vi.stubGlobal("fetch", mockFetch);

    await parseImport(new File(["x"], "cas.pdf"), "pw", "member-7");

    const [, options] = mockFetch.mock.calls[0];
    expect((options.body as FormData).get("household_member_id")).toBe("member-7");
  });

  it("posts to the discard endpoint and swallows failures", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", mockFetch);

    await expect(discardImportSession("sess 1")).resolves.toBeUndefined();
    expect(mockFetch.mock.calls[0][0]).toMatch(/\/imports\/sessions\/sess%201\/discard$/);
    expect(mockFetch.mock.calls[0][1]).toMatchObject({ method: "POST" });
  });
```

Add `parseImport` and `discardImportSession` to that file's import from `./api` if they're not already imported.

Create `frontend/src/features/import/panConflict.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { getPanConflict } from "./panConflict";

describe("getPanConflict", () => {
  it.each(["cross_account_pan_blocked", "pan_belongs_to_other_member", "pan_mismatch_for_member"])(
    "recognises a 409 %s",
    (code) => {
      expect(getPanConflict(new ApiError(409, { code, message: "m" }))).toEqual({ code, message: "m" });
    },
  );

  it("ignores other 409s, other statuses and non-API errors", () => {
    expect(getPanConflict(new ApiError(409, "Scheme needs an AMFI code."))).toBeNull();
    expect(getPanConflict(new ApiError(422, { code: "pan_mismatch_for_member", message: "m" }))).toBeNull();
    expect(getPanConflict(new TypeError("Failed to fetch"))).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run src/features/import/api.test.ts src/features/import/panConflict.test.ts`
Expected: FAIL. `discardImportSession` and `./panConflict` don't exist yet, and confirm still sends the override.

- [ ] **Step 3: Implement**

In `frontend/src/features/import/api.ts`, replace `parseImport` and `confirmImport` with the following, and add `discardImportSession` after them:

```ts
export async function parseImport(
  file: File,
  password: string,
  householdMemberId: string,
): Promise<ImportPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("password", password);
  // The backend checks and claims the CAS's PAN for this member at upload.
  formData.append("household_member_id", householdMemberId);

  const response = await fetch(`${API_BASE_URL}/imports/parse`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });

  if (!response.ok) {
    throw new ApiError(response.status, (await parseErrorDetail(response)) as ParseErrorPayload | string);
  }

  return (await response.json()) as ImportPreviewResponse;
}

export async function confirmImport(
  sessionId: string,
  householdMemberId: string,
  schemeConfirmations: SchemeConfirmation[],
): Promise<ImportConfirmResponse> {
  const response = await fetch(`${API_BASE_URL}/imports/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      session_id: sessionId,
      household_member_id: householdMemberId,
      scheme_confirmations: schemeConfirmations,
    }),
  });
```

(Keep the rest of `confirmImport` unchanged from `if (!response.ok) {` onwards.)

```ts
/** Best effort: releases a parsed-but-abandoned session's pending PAN. If
 * this never reaches the server, the pending PAN expires on its own. */
export async function discardImportSession(sessionId: string): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/imports/sessions/${encodeURIComponent(sessionId)}/discard`, {
      method: "POST",
      headers: authHeaders(),
    });
  } catch {
    // Intentionally ignored -- see doc comment.
  }
}
```

In `frontend/src/features/import/types.ts`, delete the `MemberMismatchErrorPayload` interface (lines 63-67).

Create `frontend/src/features/import/panConflict.ts`:

```ts
import { ApiError } from "./api";

export type PanConflictCode =
  | "cross_account_pan_blocked"
  | "pan_belongs_to_other_member"
  | "pan_mismatch_for_member";

const PAN_CONFLICT_CODES: readonly string[] = [
  "cross_account_pan_blocked",
  "pan_belongs_to_other_member",
  "pan_mismatch_for_member",
];

export interface PanConflict {
  code: PanConflictCode;
  message: string;
}

/** The upload-time PAN conflict carried by a /imports/parse 409, or null. */
export function getPanConflict(err: unknown): PanConflict | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const payload = err.payload as { code?: unknown; message?: unknown } | string | null;
  if (!payload || typeof payload === "string") return null;
  if (typeof payload.code !== "string" || !PAN_CONFLICT_CODES.includes(payload.code)) return null;
  return { code: payload.code as PanConflictCode, message: String(payload.message ?? "") };
}
```

- [ ] **Step 4: Run the tests**

Run: `npx vitest run src/features/import/api.test.ts src/features/import/panConflict.test.ts`
Expected: PASS. (`tsc` will fail until Tasks 8-10 update the callers. That's expected here.)

- [ ] **Step 5: Checkpoint.** Leave the changes uncommitted.

---

## Task 7: `PanConflictDialog` component

**Files:**
- Create: `frontend/src/features/import/PanConflictDialog.tsx`
- Test: `frontend/src/features/import/PanConflictDialog.test.tsx`

**Interfaces:**
- Produces: `PanConflictDialog({ isOpen, message, secondaryLabel, onChangeFile, onSecondary }: { isOpen: boolean; message: string; secondaryLabel: string; onChangeFile: () => void; onSecondary: () => void })`. The title is always "This PAN already exists". Dismissing it (X, outside click, Escape) calls `onSecondary`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/import/PanConflictDialog.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PanConflictDialog } from "./PanConflictDialog";

describe("PanConflictDialog", () => {
  it("shows the title, message and both actions", () => {
    const onChangeFile = vi.fn();
    const onSecondary = vi.fn();
    render(
      <PanConflictDialog
        isOpen
        message="Please choose Mom's own CAS."
        secondaryLabel="Skip Mom for now"
        onChangeFile={onChangeFile}
        onSecondary={onSecondary}
      />,
    );

    expect(screen.getByText("This PAN already exists")).toBeInTheDocument();
    expect(screen.getByText("Please choose Mom's own CAS.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /change cas file/i }));
    expect(onChangeFile).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /skip mom for now/i }));
    expect(onSecondary).toHaveBeenCalledTimes(1);
  });

  it("renders nothing when closed", () => {
    render(
      <PanConflictDialog isOpen={false} message="m" secondaryLabel="Cancel" onChangeFile={vi.fn()} onSecondary={vi.fn()} />,
    );
    expect(screen.queryByText("This PAN already exists")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/features/import/PanConflictDialog.test.tsx`
Expected: FAIL. The module is not found.

- [ ] **Step 3: Implement**

Create `frontend/src/features/import/PanConflictDialog.tsx`:

```tsx
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export interface PanConflictDialogProps {
  isOpen: boolean;
  message: string;
  secondaryLabel: string;
  onChangeFile: () => void;
  onSecondary: () => void;
}

// Upload-time PAN conflict (see pan_claims.py). Shown right after a file is
// parsed, never on Confirm Import. Copy must never identify another account.
export function PanConflictDialog({
  isOpen,
  message,
  secondaryLabel,
  onChangeFile,
  onSecondary,
}: PanConflictDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onSecondary()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>This PAN already exists</DialogTitle>
          <DialogDescription>{message}</DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <button
            type="button"
            onClick={onSecondary}
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 text-sm font-semibold text-[var(--color-ink)]"
          >
            {secondaryLabel}
          </button>
          <button
            type="button"
            onClick={onChangeFile}
            className="rounded-xl bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white"
          >
            Change CAS file
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Run the test**

Run: `npx vitest run src/features/import/PanConflictDialog.test.tsx`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Leave the changes uncommitted.

---

## Task 8: `ImportFlow` (Just Me onboarding + dashboard add-data)

**Files:**
- Modify: `frontend/src/features/import/ImportFlow.tsx`
- Test: `frontend/src/features/import/ImportFlow.test.tsx`

**Interfaces:**
- Consumes: `parseImport(file, password, memberId)`, `confirmImport(sessionId, memberId, confirmations)`, `discardImportSession` (Task 6); `getPanConflict` (Task 6); `PanConflictDialog` (Task 7); existing `CrossAccountBlockedDialog`.
- Produces: no prop changes (`ImportFlowProps` is unchanged).

- [ ] **Step 1: Update and add tests**

In `frontend/src/features/import/ImportFlow.test.tsx`:
- Change the `vi.mock("./api", ...)` factory's return to `{ ...actual, parseImport: vi.fn(), confirmImport: vi.fn(), discardImportSession: vi.fn() }`.
- Delete the tests `"switches to the matched member after a member-mismatch confirmation"`, `"continues with the selected member despite a different matched member"` and `"only offers continue when no matched member is available"`.
- Replace the test `"shows the cross-account-blocked popup and routes Back through onGoToHousehold"` with:

```tsx
  it("shows the cross-account-blocked popup right after upload and routes Back through onGoToHousehold", async () => {
    vi.mocked(api.parseImport).mockRejectedValue(
      new ApiError(409, {
        code: "cross_account_pan_blocked",
        message: "This PAN is already tracked under a different Unifolio account. Contact support if you believe this is a mistake.",
      }),
    );
    const handleGoToHousehold = vi.fn();

    render(<ImportFlow householdMemberId="member-1" onGoToHousehold={handleGoToHousehold} />);
    uploadAFile();

    await waitFor(() =>
      expect(screen.getByText(/already tracked under a different unifolio account/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/review cas import/i)).not.toBeInTheDocument();
    expect(api.confirmImport).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /^back$/i }));
    expect(handleGoToHousehold).toHaveBeenCalledTimes(1);
  });
```

- Append:

```tsx
  it("passes the household member id to parse", async () => {
    vi.mocked(api.parseImport).mockResolvedValue(EMPTY_PREVIEW);
    render(<ImportFlow householdMemberId="member-1" />);
    uploadAFile();
    await waitFor(() => screen.getByText(/review cas import/i));
    expect(api.parseImport).toHaveBeenCalledWith(expect.any(File), "secret", "member-1");
  });

  it("goes straight from Confirm Import to the confirmed screen with no prompt", async () => {
    // Regression: a fresh account used to get "couldn't match... Continue anyway".
    vi.mocked(api.parseImport).mockResolvedValue(EMPTY_PREVIEW);
    vi.mocked(api.confirmImport).mockResolvedValue({ added: 3, skipped: 0, import_id: "imp1", warnings: [] });

    render(<ImportFlow householdMemberId="member-1" />);
    uploadAFile();
    await waitFor(() => screen.getByRole("button", { name: /confirm import/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));

    await waitFor(() => expect(screen.getByText(/import complete/i)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /continue anyway/i })).not.toBeInTheDocument();
  });

  it.each(["pan_belongs_to_other_member", "pan_mismatch_for_member"])(
    "shows the PAN-already-exists popup on a %s upload and Change CAS file returns to upload",
    async (code) => {
      vi.mocked(api.parseImport).mockRejectedValueOnce(
        new ApiError(409, { code, message: "Please choose Self's own CAS." }),
      );

      render(<ImportFlow householdMemberId="member-1" />);
      uploadAFile();

      await waitFor(() => expect(screen.getByText("This PAN already exists")).toBeInTheDocument());
      fireEvent.click(screen.getByRole("button", { name: /change cas file/i }));

      await waitFor(() => expect(screen.queryByText("This PAN already exists")).not.toBeInTheDocument());
      expect(screen.getByLabelText(/cas pdf/i)).toBeInTheDocument();
      expect(api.confirmImport).not.toHaveBeenCalled();
    },
  );

  it("discards the parsed session when resetting after a failed confirm", async () => {
    vi.mocked(api.parseImport).mockResolvedValue(EMPTY_PREVIEW);
    vi.mocked(api.confirmImport).mockRejectedValue(new TypeError("Failed to fetch"));

    render(<ImportFlow householdMemberId="member-1" />);
    uploadAFile();
    await waitFor(() => screen.getByRole("button", { name: /confirm import/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));
    await waitFor(() => screen.getByRole("button", { name: /try again/i }));
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    expect(api.discardImportSession).toHaveBeenCalledWith("s1");
  });
```


- [ ] **Step 2: Run to verify failures**

Run: `npx vitest run src/features/import/ImportFlow.test.tsx`
Expected: the new and replaced tests FAIL.

- [ ] **Step 3: Implement**

In `frontend/src/features/import/ImportFlow.tsx`:

1. Imports: change `import { ApiError, confirmImport, parseImport } from "./api";` to `import { ApiError, confirmImport, discardImportSession, parseImport } from "./api";`. Add `import { PanConflictDialog } from "./PanConflictDialog";` and `import { getPanConflict } from "./panConflict";`. Remove `MemberMismatchErrorPayload` from the type import. Delete the `MemberMismatchConfirmation` type.

2. State: delete `memberMismatch`. Add:

```tsx
  const [panConflict, setPanConflict] = useState<string | null>(null);
  // After a PAN conflict, re-mount the upload container straight on the
  // upload form instead of the request/upload choice screen.
  const [uploadTab, setUploadTab] = useState(defaultTab);
```

3. Replace `reset`, `handleUpload`, `submitConfirmation` and `handleConfirm` with:

```tsx
  const reset = () => {
    if (preview) void discardImportSession(preview.session_id);
    clearCasResumeStep2(householdMemberId);
    setStep("upload");
    setPreview(null);
    setConfirmResult(null);
    setError(null);
    setReviewNotice(null);
    setConfirming(false);
  };

  const handleUpload = async (file: File, password: string) => {
    clearCasResumeStep2(householdMemberId);
    setStep("parsing");
    setError(null);
    try {
      const result = await parseImport(file, password, householdMemberId);
      setPreview(result);
      setStep("review");
    } catch (err) {
      const conflict = getPanConflict(err);
      if (conflict) {
        // Nothing was stored server-side; go back to the upload form under the popup.
        setUploadTab("upload");
        setStep("upload");
        if (conflict.code === "cross_account_pan_blocked") {
          setCrossAccountBlocked(conflict.message);
        } else {
          setPanConflict(conflict.message);
        }
        return;
      }
      setError(toParseErrorPayload(err));
      setStep("error");
    }
  };

  // Confirm never prompts: the member and PAN were settled at upload. The only
  // recoverable failures left are a scheme needing an AMFI code (409) and an
  // expired session (404).
  const handleConfirm = async (confirmations: SchemeConfirmation[]) => {
    if (!preview) return;
    setConfirming(true);
    setReviewNotice(null);
    try {
      const result = await confirmImport(preview.session_id, householdMemberId, confirmations);
      clearCasResumeStep2(householdMemberId);
      setConfirmResult(result);
      setStep("confirmed");
    } catch (err) {
      if (err instanceof ApiError && (err.status === 409 || err.status === 404)) {
        setReviewNotice(
          err.status === 404
            ? "This import session has expired. Please re-upload your CAS."
            : toParseErrorPayload(err).message,
        );
      } else {
        setError(toParseErrorPayload(err));
        setStep("error");
      }
    } finally {
      setConfirming(false);
    }
  };
```

4. JSX: directly after the existing `<CrossAccountBlockedDialog ... />`, add:

```tsx
      <PanConflictDialog
        isOpen={panConflict !== null}
        message={panConflict ?? ""}
        secondaryLabel="Cancel"
        onChangeFile={() => setPanConflict(null)}
        onSecondary={() => setPanConflict(null)}
      />
```

(Both actions close the popup onto the upload form. "Change CAS file" is the primary action; "Cancel" exists so the popup has an obvious non-action. Neither calls `onDone`, which in onboarding would complete onboarding.)

5. In the `step === "upload"` block, change `defaultTab={defaultTab}` on `<TwoPathImportContainer>` to `defaultTab={uploadTab}`.

6. In the `step === "review"` block, delete the whole `{memberMismatch && ( ... )}` element.

7. Search the file for leftovers:

```bash
grep -n "memberMismatch\|MemberMismatch\|submitConfirmation\|Continue anyway\|Switch to" src/features/import/ImportFlow.tsx
```

Expected: none.

- [ ] **Step 4: Run the tests**

Run: `npx vitest run src/features/import/ImportFlow.test.tsx src/features/auth/SoloCasUpload.test.tsx src/features/dashboard`
Expected: PASS. (Skip any glob that doesn't exist.)

- [ ] **Step 5: Checkpoint.** Leave the changes uncommitted.

---

## Task 9: `FamilyImportFlow` (Family onboarding)

**Files:**
- Modify: `frontend/src/features/auth/FamilyImportFlow.tsx`
- Modify: `frontend/src/features/auth/OnboardingFlow.tsx:235` (drop the `onGoToHousehold` prop on `<FamilyImportFlow>`)
- Test: `frontend/src/features/auth/FamilyImportFlow.test.tsx`

**Interfaces:**
- Consumes: `parseImport(file, password, memberId)`, `confirmImport(sessionId, memberId, confirmations)` (Task 6); `getPanConflict` (Task 6); `PanConflictDialog` (Task 7); existing `UploadForm` (`features/import/UploadForm.tsx`, props `{ onBack?, onSubmit(file, password) }`).
- Produces: `FamilyImportFlowProps` is now `{ selfName: string }` (`onGoToHousehold` removed).

- [ ] **Step 1: Update and add tests**

In `frontend/src/features/auth/FamilyImportFlow.test.tsx`:
- Change `renderFlow(onGoToHousehold?: () => void)` to `renderFlow()`, and render `<FamilyImportFlow selfName="Ayush" />`.
- Add, below `renderFlow`:

```tsx
async function reachParsingWithMomAndDadQueued() {
  renderFlow();
  await waitFor(() => screen.getByText("Mom"));
  uploadFor(/upload cas for mom/i);
  await waitFor(() => screen.getAllByText(/uploaded/i));
  uploadFor(/upload cas for dad/i);
  await waitFor(() => expect(screen.getByRole("button", { name: /^continue$/i })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
  await waitFor(() => screen.getByText(/upload your own cas/i));
  fireEvent.click(screen.getByRole("button", { name: /upload later/i }));
  await waitFor(() => screen.getByRole("button", { name: /import now/i }));
  fireEvent.click(screen.getByRole("button", { name: /import now/i }));
}

const PAN_EXISTS = new ApiError(409, {
  code: "pan_belongs_to_other_member",
  message: "The statement you uploaded for Mom belongs to a PAN that's already in Unifolio. Please choose Mom's own CAS.",
});
```

- In `"parses queued files sequentially and shows one aggregate ImportConfirmed at the end"`, add after its last assertion:

```tsx
    expect(importApi.parseImport).toHaveBeenNthCalledWith(1, expect.any(File), "secret", "mom");
    expect(importApi.parseImport).toHaveBeenNthCalledWith(2, expect.any(File), "secret", "dad");
    expect(screen.queryByRole("button", { name: /continue anyway/i })).not.toBeInTheDocument();
```

- Replace `"shows the cross-account-blocked popup and routes Back through onGoToHousehold"` with:

```tsx
  it("shows PAN-already-exists (not a leak) for a cross-account PAN right after that member's upload", async () => {
    vi.mocked(importApi.parseImport)
      .mockRejectedValueOnce(
        new ApiError(409, {
          code: "cross_account_pan_blocked",
          message: "This PAN is already tracked under a different Unifolio account. Contact support if you believe this is a mistake.",
        }),
      )
      .mockResolvedValueOnce(EMPTY_PREVIEW);

    await reachParsingWithMomAndDadQueued();

    await waitFor(() => expect(screen.getByText("This PAN already exists")).toBeInTheDocument());
    expect(screen.getByText(/the statement you uploaded for mom belongs to a pan/i)).toBeInTheDocument();
    expect(screen.queryByText(/different unifolio account/i)).not.toBeInTheDocument();
    expect(importApi.confirmImport).not.toHaveBeenCalled();
  });

  it("Skip moves on from a PAN conflict to the next queued member", async () => {
    vi.mocked(importApi.parseImport).mockRejectedValueOnce(PAN_EXISTS).mockResolvedValueOnce(EMPTY_PREVIEW);

    await reachParsingWithMomAndDadQueued();
    await waitFor(() => screen.getByText("This PAN already exists"));
    fireEvent.click(screen.getByRole("button", { name: /skip mom for now/i }));

    await waitFor(() => expect(screen.getByText(/review dad's cas import/i)).toBeInTheDocument());
  });

  it("Change CAS file re-uploads for the same member and then confirms straight through", async () => {
    vi.mocked(importApi.parseImport)
      .mockRejectedValueOnce(PAN_EXISTS)
      .mockResolvedValueOnce(EMPTY_PREVIEW)
      .mockResolvedValueOnce(EMPTY_PREVIEW);
    vi.mocked(importApi.confirmImport)
      .mockResolvedValueOnce({ added: 2, skipped: 0, import_id: "imp-mom", warnings: [] })
      .mockResolvedValueOnce({ added: 1, skipped: 0, import_id: "imp-dad", warnings: [] });

    await reachParsingWithMomAndDadQueued();
    await waitFor(() => screen.getByText("This PAN already exists"));
    fireEvent.click(screen.getByRole("button", { name: /change cas file/i }));

    const newFile = new File(["other-pdf"], "mom-real.pdf", { type: "application/pdf" });
    await waitFor(() => screen.getByLabelText(/cas pdf/i));
    fireEvent.change(screen.getByLabelText(/cas pdf/i), { target: { files: [newFile] } });
    fireEvent.change(screen.getByLabelText(/pdf password/i), { target: { value: "moms-pw" } });
    fireEvent.click(screen.getByRole("button", { name: /upload statement/i }));

    await waitFor(() => expect(screen.getByText(/review mom's cas import/i)).toBeInTheDocument());
    expect(importApi.parseImport).toHaveBeenNthCalledWith(2, newFile, "moms-pw", "mom");
    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));
    await waitFor(() => expect(screen.getByText(/review dad's cas import/i)).toBeInTheDocument());
  });

  it("change CAS file with a wrong password lands on the per-item error screen", async () => {
    vi.mocked(importApi.parseImport)
      .mockRejectedValueOnce(PAN_EXISTS)
      .mockRejectedValueOnce(new ApiError(422, { code: "wrong_password", message: "Incorrect PDF password." }));

    await reachParsingWithMomAndDadQueued();
    await waitFor(() => screen.getByText("This PAN already exists"));
    fireEvent.click(screen.getByRole("button", { name: /change cas file/i }));
    await waitFor(() => screen.getByLabelText(/cas pdf/i));
    fireEvent.change(screen.getByLabelText(/cas pdf/i), {
      target: { files: [new File(["x"], "mom.pdf", { type: "application/pdf" })] },
    });
    fireEvent.change(screen.getByLabelText(/pdf password/i), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: /upload statement/i }));

    await waitFor(() => expect(screen.getByText(/incorrect pdf password/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /skip mom for now/i })).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run to verify failures**

Run: `npx vitest run src/features/auth/FamilyImportFlow.test.tsx`
Expected: the new and replaced tests FAIL.

- [ ] **Step 3: Implement**

In `frontend/src/features/auth/FamilyImportFlow.tsx`:

1. Imports: remove `CrossAccountBlockedDialog`. Add `import { PanConflictDialog } from "../import/PanConflictDialog";`, `import { UploadForm } from "../import/UploadForm";` and `import { getPanConflict } from "../import/panConflict";`.

2. Props: change the interface to `interface FamilyImportFlowProps { selfName: string; }` and the signature to `export function FamilyImportFlow({ selfName }: FamilyImportFlowProps)`.

3. `ProcessingState`: change `status` and add a field:

```tsx
interface ProcessingState {
  index: number;
  // "conflict": the upload hit a PAN conflict (popup). "reupload": the user
  // chose Change CAS file and is picking a new file for the same member.
  status: "parsing" | "review" | "error" | "conflict" | "reupload";
  preview: ImportPreviewResponse | null;
  error: ParseErrorPayload | null;
  conflictMessage?: string;
}
```

4. State: delete `crossAccountBlocked`.

5. Replace `startParsing` with:

```tsx
  // Strictly sequential: one parse at a time — the next item only starts after
  // the current one is confirmed or skipped (the backend's preview-session
  // store is not safe under concurrent parses). `upload` defaults to the
  // queued item; Change CAS file passes the replacement explicitly because
  // the queue state update hasn't landed yet when this runs.
  const startParsing = async (index: number, upload: FamilyUpload = queue[index]) => {
    setReviewNotice(null);
    setProcessing({ index, status: "parsing", preview: null, error: null });
    try {
      const preview = await parseImport(upload.file, upload.password, upload.memberId);
      setProcessing({ index, status: "review", preview, error: null });
    } catch (err) {
      const conflict = getPanConflict(err);
      if (conflict) {
        // Cross-account gets the same generic copy: never hint another account exists.
        const conflictMessage =
          conflict.code === "cross_account_pan_blocked"
            ? `The statement you uploaded for ${upload.memberName} belongs to a PAN that's already in Unifolio. Please choose ${upload.memberName}'s own CAS.`
            : conflict.message;
        setProcessing({ index, status: "conflict", preview: null, error: null, conflictMessage });
        return;
      }
      setProcessing({ index, status: "error", preview: null, error: toParseErrorPayload(err) });
    }
  };
```

6. Replace `handleConfirm`'s `catch` body with:

```tsx
    } catch (err) {
      // Confirm never prompts (member and PAN were settled at upload). Only a
      // scheme needing an AMFI code (409) or an expired session (404) can
      // land here; both keep the review screen with an inline notice.
      if (err instanceof ApiError && (err.status === 409 || err.status === 404)) {
        setReviewNotice(
          err.status === 404
            ? "This import session has expired. Please re-upload your CAS."
            : toParseErrorPayload(err).message,
        );
        return;
      }
      setProcessing({ ...processing, status: "error", error: toParseErrorPayload(err) });
    } finally {
```

7. Add, after `handleSkipFailedItem`:

```tsx
  const handleReplacementUpload = (file: File, password: string) => {
    if (!processing) return;
    const replacement = { ...queue[processing.index], file, password };
    setQueue((q) => q.map((u, i) => (i === processing.index ? replacement : u)));
    void startParsing(processing.index, replacement);
  };
```

8. In the `stage === "processing"` block: delete the `<CrossAccountBlockedDialog ... />` element from the review branch. Then, after `if (processing.status === "parsing") { ... }`, insert:

```tsx
    if (processing.status === "conflict") {
      return (
        <>
          <p>{`${item.memberName}'s CAS`}</p>
          <PanConflictDialog
            isOpen
            message={processing.conflictMessage ?? ""}
            secondaryLabel={`Skip ${item.memberName} for now`}
            onChangeFile={() => setProcessing({ ...processing, status: "reupload" })}
            onSecondary={handleSkipFailedItem}
          />
        </>
      );
    }
    if (processing.status === "reupload") {
      return (
        <>
          <p>{`Choose ${item.memberName}'s CAS`}</p>
          <UploadForm onSubmit={handleReplacementUpload} />
        </>
      );
    }
```

9. In `frontend/src/features/auth/OnboardingFlow.tsx`, change `<FamilyImportFlow selfName={answers.name} onGoToHousehold={backToHousehold} />` to `<FamilyImportFlow selfName={answers.name} />`. `backToHousehold` is still used by `SoloCasUpload`.

10. Check:

```bash
grep -n "crossAccountBlocked\|CrossAccountBlockedDialog\|onGoToHousehold\|member_mismatch" src/features/auth/FamilyImportFlow.tsx
```

Expected: none.

- [ ] **Step 4: Run the tests**

Run: `npx vitest run src/features/auth`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Leave the changes uncommitted.

---

## Task 10: `MobileImportView`

**Files:**
- Modify: `frontend/src/mobile/features/import/MobileImportView.tsx`
- Test: `frontend/src/mobile/features/import/MobileImportView.test.tsx`

**Interfaces:**
- Consumes: the same as Task 8.
- Produces: no prop changes.

- [ ] **Step 1: Update and add tests**

In `frontend/src/mobile/features/import/MobileImportView.test.tsx`:
- In the `vi.mock("@/features/import/api", ...)` factory, add `discardImportSession: vi.fn(),`. No separate mock of `panConflict.ts` is needed: vitest mocks by resolved file path, so its `import { ApiError } from "./api"` gets this file's mocked `ApiError` class, and `getPanConflict` reads `err.payload`, not `err.message`.
- Delete the tests `"switches to the matched member after a member-mismatch confirmation"`, `"continues with the selected member despite a different matched member"` and `"only offers continue when no matched member is available"`.
- In `"switches to Upload view and parses statement with password"`, change the assertion to `expect(importApi.parseImport).toHaveBeenCalledWith(mockFile, "ABCDE1234F", "m-1");`.
- Replace `"shows the cross-account-blocked popup and Back leaves the review screen"` with:

```tsx
  it("shows the cross-account-blocked popup right after upload, before any review", async () => {
    vi.mocked(importApi.parseImport).mockRejectedValueOnce(
      new importApi.ApiError(409, {
        code: "cross_account_pan_blocked",
        message: "This PAN is already tracked under a different Unifolio account. Contact support if you believe this is a mistake.",
      }),
    );
    render(<MobileImportView defaultMemberId="m-1" />);
    fireEvent.click(await screen.findByRole("button", { name: /already have a statement/i }));
    fireEvent.change(screen.getByLabelText(/cas pdf/i), {
      target: { files: [new File(["pdf"], "statement.pdf", { type: "application/pdf" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: /upload statement/i }));

    await waitFor(() =>
      expect(screen.getByText(/already tracked under a different unifolio account/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText("Review CAS Import")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^back$/i }));
    await waitFor(() => expect(screen.getByLabelText(/cas pdf/i)).toBeInTheDocument());
  });

  it("shows the PAN-already-exists popup on a same-account conflict and returns to upload", async () => {
    vi.mocked(importApi.parseImport).mockRejectedValueOnce(
      new importApi.ApiError(409, { code: "pan_mismatch_for_member", message: "Please choose Ayush's own CAS." }),
    );
    render(<MobileImportView defaultMemberId="m-1" />);
    fireEvent.click(await screen.findByRole("button", { name: /already have a statement/i }));
    fireEvent.change(screen.getByLabelText(/cas pdf/i), {
      target: { files: [new File(["pdf"], "statement.pdf", { type: "application/pdf" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: /upload statement/i }));

    await waitFor(() => expect(screen.getByText("This PAN already exists")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /change cas file/i }));
    await waitFor(() => expect(screen.queryByText("This PAN already exists")).not.toBeInTheDocument());
    expect(screen.getByLabelText(/cas pdf/i)).toBeInTheDocument();
  });

  it("confirms straight through and Cancel on review discards the session", async () => {
    await openEmptyReview();
    expect(screen.queryByRole("button", { name: /continue anyway/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(importApi.discardImportSession).toHaveBeenCalledWith("sess-mismatch");
  });
```


- [ ] **Step 2: Run to verify failures**

Run: `npx vitest run src/mobile/features/import/MobileImportView.test.tsx`
Expected: the new and replaced tests FAIL.

- [ ] **Step 3: Implement**

In `frontend/src/mobile/features/import/MobileImportView.tsx`:

1. Imports: `import { parseImport, confirmImport, discardImportSession, ApiError } from "@/features/import/api";`. Add `import { PanConflictDialog } from "@/features/import/PanConflictDialog";` and `import { getPanConflict } from "@/features/import/panConflict";`. Remove `MemberMismatchErrorPayload` from the type import. Delete the `MemberMismatchConfirmation` type.

2. State: delete `memberMismatch`. Add `const [panConflict, setPanConflict] = useState<string | null>(null);`.

3. `resetFlow`: add `if (preview) void discardImportSession(preview.session_id);` as its first line, and delete `setMemberMismatch(null);`.

4. Replace `handleUpload`, `submitConfirmation` and `handleConfirm` with:

```tsx
  const handleUpload = async (file: File, password: string) => {
    if (!selectedMemberId) return;
    clearCasResumeStep2(selectedMemberId);
    setStep("parsing");
    setError(null);
    try {
      const result = await parseImport(file, password, selectedMemberId);
      setPreview(result);
      setStep("review");
    } catch (err) {
      const conflict = getPanConflict(err);
      if (conflict) {
        // Nothing was stored server-side; back to the upload form under the popup.
        setStep("flow");
        setView("upload");
        if (conflict.code === "cross_account_pan_blocked") {
          setCrossAccountBlocked(conflict.message);
        } else {
          setPanConflict(conflict.message);
        }
        return;
      }
      setError(toParseErrorPayload(err));
      setStep("error");
    }
  };

  // Confirm never prompts: member and PAN were settled at upload.
  const handleConfirm = async (confirmations: SchemeConfirmation[]) => {
    if (!preview || !selectedMemberId) return;
    setConfirming(true);
    setReviewNotice(null);
    try {
      const result = await confirmImport(preview.session_id, selectedMemberId, confirmations);
      clearCasResumeStep2(selectedMemberId);
      setConfirmResult(result);
      setDismissedWarnings(new Set());
      setStep("confirmed");
    } catch (err) {
      if (err instanceof ApiError && (err.status === 409 || err.status === 404)) {
        setReviewNotice(
          err.status === 404
            ? "This import session has expired. Please re-upload your CAS."
            : toParseErrorPayload(err).message,
        );
      } else {
        setError(toParseErrorPayload(err));
        setStep("error");
      }
    } finally {
      setConfirming(false);
    }
  };
```

5. In the `step === "review"` block, delete the `<CrossAccountBlockedDialog ... />` element and the whole `{memberMismatch && ( ... )}` element.

6. In the component's final `return (` (the one rendering the view switcher, after `const activeMemberId = ...`), insert as the first children of its root `<div>`:

```tsx
      <CrossAccountBlockedDialog
        isOpen={crossAccountBlocked !== null}
        message={crossAccountBlocked ?? ""}
        onBack={() => setCrossAccountBlocked(null)}
      />
      <PanConflictDialog
        isOpen={panConflict !== null}
        message={panConflict ?? ""}
        secondaryLabel="Cancel"
        onChangeFile={() => setPanConflict(null)}
        onSecondary={() => setPanConflict(null)}
      />
```

7. Check:

```bash
grep -n "memberMismatch\|MemberMismatch\|submitConfirmation\|Continue anyway\|Switch to" src/mobile/features/import/MobileImportView.tsx
```

Expected: none.

- [ ] **Step 4: Run the tests**

Run: `npx vitest run src/mobile`
Expected: PASS.

- [ ] **Step 5: Checkpoint.** Leave the changes uncommitted.

---

## Task 11: Docs and full verification

**Files:**
- Modify: `Docs/PRDs/ADR-Technical-Stack-Decisions.md` (ADR-004 section)
- Modify: `Docs/PRDs/Database-Schema-Unifolio.md` (`household_members` table)
- Modify: `Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md` (top of the "Attribution algorithm" section)
- Modify: `session.md` (repo root)

- [ ] **Step 1: ADR-004.** Under ADR-004's existing 2026-09-18 reopening note, add:

```markdown
**Amended 2026-09-24:** attribution no longer runs at Confirm Import. The PAN is
checked and claimed for the uploading member at upload time (pending until
confirm, released on discard or after 65 minutes), and Confirm never prompts.
Storage is unchanged apart from the new `household_members.pan_pending_until`.
See `Docs/superpowers/specs/2026-09-24-pan-at-upload-attribution-design.md`.
```

- [ ] **Step 2: Schema doc.** In the `household_members` table, add a row after `pan_lookup_hash`:

```markdown
| `pan_pending_until` | timestamptz, nullable | Non-null = the PAN is a pending upload-time claim (finalized on Confirm, released on discard/expiry). NULL with a PAN = permanent. Migration 0016. |
```

(Match the table's existing column order and format.)

- [ ] **Step 3: 2026-09-18 spec.** Directly under the `## Attribution algorithm (rewrite of attribution.py)` heading, add:

```markdown
> **Superseded 2026-09-24** by `2026-09-24-pan-at-upload-attribution-design.md`:
> `attribution.py` was removed; the PAN check moved to upload time
> (`pan_claims.py`) and Confirm Import no longer prompts. The rest of this
> spec (PAN persistence, CAS file retention) still applies.
```

- [ ] **Step 4: `session.md`.** Overwrite its "Latest" section per the file's own convention: it's a current-status pointer, not a log. Say what changed (upload-time PAN claim, confirm never prompts, Family PAN-exists popup), migration 0016, that the work is uncommitted pending the user's review, and the final test counts from Step 5.

- [ ] **Step 5: Full verification (fresh runs, no trusting earlier output)**

Run from `backend/`: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp=C:/Users/Dell/AppData/Local/Temp/uf_pt`
Expected: 0 failed.

Run from `frontend/`: `npx vitest run` then `npx tsc -b --noEmit`
Expected: 0 failed; tsc clean.

Final leftover sweep, from the repo root:

```bash
grep -rn "member_mismatch\|confirmed_member_override\|confirmedMemberOverride\|MemberMismatch\|resolve_attribution\|backfill_pan_if_missing\|Continue anyway" backend/app backend/tests frontend/src
```

Expected: none.

- [ ] **Step 6: Manual check on a fresh local account** (`uvicorn app.main:app --reload` + `npm run dev`, as in `AGENTS.md`):
  1. Just Me: sign up → upload your CAS → review → Confirm Import → the next screen, with no message.
  2. Family: add Mom + Dad → queue Dad's CAS in Mom's slot and your own CAS in Dad's slot, after first importing yours as Just Me in another account or as self → Import now → the "This PAN already exists" popup appears right after that upload → Change CAS file works, and Skip works.
  3. Log in to a second account → upload the first account's CAS → the "Import blocked" popup appears right after upload.

Report each step's outcome to the user. Leave everything uncommitted.
