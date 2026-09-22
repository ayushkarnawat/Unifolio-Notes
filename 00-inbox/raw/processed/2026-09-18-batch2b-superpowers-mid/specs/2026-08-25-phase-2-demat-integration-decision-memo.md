# Phase 2 Decision Memo: Getting Stock/Demat Data Into Unifolio

**Purpose of this document:** lay out every real option for bringing stock/equity holdings into Unifolio in Phase 2 — what each one is, how it would actually be built, what it costs, and what it risks — so a final call can be made with the full picture in view. It draws on two prior working documents (`2026-08-25-phase-2-stocks-demat-research.md`, the detailed research trail, and `PRD-05-Stocks-Demat-Import.md`, the PRD for the recommended path); this memo is the summary built for a decision, not a re-read of those.

**Starting constraints, already settled:**
- Account Aggregator is not in scope for this phase — it's the right long-term answer, but it's a separate future phase (SEBI has already directed CDSL/NSDL to participate as Financial Information Providers on it, so it only gets easier to adopt later, not harder).
- Broker API integration (Kite Connect, Upstox, Angel One, Dhan, Fyers, or smallcase Gateway's aggregation of all of them) has been explicitly ruled out for this phase.
- We already have one real asset in hand: the open-source `casparser` library our MF import already uses can parse CDSL/NSDL demat CAS PDFs today — our own code currently detects this and deliberately rejects it. That's not a limitation to design around; it's most of the hard part already solved.
- Email auto-ingestion (Option B) will be built in-house, not bought from a third-party CAS-parsing vendor — evaluated and ruled out on cost and vendor-trust grounds, detailed in Option B below.
- The "no PAN persistence, ever" rule is being rewritten: Unifolio will now store PAN, masked wherever displayed. This was decided independently of the automation questions in this memo and doesn't end up mattering for Option B specifically — see Option B's password-handling note.

---

## 1. What do I do — the situation in one paragraph

Unifolio needs a way to get a user's stock/equity holdings without touching their CDSL/NSDL login credentials (that's legally and contractually the one hard line — both depositories' own terms forbid sharing account passwords with anyone, and SEBI/RBI have built Account Aggregator specifically as the sanctioned alternative to exactly this pattern) and, per the decision above, without a broker API. What's left is a document — the same shape of problem Phase 1 already solved for mutual funds — plus a genuine question of how much of the "get the document to us" and "keep it updated" steps can be made to feel automatic. The rest of this memo is every real way to approach that, ranked and costed.

---

## 2. All the options

### Option A — CDSL/NSDL statement upload (extend the existing CAS pipeline)

**What it is:** the user redirects to CDSL Easi/Easiest (or NSDL IDeAS), registers/logs in themselves with their own BOID and credentials, downloads their own Statement of Holdings, and uploads it to Unifolio — identical in shape to the MF CAS flow already live.

**How to build it:** stop rejecting the `NSDLCASData` object our parser already produces; add a normalizer that extracts equities/bonds/demat-mode mutual funds; add `DematAccount` and `EquityHolding` tables plus a security-master reference table (ISIN → symbol/name), refreshed from a bulk NSE/BSE file the same way AMFI's scheme list already is; reuse the existing upload/review/confirm UI; add a daily EOD price-refresh job so holdings don't go stale. Full functional spec is in `PRD-05-Stocks-Demat-Import.md`.

**Cost:** effectively free — no new vendor, no new API fees, uses public bulk data files. **Effort:** low-to-medium — most of the plumbing (parser, dedupe, review UI, scheduled jobs) already exists in a working form for MF and is being extended, not invented. **Legal risk:** none — the user performs every authenticated action themselves. **Coverage:** universal — works for any demat account regardless of broker/DP. **The real limitation:** the depository statement is holdings-only, no transaction history for equities — so no cost basis, no capital gains, no XIRR for stocks from this source alone, a genuine data gap rather than an engineering one; modifying `casparser` can't extract a price that isn't in the PDF. There's one still-open avenue worth checking before ruling it out entirely — CDSL's separate "Statement of Transactions" (SOT), which `casparser` doesn't parse at all today — but a closer look found a discouraging signal, not a confirming one: SOT reads like a debit/credit custody-movement ledger (what moved, when, classified by transfer-type code), not a priced trade blotter, consistent with the depository being a registry of ownership rather than the system that records execution price. Worth a five-minute real-sample check (register on CDSL Easi, pull an SOT covering real trades) before spending any engineering time on it — see the research doc's addendum for the full reasoning.

### Option B — Email-based auto-ingestion, layered on top of A

**What it is:** SEBI already mandates CDSL/NSDL/CAMS/KFintech to automatically email every investor their CAS monthly (if there were transactions) or half-yearly — with zero action from the user. Instead of asking the user to log into the portal and upload each time, Unifolio watches for that email and imports it automatically.

**How to build it (in-house — decided):** generate a unique inbound-forwarding email address per user, hosted on AWS SES (already the team's cloud stack) with a receiving rule that validates the sender against the known CDSL/NSDL/CAMS/KFintech addresses, drops matched attachments to S3, and triggers Option A's import pipeline; the user sets up a one-time forward rule in their own email client. No OAuth, no third-party vendor.

**Cost:** minimal — AWS SES/S3 usage at this scale, no per-email metering to manage. **Effort:** small, self-contained addition once A is live, and it plugs into the exact same `parser.py` entry point a manual upload already calls — this is purely a new way to *deliver* a file to the existing pipeline, not a change to how the file gets parsed. **Legal risk:** none — this only ever reads mail the depository already, automatically, sends to the user; nothing is requested from CDSL/NSDL that they weren't already sending. **Coverage:** universal, same as A, and removes the recurring manual-upload step entirely once set up. **Password handling, resolved:** the "no PAN persistence, ever" rule is being rewritten — PAN will now be stored, masked wherever displayed — but that turns out not to be the piece that matters here, since CDSL Easi lets users set their own password rather than always deriving it from PAN, so an unattended, formula-based decrypt wouldn't work universally anyway. The design doesn't attempt automated decryption at all: the pipeline detects and stages the encrypted attachment, and the user types the password interactively the next time they open the app — sidestepping the automation question rather than needing PAN to answer it. Storing PAN at all is a real reversal of a documented rule and should come with safeguards proportionate to handling a government ID (encryption at rest, scoped access, masking enforced everywhere it could surface — UI, logs, exports — not just the main display path). If AWS SES specifically doesn't fit for some reason, SendGrid Inbound Parse, Mailgun Routes, Postmark Inbound, or Cloudflare Email Routing + Workers are equivalent alternatives for the receiving/webhook layer — the mechanism is the same regardless of which one receives the mail.

### Option C — Individual broker API integration *(excluded per current decision — included for completeness)*

**What it is:** the user authorizes Unifolio through their broker's own OAuth screen (Zerodha Kite Connect, Upstox, Angel One SmartAPI, Dhan, or Fyers); Unifolio receives a token and can pull that user's holdings on demand.

**How to build it:** one integration per broker — each has its own auth flow, token-refresh behavior, and holdings-endpoint shape; Kite Connect's tokens, for instance, expire daily. **Cost:** mostly free at individual/personal-usage tiers (Zerodha even offers a free "Startups" tier by direct arrangement); no SEBI registration required of Unifolio itself for read-only access — the broker carries that relationship. **Effort:** meaningful and multiplies per broker added. **Legal risk:** none — this is the one fully sanctioned "linked account" pattern available outside AA. **Coverage gap that matters:** Groww, currently India's largest broker by active clients, has no public consumer-facing OAuth product; ICICI Direct and HDFC Securities have no public API either — so even integrating all five above still misses a large share of the market.

### Option D — smallcase Gateway *(a packaged version of Option C, same exclusion applies)*

**What it is:** one SDK/integration covering 10 brokers' holdings-import APIs at once (Zerodha, Upstox, Angel One, Dhan, HDFC Sky, IIFL, Motilal Oswal, 5paisa, Trustline, Fidsom), instead of building each broker separately.

**Cost:** no public pricing exists anywhere — it's a sales-led B2B product ("Request Demo," `gateway@smallcase.com`), likely priced via revenue share or per-user licensing typical of fintech infra deals; realistically sized for partners with existing scale or a broking relationship, not a pre-revenue MVP. **Effort:** lower engineering effort than five separate broker integrations, but a real partnership-onboarding process with its own timeline. **Legal risk:** none, same as C. **A caveat worth knowing regardless of the decision:** their own docs state that 9 of the 10 supported brokers (everyone except Zerodha) require the user to log in again through the broker each time the holdings snapshot needs refreshing — only Zerodha supports a persistent session. So even here, "linked" mostly means "reconnects easily," not "connected forever."

### Option E — Browser extension

**What it is:** a companion browser extension the user installs once, which can either (E1) passively watch for a browser download event matching a CDSL/NSDL filename pattern and silently forward it to Unifolio after the user manually downloads it themselves, or (E2) actively script clicks on CDSL/NSDL's own page after the user logs in, closer to true "auto-click."

**How to build it:** a Chrome extension (Manifest V3), Chrome Web Store listing and review, ongoing maintenance against a portal UI Unifolio doesn't control. **Cost:** developer time only, no vendor fee, but real listing/review/maintenance overhead. **Legal risk:** E1 is low — it never touches the login page or credentials at all, so the depository's credential-secrecy terms don't apply; E2 is meaningfully grayer, since scripted interaction with the portal itself may run against terms even without touching the password. **Coverage:** desktop browsers with the extension installed only — no mobile coverage, a real gap given how mobile-heavy Indian retail investing is.

### Option F — Server-side login automation ("the original auto-click idea") *(not recommended)*

**What it is:** Unifolio's own servers log into CDSL/NSDL on the user's behalf — entering their OTP, clicking through the portal, downloading the file — the thing Passbook Family's desktop app can do locally that a web app structurally cannot replicate on our servers.

**Why it's not recommended, briefly** (full reasoning already in the research doc): this is the specific pattern — a third party handling a user's live authentication with a financial institution — that RBI's Account Aggregator framework was built to move the industry away from, and it runs directly into both CDSL's and NSDL's own portal terms, which explicitly forbid revealing account credentials to any other person. No confirmed enforcement case was found, but the regulatory direction is unambiguous. **Cost/effort** would also be substantial regardless (CAPTCHA-solving, session/anti-bot handling, constant breakage against portal changes) for something built on contested legal ground.

### Option G — Real-time OTP-gated fetch (market pattern, not vendor-specific)

**What it is:** some third-party products in this space offer a live, on-demand CDSL fetch gated on the user entering a fresh OTP in real time (not a stored password) — the vendor's backend then pulls holdings from CDSL directly, automated CAPTCHA-solving included. It's the closest thing on the market to the original "auto-click" idea, and proof it's technically possible to some degree.

**Assessment:** unofficial regardless of who builds it (no CDSL-sanctioned API backs this pattern), and it carries the same server-side-authentication risk profile as Option F, just relocated to a third party's servers instead of ours — outsourcing it doesn't remove the exposure, only whose infrastructure carries it. **Recommendation:** not worth building or adopting for this phase.

### Option H — Browser-native "make the manual step disappear" tricks (layered on top of A, not a standalone option)

Three small, genuinely safe additions, each with real limits:
- **File System Access API:** the user grants our web app one-time read access to a folder (e.g., Downloads); after they download the statement there, we read it directly off disk without a manual "choose file" step. Confirmed working on **Chrome/Edge/Opera desktop only** — confirmed *not* supported on Safari, Firefox, or any mobile browser, including Chrome for Android.
- **Web Share Target API:** if Unifolio is installed as a PWA, a user can download the statement on their phone and use the OS Share sheet to send it straight to the app. Confirmed working on **Android/Chrome for an installed PWA only** — not supported on iOS/Safari.
- **BOID clipboard pre-fill:** before redirecting the user to CDSL/NSDL, copy their already-known BOID to their clipboard and show it on our own page, so they paste instead of hunting for their demat slip. This works everywhere, costs almost nothing to build, and is legally clean since it never touches the depository's page. The same trick cannot extend to PAN — Unifolio's own schema already has a hard "no PAN persistence, ever" rule, so we structurally can't remember it even for this.

**Cost/effort:** all three are small additions. **Recommendation:** worth adding once Option A is live, as UX polish — none of them are a substitute for the base upload flow, since none cover Safari/iOS/Firefox users.

### Option I — Account Aggregator *(future phase, not now — included for roadmap completeness)*

The properly regulated, persistent, revocable, broker-agnostic account-link architecture — the thing every other option on this list is an approximation of, in one way or another. Per earlier research (`MF Central API.pdf`), the AA path for a platform like Unifolio to become a Financial Information User carries real cost (₹5-25 lakh+) and timeline (5-10 months, FIU registration, Sahamati certification) — not a reason to avoid it forever, but a reason it's correctly sequenced as a later phase rather than this one.

---

## 3. Comparison at a glance

| Option | Broker-agnostic? | Automates login? | Legal risk | Cost | Effort | Data completeness |
|---|---|---|---|---|---|---|
| A — CAS/SOH upload | Yes | No (manual) | None | Free | Low-Medium | Holdings only, no cost basis |
| B — Email auto-ingestion (in-house, decided) | Yes | No (reads mail) | None | Minimal (AWS) | Low, on top of A | Same as A |
| C — Individual broker APIs | No, per-broker | No (OAuth) | None | Mostly free per broker | High, multiplies per broker | Depends on broker |
| D — smallcase Gateway | No, 10 brokers | No (OAuth), but 9/10 need re-login for refresh | None | Unknown, sales-led | Medium (one integration, real onboarding) | Depends on broker |
| E1 — Extension (passive) | Yes | No | Low | Dev time only | Medium | Same as A |
| E2 — Extension (active/auto-click) | Yes | Partially | Medium-high | Dev time only | High, fragile | Same as A |
| F — Server-side bot | Yes | Yes | High — not recommended | High (infra + legal) | High, fragile | Same as A |
| G — Real-time OTP-gated fetch (market pattern) | Yes | Yes | Medium-high | Unknown | Low (if adopted from a third party) | Live holdings, not confirmed re: transactions |
| H — Browser-native pickup tricks | Yes | No | None | Minimal | Low | Same as A |
| I — Account Aggregator | Yes | N/A — proper consent | None (once registered) | ₹5-25L+, 5-10 months | High, but future phase | Full, regulated |

---

## 4. What I think is the best option

**Option A, plus Option B built in-house, plus Option H's small additions.** In that order, and here's the reasoning, not just the conclusion:

A is the only option that is simultaneously broker-agnostic, legally clean, and mostly already built — the parsing engine exists, it's just switched off. Nothing else on this list clears all three bars. B turns A's one real weakness — "the user has to remember to come back and re-upload" — into a non-issue, using a mechanism (the SEBI-mandated auto-email) that isn't automation of anything risky, just noticing mail that was already being sent, built entirely in-house with no third-party dependency. H is free polish once A exists.

Everything else earns its place on this list for completeness, not as a live recommendation: C and D are already excluded by decision, and even without that decision, D specifically turned out to be a worse deal than it first sounds (no public pricing, most brokers still need repeated re-login). E, F, and G all trade real legal or engineering fragility for an automation benefit that B already achieves more safely, in-house. I is the correct destination eventually, just not this phase's problem to solve.

## 5. What is recommended, concretely

Build order: extend `parser.py` to stop rejecting the depository CAS → new data model (demat account, equity holdings, security master) → the explicit product decision on how to handle the missing-cost-basis gap (show holdings/allocation only, no fabricated gains, is the recommended default) → daily price refresh job → frontend reuse of the existing import UI → then, as a second phase once the above is live and stable, in-house email auto-ingestion via AWS SES. Full functional detail for the first phase is already written up in `PRD-05-Stocks-Demat-Import.md`.

## 6. How to actually do each option, if a different one gets chosen

- **A:** see §2 above and `PRD-05-Stocks-Demat-Import.md` in full — it's the fully spec'd path.
- **B (in-house — the plan):** stand up an SES receiving rule + S3 bucket + a small Lambda (or existing backend endpoint) that validates the sender against the four known depository/RTA addresses and calls Option A's import function on the attachment — the same entry point a manual upload already uses, so there's no parser change involved, only a new way for a file to arrive. SendGrid Inbound Parse, Mailgun Routes, Postmark Inbound, or Cloudflare Email Routing + Workers are drop-in alternatives to SES for the receiving layer if needed.
- **C/D:** would require reopening the "no broker APIs" decision first; if reopened, smallcase Gateway's `gateway@smallcase.com` is the starting contact for a quote and partnership terms.
- **E:** scope as a standalone Chrome extension project with its own Web Store listing and maintenance owner; start with E1 (passive) only.
- **F/G:** not recommended to build in-house or adopt from a third party.
- **H:** three small frontend additions layered onto A's upload flow whenever there's spare capacity — none are blocking or sequenced ahead of A.
- **I:** revisit as its own future-phase PRD once CDSL/NSDL are confirmed live as FIPs on the AA network and the FIU-registration cost/timeline is worth reassessing against Unifolio's stage at that time.
