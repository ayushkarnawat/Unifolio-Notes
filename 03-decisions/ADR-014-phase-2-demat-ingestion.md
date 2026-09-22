# ADR-014: Phase 2 equity ingestion uses depository statement upload plus in-house email auto-ingestion

Status: Accepted
Date: 2026-08-25
Related: [2026-08-25 journey stage](../02-journey/2026-08-25-phase-2-stocks-and-demat-import.md); extends the ingestion approach in `05-docs/explanation/why-we-parse-cas-pdfs.md`

## For stakeholders

To show a user their shares alongside their mutual funds, Unifolio has to get
holdings data out of the depositories. Nine routes were examined. The
regulated data-sharing framework is the "correct" one and costs several months
and several lakh rupees in registration and certification before a single user
benefits. Broker integrations mean building and maintaining one connector per
broker, most of which make the user log in again on every refresh, and three
of the largest have no public interface at all. Automating the depository's own
download tool is not possible from a web application, and doing it server-side
by holding the user's password is both against the depositories' terms and the
exact practice the regulator's framework exists to stamp out. What remains is
the file the user already has — and, because a 2024 regulatory mandate means
that file is emailed to every investor automatically, the ability to collect
it from a mailbox instead of asking for it. Unifolio will do both, and build
the mailbox side itself rather than buy it.

## Technical detail

### Context

Phase 2 adds direct equity to a product whose only ingestion path today is a
user-uploaded mutual-fund CAS PDF parsed with `casparser`. The depositories
publish a consolidated statement in the same family of formats, and the same
parser already exposes equity, bond, demat-held-mutual-fund and pension
records from it.

### Decision drivers

- No manual data entry, and no asking the user to remember a password for a
  third party.
- No regulatory blocker that gates launch behind a registration Unifolio does
  not hold — the same constraint that already deferred MFCentral and Account
  Aggregator imports.
- Reuse the existing parser and the existing import-review mental model.
- Cost and calendar: this is one phase of a product, not a platform programme.

### Options considered

The decision memo tabulates nine options (A–I). Consolidated here into the
four that were genuinely live.

#### Option 1: Depository statement upload (memo option A)

Advantages:
- Works today, for every user, with no registration, no partner and no fee.
- The parser already reads the format.
- Mirrors the mutual-fund import flow the user has already been through.

Disadvantages:
- The user has to go and fetch the file.
- Gives current holdings only — there is no transaction history in it.

#### Option 2: In-house email auto-ingestion (memo option B)

Advantages:
- SEBI's July 2024 circular, effective April 2025, obliges the depositories and
  RTAs to email every investor their statement from a known set of sender
  addresses — so the file arrives whether or not the user acts.
- Turns a recurring chore into a one-time setup.
- Buildable on the AWS email service already in the deployment picture.

Disadvantages:
- Requires the user to forward or grant access to a mailbox.
- Statements are password-protected and the depositories let users set their
  own password, so there is no universal formula for unattended decryption.
- A new always-on ingestion surface to secure and monitor.

#### Option 3: Broker APIs and aggregator gateways (memo options C–F)

Advantages:
- Real transaction history, not just a holdings snapshot.
- Live data without any user file handling.

Disadvantages:
- One connector per broker; three of the largest platforms publish no API.
- Nine of ten brokers require the user to log in again on every refresh, which
  defeats the point.
- The aggregator gateway publishes no pricing.
- Ruled out for this phase by the product owners.

#### Option 4: Account Aggregator framework (memo option G)

Advantages:
- The regulator-sanctioned, consent-based route; the strategically correct
  destination.
- Rich, ongoing data with no file handling at all.

Disadvantages:
- ₹5–25 lakh and 5–10 months for registration and certification before any
  user value.
- Already deferred for mutual funds on exactly these grounds.

Also examined and eliminated on structural grounds rather than preference:
automating the depository's desktop download tool (an Electron application with
an embedded browser, undriveable from a web page), and a server-side
credential-holding bot (forbidden by the depositories' terms and the precise
pattern the regulator's framework was built to eliminate — NBFC-AA Master
Directions 2016, §5.9 and §8(b)).

### Decision

Options 1 + 2, with browser-native pickup conveniences layered on top (memo
option H): a file-system access path on desktop Chromium-family browsers and a
share-target path on Android installs, both strictly optional shortcuts to the
same upload. Email auto-ingestion is built in-house on AWS SES rather than
bought.

Implementation runs as a **parallel pipeline**, not an extension of the CAS
one: migration `0010_demat_accounts_and_equity_holdings` with tables for demat
accounts, equity holdings, bond holdings, demat-held mutual-fund holdings and
equity price history; routes for parse, confirm and per-member equity
holdings; a "Stocks" allocation bucket. The existing CAS import lifecycle is
untouched and continues to reject demat statements. Holdings are stored as a
snapshot keyed on demat account, ISIN and statement date — deliberately not as
opening-balance transactions, which is what the research had suggested.

### Consequences

Positive:
- Ships without any regulatory dependency or commercial partner.
- Reuses the parser, the upload component and the review-then-confirm pattern.
- The parallel pipeline means a bug in demat import cannot regress the working
  mutual-fund path.
- Keeps the Account Aggregator route open as a later upgrade rather than
  foreclosing it.

Negative:
- **No cost basis and no transaction history for equities.** The depository
  statement carries holdings, not trades. The frontend plan's rule is
  absolute — no fabricated cost basis, ever; the UI states that cost is
  unavailable. Returns analytics for equities are therefore not possible from
  this source.
- Demat-held mutual-fund holdings are the exception: they do carry average
  cost, total cost and profit-and-loss, so a blanket "no cost basis" statement
  is wrong and was corrected during planning.
- Email ingestion inherits a password problem it cannot fully solve.
- Pension-scheme holdings present in the parsed statement are out of scope and
  flagged rather than handled.
- Price data depends on an NSE bhavcopy URL and column naming that has not been
  checked against a real file (R-044).
- No depository transaction-statement sample has been obtained, so the
  research's own precondition for costing that route is unmet (R-044).

### Validation

Not yet validated — both implementation plans are entirely unticked. Neither
the upload path nor the email ingestion exists. Validation requires migration
`0010` applied, the three routes live against a real statement, and a
confirmed decision on the PAN question below before email ingestion can be
designed in detail.

**Unresolved and deliberately not decided here:** whether PAN is persisted.
The research and decision memo that produced this ADR state the no-PAN rule is
being rewritten in favour of storing PAN masked-on-display; the implementation
plan one day later decided to keep never-persisting PAN until a schema change
actually lands; and the vault's own ADR-007, dated 2026-09-16, records PAN
being stored encrypted at rest for a different purpose. See R-043. This ADR
does not depend on the answer for statement upload, but email auto-ingestion
does.

### Evidence

- Research: `08-evidence/documents/specs/2026-08-25-phase-2-stocks-demat-research.md`
- Decision memo: `08-evidence/documents/specs/2026-08-25-phase-2-demat-integration-decision-memo.md`
- Backend plan: `08-evidence/documents/plans/2026-08-26-phase-2-stocks-demat-import-backend.md`
- Frontend plan: `08-evidence/documents/plans/2026-08-26-phase-2-stocks-demat-import-frontend.md`
