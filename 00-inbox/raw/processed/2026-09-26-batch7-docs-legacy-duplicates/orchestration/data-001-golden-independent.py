"""Independent DATA-001 reference arithmetic.

This intentionally imports no application modules. XIRR is solved with a
bracketed bisection root finder (not the application's Newton-Raphson), and
TER is ordinary spreadsheet-style SUMPRODUCT / SUM arithmetic.
"""

from datetime import date
from decimal import Decimal, getcontext
import json
from pathlib import Path

getcontext().prec = 50
DATA = json.loads(Path(__file__).with_name("data-001-golden-dataset.json").read_text())


def xnpv(rate: Decimal, flows: list[tuple[date, Decimal]]) -> Decimal:
    first = min(flow_date for flow_date, _ in flows)
    return sum(
        (amount / ((Decimal(1) + rate) ** (Decimal((flow_date - first).days) / Decimal(365)))
         for flow_date, amount in flows),
        Decimal(0),
    )


def bisection_xirr(flows: list[tuple[date, Decimal]]) -> Decimal:
    low, high = Decimal("-0.999999"), Decimal("10")
    low_value = xnpv(low, flows)
    for _ in range(300):
        mid = (low + high) / Decimal(2)
        mid_value = xnpv(mid, flows)
        if abs(mid_value) < Decimal("1e-35"):
            return mid
        if (low_value > 0) == (mid_value > 0):
            low, low_value = mid, mid_value
        else:
            high = mid
    return (low + high) / Decimal(2)


schemes = DATA["schemes"]
purchase_date = date.fromisoformat(schemes[0]["purchase_date"])
valuation_date = date.fromisoformat(DATA["valuation_date"])
outflow = sum((Decimal(row["synthetic_purchase_amount_inr"]) for row in schemes), Decimal(0))
terminal = sum((Decimal(row["terminal_value_inr"]) for row in schemes), Decimal(0))
flows = [(purchase_date, -outflow), (valuation_date, terminal)]
rate = bisection_xirr(flows)
weighted_ter = sum(
    (Decimal(row["terminal_value_inr"]) * Decimal(row["independent_ter_percent"]) for row in schemes),
    Decimal(0),
) / terminal

print(f"terminal_value_inr={terminal}")
print(f"xirr_decimal_fraction={rate}")
print(f"xirr_percent={rate * Decimal(100)}")
print(f"weighted_ter_percent={weighted_ter}")
print(f"weighted_ter_api_precision={weighted_ter.quantize(Decimal('0.01'))}")
