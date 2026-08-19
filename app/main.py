"""
FastAPI application entrypoint — app initialization, middleware, global
exception handlers, and route registration.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.config import settings
from app.database import init_db
from app.schemas.inspection import ErrorResponse
from app.services.vision_engine import VisionAPIError, VisionValidationError

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("fieldcheck.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---------------------------------------------------------
    await init_db()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    settings.report_output_path.mkdir(parents=True, exist_ok=True)
    logger.info(
        "FieldCheck AI started | env=%s | vision_provider=%s | mock_mode=%s | celery=%s",
        settings.app_env,
        settings.vision_provider,
        settings.vision_mock_mode or not settings.vision_api_key_configured,
        settings.use_celery,
    )
    yield
    # --- shutdown ------------------------------------------------------
    logger.info("FieldCheck AI shutting down.")


app = FastAPI(
    title=settings.app_name,
    description="Automated industrial asset inspection platform — OCR specs, "
    "defect detection, and safety compliance from field photos.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Lightweight in-memory rate-limiting scaffolding.
#
# This is intentionally simple (per-process, in-memory sliding window) — good
# enough to demonstrate the pattern and to blunt naive abuse in the MVP. A
# production deployment behind multiple workers should replace this with a
# Redis-backed limiter (e.g. `slowapi` / `redis` fixed-window counters) so
# limits are enforced consistently across processes.
# ---------------------------------------------------------------------------
_request_log: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit_and_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = settings.rate_limit_window_seconds
    bucket = _request_log[client_ip]

    while bucket and now - bucket[0] > window:
        bucket.popleft()

    if len(bucket) >= settings.rate_limit_requests:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=ErrorResponse(
                error="rate_limited",
                detail=f"Rate limit of {settings.rate_limit_requests} requests per "
                f"{window}s exceeded.",
                status_code=429,
                path=str(request.url.path),
            ).model_dump(),
        )
    bucket.append(now)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Global exception handlers — standardized error envelope
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("Validation error on %s: %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error="validation_error",
            detail="; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()),
            status_code=422,
            path=str(request.url.path),
        ).model_dump(),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="http_error",
            detail=str(exc.detail),
            status_code=exc.status_code,
            path=str(request.url.path),
        ).model_dump(),
    )


@app.exception_handler(VisionAPIError)
async def vision_api_error_handler(request: Request, exc: VisionAPIError):
    logger.error("Vision API error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=ErrorResponse(
            error="vision_api_error",
            detail="The vision analysis provider is temporarily unavailable. Please retry.",
            status_code=502,
            path=str(request.url.path),
        ).model_dump(),
    )


@app.exception_handler(VisionValidationError)
async def vision_validation_error_handler(request: Request, exc: VisionValidationError):
    logger.error("Vision validation error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error="vision_validation_error",
            detail="The AI model's response could not be validated against the expected schema.",
            status_code=422,
            path=str(request.url.path),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled exception [request_id=%s] on %s", request_id, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="internal_server_error",
            detail=f"An unexpected error occurred. Reference: {request_id}",
            status_code=500,
            path=str(request.url.path),
        ).model_dump(),
    )


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(api_router, prefix=settings.api_v1_prefix)

# Serve the lightweight frontend dashboard directly from the API (handy for
# the demo pipeline / docker-compose all-in-one deployment). In a larger
# production setup the frontend would typically be deployed separately
# (CDN / static host) and only talk to this API over CORS.
try:
    app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")
except RuntimeError:  # pragma: no cover - frontend dir missing in some contexts
    logger.warning("frontend/ directory not found; static UI not mounted.")
