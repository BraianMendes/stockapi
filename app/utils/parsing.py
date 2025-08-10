from typing import Optional
from .value_objects import Percentage, Money


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