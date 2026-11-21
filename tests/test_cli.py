"""CLI surface and the scripted demo."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from majordomo.cli import app
from majordomo.demo import run_demo

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_demo_command() -> None:
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0
    assert "Demo done" in result.stdout


def test_demo_transcript_covers_the_day() -> None:
    transcript = run_demo()
    assert "search the web" in transcript.lower()
    assert "Reminder fired" in transcript
    assert "double espresso" in transcript  # saved, then recalled in a new session
    assert "Majordomo demo" in transcript


def test_demo_creates_the_word_brief() -> None:
    pytest.importorskip("docx")
    transcript = run_demo()
    assert "pilot-brief.docx" in transcript


def test_memory_cli_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    env = {"MAJORDOMO_DATA_DIR": str(tmp_path / "data"), "MAJORDOMO_PROVIDER": "fake"}
    added = runner.invoke(app, ["memory", "add", "fact", "The sky is blue"], env=env)
    assert added.exit_code == 0
    listed = runner.invoke(app, ["memory", "list"], env=env)
    assert listed.exit_code == 0
    assert "The sky is blue" in listed.stdout
    searched = runner.invoke(app, ["memory", "search", "sky"], env=env)
    assert "The sky is blue" in searched.stdout
    forgotten = runner.invoke(app, ["memory", "forget", "fact:1"], env=env)
    assert forgotten.exit_code == 0
    assert "The sky is blue" not in runner.invoke(app, ["memory", "list"], env=env).stdout


def test_schedule_cli_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    env = {"MAJORDOMO_DATA_DIR": str(tmp_path / "data"), "MAJORDOMO_PROVIDER": "fake"}
    added = runner.invoke(
        app, ["schedule", "add", "Water the plants", "--in-minutes", "0"], env=env
    )
    assert added.exit_code == 0
    listed = runner.invoke(app, ["schedule", "list"], env=env)
    assert "Water the plants" in listed.stdout
    due = runner.invoke(app, ["schedule", "run-due"], env=env)
    assert due.exit_code == 0
    assert "Water the plants" in due.stdout


def test_ask_command_with_fake_provider(tmp_path) -> None:  # type: ignore[no-untyped-def]
    env = {"MAJORDOMO_DATA_DIR": str(tmp_path / "data"), "MAJORDOMO_PROVIDER": "fake"}
    result = runner.invoke(app, ["ask", "hello"], env=env)
    assert result.exit_code == 0
    assert "fake provider" in result.stdout
