# Handoff: active-sips-frontend

**Status:** DONE (implemented at `9e25017`; round-0 review — dispatched
against a re-checked-out scope after an initial failed dispatch — returned
REQUEST-CHANGES for 2 Medium + 1 Low, fixed at `eeaade0`; round-1 scoped
re-review of `eeaade0` returned REQUEST-CHANGES for 1 Medium
(`setMonthlySipsLoading` inside a `useEffect` still let one stale-paint
frame through on month nav) + 1 Low (missing `role="tabpanel"` wiring),
both fixed at `8be5230`; round-2 scoped re-review of `8be5230` returned
REQUEST-CHANGES for 1 remaining Low (inactive tab's `aria-controls` IDREF
points at a not-yet-rendered panel) — accepted as a documented limitation
per the model-orchestration skill's stopping heuristic and explicit user
sign-off, logged in `CLAUDE.md`'s "Still open" list item 5 and mirrored in
`DEFERRED_FEATURES.md`'s appendix, rather than dispatching a round 3. Both
fix rounds applied directly by the orchestrator per "Review-loop fix
authorship" (diff small-to-moderate, files already in context). Full
frontend suite independently verified by the orchestrator on the closing
round: 55/55 files, 218/218 tests, zero regressions. Full round-by-round
detail: `Docs/orchestration/delegation-log.md`'s 2026-08-19 entries.)
**Parent plan:** `Docs/superpowers/plans/2026-08-18-active-sips-cadence-redesign.md` (Tasks 6-8)

## Task

Implement Tasks 6 through 8 of the parent plan, in order, exactly as
written — each task's steps already contain the real code to use verbatim.
This covers:

6. `types.ts` — add `next_due_date: string` to `SipRow`, add
   `SipMonthlyRow`/`AggregateSipsMonthlyResponse` interfaces; `api.ts` — add
   `getMemberSipsMonthly`/`getAggregateSipsMonthly`.
7. `DashboardView.tsx` — delete the client-side `upcomingSips` projection
   `useMemo`, sort by the server-provided `next_due_date` field directly; add
   a segmented "Upcoming"/"This Month" tab switcher (reusing the existing
   Portfolio Allocation section's tab-switcher JSX pattern verbatim); add
   month prev/next navigation visible only on the "This Month" tab; add a
   lazy `useEffect` that fetches the monthly view only when that tab is open
   (never as part of the initial page-load data fetch).
8. Test-file updates: `DashboardView.test.tsx` (mock factory + 2 existing
   fixture updates + 2 new tests) and `MainDashboardFlow.test.tsx` (its own
   separate mock factory needs the two new functions added too, or it will
   break with "No export is defined on mock" — this exact failure already
   happened once earlier this session when `getMemberSips`/`getAggregateSips`
   were first added without updating this file's mock in lockstep).

**Important:** `frontend/src/features/dashboard/DashboardView.tsx`,
`DashboardView.test.tsx`, `MainDashboardFlow.test.tsx`, and `api.ts` were all
just modified and committed on `feat/enhanced-ui` (commit `77c9d0d`) with the
original "Upcoming SIPs" feature (client-side projection, no `next_due_date`
field, no monthly tab). Task 6-8's line/context references in the plan
describe that already-committed state — read each file fresh before editing
rather than assuming line numbers from the plan are exact; match by the
quoted code snippets instead.

Run the full frontend suite (`cd frontend && npx vitest run`) and
`npx tsc -b --noEmit` after Task 8, and paste both results into your final
report. Some sandbox-level `vitest` worker-pool timeout flakiness on
unrelated files is a known pre-existing issue in this environment (not a
regression) — if a failure looks unrelated to files this task touched,
re-run once before reporting it as real.

## Constraints

- `Decimal`-string handling: money fields (`sip.amount`, `sip.sip_amount`)
  must go through `formatIndianCurrency` from `../../lib/decimal` for
  display — never render or arithmetic on them as raw JS numbers, per
  CLAUDE.md's non-negotiables.
- The monthly-SIPs fetch must never be part of the dashboard's initial
  page-load `Promise.all` — it must be lazy, fired only when the "This
  Month" tab is opened or the month is navigated. This is an explicit
  load-time constraint from the user this session, not a style preference.
- Reuse the exact existing tab-switcher CSS class pattern from the Portfolio
  Allocation section (`inline-flex items-center p-1 rounded-xl ...` /
  `cn(...)`-conditional button classes) rather than inventing new styling —
  visual consistency with the rest of the dashboard.

## Approaches considered and rejected

- Keeping the client-side `nextDueDate` projection `useMemo` alongside the
  new server-provided `next_due_date` field was considered and rejected —
  the server is now the single source of truth for projection (it also
  handles the redemption-exclusion case the old client math couldn't), so
  the client-side computation must be deleted outright, not left dormant.

## Open questions

None — every task's code is fully specified in the plan. If a step's quoted
"replace this exact snippet" text doesn't match the current file byte-for-byte
(likely, since the file was just modified — see the Important note above),
locate the equivalent code by intent (e.g., "the Upcoming SIPs section's
JSX block", "the client-side projection useMemo") and apply the same change
there, rather than skipping the step.
