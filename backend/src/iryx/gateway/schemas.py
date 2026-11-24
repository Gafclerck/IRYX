"""Pydantic v2 schemas for Forensic Gateway tool executions and observations."""

import contextlib
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iryx.gateway.models import ToolExecutionStatus


class ToolExecutionRead(BaseModel):
    """Schema for serialized ToolExecution audit records."""

    id: uuid.UUID
    case_id: uuid.UUID
    tool_name: str
    tool_version: str
    agent_role: str
    parameters: dict[str, Any]
    result_sha256: str | None = None
    duration_ms: int
    status: ToolExecutionStatus
    error_message: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ToolExecutionCreate(BaseModel):
    """Request payload to invoke a forensic tool."""

    case_id: uuid.UUID
    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    agent_role: str = "Executor"


class ObservationRead(BaseModel):
    """Schema for serialized Observation entities."""

    id: uuid.UUID
    case_id: uuid.UUID
    source_id: uuid.UUID | None = None
    tool_name: str
    tool_execution_id: uuid.UUID | None = None
    normalized_content: dict[str, Any]
    timestamp_utc: datetime | None = None
    source_location: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ObservationCreate(BaseModel):
    """Payload to create a normalized technical fact observation."""

    case_id: uuid.UUID
    source_id: uuid.UUID | None = None
    tool_name: str
    tool_execution_id: uuid.UUID | None = None
    normalized_content: dict[str, Any] = Field(default_factory=dict)
    timestamp_utc: datetime | None = None
    source_location: str | None = None


class ToolMetadataResponse(BaseModel):
    """Metadata response describing a registered forensic tool."""

    name: str
    version: str
    description: str
    timeout_seconds: int
    parameters_schema: dict[str, Any] = Field(default_factory=dict)


class AgentPayload(BaseModel):
    """Context-bounded projection of tool execution results for LLM agents."""

    observations: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    is_truncated: bool = False
    truncated_count: int = 0


class ToolExecutionListResponse(BaseModel):
    """Paginated collection of tool execution records."""

    items: list[ToolExecutionRead]
    total: int = Field(..., ge=0)
    total_items: int = Field(default=0, ge=0)
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)
    has_more: bool

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_total_items(cls, data: Any) -> Any:
        """Ensure total_items is populated from total when missing."""
        if isinstance(data, dict) and data.get("total_items") is None and "total" in data:
            data["total_items"] = data["total"]
        elif hasattr(data, "total") and getattr(data, "total_items", None) is None:
            with contextlib.suppress(AttributeError, TypeError):
                data.total_items = data.total
        return data


class ObservationListResponse(BaseModel):
    """Paginated collection of normalized forensic observations."""

    items: list[ObservationRead]
    total: int = Field(..., ge=0)
    total_items: int = Field(default=0, ge=0)
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)
    has_more: bool

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_total_items(cls, data: Any) -> Any:
        """Ensure total_items is populated from total when missing."""
        if isinstance(data, dict) and data.get("total_items") is None and "total" in data:
            data["total_items"] = data["total"]
        elif hasattr(data, "total") and getattr(data, "total_items", None) is None:
            with contextlib.suppress(AttributeError, TypeError):
                data.total_items = data.total
        return data
