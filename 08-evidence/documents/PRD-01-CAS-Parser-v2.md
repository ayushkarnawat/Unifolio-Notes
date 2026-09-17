---
artifact: prd
version: "1.4"
created: 2026-07-22
updated: 2026-08-05
status: draft
product: Unifolio
module: MF Import (CAS Parser v2)
---

# PRD: CAS Parser v2 (Mutual Fund Import — Tighten & Extend)

## Overview

### Problem Statement

MFCentral's third-party CAS API was shut down by SEBI/AMFI in September 2025, stranding
100+ fintechs (including MProfit and Investwell) that relied on it. This makes CAS-PDF
parsing — not a bulk API — the industry-standard MF import mechanism today, and it's the
approach Unifolio has already built (backend scaffold, `calc.py` Decimal math, SQLAlchemy
models, `casparser` wrapper, `mfapi.in` enrichment, and two-phase parse/confirm API routes
are all complete; only the frontend UI and README remain).

This PRD does **not** propose a rebuild. The parser works. This is a **tightening and
extension pass**: closing accuracy gaps, adding two new data-capture requirements
surfaced in product planning (direct-vs-regular plan detection, ARN/AMFI code capture for
future distributor analytics), and hardening the review-before-commit flow that is Unifolio's
stated differentiator against Mprofit's "import silently, users discover errors later" pattern.

### Solution Summary

Extend the existing CAS parsing pipeline (CAMS + KFintech, via `casparser`) to: (1) reach
production-grade parsing reliability across both CAS formats, (2) classify every holding as
Direct or Regular plan, (3) capture ARN/broker code per folio at parse time (storage only —
distributor analytics itself is a separate, future PRD), (4) finish the confidence-scored
Import Review screen, and (5) close out the remaining test coverage and error-message
gaps identified in the original build spec.

### Target Users

Retail DIY investors and (later) advisors/family-account holders uploading their own CAMS
or KFintech Consolidated Account Statement to import mutual fund holdings into Unifolio.
No auth in this build phase — single implicit portfolio per the current prototype scope.

## Goals & Success Metrics

### Goals

1. Parse CAMS and KFintech Detailed CAS PDFs into a clean, deduped transaction ledger
   with zero silent data loss (every unparseable line surfaces to the user, none dropped).
2. Correctly classify every scheme as Direct or Regular plan, and capture ARN/broker
   code where present, without slowing down the import flow.
3. Give the user full visibility and control before anything is committed to their
   portfolio — no auto-save on low-confidence matches.

### Success Metrics

| Metric | Current Baseline | Target | Timeline |
|--------|-------------------|--------|----------|
| CAS parse success rate (CAMS + KFintech, valid Detailed CAS) | Not yet measured | ≥98% of uploaded files parse without a fatal error | Before MVP close |
| AMFI scheme-match confidence ≥0.98 (auto-accepted) | Not yet measured | ≥90% of schemes | Before MVP close |
| Direct/Regular classification accuracy | Not built | ≥99% on schemes where CAS data includes broker/ARN field | Before MVP close |
| XIRR / FIFO known-answer test pass rate | Passing (existing fixtures) | 100% (no regressions on tightening pass) | Ongoing |
| Duplicate transactions on re-upload | Not yet measured | 0 (dedupe key working) | Before MVP close |

### Non-Goals

- This PRD does not cover MFCentral OTP/API import or Account Aggregator import — both
  remain gated behind the AMFI ARN / SEBI registration path and are tracked separately.
- This PRD does not cover distributor/ARN performance *analytics* — only the data capture
  needed so that feature isn't blocked later. Analytics itself belongs to the MF Analytics
  Dashboard PRD.
- NSDL/CDSL demat CAS parsing remains explicitly out of v1 scope (equity holdings via CAS
  are not covered here — see the future CDSL Easi/Easiest research note in the competitive
  analysis for a possible Phase 2 path).

## User Stories

| ID | User Story | Priority |
|----|-----------|----------|
| US-1 | As an investor, I want to upload my CAS PDF and password so my holdings import without me re-entering data | P0 |
| US-2 | As an investor, I want to see exactly what was parsed — schemes, folios, transaction counts — before anything is saved, so I can catch errors early | P0 |
| US-3 | As an investor, I want low-confidence AMFI scheme matches flagged and fixable, not silently guessed | P0 |
| US-4 | As an investor, I want to know which of my holdings are Direct plans vs Regular plans so I understand where I'm paying distribution commission | P0 |
| US-5 | As an investor, I want to re-upload an updated CAS without ending up with duplicate transactions | P0 |
| US-6 | As an investor, I want a clear, specific error message when my CAS is the wrong type (Summary vs Detailed) or has the wrong password, not a generic failure | P1 |
| US-7 | As a future distributor-analytics feature, I want ARN/broker code captured per folio at import time, even though it isn't displayed yet | P2 |

See the companion user-stories/acceptance-criteria doc for full Given/When/Then coverage
once this PRD is approved.

## Scope

### In Scope

- Tightening `parser.py`: full CAMS + KFintech layout coverage via `casparser`, transaction
  type normalization (existing enum), raw parser JSON retained for debugging.
- **New:** Direct vs Regular plan classification per scheme (see Functional Requirements).
- **New:** ARN/broker code capture per folio into the data model (storage only, no UI yet).
- Finishing the Import Review screen (frontend) — confidence badges, manual AMFI-match
  override, confirm/cancel.
- **New:** Ongoing import as a first-class capability, not an onboarding-only step —
  a user (or a family member) can trigger a new CAS import at any time after initial
  setup, from the Main Dashboard (see PRD-03's addendum), reusing this same parse/
  confirm/dedupe flow. This isn't new parsing logic — FR-9's dedupe key already handles
  re-upload correctly — it's a scope clarification that import is a recurring action, not a
  one-time onboarding gate, and the API/UI should be built assuming repeat use from day
  one rather than retrofitted later.
- Error classification pass: wrong password, Summary-CAS-instead-of-Detailed,
  scanned/image PDF, generic casparser failure — each with a specific, human message.
- Dedupe verification on re-upload (folio + scheme + date + amount + units key).
- Closing out remaining pytest coverage: parser normalization tests against a real CAS
  fixture (CAMS at minimum; KFintech if a sample becomes available).
- README with setup and CAS-request instructions (Phase 6 of the original build spec).

### Out of Scope

- MFCentral OTP/API import, Account Aggregator import.
- Distributor/ARN performance analytics UI.
- NSDL/CDSL demat statement parsing (equity holdings).
- Multi-user auth (single implicit portfolio remains the prototype model).

### Future Considerations

- MFCentral API via AMFI ARN partner — deferred until the partner relationship is live
  (timeline unconfirmed; flagged as an open question below).
- Distributor analytics dashboard (uses the ARN data captured here) — separate PRD.
- CDSL Easi/Easiest-based equity import, following the Passbook Family precedent — Phase 2.

## Solution Design

### Functional Requirements

#### Parsing & Normalization
- FR-1: Parse CAMS and KFintech Detailed CAS PDFs via `casparser`; reject Summary CAS
  with a specific message directing the user to request a Detailed CAS.
- FR-2: Extract investor info (name, email, PAN — masked as `ABCDE****F` in all UI and
  logs), folios, schemes (ISIN + AMFI code where present), and every transaction with
  type, date, amount, units, NAV. **PAN is never persisted** — used transiently in memory
  during the active parse/review session for masked display only, then discarded exactly
  like the source PDF (confirmed, see Database Schema's Data Classification section —
  no PAN column exists anywhere in the schema).
- FR-3: Map `casparser` transaction types to the existing canonical enum (`PURCHASE`,
  `PURCHASE_SIP`, `REDEMPTION`, `SWITCH_IN/OUT`, `DIVIDEND_PAYOUT/REINVEST`,
  `SEGREGATION`, `STT`, `STAMP_DUTY`, `MISC` catch-all preserving original description).
- FR-4: Store full raw parser output as JSON on the import record for debugging.

#### Direct vs Regular Classification (new)
- FR-5: For each scheme, classify as Direct or Regular using: (a) scheme name pattern
  match (`"- Direct"` / `"-Direct Plan"` suffix conventions used by AMCs) as primary signal,
  and (b) presence of a non-empty broker/ARN code on the folio as a corroborating signal
  for Regular. Where the two signals disagree, flag as `unclassified` and surface for user
  confirmation — never silently guess, consistent with the AMFI-match confidence pattern
  already in use for scheme resolution.
- FR-6: Persist the classification (`direct` / `regular` / `unclassified`) per scheme-folio on
  the import record so it's available to the dashboard without recomputation.

#### ARN / Broker Code Capture (new)
- FR-7: Capture the broker/ARN code from `casparser` folio output (where present) into the
  data model at parse time. No UI surfacing in this PRD — this is enablement for the future
  distributor-analytics feature.
- FR-8: Where multiple ARN codes appear across folios for the same scheme (e.g., bought
  through two distributors), preserve each folio's ARN separately rather than collapsing to
  one value — this is required for the future "which distributor performs better" analytics.

#### Review & Confirm Flow
- FR-9: `/api/imports/parse` returns a preview (no DB writes) with scheme-level confidence
  scores for AMFI matches and direct/regular classification. Called once per file — per
  PRD-02 v1.3's Family CAS Upload flow, a batch "Parse Files" action on the frontend calls
  this endpoint once per queued file, sequentially, each tagged to its own
  `household_member_id`; this endpoint itself has no batch/multi-file mode (added v1.3
  cross-reference).
- FR-10: User must confirm before `/api/imports/confirm` persists anything. Low-confidence
  AMFI matches (<0.92) and `unclassified` direct/regular results block silent confirm —
  each requires an explicit user choice.
- FR-11: `/api/imports/confirm` reports `"N new, M duplicates skipped"` on every import.

#### Error Handling
- FR-12: Wrong password → "Incorrect PDF password. CAMS/KFintech CAS passwords are
  usually your PAN in uppercase."
- FR-13: Scanned/image-only PDF → "PDF appears scanned or unreadable. Download the
  original email PDF, not a photo/scan."
- FR-14: Generic `casparser` exception → pass through a sanitized message, never a raw
  stack trace.

### User Experience

Two-phase flow (already the core differentiator vs. Mprofit's silent import): Upload →
parse preview → Import Review (confidence badges, direct/regular tags, manual override
dropdowns) → Confirm → Dashboard. Direct/regular status should render as a simple
badge next to each scheme in the review table, not a separate step — keep it inline with
the existing confidence-badge pattern rather than adding new UI surface area.

### Edge Cases

| Scenario | Expected Behavior |
|----------|--------------------|
| CAS contains both CAMS and KFintech-sourced folios (rare but possible) | Parse both correctly via `casparser`'s built-in handling; no special-casing needed |
| Scheme name has no `"-Direct"` suffix and folio has no ARN | Classify `unclassified`, require user confirmation |
| Same scheme held via two different distributors (two ARNs) | Both folios imported and tagged separately, not merged |
| Re-upload of an overlapping CAS after a Direct/Regular reclassification fix | Dedupe key unaffected (folio+scheme+date+amount+units) — reclassification doesn't create duplicate transactions |
| CAS password is correct but file is a Summary CAS | Specific error directing to Statements → CAS → Detailed on camsonline.com |
| NSDL/CDSL demat CAS uploaded by mistake | Clear message: equity/demat statements aren't supported in this version |

## Technical Considerations

### Constraints
- Money math: `Decimal` everywhere, never `float` — units to 3 decimals, amounts to 2,
  NAV to 4. Already enforced; no regression allowed in this tightening pass.
- SQLite (prototype) with `Numeric` column types (Postgres-portable) — no schema change
  required for direct/regular and ARN capture beyond adding the new columns.
- Fuzzy scheme matching stays on stdlib `difflib.SequenceMatcher` — no new dependency.

### Integration Points
- `casparser` (open-source, MIT) — existing dependency, no version change proposed here
  unless a specific parsing gap requires it (flag as an open question if found).
- `mfapi.in` — NAV and scheme-list enrichment, existing 24h disk cache.

### Data Requirements
- New columns/fields needed on the scheme-folio record: `plan_type`
  (`direct`/`regular`/`unclassified`), `arn_code` (nullable string, per folio).
- PAN never logged; PDF password never stored; uploaded PDF deleted in a `finally` block
  — all existing constraints, restated here because they apply directly to this extension.

## Dependencies & Risks

### Dependencies

| Dependency | Owner | Status | Impact if Delayed |
|------------|-------|--------|--------------------|
| Real CAMS Detailed CAS test fixture | Ayush | Requested, not yet confirmed in hand | Parser tests stay synthetic-fixture-only; real-world edge cases (formatting drift, non-standard scheme naming) go untested |
| KFintech-flavored CAS fixture | Ayush | Not yet requested | Direct/regular and ARN-capture logic untested against KFintech's specific field layout |
| AMFI scheme-name suffix conventions for Direct-plan detection | Needs verification | Assumed `"- Direct"` / `"-Direct Plan"` patterns; not yet validated against a real multi-AMC CAS | Classification accuracy target may not be reachable without real data |

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| "100% accuracy" target (stated in product planning) isn't achievable for fuzzy AMFI matching or Direct/Regular classification in every edge case | High | Medium | Redefine "100%" as: 100% *surfaced* (nothing silently wrong) rather than 100% *auto-correct* — flagged as an open question below, needs your sign-off on the distinction |
| KFintech CAS field layout differs enough from CAMS that Direct/Regular or ARN capture logic silently fails on one format | Medium | Medium | Test against both formats before calling this done; if a KFintech fixture isn't available, ship CAMS-verified and flag KFintech as best-effort until a fixture arrives |
| Scheme names without a reliable Direct/Regular naming convention (some AMCs are inconsistent) | Medium | Low | `unclassified` fallback with user confirmation, per FR-5, prevents silent misclassification |

## Timeline & Milestones

| Milestone | Description | Target Date |
|-----------|--------------|--------------|
| Direct/Regular + ARN capture logic | FR-5 through FR-8 implemented and unit-tested | TBD — pending fixture availability |
| Import Review UI complete | Confidence badges + direct/regular badges + manual override | TBD |
| Error-message pass complete | FR-12–14 verified against real failure cases | TBD |
| README + fixture docs | Phase 6 of original build spec | TBD |
| MVP close for this module | All Success Metrics met or explicitly deferred with reason | Per August build-out window |

## Open Questions

- [ ] What does "100% accuracy" mean precisely for the analytics/parsing requirement —
      100% of parseable data surfaced correctly, or 100% auto-classification with zero
      user review? These have very different engineering implications. — Owner: Ayush
- [ ] Do we have (or can we get) a real KFintech-flavored CAS to test against, or is CAMS
      the only format we can validate before launch? — Owner: Ayush
- [ ] Is the `"- Direct"` naming-suffix assumption for plan classification reliable across all
      AMCs, or does this need a maintained lookup table instead of pattern matching? —
      Owner: Claude (research), confirm with Ayush before implementation
- [ ] Should `unclassified` Direct/Regular results block dashboard display of that holding
      entirely, or show with a visible "unverified" tag? — Owner: Ayush

## Appendix

### Update — 2026-07-22

The open question below on ARN/broker-code capture has been resolved (research and
full technical approach now live in PRD-03: Main Dashboard, FR-11–FR-11c). Summary:
AMFI publicly maintains a "Locate a Mutual Fund Distributor" lookup that resolves an
ARN code to a registered distributor name/status on demand — the distributor
comparison feature this data enables doesn't need that lookup to function (it runs on the
raw ARN code alone), so name resolution is an enrichment, not a blocker. No change to
this PRD's FR-7/FR-8 (ARN capture) — they were already correctly scoped as
storage-only. This note is left here rather than editing FR-7/FR-8 or the Open Questions
list below, since the original requirements were accurate as written.

### Related Documents
- `MF_CAS_Parsers.md` (project knowledge) — original build spec and current build-status
  tracker (scaffold/calc/models/enrich/API complete; frontend in progress; README pending)
- Combined Feature-Parity Matrix (project knowledge) — competitive context for import UX
  as a stated differentiator
- Product Context — Wealth Management Platform (project knowledge) — module status and
  team/timeline context

### Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-07-22 | Claude (PM partner) | Initial draft |
| 1.1 | 2026-07-22 | Claude (PM partner) | Added Update note resolving ARN-to-distributor data-source question (see Appendix) |
| 1.2 | 2026-07-22 | Claude (PM partner) | Added Ongoing Data Addition as an explicit v1 scope item (import is recurring, not onboarding-only); noted in ADR-004 that PDF retention (vs. current delete-after-parse) is now an open decision pending Ayush's call, not yet changed |
| 1.3 | 2026-07-22 | Claude (PM partner) | FR-2 clarified: PAN confirmed never persisted (transient use only), resolved via Database Schema's open question |
| 1.4 | 2026-08-05 | Claude (PM partner), from team brainstorm relayed by Ayush | FR-9 cross-referenced to PRD-02 v1.3's Family CAS Upload batch-parse flow: this endpoint is still called once per file, sequentially, tagged per `household_member_id` — no batch/multi-file mode added here, the queueing/sequencing lives entirely in the frontend per PRD-02 |
