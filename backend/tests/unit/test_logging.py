"""Tests for JSON structured logging and secrets redaction."""

import json
import logging
from datetime import datetime

from iryx.core.logging import REDACTED_PLACEHOLDER, JSONFormatter, redact_sensitive_data


def test_json_formatter_standard_fields() -> None:
    """Verify formatted log records produce valid single-line JSON with standard fields."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="iryx.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test event message",
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert "timestamp" in data
    assert data["level"] == "INFO"
    assert data["logger"] == "iryx.test"
    assert data["message"] == "Test event message"
    assert isinstance(data["context"], dict)

    # Verify timestamp is valid ISO 8601
    dt = datetime.fromisoformat(data["timestamp"])
    assert dt.tzinfo is not None


def test_json_formatter_context_inclusion() -> None:
    """Verify extra context attributes are captured in the context dictionary."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="iryx.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="User action recorded",
        args=(),
        exc_info=None,
    )
    record.context = {"case_id": "case-123", "user_id": "user-456"}

    output = formatter.format(record)
    data = json.loads(output)

    assert data["context"]["case_id"] == "case-123"
    assert data["context"]["user_id"] == "user-456"


def test_secrets_redaction_in_context() -> None:
    """Verify sensitive keys in context are systematically masked with ***REDACTED***."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="iryx.auth",
        level=logging.INFO,
        pathname="test.py",
        lineno=20,
        msg="Authentication attempt",
        args=(),
        exc_info=None,
    )
    record.context = {
        "user_email": "analyst@iryx.local",
        "password": "plain-text-password-123",
        "api_key": "sk-secret-123456",
        "access_token": "jwt.header.payload.signature",
        "nested": {
            "client_secret": "my-client-secret",
            "safe_counter": 42,
        },
    }

    output = formatter.format(record)
    data = json.loads(output)

    assert data["context"]["user_email"] == "analyst@iryx.local"
    assert data["context"]["password"] == REDACTED_PLACEHOLDER
    assert data["context"]["api_key"] == REDACTED_PLACEHOLDER
    assert data["context"]["access_token"] == REDACTED_PLACEHOLDER
    assert data["context"]["nested"]["client_secret"] == REDACTED_PLACEHOLDER
    assert data["context"]["nested"]["safe_counter"] == 42


def test_secrets_redaction_in_dict_message() -> None:
    """Verify dictionary message payloads have sensitive fields masked."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="iryx.gateway",
        level=logging.WARNING,
        pathname="test.py",
        lineno=30,
        msg={"service": "openai", "api_key": "super-secret-key", "status": "ok"},
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    msg_obj = json.loads(data["message"])
    assert msg_obj["service"] == "openai"
    assert msg_obj["api_key"] == REDACTED_PLACEHOLDER
    assert msg_obj["status"] == "ok"


def test_secrets_redaction_in_record_args() -> None:
    """Verify args containing dictionaries with sensitive keys are masked before formatting."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="iryx.auth",
        level=logging.INFO,
        pathname="test.py",
        lineno=40,
        msg="Processed payload: %s",
        args=({"password": "secret-password", "user": "admin"},),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert "secret-password" not in data["message"]
    assert REDACTED_PLACEHOLDER in data["message"]
    assert "admin" in data["message"]


def test_redact_sensitive_data_helper() -> None:
    """Directly test the redact_sensitive_data helper function with nested structures."""
    payload = {
        "token": "tok_123",
        "authorization": "Bearer abc",
        "hashed_password": "$argon2id$v=19...",
        "items": [
            {"secret_data": "secret_value", "id": 1},
            "plain_text_item",
        ],
    }

    sanitized = redact_sensitive_data(payload)
    assert sanitized["token"] == REDACTED_PLACEHOLDER
    assert sanitized["authorization"] == REDACTED_PLACEHOLDER
    assert sanitized["hashed_password"] == REDACTED_PLACEHOLDER
    assert sanitized["items"][0]["secret_data"] == REDACTED_PLACEHOLDER
    assert sanitized["items"][0]["id"] == 1
    assert sanitized["items"][1] == "plain_text_item"


def test_json_formatter_exception_info() -> None:
    """Verify that exc_info generates an 'exception' field in the JSON log output."""
    formatter = JSONFormatter()
    try:
        raise ValueError("Erreur de test interne pour exc_info")
    except ValueError as exc:
        record = logging.LogRecord(
            name="iryx.test.exceptions",
            level=logging.ERROR,
            pathname="test.py",
            lineno=50,
            msg="Une exception s'est produite",
            args=(),
            exc_info=(type(exc), exc, exc.__traceback__),
        )

    output = formatter.format(record)
    data = json.loads(output)

    assert "exception" in data
    assert "ValueError: Erreur de test interne pour exc_info" in data["exception"]
    assert data["level"] == "ERROR"
