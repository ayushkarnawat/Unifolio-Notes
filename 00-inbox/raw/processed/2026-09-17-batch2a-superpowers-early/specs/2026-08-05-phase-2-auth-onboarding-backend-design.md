# Phase 2 (Backend) — Auth + Onboarding Design

## Purpose

Phase 1 (backend + frontend, merged to `main`) built CAS import end to end.
This is the next module: PRD-02's phone+OTP authentication and the
backend data/endpoints onboarding's questionnaire flow needs (investor
type, primary goal, household/family setup). Onboarding UI itself
(questionnaire screens, trust primer, family-setup UI) is Phase 2b, once
this API is live — matching the Phase 1 / Phase 1b split.

## Scope

**In scope:** OTP request/verify, session creation/refresh, onboarding
field updates on `User`, household-member CRUD.

**Explicitly out of scope, deferred:**
- PIN/biometric return-login (PRD-02 FR-2a) — deferred to a future
  Auth/Security PRD, per that PRD's own note.
- Full rate-limiting/lockout policy (IP-based limits, lockout duration) —
  same deferral. This plan only adds a minimal per-OTP-request attempt cap
  (see Security below), not the full policy.
- Real SMS delivery — dev-only stub this phase (confirmed with the user);
  a real provider (Twilio, MSG91, etc.) gets wired in once one is chosen.
- Onboarding UI — Phase 2b, a separate plan.
- The rest of PRD-03 (Main Dashboard) — only `/household-members` CRUD is
  built here, per `TDD-Unifolio.md`'s explicit ownership table assigning
  that endpoint to the Dashboard service; holdings/allocation/etc. stay
  out of scope.

## Service Ownership

Per `TDD-Unifolio.md`'s existing API-ownership table — no new service
invented, matching CLAUDE.md's "do not introduce... a service split not
already in that document":

- **Auth** (`backend/app/api/auth.py`, `backend/app/services/auth/`) — owns
  `otp_requests`, `sessions`, and `User`'s own fields (including onboarding
  state, since `User` is Auth's entity).
- **Dashboard** (`backend/app/api/dashboard.py`, `backend/app/services/dashboard/`)
  — owns `household_members` CRUD, per the TDD's explicit assignment
  (`/household-members` | Dashboard | PRD-02 FR-5, App Flow S7`).

## Endpoints

```
POST /auth/otp/request
  {phone_number}
  → creates OtpRequest (6-digit code, sha256-hashed, 5-min expiry)
  → dev-stub: response includes the raw OTP (never in production —
    gated behind a settings flag, off by default outside dev)

POST /auth/otp/verify
  {phone_number, otp}
  → validates against the latest unexpired, unlocked OtpRequest for that
    phone (hash match); creates User if new, fetches if existing;
    creates Session
  → {session_token, user_id, onboarding_step, onboarding_completed}

POST /auth/session/refresh
  (Authorization: Bearer <token>)
  → extends session.expires_at / last_active_at
  → confirmation response

PATCH /auth/me
  (Authorization: Bearer <token>)
  {onboarding_step?, investor_type?, primary_goal?}
  → updates the current user's onboarding fields (partial update)

POST /household-members
  (Authorization: Bearer <token>)
  {name, relationship, relationship_other_label?}
  → creates a household member scoped to the current user

GET /household-members
  (Authorization: Bearer <token>)
  → lists the current user's household members
```

A shared `get_current_user` FastAPI dependency (in `services/auth/`,
importable by both routers) extracts the bearer token from the
`Authorization` header, hashes it, and looks up the matching `Session` →
`User`. Both `/auth/me` and `/household-members` depend on it — no
endpoint in this plan trusts a client-supplied `user_id`.

## Data Flow

**Signup/login (first OTP verify for a phone number):**
1. `POST /auth/otp/request` — client sends phone number, gets back
   confirmation (+ raw OTP in dev).
2. `POST /auth/otp/verify` — client sends phone + OTP. No matching `User`
   exists yet → create one (`onboarding_step` starts null/unset). Create a
   `Session`, return the token.
3. Client uses the session token for every subsequent call.

**Resume (PRD-02 FR-8):** `User.onboarding_step` is read on login
(`/auth/otp/verify`'s response already includes it) — the frontend (Phase
2b) uses this to route to the right questionnaire step, not this plan's
concern beyond exposing the field.

**Family setup (PRD-02 FR-6):** Q1 (name) creates the first
`HouseholdMember` row with `relationship='self'` — per
`Database-Schema-Unifolio.md`'s explicit design ("including the primary
account holder... so aggregation logic treats every member uniformly").
Q4's "Family too" branch adds more `HouseholdMember` rows via the same
`POST /household-members` endpoint, one call per member added.

## Security

- **OTP hashing:** stdlib `hashlib.sha256`, not bcrypt/argon2. OTPs are
  short-lived (5 min), low-entropy 6-digit codes — not long-lived
  credentials needing expensive-to-brute-force hashing. No new dependency.
- **Session token:** `secrets.token_urlsafe(32)` generated per session,
  SHA-256-hashed for storage in `session_token_hash` (matching the schema's
  existing column name/intent) — the raw token is returned to the client
  exactly once, at verify time, and never persisted in plaintext.
- **Minimal guessing safeguard:** `OtpRequest.attempt_count` (existing
  schema column) increments on every failed verify against that request;
  at 5 failures, that specific `OtpRequest` is permanently rejected (a new
  `/otp/request` call is required). This is basic hygiene, not the
  deferred "full policy" — no IP tracking, no account lockout duration,
  no CAPTCHA.
- **No IDOR by construction:** every write in this plan (onboarding field
  update, household-member creation) is scoped to `get_current_user()`'s
  id, resolved server-side from the session token — never a body/query
  parameter. This is the real fix for the shape of gap Phase 1's Import
  Service had to work around with a dev-seeded `household_member_id`
  (tracked as a follow-up in `session.md`); real auth replaces that
  workaround going forward, though Import's own endpoints aren't touched
  by this plan.

## Testing

pytest, matching Phase 1's conventions:
- In-memory SQLite for service-level tests, session factory constructed
  with `autoflush=False` explicitly (matching production's real
  `SessionLocal` config) — Phase 1's final review found a real production
  bug hidden by a test/production `autoflush` mismatch; this plan builds
  the fix in from the start rather than discovering it in review.
- FastAPI `TestClient` for route-level tests (status codes, response
  shapes, auth-dependency enforcement — a request with no/invalid bearer
  token must 401, not 500 or silently succeed).

## Open Items Not Resolved Here

- Exact expiry duration for `Session` (PRD-02 doesn't specify a number) —
  a reasonable default (e.g. 30 days, refreshed on activity) will be
  chosen during planning and flagged there, not treated as a blocking
  question here.
- Whether `/auth/otp/request` should reject a request for a phone number
  with an already-active, unexpired `OtpRequest` (resend vs. always issue
  a new one) — a small behavioral choice, resolved during planning with
  the exact code, not a design-level fork.
