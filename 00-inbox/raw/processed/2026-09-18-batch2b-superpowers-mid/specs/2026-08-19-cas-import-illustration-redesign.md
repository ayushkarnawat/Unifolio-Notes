---
artifact: cas-import-illustration-redesign
version: "2.0"
created: 2026-08-19
status: for-review
product: Unifolio
audience: A coding agent (e.g. Google Antigravity) executing the redesign
---

# Unifolio — CAS Import Flow: Illustration-Led Redesign Plan

## 0. Version note

v1 of this document proposed decorating the existing tab-bar-plus-dense-card
layout (add an illustration, consolidate the requirement chips). That
direction was reviewed against mockups and rejected as **not enough visual
change** — the goal is a genuinely bolder structural difference, not the
same layout with a graphic added. v2 (this version) replaces the entry point
entirely with an illustrated choice screen, validated through several rounds
of visual mockups. v1's UX assessment (why the current flow is dense/
mislabeled) is still accurate background and is preserved in §1 below; only
the *direction* changed, not the diagnosis.

## 1. UX assessment of the current CAS flow (unchanged from v1, still accurate)

- **The "Step 1 / Step 2" framing is a mislabel.** `TwoPathImportContainer`
  implements these as two independently-selectable tabs — a user with a PDF
  already in hand has no reason to visit "Step 1" at all. These are two
  alternative *paths* to the same outcome, not sequential steps.
- **"Request from CAMS" is dense and bureaucratic in tone** — three required
  form values presented as cramped, scattered pill-chips.
- **"Upload Existing Statement" is already close to the bar** — proper
  drag-and-drop, file-progress list, labeled password field.
- **`WaitingForCasView` shows two full calls-to-action at once** — a status
  card *and* an unconditionally-rendered full upload form beneath it.
- **`CoverageGapBanner` is on an older visual system** (legacy `Button`
  import, inline `style` objects) and will look inconsistent with everything
  else in this flow once it's polished — still needs the migration noted in
  §6.
- **The exact illustration this flow needs already exists and is unused**:
  `OnboardingIllustration`'s `"upload"` variant, alt text *"CAS statement
  automated ingestion illustration"* — built for this flow, never wired in.
- **Motion tokens already exist** in `lib/motion.ts`
  (`staggerContainerVariants`/`staggerItemVariants`/`pageTransition`) and are
  already used by `ImportFileProgressList`/`ParsingIndicator`, just not by
  this flow's other screens yet.
- **Mobile currently has neither the illustration nor the motion system
  wired in at all** (`MobileRequestCamsView.tsx`, `MobileUploadForm.tsx`).

## 2. The validated design — four screens

Everything below was iterated and approved through visual mockups, not
invented fresh in this document. Copy shown is exact, not placeholder.

### 2.1 Entry screen — "Choose how to get your statement" (new)

Replaces the tab bar entirely as the first thing shown. Structurally mirrors
`Q4Household.tsx`'s already-proven onboarding pattern (shared illustration
anchor → eyebrow + headline → a short list of illustrated choice-rows) —
this is the single biggest structural change in this redesign.

- Top row unchanged: small uppercase "CAS IMPORT FLOW" label + a secondary
  "Import History" pill button, exactly as today. No tab bar beneath it.
- `<OnboardingIllustration variant="upload" />` as a centered hero, same
  size convention as onboarding (not larger).
- Eyebrow: "GET YOUR PORTFOLIO IN". Headline: "How would you like to bring
  in your statement?" Subtext: "Either way, Unifolio turns it into one clear
  view of everything you hold."
- Two choice-rows (icon box + title + tag + one-line description + trailing
  arrow, same visual language as `Q4Household.tsx`'s choice buttons):
  1. **"Request from CAMS"**, tag **Recommended** — "Free, official, and
     covers every AMC automatically. Arrives by email in 5–10 min."
  2. **"Already have a statement"**, tag **Upload PDF** — "Drop in a CAMS or
     KFintech PDF you already downloaded — done in seconds."
- Tapping a row navigates into that path's detail screen (§2.2/§2.3) — the
  two paths are never shown simultaneously as competing tabs.

### 2.2 Detail screen — "Request from CAMS" (replaces `RequestCamsPath`'s current layout)

- Back link: "← Back to import options".
- Title: "Request from CAMS" — **no tag/badge here** (the recommendation was
  already communicated on the choice screen; repeating it here is noise).
- Description: "CAMS generates a free Consolidated Account Statement across
  all your mutual funds and emails it to you directly."
- One consolidated reference card, captioned **"On the CAMS form, select
  these three options"**, listing the same three values as today
  (unchanged): Statement — Detailed statement · Period — 10-year duration ·
  Folios — with zero folios.
- Three guided steps, rewritten to be accurate about what's manual (CAMS is
  a third-party site — Unifolio pre-fills nothing there):
  1. "Tapping below opens the official CAMS site in a new tab."
  2. "Select the above three options on the form."
  3. "Enter your email and set a password for your CAS file — that's all
     CAMS needs from you."
- CTA: "Request Statement on CAMS →" — same action as today
  (`requestCamsStatement`), unchanged.

### 2.3 Detail screen — "Upload your statement" (`UploadForm`, minimally changed)

- Back link: "← Back to import options" (only when reached from the choice
  screen — see §4's note on `onBack` being optional/conditional, since this
  same component is also reused inside §2.4's disclosure without a back
  link there).
- Title: "Upload your statement" — **no tag/badge**.
- Description: "Drop in the CAMS or KFintech Detailed CAS PDF you already
  have — we'll take it from here."
- Dropzone, password field, and submit button: **unchanged** — this screen
  was already close to the bar in v1's assessment and stays as-is.

### 2.4 "Waiting for the CAMS email" — what's shown when the user returns from the CAMS tab

Replaces `WaitingForCasView`'s current always-both-visible layout.

- A single status card: pulse indicator + "Waiting for CAMS email" +
  "Cancel request" action (same cancel behavior as today). Body copy:
  "CAMS usually sends your statement within 5–10 minutes. Once it lands in
  your inbox, come back here to finish importing — you don't need to keep
  this tab open."
- Below it, a collapsed disclosure: **"Already got the email? Upload it now
  ↓"**. Tapping it expands the same dropzone + password field from §2.3 in
  place (animated height/opacity, respecting `prefers-reduced-motion`) —
  it is not rendered by default the way it is today.

## 3. Navigation / state model

Current `TwoPathImportContainer` state is a 3-way tab (`"request" | "upload"
| "history"`) plus a `pendingImportId` that's supposed to gate a "waiting"
view but is actually gated under the `"request"` tab while
`handleRequestInitiated` switches `activeTab` to `"upload"` — meaning today,
right after requesting, the user actually lands on the plain upload form,
and the waiting status only reappears if they navigate back to the (now
zero-numbered) first tab. This is confusing and not what §2.4 specifies.

**Named, deliberate correction** (small, scoped, and directly responsive to
the approved design above — not a silent reinterpretation): replace the tab
model with an explicit view-state:

```
view: "choice" | "request" | "waiting" | "upload" | "history"
```

- Default on fresh entry: `"choice"` (§2.1).
- Resume behavior unchanged: if `hasCasResumeStep2(memberId)` is true (the
  user already initiated a CAMS request earlier), skip straight to
  `"upload"` on mount and on window focus — exactly today's behavior, just
  renamed from the old `"upload"` tab default.
- `"request"` → §2.2. Its CTA calling `requestCamsStatement` successfully
  now transitions to `"waiting"` (not `"upload"`) — this is the one behavior
  change, and it's what makes §2.4 actually reachable as designed.
- `"waiting"` → §2.4, replacing today's `WaitingForCasView` always-shown
  form with the collapsed disclosure.
- `"upload"` → §2.3, reachable directly from `"choice"` or from expanding
  the disclosure inside `"waiting"`.
- `"history"` → unchanged, still the small persistent pill button, not part
  of the choice-row list.
- Back navigation from `"request"` or `"upload"` (when reached from
  `"choice"`) returns to `"choice"`. No back link inside `"waiting"` —
  "Cancel request" remains the way out, unchanged from today.

No API call, resume-tracking mechanism, or backend contract changes — only
which view a given state renders.

## 4. Component/file changes

| File | Change |
|---|---|
| `TwoPathImportContainer.tsx` | Remove the tab-bar UI entirely. Replace with the `view` state model in §3. Render `ImportPathChoice` (new) for `"choice"`. Keep the "Import History" pill and top label row as-is. |
| **`ImportPathChoice.tsx`** (new) | The entry screen from §2.1 — mirrors `Q4Household.tsx`'s structure: `motion.div` with `staggerContainerVariants`, `<OnboardingIllustration variant="upload" />`, header, two choice-rows built the same way as `Q4Household`'s buttons (icon box + title + tag + description + trailing arrow), calling back into the container to set `view` to `"request"` or `"upload"`. |
| `RequestCamsPath.tsx` | Add back-link (`onBack` prop, always present here). Remove the `Badge` "Recommended" element (now lives only on the choice screen). Consolidate the three chips into one captioned reference card. Replace the three step descriptions with §2.2's corrected copy. Apply `staggerContainerVariants`/`staggerItemVariants` to the steps. Preserve the `requestCamsStatement` call and its result handling exactly, except the caller now transitions to `"waiting"` instead of `"upload"` (§3). |
| `UploadForm.tsx` | Add an *optional* `onBack` prop (rendered only when provided) so the same component works both as a back-navigable detail screen (§2.3, called with `onBack`) and as the disclosure content inside `"waiting"` (§2.4, called without `onBack`). No other change — dropzone/password/submit stay exactly as they are. |
| `WaitingForCasView.tsx` | Replace the unconditionally-rendered `<UploadForm onSubmit={handleUpload} />` with the collapsed disclosure from §2.4 — a toggle that expands/collapses the same `UploadForm` (no `onBack`), animated via opacity/height, respecting reduced motion. Status card copy and "Cancel Request" behavior unchanged. |
| `CoverageGapBanner.tsx` | Still needs the v1-flagged migration off the legacy `Button` import and inline `style` objects onto the shadcn `Button` + token/Tailwind classes its siblings use — unrelated to the screens above, still worth doing in this pass for visual consistency. |
| `MobileRequestCamsView.tsx` / `MobileUploadForm.tsx` | Apply the equivalent of §2.1's choice screen, §2.2's corrected `RequestCamsPath` copy/layout, and §2.4's disclosure pattern to their mobile counterparts — currently neither uses `OnboardingIllustration` or `motion/react` at all. |
| `ParsingIndicator.tsx`, `ImportFlow.tsx` | **Out of scope**, unchanged. |

## 5. Illustration & motion

- `OnboardingIllustration variant="upload"` is used **once**, as the hero on
  the choice screen only (§2.1) — not repeated on the detail or waiting
  screens. The choice screen tells the story; the detail screens are about
  clear execution, per "illustration as storytelling, not decoration."
- Reuse `lib/motion.ts`'s existing `staggerContainerVariants`/
  `staggerItemVariants` for the choice screen's header+rows and for the
  "Request from CAMS" detail screen's three guided steps — no new motion
  tokens needed.
- The waiting screen's disclosure expand/collapse (§2.4) is the only new
  motion interaction — a simple height/opacity transition, must collapse
  instantly under `prefers-reduced-motion`.

## 6. Preserve / explicitly out of scope

- No backend changes. No change to `ImportFlow.tsx`'s `Step` union.
- Every copy *value* (statement/period/folios settings, 25MB limit, "usually
  your PAN (uppercase) or DOB" password hint, 5–10 minute timing) stays
  exactly as today except the specific rewrites called out in §2.2/§2.4,
  which the product owner has already reviewed and approved via mockup.
- `ParsingIndicator` stays a plain spinner — no illustration added there
  (§1/v1's reasoning still holds: a processing screen isn't a decision
  point).

## 7. Responsive behavior

- Apply every screen in §2 to both the desktop path
  (`RequestCamsPath.tsx`/`UploadForm.tsx`) and its mobile counterpart
  (`MobileRequestCamsView.tsx`/`MobileUploadForm.tsx`) — mobile currently
  has neither the illustration nor motion system at all, so this is not
  optional parity, it's the same amount of new work twice.
- `ImportPathChoice`'s choice-row layout should stack cleanly at narrow
  widths the same way `Q4Household.tsx`'s already does — reuse its
  responsive classes rather than inventing new breakpoints.
- Every new interactive element (choice-rows, the waiting-screen disclosure,
  back links) meets the ≥44×44px touch-target minimum already met elsewhere
  in this flow.
- `prefers-reduced-motion` collapses the disclosure animation and the
  stagger reveals to their end state instantly.

## 8. Implementation steps for Antigravity

1. Build `ImportPathChoice.tsx` per §2.1/§4.
2. Update `TwoPathImportContainer.tsx` to the `view` state model in §3,
   removing the tab bar and wiring `ImportPathChoice` as the `"choice"` view.
3. Update `RequestCamsPath.tsx`: back-link, remove the badge, consolidate
   the reference card, replace the three step descriptions with §2.2's
   copy, and change its success handler to transition to `"waiting"`.
4. Add the optional `onBack` prop to `UploadForm.tsx`; use it when rendering
   the `"upload"` view, omit it inside the waiting-screen disclosure.
5. Restructure `WaitingForCasView.tsx` per §2.4 — disclosure instead of an
   always-shown form.
6. Migrate `CoverageGapBanner.tsx` per §4's table row.
7. Apply steps 1, 3, and 5's equivalents to `MobileRequestCamsView.tsx` and
   `MobileUploadForm.tsx`.
8. Verify: existing import-flow tests pass (update any that assert on the
   old tab-bar structure or old copy); reduced-motion collapses the new
   disclosure/stagger animations; touch targets ≥44px; resume behavior
   (`hasCasResumeStep2`) still skips straight to `"upload"` on mount/focus;
   no backend or copy-*value* changes beyond §2.2/§2.4's approved rewrites.
9. Work on a new git branch, never on `main` directly. Update `session.md`
   and `CLAUDE.md`'s Session State when done.

---

## Ready-to-paste prompt

> Read `Docs/superpowers/specs/2026-08-19-cas-import-illustration-redesign.md`
> in full before writing any code — it's v2; §0 explains that v1's
> "decorate the existing layout" approach was rejected in favor of the
> bolder structural redesign in §2, which was validated through visual
> mockups the product owner already approved. Build exactly the four
> screens in §2 (with their exact copy), the `view` state model in §3
> (including the one named behavior correction — CAMS-request success now
> leads to a `"waiting"` state, not back to `"upload"`), and the file-by-file
> changes in §4. Reuse `OnboardingIllustration` and `lib/motion.ts`'s
> existing tokens — don't invent new ones. Apply everything to both web and
> mobile (§7). No backend changes, no change to `ImportFlow.tsx`'s state
> machine, no copy-*value* changes beyond what §2 specifies. Work on a new
> git branch, never on `main` directly. When finished, update `session.md`
> and `CLAUDE.md`'s Session State section.
