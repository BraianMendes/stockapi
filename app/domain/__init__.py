"""
Domain layer: ports for the MarketWatch vertical slice.
These interfaces keep the core independent from scraping details.
"""

from .ports import CompetitorsParserPort, PerformanceParserPort

__all__ = [
    "PerformanceParserPort",
    "CompetitorsParserPort",
]
