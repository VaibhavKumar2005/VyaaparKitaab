"""Exact two-decimal-place currency helpers and Pydantic money types."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal(100)


def to_money(value: Any) -> Decimal:
    """
    Converts int, float, str, or Decimal into an exact 2-decimal-place Decimal
    using ROUND_HALF_UP, avoiding binary floating-point artifacts.
    """
    if value is None:
        return ZERO
    if isinstance(value, bool):
        raise TypeError("Boolean is not a valid monetary amount")
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, int):
        dec = Decimal(value)
    elif isinstance(value, float):
        dec = Decimal(str(value))
    else:
        cleaned = str(value).strip().replace(",", "")
        if not cleaned:
            return ZERO
        try:
            dec = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid monetary amount: {value!r}") from exc

    if not dec.is_finite():
        raise ValueError(f"Non-finite monetary amount: {value!r}")
    return dec.quantize(CENT, rounding=ROUND_HALF_UP)


def to_optional_money(value: Any) -> Decimal | None:
    if value is None:
        return None
    return to_money(value)


def money_to_float(value: Any) -> float:
    """Serializes a quantized Decimal to a JSON-compatible number."""
    return float(to_money(value))


Money = Annotated[
    Decimal,
    BeforeValidator(to_money),
    PlainSerializer(money_to_float, return_type=float, when_used="json"),
]

OptionalMoney = Annotated[
    Decimal | None,
    BeforeValidator(to_optional_money),
    PlainSerializer(
        lambda v: money_to_float(v) if v is not None else None,
        return_type=float | None,
        when_used="json",
    ),
]
