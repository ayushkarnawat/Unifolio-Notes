# ADR-017: Fund Score card rebuilt around a plain-English verdict, with a display-only tier-scale flip

Status: Proposed — design and implementation plan approved/written; no execution evidence in this batch's source material
Date: 2026-09-11
Related: [2026-09-11 journey stage](../02-journey/2026-09-11-fund-score-card-redesign.md), ADR-010 (fund scorer composite formula)

## For stakeholders

Manual testing of the live Analytics dashboard found the Fund Score card
unreadable for a regular investor: a `76.6%` next to "Downside Deviation
Grade" and a `30% Wt` badge don't answer "is this fund okay for me." The
approved redesign leads with a plain score out of 10, a one-sentence
verdict, and Strengths/Watch-outs framing in place of raw percentiles,
pushing every technical number behind two clearly-labeled expandable
sections. It also fixes a separate, unrelated display bug: the tier badge
shown to users counted backwards from the backend's internal convention
(tier 5 looked worse than tier 1, when 5 is actually the best tier). The
design and full implementation plan are both written and approved; nothing
in this batch's source material shows the work has actually been built yet.

## Technical detail

### Context

`FundScoreCard.tsx` (shown inside `FundScoreDetailModal.tsx`) surfaces raw
percentile ranking, factor weights, and tier numbers with no translation
into an investor-legible verdict. Separately, the backend's tier convention
(`_tier_from_percentile` in `scorer.py`: 5 = best) is displayed unflipped
in the frontend, so "Tier 5" reads as the worst tier to a user, though it
is the best.

### Decision drivers

- Lead with a plain-English verdict; push technical detail behind
  expandable sections for the minority who want it.
- Fix the tier-display inversion without touching the persisted
  `FundScore.risk_adjusted_tier` column, which is confirmed write-only
  (nothing in the backend ever reads it back) — flipping the stored value
  would be a real migration for zero downstream benefit, and would make any
  future reader need to know which convention a given historical row used.
- Do not build a generic, multi-consumer component for a feature that today
  has exactly one consumer.

### Options considered

#### Option 1: A generic `ScoreCard` component shared with future Stock/Portfolio Score

Rejected — Stock Score does not exist (PRD-04's permanent non-goal) and
Portfolio Score is a structurally different AUM-weighted roll-up with no
per-fund factor breakdown. Building a shared prop interface for a single
real consumer would be guessed at, not derived from a second real use case,
and would need reshaping anyway once a second shape actually exists.

#### Option 2: Migrate the stored `risk_adjusted_tier` to a 1-=-best convention

Rejected — the column is write-only today; migrating it is real schema
risk for a value nothing currently reads back, and it would leave a
convention ambiguity for any future reader of historical rows.

#### Option 3 (chosen): Rebuild the card as a Fund-Score-specific component; flip the tier only at display time

Advantages: no premature abstraction; the backend tier convention, the
persisted column, and every existing consumer of `risk_adjusted_tier` stay
untouched; the display fix is a single deterministic formula
(`displayTier = 6 - risk_adjusted_tier`) applied everywhere a tier renders.

Disadvantages: if a second per-fund score card is ever built, the shared
logic (`fundScoreVerdicts.ts`'s bucket/verdict/sentence rules) will need to
be extracted from this file at that point rather than existing already.

### Decision

Option 3. `FundScoreCard.tsx` is rebuilt in place — score shown as `X.X/10`
(frontend-only conversion of the unchanged `final_score`), a one-sentence
"why" verdict, three factor cards (Return, Downside protection, Consistency
of outperformance) grouped under headed Strengths/Watch-outs sub-lists with
a colored dot instead of a raw percentile, a suitability sentence, and two
closed-by-default expandable sections ("See the evidence" with real
numbers, "How we calculate this score" with the existing methodology
prose) — ending with the unchanged "Transparent Methodology Commitment"
box and no bottom CTA (fund comparison isn't a built feature). The
verdict/bucket/sentence rules are deterministic pure functions in a new
`fundScoreVerdicts.ts`, unit-testable in isolation and the piece most
likely to be reused verbatim if a second per-fund score card is ever built.
`ScorerSection.tsx` gets the same `displayTier = 6 - risk_adjusted_tier`
flip applied only to its `T{tier}` avatar and `Tier {tier}` badge — its
`/100` "Portfolio Weighted Score" hero stat and per-fund percentile rows
are untouched. Backend: `FundScoreRow` gains six new, additive/optional raw
fields (own/category-average return, own/category-average downside
deviation, consistency hits/total) threaded through `scorer.py` from values
already computed in-memory today; `compute_consistency_hit_rate`'s return
shape changes from a `Decimal` percentage to a raw `(hits, total)` pair,
with the percentage conversion moved to the call site.

### Consequences

Positive:
- Removes raw percentiles/weights from the primary card view without
  losing them — they move to an expandable section, not deleted.
- The tier-display fix is purely additive (`displayTier` computed at
  render time); zero backend/schema risk.
- New backend fields are additive-optional, so existing precomputed
  `analytics_sections` rows (ADR-015) stay valid without a forced
  recompute; a manual recompute re-run is explicitly deferred to the
  AWS/deployment phase to backfill them.

Negative:
- Existing cached score rows won't show the new evidence numbers until
  manually recomputed — an explicit, accepted transitional gap, not
  scheduled as part of this plan.
- `compute_consistency_hit_rate`'s return-shape change requires updating
  any existing test asserting the old `Decimal` shape; the plan notes this
  is "to be found and fixed during implementation," not enumerated in
  advance.

### Validation

Not yet validated by execution. The design document is marked "Approved
sections A–E in chat" and the implementation plan is a full 9-task
TDD-style plan, but no checkbox in the plan is marked done, and no other
document in this batch (or elsewhere in this vault) references a commit,
merge, or test run for this feature. Recorded as Proposed, not Accepted, on
the execution axis — the decision itself is approved; the build is not
confirmed. See [R-053](../07-risks-and-debt.md).

### Evidence

- Design: `08-evidence/documents/specs/2026-09-11-fund-score-card-redesign-design.md`
- Plan: `08-evidence/documents/plans/2026-09-11-fund-score-card-redesign.md`
