# Model Orchestration Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a project-level Claude Code skill that makes Claude Code the
primary orchestrator and Codex (via the already-installed `openai/codex-plugin-cc`)
the default worker for delegable subtasks, with a durable per-task handoff
doc preventing context loss at the delegation boundary.

**Architecture:** A skill bundle (`SKILL.md` + four `references/` files,
loaded on demand) plus a `Docs/orchestration/` working directory for
per-task handoff docs and a session-level delegation log. The skill is a
coordination layer over the existing Codex plugin's `codex:codex-rescue`
subagent, `/codex:review`/`/codex:adversarial-review`, and `gpt-5-4-prompting`
— it never hand-rolls `codex-companion.mjs` calls directly.

**Tech stack:** Markdown skill files (Claude Code skill format), no
application code. "Tests" in this plan are content/frontmatter verification
and one live capability smoke-test (parallel Codex dispatch), not unit
tests — there is no executable code under test.

## Global Constraints

- **Skill type: internal** (per `task-observer`'s skill-authoring taxonomy)
  — contains this user's specific account setup and this project's specific
  paths. No attribution block, no LICENSE file, no license statement needed.
- **Location: project-level only** — `.claude/skills/model-orchestration/`,
  not `~/.claude/skills/`. This was an explicit user choice, not a default.
- **Reuse, never reinvent** — the skill must route all Codex delegation
  through the `codex:codex-rescue` subagent (via the `Agent` tool). It must
  never construct a direct `codex-companion.mjs` Bash invocation itself —
  that violates the plugin's own `codex-cli-runtime` contract, which
  reserves direct script calls for the subagent only.
- **Adversarial review is mandatory, never auto-applied** — every
  Codex-implemented change gets `/codex:review` or `/codex:adversarial-review`
  before its handoff doc's Status moves to `DONE`; findings are presented
  and the user decides what gets fixed, per `codex-result-handling`'s
  existing rule. This must not be softened to "recommended."
- **Opus escalation always requires explicit user approval** — no silent
  model switch, ever, and only on the three named triggers (see Task 5's
  `escalation-triggers.md` content) — not open-ended judgment.
- **No heavy process machinery** — no `ledger.jsonl`-style event log, no
  digest-pinning, no phase-folder hierarchy. This was an explicit user
  rejection of the `kiln`-equivalent approach as more overhead than this
  project's existing `session.md` / `Docs/superpowers/plans/` conventions
  justify.
- **`Docs/` is capitalized** at this repo's top level (matches
  `Docs/superpowers/`, `Docs/PRDs/`) — `Docs/orchestration/`, not
  `docs/orchestration/`.
- **Pre-Flight Principle** (`task-observer`'s skill-authoring guidance):
  every rule stated in `SKILL.md` needs a verification mechanism, not just
  prose. Task 8 below is that mechanism — it is not optional busywork.

---

### Task 1: Live-verify parallel Codex dispatch capability

**Files:** None — this is a live capability smoke-test, not a code change.
It resolves the spec's "Open item carried into implementation"
(`Docs/superpowers/specs/2026-08-12-model-orchestration-skill-design.md`).

**Interfaces:**
- Consumes: the already-installed, already-authenticated `codex:codex-rescue`
  subagent (confirmed ready via `/codex:setup` earlier this session).
- Produces: a pass/fail verdict that gates whether Task 3's
  `delegation-rules.md` and Task 7's `SKILL.md` may assert parallel Codex
  dispatch as a relied-upon capability, or must instead describe it as
  unverified/serial-only.

- [ ] **Step 1: Load the `Agent` tool schema if not already loaded this session**

  Call `ToolSearch` with query `"select:Agent"` to load the tool's full
  schema before invoking it.

- [ ] **Step 2: Dispatch two parallel `codex:codex-rescue` calls in one tool-call block**

  In a single response, invoke `Agent` twice (parallel, not sequential),
  each targeting `subagent_type: "codex:codex-rescue"`, with these
  deliberately trivial, explicitly read-only prompts so the smoke test
  costs minimal real Codex quota and cannot touch the repo:

  - Call A prompt: `Read-only, no file edits. Reply with exactly the text: SMOKE-TEST-A-OK`
  - Call B prompt: `Read-only, no file edits. Reply with exactly the text: SMOKE-TEST-B-OK`

- [ ] **Step 3: Verify independent completion**

  Confirm:
  - Both calls return successfully (no error, no "Task X is still running"
    guard message from either).
  - Call A's forwarded output contains `SMOKE-TEST-A-OK` and Call B's
    contains `SMOKE-TEST-B-OK` (i.e., no cross-talk — each got its own
    prompt answered, not a duplicate/collided response).
  - If the rendered output exposes a job ID or thread ID, confirm A and B
    have distinct IDs.

- [ ] **Step 4: Record the verdict**

  - **If both succeeded independently:** proceed to Task 2 as written.
    Parallel Codex dispatch is verified — Tasks 3 and 7 may state it as a
    supported capability.
  - **If either failed, collided, or one silently blocked on the other:**
    stop before Task 3. Update the design spec's "Open item carried into
    implementation" section with the observed failure mode, then surface
    this to the user before continuing — Tasks 3 and 7 must not assert
    parallel dispatch as reliable until this is resolved. Do not guess a
    workaround unprompted.

- [ ] **Step 5: Commit the verdict**

  If Step 4 confirmed success, no file changed yet — nothing to commit
  from this task alone; the verdict is carried into Task 3/7's content
  instead. If Step 4 required updating the spec's Open Item section,
  commit that update alone:

  ```bash
  git add "Docs/superpowers/specs/2026-08-12-model-orchestration-skill-design.md"
  git commit -m "docs: record parallel Codex dispatch smoke-test result"
  ```

---

### Task 2: Scaffold `Docs/orchestration/`

**Files:**
- Create: `Docs/orchestration/delegation-log.md`

**Interfaces:**
- Produces: the append-only log path that `SKILL.md` (Task 7) and
  `handoff-doc-template.md` (Task 4) reference by name.

- [ ] **Step 1: Create the directory and log file**

  ```markdown
  # Delegation Log

  Append-only. One line per delegation decision: task slug, worker chosen,
  one-line why. Not a full event ledger — see
  `Docs/superpowers/specs/2026-08-12-model-orchestration-skill-design.md`
  for why this stays lightweight.

  Format: `- YYYY-MM-DD | <task-slug> | worker=<codex|claude-subagent|orchestrator> | <why>`

  ---
  ```

- [ ] **Step 2: Verify the file exists and is well-formed**

  Run: `test -f "Docs/orchestration/delegation-log.md" && head -5 "Docs/orchestration/delegation-log.md"`
  Expected: prints the header above without error.

- [ ] **Step 3: Commit**

  ```bash
  git add "Docs/orchestration/delegation-log.md"
  git commit -m "docs: scaffold Docs/orchestration/ delegation log"
  ```

---

### Task 3: Write `references/delegation-rules.md`

**Files:**
- Create: `.claude/skills/model-orchestration/references/delegation-rules.md`

**Interfaces:**
- Consumes: Task 1's verdict (whether parallel Codex dispatch is stated as
  verified or unverified in this file's "Parallel dispatch" note).
- Produces: the task-type classification table `SKILL.md` (Task 7) points
  to and loads on demand.

- [ ] **Step 1: Write the file**

  ```markdown
  # Delegation Rules

  Loaded on demand from `SKILL.md` when classifying a delegable subtask.

  ## Task-type classification

  | Task type | Default worker | Notes |
  |---|---|---|
  | Boilerplate/repetitive codegen | Codex | e.g. test scaffolding across similar files |
  | Mechanical refactor | Codex | rename, extract, pattern-apply across files |
  | Isolated bug-fix implementation | Codex | once root cause is diagnosed by the orchestrator |
  | Research/lookup (docs, API shapes, live endpoint verification) | Codex | e.g. live-verifying a third-party endpoint before designing against it |
  | Architecture/multi-file interface design | Claude (orchestrator) | never delegated |
  | Final assembly / integration | Claude (orchestrator) | never delegated |
  | Read-only codebase exploration | Claude subagent (`Explore`) | cheap, no Codex round-trip needed |

  Ambiguous cases default to Codex unless one of the fallback conditions
  below is met.

  ## Worker selection for parallelizable independent subtasks

  When a task decomposes into N independent subtasks (the case that would
  otherwise mean dispatching N Claude subagents):

  - **Default:** dispatch N parallel `Agent(subagent_type: codex:codex-rescue)`
    calls in one tool-call block, each forwarding its own bounded prompt.
    Real generation cost lands on Codex/ChatGPT quota; the orchestrator only
    pays for N thin-forwarder calls plus collecting results.
  - **Fallback to a genuine Claude subagent** (`Explore`, `general-purpose`)
    only when: (a) the subtask is read-only codebase exploration cheap
    enough Claude-native that a Codex round-trip isn't worth it, (b) Codex
    has already failed or looped on this exact subtask across ≥2 rounds
    with a rewritten handoff doc, or (c) the task is too nuanced to specify
    in a forwarded prompt without losing reasoning that only holds together
    inside Claude's own context.

  Parallel Codex dispatch capability status: **[FILLED IN BY TASK 1'S VERDICT — see below]**
  ```

  For the bracketed status line, substitute one of:
  - If Task 1 succeeded: `Verified live this session (two parallel codex:codex-rescue dispatches completed independently, distinct output, no collision).`
  - If Task 1 failed: `NOT verified — Task 1's smoke test surfaced [failure mode]. Default to serial Codex dispatch until resolved; do not rely on parallel dispatch.`

- [ ] **Step 2: Verify no placeholder text remains**

  Run: `grep -n "FILLED IN BY TASK" ".claude/skills/model-orchestration/references/delegation-rules.md"`
  Expected: no output (the bracketed placeholder was replaced with a real
  verdict sentence in Step 1).

- [ ] **Step 3: Commit**

  ```bash
  git add ".claude/skills/model-orchestration/references/delegation-rules.md"
  git commit -m "feat: add model-orchestration delegation-rules reference"
  ```

---

### Task 4: Write `references/handoff-doc-template.md`

**Files:**
- Create: `.claude/skills/model-orchestration/references/handoff-doc-template.md`

**Interfaces:**
- Consumes: Task 2's `Docs/orchestration/` path.
- Produces: the exact handoff-doc template `SKILL.md` (Task 7) instructs
  the orchestrator to copy before any non-trivial Codex delegation.

- [ ] **Step 1: Write the file**

  ```markdown
  # Handoff Doc Template & Lifecycle

  Loaded on demand from `SKILL.md` before delegating any non-trivial
  subtask to Codex.

  ## When to create one

  Any subtask routed to Codex per `delegation-rules.md` that is more than a
  single trivial, fully-self-contained instruction. Skip it only for
  genuinely one-shot asks (e.g., "fix this exact typo").

  ## Where it lives

  `Docs/orchestration/<task-slug>-handoff.md` — git-tracked, so it survives
  context compaction on either side.

  ## Template

  ```markdown
  # Handoff: <task-slug>
  **Status:** OPEN | IN_PROGRESS | REVIEW | DONE
  **Parent plan:** <link to Docs/superpowers/plans/... if applicable>

  ## Task
  What Codex needs to build/fix — concrete and bounded.

  ## Constraints
  Non-negotiables that apply (pulled from CLAUDE.md, not restated in full —
  reference the section, e.g. "Decimal, never float" or the specific PRD/ADR).

  ## Approaches considered and rejected
  Why, briefly — the exact nuance that dies in a plain prompt summary.

  ## Open questions
  Anything Codex should flag back rather than guess on.
  ```

  ## Lifecycle rules

  - The Codex-facing prompt (built via `gpt-5-4-prompting`) **references
    this file's path** rather than restating its contents inline — the doc
    is the single source of truth both sides re-read, not a paraphrase that
    drifts turn to turn.
  - The orchestrator updates `Status` and appends findings after each round.
  - `Status` only moves to `DONE` after the mandatory adversarial review
    gate (see `SKILL.md`'s core workflow) has run and any findings the user
    chose to act on are resolved.
  - Every handoff doc creation/status-change is mirrored as one line in
    `Docs/orchestration/delegation-log.md`.
  ```

- [ ] **Step 2: Verify the embedded template is syntactically self-contained**

  Run: `grep -c '^\*\*Status:\*\*' ".claude/skills/model-orchestration/references/handoff-doc-template.md"`
  Expected: `1` (the template block's own Status line, confirming the
  nested code fence didn't get mangled).

- [ ] **Step 3: Commit**

  ```bash
  git add ".claude/skills/model-orchestration/references/handoff-doc-template.md"
  git commit -m "feat: add model-orchestration handoff-doc-template reference"
  ```

---

### Task 5: Write `references/escalation-triggers.md`

**Files:**
- Create: `.claude/skills/model-orchestration/references/escalation-triggers.md`

**Interfaces:**
- Produces: the three named Opus-escalation conditions `SKILL.md` (Task 7)
  points to.

- [ ] **Step 1: Write the file**

  ```markdown
  # Opus Escalation Triggers

  Loaded on demand from `SKILL.md` when the orchestrator suspects Opus may
  be warranted.

  ## Rule

  Ask before switching, every time. Never switch silently. Only ask when
  one of the three named conditions below is actually met — not on general
  difficulty or a vague sense that "this might go better on Opus."

  ## The three triggers

  1. **Cross-subsystem architecture ambiguity** — the orchestrator cannot
     resolve an architectural question from `/Docs` alone, and the
     ambiguity spans more than one subsystem (e.g., touches both the
     Import and Dashboard services, or the schema and the API surface
     together).
  2. **Repeated Codex failure on one subtask** — Codex has failed or
     looped on the exact same subtask across 2 or more rounds, even after
     the handoff doc was rewritten to close the gap the first failure
     revealed. (First failure: rewrite the handoff doc and retry with
     Codex. Second failure on the same subtask: this trigger fires.)
  3. **PRD/ADR/schema conflict** — a cross-cutting conflict between the
     PRD, an ADR, and/or the database schema. This already triggers a
     stop-and-ask per CLAUDE.md's "Working style" section; this trigger
     extends that by naming Opus as a candidate resolution path the user
     can choose, not just a flag-and-wait.

  ## How to ask

  State which trigger fired, in one sentence, plus the specific question
  Opus would need to resolve. Do not pre-frame it as a foregone conclusion
  — the user may prefer to resolve it themselves, defer, or use Sonnet
  with more context instead.
  ```

- [ ] **Step 2: Verify all three triggers are present and distinct**

  Run: `grep -c "^[0-9]\. \*\*" ".claude/skills/model-orchestration/references/escalation-triggers.md"`
  Expected: `3`.

- [ ] **Step 3: Commit**

  ```bash
  git add ".claude/skills/model-orchestration/references/escalation-triggers.md"
  git commit -m "feat: add model-orchestration escalation-triggers reference"
  ```

---

### Task 6: Write `references/no-codex-fallback.md`

**Files:**
- Create: `.claude/skills/model-orchestration/references/no-codex-fallback.md`

**Interfaces:**
- Produces: the ask-once/opt-out flow `SKILL.md` (Task 7) points to for
  sessions/users without Codex configured.

- [ ] **Step 1: Write the file**

  ```markdown
  # No-Codex Fallback

  Loaded on demand from `SKILL.md` on the first delegation attempt in a
  session where Codex isn't ready.

  ## Detecting the situation

  Run `node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" setup --json`
  (same check `/codex:setup` uses). If `ready` is `false` — no CLI, or not
  authenticated — this fallback applies.

  ## The ask (once per session, not once per delegation attempt)

  Ask exactly once, offering three options, before attempting any
  delegation:

  1. **Run this session Claude-only via subagents** — same
     `delegation-rules.md` classification table, but the Claude-subagent
     fallback lane (`Explore`, `general-purpose`) becomes the only worker,
     not just the rare-case fallback.
  2. **Name a different tool already configured** (e.g. Gemini CLI) if the
     user wants this skill's workflow adapted around it instead of Codex.
     Adapting the skill itself is a separate follow-up, not something to
     improvise silently in the moment.
  3. **Skip this skill entirely for the session** — offered explicitly,
     not just implied. A teammate who doesn't have or want this workflow
     should be able to opt out cleanly rather than have it forced on them.

  Whichever is chosen, remember it for the rest of the session. Do not
  re-ask on the next delegable subtask.
  ```

- [ ] **Step 2: Verify the detection command is accurate**

  This embeds a command per the Pre-Flight Principle — verify it against
  real output rather than trusting the paraphrase. Run:

  ```bash
  node "/home/ayush/.claude/plugins/cache/openai-codex/codex/1.0.6/scripts/codex-companion.mjs" setup --json | grep -o '"ready": *[a-z]*'
  ```

  Expected: `"ready": true` (given this session's `/codex:setup` already
  confirmed a ready state). Confirms the field name/shape referenced in
  Step 1 is correct — if this session were instead not-ready, this same
  command is what the fallback file tells the orchestrator to run.

- [ ] **Step 3: Commit**

  ```bash
  git add ".claude/skills/model-orchestration/references/no-codex-fallback.md"
  git commit -m "feat: add model-orchestration no-codex-fallback reference"
  ```

---

### Task 7: Write `SKILL.md`

**Files:**
- Create: `.claude/skills/model-orchestration/SKILL.md`

**Interfaces:**
- Consumes: all four `references/*.md` files from Tasks 3–6 (loaded on
  demand, not inlined).
- Produces: the skill Claude Code discovers and triggers on; the target of
  CLAUDE.md's pointer section (Task 9).

- [ ] **Step 1: Write the file**

  ```markdown
  ---
  name: model-orchestration
  description: >
    Use when delegating non-trivial implementation, refactor, boilerplate,
    or research/lookup work to Codex, or when a task decomposes into
    parallelizable independent subtasks that would otherwise mean
    dispatching multiple Claude subagents. Governs the split between
    Claude Code as orchestrator (architecture, multi-file interface
    design, complex debugging, final assembly — never delegated) and
    Codex as the default worker (~90%+ of delegable subtasks), including
    the mandatory per-task handoff doc, the mandatory adversarial review
    gate before any Codex-implemented change is considered done, and the
    named conditions for asking to escalate to Opus. Internal skill,
    project-scoped to this repo and this user's specific
    Claude-account-plus-Codex-account setup — see
    Docs/superpowers/specs/2026-08-12-model-orchestration-skill-design.md
    for the full design rationale.
  ---

  # Model Orchestration

  Internal skill. Coordinates Claude Code (orchestrator) and Codex
  (default worker) to preserve token/quota across accounts, without losing
  the "why" behind a plan at the delegation boundary. Sits on top of the
  `openai/codex-plugin-cc` plugin's existing mechanics
  (`codex:codex-rescue`, `/codex:review`, `/codex:adversarial-review`,
  `gpt-5-4-prompting`) — never reimplements them.

  ## Roles

  - **Orchestrator — Claude Code.** Architecture, multi-file interface
    design, complex debugging, final assembly, all planning. Never
    delegated away.
  - **Worker, default (~90%+) — Codex**, dispatched via
    `Agent(subagent_type: codex:codex-rescue)`. Single subtask: one call.
    Parallelizable independent subtasks: N parallel calls in one tool-call
    block (see `references/delegation-rules.md` for the verified/unverified
    status of this capability).
  - **Worker, rare fallback — a genuine Claude subagent** (`Explore`,
    `general-purpose`). Only per the three conditions in
    `references/delegation-rules.md`.
  - **Escalation — Opus.** Only on the three named triggers in
    `references/escalation-triggers.md`, always with explicit user
    approval first. No silent switch, ever.

  This skill does not prescribe which of the user's two Claude accounts
  (personal Pro / work) handles which work — that stays the user's call,
  session to session.

  ## Reference files — load on demand

  - `references/delegation-rules.md` — task-type classification table;
    load when classifying any delegable subtask.
  - `references/handoff-doc-template.md` — the handoff doc format and
    lifecycle; load before delegating any non-trivial subtask to Codex.
  - `references/escalation-triggers.md` — the three Opus-escalation
    conditions; load when considering whether to ask about Opus.
  - `references/no-codex-fallback.md` — the ask-once/opt-out flow; load
    on the first delegation attempt in a session where Codex isn't ready.

  ## Core workflow

  1. Classify the subtask against `references/delegation-rules.md`.
  2. If Codex-bound and non-trivial: write a handoff doc per
     `references/handoff-doc-template.md` at
     `Docs/orchestration/<task-slug>-handoff.md` before dispatching.
  3. Dispatch via `Agent(subagent_type: codex:codex-rescue)` — one call for
     a single subtask, N parallel calls for independent parallelizable
     subtasks. Use `gpt-5-4-prompting`'s recipe to shape the prompt; the
     prompt references the handoff doc's path rather than restating it.
  4. Append one line to `Docs/orchestration/delegation-log.md` recording
     the decision.
  5. Present Codex's output per the existing `codex-result-handling`
     skill's rules (findings first, ordered by severity; never auto-apply
     fixes).
  6. **Mandatory gate:** before the handoff doc's Status moves to `DONE`,
     run `/codex:review` or `/codex:adversarial-review` against the
     change. This is not optional and not skippable for convenience —
     only the user deciding a finding isn't worth fixing closes it out,
     never a silent skip of the review step itself.
  7. If, at any point, one of the three conditions in
     `references/escalation-triggers.md` is met: state which one fired and
     ask before switching to Opus. Otherwise stay on the default
     orchestrator model.
  8. If Codex isn't configured/ready when Step 3 would otherwise fire:
     follow `references/no-codex-fallback.md` instead.

  ## What this skill does not do

  - Does not hand-roll `codex-companion.mjs` Bash calls directly — always
    through `codex:codex-rescue`.
  - Does not auto-apply any review finding.
  - Does not switch models without asking first.
  - Does not maintain a full event ledger, digest-pinned routing file, or
    phase-folder hierarchy — deliberately lighter than `kiln`, per this
    project's existing conventions.
  ```

- [ ] **Step 2: Verify frontmatter parses as valid YAML**

  Run:
  ```bash
  python3 -c "
  import yaml, re
  text = open('.claude/skills/model-orchestration/SKILL.md').read()
  fm = text.split('---')[1]
  data = yaml.safe_load(fm)
  assert data['name'] == 'model-orchestration'
  assert 'description' in data
  print('OK', data['name'])
  "
  ```
  Expected: `OK model-orchestration`, no exception.

- [ ] **Step 3: Commit**

  ```bash
  git add ".claude/skills/model-orchestration/SKILL.md"
  git commit -m "feat: add model-orchestration SKILL.md"
  ```

---

### Task 8: Pre-Flight self-check (enforcement mechanism, not optional)

Per the Global Constraints' Pre-Flight Principle: every rule in `SKILL.md`
needs a verification step, not just prose. This task IS that step.

**Files:** None created — verification only, against files from Tasks 3–7.

- [ ] **Step 1: Reference-path integrity check**

  Every `references/...` path mentioned in `SKILL.md`'s body must exist on
  disk. Run:

  ```bash
  cd "/mnt/d/Unifolio code" && grep -oE 'references/[a-z-]+\.md' ".claude/skills/model-orchestration/SKILL.md" | sort -u | while read f; do
    test -f ".claude/skills/model-orchestration/$f" && echo "OK: $f" || echo "MISSING: $f"
  done
  ```
  Expected: four `OK:` lines, zero `MISSING:` lines (delegation-rules.md,
  handoff-doc-template.md, escalation-triggers.md, no-codex-fallback.md).
  If any `MISSING:` line appears, stop and fix before continuing — this is
  the exact "single-file delivery truncates it silently" failure mode
  `task-observer`'s skill-authoring guidance warns about.

- [ ] **Step 2: Placeholder scan across the whole skill bundle**

  ```bash
  grep -rniE "TBD|TODO|fill in|implement later|FILLED IN BY" ".claude/skills/model-orchestration/"
  ```
  Expected: no output. (This also catches if Task 3's Step 1 bracketed
  placeholder was accidentally left unresolved.)

- [ ] **Step 3: Rule-vs-enforcement checklist**

  Re-read `SKILL.md`'s "Core workflow" and "What this skill does not do"
  sections. For each stated rule, confirm it maps to something checkable,
  not just asserted prose:

  | Rule | Enforcement |
  |---|---|
  | Adversarial review before DONE | Step 6 of the core workflow names it as a gate tied to the handoff doc's Status field, which is itself git-tracked and diffable |
  | No silent Opus switch | Step 7 requires stating which named trigger fired before asking — a trigger-less ask is itself a violation an implementer/reviewer can catch by re-reading `escalation-triggers.md` |
  | Never auto-apply review findings | Inherited directly from the existing `codex-result-handling` skill's own rule, not re-invented here — no new enforcement needed, just correct delegation to that skill |
  | No hand-rolled `codex-companion.mjs` calls | `codex-cli-runtime`'s own contract already restricts direct script calls to the subagent; this skill's "What this skill does not do" section restates it as a check the orchestrator can self-verify by asking "am I about to Bash this directly?" |

  If any row's enforcement is missing or weak, fix the relevant file now
  rather than deferring.

- [ ] **Step 4: Commit (only if Step 1 or 2 required a fix)**

  If everything passed clean, no commit needed for this task. If a fix was
  required:
  ```bash
  git add ".claude/skills/model-orchestration/"
  git commit -m "fix: close pre-flight gaps found in model-orchestration skill"
  ```

---

### Task 9: Update `CLAUDE.md` with a pointer section

**Files:**
- Modify: `CLAUDE.md` (add a new section, same pattern as the existing
  "Skill Observation" section)

**Interfaces:**
- Consumes: nothing new.
- Produces: the structural trigger that makes this skill reliably
  discoverable, matching the reasoning already applied to `task-observer`'s
  own activation setup.

- [ ] **Step 1: Add the section**

  Insert immediately after the existing "Skill Observation" section (before
  "## Session State"):

  ```markdown
  ## Model Orchestration

  When delegating non-trivial implementation, refactor, boilerplate, or
  research/lookup work — or dispatching parallelizable independent
  subtasks that would otherwise mean multiple Claude subagents — invoke
  the model-orchestration skill first. It governs the Claude
  (orchestrator) / Codex (default worker) split, the mandatory per-task
  handoff doc, and the mandatory adversarial-review gate before any
  Codex-implemented change is considered done. Full design:
  `Docs/superpowers/specs/2026-08-12-model-orchestration-skill-design.md`.
  ```

- [ ] **Step 2: Verify the section landed correctly**

  Run: `grep -n "## Model Orchestration" "CLAUDE.md"`
  Expected: one match, with a line number between the "Skill Observation"
  and "Session State" headings.

- [ ] **Step 3: Commit**

  ```bash
  git add "CLAUDE.md"
  git commit -m "docs: point CLAUDE.md at the new model-orchestration skill"
  ```

---

### Task 10: Update `session.md`

**Files:**
- Modify: `session.md` (prepend a new dated note, per the file's own
  "gets overwritten each session" convention — this is a note for the
  *next* session, so it goes at the top, above the current top entry)

**Interfaces:**
- Consumes: nothing new.
- Produces: the "picking this up cold" continuity note for a fresh session.

- [ ] **Step 1: Prepend the note**

  Insert immediately after the file's existing header/pointer line (before
  the current first `##` section):

  ```markdown
  ## Model Orchestration skill — built this session

  New project-level skill at `.claude/skills/model-orchestration/`
  (internal, not open-source — contains this user's specific
  two-Claude-accounts-plus-Codex setup). Governs delegating implementation
  work to Codex (via the already-installed `openai/codex-plugin-cc`
  plugin's `codex:codex-rescue` subagent) as the default worker, with
  Claude Code staying the orchestrator for architecture/interface
  design/final assembly. Built via the standard brainstorming →
  writing-plans → (subagent-driven-development or executing-plans)
  pipeline, not via `task-observer`'s own observation-driven update flow —
  this was a direct user-commissioned build. Full design:
  `Docs/superpowers/specs/2026-08-12-model-orchestration-skill-design.md`;
  full plan: `Docs/superpowers/plans/2026-08-12-model-orchestration-skill.md`.
  Parallel Codex dispatch capability: see Task 1's recorded verdict in
  that plan for whether it's verified this session.
  ```

- [ ] **Step 2: Verify it landed above the prior top entry**

  Run: `head -20 "session.md"`
  Expected: the new "## Model Orchestration skill — built this session"
  heading appears before the previous top section
  ("## Phase 4 Part 4: category-universe...").

- [ ] **Step 3: Commit**

  ```bash
  git add "session.md"
  git commit -m "docs: record model-orchestration skill build in session.md"
  ```

---

## Post-implementation

Nothing further is auto-scheduled. The skill is dormant until its
description matches a future delegation-shaped task, or `CLAUDE.md`'s
pointer surfaces it. No existing workflow (Phase 4 Scorer work, etc.) is
required to use it — it's available, not mandatory, for the next piece of
delegable work.
