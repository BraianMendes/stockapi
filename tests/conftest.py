import os
import types
import pytest
import logging

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


class DummyHTTP:
    def __init__(self, json_map=None, text_map=None, status_code=200):
        self.json_map = json_map or {}
        self.text_map = text_map or {}
        self.status_code = status_code
        self.session = types.SimpleNamespace(get=self._get)

    def _get(self, url, headers=None, params=None, timeout=None):
        class Resp:
            def __init__(self, status_code, text, json_data):
                self.status_code = status_code
                self.text = text
                self._json = json_data
            def raise_for_status(self):
                if not (200 <= self.status_code < 300):
                    import requests
                    resp = types.SimpleNamespace(status_code=self.status_code, text=self.text)
                    raise requests.HTTPError(f"HTTPError {self.status_code}", response=resp)
            def json(self):
                return self._json
        text = self.text_map.get(url, "ok")
        json_data = self.json_map.get(url, {})
        return Resp(self.status_code, text, json_data)
