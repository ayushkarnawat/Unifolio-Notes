# Product and Architecture Definition

Date: 2026-07-22 → 2026-09-02
Status: Complete — superseded in part by implementation work not yet ingested

## For stakeholders

This stage turned "we want to build a mutual-fund portfolio tracker" into a complete,
buildable specification: four product requirement documents, a technical design, a
database schema, an app flow, a design system, and six formal architecture decisions.
The intended outcome was a spec the team could build from without re-litigating choices
mid-build. That largely happened — but three things went differently than planned, and
they are the most useful part of this record. First, formalising the deployment choice
turned up the fact that the AWS service everyone assumed we would use had stopped
accepting new customers, which was caught before anything was built on it rather than
after. Second, the login method was changed twice in a single day in August and ended up
back where it started, passwordless. Third, a compliance audit in September found the
database documentation had drifted three to four migrations behind the actual code —
caught, and fixed, but a warning about how quickly that happens. The result is a
specification set that is genuinely build-ready, with a known set of unreconciled
conflicts carried forward rather than papered over.

## Technical detail

### Intended outcome

A complete, internally consistent specification set covering the four MVP modules —
CAS import, signup and onboarding, main dashboard, analytics dashboard — with the
technology stack formally decided, the database designed, and the design system
specified to token level, so that implementation could proceed without re-deciding
architecture mid-build.

### What actually happened

The specification set was produced: PRD-01 through PRD-04, a TDD, a database schema, an
app flow, a design brief, a design schema, a set of six ADRs, and a SQLite-to-Postgres
migration plan. All six ADRs reached **Accepted**.

Three things did not go to plan.

**1. The deployment assumption was wrong, and formalising it is what caught it.** The TDD
had proposed AWS App Runner as an unformalised default. Writing it up as ADR-005
surfaced that App Runner had stopped accepting new customers on 2026-04-30 and was in
maintenance mode. Unifolio would have been a new customer, so the service could not have
been provisioned at all. The decision moved to ECS Express Mode, which — usefully —
natively supports the scheduled-task pattern ADR-006 needed, something App Runner never
did. **This is the clearest argument in the whole batch for writing decisions down: the
error was in an assumption nobody had questioned, and the act of formalising it was what
exposed it.**

**2. The authentication method was reversed within a single day.** PRD-02's FR-2 was
revised twice on 2026-08-17 — moved to email + password, then reversed back to email +
OTP by management decision. The schema followed: migrations 0004–0006 added
`auth_identities` and password columns, and migrations 0007–0008 removed
`password_hash`, `email_confirmed_at`, `password_reset_tokens`, and
`email_confirmation_tokens` entirely. The product is passwordless throughout —
phone + OTP, email + OTP, or Google, converging on a mandatory verified phone number.

**3. Documentation drifted behind the code, and an audit caught it.** By 2026-09-02 the
database schema document had gone stale by three to four migrations — the `imports`
status enum, coverage-gap columns, the `opening_balance` transaction type, and the
removal of the password tables were all missing. A compliance audit reconciled them in
one pass (v1.4), and a second pass the same day (v1.5) found a partial unique index on
`household_members` that the document had **never specified even before the code caught
up**.

Two further things worth recording. A 2026-08-05 amendment corrected ADR-001's Context:
the prototype frontend it claimed to be preserving was vanilla TypeScript, not React, so
the "avoids rework" justification was moot — the decision stood on its other merits, and
the ADR was amended rather than rewritten. And a deferred `LATERAL`-join optimisation was
**benchmarked rather than assumed** on 2026-08-19, with the result contradicting the
obvious expectation: the theoretically faster shape measured ~4.6s against the current
approach's ~3.5s on the dev dataset.

### Deviation — decision or response taken

| Deviation | Response |
|---|---|
| App Runner unavailable to new customers | ADR-005 written against ECS Express Mode, with standard ECS Fargate documented as the fallback. Caught before any build work depended on it |
| Auth method reversed | PRD-02 FR-2 revised twice in one day; schema followed via migrations 0007–0008. Password auth removed entirely rather than left dormant |
| Schema doc three to four migrations stale | Compliance audit; schema doc reconciled to v1.4, then v1.5. The lesson is recorded in `05-docs/reference/database-schema.md`: treat it as lagging the migrations by default |
| ADR-001's stated justification was factually wrong | **Amended, not rewritten.** The correction is visible in the record and the decision was re-justified on its remaining merits |
| A "obviously faster" query optimisation | Benchmarked before adoption; measured slower; deferred with the measurement attached so nobody redoes it on faith |

### Result

A build-ready specification set, six Accepted ADRs, and a schema reconciled against
migrations 0001–0011. Implementation had begun in parallel — Phase 1 (Import Review UI),
Phase 3 (ARN lookup), and Phase 4 (analytics backend, with three external integrations
live-verified on 2026-08-10) are all referenced as done or in progress by these
documents, though the plans describing that work are in a later batch and are not yet in
this vault.

Carried forward unresolved: a direct contradiction on whether the PAN is stored, a
contradiction on whether the raw PDF is retained, three different definitions of the
transaction dedupe key, two unreconciled generations of the CAS import flow, and a
`family-members` vs `household-members` naming split. All are in
[`07-risks-and-debt.md`](../07-risks-and-debt.md).

### Related

- [ADR-001](../03-decisions/ADR-001-frontend-application-architecture.md) through
  [ADR-006](../03-decisions/ADR-006-background-job-scheduling.md)
- [Architecture index](../06-architecture/00-index.md)
- [Risks and debt](../07-risks-and-debt.md)
- Sources: `08-evidence/documents/` (14 files)

## Addendum — 2026-09-23: the earliest artifact this vault holds predates this stage by 8 days

A newly-ingested investor-facing roadmap document, dated **2026-07-14**, is
now the earliest dated artifact in this vault — a week before this stage's
own 2026-07-22 start. It shows the project's MVP scope and schedule as
management framed it before the formal specification set (PRD-01 through
PRD-04, the six ADRs above) existed:

- **Original target:** a working MF-only MVP shippable by **1 August 2026**,
  on the already-built CAS-parser pipeline (`casparser` + `mfapi.in` +
  XIRR/FIFO), with a four-phase timeline (Foundation Jul 14–18, Build Jul
  19–24, Complete Jul 25–Aug 1, Launch Aug 2–15).
- **A single named critical-path dependency:** the whole downstream schedule
  assumed the first engineer would start around **2026-07-21**; the document
  states explicitly there was "no hidden slack to absorb" a hiring delay
  elsewhere in the plan.
- **Scope at that point explicitly excluded** equity/broker integration,
  MFCentral live API / Account Aggregator access (both already named as
  gated behind ARN/RIA registration — consistent with what became ADR-014's
  Phase 2 framing a month later), and **multi-member family accounts
  ("single-login only for MVP")**.

That last point does not match what this vault otherwise documents: the
2026-07-22 specification set that followed (PRD-02's household step) and
everything built since (`current-status.md`: "add family members") already
treat multi-member/household accounts as in scope for the same MVP, not a
later phase. No source material in this vault records the specific moment
this changed — flagged as a hypothesis that the single-login-only framing
was an early, pre-spec simplification superseded within days, not a
verified fact, since no document narrates the change itself.

This does not change any status, ADR, or risk recorded above — it is
earlier-dated context that predates and does not contradict the stage's own
"what actually happened" account, except for the one scope point flagged.
See also the [ADR-003 addendum](../03-decisions/ADR-003-primary-database-rds-postgresql.md)
for a related early-stage alternative (S3+Athena) that this same batch's
material surfaced and that also predates the formal ADRs above.

Source: `08-evidence/documents/mf-mvp-roadmap.md.pdf`.

## Addendum — 2026-09-24 (batch 4e1 ingestion): the pre-PRD-01 CAS-import build-vs-buy triage

Two raw planning files ingested in batch 4e1 (`Planning-V1.MD`, `MF CAS PARSER.pdf`) contain
an explicit build-vs-buy comparison that precedes PRD-01 and is not otherwise recorded in the
vault at this level of detail. PRD-01's background section already notes the MFCentral CAS API
shutdown at summary level; these files show the actual options considered and rejected. Neither
source file carries an internal date — treat the dating as "before or around PRD-01's 2026-07-22
creation," not confirmed.

**Options considered, per the raw table:**

| Path | User data access | Cost/effort | Verdict |
|---|---|---|---|
| CAS PDF parsing (open-source `casparser`) | Full transaction history | Free, ~a day | **Chosen** — user's own consented download/upload, works today |
| casparser.in hosted API | Same | ₹999/mo, 10 free credits | Fallback/benchmark only |
| mfapi.in | NAV/scheme data only, no user holdings | Free | Enrichment only (NAV series) |
| parse.bot MFCentral API | Public scheme data only, no user holdings | Key needed | Enrichment only (sector/holdings reference data) |
| smallcase Gateway | Full | Commercial partnership + KYB required | Rejected as "not viable for a test build" |
| Account Aggregator (via a TSP such as Setu/Finvu) | Full, real-time | Regulated-entity status, 5–10 months, ₹5–25L | Deferred — "your long-term differentiator, not the prototype" |

This is the same AA cost/timeline figure (5–10 months, ₹5–25L) that reappears in the later,
separate Phase 2 stocks/demat decision — see
[ADR-014](../03-decisions/ADR-014-phase-2-demat-ingestion.md) and the
[2026-08-25 journey entry](2026-08-25-phase-2-stocks-and-demat-import.md) — confirming the same
build-vs-buy reasoning was applied consistently across both the original MF CAS decision and the
later stocks/demat one, not re-derived from scratch each time.

**Why MFCentral's own API was ruled out, specifically:** the raw material states SEBI/AMFI shut
down the MFCentral CAS API in September 2025, "stranding 100+ fintechs that relied on it,"
including the PAN+OTP sync flow that Mprofit and Investwell reportedly used — so "recreate what
Mprofit does" was explicitly not an option. The source is explicit that attempting to hit
MFCentral's now-private endpoints, or automate its OTP flow without authorization, "would be
unauthorized access, so that path is out both practically and legally." This is a hypothesis from
a single raw planning document, not independently verified against SEBI/AMFI's own notices, but it
is the stated reasoning behind going with CAS-PDF parsing rather than an MFCentral integration.

This connects to **R-046** in [`07-risks-and-debt.md`](../07-risks-and-debt.md) (the marketing
brief's "powered by MFCentral" trust-bar claim contradicting how Unifolio actually imports
statements): this addendum's source material is evidence that the contradiction is not just
imprecise marketing copy but reflects a real, deliberate technical/legal constraint — Unifolio's
CAS import was built the way it was in part *because* a direct MFCentral integration was
considered and ruled out, not merely not-yet-built.

Sources: `08-evidence/documents/Planning-V1.MD`, `08-evidence/documents/MF CAS PARSER.pdf`.
