from datetime import date, timedelta
from typing import Optional


def last_business_day(start: Optional[date] = None) -> date:
    """
    Return the last business day before `start` (or today).
    Weekends (Saturday=5, Sunday=6) are skipped.
    """
    d = (start or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d
