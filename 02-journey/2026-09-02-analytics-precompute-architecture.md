# Analytics precompute architecture designed and built

## For stakeholders

The Analytics dashboard was crashing for users who switched tabs quickly —
every switch fired a fresh batch of slow calculations on top of ones still
running, exhausting the database's connection capacity. The fix, designed
and then built the same session, was not a quick patch: Analytics now
calculates each household's numbers once, in the background, and every
screen simply reads the already-calculated result. This also resolved a
loose thread this vault had flagged as unverified (R-042) — an earlier
design had assumed this "calculate once, fill in cards as they finish"
mechanism existed, and it turned out not to, until this stage built it.

## Technical detail

### Intended outcome

Replace all 7 live-compute Analytics endpoints with one consolidated read
over precomputed rows, eliminating the connection-pool exhaustion caused by
concurrent live compute, without changing what the 7 sections calculate.

### What actually happened

The design (2026-09-02) named and rejected two alternatives before
choosing ECS Fargate `RunTask` recompute: a Postgres-queue-backed worker
(needs a new always-on service ADR-005/006 don't cover) and keeping the 7
endpoints but swapping each to read a precomputed row (perpetuates 7x
request volume for no benefit). The chosen design also caught and corrected
a stale claim in `session.md` — a blocking-event-loop risk it cited as
"still open" had actually already been fixed by an earlier, unrelated
commit (`bb5225f`, 2026-08-27) — flagged for `session.md` to be updated,
not itself part of this design's work.

The implementation plan, written the same day, flagged three deliberate,
disclosed refinements to the literal design text rather than building them
silently: scope processing order (combined household first, then each
member) reuses existing in-process caches instead of adding a new explicit
NAV-warming step; no new `nav_fetch_attempts` table was added, since the
call frequency dropped enough (a handful of times per household per day,
not per page load) that the old cache's abuse-protection reasoning no
longer applied at this volume; and the CAS-import dispatch call was placed
in the import route handler rather than the service function the design
prose named, because only the route handler has the `BackgroundTasks`
instance the dispatch needs.

By the time of the 2026-09-10 staging push, this was confirmed **merged**,
not just designed: a 26-commit worktree implementing the full
`analytics_sections`/`analytics_recompute_status` read/write split was
merged into `feat/enhanced-ui` (`f2daf84`), a real post-merge regression
was found and fixed (missing exception handling in
`_dispatch_recompute_and_release_claim_on_failure`, `8c2f0ef`), and the
full backend suite passed fresh (628 passed, 6 skipped).

### Deviation (if any) — decision or response taken

The migration's actual applied number (`0012_analytics_sections`, per the
2026-09-11 AWS staging doc) does not match the number the design/plan wrote
at design time (`0010`) — two unrelated migrations landed on the branch
first between design and merge. Recorded as ordinary plan drift in
[ADR-015](../03-decisions/ADR-015-analytics-precompute-architecture.md),
not a contradiction to resolve.

### Result

Built and merged on the backend side. The matching frontend migration
(consuming the new consolidated endpoints) is a separate, subsequent stage
— see the 2026-09-10 journey entry. The merge deleted the 14 old
per-section routes immediately, which made the frontend migration a launch
blocker rather than a nice-to-have, not an optional follow-up.

### Related

- ADR-015 — analytics precompute architecture
- R-042 — resolved by this stage (see the updated entry in `07-risks-and-debt.md`)
- INV-008 — an unrelated bug found the same push cycle, in a sibling scheduled job
- Evidence: `08-evidence/documents/specs/2026-09-02-analytics-precompute-architecture-design.md`
- Evidence: `08-evidence/documents/plans/2026-09-02-analytics-precompute-architecture.md`
