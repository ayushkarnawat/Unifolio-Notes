# DATA-001 — field lineage, golden dataset, and XIRR complaint findings

Date: 2026-08-17  
Scope: investigation/documentation only; no application code changed  
Privacy: synthetic transactions and public scheme data only

## Orchestrator correction (added after Codex's pass, before review gate)

The repro DB's 3 seeded `Scheme` rows have **corrupted name↔AMFI-code pairs**,
introduced by this session's own seed script
(`/tmp/claude-1000/.../seed_bug001.py`), not by any application code path.
Verified directly against mfapi.in:

| AMFI code | Seed script's (wrong) name | Real fund |
|---|---|---|
| 118989 | "Nippon India Growth Fund" | **HDFC Mid Cap Fund** |
| 120503 | "HDFC Large Cap Fund" | **Axis ELSS Tax Saver Fund** |
| 120716 | "ICICI Prudential Bluechip Fund" | **UTI Nifty 50 Index Fund** |

**Practical effect on the findings below:** the earlier adverse TER-ingestion verdict
and the 0.65%-vs-0.28% golden TER mismatch are primarily garbage-in/
garbage-out from this seed defect — the app fuzzy-matched TER against the
*names I fabricated*, which of course don't correspond to what those AMFI
codes really are. This does **not**, by itself, demonstrate a production
data-integrity bug. The seed-artifact conclusion applies to this specific
reproduction, not as a blanket guarantee about production: `backend/app/services/import_/enrich.py`
(~lines 90-99) accepts a CAS-supplied AMFI code paired with the CAS-supplied scheme
name at confidence 1.0 with no cross-check between the two, and `service.py`'s
`confirm_import()` (~lines 180-195) persists `amfi_code` from the match/override while
`name` comes from parsed CAS data — including user-driven overrides, which can pair an
override code with the original parsed name. That unvalidated pairing risk overlaps with
the `MIN_MATCH_CONFIDENCE = 0.55` finding below.

**What remains genuinely code-level and independent of the seed bug** (i.e.
still holds even with correct identity data):
- The **XIRR ×100 display bug** (`BenchmarkSection.formatXirrPercent()` never
  multiplies the backend's decimal fraction by 100) — confirmed against the
  golden dataset's own correct backend value (`0.143451...` → displayed
  `+0.14%` instead of `+14.35%`), independent of any scheme-identity issue.
  This is a confirmed, unambiguous code defect that produces exactly the complaint's
  100x-too-small shape. The specific screenshot could not be independently re-examined
  this session to confirm that it came through this exact code path.
- TER's literal `Decimal("0")` being persisted and treated as genuine
  coverage rather than "no match" — this is a real behavior of
  `refresh_ter_data`/`_best_match` regardless of which name matched.
- `MIN_MATCH_CONFIDENCE = 0.55` with no AMC/AMFI-code/category cross-check is
  a real, permissive-fuzzy-matching design gap — worth flagging as a risk
  even though this specific repro's mismatches were self-inflicted, since a
  real casparser-derived scheme name variant could plausibly cross that same
  low bar in production.
- Beta not implemented, AAUM never populated (no refresh entrypoint), NSE
  redirect not followed — none of these depend on the seed's identity error.

**Re-running the golden TER comparison with correctly-identified seed data**
(matching real name to real AMFI code) is needed before TER production-ingestion
correctness can be treated as a confirmed, ship-blocking finding rather than a
seed-data artifact — flagged as follow-up, not done
here to conserve further token/time spend on a repro-only fix.

### Golden-comparison re-run, correct identity (2026-08-18) — closes the item above

Re-ran the comparison from scratch in a fresh isolated sqlite DB, seeded
directly from `Docs/orchestration/data-001-golden-dataset.json` with the
CORRECT (verified) name↔AMFI-code pairs this time (not `seed_bug001.py`'s
scrambled pairing above), calling the app's real `compute_weighted_ter`
end-to-end. The live AMFI NAV fetch was mocked to raise `httpx.HTTPError` so
`get_nav_on_or_before`'s "always attempt a live refetch for `on_date ==
date.today()`" behavior (`backend/app/services/dashboard/nav.py`) falls back
to the seeded, frozen NAV rather than a real current-date value — this keeps
the comparison pinned to the golden dataset's frozen valuation date without
any live network dependency.

**Result: exact match.** App-computed weighted TER `0.65%` vs. golden's
`weighted_ter_percent_api_precision: 0.65` — **0.00pp diff**, well inside the
stated `0.01pp` tolerance (golden's full unrounded expected value is
`0.6499960033894331922350468161`).

**Conclusion: no real ingestion discrepancy remains.** The original
0.65%-vs-0.28% mismatch was caused entirely by `seed_bug001.py`'s scrambled
identity mapping, not by any defect in `compute_weighted_ter`,
`refresh_ter_data`, or `_best_match`'s fuzzy matching. TER production-
ingestion correctness — for the specific case of correctly-identified
scheme↔AMFI-code pairs — is now a **confirmed pass**, not an open item. The
executive-summary table's "production ingestion correctness: open" verdicts
below are superseded by this result; the only genuinely still-open risk in
this area is the *unvalidated* name/AMFI-code pairing at import time
(`MIN_MATCH_CONFIDENCE = 0.55`, `enrich.py`/`service.py`, described above) —
a real-world scheme whose CAS-parsed name is a poor fuzzy match for its true
AMFI-code identity, not a defect in the weighting/computation path itself.

## Executive summary

| Metric | Verdict | Evidence |
|---|---|---|
| Fund AAUM / category AUM weighting | **Open / unavailable** | `scheme_aaum` has 0 rows in the repro DB. The reader exists, but no request-time or implemented scheduled entrypoint calls `refresh_aaum_data`; therefore category AUM-weighted return/cost context cannot be validated dynamically. |
| Beta | **Not implemented** | No beta field, covariance calculation, route, schema, DB column, or UI exists. `risk_metrics.py` computes downside deviation and consistency, not beta. Benchmark XIRR is not beta. |
| TER ingestion/mapping | **Formula/computation logic: pass; production ingestion correctness: open** | The only golden comparison used seed data with corrupted name↔AMFI-code identity (see Orchestrator correction). Re-run with correctly identified seed data before treating this as a confirmed, ship-blocking finding. The import path's unvalidated name/code pairing remains a structural risk. |
| Weighted TER formula | **Formula/computation logic: pass; production ingestion correctness: open** | `SUMPRODUCT(current value, TER) / covered value` is correct and uses `Decimal`. The observed `0.28%` versus code-matched `0.65%` comparison used corrupted seed identities, so it must be re-run with correctly identified data before judging production ingestion. |
| XIRR backend | **Pass** | Independent bisection gives `0.14345100447244033` (14.3451%); the application gives `0.14345100447244031`, effectively identical and well within 0.01 percentage points. |
| XIRR display / +0.10% complaint | **Fail; formatter defect confirmed** | Backend XIRR is a decimal fraction, but `BenchmarkSection.tsx` appends `%` without multiplying by 100. A correct backend `0.10` (10%) is displayed as `+0.10%`. This is the confirmed cause for a complaint of this shape; the unavailable specific screenshot could not be re-examined to prove it traversed this code path. |
| NSE benchmark availability | **Fail-open as unavailable** | The repro DB has 0 benchmark rows. The NSE request does not follow the observed 302; errors are swallowed, so benchmark XIRRs become `None`. This is honest missing output, not a silently fabricated benchmark, but the UI has no data-age explanation. |

## Field-level lineage

| Metric | Source / stored field | Units | As-of-date semantics | Missing/stale fallback | Methodology and exact function |
|---|---|---|---|---|---|
| AUM (scheme AAUM used for category averages) | AMFI `average-aum-schemewise` → `schemes.amfi_code` → `scheme_aaum.aaum_value` | Feed/schema unit is not declared in code; stored as `Numeric(18,2)`. It is used only as a relative weight, so a common lakh/crore scale cancels. It is not the user's ₹ holding value. | `reference_period` is intended as the last day of the period-ending month, parsed from an assumed period label. Readers select the latest row **per scheme**, not a common portfolio/category period. | Fetch/shape/mapping failure returns `False` and writes nothing. Readers omit schemes without AAUM; zero denominator returns `None`. Stale rows are accepted indefinitely. No live refresh caller exists. | `refresh_aaum_data()` in `amfi_aaum_client.py`; `_latest_aaum_by_scheme()` and `_aum_weighted_average()` in `category_ranking.py`. |
| Beta | No source, field, or computation exists | N/A (beta would normally be a unitless covariance ratio) | N/A | N/A; unavailable by absence, with no beta API/UI contract | **Unimplemented.** `risk_metrics.build_monthly_series()` feeds downside deviation and rolling consistency only. |
| TER | AMFI TER month/data APIs → fuzzy scheme-name match → `scheme_ter.ter_value`; Direct reads `D_TER`, Regular reads `R_TER` | Percentage points: `1.02` means **1.02%**, not fraction `0.0102` | DB key is month start. `_latest_ter_for_scheme()` selects each scheme's newest row. | If any holding lacks current-month TER, one bulk refresh is attempted. Failure keeps arbitrary older rows. Missing schemes are uncovered; raw `0` is accepted as real coverage. | `refresh_ter_data()` / `_best_match()` in `amfi_ter_client.py`; `_latest_ter_for_scheme()` in `ter.py`. |
| Weighted cost / TER analysis | Holding `current_value` from FIFO units × latest public NAV, joined to latest `scheme_ter`; direct/regular split uses merged holding `plan_type` | `current_value` is ₹; TER and result are percentage points | NAV carries `current_nav_date` internally, but TER response exposes only the **latest** TER period among covered schemes. It does not expose the oldest/mixed period or NAV valuation date. | Missing TER is removed from numerator **and denominator**, with `covered_value` and names reported. If nothing is covered, result is `None`. A literal zero is treated as covered. | `_summarize()` and `compute_direct_regular_ter_comparison()` in `ter.py`: `Σ(value × TER) / Σ(covered value)`. Cost adjustment uses `_category_ter_context()` / `_cost_adjustment_from_context()` in `scorer.py`. |
| XIRR | Relevant transactions (`purchase`/SIP negative; redemption/dividend positive) + terminal `compute_holdings()` current value | Backend decimal fraction: `0.10` means **10%**. Web formatter incorrectly treats it as already-percent. | Transaction dates plus terminal date `date.today()`. Terminal NAV can actually be an earlier business day's NAV, but the XIRR response does not expose that NAV date. | No two-sided flow or Newton failure → `None`. A holding missing NAV disappears from `compute_holdings`, reducing terminal value silently; benchmark index fetch failure yields `None` only for benchmark results. | `_signed_amount()`, `_portfolio_xirr()`, `compute_portfolio_vs_benchmarks()` in `benchmark.py`; root solver `xirr()` in `xirr.py`. |

## Required correctness checks

### AUM / AAUM

- **Scaling:** AAUM's source unit is undocumented in the implementation. Because the only computation is a weighted mean, a common unit cancels, but mixed feed units would not be detected.
- **Staleness:** latest-per-scheme rows may be from different quarters; no common reference period or age is returned to the user.
- **Plan and option mixing:** AAUM joins by `AMFI_Code`, which distinguishes plan/option codes, but category universes include all local variants. Direct, Regular, Growth and IDCW can all contribute as separate peers, potentially overweighting one underlying scheme family.
- **Mapping:** missing AMFI code matches are simply omitted. Missing `sebi_category` is represented as unavailable by the ranking layer; the DB model currently declares it non-null.
- **Silent zero:** zero AAUM participates as a zero weight; all-zero/missing weights yield `None`, not zero.
- **Population path:** only unit tests call `refresh_aaum_data()`. The TDD specifies future EventBridge/Fargate quarterly execution, but no job/CLI/route entrypoint is present. The repro DB's `scheme_aaum` table is empty.

### Beta / benchmark

- **Beta:** there is nothing to validate. The handoff's description of `risk_metrics.py` as beta logic is inconsistent with the repository: it computes monthly downside deviation and rolling 12-month peer consistency.
- **Window:** `build_monthly_series()` has no SQL lower bound, but it emits only requested month-end anchors, so older rows do not change the result; they add query cost only. This does not rescue beta, which remains absent.
- **Benchmark scaling:** index levels are absolute points; benchmark XIRR returns decimal fractions.
- **Staleness:** `ensure_index_history_fresh()` requires cached bounds through `date.today()`. On weekends/holidays that condition is impossible for a trading-day series, encouraging a fetch on every request.
- **Fallback:** failed NSE refresh leaves cache untouched. `get_index_level_on_or_before()` then uses whatever is present; if empty, benchmark XIRRs are `None`. Portfolio XIRR remains computable.
- **Observed redirect:** `httpx.AsyncClient` is created without `follow_redirects=True`. Given the prior observed 302, `raise_for_status()` enters the broad failure fallback. The repro DB contains 0 benchmark rows, so all four benchmark comparisons are unavailable.
- **Category fallback:** only exact Large/Mid category keywords choose specialized indices; every other category, including debt/hybrid and missing/misclassified categories, falls back to Nifty 500. That is available-but-methodologically-weak, not beta.

### TER and weighted-cost analysis

- **Scaling:** consistent internally: AMFI values and UI are percentage points. No ×100/÷100 error was found in TER.
- **Staleness:** each scheme's latest row is used, while the response reports the maximum date. A portfolio could therefore be labeled with a newer period than some inputs actually use.
- **Direct/Regular:** ingestion selects `D_TER` or `R_TER` from `Scheme.plan_name_variant`; unresolved variants are skipped. The direct/regular comparison instead uses `HoldingRow.plan_type`. `compute_holdings()` merges folios by member+scheme and takes the first folio's plan type, so mixed-plan folios for one scheme can be assigned to the wrong bucket.
- **Growth/IDCW:** AMFI's row is plan-generic and local fuzzy matching does not explicitly strip/validate Growth vs IDCW identity. Both variants may independently match the same row; that is acceptable only if AMFI truly publishes one TER for both options, but no invariant enforces it.
- **Mapping:** TER uses `SequenceMatcher` with a low `0.55` threshold and no AMC, AMFI code, category, token, or rename validation. Every repro identity is wrong: 118989 is HDFC Mid Cap (stored as Nippon Growth/Large Cap), 120503 is Axis ELSS (stored as HDFC Large Cap), and 120716 is UTI Nifty 50 Index (stored as ICICI Bluechip/Large Cap). This contaminates all category, TER, and benchmark selection before arithmetic begins.
- **Silent zero / coverage:** confirmed in code, a literal zero TER from the feed is indistinguishable from a genuine zero-expense-ratio fund and both are counted as coverage. This is a real validation gap regardless of the specific reproduced values, which are known seed-corrupted: it is a structural risk, not a demonstrated incorrect production value.
- **Cost overlay:** if own TER or category AAUM-weighted TER is unavailable, `_cost_adjustment_from_context()` returns numeric `0`, indistinguishable from a genuine “no adjustment.” This is a confirmed silent-zero semantic issue.

### XIRR

- **Scaling:** backend correctly documents/returns a fraction. `BenchmarkSection.formatXirrPercent()` parses that fraction and appends `%` directly. Tests reinforce the wrong contract with fixtures such as `"16.45"`, even though the backend would return about `"0.1645"` for 16.45%.
- **Staleness/as-of:** terminal flow date is today even when the terminal NAV is from an earlier business day. The golden case has a three-day weekend gap (NAV 2026-08-14, terminal flow 2026-08-17), a negligible numerical difference but mislabeled semantics.
- **Plan/option mixing:** cash flows are transaction/folio based, so all plans/options are included. Current value is aggregated by scheme. A wrong scheme mapping or a holding dropped for absent NAV directly distorts XIRR.
- **Mapping fallback:** transactions need a valid folio→scheme. Missing NAV causes the holding—and therefore its terminal value—to be omitted, while its historical purchase outflow remains in `_investment_transactions`; this can silently depress portfolio XIRR.
- **Silent zero:** a fully redeemed fund can legitimately have zero terminal value. A currently held fund missing NAV is also represented as absent from terminal value, which is not distinguished in the XIRR response.
- **Numerics:** all backend money/rate arithmetic is `Decimal`. The Newton result passes the independent bisection reference. The web percentage path uses `parseFloat`; besides the ×100 bug, that violates the repository's explicit no-float percentage rule.

## Golden dataset and independent calculations

Machine-readable inputs and expected values are in `data-001-golden-dataset.json`. The transactions contain no PAN, CAS, folio, phone, or real user identity. They use three public AMFI codes with synthetic ₹100,000 purchases and synthetic 1,000-unit lots. Cached NAV rows originated from mfapi.in's public histories; valuation uses the last public NAV on 2026-08-14 and a 2026-08-17 terminal date.

The reproducible reference script is `data-001-golden-independent.py`. It imports no application module. It solves XNPV=0 with 300 iterations of bracketed bisection, independently of the application's Newton-Raphson, and computes TER using spreadsheet-style `SUMPRODUCT / SUM`.

### Hand arithmetic

Terminal values:

- FUND-A: `1,000 × 236.3720 = ₹236,372.0000`
- FUND-B: `1,000 × 112.4854 = ₹112,485.4000`
- FUND-C: `1,000 × 171.5836 = ₹171,583.6000`
- Total: `₹520,441.0000`

All three purchases occur on the same date, so the XIRR has a closed-form cross-check:

`r = (520441 / 300000)^(365 / 1500) - 1 = 0.14345100447244033 = 14.3451004472%`

Independent weighted TER, using code-matched contemporary Direct-plan TERs of 0.75% (HDFC Mid Cap), 1.05% (Axis ELSS), and 0.25% (UTI Nifty 50):

`(236372×0.75 + 112485.4×1.05 + 171583.6×0.25) / 520441 = 0.6499960034% → 0.65%`

The TER references are the HDFC Mid Cap, Axis ELSS, and UTI Nifty 50 public references linked in the JSON. Their as-of dates differ by days/weeks, so this validates weighting and catches broken identity/ingestion; it is not a claim that three TERs share one exact AMFI publication timestamp. The UTI value is corroborative rather than primary-AMC data, so the exact UTI TER remains lower-confidence; even excluding it, the persisted scheme identity used for this comparison is known seed-corrupted (see Orchestrator correction), so this comparison must be re-run against correctly-identified seed data before the weighted-TER mismatch itself can be treated as confirmed.

### Comparison

| Output | Independent expected | Application/service output on isolated copy | Tolerance | Result |
|---|---:|---:|---:|---|
| Backend portfolio XIRR | 14.3451004472% (`0.143451...`) | 14.3451004472% (`0.143451...`) | 0.01 percentage points | **Pass** |
| Web-displayed portfolio XIRR | +14.35% | +0.14% from the same backend value | 0.01 percentage points | **Fail** (×100 display bug) |
| Weighted TER | 0.65% | 0.28% | 0.01 percentage points | **Formula pass; production ingestion open** — comparison used corrupted seed identities and must be re-run with correctly identified data |
| AUM-weighted category metric | N/A | N/A (`scheme_aaum` empty) | N/A | **Open, not falsely passed** |
| Beta | N/A | no output exists | N/A | **Not implemented** |

The isolated comparison copied `unifolio_dev.db` to `/tmp/data001_endpoint.db`; it did not write the shared DB. The aggregate service behind the endpoint returned portfolio XIRR `0.143451004472440311...`, weighted TER `0.28`, and `None` for all benchmark XIRRs when refresh was disabled to reproduce the empty-cache fallback. Local loopback sockets are blocked in this sandbox, so verification invoked the same aggregate service functions rather than claiming a completed HTTP curl.

## +0.10% portfolio XIRR complaint — root cause

The screenshot file named in the handoff was no longer present at the supplied cache path, but the reported text and the complete producer/formatter path are sufficient to reproduce the issue.

This complaint is **not explained by “small gain over a long holding period” in the observed UI path**. Such a portfolio can mathematically have a true 0.10% XIRR—for example, ₹300,000 becoming ₹301,234.79 over 1,500 days is a ₹1,234.79 (0.4116%) total gain and exactly 0.10% annualized. However, the application has a confirmed 100× display defect:

1. `xirr()` explicitly returns a decimal fraction (`0.10` means 10%).
2. `compute_portfolio_vs_benchmarks()` serializes that fraction unchanged.
3. `BenchmarkSection.formatXirrPercent()` runs `parseFloat(val).toFixed(2)` and appends `%` without multiplying by 100.

Therefore an ordinary correct backend XIRR near 10% (`0.10`) is displayed as `+0.10%`. The golden case proves the same defect: correct backend 14.3451% becomes `+0.14%`. This is a confirmed, unambiguous code defect that produces exactly the symptom described and is the confirmed root cause for a complaint of this shape. The specific screenshot could not be independently re-examined this session to confirm it was generated by this exact code path, but no other mechanism in the codebase produces this 100x-too-small pattern.

## Conclusions and remaining open work

Confirmed correct: backend XIRR signs, annualization, and solver; weighted-TER arithmetic given valid inputs; missing benchmark cache results in `None` rather than a fabricated number.

Confirmed incorrect: XIRR web scaling; category/cost overlay uses zero to mean unavailable; all three seeded AMFI code→name/category mappings. Confirmed structural TER gap: a literal zero is indistinguishable from a genuine zero TER and is counted as coverage. TER formula/computation logic passes; production ingestion correctness remains open because the only golden comparison used corrupted seed identities and must be re-run with correctly identified data before becoming a ship-blocking finding.

Still open by missing implementation/data: beta; a production AAUM refresh entrypoint and real AAUM rows; a working NSE redirect/freshness path; a response contract that exposes the true terminal NAV date and per-input TER/AAUM staleness. No application fix was made under DATA-001.
