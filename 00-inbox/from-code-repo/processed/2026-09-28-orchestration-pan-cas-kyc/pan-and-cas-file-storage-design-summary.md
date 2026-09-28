# PAN Persistence + CAS File Storage + PAN-Based Attribution — Discussion Summary

**Status:** Pre-decision summary, written for the user to review and decide on. Nothing in this document has been implemented. No code, schema, or infra has been changed as part of this discussion.

**Date:** 2026-09-18

---

## 1. What was asked for

Three related changes to the CAS (Consolidated Account Statement) import flow:

1. **Store the PAN** extracted from an imported CAS file (currently discarded after masking).
2. **Store the uploaded CAS file itself** (currently discarded after parsing).
3. **Attribute CAS files to household members by PAN**, not by name/email — a user should be able to type any name (first name, nickname, anything) and it shouldn't matter; only PAN should determine whose account a statement belongs to.

---

## 2. Current state (verified by reading the actual code, not assumed)

### PAN — parsed, masked, never persisted
- The parser (`backend/app/services/import_/parser.py`) already extracts PAN from the CAS (`parser.py:183`), but immediately masks it (`ABCDE****F` style) and discards the raw value.
- Only the masked form ever reaches the API response (`ImportPreviewResponse.pan_masked`) or the frontend.
- **No table anywhere has a PAN column.** A CI guard test (`backend/tests/models/test_no_pan_field.py`) actively fails the build if one is ever added.

### The uploaded file — never persisted
- The PDF bytes are read into memory per-request, written to an OS temp file only because the parsing library (`casparser`) requires a filesystem path, and unconditionally deleted in a `finally` block right after parsing.
- One narrow exception: a 15-minute in-process memory buffer (`buffer_cache.py`) used only to support "wrong password, try again" UX without forcing re-upload. Never touches disk/S3/DB, wiped on success/failure/expiry.

### Attribution — folio number first, then fuzzy name match, then email (self only)
Actual precedence in `backend/app/services/import_/attribution.py`:
1. **Folio number + AMC match** (if this CAS's folio was already linked to a household member from a previous import) — checked first, highest priority.
2. **Fuzzy name match** — normalizes and does substring-contains matching between the CAS investor name and each household member's stored name. Fragile: nicknames, initials, similar names between family members can all cause mismatches.
3. **Email fallback, "self" only** — if CAS investor email equals the logged-in user's account email, auto-matches to whichever household member is marked "self." Never used for other family members.
4. No match on any of the above → prompts the user to confirm or add a new family member.

A **separate, cross-account** check (`detect_cross_account_duplicate`) independently warns (non-blocking, today) if a folio or name matches someone in a *different* Unifolio account.

### Why none of this exists today — this is a locked decision, not a gap
**ADR-004** (`Docs/PRDs/ADR-Technical-Stack-Decisions.md`) and a matching section of `Docs/PRDs/Database-Schema-Unifolio.md` explicitly state, as a **final, Accepted decision**:
> "No raw CAS PDF storage, ever. No PAN persistence, ever."

Rationale given: DPDP Act data-minimization, avoiding legal-review overhead for retaining PAN-bearing documents. Restated in `AGENTS.md`, `PRODUCT.md`, `decisions.md`, `database.md`. This was re-confirmed as recently as 2026-09-02, when a PAN-based dedup idea was raised, flagged back per this repo's "stop and say so on ADR conflicts" rule, and a non-PAN alternative was chosen instead (`Docs/orchestration/non-pan-duplicate-person-detection-handoff.md`).

The ADR itself states that reopening it requires **"its own fresh product/security review, including a legal read on DPDP-Act implications"** — not just a code change.

**Decision made in this conversation: reopen ADR-004 formally.** This is a real reversal, not an incremental addition — it requires updating the ADR + schema docs + PRDs, rewriting the CI guard test, and doing the review the ADR calls for.

---

## 3. AWS cost/risk context (established in this conversation)

- **Nothing is live on AWS yet at the application level.** What exists: AWS account setup (IAM, budget alert, root MFA), and a Route 53 hosted zone for `unifolio.in` with Microsoft 365 mail records preserved. Actual infra (VPC, RDS, ECS, S3 for the app) has not been applied yet.
- **A lot *is* staged (written but not applied) in Terraform**: modules for `networking`, `security`, `database`, `backend`, `frontend`, `dns`, `ecr`, `scheduler`, composed together in `infra/envs/staging/main.tf`. Confirmed by direct inspection — none of `security`, `database`, or `backend` currently define any S3 bucket or KMS key, so nothing in this feature collides with what's already staged.
- **The only AWS resource confirmed to actually exist:** the Terraform state backend itself — an S3 bucket (`unifolio-tfstate-staging-811364789032`) + DynamoDB lock table, used purely for Terraform's own bookkeeping. Unrelated to this feature.
- **Conclusion: no risk to anything currently live or staged.** New resources (S3 bucket for the file, a key for PAN encryption, new DB columns) are purely additive and would be folded into the same first `terraform apply` for Phase 0/1 — nothing to modify, rename, or replace.

---

## 4. Scope decisions made in this conversation

| Question | Decision |
|---|---|
| Should the real PAN be recoverable, or only a one-way hash for matching? | **Real PAN, encrypted, recoverable** — not a one-way hash. |
| How long should the raw CAS file be kept? | **30 days**, then auto-deleted — for re-parsing/dispute-resolution purposes, not indefinite storage or a user-facing download feature. |
| Same household, PAN already matches an existing member | **Auto-attribute (attach the new statement to that member), with a disclaimer/warning shown.** This is *not* a new "account merge" feature — it's the same "attach a new statement to an existing member's holdings" behavior the app already does today, just triggered by PAN instead of name. |
| PAN matches a member in a **different** Unifolio account | **Block the import entirely.** No self-serve resolution — the app tells the user this PAN is already tracked under another account and to contact support. No "this isn't me, import anyway" override, and no in-app account-merge feature (that was identified as a much larger, separate subsystem — auth/ownership verification, data-merge logic, reversibility — explicitly out of scope here). |

---

## 5. Two open technical decisions — approaches, trade-offs, and pricing

### 5a. How the PAN is stored/matched

**Recommended: encrypted PAN + separate lookup hash.**
Store two things per household member: `pan_encrypted` (the real PAN, envelope-encrypted, recoverable) and `pan_lookup_hash` (a deterministic HMAC-SHA256 hash of the normalized PAN, indexed). All matching — within-household *and* the cross-account block check — is done by comparing hashes, never by decrypting. This matters because the cross-account check has to search every household member in the *entire system* for a match; decrypting every row just to compare would mean the app handles other users' raw PANs in memory during that scan — worse security, and it doesn't scale.

*Alternative (not recommended):* store only the encrypted PAN, decrypt-and-compare in application code for matching. Simpler schema, but breaks down exactly on the cross-account check, which needs a system-wide search — would require decrypting every household member's PAN in the database to check for a match.

#### Sub-decision: which key protects the encryption?

This is the part still open — and where a naming confusion came up worth restating clearly:

> **"Customer-managed key" is AWS's own terminology for "managed by you, the AWS account holder (Unifolio)" — not "controlled by your app's end users."** Your app's users (the people uploading CAS files) never have any control over, or visibility into, encryption/decryption either way. That logic is entirely internal, server-side code. The only thing this choice affects is *which AWS-internal mechanism protects the key your backend uses*, and who inside AWS/your IAM setup can invoke it.

Two options:

| | **Customer-managed KMS key (CMK)** | **AWS-managed key via SSM Parameter Store** |
|---|---|---|
| Monthly cost | ~$1/month flat fee + ~$0.03 per 10,000 encrypt/decrypt calls (negligible at MVP volume) | **$0** — SSM Standard tier is free; the default `alias/aws/ssm` managed key has no extra charge |
| Access control | You define a custom key policy — precise control over exactly which IAM roles/services can invoke encrypt/decrypt, all calls logged in CloudTrail | Uses AWS's default key policy for the service; less fine-grained control over who can invoke it |
| Key rotation | Automatic yearly rotation available as a built-in AWS feature | Manual/scripted rotation — you own this yourself |
| Verdict | Slightly more expensive, but tighter, auditable, fully self-controlled access policy | Free, same underlying encryption strength (AES-256 envelope encryption either way), less rotation/access-policy convenience |

**This is the one decision still waiting on you.** Given the CMK cost is trivial regardless (~$1/month), the real trade-off isn't money — it's whether you want AWS's default access/rotation handling (SSM route) or your own precise, auditable IAM key policy (CMK route).

### 5b. Where the raw CAS file lives

**Recommended: private S3 bucket + native S3 Lifecycle rule for the 30-day auto-expiry.**
One object per import, SSE-KMS encrypted, bucket fully private (backend-only IAM access, no user-facing download UI in this scope). AWS's own Lifecycle policy deletes the object after 30 days — no cron job to build or maintain, no risk of a missed scheduled deletion.

*Alternative (not recommended):* store the PDF as a DB blob in Postgres, with a scheduled job (reusing the existing but not-yet-built ADR-006 EventBridge+ECS Fargate pattern) to sweep expired rows. Rejected: bloats DB/backup size with binary data Postgres isn't optimized for, and pulls forward building an entire separate piece of job infrastructure that this repo has explicitly deferred until later, just for this feature.

*Micro-optimizations considered and explicitly ruled out (not worth it):*
- S3 One Zone-IA storage class instead of Standard — saves fractions of a cent at this file volume, trades away multi-AZ redundancy. Not worth the durability trade for that little money.
- Keeping the file only in memory instead of S3 — doesn't actually satisfy the 30-day retention requirement, since in-memory state doesn't survive an ECS task restart/redeploy or exist across multiple backend replicas. This would silently fail to deliver what was asked for, not just be a cheaper version of it.

**Net new recurring AWS cost from this whole feature:** S3 storage (cents/month at MVP scale, self-limiting due to 30-day expiry) + optionally ~$1/month if you choose the CMK route for PAN encryption. No new compute, nothing added to what's already staged.

---

## 6. What's still needed before an implementation plan can be written

1. **Your call on 5a's sub-decision** — CMK vs. SSM-backed key for PAN encryption.
2. Formal reopening of ADR-004 (update the ADR, `Database-Schema-Unifolio.md`, `PRD-01-CAS-Parser-v2.md`, `AGENTS.md`, `PRODUCT.md`, `decisions.md`, `database.md`, and rewrite `test_no_pan_field.py`) — not yet drafted.
3. Migration/backfill behavior for existing household members who have no PAN on file yet (they'll get backfilled on their next import, once attribution is confirmed via the existing fallback path) — sketched in discussion, not yet written up as a formal design section.
4. A full design write-up (data model, attribution algorithm rewrite, encryption implementation detail, testing plan) — this document is a summary of the conversation so far, not that spec. Per this repo's process (`superpowers:brainstorming` → `superpowers:writing-plans`), the next step after you decide 5a is a written design spec, then an implementation plan.

---

## 7. Recap of every explicit decision made so far

- Reopen ADR-004 formally (not work around it, not decline).
- Store the real PAN, encrypted and recoverable (not a one-way hash).
- Retain the raw CAS file for 30 days, then auto-delete (not indefinite, not "just for this session").
- Same-household PAN match → auto-attribute with a warning/disclaimer (no new merge feature needed — this reuses existing attach-to-member behavior).
- Cross-account PAN match → block the import, show a message, contact-support-only resolution (no in-app override, no account-merge feature).
- Recommended: hash-based lookup (not decrypt-and-compare) for all matching.
- Recommended: S3 + Lifecycle rule for the file (not a DB blob + cron job).
- **Undecided:** CMK vs. SSM-managed key for PAN encryption.
