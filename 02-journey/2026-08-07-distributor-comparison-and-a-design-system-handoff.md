# Distributor Comparison and a Design-System Handoff

Date: 2026-08-07
Status: Complete

## For stakeholders

Two unrelated things happened on this day.

The first is a feature with a sharp edge to it: showing a user, per fund,
how their returns differ depending on which distributor sold them the
holding — and naming that distributor rather than showing an opaque code.
India's mutual-fund industry body publishes distributor names, but not
through any documented interface. The publicly-known community tool for
doing this lookup had stopped working. So the endpoint the industry body's
own website uses was identified and verified by hand, and the product now
calls it directly, caching results platform-wide so the same distributor is
never looked up twice. If the lookup fails, the screen still renders and
falls back to the raw code — this feature is never allowed to block a
dashboard from loading. The full account is in
[INV-004](../04-investigations/INV-004-amfi-arn-distributor-lookup.md).

The second was a written handoff: the frontend design work was packaged as a
brief and given to an external coding agent (Google Antigravity) to
implement, with a quality bar stated as a number and an explicit split
between "polish what exists" and "build these screens fresh." Recording this
matters because it is the first time work left the team's own tooling.

## Technical detail

### Intended outcome

**Distributor comparison** — PRD-03's FR-11/FR-11a/FR-11b/FR-11c: a
per-scheme, per-member returns-by-distributor comparison backed by a real,
independently verified ARN-lookup integration with platform-wide caching and
a never-blocks-on-failure fallback.

**Frontend redesign brief** — package the current frontend's design gaps and
the screens still to be built into a single self-contained brief an external
coding agent can execute without access to the team's own conversation
history.

### What actually happened

**Distributor comparison.** Two new service modules under the Dashboard
service (an ARN-lookup client plus cache, and the per-ARN grouping logic)
and one new route. Both modules reuse existing building blocks rather than
reimplementing them — the FIFO lot-processing helper from the holdings
module for cost-basis and gain, the NAV lookup from the NAV module, and the
same ownership dependency every sibling Dashboard route uses.

Four decisions are worth preserving:
- **The route is member-scoped, not fund-global.** The TDD's API table had a
  fund-level shape; the design corrected it to sit under the household
  member, because a comparison of "your returns by distributor" is
  meaningless without knowing whose returns. This contradicts the route
  recorded in this vault's API-surface reference — see
  [R-017](../07-risks-and-debt.md).
- **A transient failure is never cached as a permanent result.** Only a
  definitive outcome — found-with-status, or confirmed-not-found — is
  written to the directory table. This is the same lesson a NAV-outage bug
  had already taught in Phase 3, applied pre-emptively here.
- **No raw third-party response is persisted**, only the four columns the
  directory table already has.
- **Distributor status maps to a trust signal** — active, suspended, or
  invalid — surfaced on every row rather than hidden.

The real lookup endpoint is never called in the test suite; it is mocked
everywhere, with the verification documented in a comment rather than
exercised live.

**Frontend redesign brief.** A self-contained handoff document. It named
four concrete gaps in the implemented design system: the typefaces were
declared but never actually loaded, tabular figures were not enabled so
numbers did not align in columns, the dark-mode token set was incomplete,
and the type scale was only partially implemented. It separated refinement
of existing screens from a list of screens to build fresh, explicitly put
three screens out of scope, stated the acceptance bar as a score on a
ten-heuristic usability rubric, and required the agent to update the
project's own session and instruction files and name itself as author so the
authorship of the work would be traceable afterwards.

### Deviation — decision or response taken

| Deviation | Response |
|---|---|
| The known community tool for ARN lookup was dead | The industry body's own site endpoint identified and verified by hand; documented shape, required header, and status mapping recorded. See INV-004 |
| The TDD's endpoint shape was wrong for this feature | Route corrected to member-scoped in the design, deliberately and with reasoning. Conflicts with the vault's recorded API surface — R-017 |
| Implementation work handed to a non-team, non-Claude agent | Packaged as a written brief with an explicit quality bar and a self-attribution requirement, rather than an informal handover |
| The design system was declared but not fully implemented | Gaps enumerated as work items rather than described as done |

### Result

A working distributor comparison with a live-verified external integration,
and a frontend redesign under way outside the team's own tooling. The
external-agent pattern established here recurs on 2026-08-14 and is
**not** covered by the model-orchestration skill built on 2026-08-12 — see
[R-029](../07-risks-and-debt.md).

### Related

- [INV-004](../04-investigations/INV-004-amfi-arn-distributor-lookup.md)
- [Decisions log](../03-decisions/decisions-log.md) — 2026-08-07 entries
- [Risks and debt](../07-risks-and-debt.md) — R-016, R-017, R-029
- Sources: `08-evidence/documents/plans/2026-08-07-distributor-comparison.md`,
  `08-evidence/documents/specs/2026-08-07-distributor-comparison-design.md`,
  `08-evidence/documents/specs/2026-08-07-frontend-redesign-brief-for-coding-agent.md`
