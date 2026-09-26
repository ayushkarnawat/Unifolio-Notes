Before diving into clarifying questions, this bundles two genuinely independent things — worth splitting before we design either one.

What I found by reading the actual code first:

Tab switching (MainDashboardFlow.tsx:189-202) is a hard conditional render: activeTab === "dashboard" ? <DashboardView/> : <AnalyticsView/>. Switching tabs fully unmounts one and mounts the other from scratch — it's not tab-panels-both-in-DOM. Both DashboardView and AnalyticsView's fetch effects already guard with isMounted/AbortController cleanup per section, so a bare "state update on unmounted component" crash isn't obvious from a code read alone. That means the mid-load tab-switch error needs live reproduction to root-cause, not a guess from source.

On Redis — checked the codebase and the ADRs: there's no Redis anywhere today (not a dependency, not in any Accepted decision). Two direct precedents already exist against adding it at this stage:
- ADR-006 explicitly rejected Celery/Redis as a job queue: "adds an entire additional piece of infrastructure... worth reconsidering only if job volume/complexity grows well past what four scheduled jobs represent today."
- A past dashboard-perf fix explicitly rejected a Redis-backed cache as "gold-plating for this MVP phase."
- Every existing cache (TER, category ranking, Scorer, compute_holdings) is deliberately process-local in-memory, with a code comment already in place: "move to Redis/similar if/when this backend ever runs multiple workers." That's the team's own documented trigger condition, and it hasn't been hit yet — still one ECS task/one worker.

One more thing directly relevant to the prefetch idea: session.md's Still-open item 7 — a blocking db.commit() inside an async def can freeze the entire single-worker event loop, already root-caused and confirmed live. Kicking off Analytics prefetch work in the background while someone's still on the Main Dashboard adds more concurrent async work sharing that same event loop. If any of it hits a slow sync DB call, prefetching could make that starvation problem worse, not just free. Not a blocker, but the design needs to account for it.

Proposed split:
1. Track A (bug) — mid-load tab-switch error. Goes through systematic-debugging with live reproduction, on its own, independent of the rest.
2. Track B (architecture) — prefetch-on-load + aggregate/per-member precompute, with the Redis-vs-stay-in-memory question folded in as one of the design's approach options (leaning toward "not yet," per the precedent above, unless you want to push back on that).

Want to do it in that order — Track A first since it's a live bug, then Track B as a proper design? Or reverse?

Good question — let me separate what's an actual documented decision from what's just an untested assumption, because they're not the same thing here.

What "multiple workers" literally means

A "worker" is a separate OS process running its own full copy of the Python app — its own memory, its own event loop. Right now, checked the actual server startup code: no --workers flag anywhere, so it defaults to one process. That's true on your laptop and in the current ADR-005 production target (nothing in any ADR or the TDD commits to a specific ECS task/replica count — I checked). One process = one shared memory space = a plain Python dict cache works, because every request, from every user, is being served by the same process that owns that dict.

Why that breaks the moment there's more than one

If you ever run 2+ processes (either multiple Uvicorn workers on one machine, or multiple ECS Fargate task replicas behind a load balancer for redundancy), each process gets its own separate copy of that dict. They don't talk to each other. Concretely:
- User A's request lands on Process 1 → warms Process 1's TER cache.
- User B's request (same minute) lands on Process 2 → Process 2's cache is cold, refetches from AMFI independently, wastes the work Process 1 already did.
- Worse: two users can see genuinely different app state at the same moment depending on which process they happened to hit — which is structurally the same class of bug as the "TER data fine on my laptop, missing on my colleague's" incident from a couple days ago (different machines there, but same root shape: state that isn't shared).

Was Redis actually "rejected" for this reason, or is that a gap?

Worth being precise here, because those two precedents I cited earlier don't actually cover this question:
- ADR-006 rejected Redis specifically as a task queue (a message broker for background jobs) — a different technology role. Its reasoning was about queue/broker complexity for 4 scheduled jobs, not about whether request-serving processes need a shared cache.
- The dashboard-perf fix rejected Redis for one narrow, local-dev cache, explicitly scoped: "acceptable because it becomes moot once [a specific other fix] exists... does NOT need to be multi-instance safe." That was a call about a single temporary cache, not a decision about the app's whole caching architecture in production.

So: no ADR actually decided "the app will only ever run one worker in production." That's not a considered decision — it's an assumption implicitly baked in because every cache so far was built for the environment that existed at the time (single dev process), with a code comment ("move to Redis/similar if/when this backend ever runs multiple workers") left as a marker, not a scale target anyone actually set. That's the honest answer to "have we made this mistake" — it's not that anyone decided wrong, it's that the decision was never made at all. It's a real gap in the docs, not over-engineering-avoidance gone too far.

Does 200–400 MAU actually force multiple workers?

Not directly — MAU isn't concurrency. If those users check their portfolio a few times a week at random times, actual simultaneous load could be low, and a single async process can serve many low-frequency users fine (that's normal for single-threaded async servers). The bigger, more urgent problem is the one already logged as session.md's Still-open item 7: a blocking db.commit() inside an async def can freeze that entire single process — meaning even at low real concurrency, one user doing a slow operation (a CAS import, a NAV warm-up) can stall every other user currently connected. That bug matters regardless of worker count, and fixing it is arguably more urgent than the Redis question.

But there's a separate reason you'll likely want ≥2 workers/replicas anyway, independent of load: basic availability. One process is a single point of failure — if that one ECS task crashes or is mid-redeploy, the app is down for everyone until it restarts. Most production setups run ≥2 replicas just for that reason, which immediately reintroduces the shared-cache problem regardless of whether 200 MAU actually needs the extra capacity.

Bottom line: this is worth turning into an explicit decision rather than staying an implicit assumption — specifically, deciding a target worker/replica count for launch (I'd guess ≥2 is likely, for availability alone), and if so, which of the existing in-memory caches need to move to something shared (Redis, or reusing Postgres as a cache table — both legitimate, not yet compared). I'd fold that into Track B's design rather than deciding it right now. Want me to add it as an explicit open question there, or do you want to settle the worker-count question first before we design anything?


The plan sounds right — doing this before Track A and B makes sense, since Track B's whole premise (prefetch Analytics while someone's on the Main Dashboard) means deliberately adding more concurrent async work onto the same event loop that's already known to freeze. Building that on top of an unfixed freeze bug would be building on sand.

Before proposing a fix, I traced the actual exposure rather than trusting session.md's list at face value — found a real correction:

Scope correction from tracing the call chains:
- Session.md named 3 "known-heavy" sites for a targeted fix: nav.py's warm_nav_history, amfi_ter_client.py's refresh_ter_data, and "CAS import." I checked each route handler's actual signature:
  - nav.py's warm_nav_history — genuinely async def, genuinely exposed. Confirmed.
  - amfi_ter_client.py's refresh_ter_data — genuinely async def, genuinely exposed. Confirmed.
  - CAS import's confirm_import_route is actually a plain def, not async def — FastAPI/Starlette auto-runs sync route handlers in a threadpool, off the main event loop, automatically. Its slow commit was never actually part of this bug. Session.md's list was wrong here.
- Meanwhile, the real exposure is broader than those 3 sites: every route in app/api/analytics.py is async def — TER, Scorer, NSE benchmark index, category ranking all reach a db.commit() somewhere in their call chain, and none of those were on session.md's list. app/api/auth.py, by contrast, is entirely sync def routes already — already safe by accident, a convention the analytics module doesn't follow.

So the real fix isn't "3 known files" — it's "every async def route whose call chain reaches a blocking commit," and that set is wider than documented, concentrated in analytics.py plus nav.py.

Proposed fix (Bounded — the flow already exists, I'm not restructuring anything):
1. One shared helper, defined once (e.g. in app/db/session.py next to get_db): async def commit_off_loop(db: Session) -> None: await asyncio.to_thread(db.commit).
2. A full call-graph audit (finishing what I started above) to enumerate every db.commit() actually reachable from an async def route — not all ~30 commit sites in the codebase, just the ones proven reachable from async handlers.
3. Replace db.commit() with await commit_off_loop(db) at each of those sites only. Sync-routed sites (auth, CAS import, the sync half of dashboard.py) stay untouched — they're not broken.
4. One regression test: simulate a slow commit (monkeypatched sleep) and assert a concurrently-running request isn't blocked for its duration — the "one runnable check" this kind of concurrency fix needs.

Deliberately not doing: the full AsyncSession/asyncpg rewrite (session.md's Option 3) — that stays deferred to the Postgres migration as already planned. This is the thread-offload stopgap only, same one session.md already said was safe to do now.

Good question to ask before touching anything — let me check two things that determine the real answer: the current SQLite engine/pool config, and whether any background task shares a request-scoped Session across threads (a real correctness precondition for this fix, not just a performance question).

Two things confirmed from the engine config that matter for the answer:

- connect_args = {"check_same_thread": False} — the engine already permits a Session's connection to be used from a different thread than the one that created it. asyncio.to_thread(db.commit) doesn't fight this; it's already how the app is set up to allow Starlette's own sync-route threadpool to work.
- No PRAGMA journal_mode=WAL anywhere — SQLite is in default rollback-journal mode, which takes a whole-database lock during a write/commit (blocks other writers and readers until it's done). That matters below.
- The one BackgroundTasks.add_task(...) in the codebase (imports.py:101) passes a plain household_member_id, not the request's db Session — so there's no existing case of a Session being touched from two threads at once. Good, no hidden correctness landmine to fix first.

Now, directly answering: no, this fix doesn't cost you anything at load/scale/migration time — it's close to strictly positive, with one thing to watch, not fix.

1. Does it slow down the request that's committing, or others?
- The committing request itself: negligible. Thread-dispatch overhead is microseconds; the commit itself is unchanged (still same DB call, just off the event loop).
- Other concurrent requests: this is the entire point — they stop being frozen. Net win.
- Because SQLite isn't in WAL mode, two commits happening "concurrently" in two threads still get serialized by SQLite's own file lock — one thread just waits at the DB layer instead of freezing the whole app's event loop. That's the correct, expected behavior, not a new bottleneck: writes were always going to serialize on SQLite; the difference is that reads and every other in-flight request no longer serialize behind them too.

2. Scalability watch item (not a blocker): asyncio.to_thread uses Python's shared default thread-pool executor, which has a bounded size. If many slow commits pile up at once you could exhaust that pool and queue on a thread instead of the event loop — strictly better than today (only the slow-commit requests queue, not literally every user), but worth knowing the ceiling exists. Not worth sizing/tuning now at dev-only load; flag with a ponytail:-style comment, revisit if it's ever observed.

3. AWS/Postgres migration — no conflict, arguably more valuable there, not less:
- A Session holds one connection for its whole lifetime once a transaction starts. Offloading db.commit() to a thread doesn't check out an extra connection from the pool — same connection, just committed from a worker thread. So this doesn't add connection-pool pressure once you're on Postgres/RDS.
- Postgres has real MVCC — readers never block writers and vice versa — so this pattern is safer there than on SQLite's whole-DB lock, not riskier.
- If the app ever moves to multiple Uvicorn workers/ECS replicas, asyncio.to_thread's pool is per-process — nothing to coordinate across workers. Doesn't block or complicate that later decision.
- session.md's own note is that Postgres commits are expected to be single-digit ms, so this stopgap becomes lower-urgency (less often triggered) but not harmful to leave in — it's cheap insurance against an occasional slow commit under real production load (lock contention, a spike), not something you'd rip out at cutover.

So: keep it as a permanent small fix, not a throwaway hack you'll owe a follow-up on. It stays DB-engine-agnostic and composes cleanly with both the Postgres migration and any future multi-worker move.

Given that, want me to go ahead and finish the full call-graph audit (the remaining unaudited files: scheme_universe.py, auth/session.py, auth/otp.py, auth/identity.py, arn_lookup.py, import_/cams_portal.py, import_/coverage_gap.py, import_/lifecycle_service.py) and come back with the exact file/function list before touching any code?

The grep output is getting corrupted by a compression layer (stripping tokens like ->, async, def). Switching to reading each file directly instead.

  Read 8 files, ran 5 shell commands

Full audit is done. Here's what's confirmed and the flag you asked for.

Thread-pool-exhaustion flag — I'll put this directly in the code as a ponytail:-style comment on the commit_off_loop helper itself (not just in this chat), so it's visible to anyone reading the fix later, e.g.:

async def commit_off_loop(db: Session) -> None:
    # ponytail: shares asyncio's default thread-pool executor (bounded size).
    # Many slow commits at once queue on a thread instead of the event loop —
    # strictly better than today (only those requests wait, not every user),
    # but the pool has a ceiling. No sizing/tuning now at current load;
    # revisit with a dedicated executor if this is ever observed to matter.
    await asyncio.to_thread(db.commit)

Exact fix list — every db.commit() genuinely reachable from an async def route, confirmed by tracing each call chain to its route decorator:

┌─────┬─────────────────────────────────────────────────────────────────┬────────────┬────────────────────────────────────────────────────────────────┐
│  #  │                         File : function                         │  Commit    │                          Reached via                           │
│     │                                                                 │  line(s)   │                                                                │
├─────┼─────────────────────────────────────────────────────────────────┼────────────┼────────────────────────────────────────────────────────────────┤
│ 1   │ app/services/dashboard/nav.py : _upsert_nav_history,            │ 121, 222   │ async NAV/dashboard routes + _prefetch_member_nav_history      │
│     │ warm_nav_history                                                │            │ background task                                                │
├─────┼─────────────────────────────────────────────────────────────────┼────────────┼────────────────────────────────────────────────────────────────┤
│ 2   │ app/services/analytics/amfi_ter_client.py : refresh_ter_data    │ 332        │ async TER routes (analytics.py)                                │
├─────┼─────────────────────────────────────────────────────────────────┼────────────┼────────────────────────────────────────────────────────────────┤
│ 3   │ app/services/analytics/scorer.py : _finish_fund_score           │ 271        │ async score routes (analytics.py)                              │
├─────┼─────────────────────────────────────────────────────────────────┼────────────┼────────────────────────────────────────────────────────────────┤
│ 4   │ app/services/analytics/nse_indices_client.py :                  │ 91         │ async benchmark routes (analytics.py)                          │
│     │ _upsert_index_history                                           │            │                                                                │
├─────┼─────────────────────────────────────────────────────────────────┼────────────┼────────────────────────────────────────────────────────────────┤
│ 5   │ app/services/dashboard/snapshots.py                             │ 124        │ async get_member_snapshots / aggregate-snapshots routes        │
├─────┼─────────────────────────────────────────────────────────────────┼────────────┼────────────────────────────────────────────────────────────────┤
│ 6   │ app/services/analytics/scheme_universe.py :                     │ 174        │ category_ranking.py + scorer.py → async analytics.py routes    │
│     │ SchemeUniverseClient.get_category_universe                      │            │                                                                │
├─────┼─────────────────────────────────────────────────────────────────┼────────────┼────────────────────────────────────────────────────────────────┤
│     │                                                                 │            │ distributor_comparison.py → async                              │
│ 7   │ app/services/dashboard/arn_lookup.py : resolve_arn              │ 101        │ get_member_distributor_comparison / aggregate distributor      │
│     │                                                                 │            │ routes                                                         │
├─────┼─────────────────────────────────────────────────────────────────┼────────────┼────────────────────────────────────────────────────────────────┤
│ 8   │ app/services/import_/lifecycle_service.py : create_cas_import   │ 205, 227   │ async upload_cas_import route (cas_imports.py)                 │
│     │ only                                                            │            │                                                                │
└─────┴─────────────────────────────────────────────────────────────────┴────────────┴────────────────────────────────────────────────────────────────┘

Confirmed safe, left untouched (sync-routed, Starlette auto-threads the whole handler): app/api/auth.py and everything it calls (session.py, otp.py, identity.py, google_oauth.py); import_/service.py's confirm_import; import_/cams_portal.py (both functions); import_/coverage_gap.py's create_opening_balance; lifecycle_service.py's retry_cas_import_password (a sibling of #8, but called only from the sync retry_password route — do not touch this one, only create_cas_import); dashboard/household_members.py's create_member. amfi_aaum_client.py stays as-is too — async def but no live route/job calls it, so it's dead code, not an exposure.

That's 8 files, one shared helper, 9 call sites total (nav.py has 2). Ready to write the concurrency regression test and make these edits — go ahead?

All 6 call sites in the test file are updated. Now let's check _upsert_index_history and _upsert_nav_history for other test callers, and check for get_snapshots, resolve_arn, get_category_universe, refresh_ter_data test callers too, since those were already async but let's confirm tests don't call them synchronously in a way that would newly break (they were already async, so no new break there — only the newly-converted-to-async functions matter).

Root cause found: several test files define their own local _session() helper with create_engine("sqlite:///:memory:") and no check_same_thread=False/StaticPool — safe when everything ran on one thread, but breaks now that commits run in a worker thread. Let me find every instance.

575 passed, 3 skipped, 0 failed, no regressions. The event-loop-freeze fix (Still-open item 7) is now fully implemented and verified:

- 8 production files + cas_imports.py caller updated to route db.commit() through the shared commit_off_loop helper (app/db/session.py), with the thread-pool-exhaustion ceiling flagged via a ponytail: comment.
- 9 test files' unsafe in-memory SQLite _session() helpers fixed to add check_same_thread=False + StaticPool, resolving all 40 failures the change exposed.
- The one call site that broke because _upsert_nav_history became async def (a direct ThreadPoolExecutor cross-session race test) fixed to run each thread's coroutine via asyncio.run.
- Added the promised concurrency regression test (tests/test_db_session.py::test_commit_off_loop_does_not_block_event_loop) — proves a slow db.commit() no longer starves other coroutines on the same loop.

Nothing has been git-committed. Let me know if you'd like me to commit this, or move on to Track A (mid-load tab-switch bug).

Screenshots s1–s5 all look correct — proper loading skeletons, no visual corruption, no error states. So the hang isn't a "stuck rendering wrong data" bug — it's a genuine freeze that hit exactly when clicking "Family Combined" while a per-member fetch was in flight. Let me check what the backend was doing during that window.

Found it — dozens of Exception in ASGI application crashes in the backend log. Let me see the actual traceback content.

  Read 1 file

This is the root cause: sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00 — exactly 30s, matching the screenshot timeout. Let me confirm the mechanism: each Analytics view fires 7 concurrent requests, each doing expensive uncached warm_nav_history work that holds a DB connection for 30+ seconds, and rapid switching stacks up duplicate un-cancelled requests until the pool (15 connections) is exhausted.

  Searched for 5 patterns, read 1 file

Root cause found. Here's the evidence chain:

Symptom → Backend error → Mechanism

The Page.screenshot hang wasn't a browser freeze — it was the frontend UI stuck because analytics requests were failing/queuing. The backend log shows dozens of repeated:
sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00
That's exactly 30s — matching the screenshot timeout.

Why the pool exhausts on mid-load view switching:

1. Each Analytics view (AnalyticsView.tsx) fires 7 concurrent GET requests per load: allocation, ter, ter/direct-regular, category-ranking, score, benchmark, benchmark/funds.
2. Several of these (category-ranking, score, benchmark) call warm_nav_history, which — on a cache miss — does a full network fetch + DB commit for the entire SEBI-category peer universe (up to 1150 schemes, taking 30–120+ seconds per the log).
3. The frontend does use AbortController on view switch (AnalyticsView.tsx:116, DashboardView.tsx), but nothing in the backend checks request.is_disconnected() (confirmed: zero hits for that anywhere in app/). So an aborted client request doesn't stop the server-side work — the handler runs to completion regardless, holding its DB session/connection the whole time.
4. Every rapid tab/view switch fires a fresh batch of 7 requests on top of the still-running, now-abandoned previous batch. With create_engine(settings.database_url, connect_args=connect_args) using SQLAlchemy's default pool (5 base + 10 overflow = 15 connections), a handful of switches during a slow load is enough to exhaust the pool.
5. Once exhausted, any request — including the one for the view the user is now actually looking at — queues for the DB connection, times out at 30s, and surfaces as a 500 to the frontend. That's the "error happens" the user reported.

This isn't really a separate bug from Track B — it's the same root problem (analytics is expensively recomputed from scratch, uncached, per request) manifesting as a crash under concurrent/repeated load instead of just "slow." A connection-pool-size bump or an is_disconnected() guard would mask this specific repro but wouldn't fix the underlying cause; Track B's caching/precompute work is the actual fix.

Given that, I'd suggest folding Track A into Track B rather than doing a standalone patch: the real fix is caching/precomputing analytics results (so repeated/concurrent requests hit a cache instead of re-running multi-minute work) plus a cheap safety net (checking is_disconnected() in the slow paths, and/or raising pool size as a stopgap). Want me to proceed straight into superpowers:brainstorming for that combined architecture, or do you want a minimal stopgap fix landed first (pool size + disconnect check) before we tackle the real caching design?

This is an architectural task — it restructures how the analytics/dashboard data layer works and changes the interface between frontend polling and backend computation, not a bounded fix to one existing flow. I'll follow the full brainstorming process: explore context, ask clarifying questions, propose approaches, write a spec.

Let me check the relevant docs first.

  Ran 6 shell commands

Before asking questions — I found something worth flagging per the CLAUDE.md instruction to stop when the docs conflict with what I'm about to build: AGENTS.md's non-negotiables explicitly lock the stack to "React + Vite, FastAPI, AWS RDS PostgreSQL, scoped S3, ECS Express Mode, EventBridge Scheduler" and says "the stack is decided, not up for debate mid-build... if a real blocker makes one of these wrong, stop and flag it explicitly." Redis is not on that list. Let me check whether ECS Express Mode's scaling plan actually implies multi-instance (which is the real reason the Redis question exists) before we get to that question.

  Read 1 file, ran 4 shell commands

I found the resolution to the "Redis vs. in-memory" open question, and it surfaces a real conflict worth flagging before we go further.

The conflict: ADR-005 (Deployment Architecture) confirms the backend runs on ECS Express Mode with "automatic scaling provisioning" — meaning production will plausibly run multiple Fargate task replicas, each a separate process. In-process caching won't be shared across them, so the "single-worker-today" framing undersells it — this isn't a someday concern, it's baked into the chosen deployment target. But AGENTS.md's non-negotiables lock the stack to "FastAPI, AWS RDS PostgreSQL, scoped S3, ECS Express Mode, EventBridge Scheduler" — Redis isn't on that list, and it says the stack isn't up for debate mid-build without flagging it.

My read: we don't need Redis to solve this. RDS Postgres is already the shared, cross-instance-visible store every Fargate task can see — precomputed analytics results can live in a Postgres table instead of a Redis cache, refreshed via the EventBridge-scheduled background job mechanism ADR-006 already decided for the four periodic reference-data jobs (AMFI TER, AMFI AAUM, NSE Indices). That reuses infra that's already approved rather than adding a new moving part.

Does that resolve the open question for you — design around Postgres-as-the-shared-cache and skip Redis entirely — or is there a reason (e.g., sub-second read latency Postgres can't hit) you want Redis on the table as a real option despite the stack lock?