# Current Status

_Overwritten each update — this is a snapshot, not a history. For
history, see `02-journey/`._

**As of 2026-09-23:** Batch 4 ingested — 34 files from `Docs/orchestration/`
(the code repo's own Claude/Codex delegation handoffs, split across two
sub-batches: AWS infrastructure, and Analytics/Fund-Scorer), reconciled
against everything ingested so far. The vault now holds eighteen decisions
(ADR-001 to ADR-018), eleven investigations, twenty-nine journey stages, a
nine-section architecture description, and a risk register of sixty items.
Nothing from earlier batches has been rewritten — corrections are appended.

**The single most important thing this batch changes about the picture:**
two AWS infrastructure phases that batch 3 left "unconfirmed" are now
directly corroborated as applied and live — Phase 4 (S3+CloudFront) and
Phase 5 (ACM/DNS/HTTPS), both confirmed by a 2026-09-10 dispatch stating
`staging.unifolio.in`/`staging-api.unifolio.in` resolve over HTTPS. The
fourth piece of ADR-006 (EventBridge scheduler Terraform) was authored and
reviewed the same day, and the original ~1,000-user Phase 7 hardening plan
was deliberately rescoped to a small 5→30-user beta, with several hardening
items re-deferred by name (a second ECS task, real OTP delivery, the
fck-nat→NAT-Gateway upgrade, structured logging, Terraform-drift tooling),
each with a named revisit trigger — not silently dropped.

**A credential-rotation correction, more important than anything else in
this batch.** Batch 3 recorded a real AWS IAM access key as "rotated and
scrubbed" per its own source material's claim. **This is now known to be
inaccurate.** The vault owner has since confirmed, live, that neither that
AWS IAM key nor a separate real RDS staging database password (also found
in batch 3's raw material) has actually been rotated — both are real,
currently-live staging credentials, deliberately left unrotated until the
project moves from staging to production. Recorded as
[R-057](../07-risks-and-debt.md) (a high-severity, explicit pre-production
gate) and as a reopening addendum on
[INV-010](../04-investigations/INV-010-aws-iam-key-pasted-in-chat-and-rotated.md).
No literal credential value is reproduced anywhere in this vault. **Both
credentials must be rotated before this product goes to production.**

**Two more architectural gaps were also given their own dedicated,
cross-referenced risk entries this pass** (previously narrative-only inside
an investigation and a journey entry): the event-loop-starvation
vulnerability behind the AMFI TER `ReadTimeout` incident is architectural,
not fully closed, and will still exist in production under real concurrent
traffic ([R-058](../07-risks-and-debt.md)); and the CAS-import system has
two parallel backend code paths that independently drifted to need the same
duplicate-detection fix wired in twice, a standing dual-maintenance burden
([R-059](../07-risks-and-debt.md)).

**Real infrastructure now exists.** Batches up to 2c described AWS
infrastructure only as authored Terraform, "not a running production
system." That changed in batch 3: an AWS account was created (2026-09-07,
root MFA, budget alert, admin IAM user), `unifolio.in` was cut over from
GoDaddy to a Route 53 hosted zone with mail preserved, and staging
networking was decided (fck-nat over a managed NAT Gateway, to avoid a
cost-approval step). Terraform Phases 1-3 were applied 2026-09-09 (a real
network, RDS database, ECR registry, and ECS service); Phases 4-5 are now
also confirmed applied and live (above). Two follow-up problems from Phase
1-3 (a crash-looping service with no image pushed yet; a schema-less
database) were root-caused and fixed the same session, verified four
different ways.

**A second, independent branch surfaced and merged (batch 3).** Alongside
the 2026-08-14 multi-method-auth work this vault already knew about, a
different contributor's branch — the CAS import lifecycle rebuild (an
explicit 11-state machine replacing an implicit one), a new design-token/
mobile UI foundation, and the last piece of the fund Scorer's backend — was
found (via branch reconciliation) and merged the same day. It passes its
full test suite. Most of it has not had the same independent review pass
every other feature this size gets before being called finished — recorded
as an open gap (ADR-018, R-004 update), not smoothed over.

**Fund Scorer v2's valuation overlay is feasible but not free
([INV-011](../04-investigations/INV-011-scorer-v2-pe-pb-valuation-overlay-feasibility.md)).**
No official, free, programmatic feed for fund-level PE/PB exists in India;
building it in-house from AMC portfolio disclosures is technically feasible
but open-ended in scope, while a licensed data feed is fast but a budget
decision — which path to take is an open product/budget call, not yet
made.

**A new accepted-limitation risk, and an analytics correction pass, both
from the dashboard/analytics track.** Hardening the dashboard's NAV and
holdings cache took six review rounds; one coordination gap (concurrent
recomputation requests) was knowingly left unfixed by product-owner
decision, not an oversight — recorded as
[R-060](../07-risks-and-debt.md). Separately, a 22-item cross-reference of
the Analytics dashboard's correction plan was itself adversarially
reviewed (8 findings fixed) and closed out 4 more same-day fixes (a
category CAGR scale bug, a mixed-plan-type holdings-merge bug, a
switch-transaction XIRR blind spot, an unclamped Scorer final score); full
TRI (Total Return Index) benchmark sourcing remains explicitly deferred
behind a labeling-only fix in the meantime.

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

**Four things nothing works without, and none of them is confirmed done by
any batch's material yet:**

1. **Neither OTP channel actually delivers a message** (R-024, R-025) — the
   staging deployment explicitly keeps real OTP delivery and Google Sign-In
   out of the beta pass, deliberately, and this batch adds nothing that
   changes that.
2. **There is still no Privacy Policy page** (R-023) — untouched by this
   batch's material.
3. **Whether the 2026-09-11 staging runbook was ever run to completion** is
   still unconfirmed — Phases 1-5 of Terraform are now confirmed applied,
   but the runbook's own remaining steps (migrations against real RDS, an
   image push, the Phase 6 smoke test, CI/CD) are not evidenced as done by
   any batch's material yet (R-052).
4. **Both the RDS staging password and the AWS IAM key are still live and
   unrotated** — must be rotated before production (R-057, above).

**The open question most worth a decision, still:** PAN storage and
encryption (R-043). The non-PAN duplicate-person-detection design
(2026-09-02) deliberately avoids needing PAN for that one problem, but does
not bear on the storage/encryption question itself.

Still true from earlier batches: two incompatible fund-score methodologies
remain on the books pending a product call (R-015), the desktop Main
Dashboard is still a placeholder stub while mobile is mature (R-037), and
the marketing brief's "powered by MFCentral" claim is still wrong (R-046).

**Next:** a verification pass against the current code repo remains the
single highest-value action — most risk entries across all batches are
marked "to verify" for the same reason. `AWS Readiness/aws-golive-
readiness-report.md`, referenced but not yet ingested (R-054), and the
remaining ~22 `Docs/orchestration/` files (bug/data/import/auth track) plus
the root-level `Docs/` reference material, are the natural next batches.
