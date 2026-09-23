# Handoff: phase4-scorer-api-routes

**Status:** DONE
**Parent plan:** `Docs/superpowers/plans/2026-08-13-phase-4-analytics-backend-part5-scorer.md`, Task 4

**Resolution (2026-08-13):** Codex implemented both files and self-proofread
(sandbox couldn't reach venv/network, same limitation as Tasks 1-3). The
dispatching Agent call itself hit a session-limit API error, but the
underlying Codex job had already completed in the background — found
directly via `codex-companion.mjs status --all` rather than re-dispatching.
Controller found and fixed one genuine bug in the plan's own test code
(`test_get_fund_score_404_when_scheme_not_found` never overrode `get_db`,
so it hit the app's real un-migrated DB instead of the fake one — fixed to
match the plan's own next test's already-established fake-`get_db`
pattern; same class of fix as Task 1's median-test bug). 3/3 new tests
passed after the fix; full suite 341 passed/2 skipped (was 338/2, zero
regressions). Committed at `dc4df5c`. Task-reviewer subagent approved spec
compliance + code quality with no Critical/Important findings.

## Task

Add three new `GET` routes to `backend/app/api/analytics.py` and write
`backend/tests/api/test_analytics_scorer_route.py`, exactly as specified
in Task 4 of the parent plan (full code for both is written out verbatim
in that task — this is a transcription-plus-verification job, not a
design job).

This is PRD-04's Scorer API surface: `GET /analytics/funds/{scheme_id}/score`
(fund-level FR-5/FR-7, 404 if the scheme doesn't exist), `GET
/analytics/household-members/{member_id}/score` (portfolio-level FR-6 for
one member, 404 if the member isn't the user's), and `GET
/analytics/household/aggregate/score` (whole-household aggregate). All
three mirror the exact `Depends(get_current_user)` /
`Depends(get_db)` / `get_household_member_for_user` 404 pattern every
other route in this file already uses (see e.g. the `/allocation` and
`/ter` routes right above where these get added).

## Constraints

- **No new patterns** — this file already has six near-identical route
  triples (member-scoped + aggregate) for allocation, benchmark, category
  ranking, and TER. These three follow the exact same shape byte-for-byte
  (import block, `router.get` decorator style, 404 check, return
  statement). Do not refactor the file, do not extract a shared helper —
  just add the fourth triple(-ish; fund-level score has no aggregate
  variant, it's per-scheme).
- **Reuse existing functions verbatim, don't reimplement them:**
  `compute_fund_score`, `compute_portfolio_score`,
  `get_aggregate_portfolio_score` (Tasks 2-3, already committed at
  `aa8288f` and `6129e96`); `get_current_user` from
  `app.services.auth.session`; `get_household_member_for_user` from
  `app.services.dashboard.household_members` (both already imported at
  the top of `analytics.py` — do not re-import).
- **Confirmed against live code before this handoff was written:** the
  file's existing imports (`APIRouter`, `Depends`, `HTTPException` from
  fastapi; `Session as DbSession` from sqlalchemy.orm; `get_db`; `User`;
  `get_current_user`; `get_household_member_for_user`) and the `router =
  APIRouter(prefix="/analytics", ...)` declaration already exist — only
  add the imports the plan's Task 4 lists as new (`Scheme` from
  `app.models.reference`, plus the three analytics schemas/functions), do
  not duplicate anything already imported.
- Follow the plan's task exactly: it already contains the complete route
  code and complete test file. Do not redesign, rename, or "improve" the
  approach — flag concerns in your report instead.

## Environment note — read before touching tests

**Do not attempt to run pytest, build a virtualenv, or install
dependencies.** This worktree has no `.venv` and no network access to
your sandbox — confirmed across Tasks 1-3. This is expected, not a
blocker.

Implement both files exactly per the brief, do NOT commit, and report
status `DONE_WITH_CONCERNS` (not `BLOCKED`) with verification deferred to
the controller, who will run the real suite (including the full backend
suite, per the plan's Step 5) from outside your sandbox, fix anything
genuinely broken, and commit. Proofread your own code carefully against
the brief — especially the two 404 checks and the response models on each
route decorator — since you won't get a red/green cycle this time.

## Approaches considered and rejected

Provisioning a venv inside this worktree was considered and rejected
again for the same reason as Tasks 1-3 — the controller verifying
directly is a fast, already-proven path.

## Open questions

None — this task is fully specified in the plan, and every signature it
calls (`compute_fund_score`, `compute_portfolio_score`,
`get_aggregate_portfolio_score`, `get_household_member_for_user`,
`get_current_user`) has been independently verified against the live
codebase (see Constraints above). If anything in the plan's Task 4 code
doesn't look internally consistent against what's actually on disk, note
it precisely in your report; do not silently change behavior.
