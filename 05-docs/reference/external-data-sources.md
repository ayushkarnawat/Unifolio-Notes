# Reference: External Data Sources

Five public sources. None of them is a contracted API with an SLA — all five are public
web endpoints, and three were reverse-engineered from the sites' own network traffic.
The endpoints below were **live-verified on 2026-08-10** and recorded as such; treat
"verified on a date" as exactly that, not as a permanent guarantee.

| Source | Data | Cadence | Join key | Cache target |
|---|---|---|---|---|
| `mfapi.in` | NAV, current and historical, full scheme universe | Daily | Scheme code | `nav_history` |
| AMFI | Scheme-wise TER | Monthly | **None** — fuzzy name match | `scheme_ter` |
| AMFI | Scheme-wise AAUM | Quarterly | `AMFI_Code` → `schemes.amfi_code` | `scheme_aaum` |
| AMFI | Distributor name/status per ARN | **On demand**, not scheduled | ARN digits | `arn_directory` |
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

**NSE Indices moved off `.aspx` and the old endpoint is dead.** An earlier version of
the integration notes cited `Backpage.aspx/getHistoricaldatatabletoString`; that path is
stale. The live endpoint is `POST /BackPage/getHistoricaldatatabletoString` — no
`.aspx` — taking a JSON body whose `cinfo` field is itself a JSON *string* containing
name, `startDate`, `endDate`, and `indexName` in `DD-MMM-YYYY` format, returning
`HistoricalDate`, `OPEN`, `HIGH`, `LOW`, `CLOSE`. **It requires a browser `User-Agent`
header — the site silently drops requests without one.** That single detail is the kind
of thing that costs an afternoon if it is not written down.

**ARN lookup is on demand and never blocks.** Triggered inline by the Import Service the
first time a previously-unseen ARN appears (PRD-03 FR-11a), searching on the bare ARN
digits. If it fails or returns nothing, the UI shows the raw ARN code. No page waits on
it and no import fails because of it.

## Where the data lands

All five write into **Postgres reference tables**, not S3. S3's role (ADR-004) is for
*raw cached payloads* where a fetch is expensive enough to be worth not repeating on
retry — an implementation optimisation. The structured, queryable copy of record is
always in Postgres.

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

All five have a **confirmed automation method**. What remains is implementation — writing
the code — not research into whether it is possible. That uncertainty is closed. But
none of the three reverse-engineered integrations has been run against real responses at
production frequency yet, and they feed the same Analytics Dashboard. See
[`07-risks-and-debt.md`](../../07-risks-and-debt.md).

## Related

- [ADR-006](../../03-decisions/ADR-006-background-job-scheduling.md)
- [Runtime and data flow](../../06-architecture/runtime-and-data-flow.md)
