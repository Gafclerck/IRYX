"""IRYX AI Schemas and Data Models (D-04, ADR-0003, Story 5.1)."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LLMRole(StrEnum):
    """Supported specialized agent roles for LLM inference."""

    PLANNER = "planner"
    ANALYST = "analyst"
    RAPPORTEUR = "rapporteur"


class LLMMessage(BaseModel):
    """Individual chat completion message."""

    model_config = ConfigDict(frozen=True)

    role: str = Field(..., description="Role of the message author (system, user, assistant)")
    content: str = Field(..., description="Text content of the message")


class LLMRequest(BaseModel):
    """Normalized request payload for LLM completion."""

    role: LLMRole = Field(..., description="Agent role determining the model configuration")
    messages: list[LLMMessage] = Field(..., description="Prompt message sequence")
    temperature: float = Field(0.0, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int | None = Field(None, gt=0, description="Maximum tokens to generate")
    response_format: dict[str, Any] | None = Field(
        None, description="Optional structured output format (e.g. {'type': 'json_object'})"
    )


class LLMResponse(BaseModel):
    """Normalized response returned from LLM completion."""

    content: str = Field(..., description="Generated text content from the LLM")
    role: str = Field("assistant", description="Message role of the response")
    model: str = Field(..., description="Model identifier used for inference")
    finish_reason: str | None = Field(None, description="Reason the completion stopped")
    prompt_tokens: int | None = Field(None, description="Input prompt tokens consumed")
    completion_tokens: int | None = Field(None, description="Output tokens generated")
    total_tokens: int | None = Field(None, description="Total tokens consumed")
