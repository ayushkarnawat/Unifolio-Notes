# Scorer v2 — Calculation Annex: Open Questions for Sign-Off

The approved methodology (`Docs/Updated_and_Approved_Unifolio_Fund_Scoring_Methodology.md`)
is approved at the product/formula level. These are the definitions engineering needs to
produce deterministic code and golden tests — not objections to the methodology itself.
Grouped so the easy ones don't block on the hard ones.

## A. Needs your judgment — no safe engineering default

1. **Rolling horizons.** Return and Consistency use "1–5Y rolling windows" — are these
   exactly 1Y/2Y/3Y/4Y/5Y point-to-point windows, or a continuously rolling window at
   some sampling step (e.g. every rolling 12-month period over a 5Y lookback)?
2. **Recency-weighting curve.** What's the exact weighting function across those windows
   (e.g. linear decay, exponential half-life, or a fixed weight table)? This determines
   the Return and Consistency numbers directly, not just a presentation detail.
3. **Sampling frequency.** Are rolling observations built from monthly, weekly, or daily
   NAV data? (The rest of the platform's risk engine is monthly — flagging in case that's
   not what's intended here.)
4. **"Category average" definition** (used in Beats-Category-Average and the cost-level
   component). Median, equal-weighted mean, or AAUM-weighted mean? Note: the existing TER
   comparison already uses AAUM-weighted category averages — if that's the intended
   precedent, say so; if Consistency's "average" should be something different from Cost's
   "average," that's worth being explicit about too.
5. **Expense-ratio trend formula.** "A ratio falling as AUM grows... a ratio rising
   without AUM growth" is a qualitative description — what's the actual scoring rule (e.g.
   a 2x2 direction table, or a continuous function of both slopes)?
6. **PE/PB combination.** How do PE and PB combine into one percentile — averaged,
   one dominant, or something else? And: **build in-house (weighted harmonic mean off AMC
   portfolio disclosures) vs. buy a licensed feed (Morningstar Direct / ICRA / CRISIL)** —
   this is a cost/timeline decision, not an engineering one; feasibility findings in
   `Docs/orchestration/scorer-v2-pe-pb-feasibility-findings.md`.
7. **Benchmark per SEBI category.** Today only 4 Nifty indices exist and everything
   non-large/mid-cap equity falls back to Nifty 500 — inadequate for Down Capture/Up
   Capture/Information Ratio on debt, hybrid, gold, international, and sectoral funds.
   What's the intended benchmark for each category, and how are passive/index funds
   scored on capture/Information Ratio (their benchmark deviation is close to zero by
   design, so these metrics may need a different treatment for them specifically)?
8. **Minimum peer set widening.** "Categories below 15 are either widened or flagged
   low-confidence" — widened how (merge into a parent/sibling category, by what rule)?
9. **Provisional-fund (1–3Y) component eligibility.** Which of the 11 components can
   actually be computed for a fund with only 1–3 years of history, and how should
   "provisional" be shown alongside a partial breakdown?

## B. Proposed defaults — reply only if you want something different

10. **Final score = direct weighted sum, no second re-rank.** Already answered by
    reading §3 of the approved doc itself: `Score(f,t) = 0.25·Return + 0.12·BeatsAvg +
    ...` is a direct weighted combination of percentiles, with no re-rank pass afterward
    (unlike the current scorer's blend-then-rerank-then-TER-nudge). Flagging so it's
    explicit, not because it's actually open.
11. **Tier bands.** The approved doc doesn't mention tiers at all. Proposed default:
    keep the current 5-tier equal 20-point bands (80/60/40/20) applied to the final 0–100
    score, unless you want them changed.
12. **Minimum available-weight threshold.** Proposed default: if renormalized weight
    available is below 50% of total (i.e. more than half the components are missing),
    don't produce a score — mark unscored rather than showing a number built on a
    minority of its intended inputs. Open to a different threshold.

## C. Soft note, not a blocking question

13. The doc's overview sentence says "ten weighted components across six buckets," but
    the actual table has 11 components across 7 buckets (sums to 100% correctly). Likely
    just a stale summary sentence from an earlier draft — flagging in case it's not, but
    not treating it as blocking unless you say otherwise.
