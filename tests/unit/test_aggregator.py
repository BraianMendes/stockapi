from datetime import date, datetime, timedelta

import pytest

from app.services.aggregator import InMemoryCache, StockAggregator


class FailingCache:
    def get(self, key: str):
        raise RuntimeError("cache down")
    def set(self, key: str, value, ttl_seconds: int):
        raise RuntimeError("cache down")


class MWAlwaysFails:
    def get_overview(self, symbol: str, use_cookie: bool = True):
        raise RuntimeError("mw fail")


class RepoRaises:
    def get_purchased_amount(self, symbol: str) -> int:
        raise RuntimeError("db fail")


class PolyOk:
    def get_ohlc(self, symbol, data_date):
        return {"status": "ok", "open": 1, "high": 2, "low": 0.5, "close": 1.5}


class FakeClock:
    def __init__(self):
        self.t = datetime(2025, 8, 8, 12, 0, 0)
    def now(self):
        return self.t


class FakePolygon:
    def get_ohlc(self, symbol, data_date):
        return {"status": "ok", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1000, "afterHours": 10.5, "preMarket": 10.2}


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
    assert s1.stock_values.volume == 1000
    assert s1.stock_values.after_hours == 10.5
    assert s1.stock_values.pre_market == 10.2

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


def test_bypass_cache_flag_refreshes():
    clock = FakeClock()
    cache = InMemoryCache(_clock=clock)
    agg = StockAggregator(polygon=FakePolygon(), marketwatch=FakeMW(), repo=FakeRepo(1), cache=cache, clock=clock)
    d = date(2025, 8, 7)

    s1 = agg.get_stock("AAPL", d)
    assert s1.purchased_amount == 1

    agg.repo.amount = 7
    s2 = agg.get_stock("AAPL", d, bypass_cache=True)
    assert s2.purchased_amount == 7


def test_competitor_mapping_defaults():
    competitors = [
        {"symbol": "XYZ"},
        {"name": "ABC", "market_cap": {"currency": "EUR", "value": "invalid"}},
    ]
    agg = StockAggregator(polygon=FakePolygon(), marketwatch=FakeMW(competitors=competitors), repo=FakeRepo(), cache=InMemoryCache())
    s = agg.get_stock("AAPL", "2025-08-07")
    assert s.competitors[0].name in {"XYZ", "ABC"}
    assert s.competitors[0].market_cap.currency in {"USD", "EUR"}


def test_cache_errors_are_ignored_and_fallback_marketwatch():
    agg = StockAggregator(polygon=PolyOk(), marketwatch=MWAlwaysFails(), repo=RepoRaises(), cache=FailingCache())
    s = agg.get_stock("AAPL", date(2025, 8, 7), bypass_cache=False)
    assert s.company_code == "AAPL" and s.company_name == "AAPL"
    assert agg.last_meta.get("marketwatch_status") == "fallback"
    assert agg.last_meta.get("cache") == "miss"


def test_map_competitors_with_bad_values():
    class MWComp:
        def get_overview(self, symbol, use_cookie=True):
            return {
                "company_name": symbol,
                "performance": {},
                "competitors": [
                    {"name": "ABC", "market_cap": {"currency": "EUR", "value": "bad"}},
                    {"symbol": "XYZ"},
                ],
            }
    agg = StockAggregator(polygon=PolyOk(), marketwatch=MWComp(), repo=None, cache=InMemoryCache())
    s = agg.get_stock("AAPL", date(2025, 8, 7))
    assert len(s.competitors) == 2
    assert s.competitors[0].market_cap.value >= 0.0
