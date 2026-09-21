from __future__ import annotations

import logging
from typing import Any

import structlog

_SENSITIVE_MARKERS = ("authorization", "token", "secret", "init_data", "phone", "text", "name")
_MASK = "***"

def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (_MASK if any(m in str(k).lower() for m in _SENSITIVE_MARKERS) else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [_redact(v) for v in value]
    return value

def mask_sensitive(
    logger: object, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    return _redact(event_dict)  # type: ignore[no-any-return]

def configure_logging(env: str) -> None:
    level = logging.DEBUG if env in {"dev", "test"} else logging.INFO
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            mask_sensitive,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
