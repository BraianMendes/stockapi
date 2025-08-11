import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import Base
from app.services.repository_postgres import PostgresStockRepository
import app.routers.stock as stock_router


os.environ.setdefault("POLYGON_API_KEY", "test-key")


@pytest.fixture
def db_client():
    """Create test client with in-memory database for PostgreSQL tests."""
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    
    test_repo = PostgresStockRepository(session_factory=SessionLocal)
    
    stock_router._repo = test_repo
    
    client = TestClient(app)
    yield client, test_repo
    
    engine.dispose()


class TestDatabasePersistence:
    """Test database persistence functionality."""
    
    def test_repository_persistence_basic(self, db_client):
        """Test that repository can store and retrieve purchased amounts."""
        client, repo = db_client
        
        repo.set_purchased_amount("AAPL", 100)
        stored_amount = repo.get_purchased_amount("AAPL")
        assert stored_amount == 100
        
        repo.set_purchased_amount("MSFT", 50) 
        assert repo.get_purchased_amount("MSFT") == 50
        assert repo.get_purchased_amount("AAPL") == 100
        
    def test_repository_update_amount(self, db_client):
        """Test that repository can update existing amounts."""
        client, repo = db_client
        
        repo.set_purchased_amount("GOOGL", 25)
        assert repo.get_purchased_amount("GOOGL") == 25
        
        repo.set_purchased_amount("GOOGL", 75)
        assert repo.get_purchased_amount("GOOGL") == 75
