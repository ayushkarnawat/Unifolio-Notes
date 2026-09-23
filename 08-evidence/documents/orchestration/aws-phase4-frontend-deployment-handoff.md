# Handoff: aws-phase4-frontend-deployment

**Status:** DONE
**Parent plan:** `AWS Readiness/aws-golive-readiness-report.md` §9 (Terraform strategy), §19 (resolved decisions), §22 Phase 4 (Frontend Deployment)

## Task

Author (do not apply) a new `infra/modules/frontend` Terraform module: a
private S3 bucket for the built React/Vite SPA, fronted by a CloudFront
distribution using Origin Access Control (OAC) — no public S3 access, no
legacy Origin Access Identity. Wire it into `infra/envs/staging/main.tf` as
`module "frontend"`.

**This is authoring only** — same boundary as Phases 1-3. Do not run
`terraform apply`, do not run `npm run build`, do not upload anything to S3,
do not touch anything under `frontend/`.

**Explicitly deferred to a later, separate dispatch (Phase 5) — do not do
any of this here:** no ACM certificate, no custom domain / `aliases` on the
CloudFront distribution, no Route 53 records. This distribution serves only
CloudFront's own default `*.cloudfront.net` domain and CloudFront's own
built-in default certificate for now. Phase 5 will modify this same
distribution resource in a later dispatch to add the real domain — leave the
distribution's `aliases` unset and `viewer_certificate` pointed at
`cloudfront_default_certificate = true` so that follow-up change is additive.

### Directory layout to add/change

```
infra/
  modules/
    frontend/
      main.tf       (S3 bucket, public-access block, OAC, bucket policy,
                      CloudFront distribution)
      variables.tf
      outputs.tf     (s3_bucket_name, cloudfront_distribution_id,
                       cloudfront_domain_name)
  envs/
    staging/
      main.tf        (add `module "frontend"`, plus 3 new root outputs
                       mirroring the module's outputs — same pattern as
                       `module "backend"`)
```

Don't touch `infra/modules/networking`, `infra/modules/security`,
`infra/modules/database`, `infra/modules/ecr`, or `infra/modules/backend` —
this module is self-contained and needs none of their outputs (S3+CloudFront
here has no VPC/network dependency at all).

### S3 bucket (`modules/frontend`)

- Name: `"${var.project}-${var.environment}-frontend-${var.account_id}"` —
  S3 bucket names are globally unique across *all* AWS accounts, not just
  this one, so the account ID must be part of the name. Follow the exact
  same pattern already used for the Terraform state bucket
  (`unifolio-tfstate-staging-811364789032`, see
  `infra/bootstrap/create-state-backend.sh`) — add a new `account_id`
  variable to this module (plain string, no default) rather than hardcoding
  the account ID, and pass it from `envs/staging/main.tf` (there's no
  existing Terraform data source for the caller's account ID anywhere in
  this repo yet; add `data "aws_caller_identity" "current" {}` in
  `envs/staging/main.tf` and pass
  `account_id = data.aws_caller_identity.current.account_id` into the
  module — don't hardcode the literal account ID string anywhere).
- `aws_s3_bucket_public_access_block` on it with all four flags (`block_public_acls`,
  `block_public_policy`, `ignore_public_acls`, `restrict_public_buckets`) set
  to `true` — this bucket must never be reachable directly, only through
  CloudFront's OAC path.
- No versioning, no lifecycle policy, no website-hosting configuration —
  none of these are in scope per the readiness doc's Phase 4 task list
  (`S3 bucket (private, Origin Access Control only)`); don't add them
  speculatively.

### Origin Access Control + bucket policy (`modules/frontend`)

- `aws_cloudfront_origin_access_control` — `signing_behavior = "always"`,
  `signing_protocol = "sigv4"`, `origin_access_control_origin_type = "s3"`.
  This is the modern OAC mechanism; do not use the legacy
  `aws_cloudfront_origin_access_identity`.
- `aws_s3_bucket_policy` on the bucket: allow `s3:GetObject` to principal
  `cloudfront.amazonaws.com`, scoped with a `Condition` on
  `AWS:SourceArn` equal to *this specific distribution's* ARN (not a
  wildcard, not any-distribution-in-account) — least privilege, matches the
  scoping discipline already used for the IAM policies in
  `modules/backend`. This creates an inherent dependency ordering (the
  bucket policy needs the distribution's ARN, and the distribution needs
  the bucket as an origin) — resolve via Terraform's normal implicit
  dependency graph, referencing `aws_cloudfront_distribution.this.arn` in
  the policy document; do not try to break the cycle by hardcoding an ARN
  or adding an artificial two-pass apply step.

### CloudFront distribution (`modules/frontend`)

- `origin` — the S3 bucket's *regional* domain name
  (`aws_s3_bucket.this.bucket_regional_domain_name`, not the legacy
  website-endpoint domain), `origin_id` = the bucket name, `origin_access_control_id`
  set to the OAC resource above (no `s3_origin_config`/OAI block — OAC
  replaces that entirely).
- `enabled = true`, `is_ipv6_enabled = true`, `default_root_object = "index.html"`.
- `default_cache_behavior`: `allowed_methods = ["GET", "HEAD"]`,
  `cached_methods = ["GET", "HEAD"]` (this distribution only ever serves
  static built assets — no POST/PUT ever needs to reach it, the API lives
  on a completely separate origin/domain per §19's already-resolved
  dedicated-subdomain decision), `viewer_protocol_policy = "redirect-to-https"`,
  `target_origin_id` = the S3 origin above, `forwarded_values` (or the
  modern cache-policy equivalent, either is fine) with no query-string/cookie
  forwarding needed for a static SPA bundle. Reasonable TTLs (e.g.
  `min_ttl = 0`, `default_ttl = 86400`, `max_ttl = 31536000`) — deploys are
  expected to explicitly invalidate the cache afterward (that's the next
  manual step after this Terraform, per §22 Phase 4's own task list), so a
  same-day default TTL is fine, don't over-think this number.
- **`custom_error_response` — map *both* 403 and 404 to `/index.html` with
  `response_code = 200`, not just 404.** This is a real, easy-to-miss gotcha
  worth a code comment: an OAC-fronted private S3 bucket (no
  `s3:ListBucket` granted to CloudFront, by design) returns **403 Access
  Denied**, not 404, when a requested object doesn't exist — so a
  React-Router client-side route like `/dashboard` or `/print/analytics`
  will hit S3 as a missing key and come back 403, not 404. Mapping only 404
  would leave every SPA deep-link broken. Map both.
- `viewer_certificate { cloudfront_default_certificate = true }` — no ACM
  cert, no `aliases` block on the distribution at all in this dispatch (see
  "Explicitly deferred" above).
- `restrictions { geo_restriction { restriction_type = "none" } }` (required
  block, no actual restriction needed).
- `price_class = "PriceClass_100"` (US/Canada/Europe only) — deliberate
  staging-cost choice, cheaper than the default all-edge-locations class;
  fine to reconsider for production later, don't treat this as a
  correctness issue.

### Outputs (`modules/frontend/outputs.tf`)

- `s3_bucket_name` — needed for the manual `aws s3 sync`/`aws s3 cp` upload
  step that follows this Terraform.
- `cloudfront_distribution_id` — needed for the manual
  `aws cloudfront create-invalidation` step that follows this Terraform.
- `cloudfront_domain_name` — the distribution's own `*.cloudfront.net`
  domain (`aws_cloudfront_distribution.this.domain_name`); this is the
  actual reachable URL for the app until Phase 5 attaches
  `staging.unifolio.in`, and it's also needed as an immediate manual
  smoke-test target right after this gets applied.

### envs/staging wiring

Add `module "frontend"` to `infra/envs/staging/main.tf`, following the exact
pattern already used for `module "backend"`. Add the
`data "aws_caller_identity" "current" {}` data source (see S3 bucket section
above) and pass its `account_id` into the module. Surface `s3_bucket_name`,
`cloudfront_distribution_id`, and `cloudfront_domain_name` as new root-level
outputs, same pattern as the existing `alb_dns_name`/etc. outputs.

## Constraints

- **Never run `terraform apply` or `terraform destroy`.** Same boundary as
  every prior phase — see `AWS Readiness/aws-golive-readiness-report.md` §20.
- **Never run `npm run build`, `aws s3 cp`/`sync`, or
  `aws cloudfront create-invalidation`.** This dispatch authors Terraform
  only; it does not build or publish the frontend.
- You may and should run `terraform fmt` and `terraform validate` (per new
  module and for the full `envs/staging` root). Skip `terraform plan` —
  same reasoning as every prior phase, upstream resources this doesn't even
  depend on may or may not be real depending on session state, and this
  module has no dependency on them anyway.
- Do not modify `infra/modules/networking`, `infra/modules/security`,
  `infra/modules/database`, `infra/modules/ecr`, or `infra/modules/backend`.
- Do not touch anything under `frontend/` (no `.env` files, no
  `vite.config.ts` changes, nothing) — this is an infra-only dispatch.
- Do not touch `AWS Readiness/aws-golive-readiness-report.md` or any other
  doc — report anything that looks wrong back to the reviewer instead of
  editing docs yourself.
- Scope is Phase 4 only. No ACM certificate, no CloudFront `aliases`, no
  Route 53 records, no ALB changes — that's Phase 5, a separate dispatch.

## Approaches considered and rejected

- **Legacy Origin Access Identity (OAI) instead of OAC:** rejected — OAC is
  AWS's current recommended mechanism (supports SSE-KMS-encrypted origins
  and all S3 regions correctly; OAI has known gaps with newer S3 features).
  No reason to use the deprecated path on a from-scratch build.
- **Mapping only 404 → `/index.html` in the custom error response:**
  rejected — see the CloudFront section above; a private OAC-fronted bucket
  actually returns 403 for missing keys, so 404-only would leave client-side
  routing broken for every deep link. Map both codes.
- **A single combined CloudFront distribution serving both the frontend
  (S3 origin) and the API (ALB origin) via path-based routing
  (`/api/*` → ALB):** rejected — this exact tradeoff was already decided in
  §19 (`AWS Readiness/aws-golive-readiness-report.md`, "Backend API domain
  naming"), resolved 2026-09-08 in favor of a dedicated subdomain
  (`staging-api.unifolio.in`) specifically *to avoid* CloudFront
  dual-origin/behavior-precedence complexity and to keep the CAS-import PDF
  upload path off CloudFront entirely. Don't revisit that decision in this
  dispatch.
- **Bucket versioning / lifecycle rules:** rejected as out of scope — not
  called for by §22 Phase 4's task list, adds cost/complexity with no
  stated need yet; revisit only if a real rollback requirement shows up
  later.

## Open questions

- If `envs/staging/main.tf` already has a `data "aws_caller_identity"` block
  under a different name, reuse it rather than adding a duplicate — check
  the actual file first rather than assuming it's absent.
- If anything about the OAC/bucket-policy circular-dependency handling
  doesn't resolve cleanly under plain Terraform (it should — this is a
  well-trodden pattern), stop and flag it back rather than working around it
  with a hardcoded ARN or a manual two-step apply instruction.
