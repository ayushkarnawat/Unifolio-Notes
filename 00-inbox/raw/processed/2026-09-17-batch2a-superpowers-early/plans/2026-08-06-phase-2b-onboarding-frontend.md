# Phase 2b — Onboarding Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Onboarding frontend (PRD-02) — landing screen, phone+OTP
login, the four-question flow with back-navigation, family setup, and the
Family CAS Upload subsystem (per-member queue + batch parse) — wired to the
Phase 2 backend and Phase 1b's existing Import Review screens.

**Architecture:** A new `frontend/src/features/auth/` folder owns
everything from Landing through onboarding completion, composed under a new
`AuthContext` that resolves session state once (on load) and drives
`App.tsx`'s top-level render branch reactively. `OnboardingFlow` is a
step-history state machine (not a router — the app has exactly one active
destination at a time). The solo CAS-upload path reuses Phase 1b's
`ImportFlow` unchanged except for two new optional props; the family path
gets its own `FamilyImportFlow` orchestrator that calls the same underlying
`ReviewTable`/`ImportError`/`ImportConfirmed`/api functions directly,
sequenced across a client-side upload queue.

**Tech Stack:** React 19 + TypeScript, Vite, Vitest + React Testing
Library, CSS Modules + `frontend/src/styles/tokens.css` design tokens — all
already in place from Phase 0/1b, no new dependencies.

## Global Constraints

- **Model policy for execution:** `fable` for implementer/reviewer/final-review
  dispatches by default; escalate to `sonnet` only when a specific task
  genuinely needs it (per the user's explicit token-budget priority).
- **No router library.** One active destination at a time
  (Auth → Onboarding → Import → Dashboard placeholder); `OnboardingFlow`'s
  history-array state machine covers navigation.
- **`Decimal`-as-string values from the backend are display-only strings on
  the frontend** — this plan touches no money math, but where existing
  Import types pass through `amount`/`units`/`nav` as strings, never coerce
  them to `number`.
- **`users` has no `name` column** (confirmed in `Docs/PRDs/Database-Schema-Unifolio.md`).
  Q1's name answer is never sent to `PATCH /auth/me` — it's held in
  `OnboardingFlow`'s local state and used only when creating the account
  holder's own `household_members` row (`relationship: "self"`), lazily,
  the first time it's actually needed (see Task 9).
- **No `PATCH /household-members` endpoint exists** (only `POST`/`GET`).
  Every place that needs the account holder's own household-member row
  must resolve it via **list-then-create** (`listHouseholdMembers()`, find
  `relationship === "self"`, create only if absent) — never blind-create,
  or a session resumed after a reload will insert a duplicate `self` row.
- **Locked `onboarding_step` vocabulary** (frontend-only constant, the
  backend column is free-text `VARCHAR`, per PRD-02/App-Flow):
  `landing`, `phone`, `otp`, `trust_primer`, `q1_name`, `q2_investing`,
  `q3_purpose`, `q4_household`, `add_family`, `cas_upload`,
  `family_cas_upload`, `upload_my_cas`, `parse_queue`, `done`.
- **Batch parse is strictly sequential, never parallel** — two concurrent
  `parseImport` calls would race against the backend's in-memory
  preview-session store (the same class of bug Phase 1's dedupe race
  already surfaced once).
- **`ImportConfirmed`'s celebratory screen shows once per onboarding path**
  (solo: after the single confirm; family: once, as an aggregate, after
  the last queued item) — never once per queued member. Decided during
  brainstorming, per PRD-02 Design Handoff Alignment #5.
- **PRD-01's `ReviewTable`, `ImportError`, `UploadForm` are not redesigned.**
  Family CAS Upload adds a member-context label rendered *above*
  `ReviewTable`, never inside it.
- **`ImportConfirmed`'s default behavior (`ctaLabel="Import another CAS"`,
  resets to blank upload) must stay unchanged** for its existing S16
  Ongoing Data Addition caller — the new `ctaLabel`/`onDone` overrides are
  additive, opt-in props only.
- **PIN/biometric return-login (PRD-02 FR-2a) is out of scope** — deferred
  in PRD-02 itself to a future Auth/Security PRD.

---

### Task 1: Shared API client + wire real auth into `features/import/api.ts`

**Files:**
- Create: `frontend/src/lib/apiClient.ts`
- Modify: `frontend/src/features/import/api.ts`
- Modify: `frontend/src/features/import/api.test.ts`
- Modify: `frontend/.env.example`

**Interfaces:**
- Produces: `API_BASE_URL: string`, `class ApiError extends Error { status: number; payload: unknown }`,
  `parseErrorDetail(response: Response): Promise<unknown>` from `lib/apiClient.ts`.
- Produces: `parseImport(file: File, password: string): Promise<ImportPreviewResponse>`,
  `confirmImport(sessionId: string, householdMemberId: string, schemeConfirmations: SchemeConfirmation[]): Promise<ImportConfirmResponse>`
  (signature changed — now takes `householdMemberId`) from `features/import/api.ts`.
- Consumes (added this task, defined in Task 2): `getToken(): string | null` from `features/auth/session.ts`.

This extracts the error-handling logic that `features/import/api.ts` and
the new `features/auth/api.ts` (Task 3) both need, and closes the last
piece of the dev-seed-household-member hack: `confirmImport` now takes a
real `householdMemberId` argument and both calls attach a real
`Authorization` header, instead of reading `VITE_DEV_HOUSEHOLD_MEMBER_ID`.

- [ ] **Step 1: Write the failing tests for the changed `confirmImport` signature**

Replace the two `confirmImport` tests in `frontend/src/features/import/api.test.ts`:

```typescript
describe("confirmImport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends session_id, household_member_id, and scheme_confirmations as JSON", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ added: 1, skipped: 0, import_id: "imp1" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", mockFetch);

    await confirmImport("sess1", "member-1", [{ temp_id: "t1", amfi_code: "12345" }]);

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/imports/confirm");
    const body = JSON.parse(options.body as string);
    expect(body.session_id).toBe("sess1");
    expect(body.household_member_id).toBe("member-1");
    expect(body.scheme_confirmations).toEqual([{ temp_id: "t1", amfi_code: "12345" }]);
  });

  it("throws ApiError with a string payload on a 404", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Import session not found." }), { status: 404 }),
      ),
    );

    await expect(confirmImport("gone", "member-1", [])).rejects.toBeInstanceOf(ApiError);
  });

  it("attaches an Authorization header when a session token is stored", async () => {
    localStorage.setItem("unifolio_session_token", "tok-abc");
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ added: 0, skipped: 0, import_id: "imp1" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", mockFetch);

    await confirmImport("sess1", "member-1", []);

    const [, options] = mockFetch.mock.calls[0];
    expect((options.headers as Record<string, string>).Authorization).toBe("Bearer tok-abc");
    localStorage.removeItem("unifolio_session_token");
  });
});
```

Also add one Authorization-header test to the `parseImport` describe block:

```typescript
  it("attaches an Authorization header when a session token is stored", async () => {
    localStorage.setItem("unifolio_session_token", "tok-abc");
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session_id: "s1", schemes: [], transactions: [] }), { status: 200 }),
    );
    vi.stubGlobal("fetch", mockFetch);

    const file = new File(["pdf-bytes"], "cas.pdf", { type: "application/pdf" });
    await parseImport(file, "secret");

    const [, options] = mockFetch.mock.calls[0];
    expect((options.headers as Record<string, string>).Authorization).toBe("Bearer tok-abc");
    localStorage.removeItem("unifolio_session_token");
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- api.test.ts`
Expected: FAIL — `confirmImport` still takes 2 arguments, and neither call attaches an `Authorization` header.

- [ ] **Step 3: Create the shared API client module**

```typescript
// frontend/src/lib/apiClient.ts
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, payload: unknown) {
    super(
      typeof payload === "string"
        ? payload
        : ((payload as { message?: string } | null)?.message ?? "Request failed"),
    );
    this.status = status;
    this.payload = payload;
  }
}

export async function parseErrorDetail(response: Response): Promise<unknown> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail) && "code" in detail) {
      return detail;
    }
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0 && typeof detail[0]?.msg === "string") {
      return detail[0].msg as string;
    }
    return `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}
```

- [ ] **Step 4: Create the session token store `features/auth/session.ts` (needed now, built out fully in Task 2)**

```typescript
// frontend/src/features/auth/session.ts
const TOKEN_KEY = "unifolio_session_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}
```

- [ ] **Step 5: Rewrite `features/import/api.ts` to use the shared client, real auth, and the new `confirmImport` signature**

```typescript
import { API_BASE_URL, ApiError, parseErrorDetail } from "../../lib/apiClient";
import { getToken } from "../auth/session";
import type {
  ImportConfirmResponse,
  ImportPreviewResponse,
  ParseErrorPayload,
  SchemeConfirmation,
} from "./types";

export { ApiError };

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function parseImport(file: File, password: string): Promise<ImportPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("password", password);

  const response = await fetch(`${API_BASE_URL}/imports/parse`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });

  if (!response.ok) {
    throw new ApiError(response.status, (await parseErrorDetail(response)) as ParseErrorPayload | string);
  }

  return (await response.json()) as ImportPreviewResponse;
}

export async function confirmImport(
  sessionId: string,
  householdMemberId: string,
  schemeConfirmations: SchemeConfirmation[],
): Promise<ImportConfirmResponse> {
  const response = await fetch(`${API_BASE_URL}/imports/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      session_id: sessionId,
      household_member_id: householdMemberId,
      scheme_confirmations: schemeConfirmations,
    }),
  });

  if (!response.ok) {
    throw new ApiError(response.status, (await parseErrorDetail(response)) as ParseErrorPayload | string);
  }

  return (await response.json()) as ImportConfirmResponse;
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npm test -- api.test.ts`
Expected: PASS

- [ ] **Step 7: Remove the retired dev-seed env var**

Edit `frontend/.env.example`, removing the `VITE_DEV_HOUSEHOLD_MEMBER_ID`
block entirely (its 3 lines: the blank line before it, the two comment
lines, and the `VITE_DEV_HOUSEHOLD_MEMBER_ID=` line) — leave only:

```
# Backend base URL for local dev (uvicorn default)
VITE_API_BASE_URL=http://localhost:8000
```

- [ ] **Step 8: Run the full frontend test suite to confirm nothing else broke**

Run: `cd frontend && npm test`
Expected: All existing tests pass except `ImportFlow.test.tsx` and
`ImportConfirmed.test.tsx`, which are expected to fail now (they call the
old 2-argument `confirmImport`/props shape) — fixed in Task 9. Confirm the
failures are *only* in those two files.

- [ ] **Step 9: Commit**

```bash
cd frontend
git add src/lib/apiClient.ts src/features/import/api.ts src/features/import/api.test.ts src/features/auth/session.ts .env.example
git commit -m "refactor: extract shared API client, wire real auth into Import Service calls"
```

---

### Task 2: Auth types + session token store tests

**Files:**
- Create: `frontend/src/features/auth/types.ts`
- Test: `frontend/src/features/auth/session.test.ts`
- Modify: `frontend/src/features/auth/session.ts` (created in Task 1 — this task adds its test)

**Interfaces:**
- Produces: `OtpRequestResponse`, `OtpVerifyResponse`, `MeResponse`,
  `UpdateMeBody`, `Relationship`, `HouseholdMember`, `InvestorType`,
  `PrimaryGoal` types from `features/auth/types.ts` — the exact shapes
  Task 3's `api.ts` and every later screen consume.
- Consumes: nothing new (session.ts already exists from Task 1).

- [ ] **Step 1: Write the failing test for the session store**

```typescript
// frontend/src/features/auth/session.test.ts
import { afterEach, describe, expect, it } from "vitest";
import { clearToken, getToken, setToken } from "./session";

describe("session token store", () => {
  afterEach(() => {
    clearToken();
  });

  it("returns null when no token is stored", () => {
    expect(getToken()).toBeNull();
  });

  it("round-trips a token through set/get", () => {
    setToken("tok-123");
    expect(getToken()).toBe("tok-123");
  });

  it("clears a stored token", () => {
    setToken("tok-123");
    clearToken();
    expect(getToken()).toBeNull();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- session.test.ts`
Expected: FAIL if `session.ts` doesn't exist yet in this branch's history at
this point; if Task 1 already landed it, this step instead confirms the
test passes immediately — either is fine, `session.ts`'s implementation
does not change in this task, only its test coverage is added.

- [ ] **Step 3: Confirm `session.ts` (from Task 1) needs no changes**

`frontend/src/features/auth/session.ts` already implements `getToken`,
`setToken`, `clearToken` exactly as tested above (Task 1, Step 4). No edit
needed here.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- session.test.ts`
Expected: PASS

- [ ] **Step 5: Create the auth types module**

```typescript
// frontend/src/features/auth/types.ts
export type InvestorType = "self_directed" | "advisor_assisted" | "mixed" | "beginner";
export type PrimaryGoal =
  | "consolidated_view"
  | "understand_holdings"
  | "family_management"
  | "performance_comparison";
export type Relationship = "self" | "spouse" | "parent" | "child" | "sibling" | "other";

export interface OtpRequestResponse {
  message: string;
  otp: string | null;
}

export interface OtpVerifyResponse {
  session_token: string;
  user_id: string;
  onboarding_step: string | null;
  onboarding_completed: boolean;
}

export interface MeResponse {
  user_id: string;
  phone_number: string;
  email: string | null;
  onboarding_step: string | null;
  onboarding_completed: boolean;
  investor_type: InvestorType | null;
  primary_goal: PrimaryGoal | null;
}

export interface UpdateMeBody {
  onboarding_step?: string;
  investor_type?: InvestorType;
  primary_goal?: PrimaryGoal;
  onboarding_completed?: boolean;
}

export interface HouseholdMember {
  id: string;
  name: string;
  relationship: Relationship;
  relationship_other_label: string | null;
}
```

- [ ] **Step 6: Run the full frontend build to check types compile**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: PASS (no consumers of these types exist yet, so this just checks
the file itself is syntactically valid TypeScript).

- [ ] **Step 7: Commit**

```bash
git add src/features/auth/types.ts src/features/auth/session.test.ts
git commit -m "test: cover session token store, add auth types"
```

---

### Task 3: Auth API wrappers

**Files:**
- Create: `frontend/src/features/auth/api.ts`
- Test: `frontend/src/features/auth/api.test.ts`

**Interfaces:**
- Consumes: `API_BASE_URL`, `ApiError`, `parseErrorDetail` from `../../lib/apiClient`
  (Task 1); `getToken` from `./session` (Task 1); all types from `./types` (Task 2).
- Produces: `requestOtp(phoneNumber: string): Promise<OtpRequestResponse>`,
  `verifyOtp(phoneNumber: string, otp: string): Promise<OtpVerifyResponse>`,
  `getMe(): Promise<MeResponse>`, `updateMe(body: UpdateMeBody): Promise<MeResponse>`,
  `createHouseholdMember(name: string, relationship: Relationship, relationshipOtherLabel?: string): Promise<HouseholdMember>`,
  `listHouseholdMembers(): Promise<HouseholdMember[]>` — every later auth/onboarding
  screen and `AuthContext` (Task 4) calls these exactly.

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/features/auth/api.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createHouseholdMember,
  getMe,
  listHouseholdMembers,
  requestOtp,
  updateMe,
  verifyOtp,
} from "./api";
import { clearToken, setToken } from "./session";

describe("auth api", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    clearToken();
  });

  it("requestOtp posts phone_number as JSON", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: "OTP sent.", otp: "123456" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", mockFetch);

    const result = await requestOtp("+919999999999");

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/auth/otp/request");
    expect(JSON.parse(options.body as string)).toEqual({ phone_number: "+919999999999" });
    expect(result.otp).toBe("123456");
  });

  it("verifyOtp posts phone_number and otp as JSON", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          session_token: "tok-1", user_id: "u1", onboarding_step: null, onboarding_completed: false,
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", mockFetch);

    const result = await verifyOtp("+919999999999", "123456");

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/auth/otp/verify");
    expect(JSON.parse(options.body as string)).toEqual({ phone_number: "+919999999999", otp: "123456" });
    expect(result.session_token).toBe("tok-1");
  });

  it("getMe attaches the stored token as a Bearer header", async () => {
    setToken("tok-abc");
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          user_id: "u1", phone_number: "+919999999999", email: null,
          onboarding_step: "q2_investing", onboarding_completed: false,
          investor_type: null, primary_goal: null,
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", mockFetch);

    const result = await getMe();

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/auth/me");
    expect((options.headers as Record<string, string>).Authorization).toBe("Bearer tok-abc");
    expect(result.onboarding_step).toBe("q2_investing");
  });

  it("updateMe PATCHes the body as JSON with auth", async () => {
    setToken("tok-abc");
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          user_id: "u1", phone_number: "+919999999999", email: null,
          onboarding_step: "q3_purpose", onboarding_completed: false,
          investor_type: "self_directed", primary_goal: null,
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", mockFetch);

    const result = await updateMe({ onboarding_step: "q3_purpose", investor_type: "self_directed" });

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/auth/me");
    expect(options.method).toBe("PATCH");
    expect(JSON.parse(options.body as string)).toEqual({
      onboarding_step: "q3_purpose", investor_type: "self_directed",
    });
    expect(result.investor_type).toBe("self_directed");
  });

  it("createHouseholdMember posts name/relationship as JSON with auth", async () => {
    setToken("tok-abc");
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ id: "m1", name: "Mom", relationship: "parent", relationship_other_label: null }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", mockFetch);

    const result = await createHouseholdMember("Mom", "parent");

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/household-members");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body as string)).toEqual({
      name: "Mom", relationship: "parent", relationship_other_label: null,
    });
    expect(result.id).toBe("m1");
  });

  it("listHouseholdMembers GETs the list with auth", async () => {
    setToken("tok-abc");
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify([{ id: "m1", name: "Self", relationship: "self", relationship_other_label: null }]),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", mockFetch);

    const result = await listHouseholdMembers();

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/household-members");
    expect((options.headers as Record<string, string>).Authorization).toBe("Bearer tok-abc");
    expect(result).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- features/auth/api.test.ts`
Expected: FAIL — `./api` doesn't exist yet.

- [ ] **Step 3: Implement the auth API wrappers**

```typescript
// frontend/src/features/auth/api.ts
import { API_BASE_URL, ApiError, parseErrorDetail } from "../../lib/apiClient";
import { getToken } from "./session";
import type {
  HouseholdMember,
  MeResponse,
  OtpRequestResponse,
  OtpVerifyResponse,
  Relationship,
  UpdateMeBody,
} from "./types";

export { ApiError };

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function throwIfError(response: Response): Promise<void> {
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response));
  }
}

export async function requestOtp(phoneNumber: string): Promise<OtpRequestResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/otp/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone_number: phoneNumber }),
  });
  await throwIfError(response);
  return (await response.json()) as OtpRequestResponse;
}

export async function verifyOtp(phoneNumber: string, otp: string): Promise<OtpVerifyResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/otp/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone_number: phoneNumber, otp }),
  });
  await throwIfError(response);
  return (await response.json()) as OtpVerifyResponse;
}

export async function getMe(): Promise<MeResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, { headers: authHeaders() });
  await throwIfError(response);
  return (await response.json()) as MeResponse;
}

export async function updateMe(body: UpdateMeBody): Promise<MeResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  await throwIfError(response);
  return (await response.json()) as MeResponse;
}

export async function createHouseholdMember(
  name: string,
  relationship: Relationship,
  relationshipOtherLabel?: string,
): Promise<HouseholdMember> {
  const response = await fetch(`${API_BASE_URL}/household-members`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      name,
      relationship,
      relationship_other_label: relationshipOtherLabel ?? null,
    }),
  });
  await throwIfError(response);
  return (await response.json()) as HouseholdMember;
}

export async function listHouseholdMembers(): Promise<HouseholdMember[]> {
  const response = await fetch(`${API_BASE_URL}/household-members`, { headers: authHeaders() });
  await throwIfError(response);
  return (await response.json()) as HouseholdMember[];
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- features/auth/api.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/features/auth/api.ts src/features/auth/api.test.ts
git commit -m "feat: add auth/household-member API wrappers"
```

---

### Task 4: `AuthContext` — session resume, login, logout, updateMe

**Files:**
- Create: `frontend/src/features/auth/AuthContext.tsx`
- Test: `frontend/src/features/auth/AuthContext.test.tsx`

**Interfaces:**
- Consumes: `getMe`, `updateMe as apiUpdateMe` from `./api` (Task 3);
  `getToken`, `setToken`, `clearToken` from `./session` (Task 1);
  `MeResponse`, `UpdateMeBody` from `./types` (Task 2).
- Produces: `AuthProvider({ children }: { children: ReactNode })`,
  `useAuth(): { token: string | null; me: MeResponse | null; loading: boolean; login: (token: string) => Promise<void>; logout: () => void; updateMe: (body: UpdateMeBody) => Promise<void> }`
  — every screen from Task 6 onward reads session state through `useAuth()`.

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/features/auth/AuthContext.test.tsx
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";
import * as api from "./api";
import { ApiError } from "../../lib/apiClient";
import { clearToken, getToken, setToken } from "./session";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, getMe: vi.fn(), updateMe: vi.fn() };
});

const ME: api.MeResponse = {
  user_id: "u1", phone_number: "+919999999999", email: null,
  onboarding_step: "q2_investing", onboarding_completed: false,
  investor_type: null, primary_goal: null,
};

describe("AuthContext", () => {
  afterEach(() => {
    vi.clearAllMocks();
    clearToken();
  });

  it("resolves loading=false with no session when no token is stored", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.token).toBeNull();
    expect(result.current.me).toBeNull();
    expect(api.getMe).not.toHaveBeenCalled();
  });

  it("resolves with me populated when a valid token is stored", async () => {
    setToken("tok-1");
    vi.mocked(api.getMe).mockResolvedValue(ME);

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.token).toBe("tok-1");
    expect(result.current.me).toEqual(ME);
  });

  it("clears the stored token when resume gets a 401", async () => {
    setToken("stale-tok");
    vi.mocked(api.getMe).mockRejectedValue(new ApiError(401, "Invalid or expired session."));

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.token).toBeNull();
    expect(result.current.me).toBeNull();
    expect(getToken()).toBeNull();
  });

  it("login stores the token and populates me", async () => {
    vi.mocked(api.getMe).mockResolvedValue(ME);
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.login("new-tok");
    });

    expect(result.current.token).toBe("new-tok");
    expect(result.current.me).toEqual(ME);
    expect(getToken()).toBe("new-tok");
  });

  it("logout clears the token and me", async () => {
    setToken("tok-1");
    vi.mocked(api.getMe).mockResolvedValue(ME);
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.logout();
    });

    expect(result.current.token).toBeNull();
    expect(result.current.me).toBeNull();
    expect(getToken()).toBeNull();
  });

  it("updateMe calls the API and syncs the returned me into context", async () => {
    setToken("tok-1");
    vi.mocked(api.getMe).mockResolvedValue(ME);
    const updated = { ...ME, onboarding_step: "q3_purpose" };
    vi.mocked(api.updateMe).mockResolvedValue(updated);
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.updateMe({ onboarding_step: "q3_purpose" });
    });

    expect(api.updateMe).toHaveBeenCalledWith({ onboarding_step: "q3_purpose" });
    expect(result.current.me?.onboarding_step).toBe("q3_purpose");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- AuthContext.test.tsx`
Expected: FAIL — `./AuthContext` doesn't exist yet.

- [ ] **Step 3: Implement `AuthContext`**

```tsx
// frontend/src/features/auth/AuthContext.tsx
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getMe, updateMe as apiUpdateMe } from "./api";
import { clearToken, getToken, setToken } from "./session";
import type { MeResponse, UpdateMeBody } from "./types";

interface AuthContextValue {
  token: string | null;
  me: MeResponse | null;
  loading: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
  updateMe: (body: UpdateMeBody) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function resume() {
      const stored = getToken();
      if (!stored) {
        setLoading(false);
        return;
      }
      try {
        const meResponse = await getMe();
        if (!cancelled) {
          setTokenState(stored);
          setMe(meResponse);
        }
      } catch {
        clearToken();
        if (!cancelled) {
          setTokenState(null);
          setMe(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void resume();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = async (newToken: string) => {
    setToken(newToken);
    setTokenState(newToken);
    const meResponse = await getMe();
    setMe(meResponse);
  };

  const logout = () => {
    clearToken();
    setTokenState(null);
    setMe(null);
  };

  const updateMe = async (body: UpdateMeBody) => {
    const updated = await apiUpdateMe(body);
    setMe(updated);
  };

  return (
    <AuthContext.Provider value={{ token, me, loading, login, logout, updateMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- AuthContext.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/features/auth/AuthContext.tsx src/features/auth/AuthContext.test.tsx
git commit -m "feat: add AuthContext for session resume, login, logout, updateMe"
```

---

### Task 5: Onboarding step vocabulary + back-navigation history reducer

**Files:**
- Create: `frontend/src/features/auth/onboardingSteps.ts`
- Create: `frontend/src/features/auth/onboardingHistory.ts`
- Test: `frontend/src/features/auth/onboardingHistory.test.ts`

**Interfaces:**
- Produces: `ONBOARDING_STEPS: readonly OnboardingStep[]`, `type OnboardingStep`
  from `onboardingSteps.ts`.
- Produces: `type HistoryState = { order: OnboardingStep[]; cursor: number; skipped: Set<OnboardingStep> }`,
  `initHistory(first: OnboardingStep): HistoryState`,
  `currentStep(state: HistoryState): OnboardingStep`,
  `goNext(state: HistoryState, next: OnboardingStep): HistoryState`,
  `goBack(state: HistoryState): HistoryState`,
  `skipToNext(state: HistoryState, next: OnboardingStep): HistoryState`,
  `markAnswered(state: HistoryState): HistoryState`,
  `isSkipped(state: HistoryState, step: OnboardingStep): boolean`
  from `onboardingHistory.ts` — `OnboardingFlow` (Task 7) is a thin wrapper
  around these.

This is the one piece of genuinely new state-machine logic in the whole
feature (per the design spec's Testing section) — it gets full unit
coverage in isolation, with no React involved.

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/features/auth/onboardingHistory.test.ts
import { describe, expect, it } from "vitest";
import {
  currentStep,
  goBack,
  goNext,
  initHistory,
  isSkipped,
  markAnswered,
  skipToNext,
} from "./onboardingHistory";

describe("onboarding history", () => {
  it("starts at the given first step", () => {
    const state = initHistory("trust_primer");
    expect(currentStep(state)).toBe("trust_primer");
  });

  it("goNext appends and moves the cursor forward", () => {
    let state = initHistory("trust_primer");
    state = goNext(state, "q1_name");
    expect(currentStep(state)).toBe("q1_name");
  });

  it("goBack moves the cursor back without losing the forward step", () => {
    let state = initHistory("trust_primer");
    state = goNext(state, "q1_name");
    state = goBack(state);
    expect(currentStep(state)).toBe("trust_primer");
  });

  it("goNext after goBack retraces the same path (no duplicate entry)", () => {
    let state = initHistory("trust_primer");
    state = goNext(state, "q1_name");
    state = goNext(state, "q2_investing");
    state = goBack(state);
    expect(currentStep(state)).toBe("q1_name");
    state = goNext(state, "q2_investing");
    expect(currentStep(state)).toBe("q2_investing");
    expect(state.order).toEqual(["trust_primer", "q1_name", "q2_investing"]);
  });

  it("goNext with a different step after going back truncates and replaces the tail", () => {
    let state = initHistory("trust_primer");
    state = goNext(state, "q1_name");
    state = goNext(state, "q4_household");
    state = goBack(state);
    state = goNext(state, "add_family");
    expect(currentStep(state)).toBe("add_family");
    expect(state.order).toEqual(["trust_primer", "q1_name", "add_family"]);
  });

  it("goBack at the first step is a no-op", () => {
    const state = goBack(initHistory("trust_primer"));
    expect(currentStep(state)).toBe("trust_primer");
  });

  it("skipToNext marks the current step skipped and advances", () => {
    let state = initHistory("q2_investing");
    state = skipToNext(state, "q3_purpose");
    expect(currentStep(state)).toBe("q3_purpose");
    expect(isSkipped(state, "q2_investing")).toBe(true);
  });

  it("markAnswered clears the skipped flag for the current step", () => {
    let state = initHistory("q2_investing");
    state = skipToNext(state, "q3_purpose");
    state = goBack(state);
    expect(isSkipped(state, "q2_investing")).toBe(true);
    state = markAnswered(state);
    expect(isSkipped(state, "q2_investing")).toBe(false);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- onboardingHistory.test.ts`
Expected: FAIL — neither module exists yet.

- [ ] **Step 3: Implement the step vocabulary**

```typescript
// frontend/src/features/auth/onboardingSteps.ts
export const ONBOARDING_STEPS = [
  "landing",
  "phone",
  "otp",
  "trust_primer",
  "q1_name",
  "q2_investing",
  "q3_purpose",
  "q4_household",
  "add_family",
  "cas_upload",
  "family_cas_upload",
  "upload_my_cas",
  "parse_queue",
  "done",
] as const;

export type OnboardingStep = (typeof ONBOARDING_STEPS)[number];

export function isOnboardingStep(value: string | null | undefined): value is OnboardingStep {
  return (ONBOARDING_STEPS as readonly string[]).includes(value ?? "");
}
```

- [ ] **Step 4: Implement the history reducer**

```typescript
// frontend/src/features/auth/onboardingHistory.ts
import type { OnboardingStep } from "./onboardingSteps";

export interface HistoryState {
  order: OnboardingStep[];
  cursor: number;
  skipped: Set<OnboardingStep>;
}

export function initHistory(first: OnboardingStep): HistoryState {
  return { order: [first], cursor: 0, skipped: new Set() };
}

export function currentStep(state: HistoryState): OnboardingStep {
  return state.order[state.cursor];
}

export function goNext(state: HistoryState, next: OnboardingStep): HistoryState {
  const nextIndex = state.cursor + 1;
  if (state.order[nextIndex] === next) {
    return { ...state, cursor: nextIndex };
  }
  return { ...state, order: [...state.order.slice(0, nextIndex), next], cursor: nextIndex };
}

export function goBack(state: HistoryState): HistoryState {
  if (state.cursor === 0) {
    return state;
  }
  return { ...state, cursor: state.cursor - 1 };
}

export function skipToNext(state: HistoryState, next: OnboardingStep): HistoryState {
  const skipped = new Set(state.skipped);
  skipped.add(currentStep(state));
  return goNext({ ...state, skipped }, next);
}

export function markAnswered(state: HistoryState): HistoryState {
  if (!state.skipped.has(currentStep(state))) {
    return state;
  }
  const skipped = new Set(state.skipped);
  skipped.delete(currentStep(state));
  return { ...state, skipped };
}

export function isSkipped(state: HistoryState, step: OnboardingStep): boolean {
  return state.skipped.has(step);
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npm test -- onboardingHistory.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/features/auth/onboardingSteps.ts src/features/auth/onboardingHistory.ts src/features/auth/onboardingHistory.test.ts
git commit -m "feat: add onboarding step vocabulary and back-navigation history reducer"
```

---

### Task 6: Landing, Phone Entry, OTP Verify (`AuthEntryFlow`)

**Files:**
- Create: `frontend/src/features/auth/Landing.tsx`
- Create: `frontend/src/features/auth/PhoneEntry.tsx`
- Create: `frontend/src/features/auth/OtpVerify.tsx`
- Create: `frontend/src/features/auth/AuthEntryFlow.tsx`
- Create: `frontend/src/features/auth/onboarding.module.css`
- Test: `frontend/src/features/auth/AuthEntryFlow.test.tsx`

**Interfaces:**
- Consumes: `requestOtp`, `verifyOtp` from `./api` (Task 3); `useAuth` from
  `./AuthContext` (Task 4); `ApiError` from `../../lib/apiClient` (Task 1).
- Produces: `AuthEntryFlow()` — the component `App.tsx` (Task 11) mounts
  when there's no valid session.

This is the S23 → S0 → S1 sequence as one deliverable: a user can sign up
or log in, end to end, via phone + OTP.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/features/auth/AuthEntryFlow.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthEntryFlow } from "./AuthEntryFlow";
import { AuthProvider } from "./AuthContext";
import * as api from "./api";
import { ApiError } from "../../lib/apiClient";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, requestOtp: vi.fn(), verifyOtp: vi.fn(), getMe: vi.fn() };
});

function renderFlow() {
  return render(
    <AuthProvider>
      <AuthEntryFlow />
    </AuthProvider>,
  );
}

describe("AuthEntryFlow", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows Sign Up and Log In on the landing screen, both leading to phone entry", async () => {
    renderFlow();
    await waitFor(() => expect(screen.getByRole("button", { name: /sign up/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /sign up/i }));

    expect(screen.getByLabelText(/phone number/i)).toBeInTheDocument();
  });

  it("moves from phone entry to OTP verify after a successful request", async () => {
    vi.mocked(api.requestOtp).mockResolvedValue({ message: "OTP sent.", otp: "654321" });
    renderFlow();
    await waitFor(() => screen.getByRole("button", { name: /sign up/i }));
    fireEvent.click(screen.getByRole("button", { name: /sign up/i }));

    fireEvent.change(screen.getByLabelText(/phone number/i), { target: { value: "+919999999999" } });
    fireEvent.click(screen.getByRole("button", { name: /send otp/i }));

    await waitFor(() => expect(screen.getByLabelText(/6-digit code/i)).toBeInTheDocument());
    expect(screen.getByText(/654321/)).toBeInTheDocument();
  });

  it("logs in on successful OTP verification", async () => {
    vi.mocked(api.requestOtp).mockResolvedValue({ message: "OTP sent.", otp: "654321" });
    vi.mocked(api.verifyOtp).mockResolvedValue({
      session_token: "tok-1", user_id: "u1", onboarding_step: null, onboarding_completed: false,
    });
    vi.mocked(api.getMe).mockResolvedValue({
      user_id: "u1", phone_number: "+919999999999", email: null,
      onboarding_step: null, onboarding_completed: false, investor_type: null, primary_goal: null,
    });
    renderFlow();
    await waitFor(() => screen.getByRole("button", { name: /sign up/i }));
    fireEvent.click(screen.getByRole("button", { name: /sign up/i }));
    fireEvent.change(screen.getByLabelText(/phone number/i), { target: { value: "+919999999999" } });
    fireEvent.click(screen.getByRole("button", { name: /send otp/i }));
    await waitFor(() => screen.getByLabelText(/6-digit code/i));

    fireEvent.change(screen.getByLabelText(/6-digit code/i), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: /^verify$/i }));

    await waitFor(() => expect(api.verifyOtp).toHaveBeenCalledWith("+919999999999", "654321"));
  });

  it("shows an inline error when OTP verification fails", async () => {
    vi.mocked(api.requestOtp).mockResolvedValue({ message: "OTP sent.", otp: "654321" });
    vi.mocked(api.verifyOtp).mockRejectedValue(new ApiError(401, "Invalid or expired OTP."));
    renderFlow();
    await waitFor(() => screen.getByRole("button", { name: /sign up/i }));
    fireEvent.click(screen.getByRole("button", { name: /sign up/i }));
    fireEvent.change(screen.getByLabelText(/phone number/i), { target: { value: "+919999999999" } });
    fireEvent.click(screen.getByRole("button", { name: /send otp/i }));
    await waitFor(() => screen.getByLabelText(/6-digit code/i));

    fireEvent.change(screen.getByLabelText(/6-digit code/i), { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: /^verify$/i }));

    await waitFor(() => expect(screen.getByText(/invalid or expired otp/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- AuthEntryFlow.test.tsx`
Expected: FAIL — none of the components exist yet.

- [ ] **Step 3: Create the shared onboarding CSS module**

```css
/* frontend/src/features/auth/onboarding.module.css */
.container {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 420px;
  margin: 0 auto;
  padding: var(--space-8);
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--type-body-size);
}

.field input,
.field select {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  font-size: var(--type-body-size);
  background: var(--color-surface);
  color: var(--color-ink);
}

.actions {
  display: flex;
  gap: var(--space-3);
}

.error {
  color: var(--color-negative);
  font-size: var(--type-caption-size);
  margin: 0;
}

.hint {
  color: var(--color-text-secondary);
  font-size: var(--type-caption-size);
  margin: 0;
}
```

- [ ] **Step 4: Create `Landing.tsx`**

```tsx
// frontend/src/features/auth/Landing.tsx
import styles from "./onboarding.module.css";

interface LandingProps {
  onContinue: () => void;
}

export function Landing({ onContinue }: LandingProps) {
  return (
    <div className={styles.container}>
      <h1>Unifolio</h1>
      <p>Track every mutual fund you own, in one place.</p>
      <div className={styles.actions}>
        <button type="button" onClick={onContinue}>
          Sign Up
        </button>
        <button type="button" onClick={onContinue}>
          Log In
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create `PhoneEntry.tsx`**

```tsx
// frontend/src/features/auth/PhoneEntry.tsx
import { useState } from "react";
import type { FormEvent } from "react";
import styles from "./onboarding.module.css";

interface PhoneEntryProps {
  onSubmit: (phoneNumber: string) => void;
  submitting: boolean;
  error: string | null;
}

export function PhoneEntry({ onSubmit, submitting, error }: PhoneEntryProps) {
  const [phoneNumber, setPhoneNumber] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(phoneNumber);
  };

  return (
    <form className={styles.container} onSubmit={handleSubmit}>
      <h1>Enter your phone number</h1>
      <label className={styles.field}>
        Phone number
        <input
          type="tel"
          value={phoneNumber}
          onChange={(event) => setPhoneNumber(event.target.value)}
        />
      </label>
      {error && <p className={styles.error}>{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Sending..." : "Send OTP"}
      </button>
    </form>
  );
}
```

- [ ] **Step 6: Create `OtpVerify.tsx`**

```tsx
// frontend/src/features/auth/OtpVerify.tsx
import { useState } from "react";
import type { FormEvent } from "react";
import styles from "./onboarding.module.css";

interface OtpVerifyProps {
  phoneNumber: string;
  onSubmit: (otp: string) => void;
  onResend: () => void;
  submitting: boolean;
  error: string | null;
  devOtp: string | null;
}

export function OtpVerify({ phoneNumber, onSubmit, onResend, submitting, error, devOtp }: OtpVerifyProps) {
  const [otp, setOtp] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(otp);
  };

  return (
    <form className={styles.container} onSubmit={handleSubmit}>
      <h1>Enter the code we sent to {phoneNumber}</h1>
      {devOtp && <p className={styles.hint}>Dev mode OTP: {devOtp}</p>}
      <label className={styles.field}>
        6-digit code
        <input
          type="text"
          inputMode="numeric"
          maxLength={6}
          value={otp}
          onChange={(event) => setOtp(event.target.value)}
        />
      </label>
      {error && <p className={styles.error}>{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Verifying..." : "Verify"}
      </button>
      <button type="button" onClick={onResend}>
        Resend code
      </button>
    </form>
  );
}
```

- [ ] **Step 7: Create `AuthEntryFlow.tsx`**

```tsx
// frontend/src/features/auth/AuthEntryFlow.tsx
import { useState } from "react";
import { Landing } from "./Landing";
import { PhoneEntry } from "./PhoneEntry";
import { OtpVerify } from "./OtpVerify";
import { requestOtp, verifyOtp } from "./api";
import { useAuth } from "./AuthContext";
import { ApiError } from "../../lib/apiClient";

type Step = "landing" | "phone" | "otp";

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.payload === "string") {
    return err.payload;
  }
  return fallback;
}

export function AuthEntryFlow() {
  const { login } = useAuth();
  const [step, setStep] = useState<Step>("landing");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devOtp, setDevOtp] = useState<string | null>(null);

  const handlePhoneSubmit = async (phone: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await requestOtp(phone);
      setPhoneNumber(phone);
      setDevOtp(result.otp);
      setStep("otp");
    } catch (err) {
      setError(errorMessage(err, "Couldn't send the code. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const handleOtpSubmit = async (otp: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await verifyOtp(phoneNumber, otp);
      await login(result.session_token);
    } catch (err) {
      setError(errorMessage(err, "That code didn't work. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  if (step === "landing") {
    return <Landing onContinue={() => setStep("phone")} />;
  }
  if (step === "phone") {
    return <PhoneEntry onSubmit={handlePhoneSubmit} submitting={submitting} error={error} />;
  }
  return (
    <OtpVerify
      phoneNumber={phoneNumber}
      onSubmit={handleOtpSubmit}
      onResend={() => setStep("phone")}
      submitting={submitting}
      error={error}
      devOtp={devOtp}
    />
  );
}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd frontend && npm test -- AuthEntryFlow.test.tsx`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/features/auth/Landing.tsx src/features/auth/PhoneEntry.tsx src/features/auth/OtpVerify.tsx src/features/auth/AuthEntryFlow.tsx src/features/auth/AuthEntryFlow.test.tsx src/features/auth/onboarding.module.css
git commit -m "feat: add Landing/Phone/OTP auth entry flow (S23-S1)"
```

---

### Task 7: `OnboardingFlow` skeleton + Trust Primer + Q1-Q4

**Files:**
- Create: `frontend/src/features/auth/OnboardingFlow.tsx`
- Create: `frontend/src/features/auth/TrustPrimer.tsx`
- Create: `frontend/src/features/auth/Q1Name.tsx`
- Create: `frontend/src/features/auth/Q2Investing.tsx`
- Create: `frontend/src/features/auth/Q3Purpose.tsx`
- Create: `frontend/src/features/auth/Q4Household.tsx`
- Test: `frontend/src/features/auth/OnboardingFlow.test.tsx`

**Interfaces:**
- Consumes: `useAuth` (Task 4); `initHistory`, `currentStep`, `goNext`,
  `goBack`, `skipToNext`, `isSkipped` from `./onboardingHistory` (Task 5);
  `isOnboardingStep`, `OnboardingStep` from `./onboardingSteps` (Task 5).
- Produces: `OnboardingFlow()` — mounted by `App.tsx` (Task 11) whenever
  `me.onboarding_completed === false`. Stops rendering real screens at
  `q4_household`'s two branches (`add_family` and `cas_upload`) — those
  two destinations are built in Tasks 8 and 9 respectively and wired in at
  the end of this task with a placeholder `<p>` each, replaced for real in
  those tasks.
- Produces (for Task 8/9/10 to consume): `answers.name: string`,
  `answers.investorType: InvestorType | null`, `answers.primaryGoal: PrimaryGoal | null`,
  `answers.familyMembers: HouseholdMember[]` held in `OnboardingFlow`'s
  local state — Tasks 8-10 add the screens that read/write these.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/features/auth/OnboardingFlow.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OnboardingFlow } from "./OnboardingFlow";
import { AuthProvider } from "./AuthContext";
import * as api from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, getMe: vi.fn(), updateMe: vi.fn() };
});

const BASE_ME: api.MeResponse = {
  user_id: "u1", phone_number: "+919999999999", email: null,
  onboarding_step: null, onboarding_completed: false, investor_type: null, primary_goal: null,
};

function renderFlow() {
  vi.mocked(api.getMe).mockResolvedValue(BASE_ME);
  vi.mocked(api.updateMe).mockImplementation(async (body) => ({ ...BASE_ME, ...body }) as api.MeResponse);
  return render(
    <AuthProvider>
      <OnboardingFlow />
    </AuthProvider>,
  );
}

describe("OnboardingFlow", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("starts at Trust Primer and walks forward through Q1-Q4 to the household branch", async () => {
    renderFlow();
    await waitFor(() => expect(screen.getByRole("button", { name: /continue/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => expect(screen.getByLabelText(/what should we call you/i)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/what should we call you/i), { target: { value: "Ayush" } });
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));

    await waitFor(() => expect(screen.getByText(/how are you investing right now/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /mostly on my own/i }));

    await waitFor(() => expect(screen.getByText(/what brings you to unifolio/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /see all my mutual funds/i }));

    await waitFor(() => expect(screen.getByText(/just you, or tracking for family too/i)).toBeInTheDocument());
  });

  it("supports Back navigation from Q2 to Q1 with the answer preserved", async () => {
    renderFlow();
    await waitFor(() => screen.getByRole("button", { name: /continue/i }));
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => screen.getByLabelText(/what should we call you/i));
    fireEvent.change(screen.getByLabelText(/what should we call you/i), { target: { value: "Ayush" } });
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));
    await waitFor(() => screen.getByText(/how are you investing right now/i));

    fireEvent.click(screen.getByRole("button", { name: /^back$/i }));

    await waitFor(() => expect(screen.getByLabelText(/what should we call you/i)).toHaveValue("Ayush"));
  });

  it("skipping Q2 still allows reaching it again via Back later", async () => {
    renderFlow();
    await waitFor(() => screen.getByRole("button", { name: /continue/i }));
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => screen.getByLabelText(/what should we call you/i));
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));
    await waitFor(() => screen.getByText(/how are you investing right now/i));

    fireEvent.click(screen.getByRole("button", { name: /^skip$/i }));
    await waitFor(() => expect(screen.getByText(/what brings you to unifolio/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /^back$/i }));
    await waitFor(() => expect(screen.getByText(/how are you investing right now/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- OnboardingFlow.test.tsx`
Expected: FAIL — none of these components exist yet.

- [ ] **Step 3: Create `TrustPrimer.tsx`**

```tsx
// frontend/src/features/auth/TrustPrimer.tsx
import styles from "./onboarding.module.css";

interface TrustPrimerProps {
  onContinue: () => void;
}

export function TrustPrimer({ onContinue }: TrustPrimerProps) {
  return (
    <div className={styles.container}>
      <h1>Before we start</h1>
      <p>Unifolio only ever reads your portfolio data — nothing is bought, sold, or moved.</p>
      <p>Your CAS data is never sold. You can revoke access at any time.</p>
      <button type="button" onClick={onContinue}>
        Continue
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Create `Q1Name.tsx`**

```tsx
// frontend/src/features/auth/Q1Name.tsx
import { useState } from "react";
import type { FormEvent } from "react";
import styles from "./onboarding.module.css";

interface Q1NameProps {
  value: string;
  onBack?: () => void;
  onSkip: () => void;
  onSubmit: (name: string) => void;
}

export function Q1Name({ value, onBack, onSkip, onSubmit }: Q1NameProps) {
  const [name, setName] = useState(value);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(name);
  };

  return (
    <form className={styles.container} onSubmit={handleSubmit}>
      <h1>What should we call you?</h1>
      <label className={styles.field}>
        What should we call you?
        <input value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <div className={styles.actions}>
        {onBack && (
          <button type="button" onClick={onBack}>
            Back
          </button>
        )}
        <button type="button" onClick={onSkip}>
          Skip
        </button>
        <button type="submit">Next</button>
      </div>
    </form>
  );
}
```

- [ ] **Step 5: Create `Q2Investing.tsx`**

```tsx
// frontend/src/features/auth/Q2Investing.tsx
import styles from "./onboarding.module.css";
import type { InvestorType } from "./types";

interface Q2InvestingProps {
  onBack: () => void;
  onSkip: () => void;
  onSelect: (value: InvestorType) => void;
}

const OPTIONS: { value: InvestorType; label: string }[] = [
  { value: "self_directed", label: "Mostly on my own — SIPs, mutual funds, maybe some stocks" },
  { value: "advisor_assisted", label: "Through a distributor, bank RM, or family office, alongside my own tracking" },
  { value: "mixed", label: "A mix of both" },
  { value: "beginner", label: "Just getting started — haven't invested much yet" },
];

export function Q2Investing({ onBack, onSkip, onSelect }: Q2InvestingProps) {
  return (
    <div className={styles.container}>
      <h1>How are you investing right now?</h1>
      {OPTIONS.map((option) => (
        <button key={option.value} type="button" onClick={() => onSelect(option.value)}>
          {option.label}
        </button>
      ))}
      <div className={styles.actions}>
        <button type="button" onClick={onBack}>
          Back
        </button>
        <button type="button" onClick={onSkip}>
          Skip
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Create `Q3Purpose.tsx`**

```tsx
// frontend/src/features/auth/Q3Purpose.tsx
import styles from "./onboarding.module.css";
import type { PrimaryGoal } from "./types";

interface Q3PurposeProps {
  onBack: () => void;
  onSkip: () => void;
  onSelect: (value: PrimaryGoal) => void;
}

const OPTIONS: { value: PrimaryGoal; label: string }[] = [
  { value: "consolidated_view", label: "See all my mutual funds in one place" },
  { value: "understand_holdings", label: "Actually understand what I'm invested in" },
  { value: "family_management", label: "Managing investments for my family, not just myself" },
  { value: "performance_comparison", label: "Compare how my funds are really performing" },
];

export function Q3Purpose({ onBack, onSkip, onSelect }: Q3PurposeProps) {
  return (
    <div className={styles.container}>
      <h1>What brings you to Unifolio?</h1>
      {OPTIONS.map((option) => (
        <button key={option.value} type="button" onClick={() => onSelect(option.value)}>
          {option.label}
        </button>
      ))}
      <div className={styles.actions}>
        <button type="button" onClick={onBack}>
          Back
        </button>
        <button type="button" onClick={onSkip}>
          Skip
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Create `Q4Household.tsx`**

```tsx
// frontend/src/features/auth/Q4Household.tsx
import styles from "./onboarding.module.css";

interface Q4HouseholdProps {
  onBack: () => void;
  onChooseSolo: () => void;
  onChooseFamily: () => void;
}

export function Q4Household({ onBack, onChooseSolo, onChooseFamily }: Q4HouseholdProps) {
  return (
    <div className={styles.container}>
      <h1>Just you, or tracking for family too?</h1>
      <div className={styles.actions}>
        <button type="button" onClick={onChooseSolo}>
          Just me
        </button>
        <button type="button" onClick={onChooseFamily}>
          Family too
        </button>
      </div>
      <button type="button" onClick={onBack}>
        Back
      </button>
    </div>
  );
}
```

- [ ] **Step 8: Create `OnboardingFlow.tsx`**

```tsx
// frontend/src/features/auth/OnboardingFlow.tsx
import { useEffect, useState } from "react";
import { useAuth } from "./AuthContext";
import { currentStep, goBack, goNext, initHistory, isSkipped, markAnswered, skipToNext } from "./onboardingHistory";
import type { HistoryState } from "./onboardingHistory";
import { isOnboardingStep } from "./onboardingSteps";
import type { OnboardingStep } from "./onboardingSteps";
import { TrustPrimer } from "./TrustPrimer";
import { Q1Name } from "./Q1Name";
import { Q2Investing } from "./Q2Investing";
import { Q3Purpose } from "./Q3Purpose";
import { Q4Household } from "./Q4Household";
import type { HouseholdMember, InvestorType, PrimaryGoal } from "./types";

export interface OnboardingAnswers {
  name: string;
  investorType: InvestorType | null;
  primaryGoal: PrimaryGoal | null;
  familyMembers: HouseholdMember[];
}

const INITIAL_ANSWERS: OnboardingAnswers = {
  name: "",
  investorType: null,
  primaryGoal: null,
  familyMembers: [],
};

function resumeStep(step: string | null | undefined): OnboardingStep {
  return isOnboardingStep(step) && step !== "done" ? step : "trust_primer";
}

export function OnboardingFlow() {
  const { me, updateMe } = useAuth();
  const [history, setHistory] = useState<HistoryState>(() => initHistory(resumeStep(me?.onboarding_step)));
  const [answers, setAnswers] = useState<OnboardingAnswers>(INITIAL_ANSWERS);

  const step = currentStep(history);

  useEffect(() => {
    if (step !== "done") {
      void updateMe({ onboarding_step: step });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const advance = (next: OnboardingStep) => setHistory((h) => goNext(markAnswered(h), next));
  const back = () => setHistory((h) => goBack(h));
  const skip = (next: OnboardingStep) => setHistory((h) => skipToNext(h, next));
  const showBack = history.cursor > 0;

  if (step === "trust_primer") {
    return <TrustPrimer onContinue={() => advance("q1_name")} />;
  }

  if (step === "q1_name") {
    return (
      <Q1Name
        value={answers.name}
        onBack={showBack ? back : undefined}
        onSkip={() => skip("q2_investing")}
        onSubmit={(name) => {
          setAnswers((a) => ({ ...a, name }));
          advance("q2_investing");
        }}
      />
    );
  }

  if (step === "q2_investing") {
    return (
      <Q2Investing
        onBack={back}
        onSkip={() => skip("q3_purpose")}
        onSelect={(investorType) => {
          setAnswers((a) => ({ ...a, investorType }));
          advance("q3_purpose");
        }}
      />
    );
  }

  if (step === "q3_purpose") {
    return (
      <Q3Purpose
        onBack={back}
        onSkip={() => skip("q4_household")}
        onSelect={(primaryGoal) => {
          setAnswers((a) => ({ ...a, primaryGoal }));
          advance("q4_household");
        }}
      />
    );
  }

  if (step === "q4_household") {
    return (
      <Q4Household
        onBack={back}
        onChooseSolo={() => advance("cas_upload")}
        onChooseFamily={() => advance("add_family")}
      />
    );
  }

  if (step === "add_family") {
    return <p>Add Family Members — built in Task 8.</p>;
  }

  if (step === "cas_upload") {
    return <p>Solo CAS Upload — built in Task 9.</p>;
  }

  if (step === "family_cas_upload" || step === "upload_my_cas" || step === "parse_queue") {
    return <p>Family CAS Upload — built in Task 10.</p>;
  }

  return null;
}

export { isSkipped };
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `cd frontend && npm test -- OnboardingFlow.test.tsx`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add src/features/auth/OnboardingFlow.tsx src/features/auth/OnboardingFlow.test.tsx src/features/auth/TrustPrimer.tsx src/features/auth/Q1Name.tsx src/features/auth/Q2Investing.tsx src/features/auth/Q3Purpose.tsx src/features/auth/Q4Household.tsx
git commit -m "feat: add OnboardingFlow skeleton with Trust Primer and Q1-Q4"
```

---

### Task 8: Add Family Members (S7)

**Files:**
- Create: `frontend/src/features/auth/AddFamilyMembers.tsx`
- Test: `frontend/src/features/auth/AddFamilyMembers.test.tsx`
- Modify: `frontend/src/features/auth/OnboardingFlow.tsx`

**Interfaces:**
- Consumes: `createHouseholdMember` from `./api` (Task 3); `HouseholdMember`,
  `Relationship` from `./types` (Task 2).
- Produces: `AddFamilyMembers({ members, onMembersChange, onBack, onContinue })`
  props contract — wired into `OnboardingFlow`'s `add_family` branch,
  replacing the Task 7 placeholder.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/features/auth/AddFamilyMembers.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AddFamilyMembers } from "./AddFamilyMembers";
import * as api from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, createHouseholdMember: vi.fn() };
});

describe("AddFamilyMembers", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("adds a member and shows it in the list", async () => {
    vi.mocked(api.createHouseholdMember).mockResolvedValue({
      id: "m1", name: "Mom", relationship: "parent", relationship_other_label: null,
    });
    const onMembersChange = vi.fn();
    render(
      <AddFamilyMembers members={[]} onMembersChange={onMembersChange} onBack={vi.fn()} onContinue={vi.fn()} />,
    );

    fireEvent.change(screen.getByLabelText(/member's name/i), { target: { value: "Mom" } });
    fireEvent.change(screen.getByLabelText(/relationship/i), { target: { value: "parent" } });
    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));

    await waitFor(() => expect(api.createHouseholdMember).toHaveBeenCalledWith("Mom", "parent", undefined));
    await waitFor(() =>
      expect(onMembersChange).toHaveBeenCalledWith([
        { id: "m1", name: "Mom", relationship: "parent", relationship_other_label: null },
      ]),
    );
  });

  it("shows already-added members from props", () => {
    render(
      <AddFamilyMembers
        members={[{ id: "m1", name: "Dad", relationship: "parent", relationship_other_label: null }]}
        onMembersChange={vi.fn()}
        onBack={vi.fn()}
        onContinue={vi.fn()}
      />,
    );

    expect(screen.getByText("Dad")).toBeInTheDocument();
  });

  it("disables Continue until at least one member has been added", () => {
    render(<AddFamilyMembers members={[]} onMembersChange={vi.fn()} onBack={vi.fn()} onContinue={vi.fn()} />);

    expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
  });

  it("calls onContinue when Continue is clicked with members present", () => {
    const onContinue = vi.fn();
    render(
      <AddFamilyMembers
        members={[{ id: "m1", name: "Dad", relationship: "parent", relationship_other_label: null }]}
        onMembersChange={vi.fn()}
        onBack={vi.fn()}
        onContinue={onContinue}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    expect(onContinue).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- AddFamilyMembers.test.tsx`
Expected: FAIL — component doesn't exist yet.

- [ ] **Step 3: Implement `AddFamilyMembers.tsx`**

```tsx
// frontend/src/features/auth/AddFamilyMembers.tsx
import { useState } from "react";
import type { FormEvent } from "react";
import styles from "./onboarding.module.css";
import { createHouseholdMember } from "./api";
import type { HouseholdMember, Relationship } from "./types";

interface AddFamilyMembersProps {
  members: HouseholdMember[];
  onMembersChange: (members: HouseholdMember[]) => void;
  onBack: () => void;
  onContinue: () => void;
}

const RELATIONSHIPS: Relationship[] = ["spouse", "parent", "child", "sibling", "other"];

export function AddFamilyMembers({ members, onMembersChange, onBack, onContinue }: AddFamilyMembersProps) {
  const [name, setName] = useState("");
  const [relationship, setRelationship] = useState<Relationship>("parent");
  const [otherLabel, setOtherLabel] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAdd = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }
    setAdding(true);
    setError(null);
    try {
      const member = await createHouseholdMember(
        name.trim(),
        relationship,
        relationship === "other" ? otherLabel.trim() || undefined : undefined,
      );
      onMembersChange([...members, member]);
      setName("");
      setOtherLabel("");
    } catch {
      setError("Couldn't add that member. Please try again.");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className={styles.container}>
      <h1>Who else are you tracking for?</h1>

      <ul>
        {members.map((member) => (
          <li key={member.id}>{member.name}</li>
        ))}
      </ul>

      <form onSubmit={handleAdd} className={styles.container}>
        <label className={styles.field}>
          Member's name
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label className={styles.field}>
          Relationship
          <select
            value={relationship}
            onChange={(event) => setRelationship(event.target.value as Relationship)}
          >
            {RELATIONSHIPS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        {relationship === "other" && (
          <label className={styles.field}>
            Describe the relationship
            <input value={otherLabel} onChange={(event) => setOtherLabel(event.target.value)} />
          </label>
        )}
        {error && <p className={styles.error}>{error}</p>}
        <button type="submit" disabled={adding}>
          {adding ? "Adding..." : "Add"}
        </button>
      </form>

      <div className={styles.actions}>
        <button type="button" onClick={onBack}>
          Back
        </button>
        <button type="button" disabled={members.length === 0} onClick={onContinue}>
          Continue
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- AddFamilyMembers.test.tsx`
Expected: PASS

- [ ] **Step 5: Wire `AddFamilyMembers` into `OnboardingFlow`**

In `frontend/src/features/auth/OnboardingFlow.tsx`, add the import:

```typescript
import { AddFamilyMembers } from "./AddFamilyMembers";
```

Replace the `add_family` placeholder branch:

```tsx
  if (step === "add_family") {
    return <p>Add Family Members — built in Task 8.</p>;
  }
```

with:

```tsx
  if (step === "add_family") {
    return (
      <AddFamilyMembers
        members={answers.familyMembers}
        onMembersChange={(familyMembers) => setAnswers((a) => ({ ...a, familyMembers }))}
        onBack={back}
        onContinue={() => advance("family_cas_upload")}
      />
    );
  }
```

- [ ] **Step 6: Run the full onboarding test file to confirm no regressions**

Run: `cd frontend && npm test -- OnboardingFlow.test.tsx AddFamilyMembers.test.tsx`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/features/auth/AddFamilyMembers.tsx src/features/auth/AddFamilyMembers.test.tsx src/features/auth/OnboardingFlow.tsx
git commit -m "feat: add Add Family Members screen (S7), wire into OnboardingFlow"
```

---

### Task 9: `ImportFlow`/`ImportConfirmed` prop extensions + Solo CAS Upload (S8, onboarding path)

**Files:**
- Modify: `frontend/src/features/import/ImportFlow.tsx`
- Modify: `frontend/src/features/import/ImportFlow.test.tsx`
- Modify: `frontend/src/features/import/ImportConfirmed.tsx`
- Modify: `frontend/src/features/import/ImportConfirmed.test.tsx`
- Create: `frontend/src/features/auth/SoloCasUpload.tsx`
- Test: `frontend/src/features/auth/SoloCasUpload.test.tsx`
- Modify: `frontend/src/features/auth/OnboardingFlow.tsx`

**Interfaces:**
- Produces (modified): `ImportFlow({ householdMemberId: string; ctaLabel?: string; onDone?: () => void })`
  (previously took no props) — `confirmImport` calls now pass `householdMemberId`.
- Produces (modified): `ImportConfirmed({ result, onImportAnother, ctaLabel?: string })`
  (default `ctaLabel = "Import another CAS"`, unchanged from before).
- Consumes: `listHouseholdMembers`, `createHouseholdMember` from `../auth/api`
  (Task 3); `useAuth` from `../auth/AuthContext` (Task 4).
- Produces: `SoloCasUpload({ name: string })` — wired into `OnboardingFlow`'s
  `cas_upload` branch, replacing the Task 7 placeholder.

- [ ] **Step 1: Update `ImportConfirmed.tsx`'s failing test first**

Add one new test to `frontend/src/features/import/ImportConfirmed.test.tsx`
(keep the existing two tests unchanged — they must keep passing to prove
the default behavior is preserved):

```tsx
  it("uses a custom ctaLabel when provided", () => {
    const onImportAnother = vi.fn();
    render(
      <ImportConfirmed
        result={{ added: 2, skipped: 0, import_id: "imp1" }}
        onImportAnother={onImportAnother}
        ctaLabel="Continue"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
    expect(onImportAnother).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /import another cas/i })).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- ImportConfirmed.test.tsx`
Expected: FAIL — `ctaLabel` prop doesn't exist yet.

- [ ] **Step 3: Add the `ctaLabel` prop to `ImportConfirmed.tsx`**

```tsx
// frontend/src/features/import/ImportConfirmed.tsx
import type { ImportConfirmResponse } from "./types";
import styles from "./ImportConfirmed.module.css";

interface ImportConfirmedProps {
  result: ImportConfirmResponse;
  onImportAnother: () => void;
  ctaLabel?: string;
}

export function ImportConfirmed({ result, onImportAnother, ctaLabel = "Import another CAS" }: ImportConfirmedProps) {
  const addedText = `${result.added} new transaction${result.added === 1 ? "" : "s"} added`;
  const skippedText =
    result.skipped > 0 ? `, ${result.skipped} duplicate${result.skipped === 1 ? "" : "s"} skipped` : "";

  return (
    <div className={styles.container}>
      <h1>Import complete</h1>
      <p>{`${addedText}${skippedText}.`}</p>
      <button type="button" onClick={onImportAnother}>
        {ctaLabel}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- ImportConfirmed.test.tsx`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Update `ImportFlow.test.tsx` for the new required prop**

Every `render(<ImportFlow />)` call in
`frontend/src/features/import/ImportFlow.test.tsx` must become
`render(<ImportFlow householdMemberId="member-1" />)`. Also update the
"moves to confirmed on a successful confirm" test's assertion to check
`confirmImport` was called with the member id, and add one new test for
the `ctaLabel`/`onDone` overrides. The full updated file:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImportFlow } from "./ImportFlow";
import * as api from "./api";
import { ApiError } from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, parseImport: vi.fn(), confirmImport: vi.fn() };
});

function uploadAFile() {
  const file = new File(["pdf-bytes"], "cas.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText(/cas pdf/i), { target: { files: [file] } });
  fireEvent.change(screen.getByLabelText(/pdf password/i), { target: { value: "secret" } });
  fireEvent.click(screen.getByRole("button", { name: /upload/i }));
}

const EMPTY_PREVIEW = {
  session_id: "s1", filename: "cas.pdf", investor_name: "Test", investor_email: null,
  pan_masked: "A********F", schemes: [], transactions: [], transaction_count: 0,
  parse_warnings: [], cas_type: "DETAILED", file_type: "FileType.CAMS",
};

describe("ImportFlow", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("moves from upload to review on a successful parse", async () => {
    vi.mocked(api.parseImport).mockResolvedValue(EMPTY_PREVIEW);

    render(<ImportFlow householdMemberId="member-1" />);
    uploadAFile();

    await waitFor(() => expect(screen.getByText(/review cas import/i)).toBeInTheDocument());
  });

  it("moves to the error screen on a ParseError", async () => {
    vi.mocked(api.parseImport).mockRejectedValue(
      new ApiError(422, { code: "wrong_password", message: "Incorrect PDF password." }),
    );

    render(<ImportFlow householdMemberId="member-1" />);
    uploadAFile();

    await waitFor(() => expect(screen.getByText(/incorrect pdf password/i)).toBeInTheDocument());
  });

  it("shows a generic message on a network failure", async () => {
    vi.mocked(api.parseImport).mockRejectedValue(new TypeError("Failed to fetch"));

    render(<ImportFlow householdMemberId="member-1" />);
    uploadAFile();

    await waitFor(() => expect(screen.getByText(/couldn't reach the server/i)).toBeInTheDocument());
  });

  it("moves to confirmed on a successful confirm, passing the householdMemberId", async () => {
    vi.mocked(api.parseImport).mockResolvedValue(EMPTY_PREVIEW);
    vi.mocked(api.confirmImport).mockResolvedValue({ added: 3, skipped: 1, import_id: "imp1" });

    render(<ImportFlow householdMemberId="member-1" />);
    uploadAFile();
    await waitFor(() => screen.getByRole("button", { name: /confirm import/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));

    await waitFor(() => expect(screen.getByText(/import complete/i)).toBeInTheDocument());
    expect(api.confirmImport).toHaveBeenCalledWith("s1", "member-1", []);
  });

  it("shows an inline notice instead of navigating away on a 409", async () => {
    vi.mocked(api.parseImport).mockResolvedValue(EMPTY_PREVIEW);
    vi.mocked(api.confirmImport).mockRejectedValue(new ApiError(409, "Scheme 'X' requires an explicit AMFI code."));

    render(<ImportFlow householdMemberId="member-1" />);
    uploadAFile();
    await waitFor(() => screen.getByRole("button", { name: /confirm import/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/requires an explicit amfi code/i));
    expect(screen.getByText(/review cas import/i)).toBeInTheDocument();
  });

  it("resets to upload from the confirmed screen by default", async () => {
    vi.mocked(api.parseImport).mockResolvedValue(EMPTY_PREVIEW);
    vi.mocked(api.confirmImport).mockResolvedValue({ added: 1, skipped: 0, import_id: "imp1" });

    render(<ImportFlow householdMemberId="member-1" />);
    uploadAFile();
    await waitFor(() => screen.getByRole("button", { name: /confirm import/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));
    await waitFor(() => screen.getByRole("button", { name: /import another cas/i }));
    fireEvent.click(screen.getByRole("button", { name: /import another cas/i }));

    expect(screen.getByRole("button", { name: /^upload$/i })).toBeInTheDocument();
  });

  it("uses ctaLabel and onDone instead of the default reset when provided", async () => {
    vi.mocked(api.parseImport).mockResolvedValue(EMPTY_PREVIEW);
    vi.mocked(api.confirmImport).mockResolvedValue({ added: 1, skipped: 0, import_id: "imp1" });
    const onDone = vi.fn();

    render(<ImportFlow householdMemberId="member-1" ctaLabel="Continue" onDone={onDone} />);
    uploadAFile();
    await waitFor(() => screen.getByRole("button", { name: /confirm import/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));
    await waitFor(() => screen.getByRole("button", { name: /^continue$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));

    expect(onDone).toHaveBeenCalled();
  });
});
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `cd frontend && npm test -- ImportFlow.test.tsx`
Expected: FAIL — `ImportFlow` doesn't accept `householdMemberId` yet.

- [ ] **Step 7: Update `ImportFlow.tsx`**

```tsx
// frontend/src/features/import/ImportFlow.tsx
import { useState } from "react";
import { UploadForm } from "./UploadForm";
import { ParsingIndicator } from "./ParsingIndicator";
import { ReviewTable } from "./ReviewTable";
import { ImportError } from "./ImportError";
import { ImportConfirmed } from "./ImportConfirmed";
import { ApiError, confirmImport, parseImport } from "./api";
import type {
  ImportConfirmResponse,
  ImportPreviewResponse,
  ParseErrorPayload,
  SchemeConfirmation,
} from "./types";

type Step = "upload" | "parsing" | "review" | "error" | "confirmed";

interface ImportFlowProps {
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
    return typeof err.payload === "string" ? { code: "error", message: err.payload } : err.payload;
  }
  return GENERIC_NETWORK_ERROR;
}

export function ImportFlow({ householdMemberId, ctaLabel, onDone }: ImportFlowProps) {
  const [step, setStep] = useState<Step>("upload");
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [confirmResult, setConfirmResult] = useState<ImportConfirmResponse | null>(null);
  const [error, setError] = useState<ParseErrorPayload | null>(null);
  const [reviewNotice, setReviewNotice] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const reset = () => {
    setStep("upload");
    setPreview(null);
    setConfirmResult(null);
    setError(null);
    setReviewNotice(null);
    setConfirming(false);
  };

  const handleUpload = async (file: File, password: string) => {
    setStep("parsing");
    try {
      const result = await parseImport(file, password);
      setPreview(result);
      setStep("review");
    } catch (err) {
      setError(toParseErrorPayload(err));
      setStep("error");
    }
  };

  const handleConfirm = async (confirmations: SchemeConfirmation[]) => {
    if (!preview) return;
    setConfirming(true);
    setReviewNotice(null);
    try {
      const result = await confirmImport(preview.session_id, householdMemberId, confirmations);
      setConfirmResult(result);
      setStep("confirmed");
    } catch (err) {
      if (err instanceof ApiError && (err.status === 409 || err.status === 404)) {
        setReviewNotice(
          err.status === 404
            ? "This import session has expired. Please re-upload your CAS."
            : typeof err.payload === "string"
              ? err.payload
              : err.payload.message,
        );
      } else {
        setError(toParseErrorPayload(err));
        setStep("error");
      }
    } finally {
      setConfirming(false);
    }
  };

  if (step === "upload") {
    return <UploadForm onSubmit={handleUpload} />;
  }
  if (step === "parsing") {
    return <ParsingIndicator />;
  }
  if (step === "review" && preview) {
    return (
      <>
        {reviewNotice && <p role="alert">{reviewNotice}</p>}
        <ReviewTable preview={preview} confirming={confirming} onConfirm={handleConfirm} />
      </>
    );
  }
  if (step === "confirmed" && confirmResult) {
    return <ImportConfirmed result={confirmResult} onImportAnother={onDone ?? reset} ctaLabel={ctaLabel} />;
  }
  return <ImportError error={error ?? GENERIC_NETWORK_ERROR} onRetry={reset} />;
}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd frontend && npm test -- ImportFlow.test.tsx`
Expected: PASS (all 7 tests)

- [ ] **Step 9: Write the failing test for `SoloCasUpload`**

```tsx
// frontend/src/features/auth/SoloCasUpload.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SoloCasUpload } from "./SoloCasUpload";
import * as api from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, listHouseholdMembers: vi.fn(), createHouseholdMember: vi.fn() };
});

describe("SoloCasUpload", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("creates a self household member when none exists yet, then renders ImportFlow", async () => {
    vi.mocked(api.listHouseholdMembers).mockResolvedValue([]);
    vi.mocked(api.createHouseholdMember).mockResolvedValue({
      id: "self-1", name: "Ayush", relationship: "self", relationship_other_label: null,
    });

    render(<SoloCasUpload name="Ayush" />);

    await waitFor(() => expect(screen.getByLabelText(/cas pdf/i)).toBeInTheDocument());
    expect(api.createHouseholdMember).toHaveBeenCalledWith("Ayush", "self");
  });

  it("reuses an existing self household member instead of creating a duplicate", async () => {
    vi.mocked(api.listHouseholdMembers).mockResolvedValue([
      { id: "self-1", name: "Ayush", relationship: "self", relationship_other_label: null },
    ]);

    render(<SoloCasUpload name="Ayush" />);

    await waitFor(() => expect(screen.getByLabelText(/cas pdf/i)).toBeInTheDocument());
    expect(api.createHouseholdMember).not.toHaveBeenCalled();
  });

  it("falls back to a default name when none was given", async () => {
    vi.mocked(api.listHouseholdMembers).mockResolvedValue([]);
    vi.mocked(api.createHouseholdMember).mockResolvedValue({
      id: "self-1", name: "Me", relationship: "self", relationship_other_label: null,
    });

    render(<SoloCasUpload name="" />);

    await waitFor(() => expect(api.createHouseholdMember).toHaveBeenCalledWith("Me", "self"));
  });
});
```

- [ ] **Step 10: Run the test to verify it fails**

Run: `cd frontend && npm test -- SoloCasUpload.test.tsx`
Expected: FAIL — component doesn't exist yet.

- [ ] **Step 11: Implement `SoloCasUpload.tsx`**

```tsx
// frontend/src/features/auth/SoloCasUpload.tsx
import { useEffect, useState } from "react";
import { ImportFlow } from "../import/ImportFlow";
import { useAuth } from "./AuthContext";
import { createHouseholdMember, listHouseholdMembers } from "./api";
import styles from "./onboarding.module.css";

interface SoloCasUploadProps {
  name: string;
}

export function SoloCasUpload({ name }: SoloCasUploadProps) {
  const { updateMe } = useAuth();
  const [memberId, setMemberId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function resolveSelfMember() {
      try {
        const existing = await listHouseholdMembers();
        const self = existing.find((member) => member.relationship === "self");
        const member = self ?? (await createHouseholdMember(name.trim() || "Me", "self"));
        if (!cancelled) {
          setMemberId(member.id);
        }
      } catch {
        if (!cancelled) {
          setError("Couldn't set up your profile. Please try again.");
        }
      }
    }

    void resolveSelfMember();
    return () => {
      cancelled = true;
    };
  }, [name]);

  const handleDone = async () => {
    await updateMe({ onboarding_completed: true });
  };

  if (error) {
    return (
      <p role="alert" className={styles.error}>
        {error}
      </p>
    );
  }
  if (!memberId) {
    return <p>Setting up your profile...</p>;
  }

  return <ImportFlow householdMemberId={memberId} ctaLabel="Continue" onDone={handleDone} />;
}
```

- [ ] **Step 12: Run the test to verify it passes**

Run: `cd frontend && npm test -- SoloCasUpload.test.tsx`
Expected: PASS

- [ ] **Step 13: Wire `SoloCasUpload` into `OnboardingFlow`**

In `frontend/src/features/auth/OnboardingFlow.tsx`, add the import:

```typescript
import { SoloCasUpload } from "./SoloCasUpload";
```

Replace:

```tsx
  if (step === "cas_upload") {
    return <p>Solo CAS Upload — built in Task 9.</p>;
  }
```

with:

```tsx
  if (step === "cas_upload") {
    return <SoloCasUpload name={answers.name} />;
  }
```

- [ ] **Step 14: Run the full frontend suite to confirm no regressions**

Run: `cd frontend && npm test`
Expected: All tests pass.

- [ ] **Step 15: Commit**

```bash
git add src/features/import/ImportFlow.tsx src/features/import/ImportFlow.test.tsx src/features/import/ImportConfirmed.tsx src/features/import/ImportConfirmed.test.tsx src/features/auth/SoloCasUpload.tsx src/features/auth/SoloCasUpload.test.tsx src/features/auth/OnboardingFlow.tsx
git commit -m "feat: thread householdMemberId/ctaLabel through ImportFlow, add Solo CAS Upload (S8)"
```

---

### Task 10: Family CAS Upload subsystem (S24-S26)

**Files:**
- Create: `frontend/src/features/auth/FamilyCasUpload.tsx`
- Create: `frontend/src/features/auth/UploadMyCas.tsx`
- Create: `frontend/src/features/auth/ParseQueue.tsx`
- Create: `frontend/src/features/auth/FamilyImportFlow.tsx`
- Test: `frontend/src/features/auth/FamilyImportFlow.test.tsx`
- Modify: `frontend/src/features/auth/OnboardingFlow.tsx`

**Interfaces:**
- Consumes: `parseImport`, `confirmImport`, `ApiError` from `../import/api`
  (Task 1); `ReviewTable` from `../import/ReviewTable`; `ImportError` from
  `../import/ImportError`; `ImportConfirmed` from `../import/ImportConfirmed`;
  `ParsingIndicator` from `../import/ParsingIndicator`; `UploadForm` from
  `../import/UploadForm`; `listHouseholdMembers`, `createHouseholdMember`
  from `./api`; `useAuth` from `./AuthContext`; `HouseholdMember` from `./types`.
- Produces: `FamilyImportFlow({ familyMembers: HouseholdMember[]; selfName: string })`
  — wired into `OnboardingFlow`'s `family_cas_upload`/`upload_my_cas`/`parse_queue`
  branches, replacing the Task 7 placeholder. Internally renders
  `FamilyCasUpload`, `UploadMyCas`, `ParseQueue` as its three sub-views.

This is the largest single task in the plan — the queue/batch-parse state
machine described in the design spec. Build it as one deliverable since the
three sub-views share one piece of state (the queue) that only makes sense
assembled together.

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/src/features/auth/FamilyImportFlow.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FamilyImportFlow } from "./FamilyImportFlow";
import { AuthProvider } from "./AuthContext";
import * as authApi from "./api";
import * as importApi from "../import/api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, getMe: vi.fn(), updateMe: vi.fn(), listHouseholdMembers: vi.fn(), createHouseholdMember: vi.fn() };
});

vi.mock("../import/api", async () => {
  const actual = await vi.importActual<typeof import("../import/api")>("../import/api");
  return { ...actual, parseImport: vi.fn(), confirmImport: vi.fn() };
});

const ME = {
  user_id: "u1", phone_number: "+919999999999", email: null,
  onboarding_step: "family_cas_upload", onboarding_completed: false, investor_type: null, primary_goal: null,
};

const FAMILY = [
  { id: "mom", name: "Mom", relationship: "parent" as const, relationship_other_label: null },
  { id: "dad", name: "Dad", relationship: "parent" as const, relationship_other_label: null },
];

const EMPTY_PREVIEW = {
  session_id: "s1", filename: "cas.pdf", investor_name: null, investor_email: null,
  pan_masked: null, schemes: [], transactions: [], transaction_count: 0,
  parse_warnings: [], cas_type: "DETAILED", file_type: "FileType.CAMS",
};

function uploadFor(memberLabel: RegExp) {
  const file = new File(["pdf-bytes"], "cas.pdf", { type: "application/pdf" });
  fireEvent.click(screen.getByRole("button", { name: memberLabel }));
  fireEvent.change(screen.getByLabelText(/cas pdf/i), { target: { files: [file] } });
  fireEvent.change(screen.getByLabelText(/pdf password/i), { target: { value: "secret" } });
  fireEvent.click(screen.getByRole("button", { name: /^upload$/i }));
}

function renderFlow() {
  vi.mocked(authApi.getMe).mockResolvedValue(ME);
  vi.mocked(authApi.updateMe).mockImplementation(async (body) => ({ ...ME, ...body }) as typeof ME);
  return render(
    <AuthProvider>
      <FamilyImportFlow familyMembers={FAMILY} selfName="Ayush" />
    </AuthProvider>,
  );
}

describe("FamilyImportFlow", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows one card per family member, all Not Uploaded initially", async () => {
    renderFlow();
    await waitFor(() => expect(screen.getByText("Mom")).toBeInTheDocument());

    expect(screen.getAllByText(/not uploaded/i)).toHaveLength(2);
  });

  it("flips a card to Uploaded after choosing a file for that member, without affecting the other card", async () => {
    renderFlow();
    await waitFor(() => screen.getByText("Mom"));

    uploadFor(/upload cas for mom/i);

    await waitFor(() => expect(screen.getAllByText(/uploaded/i)).toHaveLength(1));
    expect(screen.getByText(/not uploaded/i)).toBeInTheDocument();
  });

  it("does not call parseImport when a file is queued (upload only queues, never auto-parses)", async () => {
    renderFlow();
    await waitFor(() => screen.getByText("Mom"));

    uploadFor(/upload cas for mom/i);

    await waitFor(() => expect(screen.getAllByText(/uploaded/i)).toHaveLength(1));
    expect(importApi.parseImport).not.toHaveBeenCalled();
  });

  it("reaches Upload My CAS? once every member card is Uploaded or skipped, then Parse Queue on Upload Later", async () => {
    renderFlow();
    await waitFor(() => screen.getByText("Mom"));
    uploadFor(/upload cas for mom/i);
    await waitFor(() => screen.getAllByText(/uploaded/i));
    fireEvent.click(screen.getByRole("button", { name: /skip for now.*dad/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /^continue$/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));

    await waitFor(() => expect(screen.getByText(/upload your own cas/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /upload later/i }));

    await waitFor(() => expect(screen.getByText(/cas\.pdf/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /parse files/i })).toBeInTheDocument();
  });

  it("parses queued files sequentially and shows one aggregate ImportConfirmed at the end", async () => {
    vi.mocked(importApi.parseImport).mockResolvedValue(EMPTY_PREVIEW);
    vi.mocked(importApi.confirmImport)
      .mockResolvedValueOnce({ added: 2, skipped: 0, import_id: "imp-mom" })
      .mockResolvedValueOnce({ added: 3, skipped: 1, import_id: "imp-dad" });

    renderFlow();
    await waitFor(() => screen.getByText("Mom"));
    uploadFor(/upload cas for mom/i);
    await waitFor(() => screen.getAllByText(/uploaded/i));
    uploadFor(/upload cas for dad/i);
    await waitFor(() => expect(screen.getByRole("button", { name: /^continue$/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/upload your own cas/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /upload later/i }));
    await waitFor(() => screen.getByRole("button", { name: /parse files/i }));

    fireEvent.click(screen.getByRole("button", { name: /parse files/i }));

    await waitFor(() => expect(screen.getByText(/reviewing: mom's cas/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));

    await waitFor(() => expect(screen.getByText(/reviewing: dad's cas/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));

    await waitFor(() => expect(screen.getByText(/import complete/i)).toBeInTheDocument());
    expect(screen.getByText(/5 new transactions added, 1 duplicate skipped/i)).toBeInTheDocument();
    expect(importApi.confirmImport).toHaveBeenNthCalledWith(1, "s1", "mom", []);
    expect(importApi.confirmImport).toHaveBeenNthCalledWith(2, "s1", "dad", []);
  });

  it("continues to the next queued file after a per-item parse failure", async () => {
    vi.mocked(importApi.parseImport)
      .mockRejectedValueOnce({ status: 422, payload: { code: "wrong_password", message: "Incorrect PDF password." } })
      .mockResolvedValueOnce(EMPTY_PREVIEW);
    vi.mocked(importApi.confirmImport).mockResolvedValue({ added: 1, skipped: 0, import_id: "imp-dad" });

    renderFlow();
    await waitFor(() => screen.getByText("Mom"));
    uploadFor(/upload cas for mom/i);
    await waitFor(() => screen.getAllByText(/uploaded/i));
    uploadFor(/upload cas for dad/i);
    await waitFor(() => expect(screen.getByRole("button", { name: /^continue$/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => screen.getByText(/upload your own cas/i));
    fireEvent.click(screen.getByRole("button", { name: /upload later/i }));
    await waitFor(() => screen.getByRole("button", { name: /parse files/i }));

    fireEvent.click(screen.getByRole("button", { name: /parse files/i }));

    await waitFor(() => expect(screen.getByText(/import failed/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() => expect(screen.getByText(/reviewing: dad's cas/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- FamilyImportFlow.test.tsx`
Expected: FAIL — none of these components exist yet.

- [ ] **Step 3: Create `FamilyCasUpload.tsx`**

```tsx
// frontend/src/features/auth/FamilyCasUpload.tsx
import { useState } from "react";
import { UploadForm } from "../import/UploadForm";
import { Badge } from "../../components/Badge";
import styles from "./onboarding.module.css";
import type { HouseholdMember } from "./types";

export interface FamilyUpload {
  memberId: string;
  memberName: string;
  file: File;
  password: string;
}

interface FamilyCasUploadProps {
  members: HouseholdMember[];
  queue: FamilyUpload[];
  onQueueUpload: (upload: FamilyUpload) => void;
  onSkip: (memberId: string) => void;
  skipped: Set<string>;
  onContinue: () => void;
}

export function FamilyCasUpload({ members, queue, onQueueUpload, onSkip, skipped, onContinue }: FamilyCasUploadProps) {
  const [activeMemberId, setActiveMemberId] = useState<string | null>(null);

  const isUploaded = (memberId: string) => queue.some((item) => item.memberId === memberId);
  const allHandled = members.every((member) => isUploaded(member.id) || skipped.has(member.id));

  if (activeMemberId) {
    const member = members.find((m) => m.id === activeMemberId);
    return (
      <UploadForm
        onSubmit={(file, password) => {
          if (member) {
            onQueueUpload({ memberId: member.id, memberName: member.name, file, password });
          }
          setActiveMemberId(null);
        }}
      />
    );
  }

  return (
    <div className={styles.container}>
      <h1>Family CAS Upload</h1>
      {members.map((member) => (
        <div key={member.id} className={styles.field}>
          <span>{member.name}</span>
          <Badge variant={isUploaded(member.id) ? "positive" : "neutral"}>
            {isUploaded(member.id) ? "Uploaded" : "Not Uploaded"}
          </Badge>
          {!isUploaded(member.id) && (
            <div className={styles.actions}>
              <button type="button" onClick={() => setActiveMemberId(member.id)}>
                {`Upload CAS for ${member.name}`}
              </button>
              <button type="button" onClick={() => onSkip(member.id)}>
                {`Skip for now — ${member.name}`}
              </button>
            </div>
          )}
        </div>
      ))}
      <button type="button" disabled={!allHandled} onClick={onContinue}>
        Continue
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Create `UploadMyCas.tsx`**

```tsx
// frontend/src/features/auth/UploadMyCas.tsx
import { UploadForm } from "../import/UploadForm";
import styles from "./onboarding.module.css";

interface UploadMyCasProps {
  awaitingUpload: boolean;
  onUploadNow: () => void;
  onUploadLater: () => void;
  onSubmit: (file: File, password: string) => void;
}

export function UploadMyCas({ awaitingUpload, onUploadNow, onUploadLater, onSubmit }: UploadMyCasProps) {
  if (awaitingUpload) {
    return <UploadForm onSubmit={onSubmit} />;
  }

  return (
    <div className={styles.container}>
      <h1>Upload your own CAS?</h1>
      <div className={styles.actions}>
        <button type="button" onClick={onUploadNow}>
          Upload Now
        </button>
        <button type="button" onClick={onUploadLater}>
          Upload Later
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create `ParseQueue.tsx`**

```tsx
// frontend/src/features/auth/ParseQueue.tsx
import styles from "./onboarding.module.css";
import type { FamilyUpload } from "./FamilyCasUpload";

interface ParseQueueProps {
  queue: FamilyUpload[];
  onParseFiles: () => void;
}

export function ParseQueue({ queue, onParseFiles }: ParseQueueProps) {
  return (
    <div className={styles.container}>
      <h1>Files ready to import</h1>
      <ul>
        {queue.map((item) => (
          <li key={item.memberId}>{`${item.file.name} (${item.memberName})`}</li>
        ))}
      </ul>
      <button type="button" disabled={queue.length === 0} onClick={onParseFiles}>
        Parse Files
      </button>
    </div>
  );
}
```

- [ ] **Step 6: Create `FamilyImportFlow.tsx`**

```tsx
// frontend/src/features/auth/FamilyImportFlow.tsx
import { useEffect, useState } from "react";
import { FamilyCasUpload } from "./FamilyCasUpload";
import type { FamilyUpload } from "./FamilyCasUpload";
import { UploadMyCas } from "./UploadMyCas";
import { ParseQueue } from "./ParseQueue";
import { ParsingIndicator } from "../import/ParsingIndicator";
import { ReviewTable } from "../import/ReviewTable";
import { ImportError } from "../import/ImportError";
import { ImportConfirmed } from "../import/ImportConfirmed";
import { ApiError, confirmImport, parseImport } from "../import/api";
import type { ImportConfirmResponse, ImportPreviewResponse, ParseErrorPayload, SchemeConfirmation } from "../import/types";
import { useAuth } from "./AuthContext";
import { createHouseholdMember, listHouseholdMembers } from "./api";
import type { HouseholdMember } from "./types";

interface FamilyImportFlowProps {
  familyMembers: HouseholdMember[];
  selfName: string;
}

type Stage = "cards" | "own-choice" | "own-upload" | "queue" | "processing" | "done";

interface ProcessingState {
  index: number;
  status: "parsing" | "review" | "error";
  preview: ImportPreviewResponse | null;
  error: ParseErrorPayload | null;
}

const GENERIC_NETWORK_ERROR: ParseErrorPayload = {
  code: "network_error",
  message: "Couldn't reach the server. Check your connection and try again.",
};

function toParseErrorPayload(err: unknown): ParseErrorPayload {
  if (err instanceof ApiError) {
    return typeof err.payload === "string" ? { code: "error", message: err.payload } : err.payload;
  }
  return GENERIC_NETWORK_ERROR;
}

export function FamilyImportFlow({ familyMembers, selfName }: FamilyImportFlowProps) {
  const { updateMe } = useAuth();
  const [stage, setStage] = useState<Stage>("cards");
  const [queue, setQueue] = useState<FamilyUpload[]>([]);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [processing, setProcessing] = useState<ProcessingState | null>(null);
  const [results, setResults] = useState<ImportConfirmResponse[]>([]);

  const startParsing = async (index: number) => {
    setProcessing({ index, status: "parsing", preview: null, error: null });
    try {
      const preview = await parseImport(queue[index].file, queue[index].password);
      setProcessing({ index, status: "review", preview, error: null });
    } catch (err) {
      setProcessing({ index, status: "error", preview: null, error: toParseErrorPayload(err) });
    }
  };

  useEffect(() => {
    if (stage === "processing" && processing === null) {
      void startParsing(0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

  const advanceOrFinish = (updatedResults: ImportConfirmResponse[]) => {
    const nextIndex = (processing?.index ?? 0) + 1;
    if (nextIndex >= queue.length) {
      setResults(updatedResults);
      setStage("done");
      return;
    }
    setResults(updatedResults);
    void startParsing(nextIndex);
  };

  const handleConfirm = async (confirmations: SchemeConfirmation[]) => {
    if (!processing?.preview) return;
    const item = queue[processing.index];
    try {
      const result = await confirmImport(processing.preview.session_id, item.memberId, confirmations);
      advanceOrFinish([...results, result]);
    } catch {
      setProcessing({ ...processing, status: "error", error: GENERIC_NETWORK_ERROR });
    }
  };

  const handleSkipFailedItem = () => {
    advanceOrFinish(results);
  };

  const resolveSelfMember = async (): Promise<HouseholdMember> => {
    const existing = await listHouseholdMembers();
    const self = existing.find((member) => member.relationship === "self");
    return self ?? createHouseholdMember(selfName.trim() || "Me", "self");
  };

  if (stage === "cards") {
    return (
      <FamilyCasUpload
        members={familyMembers}
        queue={queue}
        skipped={skipped}
        onQueueUpload={(upload) => setQueue((q) => [...q, upload])}
        onSkip={(memberId) => setSkipped((s) => new Set(s).add(memberId))}
        onContinue={() => setStage("own-choice")}
      />
    );
  }

  if (stage === "own-choice") {
    return (
      <UploadMyCas
        awaitingUpload={false}
        onUploadNow={() => setStage("own-upload")}
        onUploadLater={() => setStage("queue")}
        onSubmit={() => {}}
      />
    );
  }

  if (stage === "own-upload") {
    return (
      <UploadMyCas
        awaitingUpload
        onUploadNow={() => {}}
        onUploadLater={() => {}}
        onSubmit={async (file, password) => {
          const self = await resolveSelfMember();
          setQueue((q) => [...q, { memberId: self.id, memberName: self.name, file, password }]);
          setStage("queue");
        }}
      />
    );
  }

  if (stage === "queue") {
    return <ParseQueue queue={queue} onParseFiles={() => setStage("processing")} />;
  }

  if (stage === "processing" && processing) {
    const item = queue[processing.index];
    if (processing.status === "parsing") {
      return <ParsingIndicator />;
    }
    if (processing.status === "review" && processing.preview) {
      return (
        <>
          <p>{`Reviewing: ${item.memberName}'s CAS`}</p>
          <ReviewTable preview={processing.preview} confirming={false} onConfirm={handleConfirm} />
        </>
      );
    }
    return (
      <ImportError
        error={processing.error ?? GENERIC_NETWORK_ERROR}
        onRetry={handleSkipFailedItem}
      />
    );
  }

  if (stage === "done") {
    const aggregate: ImportConfirmResponse = {
      added: results.reduce((sum, r) => sum + r.added, 0),
      skipped: results.reduce((sum, r) => sum + r.skipped, 0),
      import_id: results.length > 0 ? results[results.length - 1].import_id : "",
    };
    return (
      <ImportConfirmed
        result={aggregate}
        ctaLabel="Continue"
        onImportAnother={async () => {
          await updateMe({ onboarding_completed: true });
        }}
      />
    );
  }

  return null;
}
```

Note: `ImportError`'s existing button label is "Try again" (unchanged from
Phase 1b, per the Global Constraints — it is not redesigned) — the
per-item-failure test above already asserts against that real label, not a
placeholder, so no follow-up fix is needed here.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd frontend && npm test -- FamilyImportFlow.test.tsx`
Expected: PASS

- [ ] **Step 8: Wire `FamilyImportFlow` into `OnboardingFlow`**

In `frontend/src/features/auth/OnboardingFlow.tsx`, add the import:

```typescript
import { FamilyImportFlow } from "./FamilyImportFlow";
```

Replace:

```tsx
  if (step === "family_cas_upload" || step === "upload_my_cas" || step === "parse_queue") {
    return <p>Family CAS Upload — built in Task 10.</p>;
  }
```

with:

```tsx
  if (step === "family_cas_upload" || step === "upload_my_cas" || step === "parse_queue") {
    return <FamilyImportFlow familyMembers={answers.familyMembers} selfName={answers.name} />;
  }
```

- [ ] **Step 9: Run the full frontend suite to confirm no regressions**

Run: `cd frontend && npm test`
Expected: All tests pass.

- [ ] **Step 10: Commit**

```bash
git add src/features/auth/FamilyCasUpload.tsx src/features/auth/UploadMyCas.tsx src/features/auth/ParseQueue.tsx src/features/auth/FamilyImportFlow.tsx src/features/auth/FamilyImportFlow.test.tsx src/features/auth/OnboardingFlow.tsx
git commit -m "feat: add Family CAS Upload subsystem (S24-S26) — per-member queue, batch parse, aggregate payoff"
```

---

### Task 11: `DashboardPlaceholder` + `App.tsx` composition root

**Files:**
- Create: `frontend/src/features/dashboard/DashboardPlaceholder.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `AuthProvider`, `useAuth` from `./features/auth/AuthContext`
  (Task 4); `AuthEntryFlow` from `./features/auth/AuthEntryFlow` (Task 6);
  `OnboardingFlow` from `./features/auth/OnboardingFlow` (Task 7).
- Produces: `DashboardPlaceholder()` — the final destination once
  `me.onboarding_completed === true`.

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/src/App.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import * as api from "./features/auth/api";

vi.mock("./features/auth/api", async () => {
  const actual = await vi.importActual<typeof import("./features/auth/api")>("./features/auth/api");
  return { ...actual, getMe: vi.fn() };
});

describe("App", () => {
  afterEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("shows Landing when there is no stored session", async () => {
    render(<App />);

    await waitFor(() => expect(screen.getByRole("button", { name: /sign up/i })).toBeInTheDocument());
  });

  it("shows OnboardingFlow when the session is valid and onboarding is incomplete", async () => {
    localStorage.setItem("unifolio_session_token", "tok-1");
    vi.mocked(api.getMe).mockResolvedValue({
      user_id: "u1", phone_number: "+919999999999", email: null,
      onboarding_step: "trust_primer", onboarding_completed: false, investor_type: null, primary_goal: null,
    });

    render(<App />);

    await waitFor(() => expect(screen.getByRole("button", { name: /continue/i })).toBeInTheDocument());
  });

  it("shows DashboardPlaceholder when the session is valid and onboarding is complete", async () => {
    localStorage.setItem("unifolio_session_token", "tok-1");
    vi.mocked(api.getMe).mockResolvedValue({
      user_id: "u1", phone_number: "+919999999999", email: null,
      onboarding_step: null, onboarding_completed: true, investor_type: null, primary_goal: null,
    });

    render(<App />);

    await waitFor(() => expect(screen.getByText(/welcome to unifolio/i)).toBeInTheDocument());
  });

  it("falls back to Landing when the stored session is invalid", async () => {
    localStorage.setItem("unifolio_session_token", "stale-tok");
    vi.mocked(api.getMe).mockRejectedValue(new Error("401"));

    render(<App />);

    await waitFor(() => expect(screen.getByRole("button", { name: /sign up/i })).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- App.test.tsx`
Expected: FAIL — `App` still just mounts `ImportFlow` directly (which now
requires a `householdMemberId` prop it doesn't pass, so this is already
broken from Task 9 forward — confirming that here motivates this task).

- [ ] **Step 3: Create `DashboardPlaceholder.tsx`**

```tsx
// frontend/src/features/dashboard/DashboardPlaceholder.tsx
export function DashboardPlaceholder() {
  return (
    <div>
      <h1>Welcome to Unifolio</h1>
      <p>Your Main Dashboard is coming soon.</p>
    </div>
  );
}
```

- [ ] **Step 4: Rewrite `App.tsx`**

```tsx
// frontend/src/App.tsx
import { AuthProvider, useAuth } from "./features/auth/AuthContext";
import { AuthEntryFlow } from "./features/auth/AuthEntryFlow";
import { OnboardingFlow } from "./features/auth/OnboardingFlow";
import { DashboardPlaceholder } from "./features/dashboard/DashboardPlaceholder";

function AppShell() {
  const { me, loading } = useAuth();

  if (loading) {
    return null;
  }
  if (!me) {
    return <AuthEntryFlow />;
  }
  if (!me.onboarding_completed) {
    return <OnboardingFlow />;
  }
  return <DashboardPlaceholder />;
}

function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}

export default App;
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npm test -- App.test.tsx`
Expected: PASS

- [ ] **Step 6: Run the full frontend test suite**

Run: `cd frontend && npm test`
Expected: All tests pass.

- [ ] **Step 7: Run the TypeScript build to confirm the whole app compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: PASS, no type errors.

- [ ] **Step 8: Commit**

```bash
git add src/features/dashboard/DashboardPlaceholder.tsx src/App.tsx src/App.test.tsx
git commit -m "feat: wire App.tsx composition root — session resume drives Landing/Onboarding/Dashboard"
```

---

## Self-Review Notes (completed during plan authoring)

**Spec coverage:** every spec section maps to a task — Landing/Phone/OTP
(Task 6), back-nav history (Task 5/7), Q1-Q4 (Task 7), Add Family Members
(Task 8), solo CAS upload with the `ctaLabel`/`onDone` extension (Task 9),
Family CAS Upload/queue/batch-parse/aggregate-payoff (Task 10), session
resume (Task 4/11), Dashboard placeholder (Task 11). The `lib/apiClient.ts`
extraction (Task 1) and the `PATCH /household-members`-doesn't-exist
resolution (list-then-create, Tasks 9/10) are implementation-level
decisions the spec described at a higher level; both are called out
explicitly in Global Constraints so no task treats them as a surprise.

**Placeholder scan:** no TBD/TODO in any task; the two intentional string
placeholders inside `OnboardingFlow.tsx` (Task 7's `<p>...built in Task
N.</p>` branches) are replaced with real code in the exact later task named
in the string, and every replacement step is spelled out with a diff.

**Type consistency:** `HouseholdMember`, `MeResponse`, `UpdateMeBody`,
`OnboardingStep`, `HistoryState`, `FamilyUpload`, `QueueItem`-shaped
`ProcessingState` are defined once (Tasks 2, 5, 10) and reused verbatim by
every consuming task — checked against each task's Interfaces block above.

**Scope check:** one cohesive feature (mirrors Phase 1b's single-plan
precedent) — Family CAS Upload is reached only through the same
`OnboardingFlow`/`AuthContext` this plan also builds, so splitting it into
a second plan would leave Task 10 unable to stand alone as working
software.
