CODEX FINDINGS - 


UNRESOLVED STUFF FROM THE EARLIER SCORER
I also identified the important unresolved methodology mismatches:
- The canonical PRD still specifies Morningstar-style 10%/22.5%/35%/22.5%/10% tier bands, while the implementation uses equal 20% bands.
- The PRD requires at least five eligible peers before scoring, but the implementation currently only flags a thin category and still produces a score.
- Ranking is not tie-aware; equal values can receive different ranks based on ordering.
- Consistency is used as a raw hit rate, not peer-ranked into a percentile, although some documentation calls it a “consistency percentile.”
- The internal correction plan explicitly says these differences require one approved, versioned scorer policy.

The approved methodology is not a small adjustment to the existing scorer. It is a scorer v2: the surrounding infrastructure remains useful, but the scoring engine, stored breakdown, UI explanation, and several data pipelines must change.
I reviewed all four pages of the approved methodology Unifolio_Fund_Scoring_Methodology.pdf and compared it with the current implementation.

Executive assessment
- Overall difficulty: high, but quite achievable.
- Formula-only difficulty: medium.
- Full approved methodology difficulty: high because of missing external data—not because the math is unusually difficult.
- Existing infrastructure reusable: peer-category universe, NAV history, monthly-series construction, TER/AAUM tables, benchmark cache framework, portfolio roll-up, endpoints, UI shells, and PDF export.
- Existing scoring logic: mostly replaced.
- Loading-time impact:
  - If calculated on demand like today: materially slower and potentially unacceptable on cold loads.
  - If calculated by a scheduled/background scorer and served from stored results: user-facing loading should remain similar or become faster.
The clean approach is to build this as a versioned scorer v2 alongside the current scorer, validate it, backfill it, and then switch the UI. I would not mutate the live scorer in place.

What changes mathematically
Area	Current scorer	Approved scorer
Components	3 components	11 components
Return	45%: percentile of blended 3Y/5Y CAGR	25%: recency-weighted rolling returns across 1–5Y
Consistency	25%: rate of beating the category median in rolling 12M periods	12% beats category average + 8% top-quartile frequency across 1–5Y windows
Downside risk	30%: downside-deviation percentile	7.5% max drawdown + 7.5% down-capture ratio
Risk-adjusted efficiency	Not present	10% Sortino + 10% Information Ratio
Upside participation	Not present	5% up-capture ratio
Valuation	Not present	5% relative PE/PB overlay
Cost	±0.25 post-score TER nudge	6% current cost level + 4% cost trend inside the core score
Missing data	Fund generally becomes unscored if a required component is absent	Missing component and weight are excluded; remaining weights are renormalized
Track record	Under 3 years is unscored	1–3 years gets a provisional score; under 1 year is unscored
Peer reliability	Under 5 is merely flagged today	Approximately 15 peers proposed; widen category or mark low confidence
Final calculation	Blend components, then re-rank the blend, then add TER	Direct weighted combination of component percentiles appears intended


The existing core is visible in [scorer.py (line 32)](D:/Unifolio code/backend/app/services/analytics/scorer.py:32). The current API only returns Return, Risk, Consistency, tier, and a TER adjustment in [schemas.py (line 112)](D:/Unifolio code/backend/app/services/analytics/schemas.py:112).
Data readiness
Mostly reusable from existing data
Approved component	Readiness	Work
Rolling return	Good	Replace 3Y/5Y point-return logic with rolling 1–5Y recency-weighted windows
Beats category average	Good	Extend existing category-median consistency engine
Top-quartile frequency	Good	Add per-window quartile calculation
Maximum drawdown	Good	New calculation over cached NAV history
Sortino	Good foundation	Downside deviation exists; add excess-return numerator and finalize MAR/risk-free policy


These five components can use the existing full-category NAV cache and monthly-series machinery in [risk_metrics.py (line 1)](D:/Unifolio code/backend/app/services/analytics/risk_metrics.py:1).
Partially available
Approved component	Readiness	Main issue
Down capture	Partial	Needs a valid category-appropriate benchmark history
Information ratio	Partial	Needs benchmark returns and tracking-error calculation
Up capture	Partial	Same benchmark dependency
Expense-ratio level	Mostly ready	Current TER comparison exists, but it must become a category percentile worth 6%, not a ±0.25 nudge
Expense-ratio trend	Weak	The table supports historical periods, but ingestion currently fetches only the latest published month


The benchmark framework currently supports only four Nifty indices and maps almost everything else to Nifty 500. That is inadequate for debt, hybrid, gold, international, sectoral, and potentially passive-fund capture/Information Ratio calculations. The limitation is visible in [benchmark.py (line 201)](D:/Unifolio code/backend/app/services/analytics/benchmark.py:201).
Entirely new data requirement
Approved component	Readiness	Consequence
PE/PB valuation overlay	Absent	New data source, storage, refresh policy, category aggregation, and lineage are required


There is no PE, PB, portfolio valuation, or underlying-holdings data in the present schema or integrations. This is the single largest unknown and likely the critical path.
Schema impact
The existing fund_scores table stores only:
- tier;
- TER adjustment;
- final score;
- computation timestamp.
That schema was designed for the old methodology. It cannot faithfully store:
- eleven component percentiles;
- which components were unavailable;
- effective weighting denominator;
- provisional/full/low-confidence status;
- peer count;
- methodology version;
- source-data dates;
- component-level explanation.
See [Database-Schema-Unifolio.md (line 235)](D:/Unifolio code/Docs/PRDs/Database-Schema-Unifolio.md:235).
I recommend a migration rather than squeezing scorer v2 into the old columns. A likely design is:
- a versioned score-run record containing final score, status, peer count, available weight, data date, and methodology version;
- child component records—or a carefully defined structured JSON breakdown—for the eleven metrics;
- retention of the old score rows until v2 is validated and cut over.
This conflicts with the existing “schema exact and final” rule, so the approved methodology should be treated as an explicit product-level reason to revise that previously final scorer slice.
UI impact
The existing UI repeatedly and explicitly describes “45% Return / 30% Risk / 25% Consistency”:
- [FundScoreCard.tsx (line 17)](D:/Unifolio code/frontend/src/features/analytics/FundScoreCard.tsx:17)
- [ScorerSection.tsx (line 1)](D:/Unifolio code/frontend/src/features/analytics/ScorerSection.tsx:1)
- [FundScoreDetailModal.tsx (line 1)](D:/Unifolio code/frontend/src/features/analytics/FundScoreDetailModal.tsx:1)
Required UI changes include:
- replacing three ingredient cards with seven bucket summaries and eleven expandable components;
- showing unavailable components and the effective renormalized weight;
- provisional and low-confidence badges;
- peer count and track-record coverage;
- revised cost presentation;
- updated tiers, if tiers remain;
- mobile treatment through the shared score components;
- larger print/PDF score sections;
- updates to every scorer fixture and analytics-export test.
The portfolio roll-up can remain current-value-weighted unless the approved methodology also intends to redefine it. The PDF only defines the fund score.
Loading-time assessment
If we keep on-request calculation
Loading will increase substantially.
The current scorer already:
- warms NAV histories for the complete category universe;
- calculates three category-wide components;
- caches category results for 15 minutes;
- previously suffered multi-minute cold calculations before optimization.
The approved scorer adds:
- multiple rolling horizons;
- per-window averages and quartiles;
- drawdown;
- three benchmark-relative calculations;
- valuation retrieval;
- historical TER/AAUM analysis;
- eleven percentile passes;
- missing-component normalization.
The raw arithmetic is manageable. On five years of monthly observations, calculating additional metrics is not itself scary. External fetches, historical backfills, and repeated category-wide database work are the real latency risks.
A warm calculation using only local, indexed data might be around a few multiples of the present CPU work, but the frontend payload size and rendering cost would be negligible. Cold external-data retrieval is what could return the scorer to tens of seconds or minutes.
Recommended performance architecture
Calculate fund scores as shared platform reference data, not during a user request:
1. Refresh NAV, benchmark, TER, AAUM, and valuation inputs on their respective schedules.
2. Recompute affected category scores in a background job.
3. Persist the complete versioned breakdown.
4. Let member and aggregate endpoints read stored fund scores and only calculate the inexpensive holding-value-weighted portfolio roll-up.
5. Keep an explicit stale-data indicator if a scheduled score run fails.
With that architecture, scorer v2 should not make the analytics page noticeably slower. It may actually be faster than today because the API would stop rebuilding category scores on demand.
Decisions needed before implementation
The PDF is approved at the product level, but it still needs an engineering-calculation annex. These are not objections to the methodology; they are definitions required to produce deterministic code and golden tests:
1. The overview says “ten components across six buckets,” but the table contains eleven components across seven buckets. The table and formula do sum correctly to 100%.
2. What exact rolling horizons are included: 1Y, 2Y, 3Y, 4Y, and 5Y?
3. What is the exact recency-weighting curve?
4. Are rolling observations monthly, weekly, or daily?
5. What constitutes the “category average”—median, equal-weighted mean, or AAUM-weighted mean?
6. How are PE and PB combined into one 5% percentile?
7. What exact formula grades expense-ratio trend, including the interaction with AUM growth?
8. Which benchmark applies to every SEBI category?
9. How are passive funds scored on Information Ratio and capture metrics?
10. Is the weighted 0–100 result final, or is it re-ranked again like the current scorer?
11. What tier bands replace or retain today’s five equal 20-point bands?
12. Is the minimum reliable peer set exactly 15, and what does “category widened” mean?
13. For provisional funds, which components are eligible and how is confidence displayed?
14. Is there any minimum available-weight threshold below which renormalization should not produce a score?
Recommended change order
1. Freeze the calculation annex. Resolve the fourteen definitions above and correct the component/bucket count.
2. Run data-source feasibility spikes. Validate category benchmarks, PE/PB, historical TER, and AAUM—especially valuation, the critical path.
3. Design scorer v2 persistence and versioning. Migration, component breakdown, confidence status, data dates, and cutover strategy.
4. Build a golden financial dataset. Finance-approved examples with expected raw metrics, percentiles, missing-data normalization, and final scores.
5. Build the pure NAV metric engine using TDD. Return, consistency, drawdown, and Sortino first.
6. Add benchmark-relative metrics. Down capture, Information Ratio, and up capture after benchmark policy is locked.
7. Add cost-level and cost-trend history.
8. Add valuation last. It has the largest external dependency and can initially appear unavailable under the approved gating rule if product accepts that rollout.
9. Build the scheduled/category-level precomputation path.
10. Change APIs and UI. Desktop, mobile, fund detail, portfolio roll-up, and PDF export.
11. Run numerical reconciliation and performance tests.
12. Release behind a version/feature flag, compare v1 and v2, then cut over.
Bottom line: this is a substantial scorer rebuild, but not a ground-up analytics rebuild. The difficult part is acquiring and governing the new benchmark, valuation, and historical cost data. If those inputs are solved and scoring is precomputed, the user-facing loading time does not need to increase.

FROM CLAUDE - 

I read the approved-methodology doc, scorer.py, schemas.py, benchmark.py, the fund_scores schema entry, and PRD-04's FR-5 section directly rather than taking Codex's summary at face value. Here's where that lands.

Codex's assessment is largely right — verified, not just trusted

- The 10-vs-11 component discrepancy is real, not a Codex nitpick. I read the doc myself: the overview says "ten weighted components across six buckets," but the table has 11 rows across 7 buckets (Return; Consistency split into BeatsAvg 12% + TopQuartile 8%; Downside Risk split into Drawdown 7.5% + DownCapture 7.5%; Risk-Adjusted Efficiency; Upside Participation; Valuation; Cost split into Level 6% + Trend 4%), summing to exactly 100%. The table is internally consistent; the prose summary sentence is just wrong. That's a one-line question back to your finance lead, not an engineering judgment call — don't let anyone guess at it.
- The schema conflict is real and correctly flagged. fund_scores (confirmed in both models/reference.py and Docs/PRDs/Database-Schema-Unifolio.md:235) stores exactly scheme_id, computed_at, risk_adjusted_tier, cost_adjustment, final_score — nothing else. scorer.py's own docstring even says the FR-7 breakdown "is never persisted" today, by design, for the 3-component version. Storing 11 component percentiles, per-component availability, effective weight, confidence status, peer count, methodology version isn't a tweak to that table — it needs new columns/tables. AGENTS.md line 19 does say the schema is "exact and final," so per CLAUDE.md's own working-style rule ("when a PRD, ADR, or the schema seems to conflict with what you're about to build, stop and say so") — this is precisely that situation, correctly identified. Good catch on Codex's part.
- Current scorer confirmed: 45/30/25 weights, TER ±0.25 nudge with a 0.05pp dead zone, blend-then-rerank-then-add-TER, tier via equal 80/60/40/20 bands, clamp 0–100 — matches your stated understanding and scorer.py:44-77 exactly.
- Benchmark coverage confirmed thin: benchmark.py:201-221 — literally only 4 indices exist, everything that isn't Large/Mid/Large&Mid falls back to Nifty 500. Debt, hybrid, gold, international, sectoral all get a broad-equity-index proxy today. Down-capture/up-capture/Information Ratio need a real category-appropriate benchmark, so this is a genuine gap, not overstated.
- Precompute-and-store architecture recommendation isn't Codex inventing new design — it's actually already the documented intent. Database-Schema-Unifolio.md:235-240 explicitly says portfolio-level scores are "an AUM-weighted roll-up computed on read from a member's holdings plus this [fund_scores] table, not separately stored." The current on-demand-with-15-min-cache scorer is already a shortcut relative to spec; scorer v2 moving to scheduled precompute is bringing the system closer to its own documented design, not a new architectural risk.

Where I'd push back or add nuance

1. Not all 14 "decisions needed" are equally blocking. A few (exact rolling horizons, monthly/weekly/daily sampling, category-average definition, PE/PB combination formula, benchmark-per-category mapping, provisional-fund component eligibility) genuinely need your finance lead's sign-off — don't let engineering guess financial policy. But others are silent in the doc precisely because the doc doesn't intend to change them — e.g. tier bands and "is the result re-ranked again": the approved doc never mentions tiers at all, which most plausibly means "keep whatever tier presentation exists" rather than "this is undefined." I'd bucket the 14 into true policy blockers (~6-7) vs. defaults we propose and get a one-line yes/no on (~6-7), so this doesn't stall on a 14-item RFC before any code gets written.
2. PRD-04 itself is already stale against the live scorer, independent of v2: FR-5a specifies unequal tier bands (10/22.5/35/22.5/10%), but scorer.py implements equal 20-point bands. That's pre-existing drift Codex didn't flag. Worth knowing going in — PRD-04 needs a real rewrite for v2, not a patch, since even its v1 description doesn't match v1's code today.
3. Codex's phased order is sound, and I'd keep it, with one change: move "freeze the calculation annex" and "data-source feasibility spike for PE/PB" to run in parallel, not sequentially — the PE/PB source question is the actual critical path per Codex's own analysis, so don't wait on all 14 formula questions before starting to find out if PE/PB data is even obtainable at reasonable cost/latency. If it isn't, that reshapes the annex questions too (e.g. whether valuation ships gated-unavailable at launch).

How I'd set this up

Agreed on a dedicated branch, not a worktree, since you want to test it interactively yourself rather than have it run headless. Base it off feat/enhanced-ui, not main — main is 410 commits behind and doesn't have the peer-universe/NAV-cache/benchmark/TER infrastructure v2 depends on. I'll create feat/scorer-v2 off feat/enhanced-ui now.

For the build itself, this still fits the model-orchestration skill's Claude/Codex split and handoff-doc/adversarial-review discipline used for the last two big features (just anchored on a plain branch instead of a worktree) — I'd invoke that when we're ready to actually start dispatching tasks, not before the annex is resolved.

PE/PB feasibility research and the annex are both done — here's the breakdown, then the two docs.

PE/PB feasibility — findings

No official free API exists for fund-level PE/PB in India, confirmed via search. There's no existing integration for this in the codebase either (checked: only NAV, AAUM, TER, and NSE index clients exist today — nothing touching holdings or stock fundamentals). Three real paths:

A. Build in-house (matches this project's existing pattern of computing everything from primitives, not trusting a third-party black box): SEBI mandates portfolio disclosure (half-yearly by regulation, monthly in practice — most AMCs publish monthly disclosures voluntarily), but there's no standard API or shared format — each AMC publishes its own Excel/CSV on its own site. You'd need: (1) a per-AMC ingestion pipeline for holdings+weights — no standard format is the hard part here, harder than the PE/PB numbers themselves, (2) a stock-level fundamentals feed (viable paid options exist here — e.g. FinEdge's API, or NSE/BSE data actors — nowhere near Bloomberg/Refinitiv's ~$24k/seat tier), (3) fund-level PE/PB computed as a weighted harmonic mean across holdings — this is Value Research's own published formula, not a guess, so it's a real, citable methodology. This is genuinely the largest new engineering surface in all of scorer v2, exactly as Codex flagged — but "AMC disclosure ingestion" is the harder sub-problem, not "getting a PE/PB number."

B. Buy it — Morningstar Direct / ICRA Analytics / CRISIL license fund-level PE/PB directly. Zero engineering lift, but this is a procurement/cost decision, not something I can resolve — needs your (or your finance lead's) sign-off on budget.

C. Scrape an aggregator (Value Research, Moneycontrol) — fragile, ToS risk, not something I'd recommend for a production financial product without legal review.

I'd default to recommending A, consistent with how the rest of the scorer is built, but B vs. A is a real business decision (cost vs. engineering time) that belongs in the annex, not something I should silently decide.

Sources: SEBI Portfolio Disclosures (https://www.sebi.gov.in/sebi_data/commondocs/cirmfd142002_h.html) · Value Research — Key Ratios methodology (https://www.valueresearchonline.com/key-ratios/) · Morningstar India tools (https://www.morningstar.in/tools/mutual-fund-detailed-portfolio.aspx) · FinEdge Financial Data API (https://www.finedgeapi.com/)


Verified your framing against the actual PRD text, not just Codex's summary — it holds up exactly as described. Docs/PRDs/PRD-04-MF-Analytics-Dashboard.md explicitly says cap-wise composition/overlap are deferred because they "require the fund's underlying portfolio holdings... the same gap already flagged as a Future Consideration in PRD-03 for equity look-through," and recommends revisiting "once the portfolio-holdings data question... is resolved, ideally as a single combined data-sourcing effort rather than solving it twice." PRD-03-Main-Dashboard.md independently points at the identical gap for equity look-through. The 5th item you listed (equity-specific analytics generally) is categorically different, though — PRD-04's Non-Goals calls that a permanent scope exclusion ("MF-only per the overall MVP scope"), not a data-gated deferral, so building holdings data doesn't unlock that one.

This is an architectural decision, not a bounded scorer tweak — using the brainstorming skill for it rather than jumping straight to a design.

Before refining the idea further: what you're describing is actually two layers, not one build. Layer 1 is a single shared foundation — ingest and store fund holdings data, reusable regardless of who consumes it. Layer 2 is up to four independent consumer features sitting on top of it: Scorer v2's PE/PB overlay, cap-wise composition, stock overlap detection, and equity look-through — each of which was a separate, deliberately deferred PRD decision (PRD-03/PRD-04), not just a technical afterthought.

I'd decompose this as: design and build Layer 1 first (it's also literally Scorer v2's Path A from the feasibility doc, so it's not extra work relative to what PE/PB needed anyway), and treat each Layer-2 feature as its own separate scope decision afterward — not assume all four ship together just because the data now exists.

One question before I go further: for right now, do you want to (a) build only the reusable holdings-data foundation — enough for Scorer v2's PE/PB to work, with cap-wise composition/overlap/look-through left as "now easy, decide later," or (b) commit now to also shipping one or more of those three features alongside the foundation?








Let me know if you want anything trimmed, added, or reworded before sending — and once you've heard back (or decided this vendor question is settled), the next open item is resuming the architectural brainstorm for the fund-holdings foundation + 3 deferred features on feat/fund-holdings-foundation.