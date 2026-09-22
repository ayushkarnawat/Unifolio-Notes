# Auth Left Panel — Editorial Refinement (Direction B) Implementation Plan

> **For agentic workers:** This plan targets **Google Antigravity** as the implementing agent, not Claude Code's own subagent tooling — ignore any references elsewhere to `superpowers:subagent-driven-development` or `superpowers:executing-plans`; they don't apply here. Steps use checkbox (`- [ ]`) syntax purely for progress tracking. Work task-by-task, top to bottom; each task is self-contained (files, exact code, exact test commands) — you should not need outside context to complete it. If anything in this plan conflicts with what you find in the actual files, stop and flag it rather than silently resolving it either way.

**Goal:** Replace `AuthShowcasePanel.tsx`'s current "fragments align and sharpen" scattered-rectangles animation with an editorial, typography-led composition — one dominant headline anchored to the lower third of the panel, a huge near-invisible ambient arc (the brand logomark's own geometry, scaled up) as background texture, a static grain overlay for material depth, and a slower blur-to-focus reveal. No invented data, no card mockups.

**Architecture:** Single-file rewrite of one React component (`AuthShowcasePanel.tsx`) plus a small, additive token expansion in the global CSS token file (`tokens.css`). No new components, no new dependencies, no changes to any other file. The component keeps its existing external contract (`AuthShowcasePanelProps { step?: AuthStep }`) so nothing that renders it (`AuthShell.tsx` / wherever it's mounted) needs to change.

**Tech Stack:** React + TypeScript, Tailwind CSS (utility classes, plus CSS custom properties for anything token-driven), `motion/react` (Framer Motion) for the reveal animation, Vitest + React Testing Library + `@testing-library/jest-dom` for tests.

**Spec:** No separate upstream spec file exists for this — the full visual/copy/motion spec is captured in the "Design Reference" section immediately below, and is not to be re-derived or reinterpreted. Treat that section as the spec.

## Design Reference (read this before writing any code)

This is a redesign of the **left visual panel** on Unifolio's Sign Up / Sign In screen — the first thing a user sees when opening the app. Unifolio is positioned as a materially better, more premium alternative to Mprofit for tracking Indian mutual funds. Two facts made the copy decisions below, and should not be second-guessed without going back to product docs (`Docs/PRDs/PRD-02-Signup-Onboarding.md`, `Docs/PRDs/Design-Brief-Unifolio.md`):

- **One login covers a whole family** (up to 5 members) — most competitors are single-portfolio only.
- **Every holding is reconciled from real CAS statements** into one accurate number — this screen's job is to set a premium, calm, trustworthy tone; the actual emotional payoff of onboarding is the CAS-import moment later, not this screen.

**Composition (top to bottom, inside the panel):**
1. A quiet, tiny uppercase "Unifolio" wordmark, top-left — this is the composition's asymmetric anchor point (not a repeated brand lockup; `AuthShell.tsx` already shows the real brand mark elsewhere on the page).
2. Empty space — deliberate headroom, this is what makes the composition feel premium rather than cramped.
3. One dominant headline, anchored toward the lower third:
   - Line 1: `Stop Guessing.`
   - Line 2: `Start Systemizing.`
   - Supporting line directly beneath (smaller, secondary color): `Every folio, every family member — reconciled into one number you can trust.`
4. The existing trust footer, unchanged:
   - `Most investors manage wealth in scattered silos.`
   - `Disciplined portfolios run on a systematic engine.`

**Ambient background (behind everything, decorative only, `aria-hidden`):**
- A large arc bleeding off the top-right corner, reusing the same arc geometry as the brand logomark (`AuthShell.tsx` already draws `M 50 10 A 40 40 0 0 1 90 50` for the real mark) but scaled up and at very low opacity (~0.14–0.22) — texture, not an icon.
- A static grain overlay (SVG `feTurbulence`) for material depth. It does **not** animate — it's rendered once and stays still.

**Motion:**
- Headline lines: fade in + rise 16px→0 + blur 6px→0, ~950ms, easing `[0.16, 1, 0.3, 1]`, second line delayed ~160ms after the first.
- Supporting line: same treatment, starts ~620ms in.
- Ambient arc: opacity/scale fade over ~2.6s, starting ~200ms in (slower — it's texture, it should feel like it was always there, not like it "arrived").
- Wordmark: quick simple opacity fade, ~600ms.
- All of this plays **once per page load** (existing `hasAnimatedInSession` module-level flag pattern — keep it, don't rebuild it) and collapses to the fully-resolved final state instantly under `prefers-reduced-motion` or in tests (existing `isTestEnv` pattern — keep it).
- A small step-responsive touch carries over from the previous version: when `step !== "landing"` (i.e. the user has moved past the landing screen), the ambient arc and wordmark should read very slightly more present (arc opacity 0.14→0.22, wordmark opacity 0.68→0.85) — a quiet "we've moved forward" signal, not a new visual element.

**Two deliberate cleanups bundled into this rewrite** (both are pre-existing, already-flagged issues in the file being rewritten, not new scope):
- The panel currently uses `rounded-3xl`, which is not one of the Design Schema's three locked radii (`--radius-sm` 8px / `--radius-md` 12px / `--radius-lg` 20px). Tailwind's `rounded-lg` utility is already wired in `tailwind.config.js` to `var(--radius-lg, 20px)` — switch to `rounded-lg`.
- The panel currently applies `select-none` to the entire container, including the real headline/footer prose. Drop it — there's no decorative-text-selection problem here that justifies blocking selection of real copy.
- The headline is currently wrapped in an `<h1>`. It's marketing copy inside a visual panel, not the page's actual heading (the form side already has its own `<h1>` — "Create your account" / "Welcome back" — which is the real page heading). Use a `<p>` instead so the page doesn't carry two `<h1>` elements.

**Colors and motion values below are exact — don't approximate them.**

## Global Constraints

- **TDD, no exceptions:** no implementation code without a failing test first (CLAUDE.md non-negotiable). `AuthShowcasePanel.tsx` currently has zero test coverage — Task 2 closes that gap before any implementation, not after.
- **`prefers-reduced-motion` must be respected with no exceptions** — every animated value must collapse to its final state, never partially animated and never skipped-to-blank.
- **Only three border-radius values exist in this design system:** `--radius-sm` (8px), `--radius-md` (12px), `--radius-lg` (20px). No ad-hoc radii.
- **DM Sans is the display/heading font, Manrope is the body font** — both already wired as Tailwind's `font-display` / `font-body` (or the default `font-sans`, which is Manrope per `tailwind.config.js`). Don't introduce a third font.
- **No points, badges, streaks, or confetti anywhere in this product** (Design Brief, Principle 2) — not applicable to this specific change, but don't add any either.
- The panel is an **intentional, documented exception** to the app's light/dark theme system — it is always dark, regardless of the user's theme preference. Do not make it theme-responsive; that would be a regression, not a fix.

## File Structure

- **Modify:** `frontend/src/styles/tokens.css` — add a small, clearly-commented `--auth-panel-*` color token group (this panel's fixed always-dark palette, currently hardcoded as raw hex/rgba inside the component) and two new motion tokens (`--motion-hero-reveal`, `--motion-hero-stagger`) for this slower, first-impression-only reveal, distinct from the app's existing 150/400/300ms micro-interaction tokens.
- **Modify:** `frontend/src/features/auth/AuthShowcasePanel.tsx` — full rewrite of the component body. Props interface (`AuthShowcasePanelProps`) and the default export name (`AuthShowcasePanel`) stay identical — nothing that imports this component needs to change.
- **Create:** `frontend/src/features/auth/AuthShowcasePanel.test.tsx` — new test file (this component has none today).

---

### Task 1: Add design tokens for the panel's fixed palette and the hero reveal's motion timing

**Files:**
- Modify: `frontend/src/styles/tokens.css`

**Interfaces:**
- Produces (CSS custom properties consumed by Task 2): `--auth-panel-bg`, `--auth-panel-bg-2`, `--auth-panel-ink`, `--auth-panel-ink-soft`, `--auth-panel-glow`, `--auth-panel-ghost`, `--auth-panel-ghost-soft`, `--motion-hero-reveal`, `--motion-hero-stagger`.

- [x] **Step 1: Add the new tokens to the base `:root` block**

Open `frontend/src/styles/tokens.css`. Find this existing block (near the end of the base `:root { ... }` section, right after the `/* Motion */` tokens):

```css
  /* Motion */
  --motion-fast: 150ms ease-out;
  --motion-reveal: 400ms ease-in-out;
  --motion-page: 300ms ease-in-out;
}
```

Replace it with (adds two new motion tokens, then a new dedicated section, still inside the same `:root` block — note the closing `}` moves to the end of the new section):

```css
  /* Motion */
  --motion-fast: 150ms ease-out;
  --motion-reveal: 400ms ease-in-out;
  --motion-page: 300ms ease-in-out;
  /* First-impression hero reveals (e.g. AuthShowcasePanel's headline) are
     deliberately slower and calmer than in-app micro-interactions — this is
     its own tier, not a reuse of --motion-reveal. */
  --motion-hero-reveal: 950ms cubic-bezier(0.16, 1, 0.3, 1);
  --motion-hero-stagger: 160ms;

  /* Auth Panel (always-dark, intentional exception) — the left auth/onboarding
     visual panel in AuthShowcasePanel.tsx does not follow the app's light/dark
     theme toggle by design. These tokens exist so its colors are named and
     reusable instead of hardcoded hex scattered through that one component;
     they must NOT be touched by the dark-mode media query or [data-theme]
     blocks below, since the panel doesn't change with theme. */
  --auth-panel-bg: #040806;
  --auth-panel-bg-2: #081a12;
  --auth-panel-ink: #F5F7F4;
  --auth-panel-ink-soft: rgba(245, 247, 244, 0.78);
  --auth-panel-glow: #4ADE80;
  --auth-panel-ghost: rgba(148, 163, 184, 0.5);
  --auth-panel-ghost-soft: rgba(148, 163, 184, 0.22);
}
```

- [x] **Step 2: Zero out the two new motion tokens under reduced motion**

Find the existing block at the very end of the file:

```css
@media (prefers-reduced-motion: reduce) {
  :root {
    --motion-fast: 0ms;
    --motion-reveal: 0ms;
    --motion-page: 0ms;
  }
}
```

Replace it with:

```css
@media (prefers-reduced-motion: reduce) {
  :root {
    --motion-fast: 0ms;
    --motion-reveal: 0ms;
    --motion-page: 0ms;
    --motion-hero-reveal: 0ms;
    --motion-hero-stagger: 0ms;
  }
}
```

- [x] **Step 3: Verify the tokens are well-formed**

Run: `grep -n "auth-panel\|motion-hero" frontend/src/styles/tokens.css`
Expected: 9 matching lines (7 `--auth-panel-*` declarations + 2 `--motion-hero-*` declarations in the base block), plus 2 more `--motion-hero-*` lines inside the reduced-motion block — 11 lines total. If any are missing, the edit didn't land — fix before continuing.

- [x] **Step 4: Commit**

```bash
git add frontend/src/styles/tokens.css
git commit -m "feat(tokens): add auth-panel palette and hero-reveal motion tokens"
```

---

### Task 2: Rewrite `AuthShowcasePanel.tsx` as the editorial hero (TDD)

**Files:**
- Create: `frontend/src/features/auth/AuthShowcasePanel.test.tsx`
- Modify: `frontend/src/features/auth/AuthShowcasePanel.tsx`

**Interfaces:**
- Consumes: `AuthStep` type from `./AuthShell` (already exported there — `export type AuthStep = "landing" | "email" | "phone" | "otp" | "email_otp" | "link_account"`); `isTestEnv` from `@/lib/motion` (already exported there); the token names produced by Task 1.
- Produces: `AuthShowcasePanelProps { step?: AuthStep }` (unchanged) and the default-exported `AuthShowcasePanel` function component (unchanged name/signature) — anything currently rendering `<AuthShowcasePanel step={...} />` keeps working with no changes on its end.

- [x] **Step 1: Write the failing tests**

Create `frontend/src/features/auth/AuthShowcasePanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AuthShowcasePanel } from "./AuthShowcasePanel";

describe("AuthShowcasePanel", () => {
  it("renders the hero headline, supporting line, and trust footer", () => {
    render(<AuthShowcasePanel />);

    expect(screen.getByText("Stop Guessing.")).toBeInTheDocument();
    expect(screen.getByText("Start Systemizing.")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Every folio, every family member — reconciled into one number you can trust.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Most investors manage wealth in scattered silos."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Disciplined portfolios run on a systematic engine."),
    ).toBeInTheDocument();
  });

  it("does not introduce a second page-level heading", () => {
    render(<AuthShowcasePanel />);
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });

  it("marks the grain and ambient-arc graphics as decorative", () => {
    const { container } = render(<AuthShowcasePanel />);
    const decorativeSvgs = container.querySelectorAll('svg[aria-hidden="true"]');
    expect(decorativeSvgs).toHaveLength(2);
  });

  it("uses the schema's radius-lg token, not an ad-hoc rounded-3xl, and allows text selection", () => {
    const { container } = render(<AuthShowcasePanel />);
    const root = container.firstChild as HTMLElement;
    expect(root.className).toContain("rounded-lg");
    expect(root.className).not.toContain("rounded-3xl");
    expect(root.className).not.toContain("select-none");
  });

  it("resolves straight to the final visual state under test/reduced-motion (no mid-animation values)", () => {
    render(<AuthShowcasePanel />);
    const firstLine = screen.getByText("Stop Guessing.");
    // isTestEnv forces the instant path — the line's own `initial` state
    // already equals its animate target, so opacity must never read 0 here.
    expect(firstLine).toHaveStyle({ opacity: "1" });
  });

  it("reads slightly more present once the user has moved past the landing step", () => {
    render(<AuthShowcasePanel step="phone" />);
    const wordmark = screen.getByText("Unifolio");
    expect(wordmark).toHaveStyle({ opacity: "0.85" });
  });
});
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/auth/AuthShowcasePanel.test.tsx`
Expected: FAIL — the current `AuthShowcasePanel.tsx` renders "Stop Guessing." inside an `<h1>` (so the "no second heading" test fails), has zero `aria-hidden` SVGs, still has `rounded-3xl` and `select-none`, and has no "Every folio, every family member..." text or "Unifolio" wordmark at all.

- [x] **Step 3: Replace the implementation**

Replace the entire contents of `frontend/src/features/auth/AuthShowcasePanel.tsx` with:

```tsx
import { motion, useReducedMotion } from "motion/react";
import type { AuthStep } from "./AuthShell";
import { isTestEnv } from "@/lib/motion";

// Module-level flag so the reveal animation plays ONLY ONCE per full page load.
// Navigating between auth steps (landing, email, phone, otp, etc.) or form re-renders will NEVER replay or reset the animation.
let hasAnimatedInSession = false;

interface AuthShowcasePanelProps {
  step?: AuthStep;
}

const HEADLINE_LINES = ["Stop Guessing.", "Start Systemizing."];
const SUPPORT_LINE =
  "Every folio, every family member — reconciled into one number you can trust.";

export function AuthShowcasePanel({ step = "landing" }: AuthShowcasePanelProps) {
  const shouldReduceMotion = useReducedMotion() || isTestEnv;
  const isInstant = hasAnimatedInSession || shouldReduceMotion;

  // Step-responsive subtle presence enhancement: once the user has moved
  // past the landing screen, the ambient arc and wordmark read very slightly
  // more present — a quiet "we've moved forward" signal, not a new element.
  const isProgressed = step !== "landing";
  const arcOpacity = isProgressed ? 0.22 : 0.14;
  const wordmarkOpacity = isProgressed ? 0.85 : 0.68;

  const lineTransition = (delay: number) =>
    isInstant
      ? { duration: 0 }
      : { duration: 0.95, delay, ease: [0.16, 1, 0.3, 1] as const };

  return (
    <div className="relative w-full h-full min-h-[580px] lg:min-h-[640px] rounded-lg bg-[var(--auth-panel-bg)] border border-emerald-950/60 p-6 sm:p-8 lg:p-10 flex flex-col overflow-hidden text-[var(--auth-panel-ink)] shadow-2xl">
      {/* 1. Ambient Depth Background */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(circle at 60% 12%, var(--auth-panel-bg-2) 0%, var(--auth-panel-bg) 58%, #010302 100%)",
        }}
      />

      {/* 2. Static grain texture — material depth only, never animates */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none opacity-50 mix-blend-overlay"
        aria-hidden="true"
      >
        <filter id="auth-panel-grain">
          <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch" />
          <feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.05 0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#auth-panel-grain)" />
      </svg>

      {/* 3. Ambient brand-arc texture — logomark geometry at large scale, decorative only */}
      <motion.svg
        className="absolute -top-[18%] -right-[26%] w-[150%] h-[150%] pointer-events-none"
        viewBox="0 0 200 200"
        preserveAspectRatio="xMidYMid slice"
        aria-hidden="true"
        initial={isInstant ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={isInstant ? { duration: 0 } : { duration: 2.6, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
      >
        <path d="M20 185 A160 160 0 0 1 185 20" fill="none" stroke="var(--auth-panel-glow)" strokeWidth="1" opacity={arcOpacity} />
        <path d="M46 190 A150 150 0 0 1 190 46" fill="none" stroke="var(--auth-panel-ghost)" strokeWidth="0.6" opacity={arcOpacity + 0.04} />
      </motion.svg>

      {/* 4. Quiet wordmark — asymmetric composition anchor, not a repeated brand lockup */}
      <motion.p
        className="relative z-10 text-[0.62rem] font-semibold tracking-[0.22em] uppercase text-[var(--auth-panel-ink-soft)] font-body"
        initial={isInstant ? { opacity: wordmarkOpacity } : { opacity: 0 }}
        animate={{ opacity: wordmarkOpacity }}
        transition={isInstant ? { duration: 0 } : { duration: 0.6, delay: 0.1, ease: "easeOut" }}
      >
        Unifolio
      </motion.p>

      {/* 5. Hero statement — anchored to the lower third, real headroom above */}
      <div className="relative z-10 flex-1 flex flex-col justify-end gap-3 pb-1.5">
        <p className="font-display font-extrabold tracking-tight text-[clamp(1.9rem,3.4vw,2.75rem)] leading-[1.08] text-[var(--auth-panel-ink)]">
          {HEADLINE_LINES.map((line, i) => (
            <motion.span
              key={line}
              className="block"
              initial={
                isInstant
                  ? { opacity: 1, y: 0, filter: "blur(0px)" }
                  : { opacity: 0, y: 16, filter: "blur(6px)" }
              }
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={lineTransition(i * 0.16)}
            >
              {line}
            </motion.span>
          ))}
        </p>
        <motion.p
          className="max-w-[34ch] text-sm text-[var(--auth-panel-ink-soft)] font-body leading-relaxed"
          initial={isInstant ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={lineTransition(0.62)}
          onAnimationComplete={() => {
            hasAnimatedInSession = true;
          }}
        >
          {SUPPORT_LINE}
        </motion.p>
      </div>

      {/* 6. Trust footer — unchanged */}
      <div className="relative z-10 text-center max-w-sm sm:max-w-md mx-auto space-y-1 mt-6">
        <p className="text-xs sm:text-sm text-neutral-400 font-body font-normal leading-relaxed">
          Most investors manage wealth in scattered silos.
        </p>
        <p className="text-xs sm:text-sm text-[var(--auth-panel-glow)] font-body font-medium leading-relaxed">
          Disciplined portfolios run on a systematic engine.
        </p>
      </div>
    </div>
  );
}
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/features/auth/AuthShowcasePanel.test.tsx`
Expected: PASS — all 6 tests green.

- [x] **Step 5: Run the full frontend test suite to confirm nothing else broke**

Run: `cd frontend && npm test`
Expected: PASS. In particular, check any test that renders `AuthShell.tsx` or the full auth flow still passes — this component's external contract (`AuthShowcasePanelProps`, export name) didn't change, so nothing should need updating there, but confirm rather than assume.

- [x] **Step 6: Commit**

```bash
git add frontend/src/features/auth/AuthShowcasePanel.tsx frontend/src/features/auth/AuthShowcasePanel.test.tsx
git commit -m "feat(auth): replace showcase panel's fragment animation with editorial hero"
```

---

### Task 3: Final verification

**Files:** none (verification only — no code changes in this task)

- [ ] **Step 1: Type-check the whole frontend**

Run: `cd frontend && npx tsc -b`
Expected: 0 errors.

- [ ] **Step 2: Production build**

Run: `cd frontend && npm run build`
Expected: builds cleanly, no warnings about the new file.

- [ ] **Step 3: Manual check in a real browser — reduced motion**

Run the dev server (`cd frontend && npm run dev`), open the Sign Up / Sign In screen in a desktop-width window (the panel is `hidden` below the `lg` breakpoint, so the window must be at least `lg` width — 1024px — to see it at all). With OS-level "reduce motion" turned on, confirm the panel renders immediately in its fully-resolved state: headline fully sharp and opaque, wordmark and ambient arc both visible at their resting opacity, no blur, no fade-in observed.

- [ ] **Step 4: Manual check in a real browser — motion enabled, and the wordmark-duplication question**

With reduced motion off, reload the page and confirm: the headline lines blur-fade-rise into place, the supporting line follows shortly after, the ambient arc fades in slowly in the background, and none of it repeats on a second reload of the same session (refresh should show the resolved state instantly — this is the `hasAnimatedInSession` flag working as intended, note it resets on a full page reload since it's in-memory, not persisted, which is correct). Separately, look at the small "Unifolio" wordmark inside the dark panel next to the real brand wordmark+arc that `AuthShell.tsx` renders at the top of the light form column, and confirm they don't read as an odd duplicate now that they're both visible on screen together — they're in different visual zones (dark panel vs. white card) so they should read as distinct, but this was flagged as worth a real look rather than assumed.

- [ ] **Step 5: Commit (if step 4's check surfaced a fix)**

If the wordmark check in Step 4 reveals a real problem, fix it in `AuthShowcasePanel.tsx` (e.g. remove the in-panel wordmark, or reduce its opacity further) and repeat Tasks 2's test run before committing. If no problem was found, there's nothing to commit for this task — the plan is complete.

## Self-Review Notes

- **Spec coverage:** composition (wordmark, headline, support line, footer) → Task 2 Step 3; ambient arc + grain → Task 2 Step 3; motion timing/tokens → Task 1 + Task 2 Step 3; `rounded-3xl`/`select-none`/double-`<h1>` cleanups → Task 2 Step 3 and asserted directly in Task 2 Step 1's tests; step-responsive presence → Task 2 Step 3, asserted in Task 2 Step 1's last test; reduced motion → asserted in Task 2 Step 1, manually re-checked in Task 3 Step 3.
- **Type consistency:** `AuthShowcasePanelProps` name and shape unchanged from the current file; `AuthStep` import path unchanged; `isTestEnv` import path unchanged — no call site outside this component needs to change.
- **No placeholders:** every step above contains complete, real code — nothing marked TBD or "similar to above."
