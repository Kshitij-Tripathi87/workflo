"""Structured JSON logging for the workflo platform."""

import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any
from logging import LogRecord


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_data"):
            log_entry.update(record.extra_data)
        return json.dumps(log_entry, default=str)


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def add_run_context(run_id: str, goal: str = "", **kwargs: Any) -> logging.LoggerAdapter:
    extra = {"run_id": run_id, "goal": goal}
    extra.update(kwargs)

    class _RunAdapter(logging.LoggerAdapter):
        def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
            extra_ref = kwargs.setdefault("extra", {})
            existing = extra_ref.get("extra_data", {})
            extra_ref["extra_data"] = {**extra, **existing}
            return msg, kwargs

    root = logging.getLogger()
    return _RunAdapter(root, {})


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
