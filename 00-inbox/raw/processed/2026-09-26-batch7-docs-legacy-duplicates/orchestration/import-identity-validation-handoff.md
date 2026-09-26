# Handoff: import-identity-validation

**Status:** DONE
**Parent plan:** `Docs/orchestration/bug-001-data-001-implementation-prompt.md` (Item 7)

## Task

DATA-001 finding: `enrich.py`'s `resolve_scheme()` accepted a CAS-supplied
AMFI code paired with the CAS-supplied scheme name at confidence 1.0 with
zero cross-check between them, and `confirm_import()` in `service.py`
persisted `Scheme.name` from CAS-parsed data regardless of whether a
user-supplied override corrected the `amfi_code` — a legitimate manual
correction could still produce a `Scheme` row whose `name` doesn't match
its own `amfi_code`. Also folded in a combined fix for CLAUDE.md's
pre-existing "Still open" item 2 ("no server-side 409 backstop on
plan-type override") per the implementation prompt's explicit direction,
since it's the same class of gap (an override field trusted with zero
validation) in the same function.

Implemented directly as orchestrator (no Codex dispatch) — diff is
small-to-moderate (2 source files, ~40 net new lines), both files were
already fully loaded in context from the investigation phase, and a fresh
handoff/dispatch/wait round-trip would have cost more turns than fixing
inline. Per `model-orchestration`'s "Review-loop fix authorship" section,
the mandatory adversarial-review gate still applies unchanged.

**Changes:**

1. `enrich.py::resolve_scheme()` — now always fetches the AMFI master
   list first (instead of short-circuiting on `amfi_from_cas` before ever
   touching it). When `amfi_from_cas` is present, looks up that code's
   canonical name via a new `_canonical_name_for_code()` helper and
   requires similarity ≥ 0.92 (reusing the existing `_normalize_name` +
   `SequenceMatcher` idiom, same bar as the existing fuzzy-match path)
   before confirming at confidence 1.0. An unresolvable code or an
   implausible pairing falls through to the existing fuzzy-match-by-name
   path rather than blindly trusting the CAS-supplied pairing. Added
   `cached_scheme_list()` — a synchronous peek at whatever the async
   `get_scheme_list()` already fetched this process — so `confirm_import()`
   (synchronous, unlike `build_import_preview()`) can reuse the same
   cross-check without itself becoming async.

2. `service.py::confirm_import()` — in the existing up-front validation
   loop (before any DB writes):
   - An override `amfi_code` not found anywhere in the cached master list
     now raises `SchemeConfidenceError` (409) — a data-entry error, not a
     legitimate correction. Only checked when the master list is already
     cached this process (populated by the preceding `build_import_preview`
     call); a cold cache degrades to the pre-fix trusting behavior rather
     than blocking the confirm on a lookup this sync function can't itself
     perform.
   - A `plan_type_override` that contradicts the scheme's own CAS-parsed
     `plan_name_variant` (an unambiguous, name-derived signal, unlike the
     ARN-derived `preview.plan_type` an override exists to correct) now
     also raises `SchemeConfidenceError` — closes CLAUDE.md's item 2.

   In the write loop, when a NEW `Scheme` row would be created with an
   override-supplied `amfi_code`: if the override code's canonical name is
   NOT plausibly similar (< 0.92) to the CAS-parsed name, persists the
   canonical name instead of the stale CAS-parsed one — the concrete
   name/code mismatch bug.

## Constraints

- TDD: failing test first (both `test_enrich.py` and `test_service.py`
  additions were RED before the implementation, confirmed via a scoped
  pytest run each).
- `Decimal`, never `float` — not applicable here (no money/units/NAV
  values touched; `SequenceMatcher.ratio()` floats are fuzzy-match
  confidence scores, the same category as the pre-existing
  `match.confidence`/`MIN_MATCH_CONFIDENCE` floats elsewhere in this
  module, not a money-path value).
- Full backend suite: 410 passed, 2 skipped (was 401/2 before this task;
  +9 new tests: 3 net-new in `test_enrich.py`, 6 net-new in
  `test_service.py`). `tsc -b --noEmit` clean (frontend untouched).
- One pre-existing integration test
  (`test_imports_routes.py::test_parse_then_confirm_lands_a_transaction_in_the_real_db`)
  had to be updated: it mocked `MfApiClient._get_json` to always return the
  category-lookup payload, relying on the old "amfi_from_cas short-circuits
  without fetching the scheme list" behavior this fix deliberately removes.
  Updated to a URL-dispatching fake returning the scheme-list shape for the
  `/mf` endpoint and the category shape for `/mf/{code}/latest`.
- Also cleared a stale on-disk `.cache/mfapi/schemes.json` (gitignored,
  generated artifact) that a pre-fix test run had poisoned with the wrong
  payload shape — the real `MfApiClient` singleton's 24h disk cache means a
  wrong payload written once can silently corrupt every later run within
  the TTL. Not otherwise touched; this is an existing test-isolation smell
  (that integration test uses the real default cache dir, not `tmp_path`)
  that pre-dates this fix and is out of scope to harden further here.

## Approaches considered and rejected

- **Converting `confirm_import()`/`confirm_import_route()` to `async def`**
  to do a live `MfApiClient` lookup for the override's canonical name.
  Rejected: the master list is already fetched (and cached in-process) by
  the immediately-preceding `build_import_preview()` call in the normal
  flow, so a synchronous cache peek (`cached_scheme_list()`) gets the same
  answer without an async conversion that would also touch ~10 existing
  synchronous test call sites. Trade-off: a cold cache (e.g. a fresh
  process/restart between preview and confirm) degrades to the pre-fix
  behavior rather than doing a live lookup — accepted as a documented
  limitation, not a live risk in the normal single-request flow.
- **Extending `SchemeConfirmation` with a frontend-supplied scheme-name
  field** instead of a backend canonical-name lookup. Rejected: out of the
  prompt's stated file scope (only `enrich.py` and `service.py`), and would
  require a frontend contract change this pass doesn't otherwise touch.
- **Raising `amfi_ter_client.py`'s `MIN_MATCH_CONFIDENCE`** (the third
  matcher the findings doc flagged as "the same underlying validation gap
  surfacing in two call sites"). Not changed this pass: that matcher pairs
  an *already-persisted, already-validated* local `Scheme.name` against
  AMFI's TER-feed scheme-name field for TER lookups — a different
  architectural role from import-time identity binding (which schemes exist
  and what they're named in the first place). Its existing threshold is
  already justified in its own file docstring by a live-measured
  similarity-score margin (0.55 sits between a real ~0.67 match and an
  unrelated ~0.26 pair). Revisit only if a concrete TER-mismatch is
  observed in production; not touched here to avoid an unverified
  threshold change with no repro.

## Round 2 (review findings, commit e43391a)

Adversarial review of `40754dc` returned REQUEST-CHANGES: 2 Medium, 3 Low.
All fixed:

- **Medium** — the `plan_type_override` 409 backstop trusted
  `classify_plan_from_name`'s loose whole-name substring match as an
  absolute veto; a base scheme name merely containing "Direct"/"Regular"
  outside the actual plan designator could block a legitimate override.
  Fixed: the backstop now also requires the scheme's own name to contain
  the literal `"Direct Plan"`/`"Regular Plan"` phrase (regex-anchored,
  `\b(DIRECT|REGULAR)\s+PLAN\b`) matching the parsed variant before it
  fires — `parser.py`'s shared `classify_plan_from_name` itself was left
  untouched (out of this task's file scope, and used elsewhere for a
  looser best-effort purpose where that trade-off is already accepted).
- **Medium** — the stale `.cache/mfapi/schemes.json` this session already
  deleted once had recurred, because the integration test's
  `MfApiClient._get_json` mock still wrote through the module-level
  `mfapi_client` singleton's real, non-`tmp_path` cache dir. Fixed at the
  root: the test now patches `mfapi_client.cache_dir` to `tmp_path` and
  resets `_schemes` to `None` for the duration of the test, so it can no
  longer write into (or read stale data from) the shared cache dir.
  Confirmed empty after a full suite run.
- **Low** — `SequenceMatcher("", "").ratio()` returns `1.0`; a
  blank/punctuation-only name (post-normalization) could "confirm" a
  match at full confidence. Fixed in both `resolve_scheme`'s new
  cross-check and the pre-existing `fuzzy_match_scheme` (same root cause,
  same file — fixed once, not just at the new call site).
- **Low** (no action) — `parsed_scheme_by_key`'s once-per-call
  construction confirmed functionally equivalent to the replaced scan,
  no DB-write race (`confirm_import` is synchronous, `ParseResult` isn't
  mutated).
- **Low** (no action, already documented) — the cold-cache bypass is the
  same accepted, already-documented limitation from Round 1.

TDD: RED confirmed for both new regression tests before their fixes.
Full suite: 412 passed, 2 skipped (was 410/2).

## Closing review (commit e43391a)

Scoped closing re-review returned **APPROVE, zero findings**. Confirmed:
the anchored-designator fix closes the false-positive gap without
reopening the original vulnerability; the `tmp_path`/`_schemes=None`
patch genuinely isolates the integration test from the real disk cache;
both `SequenceMatcher` call sites in `enrich.py` are guarded (no third
site missed); `parsed_scheme_by_key` and the cold-cache bypass remain
safe. Noted `git diff --stat 40754dc e43391a` spans 6 files because of
the intervening `c4318fc` delegation-log commit — `e43391a` itself
touches exactly the 5 expected files. Codex's sandbox couldn't run
pytest (no writable temp dir); not a gap — the orchestrator had already
independently run the full suite green (412 passed, 2 skipped) before
dispatch.

**Item 7 is DONE.**

## Open questions

None outstanding — flag in review if the reviewer sees a gap in this
reasoning.
