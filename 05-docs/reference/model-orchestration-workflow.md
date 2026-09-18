# Reference: Model Orchestration Workflow

The rules for splitting implementation work between AI models. Decided
2026-08-12; the reasoning and the rejected alternatives are in
[ADR-011](../../03-decisions/ADR-011-model-orchestration-and-delegated-implementation.md).
This page is the operative summary — what the rules *are*, not why.

**Status:** available, not mandatory. The skill is dormant unless invoked.
Its first real use was the Scorer plan of 2026-08-13, which required it by
name for every implementation dispatch.

## Roles

| Role | Who | Does | Does not |
|---|---|---|---|
| Orchestrator | Claude Code | Holds context, plans, writes handoff documents, reviews, decides what to dispatch | Write the bulk implementation itself |
| Default worker | Codex, via the installed plugin's rescue subagent | Roughly 90% of delegable implementation work — transcription-plus-testing tasks | Get invoked by a hand-rolled direct script call; that violates the plugin's own runtime contract |
| Rare fallback | Claude subagents | Work Codex is a poor fit for | Serve as the default parallel worker — that would forfeit the cost saving delegation exists for |
| Escalation | Opus | Only on three named triggers, only with explicit user approval | Ever be switched to silently, or on open-ended judgment |

## The delegation boundary is always written down

Every delegated task gets a **durable handoff document** in a dedicated
working directory, plus an entry in a session-level delegation log. This is
the whole point of the workflow: the failure mode being designed against is
context loss at the boundary — the worker not knowing what the orchestrator
knew, and the orchestrator not being able to reconstruct afterwards what the
worker assumed.

## Review is a gate, not a suggestion

**Every Codex-implemented change is adversarially reviewed before it counts
as done, and review findings are never auto-applied.** Findings are presented;
the human decides what gets fixed. The source states explicitly that this
must not be softened to "recommended."

A model reviewing its own output is not a review. That is the reason the
reviewer is not the implementer.

## What this workflow does not cover

- **External coding agents.** Google Antigravity was used as an implementer
  on 2026-08-07 and again on 2026-08-14, with Claude Code acting as tester,
  reviewer and comparator rather than orchestrator. The 2026-08-14 analytics
  frontend design calls this "a third worker category the model-orchestration
  skill doesn't document." See [R-029](../../07-risks-and-debt.md).
- **Parallel Codex dispatch, verified.** The capability was confirmed by
  reading the plugin's code, not by running it. See
  [R-026](../../07-risks-and-debt.md).
- **Enforcement.** Nothing makes an orchestrator remember the skill exists.

## Scope and classification

The skill is **project-level, not user-level**, by explicit choice, and is
classified internal — it contains account- and path-specific detail that
should not be published.

## Related

- [ADR-011](../../03-decisions/ADR-011-model-orchestration-and-delegated-implementation.md)
- [2026-08-12 journey entry](../../02-journey/2026-08-12-delegated-execution-and-the-fund-scorer.md)
- [Risks and debt](../../07-risks-and-debt.md) — R-026, R-029
- Evidence: `08-evidence/documents/specs/2026-08-12-model-orchestration-skill-design.md`,
  `08-evidence/documents/plans/2026-08-12-model-orchestration-skill.md`,
  `08-evidence/documents/specs/2026-08-07-frontend-redesign-brief-for-coding-agent.md`
