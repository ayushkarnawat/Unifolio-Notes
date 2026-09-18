# Investigation: Finding a working way to resolve a distributor code to a distributor name

Status: Resolved
Date: 2026-08-07
Related: `02-journey/2026-08-07-distributor-comparison-and-a-design-system-handoff.md`; ADR-006; PRD-03 FR-11a

## Trigger

PRD-03's distributor comparison (FR-11) is only meaningful if the
distributor can be *named*. CAS statements carry an ARN code — an opaque
registration number — not a distributor name. A lookup was needed, and the
technical design assumed one existed without specifying how.

## Expected behavior

AMFI publishes a distributor directory; some accessible interface returns a
distributor's name and registration status from an ARN code.

## Observed behavior

There is no documented API. The publicly known community tool for scraping
this data (`amfi-arn-data-scrapper`) was checked and found dead — its
endpoints return 404. Following it would have meant building on something
already broken.

## Hypotheses

1. The community scraper's endpoints still work and only its packaging is
   stale.
2. AMFI's own site calls an endpoint that can be used directly.
3. The directory is only available as a bulk download requiring periodic
   ingestion.

## Experiments

| Experiment | Expected signal | Actual result | Conclusion |
|---|---|---|---|
| Call the community scraper's endpoints | Data | 404 | Hypothesis 1 rejected; the precedent is dead |
| Inspect what AMFI's own distributor-search page calls | A usable request | A JSON endpoint (`/api/distributor-agent`) taking a search term and pagination parameters | Hypothesis 2 confirmed |
| Call it with the ARN in its displayed form (`ARN-XXXXX`) | A match | No match | The search term must be the **bare numeric portion**, not the prefixed form |
| Call it without a `Referer` header | A match | Rejected | A `Referer` header is required |
| Call it with the bare number, pagination narrowed to a single result, and the required header | One distributor record | Name, status, and a registration validity date returned | Usable directly; no bulk ingestion needed, so hypothesis 3 is unnecessary |
| Check what statuses appear | A status field | Values mapping onto active / suspended / invalid | Enough to drive a trust signal, not just a name |

## Root cause

Not a defect — an unspecified dependency. The technical design named ARN
resolution as a capability without establishing that any interface for it
existed. The only publicly documented route to it had rotted. The working
route had to be found from AMFI's own site behaviour.

## Resolution

Call AMFI's own distributor-search JSON endpoint directly, with the bare
numeric ARN as the search term, a single-result page size, and the required
`Referer` header. Map the returned status onto an active / suspended /
invalid trust signal surfaced on every comparison row.

Caching and failure policy, both deliberate:
- Results are cached platform-wide in the existing ARN directory table —
  four columns only. **No raw response payload is persisted.**
- **A transient failure is never written to the cache.** Only a definitive
  outcome — found-with-status, or confirmed-not-found — is stored. The same
  lesson had already been learned from a NAV-outage bug in Phase 3, where a
  provider outage was cached as a permanent answer.
- The lookup **never blocks**: on failure the comparison still renders and
  falls back to displaying the raw ARN code.
- The endpoint is mocked in every test. It is never called live by the test
  suite; the verification is recorded in a comment beside the mock.

## Remaining uncertainty

- A fourth undocumented, uncontracted endpoint, in the same class as
  [R-010](../07-risks-and-debt.md)'s three. It was verified once, by hand,
  on 2026-08-07.
- Because no test exercises it live, a change to the endpoint's shape will
  surface in production rather than in CI.
- **Service ownership is now inconsistent with what this vault records.**
  This vault states ARN resolution is triggered inline by the Import Service
  when an unfamiliar ARN first appears (decisions-log 2026-07-22, ADR-006,
  `06-architecture/runtime-and-data-flow.md`). As implemented, the lookup
  lives in the Dashboard service and is triggered by the distributor
  comparison read path. Both are "on demand" — but they are triggered by
  different events, in different services, at different times. See
  [R-016](../07-risks-and-debt.md). **Not resolved here.**
- The captured registration-validity date is real data with an expiry. The
  plan explicitly kept it out of time-sensitive test fixtures so no test
  begins failing when it passes — worth preserving as a pattern.

## Related records

- [2026-08-07 journey entry](../02-journey/2026-08-07-distributor-comparison-and-a-design-system-handoff.md)
- [ADR-006](../03-decisions/ADR-006-background-job-scheduling.md) — records ARN resolution as on-demand and Import-triggered
- [Risks and debt](../07-risks-and-debt.md) — R-010, R-016, R-017
- [External data sources](../05-docs/reference/external-data-sources.md)
- Evidence: `08-evidence/documents/specs/2026-08-07-distributor-comparison-design.md`,
  `08-evidence/documents/plans/2026-08-07-distributor-comparison.md`
