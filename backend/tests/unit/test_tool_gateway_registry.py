"""Unit tests for ToolRegistry and BaseTool abstraction."""

import pytest
from pydantic import BaseModel

from iryx.core.exceptions import PluginNotWhitelistedException, ToolNotFoundException
from iryx.gateway.base import BaseTool, ToolExecutionContext, ToolExecutionResult
from iryx.gateway.registry import MVP_TOOL_WHITELIST, ToolRegistry


class DummySchema(BaseModel):
    query: str


class DummyTool(BaseTool):
    name = "hash_sha256"
    version = "1.0.0"
    description = "Dummy hashing tool for tests"
    timeout_seconds = 30
    parameters_schema = DummySchema

    async def execute(
        self,
        params: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(raw_output={"result": "ok"})


class NonWhitelistedTool(BaseTool):
    name = "arbitrary_custom_tool"
    version = "0.1.0"
    description = "Tool outside whitelist"
    timeout_seconds = 10
    parameters_schema = DummySchema

    async def execute(
        self,
        params: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(raw_output={})


def test_base_tool_initialization_and_attributes() -> None:
    """Verify BaseTool subclass initialization with parameters."""
    tool = DummyTool()
    assert tool.name == "hash_sha256"
    assert tool.version == "1.0.0"
    assert tool.description == "Dummy hashing tool for tests"
    assert tool.timeout_seconds == 30
    assert tool.parameters_schema == DummySchema


def test_tool_registry_nominal_registration() -> None:
    """Verify registering a valid whitelisted tool and retrieving it."""
    registry = ToolRegistry()
    tool = DummyTool()
    registry.register(tool)

    assert registry.has("hash_sha256")
    assert "hash_sha256" in registry
    retrieved = registry.get("hash_sha256")
    assert retrieved is tool
    assert registry.list_tool_names() == ["hash_sha256"]
    assert registry.list_tools() == [tool]


def test_tool_registry_duplicate_registration_rejection() -> None:
    """Verify attempting to register a duplicate tool name raises ValueError."""
    registry = ToolRegistry()
    tool = DummyTool()
    registry.register(tool)

    duplicate = DummyTool()
    with pytest.raises(ValueError, match="déjà enregistré"):
        registry.register(duplicate)


def test_tool_registry_whitelist_enforcement() -> None:
    """Verify attempting to register a non-whitelisted tool raises PluginNotWhitelistedException."""
    registry = ToolRegistry()
    tool = NonWhitelistedTool()

    with pytest.raises(PluginNotWhitelistedException):
        registry.register(tool)


def test_tool_registry_whitelist_dynamic_addition() -> None:
    """Verify dynamically adding a tool name to whitelist permits its registration."""
    registry = ToolRegistry()
    registry.add_to_whitelist("arbitrary_custom_tool")
    assert registry.is_whitelisted("arbitrary_custom_tool")

    tool = NonWhitelistedTool()
    registry.register(tool)
    assert registry.get("arbitrary_custom_tool") is tool


def test_tool_registry_disabled_whitelist_mode() -> None:
    """Verify ToolRegistry with enforce_whitelist=False allows arbitrary tools."""
    registry = ToolRegistry(enforce_whitelist=False)
    tool = NonWhitelistedTool()
    registry.register(tool)
    assert registry.has("arbitrary_custom_tool")


def test_tool_registry_get_unregistered_tool_raises_404() -> None:
    """Verify get on nonexistent tool raises ToolNotFoundException."""
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundException):
        registry.get("unknown_tool_name")


def test_tool_registry_unregister() -> None:
    """Verify unregistering a tool and attempting to unregister unknown tool."""
    registry = ToolRegistry()
    tool = DummyTool()
    registry.register(tool)
    assert registry.has("hash_sha256")

    registry.unregister("hash_sha256")
    assert not registry.has("hash_sha256")

    with pytest.raises(ToolNotFoundException):
        registry.unregister("hash_sha256")


def test_tool_registry_invalid_tool_types() -> None:
    """Verify registering a non-BaseTool object raises TypeError."""
    registry = ToolRegistry()

    with pytest.raises(TypeError):
        registry.register("not_a_tool")  # type: ignore


def test_tool_registry_empty_name() -> None:
    """Verify registering a tool with empty name raises ValueError."""
    registry = ToolRegistry()

    class EmptyNameTool(BaseTool):
        name = ""
        parameters_schema = DummySchema

        async def execute(self, params: BaseModel, context: ToolExecutionContext):
            return ToolExecutionResult()

    with pytest.raises(ValueError, match="cannot be empty"):
        registry.register(EmptyNameTool())


def test_tool_registry_clear() -> None:
    """Verify clear method removes all registered tools."""
    registry = ToolRegistry()
    tool = DummyTool()
    registry.register(tool)
    assert len(registry.list_tools()) == 1

    registry.clear()
    assert len(registry.list_tools()) == 0


def test_mvp_tool_whitelist_contents() -> None:
    """Verify default MVP whitelist matches architecture requirements."""
    expected = {
        "hash_sha256",
        "parse_text_logs",
        "parse_evtx",
        "parse_registry",
        "parse_execution",
        "analyze_memory",
    }
    assert expected == MVP_TOOL_WHITELIST
