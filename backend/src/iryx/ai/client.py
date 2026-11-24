"""Unified OpenAI LLM Client with Tenacity Retries and Secret Masking (Story 5.1).

Conforms to ADR-0003, D-10, D-11, and NFR-SEC-06.
"""

import logging
from typing import Any

import openai
from openai import AsyncOpenAI
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from iryx.ai.schemas import LLMMessage, LLMRequest, LLMResponse, LLMRole
from iryx.core.config import Settings, get_settings
from iryx.core.exceptions import LLMServiceUnavailableException

logger = logging.getLogger("iryx.ai.client")

# Transient errors eligible for automatic retry with exponential backoff
TRANSIENT_ERRORS = (
    openai.RateLimitError,  # HTTP 429
    openai.InternalServerError,  # HTTP 500, 502, 503, 504
    openai.APITimeoutError,  # Request timeout
    openai.APIConnectionError,  # Network connection failure
)


def _log_retry_attempt(retry_state: RetryCallState) -> None:
    """Log retry warnings without exposing any API keys or confidential data."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    exc_type = type(exc).__name__ if exc else "UnknownException"
    attempt = retry_state.attempt_number
    sleep_time = retry_state.next_action.sleep if retry_state.next_action else 0.0

    logger.warning(
        "LLM transient error encountered (attempt %d): %s. Retrying in %.1fs...",
        attempt,
        exc_type,
        sleep_time,
    )


class UnifiedLLMClient:
    """Unified OpenAI-compatible asynchronous client for IRYX AI agents.

    Configured per agent role with automatic Tenacity exponential backoff retries,
    strict secret masking, and translation to LLMServiceUnavailableException on failure.
    """

    def __init__(
        self,
        role: LLMRole | str | None = LLMRole.PLANNER,
        settings: Settings | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        retry_wait: Any | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        if role is None:
            self._role = LLMRole.PLANNER
        else:
            self._role = LLMRole(role) if isinstance(role, str) else role

        self._base_url = base_url or self._settings.openai_api_base
        self._api_key = api_key or self._settings.openai_api_key
        timeout_val = timeout if timeout is not None else self._settings.llm_timeout_seconds
        self._timeout = float(timeout_val)
        retries_val = max_retries if max_retries is not None else self._settings.llm_max_retries
        self._max_retries = int(retries_val)
        self._retry_wait = retry_wait

        self._model = model or self._resolve_model_for_role(self._role)

        # Initialize official AsyncOpenAI SDK client
        # max_retries=0 ensures that Tenacity exclusively controls the retry strategy
        self._client = AsyncOpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=self._timeout,
            max_retries=0,
        )

    @property
    def role(self) -> LLMRole:
        """Configured agent role."""
        return self._role

    @property
    def model(self) -> str:
        """Target model identifier for inference."""
        return self._model

    @property
    def base_url(self) -> str:
        """OpenAI-compatible API base URL."""
        return self._base_url

    @property
    def timeout(self) -> float:
        """Configured timeout in seconds."""
        return self._timeout

    @property
    def max_retries(self) -> int:
        """Maximum retry attempts."""
        return self._max_retries

    @property
    def api_key(self) -> str:
        """Masked API key (NFR-SEC-06)."""
        return "***"

    def _resolve_model_for_role(self, role: LLMRole | None) -> str:
        """Resolve model name from configuration settings based on agent role."""
        if role is None:
            return self._settings.planner_model
        match role:
            case LLMRole.PLANNER:
                return self._settings.planner_model
            case LLMRole.ANALYST:
                return self._settings.analyst_model
            case LLMRole.RAPPORTEUR:
                return self._settings.rapporteur_model
            case _:
                return self._settings.planner_model

    def for_role(self, role: LLMRole | str) -> "UnifiedLLMClient":
        """Return a client instance configured for another role, sharing settings."""
        role_enum = LLMRole(role) if isinstance(role, str) else role
        return UnifiedLLMClient(
            role=role_enum,
            settings=self._settings,
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=self._timeout,
            max_retries=self._max_retries,
            retry_wait=self._retry_wait,
        )

    def __repr__(self) -> str:
        """Safe representation masking the API key (NFR-SEC-06)."""
        return (
            f"UnifiedLLMClient(role={self._role.value!r}, "
            f"model={self._model!r}, "
            f"base_url={self._base_url!r}, "
            f"api_key='***')"
        )

    def __str__(self) -> str:
        """Safe string representation."""
        return f"UnifiedLLMClient(role={self._role.value}, model={self._model})"

    async def __aenter__(self) -> "UnifiedLLMClient":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> None:
        """Async context manager exit closing connection pools."""
        await self.close()

    async def _call_chat_completions(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int | None,
        response_format: dict[str, Any] | None,
    ) -> Any:
        """Internal invocation wrapped with Tenacity retry policy.

        stop_after_attempt(1 + max_retries) allows the initial attempt plus up to max_retries
        retries (e.g. 1 initial + 3 retries = 4 attempts total), reaching the 4s backoff.
        """
        wait_strategy = self._retry_wait or wait_exponential(multiplier=1, min=1, max=4)
        retrying = AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(1 + self._max_retries),
            wait=wait_strategy,
            retry=retry_if_exception_type(TRANSIENT_ERRORS),
            before_sleep=_log_retry_attempt,
        )

        async for attempt in retrying:
            with attempt:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                if response_format is not None:
                    kwargs["response_format"] = response_format

                return await self._client.chat.completions.create(**kwargs)

    async def complete(
        self,
        messages: list[LLMMessage | dict[str, Any]] | None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Execute chat completion with retry resilience and error handling.

        Raises:
            LLMServiceUnavailableException: On persistent failure or exhausted retries.
        """
        target_model = model or self._model

        # Normalize messages to dictionaries
        raw_messages: list[dict[str, Any]] = []
        if messages:
            for msg in messages:
                if msg is None:
                    continue
                if isinstance(msg, LLMMessage):
                    raw_messages.append({"role": msg.role, "content": msg.content})
                elif isinstance(msg, dict):
                    role_val = str(msg.get("role", "user"))
                    content_val = str(msg.get("content", ""))
                    raw_messages.append({"role": role_val, "content": content_val})
                else:
                    raw_messages.append({"role": "user", "content": str(msg)})

        try:
            raw_response = await self._call_chat_completions(
                messages=raw_messages,
                model=target_model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
        except TRANSIENT_ERRORS as exc:
            logger.error("LLM provider exhausted retries or failed: %s", type(exc).__name__)
            raise LLMServiceUnavailableException(
                message="Service d'inférence LLM temporairement indisponible.",
            ) from None
        except openai.APIError as exc:
            # Map other OpenAI API errors (e.g. auth, bad gateway) to 503 without leaking secrets
            logger.error("LLM API error encountered: %s", type(exc).__name__)
            raise LLMServiceUnavailableException(
                message="Service d'inférence LLM indisponible.",
            ) from None
        except Exception as exc:
            logger.error("Unexpected error in LLM client: %s", type(exc).__name__)
            raise LLMServiceUnavailableException(
                message="Erreur inattendue lors de la communication avec le service LLM.",
            ) from None

        choice = raw_response.choices[0] if raw_response.choices else None
        content = choice.message.content if choice and choice.message else ""
        finish_reason = choice.finish_reason if choice else None

        usage = getattr(raw_response, "usage", None)
        prompt_tokens = usage.prompt_tokens if usage else None
        completion_tokens = usage.completion_tokens if usage else None
        total_tokens = usage.total_tokens if usage else None

        return LLMResponse(
            content=content or "",
            role=choice.message.role if choice and choice.message else "assistant",
            model=getattr(raw_response, "model", target_model),
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    async def complete_request(self, request: LLMRequest) -> LLMResponse:
        """Execute completion from an LLMRequest schema instance."""
        target_model = self._resolve_model_for_role(request.role)
        return await self.complete(
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            response_format=request.response_format,
            model=target_model,
        )

    # Aliases for convenience
    generate = complete
    chat = complete

    async def close(self) -> None:
        """Close underlying HTTP client connection pools."""
        await self._client.close()


def get_llm_client(role: LLMRole = LLMRole.PLANNER) -> UnifiedLLMClient:
    """Dependency factory returning a UnifiedLLMClient configured for the given role."""
    return UnifiedLLMClient(role=role)
