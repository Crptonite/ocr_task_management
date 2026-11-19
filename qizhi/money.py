"""Decimal helpers. Never use float for money: 3 x 52.81 != 158.43 in binary floating point."""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CENT = Decimal("0.01")


def D(value, default=None):
    """Convert str/int/float/Decimal to Decimal. Returns default for None/''/garbage."""
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace("$", "").strip())
    except InvalidOperation:
        return default


def q2(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def s2(x):
    """Serialise money as a 2dp string (None stays None)."""
    return None if x is None else str(q2(x))


def sq(x):
    """Serialise a quantity without trailing zeros."""
    if x is None:
        return None
    return str(int(x)) if x == x.to_integral() else str(x.normalize())
