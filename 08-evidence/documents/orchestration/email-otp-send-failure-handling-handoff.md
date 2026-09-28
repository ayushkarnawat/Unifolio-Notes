# Handoff: email-otp-send-failure-handling

**Status:** OPEN
**Parent plan:** none — bounded bug fix found live-debugging staging (2026-09-21), not part of a written plan doc.

## Task

Right now, when Postmark rejects an email-OTP send (confirmed live on staging: a
`@unifolio.in` recipient succeeds, a cross-domain recipient like a Gmail address gets
rejected by Postmark, almost certainly its trial-account same-domain-recipient
restriction — but the account-level cause itself is out of scope here, DNS/Postmark
account approval is being handled separately), the failure is an **unhandled
exception** that:

1. Propagates uncaught through `create_otp_request` → the FastAPI route function.
2. Escapes past `CORSMiddleware`'s normal response path (Starlette's default behavior
   for exceptions reaching its outer error handler), so the resulting 500 has **no
   CORS headers**.
3. Makes the browser's `fetch()` throw `TypeError: Failed to fetch` (confirmed via
   real browser network tab: the failing request shows `net::ERR_FAILED` / "blocked by
   CORS policy", zero `access-control-allow-*` headers — while the exact same
   same-domain request returns 200 with full CORS headers present).
4. Hits `frontend/src/features/auth/validation.ts:366-368`'s catch-all `TypeError`
   branch, showing the user "Unable to connect to the server. Please check your
   internet connection." — which is false; the real cause is an upstream email
   provider rejection, and the user is never told that.

Separately, and in the same code path: because `otp.py`'s `create_otp_request`
currently commits the new `OtpRequest` row to the DB **before** attempting the email
send (`backend/app/services/auth/otp.py:104-112`), a failed send still leaves a
persisted, unverified `OtpRequest` row behind — which then throttles the user's next
attempt for 60s (`RESEND_THROTTLE_SECONDS`) even though they never received a code.
This was observed live: a throttle message ("please wait 33s") followed shortly after
by the CORS-masked failure, on the same email address.

### Required behavior after the fix

1. `PostmarkEmailProvider.send_email` (`backend/app/services/auth/email_provider.py:44-60`)
   must not let `httpx.HTTPStatusError` (or a connection-level `httpx.HTTPError`, e.g.
   timeout/connect failure) escape raw. Catch it, log the real cause server-side at
   `logger.error` (status code + response body if present — this is what will let
   whoever's watching logs actually see "recipient addresses must share the same
   domain" or whatever Postmark's real rejection reason is, next time), and raise a
   new, dedicated exception type from this module — suggest `EmailSendError` — chained
   with `from exc`. Keep this distinct from the existing `NoEmailProviderConfiguredError`
   (that one is a deploy-time misconfiguration and should keep failing loudly/unhandled
   — don't fold it into the same catch).
2. `create_otp_request` (`backend/app/services/auth/otp.py:63-115`): reorder so that for
   `channel == "email"` with a real (non-stub) delivery mode, the email send is
   attempted **before** `db.add(request)` / `db.commit()` — not after, as today. If the
   send raises, let it propagate (don't catch it here); nothing should be persisted, so
   a failed send never engages the resend throttle against the user's next attempt.
   Stub mode and the SMS channel are unaffected — same generate/build/persist order
   they have today, just skipping straight to persist since there's no real send to
   attempt first.
3. In `backend/app/api/auth.py`, catch the new `EmailSendError` at every call site that
   invokes `create_otp_request(..., channel="email")` and return a clean
   `HTTPException` instead of letting it fall through as a bare 500 — following the
   exact existing pattern already used for `OtpRequestThrottledError` → 429 at each of
   these sites. Use status `502` (upstream/dependency failure) and a user-safe message
   that doesn't leak Postmark's raw error text, e.g. `"We couldn't send that email
   right now. Please try again in a few minutes."`. The three call sites:
   - `signup_email` (`auth.py:64-81`) — note this one currently doesn't even catch
     `OtpRequestThrottledError` either; that's a pre-existing separate gap, only add the
     new `EmailSendError` catch here, don't fix the throttle gap as part of this task
     unless it's trivial to do consistently with the other two sites (use judgement,
     but don't scope-creep beyond "OTP-send-failure surfaces cleanly").
   - `request_email_otp` (`auth.py:87-93`)
   - `request_contact_change` (`auth.py:311-323`), only relevant when
     `otp_channel == "email"` — the `sms` branch never touches the email provider so
     this catch is simply inert (never triggered) for that branch, which is fine.
4. **No frontend change is needed or wanted.** Confirmed by reading
   `validation.ts:339-375`: `formatAuthErrorMessage` already returns `err.payload`
   verbatim whenever `ApiError.payload` is a non-empty string (`detail` in FastAPI's
   `HTTPException` becomes exactly that) — so a clean `502` with a `detail` string will
   surface correctly and specifically without touching this file. Do not add a new
   status-code branch there for 502; the existing `if (detail) return detail;` already
   covers it before the code ever reaches the `status >= 500` generic branch.

## Constraints

- Decimal/float rules etc. don't apply here (no money math in this path).
- Don't touch the account-level Postmark restriction itself, DNS, or CORS
  configuration — those are separate, already understood, and not this task's
  problem. This task is purely: don't let an upstream email-provider failure crash
  uncaught and masquerade as a CORS/network error.
- Don't change `NoEmailProviderConfiguredError`'s behavior (still an unhandled/loud
  failure — it's a deploy misconfiguration, not a runtime provider rejection).
- Follow existing test-first practice in this repo (`backend/tests/conftest.py` forces
  `stub` delivery mode by default in every test unless a test explicitly monkeypatches
  `email_delivery_mode`/`postmark_api_token`/`postmark_from_email` — see existing
  pattern in `backend/tests/services/auth/test_email_provider.py`).

## Approaches considered and rejected

- **Catching the exception inside `create_otp_request` and returning a sentinel/bool
  instead of raising:** rejected — every call site would need its own conditional
  branch instead of reusing the existing `try/except HTTPException` pattern already
  established for `OtpRequestThrottledError`; raising a distinct exception type keeps
  the same shape the codebase already uses.
- **Leaving the DB-commit-before-send order unchanged and instead just shortening the
  throttle window or exempting failed sends via a new column:** rejected as
  over-engineered for what's actually a simple reordering — no new schema/column
  needed, just do the send attempt first.
- **Showing the real Postmark error message to the end user:** rejected — could leak
  provider-internal detail (e.g. account-restriction wording) that isn't useful or
  appropriate for an end user to see; log it server-side instead, per point 1 above.

## Existing tests to update, not just add to

- `backend/tests/services/auth/test_email_provider.py`'s
  `test_postmark_email_provider_raises_on_error_response` (lines 71-83) currently
  asserts `pytest.raises(httpx.HTTPStatusError)` — this must change to assert the new
  `EmailSendError` (or whatever name is chosen) instead, since that error type will no
  longer escape raw.
- `backend/tests/api/test_email_otp_routes.py` and
  `backend/tests/services/auth/test_otp.py` are the right places for new
  tests covering: (a) a failed send at each of the 3 endpoint call sites returns a
  clean 502 with a safe detail message, not a raw 500; (b) `create_otp_request` does
  NOT persist an `OtpRequest` row when the send fails (verify via DB query / by
  confirming an immediate retry is not throttled).

## Open questions

None — flag back only if something in the actual code contradicts what's described
above (this doc was written from a fresh read of the current file contents, but
re-verify against your own read before implementing).
