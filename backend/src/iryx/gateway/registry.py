"""Centralized tool registry with strict whitelist and duplicate prevention."""

import logging
from collections.abc import Iterable

from iryx.core.exceptions import PluginNotWhitelistedException, ToolNotFoundException
from iryx.gateway.base import BaseTool

logger = logging.getLogger("iryx.gateway.registry")

# Strict MVP whitelisted tools per documentation (02-agents-et-outils.md)
MVP_TOOL_WHITELIST: frozenset[str] = frozenset(
    {
        "hash_sha256",
        "parse_text_logs",
        "parse_evtx",
        "parse_registry",
        "parse_execution",
        "analyze_memory",
    }
)


class ToolRegistry:
    """Registry maintaining authorized forensic tools with strict whitelist enforcement."""

    def __init__(
        self,
        whitelist: Iterable[str] | None = None,
        enforce_whitelist: bool = True,
    ) -> None:
        self.enforce_whitelist = enforce_whitelist
        self._whitelist: set[str] = (
            set(whitelist) if whitelist is not None else set(MVP_TOOL_WHITELIST)
        )
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a new tool instance in the registry.

        Raises:
            TypeError: If tool is not an instance of BaseTool.
            PluginNotWhitelistedException: If tool name is not in the authorized whitelist.
            ValueError: If tool name is empty or already registered.
        """
        if not isinstance(tool, BaseTool):
            raise TypeError(f"Expected BaseTool instance, got {type(tool).__name__}")

        if not tool.name or not tool.name.strip():
            raise ValueError("Tool name cannot be empty.")

        name = tool.name.strip()

        if self.enforce_whitelist and name not in self._whitelist:
            raise PluginNotWhitelistedException(
                f"L'outil '{name}' n'est pas autorisé par la liste blanche du registre."
            )

        if name in self._tools:
            raise ValueError(f"L'outil '{name}' est déjà enregistré dans le registre.")

        self._tools[name] = tool
        logger.info("Tool registered: %s (v%s)", name, tool.version)

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry.

        Raises:
            ToolNotFoundException: If tool is not registered.
        """
        if name not in self._tools:
            raise ToolNotFoundException(f"L'outil '{name}' n'est pas enregistré.")
        del self._tools[name]

    def get(self, name: str) -> BaseTool:
        """Retrieve a tool by name.

        Raises:
            ToolNotFoundException: If tool is not registered.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundException(f"L'outil '{name}' n'est pas enregistré dans le registre.")
        return tool

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def list_tools(self) -> list[BaseTool]:
        """Return list of all registered tools."""
        return list(self._tools.values())

    def list_tool_names(self) -> list[str]:
        """Return list of registered tool names."""
        return list(self._tools.keys())

    def add_to_whitelist(self, name: str) -> None:
        """Dynamically add an authorized tool name to the whitelist."""
        self._whitelist.add(name.strip())

    def is_whitelisted(self, name: str) -> bool:
        """Check if a tool name is authorized in the whitelist."""
        return name in self._whitelist

    def clear(self) -> None:
        """Clear all registered tools (primarily used for test cleanup)."""
        self._tools.clear()


# Default singleton instance
default_registry = ToolRegistry()


def _register_default_tools(registry: ToolRegistry) -> None:
    """Register all implemented built-in forensic tools."""
    from iryx.gateway.tools.evtx_parser import EvtxParserTool
    from iryx.gateway.tools.log_parser import LogCsvParserTool
    from iryx.gateway.tools.prefetch_parser import PrefetchParserTool
    from iryx.gateway.tools.registry_parser import RegistryParserTool

    registry.register(LogCsvParserTool())
    registry.register(EvtxParserTool())
    registry.register(RegistryParserTool())
    registry.register(PrefetchParserTool())


_register_default_tools(default_registry)


def get_tool_registry() -> ToolRegistry:
    """Dependency provider for tool registry."""
    return default_registry
