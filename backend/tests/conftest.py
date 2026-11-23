"""Pytest configuration and shared fixtures for IRYX."""

import os
from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# Ensure required environment variables are set for all test runs
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-testing-32-chars-min"
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "DEBUG"

from iryx.core.config import get_settings  # noqa: E402
from iryx.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Clear settings cache before each test to guarantee test isolation."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client fixture with disabled exception re-raising for status verification."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def client() -> TestClient:
    """Synchronous Starlette TestClient fixture with disabled server exception re-raising."""
    return TestClient(app, raise_server_exceptions=False)
