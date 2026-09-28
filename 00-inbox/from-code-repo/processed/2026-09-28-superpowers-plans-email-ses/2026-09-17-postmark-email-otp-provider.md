# Postmark Email-OTP Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dev-only `StubEmailProvider` with a real `PostmarkEmailProvider` so email-OTP signup/login actually delivers a code to the user's inbox via Postmark, in both the web and mobile presentation layers (they share the same backend and API contract, so nothing on either front end needs to change).

**Architecture:** The email-OTP flow (request/verify routes, OTP generation/hashing/expiry/throttle, the frontend `OtpVerify` screen) already exists end to end and already calls a single injection point, `get_email_provider()` in `backend/app/services/auth/email_provider.py`. That file already has an `EmailProvider` protocol with exactly one method, `send_email(to, subject, body)`, built for this: "a real provider is a later, separate task: one new class implementing this same protocol, plus a config value." This plan is that task: add `PostmarkEmailProvider`, and wire it in behind the existing `otp_delivery_mode` setting's already-anticipated `"postmark"` value (that value is not a nice round number — it's already hardcoded into several existing tests in `test_otp.py`, so it's not a new decision, just finishing wiring that was left half-built).

**Tech Stack:** FastAPI backend, `httpx` (already a pinned dependency, used elsewhere in this codebase for outbound HTTP — see `app/services/import_/enrich.py`) for the Postmark HTTP call. No new package.

**Spec:** No standalone spec doc — this is a small, bounded addition to an existing, already-tested extension point, brainstormed directly with the user in-session (2026-09-17): use Postmark as the real email transport, keep the existing OTP generation/hashing/expiry/throttle logic exactly as-is, only swap what sends the email.

## Global Constraints

- **Test-driven, always.** Red → green, no implementation without a failing test first (`AGENTS.md`).
- **Touch nothing outside the email-provider extension point.** `otp.py`, `auth.py` (API routes), the frontend `OtpVerify` component, and the mobile presentation layer (`frontend/src/mobile`) are explicitly out of scope — they already call the generic `EmailProvider` interface and don't need to know which real provider is behind it.
- **`otp_delivery_mode` is a single flag shared by both the phone/SMS and email channels** (pre-existing design, not introduced by this plan — see `test_create_otp_request_hides_otp_outside_stub_mode` in `test_otp.py`, which already treats any non-`"stub"` value as "hide the raw OTP," for phone too). Setting it to `"postmark"` to test real email delivery will also turn off the phone-channel's dev-OTP-echo convenience (there's still no real SMS provider). This is existing, already-tested behavior — not something this plan changes — but it matters operationally for Task 3's manual test.
- **Secrets never get committed.** The Postmark Server API Token goes in the untracked `backend/.env` only, never in `.env.example`, never in this plan, never in a commit.
- **All work happens on the `tasks` branch** — already checked out, confirmed via `git status`/`git branch`. Do not touch `feat/enhanced-ui`.

---

## File Structure

- **Modify:** `backend/app/config.py` — two new settings: `postmark_api_token`, `postmark_from_email`.
- **Modify:** `backend/app/services/auth/email_provider.py` — add `PostmarkEmailProvider`, update `get_email_provider()` to return it for `otp_delivery_mode == "postmark"`, refresh the module docstring (it currently says "do not build that class here," which stops being true after this plan).
- **Modify:** `backend/tests/services/auth/test_email_provider.py` — add tests for the new class and the new branch of `get_email_provider()`.
- **Modify:** `backend/tests/services/auth/test_otp.py` — one existing test (`test_create_otp_request_email_channel_raises_when_no_real_provider_configured`) currently uses `otp_delivery_mode="postmark"` to represent "not configured yet." Once `"postmark"` is a real, working mode, that test's premise is false, so it needs to point at a different placeholder value instead (reusing `"sms"`, the same placeholder the phone-channel tests in the same file already use for "not stub, not real either").
- **Modify:** `backend/.env.example` — document the new keys plus `OTP_DELIVERY_MODE` (currently missing from this file even though it's read by `config.py`).
- **No new files.**

---

### Task 1: `PostmarkEmailProvider` — config, class, wiring, tests

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/auth/email_provider.py`
- Test: `backend/tests/services/auth/test_email_provider.py`

**Interfaces:**
- Consumes: the existing `EmailProvider` protocol (`send_email(to: str, subject: str, body: str) -> None`) and `settings.otp_delivery_mode` (existing, `str`, already `"stub"` by default).
- Produces: `PostmarkEmailProvider` (new class, no constructor args, implements `send_email`), `settings.postmark_api_token: str`, `settings.postmark_from_email: str` (both new, default `""`). `get_email_provider()`'s existing signature (`() -> EmailProvider`) is unchanged — only its internal branching gains a case.

- [x] **Step 1: Write the failing tests**

Add to `backend/tests/services/auth/test_email_provider.py` (full new file content — the three existing tests are unchanged, these four are new):

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

    monkeypatch.setattr(email_provider_module.settings, "otp_delivery_mode", "stub")
    provider = get_email_provider()
    assert isinstance(provider, StubEmailProvider)


def test_get_email_provider_raises_outside_stub_mode(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "otp_delivery_mode", "sms")
    with pytest.raises(NoEmailProviderConfiguredError, match="Postmark"):
        get_email_provider()


def test_get_email_provider_returns_postmark_in_postmark_mode(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "otp_delivery_mode", "postmark")
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

Run: `cd backend && pytest tests/services/auth/test_email_provider.py -v`
Expected: FAIL — `ImportError: cannot import name 'PostmarkEmailProvider'` (it doesn't exist yet).

- [x] **Step 3: Add the two new config settings**

In `backend/app/config.py`, add these two lines directly under the existing `otp_delivery_mode: str = "stub"` line:

```python
    postmark_api_token: str = ""
    postmark_from_email: str = ""
```

- [x] **Step 4: Implement `PostmarkEmailProvider` and wire it into `get_email_provider()`**

Replace the full contents of `backend/app/services/auth/email_provider.py` with:

```python
"""Email-sending abstraction for email OTP — Design Spec §3.

StubEmailProvider logs instead of sending (dev default). PostmarkEmailProvider
sends real email via Postmark's transactional Email API
(https://postmarkapp.com/developer/api/email-api) once OTP_DELIVERY_MODE is
set to "postmark" and POSTMARK_API_TOKEN/POSTMARK_FROM_EMAIL are configured.
get_email_provider() selects between them.
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
    """Logs instead of sending — mirrors how phone OTP already behaves in
    stub mode (see otp.py's otp_delivery_mode='stub' gate)."""

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
    if settings.otp_delivery_mode == "stub":
        return StubEmailProvider()
    if settings.otp_delivery_mode == "postmark":
        return PostmarkEmailProvider()
    raise NoEmailProviderConfiguredError(
        f"No real EmailProvider is configured for OTP_DELIVERY_MODE={settings.otp_delivery_mode!r}. "
        "Set OTP_DELIVERY_MODE to 'postmark' (with POSTMARK_API_TOKEN and "
        "POSTMARK_FROM_EMAIL set) to send real email via Postmark, or back "
        "to 'stub' for local development."
    )
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/services/auth/test_email_provider.py -v`
Expected: PASS — all 6 tests (3 existing + 3 new... note Step 1 actually adds 3 new tests: `test_get_email_provider_returns_postmark_in_postmark_mode`, `test_postmark_email_provider_sends_expected_request`, `test_postmark_email_provider_raises_on_error_response`).

- [x] **Step 6: Run the full backend suite to find the now-outdated test**

Run: `cd backend && pytest -q`
Expected: FAIL — exactly one failure, `tests/services/auth/test_otp.py::test_create_otp_request_email_channel_raises_when_no_real_provider_configured`. This is expected and is fixed in Task 2, not here.

- [x] **Step 7: Commit**

```bash
git add backend/app/config.py backend/app/services/auth/email_provider.py backend/tests/services/auth/test_email_provider.py
git commit -m "feat(auth): add PostmarkEmailProvider for real email-OTP delivery"
```

---

### Task 2: Fix the now-outdated placeholder test + document env vars

**Files:**
- Modify: `backend/tests/services/auth/test_otp.py:204-218`
- Modify: `backend/.env.example`

**Interfaces:**
- Consumes: `PostmarkEmailProvider`, `get_email_provider()` from Task 1 (no signature changes, just now a working mode).
- Produces: nothing new — this task only keeps existing coverage honest and documents config.

- [x] **Step 1: Update the outdated test**

In `backend/tests/services/auth/test_otp.py`, replace the existing `test_create_otp_request_email_channel_raises_when_no_real_provider_configured` (currently lines 204-218) with:

```python
def test_create_otp_request_email_channel_raises_when_no_real_provider_configured(monkeypatch):
    import app.services.auth.otp as otp_module

    # "sms" isn't a real email-provider mode either (same placeholder the
    # phone-channel tests above use) -- anything other than "stub" or
    # "postmark" has no EmailProvider behind it (email_provider.py).
    monkeypatch.setattr(otp_module.settings, "otp_delivery_mode", "sms")
    monkeypatch.setattr(otp_module.settings, "database_url", "sqlite:///:memory:")
    db = _session()

    from app.services.auth.email_provider import NoEmailProviderConfiguredError

    with pytest.raises(NoEmailProviderConfiguredError):
        create_otp_request(db, "person@example.com", channel="email")
```

- [x] **Step 2: Run the full backend suite to verify it's green**

Run: `cd backend && pytest -q`
Expected: PASS — all tests, no failures.

- [x] **Step 3: Document the new env vars**

Append to `backend/.env.example` (which currently doesn't even list `OTP_DELIVERY_MODE`, even though `config.py` reads it — adding it now since it's directly relevant):

```
OTP_DELIVERY_MODE=stub
POSTMARK_API_TOKEN=
POSTMARK_FROM_EMAIL=
```

- [x] **Step 4: Commit**

```bash
git add backend/tests/services/auth/test_otp.py backend/.env.example
git commit -m "test(auth): retarget the email-provider placeholder test now that postmark mode is real"
```

---

### Task 3: Manual smoke test against the real Postmark account

Not a code task — this is the actual "does it work" check, using the Sender Signature and Server API Token already set up.

- [x] **Step 1: Set local secrets**

In `backend/.env` (untracked — create it from `.env.example` if it doesn't exist yet), set:

```
OTP_DELIVERY_MODE=postmark
POSTMARK_API_TOKEN=<the Postmark Server API Token you generated>
POSTMARK_FROM_EMAIL=aditi.shanbhag@unifolio.in
```

- [x] **Step 2: Restart the backend**

Run: `cd backend && uvicorn app.main:app --reload`

- [x] **Step 3: Trigger a real email-OTP request**

```bash
curl -X POST http://localhost:8000/auth/email-otp/request \
  -H "Content-Type: application/json" \
  -d '{"email":"aditi.shanbhag@unifolio.in"}'
```

Expected: the response no longer contains a raw `otp` field (that only happens in stub mode), and a real email from Postmark arrives at that inbox within a few seconds with a 6-digit code.

- [x] **Step 4: Verify the code**

```bash
curl -X POST http://localhost:8000/auth/email-otp/verify \
  -H "Content-Type: application/json" \
  -d '{"email":"aditi.shanbhag@unifolio.in","otp":"<code from the email>"}'
```

Expected: a successful session response (not an OTP error).

- [x] **Step 5: Revert local `.env` back to stub mode**

Set `OTP_DELIVERY_MODE=stub` again in `backend/.env`. This flag is shared with the phone/SMS channel (see Global Constraints), so leaving it on `"postmark"` would silently stop the phone-OTP dev-echo convenience for local testing until you flip it back.

No commit for this task — `.env` is untracked and this step is purely a manual verification, not a code change.

---

## Self-Review

- **Spec coverage:** the only requirement was "make Postmark the real sender for email OTP, change nothing else." Task 1 adds the provider, Task 2 keeps the existing test suite honest and documents the config, Task 3 proves it actually works end to end. No frontend, mobile, or migration changes anywhere — matches "don't change anything else."
- **Placeholders:** none — every step has literal file content or exact commands.
- **Type/name consistency:** `PostmarkEmailProvider`, `get_email_provider()`, `settings.postmark_api_token`, `settings.postmark_from_email` are named identically everywhere they're used across all three tasks.
- **Scope:** single subsystem (backend email-OTP delivery), not split further.
