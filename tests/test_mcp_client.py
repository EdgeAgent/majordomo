"""The MCP client, against the in-repo fake MCP server fixture."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from majordomo.mcp_client import MCPClient, MCPError, load_mcp_config, register_mcp_tools
from majordomo.tools import ToolRegistry

FIXTURE = Path(__file__).parent / "fixtures" / "fake_mcp_server.py"


@pytest.fixture()
def client() -> MCPClient:  # type: ignore[misc]
    mcp = MCPClient(name="fake", command=sys.executable, args=[str(FIXTURE)])
    mcp.start()
    yield mcp  # type: ignore[misc]
    mcp.close()


def test_handshake_and_tool_list(client: MCPClient) -> None:
    tools = client.list_tools()
    assert [t["name"] for t in tools] == ["echo", "add"]


def test_call_echo(client: MCPClient) -> None:
    assert client.call_tool("echo", {"text": "hello mcp"}) == "hello mcp"


def test_call_add(client: MCPClient) -> None:
    assert client.call_tool("add", {"a": 19, "b": 23}) == "42"


def test_unknown_tool_raises(client: MCPClient) -> None:
    with pytest.raises(MCPError, match="failed"):
        client.call_tool("nope", {})


def test_register_maps_names_and_read_only_hints(client: MCPClient) -> None:
    registry = ToolRegistry()
    names = register_mcp_tools(registry, client)
    assert names == ["fake__echo", "fake__add"]
    echo = registry.get("fake__echo")
    add = registry.get("fake__add")
    assert echo is not None and echo.read_only is True  # readOnlyHint honoured
    assert add is not None and add.read_only is False  # unannotated = acting
    assert registry.call("fake__echo", {"text": "via registry"}) == "via registry"


def test_bad_command_is_an_honest_error() -> None:
    mcp = MCPClient(name="ghost", command="definitely-not-a-real-command-xyz")
    with pytest.raises(MCPError, match="Could not start"):
        mcp.start()


def test_load_config_from_examples() -> None:
    config = Path(__file__).parent.parent / "examples" / "mcp-servers.json"
    servers = load_mcp_config(config)
    assert set(servers) == {"lead-tools", "business-tools", "mini-crm"}
    assert servers["lead-tools"]["command"] == "ai-mcp"


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(MCPError, match="Cannot read"):
        load_mcp_config(tmp_path / "nope.json")


def test_load_config_bad_shape(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"nope": {}}', encoding="utf-8")
    with pytest.raises(MCPError, match="servers"):
        load_mcp_config(bad)
