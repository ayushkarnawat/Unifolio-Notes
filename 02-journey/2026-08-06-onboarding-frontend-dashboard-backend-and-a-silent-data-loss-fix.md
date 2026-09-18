# Onboarding Frontend, Dashboard Backend, and a Silent Data-Loss Fix

Date: 2026-08-06
Status: Complete

## For stakeholders

Three pieces of work landed on this day, and the smallest of them is the most
important.

The largest was the onboarding experience: the landing screen, phone login,
the four onboarding questions with working back-navigation, family setup,
and the family CAS upload flow where several statements are uploaded for
several family members and processed as a batch. The second was the main
dashboard's entire backend — what a portfolio is worth, what was paid for it,
what has been gained and lost, how it is split across fund houses, which
monthly investments are still running, and the family-wide roll-up of all
of it.

The third was a small database migration that closed a real data-loss bug.
An earlier change had normalised transaction amounts so that purchases and
redemptions were both stored as positive numbers. That change had a
side-effect nobody had noticed: a purchase and a redemption of exactly the
same size on the same day in the same folio had become indistinguishable to
the system's duplicate check, so one of them was being silently discarded on
import. It was fixed by making the transaction type part of the duplicate
check. The full account is in [INV-003](../04-investigations/INV-003-transaction-dedupe-silent-drop.md).

## Technical detail

### Intended outcome

**Phase 2b** — the onboarding frontend (PRD-02): landing, phone+OTP, the
four-question flow with back-navigation, family setup, and the Family CAS
Upload subsystem, wired to the Phase 2 backend and reusing Phase 1b's
existing Import Review screens.

**Phase 3 backend** — PRD-03's Main Dashboard: FIFO-based holdings, allocation,
active-SIP detection, cash flow, monthly value snapshots, and family
aggregation, as read-mostly endpoints over already-imported data.

**Dedupe migration** — widen the `transactions` dedupe key from four columns
to five, in the database and in the application, together.

### What actually happened

All three completed.

**Onboarding frontend.** A new `features/auth/` area owns everything from
landing through onboarding completion, under an auth context that resolves
session state once on load and drives the app's top-level render branch.
Navigation is a history array plus a cursor rather than a router — Back
moves the cursor without truncating forward history, so a user who steps
back and forward again does not lose answers. The `onboarding_step`
vocabulary is a locked frontend constant even though the backend column is
free text, so that resume-after-reload is deterministic.

Two constraints shaped the family-upload subsystem:
- The account holder's own household-member row must be resolved
  **list-then-create**, never blind-create, because no PATCH endpoint exists
  for household members and a session resumed after a reload would otherwise
  insert a duplicate `self` row.
- Family CAS files are parsed **sequentially, never in parallel** — the
  backend holds a single in-memory preview per session, so concurrent parse
  calls would race each other. This is a backend-shape constraint expressed
  as a frontend rule.

The upload queue is in-memory only and is lost on reload. IndexedDB
persistence was considered and rejected as premature. The payoff screen is a
single aggregate confirmation across all family members, not one per member.

**Dashboard backend.** Seven service modules, each owning one concern, six of
them exposing GET routes; ten new read routes in total. The organising
constraint: **every compute function is parameterized by a list of household
member IDs**, so one implementation serves both the per-member view (a
one-item list) and the family aggregate (every member the caller owns) —
never two code paths. Family aggregate responses wrap a per-member status
list so a member with no data is shown as present-but-empty rather than
silently dropped.

Cost basis is **FIFO**. NAV is fetched on demand and cached rather than
refreshed by a scheduled job — scheduling is deployment-phase infrastructure
and was out of scope. An "active" SIP means a contribution inside a 40-day
window, chosen to tolerate a late monthly instalment without declaring a
stopped SIP active. Switch transactions are excluded from cash flow because
they move money within the portfolio rather than in or out of it.

One correction was made deliberately and is worth preserving: the TDD's
API-surface table listed the coarse allocation endpoint under the Analytics
service. Phase 3 recorded that as a documentation slip and placed allocation
in Dashboard, where the holdings engine it depends on already lives. This
agrees with the vault's existing "two allocation endpoints, deliberately not
merged" entry rather than contradicting it — Dashboard keeps the coarse
view, Analytics later adds the granular one.

**Dedupe migration.** A new additive migration (`0002`), never editing the
frozen `0001`. Both the SQLite path (via a batch table rebuild, since SQLite
cannot alter a constraint in place) and the PostgreSQL path (an alter on the
partitioned parent, which propagates to every partition) **look the existing
constraint name up at migration time** rather than hardcoding a guess,
because migration `0001` let both dialects auto-generate that name. The
application-side duplicate check was widened in the same change: doing only
one side would have turned silent drops into 500-level integrity errors.

### Deviation — decision or response taken

| Deviation | Response |
|---|---|
| A normalisation fix had silently created a data-loss path | Root-caused and fixed the same day; DB constraint and application check widened together, never separately. See INV-003 |
| No `PATCH /household-members` endpoint exists | Every caller resolves the `self` row by list-then-create; recorded as a global constraint so no task treats it as a surprise |
| Backend holds one in-memory preview per session | Family uploads sequenced client-side; parallel parse explicitly forbidden |
| `users` has no `name` column | The onboarding name answer is held in local state and used only when creating the account holder's own household-member row |
| The PostgreSQL migration path could not be executed | No live PostgreSQL in the development sandbox; the PostgreSQL branch of migration `0002` was written and reviewed but never run. Recorded as R-021 |
| Securities transaction tax and stamp duty are not treated as cost-basis-adjusting | Flagged in the design rather than silently assumed; recorded as R-028 |

### Result

A user can now sign up, answer the onboarding questions, add family members,
upload statements for each of them, and land on a dashboard backend capable
of valuing all of it. The dashboard frontend (Phase 3b) and distributor
comparison were both deferred to separate plans at this point.

### Related

- [INV-003](../04-investigations/INV-003-transaction-dedupe-silent-drop.md)
- [Decisions log](../03-decisions/decisions-log.md) — 2026-08-06 entries
- [API surface](../05-docs/reference/api-surface.md),
  [Frontend composition](../06-architecture/frontend-composition.md)
- [Risks and debt](../07-risks-and-debt.md) — R-003 (context), R-021, R-027, R-028
- Sources: `08-evidence/documents/plans/2026-08-06-phase-2b-onboarding-frontend.md`,
  `08-evidence/documents/specs/2026-08-06-phase-2b-onboarding-frontend-design.md`,
  `08-evidence/documents/plans/2026-08-06-phase-3-main-dashboard-backend.md`,
  `08-evidence/documents/specs/2026-08-06-phase-3-main-dashboard-backend-design.md`,
  `08-evidence/documents/plans/2026-08-06-transaction-dedupe-type-migration.md`,
  `08-evidence/documents/specs/2026-08-06-transaction-dedupe-type-migration-design.md`
