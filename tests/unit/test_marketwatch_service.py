from app.services.marketwatch_service import MarketWatchService
from app.utils import ScraperError


class FakeSession:
    def __init__(self, status_code=200, text="<html><title>ACME Corp - MarketWatch</title></html>"):
        self.status_code = status_code
        self.text = text
    def get(self, url, headers=None, timeout=None):
        class Resp:
            def __init__(self, status_code, text):
                self.status_code = status_code
                self.text = text
            def raise_for_status(self):
                if not (200 <= self.status_code < 300):
                    import requests
                    resp = type("Resp", (), {"status_code": self.status_code, "text": self.text})
                    raise requests.HTTPError(f"HTTPError {self.status_code}", response=resp)
        return Resp(self.status_code, self.text)


class FakeHttp:
    def __init__(self, status_code=200, text="<html><title>ACME Corp - MarketWatch</title></html>"):
        self.session = FakeSession(status_code, text)


def test_basic_parse():
    svc = MarketWatchService(http=FakeHttp())
    data = svc.get_overview("AAPL", use_cookie=False)
    assert data["company_name"].startswith("ACME Corp") and data["company_code"] == "AAPL"


def test_blocked_raises():
    svc = MarketWatchService(http=FakeHttp(status_code=403))
    import pytest
    with pytest.raises(ScraperError):
        svc.get_overview("AAPL", use_cookie=False)
