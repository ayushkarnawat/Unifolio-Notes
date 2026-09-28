# Design Spec: PAN Check at Upload, No Confirm-Time Prompts

**Date:** 2026-09-24
**Status:** Approved in conversation (Part 1 backend rules, Part 2 screens), 2026-09-24
**Supersedes:** the "Attribution algorithm" section of `2026-09-18-pan-cas-attribution-design.md`. That spec's PAN persistence (encryption, lookup hash, unique index) and CAS file retention sections are unchanged and still in force.

## Problem

After the 2026-09-18 change, attribution ran at **Confirm Import** time: PAN hash match → folio match → otherwise "unrecognized member". A member's PAN was only written *after* a successful confirm (`backfill_pan_if_missing`), so on a fresh account no member has a PAN yet and every first import fell through to "We couldn't match this statement to an existing family member", requiring "Continue anyway". In the Family onboarding flow that message rendered as bare text with no button, leaving the user stuck.

## Goals

1. PAN stays the identity signal for a CAS. PAN storage format (encrypted + lookup hash + unique index) and CAS file storage are unchanged.
2. The PAN check happens when the file is **uploaded** (parsed), not at Confirm.
3. **Confirm Import never shows a popup or message about attribution/PAN and never blocks.** It always proceeds to the next screen.
4. The "couldn't match / Continue anyway / Switch to…" prompt is removed everywhere.
5. Cross-account PAN reuse is still refused (existing "Import blocked" popup), now shown right after upload.
6. Family onboarding: any PAN conflict shows a "This PAN already exists" popup right after that member's file is uploaded, with **Change CAS file** and **Skip {name} for now**.

## Decisions (user, 2026-09-24)

- **Save at upload, delete if abandoned.** The PAN is written to the member at upload as *pending*. Confirm makes it permanent. Back / skip / change file deletes it immediately; an abandoned tab is covered by a timeout.
- **Different PAN on a member who already has a permanent PAN** → popup at upload ("doesn't match {name}'s PAN — choose {name}'s CAS"), never a silent import.
- **Scope: every import path** — onboarding Just Me, onboarding Family, dashboard "add data", mobile, and the async `/cas-imports` upload.
- **Family popup buttons:** Change CAS file + Skip {name} for now.

## Data model

`household_members.pan_pending_until` — `timestamp with time zone`, nullable. New migration `0016`.

- `pan_lookup_hash` set and `pan_pending_until` NULL → **permanent** PAN (every existing row).
- `pan_lookup_hash` set and `pan_pending_until` in the future → **pending** PAN. Still occupies the unique index, so no one else can claim it concurrently.
- `pan_lookup_hash` set and `pan_pending_until` in the past → **expired**. Treated as absent and cleared lazily by the next check that touches it. No background job.

Pending TTL = preview-session TTL (60 min) + 5 min margin, so a pending PAN always outlives the session that created it.

## Upload-time rule (all paths)

Given the member the file is uploaded for (M) and the parsed PAN (P):

| Condition | Result |
|---|---|
| No PAN parsed | Proceed. Nothing stored. |
| hash(P) held (pending or permanent) by M | Proceed. |
| hash(P) held by another member of the same account | 409 `pan_belongs_to_other_member`. Nothing stored. |
| hash(P) held by a member of a different account | 409 `cross_account_pan_blocked`. Nothing stored. |
| M has a permanent PAN ≠ P | 409 `pan_mismatch_for_member`. Nothing stored. |
| Otherwise (M has no PAN, or only a pending/expired one) | Write P on M (pending on the two-step path, permanent on the one-step path). Proceed. |

Expired claims held by others are cleared before the rule is evaluated. A unique-index race (IntegrityError) is re-evaluated and surfaces as the matching conflict.

## Two-step path (`/imports/parse` → `/imports/confirm`)

- `POST /imports/parse` gains required form field `household_member_id` (ownership-checked, 404 otherwise). Claims the PAN as pending, builds the preview, then commits. The preview session records `user_id`, `household_member_id` and the claimed `pan_hash`.
- `POST /imports/confirm` imports into the member the session was created for (a mismatching `household_member_id` is treated as an unknown session). It finalizes the pending PAN. No attribution gate, no `member_mismatch` 409, no `confirmed_member_override`. If the pending claim has somehow vanished, confirm re-attempts a permanent claim and, on conflict, imports without storing the PAN rather than failing.
- Sessions older than the TTL are rejected at confirm (existing "session expired, please re-upload" notice; unrelated to PAN).
- New `POST /imports/sessions/{session_id}/discard` → 204. Deletes the session and releases its pending PAN. Idempotent (unknown/expired session → 204). Never discards another user's session.

## One-step path (`/cas-imports`, password retry)

The same rule runs inside the single upload call, claiming the PAN as permanent. Conflicts return the same 409 codes before anything is committed. `confirmed_member_override` is removed.

## Screens

- **Shared:** `parseImport(file, password, memberId)`; `discardImportSession(sessionId)`; `confirmImport` loses its override argument. The member-mismatch notice and all "Continue anyway"/"Switch to" UI are removed.
- **`ImportFlow`** (Just Me onboarding, dashboard add-data): upload-time `cross_account_pan_blocked` → existing Import blocked popup (Back → `onGoToHousehold` if provided, else back to upload). `pan_belongs_to_other_member` / `pan_mismatch_for_member` → "This PAN already exists" popup with **Change CAS file** (back to upload) and **Cancel**. Try again/reset discards any open session.
- **`FamilyImportFlow`:** all three conflict codes → "This PAN already exists" popup with **Skip {name} for now** and **Change CAS file**. Change CAS file shows the standard upload form for the same member and re-parses; Skip moves on to the next queued member. A conflict is rejected before anything is committed, so there is no session or pending PAN to discard. Popup copy never identifies another account.
- **Where discard is called:** only where a parsed session is abandoned on purpose: `ImportFlow`'s reset (Try again after a failed confirm) and `MobileImportView`'s review Cancel/reset. Leaving the page is covered by the pending-PAN expiry.
- **`MobileImportView`:** same rules as `ImportFlow`; its review Cancel discards.
- The async `/cas-imports` upload is not reachable from the current UI (`WaitingForCasView` always delegates to its parent's parse path), so it needs no screen changes.

## Out of scope

- Moving preview sessions out of process memory.
- Any UI that reveals which member or account holds a conflicting PAN.
- Admin/support tooling to reassign a PAN.
