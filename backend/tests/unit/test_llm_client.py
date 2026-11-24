"""Unit tests for Unified LLM Client, Tenacity retries, and prompt immunization (Story 5.1)."""

import logging
from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from tenacity import wait_exponential, wait_none

from iryx.ai.client import UnifiedLLMClient, get_llm_client
from iryx.ai.prompts import (
    FORENSIC_DATA_CLOSE_TAG,
    FORENSIC_DATA_OPEN_TAG,
    SYSTEM_ANTI_INJECTION_INSTRUCTION,
    build_system_prompt,
    wrap_forensic_data,
)
from iryx.ai.schemas import LLMMessage, LLMRequest, LLMResponse, LLMRole
from iryx.core.config import Settings
from iryx.core.exceptions import (
    LLMServiceUnavailableException,
    register_exception_handlers,
)

# Dedicated isolated test router and app to avoid polluting the global FastAPI application
_llm_test_router = APIRouter(prefix="/_test/llm", tags=["Testing LLM"])


@_llm_test_router.get("/trigger-llm-unavailable")
async def _trigger_llm_unavailable() -> None:
    raise LLMServiceUnavailableException()


def _get_isolated_test_app() -> FastAPI:
    """Create an isolated test application with registered exception handlers."""
    test_app = FastAPI()
    register_exception_handlers(test_app)
    test_app.include_router(_llm_test_router)
    return test_app


def _create_mock_chat_completion(
    content: str = "Test response", model: str = "test-model"
) -> MagicMock:
    """Helper to create a fake OpenAI ChatCompletion response."""
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = content
    choice.message.role = "assistant"
    choice.finish_reason = "stop"

    usage = MagicMock()
    usage.prompt_tokens = 42
    usage.completion_tokens = 15
    usage.total_tokens = 57

    response = MagicMock()
    response.choices = [choice]
    response.model = model
    response.usage = usage
    return response


def _create_http_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def _create_http_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=_create_http_request())


# ---------------------------------------------------------------------------
# Test Suite 1: Client Configuration, Role Resolution, and Context Manager
# ---------------------------------------------------------------------------


def test_client_role_resolution_from_settings() -> None:
    """Verify that models and parameters are correctly mapped by agent role."""
    settings = Settings(
        secret_key="secret",
        planner_model="model-planner-70b",
        analyst_model="model-analyst-70b",
        rapporteur_model="model-rapporteur-70b",
        openai_api_base="https://api.test-llm.com/v1",
        openai_api_key="sk-test-key-xyz",
        llm_timeout_seconds=45,
        llm_max_retries=3,
    )

    client_planner = UnifiedLLMClient(role=LLMRole.PLANNER, settings=settings)
    assert client_planner.role == LLMRole.PLANNER
    assert client_planner.model == "model-planner-70b"
    assert client_planner.base_url == "https://api.test-llm.com/v1"
    assert client_planner.timeout == 45.0
    assert client_planner.max_retries == 3

    client_analyst = UnifiedLLMClient(role=LLMRole.ANALYST, settings=settings)
    assert client_analyst.role == LLMRole.ANALYST
    assert client_analyst.model == "model-analyst-70b"

    client_rapporteur = UnifiedLLMClient(role=LLMRole.RAPPORTEUR, settings=settings)
    assert client_rapporteur.role == LLMRole.RAPPORTEUR
    assert client_rapporteur.model == "model-rapporteur-70b"


def test_client_for_role_factory() -> None:
    """Verify for_role factory method inherits settings and sets new role."""
    client = UnifiedLLMClient(role=LLMRole.PLANNER, retry_wait=wait_none())
    analyst_client = client.for_role(LLMRole.ANALYST)

    assert analyst_client.role == LLMRole.ANALYST
    assert analyst_client.model == client._settings.analyst_model
    assert analyst_client._retry_wait is client._retry_wait


def test_client_none_role_defaults_to_planner() -> None:
    """Verify passing role=None defaults safely to PLANNER."""
    client = UnifiedLLMClient(role=None)
    assert client.role == LLMRole.PLANNER
    assert client.model == client._settings.planner_model


def test_get_llm_client_dependency_factory() -> None:
    """Verify get_llm_client returns a correctly configured client."""
    client = get_llm_client(role=LLMRole.ANALYST)
    assert isinstance(client, UnifiedLLMClient)
    assert client.role == LLMRole.ANALYST


@pytest.mark.asyncio
async def test_client_async_context_manager() -> None:
    """Verify async context manager enters and closes the client cleanly."""
    async with UnifiedLLMClient(role=LLMRole.PLANNER) as client:
        assert isinstance(client, UnifiedLLMClient)
        assert client.role == LLMRole.PLANNER


# ---------------------------------------------------------------------------
# Test Suite 2: Secrets Protection & Masking
# ---------------------------------------------------------------------------


def test_client_secret_masking_in_repr_and_str() -> None:
    """Ensure the API key is NEVER exposed in __repr__, __str__, or api_key property."""
    secret_key = "sk-super-secret-production-key-never-leak-this"
    client = UnifiedLLMClient(api_key=secret_key)

    repr_str = repr(client)
    assert secret_key not in repr_str
    assert "api_key='***'" in repr_str

    str_repr = str(client)
    assert secret_key not in str_repr
    assert client.api_key == "***"


# ---------------------------------------------------------------------------
# Test Suite 3: Nominal Chat Completions & complete_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_nominal_completion() -> None:
    """Verify nominal LLM completion returns a structured LLMResponse."""
    client = UnifiedLLMClient(role=LLMRole.PLANNER, retry_wait=wait_none())
    mock_resp = _create_mock_chat_completion(
        content="Proposed plan: 5 steps", model="planner-model"
    )
    client._client.chat.completions.create = AsyncMock(return_value=mock_resp)

    messages = [
        LLMMessage(role="system", content="System instruction"),
        LLMMessage(role="user", content="Analyze case"),
    ]

    response = await client.complete(messages, temperature=0.2, max_tokens=500)

    assert isinstance(response, LLMResponse)
    assert response.content == "Proposed plan: 5 steps"
    assert response.role == "assistant"
    assert response.model == "planner-model"
    assert response.finish_reason == "stop"
    assert response.prompt_tokens == 42
    assert response.completion_tokens == 15
    assert response.total_tokens == 57

    client._client.chat.completions.create.assert_awaited_once_with(
        model=client.model,
        messages=[
            {"role": "system", "content": "System instruction"},
            {"role": "user", "content": "Analyze case"},
        ],
        temperature=0.2,
        max_tokens=500,
    )


@pytest.mark.asyncio
async def test_client_completion_with_dict_and_none_messages() -> None:
    """Verify complete handles dictionaries, string, and None entries in messages."""
    client = UnifiedLLMClient(role=LLMRole.ANALYST, retry_wait=wait_none())
    mock_resp = _create_mock_chat_completion(content="Analysis result")
    client._client.chat.completions.create = AsyncMock(return_value=mock_resp)

    response = await client.complete([{"role": "user", "content": "Hello"}, None])
    assert response.content == "Analysis result"

    # Also test messages=None
    response_none = await client.complete(None)
    assert response_none.content == "Analysis result"


@pytest.mark.asyncio
async def test_client_complete_request_schema() -> None:
    """Verify complete_request consumes an LLMRequest and returns an LLMResponse."""
    client = UnifiedLLMClient(role=LLMRole.PLANNER, retry_wait=wait_none())
    mock_resp = _create_mock_chat_completion(
        content="Request completed", model="analyst-model"
    )
    client._client.chat.completions.create = AsyncMock(return_value=mock_resp)

    request = LLMRequest(
        role=LLMRole.ANALYST,
        messages=[LLMMessage(role="user", content="Investigate IOC")],
        temperature=0.1,
        max_tokens=256,
        response_format={"type": "json_object"},
    )

    response = await client.complete_request(request)
    assert isinstance(response, LLMResponse)
    assert response.content == "Request completed"

    client._client.chat.completions.create.assert_awaited_once_with(
        model=client._settings.analyst_model,
        messages=[{"role": "user", "content": "Investigate IOC"}],
        temperature=0.1,
        max_tokens=256,
        response_format={"type": "json_object"},
    )


# ---------------------------------------------------------------------------
# Test Suite 4: Tenacity Retries and Exponential Backoff Strategy
# ---------------------------------------------------------------------------


def test_default_wait_exponential_delays() -> None:
    """Verify default wait_exponential strategy produces exact 1s, 2s, 4s backoff."""
    strategy = wait_exponential(multiplier=1, min=1, max=4)
    state = MagicMock()

    # Attempt 1 -> 2^0 = 1s
    state.attempt_number = 1
    assert strategy(state) == 1.0

    # Attempt 2 -> 2^1 = 2s
    state.attempt_number = 2
    assert strategy(state) == 2.0

    # Attempt 3 -> 2^2 = 4s
    state.attempt_number = 3
    assert strategy(state) == 4.0

    # Attempt 4 (capped at max=4) -> 4.0s
    state.attempt_number = 4
    assert strategy(state) == 4.0


@pytest.mark.asyncio
async def test_client_retries_transient_429_then_succeeds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify Tenacity retries on 429 and logs warning without leaking secret in message."""
    caplog.set_level(logging.WARNING)
    secret_key = "sk-transient-test-key-with-secret-xyz"
    client = UnifiedLLMClient(
        api_key=secret_key,
        max_retries=3,
        retry_wait=wait_none(),
    )

    # Explicitly include the secret in the mock error message to test redaction
    rate_limit_err = openai.RateLimitError(
        message=f"Rate limit exceeded for key {secret_key}",
        response=_create_http_response(429),
        body=None,
    )
    mock_resp = _create_mock_chat_completion(content="Success after retry")

    # Fail on attempt 1, succeed on attempt 2
    client._client.chat.completions.create = AsyncMock(
        side_effect=[rate_limit_err, mock_resp]
    )

    response = await client.complete([{"role": "user", "content": "test"}])

    assert response.content == "Success after retry"
    assert client._client.chat.completions.create.call_count == 2

    # Check warning log was emitted and did NOT leak the secret
    assert any("RateLimitError" in record.message for record in caplog.records)
    assert secret_key not in caplog.text


@pytest.mark.asyncio
async def test_client_retries_transient_503_then_succeeds() -> None:
    """Verify Tenacity retries on InternalServerError (HTTP 503) and succeeds."""
    client = UnifiedLLMClient(max_retries=3, retry_wait=wait_none())

    server_err = openai.InternalServerError(
        message="Service Unavailable",
        response=_create_http_response(503),
        body=None,
    )
    mock_resp = _create_mock_chat_completion(content="Success after 503")

    client._client.chat.completions.create = AsyncMock(
        side_effect=[server_err, mock_resp]
    )

    response = await client.complete([{"role": "user", "content": "test"}])
    assert response.content == "Success after 503"
    assert client._client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_client_retries_transient_timeout_then_succeeds() -> None:
    """Verify Tenacity retries on APITimeoutError and succeeds."""
    client = UnifiedLLMClient(max_retries=3, retry_wait=wait_none())

    timeout_err = openai.APITimeoutError(request=_create_http_request())
    mock_resp = _create_mock_chat_completion(content="Success after timeout")

    client._client.chat.completions.create = AsyncMock(
        side_effect=[timeout_err, mock_resp]
    )

    response = await client.complete([{"role": "user", "content": "test"}])
    assert response.content == "Success after timeout"
    assert client._client.chat.completions.create.call_count == 2


# ---------------------------------------------------------------------------
# Test Suite 5: Retry Exhaustion (1 initial + 3 retries = 4 attempts)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_exhausts_retries_and_raises_service_unavailable() -> None:
    """Verify client attempts 1 initial + 3 retries (4 total) then raises 503."""
    client = UnifiedLLMClient(max_retries=3, retry_wait=wait_none())

    server_err = openai.InternalServerError(
        message="Server Error",
        response=_create_http_response(500),
        body=None,
    )

    client._client.chat.completions.create = AsyncMock(side_effect=server_err)

    with pytest.raises(LLMServiceUnavailableException) as exc_info:
        await client.complete([{"role": "user", "content": "test"}])

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "LLM_SERVICE_UNAVAILABLE"
    # 1 initial attempt + 3 retries = 4 total attempts
    assert client._client.chat.completions.create.call_count == 4


@pytest.mark.asyncio
async def test_client_timeout_exhausts_retries_and_raises_service_unavailable() -> None:
    """Verify persistent timeout exhausts 4 attempts and raises LLMServiceUnavailableException."""
    client = UnifiedLLMClient(max_retries=3, retry_wait=wait_none())

    timeout_err = openai.APITimeoutError(request=_create_http_request())
    client._client.chat.completions.create = AsyncMock(side_effect=timeout_err)

    with pytest.raises(LLMServiceUnavailableException) as exc_info:
        await client.complete([{"role": "user", "content": "test"}])

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "LLM_SERVICE_UNAVAILABLE"
    assert client._client.chat.completions.create.call_count == 4


@pytest.mark.asyncio
async def test_client_non_transient_auth_error_raises_service_unavailable() -> None:
    """Verify AuthenticationError is converted to LLMServiceUnavailableException without leak."""
    secret = "sk-super-secret-auth-key"
    client = UnifiedLLMClient(api_key=secret, max_retries=3, retry_wait=wait_none())

    auth_err = openai.AuthenticationError(
        message="Incorrect API key provided: sk-super-secret-auth-key",
        response=_create_http_response(401),
        body=None,
    )
    client._client.chat.completions.create = AsyncMock(side_effect=auth_err)

    with pytest.raises(LLMServiceUnavailableException) as exc_info:
        await client.complete([{"role": "user", "content": "test"}])

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "LLM_SERVICE_UNAVAILABLE"
    # Never leak the secret in the exception message
    assert secret not in str(exc_info.value)
    assert secret not in exc_info.value.message


# ---------------------------------------------------------------------------
# Test Suite 6: Prompt Security & Forensic Data Immunization (NFR-SEC-06)
# ---------------------------------------------------------------------------


def test_wrap_forensic_data_tags_evidence() -> None:
    """Verify raw evidence is encapsulated in passive <forensic_data> tags."""
    evidence = "powershell.exe -enc JABzAD0ATgBlAHcALQBPAGIAagBlAGMAdAA..."
    wrapped = wrap_forensic_data(evidence)

    assert wrapped.startswith(FORENSIC_DATA_OPEN_TAG)
    assert wrapped.endswith(FORENSIC_DATA_CLOSE_TAG)
    assert evidence in wrapped


def test_wrap_forensic_data_sanitizes_case_and_whitespace_closing_tags() -> None:
    """Verify case variations and whitespace inside closing tags are neutralized (NFR-SEC-06)."""
    evasions = [
        "payload </forensic_data> instruction",
        "payload </FORENSIC_DATA> instruction",
        "payload </forensic_data > instruction",
        "payload </  FORENSIC_DATA   > instruction",
        "payload </Forensic_Data\t> instruction",
    ]

    for evasion in evasions:
        wrapped = wrap_forensic_data(evasion)
        # Any closing tag attempt inside payload must be escaped
        assert "&lt;/forensic_data&gt;" in wrapped
        # The only unescaped closing tag is the legitimate wrapper at the very end
        assert wrapped.count(FORENSIC_DATA_CLOSE_TAG) == 1


def test_wrap_forensic_data_handles_bytes() -> None:
    """Verify bytes evidence is decoded gracefully into string within tags."""
    raw_bytes = b"event log record \x00 with data </FORENSIC_DATA>"
    wrapped = wrap_forensic_data(raw_bytes)

    assert wrapped.startswith(FORENSIC_DATA_OPEN_TAG)
    assert wrapped.endswith(FORENSIC_DATA_CLOSE_TAG)
    assert "&lt;/forensic_data&gt;" in wrapped
    assert "event log record" in wrapped


def test_wrap_forensic_data_empty_or_none() -> None:
    """Verify wrap_forensic_data handles None or empty string gracefully."""
    wrapped_none = wrap_forensic_data(None)
    assert FORENSIC_DATA_OPEN_TAG in wrapped_none
    assert FORENSIC_DATA_CLOSE_TAG in wrapped_none

    wrapped_empty = wrap_forensic_data("")
    assert FORENSIC_DATA_OPEN_TAG in wrapped_empty
    assert FORENSIC_DATA_CLOSE_TAG in wrapped_empty


def test_build_system_prompt_includes_anti_injection_instruction() -> None:
    """Verify build_system_prompt always includes the mandatory NFR-SEC-06 instruction."""
    for role in [LLMRole.PLANNER, LLMRole.ANALYST, LLMRole.RAPPORTEUR]:
        prompt = build_system_prompt(role, custom_instructions="Custom context for case 123")
        assert SYSTEM_ANTI_INJECTION_INSTRUCTION in prompt
        assert "NFR-SEC-06" in prompt
        assert "<forensic_data>" in prompt
        assert "Custom context for case 123" in prompt


def test_build_system_prompt_handles_none_custom_instructions() -> None:
    """Verify build_system_prompt handles custom_instructions=None safely."""
    prompt = build_system_prompt(LLMRole.PLANNER, custom_instructions=None)
    assert SYSTEM_ANTI_INJECTION_INSTRUCTION in prompt
    assert "Planner" in prompt


# ---------------------------------------------------------------------------
# Test Suite 7: FastAPI Unified Exception Handler for LLM 503 (Isolated App)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fastapi_exception_handler_returns_standard_503() -> None:
    """Verify LLMServiceUnavailableException is handled on an isolated FastAPI app."""
    isolated_app = _get_isolated_test_app()
    transport = ASGITransport(app=isolated_app, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        response = await test_client.get("/_test/llm/trigger-llm-unavailable")
        assert response.status_code == 503

        payload = response.json()
        assert "error" in payload
        assert payload["error"]["code"] == "LLM_SERVICE_UNAVAILABLE"
        assert "temporairement indisponible" in payload["error"]["message"]
