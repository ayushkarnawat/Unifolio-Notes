# Implementation session prompt — BUG-001 performance fixes + DATA-001 correctness fixes

Paste everything below this line into a fresh Claude Code session (a new
dedicated worktree, per this repo's standing convention) to start the
implementation work with full context.

---

Implement fixes for two already-completed, already-reviewed investigation
tickets. **Do not re-investigate from scratch** — the root causes are
already found, evidence-backed, and merged into `main`/`feat/enhanced-ui`
via PR #3:

- `Docs/orchestration/bug-001-findings.md` — Analytics dashboard
  performance investigation (waterfall table, root causes, proposed fixes).
- `Docs/orchestration/data-001-findings.md` — AUM/beta/TER/XIRR
  correctness investigation (field lineage, golden-dataset comparison,
  the +0.10% XIRR complaint's root cause).

Read both documents in full before writing any code. This is a real
implementation task, not investigation — follow this repo's non-negotiable
TDD discipline (failing test first, per `superpowers:test-driven-development`
and CLAUDE.md) and the `Decimal`-never-`float` rule for every money/percentage
value. Use the `model-orchestration` skill to delegate implementation
subtasks to Codex per its existing rules (read `SKILL.md` and
`references/delegation-rules.md` fresh — v1.2 as of 2026-08-17, includes
new isolation/retry/review-scope rules learned during the investigation
phase) — the mandatory handoff-doc-per-subtask and adversarial-review gate
still apply to every change here.

Work in a dedicated new worktree (`superpowers:using-git-worktrees`), not
directly on `feat/enhanced-ui`.

**Not in scope, already fixed:** `Docs/investigations/BUG-002-dashboard-
return-loading.md` (Main dashboard stuck loading after Analytics
navigation) is a separate, already-merged ticket (PRs #1/#2, merged
2026-08-17, well before this prompt's PR #3/#4) — its `Promise.all`/
`AbortSignal`/browser-history fixes are already in `feat/enhanced-ui`. Do
not re-investigate or re-fix it; it's unrelated to the Analytics-backend
timing/correctness issues below.

## Before starting: one gating question to resolve, not assume

DATA-001 found Beta is entirely unimplemented and AAUM has no real refresh
entrypoint (the function exists, unit-tested, but nothing calls it). Before
treating either as in scope for this pass, check `Docs/PRD-04-*.md` (and
`Docs/TDD-Unifolio.md`) for whether Beta and a scheduled AAUM refresh were
ever specified as MVP scope. If they were deferred/out-of-scope in the
PRD, they are **not** part of this bug-fix pass — flag them to the user as
a separate future task instead of building them here, per CLAUDE.md's
"don't gold-plate features the PRDs explicitly deferred" rule. If the PRD
does specify them as in-scope and simply never got built, stop and ask
Ayush before scoping a full feature build into what was framed as a
bug-fix pass — don't silently expand scope.

## Fix list, in priority order

Each item below should be its own handoff doc / Codex dispatch / review
cycle — these are independently shippable, per the findings doc's explicit
"split into separate tasks" requirement. Don't bundle unrelated fixes into
one diff.

### 1. XIRR ×100 display bug (DATA-001) — do this first, it's small and unrelated to the performance work below

**File:** `frontend/src/features/analytics/BenchmarkSection.tsx`,
`formatXirrPercent()`.

**Bug:** the backend returns XIRR as a decimal fraction (`0.10` = 10%).
This function does `parseFloat(val).toFixed(2)` and appends `%` without
multiplying by 100 — so a correct backend 10% displays as `+0.10%`. This
is the confirmed root cause of the ad-hoc "+0.10% seems too low" complaint,
and also itself violates CLAUDE.md's Decimal-never-float rule (`parseFloat`
in a percentage-display path).

**Fix:** multiply by 100 using exact decimal-string arithmetic — this repo
already has `frontend/src/lib/decimal.ts` with helpers like
`sumDecimalStrings`/`diffDecimalStrings`; check whether a
multiply-by-100-and-format helper already exists there, and if not, add
one following the same BigInt-based exact-arithmetic pattern (shifting the
decimal point by 2 places on the string is sufficient for ×100 — no actual
multiplication/BigInt math needed, unlike addition/subtraction). Do not
reach for `parseFloat`/`Number()` anywhere in this path. Write the failing
test first (existing test file: `BenchmarkSection.test.tsx`) asserting a
backend value like `"0.1435"` displays as `+14.35%`, confirm it fails
against current code, then fix.

### 2. Scorer: cache category-wide series + bound the series query (BUG-001, highest priority)

**File:** `backend/app/services/analytics/scorer.py`
(`_category_component_scores`, the `series_by_scheme` comprehension) and
`backend/app/services/analytics/risk_metrics.py` (`build_monthly_series`).

This is the only one of the five Analytics endpoints whose cost never
drops on repeat calls (confirmed 262.0–262.7s warm floor across 2 runs,
332.2s cold) — everything else gets cheap once cached, this doesn't,
because nothing about the category-wide series build is cached across
requests.

**Two independent parts, both needed:**
- Add the missing lower date bound to `build_monthly_series`'s NAV query
  (`risk_metrics.py:83-87` per the findings doc — confirm current line
  numbers, code may have shifted) — it currently fetches full NAV history
  since inception instead of just the requested month-end window.
- Cache `series_by_scheme` / category-level scoring results across
  requests with an explicit freshness key (mirror whatever TTL-cache
  pattern `nav.py`'s `warm_nav_history` already uses — this repo has that
  precedent, reuse it rather than inventing a new caching mechanism).

Write a failing performance-characterization test first if this repo's
test suite has a pattern for that (check `test_scorer.py`); otherwise
write a correctness test proving the cache doesn't serve stale data past
its TTL, plus manually re-measure the `/score` endpoint's warm-repeat
timing against the live repro setup afterward (same method BUG-001 used:
seeded DB, direct curl, ≥3 runs) to confirm the fix actually closes the
gap — don't claim it's fixed without a real before/after measurement.

**Also consider** (secondary, lower priority per the findings doc): moving
remaining synchronous CPU/DB work off the event loop, since the
concurrent-load test in BUG-001 didn't conclusively rule out event-loop
blocking during Scorer's synchronous stretches. Don't build this unless
the caching fix above doesn't fully resolve the timing, to avoid
over-engineering a fix beyond what's needed.

### 3. TER: negative-cache/backoff for unresolved schemes (BUG-001)

**File:** `backend/app/services/analytics/amfi_ter_client.py`
(`refresh_ter_data`, `_fetch_ter_rows`) and
`backend/app/services/analytics/ter.py` (`_ensure_ter_fresh`,
`_missing_current_month_ter`).

**Bug:** one missing current-month TER row for one scheme triggers a
sequential whole-country AMFI pagination scan (500 rows/page, no
concurrency) with no negative-caching/backoff — an unresolved scheme (bad
plan-variant match, or fuzzy match below `MIN_MATCH_CONFIDENCE = 0.55`)
re-triggers the full national scan on **every subsequent request**.
Measured 185.8s/277.0s while cold/re-fetching vs. 0.0297s once genuinely
warm.

**Fix:** persist a time-bounded negative result (e.g. "scheme X had no
resolvable TER match as of month Y, don't retry until Z") so a
permanently-unresolvable scheme doesn't cost a full national scan on every
request. Also coalesce concurrent whole-feed refreshes (if two requests
both find missing coverage simultaneously, only one should actually hit
AMFI — check whether this repo has an existing lock/in-flight-request
pattern elsewhere to reuse, e.g. the import-preview concurrency work
referenced in the model-orchestration observation log). Re-measure
directly against the live repro server afterward.

### 4. Category Ranking: bulk query + cross-request caching, investigate the alternating timing (BUG-001)

**File:** `backend/app/services/analytics/category_ranking.py`
(`_category_returns`, the per-scheme sequential loop) and
`risk_metrics.py`.

**Bug:** `_category_returns` warms NAV concurrently but then loops
sequentially per scheme (2 DB reads each) to compute 3y/5y returns, with
no cross-request caching. Measured an **alternating 42.77s/8.31s/43.56s/
8.71s pattern** across 4 runs — this is NOT a clean cold/warm split and
was left as a genuinely open, unexplained question in the findings doc
(checked and ruled out: `nav.py`'s 15-minute NAV-warm TTL doesn't explain
alternation within one TTL window; `category_ranking.py` itself has no
dedicated cache).

**Before fixing, investigate the alternation** — don't just apply the
obvious fix and assume it also happens to resolve a mystery you never
understood. Possible leads worth checking: is something else on the
machine/process periodically evicting a cache (GC pressure, a background
job, SQLite's own caching behavior under concurrent access)? Is there a
per-worker or per-connection-pool state that resets? Reproduce it first
(run the endpoint 4-6 times with timestamps) before touching code, per
`systematic-debugging`'s Phase 1.

**Fix:** replace the sequential two-lookups-per-scheme loop with a bulk
pair-of-dates NAV lookup for the whole category/window in one query, and
cache computed category returns across requests with an explicit
freshness key (same TTL-cache pattern as the Scorer fix above — these two
fixes should probably share the same underlying cache helper if the
timing/design allows, to avoid two different half-duplicate caching
mechanisms). Re-measure directly afterward, ≥3 runs, to confirm the
alternation is actually gone and not just coincidentally not observed in
a small sample.

### 5. Benchmark/NSE: add `follow_redirects=True` (BUG-001 low-priority + DATA-001 overlap)

**File:** `backend/app/services/analytics/nse_indices_client.py`
(`httpx.AsyncClient` construction, ~line 45-58 per the findings doc).

**Bug:** the client has no `follow_redirects=True`; a live curl against
niftyindices.com returned a 302. This is lower BUG-001 priority (the cost
is a one-time 63s cold hit, not a recurring hang — confirmed via 3 runs:
63.0s/2.81s/1.51s), but it's also a DATA-001 correctness concern: if the
redirect isn't followed, the request may be failing into the broad
`except` fallback and silently returning stale/empty index history rather
than genuinely fresh data, meaning benchmark comparisons could be silently
wrong rather than honestly "unavailable."

**Fix:** add `follow_redirects=True`, then verify with a live request
(same repro method) whether benchmark data actually populates correctly
afterward, and whether that changes the cold-cost timing. This is a small,
mostly self-contained fix — good first Codex dispatch if starting the
performance work in parallel with the XIRR fix above.

### 6. TER silent-zero + cost-adjustment sentinel (DATA-001)

**Files:** `backend/app/services/analytics/amfi_ter_client.py`
(`_best_match`, `refresh_ter_data`), `backend/app/services/analytics/ter.py`,
`backend/app/services/analytics/scorer.py` (`_cost_adjustment_from_context`).

**Bug 1:** a literal `Decimal("0")` TER value returned by AMFI's feed is
currently indistinguishable from "no match found" — both get treated as
valid coverage. A genuine zero-expense-ratio fund and a failed-match fund
look identical downstream.

**Bug 2:** `_cost_adjustment_from_context()` returns numeric `0` when own
TER or category AAUM-weighted TER is unavailable — indistinguishable from
a genuine "no adjustment needed" result.

**Fix:** introduce an explicit sentinel/optional-with-reason for "no TER
match found" distinct from a real zero value (e.g. `Decimal | None` with a
separate "matched" flag, or an explicit unavailable marker threaded through
to the API response) — check how the rest of this codebase represents
"unavailable" vs. a real value elsewhere (e.g. how benchmark handles
missing index data with `None`) and follow the same convention rather than
inventing a new one. Same for the cost-adjustment path — it should return
something the frontend can render as "unavailable" rather than a
possibly-misleading `0`.

**Re-run the golden TER comparison after this fix**, using
correctly-identified seed data — DATA-001 found the repro DB's 3 seeded
schemes had name↔AMFI-code pairs corrupted by the investigation's own seed
script (not an application bug), so the previously-measured 0.65%-vs-0.28%
weighted-TER mismatch could not be attributed to a real ingestion bug. Fix
the seed data identity (or write a fresh golden fixture with verified
correct name/code pairs — cross-check against mfapi.in or AMFI's own
scheme master, don't just trust a hand-typed name/code pair again) and
re-run `data-001-golden-independent.py`'s comparison method before/after
this fix to confirm whether a real ingestion discrepancy remains once the
identity data is correct.

### 7. Import identity validation tightening (DATA-001, separate from the analytics fixes above)

**Files:** `backend/app/services/import_/enrich.py`'s `resolve_scheme()`
(the `if amfi_from_cas:` branch, currently line 119-120 — **note: PR #4
("perf: cut first-login dashboard load time", merged 2026-08-17 after
these findings docs were written) touched this file for CAS-import
concurrency; re-confirm this line number against current code before
editing, don't trust it blindly**) and `backend/app/services/import_/
service.py`'s `confirm_import()` (the `amfi_code = (override.amfi_code ...)
or preview.suggested_amfi_code` lines, currently ~152 and ~185 — same
re-confirm-first caveat, PR #4 also touched `service.py`).

**Bug:** `enrich.py` accepts a CAS-supplied AMFI code paired with the
CAS-supplied scheme name at confidence 1.0 with no cross-check between
them, and `confirm_import()` persists `amfi_code` from the match/override
while `name` comes from parsed CAS data — including user-driven overrides,
which can pair an override code with the original parsed name. Combined
with `MIN_MATCH_CONFIDENCE = 0.55` (low, no AMC/category cross-check) in
the TER fuzzy-matcher, this is a real production risk: a real
casparser-derived scheme name variant could plausibly cross that low bar
and get mismatched, the same failure class that (accidentally,
self-inflicted) corrupted this session's own repro data.

Verified this specific line still has the gap post-PR#4 (still `return
SchemeMatch(amfi_code=amfi_from_cas, scheme_name=scheme_name,
confidence=1.0), "confirmed"` with no cross-check) — PR #4's changes here
were concurrency-only, not identity-validation-related, so the root cause
and fix approach below are unaffected by that merge. Only the line numbers
moved.

**Fix:** add a cross-check between the CAS-supplied/override AMFI code and
the scheme name before accepting the pairing at high confidence — e.g.
verify the code resolves to a scheme whose name is at least
plausibly-similar to the CAS-parsed name (reuse whatever fuzzy-matching
utility this repo already has, don't add a new dependency), and/or raise
`MIN_MATCH_CONFIDENCE` with an added AMC-code or category check. This
overlaps with the existing `MIN_MATCH_CONFIDENCE` finding — fix both in
the same pass since they're the same underlying validation gap surfacing
in two call sites. Check `CLAUDE.md`'s note on `confirm_import`'s existing
known gap (item 2 in the "Still open" list — "no server-side 409 backstop
on plan-type override") for related context before touching this file, in
case there's a cleaner combined fix.

## Constraints (carried over from the investigation, still apply)

- TDD: failing test first, for every fix above, no exceptions.
- `Decimal`, never `float`, for every money/units/NAV/percentage value —
  this includes frontend display formatting, not just backend
  computation.
- Every timing claim in your final report must be a real re-measured
  number against the live repro setup (or a fresh equivalent), not an
  assumption that a fix worked. Reuse BUG-001's repro method: seeded
  household member, direct curl against a running `uvicorn` instance,
  ≥3 runs recorded.
- Full backend + frontend test suites must pass, `tsc -b --noEmit` clean,
  before any fix's handoff doc moves to `DONE` — per `model-orchestration`'s
  existing verification-tiering rule (full suite required for the round
  expected to reach `DONE`).
- Update `session.md` and `CLAUDE.md`'s Session State section when this
  work completes, per this repo's existing convention — don't leave the
  next session to rediscover status from git log alone.
- Run `task-observer` at the end of this session too, same as the
  investigation session — capture anything non-obvious that comes up
  while actually implementing against these findings (a fix that turned
  out harder/easier than the findings doc implied, a caching pattern that
  should be extracted into a shared helper, etc.).
