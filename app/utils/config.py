import os
from typing import Protocol


class Config(Protocol):
    """Typed config interface."""
    def get_str(self, name: str, default: str | None = None) -> str | None:
        ...
    def get_str_required(self, name: str) -> str:
        ...
    def get_bool(self, name: str, default: bool = False) -> bool:
        ...
    def get_int(self, name: str, default: int = 0) -> int:
        ...
    def get_float(self, name: str, default: float = 0.0) -> float:
        ...


class EnvConfig:
    """Environment-backed config provider."""
    def get_str(self, name: str, default: str | None = None) -> str | None:
        val = os.getenv(name)
        return val if val is not None else default

    def get_str_required(self, name: str) -> str:
        val = self.get_str(name)
        if not val:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return val

    def get_bool(self, name: str, default: bool = False) -> bool:
        val = os.getenv(name)
        if val is None:
            return default
        v = val.strip().lower()
        if v in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if v in {"0", "false", "f", "no", "n", "off"}:
            return False
        return default

    def get_int(self, name: str, default: int = 0) -> int:
        val = os.getenv(name)
        if val is None:
            return default
        try:
            return int(val)
        except ValueError:
            return default

    def get_float(self, name: str, default: float = 0.0) -> float:
        val = os.getenv(name)
        if val is None:
            return default
        try:
            return float(val)
        except ValueError:
            return default