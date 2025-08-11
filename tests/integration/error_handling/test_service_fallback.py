import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.aggregator import InMemoryCache
from app.utils import PolygonError, ScraperError
import app.routers.stock as stock_router


os.environ.setdefault("POLYGON_API_KEY", "test-key")


class MockPolygonService:
    """Mock Polygon service that can simulate failures."""
    
    def __init__(self, fail_mode=None):
        self.fail_mode = fail_mode
        
    def get_ohlc(self, symbol, data_date):
        if self.fail_mode == "unauthorized":
            raise PolygonError("unauthorized")
        elif self.fail_mode == "rate_limited":
            raise PolygonError("rate_limited")
        elif self.fail_mode == "not_found":
            raise PolygonError("not_found")
        else:
            return {
                "status": "ok",
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 102.5
            }


class MockMarketWatchService:
    """Mock MarketWatch service that can simulate failures."""
    
    def __init__(self, fail_mode=None):
        self.fail_mode = fail_mode
        self.call_count = 0
        
    def get_overview(self, symbol, use_cookie=True):
        self.call_count += 1
        
        if self.fail_mode == "always_fail":
            raise ScraperError("blocked:403")
        elif self.fail_mode == "fail_with_cookie":
            if use_cookie:
                raise ScraperError("blocked:403")
            else:
                # Succeeds without cookie (fallback works)
                return {
                    "company_name": f"{symbol} Inc.",
                    "performance": {"five_days": 2.5, "one_year": 15.0},
                    "competitors": []
                }
        else:
            return {
                "company_name": f"{symbol} Inc.",
                "performance": {"five_days": 2.5, "one_year": 15.0},
                "competitors": []
            }


class MockRepository:
    """Mock repository for testing."""
    
    def get_purchased_amount(self, symbol):
        return 0
        
    def set_purchased_amount(self, symbol, amount):
        pass


@pytest.fixture
def error_client():
    """Create test client for error handling tests."""
    # Use a simple repository and cache
    test_repo = MockRepository()
    test_cache = InMemoryCache()
    
    # We'll replace services in individual tests
    stock_router._aggregator.repo = test_repo
    stock_router._aggregator.cache = test_cache
    stock_router._repo = test_repo
    
    client = TestClient(app)
    yield client


class TestServiceFallback:
    """Test error handling and fallback mechanisms."""
    
    def test_polygon_unauthorized_error(self, error_client):
        """Test Polygon unauthorized error handling."""
        client = error_client
        
        # Setup failing Polygon service
        stock_router._aggregator.polygon = MockPolygonService(fail_mode="unauthorized")
        stock_router._aggregator.marketwatch = MockMarketWatchService()
        
        response = client.get("/stock/AAPL")
        
        # Router uses 502 as default for upstream errors
        assert response.status_code == 502
        response_data = response.json()
        assert "unauthorized" in response_data["detail"]["message"].lower()
        
    def test_polygon_rate_limited_error(self, error_client):
        """Test Polygon rate limited error handling."""
        client = error_client
        
        # Setup rate limited Polygon service
        stock_router._aggregator.polygon = MockPolygonService(fail_mode="rate_limited")
        stock_router._aggregator.marketwatch = MockMarketWatchService()
        
        response = client.get("/stock/AAPL")
        
        # Router uses 502 as default for upstream errors  
        assert response.status_code == 502
        response_data = response.json()
        assert "rate limited" in response_data["detail"]["message"].lower()
        
    def test_marketwatch_fallback_mechanism(self, error_client):
        """Test MarketWatch fallback from cookie to no-cookie."""
        client = error_client
        
        # Setup services: Polygon works, MarketWatch fails with cookie but works without
        stock_router._aggregator.polygon = MockPolygonService()
        mw_service = MockMarketWatchService(fail_mode="fail_with_cookie")
        stock_router._aggregator.marketwatch = mw_service
        
        response = client.get("/stock/AAPL")
        
        assert response.status_code == 200
        # Should have tried twice: once with cookie (failed), once without (succeeded)
        assert mw_service.call_count == 2
        
        data = response.json()
        assert data["company_name"] == "AAPL Inc."
        
    def test_marketwatch_complete_failure_fallback(self, error_client):
        """Test MarketWatch complete failure results in fallback data."""
        client = error_client
        
        # Setup services: Polygon works, MarketWatch always fails
        stock_router._aggregator.polygon = MockPolygonService()
        mw_service = MockMarketWatchService(fail_mode="always_fail")
        stock_router._aggregator.marketwatch = mw_service
        
        response = client.get("/stock/AAPL")
        
        assert response.status_code == 200
        # Should have tried twice: once with cookie, once without (both failed)
        assert mw_service.call_count == 2
        
        data = response.json()
        # Should use symbol as company name (fallback)
        assert data["company_name"] == "AAPL"
        # Should have empty performance and competitors (fallback)
        assert data["performance_data"]["five_days"] == 0.0
        # Check the correct field name in response
        assert data["Competitors"] == []
