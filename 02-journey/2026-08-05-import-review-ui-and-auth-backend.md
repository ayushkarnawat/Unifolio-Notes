# Import Review UI and Auth Backend

Date: 2026-08-05
Status: Complete

## For stakeholders

With a working import API, two things were built on the same day: the screens
a user actually sees when uploading a CAS statement, and the login and
onboarding machinery behind them.

The import screens were built with one rule driving most of the design — the
app must never quietly guess. If the system is unsure which fund a line item
refers to, or cannot tell whether a holding is a Direct or a Regular plan,
the Confirm button stays disabled until a human resolves it. The server
refuses the same cases independently, so the guarantee holds even if someone
bypasses the UI.

The auth work built phone-number-plus-one-time-code login. It deliberately
does not send real text messages yet — the code is echoed back in the
response in a development-only mode — because choosing an SMS provider is a
separate decision. The most valuable thing on this day was not a feature at
all: a review of the previous phase found a real production bug that the
test suite had been hiding, because tests and production were configured
differently in one subtle way. The fix was made a standing rule rather than
a one-off patch.

## Technical detail

### Intended outcome

**Phase 1b** — the Import Review frontend: App-Flow screens S8–S12 (Upload,
Parsing, Review, Error, Confirmed) as a self-contained React feature talking
to the live parse and confirm endpoints.

**Phase 2 backend** — phone+OTP authentication (PRD-02 FR-2) plus the
endpoints onboarding needs: session management, onboarding field updates on
`User`, and household-member CRUD. No new tables and no migration — the
required tables already existed from Phase 0.

### What actually happened

Both completed. Design decisions worth preserving:

**Import Review frontend.**
- One stateful parent component owns a step enum and the current
  preview/confirm/error data; five child screens render off it. No router,
  no context, no state library — the flow is linear and short-lived. A
  router was explicitly considered and rejected as premature.
- Styling is CSS Modules over design tokens exposed as CSS custom
  properties. A single global stylesheet was considered and rejected.
- `household_member_id` comes from a dev-seeded environment variable, never
  a UI field, because no auth existed yet at the time this screen was built.
- Money, unit and NAV values arrive from the API as strings and are
  displayed as-is, never parsed into a JavaScript number — the frontend
  mirror of the backend's `Decimal`-everywhere rule.
- Confirm is disabled client-side until every low-confidence match and every
  `unclassified` plan type has an override filled in. The server's 409 is
  the backstop, not the mechanism.
- A four-way error taxonomy is routed explicitly: parse failure, scheme
  confidence failure, session-not-found, and network failure each have their
  own screen state and their own test.
- Persisting in-flight state to `sessionStorage` was considered and
  rejected; a reload restarts the flow.

**Auth and onboarding backend.**
- Two services, both already defined in the TDD's ownership table — no new
  service invented. Auth owns OTP, session and user-profile logic. Dashboard
  owns household-member CRUD only.
- OTP codes are hashed with the standard library's SHA-256, deliberately not
  bcrypt or argon2: they are short-lived, low-entropy codes, not long-lived
  credentials, and a deliberately slow hash on a six-digit code buys
  nothing.
- Session tokens are opaque random strings, stored only as a SHA-256 hash,
  and returned to the client exactly once.
- No IDOR by construction: every onboarding and household-member write
  resolves the acting user from the session token via a shared dependency,
  never from a request body or query parameter.
- A minimal per-request attempt cap (5) was added, being what the schema's
  existing `attempt_count` column already implied. Full rate-limiting and
  lockout policy stays deferred to a future Auth/Security PRD.
- A `GET /auth/me` route was *not* added despite being obviously useful,
  because it was not in the approved design. Recorded because the restraint
  is the point.

### Deviation — decision or response taken

| Deviation | Response |
|---|---|
| Phase 1's final review found a real production bug hidden by a test/production `autoflush` mismatch | Made a standing rule: test sessions must be constructed with the same `autoflush=False` setting production uses. Built into this plan from the start rather than patched after |
| No SMS provider chosen | A development stub delivery mode that echoes the OTP back; flipping to a real provider is an isolated follow-up, not a redesign. Recorded as R-025 |
| No auth existed when the import UI was built | `household_member_id` sourced from a dev-seeded environment variable, removed once Phase 2b wires real sessions |
| Two design open items left unanswered | Session TTL as a concrete number, and whether a resend issues a new OTP or reuses the pending one — both flagged in the design doc and not resolved there |

### Result

A working end-to-end import path for a single seeded user, and a login and
onboarding API ready for the Phase 2b UI. Deferred with reasons recorded:
AMFI-override UX beyond a plain text field, real navigation from the
Confirmed screen to a Dashboard that did not yet exist, a manual dark-mode
toggle, PIN/biometric return-login, and full rate-limiting policy.

### Related

- [Decisions log](../03-decisions/decisions-log.md) — 2026-08-05 entries
- [Frontend composition](../06-architecture/frontend-composition.md)
- [API surface](../05-docs/reference/api-surface.md)
- [Risks and debt](../07-risks-and-debt.md) — R-025
- Sources: `08-evidence/documents/plans/2026-08-05-phase-1b-import-review-frontend.md`,
  `08-evidence/documents/specs/2026-08-05-import-review-frontend-design.md`,
  `08-evidence/documents/plans/2026-08-05-phase-2-auth-onboarding-backend.md`,
  `08-evidence/documents/specs/2026-08-05-phase-2-auth-onboarding-backend-design.md`
