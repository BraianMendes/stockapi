import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

TRACE_ID: ContextVar[str] = ContextVar("trace_id", default="-")

class JsonFormatter(logging.Formatter):
    """JSON log formatter."""

    def __init__(self, *, utc: bool = True) -> None:
        super().__init__()
        self.utc = utc

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self._timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": getattr(record, "trace_id", TRACE_ID.get()),
        }

        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k
            not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "trace_id",
            }
        }
        if extras:
            payload["extra"] = extras

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)

    def _timestamp(self, created: float) -> str:
        if self.utc:
            return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created))
        return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(created))


class PlainFormatter(logging.Formatter):
    """Plain text log formatter."""

    def __init__(self, *, utc: bool = True) -> None:
        dtfmt = "%Y-%m-%dT%H:%M:%SZ" if utc else "%Y-%m-%d %H:%M:%S%z"
        super().__init__(fmt="%(asctime)s %(levelname)s %(name)s - %(message)s | trace_id=%(trace_id)s",
                         datefmt=dtfmt)
        self.converter = time.gmtime if utc else time.localtime

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "trace_id"):
            record.trace_id = TRACE_ID.get()
        return super().format(record)


class TraceIdFilter(logging.Filter):
    """Adds trace_id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = TRACE_ID.get()
        return True


def set_trace_id(value: str | None = None) -> str:
    """Sets (or generates) the current trace id."""
    tid = value or uuid.uuid4().hex
    TRACE_ID.set(tid)
    return tid


def clear_trace_id() -> None:
    """Clears the current trace id."""
    TRACE_ID.set("-")


def get_logger(name: str | None = None) -> logging.Logger:
    """Returns a namespaced logger."""
    return logging.getLogger(name or "app")


def configure_logging(
    *,
    level: str | None = None,
    fmt: str | None = None,
    utc: bool | None = None,
    include_uvicorn: bool = True,
) -> None:
    """Configures root logging."""
    level_value = level if level is not None else (os.getenv("LOG_LEVEL", "INFO") or "INFO")
    level_str = level_value.upper()
    fmt_value = fmt if fmt is not None else (os.getenv("LOG_FORMAT", "plain") or "plain")
    fmt_str = fmt_value.lower()
    use_utc = (os.getenv("LOG_UTC", "true") if utc is None else str(utc)).lower() == "true"

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    root.setLevel(getattr(logging, level_str, logging.INFO))

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.addFilter(TraceIdFilter())

    if fmt_str == "json":
        handler.setFormatter(JsonFormatter(utc=use_utc))
    else:
        handler.setFormatter(PlainFormatter(utc=use_utc))

    root.addHandler(handler)

    if include_uvicorn:
        for lname in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            lg = logging.getLogger(lname)
            lg.handlers = []
            lg.propagate = True
            lg.setLevel(getattr(logging, level_str, logging.INFO))

    log = get_logger("app.boot")
    log.info("logging configured", extra={"level": level_str, "format": fmt_str, "utc": use_utc})
