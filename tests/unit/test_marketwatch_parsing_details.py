from app.services.marketwatch_service import MarketWatchService


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
