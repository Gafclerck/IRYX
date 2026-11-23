"""IRYX Application Configuration via Pydantic Settings."""

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized, typed, immutable application settings."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core Application Settings
    app_name: str = "IRYX API"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    log_level: str = "INFO"

    # Security & Authentication (ADR-0006)
    secret_key: str = Field(..., description="Application secret key (mandatory)")
    jwt_secret_key: str = "change-me-in-production-use-a-strong-jwt-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 480

    # Database Configuration (D-05, D-06)
    database_url: str = "postgresql+psycopg://iryx:iryx_password@localhost:5432/iryx_db"

    # Celery & Redis (D-08)
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # Evidence Storage (ADR-0005, ADR-0010)
    evidence_storage_path: str = "/data/evidence/"
    max_evidence_size_gb: int = 16

    # LLM Settings (D-10, D-11)
    openai_api_base: str = "https://api.groq.com/openai/v1"
    openai_api_key: str = "dummy-key-for-local-dev"
    planner_model: str = "llama-3.3-70b-versatile"
    analyst_model: str = "llama-3.3-70b-versatile"
    rapporteur_model: str = "llama-3.3-70b-versatile"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 3

    # Polling & Protocol (ADR-0008, D-24)
    polling_retry_after_seconds: int = 3

    # Volatility 3 (D-26)
    volatility_symbols_path: str = "/opt/volatility3/symbols"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Parse and normalize CORS origins (strip whitespace and trailing slashes)."""
        if isinstance(v, str):
            v_stripped = v.strip()
            if v_stripped.startswith("[") and v_stripped.endswith("]"):
                import json

                origins = json.loads(v_stripped)
                return [
                    str(origin).strip().rstrip("/") for origin in origins if str(origin).strip()
                ]
            return [origin.strip().rstrip("/") for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(origin).strip().rstrip("/") for origin in v if str(origin).strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
