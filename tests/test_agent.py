"""The agent loop: tool dispatch, the approval gate, persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from majordomo.agent import Agent
from majordomo.providers import FakeProvider, ProviderResponse, ToolCall
from majordomo.sessions import SessionStore
from majordomo.tools import Tool, ToolRegistry, approve_all, approve_none


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="look",
            description="read-only look",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda: "you see a door",
            read_only=True,
        )
    )
    reg.register(
        Tool(
            name="open",
            description="acting open",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda: "the door is open",
            read_only=False,
        )
    )
    return reg


def _agent(tmp_path: Path, script: list[ProviderResponse], registry: ToolRegistry) -> Agent:
    return Agent(
        provider=FakeProvider(script=script),
        registry=registry,
        sessions=SessionStore(tmp_path / "sessions"),
    )


def _call(name: str) -> ProviderResponse:
    return ProviderResponse(tool_calls=[ToolCall(id="c1", name=name, arguments={})])


def test_plain_reply_roundtrip(tmp_path: Path, registry: ToolRegistry) -> None:
    agent = _agent(tmp_path, [ProviderResponse(text="Hello, Kevin.")], registry)
    result = agent.run(None, "hi", approver=approve_none)
    assert result.text == "Hello, Kevin."
    assert result.session_id


def test_read_only_tool_runs_without_approval(tmp_path: Path, registry: ToolRegistry) -> None:
    agent = _agent(tmp_path, [_call("look"), ProviderResponse(text="done")], registry)
    result = agent.run(None, "look around", approver=approve_none)
    assert result.text == "done"
    tool_results = [e for e in result.events if e.kind == "tool_result"]
    assert tool_results[0].text == "you see a door"


def test_acting_tool_declined_without_approval(tmp_path: Path, registry: ToolRegistry) -> None:
    agent = _agent(tmp_path, [_call("open"), ProviderResponse(text="ok")], registry)
    result = agent.run(None, "open it", approver=approve_none)
    assert any(e.kind == "declined" for e in result.events)
    tool_results = [e for e in result.events if e.kind == "tool_result"]
    assert "Declined" in tool_results[0].text
    assert "the door is open" not in tool_results[0].text


def test_acting_tool_runs_with_approval(tmp_path: Path, registry: ToolRegistry) -> None:
    agent = _agent(tmp_path, [_call("open"), ProviderResponse(text="ok")], registry)
    result = agent.run(None, "open it", approver=approve_all)
    tool_results = [e for e in result.events if e.kind == "tool_result"]
    assert tool_results[0].text == "the door is open"


def test_unknown_tool_is_an_error_not_a_crash(tmp_path: Path, registry: ToolRegistry) -> None:
    agent = _agent(tmp_path, [_call("nope"), ProviderResponse(text="ok")], registry)
    result = agent.run(None, "do the thing", approver=approve_all)
    tool_results = [e for e in result.events if e.kind == "tool_result"]
    assert "unknown tool" in tool_results[0].text


def test_tool_exception_surfaces_as_error_text(tmp_path: Path) -> None:
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="boom",
            description="fails",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda: (_ for _ in ()).throw(RuntimeError("kaboom")),
            read_only=True,
        )
    )
    agent = _agent(tmp_path, [_call("boom"), ProviderResponse(text="ok")], reg)
    result = agent.run(None, "boom", approver=approve_all)
    tool_results = [e for e in result.events if e.kind == "tool_result"]
    assert "kaboom" in tool_results[0].text


def test_provider_failure_is_reported_and_session_saved(
    tmp_path: Path, registry: ToolRegistry
) -> None:
    class Exploding(FakeProvider):
        def chat(self, messages, tools):  # type: ignore[override]
            raise RuntimeError("provider down")

    sessions = SessionStore(tmp_path / "sessions")
    agent = Agent(provider=Exploding(), registry=registry, sessions=sessions)
    result = agent.run(None, "hi", approver=approve_all)
    assert "provider failed" in result.text.lower()
    saved = sessions.get(result.session_id)
    assert saved is not None
    assert saved["messages"][0]["content"] == "hi"


def test_session_persists_across_runs(tmp_path: Path, registry: ToolRegistry) -> None:
    agent = _agent(
        tmp_path, [ProviderResponse(text="first"), ProviderResponse(text="second")], registry
    )
    first = agent.run(None, "one", approver=approve_all)
    second = agent.run(first.session_id, "two", approver=approve_all)
    assert second.session_id == first.session_id
    saved = agent.sessions.get(first.session_id)
    assert saved is not None
    contents = [m.get("content") for m in saved["messages"]]
    assert contents == ["one", "first", "two", "second"]


def test_title_comes_from_first_message(tmp_path: Path, registry: ToolRegistry) -> None:
    agent = _agent(tmp_path, [ProviderResponse(text="ok")], registry)
    result = agent.run(None, "Plan the Lisbon trip", approver=approve_all)
    saved = agent.sessions.get(result.session_id)
    assert saved is not None
    assert saved["title"] == "Plan the Lisbon trip"


def test_max_steps_stops_the_loop(tmp_path: Path, registry: ToolRegistry) -> None:
    script = [_call("look")] * 20
    agent = _agent(tmp_path, script, registry)
    agent.max_steps = 3
    result = agent.run(None, "keep looking", approver=approve_all)
    assert "stopped after 3" in result.text
