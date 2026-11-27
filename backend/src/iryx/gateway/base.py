"""Base classes and execution contracts for forensic tools."""

import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iryx.core.config import get_settings
from iryx.core.exceptions import ValidationException
from iryx.gateway.models import ToolExecutionStatus


def resolve_confined_evidence_path(raw_path: str | Path) -> Path:
    """Resolve a file path and ensure it stays confined within evidence storage or staging."""
    if isinstance(raw_path, str) and not raw_path.strip():
        raise ValidationException("Chemin de fichier non autorisé ou hors périmètre: ''.")

    settings = get_settings()
    resolved = Path(raw_path).resolve()
    raw_allowed = (settings.evidence_storage_path, settings.evidence_staging_path)
    allowed_dirs = tuple(
        Path(d).resolve() for d in raw_allowed if isinstance(d, str) and d.strip()
    )
    if not allowed_dirs or not any(resolved.is_relative_to(allowed_dir) for allowed_dir in allowed_dirs):
        raise ValidationException(
            f"Chemin de fichier non autorisé ou hors périmètre: '{raw_path}'."
        )
    return resolved


class ToolExecutionContext(BaseModel):
    """Runtime context passed to a forensic tool during execution."""

    case_id: uuid.UUID
    agent_role: str = "Executor"
    evidence_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ToolExecutionResult(BaseModel):
    """Standardized result returned by a forensic tool execution."""

    raw_output: Any = Field(default=None)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0
    status: ToolExecutionStatus = ToolExecutionStatus.SUCCESS
    error_message: str | None = None
    result_sha256: str | None = None
    tool_execution_id: uuid.UUID | None = None
    agent_payload: Any = Field(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="before")
    @classmethod
    def _map_output_alias(cls, data: Any) -> Any:
        if isinstance(data, dict) and "output" in data and "raw_output" not in data:
            data = dict(data)
            data["raw_output"] = data.pop("output")
        return data

    @property
    def output(self) -> Any:
        return self.raw_output

    def to_agent_payload(self) -> Any:
        """Project tool execution results to context-bounded payload for LLM agents."""
        if self.agent_payload is not None:
            return self.agent_payload
        from iryx.gateway.truncation import truncate_for_agent

        self.agent_payload = truncate_for_agent(
            observations=self.observations,
            raw_output=self.raw_output,
        )
        return self.agent_payload


class BaseTool(ABC):
    """Abstract base class defining the contract for all IRYX forensic tools."""

    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    timeout_seconds: int = 60
    parameters_schema: type[BaseModel]

    def __init__(
        self,
        name: str | None = None,
        version: str | None = None,
        description: str | None = None,
        timeout_seconds: int | None = None,
        parameters_schema: type[BaseModel] | None = None,
    ) -> None:
        if name is not None:
            self.name = name
        if version is not None:
            self.version = version
        if description is not None:
            self.description = description
        if timeout_seconds is not None:
            self.timeout_seconds = timeout_seconds
        if parameters_schema is not None:
            self.parameters_schema = parameters_schema

    @abstractmethod
    async def execute(
        self,
        params: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute the forensic tool logic under controlled environment."""
        pass
