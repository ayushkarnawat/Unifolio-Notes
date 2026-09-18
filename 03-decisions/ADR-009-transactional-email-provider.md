# ADR-009: Transactional email provider — Postmark, behind a provider abstraction

Status: Accepted — decided, not implemented
Date: 2026-08-14
Related: ADR-008; `02-journey/2026-08-14-multi-method-auth-and-the-analytics-frontend.md`

## For stakeholders

Adding email one-time codes to login means Unifolio needs to actually send
email, reliably and fast — a code that arrives three minutes late is a
failed login. Four providers were compared on cost and on how well they
handle this specific kind of message. Postmark was chosen: it is built
around transactional delivery speed rather than marketing campaigns, and at
Unifolio's volumes the cost difference against the alternatives is small
enough not to drive the decision. The important caveat: **no email is
actually being sent yet.** The code that would send it sits behind a small
interface with a do-nothing stub implementation, so login by email works in
development but not in production until a provider is wired up. That
remaining work is deliberately small and isolated.

## Technical detail

### Context

ADR-008 adds email+OTP as an entry method. A one-time code is the most
delivery-sensitive message class there is: late is the same as failed, and
landing in spam is the same as failed. The provider choice is therefore a
real decision and not a default.

### Decision drivers

- Transactional delivery latency and inbox placement, not campaign features.
- Cost at low volume, with a credible path as volume grows.
- Setup effort — an early-stage team should not be configuring a deliverability
  programme to send a six-digit code.
- Replaceability: whatever is chosen must not leak into the auth service's
  logic.

### Options considered

The design compares four providers with a cost table. Summarised by
character rather than by restating figures that will age:

#### Option 1: Amazon SES
Advantages: lowest per-message cost by a wide margin; already inside the AWS
account the rest of the stack uses (ADR-003, ADR-005).
Disadvantages: the most setup and the most deliverability responsibility
carried in-house; sandbox removal and reputation management are the team's
problem.

#### Option 2: Resend
Advantages: modern developer experience, quick to integrate.
Disadvantages: the youngest option, with the least track record on the one
attribute that matters here.

#### Option 3: SendGrid
Advantages: long-established, large scale.
Disadvantages: a marketing-first product whose shared-IP transactional
deliverability is its weakest point.

#### Option 4: Postmark (chosen)
Advantages: explicitly built for transactional mail, with separate
transactional and broadcast streams; strong deliverability reputation;
minimal setup.
Disadvantages: higher per-message cost than SES; an additional vendor
outside the AWS account.

### Decision

Postmark, reached through an `EmailProvider` protocol so the concrete
provider is one swappable implementation. Version 1 ships with the stub
implementation only — the plan explicitly forbids writing a real Postmark
implementation or any live sending call.

### Consequences

Positive:
- The auth service never names a vendor; swapping providers touches one file.
- Development and tests need no network and no credentials.
- The decision is made and recorded, so it is not re-litigated at wiring time.

Negative:
- Email login cannot work in production until the real implementation exists.
  See R-024.
- A vendor outside the AWS account, with its own billing and its own
  availability.
- The cost comparison in the source is a point-in-time snapshot of published
  pricing and should be re-checked before signing up.

### Validation

None. No provider integration exists to validate. The stub is exercised by
the auth test suite; nothing tests real delivery.

### Evidence

- `08-evidence/documents/specs/2026-08-14-multi-method-auth-design.md` (provider
  comparison and cost table)
- `08-evidence/documents/plans/2026-08-14-multi-method-auth-backend-plan.md`
  (Global Constraints: stub only)
