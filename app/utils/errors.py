# app/utils/errors.py
class ExternalServiceError(RuntimeError):
    """
    Base error for external API or data source failures.
    """


class PolygonError(ExternalServiceError):
    """
    Error for Polygon API failures.
    """


class ScraperError(ExternalServiceError):
    """
    Error for scraping failures.
    """