# Unifolio Analytics Dashboard
## Financial Calculation Methodology for Review and Sign-off

**Prepared for:** Financial and accounting review  
**Document date:** 18 August 2026  
**Purpose:** To explain, in financial and mathematical terms, how the analytics dashboard calculates and presents portfolio measures.

---

## 1. Purpose of this document

This document describes the calculation policy to be followed by the Unifolio analytics dashboard. It is written for review by a Chartered Accountant, finance leader, auditor, or other stakeholder who needs to validate the financial logic without reviewing software code.

The dashboard is intended to answer five broad questions:

1. What is the investor's portfolio worth, and how is it allocated?
2. What ongoing expense ratio is the investor effectively bearing?
3. How have the portfolio and individual schemes performed, allowing for the timing of cash flows?
4. How does the portfolio compare with an appropriate market benchmark?
5. How are mutual funds compared with their peers using return, risk, and consistency?

The governing principles are:

- calculations use like-for-like units and periods;
- percentages and decimal rates are converted consistently;
- portfolio-level results are value-weighted where appropriate;
- investor returns reflect actual cash-flow dates;
- benchmarks use total returns, including reinvested distributions;
- incomplete material data is shown as unavailable rather than silently treated as zero; and
- displayed figures are rounded only after the underlying calculation is complete.

---

## 2. Common definitions

| Term | Meaning in this document |
|---|---|
| Units | Number of mutual-fund units held |
| NAV | Net Asset Value per unit |
| Current value | Units multiplied by the applicable NAV |
| Portfolio value | Sum of the current values of all included holdings |
| TER | Total Expense Ratio charged by a scheme, expressed per annum |
| AAUM | Average Assets Under Management |
| CAGR | Compounded Annual Growth Rate |
| XIRR | Annualised money-weighted return for irregularly dated cash flows |
| TRI | Total Return Index, which includes both price movement and reinvested distributions |
| Peer group | Comparable schemes within the same defined category |
| Percentage point | The arithmetic difference between two percentages; for example, 1.20% minus 0.80% equals 0.40 percentage points |

---

## 3. Portfolio value and asset allocation

### 3.1 Value of each holding

For each holding:

> **Current value = Units held × Applicable NAV**

The applicable NAV is the latest eligible NAV as at the dashboard valuation date.

### 3.2 Total portfolio value

> **Portfolio value = Sum of the current values of all holdings**

### 3.3 Allocation percentage

Holdings are grouped into the required reporting buckets, such as equity, debt, hybrid, gold, international, or other categories.

> **Allocation % for a bucket = Bucket current value ÷ Total portfolio value × 100**

Example: if equity holdings are worth ₹7,00,000 and the total portfolio is worth ₹10,00,000, the equity allocation is:

> ₹7,00,000 ÷ ₹10,00,000 × 100 = **70.00%**

Subject to rounding, all displayed allocation percentages should total 100%.

### 3.4 Financial interpretation

Allocation is a point-in-time market-value measure. It is not based on the original amount invested and therefore changes as NAVs and holdings change.

---

## 4. Total Expense Ratio (TER)

AMFI describes TER as the total expenses charged to a scheme as a percentage of its average net assets. The dashboard uses the applicable published TER for each scheme and plan. [AMFI — Total Expense Ratio](https://www.amfiindia.com/ter-of-mf-schemes)

### 4.1 Portfolio weighted TER

A simple average would give a small holding the same importance as a large holding. The dashboard therefore uses a current-value-weighted calculation:

> **Portfolio weighted TER = Sum of (Holding value × Holding TER) ÷ Sum of holding values covered by TER data**

Example:

| Holding | Current value | TER | Weighted contribution |
|---|---:|---:|---:|
| Fund A | ₹6,00,000 | 0.60% | ₹6,00,000 × 0.60% |
| Fund B | ₹4,00,000 | 1.20% | ₹4,00,000 × 1.20% |

> Weighted TER = [(₹6,00,000 × 0.60%) + (₹4,00,000 × 1.20%)] ÷ ₹10,00,000 = **0.84% per annum**

### 4.2 Direct-plan and regular-plan comparison

Where corresponding direct and regular plan TERs are available:

> **TER difference = Regular-plan TER − Direct-plan TER**

If the regular-plan TER is 1.20% and the direct-plan TER is 0.80%, the difference is **0.40 percentage points per annum**.

This difference is a cost-rate comparison. It should not be presented as an exact guaranteed rupee saving because future portfolio values, TERs, taxes, and cash-flow timing can vary.

### 4.3 Data and presentation controls

- TER must match the correct scheme and plan type.
- A missing TER must be shown as unavailable, not as 0%.
- If the portfolio TER covers less than the full portfolio, the coverage percentage should be disclosed.
- TERs from different effective dates should be identified where the age of the data is material.

---

## 5. Category return analytics

Schemes are compared only within an appropriate peer category, based on the applicable mutual-fund categorisation framework. [SEBI — Master Circular for Mutual Funds](https://www.sebi.gov.in/sebi_data/attachdocs/mar-2026/1774024028162.pdf)

### 5.1 CAGR for a scheme or category representative

For an observation period of *n* years:

> **CAGR = (Ending value ÷ Beginning value)^(1 ÷ n) − 1**

The result is multiplied by 100 when displayed as a percentage.

Example: if an investment value grows from 100 to 140 over three years:

> CAGR = (140 ÷ 100)^(1/3) − 1 = **11.87% per annum**

Returns should be based on an adjusted or total-return series so that distributions are treated consistently.

### 5.2 Combined three-year and five-year return measure

For peer comparison, the dashboard places greater weight on the longer period:

> **Blended return score input = 40% × 3-year CAGR + 60% × 5-year CAGR**

Example: if three-year CAGR is 15% and five-year CAGR is 12%:

> (40% × 15%) + (60% × 12%) = **13.20%**

The longer period receives greater weight because it reflects performance across more market conditions.

### 5.3 Category average and AAUM-weighted return

When calculating an asset-weighted category return:

> **AAUM-weighted category return = Sum of (Scheme return × Scheme AAUM) ÷ Sum of AAUM for schemes with usable return data**

This answers: “What return did the average rupee invested in this category experience?” It differs from an equal-weighted average, which answers: “What did the average scheme experience?”

### 5.4 Ranking and percentiles

Each eligible scheme is ranked against its peer group. A percentile converts that rank to a 0–100 scale:

- higher return receives a higher return percentile;
- schemes with equal values receive equal treatment; and
- the eligible peer count is disclosed.

Peer comparison is published only when at least five eligible schemes are available. This prevents an apparently precise score from being produced from an unreasonably small comparison set.

---

## 6. Unifolio peer-comparison score

The Unifolio score is a relative peer-comparison measure. It is not a forecast, credit rating, or recommendation to buy or sell.

### 6.1 Components and weights

| Component | Weight | What it measures |
|---|---:|---|
| Return | 45% | Medium- and long-term return relative to peers |
| Downside risk | 30% | Frequency and magnitude of negative return observations |
| Consistency | 25% | Frequency with which the scheme outperforms the peer median |

> **Base score = 45% × Return percentile + 30% × Downside-risk percentile + 25% × Consistency percentile**

### 6.2 Return component

The return component uses the blended three-year/five-year measure explained in Section 5.2. Higher blended return is better, subject to being compared only with the same peer category.

### 6.3 Downside-risk component

For each periodic return observation, positive observations are set to zero and negative observations retain their value. Downside deviation is then:

> **Downside deviation = Square root of [Sum of squared negative returns ÷ Number of usable return observations]**

Lower downside deviation is better. The peer ranking is therefore reversed for this component: the scheme with lower downside deviation receives the higher percentile.

This measure focuses on harmful variability instead of treating upside and downside volatility as equally undesirable.

### 6.4 Consistency component

For each rolling 12-month period, a scheme's return is compared with the median return of its eligible peer group for the same period.

> **Consistency rate = Number of periods in which scheme return is above peer median ÷ Number of valid comparison periods × 100**

Example: if a scheme exceeds the peer median in 30 of 40 valid periods:

> 30 ÷ 40 × 100 = **75% consistency**

Higher consistency is better.

### 6.5 Composite score example

Suppose a scheme has:

- return percentile: 78;
- downside-risk percentile: 65; and
- consistency percentile: 70.

Then:

> Base score = (0.45 × 78) + (0.30 × 65) + (0.25 × 70) = **72.10**

The scheme's final relative position is determined within its peer group.

### 6.6 Score tiers

| Peer percentile | Tier | Interpretation |
|---:|---:|---|
| 80 to 100 | 5 | Top peer band |
| 60 to below 80 | 4 | Above-average peer band |
| 40 to below 60 | 3 | Middle peer band |
| 20 to below 40 | 2 | Below-average peer band |
| 0 to below 20 | 1 | Bottom peer band |

Equal-percentile boundaries are handled consistently, and tied schemes receive the same ranking treatment.

### 6.7 TER adjustment to the score

The score may include a small cost adjustment after the performance, downside-risk, and consistency assessment.

1. Calculate the category's AAUM-weighted TER.
2. Compare the scheme TER with that category TER.
3. Apply no adjustment when the difference is within ±0.05 percentage points.
4. Apply a **+0.25 point** adjustment when the scheme is meaningfully cheaper.
5. Apply a **−0.25 point** adjustment when the scheme is meaningfully more expensive.

The adjusted score is restricted to the 0–100 range. This small adjustment allows cost to act as a tie-breaker without overpowering the main analytical factors. It does not change the scheme's underlying peer tier.

Where TER or category AAUM is unavailable, the adjustment is shown as unavailable and the score is not represented as having earned a cost benefit.

---

## 7. Portfolio-level Unifolio score

The portfolio score is weighted by the current value of each scored holding:

> **Portfolio score = Sum of (Holding current value × Holding score) ÷ Sum of current values of scored holdings**

Example: Fund A is worth ₹6,00,000 and has a score of 80; Fund B is worth ₹4,00,000 and has a score of 60.

> [(₹6,00,000 × 80) + (₹4,00,000 × 60)] ÷ ₹10,00,000 = **72.00**

The dashboard should also disclose what percentage of the portfolio value was covered by eligible fund scores.

---

## 8. Investor return using XIRR

Ordinary CAGR is unsuitable when an investor makes purchases, redemptions, SIPs, or other transactions on different dates. XIRR calculates an annualised money-weighted return using the exact cash-flow dates. [Microsoft — XIRR function](https://support.microsoft.com/en-us/excel/functions/xirr-function)

### 8.1 Cash-flow signs

From the investor's perspective:

- purchases and additional investments are negative cash flows;
- redemptions and other amounts received are positive cash flows; and
- the portfolio's closing market value is a final positive cash flow on the valuation date.

Internal portfolio switches do not represent cash entering or leaving the investor's overall portfolio and are excluded from portfolio-level XIRR. For an individual fund, the switch-out is treated as an amount received from that fund and the switch-in as an investment into the receiving fund.

### 8.2 Mathematical equation

XIRR is the value of *r* that makes the net present value of all dated cash flows equal to zero:

> **Sum of [Cash flow i ÷ (1 + r)^((Date i − First date) ÷ 365)] = 0**

The result *r* is a decimal annual rate. Therefore, a calculated value of 0.10 is displayed as **10.00%**, not 0.10%.

### 8.3 Validity controls

- There must be at least one negative and one positive cash flow.
- Dates must be valid and must correspond to their respective amounts.
- The closing value and valuation date must refer to the same reporting point.
- All material holdings and transactions within the selected scope must be included.
- If a reliable solution cannot be found, the dashboard should show the return as unavailable rather than substitute zero.

---

## 9. Benchmark comparison

The benchmark comparison answers: “What would the same dated external cash flows have become if invested in the selected benchmark?”

### 9.1 Total Return Index requirement

The comparison uses an appropriate **Total Return Index**, not only a price index. A TRI includes both market-price movement and reinvested distributions and therefore provides a like-for-like comparison with reinvestment-based mutual-fund returns. [NSE Indices — Total Return Index](https://www.niftyindices.com/resources/index-concepts/total-return-index)

### 9.2 Same-cash-flow method

For each investor cash flow on date *t*:

> **Hypothetical benchmark units purchased or sold = Investor cash flow amount ÷ Benchmark TRI level on date t**

At the reporting date:

> **Hypothetical benchmark value = Accumulated benchmark units × Benchmark TRI level on reporting date**

The benchmark XIRR is then calculated using the same investor cash flows and this hypothetical closing value.

Using identical amounts and dates isolates the difference attributable to the investment performance rather than the investor's contribution schedule.

### 9.3 Completeness rule

Every material cash-flow date must have a valid benchmark observation under the defined trading-day convention. If a complete benchmark path cannot be established, the result is shown as unavailable; a partial cash-flow comparison is not presented as a valid benchmark return.

### 9.4 Benchmark selection

Benchmark selection follows the economic exposure being measured:

- portfolio-level reporting uses the approved broad-market or policy benchmark;
- equity, debt, hybrid, gold, international, and other exposures use appropriate approved total-return benchmarks; and
- individual schemes use their category-appropriate benchmark where available.

The benchmark name and whether it is a TRI are displayed with the result.

---

## 10. Family or multi-portfolio aggregation

When multiple family members or portfolios are combined:

- current values are added across the selected portfolios;
- allocations are recalculated from the combined current values;
- weighted TER and weighted scores are recalculated using the combined holdings; and
- XIRR is recalculated from the combined dated cash flows and combined closing value.

Portfolio percentages or XIRRs are **not** combined using a simple arithmetic average, because that would ignore differences in portfolio size and cash-flow timing.

---

## 11. Rounding policy

- All calculations retain full available precision internally.
- Currency is normally displayed to the nearest rupee or the chosen reporting unit.
- Rates and returns are normally displayed to two decimal places.
- Scores are normally displayed to one or two decimal places.
- Rounding occurs at presentation, not at each intermediate step.
- Small differences caused solely by display rounding are acceptable and should not change the underlying calculation.

---

## 12. Data-quality and exception policy

Financial analytics are only as reliable as their underlying data. The following policy applies across the dashboard:

- zero is used only when the true financial value is known to be zero;
- unknown or unavailable data is not converted into zero;
- stale or incomplete market data is identified;
- schemes are matched to the correct plan, option, and peer category;
- return calculations use complete, consistently dated histories;
- coverage ratios are disclosed for partial portfolio metrics; and
- material methodology or benchmark changes are versioned and documented.

---

## 13. Overall conclusion

The methodology is moving in the correct financial direction because it distinguishes among the different questions being answered:

- market value and allocation use current-value arithmetic;
- portfolio costs use value-weighted TER rather than a simple average;
- scheme performance uses compounded annual returns;
- investor experience uses dated, money-weighted XIRR;
- benchmark comparison replays the investor's cash flows against a total-return index; and
- peer scoring separates return, downside risk, consistency, and a limited cost adjustment.

These approaches are financially coherent provided the data-completeness, peer-comparability, plan-matching, and total-return benchmark controls described in this document are maintained.

---

## 14. Review and sign-off

The reviewer is requested to confirm whether the following calculation policies are acceptable:

| Review point | Reviewer confirmation |
|---|---|
| Current-value basis for portfolio allocation |  |
| Current-value-weighted portfolio TER |  |
| CAGR methodology and 40%/60% three-year/five-year blend |  |
| 45% return, 30% downside-risk, and 25% consistency score |  |
| Limited ±0.25 TER adjustment with a ±0.05 percentage-point tolerance |  |
| Value-weighted portfolio score |  |
| XIRR treatment of dated investor cash flows and closing value |  |
| Same-cash-flow benchmark comparison using TRI data |  |
| Unavailable-data and minimum-peer controls |  |

**Reviewed by:** ______________________________  
**Designation:** ______________________________  
**Organisation:** _____________________________  
**Date:** ____________________________________  
**Comments / qualifications:** ________________________________________________

