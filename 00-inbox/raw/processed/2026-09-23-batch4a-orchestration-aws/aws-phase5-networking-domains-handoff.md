# Handoff: aws-phase5-networking-domains

**Status:** DONE
**Parent plan:** `AWS Readiness/aws-golive-readiness-report.md` §9 (Terraform strategy), §19 (resolved decisions), §22 Phase 5 (Networking & Domains)
**Depends on:** `aws-phase4-frontend-deployment` must be `DONE` (reviewed **and** applied) before this is dispatched — this task modifies live resources Phase 4 creates (`infra/modules/frontend`'s CloudFront distribution) and adds a new HTTPS listener to a live resource Phase 3 created (`infra/modules/backend`'s ALB). Do not dispatch this to Codex until Phase 4's `terraform apply` has actually run.

## Task

Author (do not apply) the TLS/domain layer for staging: two ACM certificates
(one `us-east-1` for CloudFront, one `ap-south-1` for the ALB), DNS
validation records and an HTTPS listener on the existing ALB, and Route 53
alias records pointing `staging.unifolio.in` at CloudFront and
`staging-api.unifolio.in` at the ALB. Unlike Phase 4, this dispatch **does**
touch two already-authored modules (`modules/backend`, `modules/frontend`) —
that's expected; Phase 3's own listener comment ("Phase 5 is where HTTPS is
added") and Phase 4's own `viewer_certificate` comment both anticipated this.

**This is authoring only** — same boundary as every prior phase. Do not run
`terraform apply`. Do not touch `frontend/` (the actual frontend rebuild with
the new `https://staging-api.unifolio.in` API URL, and the S3
upload/CloudFront invalidation that follows, are separate manual steps after
this Terraform is applied — not part of this dispatch).

### Directory layout to add/change

```
infra/
  modules/
    dns/                          (NEW)
      main.tf     (2x aws_acm_certificate, their DNS validation records,
                    2x aws_acm_certificate_validation, 2x Route 53 alias
                    record)
      variables.tf
      outputs.tf   (frontend_acm_certificate_arn, backend_acm_certificate_arn)
    backend/
      main.tf       (CHANGE: add aws_lb_listener "https"; change
                      aws_lb_listener "http"'s default_action to a redirect)
      variables.tf  (CHANGE: add acm_certificate_arn)
      outputs.tf    (CHANGE: add alb_zone_id)
    frontend/
      main.tf       (CHANGE: aliases + viewer_certificate on the existing
                      aws_cloudfront_distribution.this)
      variables.tf  (CHANGE: add domain_name, acm_certificate_arn)
  envs/
    staging/
      main.tf        (add `data "aws_route53_zone" "primary"`, add
                       `module "dns"`, pass its outputs into `module
                       "backend"` and `module "frontend"`)
```

### Route 53 zone lookup (`envs/staging/main.tf`)

The `unifolio.in` public hosted zone already exists (created manually/
out-of-band in an earlier session, not by Terraform — confirmed zero
`aws_route53_zone` resources exist anywhere in `infra/`). Reference it via a
data source, do not create a new zone:

```hcl
data "aws_route53_zone" "primary" {
  name         = "unifolio.in."
  private_zone = false
}
```

Pass `zone_id = data.aws_route53_zone.primary.zone_id` into `module "dns"`.

### `modules/dns` — ACM certificates

Two certificates, **in different regions, each via the matching provider**:

- **CloudFront cert** (for `staging.unifolio.in`): `aws_acm_certificate`,
  `validation_method = "DNS"`, **`provider = aws.us_east_1`** (the alias
  already reserved in `envs/staging/providers.tf` specifically for this).
  CloudFront only ever accepts certs from `us-east-1`, regardless of the
  stack's primary region — this is a hard AWS requirement, not a style
  choice.
- **ALB cert** (for `staging-api.unifolio.in`): `aws_acm_certificate`,
  `validation_method = "DNS"`, default provider (`ap-south-1`) — no alias
  needed, the ALB lives in the stack's primary region.
- For each cert: `for_each` over
  `aws_acm_certificate.<x>.domain_validation_options` to create the DNS
  validation `aws_route53_record`, then an `aws_acm_certificate_validation`
  resource referencing the validation record FQDNs, waiting for AWS to
  actually issue the cert before Terraform proceeds.
- **The DNS validation `aws_route53_record` resources use the default
  provider for both certs, even the `us-east-1` one** — Route 53 is a
  global service with no per-region distinction; only the `aws_acm_certificate`
  and `aws_acm_certificate_validation` resources themselves need the
  `us_east_1` alias. This is a common point of confusion worth getting
  right the first time rather than debugging a provider-mismatch error.
- Module inputs needed: `zone_id` (from the data source above),
  `frontend_domain_name` (`staging.unifolio.in`), `backend_domain_name`
  (`staging-api.unifolio.in`).
- Module outputs: `frontend_acm_certificate_arn` (the validated `us-east-1`
  cert's ARN), `backend_acm_certificate_arn` (the validated `ap-south-1`
  cert's ARN).

### `modules/dns` — Route 53 alias records

Two alias records in the existing zone, both targeting resources that live
outside this module — take them as module inputs, don't hardcode:

- `staging.unifolio.in` → CloudFront. Alias `zone_id` and `name` both come
  from the CloudFront distribution's own computed attributes
  (`aws_cloudfront_distribution.this.hosted_zone_id` /
  `.domain_name`, passed in from `module "frontend"`'s existing
  `cloudfront_distribution_id`/`cloudfront_domain_name` outputs — add a
  third output, `cloudfront_hosted_zone_id`, to `modules/frontend/outputs.tf`
  for this). Do not hardcode CloudFront's well-known fixed hosted zone ID
  literal (`Z2FDTNDATAQYW3`) — read it off the distribution resource instead,
  so it's correct even if AWS ever changes it. `evaluate_target_health = false`
  (CloudFront doesn't support target health evaluation).
- `staging-api.unifolio.in` → ALB. Alias `zone_id`/`name` from the ALB's own
  `zone_id`/`dns_name` attributes — `modules/backend` doesn't currently
  output `alb_zone_id` (only `alb_dns_name`), so add that output (see
  "modules/backend changes" below). `evaluate_target_health = true`.

### `modules/backend` changes

- New variable `acm_certificate_arn` (string, no default — always supplied
  from Phase 5 onward).
- New output `alb_zone_id` — `aws_lb.this.zone_id` (needed by `modules/dns`
  for the alias record above).
- New resource `aws_lb_listener` `"https"`: port 443, protocol `HTTPS`,
  `certificate_arn = var.acm_certificate_arn`, a current recommended
  `ssl_policy` (e.g. `ELBSecurityPolicy-TLS13-1-2-2021-06`), default action
  `forward` to the existing `aws_lb_target_group.this` — same target group
  the HTTP listener already forwards to, nothing changes on the ECS/target-
  group side.
- **Change the existing `aws_lb_listener "http"`'s `default_action`** from
  `forward` to a `redirect`: `protocol = "HTTPS"`, `port = "443"`,
  `status_code = "HTTP_301"`. This is a genuine in-place modification to an
  already-applied, currently-live listener on a running ALB — flag this
  explicitly in your report, not because it's risky (changing a listener's
  default action doesn't tear down the load balancer, target group, or ECS
  service; there's a few-second gap where it applies the new rule), but
  because every prior phase only ever added new resources and this is the
  first one that changes existing live behavior.

### `modules/frontend` changes

- New variables: `domain_name` (string, e.g. `staging.unifolio.in`) and
  `acm_certificate_arn` (string, no default).
- On the existing `aws_cloudfront_distribution.this`: set
  `aliases = [var.domain_name]` (previously unset per Phase 4's design),
  and replace `viewer_certificate { cloudfront_default_certificate = true }`
  with:
  ```hcl
  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
  ```
- New output `cloudfront_hosted_zone_id` — `aws_cloudfront_distribution.this.hosted_zone_id`
  (see "Route 53 alias records" above).
- This is also a genuine in-place modification to an already-applied,
  live CloudFront distribution. Changing `aliases`/`viewer_certificate`
  triggers a full redistribution across CloudFront's edge network — expect
  `terraform apply` to take 15-25 minutes on this resource before it
  reports success (CloudFront's own `Deployed` status, which Terraform
  waits for by default). This is normal, not a hang — note it in your
  report so the user isn't caught off guard when they run `apply`
  themselves.

### envs/staging wiring

- Add `data "aws_route53_zone" "primary"` (see above).
- Add `module "dns"` with `zone_id`, `frontend_domain_name = "staging.unifolio.in"`,
  `backend_domain_name = "staging-api.unifolio.in"`, plus whatever the
  module needs from `module "frontend"` (`cloudfront_domain_name`,
  `cloudfront_hosted_zone_id`) and `module "backend"` (`alb_dns_name`,
  `alb_zone_id`) to build the alias records.
- Pass `module.dns.backend_acm_certificate_arn` into `module "backend"`'s
  new `acm_certificate_arn` variable.
- Pass `module.dns.frontend_acm_certificate_arn` and
  `domain_name = "staging.unifolio.in"` into `module "frontend"`'s new
  variables.
- Watch the dependency order here: `module "dns"` needs
  `module.frontend`'s CloudFront outputs to build the alias record, but
  `module "frontend"` also needs `module.dns`'s cert output for
  `viewer_certificate`. This is **not** a real cycle — the cert (issued
  against the zone) doesn't depend on the CloudFront distribution at all,
  only the *alias record* does. Structure `modules/dns` so the ACM
  cert/validation resources only take `zone_id` + domain name strings as
  input (no CloudFront/ALB dependency), and only the two
  `aws_route53_record` alias resources take the CloudFront/ALB attributes
  as input. That keeps the graph a clean DAG: `dns` (certs) → `backend` /
  `frontend` (consume cert ARNs, produce ALB/CloudFront attributes) → `dns`
  (alias records, consume those attributes) would still be a cycle at the
  *module* level if `module "dns"` is one indivisible unit depended on
  both ways. Resolve this the same way `modules/frontend`'s Phase 4
  bucket-policy/distribution circular dependency was resolved — through
  Terraform's normal resource-level (not module-level) dependency graph:
  put the alias `aws_route53_record` resources in `modules/dns` but have
  `envs/staging/main.tf` pass `module.frontend`'s and `module.backend`'s
  outputs into `module "dns"` as *plain input variables*, while `module
  "dns"`'s cert outputs are separately consumed by `module "backend"`/
  `module "frontend"`. Terraform resolves this fine at the resource graph
  level even though it looks like a module-level cycle on paper, because
  the actual dependency is cert-ARN-output → cert-ARN-input in one
  direction and CloudFront/ALB-attribute-output → alias-record-input in
  the other, non-overlapping direction. If this genuinely doesn't resolve
  cleanly once written, that's exactly the kind of thing to stop and flag
  per the Open Questions section below, rather than hacking around it.

## Constraints

- **Never run `terraform apply` or `terraform destroy`.**
- **Never run `npm run build`, `aws s3 cp`/`sync`, or
  `aws cloudfront create-invalidation`.** The frontend rebuild pointing at
  `https://staging-api.unifolio.in` is a manual step after this Terraform
  is applied, not part of this dispatch.
- You may and should run `terraform fmt` and `terraform validate`. Skip
  `terraform plan`.
- Do not modify `infra/modules/networking`, `infra/modules/security`,
  `infra/modules/database`, or `infra/modules/ecr` — unrelated to this
  task.
- Do not touch anything under `frontend/`.
- Do not touch `AWS Readiness/aws-golive-readiness-report.md` or any other
  doc — report anything that looks wrong back to the reviewer instead.
- Do not change the backend's `ALLOWED_ORIGINS`/`FRONTEND_BASE_URL` env vars
  in `modules/backend/main.tf` — they're already hardcoded to
  `https://staging.unifolio.in` from Phase 3 and need no change here.
- Do not add a Route 53 record or ACM cert for the apex `unifolio.in` domain
  or any production (`app.`/`api.`) subdomain — staging only, in this
  dispatch.

## Approaches considered and rejected

- **Path-based CloudFront routing instead of a dedicated `staging-api.`
  subdomain:** rejected — already decided in §19, resolved 2026-09-08, for
  the same reasons cited in Phase 4's handoff doc. Not revisited here.
- **A single ACM cert covering both domains (SAN cert) instead of two:**
  rejected — the two domains are consumed by two different AWS services in
  two different regions (CloudFront requires `us-east-1`, the ALB requires
  `ap-south-1`); ACM certs aren't shareable across regions regardless of
  SAN configuration, so two separate certs are required no matter what.
- **Leaving the HTTP listener as a plain forward (no redirect) once HTTPS
  exists:** rejected — §22 Phase 5's own task list calls for enforcing
  HTTP→HTTPS redirects; leaving HTTP as a silent parallel path defeats the
  point of adding TLS.
- **Rebuilding the CloudFront distribution from scratch with the domain/cert
  included from the start, instead of modifying Phase 4's existing one:**
  rejected — this was the explicit design intent written into Phase 4's own
  handoff doc (leave `aliases` unset and `viewer_certificate` on the default
  cert specifically so Phase 5 could add them additively); redoing that
  work would throw away Phase 4's already-reviewed resource and forces an
  unnecessary full distribution recreation instead of an in-place update.

## Open questions

- If the module-level dependency ordering described above (cert issuance
  vs. alias records) doesn't resolve cleanly as a single `modules/dns`
  module, the fallback is splitting it into two modules
  (`modules/acm-certificates` and `modules/dns-records`) — but try the
  single-module approach with resource-level (not module-level) dependency
  separation first, since it matches this repo's existing one-module-per-
  concern granularity. Flag back if the split turns out to be necessary.
- If `envs/staging/providers.tf`'s reserved `us_east_1` provider alias has
  drifted from what's described here (check the actual file, don't assume),
  reconcile against the actual file rather than this doc.
