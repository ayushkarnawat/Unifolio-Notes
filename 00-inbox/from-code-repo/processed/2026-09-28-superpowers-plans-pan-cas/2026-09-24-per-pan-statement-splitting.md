# Per-PAN Statement Splitting ("Who is who") — Plan

**Date:** 2026-09-24
**Status:** Draft for review. No code written.
**Builds on:** the PAN-at-upload work, commits `11f7dfc`, `b8d88a8`, `b8901e4` (spec `Docs/superpowers/specs/2026-09-24-pan-at-upload-attribution-design.md`).

## Why

Most Unifolio users request their CAS **without PAN**. That statement is keyed on one email address, and in Indian families one parent's email is often registered on the spouse's, children's and parents' folios. **One statement can hold several people's investments.** Every folio carries its own PAN (confirmed on a real 10-year CAMS statement: 11 folios, each with a PAN). Folios carry **no holder name**: `casparser` 1.3.0 gives a folio only `PAN`, `KYC` and `PANKYC`.

Today we read the PAN from the **first folio only** (`backend/app/services/import_/parser.py:191`). A family statement therefore stores one person's PAN and imports **everyone's funds into one member**. If that first folio has no PAN, the whole statement is treated as having none.

## What's already done vs. what's missing

| Already done (committed) | Missing (this plan) |
|---|---|
| PAN is the identity key; name/email only for display | Read the PAN **per folio** and group folios by person |
| PAN checked and claimed at upload, pending → permanent on Confirm | Claim **one PAN per person** in a statement, each for its own member |
| Confirm Import never prompts | Keep that true when several people are imported in one confirm |
| Cross-account PAN block; "This PAN already exists" popup | Apply conflicts **per person**: one blocked person doesn't stop the rest |
| Family onboarding with per-member upload cards | Family onboarding with **one family statement** and a who-is-who step |
| Just Me: one statement = self | Just Me: pick which person is you; others left out or added as family |
| — | Folios with **no PAN**: folio number + fund house hint, else the user decides |
| — | Review screen grouped by person; one Import record per member |

**Deliberately not in this plan** (later work): a "claim this PAN from another account" flow to replace "contact support"; a non-blocking cross-account hint for no-PAN folios based on the folio number.

## Behaviour after this change

- **A statement with one person** works as today, with no extra step:
  - The PAN is known in the household, or it's the member being uploaded for and that member has no PAN yet.
  - The PAN is still claimed at upload.
- **A statement with several people, or one unknown person uploaded for a member who already has a PAN,** gets a **who-is-who** step between upload and review:
  - There is one card per person: masked PAN, number of funds, fund houses and the top fund names.
  - Each card's choice is: *Me*, an existing member, *+ Add new member* (name + relationship), or *Leave out*.
  - **Pre-filled automatically:**
    - A PAN already held by a member of this household. That card is **locked**, since a PAN can only ever belong to that member.
    - In Just Me, when exactly one card is unassigned, it's pre-filled as *Me*.
  - **Blocked card:** a PAN held by **another Unifolio account** shows "Already tracked in another Unifolio account — this person will be left out". The other people still import.
  - **Funds with no PAN:**
    - A folio whose number and fund house already exist under a household member is assigned to that member.
    - The rest form one "Funds with no PAN" card, defaulting to the member the upload is for.
  - **Validation:** every card needs a choice, and two cards can't pick the same member. The no-PAN card is exempt from the second rule.
- **When the PAN enters the database:**
  - Single-person statements: at upload, unchanged.
  - Multi-person statements: when the user clicks **Continue to review** on the who-is-who step. All assigned PANs are claimed as pending in one transaction, all or nothing. Confirm makes them permanent.
- **Confirm** imports each person's funds into their member. It writes one `imports` row per member and drops left-out people's transactions. It never prompts.
- **Family onboarding:**
  - Steps: Add Family Members → *Upload your family's statement* → who-is-who (the members just added are offered) → review → confirm → *Add another statement?* → finish.
  - The *Add another statement?* step is for families whose folios are spread across two emails.
  - Per-member cards and the parse queue go away.

## Design

### Backend data model
No schema change. `household_members` already holds one PAN per member, and `imports.household_member_id` already allows one import row per member.

### Parser (`parser.py`)
- `ParsedScheme` and `NormalizedTransaction` each gain `pan: str | None`, taken from their folio.
- `ParseResult` gains `people: list[ParsedPerson]`:
  - `ParsedPerson(key: str, pan: str | None, pan_masked: str | None, folio_keys: set[tuple[str, str]], scheme_count: int, amcs: list[str], top_schemes: list[str])`.
  - `key` is `"p1"`, `"p2"`, … in order of first appearance, plus `"no_pan"`.
- `ParsedInvestor.pan` is removed. `ParsedInvestor` keeps the recipient's name and email for display.
- `raw_json` keeps redacting every folio's PAN, as today.

### Suggestions (`pan_claims.py`)
`suggest_assignments(db, user_id, uploading_member, people) -> list[PersonSuggestion]`, where `PersonSuggestion(key, kind, member_id)` and `kind` is one of:
- `"known"`: locked, the PAN is held by a member of this account.
- `"blocked"`: the PAN is held by another account.
- `"uploading_member"`: the default when it's safe.
- `"none"`: the user must choose.

For no-PAN folios: a folio+AMC match gives a per-folio pre-assignment. The remaining folios get `"uploading_member"`.

### Two-step API (`api/imports.py`, `service.py`)
- **`POST /imports/parse`:**
  - Builds the session (now also holding the people and suggestions) and returns a preview containing `people[]`, `suggestions[]`, `needs_assignment: bool` and `schemes[].person_key`.
  - If `needs_assignment` is false, it claims the single PAN as pending exactly as today.
  - If it's true, it claims nothing yet.
- **New `POST /imports/sessions/{id}/assignments`:**
  - Body: `[{person_key, member_id?, new_member?: {name, relationship}, skip?: bool}]`.
  - Checks every `member_id` belongs to the user, creates any new members, and claims each assigned PAN as pending with `claim_pan_for_member`.
  - All in one transaction. On any `PanConflictError` it rolls back everything and returns 409 with the failing `person_key` and code.
  - Stores the assignment on the session and returns the preview with members attached.
- **`POST /imports/confirm`:**
  - Requires a complete assignment when `needs_assignment` is true. Otherwise it uses the uploading member, as today.
  - For each assigned member: `confirm_pan_claim`, one `Import` row, its folios and transactions, and `store_cas_file` (a copy per import row, so each row's 30-day expiry stays independent).
  - Left-out people are not imported.
  - Response: totals plus `imports: [{member_id, import_id, added, skipped}]`. `import_id` is kept for compatibility.
- **`POST /imports/sessions/{id}/discard`:** releases every pending claim in the session.

### One-step path (`/cas-imports`)
- A multi-person statement returns 409 `multi_person_statement` ("upload it through the review flow"). This path isn't reachable from the current UI, and it has no step where the user could say who is who.
- No-PAN folios go to the member.

### Frontend
- **`types.ts` / `api.ts`:** add `PersonGroup`, `PersonSuggestion` and `needs_assignment`; `submitAssignments(sessionId, assignments)`; confirm response `imports[]`.
- **New shared `WhoIsWho` component:**
  - Cards, choice dropdowns, inline *Add new member* form (name + relationship), locked and blocked states, validation, and a **Continue to review** button.
  - Per-card 409s are shown on the matching card.
- **`ReviewTable`:** groups schemes into one section per person (member name + masked PAN) when there is more than one person. The Confirm button is unchanged.
- **`ImportFlow` (Just Me, dashboard) and `MobileImportView`:** the flow becomes upload → (who-is-who if needed) → review → confirm.
- **`FamilyImportFlow`:** rebuilt as single family upload → who-is-who → review → confirm → *Add another statement?* → done. Per-member cards and the queue are removed. The self member is created before upload so *Me* is always available.

## Tasks (TDD, in order)

1. **Parser: per-folio PAN and people groups** (`parser.py`, `tests/services/import_/test_parser.py`)
   - Tests use synthetic CAS data: three PANs plus one no-PAN folio.
   - Check groups, keys, folio membership and counts.
   - A single-PAN statement gives one group.
   - The first folio having no PAN no longer hides the others.
   - `raw_json` has no PAN.
   - Every schema/transaction carries its `pan`.
2. **Suggestions** (`pan_claims.py`, `test_pan_claims.py`)
   - One test per kind: known, blocked, uploading_member, none.
   - Expired pending claims are treated as free.
   - No-PAN folio+AMC match.
   - Just Me pre-fill of the single unassigned card.
3. **Parse + assignments service and route** (`service.py`, `api/imports.py`, tests)
   - `needs_assignment` true/false cases.
   - The single-person fast path still claims at parse.
   - Assignment creates members, claims all PANs, and rolls back fully on one conflict (409 names the `person_key`).
   - The IDOR check on `member_id`.
   - Duplicate-member rejection.
   - Discard releases every claim.
4. **Multi-member confirm** (`service.py`, tests)
   - One `Import` per member.
   - Transactions land on the right member's folios.
   - Left-out people's transactions aren't written.
   - Each PAN becomes permanent.
   - Totals and per-member breakdown.
   - Dedupe across two statements of the same PAN.
   - Confirm never raises on PAN.
5. **One-step path** (`lifecycle_service.py`, `api/cas_imports.py`, tests)
   - Multi-person → 409 `multi_person_statement` with nothing written.
   - Single-person unchanged.
6. **Frontend API/types** (`api.ts`, `types.ts`, `api.test.ts`)
7. **`WhoIsWho` component** (`features/import/WhoIsWho.tsx` + test)
   - Pre-fill, locked and blocked cards.
   - Add-new-member form.
   - Validation (unassigned, duplicate member).
   - The payload sent.
   - A 409 shown on the right card.
8. **ReviewTable grouping** (+ test)
9. **ImportFlow + MobileImportView wiring** (+ tests)
   - The single-person path is unchanged.
   - Multi-person goes upload → who-is-who → review → confirm straight through.
   - Discard on reset/cancel.
10. **Family onboarding rebuild** (`FamilyImportFlow.tsx`, `OnboardingFlow.tsx`, tests)
    - A single upload with 3 people maps to the added members and confirms.
    - The *Add another statement* loop.
    - Remove the per-member cards, `ParseQueue` usage and `UploadMyCas` usage from this flow.
11. **Docs and full verification**
    - Update the PAN storage flow doc and artifact (the new "PAN enters DB at Continue to review" moment for multi-person statements), ADR-004 note, `session.md`.
    - Full backend and frontend suites plus `tsc`.
    - Manual check with a real multi-PAN statement when one is available.

A code-level version of each task (exact code and test bodies, like the previous plan) gets written once you approve this.

## Decisions to confirm

1. **Known household PAN cards are locked.** The user can't reassign a PAN that already belongs to a member. *Recommended: yes.* A PAN can legally belong to one person only.
2. **Family flow gets *Add another statement?*** for families whose folios are spread over two emails. *Recommended: yes.*
3. **Just Me with a multi-person statement:** other people default to *Leave out*, with *Add as family member* offered. *Recommended: yes.*
4. **The one-step `/cas-imports` path refuses multi-person statements** rather than guessing. *Recommended: yes.* It's unused by the UI today.
