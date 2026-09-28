# PAN Verification at Signup, KYC, and PAN-Usage Rules — Research

**Date:** 2026-09-23
**Status:** Research only. Nothing here is built or decided.
**Builds on:** `Docs/pan-cas-attribution-feature-documentation.md` (encrypted PAN + lookup hash on
`household_members`, 30-day CAS retention, PAN-based attribution), `infra/modules/security`
(the `pan_keys` Secrets Manager secret + CMK), `infra/modules/storage` (CAS S3 bucket).

> **Conflict to resolve first (per CLAUDE.md):** `PRD-02-Signup-Onboarding.md` §Non-Goals/§Out of
> Scope and `DEFERRED_FEATURES.md` line 34 list "KYC/identity verification beyond CAS parsing"
> as **not built, N/A (permanent)**, and `decisions.md` still describes ADR-004's old
> no-PAN-storage rule as "final, non-negotiable" — even though the 2026-09-18 work reopened it.
> Adding PAN verification at signup would reverse the PRD-02 non-goal. That's a product
> decision for you to make; this doc doesn't make it. (`decisions.md` is stale either way.)

> **Legal caveat:** this is engineering research, not legal advice. Items marked **[counsel]**
> need a lawyer who knows Indian fintech and data-protection law before launch.

---

## TL;DR

| Question | Short answer |
|---|---|
| 1. Can PAN be verified at signup? | **Yes.** It's a synchronous API call that takes about 1 second and costs about ₹1–5. |
| 1b. Do we get the name back? | **It depends on the route.** The official ITD/Protean route only returns **yes/no match flags**: you send name + DOB and it confirms or denies. Some aggregators return the **registered name**, and DigiLocker returns the issued PAN document. |
| 1c. Does it prove the user *owns* that PAN? | **No.** This is the most important finding. PAN verification proves a PAN exists and matches a name. It does **not** prove the person typing it is that person. Ownership needs an OTP to a contact the PAN holder registered (DigiLocker's Aadhaar OTP, or MF Central / RTA-registered email or phone). |
| 2. Do we need KYC? | **Not as a pure tracker** (no transactions, no advice, no money handling). KYC becomes mandatory only if Unifolio becomes an MF distributor, execution-only platform, investment adviser, or Account Aggregator FIU. One flag: the fund **scorer** could be read as "advice" **[counsel]**. |
| 3. PAN-usage rules | No law stops a private company collecting PAN **with consent, for a stated purpose**. The governing regime is the **DPDP Act 2023 + DPDP Rules 2025** (substantive obligations from **14 May 2027**), with IT Act §43A / SPDI Rules 2011 until then. Vendor contracts also require a consent flag and a purpose string on every call. |
| 4. Tech/infra/cost | **No new AWS services.** You'd add one vendor adapter module, a migration (verification fields + consent log), two endpoints, and one secret. Vendor cost at 1,000 users is roughly **₹2k–8k total**, one-time. The AWS delta is about **$0.40/month**. |

---

## 1. PAN verification at signup, and getting the name

### 1.1 The three routes

**Route A — Official PAN verification via an aggregator (flags only)**
- Source of truth: the Income Tax Dept's Online PAN Verification (OPV), run by Protean (ex-NSDL).
- It returns: PAN status (valid / deleted / deactivated / fake), **name match Y/N**, **DOB match
  Y/N**, Aadhaar-seeding status (operative / inoperative). It does **not** return the name.
  This is confirmed by Protean's own overview page and by Sandbox.co.in's API schema.
- Sandbox.co.in's request requires `pan`, `name_as_per_pan`, `date_of_birth`, `consent: "Y"`,
  and a `reason` string (≥ 20 characters).
- **Going to Protean directly isn't possible for us.** OPV registration is limited to regulated
  or government entities (RBI/SEBI/IRDAI/PFRDA-regulated entities, SFT filers, >500-deductee TDS
  filers, and so on). The fee is ₹12,000/yr + GST. Unregulated platforms go through aggregators.

**Route B — Aggregator "PAN details" APIs (return the registered name)**
- Examples: **Eko** (from ₹1.20/verification excl. GST; returns full registered name,
  category, name/DOB match, seeding status; production keys only after business KYC), and
  **Cashfree Secure ID** (returns `registered_name` + `name_provided`, plus an optional
  `nameMatchScore`). Surepass, Signzy, IDfy, Perfios, Deepvue and Setu offer similar products.
- **Caveat:** since OPV itself only returns flags, ask each vendor where their name comes from
  and what their legal basis is before signing. Get the answer in writing **[counsel]**. Some
  "PAN Advanced" products also return masked Aadhaar, email, phone and address. **Don't use
  those.** They collect far more than we need, which works against DPDP data minimisation.

**Route C — DigiLocker (consented, and it proves ownership)**
- The user is redirected to DigiLocker, logs in with an **Aadhaar OTP**, and consents to sharing
  their PAN (`PANCR` scope). We get back the ITD-issued PAN document, including name and DOB.
- Aggregators (Setu, Digio, Signzy, Sandbox, Eko) wrap it. Eko advertises from ₹2.50/request.
- **This is the only route that also proves ownership.** The OTP goes to the Aadhaar-linked
  mobile, not to whatever the user typed.
- Costs: noticeably more friction (redirect plus Aadhaar OTP), and the user needs an
  Aadhaar-linked mobile. It also brings Aadhaar into our data flow. Even with only masked data
  coming back, that is a compliance surface (§3.3).

**Route D — What we already have (free)**
- Every CAS import already gives us the PAN plus the investor name as the RTA (CAMS/KFintech)
  holds them. RTA records are themselves KYC'd through the KRAs. Today's attribution flow uses
  this.
- A CAS the user **pulls from MF Central** (OTP to the RTA-registered email/phone) is decent
  proof of ownership. A PDF someone uploads is not; they could have got another person's CAS.

### 1.2 Why "verify PAN at signup" doesn't fix what it seems to fix

The existing cross-account block ("this PAN is already tracked under another account") is the
fraud guard. Consider an impostor who signs up first with someone else's PAN:
- **Routes A/B pass.** The PAN is real and the name matches, because the impostor knows the name.
- The real owner then signs up later and is **locked out** of their own PAN.

So Routes A/B, used alone at signup, make that failure *easier* to trigger, not harder. The
real owner hits the block the moment they type their own PAN. Only an ownership-proving step
(Route C, or an MF Central OTP) is a sound basis for "this PAN belongs to this account." That
drives the recommendation below.

### 1.3 Recommendation

1. **Collect PAN at signup (optional or required, your call) and verify it with Route B
   (name-returning).** The user gets the "we found you: *R**** K****R*" moment, we pre-fill the
   SELF household member's name, and typos and fake PANs are caught before CAS import. Note
   that `users` has no name column today, so the name currently only lives on `household_members`.
2. **Don't treat Route B as ownership.** Mark the PAN `verified_exists`, not `verified_owner`.
3. **Resolve PAN collisions by ownership, not by who registered first.** When an A/B-verified
   PAN collides with another account, offer a **DigiLocker (Route C) or MF Central proof**. Whoever
   proves ownership keeps the PAN, and support handles the rest. That gives Route C's cost and
   friction only to the rare contested cases.
4. Keep CAS-derived PAN (Route D) as the primary attribution signal. It already works.

**Enumeration tradeoff** (same shape as session.md item 9's phone-OTP issue): checking
`pan_lookup_hash` at signup and saying "this PAN is already registered" reveals to anyone that
a given PAN uses Unifolio. Options: a generic message plus routing into the ownership-proof
flow, or rate-limiting plus CAPTCHA on the PAN step. This is your decision.

---

## 2. Do we need a KYC system?

### 2.1 Not for what Unifolio is today

KYC (SEBI KYC via KRAs, CKYC via CERSAI, PMLA obligations) attaches to **regulated
intermediaries**: MF distributors (AMFI ARN), execution-only platforms (SEBI 2023 framework,
Category I via AMFI / Category II via exchanges), investment advisers (SEBI IA Regs 2013),
stockbrokers, and Account Aggregator FIUs. A **read-only tracker**, which is the MProfit and
most-tracker-apps model, is none of these. PRD-02 §184 already records this reasoning.

**Flag [counsel]:** the fund **scorer** (`Updated_and_Approved_Unifolio_Fund_Scoring_Methodology.md`).
If scores are shown as "buy / switch to X", that can look like investment advice under SEBI IA
Regulations. Keep the wording descriptive ("scores", "rankings", "how it compares") and never
make a personalised recommendation to act, unless and until Unifolio is registered.

### 2.2 When KYC *would* become necessary

| Future feature | Registration | KYC implication |
|---|---|---|
| Transacting in MFs (regular plans, earning commission) | AMFI ARN (MFD) | Investor KYC via KRA. The AMC/RTA verifies it at transaction time. You check KRA status and collect KYC for new investors. |
| Transacting in direct plans | SEBI EOP (Cat I/II; Cat II ≈ ₹10 lakh deposit) | Same as above |
| Personalised advice | SEBI RIA | Client KYC, risk profiling, agreements |
| Auto-fetching holdings via Account Aggregator | Must be a regulated FIU | Handled inside that regime |

### 2.3 If KYC is ever needed — how it's done (for reference)

1. **KRA lookup by PAN** (CVL / NDML / CAMS / KFin / DotEx). If the investor is already
   KYC-validated, you're mostly done. Access is limited to SEBI intermediaries.
2. **CKYC (CERSAI) search and download** using the KYC identifier.
3. **New KYC:** Aadhaar e-KYC or offline XML through DigiLocker, PAN verification,
   in-person verification (video KYC), e-sign, then upload to the KRA.
4. Vendors bundle all of this: Digio, Signzy, IDfy, HyperVerge, Perfios. Budget roughly
   ₹30–100 per full KYC. These are market estimates, not quotes.

None of this applies until one of the §2.2 rows does.

---

## 3. PAN usage rules for Indian products

### 3.1 Income-tax law
- Income-tax law requires PAN to be **quoted** in specified transactions (Rule 114B, e.g. MF
  purchases > ₹50k). That obligation falls on the investor and the AMC, not on us. No provision
  bars a private company from collecting PAN with the holder's consent.
- **[counsel]** The Income-tax Act 2025 replaced the 1961 Act from 1 April 2026, so rule
  numbers (114B, etc.) may have changed. Recheck any specific citations.
- Direct OPV access is limited to the entity categories in §1.1. Using an aggregator is the
  normal path; vendor terms put consent and purpose obligations on us.

### 3.2 Data protection — the rules that actually bind us
- **DPDP Act 2023 + DPDP Rules 2025** (notified 13 Nov 2025). Phased: substantive obligations
  from **14 May 2027**. Relevant duties:
  - An **itemised notice** plus **specific consent** for "verify your PAN to identify you and
    match your statements". Keep this separate from CAS-parsing consent if the purposes differ.
  - **Purpose limitation:** don't reuse PAN for marketing, credit checks, and so on.
  - **Reasonable security safeguards.** The penalty for failure goes up to ₹250 cr. Our
    AES-256-GCM + peppered hash + KMS-backed secret design is a good baseline.
  - **Erasure** once the purpose ends or consent is withdrawn. This ties into the existing
    `pending_deletion` / `deletion_scheduled_at` flow, which must also wipe `pan_encrypted`,
    verification rows and vendor references.
  - **Breach notification** to the Data Protection Board and to affected users.
  - Consent withdrawal must be as easy as giving consent.
- **Until May 2027:** IT Act §43A + SPDI Rules 2011 apply (reasonable security practices,
  a privacy policy, consent for sensitive data).
- **Practical implication:** start logging consent now (the §4.2 table). Retrofitting consent
  evidence later is much harder.

### 3.3 Aadhaar (only if we use DigiLocker, Route C)
- The Aadhaar Act restricts storing and using Aadhaar numbers. **Never store the Aadhaar number.**
  Request only the `PANCR` (PAN) scope, not `ADHAR`. Drop masked Aadhaar and address fields at
  the adapter boundary.
- Aadhaar-seeding status (a Y/N from Routes A/B) is not Aadhaar data and is safe to keep.

### 3.4 Display and logging
- Keep today's rules: the PAN is never returned unmasked, and only masked PAN (`A****1234F`) is
  shown. Also **never log the PAN or the vendor's raw request/response**, including in
  CloudWatch. That needs an explicit redaction step in the vendor HTTP client.

---

## 4. Technical design

### 4.1 Signup flow (Route B, plus Route C on collisions)

```
Onboarding step "Verify PAN"  (after OTP login, before CAS upload)
  user enters PAN (+ DOB if the vendor needs it) and ticks consent
    → POST /identity/pan/verify
        1. format check  ^[A-Z]{5}[0-9]{4}[A-Z]$, 4th char 'P' for individuals
        2. rate-limit (per user + per IP) — each call costs money
        3. compute pan_lookup_hash (existing crypto.py)
             ├─ hash on THIS user's member   → already verified, return cached result (no vendor call)
             ├─ hash on ANOTHER account      → collision → return generic "needs ownership proof"
             │                                  → offer DigiLocker flow (Route C)
             └─ no hash                      → call vendor
        4. vendor: PanVerificationProvider.verify(pan, dob, consent, reason)
        5. valid → encrypt + hash onto the SELF household member, set name if empty,
                   write pan_verifications row + consent_records row
           invalid/deleted/fake → 422 with a clear message, no PAN persisted
    → UI shows masked PAN + returned name ("Is this you?")
       user confirms → onboarding continues to CAS upload

Collision / ownership proof (Route C):
  GET  /identity/digilocker/start    → vendor-created request, redirect URL
  GET  /identity/digilocker/callback → fetch PAN doc, compare hash, mark verified_owner
```

Later CAS imports then hit attribution step 1 ("PAN matches own household") directly. The
existing flow needs no changes.

### 4.2 Backend changes

| Area | Change |
|---|---|
| New module `backend/app/services/identity/` | `pan_verification.py`: a `PanVerificationProvider` protocol with vendor adapters (same pattern as `import_/file_storage.py`'s swappable storage interface), plus a `StubProvider` for dev/tests, mirroring the OTP `stub` mode. `digilocker.py` holds Route C. |
| Vendor HTTP client | `httpx.AsyncClient` with a timeout (~5s), 1 retry on 5xx only, **redaction of PAN/DOB in logs**, idempotency via our own `request_id`. Vendor outages degrade gracefully: let the user skip and verify later (don't block onboarding). |
| API router `backend/app/api/identity.py` | `POST /identity/pan/verify`, `GET /identity/pan/status`, plus the DigiLocker start/callback endpoints. Every DB commit goes through `commit_off_loop` (per the bb5225f convention). |
| Onboarding | New `onboarding_step` value, a frontend step component next to `TrustPrimer.tsx`, and TrustPrimer copy covering *why* we ask for PAN. |
| Config | `PAN_VERIFY_PROVIDER` (`stub`/`<vendor>`), `PAN_VERIFY_API_KEY`, `PAN_VERIFY_REQUIRED` (bool), plus the same startup guard the PAN keys use (refuse to boot outside dev if unset). |
| Tests | Stub-provider tests for every branch in §4.1, a redaction test (no PAN in captured logs), and an extension of `tests/models/test_no_pan_field.py` so the new tables pass the no-plaintext-PAN guard. |

### 4.3 Database migration (0016)

```
household_members (add)
  pan_verification_status   enum: unverified | verified_exists | verified_owner | failed
  pan_verified_at           timestamptz
  pan_name_as_per_itd       string         -- vendor-returned name; plain text (a name alone is low-sensitivity)
  aadhaar_seeding_status    enum: y | n | na  (nullable)

pan_verifications (new — audit + cost control; NO plaintext PAN)
  id, user_id, household_member_id (nullable), pan_lookup_hash,
  provider, provider_request_id, route (api|digilocker),
  result_status, name_match (bool, nullable), dob_match (bool, nullable),
  http_status, latency_ms, cost_paise (nullable), created_at

consent_records (new — DPDP evidence)
  id, user_id, purpose (pan_verification|cas_processing|...), notice_version,
  granted_at, withdrawn_at (nullable), ip, user_agent
```

Account deletion must cascade-wipe `pan_encrypted`/`pan_lookup_hash`. Keep `pan_verifications`
rows only as long as the privacy policy says, and null out their hash on deletion.

### 4.4 AWS infra (on top of what exists)

| Need | Change | Cost |
|---|---|---|
| Vendor API key | A new Secrets Manager secret (or a key added to the `pan_keys` JSON), encrypted with the existing CMK, and added to the ECS task-definition `secrets` block plus the `ecs_secrets_read` policy | $0.40/mo per secret |
| Outbound HTTPS to vendor | Already covered. ECS egress goes through fck-nat. If the vendor asks us to allow-list our IP, that's the fck-nat Elastic IP (stable). | ~$0 |
| Monitoring | A CloudWatch metric filter plus alarm on vendor error rate and latency; optionally a daily-spend metric from `pan_verifications.cost_paise` | cents/mo |
| Abuse control | App-level rate limiting is enough at this scale. AWS WAF on the ALB is optional later (~$5/mo + $1/rule). | $0 now |
| No new services | No new RDS, S3, KMS or queues. The call is synchronous and fast. | — |

### 4.5 Pricing summary

| Item | Unit cost | At 1,000 users (~1.5 PANs each incl. family) |
|---|---|---|
| PAN verify with name (Route B, e.g. Eko) | from ₹1.20 + GST | ~₹2,000 one-time |
| Same, pricier vendor tier | ~₹3–5 | ~₹4,500–7,500 |
| DigiLocker pull (Route C, only on collisions, maybe 1–3%) | from ₹2.50 | < ₹100 |
| AWS delta | — | ~$0.40–1/mo |
| Direct Protean OPV | ₹12,000/yr + GST | not eligible anyway |

Unit prices come from vendors' public pages as of 2026-09-23. Get written quotes: most vendors
negotiate, add GST, and some require prepaid wallets or minimums. Re-verifying an already-hashed
PAN costs ₹0 thanks to the step-3 cache.

### 4.6 Vendor selection checklist
1. Name-return **data source and legal basis** in writing **[counsel]**.
2. DPA / data-processing terms: no retention of our requests beyond what's necessary, and
   Indian data residency.
3. SLA, sandbox, idempotency, latency (p95 < 2s).
4. Minimal-field endpoint available, with no forced "advanced" payload.
5. The same vendor covers DigiLocker (Route C), for one integration and one contract.

---

## 5. Decisions needed from you

1. Reverse PRD-02's "no KYC/identity verification" non-goal and update
   `DEFERRED_FEATURES.md` line 34? (Also fix `decisions.md`, which still states the pre-09-18
   no-PAN rule.)
2. PAN at signup: **required** or **optional/skippable**? Required improves data quality but
   adds signup drop-off, and a vendor outage then blocks signups unless there's a skip-and-retry
   path.
3. Name-returning (Route B) vs flags-only (Route A, where the user must type name + DOB)?
4. Collision handling: DigiLocker ownership proof, MF Central proof, or support-only?
5. Enumeration tradeoff on "PAN already registered" messaging (§1.3).
6. Get counsel review of: the scorer's advice exposure, vendor name-source legality, the
   privacy policy and consent text.

---

## Sources

- Protean OPV overview (eligible entities, returned fields): https://tinpan.proteantech.in/services/online-pan-verification/pan-verification-overview.html
- Protean OPV registration and fee (₹12,000 p.a.): https://tinpan.proteantech.in/services/online-pan-verification/pan-verification-register.html
- Protean PAN OPV: https://www.proteantech.in/services/pan-opv/
- Sandbox.co.in Verify PAN Details API (flags only, consent + reason required): https://developer.sandbox.co.in/api-reference/kyc/pan/endpoints/verify_pan_details
- Cashfree PAN verification (registered_name, nameMatchScore): https://www.cashfree.com/docs/secure-id/kyc-stack/verify-pan
- Eko PAN verification (₹1.20, returns name, business KYC for prod keys): https://eps.eko.in/products/pan-verification-api
- Eko DigiLocker API (from ₹2.50): https://eps.eko.in/products/digilocker-api
- Setu DigiLocker integration guide: https://docs.setu.co/data/digilocker/quickstart
- API Setu DigiLocker: https://apisetu.gov.in/digilocker
- BeFiSc PAN verification compliance guide: https://www.befisc.com/fintechsherlock/pan-verification-api-guide-india/
- SEBI EOP registration (BusinessToday): https://www.businesstoday.in/personal-finance/investment/story/sebi-mandates-registration-for-execution-only-platform-providers-offering-mutual-fund-schemes-385523-2023-06-14
- SEBI EOP deposit (Business Standard): https://www.business-standard.com/markets/mutual-fund/market-regulator-sebi-sets-deposit-requirement-for-execution-only-platforms-123100601157_1.html
- SEBI IA Regulations FAQ: https://www.sebi.gov.in/sebi_data/attachdocs/1424862077270.pdf
- DPDP Rules 2025 (PIB): https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf
- DPDP timeline (Shardul Amarchand Mangaldas): https://www.amsshardul.com/insight/enforcement-of-the-dpdp-act-and-notification-of-the-dpdp-rules/
