# Multi-Method Auth — Frontend Design

## Purpose

`2026-08-14-multi-method-auth-design.md` (the backend spec) covers the
identity model, Google Sign-In verification, email+OTP, the account-linking
collision policy, the session model, security, and the setup/credentials
checklist for v1's three auth methods — **phone, email, and Google** (Apple
is explicitly Future Scope there, not touched by this doc either). This is
the frontend that calls those endpoints, split into its own file the same
way `2026-08-06-phase-2b-onboarding-frontend-design.md` was split from its
Phase 2 backend spec — this repo's existing precedent for backend/frontend
design docs, not a new pattern.

Read the backend spec first if you haven't — this doc assumes its API
shapes (`OtpVerifyResult`'s `link_required` and `phone_required` variants,
`POST /auth/oauth/google`, the widened `/auth/otp/request`/`/auth/otp/verify`
accepting `email` as an alternative to `phone_number`) without re-deriving
them. In particular, the backend now requires **every account to end up
with a verified phone number regardless of starting method** (its §1) — a
Google/email signup that doesn't match an existing account is not
complete until a phone-verification step also succeeds. This doc covers
what that looks like on screen (§3).

The Apple button described in §1/§5 below is a **visual placeholder only**
— a disabled "Continue with Apple — Coming soon" button reserving its slot
in the button stack. No SDK, no handler, no backend call. Real Apple
sign-in is Future Scope in the backend spec; this placeholder exists so the
UI doesn't need to reflow when it ships.

## 0. Branch-reality check (resolved before designing against it)

Checked `feat/enhanced-ui` against `Docs/frontend_execution.md`'s planned
stack rather than assuming either "not started" or "fully done":

- **Tailwind + shadcn/ui are actually landed and in active use.**
  `frontend/package.json` has `tailwindcss`, `tailwindcss-animate`,
  `class-variance-authority`, `tailwind-merge`, and the Radix primitives
  shadcn generates against (`@radix-ui/react-dialog`, `-label`, `-select`,
  `-slot`, `-tabs`, `-tooltip`). `frontend/components.json` is a real shadcn
  config. `@/components/ui/button` exists and is already imported by every
  file in `features/auth/`. `frontend/src/styles/tokens.css` explicitly
  bridges Design-Schema tokens into shadcn's own CSS-variable contract
  (`--background`, `--primary`, `--radius`, etc. sit alongside
  `--color-accent`, `--color-surface`). This spec designs directly against
  this — real, present, not aspirational.
- **Bklit UI has not actually migrated.** `components.json` only registers
  `"@bklit": "https://ui.bklit.com/r/{name}.json"` as a pull-on-demand
  shadcn registry *source* — there is no `@bklit` package in
  `package.json`, and no systematic chart migration. The only trace is a
  comment in `frontend/src/components/FundSignal.tsx` noting a nearby chart
  was hand-adapted from a Bklit-sourced component at some point. Everything
  chart-shaped in the repo today is built directly on `@visx`/`d3-shape`.
  **This spec does not design any `@bklit` import** for the new decorative
  panel (§5) — it's specified as a hand-built SVG/`@visx` component,
  matching what's actually there.
- **No router exists, confirmed, not just assumed.** No
  `react-router`/`BrowserRouter` usage anywhere in `frontend/src`. This
  matches `2026-08-06-phase-2b-onboarding-frontend-design.md`'s explicit,
  deliberate decision to not add one — `OnboardingFlow.tsx`'s in-memory
  history-array (`onboardingHistory.ts`) is *its own* step machine, but
  `AuthEntryFlow.tsx` (the component this section actually modifies) has an
  even simpler one: a local `useState<Step>` with `Step = "landing" |
  "phone" | "otp"`, switched over directly in JSX. This spec extends that
  same simple `useState` union — it does not introduce a router, and does
  not reuse `onboardingHistory`'s history-stack machinery, which belongs to
  the (separate, later) onboarding flow, not auth entry.

## 1. Component changes

`Landing.tsx` becomes the method-selector screen directly — it already *is*
the landing screen (currently rendering two buttons, Sign Up/Log In); it is
not preceded by a separate new screen. Concretely:

| File | Change |
|---|---|
| `AuthEntryFlow.tsx` | **Modified.** Outer wrapper (currently a single centered-card container) becomes the two-panel shell: left slot renders whichever step is active, right slot renders the new decorative panel, hidden below `lg:` (see §5). `Step` union extends to `"landing" \| "phone" \| "otp" \| "email" \| "email_otp" \| "link_account"` — **no additional step value for the phone gate**, see §3. The `AuthMode` (`"signup"\|"login"`) state is **removed** — see below. New local state: `pendingToken: string | null` and `phoneGatePrefillEmail: string | null` (§3). New handler: `handleGoogleCredential(idToken)`, and branching logic in both the Google-credential handler and the email-OTP-verify handler to check the response for `link_required` vs. `phone_required` vs. a normal session, instead of always calling `login()` directly (§3). |
| `Landing.tsx` | **Modified.** Headline becomes one neutral line ("Log in or sign up") replacing the two Sign Up/Log In buttons. The three feature-bullet blocks (Unified Wealth View / Smarter Financial Decisions / Family Portfolio Hub) should be condensed or dropped — the card now also holds the method buttons, and keeping all three bullets risks an overly tall card; this is a design-brief-stage call, not mandated here. Renders **four** pill buttons in this confirmed order — **1. Google, 2. Apple (disabled, "Coming soon"), 3. Email, 4. Phone** — kept inline in this file, not extracted, since it's used nowhere else (`frontend_execution.md` §19 warns against abstraction before repetition exists). |
| `PhoneEntry.tsx` | **Modified, twice over.** Drops `mode`/`onToggleMode` props and the mode-dependent headline/bottom toggle link ("Already have an account? Log In") — cascades from dropping Sign Up/Log In at the landing screen. Also gains an optional `context?: "primary" \| "phoneGate"` prop (default `"primary"`) driving which headline renders and whether a `pendingToken` is threaded into the submit — see §3 for why this is a prop on the existing component rather than a new one. |
| `OtpVerify.tsx` | **Unchanged.** Never depended on `mode`; reused as-is for the phone path, including the phone-gate completion path (§3) — it doesn't need to know why it's being shown, only that it's verifying a phone number. |

New files:

| File | Purpose |
|---|---|
| `EmailEntry.tsx` | Mirrors `PhoneEntry.tsx`'s shell (card, trust footer, error banner) collecting an email address instead of a phone number, calling the new `sendEmailOtp`. |
| `EmailOtpVerify.tsx` | Mirrors `OtpVerify.tsx` structurally — same props shape, differing only in copy ("We sent a 6-digit code to {email}") and calling `verifyEmailOtp`. **Deliberately a separate file, not a `channel`-parameterized generalization of `OtpVerify`** — two near-identical ~150-line files is a better trade here than one component with copy branching sprinkled through its JSX. |
| `GoogleButton.tsx` | Thin wrapper around Google Identity Services: renders the button, triggers the popup, forwards the resulting `id_token` via an `onCredential(idToken: string)` prop. Owns its own local `pending`/`error` state (same pattern as the existing `submitting`/`error` props threaded through `PhoneEntry`/`OtpVerify`), rendered as a spinner replacing the button's icon — not a separate screen (§2/§3). Also reused inside `LinkAccountPrompt` when the existing method to step up through is Google. |
| `useOAuthScript.ts` | Small shared hook: injects a third-party `<script>` tag exactly once per app lifetime (Google's `accounts.google.com/gsi/client`) and exposes loaded/error state. Written generically (takes a script URL, not hardcoded to Google) so a future `AppleButton` can reuse it without rework, per the backend spec's Future Scope section — but only instantiated for Google in this pass. |
| `LinkAccountPrompt.tsx` | The step-up-to-link screen for the collision case defined in the backend spec's §4. See §3. |
| `AuthShowcasePanel.tsx` | The static decorative right panel. See §5. |

## 2. OAuth flow in a router-less SPA

This is the concrete mechanism, not left as an open question: **Google's
sign-in uses a popup/token-based flow specifically because that avoids
needing a router or a callback route at all**, which the backend spec's §2
already specified but didn't spell out the *why* for the frontend
architecture.

- **Google Identity Services**, configured as the standard rendered
  button (not the redirect-based OAuth flow), runs entirely inside a
  GIS-managed iframe/popup. It does not navigate the top-level window. The
  `credential` (ID token) arrives via a JS callback
  (`callback: (response) => ...`) inside the SPA's existing execution
  context. **The page never unmounts** — `AuthEntryFlow`'s `useState<Step>`
  is untouched throughout, and nothing in progress is lost, because nothing
  ever navigates away to lose it.
- **The alternative (full-page redirect flow) would have genuinely broken
  the current architecture**, not just been inconvenient: a top-level
  redirect to `accounts.google.com` and back reloads the SPA from scratch on
  return, which would wipe `AuthEntryFlow`'s in-memory `useState` entirely
  (nothing here persists to `localStorage` except the session token itself,
  per `session.ts`). It would also require inventing a "callback"
  pseudo-step purely to re-inject the OAuth result into a freshly-mounted
  step machine after the reload. The popup/token flow sidesteps this
  category of problem rather than solving it after the fact.
- **Concrete risk to design around: popup blockers.** The GIS sign-in
  trigger must be called synchronously as the first line of the button's
  `onClick` handler — if there's an `await` (e.g. an analytics call) before
  `google.accounts.id.prompt()`, some browsers' popup blockers will kill the
  popup silently. `GoogleButton` must be written with this constraint
  explicit, not discovered later.
- **Loading state is inline, not a screen.** While the popup is open,
  `GoogleButton` shows a spinner in place of its own icon (mirroring the
  existing `submitting` boolean pattern) — there is no separate "OAuth
  loading" step in `AuthEntryFlow`'s `Step` union, because the screen
  underneath never needs to change while the popup is open.
- **Dismiss/failure handling** reuses the existing inline error-banner
  pattern (`error` state + `AlertCircle`, as already implemented in
  `PhoneEntry.tsx`/`OtpVerify.tsx`): Google's
  `notification.isNotDisplayed()`/`isSkippedMoment()` maps to the same
  banner, not a distinct error screen.

## 3. New auth-method screens

- **Email entry / verify**: `EmailEntry.tsx` → `EmailOtpVerify.tsx`,
  structurally identical to the existing Phone path, wired into
  `AuthEntryFlow`'s extended `Step` union exactly the same way.
- **OAuth loading/callback state**: intentionally **does not exist** as a
  distinct step — see §2. There is no callback route and no dedicated
  loading screen; the pending/error state lives locally inside
  `GoogleButton`.
- **Apple button**: a disabled pill button, same visual family as the other
  three (§5), labeled "Continue with Apple" with a small "Coming soon"
  badge/sub-label, `disabled` and inert — no `onClick`, no SDK loaded, no
  API call. Purely reserves its position in the button stack so the layout
  doesn't reflow when real Apple sign-in ships (backend spec's Future
  Scope). Not its own component — a static block inline in `Landing.tsx`,
  matching the same "don't abstract before there's real behavior" reasoning
  as the other inline button markup. When Apple sign-in is actually built,
  this block is replaced by a real `AppleButton.tsx` (backend spec's Future
  Scope already lists this file).

**Full response shape, now three-way** — the backend's mandatory phone gate
(its §1) means Google and email-OTP verification can resolve to one of
three outcomes, not two. Recommended wire contract (flagged as a
recommendation for planning to confirm against the actual route signature,
since the backend spec specifies the *policies* but not this exact shape):

```ts
type OtpVerifyResult =
  | OtpVerifyResponse                       // existing shape, normal login (or phone-gate completion, same shape)
  | { link_required: { token: string; matched_email: string; existing_method: "phone" | "email" | "google" } }
  | { phone_required: { token: string; prefill_email: string | null } };
```

The `token` field is named identically in both non-success variants and
serves the same mechanical role in both (attach a
`pending_identity_verifications` row's identity once a subsequent
verification succeeds — backend spec §1/§4) — the frontend threads it
through as a single `pendingToken` parameter regardless of which variant
produced it, rather than two differently-named fields. (This is a rename
from an earlier draft's `linkToken` — the backend spec unified both
triggers onto one table, so the frontend parameter name follows.)

- **`link_required`** (existing account, different method — §4): `AuthEntryFlow`
  transitions to `"link_account"` with the payload in local state, rendering
  `LinkAccountPrompt`: "We found an account associated with {matched_email}
  — log in with your {existing_method} to link this to it." It internally
  reuses whichever of `PhoneEntry`/`EmailEntry`/`GoogleButton` matches
  `existing_method`, threading `pendingToken` through that re-auth's verify
  call.
- **`phone_required`** (brand-new signup, phone still missing — backend
  spec's §1 mandatory gate): `AuthEntryFlow` stores `pendingToken` and
  `phoneGatePrefillEmail` (from the response's `prefill_email`) and
  transitions to the **existing** `"phone"` step — not a new step value —
  rendering `PhoneEntry` with `context="phoneGate"`. In that mode its
  headline changes to something like "One more step — verify your phone to
  finish creating your account" (optionally referencing
  `phoneGatePrefillEmail` if present, e.g. "...for {email}"), and its
  submit threads `pendingToken` through to `verifyOtp`. `OtpVerify.tsx`
  itself needs no change (§1) — on success, the backend has atomically
  created the `User`, both identities, and the `Session`, so
  `AuthEntryFlow` calls `login()` exactly as it does for a normal phone
  signup. **Both the Google-credential handler and the email-OTP-verify
  handler need this same three-way branch** — the backend spec confirms
  email and Google are symmetric here, not a Google-only case.

No new standalone "resolve link" or "complete signup" endpoint is
introduced in either case — the existing verify endpoints grow one
optional field and one richer response shape.

## 4. API client changes

New functions in `features/auth/api.ts`, following the existing plain-fetch/
typed-wrapper pattern (no client library, matches `requestOtp`/`verifyOtp`
exactly):

```ts
sendEmailOtp(email: string): Promise<OtpRequestResponse>              // POST /auth/otp/request, {email} instead of {phone_number}
verifyEmailOtp(email: string, otp: string, pendingToken?: string): Promise<OtpVerifyResult>  // POST /auth/otp/verify
verifyGoogleCredential(idToken: string, pendingToken?: string): Promise<OtpVerifyResult>      // POST /auth/oauth/google
```

`verifyOtp`'s existing signature also gains an optional `pendingToken`
param, covering **both** the phone-as-existing-method link-completion path
(§3's `link_required`) and the phone-gate completion path (§3's
`phone_required`) — one parameter name, since both attach an identity held
in the same backend-side `pending_identity_verifications` record (backend
spec §1).

**`AuthContext.tsx` needs no changes.** `login(token: string)` already only
cares about receiving a raw session token and calling `getMe()` — it has no
idea and no need to know which method produced that token, confirmed
provider-agnostic exactly like the backend's `Session` model (backend
spec's §5). The only new branching (normal login vs. `link_required`) lives
in `AuthEntryFlow`, which decides *whether* to call `login()` at all —
`AuthContext` itself is untouched.

## 5. Visual design

Built with the tokens confirmed real in §0 :

- **Pill buttons** use the same visual family as the existing `Button`
  usages in `Landing.tsx` (`rounded-xl`, `h-11 sm:h-12`, `min-h-[44px]`,
  full-width) — not shrunk-down icon chips like the reference. Phone/Email
  buttons use the existing outline-button treatment
  (`--color-surface`/`--color-border`). The Google button uses Google's
  **official logomark and brand-guideline button treatment** (Google
  requires using its unmodified logomark and publishes light/dark button
  assets with limited permitted customization, e.g. corner radius) — this
  is the one place "don't copy the reference's literal styling" doesn't
  apply, because it's a brand-compliance requirement, not a stylistic
  choice.
- **Apple's disabled button** uses `frontend_execution.md`'s existing
  disabled-state expectation (§21, "every relevant screen/component should
  account for... disabled") — reduced opacity, `cursor-not-allowed`, no
  hover treatment, and a small muted "Coming soon" badge/sub-label using
  `--color-text-secondary` — visually clearly inert rather than looking
  like a broken button. Still shows Apple's official logomark per its own
  brand guideline, same reasoning as the Google button treatment above.
- **Right panel theme**: follows the same light/dark tokens as the rest of
  the card (`--color-bg-dark`/`--color-surface-dark` family under dark
  theme) rather than being hardcoded permanently dark — a panel that never
  responds to `ThemeToggle` would look inconsistent sitting next to a card
  that does.
- **Right panel content** (`AuthShowcasePanel.tsx`): **structural
  placeholder only — exact content is pending details the product owner
  will provide separately** (Open Items). Until then, the working
  assumption to build against is a static SVG illustration — an arc using
  the same geometry convention as `FundSignal`'s logomark arc (per Design
  Schema's Fund Signal spec) plus a muted sparkline/trend line in
  `--color-accent`, built with the same raw SVG/`@visx` primitives already
  used elsewhere (not `@bklit`, per §0), with placeholder/sample values and
  short product copy. Static asset, no backend dependency, no real user
  data — this shape (static, no backend call) should hold regardless of
  what the final content turns out to be.
- **Responsive**: right panel hidden below the `lg:` breakpoint (matching
  the `sm:`/`lg:` breakpoint usage already present in `Landing.tsx`'s own
  classNames) — mobile collapses to the existing single centered-card
  layout, consistent with `frontend_execution.md`'s "reflow, don't just
  shrink" responsive mandate.

## 6. Test plan

Following `AuthEntryFlow.test.tsx`'s existing pattern exactly (render via
Testing Library, `vi.mock("./api")`, drive through roles/labels, assert on
calls and rendered content) — and matching the existing convention that
`PhoneEntry.tsx`/`OtpVerify.tsx` have **no dedicated test files of their
own**, covered entirely through `AuthEntryFlow.test.tsx`:

| File | Coverage |
|---|---|
| `AuthEntryFlow.test.tsx` (**modified**) | The existing "shows Sign Up and Log In" test is rewritten (that framing is gone). New cases: renders all four buttons in order (Google, Apple, Email, Phone), with Google/Email/Phone active and Apple disabled/non-interactive with "Coming soon" messaging on landing; "Continue with Phone" still leads through the existing phone→OTP→login path unchanged; "Continue with Email" leads through email→email-OTP→login, mirroring the phone test; a mocked Google credential success with a plain session response calls `login()` directly with no intermediate screen; a mocked response containing `link_required` transitions to the link-account step instead of calling `login()`; a mocked response containing `phone_required` transitions to the **existing** phone step (not a new one) with phone-gate copy, and completing that phone verification calls `login()` — parameterized across both Google and email-OTP as the triggering method, per the backend spec confirming they're symmetric. |
| `GoogleButton.test.tsx` (**new, dedicated**) | Unlike Email/Phone, this warrants its own file — it mocks a third-party global (`window.google`) that doesn't fit `AuthEntryFlow.test.tsx`'s existing `vi.mock("./api")` shape. Covers: renders the button; simulates the SDK callback firing with a fake credential and asserts `onCredential` is called with it; simulates a popup-dismissed event and asserts the inline error renders. |
| `useOAuthScript.test.ts` (**new**) | Loads a script tag exactly once even when invoked from two components; resolves a loaded-state; surfaces a script-load failure (e.g. an ad-blocker) as an error state. |
| `LinkAccountPrompt.test.tsx` (**new**) | Renders the "account already exists" messaging with the matched email and method hint; completes a step-up re-auth (mocking the existing method's OTP verify or Google re-auth) and asserts `login()` is called with the resulting session token afterward. |
| `AuthContext.test.tsx`, `onboardingHistory.test.ts` | **Unchanged** — confirmed no behavior change needed in either (§4). |

## Explicit Deviations (flagging, not silently resolving)

1. **PRD-02 FR-2b superseded for the entry screen specifically.** FR-2b's
   "Sign Up and Log In as two labeled entry points" is replaced by one
   neutral framing across all v1 methods (§1). PRD-02 itself is left
   unedited per product decision (the backend spec is standalone,
   cross-referenced, not a PRD-02 revision) — but anyone reading PRD-02
   FR-2b going forward should know it no longer reflects the built entry
   screen.
2. **ADR-001's "no public marketing surface" framing is overridden for this
   one screen's decorative right panel**, per explicit product decision.
   This is scoped narrowly — one static, illustrative asset on the auth
   screen — not a reopening of ADR-001's broader no-Next.js/no-SEO-surface
   decision, which stands otherwise unchanged.

## Appendix

### Related Documents
- `2026-08-14-multi-method-auth-design.md` — the backend spec this doc
  builds on: identity model, Google verification, email+OTP, the
  account-linking policy, session model, security, and setup checklist
- `2026-08-06-phase-2b-onboarding-frontend-design.md` — the existing
  onboarding frontend this auth screen hands off into, and the precedent
  for splitting frontend design into its own doc from a backend spec
- Design-Schema-Unifolio.md — light/dark color tokens, component
  conventions reused for the new card and pill buttons
- `Docs/frontend_execution.md` — Tailwind/shadcn/Bklit stack status,
  confirmed against actual `feat/enhanced-ui` code in §0

### Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-14 | Claude (PM partner) | Split out of `2026-08-14-multi-method-auth-design.md`'s §9 into its own file, per user request, mirroring this repo's existing Phase 2 / Phase 2b backend-frontend doc split. Content unchanged from that section at time of split (branch-reality check, component changes, router-less OAuth-popup mechanism, new screens, API client changes, visual design, test plan) — renumbered from 9.0–9.6 to 0–6 for a standalone doc. |
| 1.1 | 2026-08-14 | Claude (PM partner) | Synced with the backend spec's v1.4 resolutions: added the mandatory phone-gate UI path (`phone_required` response variant, reusing the existing `"phone"`/`"otp"` steps via a new `PhoneEntry` `context` prop rather than new step values), renamed `linkToken` to `pendingToken` throughout (backend unified both triggers onto one table), and added a disabled "Coming soon" Apple placeholder button per product decision to reserve its UI slot ahead of the real (still Future Scope) integration. |
| 1.2 | 2026-08-14 | Claude (PM partner) | Confirmed pill-button order: Google, Apple (disabled), Email, Phone — no longer an open item. Clarified the right-side panel's content is a structural placeholder pending product-owner input, not a design-brief default. |
