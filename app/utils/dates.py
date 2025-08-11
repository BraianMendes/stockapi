from datetime import date, timedelta


def last_business_day(start: date | None = None) -> date:
    """Returns the last business day before start (or today)."""
    d = (start or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def is_business_day(d: date) -> bool:
    """Returns True for Mon–Fri (no holidays)."""
    return d.weekday() < 5


def previous_business_day(d: date) -> date:
    x = d - timedelta(days=1)
    while x.weekday() >= 5:
        x -= timedelta(days=1)
    return x


def next_business_day(d: date) -> date:
    x = d + timedelta(days=1)
    while x.weekday() >= 5:
        x += timedelta(days=1)
    return x


def roll_to_business_day(d: date, policy: str = "previous") -> tuple[date, str]:
    """Rolls date to a business day per policy and returns (date, reason)."""
    if is_business_day(d):
        return d, "none"
    reason = "weekend"
    policy = (policy or "previous").lower()
    if policy == "next":
        return next_business_day(d), reason
    if policy == "nearest":
        prev_d = previous_business_day(d)
        next_d = next_business_day(d)
        if (d - prev_d) <= (next_d - d):
            return prev_d, reason
        return next_d, reason
    return previous_business_day(d), reason
