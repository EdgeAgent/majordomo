"""Reminders: one-time and recurring, in one JSON store.

A reminder is ``{id, text, due_at, repeat, done}``. ``run_due`` is the
firing engine: hand it the current time (tests hand it a fake clock)
and it returns everything that should fire, marking one-time reminders
done and advancing recurring ones by their interval. The CLI exposes it
as ``majordomo schedule run-due``; the web app ticks it in the
background and drops fired reminders into the inbox session.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .tools import Tool, ToolRegistry

_INTERVALS = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}
REPEATS = ("none", "daily", "weekly")


@dataclass
class Reminder:
    """One scheduled reminder."""

    id: str
    text: str
    due_at: str  # ISO 8601, UTC
    repeat: str = "none"
    done: bool = False

    def due_datetime(self) -> datetime:
        return datetime.fromisoformat(self.due_at)


class ScheduleStore:
    """Persist and fire reminders from a single JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save([])

    def _load(self) -> list[Reminder]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return [Reminder(**item) for item in raw]

    def _save(self, reminders: list[Reminder]) -> None:
        self.path.write_text(json.dumps([asdict(r) for r in reminders], indent=2), encoding="utf-8")

    def add(self, text: str, due_at: datetime, repeat: str = "none") -> Reminder:
        if repeat not in REPEATS:
            raise ValueError(f"repeat must be one of {', '.join(REPEATS)}.")
        reminder = Reminder(
            id=uuid.uuid4().hex[:8],
            text=text,
            due_at=due_at.isoformat(),
            repeat=repeat,
        )
        reminders = self._load()
        reminders.append(reminder)
        self._save(reminders)
        return reminder

    def list(self, include_done: bool = False) -> list[Reminder]:
        reminders = self._load()
        if not include_done:
            reminders = [r for r in reminders if not r.done]
        return sorted(reminders, key=lambda r: r.due_at)

    def cancel(self, reminder_id: str) -> bool:
        reminders = self._load()
        kept = [r for r in reminders if r.id != reminder_id]
        if len(kept) == len(reminders):
            return False
        self._save(kept)
        return True

    def fire_due(self, now: datetime) -> list[Reminder]:
        """Return everything due at ``now`` and advance the store.

        One-time reminders are marked done; recurring ones move their
        due time forward by whole intervals until they are in the future.
        """
        fired: list[Reminder] = []
        reminders = self._load()
        for reminder in reminders:
            if reminder.done or reminder.due_datetime() > now:
                continue
            fired.append(reminder)
            if reminder.repeat in _INTERVALS:
                interval = _INTERVALS[reminder.repeat]
                due = reminder.due_datetime()
                while due <= now:
                    due += interval
                reminder.due_at = due.isoformat()
            else:
                reminder.done = True
        if fired:
            self._save(reminders)
        return fired


def register_schedule_tools(
    registry: ToolRegistry, store: ScheduleStore, now_fn: Callable[[], datetime]
) -> None:
    """Add schedule_reminder / list_reminders / cancel_reminder."""

    def schedule(text: str, due_in_minutes: int = 60, repeat: str = "none") -> str:
        due = now_fn() + timedelta(minutes=int(due_in_minutes))
        reminder = store.add(text, due, repeat)
        return (
            f"Reminder {reminder.id} set for {reminder.due_at} "
            f"({repeat if repeat != 'none' else 'one-time'}): {text}"
        )

    def list_reminders() -> str:
        reminders = store.list()
        if not reminders:
            return "No active reminders."
        return "\n".join(f"{r.id} — due {r.due_at} ({r.repeat}): {r.text}" for r in reminders)

    def cancel(reminder_id: str) -> str:
        return (
            f"Cancelled reminder {reminder_id}."
            if store.cancel(reminder_id)
            else f"No reminder with id {reminder_id}."
        )

    registry.register(
        Tool(
            name="schedule_reminder",
            description="Set a reminder, due in N minutes, optionally repeating daily or weekly.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "due_in_minutes": {"type": "integer"},
                    "repeat": {"type": "string", "enum": list(REPEATS)},
                },
                "required": ["text"],
            },
            handler=schedule,
        )
    )
    registry.register(
        Tool(
            name="list_reminders",
            description="List active reminders.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=list_reminders,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="cancel_reminder",
            description="Cancel a reminder by id.",
            parameters={
                "type": "object",
                "properties": {"reminder_id": {"type": "string"}},
                "required": ["reminder_id"],
            },
            handler=cancel,
        )
    )
