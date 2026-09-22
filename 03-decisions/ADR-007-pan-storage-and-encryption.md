# ADR-007: PAN storage and encryption — planned future work

Status: Planned — direction confirmed 2026-09-16, not yet implemented
Date: 2026-09-16
Related: `Updated-CAS-PRD.md` FR-4; ADR-004 (object storage — the related, separate PDF-retention question); `05-docs/reference/database-schema.md`; `06-architecture/quality-and-constraints.md`; `07-risks-and-debt.md` R-001 (resolved by this ADR)

## For stakeholders

Unifolio will store each family member's PAN (Permanent Account Number — the Indian tax
ID printed on a CAS statement), encrypted at rest, so the system can automatically match
an incoming statement to the right family member. This direction was confirmed verbally
by the founders on 2026-09-16, during the same conversation that built this vault — it
is a real decision, not a hypothesis, but nothing has been built for it yet. It also
directly contradicts what three other documents in this batch say: the original CAS PRD,
the database schema, and the technical design all state, as of today, that the PAN is
never persisted anywhere. That is still true of the system as it exists right now — no
PAN column exists in the database. This ADR records the new target state and the
reasoning, so the contradiction is resolved as a decision rather than left as an open
question, and so a future migration has something concrete to build against. One thing
this decision does **not** yet cover: exactly what India's DPDP Act requires for storing
a government-issued tax ID, which needs its own follow-up rather than being assumed
handled here.

## Technical detail

### Status

**Planned, not implemented.** As of 2026-09-16, no PAN column exists in the schema (see
`05-docs/reference/database-schema.md`). This ADR sets the target state for a future
migration; it is not a record of a completed change, and nothing in the current codebase
or schema should be assumed to already reflect it.

### Context

Two positions existed side by side in the batch-1 source documents, unreconciled until
now:

- **(a) Never store the PAN.** PRD-01 FR-2, the Database Schema's Data Classification
  table ("Not persisted at all … No PAN column exists anywhere in this schema"), and the
  TDD's Security NFR ("PAN never persisted (confirmed)") all state this as settled,
  implemented fact.
- **(b) Store it, encrypted, for matching.** `Updated-CAS-PRD.md` FR-4 requires matching
  a CAS-parsed PAN against PAN values stored on file per family member — an exact match
  on a "well-formed 10-character alphanumeric" value, "decrypted only in-memory at match
  time, consistent with the PAN encryption-at-rest policy." That requirement presupposes
  both stored PANs and a PAN encryption-at-rest policy that did not otherwise exist in
  this batch's documents.

This was tracked as **R-001** in `07-risks-and-debt.md`, flagged explicitly as needing a
product-and-security decision rather than a documentation cleanup, because the FR-4
per-member matching feature cannot work without stored PANs — the contradiction was
functional, not editorial.

### Decision

**Unifolio will store each family member's PAN, encrypted at rest**, to support
per-member matching of incoming CAS filings against the correct household member, per
`Updated-CAS-PRD.md` FR-4. This resolves position (b) as the chosen direction. Position
(a) — the current, no-PAN implementation — remains accurate as a description of the
system **as it exists today**; nothing changes until a migration implements this.

### Alternatives considered

#### Option (a): Never store the PAN (the prior, three-document consensus)
**Advantages:** minimum stored PII; simplest DPDP-Act posture; already implemented.
**Disadvantages:** cannot support FR-4's per-member automatic matching — without a
stored PAN to compare against, matching a new import to the correct family member falls
back to manual attribution or weaker heuristics (name, folio history), which is a worse
product experience for the household use case this product is built around.

#### Option (b): Store the PAN, encrypted at rest (chosen)
**Advantages:** enables the per-member matching FR-4 specifies; matches how the founders
now want the household-matching feature to behave.
**Disadvantages:** introduces a government-issued tax ID as stored, encrypted PII where
none existed before — a real increase in sensitive-data surface area, with DPDP Act
compliance implications that are not yet worked out (see Follow-up below). Reverses the
data-minimisation posture ADR-004 argued for on the adjacent question of PDF retention,
so the two decisions should be read together, not assumed to imply the same policy.

### The source of this decision

This decision is a **verbal/relayed founder-and-product decision**, confirmed live in
the vault-building conversation on 2026-09-16 — **it is not yet reflected in any
written, corrected product spec.** `Updated-CAS-PRD.md` FR-4 is the document that
anticipated this direction (it already assumed stored, encrypted PANs), but PRD-01, the
Database Schema, and the TDD have not been corrected to match, and per this vault's
rules they will not be silently edited — they are accurate as descriptions of the
current implementation and stay that way until a real migration lands.

### Consequences

**Positive:**
- Resolves R-001 as a decision rather than leaving it open.
- Unblocks FR-4's per-member CAS matching as a buildable feature.

**Negative / stale documentation flagged, not corrected:**
- A future migration will need to add an encrypted PAN column (or table) plus the
  encryption-at-rest policy and in-memory-only decryption behaviour FR-4 describes.
- **PRD-01 FR-2's "PAN never persisted" statement is now stale** in light of this
  decision. It is not rewritten — per the vault's rule, source material is never edited
  — but it should be read as superseded by this ADR going forward.
- **The TDD's Security NFR ("PAN never persisted (confirmed)") is now stale** for the
  same reason, and is likewise not rewritten.
- The Database Schema's Data Classification table statement ("No PAN column exists
  anywhere in this schema") remains **accurate today** and should stay that way until
  the migration in this ADR's target state actually lands — see the note added to
  `05-docs/reference/database-schema.md`.

**Follow-up required, explicitly not assumed handled by this ADR:**
- **DPDP Act (India) compliance implications** of storing a government-issued tax ID
  apply here and have not been assessed. This needs its own follow-up work — a legal and
  security review — before implementation, not an assumption that "encrypted at rest" is
  sufficient on its own. Tracked in `07-risks-and-debt.md`.

### Validation

This ADR is validated once (1) a migration exists adding the encrypted PAN
column/table, (2) the encryption-at-rest and in-memory-only decryption behaviour FR-4
specifies is implemented and reviewed, and (3) a DPDP Act compliance review of storing a
government tax ID has been completed. None of the three is true as of this ADR's date.

### Evidence

- Anticipating document: `Updated-CAS-PRD.md` FR-4, now at
  `08-evidence/documents/Updated-CAS-PRD.md`.
- Resolving decision: this vault-building conversation, 2026-09-16 — a verbal/relayed
  founder-and-product decision, not yet captured in any written, corrected product spec.
  No other evidence artifact exists for it yet.
- Contradicting (now stale, not rewritten): `08-evidence/documents/PRD-01-CAS-Parser-v2.md`
  FR-2; `08-evidence/documents/Database-Schema-Unifolio.md` Data Classification table;
  `08-evidence/documents/TDD-Unifolio.md` Security NFR.

## Addendum — 2026-09-18: earlier written evidence found, and a mechanism discrepancy

Ingesting the 2026-08-17 → 2026-08-31 plans and specs surfaced written material
about PAN persistence that predates this ADR by three weeks. It is recorded
here without altering anything above.

**What was found.** The 2026-08-25 Phase 2 demat research document and its
companion decision memo both state, as a starting constraint, that "the 'no PAN
persistence, ever' rule is being rewritten: Unifolio will now store PAN, masked
wherever displayed." This ADR's Context notes that the reversal had no written
artifact. It has one.

**Why this does not simply confirm the ADR.** Three differences:

1. **Mechanism.** This ADR specifies PAN encrypted at rest. The 2026-08-25
   documents specify PAN masked wherever displayed. Those are different
   controls — one governs storage, one governs presentation — and satisfying
   one does not satisfy the other.
2. **Purpose.** This ADR's motivation is per-member matching against CAS
   filings (`Updated-CAS-PRD.md` FR-4). The 2026-08-25 motivation is automated
   ingestion of emailed depository statements, a Phase 2 concern that did not
   exist when FR-4 was written.
3. **A later contrary decision.** On 2026-08-26 — one day after those
   documents, and three weeks before this ADR — the Phase 2 backend
   implementation plan recorded: "Decided during planning: keep
   never-persisting PAN. Revisit if/when that reversal actually lands in the
   schema."

The 2026-08-25 decision memo also contradicts itself internally: it lists the
rule-being-rewritten among its starting constraints, then later asserts that a
clipboard pre-fill trick "cannot extend to PAN" precisely because the hard
no-PAN rule still stands.

**Status unchanged.** This ADR remains *Planned — not yet implemented*. No PAN
column exists in the schema. Nothing above is superseded by this addendum; the
new evidence is registered and the resulting open questions are tracked as
R-043, which needs a human decision on whether PAN is stored, by what
mechanism, and for which purpose.

### Addendum evidence

- `08-evidence/documents/specs/2026-08-25-phase-2-stocks-demat-research.md` (§7-A, §8a)
- `08-evidence/documents/specs/2026-08-25-phase-2-demat-integration-decision-memo.md` (starting constraints; option H)
- `08-evidence/documents/plans/2026-08-26-phase-2-stocks-demat-import-backend.md` (deviation 1)

## Addendum — 2026-09-19: direction reaffirmed, in-transit detail added, documentation pending

In a live conversation, the vault owner reaffirmed this ADR's direction:
PAN will most likely be stored encrypted at rest, consistent with the
decision above, and will most likely also be encrypted in transit (stated
verbally as "TLS 3.1" — no such protocol version exists; TLS 1.3 is the
current standard and the most plausible intended reference, recorded here
as an inference, not a confirmed fact). Detailed documentation is being
prepared by a colleague and does not yet exist.

**Status unchanged.** This ADR remains *Planned — not yet implemented*.
No PAN column exists in the schema. This addendum does not settle R-043 —
it narrows the range of open questions (storage mechanism direction is
now reaffirmed) without closing them (in-transit mechanism unconfirmed,
no written documentation yet to cite as a source).

Source: vault owner, live conversation, 2026-09-19.
