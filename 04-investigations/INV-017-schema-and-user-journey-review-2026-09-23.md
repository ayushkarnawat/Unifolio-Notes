# INV-017 — Schema and user-journey trace for 3 QA-flagged issues (reference doc, no fixes yet)

**Status:** Open — reference baseline established; no fixes proposed or made.
Two of three issues are clarified (one "not a bug as described," one "a
product decision, not a bug"); the remaining issue needs more input
(sample CAS files) before root cause can be confirmed.
**Date investigated:** 2026-09-23

## For stakeholders

QA flagged three things as possible bugs: signups that stop partway through
seem to leave data outside the main `users` table; CAS statement data looks
like it's read during import but never saved; and a 10-year CAS statement
displays wrong numbers, unlike shorter statements for the same portfolio.
Before fixing anything, the team traced the actual code, table by table and
step by step, to see what really happens. Two of the three turned out not to
be bugs in the way they were first described: an account genuinely cannot be
created with only a phone or only an email — what QA saw was a normal,
by-design holding record for an unfinished signup, not a broken account. And
CAS data genuinely is saved once a user confirms an import — the real,
narrower gap is the review screen *before* confirmation, which intentionally
doesn't save anything yet, so leaving at that exact moment saves nothing (this
may be the correct behavior, or it may need to change — that's a product call,
not a bug fix). The 10-year-statement discrepancy is still unresolved; the
team's working theory is that it lives inside the third-party PDF-parsing
library Unifolio depends on, not in Unifolio's own code, but confirming that
needs the actual 7-year and 10-year files from the reporting user side by
side. No code changes have been made — this document is the shared factual
baseline the team is working from before deciding what, if anything, to fix.

## Technical detail

### Symptom / report

QA reported three(four) issues:
1. Partial signups (stopped at the mobile or email step) appear to be
   recorded outside the `users` table.
2. CAS file data appears to be read during import but never written to the
   database.
3. A 10-year CAS file parses correctly, but the data displayed to the user
   is still wrong.
4. CAS files spanning 10 years parse differently — and less correctly —
   than shorter files covering the same portfolio.

### Method

Rather than guessing from the symptom, the team traced the actual code path
for every step of a real user's journey — account creation through viewing
Analytics — establishing exactly which table/column each action writes to,
and produced an ER diagram of the schema as it exists in the codebase today
(not from the older `Docs/PRDs/Database-Schema-Unifolio.md` reference, which
the trace found to be out of date — see Documentation drift below).

### Findings, per issue

**Issue 1 (partial signups outside `users`) — not a defect as described.**
An account cannot be created with only a phone number or only an email; the
account-creation code path requires both to be independently verified first,
as a single atomic step. What was likely observed in the database is a
`pending_identity_verifications` or `otp_requests` row — tables that exist
specifically so an unverified signup attempt never has to touch `users` at
all. This is working as designed, not a bug.

A genuine, separate **open design question** was surfaced alongside this:
today the account row is created immediately after phone verification
succeeds — before the user confirms their name/onboarding details, and
before any CAS import. Whether account creation should instead happen later
(e.g., only after onboarding, or only after a first CAS import) is a
product decision to make, not a bug to fix; moving it later would require a
larger restructuring since imports currently depend on an account already
existing. Not yet decided as of this document.

**Issue 2 (CAS data read but never written) — not accurate as a blanket
statement; a narrower, possibly-intentional gap named instead.** When an
import is confirmed, everything is written to the database correctly. The
real, concrete gap is the review screen between upload and confirmation:
during that window the parsed data is shown to the user but deliberately not
yet persisted, so leaving the flow at that exact point saves nothing. This
may be working as intended (a preview should be abandonable without side
effects) or may need to change — flagged as a product decision, not
resolved by this document.

**Issues 3 & 4 (10-year CAS parsing discrepancy) — root cause not yet
confirmed.** Unifolio's own import code has no logic that treats a CAS file
differently based on how many years it spans. The working hypothesis is that
the discrepancy lives inside the third-party PDF-parsing library
(`casparser`) used to read CAS statements, specifically in its page-break/
fund-section-boundary detection — a longer document has more of these
boundaries and more opportunity for that detection to misfire. Confirming
this requires the actual 7-year and 10-year CAS files for the same portfolio,
run side by side and diffed — not yet obtained as of this document.

### Documentation drift noted in passing

The trace found `Docs/PRDs/Database-Schema-Unifolio.md` (last updated
2026-09-02, per this document's own note) does not yet reflect
`users.pending_deletion`/`deletion_scheduled_at`, or the
`account_deletion_surveys`, `analytics_sections`, and
`analytics_recompute_status` tables — all of which exist in the current
codebase as of this trace. Recorded here as a documentation-currency note,
not a defect; this vault's own `06-architecture/data-model.md` already
covers these tables (see Related) so this vault is not affected by the drift,
only the repo's own PRD doc.

### Next steps named in the source document (not yet actioned)

1. Decide the intended design for Issue 1 (when an account record should
   actually be created).
2. Decide whether Issue 2's review-screen behavior (nothing saved until
   confirm) is expected or should change.
3. Obtain the 7-year and 10-year CAS files needed to root-cause Issues 3/4.

### Related

- [06-architecture/data-model.md](../06-architecture/data-model.md) — this
  vault's own schema reference already covers the tables this trace confirms
  (`otp_requests`, `pending_identity_verifications`, `account_deletion_surveys`,
  etc.); no correction needed here, just corroboration.
- [INV-013](INV-013-dashboard-stuck-loading-after-analytics-navigation.md) —
  a different dashboard-loading bug (`BUG-002`), already fully ingested; not
  related to any of the four issues traced here.
- Evidence: `08-evidence/documents/investigations/2026-09-23-schema-and-user-journey-review.md`,
  `08-evidence/documents/investigations/2026-09-23-schema-and-user-journey-review.pdf`,
  `08-evidence/documents/investigations/assets/schema-erd.png`,
  `08-evidence/documents/investigations/assets/journey-flow.png`
