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
    import pytest
    with pytest.raises(PolygonError):
        svc.get_ohlc("AAPL", "2025-08-07")
