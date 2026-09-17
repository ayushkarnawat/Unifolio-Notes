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

## Unreconciled

`App-Flow-Unifolio.md` v1.2 describes S24/S25/S26 — a queue built into the onboarding
screen sequence. `Updated-CAS-App-Flow.md` describes a modal Import CAS panel with
Request/Upload tabs and an attribution dialog. They cover the same feature one generation
apart and have not been merged. Both are preserved. Do not treat either as settled until
someone decides.

## Related

- [Runtime and data flow](../../06-architecture/runtime-and-data-flow.md)
- [Design tokens](design-tokens.md)
