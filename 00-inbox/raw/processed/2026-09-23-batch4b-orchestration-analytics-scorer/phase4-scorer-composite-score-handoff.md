# Handoff: phase4-scorer-composite-score

**Status:** DONE
**Parent plan:** `Docs/superpowers/plans/2026-08-13-phase-4-analytics-backend-part5-scorer.md`, Task 2

**Resolution (2026-08-13):** Codex implemented both files, self-proofread
(sandbox couldn't reach the venv/network, same limitation as Task 1), and
deferred verification. Controller ran the real suite directly: 6/6 new
tests passed on the first run, no fixes needed; full suite 336 passed/2
skipped (was 330/2, zero regressions). Committed at `aa8288f`.
Task-reviewer subagent (haiku) approved spec compliance + code quality.
One Important-but-inherited finding parked, not fixed here: `date.replace
(year=year - N)` raises `ValueError` on Feb 29 in a non-leap target year —
pre-existing in `risk_metrics.py` and already-shipped `category_ranking.py`,
not introduced by this task. Recorded in the SDD ledger for the final
whole-branch review to weigh.

## Task

Implement `backend/app/services/analytics/scorer.py`, add `FundScoreRow` to
`backend/app/services/analytics/schemas.py`, and write
`backend/tests/services/analytics/test_scorer.py` exactly as specified in
Task 2 of the parent plan (full code for all three is written out verbatim
in that task — this is a transcription-plus-verification job, not a design
job).

This is the composite fund score itself (PRD-04 FR-5, FR-7): `async def
compute_fund_score(db: Session, scheme: Scheme) -> FundScoreRow`, which
blends Return (45%, reusing `category_ranking.py`'s peer-percentile),
Risk (30%, from Task 1's `compute_downside_deviation`, inverted), and
Consistency (25%, from Task 1's `compute_consistency_hit_rate`) into one
composite, re-percentiles it within category, maps to a 1-5 tier, applies
the ±0.25 TER cost-overlay nudge, and upserts one `fund_scores` row per day
(check-before-insert — never persist the FR-7 breakdown itself, only
`risk_adjusted_tier`/`cost_adjustment`/`final_score`, per the plan's design
note on why that's schema-respecting, not an oversight).

## Constraints

- `Decimal`, never `float`, throughout (CLAUDE.md non-negotiable).
- **No schema changes** — `fund_scores` is exact and final; the FR-7
  breakdown (return/risk/consistency percentiles) is recomputed fresh on
  every call, never persisted.
- **Reuse existing private helpers, don't reimplement them.** Import
  `_category_returns`, `_rank_and_percentile`, `_aum_weighted_average`,
  `_latest_aaum_by_scheme`, `_THIN_CATEGORY_THRESHOLD` from
  `category_ranking.py`; `_ensure_ter_fresh`, `_latest_ter_for_scheme` from
  `ter.py`; `get_category_universe` from `scheme_universe.py`; all seven
  functions from Task 1's `risk_metrics.py` (already committed at `7058b0e`
  — read that file directly for exact signatures, don't guess).
- **Formula weights (fixed, do not change):** Return 45%, Risk 30%,
  Consistency 25%. Cost overlay: ±0.25 nudge, 0.05 percentage-point dead
  zone around the category-average TER.
- **Tier boundaries inclusive on the lower bound**
  (`percentile >= 80` → tier 5, `>= 60` → tier 4, `>= 40` → tier 3,
  `>= 20` → tier 2, else tier 1) — not a strict `>`.
- **History window:** month-end anchors span `today - 5 years` to `today`
  regardless of how much history a scheme actually has (this is what Task
  1's `month_end_dates` already does — call it, don't reimplement it).
- Follow the plan's task exactly: it already contains the complete
  implementation and complete test file. Do not redesign, rename, or
  "improve" the approach — flag concerns in your report instead.

## Environment note — read before touching tests

**Do not attempt to run pytest, build a virtualenv, or install
dependencies.** This worktree has no `.venv` (it's gitignored and only
exists in the main checkout, outside this worktree's directory tree — your
sandbox cannot reach it by any path, absolute or relative, and has no
network access to build its own). This was discovered and confirmed during
Task 1's dispatch. **This is expected, not a blocker to report as BLOCKED.**

Instead: implement both files exactly per the brief, write the test file
exactly per the brief, do NOT commit, and report status `DONE_WITH_CONCERNS`
(not `BLOCKED`) with a note that verification is deferred to the
controller, who will run the real test suite from outside your sandbox
using the project's actual virtualenv, fix anything genuinely broken, and
commit. Your job is a careful, self-reviewed transcription — proofread
your own code against the brief line by line (types, `None`-handling,
exact percentile/tier formulas) since you cannot rely on a red/green cycle
to catch mistakes this time.

## Approaches considered and rejected

Provisioning a venv inside this worktree (copying or symlinking the main
checkout's `.venv`) was considered and rejected for this task — same
reasoning as Task 1: added complexity for a one-off, and the controller
verifying directly is a fast, already-proven path (see Task 1's
resolution in `Docs/orchestration/phase4-scorer-risk-metrics-handoff.md`).

## Open questions

None — this task is fully specified in the plan. If anything in the plan's
Task 2 code doesn't look internally consistent (e.g. a genuine typo, a
signature mismatch against Task 1's actual committed `risk_metrics.py`),
note it precisely in your report; do not silently change behavior.
