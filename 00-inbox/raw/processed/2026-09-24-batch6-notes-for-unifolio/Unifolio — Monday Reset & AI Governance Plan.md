
_Captured from voice notes: Aug 14–17, 2026_ _Owner: Ayush Karnawat_

---

## The Core Problem (Honest Diagnosis)

> "I'm not reading the code, refactoring it, and understanding what's changing and what's not changing. It's just getting fucked more and more."

The root issue is not Claude — it's the **feedback loop being broken**:

1. Claude writes code
2. Claude runs tests → says "green"
3. Ayush sees bugs Claude missed
4. Ayush tells Claude → Claude "fixes" it
5. Nobody audited what actually changed
6. Loop repeats with more surface area

This is a **process failure**, not an AI failure. The fix is structural, not prompt-based.

---

## Monday: Code Archaeology Session

**Do this before touching any feature work.**

### Step 1 — Run the Refactor Pass

- Run `ponytail` command (or equivalent codebase scan) to get a structural map of the repo
- Goal: understand what files exist, what each one does, what owns what

### Step 2 — Do a Manual Walkthrough (Not Claude's Summary)

Ayush + Claude together, file by file:

- `frontend/` — what screens are built, what's wired vs. mocked
- `backend/` — which routes exist, which are actually functional
- `analytics dashboard` — specific audit of what's built vs. what was spec'd

Document the output as: **`CODEBASE_MAP.md`** — a plain-English map of the actual current state.

### Step 3 — Identify the "DO NOT TOUCH" Zones

Mark sections of code that:

- Work correctly right now
- Are complex enough that AI rewrites them badly
- Contain core financial math (XIRR, FIFO, Decimal handling)

Tag these in code with:

```python
# ⛔ DO NOT TOUCH — Human-reviewed, financially critical. Any change needs Ayush sign-off.
```

And maintain a list in `CLAUDE.md`:

```
## OFF-LIMITS ZONES
- backend/app/calc.py — pure financial functions, human-verified
- [add as discovered]
```

---

## What's Actually Broken (Known Issues to Triage)

### Analytics Dashboard

- [ ] Loading issues — Claude said "fixed," still broken
- [ ] Several features Pratik flagged as missing — not yet built
- [ ] Unknown how many of the 5-6 built things are actually working end-to-end

### General

- [ ] Tests go green but bugs exist that Claude doesn't self-catch
- [ ] Unclear what features were deferred vs. never started vs. partially built

### Action: Build a `DEFERRED_FEATURES.md`

Pull from: `session.md`, `CLAUDE.md`, PRDs Columns: Feature | Spec Source | Status | Deferred Reason | Priority

---

## New PR + Git Workflow (Starting Immediately)

### The Rule: No Direct Commits to Main

**Old (bad) pattern:**

```
build → commit → push → "oh why did we push that"
```

**New pattern:**

```
feature branch (worktree) → PR → Ayush reviews → merge
```

### Worktree Assignment

Each Claude Code session gets its own worktree + branch. Already set up — enforce it:

- Session 1 (personal): `worktree/session-1-[feature]`
- Session 2 (unifolio work): `worktree/session-2-[feature]`

### PR Rules

Every PR must have:

- [ ] What changed (1-3 sentences, not a wall of text)
- [ ] Why it changed (link to issue or session note)
- [ ] What to test manually before merging
- [ ] No PR merges without Ayush reading the diff

### Tell Aditya the Same

When he joins: same rules apply from day one. More PRs, fewer cowboy commits.

### Token Optimization — Stop Running Full Test Suites Constantly

- Don't run `npm test` + full backend suite on every small change
- Run targeted tests: only the module being changed
- Save full suite runs for pre-PR checks

---

## AI Governance Rules (Making Claude a Builder, Not an Architect)

### The Problem

> "Do not let AI become your architect. Do not let it dictate terms."

Claude's failure modes in this codebase:

- Makes changes without explaining the tradeoff
- "Fixes" things that weren't the real problem
- Self-reports green tests while bugs remain
- Accumulates technical debt across sessions

### Rules for Claude Code Sessions

**1. Claude proposes, Ayush decides architecture** Any change that touches: schema, API contracts, component structure, data flow → needs explicit Ayush approval before implementation, not after.

**2. Decisions get logged** Create `DECISIONS.md` — any time Claude makes a structural call, it goes here with date + rationale. If Ayush didn't explicitly approve it, it's a draft, not canon.

**3. No "I fixed it" without a test Ayush can run manually** Claude cannot claim a fix is done unless it provides:

- The exact URL/action to reproduce the bug
- The expected behavior after fix
- Steps to verify manually

**4. Model strategy (already in place — enforce it)**

- Sonnet 4.6 → implementation loop (fast, cheap)
- Stronger model → PAN removal, money math, any session where Claude has failed 3 times

**5. Software development cycle stages — Claude must respect the phase** Define the current phase before starting a session. Claude operates differently in each:

| Phase        | What Claude can do                | What requires Ayush        |
| ------------ | --------------------------------- | -------------------------- |
| **Spec**     | Draft, suggest, brainstorm        | Final sign-off on scope    |
| **Build**    | Implement to spec                 | Any deviation from spec    |
| **Review**   | Flag issues, explain what changed | Merge decision             |
| **Fix**      | Targeted fixes only               | Root cause confirmation    |
| **Refactor** | Cleanup with no behavior change   | Confirm behavior preserved |
|              |                                   |                            |

---

## Sub-Agent + Multi-Session Usage

> "Just hardcore usage of subagents and multiplayer based systems for two Claude sessions working on something common."

### When to use dual sessions

- One session: backend work on a feature
- Other session: frontend of the same feature
- Coordination: shared spec in `CLAUDE.md` + separate worktrees
- Risk: git conflicts — mitigated by worktree branches, never working on the same file

### When to use sub-agents

- Any task that fails 3 times → escalate to a sub-agent with fresh context
- Long research tasks (competitive analysis, API docs parsing) → sub-agent handles it while main session continues building

### Codecs Usage (Personal Note)

- Currently underusing codecs / token compression
- Start using them for: large context windows, repeated long docs passed into sessions
- Goal: reduce token waste on repeated boilerplate context

---

## G-Stack / Skills — Selective Adoption

> "Let's start using G-Stack if it's really worth it."

**Decision: Selective, not wholesale.**

Use pm-skills that already fit the workflow:

- `deliver-acceptance-criteria` → before any PR goes to Aditya
- `develop-adr` → for any new architecture decision
- `foundation-meeting-recap` → after standups with Aditya once he joins
- `measure-instrumentation-spec` → before analytics dashboard ships

Skip the rest until team is larger.

---

## Open Questions to Resolve This Week

1. **Analytics dashboard audit** — what exactly did Pratik say was missing? Pull those notes.
2. **Deferred features** — go through `session.md` and PRDs, compile the real list
3. **`CODEBASE_MAP.md`** — do the walkthrough, build this
4. **`DECISIONS.md`** — start it retroactively for decisions already made
5. **`DEFERRED_FEATURES.md`** — build from existing docs, don't start from scratch

---

## Files to Create / Update This Week

| File                   | What it is                                    | Priority    |
| ---------------------- | --------------------------------------------- | ----------- |
| `CODEBASE_MAP.md`      | Plain-English map of current repo state       | P0 — Monday |
| `DECISIONS.md`         | Log of architectural decisions with rationale | P0 — Monday |
| `DEFERRED_FEATURES.md` | What's not built yet and why                  | P0 — Monday |
| `CLAUDE.md` update     | Add DO NOT TOUCH zones + phase rules          | P0 — Monday |
| `AGENTS.md` update     | Software cycle phase definitions + PR rules   | P1 — Monday |

---

_Last updated: 17 Aug 2026_ _Status: Draft — needs Ayush review before sharing with Aditya_