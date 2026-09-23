# INV-012: Two Critical OTP-verification account-binding bugs found in adjacent auth work

Status: Both found and fixed same-day; both confirmed closed by a scoped
re-review. Date investigated: 2026-08-17.
Related: [02-journey/2026-08-17-email-password-auth-built-and-reversed.md](../02-journey/2026-08-17-email-password-auth-built-and-reversed.md),
[ADR-008](../03-decisions/ADR-008-phone-anchored-multi-method-identity.md),
[INV-006](INV-006-provider-precedence-keyerror.md),
[R-031](../07-risks-and-debt.md), [R-024/R-025](../07-risks-and-debt.md)

## For stakeholders

Two separate one-time-password (OTP) features, built back-to-back on the
same day, were each found — through a mandatory second-pair-of-eyes review
step that runs before any auth-related work is marked finished — to have
the same underlying class of mistake: the code correctly checked that a
person had typed a valid OTP, but did not correctly check that the OTP they
typed actually belonged to the account record it was about to modify. In
both cases this could have let someone with a legitimate, valid OTP for
their own email address apply it to a different account instead of their
own — the first case could flip a stranger's account into a "verified"
state without their consent, the second, more serious case could let an
attacker use their own valid OTP to pre-claim a victim's email address
against the attacker's own account before the real owner ever signed up
with it. Both were caught before ever reaching production, both were fixed
the same day with a targeted, tested code change, and both fixes were
independently re-checked and confirmed to close the specific exploit with
no side effects on the legitimate flow. No evidence exists that either bug
was ever exploited — they were found by the project's own internal review
process, not by an external report.

## Technical detail

### Shared root cause pattern

Both bugs share the same shape: a request handler verifies that a supplied
OTP is cryptographically/temporally valid for *some* record, but does not
verify that the record the OTP resolves to is the same record the caller
is claiming to act on. "OTP is valid" and "OTP belongs to the identity
being modified" were treated as the same check when they are not.

### Bug 1 — `email-otp-signup`: missing verified-email-to-pending-record binding check

Found: 2026-08-17, during the mandatory adversarial-review gate for the
`email-otp-signup` task (inline email-OTP replacing link-based email
confirmation; new migration 0007, `otp.py` channel generalization, new
`/auth/email-otp/verify` endpoint, sequenced before the existing phone
gate). The review (a Claude subagent using `feature-dev:code-reviewer`,
Codex unavailable this session per the project's documented no-codex
fallback) found **1 Critical**: `/auth/email-otp/verify` had no binding
check between the verified OTP's own email and the pending signup record's
email — an attacker could apply their own genuinely-valid OTP to an
arbitrary victim's `pending_token`, marking the victim's pending signup as
email-verified without the victim ever having proven ownership of that
email.

Fix (same day, implemented directly by the orchestrator under this
project's "review-loop fix authorship" convention rather than
re-dispatched): `mark_pending_email_verified` was changed to take and
check a `verified_email` argument against `pending.email`, raising on
mismatch; the route was updated to pass `body.email` through. Test-driven:
a failing test reproducing the exact exploit was added first (confirmed
red — the vulnerable code returned 200 instead of 401), then the fix was
applied, then confirmed green. Full backend suite: 481 passed / 2 skipped
(+2 from a 479 baseline, zero regressions). A scoped re-review confirmed
the fix closes the exploit with no bypass, and that the existing email
normalization logic was already correctly shared between the two paths (so
the fix didn't introduce a second inconsistency).

### Bug 2 — `remove-password-auth`: step-up pre-emptive account-claim vulnerability

Found: 2026-08-17, same day, during the mandatory adversarial-review gate
for the immediately-following `remove-password-auth` task (migration 0008;
`EMAIL_OTP`/`EMAIL_PASSWORD` provider swap; a three-way `/auth/email-otp/verify`
branch needed to keep `LinkAccountPrompt.tsx`'s step-up re-authentication
flow correct — a naive two-way branch was the orchestrator's own first
design and was caught and corrected during spec-writing, before dispatch,
because it would have misrouted the step-up case into the phone-gate path).
This second review (again a Claude subagent, Codex still unavailable) found
a **second Critical**, explicitly assessed as worse than the first: the
step-up branch looked up an existing identity by the just-verified email,
then attached whatever `pending_token` the caller supplied to it — for a
fresh-signup token (`matched_user_id` NULL, a self-chosen email with no
ownership check performed at creation time), this let an attacker
pre-claim an arbitrary victim's email address onto the attacker's own
account, using the attacker's own unrelated, genuinely-valid OTP. Unlike
Bug 1 (which flipped a verification flag on someone else's record), this
one let an attacker bind a victim's email to the attacker's own account
before the victim ever attempted to sign up with it.

Fix (same day, also implemented directly by the orchestrator): a new
read-only `peek_pending_matched_user_id` helper was added; the step-up
branch now dispatches on the pending token's own `matched_user_id` field
(trustworthy — only ever set by `resolve_new_verified_identity` against an
independently-verified email) instead of doing a fresh lookup keyed on the
caller-claimed email. Test-driven: the exploit was reproduced as a failing
end-to-end test first (confirmed red — 200 instead of 401), then fixed,
then confirmed green, plus 3 new unit tests for the helper itself. Full
backend suite: 449 passed / 2 skipped (+4, zero regressions — note the
lower absolute count than Bug 1's 481 reflects `remove-password-auth`
having since removed the password-auth test paths entirely, not a
regression). A scoped re-review confirmed the fix closes the pre-emptive
claim exploit and that both the step-up path and fresh-signup path remain
correct.

### Why this is logged as one investigation, not two isolated fixes

Both bugs were introduced in the same narrow window (auth-provider work
done back-to-back on 2026-08-17), both were missed by the implementing
agent (a Claude subagent, in both cases, with Codex unavailable that
session) and both were only caught by the project's separate, mandatory
adversarial-review gate — not by the implementer's own testing. That
repetition is itself the finding worth recording: OTP-verification
endpoints that resolve to an *existing or pending record by a caller-
supplied token* are a recurring blind spot for missing binding checks, and
any future OTP-adjacent endpoint (e.g. phone-OTP, future 2FA) should be
reviewed specifically for this pattern rather than assumed safe because
"the OTP itself was checked correctly."

### What remains unverified

This investigation is scoped to what the source delegation record confirms
directly: both bugs were found, fixed same day, and each fix was confirmed
closed by a scoped re-review with a real test reproducing the exploit
before the fix and passing after. No production incident or external
report is referenced in the source material — there is no evidence either
bug was ever exploited outside the project's own internal review process.
Whether the `remove-password-auth` change (migration 0008, dropping
password storage) was ever deployed to a live environment is addressed
separately in `07-risks-and-debt.md`'s R-031 update and the related
journey entry, not here.

### Evidence

- `08-evidence/documents/orchestration/email-otp-signup-handoff.md`
- `08-evidence/documents/orchestration/remove-password-auth-handoff.md`
- `08-evidence/documents/orchestration/delegation-log.md`, entries dated
  2026-08-17 for `email-otp-signup` (lines ~314-319) and
  `remove-password-auth` (lines ~320-325)
