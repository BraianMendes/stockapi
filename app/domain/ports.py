"""
Domain ports for the MarketWatch vertical slice.
Adapters implement these to keep dependencies pointing inward.
"""

from __future__ import annotations

from typing import Any, Protocol

from bs4 import BeautifulSoup


class PerformanceParserPort(Protocol):
    def parse(self, soup: BeautifulSoup) -> dict[str, float | None]: ...


class CompetitorsParserPort(Protocol):
    def parse(self, soup: BeautifulSoup, *, base_url: str) -> list[dict[str, Any]]: ...
