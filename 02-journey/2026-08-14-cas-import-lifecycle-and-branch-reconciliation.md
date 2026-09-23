# A second, independent branch is reconciled: the CAS import lifecycle rebuilt, a UI/UX foundation laid, and the fund Scorer's backend completed

## For stakeholders

While the multi-method auth work (recorded separately, same date) was the
main Claude-Code-led thread this day, a second body of work — built by a
different contributor on a branch that had quietly drifted apart for about
a day — was found and merged in. It included a substantial rebuild of how
CAS statements are imported (an explicit lifecycle instead of an implicit
one), a new visual foundation for the whole app (design tokens, a mobile
shell), and the last piece of the fund-scoring backend that had been
designed on 2026-08-13. All of it passes its tests. None of it — except the
Scorer piece, which did get reviewed — has had the same independent review
pass every other feature this size gets before being called finished. That
gap is recorded here, not smoothed over.

## Technical detail

### Intended outcome

Reconcile a diverged branch (`dev_intern`, authored by `aditishanbhag`)
back into the main workstream (`feat/enhanced-ui`) without losing or
silently overwriting either side's work, and take stock of everything that
had landed on either branch since the two were last compared
(2026-08-13).

### What actually happened

A small, in-progress local fix for a Badge/Select componentry issue was
discarded in favour of the intern's own commits, which independently fixed
the same two problems with an equally valid but different approach. The
two branches merged cleanly as a fast-forward (`dev_intern` had zero unique
commits after that), landing at commit `7426047`. The merged tree was
independently re-verified fresh: backend 357 passed/2 skipped, frontend 190
passed across 49 files, `tsc -b --noEmit` clean.

Reconciling the branches surfaced three streams of work landed since
2026-08-13 without being logged here at the time:

1. **The fund Scorer's backend, completing PRD-04's Analytics backend.**
   Three ordered building blocks (`risk_metrics.py`'s shared time-series
   helpers; `scorer.py`'s composite score at the 45/30/25 Return/Risk/
   Consistency weighting settled with the product owner on 2026-08-13,
   per [ADR-010](../03-decisions/ADR-010-fund-scorer-composite-formula.md);
   a portfolio-level roll-up) plus three new `GET` routes and a
   stakeholder-facing methodology doc. This piece **did** get the
   mandatory independent whole-branch review, which found and fixed 3 real
   issues: a redundant per-fund category re-scoring instead of computing
   shared category inputs once; a `Feb 29` date-arithmetic crash (a repeat
   of a bug already patched once elsewhere, now fixed at the root with a
   shared helper); and a race condition in the daily score cache's
   check-then-insert pattern. Backend suite grew to 357 passed/2 skipped.
   Frontend work against these routes was not found anywhere in this
   session's commit survey — the Analytics dashboard frontend was still
   entirely unbuilt at this point.
2. **The CAS import lifecycle redesign** — see
   [ADR-018](../03-decisions/ADR-018-cas-import-lifecycle-redesign.md) for
   the full design and decision record. Built and passing tests; **not**
   independently reviewed.
3. **A UI/UX foundation** (shadcn/Tailwind design tokens, the mobile app
   shell, a `Select`/`Badge` componentry unification, a `toTitleCase`
   utility) — also intern-authored, also passing tests, also **not**
   independently reviewed.

The reconciliation also found the vault's own knowledge-graph tooling
(`.ua/knowledge-graph.json`) stale as of an earlier commit, predating all
three streams above — a vault-internal tooling note, not itself a product
finding.

### Deviation (if any) — decision or response taken

None of the CAS import lifecycle or UI/UX foundation work was sent through
the same handoff → dispatch → mandatory adversarial-review gate that every
Claude-Code-led feature in this project otherwise goes through before being
called done. This was not a deliberate skip of process on this work — it
was authored entirely outside that process by a different contributor and
only discovered at reconciliation. The explicit decision recorded here is
**not** to treat "passes the test suite" as equivalent to "reviewed" for
either stream.

### Result

Branches merged and identical, full suite green. The fund Scorer backend
is complete and reviewed. The CAS import lifecycle redesign and the UI/UX
foundation are built, tested, and merged, but carry an open review debt —
see [ADR-018](../03-decisions/ADR-018-cas-import-lifecycle-redesign.md) and
[R-004](../07-risks-and-debt.md).

### Related

- ADR-010 — fund scorer composite formula (the backend piece this
  reconciliation completed)
- ADR-018 — CAS import lifecycle redesign
- R-004 — two unreconciled generations of the CAS import flow (this stage
  is the bridging design; the review-debt point is new, not previously
  tracked)
- Evidence: `08-evidence/documents/engineering-loop/session.md` ("Branch
  reconciliation — final check..." section), `08-evidence/documents/engineering-loop/backend.md`,
  `08-evidence/documents/engineering-loop/database.md`
