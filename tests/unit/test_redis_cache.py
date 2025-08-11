import builtins
import sys

import pytest


class _FakeRedisClient:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value

    def delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0

    def scan_iter(self, pattern):
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            for k in list(self.store.keys()):
                if k.startswith(prefix):
                    yield k
        else:
            if pattern in self.store:
                yield pattern


class _FakeRedisModule:
    class Redis:
        @staticmethod
        def from_url(url, decode_responses=True):
            return _FakeRedisClient()


def _with_fake_redis(monkeypatch):
    monkeypatch.setitem(sys.modules, "redis", _FakeRedisModule)


def test_set_get_and_delete_by_symbol(monkeypatch):
    _with_fake_redis(monkeypatch)
    from app.utils.redis_cache import RedisCache

    rc = RedisCache(url="redis://fake", prefix="stocks")

    rc.set("stock:AAPL:2025-08-07", {"a": 1}, 60)
    rc.set("stock:AAPL:2025-08-06", {"a": 2}, 60)
    rc.set("stock:MSFT:2025-08-07", {"a": 3}, 60)

    assert rc.get("stock:AAPL:2025-08-07") == {"a": 1}
    assert rc.get("stock:AAPL:2025-08-06") == {"a": 2}
    assert rc.get("stock:MSFT:2025-08-07") == {"a": 3}

    deleted = rc.delete_by_symbol("AAPL")
    assert deleted == 2

    assert rc.get("stock:AAPL:2025-08-07") is None
    assert rc.get("stock:AAPL:2025-08-06") is None
    assert rc.get("stock:MSFT:2025-08-07") == {"a": 3}


def test_get_invalid_json_returns_none(monkeypatch):
    _with_fake_redis(monkeypatch)
    from app.utils.redis_cache import RedisCache

    rc = RedisCache(url="redis://fake", prefix="stocks")

    bad_key = rc._k("stock:AAPL:bad")
    rc.client.set(bad_key, "not-json", ex=0)

    assert rc.get("stock:AAPL:bad") is None


def test_init_raises_without_redis(monkeypatch):
    import builtins as _b

    orig_import = _b.__import__

    def _no_redis(name, *args, **kwargs):
        if name == "redis":
            raise ImportError("no redis")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(_b, "__import__", _no_redis)

    from app.utils.redis_cache import RedisCache

    with pytest.raises(RuntimeError):
        RedisCache(url="redis://fake", prefix="stocks")
