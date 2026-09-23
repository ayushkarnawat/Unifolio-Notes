# Current Status

_Overwritten each update — this is a snapshot, not a history. For
history, see `02-journey/`._

**As of 2026-09-22:** Batch 3 ingested — the code repo's own root
engineering-loop files (`decisions.md`, `log.md`, `session.md`, `AGENTS.md`,
`CLAUDE.md`, `backend.md`, `database.md`, `PRODUCT.md`, `README.md`,
`DEFERRED_FEATURES.md`, `CAS-IMPORT-UPDATE-PLAN.md`), reconciled against
everything ingested so far. The vault now holds eighteen decisions (ADR-001
to ADR-018), ten investigations, twenty-five journey stages, an
eight-section architecture description, and a risk register of fifty-six
items. Nothing from earlier batches has been rewritten — corrections are
appended.

**The single most important thing this batch changes about the picture:**
three of the six plans batch 2b/2c had marked unexecuted are now directly
corroborated as built — the SIP cadence redesign, the analytics PDF export,
and the portfolio-level distributor comparison, all through the mandatory
adversarial-review gate. The other three (the auth left-panel verification
task, and both Phase 2 demat-import plans) remain uncorroborated by this
batch's material — R-051 is updated, not resolved. The Fund Score card
redesign (ADR-017) is now also confirmed fully executed the day after it was
designed (R-053 resolved).

**Real infrastructure now exists.** Batches up to 2c described AWS
infrastructure only as authored Terraform, "not a running production
system." That changed this batch: an AWS account was created (2026-09-07,
root MFA, budget alert, admin IAM user), `unifolio.in` was cut over from
GoDaddy to a Route 53 hosted zone with mail preserved, and staging
networking was decided (fck-nat over a managed NAT Gateway, to avoid a
cost-approval step). Two days later (2026-09-09), Terraform Phases 1-3 were
actually applied: a real network, RDS database, ECR registry, and ECS
service exist in AWS, not only in `.tf` files. Two follow-up problems
(a crash-looping service with no image pushed yet; a schema-less database)
were root-caused and fixed the same session, verified four different ways.
Whether Phase 4 (S3+CloudFront) and Phase 5 (ACM/DNS/HTTPS) have since been
applied, and whether the 2026-09-11 staging runbook was ever actually run
end to end, remains unconfirmed by this batch's material.

**A security incident, handled and closed.** During the same infrastructure
session, a real AWS IAM access key was briefly exposed in plaintext and was
rotated before any evidence of misuse — the full incident, including the
GitHub push-protection catch and the commit-history rewrite, is recorded as
its own investigation (INV-010). No literal credential value is reproduced
anywhere in this vault, including in that record. A related, separate
finding — a real-looking RDS master database password appearing in the raw
source material's own shell-quoting-bug narrative — is referenced only
descriptively in this vault, never by its literal characters, for the same
reason.

**A second, independent branch surfaced and merged.** Alongside the
2026-08-14 multi-method-auth work this vault already knew about, a
different contributor's branch — the CAS import lifecycle rebuild (an
explicit 11-state machine replacing an implicit one), a new design-token/
mobile UI foundation, and the last piece of the fund Scorer's backend — was
found (via branch reconciliation) and merged the same day. It passes its
full test suite. Most of it has not had the same independent review pass
every other feature this size gets before being called finished — recorded
as an open gap (ADR-018, R-004 update), not smoothed over.

**Where the product stands.** Everything true as of batch 2c still holds
(sign up, onboard, add family members, upload CAS statements, see a valued
dashboard, plus the now-precomputed Analytics dashboard) plus: a rebuilt CAS
import lifecycle; the SIP "This Month" tab now uses cadence projection
instead of a 40-day recency window; the analytics dashboard can be exported
as a real vector PDF; distributor comparison is portfolio-wide; and the Fund
Score card shows a plain-English verdict instead of raw statistics. A
mobile-polish pass (2026-08-27) added a Fund Details performance graph,
using a narrow, explicitly documented exception to the Decimal-never-float
rule for chart pixel geometry only — never for any number shown to the
user.

**Two open items worth flagging by name, both explicitly deferred by
product-owner decision, not oversights:**

1. **Phone-OTP login silently creates a new account for an unrecognized
   phone number**, instead of erroring the way the email channel already
   does (R-056). Root-caused; fix direction is known; not built.
2. **The SIP tab switcher has a low-severity ARIA IDREF gap** (an inactive
   tab's `aria-controls` points at an unmounted panel id) — accepted as a
   documented limitation rather than a third fix round (R-055).

**Three things nothing works without, and none of them is confirmed done
by any batch's material yet:**

1. **Neither OTP channel actually delivers a message** (R-024, R-025) — this
   batch's staging deployment explicitly keeps real OTP delivery and Google
   Sign-In out of the beta pass, deliberately, and this batch adds nothing
   that changes that.
2. **There is still no Privacy Policy page** (R-023) — untouched by this
   batch's material.
3. **Whether the 2026-09-11 staging runbook was ever run to completion** is
   still unconfirmed — Phases 1-3 of Terraform are now confirmed applied
   (2026-09-09), but the runbook's own remaining steps (migrations against
   real RDS, image push, Phase 4/5 Terraform, the Phase 6 smoke test, CI/CD)
   are not evidenced as done by this batch's material (R-052).

**The open question most worth a decision, still:** PAN storage and
encryption (R-043). This batch's non-PAN duplicate-person-detection design
(2026-09-02) deliberately avoids needing PAN for that one problem, but does
not bear on the storage/encryption question itself.

Still true from earlier batches: two incompatible fund-score methodologies
remain on the books pending a product call (R-015), the desktop Main
Dashboard is still a placeholder stub while mobile is mature (R-037), and
the marketing brief's "powered by MFCentral" claim is still wrong (R-046).

**Next:** a verification pass against the current code repo remains the
single highest-value action — most risk entries across all three batches
are marked "to verify" for the same reason. `AWS Readiness/aws-golive-
readiness-report.md`, referenced but not yet ingested (R-054), is the
natural next batch, since this batch's real infrastructure work makes its
content directly load-bearing rather than speculative.
