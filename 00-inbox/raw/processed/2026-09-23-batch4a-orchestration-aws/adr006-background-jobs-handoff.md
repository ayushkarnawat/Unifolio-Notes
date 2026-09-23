# Handoff: adr006-background-jobs

**Status:** DONE (2026-09-03)
**Parent:** `CLAUDE.md` Session State "F4" / ADR-006 (EventBridge Scheduler background jobs) / `AWS Readiness/aws-golive-launch-blockers.md`
**Dispatch mode:** User is running this directly in their own Codex CLI/app session (not via Claude's `codex:codex-rescue` Agent dispatch) — this doc is the source of truth both sides read; update `Status` here after Codex finishes and report back.

## Task

F4 splits into two genuinely different pieces (user-confirmed 2026-09-02). **This handoff covers piece 1 only** — backend job code, fully buildable now, no AWS dependency. Piece 2 (the actual EventBridge Scheduler + ECS Fargate Terraform) is deliberately out of scope here; it gets authored later, at the infra-authoring phase, once an AWS account/ECR/ECS cluster exist to schedule against.

Build 4 standalone job-entrypoint scripts under `backend/scripts/jobs/` (new subdirectory — the existing `backend/scripts/` convention is flat, but 4 new files sharing one purpose warrant their own subfolder rather than cluttering the flat list; don't over-think this, it's one `mkdir`). Each script follows the exact shape of `backend/scripts/seed_dev_household_member.py`: `sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))` (one extra `.parent` — these live one directory deeper), `from app.db.session import SessionLocal`, a `def main() -> None:` doing the real work inside `with SessionLocal() as db:`, `if __name__ == "__main__": main()`. Each wraps an **already-existing, already-tested** lazy-fetch/refresh function — none of these 4 need new fetch/parse logic, only a new caller and (for NAV only) a new universe query.

1. **`backend/scripts/jobs/refresh_nav_daily.py`** — wraps `warm_nav_history(db, schemes)` (`app/services/dashboard/nav.py:167`). No existing "give me every scheme that needs a NAV refresh" query exists anywhere in the codebase (checked: `holdings.py`, `category_ranking.py`, `cash_flow.py` all build scheme sets scoped to one household/category, not a global one). Build the universe as **every `Scheme` referenced by at least one `Folio`** — i.e. actually held by some user — not every row in the `schemes` reference table:
   ```python
   from sqlalchemy import distinct
   from app.models.folio import Folio
   from app.models.reference import Scheme

   schemes = (
       db.query(Scheme)
       .join(Folio, Folio.scheme_id == Scheme.id)
       .filter(Scheme.id.in_(db.query(distinct(Folio.scheme_id))))
       .all()
   )
   ```
   (the `.filter(...in_(distinct(...)))` avoids duplicate `Scheme` rows from the join without needing `.distinct()` on the full row, which can be slower on wide tables — but if Codex finds a cleaner equivalent, e.g. a plain `.distinct()`, that's fine, it's not a load-bearing detail). **Why held-only, not the full AMFI catalog**: `warm_nav_history` fetches a scheme's *full* NAV history per call — unlike TER/AAUM (item 2/3 below), which upsert one row per scheme per month across the *entire* reference table cheaply. Running that same "every known scheme" sweep daily for NAV would mean full-history fetches for thousands of schemes nobody holds — wasteful and slow for no benefit (Category Ranking/Scorer's peer-universe warming already handles on-demand NAV needs for unheld schemes via the existing `warm_nav_history` call sites). Call `await warm_nav_history(db, schemes)` — it already handles batching, the 15-minute warm-TTL dedup, and its own commit.

2. **`backend/scripts/jobs/refresh_ter_monthly.py`** — wraps `refresh_ter_data(db)` (`app/services/analytics/amfi_ter_client.py:275`). Already scoped to every locally-known resolved-plan scheme internally — the job script is a thin `await refresh_ter_data(db)` call, nothing else. Already has a live caller (`ter.py:146`, lazy/on-demand) — this job adds a proactive monthly path alongside it, doesn't replace it.

3. **`backend/scripts/jobs/refresh_aaum_quarterly.py`** — wraps `refresh_aaum_data(db)` (`app/services/analytics/amfi_aaum_client.py:127`). **This function currently has zero production callers anywhere in `app/`** (confirmed via grep — only test code invokes it) — this job script is the fix that wires it into a real caller, per F4's original finding. Thin `await refresh_aaum_data(db)` call.

4. **`backend/scripts/jobs/refresh_benchmark_daily.py`** — wraps `ensure_index_history_fresh(db, index, start_date, end_date)` (`app/services/analytics/nse_indices_client.py:104`), called once per `BenchmarkIndex` enum member (4 members: `NIFTY_50`, `NIFTY_500`, `NIFTY_LARGEMIDCAP_250`, `NIFTY_MIDCAP_150` — iterate `BenchmarkIndex` directly, don't hardcode the list, so a future 5th index needs no job-script edit). **Date range, resolved 2026-09-03 (was an open question, now locked)**: `start_date` = a fixed **10 calendar years** back from `end_date`, `end_date = date.today()`. Reasoning: `benchmark.py` itself derives its actual comparison window from the portfolio's earliest transaction date (unbounded, not a fixed duration), so it doesn't imply a concrete number on its own — the 10-year figure instead comes from product intent (investing horizon here is framed in years, not a 1-2yr window) and from consistency with this job's own NAV-history sibling, which pulls full/long-run history by default. Use a real calendar-year subtraction, not a naive `days=3650`, to correctly land on the same month/day 10 years prior including leap-year handling — e.g. `start_date = end_date.replace(year=end_date.year - 10)`, with the standard Feb-29-on-a-non-leap-year fallback (step back one more day) if that edge case isn't already handled by a helper elsewhere in this codebase (check first, don't duplicate one that already exists). `ensure_index_history_fresh` already no-ops cheaply if the cache already covers the requested range, so calling it daily with a wide fixed range is safe and correct, not wasteful — a 10-year first-run fetch happens once, every subsequent daily run only pulls the new day(s).

For all 4: use `commit_off_loop`-safe `asyncio.run(main_async())` pattern (an `async def main_async(db)` called via `asyncio.run()` inside `main()`) since 3 of the 4 wrapped functions are `async def` and the codebase's own convention (`app/db/session.py`'s `commit_off_loop`) assumes a running event loop — `asyncio.run()` guarantees that. Log a one-line summary at the end of each script (schemes/rows touched, success/failure) via the stdlib `logging` module matching the existing `logger.info(...)` style already used in `nav.py`/`amfi_ter_client.py` — this is what an EventBridge/CloudWatch Logs consumer will read later, so make it grep-able, not decorative.

## Constraints

- Do not touch `warm_nav_history`, `refresh_ter_data`, `refresh_aaum_data`, or `ensure_index_history_fresh` themselves — all 4 are already correct, tested, and in production use (except AAUM's caller gap, which this task fixes by adding a caller, not by editing the function). This task is purely "add an invocable entrypoint," not "change fetch/refresh logic."
- Decimal, never float, in any money/NAV-adjacent code path — none of these 4 scripts do their own math (they delegate entirely to the wrapped functions), so this should be a non-issue, but don't introduce any incidental float coercion while writing the universe query or logging.
- Follow the `backend/scripts/seed_dev_household_member.py` shape exactly (see Task section) — don't invent a new `app/jobs/` package or a shared base-class/framework for "a job" across the 4 scripts. Four short, similar, boring scripts are correct here (YAGNI on the abstraction — there's no second call site or config-driven registry that would justify one).
- Each script must be independently runnable (`python backend/scripts/jobs/refresh_nav_daily.py`) and exit non-zero on an unhandled exception (default Python behavior — don't add a broad `try/except` around `main()` that swallows failures; a future EventBridge/ECS task needs a real non-zero exit code to know the run failed, since all 4 wrapped functions already degrade gracefully internally for *expected* failure modes like a network blip).
- Run the full backend test suite after adding these — must stay green (additive-only change, nothing here should touch existing tests). Add one small test per script (per this project's "non-trivial logic leaves one runnable check" convention) — e.g. mock the wrapped function (`warm_nav_history`/`refresh_ter_data`/etc.) and assert `main()` calls it with the expected arguments (the NAV job's universe query is the one piece worth a real assertion — a test seeding 2 folios referencing 2 schemes plus 1 unheld scheme, asserting only the 2 held schemes are passed to `warm_nav_history`).

## Approaches considered and rejected

- **NAV job sweeping every `Scheme` row (matching TER/AAUM's "all locally-known schemes" pattern)** — rejected; see the reasoning in item 1 above (full-history fetch cost is not the same shape as TER/AAUM's cheap one-row-per-scheme-per-month upsert).
- **A shared `app/jobs/` package with a common `BaseJob` class** — rejected per YAGNI; 4 near-identical thin wrapper scripts don't need a shared abstraction, especially with piece 2 (the actual scheduling mechanism) not yet built — premature to design a job framework before knowing exactly how EventBridge will invoke these (one Fargate task per job? one task running all 4 sequentially via a dispatcher argument? that shapes whether a shared entrypoint pattern is even useful, and isn't decided yet).
- **Wiring AAUM's new caller into an existing lazy on-demand path (like TER's)** instead of a scheduled-only job — rejected; AAUM data changes quarterly (matches the AMFI feed's own cadence), so unlike NAV/TER there's no user-facing "click and wait" moment where on-demand fetch-then-cache makes sense — proactive-only is the right shape here, no fallback lazy path needed.

## Open questions

- ~~The benchmark job's lookback window~~ — **Resolved 2026-09-03: 10 calendar years, fixed.** See item 4 above.
- Confirm during implementation whether any of the 4 wrapped functions' commit behavior (`commit_off_loop` vs. a plain `db.commit()`) changes when called from a fresh top-level `asyncio.run()` vs. their existing callers (an in-flight FastAPI request) — should be a non-issue per `commit_off_loop`'s existing "safe under any running event loop" contract, but worth a sanity check in the new tests rather than assuming.

## Review-gate note (2026-09-03, orchestrator)

Independently reran the full backend suite (not just Codex's self-report) after the F8/non-PAN-dedup flake investigation landed alongside this: 600 passed/6 skipped/0 failed, clean. Mandatory adversarial-review gate: **PASS, zero findings** — standalone-script shape, held-only NAV scope, 10-year leap-safe benchmark lookback, wrapped functions unmodified, grep-able logging, non-zero exit on unhandled exceptions all confirmed. Status moved to DONE.
