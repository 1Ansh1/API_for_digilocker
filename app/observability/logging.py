"""Structured logging configuration using structlog.

Provides a :func:`setup_logging` bootstrap that wires structlog into the
standard-library logging system with PII redaction, ISO timestamps, and
environment-aware rendering (JSON for production, coloured console for
development).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

__all__ = ["setup_logging", "get_logger"]

# ---------------------------------------------------------------------------
# PII / secret field names that must never appear in log output
# ---------------------------------------------------------------------------

_SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "password",
        "secret",
        "client_secret",
        "code_verifier",
        "authorization",
    }
)

_REDACTED = "***REDACTED***"


def _redact_pii(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that replaces sensitive values with a placeholder.

    Field names are compared case-insensitively.  Both top-level keys and
    keys nested inside ``dict`` values (one level deep) are inspected.
    """
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_FIELDS:
            event_dict[key] = _REDACTED
        elif isinstance(event_dict[key], dict):
            for nested_key in list(event_dict[key].keys()):
                if nested_key.lower() in _SENSITIVE_FIELDS:
                    event_dict[key][nested_key] = _REDACTED
    return event_dict


def setup_logging(*, debug: bool = False) -> structlog.BoundLogger:
    """Configure structlog and stdlib logging for the application.

    Parameters
    ----------
    debug:
        When ``True`` the console renderer is used with colours; otherwise
        JSON lines are emitted for machine consumption.

    Returns
    -------
    structlog.BoundLogger
        A pre-bound logger instance ready for immediate use.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ],
        ),
        structlog.processors.StackInfoRenderer(),
        _redact_pii,
    ]

    if debug:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Wire structlog into stdlib so third-party loggers also get formatted.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    return structlog.get_logger()


def get_logger() -> structlog.BoundLogger:
    """Return a structlog :class:`BoundLogger`.

    This is safe to call at module level; structlog lazily binds the
    underlying logger on first use.
    """
    return structlog.get_logger()
