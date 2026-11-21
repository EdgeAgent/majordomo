"""The agent loop.

One turn: take the user's message, give the provider the conversation
plus every tool schema, and keep going while the provider asks for
tools. Each tool call passes the registry's approval philosophy —
read-only tools run free; acting tools need the run's approver. Tool
results (including declines and errors, stated plainly) go back into
the conversation, so the model always knows what actually happened.
The session is persisted after every turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from .providers import Provider
from .sessions import SessionStore
from .tools import Approver, ToolError, ToolRegistry

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are Majordomo, a self-hosted personal AI agent running on the user's own machine.

Rules of the house:
- Use tools when they help; say what you did, plainly, including failures.
- Long-term memory is explicit: only save something when the user asks you to remember it, and use memory_recall before claiming you don't know a preference.
- Anything that writes, creates, schedules, or generates needs the user's approval in this run; if a tool call is declined, accept it and offer the read-only alternative.
- Never invent web results, file contents, or memories. If a tool errors, report the error.
"""


@dataclass
class AgentEvent:
    """One thing that happened during a turn, for transcripts and UIs."""

    kind: str  # "tool_call" | "tool_result" | "declined" | "error" | "reply"
    text: str
    tool: str | None = None


@dataclass
class AgentResult:
    """The outcome of one turn."""

    session_id: str
    text: str
    events: list[AgentEvent] = field(default_factory=list)


class Agent:
    """A provider, a registry, and a session store, looped."""

    def __init__(
        self, provider: Provider, registry: ToolRegistry, sessions: SessionStore, max_steps: int = 8
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.sessions = sessions
        self.max_steps = max_steps

    def run(self, session_id: str | None, user_text: str, approver: Approver) -> AgentResult:
        """Run one user message to a final reply, persisting the session."""
        session = self.sessions.get_or_create(session_id)
        sid = str(session["id"])
        history: list[dict[str, Any]] = list(session.get("messages", []))
        history.append({"role": "user", "content": user_text})
        events: list[AgentEvent] = []
        final_text = ""

        for _step in range(self.max_steps):
            messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
            try:
                response = self.provider.chat(messages, self.registry.schemas())
            except Exception as exc:  # noqa: BLE001 - provider failures are reported, not hidden
                final_text = f"The model provider failed: {exc}"
                events.append(AgentEvent(kind="error", text=final_text))
                break

            if not response.tool_calls:
                final_text = response.text
                history.append({"role": "assistant", "content": final_text})
                events.append(AgentEvent(kind="reply", text=final_text))
                break

            history.append(
                {
                    "role": "assistant",
                    "content": response.text,
                    "tool_calls": [
                        {"id": call.id, "name": call.name, "arguments": call.arguments}
                        for call in response.tool_calls
                    ],
                }
            )
            for call in response.tool_calls:
                events.append(
                    AgentEvent(
                        kind="tool_call", text=f"{call.name}({call.arguments})", tool=call.name
                    )
                )
                result_text = self._execute(call.name, call.arguments, approver, events)
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": result_text,
                    }
                )
                events.append(AgentEvent(kind="tool_result", text=result_text, tool=call.name))
        else:
            final_text = (
                f"I stopped after {self.max_steps} tool steps without a final answer. "
                "The tool results above are in the conversation — ask me to continue."
            )
            history.append({"role": "assistant", "content": final_text})
            events.append(AgentEvent(kind="error", text=final_text))

        session["messages"] = history
        if not session.get("title"):
            session["title"] = user_text[:60]
        self.sessions.save(session)
        log.info("agent.turn", session=sid, events=len(events))
        return AgentResult(session_id=sid, text=final_text, events=events)

    def _execute(
        self, name: str, arguments: dict[str, Any], approver: Approver, events: list[AgentEvent]
    ) -> str:
        tool = self.registry.get(name)
        if tool is None:
            return f"Error: unknown tool {name!r}."
        if not tool.read_only and not approver(name, arguments):
            note = f"Declined: {name} needs approval and this run did not grant it."
            events.append(AgentEvent(kind="declined", text=note, tool=name))
            return note + " Nothing was done."
        try:
            return self.registry.call(name, arguments)
        except ToolError as exc:
            return f"Error: {exc}"
