from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

from app.routers.stock import router as stock_router
from app.routers.healthcheck import router as health_router
from app.db.database import init_db

from app.utils import configure_logging, get_logger
from app.middlewares import RequestLoggingMiddleware

TAGS_METADATA = [
    {
        "name": "Health",
        "description": "Liveness and readiness endpoints.",
    },
    {
        "name": "Stock",
        "description": "Retrieve stock data (Polygon + MarketWatch) and persist purchased amounts.",
    },
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log = get_logger("app.boot")
    log.info("starting app")

    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path, override=False)

    init_db()
    log.info("db initialized")

    yield
    log.info("shutting down app")

app = FastAPI(
    title="Stocks API",
    description=(
        "REST API that aggregates Polygon (OHLC) and MarketWatch (performance & competitors), "
        "with Redis-based per-stock caching and Postgres persistence for purchases."
    ),
    version="1.0.0",
    contact={"name": "Stocks API", "url": "http://localhost:8000/docs"},
    license_info={"name": "MIT"},
    openapi_tags=TAGS_METADATA,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    RequestLoggingMiddleware,
    skip_paths={"/health", "/ready", "/docs", "/redoc", "/openapi.json"},
)

app.include_router(health_router)
app.include_router(stock_router)

@app.get("/", tags=["Health"], summary="API index")
def index():
    return {
        "name": "Stocks API",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "ready": "/ready",
        "stock_example": "/stock/AAPL?request_date=2025-08-07",
    }
