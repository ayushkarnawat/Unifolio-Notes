# ADR-012: Active-SIP detection by cadence projection, not a fixed recency window

Status: Accepted
Date: 2026-08-18
Related: [2026-08-18 journey stage](../02-journey/2026-08-18-active-sip-cadence-redesign.md); supersedes one clause of the 2026-08-06 portfolio-accounting conventions

## For stakeholders

Unifolio needed to tell a user which of their systematic investment plans are
still running. The original rule was a recency window — a contribution in the
last 40 days meant the plan counted as active — which is cheap to compute and
wrong whenever a debit date drifts, silently hiding a plan the user has not
cancelled. The product owner rejected that behaviour for this release. The
replacement reads each plan's own rhythm out of its transaction history and
projects the next due date forward, so the product answers "what is due this
month" rather than "what happened recently". The cost is more computation and
more edge cases — month-end clamping, leap years — and an acknowledged risk
that projection can show a plan as due that the user has quietly stopped.
That risk was accepted with a named fallback: if this does not hold up in use,
the original 40-day behaviour documented in PRD-03 is the retreat position.
Designed and planned on 2026-08-18; not yet implemented.

## Technical detail

### Context

The 2026-08-06 decisions-log entry fixed three portfolio-accounting
conventions, one of which was a 40-day active-SIP window backed by the
`SIP_ACTIVE_WINDOW_DAYS` constant. PRD-03 FR-6 documents the same behaviour.
In use it produces two visible failures: a plan whose debit date moves past
the window vanishes, and the dashboard cannot answer what is due in a given
month because it only knows what has already arrived.

### Decision drivers

- The user-facing question is forward-looking ("what is due this month"), and a
  backward-looking window cannot answer it.
- A plan disappearing from the view without any user action is a trust
  failure, worse than showing a plan that has quietly stopped.
- Whatever is chosen must work at both member and household level.
- Unifolio deliberately does not editorialise about missed contributions; the
  design notes Groww does, and rejects that.

### Options considered

#### Option 1: Keep the 40-day recency window

Advantages:
- Already implemented, trivially cheap, one constant.
- No projection means no false "due" rows.
- Matches PRD-03 as written, so no specification conflict to resolve.

Disadvantages:
- Cannot answer "what is due this month" at all.
- Silently drops plans whose debit date drifts, with no signal to the user.
- The cutoff value is arbitrary; nothing in the domain makes 40 days correct.
- Explicitly rejected by the product owner for this release.

#### Option 2: Cadence projection from transaction history

Advantages:
- Answers the forward-looking question directly.
- Derives the interval from the plan's own history rather than a global
  constant.
- Naturally supports a per-month view at member and household level.
- Removes a magic number from the codebase.

Disadvantages:
- Month-end and leap-year clamping must be handled explicitly.
- A plan the user has stopped without redeeming will keep projecting as due.
- More computation per request; needs the accompanying N+1 fix to be viable.

#### Option 3: Cadence projection plus a missed-SIP / `is_actual` flag

Advantages:
- Distinguishes a projected due date from a contribution that actually arrived.
- Would allow a future "your SIP did not go through" signal.

Disadvantages:
- Speculative — no screen in the current design consumes the flag.
- Missed-contribution messaging was explicitly rejected as product behaviour,
  so the flag's only plausible consumer is ruled out.
- Adds a persisted distinction that would then have to be maintained.

### Decision

Option 2. Remove `SIP_ACTIVE_WINDOW_DAYS` and detect active plans by
projecting each plan's own cadence forward from its transaction history.
Expose `GET /household-members/{member_id}/sips/monthly` and
`GET /household/aggregate/sips/monthly`. The only remaining exclusion is a
fully-redeemed folio, identified by a non-positive units-held balance. Month
arithmetic clamps to the real month length. No missed-SIP flag, no step-up
detection, no cancelled state, and no change to how SIPs are detected in the
first place.

### Consequences

Positive:
- A "This Month" view becomes possible at both member and household level.
- Plans stop disappearing because of debit-date drift.
- A magic constant leaves the codebase.
- The accompanying fix collapses a per-folio N+1 to two queries, guarded by a
  query-count regression test.
- The client-side next-due-date computation is deleted, so one number has one
  source.

Negative:
- A silently stopped plan will keep appearing as due until it is redeemed.
- Month-end clamping and leap-year handling are now correctness-critical.
- PRD-03 FR-6 and its edge-case table are now contradicted and need a
  superseding note (R-032).
- One clause of a previously-fixed accounting convention is reversed eleven
  days after it was fixed.

### Validation

Not yet validated. Every task in the implementation plan is unticked, so no
part of this decision is in the product. Validation requires: the two routes
live, the constant removed, the edge-case table from the design exercised by
tests, the query-count regression guard passing, and the PRD-03 superseding
note written. The design states in its own words that this is an explicit
experiment, with PRD-03's original 40-day-cutoff behaviour as the documented
fallback if it does not hold up in use.

### Evidence

- Design: `08-evidence/documents/specs/2026-08-18-active-sips-cadence-redesign-design.md`
- Plan: `08-evidence/documents/plans/2026-08-18-active-sips-cadence-redesign.md`
- Superseded convention: `decisions-log.md`, 2026-08-06, "Three portfolio-accounting conventions fixed" (left untouched)
