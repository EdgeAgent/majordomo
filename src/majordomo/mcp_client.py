"""An MCP client: Majordomo as a consumer of MCP servers.

Majordomo speaks the Model Context Protocol over stdio. It launches
a server process, performs the
``initialize`` handshake, lists its tools, and re-registers them in the
agent's own registry, namespaced as ``<server>__<tool>``. A remote
tool's ``readOnlyHint`` annotation decides whether Majordomo treats it
as read-only; everything else goes through the approval gate like any
acting tool.

Servers are configured in one JSON file::

    {
      "servers": {
        "majordomo": {"command": "majordomo", "args": ["mcp-server"]}
      }
    }
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from queue import Queue
from typing import Any, Self

from . import __version__
from .tools import Tool, ToolRegistry

PROTOCOL_VERSION = "2025-06-18"
_TIMEOUT_SECONDS = 30.0


class MCPError(RuntimeError):
    """An MCP server call failed; the message says why."""


class MCPClient:
    """A synchronous stdio MCP client for one server process."""

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.command = command
        self.args = list(args or [])
        self.env = env
        self._process: subprocess.Popen[str] | None = None
        self._lines: Queue[str | None] = Queue()
        self._next_id = 0

    # -- lifecycle ------------------------------------------------------

    def start(self) -> None:
        """Launch the server and run the initialize handshake."""
        if self._process is not None:
            return
        merged_env = dict(os.environ)
        if self.env:
            merged_env.update(self.env)
        try:
            self._process = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                env=merged_env,
            )
        except OSError as exc:
            raise MCPError(f"Could not start MCP server {self.name!r}: {exc}") from exc
        reader = threading.Thread(target=self._pump, daemon=True)
        reader.start()
        self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "majordomo", "version": __version__},
            },
        )
        self._notify("notifications/initialized", {})

    def close(self) -> None:
        """Terminate the server process."""
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- wire -----------------------------------------------------------

    def _pump(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _send(self, payload: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise MCPError(f"MCP server {self.name!r} is not running.")
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict[str, Any]) -> Any:
        if self._process is None:
            self.start()
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            try:
                line = self._lines.get(timeout=_TIMEOUT_SECONDS)
            except Exception as exc:
                raise MCPError(
                    f"Timed out waiting for {method} from MCP server {self.name!r}."
                ) from exc
            if line is None:
                raise MCPError(f"MCP server {self.name!r} closed the connection.")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # a stray non-JSON line is not a response
            if message.get("id") != request_id:
                continue  # a notification or someone else's response
            if "error" in message:
                error = message["error"]
                raise MCPError(
                    f"MCP server {self.name!r} error {error.get('code')}: {error.get('message')}"
                )
            return message.get("result")

    # -- protocol -------------------------------------------------------

    def list_tools(self) -> list[dict[str, Any]]:
        """The server's tool descriptors (name, description, schema, hints)."""
        result = self._request("tools/list", {})
        tools: list[dict[str, Any]] = (result or {}).get("tools", [])
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call one tool and flatten its content blocks to text."""
        result = self._request("tools/call", {"name": name, "arguments": arguments}) or {}
        parts = [
            str(block.get("text", ""))
            for block in result.get("content", [])
            if block.get("type") == "text"
        ]
        text = "\n".join(part for part in parts if part) or "(no content)"
        if result.get("isError"):
            raise MCPError(f"MCP tool {name} failed: {text}")
        return text


def load_mcp_config(path: Path) -> dict[str, dict[str, Any]]:
    """Load the servers mapping from a JSON config file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MCPError(f"Cannot read MCP config {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MCPError(f"MCP config {path} is not valid JSON: {exc}") from exc
    servers = data.get("servers")
    if not isinstance(servers, dict):
        raise MCPError(f'MCP config {path} needs a top-level "servers" object.')
    return servers


def register_mcp_tools(registry: ToolRegistry, client: MCPClient) -> list[str]:
    """Expose one connected server's tools in the agent registry.

    Returns the registered names (``<server>__<tool>``). The remote
    ``readOnlyHint`` annotation maps to Majordomo's read-only class;
    unannotated tools are treated as acting, so they need approval.
    """
    registered: list[str] = []
    for descriptor in client.list_tools():
        remote_name = str(descriptor.get("name", ""))
        if not remote_name:
            continue
        local_name = f"{client.name}__{remote_name}"
        annotations = descriptor.get("annotations") or {}
        read_only = bool(annotations.get("readOnlyHint", False))

        def make_handler(tool_name: str) -> Any:
            def handler(**arguments: Any) -> str:
                return client.call_tool(tool_name, arguments)

            return handler

        registry.register(
            Tool(
                name=local_name,
                description=str(descriptor.get("description", f"MCP tool from {client.name}.")),
                parameters=descriptor.get("inputSchema") or {"type": "object", "properties": {}},
                handler=make_handler(remote_name),
                read_only=read_only,
            )
        )
        registered.append(local_name)
    return registered
