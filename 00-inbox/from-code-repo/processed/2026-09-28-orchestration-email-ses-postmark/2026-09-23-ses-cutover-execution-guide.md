# SES Cutover — Execution Guide (from here on)

**Source plan:** `Docs/superpowers/plans/2026-09-22-ses-cutover-and-postmark-removal.md`
— read that first for full rationale; this doc is the step-by-step "what to actually
type" companion.

**Both of Part 3's prerequisites are now satisfied — deploy can start:**
- **SES production access: approved 2026-09-23.** Confirmed via AWS's email and the
  SES console (`ap-south-1`, "Production access granted", 50,000/day, 14/sec).
- **Parts 1/2 committed and pushed to `feat/enhanced-ui`: done 2026-09-23.** Two
  commits — `18c13b4` (`refactor(auth): remove Postmark provider and update tests for
  SES`) and `49fd1ae` (`refactor(infra): remove Postmark secrets and variables from
  Terraform`) — both on `feat/enhanced-ui` and pushed to `origin`. Working tree is
  clean.

**Split across two machines**, per the existing project pattern (same as
`ses-terraform-deploy-runbook.md`):
- **Steps 1-4** — your manager's laptop (has Terraform/AWS CLI/Docker + AWS
  credentials already set up per `ses-terraform-deploy-runbook.md` Step 0/1). This is
  everything left to do — start here.

---

## Can any of this be tested before touching staging?

Yes, several parts — worth doing before Step 1 below, since each one is cheap and
catches a different class of mistake:

| What | Where | Needs AWS creds? | Already done? |
|---|---|---|---|
| `SesEmailProvider` logic (mocked boto3) | either laptop, `pytest` | No | Yes — 689 passed, 8 skipped |
| `terraform validate` (syntax/internal consistency) | either laptop | No | Yes — passes clean |
| `docker build` (build only, no push) | either laptop | No | Not yet — cheap to try first |
| **A real SES send, end-to-end, from a local dev backend** | manager's laptop | Yes | Not yet — see below |
| `terraform plan` (preview only, no changes) | manager's laptop | Yes | This is Step 3 |

**The one worth calling out — testing a real SES send locally, before staging:**
since SES uses the default AWS credential chain (`boto3.client("ses", ...)`, no static
key in code), you can prove the actual send path works *before* ever deploying, by
running the backend locally with real settings instead of stub:

```bash
cd backend
# in backend/.env (or exported env vars):
#   EMAIL_DELIVERY_MODE=ses
#   SES_FROM_EMAIL=no-reply@unifolio.in
#   AWS_REGION=ap-south-1
aws configure   # if not already done on this machine — needs an identity with ses:SendEmail
uvicorn app.main:app --reload   # or however this repo's dev server is normally started
```
Then trigger the email-OTP request flow (e.g. via the frontend pointed at this local
backend, or a direct API call) and confirm a real email arrives. This is optional —
Part 3 doesn't require it — but it's a low-risk way to catch a bad `SES_FROM_EMAIL` or
IAM-permission problem before it shows up mid-deploy on staging, where a failure is
noisier to unwind.

**What genuinely can't be tested before deploying:** the ECS task actually picking up
the IAM role's SES permission inside its own network context, the ALB routing
`staging-api.unifolio.in` traffic to the new task, and real cross-domain deliverability
at staging's actual sending reputation. These are exactly what Step 4's verification
covers.

---

## Step 1 — Re-verify environment (manager's laptop)

```bash
aws sts get-caller-identity
```
**Expected output:** JSON with `Account: "811364789032"` and an `Arn` ending in the
IAM user being used (e.g. `.../user/ayush-admim`). If this errors instead (expired
token, no credentials found), fix that before continuing — nothing below will work.

```bash
cd MVP_V1_MF_only
git checkout feat/enhanced-ui
git pull
```
**Expected output:** `Fast-forward` with a file-change summary that includes the 14
files from Parts 1/2 (plus anything else that landed on the branch since — this doc
included). Confirm with:
```bash
git log --oneline -3
```
should show `18c13b4` and `49fd1ae` (Parts 1 and 2) at or near the top.

```bash
cd infra/envs/staging
terraform init
```
**Expected output:** `Terraform has been successfully initialized!` — this should be
a fast no-op per the plan (provider versions unchanged), not a fresh download.

---

## Step 2 — Rebuild and push the image

The image currently in ECR predates Parts 1/2 and **must not be deployed as-is** — it
still has `PostmarkEmailProvider` in it.

```bash
cd ../../../backend   # repo root's backend/
docker build -t unifolio-staging-backend .
```
**Expected output:** build completes with a final `Successfully tagged
unifolio-staging-backend:latest` (or buildkit's equivalent final line). If you hit the
`.pytest_tmp` permission error the plan warns about: `sudo rm -rf .pytest_tmp`, then
retry the build.

```bash
aws ecr get-login-password --region ap-south-1 | \
  docker login --username AWS --password-stdin \
  811364789032.dkr.ecr.ap-south-1.amazonaws.com
```
**Expected output:** `Login Succeeded`.

```bash
docker tag unifolio-staging-backend:latest \
  811364789032.dkr.ecr.ap-south-1.amazonaws.com/unifolio-staging-backend:latest

docker push 811364789032.dkr.ecr.ap-south-1.amazonaws.com/unifolio-staging-backend:latest
```
**Expected output:** layer push progress, ending in a line like
`latest: digest: sha256:... size: ...`.

---

## Step 3 — One combined `terraform apply`

**Caution before exporting the PAN variables:** `TF_VAR_pan_encryption_key` and
`TF_VAR_pan_lookup_pepper` must be the *exact same values* already in use in staging's
Secrets Manager — not newly generated ones. This plan doesn't touch PAN handling at
all, but Terraform will overwrite the `pan_keys` secret with whatever you export; a
different value here would silently break decryption of every PAN already stored in
staging's database.

These values were never written to any file, doc, or commit — per
`Docs/2026-09-19-cas-s3-postmark-secrets-infra.md` Part D1, they were generated once
and exported only as shell `TF_VAR_*` vars for that one `terraform apply`, explicitly
never saved to a `.tfvars` file. The only durable copy is the Secrets Manager secret
Terraform created from them. Read it back and re-export, rather than trying to find
them anywhere else:

```bash
SECRET=$(aws secretsmanager get-secret-value \
  --secret-id unifolio-staging-pan-keys \
  --region ap-south-1 \
  --query SecretString --output text)

export TF_VAR_pan_encryption_key=$(echo "$SECRET" | python3 -c "import json,sys; print(json.load(sys.stdin)['PAN_ENCRYPTION_KEY'])")
export TF_VAR_pan_lookup_pepper=$(echo "$SECRET" | python3 -c "import json,sys; print(json.load(sys.stdin)['PAN_LOOKUP_PEPPER'])")
```
This guarantees an exact match — `terraform plan` should then show **no diff at all**
on the `pan_keys` secret (only the Postmark/SES changes below). **If the
`get-secret-value` call fails ("secret not found")**, Part D of the 2026-09-19 plan was
never actually applied to staging — stop and flag this rather than generating fresh
keys on the spot; it's a bigger gap than this plan assumes.

```bash
export TF_VAR_otp_delivery_mode="stub"
export TF_VAR_email_delivery_mode="ses"
export TF_VAR_ses_from_email="no-reply@unifolio.in"
export TF_VAR_ses_identity_arn="arn:aws:ses:ap-south-1:811364789032:identity/unifolio.in"
```
Do **not** export `TF_VAR_postmark_api_token` or `TF_VAR_postmark_from_email` —
Part 2 deleted those variables; Terraform will error on an unrecognized variable if
you try.

```bash
terraform plan
```
**Expected diff — check this carefully before applying:**
- **Additions:** the SES IAM role policy (`aws_iam_role_policy.backend_task_ses`) and
  its policy document.
- **Destructions (expected and correct here):**
  `aws_secretsmanager_secret.postmark_api_token` and
  `aws_secretsmanager_secret_version.postmark_api_token`.
- **Updated in place:** `aws_iam_role_policy.ecs_secrets_read` (Postmark ARN dropped
  from its `resources` list).
- **Replaced:** `aws_ecs_task_definition.this` (new image + env vars + secrets list);
  `aws_ecs_service.this` updated in place to point at the new revision.
- **Stop and don't apply** if anything outside this list is touched — no RDS, VPC, ECS
  *cluster*, S3 bucket, or PAN-keys secret should appear.

```bash
terraform apply
```
Type `yes` when prompted. **Expected output:** ends with `Apply complete! Resources: X
added, Y changed, Z destroyed.` — the counts should match what `terraform plan` showed.

Watch the rollout (two terminals):
```bash
watch -n 5 'aws ecs describe-services --cluster unifolio-staging --services unifolio-staging-backend \
  --query "services[0].{running:runningCount,desired:desiredCount,rollout:deployments[0].rolloutState}"'
```
```bash
aws logs tail /ecs/staging-backend --follow
curl -s https://staging-api.unifolio.in/health
```
**Expected:** `running` catches up to `desired`, `rolloutState` reaches `COMPLETED`,
`/health` returns a healthy response, and the logs show no crash loop.

---

## Step 4 — Verify

- **Same-domain email OTP** (`@unifolio.in` address) — should work immediately.
- **Cross-domain email OTP** (Gmail, etc.) — the actual point of this migration; now
  unblocked since sandbox mode is gone. This is the one check that couldn't be done
  before Step 4, since sandbox mode blocks unverified recipients.
- **Force a real failure to confirm the 502 fix:** temporarily export a broken
  `TF_VAR_ses_from_email` (an unverified address), `terraform apply` again, attempt a
  send, confirm the frontend shows a real error (not "Unable to connect to the
  server"). Then set it back to `no-reply@unifolio.in` and `terraform apply` once
  more.
- **Phone/SMS OTP regression check** — stub mode, dev-echo OTP still shown in the
  response. This plan touches nothing on that path; this is a pure regression check.

**If something goes wrong mid-rollout:** re-point the ECS service at the previous
task-definition revision without touching Terraform state:
```bash
aws ecs update-service --cluster unifolio-staging --service unifolio-staging-backend \
  --task-definition unifolio-staging-backend:<previous-revision-number>
```
Note the tradeoff from the plan: this rollback restores the previous *image and task
definition*, which still has Postmark code in it — that's the only way email OTP
recovers post-cutover, since there's no live delivery-mode fallback anymore.

---

## Part 4 — Manual DNS cleanup (after Step 4 is fully green, low priority, anytime)

Done directly in the Route 53 console for the `unifolio.in` hosted zone, not code.
Two records were added for Postmark's Sender Signature: a DKIM CNAME (commonly
`pm._domainkey.unifolio.in`) and a Return-Path CNAME (commonly under
`pm-bounces.unifolio.in`). **Confirm the actual names/values in the console before
deleting** — identify them by their *value* pointing at a
`postmarkapp.com`/`pm.mtasv.net`-style target, don't delete by guessing the name
pattern.

**Do not touch:** the Microsoft 365 MX/SPF/DMARC/autodiscover records, or the SES
DKIM CNAME records + MAIL FROM (`mail.unifolio.in`) records — those are live and
needed.

---

## Part 5 — Docs cleanup (no deploy dependency, do anytime)

1. `Docs/email-otp-postmark-technical-documentation.md` — add a one-line note at the
   top: superseded by the cutover plan; Postmark no longer used as of this deploy.
2. `Docs/orchestration/ses-terraform-deploy-runbook.md` — add a one-line pointer at
   the top: superseded by `2026-09-22-ses-cutover-and-postmark-removal.md` for deploy
   purposes.
3. `CLAUDE.md`'s Session State section and `session.md` — update once Step 4 is fully
   green: SES live in staging, Postmark fully removed, phone/SMS still stub.

---

*This guide was written after checking Part 1/2's diffs against the plan and
re-running the backend test suite and `terraform validate` fresh — see the
conversation history for that verification. It doesn't replace the source plan; it's
the runnable version of its Part 3-5.*
