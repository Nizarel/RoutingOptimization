"""Structured JSON logging setup using structlog."""
from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib logging to emit JSON lines to stdout."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Silence verbose Azure SDK HTTP logging — it floods stdout with request/
    # response dumps and crowds out our own structured logs. WARNING preserves
    # auth failures and throttling notices.
    for noisy in (
        "azure",
        "azure.core.pipeline.policies.http_logging_policy",
        "azure.identity",
        "azure.monitor",
        "urllib3",
        "uvicorn.access",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
