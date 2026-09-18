# Distributor Comparison — Backend Design

## Purpose

PRD-03 FR-11/FR-11a/FR-11b/FR-11c: when a user holds the same scheme across
folios bought through different distributors (ARNs), show a comparison of
their own returns by distributor, with the distributor's resolved name
where available and a trust signal if AMFI's registry shows the ARN is no
longer valid. Deferred out of Phase 3 (Main Dashboard backend) during that
phase's brainstorming as a separable follow-up with its own external-
integration risk profile; built now as that follow-up, ahead of Phase 3b
(Main Dashboard frontend).

## Scope

**In scope:** the comparison endpoint itself (FR-11), on-demand AMFI ARN
name/status resolution with platform-wide caching in `arn_directory`
(FR-11a), graceful raw-ARN fallback (FR-11b), and a suspended/invalid trust
signal derived from the same lookup (FR-11c).

**Explicitly out of scope:** frontend (Phase 3b, App-Flow S17, separate
spec). A scheduled/bulk ARN-refresh job — FR-11a is on-demand only, per the
TDD's Background Jobs table ("ARN resolution stays on-demand, triggered
... rather than through EventBridge").

## Resolved Open Item: AMFI ARN-lookup automation

PRD-03's own Open Questions flagged this as needing a compliance/ToS check
before implementation, non-blocking given FR-11b's fallback. Resolved this
session with a real, verified endpoint (found via live browser DevTools
inspection against `amfiindia.com/locate-distributor`, independently
re-verified with direct HTTP calls before writing this spec):

```
GET https://www.amfiindia.com/api/distributor-agent?strOpt=ALL&search={arn_digits}&page=1&pageSize=1
Referer: https://www.amfiindia.com/locate-distributor
```

- `search` takes the **bare numeric ARN** (e.g. `0671`), not the `ARN-`
  prefixed form this codebase stores in `folios.arn_code` (confirmed
  against `test_parser.py`) — verified `search=0671` returns an exact
  match while `search=ARN-0671` returns zero results.
- Response: `{"data": [{"ARN": "...", "ARNHolderName": "...",
  "ARNValidTill": "...", ...}], "meta": {"total": N, ...}}`. `total == 0`
  means AMFI has no record of that ARN at all — verified directly.
- This is a **single-item lookup per ARN**, never a bulk/paginated crawl —
  exactly the low-risk pattern PRD-03's Risk table already scoped as
  acceptable ("single-item lookups on a small ARN set, not bulk scraping").

The `amfi-arn-data-scrapper` precedent the TDD originally cited is dead (its
endpoint 404s as of this session — AMFI rebuilt the site since that project
was written); this spec supersedes that citation with the endpoint above.

No separate "suspended ARN list" endpoint was found or is used — FR-11c's
trust signal is derived entirely from this one verified endpoint (see
Status Mapping below), not a second unverified integration.

## Architecture

```
backend/app/services/dashboard/
  arn_lookup.py               # NEW — AMFI client + arn_directory cache
  distributor_comparison.py   # NEW — per-ARN FIFO grouping + response assembly
backend/app/api/dashboard.py  # extended — 1 new GET route
```

### `arn_lookup.py`

Same shape as `nav.py`: an isolated, mockable fetch function plus a
cache-aware wrapper.

```python
async def _fetch_arn_record(arn_code: str) -> dict | None:
    """Bare HTTP call to the verified AMFI endpoint. Strips any 'ARN-'
    prefix before querying. Returns the matched record dict, or None if
    AMFI has no record for this ARN (total == 0)."""

async def resolve_arn(db: Session, arn_code: str) -> ArnDirectory | None:
    """Cache-first: an existing arn_directory row (any status) is returned
    as-is, no re-fetch — FR-11a's 'once per ARN ever, platform-wide', no
    TTL (unlike NAV there is no future scheduled refresh job for this;
    on-demand is the permanent mechanism per the TDD).

    On a cache miss, calls _fetch_arn_record:
    - record found, ARNValidTill >= today  -> write ACTIVE, return it
    - record found, ARNValidTill < today   -> write SUSPENDED, return it
    - total == 0 (AMFI has no such ARN)    -> write INVALID, return it
    - _fetch_arn_record raises (network/HTTP/parse error) -> write NOTHING,
      return None. Same lesson as Phase 3's NAV-outage fix: a transient
      failure must never be cached as a permanent value. The caller
      displays the raw ARN this one time; the next request retries.
    """
```

`distributor_name` on the returned `ArnDirectory` row is `None` for
`INVALID`/a fresh miss that failed — callers fall back to the raw
`arn_code` display per FR-11b, never block on this.

### `distributor_comparison.py`

Reuses `holdings._process_folio_lots` and `nav.get_nav_on_or_before`
exactly like `holdings.py`, grouped one level finer:

```python
async def compute_distributor_comparison(
    db: Session, household_member_id: uuid.UUID, scheme_id: uuid.UUID
) -> list[DistributorComparisonRow]:
```

- Load the member's folios for this scheme, group by `folio.arn_code`
  (folios with `arn_code is None` — Direct plans — group together under a
  `None` bucket; the row's `distributor_name` is omitted/null and no AMFI
  lookup happens for that bucket).
- Per ARN group: run `_process_folio_lots` per folio and sum, exactly as
  `holdings.compute_holdings` does per scheme — same fields
  (`units_held`, `amount_invested` [cost basis], `current_value`,
  `realized_gain`, `unrealized_gain`, `current_profit_total`), plus
  `average_nav = amount_invested / units_held` (`None` if `units_held == 0`),
  same convention as `HoldingRow`. `current_nav`/`current_nav_date`/
  `today_gain` are deliberately *not* repeated per row — the scheme's NAV
  doesn't vary by distributor, so the caller fetches it once (same
  `get_nav_on_or_before` call, reused across every group) rather than
  duplicating an identical value on every row.
- Call `resolve_arn` once per distinct non-null ARN in the result (not per
  folio) to attach `distributor_name`/`arn_status`.
- A scheme with no NAV available (`get_nav_on_or_before` returns `None`)
  drops out entirely, same documented behavior as `holdings.py` (existing
  Follow-up #1 in `session.md` — not re-litigated here).

### Schema addition (`schemas.py`)

```python
class DistributorComparisonRow(BaseModel):
    arn_code: str | None            # None = Direct (no distributor)
    distributor_name: str | None    # None until resolved, or Direct bucket
    arn_status: ArnStatus | None    # None for the Direct bucket
    units_held: str
    average_nav: str | None
    amount_invested: str
    current_value: str
    current_profit_total: str
    realized_gain: str
    unrealized_gain: str
```

### API route (`dashboard.py`)

```
GET /household-members/{member_id}/schemes/{scheme_id}/distributor-comparison
    -> list[DistributorComparisonRow]
```

Deliberate correction of the TDD's API-surface table, which lists
`/funds/{scheme_id}/distributor-comparison` with no member scoping — the
comparison is inherently per-member (a family's two members holding the
same scheme through different distributors are not each other's
comparison), and every existing Dashboard route follows the
`/household-members/{member_id}/...` convention. Same category of
documented TDD correction as Phase 3's allocation-ownership fix.

`Depends(get_current_user)` plus the existing `get_household_member_for_user`
ownership check (404 for a member that doesn't exist or isn't the caller's,
matching every other per-member route). A `scheme_id` the member doesn't
hold, or holds through only one distributor, returns a list (empty or
length-1) — not a 404 or an error; the App-Flow's "only surface S17 when
there's more than one ARN" rule is a frontend nav-gating decision (Phase
3b), not this endpoint's job.

## Error Handling & Edge Cases

- **AMFI lookup fails (network/HTTP/parse error):** `resolve_arn` returns
  `None`, writes nothing to `arn_directory`. The comparison row still
  renders with the raw `arn_code`, `distributor_name: null`,
  `arn_status: null` — FR-11b's fallback, never blocks the response.
- **ARN not in AMFI's registry at all:** cached as `INVALID` (a stable,
  cacheable fact, unlike a transient fetch failure).
- **ARN's registered validity has lapsed:** cached as `SUSPENDED` — FR-11c's
  trust signal.
- **Direct-plan folios (no ARN):** their own bucket, no AMFI lookup
  attempted, `distributor_name`/`arn_status` both `None`.
- **Scheme with no obtainable current NAV:** drops from the response
  entirely — same pre-existing, already-flagged Phase 3 behavior, not
  re-decided here.
- **Member not found / not owned by caller:** 404, same pattern as every
  other per-member Dashboard route.

## Testing

- `_fetch_arn_record` mocked via `unittest.mock.patch`, identical pattern
  to `test_nav.py` — no real network calls in the suite, despite the
  endpoint being real and independently verified by hand during design.
- `resolve_arn`: cache-hit-skips-fetch, cache-miss-writes-`ACTIVE`,
  not-found-writes-`INVALID`, fetch-failure-writes-nothing-and-returns-`None`
  (proving the retryable-on-outage behavior directly, one test per branch).
- `compute_distributor_comparison`: hand-built known-answer fixture with
  two folios of the same scheme under two different ARNs plus one Direct
  folio, asserting per-group FIFO totals — same rigor as `holdings.py`'s
  existing fixtures, reusing the same `_process_folio_lots` function so no
  new algorithmic risk is introduced.
- Ownership check: one 404 test, reusing the existing IDOR test pattern.

## Global Constraints (carried from CLAUDE.md / prior specs)

- `Decimal`, never `float`, for every money/units/NAV value, including any
  test fixtures.
- No raw AMFI response persisted beyond `arn_directory`'s four columns —
  no caching of full API payloads, no new S3 usage (this is a tiny,
  structured, already-public dataset, not the "expensive fetch worth
  raw-caching" case ADR-004 describes).
