import os

from app.services.polygon_service import PolygonService
from app.utils import PolygonError


def test_success():
    os.environ["POLYGON_API_KEY"] = "key"
    class FakeHttp:
        def get_json(self, url, headers=None, params=None, timeout=None):
            return {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "symbol": "AAPL", "status": "ok"}
    svc = PolygonService(http=FakeHttp())
    d = svc.get_ohlc("AAPL", "2025-08-07")
    assert d["open"] == 1 and d["close"] == 1.5 and d["request_date"] == "2025-08-07"


def test_missing_fields_raises():
    os.environ["POLYGON_API_KEY"] = "key"
    class FakeHttp:
        def get_json(self, url, headers=None, params=None, timeout=None):
            return {"open": 1, "high": 2}
    svc = PolygonService(http=FakeHttp())
    try:
        svc.get_ohlc("AAPL", "2025-08-07")
        assert False, "Expected PolygonError for missing fields"
    except PolygonError:
        assert True


def test_maps_optional_fields():
    os.environ["POLYGON_API_KEY"] = "key"
    class FakeHttp:
        def get_json(self, url, headers=None, params=None, timeout=None):
            return {
                "open": 10,
                "high": 12,
                "low": 9,
                "close": 11,
                "symbol": "AAPL",
                "status": "ok",
                "volume": 66084170,
                "afterHours": 164.4,
                "preMarket": 165.18,
            }
    svc = PolygonService(http=FakeHttp())
    d = svc.get_ohlc("AAPL", "2023-04-19")
    assert d["volume"] == 66084170
    assert d["afterHours"] == 164.4
    assert d["preMarket"] == 165.18
