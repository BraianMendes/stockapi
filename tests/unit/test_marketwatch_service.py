from app.services.marketwatch_service import MarketWatchService
from app.utils import ScraperError
import requests


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

class _FakeResp:
    def __init__(self, status_code=200, text="OK"):
        self.status_code = status_code
        self.text = text
    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class _FakeSession:
    def __init__(self, mode="ok", text="<html><title>ACME - MarketWatch</title></html>"):
        self.mode = mode
        self.calls = 0
        self.text = text
    def get(self, url, headers=None, timeout=None):
        self.calls += 1
        if self.mode == "ok":
            return _FakeResp(200, self.text)
        if self.mode == "http_error":
            return _FakeResp(403, "blocked")
        if self.mode == "req_exc":
            import requests as _r
            raise _r.RequestException("boom")
        if self.mode == "unexpected":
            raise RuntimeError("weird")
        return _FakeResp(200, self.text)


class _FakeHttp:
    def __init__(self, session):
        self.session = session


def test_headers_build_cookie_toggle(monkeypatch):
    monkeypatch.setenv("MARKETWATCH_COOKIE", "x=y")
    svc = MarketWatchService(http=_FakeHttp(_FakeSession()))
    h1 = svc._build_headers(use_cookie=True)
    h2 = svc._build_headers(use_cookie=False)
    assert h1.get("Cookie") == "x=y"
    assert "Cookie" not in h2


def test_cache_ttl_zero_evicts_and_refetches():
    html = """
    <html>
      <head><title>Apple Inc. - MarketWatch</title></head>
      <body></body>
    </html>
    """
    sess = _FakeSession(mode="ok", text=html)
    svc = MarketWatchService(http=_FakeHttp(sess), cache_ttl_seconds=0)
    _ = svc.get_overview("AAPL", use_cookie=False)
    _ = svc.get_overview("AAPL", use_cookie=False)
    assert sess.calls >= 2


def test_fetch_html_http_error_blocked():
    svc = MarketWatchService(http=_FakeHttp(_FakeSession(mode="http_error")))
    try:
        svc.get_overview("AAPL", use_cookie=False)
        assert False, "expected ScraperError"
    except Exception as e:
        assert "blocked:403" in str(e)


def test_fetch_html_error_paths_request_and_unexpected():
    svc1 = MarketWatchService(http=_FakeHttp(_FakeSession(mode="req_exc")))
    try:
        svc1.get_overview("AAPL", use_cookie=False)
        assert False, "expected ScraperError"
    except Exception as e:
        assert "error:" in str(e)

    svc2 = MarketWatchService(http=_FakeHttp(_FakeSession(mode="unexpected")))
    try:
        svc2.get_overview("AAPL", use_cookie=False)
        assert False, "expected ScraperError"
    except Exception as e:
        assert "error:" in str(e)


def test_extract_company_name_variants():
    svc = MarketWatchService(http=_FakeHttp(_FakeSession()))

    html_meta = """
    <html><head><meta property="og:title" content="Meta Co - MarketWatch"></head><body></body></html>
    """
    d1 = MarketWatchService(http=_FakeHttp(_FakeSession(text=html_meta))).get_overview("META", use_cookie=False)
    assert d1["company_name"] == "Meta Co"

    html_h1 = """
    <html><body><h1 class="company__name">Header Name</h1></body></html>
    """
    d2 = MarketWatchService(http=_FakeHttp(_FakeSession(text=html_h1))).get_overview("HDR", use_cookie=False)
    assert d2["company_name"] == "Header Name"

    html_title = """
    <html><head><title>Title Co - MarketWatch</title></head><body></body></html>
    """
    d3 = MarketWatchService(http=_FakeHttp(_FakeSession(text=html_title))).get_overview("TTL", use_cookie=False)
    assert d3["company_name"] == "Title Co"


def test_get_overview_uses_html_parser_when_lxml_missing(monkeypatch):
    from app.services import marketwatch_service as mws
    real_bs = mws.BeautifulSoup

    def fake_bs(html, parser):
        if parser == "lxml":
            raise mws.FeatureNotFound("no lxml")
        return real_bs(html, "html.parser")

    monkeypatch.setattr(mws, "BeautifulSoup", fake_bs)

    html = """
    <html><head><title>Fallback Co - MarketWatch</title></head><body></body></html>
    """
    svc = MarketWatchService(http=_FakeHttp(_FakeSession(text=html)))
    d = svc.get_overview("FBK", use_cookie=False)
    assert d["company_name"] == "Fallback Co"


def test_parses_performance_and_competitors_from_html():
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

    class FakeHttp:
        def __init__(self, text):
            self.session = type("S", (), {"get": lambda *_args, **_kw: type("R", (), {
                "status_code": 200,
                "text": text,
                "raise_for_status": lambda self: None,
            })()})

    svc = MarketWatchService(http=FakeHttp(html))
    data = svc.get_overview("AAPL", use_cookie=False)

    perf = data["performance"]
    assert perf["five_days"] == 1.2
    assert perf["one_month"] == -0.4
    assert perf["year_to_date"] == 10.0

    comps = data["competitors"]
    assert comps and comps[0]["name"] == "Microsoft"
    assert comps[0]["market_cap"]["currency"] == "USD"
    assert comps[0]["market_cap"]["value"] > 0
