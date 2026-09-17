# ADR-004: Object storage — S3 scoped to reference-data cache and exports; the CAS PDF is not retained

Status: Accepted
Date: 2026-07-22
Related: ADR-003 (where user data actually lives), `06-architecture/quality-and-constraints.md`,
`07-risks-and-debt.md` (contradicting statement in `Updated-CAS-PRD.md`)

## For stakeholders

This decision is about *files*, not about whether a user's portfolio persists — it does,
permanently, in the database (ADR-003). Two questions needed answering: what belongs in
Amazon's file-storage service (S3), and whether we keep the original statement PDF a
user uploads. The answers: S3 holds cached copies of public market data and, later, any
statements we generate for users to download. The **original uploaded CAS PDF is not
kept anywhere** — it is parsed and then discarded. We weighed keeping it, which would
have allowed re-download and an audit trail, against the fact that it contains a full
unmasked PAN and that India's DPDP Act favours holding no more personal data than the
product actually needs. The product's value is the structured portfolio data, not
document storage; a user who wants their original statement can always request it from
CAMS or KFintech again. This is final, not an open question.

## Technical detail

### Context

Every holding, transaction, household member, and user profile is structured, relational
data and belongs in RDS/PostgreSQL permanently (ADR-003). A user uploads a CAS once; the
parsed result lives in Postgres from then on. They return and see their portfolio without
re-uploading. They upload again only to *add* new data. None of that is what this ADR
decides.

What this ADR scopes is what belongs in **S3 specifically** — an object/blob store suited
to files and large cached datasets, not to relational, queryable, joined data (a
household's holdings across members, XIRR across a transaction history). Two candidates:
(1) the raw uploaded CAS PDF, and (2) cached copies of public reference data (AMFI TER
and AAUM, NSE index history, `mfapi.in` NAV snapshots) plus future generated exports.

### Decision drivers

- Data minimisation under India's DPDP Act — the raw PDF carries a full unmasked PAN.
- PRD-01 already specified delete-after-parse; the question was whether the
  wealth-management direction justified reopening it.
- PRD-04's analytics depend on repeatedly-fetched public datasets that benefit from a
  durable, cheap cache.
- Each store should do the job it is good at.

### Options considered

#### Option 1: S3 scoped to reference-data cache + future exports; PDF discarded (chosen)
**Advantages:** gives PRD-04's TER/AAUM/NSE integrations a durable, cheap cache layer,
reducing repeated calls to AMFI and NSE and lowering the automation-frequency risk
those PRDs already flag; clean separation of concerns — Postgres for structured,
queryable, permanent user data, S3 for files and caching; minimises stored PII.
**Disadvantages:** requires explicit bucket policy and access controls set up correctly
from day one (private by default, scoped IAM roles) — S3 is not default-safe out of the
box; adds a second piece of AWS infrastructure to secure before launch.

#### Option 2: Retain the original CAS PDF in S3 long-term
**Advantages:** enables user re-download of their own source document and gives an
audit trail of exactly what was parsed.
**Disadvantages:** stores a full unmasked PAN and original formatting — sensitive
surface area with no corresponding product need, since the structured data is
everything the product uses; triggers legal-review overhead under DPDP-Act
data-minimisation; inconsistent with the product's value proposition, which is
structured portfolio data and analytics, not document storage.

#### Option 3: No object storage at all — keep everything in RDS/Postgres
**Advantages:** one fewer service to configure and secure.
**Disadvantages:** rejected — cached reference datasets (full NAV history across the
scheme universe, TER data) do not belong in the relational database's primary storage
path at the volumes PRD-04 implies. A blob store is the standard fit.

#### Option 4: Stage the CAS PDF in S3 temporarily during processing
**Advantages:** avoids depending on local container temp storage.
**Disadvantages:** considered, not adopted for v1 — local temp storage with guaranteed
deletion is simpler to reason about and audit than an S3 upload-then-delete cycle, and
avoids a network hop for a file that is meant to be short-lived. Note this is a
*different* question from permanent retention; revisit only if the processing
architecture changes.

### Decision

Use **AWS S3** for (1) cached copies of public reference data (AMFI TER/AAUM, NSE index
history, `mfapi.in` NAV snapshots) supporting PRD-04's analytics, and (2) future
generated user-facing exports (PDF/CSV statements), if and when that feature is built.

**The original uploaded CAS PDF is not retained — not in S3, not elsewhere.** PRD-01's
delete-after-parse behaviour stands as a final decision. None of this affects portfolio,
transaction, household, or user data, which persists permanently in Postgres per ADR-003.

### Consequences

**Positive:**
- Durable, cheap cache for the reference-data integrations.
- Clean separation of concerns between the two stores.
- Minimum stored PII; cleaner DPDP-Act compliance posture.

**Negative:**
- Bucket policy and scoped IAM roles must be correct from day one.
- A second piece of AWS infrastructure to configure and secure before launch.

**Neutral:**
- If this is ever revisited because a future feature genuinely requires the original
  document, that needs its own fresh product and security review including a legal read
  on DPDP-Act implications — not a casual infrastructure afterthought.

### Validation

Validated by inspection at deployment: no code path writes the uploaded PDF to durable
storage, no schema column references a source document (confirmed in
`06-architecture/data-model.md`, Design Principle 3), and the bucket is private with
scoped IAM. **Open conflict:** `Updated-CAS-PRD.md` FR-3 and its NFR table contemplate
retaining the raw PDF with a 7-day encrypted window. See `07-risks-and-debt.md` — this
ADR is treated as authoritative pending your confirmation.

### Evidence

- Source document: `08-evidence/documents/ADR-Technical-Stack-Decisions.md`
  (ADR-004 and its "Decision: CAS PDF Is Not Retained" section)
- Corroborating: `Database-Schema-Unifolio.md` Data Classification table ("No PAN column
  exists anywhere in this schema")
- Conflicting: `Updated-CAS-PRD.md` FR-3 Security, NFR table
