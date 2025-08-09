from datetime import datetime, timedelta, date
from app.services.aggregator import StockAggregator, InMemoryCache


class FakeClock:
    def __init__(self):
        self.t = datetime(2025, 8, 8, 12, 0, 0)
    def now(self):
        return self.t


class FakePolygon:
    def get_ohlc(self, symbol, data_date):
        return {"status": "ok", "open": 10, "high": 12, "low": 9, "close": 11}


class FakeMW:
    def __init__(self, competitors=None, performance=None, company_name="Apple Inc."):
        self._competitors = competitors if competitors is not None else []
        self._performance = performance if performance is not None else {}
        self._company = company_name
    def get_overview(self, symbol, use_cookie=True):
        return {"company_name": self._company, "performance": self._performance, "competitors": self._competitors}


class FakeRepo:
    def __init__(self, amount=3):
        self.amount = amount
    def get_purchased_amount(self, symbol: str) -> int:
        return self.amount


def test_builds_payload_and_caches():
    clock = FakeClock()
    cache = InMemoryCache(_clock=clock)
    agg = StockAggregator(polygon=FakePolygon(), marketwatch=FakeMW(performance={"five_days": 1.2}), repo=FakeRepo(3), cache=cache, clock=clock)
    d = date(2025, 8, 7)

    s1 = agg.get_stock("AAPL", d)
    assert s1.company_code == "AAPL"
    assert s1.purchased_amount == 3
    assert s1.performance_data.five_days == 1.2

    s2 = agg.get_stock("AAPL", d)
    assert s2.stock_values.close == 11


def test_cache_expires_and_refreshes_repo():
    clock = FakeClock()
    cache = InMemoryCache(_clock=clock)
    repo = FakeRepo(3)
    agg = StockAggregator(polygon=FakePolygon(), marketwatch=FakeMW(), repo=repo, cache=cache, clock=clock)

    d = date(2025, 8, 7)
    s1 = agg.get_stock("AAPL", d)
    assert s1.purchased_amount == 3

    repo.amount = 9
    clock.t = clock.t + timedelta(seconds=agg.cache_ttl + 1)

    s2 = agg.get_stock("AAPL", d)
    assert s2.purchased_amount == 9


def test_competitor_mapping_defaults():
    competitors = [
        {"symbol": "XYZ"},
        {"name": "ABC", "market_cap": {"currency": "EUR", "value": "invalid"}},
    ]
    agg = StockAggregator(polygon=FakePolygon(), marketwatch=FakeMW(competitors=competitors), repo=FakeRepo(), cache=InMemoryCache())
    s = agg.get_stock("AAPL", "2025-08-07")
    assert s.competitors[0].name in {"XYZ", "ABC"}
    assert s.competitors[0].market_cap.currency in {"USD", "EUR"}
