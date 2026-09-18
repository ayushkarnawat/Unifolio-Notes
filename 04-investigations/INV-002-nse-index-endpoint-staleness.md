# Investigation: The benchmark index endpoint still responded, but had stopped being updated

Status: Resolved
Date: 2026-08-10
Related: `02-journey/2026-08-10-analytics-research-and-first-integrations.md`; R-010; PRD-04 FR-8/FR-9

## Trigger

PRD-04's benchmark comparison (FR-8, FR-9) needs historical index values so a
fund's performance can be shown against the index it tracks. The index source
identified during specification was a page on the exchange's own site. While
verifying every Phase 4 data source by hand rather than trusting the spec,
the index path was checked.

## Expected behavior

The documented `.aspx` path returns current historical index data, as it did
when the technical design was written.

## Observed behavior

The path still responded — it did not 404 — but the data it returned was
stale. This is the dangerous failure mode: an integration that keeps working
in the sense that requests succeed, while silently serving old numbers. A
naive health check would have reported it healthy.

## Hypotheses

1. A request parameter is wrong and the endpoint is returning a default or
   cached response.
2. The exchange moved to a different backend endpoint and left the old path
   in place, unmaintained.
3. The endpoint requires a browser-like request and is degrading rather than
   rejecting.

## Experiments

| Experiment | Expected signal | Actual result | Conclusion |
|---|---|---|---|
| Vary the request parameters against the `.aspx` path | Fresh data for some parameter combination | Still stale | Hypothesis 1 rejected |
| Read the exchange site's own front-end JavaScript (`IISLComponet.js`) to see what the live site actually calls | The real endpoint the current site uses | A different, POST-based endpoint on the same host (`BackPage/getHistoricaldatatabletoString`) | Hypothesis 2 confirmed — the site itself had moved and the old path was left behind |
| Call the newly-found endpoint with a default client user-agent | Historical data | Rejected | The endpoint discriminates on user-agent |
| Call it with a browser user-agent | Historical data | Works | A browser user-agent is a hard requirement, not a nicety |
| Try the related live-index endpoint (`liveindexsa`) | Current index values | HTTP 405 | Not usable; not pursued further |
| Load the index-mapping reference file with a default text decoder | Clean parse | Leading bytes corrupted the first key | The file carries a byte-order mark and must be decoded accordingly |

## Root cause

The exchange migrated its historical-data retrieval from a page-based
`.aspx` endpoint to a POST-based backend endpoint, and left the old path
serving without maintaining it. The technical design had captured the old
path when it still worked. Nothing announced the change; the only reliable
record of what the site currently does was the site's own front-end script.

A second, independent defect was found in the same pass: the accompanying
index-mapping file is byte-order-marked, and decoding it without accounting
for that corrupts its first key silently rather than raising.

## Resolution

- Switch to the POST-based endpoint discovered in the site's own script.
- Send a browser user-agent; without it the endpoint refuses.
- Decode the index-mapping file with BOM-aware decoding.
- Do not use the live-index endpoint; it rejects the request method.

All of this was verified live on 2026-08-10 before any code depended on it.

## Remaining uncertainty

- The replacement endpoint is as undocumented and uncontracted as the one it
  replaces. This is the second time this source has moved. It has the worst
  track record of the external integrations and should be assumed to move
  again.
- The failure mode observed here — **serving stale data rather than
  failing** — is not detectable by an availability check. Nothing currently
  monitors index-data freshness. A freshness assertion, not a liveness
  check, is what would have caught this.
- Verification is a single point-in-time observation.

## Related records

- [2026-08-10 journey entry](../02-journey/2026-08-10-analytics-research-and-first-integrations.md)
- [INV-001](INV-001-category-universe-gap.md) — found the same day
- [Risks and debt](../07-risks-and-debt.md) — R-010 already records this
  source's fragility and cites this exact move
- [External data sources](../05-docs/reference/external-data-sources.md) —
  needs its NSE row corrected to the POST endpoint
- Evidence: `08-evidence/documents/plans/2026-08-10-phase-4-analytics-backend-design.md` §4
