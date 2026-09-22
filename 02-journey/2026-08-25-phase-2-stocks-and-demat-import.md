# Phase 2: stocks and demat import

## For stakeholders

Unifolio's second asset class is direct equity. The question was how to get a
user's stock holdings in without asking them to type anything. Over 25 and 26
August the team researched every available route — broker APIs, the regulated
Account Aggregator framework, screen-scraping the depositories, and plain file
upload — and chose the boring combination: the user uploads the depository
statement they already receive, plus, in a later step, Unifolio reads those
statements automatically out of a dedicated mailbox, because a 2024 regulator
mandate means every investor is emailed one whether they ask for it or not.
Broker integrations and the Account Aggregator route were ruled out for this
phase on cost and timeline. The research also produced the most important
constraint in the whole programme: a depository statement shows what a user
holds today, not how they got there — so for stocks, Unifolio starts with
holdings and no purchase history, and the design refuses to invent a cost
basis to fill the gap.

## Technical detail

### Intended outcome

Import direct equity holdings for a household member with no manual data
entry, alongside the existing mutual-fund CAS pipeline rather than inside it.

### What actually happened

**Research (2026-08-25).** Several options were eliminated on structural rather
than preference grounds:

- **Automating the depository's own download** is impossible from a web app:
  the desktop tool that does it is an Electron application with an embedded
  browser, which a page in a browser cannot drive.
- **A server-side bot** logging in on the user's behalf is precisely the
  pattern the RBI's Account Aggregator framework was created to eliminate
  (NBFC-AA Master Directions 2016, §5.9 and §8(b)), and the depositories'
  terms forbid the user revealing their password in the first place.
- **The depository CAS gives current holdings, not transaction history.** The
  parser's equity records carry name, ISIN, share count, price, value, symbol
  and exchange — there is no per-transaction record. The research suggested
  reusing the existing opening-balance transaction type as the fallback shape;
  the implementation plan later rejected that in favour of a snapshot table.
- **The depository's Statement of Transactions** reads as a custody-movement
  ledger rather than a priced trade blotter. The research's conclusion is to
  obtain one real sample before committing engineering time — that sample has
  not been obtained (R-044).
- **Broker APIs** (Kite, Upstox, Angel One, Dhan, Fyers, and the smallcase
  gateway) were ruled out for this phase by the product owners. The decision
  memo adds the supporting facts: no public pricing for the aggregator, nine
  of ten brokers requiring a fresh login per refresh, and three large
  platforms with no public API at all.
- **The Account Aggregator route** is costed at ₹5–25 lakh and 5–10 months,
  covering FIU registration and certification.

The research's §7-A is the finding that changes the shape of the solution:
**SEBI's July 2024 circular, effective April 2025, requires the depositories
and the RTAs to email every investor their consolidated account statement**,
from a small set of known sender addresses. That turns "ask the user to fetch
a file" into "read a mailbox", and the decision is to build that ingestion
in-house on AWS SES rather than buy it.

**The decision memo (2026-08-25)** lays out options A through I in a
comparison table and recommends A + B + H: statement upload, in-house email
auto-ingestion, and browser-native pickup conveniences. Recorded as
[ADR-014](../03-decisions/ADR-014-phase-2-demat-ingestion.md). Its §8 notes
the browser capabilities involved are unevenly supported — the file-system
access API is desktop Chromium-family only, and the share-target route is
Android PWA only — so these are conveniences layered on top of plain upload,
never a replacement for it.

**The backend plan (2026-08-26)** builds a parallel pipeline rather than
extending the CAS one: migration `0010_demat_accounts_and_equity_holdings`
adds `demat_accounts`, `equity_holdings`, `bond_holdings`,
`demat_mutual_fund_holdings` and `equity_price_history`, plus a depository
type enumeration; routes `POST /demat-imports/parse`,
`POST /demat-imports/confirm` and
`GET /household-members/{member_id}/equity-holdings`; and a "Stocks"
allocation bucket. The existing `/cas-imports` lifecycle is untouched and
continues to reject demat statements. The snapshot model is keyed on demat
account, ISIN and statement date — deliberately not the opening-balance
transaction shape the research had suggested.

The plan carries **seven numbered deviations from the source documents**,
under an instruction to flag rather than silently resolve, each confirmed with
the product owner during planning:

1. **PAN — "keep never-persisting PAN. Revisit if/when that reversal actually
   lands in the schema."** See the contradiction note below; this is the
   single most consequential open item in the batch.
2. Lean on the parser's bundled ISIN data rather than building a custom
   security-master table; carry only a binary unresolved-security flag.
3. A module mix-up in the source documents (scheme-universe versus enrichment)
   corrected.
4. No scheduled-job infrastructure exists yet for anything, so price fetching
   mirrors the NAV module's on-demand fetch-and-cache instead.
5. The blanket "no cost basis" claim is wrong for mutual-fund holdings held in
   demat form, which do carry average cost, total cost and profit-and-loss.
6. The real mutual-fund dedupe key is the five-column key established by
   INV-003, not the four-column key the source documents describe.
7. National Pension System holdings present in the parsed statement are
   explicitly out of scope, flagged rather than dropped.

One assumption is flagged as unverified: the NSE bhavcopy URL and its column
names have not been checked against a real file (R-044).

**The frontend plan (2026-08-26)** adds a `DematImportFlow` as a sibling to the
existing mutual-fund import flow, reusing `UploadForm` and adding a
`DematReviewTable`, behind a new "What are you adding?" asset-type choice in
`MainDashboardFlow.tsx`. Its governing rule is stated flatly: **no fabricated
cost basis, ever** — where cost is unknown the UI says "Cost basis
unavailable" rather than showing a zero or a guess. Unresolved securities are
informational and never block a confirm. Scope limits are explicit: member
view only (there is no aggregate endpoint yet), mobile out of scope, and the
allocation donut needs no changes — its task is a regression test only.

### Deviation — decision or response taken

**The PAN contradiction is the open item this stage must not resolve.** Four
positions exist, in this order:

1. The vault's standing rule through batch 1 and 2a: PAN is never persisted,
   with a permanent guard test added on 2026-08-04.
2. 2026-08-25, research and decision memo: "the 'no PAN persistence, ever'
   rule is being rewritten — Unifolio will now store PAN, **masked wherever
   displayed**", motivated by automated statement ingestion.
3. 2026-08-26, backend plan: "Decided during planning: **keep never-persisting
   PAN.** Revisit if/when that reversal actually lands in the schema."
4. 2026-09-16, already in the vault:
   [ADR-007](../03-decisions/ADR-007-pan-storage-and-encryption.md) and the
   matching decisions-log entry — PAN **will** be stored, **encrypted at
   rest**, to support per-member matching against CAS filings; direction
   confirmed, not implemented.

Masked-on-display and encrypted-at-rest are different mechanisms with
different rationales, and the 25 August memo additionally contradicts itself:
its option-H discussion asserts the hard no-PAN rule still stands while its own
opening constraints say the rule is being rewritten. This is presented as an
open question in the risk register (R-043) and is not resolved here.

One thing the batch *does* settle in the vault's favour: ADR-007 records that
the PAN reversal had no written artifact behind it. This batch supplies one,
dated three weeks earlier. An appended dated addendum to ADR-007 is proposed
in §2b to record that evidence without altering the ADR's body.

### Result

Researched, decided, planned, not built. Both implementation plans are
entirely unticked.

### Related

- ADR-014 — Phase 2 demat ingestion
- ADR-007 — PAN storage and encryption (addendum proposed, body untouched)
- R-043 — PAN persistence: three positions across three dates
- R-044 — unverified bhavcopy format and no depository transaction-statement sample
- R-045 — Phase 2 scope gaps
- INV-003 — the five-column dedupe key that deviation 6 restores
- Evidence: `08-evidence/documents/specs/2026-08-25-phase-2-stocks-demat-research.md`
- Evidence: `08-evidence/documents/specs/2026-08-25-phase-2-demat-integration-decision-memo.md`
- Evidence: `08-evidence/documents/plans/2026-08-26-phase-2-stocks-demat-import-backend.md`
- Evidence: `08-evidence/documents/plans/2026-08-26-phase-2-stocks-demat-import-frontend.md`
