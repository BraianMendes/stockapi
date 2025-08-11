"""CA vertical slice: MarketWatch adapters implement domain ports."""

from .parsers import CompetitorsParser, PerformanceParser

__all__ = ["PerformanceParser", "CompetitorsParser"]
