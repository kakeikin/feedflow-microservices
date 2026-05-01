import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .routes import router
from . import cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("REDIS_URL"):
        await cache.connect()
    try:
        yield
    finally:
        if os.environ.get("REDIS_URL"):
            await cache.disconnect()


app = FastAPI(lifespan=lifespan)
app.include_router(router)
