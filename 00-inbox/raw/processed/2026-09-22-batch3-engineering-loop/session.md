# Session state — 2026-09-12 (updated)

Working notes for picking this project back up cold. Not a planning doc — see
`Docs/superpowers/plans/` for those. This file tracks *where things stand*,
gets overwritten each session, and isn't meant to accumulate history.

**Read this file, then `CLAUDE.md`'s Session State section, before re-deriving
anything by re-reading the whole repo.**

## Latest Session (2026-09-12): Fund Score card redesign implemented via subagent-driven-development, all 9 tasks + full-suite verification clean

The Fund Score card redesign (spec `Docs/superpowers/specs/2026-09-11-fund-score-card-redesign-design.md`,
plan `Docs/superpowers/plans/2026-09-11-fund-score-card-redesign.md`) is implemented:
score out of 10 (display-only, backend still returns/stores the raw 0-100 value),
reversed 1=best tier display convention everywhere it's shown, plain-English
Strengths/Watch-outs verdicts replacing raw percentiles, a "why" sentence and a closing
"what this means for you" suitability sentence, expandable "See the evidence" and "How
we calculate this score" sections, and the "Transparent Methodology Commitment" box
moved to the bottom. Executed as 9 tasks via `superpowers:subagent-driven-development`
entirely in this session (no Codex) — full ledger at
`.superpowers/sdd/2026-09-11-fund-score-card-redesign/progress.md`. Two escaped-defect/
plan-gap fixes were needed along the way (Task 2's `FundScoreRow` fields lacked
Pydantic defaults, breaking an unplanned test fixture; two other unplanned consumer
test files — `AnalyticsView.test.tsx`, `PrintAnalyticsView.test.tsx` — needed the new
fields added, and `PrintAnalyticsView.test.tsx` separately needed its stale raw-score
assertion updated to the new `/10` format after Task 6 landed), all fixed directly as
controller and logged as rulings. One cosmetic, non-blocking issue is flagged, not
fixed: the approved spec's own middle-tier "why" sentence template double-states
"weaker" (design doc line 221) — present in the spec before this work started, purely
copy, no functional impact.

Full suites re-run clean after the last fix: backend 650 passed/8 skipped, frontend
454 passed across 80 files, `tsc -b --noEmit` clean.

**Final whole-branch review (opus) completed and adjudicated.** 1 Critical + 5
Important + 9 Minor findings. Fixed directly as controller: Critical #1 (stale
precompute-cache rows missing new fields entirely, not null — `=== null` checks
didn't catch `undefined`; switched to loose equality, marked the 6 new
`FundScoreRow` fields optional), Important #2 (PDF export's `printMode` prop
so evidence/methodology accordions render open in the print view, matching
the existing `AllocationSection`/`BenchmarkSection` convention), Important #5
(missing `aria-expanded`/`aria-controls` on the accordion buttons). A scoped
re-review of that fix commit caught a new bug the aria-controls fix itself
introduced — duplicate accordion panel ids across multiple `FundScoreCard`s
on one page — fixed by keying the id off `data.scheme_id`. Important #3
(5-segment tier progress bar dropped, not flipped) and #4 (computed verdict
word never rendered) were real spec-vs-plan deviations (the plan's own Task 6
JSX silently omitted both) — flagged to the user per CLAUDE.md rather than
silently resolved either way. **User chose to restore both**, and also asked
to fix the previously-flagged "weaker weaker" duplicate-word copy bug in
`fundScoreVerdicts.ts`'s middle-tier why-sentence (present in the spec's own
pseudocode, not just the implementation). All three fixed; full ledger detail
in `.superpowers/sdd/2026-09-11-fund-score-card-redesign/progress.md`'s
"Post-review fix round" section.

**Still pending, deferred to the AWS/deployment phase per spec §8:** the
precompute-cache backfill (a manual analytics-recompute re-run) needed so already-cached
score summaries reflect the new raw-evidence fields — not done this session, since it
requires the real ADR-006 ECS infra this repo doesn't have running yet.

**Not yet done:** Step 4's manual browser smoke check (no browser tool in this
environment — flagged as human-only, not fabricated as passed).

## Previous Session (2026-09-11): Investor 10-item feature batch complete, committed; AWS staging prerequisites doc drafted

Three small commits landed on `feat/enhanced-ui` first (pre-existing, unrelated to
today's main thread): `83a3749` hides the Google sign-in button when no OAuth client id
is configured, `b972e65` migrates the frontend off the 14 deleted per-section analytics
routes onto the consolidated precompute contract, `20a825e` wires the analytics-recompute
dispatcher to real ADR-006 ECS infra (Terraform authored, not yet applied).

The investor-requested 10-item feature batch (Profile page, account deletion with a
5-day grace period + exit survey + household cascade, email/phone change via OTP, theme
toggle in Profile, import history + delete-import, Dashboard header XIRR, allocation
sort toggle, AMC/asset-class drill-down modal, decimal-formatting consistency fix — full
spec `Docs/orchestration/investor-beta-feature-batch-handoff.md`) went through 3 rounds
of implementation + adversarial review (Round 1 → 8 Round-2 findings → 5 Round-3
findings) and a same-session PM/tech-lead gap-analysis pass (3 more fixes: XIRR
popover replaced with a Lifetime/Current toggle, a subtotal added to the AMC/asset
drill-down modal, real-Postgres cascade-delete test coverage added). Round-3 fixes and
the PM-gap fixes were both implemented directly by the orchestrator rather than Codex
(Codex usage-limited both times) — per the model-orchestration skill's fix-authorship
rule this is allowed for small/isolated diffs, but the mandatory adversarial-review gate
for both rounds is **deferred, not run** this session (user explicitly deprioritized
running it today in favor of moving straight to AWS execution planning — this is a real,
open gap to flag, not a completed review). Full detail on every round: `Docs/orchestration/
delegation-log.md`'s `round-3-adversarial-review-fixes` and `pm-gap-analysis-fixes`
entries.

Before committing, both full suites were re-run fresh from a clean shell (not trusted
from any prior self-report in this session or an earlier one): backend 649 passed/8
skipped, frontend 437 passed across 79 files, `npx tsc -b --noEmit` clean. Cross-checked
every one of the 10 batch items plus Round 2/3's fixes directly against the actual code
(not the handoff doc's claims) before treating them as real — all present. One
environment artifact hit and worked around, not fixed: a stale `backend/.pytest_tmp`
directory (`pytest.ini`'s configured `--basetemp`) was left in an unremovable
permission state by an earlier interrupted run on this WSL/drvfs mount — `chmod`, `rm`,
Windows-side `cmd.exe`/PowerShell `icacls` all independently denied removal. Worked
around via `pytest --basetemp=<scratch-dir>` on the CLI; the directory itself is still
sitting there unremoved, harmless as long as that flag is used for any future run in
this environment.

Everything above (the entire investor batch — it had never been committed before this
session, all 79 changed/new files sitting in the working tree since it was implemented)
committed to `feat/enhanced-ui`. See `git log` for the exact commit(s)/message(s) rather
than duplicating them here, since this section predates the actual commit step in this
session's own timeline — check `git log --oneline -10` first if picking this up.

AWS staging prerequisites/runbook doc drafted: `Docs/superpowers/plans/
2026-09-11-aws-staging-prerequisites.md`. Covers: current live-AWS state, the 3-migration
alembic drift (`0012`-`0014` authored, not yet applied to real RDS — RDS is still at
`0011`), two Terraform modules with real unapplied diffs (`infra/modules/backend`'s
dispatcher task def/role, `infra/modules/scheduler`'s 2 new jobs beyond the 4 already
live), the Docker Desktop WSL-integration prerequisite to re-verify before rebuilding the
backend image, and a full command-by-command runbook (alembic via bastion tunnel, image
build/push, `terraform apply` for backend+scheduler+Phase 4+Phase 5, ECS force-deploy,
frontend rebuild/S3/CloudFront invalidation, smoke test). Every command in it is
explicitly for the user to run themselves — no AWS/Terraform/Docker command has been
executed by Claude in this repo at any point.

## Previous Session (2026-09-10): Analytics frontend precompute migration complete

The Analytics dashboard frontend migration is implemented for both consumers: desktop
`frontend/src/features/analytics/AnalyticsView.tsx` and mobile
`frontend/src/mobile/features/analytics/MobileAnalyticsView.tsx`. Both now reuse the
single `useAnalyticsScope` hook, consume `GET /analytics/{scope}`, poll the backend's
cold-start/recompute state, and expose whole-scope retry UI for permanently failed
sections. The previous broken-build/404 gap from the deleted 14 per-section analytics
client functions is resolved. Verification: `npx tsc -b --noEmit` clean; full frontend
suite 76 files / 412 tests passing. Implementation plan and exact contract:
`Docs/superpowers/plans/2026-09-10-analytics-frontend-precompute-migration.md`.
Manual backend smoke testing and the orchestrator-owned adversarial review remain
outside this implementation session, per the corrected handoff prompt.

## Previous Session (2026-09-09): Terraform Phases 1-3 applied to real AWS — staging infra now live

Following the previous session's Phase 1-3 Terraform authoring (networking, security,
database, ecr, backend modules — all already reviewed/committed), this session walked
Ayush end-to-end through applying that code against a real AWS account for the first
time, entirely from his own WSL terminal (Claude never runs `terraform apply` or any
other AWS-state-mutating command — only the user does, per this project's established
division of labor for irreversible/billable actions):

- Installed AWS CLI v2, ran `aws configure` (IAM user `ayush-admim`, account
  `811364789032`, region `ap-south-1`), installed Terraform 1.16.1 pinned to match the
  repo's `.terraform.lock.hcl` files.
- Ran `infra/bootstrap/create-state-backend.sh 811364789032` — created the S3 state
  bucket `unifolio-tfstate-staging-811364789032` and DynamoDB lock table
  `unifolio-tfstate-lock-staging` (both confirmed via `aws dynamodb describe-table`, not
  just assumed from a truncated/paginated terminal paste — the first status check looked
  ambiguous only because AWS CLI's default `less` pager cut off the JSON mid-way, not
  because anything actually failed).
- Edited `infra/envs/staging/backend.tf`'s placeholder bucket name to the real value.
- `terraform init` (migrated to the S3 backend) → `terraform plan -out=tfplan` (57 to
  add, 0 to change, 0 to destroy — reviewed against the already-verified module wiring
  before giving go-ahead) → `terraform apply "tfplan"`, which succeeded: **57 resources
  created, 0 changed, 0 destroyed.**

**Now live in `ap-south-1` (real, billable AWS resources as of this session):**
- VPC `vpc-0570cc60e505184ed` + full subnet/routing/security-group layout.
- fck-nat instance (`i-0681a3cd783bcc695`) and SSM-only bastion (`i-0b67d40d9b58b7814`),
  both `t4g.nano`.
- KMS CMK `alias/unifolio-staging-cmk` for RDS/Secrets Manager encryption.
- RDS PostgreSQL 16 instance, `staging-rds.ctu88scmut9m.ap-south-1.rds.amazonaws.com:5432`,
  `skip_final_snapshot=true`/`deletion_protection=false` (correct for staging).
- ECR repo `unifolio-staging-backend` (currently empty — no image pushed yet).
- ECS cluster `unifolio-staging` + service `unifolio-staging-backend`, ALB at
  `unifolio-staging-alb-958627457.ap-south-1.elb.amazonaws.com`.

**Two known, expected (not bugs) follow-ups before this environment is actually usable — both RESOLVED same session:**
1. **RESOLVED.** The ECS service was crash-looping (`CannotPullContainerError`) because
   the ECR repo had no image yet. Fixed end-to-end from the local WSL machine (evaluated
   and rejected an EC2-build-server alternative — redundant with the existing CI/ECR
   path per `AWS Readiness/aws-golive-readiness-report.md` §3, and ECS Fargate defaults
   to X86_64 which matches a local Docker Desktop build with no extra config needed):
   `docker build` → `aws ecr get-login-password | docker login` → `docker tag` →
   `docker push` → `aws ecs update-service --force-new-deployment`. One real blocker hit
   and fixed mid-task: a stale `backend/.pytest_tmp` artifact directory (broken
   permissions, `d--x--x--x`, left over from an interrupted test run) made Docker's
   BuildKit context-transfer walker fail with `error from sender: failed to xattr
   .pytest_tmp: permission denied` even though the path was already listed in
   `.dockerignore` — BuildKit still has to stat/xattr every path during its initial
   context walk regardless of ignore patterns. Plain `chmod`/`rm -rf` as the owning user
   failed too (`permission denied`) because `backend/` lives on `/mnt/d`, a 9p/drvfs
   mount of the Windows `D:` drive — the Linux permission bits there are emulated by the
   9p client and can reject even the "owning" uid's own chmod. `sudo rm -rf` (bypasses
   the 9p client-side check) removed it, after which the build/push/redeploy succeeded
   cleanly. **Verified with 4 independent checks, not just the one `/health` curl**
   (`/health` is a pure liveness stub — no DB call — so it alone doesn't prove much):
   (1) ALB target-group health via `aws elbv2 describe-target-health` → `healthy`;
   (2) `aws logs tail /ecs/staging-backend` → clean continuous `/health 200 OK`s, and
   the *old* task's shutdown sequence in the logs confirms it was a deliberate drain,
   not a crash; (3) a real DB write through the ECS task's own network path (not the
   bastion path used for the migration) via `POST /auth/email-otp/request` (safe in
   staging — `OTP_DELIVERY_MODE=stub` returns the OTP in the response instead of
   emailing) → `{"message":"OTP sent.","otp":"..."}`, proving ALB → ECS task → its own
   security group → RDS → back all work; (4) `aws ecs describe-tasks` → `RUNNING`, no
   `stoppedReason`, `startedAt` unchanged since boot — confirms stability, not a lucky
   snapshot.
2. **RESOLVED.** The database schema didn't exist yet. Fixed via an SSM
   Session Manager port-forward through the bastion (`aws ssm start-session
   --document-name AWS-StartPortForwardingSessionToRemoteHost`, local port 5433 ->
   RDS's 5432), fetching the Terraform-generated master password from Secrets Manager,
   and running `alembic upgrade head` from the local `.venv` against the tunnel.
   `alembic current` confirms `0011 (head)` on the real RDS instance — all 11 migrations
   applied cleanly. **One real bug hit and fixed mid-task, worth remembering**: the
   fetched password (`[REDACTED — literal value contained shell metacharacters, redacted
   2026-09-23 before this raw evidence file was committed to this vault's git history;
   the credential was confirmed live/unrotated at redaction time, see R-057]`) contains a literal `$R` and `$5` —
   embedding it directly inside a double-quoted `python3 -c "..."` string let bash
   variable-expand `$R`/`$5` to empty before Python ever saw it, silently corrupting the
   password and producing a confusing `password authentication failed` further down the
   stack. Fixed by piping the secret through `python3 -c` reading from `os.environ`
   instead of a literal string, so bash never re-parses `$` inside it — general lesson:
   never place a real secret value literally inside a double-quoted shell string, always
   route it through a variable/env-var/stdin instead.

**Security note — resolved 2026-09-09:** a real AWS IAM access key/secret for
`ayush-admim` was pasted into this chat conversation in plaintext during `aws configure`,
and the access key ID was also (accidentally) committed in this file's own text at one
point. GitHub's push protection caught the committed copy and blocked the push. The key
has been rotated (deactivated in IAM console, fresh key generated, `aws configure`
re-run) and the offending commit rewritten via `git rebase -i` to remove the literal
value before it was ever pushed — no shared history was affected since the commit had
not left this machine. Lesson: never write a real credential value into any tracked
file, even in a "note to self" — redact to `<redacted>` or reference the IAM user/key
name only.

**Staging backend is now fully live and verified end-to-end** (image built/pushed, ECS
service healthy, DB schema migrated).

**Phase 4 (frontend S3+CloudFront) — Terraform authored, reviewed, DONE; not yet
applied.** Dispatched to Codex via `Docs/orchestration/aws-phase4-frontend-deployment-
handoff.md`/`-implementation-prompt.md` (user-run, per established pattern). Codex built
`infra/modules/frontend` (private S3 + CloudFront with OAC, both 403 and 404 mapped to
`/index.html` for SPA routing, no domain/ACM yet — deliberately deferred to Phase 5).
Independently reviewed against the handoff doc line by line — zero findings, `terraform
fmt`/`validate` clean. Handoff doc Status moved to `DONE`. **Ayush still needs to run
`terraform apply` himself** — a stray `infra/envs/staging/tfplan` from his own `plan`
run was found in the working tree during review (not committed, flagged back to him).

**Phase 5 (ACM/Route 53/ALB HTTPS/CloudFront domain) — Terraform handoff doc + prompt
drafted, not yet dispatched.** `Docs/orchestration/aws-phase5-networking-domains-
handoff.md`/`-implementation-prompt.md` written this session: two ACM certs (`us-east-1`
for CloudFront, `ap-south-1` for the ALB), Route 53 alias records against the existing
`unifolio.in` zone, an HTTPS listener + HTTP→HTTPS redirect on the live ALB, and in-place
`aliases`/`viewer_certificate` updates to Phase 4's CloudFront distribution. Explicitly
gated on Phase 4 being *applied* first (not just authored) — don't dispatch to Codex
until then.

**Not yet started:** Phase 6 (validation), Phase 7 (hardening/CI-CD). Once both Phase 4
and Phase 5 are applied, the frontend still needs a manual rebuild pointed at
`https://staging-api.unifolio.in` + upload to the Phase 4 S3 bucket + CloudFront
invalidation before real functional testing can start — none of that is Terraform's job,
see the phase docs' "Constraints" sections.

## Previous Session (2026-09-07): AWS account + domain cutover, doc cleanup, pre-Terraform verification

**AWS account and domain, done this session:**
- AWS account created (root MFA via authenticator app, a $50 monthly budget alert,
  IAM admin user `ayush-admim` with `AdministratorAccess`, account alias
  `unifolio-aws-stagging`) — both names carry typos, cosmetic, fixable anytime via
  `aws iam update-user --new-user-name` / IAM Dashboard, not fixed yet.
- Region confirmed: `ap-south-1` (Mumbai).
- `unifolio.in` cut over from GoDaddy DNS to a Route 53 public hosted zone. Before
  switching nameservers, GoDaddy's existing 11 records were audited: the domain runs
  live Microsoft 365 mail (MX → `unifolio-in.mail.protection.outlook.com`, SPF, DMARC,
  `autodiscover` CNAME, an MS-verification TXT) — all preserved as new Route 53 records.
  Dropped deliberately: GoDaddy's own NS/SOA (Route 53 generates its own), the
  `_domainconnect` CNAME (GoDaddy-proprietary quick-setup protocol, meaningless once DNS
  leaves GoDaddy), and the root `A` record (GoDaddy Website Builder's "Launching Soon"
  placeholder page — tied to GoDaddy's own builder backend, not a portable IP; stops
  working regardless of what's done with DNS, so nothing to preserve). Nameserver switch
  verified propagated via `dig`/`nslookup` against Google's `8.8.8.8` resolver.
- Domain/subdomain architecture decided: `unifolio.in` (apex) = marketing/overview site
  with Login/Sign Up CTAs; `app.unifolio.in` = production web app; `staging.unifolio.in`
  = staging web app (what all the AWS readiness work in this repo targets). Backend API's
  own domain (dedicated subdomain vs. path-based CloudFront routing) is still an open
  decision, needed before §22 Phase 5, not before Phase 0/1.
- Networking decision: staging uses **fck-nat** (a self-hosted EC2 NAT alternative)
  instead of a managed NAT Gateway, to avoid the NAT Gateway cost-approval step for a
  low-traffic staging environment. All of the above folded into
  `AWS Readiness/aws-golive-readiness-report.md` (§12 Option C, §19, §22 Phase 5).

**Documentation cleanup, done this session, before starting Terraform Phase 0/1** (the
user's own reasoning: infrastructure work is expensive to unwind once started, so verify
everything code-side is actually as documented first, not just as claimed):
- `CLAUDE.md`'s Session State section previously claimed 2026-09-03's F8/F4/non-PAN-dedup
  work was "still uncommitted in one large combined working-tree diff" — checked `git log`
  directly: it was already committed, as `9fe21fe`. Corrected.
- `AWS Readiness/aws-golive-launch-blockers.md` listed several items as open BLOCKERs
  that were actually already fixed in code (in commit `c7ba70a`, an earlier commit than
  `9fe21fe`): the Dockerfile, the Playwright/Chromium install step, CORS, `/imports/parse`
  upload validation, the OTP stub-mode environment-flag guard, and the
  ImportStatus/TransactionType enum-widening migration. Verified each directly against
  the actual source (not the doc, not a prior self-report) before marking resolved.
- Ran both full test suites fresh as the final check: backend 614 passed/6 skipped,
  frontend 397 passed (75 files), `tsc -b --noEmit` clean — matches prior self-reports
  exactly, confirms the code side is genuinely stable going into infra work.
- One environment artifact found and worked around (not a code bug): a stale
  `backend/.pytest_tmp` directory (pytest.ini's configured `--basetemp`) was left with
  broken permissions (`d--x--x--x`, likely from an interrupted test that deliberately
  creates a permission-denied fixture) from the 2026-09-03 session, blocking a plain
  `pytest` run with 32 unrelated-looking errors. Not a regression — bypassed via
  `pytest --basetemp=<scratch-dir>`; the directory itself still needs `sudo rm -rf` to
  actually remove, not done (no passwordless sudo in this environment).

**Not yet started:** actual Terraform Phase 0/1 module authoring — the cloud engineer
has suggested changes to the original plan, to be reviewed before drafting begins.

## Previous Session (2026-09-02): AWS staging prep — compliance-audit remediation, Group 1

Working through `AWS Readiness/sqlite-postgres-migration-compliance-audit.md`,
`aws-golive-launch-blockers.md`, and `aws-golive-readiness-report.md` to close every
pre-staging gap (any priority, as long as it isn't safely deferrable past staging) before
starting the AWS Terraform build. Two prior Codex-implemented pieces were independently
verified this session, not just trusted from self-report: `Docs/orchestration/staging-code-blockers-handoff.md`
(OTP stub-mode guard now keyed on `environment == "production"` not a SQLite-path sniff,
`Dockerfile`+`.dockerignore`+pinned `requirements.txt`, `_allowed_cors_origins` config-driven
CORS, `/imports/parse` upload validation) and `enum-drift-migration-handoff.md` (migration
`0010` widens the `importstatus` native enum and rebuilds the `transactions_type_check`
CHECK constraint to include `opening_balance`) — both confirmed correct via fresh test
runs, direct Postgres DDL inspection, and container boot checks. Both docs' own deviations
from their handoff instructions (0010 skipping a native `transactiontype` Postgres enum
that migration 0001 never actually created) were confirmed to be legitimate,
evidence-based corrections, not errors.

Remaining findings grouped into: **Group 1** (no product decision needed — done this
session, directly in Claude, without Codex, since Codex's usage limit was exhausted until
~7pm and the user didn't want to burn Claude's limits either while waiting):
- **F6**: `nav.py`'s `_upsert_nav_history` Postgres `ON CONFLICT DO NOTHING` branch had
  zero test coverage (only ever exercised on SQLite) — added
  `test_upsert_nav_history_is_conflict_safe_on_postgres` to
  `tests/functional_postgres/test_partitioning.py`, run and passing against the local
  Docker Postgres 16 container. Also did the audit's suggested small refactor: the
  per-call `if/elif` dialect branch in `_upsert_nav_history` is now a one-line
  `_NAV_UPSERT_INSERT_BUILDERS` dict lookup.
- **F9**: `amfi_aaum_client.py`'s `refresh_aaum_data` was the one remaining caller with a
  bare `db.commit()` inside an `async def`, not routed through `commit_off_loop` like
  every sibling analytics client — fixed. (Fixing this surfaced a real, previously-latent
  test bug: `tests/services/analytics/test_amfi_aaum_client.py`'s in-memory SQLite fixture
  didn't set `check_same_thread=False`/`StaticPool`, which every other `commit_off_loop`
  caller's test fixture already does — `commit_off_loop`'s `asyncio.to_thread` hop crashed
  against it. Fixed the fixture to match the established sibling pattern.)
- **F10**: `folios.coverage_gap_details` migration 0003 used raw `postgresql.JSONB()`
  while the ORM model uses the dialect-portable `sa.JSON().with_variant(postgresql.JSONB(),
  "postgresql")` — cosmetic-only (identical compiled DDL either way), but flagged as
  autogenerate-diff drift. Aligned the migration to the model's idiom; safe to edit
  directly since no real deployment has ever run this migration against a live DB.
- **F5**: `Docs/PRDs/Database-Schema-Unifolio.md` was stale by migrations 0003 and
  0007-0010 — refreshed to v1.4: `imports.status`'s full 14-value lifecycle enum and its
  6 undocumented columns, `folios.has_coverage_gap`/`coverage_gap_details`,
  `transactions.type`'s `opening_balance` value (and the note that this column is
  `VARCHAR`+CHECK on Postgres, never a native enum), `scheme_ter.ter_value`'s nullable
  "checked, no match" meaning, `auth_identities`/`pending_identity_verifications`'s dropped
  `password_hash`/`email_confirmed_at`, and full removal of the now-dropped
  `password_reset_tokens`/`email_confirmation_tokens` tables.
- Full non-Postgres test suite (584 tests) and the Postgres-marked subset (now 4 tests,
  including the new F6 one) both green after all Group 1 changes.

**Also done this session, outside Group 1 (user explicitly authorized each, overriding
the initial recommendation to defer):**
- **F7**: `compute_holdings`'s per-folio `Transaction` N+1 query, batched into one query
  across all folios. See "Still open" list item 6 below for full detail.
- **F3**: `household_members` had no uniqueness enforcement on its "self" row — read-only
  violation check first (zero existing violations), then migration `0011` (partial unique
  index) plus a `DuplicateSelfMemberError` → 409 application guard. See "Still open" list
  item 2 below for full detail.

**Handoff docs written and dispatched to the user's own Codex session 2026-09-02** (all
open product/scope questions for F4, F8, and the non-PAN dedup idea were resolved by the
user in one message this session — see "Still open" list items 1, 2, and 8 below for full
detail on each):
- `Docs/orchestration/adr006-background-jobs-handoff.md` (F4, piece 1 only — the 4 job
  entrypoint scripts; the actual EventBridge/ECS Terraform is explicitly deferred to the
  infra-authoring phase).
- `Docs/orchestration/f8-nav-unavailable-degraded-row-handoff.md` (F8 — degraded row +
  `nav_unavailable` flag, per user's confirmed "(b)" choice).
- `Docs/orchestration/non-pan-duplicate-person-detection-handoff.md` (the PAN idea's
  non-PAN replacement — see item 2's sub-paragraph below for the design).

**Single-ECS-task / Redis deferral, documented not silently dropped (2026-09-02):** user
confirmed they do NOT want the full Redis-backed cache rewrite built now, even for
staging — the operational mitigation (`desiredCount=1`, no autoscaling, stop-then-start
deploys — an ECS Terraform parameter, not code) is fine for now, but must stay tracked
rather than quietly disappear from the list, since it's genuinely multi-day work that may
come later. Full DECISION record (exact ECS parameters, revisit trigger): a new "DECISION
(2026-09-02)" paragraph in `AWS Readiness/aws-golive-launch-blockers.md`, immediately
after that doc's "Scale note" bullet in the "BLOCKER — The app can only safely run as
exactly one instance" section.

## Previous Session (2026-08-27)

1. **Login Roadmap State Logic & 2-Milestone Flow (`MobileAuthBackground.tsx`, `AuthEntryFlow.tsx`, `AuthShell.tsx`, `mobileJourneyContext.tsx`)**:
   - Fixed roadmap milestone state management: explicitly decoupled login progression from page switching, route changing, or Sign-up/Login toggles.
   - Starting at Step 1 (`x: 36, y: 38`), clicking "Log in" from the Sign-up page switches to Login mode while keeping the marker rock solid at Step 1 (Milestone 1).
   - Selecting "Continue with Email" or "Continue with Phone" and typing credentials keeps the marker firmly at Step 1.
   - Transitioning to the OTP verification screen (`email_otp` or `otp`) moves the marker smoothly along the curved route to Step 2 (`x: 340, y: 22`), triggering the milestone pop/lift effect and `#milestone-unlock-glow`.
   - After successful OTP verification, navigates directly to the dashboard without adding further roadmap steps.
   - Added unit tests in `MobileAuthBackground.test.tsx` and re-verified all 75 test suites (381 tests passing).

2. **Comprehensive Mobile Scrolling Fixes across all Mobile Screens**:
   - Resolved height/overflow trapping across all mobile screens where users were unable to scroll down to view options, inputs, or CTAs.
   - `MobileOnboardingScreen.tsx`: Replaced rigid `h-dvh max-h-dvh overflow-hidden` with `min-h-dvh overflow-x-hidden overflow-y-auto`, adjusted `<motion.main>` to `justify-start sm:justify-center`, scaled onboarding artwork responsively, and pinned `<motion.footer>` with `sticky bottom-0 backdrop-blur-sm z-30` so CTAs are always accessible.
   - `App.tsx` (`MobileInitialFlow`): Removed outer `h-dvh max-h-dvh` height barrier, establishing `min-h-dvh overflow-x-hidden overflow-y-auto`.
   - `MobileLandingPage.tsx`: Replaced `h-dvh max-h-dvh overflow-hidden` with `min-h-dvh overflow-x-hidden overflow-y-auto`.
   - `AuthShell.tsx`: Added `overflow-y-auto pb-28 lg:pb-5` on mobile to prevent form CTAs and inputs from colliding with or hiding behind the bottom mobile roadmap.
   - `MobileDistributorComparisonView.tsx`: Added `flex-1 min-h-0 overflow-y-auto pb-16` to ensure the list of distributors and scheme breakdowns scroll smoothly without being cut off.
   - `MobileReviewView.tsx`: Increased bottom clearance from `pb-20` to `pb-28 sm:pb-32` above the sticky bottom action bar.
   - `TrustPrimer.tsx`: Scaled custom illustration gracefully (`w-36 h-36 xs:w-44 xs:h-44 sm:w-56 sm:h-56`) on compact screens.

3. **Mobile & Web Import Screens Vertical Centering & Refinements**:
   - Vertically centered the Upload Screen (`UploadForm.tsx`, `MobileUploadForm.tsx`, `TwoPathImportContainer.tsx`).
   - Enlarged the hero illustration on the upload statement screen (`w-24 h-24 sm:w-28 sm:h-28`) and removed the PAN/DOB password hint line.
   - Vertically centered the CAS Processing Indicator Screen (`ParsingIndicator.tsx`, `ImportFlow.tsx`, `MobileImportView.tsx`).
   - Vertically centered the Import Complete Screen (`ImportConfirmed.tsx`, `ImportFlow.tsx`, `MobileImportView.tsx`).
   - Centered the "Import Choice" screen (`ImportPathChoice.tsx` & `TwoPathImportContainer.tsx`), keeping top "Import History" anchored while centering the illustration, title, and choice cards.

4. **Roadmap Milestone Sequential Activation & Pop/Glow Animations**:
   - Updated `MobileAuthBackground.tsx` / `<AuthRoadmapSvg />` shared component across mobile and desktop.
   - Milestones remain muted (`opacity: 0.4`) until reached, then animate with a subtle pop/lift (`scale: [1, 1.14, 1]`, `y: [0, -1.8, 0]`) and a soft radial unlock glow (`#milestone-unlock-glow`).
   - Reached milestones persist in their dark, prominent active state (`opacity: 1.0`, bold stroke, green accents).

5. **UI Consistency & CTA Centering Audit**:
   - Audited all action controls across mobile and web.
   - Fixed asymmetric left spacer in `MobileOnboardingScreen.tsx` footer when `onSkip` is absent.
   - Ensured explicit flex centering wrappers (`w-full flex justify-center items-center`) and `mx-auto` alignment on `ImportConfirmed.tsx`, `ImportError.tsx`, `MobileImportView.tsx`, and `EmptyState.tsx`.

## Fund Details performance graph: unified periods + desktop chart-distortion fix (2026-08-27)

Separate workstream from the mobile UI polish above, same day. Unified the "Fund
Details" performance graph on both web (`FundSignal.tsx`/`FundDetailModal.tsx`) and
mobile (`MobileFundDetailView.tsx`) onto the same 1M/1Y/3Y/5Y/MAX timeframe set,
wired to a new real backend endpoint (`GET /funds/{scheme_id}/nav-history`,
`fund_detail.py`) — both had previously shown 100% fake/stubbed chart data. Full
task breakdown, review rounds, and commit trail: `Docs/orchestration/delegation-log.md`'s
`fund-nav-history-graph` entries; spec/status: `Docs/orchestration/fund-nav-history-graph-handoff.md`
(**Status: DONE**, Tasks 1-4).

Built via `model-orchestration` (Codex implements, orchestrator verifies + reviews):
Task 1 backend service/route/tests (`abc1347`→`248daae`), Task 2 web wiring incl. a
scrubber-based hover/keyboard/touch interaction model (`b868947`→`9be0e2e`→`c38b37e`),
Task 3 mobile wiring porting the same interaction model (`4378679`→`750f189`→`2d7e72b`),
Task 4 final whole-diff review (3 Important + 1 Minor, all fixed: `c58c55b`, `83cfacc`,
`d7d06d5`).

**User-reported follow-up bug, found only after live use** (screenshots showed the
web chart rendering correctly in DevTools mobile-emulation but visibly warped — an
elliptical marker, distorted curve — on a real desktop/laptop width): root-caused to
`FundSignal.tsx`'s `viewBox="0 0 100 44" preserveAspectRatio="none"` forcing
non-uniform X/Y scaling once the wrapper's actual rendered width diverged from the
viewBox's fixed aspect ratio (true at the modal's realistic ~300-640px range).
Rejected a hardcoded-constant re-tune (range too wide for one constant) in favor of
measuring the wrapper's live width via `ResizeObserver` and using it directly as the
viewBox width, with viewBox height fixed to exactly match the CSS wrapper height —
makes the SVG-to-screen scale factor exactly 1:1 on both axes for any container
width. Committed `d6b367e`, visually confirmed by the user on both platforms.

Also resolved, per the user's explicit call: both chart components' `Number(point.return_pct)`
float coercion for chart-geometry (min/max/range) math was flagged across three review
passes as possibly violating the Decimal-never-float constraint. Confirmed `return_pct`
is always server-quantized to exactly `Decimal("0.01")` before being stringified, so
float rounding error (~1e-15) is undetectable at any chart pixel scale — kept as float,
documented as a deliberate, resolved exception rather than a residual bug.

Full frontend suite green throughout: 75 files / 381 tests. Dev servers used for local
verification (backend :8000, frontend :5173) were stopped at the end of this workstream.

## Still open, carried forward from earlier phases, not yet revisited

*(Moved here from `CLAUDE.md` 2026-08-24 — that file's Session State section is a
short pointer only, per its own header note; this is the detail it points to.)*

1. **RESOLVED 2026-09-03 (= compliance audit F8).** A held scheme with no obtainable NAV
   silently vanished from holdings/allocation/aggregates, no error or placeholder.
   **Product call resolved 2026-09-02**: user chose (b) — a degraded row with a visible
   "NAV unavailable" flag, NAV-dependent fields null, FIFO-derived fields (units held,
   invested, realized gain) always populated. Design: `Docs/orchestration/
   f8-nav-unavailable-degraded-row-handoff.md` (`distributor_comparison.py`'s identical
   sibling bug explicitly flagged as a separate, out-of-scope follow-up, not silently
   fixed alongside this). Implemented across 2 review rounds: round 1 fixed an
   understated "Total Invested" and a missing caption; round 2 caught (via adversarial
   review, independently confirmed) that `gainPercentage` mixed populations — dividing
   valued-only profit by an all-holdings invested total, understating the return — fixed
   by adding a `valuedInvestedVal` (valued-holdings-only) denominator in both
   `DashboardView.tsx` and `MobileDashboardView.tsx`. Status: DONE, in the combined
   uncommitted working-tree diff pending the non-PAN dedup task's own review closure.
2. **RESOLVED 2026-09-02 (= compliance audit F3).** No DB uniqueness constraint on the
   "self" `household_members` row — frontend-mitigated client-side only; real fix needed
   a migration (confirmed missing — migrations `0001`-`0010` existed, none touched this).
   **Read-only violation check run 2026-09-02** against the local dev SQLite DB
   (`backend/unifolio_dev.db`) first: 39 `self`-relationship rows across 46 distinct
   users, **zero users with more than one** — no existing dirty data to remediate,
   simplifying the fix to a straight constraint-add + API guard with no data-migration
   remediation strategy needed. Fixed: migration `0011_household_members_one_self_row.py`
   adds a partial unique index on `household_members(user_id) WHERE relationship =
   'self'`, expressed once via SQLAlchemy's `sqlite_where=`/`postgresql_where=` kwargs on
   a single `op.create_index` call (no runtime dialect branch needed, unlike F6's fix);
   `create_household_member` (`services/dashboard/household_members.py`) gained a
   pre-check raising `DuplicateSelfMemberError`, mapped to a 409 in the
   `/household-members` route (`api/dashboard.py`). Verified: new unit tests
   (`tests/services/dashboard/test_household_members.py`), an API 409 test
   (`tests/api/test_dashboard_routes.py`), a new Postgres functional test proving the
   `postgresql_where` branch enforces the constraint against a real server
   (`tests/functional_postgres/test_partitioning.py::test_household_members_one_self_row_per_user_on_postgres`),
   and the full 587-test SQLite suite plus 5 Postgres-marked tests, all green.
   `Docs/PRDs/Database-Schema-Unifolio.md` bumped to v1.5 documenting the new index.

   User separately raised a PAN-based idea for a related-but-distinct problem (detecting
   the same real person across multiple household-member/CAS-upload records), stating a
   belief that PAN is "currently persisted." That conflicts with this codebase's explicit,
   test-guarded rule — **no PAN persistence, ever** (`tests/models/test_no_pan_field.py`,
   `Docs/PRDs/Database-Schema-Unifolio.md`'s Data Classification section) — flagged back
   to the user 2026-09-02 per CLAUDE.md's "stop and say so" rule rather than silently
   built or silently dropped.

   **Resolved 2026-09-02**: user confirmed no PAN persistence, sign-off given for a
   non-PAN alternative, design left to Claude, explicitly asked to be "extensive." Design:
   split into two cases with different privacy remedies. Same-user cross-household-member
   duplicates get a new `(folio_number, amc_name)` signal added to `resolve_attribution`'s
   existing within-household matching (prioritized over its existing weaker name/email
   signal, safe to auto-offer a redirect since same tenant). Cross-user duplicates (two
   different Unifolio accounts holding the same real person's data) get a new, separate,
   advisory-only `detect_cross_account_duplicate` check — never blocks, never merges,
   never leaks the other account's identity, folio-match primary / name-match weaker
   secondary signal. Zero new PII persisted (folio_number/amc_name are already-persisted
   data reused, not new fields). Full design + rationale + rejected alternatives:
   `Docs/orchestration/non-pan-duplicate-person-detection-handoff.md`. **RESOLVED
   2026-09-03**: round 2 wired the design into the actual production import paths —
   a shared `enforce_attribution_confirmation` gate added to `attribution.py` and
   called at all 3 backend commit sites (`service.py::confirm_import`, both of
   `lifecycle_service.py`'s), a structured `member_mismatch` 409 through both
   `imports.py` and `cas_imports.py`, and desktop/mobile confirmation UI ("Switch" vs.
   "Continue anyway", resolving to genuinely different target members, not just
   different copy). This wiring surfaced a standalone architectural gap — two parallel
   import backends (`service.py`'s preview/confirm flow and `lifecycle_service.py`'s
   async CAS-upload flow) had independently drifted to need the identical fix wired in
   twice — documented at `Docs/orchestration/
   two-parallel-import-backends-architectural-gap.md`. Adversarial review round 2
   returned a bare "PASS, no findings" whose own test-execution claim was flagged
   unreproduced by the reviewer's environment (no SQLAlchemy in its Linux sandbox); not
   accepted at face value — the orchestrator independently re-verified the 3
   highest-risk points directly against the code (bypass-proofing at all 3 sites,
   Switch/Continue's end-to-end divergence, 409-shape consistency across both routes)
   plus PAN-safety, and independently reran both full test suites (614 backend/1
   skipped, 397 frontend/75 files — both exact matches to the implementer's
   self-report). Status: DONE, in the combined uncommitted working-tree diff.
3. `HoldingsTable.tsx` references a dead `row.return_percentage_1y` field that doesn't
   exist on the real API type — harmless (client-computed fallback always runs), never
   cleaned up.
4. `category_ranking.py`'s `_bulk_nav_on_or_before` (BUG-001 fix, 2026-08-18): the
   per-scheme N+1 query pattern is gone (one `MAX(date) GROUP BY` query per target date,
   bounded by a 15-min per-category cache), but the DB-side scan to compute each
   `MAX(date)` still isn't index-seek-bounded without a `LATERAL` join — a primitive
   unused elsewhere in this codebase and unverifiable via query plan on SQLite. Accepted
   as a documented limitation rather than a third fix round (correctness-safe, cost
   already bounded by the cache). Full follow-up action and rationale:
   `Docs/PRDs/Migration-Plan-SQLite-to-Postgres.md`'s "Deferred Postgres-Only
   Optimizations" section — revisit with `EXPLAIN ANALYZE` once Postgres is live.
5. `DashboardView.tsx`'s SIP Upcoming/This Month segmented control (`sip-tab-upcoming`/
   `sip-tab-month`) always renders both tab buttons' `aria-controls` IDs, but only the
   active tab's `role="tabpanel"` actually exists in the DOM — the inactive tab's
   `aria-controls` points at an ID that doesn't resolve, an incomplete ARIA tabs IDREF
   pattern. Confirmed via a second scoped Codex adversarial-review round
   (2026-08-19, `active-sips-cadence-redesign` branch, commit `8be5230`) after two
   earlier rounds closed a stale-row-flash bug and the missing tabpanel wiring itself.
   Accepted as a documented limitation rather than a third fix round, per the
   model-orchestration skill's stopping heuristic — negligible real-world screen-reader
   impact since the tab/panel pairing is already correctly conveyed via
   `role`/`aria-selected`/`aria-labelledby` on the panel that does exist, and a full fix
   means always mounting both panels (one `hidden`) instead of one conditionally-rendered
   panel, which also touches the lazy monthly-SIP-fetch trigger (the `sipTab !== "month"`
   early-return in `DashboardView.tsx`'s fetch effect) — a bigger structural change than
   proportionate to a Low finding. Revisit only if a real accessibility-audit or user
   complaint surfaces it as an actual usability problem. Full review-round detail:
   `Docs/orchestration/delegation-log.md`'s 2026-08-19 entries.
6. **RESOLVED 2026-09-02 (= compliance audit F7).** `compute_holdings`'s per-folio
   `Transaction` N+1 query pattern (`backend/app/services/dashboard/holdings.py`) —
   discovered as a side effect of the 2026-08-21 distributor-comparison-portfolio-level
   rewrite, confirmed pre-existing and explicitly out of scope for that change at the
   time. User explicitly asked for this fixed before staging rather than deferred
   further. Fixed: one batched `Transaction` query across all folios
   (`folio_id.in_(...)`), grouped by `folio_id` in Python preserving per-folio
   chronological order (the FIFO lot processor requires it). 42 holdings/allocation/
   category-ranking tests plus the full 584-test backend suite pass unchanged. Original
   deferral rationale: `Docs/superpowers/specs/2026-08-20-distributor-comparison-portfolio-level-design.md`'s
   "Follow-up (not built here)" section.
8. **(= compliance audit F4)** ADR-006's EventBridge Scheduler background jobs (daily
   NAV refresh, monthly TER, quarterly AAUM, daily benchmark) have never been built —
   today's lazy on-demand-fetch mechanism is a documented interim stand-in. User
   explicitly overrode the recommendation to defer/re-scope this past staging, reasoning
   the AWS infra work is happening right now anyway. **Scope split confirmed 2026-09-02**:
   (a) the 4 job-entrypoint scripts + wiring `amfi_aaum_client.refresh_aaum_data` into a
   real caller — buildable immediately, no AWS dependency, handed off as
   `Docs/orchestration/adr006-background-jobs-handoff.md`. **RESOLVED 2026-09-03**:
   piece (a) implemented and cleared the mandatory adversarial-review gate — status
   DONE, in the combined uncommitted working-tree diff (`backend/scripts/jobs/`,
   `backend/tests/scripts/`); (b) the actual EventBridge Scheduler + ECS Fargate task
   Terraform module — deliberately deferred to the infra-authoring phase, once an AWS
   account/ECR repo/ECS cluster exist to schedule against — not started.
7. **RESOLVED 2026-08-27, commit `bb5225f`** (this item was still marked open in the
   "Still open" lists above as of this session — corrected 2026-09-02 while writing the
   Analytics precompute implementation plan, which had cited it as a live risk before
   checking current code). A colleague's AMFI TER `ReadTimeout`s were root-caused to
   event-loop starvation from a blocking `db.commit()` inside an `async def` (this
   backend's SQLAlchemy engine is fully synchronous, single worker/event loop) — not
   AMFI slowness. Stopgap applied (`945b271`): AMFI TER httpx client timeout raised
   30s→90s, confirmed fixed live 2026-08-26. The underlying architectural vulnerability
   (any blocking sync DB call inside an async handler stalls every concurrent user, not
   just the slow request) was then properly fixed, not just worked around: `bb5225f`
   added `commit_off_loop` (routes `db.commit()` through `asyncio.to_thread`) and
   rewired every reachable commit across all 8 affected service files, with a
   regression test proving a slow commit no longer starves the event loop. Full
   narrative: this file's "AMFI TER `ReadTimeout` root-caused..." section below (predates
   the fix — read as historical, not current state).
9. **Phone-login OTP verify silently creates a new account for an unrecognized phone
   number, instead of erroring like the email channel does.** Found by the user
   2026-09-11 manually smoke-testing staging: logging in with a phone number that has no
   matching account still goes through the OTP-send/verify flow and ends by creating a
   brand-new account, rather than telling the user no account exists and directing them
   to sign up.

   Root cause, confirmed against the code: `backend/app/api/auth.py`'s
   `verify_otp_route` (phone-OTP channel), in the branch that handles a verify call with
   no `pending_token` (i.e. a plain login attempt, not part of an in-progress signup/
   phone-gate flow) — `find_or_backfill_phone_identity` returning `None` falls straight
   through to an unconditional new-`User` INSERT, per the branch's own comment ("Phone
   never collision-checks... brand-new phone number always completes signup
   immediately"). The equivalent email-OTP branch, `verify_email_otp`'s no-`pending_token`
   path, already does the right thing: `find_identity_by_subject` returning `None` raises
   a 401 ("No account found for that email — sign up instead.") instead of creating an
   account. The two channels' identical-shaped branches have simply diverged.

   Frontend-side, confirmed this is a clean single-sided gap, not a shared code path:
   `Landing.tsx` only renders the "Continue with Phone" button in **login mode** (its
   "Log In Experience" branch); signup mode offers email + Google only, with no direct
   phone-signup entry point anywhere in the UI. So the phone no-`pending_token` verify
   branch is *only* ever reached from a genuine login attempt — fixing it to 401 like
   email can't break a legitimate phone-signup flow, because that flow doesn't exist.

   **Also worth carrying forward for whoever picks this up**: even the email channel
   doesn't fully match the UX the user described as ideal. Today, email's existence
   check happens at **verify time** — the OTP is still requested and sent, and the user
   still lands on the "enter your code" screen, before the 401 fires. The user's stated
   expectation ("it shouldn't even go to this process of OTP... it should go back to the
   sign up side") implies the check should happen at **request time**
   (`/email-otp/request` / `/otp/request`), before any OTP is sent at all, for both
   channels — not just bringing phone's verify-time behavior in line with email's
   verify-time behavior. Moving the check to request time is a slightly larger change
   (touches both `request_*` handlers, not just both `verify_*` handlers) and has one
   real tradeoff worth surfacing to the user before building it: an unauthenticated
   "does this identifier have an account" check at request time is a mild account-
   enumeration surface (probeable without ever completing an OTP). Low stakes for this
   product, but a deliberate tradeoff, not a free improvement.

   **Explicitly deferred, not fixed, by user decision 2026-09-11**: the user judged this
   redundant work right now, reasoning that once a real OTP provider is attached later,
   invalid/nonexistent phone numbers will need to be handled as part of that integration
   anyway — fixing the current stub-OTP behavior first would likely be thrown away or
   reworked at that point. No code changed for this item; this write-up exists so the fix
   (either the narrow phone-verify 401, or the broader request-time check for both
   channels) can be picked up later without re-deriving the root cause from scratch.

## Two small post-merge bug fixes: AMFI TER concurrency, PDF export Allocation section (2026-08-24)

Two independent, small bug fixes on `feat/enhanced-ui`, neither delegated to Codex
(both small and contained enough for a direct fix — no `model-orchestration` dispatch):

**1. AMFI TER fetch concurrency lowered to avoid a 429 rate limit (commit `bb9f507`).**
`amfi_ter_client.py`'s `_TER_FETCH_CONCURRENCY` was raised to 20 in an earlier session
to fix a ~4-minute sequential-fetch regression, on the documented assumption that AMFI's
TER-page endpoint had no rate limit. Live-verified 2026-08-21 that assumption was wrong:
20 concurrent page requests trips a 429, leaving `scheme_ter` empty until the next
15-minute backoff window clears — surfaced to the user as "TER Data Unavailable" with
every scheme excluded. Lowered to 5. No retry-on-429 added on purpose: `ter.py`'s
existing 15-minute backoff already retries a failed refresh on the next request, so a
second retry layer here would be redundant.

**2. Analytics PDF export's Portfolio Allocation section rendered incorrectly (commit
`12946f7`).** User-reported via screenshot after downloading a portfolio's Analytics
PDF: the SEBI Category donut appeared as a barely-visible thin sliver instead of a full
circle, and the AMC breakdown never appeared in the PDF at all — only the Category tab
was visible. Two independent root causes, both traced from the actual render path
(`backend/app/services/analytics/pdf_export.py`'s `render_analytics_pdf`, which drives
Playwright against `frontend/src/features/analytics/print/PrintAnalyticsView.tsx`), not
guessed:

- **AMC tab never rendered**: `AllocationSection.tsx`'s Category/AMC toggle was pure
  React click state (`useState`), defaulting to "category" — the exact same bug class
  the PDF export feature's own Task 10 already found and fixed once, in
  `BenchmarkSection.tsx`'s tab toggle (see the "Analytics PDF export" section below).
  `AllocationSection` never got that same `printMode` treatment. Since Playwright's
  static print capture never clicks anything, only the default tab's data could ever
  reach the PDF.
- **Donut rendered mid-animation**: `PieSlice.tsx` (the `ui/charts` primitive
  `AllocationDonut` builds on) draws each slice in via a `motion/react` spring, with a
  per-slice stagger delay, starting from a 0%-drawn arc on mount. `render_analytics_pdf`
  captures `page.pdf()` the instant the `data-print-ready` DOM marker appears — which
  fires as soon as the export payload loads, not once the chart's entrance animation has
  finished — so the PDF snapshotted the donut a fraction of a second into its draw-in
  animation, matching the screenshot exactly (a barely-visible sliver of the first
  slice's color).

**Fix**: gave `AllocationSection` a `printMode` prop mirroring `BenchmarkSection`'s
existing pattern exactly — hides the toggle buttons, stacks both the Category and AMC
`AllocationDonut` breakdowns instead of tab-switching between them. Separately, added an
`animate` prop to `AllocationDonut`, forwarded to each `PieSlice` — `PieSlice` already
had a built-in static (instant, non-animated) render path for this exact purpose, just
never wired through to anything; both print-mode donuts now pass `animate={false}`.
Wired into `PrintAnalyticsView.tsx` (`<AllocationSection ... printMode />`).

TDD: new tests written first and confirmed red — `AllocationDonut.test.tsx` (a slice's
`d` path attribute is empty on the very first render frame with the default animated
path, present immediately with `animate={false}`) and a new `AllocationSection.test.tsx`
(printMode renders both breakdowns with no tab button in the DOM at all) — then green
after the fix. Full frontend suite re-run clean: 335/335 tests across 72 files, `tsc -b
--noEmit` clean.

## AMFI TER `ReadTimeout` root-caused to event-loop starvation from blocking `db.commit()` (2026-08-25/26)

A colleague's Analytics dashboard persistently showed "TER Data Unavailable"/"No
Direct Holdings"/"No Regular Holdings" plus a growing TER-exclusion list, on the same
codebase where Ayush's own laptop showed correct data. Diagnosed via
`superpowers:systematic-debugging`, three rounds:

1. **Fix 1 — AMFI 429** (`3b2b1d8` on this worktree / `bb9f507` on `feat/enhanced-ui`):
   `_TER_FETCH_CONCURRENCY` 20→5 in `amfi_ter_client.py`. Live-verified the colleague was
   getting rate-limited by AMFI at concurrency 20, leaving `scheme_ter` empty for the
   full 15-min backoff window. Confirmed no scaling/loading-speed regression — matches
   the existing degrade-gracefully convention used elsewhere (`nav.py`, `arn_lookup.py`).
2. **The issue recurred after Fix 1.** `refresh_ter_data` had zero logging on any failure
   path (a bare `return False`), making a recurrence undiagnosable from a report alone.
   Added two `logger.warning(...)` calls — pure diagnostics, no behavior change
   (`142eb6b`). Colleague re-tested live; the new logging immediately captured the real
   failure on the very first run: `refresh_ter_data: fetch failed: ReadTimeout('')` — a
   genuinely different failure mode from the already-fixed 429 (all AMFI TER pages in
   this run returned `200 OK`).
3. **Root cause**: this backend's SQLAlchemy engine is fully synchronous
   (`app/db/session.py`'s `create_engine`, no async driver), and — per an existing
   comment in `pdf_export.py` ("move to Redis/similar if/when this backend ever runs
   multiple workers") — currently runs as a single worker, i.e. a single event loop
   shared by every concurrent request. A blocking `db.commit()` called directly inside
   an `async def` (here, `nav.py`'s `warm_nav_history`, logged at `commit=63.67s` then
   `commit=66.69s` for the same 1150-scheme NAV warm on the colleague's machine, minutes
   apart) freezes that entire event loop for its full duration — including an AMFI TER
   page request already waiting on its socket in a concurrently-running task, which then
   blows its own 30s client-side httpx timeout even though AMFI itself answered
   normally. Not a repeat of the 429 (already fixed) and not the caching-divergence
   theory originally suspected — direct evidence of event-loop starvation, correlating
   with `nav.py`'s own documented note that commits measure "57x slower... on a WSL
   DrvFs-mounted dev DB than a native filesystem."
4. **Fix 3** (`945b271`): raised `amfi_ter_client.py`'s httpx client timeout from 30.0s
   to 90.0s (`_TER_HTTP_TIMEOUT`, both `_fetch_latest_ter_month` and `_fetch_ter_rows`),
   giving real margin against the observed 63-66s stall. This is a stopgap for TER
   refresh's all-or-nothing blast radius (one page timing out currently fails the
   *entire* batch for the full 15-min backoff, unlike NAV's per-scheme degrade), not a
   fix for the underlying starvation. All 27 TER tests still passing.

All three fixes cherry-picked onto `feat/enhanced-ui` and live-tested together on the
colleague's machine 2026-08-26: **confirmed working** — TER data now loads correctly
(noticeably slower than Ayush's machine, but correct — expected, since the colleague's
disk/network genuinely is slower, not a bug).

**Localhost-specific vs. global, discussed with Ayush, not yet built:** the *trigger*
(60-120s SQLite commits) is dev-environment-specific — SQLite on a WSL DrvFs-mounted
filesystem — and should mostly disappear once the app is on Postgres (per the planned
SQLite→Postgres migration), where a comparable commit is typically single-digit
milliseconds even under load. The underlying *vulnerability* (any blocking sync DB call
inside an `async def` handler stalls every concurrent user sharing that event loop, not
just the slow request) is architectural, not environment-specific, and will still exist
in production: under real concurrent traffic, any sufficiently slow DB operation (lock
wait, a big batch commit, connection-pool exhaustion, a large CAS re-import) could still
freeze every logged-in user's request simultaneously — a materially worse failure shape
(correlated, multi-tenant outage) than a typical N+1 slowdown, which only affects the one
slow request.

**Decision: not fixed now.** Logged as a new "Still open" item (`CLAUDE.md` item 7),
same precedent as `compute_holdings`'s N+1 and `category_ranking`'s non-index-seek-bounded
scan — avoid a large cross-cutting DB-layer refactor bundled into unrelated debugging
work. Revisit deliberately, ideally paired with the Postgres migration, since that's the
natural point to pick between these three remediation options against a real production
driver instead of guessing against SQLite:
1. **Targeted** — wrap only the known-heavy batch commits (`warm_nav_history`'s,
   `refresh_ter_data`'s, CAS import's) in `asyncio.to_thread(db.commit)`.
2. **Blanket** — wrap every sync DB call site inside an `async def` in
   `asyncio.to_thread`. More consistent; needs auditing that no `Session` is touched
   from two threads concurrently.
3. **Correct long-term fix** — migrate to SQLAlchemy's native async engine
   (`AsyncSession` + `asyncpg`/`aiosqlite`), rewriting every `db.query`/`db.execute`/
   `db.commit` call across the backend. The right answer, but a dedicated project of
   its own, not a task to bundle into other work.

## Distributor comparison rewritten portfolio-wide, desktop + mobile (2026-08-21)

Rewrote the existing fund-scoped distributor comparison (PRD-03 FR-11, the
`DistributorComparisonModal`/`MobileDistributorComparisonView` pair added in an earlier
phase) into a portfolio-wide feature: one "Compare Distributors" trigger per Holdings
section (desktop `DashboardView`, mobile `MobileHoldingsView`, mobile
`MobileDashboardView`'s embedded Holdings section) instead of a per-fund CTA, showing
every distributor across the whole household/member portfolio with expandable
per-scheme breakdowns. Backend: `compute_distributor_comparison` rewritten around a
batched query (`Folio.household_member_id.in_(...)`), replacing the old
`compute_distributor_comparison`'s N+1 pattern; schema split into
`DistributorSchemeBreakdown`/`DistributorPortfolioRow`/
`AggregateDistributorComparisonResponse`; two new routes (member-scoped + aggregate),
old single-scheme route removed. Frontend: `getMemberDistributorComparison`/
`getAggregateDistributorComparison` replace the old `getDistributorComparison`;
`DistributorComparisonModal` rebuilt as an expandable-row table (desktop),
`MobileDistributorComparisonView` rebuilt as expandable cards (mobile idiom, not a
ported table). Full design: `Docs/superpowers/specs/2026-08-20-distributor-comparison-portfolio-level-design.md`.

Executed via `superpowers:subagent-driven-development` in a dedicated worktree
(`.claude/worktrees/distributor-comparison-portfolio-level`, branch
`worktree-distributor-comparison-portfolio-level`, off `feat/enhanced-ui`), 10
implementation tasks + full-suite verification, each through the `model-orchestration`
skill's mandatory Codex-implements/orchestrator-verifies/task-scoped-review loop. Every
task closed on its first review pass except Task 5 (1 Important — test fixtures widened
`DistributorPortfolioRow.arn_status` from its literal-union type to plain `string`,
failing `tsc`/`npm run build`; fixed inline by the orchestrator per the "small diff,
already in context" rule rather than a full Codex re-dispatch, then pre-empted from
recurring in Task 8 by instructing that implementer to type the fixture up front) and a
scoping-artifact false-positive on Task 7 (a delegation-log commit swept into the review
diff range — not a code defect; fixed by tightening the review-package range, not the
code). Full per-task narrative: `Docs/orchestration/delegation-log.md`'s 2026-08-21
entries.

Full-suite verification (Task 11) green: backend 455 passed/2 skipped, frontend 230
passed across 56 files, `tsc --noEmit` clean. One dead-reference cleanup caught by the
verification grep sweep and fixed inline: `MainDashboardFlow.test.tsx` still mocked the
old singular `getDistributorComparison` (renamed/split in Task 3), unused elsewhere in
the file — removed. `compute_holdings`'s own pre-existing per-folio N+1 (discovered as
a side effect, confirmed unrelated and out of scope) logged as a new "Still open" item
in `CLAUDE.md` rather than fixed here, per the spec's own Follow-up section.

Task 12 (final whole-branch review) is now complete: 1 fix round (a Decimal-float
violation, a missing TTL-expiry test, stale docs — commit `848a1fd`), 1 scoped
re-review residual (a Decimal scientific-notation sign-check gap — commit `b01ef0d`).
Full ledger trail: `Docs/orchestration/delegation-log.md`. Merged into `feat/enhanced-ui`
via merge-conflict resolution (not rebase, since `feat/enhanced-ui` had moved 133
commits ahead of this branch's creation point) — only 3 real conflicts, all docs
(`CLAUDE.md`, `session.md`, `Docs/orchestration/delegation-log.md`), everything else
auto-merged clean. That divergence brought in, already on `feat/enhanced-ui`, the three
sections immediately below: post-merge stabilization, the `authsetup` merge (Auth,
Onboarding, CAS Import v2, Mobile Polish), and the Analytics PDF export merge.

## Mobile Privacy Screen & Onboarding Full-Screen Redesign (2026-08-21)

Implemented the Mobile Privacy Screen & Onboarding Full-Screen Redesign per `Docs/superpowers/specs/2026-08-20-mobile-privacy-onboarding-fullscreen-plan.md` on branch `feat/enhanced-ui`:

1. **`MobileOnboardingScreen.tsx` Component**:
   - Built the shared mobile full-screen container (`min-h-dvh w-full bg-[var(--color-bg)] flex flex-col justify-between p-4 sm:p-6`).
   - Implemented exact validated element order (§3):
     `top bar → headline → illustration → subtext → content → CTA (no eyebrow label)`.
   - Top bar renders back chevron (`ChevronLeft`), step progress indicator dashes (`Step X of 5`), and skip link (when available).
   - Constrained illustration height to fit comfortably above subtext without pushing CTAs off-screen.

2. **Client-Side 2-Point Privacy Split in `TrustPrimer.tsx` (§5)**:
   - Added internal client-side `point: 1 | 2` state to `TrustPrimer.tsx` when `isMobile` is `true`:
     - Point 1: Headline *"Your privacy & data safety come first"*, Illustration `trust`, Subtext *"Unifolio only parses holdings and transactions to show analytics. Nothing is ever bought, sold, or transferred."*, CTA *"Next"*.
     - Point 2: Headline *"No raw CAS PDF storage"*, Custom Privacy Lock Hero Visual SVG with emerald glow, Subtext *"Statements are processed in-memory. Your raw CAS PDF and PAN are never permanently stored."*, CTA *"Continue"*.
     - Removed redundant bottom bordered information boxes/cards, leaving the clean `Heading → Illustration → Description → CTA` structure matching reference design.
     - Back navigation from Point 2 returns internal state to Point 1.
   - Desktop presentation (`isMobile === false`) renders completely unchanged in its original single-card layout inside `OnboardingCardStack`.

3. **Step Wrappers & Unification**:
   - Threaded `isMobile` from `App.tsx` into `OnboardingFlow.tsx`.
   - Wrapped `Q1Name.tsx`, `Q2Investing.tsx`, `Q3Purpose.tsx`, `Q4Household.tsx`, and `AddFamilyMembers.tsx` with `MobileOnboardingScreen` when `isMobile` is `true`.
   - Swapped illustration variant in `AddFamilyMembers.tsx` from `"household"` to `"family"` (§6 #7).
   - Preserved desktop's `OnboardingCardStack` presentation 100% unchanged.

4. **Automated Unit Tests**:
   - Created `MobileOnboardingScreen.test.tsx` testing top bar, element order, back/skip/CTA clicks, and disabled CTA states.
   - Updated `TrustPrimer.test.tsx` testing both desktop view and mobile 2-point pagination navigation.
   - Verified that all **72 test files (334 tests total)** pass 100% cleanly.

## Post-Merge Stabilization: Alembic Migration Linearization & Windows Playwright Lifecycle (2026-08-21)

Stabilization following the merge of `authsetup` and `worktree-analytics-pdf-export` into `feat/enhanced-ui`:
1. **Alembic Head Conflict**: Resolved two `0004` revisions by renumbering `0004_scheme_ter_nullable_value.py` to `0009_scheme_ter_nullable_value.py` (`down_revision = "0008"`), creating a linear chain from 0001 to 0009.
2. **Local DB Version Alignment**: Local SQLite DB was reset with `alembic stamp 0003` then upgraded through `0009` so `auth_identities` table and phone OTP backfills created in 0004/0005 exist before application startup.
3. **Windows Playwright Lifespan**: Playwright Chromium launch uses `asyncio.create_subprocess_exec`, which requires `ProactorEventLoop` on Windows. Set `asyncio.WindowsProactorEventLoopPolicy` in `app/main.py`, updated `backend/scripts/run_server.py`, and documented `--loop asyncio.ProactorEventLoop` for uvicorn reloader.
4. **Detailed Reference**: Full failure modes, error logs, and verification checklist documented in `Docs/orchestration/post-merge-environment-and-migration-fixes.md`.

## Auth, Onboarding, CAS Import v2 & Mobile Polish merged from `authsetup` (2026-08-20)

Merged from a long-running parallel branch, `authsetup`, covering Auth, Onboarding,
Validation, Visual Experience, Mobile Auth, and the CAS Import Flow Redesign (v2) —
all reported 100% complete on that branch as of 2026-08-20. Most recent slice before
merge: Mobile Auth Header Typography & Spacing (`AuthShell.tsx`) — scaled up mobile
brand text (`text-2xl`), logo glyph (`w-5 h-5`), mobile headline (`text-xl`), and
subtext (`text-sm`); replaced `my-auto` centering on the mobile form container with
`mt-2 mb-auto lg:my-auto` to remove the excessive vertical gap between the subtext and
the "Create your account" form.

**Components built/integrated in this merge:**
1. `amcLogos` module (`frontend/src/lib/amcLogos.ts` & `amcLogos.test.ts`) — AMC → logo
   vector asset map and alias resolution engine (7/7 unit tests passing).
2. `SchemeLogo` (`frontend/src/components/SchemeLogo.tsx`) — prioritizes AMC logo
   vector assets mapped from parsed scheme data, falling back to initial-letter avatars.
3. `ReviewTable` & `MobileReviewView` — embed AMC logo tiles in web (grid/list) and
   mobile review cards.

**Verification on `authsetup` before merge:** 60/60 test files, 279/279 tests passed
(`npx vitest run`); 0 TypeScript errors (`npx tsc -b`).

**Note for whoever picks this up next:** `authsetup`'s own "what's next" pointed at
building the PRD-04 Analytics frontend — by the time of this merge that work had
already progressed significantly on `feat/enhanced-ui` independently (see the Analytics
PDF export and phantom-holding/ISIN sections below). Reconcile against those before
assuming Analytics frontend work is still fully greenfield.

Full detail on everything else merged from `authsetup` (Auth Input/OTP responsiveness,
Auth Navigation Flow fix, the global mobile UI/UX pass across onboarding/auth/CAS-import,
the illustration-led CAS Import redesign v2, the Auth Showcase panel redesign, the auth
validation engine, hand-drawn illustrations): see `git log authsetup` prior to this
merge, or `CLAUDE.md`'s Session State history before this merge commit.

## Analytics PDF export: all 10 plan tasks done, reviewed clean, merged to feat/enhanced-ui (2026-08-20/21)

Worktree `/mnt/d/Unifolio code/.claude/worktrees/analytics-pdf-export`,
branch `worktree-analytics-pdf-export`, executed via
`superpowers:subagent-driven-development` against
`Docs/superpowers/plans/2026-08-20-analytics-pdf-export.md` (spec:
`Docs/superpowers/specs/2026-08-20-analytics-pdf-export-design.md`). All 10
tasks implemented, task-reviewed, and committed:
`2f77e4b..4ce4561` (base for the review range is `321b6ed`, the plan-commit
itself). Feature: capability-token payload store, shared Playwright browser
lifecycle, `/export/pdf` + `/export/payload/{token}` routes, a real
(non-mocked) Playwright integration test, `FundScoreCard` extraction,
`AnalyticsExportPayload` type + API client, `/print/analytics` print route,
and a "Download PDF" button gated on full dashboard load.

**Task 10 (manual E2E verification) found and fixed two real bugs**,
committed as `4ce4561`:
1. `PrintAnalyticsView.tsx`'s fetch effect double-fired under React 18
   StrictMode, always 404ing on the second call against the single-use
   export token — fixed with a `useRef` guard.
2. `BenchmarkSection.tsx`'s per-fund comparison tab and "Show More"
   pagination were gated behind client-side click state, invisible to a
   static PDF render, contradicting the design doc's explicit no-click-gating
   claim — fixed with an opt-in `printMode` prop (mirrors the `FundScoreCard`
   "always expanded" precedent from Tasks 6/8), plus a new test.

Also confirmed correct (not bugs): the cover page's scope name for both
single-member ("Dev User (Me)") and multi-member aggregate ("Family
Aggregate") scenarios, and member-scoped PDF export correctly excluding
other members' data.

**Found, ledgered, ruled out of scope — not fixed:** a pre-existing backend
bug, `category_ranking.py:76`'s `_cagr` raising `decimal.DivisionUndefined`
(0/0) for aggregate multi-category portfolio scoring when a category's NAV
history is shorter than the 3-year CAGR lookback. Confirmed via backend-log
correlation that this identically breaks the *live* dashboard's own
`getAggregateScore`/`getAggregateCategoryRanking` calls (degrading to an
empty "No category ranking data available" state) — not introduced by or
specific to PDF export. Worth a follow-up ticket; full detail in
`.superpowers/sdd/2026-08-20-analytics-pdf-export/progress.md` (git-ignored
ledger, worktree-local).

All seed data, temp scripts, and manually-launched dev servers used for
verification were cleaned up; working tree is clean apart from the
untracked, pre-existing `backend/.venv`.

**Handed off to Codex, not dispatched as a Claude subagent:** the plan's
mandatory final whole-branch review (git range `321b6ed..4ce4561`) — because
this Claude account is at ~93% of its weekly limit, and the review is a
bounded read-only task Codex can do without spending Claude quota. Handoff
doc: `Docs/orchestration/analytics-pdf-export-final-review-handoff.md`,
logged in `Docs/orchestration/delegation-log.md`'s 2026-08-21 entries.

**Review round 1** found 2 confirmed Important findings (both against the
spec's literal "500 + evict token, regardless of success or failure" line):
the print page's success and error paths both set the same "ready" marker,
so a fetch failure rendered a 200 PDF of an error page instead of a 500; and
the export token was only ever consumed by the print page's own fetch, so a
render failure never evicted it. A third finding (`FundScoreCard`'s
`parseFloat`/`toFixed`) was ruled *not* a defect — `decimal.ts`'s own
documented exemption for single, non-accumulating display conversions
covers it, and the code predates this plan (Task 4 only extracted it).
Fix round 1 (Codex-authored, orchestrator-verified and committed — Codex's
own sandbox hit an unrelated AnyIO/TestClient hang on the full suite and
declined to commit under its completion contract; the orchestrator
independently reran both full suites clean outside that sandbox): `d59542e`.

**Round-2 scoped re-review** of that fix found one further Medium gap: the
fix caught the render failure with `except Exception`, which does not catch
`asyncio.CancelledError` (derives from `BaseException` in Python 3.8+) — a
client disconnect or request timeout mid-render would skip token cleanup.
Fixed directly by the orchestrator (not redelegated, per the
model-orchestration skill's "Review-loop fix authorship" rule — small diff,
files already in context) by moving the eviction into a `finally` block:
`86c60c5`. A final scoped re-review confirmed the gap closed, no new issues,
and returned **"Ready to merge? Yes"** for `321b6ed..86c60c5`.

Merged into `feat/enhanced-ui` locally (Option 1 of
`superpowers:finishing-a-development-branch`) as merge commit `ed149bf`
(`9c1dcbc..ed149bf`, no conflicts — pre-verified conflict-free via
`git merge-tree --write-tree`). Backend `pytest` and frontend `vitest` both
confirmed passing on the merged tree. `feat/enhanced-ui`'s worktree is not
under `.worktrees/`/`worktrees/`, so it's left in place per that skill's
cleanup table. SDD workspace
(`.superpowers/sdd/2026-08-20-analytics-pdf-export/`) deleted. This feature
is fully done — nothing left open on this branch.

## Phantom-holding bug fixed, ISIN cross-check added, index-fund mega-category split investigated + deferred (2026-08-19/20)

Root-caused a dashboard-visible phantom "UTI Children's Equity Fund" holding: a newly
launched scheme (JioBlackRock Flexi Cap, launched Oct 2025) whose CAS-parsed name
dropped "Plan"/"Option" suffixes fell to 0.87 name-similarity against mfapi.in's
canonical name — below `resolve_scheme`'s 0.92 confirm gate — even though
`amfi_from_cas` was correct (casparser resolved it via ISIN). General fix (not just this
one scheme): `enrich.py`'s `resolve_scheme` now checks `isin` against mfapi.in's own
`isinGrowth`/`isinDivReinvestment` for the CAS-supplied code *before* falling back to
name-similarity — additive only, never weaker than the existing DATA-001 cross-check.
Verified against the real cached mfapi data reproducing the exact previously-failing
case now succeeding. Also cleaned up two throwaway test accounts. Committed as 3
commits on `feat/enhanced-ui` (ISIN fix + tests, TER parallel-fetch/nullable-marker
work already in flight, and the timing/logging instrumentation added to
`main.py`/`nav.py`/`category_ranking.py`/`scorer.py` — explicitly kept per Ayush's
request, useful for the next perf investigation).

Separately, investigated whether to split AMFI's 1,150-scheme
`"Other Scheme - Index Funds"` mega-category into smaller peer-groups for
category-ranking/Scorer performance. Produced a concrete bucket list (both a
fine-grained per-benchmark option and a coarser AMFI-precedented asset-class option,
with real counts from the cached `NAVAll.txt`) for Ayush to review with finance-domain
peers before any build decision. **Decision: deferred, not built** — peers judged the
only design that actually shrinks the category (bespoke per-benchmark regex buckets) an
unrecognized-by-AMFI taxonomy not worth the risk; the AMFI-native alternative doesn't
solve the size problem. Full bucket list, both options, and a side finding (a possible
data-completeness gap in `get_category_universe`'s exact-string category match) at
`Docs/superpowers/specs/2026-08-20-index-fund-mega-category-split-deferred.md`; tracked
in `DEFERRED_FEATURES.md`'s PRD-04 table for future revisit.

## BUG-001/DATA-001 implementation complete, all 7 items DONE (2026-08-18)

Worked from the ready-to-paste implementation prompt
(`Docs/orchestration/bug-001-data-001-implementation-prompt.md`) in a
dedicated worktree/branch (`bug-001-data-001-implementation`, off
`feat/enhanced-ui`). All 7 items closed through `model-orchestration`'s
full mandatory adversarial-review gate, TDD throughout:

1. **XIRR ×100 display fix** — DONE.
2. **Scorer caching + bounded series query** — DONE.
3. **TER negative-cache/backoff** — DONE after 4 review→fix rounds: a
   per-loop-lock fix introduced a cross-loop deadlock (fixed with a
   `WeakKeyDictionary`-keyed lock per event loop), which introduced a
   cross-thread backoff race on the shared last-attempt timestamp (fixed
   with a `threading.Lock`-guarded claim function), whose own regression
   test was non-deterministic (fixed with an `Event`-based deterministic
   contention test). Closing review: APPROVE.
4. **Category Ranking bulk query + alternating-timing investigation** —
   DONE. `_bulk_nav_on_or_before`'s N+1 pattern replaced with one
   `MAX(date) GROUP BY` query per target date, 15-min per-category cache.
   Residual non-index-seek-bounded scan on SQLite accepted as a
   documented Postgres-migration follow-up (`Migration-Plan-SQLite-to-Postgres.md`).
5. **NSE `follow_redirects=True`** — the initial fix was found, on live
   reproduction, to rest on a false premise, and was correctly reverted;
   re-fixed with a narrower `decimal.InvalidOperation` catch at the
   actual `Decimal(entry["CLOSE"])` conversion boundary. Closing review:
   APPROVE.
6. **TER silent-zero + Scorer cost-adjustment sentinel** — DONE after 2
   rounds: ingestion now skips AMFI's literal-0 TER rows and the Scorer
   distinguishes "TER unknown" (`None`) from "TER genuinely 0" via a
   dead-zone check, and a stale already-persisted zero-TER row from
   before the fix is now deleted on next refresh rather than surviving
   forever. Closing review: APPROVE (1 Low process-only nitpick, no code
   finding).
7. **Import identity validation tightening** — `enrich.py`'s
   `resolve_scheme()` now cross-checks a CAS-supplied AMFI code against
   its canonical master-list name (≥0.92 similarity) before confirming
   at full confidence, instead of trusting the pairing blindly;
   `confirm_import()` gained a 409 backstop on both an override
   `amfi_code` absent from the master list and a `plan_type_override`
   contradicting an anchored "Direct Plan"/"Regular Plan" name match —
   closing CLAUDE.md's previously-open "no server-side 409 backstop on
   plan-type override" item. 2 review rounds: round 1 found the plan
   backstop was checking a loose whole-name substring match (false-positive
   risk), a recurred stale-`.cache/mfapi/` test-isolation gap, and a
   `SequenceMatcher("", "").ratio() == 1.0` blank-name edge case in two
   call sites — all fixed. Closing review: APPROVE, zero findings.

Full backend suite: 412 passed, 2 skipped (started this workstream at
401/2). `tsc -b --noEmit` clean throughout (frontend untouched by every
item). Full per-item narrative, rejected approaches, and review verdicts:
`Docs/orchestration/delegation-log.md` and the per-item handoff docs
under `Docs/orchestration/` (`*-handoff.md`, one per item).

**What's next:** this branch/worktree is not yet merged into
`feat/enhanced-ui` — that's the next action. `task-observer` has not yet
been run for this workstream's accumulated observations (codex-rescue
meta-result pattern, an inconsistent status-check refusal, a self-caught
`isolation: worktree` review-dispatch mistake, and the value of the
root-cause-not-symptom stale-cache fix) — worth doing before or shortly
after the merge.
## "This Month" SIP tab feature, Tasks 6-8 review gate closed (2026-08-19)

Frontend half of `Docs/superpowers/plans/2026-08-18-active-sips-cadence-redesign.md`
(Tasks 1-5, backend, already `DONE` from a prior session) — a month-scoped SIP
view on `DashboardView.tsx` alongside the existing Upcoming SIPs list, switched
via a `role="tablist"` control. Went through `model-orchestration`'s full
mandatory adversarial-review gate, three rounds:

- **Round 0** (`53919a6..4f39e9b` scope, after an initial dispatch had to be
  re-issued): 2 Medium + 1 Low — a `{upcomingSips.length > 0 && ...}` gate that
  hid the entire tab switcher whenever there were no upcoming SIPs, stale
  monthly-SIP rows rendering during an in-flight fetch, and missing tab ARIA
  semantics (`role="tab"`/`aria-selected`). Fixed directly by the orchestrator
  (small diff, file already in context — the skill's "Review-loop fix
  authorship" rule) at `eeaade0`.
- **Round 1** (scoped re-review of `eeaade0`): found the loading-flash fix was
  necessary but incomplete — `setMonthlySipsLoading(true)` lived inside a
  `useEffect`, which fires after the paint that already shows the new
  `sipMonth`, so one stale frame still got through — plus a missing
  `role="tabpanel"` (`id`/`aria-labelledby`/`aria-controls`) wiring. Fixed at
  `8be5230`: moved the `setState` call into the Previous/Next month `onClick`
  handlers directly so it batches with `setSipMonth` into the same render
  (avoided reaching for `useLayoutEffect`), and added the tabpanel wiring.
- **Round 2** (scoped re-review of `8be5230`, full frontend suite requested
  since this round was expected to close the gate): one remaining Low — the
  inactive tab's `aria-controls` still points at a `tabpanel` `id` that isn't
  mounted in the DOM (only the active panel renders). Recommended accepting as
  a documented limitation per the skill's stopping heuristic (lower severity
  than round 0, correctness-safe — screen readers still get the correct
  tab/panel pairing via `aria-selected`/`aria-labelledby` — and a real fix
  needs always-mounted dual panels, a bigger structural change than the
  finding warrants, also touching the lazy monthly-SIP-fetch effect's
  `sipTab !== "month"` early return). User agreed, conditioned on it not being
  a loading/efficiency/scaling issue (it isn't — synchronous client-side tab
  state, no fetch path involved). No round 3 dispatched.

Orchestrator independently ran the full frontend suite on the closing round:
55/55 files, 218/218 tests, zero regressions. **Tasks 6-8 review gate: DONE**,
final scope `9e25017..8be5230`. Closing commit `a148d42` documents the
accepted ARIA gap in `CLAUDE.md`'s "Still open" list (item 5) and mirrors it in
`DEFERRED_FEATURES.md`'s appendix; `Docs/orchestration/active-sips-frontend-handoff.md`'s
`Status` line carries the same closing summary. Full round-by-round log:
`Docs/orchestration/delegation-log.md`'s 2026-08-19 entries.

**`model-orchestration` skill → v1.4, same session:** added
`delegation-rules.md`'s mandatory cheap-probe-before-expensive-setup pre-step
(write a file, `git add`, `git commit` against any new Codex dispatch
location, before paying a large dependency-tree copy cost) after confirming
`git add`/`git commit` fail inside this project's `codex:codex-rescue` sandbox
even when ordinary source-tree writes succeed — reproduced across two
independent sessions/directories, scoped as an environment limitation, not a
universal Codex constraint. Codified the resulting default worker split
(Codex implements + self-tests; orchestrator always handles
staging/commits/merges/worktrees; Codex stays default worker for read-only
review regardless) and an explicit independent-verification rule for agent
completion whenever a dispatched agent's terminal notification is missing,
premature, or contradictory. Full changelog: `SKILL.md`'s v1.4 note.

**Housekeeping, same session:** two Analytics Dashboard docs
(`Docs/Analytics-Dashboard-Formula-Implementation-Review.md`,
`Docs/Analytics-Dashboard-Internal-Correction-Plan.md`) were found sitting
uncommitted and unlinked from any session doc — a stakeholder-facing
methodology write-up and its internal P0/P1 correction plan (including the
already-known XIRR ×100 display bug from `data-001-findings.md`), both
awaiting their own sign-off gates, not a Claude Code review-gate item. Now
committed and pointed to from `CLAUDE.md`'s Session State — worth reconciling
against `Docs/orchestration/bug-001-data-001-implementation-prompt.md`'s fix
list next time DATA-001 implementation actually starts, in case the two have
diverged. `.claude/settings.json`'s uncommitted diff (a trivial
`worktree.baseRef` reordering, tool-generated) was deliberately left alone —
unrelated to this session's work.

**What's next:** nothing outstanding from the SIP tab task. The
next real implementation work on the table is still DATA-001
(`Docs/orchestration/bug-001-data-001-implementation-prompt.md`) and
BUG-001 (`Docs/orchestration/bug-001-findings.md`) — both investigated and
unblocked as of 2026-08-17/18, neither started yet.

## First-login dashboard load-time fix, PR #4 merged (2026-08-18)

User-reported follow-up to the earlier `dashboard-nav-perf-handoff.md` round: first
dashboard load right after a new signup's CAS upload was still ~30s. Root-caused as
two independent bottlenecks (dashboard NAV fetch's no-connection-reuse/no-dedup pattern
in `nav.py`, and CAS-preview's fully-sequential no-connection-reuse/full-endpoint pattern
in `enrich.py`/`service.py`) via live benchmarking against the real `api.mfapi.in`. Each
fixed in its own worktree/branch (`perf/nav-fetch-connection-reuse`,
`perf/import-preview-concurrency`), each through `model-orchestration`'s full
Codex-dispatch + mandatory adversarial-review gate cycle — 2 review rounds apiece. The
import-preview review's first round caught a real regression the `asyncio.gather`
parallelization introduced (a concurrent stampede on `get_scheme_list()`'s uncached
first-fetch path — the old sequential loop had accidentally serialized this); fixed with
a double-checked `asyncio.Lock`. That fix's own scoped re-review returned a stale,
contradicted-by-direct-read "REQUEST CHANGES" on the first dispatch (described the lock
as absent when it was present) — re-dispatched and got a correct "APPROVE" on the second
try; logged as `skill-observations/log.md` Observation 2 (stable Claude Code workspace
project folder, not this repo) since blindly trusting a review verdict without a cheap
sanity-check on the cited lines would have triggered wasted rework.

Both branches were merged into one combined branch `perf/dashboard-load-time` (clean
merge, no conflicts — disjoint files) and shipped as
[PR #4](https://github.com/ayushkarnawat/MVP_V1_MF_only/pull/4) against
`feat/enhanced-ui` — **merged 2026-08-18**. Full backend suite on the combined branch:
374 passed, 2 skipped, zero regressions (up from 368/2 on `import-preview-concurrency`
alone — the +6 delta is the `nav-fetch-connection-reuse` branch's own test additions
folded in by the merge). Live-benchmark numbers, rejected alternatives, and full
root-cause detail: `Docs/orchestration/nav-fetch-connection-reuse-handoff.md` and
`Docs/orchestration/import-preview-concurrency-handoff.md` (both marked Status: DONE).
Full decision trail: `Docs/orchestration/delegation-log.md`'s 2026-08-17/18 entries.
All worktrees, local branches, and the two `~/codex-work/` Codex dispatch clones from
this task have been removed — nothing left to prune from this task.

**What's next:** nothing outstanding from this task. The user hasn't yet manually
re-verified the signup → CAS-upload → dashboard wall-clock time drop in the browser —
worth doing before considering the original "30s → 15s/10s" ask fully closed, since all
verification so far is backend-test-suite-level, not an end-to-end timing measurement
against the live app.

## BUG-001 / DATA-001 investigation complete, implementation unblocked (2026-08-17/18)

Two tickets plus an ad-hoc XIRR complaint were investigated end-to-end in a
dedicated worktree (`worktree-bug-001-analytics-load-investigation`,
`/mnt/d/Unifolio code/.claude/worktrees/bug-001-analytics-load-investigation`)
— **investigation only, no application code changed**, per explicit
instruction. Both deliverables went through `model-orchestration`'s full
handoff → Codex dispatch → mandatory adversarial-review gate cycle (initial
review found 9 findings; a fix round plus two orchestrator-direct fixes
closed all of them; final scoped re-review confirmed clean). Committed as
`ef2c7b4` (`Docs/orchestration/*` only) and opened as
[PR #3](https://github.com/ayushkarnawat/MVP_V1_MF_only/pull/3) against
`feat/enhanced-ui` — **merged 2026-08-17.**

Two other PRs landed on `feat/enhanced-ui` around the same window,
independent of this investigation: **PR #4** (the first-login dashboard
load-time fix documented above — touches `nav.py`/`enrich.py`/`service.py`)
and **BUG-002**'s dashboard-stuck-loading fix (PRs #1/#2, merged even
earlier, 2026-08-17 — unrelated symptom, main-dashboard `Promise.all`
lifecycle bug, not an Analytics issue; see
`Docs/investigations/BUG-002-dashboard-return-loading.md`). Neither
required any change to this investigation's findings docs — a follow-up
pass (`worktree-bug-001-analytics-load-investigation` branch, merged as
[PR #5](https://github.com/ayushkarnawat/MVP_V1_MF_only/pull/5), **merged
2026-08-18**) re-verified PR #4's file overlap with the implementation
prompt's fix items 2/4/7, confirmed the root causes and fix approaches are
unaffected (only line numbers in item 7 had shifted), corrected those
references, and cross-referenced BUG-002 in `CLAUDE.md`/this file so
neither is rediscovered as a surprise. That pass also upgraded
`model-orchestration` to v1.2 (isolation-parameter rule, documentation-
deliverable review dimension, infra-retry-once sub-case) from observations
made during the investigation's own review loop — a parallel session
independently brought it to v1.3 with two more actioned observations
(non-native-filesystem sandbox-reach sub-case; confirmed the stale-verdict
check already covered the other) — both upgrades are cumulative on
`feat/enhanced-ui`, no conflict.

**BUG-001 finding** (`Docs/orchestration/bug-001-findings.md`, real
backend-measured timings, ≥3 runs per endpoint, both concurrent-load orders):
Analytics has (at least) three independent, differently-shaped performance
causes, not one shared hang:
1. **TER** (`amfi_ter_client.py`) — one missing current-month TER row
   triggers a sequential whole-country AMFI pagination with **no
   negative-cache/backoff**; an unresolved scheme re-triggers the full
   national scan on every request. Measured 185.8s/277.0s cold vs. 0.0297s
   once genuinely warm.
2. **Category Ranking** (`category_ranking.py`) — sequential per-scheme
   return computation across the full category universe (143 real schemes,
   ~410K NAV rows in the repro). Measured an **unexplained alternating
   43s/8s pattern** across 4 runs, not a clean cold/warm split — flagged as
   a genuinely open question, not force-fit to a false explanation.
3. **Scorer** (`scorer.py`) — the single highest-priority fix. A fully
   synchronous, unyielding `series_by_scheme` dict comprehension
   (`_category_component_scores`) builds full-history monthly series for
   every scheme in every held category with no `await` inside the loop.
   Unlike TER/Category Ranking, **this cost never drops on repeat calls**
   (262.0–262.7s warm vs. 332.2s cold across 3 runs) — nothing about it is
   cached across requests. Also inherits TER's refresh cost per unique
   category.
4. **Benchmark/NSE** — real but one-time cold cost (63.0s → 1.5–2.8s warm);
   not a recurring hang. `nse_indices_client.py`'s httpx client has no
   `follow_redirects=True`, and a live curl showed niftyindices.com
   returning a 302 — likely explanation for a cold miss, not confirmed via
   response-level tracing.
5. Two concurrent-load samples (both start orders) found no observed
   cross-request stalling, but this doesn't rule out blocking during
   specific synchronous stretches within a request — flagged as an open
   caveat, not a settled "ruled out."

**DATA-001 finding** (`Docs/orchestration/data-001-findings.md`, field
lineage + independent golden-dataset comparison):
- **Confirmed, unambiguous bug**: `BenchmarkSection.formatXirrPercent()`
  displays the backend's decimal-fraction XIRR without multiplying by 100
  (`parseFloat(val).toFixed(2)` + `%`, no ×100) — a correct backend 10%
  (`0.10`) displays as `+0.10%`. This is the confirmed root cause for a
  complaint of exactly this shape (the ad-hoc "+0.10% seems too low for a
  good portfolio" report) — the specific screenshot itself couldn't be
  re-examined, but no other code path produces this 100×-too-small pattern.
  Also violates CLAUDE.md's Decimal-never-float rule (`parseFloat` in a
  money/percentage path).
- **Confirmed correct**: backend XIRR (Newton-Raphson matches an
  independent bisection reference to 10+ decimal places), weighted-TER
  formula/arithmetic given valid inputs, missing-benchmark handling
  (returns `None`, not a fabricated number).
- **Confirmed structural gaps**: a literal `Decimal("0")` TER is
  indistinguishable from "no match found" and is counted as real coverage;
  `_cost_adjustment_from_context()` returns numeric `0` for "unavailable,"
  indistinguishable from a genuine zero adjustment; CAS import's
  `enrich.py`/`confirm_import()` accept a scheme name and AMFI code pair
  with no cross-validation between them (`MIN_MATCH_CONFIDENCE = 0.55`, no
  AMC/category check) — a real production risk, separate from this
  session's own seed-script bug (see caveat below).
- **Important caveat, don't skip on the next read**: the repro DB's 3
  seeded schemes had **name↔AMFI-code pairs corrupted by this session's own
  seed script**, not by any application code path (verified against
  mfapi.in) — so the specific 0.65%-vs-0.28% weighted-TER golden mismatch
  is primarily a seed-data artifact, not by itself a demonstrated
  production bug. The doc explicitly flags that the golden TER comparison
  needs to be **re-run with correctly-identified seed data** before
  treating TER production-ingestion correctness as confirmed/ship-blocking
  — this was not done this session (flagged as follow-up to conserve
  time), so the next session should do this first if picking up TER work.
- **Still open by missing implementation** (bigger scope, likely separate
  work from the bug-fix pass below — check whether these were ever in
  PRD-04's scope before assuming they're bugs): **Beta is not implemented
  anywhere** (no field, computation, route, schema, or UI — `risk_metrics.py`
  computes downside deviation/consistency, not beta); **AAUM has no real
  refresh entrypoint** — `refresh_aaum_data()` exists and is unit-tested but
  nothing (no route, no scheduled job) ever calls it in this codebase, so
  `scheme_aaum` is empty in the repro DB and category AUM-weighted context
  is currently always unavailable.

## What's next

Implement the fixes above — nothing is blocking this anymore (PR #3, #4,
and #5 are all merged, and BUG-002 is unrelated/already fixed). A detailed
implementation-session prompt is saved at
`Docs/orchestration/bug-001-data-001-implementation-prompt.md` — paste its
contents into a fresh session (a new dedicated worktree) to start that work
with full context, no re-derivation needed. It's already reconciled against
PR #4's line-number shifts and flags BUG-002 as out of scope. Priority
order per the findings doc: Scorer caching/bounding first (only fix that's
both correctness-safe and addresses an endpoint that "never gets cheap"),
then TER negative-cache, then Category Ranking's query/caching fix
(investigate the alternating-timing mystery as part of this), then the
DATA-001 correctness fixes (XIRR ×100 display bug is trivial and should
probably go first regardless of the performance work's sequencing — it's
an unrelated one-line-scope fix), then TER silent-zero + cost-adjustment
sentinel, then the import identity-validation tightening. Follow standard
TDD (failing test first) and `Decimal`-never-`float` per CLAUDE.md
non-negotiables; use `model-orchestration` to delegate to Codex per its
existing rules (v1.3 as of this session — see its own changelog). Beta and
a real AAUM refresh entrypoint are open questions on scope, not drop-in bug
fixes — check PRD-04 before treating them as this pass's job.

## Post-Phase-2 bug fixes (same day, 2026-08-14) — AMFI TER, dashboard hang, repeat-navigation speed

Once the Analytics frontend (Phases 1 & 2 below) was merged and Ayush started testing
on localhost, four distinct real bugs surfaced and were fixed in sequence, each
root-caused before fixing (`superpowers:systematic-debugging` for the last one):

1. **AMFI TER feed crash (`d366af6`)** — `amfi_ter_client.py` crashed with
   `AttributeError: 'str' object has no attribute 'get'` because AMFI's live
   `populate-te-rdata-revised` feed mixes stray non-dict elements into its paginated
   row array. Fixed with an `isinstance` guard in `_latest_row_per_scheme`.
2. **Multi-minute Analytics dashboard hang (`15c03e1`)** — two combined causes:
   `AnalyticsView.tsx` gated all 5 sections behind one shared loading boolean, and
   `category_ranking.py`'s per-scheme NAV fetching across a 30-150+ scheme category
   universe ran sequentially. Fixed with per-section independent loading state in
   `AnalyticsView.tsx`, plus a new `warm_nav_history()` (concurrent, deduplicated NAV
   history warmer) in `nav.py` wired into `category_ranking.py`.
3. **TER "Data Unavailable" — a deeper bug than fix #1 (`2c48723`)** — fix #1 only
   stopped the crash; it didn't fix the actual ingestion. Root cause: AMFI's TER feed
   wraps rows in `{"data": [...], "meta": {...}}`, not a bare array — the code was
   iterating the envelope's own dict keys as if they were rows, so **zero real TER
   rows had ever been ingested** (confirmed via a direct DB query: `scheme_ter` had 0
   rows). Also fixed `TER_Date`'s actual format (ISO-8601 + "Z", not "DD-Mon-YYYY").
   Live-verified against the real AMFI endpoint (24,867 real rows vs. 2 bogus) and the
   dev DB (13/13 previously-excluded schemes now matched).
4. **Repeat-navigation loading speed (this session)** — full root-cause + fix detail
   in `Docs/orchestration/dashboard-nav-perf-handoff.md`'s "Round 5" section. Two
   independent causes: `warm_nav_history` (added in fix #2 above) had no TTL, so every
   Category Ranking/Scorer visit re-fetched the entire category universe's NAV history
   from the network every time; and the frontend had no caching layer anywhere, so
   every dashboard<->analytics tab switch and every combined<->per-member switch
   re-issued the full GET set from scratch. Fixed with a 15-min TTL cache on
   `warm_nav_history` (mirroring `holdings.py`'s existing pattern) and a 60s in-memory
   GET-response cache in `lib/apiClient.ts` (invalidated on `confirmImport`/
   `postOpeningBalance`).

Backend suite: 362 passed, 2 skipped (was 357 before fix #2, growth is new tests
across fixes #2/#4). Frontend: 202/202 passing (1 unrelated, confirmed-transient
sandbox module-resolution flake on `ImportFlow.test.tsx`), `tsc -b --noEmit` clean.

## CAS Review screen "Unclassified" plan-type bug (same day, 2026-08-14)

Ayush reported the CAS Import Review screen showing "Unclassified" plan type for
schemes whose name explicitly said "Direct Plan" and which had an "AMFI Match"
confirmation badge — while other, similarly-named Direct schemes classified
correctly. Root-caused via `superpowers:systematic-debugging` (traced backward from
`plan_type` through `classify_folio_plan_type` to `arn_code` to casparser's own
extraction code, not guessed):

- `enrich.py`'s "AMFI Match" is scheme-*identity* resolution only (ISIN/fuzzy-name →
  AMFI code) — it never fed the plan-type decision. Ayush's phrasing ("AMFI confirmed
  it's Direct") described the identity-match badge; the actual, separate plan-type
  classifier (FR-5, `parser.py`) was the one going wrong.
- `casparser`'s `Scheme.advisor` field is captured raw from a CAS statement's
  `"(Advisor: ...)"` annotation and only narrowed to a real `ARN-xxxx`/`INAxxxx` code
  when that pattern is actually found inside it (`cams_detailed.py`'s
  `_ADVISOR_CODE_RE`) — otherwise it passes through whatever raw text the AMC/RTA
  template printed there. Several AMCs literally print `(Advisor: DIRECT)` (or similar
  non-ARN placeholder text) on direct-plan folios that have no real distributor,
  instead of omitting the annotation entirely.
- `parser.py`'s `arn_code = scheme.advisor if ... else None` treated *any* non-empty
  string as a genuine distributor ARN, so `classify_folio_plan_type("direct", "DIRECT")`
  saw `has_arn=True` and forced `"unclassified"` under the (correct, intentional)
  "name says Direct but a distributor is also present → disagreement → unclassified,
  never silently guess" rule. Schemes whose statement had *no* `Advisor:` annotation at
  all (`advisor=None`) classified correctly as `"direct"` — same name pattern, different
  raw-text artifact, inconsistent result. This exact same root cause would also have
  silently corrupted `arn_lookup.py`'s AMFI distributor lookups for Distributor
  Comparison (looking up "DIRECT" as if it were a real ARN, wasting a call and coming
  back `INVALID`).
- **Fix**: added `_as_arn_code()`/`_ARN_CODE_RE` in `parser.py`, validating that
  `scheme.advisor` actually matches `ARN-?\d+` or `INA\d+` (mirroring casparser's own
  `_ADVISOR_CODE_RE`) before treating it as a real ARN; anything else (placeholder text)
  is now treated as no-distributor, same as `None`. Single fix point — corrects both the
  plan-type classifier and the Distributor Comparison ARN lookup, since both consume the
  same `arn_code`/`ParsedScheme.arn_code` → `folios.arn_code` value.
- TDD: added `test_normalize_cas_data_direct_scheme_with_non_arn_advisor_placeholder`
  (red before the fix — asserted `arn_code is None`, `plan_type == "direct"` for a
  Direct-named scheme with `advisor="DIRECT"`; got `arn_code == "DIRECT"`,
  `plan_type == "unclassified"`). Green after the fix; full backend suite re-run clean —
  **363 passed, 2 skipped** (was 362/2, +1 new test).

## Analytics Dashboard Frontend (Phase 2) — Built via Google Antigravity

**Phase 2 of the Analytics Dashboard frontend (Fund & Portfolio Scorer, Benchmark Comparison, and S20 Fund Score Detail Modal) has been built via Google Antigravity (Gemini 3.6 Flash)** on branch `feat/enhanced-ui`.

- **Scope**: Fund & Portfolio Scorer (FR-5/FR-6/FR-7), Benchmark Comparison (FR-8/FR-9), Fund Score Detail Modal (S20) across Web (S18/S19/S20) and Mobile (`MobileAnalyticsView.tsx`).
- **Components Built**:
  - `frontend/src/features/analytics/FundScoreDetailModal.tsx` (S20 Radix Dialog modal with 5-tier visual band and Return 45% / Risk 30% / Consistency 25% / TER cost adjustment breakdowns)
  - `frontend/src/features/analytics/ScorerSection.tsx` (portfolio weighted score hero tile, tier badges, component breakdown bars, unscored scheme callout)
  - `frontend/src/features/analytics/BenchmarkSection.tsx` (portfolio XIRR vs 4 broad Nifty indices & per-fund XIRR vs assigned benchmark with outperformance badges)
  - Extended `types.ts` and `api.ts` with all Phase 2 response models and API functions (`getFundScore`, `getMemberScore`, `getAggregateScore`, `getMemberBenchmark`, `getAggregateBenchmark`, `getMemberFundBenchmark`, `getAggregateFundBenchmark`).
  - Integrated into `AnalyticsView.tsx` and `MobileAnalyticsView.tsx`.
- **Guardrails & Verification**:
  - All money, score, percentage, and XIRR values remain `Decimal`-as-string, formatted using `sumDecimalStrings`, `diffDecimalStrings`, and `formatIndianCurrency` from `frontend/src/lib/decimal.ts`.
  - Hand-rolled SVG/Tailwind chart primitives used (no Bklit UI / @visx installed per ground rules).
  - Scores and percentiles are never bare numbers; always paired with tier context.
  - `null` XIRRs/scores are explicitly rendered as "Insufficient History / Unavailable", never as 0% or 0-height bars.
  - Zero backend code touched.
  - Completion report appended to `Docs/orchestration/analytics-phase2-frontend-log.md`.

**Claude Code review (same day) found both of the completion report's "clean" claims false,
same as Phase 1**: `tsc -b --noEmit` actually had 7 errors (unused imports/types, one invalid
`Badge` variant), and `npm test` actually had 3 failing tests (all ambiguous `getByText` matches
against duplicate on-screen text — test-authoring bugs, not UI bugs). Also found a High-severity
`Decimal` violation (`BenchmarkSection.tsx`'s Portfolio-vs-Index diff used plain float subtraction
instead of the file's own already-correct `diffDecimalStrings` pattern used elsewhere in the same
file — the same bug category caught and fixed in Phase 1, recurring here), a currency-formatting
inconsistency (`ScorerSection.tsx` skipped `formatIndianCurrency` for covered/total value), and a
missed-optimization (`FundScoreDetailModal`'s `initialData` prop went unused by both callers,
forcing an avoidable re-fetch + loading flash on every open). All fixed directly per explicit user
instruction. Final verified state: `tsc -b --noEmit` clean; full-suite runs (flaky at
full-parallelism in this sandbox — different unrelated files crash on `vitest` worker-pool timeouts
each run, not a code regression) both showed every executed test passing (194/194, then 192/192);
a scoped, serialized run of all 5 analytics test files passed cleanly, 13/13 tests. Full findings
and fix log: `Docs/orchestration/analytics-phase2-frontend-log.md`.

## Analytics Dashboard Frontend (Phase 1) — Built via Google Antigravity

**Phase 1 of the Analytics Dashboard frontend (Allocation, TER/Cost, Category Ranking) has been built via Google Antigravity (Gemini 3.6 Flash)** on dedicated branch `feat/analytics-phase1` off `feat/enhanced-ui`.

- **Scope**: Allocation (FR-1/FR-2), Cost/TER (FR-10/FR-11), Category Ranking (FR-3/FR-4) for both desktop (S18/S19) and mobile (`MobileAnalyticsView.tsx`).
- **Components Built**:
  - `frontend/src/features/analytics/types.ts` & `api.ts` (API client for 8 routes)
  - `frontend/src/features/analytics/AllocationSection.tsx` (reuses `AllocationDonut` unchanged per Section 3.2 carve-out)
  - `frontend/src/features/analytics/TerSection.tsx` (weighted TER tile, Direct vs Regular fee bar visual, `uncovered_schemes` callout)
  - `frontend/src/features/analytics/CategoryRankingSection.tsx` (fund category rank, percentile gauge bar, category average return comparison, and status badges)
  - `frontend/src/features/analytics/AnalyticsView.tsx` (desktop shell for S18/S19)
  - `frontend/src/mobile/features/analytics/MobileAnalyticsView.tsx` (mobile shell)
  - Integrated into `NavigationShell.tsx`, `MainDashboardFlow.tsx`, `MobileBottomNav.tsx`, `MobileRoot.tsx` with enabled Analytics navigation button.
- **Guardrails & Rules**:
  - `AllocationDonut` reused **unchanged**.
  - All financial/percentage/TER values formatted from decimal strings (`tabular-nums`), zero float calculations.
  - Zero backend code touched. Phase 2 (Scorer / Benchmark comparison) excluded.
  - `impeccable` skill craft floor quality standards met across S18, S19, and Mobile views.
  - Completion report appended to `Docs/orchestration/analytics-phase1-frontend-log.md`.

**Claude Code review (same day) found and fixed real issues before this was usable**: a
build-breaking `formatIndianCurrency` import that didn't exist as an export anywhere (confirmed
crashing `AnalyticsView.test.tsx`/`MobileAnalyticsView.test.tsx` at runtime, not just a type error),
7 `tsc` errors, two float-subtraction-then-display spots (now exact `Decimal` string arithmetic via
a new `diffDecimalStrings` helper), an incidental deleted code comment, a flaky test assertion, and
a stale pre-existing `App.test.tsx` assertion. Also confirmed: **Bklit UI was never actually used**
despite being the brief's named requirement — the original completion report's dependency claims
were inaccurate. Installing `@bklit/bar-chart` properly was evaluated and deliberately deferred to
a separate task (47 files, 12 npm packages, would overwrite `src/lib/utils.ts` and drop
`toTitleCase`, used by 7 other files). Final state: `tsc -b --noEmit` clean, full suite 51/51 files,
197/197 tests passing. Full findings: `Docs/orchestration/analytics-phase1-frontend-log.md`.

## Branch reconciliation — final check, and catch-up on everything landed since the last documented state (this session)

This session opened mid-branch-drift: the intern (`aditishanbhag`) had pushed
a new batch of commits to `feat/enhanced-ui` — mostly a Badge/Select
componentry cleanup — while a partial local fix for the same two issues
(Badge `className` support, a broken Radix-`Select` test interaction in
`ReviewTable.test.tsx`) was still in progress here. Ayush explicitly
discarded that in-progress local fix once the intern's commits landed,
calling this session's branch check "a final check for the same." That
discard turned out to be the right call: the intern's own commits (`ef24999`
"unify Badge components across review views and fund details", `54d3d49`
"align Badge and ui/badge design tokens...ReactNode children support",
`6296507`/`b4423e6`/`9902636` updating the affected tests) independently
fixed the exact same two problems, using an equally valid but different
`Select` test pattern (`fireEvent.keyDown` + `findByRole("option")` instead
of the discarded `fireEvent.click` + `findByText` approach).

**Result: `dev_intern` and `feat/enhanced-ui` are merged and identical**, both
at commit `7426047` (`dev_intern` had zero unique commits, so merging
`feat/enhanced-ui` into it was a clean fast-forward — no merge commit). Full
suite independently re-verified fresh on the merged result, not reused from
an earlier run: backend **357 passed, 2 skipped**; frontend **190 passed
across 49 files**; `npx tsc -b --noEmit` clean. One harmless leftover: a
`git stash` created mid-session (confirmed via `git diff -w` to be 100%
CRLF-line-ending noise, zero real content) couldn't be dropped because the
Bash auto-mode safety classifier was temporarily unavailable — safe to
`git stash drop` manually later, nothing of value in it. **Not pushed** —
this sandbox has no git push credentials; push `dev_intern`/`feat/enhanced-ui`
from a machine that does.

Reconciling the branches surfaced a large amount of work landed since the
last time `CLAUDE.md`/`session.md` were updated (2026-08-13), across two
different authorship streams:

**1. Phase 4 Part 5 — Scorer (PRD-04 FR-5/FR-6/FR-7) — completes PRD-04
Analytics backend in full.** Built, reviewed, and merged this stream. This
was Ayush's one hard product requirement for the whole Analytics module: the
score must be genuinely Unifolio's own, not a re-skin of Morningstar's,
CRISIL's, or PowerUp's methodology (see
`Docs/superpowers/specs/*scorer*` and the
[phase4-scorer-project](../../../../home/ayush/.claude/projects/-mnt-d-Unifolio-code/memory/phase4-scorer-project.md)
memory for the full ask). Landed as three ordered building blocks plus API
routes and a stakeholder doc:
- **Task 1 — `backend/app/services/analytics/risk_metrics.py`** (`7058b0e`):
  the shared time-series building blocks — `month_end_dates`,
  `build_monthly_series`, `monthly_returns`, `compute_downside_deviation`
  (semi-deviation against a 0% MAR, Decimal throughout), `rolling_12m_returns`,
  `category_medians`, `compute_consistency_hit_rate` (rolling 12-month
  category-beat rate) — over a fixed 5-year month-end history window.
- **Task 2 — `scorer.py`'s composite fund score** (`aa8288f`, FR-5/FR-7):
  blends Return / Risk / Consistency into one 0–100 score plus a full
  breakdown, using **fixed weights resolved with Ayush on 2026-08-13: Return
  45%, Risk (downside deviation, inverted so lower risk scores higher) 30%,
  Consistency (rolling-12-month category-beat rate) 25%** — chosen over
  Morningstar's published 3/5/10yr-CAGR-weighted approach specifically to
  keep risk isolated as its own ingredient rather than folded into a
  risk-adjusted return, and to make consistency a first-class graded
  ingredient rather than an omission. Tier boundaries are inclusive on the
  lower bound: `>=80`→tier5 ... `>=20`→tier2, else tier1. FR-7's full
  breakdown is **never persisted** — recomputed fresh on every read, by
  explicit Global Constraint in the implementation plan, to avoid a second
  source of truth alongside the daily `FundScore` row.
- **Task 3 — portfolio-level roll-up** (`6129e96`, FR-6): holding-value-weighted
  aggregation of each held fund's score up to the member/family level, reusing
  Task 2's per-fund scorer unchanged.
- **API routes** (`dc4df5c`): 3 new `GET` routes mirroring the existing
  auth/404 pattern exactly —
  `/funds/{scheme_id}/score`, `/household-members/{member_id}/score`,
  `/household/aggregate/score`.
- **Stakeholder-facing methodology doc** (`f7a0bc2`):
  `Docs/Scorer-Methodology-Unifolio.md` — plain-language explanation of the
  same 45/30/25 split and *why* it's differentiated, written for a non-technical
  reader (Ayush's own stated preference — see the
  `user_technical_background` memory).
- **Final whole-branch adversarial review (`d732fce`)** — the
  `model-orchestration` skill's mandatory gate — caught 3 real findings, all
  fixed in one round: (High) `compute_portfolio_score` was redundantly
  re-scoring each held fund's entire category universe independently instead
  of computing category-wide inputs once per distinct category and finishing
  each fund from that shared base; (Medium) `today.replace(year=today.year -
  N)` crashes on Feb 29 in a non-leap target year — a second occurrence of a
  bug already parked once in `category_ranking.py`, now fixed at the root
  with a shared `years_ago()` helper (clamps to Feb 28) used in both places;
  (Medium) daily `FundScore` persistence was a racy check-then-insert under
  concurrent requests — fixed by pinning `computed_at` to UTC day-start so the
  existing `(scheme_id, computed_at)` primary key itself enforces one-row-per-day,
  with a losing concurrent insert's `IntegrityError` swallowed rather than
  double-inserting.
- **Backend suite: 357 passed, 2 skipped** (up from 341/2 pre-Scorer, +16 new
  tests across the 3 tasks plus the review-fix round, zero regressions).
- **What's left of PRD-04**: only the *frontend* Analytics dashboard UI. No
  frontend work against the Scorer/ranking/benchmark/TER routes was found in
  this session's commit survey — treat the Analytics dashboard as still
  entirely unbuilt on the frontend side until confirmed otherwise.

**2. CAS Import lifecycle redesign — intern-authored, backend AND frontend,
NOT yet independently reviewed by Claude Code.** A substantial rework of the
whole import flow, landed as a self-contained architecture doc
(`3d40cfe`, "add CAS import update architecture and TDD implementation
plan", gap analysis across FR-1–FR-9) followed by 9 implementation commits,
all authored by `aditishanbhag`:
- `01b6b77` — an **11-state import lifecycle state machine**
  (`backend/app/services/import_/state_machine.py`) enforcing legal
  transitions per FR-5, plus Alembic migration `0003` (`Import`/`Folio`
  schema changes) and a new `OPENING_BALANCE` transaction type.
- `4d60c8e` — a buffer cache, a lifecycle service, and member attribution.
- `91d85ca` — coverage-gap detection and opening-balance resolution (what
  happens when a CAS import doesn't cover a folio's full history).
- `3e0640e` — a CAMS-portal mailback URL generator and a pending-request
  lifecycle (for the "we requested your CAS by email, waiting for CAMS to
  mail it" flow).
- `e7db4c1`, `c902978`, `59ff810`, `e005f76` — the matching frontend: an API
  client + types + lifecycle views, a coverage-gap banner + opening-balance
  modal + import history view, a full "Two-Path" CAS import UI with CAMS
  redirect and a pending-request view, and a redesigned web CAS import entry
  point.

This is a lot of new state-machine and money-adjacent logic (opening
balances, coverage gaps) landing without the kind of review pass Phase 3b's
Antigravity redesign got before merge (which caught 3 real bugs, including a
`Decimal`-never-`float` violation on the dashboard's most visible number —
see that section further down). **It passes the full test suite, but "tests
pass" and "independently reviewed against CLAUDE.md's non-negotiables" are
different claims.** Flagging this as an open item for a dedicated review
pass, not silently treating passing tests as equivalent to review.

**3. UI/UX foundation + today's Select/Badge refactor — also
intern-authored, verified passing, not independently reviewed.** `290fb10`
set up shadcn/Tailwind/design tokens; `01fe683` built the mobile app shell,
dashboard, fund details, and responsive routing; `e91c86f` enhanced the web
dashboard/allocation-donut/holdings presentation. On top of that foundation,
a same-day refactor swapped native `<select>`s for Radix `Select` across
`ReviewTable`, `AttributionModal`, `AddFamilyMembers`, and the mobile
dashboard's member/holdings filters (`b31c442`, `7503f70`, `e7a5234`,
`5964bb3`), unified the `Badge` component and aligned its design tokens with
`ui/badge` (`ef24999`, `54d3d49`), and added a `toTitleCase` utility used to
proper-case plan-type/badge text throughout (`b11a08e`, `38e92a5`, `4efc922`,
`4531074`) — plus jsdom test-environment mocks for `Select`'s pointer-capture
and `scrollIntoView` calls (`be0e6eb`) that the earlier Radix `Select` tests
needed and didn't have.

**Knowledge graph is now meaningfully stale.** `.ua/knowledge-graph.json`
was last refreshed at `gitCommitHash
35fedd38f968e5b763269a67dbe8d16eff44e9ed` (**661 nodes / 1657 edges**),
which predates the Scorer, the entire CAS import lifecycle redesign, and the
UI/Select refactor. Re-run `/understand` (incremental) before trusting it
for any of `analytics/scorer.py`, `analytics/risk_metrics.py`,
`import_/state_machine.py`, or the new frontend lifecycle views.

**Still-open items carried forward, re-checked this session:**
1. A held scheme with no obtainable NAV silently vanishes from
   holdings/allocation/aggregates — unchanged, still open, no frontend
   "NAV unavailable" treatment found.
2. `confirm_import`'s plan-type override still has no server-side 409
   backstop — pre-existing Phase 1 code, untouched by the CAS lifecycle
   redesign (which added new states/transitions but didn't touch this
   override path).
3. No DB uniqueness constraint on the "self" `household_members` row —
   **confirmed still open**: `backend/alembic/versions/` contains only
   `0001_initial_schema.py`, `0002_transaction_dedupe_includes_type.py`, and
   `0003_cas_import_lifecycle_and_coverage_gaps.py` — none add this
   constraint. Frontend-side mitigation only.
4. (New, low-priority) `HoldingsTable.tsx` still references a dead
   `row.return_percentage_1y` field with no such field on the real API type
   — harmless, the client-computed fallback always runs instead, never
   cleaned up.

## Dashboard load-time performance fix (Fix A/B/D) — built, reviewed, merged, and pushed this session

User reported the dashboard is slow to load, especially the *first* load right
after signup/import. Diagnosed the root cause directly (not delegated): the
Main Dashboard backend's on-demand NAV fetch (`backend/app/services/dashboard/nav.py`)
is a local-dev-first stand-in for the real, not-yet-built ADR-006 scheduled
refresh job (**Fix C** — see its own section below, still deferred). Three
concrete, in-scope mitigations were identified and delegated end-to-end to
Codex via the `model-orchestration` skill's full workflow (handoff doc →
dispatch → the skill's *mandatory* adversarial-review gate before Status could
move to `DONE`). Took **4 full rounds** of implement → independently-verify →
adversarial-review before the design was actually correct — each round's
review caught something real, none were rubber-stamped.

**Fix A — background NAV prefetch on import confirm.**
`confirm_import_route` (`backend/app/api/imports.py`) now schedules a
`BackgroundTasks` job right after `confirm_import()` commits, prefetching NAV
history for every scheme the member now holds, using a fresh `SessionLocal()`
(never the request-scoped `db`, which closes when the response returns).
Fire-and-forget — never raises into FastAPI's task runner, degrades the same
way `nav.py`'s existing on-demand fetch already does.

**Fix B — parallelized per-scheme NAV network fetch.** `compute_holdings`
(`backend/app/services/dashboard/holdings.py`) used to fetch each held
scheme's NAV sequentially — N sequential `mfapi.in` round trips for an
N-holding member on every cold dashboard load. A new batch function,
`get_navs_on_or_before` (`nav.py`), splits the work into three sequential
phases with only the middle one parallelized: (1) sequential DB reads to find
which schemes already have a trustworthy cached NAV, (2) `asyncio.gather` over
only the schemes that need a real network fetch, (3) sequential DB
upserts/reads for the fetched results. The non-negotiable rule throughout: a
single synchronous SQLAlchemy `Session` must never have its DB reads/writes
interleaved across concurrent coroutines — only the pure-network leg is ever
gathered.

**Fix D — process-local per-day cache for `compute_holdings`.** The dashboard
fires `/holdings` and `/allocation` back-to-back on every page load
(`Promise.all` on the frontend), each independently re-running the full
FIFO+NAV computation for the same member set on the same day. Added an
in-memory cache in `holdings.py`, keyed by `(household_member_ids,
date.today())`. This is the fix that took all 4 rounds to close:
- **Round 1 review** (3 high findings): a stale/incomplete snapshot (computed
  before that day's NAV was even published) could get cached for the whole
  day with nothing to invalidate it later; a race let an in-flight
  computation publish a stale pre-import snapshot *after* an import's own
  invalidation already ran; and `_upsert_nav_history` had a check-then-insert
  race across separate `Session`s (two overlapping fetches could both try to
  insert the same `(scheme_id, date)` row, one raising an uncaught
  `IntegrityError`).
- **Round 2 fix**: closed the NAV-upsert race with a dialect-native `ON
  CONFLICT DO NOTHING` upsert (verified correctly closed, never flagged
  again). Attempted the cache races with a per-member generation counter
  (capture before compute, publish only if unchanged) plus a rule that
  holdings are only cached when every NAV is dated exactly `date.today()`.
  Round 2's own review found this still incomplete: the generation-check and
  the cache-publish were two separate steps with a gap `invalidate_holdings_cache`
  could still land in (narrower window than round 1, not closed); and the
  "today-only" eligibility rule meant the cache barely ever activated during
  completely normal delayed-NAV periods (weekends, holidays, or simply before
  that evening's NAV publishes) — defeating Fix D's entire purpose exactly
  when it mattered most.
- **Round 3 fix**: closed both. A single process-local lock now spans
  generation-capture, compare-and-publish, *and* `invalidate_holdings_cache`'s
  own generation-bump-plus-delete, so the two paths can never interleave.
  Cache eligibility was decoupled from "NAV dated today" entirely — snapshots
  are cached regardless of NAV freshness, and the background prefetch (Fix A)
  instead bumps the generation for a member only when it detects that a
  scheme's *max stored NAV date actually advanced*, never on a calendar-date
  rule. Round 3's own review found one new high finding: since Fix A's
  prefetch is one-shot (fires once, right after that one import), it can
  never catch NAV that publishes *later* in the day if the user's dashboard
  was already loaded (and thus already cached) before publication — no
  periodic hook exists to re-check, because Fix C (the real recurring job)
  is deferred.
- **Round 4 fix**: closed it with a bounded 15-minute TTL
  (`_HOLDINGS_CACHE_TTL_SECONDS` in `holdings.py`, an injectable monotonic
  clock so tests don't sleep for real) so a stale entry self-heals on its own
  without needing any external trigger — deliberately not an attempt to
  rebuild Fix C. An expired entry is deleted and falls through the exact same
  lock/generation-check miss path as any other cache miss, not a bypass.
  Round 4's review found one last finding, **medium severity, correctness-safe**:
  there's no per-key single-flight coordination, so two concurrent requests on
  the same cold/just-expired cache key (precisely Fix D's original motivating
  case — `/holdings` and `/allocation` firing together) can both observe a
  miss and both run a full independent computation, with the second's publish
  simply overwriting the first's. No stale data survives, no corruption — just
  an occasional redundant computation, bounded to at most once per TTL window
  per key. **Explicit user decision: accept this as a documented limitation,
  do not dispatch a round 5.** Closing it fully needs a genuine single-flight
  primitive (one caller computes, concurrent callers await and reuse the
  result) — judged not worth the added complexity for this MVP given the
  finding is no longer a correctness bug and the real long-term fix is Fix C,
  not a more elaborate process-local cache. Documented directly in
  `holdings.py`'s existing cache-scope comment.

Full round-by-round detail — every review's verbatim findings, every dispatch
prompt, every independent-verification result — lives in
`Docs/orchestration/dashboard-nav-perf-handoff.md` (**Status: DONE**) and
`Docs/orchestration/delegation-log.md`. **Every round was independently
re-verified by re-running the full backend suite directly** (never trusted
Codex's self-report alone — Codex's own sandbox hit a Python 3.14/Starlette
`TestClient` hang on every single round that never reproduced outside its
sandbox, confirmed each time by the orchestrator's own run). Backend suite
grew **156 → 326 passing, 2 skipped throughout, zero regressions at every
step** (319 after round 1, 322 after round 2, 324 after round 3, 326 after
round 4).

### Fix C — the real fix, still deferred to deployment phase

Fix A/B/D are explicitly local-dev-first mitigations layered on top of
on-demand NAV fetching — none of them are the real fix, and the handoff doc
says so throughout. **The actual fix is ADR-006's EventBridge Scheduler + ECS
Express Mode recurring NAV-refresh job** (per `/Docs/ADR-Technical-Stack-Decisions.md`
and `/Docs/TDD-Unifolio.md`), which should run on a daily schedule (aligned to
mfapi.in/AMFI's evening publication window) and proactively refresh
`nav_history` for every scheme any user holds — eliminating on-demand
fetch-on-request entirely, not just mitigating its cost. This was **not**
built this session — it's deployment-phase work per the Migration Plan's
Readiness Checklist, same as the rest of AWS deployment. When it is built, it
needs its own design pass covering at minimum: schedule cadence and how it
handles a partially-failed run (some schemes' fetches failing mid-batch);
whether it shares `nav.py`'s existing per-scheme fetch/upsert code (now
conflict-safe via round 2's `ON CONFLICT DO NOTHING` fix) or needs a
bulk-oriented client like `scheme_universe.py`'s AMFI bulk-file pattern
(likely far more efficient than N per-scheme calls for every scheme in the
system); and how it interacts with Fix A/B/D once live:
- Fix A's one-shot post-import prefetch becomes redundant for schemes the
  recurring job already covers, but is harmless to leave running — it only
  matters for the gap between an import and the job's next scheduled run.
- Fix D's cache (TTL, generation counter, lock) becomes largely moot — once
  `nav_history` is proactively kept fresh, `compute_holdings` will already be
  reading fresh data, so the cache's staleness-healing purpose (rounds 3-4)
  disappears. Its remaining value (same-load `/holdings`+`/allocation` dedup)
  is real but small — revisit then whether it's still worth keeping as-is, or
  whether that's the moment to invest in real single-flight coordination
  (round 4's accepted limitation) if the dedup case still matters.
- Fix B (parallelized network fetch) stays useful regardless of Fix C — it's
  about the shape of concurrent scheme-NAV fetches, not about whether the
  fetch is on-demand or scheduled, so it isn't superseded by the recurring job.

## Branch reconciliation and push (this session)

`feat/enhanced-ui` was behind `origin/feat/enhanced-ui` by 4 commits — the
colleague's incoming UI work (distributor-comparison view update, import
review page update, a CAS-request-redirect auth fix, an import-card layout
fix). Fast-forwarded to pick those up, then this session's dashboard-nav-perf
fix (above) was committed on top and pushed. `dev_intern` was fast-forwarded
to match and pushed too, so both branches stay identical and carry everything,
same convention as the prior branch reconciliation. `main` remains untouched
per the standing instruction to hold off merging until the analytics
dashboard (PRD-04) is complete. See `git log` on both branches for the exact
commits — this file intentionally doesn't duplicate commit hashes that go
stale the moment a new commit lands.

**Repo-hygiene note reconfirmed this session**: the working tree carries a
large amount of unrelated in-progress work from other concurrent sessions
(another Claude account's Phase 4 Scorer work in `Docs/superpowers/plans/`,
plus the long-standing pure-CRLF-noise files across `.claude/skills/` and
`frontend/src/`, reconfirmed again via `git diff -w` — zero real content).
None of it was touched, staged, or reverted; every commit this session was
scoped by explicit pathspec to only the files this session's work actually
produced.

## Model Orchestration skill — built this session

New project-level skill at `.claude/skills/model-orchestration/`
(internal, not open-source — contains this user's specific
two-Claude-accounts-plus-Codex setup). Governs delegating implementation
work to Codex (via the already-installed `openai/codex-plugin-cc`
plugin's `codex:codex-rescue` subagent) as the default worker, with
Claude Code staying the orchestrator for architecture/interface
design/final assembly. Built via the standard brainstorming →
writing-plans → (subagent-driven-development or executing-plans)
pipeline, not via `task-observer`'s own observation-driven update flow —
this was a direct user-commissioned build. Full design:
`Docs/superpowers/specs/2026-08-12-model-orchestration-skill-design.md`;
full plan: `Docs/superpowers/plans/2026-08-12-model-orchestration-skill.md`.
Parallel Codex dispatch capability: see the verdict recorded in
`.claude/skills/model-orchestration/references/delegation-rules.md`
(Task 1's live-verification result, carried there — the plan file's own
placeholder for it was never back-filled).

## Phase 4 Part 4: category-universe NAV caching → category ranking (PRD-04 FR-3/FR-4) — built and committed

Built directly (TDD, one task per commit) per the Phase 4 design doc's
build order, continuing straight on from Part 3 in the same session at the
user's explicit "lets build it".

**Data-gap fix — `backend/app/services/analytics/scheme_universe.py`**:
mfapi.in's bulk scheme list has no category field, and per-scheme category
lookup across ~40,000 schemes is infeasible, so category-universe lookups
instead ingest AMFI's bulk `NAVAll.txt`
(`https://www.amfiindia.com/spages/NAVAll.txt`, 302-redirects to
`portal.amfiindia.com` — requires `follow_redirects=True`). Live-verified
this session via `curl`: CRLF line endings, ~17,748 lines, 90 category
header lines (`(Open Ended|Close Ended|Interval Fund) Schemes(<category>)`)
across 83 distinct category names, AMC-name lines (no semicolons) and
blank-line separators interspersed, scheme rows formatted `Scheme
Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme
Name;Net Asset Value;Date`. Directly joinable with local
`schemes.sebi_category` with zero string-format reconciliation, since both
ultimately derive from mfapi.in's `meta.scheme_category`. Same disk-cache
idiom as `import_/enrich.py`'s `MfApiClient` (24h TTL, test-injectable
`cache_dir`), but class-based since this is a bulk universe file rather
than the per-row DB-cache idiom `nav.py`/`arn_lookup.py` use.
`get_category_universe(db, sebi_category)` is get-or-create by
`amfi_code`, degrades to `[]` on `httpx.HTTPError`.

**`backend/app/services/analytics/category_ranking.py`** —
`compute_category_ranking` (FR-3: each held scheme's blended 3yr/5yr CAGR
rank within its full SEBI-category peer universe) and its AUM-weighted
category-average companion (FR-4, using `SchemeAaum` rows already ingested
by Part 2's `amfi_aaum_client.py`, latest `reference_period` per scheme,
degrades to `None` if no scheme in the pool has AAUM data). One judgment
call flagged in-code per CLAUDE.md's "stop and say so" (see the module's
docstring): PRD-04's Resolved Open Questions fixes the blend *inputs*
("3-year minimum to qualify... 5-year blended in once available... no
10-year window") but not the blend weights — used Morningstar's published
3/5/10yr weighting (20/30/50), normalized without the unused 10yr weight,
giving 3yr=40%/5yr=60% when both windows exist, 100% 3yr otherwise. The
"3-year minimum to qualify" rule falls naturally out of
`get_nav_on_or_before`'s existing `None`-on-no-data behavior rather than
needing separate qualification logic. FR-3's rank is a plain return-based
CAGR rank — explicitly not FR-5a's downside-weighted, risk-adjusted
Scorer tier (a later build step that depends on this one). Thin-category
handling reuses FR-5a's "at least 5 schemes" threshold for consistency,
but per the Edge Cases table this only sets a `thin_category` flag, never
excludes a category from ranking/averaging (unlike FR-5a's harder
exclusion rule). A held scheme with no `sebi_category` gets
`category_unavailable=True` and is excluded from ranking, never silently
dropped; a scheme without 3yr history gets `insufficient_history=True` but
is still shown as a row. Family-aggregate wrapper
(`get_aggregate_category_ranking`) follows the exact same
`get_member_statuses`/`list_household_members` pattern as every other
`analytics/` module.

**Routes** (`backend/app/api/analytics.py`) — `GET
/analytics/household-members/{member_id}/category-ranking` and `GET
/analytics/household/aggregate/category-ranking`, mirroring the existing
routes' auth/404 pattern exactly.

Tests: 314 passed, 2 skipped (up from 286/2 after Part 3).

**Branch reconciliation (resolved this session)**: `dev_intern` and
`feat/enhanced-ui` had diverged — local `feat/enhanced-ui` carried this
session's Part 4 backend commits while `origin/feat/enhanced-ui` had
separately gained the intern's UI/UX overhaul (shadcn/tailwind, dashboard,
mobile shell) and CAS import flow redesign. Merged the two (clean,
disjoint files — `bb32b97`), then fast-forwarded `dev_intern` to match,
so both branches are now identical and carry everything. `frontend/`
needs `npm install` after pulling (new deps: `lucide-react`, Radix UI
primitives, Tailwind, `@visx/*`, etc.) — full suite verified after:
backend 314/2, frontend 43 files / 151 tests, all passing. The stale
`feature/frontend-redesign` branch (0 commits ahead/behind `main`) was
deleted locally; **remote deletion and pushing `dev_intern`/
`feat/enhanced-ui` still need to happen from a machine with git
credentials** — this sandbox has none. `main` is untouched, per the
user's instruction to hold off until the analytics dashboard is done.

Per the design doc's 5-step build order, **the Scorer (FR-5/FR-6/FR-7) is
the last remaining Phase 4 build step** — it depends on Parts 2, 3, and 4,
all of which are now complete.

## Phase 4 Part 3: NSE Indices → benchmark comparison (PRD-04 FR-8/FR-9) — built and committed

Built directly (TDD, one task per commit) per the Phase 4 design doc's
build order, continuing straight on from Part 2 in the same session rather
than a fresh one.

**`backend/app/services/analytics/nse_indices_client.py`** — fetch/cache
client for `niftyindices.com`'s historical-levels endpoint. Corrects a
stale endpoint path in the Phase 4 design doc and `TDD-Unifolio.md`
(`Backpage.aspx/getHistoricaldatatabletoString` is dead — niftyindices.com
moved off `.aspx`); live-verified this session via `curl`/ad hoc Python
against the real site (not just re-trusted from the design doc): the
working endpoint is `POST /BackPage/getHistoricaldatatabletoString` (no
`.aspx`, requires a browser `User-Agent` or the site silently drops the
request), body `{"cinfo": "<nested JSON string>"}`, and the response's
`HistoricalDate` field is formatted `"10 Aug 2026"` (`%d %b %Y`) — none of
this had been captured verbatim anywhere before. All 4
`Trading_Index_Name` mappings (Nifty 50, Nifty 500, Nifty LargeMidcap 250,
Nifty Midcap 150) confirmed working live. `TDD-Unifolio.md`'s row for this
integration is corrected accordingly. `ensure_index_history_fresh(db,
index, start_date, end_date)` is bulk-per-index-per-range (unlike `nav.py`'s
per-scheme fetches) and skips the network call entirely when cached date
bounds already cover the requested range — avoids redundant HTTP calls
across the 4 indices within a single XIRR computation. Degrades to
`False`/no-op on any fetch failure, same convention as `nav.py`/`arn_lookup.py`.

**`backend/app/services/analytics/xirr.py`** — pure `decimal.Decimal`
Newton-Raphson XIRR solver, no numpy/scipy. `Decimal ** Decimal` supports
fractional exponents for a positive base, so `(1+rate) ** (days/365)` never
touches `float`, per CLAUDE.md's Decimal-never-float rule. Degrades to
`None` on non-convergence rather than raising.

**`backend/app/services/analytics/benchmark.py`** — `compute_portfolio_vs_benchmarks`
(FR-8: whole-portfolio XIRR alongside all 4 index XIRRs) and
`compute_fund_vs_benchmark` (FR-9: per-fund-appropriate benchmark, plus an
overall portfolio-vs-Nifty-500 view), each with a family-aggregate wrapper.
Two judgment calls not fully spelled out by the PRD, flagged in-code per
CLAUDE.md's "stop and say so" (see the module's docstring and
`_benchmark_index_for_category`'s docstring for full reasoning): **(1)**
benchmark-hypothetical XIRR replays each real transaction against the
index — same cash-flow dates/amounts as the real portfolio, purchases buy
`amount / index_level_on_date` hypothetical units, redemptions sell that
many, only the terminal value differs (`net_units * today's index level`).
**(2)** since only 4 benchmark indices exist in scope, every SEBI category
folds into one via substring match on "LARGE"/"MID" (Large Cap → Nifty 50,
Mid Cap → Nifty Midcap 150, Large & Mid Cap → Nifty LargeMidcap 250,
everything else — Flexi/Multi/Small Cap, Value/Contra, Sectoral, ELSS,
Debt, Hybrid, etc. — falls back to Nifty 500 as the broad-market default);
never excludes a fund from comparison. Every missing-index-history date is
skipped rather than crashing the whole comparison.

**Routes:** `GET /analytics/household-members/{id}/benchmark`,
`.../benchmark/funds`, and family-aggregate variants
(`/analytics/household/aggregate/benchmark[/funds]`), mirroring the
existing allocation/ter routes' auth/404/response-shape pattern exactly.

**Backend suite: 286 passing, 2 skipped** (up from 250/2) — 36 new tests
(7 NSE client + 8 XIRR + 11 benchmark service + 10 routes), zero
regressions, verified re-running the full suite. Five commits, one per
task (`0b9fffc` NSE client, `59d995b` XIRR, `9960565` FR-8 benchmark,
`0e4c6f9` FR-9 benchmark, `66d0540` routes).

**Not yet done:** knowledge graph not refreshed for this work — treat
`analytics/nse_indices_client.py`, `xirr.py`, `benchmark.py`, and the 4 new
routes as stale in the graph until a fresh `/understand` run. Per the
design doc's 5-step build order, **Part 4 (category-universe NAV caching →
ranking, FR-3/FR-4) is next**, with the Scorer (FR-5/FR-6/FR-7) built last
since it depends on Parts 2–4.

## Phase 4 Part 2: AMFI TER + AAUM integrations → weighted TER (PRD-04 FR-10/FR-11) — built and committed

Built directly (TDD, one task per commit) per the Phase 4 design doc's
build order (`Docs/superpowers/plans/2026-08-10-phase-4-analytics-backend-design.md`),
without a separate written task-by-task plan file — the design doc already
carried full research/spec, and this was executed in one continuous
session rather than delegated to subagents.

**`backend/app/services/analytics/amfi_ter_client.py`** — bulk TER
ingestion. `refresh_ter_data(db)` fetches the latest published month from
AMFI (`populate-ter-month` → `populate-te-rdata-revised`, paginated),
dedupes to the latest `TER_Date` per `Scheme_Name` (AMFI republishes daily
even unchanged), and fuzzy-matches each locally-known scheme with a
resolved Direct/Regular plan variant against that name list
(`difflib.SequenceMatcher`, same idiom as `import_/enrich.py`). One real
tuning finding: `enrich.py`'s 0.92 confirmation threshold doesn't work
here — local scheme names carry a "- Direct/Regular Plan - Growth" suffix
AMFI's plan-generic `Scheme_Name` never has, capping a genuine match's
ratio around 0.67 against an unrelated pair's ~0.26; landed on 0.55 after
computing both live, comfortable margin either side. Degrades gracefully
(returns `False`, writes nothing) on fetch failure or an empty month.

**`backend/app/services/analytics/amfi_aaum_client.py`** — bulk AAUM
ingestion, front-loaded per the design doc's build order even though
FR-10/FR-11 don't consume it (infrastructure for the later FR-4 step).
Matches directly by `AMFI_Code` (no fuzzy matching needed, unlike TER).
**Flagged, not silently assumed:** the financial-years endpoint's shape
was live-verified during design research, but the intermediate
"periods within a financial year" endpoint's exact response shape was
never captured — this module assumes the same envelope by analogy and
documents that assumption inline (module docstring), recommending
live-verification before FR-4 relies on it. Every failure mode here
(missing years/periods, unparseable period label, zero scheme matches)
degrades to "nothing ingested," never a wrong value.

**`backend/app/services/analytics/ter.py`** — `compute_weighted_ter`
(FR-10) and `compute_direct_regular_ter_comparison` (FR-11). Resolves a
real ambiguity in PRD-04's own text: the PRD calls FR-10 "AUM-weighted,"
but the design doc's research already clarified this means weighted by
the *user's own holding value*, not the fund's platform-wide AAUM — this
module never reads `scheme_aaum`. TER is refreshed on-demand with one
bulk fetch (not one fetch per scheme, unlike NAV) only when a held scheme
lacks a current-month `scheme_ter` row; a scheme whose fuzzy match never
resolves is excluded from the weighted average and surfaced via
`uncovered_schemes` rather than silently miscomputed or crashing, per
PRD-04's "TER not yet published" edge case.

**Routes:** `GET /analytics/household-members/{id}/ter`,
`.../ter/direct-regular`, and family-aggregate variants
(`/analytics/household/aggregate/ter[/direct-regular]`), mirroring the
existing allocation routes' auth/404/response-shape pattern exactly.

**Backend suite: 250 passing, 2 skipped** (up from 215/2) — 40 new tests
across 4 new test files, zero regressions. Four commits, one per task
(`f6bbb5c` TER client, `b7197ed` AAUM client, `0971148` weighted TER +
Direct/Regular service, `e026751` routes).

**Not yet done:** the knowledge graph (`.ua/knowledge-graph.json`) has not
been refreshed for this work — a fresh session picking this up next
should treat the graph as stale for the new `analytics/` files until
re-run. AAUM's periods-endpoint shape (above) needs live verification
before FR-4 build starts. Per the design doc's build order, **Part 3 (NSE
Indices integration → benchmark comparison, FR-8/FR-9) is next.**

## Cleanup pass complete: knowledge graph refreshed, worktree branch deleted, CRLF noise reconfirmed harmless

Follow-up session to the CAS Import lifecycle sync (`af74384`) — worked
through the full punch list before starting Phase 4 Part 2.

**Knowledge graph re-refreshed (incremental `/understand` update) — now
matches current HEAD `35fedd38f968e5b763269a67dbe8d16eff44e9ed`.**
`.ua/knowledge-graph.json`: **661 nodes / 1657 edges / 10 layers / 15 tour
steps** (up from 533/1223/10/15 pre-refresh — the CAS Import lifecycle
feature added ~130 nodes across `backend/app/services/import_/`,
`backend/app/api/cas_imports.py`, the Alembic migration, and the whole
`frontend/src/features/import/` tree). Ran the full 7-phase pipeline
manually again (SCAN → BATCH → ANALYZE → ASSEMBLE REVIEW → ARCHITECTURE →
TOUR → REVIEW → SAVE) via the bundled scripts + subagent dispatches from
SKILL.md, same as the Phase 4 Part 1 refresh. Phase 1 re-scanned from
scratch (295 files, up from 262) since new files must be in `scan-result.json`
before `compute-batches.mjs --changed-files` can see them. 13 batches
dispatched to `file-analyzer` subagents (5+8 concurrent, small batches
fused for token efficiency); one subagent (the CLAUDE.md/session.md docs
batch) guessed two doc paths wrong (`Docs/TDD-Unifolio.md` instead of
`Docs/PRDs/TDD-Unifolio.md`, and a wrong `FundSignal.tsx` path) — the merge
script's dangling-edge dropper caught both, and both were manually
re-added with corrected paths after cross-checking the real file tree.
`assemble-reviewer` found nothing else to fix (0 nodes recovered, all 550
import-map edges already present). Architecture layers stayed at the same
10 (CAS Import files slotted into existing Service/API/UI/Test layers, no
new layer needed). Tour grew from 15 to still-15 steps — split the old
single "CAS Import Pipeline" step into "CAS Import: Upload & Parsing" +
"CAS Import Lifecycle: State Machine, Attribution & Coverage Gaps", and
merged "Frontend Entry Point" into "Frontend Auth & Onboarding" to stay
under the 15-step cap. Inline validation: 0 issues, 37 orphan-node warnings
(all pre-existing empty `__init__.py`/static doc files, expected).
`meta.json`/`fingerprints.json` both regenerated and now agree on
`gitCommitHash 35fedd38f...`.

**`feature/phase4-part1-allocation` local branch deleted.** The worktree
was already removed in the prior session; this session finished the
cleanup with `git branch -d feature/phase4-part1-allocation` (safe delete,
refused-if-unmerged check passed since it was confirmed fully merged into
`dev_intern`). No remote branch existed for it, so nothing to clean up
upstream.

**~50 files showing as modified in `git status` are still pure CRLF
noise** — reconfirmed via `git diff -w`, same pre-existing
checkout-environment quirk as `backend/app/api/{auth,dashboard,imports}.py`.
Not touched; not worth normalizing line endings repo-wide for.

**Push still pending** — this sandbox has no git credentials configured
(no credential helper, no SSH key), so `git push` fails immediately with
`could not read Password`. Push manually from a terminal with credentials,
or run `! git push origin dev_intern` in a Claude Code session that has
them.

## Phase 4 Part 1 (Analytics — category allocation, PRD-04 FR-1/FR-2) is built and merged to `dev_intern`

Built in an earlier Claude Code session on branch `feature/phase4-part1-allocation`
via a git worktree at `.worktrees/phase4-part1-allocation` (worktree since
removed — see note above; the branch itself is unaffected and still exists).
Merged into `dev_intern` this session with
`git merge --no-ff` (merge commit `1ab0fab`, auto-merged cleanly, zero
conflicts in the feature code). One unrelated conflict surfaced restoring
this session's own pre-merge stash (`backend/app/api/analytics.py` — the
stashed side was just the old pre-Phase-4 stub file, no real content;
resolved by keeping the merged version, nothing lost).

Per the design doc's build order (`Docs/superpowers/plans/2026-08-10-phase-4-analytics-backend-design.md`),
Analytics is being built in 5 steps: **(1) Allocation — done**, (2) AMFI
TER+AAUM → weighted TER (FR-10, FR-11), (3) NSE Indices → benchmark
comparison (FR-8, FR-9), (4) category-universe NAV caching → ranking (FR-3,
FR-4), (5) Scorer (FR-5, FR-6, FR-7, depends on 2–4). **Part 2 (TER/AAUM) is
next.**

**What Part 1 built:**
- `backend/app/services/analytics/allocation.py` — `compute_category_allocation`
  (SEBI-category + AMC buckets, Decimal-precise throughout) and
  `get_aggregate_category_allocation` (family-aggregate wrapper). Reuses
  `dashboard/holdings.py`'s existing FIFO engine rather than duplicating
  holdings computation — same pattern as `dashboard/allocation.py`'s
  by-AMC view.
- `backend/app/services/analytics/schemas.py` — `AnalyticsAllocationSummary`,
  `AggregateAnalyticsAllocationResponse`.
- Two new routes on `backend/app/api/analytics.py`:
  `GET /analytics/household-members/{member_id}/allocation` (per-member) and
  `GET /analytics/household/aggregate/allocation` (family aggregate).
- 8 new tests (5 route-level in `test_analytics_allocation_route.py`, 3
  service-level in `test_allocation.py`). **Backend suite: 164 passing, 2
  skipped (was 156)** — verified by running `pytest` after the merge, not
  just claimed.
- Plan docs: `Docs/superpowers/plans/2026-08-10-phase-4-analytics-backend-design.md`
  (full Analytics build-order design) and
  `...-part1-allocation.md` (Part 1's own TDD plan), plus a
  `Docs/PRDs/TDD-Unifolio.md` API-surface table correction.

**Branch state:** `dev_intern` is now **ahead 7 / behind 10 of
`origin/dev_intern`** (diverged — not pushed or pulled this session; no TTY
for credentials in this sandbox, sync manually). Also carried in from an
earlier commit on this branch (`675e0f2`, not part of the Phase 4 merge):
Claude plugin config + local headroom-wrap session hooks
(`.claude/settings.json`, `.claude/settings.local.json`).

**Knowledge graph refreshed (incremental `/understand` update, same
session).** `.ua/knowledge-graph.json` now matches `gitCommitHash
1ab0fabc9cd075e7b7a40e2a9dc37835b77267de` (the Phase 4 Part 1 merge commit):
533 nodes / 1223 edges / 10 layers / 15 tour steps (up from 505/1121/10/14
pre-merge). Ran the full 7-phase pipeline manually (SCAN → BATCH → ANALYZE →
ASSEMBLE REVIEW → ARCHITECTURE → TOUR → REVIEW → SAVE) since the `Skill`
tool's `understand` skill wasn't loaded in this session's registry — executed
the bundled scripts/subagent dispatches from SKILL.md directly instead.
Incremental path: pruned the 27 old nodes/102 edges for the 16
changed/new files from the prior graph into `batch-existing.json`, re-merged
against 7 freshly-analyzed batches — 0 dropped edges, 0 validation issues.
New Analytics service/route/schema/test nodes landed in the existing
"Service Layer"/"API Layer"/"Types Layer"/"Test Layer" layers (no new layer
needed); tour got one new step ("Analytics: Category & AMC Allocation",
step 10 of 15) inserted after the dashboard-narrative steps. Also deleted 2
leftover bogus `.ua/`-scoped nodes (`file:.ua/.understandignore`,
`document:.ua/tmp/scan-stderr.txt`) that had been carried over from a prior
run's data-hygiene issue.

**Separate pre-existing hygiene issue (not fixed, flagged only):** an old
`.ua/.trash-1786098818/` directory is tracked in git and shows as modified
in `git status` — confirmed via `git diff -w` that it's pure CRLF/line-ending
noise, same as the pre-existing `backend/app/api/{auth,dashboard,imports}.py`
noise already noted above. A prior session apparently committed a
plugin-cleanup trash dir to the repo; worth `git rm -r`-ing it in a future
session, but out of scope here since it predates this session's changes.

---

## Phase 0, Phase 1 (backend + frontend), Phase 2 (backend), Phase 2b (frontend), Phase 3 (Main Dashboard backend), and Phase 3b (Frontend UI Redesign) are all complete

**Phase 3b / Frontend UI Redesign — built via Google Antigravity on branch
`feature/frontend-redesign`, reviewed and fixed by Claude Code this
session.** Zero changes under `backend/` (confirmed: empty diff against
`main`, 156/156 backend tests untouched and passing).

**Antigravity's own report claimed "28 passing test files" / fully tested —
that was false.** Actual state on first inspection: 39 of 104 frontend tests
failing, plus 6 `tsc -b --noEmit` errors. Root-caused and fixed every one
(not just patched to green) — see the "Frontend redesign review — fixes
made" section below for the breakdown between real app bugs (fixed in
component code) and stale pre-existing tests never updated after the
redesign changed copy/behavior (fixed in tests, each verified to be a
legitimate copy/behavior change, not a masked regression). **Current true
state: 156/156 backend, 104/104 frontend, `tsc -b --noEmit` clean.**

### Summary of UI/UX Enhancements & Deliverables:
- **Design Tokens & Typography (`frontend/src/styles/tokens.css`, `index.css`, `index.html`)**:
  - Full 8-token type scale: `type-display` (32px), `type-h1` (24px), `type-h2` (18px), `type-body` (15px), `type-body-medium` (15px), `type-caption` (13px), `type-data` (15px tabular-nums), `type-data-large` (20px tabular-nums).
  - Web fonts: DM Sans and Manrope loaded via Google Fonts with `font-display: swap` and OpenType tabular figures (`font-variant-numeric: tabular-nums`).
  - Dark Mode tokens & Global Floating Theme Toggle: `--color-accent-dark` (`#22C55E`), `--color-neutral-badge-dark` (`#475569`), `--color-warning-dark` (`#F59E0B`), `--color-positive-dark` (`#22C55E`), `--color-negative-dark` (`#F87171`), `--color-surface-dark` (`#1A1A1A`), `--color-border-dark` (`#2A2A2A`). Accessible via persistent floating theme toggle button (`🌙`/`☀️`) on all screens.
  - Verified `prefers-reduced-motion: reduce` zeroing out all motion variables.

- **Polished Interactive Controls & Forms**:
  - **Drag-and-Drop CAS Statement Upload (`UploadForm.tsx`)**: Elevated upload drop zone with file type validation, selected file badge (`📄`), remove file button, password reveal toggle (`👁️`), and clear call-to-action button (`Upload & Parse Statement →`).
  - **Button Primitives (`Button.tsx`)**: Standardized button hierarchy (`primary` green, `secondary` outline, `ghost` text/skip/back buttons) with hover micro-animations, active lift, and WCAG AA focus rings.
  - **Onboarding Questionnaire (`Q1Name`, `Q2Investing`, `Q3Purpose`, `Q4Household`, `TrustPrimer`)**: Redesigned choice tiles with radio icons, trust guarantee cards, phone input group (`🇮🇳 +91`), 6-digit OTP monospaced inputs, and clear Back/Next/Skip navigation.

- **Main Dashboard & Greenfield Screens (`frontend/src/features/dashboard/`)**:
  - **`NavigationShell.tsx`**: Persistent header with mode switcher (Per-Member ↔ Family Aggregate), member selector dropdown, "+ Add Data" action button (S16), dark/light mode toggle, and disabled Analytics nav item (with tooltip explaining PRD-04 backend status).
  - **`DashboardView.tsx`**: Hero summary card (Total Value in `type-display` DM Sans 700 32px, Total Gain, XIRR/Percentage), Allocation Donut breakdown, Holdings Table with Fund Signal arcs, S21 Empty State for 0 holdings, and S22 Family Member Placeholders for members with `has_data: false`.
  - **`FundSignal.tsx`**: Signature SVG radial arc component matching Unifolio logo "o" geometry, `motion-reveal` animated fill on load, positive/negative gain semantics, and hover/focus trend sparkline popout (30D, 90D, 1Y).
  - **`FundDetailModal.tsx` (S15)**: Overlay displaying detailed NAV history and investment metrics. *(Historical — the "Compare Distributors" CTA described here was removed from this component by the 2026-08-21 portfolio-level rewrite; see the top of this file.)*
  - **`DistributorComparisonModal.tsx` (S17)**: *(Historical — describes the original scheme-scoped design. Rebuilt portfolio-wide against `/household-members/{id}/distributor-comparison` and `/aggregate/distributor-comparison` by the 2026-08-21 rewrite; see the top of this file.)* Displays ARN status (`ACTIVE`, `SUSPENDED`, `INVALID`), distributor name, units, invested, current value, gains.
  - **`MainDashboardFlow.tsx`**: Manages default landing logic (family aggregate view default for multi-member accounts, per-member default for single accounts) and S16 Add Data re-entry into CAS upload.

- **Testing & Quality Verification** (as claimed by Antigravity, not independently re-verified by Claude Code — the Impeccable scoring workflow wasn't re-run this session):
  - Evaluated against Impeccable skill heuristic scoring (Alex power user & Sam accessibility personas) in Operate Mode. Claimed Good-band score (≥34/40) across all major screens.

### Frontend redesign review — fixes made (Claude Code, this session)

Real app bugs, fixed in component code:
- **`UploadForm.tsx`**: the PDF-password `<label>` had no `htmlFor`/`id`
  linking it to its `<input>` — a genuine accessibility regression (screen
  readers couldn't associate the label with the field). Root cause of 17 of
  the 39 initial test failures across `UploadForm`/`ImportFlow`/
  `FamilyImportFlow`.
- **`MainDashboardFlow.tsx`**'s "Add Data" (S16) re-entry used
  `SoloCasUpload` — an onboarding-only component that always resolves/
  creates the **"self"** household member and has no way to accept an
  existing `householdMemberId`. Every Add Data click for a non-self family
  member would have silently uploaded against the wrong member (or created
  a duplicate self row) — a real correctness risk for a financial app,
  caught by TypeScript's own prop-mismatch error. Fixed by swapping to
  `ImportFlow`, the generic component that already takes a real
  `householdMemberId` (what the redesign brief itself pointed at for S16).
- **`DashboardView.tsx`**: the "Total Portfolio Value" hero number was
  computed by `parseFloat`-summing every holding's `current_value`
  client-side, even though the exact figure (`allocation.total_value`,
  Decimal-precise, computed backend-side) was already fetched and sitting
  unused in state. Client-side float accumulation across holdings is
  exactly the failure mode CLAUDE.md's "`Decimal`, never `float`" rule
  exists to prevent, on the single most visible number on the page. Fixed
  to use the server total directly. `investedVal`/`profitVal` had no
  server total to substitute the same way (allocation only exposes
  `total_value`) — resolved separately, see below.
- **`FundSignal.tsx`**: removed a dead, never-wired `strokeDashoffset`
  variable (an earlier arc-fill approach superseded by the working
  `strokeDasharray`/`fillRatio` technique already in use) — a `tsc` error,
  not a visual bug; the arc already renders/animates correctly via the
  technique that stayed.
- **`Button.tsx`/`Modal.tsx`**: `import type` fixes for `verbatimModuleSyntax`.

Test-suite staleness, fixed in tests (each verified to be a copy/behavior
change, not a masked regression):
- ~20 failures were pre-existing tests never updated after the redesign
  changed visible copy ("Phone number" → "Mobile Number", "Send OTP" →
  "Send Verification Code", "6-digit code" → "Verification Code", "Verify"
  → "Verify & Continue", "What should we call you?" → "Your Full Name or
  First Name", "Add" → "Add Member", "Upload" → "Upload & Parse Statement",
  plus two validation-message wording changes).
- 3 `OnboardingFlow` tests broke because the redesigned `Q1Name` added
  `disabled={!name.trim()}` to its Next button (the original never disabled
  it) — a real, undocumented behavior change. Since those tests don't care
  about Q1's answer, switched their Q1 step to the existing Skip button.
- `DashboardView`'s `₹7,500` assertion used `getByText`, but the
  single-holding fixture legitimately renders that value in 4 places (hero,
  donut center, donut legend, table cell) — switched to `getAllByText`.
- `FundSignal.test.tsx` had a literal syntax error (a stray `aria-label:`
  token) that made the whole file fail to parse.
- `MainDashboardFlow.test.tsx`'s `HouseholdMember` fixture included
  `user_id`/`created_at` fields the real type (matching the backend's
  `HouseholdMemberResponse` exactly) doesn't have.
- Added the missing `window.matchMedia` jsdom mock
  (`frontend/src/setupTests.ts`) — `ThemeToggle`/`NavigationShell` both call
  it and jsdom doesn't implement it.

**Both flagged items resolved this session, per your explicit follow-up
instruction:**
- **`investedVal`/`profitVal` float accumulation** — fixed with a new,
  dependency-free `sumDecimalStrings` helper
  (`frontend/src/lib/decimal.ts`): exact decimal-string addition via
  integer minor units (`BigInt`), no new npm dependency. Handles a
  variable number of decimal places (the backend doesn't quantize
  `current_value`/`amount_invested` before serializing — `units * nav` can
  carry more than 2 decimal places, so a fixed-2dp assumption would have
  silently truncated real precision). Only the final summed result is
  parsed to a number once, for display formatting — the accumulation
  itself never touches `float`. 7 new tests, including one proving an
  exact result where float accumulation would visibly drift (ten additions
  of `"0.1"`).
- **`impeccable` plugin committed into this repo's git history** —
  untracked (`git rm --cached`) and added to `.gitignore`
  (`.agents/skills/`, `.claude/skills/`), left in place on disk so any
  coding agent working in this checkout still has it available. Per your
  instruction: keep it usable for switching agents, don't keep it tracked
  in the app's own history where it'll drift stale against the plugin's
  own update mechanism.
- `HoldingsTable.tsx` still references a `row.return_percentage_1y` field
  that doesn't exist anywhere in the real `HoldingRow` backend response —
  always `undefined` in practice, silently falling through to a
  client-computed fallback. Harmless (the fallback is what runs either
  way), but dead code worth cleaning up. Not yet actioned.

- **Branch Status**: merged to `main` (fast-forward from
  `feature/frontend-redesign` — same commit, `61bf6f4`). A `dev_intern`
  branch was cut from `main` at this same commit for sharing with an
  intern. Both `main` and `dev_intern` are pushed to `origin`. 156/156
  backend, 111/111 frontend (30 files), `tsc -b --noEmit` clean —
  genuinely verified, not claimed.

## Knowledge graph — read this before re-scanning the codebase

A full codebase knowledge graph exists at `.ua/knowledge-graph.json`
(built via the `understand-anything` Claude Code plugin — **533 nodes, 1223
edges, 10 architectural layers, a 15-step guided tour** as of the Phase 4
Part 1 merge), with `meta.json.gitCommitHash` =
`1ab0fabc9cd075e7b7a40e2a9dc37835b77267de`, matching `dev_intern`'s HEAD at
merge time (not stale as of this session). A fresh session should query this
graph (or launch its dashboard: `/understand-dashboard`) instead of
re-reading/grepping the whole repo. If `dev_intern` has moved past that
commit by the time you read this, the graph may be stale — check
`git log -1 --format=%H` against `.ua/meta.json`'s `gitCommitHash` before
trusting it, and re-run `/understand` (incremental update, only
re-analyzes changed files) if they've diverged.

---

## Phase 0, Phase 1 (backend + frontend), Phase 2 (backend), Phase 2b (frontend), and Phase 3 (Main Dashboard backend) are all complete, merged to `main`

**Phase 0 (foundation)** — all 11 tasks, `Docs/superpowers/plans/2026-08-04-phase-0-foundation.md`.
**Phase 1 backend — CAS import tightening + monolith port.** All 9 tasks, `Docs/superpowers/plans/2026-08-04-phase-1-cas-import-backend.md`.
**Phase 1b — Import Review frontend.** All 7 tasks, `Docs/superpowers/plans/2026-08-05-phase-1b-import-review-frontend.md`.
**Phase 2 (backend) — Auth + Onboarding.** All 4 tasks, `Docs/superpowers/plans/2026-08-05-phase-2-auth-onboarding-backend.md`.
**Phase 2b (Onboarding frontend).** `Docs/superpowers/plans/2026-08-06-phase-2b-onboarding-frontend.md`.
**Phase 3 (Main Dashboard backend).** `Docs/superpowers/plans/2026-08-06-phase-3-main-dashboard-backend.md`.

Test suites: **backend 156 passing**, **frontend 29 test files / 104 tests passing**.

## What's next

*(Stale as of 2026-08-14 — kept for history. PRD-04's backend is now fully built; see
the "Branch reconciliation" section at the top of this file for current status.)*

**PRD-04 (Analytics)** remains fully unbuilt, the module after Main Dashboard in the natural build order.
