"""The morning brief: a deterministic template over real state."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from majordomo.brief import build_brief
from majordomo.cli import app
from majordomo.mailtools import FakeMailBackend, UnconfiguredMailBackend
from majordomo.memory import MemoryStore
from majordomo.scheduler import ScheduleStore

NOW = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)

runner = CliRunner()


def _parts(tmp_path: Path) -> tuple[ScheduleStore, MemoryStore, Path]:
    schedules = ScheduleStore(tmp_path / "schedules.json")
    schedules.add("Water the plants", NOW - timedelta(hours=1))  # overdue
    schedules.add("Call the bank", NOW + timedelta(hours=3))  # later today
    memory = MemoryStore(tmp_path / "memory")
    memory.remember("fact", "The workshop is in London, Ontario")
    return schedules, memory, tmp_path / "initiative.json"


def test_brief_reports_reminders_mail_and_memory(tmp_path: Path) -> None:
    schedules, memory, state_path = _parts(tmp_path)
    text = build_brief(
        schedules=schedules,
        backend=FakeMailBackend(),
        memory=memory,
        state_path=state_path,
        now=NOW,
    )
    assert "# Majordomo brief — Saturday, November 21, 2026" in text
    assert "Water the plants — overdue" in text
    assert "Call the bank — today at 12:00" in text
    # No initiative baseline yet: every listed message counts as new.
    assert "3 recent message(s), 3 new" in text
    assert "Notes on the Analytical Engine" in text
    assert "The workshop is in London, Ontario" in text


def test_brief_counts_only_unseen_mail_as_new(tmp_path: Path) -> None:
    schedules, memory, state_path = _parts(tmp_path)
    state_path.write_text(
        json.dumps({"seen_mail_ids": ["fake-1", "fake-2"], "fired": {}}), encoding="utf-8"
    )
    text = build_brief(
        schedules=schedules,
        backend=FakeMailBackend(),
        memory=memory,
        state_path=state_path,
        now=NOW,
    )
    assert "3 recent message(s), 1 new" in text


def test_brief_reports_unconfigured_mail_honestly(tmp_path: Path) -> None:
    schedules, memory, state_path = _parts(tmp_path)
    text = build_brief(
        schedules=schedules,
        backend=UnconfiguredMailBackend(),
        memory=memory,
        state_path=state_path,
        now=NOW,
    )
    assert "Mail unavailable: Mail is not configured" in text


def test_brief_command_prints_and_saves(tmp_path: Path) -> None:
    env = {"MAJORDOMO_DATA_DIR": str(tmp_path / "data"), "MAJORDOMO_PROVIDER": "fake"}
    result = runner.invoke(app, ["brief"], env=env)
    assert result.exit_code == 0
    assert "Majordomo brief" in result.stdout
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    saved = tmp_path / "data" / "workspace" / f"brief-{today}.md"
    assert saved.exists()
    assert "Majordomo brief" in saved.read_text(encoding="utf-8")
