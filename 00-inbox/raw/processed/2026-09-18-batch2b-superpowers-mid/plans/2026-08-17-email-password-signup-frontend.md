# Email Signup: OTP → Password (Frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace the email-OTP entry/verify screens with a single email+password screen offering both "Create account" and "Log in" actions, wire it into the existing phone-gate machinery exactly like Google already does, and add the "check your email to confirm" acknowledgment after a password signup's phone gate completes.

**Architecture:** Extends `AuthEntryFlow.tsx`'s existing `useState<Step>` machine from `Docs/superpowers/plans/2026-08-14-multi-method-auth-frontend-plan.md` (already complete and merged — read that plan and its spec for the step machine, `goToStep` helper, and phone-gate reuse pattern this one assumes without re-deriving). This plan does NOT edit that plan or its ledger — it's new, separate work on the same codebase. `EmailEntry.tsx` is reworked in place (password field replaces the old email-only form, gains two submit actions) rather than replaced by a new component, since it's still "the email entry screen," just collecting one more field. `EmailOtpVerify.tsx` is deleted — password auth is single-shot, no separate code-verification screen needed. `LinkAccountPrompt.tsx`'s email branch also needs rework: it currently re-authenticates an existing email identity via OTP (`sendEmailOtp`/`verifyEmailOtp`), which no longer exists on the backend — this plan makes that branch use password login too, reusing the same reworked `EmailEntry` in a login-only mode.

**Tech Stack:** React 19, Vite, TypeScript, Tailwind, shadcn/ui, Vitest + Testing Library — same as the existing frontend. No new libraries.

**Spec:** `Docs/superpowers/specs/2026-08-17-email-password-signup-design.md`

**Depends on:** `Docs/superpowers/plans/2026-08-17-email-password-signup-backend.md` must be implemented first — every API shape this plan wires against (`POST /auth/signup/email`, `POST /auth/login/email`, the removal of `/auth/otp/*`'s email support) comes from that plan.

## Global Constraints

- **Google and phone+OTP UI are completely unchanged.** Do not modify `GoogleButton.tsx`, `PhoneEntry.tsx`, `OtpVerify.tsx`, or `Landing.tsx`'s button order/labels.
- **No router** — extends the existing local `useState<Step>` machine in `AuthEntryFlow.tsx`, same as every prior auth-frontend plan.
- **Minimum password length: 8 characters**, enforced client-side (matching the backend's own validation) so the error surfaces before a round-trip, not just after a 422.
- **`sendEmailOtp`/`verifyEmailOtp` are deleted, not deprecated** — the backend plan removes their server-side support entirely (Design Spec §1's "delete completely" instruction applies here too).
- **`loginEmail`'s error messages are shown verbatim, no frontend special-casing between wrong-credentials and not-yet-confirmed** — the backend's `detail` string already differs appropriately for each case (401 vs 403), and the existing `errorMessage()` helper pattern (`ApiError.payload` extraction) already surfaces it correctly. Do not add status-code branching in the frontend for this.
- **Test runner:** `cd frontend && npx vitest run <path>` (or `npm test` for the full suite). Match existing test file conventions exactly — `vi.mock("./api")`, Testing Library `render`/`fireEvent`/`waitFor`.
- **CRLF discipline:** this session has repeatedly hit an issue where edits silently convert LF files to CRLF. Before every commit, run `file <every touched path>` and compare against `git show HEAD:<path> | file -` for modified files. Fix with `sed -i 's/\r$//' <path>` if a regression appears.
- **Never `git add -A`/`git add .`.**

---

## Task 1: Types and API client — `signupEmail`, `loginEmail`, remove email-OTP functions

**Files:**
- Modify: `frontend/src/features/auth/types.ts`
- Modify: `frontend/src/features/auth/api.ts`
- Modify: `frontend/src/features/auth/api.test.ts`

**Interfaces:**
- Removes: `sendEmailOtp`, `verifyEmailOtp` (both from `api.ts`; no longer callable, the backend routes they hit no longer accept `email`).
- Produces: `signupEmail(email: string, password: string): Promise<PhoneRequiredResponse>`; `loginEmail(email: string, password: string, pendingToken?: string): Promise<OtpVerifyResponse>` (the `pendingToken` param is what makes `loginEmail` usable as `LinkAccountPrompt`'s email step-up re-auth in Task 3 — without it, that flow could log a user into their existing account but would never attach the pending Google/phone-gate identity that triggered the collision in the first place; the backend plan's `LoginEmailBody`/`login_email` route accept and act on the same field).

- [x] **Step 1: Write the failing tests**

In `frontend/src/features/auth/api.test.ts`, remove the `sendEmailOtp posts email as JSON` and `verifyEmailOtp posts email and otp as JSON` tests (they test functions this task deletes), and add:

```ts
it("signupEmail posts email and password as JSON", async () => {
  const mockFetch = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({ phone_required: { token: "gate-tok", prefill_email: "a@example.com" } }),
      { status: 200 },
    ),
  );
  vi.stubGlobal("fetch", mockFetch);

  const result = await signupEmail("a@example.com", "correcthorse");

  const [url, options] = mockFetch.mock.calls[0];
  expect(url).toContain("/auth/signup/email");
  expect(JSON.parse(options.body as string)).toEqual({ email: "a@example.com", password: "correcthorse" });
  expect("phone_required" in result).toBe(true);
});

it("loginEmail posts email and password as JSON", async () => {
  const mockFetch = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({ session_token: "tok-5", user_id: "u5", onboarding_step: null, onboarding_completed: false }),
      { status: 200 },
    ),
  );
  vi.stubGlobal("fetch", mockFetch);

  const result = await loginEmail("a@example.com", "correcthorse");

  const [url, options] = mockFetch.mock.calls[0];
  expect(url).toContain("/auth/login/email");
  expect(JSON.parse(options.body as string)).toEqual({ email: "a@example.com", password: "correcthorse" });
  expect(result.session_token).toBe("tok-5");
});

it("loginEmail includes pending_token only when provided", async () => {
  const mockFetch = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({ session_token: "tok-6", user_id: "u6", onboarding_step: null, onboarding_completed: false }),
      { status: 200 },
    ),
  );
  vi.stubGlobal("fetch", mockFetch);

  await loginEmail("a@example.com", "correcthorse", "pending-xyz");

  const [, options] = mockFetch.mock.calls[0];
  expect(JSON.parse(options.body as string)).toEqual({
    email: "a@example.com", password: "correcthorse", pending_token: "pending-xyz",
  });
});
```

Update the test file's import line at the top to add `signupEmail, loginEmail` and remove `sendEmailOtp, verifyEmailOtp` from the existing `import { ... } from "./api"` statement.

- [x] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/auth/api.test.ts`
Expected: FAIL — `signupEmail`/`loginEmail` don't exist yet; the two removed-function tests will also fail to compile until Step 1's removal is complete, so do the deletions and additions together before running this.

- [x] **Step 3: Update `types.ts`**

In `frontend/src/features/auth/types.ts`, `PhoneRequiredResponse`/`OtpVerifyResponse` already exist and are reused as-is — no new types needed here. Confirm both are already exported (they are, from the 2026-08-14 frontend plan) before proceeding.

- [x] **Step 4: Update `api.ts`**

In `frontend/src/features/auth/api.ts`, remove the `sendEmailOtp` and `verifyEmailOtp` functions entirely:

```ts
export async function sendEmailOtp(email: string): Promise<OtpRequestResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/otp/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  await throwIfError(response);
  return (await response.json()) as OtpRequestResponse;
}
```

```ts
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
```

Add, in their place:

```ts
export async function signupEmail(email: string, password: string): Promise<PhoneRequiredResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/signup/email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  await throwIfError(response);
  return (await response.json()) as PhoneRequiredResponse;
}

export async function loginEmail(
  email: string,
  password: string,
  pendingToken?: string,
): Promise<OtpVerifyResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/login/email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
      ...(pendingToken ? { pending_token: pendingToken } : {}),
    }),
  });
  await throwIfError(response);
  return (await response.json()) as OtpVerifyResponse;
}
```

Update the `import type { ... } from "./types"` line at the top of the file to add `PhoneRequiredResponse` (already imported as part of `OtpVerifyResult`'s definition elsewhere, but check whether it needs its own explicit import for this file's usage — `PhoneRequiredResponse` is a distinct exported type, not just part of the union alias, so add it explicitly if not already present).

- [x] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/auth/api.test.ts`
Expected: PASS, all tests.

- [x] **Step 6: Run the TypeScript build check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: errors in `EmailEntry.tsx`/`EmailOtpVerify.tsx`/`AuthEntryFlow.tsx`/`LinkAccountPrompt.tsx`/their test files (all still reference `sendEmailOtp`/`verifyEmailOtp`) — expected at this point, fixed in Tasks 2-5. Confirm no errors in files THIS task didn't touch.

- [x] **Step 7: Check for CRLF, then commit**

```bash
file frontend/src/features/auth/types.ts frontend/src/features/auth/api.ts frontend/src/features/auth/api.test.ts
# fix CRLF if needed

git add frontend/src/features/auth/types.ts frontend/src/features/auth/api.ts frontend/src/features/auth/api.test.ts
git commit -m "feat(auth): add signupEmail/loginEmail API functions, remove email-OTP functions"
```

---

## Task 2: `EmailEntry.tsx` — password field, two submit actions; delete `EmailOtpVerify.tsx`

**Files:**
- Modify: `frontend/src/features/auth/EmailEntry.tsx`
- Delete: `frontend/src/features/auth/EmailOtpVerify.tsx`

**Interfaces:**
- Produces: `EmailEntryProps` becomes `{ context?: "primary" | "link"; onSignup?: (email: string, password: string) => void; onLogin: (email: string, password: string) => void; onBack?: () => void; submitting: boolean; error: string | null }` — `onSubmit` is removed (breaking change, rewired in Tasks 3/4). `context="primary"` (default) renders both "Create account" and "Log in" buttons; `context="link"` renders only "Log in" (used by `LinkAccountPrompt`, where the account being re-authenticated always already exists) and makes `onSignup` unused/optional.

This task leaves `AuthEntryFlow.tsx`/`LinkAccountPrompt.tsx`/their test files with more TypeScript errors (they still use the old `onSubmit` prop and reference the deleted `EmailOtpVerify`) — expected, fixed in Tasks 3/4/5.

- [x] **Step 1: Replace `EmailEntry.tsx` in full**

```tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { AlertCircle, ArrowLeft, Loader2, ShieldCheck } from "lucide-react";

interface EmailEntryProps {
  /** "link": step-up re-authentication against an account that already
   * exists — only a login action makes sense, never signup. Defaults to
   * "primary" (the landing-screen entry point, both actions available). */
  context?: "primary" | "link";
  onSignup?: (email: string, password: string) => void;
  onLogin: (email: string, password: string) => void;
  onBack?: () => void;
  submitting: boolean;
  error: string | null;
}

const MIN_PASSWORD_LENGTH = 8;

export function EmailEntry({ context = "primary", onSignup, onLogin, onBack, submitting, error }: EmailEntryProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const isLink = context === "link";
  const passwordTooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH;

  const submit = (event: FormEvent<HTMLFormElement>, action: "signup" | "login") => {
    event.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      setValidationError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    setValidationError(null);
    if (action === "signup") {
      onSignup?.(email, password);
    } else {
      onLogin(email, password);
    }
  };

  const displayedError = validationError ?? error;

  return (
    <form
      onSubmit={(event) => submit(event, isLink ? "login" : "signup")}
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
            {isLink ? "Log in with email" : "Continue with email"}
          </h1>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed max-w-xs mx-auto">
            {isLink
              ? "Enter your email and password to link this to your account."
              : "Enter your email and choose a password to get started, or log in if you already have an account."}
          </p>
        </div>
      </div>

      <div className="space-y-3 text-left">
        <div className="space-y-2">
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
        <div className="space-y-2">
          <label htmlFor="password-input" className="text-xs font-semibold text-[var(--color-ink)] block">
            Password
          </label>
          <input
            id="password-input"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full h-11 sm:h-12 min-h-[44px] rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] focus-within:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent)]/20 px-3.5 text-xs sm:text-sm text-[var(--color-ink)] placeholder:text-[var(--color-text-secondary)]/50 focus:outline-none transition-all"
          />
          {passwordTooShort && (
            <p className="text-[11px] text-[var(--color-text-secondary)]">
              At least {MIN_PASSWORD_LENGTH} characters.
            </p>
          )}
        </div>
      </div>

      {displayedError && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3 rounded-xl bg-[color-mix(in_srgb,var(--color-negative)_10%,transparent)] border border-[color-mix(in_srgb,var(--color-negative)_25%,transparent)] text-xs text-[var(--color-negative)] font-medium text-left"
        >
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{displayedError}</span>
        </div>
      )}

      <div className="space-y-3 pt-1">
        <Button
          type="submit"
          disabled={submitting || !email.trim() || !password.trim()}
          className="w-full h-11 sm:h-12 rounded-xl bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent)]/90 font-semibold text-xs sm:text-sm shadow-xs gap-2 cursor-pointer active:scale-[0.99] transition-all min-h-[44px] sm:min-h-[48px]"
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{isLink ? "Logging in..." : "Creating account..."}</span>
            </>
          ) : (
            <span>{isLink ? "Log in" : "Create account"}</span>
          )}
        </Button>

        {!isLink && (
          <Button
            type="button"
            variant="outline"
            disabled={submitting || !email.trim() || !password.trim()}
            onClick={(event) => submit(event as unknown as FormEvent<HTMLFormElement>, "login")}
            className="w-full h-11 sm:h-12 rounded-xl border border-[var(--color-border)] bg-transparent text-[var(--color-ink)] hover:bg-[var(--color-bg)] font-semibold text-xs sm:text-sm cursor-pointer active:scale-[0.99] transition-all min-h-[44px] sm:min-h-[48px]"
          >
            Log in instead
          </Button>
        )}

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

The secondary "Log in instead" button uses `type="button"` with its own `onClick` (rather than a second `<button type="submit">`, since a form can only have one implicit submit action per Enter-key press) — clicking it calls `submit(...)` directly with `action="login"`, reusing the same validation path. The primary form `onSubmit` (triggered by Enter or the main button) defaults to `"signup"` unless `context="link"`, in which case it's always `"login"`.

- [x] **Step 2: Delete `EmailOtpVerify.tsx`**

```bash
rm frontend/src/features/auth/EmailOtpVerify.tsx
```

- [x] **Step 3: Run the TypeScript build check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: errors in `AuthEntryFlow.tsx`/`LinkAccountPrompt.tsx`/their test files (still import `EmailOtpVerify` and use the old `EmailEntry` `onSubmit` prop) — expected, fixed in Tasks 3/4/5. Confirm `EmailEntry.tsx` itself introduces no NEW errors in isolation.

- [x] **Step 4: Check for CRLF, then commit**

```bash
file frontend/src/features/auth/EmailEntry.tsx
# fix CRLF if needed

git add frontend/src/features/auth/EmailEntry.tsx
git rm frontend/src/features/auth/EmailOtpVerify.tsx
git commit -m "feat(auth): rework EmailEntry for password auth, delete EmailOtpVerify"
```

---

## Task 3: `LinkAccountPrompt.tsx` — email step-up re-auth switches from OTP to password

**Files:**
- Modify: `frontend/src/features/auth/LinkAccountPrompt.tsx`

**Interfaces:**
- Consumes: `EmailEntry` with `context="link"` (Task 2), `loginEmail` with its `pendingToken` param (Task 1) — this component's own `pendingToken` prop (already present, unchanged) now gets threaded into `loginEmail`'s third argument, matching how the phone/Google branches already thread it into `verifyOtp`/`verifyGoogleCredential`.
- Produces: no prop-shape change to `LinkAccountPromptProps` itself — `existingMethod === "email"` now resolves via password login internally instead of OTP request/verify.

The `step` state (`"entry" | "otp"`) stays — phone's re-auth still needs it — but the email branch no longer transitions to `"otp"` at all; a password login is single-shot.

- [x] **Step 1: Replace `LinkAccountPrompt.tsx` in full**

```tsx
import { useState } from "react";
import { ArrowLeft } from "lucide-react";
import { PhoneEntry } from "./PhoneEntry";
import { OtpVerify } from "./OtpVerify";
import { EmailEntry } from "./EmailEntry";
import { GoogleButton } from "./GoogleButton";
import { requestOtp, loginEmail, verifyGoogleCredential, verifyOtp } from "./api";
import { isLinkRequired, isPhoneRequired } from "./types";
import type { ExistingMethod, OtpVerifyResponse } from "./types";
import { ApiError } from "../../lib/apiClient";

interface LinkAccountPromptProps {
  matchedEmail: string;
  existingMethod: ExistingMethod;
  pendingToken: string;
  onLinked: (result: OtpVerifyResponse) => void;
  onCancel: () => void;
}

type Step = "entry" | "otp";

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.payload === "string") return err.payload;
  return fallback;
}

export function LinkAccountPrompt({ matchedEmail, existingMethod, pendingToken, onLinked, onCancel }: LinkAccountPromptProps) {
  const [step, setStep] = useState<Step>("entry");
  const [identifier, setIdentifier] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devOtp, setDevOtp] = useState<string | null>(null);

  const goToStep = (next: Step) => {
    setError(null);
    setDevOtp(null);
    setStep(next);
  };

  const handlePhoneEntrySubmit = async (phoneNumber: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await requestOtp(phoneNumber);
      setIdentifier(phoneNumber);
      setDevOtp(result.otp);
      setStep("otp");
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
      const result = await verifyOtp(identifier, otp, pendingToken);
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

  const handleEmailLogin = async (email: string, password: string) => {
    setSubmitting(true);
    setError(null);
    try {
      // loginEmail never returns link_required/phone_required (those are
      // signup-only outcomes) — a successful call always means a session.
      // pendingToken is threaded through here (unlike AuthEntryFlow's own
      // primary email login in Task 4, which never passes one) — this is
      // the one place email's step-up path differs from a normal login: it
      // tells the backend to also attach this pending Google/phone-gate
      // identity to whichever account the password just authenticated into.
      const result = await loginEmail(email, password, pendingToken);
      onLinked(result);
    } catch (err) {
      setError(errorMessage(err, "That didn't work. Try again."));
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

  const cancelButton = (
    <div className="flex justify-center">
      <button
        type="button"
        onClick={onCancel}
        className="inline-flex items-center gap-1 text-[var(--color-text-secondary)] hover:text-[var(--color-ink)] font-medium transition-colors cursor-pointer text-xs"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        <span>Back</span>
      </button>
    </div>
  );

  if (existingMethod === "google") {
    return (
      <div className="w-full max-w-sm sm:max-w-md mx-auto space-y-3">
        {cancelButton}
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

  if (existingMethod === "email") {
    // Single-shot password login — no "entry then otp" transition needed,
    // unlike phone below.
    return (
      <div className="space-y-3">
        {cancelButton}
        {banner}
        <EmailEntry context="link" onLogin={handleEmailLogin} submitting={submitting} error={error} />
      </div>
    );
  }

  if (step === "entry") {
    return (
      <div className="space-y-3">
        {cancelButton}
        {banner}
        <PhoneEntry onSubmit={handlePhoneEntrySubmit} submitting={submitting} error={error} />
      </div>
    );
  }

  return (
    <OtpVerify
      phoneNumber={identifier}
      onSubmit={handlePhoneOtpSubmit}
      onResend={() => goToStep("entry")}
      onBack={() => goToStep("entry")}
      submitting={submitting}
      error={error}
      devOtp={devOtp}
    />
  );
}
```

- [x] **Step 2: Run the TypeScript build check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: errors remain only in `AuthEntryFlow.tsx` and test files (still reference the old `EmailEntry`/`EmailOtpVerify` shapes) — expected, fixed in Tasks 4/5. Confirm `LinkAccountPrompt.tsx` itself compiles clean against `EmailEntry`'s new props.

- [x] **Step 3: Check for CRLF, then commit**

```bash
file frontend/src/features/auth/LinkAccountPrompt.tsx
# fix CRLF if needed

git add frontend/src/features/auth/LinkAccountPrompt.tsx
git commit -m "feat(auth): switch LinkAccountPrompt's email step-up re-auth to password login"
```

---

## Task 4: `AuthEntryFlow.tsx` — wire signup/login handlers, confirm-email acknowledgment

**Files:**
- Modify: `frontend/src/features/auth/AuthEntryFlow.tsx`

**Interfaces:**
- Consumes: `signupEmail`/`loginEmail` (Task 1), reworked `EmailEntry` (Task 2).
- Produces: `Step` union drops `"email_otp"` (no longer needed — one email screen replaces the old two-step flow); new local state `confirmationPendingEmail: string | null` for the post-gate acknowledgment.

- [x] **Step 1: Replace `AuthEntryFlow.tsx` in full**

```tsx
import { useState } from "react";
import { Landing } from "./Landing";
import { PhoneEntry } from "./PhoneEntry";
import { OtpVerify } from "./OtpVerify";
import { EmailEntry } from "./EmailEntry";
import { LinkAccountPrompt } from "./LinkAccountPrompt";
import { AuthShowcasePanel } from "./AuthShowcasePanel";
import { requestOtp, signupEmail, loginEmail, verifyGoogleCredential, verifyOtp } from "./api";
import { isLinkRequired, isPhoneRequired } from "./types";
import type { ExistingMethod } from "./types";
import { useAuth } from "./AuthContext";
import { ThemeToggle } from "../../components/ThemeToggle";
import { ApiError } from "../../lib/apiClient";

type Step = "landing" | "phone" | "otp" | "email" | "link_account";

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
  // steps — no extra Step value needed.
  const [phoneGateToken, setPhoneGateToken] = useState<string | null>(null);
  const [phoneGatePrefillEmail, setPhoneGatePrefillEmail] = useState<string | null>(null);

  // Account-linking state (Design Spec §4): set when a verification
  // returns link_required.
  const [linkInfo, setLinkInfo] = useState<LinkInfo | null>(null);

  // Set the moment an email+password SIGNUP (not login) enters the phone
  // gate; consumed once the gate completes, to show the "check your email"
  // acknowledgment (2026-08-17 email-password design spec §4c). Cleared on
  // every other path so a Google/phone signup never shows it by accident.
  const [confirmationPendingEmail, setConfirmationPendingEmail] = useState<string | null>(null);

  const goToStep = (next: Step) => {
    setError(null);
    setDevOtp(null);
    setStep(next);
  };

  const handleSelectPhone = () => {
    setPhoneGateToken(null);
    setPhoneGatePrefillEmail(null);
    goToStep("phone");
  };

  const handleSelectEmail = () => {
    setPhoneGateToken(null);
    setPhoneGatePrefillEmail(null);
    goToStep("email");
  };

  const handlePhoneSubmit = async (phone: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await requestOtp(phone);
      setIdentifier(phone);
      goToStep("otp");
      setDevOtp(result.otp);
    } catch (err) {
      setError(errorMessage(err, "Couldn't send the code. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const handleEmailSignup = async (email: string, password: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await signupEmail(email, password);
      // signupEmail always resolves to phone_required (Design Spec §4/§4a)
      // — there's no login/link_required branch to guard against here,
      // unlike Google/the old email-OTP path.
      setPhoneGateToken(result.phone_required.token);
      setPhoneGatePrefillEmail(result.phone_required.prefill_email);
      setConfirmationPendingEmail(email);
      goToStep("phone");
    } catch (err) {
      setError(errorMessage(err, "Couldn't create your account. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const handleEmailLogin = async (email: string, password: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await loginEmail(email, password);
      await login(result.session_token);
    } catch (err) {
      // Covers both "wrong email or password" (401) and "please confirm
      // your email" (403) — the backend's own message already
      // distinguishes them correctly, no frontend branching needed
      // (Global Constraints).
      setError(errorMessage(err, "That didn't work. Try again."));
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
      // Only reachable when the just-completed gate followed an email+
      // password signup — Google/plain-phone signups never set this.
      // Cleared immediately after being consumed by the render below.
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
        setConfirmationPendingEmail(null);
        goToStep("phone");
        return;
      }
      if (isLinkRequired(result)) {
        setLinkInfo({
          token: result.link_required.token,
          matchedEmail: result.link_required.matched_email,
          existingMethod: result.link_required.existing_method,
        });
        goToStep("link_account");
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
          {confirmationPendingEmail && (
            <div
              role="status"
              className="mb-3 flex items-center gap-2 p-3 rounded-xl bg-[color-mix(in_srgb,var(--color-accent)_10%,transparent)] border border-[color-mix(in_srgb,var(--color-accent)_20%,transparent)] text-xs text-[var(--color-ink)] text-left"
            >
              <span>
                We've sent a confirmation link to <strong>{confirmationPendingEmail}</strong> — click it to enable
                password sign-in. You're already signed in via your phone.
              </span>
            </div>
          )}
          {step === "landing" && (
            <Landing
              onSelectPhone={handleSelectPhone}
              onSelectEmail={handleSelectEmail}
              onGoogleCredential={handleGoogleCredential}
              error={error}
              submitting={submitting}
            />
          )}
          {step === "phone" && (
            <PhoneEntry
              context={phoneGateToken ? "phoneGate" : "primary"}
              phoneGatePrefillEmail={phoneGatePrefillEmail}
              onSubmit={handlePhoneSubmit}
              onBack={phoneGateToken ? undefined : () => goToStep("landing")}
              submitting={submitting}
              error={error}
            />
          )}
          {step === "otp" && (
            <OtpVerify
              phoneNumber={identifier}
              onSubmit={handlePhoneOtpSubmit}
              onResend={() => goToStep("phone")}
              onBack={() => goToStep("phone")}
              submitting={submitting}
              error={error}
              devOtp={devOtp}
            />
          )}
          {step === "email" && (
            <EmailEntry
              onSignup={handleEmailSignup}
              onLogin={handleEmailLogin}
              onBack={() => goToStep("landing")}
              submitting={submitting}
              error={error}
            />
          )}
          {step === "link_account" && linkInfo && (
            <LinkAccountPrompt
              matchedEmail={linkInfo.matchedEmail}
              existingMethod={linkInfo.existingMethod}
              pendingToken={linkInfo.token}
              onLinked={async (result) => {
                try {
                  await login(result.session_token);
                } catch (err) {
                  const message = errorMessage(err, "Something went wrong finishing sign-in. Try again.");
                  setLinkInfo(null);
                  goToStep("landing");
                  setError(message);
                }
              }}
              onCancel={() => {
                setLinkInfo(null);
                goToStep("landing");
              }}
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

Note what changed from the pre-existing file beyond the email handlers: `confirmationPendingEmail` is set only by `handleEmailSignup` and explicitly cleared to `null` by `handleGoogleCredential`'s `phone_required` branch (so a Google signup never shows the email-confirmation banner) — it is deliberately NOT cleared by `goToStep`, since it needs to survive the `"phone"` → `"otp"` transition and still be visible once `login()` succeeds and the whole `AuthEntryFlow` unmounts in favor of the authenticated app shell (at which point the banner's own component tree is gone anyway, so no explicit "clear after showing" cleanup is needed — the acknowledgment's lifetime is naturally bounded by how long `AuthEntryFlow` stays mounted, which ends exactly when `login()` succeeds and `AuthContext`'s `token`/`me` state flips the app over to the authenticated shell).

- [x] **Step 2: Run the TypeScript build check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: errors remain only in `AuthEntryFlow.test.tsx` (still uses old email-OTP mocks/assertions) — fixed in Task 5. Zero errors in any `.tsx`/`.ts` source file.

- [x] **Step 3: Check for CRLF, then commit**

```bash
file frontend/src/features/auth/AuthEntryFlow.tsx
# fix CRLF if needed

git add frontend/src/features/auth/AuthEntryFlow.tsx
git commit -m "feat(auth): wire email signup/login into AuthEntryFlow, add confirm-email acknowledgment"
```

---

## Task 5: Rewrite `AuthEntryFlow.test.tsx` and `LinkAccountPrompt.test.tsx`

**Files:**
- Modify: `frontend/src/features/auth/AuthEntryFlow.test.tsx`
- Modify: `frontend/src/features/auth/LinkAccountPrompt.test.tsx`

**Interfaces:**
- Consumes: everything from Tasks 1-4.

- [x] **Step 1: Replace `AuthEntryFlow.test.tsx` in full**

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthEntryFlow } from "./AuthEntryFlow";
import { AuthProvider } from "./AuthContext";
import * as api from "./api";
import { ApiError } from "../../lib/apiClient";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    requestOtp: vi.fn(),
    signupEmail: vi.fn(),
    loginEmail: vi.fn(),
    verifyOtp: vi.fn(),
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

function fillEmailPassword(email: string, password: string) {
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: email } });
  fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: password } });
}

describe("AuthEntryFlow", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_GOOGLE_OAUTH_CLIENT_ID", "test-client-id.apps.googleusercontent.com");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
    delete (window as { google?: unknown }).google;
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
    await waitFor(() => expect(api.getMe).toHaveBeenCalled());
  });

  it("moves to the email screen and signs up, transitioning to the mandatory phone gate", async () => {
    vi.mocked(api.signupEmail).mockResolvedValue({
      phone_required: { token: "gate-tok", prefill_email: "newsignup@example.com" },
    });
    renderFlow();
    fireEvent.click(screen.getByRole("button", { name: /continue with email/i }));
    fillEmailPassword("newsignup@example.com", "correcthorse");
    fireEvent.click(screen.getByRole("button", { name: /^create account$/i }));

    await waitFor(() => expect(api.signupEmail).toHaveBeenCalledWith("newsignup@example.com", "correcthorse"));
    await waitFor(() => expect(screen.getByText(/one more step/i)).toBeInTheDocument());
    expect(screen.getByText(/newsignup@example\.com/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^back$/i })).not.toBeInTheDocument();
  });

  it("shows the confirm-your-email acknowledgment once the phone gate completes after an email signup", async () => {
    vi.mocked(api.signupEmail).mockResolvedValue({
      phone_required: { token: "gate-tok", prefill_email: "confirmme@example.com" },
    });
    vi.mocked(api.requestOtp).mockResolvedValue({ message: "OTP sent.", otp: "111222" });
    vi.mocked(api.verifyOtp).mockResolvedValue(NORMAL_SESSION);
    vi.mocked(api.getMe).mockResolvedValue(ME_RESPONSE);
    renderFlow();
    fireEvent.click(screen.getByRole("button", { name: /continue with email/i }));
    fillEmailPassword("confirmme@example.com", "correcthorse");
    fireEvent.click(screen.getByRole("button", { name: /^create account$/i }));
    await waitFor(() => screen.getByText(/one more step/i));

    fireEvent.change(screen.getByLabelText(/mobile number/i), { target: { value: "+919111111112" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));
    await waitFor(() => screen.getByLabelText(/verification code/i));
    fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: "111222" } });
    fireEvent.click(screen.getByRole("button", { name: /verify & continue/i }));

    await waitFor(() => expect(api.getMe).toHaveBeenCalled());
    expect(screen.getByRole("status")).toHaveTextContent(/confirmation link/i);
    expect(screen.getByRole("status")).toHaveTextContent(/confirmme@example\.com/);
  });

  it("does not show the confirm-your-email acknowledgment for a Google signup's phone gate", async () => {
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

    await waitFor(() => expect(api.getMe).toHaveBeenCalled());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows an inline error when email signup fails", async () => {
    vi.mocked(api.signupEmail).mockRejectedValue(
      new ApiError(409, "An account with this email already exists — log in instead."),
    );
    renderFlow();
    fireEvent.click(screen.getByRole("button", { name: /continue with email/i }));
    fillEmailPassword("dup@example.com", "correcthorse");
    fireEvent.click(screen.getByRole("button", { name: /^create account$/i }));

    await waitFor(() => expect(screen.getByText(/already exists/i)).toBeInTheDocument());
  });

  it("logs in directly on successful email login, no phone gate", async () => {
    vi.mocked(api.loginEmail).mockResolvedValue(NORMAL_SESSION);
    vi.mocked(api.getMe).mockResolvedValue(ME_RESPONSE);
    renderFlow();
    fireEvent.click(screen.getByRole("button", { name: /continue with email/i }));
    fillEmailPassword("existing@example.com", "correcthorse");
    fireEvent.click(screen.getByRole("button", { name: /^log in instead$/i }));

    await waitFor(() => expect(api.loginEmail).toHaveBeenCalledWith("existing@example.com", "correcthorse"));
    await waitFor(() => expect(api.getMe).toHaveBeenCalled());
  });

  it("shows the backend's own message on a failed email login, whether wrong credentials or unconfirmed", async () => {
    vi.mocked(api.loginEmail).mockRejectedValue(
      new ApiError(403, "Please confirm your email before signing in with a password — check your inbox, or resend the link."),
    );
    renderFlow();
    fireEvent.click(screen.getByRole("button", { name: /continue with email/i }));
    fillEmailPassword("unconfirmed@example.com", "correcthorse");
    fireEvent.click(screen.getByRole("button", { name: /^log in instead$/i }));

    await waitFor(() => expect(screen.getByText(/please confirm your email/i)).toBeInTheDocument());
  });

  it("a link_required response from Google transitions to the link-account screen instead of logging in", async () => {
    vi.mocked(api.verifyGoogleCredential).mockResolvedValue({
      link_required: { token: "link-tok", matched_email: "existing@example.com", existing_method: "email" },
    });
    window.google = { accounts: { id: { initialize: vi.fn(), renderButton: vi.fn() } } };
    renderFlow();
    const script = document.head.querySelector("script")!;
    fireEvent.load(script);
    await waitFor(() => expect(window.google!.accounts.id.initialize).toHaveBeenCalled());
    const { callback } = vi.mocked(window.google!.accounts.id.initialize).mock.calls[0][0];
    await callback({ credential: "fake-id-token" });

    await waitFor(() => expect(screen.getByText(/existing@example\.com/)).toBeInTheDocument());
    expect(screen.getByText(/log in with your email/i)).toBeInTheDocument();
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

- [x] **Step 2: Replace `LinkAccountPrompt.test.tsx` in full**

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LinkAccountPrompt } from "./LinkAccountPrompt";
import * as api from "./api";
import { ApiError } from "../../lib/apiClient";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, requestOtp: vi.fn(), verifyOtp: vi.fn(), loginEmail: vi.fn() };
});

describe("LinkAccountPrompt", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_GOOGLE_OAUTH_CLIENT_ID", "test-client-id.apps.googleusercontent.com");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  it("shows the matched-account banner naming the existing method", () => {
    render(
      <LinkAccountPrompt
        matchedEmail="a@example.com"
        existingMethod="phone"
        pendingToken="pending-tok"
        onLinked={vi.fn()}
        onCancel={vi.fn()}
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
      <LinkAccountPrompt matchedEmail="a@example.com" existingMethod="phone" pendingToken="pending-tok" onLinked={onLinked} onCancel={vi.fn()} />,
    );

    fireEvent.change(screen.getByLabelText(/mobile number/i), { target: { value: "+919999999999" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));
    await waitFor(() => screen.getByLabelText(/verification code/i));

    fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: /verify & continue/i }));

    await waitFor(() => expect(api.verifyOtp).toHaveBeenCalledWith("+919999999999", "654321", "pending-tok"));
    await waitFor(() => expect(onLinked).toHaveBeenCalledWith(expect.objectContaining({ session_token: "tok-linked" })));
  });

  it("completes an email-based link via password login and calls onLinked with the session", async () => {
    vi.mocked(api.loginEmail).mockResolvedValue({
      session_token: "tok-linked-2", user_id: "u2", onboarding_step: null, onboarding_completed: false,
    });
    const onLinked = vi.fn();
    render(
      <LinkAccountPrompt matchedEmail="a@example.com" existingMethod="email" pendingToken="pending-tok-2" onLinked={onLinked} onCancel={vi.fn()} />,
    );

    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "a@example.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "correcthorse" } });
    fireEvent.click(screen.getByRole("button", { name: /^log in$/i }));

    await waitFor(() => expect(api.loginEmail).toHaveBeenCalledWith("a@example.com", "correcthorse", "pending-tok-2"));
    await waitFor(() => expect(onLinked).toHaveBeenCalledWith(expect.objectContaining({ session_token: "tok-linked-2" })));
  });

  it("shows an error when the email password login fails", async () => {
    vi.mocked(api.loginEmail).mockRejectedValue(new ApiError(401, "Invalid email or password."));
    render(
      <LinkAccountPrompt matchedEmail="a@example.com" existingMethod="email" pendingToken="pending-tok-2b" onLinked={vi.fn()} onCancel={vi.fn()} />,
    );

    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "a@example.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "wrongpassword" } });
    fireEvent.click(screen.getByRole("button", { name: /^log in$/i }));

    await waitFor(() => expect(screen.getByText(/invalid email or password/i)).toBeInTheDocument());
  });

  it("renders a GoogleButton when the existing method is google", () => {
    render(
      <LinkAccountPrompt matchedEmail="a@example.com" existingMethod="google" pendingToken="pending-tok-3" onLinked={vi.fn()} onCancel={vi.fn()} />,
    );

    expect(screen.getByTestId("google-button-container")).toBeInTheDocument();
  });

  it("clears a stale error when navigating back from a failed phone OTP attempt", async () => {
    vi.mocked(api.requestOtp).mockResolvedValue({ message: "OTP sent.", otp: "654321" });
    vi.mocked(api.verifyOtp).mockRejectedValue(new ApiError(401, "Invalid or expired OTP."));
    render(
      <LinkAccountPrompt
        matchedEmail="a@example.com"
        existingMethod="phone"
        pendingToken="pending-tok"
        onLinked={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText(/mobile number/i), { target: { value: "+919999999999" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));
    await waitFor(() => screen.getByLabelText(/verification code/i));
    fireEvent.change(screen.getByLabelText(/verification code/i), { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: /verify & continue/i }));
    await waitFor(() => expect(screen.getByText(/invalid or expired otp/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /change number/i }));

    expect(screen.queryByText(/invalid or expired otp/i)).not.toBeInTheDocument();
  });

  it("offers a back control that cancels the link instead of dead-ending", () => {
    const onCancel = vi.fn();
    render(
      <LinkAccountPrompt
        matchedEmail="a@example.com"
        existingMethod="phone"
        pendingToken="pending-tok"
        onLinked={vi.fn()}
        onCancel={onCancel}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^back$/i }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
```

- [x] **Step 3: Run both test files to verify they pass**

Run: `cd frontend && npx vitest run src/features/auth/AuthEntryFlow.test.tsx src/features/auth/LinkAccountPrompt.test.tsx`
Expected: PASS, all tests. If any button-name queries don't match (e.g. `/^create account$/i` vs. the actual rendered text), fix `AuthEntryFlow.tsx`/`EmailEntry.tsx`/`LinkAccountPrompt.tsx`'s copy to match what these tests assert, rather than loosening the assertions — the copy in the tests reflects the intended UX text (same principle the 2026-08-14 frontend plan's own Final Verification step used).

- [x] **Step 4: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS across all test files, zero failures. If a `vitest-pool` fork-worker startup timeout appears with zero test output (a known environment flake, not a code issue — see `decisions.md`'s 2026-08-17 entry on the `@rolldown` native-binding fix), retry the exact same command once before investigating further.

- [x] **Step 5: Run the TypeScript build check**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: clean, zero errors.

- [x] **Step 6: Run the production build**

Run: `cd frontend && npm run build`
Expected: succeeds.

- [x] **Step 7: Check for CRLF, then commit**

```bash
file frontend/src/features/auth/AuthEntryFlow.test.tsx frontend/src/features/auth/LinkAccountPrompt.test.tsx
# fix CRLF if needed

git add frontend/src/features/auth/AuthEntryFlow.test.tsx frontend/src/features/auth/LinkAccountPrompt.test.tsx
git commit -m "test(auth): cover email signup/login, confirm-email banner, and LinkAccountPrompt's password re-auth"
```

---

## Final Verification

- [x] `cd frontend && npm test` — full suite passes, zero failures.
- [x] `cd frontend && npx tsc -b --noEmit` — clean.
- [x] `cd frontend && npm run build` — production build succeeds.
- [x] Manually run `npm run dev` against a backend with the companion backend plan already implemented, and confirm: the "Continue with Email" screen shows both "Create account" and "Log in instead" actions; a signup transitions into the existing phone-gate UI unchanged; the phone gate's completion shows the confirm-your-email banner for an email signup and does NOT show it for a Google/phone signup; a login with a wrong password shows a generic error, and a login with a correct-but-unconfirmed password shows the distinct "please confirm your email" message; the `LinkAccountPrompt` screen's email branch shows password fields, not an OTP code input.
- [x] Cross-check this plan's coverage against the three items the user explicitly asked for: password field replacing OTP-code input on the email signup screen (Task 2), password field on email login (Tasks 2/4, plus the `LinkAccountPrompt` case in Task 3 — flagged as a necessary consequence beyond the literal 3-item list, not scope creep, since `LinkAccountPrompt`'s email branch would otherwise call deleted API functions), and the "check your email to confirm" UI note (Task 4).
