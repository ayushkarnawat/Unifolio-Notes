# BUG-002 — Main dashboard remains loading after Analytics

Date: 2026-08-17  
Branch: `codex/bug-002-dashboard-return-investigation`  
PR base: `3987321` (`origin/feat/enhanced-ui`)  
Status: root cause confirmed; robust fix implemented on the investigation branch

## Executive finding

The reproducible stuck transition is in the single-member dashboard path, not in a
shared Dashboard/Analytics cache entry or global loading store.

`DashboardView` sets its page-wide `loading` flag to `true` on every mount and awaits
one `Promise.all` containing:

1. member holdings;
2. member allocation; and
3. member coverage gaps.

Holdings and allocation use the 60-second `cachedFetch` response cache. Coverage gaps
uses raw `fetch`, has no timeout or cancellation, and is fetched again on every mount.
If that third request remains pending after Analytics -> Dashboard, the first two
requests can resolve from valid cache but the `Promise.all` continuation never runs.
Neither the success block nor the catch block is reached, so `setLoading(false)` is
never called. The full dashboard remains behind `HoldingsTableSkeleton` indefinitely.

Analytics contributes to the failure window because all seven Analytics requests keep
running after its component unmounts. Cleanup only flips a local `isMounted` boolean;
it does not abort network/backend work. A remounted dashboard therefore starts its
uncached coverage-gap request while abandoned Analytics work can still be consuming
backend/external-request capacity. A settled Analytics rejection is handled locally
and does not directly mutate Dashboard state; the hazardous state is an unresolved
request, including a request delayed behind abandoned work.

## Exact stuck transition

| Step | Component/request state | Result |
|---|---|---|
| 1 | Initial member `DashboardView` mounts; `loading=true` | holdings, allocation, and coverage gaps settle |
| 2 | Dashboard success continuation runs | data is stored and `loading=false` |
| 3 | User selects Analytics | Dashboard unmounts; its `isMounted=false` |
| 4 | `AnalyticsView` starts 7 requests | cleanup on later unmount does not cancel them |
| 5 | User returns to Dashboard | a new `DashboardView` instance initializes `loading=true` |
| 6 | holdings/allocation resolve, commonly from the 60s cache | valid main data is available to the promises but not committed to component state |
| 7 | raw `GET /household-members/{id}/coverage-gaps` remains pending | the combined `Promise.all` remains pending |
| 8 | no `then`, `catch`, or `finally` exists outside that combined await | `loading` stays `true`; skeleton remains |

A page refresh appears to recover when the new coverage-gap request settles because it
destroys all prior component/request state and starts a clean app instance. It does not
remove the underlying unbounded-wait condition.

## Reproduction evidence

A temporary investigation-only Vitest probe (removed after the run) performed this
sequence:

1. mock holdings/allocation as successful;
2. resolve coverage gaps on the first mount;
3. unmount the dashboard (the Analytics navigation behavior);
4. remount it with holdings/allocation successful and the second coverage-gap promise
   intentionally left pending;
5. assert that normal dashboard content renders within 300 ms.

Result:

```text
DashboardView.test.tsx (7 tests | 1 failed)
BUG-002 probe: core cached data renders when coverage-gap refresh remains pending on remount
Unable to find an element with the text: No Holdings Found
DOM: <div class="py-8 animate-pulse"> ... HoldingsTableSkeleton ...
Tests: 1 failed | 6 passed
```

This is a deterministic component/request trace of the stuck state. It does not depend
on response-shape assumptions or a real backend outage.

## Hypotheses evaluated

| Hypothesis | Finding | Evidence |
|---|---|---|
| Main and Analytics share a cache key | Rejected | Main allocation URLs begin `/household/...`; Analytics URLs begin `/analytics/household/...`. `cachedFetch` keys on the full URL. |
| An aborted request is cached as pending | Rejected | There is no `AbortController`; `cachedFetch` stores only an already-resolved, successful `Response`, after `fetch` completes. It does not cache promises. |
| Effect cleanup/dependencies prevent refetch | Rejected | tab switching fully unmounts/remounts the views; Dashboard's effect depends on `viewMode` and `memberId` and runs on each mount. |
| Analytics leaves a global loading flag set | Rejected | Dashboard and Analytics loading flags are component-local `useState`; there is no shared query/loading store. |
| Preserved provider/layout holds stale dashboard state | Rejected | `MainDashboardFlow` uses a ternary and fully replaces `DashboardView` with `AnalyticsView`. Only auth and shell state survive. |
| A swallowed rejection skips cleanup | Rejected for settled failures | Dashboard catches core failures and sets `loading=false`; coverage-gap rejections are converted to `[]`. Analytics sections use `finally`. An unresolved promise, not a rejected one, bypasses all settlement code. |
| Analytics mutates/clears state required by Main | Rejected | no shared data store exists; the only shared mechanism is the GET response cache, whose URLs are distinct. |

## Success, failure, cancellation, and repeated switching

- Analytics success: returning works if all Dashboard remount requests settle.
- Analytics partial/full rejection: settled rejections do not poison Dashboard state or
  cache. Failed responses are not cached.
- Cancellation: not implemented. Unmount suppresses React state writes but does not
  cancel any request. Consequently a true cancellation trace cannot currently occur.
- Repeated/rapid switching: every mount creates a new request set. Stale completions are
  prevented from writing to an unmounted instance by `isMounted`, but abandoned work is
  unbounded and requests are not deduplicated while in flight.
- Duplicate calls: the response cache deduplicates only sequential requests after the
  first response is stored. Concurrent calls for the same URL are not coalesced.
- Console behavior: expected Analytics section failures are logged with
  `console.error`; unmounted successful/failing requests are suppressed from state
  writes. No code path creates a React unmounted-state warning.

## Browser Back finding

Desktop navigation is not route based. `MainDashboardFlow.activeTab` is local React
state and `NavigationShell` uses buttons that call `setActiveTab`; neither
`history.pushState` nor a router is used. Selecting Analytics creates no browser-history
entry, so browser Back cannot execute Analytics -> Dashboard. This acceptance criterion
requires a small routing/history change in addition to the loading fix, or it must be
explicitly re-scoped to in-app navigation.

## Affected code

- `frontend/src/features/dashboard/DashboardView.tsx:68-125`: page-wide loading flag
  and the three-request `Promise.all`; `setLoading(false)` exists only after all settle
  or a rejection reaches the catch.
- `frontend/src/features/import/api.ts:134-145`: coverage-gap GET uses raw `fetch`, with
  no cache, timeout, or abort signal.
- `frontend/src/features/analytics/AnalyticsView.tsx:76-160`: seven independent request
  chains; cleanup suppresses state writes but does not abort requests.
- `frontend/src/features/dashboard/MainDashboardFlow.tsx:24,147-173`: local tab state
  and full view unmount/remount.
- `frontend/src/lib/apiClient.ts:32-52`: completed-response cache; no pending-request
  coalescing or request ownership/cancellation.

## Implemented fix

The fix goes beyond the minimal render change and closes the related lifecycle gaps:

1. Dashboard page-wide loading now waits only for holdings and allocation. Coverage
   gaps load independently and can no longer block valid portfolio data.
2. Dashboard and Analytics API functions accept an `AbortSignal`; desktop and mobile
   views abort their owned request sets on unmount or dependency change.
3. Mobile Dashboard received the same auxiliary-request separation, including its
   aggregate member-status refresh, so the defect is not left in the parallel UI.
4. Desktop tab changes are written to browser history and restored on `popstate`, so
   browser Back/Forward now performs Analytics <-> Dashboard transitions.

The existing completed-response cache policy is unchanged: successful GET responses
remain reusable for 60 seconds and failed/aborted requests are not cached.

## Verification after implementation

- Red-first probe: 4 targeted failures before implementation (pending coverage gaps,
  Dashboard abort, Analytics abort, browser-history restoration).
- Focused suite: 39/39 tests passed.
- Full frontend suite: 55 files, 213/213 tests passed.
- TypeScript: `tsc -b --noEmit` passed.
- Lint: passed with pre-existing Fast Refresh/useMemo warnings only; the one new
  exhaustive-dependencies warning found during review was corrected.

## Required regression tests for the fix PR

1. Main -> Analytics -> Main with all requests successful.
2. Same transition with Analytics allocation failure and with each optional Analytics
   section failing.
3. Return while Analytics requests are pending; verify cleanup aborts them.
4. Return with coverage gaps pending/failing; verify holdings/allocation render and the
   page-wide loading flag settles.
5. Repeated and rapid tab switching; verify no stale overwrite, unmounted-state error,
   or unbounded duplicate requests.
6. Cache-policy tests for fresh cached Main data and invalidation after import/opening
   balance.
7. Browser Back/Forward tests once tab state is represented in history.
