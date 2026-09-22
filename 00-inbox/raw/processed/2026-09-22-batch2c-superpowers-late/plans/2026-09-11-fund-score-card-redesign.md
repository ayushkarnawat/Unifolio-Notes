# Fund Score Card Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the technical, percentile-heavy Fund Score card with a plain-English card (score/10, why-sentence, Strengths/Watch-outs drivers, "what this means for you", expandable evidence/methodology) and fix the tier-scale direction everywhere it's displayed.

**Architecture:** Backend threads raw evidence numbers (already computed in-memory, currently discarded) onto `FundScoreRow`. Frontend gets one new pure-logic module (`fundScoreVerdicts.ts`) for the deterministic bucket/verdict/sentence rules, consumed by a rebuilt `FundScoreCard.tsx`. `ScorerSection.tsx` gets a display-only tier-direction fix, nothing else.

**Tech Stack:** FastAPI + Pydantic + SQLAlchemy (backend), React + TypeScript + Vitest/Testing Library (frontend).

**Spec:** `Docs/superpowers/specs/2026-09-11-fund-score-card-redesign-design.md`

## Global Constraints

- Tier reversal is **display-only** — `displayTier = 6 - risk_adjusted_tier`. Never change `_tier_from_percentile`, the persisted `FundScore.risk_adjusted_tier` column, or `risk_adjusted_tier` on `FundScoreRow`.
- No generic multi-page `ScoreCard` component — `FundScoreCard.tsx` stays Fund-Score-specific (spec §3).
- No bottom CTA — the card ends with the "Transparent Methodology Commitment" box (spec §2, §5.7).
- `ScorerSection.tsx`'s "Portfolio Weighted Score" hero stat and its per-fund percentile breakdown rows stay `/100` and unchanged — only the `T{tier}` avatar and `Tier {tier}` badge get the display-only flip.
- All new backend `FundScoreRow` fields are additive/optional — existing cached precompute rows stay valid until the (separately scheduled, out-of-scope-here) manual recompute re-run.

---

## Task 1: `compute_consistency_hit_rate` returns a raw (hits, total) pair

**Files:**
- Modify: `backend/app/services/analytics/risk_metrics.py:224-241`
- Test: `backend/tests/services/analytics/test_risk_metrics.py:262-273`

**Interfaces:**
- Produces: `compute_consistency_hit_rate(scheme_rolling: list[Decimal | None], medians: list[Decimal | None]) -> tuple[int, int] | None` — was `Decimal | None` (a percentage). Task 3 converts this to a percentage itself and also uses the raw pair for evidence fields.

- [ ] **Step 1: Update the two existing tests to expect the new return shape**

Replace both tests in `backend/tests/services/analytics/test_risk_metrics.py`:

```python
def test_compute_consistency_hit_rate_counts_beats_at_or_above_median():
    scheme_rolling = [Decimal("0.10"), Decimal("0.05"), Decimal("0.30"), None]
    medians = [Decimal("0.08"), Decimal("0.08"), Decimal("0.20"), Decimal("0.10")]
    # index0: 0.10 >= 0.08 -> hit. index1: 0.05 >= 0.08 -> miss.
    # index2: 0.30 >= 0.20 -> hit. index3: scheme value None -> skipped.
    result = compute_consistency_hit_rate(scheme_rolling, medians)
    assert result == (2, 3)


def test_compute_consistency_hit_rate_none_when_no_comparable_windows():
    assert compute_consistency_hit_rate([None, None], [Decimal("0.1"), None]) is None
```

- [ ] **Step 2: Run the tests, confirm they fail against the current implementation**

Run: `cd backend && python -m pytest tests/services/analytics/test_risk_metrics.py -k consistency_hit_rate -v`
Expected: FAIL — `assert Decimal('66.66...') == (2, 3)`

- [ ] **Step 3: Change the implementation**

Replace `compute_consistency_hit_rate` in `backend/app/services/analytics/risk_metrics.py`:

```python
def compute_consistency_hit_rate(
    scheme_rolling: list[Decimal | None], medians: list[Decimal | None]
) -> tuple[int, int] | None:
    """(hits, total) across comparable rolling 12-month windows -- a hit is
    a window where the scheme's return was at or above its category's
    median for that same window. `None` if there are no comparable windows
    (e.g. a fund too new to overlap the category's shared history). Kept as
    a raw pair, not a percentage, so callers can derive both the
    `consistency_hit_rate` percentage and the "beat its category median in
    X of Y periods" evidence text from a single computation."""
    hits = 0
    total = 0
    for value, median in zip(scheme_rolling, medians):
        if value is None or median is None:
            continue
        total += 1
        if value >= median:
            hits += 1
    if total == 0:
        return None
    return hits, total
```

- [ ] **Step 4: Run the tests again, confirm they pass**

Run: `cd backend && python -m pytest tests/services/analytics/test_risk_metrics.py -v`
Expected: PASS (all tests in the file, not just the two edited — confirms nothing else in this file depended on the old shape)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/analytics/risk_metrics.py backend/tests/services/analytics/test_risk_metrics.py
git commit -m "refactor(analytics): compute_consistency_hit_rate returns raw (hits, total)"
```

---

## Task 2: Add raw-evidence fields to `FundScoreRow`

**Files:**
- Modify: `backend/app/services/analytics/schemas.py:112-127`

**Interfaces:**
- Produces: `FundScoreRow` with six new optional fields, all `None` unless a fund was fully scored. Consumed by Task 3 (population) and Task 4 (frontend mirror type).

- [ ] **Step 1: Add the fields**

In `backend/app/services/analytics/schemas.py`, replace the `FundScoreRow` class:

```python
class FundScoreRow(BaseModel):
    """PRD-04 FR-5/FR-7 — one fund's composite score plus the full
    breakdown (return_percentile, risk_percentile, consistency_hit_rate)
    so it's never displayed as a bare number or a single-word label. The
    six `*_return`/`*_deviation`/`consistency_*` fields below are the raw
    numbers behind those percentiles — computed in `scorer.py` regardless,
    now also threaded through for the card's "See the evidence" section
    instead of being discarded after the percentile conversion."""

    scheme_id: str
    scheme_name: str
    category_unavailable: bool
    insufficient_history: bool
    thin_category: bool
    risk_adjusted_tier: int | None
    cost_adjustment: str | None
    final_score: str | None
    return_percentile: str | None
    risk_percentile: str | None
    consistency_hit_rate: str | None
    scheme_return: str | None
    category_avg_return: str | None
    downside_deviation: str | None
    category_avg_downside_deviation: str | None
    consistency_hits: int | None
    consistency_total_windows: int | None
```

- [ ] **Step 2: Verify the app still imports cleanly**

Run: `cd backend && python -c "from app.services.analytics.schemas import FundScoreRow; FundScoreRow(scheme_id='x', scheme_name='y', category_unavailable=False, insufficient_history=False, thin_category=False, risk_adjusted_tier=None, cost_adjustment=None, final_score=None, return_percentile=None, risk_percentile=None, consistency_hit_rate=None, scheme_return=None, category_avg_return=None, downside_deviation=None, category_avg_downside_deviation=None, consistency_hits=None, consistency_total_windows=None); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/analytics/schemas.py
git commit -m "feat(analytics): add raw evidence fields to FundScoreRow"
```

---

## Task 3: Thread raw evidence values through `scorer.py`

**Files:**
- Modify: `backend/app/services/analytics/scorer.py:69-288`
- Test: `backend/tests/services/analytics/test_scorer.py`

**Interfaces:**
- Consumes: `compute_consistency_hit_rate` now returns `tuple[int, int] | None` (Task 1). `FundScoreRow` now accepts the six new fields (Task 2). `_aum_weighted_average` and `_latest_aaum_by_scheme` are already imported into `scorer.py` from `category_ranking.py` — no new imports needed.
- Produces: `FundScoreRow` instances (from both `_empty_row` and `_finish_fund_score`) fully populated with the new evidence fields whenever a fund is scored; `None` for all six when it isn't.

- [ ] **Step 1: Add a failing test for the new fields**

Add to `backend/tests/services/analytics/test_scorer.py` (after `test_compute_fund_score_best_return_in_min_category_gets_tier_five`):

```python
def test_compute_fund_score_includes_raw_evidence_fields():
    db = _session()
    held = _scheme(db, "Held Fund")
    peer = _scheme(db, "Peer Fund")
    _seed_monthly_nav(db, held, 24, monthly_growth=Decimal("0.02"))
    _seed_monthly_nav(db, peer, 24, monthly_growth=Decimal("0.005"))
    db.add(SchemeAaum(scheme_id=held.id, reference_period=date(2026, 3, 31), aaum_value=Decimal("100")))
    db.add(SchemeAaum(scheme_id=peer.id, reference_period=date(2026, 3, 31), aaum_value=Decimal("100")))
    db.commit()

    async def _returns(db_, universe, today):
        return {held.id: Decimal("0.30"), peer.id: Decimal("0.05")}

    with (
        patch("app.services.analytics.scorer._category_returns", new=AsyncMock(side_effect=_returns)),
        patch("app.services.analytics.scorer.get_category_universe", new=AsyncMock(return_value=[held, peer])),
        patch("app.services.analytics.scorer._ensure_ter_fresh", new=AsyncMock(return_value=None)),
    ):
        row = asyncio.run(compute_fund_score(db, held))

    assert row.scheme_return == "0.30"
    assert row.category_avg_return is not None
    assert row.downside_deviation is not None
    assert row.category_avg_downside_deviation is not None
    assert row.consistency_hits is not None
    assert row.consistency_total_windows is not None
    assert row.consistency_hits <= row.consistency_total_windows
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `cd backend && python -m pytest tests/services/analytics/test_scorer.py -k includes_raw_evidence -v`
Expected: FAIL — `AttributeError: 'FundScoreRow' object has no attribute 'scheme_return'` (or a `TypeError` from the still-`Decimal`-shaped `compute_consistency_hit_rate` call inside `_compute_category_component_scores`, since Task 1 already landed and this function hasn't been updated yet)

- [ ] **Step 3: Add two small module-level helpers**

In `backend/app/services/analytics/scorer.py`, add near the top (after the existing constants, before `_tier_from_percentile`):

```python
def _decimal_field_to_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _decimal_field_to_int(value: Decimal | None) -> int | None:
    return int(value) if value is not None else None
```

- [ ] **Step 4: Replace `_compute_category_component_scores`**

Replace the whole function body in `backend/app/services/analytics/scorer.py`:

```python
async def _compute_category_component_scores(
    db: Session, universe: list[Scheme], today: date
) -> dict[uuid.UUID, dict[str, Decimal | None]]:
    returns_start = time.perf_counter()
    returns = await _category_returns(db, universe, today)
    returns_elapsed = time.perf_counter() - returns_start
    if not returns:
        return {}

    # Same AUM-weighted category average calculation category_ranking.py
    # already uses for CategoryRankRow.category_avg_return -- reused here,
    # not reinvented, for the "See the evidence" section's raw numbers.
    aaum_by_scheme = _latest_aaum_by_scheme(db, list(returns.keys()))
    category_avg_return = _aum_weighted_average(returns, aaum_by_scheme)

    month_ends = month_end_dates(years_ago(today, _HISTORY_YEARS), today)
    series_start = time.perf_counter()
    series_by_scheme = build_monthly_series_bulk(db, list(returns), month_ends)
    series_elapsed = time.perf_counter() - series_start
    # Instrumented 2026-08-20 alongside category_ranking.py/nav.py's timers —
    # see nav.py's warm_nav_history docstring note for why.
    logger.info(
        "_compute_category_component_scores[%s]: %d schemes, category_returns=%.2fs "
        "(cache hit if tiny) series_build=%.2fs",
        universe[0].sebi_category if universe else "?", len(universe), returns_elapsed, series_elapsed,
    )
    rolling_by_scheme = {
        scheme_id: rolling_12m_returns(series) for scheme_id, series in series_by_scheme.items()
    }
    medians = category_medians(list(rolling_by_scheme.values()))

    downside_by_scheme: dict[uuid.UUID, Decimal] = {}
    for scheme_id, series in series_by_scheme.items():
        deviation = compute_downside_deviation(monthly_returns(series))
        if deviation is not None:
            # Lower deviation is safer -> negate so `_rank_and_percentile`'s
            # "higher value ranks better" ordering favors the lowest
            # deviation.
            downside_by_scheme[scheme_id] = -deviation

    category_avg_downside_deviation = (
        -sum(downside_by_scheme.values(), Decimal(0)) / Decimal(len(downside_by_scheme))
        if downside_by_scheme
        else None
    )

    consistency_by_scheme = {
        scheme_id: compute_consistency_hit_rate(rolling_by_scheme[scheme_id], medians)
        for scheme_id in returns
    }

    scores: dict[uuid.UUID, dict[str, Decimal | None]] = {}
    for scheme_id in returns:
        return_rank = _rank_and_percentile(returns, scheme_id)
        risk_rank = (
            _rank_and_percentile(downside_by_scheme, scheme_id)
            if scheme_id in downside_by_scheme
            else None
        )
        return_pct = return_rank[1] if return_rank else None
        risk_pct = risk_rank[1] if risk_rank else None
        consistency_pair = consistency_by_scheme.get(scheme_id)
        consistency_pct = (
            Decimal(consistency_pair[0]) / Decimal(consistency_pair[1]) * Decimal(100)
            if consistency_pair
            else None
        )

        composite = None
        if return_pct is not None and risk_pct is not None and consistency_pct is not None:
            composite = (
                _RETURN_WEIGHT * return_pct + _RISK_WEIGHT * risk_pct + _CONSISTENCY_WEIGHT * consistency_pct
            )

        own_downside = -downside_by_scheme[scheme_id] if scheme_id in downside_by_scheme else None

        scores[scheme_id] = {
            "return_percentile": return_pct,
            "risk_percentile": risk_pct,
            "consistency_hit_rate": consistency_pct,
            "composite": composite,
            "scheme_return": returns.get(scheme_id),
            "category_avg_return": category_avg_return,
            "downside_deviation": own_downside,
            "category_avg_downside_deviation": category_avg_downside_deviation,
            "consistency_hits": Decimal(consistency_pair[0]) if consistency_pair else None,
            "consistency_total_windows": Decimal(consistency_pair[1]) if consistency_pair else None,
        }
    return scores
```

- [ ] **Step 5: Update `_empty_row`**

Replace `_empty_row` in `backend/app/services/analytics/scorer.py`:

```python
def _empty_row(scheme: Scheme, *, category_unavailable: bool, insufficient_history: bool) -> FundScoreRow:
    return FundScoreRow(
        scheme_id=str(scheme.id),
        scheme_name=scheme.name,
        category_unavailable=category_unavailable,
        insufficient_history=insufficient_history,
        thin_category=False,
        risk_adjusted_tier=None,
        cost_adjustment=None,
        final_score=None,
        return_percentile=None,
        risk_percentile=None,
        consistency_hit_rate=None,
        scheme_return=None,
        category_avg_return=None,
        downside_deviation=None,
        category_avg_downside_deviation=None,
        consistency_hits=None,
        consistency_total_windows=None,
    )
```

- [ ] **Step 6: Update `_finish_fund_score`'s return statement**

Replace the final `return FundScoreRow(...)` at the bottom of `_finish_fund_score` in `backend/app/services/analytics/scorer.py`:

```python
    return FundScoreRow(
        scheme_id=str(scheme.id),
        scheme_name=scheme.name,
        category_unavailable=False,
        insufficient_history=False,
        thin_category=len(universe) < _THIN_CATEGORY_THRESHOLD,
        risk_adjusted_tier=tier,
        cost_adjustment=str(cost_adjustment) if cost_adjustment is not None else None,
        final_score=str(final_score),
        return_percentile=str(scheme_scores["return_percentile"]),
        risk_percentile=str(scheme_scores["risk_percentile"]),
        consistency_hit_rate=str(scheme_scores["consistency_hit_rate"]),
        scheme_return=_decimal_field_to_str(scheme_scores.get("scheme_return")),
        category_avg_return=_decimal_field_to_str(scheme_scores.get("category_avg_return")),
        downside_deviation=_decimal_field_to_str(scheme_scores.get("downside_deviation")),
        category_avg_downside_deviation=_decimal_field_to_str(
            scheme_scores.get("category_avg_downside_deviation")
        ),
        consistency_hits=_decimal_field_to_int(scheme_scores.get("consistency_hits")),
        consistency_total_windows=_decimal_field_to_int(scheme_scores.get("consistency_total_windows")),
    )
```

`.get(...)` (not `[...]`) is deliberate for the six new keys only: `test_finish_fund_score_clamps_cost_adjustment_to_valid_range` (already in the test file) constructs a `scores` dict by hand with just the four original keys — `.get()` returns `None` for the new fields there instead of raising `KeyError`, so that existing test keeps passing unmodified.

- [ ] **Step 7: Run the new test, confirm it passes**

Run: `cd backend && python -m pytest tests/services/analytics/test_scorer.py -k includes_raw_evidence -v`
Expected: PASS

- [ ] **Step 8: Run the full scorer + risk_metrics + analytics route test files, confirm no regressions**

Run: `cd backend && python -m pytest tests/services/analytics/test_scorer.py tests/services/analytics/test_risk_metrics.py tests/api/test_analytics_scorer_route.py -v`
Expected: PASS (all tests, including the untouched ones — confirms the `.get()` fallback and the composite-score arithmetic are unchanged for existing cases)

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/analytics/scorer.py backend/tests/services/analytics/test_scorer.py
git commit -m "feat(analytics): thread raw evidence numbers through the scorer"
```

---

## Task 4: Mirror the new fields on the frontend `FundScoreRow` type

**Files:**
- Modify: `frontend/src/features/analytics/types.ts:71-83`

**Interfaces:**
- Produces: `FundScoreRow` (frontend) matching the backend schema from Task 2. Consumed by Tasks 6–8.

- [ ] **Step 1: Add the fields**

In `frontend/src/features/analytics/types.ts`, replace the `FundScoreRow` interface:

```typescript
/* Phase 2: Scorer Types (FR-5/FR-6/FR-7) */
export interface FundScoreRow {
  scheme_id: string;
  scheme_name: string;
  category_unavailable: boolean;
  insufficient_history: boolean;
  thin_category: boolean;
  risk_adjusted_tier: number | null;
  cost_adjustment: string | null;
  final_score: string | null;
  return_percentile: string | null;
  risk_percentile: string | null;
  consistency_hit_rate: string | null;
  scheme_return: string | null;
  category_avg_return: string | null;
  downside_deviation: string | null;
  category_avg_downside_deviation: string | null;
  consistency_hits: number | null;
  consistency_total_windows: number | null;
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: New errors at every `FundScoreRow` literal in test files that don't yet have the six new fields (`FundScoreCard.test.tsx`, `ScorerSection.test.tsx`, `FundScoreDetailModal.test.tsx`) — expected at this point, fixed in Tasks 6–8. No errors in non-test source files.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/analytics/types.ts
git commit -m "feat(analytics): mirror FundScoreRow's new evidence fields on the frontend"
```

---

## Task 5: `fundScoreVerdicts.ts` — deterministic bucket/verdict/sentence rules

**Files:**
- Create: `frontend/src/features/analytics/fundScoreVerdicts.ts`
- Test: `frontend/src/features/analytics/fundScoreVerdicts.test.ts`

**Interfaces:**
- Produces: `FactorKey`, `FACTOR_KEYS`, `FACTOR_LABELS`, `assessFactor()`, `displayTierFromBackendTier()`, `buildWhySentence()`, `whatThisMeansForYou()` — all consumed by Task 6 (`FundScoreCard.tsx`) and Task 8 (`ScorerSection.tsx` uses only `displayTierFromBackendTier`).
- Pure functions, no React/DOM dependency — testable in isolation.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/features/analytics/fundScoreVerdicts.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import {
  assessFactor,
  buildWhySentence,
  displayTierFromBackendTier,
  whatThisMeansForYou,
} from "./fundScoreVerdicts";

describe("displayTierFromBackendTier", () => {
  it("flips the backend 5=best convention to a 1=best display convention", () => {
    expect(displayTierFromBackendTier(5)).toBe(1);
    expect(displayTierFromBackendTier(4)).toBe(2);
    expect(displayTierFromBackendTier(3)).toBe(3);
    expect(displayTierFromBackendTier(2)).toBe(4);
    expect(displayTierFromBackendTier(1)).toBe(5);
  });
});

describe("assessFactor", () => {
  it("buckets p >= 50 as a green Strength", () => {
    expect(assessFactor("return", 50)).toMatchObject({ bucket: "strength", dotColor: "green", verdict: "strong" });
    expect(assessFactor("return", 100)).toMatchObject({ bucket: "strength", dotColor: "green", verdict: "excellent" });
  });

  it("buckets 20 <= p < 50 as an orange Watch-out", () => {
    expect(assessFactor("risk", 49)).toMatchObject({ bucket: "watchout", dotColor: "orange", verdict: "weak" });
    expect(assessFactor("risk", 20)).toMatchObject({ bucket: "watchout", dotColor: "orange", verdict: "weak" });
  });

  it("buckets p < 20 as a red Watch-out", () => {
    expect(assessFactor("consistency", 19)).toMatchObject({ bucket: "watchout", dotColor: "red", verdict: "poor" });
    expect(assessFactor("consistency", 0)).toMatchObject({ bucket: "watchout", dotColor: "red", verdict: "poor" });
  });

  it("crosses the excellent/strong boundary at p = 80", () => {
    expect(assessFactor("return", 79.99)).toMatchObject({ verdict: "strong" });
    expect(assessFactor("return", 80)).toMatchObject({ verdict: "excellent" });
  });

  it("returns a non-empty sentence distinct per factor", () => {
    const returnSentence = assessFactor("return", 90).sentence;
    const riskSentence = assessFactor("risk", 90).sentence;
    const consistencySentence = assessFactor("consistency", 90).sentence;
    expect(returnSentence).not.toBe(riskSentence);
    expect(riskSentence).not.toBe(consistencySentence);
    [returnSentence, riskSentence, consistencySentence].forEach((s) => expect(s.length).toBeGreaterThan(0));
  });
});

describe("buildWhySentence", () => {
  it("leads with the strongest factor and mentions low cost for top tiers", () => {
    const sentence = buildWhySentence({
      returnPct: 88,
      riskPct: 82,
      consistencyPct: 80,
      displayTier: 1,
      costAdjustment: 0.25,
    });
    expect(sentence).toBe("Scores well mainly due to strong long-term performance and low cost.");
  });

  it("omits the cost clause when there's no low-fee bonus", () => {
    const sentence = buildWhySentence({
      returnPct: 88,
      riskPct: 82,
      consistencyPct: 80,
      displayTier: 2,
      costAdjustment: null,
    });
    expect(sentence).toBe("Scores well mainly due to strong long-term performance.");
  });

  it("leads with the weakest factor and mentions high cost for bottom tiers", () => {
    const sentence = buildWhySentence({
      returnPct: 15,
      riskPct: 40,
      consistencyPct: 45,
      displayTier: 5,
      costAdjustment: -0.25,
    });
    expect(sentence).toBe("Held back mainly by weaker long-term performance and higher-than-average cost.");
  });

  it("balances strongest and weakest for the middle tier", () => {
    const sentence = buildWhySentence({
      returnPct: 70,
      riskPct: 30,
      consistencyPct: 50,
      displayTier: 3,
      costAdjustment: null,
    });
    expect(sentence).toBe(
      "Performs roughly in line with similar funds, with strength in strong long-term performance balanced by weaker weaker downside protection."
    );
  });
});

describe("whatThisMeansForYou", () => {
  it("returns a distinct sentence for every display tier 1-5", () => {
    const sentences = [1, 2, 3, 4, 5].map(whatThisMeansForYou);
    expect(new Set(sentences).size).toBe(5);
    sentences.forEach((s) => expect(s.length).toBeGreaterThan(0));
  });
});
```

- [ ] **Step 2: Run the tests, confirm they fail**

Run: `cd frontend && npx vitest run src/features/analytics/fundScoreVerdicts.test.ts`
Expected: FAIL — `Cannot find module './fundScoreVerdicts'`

- [ ] **Step 3: Implement `fundScoreVerdicts.ts`**

Create `frontend/src/features/analytics/fundScoreVerdicts.ts`:

```typescript
/** Deterministic plain-English rules for the Fund Score card (design doc
 * §6): which of the three factors are Strengths vs. Watch-outs, what verdict
 * word and sentence each gets, the card's one-line "why" summary, and the
 * closing "what this means for you" sentence. Pure functions, no React
 * dependency, so the rules are testable without rendering anything. */

export type FactorKey = "return" | "risk" | "consistency";
export type Bucket = "strength" | "watchout";
export type DotColor = "green" | "orange" | "red";
export type Verdict = "excellent" | "strong" | "weak" | "poor";

export const FACTOR_KEYS: FactorKey[] = ["return", "risk", "consistency"];

export const FACTOR_LABELS: Record<FactorKey, string> = {
  return: "Return",
  risk: "Downside protection",
  consistency: "Consistency of outperformance",
};

const FACTOR_SENTENCES: Record<FactorKey, Record<Verdict, string>> = {
  return: {
    excellent: "Strong long-term performance — has consistently outperformed similar funds.",
    strong: "Solid long-term performance, generally in line with or ahead of similar funds.",
    weak: "Below-average long-term performance compared to similar funds.",
    poor: "Long-term performance has lagged most similar funds.",
  },
  risk: {
    excellent: "Strong downside protection — has historically lost less than peers in falling markets.",
    strong: "Reasonable downside protection compared to similar funds.",
    weak: "Below-average downside protection — has historically fallen more than peers in weak markets.",
    poor: "Weak downside protection — has historically lost more than most peers in falling markets.",
  },
  consistency: {
    excellent: "Very consistent — has beaten its category median in most 12-month periods.",
    strong: "Fairly consistent — has beaten its category median in more than half of 12-month periods.",
    weak: "Inconsistent — has beaten its category median in less than half of 12-month periods.",
    poor: "Highly inconsistent — has rarely beaten its category median over rolling 12-month periods.",
  },
};

const WHY_PHRASES: Record<FactorKey, { strong: string; weak: string }> = {
  return: { strong: "strong long-term performance", weak: "weaker long-term performance" },
  risk: { strong: "strong downside protection", weak: "weaker downside protection" },
  consistency: {
    strong: "consistent outperformance of peers",
    weak: "inconsistent performance versus peers",
  },
};

const WHAT_THIS_MEANS_FOR_YOU: Record<number, string> = {
  1: "A strong choice within its category based on historical data — suitable if you're comfortable with typical risk for this fund type.",
  2: "A solid, dependable option within its category based on historical data.",
  3: "An average performer within its category — worth comparing against a few alternatives before deciding.",
  4: "A below-average performer within its category — consider reviewing whether it still fits your goals.",
  5: "One of the weaker performers within its category based on historical data — worth a closer look before adding more.",
};

/** Backend tier convention is 5=best; display convention is 1=best.
 * Display-only — never change what the backend stores or returns. */
export function displayTierFromBackendTier(tier: number): number {
  return 6 - tier;
}

export function verdictWord(percentile: number): Verdict {
  if (percentile >= 80) return "excellent";
  if (percentile >= 50) return "strong";
  if (percentile >= 20) return "weak";
  return "poor";
}

export function bucketAndColor(percentile: number): { bucket: Bucket; dotColor: DotColor } {
  if (percentile >= 50) return { bucket: "strength", dotColor: "green" };
  if (percentile >= 20) return { bucket: "watchout", dotColor: "orange" };
  return { bucket: "watchout", dotColor: "red" };
}

export interface FactorAssessment {
  bucket: Bucket;
  dotColor: DotColor;
  verdict: Verdict;
  sentence: string;
}

export function assessFactor(factor: FactorKey, percentile: number): FactorAssessment {
  const verdict = verdictWord(percentile);
  const { bucket, dotColor } = bucketAndColor(percentile);
  return { bucket, dotColor, verdict, sentence: FACTOR_SENTENCES[factor][verdict] };
}

export function buildWhySentence(params: {
  returnPct: number;
  riskPct: number;
  consistencyPct: number;
  displayTier: number;
  costAdjustment: number | null;
}): string {
  const { returnPct, riskPct, consistencyPct, displayTier, costAdjustment } = params;
  const values: Record<FactorKey, number> = {
    return: returnPct,
    risk: riskPct,
    consistency: consistencyPct,
  };
  const strongest = FACTOR_KEYS.reduce((a, b) => (values[b] > values[a] ? b : a));
  const weakest = FACTOR_KEYS.reduce((a, b) => (values[b] < values[a] ? b : a));
  const costBonus = costAdjustment !== null && Math.abs(costAdjustment - 0.25) < 0.001;
  const costPenalty = costAdjustment !== null && Math.abs(costAdjustment + 0.25) < 0.001;

  if (displayTier <= 2) {
    return `Scores well mainly due to ${WHY_PHRASES[strongest].strong}${costBonus ? " and low cost" : ""}.`;
  }
  if (displayTier >= 4) {
    return `Held back mainly by ${WHY_PHRASES[weakest].weak}${costPenalty ? " and higher-than-average cost" : ""}.`;
  }
  return `Performs roughly in line with similar funds, with strength in ${WHY_PHRASES[strongest].strong} balanced by weaker ${WHY_PHRASES[weakest].weak}.`;
}

export function whatThisMeansForYou(displayTier: number): string {
  return WHAT_THIS_MEANS_FOR_YOU[displayTier] ?? WHAT_THIS_MEANS_FOR_YOU[3];
}
```

- [ ] **Step 4: Run the tests, confirm they pass**

Run: `cd frontend && npx vitest run src/features/analytics/fundScoreVerdicts.test.ts`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/analytics/fundScoreVerdicts.ts frontend/src/features/analytics/fundScoreVerdicts.test.ts
git commit -m "feat(analytics): add fundScoreVerdicts deterministic rule module"
```

---

## Task 6: Rebuild `FundScoreCard.tsx`

**Files:**
- Modify: `frontend/src/features/analytics/FundScoreCard.tsx`
- Modify: `frontend/src/features/analytics/FundScoreCard.test.tsx`

**Interfaces:**
- Consumes: `FundScoreRow` (Task 4), `FACTOR_KEYS`/`FACTOR_LABELS`/`assessFactor`/`displayTierFromBackendTier`/`buildWhySentence`/`whatThisMeansForYou` (Task 5), `toPercentString` from `@/lib/decimal` (existing).
- Produces: `FundScoreCard({ data: FundScoreRow })` — same public prop shape as today, unchanged consumer contract for `FundScoreDetailModal.tsx` (Task 7).

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/features/analytics/FundScoreCard.test.tsx`:

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { FundScoreCard } from "./FundScoreCard";
import type { FundScoreRow } from "./types";

const baseRow: FundScoreRow = {
  scheme_id: "s-1",
  scheme_name: "Test Flexi Cap Fund",
  category_unavailable: false,
  insufficient_history: false,
  thin_category: false,
  risk_adjusted_tier: 4, // displayTier = 2
  cost_adjustment: "0.25",
  final_score: "78.4", // displayScore 7.8
  return_percentile: "70", // strong -> Strength, green
  risk_percentile: "65", // strong -> Strength, green
  consistency_hit_rate: "15", // poor -> Watch-out, red
  scheme_return: "0.184",
  category_avg_return: "0.15",
  downside_deviation: "0.03",
  category_avg_downside_deviation: "0.035",
  consistency_hits: 2,
  consistency_total_windows: 13,
};

describe("FundScoreCard", () => {
  it("renders the score out of 10, flipped tier, and the why sentence", () => {
    render(<FundScoreCard data={baseRow} />);
    expect(screen.getByText("7.8")).toBeInTheDocument();
    expect(screen.getByText("/ 10")).toBeInTheDocument();
    expect(screen.getByText("Tier 2 of 5")).toBeInTheDocument();
    expect(
      screen.getByText("Scores well mainly due to strong long-term performance and low cost.")
    ).toBeInTheDocument();
  });

  it("groups factors into Strengths and Watch-outs with plain labels, no raw percentiles or weight badges", () => {
    render(<FundScoreCard data={baseRow} />);
    expect(screen.getByText("What's driving your score")).toBeInTheDocument();
    expect(screen.getByText("Strengths")).toBeInTheDocument();
    expect(screen.getByText("Watch-outs")).toBeInTheDocument();
    expect(screen.getByText("Return")).toBeInTheDocument();
    expect(screen.getByText("Downside protection")).toBeInTheDocument();
    expect(screen.getByText("Consistency of outperformance")).toBeInTheDocument();
    expect(screen.queryByText("70%")).not.toBeInTheDocument();
    expect(screen.queryByText("45% Wt")).not.toBeInTheDocument();
    expect(screen.queryByText("The 3 Core Methodology Ingredients")).not.toBeInTheDocument();
  });

  it("renders the what-this-means-for-you block", () => {
    render(<FundScoreCard data={baseRow} />);
    expect(screen.getByText("What this means for you")).toBeInTheDocument();
  });

  it("reveals evidence numbers only after expanding See the evidence", () => {
    render(<FundScoreCard data={baseRow} />);
    expect(screen.queryByText("18.40%")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("See the evidence"));
    expect(screen.getByText("18.40%")).toBeInTheDocument();
    expect(screen.getByText("2 of 13")).toBeInTheDocument();
  });

  it("reveals methodology only after expanding How we calculate this score", () => {
    render(<FundScoreCard data={baseRow} />);
    expect(screen.queryByText(/45% of score/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("How we calculate this score"));
    expect(screen.getByText(/45% of score/)).toBeInTheDocument();
  });

  it("keeps the Transparent Methodology Commitment box as the last element", () => {
    render(<FundScoreCard data={baseRow} />);
    expect(screen.getByText("Transparent Methodology Commitment")).toBeInTheDocument();
  });

  it("shows the category-unavailable notice instead of the score", () => {
    render(<FundScoreCard data={{ ...baseRow, category_unavailable: true }} />);
    expect(screen.getByText("Category Data Unavailable")).toBeInTheDocument();
    expect(screen.queryByText("What's driving your score")).not.toBeInTheDocument();
  });

  it("shows the insufficient-history notice instead of the score", () => {
    render(<FundScoreCard data={{ ...baseRow, insufficient_history: true }} />);
    expect(screen.getByText("Insufficient Track Record")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests, confirm they fail**

Run: `cd frontend && npx vitest run src/features/analytics/FundScoreCard.test.tsx`
Expected: FAIL — text like "Tier 2 of 5", "What's driving your score", "Strengths" not found against the current implementation

- [ ] **Step 3: Rebuild the component**

Replace `frontend/src/features/analytics/FundScoreCard.tsx`:

```tsx
import { useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import type { FundScoreRow } from "./types";
import { ShieldAlert, Info, Sparkles, CheckCircle2, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { toPercentString } from "@/lib/decimal";
import {
  FACTOR_KEYS,
  FACTOR_LABELS,
  assessFactor,
  buildWhySentence,
  displayTierFromBackendTier,
  whatThisMeansForYou,
  type FactorKey,
} from "./fundScoreVerdicts";

export interface FundScoreCardProps {
  data: FundScoreRow;
}

function parseNum(val: string | null | undefined): number | null {
  if (val === null || val === undefined) return null;
  const num = parseFloat(val);
  return isNaN(num) ? null : num;
}

function formatRawFractionPercent(val: string | null): string {
  return val === null ? "N/A" : `${toPercentString(val)}%`;
}

const DOT_CLASS: Record<string, string> = {
  green: "bg-[var(--color-positive)]",
  orange: "bg-[var(--color-warning)]",
  red: "bg-[var(--color-negative)]",
};

function UnavailableNotice({ icon, title, body }: { icon: ReactNode; title: string; body: string }) {
  return (
    <div className="rounded-xl border border-[var(--color-warning)]/40 bg-[var(--color-warning)]/5 p-4 flex items-center gap-3">
      {icon}
      <div className="text-xs">
        <p className="font-bold text-[var(--color-ink)]">{title}</p>
        <p className="text-[var(--color-text-secondary)]">{body}</p>
      </div>
    </div>
  );
}

interface AssessedFactor {
  key: FactorKey;
  dotColor: "green" | "orange" | "red";
  sentence: string;
}

function FactorGroup({ title, items }: { title: string; items: AssessedFactor[] }) {
  return (
    <div className="space-y-2">
      <span
        className={cn(
          "text-[10px] font-bold uppercase tracking-wider block",
          title === "Strengths" ? "text-[var(--color-positive)]" : "text-[var(--color-warning)]"
        )}
      >
        {title}
      </span>
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.key}
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5 flex items-start gap-3 shadow-2xs"
          >
            <span className={cn("h-2.5 w-2.5 rounded-full mt-1.5 flex-shrink-0", DOT_CLASS[item.dotColor])} />
            <div className="space-y-0.5">
              <span className="text-xs font-semibold text-[var(--color-ink)]">{FACTOR_LABELS[item.key]}</span>
              <p className="text-[11px] text-[var(--color-text-secondary)] leading-relaxed">{item.sentence}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Accordion({
  open,
  onToggle,
  title,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between p-3.5 text-xs font-semibold text-[var(--color-ink)] bg-[var(--color-bg)]/40 hover:bg-[var(--color-bg)]/70 transition-colors"
      >
        <span>{title}</span>
        <ChevronDown
          className={cn("h-4 w-4 text-[var(--color-text-secondary)] transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="p-3.5 pt-3 text-xs space-y-2.5 border-t border-[var(--color-border)]">{children}</div>
      )}
    </div>
  );
}

function EvidenceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[var(--color-text-secondary)]">{label}</span>
      <span className="font-semibold text-[var(--color-ink)] tabular-nums">{value}</span>
    </div>
  );
}

function EvidenceSection({ data }: { data: FundScoreRow }) {
  const downside = parseNum(data.downside_deviation);
  const categoryAvgDownside = parseNum(data.category_avg_downside_deviation);
  // Annualized (x sqrt(12)) purely for a more legible on-screen number --
  // risk_metrics.py's docstring notes this is a constant scalar that
  // doesn't change relative ranking, so it's safe as a display-only
  // transform without touching the backend's ranking computation.
  const annualizedDownside = downside !== null ? downside * Math.sqrt(12) * 100 : null;
  const annualizedCategoryDownside =
    categoryAvgDownside !== null ? categoryAvgDownside * Math.sqrt(12) * 100 : null;

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <p className="font-semibold text-[var(--color-ink)]">Return</p>
        <EvidenceRow label="This fund" value={formatRawFractionPercent(data.scheme_return)} />
        <EvidenceRow label="Category average" value={formatRawFractionPercent(data.category_avg_return)} />
      </div>
      <div className="space-y-1.5">
        <p className="font-semibold text-[var(--color-ink)]">Downside protection (annualized downside deviation)</p>
        <EvidenceRow label="This fund" value={annualizedDownside !== null ? `${annualizedDownside.toFixed(2)}%` : "N/A"} />
        <EvidenceRow
          label="Category average"
          value={annualizedCategoryDownside !== null ? `${annualizedCategoryDownside.toFixed(2)}%` : "N/A"}
        />
      </div>
      <div className="space-y-1.5">
        <p className="font-semibold text-[var(--color-ink)]">Consistency</p>
        <EvidenceRow
          label="Rolling 12-month periods beaten"
          value={
            data.consistency_hits !== null && data.consistency_total_windows !== null
              ? `${data.consistency_hits} of ${data.consistency_total_windows}`
              : "N/A"
          }
        />
      </div>
    </div>
  );
}

function MethodologySection({ costAdjNum }: { costAdjNum: number | null }) {
  return (
    <div className="space-y-2 text-[var(--color-text-secondary)] leading-relaxed">
      <p>
        The Unifolio Score combines three weighted components, ranked against every fund in the same SEBI
        category:
      </p>
      <ul className="list-disc pl-4 space-y-1">
        <li>
          <span className="font-semibold text-[var(--color-ink)]">Return — 45% of score:</span> medium/long-term
          CAGR growth vs. category peers.
        </li>
        <li>
          <span className="font-semibold text-[var(--color-ink)]">Downside protection — 30% of score:</span>{" "}
          downside-only volatility (losses in bad months only) vs. category peers.
        </li>
        <li>
          <span className="font-semibold text-[var(--color-ink)]">Consistency — 25% of score:</span> how often
          the fund beat its category's median return over rolling 12-month periods.
        </li>
      </ul>
      <p>
        A cost adjustment of up to ±0.25 points is then applied based on this fund's expense ratio (TER) versus
        the AUM-weighted category average, with a 0.05 percentage-point dead zone where no adjustment is made.
        {costAdjNum !== null && (
          <span className="block mt-1 font-medium text-[var(--color-ink)]">
            {costAdjNum > 0
              ? `This fund received a +${costAdjNum.toFixed(2)} point low-fee bonus.`
              : costAdjNum < 0
                ? `This fund received a ${costAdjNum.toFixed(2)} point high-fee penalty.`
                : "This fund's fee is close enough to the category average — no adjustment applied."}
          </span>
        )}
      </p>
    </div>
  );
}

export function FundScoreCard({ data }: FundScoreCardProps) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [methodologyOpen, setMethodologyOpen] = useState(false);

  if (data.category_unavailable) {
    return (
      <div className="space-y-6 pt-2">
        <UnavailableNotice
          icon={<ShieldAlert className="h-5 w-5 text-[var(--color-warning)] flex-shrink-0" />}
          title="Category Data Unavailable"
          body="This scheme cannot be scored because SEBI category classification data is not available."
        />
      </div>
    );
  }
  if (data.insufficient_history) {
    return (
      <div className="space-y-6 pt-2">
        <UnavailableNotice
          icon={<Info className="h-5 w-5 text-[var(--color-warning)] flex-shrink-0" />}
          title="Insufficient Track Record"
          body="This fund does not have enough historical NAV data to evaluate downside risk and 12-month rolling consistency."
        />
      </div>
    );
  }

  const finalScoreNum = parseNum(data.final_score);
  const displayScore = finalScoreNum !== null ? finalScoreNum / 10 : null;
  const returnPct = parseNum(data.return_percentile);
  const riskPct = parseNum(data.risk_percentile);
  const consistencyPct = parseNum(data.consistency_hit_rate);
  const costAdjNum = parseNum(data.cost_adjustment);
  const displayTier = data.risk_adjusted_tier !== null ? displayTierFromBackendTier(data.risk_adjusted_tier) : null;

  const factorPct: Record<FactorKey, number | null> = {
    return: returnPct,
    risk: riskPct,
    consistency: consistencyPct,
  };
  const fullyScored = returnPct !== null && riskPct !== null && consistencyPct !== null;
  const assessments = fullyScored
    ? FACTOR_KEYS.map((key) => ({ key, ...assessFactor(key, factorPct[key]!) }))
    : [];
  const strengths = assessments.filter((a) => a.bucket === "strength");
  const watchouts = assessments.filter((a) => a.bucket === "watchout");

  const whySentence =
    fullyScored && displayTier !== null
      ? buildWhySentence({
          returnPct: returnPct!,
          riskPct: riskPct!,
          consistencyPct: consistencyPct!,
          displayTier,
          costAdjustment: costAdjNum,
        })
      : null;

  return (
    <div className="space-y-6 pt-2">
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]/60 p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-[11px] font-medium text-[var(--color-text-secondary)] uppercase tracking-wider block">
              Unifolio Score
            </span>
            <div className="flex items-baseline gap-2 mt-0.5">
              <span className="font-display text-3xl font-bold text-[var(--color-ink)] tabular-nums type-display">
                {displayScore !== null ? displayScore.toFixed(1) : "N/A"}
              </span>
              <span className="text-xs font-semibold text-[var(--color-text-secondary)]">/ 10</span>
            </div>
          </div>
          {displayTier !== null && (
            <div className="text-right">
              <Badge className="bg-[var(--color-accent)] text-white font-bold text-xs px-3 py-1 shadow-xs">
                Tier {displayTier} of 5
              </Badge>
              <span className="text-[10px] text-[var(--color-text-secondary)] block mt-1">
                {displayTier <= 2
                  ? "Top Tier Performer"
                  : displayTier === 3
                    ? "Average Category Rank"
                    : "Below Category Average"}
              </span>
            </div>
          )}
        </div>
        {whySentence && (
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed border-t border-[var(--color-border)]/60 pt-2.5">
            {whySentence}
          </p>
        )}
      </div>

      {fullyScored && (
        <div className="space-y-3">
          <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-secondary)] flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-[var(--color-accent)]" />
            <span>What's driving your score</span>
          </h4>
          {strengths.length > 0 && <FactorGroup title="Strengths" items={strengths} />}
          {watchouts.length > 0 && <FactorGroup title="Watch-outs" items={watchouts} />}
        </div>
      )}

      {displayTier !== null && (
        <div className="rounded-xl border border-[var(--color-accent)]/30 bg-[var(--color-accent)]/5 p-4 text-xs">
          <p className="font-bold text-[var(--color-ink)] mb-1">What this means for you</p>
          <p className="text-[var(--color-text-secondary)] leading-relaxed">{whatThisMeansForYou(displayTier)}</p>
        </div>
      )}

      <Accordion open={evidenceOpen} onToggle={() => setEvidenceOpen((v) => !v)} title="See the evidence">
        <EvidenceSection data={data} />
      </Accordion>

      <Accordion
        open={methodologyOpen}
        onToggle={() => setMethodologyOpen((v) => !v)}
        title="How we calculate this score"
      >
        <MethodologySection costAdjNum={costAdjNum} />
      </Accordion>

      <div className="rounded-xl border border-[var(--color-border)]/80 bg-[var(--color-bg)]/30 p-3.5 text-[11px] text-[var(--color-text-secondary)] space-y-1">
        <p className="font-bold text-[var(--color-ink)] flex items-center gap-1">
          <CheckCircle2 className="h-3.5 w-3.5 text-[var(--color-positive)]" />
          <span>Transparent Methodology Commitment</span>
        </p>
        <p className="leading-relaxed">
          Unifolio Fund Scores are modeling judgments built on historical data using a fixed 45% Return / 30%
          Downside Risk / 25% Consistency formula with TER fee nudges. They are comparative analytical insights,
          not regulated investment advice or guarantees.
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests, confirm they pass**

Run: `cd frontend && npx vitest run src/features/analytics/FundScoreCard.test.tsx`
Expected: PASS (all tests)

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: No errors from `FundScoreCard.tsx` or `FundScoreCard.test.tsx` (errors may remain in `ScorerSection.test.tsx`/`FundScoreDetailModal.test.tsx` — fixed in Tasks 7–8)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/analytics/FundScoreCard.tsx frontend/src/features/analytics/FundScoreCard.test.tsx
git commit -m "feat(analytics): rebuild FundScoreCard with plain-English drivers and evidence/methodology accordions"
```

---

## Task 7: `FundScoreDetailModal.tsx` subtitle

**Files:**
- Modify: `frontend/src/features/analytics/FundScoreDetailModal.tsx:85`
- Modify: `frontend/src/features/analytics/FundScoreDetailModal.test.tsx`

**Interfaces:**
- No prop/interface changes — `FundScoreDetailModal`'s own props are untouched. Its `DialogDescription` copy changes, and its test's `sampleScoreRow` fixture needs the six new `FundScoreRow` fields (Task 4) plus assertions matching the new `FundScoreCard` (Task 6).

- [ ] **Step 1: Update the test fixture and assertions**

Replace `frontend/src/features/analytics/FundScoreDetailModal.test.tsx`:

```typescript
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { FundScoreDetailModal } from "./FundScoreDetailModal";
import * as api from "./api";

vi.mock("./api");

const sampleScoreRow = {
  scheme_id: "scheme-101",
  scheme_name: "Parag Parikh Flexi Cap Fund",
  category_unavailable: false,
  insufficient_history: false,
  thin_category: false,
  risk_adjusted_tier: 5, // displayTier = 1
  cost_adjustment: "0.25",
  final_score: "85.0", // displayScore 8.5
  return_percentile: "88.0",
  risk_percentile: "82.0",
  consistency_hit_rate: "80.0",
  scheme_return: "0.22",
  category_avg_return: "0.15",
  downside_deviation: "0.025",
  category_avg_downside_deviation: "0.03",
  consistency_hits: 12,
  consistency_total_windows: 15,
};

describe("FundScoreDetailModal (S20)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders modal with initialData breakdown when open", () => {
    render(
      <FundScoreDetailModal
        isOpen={true}
        onClose={vi.fn()}
        schemeId="scheme-101"
        initialData={sampleScoreRow}
      />
    );

    expect(screen.getByText("Parag Parikh Flexi Cap Fund")).toBeInTheDocument();
    expect(screen.getByText("How this fund compares to similar funds in its category.")).toBeInTheDocument();
    expect(screen.getByText("8.5")).toBeInTheDocument();
    expect(screen.getByText("Tier 1 of 5")).toBeInTheDocument();
    expect(
      screen.getByText("Scores well mainly due to strong long-term performance and low cost.")
    ).toBeInTheDocument();
    expect(screen.queryByText("Watch-outs")).not.toBeInTheDocument();
    expect(screen.queryByText("88.0%")).not.toBeInTheDocument();
  });

  it("fetches fund score from API when initialData is not supplied", async () => {
    vi.mocked(api.getFundScore).mockResolvedValue(sampleScoreRow);

    render(
      <FundScoreDetailModal
        isOpen={true}
        onClose={vi.fn()}
        schemeId="scheme-101"
      />
    );

    await waitFor(() => {
      expect(api.getFundScore).toHaveBeenCalledWith("scheme-101");
      expect(screen.getByText("Parag Parikh Flexi Cap Fund")).toBeInTheDocument();
    });
  });

  it("returns null when isOpen is false", () => {
    const { container } = render(
      <FundScoreDetailModal
        isOpen={false}
        onClose={vi.fn()}
        schemeId="scheme-101"
        initialData={sampleScoreRow}
      />
    );

    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests, confirm they fail on the subtitle and tier assertions**

Run: `cd frontend && npx vitest run src/features/analytics/FundScoreDetailModal.test.tsx`
Expected: FAIL — subtitle text not found, "Tier 1 of 5" not found (still shows "Tier 5 of 5")

- [ ] **Step 3: Update the subtitle**

In `frontend/src/features/analytics/FundScoreDetailModal.tsx`, change:

```diff
-          <DialogDescription className="text-xs text-[var(--color-text-secondary)]">
-            Comprehensive quality verdict relative to true SEBI category peers
-          </DialogDescription>
+          <DialogDescription className="text-xs text-[var(--color-text-secondary)]">
+            How this fund compares to similar funds in its category.
+          </DialogDescription>
```

- [ ] **Step 4: Run the tests again, confirm they pass**

Run: `cd frontend && npx vitest run src/features/analytics/FundScoreDetailModal.test.tsx`
Expected: PASS (all tests — the tier/sentence assertions now pass because Task 6 already rebuilt `FundScoreCard`)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/analytics/FundScoreDetailModal.tsx frontend/src/features/analytics/FundScoreDetailModal.test.tsx
git commit -m "feat(analytics): simplify FundScoreDetailModal subtitle copy"
```

---

## Task 8: `ScorerSection.tsx` tier-badge display fix

**Files:**
- Modify: `frontend/src/features/analytics/ScorerSection.tsx:141-208`
- Modify: `frontend/src/features/analytics/ScorerSection.test.tsx`

**Interfaces:**
- Consumes: `displayTierFromBackendTier` (Task 5).
- No other change in this file — the AUM-weighted hero stat, the per-fund percentile breakdown row, and everything else stays `/100` and untouched (Global Constraints).

- [ ] **Step 1: Update the test fixture and assertions**

In `frontend/src/features/analytics/ScorerSection.test.tsx`, update `sampleScoreSummary`'s first fund and the assertions:

```diff
     {
       scheme_id: "scheme-101",
       scheme_name: "Parag Parikh Flexi Cap Fund",
       category_unavailable: false,
       insufficient_history: false,
       thin_category: false,
       risk_adjusted_tier: 5,
       cost_adjustment: "0.25",
       final_score: "82.0",
       return_percentile: "88.0",
       risk_percentile: "82.0",
       consistency_hit_rate: "80.0",
+      scheme_return: "0.22",
+      category_avg_return: "0.15",
+      downside_deviation: "0.025",
+      category_avg_downside_deviation: "0.03",
+      consistency_hits: 12,
+      consistency_total_windows: 15,
     },
     {
       scheme_id: "scheme-102",
       scheme_name: "New Unrated Scheme",
       category_unavailable: false,
       insufficient_history: true,
       thin_category: false,
       risk_adjusted_tier: null,
       cost_adjustment: null,
       final_score: null,
       return_percentile: null,
       risk_percentile: null,
       consistency_hit_rate: null,
+      scheme_return: null,
+      category_avg_return: null,
+      downside_deviation: null,
+      category_avg_downside_deviation: null,
+      consistency_hits: null,
+      consistency_total_windows: null,
     },
```

```diff
-    expect(screen.getByText("T5")).toBeInTheDocument();
+    expect(screen.getByText("T1")).toBeInTheDocument();
```

- [ ] **Step 2: Run the tests, confirm they fail**

Run: `cd frontend && npx vitest run src/features/analytics/ScorerSection.test.tsx`
Expected: FAIL — `T1` not found (still shows `T5`); also fails to compile until Task 4's types land (already done by this point)

- [ ] **Step 3: Fix the tier display**

In `frontend/src/features/analytics/ScorerSection.tsx`, add the import:

```diff
 import { AlertCircle, ChevronRight, HelpCircle, Star } from "lucide-react";
 import type { PortfolioScoreSummary } from "./types";
+import { displayTierFromBackendTier } from "./fundScoreVerdicts";
```

Inside the `funds.map((fund) => { ... })` block, add a `displayTier` and use it in both places `tier` is rendered:

```diff
             const tier = fund.risk_adjusted_tier;
+            const displayTier = tier !== null ? displayTierFromBackendTier(tier) : null;
```

```diff
                     <div className="h-8 w-8 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] flex items-center justify-center font-display font-bold text-xs text-[var(--color-accent)] shadow-2xs group-hover:scale-105 transition-transform">
-                      {tier !== null ? `T${tier}` : "—"}
+                      {displayTier !== null ? `T${displayTier}` : "—"}
                     </div>
```

```diff
                       <Badge className="bg-[var(--color-accent)] text-white font-bold text-xs px-2.5 py-1 shadow-2xs">
-                        Tier {tier}
+                        Tier {displayTier}
                       </Badge>
```

- [ ] **Step 4: Run the tests again, confirm they pass**

Run: `cd frontend && npx vitest run src/features/analytics/ScorerSection.test.tsx`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/analytics/ScorerSection.tsx frontend/src/features/analytics/ScorerSection.test.tsx
git commit -m "fix(analytics): flip ScorerSection's tier badges to the 1=best display convention"
```

---

## Task 9: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Backend full suite**

Run: `cd backend && python -m pytest -q`
Expected: All tests pass, 0 failures (same skip count as before this work — no unrelated regressions)

- [ ] **Step 2: Frontend full suite**

Run: `cd frontend && npx vitest run`
Expected: All tests pass, 0 failures

- [ ] **Step 3: Frontend type-check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: Clean, no errors

- [ ] **Step 4: Manual smoke check**

Start the app locally, open a held fund's Fund Score detail modal, and confirm: score renders as `X.X / 10`; the why-sentence appears under the score; Strengths/Watch-outs render with colored dots and no raw percentages; "See the evidence" and "How we calculate this score" are collapsed by default and expand on click; the "Transparent Methodology Commitment" box is the last element; no bottom CTA is present. Also open the main analytics Scorer section and confirm the `T{n}` avatar and `Tier {n}` badge on each fund row now show the flipped (1=best) value.

- [ ] **Step 5: Update session.md**

Add a short dated note to `session.md`'s current-session section recording that the Fund Score card redesign (spec + plan at the paths above) is implemented, and that the precompute-cache backfill (manual recompute re-run) is still pending, deferred to the AWS/deployment phase per the spec's §8.

No commit for this task — verification and documentation only, not covered by a single diff.
