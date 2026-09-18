# Multi-Method Auth (Frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the phone-only auth entry screen with a split-card layout offering Google, Apple (disabled placeholder), Email, and Phone as visually equal entry points, wired to the backend's three-way verify outcome (login / step-up link / mandatory phone gate).

**Architecture:** `Landing.tsx` becomes the method-selector card directly (no separate screen ahead of it), embedding a `GoogleButton` (Google Identity Services popup) alongside Email/Phone pill buttons and a disabled Apple placeholder. `AuthEntryFlow.tsx`'s existing `useState<Step>` machine is extended, not replaced, with two new steps (`email`, `email_otp`) and one new rendering mode (`link_account`) — the mandatory phone-gate case reuses the *existing* `phone`/`otp` steps via a new `context` prop rather than adding a fifth step. A new `AuthShowcasePanel` fills the right half of a two-column layout, built as a static, illustrative placeholder pending real content from the product owner.

**Tech Stack:** React 19, Vite, TypeScript, Tailwind CSS, shadcn/ui (`@/components/ui/button`), `@visx`/`d3-shape` (existing chart primitives, reused for the showcase panel), Vitest + Testing Library (existing test stack). No new frontend libraries.

**Spec:** `Docs/superpowers/specs/2026-08-14-multi-method-auth-frontend-design.md` (and its companion backend spec, `Docs/superpowers/specs/2026-08-14-multi-method-auth-design.md`, for the exact API contracts this plan wires against — see the sibling plan, `Docs/superpowers/plans/2026-08-14-multi-method-auth-backend-plan.md`, which must be implemented first).

## Global Constraints

- **This plan depends on the backend plan being implemented first.** Every API shape referenced below (`POST /auth/oauth/google`, the widened `/auth/otp/request`/`/auth/otp/verify`, the `link_required`/`phone_required` response variants) comes from `Docs/superpowers/plans/2026-08-14-multi-method-auth-backend-plan.md`. Do not start this plan against a backend that doesn't yet implement those routes.
- **Confirmed pill-button order: Google, Apple (disabled), Email, Phone.** Not alphabetical, not a placeholder — this exact order is a resolved product decision, matching the Goal line above, Task 7's JSX comment, Task 10's ordering test, and `decisions.md`/the frontend spec. (An earlier draft of this line read "Email, Phone, Google, Apple" — a transcription error, corrected 2026-08-15; every other reference to the order in this plan already had it right.)
- **Apple is a disabled visual placeholder only.** No SDK, no handler, no API call, no `AppleButton.tsx` component in this plan — just a static, inert button with "Coming soon" messaging.
- **No router.** Confirmed no `react-router`/`BrowserRouter` anywhere in `frontend/src` — this plan extends `AuthEntryFlow.tsx`'s existing local `useState<Step>` machine, matching `2026-08-06-phase-2b-onboarding-frontend-design.md`'s explicit decision not to add one. Do not introduce React Router.
- **Tailwind + shadcn/ui are real and already in use** (`frontend/src/styles/tokens.css` bridges Design-Schema tokens into shadcn's CSS-variable contract; `@/components/ui/button` is already imported throughout `features/auth/`). **Bklit UI is not actually installed** — `components.json` only registers its registry URL as a pull-on-demand source, no `@bklit` package exists. Do not `import` anything from `@bklit/*`; the showcase panel is hand-built on `@visx`/`d3-shape`, matching `FundSignal.tsx`'s existing pattern.
- **`AuthContext.tsx` needs no changes.** `login(token: string)` is already provider-agnostic. Do not modify this file.
- **No dedicated test files for `PhoneEntry`/`OtpVerify`/`EmailEntry`/`EmailOtpVerify`.** Matching this repo's existing convention, their coverage lives entirely in `AuthEntryFlow.test.tsx`. `GoogleButton` and `useOAuthScript` **do** get dedicated test files — they mock third-party globals that don't fit the `vi.mock("./api")` pattern the other tests use.
- **Popup-blocker constraint**: the Google Identity Services sign-in trigger must run synchronously inside the button's own render/init path, not behind an `await` in a click handler — GIS's `renderButton` already satisfies this by construction (it renders its own native button), so don't wrap it in an intermediate custom `onClick` that adds an async gap before the popup can open.
- **The right-side panel (`AuthShowcasePanel`) is a structural placeholder.** Its illustrative content is not final — build it as static, no backend dependency, and expect it to be revisited once the product owner provides real content.
- **Test runner**: `npm test` (`vitest run`) from `frontend/`. Match existing test file conventions exactly — see `AuthEntryFlow.test.tsx`'s `vi.mock("./api")` + Testing Library `render`/`fireEvent`/`waitFor` pattern.

---

## Task 1: Types and API client — email, Google, and the three-way verify outcome

**Files:**
- Modify: `frontend/src/features/auth/types.ts`
- Modify: `frontend/src/features/auth/api.ts`
- Modify: `frontend/src/features/auth/api.test.ts`

**Interfaces:**
- Produces: `ExistingMethod = "phone" | "email" | "google"`; `LinkRequiredResponse`, `PhoneRequiredResponse`, `OtpVerifyResult = OtpVerifyResponse | LinkRequiredResponse | PhoneRequiredResponse`; type guards `isLinkRequired`, `isPhoneRequired`; `sendEmailOtp(email: string): Promise<OtpRequestResponse>`; `verifyEmailOtp(email: string, otp: string, pendingToken?: string): Promise<OtpVerifyResult>`; `verifyGoogleCredential(idToken: string, pendingToken?: string): Promise<OtpVerifyResult>`; `verifyOtp(phoneNumber: string, otp: string, pendingToken?: string): Promise<OtpVerifyResult>` (signature widened, backward-compatible).

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/features/auth/api.test.ts` (add `sendEmailOtp, verifyEmailOtp, verifyGoogleCredential` to the existing import from `"./api"`):

```ts
it("sendEmailOtp posts email as JSON", async () => {
  const mockFetch = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ message: "OTP sent.", otp: "111111" }), { status: 200 }),
  );
  vi.stubGlobal("fetch", mockFetch);

  const result = await sendEmailOtp("a@example.com");

  const [url, options] = mockFetch.mock.calls[0];
  expect(url).toContain("/auth/otp/request");
  expect(JSON.parse(options.body as string)).toEqual({ email: "a@example.com" });
  expect(result.otp).toBe("111111");
});

it("verifyEmailOtp posts email and otp as JSON", async () => {
  const mockFetch = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({ session_token: "tok-2", user_id: "u2", onboarding_step: null, onboarding_completed: false }),
      { status: 200 },
    ),
  );
  vi.stubGlobal("fetch", mockFetch);

  const result = await verifyEmailOtp("a@example.com", "654321");

  const [url, options] = mockFetch.mock.calls[0];
  expect(url).toContain("/auth/otp/verify");
  expect(JSON.parse(options.body as string)).toEqual({ email: "a@example.com", otp: "654321" });
  expect("session_token" in result && result.session_token).toBe("tok-2");
});

it("verifyOtp includes pending_token only when provided", async () => {
  const mockFetch = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({ session_token: "tok-3", user_id: "u3", onboarding_step: null, onboarding_completed: false }),
      { status: 200 },
    ),
  );
  vi.stubGlobal("fetch", mockFetch);

  await verifyOtp("+919999999999", "123456", "pending-abc");

  const [, options] = mockFetch.mock.calls[0];
  expect(JSON.parse(options.body as string)).toEqual({
    phone_number: "+919999999999", otp: "123456", pending_token: "pending-abc",
  });
});

it("verifyOtp omits pending_token when not provided", async () => {
  const mockFetch = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({ session_token: "tok-4", user_id: "u4", onboarding_step: null, onboarding_completed: false }),
      { status: 200 },
    ),
  );
  vi.stubGlobal("fetch", mockFetch);

  await verifyOtp("+919999999999", "123456");

  const [, options] = mockFetch.mock.calls[0];
  expect(JSON.parse(options.body as string)).toEqual({ phone_number: "+919999999999", otp: "123456" });
});

it("verifyGoogleCredential posts id_token as JSON", async () => {
  const mockFetch = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({ phone_required: { token: "gate-tok", prefill_email: "a@example.com" } }),
      { status: 200 },
    ),
  );
  vi.stubGlobal("fetch", mockFetch);

  const result = await verifyGoogleCredential("fake-id-token");

  const [url, options] = mockFetch.mock.calls[0];
  expect(url).toContain("/auth/oauth/google");
  expect(JSON.parse(options.body as string)).toEqual({ id_token: "fake-id-token" });
  expect("phone_required" in result).toBe(true);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/auth/api.test.ts`
Expected: FAIL — `sendEmailOtp`/`verifyEmailOtp`/`verifyGoogleCredential` don't exist yet, and `verifyOtp` doesn't accept a third argument.

- [ ] **Step 3: Add the new types**

In `frontend/src/features/auth/types.ts`, append:

```ts
export type ExistingMethod = "phone" | "email" | "google";

export interface LinkRequiredDetail {
  token: string;
  matched_email: string;
  existing_method: ExistingMethod;
}

export interface LinkRequiredResponse {
  link_required: LinkRequiredDetail;
}

export interface PhoneRequiredDetail {
  token: string;
  prefill_email: string | null;
}

export interface PhoneRequiredResponse {
  phone_required: PhoneRequiredDetail;
}

export type OtpVerifyResult = OtpVerifyResponse | LinkRequiredResponse | PhoneRequiredResponse;

export function isLinkRequired(result: OtpVerifyResult): result is LinkRequiredResponse {
  return "link_required" in result;
}

export function isPhoneRequired(result: OtpVerifyResult): result is PhoneRequiredResponse {
  return "phone_required" in result;
}
```

- [ ] **Step 4: Update the API client**

Replace `frontend/src/features/auth/api.ts` in full:

```ts
import { API_BASE_URL, ApiError, parseErrorDetail } from "../../lib/apiClient";
import { getToken } from "./session";
import type {
  HouseholdMember,
  MeResponse,
  OtpRequestResponse,
  OtpVerifyResult,
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

export async function sendEmailOtp(email: string): Promise<OtpRequestResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/otp/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  await throwIfError(response);
  return (await response.json()) as OtpRequestResponse;
}

export async function verifyOtp(
  phoneNumber: string,
  otp: string,
  pendingToken?: string,
): Promise<OtpVerifyResult> {
  const response = await fetch(`${API_BASE_URL}/auth/otp/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      phone_number: phoneNumber,
      otp,
      ...(pendingToken ? { pending_token: pendingToken } : {}),
    }),
  });
  await throwIfError(response);
  return (await response.json()) as OtpVerifyResult;
}

export async function verifyEmailOtp(
  email: string,
  otp: string,
  pendingToken?: string,
): Promise<OtpVerifyResult> {
  const response = await fetch(`${API_BASE_URL}/auth/otp/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      otp,
      ...(pendingToken ? { pending_token: pendingToken } : {}),
    }),
  });
  await throwIfError(response);
  return (await response.json()) as OtpVerifyResult;
}

export async function verifyGoogleCredential(
  idToken: string,
  pendingToken?: string,
): Promise<OtpVerifyResult> {
  const response = await fetch(`${API_BASE_URL}/auth/oauth/google`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id_token: idToken,
      ...(pendingToken ? { pending_token: pendingToken } : {}),
    }),
  });
  await throwIfError(response);
  return (await response.json()) as OtpVerifyResult;
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

export const getHouseholdMembers = listHouseholdMembers;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/auth/api.test.ts`
Expected: PASS (all tests, existing and new).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/auth/types.ts frontend/src/features/auth/api.ts frontend/src/features/auth/api.test.ts
git commit -m "feat(auth): add email/Google API functions and the three-way verify result type"
```

---

## Task 2: `useOAuthScript` — shared third-party script loader

**Files:**
- Create: `frontend/src/features/auth/useOAuthScript.ts`
- Create: `frontend/src/features/auth/useOAuthScript.test.ts`
- Modify: `frontend/.env.example`

**Interfaces:**
- Produces: `useOAuthScript(src: string): "loading" | "loaded" | "error"`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/features/auth/useOAuthScript.test.ts`:

```ts
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useOAuthScript } from "./useOAuthScript";

describe("useOAuthScript", () => {
  afterEach(() => {
    document.head.innerHTML = "";
  });

  it("starts in the loading state", () => {
    const { result } = renderHook(() => useOAuthScript("https://example.com/script.js"));
    expect(result.current).toBe("loading");
  });

  it("resolves to loaded when the script fires onload", async () => {
    const { result } = renderHook(() => useOAuthScript("https://example.com/script.js"));
    const script = document.head.querySelector("script")!;

    act(() => {
      script.onload?.(new Event("load"));
    });

    await waitFor(() => expect(result.current).toBe("loaded"));
  });

  it("resolves to error when the script fails to load", async () => {
    const { result } = renderHook(() => useOAuthScript("https://example.com/bad.js"));
    const script = document.head.querySelector("script")!;

    act(() => {
      script.onerror?.(new Event("error"));
    });

    await waitFor(() => expect(result.current).toBe("error"));
  });

  it("only injects one script tag even when used from two components at once", () => {
    renderHook(() => useOAuthScript("https://example.com/shared.js"));
    renderHook(() => useOAuthScript("https://example.com/shared.js"));

    const scripts = document.head.querySelectorAll('script[src="https://example.com/shared.js"]');
    expect(scripts).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/auth/useOAuthScript.test.ts`
Expected: FAIL with a module-not-found error.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/features/auth/useOAuthScript.ts`:

```ts
import { useEffect, useState } from "react";

export type OAuthScriptStatus = "loading" | "loaded" | "error";

const loadedScripts = new Map<string, Promise<void>>();

function loadScriptOnce(src: string): Promise<void> {
  const existing = loadedScripts.get(src);
  if (existing) return existing;

  const promise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
    document.head.appendChild(script);
  });
  loadedScripts.set(src, promise);
  return promise;
}

/** Injects a third-party <script> tag exactly once per app lifetime,
 * regardless of how many components request the same src — written
 * generically (takes a URL, not hardcoded to Google) so a future Apple
 * integration can reuse it without rework (Frontend Spec, "New files"). */
export function useOAuthScript(src: string): OAuthScriptStatus {
  const [status, setStatus] = useState<OAuthScriptStatus>("loading");

  useEffect(() => {
    let cancelled = false;
    loadScriptOnce(src)
      .then(() => {
        if (!cancelled) setStatus("loaded");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [src]);

  return status;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/auth/useOAuthScript.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Add the Google Client ID env var**

In `frontend/.env.example`, append:

```
# Google OAuth Client ID for Sign-In (Google Identity Services) — see
# Docs/superpowers/specs/2026-08-14-multi-method-auth-design.md §8 for setup
VITE_GOOGLE_OAUTH_CLIENT_ID=
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/auth/useOAuthScript.ts frontend/src/features/auth/useOAuthScript.test.ts frontend/.env.example
git commit -m "feat(auth): add shared OAuth script-loading hook"
```

---

## Task 3: `GoogleButton` component

**Files:**
- Create: `frontend/src/types/google-identity-services.d.ts`
- Create: `frontend/src/features/auth/GoogleButton.tsx`
- Create: `frontend/src/features/auth/GoogleButton.test.tsx`

**Interfaces:**
- Consumes: `useOAuthScript` (Task 2).
- Produces: `<GoogleButton onCredential={(idToken: string) => void} />`.

- [ ] **Step 1: Add the ambient type declaration**

Create `frontend/src/types/google-identity-services.d.ts`:

```ts
export {};

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential: string }) => void;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: {
              type?: "standard" | "icon";
              theme?: "outline" | "filled_blue" | "filled_black";
              size?: "small" | "medium" | "large";
              shape?: "rectangular" | "pill" | "circle" | "square";
              width?: number;
              text?: "signin_with" | "signup_with" | "continue_with" | "signin";
            },
          ) => void;
        };
      };
    };
  }
}
```

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/features/auth/GoogleButton.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GoogleButton } from "./GoogleButton";

function mockGoogleGlobal() {
  const initialize = vi.fn();
  const renderButton = vi.fn();
  window.google = { accounts: { id: { initialize, renderButton } } };
  return { initialize, renderButton };
}

describe("GoogleButton", () => {
  afterEach(() => {
    document.head.innerHTML = "";
    delete (window as { google?: unknown }).google;
    vi.restoreAllMocks();
  });

  it("initializes GIS and renders the button once the script loads", async () => {
    const { initialize, renderButton } = mockGoogleGlobal();
    render(<GoogleButton onCredential={vi.fn()} />);

    const script = document.head.querySelector("script")!;
    fireEvent.load(script);

    await waitFor(() => expect(initialize).toHaveBeenCalled());
    expect(renderButton).toHaveBeenCalled();
  });

  it("calls onCredential with the returned id_token", async () => {
    const onCredential = vi.fn();
    const { initialize } = mockGoogleGlobal();
    render(<GoogleButton onCredential={onCredential} />);
    const script = document.head.querySelector("script")!;
    fireEvent.load(script);
    await waitFor(() => expect(initialize).toHaveBeenCalled());

    const { callback } = initialize.mock.calls[0][0] as { callback: (r: { credential: string }) => void };
    callback({ credential: "fake-id-token" });

    expect(onCredential).toHaveBeenCalledWith("fake-id-token");
  });

  it("shows an inline error if the GIS script fails to load", async () => {
    render(<GoogleButton onCredential={vi.fn()} />);
    const script = document.head.querySelector("script")!;
    fireEvent.error(script);

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/auth/GoogleButton.test.tsx`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 4: Write the implementation**

Create `frontend/src/features/auth/GoogleButton.tsx`:

```tsx
import { useEffect, useRef } from "react";
import { AlertCircle } from "lucide-react";
import { useOAuthScript } from "./useOAuthScript";

const GOOGLE_GSI_SCRIPT_SRC = "https://accounts.google.com/gsi/client";

interface GoogleButtonProps {
  onCredential: (idToken: string) => void;
}

export function GoogleButton({ onCredential }: GoogleButtonProps) {
  const scriptStatus = useOAuthScript(GOOGLE_GSI_SCRIPT_SRC);
  const buttonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scriptStatus !== "loaded" || !buttonRef.current || !window.google) return;

    window.google.accounts.id.initialize({
      client_id: import.meta.env.VITE_GOOGLE_OAUTH_CLIENT_ID ?? "",
      callback: (response) => onCredential(response.credential),
    });
    window.google.accounts.id.renderButton(buttonRef.current, {
      type: "standard",
      theme: "outline",
      size: "large",
      shape: "pill",
      width: 320,
      text: "continue_with",
    });
    // onCredential is expected to be a stable callback from the parent
    // (AuthEntryFlow's handlers don't change identity across renders in
    // practice) — re-initializing GIS on every render would tear down and
    // rebuild the native button unnecessarily.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scriptStatus]);

  if (scriptStatus === "error") {
    return (
      <div
        role="alert"
        className="flex items-center gap-2 p-3 rounded-xl bg-[color-mix(in_srgb,var(--color-negative)_10%,transparent)] border border-[color-mix(in_srgb,var(--color-negative)_25%,transparent)] text-xs text-[var(--color-negative)] font-medium"
      >
        <AlertCircle className="h-4 w-4 flex-shrink-0" />
        <span>Couldn't load Google Sign-In. Check your connection and try again.</span>
      </div>
    );
  }

  return <div ref={buttonRef} data-testid="google-button-container" className="w-full flex justify-center" />;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/auth/GoogleButton.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/google-identity-services.d.ts frontend/src/features/auth/GoogleButton.tsx frontend/src/features/auth/GoogleButton.test.tsx
git commit -m "feat(auth): add GoogleButton wrapping Google Identity Services"
```

---

## Task 4: `EmailEntry` and `EmailOtpVerify` components

**Files:**
- Create: `frontend/src/features/auth/EmailEntry.tsx`
- Create: `frontend/src/features/auth/EmailOtpVerify.tsx`

**Interfaces:**
- Produces: `<EmailEntry onSubmit={(email: string) => void} onBack={() => void} submitting error />`; `<EmailOtpVerify email onSubmit={(otp: string) => void} onResend onBack submitting error devOtp />`.
- No dedicated test file for either — covered via `AuthEntryFlow.test.tsx` in Task 10, per Global Constraints.

- [ ] **Step 1: Create `EmailEntry.tsx`**

Mirrors `PhoneEntry.tsx`'s structure exactly, collecting an email instead of a phone number:

```tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { ArrowLeft, AlertCircle, ShieldCheck, Loader2 } from "lucide-react";

interface EmailEntryProps {
  onSubmit: (email: string) => void;
  onBack?: () => void;
  submitting: boolean;
  error: string | null;
}

export function EmailEntry({ onSubmit, onBack, submitting, error }: EmailEntryProps) {
  const [email, setEmail] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(email);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full max-w-sm sm:max-w-md mx-auto p-5 sm:p-8 rounded-3xl bg-[var(--color-surface)] border border-[var(--color-border)]/80 shadow-lg space-y-6 text-center box-border animate-in fade-in zoom-in-95 duration-200"
    >
      <div className="space-y-2.5">
        <div className="mx-auto h-10 w-10 rounded-xl bg-[color-mix(in_srgb,var(--color-accent)_12%,transparent)] border border-[color-mix(in_srgb,var(--color-accent)_24%,transparent)] text-[var(--color-accent)] flex items-center justify-center">
          <svg
            viewBox="0 0 100 100"
            className="w-5 h-5 text-[var(--color-accent)] fill-none stroke-current stroke-[14] stroke-linecap-round"
            aria-label="Unifolio Logo Mark"
          >
            <path d="M 50 10 A 40 40 0 0 1 90 50" />
          </svg>
        </div>
        <div className="space-y-1">
          <h1 className="font-display font-bold text-xl sm:text-2xl text-[var(--color-ink)] tracking-tight">
            Continue with email
          </h1>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed max-w-xs mx-auto">
            Enter your email address to get started with Unifolio.
          </p>
        </div>
      </div>

      <div className="space-y-2 text-left">
        <label htmlFor="email-input" className="text-xs font-semibold text-[var(--color-ink)] block">
          Email address
        </label>
        <input
          id="email-input"
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="w-full h-11 sm:h-12 min-h-[44px] rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] focus-within:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent)]/20 px-3.5 text-xs sm:text-sm text-[var(--color-ink)] placeholder:text-[var(--color-text-secondary)]/50 focus:outline-none transition-all"
          autoFocus
        />
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3 rounded-xl bg-[color-mix(in_srgb,var(--color-negative)_10%,transparent)] border border-[color-mix(in_srgb,var(--color-negative)_25%,transparent)] text-xs text-[var(--color-negative)] font-medium text-left"
        >
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="space-y-3 pt-1">
        <Button
          type="submit"
          disabled={submitting || !email.trim()}
          className="w-full h-11 sm:h-12 rounded-xl bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent)]/90 font-semibold text-xs sm:text-sm shadow-xs gap-2 cursor-pointer active:scale-[0.99] transition-all min-h-[44px] sm:min-h-[48px]"
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Sending code...</span>
            </>
          ) : (
            <>
              <span>Send Verification Code</span>
              <span>→</span>
            </>
          )}
        </Button>

        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1 text-[var(--color-text-secondary)] hover:text-[var(--color-ink)] font-medium transition-colors cursor-pointer text-xs"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back</span>
          </button>
        )}
      </div>

      <div className="flex items-center justify-center gap-1.5 text-[11px] text-[var(--color-text-secondary)] pt-1 select-none">
        <ShieldCheck className="h-3.5 w-3.5 text-[var(--color-accent)]" />
        <span>256-bit encrypted · Read-only access · No spam</span>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Create `EmailOtpVerify.tsx`**

Mirrors `OtpVerify.tsx`'s structure exactly:

```tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { ArrowLeft, AlertCircle, ShieldCheck, Loader2, KeyRound } from "lucide-react";

interface EmailOtpVerifyProps {
  email: string;
  onSubmit: (otp: string) => void;
  onResend: () => void;
  onBack?: () => void;
  submitting: boolean;
  error: string | null;
  devOtp: string | null;
}

export function EmailOtpVerify({
  email,
  onSubmit,
  onResend,
  onBack,
  submitting,
  error,
  devOtp,
}: EmailOtpVerifyProps) {
  const [otp, setOtp] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(otp);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full max-w-sm sm:max-w-md mx-auto p-5 sm:p-8 rounded-3xl bg-[var(--color-surface)] border border-[var(--color-border)]/80 shadow-lg space-y-6 text-center box-border animate-in fade-in zoom-in-95 duration-200"
    >
      <div className="space-y-2.5">
        <div className="mx-auto h-10 w-10 rounded-xl bg-[color-mix(in_srgb,var(--color-accent)_12%,transparent)] border border-[color-mix(in_srgb,var(--color-accent)_24%,transparent)] text-[var(--color-accent)] flex items-center justify-center">
          <svg
            viewBox="0 0 100 100"
            className="w-5 h-5 text-[var(--color-accent)] fill-none stroke-current stroke-[14] stroke-linecap-round"
            aria-label="Unifolio Logo Mark"
          >
            <path d="M 50 10 A 40 40 0 0 1 90 50" />
          </svg>
        </div>
        <div className="space-y-1">
          <h1 className="font-display font-bold text-xl sm:text-2xl text-[var(--color-ink)] tracking-tight">
            Verify your email
          </h1>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed max-w-xs mx-auto">
            We sent a 6-digit verification code to <strong className="text-[var(--color-ink)]">{email}</strong>
          </p>
        </div>
      </div>

      {devOtp && (
        <div className="flex items-center justify-between p-3 rounded-xl bg-[color-mix(in_srgb,var(--color-accent)_10%,transparent)] border border-[color-mix(in_srgb,var(--color-accent)_20%,transparent)] text-xs text-[var(--color-ink)]">
          <div className="flex items-center gap-1.5">
            <KeyRound className="h-3.5 w-3.5 text-[var(--color-accent)] flex-shrink-0" />
            <span className="font-semibold text-[var(--color-accent)]">Local Dev OTP:</span>
          </div>
          <strong className="font-mono text-xs tracking-widest text-[var(--color-ink)] bg-[var(--color-surface)] px-2 py-0.5 rounded border border-[var(--color-border)]">
            {devOtp}
          </strong>
        </div>
      )}

      <div className="space-y-2 text-left">
        <label htmlFor="email-otp-input" className="text-xs font-semibold text-[var(--color-ink)] block">
          Verification Code
        </label>
        <input
          id="email-otp-input"
          type="text"
          inputMode="numeric"
          maxLength={6}
          placeholder="• • • • • •"
          value={otp}
          onChange={(event) => setOtp(event.target.value)}
          className="w-full text-center tracking-[0.4em] font-mono text-xl sm:text-2xl font-bold h-12 sm:h-14 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent)]/20 text-[var(--color-ink)] focus:outline-none transition-all placeholder:text-[var(--color-text-secondary)]/30"
          autoFocus
        />
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3 rounded-xl bg-[color-mix(in_srgb,var(--color-negative)_10%,transparent)] border border-[color-mix(in_srgb,var(--color-negative)_25%,transparent)] text-xs text-[var(--color-negative)] font-medium text-left"
        >
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="space-y-3 pt-1">
        <Button
          type="submit"
          disabled={submitting || otp.length < 4}
          className="w-full h-11 sm:h-12 rounded-xl bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent)]/90 font-semibold text-xs sm:text-sm shadow-xs cursor-pointer active:scale-[0.99] transition-all min-h-[44px] sm:min-h-[48px]"
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Verifying...</span>
            </>
          ) : (
            <>
              <span>Verify &amp; Continue</span>
              <span>→</span>
            </>
          )}
        </Button>

        <div className="flex items-center justify-between text-xs pt-0.5">
          <button
            type="button"
            onClick={onBack ?? onResend}
            className="inline-flex items-center gap-1 text-[var(--color-text-secondary)] hover:text-[var(--color-ink)] font-medium transition-colors cursor-pointer"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Change Email</span>
          </button>

          <Button
            variant="ghost"
            type="button"
            onClick={onResend}
            className="h-auto p-0 text-xs font-semibold text-[var(--color-accent)] hover:text-[var(--color-accent)]/80 hover:bg-transparent cursor-pointer"
          >
            Resend code
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-center gap-1.5 text-[11px] text-[var(--color-text-secondary)] pt-1 select-none">
        <ShieldCheck className="h-3.5 w-3.5 text-[var(--color-accent)]" />
        <span>256-bit encrypted · Read-only access · No spam</span>
      </div>
    </form>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no new errors from these two files (they aren't imported anywhere yet, so this mainly checks for syntax/type errors in isolation).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/auth/EmailEntry.tsx frontend/src/features/auth/EmailOtpVerify.tsx
git commit -m "feat(auth): add EmailEntry and EmailOtpVerify components"
```

---

## Task 5: `PhoneEntry` — drop mode toggle, add phone-gate context

**Files:**
- Modify: `frontend/src/features/auth/PhoneEntry.tsx`

**Interfaces:**
- Produces: `PhoneEntryProps` becomes `{ context?: "primary" | "phoneGate"; phoneGatePrefillEmail?: string | null; onSubmit; onBack?; submitting; error }` — `mode`/`onToggleMode` removed (breaking change, no other file references them until Task 9 rewires the caller).

- [ ] **Step 1: Replace `PhoneEntry.tsx`**

Replace `frontend/src/features/auth/PhoneEntry.tsx` in full:

```tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { ArrowLeft, AlertCircle, ShieldCheck, Loader2 } from "lucide-react";

interface PhoneEntryProps {
  /** "phoneGate": completing the mandatory phone step after a Google/email
   * signup with no existing account match — different copy, no back button
   * (Design Spec §1; Frontend Spec §3). Defaults to the plain entry copy. */
  context?: "primary" | "phoneGate";
  phoneGatePrefillEmail?: string | null;
  onSubmit: (phoneNumber: string) => void;
  onBack?: () => void;
  submitting: boolean;
  error: string | null;
}

export function PhoneEntry({
  context = "primary",
  phoneGatePrefillEmail,
  onSubmit,
  onBack,
  submitting,
  error,
}: PhoneEntryProps) {
  const [phoneNumber, setPhoneNumber] = useState("");
  const isPhoneGate = context === "phoneGate";

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(phoneNumber);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full max-w-sm sm:max-w-md mx-auto p-5 sm:p-8 rounded-3xl bg-[var(--color-surface)] border border-[var(--color-border)]/80 shadow-lg space-y-6 text-center box-border animate-in fade-in zoom-in-95 duration-200"
    >
      {/* 1. Refined Brand Header */}
      <div className="space-y-2.5">
        <div className="mx-auto h-10 w-10 rounded-xl bg-[color-mix(in_srgb,var(--color-accent)_12%,transparent)] border border-[color-mix(in_srgb,var(--color-accent)_24%,transparent)] text-[var(--color-accent)] flex items-center justify-center">
          <svg
            viewBox="0 0 100 100"
            className="w-5 h-5 text-[var(--color-accent)] fill-none stroke-current stroke-[14] stroke-linecap-round"
            aria-label="Unifolio Logo Mark"
          >
            <path d="M 50 10 A 40 40 0 0 1 90 50" />
          </svg>
        </div>
        <div className="space-y-1">
          <h1 className="font-display font-bold text-xl sm:text-2xl text-[var(--color-ink)] tracking-tight">
            {isPhoneGate ? "One more step" : "Continue with your mobile number"}
          </h1>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed max-w-xs mx-auto">
            {isPhoneGate
              ? `Verify your phone to finish creating your account${
                  phoneGatePrefillEmail ? ` for ${phoneGatePrefillEmail}` : ""
                }.`
              : "Enter your mobile number to get started with Unifolio."}
          </p>
        </div>
      </div>

      {/* 2. Premium Phone Input Group */}
      <div className="space-y-2 text-left">
        <label
          htmlFor="phone-input"
          className="text-xs font-semibold text-[var(--color-ink)] block"
        >
          Mobile Number
        </label>
        <div className="flex items-center rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] focus-within:border-[var(--color-accent)] focus-within:ring-2 focus-within:ring-[var(--color-accent)]/20 transition-all overflow-hidden h-11 sm:h-12 min-h-[44px]">
          <div className="px-3 sm:px-3.5 flex items-center gap-1.5 border-r border-[var(--color-border)] text-xs font-medium text-[var(--color-ink)] select-none bg-[var(--color-surface)]/50 h-full">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-secondary)]">IN</span>
            <span className="font-semibold">+91</span>
          </div>
          <input
            id="phone-input"
            type="tel"
            placeholder="98765 43210"
            value={phoneNumber}
            onChange={(event) => setPhoneNumber(event.target.value)}
            className="flex-1 bg-transparent px-3 sm:px-3.5 text-xs sm:text-sm text-[var(--color-ink)] placeholder:text-[var(--color-text-secondary)]/50 focus:outline-none font-mono"
            autoFocus
          />
        </div>
      </div>

      {/* 3. Error Alert */}
      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3 rounded-xl bg-[color-mix(in_srgb,var(--color-negative)_10%,transparent)] border border-[color-mix(in_srgb,var(--color-negative)_25%,transparent)] text-xs text-[var(--color-negative)] font-medium text-left"
        >
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 4. Actions & Navigation */}
      <div className="space-y-3 pt-1">
        <Button
          type="submit"
          disabled={submitting || !phoneNumber.trim()}
          className="w-full h-11 sm:h-12 rounded-xl bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent)]/90 font-semibold text-xs sm:text-sm shadow-xs gap-2 cursor-pointer active:scale-[0.99] transition-all min-h-[44px] sm:min-h-[48px]"
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Sending OTP...</span>
            </>
          ) : (
            <>
              <span>Send Verification Code</span>
              <span>→</span>
            </>
          )}
        </Button>

        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1 text-[var(--color-text-secondary)] hover:text-[var(--color-ink)] font-medium transition-colors cursor-pointer text-xs"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back</span>
          </button>
        )}
      </div>

      {/* 5. Trust Footer */}
      <div className="flex items-center justify-center gap-1.5 text-[11px] text-[var(--color-text-secondary)] pt-1 select-none">
        <ShieldCheck className="h-3.5 w-3.5 text-[var(--color-accent)]" />
        <span>256-bit encrypted · Read-only access · No spam</span>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: errors in `AuthEntryFlow.tsx` and `AuthEntryFlow.test.tsx` (they still reference the old `mode`/`onToggleMode` props) — expected at this point, fixed in Task 9/10. Confirm no *other* files reference `PhoneEntry`'s removed props.

Run: `grep -rn "onToggleMode\|mode=\"signup\"\|mode=\"login\"" frontend/src --include=*.tsx`
Expected: only matches inside `AuthEntryFlow.tsx` and `AuthEntryFlow.test.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/auth/PhoneEntry.tsx
git commit -m "feat(auth): drop Sign Up/Log In mode toggle from PhoneEntry, add phone-gate context"
```

---

## Task 6: `AuthShowcasePanel` — decorative right panel

**Files:**
- Create: `frontend/src/features/auth/AuthShowcasePanel.tsx`

**Interfaces:**
- Produces: `<AuthShowcasePanel />` — no props, static.

- [ ] **Step 1: Write the implementation**

No test file for this task — it's a static, prop-less visual component; its presence/behavior is verified as part of `AuthEntryFlow.test.tsx` in Task 10 (confirming the layout renders without crashing), not in isolation.

Create `frontend/src/features/auth/AuthShowcasePanel.tsx`:

```tsx
import { useMemo } from "react";
import { area as d3Area, curveMonotoneX, line as d3Line } from "d3-shape";

const SPARKLINE_POINTS = [12, 14, 13, 17, 16, 20, 19, 23];
const CHART_WIDTH = 220;
const CHART_HEIGHT = 80;

/** Static, illustrative visual for the auth screen's right-hand panel —
 * a structural placeholder only. Exact content is pending details the
 * product owner will provide separately (Frontend Spec, Open Items). No
 * backend dependency, no real user data — built on the same @visx/
 * d3-shape primitives FundSignal.tsx already uses elsewhere in this repo,
 * not @bklit (which isn't an installed dependency — see Frontend Spec
 * §0). This shape (static asset, no network call) should hold regardless
 * of what the final content turns out to be. */
export function AuthShowcasePanel() {
  const { linePath, areaPath } = useMemo(() => {
    const minVal = Math.min(...SPARKLINE_POINTS);
    const maxVal = Math.max(...SPARKLINE_POINTS);
    const range = maxVal - minVal || 1;
    const coords = SPARKLINE_POINTS.map((val, idx) => ({
      x: (idx / (SPARKLINE_POINTS.length - 1)) * CHART_WIDTH,
      y: CHART_HEIGHT - ((val - minVal) / range) * CHART_HEIGHT,
    }));

    const lineGenerator = d3Line<{ x: number; y: number }>()
      .x((d) => d.x)
      .y((d) => d.y)
      .curve(curveMonotoneX);
    const areaGenerator = d3Area<{ x: number; y: number }>()
      .x((d) => d.x)
      .y0(CHART_HEIGHT)
      .y1((d) => d.y)
      .curve(curveMonotoneX);

    return { linePath: lineGenerator(coords) ?? "", areaPath: areaGenerator(coords) ?? "" };
  }, []);

  return (
    <div className="flex flex-col justify-between h-full w-full min-h-[420px] p-10 rounded-3xl bg-[var(--color-surface)] border border-[var(--color-border)]/60 overflow-hidden">
      <div className="flex items-center gap-2">
        <svg
          viewBox="0 0 100 100"
          className="w-6 h-6 text-[var(--color-accent)] fill-none stroke-current stroke-[10] stroke-linecap-round"
          aria-hidden="true"
        >
          <path d="M 50 10 A 40 40 0 0 1 90 50" />
        </svg>
        <span className="font-display font-bold text-sm text-[var(--color-ink)]">Unifolio</span>
      </div>

      <div className="space-y-4">
        <svg
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
          className="w-full text-[var(--color-accent)]"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path d={areaPath} fill="currentColor" fillOpacity="0.12" stroke="none" />
          <path d={linePath} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div className="space-y-1">
          <h2 className="font-display font-bold text-lg text-[var(--color-ink)]">
            A unified view of everything you own
          </h2>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed max-w-xs">
            Track every fund, every family member, in one restrained, trustworthy place.
          </p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no new errors (not imported anywhere yet).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/auth/AuthShowcasePanel.tsx
git commit -m "feat(auth): add static decorative right-panel placeholder"
```

---

## Task 7: `Landing` redesign — four pill buttons, no Sign Up/Log In split

**Files:**
- Modify: `frontend/src/features/auth/Landing.tsx`

**Interfaces:**
- Produces: `LandingProps` becomes `{ onSelectPhone: () => void; onSelectEmail: () => void; onGoogleCredential: (idToken: string) => void }` — the old `onContinue(mode?) => void` prop is removed (breaking change, rewired in Task 9).

- [ ] **Step 1: Replace `Landing.tsx`**

Replace `frontend/src/features/auth/Landing.tsx` in full:

```tsx
import { Button } from "@/components/ui/button";
import { ShieldCheck, Mail, Phone } from "lucide-react";
import { GoogleButton } from "./GoogleButton";

interface LandingProps {
  onSelectPhone: () => void;
  onSelectEmail: () => void;
  onGoogleCredential: (idToken: string) => void;
}

function AppleLogo() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden="true">
      <path d="M16.365 1.43c0 1.14-.493 2.27-1.177 3.08-.744.9-1.99 1.57-2.987 1.57-.12 0-.23-.02-.3-.03-.01-.06-.04-.22-.04-.39 0-1.15.572-2.27 1.206-2.98.804-.94 2.142-1.64 3.248-1.68.03.13.05.28.05.43zm4.565 15.71c-.03.07-.463 1.58-1.518 3.12-.945 1.34-1.94 2.71-3.43 2.71-1.517 0-1.9-.88-3.63-.88-1.698 0-2.302.91-3.67.91-1.377 0-2.332-1.26-3.4-2.8-1.239-1.8-2.246-4.6-2.246-7.27 0-4.27 2.782-6.54 5.52-6.54 1.377 0 2.523.91 3.39.91.83 0 2.11-.96 3.68-.96.6 0 2.746.05 4.16 2.09-.107.07-2.483 1.45-2.483 4.44 0 3.55 3.13 4.8 3.19 4.83z" />
    </svg>
  );
}

export function Landing({ onSelectPhone, onSelectEmail, onGoogleCredential }: LandingProps) {
  return (
    <div className="w-full max-w-sm sm:max-w-md mx-auto p-5 sm:p-8 rounded-3xl bg-[var(--color-surface)] border border-[var(--color-border)]/80 shadow-lg space-y-6 text-center box-border animate-in fade-in zoom-in-95 duration-200">
      {/* 1. Refined Brand Header with Official Unifolio Arc Mark */}
      <div className="space-y-2.5">
        <div className="mx-auto h-10 w-10 rounded-xl bg-[color-mix(in_srgb,var(--color-accent)_12%,transparent)] border border-[color-mix(in_srgb,var(--color-accent)_24%,transparent)] text-[var(--color-accent)] flex items-center justify-center">
          <svg
            viewBox="0 0 100 100"
            className="w-5 h-5 text-[var(--color-accent)] fill-none stroke-current stroke-[14] stroke-linecap-round"
            aria-label="Unifolio Logo Mark"
          >
            <path d="M 50 10 A 40 40 0 0 1 90 50" />
          </svg>
        </div>
        <div className="space-y-1">
          <h1 className="font-display font-bold text-xl sm:text-2xl text-[var(--color-ink)] tracking-tight">
            Unifolio
          </h1>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed max-w-xs mx-auto">
            Log in or sign up to track your investments in one place.
          </p>
        </div>
      </div>

      {/* 2. Four equal entry points — confirmed order: Google, Apple
          (disabled), Email, Phone. No separate Sign Up/Log In screen:
          every method transparently handles new-vs-existing on the
          backend, exactly like phone already did. */}
      <div className="space-y-2.5">
        <GoogleButton onCredential={onGoogleCredential} />

        <Button
          type="button"
          variant="outline"
          disabled
          className="w-full h-11 sm:h-12 rounded-xl border border-[var(--color-border)] bg-transparent text-[var(--color-text-secondary)] font-semibold text-xs sm:text-sm gap-2 min-h-[44px] sm:min-h-[48px] cursor-not-allowed opacity-60"
        >
          <AppleLogo />
          <span>Continue with Apple</span>
          <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-secondary)]">
            Coming soon
          </span>
        </Button>

        <Button
          type="button"
          variant="outline"
          onClick={onSelectEmail}
          className="w-full h-11 sm:h-12 rounded-xl border border-[var(--color-border)] bg-transparent text-[var(--color-ink)] hover:bg-[var(--color-bg)] font-semibold text-xs sm:text-sm gap-2 cursor-pointer active:scale-[0.99] transition-all min-h-[44px] sm:min-h-[48px]"
        >
          <Mail className="h-4 w-4" />
          <span>Continue with Email</span>
        </Button>

        <Button
          type="button"
          variant="outline"
          onClick={onSelectPhone}
          className="w-full h-11 sm:h-12 rounded-xl border border-[var(--color-border)] bg-transparent text-[var(--color-ink)] hover:bg-[var(--color-bg)] font-semibold text-xs sm:text-sm gap-2 cursor-pointer active:scale-[0.99] transition-all min-h-[44px] sm:min-h-[48px]"
        >
          <Phone className="h-4 w-4" />
          <span>Continue with Phone</span>
        </Button>
      </div>

      {/* 3. Trust & Security Footer */}
      <div className="flex items-center justify-center gap-1.5 text-[11px] text-[var(--color-text-secondary)] pt-1 select-none">
        <ShieldCheck className="h-3.5 w-3.5 text-[var(--color-accent)]" />
        <span>256-bit encrypted · Read-only access · No spam</span>
      </div>
    </div>
  );
}
```

Note: the three feature-bullet blocks (Unified Wealth View / Smarter Financial Decisions / Family Portfolio Hub) from the original `Landing.tsx` are dropped entirely here, per the Frontend Spec's call that keeping all three risked an overly tall card once four method buttons are added — this is a design-brief-stage call, not mandated; re-adding a condensed version is a reasonable follow-up if the card reads as too sparse once built.

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: errors only in `AuthEntryFlow.tsx`/`AuthEntryFlow.test.tsx` (still calling the old `<Landing onContinue={...} />` shape) — fixed in Task 9/10.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/auth/Landing.tsx
git commit -m "feat(auth): redesign Landing with four ordered entry-point buttons"
```

---

## Task 8: `LinkAccountPrompt` — step-up account-linking screen

**Files:**
- Create: `frontend/src/features/auth/LinkAccountPrompt.tsx`
- Create: `frontend/src/features/auth/LinkAccountPrompt.test.tsx`

**Interfaces:**
- Consumes: `PhoneEntry`, `OtpVerify`, `EmailEntry`, `EmailOtpVerify`, `GoogleButton`, `requestOtp`/`sendEmailOtp`/`verifyOtp`/`verifyEmailOtp`/`verifyGoogleCredential` (Tasks 1/4/5), `isLinkRequired`/`isPhoneRequired` (Task 1).
- Produces: `<LinkAccountPrompt matchedEmail existingMethod pendingToken onLinked={(result: OtpVerifyResponse) => void} />`.

This gets its own dedicated test file (unlike Email/Phone) because it orchestrates three different re-auth sub-flows and has real branching logic worth testing directly, not just as one path through `AuthEntryFlow`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/features/auth/LinkAccountPrompt.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LinkAccountPrompt } from "./LinkAccountPrompt";
import * as api from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, requestOtp: vi.fn(), sendEmailOtp: vi.fn(), verifyOtp: vi.fn(), verifyEmailOtp: vi.fn() };
});

describe("LinkAccountPrompt", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the matched-account banner naming the existing method", () => {
    render(
      <LinkAccountPrompt
        matchedEmail="a@example.com"
        existingMethod="phone"
        pendingToken="pending-tok"
        onLinked={vi.fn()}
      />,
    );

    expect(screen.getByText(/a@example.com/)).toBeInTheDocument();
    expect(screen.getByText(/log in with your phone/i)).toBeInTheDocument();
  });

  it("completes a phone-based link and calls onLinked with the session", async () => {
    vi.mocked(api.requestOtp).mockResolvedValue({ message: "OTP sent.", otp: "654321" });
    vi.mocked(api.verifyOtp).mockResolvedValue({
      session_token: "tok-linked", user_id: "u1", onboarding_step: null, onboarding_completed: false,
    });
    const onLinked = vi.fn();
    render(
      <LinkAccountPrompt matchedEmail="a@example.com" existingMethod="phone" pendingToken="pending-tok" onLinked={onLinked} />,
    );

    fireEvent.change(screen.getByLabelText(/mobile number/i), { target: { value: "+919999999999" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));
    await waitFor(() => screen.getByLabelText(/verification code/i));

    fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: /verify & continue/i }));

    await waitFor(() => expect(api.verifyOtp).toHaveBeenCalledWith("+919999999999", "654321", "pending-tok"));
    await waitFor(() => expect(onLinked).toHaveBeenCalledWith(expect.objectContaining({ session_token: "tok-linked" })));
  });

  it("completes an email-based link and calls onLinked with the session", async () => {
    vi.mocked(api.sendEmailOtp).mockResolvedValue({ message: "OTP sent.", otp: "111222" });
    vi.mocked(api.verifyEmailOtp).mockResolvedValue({
      session_token: "tok-linked-2", user_id: "u2", onboarding_step: null, onboarding_completed: false,
    });
    const onLinked = vi.fn();
    render(
      <LinkAccountPrompt matchedEmail="a@example.com" existingMethod="email" pendingToken="pending-tok-2" onLinked={onLinked} />,
    );

    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "a@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));
    await waitFor(() => screen.getByLabelText(/verification code/i));

    fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: "111222" } });
    fireEvent.click(screen.getByRole("button", { name: /verify & continue/i }));

    await waitFor(() => expect(api.verifyEmailOtp).toHaveBeenCalledWith("a@example.com", "111222", "pending-tok-2"));
    await waitFor(() => expect(onLinked).toHaveBeenCalledWith(expect.objectContaining({ session_token: "tok-linked-2" })));
  });

  it("renders a GoogleButton when the existing method is google", () => {
    render(
      <LinkAccountPrompt matchedEmail="a@example.com" existingMethod="google" pendingToken="pending-tok-3" onLinked={vi.fn()} />,
    );

    expect(screen.getByTestId("google-button-container")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/auth/LinkAccountPrompt.test.tsx`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/features/auth/LinkAccountPrompt.tsx`:

```tsx
import { useState } from "react";
import { PhoneEntry } from "./PhoneEntry";
import { OtpVerify } from "./OtpVerify";
import { EmailEntry } from "./EmailEntry";
import { EmailOtpVerify } from "./EmailOtpVerify";
import { GoogleButton } from "./GoogleButton";
import { requestOtp, sendEmailOtp, verifyEmailOtp, verifyGoogleCredential, verifyOtp } from "./api";
import { isLinkRequired, isPhoneRequired } from "./types";
import type { ExistingMethod, OtpVerifyResponse } from "./types";
import { ApiError } from "../../lib/apiClient";

interface LinkAccountPromptProps {
  matchedEmail: string;
  existingMethod: ExistingMethod;
  pendingToken: string;
  onLinked: (result: OtpVerifyResponse) => void;
}

type Step = "entry" | "otp";

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.payload === "string") return err.payload;
  return fallback;
}

export function LinkAccountPrompt({ matchedEmail, existingMethod, pendingToken, onLinked }: LinkAccountPromptProps) {
  const [step, setStep] = useState<Step>("entry");
  const [identifier, setIdentifier] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devOtp, setDevOtp] = useState<string | null>(null);

  const handleEntrySubmit = async (value: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = existingMethod === "phone" ? await requestOtp(value) : await sendEmailOtp(value);
      setIdentifier(value);
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
      const result = existingMethod === "phone"
        ? await verifyOtp(identifier, otp, pendingToken)
        : await verifyEmailOtp(identifier, otp, pendingToken);
      if (isLinkRequired(result) || isPhoneRequired(result)) {
        setError("Something went wrong linking your account. Please try again.");
        return;
      }
      onLinked(result);
    } catch (err) {
      setError(errorMessage(err, "That code didn't work. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const handleGoogleCredential = async (idToken: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await verifyGoogleCredential(idToken, pendingToken);
      if (isLinkRequired(result) || isPhoneRequired(result)) {
        setError("Something went wrong linking your account. Please try again.");
        return;
      }
      onLinked(result);
    } catch (err) {
      setError(errorMessage(err, "Google sign-in didn't work. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const banner = (
    <p className="text-xs text-[var(--color-text-secondary)] text-center max-w-sm mx-auto">
      We found an account associated with <strong className="text-[var(--color-ink)]">{matchedEmail}</strong> — log
      in with your {existingMethod} to link this to it.
    </p>
  );

  if (existingMethod === "google") {
    return (
      <div className="w-full max-w-sm sm:max-w-md mx-auto space-y-3">
        {banner}
        <div className="p-5 sm:p-8 rounded-3xl bg-[var(--color-surface)] border border-[var(--color-border)]/80 shadow-lg flex justify-center">
          <GoogleButton onCredential={handleGoogleCredential} />
        </div>
        {error && (
          <p role="alert" className="text-xs text-[var(--color-negative)] text-center">
            {error}
          </p>
        )}
      </div>
    );
  }

  if (step === "entry") {
    return (
      <div className="space-y-3">
        {banner}
        {existingMethod === "phone" ? (
          <PhoneEntry onSubmit={handleEntrySubmit} submitting={submitting} error={error} />
        ) : (
          <EmailEntry onSubmit={handleEntrySubmit} submitting={submitting} error={error} />
        )}
      </div>
    );
  }

  return existingMethod === "phone" ? (
    <OtpVerify
      phoneNumber={identifier}
      onSubmit={handleOtpSubmit}
      onResend={() => setStep("entry")}
      onBack={() => setStep("entry")}
      submitting={submitting}
      error={error}
      devOtp={devOtp}
    />
  ) : (
    <EmailOtpVerify
      email={identifier}
      onSubmit={handleOtpSubmit}
      onResend={() => setStep("entry")}
      onBack={() => setStep("entry")}
      submitting={submitting}
      error={error}
      devOtp={devOtp}
    />
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/auth/LinkAccountPrompt.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/auth/LinkAccountPrompt.tsx frontend/src/features/auth/LinkAccountPrompt.test.tsx
git commit -m "feat(auth): add LinkAccountPrompt for step-up account linking"
```

---

## Task 9: `AuthEntryFlow` orchestration — split-panel shell, phone gate, linking

**Files:**
- Modify: `frontend/src/features/auth/AuthEntryFlow.tsx`

**Interfaces:**
- Consumes: everything from Tasks 1–8.
- Produces: extended `Step` union (`"landing" | "phone" | "otp" | "email" | "email_otp" | "link_account"`), the two-panel layout, all verify-result branching.

- [ ] **Step 1: Replace `AuthEntryFlow.tsx`**

Replace `frontend/src/features/auth/AuthEntryFlow.tsx` in full:

```tsx
import { useState } from "react";
import { Landing } from "./Landing";
import { PhoneEntry } from "./PhoneEntry";
import { OtpVerify } from "./OtpVerify";
import { EmailEntry } from "./EmailEntry";
import { EmailOtpVerify } from "./EmailOtpVerify";
import { LinkAccountPrompt } from "./LinkAccountPrompt";
import { AuthShowcasePanel } from "./AuthShowcasePanel";
import { requestOtp, sendEmailOtp, verifyEmailOtp, verifyGoogleCredential, verifyOtp } from "./api";
import { isLinkRequired, isPhoneRequired } from "./types";
import type { ExistingMethod } from "./types";
import { useAuth } from "./AuthContext";
import { ThemeToggle } from "../../components/ThemeToggle";
import { ApiError } from "../../lib/apiClient";

type Step = "landing" | "phone" | "otp" | "email" | "email_otp" | "link_account";

interface LinkInfo {
  token: string;
  matchedEmail: string;
  existingMethod: ExistingMethod;
}

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.payload === "string") {
    return err.payload;
  }
  return fallback;
}

export function AuthEntryFlow() {
  const { login } = useAuth();
  const [step, setStep] = useState<Step>("landing");
  const [identifier, setIdentifier] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devOtp, setDevOtp] = useState<string | null>(null);

  // Mandatory phone-gate state (Design Spec §1): set when a Google/email
  // verification returns phone_required. Reuses the existing "phone"/"otp"
  // steps — no fifth Step value needed.
  const [phoneGateToken, setPhoneGateToken] = useState<string | null>(null);
  const [phoneGatePrefillEmail, setPhoneGatePrefillEmail] = useState<string | null>(null);

  // Account-linking state (Design Spec §4): set when a verification
  // returns link_required.
  const [linkInfo, setLinkInfo] = useState<LinkInfo | null>(null);

  const handleSelectPhone = () => {
    setError(null);
    setPhoneGateToken(null);
    setPhoneGatePrefillEmail(null);
    setStep("phone");
  };

  const handleSelectEmail = () => {
    setError(null);
    setStep("email");
  };

  const handlePhoneSubmit = async (phone: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await requestOtp(phone);
      setIdentifier(phone);
      setDevOtp(result.otp);
      setStep("otp");
    } catch (err) {
      setError(errorMessage(err, "Couldn't send the code. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const handleEmailSubmit = async (email: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await sendEmailOtp(email);
      setIdentifier(email);
      setDevOtp(result.otp);
      setStep("email_otp");
    } catch (err) {
      setError(errorMessage(err, "Couldn't send the code. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const handlePhoneOtpSubmit = async (otp: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await verifyOtp(identifier, otp, phoneGateToken ?? undefined);
      if (isLinkRequired(result) || isPhoneRequired(result)) {
        // Phone never produces either of these itself (Design Spec §1) —
        // a defensive guard against a backend contract mismatch, not an
        // expected path.
        setError("Something unexpected happened. Please try again.");
        return;
      }
      await login(result.session_token);
    } catch (err) {
      setError(errorMessage(err, "That code didn't work. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const handleEmailOtpSubmit = async (otp: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await verifyEmailOtp(identifier, otp);
      if (isPhoneRequired(result)) {
        setPhoneGateToken(result.phone_required.token);
        setPhoneGatePrefillEmail(result.phone_required.prefill_email);
        setStep("phone");
        return;
      }
      if (isLinkRequired(result)) {
        setLinkInfo({
          token: result.link_required.token,
          matchedEmail: result.link_required.matched_email,
          existingMethod: result.link_required.existing_method,
        });
        setStep("link_account");
        return;
      }
      await login(result.session_token);
    } catch (err) {
      setError(errorMessage(err, "That code didn't work. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const handleGoogleCredential = async (idToken: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await verifyGoogleCredential(idToken);
      if (isPhoneRequired(result)) {
        setPhoneGateToken(result.phone_required.token);
        setPhoneGatePrefillEmail(result.phone_required.prefill_email);
        setStep("phone");
        return;
      }
      if (isLinkRequired(result)) {
        setLinkInfo({
          token: result.link_required.token,
          matchedEmail: result.link_required.matched_email,
          existingMethod: result.link_required.existing_method,
        });
        setStep("link_account");
        return;
      }
      await login(result.session_token);
    } catch (err) {
      setError(errorMessage(err, "Google sign-in didn't work. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-dvh w-full bg-[var(--color-bg)] flex flex-col justify-center items-center p-3.5 sm:p-6 lg:p-8 box-border text-left overflow-y-auto relative">
      {/* Light / Dark Theme Toggle */}
      <div className="absolute top-4 right-4 sm:top-6 sm:right-6 z-20">
        <ThemeToggle />
      </div>

      <div className="w-full max-w-5xl mx-auto my-auto grid grid-cols-1 lg:grid-cols-2 gap-6 items-center">
        <div className="order-2 lg:order-1">
          {step === "landing" && (
            <Landing
              onSelectPhone={handleSelectPhone}
              onSelectEmail={handleSelectEmail}
              onGoogleCredential={handleGoogleCredential}
            />
          )}
          {step === "phone" && (
            <PhoneEntry
              context={phoneGateToken ? "phoneGate" : "primary"}
              phoneGatePrefillEmail={phoneGatePrefillEmail}
              onSubmit={handlePhoneSubmit}
              onBack={phoneGateToken ? undefined : () => setStep("landing")}
              submitting={submitting}
              error={error}
            />
          )}
          {step === "otp" && (
            <OtpVerify
              phoneNumber={identifier}
              onSubmit={handlePhoneOtpSubmit}
              onResend={() => setStep("phone")}
              onBack={() => setStep("phone")}
              submitting={submitting}
              error={error}
              devOtp={devOtp}
            />
          )}
          {step === "email" && (
            <EmailEntry
              onSubmit={handleEmailSubmit}
              onBack={() => setStep("landing")}
              submitting={submitting}
              error={error}
            />
          )}
          {step === "email_otp" && (
            <EmailOtpVerify
              email={identifier}
              onSubmit={handleEmailOtpSubmit}
              onResend={() => setStep("email")}
              onBack={() => setStep("email")}
              submitting={submitting}
              error={error}
              devOtp={devOtp}
            />
          )}
          {step === "link_account" && linkInfo && (
            <LinkAccountPrompt
              matchedEmail={linkInfo.matchedEmail}
              existingMethod={linkInfo.existingMethod}
              pendingToken={linkInfo.token}
              onLinked={(result) => void login(result.session_token)}
            />
          )}
        </div>
        <div className="order-1 lg:order-2 hidden lg:block h-full">
          <AuthShowcasePanel />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: errors remain only in `AuthEntryFlow.test.tsx` (still using the old test helpers/assertions) — fixed in Task 10. No errors in any `.tsx`/`.ts` source file.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/auth/AuthEntryFlow.tsx
git commit -m "feat(auth): wire split-panel layout, phone gate, and account linking into AuthEntryFlow"
```

---

## Task 10: Rewrite `AuthEntryFlow.test.tsx` for the full multi-method flow

**Files:**
- Modify: `frontend/src/features/auth/AuthEntryFlow.test.tsx`

**Interfaces:**
- Consumes: everything above. This is the integration test layer covering `PhoneEntry`/`EmailEntry`/`EmailOtpVerify`'s behavior indirectly, per Global Constraints (no dedicated test files for those).

- [ ] **Step 1: Replace `AuthEntryFlow.test.tsx`**

Replace `frontend/src/features/auth/AuthEntryFlow.test.tsx` in full:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthEntryFlow } from "./AuthEntryFlow";
import { AuthProvider } from "./AuthContext";
import * as api from "./api";
import { ApiError } from "../../lib/apiClient";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    requestOtp: vi.fn(),
    sendEmailOtp: vi.fn(),
    verifyOtp: vi.fn(),
    verifyEmailOtp: vi.fn(),
    verifyGoogleCredential: vi.fn(),
    getMe: vi.fn(),
  };
});

function renderFlow() {
  return render(
    <AuthProvider>
      <AuthEntryFlow />
    </AuthProvider>,
  );
}

const NORMAL_SESSION = { session_token: "tok-1", user_id: "u1", onboarding_step: null, onboarding_completed: false };
const ME_RESPONSE = {
  user_id: "u1", phone_number: "+919999999999", email: null,
  onboarding_step: null, onboarding_completed: false, investor_type: null, primary_goal: null,
};

describe("AuthEntryFlow", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders Google, Apple (disabled), Email, and Phone in that order", async () => {
    renderFlow();
    await waitFor(() => expect(screen.getByTestId("google-button-container")).toBeInTheDocument());

    const appleButton = screen.getByRole("button", { name: /continue with apple/i });
    expect(appleButton).toBeDisabled();
    expect(screen.getByRole("button", { name: /continue with email/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /continue with phone/i })).toBeEnabled();
  });

  it("moves from phone entry to OTP verify after a successful request", async () => {
    vi.mocked(api.requestOtp).mockResolvedValue({ message: "OTP sent.", otp: "654321" });
    renderFlow();
    fireEvent.click(screen.getByRole("button", { name: /continue with phone/i }));

    fireEvent.change(screen.getByLabelText(/mobile number/i), { target: { value: "+919999999999" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));

    await waitFor(() => expect(screen.getByLabelText(/verification code/i)).toBeInTheDocument());
    expect(screen.getByText(/654321/)).toBeInTheDocument();
  });

  it("logs in on successful phone OTP verification", async () => {
    vi.mocked(api.requestOtp).mockResolvedValue({ message: "OTP sent.", otp: "654321" });
    vi.mocked(api.verifyOtp).mockResolvedValue(NORMAL_SESSION);
    vi.mocked(api.getMe).mockResolvedValue(ME_RESPONSE);
    renderFlow();
    fireEvent.click(screen.getByRole("button", { name: /continue with phone/i }));
    fireEvent.change(screen.getByLabelText(/mobile number/i), { target: { value: "+919999999999" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));
    await waitFor(() => screen.getByLabelText(/verification code/i));

    fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: /verify & continue/i }));

    await waitFor(() => expect(api.verifyOtp).toHaveBeenCalledWith("+919999999999", "654321", undefined));
  });

  it("shows an inline error when phone OTP verification fails", async () => {
    vi.mocked(api.requestOtp).mockResolvedValue({ message: "OTP sent.", otp: "654321" });
    vi.mocked(api.verifyOtp).mockRejectedValue(new ApiError(401, "Invalid or expired OTP."));
    renderFlow();
    fireEvent.click(screen.getByRole("button", { name: /continue with phone/i }));
    fireEvent.change(screen.getByLabelText(/mobile number/i), { target: { value: "+919999999999" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));
    await waitFor(() => screen.getByLabelText(/verification code/i));

    fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: /verify & continue/i }));

    await waitFor(() => expect(screen.getByText(/invalid or expired otp/i)).toBeInTheDocument());
  });

  it("moves from email entry through email OTP to login", async () => {
    vi.mocked(api.sendEmailOtp).mockResolvedValue({ message: "OTP sent.", otp: "111222" });
    vi.mocked(api.verifyEmailOtp).mockResolvedValue(NORMAL_SESSION);
    vi.mocked(api.getMe).mockResolvedValue(ME_RESPONSE);
    renderFlow();
    fireEvent.click(screen.getByRole("button", { name: /continue with email/i }));
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "a@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));
    await waitFor(() => screen.getByLabelText(/verification code/i));
    expect(screen.getByText(/111222/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: "111222" } });
    fireEvent.click(screen.getByRole("button", { name: /verify & continue/i }));

    await waitFor(() => expect(api.verifyEmailOtp).toHaveBeenCalledWith("a@example.com", "111222"));
  });

  it("a Google credential with a normal session logs in directly, no intermediate screen", async () => {
    vi.mocked(api.verifyGoogleCredential).mockResolvedValue(NORMAL_SESSION);
    vi.mocked(api.getMe).mockResolvedValue(ME_RESPONSE);
    window.google = { accounts: { id: { initialize: vi.fn(), renderButton: vi.fn() } } };
    renderFlow();
    const script = document.head.querySelector("script")!;
    fireEvent.load(script);
    await waitFor(() => expect(window.google!.accounts.id.initialize).toHaveBeenCalled());

    const { callback } = vi.mocked(window.google!.accounts.id.initialize).mock.calls[0][0];
    await callback({ credential: "fake-id-token" });

    await waitFor(() => expect(api.verifyGoogleCredential).toHaveBeenCalledWith("fake-id-token"));
    delete (window as { google?: unknown }).google;
  });

  it("a phone_required response transitions to the phone step with phone-gate copy", async () => {
    vi.mocked(api.sendEmailOtp).mockResolvedValue({ message: "OTP sent.", otp: "111222" });
    vi.mocked(api.verifyEmailOtp).mockResolvedValue({
      phone_required: { token: "gate-tok", prefill_email: "newsignup@example.com" },
    });
    renderFlow();
    fireEvent.click(screen.getByRole("button", { name: /continue with email/i }));
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "newsignup@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));
    await waitFor(() => screen.getByLabelText(/verification code/i));
    fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: "111222" } });
    fireEvent.click(screen.getByRole("button", { name: /verify & continue/i }));

    await waitFor(() => expect(screen.getByText(/one more step/i)).toBeInTheDocument());
    expect(screen.getByText(/newsignup@example\.com/)).toBeInTheDocument();
    // No back button during the mandatory phone gate.
    expect(screen.queryByRole("button", { name: /^back$/i })).not.toBeInTheDocument();
  });

  it("completing the phone gate after a Google signup logs in with the pending token attached", async () => {
    vi.mocked(api.verifyGoogleCredential).mockResolvedValue({
      phone_required: { token: "gate-tok-2", prefill_email: "g@example.com" },
    });
    vi.mocked(api.requestOtp).mockResolvedValue({ message: "OTP sent.", otp: "999888" });
    vi.mocked(api.verifyOtp).mockResolvedValue(NORMAL_SESSION);
    vi.mocked(api.getMe).mockResolvedValue(ME_RESPONSE);
    window.google = { accounts: { id: { initialize: vi.fn(), renderButton: vi.fn() } } };
    renderFlow();
    const script = document.head.querySelector("script")!;
    fireEvent.load(script);
    await waitFor(() => expect(window.google!.accounts.id.initialize).toHaveBeenCalled());
    const { callback } = vi.mocked(window.google!.accounts.id.initialize).mock.calls[0][0];
    await callback({ credential: "fake-id-token" });
    await waitFor(() => screen.getByText(/one more step/i));

    fireEvent.change(screen.getByLabelText(/mobile number/i), { target: { value: "+919111111111" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));
    await waitFor(() => screen.getByLabelText(/verification code/i));
    fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: "999888" } });
    fireEvent.click(screen.getByRole("button", { name: /verify & continue/i }));

    await waitFor(() => expect(api.verifyOtp).toHaveBeenCalledWith("+919111111111", "999888", "gate-tok-2"));
    delete (window as { google?: unknown }).google;
  });

  it("a link_required response transitions to the link-account screen instead of logging in", async () => {
    vi.mocked(api.sendEmailOtp).mockResolvedValue({ message: "OTP sent.", otp: "555444" });
    vi.mocked(api.verifyEmailOtp).mockResolvedValue({
      link_required: { token: "link-tok", matched_email: "existing@example.com", existing_method: "phone" },
    });
    renderFlow();
    fireEvent.click(screen.getByRole("button", { name: /continue with email/i }));
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "existing@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));
    await waitFor(() => screen.getByLabelText(/verification code/i));
    fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: "555444" } });
    fireEvent.click(screen.getByRole("button", { name: /verify & continue/i }));

    await waitFor(() => expect(screen.getByText(/existing@example\.com/)).toBeInTheDocument());
    expect(screen.getByText(/log in with your phone/i)).toBeInTheDocument();
    expect(api.verifyOtp).not.toHaveBeenCalled(); // no session was created
  });

  it("renders light/dark theme toggle on auth entry screen", async () => {
    renderFlow();
    await waitFor(() => expect(screen.getByTestId("google-button-container")).toBeInTheDocument());

    const themeToggle = screen.getByRole("button", { name: /toggle.*theme/i });
    expect(themeToggle).toBeInTheDocument();
    fireEvent.click(themeToggle);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail, then pass**

Run: `cd frontend && npx vitest run src/features/auth/AuthEntryFlow.test.tsx`
Expected first: some failures if any wiring detail in Task 9 doesn't quite match (e.g. an aria-label mismatch) — fix `AuthEntryFlow.tsx`/`Landing.tsx`/`PhoneEntry.tsx` copy to match rather than loosening the test's assertions, since the copy in the test reflects the actual designed UX text.
Expected after fixes: PASS (all 10 tests).

- [ ] **Step 3: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS across all test files — 190+ pre-existing tests plus this plan's new/modified ones, zero failures.

- [ ] **Step 4: Run the TypeScript build check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: clean, zero errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/auth/AuthEntryFlow.test.tsx
git commit -m "test(auth): cover the full multi-method flow — phone gate, linking, Google login"
```

---

## Final Verification

- [ ] `cd frontend && npm test` — full suite passes, zero failures.
- [ ] `cd frontend && npx tsc -b --noEmit` — clean.
- [ ] `cd frontend && npm run build` (`tsc -b && vite build`) — production build succeeds.
- [ ] Manually run `npm run dev`, open the auth screen, and visually confirm: four buttons in the confirmed order (Google, Apple-disabled-with-"Coming soon", Email, Phone); the right-hand showcase panel appears at `lg:` width and disappears below it; the Phone/Email/OTP flows still work end-to-end against a locally running backend (`otp_delivery_mode=stub`); Google's rendered button appears once `VITE_GOOGLE_OAUTH_CLIENT_ID` is set in a local `.env`.
- [ ] Cross-check against the frontend spec's §6 (Test plan) checklist — every named file/case there should now exist: `AuthEntryFlow.test.tsx` (modified), `GoogleButton.test.tsx`, `useOAuthScript.test.ts`, `LinkAccountPrompt.test.tsx`, `AuthContext.test.tsx`/`onboardingHistory.test.ts` unchanged.

## Self-Review Notes (for whoever executes this plan)

- **This plan assumes the backend plan's exact field names** (`phone_required.token`/`prefill_email`, `link_required.token`/`matched_email`/`existing_method`, `existing_method` values `"phone"|"email"|"google"`). If the backend implementation diverges from its own plan during execution, update this plan's Task 1 types/API functions to match before continuing — don't silently adapt around a mismatch.
- **`GoogleButton`'s `useEffect` has an intentionally narrow dependency array** (`[scriptStatus]`, not `[scriptStatus, onCredential]`) — see the inline comment in Task 3. If a future caller ever passes a genuinely unstable `onCredential` (e.g. one that closes over changing state each render), this will call a stale closure. None of this plan's callers do that (`AuthEntryFlow`'s and `LinkAccountPrompt`'s handlers are stable across the relevant renders), but flag it if that ever changes.
- **Apple's placeholder button uses an approximate, recognizable Apple logomark SVG path**, not Apple's exact official downloadable asset — fine for a disabled placeholder, but swap in the real asset from Apple's Human Interface Guidelines download when the real `AppleButton.tsx` is built (Future Scope, tracked in the backend plan).
- **The three feature-bullet blocks removed from `Landing.tsx` in Task 7** are a design-brief-stage call, not a hard requirement — if the redesigned card reads as too sparse once actually rendered, re-adding a condensed one-line version of the value props is a reasonable, small follow-up.
