"""JARVIS OS - Structured JSON Logging.

Provides JSON-formatted log output streams with automated context tracking via contextvars.
"""

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

# Context variables for tracing and logging correlation
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default=""
)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)
agent_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "agent_id", default=""
)
task_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("task_id", default="")
session_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "session_id", default=""
)


class StructuredJsonFormatter(logging.Formatter):
    """Custom logging formatter outputting single-line structured JSON logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a structured JSON string."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }

        # Inject tracing metadata from ContextVars
        log_data["trace_id"] = trace_id_var.get()
        log_data["request_id"] = request_id_var.get()
        log_data["agent_id"] = agent_id_var.get()
        log_data["task_id"] = task_id_var.get()
        log_data["session_id"] = session_id_var.get()

        # Merge in any explicitly passed record properties or exceptions
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Merge in extra dict context if provided
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            log_data["context"] = context
        else:
            log_data["context"] = {}

        return json.dumps(log_data)


def configure_logging(level: str = "INFO") -> None:
    """Configure system-wide structured JSON logging handlers.

    Args:
        level: The default logging level (e.g. 'DEBUG', 'INFO').
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Output to stdout stream handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Retrieve or create a logger with the given namespace.

    Args:
        name: The namespace name of the module.

    Returns:
        logging.Logger: The configured Logger.
    """
    return logging.getLogger(name)
