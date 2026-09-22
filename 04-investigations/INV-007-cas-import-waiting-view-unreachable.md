# Investigation: the CAS-import waiting screen cannot be reached after a request is made

Status: Open — root cause identified and a correction specified, not implemented
Date: 2026-08-19
Related: [2026-08-18 → 08-19 journey stage](../02-journey/2026-08-18-visual-motion-redesign-and-the-auth-panel.md)

## Trigger

Found while redesigning the CAS-import entry screen, not from a user report.
The redesign needed to know what the current screen does after a user asks
their registrar to email them a statement, and the answer turned out to be
"not what it was built to do".

## Expected behavior

A user who requests a CAS by email should land on a waiting screen that
explains a statement is on its way and offers to accept the file when it
arrives.

## Observed behavior

The user lands on the plain upload form instead. The waiting screen exists and
is never shown.

## Hypotheses

1. The waiting screen is gated on state that is not set when a request is made.
2. The waiting screen is gated correctly but something else navigates away from
   it immediately afterwards.

## Experiments

| Experiment | Expected signal | Actual result | Conclusion |
|---|---|---|---|
| Find the condition that renders the waiting view | A single gate on request state | The waiting view is gated on a pending-import identifier **and** on the active tab being the request tab | The gate is compound, which makes hypothesis 2 plausible |
| Trace what runs when a request is initiated | The pending-import identifier is set and nothing else changes | The handler sets the pending identifier *and* switches the active tab to the upload tab | Hypothesis 2 confirmed — the same handler that satisfies one half of the gate breaks the other half |

## Root cause

Two independent pieces of state — a pending-import identifier and a
three-way tab selection — are both used to decide one thing: which screen the
user is on. The request handler updates both, in opposite directions. The
waiting view's condition can therefore never be true immediately after a
request, which is the only moment it is meant to be true.

## Resolution

Specified, not implemented. The correction in the 2026-08-19 redesign is to
stop deriving the screen from two sources and replace the three-way tab state
with one explicit view state covering choice, request, waiting, upload and
history. The existing resume check for a member's in-progress import is
unaffected and stays as it is.

The redesign carrying this fix has no execution record in this batch, so the
defect should be assumed live.

## Remaining uncertainty

Whether the defect still exists — the surrounding screens were being rewritten
across several documents in the same week. **To verify:** cross-check against
the current state of the Unifolio code repo.

## Related records

- R-034 — an illustration variant built for this flow and never wired in
- Evidence: `08-evidence/documents/specs/2026-08-19-cas-import-illustration-redesign.md`
