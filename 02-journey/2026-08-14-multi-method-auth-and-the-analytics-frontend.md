# Multi-Method Auth and the Analytics Frontend

Date: 2026-08-14
Status: Complete (design and plans); execution partly deferred

## For stakeholders

The largest single design effort in this batch. Until this day, the only way
into Unifolio was a phone number and a one-time code. This day added Google
sign-in and email one-time codes as equal alternatives — while keeping the
phone number as the thing every account ultimately converges on, because
that is the identifier Indian financial records are keyed to.

The most interesting part is what happens when two ways of signing in turn
out to belong to the same person. The obvious approach — quietly merge them
— was rejected. Instead the user is told what was found and asked to prove
they own the existing account before anything is linked. Nothing merges
silently.

Apple sign-in was designed, researched, and then deferred over an annual
developer-account fee, with the research preserved and a visibly disabled
"Coming soon" button left in the interface rather than the option being
removed entirely. The email provider was chosen on cost — but no real email
is actually sent yet; the product ships with a stub.

One thing that will block launch surfaced here and has not been solved: a
Privacy Policy page does not exist anywhere in the product, and Google
requires one before a real sign-in consent screen can be published.

The same day also produced the design for the analytics dashboard's
interface, to be built by the external coding agent with the team's own
tooling acting as tester and reviewer rather than implementer.

## Technical detail

### Intended outcome

Add Google Sign-In and email+OTP alongside phone+OTP, with every account
converging on a verified phone number regardless of starting method, and an
explicit, non-silent account-linking policy for collisions — backend and
frontend as two dependent plans. Separately, design the analytics dashboard
frontend.

### What actually happened

**Identity model.** A new identities table becomes the source of truth for
"which credentials prove who this user is," decoupling that from the user
row, which becomes a profile and anchor. A second table holds a
just-verified Google or email identity that cannot yet be attached to a
session — either because the account is brand new and still owes its
mandatory phone step, or because it collided with an existing account and
needs step-up re-authentication. The phone column stays unique and
non-nullable; a user row cannot exist without a matching phone identity.

**This reverses the design's own first draft.** The document's revision
history runs v1.0 through v1.6, all on 2026-08-14, and the mandatory-phone
anchor is a reversal of what v1.0 proposed. Recorded as a reversal, not
presented as a clean first decision — see
[ADR-008](../03-decisions/ADR-008-phone-anchored-multi-method-identity.md).

Further decisions:
- **Identity precedence is Google > Email > Phone** wherever only one
  identity can be displayed or named.
- **Email OTP reuses the existing OTP table**, generalised to accept either
  a phone number or an email address. A separate email-OTP table was
  considered and rejected as a duplicate of working machinery.
- **Google is integrated via the rendered sign-in button and ID-token
  verification against Google's public keys** — no client secret, no token
  exchange. One Tap and the redirect flow were both rejected; the redirect
  flow in particular would destroy the in-memory state the auth flow keeps,
  since there is no router and no persisted flow state.
- **Pending verifications use one shared 10-minute TTL** for both triggers,
  not two different values.
- **The email provider is an abstraction with a stub implementation only.**
  Postmark was chosen on a cost comparison against SES, Resend and
  SendGrid — see [ADR-009](../03-decisions/ADR-009-transactional-email-provider.md)
  — but no real sending is wired up.
- **Apple Sign-In is deferred** over a $99/year developer-account cost, with
  the research preserved and a disabled placeholder button shipped.

**Frontend.** The existing step machine was extended, not replaced: two new
steps and one new rendering mode, with the mandatory-phone case reusing the
*existing* phone and OTP steps via a context flag rather than introducing a
fifth step. The verify call returns a three-way outcome — logged in, link
required, or phone required — modelled as a discriminated union so no
caller can forget a case. The pill order is Google, Apple (disabled), Email,
Phone; an earlier draft of the plan transcribed this order wrongly and the
error was caught and corrected on 2026-08-15, which is recorded rather than
silently fixed.

The frontend plan also performed a **branch-reality check** before writing
anything, and this is the most useful factual output of the day: on the
working branch, Tailwind and shadcn/ui are genuinely in use and there is
still no router — but **Bklit UI is not actually installed.** The project's
component configuration registers its registry as a pull-on-demand source;
no package exists. The showcase panel was therefore hand-built on the
existing chart primitives.

**Analytics frontend design.** Specified Bklit UI for "mostly everything,"
with one deliberate carve-out: the existing allocation donut is reused
unchanged, because the design schema's consistent-chart-language rule
outweighs visual consistency with a new component library. Implementation
was assigned to Google Antigravity, with Claude Code acting as tester,
reviewer and comparator — a role the design itself notes is "a third worker
category the model-orchestration skill doesn't document."

### Deviation — decision or response taken

| Deviation | Response |
|---|---|
| The design's own v1.0 did not make phone the universal anchor | Reversed within the same day across six revisions; the reversal is recorded, not hidden. ADR-008 |
| Silent account merging is the path of least friction | Rejected. Step-up re-authentication required before any link |
| ADR-001 states the product has no public marketing surface | Overridden for the decorative auth panel, explicitly and in writing, in the design's own Explicit Deviations section. Noted in ADR-008's consequences |
| PRD-02 FR-2b is superseded by this design | Stated explicitly in the design document rather than left for a reader to infer |
| Apple Sign-In requires a paid developer account | Deferred; research preserved; disabled placeholder shipped rather than the option removed |
| Google's consent screen requires a Privacy Policy | **Unresolved.** No Privacy Policy page exists anywhere. R-023 |
| The analytics frontend design assumes Bklit UI is available | It is not installed. Two same-day documents disagree. R-019 |
| Antigravity is a worker category the orchestration skill doesn't cover | Flagged in the design; recorded as R-029 |

### Result

A complete multi-method auth design and two dependent implementation plans,
with the identity model, linking policy, and provider choice all settled —
and with email delivery, Apple support, and the Privacy Policy all
explicitly outstanding. An analytics frontend design whose component-library
premise is contradicted by the same day's branch check.

### Related

- [ADR-008](../03-decisions/ADR-008-phone-anchored-multi-method-identity.md),
  [ADR-009](../03-decisions/ADR-009-transactional-email-provider.md)
- [ADR-001](../03-decisions/ADR-001-frontend-application-architecture.md) (overridden in part)
- [Frontend composition](../06-architecture/frontend-composition.md)
- [Risks and debt](../07-risks-and-debt.md) — R-019, R-023, R-024, R-029, R-030
- Sources: `08-evidence/documents/plans/2026-08-14-multi-method-auth-backend-plan.md`,
  `08-evidence/documents/specs/2026-08-14-multi-method-auth-design.md`,
  `08-evidence/documents/plans/2026-08-14-multi-method-auth-frontend-plan.md`,
  `08-evidence/documents/specs/2026-08-14-multi-method-auth-frontend-design.md`,
  `08-evidence/documents/specs/2026-08-14-analytics-frontend-design.md`

## Addendum — 2026-09-22: both plans were fully executed, 2026-08-14 through 2026-08-17

This stage's title line ("Complete (design and plans); execution partly
deferred") described the state as of batch 2b's source material. Later-
ingested source material confirms both the backend plan (11 tasks,
commits `39db87d` through `2784b61`, 441 backend tests passing) and the
frontend plan (10 tasks, final review clean, 219 frontend tests passing)
were executed in full, 2026-08-14 through 2026-08-17 — see the addendum on
[ADR-008](../03-decisions/ADR-008-phone-anchored-multi-method-identity.md)
for the detailed evidence. What remains outstanding is unchanged: real
Google sign-in against a published consent screen and real email delivery
are still not evidenced anywhere in this batch either.

Separately, a second body of work landed the same day on a branch that had
drifted apart from this one since 2026-08-13 — the fund Scorer's backend
completion, the CAS import lifecycle redesign, and a UI/UX foundation pass
— found and merged during a branch-reconciliation session. See
[2026-08-14 — CAS import lifecycle and branch reconciliation](2026-08-14-cas-import-lifecycle-and-branch-reconciliation.md).

### Addendum evidence

- `08-evidence/documents/engineering-loop/backend.md`, `08-evidence/documents/engineering-loop/log.md`

## Addendum — 2026-09-23: the analytics frontend itself was built, same day, and R-019's Bklit question is resolved

This stage's R-019 flagged that the analytics frontend design was written
against Bklit UI, which the same day's branch check had found not
installed. Source material for the actual build (dispatched to Google
Antigravity, same external-agent arrangement R-029 names) confirms the
question resolved itself in the branch check's favor: **Bklit UI was not
adopted.** Phase 1 (allocation, cost/TER, category ranking screens) was
built and completion-reported the same day, 2026-08-14; Phase 2 (Scorer,
Benchmark, Fund Score Detail/S20) followed, dependent on Phase 1 having
merged first.

In both phases, Claude Code's role matched exactly what R-029 already
names — tester, reviewer, comparator, not implementer — and in both
phases it caught real defects the implementing agent's own completion
report did not disclose:

- **Phase 1:** Antigravity's own completion report already disclosed one
  correction (Bklit was never actually used, despite being named in the
  brief). Claude Code's independent review then found 8 further issues:
  a build-breaking bug in a currency-formatting export, 7 `tsc` type
  errors, two float-subtraction violations of the Decimal-never-float rule
  (fixed via a new shared `diffDecimalStrings` helper — the same helper
  Fix 1 of the 2026-08-19 correction-plan round 2 later reused for the
  category-CAGR fix), and an incidental deletion of an unrelated comment,
  restored. Final state: `tsc` clean, 51/51 files, 197/197 tests passing.
- **Phase 2:** Antigravity's completion report claimed both "`tsc` clean"
  and "all tests passing." **Both claims were false** — Claude Code's
  independent re-verification found 7 `tsc` errors and 3 failing tests
  (test-authoring bugs, not production defects), plus a High-severity
  Decimal-discipline violation (float subtraction in `BenchmarkSection.tsx`
  — explicitly noted as "the same bug category caught and fixed in Phase 1;
  this instance was missed" by the implementing agent), plus 2 Low
  findings. All fixed. Final state: `tsc` clean; the project-wide test
  suite was flaky under sandbox parallelism (resource contention, not a
  regression), but a scoped analytics-only run was clean (5/5 files,
  13/13 tests).

This closes R-019's open question with a decision, not just an
observation: Bklit UI was never installed or adopted anywhere in this
codebase across either phase. It does **not** resolve R-029 — no amendment
to ADR-011 covering external-agent workers exists in any source material
ingested so far; this addendum is corroborating evidence for R-029's
existing "not covered by any workflow" finding, including two instances of
an external agent self-reporting a clean state that Claude Code's
independent check then found to be false.

### Addendum evidence

- `08-evidence/documents/orchestration/analytics-phase1-frontend-log.md`
- `08-evidence/documents/orchestration/analytics-phase2-frontend-log.md`
- `08-evidence/documents/orchestration/analytics-phase1-frontend-brief.md`
- `08-evidence/documents/orchestration/analytics-phase2-frontend-brief.md`
