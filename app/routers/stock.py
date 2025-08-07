from fastapi import APIRouter, HTTPException
from app.services.polygon_service import get_stock_ohlc
from app.services.marketwatch_service import scrape_marketwatch
from datetime import date

router = APIRouter()

@router.get("/stock/{stock_symbol}")
def get_stock(stock_symbol: str):
    try:
        poly_data = get_stock_ohlc(stock_symbol, date.today())
        mw_data = scrape_marketwatch(stock_symbol)
        return {"polygon": poly_data, "marketwatch": mw_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
