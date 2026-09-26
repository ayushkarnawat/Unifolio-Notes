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

### Addendum, 2026-09-23 (batch 4d) — annex now ingested; Scorer v2 has an ADR

`Docs/Scorer-v2-Calculation-Annex-Open-Questions.md`, cited above as "not yet
ingested," is now in this vault. Its open question 6 ("Path A: build the
overlay in-house vs. Path B: license a data feed") matches this
investigation's own framing and resolution exactly, with no new information
on that specific question. The annex adds 12 further open questions (rolling
window definitions, recency-weighting curve, category-average definition,
minimum peer-set size, and others) spanning the rest of the Scorer v2
methodology, none of which this investigation covers.

Scorer v2 as a whole now has its own record:
[ADR-019](../03-decisions/ADR-019-scorer-v2-proprietary-methodology.md),
which captures the approved-at-formula-level methodology and cross-links the
full annex. This investigation's scope remains narrowed to the Valuation
Overlay component only; its "remaining uncertainty" note above (no ADR yet
existed) is superseded by ADR-019's existence, not by any change to this
investigation's own findings.

Evidence: `08-evidence/documents/Scorer-v2-Calculation-Annex-Open-Questions.md`

### Addendum, 2026-09-24 (batch 6c) — three of four holdings-dependent features turn out not to need Path A's hardest part; a Layer 1/Layer 2 split

This entry's "Root cause" section states the AMC-disclosure-ingestion format
survey (Path A, step 1) is the hardest sub-problem in building the
Valuation Overlay. A separate raw note, investigating three *other*
holdings-dependent features that PRD-03/PRD-04 had deferred for the same
"no aggregated AMC holdings feed" reason (cap-wise composition, stock-level
fund overlap detection, equity look-through), found a genuinely new fact
that narrows — but does not resolve — this investigation's own Path A cost
estimate: **AMFI itself publishes a free, official, biannual large/mid/
small-cap stock classification list**, mandated by SEBI circular 2017/114
(at `amfiindia.com/otherdata/categorisation-of-stocks`) — a fixed
rank-based classification (top 100 = large, 101–250 = mid, 251+ = small).
This is a **hypothesis carried over from a raw note, not independently
verified against the live AMFI site or this codebase by this vault** —
flagged accordingly, consistent with this vault's practice of not treating
an unverified claim as settled fact.

If accurate, this means cap-wise composition, stock overlap detection, and
equity look-through need only the shared holdings-ingestion pipeline (Layer
1) plus, for cap-wise composition specifically, that one free AMFI list —
no paid vendor. The Valuation Overlay (this investigation's actual
subject) is the outlier of the four: it additionally needs stock-level
PE/PB fundamentals, which remains the harder, possibly-paid dependency this
investigation already found (Path A step 2 / Path B). The raw note frames
this as a Layer 1 (shared holdings-ingestion foundation) / Layer 2 (up to
four independent consumer features sitting on top of it) split, and raises
an as-yet-undecided scope question for Layer 1 itself: ingest holdings only
for schemes users actually hold (~50-150 schemes, lazily/on-demand — enough
for look-through, overlap detection, and cap-wise composition, none of
which compare a fund's holdings against its category peers) versus the
full category universe (matching how NAV/AAUM/TER are already ingested
today, but a materially larger scope). Branch names mentioned in the raw
note for this track: `feat/scorer-v2` (this investigation's Valuation
Overlay work) and `feat/fund-holdings-foundation` (the separate Layer 1 +
three-feature track) — not verified against the actual repository by this
vault.

This does not change this investigation's own resolution (Path A vs. Path B
for PE/PB specifically remains an open build-vs-buy decision) — it records
that three sibling deferred features, previously assumed to share the same
"hard" data gap, may be materially cheaper than the Valuation Overlay once
the shared holdings pipeline exists.

Evidence: `08-evidence/documents/everything defered till now.md`,
`08-evidence/documents/Fund scorer notes.md`.
