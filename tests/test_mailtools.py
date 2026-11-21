"""Mail tools: the fake mailbox, the honest unconfigured backend,
backend selection, and the tools' place in the registry and the gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from majordomo.config import Settings
from majordomo.mailtools import (
    FakeMailBackend,
    ImapSmtpBackend,
    MailError,
    UnconfiguredMailBackend,
    build_mail_backend,
)
from majordomo.providers import FakeProvider, ProviderResponse, ToolCall
from majordomo.runtime import Runtime, build_runtime
from majordomo.tools import ToolError, approve_all, approve_none


def test_fake_mailbox_is_seeded_and_clearly_fake() -> None:
    backend = FakeMailBackend()
    messages = backend.list_messages()
    assert len(messages) >= 3
    assert all("example.com" in message.sender for message in messages)
    assert "Analytical Engine" in messages[0].subject


def test_fake_read_message_and_unknown_id() -> None:
    backend = FakeMailBackend()
    message = backend.read_message("fake-2")
    assert "moth" in message.body.lower()
    with pytest.raises(MailError, match="No message with id"):
        backend.read_message("fake-999")


def test_fake_search_matches_sender_subject_and_body() -> None:
    backend = FakeMailBackend()
    assert [m.id for m in backend.search("hopper")] == ["fake-2"]
    assert [m.id for m in backend.search("ANALYTICAL")] == ["fake-1"]
    assert [m.id for m in backend.search("compiler")] == ["fake-2"]
    assert backend.search("no-such-thing") == []


def test_fake_send_is_recorded_and_stamped_fake() -> None:
    backend = FakeMailBackend()
    result = backend.send("friend@example.com", "Hello", "Body text")
    assert "fake" in result.lower()
    assert "Nothing was delivered" in result
    assert backend.sent == [
        {"to": "friend@example.com", "subject": "Hello", "body": "Body text", "fake": "yes"}
    ]


def test_unconfigured_backend_always_reports_not_configured() -> None:
    backend = UnconfiguredMailBackend()
    with pytest.raises(ToolError, match="Mail is not configured"):
        backend.list_messages()
    with pytest.raises(ToolError, match="Mail is not configured"):
        backend.read_message("1")
    with pytest.raises(ToolError, match="Mail is not configured"):
        backend.search("anything")
    with pytest.raises(ToolError, match="Mail is not configured"):
        backend.send("a@example.com", "s", "b")


def _configured_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        provider="ollama",
        mail_address="me@example.com",
        mail_username="me@example.com",
        mail_password="secret",
        mail_imap_host="imap.example.com",
        mail_smtp_host="smtp.example.com",
    )


def test_backend_selection_offline_is_fake(tmp_path: Path) -> None:
    backend = build_mail_backend(_configured_settings(tmp_path), offline=True)
    assert isinstance(backend, FakeMailBackend)


def test_backend_selection_configured_is_imap_smtp(tmp_path: Path) -> None:
    backend = build_mail_backend(_configured_settings(tmp_path), offline=False)
    assert isinstance(backend, ImapSmtpBackend)


def test_backend_selection_live_without_settings_is_unconfigured(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", provider="ollama")
    backend = build_mail_backend(settings, offline=False)
    assert isinstance(backend, UnconfiguredMailBackend)


def test_mail_tools_registered_with_the_right_classes(runtime: Runtime) -> None:
    expected = {
        "mail_list": True,
        "mail_read": True,
        "mail_search": True,
        "mail_draft": False,
        "mail_send": False,
    }
    for name, read_only in expected.items():
        tool = runtime.registry.get(name)
        assert tool is not None, name
        assert tool.read_only is read_only, name


def test_mail_list_tool_on_the_fake_backend(runtime: Runtime) -> None:
    result = runtime.registry.call("mail_list", {})
    assert "Analytical Engine" in result
    assert "fake-1" in result


def test_mail_read_and_search_tools(runtime: Runtime) -> None:
    full = runtime.registry.call("mail_read", {"message_id": "fake-3"})
    assert "fake inbox" in full.lower()
    hits = runtime.registry.call("mail_search", {"query": "moth"})
    assert "fake-2" in hits
    misses = runtime.registry.call("mail_search", {"query": "zzz-no-match"})
    assert "No messages match" in misses


def test_mail_draft_tool_writes_into_workspace_drafts(runtime: Runtime, tmp_path: Path) -> None:
    drafted = runtime.registry.call(
        "mail_draft",
        {"to": "ada@example.com", "subject": "Engine notes", "body": "Dear Ada,"},
    )
    assert "Draft saved" in drafted
    drafts_dir = tmp_path / "data" / "workspace" / "drafts"
    files = list(drafts_dir.glob("*.txt"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "To: ada@example.com" in content
    assert "Subject: Engine notes" in content
    assert "Dear Ada," in content


def _send_script() -> list[ProviderResponse]:
    return [
        ProviderResponse(
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="mail_send",
                    arguments={"to": "ada@example.com", "subject": "Hi", "body": "Hello."},
                )
            ]
        ),
        ProviderResponse(text="done"),
    ]


def test_mail_send_declined_without_approval(settings: Settings) -> None:
    runtime = build_runtime(settings, provider=FakeProvider(script=_send_script()), offline=True)
    try:
        result = runtime.agent.run(None, "send it", approver=approve_none)
        assert any(event.kind == "declined" for event in result.events)
        tool_results = [e.text for e in result.events if e.kind == "tool_result"]
        assert "Declined" in tool_results[0]
    finally:
        runtime.close()


def test_mail_send_runs_with_approval_on_the_fake_backend(settings: Settings) -> None:
    runtime = build_runtime(settings, provider=FakeProvider(script=_send_script()), offline=True)
    try:
        result = runtime.agent.run(None, "send it", approver=approve_all)
        tool_results = [e.text for e in result.events if e.kind == "tool_result"]
        assert "fake mail backend" in tool_results[0]
        assert "Nothing was delivered" in tool_results[0]
    finally:
        runtime.close()
