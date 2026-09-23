# A 22-item internal correction plan for Analytics is cross-referenced against real code, then triaged item by item

## For stakeholders

A separate, uncommitted internal document had listed 22 possible
correctness and hardening gaps across the Analytics dashboard (category
returns displaying with the wrong scale, a benchmark comparison that
silently drops unresolved cash flows, mixed-plan-type holdings merging
into one row, and 19 others). Each one was checked against the actual
code — not assumed — and given a confidence rating for how thoroughly it
was checked. The product owner then decided, item by item, what to fix
immediately, what to fix in a lighter form, what to explicitly reject, and
what to defer with a written reason and a revisit trigger, rather than
leaving a vague backlog. Four items were fixed the same day; one item (a
benchmark index missing a "distributions included or not" disclosure) got
an honest label fix now with the real, harder fix written up and shelved
until a data-sourcing question is answered; and one item was flagged as a
direct conflict with an already-made product decision and resolved in the
existing decision's favor.

## Technical detail

### Intended outcome

Cross-reference every one of the correction plan's 22 requirements
(P0.1-P0.4, P1.1-P1.10, P2.1-P2.8) against the live codebase as of
2026-08-19, then obtain an explicit, item-by-item product disposition
rather than treating "found a gap" as "must fix now."

### What actually happened

The cross-reference itself was adversarially reviewed (a Codex pass found
8 findings — 1 High overclaim on P0.3, 5 Medium including a wrong exact
number in one item's example and three VERIFIED labels that didn't match
the investigation actually performed, 2 Low) and corrected before being
used as the basis for any decision.

Of the 22 items, 4 confirmed bugs with no product-decision dependency were
implemented the same day, round 2, TDD throughout, one review round
(1 Medium + 1 Low finding, both fixed, scoped re-review APPROVE,
zero findings, full suite 418 passed/2 skipped):

- **P0.2 — category CAGR displaying at 1/100th scale** (`"0.12%"` instead
  of `"12.00%"`), fixed at the frontend display boundary using the same
  exact-decimal-string `toPercentString` helper already established for
  the earlier XIRR fix, not by changing the backend's raw-fraction wire
  format.
- **P1.10 — mixed plan types silently merging into one holdings row.**
  `compute_holdings` grouped by `(household_member_id, scheme_id)` only,
  so a member holding the same scheme via both a Direct and a Regular
  folio got one row with an arbitrary plan-type label but units/cost
  summed across both. Fixed by widening the grouping key to include
  `plan_type`, plus a matching React-key fix in `HoldingsTable.tsx`.
- **P1.6 — switch transactions invisible to fund-level XIRR.** Correctly
  excluded at the portfolio level (no cash enters/leaves the household),
  but the same exclusion set was reused, incorrectly, for each fund's own
  XIRR — a switch-out/switch-in should appear as a signed flow for the
  affected funds. Fixed via a new `extra_debit_types` parameter threaded
  through the shared XIRR helpers (default empty, so every other caller's
  behavior is unchanged) and a wider `_fund_level_transactions` query used
  only for the per-fund calculation.
- **P2.4 — Scorer's `final_score` unclamped.** A worst-percentile fund with
  the maximum negative TER cost-adjustment could land at exactly `-0.25`,
  outside the documented `[0, 100]` range (and a top fund with a positive
  adjustment could exceed 100). Clamped after the existing quantize.

**P0.3 — TRI (Total Return Index) vs. price-only benchmark** got a fifth,
lighter fix in the same round rather than the full sourcing fix: NSE's
index names carry no TRI designation and nothing in the codebase confirms
whether the values actually returned are price-only or total-return, so
the benchmark comparison could be silently misleading users into treating
it as apples-to-apples against their own (distribution-inclusive) fund
XIRR. Rather than sourcing a new data feed on a speculative basis, the
same-day fix is disclosure-only: each benchmark index label in
`BenchmarkSection.tsx` now reads e.g. "Nifty 50 (Price Return)". The full
fix — confirming a TRI series is reachable through NSE's existing
undocumented endpoint or requires a paid source, then verifying the
economic content of what's actually returned, then a schema change so the
label becomes response-driven instead of hardcoded — is written up as a
5-step future-implementation guide with an explicit revisit trigger (the
product owner decides TRI comparability is worth a paid source, or a
free/licensed feed is identified independently), not time-boxed
otherwise.

**P1.4 — minimum eligible peer count** surfaced a direct conflict, not a
gap: the correction plan asked for hard suppression (don't publish
scores/percentiles below 5 eligible peers), but the codebase already
implements a soft "still shown, flagged" behavior
(`thin_category=True`) per an existing, already-documented PRD "Edge
Cases table" decision. Flagged rather than resolved unilaterally, per
CLAUDE.md's "when a PRD seems to conflict with what you're about to
build, stop and say so" instruction. **Decision: keep the existing
soft-flag behavior; the correction plan's hard-suppression ask is
rejected** — hiding data below 5 peers would harm real, common cases
(niche sectoral/international funds), not just hypothetical ones.

The remaining 16 items were each given an explicit disposition rather than
left untriaged: 2 already satisfied by existing code (P1.2, P2.8), 2
resolved as standing product/governance decisions (P1.3's methodology doc
treated as signed off; P0.4's graceful-degrade-over-hard-fail pattern kept
as-is), 1 skipped as solving a practically nonexistent problem (P1.5's
tie-aware ranking — real Decimal-precision CAGR values essentially never
tie), and 11 explicitly deferred with a named reason and revisit trigger
each (P1.1 AAUM scheduler — gated on the AWS-deployment readiness
checklist; P1.7 non-equity benchmark families and P1.8 valuation-date
alignment and P1.9's broader identity-matching scope and P2.1/P2.2/P2.3/
P2.5/P2.7 — production-operations maturity or net-new data sourcing, not
MVP-blocking correctness bugs).

### Deviation (if any) — decision or response taken

The cross-reference document's own initial "Recommendation" section
(implement only P0.2/P2.4 now, escalate everything else) was superseded
by a fuller "Final Decision" table reached with the product owner the same
day — P1.10 and P1.6 moved from "not scoped yet" to "implemented this
round" once discussed. The Final Decision table is authoritative over the
earlier recommendation where they differ.

### Result

4 confirmed bugs fixed and re-reviewed clean; 1 item partially addressed
(honest labeling now, full fix deferred with a written path); 1 direct
PRD-conflict resolved in the existing decision's favor; 1 item skipped as
non-applicable; 2 items confirmed already satisfied; 13 items explicitly
deferred, each with a stated reason and revisit trigger rather than left
as an untriaged backlog.

### Related

- ADR-010 — fund scorer composite formula (P1.3, P1.4, P2.4 all touch the Scorer)
- ADR-013 — analytics PDF export architecture (a sibling analytics-hardening track, same period)
- R-060 — see also the dashboard cache-hardening stage the same week
- "Deferred by decision" list in [07-risks-and-debt.md](../07-risks-and-debt.md) — full TRI benchmark sourcing entry added from this stage
- Evidence: `08-evidence/documents/orchestration/analytics-correction-plan-status.md`
- Evidence: `08-evidence/documents/orchestration/correction-plan-round2-handoff.md`
- Evidence: `08-evidence/documents/orchestration/tri-benchmark-deferred-plan.md`
