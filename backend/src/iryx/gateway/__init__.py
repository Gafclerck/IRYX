"""Forensic Gateway Package."""

from iryx.analytics.models import Observation
from iryx.gateway.base import BaseTool, ToolExecutionContext, ToolExecutionResult
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.gateway.registry import ToolRegistry, default_registry, get_tool_registry
from iryx.gateway.runner import ToolRunner, compute_sha256, run_command_safely
from iryx.gateway.tools.evtx_parser import EvtxParserParameters, EvtxParserTool
from iryx.gateway.tools.log_parser import LogCsvParserParameters, LogCsvParserTool
from iryx.gateway.tools.registry_parser import (
    DEFAULT_KEY_PATHS,
    RegistryHiveParsingError,
    RegistryParserParameters,
    RegistryParserTool,
)

__all__ = [
    "BaseTool",
    "DEFAULT_KEY_PATHS",
    "EvtxParserParameters",
    "EvtxParserTool",
    "LogCsvParserParameters",
    "LogCsvParserTool",
    "Observation",
    "RegistryHiveParsingError",
    "RegistryParserParameters",
    "RegistryParserTool",
    "ToolExecution",
    "ToolExecutionContext",
    "ToolExecutionResult",
    "ToolExecutionStatus",
    "ToolRegistry",
    "ToolRunner",
    "compute_sha256",
    "default_registry",
    "get_tool_registry",
    "run_command_safely",
]
