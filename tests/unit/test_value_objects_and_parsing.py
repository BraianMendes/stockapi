from datetime import date, datetime
import math

from app.utils import IsoDate, Money, Percentage, parse_money, parse_percent, to_float_or_none, to_float_or_zero


def test_iso_date_from_any():
    d = IsoDate.from_any("2025-08-07").value
    assert d == "2025-08-07"

    d2 = IsoDate.from_any(date(2025, 8, 7)).value
    assert d2 == "2025-08-07"

    d3 = IsoDate.from_any(datetime(2025, 8, 7, 12, 30, 0)).value
    assert d3 == "2025-08-07"


def test_iso_date_invalid_raises():
    import pytest
    with pytest.raises(ValueError):
        IsoDate.from_any("07-08-2025")


def test_percentage_and_parse_percent():
    p = Percentage.parse("1.25%")
    assert p.value == 1.25

    assert parse_percent("-0.4%") == -0.4
    assert parse_percent(None) is None


def test_money_parse_and_parse_money():
    cur, val = parse_money("$1.2B")
    assert cur == "USD" and math.isclose(val, 1.2e9)

    cur2, val2 = parse_money("€10.5M")
    assert cur2 == "EUR" and math.isclose(val2, 10.5e6)

    cur3, val3 = parse_money("£7k")
    assert cur3 == "GBP" and math.isclose(val3, 7000.0)

    m = Money.parse("123")
    assert m.currency == "USD" and m.amount == 123.0


def test_to_float_helpers():
    assert to_float_or_none("1.5") == 1.5
    assert to_float_or_none(None) is None
    assert to_float_or_none("x") is None

    assert to_float_or_zero("2.5") == 2.5
    assert to_float_or_zero(None) == 0.0
    assert to_float_or_zero("x") == 0.0


def test_symbol_normalization():
    from app.utils import Symbol
    assert Symbol.of(" aapl ").value == "AAPL"
