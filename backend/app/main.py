"""
Ramus Financial Solutions - Enterprise Credit Application & Decisioning System
Main FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import logging
import time
import uuid

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import engine, create_tables
from app.api.v1.router import api_router
from app.core.exceptions import (
    RamusBaseException,
    AuthorizationException,
    ValidationException,
)

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown events."""
    logger.info("Starting Ramus Credit System...")
    await create_tables()
    logger.info("Database tables initialized.")
    yield
    logger.info("Shutting down Ramus Credit System...")


app = FastAPI(
    title="Ramus Financial Solutions - Credit System API",
    description="Enterprise Credit Application and Decisioning Platform",
    version="1.0.0",
    docs_url="/api/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/api/redoc" if settings.ENVIRONMENT != "production" else None,
    openapi_url="/api/openapi.json" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],
)

if settings.ENVIRONMENT == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS,
    )


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attach a unique request ID to every request for traceability."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    start_time = time.time()

    response = await call_next(request)

    process_time = (time.time() - start_time) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = str(round(process_time, 2))

    logger.info(
        "HTTP %s %s %s %.2fms [%s]",
        request.method,
        request.url.path,
        response.status_code,
        process_time,
        request_id,
    )
    return response


# ── Exception Handlers ────────────────────────────────────────────────────────

@app.exception_handler(RamusBaseException)
async def ramus_exception_handler(request: Request, exc: RamusBaseException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(AuthorizationException)
async def auth_exception_handler(request: Request, exc: AuthorizationException):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": "FORBIDDEN", "message": str(exc)},
    )


@app.exception_handler(ValidationException)
async def validation_exception_handler(request: Request, exc: ValidationException):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "VALIDATION_ERROR", "message": str(exc), "fields": exc.fields},
    )


# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health_check():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0",
        "service": "ramus-credit-system",
    }


@app.get("/api/v1/health/integrations", tags=["system"])
async def integration_health():
    """Check health of all external integrations."""
    from app.integrations.credit_bureaus.health import check_bureau_health
    return await check_bureau_health()
