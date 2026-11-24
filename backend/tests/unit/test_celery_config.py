"""Unit tests for Celery configuration, broker resilience, and error logging."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from kombu.exceptions import OperationalError

from iryx.core.celery_app import (
    celery_app,
    check_broker_connection,
    mask_broker_url,
)
from iryx.core.config import get_settings


def test_celery_app_configuration_parameters() -> None:
    """Verify Celery instance uses correct settings, serializers, timezone, and retry options."""
    settings = get_settings()

    assert celery_app.main == "iryx"
    assert celery_app.conf.broker_url == settings.celery_broker_url
    assert celery_app.conf.result_backend == settings.celery_result_backend
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.enable_utc is True
    assert celery_app.conf.broker_connection_retry_on_startup is True
    assert celery_app.conf.broker_connection_max_retries == 10
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.task_acks_late is True


def test_mask_broker_url_redacts_credentials() -> None:
    """Verify mask_broker_url redacts passwords and preserves safe endpoints."""
    url_with_pass = "redis://:secret_password@redis.internal:6379/0"
    masked = mask_broker_url(url_with_pass)
    assert "secret_password" not in masked
    assert "**" in masked
    assert "redis.internal:6379/0" in masked

    url_with_user_pass = "redis://user:p@ssword@localhost:6379/1"
    masked_user = mask_broker_url(url_with_user_pass)
    assert "p@ssword" not in masked_user
    assert "**" in masked_user
    assert "localhost:6379/1" in masked_user

    url_plain = "redis://localhost:6379/0"
    assert mask_broker_url(url_plain) == "redis://localhost:6379/0"


def test_check_broker_connection_success() -> None:
    """Verify check_broker_connection returns True when broker is accessible."""
    mock_conn = MagicMock()
    with patch.object(celery_app, "connection_for_read") as mock_conn_for_read:
        mock_conn_for_read.return_value.__enter__.return_value = mock_conn

        result = check_broker_connection(timeout=1.0)
        assert result is True
        mock_conn.ensure_connection.assert_called_once_with(max_retries=0, timeout=1.0)


def test_check_broker_connection_failure_logs_structured_json(caplog) -> None:
    """Verify check_broker_connection logs structured error without crashing on network failure."""
    mock_conn = MagicMock()
    mock_conn.ensure_connection.side_effect = OperationalError("Connection refused by target host")

    with patch.object(celery_app, "connection_for_read") as mock_conn_for_read:
        mock_conn_for_read.return_value.__enter__.return_value = mock_conn

        with caplog.at_level(logging.ERROR):
            result = check_broker_connection(timeout=0.5)

        assert result is False
        assert len(caplog.records) >= 1
        record = caplog.records[-1]
        assert "Échec de connexion au courtier Celery/Redis" in record.message
        assert hasattr(record, "context")
        assert "broker_url" in record.context
        assert record.context["error_type"] == "OperationalError"
        assert "Connection refused" in record.context["error"]


def test_evidence_schemas_serialization() -> None:
    """Verify EvidenceRead and IngestionRunRead schemas serialize valid entities."""
    import uuid
    from datetime import UTC, datetime

    from iryx.evidence.models import IngestionStatus
    from iryx.evidence.schemas import EvidenceRead, IngestionRunRead

    evidence_id = uuid.uuid4()
    case_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    ev_data = {
        "id": evidence_id,
        "case_id": case_id,
        "original_name": "evidence.raw",
        "file_size": 2048,
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "detected_type": "application/octet-stream",
        "imported_by": user_id,
        "created_at": now,
    }
    ev_schema = EvidenceRead.model_validate(ev_data)
    assert ev_schema.id == evidence_id
    assert ev_schema.file_size == 2048
    assert ev_schema.sha256 is not None

    run_id = uuid.uuid4()
    run_data = {
        "id": run_id,
        "evidence_id": evidence_id,
        "status": IngestionStatus.PROCESSING,
        "progress": 75,
        "error_message": None,
        "started_at": now,
        "completed_at": None,
    }
    run_schema = IngestionRunRead.model_validate(run_data)
    assert run_schema.id == run_id
    assert run_schema.progress == 75
    assert run_schema.status == IngestionStatus.PROCESSING


def test_evidence_schemas_validation_errors() -> None:
    """Verify EvidenceRead rejects empty original_name and negative file_size."""
    import uuid
    from datetime import UTC, datetime

    from pydantic import ValidationError

    from iryx.evidence.schemas import EvidenceRead

    base_data = {
        "id": uuid.uuid4(),
        "case_id": uuid.uuid4(),
        "original_name": "valid.bin",
        "file_size": 100,
        "created_at": datetime.now(UTC),
    }

    # Empty original_name
    with pytest.raises(ValidationError):
        EvidenceRead.model_validate({**base_data, "original_name": ""})

    # Negative file_size
    with pytest.raises(ValidationError):
        EvidenceRead.model_validate({**base_data, "file_size": -1})
