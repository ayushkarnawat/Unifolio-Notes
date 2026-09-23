# INV-011: Can Scorer v2's PE/PB Valuation Overlay be built, and how

Status: Closed — feasibility findings delivered, build-vs-buy decision not yet made
Date: 2026-08-24
Related: [ADR-010](../03-decisions/ADR-010-fund-scorer-composite-formula.md) (the Unifolio Scorer composite formula, the component this overlay would extend); [R-015](../07-risks-and-debt.md) (unrelated — a different, already-clarified fund-scoring-methodology question, noted here only to rule out confusion)

## For stakeholders

Scorer v2 proposes adding a fifth ingredient to the fund score — how
expensive a fund's underlying stocks are, relative to their category — but
before that could be designed, someone had to check whether the raw data
even exists to build it. It doesn't, not for free: no official Indian
regulator or index provider publishes a fund's price-to-earnings or
price-to-book ratio as an open, programmatic feed, and nothing like it
exists anywhere in this codebase today. Two real paths forward were found —
build it in-house from each fund company's own portfolio disclosures (slow
and open-ended, but consistent with how every other part of the fund score
is calculated), or pay for a licensed data feed (fast, but a budget
decision, not an engineering one) — and a third path (scraping an
aggregator website) was ruled out as too fragile and legally risky for a
financial product. Which of the two real paths to take is a business
decision that hasn't been made yet.

## Technical detail

### Trigger

Scorer v2 proposes a Valuation Overlay component (5% weight, fund PE/PB vs.
category average) as an addition to ADR-010's current three-ingredient
composite (Return/Risk/Consistency). Before that component can be designed,
it has to be established whether fund-level PE/PB data is obtainable at all
inside this codebase's existing patterns.

### Expected vs. observed

Expected: either a data source already exists to extend, or the closest
precedent (NAV/AAUM/TER/NSE-index clients under `backend/app/integrations/`)
suggests a comparably simple integration.

Observed: neither holds. No holdings, portfolio-disclosure, or
stock-fundamentals integration exists anywhere in the backend today
(`backend/app/services/analytics/`, `backend/app/integrations/` both
searched) — valuation is a genuinely new data category, not an extension of
something partially there. No official, free, programmatic feed for
fund-level PE/PB exists in India either: SEBI's monthly cumulative report
and half-yearly portfolio disclosure (Regulation 59A) cover holdings,
turnover ratio, and (per a 2025 circular) Information Ratio, but not
valuation ratios; Value Research and Morningstar India publish no public
API.

### Paths considered

1. **Build in-house** from AMC portfolio disclosures.
2. **Buy a licensed feed** (Morningstar Direct, ICRA Analytics, CRISIL).
3. **Scrape an aggregator site** (Value Research, Moneycontrol).

### Findings

| Path | Expected signal | Actual finding | Conclusion |
|---|---|---|---|
| A — build in-house | A feasible, pattern-consistent pipeline | Requires: (1) ingesting each AMC's own portfolio-disclosure file — SEBI mandates half-yearly, most AMCs publish monthly, but **no standard format or API exists**, each AMC publishes its own file on its own site (flagged as the hardest sub-problem, harder than the PE/PB numbers themselves); (2) stock-level PE/PB per constituent holding, obtainable from paid vendors (e.g. FinEdge) well under global-vendor Bloomberg/Refinitiv pricing; (3) fund-level PE/PB computed as a **weighted harmonic mean** across holdings — Value Research's own published methodology for this exact calculation, not an internal guess ("the accurate way to calculate the P/E ratio of a mutual fund is to use the weighted harmonic mean method... appropriate weightage to both price and earnings of each stock"); (4) category aggregation via the scorer's existing percentile-ranking pattern | Technically consistent with how every other scorer component is built (computed from primitives, not sourced pre-computed) — but the AMC-disclosure ingestion format survey is a genuinely open-ended spike, not a bounded task |
| B — buy a licensed feed | Zero engineering lift for the number itself | Confirmed viable (Morningstar Direct / ICRA Analytics / CRISIL license fund-level PE/PB directly) | A cost/contract decision, not an engineering one |
| C — scrape an aggregator | A fast unofficial source | Fragile, ToS risk | Not recommended for a production financial product without legal review; not pursued further |

### Root cause / underlying fact

Not applicable in the usual investigation sense — this is a feasibility
study, not a defect. The underlying fact this closes on: **no external
party publishes fund-level PE/PB for the Indian market as a free,
programmatic feed**, so any path forward costs either build time
(Path A) or licensing budget (Path B).

### Resolution

Not resolved to a single path. Path A ("build in-house") is judged the
better fit for this codebase's existing pattern of owning every
calculation from primitives rather than sourcing pre-computed numbers, but
A vs. B is explicitly stated to be a build-cost-and-time vs. license-cost
tradeoff outside engineering's authority to decide alone — captured as open
question #6 in `Docs/Scorer-v2-Calculation-Annex-Open-Questions.md` (a
code-repo document, not yet ingested into this vault). If Path A is chosen,
the AMC-disclosure ingestion format survey is recommended as the first
spike, since it is judged the piece most likely to blow up in scope.

### Remaining uncertainty

- Whether Path A or B is chosen is an open product/budget decision, not
  captured anywhere else in this vault as of this entry.
- The AMC-disclosure format survey itself (how many AMCs, how consistent
  their formats are) has not been run — Path A's cost estimate above is a
  judgment call, not a measured spike result.
- Scorer v2 more broadly (of which this overlay is one component) has no
  ADR of its own yet in this vault; this investigation covers only the
  Valuation Overlay's data-feasibility question, not the rest of v2's design.

### Evidence

- `08-evidence/documents/orchestration/scorer-v2-pe-pb-feasibility-findings.md`
