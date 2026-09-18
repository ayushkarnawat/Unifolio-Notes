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
