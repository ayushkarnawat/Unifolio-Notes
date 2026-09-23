# Handoff: phase4-scorer-risk-metrics

**Status:** DONE
**Parent plan:** `Docs/superpowers/plans/2026-08-13-phase-4-analytics-backend-part5-scorer.md`, Task 1

**Resolution (2026-08-13):** Codex implemented both files correctly but its
sandbox couldn't reach this repo's `.venv` (outside its worktree) or the
network, so it stopped BLOCKED before running tests. The orchestrator
verified directly (absolute venv path), found and fixed one genuine bug in
the plan's own test fixture (`category_medians` even-length case asserted
the arithmetically wrong median), reran green (16/16, full suite 330
passed/2 skipped, zero regressions vs. 314/2 baseline), and committed at
`7058b0e`. Task-reviewer subagent (haiku) independently confirmed the median
fix and approved spec compliance + code quality with no findings.

## Task

Implement `backend/app/services/analytics/risk_metrics.py` and its test file
`backend/tests/services/analytics/test_risk_metrics.py` exactly as specified in
Task 1 of the parent plan (full code for both files is written out verbatim in
that task — this is a transcription-plus-verification job, not a design job).

Seven pure/DB-read-only functions: `month_end_dates`, `build_monthly_series`,
`monthly_returns`, `compute_downside_deviation`, `rolling_12m_returns`,
`category_medians`, `compute_consistency_hit_rate`. These are the building
blocks PRD-04's Scorer (FR-5) uses for its Risk and Consistency components —
downstream tasks in this same plan will import and orchestrate them, so the
exact function names, signatures, and `None`-handling semantics in the plan
must be followed precisely, not paraphrased.

## Constraints

- `Decimal`, never `float`, throughout (CLAUDE.md non-negotiable — every
  function in this file operates on `Decimal` NAVs/returns).
- Every list output must stay **position-aligned** to its `month_ends` input —
  use `None` placeholders for missing data, never compact/drop entries. This
  is called out explicitly in the plan's Global Constraints and is the one
  non-obvious invariant in this task: a later task's cross-scheme median
  comparison depends on index `i` meaning the same calendar month for every
  scheme.
- `build_monthly_series` reads the `NavHistory` cache table only — no network
  call, no call to any NAV-fetching client function.
- Follow the plan's task exactly: it already contains the complete
  implementation and complete test file. Do not redesign, rename, or
  "improve" the approach — flag concerns in your report instead.

## Approaches considered and rejected

An earlier draft of this design dropped leading `None`s (compacting the
series) before position-alignment was recognized as required — rejected
during design because it would have broken the cross-scheme Consistency
comparison a later task depends on. This is why the position-alignment
requirement above is called out explicitly rather than left implicit.

## Open questions

None — this task is fully specified in the plan. If anything in the plan's
Task 1 code doesn't run as written (e.g. a genuine typo), fix it and note the
fix in your report; do not silently change behavior.
