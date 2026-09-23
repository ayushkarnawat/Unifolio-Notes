# Implementation session prompt — AWS Phase 1 Terraform foundation

Paste everything below this line into your Codex session (`codex` CLI or the
Codex app) to start this task. This is a user-run dispatch — not run through
Claude Code's own Agent tool — per this project's established pattern (see
`Docs/orchestration/delegation-log.md`'s `worker=codex (user-run, direct
CLI/app — not Agent-dispatched)` entries). Do not self-review when done —
report back what you did and stop; a separate adversarial review pass runs
afterward, driven by the user relaying your output back into the main Claude
Code session.

---

<task>
Repo: Unifolio (mutual fund portfolio tracking platform, MF-only MVP),
branch `feat/enhanced-ui`. Author the Terraform foundation for the staging
AWS environment: VPC, subnets, fck-nat networking, security groups, an
SSM-only bastion, and a customer-managed KMS key for RDS/Secrets Manager
encryption.

Full spec, exact CIDR ranges, module layout, and every resource-level
decision already made: `Docs/orchestration/aws-phase1-terraform-foundation-handoff.md`.
Read it in full before writing any code — this prompt does not restate its
contents, it points at the single source of truth both sides re-read.

Also read `AWS Readiness/aws-golive-readiness-report.md` §9, §11, §12, §19,
and §22 Phase 1 for the reasoning behind the decisions the handoff doc
encodes — in particular §11's "Encryption-at-rest keys" and "Egress
decision" notes (both dated 2026-09-08), since the handoff doc references
them rather than repeating the full reasoning inline.
</task>

<action_safety>
This is authoring only — you are not provisioning real AWS infrastructure.
Never run `terraform apply`, `terraform destroy`, or execute the bootstrap
script's actual AWS CLI calls (`create-state-backend.sh` gets written, not
run). This holds even if AWS credentials happen to be configured in your
environment. You may run `terraform fmt` and `terraform validate` freely —
neither needs real credentials or touches the account. Skip `terraform plan`
unless you've explicitly confirmed no real AWS credentials are present in
this session.

Keep changes scoped to the `infra/` directory and `.gitignore` per the
handoff doc's directory layout. Do not touch
`AWS Readiness/aws-golive-readiness-report.md` or any other doc — if you find
something in the report that seems wrong or out of date, report it back
instead of editing it yourself. Do not start Phase 2 (RDS), Phase 3
(ECS/backend), or the ECS task execution role's IAM policy — those are
separate, later dispatches, explicitly out of scope here even if related
work would be convenient to do now.
</action_safety>

<default_follow_through_policy>
Default to the most reasonable low-risk interpretation and keep going —
e.g. look up the current fck-nat AMI and current stable `hashicorp/aws`
provider version yourself rather than asking. Only stop and ask if you hit
an actual technical conflict with the handoff doc's design (not a style
preference), per its own "Open questions" section.
</default_follow_through_policy>

<completeness_contract>
Resolve the full Phase 1 scope from the handoff doc before stopping — all of:
VPC + 6 subnets across 2 AZs, IGW, fck-nat instance + its own security group
+ EIP + route tables, the 4 other security groups (ALB/ECS/RDS/Bastion) with
the 2026-09-08 egress-all update on ECS/Bastion specifically, the SSM-only
bastion EC2 instance + instance profile, the customer-managed KMS key +
alias in its own `modules/security`, the `envs/staging` root module wiring
everything together including the aliased `us-east-1` provider block for
Phase 5's future CloudFront cert, `versions.tf`, `backend.tf` (pointing at
the not-yet-created state bucket/table names), the bootstrap script
(written, not run), and `.gitignore` updates. Don't stop after just the
networking module and call it done.
</completeness_contract>

<verification_loop>
Run `terraform fmt -recursive` and `terraform validate` against every module
and against `envs/staging` before finalizing. If validate fails, fix and
re-check — don't report syntax errors as "done, just needs review." Note in
your final report which checks you ran and their results.
</verification_loop>

<compact_output_contract>
When done, report back compactly: what you built (directory tree is enough,
don't paste every file), which of the two decisions you had to make
independently (AMI lookup, provider version) and what you chose, the exact
`terraform fmt`/`validate` results, and anything from the handoff doc's
"Open questions" section you had to resolve yourself vs. anything you're
flagging back unresolved. Do not run or offer to run a self-review — that
step happens separately, on the Claude Code side, after this report is
relayed back.
</compact_output_contract>
