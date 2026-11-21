"""Scheduler: firing semantics under a fake clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from majordomo.scheduler import ScheduleStore, register_schedule_tools
from majordomo.tools import ToolRegistry

T0 = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


@pytest.fixture()
def store(tmp_path: Path) -> ScheduleStore:
    return ScheduleStore(tmp_path / "schedules.json")


def test_add_and_list(store: ScheduleStore) -> None:
    reminder = store.add("Call the bank", T0 + timedelta(hours=1))
    assert reminder.id
    listed = store.list()
    assert [r.text for r in listed] == ["Call the bank"]


def test_fire_due_one_time_fires_once(store: ScheduleStore) -> None:
    store.add("Stretch", T0 - timedelta(minutes=5))
    fired = store.fire_due(T0)
    assert [r.text for r in fired] == ["Stretch"]
    assert store.fire_due(T0) == []  # marked done — never refires
    assert store.list() == []


def test_not_yet_due_does_not_fire(store: ScheduleStore) -> None:
    store.add("Later", T0 + timedelta(hours=2))
    assert store.fire_due(T0) == []
    assert len(store.list()) == 1


def test_recurring_daily_advances(store: ScheduleStore) -> None:
    store.add("Standup notes", T0 - timedelta(days=2, minutes=1), repeat="daily")
    fired = store.fire_due(T0)
    assert len(fired) == 1
    upcoming = store.list()
    assert len(upcoming) == 1
    assert upcoming[0].due_datetime() > T0
    assert upcoming[0].due_datetime() <= T0 + timedelta(days=1)


def test_recurring_weekly_advances(store: ScheduleStore) -> None:
    store.add("Weekly review", T0 - timedelta(minutes=1), repeat="weekly")
    store.fire_due(T0)
    upcoming = store.list()
    assert upcoming[0].due_datetime() == T0 - timedelta(minutes=1) + timedelta(days=7)


def test_cancel(store: ScheduleStore) -> None:
    reminder = store.add("Cancel me", T0)
    assert store.cancel(reminder.id) is True
    assert store.cancel(reminder.id) is False
    assert store.list() == []


def test_invalid_repeat_rejected(store: ScheduleStore) -> None:
    with pytest.raises(ValueError, match="repeat must be"):
        store.add("Nope", T0, repeat="hourly")


def test_store_survives_reload(tmp_path: Path) -> None:
    path = tmp_path / "schedules.json"
    ScheduleStore(path).add("Persisted", T0)
    assert [r.text for r in ScheduleStore(path).list()] == ["Persisted"]


def test_tools_use_the_injected_clock(store: ScheduleStore) -> None:
    clock = {"now": T0}
    registry = ToolRegistry()
    register_schedule_tools(registry, store, lambda: clock["now"])
    out = registry.call("schedule_reminder", {"text": "Water plants", "due_in_minutes": 30})
    assert "Water plants" in out
    listed = registry.call("list_reminders", {})
    assert "Water plants" in listed
    # Nothing fires at T0; everything fires at T0+31m.
    assert store.fire_due(T0) == []
    assert len(store.fire_due(T0 + timedelta(minutes=31))) == 1
    cancelled = registry.call("cancel_reminder", {"reminder_id": "missing"})
    assert "No reminder" in cancelled
