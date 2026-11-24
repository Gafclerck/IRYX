"""Pydantic v2 schemas for Forensic Gateway tool executions and observations."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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
