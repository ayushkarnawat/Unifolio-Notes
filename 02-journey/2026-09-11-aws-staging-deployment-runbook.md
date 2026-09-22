# A detailed staging deployment runbook replaces the prior plan, and Terraform state turns out to be ahead of its own documentation

## For stakeholders

With the frontend fix from the previous stage complete, a much more
detailed, copy-paste-ready runbook was written for actually pushing the
application to the staging environment — every command spelled out, every
value filled in, with a strict boundary that no infrastructure-changing
command is ever run automatically; a human runs each one. While preparing
it, a discrepancy turned up: some infrastructure the runbook believed still
needed to be applied had, in fact, already been applied in an earlier,
undocumented session — the tracking notes had fallen behind reality. This
was caught and reconciled before anything was duplicated, but it is a
reminder that this project's infrastructure state can move faster than the
notes describing it.

## Technical detail

### Intended outcome

Turn the prior stage's 9-step sequencing plan into an exact, executable
runbook, and capture the true current state of code, database schema, and
AWS infrastructure before running it.

### What actually happened

The runbook confirmed, as of this session: the investor feature batch
(Profile, account deletion, contact-change OTP, theme toggle, import
history/delete, Dashboard XIRR, allocation sort, AMC drill-down) plus that
day's PM-gap-analysis follow-ups were done and independently verified
(backend 649 passed/8 skipped, frontend 437 passed/79 files, clean
`tsc -b --noEmit`) — this work is not itself part of this batch's source
material and is noted here only as context establishing what state the
runbook was written against. A mandatory adversarial-review gate for the
two most recent fix rounds was recorded as **deferred, not skipped** —
the external review agent (Codex) was unavailable this session; both
rounds were logged for a review pass once it returned.

The RDS schema was confirmed stale: three migrations
(`0012_analytics_sections`, `0013_account_deletion_grace_period`,
`0014_analytics_recompute_generation`) had landed locally since the last
confirmed `alembic current` of `0011`, none yet applied to real RDS. The
deployed ECR image was confirmed stale against all of it.

**The Terraform-state discrepancy.** The runbook's own draft, going in,
stated Phase 4 (S3+CloudFront), Phase 5 (ACM/DNS/ALB HTTPS), and the
analytics-recompute dispatcher's ECS task definition were "authored,
reviewed, not applied." A `terraform plan` run during actual execution
showed otherwise: the dispatcher's task definition, the HTTPS listener,
both ACM certs, the CloudFront distribution, and the Route 53 records were
already present in Terraform state — refreshed, not created — traced to a
stray `tfplan-step7` file in `infra/envs/staging` dated earlier the same
day, predating this session. Only 2 new EventBridge jobs and one IAM policy
change were genuinely outstanding; these applied cleanly (3 to add, 1 to
change, 0 to destroy). The runbook's own text preserves the original,
incorrect pre-execution belief for context, with the correction stated
directly above it, rather than silently rewriting the draft.

A separate, smaller recurring issue was documented: Docker builds on WSL
intermittently fail with `failed to xattr .pytest_tmp: permission denied`,
a known WSL/drvfs permission lock that BuildKit hits before
`.dockerignore` is applied. `pytest.ini`'s `--basetemp` was moved outside
the repo this session specifically to stop it recurring.

### Deviation (if any) — decision or response taken

The runbook itself states plainly: "No command below has been executed by
Claude" — every state-mutating step is `[user-run]`. This journey stage
therefore records a **plan/runbook**, not a confirmed staging launch;
whether Steps 1-9 of the runbook (push code, apply migrations, rebuild and
push images, apply remaining Terraform, rebuild the frontend, seed the two
new scheduled jobs, run the Phase 6 smoke test, stand up CI/CD) were
actually carried out is not evidenced anywhere in this batch's source
material.

### Result

A precise, executable runbook exists; the Terraform-state gap between
documentation and reality was found and reconciled once. Whether the
runbook was actually run to completion is unverified from this batch's
source material — see [R-052](../07-risks-and-debt.md).

### Related

- ADR-006 — background job scheduling (the EventBridge/ECS pattern this runbook operates)
- ADR-015 — analytics precompute architecture (the dispatcher this runbook wires up)
- R-052 — Terraform state can silently drift ahead of session notes
- Evidence: `08-evidence/documents/plans/2026-09-11-aws-staging-prerequisites.md`
