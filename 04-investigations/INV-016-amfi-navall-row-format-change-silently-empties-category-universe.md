# INV-016 — AMFI's `NAVAll.txt` feed silently changed row shape, and a hardcoded field-count check dropped every row

**Status:** Root cause found and fixed (per source material; not independently re-verified in this codebase by this vault)
**Date investigated:** Not stated in source material — appears in the same
raw conversation as, and immediately after, the BUG-001 item 4/5 re-review
(2026-08-18/19 window; see Related), so provisionally placed there. Treat
the exact date as unconfirmed.

## For stakeholders

Well-established, popular funds (e.g. Parag Parikh Flexi Cap Fund) started
showing "Insufficient History" in category-ranking screens even though
they had years of track record. The cause: AMFI (the industry body that
publishes the daily NAV feed every scheme's ranking is built from) changed
the *shape* of its data file — splitting the "Plan/Option" wording out of
the scheme name into its own field — without changing the feed's URL or
announcing it. The app's parser only recognized the old shape and was
silently throwing away every single row of the new shape, which zeroed out
entire fund categories' peer-comparison data. Fixed by accepting both the
old and the new row shape.

## Technical detail

### Symptom

Category-ranking/peer-percentile screens showed "Insufficient History" for
schemes with long, uninterrupted track records — including well-known,
large funds — not just genuinely new/thin schemes.

### Root cause

`scheme_universe.py`'s `_parse_nav_all` (the parser for AMFI's bulk
`NAVAll.txt` feed — see ADR/evidence on Phase 4 Part 4, which live-verified
this feed's *original* 6-field shape: `Scheme Code;ISIN Div
Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date`)
hardcoded a `len(fields) != 6` guard and silently `continue`d past any row
that didn't match. AMFI's feed changed to an 8-field shape — splitting the
combined "Scheme Name" field into a separate Plan and Option pair — with no
URL or version change to signal it. Every row now had 8 fields, so every
row failed the `== 6` check and was dropped, silently. `get_category_universe`
degraded to an empty (or near-empty) universe for every SEBI category,
which the percentile/ranking logic surfaced as "Insufficient History" —
indistinguishable, from the outside, from a scheme genuinely lacking
history.

### Fix

`_parse_nav_all` updated to accept both the 6-field and 8-field row shapes
(reconstructing/deriving the display name in the 8-field case), rather than
rejecting anything that isn't exactly 6 fields.

### Why this matters beyond the immediate fix

This is a silent-external-dependency-format-change failure mode: AMFI is a
third-party feed this app has no control over, the parser had no
shape-mismatch alerting (a wrong-shape row was swallowed with a bare
`continue`, not logged or counted), and the user-visible symptom
("Insufficient History") gave no hint that the actual cause was upstream
and total (every row, every category), not scheme-specific. No monitoring
or fallback-alert for "AMFI's feed shape changed again" is described as
having been added in the source material — flagged as an open item below.

### Open item

The source material does not describe adding any format-drift detection
(e.g., logging/alerting when a nonzero fraction of rows fail to parse) —
only the immediate accept-both-shapes fix. Whether such detection exists
is unconfirmed by this batch's source material.

### Related

- Phase 4 Part 4 build (`scheme_universe.py`, `NAVAll.txt` bulk ingestion,
  original 6-field shape live-verified) — see
  `08-evidence/documents/engineering-loop/log.md` and `backend.md`.
- [INV-005](INV-005-index-fund-mega-category.md) and the
  2026-08-20 mega-category-split journey entry cover a *different* problem
  with the same category-universe pipeline (one category being too large),
  not this row-parsing bug.
- Evidence: `08-evidence/documents/Notes for the product.md` (source of this
  investigation; no other evidence copy in this vault describes this
  specific bug as of this entry).
