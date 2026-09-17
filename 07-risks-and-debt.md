# Risks and Technical Debt

> Single running file until it outgrows a comfortable single-file size,
> then splits into per-risk files. Never trim past entries — mark
> resolved, don't delete.

## Contradictions between source documents — unresolved, needing a human decision

### R-001 — Is the PAN stored, or not? (Resolved — see ADR-007, 2026-09-16)

`Updated-CAS-PRD.md` FR-4 requires matching a CAS-parsed PAN against PAN values **stored
on file per family member** — exact match on a "well-formed 10-character alphanumeric"
value, "decrypted only in-memory at match time, consistent with the PAN encryption-at-rest
policy." That requirement presupposes both stored PANs and a PAN encryption-at-rest
policy.

This contradicted three other documents directly: PRD-01 FR-2, the Database Schema's Data
Classification table ("**Not persisted at all** … No PAN column exists anywhere in this
schema"), and the TDD's Security NFR ("PAN never persisted (confirmed)").

**Resolved 2026-09-16:** the founder/product decision is to store each family member's
PAN, encrypted at rest, to support the FR-4 matching requirement. See
[ADR-007](03-decisions/ADR-007-pan-storage-and-encryption.md). This is a confirmed
direction, not yet implemented — no PAN column exists in the schema today, and a future
migration is required. PRD-01's "no PAN" statement and the TDD's "PAN never persisted"
NFR are now stale in light of this decision; they have not been edited (the vault never
edits source material), but should not be read as current. DPDP Act compliance
implications of storing a government tax ID are follow-up work, not something this ADR
resolves.

### R-002 — Is the raw CAS PDF retained? (Open, high)

ADR-004 is final and unambiguous: "not in S3, not elsewhere," resolved on DPDP-Act
data-minimisation grounds. `Updated-CAS-PRD.md` FR-3 Security and its NFR table say that
"if the raw PDF is retained at all post-parse, it must be encrypted at rest with a short,
enforced retention window (e.g. 7 days)."

**Recommended resolution (not applied):** ADR-004 stands as authoritative — it is a
formal, Accepted decision record with reasoning; the PRD language is conditional ("if …
at all"), reading more like a defensive clause than a requirement. Confirm and the
conflict closes.

### R-003 — Three different transaction dedupe keys (Open, medium)

| Source | Key |
|---|---|
| `Updated-CAS-PRD.md` FR-6 | folio + scheme + date + type + amount (**no units**) |
| `PRD-01` FR-9 | folio + scheme + date + amount + units (**no type**) |
| Database Schema v1.2 / migration 0002 | **`(folio_id, date, amount, units, type)`** |

**Recommended resolution (not applied):** the schema's five-column key is the implemented
fact and the architecture records state it as such. The PRDs are stale. The schema's own
rationale is documented and convincing — with amounts and units normalised to positive
magnitudes, an equal-magnitude same-day purchase and redemption pair was not
sign-distinguishable and collided under a four-column key. **Both PRDs should be
corrected; neither has been.**

### R-004 — Two unreconciled generations of the CAS import flow (Open, medium)

`PRD-01` + `App-Flow-Unifolio.md` v1.2 describe a queue-based family upload built into
the onboarding screen sequence (S24 → S25 → S26). `Updated-CAS-PRD.md` +
`Updated-CAS-App-Flow.md` describe a server-backed, queue-driven modal Import CAS panel
with Request/Upload tabs, an 11-state lifecycle, and an attribution dialog.

The second generation is newer and implementation-ready, and the Database Schema has
already absorbed its lifecycle enum and coverage-gap columns — which is good evidence
that it is the live generation. But the two have never been merged, and PRD-01 has not
been marked superseded.

**Recommended resolution (not applied):** mark the newer pair authoritative for import
behaviour and annotate PRD-01 and App-Flow v1.2 as superseded *in the import sections
only* — they carry material (Direct/Regular classification, ARN capture, the full screen
inventory) that the newer pair does not.

### R-005 — `family-members` vs `household-members` (Open, low but spreading)

`Updated-CAS-App-Flow.md`'s endpoints use `/family-members/{id}/…`. The TDD's API surface
uses `/household-members/{id}/…`. The schema table is `household_members`. The UI language
is "family." Cheap to fix now; annoying once it is in client code and URLs.

### R-006 — `Updated-CAS-PRD.md` has a corrupted find-and-replace (Open, low severity, high nuisance)

The file has had a global replacement of "PAN" → "password" applied to it, producing
nonsense: the analytics event `cas_import_passwordel_viewed` (was
`cas_import_panel_viewed`), "help passwordel" (panel), "passwordmatch" (PAN match), and
"multi-password/" (multi-PAN). The companion `Updated-CAS-App-Flow.md` still contains the
original wording in the same places — "Captures PAN/name/email," "multiple PANs found,"
"PAN-match lookup" — which proves what the original text said.

**No drafted record in this batch inherits the corruption.** The source file needs
repairing before anyone reads it fresh and implements an analytics event literally named
`cas_import_passwordel_viewed`.

### R-007 — PRD-01 contains a stale scope statement (Open, low)

PRD-01 says "No auth in this build phase — single implicit portfolio per the current
prototype scope." This is contradicted by PRD-02, the multi-user schema, and everything
built since. Harmless in context, actively misleading out of it.

### R-008 — PRD-02's frontmatter is stale against its own body (Open, trivial)

Frontmatter reads `version: "1.3"`, `updated: 2026-08-05`; the body's revision history
carries a 1.4 row. Noted only because version numbers are how the next reader decides
which document to trust.

## Technical debt

### R-009 — Test fixtures for the parse-accuracy NFR do not exist (Open, high)

The ≥98% parse success rate and 100% calculation accuracy targets are backed by
hand-verified known-answer CAS fixtures. Per PRD-01's Dependencies: the **CAMS fixture
was requested but not in hand**, and the **KFintech fixture had not been requested at
all**. The headline quality numbers for the product's core feature currently have no
evidence behind them. This is the highest-leverage item on this page.

### R-010 — Three reverse-engineered integrations, unproven at production frequency (Open, medium)

AMFI TER, AMFI AAUM, and NSE Indices are reached through endpoints reverse-engineered
from the sites' own traffic, live-verified once on 2026-08-10. They are undocumented,
uncontracted, and can change without notice — NSE already moved off its `.aspx` path
once, killing a previously-working endpoint. All three feed the same Analytics Dashboard,
so a simultaneous cluster failure would degrade it noticeably even with per-source
stale-data fallbacks. **Build and exercise these early rather than last.**

### R-011 — The Fargate placement-failure alert is a silent single point of failure (Open, medium)

AWS documents occasional Fargate capacity transients causing a scheduled task to **not
start at all**, with no error surfaced anywhere. The mitigation is a known pattern — an
EventBridge rule watching for `SERVICE_TASK_PLACEMENT_FAILURE` — but it is a setup task
that must actually be done. Until it is, a scheduled NAV refresh can silently not run and
the only symptom is stale prices.

### R-012 — Deferred `LATERAL` optimisation in `category_ranking.py` (Open, low)

`_bulk_nav_on_or_before` was rewritten from an N+1 pattern (100+ sequential ORM
round-trips) to one `MAX(date) GROUP BY scheme_id` join per target date, closing BUG-001.
A residual remains: without an index structure supporting a per-group skip-scan, the
database still scans every historical row per scheme to compute each `MAX(date)` —
bounded in what Python touches, not in what the DB reads. Cost is bounded to once per
15-minute cache TTL per category, not per request.

**The measurement matters more than the finding.** Benchmarked 2026-08-19 against the real
dev database (410,845 NAV rows, 143 schemes in one category, up to 5,020 rows per
scheme): current approach ~3.5s across three target dates; the per-scheme
correlated-subquery reformulation — SQLite's closest equivalent to the `LATERAL` shape,
confirmed by `EXPLAIN QUERY PLAN` to actually do the seek-per-scheme — measured
**~4.6s, slower.** Per-row invocation overhead outweighed the row-scan saving at this
scale.

**Action once Postgres is live:** `EXPLAIN ANALYZE` the three queries at realistic
category size. If the planner is not already using an index-backed skip-scan, rewrite as
a `LATERAL` join backed by the composite index on `(scheme_id, date)` — then re-run
`EXPLAIN ANALYZE` to confirm the plan actually changed before calling it closed. **Do not
assume the direction; the SQLite result shows theory can be wrong in practice here.**

### R-013 — ECS Express Mode is newer than what it replaces (Open, low)

Launched November 2025. Less battle-tested, thinner community tooling than App Runner had.
Accepted knowingly in ADR-005; mitigation is a light documentation and tooling check
closer to implementation.

### R-014 — Documentation drift against migrations is a recurring failure, not a one-off (Open, medium)

The schema document was found three to four migrations stale on 2026-09-02, and a second
audit pass the same day found an index it had never documented at all. There is no
mechanism preventing recurrence. The vault's response is to treat the schema document as
lagging by default, which manages the symptom rather than the cause.

## Deferred by decision (not debt, tracked so it is not lost)

- **Cap-wise portfolio composition and stock-level overlap between funds** — deferred in
  both PRD-03 and PRD-04 with a standing reminder carried in each.
- **Full auth and security policy** — rate-limiting rules, lockout thresholds,
  session-expiry specifics, device management. A separate future PRD; the Auth service
  implements only the base flow it will build on.
- **MFCentral OTP/API import and Account Aggregator import** — both gated behind an AMFI
  ARN / SEBI registration path the company does not yet have. Regulatory, not technical.
- **Connection pooling** (PgBouncer or RDS Proxy) — a known future tuning knob, not a
  launch blocker (ADR-003).
- **Partition maintenance automation** — creating next year's partition ahead of time;
  an operational runbook item not yet written.
- **A Django admin-style internal ops tool** — the agreed answer if internal tooling need
  appears, rather than reopening ADR-002.
