import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api import (
    routes_ai,
    routes_auth,
    routes_consumer,
    routes_dashboard,
    routes_health,
    routes_ingestion,
    routes_review,
    routes_validation,
)
from .core.config import get_settings
from .core.context import request_id_var
from .core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="LoanTrust Copilot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

_request_log = logging.getLogger("request")


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request_id to every request/log line and emit one structured access log."""
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        _request_log.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        request_id_var.reset(token)

app.include_router(routes_health.router)
app.include_router(routes_auth.router)
app.include_router(routes_dashboard.router)
app.include_router(routes_ingestion.router)
app.include_router(routes_validation.router)
app.include_router(routes_review.router)
app.include_router(routes_ai.router)
app.include_router(routes_consumer.router)


@app.get("/", tags=["meta"])
def root():
    return {"name": "LoanTrust Copilot API", "version": app.version, "docs": "/docs"}
