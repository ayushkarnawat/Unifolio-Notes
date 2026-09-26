1. Everything rooted in "no fund-level stock holdings data" — the big one

This single data gap (no aggregated public feed of what stocks each fund actually holds — SEBI mandates monthly AMC disclosure, but it's 40+ AMCs each publishing their own PDF/Excel, no standard format or API) blocks four separate features:

Feature: Cap-wise composition (true large/mid/small-cap split within a fund)
Where: PRD-04 Out of Scope
Why deferred: Needs underlying holdings; "a real data-engineering project, not a build-inside-this-PRD task"
────────────────────────────────────────
Feature: Stock-level fund overlap detection (which of your funds hold the same stocks)
Where: PRD-04 Out of Scope
Why deferred: Same data gap — explicitly meant to be solved together with the item below, not twice
────────────────────────────────────────
Feature: Equity look-through (which stocks a fund holds, shown on the Main Dashboard)
Where: PRD-03 Non-Goals
Why deferred: Same gap, PRD-03 side of it
────────────────────────────────────────
Feature: PE/PB Valuation Overlay (5% of the new Scorer v2, the "is this fund cheap or expensive relative to its category" signal)
Where: Scorer v2, investigated 2026-08-24
Why deferred: No official free API for fund-level PE/PB in India either — SEBI's own disclosures don't include valuation ratios. Three paths scoped: build

in-house (ingest AMC disclosures + stock-level PE/PB + weighted-harmonic-mean per Value Research's published formula — "the largest new engineering
surface in scorer v2"), buy a licensed feed (Morningstar Direc, not engineering), or scrape an aggregator (rejected, ToS
risk). Not decided — flagged as open question #6 for the finance lead
────────────────────────────────────────
Feature: Equity-specific analytics (stock-level metrics generally)
Where: PRD-04 Non-Goals
Why deferred: Permanent, not a timing deferral — MF-only is the whole MVP's scope

This is the one place a decision-maker actually needs to pick a path (build vs. buy) before work can start.

2. Scorer methodology — mid-rebuild

- Live today: 3-component v1 (Return 45% / Risk 30% / Consistency 25%, ±0.25 TER nudge).
- Being built now (your current branch): 11-component v2 from ethodology (Return, BeatsCategoryAvg, TopQuartileFreq,MaxDrawdown, DownCapture, Sortino, InformationRatio, UpCapture, PE/PB, CostLevel, CostTrend). Formula-level approved, but 9 engineering-judgment questions
are unresolved before code can start deterministically: rollincency-weighting curve, sampling frequency, "category average"definition, expense-trend scoring rule, PE/PB combination, per-category benchmark mapping (see #3), minimum-peer-set widening rule, provisional-fund
(1–3Y) component eligibility.
- Also open: fund_scores table only stores the v1's 5 fields — needs a migration for 11 component percentiles + confidence + peer count + methodology
version.

3. Benchmark comparison gaps

- TRI vs. price-return index. A fund's XIRR reflects reinveste against a plain price index (no dividends) isn't a faircomparison. Deferred — shipped only a disclosure fix (labels now say "Nifty 50 (Price Return)"). Full fix needs two unconfirmed things: whether NSE's
existing free endpoint even serves a TRI variant, and whether (nobody's checked returned values against known TRI figures).Real fix is scoped in tri-benchmark-deferred-plan.md if picked up.
- Only 4 Nifty indices exist (Nifty 50/500/LargeMidcap 250/Midebt, hybrid, gold, international, sectoral, Flexi/Multi/SmallCap, ELSS — falls back to Nifty 500, a broad equity index, which is a bad comparison for a debt fund. Confirmed gap, deferred: "fixing this properly
requires sourcing debt/gold/international indices that don't eoday — a new-data-source feature." This is also the same openquestion blocking Scorer v2's Down/Up Capture and Information Ratio components for non-equity categories.
- Deep multi-year rolling-return heatmaps — deferred as a futue scorer/category comparison need.

4. Category ranking

- Index-fund mega-category (1,150 schemes lumped under one AMFth two concrete bucketing options, presented to you andfinance-domain peers, both rejected: a fine-grained regex split was judged an "unrecognized-by-AMFI taxonomy" not worth the mis-bucketing/maintenance
risk; the AMFI-native alternative doesn't actually shrink the d time becomes a real user-facing problem.
- Hard suppression below 5 peer schemes — the correction plan wanted categories with <5 peers hidden entirely; you decided to keep the existing soft-flag
behavior instead, since hiding data would hurt real niche catel funds).
- Tie-aware ranking — skipped; Decimal-precision NAV math essentially never produces exact ties, so this was solving a practically nonexistent problem.
- Peer-set normalization (dedupe share classes of the same undhecked, enterprise-grade governance not needed at currentscale.
- Side finding: schemes tagged with AMFI's legacy "Index Fundsheaders are invisible to comparison against the same-indexschemes tagged "Other Scheme - Index Funds" — not confirmed high-impact, not investigated further.

5. Known correctness gaps, deliberately not fixed (not scope deferrals, but relevant "why it's not built right")

- Silent partial-XIRR when a benchmark cash-flow date can't resolve (drops the flow instead of failing) — kept as-is, consistent with this codebase's
established graceful-degrade pattern elsewhere.
- Valuation-date/XIRR terminal-value alignment (today's holdings value vs. each scheme's own last-available NAV, no staleness disclosure) — deferred,
needs deeper tracing first.
- TER/AAUM pipeline's looser fuzzy scheme-matcher (0.55 confidence threshold) vs. the tighter import-time matcher — deferred, no confirmed live risk yet.
- No formal NAV/market-data freshness-tolerance policy (informeferred, enterprise hardening.
- No calculation-lineage/audit metadata (methodology_version, valuation_date, etc.) on analytics responses — deferred, "governance/compliance tooling appropriate for a later maturity stage."
- category_ranking.py's _cagr can crash with a 0/0 division on thin multi-category NAV history during aggregate scoring — real, reproducible, pre-existing bug, explicitly not fixed, ledgered for a follow-up ticket.


6. Cost (TER) / infrastructure

- AAUM refresh has no production scheduler — an on-demand function exists, but nothing calls it on a cadence. Deferred to the AWS deployment phase (same gate as everything else infra).
- TER/AAUM/NSE client hardening (request coalescing, bounded retries, source-health monitoring) — deferred, "production-ops maturity... appropriate once real production traffic exists."
- The bigger infra items (ADR-006's recurring NAV-refresh job, AWS RDS Postgres migration) aren't analytics-specific but are why the dashboard's load-time mitigations today are stand-ins rather than the real fix.

---
On your "equity and stocks" instinct: you were right — it's the single largest live gap, showing up as cap-wise composition, overlap detection, the PRD-03 look-through, and now the Scorer v2 PE/PB component, all blocked on the same unsolved "no aggregated AMC holdings feed" problem, and it's the one item that currently needs a real build-vs-buy decision from you before Scorer v2 work can fully proceed.


Now I have the full picture across the rest of the product. Here's everything deferred product-wide, organized by area, with what's needed to actually build each one.

Auth & Onboarding (PRD-02) — biggest cluster of currently-live stubs

Feature: Real email delivery (Postmark)
Deferred because: Product decided Postmark as the provider, but it wasn't wired into the multi-method-auth build — StubEmailProvider ships instead, logs
instead of sending. Confirmed still true in code today (email_provider.py)
What's needed to build it: A Postmark account (~$15/mo past 100 emails), DNS access to add SPF/DKIM/Return-Path records for the sending domain, a decision
on the sending address, and an AWS Secrets Manager entry once deployed. Hard blocker: the code already refuses to run in stub mode against any non-SQLite
 DB, so this must land before the Postgres migration, not after
────────────────────────────────────────
Feature: Real SMS delivery (phone OTP)
Deferred because: Same stub pattern, same gate (otp_delivery_mode) — deferred since the original Phase 2 auth build
What's needed to build it: An SMS gateway integration (Twilio or equivalent) — not yet scoped/chosen in any doc, unlike email where Postmark is already the
confirmed choice
────────────────────────────────────────
Feature: Sign in with Apple
Deferred because: Requires a $99/year Apple Developer Program membership — a real recurring cost the product owner needs to sign off on separately from
everything else
What's needed to build it: Approve the membership → Services ID, .p8 private key, domain-verification file, auth_identities.provider enum migration to add
'apple', new AppleButton.tsx + route. Full spec already written (2026-08-14-multi-method-auth-design.md §"Future Scope"), not a re-derivation. Not
required for compliance since Unifolio isn't on the App Store yet
────────────────────────────────────────
Feature: Privacy Policy / Terms of Service pages
Deferred because: Content pending product-owner input — code deliberately didn't draft policy text
What's needed to build it: Route/link scaffolding already expected by the auth spec; just needs real copy from you, then wiring
────────────────────────────────────────
Feature: PIN/biometric return-login + full Auth/Security policy (rate-limiting, lockout duration, device management)
Deferred because: Explicitly punted to a dedicated future Auth/Security PRD — foundational schema (attempt_count, device_info) already exists so this
layers on without a migration later
What's needed to build it: Needs its own PRD; not started
────────────────────────────────────────
Feature: Formal risk-profiling / regulated advice
Deferred because: Permanent non-goal — Unifolio isn't SEBI RIA-registered
What's needed to build it: N/A, not a build item
────────────────────────────────────────
Feature: KYC/identity verification beyond CAS parsing needs
Deferred because: Permanent — no regulatory requirement for a pure tracking product
What's needed to build it: N/A
────────────────────────────────────────
Feature: Onboarding-driven dashboard personalization, lighter HNI/family-office flow, advisor/CA bulk-client onboarding
Deferred because: Deliberately deferred, revisit once real usage data exists or the target-customer question resolves
What's needed to build it: Needs product decision first, not an engineering task

CAS Import (PRD-01)

┌────────────────────────────────────┬────────────────────────────────────────────────────┬──────────────────────────────────────────────────────────┐
│              Feature               │                  Deferred because                  │                      What's needed                       │
├────────────────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ MFCentral OTP/API import           │ Needs a live AMFI ARN partner relationship —       │ Business/partnership work, not engineering               │
│                                    │ timeline unconfirmed                               │                                                          │
├────────────────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ Account Aggregator (AA) import     │ Same partner/regulatory gate as above              │ Same                                                     │
├────────────────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ NSDL/CDSL demat statement parsing  │ Explicitly out of v1                               │ CDSL Easi/Easiest flagged as a possible Phase 2 path in  │
│ (equity holdings)                  │                                                    │ competitive research, not scoped                         │
├────────────────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ Distributor/ARN performance        │ Split into its own PRD; PRD-01 only captures the   │ Needs a dedicated PRD to be written                      │
│ analytics UI                       │ ARN field so nothing's blocked                     │                                                          │
├────────────────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ Multi-user auth (beyond single     │ Accepted as the MVP prototype model                │ N/A for MVP                                              │
│ implicit portfolio)                │                                                    │                                                          │
└────────────────────────────────────┴────────────────────────────────────────────────────┴──────────────────────────────────────────────────────────┘

Main Dashboard (PRD-03) & Analytics — the equity/stock data gap

Already covered in detail last turn (equity look-through, cap-wise composition, stock-level overlap, PE/PB valuation, equity-specific analytics) — all rooted in no aggregated public feed of AMC monthly portfolio-holdings disclosures. That's the single largest cross-cutting gap in the whole product, touching PRD-03, PRD-04, and Scorer v2 simultaneously. Build path: an in-house AMC-by-AMC ingestion pipeline (40+ formats, no standard API) or a licensed feed (Morningstar Direct/ICRA/CRISIL) — a build-vs-buy decision, not yet made.

Real bank-account cash flow integration — deferred, N/A for MVP; today's cash flow is investment-only, derived from parsed CAS transactions, not a bank feed.

Infrastructure & Deployment — the launch gate

┌───────────────────────────────────┬───────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────┐
│              Feature              │                     Deferred because                      │                    What's needed                    │
├───────────────────────────────────┼───────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────┤
│ ADR-006 recurring NAV-refresh job │ Deployment-phase work; today's dashboard-load mitigations │                                                     │
│  (EventBridge Scheduler → ECS     │  (background prefetch, parallelized fetch, process-local  │ Build once AWS deployment starts                    │
│ Fargate)                          │ cache) are explicit local-dev stand-ins                   │                                                     │
├───────────────────────────────────┼───────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────┤
│                                   │ Migration Plan's Readiness Checklist requires this before │ Needs: backend deployed via ECS, Alembic history    │
│ AWS RDS PostgreSQL migration +    │  any real user data exists — a hard launch gate, not a    │ exercised against real Postgres at least once, zero │
│ full AWS deployment               │ soft target                                               │  real user data collected yet, foundational auth    │
│                                   │                                                           │ tables validated against Postgres                   │
├───────────────────────────────────┼───────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────┤
│ LATERAL-join rewrite of           │ Can't be properly verified without a real Postgres query  │ Run EXPLAIN ANALYZE once Postgres is live; only     │
│ _bulk_nav_on_or_before (category  │ plan — SQLite has no LATERAL semantics to benchmark       │ rewrite if the planner isn't already doing an       │
│ ranking query)                    │ against; current approach already measured faster than    │ index-seek                                          │
│                                   │ the closest SQLite equivalent                             │                                                     │
├───────────────────────────────────┼───────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────┤
│ AAUM production refresh scheduler │ Same AWS-deployment gate                                  │ Same                                                │
└───────────────────────────────────┴───────────────────────────────────────────────────────────┴─────────────────────────────────────────────────────┘

Known implementation gaps (not scope deferrals, but "not built right yet")

These are bugs/shortcuts the team explicitly chose to leave rather than fix, each with a stated revisit trigger:
- A held scheme with no NAV silently vanishes from holdings/allocation instead of showing "unavailable"
- No DB uniqueness constraint on the "self" household_members row (frontend-mitigated only)
- Dead row.return_percentage_1y field reference in HoldingsTable.tsx
- compute_holdings's per-folio N+1 query pattern — flagged as needing its own isolated perf pass
- SIP tab switcher's incomplete ARIA aria-controls pairing — accepted as Low severity
- @bklit/bar-chart never actually installed (hand-rolled SVG/Tailwind used instead) — installing it properly would overwrite src/lib/utils.ts, deliberately deferred
- CAS import lifecycle redesign (11-state machine) is intern-authored and merged, but hasn't had the same Decimal/no-PAN/no-raw-CAS review pass other features got


 session.md's Still-open item 7: a blocking db.commit() inside an async def can freeze that entire single process — meaning even at low real concurrency, one user doing a slow operation (a CAS import, a NAV warm-up) can stall every other user currently connected. That bug matters regardless of worker count, and fixing it is arguably more urgent than the Redis question. - One more thing directly relevant to the prefetch idea: session.md's Still-open item 7 — a blocking db.commit() inside an async def can freeze the entire single-worker event loop, already root-caused and confirmed live. Kicking off Analytics prefetch work in the background while someone's still on the Main Dashboard adds more concurrent async work sharing that same event loop. If any of it hits a slow sync DB call, prefetching could make that starvation problem worse, not just free. Not a blocker, but the design needs to account for it.

Deliberately not doing: the full AsyncSession/asyncpg rewrite (session.md's Option 3) — that stays deferred to the Postgres migration as already planned. This is the thread-offload stopgap only, same one session.md already said was safe to do now.
________________________________________________________________________________________________________________________________________________________________________


FOR EVERYTHING RELATED WITH STOCKS and EQUITY- 

Good news that changes the shape of this: I checked whether cap-wise composition needs the same hard data source as PE/PB, and it doesn't. AMFI publishes a free, official, biannual large/mid/small-cap stock classification list (mandated by SEBI circular 2017/114, at amfiindia.com/otherdata/categorisation-of-stocks) — a fixed rank-based classification (top 100 = large, 101–250 = mid, 251+ = small), no paid vendor needed.

So the four features split into two very different tiers once the holdings foundation exists:
- Equity look-through, stock overlap detection, cap-wise composition — all three need only the holdings pipeline (cap-wise additionally needs that one free AMFI list). No paid data, no buy-vs-build decision.
- Scorer v2's PE/PB valuation overlay — needs holdings plus stock-level PE/PB fundamentals, which is the genuinely hard, possibly-paid data source from the earlier feasibility research.

That's a real fork: three of the four deferred features become "basically free" the moment the foundation exists, while PE/PB has its own separate, harder dependency that shouldn't gate the other three.

Given that — do you want to commit to shipping all three of look-through/overlap/cap-wise once the foundation is built, and treat PE/PB (and the buy-vs-build call) as a separate, later decision that doesn't block them? That's what I'd recommend, but it's your call to confirm before I go further into the design.

That matches this session's role exactly to how the existing docs already work in this repo — a spec in Docs/superpowers/specs/ plus an implementation plan doc are self-contained handoff artifacts, meant to be picked up by any session/branch, not tied to the chat that wrote them. So: full architectural planning happens here now, the resulting spec + plan doc is what you take to the other session to execute, and this session stays parked on Scorer v2 until you come back and say the foundation + three features are done.

One practical thing before we go further: this foundation-and-three-features work isn't really "Scorer v2" — it's its own initiative that Scorer v2's PE/PB will later consume. I'd give it its own branch, separate from feat/scorer-v2, so the two histories don't get tangled and the other session has a clean branch to check out. Creating feat/fund-holdings-foundation off feat/enhanced-ui now — same base as scorer-v2, since it needs the same underlying infra (NAV cache, scheme universe, category machinery) — and switching to it for the planning work. Say if you'd rather name it differently.

Scope of the holdings data itself: do we ingest holdings only for funds people actually hold, or for the full category universe (every scheme, like NAV/AAUM/TER already do today)?

These have very different costs:
- Held-funds-only — realistically ~50–150 unique schemes across your whole user base, ingested lazily/on-demand as people hold them. This is all look-through, overlap detection, and cap-wise composition actually need — none of those three compare a fund's holdings against its category peers, they just describe or compare the funds a person owns.
- Full category universe (800+ schemes) — matches the existing pattern for NAV/AAUM/TER, and is what Scorer v2's PE/PB eventually needs (it ranks a fund's PE/PB as a percentile within its category, so it needs every peer's holdings too, not just held ones).

My instinct: scope the foundation to held-funds-only for now — it's the same ingestion pipeline either way (works for any scheme), just a much smaller initial dataset, and it's all three of your committed features need. Full category-universe backfill becomes PE/PB's problem specifically, tackled when you come back to that piece. Does that split make sense, or do you want the foundation to ingest the full universe from day one?

Good question, and the two are connected — let me answer the architecture one first since it resolves the loading-time one.

This has to be scheduled background reference data, never per-user/per-request — the exact same pattern already used for NAV history, AAUM, TER, category universe, and fund_scores in this codebase today. A background job ingests/refreshes it on a schedule (monthly makes sense — AMC portfolio disclosures come out monthly with roughly a 10-day lag), the result is stored in the DB, and every user's page just reads the stored result. Nobody's individual page load ever triggers ingestion, and it isn't recomputed per user. Given that, the size of the universe doesn't affect user-facing loading time at all — that variable is fully absorbed by the background job, not the request path.

So "full universe from day 1" doesn't cost you loading time. What it actually costs is different: ingestion-pipeline risk and time-to-ship. Since there's no standard format across AMCs (that's the whole reason this is hard), covering all 40+ AMCs from day one means you have to solve every AMC's format quirk before any of the three features can ship. Covering only the AMCs needed for currently-held funds first means you validate the pipeline against a much smaller set, ship look-through/overlap/cap-wise sooner, and then expand AMC coverage incrementally — using the exact same pipeline code, not a rebuild. "Build once" and "ship sooner" aren't actually in tension here: the pipeline is universe-size-agnostic by design either way, it's just a question of how many AMCs you onboard before the first ship vs. after.

My recommendation: design the pipeline to be universe-agnostic from the start (no held-funds-only logic hardcoded anywhere), but phase the actual AMC coverage — start with whatever AMCs are needed to cover your current users' held funds, ship the three features, then keep expanding coverage toward the full universe ahead of when PE/PB needs it. Zero rework either way, just a smarter ship order.

Want me to check how many distinct AMCs your actual held funds span right now, to make that phased number concrete instead of hypothetical?

______________________________________________________________________________________________________________________________________________________________________