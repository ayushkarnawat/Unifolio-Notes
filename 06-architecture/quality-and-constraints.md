# Quality and Constraints

## Non-functional targets

These are consolidated from the PRDs' own success metrics. They are not new targets
invented at architecture time.

| Requirement | Target | Source |
|---|---|---|
| Dashboard load time | Under 2 seconds at ≤50 holdings | PRD-03 |
| CAS parse success rate | ≥98% | PRD-01 |
| Gain/loss calculation accuracy | 100% match on known-answer fixtures | PRD-01/03/04 |
| Direct/Regular classification accuracy | ≥99% where the signal is present | PRD-01 |
| AMFI scheme-match confidence auto-accept | ≥90% of schemes | PRD-01 |

**On "100% accuracy" — the claim is narrower than it looks, deliberately.** It means
100% of *what is computed* matches hand-verified fixtures. It does **not** claim 100% of
real-world CAS files parse perfectly; that would be an unbounded claim and is not made.
This distinction was raised and resolved explicitly across the PRD set and is worth
preserving, because it is exactly the kind of number that gets quoted out of context.

## Hard rules the code must not break

- **`Decimal` in Python, `NUMERIC` in Postgres. Never floating point.** Every money,
  unit, and NAV field.
- **The PAN is never persisted.** No column exists for it anywhere. It is held in memory
  during the active parse/review session, displayed masked (`ABCDE****F`), and discarded
  with the source PDF.
- **The CAS PDF is never persisted** (ADR-004).
- **Nothing is written to `transactions` before the user confirms.** Parse produces a
  preview only.
- **Duplicate rejection is a database constraint, not application logic.**
- **A failed reference-data refresh degrades to a stale-data label, never to an error
  state.** Missing months show as unavailable, never as zero. Funds with insufficient
  history are skipped by the scorer, not scored badly. An unresolved ARN falls back to
  the raw code and never blocks a page.
- **No new runtime dependencies for scheme matching.** PRD-01 constrains fuzzy matching
  to the standard library's `difflib.SequenceMatcher`, and the same idiom is reused for
  AMFI TER name matching.

## Data classification

| Data | Classification | Handling |
|---|---|---|
| `transactions`, `folios`, `portfolio_snapshots` | Sensitive (financial) | Standard RDS encryption at rest; no masking needed — the user's own numbers |
| Parsed PAN | Highly sensitive | **Not persisted at all.** Transient in memory, masked in display, discarded with the PDF |
| `phone_number` | Sensitive PII, and also an auth credential | Encrypted at rest; rate-limit any lookup path |
| Reference tables | Public | No special handling — already-public AMFI/NSE data |
| CAS PDF | Not stored | Per ADR-004, final |

Session tokens and OTPs are stored hashed. Authentication is passwordless throughout;
password storage was removed from the schema by migration 0008.

## Testing strategy

- **Known-answer fixtures** — hand-verified CAMS and KFintech statements with a known
  expected parse output. These are the concrete backing for the "100% accuracy" NFR
  above. **Status caveat:** PRD-01's Dependencies record that the CAMS fixture was
  requested but not in hand, and the KFintech fixture had not been requested at all. See
  [`07-risks-and-debt.md`](../07-risks-and-debt.md).
- **Integration tests** — the full parse → review → confirm flow against a test
  database, explicitly including dedupe-constraint behaviour on re-upload.
- **Background job tests** — mocked external-source responses verifying the stale-data
  fallback path when a source is unavailable, not only the happy path.

## Cross-cutting risks

Every PRD and ADR carries its own risk list. These are the ones that span documents.

| Risk | Spans | Mitigation |
|---|---|---|
| The AMFI TER/AAUM and NSE Indices automation methods are confirmed feasible but not yet implemented or tested against real responses at production frequency | PRD-04, TDD | Downgraded from "unresolved research question" to "known implementation task" — but worth building early rather than last, because three of the five integrations feed the same Analytics Dashboard and a simultaneous cluster failure on launch week would degrade it noticeably even with per-source stale-data fallbacks |
| ECS Express Mode is newer than the App Runner path it replaces | TDD, ADR-005 | Acknowledged in ADR-005; a light documentation/tooling check closer to implementation, not a reason to delay the decision |
| Cap-wise composition and stock-level overlap remain deferred | PRD-03, PRD-04 | Standing reminder already carried in both PRDs; restated here for visibility |

## Related

- [Deployment](deployment.md), [data model](data-model.md)
- [`07-risks-and-debt.md`](../07-risks-and-debt.md)
