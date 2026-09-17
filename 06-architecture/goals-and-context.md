# Goals and Context

## What Unifolio is

A portfolio tracker for Indian mutual-fund investors and their households. A user
uploads their Consolidated Account Statement (CAS) — the single PDF that CAMS and
KFintech, the two registrars that between them administer essentially every Indian
mutual fund, will email to an investor on request. Unifolio parses it into structured
holdings and transactions, and from then on shows the household's portfolio, its
performance, and how each fund stacks up against its peers, without the user ever
re-uploading anything to simply look at their data.

## Who it serves

- **The individual investor** who wants one place that shows what they actually own,
  across every AMC and every folio, with honest performance numbers.
- **The household.** Family is not an add-on: the onboarding flow asks about it up
  front, each member has their own statements and holdings, and the default landing
  view for a user who has set up family members is the family aggregate, not their own
  slice.

## The four product surfaces

| Surface | Source PRD | What it does |
|---|---|---|
| CAS import | PRD-01, superseded in part by `Updated-CAS-PRD` | Upload → parse → review → confirm, with duplicate transactions rejected at the database level |
| Signup and onboarding | PRD-02 | Passwordless auth, a four-question intake, household setup, first import |
| Main dashboard | PRD-03 | Holdings table, allocation, SIP detection, cash flow, monthly snapshots, family view, distributor comparison |
| Analytics dashboard | PRD-04 | AMC and SEBI-category allocation, category ranking, a cost-aware fund score, benchmark XIRR comparison, weighted TER |

## Constraints the architecture answers to

- **Team size: two founders plus one incoming engineer.** This is the single most
  load-bearing constraint in the ADR set. It is why the frontend is one application
  rather than micro-frontends (ADR-001), why the backend is four *logical* services
  inside one FastAPI deployment rather than four deployments (ADR-002, TDD), why the
  database is managed rather than self-hosted (ADR-003), and why deployment favours the
  highest-abstraction option available (ADR-005).
- **Everything is behind a login.** There is no public marketing surface or
  SEO-dependent content in MVP scope. This is why SSR buys nothing (ADR-001).
- **Money maths must be exact.** `Decimal` in Python, `NUMERIC` in Postgres, never
  floating point, throughout — a constraint stated in PRD-01 and carried literally into
  the column types.
- **Minimum retained personal data.** The parsed PAN is never persisted; the source PDF
  is discarded after parsing (ADR-004). The compliance frame is India's DPDP Act.
- **No control over the upstream data.** AMFI, NSE, and `mfapi.in` are public sources
  with no contract and no SLA. Every dependency on them is designed to degrade to a
  stale-data label rather than an error.

## What is deliberately out of scope for v1

- Cap-wise portfolio composition and stock-level overlap between funds — deferred in
  both PRD-03 and PRD-04, with a standing reminder carried in each so it is not
  silently lost.
- Full auth and security policy (rate-limiting detail, lockout, session expiry UX,
  device management) — a separate deferred PRD; the Auth service implements only the
  base flow that PRD unblocks against.
- Document storage of any kind (ADR-004).

## Related

- Decisions: [ADR-001](../03-decisions/ADR-001-frontend-application-architecture.md) …
  [ADR-006](../03-decisions/ADR-006-background-job-scheduling.md)
- Open items: [`07-risks-and-debt.md`](../07-risks-and-debt.md)
