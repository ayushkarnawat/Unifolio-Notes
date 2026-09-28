# Email Provider Alternatives to Postmark — Comparison

**Date:** 2026-09-21
**Why this exists:** Postmark's trial account is still restricted to same-domain-only
recipients (approval requested 2026-09-17, still pending as of this writing — 4+ days
with no ETA and no visibility into when/whether it clears). This compares realistic
replacements against your actual constraints: cross-domain OTP delivery must work
end-to-end, nothing else in the current auth flow should break, and it should fit your
existing AWS (`ap-south-1`, Route 53 for `unifolio.in`) setup.

**One structural fact that changes the risk profile of switching at all:** your code
already isolates the email provider behind one small interface —
`EmailProvider` (`backend/app/services/auth/email_provider.py`), selected by
`EMAIL_DELIVERY_MODE` via `get_email_provider()`. Swapping providers means writing one
new class with a `send_email(to, subject, body)` method and adding one `if` branch —
nothing in `otp.py`, the API routes, or the frontend needs to change for any of the
options below. This makes "switch provider" a genuinely small, low-risk change
regardless of which one you pick.

## Important honesty check before the table

**Almost every reputable transactional email provider gates new/unverified accounts
somehow** — this is industry-standard anti-abuse practice, not a Postmark-specific
flaw. The real differences are (a) *how* they gate you (domain-restricted vs.
recipient-allowlisted vs. time/volume-limited vs. verify-then-free), and (b) how fast
and predictable the path out of that gate is. That's the actual axis this comparison
is judging on, not "which provider has zero restrictions" — none of them truly do.

## Comparison table

| Provider | Cross-domain gate on a new account | Path out, and how predictable | Cost at your current volume (OTP-only, low hundreds/month) | Build+test+stage estimate | Verdict |
|---|---|---|---|---|---|
| **Amazon SES** | Sandbox mode: can only send to *individually verified* addresses/domains (stricter day-one than Postmark, ironically) | Official "Request production access" form (use-case + volume + bounce/complaint plan) reviewed by AWS Trust & Safety. Typically ~24h, some reports of a few days — but it's a defined, trackable request with a status, unlike Postmark's opaque pending review | **~$0.10/1,000 emails**, no monthly minimum — effectively pennies/month at your volume | **~2–3 working days** of actual effort (see breakdown below), production-access wait runs in parallel | **Recommended** |
| **SendGrid (Twilio)** | 60-day free trial, time/volume-limited (100/day via Marketing Campaigns), not a same-domain recipient restriction per SendGrid's own docs — cross-domain sending during the trial appears to work once domain auth (SPF/DKIM CNAMEs) is done. *Flag: this is inferred from secondary sources, not confirmed against SendGrid's primary docs for the transactional Email API specifically — verify directly before committing* | After 60 days, mandatory paid plan (no more free tier as of 2025) | **$19.95/mo minimum** (Essentials, up to 100K emails) regardless of your actual volume | ~1–2 days (mature SDK, well-documented domain auth) | Solid fallback if SES is ruled out for some reason |
| **Mailgun** | Free/sandbox-domain accounts restricted to 5 manually-added "Authorized Recipients" until a valid card is added — a real gate, comparable in spirit to Postmark's | Add a card → gate lifts immediately (not a manual review queue) | **$35/mo minimum** (Foundation) | ~1–2 days | Workable, but pricier than SES/SendGrid for no clear benefit here |
| **Resend** | Free tier (3,000/mo, 100/day cap) — no domain-based recipient restriction found; terms explicitly restrict *cold/bulk* email, not transactional OTP | No approval gate described; the 100/day cap is the practical limit, plenty for OTP volume today | **Free** at your volume, $20/mo (Pro) once you outgrow 100/day or 3,000/mo | ~1 day (newer, minimal API, less legacy config) | Attractive if you want fastest time-to-working and don't need AWS-native billing |
| **Brevo (Sendinblue)** | Free plan: 300 emails/day forever-free, contact-count limits tightened Oct 2025 but those apply to marketing lists, not transactional API sends | No restrictive recipient gate found for transactional sends | **Free** at your volume | ~1–2 days | Viable, less commonly used for pure transactional/OTP at scale |
| **MSG91** | India-based, no same-domain gate found; pricing is pay-as-you-go from the first email | None — starts working once configured | ₹0.35/email pay-as-you-go, or 5,000 free/mo on the free plan, then ~₹0.02–0.25/email at volume | ~1–2 days | Worth a specific look **because it also does SMS/WhatsApp OTP** — could let you consolidate the still-not-yet-built phone-OTP provider (per your own docs, that's a separate open task) onto the same vendor later |

## Recommendation: Amazon SES

Given "given my current infrastructure" is explicitly part of your ask, SES is the
clear fit, independent of the gate-severity question:

- **Same AWS account, same billing, same region (`ap-south-1`)** — no new vendor
  relationship, no new API token to generate and store in Secrets Manager. Auth is via
  IAM role, which is *more* secure than Postmark's bearer-token-in-env-var model and
  matches how the rest of your AWS infra is heading (per the Terraform Phase 0/1 work
  already planned).
- **By far the cheapest** at your volume — effectively free, vs. $20-35/mo minimums
  elsewhere for capacity you're nowhere near using.
- **DKIM/SPF setup is more mechanical, less error-prone than what just happened with
  Postmark's DMARC**: SES's "Easy DKIM" adds exactly 3 CNAME records, and the SES
  console has a one-click "verify this domain in Route 53" flow that writes them for
  you directly — no copy-pasting a value into a text box by hand (which is exactly
  what caused the two-DMARC-values bug you just fixed).
- **The exit-sandbox process is official and trackable** (a real AWS request with a
  status), vs. Postmark's opaque manual review that's now been pending 4+ days with no
  visibility into timeline.

### Effort breakdown for SES (est. ~2–3 working days total, excluding AWS's review wait which runs in parallel)

1. **Code (~0.5–1 day):** new `SesEmailProvider` class (boto3 `send_email`), added
   behind the existing `EmailProvider` Protocol/`get_email_provider()` factory in
   `email_provider.py` — same shape as the existing `PostmarkEmailProvider`, plus unit
   tests following the pattern already in `backend/tests/services/auth/test_email_provider.py`.
2. **IAM (~0.5 day):** attach an `ses:SendEmail`/`ses:SendRawEmail` policy to whatever
   role the backend runs under in staging/prod (ECS task role, EC2 instance role, or
   equivalent) — no secret to rotate or store.
3. **DNS (~0.5 day incl. propagation):** verify `unifolio.in` in SES (3 DKIM CNAMEs via
   the Route 53 one-click flow), optionally a custom MAIL FROM subdomain for stricter
   SPF alignment.
4. **Request production access (parallel, not sequential):** submit the form on day
   one alongside the code/DNS work — a clear use case ("transactional OTP emails, ~X
   per month, bounce/complaint handling via SES's own notification config") gets
   approved faster per AWS's own guidance.
5. **Testing (~0.5 day):** unit tests with a mocked boto3 client, then one real
   staging send to both a same-domain and a cross-domain (Gmail) address once
   production access clears.

### What doesn't change

- `otp.py`, the three API call sites in `auth.py`, and the frontend are all
  provider-agnostic already — this is purely a new class + one config branch, not a
  rework of the OTP flow.
- The same error-handling gap flagged separately (Postmark rejections currently
  crashing uncaught and masquerading as a CORS/network error to the frontend —
  see `Docs/orchestration/email-otp-send-failure-handling-handoff.md`) applies
  identically to *any* provider, SES included — worth fixing once, regardless of which
  provider you land on, so a future SES throttle/error also surfaces cleanly instead of
  looking like a network outage.

### If you want the fastest possible path with zero AWS review wait

**Resend** is the one candidate with no discovered approval gate at all for
transactional sends at your volume, is free at this scale, and has the lightest setup
of the group. The tradeoff: it's a separate vendor/API-key relationship (not
AWS-native), and it's a newer company with a shorter deliverability track record than
SES/SendGrid/Mailgun. Reasonable as a stop-gap if you want cross-domain OTP working
today while an SES production-access request is still in flight — since the
`EmailProvider` abstraction makes it cheap to build both and switch the `EMAIL_DELIVERY_MODE`
value later without re-touching the OTP logic itself.
