# ADR-010: The Unifolio Scorer — a three-ingredient composite, deliberately unlike Morningstar

Status: Accepted
Date: 2026-08-13
Related: `02-journey/2026-08-12-delegated-execution-and-the-fund-scorer.md`; contradicts `05-docs/explanation/fund-scoring-methodology.md` as currently written — see R-015

## For stakeholders

The Scorer answers one question — "how good is this fund, really?" — as a
number and a tier from 1 to 5, with the reasoning always shown alongside it.
The formula was settled with the product owner on 2026-08-13: 45% past
return, 30% risk, 25% consistency. Two choices give it its character. Risk
is measured only by how far a fund falls, not by how much it moves in
general, because a fund rising sharply is not a risk to an investor.
Consistency asks how often the fund beat its category over rolling
twelve-month periods — a plain question that existing ratings largely do not
ask, and the stated reason the score is worth having at all rather than
being a copy of Morningstar or CRISIL. A small bonus or penalty is applied
for being cheaper or pricier than comparable funds, capped so that cost
nudges the answer but never drives it. The score is presented as a modelling
opinion, never as a neutral fact.

**This vault currently describes the fund score differently**, in a document
written from the product requirements before this conversation happened.
That conflict is recorded as R-015 and is not resolved by this record.

## Technical detail

### Context

PRD-04 FR-5 through FR-7 require a per-fund quality score, a portfolio-level
roll-up, and a breakdown that prevents the score from being shown as a bare
number or a single-word label. PRD-04 itself also states, in its own risk
table, that the scorer must never be presented as a neutral fact.

The 2026-08-10 analytics design doc sketched the scorer; the formula was
then revised in conversation with the product owner on 2026-08-13. The
design flagged, rather than quietly absorbed, that the resulting formula
deviates from the two-ingredient description in the schema document's FR-5a.

### Decision drivers

- Differentiation was an explicit requirement: the score must not be a
  restatement of what rating agencies already publish.
- Every ingredient must be explainable to a non-technical user in one
  sentence.
- The schema's scores table is fixed; the decision must not require new
  columns.
- `Decimal` throughout — no floating point anywhere in the calculation.
- The score must degrade sensibly in thin categories rather than producing a
  confident number from five data points.

### Options considered

#### Option 1: Replicate a Morningstar-style risk-adjusted return rating
Advantages: familiar; defensible by precedent; less to explain.
Disadvantages: offers a user nothing they cannot already get, and the
product's own requirement was to be different. Rejected.

#### Option 2: Two ingredients — return and risk only
Advantages: simplest; matches the schema document's FR-5a description.
Disadvantages: return and risk are both point-in-time summaries; neither
captures whether a fund's performance is repeatable. This was the initial
sketch and was superseded on 2026-08-13.

#### Option 3: Standard deviation as the risk measure
Advantages: the conventional choice; widely understood.
Disadvantages: penalises upside movement, which is not a risk an investor
wants protecting from. Rejected in favour of downside deviation.

#### Option 4: Three ingredients — return, downside risk, rolling consistency (chosen)
Advantages: the consistency ingredient is the concrete differentiator and is
trivially explainable ("how often did it beat its peers?"); downside-only
risk matches how a retail investor actually experiences loss.
Disadvantages: more computation, a longer history requirement, and a third
thing to explain.

### Decision

| Ingredient | Weight | Measure |
|---|---|---|
| Return | 45% | Category-relative percentile of blended returns — 3-year minimum, 5-year blended in where available, no 10-year window |
| Risk | 30% | Downside deviation, unannualized, inverted so lower downside ranks higher |
| Consistency | 25% | Hit rate of beating the category median across rolling 12-month windows |

- The weighted composite is re-percentiled within its category and cut into
  **even quintiles** → tier 1 to 5.
- Tier boundaries are **inclusive on the lower bound**, not strict. The
  percentile formula in use means the best fund in a minimum-size category
  of exactly five schemes scores exactly at the boundary; a strict
  comparison would wrongly deny it the top tier.
- The final score is the composite percentile plus a cost adjustment of at
  most ±0.25, with a 0.05-percentage-point dead zone so trivial expense
  differences do not move a score.
- The month-end history window spans five years back regardless of a
  scheme's own history; schemes with less history simply have leading gaps.
  This mirrors the already-settled return rule rather than introducing a
  second window decision.
- The FR-7 breakdown is **recomputed on read and never persisted** — the
  scores table's columns are final per the schema document.
- A stakeholder-facing methodology document is a required deliverable of the
  same plan, written after the code exists so it describes real behaviour.

### Consequences

Positive:
- A score with a stated, defensible point of difference.
- No schema change.
- Explicable end to end: every user-visible number can be traced to one of
  three ingredients plus a named cost nudge.

Negative:
- Funds younger than three years cannot be scored at all.
- Thin categories fall back rather than scoring confidently, so coverage is
  uneven across the fund universe.
- The rolling-consistency calculation is the most expensive part of the
  analytics workload.
- **It contradicts `05-docs/explanation/fund-scoring-methodology.md`**, which
  records Morningstar-modelled tiers of 10% / 22.5% / 35% / 22.5% / 10% and
  a two-ingredient framing. See R-015 — unresolved.

### Validation

The plan is test-driven throughout, with the tier-boundary edge case
(best-fund-in-a-five-scheme-category) called out as a specific test rather
than left to chance. The methodology document's self-review step requires
spot-checking the published weights and thresholds against the implemented
constants, so the stakeholder explanation cannot drift from the code
silently.

**Not validated:** the score has not been compared against any external
rating on real data, so the claimed differentiation is a design intent, not
a measured result. Treat "different from Morningstar/CRISIL" as a
requirement that was designed for, not a verified outcome.

### Evidence

- `08-evidence/documents/plans/2026-08-10-phase-4-analytics-backend-design.md` (§6 Scorer)
- `08-evidence/documents/plans/2026-08-13-phase-4-analytics-backend-part5-scorer.md`
- Contradicted document: `05-docs/explanation/fund-scoring-methodology.md`
