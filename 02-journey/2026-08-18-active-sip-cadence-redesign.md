# The active-SIP window is replaced by a cadence model

## For stakeholders

Until this point Unifolio decided whether a systematic investment plan was
"active" by a simple rule: if a contribution had arrived in the last 40 days,
the plan counted as running. That rule is cheap and wrong at the edges — a
plan whose debit date drifts past the window disappears from the user's view
even though nothing has been cancelled. On 2026-08-18 the product owner
explicitly rejected that behaviour for this release. The replacement projects
each plan's own cadence forward from its transaction history and answers the
question the user actually asks: what is due this month. The change was
designed and planned in detail but, on the evidence in this batch, **not yet
built** — every task in the implementation plan is unticked.

## Technical detail

### Intended outcome

Replace recency-window detection with cadence projection, and expose a
per-month view of expected contributions at both member and household level.

### What actually happened

The design settled three things that had been ambiguous.

First, the 40-day cutoff is removed outright. The design records the product
owner's position in plain terms — the behaviour was "explicitly rejected for
this MVP". The only remaining exclusion is a fully-redeemed folio, detected by
`units_held <= 0`.

Second, there is deliberately **no "you missed your SIP" messaging**, in
contrast to how the design notes Groww handles the same situation. Unifolio
shows what is due; it does not editorialise about what did not arrive.

Third, the design is honest that this is a bet: it states that this is an
explicit experiment, and that if it does not hold up in use, PRD-03's original
40-day-cutoff behaviour is the documented fallback. That framing is why this
is recorded as a reversible decision with a named retreat position rather than
a settled convention.

The implementation plan specifies removing the `SIP_ACTIVE_WINDOW_DAYS`
constant, adding `_add_months_clamped`, `_next_due_on_or_after` and
`compute_sips_for_month` helpers, a `SipMonthlyRow` schema and an
`AggregateSipsMonthlyResponse`, and two routes:
`GET /household-members/{member_id}/sips/monthly` and
`GET /household/aggregate/sips/monthly`. Month-end clamping uses
`calendar.monthrange`; the design carries an edge-case table covering clamping,
leap-year 29 February, and backward projection.

The plan also fixes a pre-existing N+1 query pattern in the same path,
reducing it from one query per folio to two total, and guards the fix with a
query-count regression test built on a `before_cursor_execute` engine event
listener. On the frontend, the client-side `nextDueDate` `useMemo` is deleted
in favour of the server-computed value, and the "This Month" tab loads lazily.

Explicitly out of scope, with reasons: an `is_actual` / missed-SIP flag
(judged speculative), step-up detection, a cancelled state, and any change to
how SIPs are detected in the first place.

### Deviation — decision or response taken

This supersedes one clause of the three portfolio-accounting conventions fixed
on 2026-08-06 — specifically the 40-day active-SIP window. Per vault policy
the earlier entry is left untouched and the reversal is recorded as a new
dated decision and as [ADR-012](../03-decisions/ADR-012-active-sip-cadence-projection.md).

The design also requires a superseding note to be added to PRD-03's FR-6 and
its edge-case table, on the stated grounds that a PRD conflict must be flagged
rather than silently resolved. That note is a code-repo document change and is
outside this vault's scope; it is recorded here so the requirement is not lost.

### Result

Designed, planned, and not yet implemented. Every task in the plan is unticked.
Any downstream claim that Unifolio no longer uses a 40-day window is a claim
about intent, not about shipped behaviour.

### Related

- ADR-012 — active-SIP detection by cadence projection
- `decisions-log.md` 2026-08-06 — the original three conventions (unchanged)
- R-032 — the PRD-03 superseding note is required and not yet written
- Evidence: `08-evidence/documents/specs/2026-08-18-active-sips-cadence-redesign-design.md`
- Evidence: `08-evidence/documents/plans/2026-08-18-active-sips-cadence-redesign.md`
