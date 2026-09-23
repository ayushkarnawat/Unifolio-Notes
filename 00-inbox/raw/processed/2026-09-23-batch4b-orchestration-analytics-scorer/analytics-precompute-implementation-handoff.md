# Handoff: analytics-precompute-implementation

**Status:** All 9 tasks done (commits `47b0bb9`, `9ca4933`, `729ea8e`,
`d2c1be8`, `225e4e6`, `e92e827`, `95c2d93`, `0d0d4b7`, `9bf5603` on
`worktree-analytics-precompute-architecture`). Codex ran Tasks 1-2 and Task 4
cleanly, then correctly stopped mid-Task-3, mid-Task-5, and mid-Task-6 on
genuine internal inconsistencies in the plan's literal code rather than
guessing (see "Task 3 findings" / "Task 4 & 5 findings" / "Task 6 findings"
below); stopped again mid-Task-7 on a genuine schema mismatch (see "Task 7-9
findings" below). Claude fixed all four rounds directly and implemented
Tasks 7-9 directly (given the established recurring-bug pattern and to avoid
another dispatch round-trip for the remaining, now-well-understood work),
full suite green throughout. Mandatory adversarial-review gate: round 1
returned **needs-fixes** (6 findings), fixed `3ca83ae`; the fix's own scoped
re-review (round 2) returned **needs-fixes** again with a Critical
regression the round-1 fix introduced, fixed `3f2bdd0`; round 2's own fix
scoped re-review (round 3) returned **needs-fixes** with 2 High findings in
`EcsRunTaskDispatcher.dispatch()`'s error handling, fixed `88a1baa`; round
3's own fix scoped re-review (round 4) returned **PASS, zero findings** (see
"Review gate round 1 & round 2 findings" below, which also covers rounds 3
and 4). Full backend suite independently re-confirmed clean at the close of
round 4: 597 passed, 6 skipped, 0 failures. **DONE.** (2026-09-03)

**IMPORTANT — migration renumber:** this worktree's `0010_analytics_sections.py`
migration was renumbered to `0012_analytics_sections.py` (`down_revision`
`0011`) during a 2026-09-03 merge of `feat/enhanced-ui` into this branch — a
parallel session's enum-drift migration had already landed as revision `0010`
on `feat/enhanced-ui`, with a household-members migration chained on top of
it as `0011`. If Task 9's grep-for-dangling-references step touches migration
numbers, `0012` is the current one for `analytics_sections`/
`analytics_recompute_status`, not `0010` as the plan's literal text says.
**Parent plan:** `Docs/superpowers/plans/2026-09-02-analytics-precompute-architecture.md`
(9 tasks, fully detailed, no placeholders — this handoff doc does not restate that
plan's content, only the "why" and constraints a plain prompt summary would lose)
**Parent spec:** `Docs/superpowers/specs/2026-09-02-analytics-precompute-architecture-design.md`
**Dispatch mode:** User is running this directly in their own Codex CLI/app session
(not via Claude's `codex:codex-rescue` Agent dispatch), specifically to conserve Claude
token spend for this session. This doc is still the source of truth both sides read;
update `Status` here after Codex finishes and report back to Claude for the mandatory
review gate.
**Worktree:** `.claude/worktrees/analytics-precompute-architecture` (branch
`worktree-analytics-precompute-architecture`, forked off `feat/enhanced-ui` at `39a97ca`)
— created so this work stays isolated from any other in-flight session on
`feat/enhanced-ui`.

## Task

Execute all 9 tasks of the implementation plan in order, task by task, TDD-style
exactly as each task's steps specify (failing test → run to confirm fail → minimal
implementation → run to confirm pass → commit). The plan already contains complete,
non-placeholder code for every step — this is execution, not design or research.

## Constraints

- **TDD, no exceptions** — every task's steps already dictate the red/green/commit
  cycle; follow it as written, don't batch multiple tasks' code together before
  running tests.
- **`Decimal`, never `float`**, for every money/units/NAV/percentage value (repo-wide
  rule, CLAUDE.md/AGENTS.md) — none of this plan's 9 tasks should introduce a new
  `float` on a money path; if one seems necessary, stop and flag it rather than adding it.
- **AWS ARNs/networking are explicitly out of scope.** Task 4's `config.py` settings
  (`ecs_cluster_arn`, `ecs_task_definition_arn`, etc.) must stay empty-string defaults.
  Do not invent, guess, or fill in any concrete AWS resource identifier — a separate,
  parallel session is finalizing the real ECS/EventBridge wiring, and reconciling the
  exact `RunTask` invocation contract against that session's decisions happens later,
  outside this task.
- **Don't touch `session.md`/`CLAUDE.md`'s "still open" item 7** (blocking
  `db.commit()` inside `async def`) even though the plan's Global Constraints section
  discusses it — that's a separate docs-only correction, not part of this plan's code.
- **Don't touch the frontend.** `frontend/src/features/analytics/api.ts` and its
  callers will break once Task 9 removes the 14 old routes — that's expected and
  flagged as an explicit, separate follow-up in the plan's closing section, not
  something to fix here.
- Full backend test suite must pass (`cd backend && .venv/bin/pytest -q`) before any
  task's step says "run to verify it passes" reports success, and again as the final
  check after Task 9. Two Postgres-marked functional tests may skip/fail in this
  worktree if no local Docker Postgres is reachable — that's expected and unrelated to
  this plan's changes; don't attempt to fix or work around it.
- This worktree has no Python virtualenv yet (worktrees don't inherit gitignored
  `.venv` from the main checkout) — set one up first: `cd backend && python3 -m venv
  .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt` (Task 4
  adds `boto3>=1.35.0` to `requirements.txt` partway through — re-run `pip install -r
  requirements.txt` after that edit, before Task 4's tests).
- Commit after every task (each task's own Step "Commit" already specifies the exact
  `git add`/`git commit` invocation and message) — don't squash multiple tasks into one
  commit, don't skip a task's commit step.

## Approaches considered and rejected

- **Dispatching this via Claude's own `codex:codex-rescue` Agent tool, task-by-task
  with a review gate between each** — the model-orchestration skill's normal default.
  Rejected for this run specifically at the user's request: that flow burns Claude
  tokens on every dispatch/monitor/review round-trip across 9 tasks. Running the whole
  plan in one user-driven Codex CLI/app session, then a single consolidated review once
  it's back, keeps Claude's token spend to the review pass only.
- **9 separate handoff docs, one per task** — the implementation plan document already
  contains everything each task needs (files, exact code, step-by-step TDD sequence);
  a second per-task doc would just paraphrase it. One handoff doc covering the whole
  plan, carrying only the constraints/context the plan itself doesn't restate, is
  sufficient here.

## Open questions

- If any task's plan code references a function/schema field/signature that no longer
  matches what's actually in the worktree's checked-out code (e.g. something changed
  between when the plan was written and when Codex runs it), stop and report the
  mismatch rather than guessing a fix — the plan was grounded against the codebase at
  commit `39a97ca`; if drift is found, note the specific task/file/line.
- If a task's test setup needs a fixture/helper pattern not fully spelled out in the
  plan (the plan references some existing test file conventions by name, e.g.
  `tests/models/test_auth_identity_models.py`'s `_session()` pattern for Task 1) and
  something is genuinely ambiguous, follow the referenced file's actual current
  convention over the plan's paraphrase of it.

## Task 3 findings (resolved by Claude, 2026-09-02, commit `729ea8e`)

Codex's stop-and-report was correct — both were genuine bugs in the plan's
literal code, not something to guess around:

1. `_SectionSpec` was declared `@dataclass(frozen=True)`, but the plan's own
   tests patch `.compute` per-instance via `unittest.mock.patch.object`,
   which requires attribute mutation. Fix: dropped `frozen=True`.
2. `should_dispatch_recompute` subtracted a DB-round-tripped `started_at`
   from an aware `datetime.now(timezone.utc)`. SQLite's `DateTime(timezone=True)`
   doesn't preserve tzinfo on read (Postgres does) — a `started_at` written
   aware comes back naive on SQLite. Fix: normalize a naive read to UTC
   before subtracting.

Also corrected the new `test_recompute_does_not_refetch_nav_over_network_for_a_category_shared_across_scopes`
test: it asserted on `_fetch_nav_history`'s call count (2, not 1), but
`compute_holdings` (called at the top of `compute_category_ranking`,
unmodified by this plan) does its own separate, pre-existing per-scheme
valuation lookup via `get_nav_on_or_before`, which also touches
`_fetch_nav_history` once — independent of this module's category-returns
caching. Rewrote to spy on `warm_nav_history` directly (call count == 1),
which is the exact function the spec's "called once, not once per scope"
claim is about.

## Task 4 & 5 findings (resolved by Claude, 2026-09-03)

Task 4 (`d2c1be8`) completed cleanly by Codex, no findings.

Task 5 (`225e4e6`) — Codex's stop-and-report was correct, a genuine bug:
`test_run_one_calls_recompute_with_the_given_user_id` used `fake_db = object()`,
but `_run_one`'s own `finally` block calls `db.close()`, which a bare
`object()` has no attribute for. Fix: `fake_db = MagicMock()`, matching the
sibling test's own hand-rolled fake-db-with-`close()` convention already
present in the same file.

Separately (not something Codex hit, since it happened between Codex's Task-4
and Task-5 runs): this worktree branch needed a merge from `feat/enhanced-ui`
to pick up this doc's own Task-3-findings update, which caused the
`requirements.txt` pinning conflict and the migration renumber noted above.
Both resolved before Task 5 ran; not a plan-code issue.

## Task 6 findings (resolved by Claude, 2026-09-03)

Codex's stop-and-report was correct, a genuine sequencing bug in the plan's
own Step ordering: Task 6 Step 1's test patches
`app.api.imports.should_dispatch_recompute` (`return_value=True`/`False`),
but by default `unittest.mock.patch("module.attr")` does a `getattr` on the
target module to save the original value, which raises `AttributeError` if
the attribute doesn't exist yet — and it didn't, since Step 3 (which adds
the `from app.services.analytics.recompute import should_dispatch_recompute`
import) hadn't run yet. The plan's own Step 2 expects the red test to fail
via `assert 1 == 2` (only the prefetch task scheduled), but it actually
errored via `AttributeError` before ever reaching that assertion — same
"literal test/step ordering assumes something not yet true" class of bug as
Tasks 3 and 5.

Fix: split Step 3's two import lines out and add them to `imports.py` ahead
of the red-test run (no behavior change — `should_dispatch_recompute` and
`dispatcher` become resolvable names but nothing calls them yet), confirmed
this reaches the plan's own literal expected red failure
(`assert 1 == 2`), then wired the actual `if should_dispatch_recompute(db,
user.id): background_tasks.add_task(dispatcher.dispatch, user.id)` call as
Step 3 originally specified. No test-file changes were needed — only the
import ordering in production code moved earlier. Full suite green (603
passed, 6 skipped, 1 pre-existing flake in
`test_upsert_nav_history_is_conflict_safe_across_sessions` confirmed to pass
in isolation — an unrelated cross-test flake, not caused by this change).
Committed `e92e827`.

## Task 7-9 findings (resolved/implemented by Claude, 2026-09-03)

Codex's stop-and-report on Task 7 was correct, a genuine bug in the plan's
own `_seed_section` snippet: it assigned `household_member_id=user_id`,
but the authenticated user's id and the household-member id are distinct
values — `analytics.py:30`'s `household_member_id` is a foreign key to
`household_members.id`, not `users.id`. Fixed by using `scope_key`
(the member id already passed into the helper) instead of `user_id`.

A second bug surfaced during Claude's own red-run, which Codex hadn't
reached yet: `AnalyticsSection.user_id`/`household_member_id` are
`uuid.UUID`-typed SQLAlchemy columns, but the OTP-verify response's
`user_id` and the household-member route's `id` are both plain JSON
strings — constructing the ORM object directly with string values raised
`StatementError: 'str' object has no attribute 'hex'`. Fixed by wrapping
both values in `uuid.UUID(...)` inside `_seed_section`.

The plan's own flagged open question — "check `app/api/auth.py`'s verify
response shape... since it wasn't directly confirmed in this plan's
research" — is resolved: `OtpVerifyResponse.user_id: str` (in
`app/services/auth/schemas.py`) is already returned directly by
`/auth/otp/verify`, no extra `/me`-style call needed.

Given this was now the fourth round of the same "plan's literal
test/step code assumes something not yet true" bug class (Tasks 3, 5, 6,
7), and Tasks 8-9's remaining work was small, mechanical, and already
fully specified in the plan's own literal code, Claude implemented Tasks
7 (route replacement), 8 (`POST /analytics/{scope}/retry`), and 9 (test
deletion + dangling-reference grep) directly rather than a further Codex
dispatch round-trip — per `model-orchestration`'s "Review-loop fix
authorship" allowance (small diffs, files already in context, faster
than another handoff/dispatch/wait cycle).

One own-test bug found while implementing Task 7: the test file (written
by Claude, since Codex stopped before writing it) patched
`app.api.analytics.compute_category_allocation` to assert live compute
never runs — but the consolidated route's whole design point is that it
*never* imports or calls any compute function, so that name no longer
exists on the module. Fixed by asserting `dispatcher.dispatch` isn't
called instead, which is the actually-correct signal for "no live
compute/no dispatch happened."

Task 9's Step 3 grep (for dangling references to the 14 removed routes)
returned matches in `app/api/dashboard.py` and its tests — confirmed
these are a **different, unprefixed router** (`/household-members/...`,
`/household/aggregate/...` with no `/analytics` prefix) that happens to
share the same relative path suffixes as the removed analytics routes.
Pre-existing, unrelated functionality; not a dangling reference to
anything this plan touched. The plan's own "Expected: no output" was
imprecise on this point — flagging it here rather than silently treating
the extra grep output as a false alarm without a reason.

Full suite green after Task 9: 583 passed, 6 skipped, 0 failures (net
count reflects the 14 old-route tests + 1 old scorer test removed against
the 10 new scope/retry tests added in Tasks 7-8).

Committed: `95c2d93` (Task 7), `0d0d4b7` (Task 8), `9bf5603` (Task 9).

## Review gate round 1 & round 2 findings (2026-09-03)

**Round 1 verdict: needs-fixes, 6 findings (3 High, 3 Medium)** — the first
round in this whole plan where findings were genuine design/logic gaps, not
a plan-sequencing artifact. Root cause of the 3 High findings:
`should_dispatch_recompute()` is read-only, so nothing atomically claimed
`AnalyticsRecomputeStatus` at any of the 3 dispatch decision points (GET,
retry, CAS-import), letting concurrent callers double-dispatch; GET's
`recomputing` flag checked `started_at is not None` rather than staleness,
permanently blocking its own recovery once stale; the daily `--all` backstop
had zero in-flight guard, able to race an event-triggered recompute. The 3
Medium findings: ECS `RunTask` placement failures silently logged as
success; a non-canonical UUID scope (uppercase/hyphenless) passed auth but
missed its stored row (queried on the raw string, not `str(member_uuid)`);
no test coverage for any of the above. All 6 independently re-verified by
direct code read before fixing.

**Round-1 fix (commit `3ca83ae`):** added `try_claim_recompute()` to
`recompute.py` — one atomic dialect-branching
`INSERT ... ON CONFLICT DO UPDATE ... WHERE started_at IS NULL OR started_at
< cutoff`, same pattern as `_upsert_section` — swapped in at all 4 dispatch
decision call sites (GET, retry, CAS-import, and `_run_one()`). Canonicalized
`scope`, added `RunTask` failure-response handling, added tests. Full suite:
589 passed, 6 skipped.

**Round 2 (scoped re-review of the round-1 fix) verdict: needs-fixes, 3
findings (1 Critical, 1 High, 1 Medium).** **Critical:** the round-1 fix put
`try_claim_recompute()` at both the 3 API dispatch sites (which commit the
claim before calling `dispatcher.dispatch()`) and inside `_run_one()` — the
same function the resulting ECS task calls when it starts — so the worker's
own claim attempt always found the slot already freshly held by its own
caller and returned `False`, silently skipping `recompute_household_analytics()`
for every event-triggered recompute. The two claim sites were meant to be
one continuous operation split across two processes, not two independent
claimants. **High:** the API-layer claim committed before
`dispatcher.dispatch()` ran, but `dispatch()`'s success/failure was never
surfaced back, so a failed/unconfigured dispatch orphaned the claim for up
to the 2-hour staleness ceiling. **Medium:** round-1's new tests mocked
`try_claim_recompute`'s return value rather than seeding a real claim and
exercising the actual cross-process handoff, which is why they didn't catch
the Critical regression.

**Round-2 fix (commit `3f2bdd0`):** `_run_one()` no longer claims at all —
it trusts its caller (an API dispatch site, for `--household` mode) already
claimed the slot, and runs `recompute_household_analytics()` directly.
`_run_all()`'s own per-user loop claims instead, since that's the only path
(the daily backstop) with nothing claimed on its behalf. `dispatch()` now
returns `bool` (True only if RunTask actually placed the task); a new
`release_recompute_claim()` is called by all 3 dispatch sites when dispatch
returns `False` (`imports.py`'s CAS-confirm site via a new
`_dispatch_recompute_and_release_claim_on_failure` background-task wrapper,
since dispatch there runs via `background_tasks.add_task`). Tests rewritten
to seed a real claim via `try_claim_recompute` against a real session and
assert on actual worker/backstop behavior, instead of mocking the claim
function's return value. Full suite: 595 passed (+6 net), 6 skipped, 0
failures. `git diff --stat` confirmed narrow (same 10 files as round 1).
Round 3 (scoped re-review of this fix) dispatched next.

**Round 3 (scoped re-review of the round-2 fix) verdict: needs-fixes, 2
findings (both High), both confined to `EcsRunTaskDispatcher.dispatch()` in
`dispatch.py`.** Round 3 first confirmed all 3 round-2 findings genuinely
closed (with file:line citations for each) before reporting new findings.
**Finding 1:** `boto3.client()`/`client.run_task()` exceptions (network/API
errors) were never caught, so a transport failure would propagate straight
past every caller's `release_recompute_claim()` check — reproducing the
exact orphaned-claim-for-up-to-2-hours failure mode round 2's bool-return
fix was meant to close, just via an uncaught exception instead of a `False`
return. **Finding 2:** a `{"tasks": [], "failures": []}` `RunTask` response
returned `True` on "no reported failures" alone, without confirming a task
was actually placed — the existing "configured, success" test explicitly
codified this gap (it asserted success from `{"failures": []}` with no
`tasks` key at all). Both independently re-verified against `dispatch.py`
before fixing.

**Round-3 fix (commit `88a1baa`):** wrapped the `boto3.client()`/`run_task()`
call in `try/except (BotoCoreError, ClientError)`, returning `False` (logged
via `logger.exception`) on any transport/API failure. Added a
`response.get("tasks")` truthiness check after the existing `failures`
check, returning `False` (logged via `logger.error`) when no task was
actually reported placed. Fixed the existing success test to include a
non-empty `tasks` list (previously the gap-codifying shape); added
`test_dispatch_returns_false_when_run_task_raises` and
`test_dispatch_returns_false_when_run_task_reports_no_tasks_and_no_failures`.
Touched-area suite (5 files): 52/52 passed. Full suite (run since this round
was expected to potentially close the gate): 597 passed, 6 skipped, 0
failures. `git diff --stat` confirmed narrow (2 files: `dispatch.py` + its
test file only) — dispatched a further scoped re-review (round 4) per the
skill's stopping heuristic, since round 3's findings were High severity, not
a lower-severity trend from round 2's Critical/High/Medium.

**Round 4 (scoped re-review of the round-3 fix) verdict: PASS, zero
findings.** Codex confirmed all 6 verification points against `git diff
3f2bdd0..88a1baa` (both `dispatch.py` and its test file), independently
checked the installed botocore exception hierarchy (`NoCredentialsError` ->
`BotoCoreError`; `EndpointConnectionError` -> `ConnectionError` ->
`BotoCoreError`; `ClientError` handled explicitly) to confirm the `except`
clause is actually broad enough rather than accepting the fix's own
docstring claim, and ran the 5 targeted tests (all passed) in its own
environment. Orchestrator independently re-ran the full backend suite as
the closing-round check: 597 passed, 6 skipped, 0 failures. Review gate
closed — 4 rounds total (needs-fixes x3, PASS x1), all findings genuine
(no plan-sequencing artifacts among them, unlike the implementation-phase
task rounds above).

**Environment note:** the `codex:codex-rescue` Agent dispatch is
forwarder-only for implementation/most review dispatches — it returns a job
ID immediately and Claude cannot poll it; `/codex:status`/`/codex:result`
are `disable-model-invocation: true`, human-only. Round 1 needed a manual
relay. Rounds 2-4's own `task-notification`s all carried the full result
inline instead, with no manual relay needed — confirmed 3 times now, so
this appears to be the actual default behavior for this dispatch chain;
round 1's forwarder-only behavior may have been the anomaly instead. Not
fully reconciled, but worth treating the inline-result behavior as the
default going forward on similar chains.

## Verification required before reporting done

- All 9 tasks' own step-level test runs pass as each task specifies.
- Full backend suite green at the end (`pytest -q`), excluding the two
  Postgres-marked tests if Docker Postgres isn't available in this environment.
- `git log --oneline` on the worktree branch shows one commit per task (9 commits,
  possibly more if a task's steps commit more than once — check each task's plan text).
- Report back: which tasks completed cleanly, any deviations from the plan's literal
  code (and why), any open question above that got triggered, and the final test
  suite result.
