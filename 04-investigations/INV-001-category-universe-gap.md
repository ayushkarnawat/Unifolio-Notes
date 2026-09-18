# Investigation: The analytics dashboard needed a fund-category universe that no data source provided

Status: Resolved
Date: 2026-08-10
Related: `02-journey/2026-08-10-analytics-research-and-first-integrations.md`; `05-docs/reference/external-data-sources.md`; PRD-04 FR-3/FR-5/FR-6

## Trigger

PRD-04's core analytics promise is comparative: rank a fund against its
category, compare its cost against its category, compute a category median
to beat. Every one of those requires knowing **which other funds are in the
same category** — the full category universe, not just the categories of the
funds a given user happens to hold. While planning Phase 4, it became clear
no identified source supplied that.

## Expected behavior

The NAV data source already in use (mfapi.in, live since Phase 1) was
assumed to carry enough scheme metadata to derive category membership, since
it already supplied the scheme identifiers and names the import path relies
on.

## Observed behavior

It does not expose SEBI category membership at all. Without it, a
category-relative ranking has no denominator: the product could rank a
user's funds against each other, which is meaningless, or against nothing.

## Hypotheses

1. The existing NAV source has category data under a field not yet used.
2. The industry body (AMFI) publishes a category list as a downloadable
   reference file.
3. A category universe can be derived from the daily full-NAV file's
   structure rather than from an explicit field.
4. Categories would have to be maintained by hand as a static list in the
   codebase.

## Experiments

| Experiment | Expected signal | Actual result | Conclusion |
|---|---|---|---|
| Inspect the existing NAV source's scheme payload for a category field | A category or SEBI-classification attribute | No such attribute | Hypothesis 1 rejected |
| Look for a standalone AMFI category reference file | A published list of SEBI categories | No standalone category file found | Hypothesis 2 rejected |
| Fetch AMFI's daily full-NAV text file and inspect its structure | Flat rows of scheme/NAV pairs | A **section-structured** file: category headings partition the scheme rows beneath them. ~1.6MB, ~17,700 lines, roughly 90 category headings. Served via a redirect to AMFI's portal host | Hypothesis 3 confirmed |
| Compare the extracted heading strings against the category values already stored on the schemes table | Some normalisation work expected — case, punctuation, wording | **Zero reconciliation needed.** The heading vocabulary matches the stored values exactly | The file is not just *a* source, it is the same vocabulary already in use |
| Consider a hand-maintained static list | A workable fallback | Would go stale silently every time SEBI or AMFI changed a category | Hypothesis 4 rejected as a last resort only |

## Root cause

Not a bug — a genuine gap in the planned data-source set. The analytics
requirements were specified against a comparative model whose denominator
had never been sourced, because the existing NAV integration was assumed to
cover scheme metadata generally when in fact it covers only what the import
path needed.

The gap was closed by noticing that the category universe was already being
published implicitly, as the section structure of a file whose *contents*
nobody needed. The headings match a fixed pattern of three scheme-type
prefixes followed by the category name in parentheses, which is what makes
them extractable reliably rather than by guesswork.

## Resolution

AMFI's daily full-NAV text file is adopted as the category-universe source,
with the category headings parsed out by pattern match. Because the file is
large and changes at most daily, it is **cached to local disk with a 24-hour
lifetime**, not loaded into the database — the only one of the reference
integrations that does not write to a reference table.

## Remaining uncertainty

- The file's section-heading format is a formatting convention, not a
  contract. It has never been published as an interface, and AMFI can change
  it without notice. This is the same class of exposure as
  [R-010](../07-risks-and-debt.md), and the category universe should be
  counted as a fourth reverse-engineered integration rather than a safe one.
- The exact-match finding is a point-in-time observation from 2026-08-10. If
  either AMFI's wording or the stored category values drift, the match
  silently narrows rather than failing loudly.
- A disk cache is process-local. On more than one running instance, each
  keeps its own copy — acceptable at current scale, but it is not the shared
  reference-table pattern the other sources use, and
  `05-docs/reference/external-data-sources.md` currently states that all
  sources write into reference tables. That statement needs qualifying.

## Related records

- [2026-08-10 journey entry](../02-journey/2026-08-10-analytics-research-and-first-integrations.md)
- [INV-002](INV-002-nse-index-endpoint-staleness.md) — found the same day
- [ADR-010](../03-decisions/ADR-010-fund-scorer-composite-formula.md) — the scorer depends on this universe
- [External data sources](../05-docs/reference/external-data-sources.md)
- Evidence: `08-evidence/documents/plans/2026-08-10-phase-4-analytics-backend-design.md` §1
