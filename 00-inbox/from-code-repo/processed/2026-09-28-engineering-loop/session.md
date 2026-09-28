# Session state — 2026-09-26

Working notes for picking this project back up cold. Not a planning doc — see
`Docs/superpowers/plans/` for those. This file tracks *where things stand*,
gets overwritten each session, and isn't meant to accumulate history — the
permanent, append-only record of everything that's happened is `log.md`
(session-by-session), `backend.md`/`database.md` (backend/schema changes
only), and `decisions.md` (product/technical decisions). This file used to
duplicate all of that inline going back to Phase 0; trimmed 2026-09-26 down to
pointers, since `log.md` now has the full history backfilled and is the
authoritative place for it.

**Read this file, then `CLAUDE.md`'s Session State section, before re-deriving
anything by re-reading the whole repo.**

## Latest (2026-09-24): CAS import PAN check moved to upload time — committed, not uncommitted

Fixes the staging bug where every first import on a fresh account showed "We couldn't
match this statement to an existing family member" (and froze in the Family flow). Root
cause: PAN-based attribution ran at Confirm, but a member's PAN was only stored *after*
a confirm, so nothing could ever match on a first import.

What changed (spec `Docs/superpowers/specs/2026-09-24-pan-at-upload-attribution-design.md`,
plan `Docs/superpowers/plans/2026-09-24-pan-at-upload-attribution.md`):
- New `backend/app/services/import_/pan_claims.py` replaces `attribution.py` (deleted).
  `/imports/parse` now takes `household_member_id` and claims the parsed PAN for that
  member as *pending* (new column `household_members.pan_pending_until`, migration 0016);
  conflicts return 409 `cross_account_pan_blocked` / `pan_belongs_to_other_member` /
  `pan_mismatch_for_member` right after upload. `/imports/confirm` only finalizes — no
  prompts, no `confirmed_member_override`. New `POST /imports/sessions/{id}/discard`.
  `/cas-imports` claims permanently inline. PAN/CAS storage format unchanged.
- Frontend: all "Continue anyway / Switch to" UI removed. Just Me/dashboard/mobile show the
  existing Import blocked popup (cross-account) or a new "This PAN already exists" popup
  at upload. Family shows "This PAN already exists" with Change CAS file / Skip.
- Final review (fresh opus reviewer): 3 Important fixed (claim moved after mfapi
  enrichment so SQLite's write lock isn't held across network calls; Family re-upload form
  got a Back; lost unique-index race retries instead of 500ing), 7 minors deferred.

Verified fresh: backend 714 passed / 8 skipped; frontend 484 passed across all 82 files;
`tsc -b --noEmit` clean. **Correcting this file's own prior entry:** this was previously
logged here as "UNCOMMITTED, awaiting user review" — that was stale by the time this pass
started. `git log`/`git status` confirm it's fully committed (`11f7dfc`, `b8d88a8`,
`b8901e4`, `bdfa2ba`), working tree clean. A draft plan for per-PAN statement splitting
(family CAS statements only attribute to the first folio's PAN holder today — a known,
not-yet-built gap) exists at `Docs/superpowers/plans/2026-09-24-per-pan-statement-splitting.md`,
not yet built.

## Previously undocumented gap (2026-09-15 → 2026-09-23), now backfilled into `log.md`

This file went stale for about nine days/~50 commits before this pass — none of the
below existed anywhere in `session.md`, `log.md`, `backend.md`, or `database.md` until
this pass added it. Full detail for each is in `log.md`'s dated entries; short version:

- **2026-09-16**: Knowledge-graph refresh, codebase-analysis metadata added.
- **2026-09-17**: Real email-OTP delivery via `PostmarkEmailProvider` (first real
  `EmailProvider` implementation), independent per-channel delivery mode kept
  (`EMAIL_DELIVERY_MODE` vs `OTP_DELIVERY_MODE`); docs-viewer infra; audit/architecture
  doc batch.
- **2026-09-18**: ADR-004 reopened — PAN now persisted (encrypted, per household member)
  and the raw CAS PDF retained 30 days, superseding the original "no PAN, no raw file,
  ever" decision. See `decisions.md`'s 2026-09-18 entry and
  `Docs/superpowers/specs/2026-09-18-pan-cas-attribution-design.md`.
- **2026-09-19**: Cross-account PAN block surfaced as a UI popup instead of a silent
  freeze; CAS S3 storage + Postmark infra Terraform; PAN/CAS/secrets technical docs.
- **2026-09-22**: Phone-gate collision now errors like email's instead of silently
  logging in (a different bug than Still-Open item 9 below); SES email provider added
  behind the existing `EmailProvider` abstraction; marketing-site Terraform.
- **2026-09-23**: Postmark removed entirely (code + Terraform) — SES is now the only
  email provider, not kept dormant (see `decisions.md`'s SES-reversal entry); QA
  schema/journey review; HTML OTP email templates.
- **2026-09-24**: PAN check moved to upload time (see "Latest" above).

## Recent sessions before the gap (2026-09-07 → 2026-09-12) — condensed, full detail in `log.md`

- **2026-09-12**: Fund Score card redesign (score /10 display, reversed tier convention,
  plain-English verdicts, expandable evidence/methodology sections) — built via
  `subagent-driven-development`, 9 tasks, whole-branch review (1 Critical + 5 Important +
  9 Minor, all adjudicated/fixed), full suites clean. Precompute-cache backfill and a
  manual browser smoke check both explicitly deferred (AWS/ECS infra not live yet at the
  time; no browser tool in this environment).
- **2026-09-11**: Investor 10-item feature batch (Profile page, account deletion w/
  5-day grace period, email/phone change via OTP, theme toggle, import history/delete,
  header XIRR, allocation sort, AMC/asset-class drill-down, decimal-formatting fix) — 3
  review rounds + a PM/tech-lead gap pass, committed. AWS staging prerequisites/runbook
  doc drafted (`Docs/superpowers/plans/2026-09-11-aws-staging-prerequisites.md`).
- **2026-09-10**: Analytics dashboard frontend migrated onto the single precompute
  contract (`GET /analytics/{scope}`) for both desktop and mobile.
- **2026-09-08/09**: Terraform Phases 1-3 applied to a real AWS account — staging VPC,
  RDS Postgres, ECS cluster/service, ALB all live in `ap-south-1`. ECS image push +
  `alembic upgrade head` against real RDS both done and verified. Phase 4 (frontend
  S3+CloudFront) authored/reviewed, not yet applied at the time; Phase 5 (ACM/Route
  53/HTTPS) drafted, not dispatched. A real AWS IAM key was briefly pasted into chat and
  committed to this file in plaintext — rotated and the offending commit rewritten
  before it was ever pushed; never write a live credential into a tracked file again,
  redact to `<redacted>` or reference the IAM user/key name only.
- **2026-09-07**: AWS account created, `ap-south-1` confirmed, `unifolio.in` cut over to
  Route 53 (Microsoft 365 mail records preserved), `app.unifolio.in`/`staging.unifolio.in`
  domain architecture decided, staging networking set to use fck-nat over a managed NAT
  Gateway.

Everything before 2026-09-07 (Phase 0 through the 2026-08-27 mobile-UI-polish session,
the AMFI TER event-loop-starvation fix, the compliance-audit remediation rounds, etc.) is
in `log.md`, not duplicated here — see that file's dated entries for the full narrative.

## Still open, carried forward from earlier phases, not yet revisited

*(Moved here from `CLAUDE.md` 2026-08-24 — that file's Session State section is a
short pointer only, per its own header note; this is the detail it points to.)*

1. **RESOLVED 2026-09-03 (= compliance audit F8).** A held scheme with no obtainable NAV
   silently vanished from holdings/allocation/aggregates, no error or placeholder.
   **Product call resolved 2026-09-02**: user chose (b) — a degraded row with a visible
   "NAV unavailable" flag, NAV-dependent fields null, FIFO-derived fields (units held,
   invested, realized gain) always populated. Design: `Docs/orchestration/
   f8-nav-unavailable-degraded-row-handoff.md` (`distributor_comparison.py`'s identical
   sibling bug explicitly flagged as a separate, out-of-scope follow-up, not silently
   fixed alongside this). Implemented across 2 review rounds: round 1 fixed an
   understated "Total Invested" and a missing caption; round 2 caught (via adversarial
   review, independently confirmed) that `gainPercentage` mixed populations — dividing
   valued-only profit by an all-holdings invested total, understating the return — fixed
   by adding a `valuedInvestedVal` (valued-holdings-only) denominator in both
   `DashboardView.tsx` and `MobileDashboardView.tsx`. Status: DONE, committed.
2. **RESOLVED 2026-09-02 (= compliance audit F3).** No DB uniqueness constraint on the
   "self" `household_members` row — frontend-mitigated client-side only; real fix needed
   a migration (confirmed missing — migrations `0001`-`0010` existed, none touched this).
   **Read-only violation check run 2026-09-02** against the local dev SQLite DB
   (`backend/unifolio_dev.db`) first: 39 `self`-relationship rows across 46 distinct
   users, **zero users with more than one** — no existing dirty data to remediate,
   simplifying the fix to a straight constraint-add + API guard with no data-migration
   remediation strategy needed. Fixed: migration `0011_household_members_one_self_row.py`
   adds a partial unique index on `household_members(user_id) WHERE relationship =
   'self'`, expressed once via SQLAlchemy's `sqlite_where=`/`postgresql_where=` kwargs on
   a single `op.create_index` call (no runtime dialect branch needed, unlike F6's fix);
   `create_household_member` (`services/dashboard/household_members.py`) gained a
   pre-check raising `DuplicateSelfMemberError`, mapped to a 409 in the
   `/household-members` route (`api/dashboard.py`). Verified: new unit tests
   (`tests/services/dashboard/test_household_members.py`), an API 409 test
   (`tests/api/test_dashboard_routes.py`), a new Postgres functional test proving the
   `postgresql_where` branch enforces the constraint against a real server
   (`tests/functional_postgres/test_partitioning.py::test_household_members_one_self_row_per_user_on_postgres`),
   and the full 587-test SQLite suite plus 5 Postgres-marked tests, all green.
   `Docs/PRDs/Database-Schema-Unifolio.md` bumped to v1.5 documenting the new index.

   User separately raised a PAN-based idea for a related-but-distinct problem (detecting
   the same real person across multiple household-member/CAS-upload records), stating a
   belief that PAN is "currently persisted." At the time this conflicted with this
   codebase's explicit, test-guarded rule — no PAN persistence, ever
   (`tests/models/test_no_pan_field.py`, `Docs/PRDs/Database-Schema-Unifolio.md`'s Data
   Classification section) — flagged back to the user 2026-09-02 per CLAUDE.md's "stop
   and say so" rule rather than silently built or silently dropped. **Note added
   2026-09-26**: that invariant was itself superseded 2026-09-18 when ADR-004 reopened to
   allow encrypted PAN persistence — `test_no_pan_field.py` was rewritten (not deleted)
   to guard the new invariant instead (no *unencrypted* PAN-shaped column on any mapped
   model). Read as historical: at the time this paragraph was written, PAN persistence
   genuinely didn't exist yet.

   **Resolved 2026-09-02**: user confirmed no PAN persistence, sign-off given for a
   non-PAN alternative, design left to Claude, explicitly asked to be "extensive." Design:
   split into two cases with different privacy remedies. Same-user cross-household-member
   duplicates get a new `(folio_number, amc_name)` signal added to `resolve_attribution`'s
   existing within-household matching (prioritized over its existing weaker name/email
   signal, safe to auto-offer a redirect since same tenant). Cross-user duplicates (two
   different Unifolio accounts holding the same real person's data) get a new, separate,
   advisory-only `detect_cross_account_duplicate` check — never blocks, never merges,
   never leaks the other account's identity, folio-match primary / name-match weaker
   secondary signal. Full design + rationale + rejected alternatives:
   `Docs/orchestration/non-pan-duplicate-person-detection-handoff.md`. **RESOLVED
   2026-09-03**: round 2 wired the design into the actual production import paths —
   a shared `enforce_attribution_confirmation` gate added to `attribution.py` and
   called at all 3 backend commit sites, a structured `member_mismatch` 409, and
   desktop/mobile confirmation UI. This wiring surfaced a standalone architectural gap —
   two parallel import backends had independently drifted to need the identical fix wired
   in twice — documented at `Docs/orchestration/two-parallel-import-backends-architectural-gap.md`.
   **Superseded 2026-09-18/24**: `attribution.py` was itself later deleted and replaced
   by PAN-based `pan_claims.py` once ADR-004 reopened (see "Latest" above) — the non-PAN
   duplicate-detection logic this item describes predates that rework; check current
   `pan_claims.py` before assuming this exact code path still exists verbatim. Status:
   DONE, committed.
3. `HoldingsTable.tsx` references a dead `row.return_percentage_1y` field that doesn't
   exist on the real API type — harmless (client-computed fallback always runs), never
   cleaned up.
4. `category_ranking.py`'s `_bulk_nav_on_or_before` (BUG-001 fix, 2026-08-18): the
   per-scheme N+1 query pattern is gone (one `MAX(date) GROUP BY` query per target date,
   bounded by a 15-min per-category cache), but the DB-side scan to compute each
   `MAX(date)` still isn't index-seek-bounded without a `LATERAL` join — a primitive
   unused elsewhere in this codebase and unverifiable via query plan on SQLite. Accepted
   as a documented limitation rather than a third fix round (correctness-safe, cost
   already bounded by the cache). Full follow-up action and rationale:
   `Docs/PRDs/Migration-Plan-SQLite-to-Postgres.md`'s "Deferred Postgres-Only
   Optimizations" section — revisit with `EXPLAIN ANALYZE` once Postgres is live (real
   AWS RDS Postgres has been live in staging since 2026-09-09 — worth actually revisiting
   this rather than treating it as still hypothetical).
5. `DashboardView.tsx`'s SIP Upcoming/This Month segmented control (`sip-tab-upcoming`/
   `sip-tab-month`) always renders both tab buttons' `aria-controls` IDs, but only the
   active tab's `role="tabpanel"` actually exists in the DOM — the inactive tab's
   `aria-controls` points at an ID that doesn't resolve, an incomplete ARIA tabs IDREF
   pattern. Accepted as a documented limitation rather than a third fix round, per the
   model-orchestration skill's stopping heuristic — negligible real-world screen-reader
   impact since the tab/panel pairing is already correctly conveyed via
   `role`/`aria-selected`/`aria-labelledby` on the panel that does exist, and a full fix
   means always mounting both panels (one `hidden`) instead of one conditionally-rendered
   panel. Revisit only if a real accessibility-audit or user complaint surfaces it as an
   actual usability problem. Full review-round detail: `Docs/orchestration/
   delegation-log.md`'s 2026-08-19 entries.
6. **RESOLVED 2026-09-02 (= compliance audit F7).** `compute_holdings`'s per-folio
   `Transaction` N+1 query pattern (`backend/app/services/dashboard/holdings.py`) —
   discovered as a side effect of the 2026-08-21 distributor-comparison-portfolio-level
   rewrite, confirmed pre-existing and explicitly out of scope for that change at the
   time. Fixed: one batched `Transaction` query across all folios (`folio_id.in_(...)`),
   grouped by `folio_id` in Python preserving per-folio chronological order (the FIFO lot
   processor requires it). Status: DONE, committed.
7. **RESOLVED 2026-08-27, commit `bb5225f`.** A colleague's AMFI TER `ReadTimeout`s were
   root-caused to event-loop starvation from a blocking `db.commit()` inside an
   `async def` (this backend's SQLAlchemy engine is fully synchronous, single
   worker/event loop) — not AMFI slowness. `bb5225f` added `commit_off_loop` (routes
   `db.commit()` through `asyncio.to_thread`) and rewired every reachable commit across
   all 8 affected service files, with a regression test. Full narrative: `log.md`'s
   2026-08-25/26 entry.
8. **RESOLVED 2026-09-03 (= compliance audit F4), partially.** ADR-006's EventBridge
   Scheduler background jobs (daily NAV refresh, monthly TER, quarterly AAUM, daily
   benchmark) — piece (a), the 4 job-entrypoint scripts + wiring `amfi_aaum_client
   .refresh_aaum_data` into a real caller, is done and committed
   (`backend/scripts/jobs/`, `backend/tests/scripts/`). **Still not built**: piece (b),
   the actual EventBridge Scheduler + ECS Fargate Terraform module — deliberately
   deferred to the infra-authoring phase. An AWS account, ECR repo, and ECS cluster now
   all exist in staging (since 2026-09-08/09) so this is no longer blocked on
   infrastructure existing — it's just not been picked up yet.
9. **Phone-login OTP verify silently creates a new account for an unrecognized phone
   number, instead of erroring like the email channel does.** Found by the user
   2026-09-11 manually smoke-testing staging: logging in with a phone number that has no
   matching account still goes through the OTP-send/verify flow and ends by creating a
   brand-new account, rather than telling the user no account exists and directing them
   to sign up. **Independently re-checked against current code 2026-09-26 — still
   present, unchanged.**

   Root cause, confirmed against the code: `backend/app/api/auth.py`'s
   `verify_otp_route` (phone-OTP channel), in the branch that handles a verify call with
   no `pending_token` (i.e. a plain login attempt, not part of an in-progress signup/
   phone-gate flow) — `find_or_backfill_phone_identity` returning `None` falls straight
   through to an unconditional new-`User` INSERT. The equivalent email-OTP branch,
   `verify_email_otp`'s no-`pending_token` path, already does the right thing:
   `find_identity_by_subject` returning `None` raises a 401 ("No account found for that
   email — sign up instead.") instead of creating an account. The two channels'
   identical-shaped branches have simply diverged. **Distinct from the 2026-09-22
   phone-gate collision fix** (`c8a4a8e`/`31e112a`), which only touches the
   `pending_token`-present branch — that fix did not incidentally resolve this one.

   Frontend-side, confirmed this is a clean single-sided gap, not a shared code path:
   `Landing.tsx` only renders the "Continue with Phone" button in **login mode**; signup
   mode offers email + Google only, with no direct phone-signup entry point anywhere in
   the UI. So the phone no-`pending_token` verify branch is *only* ever reached from a
   genuine login attempt — fixing it to 401 like email can't break a legitimate
   phone-signup flow, because that flow doesn't exist.

   **Also worth carrying forward for whoever picks this up**: even the email channel
   doesn't fully match the UX the user described as ideal. Today, email's existence
   check happens at **verify time** — the OTP is still requested and sent, and the user
   still lands on the "enter your code" screen, before the 401 fires. The user's stated
   expectation implies the check should happen at **request time**
   (`/email-otp/request` / `/otp/request`), before any OTP is sent at all, for both
   channels — not just bringing phone's verify-time behavior in line with email's
   verify-time behavior. Moving the check to request time is a slightly larger change
   (touches both `request_*` handlers, not just both `verify_*` handlers) and has one
   real tradeoff worth surfacing to the user before building it: an unauthenticated
   "does this identifier have an account" check at request time is a mild
   account-enumeration surface (probeable without ever completing an OTP). Low stakes
   for this product, but a deliberate tradeoff, not a free improvement.

   **Explicitly deferred, not fixed, by user decision 2026-09-11**: the user judged this
   redundant work right now, reasoning that once a real OTP provider is attached later,
   invalid/nonexistent phone numbers will need to be handled as part of that integration
   anyway. **Note added 2026-09-26**: real OTP/email delivery (SES) has since gone live
   (2026-09-17/22/23) — worth checking with the user whether that changes the deferral
   calculus now that "the real provider" referenced in the original deferral reasoning
   actually exists.
