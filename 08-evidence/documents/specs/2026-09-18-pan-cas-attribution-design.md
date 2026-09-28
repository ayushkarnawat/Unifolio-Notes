# Design Spec: PAN Persistence, CAS File Storage, and PAN-Based Attribution

**Date:** 2026-09-18
**Status:** Approved for implementation planning (scope agreed across the discussion this spec summarizes)
**Supersedes for implementation purposes:** `Docs/orchestration/pan-and-cas-file-storage-design-summary.md` (that doc is the discussion history; this is the resulting design)

## Context

Today, the CAS import flow parses PAN and immediately discards the raw value (masks it, displays it, never stores it), never persists the uploaded CAS PDF, and attributes an imported statement to a household member primarily by folio-number reuse, falling back to fuzzy name matching and an email-based "self" check. All three behaviors are deliberate per **ADR-004** ("No raw CAS PDF storage, ever. No PAN persistence, ever."), enforced by a CI guard test (`backend/tests/models/test_no_pan_field.py`).

This spec reopens ADR-004 to: persist the real PAN (encrypted, recoverable), persist the raw CAS file for a bounded retention window, and replace name/email-based attribution with PAN-based attribution.

## Scope for this implementation pass

**In scope**, built to run correctly and be fully tested locally tonight/tomorrow morning:
- Schema + migration for encrypted PAN storage and file-reference tracking.
- Application-level envelope encryption and a deterministic lookup hash for PAN.
- A `FileStorage` abstraction with a local-disk implementation, expiry tracking, and a sweep mechanism.
- The attribution algorithm rewritten to match by PAN, with folio-number as a documented fallback.
- Same-household auto-attribution-with-disclaimer; cross-account hard block.
- Updated ADR-004, schema doc, PRD, and repo-root docs; rewritten CI guard test.
- Full unit test coverage for all of the above.

**Explicitly out of scope for this pass** (documented as follow-up, not built now):
- Actually provisioning/deploying AWS resources (S3 bucket, Secrets Manager secret) via Terraform apply. The code is written against interfaces so this is a swap-in later, not a redesign now — see "Production mapping" below.
- A live scheduled job (EventBridge Scheduler) for file expiry sweeping — a callable sweep function is built and tested; wiring it to a schedule is deferred to when the already-staged `infra/modules/scheduler` module is actually applied.
- Any in-app cross-account **merge** feature. Cross-account PAN collisions are blocked with a message; no self-serve resolution path.
- Any API or UI that returns a decrypted/raw PAN. The PAN stays masked in every user-facing surface, exactly as today; encryption/decryption is server-side-only, used solely for matching.

## Production mapping (for defending this design, not built tonight)

Confirmed by reading the actual staged Terraform (`infra/envs/staging/main.tf`, `infra/modules/backend/main.tf`, `infra/modules/security`):
- A customer-managed KMS key is already staged (`module.security.kms_key_arn`), explicitly earmarked in its own description for "Phase 2 RDS and Phase 3 Secrets Manager resources."
- The backend ECS task definitions already use AWS's `secrets` block pattern (pull a value from Secrets Manager into a container env var, decrypted via that KMS key, gated by a scoped IAM policy) for the RDS master password today.
- **Production path for the PAN-encryption key:** one new Secrets Manager secret, encrypted by the already-staged KMS key, injected into the backend container via the same `secrets` block pattern already used for the DB password. No new KMS key, no new IAM pattern.
- **Production path for the file:** a new, purely additive S3 bucket (private, SSE-KMS, Lifecycle rule for 30-day expiry) — no existing bucket to reuse for this, unlike the key.
- Nothing above is live yet (no `.tfstate` exists); none of this spec's local-dev implementation touches or conflicts with what's staged.

## Data model

### `household_members` (new columns)
- `pan_encrypted` (`bytea`/`text`, nullable) — envelope-encrypted real PAN. Nullable because existing members and first-time imports may not have a PAN on file yet.
- `pan_lookup_hash` (`text`, nullable, **indexed**) — deterministic HMAC-SHA256 of the normalized PAN (uppercase, stripped). Used for all equality matching, within-household and system-wide (cross-account check), so the app never needs to decrypt another user's PAN to compare.

### `imports` (new columns)
- `file_reference` (`text`, nullable) — opaque storage key/path for the retained raw file (e.g. `cas-files/{user_id}/{import_id}.pdf` locally; maps directly to an S3 key in production).
- `file_expires_at` (`timestamp`, nullable) — `uploaded_at + 30 days`; the sweep mechanism deletes any file whose `file_reference` is non-null and `file_expires_at` has passed, then nulls both columns.

### Migration
One new Alembic migration adding these four columns (all nullable — no backfill required, no default value computation needed for existing rows).

## Encryption design

- **Envelope encryption, AES-256-GCM.** A `PanCipher` component encrypts/decrypts using a symmetric key obtained from a `KeyProvider` interface.
  - `EnvVarKeyProvider` (used tonight/locally): reads the key from an env var (e.g. `PAN_ENCRYPTION_KEY`, 32 bytes, base64-encoded), documented in `.env.example`.
  - Production maps to a `SecretsManagerKeyProvider` (not built now) reading the same shape of key from the Secrets Manager secret described above — the `PanCipher` and all calling code are unchanged by this swap.
- Stored format: `base64(nonce || ciphertext || tag)` in `pan_encrypted`.
- **Never logged.** `PanCipher` and all attribution code follow the existing repo pattern (`parser.py`'s `mask_pan`) of never allowing a raw PAN into a log statement, exception message, or `raw_parser_output`-style persisted blob.
- **Lookup hash**: `HMAC-SHA256(key=lookup_pepper, msg=normalized_pan)`, hex-encoded. `lookup_pepper` comes from the same `KeyProvider` (a second, distinct key/secret from the encryption key — never reuse one key for both encryption and hashing).

## File storage design

- `FileStorage` protocol: `save(key: str, data: bytes) -> str`, `read(reference: str) -> bytes`, `delete(reference: str) -> None`.
- `LocalFileStorage` (used tonight): writes under a git-ignored local directory (e.g. `var/cas_files/`, outside any web-servable path), keyed by `{user_id}/{import_id}.pdf`.
- On successful CAS parse in the async import path (`lifecycle_service.py`), after parsing completes, the original `pdf_bytes` are saved via `FileStorage.save(...)`, and `imports.file_reference` / `imports.file_expires_at` are set. **This does not change the existing temp-file-delete-after-parse behavior** — the temp file used to hand a filesystem path to `casparser` is still deleted immediately after parsing; the *separate*, deliberate save to `FileStorage` is the new, intentional 30-day copy.
- Sweep function: `expire_stored_files(db) -> int` — queries `imports` where `file_expires_at < now()` and `file_reference IS NOT NULL`, calls `FileStorage.delete(...)` for each, then nulls both columns. Built as a plain callable + a thin CLI/management-command entry point tonight; wiring it to `infra/modules/scheduler` is a follow-up once that module is applied.

## Attribution algorithm (rewrite of `attribution.py`)

> **Superseded 2026-09-24** by `2026-09-24-pan-at-upload-attribution-design.md`:
> `attribution.py` was removed; the PAN check moved to upload time
> (`pan_claims.py`) and Confirm Import no longer prompts. The rest of this
> spec (PAN persistence, CAS file retention) still applies.

New precedence in `resolve_attribution()`:
1. **PAN hash match** — compute `pan_lookup_hash` from the parsed CAS's PAN (if present). Query all household members across the **entire system** for that hash.
   - Match is a member of the **same household** (same `user_id`) → `AUTO_MATCHED`, with `prompt_message` set to a disclaimer (e.g. "Matched to {name} by PAN — attaching this statement to their account.") shown alongside the auto-attribution, not blocking it.
   - Match is a member of a **different account** → new status `CROSS_ACCOUNT_PAN_BLOCKED`; the import is rejected before any DB write, with a message stating this PAN is already tracked under another account and to contact support. No override path.
   - No match anywhere → proceed to step 2.
2. **Folio-number + AMC match** (existing logic, kept as-is) — used only when the CAS has no parseable PAN at all (rare parser-limitation case). If matched, and the matched member has no `pan_lookup_hash`/`pan_encrypted` yet, this import's parsed PAN (if any — there may genuinely be none) cannot backfill it either; this is a documented edge case, not silently swallowed.
3. **No match** → existing `UNRECOGNIZED_MEMBER` prompt (add new member / manual selection), unchanged.

**Name and email are removed as matching signals entirely.** `HouseholdMember.name` remains stored and displayed (labels, UI) but is never read by `resolve_attribution()` or `detect_cross_account_duplicate()` going forward — both are rewritten to use only the PAN-hash and folio-key logic above.

**Backfill:** whenever an import is confirmed and the resolved household member's `pan_encrypted`/`pan_lookup_hash` are null but this CAS had a parseable PAN, store it on that member as part of the confirm transaction. This is how existing (pre-this-feature) household members and brand-new members acquire a PAN on record — there is no separate migration/backfill script.

`detect_cross_account_duplicate()` is folded into the same PAN-hash check in step 1 rather than kept as a second, separately-reasoned name-based function — it was already a duplicate of the same "search other accounts" concern the new step 1 handles.

## Documentation updates required

Reopen and rewrite, in this pass:
- `Docs/PRDs/ADR-Technical-Stack-Decisions.md` (ADR-004) — new Accepted decision superseding "no PAN, no raw file," with the DPDP-Act consideration addressed (real PAN and file are both encrypted at rest / bounded-retention, minimizing exposure versus the rejected alternative of indefinite plaintext retention).
- `Docs/PRDs/Database-Schema-Unifolio.md` — Design Principle 3, the Data Classification & Security table, Open Questions/Revision History.
- `Docs/PRDs/PRD-01-CAS-Parser-v2.md` — FR-2, FR-4 (attribution), Technical Considerations.
- `AGENTS.md`, `PRODUCT.md`, `decisions.md`, `database.md` — the repeated "no PAN, no raw file" one-liners.
- `backend/tests/models/test_no_pan_field.py` — rewritten to assert the *opposite* invariant deliberately: `pan_encrypted`/`pan_lookup_hash` exist on `HouseholdMember`, but no column anywhere stores plaintext PAN, and no test/fixture ever asserts on a decrypted value outside the encryption/attribution unit tests themselves.

## Testing plan

- **`PanCipher`**: round-trip encrypt/decrypt; ciphertext is non-deterministic (different nonce each call) for the same input; wrong key fails to decrypt (raises, doesn't silently return garbage).
- **Lookup hash**: deterministic for the same PAN regardless of case/whitespace; different PANs never collide (a `hashlib`-based sanity check, not an exhaustive proof).
- **Attribution**: same-household PAN match → `AUTO_MATCHED` with disclaimer; cross-account PAN match → blocked, no DB write occurs; no-PAN-parsed CAS falls back to folio match; no match at all → `UNRECOGNIZED_MEMBER`; backfill actually persists `pan_encrypted`/`pan_lookup_hash` on confirm.
- **File storage**: save then read round-trips bytes; `expire_stored_files` deletes only past-expiry rows and leaves others untouched; delete is idempotent (calling it twice, or on an already-missing reference, doesn't raise).
- **Migration**: upgrade adds all four columns nullable; downgrade removes them cleanly.
- **Guard test**: rewritten `test_no_pan_field.py` passes against the new schema and would fail if anyone reintroduced a plaintext PAN column.

## Open items carried into implementation (not blocking, but to flag during the walkthrough)

- The env-var-sourced key (`EnvVarKeyProvider`) is explicitly a local/demo stand-in, not the production key source — call this out proactively rather than waiting to be asked.
- The sweep mechanism is a callable + CLI command tonight, not a live cron/EventBridge schedule — same reasoning.
