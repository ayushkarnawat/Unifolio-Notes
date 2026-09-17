# Why Unifolio parses PDFs instead of calling an API

## The short version

Because the API was taken away, and nobody got a replacement.

## What happened

MFCentral offered a third-party API for retrieving an investor's Consolidated Account
Statement. **SEBI and AMFI shut it down in September 2025**, stranding more than a
hundred fintechs that had built on it — including MProfit and Investwell, both direct
comparables to Unifolio.

The result is that parsing the CAS **PDF** is not a workaround or a stopgap. It is the
industry-standard mutual-fund import mechanism as of today, for everyone in this market.
Every competitor is doing the same thing.

## Why this is not simply a worse option

It is worse in the obvious way — a PDF is a document, not a data feed, and it arrives
only when a user asks a registrar to email it. But it comes with one genuine advantage
that shaped the product: **the user is in the loop.**

Unifolio's stated differentiator against MProfit is exactly this. MProfit imports
silently and users discover errors later. Unifolio shows a confidence-scored review
screen before anything is committed to the portfolio, and nothing is written until the
user confirms. A bulk API would have made that harder to justify, not easier — there
would have been no natural moment to ask.

## What stays out of scope, and why

- **MFCentral OTP/API import** — gated behind an AMFI ARN / SEBI registration path the
  company does not have. Tracked separately, not abandoned: the note in PRD-01 is
  "deferred until the partner relationship is live," not "never."
- **Account Aggregator import** — same gate, same status.

Neither is a technical decision. Both are regulatory.

## What this costs the product, concretely

- **Two formats to support**, CAMS and KFintech, because the two registrars between them
  service essentially every Indian fund and each issues its own statement layout.
- **The Summary-vs-Detailed trap.** Only the Detailed statement contains transaction
  history. Users frequently request the Summary one. This is the single most common
  import failure and is why the flow has a *named* error for it rather than a generic
  "could not parse this file."
- **Password-protected files.** CAS PDFs are password-protected by default, which is why
  the import lifecycle has a dedicated `PasswordRequired` state that lets a user retry
  the password without re-uploading.
- **Coverage gaps.** A statement covers a date range. If a user's statements do not span
  their full history, the portfolio has holes — hence `folios.has_coverage_gap`, the
  coverage-gap endpoint, and the ability to supply an opening balance manually.
- **Fuzzy scheme matching.** The scheme names in a statement do not exactly match the
  AMFI master list, so matching is confidence-scored, with anything below the threshold
  surfaced to the user rather than silently accepted.

Every one of those is a direct consequence of the source being a document rather than a
feed. Reading them as a list makes the product's import complexity look deliberate,
which it is.

## Related

- [ADR-004](../../03-decisions/ADR-004-object-storage-scope-and-cas-pdf-retention.md) —
  why the PDF is discarded after parsing
- [Glossary](../../06-architecture/glossary.md)
