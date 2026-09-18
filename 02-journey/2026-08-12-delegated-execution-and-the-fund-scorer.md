# Delegated Execution and the Fund Scorer

Date: 2026-08-12 → 2026-08-13
Status: Complete

## For stakeholders

Two days, and the first is entirely about *how* the work gets done rather
than what gets built. A written process was established for splitting work
between AI models: one model coordinates and keeps the context, a cheaper
model does the bulk of the mechanical implementation, every delegated task
gets a durable handoff document so nothing is lost at the boundary, every
delegated change goes through an adversarial review before it is called
done, and escalating to the most expensive model requires explicit human
approval on one of three named triggers. The alternative approaches
considered — including a much heavier machine-readable event-log system —
were rejected as more process than a three-person project can carry.

The second day produced the Unifolio Scorer, and it is the most
consequential product decision in this batch. The score answers "how good is
this fund, really" as one number plus a tier, and the formula was settled
with the product owner: 45% past return, 30% risk, 25% consistency. The
risk measure deliberately only counts downside movement, on the grounds that
a fund going up sharply is not a risk to anybody. The consistency
ingredient — how often the fund beat its category over rolling twelve-month
windows — is the deliberate point of difference from the established
rating agencies, and the requirement was stated explicitly as "must be
different from Morningstar and CRISIL."

**This directly contradicts what this vault currently records about the fund
score.** See the note at the end of this entry.

## Technical detail

### Intended outcome

**Model orchestration skill** — a project-level Claude Code skill making
Claude Code the primary orchestrator and Codex the default worker for
delegable subtasks, with a durable per-task handoff document preventing
context loss at the delegation boundary.

**Scorer** — a composite per-fund quality score (PRD-04 FR-5), an
AUM-weighted portfolio roll-up of it (FR-6), and a fully explained breakdown
so the score is never shown as a bare number or a one-word label (FR-7).

### What actually happened

**Model orchestration.** A skill bundle plus a working directory for
per-task handoff documents and a session-level delegation log. Shape of the
decision:
- Claude Code orchestrates; Codex performs roughly 90% of delegable
  implementation work, dispatched through the already-installed Codex
  plugin's rescue subagent — never by hand-rolling a direct script
  invocation, which would violate the plugin's own contract.
- Claude subagents are a rare fallback, deliberately not the default
  parallel worker.
- Escalation to Opus requires explicit user approval and only on three named
  triggers — never open-ended judgment, never a silent model switch.
- Adversarial review of every Codex-implemented change is **mandatory and
  never auto-applied**: findings are presented, and the human decides what
  gets fixed. The plan states explicitly that this must not be softened to
  "recommended."
- Rejected: using the plugin's session-transfer command as the primary
  mechanism; a heavyweight append-only event-log and digest-pinning system
  modelled on another project; and making Claude subagents the default
  parallel worker.

One capability claim was **verified by reading the plugin's code, not by
running it** — parallel Codex dispatch. Recorded as
[R-026](../07-risks-and-debt.md).

**Scorer.** Two new analytics modules: pure risk-metric functions (monthly
NAV series construction, downside deviation, rolling twelve-month
consistency) and an orchestration module combining them with the
already-built category ranking (return) and expense-ratio data (cost
overlay), persisting the result and rolling it up per portfolio.

The formula, resolved with the product owner on 2026-08-13:

| Ingredient | Weight | Measure |
|---|---|---|
| Return | 45% | Category-relative percentile of blended returns (3yr minimum, 5yr blended in when available; no 10yr window) |
| Risk | 30% | Downside deviation, unannualized, inverted to a percentile so lower downside scores higher |
| Consistency | 25% | Hit rate of beating the category median over rolling 12-month windows |

The composite is re-percentiled within its category into quintiles, giving a
tier of 1 to 5. The final score is the composite percentile plus a cost
adjustment of at most ±0.25 based on expense ratio versus category, with a
0.05-percentage-point dead zone so trivial differences do not move a score.
Tier boundaries are inclusive on the lower bound — a strict comparison would
deny the top tier to the best fund in a minimum-size category of exactly
five schemes, because of how the percentile formula divides.

The FR-7 breakdown (return/risk/consistency percentiles) is deliberately
**not persisted** — the scores table's columns are fixed by the schema and
the breakdown is recomputed fresh on every read rather than growing the
table.

The scorer plan was also the first plan to *require* the orchestration skill
for its own execution, on the grounds that its tasks were
transcription-plus-testing work — the default case for delegation.

### Deviation — decision or response taken

| Deviation | Response |
|---|---|
| The scorer as originally sketched had two ingredients (return and risk) | Revised to three after the 2026-08-13 conversation; consistency added as the deliberate differentiator. The deviation from the earlier description was flagged in the design rather than quietly replaced |
| Standard deviation is the conventional risk measure | Rejected in favour of downside deviation — upside volatility is not a risk to an investor |
| A heavyweight delegation-ledger system existed as a model | Rejected as more machinery than the project can carry |
| Parallel Codex dispatch could not be live-tested | Verified by code-reading and flagged as unverified rather than claimed working. R-026 |

### Result

A documented delegation process that is available rather than mandatory, and
a complete, explainable fund score with a stakeholder-facing methodology
document as an explicit deliverable of the same plan.

**Contradiction to resolve.** This vault's
[`05-docs/explanation/fund-scoring-methodology.md`](../05-docs/explanation/fund-scoring-methodology.md),
written from PRD-04 in batch 1, describes the score as modelled on
Morningstar with five percentile tiers at 10% / 22.5% / 35% / 22.5% / 10%
and a two-ingredient framing. The formula resolved with the product owner on
2026-08-13 and implemented is three-ingredient with **even quintile** tier
boundaries, and explicitly requires differentiation from Morningstar. These
cannot both be current. Recorded as [R-015](../07-risks-and-debt.md) and
[ADR-010](../03-decisions/ADR-010-fund-scorer-composite-formula.md); **not
resolved here.**

### Related

- [ADR-010](../03-decisions/ADR-010-fund-scorer-composite-formula.md),
  [ADR-011](../03-decisions/ADR-011-model-orchestration-and-delegated-implementation.md)
- [Model orchestration workflow](../05-docs/reference/model-orchestration-workflow.md)
- [Fund scoring methodology](../05-docs/explanation/fund-scoring-methodology.md)
- [Risks and debt](../07-risks-and-debt.md) — R-015, R-026
- Sources: `08-evidence/documents/plans/2026-08-12-model-orchestration-skill.md`,
  `08-evidence/documents/specs/2026-08-12-model-orchestration-skill-design.md`,
  `08-evidence/documents/plans/2026-08-13-phase-4-analytics-backend-part5-scorer.md`
