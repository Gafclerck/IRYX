"""IRYX Structured JSON Logging Formatter and Secrets Redaction."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Standard LogRecord attributes to exclude from the custom context dictionary
STANDARD_LOG_RECORD_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)

# Substrings identifying sensitive fields to redact
SENSITIVE_FIELD_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "key",
    "authorization",
    "api_key",
    "access_token",
    "refresh_token",
    "credentials",
    "hashed_password",
)

REDACTED_PLACEHOLDER: str = "***REDACTED***"


def redact_sensitive_data(obj: Any) -> Any:
    """Recursively mask sensitive values in dictionaries and iterables."""
    if isinstance(obj, dict):
        redacted: dict[str, Any] = {}
        for key, value in obj.items():
            key_lower = str(key).lower()
            if any(sensitive in key_lower for sensitive in SENSITIVE_FIELD_SUBSTRINGS):
                redacted[key] = REDACTED_PLACEHOLDER
            else:
                redacted[key] = redact_sensitive_data(value)
        return redacted
    if isinstance(obj, list):
        return [redact_sensitive_data(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(redact_sensitive_data(item) for item in obj)
    return obj


class JSONFormatter(logging.Formatter):
    """Standard library Formatter emitting single-line JSON with secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the specified record as a JSON string."""
        # 1. Format timestamp in ISO 8601 UTC
        record_time = datetime.fromtimestamp(record.created, tz=UTC)
        timestamp_str = record_time.isoformat()

        # 2. Extract and sanitize context dictionary
        context: dict[str, Any] = {}
        if hasattr(record, "context") and isinstance(record.context, dict):
            context.update(record.context)

        # Include custom extra attributes
        for attr_name, attr_val in record.__dict__.items():
            if attr_name not in STANDARD_LOG_RECORD_ATTRIBUTES and attr_name != "context":
                context[attr_name] = attr_val

        # Mask sensitive keys in context
        sanitized_context = redact_sensitive_data(context)

        # 3. Format message and redact if dictionary payload
        if isinstance(record.msg, dict):
            sanitized_msg = redact_sensitive_data(record.msg)
            message_str = json.dumps(sanitized_msg, ensure_ascii=False)
        else:
            if record.args:
                record.args = redact_sensitive_data(record.args)
            message_str = record.getMessage()

        # 4. Construct log entry
        log_entry: dict[str, Any] = {
            "timestamp": timestamp_str,
            "level": record.levelname,
            "logger": record.name,
            "message": message_str,
            "context": sanitized_context,
        }

        # 5. Add exception info if present (without leaking raw secrets)
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str, ensure_ascii=False)


def setup_logging(log_level: str = "INFO") -> None:
    """Configure the root logger with the JSONFormatter on standard output."""
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Attach JSON stream handler to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    handler.setLevel(numeric_level)
    root_logger.addHandler(handler)
