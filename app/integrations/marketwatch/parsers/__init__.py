"""
Clean Architecture vertical slice.
Parsers here are adapters behind domain ports.
"""

from .competitors import CompetitorsParser
from .performance import PerformanceParser

__all__ = ["PerformanceParser", "CompetitorsParser"]
