# Phase 1 (Backend) — CAS Import Tightening & Monolith Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten the existing CAS-parser prototype's parsing/matching logic per
PRD-01 (Direct/Regular plan classification, ARN capture, error-message test
coverage), then port that tightened logic into the main Unifolio monolith's
Import Service (`backend/app/services/import_/`, `backend/app/api/imports.py`)
against the real schema Phase 0 already built — retiring the standalone
prototype backend once ported and green. Frontend (Import Review UI) is a
separate follow-up plan once this API is live — not in scope here.

**Architecture:** Two stages. Stage A (Tasks 1–3) tightens pure-Python logic
in place at `CAS Parsers/mf-import/backend/app/`, still validated by the
prototype's own pytest suite — no monolith changes yet. Stage B (Tasks 4–9)
ports that logic into the monolith as new files under `backend/app/core/`
and `backend/app/services/import_/`, targeting the UUID-keyed,
`household_member_id`-scoped schema from Phase 0 (not the prototype's
integer-PK, PAN-persisting schema), then wires `backend/app/api/imports.py`
and retires the prototype.

**Tech Stack:** Same as Phase 0 (FastAPI, SQLAlchemy 2.0, pytest) plus
`casparser>=1.3.0` (CAS PDF parsing, MIT-licensed, already a Phase-0-approved
dependency per PRD-01's Integration Points) and `httpx` (already in
`backend/requirements.txt`) for `mfapi.in` calls.

## Global Constraints

- `Decimal`, never `float`, for every money/units/NAV value — CLAUDE.md non-negotiable.
- No PAN persistence, anywhere, ever — CLAUDE.md non-negotiable, ADR-004. The
  target schema (Phase 0) has no PAN column on any table; the ported code
  must never introduce one. `mask_pan()` is used only for the parse-preview
  response, never written to any model.
- Build for the schema that exists (`backend/app/models/`) — don't add
  columns or tables not already there without flagging why first. This plan
  uses only `Folio.arn_code`/`Folio.plan_type` and `Scheme.plan_name_variant`,
  all already present from Phase 0.
- Money math: units to 3 decimals, amounts to 2, NAV to 4 (PRD-01 Constraints
  section) — already correct in the prototype's `decimal_utils.py`; ported
  verbatim, not re-derived.
- Fuzzy scheme matching stays on stdlib `difflib.SequenceMatcher` — no new
  dependency (PRD-01 Constraints).
- Never silently guess: AMFI match confidence <0.92 and `unclassified`
  Direct/Regular results must block a silent confirm (PRD-01 FR-10).
- Test-driven: every task below is red→green→commit. No implementation step
  without a preceding failing test.

## Pre-Implementation Findings (confirmed this session, not re-derived here)

1. **Architecture:** the prototype at `CAS Parsers/mf-import/backend` is a
   fully standalone FastAPI app (own SQLite DB, own integer-PK models). Per
   `TDD-Unifolio.md`'s Import Service definition and confirmed with the user,
   this phase ports the tightened parsing/matching logic into the monolith
   and retires the standalone app — it does not keep two backends running.
2. **`casparser>=1.3.0` field names** (verified by installing the package and
   inspecting `casparser.types` directly — this plan does not guess):
   - `Folio.PAN`, `Folio.schemes: list[Scheme]`
   - `Scheme.scheme` (name), `Scheme.advisor` (**this is the ARN/broker
     code** — casparser has no field literally named `arn`), `Scheme.isin`,
     `Scheme.amfi`, `Scheme.type`, `Scheme.transactions: list[TransactionData]`
   - `TransactionData.date/description/amount/units/nav/type`
   - `CASData.cas_type: CASFileType` (`UNKNOWN`/`SUMMARY`/`DETAILED`) — already
     used correctly by the prototype to reject Summary CAS.
   - `CASData.file_type: FileType` (`UNKNOWN`/`CAMS`/`KFINTECH`/`CDSL`/`NSDL`)
     — **this** is the CAMS-vs-KFintech source indicator, needed to populate
     `Import.source_cas_type`.
3. **`calc.py` (XIRR/FIFO/valuation) is out of scope for this plan.** It's
   Dashboard Service territory (computing holdings/valuation for display),
   not Import Service. PRD-01's Import Review screen only needs scheme-level
   match confidence and transaction counts, not computed portfolio value —
   confirmed by reading FR-9/FR-10 and the User Experience section. Only
   `decimal_utils.py` (used by parsing/quantization, not by `calc.py`
   specifically) is ported in this plan.
4. **Scheme creation is write-once ("first encounter"), per `TDD-Unifolio.md`'s
   Import Service description** ("writes to ... `schemes` (writes on
   first-encounter)"). A `Scheme` or `Folio` already resolved by
   `amfi_code`/`(household_member_id, scheme_id, folio_number)` is reused,
   never overwritten by a later import — this plan follows that, including
   for `arn_code`/`plan_type`, which are folio-level static properties.

## File Structure

```
CAS Parsers/mf-import/backend/app/
  parser.py                          # MODIFY (Stage A) — add plan classification + ARN capture
  tests/test_parser_normalize.py     # MODIFY (Stage A) — new tests
  tests/test_parser_errors.py        # CREATE (Stage A) — FR-12/13/14 coverage

backend/
  requirements.txt                   # MODIFY — add casparser>=1.3.0
  app/
    core/
      __init__.py                    # CREATE
      decimal_utils.py                # CREATE — ported verbatim from prototype
    services/import_/
      __init__.py                     # MODIFY — currently empty
      parser.py                        # CREATE — ported + adapted casparser wrapper
      enrich.py                        # CREATE — ported mfapi.in client
      schemas.py                       # CREATE — Pydantic request/response models
      service.py                       # CREATE — parse-preview + confirm orchestration
    api/
      imports.py                       # MODIFY — wire real routes
  tests/
    core/test_decimal_utils.py         # CREATE
    services/import_/
      test_parser.py                    # CREATE
      test_enrich.py                     # CREATE
      test_service.py                    # CREATE
    api/test_imports_routes.py          # CREATE
    models/test_no_pan_field.py         # CREATE — guard test
```

---

### Task 1: Direct/Regular plan classification (FR-5, FR-6) — tighten in place

**Files:**
- Modify: `CAS Parsers/mf-import/backend/app/parser.py`
- Modify: `CAS Parsers/mf-import/backend/tests/test_parser_normalize.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `classify_plan_from_name(scheme_name: str) -> str` (returns
  `"direct"` / `"regular"` / `"unresolved"`), `classify_folio_plan_type(name_variant: str, arn_code: str | None) -> str`
  (returns `"direct"` / `"regular"` / `"unclassified"`). Stage B (Task 5)
  imports these exact names.

- [ ] **Step 1: Write the failing tests**

Add to `CAS Parsers/mf-import/backend/tests/test_parser_normalize.py`:
```python
def test_classify_plan_from_name_direct():
    from app.parser import classify_plan_from_name

    assert classify_plan_from_name("HDFC Flexi Cap Fund - Direct Plan - Growth") == "direct"
    assert classify_plan_from_name("ICICI Prudential Bluechip Fund-Direct-Growth") == "direct"


def test_classify_plan_from_name_regular():
    from app.parser import classify_plan_from_name

    assert classify_plan_from_name("Axis Bluechip Fund - Regular Plan - Growth") == "regular"


def test_classify_plan_from_name_unresolved_when_no_signal():
    from app.parser import classify_plan_from_name

    assert classify_plan_from_name("SBI Small Cap Fund - Growth") == "unresolved"


def test_classify_plan_from_name_unresolved_when_both_present():
    """Malformed/ambiguous name mentioning both — never silently guess."""
    from app.parser import classify_plan_from_name

    assert classify_plan_from_name("Fund Direct to Regular Conversion") == "unresolved"


def test_classify_folio_plan_type_direct_confirmed_no_arn():
    from app.parser import classify_folio_plan_type

    assert classify_folio_plan_type("direct", None) == "direct"
    assert classify_folio_plan_type("direct", "") == "direct"


def test_classify_folio_plan_type_direct_contradicted_by_arn():
    """FR-5: signals disagree (direct-named scheme but has a distributor ARN) -> unclassified."""
    from app.parser import classify_folio_plan_type

    assert classify_folio_plan_type("direct", "ARN-12345") == "unclassified"


def test_classify_folio_plan_type_regular_confirmed_regardless_of_arn():
    from app.parser import classify_folio_plan_type

    assert classify_folio_plan_type("regular", "ARN-12345") == "regular"
    assert classify_folio_plan_type("regular", None) == "regular"


def test_classify_folio_plan_type_unresolved_name_always_unclassified():
    from app.parser import classify_folio_plan_type

    assert classify_folio_plan_type("unresolved", "ARN-12345") == "unclassified"
    assert classify_folio_plan_type("unresolved", None) == "unclassified"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "CAS Parsers/mf-import/backend" && .venv/bin/python -m pytest tests/test_parser_normalize.py -v -k classify`
Expected: FAIL — `ImportError: cannot import name 'classify_plan_from_name'`

- [ ] **Step 3: Write minimal implementation**

Add to `CAS Parsers/mf-import/backend/app/parser.py`, after `mask_pan`:
```python
def classify_plan_from_name(scheme_name: str) -> str:
    """FR-5 primary signal: scheme-name pattern match.

    AMC naming conventions for plan type vary in punctuation/position
    ("- Direct Plan", "-Direct-Growth", "Direct Plan -") but the word itself
    is consistent — case-insensitive substring match is more robust across
    AMCs than a fixed suffix pattern (verified against casparser's own
    Scheme.type/scheme fields; no maintained per-AMC lookup table needed for
    this signal, per PRD-01's open question on this).
    """
    name = scheme_name.upper()
    has_direct = "DIRECT" in name
    has_regular = "REGULAR" in name
    if has_direct and not has_regular:
        return "direct"
    if has_regular and not has_direct:
        return "regular"
    return "unresolved"


def classify_folio_plan_type(name_variant: str, arn_code: str | None) -> str:
    """FR-5: combine name-pattern (primary) with ARN presence (corroborating
    signal for Regular only). Where the two disagree, flag unclassified —
    never silently guess, consistent with the AMFI-match confidence pattern.
    """
    has_arn = bool(arn_code and arn_code.strip())
    if name_variant == "regular":
        return "regular"
    if name_variant == "direct":
        return "unclassified" if has_arn else "direct"
    return "unclassified"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_parser_normalize.py -v -k classify`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
cd "/mnt/d/Unifolio code"
git add "CAS Parsers/mf-import/backend/app/parser.py" "CAS Parsers/mf-import/backend/tests/test_parser_normalize.py"
git commit -m "feat(cas-parser): Direct/Regular plan classification (FR-5, FR-6)"
```

---

### Task 2: ARN/broker code capture (FR-7, FR-8) — tighten in place

**Files:**
- Modify: `CAS Parsers/mf-import/backend/app/parser.py`
- Modify: `CAS Parsers/mf-import/backend/tests/test_parser_normalize.py`

**Interfaces:**
- Consumes: `classify_plan_from_name`, `classify_folio_plan_type` (Task 1).
- Produces: `ParsedScheme.arn_code: str | None`, `ParsedScheme.plan_name_variant: str`,
  `ParsedScheme.plan_type: str` fields. Stage B (Task 5) reads these three
  fields directly off the ported `ParsedScheme`.

- [ ] **Step 1: Write the failing test**

Add to `CAS Parsers/mf-import/backend/tests/test_parser_normalize.py`:
```python
def test_normalize_cas_data_captures_arn_and_plan_type():
    from unittest.mock import MagicMock
    from app.parser import _normalize_cas_data
    from casparser.enums import CASFileType, FileType

    txn = MagicMock(
        date="2024-01-01", description="Purchase", amount="5000", units="10",
        nav="500", type="PURCHASE",
    )
    scheme = MagicMock(
        scheme="HDFC Flexi Cap Fund - Regular Plan - Growth",
        isin="INF123", amfi="125497", type="EQUITY", advisor="ARN-99999",
        transactions=[txn],
    )
    folio = MagicMock(folio="123/45", amc="HDFC AMC", PAN="ABCDE1234F", schemes=[scheme])
    data = MagicMock(
        cas_type=CASFileType.DETAILED, file_type=FileType.CAMS,
        investor_info=MagicMock(name="Test Investor", email="t@example.com"),
        folios=[folio], parse_warnings=[],
    )
    data.model_dump_json.return_value = "{}"

    result = _normalize_cas_data(data)

    assert len(result.schemes) == 1
    parsed_scheme = result.schemes[0]
    assert parsed_scheme.arn_code == "ARN-99999"
    assert parsed_scheme.plan_name_variant == "regular"
    assert parsed_scheme.plan_type == "regular"


def test_normalize_cas_data_direct_scheme_no_arn():
    from unittest.mock import MagicMock
    from app.parser import _normalize_cas_data
    from casparser.enums import CASFileType, FileType

    txn = MagicMock(
        date="2024-01-01", description="Purchase", amount="5000", units="10",
        nav="500", type="PURCHASE",
    )
    scheme = MagicMock(
        scheme="ICICI Prudential Bluechip Fund - Direct Plan - Growth",
        isin="INF456", amfi="120716", type="EQUITY", advisor=None,
        transactions=[txn],
    )
    folio = MagicMock(folio="678/90", amc="ICICI AMC", PAN="ABCDE1234F", schemes=[scheme])
    data = MagicMock(
        cas_type=CASFileType.DETAILED, file_type=FileType.CAMS,
        investor_info=MagicMock(name="Test Investor", email="t@example.com"),
        folios=[folio], parse_warnings=[],
    )
    data.model_dump_json.return_value = "{}"

    result = _normalize_cas_data(data)

    parsed_scheme = result.schemes[0]
    assert parsed_scheme.arn_code is None
    assert parsed_scheme.plan_name_variant == "direct"
    assert parsed_scheme.plan_type == "direct"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_parser_normalize.py -v -k captures_arn`
Expected: FAIL — `AttributeError: 'ParsedScheme' object has no attribute 'arn_code'`

- [ ] **Step 3: Write minimal implementation**

In `CAS Parsers/mf-import/backend/app/parser.py`, modify `ParsedScheme` and `_normalize_cas_data`:
```python
@dataclass
class ParsedScheme:
    name: str
    isin: str | None
    amfi: str | None
    scheme_type: str | None
    folio: str
    amc: str
    transaction_count: int
    arn_code: str | None = None
    plan_name_variant: str = "unresolved"
    plan_type: str = "unclassified"
```

In `_normalize_cas_data`, inside the `for scheme in folio.schemes:` loop, change the
`scheme_map[key] = ParsedScheme(...)` construction:
```python
            if key not in scheme_map:
                name_variant = classify_plan_from_name(scheme.scheme)
                arn_code = scheme.advisor if getattr(scheme, "advisor", None) else None
                scheme_map[key] = ParsedScheme(
                    name=scheme.scheme,
                    isin=scheme.isin,
                    amfi=scheme.amfi,
                    scheme_type=scheme.type,
                    folio=folio.folio,
                    amc=folio.amc,
                    transaction_count=0,
                    arn_code=arn_code,
                    plan_name_variant=name_variant,
                    plan_type=classify_folio_plan_type(name_variant, arn_code),
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_parser_normalize.py -v`
Expected: PASS (all tests, no regressions)

- [ ] **Step 5: Commit**

```bash
git add "CAS Parsers/mf-import/backend/app/parser.py" "CAS Parsers/mf-import/backend/tests/test_parser_normalize.py"
git commit -m "feat(cas-parser): capture ARN/broker code and plan classification per scheme (FR-7, FR-8)"
```

---

### Task 3: Error-classification test coverage (FR-12, FR-13, FR-14) — tighten in place

`classify_parse_error` already implements FR-12/13/14 correctly (verified by
reading the code — messages match the PRD text verbatim). This task only
closes the test-coverage gap PRD-01 calls out ("Closing out remaining pytest
coverage").

**Files:**
- Create: `CAS Parsers/mf-import/backend/tests/test_parser_errors.py`

**Interfaces:**
- Consumes: `classify_parse_error`, `ParseError` (existing, unmodified).

- [ ] **Step 1: Write the failing tests**

```python
# CAS Parsers/mf-import/backend/tests/test_parser_errors.py
from app.parser import classify_parse_error


def test_wrong_password_error():
    err = classify_parse_error(Exception("Incorrect password supplied"))
    assert err.code == "wrong_password"
    assert "PAN in uppercase" in err.message


def test_decrypt_failure_classified_as_wrong_password():
    err = classify_parse_error(Exception("Failed to decrypt PDF"))
    assert err.code == "wrong_password"


def test_scanned_pdf_error():
    err = classify_parse_error(Exception("Unable to extract text from image"))
    assert err.code == "unreadable_pdf"
    assert "scanned" in err.message.lower()


def test_generic_error_passes_through_sanitized():
    err = classify_parse_error(Exception("Some obscure internal casparser failure"))
    assert err.code == "parse_failed"
    assert "obscure internal casparser failure" in err.message


def test_generic_error_truncated_to_500_chars():
    err = classify_parse_error(Exception("x" * 1000))
    assert len(err.message) == 500
```

- [ ] **Step 2: Run tests to verify current behavior**

Run: `.venv/bin/python -m pytest tests/test_parser_errors.py -v`
Expected: PASS immediately — this task documents/locks in existing correct
behavior with tests, per PRD-01's coverage gap; if any assertion fails, that
reveals a real regression to fix before continuing (unexpected — flag if so
rather than adjusting the test to match).

- [ ] **Step 3: Commit**

```bash
git add "CAS Parsers/mf-import/backend/tests/test_parser_errors.py"
git commit -m "test(cas-parser): close error-classification coverage gap (FR-12-14)"
```

---

### Task 4: Shared Decimal quantization module in the monolith

**Files:**
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/decimal_utils.py`
- Create: `backend/tests/core/__init__.py`
- Create: `backend/tests/core/test_decimal_utils.py`

**Interfaces:**
- Produces: `quantize_units`, `quantize_amount`, `quantize_nav`, `quantize_pct`,
  `to_decimal` — identical signatures to the prototype's `decimal_utils.py`.
  Task 5's parser port imports these.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/core/test_decimal_utils.py
from decimal import Decimal

from app.core.decimal_utils import quantize_amount, quantize_nav, quantize_units, to_decimal


def test_quantize_units_three_places_half_up():
    assert quantize_units(Decimal("10.12345")) == Decimal("10.123")
    assert quantize_units(Decimal("10.1235")) == Decimal("10.124")


def test_quantize_amount_two_places():
    assert quantize_amount(Decimal("5000.005")) == Decimal("5000.01")


def test_quantize_nav_four_places():
    assert quantize_nav(Decimal("500.00001")) == Decimal("500.0000")


def test_to_decimal_handles_string_and_none():
    assert to_decimal("123.45") == Decimal("123.45")
    assert to_decimal(None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/core/test_decimal_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/core/__init__.py`: empty.

`backend/app/core/decimal_utils.py` (ported verbatim from
`CAS Parsers/mf-import/backend/app/decimal_utils.py` — already correct, no
changes needed):
```python
"""Decimal quantization helpers — units 3dp, amounts 2dp, NAV 4dp."""
from decimal import ROUND_HALF_UP, Decimal

UNITS_PLACES = Decimal("0.001")
AMOUNT_PLACES = Decimal("0.01")
NAV_PLACES = Decimal("0.0001")
PCT_PLACES = Decimal("0.0001")


def quantize_units(value: Decimal) -> Decimal:
    return value.quantize(UNITS_PLACES, rounding=ROUND_HALF_UP)


def quantize_amount(value: Decimal) -> Decimal:
    return value.quantize(AMOUNT_PLACES, rounding=ROUND_HALF_UP)


def quantize_nav(value: Decimal) -> Decimal:
    return value.quantize(NAV_PLACES, rounding=ROUND_HALF_UP)


def quantize_pct(value: Decimal) -> Decimal:
    return value.quantize(PCT_PLACES, rounding=ROUND_HALF_UP)


def to_decimal(value: str | Decimal | int | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
```

`backend/tests/core/__init__.py`: empty.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_decimal_utils.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core backend/tests/core
git commit -m "feat(core): shared Decimal quantization module, ported from CAS parser prototype"
```

---

### Task 5: Port the casparser wrapper into the Import Service

**Files:**
- Create: `backend/app/services/import_/parser.py`
- Create: `backend/tests/services/__init__.py`
- Create: `backend/tests/services/import_/__init__.py`
- Create: `backend/tests/services/import_/test_parser.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: `app.core.decimal_utils.{quantize_amount,quantize_nav,quantize_units,to_decimal}`
  (Task 4), `app.models.enums.TransactionType`.
- Produces: `parse_cas_pdf_bytes(pdf_bytes: bytes, password: str) -> ParseResult`,
  `ParseResult(investor: ParsedInvestor, schemes: list[ParsedScheme], transactions: list[NormalizedTransaction], raw_json: str, parse_warnings: list[str], cas_type: str, file_type: str)`,
  `ParseError(code: str, message: str)`, `mask_pan(pan: str | None) -> str | None`.
  Task 7 (service orchestration) consumes all of these.

This is the tightened `CAS Parsers/mf-import/backend/app/parser.py` from
Tasks 1–2, adapted to: (a) import `TransactionType` from the monolith's
`app.models.enums` instead of the prototype's local enum, (b) **never**
construct or return anything PAN-shaped beyond the transient, masked
`ParsedInvestor.pan_masked` used only for the parse-preview response.

- [ ] **Step 1: Add the dependency**

Add to `backend/requirements.txt`:
```
casparser>=1.3.0
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/services/import_/test_parser.py
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from app.models.enums import TransactionType
from app.services.import_.parser import (
    NormalizedTransaction,
    classify_folio_plan_type,
    classify_plan_from_name,
    mask_pan,
    normalize_txn_type,
)


def test_mask_pan():
    assert mask_pan("ABCDE1234F") == "ABCDE****F"
    assert mask_pan(None) is None


def test_normalize_txn_type_maps_to_monolith_enum():
    assert normalize_txn_type("PURCHASE") == TransactionType.PURCHASE
    assert normalize_txn_type("PURCHASE_SIP") == TransactionType.PURCHASE_SIP
    assert normalize_txn_type("STT_TAX") == TransactionType.STT
    assert normalize_txn_type("STAMP_DUTY_TAX") == TransactionType.STAMP_DUTY
    assert normalize_txn_type("UNKNOWN_TYPE") == TransactionType.MISC


def test_classify_plan_from_name_direct():
    assert classify_plan_from_name("HDFC Flexi Cap Fund - Direct Plan - Growth") == "direct"


def test_classify_folio_plan_type_disagreement_is_unclassified():
    assert classify_folio_plan_type("direct", "ARN-12345") == "unclassified"


def test_dedupe_hash_stable():
    txn = NormalizedTransaction(
        folio="123/45", amc="HDFC AMC", scheme_name="HDFC Flexi Cap",
        isin="INF123", amfi="125497", scheme_type="EQUITY",
        txn_date=date(2024, 1, 1), txn_type=TransactionType.PURCHASE,
        description="Purchase", amount=Decimal("5000.00"),
        units=Decimal("10.000"), nav=Decimal("500.0000"),
    )
    assert txn.dedupe_hash() == txn.dedupe_hash()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/services/import_/test_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.import_.parser'`

- [ ] **Step 4: Write minimal implementation**

`backend/tests/services/__init__.py`: empty.
`backend/tests/services/import_/__init__.py`: empty.

`backend/app/services/import_/parser.py`:
```python
"""casparser wrapper, normalization, plan classification, error classification.

Ported from CAS Parsers/mf-import/backend/app/parser.py (tightened per
PRD-01 FR-5-8) and re-targeted at the monolith's TransactionType enum. Never
persists PAN — pan_masked exists only for the transient parse-preview
response (CLAUDE.md non-negotiable, ADR-004).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date

from decimal import Decimal

import casparser
from casparser.enums import CASFileType, FileType, TransactionType as CasTxnType
from casparser.types import CASData, NSDLCASData

from app.core.decimal_utils import quantize_amount, quantize_nav, quantize_units, to_decimal
from app.models.enums import TransactionType

CAS_TO_CANONICAL: dict[str, TransactionType] = {
    "PURCHASE": TransactionType.PURCHASE,
    "PURCHASE_SIP": TransactionType.PURCHASE_SIP,
    "REDEMPTION": TransactionType.REDEMPTION,
    "SWITCH_IN": TransactionType.SWITCH_IN,
    "SWITCH_IN_MERGER": TransactionType.SWITCH_IN,
    "SWITCH_OUT": TransactionType.SWITCH_OUT,
    "SWITCH_OUT_MERGER": TransactionType.SWITCH_OUT,
    "DIVIDEND_PAYOUT": TransactionType.DIVIDEND_PAYOUT,
    "DIVIDEND_REINVEST": TransactionType.DIVIDEND_REINVEST,
    "SEGREGATION": TransactionType.SEGREGATION,
    "STT_TAX": TransactionType.STT,
    "STAMP_DUTY_TAX": TransactionType.STAMP_DUTY,
}

SOURCE_CAS_TYPE_MAP = {"CAMS": "cams", "KFINTECH": "kfintech"}


def mask_pan(pan: str | None) -> str | None:
    if not pan or len(pan) < 10:
        return pan
    return f"{pan[:5]}****{pan[-1]}"


def normalize_txn_type(raw: str | CasTxnType) -> TransactionType:
    key = str(raw).split(".")[-1].upper()
    return CAS_TO_CANONICAL.get(key, TransactionType.MISC)


def classify_plan_from_name(scheme_name: str) -> str:
    """FR-5 primary signal: scheme-name pattern match. Case-insensitive
    substring match is more robust across AMCs than a fixed suffix pattern —
    no maintained per-AMC lookup table needed for this signal."""
    name = scheme_name.upper()
    has_direct = "DIRECT" in name
    has_regular = "REGULAR" in name
    if has_direct and not has_regular:
        return "direct"
    if has_regular and not has_direct:
        return "regular"
    return "unresolved"


def classify_folio_plan_type(name_variant: str, arn_code: str | None) -> str:
    """FR-5: primary (name) + corroborating (ARN, Regular-only) signal.
    Disagreement -> unclassified. Never silently guess."""
    has_arn = bool(arn_code and arn_code.strip())
    if name_variant == "regular":
        return "regular"
    if name_variant == "direct":
        return "unclassified" if has_arn else "direct"
    return "unclassified"


def source_cas_type_from_file_type(file_type: FileType | str) -> str | None:
    key = str(file_type).split(".")[-1].upper()
    return SOURCE_CAS_TYPE_MAP.get(key)


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@dataclass
class NormalizedTransaction:
    folio: str
    amc: str
    scheme_name: str
    isin: str | None
    amfi: str | None
    scheme_type: str | None
    txn_date: date
    txn_type: TransactionType
    description: str
    amount: Decimal | None
    units: Decimal | None
    nav: Decimal | None

    def dedupe_hash(self) -> str:
        key = "|".join(
            [self.folio, self.scheme_name, self.txn_date.isoformat(), str(self.amount or ""), str(self.units or "")]
        )
        return hashlib.sha256(key.encode()).hexdigest()


@dataclass
class ParsedInvestor:
    name: str | None
    email: str | None
    pan_masked: str | None


@dataclass
class ParsedScheme:
    name: str
    isin: str | None
    amfi: str | None
    scheme_type: str | None
    folio: str
    amc: str
    transaction_count: int
    arn_code: str | None = None
    plan_name_variant: str = "unresolved"
    plan_type: str = "unclassified"


@dataclass
class ParseResult:
    investor: ParsedInvestor
    schemes: list[ParsedScheme]
    transactions: list[NormalizedTransaction]
    raw_json: str
    parse_warnings: list[str] = field(default_factory=list)
    cas_type: str = "DETAILED"
    file_type: str = "UNKNOWN"


class ParseError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def classify_parse_error(exc: Exception) -> ParseError:
    msg = str(exc).lower()
    if "password" in msg or "decrypt" in msg or "incorrect" in msg:
        return ParseError(
            "wrong_password",
            "Incorrect PDF password. CAMS/KFintech CAS passwords are usually your PAN in uppercase.",
        )
    if "image" in msg or "scan" in msg or "extract" in msg or "text" in msg:
        return ParseError(
            "unreadable_pdf",
            "PDF appears scanned or unreadable. Download the original email PDF, not a photo/scan.",
        )
    return ParseError("parse_failed", str(exc)[:500])


def _normalize_cas_data(data: CASData) -> ParseResult:
    if data.cas_type == CASFileType.SUMMARY or str(data.cas_type).upper() == "SUMMARY":
        raise ParseError(
            "summary_cas",
            "This is a Summary CAS. Request a Detailed CAS from camsonline.com → Statements → CAS.",
        )

    investor_info = data.investor_info
    pan = data.folios[0].PAN if data.folios and data.folios[0].PAN else None
    investor = ParsedInvestor(
        name=investor_info.name if investor_info else None,
        email=investor_info.email if investor_info else None,
        pan_masked=mask_pan(pan),
    )

    transactions: list[NormalizedTransaction] = []
    scheme_map: dict[tuple[str, str, str], ParsedScheme] = {}

    for folio in data.folios:
        for scheme in folio.schemes:
            key = (folio.folio, folio.amc, scheme.scheme)
            if key not in scheme_map:
                name_variant = classify_plan_from_name(scheme.scheme)
                arn_code = scheme.advisor if getattr(scheme, "advisor", None) else None
                scheme_map[key] = ParsedScheme(
                    name=scheme.scheme,
                    isin=scheme.isin,
                    amfi=scheme.amfi,
                    scheme_type=scheme.type,
                    folio=folio.folio,
                    amc=folio.amc,
                    transaction_count=0,
                    arn_code=arn_code,
                    plan_name_variant=name_variant,
                    plan_type=classify_folio_plan_type(name_variant, arn_code),
                )
            for txn in scheme.transactions:
                norm = NormalizedTransaction(
                    folio=folio.folio, amc=folio.amc, scheme_name=scheme.scheme,
                    isin=scheme.isin, amfi=scheme.amfi, scheme_type=scheme.type,
                    txn_date=_parse_date(txn.date), txn_type=normalize_txn_type(txn.type),
                    description=txn.description,
                    amount=quantize_amount(to_decimal(txn.amount)) if txn.amount is not None else None,
                    units=quantize_units(to_decimal(txn.units)) if txn.units is not None else None,
                    nav=quantize_nav(to_decimal(txn.nav)) if txn.nav is not None else None,
                )
                transactions.append(norm)
                scheme_map[key].transaction_count += 1

    return ParseResult(
        investor=investor,
        schemes=list(scheme_map.values()),
        transactions=transactions,
        raw_json=data.model_dump_json(),
        parse_warnings=list(data.parse_warnings or []),
        cas_type=str(data.cas_type),
        file_type=str(data.file_type),
    )


def parse_cas_pdf_bytes(pdf_bytes: bytes, password: str) -> ParseResult:
    """Parse CAS PDF from bytes; temp file deleted after parsing — no raw
    CAS PDF storage, ever (CLAUDE.md non-negotiable)."""
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        result = casparser.read_cas_pdf(tmp_path, password)
    except Exception as exc:
        raise classify_parse_error(exc) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if isinstance(result, NSDLCASData):
        raise ParseError(
            "demat_cas",
            "This appears to be an NSDL/CDSL demat CAS. Equity/demat statements aren't supported in this version.",
        )
    if not isinstance(result, CASData):
        raise ParseError("parse_failed", "Unexpected parser output type.")

    return _normalize_cas_data(result)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pip install -r backend/requirements.txt -q && cd backend && .venv/bin/python -m pytest tests/services/import_/test_parser.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/services/import_/parser.py backend/tests/services
git commit -m "feat(import): port casparser wrapper into monolith Import Service"
```

---

### Task 6: Port mfapi.in enrichment client into the Import Service

**Files:**
- Create: `backend/app/services/import_/enrich.py`
- Create: `backend/tests/services/import_/test_enrich.py`

**Interfaces:**
- Consumes: `app.core.decimal_utils.{quantize_nav,to_decimal}` (Task 4).
- Produces: `MfApiClient` with `resolve_scheme(scheme_name, amfi_from_cas) -> tuple[SchemeMatch | None, str]`,
  `get_scheme_category(amfi_code) -> str | None`, `SchemeMatch(amfi_code, scheme_name, confidence, category)`.
  Task 7 consumes `MfApiClient`.

Ported from `CAS Parsers/mf-import/backend/app/enrich.py`, trimmed to only
what Import Service needs (scheme resolution + category lookup for
`Scheme.sebi_category`) — `get_nav_series`/`get_latest_nav`/valuation-history
methods are Dashboard Service's concern (Task 3 finding), not ported here.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/import_/test_enrich.py
import asyncio
from unittest.mock import AsyncMock, patch

from app.services.import_.enrich import MfApiClient


def test_resolve_scheme_trusts_cas_amfi_code(tmp_path):
    client = MfApiClient(cache_dir=tmp_path)
    match, status = asyncio.run(client.resolve_scheme("Any Fund Name", "125497"))
    assert match.amfi_code == "125497"
    assert match.confidence == 1.0
    assert status == "confirmed"


def test_resolve_scheme_fuzzy_matches_when_no_cas_amfi_code(tmp_path):
    client = MfApiClient(cache_dir=tmp_path)
    scheme_list = [{"schemeCode": "100001", "schemeName": "HDFC Flexi Cap Fund Direct Growth"}]
    with patch.object(client, "get_scheme_list", new=AsyncMock(return_value=scheme_list)):
        match, status = asyncio.run(client.resolve_scheme("HDFC Flexi Cap Fund - Direct Plan - Growth", None))
    assert match.amfi_code == "100001"
    assert match.confidence > 0.9
    assert status in ("confirmed", "pending")


def test_resolve_scheme_low_confidence_is_pending(tmp_path):
    client = MfApiClient(cache_dir=tmp_path)
    scheme_list = [{"schemeCode": "999999", "schemeName": "Completely Unrelated Scheme Name"}]
    with patch.object(client, "get_scheme_list", new=AsyncMock(return_value=scheme_list)):
        match, status = asyncio.run(client.resolve_scheme("XYZ Totally Different Fund", None))
    assert status == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/services/import_/test_enrich.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.import_.enrich'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/services/import_/enrich.py`:
```python
"""mfapi.in client — scheme resolution + category lookup for Import Service.

Ported from CAS Parsers/mf-import/backend/app/enrich.py, trimmed to what
Import Service needs (scheme matching, not valuation history — that's
Dashboard Service's job). Fuzzy matching stays on stdlib
difflib.SequenceMatcher per PRD-01 Constraints — no new dependency.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

MFAPI_BASE = "https://api.mfapi.in"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / ".cache" / "mfapi"
SCHEMES_TTL = timedelta(hours=24)


@dataclass
class SchemeMatch:
    amfi_code: str
    scheme_name: str
    confidence: float
    category: str | None = None


def _normalize_name(name: str) -> str:
    s = name.upper()
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _cache_valid(path: Path, ttl: timedelta) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - mtime < ttl


class MfApiClient:
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._schemes: list[dict[str, Any]] | None = None

    async def _get_json(self, url: str) -> Any:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    async def get_scheme_list(self) -> list[dict[str, Any]]:
        if self._schemes is not None:
            return self._schemes
        cache_path = self.cache_dir / "schemes.json"
        if _cache_valid(cache_path, SCHEMES_TTL):
            self._schemes = json.loads(cache_path.read_text(encoding="utf-8"))
            return self._schemes
        data = await self._get_json(f"{MFAPI_BASE}/mf")
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        self._schemes = data
        return data

    def fuzzy_match_scheme(self, scheme_name: str, scheme_list: list[dict[str, Any]]) -> SchemeMatch | None:
        norm_query = _normalize_name(scheme_name)
        best: SchemeMatch | None = None
        for item in scheme_list:
            name = item.get("schemeName") or item.get("scheme_name") or ""
            ratio = SequenceMatcher(None, norm_query, _normalize_name(name)).ratio()
            if best is None or ratio > best.confidence:
                code = str(item.get("schemeCode") or item.get("scheme_code") or "")
                best = SchemeMatch(amfi_code=code, scheme_name=name, confidence=ratio)
        return best

    async def resolve_scheme(self, scheme_name: str, amfi_from_cas: str | None) -> tuple[SchemeMatch | None, str]:
        """Returns (match, match_status). Never silently guess below 0.92 (PRD-01 FR-10)."""
        if amfi_from_cas:
            return SchemeMatch(amfi_code=amfi_from_cas, scheme_name=scheme_name, confidence=1.0), "confirmed"

        scheme_list = await self.get_scheme_list()
        match = self.fuzzy_match_scheme(scheme_name, scheme_list)
        if match is None or match.confidence < 0.92:
            return match, "pending"
        return match, "confirmed" if match.confidence >= 0.98 else "pending"

    async def get_scheme_category(self, amfi_code: str) -> str | None:
        cache_path = self.cache_dir / f"{amfi_code}_meta.json"
        if _cache_valid(cache_path, SCHEMES_TTL):
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            data = await self._get_json(f"{MFAPI_BASE}/mf/{amfi_code}")
            cache_path.write_text(json.dumps(data), encoding="utf-8")
        meta = data.get("meta") or {}
        return meta.get("scheme_category") or meta.get("schemeCategory")


mfapi_client = MfApiClient()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/services/import_/test_enrich.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/import_/enrich.py backend/tests/services/import_/test_enrich.py
git commit -m "feat(import): port mfapi.in scheme-resolution client into Import Service"
```

---

### Task 7: Import Service orchestration — parse preview + confirm (FR-9, FR-10, FR-11)

**Files:**
- Create: `backend/app/services/import_/schemas.py`
- Create: `backend/app/services/import_/service.py`
- Create: `backend/tests/services/import_/test_service.py`

**Interfaces:**
- Consumes: `app.services.import_.parser.{parse_cas_pdf_bytes,ParseError,ParseResult,source_cas_type_from_file_type}`
  (Task 5), `app.services.import_.enrich.MfApiClient` (Task 6), models
  `Scheme`, `Folio`, `Import`, `Transaction` (Phase 0), enums `PlanNameVariant`,
  `PlanType`, `ImportStatus`, `SourceCasType`.
- Produces: `build_import_preview(parse_result, filename, client=None) -> ImportPreviewResponse`,
  `confirm_import(db, session_id, household_member_id, scheme_confirmations) -> ImportConfirmResponse`.
  Task 8 (API routes) calls both.

**Design notes carried into the code below** (why, not restated in comments
per CLAUDE.md's guidance on when docs already cover the what):
- No `Investor` table exists in the target schema — parsed investor
  name/email/PAN are returned in the preview response for the user's own
  eyeballing, never persisted anywhere (satisfies the PAN non-negotiable by
  construction, not by a delete-and-move-on fix).
- `Scheme.amfi_code` is `NOT NULL UNIQUE` — confirm rejects any scheme still
  below the 0.92 confidence threshold with no explicit override (FR-10).
- `Scheme.sebi_category` is `NOT NULL` — falls back through
  mfapi-category → CAS `scheme_type` → `"Unclassified"`, never left null.
- Dedupe uses the real `(folio_id, date, amount, units)` unique constraint
  via a pre-check query — no separate `dedupe_hash` column exists on the
  new `Transaction` table (unlike the prototype's), so none is computed.
- Scheme/Folio are write-once ("first encounter" per TDD-Unifolio.md) — an
  existing match is reused, never overwritten by a later import.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/import_/test_service.py
import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.user import HouseholdMember, User
from app.models.enums import Relationship
from app.models.reference import Scheme
from app.models.folio import Folio
from app.models.transaction import Transaction
from app.models.imports import Import
from app.services.import_.parser import NormalizedTransaction, ParsedInvestor, ParsedScheme, ParseResult
from app.services.import_.service import build_import_preview, confirm_import
from app.models.enums import TransactionType
from decimal import Decimal
from datetime import date


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _household_member(db):
    user = User(id=uuid.uuid4(), phone_number="+919999999999", created_at=datetime.now(timezone.utc))
    db.add(user)
    db.flush()
    member = HouseholdMember(
        id=uuid.uuid4(), user_id=user.id, name="Self",
        relationship=Relationship.SELF, created_at=datetime.now(timezone.utc),
    )
    db.add(member)
    db.commit()
    return member


def _mocked_client(category: str | None = "Equity Scheme - Flexi Cap Fund"):
    """AsyncMock's child attributes are themselves unconfigured AsyncMocks —
    resolve_scheme must be explicitly configured or `await client.resolve_scheme(...)`
    returns a bare mock instead of the (match, status) tuple callers expect."""
    from app.services.import_.enrich import SchemeMatch

    client = AsyncMock()
    client.resolve_scheme.return_value = (
        SchemeMatch(amfi_code="125497", scheme_name="HDFC Flexi Cap Fund - Direct Plan - Growth", confidence=1.0),
        "confirmed",
    )
    client.get_scheme_category.return_value = category
    return client


def _sample_parse_result():
    txn = NormalizedTransaction(
        folio="123/45", amc="HDFC AMC", scheme_name="HDFC Flexi Cap Fund - Direct Plan - Growth",
        isin="INF123", amfi="125497", scheme_type="EQUITY", txn_date=date(2024, 1, 1),
        txn_type=TransactionType.PURCHASE, description="Purchase",
        amount=Decimal("5000.00"), units=Decimal("10.000"), nav=Decimal("500.0000"),
    )
    scheme = ParsedScheme(
        name="HDFC Flexi Cap Fund - Direct Plan - Growth", isin="INF123", amfi="125497",
        scheme_type="EQUITY", folio="123/45", amc="HDFC AMC", transaction_count=1,
        arn_code=None, plan_name_variant="direct", plan_type="direct",
    )
    return ParseResult(
        investor=ParsedInvestor(name="Test Investor", email="t@example.com", pan_masked="ABCDE****F"),
        schemes=[scheme], transactions=[txn], raw_json="{}",
        parse_warnings=[], cas_type="DETAILED", file_type="FileType.CAMS",
    )


def test_build_import_preview_confident_amfi_match_needs_no_override():
    client = _mocked_client()
    preview = asyncio.run(build_import_preview(_sample_parse_result(), "test.pdf", client=client))

    assert preview.investor_name == "Test Investor"
    assert preview.pan_masked == "ABCDE****F"
    assert len(preview.schemes) == 1
    assert preview.schemes[0].suggested_amfi_code == "125497"
    assert preview.schemes[0].match_confidence == 1.0
    assert preview.schemes[0].plan_type == "direct"
    assert preview.transaction_count == 1


def test_confirm_import_creates_scheme_folio_and_transaction():
    db = _session()
    member = _household_member(db)
    client = _mocked_client()
    preview = asyncio.run(build_import_preview(_sample_parse_result(), "test.pdf", client=client))

    result = confirm_import(db, preview.session_id, member.id, scheme_confirmations=[])

    assert result.added == 1
    assert result.skipped == 0
    scheme = db.query(Scheme).filter_by(amfi_code="125497").one()
    assert scheme.sebi_category == "Equity Scheme - Flexi Cap Fund"
    assert scheme.plan_name_variant.value == "direct"
    folio = db.query(Folio).filter_by(folio_number="123/45").one()
    assert folio.plan_type.value == "direct"
    assert folio.household_member_id == member.id
    txn = db.query(Transaction).one()
    assert txn.amount == Decimal("5000.00")
    imp = db.query(Import).one()
    assert imp.new_transactions_count == 1
    assert imp.source_cas_type.value == "cams"


def test_confirm_import_deduped_on_reupload():
    db = _session()
    member = _household_member(db)
    client = _mocked_client()

    preview1 = asyncio.run(build_import_preview(_sample_parse_result(), "test.pdf", client=client))
    confirm_import(db, preview1.session_id, member.id, scheme_confirmations=[])

    preview2 = asyncio.run(build_import_preview(_sample_parse_result(), "test.pdf", client=client))
    result2 = confirm_import(db, preview2.session_id, member.id, scheme_confirmations=[])

    assert result2.added == 0
    assert result2.skipped == 1
    assert db.query(Transaction).count() == 1


def test_confirm_import_rejects_low_confidence_scheme_without_override():
    from app.services.import_.parser import NormalizedTransaction, ParsedScheme

    db = _session()
    member = _household_member(db)
    txn = NormalizedTransaction(
        folio="1", amc="X AMC", scheme_name="Ambiguous Fund", isin=None, amfi=None,
        scheme_type="EQUITY", txn_date=date(2024, 1, 1), txn_type=TransactionType.PURCHASE,
        description="Purchase", amount=Decimal("1000.00"), units=Decimal("5.000"), nav=Decimal("200.0000"),
    )
    scheme = ParsedScheme(
        name="Ambiguous Fund", isin=None, amfi=None, scheme_type="EQUITY", folio="1", amc="X AMC",
        transaction_count=1, arn_code=None, plan_name_variant="unresolved", plan_type="unclassified",
    )
    parse_result = ParseResult(
        investor=ParsedInvestor(name=None, email=None, pan_masked=None), schemes=[scheme],
        transactions=[txn], raw_json="{}", parse_warnings=[], cas_type="DETAILED", file_type="FileType.CAMS",
    )
    client = AsyncMock()
    client.get_scheme_list = AsyncMock(return_value=[])
    client.resolve_scheme = AsyncMock(return_value=(None, "pending"))
    client.get_scheme_category.return_value = None

    preview = asyncio.run(build_import_preview(parse_result, "test.pdf", client=client))
    assert preview.schemes[0].match_status == "pending"

    import pytest
    with pytest.raises(ValueError, match="requires an explicit AMFI code"):
        confirm_import(db, preview.session_id, member.id, scheme_confirmations=[])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/services/import_/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.import_.service'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/services/import_/schemas.py`:
```python
"""Pydantic request/response contracts for the Import Service API."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class SchemeMatchPreview(BaseModel):
    temp_id: str
    name: str
    isin: str | None
    amfi_code: str | None
    suggested_amfi_code: str | None
    suggested_name: str | None
    match_confidence: float
    match_status: str
    folio: str
    amc: str
    transaction_count: int
    plan_type: str
    category: str | None = None


class TransactionPreview(BaseModel):
    folio: str
    scheme_name: str
    txn_date: date
    txn_type: str
    description: str | None
    amount: str | None
    units: str | None
    nav: str | None


class ImportPreviewResponse(BaseModel):
    session_id: str
    filename: str
    investor_name: str | None
    investor_email: str | None
    pan_masked: str | None
    schemes: list[SchemeMatchPreview]
    transactions: list[TransactionPreview]
    transaction_count: int
    parse_warnings: list[str]
    cas_type: str
    file_type: str


class SchemeConfirmation(BaseModel):
    temp_id: str
    amfi_code: str | None = None
    plan_type_override: str | None = None


class ImportConfirmRequest(BaseModel):
    session_id: str
    household_member_id: str
    scheme_confirmations: list[SchemeConfirmation] = Field(default_factory=list)


class ImportConfirmResponse(BaseModel):
    added: int
    skipped: int
    import_id: str
```

`backend/app/services/import_/service.py`:
```python
"""Import Service orchestration: parse preview (no DB writes) and confirm
(persists). Implements PRD-01 FR-9-FR-11.

In-memory preview sessions are a deliberate, prototype-carried
simplification (ponytail: single-process only; move to a DB-backed or
Redis-backed session store if a multi-instance deploy needs this later).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.decimal_utils import quantize_amount
from app.models.enums import PlanNameVariant, PlanType, SourceCasType
from app.models.folio import Folio
from app.models.imports import Import, ImportStatus
from app.models.reference import Scheme
from app.models.transaction import Transaction
from app.services.import_.enrich import MfApiClient, mfapi_client
from app.services.import_.parser import ParseResult, source_cas_type_from_file_type
from app.services.import_.schemas import (
    ImportConfirmResponse,
    ImportPreviewResponse,
    SchemeConfirmation,
    SchemeMatchPreview,
    TransactionPreview,
)

_preview_sessions: dict[str, dict[str, Any]] = {}

CONFIDENCE_THRESHOLD = 0.92


async def build_import_preview(
    parse_result: ParseResult, filename: str, client: MfApiClient | None = None
) -> ImportPreviewResponse:
    client = client or mfapi_client
    session_id = uuid.uuid4().hex

    scheme_previews: list[SchemeMatchPreview] = []
    key_to_temp: dict[tuple[str, str, str], str] = {}

    for scheme in parse_result.schemes:
        temp_id = uuid.uuid4().hex[:12]
        key_to_temp[(scheme.folio, scheme.amc, scheme.name)] = temp_id

        match, status = await client.resolve_scheme(scheme.name, scheme.amfi)
        category = None
        if match and match.amfi_code:
            category = await client.get_scheme_category(match.amfi_code)

        scheme_previews.append(
            SchemeMatchPreview(
                temp_id=temp_id, name=scheme.name, isin=scheme.isin, amfi_code=scheme.amfi,
                suggested_amfi_code=match.amfi_code if match else None,
                suggested_name=match.scheme_name if match else None,
                match_confidence=match.confidence if match else 0.0,
                match_status=status, folio=scheme.folio, amc=scheme.amc,
                transaction_count=scheme.transaction_count, plan_type=scheme.plan_type,
                category=category or scheme.scheme_type,
            )
        )

    txn_previews = [
        TransactionPreview(
            folio=t.folio, scheme_name=t.scheme_name, txn_date=t.txn_date, txn_type=t.txn_type.value,
            description=t.description, amount=str(t.amount) if t.amount is not None else None,
            units=str(t.units) if t.units is not None else None, nav=str(t.nav) if t.nav is not None else None,
        )
        for t in parse_result.transactions
    ]

    _preview_sessions[session_id] = {
        "filename": filename, "parse_result": parse_result,
        "key_to_temp": key_to_temp,
        "scheme_previews": {s.temp_id: s for s in scheme_previews},
    }

    return ImportPreviewResponse(
        session_id=session_id, filename=filename,
        investor_name=parse_result.investor.name, investor_email=parse_result.investor.email,
        pan_masked=parse_result.investor.pan_masked, schemes=scheme_previews, transactions=txn_previews,
        transaction_count=len(txn_previews), parse_warnings=parse_result.parse_warnings,
        cas_type=parse_result.cas_type, file_type=parse_result.file_type,
    )


def _resolve_category(mfapi_category: str | None, cas_scheme_type: str | None) -> str:
    return mfapi_category or cas_scheme_type or "Unclassified"


def confirm_import(
    db: Session,
    session_id: str,
    household_member_id: uuid.UUID,
    scheme_confirmations: list[SchemeConfirmation],
) -> ImportConfirmResponse:
    session = _preview_sessions.get(session_id)
    if not session:
        raise ValueError("Import session not found or expired.")

    parse_result: ParseResult = session["parse_result"]
    previews: dict[str, SchemeMatchPreview] = session["scheme_previews"]
    key_to_temp = session["key_to_temp"]
    overrides = {c.temp_id: c for c in scheme_confirmations}

    import_rec = Import(
        id=uuid.uuid4(), household_member_id=household_member_id, status=ImportStatus.CONFIRMED,
        source_cas_type=_map_source_cas_type(parse_result.file_type),
        raw_parser_output={"raw": parse_result.raw_json},
        uploaded_at=datetime.now(timezone.utc), confirmed_at=datetime.now(timezone.utc),
    )
    db.add(import_rec)
    db.flush()

    scheme_cache: dict[str, Scheme] = {}
    folio_cache: dict[tuple[str, str], Folio] = {}
    added = 0
    skipped = 0

    for norm in parse_result.transactions:
        temp_id = key_to_temp[(norm.folio, norm.amc, norm.scheme_name)]
        preview = previews[temp_id]
        override = overrides.get(temp_id)

        amfi_code = (override.amfi_code if override and override.amfi_code else None) or preview.suggested_amfi_code
        confident = preview.match_confidence >= CONFIDENCE_THRESHOLD or bool(override and override.amfi_code)
        if not amfi_code or not confident:
            raise ValueError(
                f"Scheme '{preview.name}' requires an explicit AMFI code override (match confidence "
                f"{preview.match_confidence:.2f} below {CONFIDENCE_THRESHOLD})."
            )

        if amfi_code not in scheme_cache:
            existing = db.query(Scheme).filter_by(amfi_code=amfi_code).first()
            if existing:
                scheme_cache[amfi_code] = existing
            else:
                plan_name_variant = None
                for parsed_scheme in parse_result.schemes:
                    if parsed_scheme.folio == norm.folio and parsed_scheme.amc == norm.amc and parsed_scheme.name == norm.scheme_name:
                        plan_name_variant = parsed_scheme.plan_name_variant
                        break
                new_scheme = Scheme(
                    id=uuid.uuid4(), amfi_code=amfi_code, isin=norm.isin, name=norm.scheme_name,
                    amc_name=norm.amc, sebi_category=_resolve_category(preview.category, norm.scheme_type),
                    plan_name_variant=PlanNameVariant(plan_name_variant) if plan_name_variant else None,
                )
                db.add(new_scheme)
                db.flush()
                scheme_cache[amfi_code] = new_scheme

        scheme = scheme_cache[amfi_code]
        folio_key = (household_member_id, scheme.id, norm.folio)
        if folio_key not in folio_cache:
            existing_folio = (
                db.query(Folio)
                .filter_by(household_member_id=household_member_id, scheme_id=scheme.id, folio_number=norm.folio)
                .first()
            )
            if existing_folio:
                folio_cache[folio_key] = existing_folio
            else:
                plan_type = (override.plan_type_override if override and override.plan_type_override else preview.plan_type)
                arn_code = next(
                    (s.arn_code for s in parse_result.schemes if s.folio == norm.folio and s.amc == norm.amc and s.name == norm.scheme_name),
                    None,
                )
                new_folio = Folio(
                    id=uuid.uuid4(), household_member_id=household_member_id, scheme_id=scheme.id,
                    folio_number=norm.folio, arn_code=arn_code, plan_type=PlanType(plan_type),
                )
                db.add(new_folio)
                db.flush()
                folio_cache[folio_key] = new_folio

        folio = folio_cache[folio_key]
        dup = (
            db.query(Transaction)
            .filter_by(folio_id=folio.id, date=norm.txn_date, amount=norm.amount, units=norm.units)
            .first()
        )
        if dup:
            skipped += 1
            continue

        db.add(
            Transaction(
                id=uuid.uuid4(), folio_id=folio.id, import_id=import_rec.id, type=norm.txn_type,
                date=norm.txn_date, amount=quantize_amount(norm.amount), units=norm.units, nav=norm.nav,
                raw_description=norm.description,
            )
        )
        added += 1

    import_rec.new_transactions_count = added
    import_rec.duplicate_transactions_count = skipped
    db.commit()

    del _preview_sessions[session_id]
    return ImportConfirmResponse(added=added, skipped=skipped, import_id=str(import_rec.id))


def _map_source_cas_type(file_type: str) -> SourceCasType | None:
    mapped = source_cas_type_from_file_type(file_type)
    return SourceCasType(mapped) if mapped else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/services/import_/test_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/import_/schemas.py backend/app/services/import_/service.py backend/tests/services/import_/test_service.py
git commit -m "feat(import): parse-preview and confirm orchestration against the real schema (FR-9-11)"
```

---

### Task 8: Wire the API routes

**Files:**
- Modify: `backend/app/api/imports.py`
- Create: `backend/tests/api/__init__.py`
- Create: `backend/tests/api/test_imports_routes.py`

**Interfaces:**
- Consumes: `parse_cas_pdf_bytes`, `ParseError` (Task 5), `build_import_preview`,
  `confirm_import` (Task 7), `app.db.session.get_db`.
- Produces: `POST /imports/parse`, `POST /imports/confirm` — the exact
  endpoint names PRD-01 FR-9/FR-10 specify.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/__init__.py
```
(empty)

```python
# backend/tests/api/test_imports_routes.py
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.import_.parser import ParseError

client = TestClient(app)


def test_parse_route_rejects_non_pdf():
    response = client.post(
        "/imports/parse",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"password": "x"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_file"


def test_parse_route_surfaces_parse_error_as_422():
    with patch(
        "app.api.imports.parse_cas_pdf_bytes",
        side_effect=ParseError("wrong_password", "Incorrect PDF password."),
    ):
        response = client.post(
            "/imports/parse",
            files={"file": ("cas.pdf", b"%PDF-fake", "application/pdf")},
            data={"password": "wrong"},
        )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "wrong_password"


def test_confirm_route_404s_on_unknown_session():
    response = client.post(
        "/imports/confirm",
        json={"session_id": "does-not-exist", "household_member_id": "00000000-0000-0000-0000-000000000000", "scheme_confirmations": []},
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/api/test_imports_routes.py -v`
Expected: FAIL — 404 for `/imports/parse` (route doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

`backend/app/api/imports.py`:
```python
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.import_.parser import ParseError, parse_cas_pdf_bytes
from app.services.import_.schemas import ImportConfirmRequest, ImportConfirmResponse, ImportPreviewResponse
from app.services.import_.service import build_import_preview, confirm_import

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/parse", response_model=ImportPreviewResponse)
async def parse_import(file: UploadFile = File(...), password: str = Form(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail={"code": "invalid_file", "message": "Please upload a PDF file."})

    pdf_bytes = await file.read()
    try:
        parse_result = parse_cas_pdf_bytes(pdf_bytes, password)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc

    return await build_import_preview(parse_result, file.filename)


@router.post("/confirm", response_model=ImportConfirmResponse)
def confirm_import_route(body: ImportConfirmRequest, db: Session = Depends(get_db)):
    try:
        household_member_id = uuid.UUID(body.household_member_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="household_member_id must be a valid UUID.") from exc

    try:
        return confirm_import(db, body.session_id, household_member_id, body.scheme_confirmations)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/api/test_imports_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/imports.py backend/tests/api
git commit -m "feat(import): wire POST /imports/parse and /imports/confirm routes"
```

---

### Task 9: No-PAN guard test, then retire the standalone prototype

**Files:**
- Create: `backend/tests/models/test_no_pan_field.py`
- Delete (with explicit confirmation before executing this step — see below): `CAS Parsers/mf-import/backend/`

**Interfaces:**
- Consumes: `app.models.reference.Scheme`, `app.models.folio.Folio`,
  `app.models.imports.Import`.

- [ ] **Step 1: Write the guard test**

```python
# backend/tests/models/test_no_pan_field.py
"""Guards the CLAUDE.md/ADR-004 non-negotiable: no PAN persistence, ever.

Confirms the Phase 1 Import Service port did not reintroduce the prototype's
pan_masked columns (CAS Parsers/mf-import/backend/app/models.py:56,66) onto
any of the models the Import Service writes to."""

from app.models.folio import Folio
from app.models.imports import Import
from app.models.reference import Scheme


def test_no_pan_shaped_column_on_import_related_models():
    for model in (Scheme, Folio, Import):
        for column_name in model.__table__.columns.keys():
            assert "pan" not in column_name.lower(), (
                f"{model.__name__}.{column_name} looks PAN-related — "
                "PAN must never be persisted (CLAUDE.md non-negotiable, ADR-004)."
            )
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/models/test_no_pan_field.py -v`
Expected: PASS immediately (the target schema never had a PAN column — this
locks that in as a regression guard, not a fix).

- [ ] **Step 3: Run the full backend suite to confirm no regressions**

Run: `.venv/bin/python -m pytest -m "not postgres" -v`
Expected: PASS — every test from Phase 0 plus every test added in Tasks 4–9.

- [ ] **Step 4: Commit the guard test**

```bash
git add backend/tests/models/test_no_pan_field.py
git commit -m "test(import): guard against reintroducing PAN persistence"
```

- [ ] **Step 5: Retire the standalone prototype — STOP and confirm with the user first**

This step deletes `CAS Parsers/mf-import/backend/` (its logic is now fully
ported and tested in `backend/app/services/import_/`; history is preserved
in commit `ed7c4ec` and every commit since). Per this project's standing
rule on destructive operations: **do not run this step without the user
explicitly confirming**, even though it was pre-approved in principle when
choosing "port into monolith" over "keep prototype standalone" earlier.
Show a `git status`/file count first, then on confirmation:

```bash
git rm -r "CAS Parsers/mf-import/backend"
git commit -m "chore(cas-parser): retire standalone prototype backend, fully ported to Import Service"
```

Leave `CAS Parsers/mf-import/frontend` and `CAS Parsers/Planning-V1.MD` in
place — the frontend prototype is a reference for the Phase 1b (new React
Import Review UI) plan, not something to delete here.

---

## Self-Review

**Spec coverage** — PRD-01 functional requirements, item by item:
- FR-1 (parse CAMS/KFintech, reject Summary) — already correct in the
  prototype, ported unchanged in Task 5.
- FR-2 (extract investor info, PAN masked/never persisted) — Task 5 (parser),
  enforced structurally in Task 7 (no Investor table/write path exists) and
  guarded by Task 9's test.
- FR-3 (canonical transaction-type mapping) — Task 5, tested.
- FR-4 (raw parser JSON on import record) — Task 7 (`Import.raw_parser_output`).
- FR-5, FR-6 (Direct/Regular classification, persisted per folio) — Task 1
  (logic), Task 7 (persisted to `Folio.plan_type`/`Scheme.plan_name_variant`).
- FR-7, FR-8 (ARN capture, per-folio not collapsed) — Task 2 (logic), Task 7
  (`Folio.arn_code`, keyed per folio so two folios of the same scheme via two
  distributors get separate rows — matches the Edge Cases table).
- FR-9, FR-10, FR-11 (preview no-write, confirm blocks low-confidence,
  added/skipped reporting) — Task 7.
- FR-12, FR-13, FR-14 (error messages) — already correct, Task 3 closes the
  test gap.
- Ongoing Data Addition (scope item, not a numbered FR) — the confirm/parse
  endpoints take `household_member_id` explicitly (no onboarding-only
  session state), so the same routes serve first-time and repeat imports —
  no separate "onboarding import" endpoint was built.

**Explicitly out of scope for this plan** (flagged, not silently dropped):
Import Review frontend (Phase 1b, separate plan once this API is stable),
ADR-001 correction (small standalone doc edit, not sequenced here — do
before or alongside Phase 1b since it's about the frontend claim), README
update for `CAS Parsers/mf-import` (moot once that directory is retired in
Task 9 — the monolith's own README/docs should describe Import Service setup
instead, out of scope here), distributor-analytics UI, MFCentral API,
NSDL/CDSL parsing (all explicit PRD-01 Non-Goals).

**Placeholder scan** — no TBD/"add later" in any task; every step has real,
verified code (casparser field names confirmed by installing and inspecting
the package directly, not guessed).

**Type/name consistency** — `TransactionType`, `PlanNameVariant`, `PlanType`,
`SourceCasType`, `ImportStatus` all imported from `app.models.enums`
consistently across Tasks 5–8; `ParseResult`/`ParsedScheme`/`NormalizedTransaction`
field names match between Task 5 (producer) and Task 7 (consumer); Task 7's
`SchemeConfirmation`/`ImportConfirmRequest` match what Task 8's route
deserializes.

## Open Items Flagged, Not Resolved Here

- **PRD-01's open question on KFintech fixtures**: no KFintech-format CAS
  fixture is available. This plan's tests use CAMS-shaped mocks only,
  consistent with PRD-01's own Risk mitigation ("ship CAMS-verified and flag
  KFintech as best-effort until a fixture arrives"). `casparser` handles
  both formats internally; nothing in this plan special-cases CAMS, but
  KFintech-specific field-naming quirks (if any) remain unverified against
  real data.
- **PRD-01's "100% accuracy" open question**: this plan builds to "100%
  surfaced, nothing silently wrong" (unclassified/low-confidence blocks
  confirm) per the PRD's own suggested redefinition — not revisited as a
  numeric target here since that's a product-definition question, not an
  engineering one.
- **ADR-001 correction** (frontend "already in progress" claim is stale) —
  small, independent doc edit; do it whenever, doesn't block this plan.
