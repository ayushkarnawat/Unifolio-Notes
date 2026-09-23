# INV-009: AMFI TER `ReadTimeout`s root-caused to event-loop starvation from a blocking `db.commit()`

Status: Root cause found and fixed (`bb5225f`, 2026-08-27); one stopgap also
applied; the underlying architectural vulnerability is explicitly **not**
fully closed — see "Residual risk" below.
Date investigated: 2026-08-25/26
Related: [R-040](../07-risks-and-debt.md) (`compute_holdings` N+1, a related
but distinct performance item); [ADR-003](../03-decisions/ADR-003-primary-database-rds-postgresql.md)

## For stakeholders

A colleague's Analytics dashboard kept showing "data unavailable" for TER
and holdings, on the same codebase that worked fine on the product owner's
own machine. Two false leads were ruled out with real evidence before the
true cause was found: a blocking database write inside a request handler —
one that took over a minute on the colleague's slower disk — was freezing
every other request the server was handling at the same moment, including
an unrelated one that then timed out waiting for a government data feed
that had actually already answered. Because this backend runs as a single
worker with one shared task queue, any sufficiently slow database operation
can currently stall every logged-in user at once, not just the person who
triggered it. The specific case was fixed and confirmed working live. The
general shape of the problem — a slow database write can freeze the whole
app for everyone — has been fixed for the writes we know about today, but
is not fixed as a rule for every future one, and is flagged as something to
finish properly once the app moves off its current development database
technology.

## Technical detail

### Symptom

A colleague's Analytics dashboard persistently showed "TER Data
Unavailable" / "No Direct Holdings" / "No Regular Holdings" with a growing
TER-exclusion list, while the same codebase on the product owner's own
machine returned correct data.

### Investigation (via `superpowers:systematic-debugging`, three rounds)

1. **First hypothesis, confirmed real but insufficient**: AMFI's TER-page
   endpoint was being rate-limited at a fetch concurrency of 20 (raised
   there in an earlier session on the unverified assumption AMFI had no
   rate limit). Lowered to 5 (`bb9f507`). The colleague re-tested; the
   symptom recurred.
2. **No diagnosability**: the refresh function had zero logging on any
   failure path. Two `logger.warning` calls added, no behaviour change
   (`142eb6b`). The next live run immediately captured the real failure:
   `ReadTimeout('')` — a genuinely different failure mode from the
   already-fixed rate limit (every AMFI page in that run returned `200
   OK`).
3. **Root cause**: this backend's database engine is fully synchronous and
   runs as a single worker — one event loop shared by every concurrent
   request. A blocking `db.commit()` called directly inside an `async def`
   handler (a NAV-history warming operation, measured at 63.67s then
   66.69s for the same operation minutes apart on the colleague's slower
   disk) freezes that entire event loop for its full duration — including
   an unrelated AMFI TER request already waiting on its own socket in a
   concurrently-running task, which then exceeded its own client-side
   timeout even though AMFI itself had already answered normally. Not a
   repeat of the rate-limit issue, and not the caching-divergence theory
   originally suspected — direct evidence of event-loop starvation.

### Fix applied

A stopgap raised the TER client's own timeout from 30s to 90s (`945b271`),
giving margin against the observed 63-66s stall — this addresses TER's
all-or-nothing batch failure mode, not the underlying starvation. The
underlying vulnerability was then properly fixed, not just worked around:
commit `bb5225f` (2026-08-27) added a `commit_off_loop` helper that routes
`db.commit()` through a background thread, and rewired every reachable
commit across all 8 affected service files, with a regression test proving
a slow commit no longer starves the event loop. All three fixes were
live-tested together on the colleague's machine on 2026-08-26 and confirmed
working (correctly slower than the product owner's machine, not incorrect).

### Residual risk — explicitly not closed

The *trigger* (60-120 second SQLite commits) is specific to this
development environment (SQLite on a WSL filesystem mount) and is expected
to mostly disappear once the app runs on Postgres. The *vulnerability*
itself — any blocking synchronous database call inside an async handler
stalls every concurrent user sharing that event loop, not just the slow
request — is architectural and will still exist in production under real
concurrent traffic (a lock wait, a large batch commit, connection-pool
exhaustion, or a large CAS re-import could all still freeze every logged-in
user's request simultaneously). Three remediation options were identified
and deliberately not chosen yet, to avoid bundling a large cross-cutting
database-layer refactor into unrelated debugging work: wrap only the known
heavy batch commits in a background thread (targeted); wrap every
synchronous database call inside an async handler (blanket, needs
auditing for cross-thread session use); or migrate to SQLAlchemy's native
async engine (the correct long-term fix, a dedicated project of its own).
Revisit deliberately, ideally paired with the Postgres migration. Tracked
as its own dedicated entry: [R-058](../07-risks-and-debt.md).

### Evidence

- `08-evidence/documents/engineering-loop/session.md`, "AMFI TER `ReadTimeout` root-caused to event-loop starvation from blocking `db.commit()` (2026-08-25/26)" section
- `08-evidence/documents/engineering-loop/CLAUDE.md`, "Resolved, dropped from this list" (2026-09-02 entry, records the fix landed without the tracking doc being updated at the time)
