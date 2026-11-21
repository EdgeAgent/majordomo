"""Majordomo as an MCP server: the built-in other side of the protocol.

Majordomo consumes MCP servers (see ``mcp_client``), and it also *is*
one. Running ``majordomo mcp-server`` — or ``python -m majordomo.mcp_server``
— serves Majordomo's own tools over stdio to any MCP client, so another
agent can use this agent's memory, workspace, and web tools.

The gate is the same one the agent lives by: by default only read-only
tools are exposed. Acting tools (memory writes, file writes, document
creation, reminders) join the list only when the operator starts the
server with ``--allow-write`` — a deliberate, visible choice, never a
default. The server's own runtime never loads an MCP config, so a
Majordomo pointed at another Majordomo cannot recurse.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, TextIO

from . import __version__
from .mcp_client import PROTOCOL_VERSION
from .tools import Tool, ToolError, ToolRegistry

SERVER_NAME = "majordomo"


def _visible_tools(registry: ToolRegistry, allow_write: bool) -> list[Tool]:
    tools = []
    for name in registry.names():
        tool = registry.get(name)
        if tool is not None and (allow_write or tool.read_only):
            tools.append(tool)
    return tools


def _tool_payload(tool: Tool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.parameters,
        "annotations": {
            "readOnlyHint": tool.read_only,
            "destructiveHint": False,
            "openWorldHint": tool.name.startswith("web_"),
        },
    }


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _call_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def handle_message(
    registry: ToolRegistry, allow_write: bool, message: dict[str, Any]
) -> dict[str, Any] | None:
    """Answer one JSON-RPC message; ``None`` means notification, no reply."""
    method = message.get("method", "")
    request_id = message.get("id")
    if request_id is None:
        return None  # notifications (initialized, cancelled, ...) need no reply
    params: dict[str, Any] = message.get("params") or {}
    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": __version__},
            },
        )
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        tools = [_tool_payload(tool) for tool in _visible_tools(registry, allow_write)]
        return _result(request_id, {"tools": tools})
    if method == "tools/call":
        name = str(params.get("name", ""))
        tool = registry.get(name)
        if tool is None:
            return _result(request_id, _call_result(f"Unknown tool {name!r}.", is_error=True))
        if not tool.read_only and not allow_write:
            return _result(
                request_id,
                _call_result(
                    f"{name} is an acting tool. This Majordomo MCP server is "
                    "read-only; its operator can enable acting tools with "
                    "--allow-write.",
                    is_error=True,
                ),
            )
        try:
            text = registry.call(name, dict(params.get("arguments") or {}))
        except ToolError as exc:
            return _result(request_id, _call_result(str(exc), is_error=True))
        return _result(request_id, _call_result(text))
    if method in ("resources/list", "prompts/list"):
        key = "resources" if method.startswith("resources") else "prompts"
        return _result(request_id, {key: []})
    return _error(request_id, -32601, f"Method not found: {method}")


def serve_stdio(
    registry: ToolRegistry,
    allow_write: bool = False,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    """Serve newline-delimited JSON-RPC until stdin closes."""
    source = stdin if stdin is not None else sys.stdin
    sink = stdout if stdout is not None else sys.stdout
    for line in source:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue  # a malformed line has no id to answer to; skip it
        if not isinstance(message, dict):
            continue
        reply = handle_message(registry, allow_write, message)
        if reply is not None:
            sink.write(json.dumps(reply) + "\n")
            sink.flush()


def main() -> None:
    """Entry point for ``python -m majordomo.mcp_server``."""
    from .config import Settings
    from .runtime import build_runtime

    # A server never consumes servers: drop any inherited MCP config so
    # Majordomo-pointed-at-Majordomo cannot recurse.
    os.environ.pop("MAJORDOMO_MCP_CONFIG", None)
    allow_write = "--allow-write" in sys.argv
    runtime = build_runtime(Settings())
    try:
        serve_stdio(runtime.registry, allow_write=allow_write)
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
