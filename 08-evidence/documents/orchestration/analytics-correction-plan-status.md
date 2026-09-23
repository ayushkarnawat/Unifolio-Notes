# Analytics Dashboard Internal Correction Plan — Status Cross-Reference

**Source document:** `Docs/Analytics-Dashboard-Internal-Correction-Plan.md` (18 Aug 2026,
internal, uncommitted, lives in the main checkout's working tree on `feat/enhanced-ui` —
not present in this worktree/branch; confirmed genuine and read in full via its absolute
path). This doc cross-references every one of its 22 requirements (P0.1–P0.4, P1.1–P1.10,
P2.1–P2.8) against this worktree's actual codebase as of 2026-08-19, item by item, with
direct code evidence where checked. **No code has been changed as part of producing this
doc** — this is investigation/classification only, same posture as the original
`bug-001-findings.md`/`data-001-findings.md` pass.

**Confidence key:**
- **VERIFIED** — read the actual implementation this session, evidence cited below.
- **CARRIED** — presumed status from an earlier session's work/memory, not re-read this pass.
- **PARTIAL** — part of the claim was read and confirmed this session, part was not (either presumed, or left for a scoped follow-up) — see the item's prose for exactly which part.
- **UNCHECKED** — not investigated at all this pass; status unknown.

**Adversarially reviewed (2026-08-19):** a Codex review pass caught 8 findings against the
original version of this doc (1 High: an unsupported "confirmed price-only" leap on P0.3;
5 Medium: a false "no documented trading-day convention" claim on P0.4, a wrong exact
number in P2.4's clamp-overshoot example, VERIFIED labels on P1.2/P1.3/P2.8 that didn't
match the investigation actually performed that section's own prose disclosed; 2 Low:
missing PARTIAL in this key, an imprecise P1.10 description) — all fixed below. The two
previously-unverified conditions (P1.2's both-TER-required check, P1.3's 45%/30% weight
constants) were then independently re-read and confirmed present, so those two items are
now genuinely VERIFIED rather than downgraded.

---

## P0 — Release-blocking

### P0.1 XIRR percentage presentation — DONE (CARRIED)
Already fixed as Item 1 of the original 7-item workstream (×100 at the presentation
boundary). Not re-verified this pass beyond confirming `_xirr_str` in `benchmark.py`
still serializes a raw decimal-fraction string (correct — the ×100 conversion belongs at
the frontend/display boundary per that fix's design, and this doc doesn't re-litigate it).

### P0.2 Category CAGR percentage presentation — **CONFIRMED BUG, NOT FIXED** (VERIFIED)
`category_ranking.py`'s `_cagr()` returns a raw decimal fraction (e.g. `0.12`), never
multiplied by 100 anywhere in that function or its callers. `CategoryRankRow.scheme_return`
/`category_avg_return` are `str()`-serialized from that raw fraction with no scaling.
`CategoryRankingSection.tsx`'s `formatPercentString`/`parsePercent` also apply no ×100
scaling. End-to-end: a real 12% category return currently displays as **"0.12%"**. The
only ×100 conversion in the whole file is for `percentile` (a different, already-correct
field) — confirms this is a genuine gap, structurally identical to the already-fixed Item
1 XIRR bug but in an untouched code path. **This is a clean, high-confidence, low-risk fix
— same shape as Item 1, recommend implementing via the same TDD path.**

### P0.3 TRI (Total Return Index) vs. price-only benchmark — **CONFIRMED NAMING GAP, ECONOMIC CONTENT UNCONFIRMED** (VERIFIED, narrower claim)
`nse_indices_client.py`'s `_TRADING_INDEX_NAME` maps all 4 `BenchmarkIndex` members to
plain, non-TRI-labeled NSE names ("Nifty 50", "Nifty 500", "NIFTY LARGEMID250", "Nifty
Midcap 150") — no TRI designation anywhere, and a repo-wide grep for "TRI" across
`backend/app/`, `Docs/PRDs/`, `Docs/TDD-Unifolio.md` returns zero genuine hits. **What
this actually establishes:** the requested series is not explicitly labeled/selected as
TRI. **What it does NOT establish:** that the series NSE actually returns for these names
is confirmed price-only (excludes reinvested distributions) — `_fetch_index_history` only
consumes `HistoricalDate`/`CLOSE` values with no return-type metadata in the response, so
nothing in this codebase inspects the retrieved values against known TRI/price-index
figures to confirm which series NSE is actually serving under a plain "Nifty 50" request.
Reviewed and corrected after an initial draft of this doc overclaimed "confirmed
price-only" without that value-level check. Either way, this remains the doc's own
release-blocker: per P0.3's acceptance criteria, the benchmark identifier and series type
must be explicitly recorded and "TRI" displayed with the name — neither happens today
regardless of what NSE is actually serving. **Recommend scoping this as its own
investigation** (does NSE's public/free endpoint even expose TRI series, or does that
require a different, possibly paid, data source?) **before any implementation attempt** —
the largest-scope item in the whole doc.

### P0.4 Reject incomplete benchmark cash-flow paths — **CONFIRMED GAP** (VERIFIED)
`benchmark.py`'s `_benchmark_xirr_for_transactions` (line 86–99): when a transaction's
date has no index level available, it silently `continue`s — the flow is dropped, not
the whole comparison rejected. There is no "return benchmark unavailable if any material
flow remains unresolved" behavior; the function computes and returns a (silently biased)
XIRR over whatever subset of flows happened to resolve, and nothing is exposed to internal
diagnostics when a date fails to resolve. **Correction:** an earlier draft of this doc also
claimed there is "no documented, testable trading-day convention" — that's wrong.
`get_index_level_on_or_before`'s on-or-before convention IS explicitly documented
(`nse_indices_client.py:126`'s own docstring: "trading holidays/weekends mean the exact
date is often not present") and IS tested (`test_nse_indices_client.py`'s weekend-lookup
test). The trading-day convention itself is fine; the confirmed gap is narrower and
specifically about what happens when even that on-or-before lookup still comes up empty
(no cached history covers the date at all) — silent drop instead of the doc's required
"benchmark unavailable."

---

## P1 — High-priority

### P1.1 Production AAUM refresh process — **CONFIRMED GAP** (VERIFIED)
`amfi_aaum_client.py` exposes `refresh_aaum_data(db)` as a callable async function, but a
repo-wide grep for scheduler/cron/EventBridge wiring found no production caller anywhere
— matches `data-001-findings.md`'s already-known "confirmed unimplemented" conclusion
exactly (the doc's own wording: "a data-ingestion capability exists, but it needs a
scheduled production caller"). No freshness monitoring, failure alerting, or
insufficient-AAUM suppression exists either.

### P1.2 Missing TER vs. genuine 0% TER — **LARGELY SATISFIED** (VERIFIED)
`ter.py`: `weighted_ter=None` (distinct unavailable sentinel, not zero) when
`covered_value` is falsy; `covered_value`/`total_value`/`uncovered_schemes` are explicit
coverage-disclosure fields already returned. `scorer.py`'s `_cost_adjustment_from_context`
(line 170–185) independently confirmed to return `None` if `own_ter is None or
category_avg is None` — the exact both-required condition the doc's acceptance criteria
asks for, closing the gap an earlier draft of this section had left as a follow-up.
This matches Item 6's already-shipped fix and the doc's P1.2 acceptance criteria closely.

### P1.3 Scorer governance / one approved methodology — **NUMERICALLY MATCHES, GOVERNANCE OPEN** (VERIFIED)
`scorer.py`'s actual constants (line 43–47): `_RETURN_WEIGHT = Decimal("0.45")`,
`_RISK_WEIGHT = Decimal("0.30")`, `_CONSISTENCY_WEIGHT = Decimal("0.25")`,
`_TER_DEAD_ZONE = Decimal("0.05")`, `_TER_NUDGE = Decimal("0.25")` — all five independently
re-read and confirmed present, matching the doc's "45% return / 30% downside risk / 25%
consistency... ±0.25 TER adjustment outside a ±0.05pp tolerance" exactly.
`Docs/Scorer-Methodology-Unifolio.md` already exists as the stakeholder-facing methodology
doc from the original Scorer build. What's open is the doc's specific ask: reconciling
"earlier requirement language and later scoring decisions... in one versioned policy
**before sign-off**" — a product/governance action (get the financial/product owner to
formally approve the existing numbers as final), not a code change. **Recommend: confirm
with the product owner that the existing methodology doc IS the one approved version,
rather than building anything new.**

### P1.4 Minimum eligible peer count (hard suppression) — **CONFLICTS WITH EXISTING PRD DECISION** (VERIFIED)
`_THIN_CATEGORY_THRESHOLD = 5` exists in `category_ranking.py` and matches the doc's
numeric threshold exactly — but implements a **soft** "still shown, but flagged"
(`thin_category=True`) behavior, per an existing, already-documented PRD "Edge Cases
table" decision. The correction plan's P1.4 requires **hard suppression**: "do not
publish peer percentiles, tiers, or scores when fewer than five eligible peer schemes are
available." These are direct opposites for the same threshold. **Per CLAUDE.md's working-
style instruction ("when a PRD... seems to conflict with what you're about to build, stop
and say so"), this is flagged here rather than resolved in either direction — needs an
explicit product decision: keep the existing soft-flag UX, or switch to hard suppression
per the correction plan.**

### P1.5 Tie-aware ranking — **CONFIRMED GAP** (VERIFIED)
`category_ranking.py`'s `_rank_and_percentile` uses plain `sorted()` + `.index()` — two
schemes with identical returns get an arbitrary sequential rank with no shared/fractional-
rank policy. `scorer.py` imports and reuses this exact function for its own return/risk
ranking, so the gap is shared across both features simultaneously — one fix closes both.

### P1.6 Switch transactions in fund-level XIRR — **CONFIRMED GAP** (VERIFIED)
`benchmark.py`'s `_investment_transactions` filters to `_RELEVANT_TYPES = _DEBIT_TYPES |
_CREDIT_TYPES` from `dashboard/cash_flow.py`, where `_DEBIT_TYPES = {PURCHASE,
PURCHASE_SIP}` and `_CREDIT_TYPES = {REDEMPTION, DIVIDEND_PAYOUT}` — no
`SWITCH_IN`/`SWITCH_OUT` type is referenced anywhere in `benchmark.py`. This set is shared
between portfolio-level XIRR (correctly excludes switches — no money enters/leaves the
portfolio) and fund-level XIRR in `compute_fund_vs_benchmark` (incorrectly excludes them
too — a switch-out/switch-in should appear as a signed flow for each affected fund's own
XIRR, per the doc). Fund-level XIRR currently just doesn't see switches at all.

### P1.7 Exposure-appropriate benchmark families — **CONFIRMED GAP** (VERIFIED)
`_benchmark_index_for_category` maps Large Cap→Nifty 50, Mid Cap→Nifty Midcap 150,
Large&Mid→LargeMidcap 250, and **everything else — Flexi/Multi/Small Cap, Value/Contra,
Sectoral, ELSS, Dividend Yield, and every non-equity category (Debt, Hybrid, Gold,
International, etc.) — falls back to Nifty 500**, a broad Indian equity index. This is
exactly what P1.7 prohibits: comparing debt/hybrid/gold/international schemes against a
broad equity benchmark. The function's own docstring already flags this as "a judgment
call... per CLAUDE.md's 'stop and say so'" from the original Scorer build — i.e. this was
already a known, previously-flagged tradeoff, now confirmed as a correction-plan blocker
rather than an acceptable simplification.

### P1.8 Valuation-date/XIRR terminal-value alignment — **LIKELY GAP, NOT FULLY VERIFIED** (VERIFIED partial)
`_portfolio_xirr` appends `(date.today(), current_value)` as the terminal cash flow, where
`current_value` comes from `compute_holdings`'s per-scheme NAV (each scheme's own most-recent
available NAV, not necessarily today's). No explicit NAV cutoff/staleness policy or partial-
valuation-coverage disclosure was found. This is consistent with a real gap but wasn't traced
all the way through `compute_holdings`'s NAV-selection logic this pass — flagging as
identified, not confirmed to the same depth as the items above.

### P1.9 Scheme/plan/TER identity matching — **PARTIALLY ADDRESSED** (CARRIED + VERIFIED scope)
Item 7 (already shipped) tightened import-time identity binding: cross-checks a CAS-supplied
AMFI code against its canonical master-list name, and validates plan-type overrides against
an anchored Direct/Regular Plan name match. This satisfies P1.9's "prefer stable identifiers,"
"distinguish direct/regular plans" criteria — but **only at import time**. The doc's broader
ask (TER, AAUM, and peer-data lookups all correctly identity-matching the same scheme/plan/
option/effective-period) extends past import into the TER/AAUM/Scorer pipelines, which use a
separate, looser fuzzy-name matcher (`amfi_ter_client.py`'s `MIN_MATCH_CONFIDENCE=0.55`,
noted but deliberately left alone during Item 7 as a different matching context). Not
verified whether that matcher's looser threshold creates a live P1.9 risk in the TER/AAUM
path specifically.

### P1.10 Mixed plan types in aggregated holdings — **CONFIRMED BUG** (VERIFIED)
`dashboard/holdings.py`: rows are grouped by `(household_member_id, scheme_id)` (line 126)
— the same key regardless of plan type — then units/cost are summed across all folios in
that group while `plan_type = member_folios[0].plan_type` (line 136–141) picks only the
first-encountered folio's plan type to label the merged row. So when the same scheme
appears in both a direct and a regular plan folio for one member, the aggregated row shows
one arbitrary plan_type while silently summing units/cost across both plans underneath it
— the concrete defect is the folio-level plan attribution getting collapsed at the
grouping step, which can then mis-bucket any scheme-level analytics keyed off that single
`plan_type` label (not, more loosely, "NAV/TER/score inputs get merged" — all downstream
NAV/TER/score lookups key off the shared `scheme_id`, not off this plan_type field
directly). This is a *new* finding, not previously listed in CLAUDE.md's "Still open"
carry-forward items.

---

## P2 — Control, accuracy, hardening

### P2.1 Normalize category peer sets (share classes) — UNCHECKED
Not investigated this pass. Needs a look at whether `category_ranking.py`'s peer universe
query dedupes multiple share classes/options of the same underlying portfolio.

### P2.2 Distribution treatment consistency — UNCHECKED
Not investigated. Related to P0.3's TRI gap — likely blocked on the same underlying
data-source question (does the NAV series used for category-return CAGR reflect
reinvested distributions consistently across growth/IDCW options?).

### P2.3 NAV/market-data freshness tolerances — UNCHECKED
Not investigated as a formal policy. Partial, incidental coverage exists (TER's negative-
cache/backoff from Item 3, NAV warming TTLs from the dashboard perf work) but none of that
was built as an explicit "acceptable age by asset type, disclosed when stale" policy.

### P2.4 Clamp adjusted scores to [0, 100] — **CONFIRMED GAP** (VERIFIED)
`scorer.py` line 238: `final_score = (composite_rank[1] + applied_adjustment).quantize(
Decimal("0.01"))` — no `min(100, ...)` / `max(0, ...)` clamp anywhere around this
assignment or downstream. **Correction to the original example:** `_rank_and_percentile`
computes `percentile = (total - rank) / total * 100` (`category_ranking.py:161`), so rank 1
(the top fund) never gets an exact percentile of 100 — only `(n-1)/n × 100`, which
approaches but never reaches 100 as category size `n` grows. An exact `100.25` overshoot
is therefore not reachable at the top end. The bottom end IS exactly reachable, though:
rank `n` (the worst fund) gets percentile `0`, and a `-_TER_NUDGE` adjustment produces a
`final_score` of exactly **−0.25** — outside the documented `[0, 100]` valid range. The
gap is real (no clamp exists either direction, and a large enough category's top fund can
still land above 100, e.g. `99.98 + 0.25 = 100.23`), just not via the originally-cited
exact number. **Small, low-risk, clean fix** — same character as P0.2, a good second TDD
fix to pair with it.

### P2.5 Calculation lineage/audit metadata — UNCHECKED (likely gap)
No `methodology_version`, `valuation_date`, `data_source_date`, or similar audit fields
were spotted on any analytics response schema during this pass's reads of `schemas.py`
excerpts, but the full schema file wasn't exhaustively re-checked for this specific
requirement. Flagging as likely-missing, not confirmed.

### P2.6 Scoring/ranking efficiency (shared per-category computation) — **PARTIALLY ADDRESSED** (CARRIED)
Items 2 (Scorer caching) and 4 (Category Ranking bulk query + 15-min TTL category cache)
already address the core ask — `category_ranking.py`'s `_category_returns` cache computes
category-wide statistics once per category rather than per-scheme. Not verified this pass:
whether the Scorer's own per-scheme scoring loop (`compute_portfolio_score`'s per-held-fund
path) reuses this same cached category computation end-to-end, or partially reconstructs it
— the original Scorer build's High finding on this exact redundant-rescoring problem
(fixed in `d732fce`) suggests it should, but wasn't re-read this pass. The doc's specific
"bounded query and timing tests" ask also wasn't checked against what Items 2/4 actually
added test-wise.

### P2.7 TER/market-data retrieval hardening — **PARTIALLY ADDRESSED** (CARRIED)
Item 3 already added negative-result caching and backoff for the TER feed. Not verified
this pass: request coalescing (de-duplicating concurrent identical fetches, like the
NAV-fetch dedup work from the dashboard-perf fix), bounded retries, or source-health
monitoring for TER/AAUM/NSE clients — none of these were seen in the code read this pass,
and are presumed absent unless a future check finds otherwise.

### P2.8 Validate redirects and trading-day/date-range freshness — **DONE** (PARTIAL: date-range half VERIFIED this session, redirect half CARRIED)
Both halves closed: the redirect-safety half was Item 5's already-shipped fix (prior
session, not re-read this pass — CARRIED); this window's follow-up fix independently
added and verified the missing response-date-range validation this session
(`ValueError` raised if any parsed row falls outside the requested `[start_date,
end_date]`, `nse_indices_client.py:78`) — committed `5073211`, adversarially reviewed
APPROVE/zero-findings.

---

## Summary table

| Item | Status | Confidence |
|------|--------|------------|
| P0.1 XIRR % | DONE | CARRIED |
| P0.2 Category CAGR % | **BUG, not fixed** | VERIFIED |
| P0.3 TRI benchmark | **Naming gap confirmed; economic content unconfirmed** | VERIFIED (narrower) |
| P0.4 Cash-flow completeness | **Gap** | VERIFIED |
| P1.1 AAUM refresh | **Gap** | VERIFIED |
| P1.2 TER unavailable state | Largely satisfied | VERIFIED |
| P1.3 Scorer governance | Numerically matches, sign-off open | VERIFIED |
| P1.4 Min peer count | **Conflicts with existing PRD decision** | VERIFIED |
| P1.5 Tie-aware ranking | **Gap** (shared Category Ranking + Scorer) | VERIFIED |
| P1.6 Switch handling | **Gap** | VERIFIED |
| P1.7 Benchmark family mapping | **Gap** | VERIFIED |
| P1.8 Valuation-date alignment | Likely gap | PARTIAL |
| P1.9 Identity matching (broader) | Partially addressed (import-time only) | PARTIAL |
| P1.10 Mixed plan types | **Bug** | VERIFIED |
| P2.1 Peer-set normalization | Unchecked | UNCHECKED |
| P2.2 Distribution treatment | Unchecked | UNCHECKED |
| P2.3 Freshness tolerances | Unchecked (informal partial coverage) | UNCHECKED |
| P2.4 Score clamping | **Gap** | VERIFIED |
| P2.5 Audit lineage | Likely missing | UNCHECKED |
| P2.6 Ranking efficiency | Partially addressed | CARRIED |
| P2.7 Retrieval hardening | Partially addressed | CARRIED |
| P2.8 Redirect/date-range validation | DONE | PARTIAL (date-range VERIFIED, redirect CARRIED) |

## Recommendation (superseded by Final Decision below)

Given the scope (22 items, several requiring product decisions, one — P0.3 — requiring a
data-sourcing feasibility question before any code work), recommend **not** proceeding to
implement all of this unilaterally. Two items are clean, low-risk, high-confidence fixes
that don't need a product decision and can go through the same TDD + mandatory-review
discipline used for the original 7-item workstream immediately: **P0.2** (category CAGR
×100) and **P2.4** (score clamping). Everything else needs one of: a product/business
decision (P1.3 sign-off, **P1.4's direct conflict with the existing PRD "thin category"
decision**), a scoping/feasibility pass (P0.3's TRI sourcing), or further investigation
before a fix is even well-defined (P1.8, P1.9's non-import-time scope, all of P2.1/P2.2/
P2.3/P2.5, and the unverified halves of P2.6/P2.7).

## Final Decision (2026-08-19, per-item disposition)

The recommendation above was reviewed item-by-item with the user; this table is the
authoritative disposition — treat it over the "Recommendation" section above where they
differ (P1.10 and P1.6 in particular moved from "not scoped yet" to "implemented this
round").

| Item | Disposition | Detail |
|------|-------------|--------|
| P0.2 Category CAGR % | **Implemented** | Round-2 fix, frontend-only, `CategoryRankingSection.tsx`. See `Docs/orchestration/correction-plan-round2-handoff.md`. |
| P0.3 TRI benchmark | **Lighter fix implemented + full fix deferred** | Labeled "(Price Return)" in `BenchmarkSection.tsx`'s `INDEX_LABELS`; full TRI sourcing blocked on an unanswered feasibility question. Full detail and revisit path: `Docs/orchestration/tri-benchmark-deferred-plan.md`. |
| P0.4 Cash-flow completeness | **Skipped, standing decision** | Hard-failing the benchmark comparison on any unresolved flow date conflicts with this codebase's established graceful-degrade pattern (`nav.py`, `ter.py`, `amfi_ter_client.py` all degrade rather than hard-fail). Not revisited unless that codebase-wide pattern itself changes. |
| P1.1 AAUM refresh scheduler | **Deferred to AWS deployment** | Gated behind `Docs/PRDs/Migration-Plan-SQLite-to-Postgres.md`'s Readiness Checklist, same as every other production-infra item in this codebase — building a scheduler ahead of that gate would be premature per CLAUDE.md's "AWS deployment happens once that document's Readiness Checklist is met, not before." On-demand `refresh_aaum_data(db)` remains the interim path. |
| P1.2 TER unavailable state | Already satisfied | No action needed (confirmed in the VERIFIED cross-reference above). |
| P1.3 Scorer governance | **Decision: existing methodology doc IS the approved version** | `Docs/Scorer-Methodology-Unifolio.md`'s numbers (45%/30%/25%, ±0.25/±0.05) match `scorer.py`'s constants exactly — treated as signed off, no further governance action pending. |
| P1.4 Minimum eligible peer count | **Decision: keep soft-flag, do not hard-suppress** | The correction plan's hard-suppression ask is explicitly rejected in favor of the existing PRD "Edge Cases table" soft-flag (`thin_category=True`) behavior — hiding data below 5 peers would harm real, common cases (niche Indian sectoral/international funds), not just hypothetical ones. |
| P1.5 Tie-aware ranking | **Skipped** | Real Decimal-precision, NAV-derived CAGR values essentially never produce exact ties; solving a practically-nonexistent problem. Revisit only if a real tied-ranking complaint ever surfaces. |
| P1.6 Switch handling in fund-level XIRR | **Implemented, full fix (not scoped down)** | `benchmark.py`'s fund-level XIRR now includes switch transactions with the correct sign convention; portfolio-level XIRR is unchanged (switches correctly stay excluded there). See the round-2 handoff doc for the exact design (`_signed_amount`'s `extra_debit_types` parameter, a `_fund_level_transactions` query). |
| P1.7 Benchmark family mapping (non-equity) | **Deferred** | Fixing this properly requires sourcing debt/gold/international indices that don't exist in this product at all today — a new-data-source feature, not a same-file correction, and PRD-04 explicitly scoped only 4 indices. Revisit alongside any future benchmark-family expansion, not as a standalone task. |
| P1.8 Valuation-date alignment | **Deferred, needs investigation first** | Not confirmed to the same depth as other items — a future pass should trace `compute_holdings`'s NAV-selection logic fully before deciding whether/how to fix. |
| P1.9 Identity matching (broader, non-import-time) | **Deferred** | Item 7 already covers the practical import-time risk; the TER/AAUM pipeline's looser fuzzy matcher (`MIN_MATCH_CONFIDENCE=0.55`) was deliberately left alone during Item 7 as a different matching context, and no live risk from that threshold has been confirmed. Revisit if a real TER/AAUM mismatch is ever observed. |
| P1.10 Mixed plan types in holdings | **Implemented** | Round-2 fix — `holdings.py`'s grouping key now includes `plan_type`; `HoldingsTable.tsx`'s React key updated to match. See the round-2 handoff doc. |
| P2.1 Peer-set normalization | **Deferred** | Enterprise-grade peer-set governance; not needed for this MVP's current scale. Unchecked — no investigation performed. |
| P2.2 Distribution treatment consistency | **Deferred** | Tied to the same underlying data-sourcing question as P0.3 (does the NAV series reflect reinvested distributions consistently); revisit alongside any future TRI work, not standalone. |
| P2.3 NAV/market-data freshness tolerances | **Deferred** | Informal partial coverage exists (Item 3's TER negative-cache/backoff, NAV warming TTLs) but no formal "acceptable age by asset type, disclosed when stale" policy. Enterprise-grade hardening, not MVP-blocking. |
| P2.4 Score clamping | **Implemented** | Round-2 fix, `scorer.py`. See the round-2 handoff doc. |
| P2.5 Audit lineage/metadata | **Deferred** | Governance/compliance tooling appropriate for a later maturity stage, not this MVP. |
| P2.6 Ranking efficiency | Already largely addressed | Items 2/4 cover the core ask; the unverified halves (Scorer's per-scheme loop reuse, specific bounded-query tests) are low-priority follow-ups, not tracked as open debt. |
| P2.7 TER/market-data retrieval hardening | **Deferred** | Request coalescing, bounded retries, source-health monitoring — production-ops maturity work, appropriate once real production traffic exists, not before. |
| P2.8 Redirect/date-range validation | Already done | No action needed. |

**Rationale for the defer/skip items as a group:** CLAUDE.md is explicit that this is "an
MVP prototype, not an enterprise system" and to "build what's scoped, don't build what isn't
scoped yet." The deferred items above (P1.1, P1.5, P1.7, P1.8, P1.9's broader scope, P2.1,
P2.2, P2.3, P2.5, P2.7) are all legitimate asks for an institutional-grade platform but
represent production-operations maturity, statistical edge-case hardening, or net-new data
sourcing — none are correctness bugs affecting a number a user is looking at today, unlike
P0.2/P1.10/P1.6/P2.4 (implemented this round) or P0.3 (partially addressed via honest
labeling). Each deferred item's table row above states its specific revisit trigger rather
than leaving it as an untriaged backlog entry.
