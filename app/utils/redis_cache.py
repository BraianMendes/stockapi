import json
from typing import Any, Optional
import redis
from ..utils import EnvConfig

class RedisCache:
    """
    Redis-backed cache implementing get/set with TTL.
    Stores JSON-serialized values.
    """

    def __init__(self, url: str | None = None, prefix: str = "stocks", decode_responses: bool = True) -> None:
        cfg = EnvConfig()
        self.url = url or cfg.get_str("REDIS_URL", "redis://localhost:6379/0")
        self.prefix = prefix.rstrip(":")
        self.client = redis.Redis.from_url(self.url, decode_responses=decode_responses)

    def _k(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def get(self, key: str) -> Optional[Any]:
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
