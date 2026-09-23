# Architectural gap: two parallel, disconnected CAS-import backends

**Identified:** 2026-09-03, during the mandatory adversarial-review gate for the
non-PAN duplicate-person-detection task (see
`Docs/orchestration/non-pan-duplicate-person-detection-handoff.md`).
**Status:** Resolution decided by user (option a below); implementation tracked in
that same handoff doc's "Resolution round 2" section.

## How it was identified

The non-PAN dedup task built Case 1 (folio-based member attribution) and Case 2
(cross-account duplicate advisory) entirely inside
`backend/app/services/import_/attribution.py`, called from
`backend/app/services/import_/lifecycle_service.py`, routed under
`/cas-imports/*` (`backend/app/api/cas_imports.py`). The handoff doc's own design
assumed this was "the" import backend and that `MISMATCH_CONFIRMATION_REQUIRED`
was already a live, enforced confirmation gate that Case 1 could feed into.

The mandatory adversarial-review gate (run before marking the task DONE, per
`CLAUDE.md`'s model-orchestration skill) caught both assumptions as wrong:

1. **The production import UI never calls this code path at all.** Desktop
   (`frontend/src/features/import/ImportFlow.tsx`) and mobile
   (`frontend/src/mobile/features/import/MobileImportView.tsx`) call
   `frontend/src/features/import/api.ts`'s `parseImport`/`confirmImport`, which
   hit `${API_BASE_URL}/imports/parse` and `${API_BASE_URL}/imports/confirm` —
   routed by `app/main.py` to `backend/app/api/imports.py`, which calls
   `build_import_preview`/`confirm_import` from
   `backend/app/services/import_/service.py`. Grepped: zero references to
   `resolve_attribution` or `detect_cross_account_duplicate` anywhere in
   `service.py`. Meanwhile `frontend/src/features/import/ImportLifecycleView.tsx`
   — the UI apparently meant to consume `/cas-imports/*` — is referenced only by
   its own test file. No production component renders it, no route mounts it.
   This session's entire non-PAN dedup build landed on a backend with no
   reachable frontend, while the actual user-facing import flow shipped none of
   it.

2. **The confirmation gate this task assumed existed was already dead before
   this task touched anything.** `AttributionStatus.MISMATCH_CONFIRMATION_REQUIRED`
   / `AttributionDecision.requires_confirmation` had (and has) zero consumers
   anywhere in the codebase. `resolve_attribution`'s own docstring states an
   explicit invariant — *"No commit without either clean match or explicit user
   confirmation"* — that both of `lifecycle_service.py`'s call sites
   (`create_cas_import` line 239, `retry_cas_import_password` line 294) already
   violated before this task started:

   ```python
   attribution = resolve_attribution(db, user_id, household_member_id, parse_result)
   target_member_id = attribution.resolved_member_id or household_member_id
   ```

   This doesn't just skip *asking* for confirmation — when `resolve_attribution`
   finds a *different* matching member than the one the caller selected
   (`MISMATCH_CONFIRMATION_REQUIRED`), `resolved_member_id` is that other
   member's ID, and the code silently attributes the import to them, with no
   pause and no record that a mismatch was ever detected. The gate wasn't just
   unused — the one function guarded by it was actively bypassing it.

## What caused it to arise

Confirmed via `git log --oneline --diff-filter=A` per file, then
`git log -1 --format="%ad | %s" --date=short` on each first-introduction commit:

| Commit | Date | What it added |
|---|---|---|
| `5c81231` / `1e823d1` | 2026-08-04 | `service.py` / `app/api/imports.py` — parse-preview + confirm orchestration against the real schema (FR-9-11) |
| `038342a` | 2026-08-05 | `ImportFlow.tsx` wired to `/imports/*` |
| `4d60c8e` | 2026-08-10 | `lifecycle_service.py` + `cas_imports.py` + `attribution.py` (backend) |
| `e7db4c1` | 2026-08-10 | `ImportLifecycleView.tsx` (frontend) |

`lifecycle_service.py` is a newer, more capable rewrite of `service.py` — it adds
an encrypted-buffer cache for password retries, member attribution, and a richer
`ImportStatus` state machine that `service.py` never had. It was built, and its
own frontend (`ImportLifecycleView.tsx`) was built alongside it the same day, but
the cutover from `ImportFlow.tsx`/`/imports/*` to `ImportLifecycleView.tsx`/
`/cas-imports/*` was never completed — `ImportFlow.tsx` was never repointed, and
`ImportLifecycleView.tsx` was never mounted into any route or parent component.

Both backends kept working in isolation — `/imports/*` because it's what real
users (and every manual/localhost test) actually exercise, `/cas-imports/*`
because nothing calls it, so it can't fail visibly — for roughly 3.5 weeks
(2026-08-10 to 2026-09-03) without the split being noticed. Per the user's own
description of how this surfaced: *"on localhost everything seems to be
working"* — because the working path (`/imports/*`) genuinely does work; the gap
was invisible precisely because nothing exercised the abandoned path enough to
show it was disconnected. It took a task that specifically targeted
`lifecycle_service.py`, followed by an independent adversarial-review pass that
checked the actual production call chain rather than trusting the task's own
stated scope, to surface it.

## How it is being resolved

User decision, 2026-09-03: **option (a)** — wire the dedup logic (Case 1 folio
match + Case 2 cross-account advisory) and the confirmation gate into
`service.py`/`/imports/*`, the currently-live production path, rather than
cutting the frontend over to `ImportLifecycleView.tsx`/`/cas-imports/*`
(rejected — no appetite to switch a working, exercised path for an unexercised
one) or leaving `/imports/*` as a documented-but-unfixed gap (rejected — the
production path is exactly where real users are affected).

As part of the same round, `lifecycle_service.py`'s two call sites are also
fixed to route through the same shared confirmation-gate helper — this is a
near-zero-incremental-cost fix once the helper exists in
`attribution.py` (ponytail's "fix once, where all callers route through"
doctrine: the alternative, patching `service.py` only and leaving
`lifecycle_service.py`'s invariant violation in place, would mean the same class
of bug exists twice in the codebase for no reason other than which file happened
to get attention first). `ImportLifecycleView.tsx` still has no production call
site, so no frontend follow-up is needed there — only the backend invariant
gets closed.

See `Docs/orchestration/non-pan-duplicate-person-detection-handoff.md`'s
"Resolution round 2" section for the concrete wiring design, and
`Docs/orchestration/delegation-log.md` for the dispatch record.

## Why this wasn't caught earlier

- No integration test exercises the actual route-to-frontend wiring — existing
  tests hit `service.py`/`lifecycle_service.py` directly, or hit
  `ImportFlow.tsx`/`ImportLifecycleView.tsx` directly, never end-to-end through
  a browser-driven "which component does the app actually render" check.
- The original non-PAN dedup handoff doc (written by the orchestrator, this
  session) named `lifecycle_service.py` as the target without first confirming
  it was the production path — an assumption stated as fact instead of verified.
  This is a process gap in how handoff docs get written, not just a one-off
  mistake: a handoff doc that names a specific file as "the" implementation
  target should say how that was confirmed (grep for the frontend call site,
  or a route/main.py mount check), not just name the file that looked most
  relevant to the task's stated scope.
