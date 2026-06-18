"""
Structured logging setup for Ramus Credit System.
Uses structlog for JSON-formatted logs in production, pretty-printed in dev.
"""
import logging
import sys
import structlog
from app.core.config import settings


def setup_logging() -> None:
    """Configure structlog + stdlib logging."""
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.ENVIRONMENT == "production":
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Wire stdlib logging to structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Silence noisy libraries
    for lib in ("uvicorn.access", "sqlalchemy.engine", "botocore", "boto3"):
        logging.getLogger(lib).setLevel(logging.WARNING)
