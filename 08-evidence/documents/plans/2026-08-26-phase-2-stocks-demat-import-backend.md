# Phase 2 — Stocks/Demat Import (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept CDSL/NSDL demat Statement of Holdings uploads, normalize their equity/bond/demat-mode-MF contents, persist them as point-in-time snapshots, and refresh equity prices daily — the manual-upload half of Phase 2 (email auto-ingestion is a separate, later plan).

**Architecture:** A new, dedicated demat parse/preview/confirm pipeline that parallels the existing MF CAS pipeline (`parser.py` → `service.py` → `api/imports.py`) without touching it — new dataclasses in `parser.py`, a new `demat_service.py` + `demat_schemas.py` + `api/demat_imports.py`, new `DematAccount`/`EquityHolding`/`BondHolding`/`DematMutualFundHolding` tables (snapshot rows keyed by statement date, not a transaction ledger), and a `nav.py`-style on-demand equity price cache. The existing `/cas-imports` lifecycle flow (`lifecycle_service.py`) is untouched — it still rejects a demat CAS exactly as it does today (see Global Constraints).

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, `casparser==1.3.0`, Pydantic v2, pytest.

**Spec:** `Docs/superpowers/specs/2026-08-25-phase-2-stocks-demat-research.md` and `Docs/superpowers/specs/2026-08-25-phase-2-demat-integration-decision-memo.md` (no separate PRD-05 exists — see "Deviations from the source docs" below for what changed and why during planning).

## Global Constraints

- `Decimal`/`Numeric` only for every money/units/price value, matching the existing column precisions exactly: units/shares `Numeric(14, 3)`, amount/value `Numeric(14, 2)`, NAV/price `Numeric(10, 4)`. No `Float` anywhere.
- **Never persist PAN.** `DematOwner.PAN` (present on every demat account owner) must be redacted before `raw_json`/`raw_parser_output` is stored, exactly like the existing `Folio.PAN` redaction in `_normalize_cas_data`. No PAN column is added anywhere. (This reverses an assumption in the source research docs — see below.)
- **No fabricated cost basis.** Equities and bonds never get a computed/estimated gain, XIRR, or cost basis — the depository statement has none. Demat-mode mutual fund holdings are the one exception: when `casparser` finds `avg_cost`/`total_cost`/`pnl` actually printed in the source PDF, surface them as real parsed data (not estimated) — this is a scope nuance the source docs didn't call out; see below.
- **Lean on `casparser`'s built-in ISIN resolution.** `casparser==1.3.0` already backfills `Equity.symbol`/`Equity.exchange` and `MutualFund.amfi`/`MutualFund.type` from its own bundled `casparser_isin` package during parsing. Do not build a separate NSE/BSE bulk-refresh security-master table. When a field comes back `None`, flag the holding `unresolved_security = True` — no confidence score, no fuzzy matching, no silent guess.
- **No new EventBridge Scheduler code.** No such job exists yet for anything, including NAV (`ADR-Technical-Stack-Decisions.md`'s EventBridge Scheduler pattern is a decision record, not implemented infrastructure). The equity price refresh in Task 5 follows `nav.py`'s actual current pattern: on-demand fetch-and-cache, timestamped even on failure so an outage doesn't cause a re-fetch storm.
- Snapshot model, not a transaction ledger: `EquityHolding`/`BondHolding`/`DematMutualFundHolding` rows are keyed `(demat_account_id, isin, statement_date)`. Re-uploading the exact same statement is idempotent (unique constraint). A newer statement for the same account/ISIN inserts a new dated row rather than overwriting — "current holdings" is the latest `statement_date` per `(demat_account_id, isin)`, the same historical-table shape `nav_history` already uses for NAVs. Do **not** use the `OPENING_BALANCE` transaction type for equities — that was the source research doc's earlier suggestion, superseded by the later decision to use dedicated snapshot tables instead.
- This plan does not touch `lifecycle_service.py` or the `/cas-imports` API group at all. A demat CAS uploaded through that flow still hits today's `ParseError("demat_cas", ...)` unchanged, because that flow auto-commits on parse with no review step, and demat holdings need the `unresolved_security` review this plan's new flow provides. The new demat upload entry point is additive frontend/backend surface (Task 3 backend, covered in the paired frontend plan) — not a change to the existing "Add Import" flow.

### Deviations from the source docs (flag, don't silently resolve — confirmed with the user during planning)

1. **PAN persistence.** The decision memo says "no PAN persistence, ever" is "being rewritten" elsewhere. Nothing in the current codebase reflects that — `parser.py`'s docstring, `ADR-Technical-Stack-Decisions.md`, and `Database-Schema-Unifolio.md` all still state PAN is never persisted (ADR-004, non-negotiable), and no model anywhere has a PAN column. **Decided during planning: keep never-persisting PAN.** Revisit if/when that reversal actually lands in the schema.
2. **ISIN matching.** The source docs planned a custom NSE/BSE-bulk-refreshed security-master table with 0.98-confidence fuzzy matching (mirroring `enrich.py`'s AMFI scheme-match thresholds). `casparser==1.3.0` already does this resolution internally via its bundled `casparser_isin` package. **Decided during planning: lean on `casparser`, no custom security-master table** — only a binary `unresolved_security` flag for holdings it couldn't resolve.
3. **`scheme_universe.py` vs. `enrich.py`.** The source docs cite "`scheme_universe.py`'s AMFI `NAVAll.txt` handling" as the pattern for confidence-scored matching. These are two different modules: `scheme_universe.py` does a straight bulk-file fetch/cache with no matching logic at all; the actual fuzzy-match/confidence-threshold logic lives in `enrich.py`. Moot given deviation #2, but noted so nobody goes looking for thresholds in the wrong file.
4. **EventBridge Scheduler.** The source docs describe the equity price refresh as following "the same EventBridge Scheduler pattern already decided in ADR-006." No EventBridge code exists yet for anything — `nav.py` (the thing actually being mirrored) is on-demand fetch-and-cache. Task 5 mirrors what exists, not the aspirational future state.
5. **Cost basis scope.** The source docs' blanket "no cost basis for equities" is accurate for `Equity` (confirmed: `casparser`'s `Equity` model has no cost-basis field at all). It's not accurate for demat-mode `MutualFund` holdings, which do carry `avg_cost`/`total_cost`/`pnl` when the source PDF prints them. Task 3 surfaces these when present rather than nulling them out — real parsed data, not a fabrication, consistent with the "never silently guess, but never withhold real data either" convention already used elsewhere in this codebase.
6. **Dedupe key.** The source docs describe MF's dedupe key as "folio/scheme/date/amount/units." The actual key (`transactions` table's unique constraint and both `service.py`/`lifecycle_service.py`'s in-memory check) is `(folio_id, date, amount, units, type)` — `scheme` isn't a component (implied transitively through `folio_id`) and `type` is a component the docs omitted. Doesn't change this plan's design (the demat dedupe key is a different, snapshot-shaped concept per the bullet above), but corrected so nobody goes looking for a `scheme` column in a nonexistent composite key.
7. **NPS holdings.** `NSDLCASData.nps` (National Pension System holdings) is out of scope for this plan — not mentioned in the source docs, and NPS schemes carry no ISIN, a fundamentally different shape than equities/bonds/demat-MFs. Flagged, not silently dropped: Task 1's normalizer does not touch `data.nps` at all.

---

### Task 1: Parser — normalize demat CAS data

**Files:**
- Modify: `backend/app/services/import_/parser.py`
- Test: `backend/tests/services/import_/test_parser.py`

**Interfaces:**
- Consumes: `casparser.types.NSDLCASData`, `.DematAccount`, `.Equity`, `.Bond`, `.MutualFund`, `.DematOwner`, `.StatementPeriod`, `.InvestorInfo` (already installed, `casparser==1.3.0`); `mask_pan`, `to_decimal`, `quantize_amount`, `quantize_nav`, `quantize_units`, `ParseError`, `classify_parse_error` (already exist in `parser.py`).
- Produces: `DematParseResult` dataclass (`accounts: list[NormalizedDematAccount]`, `equities: list[NormalizedEquityHolding]`, `bonds: list[NormalizedBondHolding]`, `mutual_funds: list[NormalizedDematMutualFundHolding]`, `statement_date: date`, `investor_name: str | None`, `raw_json: str`, `parse_warnings: list[str]`) and `parse_demat_cas_pdf_bytes(pdf_bytes: bytes, password: str) -> DematParseResult` — both consumed by Task 3's `demat_service.py`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/services/import_/test_parser.py`:

```python
from casparser.enums import FileType
from casparser.types import (
    Bond as CasBond,
    DematAccount as CasDematAccount,
    DematOwner,
    Equity as CasEquity,
    InvestorInfo,
    MutualFund as CasMutualFund,
    NSDLCASData,
    StatementPeriod,
)

from app.services.import_.parser import _normalize_demat_cas_data, parse_demat_cas_pdf_bytes


def _demat_account(**overrides):
    defaults = dict(
        name="ABC Broking Ltd", type="NSDL Demat Account", dp_id="12345678", client_id="00012345",
        folios=1, balance=Decimal("150000.00"),
        owners=[DematOwner(name="Jane Doe", PAN="ABCDE1234F")],
        equities=[], mutual_funds=[], bonds=[],
    )
    defaults.update(overrides)
    return CasDematAccount(**defaults)


def _nsdl_data(accounts):
    return NSDLCASData(
        accounts=accounts,
        statement_period=StatementPeriod(**{"from": "2026-07-01", "to": "2026-07-31"}),
        investor_info=InvestorInfo(name="Jane Doe", email="jane@example.com", address="", mobile=""),
        file_type=FileType.NSDL,
        parse_warnings=[],
    )


def test_normalize_demat_cas_data_extracts_resolved_and_unresolved_equities():
    resolved = CasEquity(
        name="Reliance Industries", isin="INE002A01018", num_shares=Decimal("10"),
        price=Decimal("2500.50"), value=Decimal("25005.00"), symbol="RELIANCE", exchange="NSE",
    )
    unresolved = CasEquity(
        name="Unknown Corp", isin="INE999Z99999", num_shares=Decimal("5"),
        price=Decimal("100.00"), value=Decimal("500.00"), symbol=None, exchange=None,
    )
    account = _demat_account(equities=[resolved, unresolved])
    data = _nsdl_data([account])

    result = _normalize_demat_cas_data(data)

    assert len(result.equities) == 2
    resolved_out = next(e for e in result.equities if e.isin == "INE002A01018")
    assert resolved_out.symbol == "RELIANCE" and resolved_out.exchange == "NSE"
    assert resolved_out.unresolved_security is False
    unresolved_out = next(e for e in result.equities if e.isin == "INE999Z99999")
    assert unresolved_out.unresolved_security is True
    assert any("INE999Z99999" in w for w in result.parse_warnings)
    assert result.statement_date == date(2026, 7, 31)


def test_normalize_demat_cas_data_extracts_account_and_redacts_pan():
    account = _demat_account()
    data = _nsdl_data([account])

    result = _normalize_demat_cas_data(data)

    assert len(result.accounts) == 1
    normalized_account = result.accounts[0]
    assert normalized_account.depository == "nsdl"
    assert normalized_account.dp_id == "12345678"
    assert normalized_account.client_id == "00012345"
    assert normalized_account.owners[0].pan_masked == "A********F"
    assert "ABCDE1234F" not in result.raw_json


def test_normalize_demat_cas_data_skips_non_depository_account():
    mf_folios_account = CasDematAccount(
        name="Mutual Fund Folios", type="Mutual Fund Folios", dp_id="", client_id="",
        folios=3, balance=Decimal("50000.00"),
        owners=[DematOwner(name="Jane Doe", PAN="ABCDE1234F")],
        equities=[], mutual_funds=[], bonds=[],
    )
    data = _nsdl_data([mf_folios_account])

    result = _normalize_demat_cas_data(data)

    assert result.accounts == []
    assert any("Mutual Fund Folios" in w for w in result.parse_warnings)


def test_normalize_demat_cas_data_extracts_bonds():
    bond = CasBond(
        name="7.5% XYZ Corp Bond 2030", isin="INE123B07011", num_bonds=Decimal("10"),
        value=Decimal("102500.00"), face_value=Decimal("100000.00"),
        coupon_rate=Decimal("7.5"), market_price=Decimal("1025.00"),
    )
    account = _demat_account(bonds=[bond])
    data = _nsdl_data([account])

    result = _normalize_demat_cas_data(data)

    assert len(result.bonds) == 1
    assert result.bonds[0].isin == "INE123B07011"
    assert result.bonds[0].face_value == Decimal("100000.00")


def test_normalize_demat_cas_data_extracts_demat_mf_with_cost_basis_when_present():
    resolved_mf = CasMutualFund(
        name="HDFC Flexi Cap Fund", isin="INF179K01158", amfi="118834", type="EQUITY",
        balance=Decimal("100"), nav=Decimal("500.00"), value=Decimal("50000.00"),
        avg_cost=Decimal("450.00"), total_cost=Decimal("45000.00"), pnl=Decimal("5000.00"),
    )
    unresolved_mf = CasMutualFund(
        name="Unknown Fund", isin="INF999Z99999", amfi=None, type=None,
        balance=Decimal("10"), nav=Decimal("50.00"), value=Decimal("500.00"),
    )
    account = _demat_account(mutual_funds=[resolved_mf, unresolved_mf])
    data = _nsdl_data([account])

    result = _normalize_demat_cas_data(data)

    assert len(result.mutual_funds) == 2
    resolved_out = next(m for m in result.mutual_funds if m.isin == "INF179K01158")
    assert resolved_out.amfi_code == "118834"
    assert resolved_out.avg_cost == Decimal("450.0000")
    assert resolved_out.unresolved_security is False
    unresolved_out = next(m for m in result.mutual_funds if m.isin == "INF999Z99999")
    assert unresolved_out.unresolved_security is True
    assert unresolved_out.avg_cost is None


def test_parse_demat_cas_pdf_bytes_rejects_mf_cas(monkeypatch):
    from casparser.enums import CASFileType
    from casparser.enums import FileType as CasFileType
    from casparser.types import CASData

    mf_data = MagicMock(spec=CASData, cas_type=CASFileType.DETAILED, file_type=CasFileType.CAMS)
    monkeypatch.setattr("app.services.import_.parser.casparser.read_cas_pdf", lambda *a, **k: mf_data)

    try:
        parse_demat_cas_pdf_bytes(b"%PDF-fake", "password")
        assert False, "expected ParseError"
    except ParseError as exc:
        assert exc.code == "mf_cas"
```

Add these imports at the top of the test file alongside the existing ones: `from datetime import date` and `from app.services.import_.parser import ParseError`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/import_/test_parser.py -k "demat" -v`
Expected: FAIL with `ImportError: cannot import name '_normalize_demat_cas_data'` (and similarly for `parse_demat_cas_pdf_bytes`).

- [ ] **Step 3: Implement the dataclasses and `_normalize_demat_cas_data`**

Add to `backend/app/services/import_/parser.py`, after the existing `ParseResult` dataclass and before `class ParseError`:

```python
_DEMAT_TYPE_RE = re.compile(r"^(NSDL|CDSL)\s+Demat\s+Account$", re.IGNORECASE)


@dataclass
class NormalizedDematOwner:
    name: str
    pan_masked: str | None


@dataclass
class NormalizedDematAccount:
    account_key: str
    depository: str  # "nsdl" | "cdsl"
    dp_id: str
    client_id: str
    broker_name: str
    owners: list[NormalizedDematOwner]


@dataclass
class NormalizedEquityHolding:
    account_key: str
    isin: str
    name: str | None
    symbol: str | None
    exchange: str | None
    num_shares: Decimal
    price: Decimal
    value: Decimal
    unresolved_security: bool


@dataclass
class NormalizedBondHolding:
    account_key: str
    isin: str
    name: str | None
    num_bonds: Decimal
    value: Decimal
    face_value: Decimal | None
    coupon_rate: Decimal | None
    market_price: Decimal | None
    maturity_date: date | None


@dataclass
class NormalizedDematMutualFundHolding:
    account_key: str
    isin: str
    name: str | None
    amfi_code: str | None
    balance: Decimal
    nav: Decimal
    value: Decimal
    avg_cost: Decimal | None
    total_cost: Decimal | None
    pnl: Decimal | None
    unresolved_security: bool


@dataclass
class DematParseResult:
    accounts: list[NormalizedDematAccount]
    equities: list[NormalizedEquityHolding]
    bonds: list[NormalizedBondHolding]
    mutual_funds: list[NormalizedDematMutualFundHolding]
    statement_date: date
    investor_name: str | None
    raw_json: str
    parse_warnings: list[str] = field(default_factory=list)


def _account_key(dp_id: str, client_id: str) -> str:
    return f"{dp_id}:{client_id}"


def _normalize_demat_cas_data(data: NSDLCASData) -> DematParseResult:
    accounts: list[NormalizedDematAccount] = []
    equities: list[NormalizedEquityHolding] = []
    bonds: list[NormalizedBondHolding] = []
    mutual_funds: list[NormalizedDematMutualFundHolding] = []
    parse_warnings: list[str] = list(data.parse_warnings or [])

    for account in data.accounts:
        match = _DEMAT_TYPE_RE.match(account.type or "")
        if not match:
            # "Mutual Fund Folios" summary accounts (and any other
            # non-depository account type casparser emits) carry no
            # dp_id/client_id and aren't a real demat account -- skip
            # rather than fabricate a DematAccount row for one.
            parse_warnings.append(
                f"Skipped non-depository account '{account.name}' (type: {account.type!r})."
            )
            continue

        account_key = _account_key(account.dp_id or "", account.client_id or "")
        accounts.append(
            NormalizedDematAccount(
                account_key=account_key,
                depository=match.group(1).lower(),
                dp_id=account.dp_id or "",
                client_id=account.client_id or "",
                broker_name=account.name,
                owners=[
                    NormalizedDematOwner(name=owner.name, pan_masked=mask_pan(owner.PAN))
                    for owner in account.owners
                ],
            )
        )

        for eq in account.equities:
            unresolved = not eq.symbol or not eq.exchange
            if unresolved:
                parse_warnings.append(
                    f"Equity ISIN {eq.isin} ({eq.name or 'unknown name'}) could not be resolved "
                    "to a symbol/exchange -- flagged unresolved_security."
                )
            equities.append(
                NormalizedEquityHolding(
                    account_key=account_key, isin=eq.isin, name=eq.name,
                    symbol=eq.symbol, exchange=eq.exchange,
                    num_shares=quantize_units(to_decimal(eq.num_shares)),
                    price=quantize_nav(to_decimal(eq.price)),
                    value=quantize_amount(to_decimal(eq.value)),
                    unresolved_security=unresolved,
                )
            )

        for bond in account.bonds:
            bonds.append(
                NormalizedBondHolding(
                    account_key=account_key, isin=bond.isin, name=bond.name,
                    num_bonds=quantize_units(to_decimal(bond.num_bonds)),
                    value=quantize_amount(to_decimal(bond.value)),
                    face_value=quantize_amount(to_decimal(bond.face_value)) if bond.face_value is not None else None,
                    coupon_rate=to_decimal(bond.coupon_rate) if bond.coupon_rate is not None else None,
                    market_price=quantize_nav(to_decimal(bond.market_price)) if bond.market_price is not None else None,
                    maturity_date=_parse_date(bond.maturity_date) if bond.maturity_date else None,
                )
            )

        for mf in account.mutual_funds:
            unresolved = not mf.amfi
            if unresolved:
                parse_warnings.append(
                    f"Demat mutual fund ISIN {mf.isin} ({mf.name or 'unknown name'}) could not be "
                    "resolved to an AMFI code -- flagged unresolved_security."
                )
            mutual_funds.append(
                NormalizedDematMutualFundHolding(
                    account_key=account_key, isin=mf.isin, name=mf.name, amfi_code=mf.amfi,
                    balance=quantize_units(to_decimal(mf.balance)),
                    nav=quantize_nav(to_decimal(mf.nav)),
                    value=quantize_amount(to_decimal(mf.value)),
                    avg_cost=quantize_nav(to_decimal(mf.avg_cost)) if mf.avg_cost is not None else None,
                    total_cost=quantize_amount(to_decimal(mf.total_cost)) if mf.total_cost is not None else None,
                    pnl=quantize_amount(to_decimal(mf.pnl)) if mf.pnl is not None else None,
                    unresolved_security=unresolved,
                )
            )

    # Same redaction convention as _normalize_cas_data: PAN never leaves
    # this function unmasked, and raw_json is what confirm_demat_import
    # (Task 3) persists verbatim to imports.raw_parser_output.
    redacted = data.model_copy(deep=True)
    for account in redacted.accounts:
        for owner in account.owners:
            owner.PAN = None
    raw_json = redacted.model_dump_json()

    return DematParseResult(
        accounts=accounts, equities=equities, bonds=bonds, mutual_funds=mutual_funds,
        statement_date=_parse_date(data.statement_period.to),
        investor_name=data.investor_info.name if data.investor_info else None,
        raw_json=raw_json, parse_warnings=parse_warnings,
    )
```

Add `NSDLCASData` field access needs `data.statement_period.to` — already imported (`from casparser.types import CASData, NSDLCASData`, already present in `parser.py`; no new import needed there since `NSDLCASData` is already imported for the existing rejection check).

- [ ] **Step 4: Run tests to verify the normalizer tests pass**

Run: `cd backend && python -m pytest tests/services/import_/test_parser.py -k "demat" -v`
Expected: the 5 normalizer tests PASS; `test_parse_demat_cas_pdf_bytes_rejects_mf_cas` still FAILs (function not yet defined).

- [ ] **Step 5: Implement `parse_demat_cas_pdf_bytes`**

Add to `backend/app/services/import_/parser.py`, after `parse_cas_pdf_bytes`:

```python
def parse_demat_cas_pdf_bytes(pdf_bytes: bytes, password: str) -> DematParseResult:
    """Parse a CDSL/NSDL demat Statement of Holdings from bytes. Dedicated
    entry point, deliberately not reused by lifecycle_service.py's MF CAS
    flow -- that flow auto-commits on parse with no review step, and demat
    holdings need the unresolved_security review this entry point's
    caller (demat_service.py, Task 3) provides. A demat CAS uploaded
    through the MF flow still hits parse_cas_pdf_bytes's existing
    "demat_cas" ParseError above, unchanged."""
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

    if isinstance(result, CASData):
        raise ParseError(
            "mf_cas",
            "This looks like a mutual-fund CAS, not a CDSL/NSDL demat statement. "
            "Upload it from the Mutual Funds import screen instead.",
        )
    if not isinstance(result, NSDLCASData):
        raise ParseError("parse_failed", "Unexpected parser output type.")

    return _normalize_demat_cas_data(result)
```

- [ ] **Step 6: Run the full parser test file**

Run: `cd backend && python -m pytest tests/services/import_/test_parser.py -v`
Expected: all tests PASS, including the pre-existing MF ones (no regression).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/import_/parser.py backend/tests/services/import_/test_parser.py
git commit -m "feat(import): normalize CDSL/NSDL demat CAS equities, bonds, and demat-mode MFs"
```

---

### Task 2: Data model — demat accounts and holdings

**Files:**
- Modify: `backend/app/models/enums.py`
- Create: `backend/app/models/demat.py`
- Modify: `backend/app/models/reference.py` (add `EquityPriceHistory`)
- Create: `backend/alembic/versions/0010_demat_accounts_and_equity_holdings.py`
- Test: `backend/tests/models/test_demat_models.py`
- Modify: `backend/tests/test_migrations.py`

**Interfaces:**
- Consumes: `app.db.base.Base`, `enum_column` (from `app.models.enums`), the `Numeric`/`Uuid`/`ForeignKey`/`UniqueConstraint` SQLAlchemy 2.0 idiom already used by `folio.py`/`transaction.py`.
- Produces: `DepositoryType` enum; `DematAccount`, `EquityHolding`, `BondHolding`, `DematMutualFundHolding` ORM models (tables: `demat_accounts`, `equity_holdings`, `bond_holdings`, `demat_mutual_fund_holdings`); `EquityPriceHistory` ORM model (table: `equity_price_history`) — all consumed by Task 3 (`demat_service.py`), Task 4 (dashboard read endpoints), and Task 5 (price refresh job).

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/models/test_demat_models.py`:

```python
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.demat import BondHolding, DematAccount, DematMutualFundHolding, EquityHolding
from app.models.enums import DepositoryType, Relationship
from app.models.user import HouseholdMember, User


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _member(db):
    user = User(id=uuid.uuid4(), phone_number="+919999999999", created_at=datetime.now(timezone.utc))
    db.add(user)
    member = HouseholdMember(
        id=uuid.uuid4(), user_id=user.id, name="Self",
        relationship=Relationship.SELF, created_at=datetime.now(timezone.utc),
    )
    db.add(member)
    db.commit()
    return member


def test_demat_account_and_equity_holding_round_trip():
    db = _session()
    member = _member(db)

    account = DematAccount(
        id=uuid.uuid4(), household_member_id=member.id, depository=DepositoryType.NSDL,
        dp_id="12345678", client_id="00012345", broker_name="ABC Broking Ltd",
    )
    db.add(account)
    db.commit()

    holding = EquityHolding(
        id=uuid.uuid4(), demat_account_id=account.id, import_id=uuid.uuid4(),
        isin="INE002A01018", name="Reliance Industries", symbol="RELIANCE", exchange="NSE",
        num_shares=Decimal("10.000"), price=Decimal("2500.5000"), value=Decimal("25005.00"),
        statement_date=date(2026, 7, 31), unresolved_security=False,
    )
    db.add(holding)
    db.commit()

    fetched = db.query(EquityHolding).filter_by(isin="INE002A01018").one()
    assert fetched.demat_account_id == account.id
    assert fetched.num_shares == Decimal("10.000")


def test_equity_holding_unique_constraint_rejects_duplicate_statement():
    db = _session()
    member = _member(db)
    account = DematAccount(
        id=uuid.uuid4(), household_member_id=member.id, depository=DepositoryType.NSDL,
        dp_id="12345678", client_id="00012345", broker_name="ABC Broking Ltd",
    )
    db.add(account)
    db.commit()

    kwargs = dict(
        demat_account_id=account.id, import_id=uuid.uuid4(), isin="INE002A01018",
        name="Reliance Industries", num_shares=Decimal("10.000"), price=Decimal("2500.5000"),
        value=Decimal("25005.00"), statement_date=date(2026, 7, 31), unresolved_security=False,
    )
    db.add(EquityHolding(id=uuid.uuid4(), **kwargs))
    db.commit()
    db.add(EquityHolding(id=uuid.uuid4(), **kwargs))

    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        db.commit()


def test_bond_and_demat_mutual_fund_holding_round_trip():
    db = _session()
    member = _member(db)
    account = DematAccount(
        id=uuid.uuid4(), household_member_id=member.id, depository=DepositoryType.CDSL,
        dp_id="87654321", client_id="00098765", broker_name="XYZ Securities",
    )
    db.add(account)
    db.commit()

    db.add(BondHolding(
        id=uuid.uuid4(), demat_account_id=account.id, import_id=uuid.uuid4(),
        isin="INE123B07011", name="7.5% XYZ Corp Bond 2030", num_bonds=Decimal("10.000"),
        value=Decimal("102500.00"), face_value=Decimal("100000.00"), coupon_rate=Decimal("7.50"),
        market_price=Decimal("1025.0000"), statement_date=date(2026, 7, 31),
    ))
    db.add(DematMutualFundHolding(
        id=uuid.uuid4(), demat_account_id=account.id, import_id=uuid.uuid4(),
        isin="INF179K01158", name="HDFC Flexi Cap Fund", amfi_code="118834",
        balance=Decimal("100.000"), nav=Decimal("500.0000"), value=Decimal("50000.00"),
        avg_cost=Decimal("450.0000"), total_cost=Decimal("45000.00"), pnl=Decimal("5000.00"),
        unresolved_security=False, statement_date=date(2026, 7, 31),
    ))
    db.commit()

    assert db.query(BondHolding).filter_by(isin="INE123B07011").one().face_value == Decimal("100000.00")
    assert db.query(DematMutualFundHolding).filter_by(isin="INF179K01158").one().amfi_code == "118834"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/models/test_demat_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.demat'`.

- [ ] **Step 3: Add `DepositoryType` enum**

In `backend/app/models/enums.py`, add after `SourceCasType`:

```python
class DepositoryType(str, enum.Enum):
    NSDL = "nsdl"
    CDSL = "cdsl"
```

- [ ] **Step 4: Create the model file**

Create `backend/app/models/demat.py`:

```python
import uuid
from datetime import date as date_

from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DepositoryType, enum_column


class DematAccount(Base):
    """Mirrors Folio for the demat/equity side: one row per (household
    member, DP, client ID) combination a CDSL/NSDL statement identifies."""

    __tablename__ = "demat_accounts"
    __table_args__ = (
        UniqueConstraint("household_member_id", "dp_id", "client_id", name="uq_demat_account_member_dp_client"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    household_member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("household_members.id"), nullable=False)
    depository: Mapped[DepositoryType] = mapped_column(enum_column(DepositoryType), nullable=False)
    dp_id: Mapped[str] = mapped_column(String, nullable=False)
    client_id: Mapped[str] = mapped_column(String, nullable=False)
    broker_name: Mapped[str] = mapped_column(String, nullable=False)


class EquityHolding(Base):
    """Point-in-time snapshot, not a transaction ledger -- see Global
    Constraints. One row per (account, ISIN, statement_date); "current"
    holdings is the latest statement_date per (account, ISIN), the same
    shape nav_history already uses for NAV history."""

    __tablename__ = "equity_holdings"
    __table_args__ = (
        UniqueConstraint("demat_account_id", "isin", "statement_date", name="uq_equity_holding_account_isin_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    demat_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("demat_accounts.id"), nullable=False)
    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("imports.id"), nullable=False)
    isin: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    symbol: Mapped[str | None] = mapped_column(String)
    exchange: Mapped[str | None] = mapped_column(String)
    num_shares: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    statement_date: Mapped[date_] = mapped_column(Date, nullable=False)
    unresolved_security: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class BondHolding(Base):
    """Same snapshot shape as EquityHolding. No unresolved_security flag --
    bonds are identified by ISIN alone with no symbol/exchange to resolve."""

    __tablename__ = "bond_holdings"
    __table_args__ = (
        UniqueConstraint("demat_account_id", "isin", "statement_date", name="uq_bond_holding_account_isin_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    demat_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("demat_accounts.id"), nullable=False)
    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("imports.id"), nullable=False)
    isin: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    num_bonds: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    face_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    coupon_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    maturity_date: Mapped[date_ | None] = mapped_column(Date)
    statement_date: Mapped[date_] = mapped_column(Date, nullable=False)


class DematMutualFundHolding(Base):
    """Demat-mode MF holding from a CDSL/NSDL statement -- distinct from the
    RTA-sourced Folio/Transaction model. Carries avg_cost/total_cost/pnl
    when casparser found them printed in the source PDF (Global
    Constraints #3) -- never fabricated, only ever real parsed data."""

    __tablename__ = "demat_mutual_fund_holdings"
    __table_args__ = (
        UniqueConstraint(
            "demat_account_id", "isin", "statement_date",
            name="uq_demat_mf_holding_account_isin_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    demat_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("demat_accounts.id"), nullable=False)
    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("imports.id"), nullable=False)
    isin: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    amfi_code: Mapped[str | None] = mapped_column(String)
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    nav: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    avg_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    unresolved_security: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    statement_date: Mapped[date_] = mapped_column(Date, nullable=False)
```

- [ ] **Step 5: Add `EquityPriceHistory` to `reference.py`**

In `backend/app/models/reference.py`, add after `NavHistory` (needed by Task 5, added now to keep the migration in one place):

```python
class EquityPriceHistory(Base):
    """Daily EOD equity close price, keyed by ISIN -- the equity
    equivalent of NavHistory, same on-demand-fetch-and-cache shape (see
    Task 5, dashboard/equity_price.py)."""

    __tablename__ = "equity_price_history"

    isin: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[date_] = mapped_column(primary_key=True)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
```

(`date_`/`Decimal`/`Mapped`/`mapped_column`/`String`/`Numeric` are already imported at the top of `reference.py`.)

- [ ] **Step 6: Run test to verify it still fails (no migration yet, but model-only test uses `Base.metadata.create_all` so it should pass now)**

Run: `cd backend && python -m pytest tests/models/test_demat_models.py -v`
Expected: PASS (this test creates tables directly from `Base.metadata`, not via Alembic — Alembic parity is verified in Step 8).

- [ ] **Step 7: Write the migration**

Create `backend/alembic/versions/0010_demat_accounts_and_equity_holdings.py`:

```python
"""Demat accounts and equity/bond/demat-MF holding snapshots

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-26

Phase 2 stocks/demat import: CDSL/NSDL Statement of Holdings upload. Point-
in-time snapshot tables, not a transaction ledger -- see the backend plan's
Global Constraints for why OPENING_BALANCE wasn't reused instead.
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demat_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_member_id", sa.Uuid(), nullable=False),
        sa.Column("depository", sa.Enum("nsdl", "cdsl", name="depositorytype"), nullable=False),
        sa.Column("dp_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("broker_name", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["household_member_id"], ["household_members.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_member_id", "dp_id", "client_id", name="uq_demat_account_member_dp_client"),
    )

    op.create_table(
        "equity_holdings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("demat_account_id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("isin", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("exchange", sa.String(), nullable=True),
        sa.Column("num_shares", sa.Numeric(14, 3), nullable=False),
        sa.Column("price", sa.Numeric(14, 4), nullable=False),
        sa.Column("value", sa.Numeric(14, 2), nullable=False),
        sa.Column("statement_date", sa.Date(), nullable=False),
        sa.Column("unresolved_security", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["demat_account_id"], ["demat_accounts.id"]),
        sa.ForeignKeyConstraint(["import_id"], ["imports.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("demat_account_id", "isin", "statement_date", name="uq_equity_holding_account_isin_date"),
    )

    op.create_table(
        "bond_holdings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("demat_account_id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("isin", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("num_bonds", sa.Numeric(14, 3), nullable=False),
        sa.Column("value", sa.Numeric(14, 2), nullable=False),
        sa.Column("face_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("coupon_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("market_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("statement_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["demat_account_id"], ["demat_accounts.id"]),
        sa.ForeignKeyConstraint(["import_id"], ["imports.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("demat_account_id", "isin", "statement_date", name="uq_bond_holding_account_isin_date"),
    )

    op.create_table(
        "demat_mutual_fund_holdings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("demat_account_id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("isin", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("amfi_code", sa.String(), nullable=True),
        sa.Column("balance", sa.Numeric(14, 3), nullable=False),
        sa.Column("nav", sa.Numeric(10, 4), nullable=False),
        sa.Column("value", sa.Numeric(14, 2), nullable=False),
        sa.Column("avg_cost", sa.Numeric(10, 4), nullable=True),
        sa.Column("total_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("pnl", sa.Numeric(14, 2), nullable=True),
        sa.Column("unresolved_security", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("statement_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["demat_account_id"], ["demat_accounts.id"]),
        sa.ForeignKeyConstraint(["import_id"], ["imports.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "demat_account_id", "isin", "statement_date", name="uq_demat_mf_holding_account_isin_date"
        ),
    )

    op.create_table(
        "equity_price_history",
        sa.Column("isin", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(14, 4), nullable=False),
        sa.PrimaryKeyConstraint("isin", "date"),
    )


def downgrade() -> None:
    op.drop_table("equity_price_history")
    op.drop_table("demat_mutual_fund_holdings")
    op.drop_table("bond_holdings")
    op.drop_table("equity_holdings")
    op.drop_table("demat_accounts")
```

- [ ] **Step 8: Extend the migration test**

In `backend/tests/test_migrations.py`, add `"demat_accounts", "equity_holdings", "bond_holdings", "demat_mutual_fund_holdings", "equity_price_history"` to the `expected` set in `test_alembic_upgrade_creates_all_tables`.

- [ ] **Step 9: Run migration tests**

Run: `cd backend && python -m pytest tests/test_migrations.py tests/models/test_demat_models.py -v`
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/demat.py backend/app/models/reference.py \
        backend/alembic/versions/0010_demat_accounts_and_equity_holdings.py \
        backend/tests/models/test_demat_models.py backend/tests/test_migrations.py
git commit -m "feat(models): add demat account, equity/bond/demat-MF holding, and equity price tables"
```

---

### Task 3: Demat import preview/confirm service and API routes

**Files:**
- Create: `backend/app/services/import_/demat_schemas.py`
- Create: `backend/app/services/import_/demat_service.py`
- Create: `backend/app/api/demat_imports.py`
- Modify: `backend/app/main.py` (register the new router)
- Test: `backend/tests/services/import_/test_demat_service.py`
- Test: `backend/tests/api/test_demat_imports_routes.py`

**Interfaces:**
- Consumes: `DematParseResult` and friends from Task 1 (`parser.py`); `DematAccount`/`EquityHolding`/`BondHolding`/`DematMutualFundHolding` from Task 2 (`app.models.demat`); `get_household_member_for_user` (existing, `app.services.dashboard.household_members`); `invalidate_holdings_cache` (existing, `app.services.dashboard.holdings`).
- Produces: `build_demat_import_preview(parse_result: DematParseResult, filename: str) -> DematImportPreviewResponse` (session-based, mirrors `build_import_preview`), `confirm_demat_import(db: Session, session_id: str, household_member_id: uuid.UUID) -> DematImportConfirmResponse` — consumed by the paired frontend plan's API client and by the two new routes below.

- [ ] **Step 1: Write the failing schema/service tests**

Create `backend/tests/services/import_/test_demat_service.py`:

```python
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.demat import BondHolding, DematAccount, DematMutualFundHolding, EquityHolding
from app.models.imports import Import
from app.services.import_.demat_service import build_demat_import_preview, confirm_demat_import
from app.services.import_.parser import (
    DematParseResult,
    NormalizedBondHolding,
    NormalizedDematAccount,
    NormalizedDematMutualFundHolding,
    NormalizedDematOwner,
    NormalizedEquityHolding,
)


def _sample_parse_result(unresolved: bool = False) -> DematParseResult:
    account = NormalizedDematAccount(
        account_key="12345678:00012345", depository="nsdl", dp_id="12345678",
        client_id="00012345", broker_name="ABC Broking Ltd",
        owners=[NormalizedDematOwner(name="Jane Doe", pan_masked="A********F")],
    )
    equity = NormalizedEquityHolding(
        account_key="12345678:00012345", isin="INE002A01018", name="Reliance Industries",
        symbol=None if unresolved else "RELIANCE", exchange=None if unresolved else "NSE",
        num_shares=Decimal("10.000"), price=Decimal("2500.5000"), value=Decimal("25005.00"),
        unresolved_security=unresolved,
    )
    return DematParseResult(
        accounts=[account], equities=[equity], bonds=[], mutual_funds=[],
        statement_date=date(2026, 7, 31), investor_name="Jane Doe",
        raw_json="{}", parse_warnings=[],
    )


@pytest.mark.asyncio
async def test_build_demat_import_preview_flags_unresolved_equity():
    preview = await build_demat_import_preview(_sample_parse_result(unresolved=True), "statement.pdf")

    assert preview.filename == "statement.pdf"
    assert len(preview.equities) == 1
    assert preview.equities[0].unresolved_security is True
    assert preview.accounts[0].dp_id == "12345678"


@pytest.mark.asyncio
async def test_confirm_demat_import_persists_account_and_equity_snapshot(db_session):
    from app.models.enums import Relationship
    from app.models.user import HouseholdMember, User

    user = User(id=uuid.uuid4(), phone_number="+919999999999", created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    db_session.add(user)
    member = HouseholdMember(
        id=uuid.uuid4(), user_id=user.id, name="Self",
        relationship=Relationship.SELF, created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    db_session.add(member)
    db_session.commit()

    preview = await build_demat_import_preview(_sample_parse_result(), "statement.pdf")
    response = confirm_demat_import(db_session, preview.session_id, member.id)

    assert response.equities_added == 1
    assert response.bonds_added == 0
    assert response.mutual_funds_added == 0

    account = db_session.query(DematAccount).filter_by(dp_id="12345678").one()
    holding = db_session.query(EquityHolding).filter_by(demat_account_id=account.id).one()
    assert holding.isin == "INE002A01018"
    assert holding.statement_date == date(2026, 7, 31)

    import_rec = db_session.query(Import).filter_by(id=uuid.UUID(response.import_id)).one()
    assert "ABCDE1234F" not in (str(import_rec.raw_parser_output) if import_rec.raw_parser_output else "")


@pytest.mark.asyncio
async def test_confirm_demat_import_is_idempotent_on_reupload(db_session):
    from app.models.enums import Relationship
    from app.models.user import HouseholdMember, User
    from datetime import datetime, timezone

    user = User(id=uuid.uuid4(), phone_number="+919999999999", created_at=datetime.now(timezone.utc))
    db_session.add(user)
    member = HouseholdMember(
        id=uuid.uuid4(), user_id=user.id, name="Self",
        relationship=Relationship.SELF, created_at=datetime.now(timezone.utc),
    )
    db_session.add(member)
    db_session.commit()

    preview1 = await build_demat_import_preview(_sample_parse_result(), "statement.pdf")
    confirm_demat_import(db_session, preview1.session_id, member.id)

    preview2 = await build_demat_import_preview(_sample_parse_result(), "statement.pdf")
    response2 = confirm_demat_import(db_session, preview2.session_id, member.id)

    assert response2.equities_added == 0
    assert response2.equities_skipped == 1
    assert db_session.query(EquityHolding).count() == 1
```

`db_session` is the existing fixture in `backend/tests/conftest.py`. This test module needs `pytest-asyncio`'s `@pytest.mark.asyncio` marker — already used elsewhere in this test suite (`grep -rl "pytest.mark.asyncio" backend/tests` to confirm the convention before writing, and match whatever marker/config style those files use).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/import_/test_demat_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.import_.demat_service'`.

- [ ] **Step 3: Write the schemas**

Create `backend/app/services/import_/demat_schemas.py`:

```python
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class DematAccountPreview(BaseModel):
    account_key: str
    depository: str
    dp_id: str
    client_id: str
    broker_name: str
    owner_names: list[str]


class EquityHoldingPreview(BaseModel):
    account_key: str
    isin: str
    name: str | None
    symbol: str | None
    exchange: str | None
    num_shares: str
    price: str
    value: str
    unresolved_security: bool


class BondHoldingPreview(BaseModel):
    account_key: str
    isin: str
    name: str | None
    num_bonds: str
    value: str
    face_value: str | None
    coupon_rate: str | None
    market_price: str | None
    maturity_date: str | None


class DematMutualFundHoldingPreview(BaseModel):
    account_key: str
    isin: str
    name: str | None
    amfi_code: str | None
    balance: str
    nav: str
    value: str
    avg_cost: str | None
    total_cost: str | None
    pnl: str | None
    unresolved_security: bool


class DematImportPreviewResponse(BaseModel):
    session_id: str
    filename: str
    investor_name: str | None
    statement_date: date
    accounts: list[DematAccountPreview]
    equities: list[EquityHoldingPreview]
    bonds: list[BondHoldingPreview]
    mutual_funds: list[DematMutualFundHoldingPreview]
    parse_warnings: list[str]
    unresolved_count: int


class DematImportConfirmRequest(BaseModel):
    session_id: str
    household_member_id: str


class DematImportConfirmResponse(BaseModel):
    equities_added: int
    equities_skipped: int
    bonds_added: int
    bonds_skipped: int
    mutual_funds_added: int
    mutual_funds_skipped: int
    import_id: str
```

- [ ] **Step 4: Write the service**

Create `backend/app/services/import_/demat_service.py`:

```python
"""Demat Import Service orchestration: parse preview (no DB writes) and
confirm (persists) -- parallel to service.py's MF flow, deliberately not
sharing its session store or lifecycle_service.py's auto-commit path (see
the backend plan's Global Constraints)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.demat import BondHolding, DematAccount, DematMutualFundHolding, EquityHolding
from app.models.enums import DepositoryType
from app.models.imports import Import, ImportStatus
from app.services.dashboard.holdings import invalidate_holdings_cache
from app.services.import_.demat_schemas import (
    BondHoldingPreview,
    DematAccountPreview,
    DematImportConfirmResponse,
    DematImportPreviewResponse,
    DematMutualFundHoldingPreview,
    EquityHoldingPreview,
)
from app.services.import_.parser import DematParseResult

_preview_sessions: dict[str, dict[str, Any]] = {}
SESSION_TTL_MINUTES = 60


def _sweep_expired_sessions(ttl_minutes: int = SESSION_TTL_MINUTES) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
    expired = [sid for sid, s in _preview_sessions.items() if s["created_at"] < cutoff]
    for sid in expired:
        del _preview_sessions[sid]


async def build_demat_import_preview(parse_result: DematParseResult, filename: str) -> DematImportPreviewResponse:
    _sweep_expired_sessions()
    session_id = uuid.uuid4().hex

    _preview_sessions[session_id] = {
        "created_at": datetime.now(timezone.utc),
        "filename": filename,
        "parse_result": parse_result,
    }

    unresolved_count = sum(1 for e in parse_result.equities if e.unresolved_security) + sum(
        1 for m in parse_result.mutual_funds if m.unresolved_security
    )

    return DematImportPreviewResponse(
        session_id=session_id, filename=filename, investor_name=parse_result.investor_name,
        statement_date=parse_result.statement_date,
        accounts=[
            DematAccountPreview(
                account_key=a.account_key, depository=a.depository, dp_id=a.dp_id, client_id=a.client_id,
                broker_name=a.broker_name, owner_names=[o.name for o in a.owners],
            )
            for a in parse_result.accounts
        ],
        equities=[
            EquityHoldingPreview(
                account_key=e.account_key, isin=e.isin, name=e.name, symbol=e.symbol, exchange=e.exchange,
                num_shares=str(e.num_shares), price=str(e.price), value=str(e.value),
                unresolved_security=e.unresolved_security,
            )
            for e in parse_result.equities
        ],
        bonds=[
            BondHoldingPreview(
                account_key=b.account_key, isin=b.isin, name=b.name, num_bonds=str(b.num_bonds),
                value=str(b.value), face_value=str(b.face_value) if b.face_value is not None else None,
                coupon_rate=str(b.coupon_rate) if b.coupon_rate is not None else None,
                market_price=str(b.market_price) if b.market_price is not None else None,
                maturity_date=b.maturity_date.isoformat() if b.maturity_date else None,
            )
            for b in parse_result.bonds
        ],
        mutual_funds=[
            DematMutualFundHoldingPreview(
                account_key=m.account_key, isin=m.isin, name=m.name, amfi_code=m.amfi_code,
                balance=str(m.balance), nav=str(m.nav), value=str(m.value),
                avg_cost=str(m.avg_cost) if m.avg_cost is not None else None,
                total_cost=str(m.total_cost) if m.total_cost is not None else None,
                pnl=str(m.pnl) if m.pnl is not None else None,
                unresolved_security=m.unresolved_security,
            )
            for m in parse_result.mutual_funds
        ],
        parse_warnings=parse_result.parse_warnings,
        unresolved_count=unresolved_count,
    )


def confirm_demat_import(
    db: Session, session_id: str, household_member_id: uuid.UUID
) -> DematImportConfirmResponse:
    session = _preview_sessions.get(session_id)
    if not session:
        raise ValueError("Demat import session not found or expired.")

    parse_result: DematParseResult = session["parse_result"]

    import_rec = Import(
        id=uuid.uuid4(), household_member_id=household_member_id, status=ImportStatus.CONFIRMED,
        raw_parser_output=json.loads(parse_result.raw_json),
        uploaded_at=datetime.now(timezone.utc), confirmed_at=datetime.now(timezone.utc),
    )
    db.add(import_rec)
    db.flush()

    account_cache: dict[str, DematAccount] = {}
    for acc in parse_result.accounts:
        existing = (
            db.query(DematAccount)
            .filter_by(household_member_id=household_member_id, dp_id=acc.dp_id, client_id=acc.client_id)
            .first()
        )
        if existing:
            account_cache[acc.account_key] = existing
        else:
            new_account = DematAccount(
                id=uuid.uuid4(), household_member_id=household_member_id,
                depository=DepositoryType(acc.depository), dp_id=acc.dp_id, client_id=acc.client_id,
                broker_name=acc.broker_name,
            )
            db.add(new_account)
            db.flush()
            account_cache[acc.account_key] = new_account

    equities_added = equities_skipped = 0
    for eq in parse_result.equities:
        account = account_cache[eq.account_key]
        dup = (
            db.query(EquityHolding)
            .filter_by(demat_account_id=account.id, isin=eq.isin, statement_date=parse_result.statement_date)
            .first()
        )
        if dup:
            equities_skipped += 1
            continue
        db.add(EquityHolding(
            id=uuid.uuid4(), demat_account_id=account.id, import_id=import_rec.id, isin=eq.isin,
            name=eq.name, symbol=eq.symbol, exchange=eq.exchange, num_shares=eq.num_shares,
            price=eq.price, value=eq.value, statement_date=parse_result.statement_date,
            unresolved_security=eq.unresolved_security,
        ))
        equities_added += 1

    bonds_added = bonds_skipped = 0
    for bond in parse_result.bonds:
        account = account_cache[bond.account_key]
        dup = (
            db.query(BondHolding)
            .filter_by(demat_account_id=account.id, isin=bond.isin, statement_date=parse_result.statement_date)
            .first()
        )
        if dup:
            bonds_skipped += 1
            continue
        db.add(BondHolding(
            id=uuid.uuid4(), demat_account_id=account.id, import_id=import_rec.id, isin=bond.isin,
            name=bond.name, num_bonds=bond.num_bonds, value=bond.value, face_value=bond.face_value,
            coupon_rate=bond.coupon_rate, market_price=bond.market_price, maturity_date=bond.maturity_date,
            statement_date=parse_result.statement_date,
        ))
        bonds_added += 1

    mutual_funds_added = mutual_funds_skipped = 0
    for mf in parse_result.mutual_funds:
        account = account_cache[mf.account_key]
        dup = (
            db.query(DematMutualFundHolding)
            .filter_by(demat_account_id=account.id, isin=mf.isin, statement_date=parse_result.statement_date)
            .first()
        )
        if dup:
            mutual_funds_skipped += 1
            continue
        db.add(DematMutualFundHolding(
            id=uuid.uuid4(), demat_account_id=account.id, import_id=import_rec.id, isin=mf.isin,
            name=mf.name, amfi_code=mf.amfi_code, balance=mf.balance, nav=mf.nav, value=mf.value,
            avg_cost=mf.avg_cost, total_cost=mf.total_cost, pnl=mf.pnl,
            unresolved_security=mf.unresolved_security, statement_date=parse_result.statement_date,
        ))
        mutual_funds_added += 1

    db.commit()
    invalidate_holdings_cache(household_member_id)
    del _preview_sessions[session_id]

    return DematImportConfirmResponse(
        equities_added=equities_added, equities_skipped=equities_skipped,
        bonds_added=bonds_added, bonds_skipped=bonds_skipped,
        mutual_funds_added=mutual_funds_added, mutual_funds_skipped=mutual_funds_skipped,
        import_id=str(import_rec.id),
    )
```

- [ ] **Step 5: Run service tests**

Run: `cd backend && python -m pytest tests/services/import_/test_demat_service.py -v`
Expected: PASS.

- [ ] **Step 6: Write the failing API route test**

Create `backend/tests/api/test_demat_imports_routes.py` — check `backend/tests/api/test_imports_routes.py` first for this repo's exact auth-header/fixture convention (how `get_current_user` is overridden or a real token is minted in tests) and mirror it exactly rather than guessing; then write tests for:
- `POST /demat-imports/parse` with a non-PDF file returns 400.
- `POST /demat-imports/parse` with a valid demat PDF+password returns a `DematImportPreviewResponse`-shaped body (mock `parse_demat_cas_pdf_bytes` the same way `test_imports_routes.py` mocks `parse_cas_pdf_bytes`).
- `POST /demat-imports/confirm` with a `household_member_id` the authenticated user doesn't own returns 404 (mirroring the ownership gate in `confirm_import_route`).
- `POST /demat-imports/confirm` with a valid session returns a `DematImportConfirmResponse`.

- [ ] **Step 7: Run route tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_demat_imports_routes.py -v`
Expected: FAIL (route module doesn't exist).

- [ ] **Step 8: Write the API routes**

Create `backend/app/api/demat_imports.py`:

```python
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.services.auth.session import get_current_user
from app.services.dashboard.household_members import get_household_member_for_user
from app.services.import_.demat_schemas import (
    DematImportConfirmRequest,
    DematImportConfirmResponse,
    DematImportPreviewResponse,
)
from app.services.import_.demat_service import build_demat_import_preview, confirm_demat_import
from app.services.import_.parser import ParseError, parse_demat_cas_pdf_bytes

router = APIRouter(prefix="/demat-imports", tags=["demat-imports"])
logger = logging.getLogger(__name__)


@router.post("/parse", response_model=DematImportPreviewResponse)
async def parse_demat_import(
    file: UploadFile = File(...),
    password: str = Form(...),
    user: User = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail={"code": "invalid_file", "message": "Please upload a PDF file."})

    pdf_bytes = await file.read()
    try:
        parse_result = parse_demat_cas_pdf_bytes(pdf_bytes, password)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc

    return await build_demat_import_preview(parse_result, file.filename)


@router.post("/confirm", response_model=DematImportConfirmResponse)
def confirm_demat_import_route(
    body: DematImportConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        household_member_id = uuid.UUID(body.household_member_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="household_member_id must be a valid UUID.") from exc

    if get_household_member_for_user(db, user.id, household_member_id) is None:
        raise HTTPException(status_code=404, detail="Household member not found.")

    try:
        return confirm_demat_import(db, body.session_id, household_member_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 9: Register the router**

In `backend/app/main.py`, add the import alongside the existing route module imports and register it after `app.include_router(imports.router)`:

```python
from app.api import demat_imports
...
app.include_router(demat_imports.router)
```

- [ ] **Step 10: Run all Task 3 tests**

Run: `cd backend && python -m pytest tests/services/import_/test_demat_service.py tests/api/test_demat_imports_routes.py -v`
Expected: all PASS.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/import_/demat_schemas.py backend/app/services/import_/demat_service.py \
        backend/app/api/demat_imports.py backend/app/main.py \
        backend/tests/services/import_/test_demat_service.py backend/tests/api/test_demat_imports_routes.py
git commit -m "feat(import): add demat import preview/confirm service and API routes"
```

---

### Task 4: Dashboard read integration — equity holdings and allocation

**Files:**
- Create: `backend/app/services/dashboard/equity_holdings.py`
- Modify: `backend/app/services/dashboard/schemas.py` (add `EquityHoldingRow`)
- Modify: `backend/app/services/dashboard/allocation.py` (add a "Stocks" bucket)
- Modify: `backend/app/api/dashboard.py` (add `GET /household-members/{member_id}/equity-holdings`)
- Test: `backend/tests/services/dashboard/test_equity_holdings.py`
- Test: `backend/tests/services/dashboard/test_allocation.py` (extend existing, if present — check first)

**Interfaces:**
- Consumes: `EquityHolding` (Task 2); `compute_allocation`'s existing `compute_holdings` call and `_asset_class_bucket` helper (`allocation.py`).
- Produces: `EquityHoldingRow` schema, `compute_equity_holdings(db: Session, household_member_ids: list[uuid.UUID]) -> list[EquityHoldingRow]` — consumed by the paired frontend plan's Stocks holdings table.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/dashboard/test_equity_holdings.py`:

```python
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models.demat import DematAccount, EquityHolding
from app.models.enums import DepositoryType, Relationship
from app.models.imports import Import, ImportStatus
from app.models.user import HouseholdMember, User
from app.services.dashboard.equity_holdings import compute_equity_holdings


@pytest.mark.asyncio
async def test_compute_equity_holdings_returns_latest_statement_only(db_session):
    user = User(id=uuid.uuid4(), phone_number="+919999999999", created_at=datetime.now(timezone.utc))
    db_session.add(user)
    member = HouseholdMember(
        id=uuid.uuid4(), user_id=user.id, name="Self",
        relationship=Relationship.SELF, created_at=datetime.now(timezone.utc),
    )
    db_session.add(member)
    account = DematAccount(
        id=uuid.uuid4(), household_member_id=member.id, depository=DepositoryType.NSDL,
        dp_id="12345678", client_id="00012345", broker_name="ABC Broking Ltd",
    )
    db_session.add(account)
    import_rec = Import(
        id=uuid.uuid4(), household_member_id=member.id, status=ImportStatus.CONFIRMED,
        uploaded_at=datetime.now(timezone.utc),
    )
    db_session.add(import_rec)
    db_session.commit()

    older = EquityHolding(
        id=uuid.uuid4(), demat_account_id=account.id, import_id=import_rec.id, isin="INE002A01018",
        name="Reliance Industries", symbol="RELIANCE", exchange="NSE",
        num_shares=Decimal("8.000"), price=Decimal("2400.0000"), value=Decimal("19200.00"),
        statement_date=date(2026, 6, 30), unresolved_security=False,
    )
    newer = EquityHolding(
        id=uuid.uuid4(), demat_account_id=account.id, import_id=import_rec.id, isin="INE002A01018",
        name="Reliance Industries", symbol="RELIANCE", exchange="NSE",
        num_shares=Decimal("10.000"), price=Decimal("2500.5000"), value=Decimal("25005.00"),
        statement_date=date(2026, 7, 31), unresolved_security=False,
    )
    db_session.add_all([older, newer])
    db_session.commit()

    rows = await compute_equity_holdings(db_session, [member.id])

    assert len(rows) == 1
    assert rows[0].num_shares == "10.000"
    assert rows[0].statement_date == date(2026, 7, 31)
    assert rows[0].cost_basis_available is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/dashboard/test_equity_holdings.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Add `EquityHoldingRow` schema**

In `backend/app/services/dashboard/schemas.py`, add after `HoldingRow`:

```python
class EquityHoldingRow(BaseModel):
    demat_account_id: str
    household_member_id: str
    household_member_name: str
    isin: str
    name: str | None
    symbol: str | None
    exchange: str | None
    num_shares: str
    price: str
    current_value: str
    statement_date: date
    unresolved_security: bool
    cost_basis_available: bool  # always False today -- Global Constraints #2
```

- [ ] **Step 4: Implement `compute_equity_holdings`**

Create `backend/app/services/dashboard/equity_holdings.py`:

```python
"""Equity holdings for the dashboard's Stocks section -- latest statement
snapshot per (demat account, ISIN), same "no fabricated cost basis" rule
as the rest of the equities feature (see the backend plan's Global
Constraints)."""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.demat import DematAccount, EquityHolding
from app.models.user import HouseholdMember
from app.services.dashboard.schemas import EquityHoldingRow


async def compute_equity_holdings(db: Session, household_member_ids: list[uuid.UUID]) -> list[EquityHoldingRow]:
    if not household_member_ids:
        return []

    accounts = {
        a.id: a
        for a in db.query(DematAccount).filter(DematAccount.household_member_id.in_(household_member_ids)).all()
    }
    if not accounts:
        return []

    members = {m.id: m for m in db.query(HouseholdMember).filter(HouseholdMember.id.in_(household_member_ids)).all()}

    latest_dates = {
        (demat_account_id, isin): max_date
        for demat_account_id, isin, max_date in (
            db.query(EquityHolding.demat_account_id, EquityHolding.isin, func.max(EquityHolding.statement_date))
            .filter(EquityHolding.demat_account_id.in_(accounts.keys()))
            .group_by(EquityHolding.demat_account_id, EquityHolding.isin)
            .all()
        )
    }

    holdings = (
        db.query(EquityHolding)
        .filter(EquityHolding.demat_account_id.in_(accounts.keys()))
        .all()
    )

    rows: list[EquityHoldingRow] = []
    for holding in holdings:
        if latest_dates.get((holding.demat_account_id, holding.isin)) != holding.statement_date:
            continue
        account = accounts[holding.demat_account_id]
        member = members[account.household_member_id]
        rows.append(EquityHoldingRow(
            demat_account_id=str(account.id), household_member_id=str(member.id),
            household_member_name=member.name, isin=holding.isin, name=holding.name,
            symbol=holding.symbol, exchange=holding.exchange, num_shares=str(holding.num_shares),
            price=str(holding.price), current_value=str(holding.value),
            statement_date=holding.statement_date, unresolved_security=holding.unresolved_security,
            cost_basis_available=False,
        ))
    return rows
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/dashboard/test_equity_holdings.py -v`
Expected: PASS.

- [ ] **Step 6: Add the "Stocks" allocation bucket**

First check whether `backend/tests/services/dashboard/test_allocation.py` exists and read it to match its exact style before adding a test case; then add a test asserting that when equity holdings exist for a member, `compute_allocation`'s `by_asset_class` includes a `"Stocks"` bucket whose `current_value` equals the sum of that member's latest-snapshot equity values, and that `total_value` includes it too.

Modify `backend/app/services/dashboard/allocation.py`:

```python
from app.services.dashboard.equity_holdings import compute_equity_holdings
```

In `compute_allocation`, after the existing `by_class`/`by_amc` accumulation loop and before `total_value` is finalized:

```python
    equity_holdings = await compute_equity_holdings(db, household_member_ids)
    equity_total = sum((Decimal(h.current_value) for h in equity_holdings), Decimal("0"))
    if equity_total:
        by_class["Stocks"] += equity_total
    total_value = total_value + equity_total
```

(Move the `total_value = sum(...)` line for fund holdings above this block if it isn't already computed before `by_class` is finalized — check the current function body order before editing, since `_to_buckets` needs the final `total_value` to compute percentages correctly across both fund and equity value.)

- [ ] **Step 7: Run allocation tests**

Run: `cd backend && python -m pytest tests/services/dashboard/test_allocation.py -v`
Expected: PASS.

- [ ] **Step 8: Add the dashboard API route**

In `backend/app/api/dashboard.py`, add near the existing `/holdings` route:

```python
from app.services.dashboard.equity_holdings import compute_equity_holdings
from app.services.dashboard.schemas import EquityHoldingRow

...

@router.get("/household-members/{member_id}/equity-holdings", response_model=list[EquityHoldingRow])
async def get_equity_holdings(
    member_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if get_household_member_for_user(db, user.id, member_id) is None:
        raise HTTPException(status_code=404, detail="Household member not found.")
    return await compute_equity_holdings(db, [member_id])
```

(Match whatever ownership-check helper name and import the existing `/holdings` route in the same file already uses — read it first rather than assuming `get_household_member_for_user`/`HTTPException` are already imported under those exact names.)

- [ ] **Step 9: Write and run a route test**

Add a test to `backend/tests/api/test_dashboard_routes.py` (check this file exists first; if the routes test lives under a different filename, use that one) mirroring the existing `/holdings` route test's auth/fixture setup, asserting `GET /household-members/{id}/equity-holdings` returns `200` with an empty list when no equity holdings exist, and the expected row shape when one does.

Run: `cd backend && python -m pytest tests/api/test_dashboard_routes.py -k equity -v`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/dashboard/equity_holdings.py backend/app/services/dashboard/schemas.py \
        backend/app/services/dashboard/allocation.py backend/app/api/dashboard.py \
        backend/tests/services/dashboard/test_equity_holdings.py backend/tests/services/dashboard/test_allocation.py \
        backend/tests/api/test_dashboard_routes.py
git commit -m "feat(dashboard): add equity holdings endpoint and Stocks allocation bucket"
```

---

### Task 5: Daily equity price refresh (on-demand fetch-and-cache)

**Files:**
- Create: `backend/app/services/dashboard/equity_price.py`
- Test: `backend/tests/services/dashboard/test_equity_price.py`

**Interfaces:**
- Consumes: `EquityPriceHistory` (Task 2, `app.models.reference`).
- Produces: `get_equity_price_on_or_before(db: Session, isin: str, on_date: date) -> tuple[Decimal, date] | None`, `warm_equity_price_history(db: Session, isins: list[str]) -> None` — the latter wired into `api/demat_imports.py`'s confirm route as a `BackgroundTasks` call, mirroring `api/imports.py`'s `_prefetch_member_nav_history` pattern.

**Flagged assumption — verify before relying on this in production:** the NSE bhavcopy URL template and CSV column names (`ISIN_CODE`, `CLOSE_PRICE`) below are NSE's documented "Securities Bhavcopy (Full)" format as of this writing, not confirmed against a live downloaded file in this session — the same category of unknown the research doc flagged for CDSL's Statement of Transactions format ("get one real sample before committing engineering time"). Download one real bhavcopy file and confirm the URL/column layout before this task is considered done; `_parse_bhavcopy`'s `try/except` already degrades to skipping unparseable rows rather than crashing if the layout is slightly off, but a systematically wrong column name would silently return zero prices, not an error — check the row count sanity in Step 6 below for exactly this reason.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/dashboard/test_equity_price.py`:

```python
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.models.reference import EquityPriceHistory
from app.services.dashboard.equity_price import get_equity_price_on_or_before, warm_equity_price_history


@pytest.mark.asyncio
async def test_get_equity_price_on_or_before_returns_none_when_uncached_and_fetch_fails(db_session, monkeypatch):
    async def failing_fetch(on_date):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("app.services.dashboard.equity_price._fetch_bhavcopy_for_date", failing_fetch)

    result = await get_equity_price_on_or_before(db_session, "INE002A01018", date(2026, 7, 31))
    assert result is None


@pytest.mark.asyncio
async def test_get_equity_price_on_or_before_returns_cached_row_for_exact_date(db_session):
    db_session.add(EquityPriceHistory(isin="INE002A01018", date=date(2026, 7, 31), price=Decimal("2500.5000")))
    db_session.commit()

    result = await get_equity_price_on_or_before(db_session, "INE002A01018", date(2026, 7, 31))
    assert result == (Decimal("2500.5000"), date(2026, 7, 31))


@pytest.mark.asyncio
async def test_get_equity_price_on_or_before_falls_back_to_most_recent_prior_row(db_session):
    db_session.add(EquityPriceHistory(isin="INE002A01018", date=date(2026, 7, 25), price=Decimal("2490.0000")))
    db_session.commit()

    # Past on_date with no exact-date row -> trusted from cache without a
    # fetch attempt (mirrors nav.py's get_nav_on_or_before semantics: only
    # on_date == today always attempts a fetch first).
    result = await get_equity_price_on_or_before(db_session, "INE002A01018", date(2026, 7, 31))
    assert result == (Decimal("2490.0000"), date(2026, 7, 25))


@pytest.mark.asyncio
async def test_warm_equity_price_history_caches_only_requested_isins(db_session, monkeypatch):
    async def fake_fetch(on_date):
        return {"INE002A01018": Decimal("2500.5000"), "INE999Z99999": Decimal("100.0000")}

    monkeypatch.setattr("app.services.dashboard.equity_price._fetch_bhavcopy_for_date", fake_fetch)

    await warm_equity_price_history(db_session, ["INE002A01018"])

    rows = db_session.query(EquityPriceHistory).all()
    assert len(rows) == 1
    assert rows[0].isin == "INE002A01018"


@pytest.mark.asyncio
async def test_warm_equity_price_history_degrades_gracefully_on_fetch_failure(db_session, monkeypatch):
    async def failing_fetch(on_date):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("app.services.dashboard.equity_price._fetch_bhavcopy_for_date", failing_fetch)

    await warm_equity_price_history(db_session, ["INE002A01018"])  # must not raise

    assert db_session.query(EquityPriceHistory).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/dashboard/test_equity_price.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.dashboard.equity_price'`.

- [ ] **Step 3: Implement `equity_price.py`**

Create `backend/app/services/dashboard/equity_price.py`:

```python
"""On-demand equity price fetch-and-cache -- structural port of nav.py,
substituting a daily NSE bulk EOD bhavcopy file (fetched and disk-cached
once per day, same shape as scheme_universe.py's NAVAll.txt handling) for
mfapi.in's per-scheme NAV history endpoint. No EventBridge Scheduler
exists yet for anything in this codebase (see the backend plan's Global
Constraints) -- this module is the same local-dev-first, fetch-on-first-
need stand-in nav.py already is for NAVs.

Bhavcopy URL/column layout is a flagged assumption -- see the backend
plan's Task 5 note. Verify against a real downloaded file before relying
on this in production.
"""

from __future__ import annotations

import csv
import io
import logging
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.reference import EquityPriceHistory

BHAVCOPY_URL_TEMPLATE = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / ".cache" / "nse_bhavcopy"
BHAVCOPY_TTL = timedelta(hours=24)

logger = logging.getLogger(__name__)

_bhavcopy_http_client: httpx.AsyncClient | None = None
_bhavcopy_http_client_lock = threading.Lock()


def _get_bhavcopy_http_client() -> httpx.AsyncClient:
    global _bhavcopy_http_client
    if _bhavcopy_http_client is None:
        with _bhavcopy_http_client_lock:
            if _bhavcopy_http_client is None:
                _bhavcopy_http_client = httpx.AsyncClient(timeout=30, follow_redirects=True)
    return _bhavcopy_http_client


def _cache_valid(path: Path, ttl: timedelta) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - mtime < ttl


def _parse_bhavcopy(text: str) -> dict[str, Decimal]:
    """ISIN -> closing price. Skips any row missing ISIN_CODE/CLOSE_PRICE
    or with an unparseable price rather than crashing the whole fetch over
    one bad row -- but see the flagged assumption above: confirm these are
    really the column names before trusting a zero-row result as "market
    closed" rather than "wrong column name"."""
    prices: dict[str, Decimal] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        isin = (row.get("ISIN_CODE") or "").strip()
        close = (row.get("CLOSE_PRICE") or "").strip()
        if not isin or not close:
            continue
        try:
            prices[isin] = Decimal(close)
        except Exception:
            continue
    return prices


async def _fetch_bhavcopy_for_date(on_date: date, cache_dir: Path | None = None) -> dict[str, Decimal]:
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    cache_path = cache_dir / f"bhavcopy_{on_date.isoformat()}.csv"

    if _cache_valid(cache_path, BHAVCOPY_TTL):
        text = cache_path.read_text(encoding="utf-8")
    else:
        client = _get_bhavcopy_http_client()
        url = BHAVCOPY_URL_TEMPLATE.format(ddmmyyyy=on_date.strftime("%d%m%Y"))
        resp = await client.get(url)
        resp.raise_for_status()
        text = resp.text
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")

    return _parse_bhavcopy(text)


def _upsert_equity_price_history(
    db: Session, on_date: date, prices: dict[str, Decimal], *, commit: bool = True
) -> None:
    if not prices:
        return
    values = [{"isin": isin, "date": on_date, "price": price} for isin, price in prices.items()]
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "sqlite":
        statement = sqlite_insert(EquityPriceHistory).values(values).on_conflict_do_nothing(
            index_elements=[EquityPriceHistory.isin, EquityPriceHistory.date]
        )
    elif dialect_name == "postgresql":
        statement = postgresql_insert(EquityPriceHistory).values(values).on_conflict_do_nothing(
            index_elements=[EquityPriceHistory.isin, EquityPriceHistory.date]
        )
    else:
        raise RuntimeError(f"Unsupported database dialect for equity price upsert: {dialect_name}")
    db.execute(statement)
    if commit:
        db.commit()


def _latest_cached_on_or_before(db: Session, isin: str, on_date: date) -> EquityPriceHistory | None:
    return (
        db.query(EquityPriceHistory)
        .filter(EquityPriceHistory.isin == isin, EquityPriceHistory.date <= on_date)
        .order_by(EquityPriceHistory.date.desc())
        .first()
    )


async def get_equity_price_on_or_before(db: Session, isin: str, on_date: date) -> tuple[Decimal, date] | None:
    """Most recent equity close price on or before `on_date`. Same
    degrade-gracefully posture as nav.py's get_nav_on_or_before: a cached
    row is trusted without fetching unless on_date is today (today's
    bhavcopy may not be published yet -- normal, not an error, but still
    worth a fetch attempt); a fetch failure falls back to whatever's
    cached, or None if nothing is cached at all."""
    cached = _latest_cached_on_or_before(db, isin, on_date)
    have_trustworthy_cache = cached is not None and (cached.date == on_date or on_date != date.today())
    if have_trustworthy_cache:
        return cached.price, cached.date

    try:
        prices = await _fetch_bhavcopy_for_date(on_date)
    except httpx.HTTPError:
        return (cached.price, cached.date) if cached else None

    _upsert_equity_price_history(db, on_date, prices)
    refreshed = _latest_cached_on_or_before(db, isin, on_date)
    return (refreshed.price, refreshed.date) if refreshed else None


async def warm_equity_price_history(db: Session, isins: list[str]) -> None:
    """Fetches today's bhavcopy once -- a single bulk file covers every
    ISIN, unlike nav.py's per-scheme mfapi.in endpoint -- and caches
    whichever of `isins` it contains. Best-effort: a fetch failure leaves
    prices unwarmed rather than raising, same posture as nav.py's
    warm_nav_history."""
    if not isins:
        return
    try:
        prices = await _fetch_bhavcopy_for_date(date.today())
    except httpx.HTTPError:
        logger.warning("warm_equity_price_history: bhavcopy fetch failed, leaving prices unwarmed")
        return

    relevant = {isin: price for isin, price in prices.items() if isin in set(isins)}
    _upsert_equity_price_history(db, date.today(), relevant)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/dashboard/test_equity_price.py -v`
Expected: PASS.

- [ ] **Step 5: Verify the bhavcopy assumption against a real file**

Download one real NSE bhavcopy file for a recent trading day (`curl` the URL `BHAVCOPY_URL_TEMPLATE` produces for that date, or check NSE's current archives page if the URL has moved) and confirm: the URL pattern resolves, the file is CSV, and it has columns matching `ISIN_CODE`/`CLOSE_PRICE` (adjust `_parse_bhavcopy`'s column lookups if the real names differ — NSE has changed bhavcopy formats before, e.g. a `.csv` vs. `.zip` delivery or a `Sr_no` header row). Re-run Step 4's tests after any adjustment.

- [ ] **Step 6: Wire the background prefetch into the confirm route**

In `backend/app/api/demat_imports.py`, add a `_prefetch_equity_prices` function mirroring `api/imports.py`'s `_prefetch_member_nav_history` (same `SessionLocal()`/`try`/`finally db.close()` shape, same `invalidate_holdings_cache` call on change), and call it via `background_tasks.add_task(...)` in `confirm_demat_import_route`, requiring `BackgroundTasks` in that route's signature (add the import and parameter).

- [ ] **Step 7: Write and run a route-level test for the prefetch wiring**

Add a test to `backend/tests/api/test_demat_imports_routes.py` asserting `confirm_demat_import_route` schedules the background task (mock `background_tasks.add_task` and assert it was called with the equity-price prefetch function).

Run: `cd backend && python -m pytest tests/api/test_demat_imports_routes.py -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/dashboard/equity_price.py backend/app/api/demat_imports.py \
        backend/tests/services/dashboard/test_equity_price.py backend/tests/api/test_demat_imports_routes.py
git commit -m "feat(dashboard): add on-demand equity price fetch-and-cache, wired into demat import confirm"
```

---

## After this plan

- The paired **frontend plan** (`Docs/superpowers/plans/2026-08-26-phase-2-stocks-demat-import-frontend.md`) consumes `/demat-imports/parse`, `/demat-imports/confirm`, and `/household-members/{id}/equity-holdings` built here.
- **Not in this plan, flagged as follow-ups:** bonds and demat-mode MF holdings have no dashboard read endpoint yet (only equities do, per the brief's explicit dashboard scope) — add `BondHolding`/`DematMutualFundHolding` equivalents of Task 4 when the frontend needs to display them. NPS holdings (`NSDLCASData.nps`) are untouched. Email auto-ingestion (Option B in the decision memo) is a separate, later plan. The `/cas-imports` lifecycle flow's demat rejection is unchanged.
