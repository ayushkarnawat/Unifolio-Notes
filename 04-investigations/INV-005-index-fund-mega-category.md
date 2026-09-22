# Investigation: the index-fund mega-category, and why it cannot be honestly split

Status: Closed — deferred by decision, with a written revisit trigger
Date: 2026-08-20
Related: ADR-010 (the Unifolio Scorer), R-041, [2026-08-20 journey stage](../02-journey/2026-08-20-analytics-deepening-and-a-deferred-split.md)

## Trigger

Category-relative analytics compare a user's fund against its peer universe.
AMFI's `"Other Scheme - Index Funds"` heading contains **1,150 schemes**,
making it by a wide margin the largest peer universe in the system. Every
index-fund holder pays for that on load, because the comparison has to consider
the whole set.

## Expected behavior

A peer universe should be a set of genuinely comparable funds, small enough to
compute against quickly and specific enough that the comparison means
something. An index-fund holder's fund should be ranked against similar index
funds, not against every index fund in India including debt and hybrid ones.

## Observed behavior

One heading, 1,150 schemes, spanning equity, debt and hybrid index products
with no sub-structure in the source data. Comparisons are correspondingly slow
and correspondingly coarse.

## Hypotheses

1. The category can be split into meaningful sub-categories by pattern-matching
   scheme names, producing several smaller, faster, more comparable universes.
2. AMFI already publishes a finer breakdown elsewhere in the same feed, which
   can be adopted without inventing anything.

## Experiments

| Experiment | Expected signal | Actual result | Conclusion |
|---|---|---|---|
| Bucket the 1,150 schemes with regular expressions on scheme names (hypothesis 1) | A set of sub-categories each small enough to be a fast, coherent peer universe | 18 buckets. Largest is debt index at 219 schemes. A catch-all bucket of 67 schemes remains, 5.8% of the category | Works numerically. Every boundary is an invented heuristic, so mis-bucketing is certain at the margins and the rules need maintenance every month as new schemes are filed |
| Use AMFI's own parallel headers for index funds (hypothesis 2) | Native sub-categories covering the same 1,150 schemes | Index Funds — Equity 133, Debt 43, Hybrid 4. These rows are largely *not* the same feed rows as the mega-category | Nothing is invented, but it does not solve the problem — the mega-category is barely reduced |
| Ask whether a bespoke taxonomy is acceptable to the product | A judgement on credibility, not a number | Peer feedback: a taxonomy AMFI does not recognise is a bad trade for a product whose credibility rests on trustworthy category comparisons | Rules out hypothesis 1 on product grounds even though it works technically |

## Root cause

AMFI's published taxonomy genuinely does not sub-divide this category in the
feed Unifolio consumes. The finding that closes the investigation, in the
source document's own framing: **there is no split that is both AMFI-native
and actually shrinks "Other Scheme - Index Funds" to a non-mega size.** Any
effective split must be invented; any native split is ineffective.

## Resolution

Deferred, not built. The category stays as AMFI publishes it. The performance
symptom is currently mitigated by the fifteen-minute per-category cache added
to the bulk NAV lookup by the earlier BUG-001 fix.

**Revisit trigger, as written:** only if load time for index-fund holders
becomes a demonstrated user-facing problem. Not on a schedule, and not on
suspicion.

## Remaining uncertainty

A side finding is potentially more serious than the deferral itself.
`get_category_universe` matches the category by exact string, which means a
scheme filed under a legacy AMFI header is invisible to comparison entirely —
not mis-bucketed, absent. This is a possible pre-existing data-completeness
gap, was not measured in this investigation, and is carried as R-041. It
should be checked against the current code repository before any conclusion is
drawn from it.

## Related records

- R-041 — exact-string category matching may hide legacy-header schemes
- ADR-010 — the Unifolio Scorer composite formula (consumer of the peer universe)
- Evidence: `08-evidence/documents/specs/2026-08-20-index-fund-mega-category-split-deferred.md`

**Note on a connection that does not hold.** The 2026-09-17 status banner on
`05-docs/explanation/fund-scoring-methodology.md` records two coexisting
fund-*scoring* methodologies (R-015). This investigation concerns *peer-universe
scoping* for category ranking, not a scoring formula. It neither corroborates
nor contradicts R-015; the two are independent.
