"""Goals: the owner's standing aims, kept in one JSON file.

A goal is a line of text plus its *next move* — the single concrete
step that would advance it. Goals live in ``goals.json`` at the top
of the data directory, next to the self files: plain data the owner
owns, persisted across restarts, with integer ids assigned in order.
The web window's Goal read is the interface; this store is the whole
backend — no database, no hidden state.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


class GoalStore:
    """Create, list, update, and delete goals in one JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []

    def _save(self, goals: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(goals, indent=2), encoding="utf-8")

    def list(self) -> list[dict[str, Any]]:
        """Every goal, in the order it was added."""
        return self._load()

    def add(self, text: str, next_move: str = "") -> dict[str, Any]:
        """Add a goal and return it, with its freshly assigned id."""
        goals = self._load()
        goal: dict[str, Any] = {
            "id": max((g["id"] for g in goals), default=0) + 1,
            "text": text,
            "next_move": next_move,
            "done": False,
            "created_at": _now(),
        }
        goals.append(goal)
        self._save(goals)
        return goal

    def _find(self, goals: list[dict[str, Any]], goal_id: int) -> dict[str, Any] | None:
        return next((g for g in goals if g["id"] == goal_id), None)

    def set_next_move(self, goal_id: int, next_move: str) -> dict[str, Any] | None:
        """Replace a goal's next move; None when the goal is unknown."""
        goals = self._load()
        goal = self._find(goals, goal_id)
        if goal is None:
            return None
        goal["next_move"] = next_move
        self._save(goals)
        return goal

    def set_done(self, goal_id: int, done: bool) -> dict[str, Any] | None:
        """Mark a goal done (or reopen it); None when unknown."""
        goals = self._load()
        goal = self._find(goals, goal_id)
        if goal is None:
            return None
        goal["done"] = done
        self._save(goals)
        return goal

    def delete(self, goal_id: int) -> bool:
        """Remove a goal; True when one was actually removed."""
        goals = self._load()
        kept = [g for g in goals if g["id"] != goal_id]
        if len(kept) == len(goals):
            return False
        self._save(kept)
        return True
