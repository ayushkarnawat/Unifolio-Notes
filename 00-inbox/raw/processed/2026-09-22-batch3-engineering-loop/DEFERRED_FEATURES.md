# Deferred / Not-Yet-Built Features — Unifolio

Working tracker of everything the product docs have explicitly deferred, scoped out, or
left unbuilt as of 2026-08-17. Pulled from `session.md`, `CLAUDE.md`, and
`Docs/PRDs/PRD-01` through `PRD-04` (plus the ADR and Migration Plan docs for
infrastructure items). Not a planning doc — like `session.md`, this gets updated as
scope moves, not accumulated as history. When an item here gets built, move it out
rather than marking it done in place.

Two things this file does **not** cover, deliberately, because they're a different kind
of gap than "deferred feature":
- **Known implementation gaps / tech debt** on already-built features (e.g. the NAV
  cache's single-flight limitation) — tracked in `CLAUDE.md`'s "Still open" list instead.
- **Built-but-not-yet-reviewed work** (the CAS import lifecycle redesign) — not deferred,
  just missing a review pass; see `CLAUDE.md`'s Session State section.
Both are still listed in a short appendix at the bottom for completeness, since they
answer "what's not done yet" even though they aren't scope deferrals.

## PRD-01 — CAS Parser v2

| Feature | Spec Source | Status | Deferred Reason | Priority |
|---|---|---|---|---|
| MFCentral OTP/API import | PRD-01 §Out of Scope / Future Considerations | Not built | Gated behind a live AMFI ARN partner relationship; timeline unconfirmed | Future — no committed date |
| Account Aggregator (AA) import | PRD-01 §Non-Goals / Out of Scope | Not built | Bundled with the MFCentral gating above — both routes need the same partner/regulatory path | Future — no committed date |
| Distributor/ARN performance analytics UI | PRD-01 §Out of Scope, §Future Considerations | Not built (data capture done) | Explicitly split into its own PRD; PRD-01 only captures the ARN field so this isn't blocked later | Future — separate PRD |
| NSDL/CDSL demat statement parsing (equity holdings) | PRD-01 §Out of Scope, §Future Considerations | Not built | Explicitly out of v1; CDSL Easi/Easiest flagged as a possible Phase 2 path in the competitive-analysis research note | Phase 2 |
| Multi-user auth (beyond single implicit portfolio) | PRD-01 §Out of Scope | Not built | Accepted as the prototype model for MVP, not a gap to close before launch | N/A for MVP |

## PRD-02 — Signup & Onboarding

| Feature | Spec Source | Status | Deferred Reason | Priority |
|---|---|---|---|---|
| Formal risk-profiling / regulated advice | PRD-02 §Non-Goals | Not built | Unifolio isn't SEBI RIA-registered — this is a permanent non-goal, not a timing deferral | N/A (permanent) |
| KYC/identity verification beyond CAS parsing needs | PRD-02 §Non-Goals, §Out of Scope | Not built | No regulatory requirement for a pure tracking product; PAN handling stays scoped to what CAS parsing itself needs | N/A (permanent) |
| Equity/broker account linking during onboarding | PRD-02 §Out of Scope | Not built | MF-only MVP — onboarding shouldn't ask about assets the product can't yet import | Future, tied to the equity look-through gap below |
| Onboarding-answer-driven dashboard personalization | PRD-02 §Out of Scope | Not built | PRD-02 captures the data only; using it to change dashboard content is a Main Dashboard PRD concern | Future |
| Lighter-weight HNI/family-office onboarding surface | PRD-02 §Future Considerations | Not built (single flow ships for all segments) | Deliberately deferred rather than rejected — revisit once real usage data exists rather than designing two flows speculatively | Post-launch |
| Advisor/CA-assisted onboarding (bulk client setup) | PRD-02 §Future Considerations | Not built | Deferred until the target-customer question (Product Context doc §7) is resolved | TBD |
| PIN/biometric return-login (FR-2a) + full Auth/Security policy (rate-limiting, lockout, device management) | PRD-02 Open Questions; Database Schema `otp_requests`/`sessions` notes | Foundational schema only — login functions at MVP without it | Explicitly deferred to a dedicated Auth/Security PRD; the schema hooks (`attempt_count`, `device_info`) exist so this can be layered on later without a migration | TBD |

## PRD-03 — Main Dashboard

| Feature | Spec Source | Status | Deferred Reason | Priority |
|---|---|---|---|---|
| Equity-holdings-via-MF look-through (which stocks a fund actually holds) | PRD-03 §Non-Goals, §Out of Scope, §Future Considerations | Not built | No constituent-holdings data source identified yet; needs its own research pass (AMFI/AMC factsheets or a third-party API) | Future, post-core-dashboard |
| Real bank-account cash flow integration | PRD-03 §Non-Goals, §Out of Scope | Not built | Cash flow shown is investment-only, derived from parsed CAS transactions — not a bank feed | N/A for MVP / Future |

## PRD-04 — MF Analytics Dashboard

Everything else PRD-03 deferred (sector/AMC allocation, category ranking, scorer,
benchmark comparison, weighted TER) — **PRD-04 backend and frontend are now both fully
built**, so those are not listed here. What PRD-04 itself still defers:

| Feature | Spec Source | Status | Deferred Reason | Priority |
|---|---|---|---|---|
| Cap-wise composition (true large/mid/small-cap breakdown within a fund) | PRD-04 §Out of Scope/Data-Gated, standing reminder | Not built | Requires each fund's underlying portfolio holdings — SEBI mandates monthly AMC disclosure but there's no single aggregated public feed (40+ AMCs, mostly PDF/Excel); a real data-engineering project, not a build-inside-this-PRD task | Fast-follow, Post-MVP |
| Stock-level fund overlap detection | PRD-04 §Out of Scope/Data-Gated, standing reminder | Not built | Same underlying data gap as cap-wise composition above; explicitly meant to be solved together with PRD-03's equity look-through as one combined effort, not twice | Fast-follow, Post-MVP |
| Deep multi-year rolling-return analysis (e.g. full rolling-return heatmaps) | PRD-04 §Out of Scope/Data-Gated | Not built | Beyond what the scorer and category comparison need; possible future enrichment once the core scorer shipped (it now has) | Future |
| Equity-specific analytics (stock-level metrics) | PRD-04 §Non-Goals | Not built | MF-only per overall MVP scope | N/A (permanent) |
| Scorer weighting evolution beyond the fixed v1 formula (Return 45% / Risk 30% / Consistency 25%) | PRD-04 §Future Considerations | Not built (v1 formula shipped and locked) | Explicitly framed as something to revisit once real usage data exists, not a v1 gap | Future |
| Index-fund mega-category sub-bucketing (split AMFI's 1,150-scheme "Other Scheme - Index Funds" into smaller peer-groups for category-ranking/Scorer performance + comparison quality) | `Docs/superpowers/specs/2026-08-20-index-fund-mega-category-split-deferred.md` | Reviewed and deferred, not started | Investigated with a concrete bucket list (both a fine-grained per-benchmark option and a coarser AMFI-precedented asset-class option); reviewed with Ayush and finance-domain peers, who judged the only design that actually shrinks the category (bespoke per-benchmark regex buckets) as an unrecognized-by-AMFI taxonomy not worth the mis-bucketing/maintenance risk, while the AMFI-native alternative doesn't solve the size problem | Revisit only if index-fund category-ranking/Scorer load time becomes a demonstrated user-facing problem (currently mitigated by the existing BUG-001 15-min per-category cache) |

## Infrastructure & Deployment

| Feature | Spec Source | Status | Deferred Reason | Priority |
|---|---|---|---|---|
| ADR-006 recurring NAV-refresh job (EventBridge Scheduler → ECS Fargate `RunTask`) — the real fix behind dashboard load-time ("Fix C") | ADR-Technical-Stack-Decisions (ADR-006, Accepted); `session.md`'s "Fix C" section | Architecture decided, not implemented | Deployment-phase work per the Migration Plan's Readiness Checklist; Fix A/B/D (background prefetch, parallelized fetch, process-local cache) are explicit local-dev-first stand-ins layered on top, not replacements | High once deployment starts — current mitigations are load-bearing until then |
| AWS RDS PostgreSQL migration + full AWS deployment (ECS Express Mode, scoped S3, EventBridge Scheduler) | Migration-Plan-SQLite-to-Postgres.md §Readiness Checklist | Not started | Checklist requires this to happen before any real user data exists — a launch gate, not a soft target; local SQLite + Docker Postgres remains the dev/functional-test setup until then | Launch-blocking prerequisite, intentionally sequenced last |

## Appendix — related but not scope deferrals

**Built, not yet independently reviewed** (see `CLAUDE.md` Session State): the CAS
import lifecycle redesign (11-state state machine, coverage-gap detection,
opening-balance resolution, CAMS mailback flow, and the matching frontend) — intern-authored,
passes the full test suite, but has had no review pass against `Decimal`-never-`float`,
no-PAN-persistence, and no-raw-CAS-storage the way Phase 3b's redesign got before merge.

**Known implementation gaps on already-shipped features** (see `CLAUDE.md`'s "Still
open" list): a held scheme with no obtainable NAV silently disappearing from
holdings/allocation instead of showing an "unavailable" state; `confirm_import`'s
plan-type override having no server-side 409 backstop; no DB uniqueness constraint on
the "self" `household_members` row (frontend-mitigated only); a dead
`row.return_percentage_1y` field reference in `HoldingsTable.tsx`; `@bklit/bar-chart`
never actually installed despite an early frontend brief calling for it (hand-rolled
SVG/Tailwind used instead — installing it properly is a deliberately deferred, separate
task since it would overwrite `src/lib/utils.ts`); `scheme_universe.py`'s
`get_category_universe` doing an exact-string match on `sebi_category`, meaning schemes
tagged under AMFI's legacy `"Index Funds - Equity/Debt/Hybrid Funds"` headers are
invisible to comparison against schemes tagged `"Other Scheme - Index Funds"` even when
they track the same index (surfaced while investigating the mega-category split above,
not confirmed high-impact, not investigated further); the `compute_holdings` cache's
accepted lack of single-flight coordination (harmless, documented, superseded once
ADR-006's job above ships); and the SIP Upcoming/This Month tab switcher's incomplete
ARIA `aria-controls` IDREF pairing (inactive tab points at a not-yet-rendered
`tabpanel` id) — a Low finding accepted per the model-orchestration skill's stopping
heuristic rather than restructuring to always-mounted dual panels.
