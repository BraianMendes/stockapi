from app.services.marketwatch_service import MarketWatchService
from app.utils import ScraperError


class FakeSession:
    def __init__(self, status_code=200, text="<html><title>ACME Corp - MarketWatch</title></html>"):
        self.status_code = status_code
        self.text = text
        self.calls = 0
    def get(self, url, headers=None, timeout=None):
        self.calls += 1
        class Resp:
            def __init__(self, status_code, text):
                self.status_code = status_code
                self._text = text
            @property
            def text(self):
                return self._text
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


def test_local_cache_hits():
    html = """
    <html>
      <head><title>Apple Inc. - MarketWatch</title></head>
      <body>
        <section data-module='Performance'>
          <div>
            <span>5D</span><span>1.2%</span>
            <span>1M</span><span>-0.4%</span>
            <span>YTD</span><span>10%</span>
          </div>
        </section>
        <div data-module='Competitors'>
          <table>
            <tr>
              <td><a href="/investing/stock/MSFT">Microsoft</a></td>
              <td>Market Cap: $123B</td>
            </tr>
          </table>
        </div>
      </body>
    </html>
    """

    svc = MarketWatchService(http=FakeHttp(text=html))
    data1 = svc.get_overview("AAPL", use_cookie=False)
    _ = svc.get_overview("AAPL", use_cookie=False)

    assert data1["company_name"].startswith("Apple")
    assert svc.http.session.calls == 1
