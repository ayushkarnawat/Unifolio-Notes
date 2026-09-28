# Session Log

> Permanent, append-only chronological log of what was done, session by session. Distinct from `session.md`, which stays a short, prunable "picking this up cold" pointer to *current* status only and gets overwritten each session — this file is the full history and is never trimmed or summarized away. Backfilled 2026-08-14 from `session.md`'s own accumulated history plus `Docs/superpowers/plans/` and `Docs/superpowers/specs/`; entries before that date are reconstructed from those sources, not lived through in real time, so treat exact dates on early entries as best-available rather than certain.

## 2026-07-22 — Stack decisions finalized

ADR-001 through ADR-006 accepted: React/Vite SPA, FastAPI, AWS RDS Postgres, scoped S3 (no CAS PDF retention), ECS Express Mode, EventBridge Scheduler + Fargate. See `decisions.md` and `Docs/PRDs/ADR-Technical-Stack-Decisions.md`.

## 2026-08-04 — Phase 0 (foundation) and Phase 1 backend (CAS import) built

Phase 0: all 11 tasks, `Docs/superpowers/plans/2026-08-04-phase-0-foundation.md`. Phase 1 backend: CAS import tightening + monolith port, all 9 tasks, `Docs/superpowers/plans/2026-08-04-phase-1-cas-import-backend.md` — `casparser` wrapper, `mfapi.in` enrichment, two-phase parse/confirm API routes, Decimal-safe calc.

## 2026-08-05 — Phase 1b (Import Review frontend) and Phase 2 backend (Auth + Onboarding) built

Phase 1b: all 7 tasks, `Docs/superpowers/plans/2026-08-05-phase-1b-import-review-frontend.md`. Phase 2 backend: phone+OTP auth, session tokens, `GET`/`PATCH /auth/me`, household-member CRUD — all 4 tasks, `Docs/superpowers/plans/2026-08-05-phase-2-auth-onboarding-backend.md`.

## 2026-08-06 — Phase 2b (onboarding frontend), Phase 3 backend (Main Dashboard), transaction-dedupe migration

Phase 2b: `Docs/superpowers/plans/2026-08-06-phase-2b-onboarding-frontend.md`. Phase 3 backend: `Docs/superpowers/plans/2026-08-06-phase-3-main-dashboard-backend.md`. Also: migration 0002 widened the transaction dedupe key to include `type`, fixing a real bug where same-day equal-magnitude purchase/redemption pairs collided — see `decisions.md`.

## 2026-08-07 — Distributor comparison (PRD-03 FR-11) built; frontend redesign brief written

`Docs/superpowers/plans/2026-08-07-distributor-comparison.md`. Also produced `Docs/superpowers/specs/2026-08-07-frontend-redesign-brief-for-coding-agent.md`, setting up the later Antigravity-driven frontend redesign pass.

## ~2026-08-08/09 — Phase 3b: Frontend UI Redesign (Google Antigravity), reviewed and fixed by Claude Code

Built via Google Antigravity on `feature/frontend-redesign` (zero backend changes). Antigravity's own report claimed full test coverage — false on inspection: 39 of 104 frontend tests failing plus 6 `tsc` errors. Claude Code root-caused and fixed every one, not just patched to green. Real app bugs found and fixed: a PDF-password `<label>` missing `htmlFor` (accessibility regression), `MainDashboardFlow`'s Add Data re-entry silently misattributing uploads to the wrong household member (used an onboarding-only component with no way to target a specific member), and a `Decimal`-never-`float` violation on the dashboard's most visible number (Total Portfolio Value was client-side `parseFloat`-summed instead of using the already-fetched server total). Also fixed: a dead `strokeDashoffset` var, `import type` fixes for `verbatimModuleSyntax`, and ~20 tests stale against redesigned copy. Follow-up same session: fixed `investedVal`/`profitVal` float accumulation with a dependency-free exact-decimal-string `sumDecimalStrings` helper, and untracked the `impeccable` plugin from git history (kept on disk, added to `.gitignore`). Merged to `main` (fast-forward, commit `61bf6f4`); `dev_intern` cut from the same commit. Final verified state: 156/156 backend, 111/111 frontend, `tsc` clean.

## 2026-08-10 — Phase 4 Analytics backend, Parts 1–4 built (design + build order set)

Full 5-step Analytics build order designed: `Docs/superpowers/plans/2026-08-10-phase-4-analytics-backend-design.md`. **Part 1 (category allocation, FR-1/FR-2)** built on `feature/phase4-part1-allocation`, merged to `dev_intern` this session (`1ab0fab`) — `analytics/allocation.py`, 2 new routes, 8 tests, suite to 164/2. **Part 2 (AMFI TER+AAUM → weighted TER, FR-10/FR-11)** built same session, continuing straight on — `amfi_ter_client.py`, `amfi_aaum_client.py`, `ter.py`, 4 routes, 40 new tests, suite to 250/2 (see `decisions.md` for the 0.55 fuzzy-match-threshold tuning). **Part 3 (NSE Indices → benchmark comparison, FR-8/FR-9)** built same session — `nse_indices_client.py` (live-corrected the `niftyindices.com` endpoint path, since the design doc's and TDD's documented path was dead), `xirr.py` (pure-Decimal Newton-Raphson solver), `benchmark.py`, routes, 36 new tests, suite to 286/2. **Part 4 (category-universe NAV caching → ranking, FR-3/FR-4)** built same session — `scheme_universe.py` (AMFI bulk `NAVAll.txt` ingestion, live-verified format), `category_ranking.py` (see `decisions.md` for the 40/60 blend-weight decision), routes, suite to 314/2.

Also this session: knowledge graph refreshed to match the Part 1 merge commit (533 nodes/1223 edges); branch reconciliation merging Part 1–4 work with the intern's separately-landed UI/UX overhaul and CAS import redesign (`bb32b97`), `dev_intern` fast-forwarded to match.

## 2026-08-1X — Cleanup pass: knowledge graph refreshed again, stale branch deleted

Follow-up session before Phase 4 Part 2 restart context: knowledge graph re-refreshed via full 7-phase `/understand` pipeline to 661 nodes/1657 edges/10 layers/15 tour steps, matching HEAD after the CAS Import lifecycle feature landed. `feature/phase4-part1-allocation` local branch deleted (confirmed merged). ~50 files reconfirmed as pure CRLF-line-ending noise, not touched.

## 2026-08-12 — Model-orchestration skill built

`.claude/skills/model-orchestration/` — governs delegating implementation work to Codex as default worker, Claude Code as orchestrator. Built via brainstorming → writing-plans → subagent-driven-development. Design: `Docs/superpowers/specs/2026-08-12-model-orchestration-skill-design.md`; plan: `Docs/superpowers/plans/2026-08-12-model-orchestration-skill.md`.

## 2026-08-13 — Phase 4 Part 5: the Scorer built, completing PRD-04 Analytics backend

Ayush's one hard product requirement for Analytics — see `decisions.md` for the 45/30/25 weighting decision. Built as three ordered tasks (`risk_metrics.py` shared time-series building blocks; `scorer.py`'s composite score; portfolio-level roll-up) plus 3 API routes and a stakeholder-facing methodology doc (`Docs/Scorer-Methodology-Unifolio.md`). Final whole-branch adversarial review (the `model-orchestration` skill's mandatory gate) caught 3 real findings, all fixed in one round: a redundant per-fund category-universe re-scoring (High), a Feb-29 `date.replace` crash (Medium, second occurrence of a bug already parked once elsewhere — fixed at the root with a shared `years_ago()` helper), and a racy check-then-insert on daily `FundScore` persistence (Medium, fixed via pinning `computed_at` to UTC day-start). Backend suite: 357 passing, 2 skipped (up from 341/2). PRD-04 backend is now fully complete — only the Analytics frontend remains unbuilt.

## 2026-08-13/14 — Dashboard load-time performance fix (Fix A/B/D)

Root cause diagnosed directly: on-demand NAV fetch is a local-dev-first stand-in for the still-deferred ADR-006 scheduled refresh job (Fix C). Three in-scope mitigations delegated end-to-end to Codex via `model-orchestration`: **Fix A** (background NAV prefetch on import confirm), **Fix B** (parallelized per-scheme NAV network fetch, DB reads/writes never interleaved across coroutines), **Fix D** (process-local per-day holdings cache). Fix D took 4 full implement→verify→adversarial-review rounds before it was correct — each round's review caught something real (a cacheable stale/incomplete snapshot, a publish-after-invalidate race, an NAV-upsert IntegrityError race, a too-narrow cache-eligibility rule defeating the cache's own purpose, and finally a bounded-but-accepted single-flight gap). Explicit user decision: accept round 4's remaining limitation (no per-key single-flight coordination), do not dispatch a round 5 — see `decisions.md`. Full round-by-round detail: `Docs/orchestration/dashboard-nav-perf-handoff.md` (Status: DONE) and `Docs/orchestration/delegation-log.md`. Backend suite grew 156 → 326 passing, 2 skipped throughout, zero regressions. Then: `feat/enhanced-ui` fast-forwarded to pick up 4 incoming colleague UI commits, this fix committed on top and pushed; `dev_intern` fast-forwarded to match and pushed.

## 2026-08-14 — Branch reconciliation; CAS import lifecycle redesign and UI/UX foundation backfilled into shared history

Session opened mid-branch-drift: intern (`aditishanbhag`) had pushed a Badge/Select componentry cleanup to `feat/enhanced-ui` while an in-progress local fix for the same two issues was still pending here — the in-progress local fix was discarded once the intern's independently-equivalent commits landed (confirmed via full suite re-verification, not reused from an earlier run). Result: `dev_intern` and `feat/enhanced-ui` merged and identical at `7426047` (357 passed/2 skipped backend, 190/190 frontend across 49 files, `tsc` clean).

Reconciling the branches surfaced two authorship streams not yet reflected in `CLAUDE.md`/`session.md`:
1. **CAS Import lifecycle redesign** (intern-authored, backend + frontend) — an 11-state import lifecycle state machine (`import_/state_machine.py`), migration 0003 (`Import`/`Folio` schema changes, new `OPENING_BALANCE` transaction type), coverage-gap detection, opening-balance resolution, a CAMS-portal mailback URL generator, and the matching frontend (API client/types, lifecycle views, a two-path CAS import UI). **Passes the full test suite but has not had an independent Claude Code review pass** against CLAUDE.md's non-negotiables — flagged as an open item, not treated as equivalent to "reviewed."
2. **UI/UX foundation** (intern-authored) — shadcn/Tailwind/design-token setup, mobile app shell, dashboard/fund-details/responsive routing, then a same-day Radix `Select` refactor across `ReviewTable`/`AttributionModal`/`AddFamilyMembers`/mobile filters, a unified `Badge` component, and a `toTitleCase` utility for proper-casing badge/plan-type text. Also not yet independently reviewed.

## 2026-08-14 — Multi-method auth: design finalized, backend implementation plan written

Brainstormed and specced a remodel of auth from phone+OTP-only to phone + email-OTP + Google as equal-looking entry points, with Apple deferred to Future Scope. Design went through several rounds of resolution (see `decisions.md` for the substantive calls: mandatory phone gate, identity precedence, account-linking policy, `EmailProvider` abstraction, Postmark timing, Apple placeholder). Backend and frontend design specs split into separate files (`Docs/superpowers/specs/2026-08-14-multi-method-auth-design.md` and `...-frontend-design.md`), mirroring the existing Phase 2/2b precedent. A full backend implementation plan was then written (`Docs/superpowers/plans/2026-08-14-multi-method-auth-backend-plan.md`, 11 TDD tasks: schema/migration, `EmailProvider`, generalized OTP service, `Session.auth_method`, identity/collision resolution, pending-verification/phone-gate completion, Google ID-token verification, request/response schemas, the two OTP routes, the Google OAuth route, and OTP request throttling). **As of this entry, the backend plan is written but not yet executed, and the frontend implementation plan is still being written** — no code from this feature has been merged yet.

## 2026-08-14 — Multi-method auth: frontend implementation plan also completed; five more open items resolved; documentation system established

Continuing straight on from the backend plan: a full frontend implementation plan was written (`Docs/superpowers/plans/2026-08-14-multi-method-auth-frontend-plan.md`, 10 TDD tasks — types/API client, `useOAuthScript`, `GoogleButton`, `EmailEntry`/`EmailOtpVerify`, `PhoneEntry` rework, `AuthShowcasePanel`, `Landing` redesign, `LinkAccountPrompt`, `AuthEntryFlow` orchestration, and a full integration-test rewrite), explicitly sequenced to depend on the backend plan's exact API shapes. Both plans are now complete and saved, but **neither has been executed** — no code from this feature exists yet.

Before the frontend plan was written, five more open items from the design specs were resolved by the user (see `decisions.md` for each with its "why"): email stays visible in the UI on the stub provider with Postmark now a firm pre-production prerequisite; Postmark confirmed over SES; the shared `pending_identity_verifications` TTL confirmed; the four pill buttons' order locked (Google, Apple, Email, Phone); and the right-side showcase panel's content confirmed as pending separate input from the product owner rather than a generic placeholder. Both design spec files were updated in place to reflect all of this.

Also this session: a standing documentation discipline was set up — `decisions.md`, `log.md`, `backend.md`, `database.md` created and backfilled with this project's full history (this file's own existence is part of that). A duplicate dispatch happened (a direct subagent call plus a `/subtask` harness fork both working the same task concurrently) but reconciled cleanly with no data loss, committed as `074d7e1` on `authsetup`. A CLAUDE.md "End-of-Session Documentation" section and a session.md addition were drafted but deliberately left for the user to merge manually, to avoid a race on those two files.

## 2026-08-14 — Multi-method auth backend: all 11 plan tasks executed via subagent-driven-development

Executed `Docs/superpowers/plans/2026-08-14-multi-method-auth-backend-plan.md` task-by-task on branch `authsetup`, per the user's explicit instruction (TDD per task, full suite before each commit, adversarial-review gate before marking any task done, stop-and-ask before touching anything outside the plan's scope). All 11 tasks completed and reviewed; one out-of-plan issue (3 CAS-import test fixtures still calling the old 2-arg `create_session` signature, surfaced by Task 9's removal of the old phone-lookup path) was raised to the user rather than decided unilaterally — user chose to fix immediately, done as a small approved addition (`6165403`). Full commit range and the two real bugs caught mid-plan (Task 6's non-atomic commit, Task 8's false-positive review) are recorded in `backend.md`.

The mandatory final whole-branch review (run once, after all 11 tasks, per the skill's process) found 2 Critical + 4 Important findings — all genuinely cross-task, none catchable by any single task's own review. Full detail in `backend.md`; the standout is that one of the two Criticals (missing backfill migration for pre-existing users) traces back to a gap in the *plan itself*, not an implementer mistake — the design spec had explicitly named this as required future work and it was never turned into a plan task. A fix wave covering all 6 findings was dispatched; the first attempt stalled mid-way (agent-runtime timeout, not a code defect — verified via `git log`/`git diff` that no partial/broken state had landed) and was picked up by a continuation agent instructed to independently re-verify the salvaged work before finishing the rest. The fix wave completed (commit `2784b61`), and the mandatory scoped re-review that followed it (per the skill's "no second fix wave" rule) came back CLEAN — all 6 findings confirmed genuinely closed by an independent reviewer tracing the actual diff, not the fix-wave's self-report. See `backend.md`'s 2026-08-14 "fix wave complete" entry for the full detail, including 4 new Minor findings the re-review surfaced in the fix-wave diff itself, all ruled non-load-bearing and parked (not fixed) per process. **The backend implementation plan is now fully complete**: 11 tasks, 1 out-of-plan fixture fix, and the final review's 2 Critical + 4 Important findings, all fixed and independently verified. Backend suite: 441 passed, 2 skipped, 0 failed, 0 errors. The SDD workspace for this plan (`.superpowers/sdd/2026-08-14-multi-method-auth-backend-plan/`) has been deleted per the skill's Finish step, having served its purpose as the execution ledger. The companion frontend implementation plan (`Docs/superpowers/plans/2026-08-14-multi-method-auth-frontend-plan.md`, 10 tasks) remains completely unexecuted — not started, not requested for this session.

## 2026-08-15 through 2026-08-17 — Multi-method auth frontend: all 10 plan tasks executed, plan now fully complete

Executed the frontend plan task-by-task via `superpowers:subagent-driven-development`, mirroring the backend plan's discipline. Confirmed branch (`authsetup`), re-confirmed the prior session's email-OTP-stub-mode finding still held (no backend commits had touched it), corrected a pill-order transcription error in the plan itself (`decisions.md`), and resolved a hard-stop-checkpoint mismatch directly with the user — their stated "OAuth redirect flow" concern didn't apply (the design deliberately avoids a redirect via Google Identity Services' popup/token flow), so the checkpoint moved to Task 9 (`AuthEntryFlow` orchestration) instead.

All 10 tasks completed and reviewed, each independently verified by the controller against the actual diff (not just implementer/reviewer self-reports) at every step — a discipline that caught two real things a self-report alone would have missed: a `devOtp`-clearing regression Task 9's own first fix round introduced (caught via direct code reading before dispatching re-review, fixed in a second round), and Task 1's implementer correctly identifying and fixing a genuine defect in the plan's own Task 2 test-spec (a URL-reuse bug that would have made the brief's own literal test code fail). One out-of-plan issue (`App.test.tsx`, never mentioned in the plan, asserting on Landing's old removed "Sign Up" button) was raised to the user rather than decided unilaterally — user chose to fix immediately.

The mandatory final whole-branch review found 1 Critical + 6 Important findings — the Critical (Google sign-in failures completely invisible to the user — `Landing.tsx` had no `error`/`submitting` props to render what `AuthEntryFlow`'s Google handler already set) is the standout: neither Task 3 nor Task 7 could have caught it in isolation, since both were individually correct against their own briefs — only the merged wiring exposed the gap, because the design spec's explicit requirement for GoogleButton to own error/loading state was silently dropped when the plan's task briefs were written. A fix wave addressed all 9 findings (1 Critical, 6 Important, 2 selected Minor) in one commit, and — as a genuinely valuable side effect of needing its own verification to pass — found and fixed a real environment bug that had been causing this whole session's "transient" vitest worker-timeout flakiness (see `decisions.md`'s 2026-08-17 entry). Mid-fix-wave, the user tested the actual dev server in their own browser and explicitly rejected one specific piece of the fix (a visible "not configured" banner for missing Google client ID) — honored directly as a targeted follow-up revert, re-verified, without touching anything else from the fix wave. The final scoped re-review confirmed all 9 findings genuinely addressed (including the deliberate reversal), with only 3 cosmetic stale-comment items parked. **Full frontend suite: 219 passed, 0 failed, 0 skipped, tsc clean, production build clean.** Live browser visual verification remains an honestly-flagged gap in this sandbox (no Chrome/sudo available) — though the user's own direct browser testing during the fix-wave feedback loop is real, if partial, signal that the actual rendered UI works.

## 2026-08-17 — Email+password auth: backend and frontend implementation plans fully completed (Superseded)

Completed the transition from email-OTP to email+password authentication across both backend and frontend on branch `authsetup`.
*(Superseded by 2026-08-17/18 password removal below).*

## 2026-08-17/18 — Password Auth Removal & Pure Email-OTP Flow Restoration

Executed password removal across backend and frontend per management decision:
- Applied migrations `0007_email_otp_signup` and `0008_remove_password_auth`.
- Restored pure OTP-based email signup and login (`POST /auth/signup/email`, `POST /auth/email-otp/request`, `POST /auth/email-otp/verify`).
- Removed all password fields and token tables from the backend and frontend forms.
- Re-verified full test suites: backend 449 passed/2 skipped; frontend 218 passed across 52 test files.

## 2026-08-19 — Left Auth Panel Motion, Auth Validation Engine, and Hand-Drawn Hero Illustrations Integration

Executed comprehensive visual, motion, validation, and illustration enhancements:
1. **Left Auth Showcase Panel Redesign (`AuthShowcasePanel.tsx`)**:
   - Built a 3D dark slate screen card on a near-black radial background with diamond grid.
   - Designed one deliberate continuous trajectory drawing smoothly along its actual SVG path from chaotic waveform to structured compounding.
   - Added `hasAnimatedInSession` session persistence flag ensuring the animation plays exactly once per load and never restarts across step changes.
   - Replaced automated cycling statistics with cursor-hover milestone tooltips (`+14.8%`, `+28.4%`, `+41.2%`, `+56.8%`).
   - Added JSDOM guards for SVG path measurement methods to ensure test suite robustness.

2. **CORS Multi-Port Dev Support (`backend/app/main.py`)**:
   - Added `allow_origin_regex` to CORSMiddleware supporting ports 5173, 5174, 5175, and 3000.
   - Automated tests added to `backend/tests/test_health.py`.

3. **Comprehensive Auth Validation Engine (`validation.ts`, `validation.test.ts`)**:
   - Built email validator with structural rules, extension prompts, and intelligent typo suggestions (e.g. `gmial.com` -> `"Did you mean name@gmail.com?"`) without silent modification.
   - Built Indian mobile phone validator with 10-digit requirements, valid starting digits (`6-9`), non-digit rejection, and canonical normalization (`+91XXXXXXXXXX`).
   - Wired live dynamic error recovery on blur and submit in `Landing.tsx`, `EmailEntry.tsx`, `PhoneEntry.tsx`, `OtpVerify.tsx`, and `AuthEntryFlow.tsx`.
   - Comprehensive test suite: 30/30 unit tests passed in `validation.test.ts`.

4. **Hand-Drawn Hero Illustrations & Option Cards Integration**:
   - Extracted 5 distinct illustrations from the user's illustration sheet into transparent high-resolution PNGs with subtle Unifolio green accents (`#22C55E` / `#16A34A`), with both light mode (charcoal linework) and dark mode (luminous silver) assets.
   - Integrated into `OnboardingIllustration.tsx` with light/dark theme switching and ambient emerald radial depth glow.
   - Replaced generic Lucide icons in `Q4Household.tsx` (Just Me, Family Too) and `TrustPrimer.tsx` (Read-only access, No raw CAS PDF storage) with matching bespoke hand-drawn SVGs.

5. **Full Verification**:
   - All unit tests and integration tests passing (`30/30` validation, `15/15` auth entry flow, `6/6` onboarding flow).
   - Backend suite: 449 passed, 2 skipped, 0 failed.
   - Production bundle build: `npm run build` clean (0 errors).

## 2026-08-27 — Mobile Review Scroll Fixes, Roadmap Milestone Unlock Animations & CTA Centering Audit

1. **Mobile CAS Import Review Scroll & Viewport Overflow Fixes (`ReviewTable.tsx`, `App.tsx`, `OnboardingFlow.tsx`)**:
   - Resolved mobile viewport vertical overflow trap: removed `overflow-hidden` from `MobileInitialFlow` in `App.tsx`, enabled `overflow-y-auto`, and top-aligned the onboarding step containers in `OnboardingFlow.tsx`.
   - Refined mobile layout for `ReviewTable.tsx`: hidden the statement verified badge on mobile, converted the filter row into a 3-column grid without horizontal scrollbars, tightened card padding and typography, and added `pb-28 sm:pb-24` bottom clearance for sticky footer visibility.

2. **Mobile & Web Import Screens Vertical Centering & Upload Refinements (`UploadForm.tsx`, `MobileUploadForm.tsx`, `TwoPathImportContainer.tsx`, `ParsingIndicator.tsx`, `ImportConfirmed.tsx`, `ImportFlow.tsx`, `MobileImportView.tsx`)**:
   - Vertically centered the Upload Screen on both web and mobile layouts.
   - Enlarged the hero illustration on the upload statement screen (`w-24 h-24 sm:w-28 sm:h-28`) and removed the PAN/DOB password hint line.
   - Vertically centered the CAS Processing Indicator screen on both web and mobile.
   - Vertically centered the Import Complete screen on both web and mobile.
   - Vertically centered the Import Choice screen while keeping top navigation anchored.

3. **Roadmap Milestone Sequential Activation & Pop/Glow Animations (`MobileAuthBackground.tsx` / `AuthRoadmapSvg`)**:
   - Updated authentication roadmap milestone behavior across both mobile and web:
     - Icons remain muted/light (`opacity: 0.4`) before the traveler marker arrives.
     - Animate with a subtle pop/lift effect (`scale: [1, 1.14, 1]`, `y: [0, -1.8, 0]`) as the marker reaches each step sequentially.
     - Unlocks with a soft radiant `#milestone-unlock-glow` radial gradient aura.
     - Persists in a dark, active state (`opacity: 1.0`, bold stroke styling, vivid green accents) after unlock.

4. **UI Consistency & CTA Centering Audit**:
   - Audited all action buttons, CTAs, and controls across mobile and web flows.
   - Fixed asymmetric left offset in `MobileOnboardingScreen.tsx` by eliminating empty placeholder spacers when `onSkip` is absent and applying `w-full` directly.
   - Enforced explicit flex centering wrappers (`w-full flex justify-center items-center`) and `mx-auto` alignment on `ImportConfirmed.tsx`, `ImportError.tsx`, `MobileImportView.tsx`, and `EmptyState.tsx`.

5. **Login Roadmap State Logic & 2-Milestone Flow (`MobileAuthBackground.tsx`, `AuthShell.tsx`, `AuthEntryFlow.tsx`, `mobileJourneyContext.tsx`)**:
   - Fixed roadmap milestone state management: explicitly decoupled login progression from page switching, route changing, or Sign-up/Login toggles.
   - Starting at Step 1 (`x: 36, y: 38`), clicking "Log in" from the Sign-up page switches to Login mode while keeping the marker rock solid at Step 1 (Milestone 1).
   - Selecting "Continue with Email" or "Continue with Phone" and typing credentials keeps the marker firmly at Step 1.
   - Transitioning to the OTP verification screen (`email_otp` or `otp`) moves the marker smoothly along the curved route to Step 2 (`x: 340, y: 22`), triggering the milestone pop/lift effect and `#milestone-unlock-glow`.
   - After successful OTP verification, navigates directly to the dashboard without adding further roadmap steps.
   - Added unit tests in `MobileAuthBackground.test.tsx`.

6. **Comprehensive Mobile Scrolling Fixes**:
   - Eliminated rigid `h-dvh max-h-dvh overflow-hidden` barriers across mobile containers (`MobileOnboardingScreen.tsx`, `App.tsx`, `MobileLandingPage.tsx`, `AuthShell.tsx`).
   - Implemented `min-h-dvh overflow-x-hidden overflow-y-auto` enabling smooth vertical scrolling on all question screens (Q1 Name, Q2 Investing, Q3 Purpose, Q4 Household, Trust Primer, Add Family Members) on compact viewports.
   - Pinned mobile onboarding footers with `sticky bottom-0 backdrop-blur-sm z-30` ensuring CTAs are never obscured or pushed out of reach.
   - Added `flex-1 min-h-0 overflow-y-auto pb-16` on `MobileDistributorComparisonView.tsx` and increased `pb-28 sm:pb-32` on `MobileReviewView.tsx`.
   - Verified zero impact on the desktop web application.

7. **Full Verification**:
   - Frontend test suite: 75 test files passed, 381 tests passed (100% green).
   - Zero regressions across desktop and mobile test suites.

## 2026-08-24 — AMFI TER concurrency lowered to avoid a 429; Analytics PDF export Allocation section fixed

Two small, independent post-merge fixes on `feat/enhanced-ui`, both direct (no Codex dispatch): (1) `_TER_FETCH_CONCURRENCY` lowered 20→5 (`bb9f507`) after live-verifying AMFI's TER-page endpoint does rate-limit at 20 concurrent requests, tripping a 429 that left `scheme_ter` empty for the full 15-minute backoff window; no retry-on-429 added since the existing 15-minute backoff already retries on the next request. (2) Analytics PDF export's Portfolio Allocation section (`12946f7`) — the SEBI Category donut rendered as a barely-visible sliver and the AMC breakdown never appeared at all. Two root causes: `AllocationSection.tsx`'s Category/AMC toggle was pure React click state, so Playwright's static capture only ever saw the default tab (same bug class as `BenchmarkSection.tsx`'s tab toggle, fixed earlier in the PDF-export plan); and `PieSlice.tsx`'s spring-animated draw-in meant `page.pdf()` fired mid-animation. Fixed by giving `AllocationSection` the same `printMode` prop pattern as `BenchmarkSection` (stacks both breakdowns instead of tab-switching) plus a new `animate` prop threaded to `PieSlice` (already had a static render path, just never wired through). Full frontend suite: 335/335 across 72 files, `tsc -b --noEmit` clean.

## 2026-08-25/26 — AMFI TER `ReadTimeout`s root-caused to event-loop starvation, not AMFI slowness; `commit_off_loop` fix

A colleague's AMFI TER `ReadTimeout`s were initially stopgapped by raising the httpx client timeout 30s→90s (`945b271`), confirmed fixed live 2026-08-26. Root cause then properly fixed, not just worked around: this backend's SQLAlchemy engine is fully synchronous on a single worker/event loop, so any blocking `db.commit()` inside an `async def` handler stalls every concurrent request, not just the slow one. `bb5225f` added `commit_off_loop` (routes `db.commit()` through `asyncio.to_thread`) and rewired every reachable commit across all 8 affected service files, with a regression test proving a slow commit no longer starves the loop.

## 2026-09-02 — AWS staging prep: compliance-audit remediation Group 1, three F-items authorized outside it

Worked `AWS Readiness/sqlite-postgres-migration-compliance-audit.md` down to zero pre-staging gaps. Two prior Codex-implemented pieces (OTP stub-mode guard, Dockerfile/CORS/upload-validation hardening, and the enum-drift migration `0010`) independently re-verified, not trusted from self-report. Group 1 (no product decision needed, done directly since Codex was usage-limited): F6 (Postgres `ON CONFLICT DO NOTHING` NAV-upsert path got real Postgres test coverage, plus a dialect-branch→dict-lookup refactor), F9 (`amfi_aaum_client.py`'s last stray bare `db.commit()` routed through `commit_off_loop`), F10 (`folios.coverage_gap_details` migration aligned to the ORM's portable JSON/JSONB idiom), F5 (`Database-Schema-Unifolio.md` refreshed to v1.4 for migrations 0003/0007-0010). Also authorized outside Group 1: F7 (`compute_holdings`'s per-folio N+1 query batched into one query across all folios) and F3 (migration `0011` — partial unique index on `household_members(user_id) WHERE relationship='self'`, plus a `DuplicateSelfMemberError` 409 guard; a read-only check found zero existing violations first). Handoff docs written and dispatched to Codex for F4 (ADR-006's 4 job-entrypoint scripts), F8 (NAV-unavailable degraded row), and a non-PAN duplicate-person-detection design (folio+AMC signal for same-user dedup, an advisory-only cross-user check) — see `decisions.md` for the resolved product calls behind each. Single-ECS-task/no-Redis deferral for staging explicitly confirmed, documented in `AWS Readiness/aws-golive-launch-blockers.md`.

## 2026-09-03 — F4, F8, non-PAN-dedup all implemented and cleared review

F4 piece (a): 4 job-entrypoint scripts + `amfi_aaum_client.refresh_aaum_data` wiring, adversarial-review gate cleared (piece (b), the actual EventBridge/ECS Terraform, stays deferred until an AWS account exists). F8: NAV-unavailable degraded row shipped across 2 review rounds (round 2 caught `gainPercentage` mixing valued/unvalued populations, fixed with a `valuedInvestedVal` denominator). Non-PAN dedup round 2 wired the round-1 design into both parallel import backends (`service.py`'s confirm flow and `lifecycle_service.py`'s async CAS-upload flow) via a shared `enforce_attribution_confirmation` gate and a structured `member_mismatch` 409 — surfaced a standalone architectural gap (the two backends needing the identical fix wired in twice), documented at `Docs/orchestration/two-parallel-import-backends-architectural-gap.md`. Backend 614 passed/1 skipped, frontend 397/75 files, both independently re-verified by the orchestrator rather than trusting the reviewer's own unreproduced test claim.

## 2026-09-07 — AWS account + domain cutover; documentation cleanup before Terraform

AWS account created (root MFA, budget alert, IAM admin user `ayush-admim`), region `ap-south-1`, `unifolio.in` cut over from GoDaddy to a Route 53 public hosted zone (existing M365 mail records preserved, GoDaddy-proprietary records dropped). Domain architecture decided: `unifolio.in` apex = marketing site, `app.unifolio.in` = production app, `staging.unifolio.in` = staging app; staging networking decided as self-hosted fck-nat over a managed NAT Gateway to skip the cost-approval step. Before starting Terraform, independently re-verified (not trusted from self-report) that 2026-09-03's work was actually committed (`9fe21fe`) and that every blocker `aws-golive-launch-blockers.md` still listed as open was actually already fixed in code — that doc was stale, not the code.

## 2026-09-08/09 — Terraform Phases 1-3 applied to real AWS; staging infra live end-to-end

AWS CLI/Terraform installed, state backend bootstrapped (S3 + DynamoDB lock table), `terraform apply` succeeded: 57 resources created (VPC, fck-nat + SSM bastion, KMS CMK, RDS Postgres 16, ECR, ECS cluster/service, ALB). Two expected follow-ups both resolved same session: ECS was crash-looping with no image in ECR (built/pushed/force-redeployed from local WSL, after working around a `backend/.pytest_tmp` permission artifact blocking Docker's build-context walk — `sudo rm -rf` was the only thing that removed it, a 9p/drvfs quirk of `/mnt/d`); the DB schema didn't exist yet (applied via an SSM port-forward through the bastion, `alembic upgrade head` confirmed `0011` on real RDS). A real AWS credential was briefly pasted into chat and one committed copy caught by GitHub push protection — rotated and the offending commit rewritten before it ever left the machine. Phase 4 (frontend S3+CloudFront) Terraform authored and reviewed clean by Codex, not yet applied; Phase 5 (ACM/Route 53/ALB HTTPS/CloudFront domain) handoff drafted, gated on Phase 4 being applied first.

## 2026-09-10 — Analytics frontend precompute migration complete

Both desktop (`AnalyticsView.tsx`) and mobile (`MobileAnalyticsView.tsx`) migrated onto a single `useAnalyticsScope` hook consuming `GET /analytics/{scope}`, replacing the deleted 14 per-section analytics client functions, with cold-start/recompute polling and whole-scope retry UI. `tsc -b --noEmit` clean, 76 files/412 tests.

## 2026-09-11 — Investor 10-item feature batch committed; AWS staging prerequisites doc drafted

Profile page, account deletion (5-day grace period + exit survey + household cascade), email/phone change via OTP, theme toggle, import history + delete-import, Dashboard header XIRR, allocation sort toggle, AMC/asset-class drill-down modal, decimal-formatting consistency — 3 rounds of implementation + review (Round 1 → 8 Round-2 findings → 5 Round-3 findings) plus a same-session PM/tech-lead gap pass (3 more fixes). Round-3 and PM-gap fixes were done directly by the orchestrator (Codex usage-limited) — the mandatory adversarial-review gate for both was explicitly deferred, not run, a real flagged gap. Backend 649/8 skipped, frontend 437/79 files, `tsc` clean, all committed to `feat/enhanced-ui` (had sat uncommitted since implementation). AWS staging runbook drafted (`Docs/superpowers/plans/2026-09-11-aws-staging-prerequisites.md`) — every command explicitly for the user to run themselves.

## 2026-09-12 — Fund Score card redesign

Score out of 10 (display-only, backend still stores raw 0-100), reversed 1=best tier convention, plain-English Strengths/Watch-outs verdicts, expandable evidence/methodology sections. Built via `subagent-driven-development`, 9 tasks, no Codex. Final whole-branch review: 1 Critical + 5 Important + 9 Minor, all fixed; a scoped re-review of one fix caught a bug the fix itself introduced (duplicate accordion ids across multiple cards on one page). Two real spec-vs-plan deviations (a dropped tier progress bar, a computed verdict word never rendered) flagged to the user per CLAUDE.md rather than silently resolved — user chose to restore both. Backend 650/8 skipped, frontend 454/80 files, `tsc` clean. Precompute-cache backfill for the new fields explicitly deferred to the AWS/deployment phase (needs live ADR-006 infra).

## 2026-09-16 — Knowledge-graph refresh, codebase-analysis metadata added

`.ua/knowledge-graph.json` and related fingerprint/analysis metadata refreshed via `/understand` to match HEAD at the time (commit `05463e1`). Superseded again by subsequent commits — re-run before trusting it, per `CLAUDE.md`'s own note.

## 2026-09-17 — Real email-OTP delivery (Postmark), independent per-channel delivery mode; docs-viewer infra; audit/architecture doc batch

`PostmarkEmailProvider` added as the first real (non-stub) `EmailProvider` implementation (`e991646`); `email_delivery_mode` split out as its own setting independent of phone/SMS's `otp_delivery_mode` (`508fbbc`/`d0b8b3d`), with an autouse test fixture guarding every test against accidentally picking up a live local `.env` delivery mode. A large documentation batch landed: orchestration audits, backend audit report, AWS technical-architecture-flow doc, AWS go-live readiness report and launch-blockers doc, an AI-agent model-selection research note, and the SQLite→Postgres compliance audit. Separately, `docs.unifolio.in` shipped (`5a24d96`) — a static S3+CloudFront deploy of the knowledge-graph dashboard, isolated from `staging.unifolio.in` (own bucket/distribution/ACM cert/DNS record), gated by a CloudFront Function token check on `*.json` requests to keep cost near zero.

## 2026-09-18 — ADR-004 reopened: PAN persisted (encrypted), CAS PDF retained 30 days

Supersedes the original 2026-07-22 "no PAN, no raw file, ever" decision — see `decisions.md`. Migration `0015` adds `household_members.pan_encrypted`/`pan_lookup_hash` (AES-256-GCM envelope encryption + HMAC-SHA256 deterministic lookup hash) and `imports.file_reference`/`file_expires_at`; local CAS file storage with a 30-day expiry sweep (manual CLI entry point) added. `attribution.py` rewritten to match by PAN first (auto-attribute within the same household, hard-block a PAN already claimed by a different account via `CrossAccountPanBlockedError`), falling back to folio+AMC matching when the CAS has no PAN, with `backfill_pan_if_missing()` capturing PAN on first successful match. A review-fix made the PAN lookup index `UNIQUE` (was a TOCTOU race — two concurrent imports of the same PAN under different accounts could both see "no match"). `TrustPrimer` onboarding copy and `parser.py`'s stale "PAN never persisted" comments corrected to match. `tests/models/test_no_pan_field.py`'s guard broadened, not deleted, to cover every mapped model against the *new* rule (PAN only ever in the two named encrypted/hashed columns). `Database-Schema-Unifolio.md` and PRD-01 synced.

## 2026-09-19 — Cross-account PAN block surfaced as a UI popup; CAS S3 storage + Postmark infra Terraform; PAN/CAS/secrets technical docs

Frontend: a cross-account PAN block previously froze the Family upload flow with no explanation — now surfaces as an explicit "Import blocked" popup (`6de6ea7`). `tasks` branch merged into `feat/enhanced-ui`. Real infra commit (`2c360df`): `infra/modules/storage/` (CAS-files S3 bucket, private, SSE-KMS, lifecycle expiry), Postmark secrets in Secrets Manager, and the scheduled file-expiry job's Terraform wiring — all authored, not yet applied (no `.tfstate` for this environment existed at the time). Technical documentation trio added: PAN persistence/CAS-storage design summary, PAN-CAS attribution feature doc, Postmark email-OTP technical doc.

## 2026-09-22 — Phone-gate collision fix; SES email provider added behind existing abstraction; marketing-site Terraform

Bug fix (`c8a4a8e`/`31e112a`): signup's mandatory phone gate previously called `attach_pending_identity` unconditionally on any phone match, silently signing the caller into an unrelated existing account (stale email visible in Profile) instead of erroring like `signup_email` already does for a duplicate email. Now mirrors email's 409 "already exists — log in instead," the check moved from `otp/verify` to `otp/request` so it surfaces before the caller even types a code, and the already-exists alert got a clickable "Log in instead" shortcut on both channels. Separately: `SesEmailProvider` added behind the existing `EmailProvider` protocol (IAM-role auth via `boto3`, no new secret/token store, matching the codebase's existing AWS SDK usage pattern) — both Postmark and SES now raise a shared `EmailSendError` on failure, caught once per route and turned into a clean `502` instead of an unhandled `500`; an OTP request is no longer persisted if the send itself fails. `infra/envs/marketing/` Terraform + a new opt-in `cloudfront_function_arn` variable on the shared frontend module added for the marketing site. SES cutover + full Postmark removal planned in detail (`Docs/superpowers/plans/2026-09-22-ses-cutover-and-postmark-removal.md`) but explicitly gated — "do not implement/deploy until told to."

## 2026-09-23 — Postmark fully removed (code + Terraform), SES-only; QA schema/journey review; HTML OTP email templates

Postmark provider class, Terraform secrets/variables, and DNS all removed rather than kept dormant (deliberate simplicity choice — dormant cost would've been $0, not a cost-driven call). SES cutover execution guide written. Separately: a schema & user-journey review was written up in response to a QA investigation into signup/CAS-import behavior. Responsive HTML email templates added for both the email-OTP-verification and email-OTP-signup emails, with unit tests.

## 2026-09-24 — PAN check moved to upload time; Confirm Import never prompts; per-PAN statement-splitting drafted (not built)

Fixed a staging bug where every first import on a fresh account showed "we couldn't match this statement to an existing family member" and froze the Family flow — root cause: PAN-based attribution ran at Confirm, but a member's PAN was only ever stored *after* a confirm, so nothing could match on a first import. New `backend/app/services/import_/pan_claims.py` replaces `attribution.py`: `/imports/parse` now claims the parsed PAN for the uploading member as *pending* (`household_members.pan_pending_until`, migration `0016`), with conflicts (409s) returned right after upload instead of at Confirm; `/imports/confirm` only finalizes, no prompts; a new `POST /imports/sessions/{id}/discard` releases an abandoned claim. Frontend: all "Continue anyway / Switch to" UI removed in favor of upfront blocked-import popups. Final review (fresh reviewer): 3 Important fixed (claim moved after mfapi enrichment so SQLite's write lock isn't held across a network call; a Back button on Family's re-upload form; a lost unique-index race now retries instead of 500ing), 7 minors deferred. Backend 714/8 skipped, frontend 484 across 82 files, `tsc` clean. Cosmetic OTP-email desktop-alignment fix landed same day. A follow-on gap was identified and drafted as a plan, **not implemented**: a family CAS statement covering several people only ever reads the *first* folio's PAN (`casparser` exposes PAN per-folio, but folios carry no holder name) — everyone else's funds silently land under that one member. Plan: `Docs/superpowers/plans/2026-09-24-per-pan-statement-splitting.md` (status: draft, no code written).

