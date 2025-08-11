from datetime import date

from app.utils import is_business_day, last_business_day, next_business_day, previous_business_day, roll_to_business_day


def test_business_day_checks_and_rolling():
    assert is_business_day(date(2025, 8, 8)) is True
    assert is_business_day(date(2025, 8, 9)) is False

    prev = previous_business_day(date(2025, 8, 11))
    assert prev == date(2025, 8, 8)

    nxt = next_business_day(date(2025, 8, 8))
    assert nxt == date(2025, 8, 11)

    rolled, reason = roll_to_business_day(date(2025, 8, 9), policy="previous")
    assert rolled == date(2025, 8, 8) and reason == "weekend"

    rolled2, reason2 = roll_to_business_day(date(2025, 8, 10), policy="nearest")
    assert rolled2 == date(2025, 8, 11) and reason2 == "weekend"