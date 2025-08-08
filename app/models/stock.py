from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field


class MarketCap(BaseModel):
    currency: str = Field(..., description="Currency code, e.g., USD")
    value: float = Field(..., description="Market cap numeric value")


class Competitor(BaseModel):
    name: str = Field(..., description="Competitor company name")
    market_cap: Optional[MarketCap] = Field(None, description="Competitor market cap")


class StockValues(BaseModel):
    open: float = Field(..., description="Open price")
    high: float = Field(..., description="High price")
    low: float = Field(..., description="Low price")
    close: float = Field(..., description="Close price")


class PerformanceData(BaseModel):
    five_days: Optional[float] = Field(None, description="5D performance in percent")
    one_month: Optional[float] = Field(None, description="1M performance in percent")
    three_months: Optional[float] = Field(None, description="3M performance in percent")
    year_to_date: Optional[float] = Field(None, description="YTD performance in percent")
    one_year: Optional[float] = Field(None, description="1Y performance in percent")


class Stock(BaseModel):
    status: str = Field(..., description="Overall status")
    purchased_amount: int = Field(..., description="Purchased amount")
    purchased_status: str = Field(..., description="Purchased or not_purchased")
    request_data: date = Field(..., description="Request date (YYYY-MM-DD)")
    company_code: str = Field(..., description="Ticker symbol")
    company_name: str = Field(..., description="Company name")
    stock_values: StockValues = Field(..., description="OHLC object")
    performance_data: PerformanceData = Field(..., description="Performance object")
    competitors: List[Competitor] = Field(..., description="List of competitors")