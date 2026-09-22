# Current Status

_Overwritten each update — this is a snapshot, not a history. For
history, see `02-journey/`._

**As of 2026-09-18:** Batch 2b ingested — 2026-08-17 to 2026-08-31, the second
half of August, continuing directly from batch 2a. The vault now holds fourteen
decisions (ADR-001 to ADR-014), seven investigations, fifteen journey stages,
an eight-section architecture description, and a risk register of fifty-one
items. Nothing from batches 1 or 2a has been rewritten.

**The single most important thing this batch changes about the picture:** the
fortnight produced far more design than build. Of eight implementation plans,
two were executed in full — and both were for a feature that was reversed the
same day. One was partially executed. Five were never started, and four design
specifications carry no execution record at all (R-051). Almost everything
described below is **intent, not shipped behaviour**, and every record in the
vault has been written to say which is which.

**Where the product stands.** Unchanged in what a user can actually do: sign
up, onboard, add family members, upload CAS statements, and see a valued
dashboard with holdings, allocation, SIPs, cash flow, family aggregate,
distributor comparison and the first analytics subsystems. What this batch adds
to the picture is what is designed and waiting: a cadence-based SIP model
replacing the 40-day window (ADR-012), a PDF export of the analytics dashboard
(ADR-013), portfolio-level distributor comparison, and a whole second asset
class — direct equity, imported from depository statements (ADR-014).

**A finding that changes the plan rather than adding to it:** the desktop Main
Dashboard is still a placeholder stub, while the mobile dashboard is a mature
implementation (R-037). The product's primary screen on its primary platform
does not exist, and the mobile work is now the reference for what it should do.

**Three things nothing works without, and none of them is done:**

1. **Neither OTP channel actually delivers a message.** Phone SMS has no
   provider chosen at all (R-025); email has a provider chosen and a stub
   implementation (ADR-009, R-024). No real user can log in today.
2. **There is no Privacy Policy page anywhere**, and Google will not publish
   a sign-in consent screen without one (R-023). This is a legal deliverable
   with a lead time, not an engineering task. Note that the mobile
   "privacy onboarding" work of 2026-08-20 is a trust-primer screen, not this.
3. **The database still runs on SQLite.** The move to AWS RDS PostgreSQL is
   specified and has a runbook, and the PostgreSQL branch of migration `0002`
   has never been executed against a live instance (R-021).

**The open question most worth a decision:** whether Unifolio stores PAN, and
by what mechanism. There are now five different recorded positions across
five dates — being rewritten to masked-on-display (2026-08-25), kept
never-persisted until a schema change lands (2026-08-26), stored encrypted
at rest (ADR-007, 2026-09-16), and reaffirmed live on 2026-09-19 as encrypted
both at rest and in transit, with detailed documentation still pending from a
colleague — plus a document that contradicts itself on the point. Nothing has
changed in the schema. Until this is fully settled and documented, the
automatic email ingestion that makes Phase 2's equity import effortless
cannot be designed (R-043).

**Second on that list, and cheap to fix:** the marketing brief handed to an
external builder on 2026-08-31 carries a placeholder claim that Unifolio's CAS
import is "powered by MFCentral". It is not — ingestion is user-uploaded CAS
PDFs, and MFCentral-class access is a deferred, regulator-gated future phase.
The brief's own SEO strategy is built on repeating entity statements verbatim
so answer engines converge on them, which makes a wrong one expensive (R-046).

Still true from earlier batches: two incompatible fund-score methodologies
remain on the books pending a product call (R-015), the parse-accuracy targets
for the core import feature have no test fixtures behind them (R-009), and PAN
storage is a confirmed direction that is not implemented and is in direct
tension with a guard test written in August to prevent exactly it (R-018).

**Next:** a verification pass against the current code repo. Most of this
batch's risk entries are marked "to verify" for the same reason — the vault now
describes a great deal of designed work whose build status is known only up to
2026-08-31. Note also a live-conversation forward pointer (2026-09-19, not yet
corroborated by source material): the vault owner states that all six
not-fully-executed plans in this batch have since shipped in later work — see
R-051.
