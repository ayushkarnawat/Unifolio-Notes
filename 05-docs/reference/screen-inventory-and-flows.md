# Reference: Screen Inventory and Flows

The S-numbered inventory below is from `App-Flow-Unifolio.md` v1.2. **A second, newer
app-flow document (`Updated-CAS-App-Flow.md`) describes the CAS import portion
differently and the two are not reconciled** — see the note at the end and
[`07-risks-and-debt.md`](../../07-risks-and-debt.md).

## Screens

| ID | Screen | Module | Reached from |
|---|---|---|---|
| S23 | Landing — Sign Up / Log In | Onboarding | App launch with no session. **The true first screen**; both buttons lead to S0 |
| S0 | Phone entry | Onboarding | S23 |
| S1 | OTP verify | Onboarding | S0 |
| S2 | Trust primer | Onboarding | S1, first login only |
| S3 | Q1 — Name | Onboarding | S2; revisitable via back-nav |
| S4 | Q2 — Investing behaviour | Onboarding | S3; skippable and revisitable |
| S5 | Q3 — Purpose | Onboarding | S4; skippable and revisitable |
| S6 | Q4 — Household | Onboarding | S5 |
| S7 | Add family member(s) | Onboarding | S6, if "Family too" |
| S24 | Family CAS upload | Import / Onboarding | S7 — one independent upload card per member added at S7 |
| S25 | Upload my CAS? Now / Later | Onboarding | S24, once every member's card is uploaded or explicitly skipped |
| S26 | Parse queue | Import / Onboarding | S25 ("Later"), or after a queued upload completes. Lists every queued-but-unparsed file with a single "Parse Files" action |
| S8 | CAS upload | Import | S6 ("Just me"), S25 ("Now"), or S16 (ongoing) |
| S9 | Import parsing (loading) | Import | S8 |
| S10 | Import review | Import | S9 on success |
| S11 | Import error | Import | S9 on failure — wrong password / scanned / wrong CAS type / generic |
| S12 | Import confirmed (payoff) | Import | S10 on confirm |
| S14 | Main dashboard — family aggregate | Dashboard | S12. **Default landing** for returning users who have family members |
| S13 | Main dashboard — per-member | Dashboard | Switch from S14; **also the default** for users with no family members |
| S15 | Fund detail | Dashboard | Tap a holding on S13/S14 |
| S17 | Distributor comparison | Dashboard | S15 only, when a scheme has multiple ARNs |
| S16 | Add data — re-entry to import | Dashboard | S13/S14 nav; routes to S8 |
| S18 | Analytics — per-member | Analytics | Nav from S13 |
| S19 | Analytics — family aggregate | Analytics | Nav from S14 |
| S20 | Fund score detail | Analytics | Tap a fund's score on S18/S19 |
| S21 | Empty state — no holdings yet | Dashboard | Instead of S13/S14 if no import has completed |
| S22 | Family member placeholder | Dashboard | Within S14, per member with no CAS yet |
| — | `ImportPathChoice` | Import | Choose between requesting a CAS by email and uploading one. Specified 2026-08-19, mirrors the existing household question screen; no execution record |
| — | CAS import "waiting" screen | Import | Shown after a statement has been requested by email. Exists in code and is **currently unreachable** — see INV-007 |
| — | `MobileOnboardingScreen` | Onboarding | Full-screen mobile onboarding shell. Specified 2026-08-20; element order fixed as top bar → headline → illustration → subtext → content → CTA, no eyebrow |
| — | `DematImportFlow` / `DematReviewTable` | Import | Upload and review a depository statement. Planned 2026-08-26, not built. Sibling to the mutual-fund import flow, reusing `UploadForm` |
| — | `EquityHoldingsTable` | Dashboard | Member-level equity holdings. Planned 2026-08-26, not built. Shows "Cost basis unavailable" rather than a fabricated number |
| — | `PrintAnalyticsView` | Analytics | Print-only analytics rendering at `/print/analytics`. Planned 2026-08-20, not built. Mounted directly by `main.tsx`, bypassing the app shell and auth provider |
| — | `DashboardPlaceholder` | Dashboard | The desktop Main Dashboard. **Still a stub** as of 2026-08-19 while the mobile equivalent is mature (R-037) |

*Rows with no `S` number are screens named in this batch's plans and specs, not in the original `App-Flow-Unifolio.md` inventory; they carry no ID in that numbering scheme.*

## The three structural decisions inside that table

**The queue, not the upload, is the unit of work during family onboarding.** S24 gives
each member an independent upload card; files accumulate; S26 parses them in one
deliberate action. Someone setting up four family members is not made to sit through
four sequential parse spinners.

**Skips are genuinely revisitable.** S4 and S5 can be skipped and returned to later — a
stated requirement (PRD-02 FR-7a), not an implementation nicety. A skipped question that
cannot be answered later is a dead end.

**S17 is reachable only from S15.** Distributor comparison is a drill-down from a fund's
detail, never a top-level destination — it only means anything in the context of one
scheme held through multiple distributors.

## Import flow, current generation

The state machine in
[`06-architecture/runtime-and-data-flow.md`](../../06-architecture/runtime-and-data-flow.md)
is authoritative for import behaviour. In summary: a modal Import CAS panel with Request
and Upload tabs, a pending "requested from CAMS" state that expires after 7 days, a
password retry that does **not** require re-uploading the file, a named
Summary-vs-Detailed validation error, and an attribution step assigning the import to a
household member.

## Import flow — the 2026-08-19 correction (specified, not implemented)

The current generation derives which screen the user sees from two independent
pieces of state: a pending-import identifier and a three-way tab selection.
Requesting a statement by email sets the first and moves the second, which
makes the waiting screen's condition unsatisfiable at the only moment it should
be true — the user lands on the plain upload form instead. See INV-007.

The specified correction replaces the three-way tab state with a single
explicit view state covering choice, request, waiting, upload and history. The
existing per-member resume check is unaffected.

Two related findings from the same document: the "Step 1 / Step 2" framing in
the current UI is a mislabel, and `CoverageGapBanner` is still on an older
visual system.

## Unreconciled

`App-Flow-Unifolio.md` v1.2 describes S24/S25/S26 — a queue built into the onboarding
screen sequence. `Updated-CAS-App-Flow.md` describes a modal Import CAS panel with
Request/Upload tabs and an attribution dialog. They cover the same feature one generation
apart and have not been merged. Both are preserved. Do not treat either as settled until
someone decides.

- **`MobileFundDetailView` and `MobileFundDetailSheet` render the same thing.**
  Raised on 2026-08-19 as a product decision for a human rather than resolved
  in passing. See R-036.
- **`OnboardingIllustration`'s `"upload"` variant** was built for the import
  flow and is not used anywhere; `AddFamilyMembers` uses the `household`
  variant while an unused `family` variant exists. See R-034.
- **No mobile-specific onboarding views existed** as of 2026-08-18, and auth
  and onboarding are purely shared responsive components with no mobile tree
  (2026-08-19, §4.3).

## Related

- [Runtime and data flow](../../06-architecture/runtime-and-data-flow.md)
- [Design tokens](design-tokens.md)
