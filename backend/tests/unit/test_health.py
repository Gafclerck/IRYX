"""Tests for the /health endpoint."""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from iryx import __version__


@pytest.mark.asyncio
async def test_health_check_async(async_client: AsyncClient) -> None:
    """Verify GET /health returns HTTP 200 with status ok and version."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    data = response.json()
    assert data == {"status": "ok", "version": __version__}
    assert data["version"] == "0.1.0"


def test_health_check_sync(client: TestClient) -> None:
    """Verify GET /health works synchronously via TestClient."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
