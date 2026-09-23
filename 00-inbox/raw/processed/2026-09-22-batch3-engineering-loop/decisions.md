# Decisions Log

> Append-only, dated log of every decision made on this project — product, UX, and technical. Distinct from `Docs/PRDs/ADR-Technical-Stack-Decisions.md`, which stays reserved for big formal architecture decisions with full alternatives-considered writeups; this file covers everything else, and links to an ADR by reference rather than restating it once a decision graduates to one. Never trim or rewrite past entries — append corrections/reversals as new dated entries instead.

## 2026-07-22 — Core technical stack (ADR-001–006)

React SPA/Vite (not Next.js, no micro-frontends), FastAPI (not Django), AWS RDS Postgres, scoped S3 (no raw CAS PDF retention), ECS Express Mode, EventBridge Scheduler + Fargate `RunTask` for background jobs. **Why:** see `Docs/PRDs/ADR-Technical-Stack-Decisions.md` for full alternatives-considered reasoning — not restated here.

## 2026-07-22 — No raw CAS PDF storage, no PAN persistence

Final, non-negotiable per ADR-004 and the Database Schema doc. **Why:** minimizes stored PII, cleaner DPDP-Act compliance posture; the platform's value is structured data/analytics, not document custody.

## 2026-08-04/05 — Phone + OTP is the sole signup/login method (original, later revised)

PRD-02 FR-2: phone+OTP only, no password, ever. **Why:** matches the dominant Indian fintech pattern (Groww/INDmoney), removes the single biggest documented onboarding-drop-off source. **Superseded 2026-08-14** — see the multi-method-auth entries below; phone remains the universal anchor but is no longer the *only* entry method.

## 2026-08-05 — Sign Up / Log In landing screen ahead of phone entry (PRD-02 FR-2b)

Both buttons lead to the identical phone+OTP flow — framing only, not two auth mechanisms. **Why:** first-time and returning users see language matching their actual situation, at zero backend cost since new-vs-existing was already handled transparently. **Superseded 2026-08-14** for the entry screen specifically — see multi-method-auth entries.

## 2026-08-05 — Family CAS Upload: queue-then-batch-parse, not parse-on-upload (PRD-02 FR-10–14)

Each family member gets an independent upload card; a single "Parse Files" button parses every queued file, rather than parsing the instant each file is chosen. **Why:** parsing on upload would interrupt the person mid-upload-flow for every other member once more than one file is in play.

## 2026-08-06 — Transaction dedupe key widened to include `type`

`(folio_id, date, amount, units, type)`, up from a 4-column key. **Why:** a same-day purchase and redemption of equal magnitude collided under the old key once both were normalized to positive magnitudes — a real bug, not preemptive hardening. See `Docs/superpowers/specs/2026-08-06-transaction-dedupe-type-migration-design.md`.

## 2026-08-10 — Category-ranking blend weights: 40/60 (3yr/5yr), Morningstar-derived

PRD-04's Resolved Open Questions fixed the blend *inputs* but not the blend *weights*. **Why:** adopted Morningstar's published 3/5/10yr weighting (20/30/50), renormalized without the unused 10yr leg, since no in-house weighting had been specified. Flagged in-code per CLAUDE.md's "stop and say so" rather than silently assumed.

## 2026-08-10 — Benchmark mapping: 4 indices, substring-match fallback to Nifty 500

Every SEBI category not matching "LARGE"/"MID" substrings (Flexi/Multi/Small Cap, Sectoral, Debt, Hybrid, etc.) falls back to Nifty 500 as the broad-market default; no fund is ever excluded from comparison. **Why:** only 4 benchmark indices exist in scope (PRD-04), so every category needs *some* mapping rather than a gap.

## 2026-08-10 — AMFI TER fuzzy-match threshold: 0.55, not `enrich.py`'s existing 0.92

**Why:** local scheme names carry a "- Direct/Regular Plan - Growth" suffix AMFI's plan-generic `Scheme_Name` never has, capping a genuine match's ratio around 0.67 — 0.92 would reject real matches. 0.55 was chosen with a comfortable margin verified live against both a real match (~0.67) and an unrelated pair (~0.26).

## 2026-08-13 — Scorer weighting: Return 45% / Risk 30% / Consistency 25%, fixed

Chosen over Morningstar's 3/5/10yr-CAGR-weighted approach. **Why:** Ayush's one hard product requirement for Analytics — the score must be genuinely Unifolio's own, not a re-skin of Morningstar/CRISIL/PowerUp. Keeps risk isolated as its own ingredient (not folded into a risk-adjusted return) and makes consistency a first-class graded ingredient. Full stakeholder-facing rationale: `Docs/Scorer-Methodology-Unifolio.md`.

## 2026-08-13/14 — Dashboard NAV-cache race (Fix D, round 4): accept the remaining limitation, no round 5

No per-key single-flight coordination — two concurrent requests on a cold/expired cache key can both run a full independent computation (no stale data, just an occasional redundant one). **Why:** explicit user decision — no longer a correctness bug, and the real long-term fix is the deferred Fix C (ADR-006's scheduled NAV refresh job), not a more elaborate process-local cache. Documented in `holdings.py`'s cache-scope comment.

## 2026-08-12 — Model-orchestration skill: Claude as orchestrator, Codex as default worker

**Why:** delegate ~90%+ of implementation/refactor/boilerplate work to Codex while Claude Code retains architecture, multi-file interface design, complex debugging, and final assembly — plus a mandatory per-task handoff doc and adversarial-review gate before any Codex-implemented change counts as done. Full design: `Docs/superpowers/specs/2026-08-12-model-orchestration-skill-design.md`.

## 2026-08-14 — Multi-method auth: phone is the universal identity anchor, no exceptions

Every account converges on a verified phone number regardless of which method (Google, email, or phone) it started with. **Why:** reverses this same design effort's own earlier draft (which made phone fully optional to match "equal entry points" literally) — enforced structurally via a new `pending_identity_verifications` table and a `phone_required` API response, not a boolean flag, so an incomplete account is impossible to create rather than merely discouraged. See `Docs/superpowers/specs/2026-08-14-multi-method-auth-design.md` §1.

## 2026-08-14 — Multi-method auth: identity precedence is Google > Email > Phone

Applied wherever only one identity can be shown or selected — populating the denormalized `users.email` field, and which method a step-up account-linking prompt names. **Why:** needed a deterministic rule once an account can hold more than one verified identity; Google/email are richer/more recently-asserted signals than the baseline phone anchor.

## 2026-08-14 — Multi-method auth: account-linking is step-up re-auth, never silent auto-merge on an unverified email match

Auto-link only when both sides are independently verified; otherwise require re-authenticating via the existing account's own method before attaching a new identity. **Why:** an unverified `users.email` field proves nothing about who actually controls that mailbox — auto-linking against it would let anyone who happens to own that address take over an existing account's financial data.

## 2026-08-14 — Multi-method auth: `EmailProvider` abstraction now, Postmark wiring later

A `send_email(to, subject, body)` protocol ships with only a `StubEmailProvider` implementation; Postmark is the confirmed eventual choice but is not wired up in this pass. **Why:** mirrors this codebase's own existing precedent of deferring real SMS delivery for phone OTP the same way — keeps the architecture ready for a real provider (one new class + a config flip) without building it before it's needed. Real implication surfaced, not hidden: email-as-a-method won't function once this feature reaches Postgres/production until Postmark actually lands — a firm prerequisite for that deploy, not an open-ended "someday."

## 2026-08-14 — Multi-method auth: Sign in with Apple deferred to Future Scope

**Why:** the one method with a real recurring paid prerequisite (a $99/year Apple Developer Program membership, required regardless of App Store distribution) — the product decision was to confirm that cost is worth it separately rather than bundle it into this build. A disabled "Coming soon" placeholder button ships now on the frontend to reserve its UI slot.

## 2026-08-14 — Multi-method auth schema/migration design confirmed compliant with the Migration Plan guardrails

Checked against `Docs/PRDs/Migration-Plan-SQLite-to-Postgres.md`: all new tables/columns go through Alembic (never hand-edited DDL), all new queries are ORM-only (no dialect-specific raw SQL), and the design introduces zero JSON/JSONB columns. **Why:** this is the first new schema surface designed since that guardrail doc was written — confirming compliance explicitly rather than assuming it, per the doc's own "no file is allowed to go stale" spirit.

## 2026-08-06 — A held scheme with no obtainable NAV silently drops from the dashboard

Phase 3 design choice: excluded from holdings/allocation/aggregates with no error or placeholder. **Why:** no "NAV unavailable" UI treatment had been designed at the time; silently dropping was judged less confusing than a broken row. **Still open** — carried forward in every session-state update since, worth revisiting once a real treatment is decided.

## 2026-08-07 — Full independent review pass required before merging any agent-authored branch, not just a passing test suite

Google Antigravity's own report claimed full passing tests for the frontend redesign; actual state was 39/104 frontend tests failing plus 6 `tsc` errors. **Why:** never trust an agent's self-reported test status — root-caused and fixed every failure, distinguishing real app bugs (an accessibility regression, a `Decimal`-never-`float` violation on the dashboard's most visible number, a silent member-misattribution risk in "Add Data" re-entry) from tests merely stale after copy/behavior changes. This standard was later applied again to the intern's CAS import lifecycle work (see 2026-08-14 entry below) and formalized into the model-orchestration skill's adversarial-review gate (2026-08-12).

## 2026-08-07 — `impeccable` plugin untracked from git history, kept on disk

**Why:** keep it usable for whichever coding agent works in this checkout, without letting a vendored plugin drift stale against its own upstream update mechanism inside this app's own git history.

## 2026-08-10 — Analytics (PRD-04) backend build order fixed at 5 steps, Scorer last

Allocation → TER/AAUM → Benchmark → Category Ranking → Scorer. **Why:** each step's dependencies become explicit (Scorer depends on the outputs of TER/AAUM, Benchmark, and Ranking) and each step ships independently testable/committable rather than as one monolithic change. See `Docs/superpowers/plans/2026-08-10-phase-4-analytics-backend-design.md`.

## 2026-08-10/11 — FR-10's "AUM-weighted" TER clarified to mean holding-value-weighted, not platform AAUM

**Why:** PRD-04's own text reads ambiguously; resolved during design research that the weighted TER should reflect the *user's own* holding value per scheme, not the fund's platform-wide AAUM (the service never reads `scheme_aaum` as a result). Flagged in-code per CLAUDE.md's "stop and say so" rather than silently picked either way.

## 2026-08-10/11 — Benchmark-hypothetical XIRR replays real cash flows against the index, transaction-by-transaction

Purchases buy hypothetical index units at that day's index level, redemptions sell that many units; only the terminal value differs. **Why:** flagged in-code as a judgment call not fully spelled out by PRD-04 — chosen over a simplified single-cash-flow approximation to keep the benchmark comparison faithful to the portfolio's actual cash-flow timing.

## 2026-08-13 — Scorer's full FR-7 breakdown is never persisted

Recomputed fresh on every read rather than stored alongside the daily `FundScore` row. **Why:** avoids creating a second source of truth that could drift from the persisted score. Global Constraint in the Scorer implementation plan.

## 2026-08-13 — Scorer tier boundaries are inclusive on the lower bound

`>=80` → tier 5 ... `>=20` → tier 2, else tier 1. **Why:** simple, consistent rule applied uniformly across all cutoffs rather than mixing inclusive/exclusive framing.

## 2026-08-13 — Fix C (real scheduled NAV refresh) stays deferred to deployment phase

Fix A/B/D are explicitly local-dev-first mitigations layered on on-demand NAV fetching, not "the fix." **Why:** the real fix is ADR-006's EventBridge Scheduler + ECS Express Mode recurring NAV-refresh job, which needs its own design pass (schedule cadence, partial-failure handling, bulk-vs-per-scheme fetch client) and isn't built until AWS deployment per the Migration Plan's Readiness Checklist — consistent with CLAUDE.md's "local development first" non-negotiable.

## 2026-08-14 — Branch reconciliation: discard in-progress local Badge/Select fix in favor of the intern's independently-landed equivalent

Ayush's explicit call once the intern (`aditishanbhag`) pushed commits fixing the same two problems (Badge `className` support, a broken Radix-`Select` test interaction) a partial local fix was already mid-flight on. **Why:** the intern's commits fixed both issues independently and correctly, using an equally valid but different `Select` test pattern — keeping two competing fixes for the same bug would only create merge noise with no benefit.

## 2026-08-14 — Intern-authored CAS import lifecycle redesign and UI foundation: "tests pass" is not "reviewed correct"

The 11-state CAS import lifecycle state machine, coverage-gap detection, opening-balance resolution, CAMS-portal mailback flow, and shadcn/Tailwind UI foundation all passed the full suite (357/2 backend, 190/190 frontend) but have had no independent Claude Code review pass. **Why:** explicitly refusing to equate passing tests with reviewed-correct against CLAUDE.md's non-negotiables (`Decimal`-never-`float`, no raw CAS PDF storage, no PAN persistence) — same standard set on 2026-08-07 — flagged as an open item requiring a dedicated review, specifically because this batch touches money/state-machine logic (opening balances, coverage gaps).

## 2026-08-14 — Multi-method auth: pill-button order locked — Google, Apple (disabled), Email, Phone

**Why:** explicit product decision, not derived from any convention (not alphabetical, not by expected usage frequency) — recorded so it isn't silently reshuffled later. Apple's slot stays reserved even while disabled, so the layout doesn't reflow once real Apple sign-in ships.

## 2026-08-14 — Multi-method auth: Postmark confirmed as the email provider (SES-vs-Postmark question closed)

**Why:** deliverability for a login-critical OTP outweighs Amazon SES's lower cost and AWS-infra alignment at this volume — settled definitively, not left as a recommendation. Wiring it up is still deferred (see the `EmailProvider`/Postmark-timing entry above), but *which* provider is no longer open.

## 2026-08-14 — Multi-method auth: email stays visible in the UI on the stub provider; Postmark becomes a firm pre-production prerequisite

**Why:** resolves an open question the design spec had explicitly flagged rather than silently picking an answer — email-as-a-method is never hidden from users, including in early dev, but `otp.py`'s existing stub-mode guard means it genuinely can't send real email once this feature runs against Postgres. Postmark wiring is therefore required before (or as part of) this feature's first Postgres/production deploy, not an open-ended "someday."

## 2026-08-14 — Multi-method auth: `pending_identity_verifications` uses one shared ~10-minute TTL for both triggers

**Why:** the phone-gate case (mid-signup, hunting for your phone) and the step-up-link case (re-authenticating an existing account) are arguably different UX situations, but a single shared window was chosen over two different values for simplicity — flagged as an open item in the design spec, explicitly resolved this way by the user rather than left to implementation-time guessing.

## 2026-08-14 — Multi-method auth: `Session.auth_method` built now, not deferred

**Why:** originally flagged as optional/deferrable in the design spec; the user asked for it to be added as a firm decision mid-session — it's a small addition and directly useful for recording which method actually completed a phone-gated signup (the completing method, not the originating Google/email identity).

## 2026-08-14 — Multi-method auth: email OTP delivery confirmed intentionally stubbed now, mirroring phone exactly — `NoEmailProviderConfiguredError` is not a reachable state today

Confirmed via direct code trace plus the existing (already-passing) test suite that no code change was needed here. Email OTP already runs through the same shared `otp_delivery_mode` setting phone uses (`config.py`, default `"stub"`, unset in `.env.example`), and in stub mode email's flow is architecturally identical to phone's: `otp.py`'s `if channel == "email" and settings.otp_delivery_mode != "stub":` guard is false whenever mode is `"stub"`, so `EmailProvider`/`StubEmailProvider` is never even called — the OTP is generated and stored exactly like phone's, and `raw_otp` is returned in the API response's `otp` field, the same mechanism phone has always used to surface a testable code to a developer (not a console log). `test_otp_request_accepts_email` and roughly 15 other route-level tests already exercise this against the app's real default config with zero monkeypatching, and already pass at 441/2.

**Why:** explicit user instruction — `NoEmailProviderConfiguredError`/its 503 mapping must not be a reachable state right now, only a genuine misconfiguration once real email delivery is deliberately turned on before Postmark is wired. Confirmed this is already true: the error path is only reachable by explicitly setting `OTP_DELIVERY_MODE` away from `"stub"` (exercised on purpose via monkeypatch in `test_otp_request_returns_503_when_no_email_provider_is_configured`), never by anything that happens during ordinary local development or testing.

**How to apply:** the frontend implementation plan needs **no special-case handling** for a 503 on `/auth/otp/request` under current conditions — a stubbed email OTP request is an ordinary, successful 200 response, structurally identical to phone's, so the plan's existing generic error-surfacing pattern already covers it correctly as-is. This only becomes a live concern the moment `OTP_DELIVERY_MODE` is deliberately switched to a real value as part of wiring up Postmark, which is its own separate, already-flagged future task (see the `EmailProvider`/Postmark-timing entries above) — not something to design defensively around now.

## 2026-08-14 — Multi-method auth: Critical Finding 2 (missing backfill migration) ruled a plan defect, not an implementation defect

**Why:** the design spec explicitly named a one-time backfill of existing `users` rows into `auth_identities` as required work, but scoped it as "planning-phase work, not built here" — and this was never actually converted into a task in the implementation plan. Recorded explicitly as a gap in the plan I authored, not an execution slip by any implementer, because attributing it correctly matters for how this project's history reads later: the per-task review process worked exactly as designed (every task matched its own brief), but a whole-branch review was still necessary to catch a hole in the plan's own coverage. **How to apply:** when a design spec defers something to "a later migration" or "future work" without naming the specific task that will do it, treat that as an open task-planning risk, not a settled deferral — cross-check the plan's task list explicitly names it before treating the plan as complete.

## 2026-08-14 — Multi-method auth: false-positive review findings must be verified against `git show`, not trusted from a truncated diff

**Why:** a task reviewer concluded `MeResponse` had been entirely deleted based on a `git diff -U10` hunk that merely fell outside the shown context window — not actual absence. Caught before a bogus fix round was dispatched, by checking `git show`/`wc -l` directly. **How to apply:** any review finding of the shape "X was removed / never existed" gets a direct existence check (`git show <commit>:<path>`, or `grep`) before it's treated as real, regardless of how confident the reviewer's diff-based reasoning sounds.

## 2026-08-15 — Multi-method auth frontend plan: pill-order transcription error corrected in the plan itself, not just flagged

The frontend implementation plan's own Global Constraints line read "Email, Phone, Google, Apple," contradicting the Goal line two lines above it, Task 7's JSX comment, Task 10's ordering test, and this file's 2026-08-14 pill-order entry — all four of which already agreed on "Google, Apple (disabled), Email, Phone." **Why:** flagged during the pre-flight conflict scan required before Task 1; rather than leave the contradiction sitting in the plan for a future reader to trip over, the user asked for the Global Constraints line to be corrected in place. Fixed directly in `Docs/superpowers/plans/2026-08-14-multi-method-auth-frontend-plan.md` — confirmed order for implementation is **Google, Apple (disabled), Email, Phone**, Apple shown as a visibly-present, non-interactive "Coming soon" pill from the start (not added later) even though real Apple sign-in stays Future Scope on the backend.

## 2026-08-15 — Multi-method auth frontend: no OAuth redirect flow exists — the hard-stop concern about redirect/session reconciliation doesn't apply to this plan

Before starting frontend implementation, the user set a hard-stop checkpoint at "the task covering the OAuth redirect flow and its reconciliation with the router-less step-machine and AuthContext's session-on-load model." A full read of the plan and its backing frontend spec (`2026-08-14-multi-method-auth-frontend-design.md` §2, "OAuth flow in a router-less SPA") found zero occurrences of a redirect flow anywhere — Google Identity Services' popup/token flow was deliberately chosen specifically *because* it avoids a redirect: the credential arrives via a JS callback inside the SPA's existing execution context, the page never unmounts, and `AuthEntryFlow`'s `useState<Step>` machine is never at risk of being wiped by a reload. **Why this matters:** a full-page redirect would have been the one thing that genuinely broke this architecture (no router to restore state after a reload) — the spec explicitly reasoned through this and rejected it before any code was written, which is why no task in the 10-task plan needed to solve a redirect/reconciliation problem at all. Confirmed with the user directly rather than silently proceeding past their intended checkpoint on a mismatched premise; user redirected the hard stop to **Task 9 (`AuthEntryFlow` orchestration)** instead — the actual place the Google credential handler integrates with the step machine and existing `login()`/session-on-load flow — as the closest real match to their original intent.

## 2026-08-17 — Multi-method auth frontend: missing-Google-client-ID banner deliberately reverted after live browser testing

The final whole-branch review's Finding 7 flagged that `GoogleButton` failed silently when `VITE_GOOGLE_OAUTH_CLIENT_ID` was unset, and a fix wave added a visible "Google Sign-In isn't configured" error banner for that case. After the fix landed, the user tested the actual running dev server in their own browser and explicitly rejected this banner — they want `GoogleButton` to render exactly as it did before, silently, regardless of client-ID configuration. **Why:** a direct, deliberate product call made from live visual testing, not a defect report — the user's own words were "I don't want this error message to show... don't show the error." Reverted in commit `f9b6bdb`, explicitly preserving the same finding-set's Finding 6 (GIS button width measurement/clamping, same file) untouched. **How to apply:** if a future pass revisits "what should happen when Google isn't configured," this decision is the reason the answer isn't a visible banner — check with the user again before reintroducing one, don't silently re-add it as a "obvious improvement."

## 2026-08-17 — Multi-method auth frontend plan: complete, final review clean

All 10 tasks + 1 out-of-plan `App.test.tsx` fix + the final whole-branch review's 1 Critical/6 Important findings, all fixed and independently re-verified twice (controller directly, then an independent scoped re-reviewer) — full detail in `backend.md`'s frontend-completion entry and `log.md`. Notably, closing this plan out also surfaced and fixed a genuine environment-level bug unrelated to the feature itself: `frontend/node_modules/@rolldown` was missing its Linux native binding, which had been silently causing the "transient vitest worker timeout" flakiness treated as unavoidable noise for the entire session up to this point. Fixed with zero footprint on the committed repo (gitignored `node_modules` only, `package.json`/lockfile untouched) — confirmed by a subsequent full-suite run with zero flakes at all, a first for this session.

## 2026-08-14 — Standing documentation discipline established: `decisions.md`, `log.md`, `backend.md`, `database.md`

Four new append-only root-level tracking files, each distinct from an existing doc (see each file's own header). **Why:** this session's multi-method-auth work was substantial enough (a design spec, a follow-on frontend spec, two full implementation plans, six-plus rounds of decision resolution) that relying on `session.md` alone — a short, prunable, overwritten-each-session pointer — risked losing the "why" behind decisions once `session.md` gets pruned. A corresponding CLAUDE.md section ("End-of-Session Documentation") was drafted to make updating all of these a standing requirement, not proposed as optional — pending the user's manual merge into `CLAUDE.md`/`session.md` (not committed automatically here, to avoid a race with concurrent edits to those two specific files).

## 2026-08-17 — Email signup reverses to email+password (was email+OTP)

Email signup moves from email+OTP to email+password — reverses the
2026-08-14 multi-method-auth decision that made email one of three
transparent-OTP-style methods (that entry is marked superseded, not
edited — this file is append-only). **Why:** password-manager autofill
removes more real friction on email than email-OTP's inbox-check step
saves — phone+OTP and Google both keep their zero-friction, instant-
verification advantage, so the passwordless principle stays intact
everywhere it was actually earning its keep. Google and phone+OTP are
unchanged. Full design: `Docs/superpowers/specs/2026-08-17-email-password-signup-design.md`.

Two real findings surfaced during design review, not just implementation:
(1) a genuine namespace-squatting gap where an unverified signup email
could occupy the `EMAIL_PASSWORD` identity slot before its real owner ever
tries — traced explicitly (no real-account hijack is possible; a fresh
signup only attaches to an existing account if the entered *phone number*
matches) and closed with a decoupled email-confirmation step that gates
only `/auth/login/email`, never signup or the phone gate itself, so there's
zero added friction on the happy path; (2) a successful password reset
also confirms the email if it wasn't already, since clicking a link mailed
to that exact address is equally strong proof of mailbox control — this is
what makes squatting self-service-recoverable without a support ticket.

## 2026-08-17 — Password authentication removed entirely; email reverts to email+OTP for both signup and login

**Reverses the entry immediately above this one** (this file is append-
only — that entry is marked superseded, not edited). Password-based
email signup/login, password reset, and every `password_hash`/
`email_confirmed_at` field backing them are removed from the schema,
backend, and frontend — no password field survives anywhere in the
product. Email now uses the same OTP-verification pattern phone+OTP and
the (already-built) email-OTP-signup-confirmation infrastructure already
used: `signup_email` sends an email OTP directly (no password collected),
and login is now request-code-then-verify against email+OTP as well —
the `EMAIL_OTP` provider identity (benched, unused, in the 2026-08-17
entry above) is reactivated as the active email provider; `EMAIL_PASSWORD`
takes its place as the now-benched, kept-but-unused enum value, per the
same "Postgres can't cheaply drop an enum value" reasoning already
established for `EMAIL_OTP`.

**Why:** management decision. This is a reversal of judgment, not new
information about user behavior or a walked-back technical finding — the
password-manager-autofill rationale in the entry above was a real
tradeoff call at the time; leaving it uncontradicted here would misstate
why the code changed. Google and phone+OTP were never password-based and
are unaffected either way.

## 2026-08-19 — Left Auth Showcase Panel: Single Continuous Deliberate SVG Path Motion

The left authentication showcase panel was redesigned (`AuthShowcasePanel.tsx`) to replace random floating bubbles and cycling statistics with a single, deliberate continuous path integrated into the central 3D dark slate card.
- **Trajectory Motion**: The path draws progressively from a subtle chaotic waveform on the left into an increasingly structured upward compounding curve on the right.
- **Play-Once Session Guard**: Uses `hasAnimatedInSession` module state so the 3.2s animation draws exactly once on initial page load and stays in its completed state across auth step transitions, avoiding jarring resets.
- **Hover-Only Milestone Metrics**: Replaced automated cycling stats with a cursor-hover tooltip that reveals milestone data (`+14.8%`, `+28.4%`, `+41.2%`, `+56.8%`) at the nearest data point.

**Why:** Creates a calm, premium, deliberate financial visualization that communicates portfolio progression without distracting motion or false complexity.

## 2026-08-19 — Comprehensive Frontend Validation & Typo Detection Engine

Implemented client-side validation across all auth screens for both Email and Phone channels (`frontend/src/features/auth/validation.ts`):
- **Email Validation**: Structural checking (missing `@`, multiple `@`, spaces, consecutive dots, dot/hyphen boundaries) + missing TLD prompts + intelligent typo suggestions (e.g. `name@gmial.com` -> *"Did you mean name@gmail.com?"*) without silent modification.
- **Indian Mobile Phone Validation**: Enforces 10-digit requirements, valid Indian prefixes (`6`, `7`, `8`, `9`), rejects non-digits/decimals, and normalizes `+91`, `91`, `0` prefixes to standard `+91XXXXXXXXXX`.
- **Dynamic Live Recovery UX**: Errors trigger on blur and submit, and clear/update dynamically in real time as the user types corrections.

**Why:** Eliminates failed OTP submissions, prevents subtle user typos, and provides human-friendly error guidance directly below input fields.

## 2026-08-19 — Hand-Drawn Hero Illustrations & Bespoke Option Card SVGs

Replaced generic vector artwork with bespoke hand-drawn illustrations sourced from the project's illustration sheet:
- Extracted 5 transparent high-resolution PNGs with subtle Unifolio green accents (`#22C55E` / `#16A34A`) and light/dark theme assets, rendered in `OnboardingIllustration.tsx` with an ambient emerald radial glow.
- Replaced generic Lucide icons on **Household** (`Q4Household.tsx`) and **Privacy & Security** (`TrustPrimer.tsx`) option cards with custom hand-drawn SVGs matching the stroke weight and character of the rest of the onboarding cards.

**Why:** Creates a cohesive, bespoke visual identity across the entire onboarding and authentication experience while strictly honoring the brand's monochrome-with-green-accent design philosophy.

