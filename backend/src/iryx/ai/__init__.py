"""IRYX AI Module Exports (ADR-0003, Story 5.1)."""

from iryx.ai.client import UnifiedLLMClient, get_llm_client
from iryx.ai.prompts import (
    FORENSIC_DATA_CLOSE_TAG,
    FORENSIC_DATA_OPEN_TAG,
    SYSTEM_ANTI_INJECTION_INSTRUCTION,
    build_system_prompt,
    wrap_forensic_data,
)
from iryx.ai.schemas import LLMMessage, LLMRequest, LLMResponse, LLMRole
from iryx.core.exceptions import LLMServiceUnavailableException

__all__ = [
    "FORENSIC_DATA_CLOSE_TAG",
    "FORENSIC_DATA_OPEN_TAG",
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMRole",
    "LLMServiceUnavailableException",
    "SYSTEM_ANTI_INJECTION_INSTRUCTION",
    "UnifiedLLMClient",
    "build_system_prompt",
    "get_llm_client",
    "wrap_forensic_data",
]
