# SES Cutover + Full Postmark Removal — Consolidated Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** planning only, per explicit user instruction — do not implement or deploy
any part of this until told to. This doc supersedes
`Docs/orchestration/ses-terraform-deploy-runbook.md` for deploy purposes (that file's
Steps 0-2 are still accurate and already done; its Steps 3-8 are superseded by Part 3
below, which reflects a decision made after that runbook was written).

**Supersedes/extends:** `Docs/superpowers/plans/2026-09-21-ses-email-provider-migration.md`
(Tasks 1-6 of that plan are done, committed `9c514d4`..`61df3b9`, reviewed clean, 689
tests passing — that work is not being redone). This plan is the *next* phase: cut
staging over to SES, and — per a decision made after that plan shipped — remove
Postmark entirely rather than keep it as a dormant rollback path.

**Decisions this plan is built on (2026-09-22):**
- Full Postmark removal: code, Terraform/Secrets Manager, and DNS. Not kept dormant.
  (Cost of keeping it dormant would have been $0 — free tier, no expiry — this is a
  deliberate simplicity choice, not a cost-driven one.)
- Phone/SMS OTP stays on `"stub"` in staging, unchanged, until a real SMS provider is
  chosen later (separate, not-yet-scoped work) — nothing in this plan touches
  `otp_delivery_mode` or the phone/SMS code path at all.
- Nothing gets deployed until SES production access clears the AWS sandbox review
  (a support case was filed 2026-09-22 with additional use-case detail, after the
  initial short-form request came back asking for more information — normal for a new
  account, not a rejection).

---

## Part 0 — What's already done, and what needs redoing

Your manager has already completed, on his laptop, from
`ses-terraform-deploy-runbook.md`:

- **Step 0 (prerequisites):** AWS CLI v2 and Terraform `1.16.1` installed. **Don't
  redo.**
- **Step 1 (IAM role check):** confirmed (or should be reconfirmed if there's any
  doubt) that staging's running ECS task role is
  `unifolio-staging-backend-task-role`. **Don't redo unless something about staging's
  infra has changed since.**
- **Step 2 (clone + init):** repo cloned, `git checkout feat/enhanced-ui`, `terraform
  init` run against the existing remote state. **Don't redo the clone** — just `git
  pull` when it's time to deploy, to pick up this plan's new commits once they land.
  `terraform init` is safe to skip re-running unless the provider versions change
  (they won't, from this plan).
- **Step 3 (build + push image to ECR):** an image was built and pushed to
  `811364789032.dkr.ecr.ap-south-1.amazonaws.com/unifolio-staging-backend:latest`.
  **This image is now stale and must NOT be deployed as-is** — it contains only the
  original SES-addition commits (`9c514d4`..`61df3b9`), not this plan's Postmark
  removal (Part 1/2 below, not yet written at the time that image was built). **Step 3
  will need to be re-run** once Part 1/2's commits land, producing a fresh image that
  has both the SES support and the Postmark removal together. Don't deploy the
  currently-pushed image to staging.

**Nothing has been applied to staging yet.** `terraform apply` has never run for any
of this session's work — staging is still on the pre-SES-migration code and
Postmark-only configuration, exactly as it was before this whole effort started. This
means there is no "dormant intermediate state" to protect: the eventual real deploy
(Part 3) is a single jump from *old Postmark-only* directly to *new SES-only*, not a
staged rollout through an intermediate state. That's why this plan doesn't need a
"deploy the SES addition first, keep Postmark as a working fallback, verify, then
remove Postmark later" two-step rollout — the code for that intermediate state
(SES added, Postmark still present) already exists and is committed, but nothing has
used it in staging yet, so there's no reason to deploy it just to immediately replace
it again.

**Important, load-bearing constraint for Part 3:** once Part 1's code lands, the
running application can no longer serve email OTP at all if `EMAIL_DELIVERY_MODE`
is left at `"postmark"` — `get_email_provider()`'s `"postmark"` branch will no longer
exist, so it falls through to `NoEmailProviderConfiguredError`, which (by an explicit
Global Constraint from the original SES plan, unchanged) is **not** caught by the
`EmailSendError`→502 handling — it's a deploy-time misconfiguration error, meant to
fail loudly. If that ever happened in staging, every email-OTP attempt would 500. This
means **the new image and the `email_delivery_mode = "ses"` Terraform value must be
deployed together, in the same apply** — never deploy Part 1/2's code while staging's
Terraform still says `"postmark"`. Part 3 is written to enforce this ordering.

---

## Part 1 — Backend code: remove Postmark entirely

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/auth/email_provider.py`
- Modify: `backend/app/services/auth/otp.py` (docstring only, no logic change)
- Modify: `backend/tests/services/auth/test_email_provider.py`
- Modify: `backend/tests/services/auth/test_otp.py`
- Modify: `backend/tests/conftest.py` (comment only)
- Modify: `backend/.env.example`

### Task 1.1 — `config.py`

Remove these two lines (currently lines 11-12):
```python
    postmark_api_token: str = ""
    postmark_from_email: str = ""
```
`ses_from_email: str = ""` (line 13) stays untouched.

### Task 1.2 — `email_provider.py`

1. Module docstring (lines 1-10): rewrite to describe only Stub/SES, drop the Postmark
   sentence.
2. Remove `import httpx` (line 18) — nothing else in this file uses it once
   `PostmarkEmailProvider` is gone (verified: `httpx` appears only inside
   `PostmarkEmailProvider.send_email` and its `except` clause in the current file).
3. Remove `POSTMARK_SEND_URL = "https://api.postmarkapp.com/email"` (line 25).
4. Delete the entire `PostmarkEmailProvider` class (current lines 50-76).
5. In `get_email_provider()`, remove the `"postmark"` branch:
   ```python
   def get_email_provider() -> EmailProvider:
       if settings.email_delivery_mode == "stub":
           return StubEmailProvider()
       if settings.email_delivery_mode == "ses":
           return SesEmailProvider()
       raise NoEmailProviderConfiguredError(
           f"No real EmailProvider is configured for EMAIL_DELIVERY_MODE={settings.email_delivery_mode!r}. "
           "Set EMAIL_DELIVERY_MODE to 'ses' (with SES_FROM_EMAIL configured) "
           "to send real email, or back to 'stub' for local development."
       )
   ```

### Task 1.3 — `otp.py` docstring only

Find the sentence describing the live/stub split example (around the module or
function docstring referencing "live via Postmark while phone/SMS stays in dev-stub
mode" and "same pattern as Postmark") and reword both to say "via SES" / "same pattern
as SES" instead. No behavioral change — `otp.py` never referenced Postmark in actual
code, only in comments.

### Task 1.4 — `tests/conftest.py` comment only

Update the comment mentioning `EMAIL_DELIVERY_MODE=postmark` (around line 32) to say
`EMAIL_DELIVERY_MODE=ses` instead. No fixture logic change.

### Task 1.5 — `test_email_provider.py`

1. Update the import block: remove `PostmarkEmailProvider` from the import list.
2. Delete these three tests entirely:
   - `test_get_email_provider_returns_postmark_in_postmark_mode`
   - `test_postmark_email_provider_sends_expected_request`
   - `test_postmark_email_provider_raises_email_send_error_on_error_response`
3. Fix `test_get_email_provider_raises_outside_stub_mode` — it currently asserts
   `pytest.raises(NoEmailProviderConfiguredError, match="Postmark")`. Since the new
   error message (Task 1.2 step 5) no longer contains "Postmark", change the match to
   `match="ses"` (the new message contains `"Set EMAIL_DELIVERY_MODE to 'ses'"`).
4. `httpx` import (line 4) can also be removed from this test file if nothing else in
   it uses `httpx` directly after the Postmark tests are gone — check before removing
   (the SES tests use `boto3`/`ClientError`, not `httpx`).
5. All `test_ses_*` and `test_get_email_provider_returns_ses_in_ses_mode` tests are
   untouched.

### Task 1.6 — `test_otp.py`

Five references to update, all of them using `"postmark"` purely as a placeholder
"any real, non-stub mode" string (confirmed: in every case `get_email_provider` is
itself monkeypatched to a fake provider, so the literal string value never actually
reaches real Postmark/SES code) — rename all five to `"ses"` for clarity, no logic
change:
- `test_create_otp_request_email_channel_hides_otp_and_dispatches_outside_stub_mode`
- The comment in `test_create_otp_request_email_channel_raises_when_no_real_provider_configured`
  ("anything other than `\"stub\"` or `\"postmark\"`" → "anything other than
  `\"stub\"` or `\"ses\"`")
- `test_create_otp_request_email_and_phone_channels_do_not_share_throttle_state` (or
  whichever test contains the phone/email independence check around line 336)
- `test_create_otp_request_does_not_persist_when_email_send_fails`
- `test_create_otp_request_allows_immediate_retry_after_a_failed_send`
- The docstring in `test_conftest_forces_stub_delivery_modes_by_default` mentioning
  "a local `.env` that has `EMAIL_DELIVERY_MODE=postmark` set permanently" → update to
  `=ses`.

### Task 1.7 — `.env.example`

Remove these two lines:
```
POSTMARK_API_TOKEN=
POSTMARK_FROM_EMAIL=
```
`SES_FROM_EMAIL=` stays.

### Verification (Part 1)

```bash
cd backend
python3 -m pytest tests/services/auth/test_email_provider.py tests/services/auth/test_otp.py -v
python3 -m pytest -q   # full suite, confirm no regressions elsewhere
```
Expected: all pass, no `Postmark`/`postmark` string remaining anywhere in
`backend/app/` (`grep -rn -i postmark backend/app/` should return nothing).

**Safe to commit and merge to `feat/enhanced-ui` immediately** — this has zero effect
on staging until an image built from it is actually deployed (Part 3).

---

## Part 2 — Terraform: remove Postmark entirely

**Files:**
- Modify: `infra/modules/security/main.tf`
- Modify: `infra/modules/security/variables.tf`
- Modify: `infra/modules/security/outputs.tf`
- Modify: `infra/modules/backend/main.tf`
- Modify: `infra/modules/backend/variables.tf`
- Modify: `infra/envs/staging/main.tf`
- Modify: `infra/envs/staging/variables.tf`

### Task 2.1 — `infra/modules/security/main.tf`

Delete these two resources (currently lines 63-72):
```hcl
resource "aws_secretsmanager_secret" "postmark_api_token" {
  name       = "${var.project}-${var.environment}-postmark-api-token"
  kms_key_id = aws_kms_key.rds_and_secrets.arn
  tags       = local.common_tags
}

resource "aws_secretsmanager_secret_version" "postmark_api_token" {
  secret_id     = aws_secretsmanager_secret.postmark_api_token.id
  secret_string = var.postmark_api_token
}
```

### Task 2.2 — `infra/modules/security/variables.tf`

Delete the `postmark_api_token` variable block (currently lines 31-35).

### Task 2.3 — `infra/modules/security/outputs.tf`

Delete the `postmark_api_token_secret_arn` output block (currently lines 16-19).

### Task 2.4 — `infra/modules/backend/main.tf`

1. In `data.aws_iam_policy_document.ecs_secrets_read`'s `ReadAppSecrets` statement
   (currently `resources = [var.pan_keys_secret_arn, var.postmark_api_token_secret_arn]`),
   drop the Postmark ARN:
   ```hcl
   resources = [var.pan_keys_secret_arn]
   ```
2. In `aws_ecs_task_definition.this`'s `environment` list, delete the
   `POSTMARK_FROM_EMAIL` entry.
3. In the same resource's `secrets` list, delete the `POSTMARK_API_TOKEN` entry.
4. Delete the SES-related resources' guard condition is untouched — this task only
   removes Postmark, not the `backend_task_ses` resources added by the prior plan.

### Task 2.5 — `infra/modules/backend/variables.tf`

Delete two variable blocks: `postmark_api_token_secret_arn` (currently lines 103-106)
and `postmark_from_email` (currently lines 120-124). Leave `otp_delivery_mode`'s
description as-is except drop its Postmark-specific wording if it references
`postmark`/Part C (cosmetic only — it's describing the phone/SMS variable, which this
plan doesn't otherwise touch, so a minimal wording fix is enough, not a rewrite).

### Task 2.6 — `infra/envs/staging/main.tf`

1. In `module "security"` block, remove the `postmark_api_token = var.postmark_api_token`
   line (currently line 22).
2. In `module "backend"` block, remove `postmark_api_token_secret_arn =
   module.security.postmark_api_token_secret_arn` (line 77) and `postmark_from_email
   = var.postmark_from_email` (line 80).

### Task 2.7 — `infra/envs/staging/variables.tf`

Delete two variable blocks: `postmark_api_token` (currently lines 37-41) and
`postmark_from_email` (currently lines 55-59).

### Verification (Part 2)

```bash
cd infra/envs/staging
terraform validate
```
Cannot run `terraform plan`/`apply` without real AWS credentials — that happens in
Part 3. `terraform validate` only checks syntax/internal consistency and needs no
credentials; confirm it passes clean.

**Safe to commit and merge to `feat/enhanced-ui` immediately** — Terraform files are
inert until `terraform apply` runs, which doesn't happen until Part 3.

---

## Part 3 — Deploy sequence (only once SES production access is approved)

**Do not start this part until:**
1. AWS has approved the SES production-access request (check: AWS Console → SES →
   Account dashboard → no longer says "sandbox").
2. Parts 1 and 2's commits are merged to `feat/enhanced-ui`.

### Step 1 — Re-authenticate / re-verify environment

On the laptop that will run this (Terraform/AWS CLI/Docker already installed, per
Part 0):
```bash
aws sts get-caller-identity   # confirm credentials still valid
cd MVP_V1_MF_only
git checkout feat/enhanced-ui
git pull
cd infra/envs/staging
terraform init   # safe no-op if nothing changed since Part 0's init
```

### Step 2 — Rebuild and push the final image

This **must** be redone — the previously-pushed image (Part 0) predates Parts 1-2.
```bash
cd backend
docker build -t unifolio-staging-backend .
# (.pytest_tmp permission gotcha, if it recurs: sudo rm -rf .pytest_tmp, retry)

aws ecr get-login-password --region ap-south-1 | \
  docker login --username AWS --password-stdin 811364789032.dkr.ecr.ap-south-1.amazonaws.com

docker tag unifolio-staging-backend:latest \
  811364789032.dkr.ecr.ap-south-1.amazonaws.com/unifolio-staging-backend:latest
docker push 811364789032.dkr.ecr.ap-south-1.amazonaws.com/unifolio-staging-backend:latest
```

### Step 3 — One combined `terraform apply`: SES in, Postmark out, cutover to `"ses"`

Export every required value in the same terminal session (this project never uses a
`terraform.tfvars` file — see `ses-terraform-deploy-runbook.md`'s note on this; secrets
go in as `TF_VAR_*` env vars only):

```bash
export TF_VAR_pan_encryption_key="<real value>"
export TF_VAR_pan_lookup_pepper="<real value>"
export TF_VAR_otp_delivery_mode="stub"
export TF_VAR_email_delivery_mode="ses"
export TF_VAR_ses_from_email="no-reply@unifolio.in"
export TF_VAR_ses_identity_arn="arn:aws:ses:ap-south-1:811364789032:identity/unifolio.in"
```

Note what's **gone** from this list compared to the original runbook:
`TF_VAR_postmark_api_token` and `TF_VAR_postmark_from_email` no longer exist as
variables at all (Part 2 deleted them) — don't export them, Terraform will error on an
unrecognized variable if you try.

```bash
terraform plan
```

**Expected diff this time is different from the original runbook's guidance — read
carefully:**
- **Additions:** `aws_iam_role_policy.backend_task_ses` +
  `aws_iam_policy_document.backend_task_ses` (the SES IAM permission, from the prior
  plan, still not yet applied).
- **Destructions — expected and correct this time:**
  `aws_secretsmanager_secret.postmark_api_token`,
  `aws_secretsmanager_secret_version.postmark_api_token`, and the
  `aws_iam_role_policy.backend_task_ses`'s sibling change to
  `aws_iam_role_policy.ecs_secrets_read` (updated in place, Postmark ARN dropped from
  its `resources` list). **This is the one case in this whole project's Terraform
  history where a destroy is intentional and correct — the original runbook's "stop if
  anything is destroyed" guidance does NOT apply to these specific Postmark-named
  resources.**
- **Replacement:** `aws_ecs_task_definition.this` (new revision — new image, new env
  vars, new secrets list, all three changed at once) and `aws_ecs_service.this`
  updated in place to point at it.
- **Still stop and don't apply if you see anything unexpected outside this list** — no
  RDS, VPC, ECS *cluster*, S3 bucket, or PAN-keys secret should appear as
  touched/destroyed.

```bash
terraform apply
```

Watch the rollout exactly as the original runbook describes (same
`deployment_minimum_healthy_percent = 0` stop-then-start risk applies):
```bash
watch -n 5 'aws ecs describe-services --cluster unifolio-staging --services unifolio-staging-backend \
  --query "services[0].{running:runningCount,desired:desiredCount,rollout:deployments[0].rolloutState}"'
```
and in another terminal:
```bash
aws logs tail /ecs/staging-backend --follow
curl -s https://staging-api.unifolio.in/health
```

### Step 4 — Verify

- **Same-domain email OTP** (`@unifolio.in`) — should work immediately via SES.
- **Cross-domain email OTP** (Gmail, etc.) — the actual point of the whole migration;
  should now work since production access is approved (prerequisite for starting this
  part at all).
- **Force a real failure to confirm the 502 fix**: temporarily export a broken
  `TF_VAR_ses_from_email` (an unverified address), `terraform apply` again, attempt a
  send, confirm the frontend shows a real error — not "Unable to connect to the
  server." Then set it back to `no-reply@unifolio.in` and `terraform apply` once more.
- **Phone/SMS OTP still works exactly as before** (stub mode, dev-echo OTP shown in
  the response) — this plan touches nothing on that path; verify as a pure regression
  check, not because anything here could plausibly break it.

### If something goes wrong mid-rollout

Same rollback mechanism as the original runbook — re-point the ECS service at the
previous task-definition revision without touching Terraform state:
```bash
aws ecs update-service --cluster unifolio-staging --service unifolio-staging-backend \
  --task-definition unifolio-staging-backend:<previous-revision-number>
```
Note: unlike the original runbook's rollback (which could fall back to a
still-working Postmark), **there is no working email-OTP fallback once this cutover is
live** — Postmark's code and infra are gone. A rollback here restores the previous
*image and task definition*, which still has Postmark, so email OTP recovers with the
rollback. This is the one real tradeoff of removing Postmark instead of keeping it
dormant: recovery from a bad SES-related deploy depends on the ECS revision rollback
working cleanly, not on flipping a delivery-mode variable back.

---

## Part 4 — Manual DNS cleanup (after Step 4 is fully green, low priority, anytime)

Not code, not Terraform — done directly in the Route 53 console for the `unifolio.in`
hosted zone.

Two records were added for Postmark's Sender Signature
(`Docs/email-otp-postmark-technical-documentation.md` §4): a DKIM CNAME and a
Return-Path CNAME. **Identify them precisely before deleting** — do not delete by
guessing a name pattern. Look for records whose *value* points at a
`postmarkapp.com`/`pm.mtasv.net`-style target (Postmark's typical CNAME targets); the
name is commonly `pm._domainkey.unifolio.in` (DKIM) and something under
`pm-bounces.unifolio.in` (Return-Path), but confirm the actual names/values in the
console rather than trusting that pattern blindly.

**Do not touch:** the existing Microsoft 365 MX/SPF/DMARC/autodiscover records (per
`CLAUDE.md`'s explicit note that these were preserved during the Route 53 cutover),
and the SES DKIM CNAME records + MAIL FROM (`mail.unifolio.in`) records added for this
plan's Part 1 (the original SES migration plan) — those are live and needed.

Also, separately (outside AWS entirely): consider downgrading or deleting the Postmark
account itself once its DNS records are gone, though this has zero technical urgency
(free tier, $0/month, no expiry) — purely a "don't leave an unused account around"
housekeeping choice, do it whenever convenient or not at all.

---

## Part 5 — Docs cleanup (write alongside Part 1/2, or anytime — no deploy dependency)

1. `Docs/email-otp-postmark-technical-documentation.md` — add a one-line note at the
   top: superseded by this plan; Postmark is no longer used as of this plan's Part 3
   deploy. Keep the rest of the doc as historical record, don't delete it.
2. `Docs/orchestration/ses-terraform-deploy-runbook.md` — add a one-line pointer at
   the top: superseded by this plan (`2026-09-22-ses-cutover-and-postmark-removal.md`)
   for deploy purposes; its Steps 0-2 are still accurate.
3. `CLAUDE.md`'s Session State section and `session.md` — update once Part 3 actually
   ships (not now, since nothing's deployed yet) to reflect: SES live in staging,
   Postmark fully removed, phone/SMS still stub pending a real provider.

---

## Self-review

**Sequencing risk addressed:** the load-bearing constraint (code removal and the
`email_delivery_mode` flip must land in the same deploy) is stated explicitly in Part
0 and enforced by Part 3 being a single combined apply, not a two-step rollout.

**Scope check:** phone/SMS (`otp_delivery_mode`) is untouched everywhere in this plan
— confirmed by grep, the only test/code references to `"postmark"` are all in the
email path.

**Cost/tradeoff stated, not hidden:** Part 3's rollback section is explicit that
removing Postmark (vs. the original plan's "keep it dormant") means a bad SES deploy
has no live-delivery-mode fallback, only an ECS-revision rollback — this was an
explicit user tradeoff decision, not an oversight.

**What this plan does NOT do:** doesn't touch phone/SMS OTP, doesn't touch the
frontend, doesn't touch any other Terraform module (networking/database/frontend/dns/
scheduler/storage/ecr) beyond the `security` and `backend` modules' Postmark-specific
resources, doesn't request/wait on SES production access itself (that's already
submitted, tracked separately).
