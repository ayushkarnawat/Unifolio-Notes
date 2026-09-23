# Analytics Dashboard — Internal Correction and Validation Plan

**Status:** Internal working document — not for stakeholder circulation  
**Date:** 18 August 2026  
**Companion document:** `Analytics-Dashboard-Formula-Implementation-Review.md`

## 1. Purpose

The stakeholder document states the financial methodology that the product should follow after correction and validation. This internal document records the implementation work required to make the dashboard conform to that standard.

Priorities mean:

- **P0 — Release blocker:** can materially misstate a displayed return or benchmark.
- **P1 — High:** can distort scoring, cost interpretation, comparability, or calculation coverage.
- **P2 — Control and hardening:** improves reliability, auditability, and performance after the core figures are correct.

---

## 2. P0 — Release-blocking corrections

### P0.1 Correct percentage presentation for XIRR

**Required outcome:** A decimal XIRR result of 0.10 must display as 10.00%.

**Why it matters:** XIRR calculation libraries normally return a decimal rate. Displaying that value directly with a percent sign understates the return by a factor of 100.

**Implementation acceptance criteria:**

- convert decimal rates to percentage values exactly once at the presentation boundary;
- apply the same rule to portfolio, family, fund, and benchmark XIRR;
- add fixtures for positive, negative, and unavailable XIRR; and
- verify that 0.10, −0.05, and 0 display as 10.00%, −5.00%, and 0.00% respectively.

### P0.2 Correct percentage presentation for category CAGR

**Required outcome:** A decimal CAGR result of 0.12 must display as 12.00%.

**Why it matters:** The category-return service and the interface must agree on whether a return is stored as a decimal or as percentage points.

**Implementation acceptance criteria:**

- establish one explicit return-unit contract across calculation, data transfer, and display;
- convert only at the presentation boundary;
- test 3-year CAGR, 5-year CAGR, and the blended return; and
- test missing and insufficient-history cases.

### P0.3 Use Total Return Index data for benchmark performance

**Required outcome:** Benchmark XIRR must use an approved TRI series rather than a price-only closing series.

**Why it matters:** A price index excludes reinvested distributions and is not comparable with a mutual-fund total return.

**Implementation acceptance criteria:**

- source and store the TRI level explicitly;
- record the benchmark identifier and series type;
- display “TRI” with the benchmark name;
- prohibit price-only series from entering total-return calculations; and
- validate selected sample periods independently against the source series.

### P0.4 Reject incomplete benchmark cash-flow paths

**Required outcome:** Every material investor cash flow must be represented in the hypothetical benchmark investment.

**Why it matters:** Silently omitting a transaction date changes the economic question and can materially bias benchmark XIRR.

**Implementation acceptance criteria:**

- define a single trading-day convention for holidays and weekends;
- resolve every cash-flow date under that convention;
- return “benchmark unavailable” if any material flow remains unresolved;
- expose the missing date in internal diagnostics; and
- test weekend, market-holiday, missing-history, and stale-data cases.

---

## 3. P1 — High-priority corrections

### P1.1 Establish a production AAUM refresh process

**Required outcome:** AAUM used in category-weighted TER and return calculations is current, populated, and traceable.

**Current work needed:** A data-ingestion capability exists, but it needs a scheduled production caller, freshness monitoring, failure alerting, and end-to-end verification that the analytics calculations receive the refreshed values.

**Acceptance criteria:**

- defined refresh schedule and effective period;
- successful and failed-run records;
- freshness visible to analytics services;
- category coverage report; and
- no weighted result published when materially insufficient AAUM is available.

### P1.2 Distinguish missing TER from a genuine 0% TER

**Required outcome:** Missing TER or AAUM must result in an unavailable cost comparison, not a zero value or a low-fee bonus.

**Acceptance criteria:**

- use a distinct unavailable state throughout calculation and display;
- calculate portfolio TER over covered holdings and disclose coverage;
- do not award or deduct the TER adjustment without both scheme TER and category reference TER; and
- label the effective date of the TER input.

### P1.3 Finalise scorer governance as one approved methodology

**Required outcome:** Product requirements, financial methodology, calculation rules, tests, and dashboard wording must all specify the same scoring model.

**Decision to record:** Approve or amend the intended model of:

- 45% return;
- 30% downside risk;
- 25% consistency;
- equal peer-percentile tier bands; and
- a limited ±0.25 TER adjustment outside a ±0.05 percentage-point tolerance.

Earlier requirement language and later scoring decisions should be reconciled in one versioned policy before sign-off.

### P1.4 Enforce the minimum eligible peer count

**Required outcome:** Do not publish peer percentiles, tiers, or scores when fewer than five eligible peer schemes are available.

**Acceptance criteria:**

- enforce the rule in the calculation layer, not only in the interface;
- return the eligible peer count;
- show a clear insufficient-peer message; and
- test peer counts of 0, 1, 4, 5, and more than 5.

### P1.5 Use tie-aware ranking

**Required outcome:** Schemes with equal component or composite values receive equal ranking treatment.

**Why it matters:** Arbitrary ordering of ties can move economically identical schemes into different percentiles or tiers.

**Acceptance criteria:**

- adopt a documented fractional-rank or equivalent tie policy;
- apply it to return, risk, consistency, and final composite ranking; and
- test ties at tier boundaries.

### P1.6 Include switch transactions correctly in fund-level XIRR

**Required outcome:**

- portfolio XIRR excludes internal switches because no money enters or leaves the overall portfolio;
- source-fund XIRR treats a switch-out as a positive flow; and
- destination-fund XIRR treats a switch-in as a negative flow.

**Acceptance criteria:** Add paired switch-in/switch-out tests and confirm that the overall portfolio cash-flow total remains unchanged.

### P1.7 Use exposure-appropriate benchmark families

**Required outcome:** Debt, hybrid, gold, international, and other non-equity exposures must not be compared automatically with a broad Indian equity benchmark.

**Acceptance criteria:**

- approve a category-to-TRI benchmark policy;
- use a documented fallback only where justified;
- disclose the selected benchmark to the user; and
- return unavailable where no defensible benchmark exists.

### P1.8 Align closing value and valuation date for XIRR

**Required outcome:** The terminal market value must be calculated as of the same date used for the terminal XIRR cash flow.

**Acceptance criteria:**

- apply a defined NAV cut-off and staleness policy;
- prevent a current value from being attached to an earlier or unrelated date;
- disclose partial valuation coverage; and
- return unavailable if a material holding lacks an eligible terminal NAV.

### P1.9 Strengthen scheme, plan, and TER identity matching

**Required outcome:** Transactions, NAVs, TER, AAUM, and peer data must refer to the same scheme, plan, option, and effective period.

**Acceptance criteria:**

- prefer stable identifiers over name-only matching;
- explicitly distinguish direct and regular plans;
- explicitly distinguish growth and distribution options;
- flag ambiguous or multiple matches; and
- retain source and effective-date lineage.

### P1.10 Handle mixed plan types within an aggregated holding

**Required outcome:** Where the same economic scheme appears in both direct and regular plans, preserve each plan's own units, NAV, TER, and score inputs rather than collapsing them into one ambiguous record.

---

## 4. P2 — Control, accuracy, and hardening improvements

### P2.1 Normalise category peer sets

Prevent multiple share classes or options of the same underlying portfolio from unintentionally dominating a peer average or median. Adopt one representative observation per economic portfolio where the methodology requires it.

### P2.2 Confirm distribution treatment in return histories

Growth and distribution options must be compared on a total-return-equivalent basis. Where a NAV series does not incorporate distributions, include reinvested distributions or exclude the series from like-for-like comparisons.

### P2.3 Enforce NAV and market-data freshness tolerances

Define acceptable age by asset type, disclose stale inputs, and prevent stale values from being presented as current without warning.

### P2.4 Clamp adjusted scores to the valid range

After the TER adjustment:

> **Final score = Minimum of 100 and maximum of 0 and the adjusted score**

Test both lower and upper boundaries.

### P2.5 Add calculation lineage and audit metadata

For each material dashboard result, retain:

- valuation date;
- data-source date;
- methodology version;
- input coverage;
- benchmark identifier and series type;
- peer-category identifier and peer count; and
- reason when the result is unavailable.

### P2.6 Improve scoring and ranking efficiency

Compute shared peer histories and category statistics once per category and reporting date rather than repeatedly for each scheme. Add bounded query and timing tests so larger categories remain reliable.

### P2.7 Harden TER and market-data retrieval

Add request coalescing, bounded retries, negative-result caching, source-health monitoring, and explicit fallback rules. These measures reduce inconsistent results when an upstream source is slow or unavailable.

### P2.8 Validate redirects and trading-day freshness

When retrieving benchmark or market data, validate that the final source and date range match the requested series and period. Do not accept a successful response that resolves to the wrong instrument or stale data.

---

## 5. What “Beta is not implemented” means

### 5.1 Financial meaning of Beta

Beta is a measure of how sensitively a fund's returns have moved relative to a selected benchmark:

> **Beta = Covariance of fund returns and benchmark returns ÷ Variance of benchmark returns**

Broad interpretation:

- **Beta = 1.0:** the fund has historically moved with roughly the same sensitivity as the benchmark;
- **Beta above 1.0:** the fund has historically moved more strongly than the benchmark; and
- **Beta below 1.0:** the fund has historically moved less strongly than the benchmark.

Beta is benchmark-dependent, frequency-dependent, and period-dependent. It does not measure total risk and does not indicate whether a fund generated a good return.

### 5.2 Meaning in the current product scope

“Not implemented” means there is presently no approved Beta calculation, data contract, dashboard field, or user-facing Beta feature.

It does **not** mean that an agreed MVP feature was accidentally omitted. Beta is not specified as a PRD-04 MVP analytics requirement. The current peer score uses **downside deviation**, which answers a different question: how severe the negative return observations have been, regardless of their relationship with a benchmark.

### 5.3 Recommendation

Keep Beta outside the stakeholder sign-off document for the present scope. If added later, first approve:

- the benchmark for every scheme category;
- the return frequency, such as daily, weekly, or monthly;
- the historical lookback period;
- the minimum number of observations;
- the treatment of distributions and missing dates; and
- whether the output is raw Beta, rolling Beta, or both.

Reliable, category-appropriate TRI benchmarks should be in place before Beta is introduced.

---

## 6. Recommended implementation sequence

1. Fix the two percentage-display contracts and lock them with tests.
2. Replace price-index benchmarking with verified TRI data.
3. Enforce complete benchmark cash-flow coverage.
4. Establish AAUM and TER missing-data semantics and data freshness.
5. Approve one scorer specification and implement peer-count and tie controls.
6. Correct fund-level switches, valuation-date alignment, and plan identity.
7. Introduce category-appropriate benchmarks.
8. Add audit lineage, coverage reporting, performance controls, and retrieval hardening.
9. Run independent numerical reconciliation against controlled spreadsheet examples.
10. Submit the stakeholder methodology for financial sign-off only after all P0 and P1 items pass.

---

## 7. Completion gate

The analytics methodology should be treated as implementation-complete when:

- every P0 item is corrected and covered by automated and spreadsheet-reconciliation tests;
- every P1 item is corrected or explicitly accepted by the financial/product owner;
- displayed percentages agree with independently calculated examples;
- benchmark calculations use complete, approved TRI histories;
- missing values cannot appear as zero or create a score benefit;
- peer scores disclose category, peer count, coverage, and methodology version; and
- the stakeholder reviewer has signed the companion methodology document.
