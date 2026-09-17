# Decisions Log

> Append-only, dated log of smaller decisions. Distinct from `ADR-XXX`
> files, which are reserved for major decisions with full
> alternatives-considered writeups — this file covers everything else,
> and links to an ADR by reference rather than restating it once a
> decision graduates to one. Never trim or rewrite past entries — append
> corrections/reversals as new dated entries instead.

## 2026-07-22 — Four logical backend services in one FastAPI deployment

Auth, Import, Dashboard, and Analytics are logical boundaries inside a single FastAPI
application, not four deployments. **Why:** the same team-size reasoning as ADR-001,
applied to the backend — four deployments would multiply operational surface for a
three-person team with no independent-release need. Graduates to an ADR only if
independent deploy cadence ever becomes the binding constraint.

## 2026-07-22 — The family aggregate default is computed, never stored

Whether a user lands on the family-aggregate or per-member dashboard is derived from a
count of their household members at request time. **Why:** a stored `default_view`
column would go stale the moment family composition changed. One fewer piece of state
that can silently disagree with reality.

## 2026-07-22 — No new dependency for fuzzy scheme matching

Scheme-name matching uses the standard library's `difflib.SequenceMatcher`, and the same
idiom is reused for AMFI TER name matching. **Why:** PRD-01's no-new-dependencies
constraint, and the match quality is adequate at the confidence thresholds in use.

## 2026-07-22 — Two allocation endpoints, deliberately not merged

The Dashboard service keeps its coarse `/household-members/{id}/allocation`
(`by_asset_class`, `by_amc`); the Analytics service adds a granular
`/analytics/household-members/{id}/allocation` (`by_category`, plus `by_amc`
re-exposed). **Why:** different granularities for different surfaces. Recorded because it
reads like a route collision and is not one.

## 2026-07-22 — ARN resolution is on-demand, not scheduled

Distributor-name lookup runs inline when the Import Service first sees an unfamiliar ARN
code, rather than as a scheduled job. **Why:** it is event-triggered by an import, not
time-triggered, and it must never block — the fallback is displaying the raw ARN code.
See ADR-006, which confirms this scoping rather than changing it.

## 2026-07-22 — `relationship` is a fixed enum plus a free-text label for `other`

`self` / `spouse` / `parent` / `child` / `sibling` / `other`, with a free-text label used
only when `other` is chosen. **Why:** structured enough for consistent family-grouping
logic, flexible enough not to force real family shapes into the wrong bucket.

## 2026-07-22 — The CAS PDF is staged in local temp storage, not S3, during processing

Processing reads the uploaded file from local temporary storage with guaranteed
deletion, rather than an S3 upload-then-delete cycle. **Why:** simpler to reason about
and audit, and it avoids a network hop for a file that is meant to be short-lived. This
is a separate question from permanent retention, which ADR-004 settles.

## 2026-07-22 — "100% accuracy" means fixtures, not real-world files

The gain/loss accuracy NFR means 100% of what is computed matches hand-verified
known-answer fixtures. **Why:** claiming 100% of real-world CAS files parse perfectly
would be an unbounded claim. Recorded because the number gets quoted without its
qualifier.

## 2026-08-05 — ADR-001 amended, not rewritten, after its premise proved false

ADR-001 claimed the decision preserved in-progress React work; the prototype frontend
turned out to be vanilla TypeScript. An Amendment section was added and the "no rework"
benefit marked moot; the decision itself stands on its other merits. **Why:** vault rule
— supersede and correct in place, never silently rewrite a past record.

## 2026-08-17 — Authentication is passwordless; the same-day reversal is recorded, not hidden

PRD-02 FR-2 was revised twice on this date — to email + password, then reversed to
email + OTP by management decision. Final state: phone + OTP, email + OTP, or Google,
converging on a mandatory verified phone number. Password storage was removed from the
schema by migrations 0007–0008. **Why:** recorded as a reversal rather than a clean
decision because the churn is the useful fact.

## 2026-08-19 — The `LATERAL` optimisation is deferred, with a benchmark attached

The "obviously faster" per-scheme index-seek rewrite of `_bulk_nav_on_or_before` measured
**slower** on the dev dataset (~4.6s vs ~3.5s) and is deferred until it can be measured
on real Postgres. **Why:** the guardrail against coding blind for one dialect cuts both
ways. The measurement is attached so nobody redoes it on faith. See
`07-risks-and-debt.md`.

## 2026-09-02 — The schema document is treated as lagging the migrations, by default

Where `Database-Schema-Unifolio.md` and the code-repo migrations disagree, the migrations
win. **Why:** a compliance audit found the document three to four migrations stale, and a
second pass the same day found an index it had never specified at all.

## 2026-09-16 — PAN storage direction resolved: encrypted at rest, planned future work

Unifolio will store each family member's PAN, encrypted at rest, to support per-member
matching against CAS filings (`Updated-CAS-PRD.md` FR-4). **Why:** resolves R-001, the
open contradiction between that requirement and PRD-01/schema/TDD's "PAN never
persisted." See [ADR-007](ADR-007-pan-storage-and-encryption.md) — direction confirmed,
not yet implemented; no PAN column exists in the schema today.
