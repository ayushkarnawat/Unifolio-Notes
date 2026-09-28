# Email OTP via Postmark — Technical Documentation

**Date:** 2026-09-17
**Branch:** `tasks`
**Status:** Working end-to-end in local development. Not yet production-ready — see "What's still open" at the end.

## 1. What this covers, in one paragraph

Unifolio already had a fully-built email OTP (one-time password) login/signup flow — the screens, the API, the code that generates and checks a 6-digit code — but it never actually emailed anyone. It just logged the code to the terminal for developers to read. This work made it send a *real* email, using a service called Postmark, and then separated email-sending from phone/SMS-sending so each can be turned on or off independently.

## 2. What existed before we started

- A user enters their email → gets a 6-digit code → enters the code → gets logged in. This entire flow (screens, API endpoints, the code that creates/hashes/expires/checks the OTP) already existed and already worked.
- The only missing piece: the actual "send an email" step was a stub — it just wrote the code to a log file instead of emailing it. Fine for a developer testing locally, useless for a real user.
- Phone/SMS OTP has the exact same situation today: it also only has this "stub" (log instead of send) — a real SMS provider hasn't been chosen or built yet. That's intentionally out of scope for this work and is a separate future task.

## 3. What we built

### 3.1 A real email sender (Postmark)

We added one new piece of code, `PostmarkEmailProvider`, that does exactly one job: take a "send this email" request and actually send it through Postmark's API. It slots into an interface (`EmailProvider`) that the existing code was already written to expect — so nothing about *how* OTP codes are generated, stored, or checked had to change. Only "how does the code actually get emailed" changed.

**Where:** `backend/app/services/auth/email_provider.py`

### 3.2 Independent on/off switches for email vs. phone

Originally there was one single setting controlling *both* channels — if you turned on real email sending, it also silently turned off the phone OTP's developer-convenience mode (which shows the code on-screen instead of texting it). That's a problem because email is ready to go live permanently, but phone isn't (no real SMS provider exists yet).

We split this into two independent settings:
- `OTP_DELIVERY_MODE` — controls phone/SMS. Stays `stub` (dev-only, shows the code on screen) until a real SMS provider is added later.
- `EMAIL_DELIVERY_MODE` — controls email. Set to `postmark` to send real emails.

Each channel now only looks at its own setting. Turning one on has zero effect on the other.

**Where:** `backend/app/services/auth/otp.py` (a small helper function decides which setting to check, based on whether the request is for email or phone), `backend/app/config.py` (the two settings themselves).

### 3.3 A safety net for automated tests

Once `EMAIL_DELIVERY_MODE=postmark` is left on permanently on a developer's machine, there's a real risk: every time someone runs the automated test suite (`pytest`), any test that doesn't explicitly say "use stub mode for this test" would accidentally try to send a *real* email through Postmark. This actually happened once during this work — about 86 tests failed and the test run fired real requests at Postmark's servers, wasting quota.

We fixed this permanently: every test now automatically starts in `stub` mode by default, no matter what's in a developer's personal settings file. A test that specifically wants to test the real-Postmark code path still can (it just says so explicitly), but nothing happens by accident anymore.

**Where:** `backend/tests/conftest.py`

## 4. Setting up Postmark (the account side, not code)

This part happened outside the codebase, in the Postmark and AWS (Route 53 DNS) dashboards:

1. **Created a Postmark account** (free tier: 100 emails/month, no expiry).
2. **Registered a sender address** (`aditi.shanbhag@unifolio.in`) and confirmed it via the email Postmark sent.
3. **Got a Server API Token** — this is the secret credential the backend uses to authenticate with Postmark. It lives only in a local, never-committed file (`backend/.env`) — never in the codebase itself.
4. **Added domain authentication (DKIM + Return-Path) in Route 53** — this is what tells email providers "Postmark really is allowed to send email as unifolio.in." Two new DNS records were added:
   - A DKIM record (a cryptographic signature key)
   - A Return-Path record (where bounce notifications go)

   Neither of these touched or conflicted with `unifolio.in`'s existing Microsoft 365 mail setup (MX records, existing SPF, existing DMARC) — they're separate, new records.
5. **Clicked "Request Approval"** on Postmark — new Postmark accounts start in a restricted trial mode (see problem #1 below); this asks Postmark's team to lift that restriction. **Still pending as of this writing.**

## 5. Problems we hit along the way, and how each was solved

This is the "why did it take several rounds to get working" part — useful context for understanding what's actually happening under the hood.

### Problem 1: "Client error 412... recipient addresses must share the same domain"

**What happened:** Testing with a personal Gmail address failed immediately.
**Why:** New Postmark accounts are restricted — until Postmark's team approves the account, you can only send to email addresses on the *same domain* as your sender (i.e., only to other `@unifolio.in` addresses, not Gmail/Outlook/etc.).
**Fix:** Clicked "Request Approval" (pending), and in the meantime tested using `@unifolio.in` addresses only, which are allowed even before approval.

### Problem 2: Email "sent successfully" but never arrived (not even in spam)

**What happened:** Postmark said the email was sent, and even showed Microsoft's mail server accepting it — but it never showed up anywhere, not inbox, not junk.
**Why:** Microsoft 365 has anti-spoofing protection. A message claiming to be "from your own domain" that isn't cryptographically proven to actually be authorized (which is what DKIM does) looks exactly like an attacker impersonating your own company — so Microsoft quarantines it silently, in a place your personal Junk folder doesn't even show (only visible to an admin). `unifolio.in` already had a strict anti-spoofing policy (DMARC) set up for its Microsoft 365 mail, which made this worse, not better, until Postmark was properly authorized.
**Fix:** The DKIM + Return-Path DNS records described above. Once Postmark could cryptographically prove "yes, this really is authorized to send as unifolio.in," Microsoft stopped quarantining it. No change to the existing DMARC policy was needed — it was already correctly set up, it just needed Postmark to pass its check, which DKIM provided.

### Problem 3: A completely unrelated database error during testing

**What happened:** While testing phone OTP login, the app crashed with `no such column: users.pending_deletion`.
**Why:** This had nothing to do with any of the OTP work. It's a housekeeping issue — a local development database file was several versions behind the current codebase (missing some structural updates/"migrations" that were made for an unrelated feature, account deletion, earlier).
**Fix:** Ran the standard "bring the database up to date" command (`alembic upgrade head`), which applied the 7 missing updates. Confirmed this was pure local-environment drift, not a bug introduced by this work.

## 6. Testing and verification

- Every code change followed test-first practice: a failing test was written before the corresponding code, then the code was written to make it pass.
- Two rounds of independent adversarial code review were run (a fresh reviewer with no context, specifically looking for bugs/security issues/scope creep) — both came back with no real issues found.
- The full backend automated test suite (655 tests) passes with zero failures after all of this work.
- The actual feature was also manually tested end-to-end in the running app by the user: email OTP arrives via Postmark and logs the user in; phone OTP still shows the developer code on-screen and logs the user in.

## 7. How to operate this (for reference)

Local settings file (`backend/.env`, never committed to the codebase):

| Setting | What it does | Current value |
|---|---|---|
| `OTP_DELIVERY_MODE` | Controls phone/SMS OTP | `stub` (shows code on screen, no real SMS) |
| `EMAIL_DELIVERY_MODE` | Controls email OTP | `postmark` (sends real email) |
| `POSTMARK_API_TOKEN` | Postmark account credential | set to the real token |
| `POSTMARK_FROM_EMAIL` | The "from" address emails are sent as | `aditi.shanbhag@unifolio.in` |

To add a real SMS provider later: the same pattern used for Postmark applies — write one new class that knows how to send an SMS, and give `OTP_DELIVERY_MODE` a new recognized value for it. Nothing else in this system needs to change for that.

## 8. What's still open (not yet production-ready)

- **Postmark account approval is still pending.** Until Postmark approves the account, email OTP only works for `@unifolio.in` addresses — a real user with a Gmail/Outlook/etc. address cannot receive an OTP email yet. This is the main blocker before real users can use this feature.
- **No real SMS/phone provider exists yet.** Phone OTP is intentionally still developer-only (shows the code on-screen). A future task will choose a provider (e.g. Twilio, MSG91) and wire it in the same way Postmark was.
- **This has only been tested locally** (a developer's own machine, local database). None of this has been deployed to AWS/production yet — that's a separate, later step in the project's overall rollout plan.
