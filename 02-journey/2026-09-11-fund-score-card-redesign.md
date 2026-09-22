# Fund Score card redesigned for plain-English readability, and a tier-display bug fixed — designed, not yet confirmed built

## For stakeholders

Manual testing of the live staging site surfaced a real usability problem:
the card explaining a fund's Unifolio Score showed raw statistics
(percentiles, factor weights) that only make sense to someone who already
understands the scoring methodology. A full redesign was specified and a
detailed implementation plan written the same day — leading with a plain
score and a one-sentence verdict, grouping factors into Strengths and
Watch-outs, and pushing every technical number behind two optional,
collapsed sections. A separate, unrelated bug was fixed in the same design
pass: the on-screen tier badge counted backwards from what the backend
actually meant. As of this batch's source material, this work is approved
and fully planned, but not yet confirmed built.

## Technical detail

### Intended outcome

Replace the technical Fund Score card with an investor-legible one, and
correct the inverted tier display, without changing what the backend
computes or stores.

### What actually happened

The design (approved in chat, written up 2026-09-11) explicitly considered
and rejected building a generic, reusable `ScoreCard` component for a
future Stock Score / per-fund Portfolio Score — Stock Score doesn't exist
and Portfolio Score has no per-fund breakdown, so a shared interface today
would be guessed at from one real consumer, not derived from two. It also
weighed migrating the persisted tier convention itself, and rejected that
too — the column is confirmed write-only, so flipping it would be schema
risk for no reader that exists. The chosen fix flips the tier only at
display time (`displayTier = 6 - risk_adjusted_tier`), everywhere a tier
renders.

The 9-task implementation plan that followed threads six new, additive
backend fields (own and category-average return, own and category-average
downside deviation, consistency hits/total) onto `FundScoreRow` from
values already computed in-memory, and adds one new frontend module,
`fundScoreVerdicts.ts`, holding the deterministic bucket/verdict/sentence
rules as pure, independently unit-testable functions — flagged in the
design itself as the piece most likely to be reused verbatim if a second
per-fund score card is ever built. The plan's own final task instructs a
manual smoke check and a `session.md` note recording the feature as
implemented, with the precompute-cache backfill (re-running the analytics
recompute job so already-cached rows pick up the new fields) explicitly
deferred to a later AWS/deployment phase.

### Deviation (if any) — decision or response taken

None recorded within the design/plan itself. The deviation worth recording
is at the vault level: unlike the 2026-09-02 analytics precompute work,
**no later document in this batch cross-references this feature as built**
— no commit hash, no test-run confirmation, no `session.md` note. Recorded
as designed-and-planned only.

### Result

Design and implementation plan both complete and internally consistent.
Build status unconfirmed by this batch's source material — see
[ADR-017](../03-decisions/ADR-017-fund-score-card-redesign.md) and
[R-053](../07-risks-and-debt.md).

### Related

- ADR-017 — Fund Score card redesign
- ADR-010 — fund scorer composite formula (the backend logic this redesign presents, unchanged)
- R-053 — no execution evidence for this plan in this batch
- Evidence: `08-evidence/documents/specs/2026-09-11-fund-score-card-redesign-design.md`
- Evidence: `08-evidence/documents/plans/2026-09-11-fund-score-card-redesign.md`
