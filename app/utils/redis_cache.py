import json
from typing import Any

from ..utils import EnvConfig


class RedisCache:
    """Redis-backed cache with JSON values and TTL."""

    def __init__(self, url: str | None = None, prefix: str = "stocks", decode_responses: bool = True) -> None:
        try:
            _redis = __import__("redis")
        except Exception as e:
            raise RuntimeError("redis_not_available") from e
        cfg = EnvConfig()
        self.url = url or cfg.get_str("REDIS_URL", "redis://localhost:6379/0")
        self.prefix = prefix.rstrip(":")
        self.client = _redis.Redis.from_url(self.url, decode_responses=decode_responses)

    def _k(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def get(self, key: str) -> Any | None:
        raw = self.client.get(self._k(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        raw = json.dumps(value)
        self.client.set(self._k(key), raw, ex=ttl_seconds)

    def delete_by_symbol(self, symbol: str) -> int:
        pattern = f"{self.prefix}:stock:{symbol}:*"
        deleted = 0
        for k in self.client.scan_iter(pattern):
            try:
                self.client.delete(k)
                deleted += 1
            except Exception:
                pass
        return deleted
