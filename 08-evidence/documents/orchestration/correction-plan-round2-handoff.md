# Handoff: correction-plan-round2

**Status:** DONE

**Review history:** Round 1 adversarial review (2026-08-19) returned REQUEST-CHANGES with 1 Medium (`compute_fund_vs_benchmark`'s early-return guard checked only the switch-excluding `_investment_transactions()` list before `_fund_level_transactions()` was ever queried, so a switch-only household — no PURCHASE/PURCHASE_SIP/REDEMPTION/DIVIDEND_PAYOUT at all — got zero fund rows despite Fix 4's entire purpose being to surface switch-based fund-level XIRR) and 1 Low (`HoldingsTable.test.tsx`'s `console.error` spy restoration wasn't in a `try/finally`). Both fixed directly by the orchestrator (small diff, files already in context — "Review-loop fix authorship"): `benchmark.py` now queries `fund_level_transactions` before the early-return guard and gates on `not transactions and not fund_level_transactions`; a new non-tautological regression test (`test_compute_fund_vs_benchmark_switch_only_household_still_yields_fund_rows`) covers the switch-only case; the test spy restore is now in `try/finally`. Full backend suite re-run: 418 passed/2 skipped (+1 for the new test), `tsc -b --noEmit` clean. Scoped re-review (2026-08-19) returned **APPROVE, zero findings** — gate closed.
**Parent plan:** `Docs/orchestration/analytics-correction-plan-status.md` (22-item cross-reference); this round implements the 4 items whose disposition was decided as "fix now" or "lighter version" — see that doc's items P0.2, P0.3, P1.6, P1.10, P2.4.

## Task

Five independent fixes, each TDD (RED confirmed before implementation, per CLAUDE.md's non-negotiable). Land them as separate commits/diffs where practical since they touch different files, but one review pass covers all five.

### Fix 1 — P0.2: Category CAGR percentage display (frontend only)

`frontend/src/features/analytics/CategoryRankingSection.tsx`: `fund.scheme_return` and `fund.category_avg_return` arrive from the backend as raw decimal fractions (e.g. `"0.12"` for 12%) — same convention as XIRR before the already-fixed Item 1 bug. `percentile` is the one field the backend already returns pre-scaled (0–100) — do not touch that field or its existing `parsePercent`/`formatPercentString` pair, which stay correct as-is for `percentile` only.

Do **not** change the backend (`category_ranking.py`'s `_cagr()`). Per this codebase's Item-1 precedent, the ×100 conversion belongs at the frontend display boundary, using exact decimal-string arithmetic — never `parseFloat(...) * 100`. `frontend/src/lib/decimal.ts` already has the exact helper for this: `toPercentString(val: string): string` (shifts the decimal point 2 places via BigInt, used for XIRR display elsewhere in this codebase — grep for its other call sites for the established pattern).

Changes needed in `CategoryRankingSection.tsx`:
1. Add a new formatter (name it e.g. `formatRawFractionPercent`) that calls `toPercentString` from `@/lib/decimal` on the raw fraction string, then applies the same sign-prefix/`%`-suffix presentation `formatPercentString` already uses (`+` for positive, `%` suffix, `"N/A"` for null).
2. Use it at the two `formatPercentString(fund.scheme_return)` / `formatPercentString(fund.category_avg_return)` call sites (currently ~lines 141, 153) — leave `formatPercentString` itself untouched since `percentile` still needs it.
3. The `diff` variable (~line 88-91) computes `Number(diffDecimalStrings(fund.scheme_return, fund.category_avg_return))` then later does `diff.toFixed(2)` for display (~lines 210, 212) — this is the same raw-fraction scale bug. Fix by wrapping: `Number(toPercentString(diffDecimalStrings(fund.scheme_return, fund.category_avg_return)))` — keeps exact string arithmetic all the way through the ×100 shift, only the final `Number()` conversion is for display (matches this file's and `decimal.ts`'s own stated design rule).
4. `schemeReturnNum`/`categoryAvgNum` (the `parsePercent`-derived floats used only for sign comparisons like `schemeReturnNum >= 0`, ~lines 78-79) do **not** need scaling — comparing a raw fraction to 0 gives the same sign as comparing the scaled percent to 0. Leave those as-is.

Test: extend/add to `CategoryRankingSection.test.tsx` — a fund with `scheme_return: "0.12"` must render `"+12.00%"`, not `"+0.12%"`; same for `category_avg_return` and the outperformance-diff sentence.

### Fix 2 — P2.4: Clamp Scorer's final_score to [0, 100]

`backend/app/services/analytics/scorer.py` line ~238:
```python
final_score = (composite_rank[1] + applied_adjustment).quantize(Decimal("0.01"))
```
Clamp to `[Decimal("0"), Decimal("100")]` after the existing quantize — a fund at percentile 0 with the `-_TER_NUDGE` cost adjustment currently lands at exactly `-0.25`, outside the documented valid range. A large category's top fund plus a `+_TER_NUDGE` can also exceed 100.

Test: a case forcing `composite_rank[1] == Decimal("0")` (worst percentile) with a below-average-cost adjustment reaching `-0.25` before clamping must assert `final_score == Decimal("0.00")`, not negative. Mirror for the 100-ceiling case.

### Fix 3 — P1.10: Mixed plan types collapsing into one holdings row

`backend/app/services/dashboard/holdings.py` `compute_holdings`: the grouping key at line ~126 is `(household_member_id, scheme_id)`, then `plan_type = member_folios[0].plan_type` (line ~136-141) arbitrarily picks the first-encountered folio's plan type to label units/cost summed across *all* folios for that scheme — including folios of a *different* plan type. When a member holds the same scheme via both a Direct and a Regular folio, this produces one ambiguous merged row.

**Fix:** change the grouping key to `(household_member_id, scheme_id, plan_type)` so folios of different plan types for the same scheme produce separate `HoldingRow` entries instead of one merged row. Remove the now-obsolete "first-encountered folio's plan_type represents the merged row" comment and its simplification note.

**Already verified safe by the orchestrator — do not re-litigate, just implement:**
- `get_navs_on_or_before` (`nav.py`) and the `_default_single_nav_lookup` compatibility path both key their result dict by `scheme.id` alone; a duplicate `(scheme, date)` pair from two plan-type rows of the same scheme is harmless (idempotent lookup, same value written twice).
- `allocation.py` and `benchmark.py`'s `_current_value_by_scheme` both iterate the full `HoldingRow` list and sum by `scheme_id` — neither assumes one row per `scheme_id`, so two rows (one per plan type) sum correctly with zero changes needed there.
- `frontend/src/components/HoldingsTable.tsx` line ~182 uses `key={row.scheme_id + (row.household_member_id || "")}` as the React list key — this **does** need a matching fix, since two rows for the same scheme+member but different plan_type would now collide on this key. Change to also include `row.plan_type` in the key, e.g. `row.scheme_id + (row.household_member_id || "") + row.plan_type`.

Do not touch anything about how a scheme's detail/drill-down view aggregates — that already intentionally works at the scheme level, out of scope here.

Test (backend): two folios for the same `household_member_id` + `scheme_id`, one `PlanType.DIRECT` one `PlanType.REGULAR`, each with its own purchase transaction — `compute_holdings` must return 2 `HoldingRow` entries (not 1), each with that folio's own correct `units_held`/`amount_invested`, not a merged sum. Also confirm the existing single-plan-type case still merges multiple folios of the *same* plan type into one row (regression guard — this grouping refinement must not un-merge same-plan-type folios).

Test (frontend): a `CategoryRankingSection`/`HoldingsTable` React-key uniqueness check isn't practical as a unit assertion — a rendering test with two rows sharing `scheme_id`+`household_member_id` but different `plan_type` should render two distinct rows without a React key-collision console warning/error.

### Fix 4 — P1.6: Switch transactions invisible to fund-level XIRR

`backend/app/services/analytics/benchmark.py`: `_investment_transactions` filters to `_RELEVANT_TYPES = _DEBIT_TYPES | _CREDIT_TYPES` (imported from `dashboard/cash_flow.py`: `_DEBIT_TYPES = {PURCHASE, PURCHASE_SIP}`, `_CREDIT_TYPES = {REDEMPTION, DIVIDEND_PAYOUT}`). This set is correctly used for **portfolio-level** XIRR (`compute_portfolio_vs_benchmarks`) — switches are genuinely intra-portfolio, no cash enters/leaves the household, correctly excluded there, do not change that path.

It is also reused, incorrectly, for **fund-level** XIRR in `compute_fund_vs_benchmark` — a switch-out of Fund A / switch-in to Fund B should appear as a signed flow for each affected fund's *own* XIRR (money conceptually leaving Fund A, entering Fund B), even though it nets to zero at the portfolio level. Confirm sign convention against `holdings.py`: `_LOT_ADDING_TYPES` already treats `SWITCH_IN` like a purchase (adds units) and `_LOT_CONSUMING_TYPES` treats `SWITCH_OUT` like a redemption (consumes units) — so for fund-level XIRR, `SWITCH_IN` must be a debit (negative signed flow, like `PURCHASE`) and `SWITCH_OUT` must be a credit (positive signed flow, like `REDEMPTION`).

**Design (implement this exactly, this is an orchestrator-level design decision, not open for reinterpretation):**
1. Parameterize `_signed_amount(txn: Transaction, extra_debit_types: frozenset[TransactionType] = frozenset()) -> Decimal` — compute `debit_types = _DEBIT_TYPES | extra_debit_types` and return `-txn.amount if txn.type in debit_types else txn.amount`. Default (empty `extra_debit_types`) preserves today's exact behavior for every existing call site.
2. Thread an `extra_debit_types` parameter (default `frozenset()`) through `_portfolio_xirr` and `_benchmark_xirr_for_transactions`, passed straight to their internal `_signed_amount` calls. Every existing caller of these two functions passes nothing (keeps the default, unchanged behavior) **except** the fund-level per-scheme calls described in step 4.
3. Add `_fund_level_transaction_types = _RELEVANT_TYPES | {TransactionType.SWITCH_IN, TransactionType.SWITCH_OUT}` and a `_fund_level_transactions(db, household_member_ids)` query function mirroring `_investment_transactions` but filtering on this wider type set.
4. In `compute_fund_vs_benchmark`: keep the existing `transactions = _investment_transactions(...)` call and its resulting `overall_portfolio_rate`/`overall_broad_market_rate` computation completely unchanged (these are portfolio/broad-market-level rollups within this function and must still exclude switches, exactly like `compute_portfolio_vs_benchmarks`). Separately call `fund_level_transactions = _fund_level_transactions(...)`, group *that* list by scheme (same `folio_scheme` mapping already built), and use the fund-level grouped transactions — not the switch-excluding ones — for each scheme's own `fund_rate = _portfolio_xirr(scheme_txns, ..., extra_debit_types={TransactionType.SWITCH_IN})` and `benchmark_rate = await _benchmark_xirr_for_transactions(db, scheme_txns, index, extra_debit_types={TransactionType.SWITCH_IN})`.
5. Update the module docstring's line "switches ... excluded as intra-portfolio or non-cash-movement" to note this now applies to portfolio-level/broad-market rollups only, not per-fund XIRR.

Test: a fund with a `SWITCH_IN` transaction from another scheme must have that switch appear as a debit (negative) flow in its own fund-level XIRR calculation and its own benchmark-hypothetical replay; the portfolio-level XIRR test suite must show zero behavior change (switches still invisible there). Also test that `overall_portfolio_xirr`/`overall_broad_market_xirr` inside `compute_fund_vs_benchmark`'s response are unaffected by adding a switch pair (since they still route through the unwidened `transactions` list).

### Fix 5 — P0.3 (lighter version): Label benchmark indices as Price Return, not TRI

This is **not** a data-sourcing fix — do not touch `nse_indices_client.py`'s actual fetch logic or add any new index/data source. Scope is purely a disclosure/labeling fix: `frontend/src/features/analytics/BenchmarkSection.tsx`'s `INDEX_LABELS` map (~line 20-25) currently reads:
```ts
const INDEX_LABELS: Record<BenchmarkIndex, string> = {
  nifty_50: "Nifty 50",
  nifty_500: "Nifty 500",
  nifty_largemidcap_250: "Nifty LargeMidcap 250",
  nifty_midcap_150: "Nifty Midcap 150",
};
```
Change each label to append `" (Price Return)"`, e.g. `"Nifty 50 (Price Return)"`. This is a plain, honest disclosure that the benchmark comparison uses price-return index levels (NSE's plain index feed, no TRI/total-return designation confirmed available), so users aren't misled into thinking it's an apples-to-apples total-return comparison against their own (distribution-inclusive) fund XIRR.

Do not add a backend field for this — it's a static display-only label change, no new data flows through the API. Test: `BenchmarkSection.test.tsx` assertions that currently match `"Nifty 50"` etc. need updating to `"Nifty 50 (Price Return)"` etc. (a `getByText` exact-match test will need updating — check `BenchmarkSection.test.tsx` for exact strings currently asserted).

The orchestrator is separately writing a documentation update (`Docs/orchestration/tri-benchmark-deferred-plan.md`) recording why full TRI sourcing is deferred and what a future implementation would require — no action needed here beyond the label change itself.

## Constraints

- `Decimal`, never `float`, for every money/units/NAV value (CLAUDE.md non-negotiable) — Fix 4 in particular must not introduce any float arithmetic; `_signed_amount` already returns `Decimal`, keep it that way.
- TDD: RED (failing test) confirmed before implementation for every one of the 5 fixes, no exceptions.
- Do not touch anything not named in this doc — no drive-by refactors, no gold-plating (e.g. do not attempt full TRI sourcing, tie-aware ranking, or any other item from the 22-item correction plan; those are explicitly out of scope for this round).
- Full backend suite and `tsc -b --noEmit` must stay clean; scoped frontend test files for the touched components must pass.

## Approaches considered and rejected

- **P1.6:** considered widening `_investment_transactions`'s type filter globally and instead post-hoc *subtracting* switch flows for the portfolio-level path. Rejected — more code, more error-prone (a subtraction-based exclusion is harder to verify than never including the flow in the first place), and it would make the already-correct portfolio-level path depend on a new invariant instead of leaving it untouched.
- **P0.2:** considered fixing the scaling in the backend (`_cagr()` returning an already-×100 value, matching how `percentile` already works) instead of frontend. Rejected for consistency with the already-shipped Item 1 XIRR fix's design (raw fraction on the wire, ×100 at the display boundary) — mixing both conventions across sibling fields in the same response would be more confusing than the current single-convention inconsistency.
- **P0.3:** considered actually sourcing a TRI feed this round. Rejected — feasibility (does NSE's free/public endpoint even expose a TRI series, or does it require a paid source?) is unconfirmed, and CLAUDE.md's "don't gold-plate" / "build what's scoped" directs against speculative data-pipeline work before that question is answered. The label change is the honest, bounded fix for right now.
- **P1.10:** considered leaving `plan_type` as a per-transaction/per-folio detail exposed only in a drill-down rather than changing the aggregation grouping key. Rejected — the correction plan's requirement (and the underlying bug) is specifically that the *aggregated holdings row* is wrong today (silently sums across plan types under one arbitrary label); splitting the grouping key is the direct fix at the point the ambiguity is introduced, not a downstream patch.

## Open questions

None — all five fixes have a fully-specified design above. If any touched file's actual current content differs materially from what's quoted here (line numbers may have drifted since this doc was written), re-read the file first and adapt to its real current state rather than guessing.
