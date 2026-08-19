"""Structured logging so a failed Actions run is diagnosable from the log alone.

Set `logging.format: json` in config.yaml for Actions (one JSON object per
line, greppable) or `text` for readable local runs.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Attributes LogRecord always carries; anything else was passed via `extra=`
# and is worth emitting alongside the message.
_STANDARD_ATTRS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with `extra=` fields merged in."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = _safe(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _safe(value: Any) -> Any:
    """Keep JSON-native types; stringify anything else rather than blowing up."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    return str(value)


class TextFormatter(logging.Formatter):
    """Readable single line, with extras appended as key=value pairs."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)-24s %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _STANDARD_ATTRS and not k.startswith("_")
        }
        if extras:
            rendered = " ".join(f"{k}={v!r}" for k, v in extras.items())
            base = f"{base} | {rendered}"
        return base


def setup_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Install a single stdout handler. Safe to call more than once."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # These are chatty at DEBUG and never say anything we need.
    for noisy in ("httpx", "httpcore", "urllib3", "googleapiclient.discovery_cache"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
