# Login/Signup URL Routes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the landing website direct URL entry points — `/login` and `/signup` — into the existing single-screen auth flow, without changing its behavior in any other way.

**Architecture:** No router library exists in this frontend (`frontend/package.json` has no `react-router` or equivalent) and none should be introduced for two static paths. The app already has a working precedent for pathname-based branching without a router: `main.tsx` checks `window.location.pathname.startsWith("/print/analytics")` to swap the mounted tree, and `App.tsx` checks `/mobile` (path or hash) for `isMobileRoute`. This plan adds a third, identical check: read `window.location.pathname` once in `MainApp` to seed `authInitialMode`, then let the existing `AuthEntryFlow`/`Landing` internal toggle (`onModeChange`) work exactly as it does today — it never touches the URL, and this plan does not change that.

**Tech Stack:** React 18 + TypeScript, Vite, Vitest + @testing-library/react (existing stack, no new dependencies).

**Spec:** This plan implements the approach agreed in-conversation on 2026-09-15 (no separate spec doc exists — the investigation and approach were scoped directly with the user; see `session.md` / conversation history for the original ask). No PRD/ADR conflict was found: `AGENTS.md` and `/Docs` do not mandate a routing library, and CloudFront hosting (`infra/modules/frontend/main.tf`) already SPA-serves arbitrary paths, so no infra changes are in scope here.

## Global Constraints

- No new dependency may be added (no `react-router-dom`) — two static paths do not justify a router; matches the codebase's existing pathname-check pattern.
- Root `/` must retain its exact current default behavior (`authInitialMode` defaults to `"signup"`, mobile/desktop branching unchanged).
- The existing internal Login ↔ Sign Up toggle (`Landing.tsx` `onModeChange`) must not change its behavior, labels, or animation.
- No change to `infra/modules/frontend/main.tf` — CloudFront's existing 403/404 → `/index.html` @ 200 `custom_error_response` blocks already cover `/login` and `/signup` for direct nav and refresh.
- This branch (`feat/enhanced-ui`) is for review/documentation only in this pass — do not implement code changes until the user confirms and a fresh branch (`feat/auth-login-signup-routes`, cut from `main`) is created for the actual work.

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/src/App.tsx` | `MainApp` reads `window.location.pathname` once (mirroring the existing `isMobileRoute` check at line ~64) and seeds `authInitialMode` from it before falling back to today's default. |
| `frontend/src/App.test.tsx` | New test cases asserting `/login` and `/signup` seed the correct screen, `/` is unchanged, and an unrelated path falls back to the default. |
| `frontend/src/features/auth/AuthEntryFlow.tsx` | No change — `initialMode` prop already threads through correctly; included here only as the interface boundary the new code seeds. |
| `frontend/src/features/auth/Landing.tsx` | No change in this plan. Optional URL-sync-on-toggle is explicitly out of scope (see "Deferred" below) to keep this a minimal, reviewable change. |

No other files change. `infra/modules/frontend/main.tf` is verified sufficient, not modified.

---

### Task 1: Seed auth mode from `/login` and `/signup` pathnames

**Files:**
- Modify: `frontend/src/App.tsx:59-70` (inside `MainApp`, alongside the existing `isMobileRoute` computation)
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `AuthEntryFlow`'s existing `initialMode?: "login" | "signup"` prop (`frontend/src/features/auth/AuthEntryFlow.tsx:36`) — unchanged signature.
- Produces: nothing new consumed elsewhere — this task only changes how `authInitialMode`'s initial value is computed inside `MainApp`.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/App.test.tsx` (inside the existing `describe("App", ...)` block, using the same `getMe`-mock pattern already in the file):

```tsx
  it("seeds login mode when loaded at /login", async () => {
    const originalPathname = window.location.pathname;
    window.history.pushState({}, "", "/login");

    try {
      render(<App />);

      await waitFor(() => expect(screen.getByText("Welcome back")).toBeInTheDocument());
    } finally {
      window.history.pushState({}, "", originalPathname);
    }
  });

  it("seeds signup mode when loaded at /signup", async () => {
    const originalPathname = window.location.pathname;
    window.history.pushState({}, "", "/signup");

    try {
      render(<App />);

      await waitFor(() => expect(screen.getByText("Create your account")).toBeInTheDocument());
    } finally {
      window.history.pushState({}, "", originalPathname);
    }
  });

  it("keeps the default signup mode at /", async () => {
    render(<App />);

    await waitFor(() => expect(screen.getByText("Create your account")).toBeInTheDocument());
  });
```

- [ ] **Step 2: Run tests to verify the first two fail**

Run: `cd frontend && npx vitest run src/App.test.tsx`
Expected: the `/login` and `/signup` cases FAIL (both currently render `"Create your account"` regardless of path, since `authInitialMode` always defaults to `"signup"`); the `/` case already PASSES.

- [ ] **Step 3: Seed `authInitialMode` from the pathname**

In `frontend/src/App.tsx`, replace the `useState` initializer for `authInitialMode` (currently `useState<"login" | "signup">("signup")`, `App.tsx:62`) with a lazy initializer that checks the pathname the same way `isMobileRoute` already does two lines below it:

```tsx
  const [authInitialMode, setAuthInitialMode] = useState<"login" | "signup">(() => {
    if (typeof window === "undefined") return "signup";
    if (window.location.pathname === "/login") return "login";
    if (window.location.pathname === "/signup") return "signup";
    return "signup";
  });
```

This keeps the exact same default (`"signup"`) for `/` and any other path, and only branches for the two new exact-match paths. `isMobileRoute`'s own `/mobile` prefix check is untouched and evaluated independently, so `/mobile` continues to work exactly as before — this change only affects the *initial* value of `authInitialMode`, not the mobile/desktop branch itself.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/App.test.tsx`
Expected: PASS — all three new cases, plus every pre-existing case in the file (regression check for `/mobile`, `/print/analytics` is out of scope of this file but should be spot-checked manually per the testing checklist below).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat(auth): seed login/signup mode from /login and /signup pathnames"
```

---

## Deferred (explicitly out of scope for this plan)

- **URL sync on internal toggle:** flipping the browser URL when the user clicks the in-flow "Log in" / "Sign up" toggle (`Landing.tsx`), via `history.replaceState`. Not needed for the stated requirement (landing site deep links + refresh survival); adds surface area without a driving need. Revisit only if the user asks for bookmarkability of the toggled-to state.
- **Clearing the path after login:** resetting to `/` via `history.replaceState` once `me` becomes truthy, so a post-login refresh doesn't re-evaluate `/login`/`/signup`. Not needed functionally — once `me` is set, `MainApp` renders `OnboardingFlow`/`DashboardPlaceholder` regardless of `authInitialMode`, which is only read on mount and never re-derives from a still-stale pathname. Worth a testing-checklist spot check, but no code change is implicated.
- **Backend route collision check:** confirm no backend API path is namespaced at `/login` or `/signup` on the same origin before implementing. None found in this investigation, but re-grep at implementation time since backend code may have changed.

---

## Testing Checklist (manual, post-implementation)

**Local:**
- [ ] `/` → unchanged default (signup) behavior
- [ ] `/login` direct load → Login screen
- [ ] `/signup` direct load → Sign Up screen
- [ ] Hard refresh on both → same screen persists, no 404/blank
- [ ] Internal toggle from each entry URL → switches exactly as today (labels: "Already have an account? Log in" / "Don't have an account? Sign up")
- [ ] Full login and full signup flow end-to-end from each entry URL (through OTP/phone gate/onboarding)
- [ ] `/mobile` and `/print/analytics` regression check (existing pathname-branch patterns unaffected)

**Staging (post-deploy):**
- [ ] Direct browser nav to `staging.unifolio.in/login` and `/signup`
- [ ] Hard refresh on both
- [ ] `/` unchanged
- [ ] Marketing-site links to `app.unifolio.in/login` and `/signup` land correctly once wired

---

## Branching

This plan is documented on `feat/enhanced-ui` for review only. Implementation should happen on a fresh branch cut from `main`:

```
feat/auth-login-signup-routes
```

Do not implement Task 1 on `feat/enhanced-ui` or any staging/production branch.
