import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import make_asgi_app
from .database import engine, Base
from .routes import router
from . import publisher
from .metrics import EVENT_REQUEST_TOTAL, EVENT_REQUEST_LATENCY


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/metrics"):
            return await call_next(request)

        start = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            EVENT_REQUEST_TOTAL.labels(request.method, path, str(status_code)).inc()
            EVENT_REQUEST_LATENCY.labels(request.method, path).observe(time.time() - start)


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
app.add_middleware(MetricsMiddleware)
app.include_router(router)
app.mount("/metrics", make_asgi_app())
