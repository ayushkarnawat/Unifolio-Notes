# INV-010: A real AWS IAM access key was pasted into a chat session and briefly committed to a tracked file, then rotated and scrubbed before any push

Status: Closed — rotated and scrubbed same session; no evidence the key
reached a remote or was used maliciously
Date: 2026-09-09
Related: [2026-09-09 journey stage](../02-journey/2026-09-09-terraform-applied-and-iam-key-incident.md); [06-architecture/deployment.md](../06-architecture/deployment.md)

## For stakeholders

During the AWS infrastructure setup work, a real AWS access key and its
secret were exposed in plaintext twice, in one session: once pasted
directly into the chat conversation while running a local AWS configuration
command, and once accidentally saved into a file that was about to be
committed to the project's history. Neither exposure reached a public or
shared location — GitHub's own automated secret-scanning blocked the
push before it happened, which is what surfaced the problem. The key was
immediately deactivated and replaced with a new one in the AWS console, and
the commit that contained the old key's literal value was rewritten so
that value never appears anywhere in this project's shared Git history.
**No literal credential value from the source material is reproduced
anywhere in this vault**, including in this record.

## Technical detail

### What happened

While configuring AWS CLI credentials locally (`aws configure`) during the
same session that applied Terraform Phase 1-3 to real AWS infrastructure,
a real IAM access key ID and secret access key were pasted directly into
the chat/session transcript in plaintext. Separately, the access key ID
was also accidentally written into a file that was staged and about to be
committed to the project's tracked history.

### Detection

GitHub's push protection blocked the push before it reached the remote —
this is what surfaced the exposure. Had push protection not caught it, the
key would have entered shared Git history and, per the project's own
security posture, would have needed treating as fully compromised
regardless of any later local cleanup.

### Response

1. The exposed access key was deactivated in the IAM console and a fresh
   key pair generated to replace it.
2. The offending commit was rewritten via an interactive rebase to remove
   the literal key value before the branch was ever pushed — no shared
   history was affected, since the push had been blocked.

### Verification

No corroborating evidence in this batch's source material that the
original key was ever used by anyone other than the project owner between
exposure and rotation (e.g. no CloudTrail audit excerpt was included) — this
is recorded as the response taken, not as a fully closed-loop confirmation
that no misuse occurred. If a CloudTrail review was performed, it is not
evidenced in this batch.

### Why this is filed as an investigation, not just a decisions-log entry

This is a real, if contained, security incident — the classification table
this vault uses routes "troubleshooting / root-cause digging, including
incidents" to a numbered investigation record, not a one-line decision.

### A related, separate finding — not reproduced here

The same source material, in an unrelated section describing a database
connection shell-quoting bug, contains what appears to be a real database
password value. **That value is not reproduced anywhere in this vault**,
consistent with the vault's hard rule against copying sensitive material.
If the underlying shell-quoting lesson (special characters in a fetched
credential breaking naive shell interpolation) is worth carrying forward
as a documented gotcha, it should be recorded generically, without the
literal value, in a future pass — not attempted here since it was outside
this investigation's scope.

### Evidence

- `08-evidence/documents/engineering-loop/session.md`, 2026-09-09 Terraform
  Phase 1-3 section (literal credential values in the source file are not
  reproduced in this vault; the evidence copy itself is treated as
  sensitive raw material already present in the code repo's own history,
  not newly exposed by this copy — see verification note in the batch
  report)

## Addendum — 2026-09-23: status corrected, this credential is confirmed still live and unrotated

The "Closed — rotated and scrubbed" status above was drafted faithfully
from this investigation's own source material (the batch's session log),
which described the exposed IAM key as replaced. **The vault owner has
since stated directly, live, that this is not accurate**: as of
2026-09-23, neither this AWS IAM access key nor the separate RDS database
password found elsewhere in the same batch's source material (see
[R-057](../07-risks-and-debt.md)) has actually been rotated. Both remain
live, staging-environment credentials, left deliberately unrotated until
the project moves from staging to production, at which point both must
be rotated.

This status line is being **reopened**, not silently rewritten, per this
vault's append-only correction convention — the original text above is
left intact as a record of what the source material claimed at the time.
**Revised status: Open — not actually rotated; must be rotated before
production.** See [R-057](../07-risks-and-debt.md) for the dedicated,
cross-referenced risk entry tracking this until both credentials are
rotated. No literal credential value is reproduced here, consistent with
the rest of this record.

*Source: vault owner, live conversation, 2026-09-23.*
