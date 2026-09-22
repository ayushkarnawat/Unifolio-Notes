# Current Status

_Overwritten each update — this is a snapshot, not a history. For
history, see `02-journey/`._

**As of 2026-09-22:** Batch 2c ingested — 2026-09-02 to 2026-09-16, picking
up three weeks after batch 2b's material ends. The vault now holds seventeen
decisions (ADR-001 to ADR-017), eight investigations, twenty journey stages,
an eight-section architecture description, and a risk register of
fifty-four items. Nothing from earlier batches has been rewritten.

**The single most important thing this batch changes about the picture:**
the pattern from batch 2b — heavy design, light build — partly reverses.
The Analytics precompute rework (ADR-015) was designed on 2026-09-02 and
is confirmed **merged and green** by 2026-09-10 (628 passed/6 skipped),
resolving a risk this vault had been carrying open since batch 2b (R-042).
The frontend caught up the same week, an AMFI ingestion bug was found and
fixed same-day (INV-008), and a detailed staging deployment runbook was
written on 2026-09-11 — though whether that runbook was actually run is
unconfirmed. A second thread, the Fund Score card redesign (ADR-017,
2026-09-11), was fully designed and planned but has **no execution evidence
anywhere in this batch** (R-053) — the two threads sit at opposite ends of
the same fortnight.

**Where the product stands.** The live-compute-on-read pattern behind
Analytics is gone: a `analytics_sections` table now stores each section per
household, recomputed via ECS Fargate `RunTask` and read through one
consolidated endpoint. This is the mechanism batch 2b's loading-state
decision had assumed but that this vault could not previously confirm
existed (R-042, now resolved). What a user can do is otherwise unchanged
from batch 2b — sign up, onboard, add family members, upload CAS statements,
see a valued dashboard — plus, if built, a plainer-English Fund Score card
still awaiting confirmation.

**A new finding this batch: infrastructure can drift ahead of the notes
describing it, silently.** Preparing the 2026-09-11 staging runbook, a
`terraform plan` run mid-session showed HTTPS, CloudFront, and the
analytics dispatcher's task definition already applied — from a stray
plan file predating the session — while the draft runbook still described
them as "not yet applied." Caught and reconciled once; nothing says this
can't happen again (R-052).

**Three things nothing works without, and none of them is confirmed done
by this batch's material:**

1. **Neither OTP channel actually delivers a message**, per batch 2b
   (R-024, R-025) — this batch's staging scope explicitly keeps real OTP
   delivery and Google Sign-In out of the beta pass, deliberately, not as
   an oversight.
2. **There is still no Privacy Policy page** (R-023) — untouched by this
   batch's material.
3. **The database migration chain has moved to `0014`**
   (`0012_analytics_sections`, `0013_account_deletion_grace_period`,
   `0014_analytics_recompute_generation`), and as of the 2026-09-11 runbook
   none of the three had yet been applied to the real staging RDS instance.

**The open question most worth a decision, still:** PAN storage and
encryption (R-043) — **nothing in this batch bears on it directly.** None
of the nine source files mention PAN. The question remains exactly where
batch 2b left it.

**Also worth noting: this vault redesigned and rebuilt itself.** On
2026-09-16, the vault's own structure — the one this document lives in —
was designed (ADR-016) and fully executed the same day, confirmed against
this repository's own `git log`. It is recorded as a journey stage and a
decision like any other piece of delivered work, since it is one.

Still true from earlier batches: two incompatible fund-score methodologies
remain on the books pending a product call (R-015), the desktop Main
Dashboard is still a placeholder stub while mobile is mature (R-037), and
the marketing brief's "powered by MFCentral" claim is still wrong (R-046).

**Next:** a verification pass against the current code repo remains the
single highest-value action — most of both this batch's and the prior
batch's risk entries are marked "to verify" for the same reason. Also
outstanding: the `AWS Readiness/aws-golive-readiness-report.md` document
referenced (but not ingested) in this batch's runbook is a candidate for a
future batch (R-054).
