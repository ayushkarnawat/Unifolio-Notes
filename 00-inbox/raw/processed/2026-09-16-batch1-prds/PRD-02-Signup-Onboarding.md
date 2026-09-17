---
artifact: prd
version: "1.3"
created: 2026-07-22
updated: 2026-08-05
status: draft
product: Unifolio
module: Signup & Onboarding
---

# PRD: Signup & Onboarding (Questionnaire-Based, Game-Like Setup Flow)

## Overview

### Problem Statement

Every competitor in this market (Mprofit included) uses a standard form-based signup:
email, password, maybe a name field, done. Nobody in the 11-competitor set reviewed
turns onboarding itself into a moment of product delight — it's treated as a hurdle to clear
before the "real" product starts. That's the gap Unifolio wants to occupy: an onboarding
flow that feels less like filling out a form and more like the setup sequence of a
well-made app or game — a deliberate, crafted first impression — while still respecting
that this is a financial product handling sensitive data, used by everyone from DIY retail
investors to HNIs who expect an institutional-grade, non-gimmicky experience.

There is currently no concrete design for this flow. This PRD includes a research pass
(below) to ground the "game-like" direction in what actually works for fintech onboarding,
rather than guessing.

### Solution Summary

A questionnaire-driven onboarding sequence that: (1) establishes trust immediately
(security/read-only framing, before any data is asked for), (2) collects goals, family
structure, and investor type through a small number of well-designed steps rather than a
long form, (3) lets the user set up their family/household structure as part of onboarding
(not bolted on later), and (4) ends with the CAS import flow as the natural "first win" —
the moment their real portfolio data appears is the payoff, not a separate step after
onboarding "ends."

### Target Users

- **Retail DIY investors** — self-directed, price-sensitive, likely mobile-first, want speed.
- **HNI / affluent professionals** — first-generation wealth creators increasingly (60%+ of
  new HNIs in India per recent wealth-management coverage), expect a consumer-app-grade
  digital experience but with zero tolerance for anything that reads as unserious or
  templated. This segment is explicit scope per product direction, not an inference.
- Family-account setups spanning both — one login, multiple members, per the existing
  "one login → one family → up to 5 members" product direction.

## Goals & Success Metrics

### Goals

1. Make onboarding itself a differentiator, not a tax paid before the product starts.
2. Get every user — retail and HNI alike — to their first real payoff (imported portfolio
   visible on the dashboard) as fast as possible; the "game-like" feel should come from
   pacing and craft, not from adding steps.
3. Capture enough structured signal (goals, family, investor type) during onboarding to
   personalize the dashboard later, without drifting into regulated financial advice.

### Success Metrics

| Metric | Current Baseline | Target | Timeline |
|--------|-------------------|--------|----------|
| Onboarding completion rate (started → first CAS import confirmed) | Not built | ≥70% | Post-launch, first cohort |
| Time from signup start to first portfolio view | Not built | Under 5 minutes (excluding CAS wait-for-email step, which is outside our control) | Post-launch |
| Day-1 return rate | Not built | Beat industry fintech baseline (~30% is typical; see Research) | Post-launch |
| Drop-off point identification | Not built | Instrumented per-step, no blind spots | At launch |

### Non-Goals

- This flow does not constitute financial advice or a formal risk-profiling instrument in
  the SEBI RIA sense — Unifolio is not RIA-registered, and this questionnaire captures
  self-reported context for personalization, not a basis for recommendations. This
  distinction needs to be legally clean in the copy, not just implied.
- Not building KYC/identity verification in this pass — no regulatory requirement for a
  pure tracking product to collect PAN/Aadhaar beyond what CAS parsing already needs
  (and that's scoped to the CAS Parser v2 PRD, not here).

## User Stories

| ID | User Story | Priority |
|----|-----------|----------|
| US-1 | As a new user, I want to understand immediately that my data is safe and read-only before I'm asked to share anything | P0 |
| US-2 | As a new user, I want to set up my household/family structure as part of getting started, not as an afterthought buried in settings | P0 |
| US-3 | As a new user, I want the onboarding to feel quick and purposeful, not like a long form | P0 |
| US-4 | As an HNI user, I want the experience to feel premium and serious, not like a mobile game with badges and confetti | P0 |
| US-5 | As a new user, I want my first CAS import to feel like the payoff of onboarding, not a separate chore afterward | P0 |
| US-6 | As a returning user who dropped off mid-onboarding, I want to resume where I left off | P1 |

## Scope

### In Scope

- Trust-first pre-signup framing (read-only, bank-grade encryption, revoke-anytime
  language — the standard now adopted across every AA-based competitor reviewed).
- Signup/auth (method TBD — see Open Questions).
- Questionnaire: investor type/segment, primary goals, family/household setup (members,
  relationship, whether each member has their own CAS to import).
- Progress mechanic design — see Research and Functional Requirements for what
  "game-like" means here specifically (pacing/craft, not points/badges).
- Handoff into CAS import as the concluding, payoff step of onboarding.
- Resume-where-you-left-off for incomplete onboarding sessions.

### Out of Scope

- Actual risk-profiling for investment advice (regulated activity, not this product's status).
- KYC/identity verification beyond what CAS parsing itself requires.
- Equity/broker account linking during onboarding (MF-only MVP; onboarding should not
  ask about assets we can't yet import).
- Onboarding personalization logic that actually changes dashboard content — this PRD
  captures the *data*; using it to personalize the dashboard is a Main Dashboard PRD
  concern.

### Future Considerations

- A visibly different, lighter-weight onboarding surface for HNI/family-office users once
  volume justifies it — global private-banking apps increasingly separate the UHNW
  experience from the mass-market one rather than bundling both into one app; worth
  revisiting once we have real usage data rather than designing two flows speculatively.
- Advisor/CA-assisted onboarding (bulk client setup) — deferred until target-customer
  question (Section 7 of Product Context doc) is resolved.

## Solution Design

### Research Summary

A short research pass grounds the "feel like setting up a game" brief in what's actually
been proven to work — and where it breaks — in fintech onboarding specifically:

**Gamification works, but the target audience determines how far to take it.** Industry
data on fintech onboarding cites typical Day-1 retention hovering near 30% (i.e., ~70%
drop within 24 hours), and well-designed gamified onboarding (progress indicators,
milestone framing) is credited with meaningfully improving both completion and
retention in consumer-facing fintech products. But at least one documented case study
of a fintech targeting an older, more conservative audience deliberately avoided
gamification and playful visuals in favor of a restrained, minimalist flow — explicitly
because their audience's trust signals ran the other way. **This is the exact tension in our
brief**: retail DIY investors likely respond well to a livelier, game-like setup; HNI users
explicitly do not want anything that reads as unserious. The resolution isn't necessarily
two different flows — see Functional Requirements below for a single-flow approach that
threads this needle.

**Speed still matters more than delight.** Industry benchmarking (Amplitude's product
data, cited widely in fintech UX literature) associates failure to reach a first successful
action within 48 hours with a very high probability of the user never returning. Separately,
each additional authentication step has been shown to measurably reduce completion
rates. The implication for us: "game-like" must describe the *feel* of the flow, not its
*length* — every step we add for delight has to earn its place against a real completion-
rate cost.

**HNI-specific expectations, from current India wealth-management coverage:** affluent
and HNI users increasingly expect a digital experience that matches consumer-app
quality (not a clunky legacy portal), full transparency on what's being tracked and why,
and — notably — global private-wealth apps are trending toward separating the UHNW
experience from the mass-market one rather than bundling both into a single generic
app. We're not doing that separation in v1 (see Future Considerations), but the tone of the
copy and visual weight of any "game-like" elements should be calibrated so an HNI user
doesn't feel like they've downloaded a budgeting app for teenagers.

**What questionnaire-style onboarding typically asks (from risk-profiling and robo-
advisor UX literature, adapted — not adopted wholesale, since we are not doing regulated
risk profiling):** goals/time horizon, income bracket (optional, sensitive), existing
investment experience level, family/dependents, and “what best describes you” investor-
type framing. This is a useful reference list for the specific question set, not a
prescription — used to inform the draft questionnaire below, not copied wholesale, given
the non-goal of avoiding anything that reads as regulated advice-gathering.

**How to phrase questions so they don't feel like a form (second research pass, added
after initial draft):** onboarding-UX literature is consistent on one point — every question
should visibly change what the user sees next. If an answer doesn't change the path,
cut the question. This is why the draft questionnaire below asks about *investing
behavior* ("how do you currently invest") rather than demographic classification
("what's your income/net worth") — behavior-based questions read naturally to both a
retail DIY investor and an HNI, while a net-worth question would feel like a bank form to
either. The same research also flags that framing a question as "so we can personalize
your setup" performs better than labeling it "optional" — optional framing signals the
question doesn't matter, which undercuts the sense of craft we're going for.

**Auth pattern in Indian fintech, specifically (added after initial draft):** phone-number-
plus-OTP has become the default, password-free login pattern across Indian fintech —
Groww has fully phased out password-based login in favor of OTP-only, and OTP-first,
no-separate-login-friction is standard even in SEBI-regulated trading apps (which have
additional KYC obligations we don't). Since Unifolio is a tracking product, not a broker,
we don't carry SEBI's KYC/2FA mandate, but the *pattern* — phone number in, OTP back,
you're in — is now what "feels normal and fast" looks like in this market, which lines up
directly with the goal of a frictionless first step. See the Authentication section below.

### Functional Requirements

#### Reconciling "game-like" with "not childish" (design principle, not a feature)
- FR-1: "Game-like" in this product means the *pacing and craft* of a well-designed setup
  sequence (deliberate reveals, a clear sense of progress, a satisfying final moment when
  the portfolio populates) — not literal game mechanics (no points, badges, streaks, or
  confetti). Think the feel of setting up a premium device or a well-designed app's first
  run, not a mobile game's reward loop. This single interpretation should apply to both
  retail and HNI users — the *tone* of copy can flex, the *mechanic* should not.

#### Authentication (decided)
- FR-2 (updated 2026-08-17, second revision same day): Phone+OTP, Google,
  and email are all fully passwordless — no password field anywhere in
  the product. Email signup and login both use email+OTP (request a
  code, verify it), reversing this same day's earlier email+password
  revision. Every account still converges on a verified phone as a
  mandatory second step regardless of which method started signup. See
  decisions.md's second 2026-08-17 entry for the full "why" (management
  decision) and what this reverses.
- FR-2a: 6-digit OTP, standard resend/retry handling, PIN or biometric for return-visit
  login after the first OTP verification (same pattern as Groww/INDmoney's post-first-login
  flow) — this belongs in a future Auth/Security PRD for full spec, flagged here only
  because it blocks screen 1 of onboarding.
- FR-2b **(added v1.3):** The very first screen is not the phone-number field itself — it's a
  brief landing screen offering "Sign Up" and "Log In" as two labeled entry points, so a
  first-time and a returning user each see language that matches their actual situation.
  Both buttons lead to the identical phone+OTP flow (FR-2's backend already treats a new
  vs. an existing phone number transparently — a new `User` row is created on first OTP
  verification, an existing one is reused otherwise); this screen changes only the framing
  a user sees before that flow starts, not a second authentication mechanism.

#### Trust-First Framing
- FR-3: Before any data is requested, show a brief, concrete trust statement: read-only
  access, nothing is moved, data isn't sold, revoke anytime. This is now standard language
  across every AA-based competitor reviewed and should be adopted here regardless of
  which import mechanism (CAS today, AA later) is active.

#### Questionnaire Flow
- FR-4: Investor-type/segment is captured through a **behavior-based question**, not a
  demographic one — see "Onboarding Questionnaire (Draft)" below for exact wording.
  This single question set is used for both retail and HNI users (see the HNI decision
  below) and is used for later dashboard personalization only, never advice generation.
- FR-5: Capture primary goals at a light-touch level (not a full financial plan) — informs
  future dashboard framing only.
- FR-6: Family/household setup as a core onboarding step: add members, define
  relationship, indicate whether each member's own CAS will be imported now or later.
- FR-7: Every step must be skippable or deferrable except the ones required to reach the
  CAS import step — nothing blocks a user from getting to their portfolio.
- FR-7a **(added v1.3):** Skippable means genuinely revisitable, not a one-way door — a
  user must be able to go back and answer a question they skipped (or change one they
  already answered) via ordinary back-navigation, not just by re-running the whole
  questionnaire from the start. This was implicit in FR-7's original wording but not
  concretely specified; making it explicit now that it's actually being built, so "skippable"
  isn't read as "skip and lose the chance to go back."

### Onboarding Questionnaire (Draft)

Designed against the research principles above: behavior-based (not demographic)
segmentation, every answer maps to something downstream, no question labeled
"optional" (if it's not worth asking, it's cut instead). Four questions total, plus the
family-setup step — kept short deliberately, per the 48-hour-to-first-value finding.
Exact copy/microcopy is a Design Brief concern; this is the *structure and intent* the
design must preserve.

**Q1 — Name (not framed as a form field)**
> "What should we call you?"
First name only. Used immediately afterward ("Nice to meet you, Ayush — quick
questions so we can set this up right") — this is the "tell users why" pattern from the
research: framing the next questions as personalization, not paperwork.

**Q2 — Investing behavior (the segmentation question — behavior, not net worth)**
> "How are you investing right now?"
- "Mostly on my own — SIPs, mutual funds, maybe some stocks" → self-directed/DIY path
- "Through a distributor, bank RM, or family office, alongside my own tracking" →
  advisor-coexisting path (this is how HNI/affluent users self-select *without* being asked
  "are you rich," and without a separate flow — see HNI decision below)
- "A mix of both" → blended path
- "Just getting started — haven't invested much yet" → beginner path (more explainer
  tooltips later, per the Main Dashboard PRD's personalization scope)

This is the answer to the "exact wording" open question — phrased around *how they
invest* rather than *who they are*, which is why it reads naturally across the whole
target range without a separate HNI-branded question.

**Q3 — Purpose (light-touch goal capture, not a financial plan)**
> "What brings you to Unifolio?"
- "See all my mutual funds in one place"
- "Actually understand what I'm invested in" (signals analytics-dashboard-eager users)
- "Managing investments for my family, not just myself" (signals family-setup-eager users
  — can pre-select "yes" on Q4 below)
- "Compare how my funds are really performing" (signals benchmark/XIRR-eager users)

**Q4 — Household (branches into family setup, not a yes/no dead end)**
> "Just you, or tracking for family too?"
- "Just me" → straight to "Upload your own CAS?" (see Closing step below)
- "Family too" → add-member flow (name, relationship, whether their CAS will be added
  now or later), **then the Family CAS Upload flow (added v1.3, see below)** before the
  closing step

**Closing step — the payoff, not a fifth question**
> "Let's bring in your first portfolio." → CAS upload (PRD-01). For a solo user this is
  immediate; for a user who added family members, it's reached via the Family CAS
  Upload flow below rather than directly, since there's now more than one portfolio to
  bring in. Either way this is intentionally framed as the destination, not another step in
  a list, per FR's emphasis on onboarding ending at real data, not at a "you're all set!"
  screen with nothing to show.

### Family CAS Upload (added v1.3)

**Why this exists:** the original v1.0-1.2 draft above assumed a single hand-off straight
into CAS upload regardless of household size. That assumption broke once family setup
was actually being built: a household with several members needs a way to bring in
*multiple* people's CAS data without conflating whose transactions are whose, and
without forcing one file to finish parsing before the next can even be selected. This
section is the resolution — inserted between Family Setup (FR-6) and the existing CAS
import handoff (FR-9), for households with more than one member. A solo ("Just me")
user skips straight to "Upload your own CAS?" below, unaffected by any of this.

- FR-10: After family setup completes, show one independent upload card per family
  member added during onboarding (name + "Upload CAS" action + a status of
  `Not Uploaded` / `Uploaded`). Each member's upload is fully independent — selecting or
  uploading a file for one member must never affect, overwrite, or merge with another
  member's upload or data. This directly extends PRD-01's existing folio/transaction data
  model (already keyed per household member); no new merge logic is introduced here,
  only a UI surface that keeps uploads visibly separated per person.
- FR-11: Once every family member has either uploaded or been explicitly skipped, ask
  "Upload your own CAS?" with two equally-weighted options: **Upload Now** (opens the
  same CAS Upload screen PRD-01 already defines, for the account holder's own file) or
  **Upload Later** (skips directly to FR-12's queue/parse step with the account holder's
  own CAS simply absent from the batch — resumable later via PRD-01/03's existing
  Ongoing Data Addition path, same as any other post-onboarding import).
- FR-12: Uploading a file (for any member, including the account holder) does **not**
  trigger parsing immediately. Each upload is added to a visible queue (filename shown per
  entry) and stays queued until the user takes one explicit action — a single **Parse
  Files** button — that parses every queued file. This is a deliberate change from
  PRD-01's original single-file assumption: with multiple files in play, parsing each one
  the instant it's chosen would interrupt the person mid-upload-flow for every other
  member. Batching removes that interruption.
- FR-13: "Parse Files" parses every queued CAS independently — one call into PRD-01's
  existing parser per file, each still tagged with the household member it was uploaded
  for. No two members' parsed data is ever combined into one preview or one confirm
  call. Review and confirm then proceed one member at a time, reusing PRD-01's existing
  Import Review screen exactly as already specified (confidence badges, Direct/Regular
  tags, manual override) — this section does not redefine that screen, only the path that
  leads into it when more than one file is queued.
- FR-14: A family member who was skipped at FR-10 (no upload during onboarding) is not
  blocked from anything — per FR-7/FR-7a, their CAS can be added anytime afterward via
  the same ongoing "Add Data" entry point PRD-01/03 already define, scoped to that
  member.

### HNI Treatment in v1 (decided)

No separate HNI flow, screen set, or visibly different treatment in this version — one
flow for everyone. This isn't a deferral for lack of time; it's the right call structurally:
Q2 above already lets an HNI/advisor-assisted user self-identify through behavior rather
than a bank-form-style net-worth question, which means the single flow already avoids
the "budgeting app for teenagers" risk without forking the build. A visibly separate
UHNW surface (per the Future Considerations note on global private-wealth apps) is
worth revisiting once there's real usage data showing this cohort needs something
structurally different — not before.

#### Progress & Resume
- FR-7: Visible progress indicator throughout (step count or equivalent) — reduces
  abandonment by keeping the remaining effort visible, consistent with fintech onboarding
  UX findings above.
- FR-8: Incomplete onboarding sessions are resumable — a user who closes the app
  mid-flow returns to where they left off, not the start.

#### Handoff to CAS Import
- FR-9: The CAS import step is the natural conclusion of onboarding, not a separate
  post-onboarding task — framed as "the moment your real numbers show up," matching
  the emphasis on a fast first payoff from the research above. For a household with more
  than one member, this handoff is now the Family CAS Upload flow (FR-10-FR-14, added
  v1.3) rather than a direct jump into CAS upload — the payoff framing is unchanged, only
  the path to it when there's more than one portfolio to bring in.

### User Experience

Single flow, not two audience-forked flows, in v1 (see Future Considerations for why a
separate HNI surface is deferred rather than rejected). Visual language stays within the
Apple-inspired brand direction (Unifolio brand colors/fonts) — "game-like" is expressed
through motion, sequencing, and moments of reveal, not through gamification UI
elements like badges or points, per FR-1.

### Edge Cases

| Scenario | Expected Behavior |
|----------|--------------------|
| User abandons onboarding before family setup | Resume from last completed step on return; family setup remains skippable |
| User has no CAS yet (hasn't requested one from CAMS) | Clear guidance shown, onboarding can complete without import; dashboard shows an empty state with import prompt |
| User adds family members but only has their own CAS to upload | Other members' profiles exist as placeholders; import can happen per-member later |
| HNI-segment user selects an investor-type answer that doesn't map cleanly to retail/HNI | No hard branching logic in v1 — the flow doesn't change based on this answer yet, it's captured for future personalization only (per Non-Goals) |
| User skips a question (Q2/Q3), reaches CAS import, later wants to answer it | FR-7a — back-navigation lets them revisit and answer it; nothing about having already reached CAS import locks the earlier questions **(added v1.3)** |
| User uploads two family members' CAS files, then closes the app before clicking "Parse Files" | Queue is not yet parsed/persisted server-side (per FR-12); on return, the family member's status still shows `Uploaded` if the file selection survived, or `Not Uploaded` if not — either way nothing was silently discarded server-side since nothing was sent until Parse Files is clicked **(added v1.3)** |
| One family member's CAS fails to parse (wrong password, scanned PDF, etc.) while others in the same batch succeed | Per FR-13's "parses every queued CAS independently" — a failure on one file surfaces PRD-01's existing specific error for that member only (FR-12-14 of PRD-01) and does not block or roll back the others' successful parses **(added v1.3)** |

## Technical Considerations

### Constraints
- No regulated risk-profiling logic — questionnaire answers must be stored and treated as
  self-reported preference data, not advice inputs.
- Family/household data model needs to support up to 5 members per the existing
  "one login → one family" product direction — coordinate with whatever data model the
  Main Dashboard and CAS Parser v2 PRDs assume for multi-member portfolios.

### Integration Points
- CAS Parser v2 (parse/confirm API) — onboarding's final step hands off directly into this
  flow; needs a shared understanding of what "onboarding complete" means when the
  user has zero, one, or multiple family members' CAS files to upload.

### Data Requirements
- New: user profile record (investor-type/segment, goals — light schema, not a full
  financial-planning data model), family/household member records, onboarding
  progress/state (for resume).

## Dependencies & Risks

### Dependencies

| Dependency | Owner | Status | Impact if Delayed |
|------------|-------|--------|--------------------|
| Questionnaire question set and structure | Ayush + Claude | **Decided** — see Onboarding Questionnaire (Draft); exact microcopy/tone still belongs to the Design Brief pass | None — structure is locked, only wording polish remains |
| Auth method | Ayush + Claude | **Decided** — phone + OTP, no password (FR-2) | None |
| Family data model alignment with Main Dashboard PRD | Cross-PRD | Not yet reconciled | Risk of rework if data models diverge |

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| "Game-like" onboarding reads as unserious to HNI users if not carefully calibrated | Medium | High (directly named target segment) | FR-1's mechanic-vs-tone distinction, plus Q2's behavior-based (not net-worth-based) self-segmentation; get an HNI-profile reviewer's reaction to a prototype before committing to visual direction |
| Adding delight-oriented steps increases completion time and hurts the 48-hour-to-first-value metric | Medium | Medium | Every proposed step gets weighed against the research finding above before being added |
| Family setup during onboarding adds friction for single-user retail investors who don't need it | Low–Medium | Medium | FR-6 — family setup is skippable, not mandatory |

## Timeline & Milestones

| Milestone | Description | Target Date |
|-----------|--------------|--------------|
| Question set + copy finalized | Depends on Ayush input | TBD |
| Auth method decided | Blocks build start | TBD |
| Prototype (design brief stage) | Visual/interaction direction validated, including HNI-tone check | TBD |
| Build | Coordinated with CAS Parser v2 handoff | Per August build-out window |

## Design Handoff Alignment

So the upcoming Design Brief doesn't drift from what this PRD has already locked, it
needs to inherit these decisions rather than re-litigate them:

1. **Mechanic vs. tone (FR-1)**: no points/badges/streaks/confetti for anyone. "Game-like"
   is expressed through pacing, sequencing, and reveal moments — the Design Brief's job
   is to define exactly what those moments look like (motion, transitions, the specific
   instant the imported portfolio "arrives"), not to reopen whether gamification mechanics
   belong here.
2. **One flow, not two**: no HNI-specific screens, colors, or copy variants in v1 (see HNI
   Treatment decision). The Design Brief should design one flow that reads well across
   the full range, not a flow plus a variant.
3. **Four questions + family step, in the order given**: the Design Brief can restyle and
   re-word (subject to the behavior-based framing in Q2 being preserved — this is the
   part doing the real work of segmenting without feeling like a bank form), but shouldn't
   add net-worth/income/demographic questions or remove the "why we're asking" framing
   established in Q1.
4. **Auth is phone + OTP only** — the Design Brief's first screen should not design around
   a password field, email-first flow, or social login as the primary path.
5. **The CAS import step is the visual and narrative payoff of onboarding** — the Design
   Brief should treat the "your portfolio just appeared" moment as the emotional peak of
   the sequence, not a generic "setup complete" screen.
6. **(added v1.3) The Family CAS Upload flow (FR-10-FR-14) sits between family setup and
   that payoff for multi-member households** — per-member upload cards, an explicit
   "Upload your own CAS?" choice, and a queue-then-batch-parse pattern rather than
   parse-on-upload. The Design Brief should treat the per-member cards as siblings, not a
   hierarchy (no member's card should visually imply priority over another's), and should
   NOT redesign the actual Import Review screen this flow leads into — that's still PRD-01's,
   unchanged.

This PRD's Solution Design and UX sections are intentionally structural, not visual — the
actual look, motion, and microcopy are correctly a Design Brief job, not a PRD job. The
list above is what has to survive that handoff so the two documents don't contradict
each other later.

## Open Questions

- [ ] Exact microcopy/tone for each question (the structure above is locked; the words
      themselves are a Design Brief pass) — Owner: Ayush + Claude, during Design Brief
- [ ] PIN/biometric return-login spec (FR-2a) — deferred to a dedicated Auth/Security PRD
      rather than fully specified here — Owner: TBD. **Foundational schema now exists**
      (`otp_requests`, `sessions` in the Database Schema doc) so login functions at MVP;
      the deferred PRD covers policy on top of that (rate-limiting, lockout, device
      management), not the base tables.
- [x] Whether "Family too" in Q4 should let a user add members before or after their own
      CAS import completes — **Resolved v1.3**: family setup completes first, then every
      added member gets an independent upload slot in the new Family CAS Upload flow
      (FR-10), with the account holder's own CAS handled last via "Upload your own CAS?"
      (FR-11) — see the new Family CAS Upload section above.

## Appendix

### Related Documents
- Product Context — Wealth Management Platform (project knowledge) — original
  questionnaire-onboarding direction and family-structure requirement
- Combined Feature-Parity Matrix (project knowledge) — trust-framing language pattern
  adopted across competitors
- PRD-01: CAS Parser v2 — the module this onboarding flow hands off into

### Research Sources
- Fintech onboarding gamification and retention data: StriveCloud, Orbix Studio, Merge
  Rocks, Eleken, Verified.inc, Codetheorem, Webstacks (industry UX blogs, 2026)
- HNI/wealth-management digital-experience expectations: Hubbis (Dezerv, 360 ONE
  Wealth interviews), Waterfield Advisors, and a UHNW competitive-landscape analysis
  (all 2025–2026)
- Risk-profiling question design literature: peer-reviewed robo-advisor risk-profiling
  studies (BMEE journal, MDPI Sustainability/FinTech journals)
- Onboarding question design ("actionable answers," avoid "optional" framing):
  Formbricks user-onboarding best-practices guide (2026)
- Indian fintech OTP-first auth pattern: Groww and INDmoney login/onboarding
  documentation, productgrowth.in trading-app onboarding playbook (2026)

### Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-07-22 | Claude (PM partner) | Initial draft, includes research pass |
| 1.1 | 2026-07-22 | Claude (PM partner) | Added draft questionnaire (Q1–Q4 + family step); resolved auth to phone+OTP (no password); resolved HNI treatment (no separate flow in v1); added second research pass (question-phrasing and Indian auth-pattern findings); added Design Handoff Alignment section |
| 1.2 | 2026-07-22 | Claude (PM partner) | Noted foundational `otp_requests`/`sessions` tables now exist in the Database Schema doc, unblocking basic login at MVP; full auth/security policy remains deferred as before |
| 1.3 | 2026-08-05 | Claude (PM partner), from team brainstorm relayed by Ayush | Added FR-2b (Sign Up/Log In landing screen before the phone-number field); added FR-7a (skipped questions must be genuinely revisitable via back-navigation, not just a one-way skip); added the Family CAS Upload section (FR-10-FR-14) for multi-member households — per-member upload cards, independent state per member, "Upload your own CAS?" Now/Later, and a queue-then-batch-parse pattern (Parse Files) instead of parse-on-upload, sequencing into PRD-01's existing Import Review screen unchanged, once per member; resolved the "before or after own CAS import" open question accordingly; updated FR-9 and Design Handoff Alignment to match |
| 1.4 | 2026-08-17 | Claude (PM partner) | FR-2 revised twice same day: first to email+password for the email signup path (password-manager-autofill rationale), then reversed back to email+OTP for both signup and login (management decision) — phone+OTP, Google, and email are all passwordless again, no password field anywhere. See decisions.md's two 2026-08-17 entries for the full sequence. |
