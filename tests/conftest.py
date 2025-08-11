import logging
import os

import pytest

os.environ["POLYGON_API_KEY"] = os.environ.get("POLYGON_API_KEY", "test-key")
os.environ["CACHE_TTL_SECONDS"] = os.environ.get("CACHE_TTL_SECONDS", "1")
os.environ["MW_JITTER_MIN"] = "0"
os.environ["MW_JITTER_MAX"] = "0"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ.pop("REDIS_URL", None)

from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _quiet_marketwatch_logs():
    logger = logging.getLogger("app.services.marketwatch")
    prev = logger.level
    logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(prev)


@pytest.fixture(scope="session")
def client():
    return TestClient(app)
