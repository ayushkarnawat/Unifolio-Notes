# Handoff: aws-phase1-terraform-foundation

**Status:** DONE — reviewed 2026-09-08, PASS zero findings, see `delegation-log.md`.
**Parent plan:** `AWS Readiness/aws-golive-readiness-report.md` §9 (Terraform strategy), §11 (connectivity), §12 (private networking), §19 (resolved decisions), §22 Phase 1 (Infrastructure Foundation)

## Task

Author (do not apply) the Terraform foundation for the Unifolio staging environment on AWS: VPC, subnets, routing, the fck-nat instance, security groups, the SSM-only bastion, and the customer-managed KMS key(s) for RDS/Secrets Manager encryption. This is §22 Phase 1 from the readiness report, plus the KMS work that report folds into Phase 1 (see §11's "Encryption-at-rest keys" note, added 2026-09-08).

**This is authoring only.** Nothing in this task provisions real AWS resources. `terraform apply` and the state-bucket bootstrap script's actual AWS CLI calls are both explicitly out of scope — see Constraints.

### Directory layout to create

```
infra/
  modules/
    networking/
      main.tf        (VPC, subnets ×6, IGW, fck-nat instance, route tables, bastion EC2)
      security_groups.tf   (ALB SG, ECS task SG, RDS SG, Bastion SG, fck-nat SG)
      variables.tf
      outputs.tf      (VPC ID, subnet IDs by tier, SG IDs, fck-nat instance ID/ENI ID, bastion instance ID)
    security/
      main.tf         (customer-managed KMS key + alias)
      variables.tf
      outputs.tf      (KMS key ARN, KMS key ID)
  envs/
    staging/
      main.tf         (calls modules/networking and modules/security with staging inputs)
      providers.tf    (aws provider default = ap-south-1, aliased provider `us_east_1` for the Phase 5 CloudFront cert — unused this phase, declared now so Phase 5 doesn't need a structural change)
      variables.tf
      terraform.tfvars.example   (placeholder values, gitignored real .tfvars)
      backend.tf      (S3 + DynamoDB remote state config — see bootstrap script below for the resource names it expects)
      versions.tf     (`required_version`, pinned `hashicorp/aws` provider version)
  bootstrap/
    create-state-backend.sh   (one-off script: creates the S3 bucket + DynamoDB lock table `backend.tf` points at — see Constraints, this script must NOT be executed by you)
```

### VPC and subnets

- VPC CIDR: `10.0.0.0/16`.
- 2 AZs: `ap-south-1a`, `ap-south-1b`.
- Public subnets (ALB, fck-nat, bastion): `10.0.0.0/24` (1a), `10.0.1.0/24` (1b).
- Private app subnets (ECS tasks): `10.0.10.0/24` (1a), `10.0.11.0/24` (1b).
- Private data subnets (RDS): `10.0.20.0/24` (1a), `10.0.21.0/24` (1b).
- Internet Gateway attached to the VPC, public subnets' route table sends `0.0.0.0/0` to it.
- `map_public_ip_on_launch = true` on the public subnets only.

### fck-nat (§12 Option C — replaces a managed NAT Gateway for staging)

- One `t4g.nano` EC2 instance running the [fck-nat AMI](https://github.com/AndrewGuenther/fck-nat) (look up the current AMI ID via an `aws_ami` data source filtering on the `fck-nat` owner/name pattern the project publishes — don't hardcode a specific AMI ID that will go stale).
- Placed in the public subnet in `ap-south-1a` only — single-AZ, no failover. This is a deliberate, already-accepted staging trade-off (§12), not an oversight; add a one-line comment on the resource saying so, don't silently "fix" it into a multi-AZ HA setup.
- `source_dest_check = false` on its network interface (required for any NAT-style instance to forward traffic that isn't addressed to itself).
- Allocate and associate an Elastic IP to it, so its outbound IP is stable (useful if the AMFI/NSE/CAMS/mfapi.in integrations, or Google's OAuth cert endpoint, ever need allowlisting on the far side).
- Private app and private data subnets' route tables: `0.0.0.0/0` → the fck-nat instance's **network interface** (not the instance ID — route tables target ENIs for instance-based NAT). Actually: only the **private app** subnet's route table needs this — the private data (RDS) subnet's route table has no `0.0.0.0/0` route at all (RDS never initiates outbound traffic, confirmed in §12).
- fck-nat's own security group needs: inbound — all traffic from the VPC CIDR (`10.0.0.0/16`) on all ports (it's proxying traffic from the private subnets, so it must accept whatever they send it); outbound — all traffic to `0.0.0.0/0` (it's forwarding that traffic onward to the Internet Gateway). This is a new SG not explicitly named in the readiness report; it's a distinct concern from the ECS-task/bastion egress-all decision below — name it something like `staging-fck-nat-sg` so it isn't confused with the ECS task SG in review.

### Security groups (§11, updated 2026-09-08)

| SG | Inbound | Outbound |
|---|---|---|
| ALB SG | 443 and 80 from `0.0.0.0/0` | to ECS task SG only, port 8000 |
| ECS task SG | 8000 from ALB SG only | **all traffic, `0.0.0.0/0`** (2026-09-08 decision — see below) |
| RDS SG | 5432 from ECS task SG, 5432 from Bastion SG | none (RDS never initiates outbound) |
| Bastion SG | none (SSM-based access only, no open inbound port) | **all traffic, `0.0.0.0/0`** (2026-09-08 decision) |
| fck-nat SG | all traffic from `10.0.0.0/16` | all traffic to `0.0.0.0/0` |

**On the ECS/Bastion egress-all decision:** this report's §11 originally specified narrowly-scoped egress (443-only for ECS, 5432-only for bastion). The cloud engineer overrode this 2026-09-08 in favor of unrestricted egress on both, and the report now documents both the original design and the reasoning for the override in the same section — read it before writing these two rules, don't just take the table above at face value without the context of why it changed. Implement the **current** (egress-all) version; the ALB SG and RDS SG are unaffected and keep their original scoped rules.

### Bastion EC2

- `t4g.nano` or `t3.micro`, Amazon Linux 2023 AMI (SSM Agent is preinstalled on AL2023 — don't add a manual SSM Agent install step).
- Public subnet, `ap-south-1a`.
- IAM instance profile with the `AmazonSSMManagedInstanceCore` managed policy attached — this is what makes SSM Session Manager access work with zero open inbound ports. No SSH key pair, no port-22 rule anywhere.
- No Elastic IP needed (SSM access doesn't need a stable IP the way fck-nat's forwarding does).

### KMS (§11 "Encryption-at-rest keys", 2026-09-08)

- One `aws_kms_key` resource (`modules/security`) for staging, description something like "Unifolio staging — RDS + Secrets Manager encryption-at-rest". Both RDS and Secrets Manager can share this one key for staging; don't split into two keys, that's unnecessary ceremony at this stage.
- Key policy: grant the account root (`arn:aws:iam::<account_id>:root`) full `kms:*` — this is the standard AWS pattern that lets specific access be delegated later via ordinary IAM policies on specific roles (e.g. the ECS task execution role in Phase 3) **instead of** having to edit the KMS key policy itself every time a new principal needs access. Do not hardcode a specific IAM role ARN into the key policy for the not-yet-created ECS task role — that role doesn't exist until Phase 3, and this pattern avoids the circular dependency entirely. Leave a comment noting Phase 3 must attach a scoped IAM policy (`kms:Decrypt`, `kms:GenerateDataKey`, `kms:DescribeKey` on this key's ARN) to the ECS task execution role — don't build that IAM policy now, it belongs to Phase 3's own task-role module.
- An `aws_kms_alias` (e.g. `alias/unifolio-staging-cmk`) pointing at the key, for readability in the console.
- Output the key ARN and key ID from `modules/security` — Phase 2 (RDS) and Phase 3 (Secrets Manager) both need to consume this as a module output via `envs/staging/main.tf`.

### Tagging and naming (§9's decided convention)

Every resource: `Environment = "staging"`, `Project = "unifolio"` tags, and a `staging-` name prefix (e.g. `staging-vpc`, `staging-ecs-sg`, `staging-fck-nat`, `staging-bastion`). This is a shared AWS account distinguishing environments by naming/tagging, not separate AWS accounts (§9's explicit, already-made decision — don't second-guess it here).

### Providers, versions, remote state

- `versions.tf`: pin `required_version` for Terraform itself and `hashicorp/aws` at specific compatible versions (check what's current and stable at authoring time, don't leave it unconstrained).
- `providers.tf`: default `aws` provider, region `ap-south-1`. Also declare a second, aliased provider block (`provider "aws" { alias = "us_east_1", region = "us-east-1" }`) — this is for Phase 5's CloudFront ACM certificate (§19's ACM row: CloudFront only accepts `us-east-1`-issued certs regardless of the stack's primary region). No resource uses this alias yet in this phase; declaring it now just means Phase 5 doesn't need to restructure the provider block later.
- `backend.tf`: S3 backend config pointing at bucket `unifolio-tfstate-staging-<account_id>` (the bootstrap script below should accept the account ID as a parameter and print the exact bucket/table names it created, so this file's placeholder values can be filled in correctly — don't guess the account ID). DynamoDB lock table: `unifolio-tfstate-lock-staging`. Both names should also appear, consistently, in the bootstrap script.

### Bootstrap script (`infra/bootstrap/create-state-backend.sh`)

Write this script (S3 bucket with versioning + SSE enabled, DynamoDB table with `LockID` as the partition key, per §9's "Remote state" section) but **do not execute it**. It's for the account owner to run once, manually, after reviewing it — same reasoning as not running `terraform apply` (see Constraints).

## Constraints

- **Never run `terraform apply`, `terraform destroy`, or the bootstrap script's actual AWS CLI calls.** This mirrors the readiness report's own §20 responsibility split for Claude Code ("cannot provision AWS infrastructure, hold AWS credentials... a human with real AWS access reviews that output and executes anything that touches the account") — the same boundary applies here even though you're Codex, not Claude. If AWS credentials happen to be configured in your environment, that does not change this rule.
- You may and should run `terraform fmt` and `terraform validate` (per module and per env) to confirm syntax — these don't require real credentials or touch the account. Do not run `terraform plan` unless you've confirmed no real AWS credentials are configured (a `plan` against a fresh account with no state is low-risk, but stay on the safe side — if in doubt, skip it and let the reviewer/account owner run `plan` themselves).
- Follow `AWS Readiness/aws-golive-readiness-report.md` §9's module structure and naming (`infra/modules/...`, `infra/envs/staging/...`) — don't invent a different layout.
- Decimal/`float` rules, TDD discipline, etc. from `CLAUDE.md` don't apply here (this is infra config, not application code) — but CLAUDE.md's "explain non-obvious decisions inline as code comments where the why isn't in the docs" rule does: the single-AZ fck-nat trade-off and the egress-all override both need a one-line comment pointing at the report section, not a restatement of the reasoning.
- Add `.terraform/`, `*.tfstate`, `*.tfstate.backup`, `.terraform.tfvars` (but not `.terraform.lock.hcl` — that file should be committed) to `.gitignore`, and a real `terraform.tfvars` should never be committed (only the `.example` file).
- Do not touch `AWS Readiness/aws-golive-readiness-report.md` or any other doc in this task — this is a code-only dispatch. Report anything you find that contradicts the report back to the reviewer instead of silently editing the report yourself.
- Scope is Phase 1 only. Do not start on Phase 2 (RDS), Phase 3 (ECS/backend), or the ECS task execution role's IAM policy referenced in the KMS section above — those are separate, later dispatches.

## Approaches considered and rejected

- **Managed NAT Gateway instead of fck-nat:** rejected — §12's Option A was the original default, but §12 Option C (fck-nat) was explicitly chosen 2026-09-07 to avoid the NAT Gateway cost-approval step for a low-traffic staging environment. Don't build Option A here even though it's simpler to implement; if you think Option A is actually the better call, say so back to the reviewer rather than silently building it.
- **Terraform workspaces instead of separate `envs/staging` / `envs/production` directories:** rejected per §9 — workspaces sharing one state file are a known footgun (an accidental `apply` against the wrong workspace can touch the wrong environment). Only `envs/staging` is being built in this dispatch; `envs/production` doesn't exist yet and isn't part of this task.
- **Hardcoding the ECS task execution role ARN into the KMS key policy now:** rejected — that role doesn't exist until Phase 3. Using the root-account-plus-IAM-delegation pattern avoids a circular cross-phase dependency; see the KMS section above.
- **A single combined `modules/networking` module covering both networking and KMS:** rejected — KMS is encryption/security, not networking, and keeping it a separate `modules/security` module keeps each module's blast radius and review scope smaller and clearer.

## Open questions

- The exact current fck-nat AMI ID/lookup filter and the exact current stable `hashicorp/aws` provider version aren't known as of this handoff's writing — resolve both by looking them up directly (AMI via an `aws_ami` data source, not a hardcoded ID) rather than guessing a value that may already be stale.
- If, while writing this, you find a genuine reason the module boundaries or resource design above don't work as specified (not a style preference — an actual technical blocker), stop and flag it back to the reviewer rather than silently deviating. Don't guess your way around a real conflict with this doc.
