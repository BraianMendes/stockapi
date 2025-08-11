import os
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.aggregator import InMemoryCache
import app.routers.stock as stock_router


os.environ.setdefault("POLYGON_API_KEY", "test-key")


class SlowPolygonService:
    """Mock Polygon service with simulated delay."""
    
    def __init__(self):
        self.call_count = 0
        
    def get_ohlc(self, symbol, data_date):
        self.call_count += 1
        time.sleep(0.1)
        return {
            "status": "ok",
            "open": 100.0,
            "high": 105.0,
            "low": 98.0,
            "close": 102.5
        }


class SlowMarketWatchService:
    """Mock MarketWatch service with simulated delay."""
    
    def __init__(self):
        self.call_count = 0
        
    def get_overview(self, symbol, use_cookie=True):
        self.call_count += 1
        time.sleep(0.05)
        return {
            "company_name": f"{symbol} Inc.",
            "performance": {"five_days": 2.5, "one_year": 15.0},
            "competitors": []
        }


class MockRepository:
    """Mock repository for testing."""
    
    def get_purchased_amount(self, symbol: str) -> int:
        return 0
        
    def set_purchased_amount(self, symbol: str, amount: int) -> None:
        pass


@pytest.fixture
def performance_client():
    """Create test client with slow mock services."""
    polygon_service = SlowPolygonService()
    marketwatch_service = SlowMarketWatchService()
    
    stock_router._aggregator.polygon = polygon_service
    stock_router._aggregator.marketwatch = marketwatch_service
    stock_router._aggregator.repo = MockRepository()
    stock_router._aggregator.cache = InMemoryCache()
    stock_router._repo = MockRepository()
    
    return TestClient(app), polygon_service, marketwatch_service


class TestCachePerformanceValidation:
    """Test that cache improves performance."""
    
    def test_cache_eliminates_service_calls(self, performance_client):
        """Cached requests should not call external services."""
        client, polygon_service, marketwatch_service = performance_client
        
        client.get("/stock/AAPL?request_date=2025-08-07")
        initial_polygon_calls = polygon_service.call_count
        initial_mw_calls = marketwatch_service.call_count
        
        response = client.get("/stock/AAPL?request_date=2025-08-07")
        
        assert response.status_code == 200
        assert response.headers.get("X-Cache") == "hit"
        assert polygon_service.call_count == initial_polygon_calls
        assert marketwatch_service.call_count == initial_mw_calls
        
    def test_cache_reduces_response_time(self, performance_client):
        """Cached requests should be faster than fresh requests."""
        client, polygon_service, marketwatch_service = performance_client
        
        start_time = time.time()
        response1 = client.get("/stock/AAPL?request_date=2025-08-07")
        first_request_time = time.time() - start_time
        
        assert response1.status_code == 200
        assert response1.headers.get("X-Cache") == "miss"
        
        start_time = time.time()
        response2 = client.get("/stock/AAPL?request_date=2025-08-07")
        second_request_time = time.time() - start_time
        
        assert response2.status_code == 200
        assert response2.headers.get("X-Cache") == "hit"
        assert second_request_time < first_request_time
        
    def test_multiple_cached_requests_remain_fast(self, performance_client):
        """Multiple cached requests should remain consistently fast."""
        client, polygon_service, marketwatch_service = performance_client
        
        client.get("/stock/AAPL?request_date=2025-08-07")
        
        for _ in range(10):
            start_time = time.time()
            response = client.get("/stock/AAPL?request_date=2025-08-07")
            request_time = time.time() - start_time
            
            assert response.status_code == 200
            assert response.headers.get("X-Cache") == "hit"
            assert request_time < 0.05
