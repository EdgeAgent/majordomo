"""The company layer: roster with roles/goals/budgets + a task board."""

from __future__ import annotations

from pathlib import Path

import pytest

from majordomo.company import CompanyStore, register_company_tools
from majordomo.tools import ToolError, ToolRegistry


@pytest.fixture()
def store(tmp_path: Path) -> CompanyStore:
    return CompanyStore(tmp_path / "company.json")


def test_set_agent_and_roster_round_trip(store: CompanyStore) -> None:
    agent = store.set_agent("claude", role="the senior engineer", goal="ship v0.9", budget=25.0)
    assert agent["name"] == "claude"
    assert agent["budget"] == 25.0
    assert store.get_agent("Claude")["goal"] == "ship v0.9"
    assert [a["name"] for a in store.agents()] == ["claude"]


def test_set_agent_updates_in_place(store: CompanyStore) -> None:
    store.set_agent("codex", role="prototyper")
    store.set_agent("codex", role="reviewer", budget=5)
    assert len(store.agents()) == 1
    assert store.get_agent("codex")["role"] == "reviewer"


def test_set_agent_rejects_negative_budget_and_empty_name(store: CompanyStore) -> None:
    with pytest.raises(ToolError):
        store.set_agent("claude", budget=-1)
    with pytest.raises(ToolError):
        store.set_agent("  ")


def test_board_lifecycle(store: CompanyStore) -> None:
    task = store.add_task("Write the report", owner="claude")
    assert task["status"] == "queued"
    store.set_task_status(task["id"], "running")
    done = store.set_task_status(task["id"], "done")
    assert done["status"] == "done"
    assert store.tasks(status="done")[0]["id"] == task["id"]
    assert store.tasks(status="queued") == []


def test_board_rejects_unknown_task_and_bad_status(store: CompanyStore) -> None:
    with pytest.raises(ToolError):
        store.set_task_status(99, "done")
    task = store.add_task("X")
    with pytest.raises(ToolError):
        store.set_task_status(task["id"], "vanished")


def test_summary_mentions_roster_board_and_run_counts(store: CompanyStore, tmp_path: Path) -> None:
    store.set_agent("claude", role="the senior engineer", goal="ship it", budget=10)
    store.add_task("Do the thing", owner="claude")
    summary = store.summary(teammates_dir=tmp_path / "teammates")
    assert "claude" in summary
    assert "the senior engineer" in summary
    assert "ship it" in summary
    assert "queued: 1" in summary


def test_tools_registered_with_right_risk_classes(store: CompanyStore, tmp_path: Path) -> None:
    registry = ToolRegistry()
    register_company_tools(registry, store, teammates_dir=tmp_path / "teammates")
    assert registry.get("company_summary").read_only is True
    assert registry.get("company_board").read_only is True
    assert registry.get("company_set_agent").read_only is False
    assert registry.get("company_add_task").read_only is False
    assert registry.get("company_set_task_status").read_only is False
    out = registry.call("company_set_agent", {"name": "gemini", "role": "the researcher"})
    assert "gemini" in out
    out = registry.call("company_add_task", {"title": "Research X", "owner": "gemini"})
    assert "Research X" in out
    assert "Research X" in registry.call("company_board", {})
