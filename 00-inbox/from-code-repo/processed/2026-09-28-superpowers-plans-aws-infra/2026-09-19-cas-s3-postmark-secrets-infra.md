# CAS-File S3 Storage + PAN/Postmark Secrets — Infrastructure Plan

**Who this is for:** whoever runs this against the real AWS account (your manager). It assumes familiarity with `terraform` and `git`, but no prior context on this specific feature.

**Goal:** wire up the two things needed to run the already-built PAN-persistence/CAS-file-storage feature and the Postmark email provider for real in AWS staging: a private S3 bucket for retained CAS files, and Secrets Manager entries for the PAN encryption keys and the Postmark API token — reusing the KMS key and IAM patterns already staged in this repo's Terraform, not inventing new ones.

**Nothing in this plan has been applied yet.** No `.tfstate` exists for this environment (confirmed by its absence in the repo) — Phase 0/1 Terraform has never been run. This plan's Terraform changes land on top of that unapplied state, alongside everything else Phase 0/1 already defines.

**A correction worth knowing before you start:** the original framing of this work was "fix a KMS gap" on the ECS task's ability to decrypt secrets. On close inspection of the actual staged Terraform (`infra/modules/backend/main.tf`), that's only half true — the request-serving task's *execution role* (`aws_iam_role.ecs_task_execution`) already has `kms:Decrypt`/`kms:DescribeKey` on the shared KMS key (added for the RDS password), it's just scoped to reading the *RDS secret specifically*, not the two new secrets this plan adds. The real, more interesting gap is that the task's *runtime role* (`aws_iam_role.backend_task` — the one the app's own AWS SDK calls run as) currently has **zero** S3 or KMS permissions at all; it's only ever been granted `ecs:RunTask` for the analytics dispatcher. That's the role that needs new access, for a different reason (writing/reading S3 objects encrypted with the shared key), not the reason originally assumed.

---

## Prerequisites

- AWS CLI configured with credentials for the target account, region `ap-south-1`.
- Terraform installed, matching whatever version `infra/envs/staging/versions.tf` pins.
- Access to the Postmark account that will send OTP emails, and to the mailbox that will be the `POSTMARK_FROM_EMAIL` sender.
- Nothing about the marketing site, mail (MX/SPF/DMARC), or the existing Route 53 zone is touched by this plan.

---

## Part A — Terraform changes

### A1. New module: `infra/modules/storage/` (the CAS-files S3 bucket)

Create `infra/modules/storage/main.tf`:

```hcl
resource "aws_s3_bucket" "cas_files" {
  bucket = "${var.project}-${var.environment}-cas-files-${var.account_id}"
}

resource "aws_s3_bucket_public_access_block" "cas_files" {
  bucket = aws_s3_bucket.cas_files.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "cas_files" {
  bucket = aws_s3_bucket.cas_files.id

  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cas_files" {
  bucket = aws_s3_bucket.cas_files.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

# 30-day retention matches CAS_FILE_RETENTION_DAYS in
# backend/app/services/import_/file_storage.py. This is a backstop, not the
# primary deletion mechanism -- the app's own expire_stored_files() sweep
# (via backend/app/scripts/expire_cas_files.py) already deletes objects and
# nulls the DB row at 30 days; this Lifecycle rule only catches anything that
# sweep misses (e.g. a row whose Import was deleted without deleting its file).
resource "aws_s3_bucket_lifecycle_configuration" "cas_files" {
  bucket = aws_s3_bucket.cas_files.id

  rule {
    id     = "expire-cas-files-after-30-days"
    status = "Enabled"
    filter {}
    expiration {
      days = 30
    }
  }
}
```

Create `infra/modules/storage/variables.tf`:

```hcl
variable "environment" {
  description = "Deployment environment name used for resource names."
  type        = string
}

variable "project" {
  description = "Project name used for resource names."
  type        = string
}

variable "account_id" {
  description = "AWS account ID, used to make the bucket name globally unique."
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of the customer-managed KMS key used for SSE-KMS bucket encryption."
  type        = string
}
```

Create `infra/modules/storage/outputs.tf`:

```hcl
output "bucket_name" {
  description = "Name of the private S3 bucket holding retained CAS files."
  value       = aws_s3_bucket.cas_files.bucket
}

output "bucket_arn" {
  description = "ARN of the private S3 bucket holding retained CAS files."
  value       = aws_s3_bucket.cas_files.arn
}
```

### A2. New Secrets Manager resources, in `infra/modules/security/main.tf`

Add to the end of the existing file (after the `aws_kms_alias` resource):

```hcl
# Populated out-of-band via TF_VAR_pan_encryption_key / TF_VAR_pan_lookup_pepper
# at `terraform apply` time -- never written to any .tfvars file or committed.
# See Part D of the infra plan for how to generate these.
resource "aws_secretsmanager_secret" "pan_keys" {
  name       = "unifolio-${var.environment}-pan-keys"
  kms_key_id = aws_kms_key.rds_and_secrets.arn

  tags = merge(local.common_tags, {
    Name = "${var.environment}-pan-keys"
  })
}

resource "aws_secretsmanager_secret_version" "pan_keys" {
  secret_id = aws_secretsmanager_secret.pan_keys.id
  secret_string = jsonencode({
    encryption_key = var.pan_encryption_key
    lookup_pepper  = var.pan_lookup_pepper
  })
}

# Populated out-of-band via TF_VAR_postmark_api_token at apply time.
resource "aws_secretsmanager_secret" "postmark_api_token" {
  name       = "unifolio-${var.environment}-postmark-api-token"
  kms_key_id = aws_kms_key.rds_and_secrets.arn

  tags = merge(local.common_tags, {
    Name = "${var.environment}-postmark-api-token"
  })
}

resource "aws_secretsmanager_secret_version" "postmark_api_token" {
  secret_id     = aws_secretsmanager_secret.postmark_api_token.id
  secret_string = var.postmark_api_token
}
```

Add to `infra/modules/security/variables.tf`:

```hcl
variable "pan_encryption_key" {
  description = "Base64-encoded 32-byte PAN encryption key. Supply via TF_VAR_pan_encryption_key, never in a file."
  type        = string
  sensitive   = true
}

variable "pan_lookup_pepper" {
  description = "Base64-encoded 32-byte PAN lookup-hash pepper. Supply via TF_VAR_pan_lookup_pepper, never in a file."
  type        = string
  sensitive   = true
}

variable "postmark_api_token" {
  description = "Postmark server API token. Supply via TF_VAR_postmark_api_token, never in a file."
  type        = string
  sensitive   = true
}
```

Add to `infra/modules/security/outputs.tf`:

```hcl
output "pan_keys_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the PAN encryption key + lookup pepper (JSON)."
  value       = aws_secretsmanager_secret.pan_keys.arn
}

output "postmark_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the Postmark API token."
  value       = aws_secretsmanager_secret.postmark_api_token.arn
}
```

Now resolve the stale comment this plan makes obsolete. In `infra/modules/security/main.tf`, replace:

```hcl
  # Phase 3 must grant the ECS task execution role kms:Decrypt,
  # kms:GenerateDataKey, and kms:DescribeKey on this key ARN.
```

with:

```hcl
  # ecs_task_execution already has kms:Decrypt/kms:DescribeKey on this key
  # (infra/modules/backend/main.tf, rds_master_secret_read) -- broad because
  # it's scoped to the key ARN, not per-secret, so it already covers the new
  # pan_keys/postmark_api_token secrets below without any change here.
  # backend_task separately needs its own kms:GenerateDataKey/Decrypt grant
  # to read/write SSE-KMS objects in the CAS-files S3 bucket -- see
  # infra/modules/backend/main.tf's cas_files_access policy.
```

### A3. New variables on `infra/modules/backend/variables.tf`

Add:

```hcl
variable "pan_keys_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the PAN encryption key + lookup pepper."
  type        = string
}

variable "postmark_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the Postmark API token."
  type        = string
}

variable "postmark_from_email" {
  description = "Verified Postmark sender address (not secret -- see the runbook's manual Sender Signature step)."
  type        = string
}

variable "cas_files_bucket_name" {
  description = "Name of the S3 bucket holding retained CAS files."
  type        = string
}

variable "cas_files_bucket_arn" {
  description = "ARN of the S3 bucket holding retained CAS files."
  type        = string
}
```

### A4. IAM + ECS task definition changes in `infra/modules/backend/main.tf`

**A4a. Extend the execution role's Secrets Manager read access** (it can already decrypt with the KMS key; it just can't call `GetSecretValue` on these two new secrets yet). Add a new statement to the existing `rds_master_secret_read` policy document — rename it in place since it now covers more than just the RDS secret:

Replace the `data "aws_iam_policy_document" "rds_master_secret_read"` block with:

```hcl
data "aws_iam_policy_document" "ecs_secrets_read" {
  statement {
    sid       = "ReadRDSMasterSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.master_user_secret_arn]
  }

  statement {
    sid       = "ReadAppSecrets"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.pan_keys_secret_arn, var.postmark_secret_arn]
  }

  statement {
    sid       = "DecryptSecretsWithSharedKey"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:DescribeKey"]
    resources = [var.kms_key_arn]
  }
}
```

And rename the two places that reference the old name:

```hcl
resource "aws_iam_role_policy" "ecs_secrets_read" {
  name   = "ecs-secrets-read"
  role   = aws_iam_role.ecs_task_execution.id
  policy = data.aws_iam_policy_document.ecs_secrets_read.json
}
```

(This is a rename, not a new resource — Terraform will show it as one delete + one create for the `aws_iam_role_policy`, which is safe since it's an inline policy being replaced, not the role itself.) Update both `depends_on` blocks (on `aws_ecs_task_definition.analytics_recompute` and `aws_ecs_task_definition.this`) from `aws_iam_role_policy.rds_master_secret_read` to `aws_iam_role_policy.ecs_secrets_read`.

**A4b. Grant `backend_task` (the runtime role) S3 + KMS access** — this is the actually-new grant. Add after the existing `backend_task` policy document:

```hcl
data "aws_iam_policy_document" "backend_task_cas_files" {
  statement {
    sid       = "ReadWriteCasFiles"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${var.cas_files_bucket_arn}/*"]
  }

  statement {
    sid       = "EncryptDecryptCasFiles"
    effect    = "Allow"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt", "kms:DescribeKey"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "backend_task_cas_files" {
  name   = "backend-task-cas-files"
  role   = aws_iam_role.backend_task.id
  policy = data.aws_iam_policy_document.backend_task_cas_files.json
}
```

**A4c. Add the new env vars + secrets to the request-serving task definition** — `aws_ecs_task_definition.this` only (not `analytics_recompute`, which never touches imports or sends email). In its `environment` list, add:

```hcl
        { name = "EMAIL_DELIVERY_MODE", value = "postmark" },
        { name = "POSTMARK_FROM_EMAIL", value = var.postmark_from_email },
        { name = "CAS_FILE_STORAGE_BACKEND", value = "s3" },
        { name = "CAS_FILES_BUCKET_NAME", value = var.cas_files_bucket_name },
```

In its `secrets` list, alongside the existing `DB_PASSWORD` entry, add:

```hcl
        {
          name      = "PAN_ENCRYPTION_KEY"
          valueFrom = "${var.pan_keys_secret_arn}:encryption_key::"
        },
        {
          name      = "PAN_LOOKUP_PEPPER"
          valueFrom = "${var.pan_keys_secret_arn}:lookup_pepper::"
        },
        {
          name      = "POSTMARK_API_TOKEN"
          valueFrom = var.postmark_secret_arn
        }
```

(The `:key::` suffix pulls one field out of a JSON secret, same syntax already used for `:password::` on the RDS secret. `POSTMARK_API_TOKEN`'s secret is a plain string, not JSON, so it has no suffix.)

Update this task definition's `depends_on` to also include `aws_iam_role_policy.backend_task_cas_files`.

### A5. Wire it together in `infra/envs/staging/main.tf`

Add a new module block (after `module "database"`, before `module "backend"`):

```hcl
module "storage" {
  source = "../../modules/storage"

  environment = var.environment
  project     = var.project
  account_id  = data.aws_caller_identity.current.account_id
  kms_key_arn = module.security.kms_key_arn
}
```

(`data "aws_caller_identity" "current"` already exists further down this file, at line 81, and is reused as-is — Terraform resolves references via its dependency graph, not textual file order, so nothing needs to move for this to work, even though the data source is declared after this new module block.)

Update the `module "security"` block to pass the three new sensitive variables:

```hcl
module "security" {
  source = "../../modules/security"

  environment = var.environment
  project     = var.project

  pan_encryption_key  = var.pan_encryption_key
  pan_lookup_pepper   = var.pan_lookup_pepper
  postmark_api_token  = var.postmark_api_token
}
```

Add matching pass-through variables to `infra/envs/staging/variables.tf`:

```hcl
variable "pan_encryption_key" {
  type      = string
  sensitive = true
}

variable "pan_lookup_pepper" {
  type      = string
  sensitive = true
}

variable "postmark_api_token" {
  type      = string
  sensitive = true
}

variable "postmark_from_email" {
  type = string
}
```

Update the `module "backend"` block to pass the new variables:

```hcl
  pan_keys_secret_arn    = module.security.pan_keys_secret_arn
  postmark_secret_arn    = module.security.postmark_secret_arn
  postmark_from_email    = var.postmark_from_email
  cas_files_bucket_name  = module.storage.bucket_name
  cas_files_bucket_arn   = module.storage.bucket_arn
```

Optionally add an output for visibility after apply:

```hcl
output "cas_files_bucket_name" {
  description = "Name of the S3 bucket holding retained CAS files."
  value       = module.storage.bucket_name
}
```

---

## Part B — Application code changes

**Only one new class is needed.** PAN keys and the Postmark token need *zero* code changes — `EnvVarKeyProvider` (`backend/app/services/import_/crypto.py`) already reads `PAN_ENCRYPTION_KEY`/`PAN_LOOKUP_PEPPER` from environment variables, and `postmark_api_token`/`postmark_from_email` (`backend/app/config.py`) already read from env too. ECS's `secrets` block (Part A4c) makes a Secrets-Manager-sourced value appear as a plain environment variable to the running container — indistinguishable from a local `.env` file to the Python code reading it. The only thing that genuinely can't work through an env var alone is "write these bytes to S3," which needs real API calls.

### B1. `backend/app/config.py` — two new settings

Add alongside the existing `cas_file_storage_dir` setting:

```python
    cas_file_storage_backend: str = "local"  # "local" | "s3"
    cas_files_bucket_name: str = ""
```

### B2. `backend/app/services/import_/file_storage.py` — add `S3FileStorage`

Add after the `LocalFileStorage` class:

```python
class S3FileStorage:
    def __init__(self, bucket_name: str | None = None):
        import boto3

        self._bucket_name = bucket_name if bucket_name is not None else settings.cas_files_bucket_name
        self._client = boto3.client("s3")

    def save(self, key: str, data: bytes) -> str:
        self._client.put_object(Bucket=self._bucket_name, Key=key, Body=data)
        return key

    def read(self, reference: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket_name, Key=reference)
        return response["Body"].read()

    def delete(self, reference: str) -> None:
        self._client.delete_object(Bucket=self._bucket_name, Key=reference)
```

Replace the single line `default_file_storage = LocalFileStorage()` with a small factory, so the choice is made once at import time based on the deployed environment's settings, exactly like every other environment-driven singleton in this codebase:

```python
def _build_default_file_storage() -> FileStorage:
    if settings.cas_file_storage_backend == "s3":
        return S3FileStorage()
    return LocalFileStorage()


default_file_storage = _build_default_file_storage()
```

`boto3` is already a backend dependency (used by `app/services/analytics/dispatch.py` for ECS `RunTask`) — no new dependency to add.

### B3. Tests — `backend/tests/services/import_/test_file_storage.py`

Add, mocking `boto3` rather than hitting real AWS:

```python
from unittest.mock import MagicMock, patch

from app.services.import_.file_storage import S3FileStorage


def test_s3_file_storage_save_calls_put_object():
    with patch("boto3.client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        storage = S3FileStorage(bucket_name="test-bucket")

        result = storage.save("user1/import1.pdf", b"pdf-bytes")

        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket", Key="user1/import1.pdf", Body=b"pdf-bytes"
        )
        assert result == "user1/import1.pdf"


def test_s3_file_storage_read_returns_body_bytes():
    with patch("boto3.client") as mock_client_factory:
        mock_client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"pdf-bytes"
        mock_client.get_object.return_value = {"Body": mock_body}
        mock_client_factory.return_value = mock_client
        storage = S3FileStorage(bucket_name="test-bucket")

        result = storage.read("user1/import1.pdf")

        mock_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="user1/import1.pdf")
        assert result == b"pdf-bytes"


def test_s3_file_storage_delete_calls_delete_object():
    with patch("boto3.client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        storage = S3FileStorage(bucket_name="test-bucket")

        storage.delete("user1/import1.pdf")

        mock_client.delete_object.assert_called_once_with(Bucket="test-bucket", Key="user1/import1.pdf")
```

Run: `cd backend && pytest tests/services/import_/test_file_storage.py -v` — all tests (existing + these 3 new) should pass without any AWS credentials configured, since `boto3.client` is mocked.

---

## Part C — The one manual, non-Terraform step

Confirm Postmark's Sender Signature for the address that will be `postmark_from_email` (the `TF_VAR_postmark_from_email` value in Part D):

1. Log into `account.postmarkapp.com`.
2. **Sender Signatures** → **Add Sender Signature** → enter the exact address and a display name.
3. Postmark emails a confirmation link to that address (it lands in the existing Microsoft 365 mailbox — no DNS/Route 53 change needed).
4. Whoever owns that mailbox clicks the link. Signature shows "Confirmed."

Do this before or after the Terraform apply — order doesn't matter, but emails won't actually send until it's done.

---

## Part D — Runbook

**D1. Generate the two PAN key values locally** (32 random bytes each, base64-encoded):

```bash
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
```

Run it twice — the two outputs must be different values (one is the encryption key, one is the lookup pepper; reusing one key for both defeats the point of keeping them separate).

**D2. Set the sensitive values as environment variables** in the shell that will run `terraform apply` — never write these into any `.tfvars` file:

```bash
export TF_VAR_pan_encryption_key="<first value from D1>"
export TF_VAR_pan_lookup_pepper="<second value from D1>"
export TF_VAR_postmark_api_token="<the real Postmark server API token>"
export TF_VAR_postmark_from_email="<the address confirmed in Part C>"
```

**D3. Apply:**

```bash
cd infra/envs/staging
terraform init   # only needed the first time, or after adding the new module
terraform plan
```

Read the plan output. Expect to see: 1 new S3 bucket + its 4 sub-resources (public-access-block, versioning, encryption, lifecycle), 2 new Secrets Manager secrets + their 2 versions, 1 replaced `aws_iam_role_policy` (the rename in A4a — Terraform will show this as delete+create, not a destructive change to the role itself), 1 new `aws_iam_role_policy` (A4b), and an in-place update to both ECS task definitions (new revision, not destroyed). If the plan shows anything destroying the RDS database, the ECS cluster, or the VPC, **stop and don't apply** — nothing in this plan should touch those.

```bash
terraform apply
```

**D4. Verify:**

1. `terraform output cas_files_bucket_name` — confirm the bucket exists: `aws s3 ls s3://<that name>/` (should be empty right after creation).
2. Confirm the ECS service redeployed with the new task definition revision (check the ECS console, or `aws ecs describe-services`).
3. Do a real CAS import against the staging URL. Then:
   ```bash
   aws s3 ls s3://<cas-files-bucket-name>/ --recursive
   ```
   should show the uploaded file under a `<user_id>/<import_id>.pdf` key.
4. Trigger a real OTP send (e.g. sign up with a real email) and confirm it actually arrives — this exercises the Postmark secret injection end-to-end, not just that the container booted.

**D5. If something's wrong:** `terraform apply` on this plan doesn't touch or replace the RDS instance, VPC, or ECS cluster, so a bad apply here is recoverable by fixing the Terraform and re-applying, or `terraform destroy -target=module.storage` to remove just the new bucket if it needs to be redone. Don't run a bare `terraform destroy` — that would tear down everything Phase 0/1 already defined, not just this plan's additions.
