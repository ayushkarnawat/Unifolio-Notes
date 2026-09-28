# Unifolio Backend Audit — originally 2026-09-15, updated 2026-09-16

Read-only audit for internal understanding. No code was changed to produce this report.
The first pass (2026-09-15) was compiled from a checkout that predated several commits
the user hadn't yet synced — most importantly, it wrongly concluded "nothing is staged on
AWS." This update was compiled from a fresh 4-way parallel review after the sync,
specifically targeting what changed: the actual AWS deployment state, three new database
migrations, a full analytics-architecture rework, and a new "investor beta" feature
batch. Sections below are marked **[UPDATED]** where this pass changed the original
conclusion; everything else was re-confirmed still accurate. Every claim carries file/line
references, verified against the code directly, not taken from stale docs.

---

## 0. The one-paragraph version **[UPDATED]**

Unifolio's backend is a Python/FastAPI app backed by SQLAlchemy models and Alembic
migrations. Locally it runs on SQLite; staging/production is Postgres. There is no
password login anywhere — people sign in with phone OTP, email OTP, or Google, and phone
is mandatory for every account. The core of the product is a pipeline that parses your
CAS (Consolidated Account Statement) into a clean transaction ledger, from which
everything else — the holdings dashboard, cash flow, SIP tracking, and the more advanced
analytics (fund scoring, category ranking, benchmark comparison) — is computed using FIFO
lot accounting and Decimal-precision math (never floating point, because this is money).
**Real AWS infrastructure now exists and is genuinely running** — networking, a Postgres
database, and the backend API (ECS Fargate behind a load balancer) are live and verified
in `ap-south-1`. However, **the deployment is only partial**: there is currently no
frontend deployed anywhere and no working domain/HTTPS layer, so there is **not yet a
usable staging link** a person could open in a browser — only a raw, unsecured backend
address (see §2 for the full breakdown, and a direct note on the "we already have a
staging link" question). Since the first audit pass, the team also shipped a major
architecture change (analytics moved from computing everything live on each request to a
scheduled precompute/cache model) and a batch of new user-facing features (profile
management, account deletion, changing your phone/email, import history, a new XIRR
figure on the main dashboard, and an allocation drill-down view) — both are code-complete
but have real, specific gaps before they're fully live in staging (see §6 and §9).

---

## 1. Recent history — what was done, in order, and why **[UPDATED — extended through 2026-09-11]**

**Mid-to-late August: the Analytics backend was built.** The full analytics engine
(category allocation, expense-ratio analysis, benchmark comparison, category ranking,
and the fund "Scorer") was built in 5 sequential phases, each requiring new integrations
with external data feeds (AMFI's fee/size data, NSE's index data) that had to be
reverse-engineered live because the documented API shapes were stale.

**A frontend redesign was reviewed and caught real bugs.** An external contributor (via
Google Antigravity) rebuilt the UI. The mandatory review process caught that the
contributor's own "all tests pass" claim was false (39 of 104 tests were actually
failing) and found three real bugs: a floating-point sum on the dashboard's headline
total (violating this project's hard "never float for money" rule), an "Add Data" button
that could silently misattribute an upload to the wrong family member, and a broken
accessibility label. All three were fixed before merge.

**Late August/early September: application-code hardening for AWS.** A formal
compliance/readiness audit found 13 blockers (10 critical) that would break the app the
moment it ran against real Postgres/cloud infrastructure. This produced: staging-code
fixes (CORS, container binding, upload validation, a corrected OTP-stub production
safety switch, a new Dockerfile, dependency cleanup), an enum-drift migration fix, the
"NAV-unavailable degraded row" feature (F8), 4 background data-refresh scripts (F4), and
non-PAN duplicate-person detection — all independently verified, not self-reported.

**2026-09-07: AWS account and domain groundwork.** An AWS account was created (root MFA,
budget alert, an IAM admin user), region `ap-south-1` was chosen, and `unifolio.in` was
cut over from GoDaddy to a Route 53 hosted zone (propagation verified, existing
Microsoft 365 mail records preserved). Domain architecture was decided:
`unifolio.in` (apex) = marketing site, `app.unifolio.in` = production app,
`staging.unifolio.in` = staging app. Networking was decided to use **fck-nat**
(a self-hosted EC2 NAT alternative) instead of a managed NAT Gateway, specifically to
avoid a cost-approval step.

**2026-09-09: real infrastructure applied to AWS for the first time.** Terraform Phases
1–3 (networking/VPC, RDS Postgres, ECS Fargate backend + ALB + ECR) were applied for
real — 57 AWS resources created — and independently verified: ALB target-group health
checked via `aws elbv2 describe-target-health`, CloudWatch logs tailed clean, a real OTP
request round-tripped through ALB → ECS → RDS, and the ECS task confirmed stable via
`aws ecs describe-tasks`. Along the way: an ECS crash-loop from an empty ECR repo was
fixed by a manual image push; a corrupted RDS password (containing a literal `$` that
bash was silently mangling) was fixed; and a real security incident occurred and was
resolved same-session — an AWS access key was briefly pasted into chat and committed to
`session.md`, GitHub's push protection blocked the push, and the key was rotated and the
commit rewritten before it ever left the machine.

**2026-09-02 to 2026-09-10: the analytics precompute architecture was designed and
built.** Rapid tab-switching on the Analytics dashboard was firing up to 7 concurrent
live-compute requests, some of which took minutes (uncached NAV-warming, the Scorer),
exhausting the database connection pool badly enough that even the page someone was
actually looking at would fail. The fix was a full architecture change, not a quick
patch — see §6. This shipped through 4 rounds of adversarial review, PASS, zero findings,
and the ADR-006 scheduler Terraform for it was applied to staging (commit `20a825e`).

**2026-09-11: an "investor beta" feature batch shipped.** Six user-facing features —
Profile, account deletion (with a grace period), changing your phone/email, import
history, a new XIRR figure on the main dashboard, and an allocation drill-down view (see
§9 for full detail). **Important caveat, not present in the first audit pass:** this
batch went through 3 rounds of fixes, but only the first round's fixes were independently
adversarial-reviewed. The last two rounds — including a database-generation
race-condition fix and an OTP-cleanup-on-account-deletion fix, both concurrency/
security-adjacent — were implemented directly and self-verified (Codex was
usage-limited that session), with the mandatory review gate explicitly deferred, not
run. The relevant handoff doc's status is still marked `OPEN`, not `DONE`. Test suites
are green (649 backend / 437 frontend), but two new Postgres-specific cascade-delete
tests have never actually executed against a real Postgres database in this environment.

**No commits exist past 2026-09-11 in the checked-out branch as of this update
(2026-09-16)** — the gap between the last commit and today has not yet been used to
close any of the open items below.

---

## 2. Current deployment status **[UPDATED — this was wrong in the first pass]**

**Direct answer to "we already have a staging link, it's already staged":** partially
true, and worth being precise about, because the difference matters for what you can
actually show someone. What follows is verified against real AWS API calls, not just
Terraform files.

**Genuinely applied and verified live in `ap-south-1` (account `811364789032`):**
- **Networking** — a real VPC (`vpc-0570cc60e505184ed`), subnets, routing, a fck-nat
  instance, and an SSM-only bastion host (no public SSH).
- **Database** — RDS Postgres 16, reachable, schema present (though see the gap below).
- **Backend API** — ECS Fargate running the FastAPI app behind an Application Load
  Balancer, with a real ECR image. Confirmed live and healthy: the ALB's target group
  reports healthy, logs are clean, a real signup OTP request was round-tripped all the
  way through the load balancer into the database and back, and the running task is
  stable.

**Authored and reviewed, but NOT applied — this is the gap:**
- **The frontend** (the actual web app UI, meant to be served from S3+CloudFront) has
  no bucket, no distribution — nothing has ever been deployed. There is currently
  **no web app reachable at any URL.**
- **The domain/HTTPS layer** (Route 53 records + TLS certificate for
  `staging.unifolio.in` / `staging-api.unifolio.in`, plus the ALB HTTPS listener) is
  also unapplied. The Route 53 hosted *zone* for `unifolio.in` is real (DNS was cut over
  from GoDaddy on 2026-09-07), but the specific *records* for staging don't exist yet.

**What this means concretely:** the only thing reachable right now is a raw backend
address — `unifolio-staging-alb-958627457.ap-south-1.elb.amazonaws.com` — over plain
HTTP, with no custom domain and no TLS. That's an API endpoint, not something a person
could open in a browser and see the app. **There is not yet a working staging link.**
If a link exists that you've personally opened and seen the app load, that would mean
something was deployed outside this repo's Terraform (e.g. a quick manual S3/Vercel
push) — worth flagging so it can be reconciled with the infra-as-code, rather than
treating it as separately maintained going forward.

**Additional gaps found on top of the frontend/domain gap:**
- **The database schema on the real staging RDS is stale.** It was last confirmed
  migrated to `0011`. Three newer migrations (`0012`–`0014`, covering the analytics
  precompute tables and account-deletion grace period — see §3) have **not** been
  applied there yet.
- **The deployed backend image itself is stale** — it predates the entire analytics
  precompute rework and the whole 2026-09-11 investor-beta feature batch. Redeploying a
  fresh image is a separate step from applying the frontend/domain Terraform.
- The new EventBridge job for the analytics recompute backstop, and its dedicated ECS
  task role, are authored but not applied.
- The current working branch (`feat/enhanced-ui`) is ahead of its remote and hasn't been
  promoted to `main` (which auto-deploys to staging) or `production`.

**What's blocking the rest** is mostly a short, known sequence of manual steps (apply
the remaining Terraform, run the pending migrations against real RDS, rebuild and push a
fresh backend image, promote the branch) rather than open design questions — a written
runbook for exactly this exists (`Docs/superpowers/plans/2026-09-11-aws-staging-prerequisites.md`).

**Unchanged from the first pass:** the backend is intentionally a single running
instance for now — several caches (holdings, distributor-comparison, the analytics
Scorer's category cache, import-preview sessions) live in that one process's memory, not
a shared store like Redis. Fine for one instance; means no automatic failover once real
users are on it. Fixing this is deliberately scheduled for after launch.

---

## 3. Database schema **[UPDATED — 3 new migrations added]**

### 3.1 How it's built

Every table is a SQLAlchemy model under `backend/app/models/`, versioned through 14
Alembic migrations (`backend/alembic/versions/0001`–`0014`). The schema works on both
SQLite (local/dev) and Postgres (staging/production) — see §3.6. All primary keys are
UUIDs, not auto-incrementing integers.

**Important structural note, unchanged:** there are no ORM-level relationships (no
`relationship()` declarations) and no cascading deletes at the database level — every
link is a plain foreign key column. Deleting a parent record does not automatically
clean up its children; that's handled explicitly in application code where it matters
(see the new account-deletion cascade in §3.4/§9.2, which is a hand-written, carefully
ordered delete sequence specifically because the database won't do it automatically).

### 3.2 Every table, in plain words **[UPDATED — 3 tables added, `users` gained 2 columns]**

| Table | What it's for, in plain words |
|---|---|
| `users` | One row per person with a Unifolio account. Phone number is mandatory and unique. Now also tracks whether the account is **pending deletion** and, if so, **when** it will be permanently deleted (added 2026-09-11 — see below). |
| `household_members` | The people whose portfolios are tracked under one login — themselves ("self") or family. Exactly one "self" row allowed per user. |
| `folios` | One row per real-world mutual fund folio number a household member holds with a fund house. |
| `schemes` | The shared master catalogue of mutual fund schemes available in India. Platform-wide reference data. |
| `nav_history` | Daily price-per-unit (NAV) history for every scheme. |
| `scheme_ter` | Each scheme's expense ratio (fee %) by reporting period. |
| `scheme_aaum` | Each scheme's average fund size by reporting period. |
| `benchmark_index_history` | Daily values of the 4 tracked Nifty market indices. |
| `arn_directory` | A lookup of distributor codes (ARNs) and whether they're currently active. |
| `fund_scores` | Unifolio's own computed quality score for a fund at a point in time. |
| `transactions` | Every buy/sell/dividend/switch transaction line pulled from a CAS statement — the core ledger. |
| `imports` | One row per CAS-statement upload attempt — its whole lifecycle from "uploaded" to "confirmed" or "failed." |
| `portfolio_snapshots` | A saved month-end total portfolio value per household member. |
| `otp_requests` | A one-time code texted or emailed during login/signup, and whether it was verified. |
| `auth_identities` | One row per login method linked to an account (phone, email, Google). |
| `pending_identity_verifications` | A short-lived holding pen for a just-verified login that isn't complete yet. |
| `sessions` | An active logged-in session. |
| **`analytics_sections`** *(new, 2026-09-03)* | One row per (user, household scope, analytics section) — the precomputed result of one piece of the analytics dashboard (allocation, TER, benchmark, category ranking, score, etc.), so a page load is a cheap lookup instead of a live computation. See §6. |
| **`analytics_recompute_status`** *(new, 2026-09-03, extended 2026-09-11)* | One row per user, tracking whether a background recompute of their analytics is currently running, and a version counter ("generation") used to detect and discard stale, in-progress work. See §6. |
| **`account_deletion_surveys`** *(new, 2026-09-11)* | An anonymous log of "why did this person delete their account" exit-survey answers. Deliberately has no link back to the user — kept as product feedback that outlives the account itself. |

Two tables existed briefly and were fully removed: `password_reset_tokens` and
`email_confirmation_tokens` (the short-lived password-auth experiment).

### 3.3 How the tables relate to each other, in plain words

Unchanged from the first pass — see the original relationship list (users → household
members → folios → transactions; imports → transactions; schemes → their own
price/fee/size/score history). The three new tables above hang off `users` and
`household_members` the same way everything else does — `analytics_sections` and
`analytics_recompute_status` by `user_id`, `account_deletion_surveys` deliberately by
nothing at all (see above).

### 3.4 Migration history, in plain words (0001 → 0014) **[0012–0014 are new]**

*(0001 through 0011 — the initial schema, the transaction-dedupe fix, CAS import
lifecycle/coverage gaps, the multi-method-auth redesign, the phone-identity backfill,
password auth added-then-removed, the expense-ratio NULL-handling fix, catching the
database enums up to the code, and enforcing one "self" row per user — are unchanged
from the first pass; see that section's detail if needed.)*

12. **Analytics precompute tables** — added `analytics_sections` (one row per computed
    analytics section per user/scope) and `analytics_recompute_status` (tracks whether a
    background recompute is currently running for a user). This is the schema
    underpinning the architecture change in §6. (Note: this migration's Create Date
    predates 0013/0014, but it was renumbered from an original `0010` to `0012` during a
    branch merge, since another branch's work had already claimed 0010/0011 — a
    bookkeeping detail, not a sign of things being out of order.)
13. **Account deletion grace period** — added `pending_deletion` (boolean) and
    `deletion_scheduled_at` (timestamp) to `users`, plus the new
    `account_deletion_surveys` table. This is what powers the new "delete my account"
    flow — see §9.2.
14. **Analytics recompute "generation" counter** — added a single integer column
    (`generation`) to `analytics_recompute_status`. This is a safety mechanism: it lets
    the system detect "the data underneath this in-progress background computation just
    changed (e.g. someone deleted an import, or the account itself is being deleted)"
    and abandon that computation instead of writing stale results — see §6.

**Style note:** unlike most earlier migrations, these three don't need any of the old
SQLite-vs-Postgres branching logic (no enums, no partition-aware constraints) — they're
plain, portable table/column additions. The dialect-specific complexity for this feature
moved into the application code instead (see §3.6).

### 3.5 The account-deletion data flow, in plain words

A user can now ask to delete their account. Doing so doesn't delete anything
immediately — it sets a flag and a future date (5 days out) on their `users` row, and
records an anonymous "why are you leaving" survey answer completely separately (so that
feedback survives even after the account itself is gone). The user can undo this any
time before that date. A daily background job checks for anyone whose 5 days are up and,
for each one, **permanently deletes everything** — their transactions, imports,
snapshots, precomputed analytics, folios, sessions, login methods, household members, and
finally the account itself, in an order that respects the foreign keys described in §3.1.
Full detail on this flow is in §9.2.

### 3.6 SQLite vs. Postgres — real differences to know about

Unchanged from the first pass: `transactions`/`nav_history` are partitioned by year on
Postgres only; enum-like status fields are database-enforced on Postgres but free-form
text on SQLite; Postgres enum values can never be cheaply removed once added (a
permanent, accepted cost); foreign-key enforcement is on by default on Postgres but not
turned on anywhere in this codebase for SQLite. **New in this pass:** the analytics
precompute feature's "insert or update" logic (used when writing a freshly-computed
section, or bumping the generation counter) has to be written two different ways for the
two databases — SQLite and Postgres have different SQL syntax for "insert this row, but
if it already exists, update it instead" — so that specific piece of application code
(not the schema itself) branches on which database it's talking to.

---

## 4. The CAS import pipeline (the core "upload your statement" feature)

Unchanged from the first pass in its core mechanics (two parallel backends with only one
reachable by users; parse → match → preview → confirm → attribute → save-without-
duplicating → background price refresh; coverage-gap detection and opening-balance
patching; the attribution safety gate; non-PAN duplicate-person detection). See §9.3 for
a genuinely new capability added on top of this pipeline since the first pass: viewing
import history and deleting a past import.

---

## 5. The main holdings dashboard

Unchanged from the first pass in its core mechanics (FIFO lot accounting for holdings/
value/gains; allocation, cash flow, SIP tracking, distributor comparison, snapshots; live
computation with a short invalidate-on-import cache; the F8 fix for funds whose price
can't be fetched, with the known Distributor Comparison sibling gap still open). See §9.4
and §9.5 for two genuinely new pieces added since the first pass: a portfolio-wide XIRR
figure on the main dashboard header, and a drill-down view into allocation buckets.

---

## 6. The analytics engine — now a precompute/cache architecture, not live-per-request **[MAJOR UPDATE]**

This section replaces the first pass's description almost entirely. **The underlying
finance math has not changed at all** — XIRR, the two risk metrics (downside deviation
and the rolling-12-month consistency score), the fund Scorer's weighting, category
ranking, benchmark comparison, and TER/AAUM logic are all bit-for-bit identical to what
was audited before, calling the exact same functions as before. **What changed is only
where and when that math runs.**

### 6.1 Why this changed

Rapid tab-switching on the Analytics dashboard used to fire up to 7 concurrent
live-compute requests at once, on top of already-abandoned ones the backend never
noticed had been cancelled by the browser. Some of these (the peer-category compute
behind category ranking and the Scorer) took multiple minutes of uncached price-fetching
and database writes. This was bad enough to exhaust the database's connection pool
entirely — once that happened, even the one screen someone was actually looking at would
fail. The team's fix was a genuine architecture change, not a quick patch.

### 6.2 The new read path

There is now essentially one analytics read endpoint: `GET /analytics/{scope}`, where
`scope` is either `"combined"` (the whole household) or one specific family member.
Opening the analytics dashboard is now just a lookup against a table of already-computed
results (`analytics_sections`) — **no live computation ever happens on this path.** The
frontend polls this endpoint every few seconds and stops once every section has either
landed or permanently failed.

### 6.3 The new write path

A separate background process — a short-lived AWS ECS Fargate task, not the same process
serving user requests — is the only thing that ever actually computes and writes
analytics data. It's triggered by any of: a CAS import being confirmed, a user opening
the dashboard for the very first time with nothing precomputed yet, an explicit "retry"
button after a permanent failure, or a daily scheduled backstop that sweeps every
household. This is the actual fix for the original bug: because computation now happens
in its own short-lived process, it can never contend with — or exhaust the connection
pool for — a real user's live request.

Two separate safety mechanisms prevent this background process from doing the wrong
thing:
- A **time-based claim**: only one recompute can be "in flight" for a household at a
  time; if one is ever killed uncleanly, it's automatically treated as abandoned after 2
  hours so a new one can start.
- A **generation counter** (the new database column from migration 0014): if a user's
  underlying data changes while a recompute is still running for them — say, they delete
  an import, or their account itself gets permanently deleted — the counter is bumped
  immediately as part of that same change. The in-progress recompute checks this counter
  before writing each piece of its results and, if it's changed, abandons the rest of its
  work rather than overwriting good data with results computed from a now-outdated
  snapshot. In plain terms: it stops "stale" background work from clobbering the truth.

### 6.4 Current `/analytics/*` endpoints

Down from roughly 19 endpoints (one live-computed route per section, per household
scope) to 5:
- `GET /analytics/funds/{scheme_id}/score` — the one thing still computed live on
  request, deliberately, since it's a lookup for a single specific fund rather than a
  whole household's worth of sections.
- `GET /analytics/{scope}` — the consolidated precomputed read described above.
- `POST /analytics/{scope}/retry` — manually re-triggers a recompute for a household
  whose data permanently failed to compute.
- `POST /analytics/export/pdf` and `GET /analytics/export/payload/{token}` — unchanged
  PDF export machinery from before.

### 6.5 The 4 background data-refresh scripts (F4) — still true, plus a 5th

Unchanged from the first pass: 4 scripts refresh prices, fees, fund sizes, and benchmark
index levels on a schedule rather than fetching them live. A 5th scheduled job has now
been added specifically for this new architecture — a daily backstop that recomputes
analytics for every household, as a safety net in case the event-driven triggers above
are ever missed for someone.

### 6.6 Deployment status of this specific feature **[the gap]**

The code is fully built, merged, and reviewed (4 rounds of adversarial review, PASS, zero
findings for the core work; the frontend migration off the old per-section routes is
also independently verified). **But it cannot work end-to-end in staging yet**, because
the database tables it depends on (`analytics_sections`, `analytics_recompute_status`,
and the generation column) live in migrations `0012`–`0014`, which have not been applied
to the real staging database — still on `0011` as of the last confirmed check. The
Terraform for the new background-recompute ECS task and its 5th scheduled job are also
authored but not yet applied. Until both of those steps happen, this architecture is
"merged but not deployed," not "live."

---

## 7. Authentication

Unchanged from the first pass in its core mechanics (no passwords; phone/email/Google
login with phone mandatory; the identity-linking and collision rules; sessions;
security posture including the real limitation that email delivery has no live provider
wired up yet). See §9.1 and §9.2 below for two genuinely new pieces added on top of this
system: changing your phone/email on an existing account, and the account-deletion flow
itself (which is implemented as an authentication-layer feature, gating what a
"pending deletion" account is even allowed to do while it waits out its grace period).

---

## 8. The investor-beta feature batch (shipped 2026-09-11) **[NEW SECTION]**

Six new pieces of user-facing functionality landed together. All are implemented with
real backend endpoints, database changes, and frontend UI, and the full test suites pass
(649 backend / 437 frontend). **The important caveat, repeated from §1: the last two of
three implementation rounds for this batch — including the concurrency-sensitive
generation-counter fix and the OTP-cleanup-on-deletion fix — were never independently
adversarial-reviewed, and two new Postgres-specific tests covering the actual
account-hard-delete path have never been run against a real Postgres database.**
Recommend treating this batch as "implemented, partially reviewed" rather than fully
signed off until those two things happen.

### 8.1 Profile

A new screen (reached via a profile icon in the dashboard header) that brings together:
account info (name, email, phone, with a "Change" action on email/phone — see §8.3),
theme toggle, import history (§8.3 below), a relocated Logout button (moved here from
the header, not duplicated), and a clearly-separated "Danger Zone" containing account
deletion, placed last.

### 8.2 Account deletion (with a 5-day grace period)

1. **Exit survey** — the user picks a reason (not using it enough, missing a feature,
   found an alternative, a data/trust concern, or other) and can add free-text feedback.
   This is saved completely anonymously (§3.2).
2. **Scheduling** — the account is flagged `pending_deletion` with a deletion date 5
   days out. Nothing is deleted yet.
3. **While pending:** the user can still log in, but is locked to a single "your account
   will be deleted on [date] — reactivate?" screen and nothing else. This is enforced on
   the backend (not just hidden in the frontend) — a dedicated check now guards nearly
   every authenticated endpoint and rejects requests from a pending-deletion account,
   with a small, deliberate allow-list (viewing your own profile, reactivating, logging
   out) that must keep working during the grace period. **This server-side enforcement
   was itself a fix for a real gap found in review** — the very first version only
   blocked things in the frontend, so a second open browser tab or a direct API call
   could bypass it entirely.
4. **Reactivate** — one endpoint clears the flag and date, fully undoing the request, no
   side effects, any time before the 5 days are up.
5. **What actually happens when the 5 days pass:** a daily background job finds every
   account past its deletion date and performs a genuine, permanent hard delete — every
   transaction, import, snapshot, precomputed analytics row, folio, session, login
   method, and household member, in a carefully ordered sequence, ending with the account
   itself. This is not a soft-delete or an anonymization — the data is actually removed.
   Only the anonymous exit-survey response from step 1 survives, by design.

*(One thing worth a founder-level sanity check, flagged by the audit rather than
confirmed broken: the spec calls for the **whole household** to be deleted together if
the deleted account is the "self"/primary one. The code sets the deletion flag on just
the one `User` row being deleted; this only correctly cascades to the rest of the
household automatically if a "household" in this schema is always exactly one `User`
account with multiple family members underneath it — which appears to be how the schema
is designed, but is worth verifying with a real second account in the same household
before fully trusting this.)*

### 8.3 Changing your phone number or email on an existing account

Reuses the exact same one-time-code system already used for login — no new OTP
mechanism was built. The flow: request a code to be sent to the **new** phone/email
(never the old one), enter it, and only once that code is verified does the account's
phone/email actually change — there's no way to edit it without proving you control the
new value first. The system also checks the new value isn't already claimed by a
different account before sending the code, and again at the moment of verifying (closing
a narrow race-condition window between the two checks).

### 8.4 Import history (and a new "delete this import" capability)

A user can now see a list of every past CAS import — when it was uploaded, what date
range it covered, its status, and how many new transactions it added. New, and more
significant: **a user can now delete a past import entirely.** Doing so removes every
transaction that came from it, cleans up any folio that's left with zero transactions as
a result, and re-checks any folio that still has some (so a partially-emptied folio
doesn't keep a stale "there's a gap in this fund's history" warning). It also clears that
user's precomputed analytics, which then automatically recompute on the next visit —
**worth knowing for support purposes:** the main holdings dashboard reflects a deleted
import immediately, but the analytics dashboard will show a "recomputing" state for
somewhere between several seconds and a couple of minutes afterward, which is expected
behavior given the architecture in §6, not a bug.

### 8.5 A new XIRR figure on the main holdings dashboard

Previously, XIRR (the "what annual return am I really getting" metric) only appeared on
the separate Analytics dashboard. It's now also shown directly on the main Holdings
dashboard header, reusing the exact same underlying calculation, with a toggle between
two views: **Lifetime** (every transaction ever, including funds you've since fully sold
out of) and **Current Holdings** (only funds you still hold today). Because this only
needs a household's own transactions and current value — no external peer/benchmark data
— it's still computed live, in-request, unlike the analytics-dashboard version.

### 8.6 Allocation drill-down

Two smaller improvements to the existing Allocation view: the asset-class and fund-house
breakdowns are now explicitly sorted largest-to-smallest (with a toggle to flip it),
fixing what used to be arbitrary ordering that happened to often look sorted; and
clicking into any one asset class or fund house now opens a detail view listing every
individual fund inside that bucket (units held, average price, current value, plus a
running subtotal) — previously that detail was only visible as one aggregated slice of a
chart, not broken out per fund.

---

## 9. Open items and known limitations, as of 2026-09-16 **[UPDATED]**

**Deployment gaps (new, most actionable):**
- No frontend deployed anywhere — no usable staging link exists yet (§2).
- Domain/HTTPS Terraform authored but not applied — no `staging.unifolio.in` yet (§2).
- Staging RDS schema is 3 migrations behind the code (§2, §3.4).
- The deployed backend image predates the analytics rework and the entire investor-beta
  batch — a redeploy is needed even once the above is fixed (§2).
- The new analytics-recompute scheduler job and its ECS task role are authored but not
  applied (§2, §6.6).
- `feat/enhanced-ui` hasn't been promoted to `main`/`production` yet (§2).

**Review-gate gaps (new, worth closing before trusting this code fully):**
- The last two of three implementation rounds behind the investor-beta batch were never
  independently adversarial-reviewed, despite touching concurrency- and
  security-adjacent logic (§1, §8).
- Two new Postgres-specific cascade-delete tests (covering the real account-hard-delete
  path) have never actually run against a real Postgres database (§8.2).
- A household-wide deletion cascade (deleting every member of a household together, not
  just the requesting account) hasn't been independently confirmed with a real
  multi-account household (§8.2).

**Carried over from the first audit pass, still true:**
- A dead field reference in one frontend table component (harmless, documented).
- An unbounded database scan in the category-ranking analytics code — deferred until a
  real Postgres environment exists to properly test the fix against.
- A minor accessibility gap on one tab switcher (accepted, documented).
- The Distributor Comparison view can still silently drop a holding with a missing price
  (the sibling of the F8 fix, deliberately left for later).
- The newer CAS import backend is fully built but has no way for users to reach it yet.
- Several product features are intentionally not built and are not gaps: MFCentral/
  Account Aggregator import, stock/demat holdings tracking, cap-wise fund composition and
  stock-overlap detection, and broader auth hardening (rate-limiting, account lockout).

---

*Sources: direct reads of `backend/app/models/`, `backend/alembic/versions/0001`–`0014`,
`backend/app/api/`, `backend/app/services/` (auth, import_, dashboard, analytics),
`backend/scripts/jobs/`, `infra/` (all Terraform modules and the staging environment),
`session.md`, `DEFERRED_FEATURES.md`, `Docs/orchestration/*-handoff.md`,
`Docs/superpowers/plans/2026-09-11-aws-staging-prerequisites.md`, and
`Docs/superpowers/specs/2026-09-02-analytics-precompute-architecture-design.md`, plus
live AWS verification evidence (ALB health checks, CloudWatch logs, a real OTP
round-trip) cited in `session.md`'s 2026-09-09 entry — current as of 2026-09-16.*
