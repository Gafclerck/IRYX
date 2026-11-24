"""Forensic Gateway Package."""

from iryx.analytics.models import Observation
from iryx.gateway.base import BaseTool, ToolExecutionContext, ToolExecutionResult
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.gateway.registry import ToolRegistry, default_registry, get_tool_registry
from iryx.gateway.runner import ToolRunner, compute_sha256, run_command_safely
from iryx.gateway.schemas import (
    AgentPayload,
    ObservationCreate,
    ObservationListResponse,
    ObservationRead,
    ToolExecutionCreate,
    ToolExecutionListResponse,
    ToolExecutionRead,
    ToolMetadataResponse,
)
from iryx.gateway.tools.evtx_parser import EvtxParserParameters, EvtxParserTool
from iryx.gateway.tools.log_parser import LogCsvParserParameters, LogCsvParserTool
from iryx.gateway.tools.prefetch_parser import (
    PrefetchParserParameters,
    PrefetchParserTool,
    PrefetchParsingError,
)
from iryx.gateway.tools.registry_parser import (
    DEFAULT_KEY_PATHS,
    RegistryHiveParsingError,
    RegistryParserParameters,
    RegistryParserTool,
)
from iryx.gateway.tools.volatility_analyzer import (
    AUTHORIZED_PLUGINS,
    Volatility3Parameters,
    Volatility3Tool,
    VolatilityExecutionError,
)
from iryx.gateway.truncation import (
    MAX_AGENT_OBSERVATIONS,
    MAX_SUMMARY_BYTES,
    MAX_SUMMARY_LINES,
    truncate_for_agent,
)


def __getattr__(name: str) -> object:
    """Lazy-load router to avoid circular import during model mapper initialization."""
    if name == "router":
        from iryx.gateway.router import router

        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AUTHORIZED_PLUGINS",
    "AgentPayload",
    "BaseTool",
    "DEFAULT_KEY_PATHS",
    "EvtxParserParameters",
    "EvtxParserTool",
    "LogCsvParserParameters",
    "LogCsvParserTool",
    "MAX_AGENT_OBSERVATIONS",
    "MAX_SUMMARY_BYTES",
    "MAX_SUMMARY_LINES",
    "Observation",
    "ObservationCreate",
    "ObservationListResponse",
    "ObservationRead",
    "PrefetchParserParameters",
    "PrefetchParserTool",
    "PrefetchParsingError",
    "RegistryHiveParsingError",
    "RegistryParserParameters",
    "RegistryParserTool",
    "ToolExecution",
    "ToolExecutionContext",
    "ToolExecutionCreate",
    "ToolExecutionListResponse",
    "ToolExecutionRead",
    "ToolExecutionResult",
    "ToolExecutionStatus",
    "ToolMetadataResponse",
    "ToolRegistry",
    "ToolRunner",
    "Volatility3Parameters",
    "Volatility3Tool",
    "VolatilityExecutionError",
    "compute_sha256",
    "default_registry",
    "get_tool_registry",
    "router",
    "run_command_safely",
    "truncate_for_agent",
]
