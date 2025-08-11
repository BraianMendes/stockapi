from datetime import date

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class MarketCap(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    currency: str = Field(..., alias="Currency", description="Currency code, e.g., USD")
    value: float = Field(..., alias="Value", description="Market cap numeric value")


class Competitor(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., description="Competitor company name")
    market_cap: MarketCap = Field(..., description="Competitor market cap")


class StockValues(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    open: float = Field(..., description="Open price")
    high: float = Field(..., description="High price")
    low: float = Field(..., description="Low price")
    close: float = Field(..., description="Close price")
    volume: float | None = Field(None, description="Volume")
    after_hours: float | None = Field(None, alias="afterHours", description="After-hours price")
    pre_market: float | None = Field(None, alias="preMarket", description="Pre-market price")


class PerformanceData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    five_days: float = Field(0.0, description="5D performance in percent")
    one_month: float = Field(0.0, description="1M performance in percent")
    three_months: float = Field(0.0, description="3M performance in percent")
    year_to_date: float = Field(0.0, description="YTD performance in percent")
    one_year: float = Field(0.0, description="1Y performance in percent")


class Stock(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str = Field(..., description="Overall status")
    purchased_amount: float = Field(..., description="Purchased amount (can be fractional)")
    purchased_status: str = Field(..., description="Purchased or not_purchased")
    request_data: date = Field(..., description="Request date (YYYY-MM-DD)")
    company_code: str = Field(..., description="Ticker symbol")
    company_name: str = Field(..., description="Company name")
    stock_values: StockValues = Field(..., alias="Stock_values", description="OHLC object")
    performance_data: PerformanceData = Field(..., description="Performance object")
    competitors: list[Competitor] = Field(..., alias="Competitors", description="List of competitors")