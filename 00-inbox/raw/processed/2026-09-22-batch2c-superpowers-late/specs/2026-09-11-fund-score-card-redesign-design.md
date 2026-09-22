# Fund Score Card Redesign — Design Spec

**Date:** 2026-09-11
**Status:** Approved sections A–E in chat; this is the written spec for final review before implementation planning.
**Requested by:** Ayush, after manual smoke-testing `staging.unifolio.in`.

## 1. Problem & Goals

The current Fund Score card (`FundScoreCard.tsx`, shown inside
`FundScoreDetailModal.tsx`) is written for someone who already understands
percentile ranking, factor weights, and tier buckets. A regular investor sees
a `76.6%` next to "Downside Deviation Grade" and a `30% Wt` badge and has no
way to translate that into "is this fund actually okay for me."

Goal: replace it with a card that leads with a plain-English verdict, explains
*why* in one sentence, shows strengths/watch-outs instead of raw stats, and
pushes all technical detail (weights, formulas, percentiles, raw numbers)
behind two clearly-labeled expandable sections for the minority of users who
want them.

## 2. Scope

**In scope:**
- `FundScoreCard.tsx` — full rebuild of the card's content and structure.
- `FundScoreDetailModal.tsx` — subtitle copy only.
- `ScorerSection.tsx` — tier-badge direction fix only (display-only), nothing
  else in that file changes.
- `backend/app/services/analytics/schemas.py`, `scorer.py`, `risk_metrics.py`
  — new raw-evidence fields on `FundScoreRow`, threaded through from values
  already computed in-memory today.

**Explicitly out of scope (per your confirmation):**
- Stock Score — doesn't exist, PRD-04's permanent non-goal, not scaffolded.
- `ScorerSection.tsx`'s "Portfolio Weighted Score" hero stat — stays `/100`,
  untouched, since `PortfolioScoreSummary` is a structurally different
  AUM-weighted roll-up with no per-fund factor breakdown of its own.
- Any generic multi-page "ScoreCard" component. See §3.
- Manually re-running the analytics recompute job to backfill the new fields
  into already-cached rows — deferred to the AWS/deployment phase (§8).
- A bottom CTA (e.g. "Compare with similar funds"). Fund comparison isn't a
  built feature yet — this CTA gets added when that feature exists, not
  before. The card ends with the methodology box (§5.7, §5.9).

## 3. Component architecture — no premature abstraction

Earlier discussion floated a generic `ScoreCard` component with props mapped
from `FundScoreRow`, intended as the shared future template for Stock/
Portfolio Score. Revisiting that here: Stock Score doesn't exist and
Portfolio Score isn't a per-fund card, so today there is exactly one
consumer. Building a generic prop interface for a single consumer is the
textbook premature abstraction — it would be guessed at, not derived from a
second real use case, and would need to be reshaped anyway once Stock/
Portfolio Score's actual data shape exists.

**Decision:** rebuild `FundScoreCard.tsx` as the well-structured, single
Fund-Score-specific implementation, split internally into small named pieces
so it *stays* easy to generalize later:

- `FundScoreCard.tsx` — top-level layout, orchestrates the pieces below.
- `fundScoreVerdicts.ts` (new, pure functions, unit-testable in isolation) —
  the deterministic bucket/verdict/sentence rules from §6. No React, no
  component coupling — this is the part most likely to get reused verbatim
  when Stock/Portfolio Score are eventually built.
- Small inline subcomponents inside `FundScoreCard.tsx` for the score hero,
  the driver list, the evidence accordion, and the methodology accordion —
  not separate files; the whole card is a few hundred lines, one file stays
  easy to read.

When Stock Score or a per-fund Portfolio Score view is actually built,
extract the generic template from this file then — with two real shapes in
hand instead of one imagined one.

## 4. Tier scale reversal — display-only

Backend tier convention today (`_tier_from_percentile` in `scorer.py`): 5 =
best (top 20th percentile), 1 = worst. The `FundScore` table this persists
to is confirmed write-only — nothing in the backend ever reads it back — so
flipping the stored value would be a real migration for zero downstream
benefit and real risk (any future reader would need to know which
convention a historical row used).

**Decision:** flip at display time only, everywhere a tier renders:

```
displayTier = 6 - risk_adjusted_tier
```

Applies in:
- `FundScoreCard.tsx` (new tier badge, §5.4)
- `ScorerSection.tsx` — the `T{tier}` avatar badge and the `Tier {tier}`
  badge on each fund row (the only change that file gets in this pass)

Backend `risk_adjusted_tier`, `_tier_from_percentile`, and the persisted
`FundScore.risk_adjusted_tier` column are untouched.

## 5. Card structure

In order, top to bottom. Each item maps to your original spec point.

### 5.1 Header
Scheme name only. (Checked: the current header in `FundScoreDetailModal.tsx`
already renders only the "S20 · Unifolio Fund Score" badge, an optional
"Thin Category" badge, and the scheme name — no plan-type/Demat-style badge
is present today. This requirement is already satisfied; called out for
completeness, no code change needed here.)

Subtitle (`FundScoreDetailModal.tsx` `DialogDescription`) changes:
```diff
- Comprehensive quality verdict relative to true SEBI category peers
+ How this fund compares to similar funds in its category.
```

### 5.2 Score
`final_score` (0–100, unchanged on the backend) displayed as `/10`:
```
displayScore = parseFloat(final_score) / 10   // e.g. 78.4 -> "7.8"
```
Rendered `7.8 / 10`. Frontend-only conversion — no backend or schema change,
since `final_score` already carries full precision as a string.

### 5.3 Why sentence
One plain sentence directly under the score. See §6.3 for the generation
rule. Example: *"Scores well mainly due to strong long-term performance and
low cost."*

### 5.4 Tier badge
`Tier {displayTier} of 5`, `displayTier = 6 - risk_adjusted_tier` (§4).
Caption text flips to match ("Top Tier Performer" now means
`displayTier <= 2`, etc.) — same thresholds as today, just re-pointed at the
flipped value. The 5-segment progress bar's fill direction and "Tier 1
(Lower)" / "Tier 5 (Top 20%)" captions flip the same way.

### 5.5 "What's driving your score"
Replaces "The 3 Core Methodology Ingredients". Renders the three factor
cards (Return, Downside protection, Consistency of outperformance), each
built per §6:

- No weight badge (`45% Wt` etc.) — removed from this view entirely, moved
  to the "How we calculate this score" accordion (§5.9).
- No raw percentile number — replaced by a colored dot + plain-language
  label + verdict word + one sentence (§6.1, §6.2).
- Cards are grouped under two headed sub-lists, **Strengths** (green) and
  **Watch-outs** (orange/red) — never an unlabeled/neutral card. Every
  factor lands in exactly one bucket (§6.1).

### 5.6 "What this means for you"
One calm suitability sentence, deterministic from `displayTier` (§6.4).

### 5.7 "Transparent Methodology Commitment"
Unchanged copy, moved from its current position (just above the section
bottom) to genuinely the last thing on the page — after "What this means for
you" and after both expandable sections (§5.8, §5.9), i.e. the true bottom.

### 5.8 "See the evidence" (expandable, closed by default)
Real numbers, not percentile-derived text. Per factor:

- **Return:** scheme's own blended CAGR vs. category average blended CAGR
  (`scheme_return`, `category_avg_return` — new fields, §7).
- **Downside protection:** scheme's own downside deviation vs. category
  average, annualized for display only (`× √12`, display-only transform,
  matches the risk_metrics.py docstring's note that annualizing is a
  constant scalar that doesn't change ranking — safe to do purely for a more
  legible on-screen number without touching the ranking computation).
- **Consistency:** "Beat its category median in **9 of 12** rolling
  12-month periods" (`consistency_hits` / `consistency_total_windows` — new
  fields, §7).

### 5.9 "How we calculate this score" (expandable, closed by default)
Static methodology content, mostly a relocation of what the card already
states in prose today: the 45% Return / 30% Downside Risk / 25% Consistency
weighting, the ±0.25pt TER nudge with its 0.05pp dead zone, and the SEBI
category peer-universe definition. This is where the weight badges removed
from §5.5 end up (e.g. "Return — 45% of score"). Per §5.7, the "Transparent
Methodology Commitment" box renders after this section, as the true bottom
of the card — no CTA follows it (see §2, out of scope).

## 6. Deterministic verdict rules (`fundScoreVerdicts.ts`)

All three factor values (`return_percentile`, `risk_percentile`,
`consistency_hit_rate`) are 0–100 values today (the latter is a rate, not a
peer percentile, but same scale and same "higher is better" direction — no
distinction needed for bucketing purposes).

### 6.1 Bucket + dot color
```
p >= 50            -> Strength, green dot
20 <= p < 50        -> Watch-out, orange dot
p < 20             -> Watch-out, red dot
```
Every factor lands in exactly one of Strengths/Watch-outs — no neutral
bucket, satisfying your "no unlabeled cards" requirement. Red is reserved
for the more severe watch-outs (bottom quintile) so the three colors you
asked for (green/orange/red) all carry distinct meaning rather than being
decorative.

### 6.2 Verdict word + sentence, per factor
| Factor | p >= 80 | 50 ≤ p < 80 | 20 ≤ p < 50 | p < 20 |
|---|---|---|---|---|
| Return | Excellent — "Strong long-term performance — has consistently outperformed similar funds." | Strong — "Solid long-term performance, generally in line with or ahead of similar funds." | Weak — "Below-average long-term performance compared to similar funds." | Poor — "Long-term performance has lagged most similar funds." |
| Downside protection | Excellent — "Strong downside protection — has historically lost less than peers in falling markets." | Strong — "Reasonable downside protection compared to similar funds." | Weak — "Below-average downside protection — has historically fallen more than peers in weak markets." | Poor — "Weak downside protection — has historically lost more than most peers in falling markets." |
| Consistency of outperformance | Excellent — "Very consistent — has beaten its category median in most 12-month periods." | Strong — "Fairly consistent — has beaten its category median in more than half of 12-month periods." | Weak — "Inconsistent — has beaten its category median in less than half of 12-month periods." | Poor — "Highly inconsistent — has rarely beaten its category median over rolling 12-month periods." |

Label renames (technical → plain), applied wherever the factor name shows:
- "Category Return Percentile" → **Return**
- "Downside Deviation Grade" → **Downside protection**
- "12M Rolling Beat Rate" → **Consistency of outperformance**

### 6.3 Why-sentence (§5.3)
```
strongest = factor with max(return_pct, risk_pct, consistency_pct)
weakest   = factor with min(return_pct, risk_pct, consistency_pct)
costBonus  = cost_adjustment == "+0.25"
costPenalty = cost_adjustment == "-0.25"

if displayTier in (1, 2):
    "Scores well mainly due to {strongest.whyPhrase}" + (" and low cost." if costBonus else ".")
elif displayTier in (4, 5):
    "Held back mainly by {weakest.whyPhrase}" + (" and higher-than-average cost." if costPenalty else ".")
else:  # displayTier == 3
    "Performs roughly in line with similar funds, with strength in {strongest.whyPhrase}
     balanced by weaker {weakest.whyPhrase}."
```
`whyPhrase` per factor (short noun phrase, distinct from the full sentences
in §6.2):
- Return: "strong long-term performance" / "weaker long-term performance"
- Downside protection: "strong downside protection" / "weaker downside protection"
- Consistency: "consistent outperformance of peers" / "inconsistent performance versus peers"

### 6.4 "What this means for you" (§5.6), by `displayTier`
| displayTier | Sentence |
|---|---|
| 1 | "A strong choice within its category based on historical data — suitable if you're comfortable with typical risk for this fund type." |
| 2 | "A solid, dependable option within its category based on historical data." |
| 3 | "An average performer within its category — worth comparing against a few alternatives before deciding." |
| 4 | "A below-average performer within its category — consider reviewing whether it still fits your goals." |
| 5 | "One of the weaker performers within its category based on historical data — worth a closer look before adding more." |

None of this is phrased as investment advice ("should", "buy", "sell") —
stays descriptive, consistent with the Methodology box's existing disclaimer.

## 7. Backend changes

### 7.1 `schemas.py` — `FundScoreRow` additions
```python
class FundScoreRow(BaseModel):
    ...  # existing fields unchanged
    scheme_return: str | None                    # new — own blended CAGR
    category_avg_return: str | None               # new
    downside_deviation: str | None                 # new — own, monthly, unannualized
    category_avg_downside_deviation: str | None    # new — same units
    consistency_hits: int | None                   # new
    consistency_total_windows: int | None           # new
```
Existing percentile fields (`return_percentile`, `risk_percentile`,
`consistency_hit_rate`) are unchanged and unremoved — still needed for tier
computation, and `ScorerSection.tsx`'s per-fund row (out of scope, §2) still
displays them as-is.

### 7.2 `scorer.py` — threading raw values through
`_compute_category_component_scores` already computes every raw value this
needs; only the percentile survives into the returned `scores` dict today.
Changes:
- Keep the existing `returns` dict (from `_category_returns`) in scope and
  pass `returns[scheme_id]` through to `_finish_fund_score` (own blended
  CAGR). Category average: `category_ranking.py`'s existing
  `category_avg_return` computation is reused, not reinvented — same value
  `CategoryRankRow` already exposes.
- `downside_by_scheme[scheme_id]` is currently stored negated (for ranking
  direction). Add the raw (un-negated) value alongside it, and a new
  category-average aggregate (`mean` of the raw values) computed once per
  category alongside the existing `medians` call — cheap, same shape as
  `category_medians`.
- Pass both through `scores[scheme_id]` and into `_finish_fund_score`'s
  `FundScoreRow` construction.

### 7.3 `risk_metrics.py` — `compute_consistency_hit_rate` return shape
Currently returns `Decimal | None` (a percentage). Change to return
`tuple[int, int] | None` (`hits`, `total`); move the `Decimal(hits) /
Decimal(total) * 100` conversion to the call site in
`_compute_category_component_scores`, which already needs the percentage for
`consistency_hit_rate` and now also needs the raw pair for
`consistency_hits`/`consistency_total_windows`. Any existing test asserting
the old `Decimal` return shape needs updating alongside this — to be found
and fixed during implementation, not enumerated here.

## 8. Precompute cache backfill

`FundScoreRow` is nested inside `PortfolioScoreSummary`, which is part of
the precompute contract (`recompute.py`'s `_SECTIONS` includes the "score"
section). New fields added here are purely additive (new optional fields on
an existing Pydantic model) — old cached rows simply won't have them until
recomputed, which is a safe, non-breaking transitional gap.

**Per your instruction:** once all of this is coded, tested, and deployed,
and once back in the AWS/deployment/commands phase of the work, manually
re-run the analytics recompute job (the same one-off `ecs run-task` pattern
already used in the staging runbook's Step 7) to backfill the new fields
into already-cached staging rows immediately, instead of waiting for the
next scheduled recompute. Not done as part of this implementation pass.

## 9. Testing plan

- `fundScoreVerdicts.ts` — pure-function unit tests covering every bucket
  boundary (p = 0, 19, 20, 49, 50, 79, 80, 100) for §6.1/§6.2, and every
  `displayTier` branch for §6.3/§6.4.
- `FundScoreCard.test.tsx` (new or extended) — renders with representative
  `FundScoreRow` fixtures (strong fund, weak fund, mixed fund, thin
  category, insufficient history, category unavailable) and asserts the
  right section text/structure appears.
- `ScorerSection.test.tsx` — assert the tier badge shows the flipped value.
- Backend: extend existing scorer/risk_metrics test coverage for the new
  `FundScoreRow` fields and `compute_consistency_hit_rate`'s new return
  shape; exact existing test files to be located during implementation.
