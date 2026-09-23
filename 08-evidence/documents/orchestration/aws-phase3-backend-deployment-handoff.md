# Handoff: aws-phase3-backend-deployment

**Status:** DONE — reviewed 2026-09-08, PASS zero findings, see delegation-log.md.
**Parent plan:** `AWS Readiness/aws-golive-readiness-report.md` §9 (Terraform strategy), §11 (KMS), §19 (resolved decisions), §22 Phase 3 (Backend Deployment); `AWS Readiness/aws-golive-launch-blockers.md` (single-task/no-autoscaling constraint)

## Task

Author (do not apply, do not build/push a Docker image) the Terraform for the
staging ECS Fargate backend: an ECR repository, an ECS cluster/task
definition/service, an ALB (HTTP-only for now, HTTPS is Phase 5), the
supporting IAM roles, and CloudWatch logging. Also make one small Docker
change (an entrypoint script) so the container can assemble `DATABASE_URL`
from RDS-managed pieces without Terraform ever handling the plaintext
password — see "Secrets design" below, this was decided explicitly with the
user after flagging a real conflict with Phase 2's own security goal.

**This is authoring only.** Same boundary as Phase 1/2 — see Constraints.

**Explicitly out of scope, even though §22 Phase 3 mentions it as part of
"Phase 3":** building the Docker image and pushing it to ECR. That requires
real AWS credentials and `docker build`/`docker push`, neither of which this
dispatch can do. The ECS service will reference an image tag that doesn't
exist yet in ECR until the account owner does that manually post-apply —
this is expected and fine; don't try to work around it or block on it.

### Directory layout to add/change

```
infra/
  modules/
    ecr/
      main.tf        (aws_ecr_repository, scan-on-push, lifecycle policy)
      variables.tf
      outputs.tf      (repository_url, repository_arn)
    backend/
      main.tf         (ECS cluster, CloudWatch log group, IAM execution role
                        + policies, task definition, ECS service, ALB, target
                        group, HTTP listener)
      variables.tf
      outputs.tf      (alb_dns_name, ecs_cluster_name, ecs_service_name)
  envs/
    staging/
      main.tf         (add `module "ecr"` and `module "backend"`, wire their
                        inputs from the existing networking/security/database
                        module outputs; add the new outputs to the root)
backend/
  Dockerfile           (add an ENTRYPOINT pointing at the new script below —
                        this is the only edit to this file)
  docker-entrypoint.sh (new — see "Secrets design")
```

Don't touch `infra/modules/networking`, `infra/modules/security`, or
`infra/modules/database` — Phases 1 and 2 are done and reviewed, this
dispatch only adds `modules/ecr` and `modules/backend` and extends
`envs/staging/main.tf`. **Under `backend/`, touch only `Dockerfile` and the
new `docker-entrypoint.sh` — do not touch anything under `backend/app/` or
any test file.** This is a Terraform/Docker-config dispatch, not an
application-code dispatch.

### Secrets design (decided with the user, read this before writing the task definition)

Phase 2's RDS module uses `manage_master_user_password = true` specifically
so the master password is generated and owned by AWS, never appearing in
Terraform state. The app's config (`backend/app/config.py`) wants one single
`DATABASE_URL` connection-string env var, which creates a real tension: the
naive way to produce that one string via Terraform (read the RDS-managed
secret with a data source, interpolate the pieces into a new secret) would
put the plaintext password into Terraform state after all, defeating Phase
2's whole point — and would also go silently stale on any future password
rotation, since the RDS secret rotating wouldn't update a Terraform-built
copy.

**Decided approach:** ECS/Fargate fetches the password field directly from
the RDS-managed secret at container-start time — Terraform never reads or
touches the value, only its ARN. A small entrypoint script assembles
`DATABASE_URL` from parts immediately before starting uvicorn.

- Container **plain environment variables** (not secret; not sensitive by
  themselves): `ENVIRONMENT=staging`, `ALLOWED_ORIGINS=https://staging.unifolio.in`,
  `FRONTEND_BASE_URL=https://staging.unifolio.in`, `OTP_DELIVERY_MODE=stub`
  (matches the team's 2026-08-31 decision, already the code default but
  worth being explicit in infra), `GOOGLE_OAUTH_CLIENT_ID` (wire from a new
  Terraform variable with an empty-string default — non-blocking for
  staging per the launch-blockers doc, can be filled in later without a
  Terraform redesign), `DB_USERNAME=unifolio` (matches Phase 2's hardcoded
  master username — not secret, no need to fetch it from the secret JSON),
  `DB_HOST` = `module.database.db_address`, `DB_PORT` = `module.database.db_port`
  (cast to string), `DB_NAME` = `module.database.db_name`.
- Container **`secrets` block** (ECS-native, fetched at container start, never
  touches Terraform state): `DB_PASSWORD`, `valueFrom` = the RDS master
  secret's ARN with the `password` JSON key selector appended —
  `"${module.database.master_user_secret_arn}:password::"` (this is ECS's
  documented syntax for pulling one field out of a JSON secret; do not
  fetch the whole secret and do not also pull `username` this way, it's
  unnecessary since the username isn't sensitive).
- **`backend/docker-entrypoint.sh`** (new file): a `sh` script that builds
  `DATABASE_URL` from `DB_USERNAME`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT`/`DB_NAME`
  and then `exec`s uvicorn. **URL-encode `DB_PASSWORD` before interpolating
  it** — RDS's own master-password character rules forbid `/`, `"`, and `@`
  (so those specific characters can't appear), but characters like `:`, `#`,
  or `%` are still allowed in an RDS-generated password and would corrupt a
  naively-built connection string (a `:` would terminate the userinfo field
  early, `#` would start a URL fragment, `%` would be read as a percent-escape).
  The base image already has Python 3 available, so use it for the encoding,
  e.g. `python3 -c "import urllib.parse,os,sys; sys.stdout.write(urllib.parse.quote_plus(os.environ['DB_PASSWORD']))"`
  captured into a variable, then build the URL from the encoded value — don't
  interpolate `$DB_PASSWORD` directly into the connection string unencoded.
- **`backend/Dockerfile`**: `COPY` the new script in, `chmod +x` it, and set
  it as the image's `ENTRYPOINT` (replacing the current bare `CMD`). Don't
  change anything else in the Dockerfile.

### ECR (`modules/ecr`)

- One repository, name `unifolio-staging-backend` (ECR repo names are
  account-wide, not per-environment via a Terraform resource address, so the
  environment needs to be in the literal name to avoid colliding with a
  future production repo).
- `image_tag_mutability = "MUTABLE"` — fine for staging without CI/CD yet;
  revisit to immutable tags once real CI/CD exists (Phase 7, not now).
- `image_scanning_configuration { scan_on_push = true }` — free, no reason
  to skip it.
- A lifecycle policy that expires untagged images after a reasonable window
  (e.g. 14 days) so failed/superseded pushes don't accumulate storage cost
  forever. Don't add a policy that expires *tagged* images — there's no
  CI/CD yet generating a high volume of tags to prune.

### ECS cluster, task definition, service (`modules/backend`)

- `aws_ecs_cluster` — plain, no Container Insights (unnecessary cost for a
  low-traffic staging environment; add later if actually needed).
- `aws_cloudwatch_log_group` for the task's `awslogs` driver, name
  `/ecs/staging-backend`, `retention_in_days = 7` (staging default, cheap;
  not the right number for production later).
- **IAM execution role** (`aws_iam_role`, assumed by `ecs-tasks.amazonaws.com`):
  - Attach the AWS-managed `AmazonECSTaskExecutionRolePolicy` (covers ECR
    image pulls and writing to CloudWatch Logs).
  - Attach a custom inline/managed policy granting exactly:
    `secretsmanager:GetSecretValue` scoped to `module.database.master_user_secret_arn`
    only (not `*`), and `kms:Decrypt` + `kms:DescribeKey` (not `kms:GenerateDataKey*`
    — that's for encrypting new data, not needed for a read-only fetch) scoped
    to `module.security.kms_key_arn` only. This is the grant both Phase 1's
    and Phase 2's own code comments already flagged as "Phase 3 must attach
    this" — resolving those TODOs is part of this dispatch.
  - No separate ECS **task role** (as opposed to the execution role) — the
    app doesn't call any AWS APIs itself today, only the execution role's
    pull/logs/secrets permissions are actually needed. Don't add one
    speculatively.
- **Task definition**: Fargate, `cpu = 512`, `memory = 2048` (staging
  default sized for headroom during Playwright/Chromium PDF export, not a
  hard commitment — resizable later like Phase 2's RDS instance class).
  One container, image = `"${module.ecr.repository_url}:${var.image_tag}"`
  (new `image_tag` variable, default `"latest"`; note in a comment that this
  is a placeholder until real CI/CD tags images properly — Phase 7, not
  this dispatch), `containerPort = 8000`, `awslogs` log driver pointing at
  the log group above, the environment/secrets lists from "Secrets design".
- **ECS service**: `launch_type = "FARGATE"`, `desired_count = 1`,
  `network_configuration` using `module.networking.private_app_subnet_ids`
  and `module.networking.ecs_security_group_id`, `assign_public_ip = false`
  (private subnets route outbound through Phase 1's fck-nat instance).
  `health_check_grace_period_seconds = 60` (give the container's Playwright
  browser startup time before the ALB starts health-checking it). Link it to
  the target group below via `load_balancer { ... container_port = 8000 }`.
  **`deployment_maximum_percent = 100`, `deployment_minimum_healthy_percent = 0`**
  — this is not a default, it's a deliberate implementation of
  `AWS Readiness/aws-golive-launch-blockers.md`'s documented constraint
  ("stop-then-start deploy strategy, never a rolling deploy with 2 tasks
  briefly live") — the app has known in-process state that breaks under 2+
  concurrently-running tasks, so every deploy must fully stop the old task
  before starting the new one. Add a one-line comment on the service
  resource citing that doc, don't leave this setting unexplained.
  **Do not create any `aws_appautoscaling_target` or `aws_appautoscaling_policy`
  resource** — the same doc requires auto-scaling to stay fully disabled,
  not just defaulted off; the absence of these resources is itself the
  correct implementation, don't add them "for completeness."

### ALB, target group, listener (`modules/backend`)

- `aws_lb`, `internal = false`, in `module.networking.public_subnet_ids`,
  `security_groups = [module.networking.alb_security_group_id]` (Phase 1's
  ALB SG already has the correct 80/443 ingress and ECS-only egress rules —
  don't create a new one).
- `aws_lb_target_group`, `target_type = "ip"` (required for Fargate
  `awsvpc` networking mode), port 8000, protocol HTTP, `vpc_id` =
  `module.networking.vpc_id`. Health check: path `/health`, matcher `200`,
  reasonable interval/timeout/threshold defaults (e.g. 30s interval, 5s
  timeout, 2 healthy/2 unhealthy threshold).
- `aws_lb_listener`, port 80, protocol HTTP only — **no HTTPS listener and
  no ACM certificate in this dispatch.** §22 Phase 5 is explicitly where
  ACM certs and HTTPS get attached, once a real domain exists; an ALB's own
  AWS-generated DNS name can't get a usable ACM certificate anyway. Default
  action: forward to the target group.

### Outputs (`modules/backend/outputs.tf`)

- `alb_dns_name` — needed to validate Phase 3 per §22's own validation step
  ("`/health` returns 200 from the ALB's DNS name") and as the temporary
  reachability point before Phase 5 attaches a real domain.
- `ecs_cluster_name`, `ecs_service_name` — useful for the account owner to
  reference when manually building/pushing the image and forcing a new
  deployment afterward.

### envs/staging wiring

Add `module "ecr"` and `module "backend"` to `infra/envs/staging/main.tf`,
following the exact pattern already used for `module "database"` — pass in
whatever the new modules need from `module.networking`, `module.security`,
and `module.database`'s existing outputs (re-read those output names from
the actual files, don't guess). Surface `alb_dns_name`, `ecs_cluster_name`,
and `ecs_service_name` as new root-level outputs, same pattern as Phase 2's
`db_endpoint`/etc. outputs.

## Constraints

- **Never run `terraform apply` or `terraform destroy`.** Same boundary as
  Phase 1/2 — see `AWS Readiness/aws-golive-readiness-report.md` §20.
  Applies even if AWS credentials happen to be configured in your
  environment.
- **Never run `docker build`, `docker push`, or any `aws ecr` CLI command.**
  This dispatch authors the Terraform and the entrypoint script only; it
  does not build or publish the container image.
- You may and should run `terraform fmt` and `terraform validate` (per new
  module and for the full `envs/staging` root). Skip `terraform plan`
  entirely for this dispatch, same reasoning as Phase 2 — Phase 1/2
  resources this depends on may already be real if the account owner has
  applied them since the last session.
- Do not modify `infra/modules/networking`, `infra/modules/security`, or
  `infra/modules/database`.
- Under `backend/`, touch only `Dockerfile` (one edit: add the entrypoint)
  and the new `backend/docker-entrypoint.sh`. Do not touch
  `backend/app/**`, any test file, or `requirements.txt`.
- Do not touch `AWS Readiness/aws-golive-readiness-report.md`,
  `AWS Readiness/aws-golive-launch-blockers.md`, or any other doc — code-only
  dispatch. Report anything that looks wrong back to the reviewer instead of
  editing docs yourself.
- Scope is Phase 3 only. Do not start Phase 4 (frontend/S3/CloudFront) or
  Phase 5 (ACM/HTTPS/real domains) — no ACM certificate, no HTTPS listener,
  no Route 53 records in this dispatch.

## Approaches considered and rejected

- **Terraform-composed single `DATABASE_URL` secret (Option B from the
  discussion with the user):** rejected — puts the RDS master password into
  Terraform state, defeating Phase 2's `manage_master_user_password` choice,
  and goes silently stale on password rotation. See "Secrets design" above
  for the chosen alternative and full reasoning.
- **A separate ECS task role in addition to the execution role:** rejected
  for now — the app makes no AWS API calls of its own; only pull/logs/secrets
  permissions (which belong to the execution role) are needed. Revisit only
  if a future feature needs the running container to call an AWS API
  directly.
- **Enabling ECS service auto-scaling with a low max:** rejected — the
  launch-blockers doc's single-task constraint isn't about keeping scale
  *low*, it's about **never** running 2+ tasks concurrently, since the app's
  in-process caches produce real data-correctness bugs otherwise (a user can
  see stale pre-import portfolio values). Don't build any auto-scaling
  resource, not even one with `max_capacity = 1`.
- **HTTPS/ACM in this same dispatch to "save a phase":** rejected — §22
  deliberately sequences this into Phase 5, after the domain exists; an
  ALB's own DNS name can't get a meaningful ACM cert anyway, so there's
  nothing to gain by pulling this forward.

## Open questions

- If you find `module.networking`, `module.security`, or `module.database`
  don't already expose an output this dispatch needs (double-check the
  actual `outputs.tf` files rather than assuming), stop and flag it back
  rather than editing those modules yourself to add one.
- If the entrypoint script's password-encoding approach seems wrong for a
  reason not covered above (not a style preference — an actual correctness
  gap), say so back to the reviewer rather than silently changing the
  approach.
