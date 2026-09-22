# Email Signup: OTP → Password — Design

## Purpose

Changes the email signup/login method from email+OTP to email+password.
Google and phone+OTP are **unchanged** — this doc only covers what's different
for the email path, plus the two shared mechanics (the mandatory phone gate,
the account-linking collision check) confirmed to wire up identically.

**Why:** most users already have password-manager autofill for email
logins; email-OTP adds an inbox-checking step phone-OTP doesn't have (SMS
arrives instantly, in the same context), so password removes friction on
the one channel where it was actually adding some.

Read `2026-08-14-multi-method-auth-design.md` first — this doc assumes its
identity model (`users` as a provider-agnostic anchor, `auth_identities` as
the per-provider verification source of truth, `pending_identity_verifications`
for the mandatory-gate/step-up-linking mechanism) without re-deriving it.

## 1. Email-OTP infrastructure: remove the code path, keep the enum value

**Recommendation: remove the email channel's code path entirely; do not
leave it "just in case."** `otp.py`'s channel generalization and
`otp_requests.email` have zero remaining callers once email+password lands
— email-OTP's only consumer was the `/auth/otp/request`/`/auth/otp/verify`
email branch, and password reset (§3) needs a fundamentally different
mechanism (a single-use link, not a repeatable 6-digit code), so it can't
reuse this path anyway. Keeping dead code "for later" is exactly the
backwards-compatibility-hack pattern this project's CLAUDE.md explicitly
rules out.

Concretely:
- `otp.py`: revert to phone-only — drop the `channel` parameter, `Channel`
  type, and the `email`-branch of `create_otp_request`/`verify_otp`.
- `otp_requests` table: drop the `email` column and its
  `ck_otp_requests_exactly_one_identifier` check constraint (migration,
  §5). `phone_number` goes back to `NOT NULL`.
- `EmailProvider`/`StubEmailProvider` (the *sending* abstraction) are
  **not** touched — they're reused unchanged for password-reset delivery
  (§3). Only the OTP-specific table/logic goes.

**The `AuthIdentityProvider.EMAIL_OTP` enum value itself stays defined,
just unused going forward** — do not remove or rename it. Postgres ENUM
types can't cheaply drop a value (it requires recreating the whole type),
and this schema is still headed for a SQLite→Postgres migration per the
Migration Plan, so shrinking an enum now buys nothing and adds real risk
later. Add a new `EMAIL_PASSWORD` value alongside it instead (§5) —
enums grow, they don't shrink, matching how `GOOGLE` was added onto the
original two-value enum without touching `PHONE_OTP`/`EMAIL_OTP`.

## 2. Password storage: bcrypt

**Recommendation: bcrypt, via `passlib[bcrypt]`.** It's a single cost-factor
knob (unlike Argon2's three: memory/time/parallelism), which is one fewer
decision surface for a small team, and it's the most battle-tested,
zero-surprise choice for a standard FastAPI backend — nothing about this
app's threat model needs Argon2's extra memory-hardness over a properly-
costed bcrypt hash.

- New dependency: `passlib[bcrypt]>=1.7.4` in `backend/requirements.txt`.
- `hash_password(raw: str) -> str` / `verify_password(raw: str, hashed: str) -> bool`
  wrapping `passlib.context.CryptContext(schemes=["bcrypt"])`, in a new
  `backend/app/services/auth/password.py` — mirrors `otp.py`'s existing
  hash-then-compare shape (sha256 there, bcrypt here — different tool,
  same responsibility split).
- Minimum length: 8 characters, enforced in the request schema
  (`OtpRequestBody`-style Pydantic validator). No complexity-rule theater
  (mixed case/symbols requirements) — length is what actually matters and
  bcrypt handles the rest.

## 3. Password reset: reuses `EmailProvider`, new token table

Same shape as `pending_identity_verifications`'s token mechanism (raw
`secrets.token_urlsafe(32)`, sha256-hashed for storage, checked, never
stored raw) — not the OTP table, which is the wrong shape for a single-use
link.

**New table `password_reset_tokens`:**
| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `user_id` | `UUID` FK → `users.id` NOT NULL | |
| `token_hash` | `VARCHAR` NOT NULL | sha256 of the raw token, same pattern as `pending_identity_verifications.token_hash` |
| `expires_at` | `TIMESTAMPTZ` NOT NULL | 30 minutes — longer than the 10-minute pending-verification TTL, since this is a "check your email later" flow, not a same-session continuation |
| `used_at` | `TIMESTAMPTZ` NULLABLE | Set on successful reset; a used token is dead even if not yet expired |
| `created_at` | `TIMESTAMPTZ` NOT NULL | |

**Flow:**
- `POST /auth/password/forgot {email}` → looks up the `EMAIL_PASSWORD`
  identity by `provider_subject=email`. **Always returns 200** regardless
  of whether the email matches an account — the classic anti-enumeration
  pattern (Design Spec's own security section already applies this same
  logic to other auth surfaces). If it matches, generates a token, stores
  the hash, and calls `EmailProvider.send_email(to=email, ..., body=<link
  containing the raw token>)` — the exact same call shape `otp.py` already
  uses for email-OTP delivery, just a link instead of a code. In stub mode
  this logs instead of sending, same as today.
- `POST /auth/password/reset {token, new_password}` → hashes the token,
  looks it up, checks `used_at IS NULL` and not expired, updates the
  matching `AuthIdentity.password_hash`, sets `used_at`. Invalid/expired/
  used token → 401 with a generic "This reset link is invalid or has
  expired" (don't distinguish which, same anti-enumeration reasoning).

## 4. Login-with-email now means email+password — and needs its own endpoints, not the shared resolve-transparently pattern

**Confirmed explicitly, since this is a real asymmetry from every other
method:** phone/Google/email-OTP all use one "verify → resolve new-vs-
existing transparently" shape, because *proving you received a code* (or a
Google credential) is the same action whether you're new or returning.
Password breaks that symmetry — signup means *creating* a credential,
login means *proving knowledge of* one already created. They can't share
one endpoint the way OTP verification does.

**Two new endpoints, no auto-detection, no third "does this email exist"
endpoint** (an endpoint like that would itself be an enumeration oracle):

- `POST /auth/signup/email {email, password}` — checks
  `find_identity_by_subject(EMAIL_PASSWORD, email)` first; if found, 409
  ("An account with this email already exists — log in instead"). If not,
  hashes the password (§2) and calls `create_pending_verification` **directly**
  — not through `resolve_new_verified_identity` — with the new
  `password_hash` parameter (§4b) and `email_verified=False` (§4a). This
  is a deliberate simplification, not an oversight: `resolve_new_verified_
  identity`'s only extra value over calling `create_pending_verification`
  directly is its collision-check branch, and with `email_verified=False`
  that branch can never fire (§4a) — routing through it anyway would mean
  adding a `password_hash` parameter to a shared function whose other two
  callers (Google, and the now-removed email-OTP path) would never use it.
  The route always returns `phone_required` in response, matching the
  shape `resolve_new_verified_identity` would have returned for this case.
  The bcrypt hash lands on the real `AuthIdentity` row once the phone gate
  completes (§4b).
- `POST /auth/login/email {email, password}` — `find_identity_by_subject
  (EMAIL_PASSWORD, email)`; not found or hash mismatch → **same generic
  401** ("Invalid email or password") either way, standard practice, don't
  leak which part was wrong. Match → issue a session exactly like the
  existing `_session_response(user_id, EMAIL_PASSWORD, db)` helper already
  does for every other provider.

**Frontend implication (noted, not designed here — out of this backend-
focused spec's scope):** the single "Continue with Email" pill can't
transparently resolve new-vs-existing the way it does today. The clean
mechanic is an email-entry screen offering two explicit actions ("Create
account" / "Log in") rather than trying to auto-detect — sidesteps needing
a "does this email exist" check entirely. Actual screen/copy design is a
frontend-plan-time decision, flagged here so it isn't lost.

### 4a. Why password-signup's email is always treated as unverified — and what that concretely means

Treating a freshly-typed signup email as "verified" for collision purposes
would reopen the exact vulnerability class this project's own final backend
review already found and fixed for Google (Critical Finding 1: an
unverified email claim getting laundered into a verified-ownership signal,
letting an attacker capture a victim's later real signup). Nothing
cryptographically proves the signer controls the mailbox at
password-signup time — only an actual confirmation click does (§4c) — so
`email_verified=False` is passed unconditionally, exactly matching how
Google's own `email_verified: false` claim is already handled. Consequence:
email+password can never `auto_link`/`link_required` by email match at
signup.

**Traced explicitly, not just asserted by analogy** (this is the scenario
where the entered email already belongs to someone else's account, via
phone, Google, or a prior password signup):

- **A prior `EMAIL_PASSWORD` identity already exists for that email**:
  rejected up front with 409 (§4, unchanged, already explicit).
- **The email is tied to an account via phone or Google, but has no
  `EMAIL_PASSWORD` identity yet**: the existing (unmodified)
  `/auth/otp/verify` route logic decides what happens at phone-gate
  completion based on the **phone number entered**, not the email —
  `find_or_backfill_phone_identity` on that phone number. If it matches
  an existing account, the new email+password identity attaches to it
  (`attach_pending_identity`, no duplicate). If it doesn't — because the
  real owner used a different phone, or because someone else typed a
  stranger's email with their own phone number — `complete_phone_gate_
  signup` creates a **brand-new, empty `User` row**, and the
  `AuthIdentity` row's `provider_subject` (the login identifier) is set
  to whatever email was typed, `email` itself staying `NULL` since it was
  never verified.

**No hijack of a real account is possible either way** — a fresh signup
never attaches to an existing account unless the entered *phone number*
matches, and controlling a phone number is a materially harder bar than
typing an email string. What IS possible: someone typing a stranger's
email creates their own new, empty, unrelated account whose password
identity happens to be keyed by that stranger's email — a namespace-
squatting nuisance (the real owner would 409 if they later tried to sign
up with their own email), not an account compromise. §4c closes this: the
squatted identity can never be used to log in until the real mailbox owner
proves control of it, and a real owner can self-service reclaim it via
password reset (§3) even without ever seeing this design doc.

An existing account can still gain an email+password credential via the
**normal step-up-linking path** the collision system already has (§4d) —
just never silently at signup time.

### 4b. Threading the password hash through the phone gate

`complete_phone_gate_signup`/`attach_pending_identity` (unchanged
functions) call `record_identity(db, user_id, provider, provider_subject,
email, verified_at, commit=...)` with no password parameter — `AuthIdentity`
needs one more field written at the same point. Rather than change
`record_identity`'s signature (touches every call site, all four providers),
**`create_pending_verification` gains one new optional parameter,
`password_hash: str | None = None`**, stored on a new nullable
`PendingIdentityVerification.password_hash` column — already hashed by the
time it gets here (§4a's route hashes before this call; the raw password
is never written to the DB, never logged). Google's and phone's call sites
are unaffected (they don't pass it, default `None`).
`complete_phone_gate_signup` copies `pending.password_hash` onto the
newly-created `AuthIdentity` row (harmless `None` for every non-password
provider). This is the smallest change that doesn't touch the other three
providers' code path at all beyond one unused default parameter.

### 4c. Email confirmation, decoupled from signup — closes §4a's squatting gap

Signup and the phone gate complete **immediately, with zero added
friction** — the account is created and a session issued right away,
identical to Google's UX today. What's gated is narrower: `AuthIdentity`
gains `email_confirmed_at: TIMESTAMPTZ NULLABLE` (populated only for
`EMAIL_PASSWORD` rows — every other provider is inherently verified at
creation, so this column is permanently `NULL`/irrelevant there), and
**only `/auth/login/email` checks it** — a password login attempt against
an identity with `email_confirmed_at IS NULL` fails with a distinct
message ("Please confirm your email before signing in with a password —
check your inbox, or resend the link") rather than the generic
wrong-credentials 401. This is safe to disclose distinctly: reaching that
check already required the submitted password to match the stored hash,
so only someone who already knows the correct password — the legitimate
account holder, mid-confirmation — ever sees it. Until confirmed, the
account remains fully usable via the phone number the gate already
verified.

**What actually sends email, stated explicitly rather than left to
inference:** grepped the whole backend — today, `send_email` has exactly
one caller anywhere (`otp.py`'s email-OTP delivery, removed by §1). This
spec adds exactly two, and **nothing else in this codebase sends email to
an `EMAIL_PASSWORD` address, confirmed or not** — no welcome email, no
signup notification, nothing:
1. **The confirmation link** (new) — sent once, immediately after
   `complete_phone_gate_signup`/`attach_pending_identity` finish for a
   password identity. Its entire purpose is reaching an unconfirmed
   mailbox, so it's dispatched regardless of `email_confirmed_at` by
   design.
2. **The password-reset link** (§3) — also dispatched regardless of
   confirmation status. This isn't an oversight needing a gate: resetting
   a password by clicking a link mailed to that exact address is exactly
   as strong a proof of mailbox control as the confirmation link itself,
   so §3's reset flow is revised to **also set `email_confirmed_at`** (if
   still `NULL`) the moment a reset succeeds. This is what makes squatting
   self-service-recoverable: a real owner who discovers their email is
   squatted (they 409 on their own signup attempt, get suspicious, hit
   "forgot password") can reclaim login access to that identity row
   without ever filing a support ticket — they end up controlling a
   fresh, empty account under that email, not their real one, but they're
   no longer permanently locked out of using that email for password
   login going forward.

**This must not be a silent background event.** A user who signs up with
email+password has "I log in with email+password" as their mental model;
if phone-gate completion gives no acknowledgment, the first time they log
out and try password login, "please confirm your email" would be a
confusing dead end with no memory of ever being told to expect it. The
frontend needs a lightweight, non-blocking acknowledgment right after gate
completion (e.g., "We've sent a confirmation link to {email} — click it to
enable password login. You're already signed in via your phone."). No new
backend response field is needed for this — the frontend already knows
locally that it just drove an email+password signup through the gate, so
it can show this from its own flow state without the backend echoing
anything back. Flagged here so the requirement isn't lost when the
frontend plan gets written — the actual banner/copy is still a
frontend-plan-time decision, consistent with §4's other frontend note.

### 4d. Step-up linking (existing account adds email+password later)

Out of scope for this spec — the user didn't ask for an "add a login
method" settings feature, and the mandatory-phone-gate + signup/login
split above is the full v1 surface. Flagging only so it's not assumed to
already exist: today, `attach_pending_identity` handles step-up linking
for Google/email-OTP re-auth attempts against an *already-collision-
detected* pending record; email+password never produces one of those at
signup (§4a), so there is currently no path that adds a password to an
existing phone/Google-only account. Worth a follow-up spec if wanted.

## 5. Schema changes

Password is a per-provider credential, not a person-level fact — it
belongs on `auth_identities` (the verification source of truth), not
`users` (the provider-agnostic anchor). This matches the architecture's
existing split exactly: nothing else on `users` is provider-specific.

**New migration** (Alembic, SQLAlchemy Core `sa.table()` literals, no
`app.models` imports — same convention as every migration since `0001`):

- `AuthIdentityProvider` enum: add `EMAIL_PASSWORD = "email_password"`
  (Postgres: `ALTER TYPE ... ADD VALUE`, additive-only, no rename/drop —
  see §1's reasoning).
- `auth_identities`: add `password_hash VARCHAR NULLABLE` — null for every
  non-`EMAIL_PASSWORD` row, populated only for password identities.
- `pending_identity_verifications`: add `password_hash VARCHAR NULLABLE`
  — same nullability logic, per §4b.
- New table `password_reset_tokens` (§3).
- `otp_requests`: drop `email` column and
  `ck_otp_requests_exactly_one_identifier`; `phone_number` back to
  `NOT NULL` (§1). This is a genuine narrowing — confirm no non-empty
  `email` rows exist in any real environment before this runs (dev DB
  currently has none; this becomes a real pre-deploy check once Postgres
  is live, per the Migration Plan's readiness checklist).

This is one migration, not several — all five changes are part of the
same product change and land together, matching how `0004` bundled the
original multi-method-auth schema in one revision.

`Docs/PRDs/Database-Schema-Unifolio.md`'s `users`/`otp_requests` sections
already went stale when `0004`/`0005` landed (still describe pre-multi-
method-auth schema) — this spec's migration should be the trigger to
finally bring that doc current for `auth_identities`,
`pending_identity_verifications`, and `otp_requests`, not just add this
one more layer of drift on top.

## 6. Documentation: PRD-02 and decisions.md

**PRD-02 FR-2 currently reads:** "Phone number + OTP is the sole
signup/login method. No password, ever." This is now false for the email
path and needs explicit correction, not a silent contradiction left
sitting in the doc:

> FR-2 (updated): Phone+OTP and Google remain fully passwordless. Email
> signup uses email+password — the one path where password-manager
> autofill removes more friction than an inbox-check step would save.
> Every account still converges on a verified phone as a mandatory second
> step (FR-2 unchanged in that respect) regardless of which method started
> signup.

**`decisions.md`** gets a new entry (not an edit to the old one — this
file is append-only) explicitly marking the reversal:

> Email signup moves from email+OTP to email+password (reverses the
> 2026-08-14 multi-method-auth decision that made email one of three
> transparent-OTP-style methods). **Why:** password-manager autofill
> removes more real friction on email than email-OTP's inbox-check step
> saves — phone+OTP and Google both keep their zero-friction, instant-
> verification advantage, so the passwordless principle stays intact
> everywhere it was actually earning its keep. Google and phone+OTP are
> unchanged.

## Open item carried forward (not blocking, flagged per this session's own convention)

§4d (adding a password credential to an existing account after signup) is
explicitly out of scope — noted so it doesn't get silently assumed to
exist when the frontend team goes looking for a "change my login method"
settings flow later.

## Appendix

### Related Documents
- `2026-08-14-multi-method-auth-design.md` — the identity model this spec
  builds on (unchanged): `users`/`auth_identities`/
  `pending_identity_verifications`, precedence, the mandatory phone gate,
  the account-linking collision policy.
- `Docs/PRDs/PRD-02-Signup-Onboarding.md` — FR-2, updated per §6.
- `Docs/PRDs/Database-Schema-Unifolio.md` — stale on `auth_identities`
  even before this spec; flagged in §5 as due for a refresh.
- `Docs/PRDs/Migration-Plan-SQLite-to-Postgres.md` — the guardrails this
  spec's migration follows (Alembic-only, ORM-independent Core literals,
  no dialect-specific JSON, dialect-neutral where the enum-ADD-VALUE step
  needs it).

### Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-17 | Claude (PM partner) | Initial compact spec per user's explicit lean-brainstorming request — six numbered requirements resolved, no alternatives-considered essays. |
