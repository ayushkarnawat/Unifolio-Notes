# Handoff: email-otp-signup

**Status:** DONE

**Resolution (2026-08-17):** Implemented by a Claude general-purpose
subagent (Codex unavailable this session). Mandatory adversarial review
found 1 Critical (email-OTP-verify had no binding check between the
verified OTP's email and the pending record's own email — account-
takeover-adjacent). Fixed directly by the orchestrator (TDD: exploit
reproduced as a failing test first, then `mark_pending_email_verified`
now takes and checks `verified_email` against `pending.email`). Scoped
re-review confirmed the fix closes the exploit with no bypass (case/
whitespace normalization already correctly shared via `normalize_email`
at the Pydantic boundary on both sides of the comparison; legitimate
matched-email path traced unaffected). Full backend suite: 481 passed,
2 skipped, zero regressions (independently run by the orchestrator).
Frontend fallout from a concurrent, unrelated Landing.tsx UI change
(10+2 test failures) fixed directly; correctness confirmed via manual
code-level cross-check after live vitest re-runs were blocked by a
worsening WSL/vitest worker-spawn environment issue (unrelated to code).

**Progress note (2026-08-17):** Implemented by a Claude general-purpose
subagent (Codex unavailable this session — codex:codex-rescue agent type
not registered; user opted for Claude-only fallback). Backend fully
verified green by direct orchestrator run: 479 passed, 2 skipped, 0
failed. Frontend: a parallel, independent visual-only task (removing the
Landing.tsx tab toggle + signup-view phone button) broke 10 pre-existing/
new tests in `AuthEntryFlow.test.tsx` and 2 in `App.test.tsx` that
referenced the removed UI — fixed by the orchestrator directly (swapped
`getByRole("tab", ...)` queries for the equivalent link-button queries,
removed redundant default-mode tab clicks). Manually cross-verified the
fix against live `api.ts`/`OtpVerify.tsx`/`AuthEntryFlow.tsx` (exact
signature/copy matches) since a live frontend test re-run was blocked by
a worsening WSL/vitest worker-spawn environment failure across three
retry attempts (forks pool, threads pool, single-fork) — unrelated to
code correctness, same class of issue as this session's earlier Chrome/
native-binding problems. Adversarial review pass pending next.
**Parent plan:** none — user-directed, scoped small enough to skip brainstorming/writing-plans per explicit instruction. This doc is the full spec.

## Task

Replace the link-based email confirmation step in the email+password signup
flow with an inline email-OTP step, reusing the existing phone-OTP
infrastructure. New sequencing:

```
email + password entered -> email OTP sent -> email OTP verified
  -> (existing, unchanged) phone gate -> onboarding
```

Today, email confirmation happens via a clicked link **after** the phone
gate already completed (i.e. after the `User`/`AuthIdentity` rows already
exist) and is optional (`settings.require_email_confirmation`, default
`False`). This task moves confirmation to **before** the phone gate — no
account exists yet at that point, only a `PendingIdentityVerification` row
— and makes it **unconditional** (no more opt-out setting, no more link
mechanism running alongside it).

### 1. Migration `0007` (new, `down_revision = "0006"`)

Mirrors the shape migration `0004` had before `0006` reverted it:
- `otp_requests.email`: add nullable `String` column.
- `otp_requests.phone_number`: alter to nullable (currently `NOT NULL` —
  `0006` re-narrowed it; undo that).
- Reinstate a CHECK constraint requiring exactly one of `phone_number`/`email`
  set, matching `0004`'s `ck_otp_requests_exactly_one_identifier`
  (`alembic/versions/0004_multi_method_auth_identities.py:59-65` is the
  reference implementation to mirror, including the batch/`op.create_check_constraint`
  pattern used there for SQLite compatibility).
- Drop the `email_confirmation_tokens` table entirely (link mechanism is
  being deleted, not left as inert dead schema — no dual mechanism).
- Add a `downgrade()` that reverses both changes cleanly (recreate the
  table, drop the CHECK, re-narrow the column) — follow this repo's existing
  migration style for reversibility (see `0006`'s own `downgrade()`).

### 2. `backend/app/services/auth/otp.py` — generalize to a channel

Current shape (from live code):
```python
# generate_otp(), create_otp_request(db, phone_number), verify_otp(db, phone_number, otp)
# OTP_TTL_MINUTES = 5, MAX_ATTEMPTS = 5, RESEND_THROTTLE_SECONDS = 60
# stub mode: settings.otp_delivery_mode == "stub" -> raw OTP returned from
#   create_otp_request and echoed in the API response (OtpRequestResponse.otp)
# guard: stub mode refused against a non-SQLite database_url (otp.py:47-52)
```
Generalize `create_otp_request` and `verify_otp` to accept **either** a
`phone_number` or an `email` identifier (mirroring the historical
implementation this repo already had and deliberately kept reversible —
see `git show c79757d766039e8a0df674d311deb5577d982af0` for the exact prior
shape: a `Channel = Literal["sms", "email"]` param, writing to
`otp_requests.email` when `channel="email"`). Reuse — do not reimplement —
the hash/expiry/attempt-count/throttle logic that already exists; only the
identifier column and the delivery call (SMS stub vs.
`get_email_provider().send_email(...)`) should branch on channel. Keep the
same constants (`OTP_TTL_MINUTES`, `MAX_ATTEMPTS`, `RESEND_THROTTLE_SECONDS`)
shared across both channels — do not introduce separate email-specific
values unless a test genuinely requires it.

For the email channel's stub/dev-mode delivery, use
`get_email_provider().send_email(...)` (already exists,
`backend/app/services/auth/email_provider.py`, currently used by password
reset) with a subject like "Your Unifolio verification code" — same stub
behavior as phone (`StubEmailProvider` logs it; the raw OTP is still
returned/echoed in dev-stub mode exactly like phone's `OtpRequestResponse.otp`
pattern, so the frontend has the same dev-visible pattern for both channels).

### 3. New/changed API surface (`backend/app/api/auth.py`)

- **`signup_email`** (currently `api/auth.py:73-94`): after creating the
  `PendingIdentityVerification` exactly as today (do not change that part —
  still calls `create_pending_verification` directly with
  `email_verified=False`, still bypasses `resolve_new_verified_identity`),
  send an email OTP instead of returning `PhoneRequiredResponse` directly.
  Return a new response shape carrying the pending token + prefill email +
  (dev-stub-mode only) the raw OTP — mirror `PhoneRequiredResponse`/
  `PhoneRequiredDetail`'s shape (`services/auth/schemas.py:91-97`) rather
  than inventing an unrelated structure. Name it something like
  `EmailOtpRequiredResponse`/`EmailOtpRequiredDetail` for symmetry.
- **New endpoint** `POST /auth/email-otp/request` — resend path, mirrors
  whatever the existing phone OTP request endpoint is named/shaped (find it
  in `api/auth.py` — the phone equivalent of `/auth/otp/verify`; use the
  same naming convention, just under an `email-otp` prefix instead of
  `otp`).
- **New endpoint** `POST /auth/email-otp/verify` — verifies the OTP against
  the email channel, and on success:
  - Sets `pending.email_verified = True` on the `PendingIdentityVerification`
    row (do **not** consume/delete the pending row here — it stays alive for
    the phone gate step that follows, exactly like today's pending-token
    lifecycle where `_consume_pending_verification` only runs inside
    `complete_phone_gate_signup`/`attach_pending_identity`).
  - Returns the existing `PhoneRequiredResponse` shape so the frontend can
    reuse its current phone-step handoff unchanged.
- **`complete_phone_gate_signup`** and **`attach_pending_identity`**
  (`backend/app/services/auth/identity.py:191-231` and `:234-282`): replace
  the `if settings.require_email_confirmation: send_confirmation_email(...)
  else: new_identity.email_confirmed_at = now` branch with an unconditional
  `new_identity.email_confirmed_at = now` — by the time either of these
  functions runs, email-OTP verification has already happened for any
  `EMAIL_PASSWORD` pending, so there is nothing left to gate.
- **`login_email`** (`api/auth.py:97-129`): remove the
  `settings.require_email_confirmation and existing.email_confirmed_at is
  None` 403 branch — it's dead now (no account can exist with an
  unconfirmed email under the new flow, so this check can never fire for a
  real user, only stale data).
- **Delete**: `POST /auth/email/confirm` route (`api/auth.py:157-163`),
  `ConfirmEmailBody`/`ConfirmEmailResponse` schemas, `EmailConfirmationTokenError`,
  the whole `backend/app/services/auth/email_confirmation.py` module
  (`create_email_confirmation_token`, `send_confirmation_email`,
  `consume_email_confirmation_token`), and the `EmailConfirmationToken`
  model (`backend/app/models/auth.py:114-128` — also drop its table in the
  migration).
- **Delete** `settings.require_email_confirmation`
  (`backend/app/config.py:11`) entirely — no remaining reader after the
  above changes.
- **Do not touch**: `email_provider.py` itself (password reset still uses
  it), the `AuthIdentityProvider.EMAIL_OTP` enum value (leave it exactly as
  the unused-but-kept placeholder it already is — this task does not create
  identities with that provider value, it only reuses the OTP *mechanism*
  for the email+password provider's confirmation step), `verify_otp_route`
  (`/auth/otp/verify`, phone-specific, untouched), Google OAuth, phone-only
  login/signup, or `resolve_new_verified_identity`'s collision logic.

### 4. Frontend (`frontend/src/features/auth/`)

- **`AuthEntryFlow.tsx`**: add `"email_otp"` to the `Step` union (currently
  `"landing" | "email" | "phone" | "otp" | "link_account"`,
  `AuthEntryFlow.tsx:15`). `handleEmailSignup`
  (currently lines 81-96, calls `signupEmail` then unconditionally
  `goToStep("phone")`) changes to: call `signupEmail`, store the returned
  pending token/prefill email in new state, `goToStep("email_otp")` instead
  of `"phone"`. Add a new handler (mirroring `handlePhoneOtpSubmit`,
  lines 114-129) that calls the new `verifyEmailOtp` API function; on
  success, proceed exactly as `handlePhoneSubmit`/existing phone-gate
  plumbing already does today (store `phoneGateToken`/`phoneGatePrefillEmail`
  from the `PhoneRequiredResponse` the verify call returns, `goToStep("phone")`).
  Add a resend handler calling a new `requestEmailOtp` function.
- **New step render branch**: reuse the existing `OtpVerify` component
  (same one the `"otp"` step already uses for phone) for the `"email_otp"`
  step — same component, different copy/props (e.g. "Enter the code sent to
  your email" instead of phone's copy, and identifier shown is the email not
  the phone number). Check `OtpVerify.tsx`'s existing props before deciding
  whether a small prop (e.g. a `channel: "phone" | "email"` or just a
  `label`/`identifierType` prop) is the least invasive way to support both
  copy variants without forking the component — prefer extending its props
  over duplicating the component.
- **`api.ts`**: add `requestEmailOtp(email, pendingToken?)` and
  `verifyEmailOtp(email, otp, pendingToken)` functions, mirroring
  `requestOtp`/`verifyOtp`'s existing shapes.
- **Remove the confirm-email banner component** — find it (referenced in
  git history as covered by a test: "confirm-email banner" in commit
  `272b6df`'s message) and delete it along with any place it's rendered.
  There is no more "account exists but email unconfirmed" state for it to
  represent under the new flow (confirmation always completes before the
  account is created).

## Constraints

- TDD, no exceptions (CLAUDE.md non-negotiable): write/adjust failing tests
  first for every behavior change listed above, then implement.
- Do **not** touch `resolve_new_verified_identity`'s collision/squatting
  handling, or how `signup_email` bypasses it (direct
  `create_pending_verification` call, not routed through
  `resolve_new_verified_identity`) — that decision is explicitly out of
  scope, preserve exactly as today. The only related change in scope is
  that `pending.email_verified` now genuinely flips to `True` after OTP
  success (it's honest now — mailbox control really is proven) where today
  it's hardcoded `False` forever for `EMAIL_PASSWORD` pendings. This has one
  visible side effect worth testing explicitly: `User.email` (denormalized
  field, set via `verified_email = pending.email if pending.email_verified
  else None` in `complete_phone_gate_signup`) will now actually get
  populated for password signups, where today it never does (dead code path
  today since `email_verified` was always `False`). Confirm this against
  `backend/tests/models/test_password_auth_models.py` /
  `test_auth_email_password_routes.py` — if any existing test asserts
  `User.email is None` for a completed password signup, that assertion is
  expected to change, not a regression to work around.
- Do not touch phone-only login, Google OAuth, or account-linking beyond
  what's listed above.
- Keep the same OTP constants (TTL/attempts/throttle) shared between phone
  and email channels unless a specific test requirement forces a split.

## Approaches considered and rejected

- **Overloading the existing `/auth/otp/verify` endpoint** to also handle
  email OTPs (by making `phone_number` optional and adding an `email`
  field) was considered and rejected: that endpoint already serves three
  distinct roles keyed off `pending_token` presence
  (`api/auth.py:176-209`), and folding a fourth (email-gate verification,
  which must flip `email_verified` and NOT create a user/identity) into the
  same function would make an already-overloaded endpoint harder to reason
  about. A separate, thin `/auth/email-otp/verify` endpoint is cleaner and
  matches how phone and email are already separate concerns everywhere else
  in this codebase (separate request/verify pairs, separate frontend steps).
- **Keeping `settings.require_email_confirmation` as a toggle** (email-OTP
  when on, skip confirmation entirely when off) was considered and
  rejected per explicit user instruction: "REPLACES the link-based
  ...flow — don't keep both mechanisms," and the phone gate itself is
  already unconditional/mandatory, so an unconditional email-OTP step is
  consistent with the rest of this flow's design, not a new asymmetry.
- **Dropping `email_confirmed_at` entirely** (since it's now always set at
  the moment of stamping, never conditionally) was considered and rejected:
  the user explicitly said "same `email_confirmed_at` gate purpose, just
  reached via OTP-entry instead of link-click" — keep the column as an
  audit timestamp of when confirmation happened, just always populated now
  instead of conditionally.

## Open questions

None from the design side — this is fully specified above. If the actual
current code at any of the cited file:line locations has drifted from what's
quoted here (this spec was written from a same-session code read, so it
should be accurate, but re-verify before editing), trust the live file and
note the discrepancy in your report rather than guessing which is right.

## Test plan (write these first, per TDD)

- `backend/tests/services/auth/test_otp.py`: extend/mirror existing
  phone-channel test cases for the email channel (stub-mode OTP
  visibility, correct/incorrect code, lockout after `MAX_ATTEMPTS`,
  expiry, throttle, unknown email) — same coverage shape phone already has.
- `backend/tests/api/test_auth_email_password_routes.py`: update signup
  flow tests to expect the new email-OTP-required response instead of
  immediate `phone_required`; add a full happy-path test
  (signup -> email-otp verify -> phone-otp verify -> session), a
  wrong-email-OTP-code rejection test, and update/remove the
  confirmation-gated-login tests (dead branch now).
- Replace `backend/tests/api/test_email_confirmation_routes.py` with an
  equivalent `test_email_otp_routes.py` (or similar) covering the new
  request/verify endpoints — valid code succeeds and returns
  `phone_required`, invalid code 401s, expired/throttled cases per the
  otp.py test shape.
- `backend/tests/test_migrations.py`: add coverage for revision `0007`
  (upgrade/downgrade round-trip, CHECK constraint behavior) following
  however this file already tests `0004`/`0006`.
- Frontend: update/add a test in `AuthEntryFlow.test.tsx` covering the new
  `email_otp` step transition (signup -> email OTP step rendered -> submit
  -> phone step rendered), and remove/update any test that referenced the
  confirm-email banner.

Run the full backend (`pytest`) and frontend (`npm test` in `frontend/`)
suites after implementation. If your sandbox can't reach the shared venv or
network to run them (a known constraint for worktree-isolated dispatches in
this repo — see `references/delegation-rules.md`'s "Known environment
constraints"), stop and report BLOCKED with what you implemented; the
orchestrator will run verification directly.
