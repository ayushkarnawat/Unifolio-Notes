# Handoff: nav-fetch-connection-reuse

**Status:** DONE (implemented at `d4700b7`, adversarial review approved with 2 minor test-coverage nits, both closed at `721172c`, scoped re-review approved with zero new findings. Full backend suite 369 passed/2 skipped, independently verified by the orchestrator, zero regressions.)
**Parent plan:** none (direct diagnosis this session, follow-on to `dashboard-nav-perf-handoff.md`, whose Status is DONE — this is a new, separately-scoped finding in the same file, not a reopening of that doc's rounds)

## Background

User reported the *first* dashboard load right after signup/CAS import is still
~30 seconds despite `dashboard-nav-perf-handoff.md`'s Fix A (background NAV
prefetch on import confirm), Fix B (parallelized per-scheme network fetch), and
Fix D (process-local holdings cache) already being merged. Root cause was
diagnosed directly (not delegated) via `superpowers:systematic-debugging`,
Phase 1, with live reproduction against the real `api.mfapi.in` endpoint (this
sandbox has network egress to it — confirmed, not assumed) rather than
mocked-only:

1. **`_fetch_nav_history` (`backend/app/services/dashboard/nav.py`) opens a
   brand-new `httpx.AsyncClient()` for every single scheme fetch**, with no
   connection reuse across concurrent calls. Benchmarked live: 20 concurrent
   full-history fetches to real `api.mfapi.in` scheme codes took **3.60s**
   with a new client per request vs **0.63s** with one shared, connection-
   pooled client for the exact same 20 codes — roughly a 5-6x difference from
   this alone.

2. **The three real callers of NAV data race on the same schemes with zero
   cross-call de-duplication.** `confirm_import_route`'s background prefetch
   (`imports.py::_prefetch_member_nav_history`), `/holdings`'s
   `compute_holdings`, and `/allocation`'s `compute_allocation` (which itself
   calls `compute_holdings` again, `allocation.py:31`) all funnel through the
   same `get_navs_on_or_before` → `_fetch_nav_history` path in `nav.py` — and
   the frontend fires `/holdings` + `/allocation` together on mount
   (`Promise.all`) at essentially the same moment the background prefetch is
   also running, right after signup. `holdings.py`'s round-4 adversarial
   review already documented "no per-key single-flight coordination" as an
   **accepted, correctness-safe limitation at the holdings-cache level**
   (bounded to one redundant computation per TTL window) — but that
   assessment did not account for a *third* concurrent caller (the background
   prefetch) hitting the exact same schemes at exactly the exact same time,
   which triples the redundant network load specifically on the one load that
   matters most (the first one, when nothing is cached yet).

   Benchmarked live: simulating today's actual pattern (3 concurrent callers,
   new-client-per-request, no dedup) against 50 real scheme codes —
   representative of a multi-member family household — took **13.39s**. The
   same 50 codes with a shared client + a per-`amfi_code` single-flight
   de-dup took **0.69s** — roughly **19x**. This sandbox's link to
   `api.mfapi.in` is fast (~0.2-0.5s per request); production users almost
   certainly see higher per-request latency to the same public API, which is
   the most likely explanation for the reported ~30s (higher per-request
   latency multiplied by the same triplication/no-reuse pattern scales worse,
   not better).

Both findings live entirely inside `_fetch_nav_history`'s network-fetch leg in
`nav.py` — `get_nav_on_or_before`, `warm_nav_history`, and
`get_navs_on_or_before` all already call it as their only network seam, and
`imports.py`'s background prefetch calls `get_navs_on_or_before` too. Fixing
`_fetch_nav_history` itself transparently covers all three real callers with
**no changes needed to `imports.py`, `holdings.py`, or `allocation.py`**.

## Task

In `backend/app/services/dashboard/nav.py`, split `_fetch_nav_history`'s
current body into two layers, keeping the outer function's name and contract
(`async def _fetch_nav_history(amfi_code: str) -> list[tuple[date, Decimal]]`,
raises `httpx.HTTPError` on failure) exactly as-is, since every existing test
patches `nav._fetch_nav_history` directly by name and must keep passing
unmodified:

1. **Shared, connection-pooled client.** Replace the per-call
   `async with httpx.AsyncClient(timeout=30.0) as client:` with a
   module-level, lazily-created `httpx.AsyncClient` that's reused across every
   call for the lifetime of the process — same instance used by
   `get_nav_on_or_before`'s single-lookup path, `warm_nav_history`'s batch
   path, and `get_navs_on_or_before`'s batch path (they all go through
   `_fetch_nav_history`, so one change covers all three). Use
   `httpx.Limits(max_connections=..., max_keepalive_connections=...)` sized
   generously enough for a large multi-member household's peer-universe warm
   (`warm_nav_history` already documents 30-150+ schemes as the realistic
   upper bound) — your call on the exact numbers, but don't leave the default
   (`max_connections=100` is httpx's own default and is probably already
   fine; state your reasoning if you pick something else). Lazy creation
   needs to be safe if two coroutines race to create it at once (an
   `asyncio.Lock`-guarded double-checked pattern, or equivalent) — don't
   assume single-threaded ordering.
2. **Per-`amfi_code` single-flight de-dup**, inside the same
   `_fetch_nav_history` seam. If a fetch for a given `amfi_code` is already
   in flight when another caller asks for the same one, the second (and
   third) caller should await and share the first's in-flight result rather
   than starting a redundant network call — this is what collapses the
   3x-caller race (background prefetch + `/holdings` + `/allocation`) down to
   one real fetch per scheme instead of three. Scope this narrowly to
   `_fetch_nav_history`'s own network leg — do NOT touch `holdings.py`'s
   cache/generation/lock machinery or attempt the broader holdings-level
   single-flight primitive that round 4's adversarial review explicitly
   accepted as not worth building (see "Approaches considered and rejected"
   below for why this is a different, smaller thing). Clean up the in-flight
   registry entry once a fetch completes (success or failure) so it doesn't
   grow unbounded across the process lifetime.

Do not change `_fetch_nav_history`'s date-parsing, `Decimal` conversion, or
error-handling behavior — only the client-reuse and de-dup mechanics around
the HTTP call itself.

## Constraints

- **`Decimal`, never `float`** (CLAUDE.md non-negotiable) — this task doesn't
  touch numeric conversion logic, but don't introduce any `float` while
  refactoring the surrounding code.
- **Every existing test in `backend/tests/services/dashboard/test_nav.py`
  must keep passing unmodified** — they all patch
  `app.services.dashboard.nav._fetch_nav_history` directly (see that file),
  which fully replaces the function including whatever's inside it; your
  single-flight/shared-client logic lives *inside* the real
  `_fetch_nav_history`, so those tests exercise the mock, not your new code,
  and should be unaffected. Confirm this holds rather than assuming it.
- **This is local-dev-first, not the real fix** — same posture as
  `dashboard-nav-perf-handoff.md`: Fix C (the real ADR-006 EventBridge
  scheduled job) remains deferred to deployment phase. This task is a
  narrower, correctness-preserving optimization of the existing stand-in
  module, not an attempt to build that job.
- **Test-driven, always** — red/green/refactor. New tests needed:
  1. A test proving two concurrent calls to `_fetch_nav_history` for the
     *same* `amfi_code` result in only one real underlying HTTP call (mock/
     patch whatever you introduce as the actual network-calling seam one
     level below `_fetch_nav_history` — name it whatever's clearest, e.g.
     `_fetch_nav_history_uncached` or similar — and assert it's awaited
     exactly once even though `_fetch_nav_history` itself is awaited twice
     concurrently for the same code). Follow the existing
     `test_get_navs_fetches_network_legs_concurrently_then_caches_sequentially`
     pattern in the same file for how to deterministically force two
     concurrent calls to overlap (an `asyncio.Event` both sides wait on)
     rather than relying on timing.
  2. A test proving two concurrent calls for *different* `amfi_code`s both
     still result in two real underlying calls (i.e., the de-dup key is
     correctly scoped per-code, not global).
  3. A test proving the in-flight registry entry is cleaned up after
     completion — a third call for the same `amfi_code` *after* the first
     two have finished results in a fresh fetch, not a stuck/stale shared
     result.
  4. If practical without over-mocking, a test that the shared client is
     actually reused across calls (e.g., assert the same client object
     identity is used, or that a lazily-created client isn't recreated on a
     second call) — use your judgment on how deep to test this vs. treating
     it as an implementation detail; the single-flight behavior (1-3 above)
     is the part with an actual correctness contract worth testing directly.
- Full backend suite must stay green — confirm the actual current count with
  `pytest` before starting (documented as 362 passed / 2 skipped as of the
  most recent prior session, but treat that as stale and re-confirm).
- **Your sandbox has no network egress and cannot reach outside this dispatch
  worktree** — do not attempt to hit the real `api.mfapi.in` endpoint
  yourself; all of your tests must mock/patch, exactly like the existing test
  file already does. The live benchmark numbers above were gathered by the
  orchestrator outside your sandbox, not something you need to reproduce.

## Approaches considered and rejected

- **Holdings-level single-flight coordination (a per-`cache_key` lock/future
  in `holdings.py` so `/holdings` and `/allocation` share one
  `compute_holdings` computation)**: this is round 4's `dashboard-nav-perf-
  handoff.md` finding, explicitly accepted as a documented limitation rather
  than built — "a materially bigger primitive than anything built across
  rounds 1-4," not worth the complexity for this MVP. This task's
  `_fetch_nav_history`-level single-flight is deliberately a different,
  much smaller thing: it dedupes at the individual network-fetch granularity
  (per `amfi_code`), not at the whole-computation granularity (per member-set
  + date), and requires no interaction with `holdings.py`'s existing
  generation-counter/lock/TTL machinery at all. It closes the specific,
  newly-identified triplication (three independent callers × N schemes each)
  without reopening or relitigating the round-4 decision.
- **Switching to `api.mfapi.in`'s `/latest` endpoint for holdings' "current
  NAV" lookups instead of the full-history endpoint**: live-verified this
  endpoint exists and returns a much smaller single-entry payload, but
  rejected for this task — `get_previous_nav_from_cache` (today-vs-yesterday
  gain) and the Scorer's 3yr/5yr CAGR calculations both need historical NAV
  rows already sitting in the local cache, not just the latest value. Full-
  history fetch has to stay for correctness; the win here is purely
  connection-reuse + de-dup, which the benchmark already shows delivers the
  bulk of the available improvement without touching what data gets fetched.
- **A global `asyncio.Semaphore` capping total concurrent `mfapi.in` requests**:
  considered as a defense against a very large household (100+ schemes)
  overwhelming the remote API, but not mandated here — the shared client's
  own `httpx.Limits` already bounds concurrent connections, and adding a
  second, independent concurrency-limiting mechanism on top risks fighting
  itself for a scenario not yet observed as a real problem. Flag back if you
  see a concrete reason this is needed rather than adding it speculatively.

## Open questions

None outstanding. If the FIFO holdings test fixtures or CI environment reveal
a constraint on lazy shared-client creation (e.g., event-loop lifecycle
issues across test runs sharing one process) that isn't obvious from the
existing test file, describe what you find rather than inventing a new test
double pattern.
