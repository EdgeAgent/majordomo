"""The always-on daemon: one tick via --once, the same fire-due engine
the web app ticks, with fired reminders landing in the inbox session."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from majordomo.cli import app
from majordomo.sessions import SessionStore

runner = CliRunner()


def _env(tmp_path: Path) -> dict[str, str]:
    return {"MAJORDOMO_DATA_DIR": str(tmp_path / "data"), "MAJORDOMO_PROVIDER": "fake"}


def test_daemon_once_with_nothing_due(tmp_path: Path) -> None:
    result = runner.invoke(app, ["daemon", "--once"], env=_env(tmp_path))
    assert result.exit_code == 0
    assert "Nothing due." in result.stdout


def test_daemon_once_fires_a_due_reminder_into_the_inbox(tmp_path: Path) -> None:
    env = _env(tmp_path)
    added = runner.invoke(
        app, ["schedule", "add", "Water the plants", "--in-minutes", "0"], env=env
    )
    assert added.exit_code == 0

    fired = runner.invoke(app, ["daemon", "--once"], env=env)
    assert fired.exit_code == 0
    assert "Water the plants" in fired.stdout

    # The fired reminder was dropped into the inbox session, on disk.
    sessions = SessionStore(tmp_path / "data" / "sessions")
    inbox = sessions.get("inbox")
    assert inbox is not None
    contents = [str(message.get("content", "")) for message in inbox["messages"]]
    assert any("Water the plants" in content for content in contents)

    # A one-time reminder fires exactly once.
    second = runner.invoke(app, ["daemon", "--once"], env=env)
    assert second.exit_code == 0
    assert "Nothing due." in second.stdout
