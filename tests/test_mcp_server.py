"""The built-in MCP server: Majordomo serving its own tools, dogfooded
through Majordomo's own MCP client over a real subprocess."""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

from majordomo.mcp_client import MCPClient
from majordomo.mcp_server import handle_message, serve_stdio
from majordomo.runtime import Runtime


def _round_trip(runtime: Runtime, lines: list[dict], allow_write: bool = False) -> list[dict]:
    raw = "\n".join(json.dumps(line) for line in lines) + "\n"
    out = io.StringIO()
    serve_stdio(runtime.registry, allow_write=allow_write, stdin=io.StringIO(raw), stdout=out)
    return [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]


def test_initialize_and_tool_listing_are_read_only_by_default(runtime: Runtime) -> None:
    replies = _round_trip(
        runtime,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ],
    )
    assert len(replies) == 2  # the notification gets no reply
    init, listing = replies
    assert init["result"]["serverInfo"]["name"] == "majordomo"
    tools = listing["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert "workspace_list" in names
    assert "memory_recall" in names
    assert "memory_remember" not in names  # acting tool, gated out
    assert "workspace_write" not in names
    assert all(tool["annotations"]["readOnlyHint"] for tool in tools)


def test_acting_tool_call_is_refused_without_allow_write(runtime: Runtime) -> None:
    replies = _round_trip(
        runtime,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "memory_remember",
                    "arguments": {"kind": "fact", "text": "sneaky write"},
                },
            }
        ],
    )
    result = replies[0]["result"]
    assert result["isError"] is True
    assert "--allow-write" in result["content"][0]["text"]


def test_read_tool_call_answers(runtime: Runtime) -> None:
    replies = _round_trip(
        runtime,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "workspace_list", "arguments": {}},
            }
        ],
    )
    result = replies[0]["result"]
    assert result["isError"] is False
    assert result["content"][0]["type"] == "text"


def test_allow_write_lists_acting_tools(runtime: Runtime) -> None:
    reply = handle_message(
        runtime.registry, True, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert reply is not None
    names = {tool["name"] for tool in reply["result"]["tools"]}
    assert "memory_remember" in names


def test_subprocess_dogfood_with_own_client(tmp_path: Path) -> None:
    env = {
        "MAJORDOMO_PROVIDER": "fake",
        "MAJORDOMO_DATA_DIR": str(tmp_path / "data"),
    }
    client = MCPClient(
        name="self",
        command=sys.executable,
        args=["-m", "majordomo.mcp_server"],
        env={**os.environ, **env},
    )
    client.start()
    try:
        tools = client.list_tools()
        assert tools, "the built-in server exposed no tools"
        assert all(t["annotations"]["readOnlyHint"] for t in tools)
        text = client.call_tool("workspace_list", {})
        assert isinstance(text, str)
    finally:
        client.close()
