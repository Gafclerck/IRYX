"""Forensic Gateway Package."""

from iryx.analytics.models import Observation
from iryx.gateway.base import BaseTool, ToolExecutionContext, ToolExecutionResult
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.gateway.registry import ToolRegistry, default_registry, get_tool_registry
from iryx.gateway.runner import ToolRunner, compute_sha256, run_command_safely
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

__all__ = [
    "AUTHORIZED_PLUGINS",
    "BaseTool",
    "DEFAULT_KEY_PATHS",
    "EvtxParserParameters",
    "EvtxParserTool",
    "LogCsvParserParameters",
    "LogCsvParserTool",
    "Observation",
    "PrefetchParserParameters",
    "PrefetchParserTool",
    "PrefetchParsingError",
    "RegistryHiveParsingError",
    "RegistryParserParameters",
    "RegistryParserTool",
    "ToolExecution",
    "ToolExecutionContext",
    "ToolExecutionResult",
    "ToolExecutionStatus",
    "ToolRegistry",
    "ToolRunner",
    "Volatility3Parameters",
    "Volatility3Tool",
    "VolatilityExecutionError",
    "compute_sha256",
    "default_registry",
    "get_tool_registry",
    "run_command_safely",
]
