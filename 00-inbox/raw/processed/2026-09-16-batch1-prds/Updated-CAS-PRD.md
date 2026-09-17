# CAS Import — Product Requirements Document

**System:** Mutual Fund Consolidated Account Statement (CAS) Import
**Product:** Unifolio
**Document status:** Implementation-ready
**Audience:** Product, UX, Frontend Engineering, Backend Engineering, QA

---

# Overview

CAS Import is the entry point through which a user's mutual fund holdings enter Unifolio. A user either requests a Consolidated Account Statement (CAS) from CAMS/KFintech and manually returns with the emailed PDF, or uploads a CAS PDF they already have. The system unlocks, validates, and parses the PDF server-side, extracts transaction-level data, deduplicates it against the existing ledger, and commits it to the user's portfolio. The feature must handle multi-member households, password-protected files, partial failures, and the structural risk that a CAS only covers transactions within a bounded date range (the "opening balance" problem).

This PRD defines the product requirements for a **server-backed, queue-driven implementation**, which is the correct architecture for Unifolio.

---

# Background

Every mutual fund investor's holdings are legally issued as a CAS by CAMS or KFintech, the two Registrar and Transfer Agents (RTAs) that service the Indian mutual fund industry. There is no documented public API for programmatically retrieving or generating a CAS on a user's behalf — the only route is the RTA's own web form, which emails a password-protected PDF to the investor's registered email address. Any product in this category must therefore design around a **manual, human-in-the-loop acquisition step**, followed by a **file upload and parse step** that Unifolio controls end-to-end.

This creates two distinct product problems: (1) reducing the friction and confusion of the acquisition step, since most first-time users don't know a CAS must be requested before it can be uploaded, and (2) building a reliable, recoverable ingestion pipeline for a file whose structure, password, and completeness cannot be guaranteed at upload time.

---

# Product Vision

CAS Import should feel like a single, guided task — "get your holdings into Unifolio" — regardless of whether the user starts with a CAS already in hand or needs to request one first. The user should never be confused about what step they're on, never lose data to a silent duplicate or misattributed import, and never be left wondering whether an import "worked."

---

# Product Goals

1. Minimize time-to-first-imported-portfolio for a new user.
2. Eliminate the two most common support failure modes in this category: "I uploaded but nothing happened" (users who never actually requested a CAS) and "my numbers look wrong" (duplicate or misattributed imports).
3. Make import status and history transparent and queryable at every stage, for every family member independently.
4. Build a pipeline that is safely retryable and reprocessable, so a parser bug discovered later can be fixed and historical imports reprocessed without asking users to re-upload.

---

# Business Objectives

| Objective | Rationale |
|---|---|
| Increase completed-import rate among users who start a CAS request | The "Waiting for User" gap (time between requesting a CAS and returning to upload it) is the largest expected drop-off point in the funnel. |
| Reduce support ticket volume related to import | Password errors, wrong-statement-type errors, and misattribution are the dominant, addressable failure classes. |
| Establish a durable transaction ledger | Supports downstream features (XIRR, tax reporting, multi-year performance) that depend on complete, deduplicated transaction history rather than point-in-time snapshots. |
| Protect user trust in a financial product | Misattributing one family member's holdings to another, or silently double-counting a transaction, is a trust-ending bug class for a wealth application. |

---

# User Personas

| Persona | Description | Needs from CAS Import |
|---|---|---|
| **First-time Primary Investor** | Sets up Unifolio for themselves and their household for the first time. Has never requested a CAS before and may not know what one is. | Clear, explicit guidance on what a CAS is and how to get one; reassurance that "nothing happened yet" is expected while waiting for the CAMS email. |
| **Household Administrator** | Manages Unifolio on behalf of multiple family members (spouse, parent, child). Imports CAS files for people other than themselves. | Reliable, low-error family-member attribution; visibility into which member's data is covered and which isn't. |
| **Returning Power User** | Already has holdings in Unifolio and periodically imports fresh CAS files to keep the ledger current. | Fast, low-friction upload; confidence that re-uploading an overlapping-date-range CAS won't duplicate transactions; visibility into what date range is already covered. |

---

# User Problems

1. Users don't know that a CAS must be requested from CAMS/KFintech before it can be uploaded — the single largest source of "I clicked upload and nothing happened" confusion.
2. CAS PDFs are always password-protected, and the required password is not obvious to first-time investors.
3. A household may hold multiple passwords across CAMS accounts; a wrongly-attributed import silently corrupts another family member's data.
4. A CAS only reports transactions within the requested date range — holdings that predate the range and were partially redeemed inside it will net incorrectly unless the gap is detected and handled.
5. Users have no visibility into whether a re-upload will duplicate existing data, or which date ranges are already covered for a given family member.
6. A "Summary" CAS (holdings only, no transaction history) looks superficially valid but cannot support transaction-level features like XIRR — this failure needs a specific, actionable error rather than a generic parse failure.

---

# User Stories

- As a first-time user, I want to be clearly told that I need to request a CAS before I can upload one, so I don't get stuck on the upload step.
- As a user requesting a CAS, I want my investor details pre-filled on the CAMS request page, so I don't have to retype my password, name, and email.
- As a user returning after requesting a CAS, I want to be reminded that I have a pending request, so I don't forget to come back and finish the import.
- As a household administrator, I want to be asked to confirm which family member an uploaded CAS belongs to when there's any ambiguity, so I never misattribute financial data.
- As a returning user, I want to see the date range already covered by my last import, so I know whether I need a wider CAS or can upload a shorter/incremental one.
- As a user, I want a specific, actionable error if my PDF password is wrong, rather than a generic failure message.
- As a user, I want to be told explicitly if I've uploaded a Summary statement instead of a Detailed one, with a direct path to fix it.
- As a user, I want to see the status of my import (uploading, processing, failed, successful) at every stage, not just a spinner.

---

# Functional Requirements

## FR-1: Two-Path CAS Acquisition

**Purpose:** Let both first-time users (who need to generate a CAS) and returning users (who already have one) start an import through the same entry point without penalizing either group.

**Description:** The Mutual Fund import surface presents two tabs: **"Request CAS from CAMS"** and **"Upload Existing CAS"**, sharing a persistent two-step framing ("Step 1: Get Statement" → "Step 2: Upload"). Tab state is local UI state, not a routed page. Both tabs converge on one underlying upload/parse pipeline; the entry tab is recorded only as an analytics attribute, never as branching logic in validation or parsing.

**User Story:** As a user, I want to choose whether to request a fresh CAS or upload one I already have, from a single, unified import screen.

**Acceptance Criteria:**
- Both tabs are visible and switchable without a page navigation or URL change.
- The two-step ("Get Statement" → "Upload") framing is visible regardless of which tab is active.
- Switching tabs never discards in-progress state on the other tab (e.g., a partially entered password on the Upload tab persists if the user checks the Request tab).
- First-time users (zero existing mutual fund accounts) see this surface as the primary, full-width call to action; returning users see it demoted to a compact "Import Statement" action once at least one account exists.

**Business Rules:**
- The entry tab (`request` vs `upload`) must never gate or alter validation, parsing, or dedup logic — it is capture-only, for analytics and support debugging.
- The empty-state vs. populated-state presentation is driven by data (presence of ≥1 mutual fund account for the household), not by a separate maintained screen.

**Validation Rules:** None at this stage — no data has been submitted yet.

**Dependencies:** Family member profile data (for the CAMS prefill in FR-2); existing account/holdings data (to determine empty vs. populated state).

**Permissions:** Available to any authenticated household member with edit access to the target family member's portfolio.

**Edge Cases:**
- A household with zero family members configured must be routed to family member setup before this screen is reachable.
- A user with an in-progress pending CAS request (FR-8) reopening this screen should land with helpful context, not a blank slate.

**Failure Cases:** N/A (no submission occurs at this stage).

**Recovery Behaviour:** N/A.

**Success Metrics:**
- % of new households that reach a successful import within 24 hours of account creation.
- Tab selection distribution (request vs. upload) as a leading indicator of user segment mix.

**Analytics Events:** `cas_import_passwordel_viewed`, `cas_import_tab_selected {tab, is_first_import}`.

**Notifications:** None at this stage.

**Performance Requirements:** Tab switch renders in under 100ms; no network round-trip required to switch tabs.

**Security Requirements:** None specific to this requirement beyond standard session authentication.

**Accessibility Requirements:** Tabs must be keyboard-navigable (arrow keys within the tablist, Enter/Space to activate) and expose `role="tab"` / `aria-selected` semantics. The two-step framing text must not rely on color alone to indicate the active step.

**Audit Requirements:** None at this stage.

### Recommended implementation

For a v1 release, the "Upload Existing CAS" tab alone (plus a static help passwordel explaining how to obtain a CAS) delivers most of the user value at a fraction of the engineering cost of building and maintaining the CAMS-redirect tab (FR-2). The redirect tab should be treated as a fast-follow, not a launch blocker.

---

## FR-2: CAMS Prefill Redirect ("Request CAS from CAMS")

**Purpose:** Reduce the friction of manually filling out the CAMS CAS request form by pre-populating known investor details.

**Description:** Selecting "Request CAS from CAMS" and confirming redirects the user, in a new browser tab/window, to the CAMS CAS request page with password, name, and email pre-filled from the selected family member's profile. The prefill is constructed **entirely client-side**, using data already available to the authenticated session — no investor PII is routed through a Unifolio server purely to build this redirect.

**User Story:** As a user requesting a CAS, I want my details pre-filled on the CAMS page, so I don't have to retype my password and email.

**Acceptance Criteria:**
- Clicking "Continue to CAMS" opens the CAMS request page in a new tab/window with password, name, and email fields pre-populated where the CAMS form structure allows.
- The originating Unifolio tab remains open and transitions to a "waiting" state (FR-8) after the redirect fires.
- The date-range and PDF-password fields on the CAMS form are **never** pre-filled — these must remain fields the user consciously sets, since the user needs to recall the password thirty seconds later.
- If the field-name mapping against the CAMS form fails (structural change on CAMS' side), the redirect still succeeds as a blank/unfilled form rather than erroring or blocking the user.

**Business Rules:**
- The field-name mapping used to construct the redirect must live in a single, version-controlled configuration module, not be inlined at the call site.
- Only password, name, and email may be pre-filled. No other investor PII is transmitted as part of this redirect.
- This mechanism must never pass through a Unifolio backend endpoint; it is a pure client-side redirect construction.

**Validation Rules:**
- The selected family member must have a non-null password and email on file before this action is available; if either is missing, the user is routed to complete the family member profile first.

**Dependencies:** Family member profile (password, name, email); a maintained CAMS field-name mapping configuration; browser new-tab/window support (or, in a native shell, a secondary browser view).

**Permissions:** Requires edit access to the target family member's profile.

**Edge Cases:**
- User has pop-ups blocked: detect and show a fallback "Open CAMS" link the user can click manually.
- CAMS form structure changes and the mapping silently fails to prefill: covered by automated monitoring (see Success Metrics/Recovery below), not a hard blocker for the user in the moment.
- User closes the CAMS tab without submitting: no Unifolio-side state changes; the pending-request record (FR-8) remains open until expiry.

**Failure Cases:**
- Redirect fails to open (browser blocked navigation): show an inline error with a manual link as fallback.
- CAMS page is unreachable (CAMS-side outage): outside Unifolio control; the help passwordel should note this as a known possibility.

**Recovery Behaviour:** User can retry the redirect at any time from the same tab; retrying does not create a duplicate pending-request record if one is already open for this family member (see FR-8).

**Success Metrics:**
- Redirect success rate (page opens without client-side error).
- Prefill field-population rate, tracked via a scheduled synthetic check against the live CAMS form structure, not user-reported failures.

**Analytics Events:** `cams_redirect_initiated {family_member_id}`, `cams_redirect_field_mapping_version`.

**Notifications:** None at click time; see FR-8 for the pending-request reminder.

**Performance Requirements:** Redirect construction and navigation must complete in under 500ms from click.

**Security Requirements:**
- The redirect-construction code must be reviewed with the same scrutiny as any code handling password/PII, since it assembles PII into an outbound URL/form submission to a third party.
- No password, name, or email involved in this flow may be logged in plaintext in application or access logs.

**Accessibility Requirements:** The "Continue to CAMS" action must be a standard focusable, labeled button; opening a new tab/window must be announced to assistive technology (e.g., via `aria-label` noting it opens in a new tab).

**Audit Requirements:** Log the redirect-initiation event (actor, family member, timestamp) to the audit trail; do not log the constructed URL/form payload itself, since it contains PII.

### Recommended implementation

Maintain the CAMS field-name mapping in a single owned config file with a last-verified date, and add a scheduled synthetic monitor that loads the live CAMS form and asserts expected field names are still present — this turns a silent breakage into an alert rather than a support-ticket pattern discovered days later.

---

## FR-3: Upload Existing CAS

**Purpose:** Accept a CAS PDF the user already has, unlock it, validate it, and hand it off for parsing.

**Description:** A dropzone (with a "Choose PDF" fallback) accepts a single PDF file, paired with an inline password field. Validation proceeds in a strict, staged order — file type, password/decryption, structural CAS validation, then parse — so that each failure mode produces a distinct, actionable error rather than one generic failure.

**User Story:** As a user with a CAS PDF in hand, I want to drop it in, enter the password once, and see clear feedback if anything is wrong.

**Acceptance Criteria:**
- The dropzone accepts drag-and-drop and click-to-browse; non-PDF files are rejected immediately with a specific "PDF only" message, before any upload begins.
- The password field is present alongside the dropzone (not in a separate post-upload modal), and both file and password may be submitted together.
- On submission, the UI transitions through distinguishable states corresponding to the import state machine (see 02-CAS-App-Flow.md): uploading → processing → password required (if wrong/missing) → validation failed (if applicable) → success/failure.
- A wrong password produces a specific "incorrect password" message, distinct from any other failure, and allows the user to retry the password **without re-uploading the file**.
- A structurally invalid file (not a recognizable CAMS/KFintech CAS) produces a specific "this doesn't look like a CAS statement" message.
- A Summary-type CAS (holdings only, no transaction table) produces a specific, named error: "This looks like a Summary statement — please request a Detailed statement instead," with a link back to FR-2.

**Business Rules:**
- Validation order is fixed: file-type check → password/decryption → structural CAS validation → parse. Each stage must fail fast and independently reportable.
- The raw uploaded PDF and its password are never retained beyond the parse operation; the password is discarded immediately after the unlock attempt and is never logged, at any log level.
- A single file upload is scoped to a single family member per import attempt.

**Validation Rules:**
- File type: must be `application/pdf` by magic-byte inspection, not filename extension alone.
- File size: capped (recommended: 25MB) to prevent abuse; oversized files are rejected before upload begins.
- Password: required before decryption is attempted; empty submissions are blocked client-side.
- Structural validation: parsed document must contain recognizable CAMS/KFintech CAS headers/table structure and at least one transaction-level entry (not holdings-only).

**Dependencies:** PDF unlock/parse library (server-side); family member selection (see FR-4); the CAS import state machine (02-CAS-App-Flow.md).

**Permissions:** Requires edit access to the target family member's portfolio.

**Edge Cases:**
- User uploads a CAS for the wrong family member (attribution mismatch) — handled by FR-4's confirmation step, not by this requirement's validation stage.
- User uploads a CAS with a date range fully overlapping a previous import — handled by FR-6 (dedup), not rejected at this stage.
- Multi-password CAS covering more than one family member — flagged for the attribution step (FR-4) rather than accepted or rejected outright here.

**Failure Cases:**
- Wrong password (recoverable, see Recovery Behaviour).
- Corrupted or non-CAS PDF (structural validation failure).
- Unexpected parser exception (bucketed as a generic import failure, distinct from the two named failure types above).
- Upload interrupted by network failure before the file completes transmission.

**Recovery Behaviour:**
- Wrong password: user retypes the password against the already-uploaded file via a password-resubmission action; no re-upload required.
- Structural validation failure: user is directed back to request a Detailed statement (if Summary-type) or asked to confirm they selected the right file.
- Network interruption during upload: user retries the upload from scratch; no partial state is left behind.
- Unexpected parser failure: bounded automatic retry (see 02-CAS-App-Flow.md state machine) before surfacing as user-actionable.

**Success Metrics:**
- Upload-to-success conversion rate, segmented by failure type at each validation stage.
- Median time from upload start to processed result.

**Analytics Events:** `cas_upload_started`, `cas_upload_failed {stage, error_code}`, `cas_password_submitted`, `cas_validation_failed {reason}`, `cas_import_succeeded`.

**Notifications:** In-app status update; optional email notification on success/failure for long-running processing (see 02-CAS-App-Flow.md).

**Performance Requirements:**
- File upload acknowledgment within 2 seconds of submission for files under the size cap.
- Password re-submission (no re-upload) completes in under 3 seconds.
- End-to-end processing (upload to terminal status) target: under 60 seconds for a typical multi-year, multi-folio CAS.

**Security Requirements:**
- Uploaded PDFs are treated as untrusted input: MIME/magic-byte validation, size cap, and parsing executed in an isolated worker process, never inline in the request-handling path.
- The PDF password is held in memory only for the duration of the unlock operation and discarded immediately after; it must never be persisted to disk, database, or logs.
- If the raw PDF is retained at all post-parse, it must be encrypted at rest with a short, enforced retention window (deletion after a fixed period, e.g. 7 days) — retaining indefinitely is disallowed.

**Accessibility Requirements:** The dropzone must be operable via keyboard (a focusable "Choose PDF" control triggers the native file picker) and must not rely on drag-and-drop as the only input method. Error messages must be programmatically associated with the relevant field (`aria-describedby`) and announced to screen readers on appearance.

**Audit Requirements:** Log upload attempts (actor, family member, filename, timestamp, outcome) to the audit trail. Never log the password. Log structural-validation failure reasons (structured error codes) for support/debugging.

### Recommended implementation

Run PDF parsing in an isolated worker or queue-consumed job, never inline in the API request-handling process, so a malformed or adversarial PDF cannot degrade API availability for other users. Dedup should key on a transaction fingerprint (folio + scheme + date + type + amount), not a whole-file hash, since overlapping-but-not-identical date ranges across successive CAS exports are the common case, not the exception.

---

## FR-4: Family Member Attribution

**Purpose:** Ensure every imported CAS is correctly and unambiguously associated with the right family member, preventing cross-member data corruption.

**Description:** Attribution is resolved primarily by matching the password embedded in the parsed CAS against password values already on file for family members in the household. If the parsed password matches a known family member, the import proceeds against that member with a visible confirmation. If it doesn't match, or the CAS contains multiple passwords (a well-documented CAMS/KFintech behavior for linked accounts), the user is explicitly prompted to confirm or select the correct family member before the import is committed.

**User Story:** As a household administrator, I want Unifolio to confirm which family member a CAS belongs to, so I never accidentally attribute one person's data to another.

**Acceptance Criteria:**
- Before an import is committed, the system displays the resolved family member and requires explicit confirmation if the password match is not a clean single match.
- If the currently-selected family member (context the user was in when they started the import) does not match the parsed password, a confirmation dialog is shown: "This looks like [Name]'s statement — import here for [Name] instead?"
- A CAS containing multiple distinct passwords prompts the user to attribute each covered folio group to the correct family member, or to import only the subset matching the currently selected member.
- An unrecognized password (no match to any existing family member) prompts an "Add new family member" fallback flow rather than blocking the import outright.

**Business Rules:**
- No import may be committed to a family member's ledger without either a clean automatic password match or explicit user confirmation.
- password matching is exact-match only; no fuzzy or partial matching is permitted, given the correctness stakes.

**Validation Rules:** Parsed password must be a well-formed 10-character alphanumeric password string before matching is attempted; malformed password extraction is treated as a parse-quality issue and routed to manual selection.

**Dependencies:** Family member profile data (password field); the CAS parser's password-extraction output.

**Permissions:** Requires edit access to all family members being considered for attribution (i.e., the acting user must have household-level access, not just single-member access).

**Edge Cases:**
- A family member has no password on file yet (newly added, incomplete profile) — treated as "unrecognized," routed to manual confirmation/profile completion.
- Two family members share a password in the system due to a data-entry error — surfaced as a data-integrity warning, not silently resolved.
- A CAS covers a minor's folios linked to a parent's email/password — treated as a multi-password case requiring explicit per-folio attribution.

**Failure Cases:** Ambiguous or unmatched attribution that the user abandons without resolving — the import remains uncommitted (see Recovery Behaviour).

**Recovery Behaviour:** An unresolved attribution does not commit any data; the import can be resumed later from the import's status view, re-entering the attribution step without needing to re-upload the file (as long as the underlying file/parse result is still within its retention window).

**Success Metrics:**
- Rate of imports requiring manual attribution confirmation (leading indicator of multi-password household complexity).
- Rate of user-corrected auto-attributions (measures false-positive risk of the password-match heuristic).

**Analytics Events:** `cas_attribution_auto_matched {family_member_id}`, `cas_attribution_confirmation_shown`, `cas_attribution_manual_selected`, `cas_attribution_mismatch_corrected`.

**Notifications:** None beyond in-flow confirmation UI.

**Performance Requirements:** Attribution resolution (password match lookup) completes in under 1 second following successful parse.

**Security Requirements:** password values used for matching must be compared using values decrypted only in-memory at match time, consistent with the password encryption-at-rest policy defined in FR-3 and 03-Stocks-PRD.md's equivalent requirement.

**Accessibility Requirements:** The attribution confirmation dialog must trap focus appropriately, be dismissible via keyboard (Escape), and clearly label both the detected name and the action being confirmed.

**Audit Requirements:** Every attribution decision (auto-matched or manually confirmed/corrected) must be logged with actor, family member, password-match method, and timestamp — this is the audit trail that answers "why did this data end up under this family member" if ever disputed.

### Recommended implementation

Treat password-in-parsed-document as the primary signal, but never auto-commit without a visible confirmation step when there is any ambiguity — a multi-password CAS or an unmatched password. Silent misattribution is a single-bug trust failure in a household financial product and is cheap to prevent with one confirmation dialog.

---

## FR-5: CAS Import Lifecycle & Status Tracking

**Purpose:** Give every CAS import a durable, queryable, named status at every stage, so both users and support/engineering can answer "what is happening with this import" without reading logs.

**Description:** Every import attempt is represented by a persistent record with an explicit status field cycling through a defined state machine (fully specified in `02-CAS-App-Flow.md`): Not Started, Requesting CAS, Waiting for User, Upload Started, Password Required, Validation Failed, Processing, Retry Pending, Import Successful, Import Failed, Expired. Status is surfaced to the user as a specific, named state, not a generic spinner-or-error binary.

**User Story:** As a user, I want to see exactly what stage my import is at, so I know whether to wait, retry, or take action.

**Acceptance Criteria:**
- Every import record exposes a queryable status via API, reflected in the UI in real time (poll or push).
- Terminal states (`Import Successful`, `Import Failed`, `Expired`) are unambiguous and do not silently revert.
- Transient internal states (e.g., queued-for-retry) are not exposed as distinct user-facing states where doing so would confuse rather than clarify — they are collapsed into "still processing" from the user's perspective.
- Each import's full state-transition history is retrievable for support/debugging purposes.

**Business Rules:**
- State transitions must follow a defined, enforced transition table; invalid transitions (e.g., `Import Successful` → `Password Required`) must be rejected at the application layer, not merely avoided by convention.
- A `Processing` timeout (recommended: 5 minutes) automatically transitions to `Retry Pending` or `Import Failed` rather than leaving an import indefinitely in-flight.

**Validation Rules:** N/A — this requirement governs internal state, not user input.

**Dependencies:** Queue/worker infrastructure; the parser's structured error output (feeds `ValidationFailed`/`ImportFailed` detail).

**Permissions:** Status is visible only to household members with access to the relevant family member's data.

**Edge Cases:** A worker crash mid-processing must not leave an import permanently stuck in `Processing` — a timeout-based reconciliation job detects and transitions stale in-flight records.

**Failure Cases:** See `02-CAS-App-Flow.md` for the full failure-state catalogue (`PasswordRequired`, `ValidationFailed`, `ImportFailed`).

**Recovery Behaviour:** Defined per-state in `02-CAS-App-Flow.md`; in general, recoverable states offer an in-place retry action without discarding already-valid progress (e.g., a valid file doesn't need re-uploading just to retry a password).

**Success Metrics:** Time-in-state distribution per state (identifies funnel bottlenecks); failure rate by state.

**Analytics Events:** `cas_import_state_changed {import_id, from_state, to_state}`.

**Notifications:** Status changes to a terminal state (success/failure) trigger an in-app notification; optionally an email/push notification for imports that complete after the user has navigated away.

**Performance Requirements:** Status queries return in under 200ms (p95); status changes are reflected in the UI within 2 seconds of the underlying transition (via polling interval or push).

**Security Requirements:** Status/error detail exposed to the client must be a structured, sanitized error code and message — raw internal exceptions or stack traces must never be returned to the client.

**Accessibility Requirements:** Status changes must be announced via an `aria-live` region so screen reader users are notified of state transitions without needing to poll the UI manually.

**Audit Requirements:** Every state transition is logged with timestamp and (where applicable) triggering actor or system event, forming the complete lifecycle audit trail for a given import.

### Recommended implementation

Formalize the state machine as an explicit, named enum with a defined transition table enforced in code — not implicit control flow inferred from combinations of boolean flags. Instrument time-in-state and failure-rate-by-state from day one; this is cheap to add early and expensive to retrofit, and it is the primary tool for diagnosing funnel drop-off (e.g., a spike in time spent in "Waiting for User" is a direct signal to invest in the reminder mechanism in FR-8).

---

## FR-6: Duplicate Detection & Idempotent Ingestion

**Purpose:** Prevent re-imported or overlapping-date-range CAS files from double-counting transactions in the ledger.

**Description:** Every parsed transaction is assigned a deterministic fingerprint derived from folio number, scheme, date, transaction type, and amount. Before committing a transaction to the ledger, the system checks for an existing transaction with the same fingerprint for the same folio; matches are skipped, not duplicated.

**User Story:** As a returning user, I want to re-upload a CAS covering a wider or overlapping date range without worrying about my numbers doubling.

**Acceptance Criteria:**
- Re-uploading an identical CAS produces zero new transactions and a clear "no new transactions found" result, not a silent no-op or an error.
- Uploading a CAS with a partially overlapping date range imports only the non-overlapping transactions.
- The import result summary distinguishes "transactions added" from "transactions skipped as duplicates" so the user understands what happened.

**Business Rules:**
- Fingerprint composition is fixed: folio number + scheme identifier + transaction date + transaction type + amount. This must be applied consistently across all CAS import paths and, where applicable, other ingestion paths (e.g., manual entry) that could contribute to the same ledger.
- Deduplication happens per-transaction, never per-file — file-level hash comparison is explicitly disallowed as the primary dedup mechanism, since it fails on the common overlapping-range case.

**Validation Rules:** A fingerprint collision with differing amounts/types for otherwise-matching folio+scheme+date is treated as a data-quality anomaly and flagged for review rather than silently accepted as either a duplicate or a new transaction.

**Dependencies:** The transaction ledger schema (folio, scheme, date, type, amount indexed for fast fingerprint lookup); the parser's structured transaction output.

**Permissions:** N/A — internal system behavior, not user-facing configuration.

**Edge Cases:**
- Two CAS files from different RTAs (CAMS and KFintech) covering the same folio with slightly different formatting of the same underlying transaction — the fingerprint fields must be normalized (e.g., consistent date formatting, consistent amount rounding) before comparison.
- A genuinely corrected/reissued CAS containing a revised transaction amount for what looks like the same transaction — flagged as an anomaly (see Validation Rules), not auto-resolved.

**Failure Cases:** Fingerprint collision with conflicting data (see Validation Rules) is not silently resolved in either direction.

**Recovery Behaviour:** Flagged anomalies are surfaced to the user (or, if a household-review workflow exists, to the household administrator) for manual resolution.

**Success Metrics:** Duplicate-skip rate per import (expected to be non-trivial for regular re-importers); anomaly-flag rate (should trend near zero in steady state).

**Analytics Events:** `cas_import_transactions_added {count}`, `cas_import_transactions_skipped_duplicate {count}`, `cas_import_fingerprint_anomaly_detected`.

**Notifications:** None beyond the in-flow import result summary.

**Performance Requirements:** Fingerprint lookup must be indexed (composite index on folio + scheme + date + type + amount) to keep dedup checks sub-second even against a multi-year transaction history.

**Security Requirements:** N/A beyond standard data-access controls already governing the transaction ledger.

**Accessibility Requirements:** The "added vs. skipped" import summary must be presented as structured, readable text (not solely a visual diff or color-coded indicator).

**Audit Requirements:** Every transaction commit references its source `CASImport` record (`sourceCASImportId`) for full traceability of which import contributed which ledger entry.

### Recommended implementation

Index the transaction table on `(folioId, date, type, amount)` to keep the fingerprint lookup fast, and add a database-level constraint that makes accidental duplicate ingestion structurally harder to introduce, not solely dependent on the application layer remembering to check.

---

## FR-7: Coverage Gap / Opening Balance Detection

**Purpose:** Detect and surface the structural limitation that a CAS only reports transactions within its requested date range, which can cause a folio's computed holdings to be understated or net incorrectly if an earlier purchase falls outside the imported range.

**Description:** After each import, the system evaluates each affected folio's transaction history for internal consistency — specifically, any redemption, switch-out, or SIP-stop event with no matching prior purchase in the ledger for sufficient units. Folios failing this check are flagged with a coverage-gap indicator rather than allowed to silently net to an incorrect balance.

**User Story:** As a user, I want to be warned if my imported CAS doesn't cover my full holding history, so my portfolio numbers aren't silently wrong.

**Acceptance Criteria:**
- Any folio where a redemption/switch-out event has no matching prior purchase quantity in the ledger is flagged with a visible "coverage gap" indicator on that folio's view.
- The flag includes an actionable next step: request a CAS with a wider date range, or provide a manual opening-balance entry.
- The flag is cleared automatically once a subsequent import (or manual entry) resolves the gap.
- This check runs automatically after every successful import commit — it is not a separate, user-triggered action.

**Business Rules:**
- A folio's computed net units may never be allowed to silently go negative in the UI without a coverage-gap flag being raised — this is a hard invariant, not a best-effort warning.
- Manual opening-balance entries, once provided, are stored as a distinct, clearly-labeled transaction type (`OPENING_BALANCE`) rather than fabricated as a synthetic purchase transaction indistinguishable from real ledger data.

**Validation Rules:** A manual opening-balance entry requires, at minimum, folio, scheme, units, and an as-of date; amount/NAV are optional but recommended for accurate cost-basis calculation.

**Dependencies:** FR-6 (accurate deduplication is a prerequisite for this check to be meaningful); the transaction ledger.

**Permissions:** Requires edit access to the affected family member's portfolio to resolve a flagged gap.

**Edge Cases:**
- A folio that is genuinely fully redeemed and legitimately shows zero units should not be flagged — the check specifically targets redemptions exceeding known purchased units, not zero-balance folios reached through a complete, well-covered transaction history.
- A folio only ever partially imported (household administrator intentionally imports a subset of family members' data first) may show transient gaps that resolve once remaining members are imported — the flag should not read as alarming/urgent in this expected case, though it should still be visible.

**Failure Cases:** N/A — this is a detection mechanism, not a user action that can itself fail, beyond standard system errors during the post-import evaluation job.

**Recovery Behaviour:** User either imports a wider-range CAS (routes back to FR-2/FR-3) or manually enters an opening balance; both paths clear the flag on the next evaluation pass.

**Success Metrics:** % of folios with an unresolved coverage gap older than 7 days (should trend toward zero); rate of gap resolution via wider-CAS-import vs. manual entry.

**Analytics Events:** `coverage_gap_detected {folio_id}`, `coverage_gap_resolved {folio_id, resolution_method}`.

**Notifications:** In-app flag on the affected folio; optional digest notification summarizing all households/folios with unresolved gaps, for household administrators.

**Performance Requirements:** The coverage-gap evaluation job completes within the same processing window as the import itself (target: adds no more than 5 seconds to end-to-end import time).

**Security Requirements:** N/A beyond standard access controls on the affected data.

**Accessibility Requirements:** The coverage-gap indicator must not rely on color alone (e.g., a red dot) — it must include text or an icon with an accessible label.

**Audit Requirements:** Log gap detection and resolution events, including the resolution method (wider import vs. manual entry) and the specific opening-balance values entered, if applicable.

### Recommended implementation

This check should run as a first-class, automatic step after every import commit, not a background data-quality job the user has to discover separately — surfacing it plainly ("This folio may have holdings from before your imported CAS range") directly prevents the silent-netting-to-zero failure mode that erodes trust in computed portfolio values.

---

## FR-8: Pending Request Management & Expiry

**Purpose:** Track the gap between a user starting a CAS request (FR-2) and completing the corresponding upload, so the system can remind the user and so stale, abandoned requests don't accumulate indefinitely as ambiguous state.

**Description:** Starting a CAMS request creates a `PendingCASRequest` record scoped to the initiating family member. The record persists through the external CAMS navigation and email-delivery wait, is visible to the user as a "waiting" indicator, and automatically expires after a defined window (recommended: 7 days) if never completed.

**User Story:** As a user who requested a CAS, I want to be reminded that I have a pending request so I don't forget to come back and upload it.

**Acceptance Criteria:**
- Starting a CAMS request creates a pending-request record and shows a persistent "waiting for your CAS email" indicator on the import surface.
- Returning to the app while a pending request is open defaults the user to a helpful state (e.g., the Upload tab, with the pending context visible) rather than a blank import screen.
- A pending request older than the expiry window transitions to an `Expired` status automatically; this does not block the user from starting a fresh request at any time.
- Starting a new request for the same family member while one is already pending does not create a duplicate record — it either reuses or explicitly supersedes the existing one.

**Business Rules:**
- Expiry window is configurable (system default: 7 days) but must not be indefinite — unresolved pending requests must not accumulate without bound.
- Expiry is a data-hygiene and analytics classification, not a user-facing failure — an expired request never blocks or penalizes the user; it simply stops being surfaced as "waiting" and is reclassified for funnel-conversion measurement.

**Validation Rules:** N/A.

**Dependencies:** FR-2 (creates the pending record); a scheduled cleanup job for expiry transitions.

**Permissions:** Visible only to users with access to the relevant family member.

**Edge Cases:** A user starts a request, abandons it, and later starts a fresh request for the same family member without ever resolving the first — the system should not present two conflicting "waiting" indicators.

**Failure Cases:** N/A — this is a passive tracking mechanism.

**Recovery Behaviour:** The user can complete the upload at any time before expiry from the persisted "waiting" state; after expiry, starting a fresh request is a normal, unpenalized action.

**Success Metrics:** Pending-to-completed conversion rate; median time-to-completion for requests that do convert; expiry rate (proxy for abandonment).

**Analytics Events:** `pending_cas_request_created {family_member_id}`, `pending_cas_request_completed`, `pending_cas_request_expired`.

**Notifications:** Optional delayed reminder notification (recommended: +2 hours after request creation) nudging the user to check their email and complete the upload — a meaningful improvement over a purely passive indicator, since it actively reduces the number of users who simply forget to return.

**Performance Requirements:** The expiry-scan job runs at least daily and completes without measurably impacting other scheduled jobs.

**Security Requirements:** N/A beyond standard access controls.

**Accessibility Requirements:** The "waiting" indicator/banner must be perceivable without relying on animation or color alone, and must be reachable via standard keyboard/screen-reader navigation of the import surface.

**Audit Requirements:** Log creation, completion, and expiry transitions for each pending-request record.

### Recommended implementation

Make the pending-request state a visible, first-class object in the UI, not just an internal flag used to default a tab selection — a small "Waiting for your CAS email? We'll be here" banner actively signals that the product remembers where the user left off, which materially reduces perceived friction versus a silent default.

---

## FR-9: Import History Surface

**Purpose:** Give users a persistent, per-family-member view of what has already been imported, preventing duplicate-import anxiety and surfacing coverage gaps proactively.

**Description:** Every family member's mutual fund surface displays a "last imported: [date range], [import date]" indicator, along with access to a simple history list of past import attempts and their outcomes.

**User Story:** As a returning user, I want to see what date range I've already imported, so I know whether I need to import again and with what range.

**Acceptance Criteria:**
- The "last imported" indicator is visible on every surface where import is initiated (empty state and populated state alike).
- A history view lists past import attempts with date, source (request vs. upload), status, and (for successful imports) transactions added/skipped counts.
- The indicator updates immediately upon a new successful import, without requiring a page refresh.

**Business Rules:** The displayed "date range" reflects the range covered by the underlying CAS document, not merely the date the import was performed.

**Validation Rules:** N/A.

**Dependencies:** FR-5 (import status records), FR-6 (transaction counts for the summary).

**Permissions:** Visible to any household member with view access to the relevant family member.

**Edge Cases:** A family member with multiple non-contiguous imported ranges (e.g., imported January–June, then September–December, with an August gap) should display the actual covered ranges, not a single misleading combined range.

**Failure Cases:** N/A — a read-only surface.

**Recovery Behaviour:** N/A.

**Success Metrics:** Reduction in duplicate-import support tickets ("did my import work") after this surface ships, measured via ticket-tagging.

**Analytics Events:** `import_history_viewed`.

**Notifications:** None.

**Performance Requirements:** History list loads within 1 second for a typical household (under 50 historical import attempts).

**Security Requirements:** N/A beyond standard access controls.

**Accessibility Requirements:** History list must be presented as a semantic, screen-reader-navigable list/table, not solely a visual timeline.

**Audit Requirements:** N/A beyond the underlying FR-5 audit trail this surface reads from.

### Recommended implementation

This is a comparatively low-cost, high-leverage addition absent from the competitive baseline this feature set was reverse-engineered against — it directly addresses the coverage-gap problem (FR-7) and the duplicate-import anxiety problem (FR-6) with a single, always-visible UI element.

---

# Non-Functional Requirements

| Category | Requirement |
|---|---|
| Availability | Import submission and status endpoints target 99.9% availability; a queue outage degrades to delayed processing, not failed submissions. |
| Scalability | Parsing workers must scale horizontally; per-account/per-import job isolation must not create cross-tenant contention. |
| Data retention | Raw uploaded PDFs, if retained at all, are deleted after a fixed window (recommended: 7 days) post-parse; PDF passwords are never retained beyond the unlock operation. |
| Observability | Every state transition, validation failure, and dedup/coverage-gap decision must be logged in a structured, queryable form. |
| Internationalization | All user-facing copy must be externalized for future localization, even if English-only at launch. |
| Auditability | Every commit to the transaction ledger must be traceable to its originating `CASImport` record and the actor who initiated it. |

---

# Out of Scope

- CAS PDF parsing logic itself (transaction extraction algorithm) — covered by a separate parser-specific specification.
- Automated CAS retrieval via email inbox integration (e.g., Gmail OAuth-based auto-fetch) — not planned for this feature; the acquisition step remains manual.
- Automated/scripted CAMS form submission on the user's behalf (auto-generation of the CAS without user-initiated submission) — explicitly excluded on compliance and trust grounds.
- Stock/Demat holdings import — covered in `03-Stocks-PRD.md`.
- Cross-household or cross-family-member portfolio rollups — covered in `05-Family-Portfolio-PRD.md`.
- Tax-lot-level cost-basis method selection (FIFO vs. weighted average as a user-configurable option) — v1 ships with a single default methodology.

---

# Future Enhancements

- Gmail/email-inbox integration for automatic CAS retrieval, with explicit read-only OAuth consent, as an opt-in alternative to the manual request-and-upload flow.
- Support for KFintech-specific CAS variants alongside CAMS, if not already unified in the parser.
- User-configurable cost-basis methodology (FIFO / weighted-average / specific-lot) for tax-optimization power users.
- Bulk/batch import across multiple family members in a single flow.
- Proactive, scheduled reminder to re-import CAS on a recurring cadence (e.g., quarterly) rather than purely on-demand.

---

# Risks

| Risk | Impact | Mitigation |
|---|---|---|
| CAMS form structure changes, silently breaking the prefill redirect (FR-2) | Degraded UX for the request path; no functional blocker since fields simply appear unfilled | Scheduled synthetic monitoring against the live CAMS form; isolate mapping in one config file for fast patching |
| Misattribution of a family member's data (FR-4) | Severe trust damage; potential data-correctness dispute | Mandatory confirmation step on any non-clean password match; full audit trail |
| Coverage-gap logic (FR-7) produces false positives/negatives at scale | User confusion or, worse, silently wrong portfolio values | Conservative detection logic (flag rather than auto-correct); manual resolution path always available |
| Parser exceptions on malformed/adversarial PDFs | Worker instability or security exposure | Isolated worker execution, strict input validation, bounded retry |
| CAMS/KFintech introduces stronger bot defenses affecting even legitimate prefill construction | Request path degrades to a plain, unfilled redirect | Design already treats prefill as best-effort, non-blocking |

---

# Implementation Priorities

| Priority | Features | Rationale |
|---|---|---|
| P0 (Launch-blocking) | FR-3 (Upload Existing CAS), FR-4 (Attribution), FR-5 (Lifecycle/Status), FR-6 (Dedup) | Core, minimum-viable import pipeline; nothing else functions without these. |
| P1 (Near-term) | FR-7 (Coverage Gap Detection), FR-9 (Import History Surface) | Directly addresses known correctness/trust risks; high leverage relative to cost. |
| P2 (Fast-follow) | FR-1 (Two-Path UI), FR-2 (CAMS Prefill Redirect), FR-8 (Pending Request Management) | Valuable UX improvement for first-time users, but the product is functional without it if users are given clear static guidance instead. |
