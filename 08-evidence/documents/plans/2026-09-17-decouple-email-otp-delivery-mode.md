# Decouple Email/Phone OTP Delivery Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let email OTP delivery (Postmark) and phone/SMS OTP delivery run in independent modes at the same time — email always real/live, phone/SMS staying on dev-stub *for now* (no real SMS provider is built yet — this is a "not yet," not a permanent decision; a real SMS provider gets wired in later the same way Postmark was, by adding a new provider class behind this same per-channel setting) — without one setting affecting the other, the way it does today.

**Architecture:** Today, one setting (`otp_delivery_mode`) gates *both* channels — email and phone read the exact same flag in `otp.py`. That's why setting it to `"postmark"` to test email also silently disabled the phone-channel's dev-OTP echo, and why it's not possible to leave real email delivery on permanently without doing the same to phone. This plan splits it into two independent settings (`otp_delivery_mode` for phone/SMS, a new `email_delivery_mode` for email), updates the three places in `otp.py` that read the flag to pick the right one based on the request's own channel, and updates `email_provider.py`'s `get_email_provider()` to read the new email-specific setting. **No database schema or table changes at all** — `OtpRequest`'s columns, the hashing/expiry/throttle/attempt-count logic, and the API routes are completely untouched; this is purely an application-config/settings-resolution change.

One consequence this plan also has to close off: with `EMAIL_DELIVERY_MODE=postmark` now meant to be left on *permanently* in local `.env` (not just during a one-off manual test), any test that exercises the email channel without explicitly overriding the setting would start firing real calls at Postmark on every local `pytest` run — this already happened once during manual testing earlier and produced ~86 failures plus real (rejected) outbound API calls. Task 3 closes that gap with an autouse test fixture, making it structurally impossible regardless of what's in a developer's local `.env`.

**Tech Stack:** No new dependencies — same FastAPI backend, `pydantic-settings`, `pytest`/`monkeypatch` already used throughout this codebase.

**Spec:** No standalone spec doc — small, bounded follow-up to `Docs/superpowers/plans/2026-09-17-postmark-email-otp-provider.md` (already implemented, committed `e991646`/`194d489`, verified working end-to-end). Requested directly by the user in-session (2026-09-17): keep email permanently on Postmark, keep phone/SMS on stub for now (until a real SMS provider is chosen and wired in as a separate later task), independently of each other.

## Global Constraints

- **No table/schema changes.** `OtpRequest` (columns, indexes, migrations) is not touched by this plan at all — verify this stays true through self-review.
- **Test-driven, always.** Red → green, no implementation without a failing test first (`AGENTS.md`).
- **Still don't touch:** `auth.py`'s API routes, the frontend `OtpVerify` component, or the mobile presentation layer — none of them reference delivery mode at all, and this plan doesn't change that.
- **Secrets never get committed.** The real Postmark token/from-address stay in the untracked `backend/.env` only.
- **All work happens on the `tasks` branch.**

---

## File Structure

- **Modify:** `backend/app/config.py` — one new setting: `email_delivery_mode`.
- **Modify:** `backend/app/services/auth/email_provider.py` — `get_email_provider()` reads `email_delivery_mode` instead of `otp_delivery_mode`; docstring/comment updates for accuracy.
- **Modify:** `backend/app/services/auth/otp.py` — new `_delivery_mode(channel)` helper; `create_otp_request` resolves delivery mode per-channel instead of reading one shared flag in three places.
- **Modify:** `backend/tests/services/auth/test_email_provider.py` — 3 existing tests retargeted from `otp_delivery_mode` to `email_delivery_mode` (no behavior change, just which setting they monkeypatch).
- **Modify:** `backend/tests/services/auth/test_otp.py` — 5 existing email-channel tests retargeted the same way; 2 new tests (email channel's own production guard, and a test proving the two channels are now independent — the actual point of this plan).
- **Modify:** `backend/tests/conftest.py` — one new autouse fixture forcing both delivery-mode settings to `"stub"` by default for every test, regardless of local `.env` content.
- **Modify:** `backend/.env.example` — document `EMAIL_DELIVERY_MODE`.
- **No new files, no migrations.**

---

### Task 1: `email_delivery_mode` setting + `email_provider.py` wiring

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/auth/email_provider.py`
- Test: `backend/tests/services/auth/test_email_provider.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `settings.email_delivery_mode: str` (new, default `"stub"`). `get_email_provider()`'s signature is unchanged (`() -> EmailProvider`) — only which setting it reads changes.

- [x] **Step 1: Update the 3 existing tests that will fail once `get_email_provider()` stops reading `otp_delivery_mode`**

Replace the full contents of `backend/tests/services/auth/test_email_provider.py` with (only lines 25, 33, 41 change — `otp_delivery_mode` → `email_delivery_mode`; everything else identical):

```python
import logging
from unittest.mock import patch

import httpx
import pytest

from app.services.auth.email_provider import (
    NoEmailProviderConfiguredError,
    PostmarkEmailProvider,
    StubEmailProvider,
    get_email_provider,
)


def test_stub_email_provider_does_not_raise(caplog):
    caplog.set_level(logging.INFO)
    provider = StubEmailProvider()
    provider.send_email(to="a@example.com", subject="Test", body="Hello")
    assert "a@example.com" in caplog.text


def test_get_email_provider_returns_stub_in_stub_mode(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "email_delivery_mode", "stub")
    provider = get_email_provider()
    assert isinstance(provider, StubEmailProvider)


def test_get_email_provider_raises_outside_stub_mode(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "email_delivery_mode", "sms")
    with pytest.raises(NoEmailProviderConfiguredError, match="Postmark"):
        get_email_provider()


def test_get_email_provider_returns_postmark_in_postmark_mode(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "email_delivery_mode", "postmark")
    provider = get_email_provider()
    assert isinstance(provider, PostmarkEmailProvider)


def test_postmark_email_provider_sends_expected_request(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "postmark_api_token", "test-token")
    monkeypatch.setattr(email_provider_module.settings, "postmark_from_email", "noreply@unifolio.in")

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(200, request=httpx.Request("POST", url))

    with patch.object(email_provider_module.httpx, "post", side_effect=fake_post):
        PostmarkEmailProvider().send_email(to="user@example.com", subject="Your code", body="123456")

    assert captured["url"] == "https://api.postmarkapp.com/email"
    assert captured["headers"]["X-Postmark-Server-Token"] == "test-token"
    assert captured["json"]["From"] == "noreply@unifolio.in"
    assert captured["json"]["To"] == "user@example.com"
    assert captured["json"]["Subject"] == "Your code"
    assert captured["json"]["TextBody"] == "123456"


def test_postmark_email_provider_raises_on_error_response(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "postmark_api_token", "test-token")
    monkeypatch.setattr(email_provider_module.settings, "postmark_from_email", "noreply@unifolio.in")

    def fake_post(url, headers=None, json=None, timeout=None):
        request = httpx.Request("POST", url)
        return httpx.Response(422, request=request, json={"Message": "Invalid 'From' address"})

    with patch.object(email_provider_module.httpx, "post", side_effect=fake_post):
        with pytest.raises(httpx.HTTPStatusError):
            PostmarkEmailProvider().send_email(to="user@example.com", subject="s", body="b")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/services/auth/test_email_provider.py -v`
Expected: FAIL — `AttributeError` (or similar) on `email_delivery_mode`, since `config.py` doesn't define it yet and `get_email_provider()` still reads `otp_delivery_mode`.

- [x] **Step 3: Add the new setting**

In `backend/app/config.py`, add directly under `otp_delivery_mode: str = "stub"`:

```python
    email_delivery_mode: str = "stub"
```

(Full relevant section of the file after this change:)

```python
    database_url: str = "sqlite:///./unifolio_dev.db"
    test_database_url: str | None = None
    otp_delivery_mode: str = "stub"
    email_delivery_mode: str = "stub"
    postmark_api_token: str = ""
    postmark_from_email: str = ""
    environment: str = "development"
```

- [x] **Step 4: Update `get_email_provider()` to read the new setting**

In `backend/app/services/auth/email_provider.py`, replace the full file with:

```python
"""Email-sending abstraction for email OTP — Design Spec §3.

StubEmailProvider logs instead of sending (dev default). PostmarkEmailProvider
sends real email via Postmark's transactional Email API
(https://postmarkapp.com/developer/api/email-api) once EMAIL_DELIVERY_MODE is
set to "postmark" and POSTMARK_API_TOKEN/POSTMARK_FROM_EMAIL are configured.
get_email_provider() selects between them. EMAIL_DELIVERY_MODE is independent
of OTP_DELIVERY_MODE (the phone/SMS channel's own setting) -- see otp.py's
_delivery_mode() helper.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

POSTMARK_SEND_URL = "https://api.postmarkapp.com/email"


class EmailProvider(Protocol):
    def send_email(self, to: str, subject: str, body: str) -> None: ...


class StubEmailProvider:
    """Logs instead of sending — mirrors how phone OTP behaves in stub mode
    (see otp.py's per-channel _delivery_mode() helper)."""

    def send_email(self, to: str, subject: str, body: str) -> None:
        logger.info("StubEmailProvider: would send to=%s subject=%r body=%r", to, subject, body)


class PostmarkEmailProvider:
    """Sends real email via Postmark's transactional Email API. Requires a
    confirmed Sender Signature for settings.postmark_from_email in the
    Postmark dashboard — Postmark rejects the send otherwise, at the account
    level, not something this class validates itself."""

    def send_email(self, to: str, subject: str, body: str) -> None:
        response = httpx.post(
            POSTMARK_SEND_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": settings.postmark_api_token,
            },
            json={
                "From": settings.postmark_from_email,
                "To": to,
                "Subject": subject,
                "TextBody": body,
            },
            timeout=10.0,
        )
        response.raise_for_status()


class NoEmailProviderConfiguredError(RuntimeError):
    pass


def get_email_provider() -> EmailProvider:
    if settings.email_delivery_mode == "stub":
        return StubEmailProvider()
    if settings.email_delivery_mode == "postmark":
        return PostmarkEmailProvider()
    raise NoEmailProviderConfiguredError(
        f"No real EmailProvider is configured for EMAIL_DELIVERY_MODE={settings.email_delivery_mode!r}. "
        "Set EMAIL_DELIVERY_MODE to 'postmark' (with POSTMARK_API_TOKEN and "
        "POSTMARK_FROM_EMAIL set) to send real email via Postmark, or back "
        "to 'stub' for local development."
    )
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/services/auth/test_email_provider.py -v`
Expected: PASS — all 6 tests.

- [x] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/services/auth/email_provider.py backend/tests/services/auth/test_email_provider.py
git commit -m "feat(auth): add independent email_delivery_mode setting"
```

---

### Task 2: `otp.py` per-channel delivery-mode resolution

**Files:**
- Modify: `backend/app/services/auth/otp.py`
- Test: `backend/tests/services/auth/test_otp.py`

**Interfaces:**
- Consumes: `settings.email_delivery_mode` (from Task 1), `settings.otp_delivery_mode` (existing, now implicitly phone/SMS-only).
- Produces: `_delivery_mode(channel: Channel) -> str` (new, module-private helper in `otp.py`). `create_otp_request`'s own signature/return type is unchanged.

- [x] **Step 1: Update the 5 existing email-channel tests + add 2 new tests**

In `backend/tests/services/auth/test_otp.py`, apply these changes (phone-channel tests — everything before the `# --- Email channel` comment at line 162 — are NOT touched):

Change line 168 (in `test_create_otp_request_email_channel_returns_raw_otp_in_stub_mode`):
```python
    monkeypatch.setattr(otp_module.settings, "email_delivery_mode", "stub")
```

Change lines 183-184 (in `test_create_otp_request_email_channel_hides_otp_and_dispatches_outside_stub_mode`):
```python
    monkeypatch.setattr(otp_module.settings, "email_delivery_mode", "postmark")
    monkeypatch.setattr(otp_module.settings, "database_url", "sqlite:///:memory:")
```

Change lines 207-211 (in `test_create_otp_request_email_channel_raises_when_no_real_provider_configured`), including its comment:
```python
    # "sms" isn't a real email-provider mode either (same placeholder the
    # phone-channel tests above use) -- anything other than "stub" or
    # "postmark" has no EmailProvider behind it (email_provider.py).
    monkeypatch.setattr(otp_module.settings, "email_delivery_mode", "sms")
    monkeypatch.setattr(otp_module.settings, "database_url", "sqlite:///:memory:")
```

Change line 226 (in `test_create_otp_request_email_channel_does_not_dispatch_in_stub_mode`):
```python
    monkeypatch.setattr(otp_module.settings, "email_delivery_mode", "stub")
```

Change line 285 (in `test_create_otp_request_email_channel_throttles_rapid_repeat_requests`):
```python
    monkeypatch.setattr(otp_module.settings, "email_delivery_mode", "stub")
```

Then add these 2 new tests at the end of the file:

```python
def test_create_otp_request_refuses_stub_mode_in_production_for_email_channel(monkeypatch):
    import app.services.auth.otp as otp_module

    # Mirrors test_create_otp_request_refuses_stub_mode_in_production_even_with_sqlite
    # above, but for the email channel's own (now-independent) setting.
    monkeypatch.setattr(otp_module.settings, "email_delivery_mode", "stub")
    monkeypatch.setattr(otp_module.settings, "database_url", "sqlite:///:memory:")
    monkeypatch.setattr(otp_module.settings, "environment", "production")
    db = _session()

    with pytest.raises(RuntimeError, match="not allowed in production"):
        create_otp_request(db, "person@example.com", channel="email")


def test_phone_and_email_channels_use_independent_delivery_modes(monkeypatch):
    """The actual point of this plan: OTP_DELIVERY_MODE (phone) and
    EMAIL_DELIVERY_MODE (email) must not affect each other -- e.g. email can
    be switched to a real provider while phone stays in dev-stub mode (until
    a real SMS provider is added later), and vice versa."""
    import app.services.auth.otp as otp_module

    monkeypatch.setattr(otp_module.settings, "otp_delivery_mode", "stub")
    monkeypatch.setattr(otp_module.settings, "email_delivery_mode", "postmark")
    monkeypatch.setattr(otp_module.settings, "database_url", "sqlite:///:memory:")

    sent = {}

    class FakeProvider:
        def send_email(self, to, subject, body):
            sent["to"] = to

    monkeypatch.setattr(otp_module, "get_email_provider", lambda: FakeProvider())
    db = _session()

    _, phone_raw_otp = create_otp_request(db, "+919999999999")
    _, email_raw_otp = create_otp_request(db, "person@example.com", channel="email")

    assert phone_raw_otp is not None  # phone stays in dev-echo stub mode
    assert email_raw_otp is None  # email is "live" -- no echo
    assert sent["to"] == "person@example.com"  # and actually dispatched via the real-provider path
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/services/auth/test_otp.py -v`
Expected: FAIL — the 5 retargeted tests fail (since `otp.py` still reads `otp_delivery_mode` for both channels, so `email_delivery_mode` being set has no effect yet), and the 2 new tests fail (`test_phone_and_email_channels_use_independent_delivery_modes` especially — both channels currently share one flag, so this is exactly the behavior that doesn't exist yet).

- [x] **Step 3: Implement per-channel resolution in `otp.py`**

In `backend/app/services/auth/otp.py`, replace the `create_otp_request` function (and add the new helper immediately before it) with:

```python
def _delivery_mode(channel: Channel) -> str:
    """Phone/SMS and email each have their own independent delivery-mode
    setting (OTP_DELIVERY_MODE / EMAIL_DELIVERY_MODE) so one channel can be
    switched to a real provider without affecting the other -- e.g. email
    live via Postmark while phone/SMS stays in dev-stub mode until a real
    SMS provider is chosen and wired in later (same pattern as Postmark:
    a new provider class behind this same setting, nothing here needs to
    change when that happens)."""
    return settings.email_delivery_mode if channel == "email" else settings.otp_delivery_mode


def create_otp_request(
    db: DbSession, identifier: str, channel: Channel = "sms"
) -> tuple[OtpRequest, str | None]:
    """Creates and persists a new OtpRequest for either channel. Returns
    (request, raw_otp) — raw_otp is only non-None in dev-stub delivery
    mode, for the API response to echo back; a real delivery mode returns
    None here and sends the code out-of-band instead (SMS provider for
    "sms", `get_email_provider().send_email(...)` for "email")."""
    delivery_mode = _delivery_mode(channel)
    if delivery_mode == "stub" and settings.environment == "production":
        raise RuntimeError(
            "Delivery mode 'stub' is not allowed in production for this "
            "channel — this would leak real OTPs in the API response. Set "
            "OTP_DELIVERY_MODE (phone) / EMAIL_DELIVERY_MODE (email) to a "
            "real delivery mode before deploying to production."
        )

    recent = (
        db.query(OtpRequest)
        .filter_by(verified_at=None, **_identifier_filter(channel, identifier))
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
        phone_number=identifier if channel == "sms" else None,
        email=identifier if channel == "email" else None,
        otp_hash=_hash_otp(otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
        created_at=datetime.now(timezone.utc),
    )
    db.add(request)
    db.commit()

    if channel == "email" and delivery_mode != "stub":
        get_email_provider().send_email(
            to=identifier,
            subject="Your Unifolio verification code",
            body=f"Your Unifolio verification code is {otp}. It expires in {OTP_TTL_MINUTES} minutes.",
        )

    raw_otp = otp if delivery_mode == "stub" else None
    return request, raw_otp
```

(`verify_otp` and everything else in the file is unchanged — it never reads delivery mode at all.)

- [x] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/services/auth/test_otp.py -v`
Expected: PASS — all tests (existing phone-channel ones untouched and still green, retargeted email-channel ones green, both new ones green).

- [x] **Step 5: Commit**

```bash
git add backend/app/services/auth/otp.py backend/tests/services/auth/test_otp.py
git commit -m "feat(auth): resolve OTP delivery mode independently per channel"
```

---

### Task 3: Test-isolation safeguard (`conftest.py`)

**Files:**
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: `app.config.settings` (existing).
- Produces: an autouse pytest fixture — no new importable symbols, applies automatically to every test in the suite.

**Why this task exists:** once `EMAIL_DELIVERY_MODE=postmark` is set permanently in local `.env` (Task 4), every test that touches the email channel *without* explicitly monkeypatching the setting would silently pick up `"postmark"` from that `.env` file and fire a real call at Postmark. This already happened once during manual testing (~86 failures, real rejected API calls). This fixture makes that structurally impossible from now on, regardless of `.env` content.

- [x] **Step 1: Write the failing test**

This is an autouse fixture, so the "test" for it is a small dedicated test proving the guarantee: even though the test does zero monkeypatching itself, both delivery-mode settings must read `"stub"` — this is what protects every other test from a local `.env` that has `EMAIL_DELIVERY_MODE=postmark` set permanently. Add to `backend/tests/services/auth/test_otp.py` (at the end):

```python
def test_conftest_forces_stub_delivery_modes_by_default():
    """Proves the autouse fixture in conftest.py is active: even though this
    test does zero monkeypatching itself, both delivery-mode settings must
    read "stub" -- this is what protects every other test from a local
    .env that has EMAIL_DELIVERY_MODE=postmark set permanently."""
    from app.config import settings

    assert settings.otp_delivery_mode == "stub"
    assert settings.email_delivery_mode == "stub"
```

- [x] **Step 2: Run the test now, before the fixture exists, against a simulated "polluted" setting**

This one needs a manual sanity check rather than a real red step, since we can't safely commit a real non-stub value into version control to prove the red state. Run:

Run: `cd backend && ./.venv/Scripts/python.exe -c "from app.config import settings; import os; os.environ['EMAIL_DELIVERY_MODE']='postmark'; from importlib import reload; import app.config; reload(app.config); print(app.config.settings.email_delivery_mode)"`
Expected output: `postmark` — confirming that without the fixture, an env override does leak straight into `settings` with nothing resetting it. (This is a one-off manual sanity check, not part of the committed test suite.)

- [x] **Step 3: Add the autouse fixture**

In `backend/tests/conftest.py`, add after the existing `_enforce_sqlite_foreign_keys` function and before the `db_session` fixture:

```python
@pytest.fixture(autouse=True)
def _default_stub_delivery_mode(monkeypatch):
    """Forces OTP_DELIVERY_MODE and EMAIL_DELIVERY_MODE back to "stub" before
    every test, regardless of what a developer's local backend/.env has set
    -- e.g. EMAIL_DELIVERY_MODE=postmark, left on permanently so the live
    app sends real email. Without this, any test exercising the email or
    phone channel without its own explicit monkeypatch would silently pick
    up the real value and fire a real outbound call. A test that needs a
    non-stub value still monkeypatches it explicitly in its own body --
    that call runs after this fixture and simply overrides it for that one
    test; pytest's monkeypatch teardown still restores the true original
    value once the test ends."""
    from app.config import settings

    monkeypatch.setattr(settings, "otp_delivery_mode", "stub")
    monkeypatch.setattr(settings, "email_delivery_mode", "stub")
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/services/auth/test_otp.py -v`
Expected: PASS — all tests including the new `test_conftest_forces_stub_delivery_modes_by_default`.

- [x] **Step 5: Commit**

```bash
git add backend/tests/conftest.py backend/tests/services/auth/test_otp.py
git commit -m "test(auth): autouse fixture guards every test against a live local .env delivery mode"
```

---

### Task 4: Docs + full regression + manual local `.env` update

**Files:**
- Modify: `backend/.env.example`

- [x] **Step 1: Document the new setting**

In `backend/.env.example`, change:
```
OTP_DELIVERY_MODE=stub
POSTMARK_API_TOKEN=
POSTMARK_FROM_EMAIL=
```
to:
```
OTP_DELIVERY_MODE=stub
EMAIL_DELIVERY_MODE=stub
POSTMARK_API_TOKEN=
POSTMARK_FROM_EMAIL=
```

- [x] **Step 2: Run the full backend suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all pass, 0 failures (this run happens with whatever is in the developer's real local `.env` at the time — Task 3's fixture is what makes this safe to run regardless).

- [x] **Step 3: Commit**

```bash
git add backend/.env.example
git commit -m "docs(auth): document EMAIL_DELIVERY_MODE in .env.example"
```

- [x] **Step 4: Manual step — update the real local `.env` (not committed, no commit for this step)**

In `backend/.env`, change `OTP_DELIVERY_MODE=postmark` (if it's currently set that way from the previous manual test) to the final intended state:
```
OTP_DELIVERY_MODE=stub
EMAIL_DELIVERY_MODE=postmark
POSTMARK_API_TOKEN=<the real token, unchanged>
POSTMARK_FROM_EMAIL=aditi.shanbhag@unifolio.in
```

- [x] **Step 5: Manual verification**

Restart the backend, then verify both independently in the running app:
- Email signup/login with `aditi.shanbhag@unifolio.in` → should still send a real Postmark email exactly as before.
- Phone/SMS OTP (if there's a UI path to it) → should show the "Local Dev OTP" banner again (dev-echo), proving it's unaffected by email being live.

---

## Self-Review

- **Spec coverage:** the request was "keep email permanently on Postmark, phone on stub for now (not permanently — a real SMS provider comes later), independently, cleanly." Task 1 adds the independent setting, Task 2 makes `otp.py` actually resolve it per-channel (with a dedicated test proving independence), Task 3 closes the test-contamination gap this config change would otherwise reopen, Task 4 documents it and proves the full suite is safe to run with the real `.env` in place. The design places no obstacle in front of adding a real SMS provider later: `otp_delivery_mode` is an unconstrained string (not an enum), so a future SMS provider is added exactly the way Postmark was — a new provider class plus a new recognized value for this same setting — with zero changes needed to this plan's work.
- **No table/schema changes:** confirmed — no file in this plan touches `app/models/`, `alembic/`, or any migration. `OtpRequest` is unmodified.
- **Placeholders:** none — every step has literal file content or exact commands. (Task 3's Step 2 is an explicit one-off manual sanity check, called out as such rather than a committed test, since simulating a "polluted" env safely in a committed test isn't meaningful — the real proof is Task 3's Step 1 test passing after Step 3's fixture exists.)
- **Type/name consistency:** `_delivery_mode`, `settings.email_delivery_mode`, `settings.otp_delivery_mode` are named identically everywhere used across all four tasks.
- **Scope:** single subsystem (backend OTP delivery-mode resolution), not split further.
