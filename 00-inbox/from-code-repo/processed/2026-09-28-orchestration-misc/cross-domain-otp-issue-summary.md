# Cross-Domain OTP Email — Problem, Cause, Alternatives, and Recommendation

**Date:** 2026-09-21

## The problem

When a user logs in or signs up using email OTP on staging, it works perfectly for
`@unifolio.in` addresses. But if the user enters any other email (like a personal
Gmail address), it fails. The user sees "Unable to connect to the server" — which
sounds like a network or CORS problem, but it isn't.

## Why it's happening

Two separate things are going on:

**1. The real cause.** We use Postmark to send OTP emails. New Postmark accounts are
restricted: until Postmark manually reviews and approves the account, it can only send
to email addresses on the *same domain* as our verified sender — only `@unifolio.in`,
nothing else. We requested approval on 2026-09-17. It's still pending, with no fixed
timeline. This is an account-level rule Postmark enforces, not a problem with our DNS
or our code.

**2. A separate bug that hides the real cause.** When Postmark rejects a send, our
backend doesn't handle the error properly. The failure crashes uncaught, which strips
the response of its normal security headers, which makes the browser show a generic
"can't connect" message instead of the real reason. This is worth fixing regardless of
which email provider we end up using, since it will hide any future email-sending
failure the same way. (Full technical detail:
`Docs/orchestration/email-otp-send-failure-handling-handoff.md` — not yet implemented.)

**Also found, and already fixed:** our domain had two conflicting DMARC (anti-spoofing)
records instead of one, which could have made mail providers ignore our DMARC setup
entirely. That's fixed and confirmed live — but it was a separate real bug, not the
cause of the cross-domain problem above.

## Alternatives considered

| Option | Verdict |
|---|---|
| Wait for Postmark's approval | No fixed timeline, entirely out of our control |
| **Amazon SES** | Best fit — see recommendation below |
| SendGrid, Mailgun, Resend, Brevo | All workable, but cost more per month than SES for no real benefit at our email volume |
| MSG91 | Works, and could later also handle phone/SMS OTP on the same vendor — worth a future look, not urgent now |
| **Self-hosted open source (e.g. "Postal")** | Trades a solvable waiting problem for a harder one: we'd have to build our own sending reputation from scratch, and real inbox providers (Gmail, Outlook) treat unproven senders as suspicious by default. Riskier for something time-sensitive like OTP, plus ongoing server upkeep forever. Not recommended. |
| **Gmail API / Google Workspace** | Doesn't fit — our company email runs on Microsoft 365, not Google Workspace, so this would mean migrating our real email system just to send OTPs. It's also built for one person's mailbox (2,000 emails/day cap, and Google can suspend the account for exceeding it), not for automated app sending. Not recommended.

Full comparison with pricing details: `Docs/orchestration/email-provider-alternatives-comparison.md`

## Proposed solution

**Switch to Amazon SES** for sending OTP emails.

Why:
- We're already on AWS, so this fits what we have — no new vendor account, and AWS
  handles login/security for us (via IAM), instead of us managing a separate password
  the way we do for Postmark today.
- Cheapest option by far at our size — a fraction of a dollar a month, versus
  $20–35/month minimums elsewhere.
- Its version of the "new account" restriction (called sandbox mode) is lifted through
  an official AWS request that's typically resolved in about a day — not an
  open-ended wait like Postmark's.
- The required DNS setup is safer than what we just went through with Postmark's
  DMARC record — AWS can add the records to Route 53 automatically with one click,
  instead of typing them in by hand.

**Estimated effort:** about 2–3 working days of work (code + AWS/DNS setup + testing),
with AWS's approval running in the background the whole time rather than blocking us.

No code has been changed yet. A full step-by-step migration plan is the next thing to
write, once we're ready to proceed.
