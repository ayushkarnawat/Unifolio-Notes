2. Analytics dashboard is empty — this is expected right now, not a bug.
The analytics code itself is built (backend/app/services/analytics/, backend/app/api/analytics.py — category ranking, benchmark comparison, risk metrics, XIRR, allocation, all present). But that code depends on reference data — NAV history, AAUM, TER, benchmark index data — that only gets populated by 4 background job scripts (backend/scripts/jobs/refresh_{nav_daily,aaum_quarterly,ter_monthly,benchmark_daily}.py). Those scripts themselves are done (ADR-006 handoff marked DONE on 2026-09-03), but the piece that actually runs them on a schedule — EventBridge Scheduler + ECS Fargate task — was explicitly deferred because it needed an AWS account/ECR/ECS cluster to exist first. Those now exist (since Phase 3), so that blocker is gone, but nobody has built or run the scheduler yet, and nobody's manually triggered the jobs against staging either. So the tables the analytics dashboard reads from are just empty in this fresh RDS instance — that's the whole story, no missing feature.

3. Dashboard slow to load — likely the same root cause, not a regression.
The two perf fixes you're thinking of (dashboard-nav-perf-handoff.md, nav-fetch-connection-reuse-handoff.md) are both marked DONE in code already, reviewed and merged. But this was the first-ever CAS import against a completely cold, freshly-migrated staging RDS with zero NAV history cached. With nothing precomputed, the import path has to live-fetch NAV data from AMFI for every held scheme before it can render — exactly the case those perf fixes optimize around, not eliminate. Once the background jobs (from #2) run at least once and the NAV cache is warm, subsequent loads should be materially faster. Also possible minor contributor: this is a cold ECS Fargate task / cold RDS connection pool on first hit — that's normal for a just-deployed environment, not something to chase.

What I'd recommend for today, concretely:
1. Pull forward just the ADR-006 Terraform piece (EventBridge Scheduler + ECS Fargate one-off RunTask target) — a self-contained, well-scoped slice of Phase 7 — build and deploy it now, ahead of the rest of Phase 7.
2. Run it (or trigger the schedule once manually) to seed real NAV/AAUM/TER/benchmark data against your current staging holdings.
3. Then run the full Phase 6 smoke-test pass (§17 checklist: sign-in, CAS import, dashboard, analytics, PDF export, mid-load tab switching) — with real data this time, which exceeds the plan's original Phase 6 bar rather than undercutting it.

1. Build & deploy the ADR-006 Terraform piece (item 7 above), pulled forward — same reasoning as before, your beta users need real analytics data, not a documented empty state.
2. Run it once to seed NAV/AAUM/TER/benchmark data.
3. Run the full Phase 6 / §17 checklist above end-to-end, now with real data — this is now genuinely achievable in the 1-2 day window rather than rushed.
4. Fix whatever the checklist surfaces before beta users touch it.





Analysis: why the on-demand synchronous computation exists, and why it's still there

1. Why it was built this way originally

Git archaeology on ter.py/scorer.py/amfi_ter_client.py: the on-demand, refresh-on-read pattern (_ensure_ter_fresh triggering a live AMFI fetch, scorer.py computing category scores live per request) was built in Phase 4 (PRD-04 FR-5/FR-7/FR-10/FR-11), commits from 2026-08-xx — well before AWS existed. At that point there was no ECS, no EventBridge Scheduler, nothing to schedule a job on. The only compute environment was one long-running local FastAPI process. Lazy-refresh-on-read with an in-process backoff lock was the only option available then — a reasonable pattern for that constraint, not a mistake at the time. This wasn't "local-first" laziness, it was the only architecture available before background-job infra existed.

2. What changed, and the gap that opened up

ADR-006 (built 2026-09-03+, applied to real AWS just now) added EventBridge Scheduler → ECS Fargate RunTask for the raw reference data — NAV, benchmark, TER, AAUM. But nobody went back and touched ter.py/scorer.py/analytics.py — the endpoints still carry their own independent freshness check and, on a miss, still do the full synchronous AMFI scan and score computation live in the request, on a single-worker uvicorn process that also serves /health. Two refresh mechanisms now stack: the new scheduled jobs write the tables, but the read path was never changed to trust them and stop computing live.

3. The important finding: this was already fixed, reviewed, and never shipped

Docs/superpowers/specs/2026-09-02-analytics-precompute-architecture-design.md diagnoses exactly this failure mode almost verbatim — connection-pool exhaustion and multi-minute uncached live compute from concurrent analytics requests — and its explicit mandate was: "the fix is the full precompute/caching architecture... a stopgap is explicitly ruled out." The approved design: GET /analytics/{scope} reads only from a new precomputed analytics_sections table; the only writer is recompute_household_analytics(), which only ever runs inside a dedicated ECS Fargate RunTask, never inline — triggered by CAS import completion, a daily EventBridge backstop, and a cold-start dispatch on first read.

This was fully implemented: 9 tasks, commits 47b0bb9...9bf5603, on branch worktree-analytics-precompute-architecture (worktree at .claude/worktrees/analytics-precompute-architecture), forked from feat/enhanced-ui at 39a97ca. Went through 4 rounds of the mandatory adversarial review (3× needs-fixes catching real concurrency bugs — double-dispatch races, an orphaned in-flight claim, uncaught boto3 transport errors — then round 4: PASS, zero findings). Full backend suite green (597 passed). Handoff doc status: DONE, 2026-09-03.

It was never merged. feat/enhanced-ui — the branch actually running in staging right now — has no recompute.py, no analytics_sections model, none of it. Since the fork point, feat/enhanced-ui has moved 17 commits (entirely the AWS Terraform buildout: Phases 1–5, plus F4/F8/non-PAN work, plus ADR-006's job scripts) — none of which touch the precompute code, so a merge should be low-conflict on files. But:

- The design explicitly left EcsRunTaskDispatcher's ecs_cluster_arn/ecs_task_definition_arn as empty-string placeholders, deferring to "a separate parallel session... finalizing the real ECS/EventBridge wiring" — that session is exactly the ADR-006 Terraform work, which landed since but was never reconciled back against this branch. infra/modules/scheduler has 4 cron-scheduled reference-data jobs; it has no analytics-recompute task definition or dispatch-invocation wiring.
- The design doc itself flags that frontend/src/features/analytics/api.ts will break once the 14 old per-section routes are replaced by one GET /analytics/{scope} — noted as a deliberate, separate follow-up never done.
- It's been ~a week; worth a fresh full-suite run and a sanity check against current feat/enhanced-ui before trusting "DONE" still holds.

One explicit scope gap in the design itself: /funds/{scheme_id}/score (get_fund_score, fund-scoped rather than household-scoped) was deliberately left outside this precompute grid — it would still compute live even after this ships.

Direct answer to your question

No, synchronous on-demand computation is not still needed. It was the only viable architecture pre-AWS; now that ADR-006's scheduled jobs exist for raw data, the already-designed-and-approved next layer is precisely "cut it out and read precomputed rows only" — and that work is sitting done, reviewed, and unmerged, not missing.

What's actually left to ship it: merge the worktree branch into feat/enhanced-ui, add the analytics-recompute ECS task definition + dispatch wiring to Terraform (reconciling against the now-real ecs_cluster_arn/execution role from ADR-006), fix the frontend's 14→1 route consolidation, re-run the full suite, and decide what happens to get_fund_score. Not doing any of that yet, per your instruction — just flagging it's a known, bounded scope, not a fresh design problem.
dispatch-invocation wiring.
- The design doc itself flags that frontend/src/features/analytics/api.ts will break once the 14 old per-section routes are replaced by one GET /analytics/{scope} — noted as a deliberate, separate follow-up never done.
- It's been ~a week; worth a fresh full-suite run and a sanity check against current feat/enhanced-ui before trusting "DONE" still holds.

One explicit scope gap in the design itself: /funds/{scheme_id}/score (get_fund_score, fund-scoped rather than household-scoped) was deliberately left outside this precompute grid — it would still compute live even after this ships.

Direct answer to your question

No, synchronous on-demand computation is not still needed. It was the only viable architecture pre-AWS; now that ADR-006's scheduled jobs exist for raw data, the already-designed-and-approved next layer is precisely "cut it out and read precomputed rows only" — and that work is sitting done, reviewed, and unmerged, not missing.

What's actually left to ship it: merge the worktree branch into feat/enhanced-ui, add the analytics-recompute ECS task definition + dispatch wiring to Terraform (reconciling against the now-real ecs_cluster_arn/execution role from ADR-006), fix the frontend's 14→1 route consolidation, re-run the full suite, and decide what happens to get_fund_score. Not doing any of that yet, per your instruction — just flagging it's a known, bounded scope, not a fresh design problem.


TO FIX ANALYTICS ON CLOUD - 

Analytics (single import deleted): Not immediate — this one's async by design. Deleting the AnalyticsSection rows outright (the only real option — I checked, there's no staleness/dirty flag on that model, so "mark stale" in the handoff was really just "delete rows") makes the next GET /analytics/{scope} see zero rows, which triggers try_claim_recompute + an ECS Fargate RunTask dispatch, same as first-time analytics for a new user. The frontend will show the existing recomputing: true state (same spinner UX already built) until that task finishes — realistically low tens of seconds to a couple minutes (Fargate task launch + actual compute across up to 5 scopes × 7 sections), not instant. There's no faster path available without inlining the recompute on a request-serving replica, which the architecture doc explicitly rules out.

Will users actually experience a stuck/broken load? No. recompute_household_analytics commits per section (app/services/analytics/recompute.py:203-204 — _upsert_section then commit_off_loop, inside the per-section loop, not one final bulk write at the end). The frontend polls every 3s (useAnalyticsScope.ts:6,49-56) and renders each section the moment its row lands — it doesn't wait for all sections to finish. So a user sees sections populate progressively (Allocation and TER first, since those don't need the category-peer NAV warm-up; Category Ranking/Fund Score last, since that's the one waiting on the cold cache), with a "still computing" indicator on whatever hasn't landed yet — not a blank/frozen screen for 3 minutes.

And per-category, this is a one-time cost: once any user triggers a recompute in "Index Funds," that category's NAV is warm for every subsequent user for the freshness window (3 days, nav.py:49). With a small beta of friends/family, most category collisions across a handful of accounts will happen fast — only the very first person to touch a never-before-ranked category eats the cold-start cost. It's not "every user, every time."

What did today's fix actually do, and did I verify it live? Only one thing was fixed today: the missing analytics_sections/analytics_recompute_status tables, which were causing a hard 500 on every analytics request. That's the only thing that was broken. I verified it end-to-end via CloudWatch, not just assumed it:
- GET /analytics/{scope} went from 500 (UndefinedTable) → 200 OK
- The dispatcher logged a real RunTask dispatch (EcsRunTaskDispatcher: dispatched recompute RunTask for user 68c4298e-...)
- The ECS task itself ran and exited 0 (clean), with logs showing it actually computed category returns and scores for all 3 of your categories, not just what one you dispatched.
- Your screenshot confirms the dashboard now genuinely renders real data (allocation, TER, category ranking, fund scores, benchmark comparison).

Nothing about compute speed was touched or improved today — the 3-minute cold-start behavior existed before this fix too (it's the recompute working, just slowly on a cold cache), and today's change doesn't affect it either way.

Good catch — this is real, not "nothing fixed." Two separate things happened today, and only one of them is what I touched.

What I actually fixed: the analytics_sections table didn't exist at all, so GET /analytics/* was 500ing outright. That's done — confirmed by the 200 OK and the dashboard rendering.

What you're now seeing (the 3-minute wait) is a separate, pre-existing gap, and here's the exact mechanism — from backend/scripts/jobs/refresh_nav_daily.py:19-27:

schemes = (
    db.query(Scheme)
    .join(Folio, Folio.scheme_id == Scheme.id)
    .filter(Scheme.id.in_(db.query(distinct(Folio.scheme_id))))
    .all()
)
await warm_nav_history(db, schemes)

The daily NAV job only warms NAV history for schemes you actually hold — 19 schemes in this account (confirmed in its own log line: held_schemes=19). But category ranking doesn't compare your fund against your own holdings — it ranks your NIFTY 50 index fund against every other index fund in India to compute a percentile. That's _compute_category_returns in app/services/analytics/category_ranking.py, and for the "Other Scheme - Index Funds" category, that peer universe is 1,078 schemes. Nobody has ever fetched NAV history for those other 1,073 schemes before — no batch job's scope has ever included them — so the first time any recompute touches that category, it's a genuine cold cache: 1,073 sequential/concurrent live calls to api.mfapi.in, which is where the ~113 seconds went (fetch=37.64s commit=75.60s in the logs, per warm_nav_history's own instrumentation, added specifically because this exact slowness was already investigated once before — see the code comment dated 2026-08-20).

You can see the fix already half-exists in the same run: the other two categories in your portfolio, "Flexi Cap Fund" (130 peer schemes) and "Mid Cap Fund" (52 peer schemes), both hit 0 fetched over network — someone/something had already warmed those before. Once a category's peer universe is warm, warm_nav_history skips anything with a NAV row inside its freshness window (_fresh_scheme_ids), so re-ranking against an already-warm category is fast (bulk_nav_lookup=0.16s–0.43s). Index Funds was just the one category nobody had ever touched.

So the real fix, if you want cold-start category ranking to actually be fast: expand refresh_nav_daily.py's scope from "schemes you hold" to "every scheme in every SEBI category represented by anything you or any user holds" — a one-line change to that query (join through category instead of just holdings). That daily job would get slower on its own schedule (fetching ~1,000+ schemes instead of 19), but that cost moves off the user-facing request path entirely, onto a background cron nobody's waiting on.

That's a real backend change, not a one-liner I'd want to sneak in silently — want me to draft it now (I'd delegate the mechanical query-widening to Codex per our usual split), or file it as a task and move on to step 9 (CI/CD pipeline) as planned?

iMPOETANTLY - Pre-warm SEBI-category peer-universe NAV history, not just held schemes