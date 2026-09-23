# Email and password authentication, built in full and reversed the same day

## For stakeholders

On 2026-08-17 Unifolio replaced its email one-time-code sign-in with a
conventional email-and-password signup, and built the whole thing: a database
migration, a password-hashing dependency, five new API endpoints, two new
tables, confirmation and password-reset email flows, and the deletion of the
old email-code screens. Management then reversed the decision the same day.
The product's final state is passwordless — phone code, email code, or Google,
all converging on a verified phone number — and the password tables were
dropped again by later migrations. The vault already recorded that reversal;
what this stage adds is the scale of what was actually built and thrown away
in between, and one defect that the work surfaced and fixed on the way through
(a crash reachable by any user who signed up with the new method).

## Technical detail

### Intended outcome

Add `EMAIL_PASSWORD` as a third identity provider alongside phone-OTP and
Google, per the same-day revision of PRD-02 FR-2, without disturbing the
mandatory verified-phone anchor established in
[ADR-008](../03-decisions/ADR-008-phone-anchored-multi-method-identity.md).

### What actually happened

The design spec settled the contested points before implementation:

- **bcrypt, not Argon2id**, via `passlib[bcrypt]` — a new dependency. The
  spec's reasoning was maturity and operational familiarity over marginal
  hardening.
- **The `EMAIL_OTP` enum value was kept**, not removed, even though its code
  path was being deleted. PostgreSQL enums grow cheaply and shrink expensively;
  leaving the value in place costs nothing and keeps existing rows valid.
- **Two endpoints, not one auto-detecting endpoint** — separate signup and
  login routes rather than one route that infers intent from whether the
  account exists.
- **Anti-enumeration by always returning 200** on password-reset requests, so
  the response cannot be used to test whether an email is registered. The one
  deliberate exception: a distinct `403` for "correct password, but email not
  confirmed", which reveals nothing an attacker who already has the password
  does not know.
- **A password-signup email is always recorded unverified** (spec §4a). This
  was a direct guard against re-opening the trust problem the spec calls
  "Critical Finding 1" — treating a self-asserted email as proof of identity.
  The spec traces the resulting account-squatting scenario and concludes it is
  a nuisance only, because the verified phone number remains the hard bar.
- **Completing a password reset also confirms the email** (spec §4c), because
  possession of the mailbox has just been demonstrated.
- **Step-up linking was explicitly declared out of scope** (spec §4d).

The backend plan then executed in full: migration `0006_email_password_auth`
added `auth_identities.password_hash`, `auth_identities.email_confirmed_at`,
`pending_identity_verifications.password_hash`, and the tables
`password_reset_tokens` and `email_confirmation_tokens`; it dropped
`otp_requests.email` and the `ck_otp_requests_exactly_one_identifier`
constraint, and restored `phone_number` to `NOT NULL`. Routes
`/auth/signup/email`, `/auth/login/email`, `/auth/password/forgot`,
`/auth/password/reset` and `/auth/email/confirm` were added. Reset tokens are
stored SHA-256-hashed with a 30-minute time-to-live.

The frontend plan executed in full as well: `EmailOtpVerify.tsx` was deleted,
`"email_otp"` was removed from `AuthEntryFlow.tsx`'s `Step` union, the
`sendEmailOtp`/`verifyEmailOtp` client calls were replaced by
`signupEmail`/`loginEmail`, and a `confirmationPendingEmail` banner was added.

Two things surfaced that were not about authentication at all. The plan
records a standing rule never to run `git add -A` in this repository, after a
staging attempt pulled in roughly 295 files of CRLF line-ending noise; and a
fresh-virtual-environment install check was added to the workflow after a bug
in which a dependency (`requests`) was used without being declared explicitly.

### Deviation — decision or response taken

Two deviations, both recorded rather than smoothed over.

**A reachable crash was found by reading, not by a failure.** Primary-identity
selection in the auth service picks the minimum of the user's identity list
keyed by `PROVIDER_PRECEDENCE`. The list passed in is unfiltered and the
precedence map had no entry for the newly-added `EMAIL_PASSWORD` provider, so
any user whose identities included one would hit a `KeyError`. See
[INV-006](../04-investigations/INV-006-provider-precedence-keyerror.md).

**A known limitation was shipped deliberately.** `users.email` is never
backfilled for `EMAIL_PASSWORD` identities, so `/auth/me` returns a null email
for a user who has fully confirmed their email address. The plan names this as
a known limitation rather than fixing it. Tracked as R-031, with a
verification flag — the same-day reversal may have removed the code path
entirely, which would moot it.

### Result

Built and then reversed. The vault's existing `decisions-log.md` entry for
2026-08-17 records the reversal chain: PRD-02 FR-2 revised to email +
password, then reversed to email + OTP by management decision, final state
phone + OTP / email + OTP / Google on a mandatory verified phone, with
password storage removed by migrations `0007`–`0008`. This stage supplies the
missing middle of that story — the reversal was not a paper revision, it
discarded a completed implementation on both sides of the stack.

One loose thread is recorded rather than resolved: the 2026-08-19 auth panel
plan declares an `AuthStep` union that **still includes `"email_otp"`**, two
days after the frontend plan removed it. Either that work was on a branch that
had not merged, or the reversal had already restored the email-OTP path by
then. No evidence in this batch settles which. See §4, contradiction C3.

### Related

- ADR-008 — phone-anchored multi-method identity (appended note proposed)
- INV-006 — a reachable `KeyError` in primary-identity selection
- R-031 — `users.email` never backfilled for email+password identities
- `decisions-log.md` 2026-08-17 — the reversal, recorded at the time
- Evidence: `08-evidence/documents/specs/2026-08-17-email-password-signup-design.md`
- Evidence: `08-evidence/documents/plans/2026-08-17-email-password-signup-backend.md`
- Evidence: `08-evidence/documents/plans/2026-08-17-email-password-signup-frontend.md`

## Addendum — 2026-09-23 (from batch 4c orchestration ingestion): the migration `0007`/`0008` split, and two Critical bugs found on the way

This entry's "Result" section already named migrations `0007`-`0008` as
having removed password storage, sourced from `decisions-log.md`'s
summary-level entry. Later-ingested source material distinguishes what
each migration actually did, and records two related security findings
from the same day that this entry did not previously cover:

- **Migration `0007`** belongs to a *different*, earlier same-day task
  (`email-otp-signup`): replacing the old link-based email confirmation
  with an inline email-OTP step, sequenced before the existing phone
  gate — not itself the password-removal migration.
- **Migration `0008`** is the actual password-removal migration described
  in this entry's "What actually happened" section: it drops
  `auth_identities.password_hash`, `auth_identities.email_confirmed_at`,
  `pending_identity_verifications.password_hash`, and the
  `password_reset_tokens` table outright, and benches `EMAIL_PASSWORD` in
  favour of reactivating `EMAIL_OTP`.

Both `email-otp-signup` (migration 0007) and `remove-password-auth`
(migration 0008) each had a **Critical, account-takeover-adjacent OTP
account-binding bug** found by this project's mandatory adversarial-review
gate and fixed the same day, 2026-08-17 — a repeatable failure pattern
(missing binding checks between a verified OTP and the record it's
applied to) worth its own investigation entry rather than a passing
mention here. See [INV-012](../04-investigations/INV-012-otp-verification-account-binding-bugs.md)
for full technical detail on both bugs and their fixes.

### Addendum evidence

- `08-evidence/documents/orchestration/email-otp-signup-handoff.md`
- `08-evidence/documents/orchestration/remove-password-auth-handoff.md`
- `08-evidence/documents/orchestration/delegation-log.md` (2026-08-17 entries)
