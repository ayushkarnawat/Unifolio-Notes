# Risks and Technical Debt

> Single running file until it outgrows a comfortable single-file size,
> then splits into per-risk files. Never trim past entries — mark
> resolved, don't delete.

## Contradictions — unresolved, needing a human decision

> Two kinds live here: disagreements between source documents, and
> disagreements between what this vault records and what was actually built.
> The second kind is the more dangerous — the vault reads as settled when it
> is not.

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

**Appended 2026-09-17 (batch 2a).** The reasoning above is now backed by a
full investigation rather than inferred from the schema's rationale:
[INV-003](04-investigations/INV-003-transaction-dedupe-silent-drop.md)
reproduces the collision, traces it to the amount/unit normalisation change
that removed the distinguishing sign, and records that migration `0002`
widened the database constraint and the application-side check **in the same
change** — widening only one side would have converted silent drops into
500-level integrity errors. This strengthens the recommendation; it does not
change it. Both PRDs are still uncorrected.

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

**Update, 2026-09-22.** The 11-state lifecycle this risk names as "newer,
implementation-ready" has since been built and merged — see
[ADR-018](03-decisions/ADR-018-cas-import-lifecycle-redesign.md). This
confirms which generation is live, narrowing this risk's uncertainty, but
does **not** close it: nothing in the newly-ingested source material shows
PRD-01/App-Flow v1.2 were ever annotated as superseded, and the
implementation itself has not had the independent review pass this vault's
other features get before being called fully done (also tracked in
ADR-018). Status left Open.

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

### R-015 — Two fund-score methodologies recorded, not a contradiction (Clarified 2026-09-17 — two distinct, non-conflicting methodologies)

**As originally recorded (2026-08-13):** two fund-score methodologies both
appeared current in the vault:

| Source | Ingredients | Tier boundaries | Positioning |
|---|---|---|---|
| `05-docs/explanation/fund-scoring-methodology.md` (from PRD-04, batch 1) | Two — risk-adjusted return, plus a cost overlay | 10% / 22.5% / 35% / 22.5% / 10% | "Modelled on Morningstar" |
| [ADR-010](03-decisions/ADR-010-fund-scorer-composite-formula.md) (product-owner conversation 2026-08-13, implemented) | **Three** — 45% return, 30% downside deviation, 25% rolling 12-month consistency | **Even quintiles** | "Must be different from Morningstar and CRISIL" |

This was flagged as an open contradiction needing a product call — a
user-facing number computed one way and explained the other.

**Clarified 2026-09-17 (batch 2a).** These are not two competing
descriptions of the same live score. They are two different things at two
different stages:

1. **ADR-010's three-ingredient composite is the current, live methodology.**
   It is what shipped on 2026-08-13 and what the code computes today. The
   methodology page's two-ingredient formula is superseded for what is
   actually live — the page has been annotated with a status banner rather
   than rewritten (vault mechanic, not a decision).
2. **A separate, updated methodology based on per-fund stock-holdings data is
   planned**, but is blocked pending availability of that holdings data, and
   is not yet documented anywhere in the vault. This is a forward-looking
   initiative, not a live discrepancy — there is no user-facing number today
   computed from it.

No product call is needed to pick a winner between the two; they are not
competing for the same slot. What remains open is only the ordinary
follow-through: writing up the holdings-based methodology once the blocking
data question is resolved, and formally superseding PRD-04 FR-5/FR-5a in
favour of ADR-010 for the live score.

Source for this clarification: vault owner, live conversation, 2026-09-17 —
not yet corroborated against a written plan or spec; corroborate against
source material if one surfaces in a later batch. See the
[2026-09-17 decisions-log entry](03-decisions/decisions-log.md).

**To verify:** cross-check against the current state of the Unifolio code
repo once the documentation phase is further along. Several items like this
are expected to already be fixed in later work; if so, record that as a
dated resolution here, not a silent edit.

### R-016 — Which service owns ARN resolution, and what triggers it (Open, medium)

| Source | Service | Trigger |
|---|---|---|
| decisions-log 2026-07-22, [ADR-006](03-decisions/ADR-006-background-job-scheduling.md), `06-architecture/runtime-and-data-flow.md`, `05-docs/reference/external-data-sources.md` | **Import** | Inline, the first time a previously-unseen ARN code appears in a parsed statement |
| 2026-08-07 distributor-comparison design, as implemented ([INV-004](04-investigations/INV-004-amfi-arn-distributor-lookup.md)) | **Dashboard** | The distributor-comparison read path |

Both are "on demand," which is why the difference is easy to miss and why
ADR-006 reads as confirmed when it is not. The difference is real: it changes
which user action pays the latency of the first lookup for a given ARN,
whether an ARN is ever resolved for a user who never opens the comparison
screen, and which service owns the failure path.

**Recommended resolution (not applied):** the implemented placement is
probably right — the lookup's only consumer is the comparison screen, the
FIFO and NAV helpers it reuses live in Dashboard, and resolving at import
time would do work that may never be read. If so, the correct action is an
**amendment to ADR-006** and a correction to the decisions-log via a new
dated entry, not an edit to either. Both the architecture page and the
external-data-sources page have been annotated with the discrepancy rather
than silently switched.

**To verify:** cross-check against the current state of the Unifolio code
repo once the documentation phase is further along. Several items like this
are expected to already be fixed in later work; if so, record that as a
dated resolution here, not a silent edit.

### R-017 — Two shapes recorded for the distributor-comparison route (Open, low but concrete)

`05-docs/reference/api-surface.md` carries `GET /funds/{scheme_id}/distributor-comparison`,
from the TDD. The 2026-08-07 design corrected the route to sit under the
household member — `GET /household-members/{id}/distributor-comparison` — on
the reasoning that "your returns by distributor" is meaningless without
knowing whose returns, and that is what was built.

The TDD's shape is not merely differently-named; it is missing a parameter
the feature needs. **Recommended resolution (not applied):** the
member-scoped route is correct and the TDD's API table is stale. Both rows
are currently listed in the API reference with the conflict stated. Cheap to
close; it only stays open because nobody has said so.

**To verify:** cross-check against the current state of the Unifolio code
repo once the documentation phase is further along. Several items like this
are expected to already be fixed in later work; if so, record that as a
dated resolution here, not a silent edit.

### R-018 — A permanent test enforces the opposite of ADR-007 (Open, medium)

On 2026-08-04 a guard test was added at
`backend/tests/models/test_no_pan_field.py` whose only purpose is to **fail if
any model grows a PAN-shaped column**. It was added deliberately, because the
retired prototype had been persisting a masked PAN on two tables in violation
of the project's own rule.

On 2026-09-16, [ADR-007](03-decisions/ADR-007-pan-storage-and-encryption.md)
decided PANs **will** be stored, encrypted at rest, to support
`Updated-CAS-PRD.md` FR-4 per-member matching.

Implementing ADR-007 therefore requires deliberately deleting or inverting a
test that was written to prevent exactly that. That is fine — it is what
supersession looks like — but it must be a decision, not a surprise
discovered mid-migration by whoever writes the PAN column.

**Recommended resolution (not applied):** when ADR-007 is implemented, the
guard test is replaced rather than deleted — inverted into an assertion that
PAN columns exist **only** on the approved table and **only** in encrypted
form, so the protection the original test provided (no PAN leaking onto an
unintended table) survives the change. Record the swap as a decisions-log
entry citing both R-018 and ADR-007.

**To verify:** cross-check against the current state of the Unifolio code
repo once the documentation phase is further along. Several items like this
are expected to already be fixed in later work; if so, record that as a
dated resolution here, not a silent edit.

### R-019 — The analytics frontend is designed against a component library that is not installed (Open, medium)

Two documents dated **2026-08-14** disagree:

- `2026-08-14-analytics-frontend-design.md` specifies Bklit UI for "mostly
  everything," with one deliberate carve-out (the existing allocation donut,
  reused unchanged).
- `2026-08-14-multi-method-auth-frontend-plan.md` performed a branch-reality
  check before writing anything and found that **Bklit UI is not installed**.
  The project's component configuration registers its registry as a
  pull-on-demand source; no package exists. Tailwind and shadcn/ui *are*
  genuinely in use. The auth showcase panel was consequently hand-built on
  the existing chart primitives.

The branch check is the stronger evidence — it is an observation of the
repository, not a design intention. But the analytics design was not revised
after it, and implementation was assigned to an external agent
(R-029) who will read the design, not the branch check.

**Recommended resolution (not applied):** decide whether Bklit UI is being
adopted. If yes, install it and say so; if no, revise the analytics frontend
design before the external agent builds against a premise that is false.
Either way this should be settled **before** the implementation handoff, not
discovered during it.

**Update, 2026-09-23 — resolved.** The analytics frontend was built
2026-08-14 across two phases; source material for both confirms Bklit UI
was never installed or adopted. See the 2026-09-23 addendum on
[02-journey/2026-08-14-multi-method-auth-and-the-analytics-frontend.md](../02-journey/2026-08-14-multi-method-auth-and-the-analytics-frontend.md).

### R-020 — "AUM-weighted" is used with two different meanings in PRD-04 (Open, low)

Flagged during the 2026-08-10 analytics research rather than silently
unified. PRD-04 uses the phrase both for weighting a *portfolio's* score by
the user's own holding values, and for weighting across the *fund universe*
by scheme AAUM. These produce different numbers and answer different
questions.

**Recommended resolution (not applied):** name them separately in the
implementation and in the methodology document — "holding-weighted" for the
portfolio rollup, "AAUM-weighted" for anything computed across the universe.
No code change is implied; the risk is entirely that one is implemented where
the other was meant.

### R-035 — The app auto-switches to mobile on viewport width, and a repo document says it must not (Open, medium)

`App.tsx` renders the mobile tree when the route is a mobile route **or** when
a `max-width: 767px` media query matches. The code repo's
`Docs/MOBILE_APP_EXECUTION.md` states that mobile must not automatically
replace the web experience based on viewport or device detection. Both cannot
be right.

The 2026-08-19 mobile system plan found this, recommended keeping the code and
correcting the document, and said explicitly that it was flagging rather than
silently picking a side. The recommendation has not been applied — the document
in question lives in the code repo, which this vault does not modify.

**Recommended resolution (not applied):** correct
`Docs/MOBILE_APP_EXECUTION.md` in the code repo, or remove the viewport clause
from `App.tsx`. The mobile design work assumes the current behaviour, so
changing the code is the more expensive option.

**To verify:** cross-check against the current state of the Unifolio code repo.

*Source: `08-evidence/documents/specs/2026-08-19-mobile-uiux-system-plan.md` §0.1*

**Update, 2026-09-23 (batch 4d).** `Docs/MOBILE_APP_EXECUTION.md` itself is
now directly ingested — previously this vault only had the mobile plan's
indirect citation of it. Its exact text: "mobile preview must not
automatically replace the web experience based on viewport/device
detection." This confirms the 2026-08-19 plan's characterisation precisely;
it does not resolve the contradiction, since `App.tsx`'s behaviour has not
been re-checked against the current code repo. Status unchanged: **Open**.
*Source: `08-evidence/documents/MOBILE_APP_EXECUTION.md`*

### R-043 — PAN persistence now has five dated positions across five dates (Open, high — direction reaffirmed 2026-09-19, detailed documentation pending)

The most consequential open question in this batch. In date order:

1. **Through batch 1 and 2a** — PAN is never persisted. A permanent guard test
   was added on 2026-08-04 to keep it that way. R-001 tracked the resulting
   conflict with the CAS PRD's per-member matching requirement.
2. **2026-08-25**, the Phase 2 demat research and decision memo, both as a
   stated starting constraint — "the 'no PAN persistence, ever' rule is being
   rewritten: Unifolio will now store PAN, **masked wherever displayed**".
   Motivated by automated statement ingestion.
3. **2026-08-26**, the Phase 2 backend plan, deviation 1 — "Decided during
   planning: **keep never-persisting PAN.** Revisit if/when that reversal
   actually lands in the schema."
4. **2026-09-16**, already in this vault — ADR-007 and the matching
   decisions-log entry: PAN **will** be stored, **encrypted at rest**, to
   support per-member matching against CAS filings (FR-4). Direction confirmed,
   not implemented.
5. **2026-09-19**, live conversation with the vault owner — PAN
   storage direction reaffirmed: encrypted at rest, and encrypted in
   transit (most likely TLS 1.3, inferred from a spoken "TLS 3.1," not
   independently confirmed). Detailed documentation is pending from a
   colleague and has not yet been written. This reaffirms position 4
   (ADR-007) rather than replacing it, and adds the in-transit detail that
   ADR-007 did not specify.

Positions 2 and 4 are not the same decision. Masked-on-display is a
presentation control; encrypted-at-rest is a storage control. They have
different threat models, different implementation work, and different
motivations — statement ingestion versus per-member matching. A design that
satisfies one does not necessarily satisfy the other.

There is also a contradiction **inside a single document**: the 2026-08-25
decision memo lists the rule-being-rewritten as a starting constraint, and
then, discussing browser-native pickup conveniences, states that the same
clipboard trick "cannot extend to PAN — Unifolio's own schema already has a
hard 'no PAN persistence, ever' rule, so we structurally can't remember it even
for this."

Nothing in the schema has changed either way. No PAN column exists today.

**Direction is reaffirmed but not yet fully settled.** As of 2026-09-19: (a)
PAN is most likely stored — yes; (b) most likely both encrypted at rest and
encrypted in transit; (c) for per-member CAS matching (FR-4), per ADR-007 —
the 2026-08-25 masked-on-display / statement-ingestion motivation is not
reaffirmed and is not known to still be live. What remains open: the
colleague's detailed documentation, which will need to be ingested as its own
future batch once it exists, and formal confirmation of the in-transit
mechanism. A DPDP Act assessment is still outstanding regardless, per
ADR-007's own follow-up note.

*Sources: `08-evidence/documents/specs/2026-08-25-phase-2-stocks-demat-research.md` §7-A and §8a; `08-evidence/documents/specs/2026-08-25-phase-2-demat-integration-decision-memo.md` constraints and option H; `08-evidence/documents/plans/2026-08-26-phase-2-stocks-demat-import-backend.md` deviation 1; ADR-007; vault owner, live conversation, 2026-09-19*

### R-046 — The marketing brief's trust-bar claim contradicts how Unifolio actually imports statements (Open, high — launch-facing)

The 2026-08-31 marketing brief's placeholder trust-bar copy reads "Works with
your CAS from every AMC — powered by MFCentral", and justifies it on the
grounds that the repository's CAS ingestion is built against the MFCentral API.

This vault records the opposite. `05-docs/explanation/why-we-parse-cas-pdfs.md`
documents user-uploaded CAS PDFs parsed with `casparser`. The
"Deferred by decision" list already records MFCentral OTP/API import and
Account Aggregator import as gated behind a regulatory path the company does
not hold. This same batch's Phase 2 research costs MFCentral-class access as a
future phase, not a current capability.

The brief does ask for a marketing and legal check before launch, and flags
that any AMC-count claim needs a real number. That instinct is right; the
justification behind the claim is not. This is the kind of statement that gets
repeated by press and by answer engines — and the brief's own strategy is
built on repeating entity statements verbatim so answer engines converge on
them.

**Recommended resolution (not applied):** replace the claim with one grounded
in what the product does, and confirm the real AMC coverage number, before the
brief goes to Manus as final.

*Source: `08-evidence/documents/specs/2026-08-31-marketing-website-design.md` §3 (Home), §6 item 3*

### R-047 — The demat decision memo cites a PRD that does not exist (Open, low)

The 2026-08-25 decision memo references `PRD-05-Stocks-Demat-Import.md` as a
source. The 2026-08-26 backend plan states that document does not exist. One
of the two is wrong about the input to a phase of work, which matters because
the memo's recommendation was accepted on the strength of its sourcing.

**To verify:** cross-check against the current state of the Unifolio code repo
and its `Docs/PRDs/` folder.

*Sources: `08-evidence/documents/specs/2026-08-25-phase-2-demat-integration-decision-memo.md`; `08-evidence/documents/plans/2026-08-26-phase-2-stocks-demat-import-backend.md`*

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

**Appended 2026-09-17 (batch 2a).** There are now **four**, not three. The
category universe (AMFI's daily full-NAV text file, parsed by section
heading) is a fourth undocumented, uncontracted integration — and it depends
on a *formatting convention*, which is weaker than an endpoint contract, not
stronger ([INV-001](04-investigations/INV-001-category-universe-gap.md)). The
ARN lookup ([INV-004](04-investigations/INV-004-amfi-arn-distributor-lookup.md))
is a fifth if counted, though it never blocks and degrades to displaying the
raw code.

The NSE move this entry already cites was root-caused on 2026-08-10:
[INV-002](04-investigations/INV-002-nse-index-endpoint-staleness.md). **The
important detail is the failure mode.** The old endpoint did not 404 — it
kept responding and served stale data. An availability check reports that
healthy. What would have caught it is a *freshness* assertion, and nothing
currently makes one. "Build and exercise these early" should be read as
"build and exercise these early, with freshness assertions, not liveness
checks."

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

### R-021 — The PostgreSQL branch of migration `0002` has never been executed (Open, medium)

Migration `0002_transaction_dedupe_includes_type` has two dialect paths: a
SQLite batch table rebuild (SQLite cannot alter a constraint in place) and a
PostgreSQL `ALTER` on the partitioned parent, which propagates to every
partition. **Only the SQLite path has ever run.** No live PostgreSQL instance
existed in the development sandbox on 2026-08-06, so the PostgreSQL branch
was written and reviewed but not executed.

Both paths **look the existing constraint's name up at migration time**
rather than hardcoding it, because migration `0001` let each dialect
auto-generate that name. That is the right design and it is also the part
most likely to behave differently unexecuted — a lookup that returns the
wrong row on Postgres drops the wrong constraint, and the failure surfaces
during the production cutover.

This is a specific instance of the general exposure: the product develops on
SQLite and ships on PostgreSQL, and the dual-dialect CI from Phase 0 covers
the *schema*, not every migration path. **Action:** run the full migration
chain, upgrade and downgrade, against a real PostgreSQL instance before the
cutover — this is a line item for the
[SQLite-to-Postgres runbook](05-docs/how-to/migrate-sqlite-to-postgres.md),
not a separate project.

### R-022 — `transactions.type` is a `VARCHAR` + `CHECK`, not a native Postgres enum (Open, low)

A knowingly-taken corner cut from 2026-08-04, marked in the code with a
`ponytail:` comment naming the ceiling. The reasoning: a native PostgreSQL
enum is materially harder to extend than a `CHECK` constraint, and the
transaction-type vocabulary was expected to grow.

The ceiling is that a `CHECK` constraint gives weaker guarantees than a type
does and is not visible in the type system. **Upgrade path if it ever
matters:** convert to a native enum in a dedicated migration. Recorded so the
choice reads as deliberate rather than as an oversight by whoever finds it.

### R-023 — There is no Privacy Policy page, and Google will not publish a consent screen without one (Open, high — launch blocker)

Surfaced 2026-08-14 during the multi-method auth design.
[ADR-008](03-decisions/ADR-008-phone-anchored-multi-method-identity.md) makes
Google Sign-In a first-class entry method. Google requires a published
Privacy Policy URL before a real OAuth consent screen can leave testing mode.

**No Privacy Policy exists anywhere in the product** — not as a page, not as
a route, not as a draft.

This is the only item in this batch that blocks a user-visible launch rather
than degrading something. It is also not an engineering task: the content is
a legal/product deliverable, and it interacts with the DPDP Act implications
of [ADR-007](03-decisions/ADR-007-pan-storage-and-encryption.md)'s decision
to store PANs, which are themselves unresolved. **Start it early; the
dependency chain is longer than it looks.**

### R-024 — Email OTP cannot work in production; only a stub exists (Open, medium)

[ADR-009](03-decisions/ADR-009-transactional-email-provider.md) chose
Postmark, behind an `EmailProvider` protocol. The 2026-08-14 backend plan
explicitly forbids writing a real Postmark implementation or any live sending
call in version 1. So email sign-in — one of the three entry methods ADR-008
makes first-class — works in development, where the code is echoed, and not
at all in production.

The remaining work is deliberately small and isolated: one implementation of
one protocol, plus credentials and domain verification. The risk is not
difficulty, it is that "email login is built" and "email login works" are
both true statements about different things, and only one of them is what a
user experiences.

Also note the cost comparison behind ADR-009 is a point-in-time snapshot of
published pricing and should be re-checked before signing up.

### R-025 — No SMS provider has been chosen; phone OTP is also a stub (Open, medium)

The same shape as R-024, a week earlier and more fundamental. Phone+OTP has
been the product's only login method since 2026-08-05 and remains the
mandatory anchor for every account under ADR-008 — and it has **never sent a
real message.** The 2026-08-05 plan shipped a development-only delivery mode
that echoes the OTP back in the response, on the explicit grounds that
choosing an SMS provider is a separate decision.

That decision has still not been made. Unlike email, Indian SMS delivery
carries regulatory overhead — DLT registration, header and template approval
— which is lead-time, not effort, and is not something that can be done in
the week before launch.

**Recommended:** this deserves its own ADR alongside ADR-009, and it should
start before it is needed, for the same reason R-023 should.

### R-026 — Parallel Codex dispatch was verified by reading code, not by running it (Open, low)

[ADR-011](03-decisions/ADR-011-model-orchestration-and-delegated-implementation.md)'s
workflow claims a parallel-dispatch capability. The 2026-08-12 plan's own
verification was reading the plugin's source to confirm the capability
exists; the live smoke test was not run. Everything else in that plan is
content and frontmatter verification, which is appropriate for a skill
bundle with no executable code — this one item is the exception.

Low severity because the failure mode is "delegation is slower than
expected," not "something breaks." Recorded because the plan itself was
careful to state it as unverified rather than claim it working, and that
distinction should survive into the vault.

### R-027 — The family CAS upload queue is in-memory and is lost on reload (Open, low)

From 2026-08-06. A user uploading statements for several family members loses
the whole queue if the page reloads mid-flow, and must re-select every file.
IndexedDB persistence was considered and **rejected as premature** — a
deliberate call, not an oversight.

The exposure scales with family size and with file size, which is exactly the
onboarding path the product's core value depends on. The mitigating factor is
that nothing is lost *server-side*; already-parsed previews are not affected,
only the client's pending list. **Revisit when there is real evidence of
users hitting it**, not before — but revisit it with that evidence, rather
than assuming the original judgment holds forever.

### R-028 — Securities transaction tax and stamp duty are not treated as cost-basis-adjusting (Open, low)

Flagged in the 2026-08-06 dashboard design rather than silently assumed.
Cost basis is FIFO over transaction amounts; STT and stamp duty are not
folded in. This makes reported gain marginally optimistic relative to a
tax-accurate basis.

Whether that is correct depends on a question nobody has answered: whether
Unifolio's gain/loss figure is meant to be an *indicative portfolio view* or
something a user might reconcile against a tax filing. PRD-03 does not say.
Small in magnitude, and exactly the kind of thing that becomes expensive to
change once users have anchored on a number. **Needs a product answer, not an
engineering one.**

### R-029 — External coding agents are used as implementers and are not covered by any workflow (Open, medium)

Google Antigravity implemented frontend work on **2026-08-07** (the redesign
brief) and was assigned the analytics frontend on **2026-08-14**, with Claude
Code acting as tester, reviewer and comparator rather than orchestrator. The
2026-08-14 analytics design names this directly: "a third worker category the
model-orchestration skill doesn't document."

[ADR-011](03-decisions/ADR-011-model-orchestration-and-delegated-implementation.md)
covers Claude Code, Codex and Claude subagents. It says nothing about an
agent outside the team's own tooling, which means none of its guarantees
apply — no handoff-document requirement, no mandatory adversarial review
gate, no escalation policy. The 2026-08-07 brief compensated by hand: a
stated quality bar as a score on a ten-heuristic usability rubric, an
explicit in-scope/out-of-scope split, and a requirement that the agent name
itself as author so the work's provenance stays traceable. That was good
practice invented per-occasion, which is precisely what ADR-011 exists to
stop being necessary.

**Recommended resolution (not applied):** amend ADR-011 (append, do not
rewrite) with an external-agent worker category, and promote the 2026-08-07
brief's structure — quality bar, scope split, self-attribution — into the
workflow reference as the required shape for an external handoff.

**Update, 2026-09-23 — corroborated, still open.** The analytics frontend's
actual build (2026-08-14, two phases) is a second occurrence of exactly
this gap, not a new risk: Claude Code again acted as tester/reviewer, and
caught real defects — including two instances of the external agent
self-reporting "tsc clean, all tests passing" when Claude Code's
independent re-verification found both claims false. No amendment to
ADR-011 has been found in any source material ingested so far. See the
2026-09-23 addendum on
[02-journey/2026-08-14-multi-method-auth-and-the-analytics-frontend.md](../02-journey/2026-08-14-multi-method-auth-and-the-analytics-frontend.md).

### R-030 — Apple Sign-In is deferred, and a disabled button ships in its place (Open, low)

Designed and researched on 2026-08-14, then deferred over a $99/year Apple
developer-account fee. The research is preserved and a visibly disabled
"Coming soon" pill ships in the auth method row rather than the option being
removed. ADR-008 records that no provider value for Apple is added anywhere
in the data model, so there is no half-built state in the schema.

Two things to watch. First, a disabled control in production is a promise
with no date on it; if the fee is not going to be paid, the pill should go
rather than sit there indefinitely. Second, if Unifolio ever ships an iOS
app, Apple's App Store review requires Sign in with Apple wherever a
third-party sign-in is offered — at which point this stops being a $99
question. Neither is urgent. Both are cheaper to decide now than to
rediscover.

### R-031 — `users.email` is never backfilled for email-and-password identities (Open, medium)

The 2026-08-17 backend work names this as a known limitation it chose not to
fix: a user who signs up with email and password and fully confirms their
address still gets a null email back from `/auth/me`, because the value is
written to the identity row and never propagated to the user row. The feature
was reversed the same day and password storage was removed by migrations
`0007`–`0008`, so this may no longer be reachable — but the same propagation
gap could exist for any provider that writes an email to an identity.

**To verify:** cross-check against the current state of the Unifolio code repo.

*Source: `08-evidence/documents/plans/2026-08-17-email-password-signup-backend.md`*

**Resolved, 2026-09-23 (per newly-ingested source material, recorded
2026-09-23).** `remove-password-auth-handoff.md` confirms migration `0008`
drops `password_hash` and the related password-auth columns/tables
outright, and `EMAIL_PASSWORD` is benched in favour of `EMAIL_OTP`. The
specific reachability question this entry flagged is now answered: the
`EMAIL_PASSWORD` provider and its associated unbackfilled-`users.email`
code path no longer exist in the current design. This is **not** a full
closure of the underlying propagation-gap pattern, though: the same
question — does a verified email on an identity row reliably propagate to
`users.email`? — has not been checked against `EMAIL_OTP` (the provider
now active in its place) or Google sign-in. Left open as a narrower,
re-scoped question rather than closed outright.

*Resolution source: `08-evidence/documents/orchestration/remove-password-auth-handoff.md`*

### R-032 — PRD-03's SIP behaviour is contradicted by ADR-012 and has no superseding note (Open, medium)

ADR-012 removes the 40-day active-SIP window. PRD-03 FR-6 and its edge-case
table still document it. The design that produced ADR-012 requires a short
superseding note to be added to the PRD, explicitly on the grounds that a PRD
conflict must be flagged rather than silently resolved. That note is a code-repo
document change and has not been made.

This is not urgent while ADR-012 remains unimplemented, and becomes a live
documentation defect the moment it ships.

*Source: `08-evidence/documents/specs/2026-08-18-active-sips-cadence-redesign-design.md`*

### R-033 — One decorative auth panel went through four concepts in 48 hours, with no accepted design record (Open, medium)

In order: a "fund-signal ring" specified on 2026-08-18 and never built; a
chaos-loop-to-grid performance-path graphic with milestone tooltips that is
what actually shipped (commit `75a1925`); a particles-converging-into-the-arc
direction that was "built out through several mockup rounds and ultimately
dropped"; a "fragments align and sharpen" direction specified on 2026-08-19 as
v2.0; and an editorial/typographic "Direction B" planned the same day, whose
first two tasks are ticked.

Each individual rejection was made for a defensible, written reason — which is
the good part, and why the alternatives survive in the evidence. The problem is
the aggregate: an element with no functional requirement absorbed several
rounds of design and at least two rounds of implementation in two days, and no
document in this batch reconciles the last two directions or marks either as
the accepted one.

**Recommended resolution (not applied):** name one accepted direction for this
component and mark the others superseded, so the next person who opens the
file knows which document is live.

**To verify:** cross-check against the current state of the Unifolio code repo
to establish which direction is actually in the product.

*Sources: `08-evidence/documents/specs/2026-08-18-auth-onboarding-import-review-visual-motion-redesign.md` §4.3, §5.5; `08-evidence/documents/specs/2026-08-19-auth-left-visual-redesign.md` §0; `08-evidence/documents/plans/2026-08-19-auth-left-panel-editorial-refinement.md`*

### R-034 — An illustration variant was built for the import flow and never wired in (Open, low)

`OnboardingIllustration`'s `"upload"` variant exists, was built for the CAS
import flow, and is not used anywhere. A second, smaller instance of the same
class of problem: `AddFamilyMembers.tsx` renders the `household` variant while
an unused `family` variant exists. Both are cheap to resolve and both represent
work already paid for and not collected.

**To verify:** cross-check against the current state of the Unifolio code repo.

*Sources: `08-evidence/documents/specs/2026-08-19-cas-import-illustration-redesign.md`; `08-evidence/documents/specs/2026-08-20-mobile-privacy-onboarding-fullscreen-plan.md`*

### R-036 — Two components render the same mobile fund detail (Open, medium)

`MobileFundDetailView` and `MobileFundDetailSheet` duplicate each other. The
2026-08-19 mobile system plan raised this deliberately as a product and
maintenance decision for a human rather than resolving it — a sheet and a full
view are not obviously the same product decision, and picking one changes
behaviour. It remains open.

**To verify:** cross-check against the current state of the Unifolio code repo.

*Source: `08-evidence/documents/specs/2026-08-19-mobile-uiux-system-plan.md` §4.5*

### R-037 — The desktop Main Dashboard is still a placeholder while the mobile one is mature (Open, high)

`DashboardPlaceholder.tsx` is a literal stub. `MobileDashboardView.tsx` is a
666-line mature implementation. The product's primary screen, on its primary
platform, does not exist.

This inverts the assumption in most of the design documentation, where mobile
adapts what desktop establishes. The mobile system plan's recommendation is
that when the desktop dashboard is built it should follow the product semantics
already settled on mobile, not the reverse — which is a genuine architectural
instruction, not a consolation.

**To verify:** cross-check against the current state of the Unifolio code repo.

*Source: `08-evidence/documents/specs/2026-08-19-mobile-uiux-system-plan.md` §0.3*

### R-038 — Empty, loading and error states are the one real cross-cutting gap on mobile (Open, medium)

The mobile system plan's survey found the design system otherwise complete —
no new tokens needed — with one systemic hole: empty, loading and error states
are not specified anywhere and are handled ad hoc per screen. A smaller related
gap: numeric inputs are missing `inputmode` attributes, so mobile keyboards
open in the wrong mode.

The 2026-08-27 analytics loading-state decision covers exactly one surface of
this. It is a precedent, not a solution.

**To verify:** cross-check against the current state of the Unifolio code repo.

*Source: `08-evidence/documents/specs/2026-08-19-mobile-uiux-system-plan.md` §3, §4.9*

### R-039 — The PDF export's capability-token store is in-process only (Open, medium)

ADR-013's export tokens live in an in-process dictionary. It does not survive a
restart and does not work across multiple workers — so the feature breaks the
first time the API runs with more than one worker, which is the normal
production configuration. The plan requires the limitation to be recorded
inline at the point of implementation, which is the right minimum; it is not a
fix.

Not urgent — the plan is unexecuted — and must be resolved before the feature
is deployed rather than after.

*Source: `08-evidence/documents/plans/2026-08-20-analytics-pdf-export.md`*

### R-040 — `compute_holdings` keeps a per-folio N+1, deliberately (Open, low)

The 2026-08-20 distributor-comparison design fixes its own query pattern and
explicitly declines to fix the pre-existing per-folio N+1 in `compute_holdings`,
on the grounds of not risking a regression in a working path for an unrelated
cleanup — that path had already taken four review rounds of performance work.
The design asks for it to be logged as a follow-up, which is what this entry
is.

The 2026-08-18 SIP plan fixes a different N+1 in its own path and adds a
query-count regression guard; the same guard technique would apply here.

**To verify:** cross-check against the current state of the Unifolio code repo.

*Source: `08-evidence/documents/specs/2026-08-20-distributor-comparison-portfolio-level-design.md`*

**Resolved, 2026-09-02 (per newly-ingested source material, recorded
2026-09-22).** `compute_holdings`'s per-folio `Transaction` N+1 query was
replaced with one batched query across all folios, grouped by folio in
application code to preserve the per-folio chronological order the FIFO
lot processor requires. 42 targeted tests plus the full backend suite pass
unchanged. See
[2026-09-02 — compliance audit Group 1](02-journey/2026-09-02-compliance-audit-group-1-and-non-pan-duplicate-detection.md).
Status changed to Resolved; entry left in place per this file's append-only
convention.

*Resolution source: `08-evidence/documents/engineering-loop/session.md`, "Still open" list item 6 / compliance audit F7*

### R-041 — Exact-string category matching may make legacy-header schemes invisible to comparison (Open, medium)

`get_category_universe` matches categories by exact string. A scheme filed
under a legacy AMFI header therefore does not appear in any peer universe — it
is not mis-categorised, it is absent, and nothing signals its absence.

Found as a side note during the index-fund investigation (INV-005) and not
measured. If real, it is a data-completeness defect in the analytics the
product's credibility rests on, and it is larger than the deferral it was
found underneath.

**To verify:** cross-check against the current state of the Unifolio code repo,
and count how many schemes fall under legacy headers.

*Source: `08-evidence/documents/specs/2026-08-20-index-fund-mega-category-split-deferred.md`*

### R-042 — A per-household analytics precompute is referenced but documented nowhere (Open, medium)

The 2026-08-27 loading-state decision's rationale states that on cold start, a
per-household precompute writes each analytics section's row as it finishes.
No document in this batch, and no record in this vault, describes that
mechanism being designed or built. The chosen cold-start treatment depends on
it — per-card progressive reveal is only meaningful if sections genuinely
complete independently and are persisted as they do.

Either the mechanism exists and is undocumented, or the loading-state decision
assumes infrastructure that does not exist. Both are worth knowing.

**To verify:** cross-check against the current state of the Unifolio code repo.

*Source: `08-evidence/documents/specs/2026-08-27-analytics-loading-state-mockups.html`*

**Update, 2026-09-02 — resolved.** The mechanism is now designed and, per
cross-document evidence in this batch, built: `analytics_sections` and
`analytics_recompute_status` tables, dispatched via ECS Fargate `RunTask`,
merged to `feat/enhanced-ui` (`f2daf84`, regression fix `8c2f0ef`, 628
passed/6 skipped). See [ADR-015](03-decisions/ADR-015-analytics-precompute-architecture.md)
and the [2026-09-02 journey entry](02-journey/2026-09-02-analytics-precompute-architecture.md).
*Source: `08-evidence/documents/specs/2026-09-02-analytics-precompute-architecture-design.md`;
`08-evidence/documents/plans/2026-09-02-analytics-precompute-architecture.md`;
`08-evidence/documents/plans/2026-09-10-analytics-frontend-precompute-migration.md`.*

### R-044 — Two Phase 2 data-format assumptions are unverified (Open, medium)

First: the NSE bhavcopy URL and its column naming (ISIN and closing-price
columns) have not been checked against a real file, and the equity price
history depends on them. The backend plan flags this as an assumption.

Second: no real depository Statement of Transactions sample has been obtained.
The research describes it as reading like a custody-movement ledger rather than
a priced trade blotter, and states plainly that a real sample should be
obtained before committing engineering time to it. That precondition is unmet.

Both are cheap to close and both sit underneath committed plans.

*Sources: `08-evidence/documents/plans/2026-08-26-phase-2-stocks-demat-import-backend.md`; `08-evidence/documents/specs/2026-08-25-phase-2-stocks-demat-research.md`*

### R-045 — Phase 2's first cut has four stated scope gaps (Open, low)

Each is deliberate and each is a hole a user can see: there is no aggregate
(household-level) equity-holdings endpoint, so equities are member-view only;
mobile is out of scope entirely for demat import, in a product where mobile is
currently the more complete platform (R-037); bond and demat-held mutual-fund
holdings are stored by migration `0010` but not surfaced anywhere; and pension
holdings present in the parsed statement are explicitly out of scope, flagged
rather than dropped.

*Sources: `08-evidence/documents/plans/2026-08-26-phase-2-stocks-demat-import-backend.md`; `08-evidence/documents/plans/2026-08-26-phase-2-stocks-demat-import-frontend.md`*

### R-048 — A second external agent widens the gap R-029 already describes (Open, medium)

R-029 records that ADR-011's orchestration workflow covers Claude Code, Codex
and Claude subagents, and says nothing about an agent outside the team's own
tooling — at the time, Google Antigravity. This batch adds five more Antigravity
handoffs (2026-08-18, three on 2026-08-19, 2026-08-20, 2026-08-25) and a second
vendor: **Manus**, which builds *and hosts* the marketing website, in a
repository the team does not control, on a public-facing surface.

The compensating practice has held up well — the design specs end with
ready-to-paste agent prompts that require the agent to name itself in
`session.md` and `CLAUDE.md`, preserving provenance. That is still good practice
invented per occasion. Hosting by a third party is a materially different
exposure from implementation by one, and nothing in the vault covers it.

**Recommended resolution (not applied):** extend R-029's recommendation — an
external-agent worker category appended to ADR-011 — to distinguish an external
*implementer* from an external *builder-and-host*, and state what is required
of each.

*Sources: `08-evidence/documents/specs/2026-08-31-marketing-website-design.md`; the 2026-08-18 to 2026-08-25 design specs*

### R-049 — Four small UI decisions were left open and will be defaulted if nobody chooses (Open, low)

Each was raised deliberately rather than guessed at, and each has a stated
default that will take effect by inaction: privacy point two has no dedicated
illustration (default: reuse the existing inline icon at illustration scale);
the dark-mode treatment of the mobile hero band is undecided; `AddFamilyMembers`
uses the `household` illustration variant while an unused `family` variant
exists (R-034); and the 543KB hero SVG's paint cost on low-end devices has not
been measured, a smaller concern now that the blur treatment was rejected.

*Sources: `08-evidence/documents/specs/2026-08-20-mobile-privacy-onboarding-fullscreen-plan.md` §6; `08-evidence/documents/specs/2026-08-19-mobile-auth-onboarding-review-plan.md`*

### R-050 — Migration 0009 is unaccounted for in the vault's evidence (Open, low)

The vault records migration `0002` (transaction dedupe, INV-003), `0004`/`0005`
(named as the point the schema document went stale), `0006` (this batch,
email-and-password auth), `0007`–`0008` (password storage removed) and `0011`
(the point the schema document was reconciled to). This batch adds `0010`
(demat accounts and equity holdings). **Nothing in the vault says what `0009`
did.**

Not a defect, a traceability hole: the migration chain is the vault's most
reliable record of what the schema actually is, and it has a gap in it.

**To verify:** cross-check against the current state of the Unifolio code repo's
migration folder.

*Sources: this batch's plans; `decisions-log.md` 2026-08-17 and 2026-09-02*

**Update — 2026-09-23 (Resolved):** Migration `0009` is accounted for.
Later-ingested material (dated 2026-08-21) shows it is
`0004_scheme_ter_nullable_value.py`, renumbered to `0009` during a fix for
a branch-merge migration-head collision — not a missing or undocumented
migration, a renumbered one. See the
[2026-08-21 journey entry](../02-journey/2026-08-21-post-merge-migration-head-collision-and-windows-playwright-crash.md).
Separately, this batch's material also confirms the real migration `0010`
is an enum-widening change (`importstatus`/`transactiontype`, dated
2026-09-02) — distinct from this entry's own earlier reference to "this
batch adds `0010` (demat accounts and equity holdings)," which was only
ever a number named in an unexecuted design plan (R-051), never a real,
merged migration. No two real migrations share the `0010` number; the
apparent collision was between one real migration and one never-executed
plan's naming choice.
Evidence: `08-evidence/documents/orchestration/post-merge-environment-and-migration-fixes.md`,
`08-evidence/documents/orchestration/enum-drift-migration-handoff.md`

### R-051 — Six of the eight implementation plans in this batch were not fully executed (Open, high)

Of the plans covering 2026-08-17 to 2026-08-31: two are fully ticked (the
email-and-password backend and frontend, both subsequently reversed); one is
partially ticked (the auth panel editorial refinement, with its verification
task outstanding); and five are entirely unticked — the SIP cadence redesign,
the analytics PDF export, the portfolio-level distributor comparison, and both
Phase 2 demat plans. Four of the design specs carry no execution record at all.

The design output of this fortnight substantially exceeds its build output.
That is not automatically wrong — research and design ahead of build is the
point of both — but it means almost everything described in this batch is
**intent, not shipped behaviour**, and every downstream record in this vault
has been written to say so. The 2026-08-25 mobile plan reaches the same
conclusion independently, telling the implementing agent not to assume the
preceding week's work is in place and to check current state first.

**To verify:** cross-check against the current state of the Unifolio code repo.
This is the single highest-value verification pass available to this vault.

*Source: execution status of all eight files in `08-evidence/documents/plans/` for this batch*

**Update, 2026-09-19 (live conversation).** The vault owner states
that all six not-fully-executed plans above (SIP cadence redesign,
analytics PDF export, portfolio-level distributor comparison, auth
left panel verification task, both Phase 2 demat plans) have since
been completed in later work. Recorded as a forward pointer, not
verified fact. Source: vault owner, live conversation, 2026-09-19 —
not yet corroborated by source material. Corroborate against
subsequent batches as they are ingested, and ultimately against the
current state of the Unifolio code repo.

**Update, 2026-09-22 (batch 3, root engineering-loop source material).**
Three of the six now have direct, dated, evidence-backed corroboration —
not just the vault owner's word:

- **SIP cadence redesign** — built 2026-08-19, 3 review rounds, 218/218
  frontend tests passing. See the addendum on
  [ADR-012](03-decisions/ADR-012-active-sip-cadence-projection.md).
- **Analytics PDF export** — built 2026-08-20/21, merged `ed149bf`, both
  full suites passing. See the addendum on
  [ADR-013](03-decisions/ADR-013-analytics-pdf-export-architecture.md).
- **Portfolio-level distributor comparison** — built 2026-08-21, 10 tasks
  through the mandatory review gate. See the addendum appended to
  [2026-08-20 — Analytics deepening](02-journey/2026-08-20-analytics-deepening-and-a-deferred-split.md).

The remaining three (the auth left-panel verification task, both Phase 2
demat plans) still have **no** corroborating evidence in this batch's
source material — the 2026-09-19 forward pointer for those three remains
unverified. This risk is left Open; three of its six original items are
now resolved, three are not.

*Corroboration source: `08-evidence/documents/engineering-loop/session.md`*

### R-052 — Terraform state can silently drift ahead of `session.md`'s documented status (Open, medium)

Preparing the 2026-09-11 staging runbook, the draft stated Phase 4
(S3+CloudFront), Phase 5 (ACM/DNS/ALB HTTPS) and the analytics-recompute
dispatcher's ECS task definition were "authored, reviewed, not applied." A
`terraform plan` run during actual execution showed all of it already present
in Terraform state — refreshed, not created — traced to a stray
`tfplan-step7` file dated earlier the same day, predating the session that
produced the runbook. Caught and reconciled before anything was duplicated;
only 2 EventBridge jobs and one IAM policy change were genuinely outstanding.

Infrastructure state moved faster than the notes describing it, once,
undetected until a plan diff was actually run. Nothing in the vault's process
currently forces a `terraform plan` check before trusting a status note. A
related, smaller recurring issue from the same session: Docker builds on WSL
intermittently fail with a `.pytest_tmp` xattr/permission error (a known
WSL/drvfs BuildKit issue); `pytest.ini`'s `--basetemp` was moved outside the
repo to stop it recurring, not confirmed as a permanent fix.

**To verify:** cross-check against the current state of the Unifolio code
repo's Terraform state and CI configuration.

*Source: `08-evidence/documents/plans/2026-09-11-aws-staging-prerequisites.md`*

**Update — 2026-09-23 (narrowed, still Open):** Later-ingested material
pins a concrete date for when Phases 4-5 were already applied and live: a
scheduler-Terraform dispatch dated 2026-09-10 — the day before the runbook
session — states as a precondition that "Phases 1-5 [are] all applied and
live (confirmed)," with `staging.unifolio.in` /`staging-api.unifolio.in`
both already resolving over HTTPS. This is strong corroboration that the
apply happened by 2026-09-10, not that the runbook session's own actions
on 2026-09-11 caused unexpected drift — the underlying risk (a status note
going stale faster than infrastructure reality, with no automated check
catching it) is not resolved by this finding and stays Open; only the
"what actually happened, and by when" question for this specific instance
is narrowed. No document in either batch states the exact `terraform
apply` command or session that performed the Phase 4/5 apply.
Evidence: `08-evidence/documents/orchestration/adr006-scheduler-terraform-handoff.md`,
`adr006-scheduler-terraform-implementation-prompt.md`

### R-053 — Fund Score card redesign is approved and fully planned, but has no execution evidence in this batch (Open, low)

A plain-English verdict card and a display-only tier-badge fix were designed
and given a 9-task implementation plan on 2026-09-11. Unlike the 2026-09-02
analytics precompute work, no later document in this batch references it as
built — no commit hash, no test-run count, no `session.md` note.

Low severity: this is a UI readability fix with an explicit backend/schema
non-goal (the persisted `risk_adjusted_tier` column is deliberately left
untouched), not a blocker for anything else in the vault.

**To verify:** cross-check against the current state of the Unifolio code
repo, or against a later batch's source material.

**Resolved, 2026-09-12 (per newly-ingested source material, recorded
2026-09-22).** All 9 implementation tasks executed, both full suites
passing, mandatory whole-branch review closed with no unresolved findings.
See the addendum on
[ADR-017](03-decisions/ADR-017-fund-score-card-redesign.md). The
precompute-cache backfill for already-cached rows remains unconfirmed —
not itself a reason to leave this entry open, since it was already an
explicitly deferred, separate step in the original plan.

*Resolution source: `08-evidence/documents/engineering-loop/session.md`, 2026-09-12 section*

*Sources: `08-evidence/documents/specs/2026-09-11-fund-score-card-redesign-design.md`;
`08-evidence/documents/plans/2026-09-11-fund-score-card-redesign.md`*

### R-054 — A "7 in-process caches" hardening item is sourced from a document this vault has not yet ingested (Open, low — flagged, not verified)

The 2026-09-11 AWS staging runbook references an external readiness report
(`AWS Readiness/aws-golive-readiness-report.md`, its own §22 "Phase 7")
naming "in-process caches off single-task-only state" as its highest-priority
hardening item ahead of a public launch. That report itself has not been
ingested into this vault as of this batch — its contents, and even its exact
claim, are known only second-hand, through one reference inside the runbook.

Recorded as a hypothesis pointer, not a verified vault fact, per the vault's
rule against treating unverified conversation/document claims as settled.

**To verify:** ingest `AWS Readiness/aws-golive-readiness-report.md` itself in
a future batch (per the vault's roadmap) and confirm or correct this claim
against its actual text.

*Source: `08-evidence/documents/plans/2026-09-11-aws-staging-prerequisites.md`
(second-hand reference only — source document itself not yet in the vault)*

**Update — 2026-09-23 (corroborated, still Open):** A 2026-09-10
production-hardening plan, itself derived from the same readiness report's
§22 Phase 7 section, confirms the in-process-cache/single-task-only
constraint as a real, named item and re-examines it against a small beta
cohort (deferred until a concrete need for a second task arises — see the
update on [R-058](#r-058)). This corroborates the claim this risk flagged
as second-hand, but the readiness report document itself is still not
directly in this vault — only derivative handoff/prompt/plan documents
that reference it. Stays Open until the source report itself is ingested.
Evidence: `08-evidence/documents/orchestration/phase7-production-hardening-plan.md`

**Update — 2026-09-24 (source report itself now ingested — confirmed, title no
longer accurate):** `aws-golive-readiness-report.md` (batch 5) has been read
directly. The claim is **confirmed accurate**, not a misattribution — with one
correction to this entry's own title: the item is not confined to a single
§22 "Phase 7" mention, it recurs throughout the report as a named, load-bearing
constraint. §1a states the finding plainly: "a hard architectural ceiling of
exactly one running backend instance until seven in-process caches are fixed."
§7 names the fix directly: "Move the seven in-process caches to a shared store
(Redis, or DB-backed)." §22 Phase 7 (the section this entry originally named)
restates it as a sequencing instruction: "Prioritize moving the seven
in-process caches to a shared store to remove the single-ECS-task constraint
(§7) — do this before staging is trusted as the ongoing home for ~1,000 real
users; ... treat it as the first item in this phase, not the last." §8 adds a
capacity-driven reprioritization not previously known to this vault: given a
~1,000 MAU target, the report moves this cache rewrite earlier in the overall
sequence than a first read of the Phase 7 label alone would suggest.

The exact seven caches, per `aws-golive-launch-blockers.md` (same batch): the
CAS-import password-retry PDF buffer, import-preview sessions, the analytics
PDF-export payload handoff, the dashboard holdings cache, the
distributor-comparison cache, and the NAV-warming/TER-backoff/category-ranking
caches. This list matches, rather than contradicts, what R-058's 2026-09-23
update already described as the reason the single-ECS-task constraint is
being deliberately held rather than relaxed.

Status stays **Open** — the caches have not been moved to a shared store, only
the claim about their existence and priority is now verified against primary
source rather than second-hand. No longer "flagged, not verified"; retitling
the entry itself is not done here per the vault's append-only rule for
already-committed content — this update supersedes that framing in substance.

Evidence: `08-evidence/documents/aws-golive-readiness-report.md` (§1a, §7, §8,
§22 Phase 7), `08-evidence/documents/aws-golive-launch-blockers.md`.

### R-055 — SIP tab switcher: an inactive tab's `aria-controls` points at an unmounted panel id (Open, low — accepted documented limitation)

Found during the active-SIP cadence redesign's mandatory adversarial-review
gate (round 2 of 3, 2026-08-19). The inactive tab's `aria-controls`
attribute references a `tabpanel` id that is not currently mounted in the
DOM — a real ARIA IDREF gap. It was explicitly accepted rather than fixed
in a third review round, on the reasoning that screen readers still get
the correct tab/panel pairing via `aria-selected`/`aria-labelledby`, so the
practical accessibility impact is judged low. Recorded here, per this
batch's own text, so the accepted gap "is tracked as its own low-severity
item, not silently dropped."

**To verify:** confirm against the current frontend code whether the two
tabpanel ids are ever reconciled (e.g. if the SIP tab switcher is later
generalized to a shared tab component).

*Source: `08-evidence/documents/engineering-loop/session.md`, "'This
Month' SIP tab feature, Tasks 6-8 review gate closed (2026-08-19)"
section. See also the addendum on
[ADR-012](03-decisions/ADR-012-active-sip-cadence-projection.md) and the
addendum on
[2026-08-18's journey entry](02-journey/2026-08-18-active-sip-cadence-redesign.md).*

### R-056 — Phone-OTP login silently creates a new account for an unrecognized phone number, instead of erroring like email does (Open, medium — explicitly deferred by product-owner decision)

Found by the user 2026-09-11 manually smoke-testing staging: logging in
with a phone number that has no matching account still completes the
OTP-send/verify flow and creates a brand-new account, rather than telling
the user no account exists and directing them to sign up. Root-caused
against the code: `backend/app/api/auth.py`'s `verify_otp_route`
(phone-OTP channel), in the branch handling a verify call with no
`pending_token` — `find_or_backfill_phone_identity` returning `None` falls
straight through to an unconditional new-`User` INSERT. The equivalent
email-OTP branch already does the right thing, raising a 401 ("No account
found for that email — sign up instead.") instead of creating an account;
the two channels' identical-shaped branches have simply diverged.
Confirmed as a clean single-sided gap: the frontend only ever renders
"Continue with Phone" in login mode, so the unfixed branch cannot be
reached from a genuine phone-signup flow, because that flow does not
exist.

**Explicitly deferred, not fixed, by product-owner decision, 2026-09-11** —
recorded here rather than as a bug awaiting a fix, per the vault's
convention for decisions with reasons. A related, not-yet-designed
refinement is also on record: even the email channel's equivalent check
happens at OTP-verify time, not request time, which does not fully match
the user's stated ideal UX; moving it to request time was identified as
carrying a mild account-enumeration tradeoff (an unauthenticated
"does this identifier have an account" probe), and is explicitly not
scoped into this fix.

**To verify:** cross-check against the current state of the Unifolio code
repo, or against a later batch's source material, for whether this has
since been fixed.

*Source: `08-evidence/documents/engineering-loop/session.md`, "Still open"
list item 9; corroborated by the evidence-copy
`08-evidence/documents/engineering-loop/CLAUDE.md`'s "Still open" summary.*

### R-057 — Two real staging credentials (an RDS database password and an AWS IAM access key) are confirmed live and have not been rotated (Open, high — must be rotated before production)

Batch 3's raw source material contains two real, plaintext credential
values: an RDS Postgres master password (encountered while debugging a
shell-quoting bug during a `psql`-tunnel migration run — see
[INV-009](04-investigations/INV-009-amfi-ter-readtimeout-event-loop-starvation.md)'s
sibling material and the redacted raw-evidence copy), and an AWS IAM
access key pasted into a chat session during Terraform staging work (see
[INV-010](04-investigations/INV-010-aws-iam-key-pasted-in-chat-and-rotated.md)).
INV-010's own source material described the IAM key as already rotated;
**the vault owner has since confirmed, live, on 2026-09-23, that this is
incorrect — neither credential has actually been rotated.** Both are
real, currently-live staging-environment credentials, deliberately left
unrotated until the project moves from staging to production.

Neither literal credential value is reproduced anywhere in this vault.
The raw inbox evidence copy containing the RDS password
(`00-inbox/raw/processed/2026-09-22-batch3-engineering-loop/session.md`)
was redacted in place before this batch was committed, specifically so
that the literal value never enters this repository's git history. The
AWS IAM key's literal value is also known to exist in plaintext in a
not-yet-ingested file (`Notes for Unifolio/Move to Cloud.md`, future
batch material) — that file must receive the same redaction treatment
before it is ever committed to this vault.

**Must fix before production:** both the RDS master password and the AWS
IAM access key must be rotated when the project moves from staging to
production. Recorded here as a high-severity, explicit pre-production
gate, not an ordinary backlog item, precisely because it is a live,
unrotated credential rather than a historical incident.

**To verify:** confirm both credentials have been rotated at the point
production go-live is planned; do not treat this as resolved until that
rotation is independently confirmed.

*Source: vault owner, live conversation, 2026-09-23; raw evidence
`00-inbox/raw/processed/2026-09-22-batch3-engineering-loop/session.md`
(redacted before commit).*

### R-058 — Blocking synchronous database calls inside async request handlers can still freeze every concurrent user in production, not just the slow request (Open, medium — architectural, deliberately deferred)

INV-009 root-caused a real production symptom (AMFI TER `ReadTimeout`s) to
a blocking `db.commit()` inside an async handler stalling the single
worker's entire event loop for 60-120 seconds at a time, freezing
unrelated concurrent requests along with the slow one. A targeted fix
(`commit_off_loop`, commit `bb5225f`, 2026-08-27) routes the specific
commits that were observed to be slow through a background thread, and a
stopgap timeout increase was also applied.

**Why this is not closed:** the *trigger* observed (60-120 second SQLite
commits on a WSL filesystem mount) is specific to the current development
environment and is expected to mostly disappear once the app runs on
Postgres. The underlying *vulnerability* is architectural and will still
exist in production: any blocking synchronous database call inside an
async handler stalls every concurrent user sharing that event loop, not
just the request that triggered it. A lock wait, a large batch commit,
connection-pool exhaustion, or a large CAS re-import under real
concurrent production traffic could all still freeze every logged-in
user's request simultaneously — the fix so far only covers the specific
commits that were already known to be slow.

**What needs to be fixed (three options identified, deliberately not yet
chosen, to avoid bundling a large cross-cutting database-layer refactor
into unrelated debugging work):**
1. Wrap only the other known heavy batch commits in a background thread
   (targeted, incremental, but leaves any future blocking call unguarded).
2. Wrap every synchronous database call inside an async handler (blanket
   coverage, but needs auditing for cross-thread session-object use).
3. Migrate to SQLAlchemy's native async engine (the correct long-term
   fix; a dedicated project of its own, not a quick patch).

Revisit deliberately, ideally paired with the Postgres migration, rather
than patching reactively the next time a different blocking call causes
the same symptom.

*Source: `04-investigations/INV-009-amfi-ter-readtimeout-event-loop-starvation.md`,
"Residual risk — explicitly not closed" section; `08-evidence/documents/engineering-loop/session.md`.*

**Update — 2026-09-23:** The single-task constraint this risk lives
alongside is now enforced structurally, not just by convention: the
staging ECS Terraform (authored 2026-09-08) sets
`deployment_maximum_percent = 100`, `deployment_minimum_healthy_percent = 0`
(a deliberate stop-then-start deploy, never two tasks briefly concurrent)
and deliberately contains no `aws_appautoscaling_target`/`policy`
resource at all. A 2026-09-10 beta-hardening plan explicitly re-examined
and re-deferred this constraint for a small (5→30-user) first beta, named
"a concrete need for a second task" as the revisit trigger — not a fixed
date. This does not change R-058's underlying architectural risk; it
confirms the risk is currently being managed by staying single-task
rather than by fixing the blocking-call vulnerability itself.
Evidence: `08-evidence/documents/orchestration/aws-phase3-backend-deployment-handoff.md`,
`08-evidence/documents/orchestration/phase7-production-hardening-plan.md`

### R-059 — Two parallel CAS-import backend code paths independently drifted to need the identical duplicate-detection fix wired in twice (Open, medium — architectural, surfaced not fixed)

While wiring the 2026-09-02/03 non-PAN duplicate-person-detection design
into production, the same confirmation-gate logic had to be added at all
three backend commit sites across what turned out to be two separate,
parallel import-backend code paths — the two paths had already drifted
apart enough that a single shared fix could not be applied once and
inherited by both. This was surfaced as a standalone architectural
finding during that work and deliberately **not** fixed as part of that
pass, to avoid scope creep into an unrelated feature change.

**Why this matters:** having two parallel backends for the same import
functionality means every future fix, validation rule, or behavioural
change to CAS import has to be identified and re-applied in two places
by hand, as this duplicate-detection gate already was — a structural
source of the exact kind of silent drift (one path fixed, the other
forgotten) that this finding itself is an instance of.

**What needs to be fixed:** the two import backends need to be
reconciled — either consolidated into a single shared code path, or
given an explicit, enforced mechanism (a shared helper, a lint rule, or
a test that fails if the two diverge) that stops future fixes from
needing to be applied twice by hand. Not scoped or designed here;
recorded so it is not lost.

**To verify:** identify the two concrete backend code paths against the
current state of the Unifolio code repo, and confirm whether they have
since been consolidated or whether the dual-maintenance burden is still
live.

*Source: `02-journey/2026-09-02-compliance-audit-group-1-and-non-pan-duplicate-detection.md`,
"What actually happened" (non-PAN duplicate-person detection) and
"Result" sections.*

**Update, 2026-09-23 (per newly-ingested source material, recorded
2026-09-23) — partially resolved, architectural risk still open.**
`two-parallel-import-backends-architectural-gap.md` and
`f8-nav-unavailable-degraded-row-handoff.md` supply the concrete git
archaeology this entry's own "To verify" note asked for. The specific
duplicate-detection confirmation-gate gap named in this entry's title
**was closed 2026-09-03**: a shared `enforce_attribution_confirmation()`
helper was added and wired into all 3 backend commit sites across both
`service.py`/`/imports/*` (the live production path) and
`lifecycle_service.py`/`/cas-imports/*`, reviewed and independently
re-verified (614 backend tests/1 skipped, 397 frontend/75 files, matching
the implementer's self-report). The underlying architectural risk named
in this entry's "What needs to be fixed" section — the two import
backends remain two separate code paths, not consolidated — is confirmed
**still open**: `/imports/*` (added `5c81231`/`1e823d1`, 2026-08-04,
wired to the live frontend `ImportFlow.tsx` at `038342a`, 2026-08-05) and
`/cas-imports/*` (added `4d60c8e`, 2026-08-10, with its own frontend
`ImportLifecycleView.tsx` at `e7db4c1`, same day, never mounted into any
route) drifted apart undetected for ~3.5 weeks before this finding
surfaced them. No consolidation work has been done; the fix-once
mechanism (shared helper) now exists for this *one* invariant only, not
as a general safeguard against the next such drift. Full detail:
[2026-09-02 journey entry addendum](../02-journey/2026-09-02-compliance-audit-group-1-and-non-pan-duplicate-detection.md).

*Resolution source: `08-evidence/documents/orchestration/two-parallel-import-backends-architectural-gap.md`,
`08-evidence/documents/orchestration/non-pan-duplicate-person-detection-handoff.md`*

### R-060 — No per-key single-flight coordination on cache-miss recompute (Open, low — accepted limitation)

During the 2026-08-13→18 dashboard NAV/holdings cache-hardening rounds, a
gap was found and deliberately left unfixed: when two requests for the
same uncached key arrive close together, both can miss the cache and both
trigger the same expensive recompute, rather than the second waiting on
the first's in-flight result. The product owner reviewed this in round 4
and explicitly decided not to dispatch a fix — accepted as a documented
limitation, not scoped for machinery like a single-flight lock or request
coalescing at this time.

**Why this matters:** under real concurrent load (e.g. two open tabs, a
page reload racing a background poll), the same expensive computation can
run twice for no benefit. Currently accepted because the underlying
computations are bounded and the duplication is wasted work, not incorrect
output — distinguishing it from the three races that *were* fixed in the
same stage, which risked wrong or stale published values.

**What would need to change to revisit:** a demonstrated load or cost
problem from duplicate recomputes, not a schedule.

*Source: `08-evidence/documents/orchestration/dashboard-nav-perf-handoff.md`
(round 4); `02-journey/2026-08-13-dashboard-nav-and-holdings-cache-race-hardening.md`.*

### R-061 — Test fixtures create schema directly (`Base.metadata.create_all()`), so migration/model drift can pass a green test suite (Open, medium — testing-process gap)

`tests/conftest.py:24-26` builds the test database schema straight from the
current SQLAlchemy models, bypassing the Alembic migration chain entirely.
A migration that is missing, wrong, or silently out of sync with the models
(exactly the kind of drift already found and fixed once — see migration
`0010`'s enum-widening fix, recorded in the 2026-09-02 journey entry's
2026-09-23 addendum, and R-050's migration-numbering finding) will not be
caught by the test suite, because the tests never actually run the
migrations that a real deploy applies to RDS. The suite can stay green while
the migration chain that would run against staging/production Postgres is
broken or incomplete.

**Why this matters:** this is a root-cause finding, not a restatement of the
already-fixed enum-widening incident — it explains *why* that kind of drift
was able to go undetected until an unrelated audit found it by hand, and why
the same class of gap can recur silently. A schema/migration mismatch would
currently surface only in a real deploy (or a manual audit like this one),
not in CI.

**To verify / what would fix it:** add a test-suite path (even a single
smoke test) that builds the schema by running the actual Alembic migration
chain against a throwaway Postgres database, rather than `create_all()`,
and fails if the two diverge. Not scoped or designed here — recorded so the
gap is not lost, consistent with this vault's audit having independently
reconfirmed F1-F3/F5-F10 already-resolved elsewhere and found this as the
one genuinely new item.

*Source: `08-evidence/documents/sqlite-postgres-migration-compliance-audit.md`,
Section 6 (root-cause discussion of `tests/conftest.py:24-26`).*

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
- **SMS and email delivery providers** — both auth channels ship with stubs.
  Tracked as R-024 and R-025 rather than here, because "deferred" understates
  it: the product cannot log a real user in until both are done.
- **Client-side persistence of in-flight flow state** — `sessionStorage` for
  the import flow and IndexedDB for the family upload queue were both
  considered and rejected as premature (2026-08-05, 2026-08-06). A reload
  restarts the flow. See R-027.
- **A router in the frontend** — considered and rejected at least three
  times (2026-08-05, 2026-08-06, 2026-08-14), each time with a local
  navigation mechanism chosen instead. The decision is load-bearing: it is
  one of the reasons the Google OAuth redirect flow was rejected in ADR-008.
  See [frontend composition](06-architecture/frontend-composition.md).
- **`GET /auth/me`** — obviously useful, deliberately not added on
  2026-08-05 because it was not in the approved design. Recorded because the
  restraint is the point.
- **Scheduled NAV refresh** — NAV is fetched on demand and cached rather than
  refreshed by a scheduled job. Scheduling is deployment-phase infrastructure
  and was out of scope for Phase 3 (2026-08-06); ADR-006 covers the intended
  mechanism.
- **Persisting the FR-7 score breakdown** — recomputed on read instead, so
  the `fund_scores` table's columns stay as the schema document fixes them.
- **Splitting AMFI's index-fund mega-category** — 1,150 schemes in one peer
  universe. Two splits were costed and both rejected: a name-pattern split
  works but invents every boundary, and AMFI's own parallel headers cover
  largely different feed rows. Revisit only if load time for index-fund holders
  becomes a demonstrated user-facing problem (2026-08-20). See INV-005.
- **A missed-SIP / `is_actual` flag and step-up detection** — considered
  alongside ADR-012 and rejected as speculative. Unifolio shows what is due and
  deliberately does not editorialise about what did not arrive, which removes
  the flag's only plausible consumer (2026-08-18).
- **Broker APIs, aggregator gateways and the Account Aggregator framework for
  equities** — ruled out for Phase 2 on cost, coverage and calendar, not on
  merit. The Account Aggregator route remains the strategically correct
  destination and ADR-014 is deliberately built so as not to foreclose it
  (2026-08-25).
- **`gsap`** — installed and unused. The 2026-08-25 mobile landing plan
  considered it for the convergence animation and explicitly declined, keeping
  the motion on the already-used animation library. A dependency that has now
  been considered and passed over twice is a candidate for removal, not use.
- **Mobile demat import** — out of scope for Phase 2's first cut by decision,
  on the platform that is currently the more complete one (2026-08-26). See
  R-045.
- **Full TRI (Total Return Index) benchmark sourcing** — the Analytics
  correction plan's P0.3 item shipped a labeling-only fix (a
  " (Price Return)" suffix on the benchmark label) instead of sourcing true
  TRI data, with a written 5-step future-implementation guide and explicit
  revisit triggers rather than an open-ended TODO (2026-08-19). See
  [02-journey/2026-08-19-analytics-correction-plan-status-and-tri-benchmark-disposition.md](../02-journey/2026-08-19-analytics-correction-plan-status-and-tri-benchmark-disposition.md).
