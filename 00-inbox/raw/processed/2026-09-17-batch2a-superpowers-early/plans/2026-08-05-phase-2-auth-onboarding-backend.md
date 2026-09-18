# Phase 2 (Backend) — Auth + Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build phone+OTP authentication (PRD-02 FR-2) and the backend data/
endpoints onboarding's questionnaire flow needs — session management,
onboarding field updates on `User`, and household-member CRUD — against the
schema Phase 0 already built. No new tables, no migration: `otp_requests`,
`sessions`, `users`, `household_members` already exist.

**Architecture:** Two services, per `TDD-Unifolio.md`'s existing ownership
table — no new service invented. Auth (`backend/app/api/auth.py`,
`backend/app/services/auth/`) owns OTP/session/user-profile logic. Dashboard
(`backend/app/api/dashboard.py`, `backend/app/services/dashboard/`) owns
household-member CRUD only (not the rest of PRD-03). A shared
`get_current_user` dependency resolves the authenticated user from a bearer
token — every write in this plan is scoped to it, never a client-supplied
`user_id`. Full rationale: `Docs/superpowers/specs/2026-08-05-phase-2-auth-onboarding-backend-design.md`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (existing models, no changes),
stdlib `hashlib`/`secrets` for OTP and session-token hashing — no new
dependency.

## Global Constraints

- OTP hashing: stdlib `hashlib.sha256`, never bcrypt/argon2 (short-lived,
  low-entropy codes — not long-lived credentials; see design spec).
- Session tokens: `secrets.token_urlsafe(32)`, SHA-256-hashed for storage,
  raw token returned to the client exactly once, never persisted.
- No IDOR: every household-member/onboarding write resolves the acting
  user from the session token via `get_current_user()` — never from a
  request body or query parameter.
- No PIN/biometric login, no full rate-limiting/lockout policy, no real SMS
  delivery — all explicitly deferred per PRD-02 and the design spec.
  `settings.otp_delivery_mode` defaults to `"stub"` (echoes the OTP back in
  the response); a real integration flips this later.
- Test sessions must use `sessionmaker(autoflush=False, ...)`, matching
  production's real `SessionLocal` config (`backend/app/db/session.py`) —
  Phase 1's final review found a real production bug hidden by a test/
  production `autoflush` mismatch; this plan builds the fix in from the
  start.
- Test-driven: every task is red→green→commit.

## File Structure

```
backend/app/
  config.py                                # MODIFY — add otp_delivery_mode
  services/auth/
    __init__.py                             # MODIFY (currently empty)
    otp.py                                    # CREATE
    session.py                                 # CREATE
    schemas.py                                  # CREATE
  services/dashboard/
    __init__.py                             # MODIFY (currently empty)
    household_members.py                     # CREATE
    schemas.py                                 # CREATE
  api/
    auth.py                                   # MODIFY — currently empty router
    dashboard.py                               # MODIFY — fix prefix, add routes

backend/tests/
  conftest.py                              # MODIFY — add shared `client` fixture
  services/auth/
    __init__.py                             # CREATE
    test_otp.py                              # CREATE
    test_session.py                           # CREATE
  services/dashboard/
    __init__.py                             # CREATE
    test_household_members.py                # CREATE
  api/
    test_auth_routes.py                     # CREATE
    test_dashboard_routes.py                  # CREATE
```

---

### Task 1: OTP request/verify service logic

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/services/auth/otp.py`
- Create: `backend/tests/services/auth/__init__.py`
- Create: `backend/tests/services/auth/test_otp.py`

**Interfaces:**
- Consumes: `app.models.auth.OtpRequest`, `app.config.settings`.
- Produces: `generate_otp() -> str`, `create_otp_request(db, phone_number: str) -> tuple[OtpRequest, str | None]`,
  `verify_otp(db, phone_number: str, otp: str) -> OtpRequest` (raises `OtpVerificationError`),
  `OtpVerificationError(Exception)`, constants `OTP_TTL_MINUTES`, `MAX_ATTEMPTS`.
  Task 3's routes import all of these.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/auth/test_otp.py
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.auth import OtpRequest
from app.services.auth.otp import MAX_ATTEMPTS, OtpVerificationError, create_otp_request, verify_otp


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[OtpRequest.__table__])
    return sessionmaker(autoflush=False, bind=engine)()


def test_create_otp_request_returns_raw_otp_in_stub_mode(monkeypatch):
    import app.services.auth.otp as otp_module

    monkeypatch.setattr(otp_module.settings, "otp_delivery_mode", "stub")
    db = _session()
    request, raw_otp = create_otp_request(db, "+919999999999")

    assert raw_otp is not None
    assert len(raw_otp) == 6
    assert raw_otp.isdigit()
    assert request.phone_number == "+919999999999"
    assert request.otp_hash != raw_otp


def test_create_otp_request_hides_otp_outside_stub_mode(monkeypatch):
    import app.services.auth.otp as otp_module

    monkeypatch.setattr(otp_module.settings, "otp_delivery_mode", "sms")
    db = _session()
    _, raw_otp = create_otp_request(db, "+919999999999")

    assert raw_otp is None


def test_verify_otp_succeeds_with_correct_code():
    db = _session()
    _, raw_otp = create_otp_request(db, "+919999999999")

    verified = verify_otp(db, "+919999999999", raw_otp)

    assert verified.verified_at is not None


def test_verify_otp_rejects_wrong_code_and_increments_attempts():
    db = _session()
    create_otp_request(db, "+919999999999")

    with pytest.raises(OtpVerificationError, match="Incorrect OTP"):
        verify_otp(db, "+919999999999", "000000")

    request = db.query(OtpRequest).filter_by(phone_number="+919999999999").one()
    assert request.attempt_count == 1


def test_verify_otp_locks_out_after_max_attempts():
    db = _session()
    create_otp_request(db, "+919999999999")

    for _ in range(MAX_ATTEMPTS):
        with pytest.raises(OtpVerificationError):
            verify_otp(db, "+919999999999", "000000")

    with pytest.raises(OtpVerificationError, match="Too many"):
        verify_otp(db, "+919999999999", "000000")


def test_verify_otp_rejects_expired_request():
    db = _session()
    request, raw_otp = create_otp_request(db, "+919999999999")
    request.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    with pytest.raises(OtpVerificationError, match="expired"):
        verify_otp(db, "+919999999999", raw_otp)


def test_verify_otp_rejects_unknown_phone_number():
    db = _session()

    with pytest.raises(OtpVerificationError, match="No pending"):
        verify_otp(db, "+910000000000", "123456")


def test_verify_otp_uses_latest_request_when_multiple_exist():
    db = _session()
    create_otp_request(db, "+919999999999")
    _, second_otp = create_otp_request(db, "+919999999999")

    verified = verify_otp(db, "+919999999999", second_otp)

    assert verified.verified_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/services/auth/test_otp.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.auth.otp'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/config.py` (add one field):
```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./unifolio_dev.db"
    test_database_url: str | None = None
    otp_delivery_mode: str = "stub"


settings = Settings()
```

`backend/tests/services/auth/__init__.py`: empty.

`backend/app/services/auth/otp.py`:
```python
"""OTP generation, hashing, and verification — phone+OTP auth per PRD-02 FR-2.

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


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def generate_otp() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


def create_otp_request(db: DbSession, phone_number: str) -> tuple[OtpRequest, str | None]:
    """Creates and persists a new OtpRequest. Returns (request, raw_otp) —
    raw_otp is only non-None in dev-stub delivery mode, for the API
    response to echo back; a real SMS-integrated mode returns None here
    and sends the code out-of-band instead."""
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


class OtpVerificationError(Exception):
    """Any OTP verification failure — no pending request, expired, wrong code, or too many attempts."""


def verify_otp(db: DbSession, phone_number: str, otp: str) -> OtpRequest:
    """Verifies otp against the latest unverified OtpRequest for
    phone_number. Raises OtpVerificationError on any failure. On success,
    marks the request verified and returns it."""
    request = (
        db.query(OtpRequest)
        .filter_by(phone_number=phone_number, verified_at=None)
        .order_by(OtpRequest.created_at.desc())
        .first()
    )
    if not request:
        raise OtpVerificationError("No pending OTP request for this phone number.")
    if request.expires_at < datetime.now(timezone.utc):
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

Run: `.venv/bin/python -m pytest tests/services/auth/test_otp.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
cd "/mnt/d/Unifolio code"
git add backend/app/config.py backend/app/services/auth/otp.py backend/tests/services/auth
git commit -m "feat(auth): OTP request/verify service logic (PRD-02 FR-2)"
```

---

### Task 2: Session creation and the current-user dependency

**Files:**
- Create: `backend/app/services/auth/session.py`
- Create: `backend/tests/services/auth/test_session.py`

**Interfaces:**
- Consumes: `app.models.auth.Session`, `app.models.user.User`, `app.db.session.get_db`.
- Produces: `create_session(db, user_id, device_info=None) -> tuple[Session, str]`,
  `refresh_session(db, session) -> Session`, `get_current_session(authorization, db) -> Session`
  (FastAPI dependency), `get_current_user(session, db) -> User` (FastAPI dependency).
  Task 3's routes and Task 4's dashboard routes both depend on `get_current_user`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/auth/test_session.py
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.auth import Session as SessionModel
from app.models.user import User
from app.services.auth.session import (
    _extract_bearer_token,
    create_session,
    get_current_session,
    get_current_user,
    refresh_session,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[User.__table__, SessionModel.__table__])
    return sessionmaker(autoflush=False, bind=engine)()


def _user(db):
    user = User(id=uuid.uuid4(), phone_number="+919999999999", created_at=datetime.now(timezone.utc))
    db.add(user)
    db.commit()
    return user


def test_create_session_hashes_the_stored_token():
    db = _session()
    user = _user(db)

    session, raw_token = create_session(db, user.id)

    assert session.session_token_hash != raw_token
    assert len(raw_token) > 20
    assert session.user_id == user.id


def test_extract_bearer_token_rejects_missing_header():
    with pytest.raises(HTTPException) as exc_info:
        _extract_bearer_token(None)
    assert exc_info.value.status_code == 401


def test_extract_bearer_token_rejects_non_bearer_scheme():
    with pytest.raises(HTTPException) as exc_info:
        _extract_bearer_token("Basic abc123")
    assert exc_info.value.status_code == 401


def test_extract_bearer_token_returns_token():
    assert _extract_bearer_token("Bearer abc123") == "abc123"


def test_get_current_session_resolves_valid_token():
    db = _session()
    user = _user(db)
    _, raw_token = create_session(db, user.id)

    resolved = get_current_session(authorization=f"Bearer {raw_token}", db=db)

    assert resolved.user_id == user.id


def test_get_current_session_rejects_unknown_token():
    db = _session()

    with pytest.raises(HTTPException) as exc_info:
        get_current_session(authorization="Bearer not-a-real-token", db=db)
    assert exc_info.value.status_code == 401


def test_get_current_session_rejects_expired_session():
    db = _session()
    user = _user(db)
    session, raw_token = create_session(db, user.id)
    session.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        get_current_session(authorization=f"Bearer {raw_token}", db=db)
    assert exc_info.value.status_code == 401


def test_refresh_session_extends_expiry():
    db = _session()
    user = _user(db)
    session, _ = create_session(db, user.id)
    original_expiry = session.expires_at

    refreshed = refresh_session(db, session)

    assert refreshed.expires_at > original_expiry


def test_get_current_user_resolves_user_from_session():
    db = _session()
    user = _user(db)
    session, _ = create_session(db, user.id)

    resolved = get_current_user(session=session, db=db)

    assert resolved.id == user.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/services/auth/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.auth.session'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/services/auth/session.py`:
```python
"""Session token creation and current-user resolution — opaque bearer
token, hashed for storage (not JWT). The `sessions` table is the source of
truth, matching Database-Schema-Unifolio.md's session_token_hash design.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.db.session import get_db
from app.models.auth import Session as SessionModel
from app.models.user import User

SESSION_TOKEN_BYTES = 32
SESSION_TTL_DAYS = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    db: DbSession, user_id: uuid.UUID, device_info: str | None = None
) -> tuple[SessionModel, str]:
    """Creates and persists a Session. Returns (session, raw_token) — the
    raw token is returned to the caller exactly once and never stored."""
    raw_token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    now = datetime.now(timezone.utc)
    session = SessionModel(
        user_id=user_id,
        session_token_hash=_hash_token(raw_token),
        created_at=now,
        expires_at=now + timedelta(days=SESSION_TTL_DAYS),
        last_active_at=now,
        device_info=device_info,
    )
    db.add(session)
    db.commit()
    return session, raw_token


def refresh_session(db: DbSession, session: SessionModel) -> SessionModel:
    now = datetime.now(timezone.utc)
    session.last_active_at = now
    session.expires_at = now + timedelta(days=SESSION_TTL_DAYS)
    db.commit()
    return session


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")
    return authorization.removeprefix("Bearer ").strip()


def get_current_session(
    authorization: str | None = Header(default=None),
    db: DbSession = Depends(get_db),
) -> SessionModel:
    token = _extract_bearer_token(authorization)
    token_hash = _hash_token(token)
    session = db.query(SessionModel).filter_by(session_token_hash=token_hash).first()
    if not session or session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return session


def get_current_user(
    session: SessionModel = Depends(get_current_session),
    db: DbSession = Depends(get_db),
) -> User:
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Session references a deleted user.")
    return user
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/services/auth/test_session.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth/session.py backend/tests/services/auth/test_session.py
git commit -m "feat(auth): session creation and current-user dependency"
```

---

### Task 3: Auth API routes

**Files:**
- Create: `backend/app/services/auth/schemas.py`
- Modify: `backend/app/api/auth.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/api/test_auth_routes.py`

**Interfaces:**
- Consumes: `create_otp_request`, `verify_otp`, `OtpVerificationError` (Task 1);
  `create_session`, `refresh_session`, `get_current_session`, `get_current_user` (Task 2).
- Produces: `POST /auth/otp/request`, `POST /auth/otp/verify`,
  `POST /auth/session/refresh`, `PATCH /auth/me`. A shared pytest `client`
  fixture in `conftest.py` (isolated in-memory DB via `StaticPool`, real
  `TestClient(app)` with `get_db` overridden) — Task 4's route tests reuse
  this fixture, not their own copy.

- [ ] **Step 1: Write the failing tests**

`backend/tests/conftest.py` (extend the existing file):
```python
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "functional_postgres" in str(item.fspath):
            item.add_marker("postgres")


@pytest.fixture()
def client():
    """A TestClient backed by an isolated in-memory DB — StaticPool so every
    request in a test shares the same connection/data, autoflush=False to
    match production's real session config (see Global Constraints)."""
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app
    from fastapi.testclient import TestClient

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(autoflush=False, bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
```

```python
# backend/tests/api/test_auth_routes.py
def test_otp_request_returns_otp_in_stub_mode(client):
    response = client.post("/auth/otp/request", json={"phone_number": "+919999999999"})

    assert response.status_code == 200
    assert response.json()["otp"] is not None
    assert len(response.json()["otp"]) == 6


def test_otp_verify_creates_user_and_session_for_new_phone(client):
    phone = "+919888888888"
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]

    response = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp})

    assert response.status_code == 200
    body = response.json()
    assert body["session_token"]
    assert body["onboarding_step"] is None
    assert body["onboarding_completed"] is False


def test_otp_verify_reuses_existing_user_for_known_phone(client):
    phone = "+919777777777"
    otp1 = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    first = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp1}).json()

    otp2 = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    second = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp2}).json()

    assert first["user_id"] == second["user_id"]


def test_otp_verify_rejects_wrong_code(client):
    phone = "+919666666666"
    client.post("/auth/otp/request", json={"phone_number": phone})

    response = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": "000000"})

    assert response.status_code == 401


def test_me_requires_auth(client):
    response = client.patch("/auth/me", json={"onboarding_step": "q1"})
    assert response.status_code == 401


def test_me_updates_onboarding_fields_with_valid_session(client):
    phone = "+919555555555"
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]

    response = client.patch(
        "/auth/me",
        json={"onboarding_step": "q2", "investor_type": "self_directed"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["onboarding_step"] == "q2"
    assert body["investor_type"] == "self_directed"


def test_session_refresh_requires_auth(client):
    response = client.post("/auth/session/refresh")
    assert response.status_code == 401


def test_session_refresh_extends_expiry_with_valid_session(client):
    phone = "+919444444444"
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]

    response = client.post("/auth/session/refresh", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert "expires_at" in response.json()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/api/test_auth_routes.py -v`
Expected: FAIL — all 401s/404s since `/auth/otp/request` etc. don't exist yet on the empty router.

- [ ] **Step 3: Write minimal implementation**

`backend/app/services/auth/schemas.py`:
```python
from __future__ import annotations

from pydantic import BaseModel

from app.models.enums import InvestorType, PrimaryGoal


class OtpRequestBody(BaseModel):
    phone_number: str


class OtpRequestResponse(BaseModel):
    message: str
    otp: str | None = None  # only populated in dev-stub delivery mode


class OtpVerifyBody(BaseModel):
    phone_number: str
    otp: str


class OtpVerifyResponse(BaseModel):
    session_token: str
    user_id: str
    onboarding_step: str | None
    onboarding_completed: bool


class SessionRefreshResponse(BaseModel):
    expires_at: str


class UpdateMeBody(BaseModel):
    onboarding_step: str | None = None
    investor_type: InvestorType | None = None
    primary_goal: PrimaryGoal | None = None


class MeResponse(BaseModel):
    user_id: str
    phone_number: str
    email: str | None
    onboarding_step: str | None
    onboarding_completed: bool
    investor_type: InvestorType | None
    primary_goal: PrimaryGoal | None
```

`backend/app/api/auth.py`:
```python
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.db.session import get_db
from app.models.auth import Session as SessionModel
from app.models.user import User
from app.services.auth.otp import OtpVerificationError, create_otp_request, verify_otp
from app.services.auth.schemas import (
    MeResponse,
    OtpRequestBody,
    OtpRequestResponse,
    OtpVerifyBody,
    OtpVerifyResponse,
    SessionRefreshResponse,
    UpdateMeBody,
)
from app.services.auth.session import create_session, get_current_session, get_current_user, refresh_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", response_model=OtpRequestResponse)
def request_otp(body: OtpRequestBody, db: DbSession = Depends(get_db)):
    _, raw_otp = create_otp_request(db, body.phone_number)
    return OtpRequestResponse(message="OTP sent.", otp=raw_otp)


@router.post("/otp/verify", response_model=OtpVerifyResponse)
def verify_otp_route(body: OtpVerifyBody, db: DbSession = Depends(get_db)):
    try:
        verify_otp(db, body.phone_number, body.otp)
    except OtpVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = db.query(User).filter_by(phone_number=body.phone_number).first()
    if not user:
        user = User(phone_number=body.phone_number, created_at=datetime.now(timezone.utc))
        db.add(user)
        db.flush()
        db.commit()

    _, raw_token = create_session(db, user.id)

    return OtpVerifyResponse(
        session_token=raw_token,
        user_id=str(user.id),
        onboarding_step=user.onboarding_step,
        onboarding_completed=user.onboarding_completed_at is not None,
    )


@router.post("/session/refresh", response_model=SessionRefreshResponse)
def refresh_session_route(
    session: SessionModel = Depends(get_current_session),
    db: DbSession = Depends(get_db),
):
    refreshed = refresh_session(db, session)
    return SessionRefreshResponse(expires_at=refreshed.expires_at.isoformat())


@router.patch("/me", response_model=MeResponse)
def update_me(
    body: UpdateMeBody,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    if body.onboarding_step is not None:
        user.onboarding_step = body.onboarding_step
    if body.investor_type is not None:
        user.investor_type = body.investor_type
    if body.primary_goal is not None:
        user.primary_goal = body.primary_goal
    db.commit()

    return MeResponse(
        user_id=str(user.id),
        phone_number=user.phone_number,
        email=user.email,
        onboarding_step=user.onboarding_step,
        onboarding_completed=user.onboarding_completed_at is not None,
        investor_type=user.investor_type,
        primary_goal=user.primary_goal,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/api/test_auth_routes.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth/schemas.py backend/app/api/auth.py backend/tests/conftest.py backend/tests/api/test_auth_routes.py
git commit -m "feat(auth): wire OTP/session/onboarding-field API routes"
```

---

### Task 4: Household-member service and Dashboard API routes

**Files:**
- Create: `backend/app/services/dashboard/household_members.py`
- Create: `backend/app/services/dashboard/schemas.py`
- Modify: `backend/app/api/dashboard.py`
- Create: `backend/tests/services/dashboard/__init__.py`
- Create: `backend/tests/services/dashboard/test_household_members.py`
- Create: `backend/tests/api/test_dashboard_routes.py`

**Interfaces:**
- Consumes: `app.models.user.HouseholdMember`, `app.models.enums.Relationship`,
  `get_current_user` (Task 2), the shared `client` fixture (Task 3's `conftest.py`).
- Produces: `create_household_member(db, user_id, name, relationship, relationship_other_label=None) -> HouseholdMember`,
  `list_household_members(db, user_id) -> list[HouseholdMember]`,
  `POST /household-members`, `GET /household-members`.

`backend/app/api/dashboard.py` currently has `router = APIRouter(prefix="/dashboard", ...)`
— a Phase 0 placeholder prefix that doesn't match `TDD-Unifolio.md`'s actual
API design (`/household-members`, not `/dashboard/household-members` — none
of that table's endpoints are prefixed by service name). This task corrects
it: the router's Python module name still signals ownership, but the URL
prefix is dropped in favor of per-route resource paths, matching the TDD.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/dashboard/test_household_members.py
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.enums import Relationship
from app.models.user import HouseholdMember, User
from app.services.dashboard.household_members import create_household_member, list_household_members


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[User.__table__, HouseholdMember.__table__])
    return sessionmaker(autoflush=False, bind=engine)()


def _user(db, phone="+919999999999"):
    user = User(id=uuid.uuid4(), phone_number=phone, created_at=datetime.now(timezone.utc))
    db.add(user)
    db.commit()
    return user


def test_create_household_member_scoped_to_user():
    db = _session()
    user = _user(db)

    member = create_household_member(db, user.id, "Ayush", Relationship.SELF)

    assert member.user_id == user.id
    assert member.name == "Ayush"
    assert member.relationship == Relationship.SELF


def test_create_household_member_with_other_relationship_label():
    db = _session()
    user = _user(db)

    member = create_household_member(db, user.id, "Grandpa", Relationship.OTHER, "Grandfather")

    assert member.relationship == Relationship.OTHER
    assert member.relationship_other_label == "Grandfather"


def test_list_household_members_returns_only_this_users_members():
    db = _session()
    user_a = _user(db, "+919999999999")
    user_b = _user(db, "+919888888888")
    create_household_member(db, user_a.id, "Ayush", Relationship.SELF)
    create_household_member(db, user_b.id, "Someone Else", Relationship.SELF)

    members = list_household_members(db, user_a.id)

    assert len(members) == 1
    assert members[0].name == "Ayush"
```

```python
# backend/tests/api/test_dashboard_routes.py
def _authed_headers(client, phone="+919999999999"):
    otp = client.post("/auth/otp/request", json={"phone_number": phone}).json()["otp"]
    token = client.post("/auth/otp/verify", json={"phone_number": phone, "otp": otp}).json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


def test_household_members_requires_auth(client):
    response = client.get("/household-members")
    assert response.status_code == 401


def test_create_and_list_household_member(client):
    headers = _authed_headers(client)

    create_resp = client.post(
        "/household-members", json={"name": "Ayush", "relationship": "self"}, headers=headers
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["relationship"] == "self"

    list_resp = client.get("/household-members", headers=headers)
    assert list_resp.status_code == 200
    assert [m["name"] for m in list_resp.json()] == ["Ayush"]


def test_household_members_scoped_per_user(client):
    headers_a = _authed_headers(client, "+919999999999")
    headers_b = _authed_headers(client, "+919888888888")
    client.post("/household-members", json={"name": "Ayush", "relationship": "self"}, headers=headers_a)

    response = client.get("/household-members", headers=headers_b)

    assert response.json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/services/dashboard/test_household_members.py tests/api/test_dashboard_routes.py -v`
Expected: FAIL — `ModuleNotFoundError` for the service tests; 404s for the route tests (no `/household-members` path exists on the current `/dashboard`-prefixed router).

- [ ] **Step 3: Write minimal implementation**

`backend/tests/services/dashboard/__init__.py`: empty.

`backend/app/services/dashboard/household_members.py`:
```python
"""Household member CRUD — scoped to the authenticated user. Per
TDD-Unifolio.md's ownership table, /household-members belongs to the
Dashboard service even though it's populated during onboarding (PRD-02
FR-6)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DbSession

from app.models.enums import Relationship
from app.models.user import HouseholdMember


def create_household_member(
    db: DbSession,
    user_id: uuid.UUID,
    name: str,
    relationship: Relationship,
    relationship_other_label: str | None = None,
) -> HouseholdMember:
    member = HouseholdMember(
        user_id=user_id,
        name=name,
        relationship=relationship,
        relationship_other_label=relationship_other_label,
        created_at=datetime.now(timezone.utc),
    )
    db.add(member)
    db.commit()
    return member


def list_household_members(db: DbSession, user_id: uuid.UUID) -> list[HouseholdMember]:
    return (
        db.query(HouseholdMember)
        .filter_by(user_id=user_id)
        .order_by(HouseholdMember.created_at)
        .all()
    )
```

`backend/app/services/dashboard/schemas.py`:
```python
from __future__ import annotations

from pydantic import BaseModel

from app.models.enums import Relationship


class HouseholdMemberCreate(BaseModel):
    name: str
    relationship: Relationship
    relationship_other_label: str | None = None


class HouseholdMemberResponse(BaseModel):
    id: str
    name: str
    relationship: Relationship
    relationship_other_label: str | None
```

`backend/app/api/dashboard.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.db.session import get_db
from app.models.user import User
from app.services.auth.session import get_current_user
from app.services.dashboard.household_members import create_household_member, list_household_members
from app.services.dashboard.schemas import HouseholdMemberCreate, HouseholdMemberResponse

router = APIRouter(tags=["dashboard"])


@router.post("/household-members", response_model=HouseholdMemberResponse)
def create_member(
    body: HouseholdMemberCreate,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    member = create_household_member(
        db, user.id, body.name, body.relationship, body.relationship_other_label
    )
    return HouseholdMemberResponse(
        id=str(member.id),
        name=member.name,
        relationship=member.relationship,
        relationship_other_label=member.relationship_other_label,
    )


@router.get("/household-members", response_model=list[HouseholdMemberResponse])
def list_members(user: User = Depends(get_current_user), db: DbSession = Depends(get_db)):
    members = list_household_members(db, user.id)
    return [
        HouseholdMemberResponse(
            id=str(m.id),
            name=m.name,
            relationship=m.relationship,
            relationship_other_label=m.relationship_other_label,
        )
        for m in members
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/services/dashboard tests/api/test_dashboard_routes.py -v`
Expected: PASS (5 tests)

Then run the full suite to confirm no regressions:

Run: `.venv/bin/python -m pytest -m "not postgres" -v`
Expected: PASS — every test from Phase 0/1 plus every test added in this plan.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dashboard backend/app/api/dashboard.py backend/tests/services/dashboard backend/tests/api/test_dashboard_routes.py
git commit -m "feat(dashboard): household-member CRUD scoped to the authenticated user"
```

---

## Self-Review

**Spec coverage** — design spec section by section:
- Endpoints (all six) — Tasks 1-4 build exactly these, no more, no less
  (no `GET /auth/me` was added, even though useful, since it wasn't in the
  approved design — a trivial future addition, not silently added here).
- Service ownership (Auth vs. Dashboard, no new service) — Tasks 3-4's file
  placement matches exactly.
- Security (sha256 hashing, no IDOR, minimal attempt cap) — Tasks 1-2,
  directly tested.
- Data flow (signup/login, resume, family setup via repeated
  `POST /household-members` calls) — Task 3's `test_otp_verify_reuses_existing_user_for_known_phone`
  and Task 4's tests cover the mechanics; the actual UI sequencing is
  Phase 2b's concern, not this plan's.
- Testing conventions (`autoflush=False`, `StaticPool` for route tests) —
  every task's tests follow this; Task 3's `conftest.py` fixture is the
  one place it's defined, reused by Task 4.

**Placeholder scan** — no TBD/"add later" in any task; every step has
real, complete code.

**Type/name consistency** — `OtpVerificationError`, `create_otp_request`,
`verify_otp` (Task 1) imported identically in Task 3's `api/auth.py`;
`create_session`/`get_current_session`/`get_current_user`/`refresh_session`
(Task 2) imported identically in Tasks 3-4; `Relationship` enum used the
same way in Task 4's schema and service as it already is in
`app.models.enums` (no redefinition).

## Open Items Flagged, Not Resolved Here

- **Onboarding UI (Phase 2b)** — the questionnaire screens, trust primer,
  and family-setup UI that call these endpoints are a separate plan, once
  this API is live and stable, matching the Phase 1 / Phase 1b split.
- **Real SMS delivery** — `settings.otp_delivery_mode` stays `"stub"` until
  a provider is chosen; flipping it to a real integration is a small,
  isolated follow-up (implement the "else" branch of `create_otp_request`'s
  delivery logic), not a redesign.
- **PIN/biometric return-login, full rate-limiting/lockout policy** —
  explicitly deferred per PRD-02 to a future Auth/Security PRD; this plan
  only adds the minimal per-request attempt cap the schema's
  `attempt_count` column already implied.
