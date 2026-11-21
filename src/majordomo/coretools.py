"""Memory and recall tools: how the agent uses its own memory.

``memory_remember`` is the ONLY automatic path into long-term memory,
and it is an acting tool — it needs approval, like every other write.
That is deliberate: the agent should never quietly build a profile of
its user. Recall and past-chat search are reads, so they run free.
"""

from __future__ import annotations

from .memory import KINDS, MemoryStore
from .sessions import SessionStore
from .tools import Tool, ToolRegistry


def register_memory_tools(
    registry: ToolRegistry, memory: MemoryStore, sessions: SessionStore
) -> None:
    """Add memory_remember / memory_recall / search_past_chats."""

    def remember(kind: str, text: str) -> str:
        entry = memory.remember(kind, text)
        return f"Remembered as {entry.id} ({entry.kind}): {entry.text}"

    def recall(query: str) -> str:
        entries = memory.recall(query)
        if not entries:
            return "Nothing in memory matches that."
        return "\n".join(f"{e.id} [{e.kind}] {e.text}" for e in entries)

    def search_chats(query: str) -> str:
        hits = sessions.search(query)
        if not hits:
            return "No past conversation mentions that."
        return "\n".join(f"[{h['session_id']}] {h['role']}: {h['snippet']}" for h in hits)

    registry.register(
        Tool(
            name="memory_remember",
            description=(
                "Save one fact, preference, or note to long-term memory. "
                "Use only when the user asks to remember something, or confirms it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "text": {"type": "string"},
                },
                "required": ["kind", "text"],
            },
            handler=remember,
        )
    )
    registry.register(
        Tool(
            name="memory_recall",
            description="Search long-term memory for facts, preferences, and notes.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=recall,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="search_past_chats",
            description="Search past conversations for earlier context (cross-session recall).",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=search_chats,
            read_only=True,
        )
    )
