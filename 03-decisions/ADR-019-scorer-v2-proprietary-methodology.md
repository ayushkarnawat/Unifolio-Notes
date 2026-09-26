# ADR-019: Scorer v2 — a ten-component proprietary methodology, approved at the formula level, not yet implemented

Status: Accepted (formula/methodology level only) — Not implemented
Date: 2026-09-23 (ingestion date; source documents are undated beyond "approved at the product/formula level")
Related: [ADR-010](ADR-010-fund-scorer-composite-formula.md) (the live, implemented v1 formula this would replace), [INV-011](../04-investigations/INV-011-scorer-v2-pe-pb-valuation-overlay-feasibility.md) (Valuation Overlay component feasibility)

## For stakeholders

A more elaborate version of the Unifolio Fund Score — "Scorer v2" — has
been written up and approved at the product/formula level, but has not been
built. Where the current live score (ADR-010) blends three ingredients —
past return, downside risk, and consistency — Scorer v2 blends ten,
organised into six buckets: Return, Consistency, Downside Risk,
Risk-Adjusted Efficiency (Sortino and Information Ratio), Upside
Participation, a Valuation overlay (how a fund's PE/PB compares to its
category), and a two-part Cost Efficiency measure (current expense-ratio
level, plus whether that ratio has been rising or falling over time). It
still scores a fund only against its true category peers, still shows the
full component breakdown rather than a bare number, and still refuses to
score a fund on data that doesn't actually exist for it. The methodology
itself is signed off; a companion document lists 13 concrete engineering
questions (how exactly a "rolling 5-year window" is sampled, what counts as
a "category average," how thin a category can be before a score is
unreliable, and others) that block turning the approved formula into
working code. None of these questions have been answered yet, and no build
work has started.

## Technical detail

### Context

`Docs/Updated_and_Approved_Unifolio_Fund_Scoring_Methodology.md` (batch 4d,
ingested 2026-09-23) is a "Proprietary & Confidential" methodology document
distinct from, and substantially larger than, the formula this vault
already tracks as Accepted and implemented in
[ADR-010](ADR-010-fund-scorer-composite-formula.md). It is not referenced
anywhere else in this vault prior to this batch. Its companion,
`Docs/Scorer-v2-Calculation-Annex-Open-Questions.md`, frames itself
explicitly as a punch-list of *engineering* open questions needed to turn
an already-approved methodology into deterministic code and golden tests —
"not objections to the methodology itself."
[INV-011](../04-investigations/INV-011-scorer-v2-pe-pb-valuation-overlay-feasibility.md),
already in this vault, investigated exactly one of Scorer v2's ten
components (the PE/PB Valuation Overlay) in isolation, and explicitly noted
"Scorer v2 more broadly... has no ADR of its own yet in this vault." This
record fills that gap.

### The v2 formula, as approved

For fund f in category C as of date t, percentiles (0-100, higher always
better, inverted before ranking where a lower raw value is better) are
weighted:

- Return — rolling return, blended 1-5Y, recency-weighted — **25%**
- Consistency — beats category average (% of 1-5Y rolling windows) — **12%**
- Consistency — top-quartile frequency (% of 1-5Y rolling windows) — **8%**
- Downside Risk — max drawdown percentile — **7.5%**
- Downside Risk — Down Capture Ratio — **7.5%**
- Risk-Adjusted Efficiency — Sortino Ratio — **10%**
- Risk-Adjusted Efficiency — Information Ratio — **10%**
- Upside Participation — Up Capture — **5%**
- Valuation Overlay — PE/PB vs. category average (relative, not absolute) — **5%**
- Cost Efficiency — expense ratio level vs. category average — **6%**
- Cost Efficiency — expense ratio trend over 2-3 years — **4%**

A score requires a minimum 3-year NAV history for a full score (1-3 years
gets a flagged provisional score; under 1 year is not scored at all), and a
minimum category peer-set size (the source names 15 as an example
threshold) before percentile ranking is treated as statistically reliable.
Where an input metric cannot be calculated for a fund, that component is
dropped from both the score and its weighting denominator — a fund is never
scored on data that isn't actually available, the same principle already
live in ADR-010's implementation.

### How this differs from the live v1 formula (ADR-010)

| | v1 (ADR-010, live) | v2 (this ADR, approved not built) |
|---|---|---|
| Components | 3 (return, downside risk, consistency) | 10, across 6 buckets |
| Risk-adjusted efficiency | Not a separate ingredient | Sortino + Information Ratio, 20% combined |
| Valuation | Not scored | PE/PB overlay vs. category average, 5% |
| Cost | Not scored | Expense-ratio level + trend, 10% combined |
| Status | Accepted, implemented, live | Accepted at formula level, zero implementation |

This ADR does not resolve whether or when v1 is replaced by v2 — that
product decision is not addressed in either source document, and this
vault has no evidence a replacement has been scheduled.

### Decision

Record Scorer v2 as an accepted methodology at the product/formula level,
explicitly **not** implemented, distinct from and not a replacement (yet)
for the live ADR-010 formula. This is a documentation decision only — no
build work is authorised or implied by this record.

### Why a new ADR rather than an addendum to ADR-010

ADR-010 documents a specific, already-implemented three-ingredient formula
with its own alternatives-considered history. Scorer v2 is a different
formula (ten components, different weights, new inputs like PE/PB and
Sortino/Information Ratio that v1 never scores at all) approved through a
separate sign-off process, with its own 13-item open-question list blocking
implementation. Folding it into ADR-010 would misrepresent it as a revision
of the accepted formula rather than a distinct, larger decision still
pending engineering translation.

### Open questions (from the annex; implementation-blocking, not methodology objections)

13 items across three groups, none resolved as of this record:

- **Needs product/engineering judgment, no safe default** (4 items) — exact
  rolling-window sampling mechanics, the recency-weighting curve's precise
  function, NAV sampling frequency, and the definition of "category
  average" used for cost-level scoring.
- **Further items** (9 items, per the annex's B/C sections) — covering
  minimum-peer-set handling, provisional-score presentation, data-gap
  denominator mechanics, and other implementation-determinism questions not
  reproduced in full here; see the evidence copy for the complete list.
- Open question 6 specifically (build vs. license the PE/PB data feed) is
  the one already investigated in depth — see INV-011.

### Consequences

- No implementation work should proceed against Scorer v2 until the 13
  open questions have an owner and answers; several materially change the
  resulting numbers (recency-weighting curve, rolling-window sampling).
- The relationship between v1 (live) and v2 (approved, unbuilt) needs an
  explicit product decision — replace, run in parallel, or shelve — not
  addressed by either source document.
- [R-015](../07-risks-and-debt.md)'s existing contradiction (this vault's
  fund-scoring-methodology.md vs. ADR-010) is unaffected; v2 is a third,
  separate methodology, not a resolution of that contradiction.

### Evidence

- `08-evidence/documents/Updated_and_Approved_Unifolio_Fund_Scoring_Methodology.md`
- `08-evidence/documents/Scorer-v2-Calculation-Annex-Open-Questions.md`

## Addendum — 2026-09-24: an independent source corroborates the 10/6 prose summary is the annex's own error, not the 11/7 table

### For stakeholders

This ADR's own "For stakeholders" section and its "How this differs" table
both describe the v2 methodology as "ten weighted components across six
buckets" — but the ADR's own "v2 formula, as approved" section lists 11
distinct weighted line items across 7 distinct buckets (Return;
Consistency [2]; Downside Risk [2]; Risk-Adjusted Efficiency [2]; Upside
Participation; Valuation Overlay; Cost Efficiency [2]). This is an internal
inconsistency that was already present in this ADR when first written, not
introduced by this addendum. A separate, later engineering conversation
independently reviewing the same approved annex reached the identical
conclusion: the 11-row/7-bucket table is internally consistent and correct,
and the "ten... six buckets" prose summary sentence is the annex's own
error. This corroboration doesn't change the ADR's content, but confirms
the "10/6" framing (repeated in this ADR's stakeholder-facing text) should
not be trusted as the accurate count going forward.

### Technical detail

Per this batch's source material, an engineering review of Codex's
assessment of `Updated_and_Approved_Unifolio_Fund_Scoring_Methodology.md`
reached this independently: "the overview says 'ten weighted components
across six buckets,' but the table has 11 rows across 7 buckets... The
table is internally consistent; the prose summary sentence is just wrong."
This is the same discrepancy this ADR's own text already exhibits (compare
this ADR's "For stakeholders" and "How this differs" sections, which say
"10, across 6 buckets," against its own "v2 formula, as approved" section).
No correction is made to the ADR's original text per this vault's
append-only rule; this addendum flags the count as unresolved/likely-wrong
in the prose framing specifically, not in the formula table.

A related, separate count discrepancy was also noticed but is **not**
independently confirmed either way and is left as an open item, not a
finding: this ADR's "Open questions" section states "13 concrete
engineering questions," while the source conversation for this addendum
consistently refers to "14" clarifying decisions/definitions. Which count
is correct (or whether they're counting slightly different things) is not
resolved by this batch's source material.

A further, unconfirmed note from the same source conversation: it proposes
building Scorer v2 on a new dedicated branch `feat/scorer-v2` (not a
worktree, since interactive testing was wanted), based off
`feat/enhanced-ui` rather than `main`. This ADR does not record a branch
strategy at all, and this batch's source material does not confirm whether
that branch was actually created — noted here only as an open item for a
future batch to confirm or supersede, not as a settled fact.

### Addendum evidence

- `08-evidence/documents/Notes for the product.md` (the "Updated Fund
  scorer" section, lines ~811-873 of that evidence copy)
