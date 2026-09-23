# Handoff: phase4-scorer-portfolio-rollup

**Status:** DONE
**Parent plan:** `Docs/superpowers/plans/2026-08-13-phase-4-analytics-backend-part5-scorer.md`, Task 3

**Resolution (2026-08-13):** Codex implemented both files, self-proofread
(sandbox couldn't reach venv/network, same limitation as Tasks 1-2), and
deferred verification. Controller ran the real suite directly: 8/8 tests
passed on first run (2 new), full suite 338 passed/2 skipped (was 336/2,
zero regressions). Diff verified verbatim-identical to the plan's Task 3
code. Committed at `6129e96`. Task-reviewer subagent approved spec
compliance + code quality with no Critical/Important findings — two Minor
notes (unguarded `KeyError` on an orphaned scheme_id, consistent with
existing risk tolerance elsewhere in the package; mid-file import
placement, already attributed as plan-mandated, not an implementer
deviation).

## Task

Extend `backend/app/services/analytics/scorer.py` (append — do not restructure
what Task 2 already put there) and `backend/app/services/analytics/schemas.py`
(add `PortfolioScoreSummary`, `AggregatePortfolioScoreResponse`), and append
to `backend/tests/services/analytics/test_scorer.py`, exactly as specified
in Task 3 of the parent plan (full code is written out verbatim in that
task — this is a transcription-plus-verification job, not a design job).

This is PRD-04 FR-6 — the portfolio-level roll-up: `async def
compute_portfolio_score(db, household_member_ids: list[uuid.UUID]) ->
PortfolioScoreSummary` calls Task 2's `compute_fund_score` once per unique
held scheme, then AUM-weights (by each holding's own current value) into
one portfolio-level score, listing any scheme that couldn't be scored as
"uncovered" rather than silently dropping it. `async def
get_aggregate_portfolio_score(db, user_id) ->
AggregatePortfolioScoreResponse` wraps that per-user across all household
members, mirroring every other `get_aggregate_*` function already in this
package.

## Constraints

- `Decimal`, never `float`, throughout (CLAUDE.md non-negotiable) — every
  value derived from `HoldingRow.current_value` or `FundScoreRow.final_score`
  must go through `Decimal(...)` before arithmetic, never bare float ops.
- **Task 2's `scorer.py` (already committed at `aa8288f`) is the file you
  are extending — read it first** so your new code's imports and style
  match what's already there. Do not duplicate `_tier_from_percentile`,
  `_category_component_scores`, `_cost_adjustment`, or `compute_fund_score`
  — call `compute_fund_score`, don't reimplement any part of it.
- **Reuse existing functions verbatim, don't reimplement them:**
  `compute_holdings(db, household_member_ids) -> list[HoldingRow]` from
  `app.services.dashboard.holdings` (confirmed live signature: async,
  exact match to the plan); `list_household_members(db, user_id) ->
  list[HouseholdMember]` from `app.services.dashboard.household_members`;
  `get_member_statuses(db, user_id) -> list[MemberStatus]` from
  `app.services.dashboard.aggregate`. All three signatures were verified
  against the live codebase before this handoff was written — trust them.
- **A scheme with no `final_score` (category unavailable, insufficient
  history, etc.) goes into `uncovered_schemes` by name, not silently
  dropped from the portfolio value totals** — `total_value` always includes
  every holding's value; `covered_value` only includes scored ones;
  `weighted_score` is `None` only when *nothing* is covered.
- Follow the plan's task exactly: it already contains the complete
  implementation and complete test additions. Do not redesign, rename, or
  "improve" the approach — flag concerns in your report instead.

## Environment note — read before touching tests

**Do not attempt to run pytest, build a virtualenv, or install
dependencies.** This worktree has no `.venv` and no network access to your
sandbox — confirmed across Tasks 1 and 2. This is expected, not a blocker.

Implement both files exactly per the brief, append the tests exactly per
the brief, do NOT commit, and report status `DONE_WITH_CONCERNS` (not
`BLOCKED`) with verification deferred to the controller, who will run the
real suite from outside your sandbox, fix anything genuinely broken, and
commit. Proofread your own code carefully against the brief — types,
`None`-handling, the exact AUM-weighting formula — since you won't get a
red/green cycle this time.

## Approaches considered and rejected

Provisioning a venv inside this worktree was considered and rejected again
for the same reason as Tasks 1 and 2 — the controller verifying directly is
a fast, already-proven path.

## Open questions

None — this task is fully specified in the plan, and every signature it
calls has been independently verified against the live codebase (see
Constraints above). If anything in the plan's Task 3 code doesn't look
internally consistent against what's actually on disk, note it precisely
in your report; do not silently change behavior.
