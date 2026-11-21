"""The tool registry and the approval philosophy.

Every capability the agent has is a :class:`Tool` in one registry. A
tool declares whether it is **read-only** (looking is free — it runs
without asking) or **acting** (writing a file, creating a document,
setting a reminder, generating an image). Acting tools run only when
the run's approver says yes:

- the interactive CLI asks the user, per call;
- the web API takes an ``approve`` flag on the request;
- the demo auto-approves because every backend behind it is a fake.

The registry renders OpenAI-shaped function schemas for the providers
and dispatches calls by name. Handlers return strings — the text the
model (and the transcript) sees.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ToolHandler = Callable[..., str]
Approver = Callable[[str, dict[str, Any]], bool]


class ToolError(RuntimeError):
    """A tool call failed; the message is shown to the model as-is."""


@dataclass
class Tool:
    """One capability: a name, a JSON-schema, a handler, a risk class."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    read_only: bool = False

    def schema(self) -> dict[str, Any]:
        """The OpenAI-shaped function schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _params(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


class ToolRegistry:
    """All tools, by name, with schema rendering and dispatch."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [self._tools[name].schema() for name in self.names()]

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Run a tool. Unknown names and bad arguments are honest errors."""
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"Unknown tool {name!r}. Available: {', '.join(self.names())}.")
        try:
            return tool.handler(**arguments)
        except ToolError:
            raise
        except TypeError as exc:
            raise ToolError(f"Bad arguments for {name}: {exc}") from exc
        except Exception as exc:  # tool failures surface as text, never crashes
            raise ToolError(f"{name} failed: {exc}") from exc


def approve_all(_name: str, _arguments: dict[str, Any]) -> bool:
    """Approver that says yes to everything (demo and explicit flags)."""
    return True


def approve_none(_name: str, _arguments: dict[str, Any]) -> bool:
    """Approver that declines every acting tool (read-only still runs)."""
    return False
