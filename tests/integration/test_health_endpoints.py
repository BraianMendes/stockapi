from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok" and body.get("service") == "stocks-api"


def test_ping():
    r = client.get("/ping")
    assert r.status_code == 200
    assert r.json() == "pong"
