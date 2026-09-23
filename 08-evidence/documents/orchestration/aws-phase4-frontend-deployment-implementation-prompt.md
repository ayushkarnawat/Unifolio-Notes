# Implementation session prompt — AWS Phase 4 frontend deployment

Paste everything below this line into your Codex session (`codex` CLI or the
Codex app) to start this task. This is a user-run dispatch — not run through
Claude Code's own Agent tool — per this project's established pattern (see
`Docs/orchestration/delegation-log.md`'s `worker=codex (user-run, direct
CLI/app — not Agent-dispatched)` entries). Do not self-review when done —
report back what you did and stop; a separate adversarial review pass runs
afterward, driven by the user relaying your output back into the main Claude
Code session.

**Status: Codex's part of this is already done and independently reviewed
(PASS, zero findings) — `infra/modules/frontend` exists and is committed.
Nothing below this point needs to be pasted into Codex again.**

## Manual steps for you, after Codex's part is done (not for Codex)

1. `cd infra/envs/staging && terraform init` (safe to rerun — no new
   provider, just picks up the new module).
2. `terraform plan -out=tfplan` — expect only new resources (S3 bucket,
   public access block, OAC, CloudFront distribution, bucket policy) and
   the new `data "aws_caller_identity"` lookup. **0 to change, 0 to
   destroy** on anything from Phase 1-3 — if you see anything proposed to
   change/destroy outside `module.frontend`, stop and paste the plan output
   back here before applying.
3. `terraform apply "tfplan"` — CloudFront's first-time distribution
   creation typically takes 15-20 minutes to reach `Deployed`; Terraform
   blocks until then by default. This is normal, not a hang.
4. After it finishes, save the three new outputs — you'll need them for
   Phase 5 and for the eventual frontend upload:
   `terraform output s3_bucket_name`, `terraform output
   cloudfront_distribution_id`, `terraform output cloudfront_domain_name`.
5. **Don't build/upload the frontend yet.** The ALB is still HTTP-only
   until Phase 5 lands, so any real API call from the deployed frontend
   would hit the browser's mixed-content block anyway — per your own call
   to build Phase 4 and 5 back to back and only test for real once both
   are applied. It's fine to open the `cloudfront_domain_name` URL in a
   browser now just to confirm CloudFront serves *something* (it'll show
   a blank/empty bucket, since nothing's uploaded yet) — that's optional,
   not required.
6. There's a leftover `infra/envs/staging/tfplan` binary in your working
   tree from an earlier `terraform plan` — it's already excluded from what
   got committed. Fine to leave it or delete it locally; just don't `git
   add` it (plan files can contain resource details and shouldn't be
   version-controlled).

---

<task>
Repo: Unifolio (mutual fund portfolio tracking platform, MF-only MVP),
branch `feat/enhanced-ui`. Author a new `infra/modules/frontend` Terraform
module: a private S3 bucket for the built React/Vite SPA, fronted by a
CloudFront distribution using Origin Access Control (OAC) — no public S3
access, no legacy Origin Access Identity. Wire it into
`infra/envs/staging/main.tf` as `module "frontend"`.

Full spec, exact resource settings, and the reasoning behind each decision
(including a real gotcha around CloudFront custom error responses that's
easy to get wrong): `Docs/orchestration/aws-phase4-frontend-deployment-handoff.md`.
Read it in full before writing any code — this prompt does not restate its
contents.

Also skim `infra/envs/staging/main.tf` (to see the exact pattern used for
`module "backend"`, which this should mirror) and
`infra/modules/backend/outputs.tf` (for the output-naming convention) so the
new module lines up with the existing ones — don't guess conventions.
</task>

<action_safety>
This is authoring only — you are not provisioning real AWS infrastructure
and not publishing anything. Never run `terraform apply`, `terraform destroy`,
`npm run build`, `aws s3 cp`/`sync`, or `aws cloudfront create-invalidation`.
This holds even if AWS credentials happen to be configured in your
environment. You may run `terraform fmt` and `terraform validate` freely.
Skip `terraform plan` entirely.

Keep Terraform changes scoped to `infra/modules/frontend` (new) and
`infra/envs/staging/main.tf` (extended, not rewritten). Do not modify
`infra/modules/networking`, `infra/modules/security`,
`infra/modules/database`, `infra/modules/ecr`, or `infra/modules/backend` —
those are done and already reviewed. Do not touch anything under
`frontend/`. Do not touch any doc. Do not add an ACM certificate,
`aliases`/custom domain on the CloudFront distribution, or any Route 53
record — that is Phase 5, a separate dispatch that will modify this same
distribution resource later.
</action_safety>

<default_follow_through_policy>
Default to the most reasonable low-risk interpretation and keep going. Only
stop and ask if you hit an actual technical conflict with the handoff doc's
design (not a style preference), per the handoff doc's own "Open questions"
section.
</default_follow_through_policy>

<completeness_contract>
Resolve the full Phase 4 scope from the handoff doc before stopping: the S3
bucket (globally-unique name including the AWS account ID, obtained via
`data "aws_caller_identity"`, not hardcoded) with a full public-access
block; the OAC resource; the bucket policy scoped to this specific
distribution's ARN via an `AWS:SourceArn` condition; the CloudFront
distribution with `default_root_object = "index.html"`,
`redirect-to-https`, PriceClass_100, and — this is the part most likely to
get missed — a `custom_error_response` mapping **both 403 and 404** to
`/index.html` with response code 200 (read the handoff doc's explanation of
why 403 matters, not just 404); the three module outputs
(`s3_bucket_name`, `cloudfront_distribution_id`, `cloudfront_domain_name`);
and the `envs/staging` wiring including three new root-level outputs.
</completeness_contract>

<verification_loop>
Run `terraform fmt -recursive` and `terraform validate` against the new
`modules/frontend` and against `envs/staging` before finalizing. If
validate fails, fix and re-check.
</verification_loop>

<compact_output_contract>
When done, report back compactly: what you built (directory tree is enough,
don't paste every file), how you handled the OAC/bucket-policy circular
dependency, the exact `terraform fmt`/`validate` results, and anything from
the handoff doc's "Open questions" section you had to resolve yourself vs.
anything you're flagging back unresolved. Do not run or offer to run a
self-review — that step happens separately, on the Claude Code side, after
this report is relayed back.
</compact_output_contract>
