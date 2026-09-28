# AWS Staging Deployment — PAN/CAS/S3/Postmark + Fund Score

**Who this is for:** whoever runs this against the real AWS account. Assumes
familiarity with `terraform`, `git`, `docker`, and `psql`/`alembic`, but no
prior context on this specific body of work. Modeled on the same structure as
`Docs/superpowers/plans/2026-09-11-aws-staging-prerequisites.md` (the previous
push's prerequisites doc) — read that one for AWS CLI/Terraform/Docker
install steps if this is the first time running any of this from a fresh
machine; this doc doesn't repeat first-time tool setup.

**Scope:** deploys the 52 commits on `feat/enhanced-ui` since the last staging
push covering three features — Fund Score card redesign (pure app code, no
infra change), the Postmark email provider cutover, and PAN
encryption/CAS-file S3 retention (`ayushkarnawat/MVP_V1_MF_only`
`6de6ea7`..`135fa64`). Full infra/code detail and rationale for every change:
`Docs/2026-09-19-cas-s3-postmark-secrets-infra.md` — that doc is the design
record; this one is the copy-paste runbook.

**No AWS/Terraform/Docker command in this doc has been executed by Claude
against real state** — read-only checks (`describe-*`, `list-*`,
`terraform plan`) were used to verify the facts below, but every
state-mutating command (`terraform apply`, `docker push`,
`aws ecs update-service`, `alembic upgrade`) is marked **[user-run]** and is
for you to run yourself, per this project's established division of labor.

---

## 1. Where things stand right now (verified this session, not assumed)

**Live in `ap-south-1` today** (real, billable AWS resources — this is not a
from-scratch environment):
- VPC, subnets, fck-nat, SSM bastion (`i-0b67d40d9b58b7814`) — Phase 0/1.
- KMS CMK `alias/unifolio-staging-cmk`, RDS PostgreSQL 16 at
  `staging-rds.ctu88scmut9m.ap-south-1.rds.amazonaws.com:5432` — Phase 2.
- ECR repo `unifolio-staging-backend` — `:latest` tag currently points at
  commit **`b972e65`, pushed 2026-09-11** — 8 days and this entire 52-commit
  body of work stale. A fresh build/push (§3 Step 3) is a real requirement,
  not a formality.
- ECS cluster `unifolio-staging`, service `unifolio-staging-backend`
  (`ACTIVE`, 1/1 running, task-definition revision `2`), ALB at
  `unifolio-staging-alb-958627457.ap-south-1.elb.amazonaws.com` with a live
  HTTPS (443) listener — Phase 3.
- CloudFront distribution serving `staging.unifolio.in` (status `Deployed`),
  ACM cert for `staging-api.unifolio.in` (`ISSUED`) — Phases 4 and 5 are
  **both already applied**, not just authored (superseding the "Phase 4
  authored, not applied" / "Phase 5 not yet dispatched" notes in
  `session.md`, which predate this — that file is stale relative to current
  `git log`, don't trust it over what's below). The S3 bucket backing that
  distribution holds whatever static frontend build was last manually
  uploaded — equally stale relative to this branch's `HEAD` as the backend
  image, and equally in need of a fresh deploy (§3 Step 7).
- Database schema: **`0011` (head as of the 2026-09-09 migration run)**.
  This branch adds migrations `0012`-`0015` — not yet applied to real RDS.

**Not yet live** (this plan's own additions, confirmed absent via direct
`aws secretsmanager list-secrets` / `aws s3api list-buckets` this session,
not inferred from the repo):
- The `pan-keys` and `postmark-api-token` Secrets Manager secrets.
- The `cas-files` S3 bucket.
- The `cas_file_expiry_daily` scheduled job.
- Migrations `0012`-`0015` on the real RDS instance.
- Any of this branch's application code in the running ECS tasks (the image
  is 8 days stale).

A read-only `terraform plan` against the real remote state (run this session,
not applied) confirms the exact diff this push produces: **21 to add, 8 to
change, 8 to destroy** — the 8 destroys are old ECS task-definition revisions
and one renamed IAM inline policy being replaced, never the RDS instance,
VPC, or ECS cluster/service. Full breakdown: §3 Step 5.

---

## 2. Manual/external prerequisites — verify before running §3

- [ ] AWS CLI configured for account `811364789032`, region `ap-south-1`
      (`aws sts get-caller-identity` should return that account ID).
- [ ] Terraform installed matching `infra/envs/staging/.terraform.lock.hcl`
      (currently pinned to `hashicorp/aws` `6.63.0`).
- [ ] Docker Desktop running with WSL integration enabled (re-verify this
      each time — it's been the recurring blocker on this machine).
- [ ] Access to `account.postmarkapp.com` for the Sender Signature
      confirmation (§3 Step 4), and to the mailbox that will send OTP email.
- [ ] The real Postmark server API token, ready to export as
      `TF_VAR_postmark_api_token`.
- [ ] Nothing about the marketing site (`unifolio.in` apex), mail
      (MX/SPF/DMARC), or `docs.unifolio.in` is touched by any command below.

---

## 3. Command sequence

### Step 0 — Shared constants

Export once per terminal session; every step below assumes these are set.

```bash
export REPO_ROOT="/mnt/d/Unifolio code"
export AWS_ACCOUNT_ID="811364789032"
export AWS_REGION="ap-south-1"
export ECR_REPO="811364789032.dkr.ecr.ap-south-1.amazonaws.com/unifolio-staging-backend"
export ECS_CLUSTER="unifolio-staging"
export ECS_SERVICE="unifolio-staging-backend"
export ALB_DNS="unifolio-staging-alb-958627457.ap-south-1.elb.amazonaws.com"
export BASTION_ID="i-0b67d40d9b58b7814"
export RDS_HOST="staging-rds.ctu88scmut9m.ap-south-1.rds.amazonaws.com"
export RDS_PORT="5432"
export DB_NAME="unifolio"
export DB_USER="unifolio"
```

### Step 1 — Generate PAN keys and gather secrets **[user-run]**

```bash
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

Run twice — the two outputs must differ (encryption key vs. lookup pepper).
Then, in this same terminal, export everything `terraform apply` will need:

```bash
export TF_VAR_pan_encryption_key="<first value above>"
export TF_VAR_pan_lookup_pepper="<second value above>"
export TF_VAR_postmark_api_token="<real Postmark server API token>"
export TF_VAR_postmark_from_email="aditi.shanbhag@unifolio.in"
export TF_VAR_otp_delivery_mode="postmark"
export TF_VAR_email_delivery_mode="postmark"
```

2026-09-19 update: Postmark is confirmed working, so both delivery-mode vars
are set to `"postmark"` here — the apply in Step 5 goes live with real email
directly, no separate flip-and-reapply.

Never write any of these to a `.tfvars` file or commit them anywhere.

### Step 2 — Run migrations `0012`→`0015` against real RDS **[user-run]**

Open the bastion tunnel (leave this terminal running):

```bash
aws ssm start-session --target "$BASTION_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$RDS_HOST\"],\"portNumber\":[\"$RDS_PORT\"],\"localPortNumber\":[\"5433\"]}"
```

In a second terminal:

```bash
export PGPASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id "$(aws secretsmanager list-secrets --query "SecretList[?starts_with(Name, 'rds!db-')].Name" --output text)" \
  --query SecretString --output text | python3 -c "import json,sys; print(json.load(sys.stdin)['password'])")

cd "$REPO_ROOT/backend"
DATABASE_URL="postgresql://${DB_USER}:${PGPASSWORD}@localhost:5433/${DB_NAME}" .venv/bin/alembic upgrade head
DATABASE_URL="postgresql://${DB_USER}:${PGPASSWORD}@localhost:5433/${DB_NAME}" .venv/bin/alembic current
```

Confirm the last command prints `0015 (head)`. Migrating first, before the
new image is deployed, means the old running task keeps serving traffic
against a schema its own (older) code already tolerates, and the new task
(Step 5) never boots against a schema it wasn't written for.

Do NOT close the SSM tunnel terminal until this step's `alembic current`
check has printed `0015 (head)`.

### Step 3 — Build and push the current codebase's image **[user-run]**

```bash
cd "$REPO_ROOT/backend"
docker build -t unifolio-staging-backend .
```

If this fails with `error from sender: failed to xattr .pytest_tmp:
permission denied`: a stale `backend/.pytest_tmp` directory has broken 9p
permissions from an interrupted test run (`.dockerignore`'d, but BuildKit
still stats every path during its context walk). Fix and retry:

```bash
sudo rm -rf .pytest_tmp
docker build -t unifolio-staging-backend .
```

```bash
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_REPO"
docker tag unifolio-staging-backend:latest "$ECR_REPO:latest"
docker push "$ECR_REPO:latest"
```

Pushing alone doesn't redeploy anything — the running ECS task keeps serving
on the old image until Step 5's `terraform apply` updates the service.

### Step 4 — Confirm the Postmark Sender Signature **[user-run]**

**2026-09-19 update: done — two separate steps happened, not one.**

**Step 1 (single Sender Signature):** confirmed `aditi.shanbhag@unifolio.in`
via Postmark's email-click flow
(`signatures.postmarkapp.com/confirm/success-first`) — this alone would only
authorize that one address.

**Step 2 (Domain Signature, done afterward):** added two DNS records to
Route 53, verified via direct DNS lookup (not just trusting the Postmark
dashboard):
- DKIM TXT record: `20260917063050pm._domainkey.unifolio.in`
- Return-Path CNAME: `pm-bounces.unifolio.in` → `pm.mtasv.net`

Postmark's `account.postmarkapp.com/signature_domains/8114367` → DNS
Settings page shows both **Verified**, plus a third status card titled
**"Send from any address," status Active**, reading: *"Excellent, your
domain is verified! We enabled the ability to send from any email address
on this domain when you added and verified a DKIM DNS record."* That's
Postmark's own statement the grant is domain-wide, not address-locked.

Practical effect: `postmark_from_email` can be **any** address
`@unifolio.in`. This deployment uses `aditi.shanbhag@unifolio.in`
specifically (a real inbox someone owns), but any other `@unifolio.in`
address works too.

For reference, the steps Step 1 involved:

1. Log into `account.postmarkapp.com`.
2. **Sender Signatures** → **Add Sender Signature** → the exact address that
   will be `TF_VAR_postmark_from_email`.
3. Postmark emails a confirmation link to that address (lands in the
   existing Microsoft 365 mailbox — no DNS change needed).
4. Whoever owns that mailbox clicks the link. Signature shows "Confirmed."

Since this is confirmed, Step 5's apply goes live with real Postmark
delivery directly (`otp_delivery_mode`/`email_delivery_mode` set to
`"postmark"` in Step 1) — no separate flip-and-reapply step. This is a
deliberate change from the plan's earlier draft, which defaulted both vars
to `"stub"` for a follow-up apply; see the "Deviation from the original
plan" note in `Docs/2026-09-19-cas-s3-postmark-secrets-infra.md` Part A3.

### Step 5 — Apply the Terraform **[user-run]**

```bash
cd "$REPO_ROOT/infra/envs/staging"
terraform init      # only needed the first time, or after adding the storage module
terraform plan
```

Expect **21 to add, 8 to change, 8 to destroy** (verified against real
remote state this session):

- **Add:** the `cas-files` S3 bucket + its 4 sub-resources (public-access
  block, versioning, SSE-KMS encryption, 30-day lifecycle rule); the
  `pan-keys` and `postmark-api-token` secrets + their 2 versions; the new
  `backend_task_cas_files` IAM policy; the `cas_file_expiry_daily` job's log
  group, task definition, and schedule; the new `PassCasFileExpiryTaskRole`
  IAM statement.
- **Change:** `aws_ecs_service.this` (new task-definition reference), the
  scheduler's own IAM role policy, and the 6 pre-existing schedule resources
  (new task-def ARNs).
- **Destroy:** the `rds_master_secret_read`→`ecs_secrets_read` renamed
  policy (delete+create, inline policy only, not the role — see §4 for why
  this rename happened) and 6 old scheduler-job task-definition revisions
  being replaced (all 6 pre-existing jobs pick up 2 new harmless env vars,
  forcing a new revision even though only the new job needs them; old
  revisions stay in ECS's history, nothing is actually lost).

**If the plan shows anything destroying the RDS instance, VPC, or ECS
cluster/service resource itself (as opposed to updating it in-place) — stop
and don't apply.**

```bash
terraform apply
```

Applying updates the ECS service to the new task-definition revision, which
— combined with the fresh image from Step 3 — starts the new deployment
immediately.

### Step 6 — Watch the deployment live **[user-run]**

This is the mitigation for this apply's real risk, not an optional check.
`aws_ecs_service.this` runs `deployment_minimum_healthy_percent = 0` (a
deliberate pre-existing tradeoff — the app relies on single-process
in-memory state, so deploys are stop-then-start, not rolling): the old task
is stopped before the new one is confirmed healthy, so there's already a
window with zero running tasks on any normal deploy. This apply adds a new
PAN-key startup dependency on top of that: if `PAN_ENCRYPTION_KEY`/
`PAN_LOOKUP_PEPPER` are wrong or the execution role can't read the new
secrets, the new task crash-loops — and because the old task is already
gone, that's a full outage, not a degraded one, until someone watching
catches it.

```bash
watch -n 5 "aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE \
  --query 'services[0].{running:runningCount,desired:desiredCount,deployments:deployments[].{status:status,rolloutState:rolloutState}}'"
```

In another terminal:

```bash
aws logs tail /ecs/staging-backend --follow
curl -s https://staging-api.unifolio.in/health
```

Don't proceed to Step 7 until `runningCount == desiredCount`,
`rolloutState: COMPLETED`, and the logs show clean startup with no
repeated crash/restart cycles.

**If it's crash-looping:** roll back to the last known-good revision
(confirm the actual previous revision number first — `2` was healthy as of
this session, but check `aws ecs list-task-definitions --family-prefix
unifolio-staging-backend` if more applies have landed since):

```bash
aws ecs update-service --cluster "$ECS_CLUSTER" --service "$ECS_SERVICE" \
  --task-definition unifolio-staging-backend:2
```

Rolling back the service doesn't require `terraform destroy` — diagnose the
secret/IAM issue with Terraform still applied.

### Step 7 — Rebuild and deploy the frontend **[user-run]**

**A gap this doc's earlier draft in this session had:** Steps 0-6 only
rebuild and redeploy the **backend**. `module.frontend`'s S3 bucket +
CloudFront distribution are already live (confirmed in §1), but nothing
above pushes a new frontend build into that bucket — without this step,
`staging.unifolio.in` keeps serving whatever static build was uploaded in
the last manual deploy, regardless of what's on `HEAD` now (the Fund Score
redesign, the NAV-date fix, and everything else merged into this branch
since then). The 2026-09-11 version of this doc had this as its own "Step
6"; it was dropped when this doc was rewritten for the CAS/Postmark push
and needs to go back in before running the smoke tests below.

```bash
cd "$REPO_ROOT/frontend"
VITE_API_BASE_URL=https://staging-api.unifolio.in npm run build
aws s3 sync dist/ "s3://$(terraform -chdir="$REPO_ROOT/infra/envs/staging" output -raw s3_bucket_name)/" --delete
aws cloudfront create-invalidation \
  --distribution-id "$(terraform -chdir="$REPO_ROOT/infra/envs/staging" output -raw cloudfront_distribution_id)" \
  --paths "/*"
```

No `VITE_GOOGLE_OAUTH_CLIENT_ID` — deliberately left unset for staging, a
pre-existing 2026-09-11 scope decision, unrelated to this push. CloudFront
invalidation takes a couple of minutes to propagate — hard-refresh (or wait)
before checking the Fund Score/NAV-date item in Step 8 below if the old
build still appears to be serving.

### Step 8 — One-off job run, then smoke tests **[user-run]**

Run the new CAS-expiry job once manually rather than waiting for its first
19:00 IST cron fire:

```bash
terraform output -raw networking   # get the private_app_subnet_ids / ecs_security_group_id below
aws ecs run-task --cluster "$ECS_CLUSTER" \
  --task-definition unifolio-staging-job-cas-file-expiry-daily \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<private-app-subnet-ids>],securityGroups=[<ecs-security-group-id>],assignPublicIp=DISABLED}"
```

Then, against `https://staging.unifolio.in`:

1. `terraform output cas_files_bucket_name` → `aws s3 ls s3://<that name>/`
   (empty right after creation).
2. Do a real CAS import → `aws s3 ls s3://<cas-files-bucket-name>/
   --recursive` → confirm a `<user_id>/<import_id>.pdf` object exists.
3. A real PAN encrypt/decrypt round-trip (import a CAS containing a PAN;
   confirm it displays correctly on retrieval) — proves the
   Secrets-Manager-sourced keys are actually being read at runtime, not
   just present in the task definition.
4. The cross-account-PAN-block and override-mismatch paths live (`6de6ea7`/
   `7e1e400`) — the feature this whole push exists to support.
5. Fund Score card and the NAV-date fix: open a portfolio with holdings,
   confirm the redesigned card renders (tier progress bar, inline verdict,
   factor groups) and dates show `DD-MM-YYYY`. These are frontend changes —
   this only proves anything if **Step 7 above actually ran**.
6. OTP/email: `otp_delivery_mode`/`email_delivery_mode` are `"postmark"`
   from Step 5's apply (per Step 1's exports), so sign up with a real email
   directly and confirm the OTP actually arrives in the inbox at
   `postmark_from_email` — exercising the Postmark secret injection
   end-to-end, not just that the container booted. No separate
   flip-and-reapply step.

---

## 4. What's actually being renamed in this plan (the IAM question)

`data.aws_iam_policy_document.rds_master_secret_read` and
`resource.aws_iam_role_policy.rds_master_secret_read` — both in
`infra/modules/backend/main.tf`, both attached to
`aws_iam_role.ecs_task_execution` (the role ECS itself assumes to pull
secrets/images before the container starts, distinct from
`aws_iam_role.backend_task`, the app's own runtime role) — are renamed to
`ecs_secrets_read`. Reason: the policy started out granting exactly one
thing, `secretsmanager:GetSecretValue` on the RDS master-user secret. This
push adds a second statement granting the same action on the two new
`pan-keys`/`postmark-api-token` secrets, so "RDS master secret read" no
longer describes what the policy actually does — it's now "read every
secret the execution role needs." Shows up in `terraform plan` as one
delete + one create of the `aws_iam_role_policy` resource (safe — it's an
inline policy document being replaced, not the IAM role itself, which is
untouched), and required updating the `depends_on` block on both ECS task
definitions (`analytics_recompute` and the request-serving `this`) to point
at the new resource name instead of the old one.

---

## 5. Explicitly out of scope for this doc

- Phase 6 (broader validation) / Phase 7 (CI/CD, immutable image tags) —
  `image_tag = "latest"` stays mutable for this push; task #20 tracks
  drafting the staging pipeline separately.
- ADR-006's EventBridge Scheduler + ECS Fargate job scripts beyond
  `cas_file_expiry_daily` — the other 6 jobs already exist and are untouched
  in behavior by this push (only their env vars change, per §3 Step 5).
- Anything about the marketing site (`unifolio.in` apex), mail records, or
  `docs.unifolio.in`.
- Production (a separate AWS account/environment, not started).
