"""Structured logging, with financial values redacted before emission.

Redaction is the point of this module. Structured logs are useless if reading them
means reading your own balances out of a log aggregator — and once a value is in a
log pipeline it is in backups, in the vendor's index, and on anyone's laptop who has
access. The filter runs on the way out, so a caller cannot forget to apply it.

See docs/ARCHITECTURE.md#operations.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

REDACTED = "[redacted]"

#: Field names whose values are money. Matched case-insensitively against the whole
#: key, and against the last segment of a snake_case key, so ``opening_balance`` and
#: ``balance`` are both caught.
MONETARY_KEYS: frozenset[str] = frozenset(
    {
        "amount",
        "balance",
        "cost",
        "credit",
        "debit",
        "equity",
        "income",
        "interest",
        "limit",
        "net_worth",
        "networth",
        "payment",
        "premium",
        "price",
        "principal",
        "salary",
        "spend",
        "subtotal",
        "total",
        "value",
    }
)

#: Suffixes that make any key monetary regardless of its prefix.
MONETARY_SUFFIXES: tuple[str, ...] = (
    "_amount",
    "_balance",
    "_cents",
    "_cost",
    "_total",
    "_value",
)


def is_monetary_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in MONETARY_KEYS or lowered.endswith(MONETARY_SUFFIXES):
        return True
    # `account_balance` → `balance`. Catches compound names without needing every
    # combination enumerated.
    return lowered.rsplit("_", 1)[-1] in MONETARY_KEYS


def redact(value: Any) -> Any:
    """Recursively replace monetary values in dicts, lists, and tuples."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if is_monetary_key(str(key)) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


def redaction_processor(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """structlog processor applying :func:`redact` to the whole event."""
    return {
        key: (REDACTED if is_monetary_key(str(key)) else redact(value))
        for key, value in event_dict.items()
    }


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog to emit JSON on stdout.

    Called once at startup. Safe to call again — structlog replaces its config.
    """
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Last before rendering: everything above may add fields, and none of
            # them get to bypass the filter.
            redaction_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app") -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
