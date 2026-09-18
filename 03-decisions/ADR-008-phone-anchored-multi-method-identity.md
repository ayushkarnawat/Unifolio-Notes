# ADR-008: Phone-anchored multi-method identity, with non-silent account linking

Status: Accepted
Date: 2026-08-14
Related: `02-journey/2026-08-14-multi-method-auth-and-the-analytics-frontend.md`; supersedes PRD-02 FR-2b; partially overrides ADR-001

## For stakeholders

Unifolio started with one way in: a phone number and a one-time code. Users
expect Google sign-in, and email is easier to type than a phone number, so
both were added — but a mutual-fund tracker in India cannot treat a Google
account as sufficient identity, because the financial records it reads are
keyed to a phone number registered with the fund houses. The decision is to
let people start with Google, email or phone as genuinely equal choices, and
then require every account to end up with a verified phone number before it
is fully usable. When two sign-in methods turn out to belong to the same
person, nothing is merged silently: the user is told what was found and must
prove they own the existing account first. The cost is a second step for
Google and email users who don't already have an account, and a noticeably
more complex login system with two new database tables. What is done: the
identity model, the linking policy, and the Google integration are
designed and planned in full. What is left: no real email is sent yet (the
system ships with a stub), Apple sign-in is deferred over a fee, and the
Privacy Policy page Google requires before publishing a real consent screen
does not exist yet.

## Technical detail

### Context

Phone+OTP was the only auth method (Phase 2, 2026-08-05). PRD-02's FR-2 had
already been reversed twice on 2026-08-17 in the specification set and
settled on passwordless throughout. The 2026-08-14 design extends that to
three entry methods and must answer three questions the earlier work did not:
what a "user identity" actually is once one person can have several
credentials; what happens when a new credential collides with an existing
account; and whether a phone number remains mandatory once Google exists.

The design document's own revision history runs v1.0 through v1.6, all on
2026-08-14. **v1.0 did not make phone the universal anchor; later revisions
reversed that.** The reversal is part of the record.

### Decision drivers

- CAS statements, fund-house records and the RTA ecosystem are keyed to a
  phone number. An account without one cannot be reconciled against the
  data the product exists to read.
- Users expect Google sign-in; requiring a phone number *first* would lose
  people at the door.
- A silent merge of two credentials that appear to be the same person is an
  account-takeover vector if either credential's ownership is wrong.
- The auth flow has no router and keeps its state in memory, so any flow
  requiring a full-page redirect would destroy it.
- Adding a second, near-identical OTP table would duplicate machinery that
  already works.

### Options considered

#### Option 1: Keep phone+OTP as the only method
Advantages: nothing to build; the anchor problem does not exist; no new
tables; no third-party dependency.
Disadvantages: a known conversion cost at the highest-friction point of the
product; no path to the sign-in affordance every comparable app offers.

#### Option 2: Google/email as first-class identity, phone optional
Advantages: shortest possible signup; no mandatory second step.
Disadvantages: accounts exist that cannot be matched against fund-house
records at all, which is the product's core function. Rejected.

#### Option 3: Phone as universal anchor, other methods as entry points (chosen)
Advantages: any entry method is accepted; every account converges on the one
identifier the domain requires; the existing phone column stays unique and
non-nullable, so no existing invariant is loosened.
Disadvantages: a mandatory extra step for Google and email signups; a new
state ("verified identity that cannot yet hold a session") that needs its own
table and TTL.

#### Option 4 (linking sub-decision): silently merge colliding identities
Advantages: invisible to the user; no extra screen.
Disadvantages: if the collision is wrong — a recycled email, a shared
address — it silently grants access to someone else's portfolio. Rejected.

#### Option 5 (linking sub-decision): step-up re-authentication before linking (chosen)
Advantages: the user sees what was found and proves ownership of the
existing account before anything is attached.
Disadvantages: an extra screen and an extra state to model.

#### Option 6 (Google integration): One Tap, or the OAuth redirect flow
Advantages: One Tap is the lowest-friction Google entry; redirect is the
most conventional OAuth shape.
Disadvantages: the redirect flow wipes the in-memory step-machine state the
auth flow depends on, and there is no router or persisted flow state to
restore from. Both rejected in favour of the rendered button plus ID-token
verification (no client secret, no token exchange). A popup-blocker
constraint follows: the sign-in trigger must run synchronously in the
button's own render path, never behind an `await` in a click handler.

#### Option 7 (OTP storage): a separate email-OTP table
Advantages: clean separation of channels.
Disadvantages: duplicates a table and a service that already work. Rejected;
the existing OTP table was generalised to accept a phone number or an email
address instead.

### Decision

Adopt a phone-anchored multi-method identity model:

1. A new identities table is the source of truth for credentials; the user
   row becomes a profile and anchor. The phone column stays unique and
   non-nullable, and a user row cannot exist without a matching phone
   identity.
2. A new pending-verification table holds a just-verified Google or email
   identity that cannot yet hold a session, for one shared 10-minute TTL,
   covering both the mandatory-phone case and the collision case.
3. Verification returns a three-way outcome: logged in, link required, or
   phone required.
4. Collisions require step-up re-authentication. No silent merging, ever.
5. Identity precedence for display and prompts is Google > Email > Phone.
6. Google is verified by ID-token signature check against Google's public
   keys, via the rendered sign-in button.
7. The sessions table records which method produced each session.
8. Apple is out of scope; no provider value for it is added anywhere.

### Consequences

Positive:
- Every account is reconcilable against fund-house records by construction.
- Account linking is auditable and consent-based.
- No existing schema invariant was loosened to accommodate the new methods.
- The three-way verify outcome is modelled as a discriminated union, so no
  frontend caller can silently forget a case.

Negative:
- Two new tables, a widened OTP table, a new session column, and a new
  third-party dependency for token verification.
- Google and email signups have a mandatory second step.
- **ADR-001's "no public marketing surface" framing is overridden** for the
  decorative auth panel — stated explicitly in the design's own Explicit
  Deviations section, not inferred here. ADR-001 has not been amended; a
  vault owner may want to append an amendment to it, as was done on
  2026-08-05.
- **PRD-02 FR-2b is superseded** by this design, per the design's own
  statement. PRD-02 has not been annotated.
- Google's consent screen cannot be published without a Privacy Policy page,
  which does not exist. See R-023.

### Validation

The backend plan's final verification requires the full backend suite green,
a migration upgrade-then-downgrade round trip against a scratch database,
and a cross-check against the design's own testing checklist covering
identity-model constraints, mocked Google verification, collision and
linking, the mandatory phone gate, identity precedence, the session-method
column, and route-level status codes. The frontend plan requires the test
suite, a clean type build, a production build, and a manual pass confirming
the four entry points and the end-to-end phone/email/OTP flows against a
locally running backend in stub delivery mode.

**Not validated:** any real Google sign-in against a published consent
screen, and any real email delivery.

### Evidence

- Design: `08-evidence/documents/specs/2026-08-14-multi-method-auth-design.md`
- Frontend design: `08-evidence/documents/specs/2026-08-14-multi-method-auth-frontend-design.md`
- Plans: `08-evidence/documents/plans/2026-08-14-multi-method-auth-backend-plan.md`,
  `08-evidence/documents/plans/2026-08-14-multi-method-auth-frontend-plan.md`
- Prior state: `08-evidence/documents/specs/2026-08-05-phase-2-auth-onboarding-backend-design.md`
