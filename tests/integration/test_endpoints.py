import os
from fastapi.testclient import TestClient
from app.main import app
import app.routers.stock as stock_router
from app.services.aggregator import InMemoryCache
from app.services.repository_postgres import PostgresStockRepository

os.environ.setdefault("POLYGON_API_KEY", "test-key")


class FakePolygon:
    def get_ohlc(self, symbol, data_date):
        return {"status": "ok", "open": 1, "high": 2, "low": 0.5, "close": 1.5}


class FakeMW:
    def __init__(self):
        self.calls = 0
    def get_overview(self, symbol, use_cookie=True):
        self.calls += 1
        return {
            "company_name": "Apple Inc.",
            "performance": {"five_days": 1.2, "one_year": 10.0},
            "competitors": [{"name": "MSFT", "market_cap": {"currency": "USD", "value": 123.0}}],
        }


class FakeRepo(PostgresStockRepository):
    def __init__(self):
        pass
    def get_purchased_amount(self, symbol: str) -> int:
        return 0
    def set_purchased_amount(self, symbol: str, amount: int) -> None:
        self._last = (symbol, amount)


mw = FakeMW()
stock_router._aggregator.polygon = FakePolygon()
stock_router._aggregator.marketwatch = mw
stock_router._aggregator.cache = InMemoryCache()
stock_router._aggregator.repo = FakeRepo()
stock_router._repo = FakeRepo()

client = TestClient(app)


def test_get_stock():
    r = client.get("/stock/AAPL?request_date=2025-08-07")
    assert r.status_code == 200
    d = r.json()
    assert d["company_code"] == "AAPL"
    assert d["Stock_values"]["close"] == 1.5
    assert d["performance_data"]["one_year"] == 10.0


def test_post_stock_and_invalidate_cache():
    r1 = client.get("/stock/AAPL?request_date=2025-08-07")
    assert r1.status_code == 200
    calls_before = mw.calls
    rpost = client.post("/stock/AAPL", json={"amount": 4})
    assert rpost.status_code == 201
    r2 = client.get("/stock/AAPL?request_date=2025-08-07")
    assert r2.status_code == 200
    assert mw.calls > calls_before


def test_invalid_symbol_400():
    r = client.get("/stock/@@@")
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["code"] == "invalid_symbol"


def test_get_headers_and_refresh_param():
    r1 = client.get("/stock/AAPL?request_date=2025-08-07")
    assert r1.status_code == 200
    assert r1.headers.get("X-Cache") in {"miss", "hit", "bypass"}
    assert r1.headers.get("X-MarketWatch-Status") in {"ok", "fallback", "skipped"}
    assert r1.headers.get("X-MarketWatch-Used-Cookie") in {"true", "false"}

    r2 = client.get("/stock/AAPL?request_date=2025-08-07&refresh=true")
    assert r2.status_code == 200
    assert r2.headers.get("X-Cache") == "bypass"
    assert r2.headers.get("X-MarketWatch-Status") in {"ok", "fallback"}


def test_post_headers_present():
    r = client.post("/stock/AAPL?request_date=2025-08-07", json={"amount": 1})
    assert r.status_code == 201
    assert r.headers.get("X-Cache") in {"miss", "hit", "bypass"}
    assert r.headers.get("X-MarketWatch-Status") in {"ok", "fallback", "skipped"}
    assert r.headers.get("X-MarketWatch-Used-Cookie") in {"true", "false"}
