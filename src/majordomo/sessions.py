"""Conversation sessions, persisted as one JSON file per session.

A session is the full message list of one conversation. Sessions live
under ``sessions/`` in the data directory, so past conversations are
files the user owns — and :meth:`SessionStore.search` gives the agent
cross-session recall: "what did we talk about last week" is a search
over these files, not a mystery.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

Message = dict[str, Any]


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SessionStore:
    """Create, load, append to, and search conversation sessions."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "", session_id)
        return self.root / f"{safe}.json"

    def create(self, title: str = "") -> dict[str, Any]:
        """Start a new empty session and persist it."""
        session: dict[str, Any] = {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "created_at": _now(),
            "messages": [],
        }
        self.save(session)
        return session

    def get(self, session_id: str) -> dict[str, Any] | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def get_or_create(self, session_id: str | None) -> dict[str, Any]:
        """Load a session, or create one (with the given id if provided)."""
        if session_id:
            existing = self.get(session_id)
            if existing is not None:
                return existing
            session = {
                "id": session_id,
                "title": "",
                "created_at": _now(),
                "messages": [],
            }
            self.save(session)
            return session
        return self.create()

    def save(self, session: dict[str, Any]) -> None:
        self._path(str(session["id"])).write_text(
            json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def append(self, session_id: str, message: Message) -> dict[str, Any]:
        """Append one message and persist the session."""
        session = self.get_or_create(session_id)
        session["messages"].append(message)
        self.save(session)
        return session

    def list_sessions(self) -> list[dict[str, Any]]:
        """Summaries of every session, newest first."""
        summaries: list[dict[str, Any]] = []
        for path in self.root.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            summaries.append(
                {
                    "id": data.get("id", path.stem),
                    "title": data.get("title", ""),
                    "created_at": data.get("created_at", ""),
                    "message_count": len(data.get("messages", [])),
                }
            )
        summaries.sort(key=lambda item: str(item["created_at"]), reverse=True)
        return summaries

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Cross-session recall: find past messages matching the query.

        Returns snippets ranked by token overlap. The current session is
        not special-cased — callers pass a query, not a session.
        """
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        hits: list[tuple[int, dict[str, Any]]] = []
        for summary in self.list_sessions():
            session = self.get(str(summary["id"]))
            if session is None:
                continue
            for message in session.get("messages", []):
                content = str(message.get("content", ""))
                overlap = len(query_tokens & _tokens(content))
                if overlap:
                    hits.append(
                        (
                            overlap,
                            {
                                "session_id": session["id"],
                                "role": message.get("role", ""),
                                "snippet": content[:240],
                            },
                        )
                    )
        hits.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in hits[:limit]]
