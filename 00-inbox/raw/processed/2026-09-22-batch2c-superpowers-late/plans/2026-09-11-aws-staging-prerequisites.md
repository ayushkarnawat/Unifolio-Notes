# AWS staging: prerequisites & deployment runbook

**Date:** 2026-09-11
**Status:** Planning/documentation only. No command below has been executed by
Claude — every AWS-state-mutating or credential-bearing step is marked
**[user-run]**, per this project's established division of labor (Claude/Codex
never runs `terraform apply`, `docker push`, `aws ecs update-service`, or any
other state-mutating AWS command).

This supersedes §2's sequencing in
`Docs/superpowers/plans/2026-09-10-feat-enhanced-ui-to-staging-push-plan.md`
now that its step 1 (frontend precompute migration) and step 7 (dispatcher
wiring) are both done — this doc reflects current state and gives exact
commands where the prior doc gave a plan-level description.

## 1. Where things stand right now

**Code — all done, both suites green:**
- Frontend 14→1 analytics-route migration: done (`b972e65`), both desktop and
  mobile consumers use the consolidated `useAnalyticsScope` hook.
- Analytics-recompute dispatcher wired to real ADR-006 ECS infra: done
  (`20a825e`) — Terraform-authored, not yet applied (see §1 Terraform below).
- Google Sign-In hidden client-side pending real OAuth config: done
  (`83a3749`), deliberate 2026-09-11 scope decision, not a bug.
- Investor feature batch (Profile, account deletion, contact-change OTP,
  theme toggle, import history/delete, Dashboard XIRR, allocation sort, AMC
  drill-down) plus this session's PM-gap-analysis follow-ups (XIRR
  lifetime/current toggle replacing the dismiss-less popover, drill-down
  modal subtotal, `functional_postgres` cascade-delete test coverage): all
  done and independently verified this session — backend 649 passed/8
  skipped, frontend 437 passed/79 files, `tsc -b --noEmit` clean.
- Mandatory adversarial-review gate for the two most recent orchestrator-direct
  fix rounds (round-3 P1/P2 fixes, this session's PM-gap fixes) is **deferred,
  not skipped** — Codex was unavailable this session; both rounds are logged
  in `Docs/orchestration/delegation-log.md` and owe a review pass once Codex
  is back.

**Git:**
- `feat/enhanced-ui` is the sole active branch, ahead of `origin/feat/enhanced-ui`
  and not yet pushed. `main`/`production` are confirmed zero-divergence
  fast-forward ancestors (verified 2026-09-10) — no merge-conflict risk when
  promoting, but re-confirm with a fresh `git merge-base` check before Step 1
  below, since more commits have landed since that check.

**AWS — live in `ap-south-1`, account `811364789032`:**
- Phases 1-3 (networking, RDS, ECS/ALB/ECR) applied and healthy, per
  `session.md`'s 2026-09-09 entry.
- **RDS schema is stale.** `alembic current` was last confirmed at `0011`.
  Three migrations have landed since and are NOT yet applied to real RDS:
  `0012_analytics_sections`, `0013_account_deletion_grace_period`,
  `0014_analytics_recompute_generation`. Current local head is `0014`.
- **The deployed ECR image is stale** — built before the precompute merge,
  the frontend migration, the dispatcher wiring, the account-deletion
  feature, and this session's PM-gap fixes. It does not match what's on
  `feat/enhanced-ui` today.
- **Correction (2026-09-11, mid-execution):** the claim below that Phase 4/5
  and the dispatcher task-def were "authored, not applied" was stale. A
  `terraform plan` run during actual Step 4 execution showed
  `module.backend.aws_ecs_task_definition.analytics_recompute`,
  `module.backend.aws_lb_listener.https`, both `module.dns` ACM certs (+
  validation), `module.frontend.aws_cloudfront_distribution.this`, and both
  `module.dns.aws_route53_record` entries already present in Terraform
  state (refreshed, not created) — i.e. **already applied**, likely via the
  stray `tfplan-step7` file found in `infra/envs/staging` (dated
  2026-09-11 03:24, predating this session's Step 4). Only the
  `analytics_recompute_daily` job (from the same earlier apply) and the
  brand-new `account_deletion_daily` job (from this session's code) were
  still outstanding — confirmed via a fresh `terraform plan`: **3 to add, 1
  to change (scheduler IAM policy, to include the new job's ARN), 0 to
  destroy.** Applied cleanly. The bullet list immediately below is the
  original pre-execution belief, left for context, but was inaccurate by
  the time Step 4 actually ran.
- **Terraform state as originally believed going into this session** (see
  correction above — Phase 4/5 turned out to already be applied):
  - `infra/modules/backend`: a new ECS task definition + IAM task role for
    `EcsRunTaskDispatcher` (from `20a825e`) — authored, reviewed, not applied.
  - `infra/modules/scheduler`: 2 new jobs beyond the original 4
    (`analytics_recompute --all` daily backstop, `delete_expired_accounts_daily`)
    — authored, reviewed, not applied. Only the original 4 jobs are live.
  - `infra/modules/frontend` (Phase 4, S3+CloudFront): authored, reviewed,
    not applied.
  - `infra/modules/dns` (Phase 5, ACM/Route 53/ALB HTTPS): authored,
    reviewed, not applied, gated on Phase 4 being applied first.

## 2. Manual/external prerequisites — verify before running §3

- [ ] **AWS CLI v2 + Terraform 1.16.1 + `aws configure`.** Already set up in
  the 2026-09-09 session. Just confirm credentials are still valid:
  `aws sts get-caller-identity` should return the `ayush-admim` IAM user.
- [ ] **Docker Desktop WSL integration — re-verify, don't assume.** This
  session's WSL distro could not reach `docker` at all (the binary only
  existed at the Windows-side path, `/mnt/c/Program Files/Docker/Docker/
  resources/bin/docker`, and WSL integration was off for this distro). A
  prior session (2026-09-09) successfully ran `docker build`/`push` from a
  WSL terminal, so this is either distro-specific state or was toggled off
  since — don't assume the earlier success still holds. Before Step 3,
  open Docker Desktop → Settings → Resources → WSL Integration and confirm
  the distro you're building from is enabled, or build from a native
  Windows PowerShell/cmd terminal instead.
- [ ] **No concurrent Terraform run against the same state.** S3+DynamoDB
  locking should already prevent this, but worth a sanity check before a
  multi-module apply session touching `backend`, `scheduler`, `frontend`,
  and `dns` in one pass.
- [ ] **Secrets Manager RDS password retrieval — use the safe pattern.**
  Re-read `session.md`'s 2026-09-09 note before typing the migration
  commands in §3 Step 2: the master password contains shell metacharacters
  (`$`), and interpolating it directly into a double-quoted shell string
  will silently corrupt it via bash variable expansion. Always pipe it
  through `python3 -c` reading `os.environ`, never as a literal in a
  quoted string.
- [ ] **Google OAuth stays unconfigured for this pass** — deliberate
  2026-09-11 scope decision, not a prerequisite to fix. Don't accidentally
  re-enable the sign-in button while touching auth-adjacent code.

## 3. Command sequence

Everything below is **[user-run]**. Every value that is stable across
Terraform applies (account ID, region, VPC-level IDs, cluster/service names,
DB name/username) is filled in for real below — no placeholder guessing.
The handful of values that only exist *after* a given apply (the master
password, Phase 4's bucket/distribution IDs, task-def revisions) are pulled
live with an exact `terraform output`/`aws` command that stores them into a
shell variable, so every command after it is still copy-paste, just chained.

**Run Step 0 once per terminal session** (any terminal you use for Steps 2-7),
then the rest of that terminal's commands can be pasted straight through.

### Step 0 — Shared constants (paste once per terminal)

```bash
export REPO_ROOT="/mnt/d/Unifolio code"
export AWS_ACCOUNT_ID=811364789032
export AWS_REGION=ap-south-1
export ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/unifolio-staging-backend"
export ECS_CLUSTER=unifolio-staging
export ECS_SERVICE=unifolio-staging-backend
export ALB_DNS=unifolio-staging-alb-958627457.ap-south-1.elb.amazonaws.com
export BASTION_ID=i-0b67d40d9b58b7814
export RDS_HOST=staging-rds.ctu88scmut9m.ap-south-1.rds.amazonaws.com
export RDS_PORT=5432
export DB_NAME=unifolio
export DB_USER=unifolio
```

These are read from `infra/modules/database/main.tf` (`db_name`/`username =
"unifolio"`) and `session.md`'s 2026-09-09 entry — they don't change across
applies because none of Steps 4-7 touch networking/database/backend-identity
resources, only add new ones. Re-verify any single value with
`terraform output` in `infra/envs/staging` if you ever doubt it; it's the
authoritative source, this is just a copy of it.

`$REPO_ROOT` is a fixed path, used instead of a `$(git rev-parse
--show-toplevel)` subshell in every step below — the latter only works if
your shell's current directory is already somewhere inside the repo, which
it usually isn't in a fresh terminal (this is what produced the `fatal: not
a git repository` / `Invalid length for parameter SecretId` errors you hit —
nothing was wrong with the AWS side, `git rev-parse` just silently returned
empty because you were in `~`, so every path built from it collapsed to
`/infra/envs/staging`).

### Step 1 — Push code, promote branches

```bash
git push origin feat/enhanced-ui
git checkout main && git merge --ff-only feat/enhanced-ui && git push origin main
git checkout production && git merge --ff-only feat/enhanced-ui && git push origin production
git checkout feat/enhanced-ui
```

Re-run `git merge-base main feat/enhanced-ui` and confirm it equals `main`'s
current HEAD immediately before this step — the last confirmation is from
2026-09-10, more commits have landed since.

### Step 2 — Apply RDS schema migrations (0012, 0013, 0014)

**Terminal A** — open the SSM tunnel and leave it running (it blocks; don't
Ctrl-C until Step 2 is fully done):

```bash
aws ssm start-session --target "$BASTION_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$RDS_HOST\"],\"portNumber\":[\"$RDS_PORT\"],\"localPortNumber\":[\"5433\"]}"
```

You should see `Waiting for connections...` — that means the tunnel is up.
Leave this terminal open.

**Terminal B** — run Step 0's constants block again (each terminal needs its
own copy), then:

```bash
export MASTER_SECRET_ARN=$(terraform -chdir="$REPO_ROOT/infra/envs/staging" \
  output -raw master_user_secret_arn)

export DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id "$MASTER_SECRET_ARN" \
  --query SecretString --output text | python3 -c "import json,sys; print(json.load(sys.stdin)['password'])")
```

The password contains shell metacharacters (confirmed `$` in a prior
rotation) — the `python3 -c` step above is mandatory, never substitute a
literal `$DB_PASSWORD` value into a double-quoted string by hand.

Then, from `backend/` with the project `.venv` active:

```bash
cd "$REPO_ROOT/backend"
source .venv/bin/activate
export DATABASE_URL="postgresql+psycopg2://${DB_USER}:${DB_PASSWORD}@127.0.0.1:5433/${DB_NAME}"
python -m alembic upgrade head
python -m alembic current   # must print "0014 (head)" — if it doesn't, stop here
```

Once confirmed, go back to Terminal A and `Ctrl-C` the SSM session — it's
only needed for this step.

### Step 3 — Rebuild & push the backend Docker image

Only after confirming Docker Desktop WSL integration per §2 (run `docker
info` first — if it errors instead of printing server info, fix WSL
integration before continuing here, don't try to work around it).

```bash
cd "$REPO_ROOT/backend"
docker build -t unifolio-staging-backend .
```

**If this fails with `failed to xattr .pytest_tmp: permission denied`:**
this is the known stuck-`.pytest_tmp` directory (WSL/drvfs permission lock,
seen in prior sessions) — BuildKit stats every path in the build context
before applying `.dockerignore`, so a permission-denied directory anywhere
in `backend/` kills the build even though `.dockerignore` already excludes
it. Fix (needs your password, not runnable non-interactively):

```bash
sudo rm -rf .pytest_tmp
docker build -t unifolio-staging-backend .   # retry
```

`pytest.ini`'s `--basetemp` was moved to `/tmp/unifolio-backend-pytest`
(outside the repo) this session specifically so this stops recurring on
every future build — if you still hit this error after that change is in
place, something else created a permission-locked path in `backend/`, don't
assume it's the same directory.

**Do not skip straight to `docker push` if the build step errored** — a
failed `docker build` leaves the old `unifolio-staging-backend:latest` local
image tag untouched, so `docker tag`/`docker push` will silently re-push the
*old* image with no error, all layers reported "already exists." Only
proceed once `docker build` itself prints a final success line.

```bash
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
docker tag unifolio-staging-backend:latest "${ECR_REPO}:latest"
docker push "${ECR_REPO}:latest"
```

Sanity-check the pushed digest is actually new, not a repeat of a prior
stale push:

```bash
docker images --no-trunc --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep unifolio-staging-backend
```

Compare the `Id` against the digest ECR reports after `docker push` — if
you've hit this exact failure before, the old stale digest was
`sha256:bd6ac1fe...`; the new one must differ.

### Step 4 — Apply Terraform (backend + scheduler changes, then Phase 4, then Phase 5)

```bash
cd "$REPO_ROOT/infra/envs/staging"
terraform init
terraform plan -out=tfplan
```

(There are stale `tfplan-bastion-fix`/`tfplan-step7` files from earlier
sessions sitting in this directory — harmless, gitignored, and this command
overwrites `tfplan` fresh. Ignore them, no cleanup needed.)

Review the plan carefully before applying — expect **additive-only** changes:

- `modules/backend`: +1 ECS task definition, +1 IAM task role (dispatcher).
- `modules/scheduler`: +2 EventBridge schedules, +2 task definitions, +2
  CloudWatch log groups (`analytics_recompute --all` backstop,
  `delete_expired_accounts_daily`) — the original 4 jobs are unaffected.
- `modules/frontend`: new S3 bucket + CloudFront distribution (Phase 4).
- `modules/dns`: new ACM certs, Route 53 alias records, ALB HTTPS listener,
  HTTP→HTTPS redirect (Phase 5).

If anything shows as **destroyed**, stop and don't apply — that's not
consistent with the additive changes described above and needs review first.

```bash
terraform apply "tfplan"
```

Once it finishes, capture the values Steps 6-7 need (these only exist after
this apply — Phase 4's bucket/distribution didn't exist before now):

```bash
export FRONTEND_BUCKET=$(terraform output -raw s3_bucket_name)
export CLOUDFRONT_DIST_ID=$(terraform output -raw cloudfront_distribution_id)
echo "bucket=$FRONTEND_BUCKET  distribution=$CLOUDFRONT_DIST_ID"
```

Both should print non-empty values — if either is blank, the apply didn't
actually create the frontend module's resources; stop and check
`terraform state list | grep module.frontend` before continuing.

### Step 5 — Force a fresh ECS deployment

Picks up the new image (Step 3) and the dispatcher's new task-def env vars
(Step 4):

```bash
aws ecs update-service --cluster "$ECS_CLUSTER" \
  --service "$ECS_SERVICE" --force-new-deployment
```

Wait ~1-2 minutes for the new task to start, then run the same 4-check bar
from the original Phase 3 push (`session.md`, 2026-09-09) — commands, not
just descriptions:

```bash
# 1. New task is RUNNING with a fresh, stable startedAt (re-run this once,
#    ~30s apart, and confirm startedAt hasn't changed between the two runs)
aws ecs describe-tasks --cluster "$ECS_CLUSTER" \
  --tasks $(aws ecs list-tasks --cluster "$ECS_CLUSTER" --service-name "$ECS_SERVICE" --query 'taskArns[0]' --output text) \
  --query 'tasks[0].{status:lastStatus,startedAt:startedAt,stoppedReason:stoppedReason}'

# 2. ALB target group is healthy
export TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups \
  --query "TargetGroups[?contains(TargetGroupName, 'unifolio-staging')].TargetGroupArn" --output text)
aws elbv2 describe-target-health --target-group-arn "$TARGET_GROUP_ARN" \
  --query 'TargetHealthDescriptions[*].TargetHealth.State'

# 3. Logs are clean (Ctrl-C after a few lines once you've confirmed no errors)
aws logs tail /ecs/staging-backend --since 5m --follow

# 4. A real DB-touching request works end to end (stub OTP mode is safe — no real email sent)
curl -s -X POST "http://$ALB_DNS/auth/email-otp/request" \
  -H "Content-Type: application/json" -d '{"email":"smoke-test@unifolio.in"}'
# expect: {"message":"OTP sent.","otp":"..."} — the presence of "otp" in the
# response confirms OTP_DELIVERY_MODE=stub is still set, which is correct for staging.
```

If check 4 instead returns a redirect/empty body: Step 4's Phase 5 apply adds
an HTTP→HTTPS listener redirect on this same ALB, so plain `http://` may now
bounce. Retry with `curl -sk -L "https://$ALB_DNS/auth/email-otp/request" ...`
(`-k` because the ALB's own AWS DNS name won't match the `staging-api.unifolio.in`
ACM cert — that mismatch is expected here and not a bug; the real domain will
match once you hit it via `https://staging-api.unifolio.in` after DNS propagates).

### Step 6 — Rebuild & upload the frontend

```bash
cd "$REPO_ROOT/frontend"
VITE_API_BASE_URL=https://staging-api.unifolio.in npm run build
aws s3 sync dist/ "s3://${FRONTEND_BUCKET}/" --delete
aws cloudfront create-invalidation --distribution-id "$CLOUDFRONT_DIST_ID" --paths "/*"
```

(`$FRONTEND_BUCKET`/`$CLOUDFRONT_DIST_ID` come from Step 4's post-apply
export — if this is a new terminal and they're not set, re-run
`terraform output -raw s3_bucket_name` / `-raw cloudfront_distribution_id`
from `infra/envs/staging` first.)

No `VITE_GOOGLE_OAUTH_CLIENT_ID` — deliberately unset per the 2026-09-11
scope decision (§1).

### Step 7 — One-off seed run for the 2 new scheduled jobs

The original 4 jobs already ran once manually (2026-09-10, confirmed
working after the `min()`/`max()` fix now riding along in Step 3's image).
The 2 new ones need the same one-off confirmation before waiting on their
first real cron fire:

Both job families are named `<project>-<environment>-job-<slug>` (from
`infra/modules/scheduler/main.tf`'s `local.jobs`) — ECS resolves the latest
`ACTIVE` revision automatically when you pass the family name with no
`:revision` suffix, so no ARN lookup is needed:

```bash
export NETWORK_CONFIG=$(terraform -chdir="$REPO_ROOT/infra/envs/staging" \
  output -json networking | python3 -c "
import json, sys
n = json.load(sys.stdin)
subnets = ','.join(n['private_app_subnet_ids'])
print(f\"awsvpcConfiguration={{subnets=[{subnets}],securityGroups=[{n['ecs_security_group_id']}],assignPublicIp=DISABLED}}\")
")

aws ecs run-task --cluster "$ECS_CLUSTER" \
  --task-definition unifolio-staging-job-analytics-recompute-daily \
  --launch-type FARGATE --network-configuration "$NETWORK_CONFIG"

aws ecs run-task --cluster "$ECS_CLUSTER" \
  --task-definition unifolio-staging-job-account-deletion-daily \
  --launch-type FARGATE --network-configuration "$NETWORK_CONFIG"
```

Each `run-task` prints a `taskArn` — wait ~30-60s for the task to finish
(Fargate jobs, not long-running services), then confirm a clean exit (not
just `RUNNING`):

```bash
aws logs tail /ecs/staging-job-analytics-recompute-daily --since 5m
aws logs tail /ecs/staging-job-account-deletion-daily --since 5m
```

Look for the job script's own completion log line and no traceback — a
`STOPPED` status with `stoppedReason: Essential container in task exited`
and exit code `0` (check via `aws ecs describe-tasks --cluster "$ECS_CLUSTER"
--tasks <taskArn> --query 'tasks[0].containers[0].exitCode'`) confirms
success; a non-zero exit code means the job failed and needs the log output
read before retrying.

### Step 8 — Full smoke-test pass (Phase 6)

Per `AWS Readiness/aws-golive-readiness-report.md` §17/§22 Phase 6: CAS
import incl. password-retry, dashboard/holdings/allocation, analytics
(now backed by the real dispatcher instead of perpetually-pending), PDF
export, empty-state for a brand-new user, confirm RDS automated backups are
enabled, watch CloudWatch live during the pass. Google Sign-In and real OTP
delivery are explicitly excluded from this pass (2026-09-11 scope decision) —
not a gap to chase before beta opens.

### Step 9 — Staging CI/CD pipeline (task #20)

Comes after Step 8, not deferred further. Open design question carried over
unchanged from the 2026-09-10 push plan: how `alembic upgrade head` runs in
the pipeline — leaning toward a pre-deploy one-off ECS `RunTask`, matching
the ADR-006/dispatcher `RunTask` pattern already in this repo. Needs a
decision before drafting; no commands given here since the design isn't
finalized yet.

## 4. Explicitly out of scope for this doc

- **Phase 7 hardening** (moving the 7 in-process caches off single-task-only
  state — flagged in the readiness report as the highest-priority item given
  the ~1,000 MAU target — real Google OAuth/OTP providers, NAT Gateway swap,
  structured logging/error tracking): deferred, scoped separately once
  actually needed, per `AWS Readiness/aws-golive-readiness-report.md` §22
  Phase 7.
- **Resource IDs:** §3 now fills these in directly (bastion, RDS host, ECR
  repo, ECS cluster/service, ALB DNS — all stable across the remaining
  applies) rather than leaving them abstract. Only the handful that don't
  exist yet at doc-write time (Phase 4's bucket/distribution, the master
  password, task revisions) are pulled live via an exact command inline in
  the relevant step — never re-typed from a prior session's stale value.
