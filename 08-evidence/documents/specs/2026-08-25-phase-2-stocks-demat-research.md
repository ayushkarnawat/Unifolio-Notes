# Phase 2 Research: Stocks & Demat Account Integration (CDSL/NSDL, no AA)

**Date:** 2026-08-25
**Status:** Research complete — decision needed before Phase 2 build starts
**Scope:** How to bring stock/equity holdings into Unifolio by linking users' demat accounts (CDSL/NSDL), without using the Account Aggregator (AA) framework yet. Written in direct response to the specific idea raised: redirect the user to CDSL/NSDL, have them authorize, then auto-click "Download Statement" and auto-import — the way Passbook Family (a local-first Electron desktop app) appears to do it — and whether that's replicable in a web app.

---

## Bottom line up front

The "auto-click Download Statement" idea is exactly what Passbook Family can do that we can't, for a structural reason, not a laziness reason: **it's a desktop app with an embedded browser it fully controls on the user's own machine.** A web app has no equivalent surface without either (a) a browser extension, which is a real product and distribution cost, or (b) a server-side bot that logs in on the user's behalf — which is the one pattern Indian financial regulation has spent the last several years explicitly building the Account Aggregator framework to move *away* from, and which both CDSL's and NSDL's own portal terms already prohibit via a credential-secrecy clause.

The recommended path for Phase 2 is the same shape as our existing MF CAS flow: **the user logs into CDSL Easi/Easiest (or NSDL IDeAS) themselves, downloads their own Statement of Holdings, and uploads it to Unifolio — we parse it.** This is not a compromise forced by laziness; it's the only path in this space that's simultaneously safe, buildable now, and endorsed by our own earlier competitive research (which already flagged CDSL Easi/Easiest as "the only publicly known legitimate access point," before this research went deeper into confirming why and into what the file actually contains).

The one real catch, and it's a data catch, not a legal one: **the depository CAS gives you current holdings, not equity transaction history.** That changes what Phase 2 can promise on day one — see §2.

---

## 1. Why "auto-click" doesn't translate to a web app safely

**What Passbook Family almost certainly does:** as an Electron app, it can embed a real Chromium browser view inside itself. The user logs into CDSL Easi *inside that embedded view, with their own credentials, in their own session* — Passbook's own code never sees the password — and once authenticated, the app's local script can find and click the "Download" button in the DOM it's already rendering, then read the downloaded file straight off the user's disk. Nothing about this requires Passbook's servers to touch the user's credentials or run a remote bot. (Their exact mechanism isn't publicly documented — this is the most plausible explanation given what an Electron app can do, not a confirmed fact.)

**Why a web app can't do the same thing cleanly:**

| Approach | What it requires | Risk |
|---|---|---|
| **Server-side bot** (our backend logs into CDSL/NSDL on the user's behalf, using their OTP) | User's credentials/OTP flow through our servers | **Avoid.** This is structurally the "screen scraping" pattern RBI's AA framework (NBFC-AA Master Directions, 2016, §5.9 and §8(b)) was built to eliminate — AAs are explicitly barred from ever seeing FIP credentials. SEBI has since directed CDSL/NSDL to onboard as Financial Information Providers on the AA framework (SEBI circular, Aug 2022), meaning the regulator's sanctioned channel for exactly this data is AA, not scraping. Both CDSL Easi/Easiest's and NSDL IDeAS's own terms separately forbid revealing the account password "to any other person" — a bot holding the password mid-login is squarely what that clause exists to prevent. No confirmed enforcement case was found against an Indian fintech for this specifically, but the regulatory direction is unambiguous enough that building on it now is building on borrowed time. |
| **Browser extension** (runs in the user's own browser/session, automates the click after they log in themselves, never sees the password) | User installs an extension; Chrome Web Store review; doesn't work on mobile web | **Meaningfully lower risk** than a server bot — credentials never leave the user's own browser or reach us — but not zero: portal terms may still restrict automated interaction even without credential sharing, the automation breaks every time CDSL/NSDL change their page markup, and it adds real product/distribution overhead (install friction, no mobile coverage, ongoing maintenance against a UI we don't control). Worth keeping as a possible *later* power-user convenience layered on top of the manual flow, not as Phase 2's foundation. |
| **Manual: redirect → user logs in and downloads → user uploads the file to us** | Nothing beyond what we already built for MF CAS | **Safe.** The user, not our infrastructure, performs the regulated action — same trust model as the CAMS/KFintech flow already live. This is the only one of the three with no open legal question mark. |

None of the depository websites' terms contain a blanket "no bots" clause as such — the actual prohibition is the credential-secrecy clause, which the server-bot approach runs into directly and the extension approach mostly avoids.

**Recommendation: build the manual flow.** It gets ~90% of the UX win (no manual re-typing of holdings, one upload, done) with none of the open legal exposure, and matches the pattern users already went through for their MF CAS.

---

## 2. What's actually in a CDSL/NSDL statement — this changes the Phase 2 scope

We already have a strong signal on this without leaving our own codebase: `casparser` (the library our MF import already uses) parses NSDL/CDSL depository statements into an `NSDLCASData` object today — our `parser.py` detects this and explicitly rejects it ("Equity/demat statements aren't supported in this version"). Reading `casparser`'s actual source confirms what that object contains:

- `NSDLCASData.accounts[].equities[]` = `{name, isin, num_shares, price, value, symbol, exchange}` — **a point-in-time holding snapshot: how many shares, at what price, worth what, as of the statement date.**
- There is **no per-transaction buy/sell record for equities anywhere in the model** — no purchase date, no purchase price, no `TransactionType` for equities at all (that enum only exists for the MF side, CAMS/KFintech).
- Demat-mode mutual funds and bonds follow the same pattern: holdings, not ledgers.

**What this means concretely:** uploading a CDSL/NSDL CAS gets a user's stock holdings and current value onto their dashboard — real progress, and it directly extends the pipeline we've already built (same `casparser` call, same PDF+password upload UI, same parse→review→confirm flow). But it does **not** give us cost basis, so it can't drive capital-gains/XIRR/realized-gains math for stocks the way it does for mutual funds, unless the source data changes.

Two things narrow this gap, both worth verifying before the PRD is written rather than assumed:
- **CDSL Easi/Easiest also offers a separate "Statement of Transactions" (SOT)** download, distinct from the CAS/Statement of Holdings. Whether it carries per-trade *prices* for equities (which would restore cost-basis capability) is still unconfirmed, and a follow-up look turned up a discouraging signal rather than a confirming one: Zerodha's own support docs describe SOT in debit/credit movement terms ("shares sold reflect as a debit entry, purchased as a credit entry"), classified by transaction-type codes (`ON-DR`/`ON-CR`, `PAYOUT-CR`, `CA-Bonus`, etc.) — reading like a custody-movement ledger (what moved, when, why) rather than a priced trade blotter, consistent with a depository being a registry of ownership rather than the system that records execution price. `casparser` doesn't parse SOT at all today — supporting it would be new parser work from scratch, not a patch to the existing NSDL model. **Before committing any engineering time to it: get one real sample SOT PDF (register on CDSL Easi, request a statement over a period with real trades) and check by hand whether a price field exists at all.** If it doesn't, this gap is a hard floor for the depository-statement approach specifically, not a fixable parser limitation.
- **We already built the right shape of fallback for exactly this situation.** The recent CAS-import-lifecycle work added an `OPENING_BALANCE` transaction type specifically for "we don't have this folio's full history, here's what we know as of a point in time." Equity holdings from a depository CAS are a natural fit for the same concept: record them as an opening balance at the statement's price/date, flag that realized-gain/XIRR math can't run further back than that point, and let it refine itself if the SOT (or a future broker-API transaction feed) fills in the real history later. This avoids either blocking the whole feature on missing data, or quietly faking a cost basis.

MProfit, for comparison, sidesteps this gap entirely by importing **broker contract notes/tradebooks** instead of depository statements for equities — those do carry transaction-level data. That's a heavier lift (broker-specific file formats) but is the more accounting-complete path; worth keeping in mind as a "Phase 2.5" option if the SOT doesn't pan out.

---

## 3. Broker APIs — a real complementary track, not a full substitute

Zerodha (Kite Connect), Upstox, Angel One (SmartAPI), Dhan, and Fyers all offer a broker-hosted OAuth-style consent flow: the user is redirected to their broker's own login (never ours), authenticates there, and the broker hands back a token scoped to that user's holdings. None of the five appears to require the requesting app to itself be a SEBI-registered broker/RA/IA for read-only holdings access — the broker carries that regulatory relationship, not us. Zerodha's individual/personal-use tier is free; a dedicated "Startups" free tier exists by direct arrangement for retail-facing apps. This is a legitimate, sanctioned way to get real-time holdings (and, depending on the broker's data richness, potentially transaction history — worth confirming per broker) for users on that specific broker.

The catch is coverage, not legitimacy: **Groww — currently India's largest broker by active clients — has no public consumer-facing OAuth product for third-party apps**, only a self-service API-key model aimed at a user automating their own account. ICICI Direct and HDFC Securities (large bank-broker user bases) have no public API found either. Building bespoke integrations even for all five brokers above would still likely miss a large share of the market.

**`smallcase Gateway`** is worth flagging specifically: it's a B2B SDK offering a single integration surface for OAuth-based "Holdings Import" across 10 brokers (Zerodha, Upstox, Angel One, Dhan, HDFC Sky, IIFL, Motilal Oswal, 5paisa, Trustline, Fidsom) via one partnership onboarding, rather than five-plus separate builds. If the broker-API track is pursued at all, this is the more efficient entry point than integrating brokers one at a time.

**Recommendation:** treat broker APIs (via smallcase Gateway, ideally) as a **complementary, opt-in "connect your broker for live updates" layer**, not the primary coverage mechanism — the CDSL/NSDL statement upload remains the only broker-agnostic path that covers a user regardless of who they trade through, which is exactly the same reasoning that made CAS-PDF-first the right call for mutual funds before RTA/AMFI registration.

---

## 4. Competitive landscape — recap and one new data point

This confirms and sharpens what our own `competitiveanalysis_updated.pdf`/`combinedfeatureparitymatrix.pdf` already found: five of eleven tracked competitors now run production Account Aggregator integrations, CDSL Easi/Easiest-based import is confirmed for exactly one (Passbook Family, mechanism unverified), and no competitor was found with public documentation of a non-AA, non-broker depository sync — Passbook is the closest signal, not a confirmed blueprint. MProfit's contract-note/tradebook approach (see §2) is a genuinely different, broker-document-based alternative worth keeping on the radar rather than an endorsement of any depository-automation shortcut.

---

## 5. Recommended Phase 2 shape

1. **Layer A — CDSL/NSDL statement upload (do this first).** Extend the existing `casparser`-based import pipeline to accept `NSDLCASData` instead of rejecting it: new `Equity`/`Bond`/demat-`MutualFund` handling in the data model, same upload/password/review/confirm UX already live for MF CAS, holdings recorded via the existing `OPENING_BALANCE` mechanism given the no-transaction-history constraint. Gives real stock visibility and portfolio-wide net worth/allocation without new legal exposure or new infrastructure classes.
2. **Layer B — broker API, opt-in, via smallcase Gateway if pursued.** A "connect your broker" convenience layer for live holdings refresh on the brokers it covers, explicitly scoped as additive, not the coverage backbone.
3. **Layer C — Account Aggregator, later.** Already the plan; nothing here changes that timeline, and CDSL/NSDL are already directed by SEBI to participate as FIPs on AA, so this path only gets more complete with time, not less.

## Open questions to resolve before writing the Phase 2 PRD

- Does CDSL Easi/Easiest's **Statement of Transactions** actually carry equity trade-level dates/prices? (Would remove the cost-basis gap in §2 — highest-value thing to check, e.g. by requesting a real sample statement.)
- NSDL's **IDeAS** registration/OTP flow wasn't as clearly documented publicly as CDSL Easi's — confirm it's the same BOID+PAN+OTP shape before assuming parity.
- If Layer B is pursued: confirm smallcase Gateway's partnership terms/cost, and whether any of the five direct broker APIs expose transaction (not just holdings) history for users who connect that way.
- Decide, as a product call rather than a technical one, whether a browser-extension "auto-click" convenience layer is ever worth building later as a power-user option on top of the safe manual flow — not a Phase 2 blocker either way.

---

## 6. Correction: linking the demat account itself, not importing a CAS statement

Everything above (§1-2) was scoped around the CAS/Statement-of-Holdings *upload* path — the safe, broker-agnostic fallback. That's a fair Phase 2 floor, but it's a document import, not an account link, and it's a fair question to push back on if what you actually want is the "Add Demat Account" experience Passbook Family shows — connect once, holdings stay current, no re-upload ritual. Worth being straight about what's actually available for *that*, specifically outside AA:

**There is no official, broker-agnostic way to "link" a CDSL/NSDL demat account itself outside of Account Aggregator.** That's not a gap in this research — it's the reason AA exists. AA is precisely the persistent, revocable, consent-based account-link architecture (think Plaid, but India-regulated) for exactly this kind of connection, and CDSL/NSDL are already directed by SEBI to participate in it as FIPs. Anything that tries to replicate "linked account, live sync" at the raw depository level before AA is, by construction, working around the absence of the thing AA was built to provide — which is why every option below is either broker-specific or carries some version of the gray-zone tradeoffs already covered in §1.

Ranked by how close each actually gets to a real "linked account" feel, broker-agnostic depository level or not:

1. **Broker API connect (Kite Connect / Upstox / Angel One / Dhan / Fyers, or smallcase Gateway's unified 10-broker SDK)** — this is the one that's genuinely an account *link*, not a document import: the user authorizes once through their broker's own OAuth screen, and Unifolio can pull holdings on demand afterward without the user doing anything else. It's the closest thing to what you're describing that's fully sanctioned today. Two caveats: it's per-broker, not depository-level (a Zerodha-linked account only refreshes Zerodha's view of that user's holdings — though for most retail users, their broker's view *is* their demat holdings, since the broker's back office already syncs with CDSL/NSDL on the user's behalf); and tokens aren't permanent — Kite Connect's, for instance, expire daily, so "linked" here means "reconnects easily," not "connected forever with zero touch."
2. **A live OTP-gated depository fetch** — this is the only broker-agnostic option that behaves like a direct CDSL link rather than a broker link, and it's the one closest in spirit to your original "redirect, authorize, auto-pull" idea. But it's not a persistent link either — CDSL's OTP model means each sync needs a fresh OTP from the user, so it's "click sync, get an OTP, holdings refresh" rather than "connect once, forget it." It's also unofficial (no CDSL-sanctioned API backs anything like this) and sits in the grayest part of the legal spectrum from §1, whether attempted on our own servers or a third party's — either way, a server is transacting against CDSL's own login on the user's behalf in real time.
3. **Everything else (CAS/SOH upload, email auto-ingestion)** is a document-import pattern dressed up to feel less manual — genuinely useful, safe, and worth building, but honestly not "linking an account" in the sense you mean.

**Practical recommendation:** treat broker-API connect (option 1, via smallcase Gateway for coverage) as the real "link your account" feature for Phase 2 — it's sanctioned, it's a real persistent-feeling connection, and it covers a meaningful chunk of users directly. Keep CAS/SOH upload (§1-2) as the fallback for anyone not on a covered broker. Don't invest Phase 2 engineering in replicating a true depository-level link (option 2) via gray-area automation — that's precisely the capability AA delivers properly and on a defensible legal footing once CDSL/NSDL are live as FIPs, so building a fragile workaround now mostly means re-solving, with more risk, a problem that's already on your roadmap to be solved correctly.

## 7. Addendum: automation options beyond "auto-click" (follow-up research)

The question worth separating out from "auto-click" is *what* we're actually trying to automate: getting the file, or getting the recurring re-import off the user's plate. Auto-click targets the first. The strongest option below targets the second, and turns out to be both safer and more automated than auto-click would have been.

### A. Email-based auto-ingestion — the strongest option, and it changes the picture

This is the single most important new finding: **SEBI already mandates that CDSL, NSDL, CAMS, and KFintech automatically email every investor their CAS** — monthly if there were transactions, half-yearly if not — to whatever email address is registered with the depository/RTA, with no user action required to trigger it (confirmed via SEBI's July 2024 circular, effective from April 2025). The statement already shows up in the user's inbox on its own, forever, for free. The only thing missing is a way for Unifolio to notice it arrived.

Two ways to do that, both real, no browser automation involved, no credentials touched:

- **Gmail OAuth (read-only, scope-limited).** User connects their Gmail once via standard Google OAuth consent — the same "Sign in with Google"-style flow already familiar to users, fully sanctioned by Google, no depository ToS implicated at all since we're reading the user's own inbox with their own consent, not logging into CDSL/NSDL. Restricting the scope to only messages from known depository/RTA sender addresses (see below) keeps it defensible for Google's app-verification review. After that one-time consent, every future CAS email gets picked up automatically — no re-authorization, no manual re-upload, indefinitely.
- **Inbound-forwarding address (no OAuth at all).** We generate a unique address per user (e.g. `import-aditi123@import.unifolio.in`); the user sets up a one-time forwarding rule in their email client so mail from CDSL/NSDL/CAMS/KFintech auto-forwards there. Lower engineering lift than Gmail OAuth (no Google review process), and it works regardless of email provider (Gmail, Outlook, Yahoo, a company email address) — Gmail OAuth only covers Gmail users.

**The SEBI auto-email mandate is machine-detectable in practice, not just on paper: the four sources send from known, stable addresses** — `eCAS@cdslstatement.com` (CDSL), `NSDL-CAS@nsdl.co.in` (NSDL), plus CAMS's and KFintech's own no-reply sending addresses. Validating an inbound attachment against these four before ever processing it is the core of the sender-check logic either ingestion mechanism above needs.

**Decision: build this in-house**, on AWS SES (already the team's cloud stack, per `ADR-Technical-Stack-Decisions.md`). A receiving rule validates the sender against the four known addresses above, drops the matched attachment to S3, and hands it to the exact same `parser.py` entry point a manual upload already uses — no new parsing logic, no per-email metered cost, no third party gaining access to users' financial statements. SES's other inbound-email-capable alternatives (SendGrid Inbound Parse, Mailgun Routes, Postmark Inbound, Cloudflare Email Routing + Workers) are equally viable substitutes for the receiving/webhook layer if SES specifically doesn't fit — the mechanism (validated sender → attachment → existing parser) is identical regardless of which one is used; SES is only the natural default because the rest of the stack is already AWS.

**Update: this open question is now resolved, by decision rather than by discovering new data.** Two things settled it: first, the "no PAN persistence, ever" rule is being rewritten — Unifolio will now store PAN, masked wherever it's displayed. Second, and this is the part that actually simplifies the design: the CAS/statement password isn't reliably PAN-derived anyway — CDSL Easi lets a user set their own password at registration, so a formula-based auto-decrypt attempt wouldn't have worked universally even with PAN in hand. So the resolved design doesn't attempt unattended decryption at all: the email-ingestion pipeline's job is only to detect, validate, and stage the encrypted attachment — decryption still always happens interactively, with the user typing the password themselves, just at whatever point they next open the app rather than at upload time. That sidesteps the automation question rather than needing to answer it.

Worth flagging plainly, since it's a real reversal of a documented non-negotiable, not a footnote: storing PAN raises the stakes of a data breach — it's a government identity number, not an arbitrary account field — so it should come with safeguards proportionate to that (encryption at rest, tightly scoped access, and masking enforced everywhere PAN could surface — UI, logs, error messages, exports — not only the primary display path). That's a note for whoever implements the schema change, not a reason to reverse the decision.

**Net effect:** a user connects their inbox (or sets up the forward) one time; Unifolio's stock holdings stay current automatically, with the user only needing to type a password when a new statement is waiting — a better outcome than auto-click would have given us, since auto-click still would have needed the user to periodically re-trigger a full login/download cycle. This should probably be the centerpiece of "automation" in the Phase 2 PRD, not a footnote.

### B. Passive download capture (a lighter-weight extension option)

A narrower, lower-risk version of the browser-extension idea from §1: instead of an extension that logs in or clicks anything, it only listens for the browser's own download event (`chrome.downloads` API) and silently forwards a file to Unifolio when its name/source matches a known CDSL/NSDL/CAS pattern — after the user has manually clicked "Download" themselves. It never touches the login page or credentials, so it sidesteps the credential-secrecy clause entirely; the remaining question is just whether an extension observing downloads runs afoul of anything in the portal's terms, which seems unlikely since it never interacts with the portal at all. Still carries the standard extension costs (install friction, Chrome Web Store review, no mobile coverage) — a nice-to-have layered on top of the email path, not a substitute for it.

### C. Ranking

For "automate the recurring re-import," in order of recommendation: **(1) email-based auto-ingestion (§A)** — safest, most complete automation, and the one being built in-house; **(2) broker API sync (§3 above)** for whichever brokers a user connects — proper automation, but coverage-limited; **(3) passive download-capture extension (§B)** — a nice-to-have on top of the manual flow. A real-time OTP-gated fetch (§6, option 2 above) was considered and set aside — it carries the same server-side authentication exposure as §1's automation risk regardless of whose servers run it, and isn't worth pursuing for this phase.

---

## 8. The actual ceiling: what's left to automate in a plain web app, no credentials, no extension

One more honest pass at this, since it's worth pinning down exactly where the line is rather than leaving it fuzzy. Split the flow into two steps: **(i)** the user logs into CDSL Easi/NSDL IDeAS and downloads their statement, and **(ii)** that file gets into Unifolio. Everything in this doc so far has been about why (i) can't be automated without touching credentials (server bot) or an extension. Step (ii), the "now hand us the file" part, actually has two standards-based browser mechanisms that need neither credentials nor an extension — confirmed against current browser-support data, not assumed:

- **File System Access API (`showDirectoryPicker`)** — the user grants our web app one-time read permission on a folder (e.g., their Downloads folder); afterward, when they download the CDSL/NSDL statement there and return to our tab, we can find and read the new file directly off disk — no "choose file," no drag-and-drop. It touches no credentials and no CDSL/NSDL page at all, so none of §1's legal exposure applies. **The real limit is browser support: Chrome/Edge/Opera on desktop only — confirmed unsupported on Safari, Firefox, and every mobile browser including Chrome for Android.** Useful for desktop power users, not a general solution given how mobile-heavy Indian retail investing is.
- **Web Share Target API (file-capable)** — if Unifolio is installed as a PWA, a user can download the statement on their phone and use the OS "Share" sheet to send that file straight to the Unifolio app instead of us asking them to upload it. Confirmed working on Android/Chrome for an installed PWA; **not supported on iOS/Safari**, and itself flagged as non-Baseline/experimental by MDN.

So the honest answer: there's no way to automate step (i) without either credential handling or a sanctioned API (already covered at length above), but step (ii) can genuinely disappear for desktop Chrome/Edge users and Android PWA users specifically — worth adding as a UX nicety once the core manual-upload flow (§9 below) is live, not a reason to delay it, since neither covers Safari/iOS/Firefox and the manual "choose file" flow has to keep working as the baseline regardless.

### 8a. Pre-fill / pre-select tricks on redirect — one real option, one hard no

CDSL/NSDL's login page is on their domain, not ours — we have no ability to inject values into their form or pass prefill data via URL; that's a cross-origin wall, same root cause as everything else in this doc. But on **our own page**, right before redirecting, we can copy the user's BOID (16-digit demat account number — not PAN) to their clipboard and surface it prominently, so they paste it into CDSL's first field instead of hunting for their demat slip. That's genuinely available and genuinely legal, since it never touches CDSL's page at all.

PAN is the other field CDSL asks for, but only at first-ever registration (combined with DOB, to bootstrap a username/password) — after that, a returning user logs in with just their self-chosen username/password, not PAN again. **Update:** with the "no PAN persistence" rule now being rewritten to allow storing PAN (masked on display — see §7-A's update), the same clipboard pre-fill trick could be extended to PAN for that one-time registration case too, if the UX gain is judged worth it for something that only ever matters once per user. No evidence was found of a documented deep-link that skips past login to a specific report/date-range directly — unconfirmed either way, would need live inspection of the actual portal rather than assumed.

## 9. Recommended build sequence (broker APIs explicitly excluded, per decision)

Ayush/Aditi have ruled out broker API integration for this phase — no Kite Connect/Upstox/Angel One/Dhan/Fyers/smallcase Gateway. That removes the one option with an official, sanctioned "linked account" feel (§6) and leaves the CAS/SOH-upload path as the whole of Phase 2's core, with email auto-ingestion as its automation layer. Revised build order:

**Part 1 — Stop rejecting `NSDLCASData`, backend.** `parser.py` already detects a CDSL/NSDL demat CAS via `isinstance(result, NSDLCASData)` and raises a deliberate `ParseError` today — that's the one line of behavior to change. Add a `_normalize_demat_cas_data` function parallel to the existing `_normalize_cas_data`, extracting `accounts[].equities[]` (ISIN, symbol, exchange, shares, price, value), demat-mode `mutual_funds[]`, and `bonds[]`. Same `casparser.read_cas_pdf()` call already in use — no new parsing dependency.

**Part 2 — New data model.** A `DematAccount` entity (BOID/DP ID/client ID, owners — mirrors `Folio` for MF), an `EquityHolding` table (ISIN, symbol, exchange, quantity, last-known price/value, source statement date), and a lightweight security-master reference table (ISIN → symbol/company name/exchange) refreshed from an NSE/BSE bulk file — the same pattern already used for `scheme_universe.py`'s AMFI `NAVAll.txt` ingestion for mutual funds, just pointed at an equities bulk list instead. `Decimal` throughout, per the non-negotiable.

**Part 3 — The cost-basis decision (needs Ayush's call before this goes further).** The depository statement is holdings-only — no purchase date, no purchase price for equities (confirmed in §2). Three honest options, not a technical question so much as a product one: (a) show current holdings/value and portfolio allocation only, explicitly no gain/loss or XIRR for stocks until real transaction data exists — the safest, most consistent-with-existing-philosophy choice, matching the "never silently guess" rule already applied to AMFI scheme matching; (b) let the user manually enter a purchase price/date per holding, opt-in, clearly labeled as user-supplied, not statement-derived; (c) infer a synthetic buy/sell at the statement's own price whenever quantity changes between two consecutive statement uploads — technically possible but produces numbers that look precise while being an approximation, which cuts against the existing "surface uncertainty, don't fake precision" convention. Recommend (a) for v1, with (b) as a fast-follow.

**Part 4 — Ongoing valuation.** Stock prices go stale the moment the statement is imported, unlike MF NAVs which `nav.py` already refreshes daily from mfapi.in. Needs an equivalent daily job pulling NSE/BSE closing prices in bulk (their own bhavcopy-style EOD files are free and match the pattern `nse_indices_client.py` already uses for benchmark data) keyed by ISIN, feeding the same `EventBridge Scheduler` + on-demand-fetch pattern already decided in ADR-006 for NAVs.

**Part 5 — Frontend.** Extend the existing CAS upload flow (`UploadForm.tsx`, review/confirm screens) to accept a CDSL/NSDL statement through the identical drag-and-drop-PDF-plus-password UI, with a review screen showing equities/bonds as their own section rather than folded into MF schemes. Dashboard gets a Stocks holdings table and an allocation bucket for equities, reusing `FundSignal`/`HoldingsTable`-style components where the shape fits.

**Part 6 — Email auto-ingestion, once Parts 1-5 are live.** Build in-house, per the decision above: an inbound-forwarding address per user is the lower-lift version and fits the existing AWS-centric stack directly — AWS SES inbound email receiving, dropping matched attachments to S3, triggering the same import pipeline Part 1 built, no new vendor relationship and no Google OAuth-verification process to run. Gmail OAuth read-only is a heavier, later option if the forwarding-rule setup step proves too much friction for users.

**Explicitly not doing, per this decision:** any broker OAuth integration (§3/§6), a real-time OTP-gated fetch pattern (§6/§7-C), and any form of server-side or extension-based login automation (§1).

---

*Sources and detailed findings from the underlying research (casparser source, CDSL/NSDL FAQ PDFs and T&Cs, RBI Master Directions, SEBI circulars, broker API docs, SEBI's July 2024 CAS-email-mandate circular coverage) are available in the session's research notes if needed for citation in a future PRD.*
