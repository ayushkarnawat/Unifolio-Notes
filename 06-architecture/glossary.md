# Glossary

Domain terms that appear throughout these records. Indian mutual-fund vocabulary is
dense and mostly acronyms; this exists so a non-specialist reader is not stuck.

| Term | Meaning |
|---|---|
| **AAUM** | Average Assets Under Management. How much money a fund manages, averaged over a period. Published scheme-wise by AMFI, quarterly. Used to weight portfolio-level rollups |
| **AMC** | Asset Management Company — the fund house (HDFC AMC, SBI Mutual Fund, and so on) |
| **AMFI** | Association of Mutual Funds in India. The industry body. Publishes TER, AAUM, and the distributor directory, all publicly |
| **ARN** | AMFI Registration Number. The code identifying a mutual-fund distributor. Appears on a folio when a fund was bought through a distributor. Resolvable to a distributor's name and status through AMFI's public "Locate a Mutual Fund Distributor" tool |
| **CAS** | Consolidated Account Statement. A single PDF, emailed by a registrar on request, listing an investor's mutual-fund holdings and transactions across every fund house. The product's primary data source |
| **Detailed vs Summary CAS** | Two statement formats. Only the **Detailed** statement contains transaction history; the Summary one does not, and uploading it is the most common user error in the import flow |
| **Direct vs Regular plan** | Two versions of the same fund. **Direct** is bought straight from the AMC with no distributor commission; **Regular** is bought through a distributor and carries a higher expense ratio. Classifying which one a holding is affects returns materially |
| **Folio** | An account number with a single fund house. One investor can hold the same scheme under multiple folios, sometimes bought through different distributors |
| **KFintech / CAMS** | The two registrar and transfer agents (RTAs) that between them service essentially every Indian mutual fund. Each issues CAS statements covering the funds it services |
| **NAV** | Net Asset Value. The per-unit price of a fund, published daily |
| **Nifty 50 / 500 / LargeMidcap 250 / Midcap 150** | NSE market indices used as performance benchmarks |
| **RTA** | Registrar and Transfer Agent. The back-office administrator for a fund house's investor records — CAMS and KFintech |
| **SEBI category** | The regulator's standard scheme classification (Large Cap, Mid Cap, ELSS, and so on). The basis for fair peer comparison — a fund is ranked only against others in its own category |
| **SIP** | Systematic Investment Plan. A recurring, usually monthly, automatic investment. Detected from transaction patterns rather than declared by the user |
| **TER** | Total Expense Ratio. The annual percentage a fund charges. Published monthly by AMFI. Direct plans have a lower TER than Regular plans for the same fund |
| **XIRR** | Extended Internal Rate of Return. The annualised return calculation that correctly handles money going in and out at irregular intervals — the right measure for a portfolio built up through SIPs and lump sums |
| **Fund Signal** | Unifolio's own term: the signature UI element giving each holding a small radial arc, plus a sparkline on expansion, as a glanceable visual identity |
| **DPDP Act** | India's Digital Personal Data Protection Act. The compliance frame behind the data-minimisation decisions in ADR-004 |
| **MFCentral** | A third-party service that previously offered CAS retrieval via API. Shut down for this use by SEBI/AMFI in September 2025 — the reason Unifolio parses PDFs rather than calling an API. See [why we parse CAS PDFs](../05-docs/explanation/why-we-parse-cas-pdfs.md) |
