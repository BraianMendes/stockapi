from app.services.aggregator import InMemoryCache


def test_delete_by_symbol_removes_all_keys_for_symbol():
    cache = InMemoryCache()
    cache.set("stock:AAPL:2025-08-07", {"a": 1}, 300)
    cache.set("stock:AAPL:2025-08-06", {"a": 2}, 300)
    cache.set("stock:MSFT:2025-08-07", {"a": 3}, 300)

    assert cache.get("stock:AAPL:2025-08-07") is not None
    assert cache.get("stock:AAPL:2025-08-06") is not None
    assert cache.get("stock:MSFT:2025-08-07") is not None

    deleted = cache.delete_by_symbol("AAPL")
    assert deleted >= 2

    assert cache.get("stock:AAPL:2025-08-07") is None
    assert cache.get("stock:AAPL:2025-08-06") is None
    assert cache.get("stock:MSFT:2025-08-07") is not None
