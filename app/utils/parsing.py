from typing import Optional
from .value_objects import IsoDate, Symbol, Percentage, Money


def to_iso_date(value) -> str:
    """
    Convert input to YYYY-MM-DD.
    """
    return IsoDate.from_any(value).value


def normalize_symbol(value: str) -> str:
    """
    Normalize a stock symbol.
    """
    return Symbol.of(value).value


def parse_float(text: Optional[str]) -> Optional[float]:
    """
    Extract a float or return None.
    """
    if text is None:
        return None
    try:
        return float(str(text).replace(",", ""))
    except ValueError:
        return None


def parse_percent(text: Optional[str]) -> Optional[float]:
    """
    Parse a percentage as float without %.
    """
    if text is None:
        return None
    return Percentage.parse(text).value


def parse_money(text: Optional[str]):
    """
    Parse money text into (currency, value).
    """
    if text is None:
        return None
    m = Money.parse(text)
    return m.currency, m.amount