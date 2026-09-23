You are implementing a batch of 10 features in the Unifolio codebase (MF portfolio
tracker). Full scope, acceptance criteria, constraints, and rejected alternatives are
written out in full at:

`Docs/orchestration/investor-beta-feature-batch-handoff.md`

Read that file in full before starting — it is the single source of truth, not a
summary you should paraphrase from memory as you go.

Work top-to-bottom through its 10 numbered items. TDD throughout (red → make it fail,
green → minimal code to pass, refactor) — this repo's `AGENTS.md` treats this as
non-negotiable, not a suggestion. `Decimal`, never `float`, for any money/units/NAV
value you touch or add.

Reuse existing patterns exactly where the handoff doc points at one already in this
codebase — existing `Modal` component, existing OTP service functions, existing
EventBridge-Scheduler-plus-ECS-RunTask job pattern, existing plain-state tab-switching
(no router). Do not introduce a second version of any of these.

Hard boundaries, per this project's division of labor — do NOT run any of the
following yourself, no matter how tempting mid-task:
- `terraform apply` (author the Terraform for the new daily job, don't apply it)
- `alembic upgrade head` against any real/deployed database (author migrations only)
- `docker build`/`push`, `aws ecs update-service`, or any other AWS-state-mutating
  command

When you're done with all 10 items:
1. Run the full backend test suite (`pytest -m "not postgres and not playwright"`) and
   the full frontend suite (`npm test` + `npx tsc -b --noEmit`) yourself and report the
   real pass/fail counts — not a guess, not "should pass."
2. Report back per-item: what you built, which files changed, and flag explicitly any
   of the handoff doc's "Open questions" you made a judgment call on and what you chose.
3. Do not mark anything as reviewed or done beyond your own implementation — a separate
   adversarial review pass happens after this, outside your scope.

If anything in the handoff doc is ambiguous or you think an approach it names as
"rejected" is actually right, stop and say so rather than silently picking a different
approach — flag it back the same way the doc's "Open questions" section describes.
