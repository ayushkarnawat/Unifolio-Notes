# Phase 2 — Stocks/Demat Import (Frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user click "Stocks" from Add Data, upload a CDSL/NSDL Statement of Holdings through the same upload/password UI as MF CAS, review parsed equities/bonds/demat-MFs (including unresolved-security flags), confirm the import, and see the resulting holdings on the dashboard.

**Architecture:** A new, parallel review-based import flow (`DematImportFlow` → `UploadForm` (reused as-is) → `DematReviewTable` → confirm), added as a sibling choice to the existing MF `ImportFlow` at the "Add Data" entry point — not a modification of `ImportFlow`/`TwoPathImportContainer`, which stay MF-only. A new `EquityHoldingsTable` on the dashboard, fed by a new API call, explicitly shows "cost basis unavailable" rather than any gain figure. The existing `AllocationDonut` component needs no changes at all — it already renders whatever buckets the backend returns generically.

**Tech Stack:** React, TypeScript, Vitest + Testing Library (existing conventions in `frontend/src/features/import/*.test.tsx`), Tailwind (CSS custom properties already defined in `frontend/src/styles/tokens.css`), `motion/react` for transitions (matching `ImportFlow.tsx`).

**Spec:** `Docs/superpowers/specs/2026-08-25-phase-2-stocks-demat-research.md` and `Docs/superpowers/specs/2026-08-25-phase-2-demat-integration-decision-memo.md`; backend contracts consumed here are defined in the paired `Docs/superpowers/plans/2026-08-26-phase-2-stocks-demat-import-backend.md`.

## Global Constraints

- **No fabricated cost basis, ever.** Every equity/bond row shows an explicit "Cost basis unavailable" state — never a blank, never a zero, never an inferred number. This is the one visual rule that can't be relaxed anywhere in this plan.
- **Unresolved securities are informational, not blocking.** A holding with `unresolved_security: true` gets a visible badge in the review table, but the Confirm button is never disabled by it — there's no user-facing correction mechanism for a missing NSE/BSE symbol/exchange (unlike the MF flow's AMFI-code override, which exists because the user can look up and type a real code; a stock's exchange symbol isn't something to guess at either end).
- **This plan does not touch `ImportFlow.tsx`, `TwoPathImportContainer.tsx`, `ReviewTable.tsx`, or any MF-import file.** The Stocks flow is new, sibling code. The only existing files this plan modifies are `MainDashboardFlow.tsx` (add the asset-type choice step) and `DashboardView.tsx` (add the Stocks section) — both additive.
- **Scope is per-member view only.** The dashboard's "aggregate" (family combined) view has no backend equity-holdings endpoint yet (the backend plan only adds `/household-members/{id}/equity-holdings`, not a `/household/aggregate/equity-holdings` counterpart) — `EquityHoldingsTable` renders only when `viewMode === "member"`. Flagged as a follow-up, not silently handled: aggregate view needs its own backend endpoint before this table can appear there too.
- **Mobile is out of scope for this plan.** `frontend/src/mobile/features/import/` and `frontend/src/mobile/features/dashboard/` have their own parallel component trees (confirmed during planning: `MobileReviewView.tsx`, `MobileDashboardView.tsx`) that this plan does not touch. Flagged as a follow-up.
- Reuse `UploadForm.tsx` completely unchanged — it already validates `.pdf`/25MB and calls a generic `onSubmit(file, password)`, no MF-specific logic in it at all.

---

### Task 1: Demat import types and API client

**Files:**
- Create: `frontend/src/features/import/demat-types.ts`
- Create: `frontend/src/features/import/demat-api.ts`
- Test: `frontend/src/features/import/demat-api.test.ts`

**Interfaces:**
- Consumes: `API_BASE_URL`, `ApiError`, `invalidateApiCache`, `parseErrorDetail` (existing, `frontend/src/lib/apiClient.ts`); `getToken` (existing, `frontend/src/features/auth/session.ts`) — the same imports `frontend/src/features/import/api.ts` already uses.
- Produces: `DematImportPreviewResponse`, `DematAccountPreview`, `EquityHoldingPreview`, `BondHoldingPreview`, `DematMutualFundHoldingPreview`, `DematImportConfirmResponse` types (mirroring the backend plan's `demat_schemas.py` exactly, field-for-field); `parseDematImport(file, password)`, `confirmDematImport(sessionId, householdMemberId)` functions — consumed by Task 3's `DematImportFlow.tsx`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/import/demat-api.test.ts`:

```typescript
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, confirmDematImport, parseDematImport } from "./demat-api";

describe("parseDematImport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("sends the file and password as multipart form data to /demat-imports/parse", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          session_id: "s1", filename: "statement.pdf", investor_name: "Jane Doe",
          statement_date: "2026-07-31", accounts: [], equities: [], bonds: [],
          mutual_funds: [], parse_warnings: [], unresolved_count: 0,
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", mockFetch);

    const file = new File(["pdf-bytes"], "demat.pdf", { type: "application/pdf" });
    await parseDematImport(file, "secret");

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/demat-imports/parse");
    expect(options.method).toBe("POST");
    const body = options.body as FormData;
    expect(body.get("file")).toBe(file);
    expect(body.get("password")).toBe("secret");
  });

  it("throws ApiError with the structured payload on a 422", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: { code: "mf_cas", message: "This looks like a mutual-fund CAS." } }),
          { status: 422 },
        ),
      ),
    );

    const file = new File(["pdf-bytes"], "demat.pdf", { type: "application/pdf" });
    await expect(parseDematImport(file, "secret")).rejects.toMatchObject({
      status: 422,
      payload: { code: "mf_cas", message: "This looks like a mutual-fund CAS." },
    });
  });
});

describe("confirmDematImport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts session_id and household_member_id as JSON to /demat-imports/confirm", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          equities_added: 2, equities_skipped: 0, bonds_added: 0, bonds_skipped: 0,
          mutual_funds_added: 0, mutual_funds_skipped: 0, import_id: "imp-1",
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", mockFetch);

    const result = await confirmDematImport("s1", "member-1");

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/demat-imports/confirm");
    expect(JSON.parse(options.body as string)).toEqual({
      session_id: "s1", household_member_id: "member-1",
    });
    expect(result.equities_added).toBe(2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/features/import/demat-api.test.ts`
Expected: FAIL — `demat-api.ts` doesn't exist yet.

- [ ] **Step 3: Write the types**

Create `frontend/src/features/import/demat-types.ts`:

```typescript
export interface DematAccountPreview {
  account_key: string;
  depository: string;
  dp_id: string;
  client_id: string;
  broker_name: string;
  owner_names: string[];
}

export interface EquityHoldingPreview {
  account_key: string;
  isin: string;
  name: string | null;
  symbol: string | null;
  exchange: string | null;
  num_shares: string;
  price: string;
  value: string;
  unresolved_security: boolean;
}

export interface BondHoldingPreview {
  account_key: string;
  isin: string;
  name: string | null;
  num_bonds: string;
  value: string;
  face_value: string | null;
  coupon_rate: string | null;
  market_price: string | null;
  maturity_date: string | null;
}

export interface DematMutualFundHoldingPreview {
  account_key: string;
  isin: string;
  name: string | null;
  amfi_code: string | null;
  balance: string;
  nav: string;
  value: string;
  avg_cost: string | null;
  total_cost: string | null;
  pnl: string | null;
  unresolved_security: boolean;
}

export interface DematImportPreviewResponse {
  session_id: string;
  filename: string;
  investor_name: string | null;
  statement_date: string;
  accounts: DematAccountPreview[];
  equities: EquityHoldingPreview[];
  bonds: BondHoldingPreview[];
  mutual_funds: DematMutualFundHoldingPreview[];
  parse_warnings: string[];
  unresolved_count: number;
}

export interface DematImportConfirmResponse {
  equities_added: number;
  equities_skipped: number;
  bonds_added: number;
  bonds_skipped: number;
  mutual_funds_added: number;
  mutual_funds_skipped: number;
  import_id: string;
}
```

- [ ] **Step 4: Write the API client**

Create `frontend/src/features/import/demat-api.ts`:

```typescript
import { API_BASE_URL, ApiError, invalidateApiCache, parseErrorDetail } from "../../lib/apiClient";
import { getToken } from "../auth/session";
import type { DematImportConfirmResponse, DematImportPreviewResponse } from "./demat-types";
import type { ParseErrorPayload } from "./types";

export { ApiError };

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function parseDematImport(file: File, password: string): Promise<DematImportPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("password", password);

  const response = await fetch(`${API_BASE_URL}/demat-imports/parse`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });

  if (!response.ok) {
    throw new ApiError(response.status, (await parseErrorDetail(response)) as ParseErrorPayload | string);
  }

  return (await response.json()) as DematImportPreviewResponse;
}

export async function confirmDematImport(
  sessionId: string,
  householdMemberId: string,
): Promise<DematImportConfirmResponse> {
  const response = await fetch(`${API_BASE_URL}/demat-imports/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ session_id: sessionId, household_member_id: householdMemberId }),
  });

  if (!response.ok) {
    throw new ApiError(response.status, (await parseErrorDetail(response)) as ParseErrorPayload | string);
  }

  invalidateApiCache();
  return (await response.json()) as DematImportConfirmResponse;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/import/demat-api.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/import/demat-types.ts frontend/src/features/import/demat-api.ts \
        frontend/src/features/import/demat-api.test.ts
git commit -m "feat(import): add demat import types and API client"
```

---

### Task 2: DematReviewTable component

**Files:**
- Create: `frontend/src/features/import/DematReviewTable.tsx`
- Test: `frontend/src/features/import/DematReviewTable.test.tsx`

**Interfaces:**
- Consumes: `DematImportPreviewResponse` (Task 1); `Badge`, `Button` from `@/components/ui/badge` / `@/components/ui/button` (same imports `ReviewTable.tsx` uses); `cn` from `@/lib/utils`.
- Produces: `DematReviewTable({ preview, confirming, onConfirm, memberName })` component — consumed by Task 3's `DematImportFlow.tsx`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/import/DematReviewTable.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DematReviewTable } from "./DematReviewTable";
import type { DematImportPreviewResponse } from "./demat-types";

const basePreview: DematImportPreviewResponse = {
  session_id: "s1", filename: "demat.pdf", investor_name: "Jane Doe",
  statement_date: "2026-07-31",
  accounts: [
    { account_key: "12345678:00012345", depository: "nsdl", dp_id: "12345678", client_id: "00012345", broker_name: "ABC Broking Ltd", owner_names: ["Jane Doe"] },
  ],
  equities: [
    { account_key: "12345678:00012345", isin: "INE002A01018", name: "Reliance Industries", symbol: "RELIANCE", exchange: "NSE", num_shares: "10.000", price: "2500.5000", value: "25005.00", unresolved_security: false },
    { account_key: "12345678:00012345", isin: "INE999Z99999", name: "Unknown Corp", symbol: null, exchange: null, num_shares: "5.000", price: "100.0000", value: "500.00", unresolved_security: true },
  ],
  bonds: [],
  mutual_funds: [],
  parse_warnings: [],
  unresolved_count: 1,
};

describe("DematReviewTable", () => {
  it("renders every equity holding with its value", () => {
    render(<DematReviewTable preview={basePreview} confirming={false} onConfirm={vi.fn()} />);

    expect(screen.getByText("Reliance Industries")).toBeInTheDocument();
    expect(screen.getByText("Unknown Corp")).toBeInTheDocument();
    expect(screen.getByText(/25,005/)).toBeInTheDocument();
  });

  it("flags the unresolved security without disabling confirm", () => {
    render(<DematReviewTable preview={basePreview} confirming={false} onConfirm={vi.fn()} />);

    expect(screen.getByText(/unresolved/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /confirm import/i })).toBeEnabled();
  });

  it("shows cost basis unavailable for every equity row", () => {
    render(<DematReviewTable preview={basePreview} confirming={false} onConfirm={vi.fn()} />);

    expect(screen.getAllByText(/cost basis unavailable/i)).toHaveLength(2);
  });

  it("calls onConfirm when the confirm button is clicked", () => {
    const onConfirm = vi.fn();
    render(<DematReviewTable preview={basePreview} confirming={false} onConfirm={onConfirm} />);

    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("disables confirm while confirming is true", () => {
    render(<DematReviewTable preview={basePreview} confirming={true} onConfirm={vi.fn()} />);
    expect(screen.getByRole("button", { name: /confirming/i })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/features/import/DematReviewTable.test.tsx`
Expected: FAIL — component doesn't exist yet.

- [ ] **Step 3: Implement the component**

Create `frontend/src/features/import/DematReviewTable.tsx`:

```tsx
import { motion } from "motion/react";
import type { DematImportPreviewResponse } from "./demat-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowRight, CheckCircle2, HelpCircle, Loader2, Building2 } from "lucide-react";

interface DematReviewTableProps {
  preview: DematImportPreviewResponse;
  confirming: boolean;
  onConfirm: () => void;
  memberName?: string;
}

function formatCurrency(valStr: string): string {
  const num = parseFloat(valStr);
  if (isNaN(num)) return "0";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(num);
}

function formatNumber(valStr: string, decimals: number): string {
  const num = parseFloat(valStr);
  if (isNaN(num)) return "0";
  return new Intl.NumberFormat("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(num);
}

export function DematReviewTable({ preview, confirming, onConfirm, memberName }: DematReviewTableProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
      className="w-full max-w-[1200px] mx-auto space-y-6 text-left box-border relative pb-24 px-3 sm:px-6 lg:px-8"
    >
      <div className="space-y-1">
        <h1 className="font-display font-bold tracking-tight leading-tight text-xl sm:text-3xl text-[var(--color-ink)]">
          {memberName ? `Review ${memberName}'s Demat Statement` : "Review Demat Statement"}
        </h1>
        <p className="text-xs sm:text-sm text-[var(--color-text-secondary)] leading-relaxed">
          Statement as of {preview.statement_date}. Cost basis and gains aren't available from a depository
          statement — holdings and current value only.
        </p>
      </div>

      {preview.accounts.map((account) => (
        <div
          key={account.account_key}
          className="flex items-center gap-2 p-3 rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] text-xs text-[var(--color-text-secondary)]"
        >
          <Building2 className="h-3.5 w-3.5 text-[var(--color-accent)] flex-shrink-0" />
          <span className="font-semibold text-[var(--color-ink)] uppercase">{account.depository}</span>
          <span>{account.broker_name}</span>
          <span className="ml-auto font-mono">DP {account.dp_id} / Client {account.client_id}</span>
        </div>
      ))}

      {preview.equities.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-display text-base font-semibold text-[var(--color-ink)]">
            Equities ({preview.equities.length})
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {preview.equities.map((eq) => (
              <div
                key={`${eq.account_key}:${eq.isin}`}
                className="p-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xs space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold text-sm text-[var(--color-ink)] leading-snug">
                    {eq.name ?? eq.isin}
                  </h3>
                  {eq.unresolved_security ? (
                    <Badge variant="neutral" className="gap-1 text-[10px] flex-shrink-0">
                      <HelpCircle className="h-3 w-3" />
                      <span>Unresolved</span>
                    </Badge>
                  ) : (
                    <Badge variant="positive" className="gap-1 text-[10px] flex-shrink-0">
                      <CheckCircle2 className="h-3 w-3" />
                      <span>{eq.exchange}</span>
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-[var(--color-text-secondary)] font-mono">{eq.symbol ?? eq.isin}</p>
                <div className="text-xs text-[var(--color-text-secondary)] flex justify-between">
                  <span>{formatNumber(eq.num_shares, 3)} shares @ ₹{formatNumber(eq.price, 2)}</span>
                  <span className="font-bold text-[var(--color-ink)]">₹{formatCurrency(eq.value)}</span>
                </div>
                <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)]/80">
                  Cost basis unavailable
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {preview.bonds.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-display text-base font-semibold text-[var(--color-ink)]">
            Bonds ({preview.bonds.length})
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {preview.bonds.map((bond) => (
              <div
                key={`${bond.account_key}:${bond.isin}`}
                className="p-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xs space-y-2"
              >
                <h3 className="font-semibold text-sm text-[var(--color-ink)] leading-snug">{bond.name ?? bond.isin}</h3>
                <div className="text-xs text-[var(--color-text-secondary)] flex justify-between">
                  <span>{formatNumber(bond.num_bonds, 3)} units</span>
                  <span className="font-bold text-[var(--color-ink)]">₹{formatCurrency(bond.value)}</span>
                </div>
                <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)]/80">
                  Cost basis unavailable
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {preview.mutual_funds.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-display text-base font-semibold text-[var(--color-ink)]">
            Demat Mutual Funds ({preview.mutual_funds.length})
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {preview.mutual_funds.map((mf) => (
              <div
                key={`${mf.account_key}:${mf.isin}`}
                className="p-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xs space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold text-sm text-[var(--color-ink)] leading-snug">{mf.name ?? mf.isin}</h3>
                  {mf.unresolved_security && (
                    <Badge variant="neutral" className="gap-1 text-[10px] flex-shrink-0">
                      <HelpCircle className="h-3 w-3" />
                      <span>Unresolved</span>
                    </Badge>
                  )}
                </div>
                <div className="text-xs text-[var(--color-text-secondary)] flex justify-between">
                  <span>{formatNumber(mf.balance, 3)} units @ ₹{formatNumber(mf.nav, 4)}</span>
                  <span className="font-bold text-[var(--color-ink)]">₹{formatCurrency(mf.value)}</span>
                </div>
                {mf.pnl !== null ? (
                  <p className={`text-xs font-semibold ${parseFloat(mf.pnl) >= 0 ? "text-[var(--color-positive)]" : "text-[var(--color-negative)]"}`}>
                    {parseFloat(mf.pnl) >= 0 ? "+" : ""}₹{formatCurrency(mf.pnl)}
                  </p>
                ) : (
                  <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)]/80">
                    Cost basis unavailable
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {preview.parse_warnings.length > 0 && (
        <div className="p-3 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] text-xs text-[var(--color-text-secondary)] space-y-1">
          {preview.parse_warnings.map((w, i) => (
            <p key={i}>{w}</p>
          ))}
        </div>
      )}

      <div className="sticky bottom-4 z-30 w-full p-4 sm:p-5 rounded-2xl bg-[var(--color-surface)]/95 backdrop-blur-md border border-[var(--color-border)] shadow-xl flex items-center justify-between gap-4 flex-wrap box-border mt-6">
        <span className="font-semibold text-xs sm:text-sm text-[var(--color-ink)]">
          {preview.unresolved_count > 0
            ? `${preview.unresolved_count} holding${preview.unresolved_count !== 1 ? "s" : ""} couldn't be matched to a symbol/exchange — they'll still be imported`
            : "All holdings resolved"}
        </span>
        <Button
          type="button"
          disabled={confirming}
          onClick={onConfirm}
          className="h-12 px-6 rounded-xl bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent)]/90 font-semibold text-xs sm:text-sm shadow-xs gap-2 cursor-pointer active:scale-[0.99] transition-all min-h-[48px] ml-auto"
        >
          {confirming ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Confirming...</span>
            </>
          ) : (
            <>
              <span>Confirm Import</span>
              <ArrowRight className="h-4 w-4" />
            </>
          )}
        </Button>
      </div>
    </motion.div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/import/DematReviewTable.test.tsx`
Expected: PASS. If `@/components/ui/badge`'s `Badge` doesn't accept a `className` prop the way this code assumes, check that component's actual props first and adjust (it's the same `Badge` `ReviewTable.tsx` already uses with `className`, so this should already match).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/import/DematReviewTable.tsx frontend/src/features/import/DematReviewTable.test.tsx
git commit -m "feat(import): add demat review table with unresolved-security flags and no-cost-basis states"
```

---

### Task 3: DematImportFlow container and Stocks entry point

**Files:**
- Create: `frontend/src/features/import/DematImportFlow.tsx`
- Test: `frontend/src/features/import/DematImportFlow.test.tsx`
- Modify: `frontend/src/features/dashboard/MainDashboardFlow.tsx`
- Test: extend `frontend/src/features/dashboard/MainDashboardFlow.test.tsx` (read it first to match its existing setup/mocking conventions before adding cases)

**Interfaces:**
- Consumes: `UploadForm` (existing, unchanged); `ImportError` (existing, unchanged — takes `{ error: ParseErrorPayload, onRetry: () => void }`); `DematReviewTable` (Task 2); `parseDematImport`/`confirmDematImport` (Task 1).
- Produces: `DematImportFlow({ householdMemberId, ctaLabel, onDone })` — consumed by `MainDashboardFlow.tsx`'s Add Data screen.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/import/DematImportFlow.test.tsx` — mirror `frontend/src/features/import/ImportFlow.test.tsx`'s existing mocking setup (read it first for the exact `vi.mock` pattern used for `./api` and for `UploadForm`) and write equivalent cases against `./demat-api` instead:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DematImportFlow } from "./DematImportFlow";
import * as dematApi from "./demat-api";

vi.mock("./demat-api");

const preview = {
  session_id: "s1", filename: "demat.pdf", investor_name: "Jane Doe",
  statement_date: "2026-07-31", accounts: [], equities: [], bonds: [],
  mutual_funds: [], parse_warnings: [], unresolved_count: 0,
};

describe("DematImportFlow", () => {
  it("goes from upload to review on successful parse", async () => {
    vi.mocked(dematApi.parseDematImport).mockResolvedValue(preview as any);
    render(<DematImportFlow householdMemberId="member-1" />);

    const file = new File(["pdf"], "demat.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("CAS PDF"), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText("PDF Password"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: /upload statement/i }));

    await waitFor(() => expect(screen.getByText(/review demat statement/i)).toBeInTheDocument());
  });

  it("shows an error screen when parsing fails", async () => {
    vi.mocked(dematApi.parseDematImport).mockRejectedValue(
      new dematApi.ApiError(422, { code: "mf_cas", message: "This looks like a mutual-fund CAS." }),
    );
    render(<DematImportFlow householdMemberId="member-1" />);

    const file = new File(["pdf"], "demat.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("CAS PDF"), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText("PDF Password"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: /upload statement/i }));

    await waitFor(() => expect(screen.getByText(/mutual-fund cas/i)).toBeInTheDocument());
  });
});
```

Selectors above (`"CAS PDF"`, `"PDF Password"`, `/upload statement/i`) are `UploadForm.tsx`'s actual `aria-label`s and button text, confirmed by reading that file during planning — not placeholders to fill in later.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/features/import/DematImportFlow.test.tsx`
Expected: FAIL — component doesn't exist yet.

- [ ] **Step 3: Implement the container**

Create `frontend/src/features/import/DematImportFlow.tsx`:

```tsx
import { useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { UploadForm } from "./UploadForm";
import { ParsingIndicator } from "./ParsingIndicator";
import { DematReviewTable } from "./DematReviewTable";
import { ImportError } from "./ImportError";
import { ApiError, confirmDematImport, parseDematImport } from "./demat-api";
import type { DematImportConfirmResponse, DematImportPreviewResponse } from "./demat-types";
import type { ParseErrorPayload } from "./types";
import { isTestEnv } from "@/lib/motion";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";

type Step = "upload" | "parsing" | "review" | "error" | "confirmed";

interface DematImportFlowProps {
  householdMemberId: string;
  ctaLabel?: string;
  onDone?: () => void;
}

const GENERIC_NETWORK_ERROR: ParseErrorPayload = {
  code: "network_error",
  message: "Couldn't reach the server. Check your connection and try again.",
};

function toParseErrorPayload(err: unknown): ParseErrorPayload {
  if (err instanceof ApiError) {
    const payload = err.payload as ParseErrorPayload | string;
    return typeof payload === "string" ? { code: "error", message: payload } : payload;
  }
  return GENERIC_NETWORK_ERROR;
}

export function DematImportFlow({ householdMemberId, ctaLabel, onDone }: DematImportFlowProps) {
  const [step, setStep] = useState<Step>("upload");
  const [preview, setPreview] = useState<DematImportPreviewResponse | null>(null);
  const [confirmResult, setConfirmResult] = useState<DematImportConfirmResponse | null>(null);
  const [error, setError] = useState<ParseErrorPayload | null>(null);
  const [confirming, setConfirming] = useState(false);

  const shouldReduceMotion = useReducedMotion() || isTestEnv;

  const reset = () => {
    setStep("upload");
    setPreview(null);
    setConfirmResult(null);
    setError(null);
    setConfirming(false);
  };

  const handleUpload = async (file: File, password: string) => {
    setStep("parsing");
    setError(null);
    try {
      const result = await parseDematImport(file, password);
      setPreview(result);
      setStep("review");
    } catch (err) {
      setError(toParseErrorPayload(err));
      setStep("error");
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setConfirming(true);
    try {
      const result = await confirmDematImport(preview.session_id, householdMemberId);
      setConfirmResult(result);
      setStep("confirmed");
    } catch (err) {
      setError(toParseErrorPayload(err));
      setStep("error");
    } finally {
      setConfirming(false);
    }
  };

  return (
    <div className="w-full">
      <AnimatePresence mode="wait">
        {step === "upload" && (
          <motion.div
            key="upload"
            initial={shouldReduceMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={shouldReduceMotion ? undefined : { opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
          >
            <UploadForm onSubmit={handleUpload} />
          </motion.div>
        )}

        {step === "parsing" && (
          <motion.div
            key="parsing"
            initial={shouldReduceMotion ? false : { opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={shouldReduceMotion ? undefined : { opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.2 }}
          >
            <ParsingIndicator />
          </motion.div>
        )}

        {step === "review" && preview && (
          <motion.div
            key="review"
            initial={shouldReduceMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={shouldReduceMotion ? undefined : { opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
          >
            <DematReviewTable preview={preview} confirming={confirming} onConfirm={handleConfirm} />
          </motion.div>
        )}

        {step === "error" && (
          <motion.div
            key="error"
            initial={shouldReduceMotion ? false : { opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={shouldReduceMotion ? undefined : { opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.2 }}
          >
            <ImportError error={error ?? GENERIC_NETWORK_ERROR} onRetry={reset} />
          </motion.div>
        )}

        {step === "confirmed" && confirmResult && (
          <motion.div
            key="confirmed"
            initial={shouldReduceMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={shouldReduceMotion ? undefined : { opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="text-center space-y-4 py-12"
          >
            <CheckCircle2 className="h-12 w-12 text-[var(--color-positive)] mx-auto" />
            <h2 className="font-display font-bold text-xl text-[var(--color-ink)]">Statement imported</h2>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {confirmResult.equities_added} equit{confirmResult.equities_added !== 1 ? "ies" : "y"} added
              {confirmResult.bonds_added > 0 ? `, ${confirmResult.bonds_added} bond${confirmResult.bonds_added !== 1 ? "s" : ""}` : ""}
              {confirmResult.mutual_funds_added > 0 ? `, ${confirmResult.mutual_funds_added} mutual fund${confirmResult.mutual_funds_added !== 1 ? "s" : ""}` : ""}.
            </p>
            <Button type="button" onClick={onDone ?? reset} className="mt-2">
              {ctaLabel ?? "Done"}
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/import/DematImportFlow.test.tsx`
Expected: PASS.

- [ ] **Step 5: Add the "Stocks" entry point choice**

Read `frontend/src/features/dashboard/MainDashboardFlow.tsx`'s full "Add Data" render branch (the `if (isAddingData) { ... }` block, lines ~94-174 as of this writing) before editing — this step adds a new `assetType` state and an asset-type choice screen shown before `ImportFlow`/`DematImportFlow`.

In `frontend/src/features/dashboard/MainDashboardFlow.tsx`:
1. Add `import { DematImportFlow } from "../import/DematImportFlow";` alongside the existing `ImportFlow` import.
2. Add `const [assetType, setAssetType] = useState<"mutual_funds" | "stocks" | null>(null);` near the other `isAddingData`/`targetAddMemberId` state.
3. In `handleAddDataTrigger`, add `setAssetType(null);` so re-entering Add Data always shows the choice again.
4. In the `reset`/back handler (`onClick={() => { clearCasResumeStep2(targetAddMemberId); setIsAddingData(false); }}` in the header), also reset `assetType` to `null` — and add a secondary "back" affordance from the choice screen itself that only resets `assetType` (not the whole Add Data flow) once a choice has been made, matching the existing `onBack` pattern `UploadForm`/`TwoPathImportContainer` already use elsewhere.
5. Inside the "Add Data Content Area" `<main>`, replace the direct `{targetAddMemberId && <ImportFlow ... />}` with:

```tsx
{targetAddMemberId && assetType === null && (
  <div className="max-w-xl mx-auto space-y-4 text-center py-8">
    <h2 className="font-display font-bold text-xl text-[var(--color-ink)]">What are you adding?</h2>
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <button
        type="button"
        onClick={() => setAssetType("mutual_funds")}
        className="p-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-accent)] transition-colors text-left space-y-1 cursor-pointer"
      >
        <h3 className="font-semibold text-sm text-[var(--color-ink)]">Mutual Funds</h3>
        <p className="text-xs text-[var(--color-text-secondary)]">Import a CAMS/KFintech CAS statement.</p>
      </button>
      <button
        type="button"
        onClick={() => setAssetType("stocks")}
        className="p-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-accent)] transition-colors text-left space-y-1 cursor-pointer"
      >
        <h3 className="font-semibold text-sm text-[var(--color-ink)]">Stocks</h3>
        <p className="text-xs text-[var(--color-text-secondary)]">Import a CDSL/NSDL demat Statement of Holdings.</p>
      </button>
    </div>
  </div>
)}

{targetAddMemberId && assetType === "mutual_funds" && (
  <ImportFlow
    key={targetAddMemberId}
    householdMemberId={targetAddMemberId}
    ctaLabel="Back to Dashboard"
    onDone={() => setIsAddingData(false)}
  />
)}

{targetAddMemberId && assetType === "stocks" && (
  <DematImportFlow
    key={targetAddMemberId}
    householdMemberId={targetAddMemberId}
    ctaLabel="Back to Dashboard"
    onDone={() => setIsAddingData(false)}
  />
)}
```

- [ ] **Step 6: Write and run a test for the entry-point choice**

Read `frontend/src/features/dashboard/MainDashboardFlow.test.tsx` first to match its existing render/mock setup exactly, then add a test asserting: triggering Add Data shows the "What are you adding?" choice; clicking "Stocks" renders `DematImportFlow` (assert something only it renders, e.g. mock it and check it was rendered, matching however that test file already mocks `ImportFlow` if it does).

Run: `cd frontend && npx vitest run src/features/dashboard/MainDashboardFlow.test.tsx`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/import/DematImportFlow.tsx frontend/src/features/import/DematImportFlow.test.tsx \
        frontend/src/features/dashboard/MainDashboardFlow.tsx frontend/src/features/dashboard/MainDashboardFlow.test.tsx
git commit -m "feat(import): add Stocks entry point and demat import flow to Add Data"
```

---

### Task 4: Equity holdings dashboard table

**Files:**
- Create: `frontend/src/components/EquityHoldingsTable.tsx`
- Test: `frontend/src/components/EquityHoldingsTable.test.tsx`
- Modify: `frontend/src/features/dashboard/types.ts` (add `EquityHoldingRow`)
- Modify: `frontend/src/features/dashboard/api.ts` (add `getMemberEquityHoldings`)
- Modify: `frontend/src/features/dashboard/DashboardView.tsx`
- Test: extend `frontend/src/features/dashboard/DashboardView.test.tsx` (read it first to match its existing mock setup)

**Interfaces:**
- Consumes: `getMemberEquityHoldings(memberId, signal)` (new); `EquityHoldingRow` type (new, mirrors the backend plan's `EquityHoldingRow` schema field-for-field).
- Produces: `EquityHoldingsTable({ holdings })` — rendered inside `DashboardView.tsx`'s per-member view only (Global Constraints).

- [ ] **Step 1: Write the failing component test**

Create `frontend/src/components/EquityHoldingsTable.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EquityHoldingsTable } from "./EquityHoldingsTable";
import type { EquityHoldingRow } from "../features/dashboard/types";

const holding: EquityHoldingRow = {
  demat_account_id: "acc-1", household_member_id: "member-1", household_member_name: "Self",
  isin: "INE002A01018", name: "Reliance Industries", symbol: "RELIANCE", exchange: "NSE",
  num_shares: "10.000", price: "2500.5000", current_value: "25005.00",
  statement_date: "2026-07-31", unresolved_security: false, cost_basis_available: false,
};

describe("EquityHoldingsTable", () => {
  it("shows an empty state when there are no holdings", () => {
    render(<EquityHoldingsTable holdings={[]} />);
    expect(screen.getByText(/no stock holdings/i)).toBeInTheDocument();
  });

  it("renders a holding's name, symbol, and current value", () => {
    render(<EquityHoldingsTable holdings={[holding]} />);
    expect(screen.getByText("Reliance Industries")).toBeInTheDocument();
    expect(screen.getByText("RELIANCE")).toBeInTheDocument();
    expect(screen.getByText(/25,005/)).toBeInTheDocument();
  });

  it("shows cost basis unavailable instead of a gain figure", () => {
    render(<EquityHoldingsTable holdings={[holding]} />);
    expect(screen.getByText(/cost basis unavailable/i)).toBeInTheDocument();
  });

  it("flags an unresolved security", () => {
    render(<EquityHoldingsTable holdings={[{ ...holding, unresolved_security: true, symbol: null, exchange: null }]} />);
    expect(screen.getByText(/unresolved/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/EquityHoldingsTable.test.tsx`
Expected: FAIL — component and type don't exist yet.

- [ ] **Step 3: Add the `EquityHoldingRow` type**

In `frontend/src/features/dashboard/types.ts`, add:

```typescript
export interface EquityHoldingRow {
  demat_account_id: string;
  household_member_id: string;
  household_member_name: string;
  isin: string;
  name: string | null;
  symbol: string | null;
  exchange: string | null;
  num_shares: string;
  price: string;
  current_value: string;
  statement_date: string;
  unresolved_security: boolean;
  cost_basis_available: boolean;
}
```

- [ ] **Step 4: Add the API function**

In `frontend/src/features/dashboard/api.ts`, add near `getMemberHoldings`:

```typescript
export async function getMemberEquityHoldings(memberId: string, signal?: AbortSignal): Promise<EquityHoldingRow[]> {
  const res = await authFetch(`/household-members/${memberId}/equity-holdings`, { signal });
  return res.json();
}
```

Add `EquityHoldingRow` to the `import type { ... } from "./types"` block at the top of the file.

- [ ] **Step 5: Implement the component**

Create `frontend/src/components/EquityHoldingsTable.tsx`:

```tsx
import { Badge } from "./Badge";
import type { EquityHoldingRow } from "../features/dashboard/types";

export interface EquityHoldingsTableProps {
  holdings: EquityHoldingRow[];
}

function formatCurrency(valStr: string): string {
  const num = parseFloat(valStr);
  if (isNaN(num)) return "0";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(num);
}

function formatNumber(valStr: string, decimals: number): string {
  const num = parseFloat(valStr);
  if (isNaN(num)) return "0";
  return new Intl.NumberFormat("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(num);
}

export function EquityHoldingsTable({ holdings }: EquityHoldingsTableProps) {
  if (!holdings || holdings.length === 0) {
    return (
      <div className="p-8 text-center rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)]">
        <p className="type-body">No stock holdings found.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xs overflow-hidden">
      <div className="w-full overflow-x-auto">
        <table className="w-full text-left text-sm block lg:table">
          <thead className="hidden lg:table-header-group">
            <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg)]/40 text-[var(--color-text-secondary)]">
              <th className="py-3 px-4 min-w-[220px] text-xs font-semibold select-none">Security</th>
              <th className="py-3 px-4 text-xs font-semibold text-right select-none whitespace-nowrap">Shares</th>
              <th className="py-3 px-4 text-xs font-semibold text-right select-none whitespace-nowrap">Price</th>
              <th className="py-3 px-4 text-xs font-semibold text-right select-none whitespace-nowrap">Current Value</th>
              <th className="py-3 px-4 text-xs font-semibold select-none whitespace-nowrap">Gain / Loss</th>
            </tr>
          </thead>
          <tbody className="block lg:table-row-group divide-y divide-[var(--color-border)]">
            {holdings.map((row) => (
              <tr
                key={`${row.demat_account_id}:${row.isin}`}
                className="block lg:table-row p-3.5 sm:p-4 lg:p-0"
              >
                <td className="inline lg:table-cell py-1 lg:py-3 px-0 lg:px-4 align-middle">
                  <span className="font-semibold text-sm text-[var(--color-ink)]">{row.name ?? row.isin}</span>
                  <span className="text-xs text-[var(--color-text-secondary)] block mt-0.5">
                    {row.symbol ?? row.isin}
                    {row.exchange ? ` · ${row.exchange}` : ""}
                  </span>
                  {row.unresolved_security && (
                    <Badge variant="neutral">unresolved</Badge>
                  )}
                </td>
                <td className="block lg:table-cell py-1 lg:py-3 px-0 lg:px-4 text-left lg:text-right text-xs font-medium tabular-nums text-[var(--color-ink)] align-middle whitespace-nowrap">
                  {formatNumber(row.num_shares, 3)}
                </td>
                <td className="block lg:table-cell py-1 lg:py-3 px-0 lg:px-4 text-left lg:text-right text-xs font-medium tabular-nums text-[var(--color-ink)] align-middle whitespace-nowrap">
                  ₹{formatNumber(row.price, 2)}
                </td>
                <td className="block lg:table-cell py-1.5 lg:py-3 px-0 lg:px-4 text-left lg:text-right text-sm font-bold tabular-nums text-[var(--color-ink)] align-middle whitespace-nowrap">
                  ₹{formatCurrency(row.current_value)}
                </td>
                <td className="block lg:table-cell py-1 lg:py-3 px-0 lg:px-4 text-left lg:text-right text-xs text-[var(--color-text-secondary)] align-middle whitespace-nowrap">
                  {row.cost_basis_available ? "—" : "Cost basis unavailable"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/EquityHoldingsTable.test.tsx`
Expected: PASS.

- [ ] **Step 7: Wire into `DashboardView.tsx`**

Read the current full content of `frontend/src/features/dashboard/DashboardView.tsx` around its data-fetch effect (the `fetchData` function inside the `useEffect` starting at line ~83 as of this writing) and its Holdings Table Section (around line ~605-652 as of this writing) before editing — line numbers will have shifted from Task 3/prior edits.

1. Add `const [equityHoldings, setEquityHoldings] = useState<EquityHoldingRow[]>([]);` alongside the other `useState` declarations.
2. Add `import { EquityHoldingsTable } from "../../components/EquityHoldingsTable";`, `import { getMemberEquityHoldings } from "./api";`, and `EquityHoldingRow` to the `import type { ... } from "./types"` block.
3. In the `fetchData` function's `else if (memberId)` branch (member view only — Global Constraints), add `getMemberEquityHoldings(memberId, controller.signal)` to the `Promise.all([...])` call alongside the existing three, and `setEquityHoldings(equityHoldingsRes)` in that branch's `if (isMounted)` block. In the `aggregate` branch, explicitly `setEquityHoldings([])` (not fetched — Global Constraints' scope note) rather than leaving stale data from a prior member view.
4. After the existing Holdings Table `</section>` and before the `{/* S15: Fund Detail Modal */}` comment, add:

```tsx
{viewMode === "member" && equityHoldings.length > 0 && (
  <section className="flex flex-col space-y-4">
    <h2 className="font-display text-lg font-semibold tracking-tight text-[var(--color-ink)]">
      Stocks ({equityHoldings.length})
    </h2>
    <EquityHoldingsTable holdings={equityHoldings} />
  </section>
)}
```

- [ ] **Step 8: Write and run a DashboardView test**

Read `frontend/src/features/dashboard/DashboardView.test.tsx` first to match its existing mock setup for `getMemberHoldings`/etc., then add a test mocking `getMemberEquityHoldings` to return one row and asserting the "Stocks" section renders in member view, and a test asserting it does NOT render in aggregate view (Global Constraints scope note).

Run: `cd frontend && npx vitest run src/features/dashboard/DashboardView.test.tsx`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/EquityHoldingsTable.tsx frontend/src/components/EquityHoldingsTable.test.tsx \
        frontend/src/features/dashboard/types.ts frontend/src/features/dashboard/api.ts \
        frontend/src/features/dashboard/DashboardView.tsx frontend/src/features/dashboard/DashboardView.test.tsx
git commit -m "feat(dashboard): add Stocks holdings table for the per-member view"
```

---

### Task 5: Verify the allocation donut renders the Stocks bucket automatically

**Files:**
- Test: extend `frontend/src/features/dashboard/DashboardView.test.tsx`

**Interfaces:**
- Consumes: `AllocationDonut` (existing, unchanged — confirmed during planning to be fully generic over `{ label, current_value, percentage }`, with no hardcoded bucket-name list anywhere in `frontend/src/components/AllocationDonut.tsx` or in `DashboardView.tsx`'s `allocation?.by_asset_class || []` pass-through).

No component code changes are needed for this task — the backend plan's Task 4 already makes `AllocationSummary.by_asset_class` include a `"Stocks"` bucket when equity holdings exist, and `AllocationDonut` renders whatever array it's given. This task only adds regression coverage so a future refactor of `AllocationDonut` or the allocation-fetch wiring doesn't silently reintroduce a hardcoded bucket list.

- [ ] **Step 1: Write the test**

Add to `frontend/src/features/dashboard/DashboardView.test.tsx` (matching its existing mock conventions, confirmed by reading the file first): mock `getMemberAllocation` to return `{ by_asset_class: [{ label: "Equity", current_value: "100000.00", percentage: 66.6 }, { label: "Stocks", current_value: "50000.00", percentage: 33.3 }], by_amc: [], total_value: "150000.00" }`, render `DashboardView` in member view, and assert the text `"Stocks"` appears somewhere in the rendered allocation section (the donut's legend or slice label — check how the existing test suite already asserts on other bucket labels like `"Equity"`/`"Debt"` and mirror that exact assertion style).

- [ ] **Step 2: Run the test**

Run: `cd frontend && npx vitest run src/features/dashboard/DashboardView.test.tsx`
Expected: PASS with no production code changes — if it fails, that means `AllocationDonut` or its wiring is less generic than confirmed during planning; investigate before assuming this task needs a code change rather than a bad assumption.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/dashboard/DashboardView.test.tsx
git commit -m "test(dashboard): verify the allocation donut renders a Stocks bucket with no code changes"
```

---

## After this plan

- **Not in this plan, flagged as follow-ups:** aggregate (family combined) equity holdings view (needs a backend `/household/aggregate/equity-holdings` endpoint first); mobile parity (`frontend/src/mobile/features/import/`, `frontend/src/mobile/features/dashboard/`); a bonds/demat-MF dashboard table (only equities have one, matching the backend plan's scope); email auto-ingestion (a separate, later plan, per the decision memo).
- Once both plans are merged, manually verify the golden path end-to-end in a browser per this repo's UI-change convention: Add Data → Stocks → upload a real (or synthetic) CDSL/NSDL PDF → review → confirm → see it on the dashboard — the plans above were written from static analysis of the codebase and the installed `casparser` library's source, not from running the app.
