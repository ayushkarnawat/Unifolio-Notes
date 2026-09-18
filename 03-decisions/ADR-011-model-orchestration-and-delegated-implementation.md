# ADR-011: Model orchestration — Claude Code orchestrates, Codex implements, review is mandatory

Status: Accepted
Date: 2026-08-12
Related: `02-journey/2026-08-12-delegated-execution-and-the-fund-scorer.md`; `05-docs/reference/model-orchestration-workflow.md`

## For stakeholders

Most of Unifolio's code is written by AI models, and by August it was worth
deciding deliberately *which* model does *what* rather than choosing per
task. The decision: one model stays in charge, holds the context, and never
writes the bulk implementation itself; a second, cheaper model does roughly
nine tenths of the mechanical implementation work; every handoff between
them is written down in a durable document so nothing is lost at the
boundary; every delegated change is adversarially reviewed before it counts
as done, with a human deciding what actually gets fixed; and escalating to
the most expensive model requires explicit human approval and only for three
named reasons. A much heavier bookkeeping system was considered and rejected
as more process than a small project can carry. The cost of this decision is
a handoff document per task and a review step that cannot be skipped. The
benefit is that the review step cannot be skipped.

This is a decision about how the project is built rather than about what is
built. It is recorded as an ADR because it has real alternatives, real
consequences for quality, and it changed how subsequent work was executed —
the Scorer plan the next day required it by name.

## Technical detail

### Context

The project already had the Codex plugin installed and had been delegating
ad hoc. Ad hoc delegation loses context at the boundary: the worker model
does not know what the orchestrator knows, and the orchestrator cannot tell
afterwards what the worker assumed. A documented, repeatable pattern was
needed — or an explicit decision that one was not.

### Decision drivers

- Token budget: the orchestrator is the expensive context; keeping it off
  mechanical transcription work is the main saving.
- Context loss at the delegation boundary is the failure mode that actually
  bites.
- Review quality: a model reviewing its own output is not a review.
- Process weight: a three-person project cannot maintain machinery designed
  for a larger one.
- Reuse over reinvention: the existing plugin already has a subagent, review
  commands, and a runtime contract.

### Options considered

#### Option 1: Keep delegating ad hoc
Advantages: nothing to build.
Disadvantages: the boundary context loss stays unaddressed, and review
happens when someone remembers.

#### Option 2: The plugin's session-transfer command as the primary mechanism
Advantages: already exists; no new abstractions.
Disadvantages: transfers a session rather than a scoped task, which is the
wrong unit for parallel delegable subtasks. Rejected as the primary path.

#### Option 3: A heavyweight ledger — append-only event log, digest pinning, phase folders
Advantages: fully auditable; strong reproducibility guarantees.
Disadvantages: substantially more machinery than the project needs, and an
explicit user rejection. Rejected.

#### Option 4: Claude subagents as the default parallel worker
Advantages: no external tooling; same model family throughout.
Disadvantages: does not achieve the cost saving that motivates delegation at
all. Kept as a rare fallback, not the default.

#### Option 5: Orchestrator + Codex worker + handoff docs + mandatory review (chosen)
Advantages: achieves the cost saving, addresses the context-loss failure
mode directly, reuses the installed plugin's own contracts, and keeps the
human as the decision-maker on review findings.
Disadvantages: a document per task; a review gate that adds latency.

### Decision

- Claude Code is the orchestrator; Codex is the default worker for delegable
  subtasks, dispatched through the installed plugin's rescue subagent — never
  by hand-rolling a direct script invocation, which would violate the
  plugin's own runtime contract.
- A per-task handoff document under a dedicated working directory, plus a
  session-level delegation log.
- Claude subagents remain a rare fallback rather than the default parallel
  worker.
- Adversarial review of every Codex-implemented change is **mandatory and
  never auto-applied**; findings go to the human, who decides what is fixed.
  The source states explicitly that this must not be softened to
  "recommended."
- Escalation to Opus requires explicit user approval and only on three named
  triggers — never a silent model switch, never open-ended judgment.
- The skill is project-level, not user-level, by explicit choice, and is
  classified internal (it contains account- and path-specific details).

### Consequences

Positive:
- Delegation is repeatable and its boundary is documented.
- Review cannot be quietly skipped, and the human stays the decider.
- Cost control is structural rather than a per-task judgment call.

Negative:
- Overhead per delegated task.
- The skill is dormant unless invoked — it is available, not mandatory, so
  adherence depends on the orchestrator remembering it exists.
- **Parallel Codex dispatch was verified by reading the plugin's code, not
  by running it.** See R-026.
- **It does not cover external coding agents.** Google Antigravity was
  already being used as an implementer on 2026-08-07 and again on
  2026-08-14, in a reviewer/tester-orchestrator relationship the skill does
  not describe. See R-029.

### Validation

The plan's own "tests" are content and frontmatter verification plus one
live capability smoke-test, since there is no executable code under test. The
smoke-test for parallel dispatch was not run live. The first real use was the
Scorer plan on 2026-08-13, which required the skill by name for every
implementation dispatch.

### Evidence

- `08-evidence/documents/specs/2026-08-12-model-orchestration-skill-design.md`
- `08-evidence/documents/plans/2026-08-12-model-orchestration-skill.md`
- First consumer: `08-evidence/documents/plans/2026-08-13-phase-4-analytics-backend-part5-scorer.md`
- External-agent counter-examples:
  `08-evidence/documents/specs/2026-08-07-frontend-redesign-brief-for-coding-agent.md`,
  `08-evidence/documents/specs/2026-08-14-analytics-frontend-design.md`
