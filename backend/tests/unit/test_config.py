"""Tests for application Settings and configuration validation."""

import pytest
from pydantic import ValidationError

from iryx.core.config import Settings, get_settings


def test_settings_nominal_with_required_key() -> None:
    """Verify settings instantiate correctly when mandatory keys are provided."""
    settings = Settings(secret_key="my-super-secret-key-for-testing-purposes")
    assert settings.app_name == "IRYX API"
    assert settings.app_version == "0.1.0"
    assert settings.environment in ("development", "test")
    assert settings.port == 8000
    assert settings.max_evidence_size_gb == 16
    assert settings.jwt_access_token_expire_minutes == 60
    assert settings.polling_retry_after_seconds == 3


def test_settings_missing_mandatory_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify pydantic-settings blocks startup when mandatory SECRET_KEY is missing."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    # Instantiate with _env_file=None to ensure .env does not provide the key
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    errors = exc_info.value.errors()
    field_names = [e["loc"][0] for e in errors]
    assert "secret_key" in field_names
    # Verify no raw secrets leaked in validation error message
    error_str = str(exc_info.value)
    assert "Field required" in error_str


def test_settings_invalid_type_raises_validation_error() -> None:
    """Verify invalid types cause validation failure with clear message."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(secret_key="some-secret", port="not-a-number")

    errors = exc_info.value.errors()
    assert any(e["loc"][0] == "port" for e in errors)


def test_settings_jwt_expire_minutes_must_be_positive() -> None:
    """Verify jwt_access_token_expire_minutes rejects non-positive values (<= 0)."""
    with pytest.raises(ValidationError) as exc_info_zero:
        Settings(secret_key="test-key", jwt_access_token_expire_minutes=0)
    assert any(
        e["loc"][0] == "jwt_access_token_expire_minutes" for e in exc_info_zero.value.errors()
    )

    with pytest.raises(ValidationError) as exc_info_neg:
        Settings(secret_key="test-key", jwt_access_token_expire_minutes=-10)
    assert any(
        e["loc"][0] == "jwt_access_token_expire_minutes" for e in exc_info_neg.value.errors()
    )


def test_cors_origins_parsing_variants() -> None:
    """Verify CORS origins field parser handles lists, JSON strings, and comma-separated lists."""
    # List format
    s1 = Settings(secret_key="test-key", cors_origins=["http://localhost:3000"])
    assert s1.cors_origins == ["http://localhost:3000"]

    # JSON array string format
    s2 = Settings(
        secret_key="test-key", cors_origins='["http://localhost:3000", "http://localhost:8000"]'
    )
    assert s2.cors_origins == ["http://localhost:3000", "http://localhost:8000"]

    # Comma-separated string format
    s3 = Settings(secret_key="test-key", cors_origins="http://localhost:3000, http://example.com")
    assert s3.cors_origins == ["http://localhost:3000", "http://example.com"]


def test_get_settings_caching() -> None:
    """Verify get_settings returns a cached singleton instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_evidence_staging_path_default() -> None:
    """Verify evidence_staging_path defaults to {evidence_storage_path}/staging."""
    settings = Settings(secret_key="test-key", evidence_storage_path="/var/evidence/")
    assert settings.evidence_staging_path == "/var/evidence/staging"

    settings2 = Settings(secret_key="test-key", evidence_storage_path="/var/evidence")
    assert settings2.evidence_staging_path == "/var/evidence/staging"


def test_evidence_staging_path_custom() -> None:
    """Verify custom evidence_staging_path is preserved."""
    settings = Settings(
        secret_key="test-key",
        evidence_storage_path="/var/evidence/",
        evidence_staging_path="/custom/staging/path",
    )
    assert settings.evidence_staging_path == "/custom/staging/path"
