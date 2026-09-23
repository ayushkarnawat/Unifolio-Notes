# BUG-001/DATA-001: Analytics load-time investigation and a 7-item correctness fix batch

## For stakeholders

Two problems were investigated together because they showed up in the same
part of the app: the Analytics dashboard was reported as painfully slow to
load — one section ("Score") effectively never finished loading at all —
and separately, a user complained their portfolio gain was displayed as
"+0.10%" when it should have been meaningfully higher. Both were tracked
down to real, specific causes across three government/data-source
dependent sections (fund cost data, category rankings, and the fund
scoring page) plus one confirmed display bug, then fixed in seven
independently-tested pieces over the following two days, with every fix
checked by an independent reviewer before being accepted. Along the way,
the team discovered that some of the "data correctness" symptoms in their
test environment were actually caused by mistakes in the test data itself
(a step where the test setup accidentally paired the wrong fund names with
the wrong official codes), not by any real bug in the app — and confirmed
this distinction with an independent, differently-built verification tool
rather than trusting the app's own arithmetic to check itself. A follow-up
sanity check two days later, reading the finished code fresh rather than
relying on earlier notes, confirmed every fix was still in place and found
two small, low-priority items left over that don't need fixing before this
work ships.

## Technical detail

### BUG-001: five-endpoint Analytics load-time investigation

Live-measured against a seeded repro server (`unifolio_dev.db`, single
household member, single-worker `uvicorn`, 143 real AMFI-coded Large Cap
schemes, ~410,000 NAV-history rows). Investigation only in this phase — no
application code changed. Measured waterfall across five Analytics
endpoints:

- **`/allocation`**: consistently cheap (0.0099s–4.01s across runs); ruled
  out as a contributor.
- **`/ter`**: the strongest confirmed cause. One missing current-month TER
  row triggers a sequential, whole-country AMFI pagination scan with no
  negative cache or backoff for an unresolved/missed scheme, so the same
  gap re-triggers the full scan on every request. Measured 185.8s / 277.0s
  while cold-or-re-fetching, dropping to 0.0297s once genuinely cached.
- **`/category-ranking`**: a separate category-wide cost — two returns
  computed sequentially per scheme, per held category, after NAV warming.
  Four runs alternated between ~43s and ~8s (42.77s / 8.31s / 43.56s /
  8.71s) rather than settling into a clean cold/warm split — an
  alternation the 15-minute NAV warm-TTL doesn't explain, left as an open
  question for the fix.
- **`/score`**: the single highest-priority finding — a structurally
  blocking, category-wide synchronous series build with **no cache across
  requests at all**. Unlike the other four endpoints, its cost never
  dropped on repeat calls (332.2s cold, then 262.02s–262.68s warm, still
  ~262s every time). This matched the original complaint that Score
  specifically "does not load at all."
- **`/benchmark`**: a one-time cold cost (63.0s), dropping ~40x once cached
  (1.5s–2.8s) — confirmed not a recurring hang, with the likely mechanism
  (an unfollowed 302 redirect against the NSE indices source) flagged as a
  leading hypothesis, not confirmed via response-level tracing at this
  stage.

A concurrent-load test in both start orders found no observed
cross-request blocking for the full request duration (consistent with,
but not conclusive proof of, the hypothesis that the slow requests' real
`await` points let other requests interleave) — this rules out simple
total blocking but does not rule out blocking during specific synchronous
stretches within a request.

### DATA-001: field lineage, golden dataset, and the XIRR complaint

Investigation/documentation only in this phase; synthetic transaction data
and public scheme data only, no real user data touched. A machine-readable
golden dataset (`data-001-golden-dataset.json`) with synthetic ₹100,000
purchases against three public AMFI codes was checked against the
application's XIRR and TER calculations using an **independently-built
reference tool, deliberately using different math than the application's
own implementation** — a bisection-method XIRR (as opposed to the app's
Newton-Raphson) and a SUMPRODUCT-style spreadsheet TER calculation — so
that a shared bug in both the app and its own self-check couldn't hide a
real error. Backend XIRR matched the independent calculation to within
0.01 percentage points (a confirmed pass).

**Seed-data corruption found and corrected mid-investigation.** The
repro database's three seeded scheme rows had AMFI-code↔name pairs
scrambled by the investigation's own seed script (not by any application
code): code 118989 was labeled "Nippon India Growth Fund" but is really
HDFC Mid Cap Fund; 120503 was labeled "HDFC Large Cap Fund" but is really
Axis ELSS Tax Saver Fund; 120716 was labeled "ICICI Prudential Bluechip
Fund" but is really UTI Nifty 50 Index Fund. This was caught before the
review gate and flagged prominently: the originally-observed 0.65%-vs-
0.28% weighted-TER mismatch was primarily an artifact of this seed
corruption, not a demonstrated production bug — a conclusion later
confirmed, not just asserted, by a clean re-run (below).

What remained genuinely code-level, independent of the seed bug:

- **XIRR ×100 display bug** — `BenchmarkSection.tsx`'s
  `formatXirrPercent()` never multiplied the backend's decimal-fraction
  XIRR by 100 before appending `%`. Confirmed against the golden dataset's
  own correct backend value (`0.143451...` displayed as `+0.14%` instead
  of `+14.35%`) — this is the confirmed root cause for a complaint of this
  shape (an ordinary correct ~10% XIRR displaying as "+0.10%"), though the
  specific user screenshot named in the original complaint could not
  itself be re-examined this session to prove it traversed this exact code
  path.
- **TER's literal zero treated as genuine coverage** rather than
  "no match" — a real structural gap in `refresh_ter_data`/`_best_match`
  regardless of which scheme name matched.
- **`MIN_MATCH_CONFIDENCE = 0.55`** with no AMC/AMFI-code/category
  cross-check — a real, permissive fuzzy-matching design gap in the import
  path (`enrich.py`, `service.py`'s `confirm_import()`), worth flagging as
  a risk even though this specific repro's mismatches were self-inflicted,
  since a real CAS-parsed scheme-name variant could plausibly cross the
  same low bar in production.
- Beta not implemented; AAUM never populated (no live refresh entrypoint
  exists, only unit-test coverage); NSE redirect not followed.

**Golden-comparison re-run with corrected identities (2026-08-18) —
closes the TER item.** Re-ran the comparison from scratch in a fresh,
isolated SQLite database seeded directly from the golden dataset's
*correct* name↔AMFI-code pairs, calling the app's real
`compute_weighted_ter` end-to-end with the live AMFI NAV fetch mocked to
force a fallback to the frozen seeded NAV. Result: **exact match** —
app-computed weighted TER 0.65% vs. golden's 0.65% (0.00pp diff, well
inside the 0.01pp tolerance). Conclusion: the original mismatch was
entirely the seed script's scrambled identity mapping, not a defect in
`compute_weighted_ter`, `refresh_ter_data`, or its fuzzy matching. The only
genuinely still-open risk in this area is the *unvalidated* import-time
name/AMFI-code pairing (`MIN_MATCH_CONFIDENCE = 0.55`), not the weighting
or computation logic itself.

### Documentation review-and-correction round

Before either findings doc was accepted, both went through this project's
mandatory adversarial-review gate and came back "needs-attention" —
several claims in `bug-001-findings.md`/`data-001-findings.md`
overstated confidence beyond what the evidence supported (e.g. an
unqualified "Fail" verdict for TER left standing alongside the seed-
corruption caveat; a too-strong claim that production scheme identity
"can't independently drift"; Category Ranking's proposed fix bundling in
an inapplicable change; TER's "warm floor" mislabeled before a third
measurement run arrived). All were corrected in a documentation-only round
— no application code changed at that stage — reframing each overclaim
as an explicitly qualified, evidence-scoped statement instead of removing
the underlying finding.

### The 7-item implementation batch (2026-08-18)

TDD throughout (red → green), `Decimal` never `float` for any money/units/
NAV value touched, each item independently reviewed through the project's
mandatory adversarial-review gate before being accepted:

1. **XIRR ×100 display fix.** Added an exact decimal-string-shift
   `toPercentString()` helper (no `parseFloat`/`Number()`) to `decimal.ts`,
   used for all three displayed XIRR/diff strings in `BenchmarkSection.tsx`.
   This also fixed a latent second bug: a hardcoded `maxAbsXirr` floor of
   10 had been dominating unscaled ~0.05–0.20 fraction values, collapsing
   every comparison bar to its 3% minimum width. Test fixtures using
   unrealistic pre-scaled values (`"16.45"`) were corrected to raw
   fractions (`"0.1645"`). Full frontend suite 214/214, `tsc -b --noEmit`
   clean.
2. **Scorer category-wide series caching.** Split
   `_category_component_scores` into an unchanged compute function plus a
   new date-aware TTL-cache wrapper (15-minute TTL, keyed by
   `sebi_category`, requiring both TTL-freshness *and* same-calendar-day
   serving — a correctness addition beyond a pure-TTL pattern, since the
   composite score depends on calendar-day-anchored month-end dates). Also
   rewrote `build_monthly_series`'s NAV query from a single unbounded
   history scan to a two-query seed-then-bound approach, provably
   output-identical to the old carry-forward logic. Live-profiled and
   confirmed this was the correct highest-priority target.
3. **TER negative-cache/backoff** — the single most technically involved
   item, going through three review→fix rounds:
   - Round 1 fix: a 15-minute backoff tracking the last refresh *attempt*
     time (mirroring `nav.py`'s TTL pattern), guarded by an
     `asyncio.Lock` so concurrent callers share one in-flight refresh.
     Live-verified against the real repro server: `/score` went from
     3m51.375s (cold, post-restart) to 0.197s then 0.145s on warm repeat
     calls.
   - A scoped review round found the module-global `asyncio.Lock()` only
     binds to a specific event loop once genuinely contended — worse than
     the reviewer's originally-suspected `RuntimeError` risk, this could
     silently **deadlock** across loops (live-reproduced via a two-thread/
     two-loop test). Fixed by keying the lock per-running-loop via a
     `WeakKeyDictionary`.
   - A second review round found the per-loop-lock fix's own follow-on
     bug: the shared backoff timestamp check-and-set was still a plain
     unguarded global, so two different loops could each pass their own
     lock and both slip past a stale timestamp, duplicating refreshes.
     Fixed with a `_claim_ter_refresh_slot()` guarded by a plain
     `threading.Lock` (the correct primitive, since the critical section
     is synchronous).
   - A third review round found the round-2 regression test didn't
     actually prove atomicity — it gated the second thread on a flag that
     only ever became true after the first thread's claim had already
     landed, so it would have passed even without the lock. Fixed with a
     deterministic test using a wrapped lock that blocks on first
     `__enter__` until signaled, forcing genuine contention; verified RED
     (lock temporarily reverted, test failed) then GREEN. A closing review
     then approved with zero findings.
4. **Category Ranking bulk NAV query.** Replaced the sequential
   two-lookups-per-scheme loop with a bulk `MAX(date) GROUP BY` query
   fetched once per target date, plus a TTL+day-aware cross-request cache
   mirroring the Scorer cache. Live-verified: `/category-ranking` went
   from 23.076s cold to 0.019s–0.027s across four warm repeat calls. A
   review round found the first-pass fix still materialized whole-history
   rows before a Python `bisect` narrowed them; this was accepted as a
   documented limitation of that intermediate approach and then replaced
   entirely with a `MAX(date) GROUP BY` subquery joined back to
   `NavHistory` (exactly one row per scheme, regardless of category size
   or scheme age).
5. **NSE redirect handling — added, then correctly reverted.** First fix:
   pass `follow_redirects=True` to `nse_indices_client.py`'s
   `httpx.AsyncClient`. A review round found this was a real risk in
   general (httpx follows redirects with browser-style POST-to-GET
   semantics, which could silently swap in a wrong dataset under a
   redirect) — but before re-fixing, the orchestrator investigated rather
   than patched around an unreproduced claim: a live `curl` against the
   exact configured URL/scheme returned `200 OK` with correct data
   directly, no redirect at all. The `follow_redirects=True` change was
   reverted as solving a problem that did not exist for the currently-
   configured URL; a narrower, correctly-scoped fix (broadening the
   caught-exception tuple to include `decimal.InvalidOperation`) closed
   the actual finding instead.
6. **TER/Scorer silent-zero sentinels.** `refresh_ter_data` now skips
   literal-zero `R_TER`/`D_TER` rows during ingestion (AMFI's convention
   for "no plan of this type," previously mis-persisted as a genuine 0%
   TER); `scorer.py`'s cost-adjustment now returns `None` (not
   `Decimal("0")`) in the API-facing row when TER is unavailable,
   distinguishing "unavailable" from "a real computed zero." A review
   round found the ingestion fix didn't retroactively clear an
   already-persisted stale zero from before the fix, letting old
   corrupted rows silently survive; fixed with a
   `_clear_stale_zero_ter()` helper that deletes an existing zero-value
   row for the same scheme/period only if that existing row is itself
   zero (never touching a genuine non-zero value).
7. **Import identity validation.** `enrich.py`'s `resolve_scheme()` now
   cross-checks a CAS-supplied AMFI code against its canonical master-list
   name (≥0.92 similarity) before confirming at full confidence, instead
   of trusting the CAS-supplied (code, name) pairing unconditionally;
   `service.py`'s `confirm_import()` now rejects an override AMFI code not
   found in the cached master list and persists the override's canonical
   name rather than a stale CAS-parsed name. This directly closes the
   unvalidated-pairing risk `data-001-findings.md` had flagged. A review
   round found 2 Medium/3 Low findings, all fixed; closing review
   approved.

### Post-implementation performance re-assessment (2026-08-19)

A fresh, direct re-read of every Analytics service file (not a restatement
of memory or the original findings doc) confirmed all 7 fix items intact:
per-section independent frontend fetches (no shared spinner blocking a
fast section behind a slow one), 15-minute category-wide TTL caching
shared across Category Ranking and Scorer, a 15-minute NAV warm cache with
single-flight de-dup, bulk/bounded SQL replacing every N+1 found, and the
TER negative-cache backoff intact. Two new, previously-undocumented
low-severity items were found and deliberately left unfixed as optional
MVP-scope follow-ups: `nse_indices_client.py` still opens a fresh
`httpx.AsyncClient` per call rather than reusing a shared one (low impact,
only 4 indices, most calls short-circuit on cached bounds anyway); and
`scheme_universe.py`'s in-process memoization means its 24h disk-cache TTL
is only re-checked on first access per process lifetime, not continuously
(a staleness nuance, not a correctness bug). Conclusion: "no further work
is required before merging this branch into `feat/enhanced-ui`."

### Related

- [2026-08-17 dashboard load time: connection reuse and import-preview
  concurrency](2026-08-17-dashboard-load-time-connection-reuse-and-import-preview-concurrency.md)
  — an independent investigation targeting different Analytics/dashboard
  endpoints in the same general window; not a duplicate of this entry.
- Evidence: `08-evidence/documents/orchestration/bug-001-findings.md`
- Evidence: `08-evidence/documents/orchestration/bug-001-remaining-verification-handoff.md`
- Evidence: `08-evidence/documents/orchestration/data-001-findings.md`
- Evidence: `08-evidence/documents/orchestration/data-001-lineage-golden-handoff.md`
- Evidence: `08-evidence/documents/orchestration/data-001-golden-dataset.json`
  (the golden dataset's independent verification script,
  `data-001-golden-independent.py`, is deliberately not copied into this
  vault per its "no source code" policy — its methodology is described in
  prose above)
- Evidence: `08-evidence/documents/orchestration/bug-001-data-001-implementation-prompt.md`
- Evidence: `08-evidence/documents/orchestration/bug-001-data-001-review-fixes-handoff.md`
- Evidence: `08-evidence/documents/orchestration/bug-001-data-001-post-implementation-performance-assessment.md`
- Evidence: `08-evidence/documents/orchestration/import-identity-validation-handoff.md`
- Evidence: `08-evidence/documents/orchestration/delegation-log.md` (2026-08-18/19 entries)
