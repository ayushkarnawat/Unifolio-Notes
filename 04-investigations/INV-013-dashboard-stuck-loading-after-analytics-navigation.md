# INV-013: Main dashboard remains stuck loading after navigating away to Analytics

Status: Root cause confirmed; a fix is implemented and tested on a dedicated
investigation branch — merge-to-`main` status not confirmed by this vault.
Date investigated: 2026-08-17. Branch:
`codex/bug-002-dashboard-return-investigation` (base `feat/enhanced-ui`,
PR base commit `3987321`).
Related: [2026-08-17 BUG-001/DATA-001](../02-journey/2026-08-17-bug-001-data-001-analytics-load-and-correctness-fixes.md),
[2026-08-13 dashboard cache race hardening](../02-journey/2026-08-13-dashboard-nav-and-holdings-cache-race-hardening.md),
[R-060](../07-risks-and-debt.md)

## For stakeholders

A user who opened Analytics and then clicked back to the main Dashboard
could get stuck looking at a loading skeleton forever, even though the
Dashboard's own data was actually ready. The cause was one extra, unrelated
background request (a "coverage gaps" check) that the Dashboard waited on
alongside its real data, with no timeout and no way to cancel it — if that
one request got delayed by traffic left over from Analytics, the whole
Dashboard stayed stuck even after everything a user actually needed had
already arrived. It was root-caused with a reproducible automated test (not
guessed at), and a fix was implemented and verified: the Dashboard now only
waits for the data it actually needs to render, the coverage-gaps check runs
independently, and switching screens now properly cancels abandoned
background work instead of leaving it running. A separate, smaller finding
was that clicking the browser's Back button couldn't undo an Analytics
visit at all, because tab switching wasn't recorded in browser history; the
same fix pass added that.

## Technical detail

### Symptom

`DashboardView` sets a page-wide `loading` flag on every mount and awaits a
single `Promise.all` of three requests: member holdings, member allocation,
and member coverage gaps. Holdings and allocation use a 60-second
`cachedFetch` response cache; coverage gaps uses raw `fetch` with no cache,
timeout, or `AbortSignal`, and is re-issued on every mount. If a user
navigates Dashboard → Analytics → Dashboard while a stale coverage-gaps
request from the second mount remains pending, holdings/allocation can
resolve (commonly from cache) but the combined `Promise.all` never settles,
so neither the success path nor the catch path runs and `loading` is never
set back to `false`. The page-wide skeleton (`HoldingsTableSkeleton`)
remains indefinitely, even though holdings/allocation data is already
available in memory.

Analytics widens the failure window without being its direct cause: all
seven Analytics requests keep running after `AnalyticsView` unmounts,
because cleanup only flips a local `isMounted` boolean and does not abort
any network request. A remounted Dashboard's uncached coverage-gaps request
can therefore be queued behind abandoned Analytics work still consuming
request capacity.

### Root cause

No request cancellation exists anywhere in this code path (no
`AbortController`), and the Dashboard's page-wide loading flag is gated on
all three requests settling rather than only the two that are actually
required to render. This is a genuine unbounded-wait condition, not a
caching, routing, or shared-state bug — seven other hypotheses (shared
cache key collision, a cached-pending promise, effect-cleanup/dependency
gaps, a shared global loading store, stale provider state, a swallowed
rejection, or Analytics mutating Dashboard state) were each individually
tested and rejected; see the evidence doc for the per-hypothesis findings
table.

### Reproduction

A temporary investigation-only Vitest probe (mock holdings/allocation
successful, resolve coverage gaps on first mount, unmount/remount the
Dashboard the way Analytics navigation does, leave the second coverage-gaps
promise intentionally pending) failed as predicted: dashboard content did
not render within 300ms and the skeleton remained, with holdings/allocation
data available but never committed to visible state. This is a
deterministic component/request-level trace of the stuck condition, not
dependent on a specific response shape or a real backend outage. A page
refresh appears to "fix" the symptom only because it destroys all
prior component/request state and starts a clean instance — it does not
remove the underlying unbounded wait.

### Fix implemented (on the investigation branch)

1. Dashboard's page-wide loading flag now waits only on holdings and
   allocation; coverage gaps loads independently and can no longer block
   valid portfolio data from rendering.
2. Dashboard and Analytics API functions now accept an `AbortSignal`;
   desktop and mobile views abort their own owned request sets on unmount
   or dependency change, closing the abandoned-request-capacity issue as
   well as the stuck-loading bug itself.
3. Mobile Dashboard received the same auxiliary-request separation,
   including its own aggregate member-status refresh, so the defect is not
   left unfixed in the parallel mobile UI.
4. Desktop tab changes are now written to browser history and restored on
   `popstate`, so browser Back/Forward performs Analytics ↔ Dashboard
   transitions — closing a related, separately-noted gap (desktop
   navigation had been purely local React state with no history entries at
   all, so Back could not previously undo an Analytics visit in any way).

The existing 60-second completed-response cache policy is unchanged;
failed/aborted requests are still never cached.

### Verification (per source; not independently re-run by this vault)

Red-first probe: 4 targeted failures before the fix (pending coverage
gaps, Dashboard abort, Analytics abort, browser-history restoration), all
green after. Focused suite 39/39 passed. Full frontend suite: 55 files,
213/213 tests passed. `tsc -b --noEmit` clean. Lint passed with only
pre-existing warnings, plus one new exhaustive-deps warning found and
corrected during review.

### Remaining uncertainty

- This vault has no evidence the investigation branch has been merged to
  `feat/enhanced-ui` or `main` — status is "fix implemented and tested on
  the investigation branch" only, per the source document's own framing.
- The seven required regression tests the source document names for the
  eventual fix PR (repeated/rapid tab switching, cache-policy tests,
  browser Back/Forward tests, etc.) are listed as required, not
  necessarily all present in the verification run reported above.

### Evidence

- `08-evidence/documents/BUG-002-dashboard-return-loading.md`
