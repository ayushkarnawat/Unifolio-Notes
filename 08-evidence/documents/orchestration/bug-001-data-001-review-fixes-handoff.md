Status: DONE

# BUG-001 / DATA-001 findings docs — review-fix round

## Context

`Docs/orchestration/bug-001-findings.md` and `Docs/orchestration/data-001-findings.md`
went through the mandatory `model-orchestration` adversarial-review gate. Verdict for
both: **needs-attention**. This handoff carries (a) new measurement data the
orchestrator gathered directly (localhost HTTP — your sandbox can't reach it, don't
attempt to re-run anything, just incorporate the numbers below), and (b) the exact
review findings with the specific correction each one needs. This is a **documentation
edit task only** — no application code changes, no re-running of HTTP calls, no new
test execution required for this round.

## New measurement data to incorporate into `bug-001-findings.md`

All against the same repro server/DB as the rest of the doc (household member
`6f9e78bf-68dd-4d25-b248-e31c8a4d5c17`, port 8001):

- **`/allocation` run3:** 200, 1.21s (consistent with prior runs: 1.78s, 4.01s-during-concurrent-test)
- **`/allocation` reverse-order concurrent sample:** 200, 0.0099s — started 2s *after* a `/score` request that was already running (see reverse-order concurrent test below)
- **`/ter` run3:** 200, 0.0297s — genuinely fast once the AMFI feed is fully cached/ingested. This changes the picture: run1=185.8s (cold), run2=277.0s, run3=0.0297s. The true warm floor is negligible; run2's 277s was evidently still in a cold/re-fetching state, not a stable "warm" value.
- **`/category-ranking` run3:** 200, 43.56s (matches run1's cold cost, not run2's 8.31s)
- **`/category-ranking` run4:** 200, 8.71s (back down, matches run2)
- **`/score` run4 (reverse-order concurrent test, started first):** 200, 394.21s
- **Reverse-order concurrent test:** `/score` started first (completed at 394.21s); `/allocation` started 2s later and completed in 0.0099s while `/score` was still in flight. Combined with the existing forward-order sample (`/allocation` 4.01s while a ~262s `/score` request was in flight), this is now 2/2 samples, both orders, showing no observed cross-request blocking.

## Findings to fix, in order (from the adversarial review)

### 1. [HIGH] `data-001-findings.md`: executive table/golden-comparison/conclusion contradict the Orchestrator correction

The "Orchestrator correction" section (near the top) says the TER golden-dataset
mismatch is garbage-in/garbage-out from the seed script and must be re-run with
correct identities before being treated as confirmed. But elsewhere the doc still
states an unqualified **"Fail"**:
- The executive summary table's TER ingestion/mapping row
- The golden-dataset comparison's weighted-TER row
- The conclusion section's "confirmed incorrect" line for TER end-to-end correctness

**Fix:** change all three to something like: *"Formula/computation logic: pass. Production ingestion correctness: open — the only golden-dataset comparison run so far used seed data with corrupted name↔AMFI-code identity (see Orchestrator correction), so this must be re-run with correctly-identified seed data before being treated as a confirmed, ship-blocking finding."* Do not leave a bare "Fail" standing anywhere in the doc for this specific item.

### 2. [HIGH] `data-001-findings.md`: Orchestrator correction overstates that production identity drift is impossible

The correction currently claims real `Scheme` rows "originate from the same source and
can't independently drift" the way the hand-typed seed data did. This is too strong.
Reading the actual import code:
- `backend/app/services/import_/enrich.py` (~lines 90-99) accepts a CAS-supplied AMFI
  code paired with the CAS-supplied scheme name at confidence 1.0, with no cross-check
  between the two.
- `backend/app/services/import_/service.py`'s `confirm_import()` (~lines 180-195)
  persists `amfi_code` from the match/override while `name` comes from parsed CAS
  data — including user-driven overrides, which can pair an override code with the
  original parsed name.

**Fix:** soften the correction's claim. Keep the core point (this specific repro's
mismatch was a seed-script artifact, not a demonstrated production bug), but remove or
qualify the "can't independently drift" line — instead note that the import path *does*
have an unvalidated name/code pairing risk (this overlaps with, and should
cross-reference, the doc's own existing `MIN_MATCH_CONFIDENCE = 0.55` finding), so the
seed-artifact conclusion applies to *this specific reproduction*, not as a blanket
guarantee that production data can never show a similar mismatch.

### 3. [RESOLVED — verify only] `bug-001-findings.md`: handoff's 3-runs-per-endpoint and both-order concurrency requirements

This was flagged as unmet (only 2 runs for allocation/ter/category-ranking, and only
one concurrent-test order). It is now resolved by the new measurement data above — each
of the three endpoints now has 3+ real runs, and both concurrent-test orders have been
run. Update the "Verification checklist against handoff" section to reflect this
honestly (3 runs each, both orders tested) using the exact numbers listed above. Do not
claim more precision than the data shows — e.g. category-ranking's runs (42.77s /
8.31s / 43.56s / 8.71s) alternate rather than cleanly separating into "cold" and "warm"
buckets; say so plainly rather than picking one bucket to feature.

### 4. [MEDIUM] `bug-001-findings.md`: concurrent-load interpretation overclaims

The doc currently speculates the single forward-order sample "happened to land in (or
near) an await window." With the new reverse-order sample now available, replace this
with the more defensible framing: *"Two independent samples, in both start orders, show
no observed cross-request blocking: forward-order, `/allocation` completed in 4.01s
while a ~262s `/score` request was in flight; reverse-order, `/allocation` completed in
0.0099s while a 394s `/score` request (started 2s earlier) was still in flight. This is
consistent with — but does not conclusively prove — the hypothesis that the slow
request's genuine `await` points (NAV warming via `asyncio.gather`, httpx calls) let
other requests interleave despite `get_db` being a synchronous generator dependency and
the routes being `async def`. It rules out simple total-blocking-for-the-full-duration,
but does not rule out blocking during specific synchronous stretches within the request."*

### 5. [MEDIUM] `bug-001-findings.md`: Benchmark's "one-time cold cost" causal explanation

The measured pattern (63.0s / 2.81s / 1.51s) is solid, repeated evidence — keep that
claim as-is. But soften the *causal* explanation: the doc currently states the 63s is
"entirely" the first NSE index-history fetch attempt, with the four sequential index
calls and the unfollowed-redirect NSE client cited as if fully confirmed. Reframe as:
*"The measured pattern (63.0s / 2.81s / 1.51s across three runs) confirms this is a
one-time cold cost, not a recurring hang. The most likely mechanism, based on reading
`benchmark.py`'s four sequential index calls and `nse_indices_client.py`'s 30s timeouts
without `follow_redirects=True`, is a slow/redirected first fetch per index that then
gets cached — but this wasn't confirmed via response-level tracing this session, so
treat the timing conclusion (one-time, not a hang) as confirmed and the specific
mechanism as the leading hypothesis, not a proven fact."*

### 6. [MEDIUM] `data-001-findings.md`: TER zero-as-coverage overclaimed as "confirmed incorrect"

The mechanism (a literal `Decimal("0")` passes the missing-value guard in
`amfi_ter_client.py` and gets counted as coverage in `ter.py`'s `_summarize()`) is
correctly identified and confirmed in code. But calling this "confirmed incorrect data"
overclaims, since the doc itself already notes there's no way to distinguish a genuine
zero from a feed placeholder, and the one reproduced example is known seed-corrupted.
**Fix:** reframe as a confirmed *structural gap* rather than a confirmed *incorrect
value*: *"Confirmed in code: a literal zero TER from the feed is indistinguishable from
a genuine zero-expense-ratio fund and both are counted as coverage. This is a real
validation gap regardless of the specific reproduced values (which are known
seed-corrupted) — flagged as a structural risk, not a demonstrated incorrect production
value."*

### 7. [MEDIUM] `data-001-findings.md`: XIRR bug's tie to the user's specific screenshot

The code defect (`BenchmarkSection.tsx`'s `formatXirrPercent()` never multiplying by
100) is solidly confirmed and should stay stated as confirmed. But the doc calls it the
"direct, confirmed root cause" of the specific screenshot while also noting the
screenshot itself couldn't be independently examined this session. **Fix:** reframe as:
*"This is a confirmed, unambiguous code defect that produces exactly the symptom
described (a real portfolio XIRR displayed as ~100x too small, e.g. a true +10% shown
as +0.10%). It is the confirmed root cause for a complaint of this shape; the specific
screenshot itself could not be independently re-examined this session to confirm it was
generated by this exact code path, but no other mechanism in the codebase produces this
100x-too-small pattern."*

### 8. [MEDIUM] `bug-001-findings.md`: Category Ranking's proposed fix bundles an inapplicable change, and the "warm floor" claim needs updating with new data

Two issues to fix together:

a) The proposed fix currently bundles a monthly-series lower-bound change alongside the
bulk-NAV-lookup fix, claiming both target Category Ranking's cost. But
`category_ranking.py` never calls `build_monthly_series` — only `scorer.py` does
(confirmed by reading both files). Remove the monthly-series lower-bound item from
Category Ranking's proposed fix; keep it scoped to the bulk pair-of-dates NAV lookup
(replacing the sequential per-scheme fetch loop). If a monthly-series lower bound is
still worth proposing, it belongs under the Scorer fix instead, not Category Ranking's.

b) Incorporate the new run3/run4 data (43.56s / 8.71s) which contradicts a clean
cold-then-permanently-warm story — runs alternate between ~8s and ~43s rather than
settling into one warm floor. Add a line noting this is not yet fully explained (the
15-minute NAV warm-TTL in `nav.py` doesn't account for it, since the alternating runs
happened well within a single 15-minute window) — flag as an open question for whoever
picks up the fix, rather than asserting a clean two-state (cold/warm) model.

### 9. [LOW] `bug-001-findings.md`: TER's mislabeled "warm floor" and unsupported linear-scaling extrapolation

With the new run3 data (0.0297s), relabel: run1 (185.8s) = cold; run2 (277.0s) = still
effectively cold / an in-progress retry, not a stable warm value; run3 (0.0297s) = the
actual warm floor once the feed is truly cached. Also soften the "~8s per category,
scaling linearly to 260s for 8 categories" claim in the Category Ranking section — this
was extrapolated from a single category's measurement and was never actually measured
across multiple categories; label it explicitly as an unverified extrapolation, not
measured evidence.

## Constraints

- Documentation edits only — no application code changes.
- Do not attempt any localhost HTTP calls or re-run any measurement; use only the
  numbers given above.
- Preserve the rest of each document's structure; these are targeted corrections, not a
  rewrite.
- When done, update this handoff's Status to REVIEW and briefly summarize what changed
  in each doc, section by section, so the orchestrator can quickly verify the edits
  against the review findings above before the mandatory re-review gate.

## Applied-change summary

### `bug-001-findings.md`

- **Result summary / measured waterfall:** incorporated allocation run 3 and the
  reverse-order sample, TER run 3, Category Ranking runs 3–4, and Score run 4; corrected
  TER's true warm floor and replaced Category Ranking's clean cold/warm claim with the
  observed alternating timings.
- **Concurrent-load verification:** documented both start orders and limited the
  conclusion to no observed full-duration blocking while preserving the possibility
  of blocking in specific synchronous stretches.
- **Blocking paths:** updated TER and Category Ranking timing interpretations, flagged
  the unexplained within-TTL Category Ranking alternation, and separated Benchmark's
  confirmed one-time timing pattern from its untraced causal hypothesis.
- **Proposed fixes / open questions:** removed the inapplicable monthly-series bound
  from Category Ranking, retained it under Scorer, scoped Category Ranking to bulk
  pair-of-dates NAV lookup, and labeled multi-category linear scaling unverified.
- **Verification checklist:** recorded three or more measurements for the required
  endpoints and both concurrent-test orders with the supplied exact numbers.

### `data-001-findings.md`

- **Orchestrator correction:** limited the seed-artifact conclusion to this repro and
  documented the production import path's unvalidated name/code-pairing risk with a
  cross-reference to the permissive-match finding.
- **Executive summary / golden comparison / conclusions:** changed TER computation to
  pass and production ingestion correctness to open pending a correctly identified
  rerun; removed the bare end-to-end failure conclusion.
- **TER correctness checks:** reframed zero-as-coverage as a confirmed structural
  validation gap, not a demonstrated incorrect production value.
- **XIRR correction and complaint analysis:** retained the confirmed ×100 formatter
  defect while qualifying its attribution to the unavailable specific screenshot.
