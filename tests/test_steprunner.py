"""The step runner: plan steps, one teammate run each, journal, stop on failure."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from majordomo.steprunner import parse_steps, run_steps


def _which(name: str) -> str:
    return f"/usr/bin/{name}"


def _ok_run(calls: list[list[str]]):
    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="step done", stderr="")

    return run


def test_parse_steps_strips_numbering_and_bullets() -> None:
    raw = "1. Write the code\n2) Test it\n- Ship it\nStep 3: Rest\n\n"
    assert parse_steps(raw) == ["Write the code", "Test it", "Ship it", "Rest"]


def test_run_steps_all_pass_and_journal_written(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    run = run_steps(
        "claude",
        ["first", "second"],
        cwd=tmp_path / "ws",
        timeout=30,
        teammates_dir=tmp_path / "teammates",
        journal_dir=tmp_path / "runs",
        which=_which,
        run_fn=_ok_run(calls),
    )
    assert run.status == "done"
    assert len(run.results) == 2
    assert len(calls) == 2
    journal = json.loads(run.journal_path.read_text(encoding="utf-8"))
    assert journal["status"] == "done"
    assert [s["step"] for s in journal["steps"]] == ["first", "second"]


def test_run_steps_stops_on_first_failure(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def flaky(argv, **kwargs):
        calls.append(argv)
        code = 0 if len(calls) == 1 else 3
        return subprocess.CompletedProcess(argv, code, stdout="x", stderr="")

    run = run_steps(
        "codex",
        ["ok step", "bad step", "never runs"],
        cwd=tmp_path / "ws",
        timeout=30,
        teammates_dir=tmp_path / "teammates",
        journal_dir=tmp_path / "runs",
        which=_which,
        run_fn=flaky,
    )
    assert run.status == "failed"
    assert len(run.results) == 2
    assert len(calls) == 2
    journal = json.loads(run.journal_path.read_text(encoding="utf-8"))
    assert journal["steps"][1]["exit_code"] == 3


def test_run_steps_unknown_agent_is_clean_error(tmp_path: Path) -> None:
    from majordomo.tools import ToolError

    with pytest.raises(ToolError):
        run_steps(
            "nobody",
            ["x"],
            cwd=tmp_path / "ws",
            timeout=30,
            teammates_dir=tmp_path / "teammates",
            journal_dir=tmp_path / "runs",
            which=_which,
            run_fn=_ok_run([]),
        )
