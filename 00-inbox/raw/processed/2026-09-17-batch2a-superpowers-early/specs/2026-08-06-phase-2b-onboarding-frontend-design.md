# Onboarding Frontend — Design (Phase 2b)

## Purpose

Phase 2 backend (complete, merged to `main`) built phone+OTP auth, session
tokens, `GET`/`PATCH /auth/me`, and household-member CRUD. This is the
frontend that calls those endpoints — PRD-02's onboarding flow
(App-Flow-Unifolio.md screens S0-S7, S23-S26), including the v1.3/v1.2 scope
pivot: a Sign Up/Log In landing screen ahead of phone entry (FR-2b),
back-navigable/revisitable onboarding questions (FR-7a), and the Family CAS
Upload subsystem (FR-10-FR-14) — per-member independent upload cards, an
"Upload your own CAS?" branch, and a client-side queue with a single
batch "Parse Files" action, sequencing into PRD-01's existing Import Review
screens (built in Phase 1b) unchanged.

## Scope

**In scope:**
- Landing (S23), Phone Entry (S0), OTP Verify (S1) — auth entry.
- Trust Primer (S2), Q1-Q4 (S3-S6), Add Family Members (S7) — the
  questionnaire, with back-navigation/revisit (FR-7a).
- Family CAS Upload (S24), Upload My CAS? (S25), Parse Queue (S26) — the new
  multi-member upload/queue/batch-parse subsystem.
- Session resume on app load (`GET /auth/me`), replacing
  `VITE_DEV_HOUSEHOLD_MEMBER_ID` in `features/import/api.ts` with a real
  bearer token from the authenticated session.
- A minimal `Dashboard` placeholder — just enough to land on after
  onboarding completes. PRD-03's real Main Dashboard is a separate,
  unbuilt phase; this placeholder is not it.

**Explicitly out of scope:**
- PRD-03's actual Main Dashboard UI (holdings tables, family aggregate
  view, etc.) — out of scope for this phase, a placeholder screen only.
- A router library. The app is still small enough (one active flow at a
  time: Auth → Onboarding → Import → Dashboard placeholder) that a step
  machine with a history array, as already established for `OnboardingFlow`,
  covers navigation without adding React Router. Revisit when PRD-03/04 add
  real multi-destination navigation (the persistent Navigation Shell
  App-Flow-Unifolio.md already describes structurally).
- PIN/biometric return-login (PRD-02 FR-2a) — explicitly deferred in PRD-02
  itself to a dedicated Auth/Security PRD, not part of this build.
- Redesigning PRD-01's `ReviewTable`/Import Review screen. Family CAS
  Upload reuses it unchanged, per Design Handoff Alignment #6 — the only
  addition is a small "Reviewing: {memberName}'s CAS" label rendered above
  it during batch mode.
- Server-side onboarding_step enum validation. `PATCH /auth/me` already
  accepts any string; the locked step vocabulary below is a frontend-only
  constant. Revisit if a second client ever needs to write this field.

## Architecture

```
frontend/src/
  features/auth/
    AuthContext.tsx          # session token (localStorage-backed) + GET/PATCH /auth/me wrappers
    Landing.tsx               # S23
    PhoneEntry.tsx             # S0
    OtpVerify.tsx               # S1
    TrustPrimer.tsx              # S2
    Q1Name.tsx .. Q4Household.tsx # S3-S6
    AddFamilyMembers.tsx           # S7
    OnboardingFlow.tsx               # orchestrator: history stack, step routing, resume
    onboardingSteps.ts                # ONBOARDING_STEPS locked vocabulary (frontend-only)
    FamilyCasUpload.tsx                # S24
    UploadMyCas.tsx                     # S25
    ParseQueue.tsx                       # S26
    FamilyImportFlow.tsx                  # orchestrator: queue state, sequential parse/review/confirm
  features/dashboard/
    DashboardPlaceholder.tsx                # minimal "you're in" stub, not PRD-03
  features/import/                           # Phase 1b, mostly unchanged
    ImportFlow.tsx                             # solo path only — untouched
    ImportConfirmed.tsx                         # +1 optional prop, see below
    UploadForm.tsx, ParsingIndicator.tsx,
    ReviewTable.tsx, ImportError.tsx               # untouched
    api.ts                                          # parseImport/confirmImport now attach
                                                       # Authorization header from AuthContext
  App.tsx                                             # composition root, session-resume boot effect
```

**`App.tsx`** — boot effect: read token from `localStorage` → if present,
call `GET /auth/me`. No token, or a 401 (clears the stale token) → mount
`Landing`. Valid session + `onboarding_completed: false` → mount
`OnboardingFlow`, resuming at the user's stored `onboarding_step`. Valid
session + `onboarding_completed: true` → mount `DashboardPlaceholder`.

**`OnboardingFlow`** owns:
- `history: {step: OnboardingStep, skipped: boolean}[]` + `cursor` index.
  Forward navigation pushes; Skip pushes with `skipped: true`; Back moves the
  cursor left without truncating — Back then Forward retraces the same path.
  Revisiting a step via Back is fully editable; answering it updates that
  step's value in place and clears `skipped`, it never forks a new branch.
- Answers for each question (name, investing behavior, purpose, household
  choice, family member list) held in local state and flushed to
  `PATCH /auth/me` (or `POST /household-members` for family members) as each
  step completes — not deferred to one big submit at the end, matching
  Phase 2 backend's existing per-field `PATCH /auth/me` design.
- Locked `onboarding_step` vocabulary (`onboardingSteps.ts`): `landing`,
  `phone`, `otp`, `trust_primer`, `q1_name`, `q2_investing`, `q3_purpose`,
  `q4_household`, `add_family`, `family_cas_upload`, `upload_my_cas`,
  `parse_queue`, `done`.

**`FamilyImportFlow`** owns the upload queue:
```ts
type QueueItem = {
  memberId: string;
  memberName: string;
  file: File;
  password: string;
  status: "queued" | "parsing" | "review" | "confirmed" | "failed";
};
```
One `QueueItem` per member who uploaded (including the user's own file from
S25's "Upload Now"). Nothing is sent to the server until "Parse Files" is
clicked (S26) — files sit in browser memory as `File` objects, per FR-12.

**The one behavioral fork in `UploadForm`'s caller:** the component itself
is unchanged. Called from the solo path (S8, after Q4's "Just me"), its
`onSubmit` calls `parseImport` immediately, exactly as Phase 1b built it.
Called from a family member's card (S24) or S25's "Upload Now", its
`onSubmit` instead pushes a `QueueItem` and flips that member's card to
`Uploaded` — no parse call happens until the batch step.

**Batch parse (S26 → "Parse Files"):** `FamilyImportFlow` processes the
queue **sequentially, never in parallel** — two concurrent `parseImport`
calls would race against the backend's in-memory preview-session store
(the exact class of bug Phase 1's dedupe race already surfaced once). Per
item: `parseImport` → `ReviewTable` (with the added member-context label) →
user confirms → `confirmImport` with that item's `memberId` → advance. A
failed item (bad password, unreadable PDF) shows the existing `ImportError`
retry UI scoped to just that item; the queue continues to the next item
either way — one member's failure never blocks another's.

**Payoff screen, decided during brainstorming:** showing the full
celebratory `ImportConfirmed` screen after every member in a multi-member
batch would dilute the moment PRD-02's Design Handoff Alignment #5 calls the
narrative payoff of onboarding. Between queue items, only a lightweight
inline "✓ {memberName} done" shows. The real `ImportConfirmed` screen shows
once, after the last queued item, with `added`/`skipped` summed across all
items into one aggregate result (`import_id` is unused by the component's
render, so the aggregate's value is arbitrary — the last item's id).

**`ImportConfirmed` gets one optional prop:** `ctaLabel?: string` (default
`"Import another CAS"`, preserving S16 Ongoing Data Addition's existing
behavior/tests unchanged). Both onboarding entry points — solo (single
confirm) and family (aggregate, after the batch) — pass `ctaLabel="Continue"`
and wire the click to `PATCH /auth/me {onboarding_completed: true}` then
mount `DashboardPlaceholder`, instead of resetting to a blank upload form.
This makes solo and family onboarding end the same way regardless of how
many members' CAS files were involved.

## Screens (new/changed only — S8-S12 are Phase 1b, untouched)

| Screen | Component | Notes |
|---|---|---|
| S23 Landing | `Landing.tsx` | Two buttons, "Sign Up" and "Log In" — both lead to the same Phone Entry/OTP flow (no behavioral difference; FR-2b requires the *label*, not a divergent flow) |
| S0 Phone Entry | `PhoneEntry.tsx` | Unchanged mechanically, now reached only via S23 |
| S1 OTP Verify | `OtpVerify.tsx` | On success, stores the session token via `AuthContext`, routes to `OnboardingFlow` at the resumed step |
| S2-S6 | `TrustPrimer.tsx`, `Q1Name.tsx`...`Q4Household.tsx` | Each is a thin form + Back/Skip/Next controls wired to `OnboardingFlow`'s history |
| S7 Add Family Members | `AddFamilyMembers.tsx` | Repeatable add-member form calling `POST /household-members` per member |
| S24 Family CAS Upload | `FamilyCasUpload.tsx` | One card per member (name, Upload CAS action, Not Uploaded/Uploaded status) — cards are visual siblings, no ordering implies priority (Design Handoff #6) |
| S25 Upload My CAS? | `UploadMyCas.tsx` | Upload Now / Upload Later, per FR-11 |
| S26 Parse Queue | `ParseQueue.tsx` | Lists queued filenames, single "Parse Files" action; during processing shows per-item progress (queued/parsing/review/confirmed/failed) |
| Dashboard placeholder | `DashboardPlaceholder.tsx` | Minimal landing stub post-onboarding, not PRD-03 |

## Error Handling

- **Session resume 401** → clear stored token, mount `Landing`. Never
  surface a raw error here — an expired/invalid session on load is a normal
  return-visit case, not a failure state.
- **Per-queue-item parse/confirm failure** → existing `ImportError` retry UI,
  scoped to that item; the batch continues past it (see Architecture above).
- **`PATCH /household-members` / `PATCH /auth/me` failures during
  onboarding** → inline retry on the current step; the step's local state is
  preserved (not cleared) so the user doesn't re-enter data after a
  transient network failure.
- **App closed before "Parse Files"** (an edge case already logged in
  App-Flow-Unifolio.md's Screen States / PRD-02's Edge Cases table) →
  the queue is in-memory only and does not survive a reload. On resume, the
  user lands back at `family_cas_upload`/`parse_queue` per their stored
  `onboarding_step`, but any queued-not-yet-parsed files are gone — cards
  that were `Uploaded` revert to reflecting only what's still queued (none),
  so the user re-selects those files. This is a deliberate simplification,
  not a gap: persisting `File` objects across reloads would need IndexedDB
  or actual server-side upload-without-parse, neither of which PRD-02 asks
  for.

## Styling

Reuses `frontend/src/styles/tokens.css` and the shared `Badge` component
(for card status: Not Uploaded/Uploaded) exactly as Phase 1b established
them — no new design-token work in this phase.

## Testing

- `OnboardingFlow`'s history/back-nav reducer and `FamilyImportFlow`'s queue
  reducer get real unit tests (the only genuinely new *logic* in this
  phase) — push/back/skip/revisit-then-edit for the former, queue
  add/sequential-process/per-item-failure for the latter.
- `App.tsx`'s boot effect gets one test per branch: no token, 401 (expired),
  valid + `onboarding_completed: false` (resumes at stored step), valid +
  `true` (Dashboard placeholder).
- Screens that are thin wrappers around already-tested components
  (`UploadForm`, `ReviewTable`, `ImportError`) are tested for wiring only —
  right props passed, right callback invoked — not for re-testing those
  components' own internals.
- `ImportConfirmed`'s new `ctaLabel` prop gets one test confirming the
  default (`"Import another CAS"`) is unchanged when the prop is omitted,
  protecting Phase 1b's existing S16 behavior.

## Open Items Not Resolved Here

- Exact microcopy/tone for each question — PRD-02 explicitly defers this to
  a Design Brief pass, not a PRD/spec job.
- The real PRD-03 Main Dashboard — `DashboardPlaceholder` is intentionally
  minimal and will be replaced outright when that phase is built.
