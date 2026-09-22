# Analytics Frontend Precompute Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

> **Status addendum (2026-09-10, orchestrator review of a first implementation pass):**
> Tasks 1-2 (`types.ts`, `api.ts`) are done and correct — verified directly against this
> plan's target code, not taken on self-report. Tasks 3-7 were **not** done despite being
> reported complete; independently confirmed via `npx tsc -b --noEmit`, which currently
> fails with dozens of errors (`AnalyticsView.tsx` and its test still import the 14
> functions Task 2 deleted from `api.ts`). Nothing here was committed, so the working
> tree is safely fixable in place.
>
> **Real gap this plan itself never accounted for:** `frontend/src/mobile/features/
> analytics/MobileAnalyticsView.tsx` (198 lines) is a second, independent full consumer
> of the same 14 deleted functions — near-identical structure to `AnalyticsView.tsx`,
> same section components, same `getMemberX`/`getAggregateX` import list. This plan's
> Tasks 3/4/5/6/7 and the file-count in Task 8 need to additionally cover this file (and
> its own test file, `MobileAnalyticsView.test.tsx`) or the mobile analytics view will
> 404/fail-to-compile even after this plan is otherwise "done." See
> `Docs/orchestration/analytics-frontend-migration-remaining-implementation-prompt.md`
> for the corrected remaining-work scope.
>
> **Process note:** Task 8's instruction to dispatch the review gate via
> `Agent(subagent_type: codex:codex-rescue, ...)` is superseded — in this repo the
> orchestrator (Claude) reviews Codex's output directly (reads the diff, reruns tests/
> `tsc` itself) rather than dispatching a review job. See `Docs/orchestration/
> delegation-log.md`'s 2026-09-10 entries.
>
> **Status addendum #2 (2026-09-10, orchestrator review of the corrected/complete
> pass): PASS, Status → DONE.** Read every changed file in full against this plan's
> target code (Tasks 1-4), not the self-report: `types.ts`, `api.ts`,
> `useAnalyticsScope.ts`/`.test.ts`, `AnalyticsView.tsx`/`.test.tsx` all match the plan
> verbatim (only cosmetic line-wrap/typing-tightness diffs, no semantic deviation).
> `MobileAnalyticsView.tsx`/`.test.tsx` (not in this plan, added per the corrected
> remaining-work prompt) correctly reuse the same `useAnalyticsScope` hook rather than
> duplicating polling logic, adapted to the mobile view's `memberId?: string | null`
> prop shape. Independently ran `npx tsc -b --noEmit` myself — clean. Independently ran
> the full frontend suite myself (not the pasted self-report) — first pass returned
> 73/406 with 3 files failing to start (`vitest-pool-runner` worker-timeout, an
> infra/WSL flake given the abnormal 400s+ setup/import durations, not a test
> failure); re-ran those 3 files individually and they all passed, confirming the full
> suite is genuinely 76 files / 412 tests passing. `get_fund_score` fate confirmed
> unchanged and correct: still only called from `FundScoreDetailModal.tsx`, synchronous
> on-demand by original design. Zero findings.

**Goal:** Migrate the Analytics dashboard frontend off the 14 deleted per-section REST
routes onto the new consolidated precompute contract (`GET /analytics/{scope}`,
`POST /analytics/{scope}/retry`), so the dashboard renders real data instead of 404ing,
including correct handling of the backend's cold-start/background-recompute semantics
(polling) and permanently-failed sections (retry UI). Zero backend changes.

**Architecture:** One new hook, `useAnalyticsScope(scope)`, owns fetching + polling
against the single consolidated endpoint and exposes a flat `sections` map plus derived
status flags. `AnalyticsView.tsx` becomes a pure consumer of that hook: it unwraps each
of the 7 section payloads into the exact same typed shapes the section components
(`AllocationSection`, `TerSection`, etc.) already expect, so **zero section-component
prop changes are needed anywhere in this plan** — the backend was built so each
section's stored `payload` is byte-for-byte identical to what the old per-section route
used to return (verified against `backend/app/services/analytics/recompute.py`'s
`_SECTIONS` combined-wrap lambdas). `api.ts` shrinks from 14 fetch functions to 2, plus
the 3 unrelated ones (`getFundScore`, `postExportPdf`, `getExportPayload`) that are
untouched by this migration.

**Tech Stack:** React 18 (hooks only, no new deps), TypeScript, Vitest +
`@testing-library/react` (pattern precedent: `frontend/src/features/auth/useOAuthScript.ts`
+ its test — same polling-free custom-hook shape, reused here for the fake-timer polling
tests), existing `apiClient.ts`/`cachedFetch`/`ApiError` plumbing (unchanged).

**Spec:** No separate spec doc — this is a Bounded-path migration of an existing,
already-built backend contract. The contract itself is defined by
`backend/app/api/analytics.py`, `backend/app/services/analytics/schemas.py`, and
`backend/app/services/analytics/recompute.py` (all already implemented and merged in
this worktree), and narrated in `Docs/orchestration/analytics-precompute-implementation-handoff.md`
(Status: DONE) and `Docs/superpowers/plans/2026-09-02-analytics-precompute-architecture.md`.

## Global Constraints

- Never introduce a `float` on any money, NAV, or percentage-bearing value — every
  number that reaches a section component must stay a `string` exactly as the backend
  serialized it (this plan only moves data between layers, never recomputes it, so this
  should never come up, but any code review must check for it — this is this project's
  #1 non-negotiable per `AGENTS.md`).
- No section component (`AllocationSection.tsx`, `TerSection.tsx`,
  `CategoryRankingSection.tsx`, `ScorerSection.tsx`, `BenchmarkSection.tsx`,
  `FundScoreDetailModal.tsx`) changes props or behavior in this plan. If a task appears
  to require one, stop and flag it — that means a payload-shape assumption above was
  wrong, not that the component needs updating.
- The PDF export path (`postExportPdf`, `getExportPayload`,
  `print/PrintAnalyticsView.tsx`, `AnalyticsExportPayload`) is unaffected by this
  migration — it already consumes locally-assembled typed values, not raw fetch
  responses — and must not be touched except where `AnalyticsView.tsx` sources those
  typed values (Task 4).
- `tsc -b --noEmit` and `npm run test` (Vitest) must both be clean before any task is
  considered complete, and again at the end of the whole plan.
- ECS/EventBridge AWS infra (the actual dispatch target `dispatcher.dispatch()` talks
  to) is explicitly **out of scope** for this plan — it's being built in a separate,
  parallel track. Nothing in this plan blocks on it: in any environment where it isn't
  configured yet, `GET /analytics/{scope}` still returns correctly (empty sections,
  `recomputing: true` forever, per `backend/app/services/analytics/dispatch.py`'s
  documented no-op behavior) and the polling UI added in Task 3 will simply show
  "computing" indefinitely rather than erroring — this is expected staging behavior
  until that track lands, not a bug in this plan.
- Mandatory adversarial-review gate (per the `model-orchestration` skill) before Task 8
  is marked done — see Task 8.

---

### Task 1: Add the new response contract types

**Files:**
- Modify: `frontend/src/features/analytics/types.ts`

**Interfaces:**
- Produces: `AnalyticsSectionName` (the 7 literal section-key strings), `ANALYTICS_SECTION_NAMES`
  (runtime array of the same, used by every later task to iterate all 7 sections),
  `AnalyticsSectionState`, `AnalyticsScopeResponse`, `AnalyticsRetryResponse`.

These mirror `backend/app/services/analytics/schemas.py`'s `AnalyticsSectionState`
(`payload: dict | None`, `computed_at`, `failed_at`) and `AnalyticsScopeResponse`
(`scope: str`, `recomputing: bool`, `sections: dict[str, AnalyticsSectionState]`) exactly,
and the 7 keys come from `recompute.py`'s `_SECTIONS` list (`allocation`, `ter`,
`ter_direct_regular`, `benchmark`, `benchmark_funds`, `category_ranking`, `score`).

- [ ] **Step 1: Add the types**

Append to `frontend/src/features/analytics/types.ts` (after the existing
`AnalyticsExportPayload` interface, end of file):

```ts
/* Consolidated precompute contract (backend/app/services/analytics/schemas.py) */
export const ANALYTICS_SECTION_NAMES = [
  "allocation",
  "ter",
  "ter_direct_regular",
  "benchmark",
  "benchmark_funds",
  "category_ranking",
  "score",
] as const;

export type AnalyticsSectionName = (typeof ANALYTICS_SECTION_NAMES)[number];

export interface AnalyticsSectionState {
  payload: Record<string, unknown> | null;
  computed_at: string | null;
  failed_at: string | null;
}

export interface AnalyticsScopeResponse {
  scope: string;
  recomputing: boolean;
  sections: Partial<Record<AnalyticsSectionName, AnalyticsSectionState>>;
}

export interface AnalyticsRetryResponse {
  dispatched: boolean;
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no new errors (nothing imports these yet, so this only checks the file itself
is syntactically/typologically valid).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/analytics/types.ts
git commit -m "feat(analytics): add consolidated precompute response types"
```

---

### Task 2: Replace `api.ts`'s 14 per-section functions with the 2 consolidated ones

**Files:**
- Modify: `frontend/src/features/analytics/api.ts`
- Modify: `frontend/src/features/analytics/api.test.ts`

**Interfaces:**
- Consumes: `AnalyticsScopeResponse`, `AnalyticsRetryResponse` from Task 1.
- Produces: `getAnalyticsScope(scope: string, signal?: AbortSignal): Promise<AnalyticsScopeResponse>`,
  `retryAnalyticsScope(scope: string): Promise<AnalyticsRetryResponse>` — Task 3's hook is
  the sole caller of both. `getFundScore`, `postExportPdf`, `getExportPayload` keep their
  exact existing signatures unchanged — `FundScoreDetailModal.tsx` and
  `AnalyticsView.tsx`'s export flow keep working with zero changes on their end.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `frontend/src/features/analytics/api.test.ts` with:

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { getAnalyticsScope, retryAnalyticsScope, postExportPdf, getExportPayload } from "./api";
import * as session from "../auth/session";

describe("getAnalyticsScope", () => {
  beforeEach(() => {
    vi.spyOn(session, "getToken").mockReturnValue("session-tok");
  });

  it("GETs /analytics/{scope} with the bearer token and an abort signal", async () => {
    const body = { scope: "combined", recomputing: false, sections: {} };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(body) }),
    );
    const controller = new AbortController();
    const result = await getAnalyticsScope("combined", controller.signal);
    expect(result).toEqual(body);
    const [url, options] = (fetch as any).mock.calls[0];
    expect(url).toContain("/analytics/combined");
    expect(options.headers.get("Authorization")).toBe("Bearer session-tok");
    expect(options.signal).toBe(controller.signal);
  });

  it("works with a member-id scope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ scope: "m-1", recomputing: false, sections: {} }),
      }),
    );
    await getAnalyticsScope("m-1");
    const [url] = (fetch as any).mock.calls[0];
    expect(url).toContain("/analytics/m-1");
  });

  it("throws ApiError on a non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: "Household member not found." }),
      }),
    );
    await expect(getAnalyticsScope("bad-scope")).rejects.toThrow();
  });
});

describe("retryAnalyticsScope", () => {
  beforeEach(() => {
    vi.spyOn(session, "getToken").mockReturnValue("session-tok");
  });

  it("POSTs /analytics/{scope}/retry with the bearer token", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ dispatched: true }) }),
    );
    const result = await retryAnalyticsScope("combined");
    expect(result).toEqual({ dispatched: true });
    const [url, options] = (fetch as any).mock.calls[0];
    expect(url).toContain("/analytics/combined/retry");
    expect(options.method).toBe("POST");
    expect(options.headers.get("Authorization")).toBe("Bearer session-tok");
  });
});

describe("postExportPdf", () => {
  beforeEach(() => {
    vi.spyOn(session, "getToken").mockReturnValue("session-tok");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(new Blob(["%PDF-1.4"], { type: "application/pdf" })),
      }),
    );
  });

  it("POSTs the payload with the session bearer token and returns a Blob", async () => {
    const payload = { scopeName: "Family Aggregate" } as any;
    const blob = await postExportPdf({ scope: "aggregate", memberId: null, payload });
    expect(blob).toBeInstanceOf(Blob);
    const [, options] = (fetch as any).mock.calls[0];
    expect(options.method).toBe("POST");
    expect(options.headers.get("Authorization")).toBe("Bearer session-tok");
    expect(JSON.parse(options.body)).toEqual({ scope: "aggregate", member_id: null, payload });
  });
});

describe("getExportPayload", () => {
  it("GETs the payload by token with no Authorization header", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ scopeName: "Family Aggregate" }),
      }),
    );
    const result = await getExportPayload("tok-123");
    expect(result).toEqual({ scopeName: "Family Aggregate" });
    const [url, options] = (fetch as any).mock.calls[0];
    expect(url).toContain("/analytics/export/payload/tok-123");
    expect(options?.headers).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/analytics/api.test.ts`
Expected: FAIL — `getAnalyticsScope`/`retryAnalyticsScope` don't exist in `./api` yet.

- [ ] **Step 3: Rewrite `api.ts`**

Replace the entire contents of `frontend/src/features/analytics/api.ts` with:

```ts
import { API_BASE_URL, ApiError, cachedFetch, parseErrorDetail } from "../../lib/apiClient";
import { getToken } from "../auth/session";
import type {
  AnalyticsExportPayload,
  AnalyticsRetryResponse,
  AnalyticsScopeResponse,
  FundScoreRow,
} from "./types";

async function authFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await cachedFetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const errorPayload = await parseErrorDetail(res);
    throw new ApiError(res.status, errorPayload);
  }

  return res;
}

/* Consolidated precompute contract -- one snapshot per scope ("combined" or a
 * household member id). The backend dispatches its own recompute on a cold-start
 * GET; callers must poll (see useAnalyticsScope.ts), not treat this as one-shot. */
export async function getAnalyticsScope(scope: string, signal?: AbortSignal): Promise<AnalyticsScopeResponse> {
  const res = await authFetch(`/analytics/${scope}`, { signal });
  return res.json();
}

export async function retryAnalyticsScope(scope: string): Promise<AnalyticsRetryResponse> {
  const res = await authFetch(`/analytics/${scope}/retry`, { method: "POST" });
  return res.json();
}

/* Scorer (FR-5/FR-6/FR-7) -- single-fund lookup for the S20 detail modal; not part
 * of the scope snapshot above, fetched on demand when a fund row is clicked. */
export async function getFundScore(schemeId: string): Promise<FundScoreRow> {
  const res = await authFetch(`/analytics/funds/${schemeId}/score`);
  return res.json();
}

/* PDF Export (FR-12) */
export async function postExportPdf(request: {
  scope: "aggregate" | "member";
  memberId: string | null;
  payload: AnalyticsExportPayload;
}): Promise<Blob> {
  const res = await authFetch(`/analytics/export/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scope: request.scope, member_id: request.memberId, payload: request.payload }),
  });
  return res.blob();
}

// Deliberately NOT authFetch: the headless print route has no session bearer
// token available to it -- this endpoint is gated by possession of the opaque,
// single-use `token` itself (see the backend design spec's "Auth" section).
export async function getExportPayload(token: string): Promise<AnalyticsExportPayload> {
  const res = await fetch(`${API_BASE_URL}/analytics/export/payload/${token}`);
  if (!res.ok) {
    const errorPayload = await parseErrorDetail(res);
    throw new ApiError(res.status, errorPayload);
  }
  return res.json();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/analytics/api.test.ts`
Expected: PASS, all cases.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/analytics/api.ts frontend/src/features/analytics/api.test.ts
git commit -m "feat(analytics): replace 14 per-section fetches with the consolidated scope/retry endpoints"
```

---

### Task 3: Build the `useAnalyticsScope` polling hook

This is the only genuinely new logic in this plan — polling-against-a-real-backend-status
has no precedent elsewhere in this codebase (`ParsingIndicator.tsx`'s `setInterval` is a
cosmetic fake-progress simulator only), so it's built and tested in isolation here before
`AnalyticsView.tsx` (Task 4) is touched at all.

**Files:**
- Create: `frontend/src/features/analytics/useAnalyticsScope.ts`
- Create: `frontend/src/features/analytics/useAnalyticsScope.test.ts`

**Interfaces:**
- Consumes: `getAnalyticsScope`, `retryAnalyticsScope` (Task 2); `ANALYTICS_SECTION_NAMES`,
  `AnalyticsSectionName`, `AnalyticsSectionState` (Task 1).
- Produces: `useAnalyticsScope(scope: string | null): UseAnalyticsScopeResult` and the
  exported helper `isSectionSettled(state)`, both consumed by Task 4.
  `UseAnalyticsScopeResult = { sections, recomputing, fetchError, hasFailedSection, isRetrying, retry }`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/features/analytics/useAnalyticsScope.test.ts`:

```ts
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAnalyticsScope } from "./useAnalyticsScope";
import * as api from "./api";

vi.mock("./api");

const settledSections = {
  allocation: { payload: { total_value: "100" }, computed_at: "2026-09-01T00:00:00Z", failed_at: null },
  ter: { payload: {}, computed_at: "2026-09-01T00:00:00Z", failed_at: null },
  ter_direct_regular: { payload: {}, computed_at: "2026-09-01T00:00:00Z", failed_at: null },
  benchmark: { payload: {}, computed_at: "2026-09-01T00:00:00Z", failed_at: null },
  benchmark_funds: { payload: {}, computed_at: "2026-09-01T00:00:00Z", failed_at: null },
  category_ranking: { payload: {}, computed_at: "2026-09-01T00:00:00Z", failed_at: null },
  score: { payload: {}, computed_at: "2026-09-01T00:00:00Z", failed_at: null },
};

const coldStartSections = {
  ...settledSections,
  score: { payload: null, computed_at: null, failed_at: null },
};

describe("useAnalyticsScope", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("does nothing and fetches nothing when scope is null", () => {
    const { result } = renderHook(() => useAnalyticsScope(null));
    expect(result.current.sections).toEqual({});
    expect(api.getAnalyticsScope).not.toHaveBeenCalled();
  });

  it("fetches once and stops polling once every section is settled and not recomputing", async () => {
    vi.mocked(api.getAnalyticsScope).mockResolvedValue({
      scope: "combined",
      recomputing: false,
      sections: settledSections,
    });

    renderHook(() => useAnalyticsScope("combined"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(api.getAnalyticsScope).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(api.getAnalyticsScope).toHaveBeenCalledTimes(1);
  });

  it("keeps polling every 3s while a section hasn't settled yet, then stops", async () => {
    vi.mocked(api.getAnalyticsScope)
      .mockResolvedValueOnce({ scope: "combined", recomputing: true, sections: coldStartSections })
      .mockResolvedValueOnce({ scope: "combined", recomputing: false, sections: settledSections });

    const { result } = renderHook(() => useAnalyticsScope("combined"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(api.getAnalyticsScope).toHaveBeenCalledTimes(1);
    expect(result.current.recomputing).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(api.getAnalyticsScope).toHaveBeenCalledTimes(2);
    expect(result.current.recomputing).toBe(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(api.getAnalyticsScope).toHaveBeenCalledTimes(2);
  });

  it("sets fetchError and stops polling on a rejected fetch", async () => {
    vi.mocked(api.getAnalyticsScope).mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() => useAnalyticsScope("combined"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.fetchError).toBe("boom");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(api.getAnalyticsScope).toHaveBeenCalledTimes(1);
  });

  it("reports hasFailedSection when any section has failed_at set", async () => {
    const failedSections = {
      ...settledSections,
      score: { payload: null, computed_at: null, failed_at: "2026-09-01T00:00:00Z" },
    };
    vi.mocked(api.getAnalyticsScope).mockResolvedValue({
      scope: "combined",
      recomputing: false,
      sections: failedSections,
    });

    const { result } = renderHook(() => useAnalyticsScope("combined"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.hasFailedSection).toBe(true);
  });

  it("restarts polling when retry() is called", async () => {
    const failedSections = {
      ...settledSections,
      score: { payload: null, computed_at: null, failed_at: "2026-09-01T00:00:00Z" },
    };
    vi.mocked(api.getAnalyticsScope)
      .mockResolvedValueOnce({ scope: "combined", recomputing: false, sections: failedSections })
      .mockResolvedValueOnce({ scope: "combined", recomputing: false, sections: settledSections });
    vi.mocked(api.retryAnalyticsScope).mockResolvedValue({ dispatched: true });

    const { result } = renderHook(() => useAnalyticsScope("combined"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(api.getAnalyticsScope).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.retry();
    });
    expect(api.retryAnalyticsScope).toHaveBeenCalledWith("combined");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(api.getAnalyticsScope).toHaveBeenCalledTimes(2);
  });

  it("aborts the in-flight request when the hook unmounts", async () => {
    let observedSignal: AbortSignal | undefined;
    vi.mocked(api.getAnalyticsScope).mockImplementation((_scope: string, signal?: AbortSignal) => {
      observedSignal = signal;
      return new Promise(() => {});
    });

    const { unmount } = renderHook(() => useAnalyticsScope("combined"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    unmount();

    expect(observedSignal?.aborted).toBe(true);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/analytics/useAnalyticsScope.test.ts`
Expected: FAIL — `useAnalyticsScope.ts` doesn't exist yet.

- [ ] **Step 3: Implement the hook**

Create `frontend/src/features/analytics/useAnalyticsScope.ts`:

```ts
import { useCallback, useEffect, useState } from "react";
import { getAnalyticsScope, retryAnalyticsScope } from "./api";
import { ANALYTICS_SECTION_NAMES } from "./types";
import type { AnalyticsSectionName, AnalyticsSectionState } from "./types";

const POLL_INTERVAL_MS = 3000;

export function isSectionSettled(state: AnalyticsSectionState | undefined): boolean {
  return !!state && (state.payload !== null || state.failed_at !== null);
}

export interface UseAnalyticsScopeResult {
  sections: Partial<Record<AnalyticsSectionName, AnalyticsSectionState>>;
  recomputing: boolean;
  fetchError: string | null;
  hasFailedSection: boolean;
  isRetrying: boolean;
  retry: () => Promise<void>;
}

/** Polls GET /analytics/{scope} until every section has settled (a payload landed
 * or it permanently failed) and the backend reports it's done recomputing -- the
 * precompute backend answers a cold-start GET with whatever has landed so far, not
 * a single blocking response (Docs/orchestration/analytics-precompute-implementation-handoff.md).
 * `scope` is "combined" for the household aggregate or a household member's id;
 * pass null when there's nothing to fetch yet (e.g. member mode with no member
 * selected) -- the hook is then a no-op, matching the old per-section fetch's
 * early-return behavior. */
export function useAnalyticsScope(scope: string | null): UseAnalyticsScopeResult {
  const [sections, setSections] = useState<Partial<Record<AnalyticsSectionName, AnalyticsSectionState>>>({});
  const [recomputing, setRecomputing] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);
  const [pollGeneration, setPollGeneration] = useState(0);

  useEffect(() => {
    if (!scope) {
      setSections({});
      setFetchError(null);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();

    const poll = () => {
      getAnalyticsScope(scope, controller.signal)
        .then((res) => {
          if (cancelled) return;
          setSections(res.sections);
          setRecomputing(res.recomputing);
          setFetchError(null);
          const allSettled = ANALYTICS_SECTION_NAMES.every((name) => isSectionSettled(res.sections[name]));
          if (res.recomputing || !allSettled) {
            timer = setTimeout(poll, POLL_INTERVAL_MS);
          }
        })
        .catch((err: any) => {
          if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
          setFetchError(err.message || "Failed to load analytics data");
        });
    };

    setFetchError(null);
    poll();

    return () => {
      cancelled = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [scope, pollGeneration]);

  const retry = useCallback(async () => {
    if (!scope) return;
    setIsRetrying(true);
    try {
      await retryAnalyticsScope(scope);
    } finally {
      setIsRetrying(false);
      // Bumping this re-runs the effect above with a fresh AbortController and
      // restarts the poll loop, whether the prior loop had already stopped
      // (all sections settled, one or more failed) or was still running.
      setPollGeneration((g) => g + 1);
    }
  }, [scope]);

  const hasFailedSection = ANALYTICS_SECTION_NAMES.some((name) => !!sections[name]?.failed_at);

  return { sections, recomputing, fetchError, hasFailedSection, isRetrying, retry };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/analytics/useAnalyticsScope.test.ts`
Expected: PASS, all 7 cases. If `vi.advanceTimersByTimeAsync` isn't recognized, confirm
`@testing-library/react`'s `renderHook`/`act` are imported (not React's raw `act`) and
that `vi.useFakeTimers()` is called before `renderHook` — Vitest 4's modern fake timers
support this API out of the box, no extra config needed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/analytics/useAnalyticsScope.ts frontend/src/features/analytics/useAnalyticsScope.test.ts
git commit -m "feat(analytics): add useAnalyticsScope polling hook for the consolidated precompute contract"
```

---

### Task 4: Rewrite `AnalyticsView.tsx` to consume the hook

**Files:**
- Modify: `frontend/src/features/analytics/AnalyticsView.tsx`

**Interfaces:**
- Consumes: `useAnalyticsScope`, `isSectionSettled` (Task 3); `ANALYTICS_SECTION_NAMES`,
  `AnalyticsSectionName` (Task 1); `postExportPdf` (Task 2, unchanged signature).
  Section component props (`AllocationSection`, `TerSection`, `CategoryRankingSection`,
  `ScorerSection`, `BenchmarkSection`, `FundScoreDetailModal`) are **unchanged** —
  confirm this by not touching any of those 6 files in this task.
- Produces: the same `AnalyticsViewProps` public interface as before (no caller of
  `AnalyticsView` needs to change).

**Key mapping (why `unwrap` looks up a different field per section):** each section's
stored `payload`, for the `"combined"` (aggregate) scope, is the *old* `Aggregate*Response`
shape wrapping `{ members, <field> }` — and `<field>`'s name differs per section (verified
against `recompute.py`'s `_SECTIONS` combined-wrap lambdas):

| section name         | combined-scope field | member-scope shape                  |
|-----------------------|----------------------|--------------------------------------|
| `allocation`           | `allocation`          | bare `AnalyticsAllocationSummary`     |
| `ter`                  | `ter`                 | bare `WeightedTerSummary`             |
| `ter_direct_regular`   | `ter`                 | bare `DirectRegularTerComparison`     |
| `benchmark`            | `benchmark`           | bare `PortfolioBenchmarkSummary`      |
| `benchmark_funds`      | `comparison`          | bare `FundVsBenchmarkSummary`         |
| `category_ranking`     | `ranking`              | bare `CategoryRankingSummary`         |
| `score`                | `score`               | bare `PortfolioScoreSummary`          |

For a member scope, `payload` IS the bare summary directly (no wrapper) — this is why
`unwrap` below branches on `isAggregate`.

**Behavior change to flag explicitly (not a bug):** previously, only the allocation
fetch's rejection triggered the full-page error state; the other 4 sections' fetch
rejections were caught and just logged, leaving that section's local state `null`. Under
the new single-GET contract there is one shared request per scope, so a *transport-level*
failure (`fetchError` from the hook — auth/network problem) now blocks the whole page,
which is correct and unavoidable (there's only one request now). A *per-section compute*
failure (`failed_at` set on one row) does **not** block the page — that section simply
shows its own existing empty state (same visual as "no data yet" today), and the new
retry banner (this task) surfaces it. This is a more consistent model than the old
allocation-is-special-cased behavior, not a regression.

- [ ] **Step 1: Update `AnalyticsView.test.tsx` first (TDD — write the target test, then make it pass)**

Replace the entire contents of `frontend/src/features/analytics/AnalyticsView.test.tsx`
with:

```tsx
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { AnalyticsView } from "./AnalyticsView";
import * as api from "./api";
import type { MemberStatus } from "./types";

vi.mock("./api");

const sampleAllocationSummary = {
  by_category: [
    { label: "Flexi Cap", current_value: "100000", percentage: "60.0" },
    { label: "Large Cap", current_value: "66666.67", percentage: "40.0" },
  ],
  by_amc: [
    { label: "Parag Parikh Mutual Fund", current_value: "100000", percentage: "60.0" },
    { label: "HDFC Mutual Fund", current_value: "66666.67", percentage: "40.0" },
  ],
  total_value: "166666.67",
};

const sampleTerSummary = {
  weighted_ter: "0.85",
  covered_value: "166666.67",
  total_value: "166666.67",
  reference_period: "2026-07-31",
  uncovered_schemes: [],
};

const sampleDirectRegularComparison = {
  direct: { weighted_ter: "0.65", covered_value: "100000", total_value: "100000", reference_period: "2026-07-31", uncovered_schemes: [] },
  regular: { weighted_ter: "1.15", covered_value: "66666.67", total_value: "66666.67", reference_period: "2026-07-31", uncovered_schemes: [] },
};

const sampleCategoryRanking = {
  funds: [
    { scheme_id: "scheme-1", scheme_name: "Parag Parikh Flexi Cap Fund - Direct Plan", sebi_category: "Flexi Cap Fund", category_unavailable: false, insufficient_history: false, scheme_return: "18.45", category_rank: 3, category_size: 42, percentile: "92.8", category_avg_return: "14.20", thin_category: false },
    { scheme_id: "scheme-2", scheme_name: "Old Legacy Fund", sebi_category: null, category_unavailable: true, insufficient_history: false, scheme_return: null, category_rank: null, category_size: 0, percentile: null, category_avg_return: null, thin_category: false },
  ],
};

const sampleScoreSummary = {
  funds: [
    { scheme_id: "scheme-1", scheme_name: "Parag Parikh Flexi Cap Fund - Direct Plan", category_unavailable: false, insufficient_history: false, thin_category: false, risk_adjusted_tier: 5, cost_adjustment: "0.25", final_score: "85.5", return_percentile: "88.0", risk_percentile: "82.0", consistency_hit_rate: "80.0" },
  ],
  weighted_score: "85.5",
  covered_value: "166666.67",
  total_value: "166666.67",
  uncovered_schemes: [],
};

const samplePortfolioBenchmark = {
  portfolio_xirr: "0.1645",
  benchmarks: [
    { index: "nifty_50" as const, xirr: "0.1230" },
    { index: "nifty_500" as const, xirr: "0.1410" },
    { index: "nifty_largemidcap_250" as const, xirr: "0.1500" },
    { index: "nifty_midcap_150" as const, xirr: "0.1720" },
  ],
};

const sampleFundBenchmark = {
  funds: [
    { scheme_id: "scheme-1", scheme_name: "Parag Parikh Flexi Cap Fund - Direct Plan", benchmark_index: "nifty_500" as const, fund_xirr: "0.1845", benchmark_xirr: "0.1410" },
  ],
  overall_portfolio_xirr: "0.1645",
  overall_broad_market_xirr: "0.1410",
};

function settled(payload: unknown, failedAt: string | null = null) {
  return { payload: failedAt ? null : payload, computed_at: failedAt ? null : "2026-09-01T00:00:00Z", failed_at: failedAt };
}

function buildSections(isAggregate: boolean, members: MemberStatus[] = []) {
  const wrap = (field: string, value: unknown) => (isAggregate ? { members, [field]: value } : value);
  return {
    allocation: settled(wrap("allocation", sampleAllocationSummary)),
    ter: settled(wrap("ter", sampleTerSummary)),
    ter_direct_regular: settled(wrap("ter", sampleDirectRegularComparison)),
    category_ranking: settled(wrap("ranking", sampleCategoryRanking)),
    score: settled(wrap("score", sampleScoreSummary)),
    benchmark: settled(wrap("benchmark", samplePortfolioBenchmark)),
    benchmark_funds: settled(wrap("comparison", sampleFundBenchmark)),
  };
}

describe("AnalyticsView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches and renders all 5 analytics sections for aggregate view", async () => {
    vi.mocked(api.getAnalyticsScope).mockResolvedValue({
      scope: "combined",
      recomputing: false,
      sections: buildSections(true, [
        { id: "m-1", name: "Alice", has_data: true },
        { id: "m-2", name: "Bob", has_data: false },
      ]),
    });

    render(<AnalyticsView viewMode="aggregate" memberId={null} />);

    expect(screen.getByText("Analytics & Portfolio Performance Dashboard")).toBeInTheDocument();
    expect(api.getAnalyticsScope).toHaveBeenCalledWith("combined", expect.any(AbortSignal));

    await waitFor(() => {
      expect(screen.getByText("Portfolio Allocation")).toBeInTheDocument();
      expect(screen.getByText("Total Expense Ratio (TER) & Cost Analysis")).toBeInTheDocument();
      expect(screen.getByText("SEBI Category Ranking & Peer Comparison")).toBeInTheDocument();
      expect(screen.getByText("Fund Quality Scorer & Composite Ratings")).toBeInTheDocument();
      expect(screen.getByText("Benchmark Comparison (XIRR)")).toBeInTheDocument();
    });

    expect(screen.getByText("0.85%")).toBeInTheDocument();
    expect(screen.getByText(/Bob/)).toBeInTheDocument();
  });

  it("fetches and renders per-member analytics data for all 5 sections", async () => {
    vi.mocked(api.getAnalyticsScope).mockResolvedValue({
      scope: "m-1",
      recomputing: false,
      sections: buildSections(false),
    });

    render(<AnalyticsView viewMode="member" memberId="m-1" />);

    await waitFor(() => {
      expect(api.getAnalyticsScope).toHaveBeenCalledWith("m-1", expect.any(AbortSignal));
      expect(screen.getByText("Flexi Cap")).toBeInTheDocument();
    });
  });

  it("does not fetch when in member mode with no member selected", () => {
    render(<AnalyticsView viewMode="member" memberId={null} />);
    expect(api.getAnalyticsScope).not.toHaveBeenCalled();
  });

  it("opens S20 score modal when fund score row is clicked", async () => {
    vi.mocked(api.getAnalyticsScope).mockResolvedValue({
      scope: "combined",
      recomputing: false,
      sections: buildSections(true, [{ id: "m-1", name: "Alice", has_data: true }]),
    });
    vi.mocked(api.getFundScore).mockResolvedValue(sampleScoreSummary.funds[0]);

    render(<AnalyticsView viewMode="aggregate" memberId={null} />);

    await waitFor(() => {
      expect(screen.getByText("Fund Quality Scorer & Composite Ratings")).toBeInTheDocument();
    });

    const scoreRowMatches = screen.getAllByText("Parag Parikh Flexi Cap Fund - Direct Plan");
    fireEvent.click(scoreRowMatches[scoreRowMatches.length - 1]);

    await waitFor(() => {
      expect(screen.getByText("S20 · Unifolio Fund Score")).toBeInTheDocument();
    });
  });

  it("renders error boundary when the scope fetch fails", async () => {
    vi.mocked(api.getAnalyticsScope).mockRejectedValue(new Error("Network Error"));

    render(<AnalyticsView viewMode="aggregate" memberId={null} />);

    await waitFor(() => {
      expect(screen.getByText("Unable to load Analytics Dashboard")).toBeInTheDocument();
      expect(screen.getByText("Network Error")).toBeInTheDocument();
    });
  });

  it("aborts the analytics request when the view unmounts", async () => {
    let observedSignal: AbortSignal | undefined;
    vi.mocked(api.getAnalyticsScope).mockImplementation((_scope: string, signal?: AbortSignal) => {
      observedSignal = signal;
      return new Promise(() => {});
    });

    const { unmount } = render(<AnalyticsView viewMode="aggregate" memberId={null} />);
    unmount();

    expect(observedSignal?.aborted).toBe(true);
  });

  it("disables the Download PDF button while any section is still loading", () => {
    vi.mocked(api.getAnalyticsScope).mockImplementation(() => new Promise(() => {}));
    render(<AnalyticsView viewMode="aggregate" memberId={null} />);
    const button = screen.getByRole("button", { name: /download pdf/i });
    expect(button).toBeDisabled();
  });

  it("enables Download PDF once all sections have settled, and posts the assembled payload", async () => {
    vi.mocked(api.getAnalyticsScope).mockResolvedValue({
      scope: "combined",
      recomputing: false,
      sections: buildSections(true, []),
    });
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });
    vi.mocked(api.postExportPdf).mockResolvedValue(blob);
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:fake"), revokeObjectURL: vi.fn() });

    render(<AnalyticsView viewMode="aggregate" memberId={null} />);
    const button = await screen.findByRole("button", { name: /download pdf/i });
    await waitFor(() => expect(button).toBeEnabled());

    fireEvent.click(button);

    await waitFor(() => expect(api.postExportPdf).toHaveBeenCalledTimes(1));
    const call = vi.mocked(api.postExportPdf).mock.calls[0][0];
    expect(call.scope).toBe("aggregate");
    expect(call.payload.scopeName).toBe("Family Aggregate");
  });

  it("shows a retry banner when a section has permanently failed, and re-fetches on click", async () => {
    const sectionsWithFailure = { ...buildSections(true, []), score: settled(null, "2026-09-01T00:00:00Z") };
    vi.mocked(api.getAnalyticsScope).mockResolvedValue({
      scope: "combined",
      recomputing: false,
      sections: sectionsWithFailure,
    });
    vi.mocked(api.retryAnalyticsScope).mockResolvedValue({ dispatched: true });

    render(<AnalyticsView viewMode="aggregate" memberId={null} />);

    const retryButton = await screen.findByRole("button", { name: /retry/i });
    fireEvent.click(retryButton);

    await waitFor(() => expect(api.retryAnalyticsScope).toHaveBeenCalledWith("combined"));
    await waitFor(() => expect(api.getAnalyticsScope).toHaveBeenCalledTimes(2));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/analytics/AnalyticsView.test.tsx`
Expected: FAIL — `AnalyticsView.tsx` still imports the 14 deleted functions from `./api`
(compile error) or, if `api.ts` mocks resolve `undefined` for the old function names,
component logic errors.

- [ ] **Step 3: Rewrite `AnalyticsView.tsx`**

Replace the entire contents of `frontend/src/features/analytics/AnalyticsView.tsx` with:

```tsx
import { useState } from "react";
import { formatIndianCurrency } from "@/lib/decimal";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, RefreshCw, TrendingUp } from "lucide-react";
import { postExportPdf } from "./api";
import { isSectionSettled, useAnalyticsScope } from "./useAnalyticsScope";
import { AllocationSection } from "./AllocationSection";
import { TerSection } from "./TerSection";
import { CategoryRankingSection } from "./CategoryRankingSection";
import { ScorerSection } from "./ScorerSection";
import { BenchmarkSection } from "./BenchmarkSection";
import { FundScoreDetailModal } from "./FundScoreDetailModal";
import { ANALYTICS_SECTION_NAMES } from "./types";
import type {
  AnalyticsAllocationSummary,
  AnalyticsExportPayload,
  AnalyticsSectionName,
  CategoryRankingSummary,
  DirectRegularTerComparison,
  FundVsBenchmarkSummary,
  MemberStatus,
  PortfolioBenchmarkSummary,
  PortfolioScoreSummary,
  WeightedTerSummary,
} from "./types";

export interface AnalyticsViewProps {
  viewMode: "aggregate" | "member";
  memberId: string | null;
  onAddDataForMember?: (memberId?: string) => void;
  activeMemberName?: string;
}

// A combined-scope payload wraps each section's own field under this name
// (backend/app/services/analytics/recompute.py's _SECTIONS combined-wrap
// lambdas) -- a member scope's payload IS the bare summary, no wrapper. See
// this plan's Task 4 mapping table for why the field name differs per section.
const AGGREGATE_FIELD: Record<AnalyticsSectionName, string> = {
  allocation: "allocation",
  ter: "ter",
  ter_direct_regular: "ter",
  benchmark: "benchmark",
  benchmark_funds: "comparison",
  category_ranking: "ranking",
  score: "score",
};

export function AnalyticsView({
  viewMode,
  memberId,
  onAddDataForMember,
  activeMemberName,
}: AnalyticsViewProps) {
  const isAggregate = viewMode === "aggregate";
  const scope = isAggregate ? "combined" : memberId;
  const { sections, recomputing, fetchError, hasFailedSection, isRetrying, retry } = useAnalyticsScope(scope);

  function unwrap<T>(name: AnalyticsSectionName): T | null {
    const payload = sections[name]?.payload;
    if (!payload) return null;
    return (isAggregate ? (payload as Record<string, unknown>)[AGGREGATE_FIELD[name]] : payload) as T;
  }

  const allocation = unwrap<AnalyticsAllocationSummary>("allocation");
  const ter = unwrap<WeightedTerSummary>("ter");
  const terComparison = unwrap<DirectRegularTerComparison>("ter_direct_regular");
  const ranking = unwrap<CategoryRankingSummary>("category_ranking");
  const scoreSummary = unwrap<PortfolioScoreSummary>("score");
  const portfolioBenchmark = unwrap<PortfolioBenchmarkSummary>("benchmark");
  const fundBenchmark = unwrap<FundVsBenchmarkSummary>("benchmark_funds");
  const members: MemberStatus[] = isAggregate
    ? (((sections.allocation?.payload as Record<string, unknown> | undefined)?.members as MemberStatus[]) ?? [])
    : [];

  // !!scope guards match the old early-return behavior for "member mode, no
  // member selected yet": immediately not-loading, nothing to fetch.
  const allocationLoading = !!scope && !isSectionSettled(sections.allocation);
  const terLoading = !!scope && (!isSectionSettled(sections.ter) || !isSectionSettled(sections.ter_direct_regular));
  const rankingLoading = !!scope && !isSectionSettled(sections.category_ranking);
  const scoreLoading = !!scope && !isSectionSettled(sections.score);
  const benchmarkLoading =
    !!scope && (!isSectionSettled(sections.benchmark) || !isSectionSettled(sections.benchmark_funds));

  const allSectionsLoaded =
    !scope || (!recomputing && ANALYTICS_SECTION_NAMES.every((name) => isSectionSettled(sections[name])));

  // S20 Modal State
  const [selectedSchemeId, setSelectedSchemeId] = useState<string | null>(null);
  const [selectedSchemeName, setSelectedSchemeName] = useState<string | undefined>(undefined);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const handleDownloadPdf = async () => {
    setIsExporting(true);
    setExportError(null);
    try {
      const payload: AnalyticsExportPayload = {
        scopeName: isAggregate ? "Family Aggregate" : activeMemberName ?? "Member",
        allocation,
        ter,
        terComparison,
        ranking,
        scoreSummary,
        portfolioBenchmark,
        fundBenchmark,
      };
      const blob = await postExportPdf({ scope: viewMode, memberId, payload });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `unifolio-analytics-${isAggregate ? "family" : memberId}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setExportError(err.message || "Failed to generate PDF");
    } finally {
      setIsExporting(false);
    }
  };

  const handleOpenScoreModal = (schemeId: string, schemeName: string) => {
    setSelectedSchemeId(schemeId);
    setSelectedSchemeName(schemeName);
    setIsModalOpen(true);
  };

  const targetMemberPlaceholder = isAggregate ? members.find((m) => !m.has_data) : null;

  if (fetchError) {
    return (
      <div className="rounded-xl border border-[var(--color-negative)]/30 bg-[var(--color-negative)]/5 p-6 text-center space-y-3">
        <AlertCircle className="h-8 w-8 text-[var(--color-negative)] mx-auto" />
        <h2 className="font-display text-base font-bold text-[var(--color-ink)]">
          Unable to load Analytics Dashboard
        </h2>
        <p className="text-xs text-[var(--color-text-secondary)] max-w-md mx-auto">
          {fetchError}
        </p>
      </div>
    );
  }

  const totalValStr = allocation?.total_value || "0";

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* Hero Summary Header */}
      <Card className="p-6 sm:p-7 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xs relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
          <div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-[10px] border-[var(--color-border)] text-[var(--color-text-secondary)]">
                Phase 1 & 2 Active
              </Badge>
            </div>
            <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-[var(--color-ink)] mt-1">
              Analytics & Portfolio Performance Dashboard
            </h1>
            <p className="text-xs sm:text-sm text-[var(--color-text-secondary)] mt-1">
              Full 5-part depth: Allocation, TER Costs, SEBI Category Ranks, Quality Scorer & Benchmark Comparisons.
            </p>
          </div>

          <div className="flex items-center gap-4 bg-[var(--color-bg)]/80 p-4 rounded-xl border border-[var(--color-border)] self-start md:self-auto">
            <div>
              <span className="text-[11px] font-medium text-[var(--color-text-secondary)] block">
                Total Portfolio Value
              </span>
              {allocationLoading ? (
                <Skeleton className="h-7 w-32 mt-1" />
              ) : (
                <span className="font-display text-xl sm:text-2xl font-bold text-[var(--color-ink)] tabular-nums type-display">
                  ₹{formatIndianCurrency(totalValStr)}
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={handleDownloadPdf}
              disabled={!allSectionsLoaded || isExporting}
              className="text-xs font-semibold px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isExporting ? "Generating…" : "Download PDF"}
            </button>
          </div>
        </div>
        {exportError && (
          <p className="text-xs text-[var(--color-negative)] mt-3 relative z-10">{exportError}</p>
        )}
      </Card>

      {/* Aggregate Placeholder Notice */}
      {isAggregate && targetMemberPlaceholder && (
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <TrendingUp className="h-4 w-4 text-[var(--color-accent)] flex-shrink-0" />
            <p className="text-xs text-[var(--color-text-secondary)]">
              Family member <strong className="text-[var(--color-ink)]">{targetMemberPlaceholder.name}</strong> has no CAS holdings imported yet.
            </p>
          </div>
          {onAddDataForMember && (
            <button
              type="button"
              onClick={() => onAddDataForMember(targetMemberPlaceholder.id)}
              className="text-xs font-semibold text-[var(--color-accent)] hover:underline cursor-pointer self-start sm:self-auto"
            >
              + Add CAS for {targetMemberPlaceholder.name}
            </button>
          )}
        </div>
      )}

      {/* Failed-section retry banner -- no per-section retry exists on the
          backend, only a whole-scope one (POST /analytics/{scope}/retry) */}
      {hasFailedSection && (
        <div className="rounded-xl border border-[var(--color-negative)]/30 bg-[var(--color-negative)]/5 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <AlertCircle className="h-4 w-4 text-[var(--color-negative)] flex-shrink-0" />
            <p className="text-xs text-[var(--color-text-secondary)]">
              Some sections failed to compute.
            </p>
          </div>
          <button
            type="button"
            onClick={retry}
            disabled={isRetrying}
            className="text-xs font-semibold text-[var(--color-accent)] hover:underline cursor-pointer self-start sm:self-auto disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1.5"
          >
            <RefreshCw className="h-3 w-3" />
            {isRetrying ? "Retrying…" : "Retry"}
          </button>
        </div>
      )}

      {/* Section 1: Allocation */}
      <AllocationSection summary={allocation} isLoading={allocationLoading} />

      {/* Section 2: Cost / TER */}
      <TerSection ter={ter} comparison={terComparison} isLoading={terLoading} />

      {/* Section 3: Category Ranking */}
      <CategoryRankingSection ranking={ranking} isLoading={rankingLoading} />

      {/* Section 4: Fund & Portfolio Scorer (FR-5/FR-6/FR-7) */}
      <ScorerSection
        scoreSummary={scoreSummary}
        isLoading={scoreLoading}
        onSelectFundScore={handleOpenScoreModal}
      />

      {/* Section 5: Benchmark Comparison (FR-8/FR-9) */}
      <BenchmarkSection
        portfolioBenchmark={portfolioBenchmark}
        fundBenchmark={fundBenchmark}
        isLoading={benchmarkLoading}
      />

      {/* S20 Fund Score Detail Modal */}
      <FundScoreDetailModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        schemeId={selectedSchemeId}
        schemeName={selectedSchemeName}
        initialData={scoreSummary?.funds.find((f) => f.scheme_id === selectedSchemeId) ?? null}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/analytics/AnalyticsView.test.tsx`
Expected: PASS, all cases including the new retry-banner test.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/analytics/AnalyticsView.tsx frontend/src/features/analytics/AnalyticsView.test.tsx
git commit -m "feat(analytics): consume the consolidated precompute contract in AnalyticsView"
```

---

### Task 5: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Type-check the whole frontend**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: clean. If anything outside `features/analytics/` fails, it means something
still imports one of the 14 deleted `api.ts` functions — grep for it:

```bash
grep -rn "getMemberAllocation\|getAggregateAllocation\|getMemberTer\|getAggregateTer\|getMemberDirectRegularTer\|getAggregateDirectRegularTer\|getMemberCategoryRanking\|getAggregateCategoryRanking\|getMemberScore\|getAggregateScore\|getMemberBenchmark\|getAggregateBenchmark\|getMemberFundBenchmark\|getAggregateFundBenchmark" frontend/src --include="*.ts*"
```

Expected: no matches outside `node_modules`/build artifacts. (`print/PrintAnalyticsView.tsx`
and its test only use `getExportPayload`, unaffected — confirm they aren't in this list.)

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npm run test`
Expected: all tests pass, including the untouched `AllocationSection.test.tsx`,
`TerSection` (no dedicated test file today — skip), `CategoryRankingSection.test.tsx`,
`ScorerSection.test.tsx`, `BenchmarkSection.test.tsx`, `FundScoreCard.test.tsx`,
`FundScoreDetailModal.test.tsx`, `PrintAnalyticsView.test.tsx` — none of these should
need edits; if any fails, the section-component-prop-change guardrail in Global
Constraints was violated somewhere and must be fixed, not worked around.

- [ ] **Step 3: Run the backend test suite as a regression check**

Run: `cd backend && source .venv/bin/activate && pytest`
Expected: unaffected (this plan makes zero backend changes) — run anyway as a cheap
sanity check that nothing in the worktree was left in a broken state from prior work.

---

### Task 6: Manual smoke test against a running backend

This plan's automated tests use mocked fetches throughout — this task is the only place
real end-to-end wiring gets exercised, catching anything the mocks could paper over
(URL typos, header issues, actual JSON shape drift).

- [ ] **Step 1: Start the backend and frontend dev servers**

Follow this repo's existing local-dev setup (`AGENTS.md`'s setup commands) — typically:

```bash
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload &
cd frontend && npm run dev &
```

- [ ] **Step 2: Exercise the cold-start path**

Log in as a user with no `analytics_section` rows yet for at least one scope (a fresh
household member, or manually delete rows for an existing one). Open the Analytics tab.
Confirm: sections show their loading state, a network request to `GET /analytics/{scope}`
recurs roughly every 3s (check browser dev tools' Network tab), and each section
populates independently as its data lands — **unless** `ecs_cluster_arn`/
`ecs_task_definition_arn` are unset in this environment's `backend/app/config.py`
settings, in which case `recomputing` stays `true` forever and no section ever
populates from a cold start. This is expected per Global Constraints (the ECS/EventBridge
track isn't done yet) — if so, seed `AnalyticsSection` rows directly (or run
`backend/scripts/run_analytics_recompute.py --household <user-id>` once by hand) to
verify the warm-data rendering path instead.

- [ ] **Step 3: Exercise the warm path**

With `AnalyticsSection` rows already present (from Step 2 or seeded directly), reload
the Analytics tab. Confirm: all 5 sections render immediately with real numbers, no
visible flash of skeleton state, and polling stops (no more than one `GET
/analytics/{scope}` request fires, confirmed via the Network tab, since `recomputing`
should already be `false` and every section already settled).

- [ ] **Step 4: Exercise member-scope switching**

Switch between the aggregate view and at least two different household members using
the existing view-mode toggle. Confirm each switch fires exactly one new
`GET /analytics/{scope}` (or `GET /analytics/{member-uuid}`) and the previous scope's
in-flight request is aborted (Network tab shows it as "canceled" if you switch quickly).

- [ ] **Step 5: Exercise the retry banner**

Manually set one `AnalyticsSection` row's `failed_at` to a non-null timestamp (via a
direct DB update in the dev database) and reload. Confirm the retry banner renders,
clicking "Retry" fires `POST /analytics/{scope}/retry`, and polling resumes.

- [ ] **Step 6: Exercise PDF export**

With all sections settled, click "Download PDF." Confirm the button was disabled before
that point, a PDF downloads, and its content matches the on-screen values (this exercises
`postExportPdf`/`getExportPayload`/`PrintAnalyticsView.tsx`, unchanged by this plan but
worth confirming the locally-assembled `AnalyticsExportPayload` still has real values
now that it's sourced from `sections` instead of the old direct fetch results).

---

### Task 7: Update session/status docs

**Files:**
- Modify: `session.md` (repo root)
- Modify: `Docs/orchestration/delegation-log.md`

- [ ] **Step 1: Append one line to `delegation-log.md`** recording this task's
completion (worker=orchestrator, direct implementation — no Codex dispatch was used
for this plan since implementation happened directly in this session; the mandatory
review gate in Task 8 still applies).

- [ ] **Step 2: Update `session.md`'s "Still open" section** to remove the frontend
migration gap (previously flagged as "the Analytics dashboard 404s against the new
backend") and note it's resolved, pointing at this plan's file.

- [ ] **Step 3: Commit**

```bash
git add session.md Docs/orchestration/delegation-log.md
git commit -m "docs: record analytics frontend precompute migration completion"
```

---

### Task 8: Mandatory adversarial-review gate

Per the `model-orchestration` skill: before this plan is considered `DONE`, dispatch
`/codex:adversarial-review` against the full diff from Task 1 through Task 4 (the actual
code changes; Tasks 5-7 are verification/docs, not reviewable code). Do this via
`Agent(subagent_type: codex:codex-rescue, run_in_background: true, description: "...",
prompt: "run /codex:adversarial-review against <scope> and report verdict + findings")`
— never a direct Bash call, never with `isolation: "worktree"`.

- [ ] **Step 1: Dispatch the review**, scoped to the 4 touched/created files
(`types.ts`, `api.ts`, `useAnalyticsScope.ts`, `AnalyticsView.tsx`) plus their test
files.

- [ ] **Step 2: Triage findings** by severity per the skill's stopping heuristic — fix
directly (small diff, files already in context) or redelegate, per "Review-loop fix
authorship" in the skill.

- [ ] **Step 3: Re-review after any fix** (scoped re-review if the fix stayed within
the 4 files above; full fresh review if it touched anything else).

- [ ] **Step 4: Once PASS with zero findings**, mark this plan DONE in a final
`delegation-log.md` line, matching the pattern used to close the backend precompute
plan (`Docs/orchestration/analytics-precompute-implementation-handoff.md`).

---

### Task 9 (deferred, separate from this plan's completion): Merge into `feat/enhanced-ui`

Once Task 8 closes, this worktree's branch can be merged into `feat/enhanced-ui`
(the user's original, still-pending instruction). This is intentionally its own task,
not folded into Task 8, because:
- `feat/enhanced-ui` has continued accumulating unrelated in-progress work
  (`adr006-background-jobs-handoff.md`, `f8-nav-unavailable-degraded-row-handoff.md`,
  `non-pan-duplicate-person-detection-handoff.md`, dashboard/import/mobile frontend
  changes, `Scorer-v2` docs) since this worktree branched off it — a merge here needs a
  dedicated conflict-resolution pass, not a fold-in.
- Before merging, confirm `feat/enhanced-ui`'s own `frontend/src/features/analytics/`
  tree hasn't independently diverged (e.g. a section component prop tweak done directly
  on that branch) — diff the two branches' `features/analytics/` directories first,
  not just trust a clean `git merge`.

This task is **not** part of "the plan is DONE" — it's the natural next step once it is,
and should be started as its own conversation/task given the conflict-resolution work
involved.
