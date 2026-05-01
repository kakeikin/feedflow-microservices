import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .database import engine, Base
from .routes import router
from . import publisher


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine is not None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    if os.environ.get("RABBITMQ_URL"):
        await publisher.connect()
    yield
    if os.environ.get("RABBITMQ_URL"):
        await publisher.disconnect()


app = FastAPI(title="Event Service", lifespan=lifespan)
app.include_router(router)
