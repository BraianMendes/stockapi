from typing import Any

from .value_objects import Money, Percentage


def parse_percent(text: str | None) -> float | None:
    """Parses percentage text into float (no %)."""
    if text is None:
        return None
    return Percentage.parse(text).value


def parse_money(text: str | None):
    """Parses money text into (currency, value)."""
    if text is None:
        return None
    m = Money.parse(text)
    return m.currency, m.amount


def to_float_or_none(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def to_float_or_zero(v: Any) -> float:
    try:
        return float(v) if v is not None else 0.0
    except Exception:
        return 0.0