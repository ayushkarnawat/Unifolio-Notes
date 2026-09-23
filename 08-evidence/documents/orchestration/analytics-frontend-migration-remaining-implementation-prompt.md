# Implementation prompt: finish the analytics frontend precompute migration

Run this yourself in your own Codex CLI/app session (paste the whole prompt below). Do
not run this via any Claude-side Agent dispatch — this repo's workflow is: you run
Codex directly, paste the output back, Claude reviews independently.

## Current state (verified by the orchestrator, not self-reported)

- `frontend/src/features/analytics/types.ts` and `api.ts` are done and correct —
  matches Tasks 1-2 of `Docs/superpowers/plans/2026-09-10-analytics-frontend-precompute-migration.md`.
  Do not re-do these.
- `frontend/src/features/analytics/AnalyticsView.tsx` still imports the 14 functions
  Task 2 deleted — the build is currently broken (`npx tsc -b --noEmit` fails). Nothing
  is committed, so this is safe to leave uncommitted while you fix it.
- `frontend/src/mobile/features/analytics/MobileAnalyticsView.tsx` (198 lines) is a
  second, independent consumer of the same 14 deleted functions. The plan document
  never accounted for this file — treat it as in-scope, same pattern as `AnalyticsView.tsx`.

## What's left

--- Copy from here into Codex ---

Repo: /mnt/d/Unifolio code (branch feat/enhanced-ui). Working tree already has Tasks 1-2
of `Docs/superpowers/plans/2026-09-10-analytics-frontend-precompute-migration.md` applied
(`frontend/src/features/analytics/types.ts` and `api.ts` — do not modify these further
unless a genuine bug in them surfaces while you work).

Do, in order:

1. Task 3 of that plan: build the `useAnalyticsScope` polling hook exactly as specified,
   plus its test file.
2. Task 4: rewrite `frontend/src/features/analytics/AnalyticsView.tsx` to consume the
   hook, exactly as specified, plus update its test file.
3. **Not in the plan doc, but required**: apply the same migration to
   `frontend/src/mobile/features/analytics/MobileAnalyticsView.tsx` and its test file
   (`MobileAnalyticsView.test.tsx`) — it is a second, near-identical consumer of the
   same 14 now-deleted `api.ts` functions (same section components: `AllocationSection`,
   `TerSection`, `CategoryRankingSection`, `ScorerSection`, `BenchmarkSection`,
   `FundScoreDetailModal`). Reuse the same `useAnalyticsScope` hook from step 1 — do not
   build a second hook. Adapt to `MobileAnalyticsView`'s existing prop shape
   (`memberId?: string | null`) rather than copying `AnalyticsView.tsx` verbatim.
4. Task 5: full-suite verification — run the frontend test suite AND
   `npx tsc -b --noEmit` from `frontend/`. Both must be fully clean (zero failures, zero
   type errors) before you report done. If you find yourself unable to make both clean,
   report exactly what's failing and why rather than reporting success.
5. Task 7: update session/status docs per that task's description.

Skip Task 6 (manual smoke test against a running backend — not available in this
environment) and Task 8 (review gate — the orchestrator handles this separately, do not
dispatch any review yourself).

Report back: exact `tsc` and test suite output (paste it, don't summarize as "passed"),
and a complete list of every file you changed or created.

--- Copy to here ---
