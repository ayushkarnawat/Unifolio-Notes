# Investigation: a reachable crash in primary-identity selection

Status: Resolved — fixed within the same work, 2026-08-17
Date: 2026-08-17
Related: ADR-008, [2026-08-17 journey stage](../02-journey/2026-08-17-email-password-auth-built-and-reversed.md)

## Trigger

Not a reported failure. While adding a third identity provider
(`EMAIL_PASSWORD`) during the 2026-08-17 email-and-password work, the primary
identity selection path was read and found to be unsound for the new value
before it was ever exercised in production.

## Expected behavior

Given a user with one or more linked identities, primary-identity selection
returns the highest-precedence identity, for every provider the system can
create.

## Observed behavior

Selection takes the minimum of the user's identity list keyed by a
`PROVIDER_PRECEDENCE` lookup. The list passed in is **not filtered** to
providers present in that map, and the map had no entry for the newly added
provider. Any user whose identity set included an `EMAIL_PASSWORD` identity
would raise a `KeyError` — which is to say, every user created by the feature
being built.

## Hypotheses

1. The lookup is total over the provider enumeration and the new value simply
   needs adding to the map.
2. The lookup is partial by design and the caller is expected to pre-filter,
   in which case the caller is the defect.

## Experiments

| Experiment | Expected signal | Actual result | Conclusion |
|---|---|---|---|
| Trace the argument passed to the selection helper back to its call sites | Either a filtered list or an unfiltered one | Unfiltered — the caller passes the user's full identity list | Hypothesis 2 does not hold; the caller is not pre-filtering and was never required to |
| Check `PROVIDER_PRECEDENCE` against the provider enumeration after the new value is added | Every enum member present as a key | The new provider is absent | Hypothesis 1 confirmed: the map is intended to be total and had gone stale relative to the enumeration |

## Root cause

A precedence map that must be kept in step with a provider enumeration by hand,
with nothing enforcing that it is. Adding an enumeration member is a two-place
change and only one place is obvious.

## Resolution

Fixed in the same work — the plan's tasks are all ticked. The provider was
given its precedence position so the map is total again.

## Remaining uncertainty

The structural cause is untouched: adding a future provider will reintroduce
the same crash unless the map is kept total, and nothing in the code enforces
totality. A test asserting that every enumeration member has a precedence
entry would close it for good; no evidence in this batch shows one exists.

A second, larger uncertainty: the email-and-password feature was reversed the
same day and password storage was removed by later migrations, so the specific
provider that triggered this may no longer exist. **To verify:** cross-check
against the current state of the Unifolio code repo before acting on this
record.

**Update, 2026-09-19 (live conversation).** The vault owner believes
`EMAIL_PASSWORD` was most likely removed entirely, with only phone-OTP,
email-OTP, and Google remaining as identity providers — consistent with
the existing 2026-08-17 decisions-log entry. This corroborates rather than
confirms the uncertainty above: the specific crash path this investigation
found is most likely moot, but the structural cause (a precedence map not
enforced total over the provider enumeration) is untouched and unverified,
and remains a live risk for the next new provider (Apple, per R-030). Not
yet checked against the code repo.

## Related records

- ADR-008 — phone-anchored multi-method identity (defines the provider set and precedence)
- R-031 — `users.email` never backfilled for email-and-password identities
- Evidence: `08-evidence/documents/plans/2026-08-17-email-password-signup-backend.md`
- Evidence: `08-evidence/documents/specs/2026-08-17-email-password-signup-design.md`
