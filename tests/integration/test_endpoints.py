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
    def get_overview(self, symbol, use_cookie=True):
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


stock_router._aggregator.polygon = FakePolygon()
stock_router._aggregator.marketwatch = FakeMW()
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


def test_post_stock():
    r = client.post("/stock/AAPL", json={"amount": 4})
    assert r.status_code == 201
    assert "were added" in r.json()["message"]
