# Handoff: remove-password-auth

**Status:** REVIEW

**Progress note (2026-08-17):** Implementation subagent hit an account
session-limit error mid-task (after completing all backend work per this
doc — migration 0008, provider swap, three-way branch, all deletions —
but before starting frontend/docs). Orchestrator resumed directly:
cleaned up 11 stale backend tests referencing removed
`password_hash`/`email_confirmed_at` (backend confirmed green: 445
passed, 2 skipped, `alembic heads` = 0008), then implemented all
remaining frontend work directly (`api.ts`, `types.ts`, `Landing.tsx`,
`EmailEntry.tsx`, `AuthEntryFlow.tsx`'s new `emailOtpFlow`-branched login
path, `LinkAccountPrompt.tsx`'s OTP-based step-up conversion, and the
corresponding test files) plus the docs updates (`decisions.md` new
entry, `PRD-02` FR-2 + version history). Frontend verified in two passes
due to this session's known WSL/vitest worker-spawn flakiness: a full
run passed 32/32 started files (110/110 tests) with 20 files hitting the
infra error before starting (unrelated to this change); a scoped rerun
of exactly the 3 files that hit that error this round
(`App.test.tsx`, `AuthEntryFlow.test.tsx`, `LinkAccountPrompt.test.tsx`)
passed cleanly, 27/27. Combined: every test that has run, across both
attempts, passed. Adversarial review pass next.
**Parent plan:** none — management decision, user-directed undo. This doc
is the full spec (brainstorming/writing-plans explicitly skipped per user
instruction).

## Task

Remove password-based authentication entirely. Revert to email+OTP for
both signup and login (Google and phone+OTP are untouched — they were
never password-based). No `password` field anywhere: frontend, backend,
or database.

This is written from a live read of the actual current code (not the
earlier exploration summary) — trust this doc's exact snippets over any
prior summary if they ever disagree.

### 1. New migration `0008` (`down_revision = "0007"`) — never edit `0006`/`0007`

Drop:
- `auth_identities.password_hash`
- `auth_identities.email_confirmed_at`
- `pending_identity_verifications.password_hash`
- `password_reset_tokens` table entirely

Leave the `email_password` Postgres enum value untouched — no `DROP
VALUE`, no `ALTER TYPE`, exactly the precedent already set for
`EMAIL_OTP` in migration `0006`'s downgrade (Postgres can't cheaply drop
an enum value; leaving it defined is harmless).

`downgrade()` must be a genuine, correct reversal: re-add all four things
above (nullable columns matching `0006`'s original `add_column` calls,
`password_reset_tokens` recreated matching `0006`'s original
`create_table`). Follow this repo's existing batch-mode/SQLite-compatible
migration style (see `0006`/`0007` for the pattern).

### 2. Enum/precedence swap — `EMAIL_OTP` reactivates, `EMAIL_PASSWORD` benches

`backend/app/models/enums.py`, `AuthIdentityProvider`: no structural
change (all four values stay defined), but going forward **email
identities use `EMAIL_OTP`, not `EMAIL_PASSWORD`** — this is the same
swap in reverse of what migration `0006` did originally. Update the
trailing comment on `EMAIL_PASSWORD` to the same "kept, unused going
forward" wording `EMAIL_OTP` currently carries, and remove that wording
from `EMAIL_OTP` since it's active again.

`backend/app/services/auth/identity.py:25-30`, `PROVIDER_PRECEDENCE`:
flip which entry carries which comment (same reasoning, precedence value
itself — email is `1` either way — doesn't need to change).

`backend/app/services/auth/schemas.py:5-10`, `PROVIDER_TO_METHOD_LABEL`:
both `EMAIL_OTP` and `EMAIL_PASSWORD` already map to `"email"` — no
functional change needed, optionally add the same "benched" comment.

Every other live use of `AuthIdentityProvider.EMAIL_PASSWORD` in
`backend/app/api/auth.py` and `backend/app/services/auth/identity.py`
(listed precisely in §3-4 below) becomes `AuthIdentityProvider.EMAIL_OTP`.

### 3. Delete entirely

- `backend/app/services/auth/password.py` (`hash_password`/`verify_password`) and `backend/tests/services/auth/test_password.py`.
- `backend/app/services/auth/password_reset.py` and `backend/tests/services/auth/test_password_reset.py` and `backend/tests/api/test_password_reset_routes.py`.
- `PasswordResetToken` model (`backend/app/models/auth.py`).
- `/auth/password/forgot` and `/auth/password/reset` routes, and their schemas (`ForgotPasswordBody`, `ForgotPasswordResponse`, `ResetPasswordBody`, `ResetPasswordResponse`) in `backend/app/services/auth/schemas.py`.
- `LoginEmailBody` schema.
- The `/auth/login/email` route (`login_email` function) — fully replaced by the extended `/auth/email-otp/verify` below, not kept alongside it.
- `AuthIdentity.email_confirmed_at` and `PendingIdentityVerification.password_hash`/`AuthIdentity.password_hash` fields on the SQLAlchemy models (`backend/app/models/auth.py`) — matching migration `0008`.
- `SignupEmailBody.password` field and its min-length validator (`schemas.py`) — `SignupEmailBody` becomes `email: str` only (still normalized).
- `create_pending_verification`'s `password_hash` parameter (`identity.py:144-168`) and every call site passing it.
- The two `new_identity.password_hash = pending.password_hash` lines and the two `if pending.provider == AuthIdentityProvider.EMAIL_PASSWORD: new_identity.email_confirmed_at = now` blocks in `complete_phone_gate_signup` and `attach_pending_identity` (`identity.py:216-257`, `:260-307`) — delete both blocks outright, no replacement logic needed (OTP verification during signup already IS the confirmation, tracked via `PendingIdentityVerification.email_verified`; no persistent "confirmed at" timestamp is needed for OTP-based identities).
- No frontend caller of `/password/forgot` or `/password/reset` exists anywhere (`api.ts` has no such functions, no page renders them) — zero frontend cleanup needed for password-reset specifically.

### 4. `signup_email` — drop the password, keep the OTP send unchanged

Current (`backend/app/api/auth.py:71-97`) already sends an email OTP via
`create_otp_request(db, body.email, channel="email")` — that call is
correct and unchanged. Only the password parts go:

```python
@router.post("/signup/email", response_model=EmailOtpRequiredResponse)
def signup_email(body: SignupEmailBody, db: DbSession = Depends(get_db)):
    existing = find_identity_by_subject(db, AuthIdentityProvider.EMAIL_OTP, body.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists — log in instead.")

    _, raw_token = create_pending_verification(
        db,
        AuthIdentityProvider.EMAIL_OTP,
        body.email,
        body.email,
        False,
        matched_user_id=None,
    )
    _, raw_otp = create_otp_request(db, body.email, channel="email")
    return EmailOtpRequiredResponse(
        email_otp_required=EmailOtpRequiredDetail(token=raw_token, prefill_email=body.email, otp=raw_otp)
    )
```

### 5. `/auth/email-otp/verify` — THREE-way branch, not two-way

This is the one place the design needs to be precise, not just "add a
login branch" — `LinkAccountPrompt.tsx`'s existing step-up re-auth flow
(an existing account's highest-precedence method is email; a Google-link
collision needs to re-verify that email before attaching) depends on a
THIRD sub-case, exactly mirroring how `/auth/otp/verify` (phone,
`auth.py:196-229`) already branches three ways. Do not collapse this to
two branches:

```python
@router.post("/email-otp/verify", response_model=OtpVerifyResponse | PhoneRequiredResponse)
def verify_email_otp(body: EmailOtpVerifyBody, db: DbSession = Depends(get_db)):
    try:
        verify_otp(db, body.email, body.otp, channel="email")
    except OtpVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if body.pending_token:
        existing = find_identity_by_subject(db, AuthIdentityProvider.EMAIL_OTP, body.email)
        if existing is not None:
            # Step-up re-auth (LinkAccountPrompt's email branch): the
            # pending_token is a link/collision token, not a fresh-signup
            # token -- attach it to the account this email already belongs to.
            try:
                user_id = attach_pending_identity(db, body.pending_token, existing.user_id)
            except PendingVerificationError as exc:
                raise HTTPException(status_code=401, detail=str(exc)) from exc
            return _session_response(user_id, AuthIdentityProvider.EMAIL_OTP, db)
        # Fresh signup: flip the pending record's verified flag, hand off
        # to the existing mandatory phone gate -- unchanged from today.
        try:
            pending = mark_pending_email_verified(db, body.pending_token, body.email)
        except PendingVerificationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return PhoneRequiredResponse(phone_required=PhoneRequiredDetail(token=body.pending_token, prefill_email=pending.email))

    # Plain login: no pending record involved at all, just an existing identity.
    existing = find_identity_by_subject(db, AuthIdentityProvider.EMAIL_OTP, body.email)
    if existing is None:
        raise HTTPException(status_code=401, detail="No account found for that email — sign up instead.")
    return _session_response(existing.user_id, AuthIdentityProvider.EMAIL_OTP, db)
```

Note this endpoint's `response_model` changes from `PhoneRequiredResponse`
to a union (`OtpVerifyResponse | PhoneRequiredResponse`) since it can now
return either shape. `EmailOtpVerifyBody.pending_token` (`schemas.py:119-127`)
must become `pending_token: str | None = None` (currently required) to
support the plain-login case.

`/auth/email-otp/request` (`auth.py:159-165`) needs **no change** — it
already sends an OTP to any email unconditionally (no existing-identity
check), which is exactly the anti-enumeration-safe behavior a login-OTP
request needs too. Reused as-is for login-initiation.

### 6. Frontend — `Landing.tsx` and `EmailEntry.tsx` lose the password field

**`Landing.tsx`**: remove `password` state, `MIN_PASSWORD_LENGTH`,
`passwordTooShort`, the password `<input>`, and the min-length check in
`handleSignupSubmit`. `onSignup` prop becomes `(email: string) => void`.

**`EmailEntry.tsx`**: remove `password` state, `MIN_PASSWORD_LENGTH`,
`passwordTooShort`, the password `<input>`. `onLogin`/`onSignup` props
become `(email: string) => void`. Note this component is currently
mounted with `context="login"` (from `AuthEntryFlow.tsx`) and
`context="link"` (from `LinkAccountPrompt.tsx`) — both already collapse
to the same `isLoginOnly` UI branch today, so removing the password
field affects both identically; no context-specific split needed. Check
whether `context="primary"` (the dual signup/login legacy branch) has
any live caller left before deciding whether to keep or simplify that
branch — don't remove it blindly if something still mounts it.

### 7. `AuthEntryFlow.tsx` — email_otp step now serves two flows

The `email_otp` step and its `OtpVerify(channel="email")` rendering
already exist and work for signup (`handleEmailSignup` →
`email_otp_required` → `email_otp` step → `handleEmailOtpSubmit` →
`phone_required` → `phone` step) — that whole chain is unchanged.

What's new: login must also reach the `email_otp` step, but its verify
call has no `pending_token` and gets a **session** back directly
(`OtpVerifyResponse`), not `phone_required`. Add a way to distinguish
which flow is active when `handleEmailOtpSubmit` runs — e.g. a new
`emailOtpFlow: "signup" | "login"` state alongside the existing
`emailOtpToken`/`emailOtpEmail` (token stays unset for the login case).

- New handler, e.g. `handleEmailLoginRequest(email: string)`: calls
  `requestEmailOtp(email)`, sets `emailOtpEmail`, clears
  `emailOtpToken`, marks the flow as `"login"`, `goToStep("email_otp")`,
  sets `devOtp` from the response.
- `handleEmailOtpSubmit` branches on the flow marker: `"signup"` →
  unchanged existing behavior (call `verifyEmailOtp(email, otp, token)`,
  expect `phone_required`, go to `"phone"`); `"login"` → call
  `verifyEmailOtp(email, otp)` (no token), expect a session response
  (`"session_token" in result`), call `login(result.session_token)`.
- Delete the old password-based `handleEmailLogin(email, password)`.
- Wire `EmailEntry`'s `onLogin` prop (in the `step === "email"` render
  branch) to `handleEmailLoginRequest` instead.
- The `email_otp` step's `onBack` should go back to `"email"` for the
  login flow, matching the existing signup flow's `onBack={() =>
  goToStep("email")}` pattern.

### 8. `LinkAccountPrompt.tsx` — email branch becomes OTP-based

Currently (`LinkAccountPrompt.tsx:72-83`) `handleEmailLogin(email,
password)` calls `loginEmail(email, password, pendingToken)` directly,
one step. Replace with a two-step flow mirroring how this same component
already handles phone (`handlePhoneEntrySubmit` → `"otp"` step →
`handlePhoneOtpSubmit`):

- `EmailEntry`'s `onLogin` (now `(email: string) => void`) calls
  `requestEmailOtp(email)`, stores the email locally, transitions to a
  new step (this component's local `Step` type is currently `"entry" |
  "otp"` where `"otp"` means phone — add a distinct `"email_otp"` value
  and its own email-identifier state, don't reuse the phone `identifier`
  state for it).
- On email-OTP submit, call `verifyEmailOtp(email, otp, pendingToken)`
  — **with** `pendingToken` this time (the link token) — which per §5's
  three-way branch resolves through the "step-up re-auth" sub-case
  (`attach_pending_identity`) and returns a session. Call `onLinked(result)`
  exactly like the phone branch already does, after the same
  `isLinkRequired`/`isPhoneRequired` unexpected-shape guard the phone
  branch uses.

### 9. `api.ts` / `types.ts`

- `signupEmail(email: string)` — drop the `password` param, body `{email}` only.
- Delete `loginEmail` entirely.
- `verifyEmailOtp(email: string, otp: string, pendingToken?: string)` —
  `pendingToken` becomes optional; body conditionally includes
  `pending_token` only when provided, mirroring `verifyOtp`'s existing
  `...(pendingToken ? { pending_token: pendingToken } : {})` pattern
  exactly. Return type becomes a union (see below), not just
  `PhoneRequiredResponse`.
- `types.ts`: add `EmailOtpVerifyResult = OtpVerifyResponse |
  PhoneRequiredResponse` (mirroring `OtpVerifyResult`'s existing shape).
  The existing `isPhoneRequired` type guard (`"phone_required" in
  result`) already works unchanged against this new union — no new
  guard needed.

## Constraints

- TDD, no exceptions (CLAUDE.md non-negotiable).
- Do not touch Google OAuth or phone+OTP login/signup — both are
  untouched by this change; verify no code path shared with them (e.g.
  `PROVIDER_PRECEDENCE`, `_session_response`) regresses.
- Do not silently auto-create an account on a failed login lookup — the
  "no account found" case in §5's plain-login branch must be a clear
  401, never a silent signup (unlike phone, which is intentionally
  single-step-passwordless by original design; email keeps signup and
  login as distinct entry points).
- This is a security-sensitive area (this session's prior task found a
  real Critical account-binding bug in adjacent code) — trace the
  ownership/binding logic carefully, don't just make it compile. In
  particular: verify `attach_pending_identity`'s existing
  `matched_user_id` mismatch guard (`identity.py:277-278`) still
  correctly protects the step-up path now that `verify_email_otp` calls
  it from a third branch.

## Approaches considered and rejected

- **Keeping `login_email`/`/auth/login/email` alongside the extended
  `/auth/email-otp/verify`** was considered and rejected — the user
  explicitly said reuse the existing OTP infra as "the actual path," not
  add a second one; a lone password-shaped route with no password left
  to check would be dead weight.
- **A two-way branch on `/auth/email-otp/verify`** (pending_token → old
  signup behavior; no pending_token → login) was the orchestrator's
  first-draft design and is explicitly wrong — traced against
  `LinkAccountPrompt.tsx`'s actual usage, it would misroute step-up
  re-auth into the phone-gate path. §5's three-way branch (mirroring
  phone's existing structure exactly) is correct; use it as written.
- **Dropping `email_confirmed_at`'s write sites but keeping the column**
  was considered and rejected — nothing would ever read a live value
  again once `password_reset.py` (its one reader) is deleted, so keeping
  a permanently-null column is pure dead weight; drop it in the same
  migration.

## Open questions

None from the design side — this is fully specified above from a live
code read. If `EmailEntry.tsx`'s `context="primary"` branch turns out to
have a live caller not found during this doc's own read, flag it in your
report rather than guessing whether to keep or simplify it.

## Docs (separate from code, but part of this task)

- `decisions.md` (repo root): append a **new** dated entry (its own
  stated convention is append-only — never edit the 2026-08-17 entry
  that introduced password auth). State plainly that this reverses that
  entry, and why: "management decision" — don't leave the password
  rationale sitting uncontradicted; link back to the entry being
  reversed.
- `Docs/PRDs/PRD-02-Signup-Onboarding.md`: update `FR-2` in place (this
  is a living doc, not append-only) to state phone+OTP, Google, and
  email+OTP are all passwordless again. Update the Changelog/version-
  history lines that reference the password decision to point at the new
  decisions.md entry instead.

## Test plan (write these first, per TDD)

- Migration `0008`: upgrade/downgrade round-trip test in
  `backend/tests/test_migrations.py`, following the existing pattern for
  `0006`/`0007`.
- `backend/tests/services/auth/test_identity.py`: update any test
  referencing `password_hash`/`email_confirmed_at`/`EMAIL_PASSWORD` as
  the active provider to use `EMAIL_OTP` instead and drop the
  password-related assertions.
- `backend/tests/api/test_auth_email_password_routes.py`: this file's
  entire premise (password-based signup/login) is gone — replace or
  delete it; salvage any assertion still meaningful under OTP-only
  (e.g. the 409-on-duplicate-signup check) into `test_email_otp_routes.py`
  rather than losing that coverage.
- `backend/tests/api/test_email_otp_routes.py`: add tests for the new
  plain-login branch (valid email+otp with no pending_token → session;
  unknown email → 401) and the step-up re-auth branch (pending_token +
  existing identity → session via attach, verify the account actually
  gets the new identity attached).
- `backend/tests/models/test_password_auth_models.py`: delete or gut to
  whatever's left non-password-specific (likely nothing — check).
- Frontend: `AuthEntryFlow.test.tsx` needs a new login-via-email-OTP
  test (email entered → OTP requested → code verified → session, no
  phone gate involved) alongside updating/removing every existing
  password-based signup/login test. `LinkAccountPrompt.test.tsx` needs
  its email-branch test rewritten from password to OTP.

Run the full backend suite after implementation and confirm zero
regressions vs. today's 481 passed/2 skipped baseline, and confirm
`alembic heads` shows `0008` as the sole head. Frontend test execution
may hit the same WSL/vitest worker-spawn environment flakiness seen
earlier this session (unrelated to code) — if so, fall back to careful
manual code-level verification and say so explicitly rather than
claiming a run that didn't actually complete.
