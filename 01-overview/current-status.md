# Current Status

_Overwritten each update — this is a snapshot, not a history. For
history, see `02-journey/`._

**As of 2026-09-30:** Batches 4c through 7 ingested (root `Docs/` reference
material, AWS go-live readiness, `Notes for Unifolio/`, the legacy `Docs/`
duplicate archive, and the full `Docs/orchestration/` + `Docs/superpowers/`
code-repo pull), plus an approved design and implementation plan for
publishing this vault as a stakeholder-facing site. The vault now holds
nineteen decisions (ADR-001 to ADR-019), sixteen investigations,
thirty-four journey stages, and a risk register of seventy items. Nothing
from earlier batches has been rewritten — corrections are appended.

**The PAN question moved from "undecided" to "decided but not built."**
[ADR-007](../03-decisions/ADR-007-pan-storage-and-encryption.md) — planned
since 2026-08-25, "not yet implemented" through every addendum since — was
formally reopened and settled on 2026-09-18/28: Unifolio **will** store PAN,
encrypted at rest, using a customer-managed KMS key (the open CMK-vs-SSM
question is now resolved as CMK). The same discussion reversed
[ADR-004](../03-decisions/ADR-004-object-storage-scope-and-cas-pdf-retention.md)
("CAS PDF not retained, not in S3, not elsewhere" → now retained 30 days
post-parse via migration `0015`), for the same reason: reliable
per-household-member matching needs a signal only PAN provides. **Both
decisions are on paper, not in production** — no PAN column exists in the
schema yet, and the CAS-files S3 bucket is authored in Terraform but not
applied (file storage is still disk-backed). A correction was also made
this batch: earlier material overstated "S3 in production" — that was
wrong; it's authored only. The legal-review/DPDP-Act precondition ADR-007
itself named as required before reopening is still not evidenced as done —
tracked as [R-066](../07-risks-and-debt.md) (should Unifolio verify PAN
*ownership* at signup — research complete, decision pending).
[R-002](../07-risks-and-debt.md) (raw CAS PDF retention) is now resolved on
this basis. A related gap surfaced the same pass: the 30-day CAS-file
retention window is a real, tested script (`expire_cas_files.py`) that
**nothing schedules to run** — files are not actually being deleted on
schedule anywhere yet ([R-070](../07-risks-and-debt.md)).

**The Postmark → SES email cutover is complete, and Postmark is gone
entirely.** Following the 2026-09-17→23 arc documented in
[the journey entry](../02-journey/2026-09-17-email-otp-postmark-to-ses.md),
Postmark hit its trial same-domain sending wall and was fully replaced by
Amazon SES — including removing the dormant `PostmarkEmailProvider`
fallback the runbook itself had recommended keeping wired in for rollback.
That means there is currently no live fallback if SES has an outage or gets
throttled ([R-067](../07-risks-and-debt.md), low severity, new). This does
not change the more fundamental fact that **neither OTP channel actually
sends a real message yet** — email (R-024) and phone (R-025) both remain
stub/echo-back implementations by deliberate scope choice, unchanged by
this batch.

**Two new production-affecting bugs, both root-caused this batch.**
[INV-012](../04-investigations/INV-012-otp-verification-account-binding-bugs.md)
found critical OTP verification/account-binding bugs. Separately,
[INV-013](../04-investigations/INV-013-dashboard-stuck-loading-after-analytics-navigation.md)
root-caused BUG-002 — the dashboard getting stuck on a loading state after
navigating from Analytics — to an uncached, uncancellable request sitting
inside a blocking `Promise.all`. The Analytics load-time investigation
(BUG-001/DATA-001) separately confirmed the reported "seed data" XIRR ×100
issue was a test-fixture artifact, not a real bug, via an independently
re-verified golden dataset — but flagged that the *test fixtures themselves*
can mask real schema drift ([R-061](../07-risks-and-debt.md)). The
dashboard's N+1 NAV-lookup pattern (100+ sequential round-trips) was
rewritten into a single grouped join, closing BUG-001's performance
complaint; a smaller residual (no skip-scan index for the per-group `MAX`)
is deferred as low-severity ([R-012](../07-risks-and-debt.md)).

**Fund Scorer v2's methodology is now specified, still not built.**
[ADR-019](../03-decisions/ADR-019-scorer-v2-proprietary-methodology.md)
records a ten-component proprietary fund-scoring formula, approved at the
formula level, distinct from and not replacing the live three-ingredient
ADR-010 formula in production today. The PE/PB valuation-overlay feasibility
question from
[INV-011](../04-investigations/INV-011-scorer-v2-pe-pb-valuation-overlay-feasibility.md)
is now directly corroborated by its own source annex — still an open
product/budget call, not a technical blocker.

**Two more investigations closed out data-quality edge cases.**
[INV-015](../04-investigations/INV-015-staging-rds-missing-analytics-migration.md)
found staging RDS was missing an Analytics migration.
[INV-016](../04-investigations/INV-016-amfi-navall-row-format-change-silently-empties-category-universe.md)
found an AMFI `NAVAll` row-format change was silently emptying an entire
category universe with no error raised — a silent-failure class of bug, not
a one-off. A later QA-driven schema/journey review
([INV-017](../04-investigations/INV-017-schema-and-user-journey-review-2026-09-23.md))
traced three flagged issues to source: two were clarified as intentional
design, one (10-year CAS statement parsing) is still open pending sample
files to test against.

**A large housekeeping pass found no new facts, which is itself the
finding.** The legacy `Docs/` folder (58 files, leftover from early-batch
staging) was individually verified byte-for-byte against what's already
ingested — 56 identical, 2 older superseded drafts — and archived with
nothing new drafted. `Docs/orchestration/` and `Docs/superpowers/plans`
(clusters 1, 2a-2d, and batch-7 sub-3a through sub-7, covering PAN/CAS
attribution detail, the AWS/infra next-increment plan, email OTP→SES
corroboration, and five root project files) mostly corroborated existing
records with implementation-level detail rather than surfacing new
decisions. Where it did surface something new: the AWS/infra plan closes an
IAM gap (`backend_task`'s runtime role previously had zero S3/KMS access);
a small dead-API-field pair (`parse_warnings`/`warnings`) was noted from a
2026-09-18 plan's own self-review; and Postgres has been confirmed live in
staging since 2026-09-09 with an `EXPLAIN ANALYZE` follow-up still pending
(R-012 addendum). The phone-OTP unrecognized-number account-creation bug
(R-056) was re-confirmed still present as of 2026-09-26.

**Four new risks from the `Notes for Unifolio/` product/engineering
material (batch 6), alongside two real, redacted secrets.** A file named
`Move to Cloud.md` contained a live AWS IAM access key and an RDS master
password (three variant forms) in plaintext — **both were redacted before
the file ever entered git history**, consistent with the existing R-057
gate. New:
[INV-015](../04-investigations/INV-015-staging-rds-missing-analytics-migration.md)
and
[INV-016](../04-investigations/INV-016-amfi-navall-row-format-change-silently-empties-category-universe.md)
(above), plus [R-062 through R-065](../07-risks-and-debt.md) and
[R-068](../07-risks-and-debt.md) (an account-hard-delete
household-cascade/Postgres test gap) and
[R-069](../07-risks-and-debt.md) (an AI/SEBI-advice-boundary question,
cross-linked to R-066's PAN-ownership question).

**New work this session, not yet built:** an approved design spec
(2026-09-29) and a ten-task implementation plan (2026-09-30) for publishing
this vault itself as a password-gated stakeholder documentation site —
MkDocs Material, Vercel Hobby hosting at
`internaldocumentation.unifolio.in`, shared-password Edge Middleware,
evidence treated as secondary-tier content. Nothing has been scaffolded
yet.

**Where the product stands.** Unchanged from batch 4 at the feature level
(sign up, onboard, add family members, upload CAS statements, see a valued
dashboard plus the precomputed Analytics dashboard, rebuilt CAS import
lifecycle, cadence-projected SIP tab, vector-PDF analytics export,
portfolio-wide distributor comparison, plain-English Fund Score verdict) —
this batch's changes are almost entirely about what's *decided and
documented* (PAN, CAS retention, SES, Scorer v2 methodology) versus what's
actually *running in staging*, which remains materially unchanged.

**Four things nothing works without, still none confirmed done:**

1. **Neither OTP channel delivers a real message** (R-024, R-025) —
   unchanged; the SES cutover replaces the transport, not this gap.
2. **There is still no Privacy Policy page** (R-023) — untouched by any
   batch since 2c.
3. **Whether the 2026-09-11 staging runbook ever ran to completion** is
   still unconfirmed (R-052) — the AWS go-live readiness report (now
   directly ingested, batch 5) confirms in-process-cache hardening but
   doesn't settle this.
4. **Both the RDS staging password and the AWS IAM key are still live and
   unrotated** (R-057) — unchanged; must be rotated before production.

**Two open items still explicitly deferred by product-owner decision, not
oversights, unchanged this batch:** phone-OTP silently creating accounts
for unrecognized numbers (R-056, re-confirmed present 2026-09-26), and the
SIP tab switcher's low-severity ARIA IDREF gap (R-055).

**The open questions most worth a decision now:** PAN *ownership*
verification at signup (R-066, research complete, decision pending — the
storage/encryption question itself is now decided per ADR-007 above), and
the CAS-file retention window that's built but not scheduled to actually
run (R-070).

Still true from earlier batches: two incompatible fund-score methodologies
remain on the books pending a product call (R-015, now sharpened by ADR-019
adding a third, unbuilt methodology), the desktop Main Dashboard is still a
placeholder stub while mobile is mature (R-037), and the marketing brief's
"powered by MFCentral" claim is still wrong (R-046).

**Next:** with the code-repo pull and legacy-duplicate archive both fully
ingested and the inbox now empty, a direct verification pass against the
live code repo (not repo-authored docs) is the highest-value remaining
action — most risk entries across all batches are still marked "to verify"
for that reason. In parallel, the internal documentation site's
implementation plan is ready to execute.
