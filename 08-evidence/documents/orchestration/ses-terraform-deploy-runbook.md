# SES Migration — Terraform Apply & Deploy Runbook

**For:** whoever is running this from their own laptop (Terraform/AWS CLI access).
**Status as of 2026-09-22:** all code is merged and reviewed on `feat/enhanced-ui`
(commits `9c514d4`..`61df3b9`, full backend suite green: 689 passed, 8 skipped, 0
failed). AWS-side SES setup (Part 1 of the full plan) is done: `unifolio.in` is a
verified SES domain identity in `ap-south-1`, sandbox test email confirmed working.
**What's left: build + push the new image, apply the Terraform, deploy, and flip the
switch in staging.** Full source plan, if you want the complete rationale behind any
step below: `Docs/superpowers/plans/2026-09-21-ses-email-provider-migration.md`.

**Important — this is not a Terraform-only step.** `terraform apply` alone changes
*infrastructure* (the IAM permission, the `SES_FROM_EMAIL` env var), but the ECS task
definition points at a fixed image tag (`:latest` in ECR) that Terraform does not
rebuild. If you skip Step 3 below and go straight to `terraform apply`, staging
redeploys with the **old container image** — the one without `SesEmailProvider`,
`EmailSendError`, etc. — even though the Terraform state and env vars look correct.
The image has to be rebuilt from this session's code and pushed to ECR first.

Known values already decided (from Part 0/Part 1, done this session):
- **SES send-from address:** `no-reply@unifolio.in`
- **SES domain identity ARN:** `arn:aws:ses:ap-south-1:811364789032:identity/unifolio.in`
- **SES production access:** requested 2026-09-22, status "Under review" as of
  submission. **Check AWS Console → SES → Account dashboard before Step 7 below** —
  until it's approved, cross-domain (non-`@unifolio.in`) sends will fail (sandbox mode
  only allows individually-verified recipients).

---

## 0. Prerequisites on your laptop

1. **AWS CLI v2** — https://awscli.amazonaws.com (pick your OS's installer from that
   page). Verify: `aws --version`.
2. **Terraform, exact version `1.16.1`** — this repo pins
   `required_version = "= 1.16.1"` in `infra/envs/staging/versions.tf`; a newer version
   will refuse to run. Download from
   https://releases.hashicorp.com/terraform/1.16.1/ (pick your OS/arch) or via a
   version manager (`tfenv install 1.16.1`) if you use one. Verify: `terraform
   version`.
3. **Docker** — needed to build the backend image (Step 3). Any recent Docker
   Desktop/Engine install is fine.
4. **AWS credentials** for an IAM identity with permission to manage this project's
   infra (IAM role policies, ECS, ECR, S3 state bucket, DynamoDB lock table, SES). The
   `ayush-admin` IAM admin user (created 2026-09-07, full admin) is the one already
   used for this project — decide together whether to use that user's own access key
   or a separate one for your laptop. To create an access key: **AWS Console → IAM →
   Users → (the user) → Security credentials tab → Create access key → "Command Line
   Interface (CLI)" use case → Create → download/copy the key ID + secret (shown only
   once)**. Then run:
   ```
   aws configure
   ```
   and paste in the Access Key ID / Secret Access Key when prompted (region:
   `ap-south-1`).

---

## 1. One check before touching Terraform

The repo's Terraform manages a specific IAM role (`aws_iam_role.backend_task` in
`infra/modules/backend/main.tf`) that this migration attaches a new SES permission to.
Confirm the *actually-running* staging ECS task uses that same role — if staging was
ever set up or hand-patched outside Terraform, this check catches that before you
apply:

**AWS Console → ECS → cluster `unifolio-staging` → service `unifolio-staging-backend`
→ current task definition → "Task role"** — confirm it's exactly
**`unifolio-staging-backend-task-role`** (the name Terraform's `aws_iam_role.backend_task`
resource creates, per `infra/modules/backend/main.tf`).

If it doesn't match, stop and figure out why before applying — the new SES permission
would attach to a role nothing actually uses.

---

## 2. Get the code and set up Terraform

```bash
git clone https://github.com/ayushkarnawat/MVP_V1_MF_only.git
cd MVP_V1_MF_only
git checkout feat/enhanced-ui
cd infra/envs/staging
terraform init
```

(`terraform init` downloads the pinned `aws`/`random` provider versions and connects
to the existing remote state — S3 bucket `unifolio-tfstate-staging-811364789032`,
DynamoDB lock table `unifolio-tfstate-lock-staging`, both already provisioned. Your
IAM identity needs read/write on both.)

---

## 3. Build and push the current code's image to ECR

This is the step that actually gets this session's code (`SesEmailProvider`,
`EmailSendError`, the 502 handling, etc.) into staging. Do this **before**
`terraform apply` in Step 5, so the new task-definition revision that apply creates
picks up the freshly-pushed image, not a stale one.

```bash
cd backend
docker build -t unifolio-staging-backend .
```

If the build fails with `error from sender: failed to xattr .pytest_tmp: permission
denied`, a stale `backend/.pytest_tmp` dir with broken permissions is the cause even
though it's `.dockerignore`'d (BuildKit still stats every path during its context
walk) — `sudo rm -rf .pytest_tmp`, then re-run the build.

```bash
aws ecr get-login-password --region ap-south-1 | \
  docker login --username AWS --password-stdin 811364789032.dkr.ecr.ap-south-1.amazonaws.com

docker tag unifolio-staging-backend:latest \
  811364789032.dkr.ecr.ap-south-1.amazonaws.com/unifolio-staging-backend:latest
docker push 811364789032.dkr.ecr.ap-south-1.amazonaws.com/unifolio-staging-backend:latest
```

Pushing doesn't redeploy anything by itself — the running ECS task keeps serving the
old image until Step 5's `terraform apply` (or a manual force-new-deployment) actually
rolls it out.

---

## 4. Add the two new variables to your `terraform.tfvars`

`terraform.tfvars` is gitignored — you (or whoever already manages staging's infra)
should already have a working copy with all the existing required values (DB
password, PAN encryption keys, etc.) from prior sessions. **Add these two new lines**
to that existing file — don't recreate it from scratch:

```hcl
ses_from_email   = "no-reply@unifolio.in"
ses_identity_arn = "arn:aws:ses:ap-south-1:811364789032:identity/unifolio.in"
```

Leave `email_delivery_mode` as `"postmark"` for now — don't flip it yet (Step 7 below
does that, deliberately as a separate step).

---

## 5. Plan, review, apply

```bash
terraform plan
```

**Expected diff — additive only:**
- One new resource: `aws_iam_role_policy.backend_task_ses` (grants `ses:SendEmail`/
  `ses:SendRawEmail` on the `unifolio.in` SES identity, scoped to the existing backend
  task role)
- One new data source: `aws_iam_policy_document.backend_task_ses`
- `aws_ecs_task_definition.this` shows as `# forces replacement` — this is expected
  and correct, it's how ECS task definitions pick up a new env var
  (`SES_FROM_EMAIL`); it creates a **new revision**, not a destroy of the running one
- `aws_ecs_service.this` shows as updated in-place to point at the new task
  definition revision — this is what actually triggers the redeploy

**Stop and don't apply if you see anything destroyed/replaced beyond those two
resources** — in particular, no existing IAM role, ECS cluster, RDS instance, or S3
bucket should appear as destroyed. If something unexpected shows up, paste the plan
output back before proceeding.

If the plan looks right:

```bash
terraform apply
```

Type `yes` when prompted. This redeploys the backend — combined with the fresh image
pushed in Step 3, it rolls out the new code, new task-def revision with
`SES_FROM_EMAIL` added, still on Postmark since `email_delivery_mode` is untouched.

**Watch the deployment live — not an optional nicety.** `aws_ecs_service.this` runs
with `deployment_minimum_healthy_percent = 0` / `deployment_maximum_percent = 100` (a
deliberate, pre-existing tradeoff — the app relies on single-process in-memory state
today, so deploys are stop-then-start, not rolling), meaning **the old task is
stopped before the new one is confirmed healthy** — there's a window with zero
running tasks even on a normal deploy. Immediately after `terraform apply` returns:

```bash
watch -n 5 'aws ecs describe-services --cluster unifolio-staging --services unifolio-staging-backend \
  --query "services[0].{running:runningCount,desired:desiredCount,rollout:deployments[0].rolloutState}"'
```

and in another terminal:

```bash
aws logs tail /ecs/staging-backend --follow
curl -s https://staging-api.unifolio.in/health
```

Don't move on until `running == desired`, `rolloutState: COMPLETED`, and the logs
show clean startup with no crash/restart looping. **If it's crash-looping:** see
"If something goes wrong" at the bottom.

---

## 6. Regression check — still on Postmark

Confirm same-domain (`@unifolio.in`) email OTP still works exactly as before this
change (signup or login flow, real email delivery mode, not stub). This is the sanity
check that Tasks 2-6's code changes didn't break the existing Postmark path — and,
combined with Step 3, that the newly-built image is actually the one running (not a
stale cached one).

**Check SES production access status now, before Step 7:** AWS Console → SES →
Account dashboard (region `ap-south-1`) → confirm it no longer says "sandbox." If
still under review, you can still test same-domain sends in Step 7 below, but
cross-domain (Gmail, etc.) sends will fail until it clears — that's expected, not a
bug.

---

## 7. Cut over to SES (temporary, for testing)

Edit `terraform.tfvars`:

```hcl
email_delivery_mode = "ses"
```

```bash
terraform apply
```

This triggers another redeploy (same watch command as Step 5 — the image doesn't
change this time, only the env var, but it's still worth watching). Then test:

- **Same-domain send** (`@unifolio.in`) — sanity check, should work regardless of
  sandbox/production status.
- **Cross-domain send** (a Gmail address, etc.) — this is the actual point of the
  whole migration. Works only if SES production access has been approved (see above);
  if still in sandbox, verify a personal test address individually in the SES console
  first (Identities → Create identity → Email address) to test before approval
  clears.
- **Force a real failure to confirm the 502 fix works end-to-end**: temporarily set
  `ses_from_email` to something invalid/unverified (e.g. a typo'd address not on the
  verified domain), `terraform apply` again, attempt a send, confirm the frontend
  shows a real error message — not "Unable to connect to the server." Then set
  `ses_from_email` back to `no-reply@unifolio.in` and `terraform apply` once more.

---

## 8. Cutover & cleanup (once Step 7 is fully green)

1. Leave `email_delivery_mode = "ses"` as the live staging value — no further action
   needed here, it's already applied from Step 7.
2. **Don't remove Postmark.** Keep `PostmarkEmailProvider`, the Postmark
   env vars/DNS records in place, dormant, as a documented rollback path — flipping
   `email_delivery_mode` back to `"postmark"` later costs nothing to keep available.
3. Update `Docs/email-otp-postmark-technical-documentation.md` with a short note that
   it's superseded by the SES plan for the production delivery path, and update
   `session.md`'s "still open" list to drop the Postmark-approval-pending item.

---

## If something goes wrong mid-rollout

Roll back the ECS service to the previous task-definition revision without touching
Terraform state:

```bash
aws ecs update-service --cluster unifolio-staging --service unifolio-staging-backend \
  --task-definition unifolio-staging-backend:<previous-revision-number>
```

(Find the previous revision number via `aws ecs list-task-definitions --family-prefix
unifolio-staging-backend --sort DESC` — the one before whatever this session's
`terraform apply` created.) This doesn't require `terraform destroy`; diagnose the
underlying issue (check `aws logs tail /ecs/staging-backend` for the crash reason)
with Terraform still applied, then re-apply once fixed.
