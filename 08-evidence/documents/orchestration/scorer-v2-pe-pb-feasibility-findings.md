# Scorer v2 — PE/PB Valuation Data Feasibility Findings

Investigation date: 2026-08-24. Question: can the Valuation Overlay component (5% weight,
PE/PB vs. category average) be built, and how.

## Existing codebase: nothing to build on

No holdings, portfolio-disclosure, or stock-fundamentals integration exists anywhere in
the backend today (`backend/app/services/analytics/`, `backend/app/integrations/`
searched). The only external data clients are NAV (`amfi_navall`/`mfapi` cache), AAUM
(`amfi_aaum_client.py`), TER (`amfi_ter_client.py`), and NSE index levels
(`nse_indices_client.py`). Valuation is a genuinely new data category for this platform,
not an extension of something partially there.

## No official free API for fund-level PE/PB in India

Searched for SEBI/AMFI-published PE/PB, and for Value Research / Morningstar India APIs.
Neither publishes a public, programmatic feed for fund-level PE/PB. SEBI's monthly
cumulative report and half-yearly portfolio disclosure (Regulation 59A) don't include
PE/PB either — they cover holdings, turnover ratio, and (as of a 2025 circular)
Information Ratio, but not valuation ratios.

## Three viable paths

**A. Build in-house.**
1. Ingest each AMC's portfolio disclosure (holdings + weights) — SEBI mandates half-yearly
   disclosure by regulation; most AMCs publish monthly in practice. **No standard format or
   API** — each AMC publishes its own file on its own site. This is the hardest sub-problem,
   harder than getting the PE/PB numbers themselves.
2. Get stock-level PE/PB for every constituent holding. Viable paid options exist here
   (e.g. FinEdge's financial data API; several NSE/BSE data vendors) — nowhere near
   Bloomberg/Refinitiv's ~$24k/seat tier some global vendors quote for India coverage.
3. Compute fund-level PE/PB as a **weighted harmonic mean** across holdings — this is
   Value Research's own published methodology for exactly this calculation, not a guess:
   "the accurate way to calculate the P/E ratio of a mutual fund is to use the weighted
   harmonic mean method... appropriate weightage to both price and earnings of each
   stock." A citable formula, not internal engineering judgment.
4. Aggregate to category average the same way the rest of the scorer already aggregates
   (category-wide percentile ranking).

Consistent with how the rest of this scorer is built — every other component is computed
from primitives (NAV history, monthly series) rather than sourced pre-computed from a
third party. Genuinely the largest new engineering surface in scorer v2: a new AMC-by-AMC
ingestion pipeline, a stock master dataset, and a refresh cadence policy (monthly
disclosures typically lag by ~10 days).

**B. Buy a licensed feed.** Morningstar Direct, ICRA Analytics, or CRISIL license
fund-level PE/PB directly — zero engineering lift for the number itself, but this is a
cost/contract decision, not an engineering one.

**C. Scrape an aggregator site** (Value Research, Moneycontrol). Fragile, ToS risk — not
recommended for a production financial product without legal review.

## Recommendation

Path A is the better fit for this codebase's existing pattern (own the calculation), but
A vs. B is fundamentally a build-cost-and-time vs. license-cost tradeoff that only you (or
whoever owns the budget) can make — captured as open question #6 in
`Docs/Scorer-v2-Calculation-Annex-Open-Questions.md`. If A is chosen, the AMC-disclosure
ingestion format survey (which AMCs publish what, how consistent the formats are) should
be the very first spike, since it's the piece most likely to blow up in scope.

## Sources

- [SEBI Portfolio Disclosures](https://www.sebi.gov.in/sebi_data/commondocs/cirmfd142002_h.html)
- [SEBI — Information Ratio disclosure mandate, 2025](https://www.business-standard.com/markets/mutual-fund/sebi-mandates-disclosure-of-information-ratio-for-equity-mutual-funds-125011701185_1.html)
- [Value Research — Key Ratios methodology (weighted harmonic mean)](https://www.valueresearchonline.com/key-ratios/)
- [Morningstar India — Mutual Fund Research Tools](https://www.morningstar.in/tools/mutual-fund-detailed-portfolio.aspx)
- [FinEdge Financial Data API](https://www.finedgeapi.com/)
