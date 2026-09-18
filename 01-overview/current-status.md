# Current Status

_Overwritten each update — this is a snapshot, not a history. For
history, see `02-journey/`._

**As of 2026-09-17:** Batch 2a ingested — the first eleven days of actual
implementation, 2026-08-04 to 2026-08-14. The vault now holds eleven
decisions (ADR-001 to ADR-011), four investigations, eight journey stages, an
eight-section architecture description, and a risk register of thirty items.
Batch 1's product-and-architecture foundation is unchanged; this batch is the
record of building against it.

**Where the product stands, per that material:** a user can sign up, complete
onboarding, add family members, upload CAS statements for each of them, and
see a valued dashboard — holdings, allocation, SIPs, cash flow, family
aggregate — plus distributor comparison and the first two analytics
subsystems. Google and email sign-in are designed and planned in full
(ADR-008) on a mandatory phone anchor with non-silent account linking. The
Unifolio Scorer is settled and built (ADR-010). Every external data source is
identified and was verified by hand.

**Three things nothing works without, and none of them is done:**

1. **Neither OTP channel actually delivers a message.** Phone SMS has no
   provider chosen at all (R-025); email has a provider chosen and a stub
   implementation (ADR-009, R-024). No real user can log in today.
2. **There is no Privacy Policy page anywhere**, and Google will not publish
   a sign-in consent screen without one (R-023). This is a legal deliverable
   with a lead time, not an engineering task.
3. **The database still runs on SQLite.** The move to AWS RDS PostgreSQL is
   specified and has a runbook, and the PostgreSQL branch of migration `0002`
   has never been executed against a live instance (R-021).

**The open question most worth a decision:** the vault now records two
incompatible fund-score methodologies — the PRD-04-derived one in
`05-docs/explanation/fund-scoring-methodology.md` and the implemented one in
[ADR-010](../03-decisions/ADR-010-fund-scorer-composite-formula.md). They
disagree on the number of ingredients, the tier cut-points, and whether the
score is modelled on Morningstar or deliberately unlike it. That is a product
call (R-015). Alongside it sit two smaller vault-versus-implementation
mismatches: which service owns the ARN lookup (R-016) and which shape the
distributor-comparison route has (R-017).

Still true from batch 1: the parse-accuracy targets for the core import
feature have no test fixtures behind them (R-009), and PAN storage is a
confirmed direction that is not implemented — and is now in direct tension
with a guard test written in August to prevent exactly it (ADR-007, R-018).

**Next:** the rest of batch 2 — the later implementation plans and specs,
which should carry the story past 2026-08-14.
