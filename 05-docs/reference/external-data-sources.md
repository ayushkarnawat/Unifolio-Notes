# Reference: External Data Sources

Six public sources. None of them is a contracted API with an SLA — all six
are public web endpoints, and **four** were reverse-engineered from the sites'
own behaviour or network traffic. The endpoints below were **live-verified on
2026-08-10** (ARN lookup on 2026-08-07) and recorded as such; treat "verified
on a date" as exactly that, not as a permanent guarantee.

| Source | Data | Cadence | Join key | Cache target |
|---|---|---|---|---|
| `mfapi.in` | NAV, current and historical, full scheme universe | Daily | Scheme code | `nav_history` |
| AMFI | Scheme-wise TER | Monthly | **None** — fuzzy name match | `scheme_ter` |
| AMFI | Scheme-wise AAUM | Quarterly | `AMFI_Code` → `schemes.amfi_code` | `scheme_aaum` |
| AMFI | Distributor name/status per ARN | **On demand**, not scheduled | ARN digits | `arn_directory` |
| AMFI | **Category universe** — the SEBI category list itself | On read, 24h | n/a — the vocabulary already matches `schemes.category` | **Local disk, not Postgres** |
| NSE Indices | Nifty 50 / 500 / LargeMidcap 250 / Midcap 150 levels | Daily | Index name | `benchmark_index_history` |

## The details that will cost time if lost

**AMFI TER has no shared join key.** Its rows carry a plan-generic `Scheme_Name` with
`R_TER` and `D_TER` (Regular and Direct), and nothing that joins cleanly to the local
`schemes` table. Matching is by fuzzy name using the standard library's `difflib` — the
same idiom PRD-01 uses for scheme matching, deliberately, rather than adding a
dependency. Month discovery and data fetch are two separate calls: one lists which
months have data for a financial year, the other returns the rows for a chosen month.

**AMFI AAUM, by contrast, has a clean key.** Each scheme row carries an `AMFI_Code`
directly joinable to `schemes.amfi_code`. No fuzzy matching. The endpoint cascades
financial year → period → scheme-wise data.

**The category universe had no source at all until 2026-08-10.** `mfapi.in`
does not expose SEBI category membership, and AMFI publishes no standalone
category reference file — which meant a category-relative ranking had no
denominator. The resolution: AMFI's **daily full-NAV text file is
section-structured by scheme category**, and those section headings *are* the
universe (~90 of them, in a file of roughly 1.6MB / 17,700 lines, served via
a redirect to AMFI's portal host). The headings follow a fixed pattern of
three scheme-type prefixes followed by the category name in parentheses,
which is what makes them extractable by pattern match rather than by
guesswork.

The finding that mattered most: the extracted heading strings needed **zero
reconciliation** against the category values already stored on `schemes` —
they are the same vocabulary. That is a point-in-time observation from
2026-08-10, and if either side's wording drifts the match narrows silently
rather than failing loudly. Full account:
[INV-001](../../04-investigations/INV-001-category-universe-gap.md).

**NSE Indices moved off `.aspx` and the old endpoint is dead.** An earlier version of
the integration notes cited `Backpage.aspx/getHistoricaldatatabletoString`; that path is
stale. The live endpoint is `POST /BackPage/getHistoricaldatatabletoString` — no
`.aspx` — taking a JSON body whose `cinfo` field is itself a JSON *string* containing
name, `startDate`, `endDate`, and `indexName` in `DD-MMM-YYYY` format, returning
`HistoricalDate`, `OPEN`, `HIGH`, `LOW`, `CLOSE`. **It requires a browser `User-Agent`
header — the site silently drops requests without one.** That single detail is the kind
of thing that costs an afternoon if it is not written down.

Two further details from the same investigation: the endpoint **discriminates
on user-agent** rather than degrading (a default client user-agent is
rejected outright), the related `liveindexsa` endpoint returns HTTP 405 and
is not usable, and the accompanying index-mapping reference file carries a
**byte-order mark** — decoding it without accounting for that corrupts its
first key silently rather than raising. See
[INV-002](../../04-investigations/INV-002-nse-index-endpoint-staleness.md).

The failure mode this source actually exhibited is the one worth remembering:
it kept responding while serving stale data. **A liveness check would have
reported it healthy.** Nothing currently asserts freshness.

**ARN lookup is on demand and never blocks.** It searches on the bare ARN
digits — the displayed `ARN-XXXXX` form returns no match — with a required
`Referer` header, and maps the returned status onto an active / suspended /
invalid trust signal surfaced on every comparison row. If it fails or returns
nothing, the UI shows the raw ARN code. No page waits on it and no import
fails because of it. **A transient failure is never cached as a result**;
only a definitive outcome — found-with-status, or confirmed-not-found — is
written to `arn_directory`, and no raw response payload is persisted. The
publicly known community scraper for this data is dead (404s), so the working
route was found from AMFI's own site behaviour:
[INV-004](../../04-investigations/INV-004-amfi-arn-distributor-lookup.md).

> **Correction, 2026-09-17 (batch 2a).** This paragraph previously stated the
> lookup is triggered inline by the **Import Service** the first time a
> previously-unseen ARN appears (PRD-03 FR-11a). As implemented on
> 2026-08-07 it is triggered by the **Dashboard** service's
> distributor-comparison read path. Unresolved — see
> [R-016](../../07-risks-and-debt.md).

## Where the data lands

Five of the six write into **Postgres reference tables**, not S3. S3's role
(ADR-004) is for *raw cached payloads* where a fetch is expensive enough to
be worth not repeating on retry — an implementation optimisation. The
structured, queryable copy of record is always in Postgres.

**The category universe is the exception.** It is cached to **local disk with
a 24-hour lifetime** and never loaded into the database, because it is large,
changes at most daily, and is a lookup list rather than a joinable dataset.
A disk cache is process-local: on more than one running instance each keeps
its own copy. Acceptable at current scale, and noted because it is the one
source that does not follow the reference-table pattern.

## Failure behaviour, uniformly

A failed refresh produces a **stale-data label**, never an error state:

| Job | Cadence | On failure |
|---|---|---|
| NAV refresh | Daily | Retry with backoff; stale-NAV labelling is the user-facing fallback |
| TER refresh | Monthly | Stale-data labelling |
| AAUM refresh | Quarterly | Stale-data labelling |
| Benchmark index refresh | Daily | Stale-data labelling |
| ARN resolution | On demand | Falls back to the raw ARN code — never blocks |
| Monthly portfolio snapshots | Monthly, backfillable | Missing months show as unavailable, never zero |
| Fund score computation | Monthly, aligned to TER | Funds with insufficient history are skipped, not scored badly |

## Status, stated honestly

All six have a **confirmed automation method**, each verified by hand once —
the ARN lookup on 2026-08-07, the rest on 2026-08-10. What remains is
implementation, not research into whether it is possible. But **four** of the
six are undocumented and uncontracted, none has been run against real
responses at production frequency, and they feed the same Analytics
Dashboard. Two of them have already been observed failing in ways a health
check would not catch — NSE served stale data while responding, and a NAV
provider outage was once cached as a permanent answer. See
[`07-risks-and-debt.md`](../../07-risks-and-debt.md), R-010.

## Related

- [ADR-006](../../03-decisions/ADR-006-background-job-scheduling.md)
- [Runtime and data flow](../../06-architecture/runtime-and-data-flow.md)
