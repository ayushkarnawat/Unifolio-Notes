> **Note on scope.** This reference is drafted as an *entity map with the load-bearing
> columns and constraints*, not a column-by-column transcription of the 397-line source.
> Full column tables belong with the code repo's migrations, which are the real source of
> truth and which this vault does not hold. If you want the complete column lists mirrored
> here instead, say so — it is a mechanical expansion, but it will go stale against
> migrations and the vault has no way to detect that.

# Reference: Database Schema

Source of truth: `Database-Schema-Unifolio.md` v1.5 (2026-09-02), itself reconciled
against migrations 0001–0011. The migrations in the code repo are the ultimate
authority; this record exists so the shape is legible without opening them.

The design principles behind this schema are in
[`06-architecture/data-model.md`](../../06-architecture/data-model.md). This page is the
entity list.

## User data (per-user, private)

| Entity | Purpose | Notable columns and constraints |
|---|---|---|
| `users` | The account holder | `phone_number` (sensitive, encrypted at rest). `auth_identities` is the login source of truth, not this table |
| `household_members` | Each person whose portfolio is tracked | `relationship` enum (`self`/`spouse`/`parent`/`child`/`sibling`/`other`) plus a free-text label used only for `other`. Partial unique index on `(user_id) WHERE relationship = 'self'` (migration 0011) — exactly one account-holder row per user |
| `imports` | One CAS upload event; a member has many | `status` — the full 14-value lifecycle enum (widened by migration 0003/0007–0010); `error_code`, `error_message`, `source_tab`, `statement_from_date`, `statement_to_date`, `expires_at`; `raw_parser_output` as `JSONB` (PRD-01 FR-4) |
| `folios` | An account number with one fund house | `plan_type` (Direct/Regular), ARN code where present, `has_coverage_gap` and `coverage_gap_details` |
| `transactions` | The ledger | `NUMERIC` amounts and units, never `FLOAT`. `type` includes `opening_balance`; on Postgres it is a `VARCHAR` + `CHECK`, deliberately **not** a native enum type. **Unique on `(folio_id, date, amount, units, type)`** (migration 0002). Partitioned `BY RANGE(date)`, yearly |
| `portfolio_snapshots` | Monthly computed value per member | Computed, never user-submitted; backfillable |

## Reference data (public, shared platform-wide, no user or household FK)

| Entity | Purpose | Refreshed by |
|---|---|---|
| `schemes` | The scheme master — the universe of funds | Written on first encounter by the Import Service; `amfi_code` is the join key for AAUM |
| `nav_history` | Daily NAV per scheme | Daily job against `mfapi.in`. Partitioned `BY RANGE(date)`, yearly |
| `scheme_ter` | Total expense ratio per scheme per month | Monthly job against AMFI. `ter_value` is **nullable** with a documented meaning — absent is not zero |
| `scheme_aaum` | Average AUM per scheme per quarter | Quarterly job against AMFI |
| `benchmark_index_history` | Daily index levels | Daily job against NSE Indices |
| `arn_directory` | ARN code → distributor name and status | On-demand lookup, first time an unseen ARN appears |
| `fund_scores` | Computed score per fund | Monthly job, aligned to the TER refresh since cost is an input. **Fund-level, not per-user** — portfolio rollups are computed on read |

## Auth

| Entity | Purpose | Notes |
|---|---|---|
| `auth_identities` | How a user logs in — phone, email, Google | The source of truth for authentication. `password_hash` was **removed** by migration 0008 |
| `pending_identity_verifications` | In-flight identity verification | Standalone; not tied to a `users` row at creation. `email_confirmed_at` removed by migration 0008 |
| `otp_requests` | Issued one-time codes | Stored hashed, never raw. Narrowed to phone-only by migrations 0004–0006, then `email` added back by 0007 with a CHECK enforcing exactly one identifier |
| `sessions` | Active logins | Tokens stored hashed. `auth_method` records which identity type was used |

**Removed entirely by migrations 0007/0008:** `password_reset_tokens`,
`email_confirmation_tokens`. Authentication is passwordless throughout.

## Two things that do not exist, deliberately

- **No PAN column, anywhere.** The parsed PAN is transient in memory during the active
  parse/review session, shown masked, and discarded with the source PDF. **This
  describes the schema as it exists today.** [ADR-007](../../03-decisions/ADR-007-pan-storage-and-encryption.md)
  establishes storing an encrypted PAN as planned future work, pending a migration — no
  such migration has been written yet, and no PAN column exists in this schema as of
  this record.
- **No `default_view` column.** The family-aggregate default is computed from a count of
  household members, so it cannot go stale.

**A note on the first of those two.** The no-PAN-column position is now stated
five different ways across five dates — being rewritten to masked-on-display
(2026-08-25), kept as-is until a schema change actually lands (2026-08-26), to
be stored encrypted at rest (ADR-007, 2026-09-16), and reaffirmed live on
2026-09-19 as encrypted both at rest and in transit, with documentation still
pending. Nothing has changed in the schema; no PAN column exists today. The
open question is tracked as R-043 and must not be read as resolved from any
single document.

## History worth knowing

The source document had gone stale by three to four migrations before a compliance audit
caught it on 2026-09-02, at which point `imports`' full status enum, the coverage-gap
columns on `folios`, the `opening_balance` transaction type, and the removal of the
password tables were all reconciled in at once. A second audit pass on the same date
found the `(user_id) WHERE relationship = 'self'` unique index had never been specified
in the document at all, even before the code caught up. **Treat this document as lagging
the migrations by default, not as authoritative over them.**

- **`0006_email_password_auth` (2026-08-17)** added
  `auth_identities.password_hash`, `auth_identities.email_confirmed_at` and
  `pending_identity_verifications.password_hash`; created
  `password_reset_tokens` and `email_confirmation_tokens`; dropped
  `otp_requests.email` and the exactly-one-identifier check constraint; and
  restored `phone_number` to `NOT NULL`. Reversed the same day in product
  terms; password storage was removed again by `0007`–`0008`. The
  `EMAIL_OTP` provider enumeration value was deliberately **not** removed,
  because PostgreSQL enumerations grow cheaply and shrink expensively — which
  is what made the reversal cheap.
- **`0009` is unaccounted for in this vault.** No record here says what it
  does. See R-050.
- **`0010_demat_accounts_and_equity_holdings` (2026-08-26, planned, not
  applied)** adds `demat_accounts`, `equity_holdings`, `bond_holdings`,
  `demat_mutual_fund_holdings` and `equity_price_history`, plus a depository
  type enumeration. Holdings are stored as a **snapshot** keyed on demat
  account, ISIN and statement date — deliberately not as opening-balance
  transactions, which is what the research document had proposed. Bond and
  demat-held mutual-fund tables are created but not surfaced anywhere (R-045).

## Related

- [Data model](../../06-architecture/data-model.md)
- [Migration runbook](../how-to/migrate-sqlite-to-postgres.md)
