# Backend technical walkthrough — staging, for a live demo

**Read this first, before the demo starts.**

## ⚠️ Do this check before you demo anything

Staging's database schema is currently **behind** the code that's deployed. Three
migrations (`0012`, `0013`, `0014`) were authored after the last confirmed migration
run (`0011`) and, as of this writing, had **not** been applied to the real RDS
instance. If that's still true when you read this, two features in the running app
will 500 the moment you touch them live in front of your reviewer:

- **Account deletion** — needs `users.pending_deletion`, `users.deletion_scheduled_at`,
  and the `account_deletion_surveys` table (migration `0013`).
- **Analytics dashboard** — needs `analytics_sections` (migration `0012`) and
  `analytics_recompute_status.generation` (migration `0014`).

Run this first (5 minutes) to check, and fix it if needed:

```bash
export REPO_ROOT="/mnt/d/Unifolio code"
export BASTION_ID=i-0b67d40d9b58b7814
export RDS_HOST=staging-rds.ctu88scmut9m.ap-south-1.rds.amazonaws.com

# Terminal A — open the tunnel, leave it running
aws ssm start-session --target "$BASTION_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$RDS_HOST\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5433\"]}"
```

```bash
# Terminal B
export MASTER_SECRET_ARN=$(terraform -chdir="$REPO_ROOT/infra/envs/staging" \
  output -raw master_user_secret_arn)
export DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id "$MASTER_SECRET_ARN" \
  --query SecretString --output text | python3 -c "import json,sys; print(json.load(sys.stdin)['password'])")

cd "$REPO_ROOT/backend" && source .venv/bin/activate
export DATABASE_URL="postgresql+psycopg2://unifolio:${DB_PASSWORD}@127.0.0.1:5433/unifolio"
python -m alembic current
```

- If it prints `0014 (head)` → you're good, skip to the walkthrough below.
- If it prints anything earlier (`0011`, `0012`...) → run `python -m alembic upgrade head`,
  confirm it re-prints `0014 (head)`, then `Ctrl-C` Terminal A's tunnel.

Full context/rationale for this drift and the rest of the still-pending deploy steps:
`Docs/superpowers/plans/2026-09-11-aws-staging-prerequisites.md`.

---

## 1. How to connect to the staging database, live

Staging's RDS instance has **no public access** (`publicly_accessible = false`) — the
only path in is through an SSM Session-Manager-only bastion EC2 instance that has no
inbound security-group rules at all. You tunnel through it, then talk to Postgres
normally over the tunnel.

```bash
export BASTION_ID=i-0b67d40d9b58b7814
export RDS_HOST=staging-rds.ctu88scmut9m.ap-south-1.rds.amazonaws.com

# Terminal A — opens and holds the tunnel (Ctrl-C when done)
aws ssm start-session --target "$BASTION_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$RDS_HOST\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5433\"]}"
```

```bash
# Terminal B — get the password, then connect
export MASTER_SECRET_ARN=$(terraform -chdir="/mnt/d/Unifolio code/infra/envs/staging" \
  output -raw master_user_secret_arn)
export DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id "$MASTER_SECRET_ARN" \
  --query SecretString --output text | python3 -c "import json,sys; print(json.load(sys.stdin)['password'])")

PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p 5433 -U unifolio -d unifolio
```

(No `psql` client installed locally? Use the backend's own Python venv instead —
`cd backend && source .venv/bin/activate && python -c "import psycopg2; ..."`, or point
any GUI client — TablePlus, DBeaver — at `127.0.0.1:5433` while the tunnel is open.)

Once connected, `\dt` lists every table below.

**Why the password looks awkward to fetch:** it's Terraform-generated and contains
shell metacharacters (`$`). Never paste it into a double-quoted string by hand — the
`python3 -c` step above is what avoids silent corruption from bash variable expansion.

---

## 2. Every table, what it stores, what it deliberately doesn't

Grouped the way your reviewer will care about — identity/auth, the actual portfolio
data, reference/market data, analytics cache, and the deletion-lifecycle tables.

### Identity & auth

| Table | What's in it | What's NOT in it |
|---|---|---|
| `users` | `phone_number` (unique, mandatory), `email` (optional), `onboarding_step`, `onboarding_completed_at`, `investor_type`, `primary_goal`, `pending_deletion` + `deletion_scheduled_at` (soft-delete state) | **No PAN, no name, no password, no date of birth.** `users` is a provider-agnostic anchor — it exists so multiple auth methods (phone/email/Google) can point at one identity, not a profile table. |
| `auth_identities` | One row per verified login method per user: `provider` (phone_otp / email_otp / google), `provider_subject` (the phone number, email, or Google `sub` claim), `identifier_verified_at`, `last_used_at` | No password/OTP value itself — that's `otp_requests` (below), and it's a hash. |
| `otp_requests` | `phone_number` OR `email` (a DB check constraint enforces exactly one), `otp_hash`, `expires_at`, `attempt_count` | **Never the raw OTP** — only its hash. Also **no `user_id` FK** — deliberate, so the same code path serves phone and email OTP before a user necessarily exists yet (signup case). |
| `sessions` | `session_token_hash`, `auth_method`, `expires_at`, `last_active_at`, `device_info` | **Never the raw session token** — only its hash. |
| `pending_identity_verifications` | A just-verified Google/email identity waiting to either complete signup (needs phone) or resolve a collision (step-up re-auth) — `token_hash`, `expires_at` | Never the raw verification token. |
| `household_members` | `name`, `relationship` (self/spouse/parent/child/sibling/other), belongs to a `user_id` | This is where a human name actually lives — one `users` row can have several `household_members` (e.g. self + spouse's folios tracked together). |

### Portfolio data (per household member)

| Table | What's in it | Notes |
|---|---|---|
| `imports` | One row per CAS upload: `status` (pending/confirmed/failed/...), `source_cas_type`, `raw_parser_output` (JSON), `statement_from_date`/`to_date`, `new_transactions_count`/`duplicate_transactions_count` | This is what gets deleted in §4 below. |
| `folios` | `folio_number`, `arn_code`, `plan_type`, `has_coverage_gap` + `coverage_gap_details` (JSON) — links a household member to a `scheme_id` | Unique on `(household_member_id, scheme_id, folio_number)`. |
| `transactions` | `type`, `date`, `amount`, `units`, `nav`, `raw_description`, points at `folio_id` + `import_id` | **Partitioned by year on Postgres** (`RANGE(date)`) — the ORM model doesn't show this, it's physical-schema-only. Deduped on `(folio_id, date, amount, units, type)` — that 5-column tuple is the identity of "the same transaction," used at import time to skip re-inserting duplicates. |
| `portfolio_snapshots` | `total_value` per `household_member_id` per `snapshot_month` | Monthly rollup, not live-computed every request. |

### Reference / market data (platform-wide, no user FK)

| Table | What's in it |
|---|---|
| `schemes` | AMFI code, ISIN, name, AMC name, SEBI category, plan variant — the fund master list |
| `nav_history` | Daily NAV per scheme |
| `scheme_ter` | Total expense ratio per scheme per period (nullable value = "checked AMFI's feed, found nothing" vs. no row = "never checked") |
| `scheme_aaum` | AUM per scheme per period |
| `benchmark_index_history` | Daily index values (e.g. Nifty) for benchmarking |
| `arn_directory` | Distributor ARN → status lookups |
| `fund_scores` | Precomputed Fund Score inputs per scheme: `risk_adjusted_tier`, `cost_adjustment`, `final_score` |

### Analytics cache

| Table | What's in it |
|---|---|
| `analytics_sections` | One row per `(user_id, scope_key, section)` — the precomputed JSON payload the dashboard actually reads. `scope_key` is `"combined"` or a member ID string. No live computation happens on a normal page load; this table is the read path. |
| `analytics_recompute_status` | One row per user: is a recompute currently running (`started_at`), and a `generation` counter used to invalidate stale in-flight computations when data changes underneath them (see §4). |

### Account-deletion lifecycle

| Table | What's in it |
|---|---|
| `account_deletion_surveys` | `reason`, optional free-text `feedback`, `created_at` — **deliberately has no `user_id` FK.** Anonymous product feedback, kept even after the account itself is gone. |

---

## 3. Which accounts exist, live — query it in front of your reviewer

With the `psql` session from §1 open:

```sql
-- How many real accounts exist, and their lifecycle state
SELECT id, phone_number, email, onboarding_step, onboarding_completed_at,
       pending_deletion, deletion_scheduled_at, created_at
FROM users
ORDER BY created_at DESC;

-- Every login method attached to each account
SELECT u.phone_number, ai.provider, ai.provider_subject, ai.identifier_verified_at
FROM auth_identities ai JOIN users u ON u.id = ai.user_id
ORDER BY u.phone_number;

-- Household members per account (this is where names live, not `users`)
SELECT u.phone_number, hm.name, hm.relationship
FROM household_members hm JOIN users u ON u.id = hm.user_id
ORDER BY u.phone_number;

-- Anyone currently in the 5-day deletion grace period right now
SELECT phone_number, deletion_scheduled_at
FROM users WHERE pending_deletion = true;
```

**Talking point for the "what does the account store" question:** `phone_number` and
`email` are the only literal PII columns on `users` itself — no PAN field exists
anywhere in this schema (grep `backend/app/models/*.py` for `pan` live if asked — zero
hits), no plaintext password, no plaintext OTP or session token (both are hashed
before storage, in `otp_requests.otp_hash` / `sessions.session_token_hash`).

---

## 4. Import deletion — what actually happens, row by row

Route: `DELETE /imports/{import_id}` → `delete_household_import`
(`backend/app/api/imports.py:75`).

**Live demo query, before you click delete** (note the import ID and folio IDs):

```sql
SELECT id, status, uploaded_at FROM imports WHERE household_member_id = '<member-id>';
SELECT DISTINCT folio_id FROM transactions WHERE import_id = '<import-id>';
SELECT count(*) FROM transactions WHERE import_id = '<import-id>';
```

Then click delete in the app (or `curl -X DELETE .../imports/<import-id>`), and walk
through what just happened, in the exact order the code does it:

1. **Ownership check** — confirms the import belongs to a household member owned by
   the calling user (join on `household_member_id`), 404s otherwise.
2. **Every `transactions` row with that `import_id` is deleted.** This is a hard
   delete, not a soft flag — the dedupe identity (`folio_id, date, amount, units,
   type`) means these exact rows can never silently reappear from a re-upload of the
   same statement; they'd just be re-inserted as "new."
3. **Per affected folio:** if it has zero transactions left, the `folios` row itself
   is deleted too (nothing to show without transactions). If it still has other
   transactions (from a different, still-live import), its coverage-gap fields
   (`has_coverage_gap`, `coverage_gap_details`) are **recomputed**, not deleted — the
   remaining transaction history might now have a hole where the deleted import used
   to fill it in.
4. **The `imports` row itself is deleted.**
5. **The analytics-recompute `generation` counter is bumped** — deliberately *before*
   deleting the cached `analytics_sections` rows, not after. If a background analytics
   worker is mid-computation for this user right now, this ordering guarantees it either
   aborts (sees the bumped generation) or loses the race cleanly (this delete waits
   for its row lock, then removes whatever it just wrote) — either way stale numbers
   never survive the delete.
6. **All `analytics_sections` rows for this user are deleted** — forces the dashboard
   to show a fresh "recomputing" state instead of stale numbers from before the
   deletion.
7. **Commit.** Only after the commit is the in-memory holdings cache invalidated —
   if it were invalidated before commit, a request racing the delete could read
   pre-delete data and re-populate the cache with it, and nothing left in the delete
   itself would ever clear that stale entry.

**Verify live, right after:**

```sql
SELECT count(*) FROM transactions WHERE import_id = '<import-id>';        -- 0
SELECT count(*) FROM imports WHERE id = '<import-id>';                     -- 0
SELECT count(*) FROM analytics_sections WHERE user_id = '<user-id>';       -- 0 (will repopulate on next dashboard load)
```

---

## 5. Account deletion — the 5-day grace period, for completeness

Not what "import deletion" refers to, but likely worth showing since it's the other
deletion flow in the app (`backend/app/services/auth/account_deletion.py`).

- **Request delete** (`schedule_account_deletion`): sets `users.pending_deletion =
  true`, `users.deletion_scheduled_at = now + 5 days`, and logs an anonymous row in
  `account_deletion_surveys` (reason + optional feedback — no `user_id`, so it
  survives the account's eventual deletion). The account still works normally during
  the 5 days.
- **Undo** (`reactivate_account`): flips both fields back, no trace left.
- **Actual hard delete** (`hard_delete_expired_accounts`, run daily by the
  `unifolio-staging-job-account-deletion-daily` scheduled ECS task): finds every user
  past their `deletion_scheduled_at`, then deletes in this order — bump analytics
  generation → transactions → imports → portfolio_snapshots → analytics_sections
  (household-scoped) → folios → analytics_sections (user-scoped) →
  analytics_recompute_status → pending_identity_verifications → sessions →
  every `otp_requests` row matching any identifier this user ever verified (collected
  from `users.phone_number`/`email` and every `auth_identities` row, since
  `otp_requests` has no `user_id` FK to cascade on directly) → `auth_identities` →
  `household_members` → the `users` row itself.

```sql
-- confirm the daily job has actually run and cleared anyone past due
SELECT count(*) FROM users WHERE pending_deletion = true AND deletion_scheduled_at <= now();
```

---

## 6. Quick reference — resource IDs used above

```
AWS account:      811364789032, region ap-south-1
Bastion (SSM):    i-0b67d40d9b58b7814
RDS endpoint:     staging-rds.ctu88scmut9m.ap-south-1.rds.amazonaws.com:5432
DB name/user:     unifolio / unifolio
ECS cluster:      unifolio-staging
ECS service:      unifolio-staging-backend
ALB:              unifolio-staging-alb-958627457.ap-south-1.elb.amazonaws.com
```
