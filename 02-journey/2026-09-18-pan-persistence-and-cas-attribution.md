# ADR-004 is formally reopened: PAN is now stored, encrypted, and CAS statements are matched by it

## For stakeholders

Since launch, Unifolio had a strict, tested rule: never store a user's PAN
(India's tax ID) or the uploaded statement PDF — parse it, keep the
structured numbers, throw the rest away (ADR-004). That rule had a real
cost: without a stable identifier, the app could only guess which family
member a statement belonged to by matching the name printed on it, and
names are unreliable — nicknames, spelling differences, two relatives with
similar names. On 2026-09-18 that rule was formally reopened. The PAN is
now stored per family member, encrypted so it can never be read directly
from the database, and it — not the typed name — is what decides who a
statement belongs to: a second statement for the same person auto-attaches
even if a different nickname is typed; a PAN already claimed by someone
else's Unifolio account is refused outright, with no override, as a
fraud/duplicate-account guard. The original PDF is now kept for 30 days
(for re-checking or disputes), then deleted. Six days later, a real gap in
the first version was found and fixed: a brand-new account's very first
upload had no PAN on file yet to check, so it could never benefit from the
new matching — every first-time import failed with a false "we can't match
this statement" error. That's fixed by claiming the PAN as soon as the
file is uploaded, not only after the user confirms.

## Technical detail

### Intended outcome

Resolve three related requests together: store the parsed PAN instead of
discarding it, retain the uploaded CAS file for a bounded window instead
of deleting it immediately, and use PAN as the primary signal for matching
a statement to a household member instead of fragile name-matching.

### What actually happened

**2026-09-18 — discussion, decision, and same-day build.** Current-state
verification (reading the code, not assuming) confirmed the PAN was
already parsed and immediately masked/discarded
(`backend/app/services/import_/parser.py`), no table had a PAN column, and
a CI guard test (`tests/models/test_no_pan_field.py`) actively failed the
build if one was ever added — this was ADR-004's premise, correctly
implemented. Attribution precedence at the time was folio+AMC match, then
fuzzy name match, then a self-only email fallback.

Scope decided in discussion, before any code was written:

| Question | Decision |
|---|---|
| Recoverable PAN, or one-way hash only? | **Real PAN, encrypted, recoverable** |
| How long is the raw CAS file kept? | **30 days**, then auto-deleted — for re-parsing/dispute purposes, not a user-facing download feature |
| Same household, PAN already matches a member | **Auto-attribute, with a disclaimer shown** — reuses the existing "attach to member" behavior, not a new merge feature |
| PAN matches a member on a **different** account | **Block the import entirely, no override** — contact support. No in-app account-merge (identified as a much larger, separate subsystem, explicitly out of scope) |
| How is the PAN matched — decrypt-and-compare, or hash lookup? | **Hash lookup** (HMAC-SHA256, deterministic). Chosen because the cross-account block has to search every household member *system-wide* — decrypting every row just to compare would mean handling other users' raw PANs in memory during that scan |
| Where does the file live? | **Private S3 + native Lifecycle rule** for the 30-day expiry, recommended over a DB blob + a cron sweep job (rejected: bloats backups, pulls forward an entire scheduling subsystem this repo had explicitly deferred) |
| Which key protects the PAN encryption — a customer-managed KMS key (CMK, ~$1/mo, self-controlled key policy and audit trail) or the free AWS-managed SSM key? | **Left open** at the time of this discussion — see Resolution below |

Built the same day: migration `0015` added `pan_encrypted` (AES-256-GCM)
and `pan_lookup_hash` (HMAC-SHA256, `UNIQUE`) to `household_members`, and
`file_reference`/`file_expires_at` to `imports`. `attribution.py` was
rewritten to check PAN first (household match → auto-attach;
cross-account match → `CrossAccountPanBlockedError`, no override; no PAN
readable → falls back to the pre-existing folio+AMC match). Two separate
secrets protect two separate jobs — one encrypts the PAN (reversible), a
different one peppers the lookup hash (never reversible) — deliberately
not the same secret. Encryption is authenticated: a tampered value or
wrong key throws a clear error rather than silently producing plausible
garbage. `test_no_pan_field.py` was broadened, not deleted, to assert PAN
only ever exists in these two named encrypted/hashed columns, checked
against every mapped table — enforcing "no *unencrypted* PAN" in place of
the old "no PAN at all" invariant. A missing-secret-key misconfiguration
was changed, during review, from failing silently on the first PAN-bearing
import to refusing to boot at all outside dev — caught immediately instead
of partially, confusingly breaking imports later. 150+ new/changed tests;
full suites (672 backend / 435 frontend at the time) passed.

**Deliberately not built in this pass**, recorded rather than treated as
an oversight: no real cloud file storage yet — the 30-day retention wrote
to local disk (`backend/var/cas_files/`) behind a swappable storage
interface designed for an S3 swap later, not yet built; no automatic
scheduled cleanup — a CLI tool (`expire_cas_files.py`) exists and is
tested, but nothing runs it on a schedule; no account-merge path, as
scoped above. Two narrow, named edge cases were flagged rather than fixed:
a specific override-plus-existing-PAN-match combination could raise a raw
database error instead of a clean message; a small file-path test helper
is duplicated across four test files instead of shared.

**2026-09-24 — the first-upload gap found and fixed (migration `0016`).**
A member's PAN was only ever written *after* Confirm Import, so a brand
new account's very first upload had nothing to check the new PAN against
— every first-time import produced a false "couldn't match this
statement" error. Amends, does not reverse, the 09-18 design — same
storage, same matching rules, different point in the flow where the
check/claim happens. `household_members` gained `pan_pending_until`;
`/imports/parse` now writes `pan_encrypted`/`pan_lookup_hash` and sets
`pan_pending_until` to upload-time + 65 minutes, in the same database
write, the moment the file is parsed and no conflict is found — before
the user has even seen the Review screen. `/imports/confirm` no longer
touches the PAN columns at all; it only clears `pan_pending_until` to
`NULL`, converting a pending claim into a permanent one. Abandoning the
upload (Try again, Cancel, or 65 minutes passing with no Confirm) wipes
all three PAN columns back to empty. The unique index on
`pan_lookup_hash` covers a *pending* claim too, so while one member's
Review screen is open, no other member or account — including a second
concurrent upload — can claim the same PAN out from under it.
`attribution.py` was replaced by
`backend/app/services/import_/pan_claims.py`. A known, explicitly
unbuilt gap was named alongside this: a single family CAS statement
covering several people is still only ever attributed to the first
folio's PAN holder, since `casparser` exposes PAN per-folio but folios
carry no holder name — drafted as a plan, not built
(`Docs/superpowers/plans/2026-09-24-per-pan-statement-splitting.md`, not
yet ingested into this vault).

**Resolution of the open CMK-vs-SSM question.** A later infrastructure
commit (`infra/modules/storage/`, evidenced in `log.md`'s engineering-loop
entry) authored a private S3 bucket for CAS files with **SSE-KMS**
encryption and a Lifecycle rule for the 30-day expiry — resolving the
09-18 open question in favor of the customer-managed-key route. As of the
material read for this entry, that Terraform was **authored and reviewed,
not yet applied** — no `.tfstate` existed for it at the time — so the
running application still writes to local disk in every environment. This
corrects an overstatement in this vault's own [ADR-007 addendum written
2026-09-28](../03-decisions/ADR-007-pan-storage-and-encryption.md), which
described the file storage as "S3 in production"; see the correction
addendum appended there.

### Deviation (if any) — decision or response taken

A prior, considered position is reversed here, not silently replaced:
ADR-004 (2026-07-22, "no raw CAS PDF storage, ever; no PAN persistence,
ever," re-confirmed as recently as 2026-09-02 when a PAN-based dedup idea
was raised and rejected in favor of a non-PAN design — see the
[2026-09-02 journey entry](2026-09-02-compliance-audit-group-1-and-non-pan-duplicate-detection.md))
is formally superseded by this decision. ADR-004 itself required "its own
fresh product/security review, including a legal read on DPDP-Act
implications" to reopen — that legal read is not evidenced in the
material read for this entry and remains open (see
[R-066](../07-risks-and-debt.md)).

### Result

PAN persistence and CAS-file retention, previously an explicit, tested
"never," is implemented, tested, and (per the code repository's own
status note) reviewed, sitting on a feature branch as of 2026-09-18/24. A
same-day gap in the first version (first-upload matching) was found and
fixed six days later without reversing the underlying design. The
DPDP-Act legal review ADR-004 itself called for as a precondition to
reopening is not evidenced as having happened.

### Addendum — 2026-09-28: implementation-plan detail now ingested, one dead API field, one enforcement gap named

Three plan documents behind the 2026-09-18/24 work above are now ingested
as evidence: `2026-09-18-pan-cas-attribution.md` (the 09-18 build itself),
`2026-09-24-pan-at-upload-attribution.md` (the 09-24 fix, including the
exact 409 codes `cross_account_pan_blocked`, `pan_belongs_to_other_member`,
`pan_mismatch_for_member`, and a new `/imports/sessions/{id}/discard`
endpoint), and `2026-09-24-per-pan-statement-splitting.md` — a **draft,
not-yet-built** plan for the multi-person-per-statement gap already named
above, proposing a "who-is-who" screen between upload and review (one
person-card per PAN, pre-filled from known household members, a new
`/imports/sessions/{id}/assignments` endpoint) so a family statement that
covers several folios' worth of PANs can be split across members instead
of attributed to the first folio only. All three corroborate the summary
above down to implementation detail; nothing in them contradicts it.

Two items surfaced that the summary above doesn't cover:

- The 2026-09-18 plan's own self-review names a small, deliberately
  deferred cleanup: `CASImportStatusResponse.parse_warnings` and
  `ImportConfirmResponse.warnings` became permanently empty (`[]`) once
  the cross-account case turned into a hard block instead of a soft
  warning, but the fields were left in the API schema rather than removed,
  to avoid an unrelated frontend contract change under that pass's time
  budget.
- Neither plan schedules the `expire_cas_files.py` sweep named above —
  see [R-070](../07-risks-and-debt.md), added this pass.

The two design specs behind the 09-18/09-24 plans
(`2026-09-18-pan-cas-attribution-design.md`,
`2026-09-24-pan-at-upload-attribution-design.md`) were also read this pass;
they corroborate the plans down to the same detail (migrations, encryption
design, the 409 codes, the upload-time rule table) and add nothing new —
the one point that looked new on first read, that preview sessions live in
process memory, is already covered by [R-054](../07-risks-and-debt.md).

#### Addendum evidence

- `08-evidence/documents/plans/2026-09-18-pan-cas-attribution.md`
- `08-evidence/documents/plans/2026-09-24-pan-at-upload-attribution.md`
- `08-evidence/documents/plans/2026-09-24-per-pan-statement-splitting.md`
- `08-evidence/documents/specs/2026-09-18-pan-cas-attribution-design.md`
- `08-evidence/documents/specs/2026-09-24-pan-at-upload-attribution-design.md`

### Related

- [ADR-004](../03-decisions/ADR-004-object-storage-scope-and-cas-pdf-retention.md)
  — superseded by this stage (addendum appended there)
- [ADR-007](../03-decisions/ADR-007-pan-storage-and-encryption.md) —
  the encryption-at-rest direction this stage implements; correction
  addendum appended there for the S3-vs-disk detail
- [R-002](../07-risks-and-debt.md) — raw CAS PDF retention, resolved by
  this stage
- [R-043](../07-risks-and-debt.md) — PAN persistence's five dated
  positions, resolved by this stage (see the ADR-007 addendum)
- [R-066](../07-risks-and-debt.md) — the DPDP-Act legal review and the
  separate, unresolved question of verifying PAN *ownership* at signup
- [R-070](../07-risks-and-debt.md) — new risk this stage's addendum
  creates: the 30-day retention window isn't actually enforced anywhere yet
- Evidence: `08-evidence/documents/orchestration/pan-and-cas-file-storage-design-summary.md`,
  `08-evidence/documents/orchestration/pan-cas-attribution-feature-documentation.md`,
  `08-evidence/documents/orchestration/pan-storage-flow-and-er-diagram.md`,
  `08-evidence/documents/orchestration/pan-storage-map.pdf`,
  `08-evidence/documents/orchestration/pan-storage-map.html`,
  `08-evidence/documents/engineering-loop/log.md` (2026-09-18/24 infra-commit entry)
