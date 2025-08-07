from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv
from app.routers import routers

@asynccontextmanager
async def lifespan(app: FastAPI):
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path, override=False)
    yield

app = FastAPI(lifespan=lifespan)

for router in routers:
    app.include_router(router)
