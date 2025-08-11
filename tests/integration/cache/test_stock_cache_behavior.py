import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.aggregator import InMemoryCache
import app.routers.stock as stock_router


os.environ.setdefault("POLYGON_API_KEY", "test-key")


class MockPolygonService:
    """Mock Polygon service for predictable test responses."""
    
    def __init__(self):
        self.call_count = 0
        
    def get_ohlc(self, symbol, data_date):
        self.call_count += 1
        return {
            "status": "ok",
            "open": 100.0,
            "high": 105.0,
            "low": 98.0,
            "close": 102.5,
            "volume": 1000000
        }


class MockMarketWatchService:
    """Mock MarketWatch service for predictable test responses."""
    
    def __init__(self):
        self.call_count = 0
        
    def get_overview(self, symbol, use_cookie=True):
        self.call_count += 1
        return {
            "company_name": f"{symbol} Inc.",
            "performance": {
                "five_days": 2.5,
                "one_month": 5.0,
                "three_months": 8.0,
                "year_to_date": 12.0,
                "one_year": 15.0
            },
            "competitors": [
                {
                    "name": "COMPETITOR1",
                    "market_cap": {"currency": "USD", "value": 1000000000.0}
                }
            ]
        }


class MockRepository:
    """Mock repository for testing."""
    
    def get_purchased_amount(self, symbol: str) -> int:
        return 0
        
    def set_purchased_amount(self, symbol: str, amount: int) -> None:
        pass


@pytest.fixture
def client():
    """Create test client with mock services and fresh cache."""
    mock_polygon = MockPolygonService()
    mock_marketwatch = MockMarketWatchService()
    mock_repo = MockRepository()
    
    stock_router._aggregator.polygon = mock_polygon
    stock_router._aggregator.marketwatch = mock_marketwatch
    stock_router._aggregator.repo = mock_repo
    stock_router._aggregator.cache = InMemoryCache()
    stock_router._repo = mock_repo
    
    return TestClient(app), mock_polygon, mock_marketwatch


class TestCacheFunctionality:
    """Test basic cache functionality for stock data."""
    
    def test_first_request_is_cache_miss(self, client):
        """First request should result in cache miss and call external services."""
        test_client, mock_polygon, mock_marketwatch = client
        
        response = test_client.get("/stock/AAPL?request_date=2025-08-07")
        
        assert response.status_code == 200
        assert response.headers.get("X-Cache") == "miss"
        assert mock_polygon.call_count == 1
        assert mock_marketwatch.call_count == 1
        
    def test_second_request_is_cache_hit(self, client):
        """Second identical request should result in cache hit."""
        test_client, mock_polygon, mock_marketwatch = client
        
        test_client.get("/stock/AAPL?request_date=2025-08-07")
        response = test_client.get("/stock/AAPL?request_date=2025-08-07")
        
        assert response.status_code == 200
        assert response.headers.get("X-Cache") == "hit"
        assert response.headers.get("X-MarketWatch-Status") == "skipped"
        assert mock_polygon.call_count == 1
        assert mock_marketwatch.call_count == 1
        
    def test_different_symbols_have_separate_cache(self, client):
        """Different symbols should have separate cache entries."""
        test_client, mock_polygon, mock_marketwatch = client
        
        test_client.get("/stock/AAPL?request_date=2025-08-07")
        response = test_client.get("/stock/MSFT?request_date=2025-08-07")
        
        assert response.status_code == 200
        assert response.headers.get("X-Cache") == "miss"
        assert mock_polygon.call_count == 2
        assert mock_marketwatch.call_count == 2
        
    def test_different_dates_have_separate_cache(self, client):
        """Different dates should have separate cache entries."""
        test_client, mock_polygon, mock_marketwatch = client
        
        test_client.get("/stock/AAPL?request_date=2025-08-07")
        response = test_client.get("/stock/AAPL?request_date=2025-08-06")
        
        assert response.status_code == 200
        assert response.headers.get("X-Cache") == "miss"
        assert mock_polygon.call_count == 2
        assert mock_marketwatch.call_count == 2
        
    def test_post_request_invalidates_cache(self, client):
        """POST request should invalidate cache for the specific symbol."""
        test_client, mock_polygon, mock_marketwatch = client
        
        test_client.get("/stock/AAPL?request_date=2025-08-07")
        test_client.post("/stock/AAPL", json={"amount": 10})
        response = test_client.get("/stock/AAPL?request_date=2025-08-07")
        
        assert response.status_code == 200
        assert response.headers.get("X-Cache") == "miss"
        assert mock_marketwatch.call_count == 3
        
    def test_cached_data_matches_fresh_data(self, client):
        """Cached response should be identical to fresh response."""
        test_client, mock_polygon, mock_marketwatch = client
        
        fresh_response = test_client.get("/stock/AAPL?request_date=2025-08-07")
        cached_response = test_client.get("/stock/AAPL?request_date=2025-08-07")
        
        assert fresh_response.json() == cached_response.json()
        assert fresh_response.status_code == cached_response.status_code
        
        data = cached_response.json()
        assert data["company_code"] == "AAPL"
        assert "Stock_values" in data
        assert "close" in data["Stock_values"]
