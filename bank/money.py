"""Money handling. Read this file first.

Rule: money is a `decimal.Decimal`. Never a `float`.

A float cannot represent 0.10 exactly, so sums drift:

    >>> 1000.10 + 234.20 + 0.30 - 0.04
    1234.5599999999999

The same arithmetic in Decimal gives exactly 1234.56. In a system that moves
money that difference is not cosmetic, and it compounds across a ledger.

This was question 10 on the Day 1 module assessment (BigDecimal / Decimal for
high-precision financial calculations). This module is that answer, applied.
"""
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import re

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_TXN_AMOUNT = Decimal("1000000.00")

_AMOUNT_PATTERN = re.compile(r"^\d{1,10}(\.\d{1,2})?$")


def to_money(value) -> Decimal:
    """Coerce to a 2-decimal-place Decimal.

    Rejects floats rather than rounding them. By the time a float reaches here it
    has already lost precision, so silently accepting it hides the bug instead of
    surfacing it.
    """
    if isinstance(value, float):
        raise TypeError(
            "Refusing to build money from a float. Pass a str or a Decimal. "
            f"Got {value!r}, which is really {Decimal(value)}"
        )
    if isinstance(value, Decimal):
        return value.quantize(CENTS, rounding=ROUND_DOWN)
    try:
        return Decimal(str(value)).quantize(CENTS, rounding=ROUND_DOWN)
    except InvalidOperation as exc:
        raise ValueError(f"not a valid monetary amount: {value!r}") from exc


def parse_amount(raw) -> Decimal:
    """Validate an amount that came from outside the program.

    Today "outside" means a console prompt. Later it means an HTTP request body.
    The rules are the same either way, which is why they live here and not in
    whatever is reading the input.
    """
    from .errors import InvalidAmount

    if isinstance(raw, float):
        raise InvalidAmount("amount must be given as a string or Decimal, not a float")
    text = str(raw).strip()
    if not _AMOUNT_PATTERN.match(text):
        raise InvalidAmount(
            "amount must be a positive number with at most 2 decimal places"
        )
    amount = Decimal(text)
    if amount <= 0:
        raise InvalidAmount("amount must be greater than zero")
    if amount > MAX_TXN_AMOUNT:
        raise InvalidAmount(f"amount exceeds the per-transaction limit of {MAX_TXN_AMOUNT}")
    return amount.quantize(CENTS)


def format_money(value: Decimal) -> str:
    """Display form with thousands separators: Decimal('84210.75') -> '84,210.75'."""
    return f"{to_money(value):,.2f}"
