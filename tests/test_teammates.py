"""Teammates: detection, the CLI-agent bridge, characters, the gate.

Every run here uses a FAKE agent — a tiny script the test itself
plants in a tmp bin dir on PATH, named like the real CLI. No real
coding agent is ever launched by the suite.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

import majordomo.runtime as runtime_module
from majordomo.agent import Agent
from majordomo.cli import app
from majordomo.config import Settings
from majordomo.providers import FakeProvider, ProviderResponse, ToolCall
from majordomo.runtime import build_runtime
from majordomo.sessions import SessionStore
from majordomo.teammates import (
    AGENT_CLIS,
    AgentStatus,
    detect_agents,
    register_teammate_tools,
    run_count,
    run_teammate,
)
from majordomo.tools import ToolError, ToolRegistry, approve_all, approve_none

runner = CliRunner()


def _plant_fake_agent(bin_dir: Path, name: str, body: str) -> Path:
    """Write an executable fake CLI into a bin dir the test controls."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / name
    script.write_text(f"#!/usr/bin/env python3\n{body}", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _on_path(monkeypatch: pytest.MonkeyPatch, bin_dir: Path) -> None:
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")


_ECHO_BODY = "import sys\nprint('fake agent ran:', ' '.join(sys.argv[1:]))\n"


# -- the cast ------------------------------------------------------------


def test_the_cast_is_the_brief() -> None:
    assert AGENT_CLIS["claude"].display_name == "Claude"
    assert AGENT_CLIS["claude"].role == "the senior engineer"
    assert AGENT_CLIS["codex"].role == "the fast prototyper"
    assert AGENT_CLIS["gemini"].role == "the researcher"
    assert AGENT_CLIS["opencode"].display_name == "Otto"
    assert AGENT_CLIS["cursor"].binary == "cursor-agent"
    assert AGENT_CLIS["copilot"].role == "the pair programmer"
    assert AGENT_CLIS["aider"].role == "the focused patcher"
    assert AGENT_CLIS["aider"].experimental is True
    for spec in AGENT_CLIS.values():
        assert spec.initial and spec.colour.startswith("#")


def test_invocation_templates() -> None:
    assert AGENT_CLIS["claude"].build_argv("/bin/claude", "do it") == ["/bin/claude", "-p", "do it"]
    assert AGENT_CLIS["codex"].build_argv("/bin/codex", "do it") == ["/bin/codex", "exec", "do it"]
    assert AGENT_CLIS["opencode"].build_argv("/bin/op", "do it") == ["/bin/op", "run", "do it"]
    assert AGENT_CLIS["aider"].build_argv("/bin/aider", "do it") == [
        "/bin/aider",
        "--message",
        "do it",
        "--yes-always",
    ]


# -- detection -------------------------------------------------------------


def test_detection_with_monkeypatched_which() -> None:
    def fake_which(name: str) -> str | None:
        return f"/fake/bin/{name}" if name in {"claude", "codex"} else None

    statuses = {status.spec.key: status for status in detect_agents(which=fake_which)}
    assert statuses["claude"].available is True
    assert statuses["claude"].path == "/fake/bin/claude"
    assert statuses["codex"].available is True
    assert statuses["gemini"].available is False
    assert statuses["aider"].available is False


def test_detection_with_nothing_installed() -> None:
    statuses = detect_agents(which=lambda _name: None)
    assert statuses  # the cast still lists everyone
    assert all(not status.available for status in statuses)


# -- running a teammate ------------------------------------------------------


def test_run_teammate_success_records_transcript_and_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    _plant_fake_agent(bin_dir, "claude", _ECHO_BODY)
    _on_path(monkeypatch, bin_dir)
    teammates_dir = tmp_path / "teammates"
    workspace = tmp_path / "workspace"

    result = run_teammate(
        "claude",
        "fix the parser",
        cwd=workspace,
        timeout=30,
        teammates_dir=teammates_dir,
    )
    assert result.ok is True
    assert result.exit_code == 0
    assert "-p" in result.output
    assert "fix the parser" in result.output

    home = teammates_dir / "claude"
    card = json.loads((home / "character.json").read_text(encoding="utf-8"))
    assert card["name"] == "Claude"
    assert card["agent"] == "claude"
    assert card["role"] == "the senior engineer"
    assert card["created"]

    lines = (home / "transcript.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["agent"] == "claude"
    assert entry["task"] == "fix the parser"
    assert entry["exit_code"] == 0
    assert entry["timed_out"] is False
    assert "fix the parser" in entry["output"]
    assert entry["timestamp"]

    notes = (home / "notes.md").read_text(encoding="utf-8")
    assert "fix the parser → done" in notes
    assert run_count(teammates_dir, AGENT_CLIS["claude"]) == 1


def test_run_teammate_nonzero_exit_captures_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    _plant_fake_agent(
        bin_dir,
        "codex",
        "import sys\nprint('working on it')\nprint('it broke', file=sys.stderr)\nsys.exit(3)\n",
    )
    _on_path(monkeypatch, bin_dir)
    result = run_teammate(
        "codex", "build it", cwd=tmp_path, timeout=30, teammates_dir=tmp_path / "teammates"
    )
    assert result.ok is False
    assert result.exit_code == 3
    assert "working on it" in result.output
    assert "it broke" in result.output
    notes = (tmp_path / "teammates" / "codex" / "notes.md").read_text(encoding="utf-8")
    assert "failed (exit 3)" in notes


def test_run_teammate_timeout_kills_and_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    _plant_fake_agent(bin_dir, "gemini", "import time\ntime.sleep(30)\n")
    _on_path(monkeypatch, bin_dir)
    result = run_teammate(
        "gemini", "research slowly", cwd=tmp_path, timeout=1, teammates_dir=tmp_path / "teammates"
    )
    assert result.timed_out is True
    assert result.exit_code is None
    assert result.ok is False
    entry = json.loads(
        (tmp_path / "teammates" / "gemini" / "transcript.jsonl").read_text(encoding="utf-8").strip()
    )
    assert entry["timed_out"] is True
    assert entry["exit_code"] is None


def test_run_teammate_resolves_display_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    _plant_fake_agent(bin_dir, "opencode", _ECHO_BODY)
    _on_path(monkeypatch, bin_dir)
    result = run_teammate(
        "Otto", "tidy up", cwd=tmp_path, timeout=30, teammates_dir=tmp_path / "teammates"
    )
    assert result.ok is True
    assert result.spec.key == "opencode"
    assert (tmp_path / "teammates" / "opencode" / "transcript.jsonl").exists()


def test_run_teammate_unknown_agent_is_a_clean_error(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="Unknown teammate"):
        run_teammate(
            "skynet", "do it", cwd=tmp_path, timeout=5, teammates_dir=tmp_path / "teammates"
        )


def test_run_teammate_missing_binary_is_a_clean_error(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="not installed"):
        run_teammate(
            "claude",
            "do it",
            cwd=tmp_path,
            timeout=5,
            teammates_dir=tmp_path / "teammates",
            which=lambda _name: None,
        )


def test_run_teammate_output_is_truncated_to_the_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    _plant_fake_agent(bin_dir, "claude", "print('x' * 20000)\nprint('THE END')\n")
    _on_path(monkeypatch, bin_dir)
    result = run_teammate(
        "claude", "be verbose", cwd=tmp_path, timeout=30, teammates_dir=tmp_path / "teammates"
    )
    assert len(result.output) <= 8100
    assert "truncated" in result.output
    assert "THE END" in result.output


# -- the tool and the gate ---------------------------------------------------


def _registry_with_fake_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, marker: Path
) -> ToolRegistry:
    bin_dir = tmp_path / "bin"
    _plant_fake_agent(
        bin_dir,
        "claude",
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\nprint('did it')\n",
    )
    _on_path(monkeypatch, bin_dir)
    registry = ToolRegistry()
    register_teammate_tools(
        registry,
        workspace_root=tmp_path / "workspace",
        teammates_dir=tmp_path / "teammates",
        timeout=30,
    )
    return registry


def test_delegate_task_is_registered_as_acting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry_with_fake_claude(tmp_path, monkeypatch, tmp_path / "marker")
    tool = registry.get("delegate_task")
    assert tool is not None
    assert tool.read_only is False


def test_delegate_task_declined_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "marker"
    registry = _registry_with_fake_claude(tmp_path, monkeypatch, marker)
    script = [
        ProviderResponse(
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="delegate_task",
                    arguments={"agent": "claude", "task": "fix it"},
                )
            ]
        ),
        ProviderResponse(text="ok"),
    ]
    agent = Agent(
        provider=FakeProvider(script=script),
        registry=registry,
        sessions=SessionStore(tmp_path / "sessions"),
    )
    result = agent.run(None, "delegate to claude: fix it", approver=approve_none)
    assert any(event.kind == "declined" for event in result.events)
    # The gate held: the fake binary was never executed — no marker,
    # no transcript, no character home.
    assert not marker.exists()
    assert not (tmp_path / "teammates").exists()


def test_delegate_task_approved_runs_the_teammate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "marker"
    registry = _registry_with_fake_claude(tmp_path, monkeypatch, marker)
    script = [
        ProviderResponse(
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="delegate_task",
                    arguments={"agent": "claude", "task": "fix it"},
                )
            ]
        ),
        ProviderResponse(text="ok"),
    ]
    agent = Agent(
        provider=FakeProvider(script=script),
        registry=registry,
        sessions=SessionStore(tmp_path / "sessions"),
    )
    result = agent.run(None, "delegate to claude: fix it", approver=approve_all)
    assert marker.exists()
    tool_results = [e.text for e in result.events if e.kind == "tool_result"]
    assert "did it" in tool_results[0]


def test_delegate_task_unknown_agent_errors_cleanly_through_the_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry_with_fake_claude(tmp_path, monkeypatch, tmp_path / "marker")
    with pytest.raises(ToolError, match="Unknown teammate"):
        registry.call("delegate_task", {"agent": "skynet", "task": "do it"})


# -- registration rule in the runtime -----------------------------------------


def _no_agents(_which: object = None) -> list[AgentStatus]:
    return [AgentStatus(spec=spec, path=None) for spec in AGENT_CLIS.values()]


def test_runtime_registers_delegate_only_when_a_teammate_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime_module, "detect_agents", _no_agents)
    settings = Settings(data_dir=tmp_path / "data", provider="fake")
    runtime = build_runtime(settings, provider=FakeProvider(), offline=True)
    try:
        assert "delegate_task" not in runtime.registry.names()
    finally:
        runtime.close()


def test_runtime_registers_delegate_when_explicitly_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime_module, "detect_agents", _no_agents)
    settings = Settings(data_dir=tmp_path / "data", provider="fake", teammates=True)
    runtime = build_runtime(settings, provider=FakeProvider(), offline=True)
    try:
        assert "delegate_task" in runtime.registry.names()
    finally:
        runtime.close()


def test_runtime_teammates_off_removes_the_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    _plant_fake_agent(bin_dir, "claude", _ECHO_BODY)
    _on_path(monkeypatch, bin_dir)
    settings = Settings(data_dir=tmp_path / "data", provider="fake", teammates=False)
    runtime = build_runtime(settings, provider=FakeProvider(), offline=True)
    try:
        assert "delegate_task" not in runtime.registry.names()
    finally:
        runtime.close()


# -- the fake provider's delegation intents ------------------------------------


def _delegate_schema() -> list[dict]:
    registry = ToolRegistry()
    register_teammate_tools(
        registry,
        workspace_root=Path("/tmp"),
        teammates_dir=Path("/tmp"),
        timeout=30,
    )
    return registry.schemas()


@pytest.mark.parametrize(
    "text,agent,task",
    [
        ("Delegate to claude: fix the parser", "claude", "fix the parser"),
        ("delegate to codex: build a prototype", "codex", "build a prototype"),
        ("Ask gemini to research vector databases", "gemini", "research vector databases"),
        ("ask otto to tidy the repo", "otto", "tidy the repo"),
    ],
)
def test_fake_provider_delegate_intents(text: str, agent: str, task: str) -> None:
    provider = FakeProvider()
    response = provider.chat([{"role": "user", "content": text}], _delegate_schema())
    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert call.name == "delegate_task"
    assert call.arguments == {"agent": agent, "task": task}


def test_fake_provider_ask_me_is_not_a_delegation() -> None:
    provider = FakeProvider()
    response = provider.chat(
        [{"role": "user", "content": "Ask me to remember this later"}], _delegate_schema()
    )
    assert all(call.name != "delegate_task" for call in response.tool_calls)


# -- CLI: agents + team ---------------------------------------------------------


def test_agents_command_never_errors(tmp_path: Path) -> None:
    env = {
        "MAJORDOMO_DATA_DIR": str(tmp_path / "data"),
        "MAJORDOMO_PROVIDER": "fake",
        "COLUMNS": "220",
    }
    result = runner.invoke(app, ["agents"], env=env)
    assert result.exit_code == 0
    assert "Claude" in result.stdout
    assert "Otto" in result.stdout
    assert "senior engineer" in result.stdout


def test_team_command_prints_the_roster(tmp_path: Path) -> None:
    env = {"MAJORDOMO_DATA_DIR": str(tmp_path / "data"), "MAJORDOMO_PROVIDER": "fake"}
    result = runner.invoke(app, ["team"], env=env)
    assert result.exit_code == 0
    assert "chief of staff" in result.stdout
    assert "Codex" in result.stdout
    assert "fast prototyper" in result.stdout
    assert "their own logins" in result.stdout


def test_agents_command_shows_run_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    _plant_fake_agent(bin_dir, "claude", _ECHO_BODY)
    _on_path(monkeypatch, bin_dir)
    data_dir = tmp_path / "data"
    run_teammate(
        "claude", "one job", cwd=tmp_path, timeout=30, teammates_dir=data_dir / "teammates"
    )
    env = {"MAJORDOMO_DATA_DIR": str(data_dir), "MAJORDOMO_PROVIDER": "fake"}
    result = runner.invoke(app, ["agents"], env=env)
    assert result.exit_code == 0
    claude_line = next(line for line in result.stdout.splitlines() if "Claude" in line)
    assert "1" in claude_line
