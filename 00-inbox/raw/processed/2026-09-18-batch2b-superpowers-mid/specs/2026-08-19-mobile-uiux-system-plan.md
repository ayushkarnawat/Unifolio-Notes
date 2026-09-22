---
artifact: mobile-uiux-system-plan
version: "1.0"
created: 2026-08-19
status: for-review
product: Unifolio
audience: A coding agent (e.g. Google Antigravity) executing the plan
---

# Unifolio — Mobile UI/UX System Plan

**Planning only. No code was written or modified to produce this document.**
Grounded in `Docs/MOBILE_APP_EXECUTION.md` (existing mobile policy — read in
full, not duplicated here), a direct read of every file listed in §2, the
`ui-ux-pro-max` skill's UX/navigation/forms guidance, and a mobile
inspiration folder that turned out narrower than expected (§0).

## 0. What the recon actually found — three things to resolve before planning further

1. **A real routing contradiction, already in the code.** `Docs/
   MOBILE_APP_EXECUTION.md` states mobile "must not automatically replace
   the web experience based on viewport/device detection." But
   `frontend/src/App.tsx` currently does exactly that: it renders
   `MobileRoot` when `isMobileRoute` (path `/mobile`) **OR**
   `isMobileViewport` (a live `matchMedia("(max-width: 767px)")` check) is
   true — so resizing a desktop browser window below 768px already
   auto-switches to the mobile shell today, contradicting the written
   policy. **This is actually what makes your "Chrome DevTools responsive
   viewport" requirement already work** — recon confirms the dev-experience
   you asked for is already true, not something to build. Recommendation:
   keep the current auto-viewport behavior (it's what you explicitly asked
   for) and update `MOBILE_APP_EXECUTION.md`'s wording to match reality,
   rather than ripping out working, useful behavior to match a doc that
   predates it. Flagging this rather than silently picking a side — say if
   you'd rather enforce the doc as written instead.
2. **The mobile inspiration folder is entirely auth/onboarding screens** —
   login, signup, OTP, forgot-password, welcome carousels. Nothing on
   navigation, dashboard, holdings, charts, or empty/loading states, which
   is most of what this plan actually needs to design. Several images
   overlap with two auth-focused folders already analyzed earlier this
   session. Where §5 needs inspiration for non-auth screens, it's grounded
   in Unifolio's own already-established mobile patterns (below) rather
   than stretched from auth references that don't cover that ground.
3. **Mobile is already ahead of web for Dashboard/Holdings.** The desktop
   Main Dashboard is still `DashboardPlaceholder.tsx`, a literal stub. So
   "carry over web dashboard patterns to mobile" has no source to carry
   *from* for that specific screen — mobile's dashboard/holdings
   implementation (666-line `MobileDashboardView.tsx`, full fund-detail
   view + sheet, distributor comparison drill-down) is mature and already
   ahead. When the desktop dashboard eventually gets built, it should
   follow the product semantics already established on mobile, not the
   reverse.

## 1. Confirmed architecture decision — no new mobile codebase question to answer

`Docs/MOBILE_APP_EXECUTION.md` already, deliberately, establishes a
separate mobile presentation tree (`frontend/src/mobile/`), reached via
`/mobile`, isolated from web, reusing the same API clients/types/tokens.
This *is* "the existing architecture genuinely requiring it" — it's
documented policy, already substantially built out (shell, dashboard,
holdings, fund detail, distributor comparison, and a just-redesigned import
flow), not something to reconsider or consolidate.

**The CAS import v2 redesign already established the right pattern going
forward** — confirmed by reading `MobileImportView.tsx`: it directly reuses
`ImportPathChoice` and `WaitingForCasView` from the web feature folder
as-is (genuinely device-agnostic screens), while `MobileRequestCamsView.tsx`
and `MobileUploadForm.tsx` stay mobile-specific (touch dropzone, own
layout), navigating via an `onBack` prop rather than route params. This
plan adopts that exact rule for everything below:

> **Share a screen's component when nothing about it is touch/layout-
> sensitive (choice screens, status/waiting screens, simple confirmations).
> Keep a mobile-specific component when density, input method, or layout
> genuinely differs (forms, lists, detail views, navigation chrome). Use
> `onBack`-prop navigation, not routes, for drill-downs — already the
> established convention.**

## 2. Current mobile state — what already exists (verified by reading the files)

| Area | File(s) | State |
|---|---|---|
| Shell | `MobileRoot.tsx`, `shell/MobileAppShell.tsx`, `MobileBottomNav.tsx`, `MobileHeader.tsx`, `MobileDeviceFrame.tsx` | Mature. `MobileDeviceFrame` doubles as the real layout (edge-to-edge, `h-dvh`) below `md:` and a centered "phone" preview chrome above it. `MobileAppShell` already has generic loading/error/empty state handling. `MobileHeader` is sticky (wordmark+logo or back-chevron+title, right-action slot). `MobileBottomNav` has exactly 3 slots — Dashboard, Analytics (disabled, "Soon"), Import — safe-area-aware, 44–48px targets. |
| Dashboard | `MobileDashboardView.tsx` (666L), `MobileHoldingCard.tsx` | Mature: hero portfolio value (tabular-nums), `AllocationDonut`, searchable/filterable holdings list, coverage-gap surfacing, household-member handling. Card already matches the documented summary-first decision (FundSignal, scheme, member, value) plus more (plan-type badge, gain/loss, stale-NAV badge). No illustration/motion used anywhere in this file. |
| Holdings/Fund detail | `MobileHoldingsView.tsx`, `MobileHoldingCardSummary.tsx`, `MobileFundDetailView.tsx` (full-screen), `MobileFundDetailSheet.tsx` (bottom-sheet variant), `MobileDistributorComparisonView.tsx` | Mature, two detail presentations exist (full-screen vs. sheet). No illustration/motion used. |
| Import (just redesigned) | `MobileImportView.tsx`, `MobileRequestCamsView.tsx`, `MobileUploadForm.tsx`, `MobileImportHistory.tsx`, `MobileReviewView.tsx` | Current, already illustration/motion-aware where relevant, establishes the sharing pattern in §1. `MobileReviewView.tsx` is the only file here importing `motion/react` directly. |
| Onboarding/Auth | `frontend/src/features/auth/*` | **No separate mobile tree at all — purely shared, responsive web components.** `App.tsx` renders `AuthEntryFlow`/`OnboardingFlow` identically regardless of `isMobile`; a user only reaches `MobileRoot` after onboarding completes. This is already correct and needs no new mobile-specific work. |
| Main Dashboard (web) | `DashboardPlaceholder.tsx` | Still a stub (§0.3). |

## 3. Mobile design system

Extends existing tokens (`frontend/src/styles/tokens.css`) — no new colors,
no new type family, no new spacing unit invented for mobile specifically.

| Aspect | System |
|---|---|
| Typography | Same DM Sans (display) / Manrope (body) pairing and 8-token scale as web. Mobile body text floors at 16px (already avoids iOS input auto-zoom); tabular-nums stays mandatory on every financial figure, as on web. |
| Spacing | Same 4px-base scale. Mobile leans toward the tighter end (8/12/16) for list density, 24/32 for section breaks — a density choice, not a new unit. |
| Grid/layout | Single-column, full-bleed within `MobileDeviceFrame`'s safe area. No multi-column layouts below `md:` — matches `mobile-first`/`no-horizontal-scroll` guidance. |
| Buttons | Same shadcn `Button` primitives as web; primary CTA always accent-green, one per screen (`primary-action` rule) — already followed in the CAS import mobile work. |
| Inputs | Same `Input`/`Label` primitives; add `inputmode="numeric"`/`"tel"`/`"email"` per field type where missing (a genuine, concrete gap the ui-ux-pro-max search surfaced — mobile keyboards should match input type, not default to text everywhere). |
| Cards | Existing `MobileHoldingCard`/`MobileHoldingCardSummary` pattern (icon/signal + primary label + secondary meta + trailing value) is the canonical mobile card shape — reuse its structure for any new list, don't invent a second card language. |
| Navigation | `MobileBottomNav`'s existing 3-slot pattern stays canonical (bottom-nav-limit ≤5 is already respected). `MobileHeader`'s sticky wordmark-or-back pattern stays canonical for all screens. |
| Icons/illustrations | Lucide icons throughout (already the standard, no emoji). Illustrations: reuse the *existing* hand-drawn `OnboardingIllustration` system (already used in onboarding + the new CAS import choice screen) for empty states — don't introduce a second illustration style. Per the Design Brief's own "numbers are the product" principle, illustration belongs in empty/loading/encouragement moments, not inside dense data screens (Dashboard/Holdings/Fund Detail stay clean and tabular — playful lives in the soft moments, not the numbers). |
| States | `MobileAppShell`'s existing generic loading/error/empty handling is the canonical mechanism — extend it with the illustration treatment above for empty states specifically (e.g. "No holdings yet"), keep loading states as skeletons (already the pattern), keep error states text+icon+retry (already the pattern used in `MobileDistributorComparisonView`). |
| Touch targets | ≥44×44px everywhere, already met by `MobileBottomNav` and the CAS import mobile work — hold every new interactive element to the same bar. |
| Breakpoints | Validate at 320/375/430px exactly as `MOBILE_APP_EXECUTION.md` already specifies — no new breakpoint set needed. |

## 4. Per-screen plan

Screens already mature (Dashboard, Holdings, Fund Detail, Distributor
Comparison, Import — all of §2) get a **shorter** entry below: what to
*preserve* and the one or two concrete gaps found, not a redesign from
scratch. Screens with a real gap (empty/error states, Import History) get
the fuller 7-point treatment.

### 4.1 Navigation (`MobileBottomNav` / `MobileHeader`)
1. **Purpose/hierarchy**: top-level wayfinding between Dashboard, Analytics (deferred), Import.
2. **Layout**: bottom tab bar, 3 slots, safe-area-aware — unchanged.
3. **Components/interactions**: icon + label per slot, active-state accent color — unchanged.
4. **Carries from web**: the accent-color active-state convention.
5. **Redesigned for mobile**: nothing new — this is already correctly mobile-native, not a shrunken web pattern (web has no equivalent nav yet since its dashboard doesn't exist).
6. **Inspiration**: none needed from the auth-only inspo folder; already sound per `bottom-nav-limit`/`nav-state-active`.
7. **Responsive**: already safe-area-aware; no change.

### 4.2 CAS Import flow
Already fully redesigned this session (`Docs/superpowers/specs/2026-08-19-cas-import-illustration-redesign.md`, v2) with full mobile parity. This plan treats that work as the **reference implementation** for the sharing pattern in §1 — no further changes proposed here.

### 4.3 Onboarding / authentication
Purely shared, responsive web components (§2) — reached before `MobileRoot` even mounts. No mobile-specific plan needed; this is already correct, not a gap.

### 4.4 Main Dashboard (mobile)
1. **Purpose/hierarchy**: portfolio value first, then allocation, then holdings list — already the order in `MobileDashboardView.tsx`.
2. **Layout**: hero value → `AllocationDonut` → searchable/filterable list. Preserve as-is.
3. **Components/interactions**: search/filter, coverage-gap surfacing, household-member switching — preserve.
4. **Carries from web**: N/A — web's dashboard doesn't exist yet (§0.3); this screen is the semantic source, not the follower.
5. **Redesigned for mobile**: the one real gap — its empty state (no holdings yet) should get the illustration treatment from §3 (an "empty portfolio" moment, following the household-member-placeholder pattern already described in the App-Flow docs), rather than a bare text message. Loading state: convert to skeleton cards matching `MobileHoldingCard`'s shape if not already.
6. **Inspiration**: none from the auth-only folder; ground the empty-state illustration in the existing `OnboardingIllustration` visual recipe (hand-drawn, green-accent, ambient glow) for consistency, not a new style.
7. **Responsive**: validate at 320px specifically — this is the densest screen in the app (donut + list + hero value) and the one most likely to feel cramped at the smallest supported width.

### 4.5 Holdings list, Fund Detail, Distributor Comparison
1. **Purpose/hierarchy**: list → detail → distributor drill-down, already correctly layered with back-navigation at each level.
2. **Layout**: summary-first cards → full-screen or sheet detail → comparison table. Preserve.
3. **Components/interactions**: `FundSignal`, gain/loss arrows, badges — preserve.
4. **Carries from web**: N/A, same reasoning as §4.4.
5. **Redesigned for mobile**: two detail presentations exist (full-screen `MobileFundDetailView` and `MobileFundDetailSheet`) — worth a product decision on which is canonical rather than maintaining both indefinitely; not a design gap, a maintenance-scope question to raise with the product owner before Antigravity does more work on either.
6. **Inspiration**: none needed.
7. **Responsive**: validate the comparison table doesn't force horizontal scroll at 320px — this is the one place tabular data meets the narrowest viewport.

### 4.6 Import History (mobile)
1. **Purpose/hierarchy**: secondary/tertiary — a list of past imports, reached via a small persistent action (mirroring web's placement per the CAS v2 redesign).
2. **Layout**: simple list, one row per past import (date, status, member).
3. **Components/interactions**: currently plain — no motion, no illustration.
4. **Carries from web**: the same de-emphasized, secondary placement convention.
5. **Redesigned for mobile**: apply the standard empty-state treatment (§3) when no history exists yet; otherwise, this screen is low-stakes and doesn't need illustration — a plain list is correct here per "illustration as storytelling, not decoration" (a history log isn't a decision point).
6. **Inspiration**: none needed.
7. **Responsive**: standard list virtualization if the list can grow long (`virtualize-lists` guidance) — flag for Antigravity to check the actual list-length ceiling before deciding if virtualization is warranted.

### 4.7 Forms & inputs (cross-cutting, not a single screen)
1. **Purpose**: every text/password/file input across mobile (password fields in CAS import, search boxes in Dashboard/Holdings).
2. **Layout**: unchanged, already using shadcn `Input`/`Label`.
3. **Components/interactions**: add `inputmode` per field type where missing (§3) — the one concrete cross-cutting gap found.
4. **Carries from web**: the visible-label-not-placeholder-only convention, already followed.
5. **Redesigned for mobile**: `inputmode` attributes; otherwise unchanged.
6. **Inspiration**: the auth-inspo folder's OTP screens use individual digit-box inputs — already matched by Unifolio's own `OtpInput` component built earlier this session; no further action.
7. **Responsive**: inputs already meet the ≥44px height requirement.

### 4.8 Cards & lists (cross-cutting)
1. **Purpose**: the holdings/history list shape used across Dashboard, Holdings, Import History.
2. **Layout**: `MobileHoldingCard`'s existing shape (icon/signal + primary + meta + trailing value) is canonical — reuse it, don't invent a second card shape for Import History.
3. **Components/interactions**: tap-to-expand/drill-down, already established.
4. **Carries from web**: the underlying data fields/semantics (same API types).
5. **Redesigned for mobile**: N/A — already mobile-native by design.
6. **Inspiration**: the wellness-app reference's "segmented control below, sparkline row above" composition (§0.2's cluster D) is the one genuinely transferable pattern from the inspo folder — worth citing as a layout precedent *if* a time-range selector ever gets added to a mobile chart (e.g. an allocation trend), not for the card list itself.
7. **Responsive**: cards already stack single-column; no change.

### 4.9 Empty / loading / error states (cross-cutting)
1. **Purpose**: the one real cross-cutting gap this recon surfaced — `MobileAppShell` already has the *mechanism* (generic props for each state) but most screens don't yet pass an illustrated empty state through it.
2. **Layout**: centered illustration (small/`sm` size, per the onboarding convention) + one-line message + one action, inside the existing shell mechanism.
3. **Components/interactions**: reuse `OnboardingIllustration` variants where semantically close (e.g. `"upload"` for "no imports yet"); commission at most one or two new variants for concepts with no existing match (e.g. "no holdings yet") rather than one bespoke illustration per screen.
4. **Carries from web**: the illustration system itself.
5. **Redesigned for mobile**: the empty/loading/error *copy and layout* — mobile has less room, so copy should be shorter than any equivalent web empty state.
6. **Inspiration**: ground new illustration needs in Unifolio's own established recipe, not the auth-only inspo folder.
7. **Responsive**: standard — same treatment at all three validated widths.

## 5. Implementation roadmap for Antigravity

**Scope**: `frontend/src/mobile/**` for the concrete changes below; a small
edit to `Docs/MOBILE_APP_EXECUTION.md` to reconcile §0.1; no changes to
`frontend/src/features/**` (web) beyond what's already shipped; no backend
changes.

1. **Resolve §0.1 first**: get explicit product-owner confirmation to keep
   the current auto-viewport-switch behavior in `App.tsx` (recommended,
   since it's what you asked for), then update `MOBILE_APP_EXECUTION.md`'s
   wording to match — don't leave the doc and the code contradicting each
   other.
2. Add `inputmode` attributes to any mobile input missing them (§4.7).
3. Build the illustrated empty-state treatment (§4.9) and wire it into
   `MobileAppShell`'s existing empty-state prop for Dashboard (§4.4) and
   Import History (§4.6) at minimum.
4. Convert Dashboard's loading state to skeleton cards matching
   `MobileHoldingCard`'s shape if it isn't already (§4.4).
5. Raise the `MobileFundDetailView` vs. `MobileFundDetailSheet` duplication
   (§4.5) with the product owner — a scope/maintenance question, not
   something to silently resolve by picking one.
6. Verify the distributor comparison table and the dashboard's donut+list
   composition both hold up at 320px without horizontal scroll (§4.4/§4.5).
7. Check Import History's real-world list length; add virtualization only
   if warranted (§4.6).
8. No changes needed for Navigation (§4.1), CAS Import (§4.2 — already
   done), Onboarding/Auth (§4.3 — already correct), or Cards/Lists (§4.8)
   beyond what's already built.
9. Work on a new git branch, never on `main` directly. Update `session.md`
   and `CLAUDE.md`'s Session State when done.

---

## Ready-to-paste prompt

> Read `Docs/superpowers/specs/2026-08-19-mobile-uiux-system-plan.md` in
> full before writing any code. Most of Unifolio's mobile experience
> (`frontend/src/mobile/**`) already exists and is mature — this plan is
> deliberately scoped to real, verified gaps only (§0 and §4's numbered
> points), not a redesign of what's already working. Start with §0.1: get
> product-owner sign-off on keeping the current auto-viewport-switch
> behavior in `App.tsx` (it's what was actually requested), then update
> `Docs/MOBILE_APP_EXECUTION.md` to match. Then work through §5's roadmap in
> order — illustrated empty states reusing the existing `OnboardingIllustration`
> system, `inputmode` attributes, dashboard loading skeletons, and the two
> flagged items that need a product decision rather than code (§4.5's dual
> fund-detail presentations, §4.6's list-length check). Do not modify
> `frontend/src/features/**` (web) or backend code. Work on a new git
> branch, never on `main` directly. When finished, update `session.md` and
> `CLAUDE.md`'s Session State section.
