import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Tuple, Union


@dataclass(frozen=True)
class IsoDate:
    """
    ISO date value object (YYYY-MM-DD).
    """
    value: str

    @staticmethod
    def from_any(d: Union[str, date, datetime]) -> "IsoDate":
        if isinstance(d, date) and not isinstance(d, datetime):
            return IsoDate(d.isoformat())
        if isinstance(d, datetime):
            return IsoDate(d.date().isoformat())
        s = str(d).strip()
        try:
            return IsoDate(datetime.fromisoformat(s).date().isoformat())
        except ValueError:
            pass
        try:
            return IsoDate(datetime.strptime(s, "%Y-%m-%d").date().isoformat())
        except ValueError:
            raise ValueError("Invalid date format, expected YYYY-MM-DD")


@dataclass(frozen=True)
class Symbol:
    """
    Normalized stock symbol (uppercase, trimmed).
    """
    value: str

    @staticmethod
    def of(s: str) -> "Symbol":
        return Symbol(str(s or "").strip().upper())


@dataclass(frozen=True)
class Percentage:
    """
    Percentage as float without % sign.
    """
    value: float

    @staticmethod
    def parse(text: str) -> "Percentage":
        num = _parse_float(text)
        return Percentage(num if num is not None else float("nan"))


@dataclass(frozen=True)
class Money:
    """
    Money with currency code and numeric amount.
    """
    currency: str
    amount: float

    @staticmethod
    def parse(text: str) -> "Money":
        currency = "USD"
        s = str(text or "").strip().replace("US$", "$").replace("USD", "$")
        if "€" in s:
            currency = "EUR"
        elif "£" in s:
            currency = "GBP"
        elif "$" in s:
            currency = "USD"
        numeric, multiplier = _extract_number_and_multiplier(s)
        return Money(currency, numeric * multiplier)


def _parse_float(text: str):
    s = str(text or "").strip().replace(",", "")
    m = re.search(r"[+-]?\d+(\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _extract_number_and_multiplier(text: str) -> Tuple[float, float]:
    s_clean = re.sub(r"[^\d\.\-\+KMBTkmbt]", "", str(text or ""))
    m = re.search(r"[+-]?\d+(\.\d+)?", s_clean)
    if not m:
        return 0.0, 1.0
    num = float(m.group(0))
    mult = 1.0
    tail = s_clean[-1:].lower()
    if tail == "k":
        mult = 1e3
    elif tail == "m":
        mult = 1e6
    elif tail == "b":
        mult = 1e9
    elif tail == "t":
        mult = 1e12
    return num, mult