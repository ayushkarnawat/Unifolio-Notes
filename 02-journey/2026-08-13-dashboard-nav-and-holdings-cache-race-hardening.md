# The dashboard's NAV and holdings caches are hardened against real concurrency races, across six review rounds

## For stakeholders

Over six review-and-fix rounds between 13 and 18 August, the dashboard's
performance-caching layer was tested against what actually happens when
real users import data, refresh, and hit the same endpoints at close to
the same time — not just against a single well-behaved request. Three real
bugs were found and fixed this way: a stale holdings figure that could
survive a fresh CAS import, a race between two browser tabs both saving a
value at once, and a gap where the dashboard could publish a number to a
user with data that had already changed underneath it. A fourth known gap
was found, discussed, and deliberately left as a documented limitation
rather than fixed immediately. Along the way, a separate cache with no
expiry and a frontend with no caching at all were both found and fixed
too.

## Technical detail

### Intended outcome

Make the dashboard's NAV-lookup and holdings-aggregation caching layer
safe under real concurrent access, not just fast under a single request.

### What actually happened

Six rounds of dispatch-then-mandatory-adversarial-review ran across
2026-08-13 through 2026-08-18, fixing three genuine concurrency races:

1. **A stale holdings cache surviving import invalidation** — a cached
   holdings total could outlive a fresh CAS import that should have
   invalidated it.
2. **A cross-session upsert race** — two concurrent writers (e.g. two open
   tabs) could both pass a check-then-insert gate and upsert the same row.
3. **Generation-check/publish non-atomicity** — the dashboard could read a
   "current" generation number, then publish a value computed against it,
   with the underlying data changing in between the check and the publish.

A fourth finding — a one-shot prefetch with no staleness bound — was fixed
with a 15-minute TTL. A separate, related finding — no per-key
single-flight coordination, so two near-simultaneous requests for the same
uncached key could both trigger a duplicate expensive recompute — was
reviewed in round 4 and **deliberately not dispatched for a fix**; the
product owner explicitly decided to accept and document it rather than
add coordination machinery, at least for now.

**Round 5 (2026-08-14)** was a newly discovered gap, not a re-review of
rounds 1-4: `warm_nav_history` had no TTL at all (fixed, 15-minute cache),
and the frontend had **no caching layer whatsoever** — every dashboard
interaction re-fetched from the network. Fixed with a 60-second in-memory
GET-response cache in `lib/apiClient.ts` (`cachedFetch` /
`invalidateApiCache`), wired into both the dashboard and analytics
`api.ts` modules, and explicitly invalidated on `confirmImport` and
`postOpeningBalance` so a fresh import or a new opening balance is never
served a stale cached response.

**Round 6 (2026-08-17/18)** split into two sibling handoffs not covered by
this stage's source material (`nav-fetch-connection-reuse-handoff.md`,
`import-preview-concurrency-handoff.md`), merged as PR #4 — recorded here
only as a forward pointer for a future ingestion batch, not drafted from.

### Deviation (if any) — decision or response taken

The round-4 single-flight-coordination gap was reviewed and explicitly
**not** fixed, by product-owner decision — accepted as a documented
limitation rather than dispatched for a round-5 fix. This is a deliberate
scope boundary, not an oversight.

### Result

Three real concurrency races fixed and independently re-reviewed across
rounds 1-4; a one-shot-prefetch staleness gap and a completely absent
frontend caching layer found and fixed in round 5; one further
coordination gap accepted as a known limitation rather than fixed; round 6
merged via a PR this stage's material does not itself document in detail.

### Related

- R-060 — no per-key single-flight coordination on cache-miss recompute (new, this stage)
- ADR-015 — analytics precompute architecture (a related but separate caching layer, built later)
- Evidence: `08-evidence/documents/orchestration/dashboard-nav-perf-handoff.md`
