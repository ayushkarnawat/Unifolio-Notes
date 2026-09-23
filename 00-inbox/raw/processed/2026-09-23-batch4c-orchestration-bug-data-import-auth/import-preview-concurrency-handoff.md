# Handoff: import-preview-concurrency

**Status:** DONE (implemented at `2a76b35`; round 1 adversarial review returned request-changes for a real `asyncio.gather`-introduced race in `get_scheme_list()` — fixed at `dd62cff` along with 1 of 2 requested test additions; scoped re-review of `dd62cff` approved, Major finding confirmed closed, both new tests confirmed non-tautological, scope confirmed clean, the one deliberately-skipped Minor test explicitly accepted as a non-blocking documented gap. Full backend suite 368 passed/2 skipped, independently verified by the orchestrator, zero regressions.)
**Parent plan:** none (direct diagnosis this session, sibling finding to
`nav-fetch-connection-reuse-handoff.md` — same overall investigation into
why the first dashboard load after signup/CAS import is slow, but a
different, earlier stage of the pipeline: the CAS-upload/preview step that
runs *before* the dashboard is even reached).

## Background

While diagnosing `nav-fetch-connection-reuse-handoff.md`'s dashboard-load
slowness, a second, independent bottleneck was found earlier in the same
end-to-end flow: the CAS upload → preview step (`POST /imports/preview`,
before the user even confirms and reaches the dashboard). Root-caused via
`superpowers:systematic-debugging` Phase 1, with live reproduction against
the real `api.mfapi.in` endpoint (network egress confirmed available):

1. **`build_import_preview` (`backend/app/services/import_/service.py:71`)
   resolves schemes in a fully sequential `for scheme in
   parse_result.schemes:` loop**, `await`-ing `client.resolve_scheme(...)`
   then `await client.get_scheme_category(...)` one scheme at a time. This
   is a *worse* pattern than `dashboard-nav-perf-handoff.md`'s pre-Fix-B
   holdings code — there's no `asyncio.gather` at all here, not even a
   partial one.
2. **`MfApiClient._get_json` (`backend/app/services/import_/enrich.py:61`)
   opens a brand-new `httpx.AsyncClient()` per call**, the same
   no-connection-reuse pattern as `nav.py`'s `_fetch_nav_history` before
   its fix.
3. **`get_scheme_category` fetches the full `/mf/{amfi_code}` endpoint**
   (the entire historical NAV history, e.g. 3000+ rows) just to read one
   field, `meta.scheme_category`/`meta.schemeCategory`, and discards
   `data` entirely. Unlike `nav.py`'s case (where `dashboard-nav-perf-
   handoff.md` correctly kept full-history fetches because holdings/Scorer
   genuinely need historical NAV rows), **this caller only ever reads
   `meta`** — `api.mfapi.in`'s `/mf/{code}/latest` endpoint returns the
   identical `meta` block with a tiny single-entry payload instead of the
   full history, live-confirmed via curl.

Live-benchmarked (this sandbox has network egress to `api.mfapi.in`,
confirmed, not assumed): 30 real scheme codes, sequential + new-client-per-
call + full-history (today's pattern) took **7.74s**. The same 30 codes,
concurrent (`asyncio.gather`) + one shared client + the `/latest` endpoint,
took **0.31s** — roughly **25x**. `get_scheme_category` already disk-caches
per-scheme results for 24h (`SCHEMES_TTL`), so this cost is paid in full
only on a scheme's *first* sighting across all users — which is exactly the
signup/first-CAS-import case the user is complaining about, where every
scheme in the household's portfolio is being resolved for the first time.

## Task

Two changes, both inside `backend/app/services/import_/`:

1. **`enrich.py`: shared, connection-pooled client + `/latest` for
   category lookups.**
   - Replace `MfApiClient._get_json`'s per-call
     `async with httpx.AsyncClient(timeout=30.0) as client:` with a lazy,
     race-safe shared client, reused across every call for the process
     lifetime — same shape as `nav-fetch-connection-reuse-handoff.md`'s
     fix to `nav.py` (a double-checked lazy-init guard safe against two
     coroutines racing to create it). Do not share the *same* client
     instance across `enrich.py` and `nav.py` — keep them as two separate
     module-level clients, one per module, to avoid coupling two otherwise
     -independent services' lifecycles together for no real benefit.
   - In `get_scheme_category`, switch the network call from
     `f"{MFAPI_BASE}/mf/{amfi_code}"` to `f"{MFAPI_BASE}/mf/{amfi_code}/latest"`.
     Confirm the response shape is compatible: live-verify (curl or a
     one-off script) that `/latest`'s `meta` block has the same
     `scheme_category`/`schemeCategory` fields as the full endpoint — the
     diagnosis above assumed this holds but you should re-confirm it
     yourself rather than trust the assumption blindly, per this project's
     debugging discipline. `resolve_scheme`'s `get_scheme_list` call
     (the full `/mf` scheme directory) is unrelated and must NOT be
     touched — that endpoint has no `/latest` equivalent and isn't part of
     this bottleneck.
   - Existing per-scheme disk cache (`{cache_dir}/{amfi_code}_meta.json`,
     24h TTL) stays exactly as-is; you're only changing what URL populates
     it, not the caching mechanics.

2. **`service.py`: parallelize the per-scheme resolution loop.**
   - In `build_import_preview`, replace the sequential `for scheme in
     parse_result.schemes:` loop's network-calling portion
     (`client.resolve_scheme` + `client.get_scheme_category`) with an
     `asyncio.gather`-based concurrent fetch, then a second, ordinary
     sequential pass to build `key_to_temp` and `scheme_previews` in the
     original input order (`asyncio.gather` preserves result-list order
     matching the input list, so this is a mechanical split, not a
     reordering). `temp_id = uuid.uuid4().hex[:12]` generation and
     `key_to_temp` dict population have no network dependency and can stay
     in whichever pass is simplest — your call, as long as final output
     order and `session_id`/dict contents are unchanged for identical
     input.
   - Do not touch `confirm_import` — it's synchronous, DB-only, and
     entirely unrelated to this network-bound preview step.

## Constraints

- **`Decimal`, never `float`** (CLAUDE.md non-negotiable) — this task
  doesn't touch numeric conversion logic at all (scheme resolution is
  string/metadata only), but don't introduce any `float` while
  refactoring.
- **Every existing test in `backend/tests/services/import_/test_service.py`
  and `backend/tests/services/import_/test_enrich.py` (if it exists —
  check) must keep passing unmodified.** `test_service.py`'s tests already
  mock at the whole-`MfApiClient`-instance level
  (`client = AsyncMock()`; `client.resolve_scheme.side_effect = ...`), so
  a `service.py` refactor to `asyncio.gather` should be transparent to
  them — confirm this holds rather than assuming it.
  `test_confirm_import_rejection_writes_nothing_even_for_earlier_confident_scheme`
  specifically exercises a confident + ambiguous scheme pair and checks
  behavior *after* `build_import_preview` — your refactor must preserve
  `scheme_previews` list ordering (matching `parse_result.schemes` input
  order) since that test's fixture ordering matters for which temp_id maps
  to which scheme.
- **This is local-dev-first, not the real fix** — same posture as the
  sibling `nav-fetch-connection-reuse-handoff.md`: no AWS/production
  deployment changes, this is a narrower correctness-preserving
  optimization of the existing module.
- **Test-driven, always** — red/green/refactor. New tests needed:
  1. A test proving `build_import_preview` resolves multiple schemes
     concurrently rather than sequentially (mock `client.resolve_scheme`/
     `client.get_scheme_category` with an `asyncio.Event`-based overlap
     check, same pattern as `nav.py`'s existing
     `test_get_navs_fetches_network_legs_concurrently_then_caches_sequentially`
     test — force two schemes' resolution to overlap in time and assert
     both started before either finished, rather than relying on timing).
  2. A test proving output ordering is preserved: multiple schemes with
     distinguishable resolution results (e.g. different confidences/
     categories) come back in `scheme_previews` in the same order as
     `parse_result.schemes`, even when an earlier-indexed scheme's mock
     resolves *after* a later-indexed one (use an `asyncio.Event`/delay to
     force this ordering inversion so the test can't pass by accident).
  3. A test in `enrich.py`'s own test file proving `get_scheme_category`
     calls the `/latest` URL, not the full-history URL — mock/patch
     `_get_json` and assert the URL argument.
  4. A test proving `enrich.py`'s shared client is lazily created once and
     reused across multiple `_get_json` calls (same judgment call as
     `nav-fetch-connection-reuse-handoff.md`'s test 4 — test this if
     practical without over-mocking, treat as an implementation detail
     otherwise, prioritize tests 1-3 which have actual correctness
     contracts).
- Full backend suite must stay green — confirm the actual current count
  with `pytest` before starting (this worktree's `tests/services/import_`
  subtree alone was 74 passed just before this task was written; treat
  that as a starting baseline, not the target, and re-run the full suite
  before calling this done).
- **Your sandbox has no network egress and cannot reach outside this
  dispatch worktree** — do not attempt to hit the real `api.mfapi.in`
  endpoint yourself for testing; all of your tests must mock/patch, like
  the existing test files already do. You may still need to *reason about*
  what `/latest`'s response shape looks like from this doc's description
  above (mirrors `meta`, single-entry `data`) — the orchestrator has
  already live-confirmed this out-of-sandbox; describe if anything you
  find in the existing code contradicts that assumption rather than
  guessing further.

## Approaches considered and rejected

- **Switching `resolve_scheme`'s `get_scheme_list` (the full `/mf` scheme
  directory fetch) to some smaller endpoint**: no such endpoint exists on
  `api.mfapi.in` — the full scheme directory is a single flat list
  covering all ~20,000+ schemes with no filtering/pagination options, and
  this call is already disk-cached for 24h (`SCHEMES_TTL`) and only fires
  once per household regardless of scheme count (it fetches the *whole*
  directory once, then fuzzy-matches locally against it in-memory,
  `fuzzy_match_scheme`) — not a per-scheme cost, so not part of this
  bottleneck at all.
- **Sharing one `httpx.AsyncClient` between `nav.py` and `enrich.py`**:
  considered for simplicity, rejected — these are two independently-scoped
  services (Dashboard Service vs. Import Service per this module's own
  docstring) with no other coupling; sharing a client instance would tie
  their process lifecycles together and complicate testing (mocking one
  module's client would leak into the other's tests) for no measurable
  benefit, since both are cheap, independent lazy singletons either way.
- **Batching multiple schemes into a single `api.mfapi.in` request**: no
  such batch endpoint exists on this public API — confirmed via the same
  live exploration used for the `/latest` finding. `asyncio.gather`-based
  concurrency over the existing per-scheme endpoint is the only available
  lever.

## Open questions

None outstanding. If `/latest`'s `meta` block turns out NOT to match the
full endpoint's `meta` block for some scheme category edge case (e.g. a
discontinued/merged scheme), describe what you find rather than silently
falling back to the full endpoint — that would defeat the fix's purpose
for exactly the schemes where it matters (a fresh household's full scheme
list, including possibly-unusual/older schemes).
