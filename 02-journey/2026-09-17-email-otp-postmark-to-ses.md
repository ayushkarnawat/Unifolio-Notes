# Email OTP goes live on Postmark, hits a trial-account wall, and is fully replaced by SES within a week

## For stakeholders

ADR-009 (2026-08-14) chose Postmark for sending the email login code, but
left it unbuilt — a placeholder that only worked in development. On
2026-09-17 the real thing shipped: emails actually left the building,
DNS was configured so they wouldn't land in spam, and a safety net was
added after an earlier mistake nearly sent ~86 test emails to real
inboxes. It looked done. Four days later it wasn't usable for real
users: Postmark's trial tier only delivers to the same email domain the
account is registered under, so it could email a `@unifolio.in` address
but not a user's Gmail — and the request to lift that restriction sat
with no answer for four days. Rather than wait indefinitely, the team
compared five alternatives and picked Amazon SES, already inside the
same AWS account as everything else. In the same window, a real bug
surfaced while testing this on the staging server: when a send failed,
the error was swallowed in a way that made the browser report a generic
network error instead of the real cause, and a failed attempt was still
being counted against the 60-second resend limit — both fixed together.
The infrastructure plan written the day before the cutover explicitly
said to keep Postmark wired in, dormant, as a rollback option — the team
changed course the very next day and removed it completely instead, on
the reasoning that a second, unused email-sending surface isn't worth
carrying. SES went live in production on 2026-09-23.

## Technical detail

### Intended outcome

Turn ADR-009's placeholder `EmailProvider` into a real, production-usable
implementation so email login works for actual users, not just in
development.

### What actually happened

**2026-09-17 — `PostmarkEmailProvider` shipped.** First real
(non-stub) implementation of the `EmailProvider` protocol ADR-009
specified. `email_delivery_mode` was split out as its own setting,
independent of phone/SMS's `otp_delivery_mode`, so the two channels
could be toggled separately. An autouse test fixture was added to guard
every test against silently picking up a live value from a local
`.env` file — added *because* roughly 86 tests had already, at some
earlier point, fired real Postmark requests by accident. Account setup:
sender `aditi.shanbhag@unifolio.in`, DKIM and Return-Path DNS records
added in Route 53, a "Request Approval" ticket filed with Postmark for
production sending. Two problems were found and fixed same-day: a 412
error from Postmark's same-domain sending restriction (workaround at
the time, not yet the real fix), and Microsoft 365's anti-spoofing
silently quarantining outbound mail with no bounce or error — fixed by
completing the DKIM setup. 655 backend tests passing; two clean
adversarial review rounds. Left explicitly open at this point: the
Postmark production-sending approval was still pending, there was still
no SMS provider, and the whole thing had only been tested locally, not
on a deployed environment.

**2026-09-21 — the trial-restriction wall, and the provider comparison.**
Four-plus days after filing, the Postmark approval request had no ETA
and no visibility into when — or whether — it would clear, and its
free/trial tier restricted delivery to the same domain as the sending
account, meaning it could not yet reach a real user's inbox at all. A
comparison of five providers (Amazon SES, SendGrid, Mailgun, Resend,
Brevo, MSG91) was written on cost, cross-domain gating, and setup effort.
**Amazon SES was recommended**: same AWS account and region as the rest
of the stack, ~$0.10 per 1,000 emails, IAM-role authentication (no new
secret to manage), an official trackable production-access request
process, and one-click DKIM setup through the SES console since the
domain was already in Route 53 — mechanically simpler and less
error-prone than the manual DNS copy-paste that had caused the Microsoft
365 quarantine issue four days earlier. Estimated at 2-3 days of work.
Resend was named as a zero-gate fallback if SES also stalled. The
comparison noted, as direct validation of ADR-009's original design
choice, that the `EmailProvider` abstraction made this swap "genuinely
small, low-risk" regardless of which provider was picked.

**Same window — a send-failure bug found live-debugging staging, fixed
alongside the SES work.** An unhandled exception on a Postmark send
rejection was escaping through the CORS middleware, so the browser
reported a generic `TypeError: Failed to fetch` — indistinguishable from
a real network problem — instead of surfacing that the upstream provider
had rejected the send. Separately, the `OtpRequest` database row was
being committed *before* the send was attempted, so a failed send still
started the 60-second resend cooldown, silently locking the user out of
retrying even though nothing had actually been sent. Fix: a new
`EmailSendError` exception type (kept distinct from
`NoEmailProviderConfiguredError`, which is left loud and unhandled on
purpose — a misconfigured environment should fail obviously), raised by
both providers on send failure, caught at three call sites in the auth
route and mapped to a `502` with a safe user-facing message; and the
request flow reordered so the send is attempted before the database
commit, so a failed send never creates a throttling row. No frontend
change was needed.

**2026-09-22 — SES infrastructure planned, with an explicit "keep
Postmark" recommendation.** A Terraform deploy runbook was written
covering IAM/task-role verification, image build and push, `tfvars`
additions, an additive-only plan/apply, a regression check while still
on Postmark, and a rollback procedure. Its own Step 8 was explicit:
**"Don't remove Postmark — keep `PostmarkEmailProvider` wired in,
dormant, as a documented rollback path."**

**2026-09-23 — the cutover executes, and reverses that recommendation.**
A companion execution guide (which itself states it supersedes the prior
day's runbook) confirms SES production access was approved that day
(50,000 emails/day, 14/second) and the cutover was carried out — but
**not** as the runbook had specified. Postmark was removed entirely:
commit `18c13b4` (`refactor(auth): remove Postmark provider`) and
`49fd1ae` (`refactor(infra): remove Postmark secrets`), both already
pushed to `feat/enhanced-ui` by the time this guide was written. The
guide carries its own sharp caution for the deploy step: the PAN
encryption key and lookup pepper (`TF_VAR_pan_encryption_key`,
`TF_VAR_pan_lookup_pepper` — see
[the PAN-persistence journey entry](2026-09-18-pan-persistence-and-cas-attribution.md))
must be **re-read from the existing `unifolio-staging-pan-keys` Secrets
Manager secret, never regenerated**, since regenerating either would
silently break decryption of every PAN already stored under the old
values. A separate manual step removed Postmark's now-unused DKIM and
Return-Path DNS CNAMEs, explicitly leaving Microsoft 365's and SES's own
DNS records untouched.

### Deviation (if any) — decision or response taken

Two, both recorded rather than smoothed over. First, ADR-009's original
choice of Postmark over SES (2026-08-14) is reversed five weeks later —
not because the original comparison was wrong at the time, but because a
trial-tier restriction that only became visible once real sending was
attempted made Postmark unusable for real users on a timeline the team
could plan around. Second, and narrower: the 2026-09-22 runbook's own
explicit instruction — keep Postmark dormant as a rollback path — was
overridden the very next day by the people executing the cutover, who
chose full removal instead. This is a same-week course-correction on an
operational plan, not a contradiction requiring resolution; the final,
executed state (full removal) is what's current and is what
[ADR-009's addendum](../03-decisions/ADR-009-transactional-email-provider.md)
already records.

### Result

Email OTP is live against Amazon SES in production as of 2026-09-23, not
Postmark. R-024 (email OTP could not work in production) is resolved.
The CORS-masking send-failure bug and the pre-send-commit throttle bug
are both fixed as part of the same window. One operational consequence
of the full-removal choice is now recorded as a risk: there is no live,
config-flag fallback if SES has an outage or is throttled — recovery
means redeploying an older image/task definition that still contains
Postmark code (see [R-067](../07-risks-and-debt.md)).

### Related

- [ADR-009](../03-decisions/ADR-009-transactional-email-provider.md) —
  the original Postmark decision and its 2026-09-28 addendum; this entry
  is the fuller account that addendum's evidence pointer referenced
- [R-024](../07-risks-and-debt.md) — resolved by this stage
- [R-067](../07-risks-and-debt.md) — new risk this stage creates: no
  live rollback path for email OTP post-removal
- Evidence: `08-evidence/documents/orchestration/email-otp-postmark-technical-documentation.md`,
  `08-evidence/documents/orchestration/email-provider-alternatives-comparison.md`,
  `08-evidence/documents/orchestration/email-otp-send-failure-handling-handoff.md`,
  `08-evidence/documents/orchestration/2026-09-23-ses-cutover-execution-guide.md`,
  `08-evidence/documents/orchestration/ses-terraform-deploy-runbook.md`
