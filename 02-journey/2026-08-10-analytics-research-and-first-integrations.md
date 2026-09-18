# Analytics Research and First Integrations

Date: 2026-08-10
Status: Complete

## For stakeholders

The analytics dashboard is the part of Unifolio that compares a user's funds
against everything else in the same category — how a fund ranks, what it
costs relative to its peers, how it has tracked its benchmark. None of that
data is available from a single source. This day was spent finding out
where each piece actually comes from, verifying each source by hand, and
only then writing the first piece of analytics code.

Four things were established, and one of them was a genuine gap that had not
been anticipated. The product needs to know which funds belong to which
category in order to rank a fund against its peers — and the price-data
source the product already used does not publish category membership at all.
The resolution came from a plain-text file the industry body publishes
daily, whose internal section headings turn out to be exactly the category
list needed, and which matches the categories already stored in the database
without any reconciliation work. The full account is in
[INV-001](../04-investigations/INV-001-category-universe-gap.md).

A second problem was found the same day: the stock-exchange index data the
benchmark comparison depends on was being read from a page that still
existed but had stopped being updated. The live source was found by reading
the exchange site's own front-end scripts. See
[INV-002](../04-investigations/INV-002-nse-index-endpoint-staleness.md).

## Technical detail

### Intended outcome

Establish, by live verification rather than assumption, the data sources
behind PRD-04's analytics requirements: the category universe, expense
ratios, fund size, benchmark index history, and the return calculation —
then implement the first subsystem (granular category allocation, FR-2).

### What actually happened

Five source questions were resolved, and the first subsystem shipped.

1. **Category universe (the gap).** The NAV source the product already used
   does not expose SEBI category membership. The resolution: the industry
   body's daily full-NAV text file is section-structured by scheme category,
   and those section headings *are* the category universe — around ninety of
   them. The file is roughly 1.6MB and served via a redirect to a portal
   host. Crucially, the category strings needed **zero reconciliation**
   against the category values already stored on the schemes table — they
   are the same vocabulary. Cached to local disk for 24 hours rather than
   loaded into the database.
2. **Expense ratio.** Available, but with no shared join key against the
   product's own scheme records, so the match is fuzzy on scheme name using
   the standard-library matcher already used elsewhere in the codebase — an
   existing idiom, not a new dependency.
3. **Fund size (AAUM).** Available with a clean numeric join key, so this
   one joins exactly.
4. **Benchmark index history.** The previously-working path had gone stale.
   Root-caused and replaced — see INV-002.
5. **Return calculation (XIRR).** Implemented as a hand-written
   Newton-Raphson solver operating purely on `Decimal`. A numeric library
   was rejected: it would force conversion to floating point, which the
   project's non-negotiable money rules forbid, and would add a heavy
   dependency for one function.

**First subsystem.** Granular SEBI-category allocation was added to the
Analytics service as one module computing holdings once and bucketing them
along two dimensions in a single pass. The coarse fund-house allocation
already built in Dashboard was **not rebuilt** — it is re-exposed alongside
the granular view inside the Analytics response so the analytics tab is one
request, sourced from the same holdings computation rather than duplicated
logic. Two routes mirror the Dashboard service's exact structure, including
the family-aggregate rule that a member with no data is shown as present and
empty rather than dropped.

The scorer design was drafted this day and then revised after a conversation
with the product owner on 2026-08-13 — see the 2026-08-12 journey entry and
[ADR-010](../03-decisions/ADR-010-fund-scorer-composite-formula.md).

### Deviation — decision or response taken

| Deviation | Response |
|---|---|
| The category universe had no source at all | Found one in a file already being published daily; verified the vocabulary matched the database's existing values before committing to it. INV-001 |
| The benchmark index endpoint was silently stale | Root-caused from the site's own front-end scripts; live endpoint, required request shape and required browser user-agent all documented. INV-002 |
| Expense-ratio data has no join key | Fuzzy name matching accepted, reusing the existing standard-library idiom rather than adding a matching library |
| A numeric library would be the obvious XIRR choice | Rejected — it would require floats. Hand-rolled solver on `Decimal` instead |
| PRD-04 uses "AUM-weighted" with two different meanings | Flagged rather than silently unified. Recorded as R-020 |

### Result

Every external source the analytics dashboard depends on was identified and
live-verified on this date, and the first of five analytics subsystems
shipped. The verification is a point-in-time fact about undocumented
endpoints, which is exactly what [R-010](../07-risks-and-debt.md) already
warns about.

### Related

- [INV-001](../04-investigations/INV-001-category-universe-gap.md),
  [INV-002](../04-investigations/INV-002-nse-index-endpoint-staleness.md)
- [External data sources](../05-docs/reference/external-data-sources.md)
- [Decisions log](../03-decisions/decisions-log.md) — 2026-08-10 entries
- [Risks and debt](../07-risks-and-debt.md) — R-010, R-020
- Sources: `08-evidence/documents/plans/2026-08-10-phase-4-analytics-backend-design.md`,
  `08-evidence/documents/plans/2026-08-10-phase-4-analytics-backend-part1-allocation.md`
