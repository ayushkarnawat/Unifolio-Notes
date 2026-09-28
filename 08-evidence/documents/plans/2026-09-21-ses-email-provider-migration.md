# SES Email Provider Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Postmark with Amazon SES as the email-OTP delivery backend, so OTP
emails reach any address (not just `@unifolio.in`), and fix the related bug where any
email-send failure currently crashes uncaught and shows the user a false "can't
connect" error instead of a real message.

**Architecture:** Add a new `SesEmailProvider` class behind the existing
`EmailProvider` protocol/`get_email_provider()` factory in
`backend/app/services/auth/email_provider.py` — no changes needed to `otp.py`'s
calling code shape, the API routes, or the frontend, since the provider is already
fully abstracted. Both `PostmarkEmailProvider` and the new `SesEmailProvider` raise a
shared `EmailSendError` on failure, caught once per API route and turned into a clean
`502` instead of an unhandled `500`. IAM-role-based auth (no API token/secret to
store), matching this codebase's existing AWS SDK usage in
`backend/app/services/analytics/dispatch.py` and
`backend/app/services/import_/file_storage.py`.

**Tech Stack:** Python/FastAPI backend, `boto3` (already a pinned dependency,
`boto3==1.43.87`, `backend/requirements.txt:6` — no new dependency needed), Terraform
for AWS infra (`infra/modules/backend`, `infra/envs/staging`), `pytest` +
`unittest.mock.patch` for tests (this codebase does not use `moto`).

**Spec:** This plan supersedes and folds in
`Docs/orchestration/email-otp-send-failure-handling-handoff.md` (the CORS-masking bug
fix — Tasks 2, 4, 5 below implement it, generalized to cover both providers instead of
just Postmark). Background and provider comparison:
`Docs/orchestration/email-provider-alternatives-comparison.md` and
`Docs/orchestration/cross-domain-otp-issue-summary.md`.

## Global Constraints

- `EMAIL_DELIVERY_MODE` stays independent of `OTP_DELIVERY_MODE` (phone/SMS) — don't
  couple them (this was a deliberate earlier fix, see `otp.py`'s `_delivery_mode()`
  docstring).
- No static AWS credentials anywhere — SES access goes through the existing ECS task
  IAM role, same as S3/ECS access already do. Never add an AWS access key to `.env` or
  Secrets Manager for this.
- Test-first. Mirror this codebase's existing test style exactly: plain
  `unittest.mock.patch`/`monkeypatch`, not `moto` (confirmed: no `moto` anywhere in
  `backend/`).
- Don't touch `NoEmailProviderConfiguredError`'s behavior — that's a deploy-time
  misconfiguration and must keep failing loudly/unhandled, not get folded into the new
  `EmailSendError` handling.
- Postmark stays wired and working throughout — this migration adds SES alongside it,
  it does not rip Postmark out. Cutover (switching the live `EMAIL_DELIVERY_MODE`
  value) is a separate, later, reversible step (Part 4 below), not part of the code
  tasks.

---

## Part 0 — What's needed from you before/alongside this plan

1. **Decide the send-from address.** Postmark today sends as
   `aditi.shanbhag@unifolio.in` (a real personal mailbox, per
   `Docs/email-otp-postmark-technical-documentation.md`). SES doesn't require proving
   control of one specific mailbox the way Postmark's Sender Signature did — once the
   *domain* `unifolio.in` is verified in SES, you can send from any address at that
   domain. Recommend a dedicated address like `otp@unifolio.in` or
   `no-reply@unifolio.in` instead of a real personal inbox. **Tell me which address you
   want** before Task 3 (it goes into `SES_FROM_EMAIL`/`ses_from_email`).
2. **AWS Console access** to the account already created for `ap-south-1` (per
   `CLAUDE.md`'s session notes) — you'll do the SES domain verification and production
   access request yourself in Part 1 below (console steps, same style as the Route 53
   DNS work you already did for DMARC).
3. **Terraform apply access.** This sandbox has no `aws`/`terraform` CLI installed and
   no AWS credentials — I can write the Terraform code (Task 1), but *you* (or wherever
   you normally run `terraform plan`/`apply` for this project) will need to actually
   apply it. Let me know if you want to set up AWS CLI/Terraform access in this
   environment instead, or if you'll run it from your own machine/CI.
4. **One thing only you can confirm:** this repo has no local Terraform state (it uses
   a remote S3 backend, `infra/envs/staging/backend.tf`), so I can't tell from here
   whether `infra/modules/backend`'s Terraform has actually been applied to the
   *currently running* staging ECS service, or whether staging was set up some other
   way before this Terraform code existed. **Before Task 1's `terraform apply`**, check
   AWS Console → ECS → the staging cluster/service → task definition → "Task role" —
   confirm it matches `aws_iam_role.backend_task` from `infra/modules/backend/main.tf`.
   If it doesn't, the IAM permission needs to be attached to whatever role actually is
   in use (via IAM console directly), and this Terraform edit alone won't take effect
   until that's reconciled.

---

## Part 1 — AWS SES account & domain setup (manual, console-driven, do this first)

These are AWS Console actions, not code — same style as the Route 53 DNS work you
already did. Do these before or in parallel with the code tasks below; the code tasks
don't depend on this being finished (tests mock the AWS calls), but you can't actually
send a real email until it is.

1. Open the SES console in the `ap-south-1` region.
2. **Identities → Create identity → Domain.** Enter `unifolio.in`. Choose "Easy DKIM"
   (2048-bit RSA, the default).
3. Since the domain is already in Route 53, use SES's **"Publish DNS records to Route
   53"** button — this adds the 3 DKIM CNAME records for you automatically. Do not
   type them in by hand (this is exactly the kind of manual-entry step that caused the
   two-value DMARC record bug you just fixed).
4. *(Recommended, optional)* Configure a **Custom MAIL FROM domain** (e.g.
   `mail.unifolio.in`) for stricter SPF alignment — SES again offers a one-click
   "publish to Route 53" option for the required MX + TXT records.
5. Wait for the identity's status to flip to **Verified** (usually minutes, since
   Route 53 is authoritative).
6. **Account dashboard → General details → "Request production access."** Fill in the
   use case (transactional OTP emails, expected volume ~a few thousand/month, bounce
   handling via SES's own notifications). Submit.
7. **Wait for AWS approval** (typically ~24h, sometimes longer). This runs in the
   background — it does not block Tasks 1–6 below. Until it's approved, SES is in
   "sandbox mode" and can only send to individually-verified addresses (you can verify
   your own test addresses individually in the console to test before approval
   clears).
8. Note the domain identity's ARN once verified — SES shows it in the identity's
   details page, format `arn:aws:ses:ap-south-1:<account-id>:identity/unifolio.in`.
   This goes into Terraform's `ses_identity_arn` variable (Task 1).

---

## File structure (code + infra changes this plan makes)

- Modify: `backend/app/config.py` — add `ses_from_email` setting.
- Modify: `backend/app/services/auth/email_provider.py` — add `EmailSendError`, wrap
  `PostmarkEmailProvider` to raise it, add `SesEmailProvider`, wire `"ses"` into
  `get_email_provider()`.
- Modify: `backend/app/services/auth/otp.py` — reorder `create_otp_request` so a
  failed email send never persists a throttling row.
- Modify: `backend/app/api/auth.py` — catch `EmailSendError` at the 3 call sites that
  send email OTPs, return `502`.
- Modify: `backend/tests/services/auth/test_email_provider.py`,
  `backend/tests/services/auth/test_otp.py`, `backend/tests/api/test_email_otp_routes.py`
  — new/updated tests for all of the above.
- Modify: `infra/modules/backend/variables.tf`, `infra/modules/backend/main.tf`,
  `infra/envs/staging/variables.tf`, `infra/envs/staging/main.tf` — SES IAM permission
  + `SES_FROM_EMAIL` plumbing.
- Modify: `backend/.env.example` — document the new setting for local dev.

---

### Task 1: Terraform — SES IAM permission and config plumbing

**Files:**
- Modify: `infra/modules/backend/variables.tf:120-124` (after the existing
  `postmark_from_email` variable block)
- Modify: `infra/modules/backend/main.tf:207-208` (after the existing
  `aws_iam_role_policy.backend_task_cas_files` resource) and `infra/modules/backend/main.tf:238`
  (after the existing `POSTMARK_FROM_EMAIL` environment entry)
- Modify: `infra/envs/staging/variables.tf:114-124` (mirroring the existing
  `email_delivery_mode`/`postmark_from_email` variables)
- Modify: `infra/envs/staging/main.tf:80` (after the existing `postmark_from_email =`
  line in the `module "backend"` block)

**Interfaces:**
- Produces: `var.ses_from_email` and `var.ses_identity_arn`, consumed by
  `infra/modules/backend/main.tf`'s task definition and new IAM policy.

- [ ] **Step 1: Add the two new module variables**

In `infra/modules/backend/variables.tf`, after the existing `postmark_from_email`
block (ends at line 124):

```hcl
variable "ses_from_email" {
  description = "Verified SES identity address emails are sent from once EMAIL_DELIVERY_MODE is set to \"ses\". Must belong to a domain verified in SES (see Docs/superpowers/plans/2026-09-21-ses-email-provider-migration.md Part 1)."
  type        = string
  default     = ""
}

variable "ses_identity_arn" {
  description = "ARN of the verified SES domain identity the backend task role is allowed to send from, e.g. arn:aws:ses:<region>:<account_id>:identity/unifolio.in. Empty disables the backend task's SES IAM permission entirely (see Part 1 of the SES migration plan)."
  type        = string
  default     = ""
}
```

- [ ] **Step 2: Add the SES IAM policy, guarded on the identity ARN being set**

In `infra/modules/backend/main.tf`, immediately after the
`aws_iam_role_policy.backend_task_cas_files` resource (after line 207):

```hcl
# SesEmailProvider (backend/app/services/auth/email_provider.py) sends via the
# SES API using this same task role -- no static AWS credentials, same pattern
# as the S3/KMS access above. count=0 until ses_identity_arn is actually set,
# so this module stays apply-safe before the SES domain identity exists
# (Part 1 of the SES migration plan).
data "aws_iam_policy_document" "backend_task_ses" {
  count = var.ses_identity_arn == "" ? 0 : 1

  statement {
    sid       = "SendEmailViaSes"
    effect    = "Allow"
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = [var.ses_identity_arn]
  }
}

resource "aws_iam_role_policy" "backend_task_ses" {
  count  = var.ses_identity_arn == "" ? 0 : 1
  name   = "backend-task-ses-send"
  role   = aws_iam_role.backend_task.id
  policy = data.aws_iam_policy_document.backend_task_ses[0].json
}
```

- [ ] **Step 3: Add `SES_FROM_EMAIL` to the task's environment variables**

In `infra/modules/backend/main.tf`, in the `environment` list (right after the
existing `POSTMARK_FROM_EMAIL` entry, line 238):

```hcl
        { name = "SES_FROM_EMAIL", value = var.ses_from_email },
```

- [ ] **Step 4: Add matching variables at the staging env level**

In `infra/envs/staging/variables.tf`, after the existing `postmark_from_email`
variable (mirrors lines 114-124's style):

```hcl
variable "ses_from_email" {
  description = "Verified SES identity address for the \"ses\" email delivery mode. Empty until Part 1 of the SES migration plan is done."
  type        = string
  default     = ""
}

variable "ses_identity_arn" {
  description = "ARN of the SES domain identity for unifolio.in, once verified (Part 1 of the SES migration plan). Empty disables the backend task's SES IAM permission entirely."
  type        = string
  default     = ""
}
```

- [ ] **Step 5: Pass them into the `backend` module**

In `infra/envs/staging/main.tf`, in the `module "backend"` block, right after the
existing `postmark_from_email = var.postmark_from_email` line (line 80):

```hcl
  ses_from_email   = var.ses_from_email
  ses_identity_arn = var.ses_identity_arn
```

- [ ] **Step 6: Validate**

Run (you or whoever has Terraform/AWS access — see Part 0 item 3):

```bash
cd infra/envs/staging
terraform validate
terraform plan
```

Expected: `terraform validate` passes with no syntax errors; `terraform plan` shows
only additive changes (a new `aws_iam_role_policy.backend_task_ses` resource — created
with `count = 0`, i.e. no-op, until `ses_identity_arn` is set in the real
`terraform.tfvars`) and the new `SES_FROM_EMAIL` env var on the task definition. No
existing resource should show as destroyed/replaced.

- [ ] **Step 7: Commit**

```bash
git add infra/modules/backend/variables.tf infra/modules/backend/main.tf infra/envs/staging/variables.tf infra/envs/staging/main.tf
git commit -m "infra: add SES IAM permission and config plumbing for email OTP"
```

---

### Task 2: Add `EmailSendError` and make `PostmarkEmailProvider` raise it

**Files:**
- Modify: `backend/app/services/auth/email_provider.py:1-78`
- Test: `backend/tests/services/auth/test_email_provider.py:71-83`

**Interfaces:**
- Produces: `EmailSendError` (new exception class, importable from
  `app.services.auth.email_provider`), raised by both `PostmarkEmailProvider` (this
  task) and `SesEmailProvider` (Task 3).

- [ ] **Step 1: Update the existing failing-on-purpose test**

Replace the existing test in `backend/tests/services/auth/test_email_provider.py`
(lines 71-83), which currently expects the raw `httpx.HTTPStatusError` to escape:

```python
def test_postmark_email_provider_raises_email_send_error_on_error_response(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "postmark_api_token", "test-token")
    monkeypatch.setattr(email_provider_module.settings, "postmark_from_email", "noreply@unifolio.in")

    def fake_post(url, headers=None, json=None, timeout=None):
        request = httpx.Request("POST", url)
        return httpx.Response(422, request=request, json={"Message": "Invalid 'From' address"})

    with patch.object(email_provider_module.httpx, "post", side_effect=fake_post):
        with pytest.raises(email_provider_module.EmailSendError):
            PostmarkEmailProvider().send_email(to="user@example.com", subject="s", body="b")
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
cd backend && python3 -m pytest tests/services/auth/test_email_provider.py::test_postmark_email_provider_raises_email_send_error_on_error_response -v
```

Expected: FAIL — `EmailSendError` doesn't exist yet.

- [ ] **Step 3: Add `EmailSendError` and wrap the Postmark send call**

In `backend/app/services/auth/email_provider.py`, add the new exception class right
after `POSTMARK_SEND_URL` (after line 23):

```python
class EmailSendError(RuntimeError):
    """Raised when an email provider rejects or fails to send an OTP email.
    Callers (otp.py, auth.py) catch this and return a clean error to the
    caller instead of letting the underlying provider exception (an httpx or
    boto3 error) escape uncaught -- an uncaught exception here crashes past
    CORSMiddleware's normal response path, so the browser sees a stripped,
    CORS-header-less 500 and misreports it as a network/CORS failure instead
    of the real cause."""
```

Then replace `PostmarkEmailProvider.send_email` (lines 44-60) with:

```python
    def send_email(self, to: str, subject: str, body: str) -> None:
        try:
            response = httpx.post(
                POSTMARK_SEND_URL,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Postmark-Server-Token": settings.postmark_api_token,
                },
                json={
                    "From": settings.postmark_from_email,
                    "To": to,
                    "Subject": subject,
                    "TextBody": body,
                },
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("PostmarkEmailProvider: send to %s failed: %s", to, exc)
            raise EmailSendError("We couldn't send that email right now.") from exc
```

(`httpx.HTTPError` is the base class for both `HTTPStatusError`, raised by
`raise_for_status()`, and connection-level failures like a timeout or connection
error — both should be treated the same way here.)

- [ ] **Step 4: Run the test again**

```bash
cd backend && python3 -m pytest tests/services/auth/test_email_provider.py -v
```

Expected: PASS, all tests in the file green (the other existing tests in this file are
unaffected by this change).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth/email_provider.py backend/tests/services/auth/test_email_provider.py
git commit -m "fix(auth): wrap Postmark send failures in a catchable EmailSendError"
```

---

### Task 3: Add `SesEmailProvider`

**Files:**
- Modify: `backend/app/config.py:10` (after the existing `postmark_from_email` line)
- Modify: `backend/app/services/auth/email_provider.py` (adds to the file from Task 2)
- Test: `backend/tests/services/auth/test_email_provider.py`

**Interfaces:**
- Consumes: `EmailSendError` (from Task 2), `settings.aws_region` (already exists,
  `backend/app/config.py:40`), `settings.ses_from_email` (added this task).
- Produces: `SesEmailProvider` class (a `send_email(to, subject, body) -> None`
  implementer of the `EmailProvider` protocol), consumed by `get_email_provider()`
  (Task 4).

- [ ] **Step 1: Add the `ses_from_email` setting**

In `backend/app/config.py`, right after the existing `postmark_from_email: str = ""`
line (line 10):

```python
    ses_from_email: str = ""
```

- [ ] **Step 2: Write the failing tests**

Add to `backend/tests/services/auth/test_email_provider.py` (add these imports at the
top alongside the existing ones — `from unittest.mock import patch` already exists;
add `from botocore.exceptions import ClientError`):

```python
def test_ses_email_provider_sends_expected_request(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "aws_region", "ap-south-1")
    monkeypatch.setattr(email_provider_module.settings, "ses_from_email", "otp@unifolio.in")

    mock_client = MagicMock()
    with patch.object(email_provider_module.boto3, "client", return_value=mock_client) as mock_boto_client:
        email_provider_module.SesEmailProvider().send_email(to="user@example.com", subject="Your code", body="123456")

    mock_boto_client.assert_called_once_with("ses", region_name="ap-south-1")
    mock_client.send_email.assert_called_once_with(
        Source="otp@unifolio.in",
        Destination={"ToAddresses": ["user@example.com"]},
        Message={
            "Subject": {"Data": "Your code", "Charset": "UTF-8"},
            "Body": {"Text": {"Data": "123456", "Charset": "UTF-8"}},
        },
    )


def test_ses_email_provider_raises_email_send_error_on_client_error(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "aws_region", "ap-south-1")
    monkeypatch.setattr(email_provider_module.settings, "ses_from_email", "otp@unifolio.in")

    mock_client = MagicMock()
    mock_client.send_email.side_effect = ClientError(
        {"Error": {"Code": "MessageRejected", "Message": "Email address not verified"}},
        "SendEmail",
    )
    with patch.object(email_provider_module.boto3, "client", return_value=mock_client):
        with pytest.raises(email_provider_module.EmailSendError):
            email_provider_module.SesEmailProvider().send_email(to="user@example.com", subject="s", body="b")


def test_ses_email_provider_raises_when_region_unconfigured(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "aws_region", "")
    with pytest.raises(email_provider_module.EmailSendError, match="not configured"):
        email_provider_module.SesEmailProvider().send_email(to="user@example.com", subject="s", body="b")
```

You'll also need `from unittest.mock import MagicMock, patch` at the top of the test
file (currently only `patch` is imported — check the existing import line and extend
it).

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && python3 -m pytest tests/services/auth/test_email_provider.py -k ses -v
```

Expected: FAIL (`SesEmailProvider` doesn't exist, `email_provider_module.boto3`
doesn't exist).

- [ ] **Step 3: Implement `SesEmailProvider`**

In `backend/app/services/auth/email_provider.py`:
1. Add `import boto3` and `from botocore.exceptions import BotoCoreError, ClientError`
   near the top, alongside the existing `import httpx`.
2. Add the class, right after `PostmarkEmailProvider` (after the class from Task 2):

```python
class SesEmailProvider:
    """Sends real email via Amazon SES's SendEmail API. Requires the sending
    domain to be a verified SES identity (see
    Docs/superpowers/plans/2026-09-21-ses-email-provider-migration.md Part 1)
    -- SES rejects the send otherwise, at the account level, same as
    PostmarkEmailProvider's Sender Signature requirement. Uses the ECS task's
    IAM role for credentials (boto3's default credential chain) -- no static
    access key, matching this codebase's existing boto3 usage in
    services/analytics/dispatch.py and services/import_/file_storage.py."""

    def send_email(self, to: str, subject: str, body: str) -> None:
        if not settings.aws_region:
            raise EmailSendError("Email delivery is not configured (missing AWS region).")

        client = boto3.client("ses", region_name=settings.aws_region)
        try:
            client.send_email(
                Source=settings.ses_from_email,
                Destination={"ToAddresses": [to]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                },
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("SesEmailProvider: send to %s failed: %s", to, exc)
            raise EmailSendError("We couldn't send that email right now.") from exc
```

Note this deliberately does **not** follow `EcsRunTaskDispatcher`'s "log and silently
no-op when unconfigured" pattern (`services/analytics/dispatch.py:38-44`) — that
pattern fits a best-effort background dispatch where doing nothing is an acceptable
outcome. Here, silently doing nothing would leave a user waiting for a code that never
arrives with no error at all, so an unconfigured region raises `EmailSendError`
instead, which the caller (Task 5) turns into a real error response.

- [ ] **Step 4: Run tests again**

```bash
cd backend && python3 -m pytest tests/services/auth/test_email_provider.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/app/services/auth/email_provider.py backend/tests/services/auth/test_email_provider.py
git commit -m "feat(auth): add SesEmailProvider for email OTP delivery via Amazon SES"
```

---

### Task 4: Wire `"ses"` into `get_email_provider()`

**Files:**
- Modify: `backend/app/services/auth/email_provider.py:67-77`
- Test: `backend/tests/services/auth/test_email_provider.py`

- [ ] **Step 1: Write the failing test**

```python
def test_get_email_provider_returns_ses_in_ses_mode(monkeypatch):
    import app.services.auth.email_provider as email_provider_module

    monkeypatch.setattr(email_provider_module.settings, "email_delivery_mode", "ses")
    provider = get_email_provider()
    assert isinstance(provider, email_provider_module.SesEmailProvider)
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && python3 -m pytest tests/services/auth/test_email_provider.py::test_get_email_provider_returns_ses_in_ses_mode -v
```

Expected: FAIL — `get_email_provider()` still raises `NoEmailProviderConfiguredError`
for `"ses"`.

- [ ] **Step 3: Add the branch**

In `backend/app/services/auth/email_provider.py`, update `get_email_provider()`:

```python
def get_email_provider() -> EmailProvider:
    if settings.email_delivery_mode == "stub":
        return StubEmailProvider()
    if settings.email_delivery_mode == "postmark":
        return PostmarkEmailProvider()
    if settings.email_delivery_mode == "ses":
        return SesEmailProvider()
    raise NoEmailProviderConfiguredError(
        f"No real EmailProvider is configured for EMAIL_DELIVERY_MODE={settings.email_delivery_mode!r}. "
        "Set EMAIL_DELIVERY_MODE to 'postmark' or 'ses' (with the matching "
        "provider settings configured) to send real email, or back to "
        "'stub' for local development."
    )
```

- [ ] **Step 4: Run tests again**

```bash
cd backend && python3 -m pytest tests/services/auth/test_email_provider.py -v
```

Expected: PASS, including the pre-existing
`test_get_email_provider_raises_outside_stub_mode` test (still uses `"sms"` as its
not-a-real-mode probe, unaffected by this change).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth/email_provider.py backend/tests/services/auth/test_email_provider.py
git commit -m "feat(auth): select SesEmailProvider when EMAIL_DELIVERY_MODE=ses"
```

---

### Task 5: Don't persist an OTP request when the email send fails

**Files:**
- Modify: `backend/app/services/auth/otp.py:96-112`
- Test: `backend/tests/services/auth/test_otp.py`

**Why:** Today, `create_otp_request` commits the new `OtpRequest` row to the database
*before* attempting the email send. If the send then fails, the row is still there —
which throttles the user's next attempt for 60 seconds even though they never received
a code. Reordering so the send is attempted first (for real, non-stub delivery modes)
means a failed send never persists anything, so the user can retry immediately once
whatever caused the failure is fixed.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/services/auth/test_otp.py`:

```python
def test_create_otp_request_does_not_persist_when_email_send_fails(monkeypatch):
    import app.services.auth.otp as otp_module
    from app.services.auth.email_provider import EmailSendError

    monkeypatch.setattr(otp_module.settings, "email_delivery_mode", "postmark")

    class FailingProvider:
        def send_email(self, to, subject, body):
            raise EmailSendError("boom")

    monkeypatch.setattr(otp_module, "get_email_provider", lambda: FailingProvider())
    db = _session()

    with pytest.raises(EmailSendError):
        create_otp_request(db, "failed-send@example.com", channel="email")

    assert db.query(OtpRequest).filter_by(email="failed-send@example.com").first() is None


def test_create_otp_request_allows_immediate_retry_after_a_failed_send(monkeypatch):
    import app.services.auth.otp as otp_module
    from app.services.auth.email_provider import EmailSendError

    monkeypatch.setattr(otp_module.settings, "email_delivery_mode", "postmark")

    attempt = {"count": 0}

    class FlakyThenWorkingProvider:
        def send_email(self, to, subject, body):
            attempt["count"] += 1
            if attempt["count"] == 1:
                raise EmailSendError("boom")

    monkeypatch.setattr(otp_module, "get_email_provider", lambda: FlakyThenWorkingProvider())
    db = _session()

    with pytest.raises(EmailSendError):
        create_otp_request(db, "retry@example.com", channel="email")

    # Immediately retrying (no 60s wait) must succeed, not raise
    # OtpRequestThrottledError -- the failed first attempt persisted nothing.
    request, raw_otp = create_otp_request(db, "retry@example.com", channel="email")
    assert request is not None
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && python3 -m pytest tests/services/auth/test_otp.py -k "does_not_persist_when_email_send_fails or allows_immediate_retry_after_a_failed_send" -v
```

Expected: FAIL — today's code persists the row before sending, so the first assertion
(`.first() is None`) fails, and the second test's retry hits
`OtpRequestThrottledError` instead of succeeding.

- [ ] **Step 3: Reorder `create_otp_request`**

In `backend/app/services/auth/otp.py`, replace lines 96-112 (from `otp =
generate_otp()` through the `if channel == "email"` send block) with:

```python
    otp = generate_otp()

    if channel == "email" and delivery_mode != "stub":
        # Attempt the real send BEFORE persisting anything: if this raises
        # (EmailSendError), nothing is written to the DB, so a failed send
        # never engages the resend throttle against the user's next attempt.
        get_email_provider().send_email(
            to=identifier,
            subject="Your Unifolio verification code",
            body=f"Your Unifolio verification code is {otp}. It expires in {OTP_TTL_MINUTES} minutes.",
        )

    request = OtpRequest(
        phone_number=identifier if channel == "sms" else None,
        email=identifier if channel == "email" else None,
        otp_hash=_hash_otp(otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
        created_at=datetime.now(timezone.utc),
    )
    db.add(request)
    db.commit()
```

(This preserves stub mode and the SMS channel exactly as they behave today — they
just go straight to persisting, since there's no real send to attempt first.)

- [ ] **Step 4: Run the full otp test file**

```bash
cd backend && python3 -m pytest tests/services/auth/test_otp.py -v
```

Expected: PASS, all tests — including every pre-existing email-channel test (they
don't depend on the ordering, only on the end behavior, which is unchanged for the
success path).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/auth/otp.py backend/tests/services/auth/test_otp.py
git commit -m "fix(auth): don't persist an OTP request when the email send fails"
```

---

### Task 6: Return a clean 502 instead of an unhandled 500 on email-send failure

**Files:**
- Modify: `backend/app/api/auth.py:24` (import), `:78-81`, `:92-95`, `:322-325`
- Test: `backend/tests/api/test_email_otp_routes.py`

**Why:** These are the three routes that call `create_otp_request(..., channel="email")`
and can now raise `EmailSendError` (Tasks 2/3/5). Each already catches
`OtpRequestThrottledError` → 429 the same way; add one more `except` clause following
that exact existing pattern.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/api/test_email_otp_routes.py`:

```python
def test_request_email_otp_returns_502_not_500_when_send_fails(client, monkeypatch):
    import app.api.auth as auth_module
    from app.services.auth.email_provider import EmailSendError

    def failing_create_otp_request(*args, **kwargs):
        raise EmailSendError("boom")

    monkeypatch.setattr(auth_module, "create_otp_request", failing_create_otp_request)

    response = client.post("/auth/email-otp/request", json={"email": "failure@example.com"})

    assert response.status_code == 502
    assert response.json()["detail"]


def test_signup_email_returns_502_not_500_when_send_fails(client, monkeypatch):
    import app.api.auth as auth_module
    from app.services.auth.email_provider import EmailSendError

    def failing_create_otp_request(*args, **kwargs):
        raise EmailSendError("boom")

    monkeypatch.setattr(auth_module, "create_otp_request", failing_create_otp_request)

    response = _signup(client, "sendfailure@example.com")

    assert response.status_code == 502
    assert response.json()["detail"]
```

(A third test for `request_contact_change` follows the same shape, but that route
needs an authenticated `user` fixture — check how other `contact-change` tests in this
same test suite set that up, e.g. search this file's directory for an existing
`test_contact_change_routes.py`-style file, and mirror its auth setup rather than
inventing a new one here.)

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && python3 -m pytest tests/api/test_email_otp_routes.py -k "502" -v
```

Expected: FAIL — currently these would 500 (or error out unexpectedly since nothing
catches `EmailSendError` yet).

- [ ] **Step 3: Add the catch at all three call sites**

In `backend/app/api/auth.py`, update the import at line 24 to also bring in
`EmailSendError`:

```python
from app.services.auth.email_provider import EmailSendError
```

Then, in `signup_email` (lines 78-81):

```python
    try:
        _, raw_otp = create_otp_request(db, body.email, channel="email")
    except OtpRequestThrottledError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except EmailSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

In `request_email_otp` (lines 92-95):

```python
    try:
        _, raw_otp = create_otp_request(db, body.email, channel="email")
    except OtpRequestThrottledError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except EmailSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

In `request_contact_change` (lines 322-325):

```python
    try:
        _, raw_otp = create_otp_request(db, body.identifier, channel=otp_channel)
    except OtpRequestThrottledError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except EmailSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

(`str(exc)` here is `EmailSendError`'s own message — e.g. "We couldn't send that email
right now." — never the raw underlying Postmark/SES error, which could leak
provider-internal detail. This is deliberate: see Task 2/3's error messages.)

- [ ] **Step 4: Run the full email-OTP route test file**

```bash
cd backend && python3 -m pytest tests/api/test_email_otp_routes.py -v
```

Expected: PASS, all tests.

- [ ] **Step 5: Run the full backend test suite**

```bash
cd backend && python3 -m pytest -v
```

Expected: PASS, no regressions anywhere else (this is the round that should catch
anything Tasks 1-6 collectively broke elsewhere).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/auth.py backend/tests/api/test_email_otp_routes.py
git commit -m "fix(auth): return 502 instead of an unhandled 500 when email send fails"
```

**No frontend change needed or wanted** — confirmed by reading
`frontend/src/features/auth/validation.ts:339-375`: `formatAuthErrorMessage` already
returns `err.payload` (FastAPI's `detail`) verbatim whenever it's a non-empty string,
before it ever reaches the generic `status >= 500` branch. A `502` with a `detail`
string surfaces correctly without touching this file.

---

## Part 2 — Deploy & end-to-end verification (after Tasks 1–6, manual)

1. Set the real values in staging's `terraform.tfvars` (gitignored, not something I
   can see or edit for you): `ses_from_email` (Part 0 item 1's decision),
   `ses_identity_arn` (Part 1 step 8), and leave `email_delivery_mode` as `"postmark"`
   for now — don't cut over yet.
2. `terraform apply` (you, or whoever has access — Part 0 item 3). This attaches the
   new IAM permission and adds `SES_FROM_EMAIL` to the task definition, without
   changing what's actually live (delivery mode is still `"postmark"`).
3. Redeploy the backend so the new code (Tasks 2-6) is running in staging, still on
   Postmark. Confirm same-domain OTP still works exactly as before (regression check).
4. Temporarily flip staging's `email_delivery_mode` to `"ses"` (via the same
   `terraform.tfvars` + apply + redeploy) and test:
   - A same-domain (`@unifolio.in`) OTP send — sanity check.
   - A cross-domain (Gmail, etc.) OTP send. **Expected before SES production access is
     approved:** this will fail (SES sandbox mode only allows individually-verified
     recipients) — that's expected, not a new bug. You can individually verify a
     personal test address in the SES console to test before approval clears.
   - Once Part 1 step 7's production access is approved, redo the cross-domain test —
     it should now succeed.
5. Confirm the 502 behavior is real, not just theoretical: temporarily point
   `ses_from_email` at an unverified address (or similar) to force a real SES
   rejection, and confirm the frontend shows a real error message instead of "Unable
   to connect to the server."

## Part 3 — Cutover & cleanup (later, once Part 2 is fully green)

1. Leave `email_delivery_mode = "ses"` as the live staging value.
2. **Recommended: don't remove Postmark.** Keep `PostmarkEmailProvider`,
   `postmark_api_token`/`postmark_from_email`, and the Postmark DNS records
   (DKIM/Return-Path/DMARC) in place, dormant, as a documented rollback path — flipping
   `email_delivery_mode` back to `"postmark"` costs nothing to keep available. Revisit
   removing it later only if you're confident you'll never want the fallback.
3. Update `Docs/email-otp-postmark-technical-documentation.md` with a short note that
   it's superseded by this plan for the production delivery path, and update
   `session.md`'s "still open" list to drop the Postmark-approval-pending item (it's no
   longer the blocking path once SES is live).

---

## Self-review

**Spec coverage:** cross-domain sending (Task 3 + Part 1 unblocks it), the
CORS-masking bug (Tasks 2/4/6, generalized to both providers, supersedes the earlier
standalone handoff doc), the throttle-on-failed-send bug found during live debugging
(Task 5), infra/IAM (Task 1), and deploy/verification/rollback (Parts 2-3) are all
covered.

**Placeholder scan:** no TBD/"add error handling"/"similar to Task N" language — every
step has real, complete code.

**Type/name consistency check:** `EmailSendError` (Task 2) is the one name used
throughout by `SesEmailProvider` (Task 3), `create_otp_request` (Task 5), and
`auth.py`'s three routes (Task 6) — no drift. `get_email_provider()` (Task 4)'s return
type stays `EmailProvider` (the existing `Protocol`), satisfied by both
`PostmarkEmailProvider` and `SesEmailProvider`, matching the existing pattern.

---

**Plan complete and saved to `Docs/superpowers/plans/2026-09-21-ses-email-provider-migration.md`.**
No code has been touched yet, per your instruction.

When you're ready to execute, two options:

1. **Subagent-driven (recommended)** — a fresh subagent per task, review between
   tasks, fast iteration.
2. **Inline execution** — execute tasks in this session, batch execution with
   checkpoints.

Note: this project's model-orchestration skill normally routes implementation work to
Codex by default, but Codex isn't configured in this session (confirmed earlier) — so
either option above would run via Claude directly (or Claude subagents), not Codex,
unless that changes by the time you execute this.

Which approach do you want, and have you decided the send-from address (Part 0 item
1) yet?
