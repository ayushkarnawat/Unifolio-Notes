# Multi-Method Auth — Design Spec

## Purpose

Unifolio's auth is currently phone+OTP-only (PRD-02 FR-2/FR-2a/FR-2b), built
and merged in Phase 2. This spec remodels it into a multi-method system —
**v1 scope: Google sign-in, email+OTP, and the existing phone+OTP** — as
equal entry points on one landing screen, per direct product decision (not
a PRD-02 revision cycle; PRD-02 stays as the historical record of the
original phone-only decision, cross-referenced here, not edited).

**Sign in with Apple is explicitly deferred to Future Scope, not built in
this pass** — it's the one method with a real, recurring, paid
prerequisite (a $99/year Apple Developer Program membership, required
regardless of App Store distribution), and the product decision was to
confirm that cost is worth it separately rather than bundle it into this
build. The research is preserved (see **Future Scope — Apple Sign-In**
below) so nothing is lost when it's picked back up; nothing about the v1
schema or API design below forecloses adding it later.

**Phone is the universal identity anchor — every account ends up with a
verified phone number, no exceptions**, per updated product decision (§1).
This reverses this spec's own earlier v1.0 draft, which made phone fully
optional to match "three equal entry points" literally. The landing screen
still presents Phone/Google/Email as three equal-looking buttons (frontend
spec, unaffected) — but backend behavior now guarantees that whichever one
a user starts with, phone gets captured and verified before the account is
considered fully signed up. Google and Email remain equal-weight *entry
points into signup*; they are not equal-weight *identity anchors* once
signup completes.

This is a design spec only. No code, no migrations, no implementation. The
next step after approval is `writing-plans`, not implementation.

## Context — what exists today

- `users.phone_number` is `UNIQUE NOT NULL` — the sole identity anchor.
  `otp_requests` is phone-keyed; `sessions` is opaque-bearer-token,
  SHA-256-hashed, provider-agnostic in practice even though only one provider
  exists today (`backend/app/models/auth.py`, `backend/app/services/auth/`).
- `POST /auth/otp/verify` creates a `User` on first-ever verification for a
  phone number, fetches otherwise, then issues a `Session` — new-vs-existing
  is handled transparently, never asked explicitly (`backend/app/api/auth.py`).
- Frontend: `Landing.tsx` (Sign Up / Log In framing, PRD-02 FR-2b) →
  `PhoneEntry.tsx` → `OtpVerify.tsx`, orchestrated by `AuthEntryFlow.tsx`.
- Database-Schema-Unifolio.md's design principle of separating *reference
  data* from *user data* is the closest existing precedent for the identity/
  profile separation this spec introduces (§1).
- ADR-001 states Unifolio has no public/SEO marketing surface in scope for
  this MVP. This spec deliberately overrides that framing for one narrow
  piece — see the frontend spec's visual design section and Explicit
  Deviations below — rather than reopening the ADR itself.

## 1. Identity model

**New table `auth_identities`** — one row per external identity, many rows
per user:

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `user_id` | `UUID` FK → `users.id` NOT NULL | |
| `provider` | `ENUM('phone_otp','email_otp','google')` NOT NULL — **v1 scope only** | `apple` is deliberately not in the v1 enum (see Future Scope) — adding it later is a small, standard `ALTER TYPE ... ADD VALUE` migration, not a redesign |
| `provider_subject` | `VARCHAR` NOT NULL | Phone number (`phone_otp`), email address (`email_otp`), or Google `sub` claim |
| `email` | `VARCHAR` NULLABLE | Denormalized from the identity's own claim (OAuth) or the identifier itself (`email_otp`) — used only for the collision lookup in §4, not as a credential itself |
| `identifier_verified_at` | `TIMESTAMPTZ` NOT NULL | When *this specific identity* was proven — OTP `verified_at` or OAuth token verification time |
| `created_at` | `TIMESTAMPTZ` NOT NULL | |
| `last_used_at` | `TIMESTAMPTZ` NOT NULL | |
| UNIQUE | `(provider, provider_subject)` | A given phone number, email, or Google account can only ever belong to one `user_id` |

**`users.phone_number` stays exactly as it is today: `UNIQUE NOT NULL`.**
This reverses this spec's own v1.0 draft, which dropped that constraint to
make phone fully optional (see Purpose). Per updated product decision,
phone is the universal anchor — every `User` row has a verified phone,
regardless of which method the account started with. This is actually
**less migration work than v1.0's draft implied**, not more: there is no
`ALTER COLUMN phone_number DROP NOT NULL` to write at all, since the column
isn't changing shape. `auth_identities` still models phone as its own row
(`provider='phone_otp'`) exactly like Google and email — this isn't a
reversion to the original phone-only schema, it's the NOT NULL constraint
sitting on top of (not instead of) the `auth_identities` design, enforced
at the service layer: a `User` row cannot be created without a
corresponding verified `phone_otp` identity, which is what makes the
constraint enforceable by construction rather than by a flag someone has
to remember to check (see "Signup completion" below).

`email` stays nullable, **purely denormalized** — whatever email happens
to be attached to the profile for display/notification purposes. It is
never itself a source of verification truth. Only `auth_identities` rows
carry `identifier_verified_at`, which is what §4's collision logic reads.
(`phone_number` is denormalized in exactly the same sense — the
`auth_identities` `phone_otp` row is the verification source of truth;
`users.phone_number` is a fast-lookup copy of it, same relationship as
`users.email` has to its own identity rows.)

**New table `pending_identity_verifications`** — holds a newly-verified
Google or email identity that can't yet be attached to a session, either
because it belongs to a brand-new signup still missing its mandatory phone
step, or because it collided with an existing account and needs step-up
re-auth (§4) before linking. One mechanism, two triggers — see "Signup
completion" below for the first, §4 for the second.

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `provider` | `ENUM('email_otp','google')` NOT NULL | Never `phone_otp` — a phone-first verification never produces a pending record; it completes signup on its own (see below) |
| `provider_subject` | `VARCHAR` NOT NULL | Email address or Google `sub`, matching `auth_identities.provider_subject`'s meaning |
| `email` | `VARCHAR` NULLABLE | |
| `email_verified` | `BOOLEAN` NOT NULL | From Google's claim, or always `true` for `email_otp` (it was OTP-verified to get here) |
| `matched_user_id` | `UUID` FK → `users.id` NULLABLE | Set only for the §4 step-up-link case; `NULL` for a brand-new signup awaiting its phone step |
| `token_hash` | `VARCHAR` NOT NULL | Same hash-and-return-once convention as `sessions.session_token_hash` — the raw token goes to the client exactly once |
| `expires_at` | `TIMESTAMPTZ` NOT NULL | Short-lived (~5–10 min) — **confirmed as one shared window for both triggers**, phone-gate and step-up-link alike, not two different values |
| `created_at` | `TIMESTAMPTZ` NOT NULL | |

**Signup completion: the mandatory phone gate.** Google/Email verification
alone is never enough to create a `User` — it structurally can't be, since
`users.phone_number` is `NOT NULL` and neither Google nor email-OTP
verification produces a phone number. Concretely, when a Google or email-OTP
verification finds **no** existing-account collision (§4's case 3, a
genuinely new identity):

1. Do **not** create a `User` yet.
2. Create a `pending_identity_verifications` row (`matched_user_id = NULL`)
   and return a new response shape — `phone_required: { token, prefill_email }`
   — instead of `OtpVerifyResponse`.
3. The client is routed to phone entry, carrying that `token`.
4. On successful phone+OTP verification with that token attached, the
   backend atomically creates: the `User` row (with the now-known
   `phone_number`), **two** `auth_identities` rows (the new `phone_otp` one,
   and the original Google/email one pulled from the pending record), and a
   `Session` — then responds with the normal `OtpVerifyResponse`, exactly as
   phone-first signup does today.

If the Google/email verification instead **collides** with an existing
account (§4's cases 1–2), this phone gate never fires — the target account
already satisfies the phone invariant by construction, so linking proceeds
via §4's existing collision handling with no extra step.

**Phone-first signup is completely unaffected** — "If Phone: existing
phone+OTP flow, done" per the product decision. It was already the only
method that satisfies the phone requirement on its own, so nothing about
today's `/auth/otp/verify` behavior for a brand-new phone number changes.

**No explicit "signup vs. login" choice anywhere, on either side of this.**
This resolves cleanly into the already-decided frontend framing (no
separate Sign Up/Log In screen, PRD-02 FR-2b superseded): the same
verification endpoint transparently branches on whether the identity
already exists — existing identity → login, session issued immediately, no
phone re-check (it was already captured at signup); no existing identity →
this *is* a signup attempt, and Google/email routes through the phone gate
above while phone completes on the spot, exactly as today.

**Identity precedence: Google > Email > Phone.** Wherever more than one
verified identity exists on the same account and only one can be shown or
selected, prefer Google, then email, then phone. Two concrete places this
resolves ambiguity in this spec:
1. **Populating/refreshing the denormalized `users.email` field** when an
   account holds more than one email-bearing identity (e.g. after an
   auto-link merges a Google identity onto an account that also has a
   separately-verified `email_otp` identity) — use the highest-precedence
   identity's email, i.e. Google's if present, else the `email_otp`
   identity's.
2. **Choosing which `existing_method` to name in a §4 step-up prompt**
   when the target account already holds more than one verified identity —
   prompt via the highest-precedence one the account actually has (Google
   first, then email, then phone). In the common case — an account with
   only its mandatory phone and nothing else — there's nothing to choose
   between; the prompt names phone regardless.

Precedence does **not** change how the §4 email-match lookup itself works
(that's a plain string match against `auth_identities.email`, independent
of provider) — it only resolves which identity to *display or act through*
once more than one candidate exists on the matched account.

**Migration Plan compliance** (per `Docs/PRDs/Migration-Plan-SQLite-to-Postgres.md`,
not restated here, only checked against): `auth_identities` and
`pending_identity_verifications` are new tables, and `otp_requests` gains
nullable columns — all three go through Alembic migrations, never a
hand-edited `CREATE TABLE`/`create_all()` (Guardrail 1). No new query in
this design uses raw dialect-specific SQL — the collision lookup (email
match across `auth_identities`), uniqueness checks, and the widened OTP
verify path are all plain ORM queries (Guardrail 2). **This design
introduces no JSON-ish columns at all** — Google's claims are extracted
into typed columns (`provider_subject`, `email`, `email_verified`), nothing
raw is persisted. If a future need arises to store a raw OAuth payload
(e.g. for debugging, mirroring `imports.raw_parser_output`), it must use
SQLAlchemy's generic `JSON` type per the Known Compatibility Gaps table,
never a Postgres-only `JSONB` literal — flagged now so it isn't
rediscovered later. Neither new table needs partitioning (both are small
and short-lived/append-only, unlike `transactions`/`nav_history`), so that
Known Compatibility Gap doesn't apply here.

**`otp_requests` is generalized, not duplicated.** Email OTP reuses the same
table and the same `otp.py` logic as phone OTP — the hash/expiry/
attempt-count/verification logic is identical; only the delivery channel
(SMS vs. email) differs. Concretely: widen `otp_requests` to nullable
`phone_number` + nullable `email` (a check constraint enforces exactly one is
set), and generalize `create_otp_request`/`verify_otp` to take
`(identifier: str, channel: Literal["sms", "email"])` instead of a
hardcoded phone number. A separate `EmailOtpRequest` table was considered and
rejected — it would duplicate security-sensitive logic (hashing, attempt
capping, expiry) across two tables for no benefit.

**Migration note** (planning-phase work, not built here): existing `users`
rows need a one-time backfill into `auth_identities` —
`provider='phone_otp'`, `provider_subject=users.phone_number`,
`identifier_verified_at=users.created_at` (a verified phone is currently a
precondition for a `User` row existing at all, so `created_at` is an
accurate proxy for when that identity was proven).

**Onboarding integration note**: Google returns a `name` claim that has
nowhere to live on the current schema — `users` has no name column; the
account holder's display name is created during onboarding Q1 as a
`HouseholdMember(relationship='self')` row (per the Phase 2 backend design).
This spec does not add a name column to `users`; instead, a claimed name
should pre-fill onboarding Q1's answer rather than be persisted as new
user-table state. Flagging this as an integration point for the onboarding
flow to handle, not resolving it here.

## 2. Google Sign-In

**Google Identity Services (GIS), rendered button + ID-token flow.** Not One
Tap (an unsolicited auto-popup that would undermine "equal entry points" by
prompting before any button is chosen), not the redirect/authorization-code
flow (built for apps needing ongoing Google API access — Calendar, Drive,
etc. — which Unifolio doesn't need; we only need identity).

**Flow, concretely:**
1. GIS button click → JS callback receives a `credential` (ID token, a JWT).
2. Frontend → `POST /auth/oauth/google {id_token}`.
3. Backend verifies the JWT against Google's public JWKS via the
   `google-auth` Python library (`google.oauth2.id_token.verify_oauth2_token`)
   — checks signature, `aud` == our Client ID, `iss` is
   `accounts.google.com`/`https://accounts.google.com`, `exp` not expired.
4. Extract `sub` (stable Google user id — the only field ever used as
   `provider_subject`, never `email`, since email can change on Google's
   side), `email`, `email_verified`.
5. Run the §4 collision check against `email` (only meaningful if
   `email_verified` is `true` — an unverified Google email, a real if rare
   case, is treated exactly like an unverified `users.email`, i.e. never an
   auto-link candidate).
6. No match → this is a new signup. Per §1's mandatory phone gate, do
   **not** create a `User` yet — create a `pending_identity_verifications`
   row and respond `phone_required` instead of a session (§1). Match → see
   §4's `link_required` response (no phone gate needed there — the matched
   account already has a verified phone by construction).

**No client secret is needed for this** — ID-token verification is pure
signature checking against Google's published public keys, not a token
exchange. This matters for the "what do we need from you" checklist (§8):
Google Sign-In has no secret to protect, only a Client ID, which is
public-safe by design (it goes into frontend code either way).

**Setup** (see §8 for the full checklist, ordered by urgency):
- Google Cloud Console → OAuth consent screen (**External** user type,
  since this is a public consumer product, not a Workspace-internal tool).
- OAuth 2.0 Client ID, type **Web application**.
- **Authorized JavaScript origins** — not redirect URIs, which only apply
  to the authorization-code flow this spec doesn't use.
- **Separate Client IDs per environment** (dev/staging/prod) rather than
  one client with three origins allowlisted, for blast-radius isolation —
  a leaked or misconfigured dev origin can't open a hole in prod.

**Production changes on deploy**: add the prod domain as an authorized
JavaScript origin on the prod Client ID, and move the OAuth consent screen
from **Testing** (capped at 100 test users, shows an "unverified app"
warning) to **Published/In production** — a real go-live blocker, not
automatic. Since only `openid email profile` scopes are requested (no
sensitive/restricted scopes), this does **not** require Google's manual
OAuth verification review — publishing is a self-service step in Console,
but it does require a filled-in **Privacy Policy URL** on the consent
screen, which does not currently exist anywhere in this codebase (flagged
as a real gap in §8, not assumed to exist).

## 3. Email + OTP

Compared four providers for OTP specifically (deliverability-critical, low
volume at MVP scale):

| Provider | ~Cost/1000 (India) | Deliverability posture |
|---|---|---|
| Amazon SES | ~₹8.40 | Cheapest; deliverability/reputation management is on us (DKIM/SPF/DMARC, warm-up, production-access request out of sandbox) |
| Resend | Free tier (3k/mo), then low-cost | Modern DX, good React-email tooling, less battle-tested reputation at scale than Postmark |
| Postmark | ~$1.50/1000, ~$15/mo entry paid tier | Best-in-class transactional deliverability; enforces transactional/broadcast separation by policy |
| SendGrid | ~$0.40/1000 | Mid-price; historically mixed deliverability reputation (shared IP pools) |

**Decided: Postmark** — no longer just a recommendation, confirmed per
product decision. Despite SES's cost and AWS-infra alignment (ADR-003/005
already put us on AWS), at MVP volume (thousands/month, not millions) the
price delta is a few dollars a month — dwarfed by the cost of a login OTP
silently landing in spam. The schema/service design (§1) would have been
identical regardless of provider either way, per the `EmailProvider`
abstraction below.

**Cost, stated plainly**: Postmark has a free tier (100 emails/month,
enough for local/early dev), then ~$15/month for the entry paid tier
(roughly 10,000 emails) — a real, small, recurring cost, distinct from
Google (free) and Apple (see Future Scope's $99/year). Worth an explicit
go-ahead even though it's cheap, since it's a new recurring vendor bill.

**Setup, concretely** (see §8 for full checklist):
1. Postmark account — decide who owns billing.
2. **Domain verification**: Postmark requires adding DNS records (an SPF
   `TXT` record, a DKIM `CNAME`/`TXT` record, and a Return-Path `CNAME`) to
   whichever domain OTP emails are sent from — e.g. `unifolio.in` directly,
   or a subdomain like `mail.unifolio.in` (a subdomain is often preferred so
   a sending-reputation issue can't affect the main domain's regular email).
   This requires access to that domain's DNS management — **not something
   code alone can do**, flagged explicitly as a developer/ops action item.
3. Decide the sending address/display name (e.g. `Unifolio <otp@unifolio.in>`)
   — a product decision, not just a technical one.
4. Generate a Postmark **Server API Token** once the account/domain are set
   up — this is the real secret that goes into AWS Secrets Manager (§6).

Email OTP reuses the existing `otp_requests` table and `otp.py` logic per
§1 — same hash/expiry/attempt-count/verify code path as phone, dispatched to
Postmark instead of the SMS stub at send time. **Local dev is not blocked
on Postmark existing** — the existing `otp_delivery_mode="stub"` echo-back
behavior (already gating phone OTP in `otp.py`, `create_otp_request`)
extends identically to email: in stub mode, the raw OTP is returned in the
API response instead of actually being sent, exactly as it works for phone
today. Postmark is only required for a real end-to-end send test and for
anything beyond local SQLite dev.

**A verified email-OTP identity that finds no collision (§4) goes through
the same mandatory phone gate as Google (§1)** — email is symmetric with
Google here, not a second special case. A brand-new email-first signup gets
a `pending_identity_verifications` row and a `phone_required` response,
exactly like an unmatched Google verification does.

**`EmailProvider` abstraction — don't hardcode "no email provider" as a
dead end.** Same pattern as `otp_delivery_mode`'s existing stub/real split
for phone: a small protocol,

```python
class EmailProvider(Protocol):
    def send_email(self, to: str, subject: str, body: str) -> None: ...
```

with a `StubEmailProvider` implementation for this pass — logs/echoes
instead of sending, selected whenever `otp_delivery_mode == "stub"`, mirroring
exactly how phone OTP already behaves in that mode. Swapping in the real
`PostmarkEmailProvider` later is adding one new implementation of the same
protocol and flipping a config value — not a redesign. This same
abstraction is what any future account-linking or notification email (e.g.
"a new sign-in method was added to your account," not specified further in
this pass) would send through too, so it isn't built twice when that need
shows up.

**v1 implementation ships with `StubEmailProvider` only — wiring up
`PostmarkEmailProvider` is deferred, but only until production launch,
not open-ended.** Per product decision: **email stays visible in the UI
throughout** — it is not hidden while running on the stub, in dev or
otherwise. This mirrors an existing precedent in this codebase exactly:
the Phase 2 backend spec already deferred *real SMS delivery* the same way
("dev-only stub this phase... a real provider gets wired in once one is
chosen") — email OTP gets the identical treatment.

**The one hard constraint this creates, now resolved rather than left
open**: `otp.py`'s existing safety guard already refuses stub delivery
outside SQLite (`otp_delivery_mode='stub' is not allowed against a
non-SQLite database`). That guard isn't being relaxed, so
`PostmarkEmailProvider` becomes a **firm prerequisite for this feature
reaching a Postgres environment** (staging or production) with email still
functional — not a nice-to-have follow-up. Local SQLite dev is unaffected
either way. This is a real sequencing dependency for planning to carry
forward: Postmark setup (§8) needs to land before — or, at the latest,
as part of — this feature's first Postgres deployment.

## 4. Account linking / collision policy

Product decision: **step-up re-auth to link, not silent auto-merge on an
unverified email match.** Concretely, on any new Google or email-OTP
verification, check `auth_identities` for a matching email in this order:

1. **Matches another user's already-independently-verified identity**
   (a verified Google account's email, or a separately email-OTP-verified
   address — on a *different* `user_id`) → **auto-link**. Both sides have
   independently proven ownership of that mailbox/account, so attaching the
   new identity to that `user_id` carries no session-hijack risk.
2. **Matches only the denormalized, never-separately-verified `users.email`**
   on an existing account (e.g. a phone-only account that has an unverified
   email string sitting on its profile) → **do not auto-link.** Surface a
   step-up prompt: "We found an account with this email — log in with your
   phone to link Google to it." Require a successful login via the existing
   account's already-verified method — if the matched account holds more
   than one, pick which to name via §1's identity-precedence rule (Google >
   Email > Phone; in the common case, an account with only its mandatory
   phone, the prompt just names phone) — then attach the new identity to
   that now-authenticated session's user. The `pending_identity_verifications`
   table (§1) holds the new identity's claim
   (`provider`, `provider_subject`, `email`, `matched_user_id` set to the
   matched account) until the step-up login succeeds — the same table and
   mechanism used for the mandatory-phone-gate case, just with
   `matched_user_id` populated instead of `NULL`.
3. **No match at all** → normal new-account creation, identical to today's
   phone-first-verification-creates-a-User behavior.

Note this is symmetric across all three v1 methods — the "new" identity
triggering a collision check and the "existing" identity it collides with
can be any pairing of phone/email/Google; nothing here special-cases which
side is which.

This is deliberately more cautious than "any email match auto-links" — an
unverified `users.email` field proves nothing about who actually controls
that mailbox, and auto-linking against it would let anyone who happens to
own that address take over an existing account's financial data.

## 5. Session model

**No structural changes needed, one column added.** `Session` /
`get_current_session` / `get_current_user`
(`backend/app/services/auth/session.py`) is already provider-agnostic — a
session is keyed on `user_id`, and nothing in token creation or
verification cares which method produced that user. The opaque-bearer-token,
SHA-256-hashed, 30-day-refreshed-on-activity design carries over unchanged
regardless of how many auth methods exist.

**One addition: an `auth_method` column on `Session`.** Previously flagged
as optional/deferrable; now built in, since it's a small addition and it's
directly useful given §1's new signup-completion flow — the same column
that would support future observability/device-management UX (PRD-02
FR-2a's already-deferred scope) also cleanly records, for the session
created at the end of a phone-gated Google/email signup, that the account's
*originating* method was Google/email even though the session itself was
issued off the final phone verification. Without it, that provenance would
otherwise only be recoverable by joining out to `auth_identities` and
guessing from `created_at` ordering.

| Column | Type | Notes |
|---|---|---|
| `auth_method` | `ENUM('phone_otp','email_otp','google')` NOT NULL | Matches `auth_identities.provider`'s v1 values (no `apple` — see Future Scope). Set to whichever method's verification directly produced this session — for a phone-gated signup, that's `phone_otp` (the method that completed it), not the originating Google/email identity; the originating identity is still recoverable via `auth_identities` if ever needed |

## 6. Security / production-readiness

- **CSRF**: Google GIS requires verifying its `g_csrf_token` double-submit
  cookie against the value in the POST body before trusting the credential —
  a documented Google requirement, not optional.
- **Nonce**: pass a per-attempt nonce into the GIS init call; verify it
  against the `nonce` claim in the returned, verified ID token. Standard
  OIDC replay protection.
- **Per-environment isolation**: separate Google Client ID for dev /
  staging / prod — never shared across environments.
- **Secrets management**: Google needs **no server-side secret** for this
  flow (pure JWT verification against public keys) — the only real secret
  in v1 is the **Postmark API token**, which goes into AWS Secrets Manager /
  SSM Parameter Store, injected into the ECS task definition (fits
  ADR-005's existing ECS Express Mode target) — never committed, never in a
  frontend-visible `.env`.
- **Rate limiting**: extend the existing per-`OtpRequest` `attempt_count`
  cap (5 wrong tries kills that request) identically to email. New addition
  worth doing now (distinct from the already-deferred full IP/lockout
  policy): reject a new `/otp/request` for the same identifier if an
  unexpired, unverified request already exists under ~60 seconds old — a
  real cost control now that email sends are billed per-message.
- **Deploy checklist items to carry into planning**: CORS origin allowlist
  per environment; CSP `script-src`/`connect-src` addition for
  `accounts.google.com`; Google consent screen publish status (and its
  Privacy Policy URL dependency, §2/§8) before real users can sign in.

## 7. Backend testing

Matching Phase 2's own testing approach (pytest, in-memory SQLite for
service-level tests, `TestClient` for route-level tests):

- **Identity model (§1)**: service-level tests for the generalized
  `create_otp_request`/`verify_otp` covering both `channel="sms"` and
  `channel="email"` against the same widened table — same hash/expiry/
  attempt-count assertions as today's phone tests, parameterized by channel
  rather than duplicated. A dedicated test for the check constraint (exactly
  one of `phone_number`/`email` set) rejecting a row with both or neither.
- **Google verification (§2)**: mock `google.oauth2.id_token.verify_oauth2_token`
  (the library boundary, not real network calls) to test: a valid token
  creates a new user; a valid token matching an existing `auth_identities`
  row logs in that user; an invalid signature/expired/wrong-`aud` token is
  rejected with 401; an unverified-email Google token never triggers
  auto-link (§4).
- **Collision/linking (§4)**: the highest-value test surface here —
  auto-link-on-verified-match, no-auto-link-on-unverified-match producing a
  `link_required` response instead, the `pending_identity_verifications`
  record's TTL expiring, and completing a step-up link via each of the
  three possible existing methods (phone/email/Google).
- **Mandatory phone gate (§1)**: a brand-new Google verification with no
  collision returns `phone_required`, not a session, and does **not**
  create a `User` row; completing the phone step with that token
  atomically creates the `User` plus both `auth_identities` rows (Google
  and phone) plus a `Session` in one transaction; an expired
  `pending_identity_verifications` token is rejected cleanly; a brand-new
  phone-first signup is completely unaffected (no gate, no pending record,
  same behavior as today) — parameterize the same test across Google and
  email-OTP as the originating method, since §3 confirmed they're symmetric.
- **Identity precedence (§1)**: an account with both a Google identity and
  a separately-verified email identity resolves `users.email` to the
  Google address, not the email-OTP one; a step-up prompt against an
  account holding phone + Google (no separate email identity) names Google,
  not phone.
- **`Session.auth_method` (§5)**: a phone-gated signup's resulting session
  records `auth_method='phone_otp'` (the completing method), not the
  originating Google/email identity.
- **Route-level (`TestClient`)**: `POST /auth/oauth/google` status codes and
  response shapes exactly like the existing `/auth/otp/verify` route tests —
  a malformed/missing `id_token` is a 400, not a 500; an unauthenticated
  request never trusts a client-supplied `user_id`, matching the existing
  "no IDOR by construction" pattern from Phase 2's own design.

## 8. Setup & Credentials Checklist — what we need from you

Organized by urgency, not by topic — some of this blocks starting
implementation, some only blocks a real end-to-end test, some only blocks
production deploy.

### Needed to start backend implementation (blocks day one)
- **One Google Cloud OAuth Client ID for local dev** (`http://localhost:5173`,
  or whatever Vite's dev port is) — free, no billing account required for
  this. Someone needs to either create a Google Cloud project for Unifolio
  or confirm one already exists, then create this Client ID and share it
  (the Client ID itself, nothing secret) with whoever's implementing.
- **No Postmark account needed yet** — local dev uses the existing stub
  delivery mode (§3), same as phone OTP does today.

### Deferred past this pass's implementation, but required before this feature reaches Postgres (staging/production)
Per product decision, **Postmark is the confirmed choice** (§3) but isn't
wired up as part of this implementation pass — `StubEmailProvider` ships
first, and email stays visible in the UI throughout regardless. This
bucket isn't optional forever, though: per §3, email-as-a-method won't
function once this runs against Postgres until it's actioned, so treat it
as a prerequisite for that deploy, not a someday-maybe:
- **A Postmark account** — decide who owns billing (free tier covers early
  testing; ~$15/month once past 100 emails/month, see §3).
- **DNS access for whichever domain sends OTP emails** (e.g. `unifolio.in`
  or a subdomain) — Postmark's SPF/DKIM/Return-Path records need to be
  added by whoever controls that domain's DNS. This is a real action item
  outside of what code can do — flagging it now so it isn't discovered as a
  blocker later.
- **A decision on the sending address/display name** (e.g.
  `Unifolio <otp@unifolio.in>`).

### Needed before Google sign-in can go live for real users (not just testing)
- **A Privacy Policy page.** Confirmed via a repo search: **no Privacy
  Policy or Terms of Service page exists anywhere in the current frontend**.
  This spec **does not draft policy text** — content is pending input from
  the product owner. What this spec does confirm: a `/privacy-policy` route
  is required, linked from the signup screen per PRD-02 FR-3's trust-first
  framing (the frontend spec's landing screen should wire up the link/route
  now, pointing at placeholder content until real copy is provided), and
  the resulting URL is also required on Google's OAuth consent screen to
  move it out of "Testing" mode (capped at 100 users, shows an "unverified
  app" warning to everyone else otherwise). One page, two consumers.
- **Separate Google Client IDs for staging and production domains**, once
  those domains are decided — cheap and fast to create, but needs the
  domain name(s) decided first.
- **AWS access** to create a Secrets Manager / SSM Parameter Store entry for
  the Postmark API token in whatever AWS account/region will host the ECS
  deployment (ADR-005) — per CLAUDE.md's "local development first," this
  can wait until the Migration-Plan-SQLite-to-Postgres.md readiness
  checklist is actually being worked, not before.

### Not needed at all in this pass
- **Apple Developer Program membership ($99/year)** — see Future Scope.
  Nothing above requires it; nothing in the v1 schema forecloses adding it
  later.

## 9. Frontend scope

**Split into its own file**: `2026-08-14-multi-method-auth-frontend-design.md`,
mirroring this repo's existing Phase 2 (backend) / Phase 2b (frontend) doc
split. That file covers: the `feat/enhanced-ui` branch-reality check
(Tailwind/shadcn landed, Bklit not, no router), component-by-component
changes to `Landing.tsx`/`AuthEntryFlow.tsx`/`PhoneEntry.tsx` and the new
`EmailEntry`/`EmailOtpVerify`/`GoogleButton`/`LinkAccountPrompt` components,
the concrete resolution of the OAuth-popup-in-a-router-less-SPA question,
the account-linking-collision UI wire contract, new `api.ts` functions,
brand-guideline-aware visual treatment for the split-card layout with its
decorative right panel, and the test plan.

## Future Scope — Apple Sign-In

**Deferred, not built in this pass, due to a real recurring cost the
product owner should sign off on independently: a $99/year Apple Developer
Program membership, required to use Sign in with Apple at all, regardless
of App Store distribution status.** This is a genuinely different kind of
decision than Postmark's ~$15/month (§3) — an annual developer-program fee
tied to an Apple account, not a usage-based SaaS bill — worth its own
explicit approval rather than bundling into this build's setup checklist.

The research below is preserved so nothing is lost when this is picked back
up; nothing in the v1 design (schema enum, `LinkAccountPrompt`'s
`existing_method` union, `useOAuthScript`'s generic shape) forecloses adding
it later — each of those call out exactly what a future Apple addition
touches.

**One piece of Apple *is* in scope now, on the frontend only**: a disabled
"Continue with Apple — Coming soon" placeholder button, reserving its slot
in the landing screen's button stack so the layout doesn't reflow when the
real integration ships (frontend spec §1/§3/§5). It has no SDK, no handler,
and makes no backend call — this section's deferral is otherwise
unaffected; the backend still does nothing Apple-related in this pass.

**Flow**: same JWT-verification shape as Google — Apple JS SDK → `id_token`
(JWT) → `POST /auth/oauth/apple {id_token}` → backend verifies against
Apple's public JWKS (`https://appleid.apple.com/auth/keys`), checking `aud`
against our Services ID.

**Setup, once approved** — heavier than Google's, regardless of App Store
status:
- The $99/year Apple Developer Program membership itself.
- A **Services ID** (the web `client_id`).
- A **Sign in with Apple private key** (`.p8`, downloadable exactly once at
  creation) — used to sign a JWT client secret, needed only if a future
  authorization-code exchange is added (not needed for pure ID-token
  verification, same reasoning as Google).
- Domain verification via a `.well-known/apple-developer-domain-association.txt`
  file served from each environment's domain.
- Once built: the `.p8` private key is a genuine secret (unlike Google) and
  would need its own AWS Secrets Manager entry (§6).

**Apple-specific quirks to design around when this is built:**
- Apple returns the user's **name only on the first-ever authorization
  ever** — must be captured and used to pre-fill onboarding at that moment,
  or it's gone (Apple will not resend it on subsequent logins).
- Users may choose **Hide My Email**, returning a
  `@privaterelay.appleid.com` forwarding address instead of a real one —
  treat it as verified, since Apple forwards mail to the user's real inbox.

**Is it required?** No. Apple's App Store Review Guideline 4.8 (offer Apple
sign-in if other social logins are offered) applies only to apps
distributed through App Store review. Unifolio is a web app, not currently
submitted there, so Sign in with Apple is not a compliance requirement
today. If a native iOS app ships later and offers Google sign-in, this
guideline would then apply.

**What re-enabling it touches, concretely** (so a future pass isn't a
rediscovery exercise):
- `auth_identities.provider` enum: add `'apple'` (one migration).
- A new `AppleButton.tsx`, reusing the already-generic `useOAuthScript.ts`.
- `LinkAccountPrompt`'s `existing_method`/`OtpVerifyResult` union: add
  `"apple"`.
- `POST /auth/oauth/apple` route, mirroring `/auth/oauth/google`'s shape.
- A dedicated `AppleButton.test.tsx`, mirroring `GoogleButton.test.tsx`.
- §8's checklist: add the Apple Developer Program membership, Services ID,
  `.p8` key, and domain-association file as new setup items.

## Explicit Deviations (flagging, not silently resolving)

1. **PRD-02 FR-2b superseded for the entry screen specifically.** FR-2b's
   "Sign Up and Log In as two labeled entry points" is replaced by one
   neutral framing across all v1 methods (see the frontend spec's
   Component changes section). PRD-02 itself is left unedited per product
   decision (this spec is standalone, cross-referenced, not a PRD-02
   revision) — but anyone reading PRD-02 FR-2b going forward should know it
   no longer reflects the built entry screen.
2. **ADR-001's "no public marketing surface" framing is overridden for this
   one screen's decorative right panel**, per explicit product decision.
   This is scoped narrowly — one static, illustrative asset on the auth
   screen — not a reopening of ADR-001's broader no-Next.js/no-SEO-surface
   decision, which stands otherwise unchanged.

## Open Items Not Resolved Here

Six resolutions came in the prior round (numbered 1–4 and 6, no item 5),
and a further five resolved most of what was still open after that. Both
rounds are folded into the sections above; what's left:

- **The Privacy Policy page's actual content** — the route/link requirement
  is resolved (§8), but the copy itself is pending input from the product
  owner, per explicit instruction not to draft it here.
- **When to revisit Apple Sign-In** — no target date set; Future Scope above
  is ready to pick up whenever the $99/year is approved. (The frontend's
  disabled placeholder button is already in place either way.)
- **Changing a linked phone number after signup** isn't addressed anywhere
  in this spec (same as today) — out of scope for this pass, flagged only
  so it isn't assumed to be covered.

Resolved this round, for the record: email stays visible in the UI
throughout, running on `StubEmailProvider` until Postmark is wired up as a
firm prerequisite for production launch specifically (§3/§8) — not hidden
in the interim, and not an open-ended "later." Postmark is the confirmed
choice, not just the recommendation (§3) — the SES-vs-Postmark question is
closed. `pending_identity_verifications` uses one shared TTL window for
both triggers (§1), no differentiated timing. The right-side panel's exact
content is pending details the product owner will provide separately —
tracked in the frontend spec, not specified here.

## Appendix

### Related Documents
- `2026-08-14-multi-method-auth-frontend-design.md` — the frontend spec
  split out of this doc's former §9, covering the auth-entry UI, the
  OAuth-popup mechanism, and the account-linking prompt
- PRD-02: Signup & Onboarding — FR-2/FR-2a/FR-2b, the original phone-only
  decision this spec extends (not edited)
- `Docs/superpowers/specs/2026-08-05-phase-2-auth-onboarding-backend-design.md`
  — the existing phone+OTP backend this spec builds on top of
- Database-Schema-Unifolio.md — `users`, `otp_requests`, `sessions` current
  definitions
- ADR-Technical-Stack-Decisions.md — ADR-001 (deviation noted in the
  frontend spec), ADR-003/ADR-005 (AWS RDS/ECS — where secrets and email
  provider calls live)
- Design-Schema-Unifolio.md — light/dark color tokens, component conventions
  reused for the new card and pill buttons

### Research Sources
- Google Identity Services / ID-token verification: Google for Developers
  documentation (`developers.google.com/identity/gsi/web`)
- Sign in with Apple web setup, Services ID, `.p8` key / JWT client secret
  (Future Scope): Apple Developer documentation, Okta and Sarunw's Sign in
  with Apple technical write-ups (2026 sources)
- Apple App Store Review Guideline 4.8 scope (Future Scope): Apple Developer
  Program guidelines, 9to5Mac coverage of the 2024 guideline revision
- Transactional email provider comparison (SES/Resend/Postmark/SendGrid):
  productgrowth.in, buildmvpfast.com, emailsendx.com (2026 pricing/
  deliverability comparisons)

### Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-14 | Claude (PM partner) | Initial draft — multi-method auth design, all areas resolved per user decisions during brainstorming (phone fully optional, step-up re-auth linking, PRD-02 left standalone, split-card layout with decorative right panel overriding ADR-001 for this screen only) |
| 1.1 | 2026-08-14 | Claude (PM partner) | Frontend section (then §8) expanded to match backend depth: confirmed `feat/enhanced-ui`'s actual Tailwind/shadcn (landed) vs. Bklit (not landed) status before designing against it; resolved the router-less-SPA/OAuth-popup question concretely; added collision-UI wire contract, new API functions, brand-guideline-aware visual treatment, and a test file list matching actual repo convention |
| 1.2 | 2026-08-14 | Claude (PM partner) | Descoped Sign in with Apple to Future Scope per product decision (its $99/year Apple Developer Program membership is a real recurring cost warranting separate sign-off) — v1 is phone + email + Google only. Added a consolidated Setup & Credentials Checklist (§8) organized by urgency, a new Backend Testing section (§7), and expanded Google/Email setup steps with concrete detail (DNS records, Privacy Policy URL gap, per-environment Client IDs). Renumbered backend sections 1–6, frontend section 8→9 accordingly. Apple's original research preserved, not deleted, under Future Scope. |
| 1.3 | 2026-08-14 | Claude (PM partner) | Split former §9 (Frontend scope) out into its own file, `2026-08-14-multi-method-auth-frontend-design.md`, per user request — mirrors this repo's existing Phase 2/Phase 2b backend-frontend doc split. This doc is now backend-only (§1–8) plus the shared Future Scope/Deviations/Open Items/Appendix. |
| 1.4 | 2026-08-14 | Claude (PM partner) | Six product resolutions applied: (1) reversed v1.0's "phone fully optional" call — phone is now the universal identity anchor, every account gets one regardless of starting method, enforced structurally via a new mandatory phone-gate flow (`pending_identity_verifications` table, `phone_required` response) rather than a flag; (2) confirmed compliance with `Migration-Plan-SQLite-to-Postgres.md`'s guardrails, no JSON columns introduced; (3) added an explicit Privacy Policy page/route requirement, content deliberately left undrafted pending product-owner input; (4) added an `EmailProvider` protocol + `StubEmailProvider`, mirroring the existing OTP stub-delivery pattern, so a real provider is a future drop-in, not a redesign; (6) resolved identity precedence (Google > Email > Phone) at its two concrete ambiguity points — `users.email` denormalization and step-up-prompt method selection. Also added the previously-optional `Session.auth_method` column as a firm decision, per follow-up request mid-turn. (No item 5 was provided — flagged in Open Items rather than assumed.) |
| 1.5 | 2026-08-14 | Claude (PM partner) | Three follow-ups: confirmed the frontend spec is now updated to match v1.4 (§9 pointer unaffected, actual sync done in that file); clarified Postmark is explicitly deferred beyond this pass — `StubEmailProvider` only, with the real implication surfaced that email-as-a-method won't function against Postgres until Postmark lands (new Open Item, not silently resolved); added the disabled Apple "Coming soon" placeholder button to the frontend spec and noted it in Future Scope here — the only piece of Apple in scope now, backend untouched. |
| 1.6 | 2026-08-14 | Claude (PM partner) | Five more open items resolved: email stays visible in the UI on `StubEmailProvider` for this pass, with `PostmarkEmailProvider` now a firm (not open-ended) prerequisite for this feature reaching Postgres/production, not an interim UI-hiding decision; Postmark is confirmed, closing the SES-vs-Postmark question; `pending_identity_verifications`' TTL is confirmed as one shared window for both triggers; pill-button ordering resolved (frontend spec, §9 pointer here); right-panel content confirmed as pending product-owner input rather than a generic design-brief placeholder. |
