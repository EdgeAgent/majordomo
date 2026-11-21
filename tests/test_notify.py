"""Notifications: the webhook sender, the CLI test command, and the
initiative engine's "needs you / done" wiring.

No real network leaves the machine: sends go to a fake opener or to
an HTTP sink on 127.0.0.1 that the test itself runs.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Self

from typer.testing import CliRunner

from majordomo.cli import app
from majordomo.config import Settings
from majordomo.initiative import InitiativeEngine
from majordomo.mailtools import MailMessage
from majordomo.notify import Notifier, send_notification
from majordomo.providers import FakeProvider
from majordomo.runtime import build_runtime
from majordomo.scheduler import ScheduleStore
from majordomo.sessions import SessionStore

runner = CliRunner()
T0 = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)


# -- a local HTTP sink -------------------------------------------------------


class _Sink:
    """A real HTTP server on loopback that records what it receives."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        sink = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                sink.requests.append(
                    {
                        "path": self.path,
                        "content_type": self.headers.get("Content-Type"),
                        "json": json.loads(body.decode("utf-8")),
                    }
                )
                self.send_response(200)
                self.end_headers()

            def log_message(self, *_args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/hook"

    def __enter__(self) -> Self:
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        pass


# -- send_notification ---------------------------------------------------------


def test_send_notification_posts_the_documented_payload() -> None:
    captured: dict[str, Any] = {}

    def opener(request: Any, timeout: float | None = None) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["content_type"] = request.headers.get("Content-type")
        return _FakeResponse(200)

    assert send_notification("Needs you", "the body", "https://example.com/hook", opener=opener)
    assert captured["url"] == "https://example.com/hook"
    assert captured["payload"] == {
        "title": "Needs you",
        "body": "the body",
        "source": "majordomo",
    }
    assert captured["content_type"] == "application/json"


def test_send_notification_without_a_url_is_a_quiet_false() -> None:
    def opener(_request: Any, timeout: float | None = None) -> _FakeResponse:
        raise AssertionError("no send may be attempted without a URL")

    assert send_notification("t", "b", None, opener=opener) is False
    assert send_notification("t", "b", "", opener=opener) is False


def test_send_notification_failures_are_swallowed() -> None:
    def boom(_request: Any, timeout: float | None = None) -> _FakeResponse:
        raise OSError("connection refused")

    assert send_notification("t", "b", "https://example.com/hook", opener=boom) is False

    def sad_server(_request: Any, timeout: float | None = None) -> _FakeResponse:
        return _FakeResponse(500)

    assert send_notification("t", "b", "https://example.com/hook", opener=sad_server) is False


def test_send_notification_to_a_real_local_sink() -> None:
    with _Sink() as sink:
        assert send_notification("Hello", "from the test", sink.url) is True
        assert len(sink.requests) == 1
        assert sink.requests[0]["json"] == {
            "title": "Hello",
            "body": "from the test",
            "source": "majordomo",
        }
        assert sink.requests[0]["content_type"] == "application/json"


def test_notifier_enabled_flag() -> None:
    assert Notifier(None).enabled is False
    assert Notifier("").enabled is False
    assert Notifier("https://example.com/hook").enabled is True
    assert Notifier(None).notify("t", "b") is False


# -- the CLI test command --------------------------------------------------------


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {"MAJORDOMO_DATA_DIR": str(tmp_path / "data"), "MAJORDOMO_PROVIDER": "fake"}
    env.update(extra)
    return env


def test_cli_notify_without_a_webhook_fails_honestly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["notify", "Hi", "Body"], env=_env(tmp_path))
    assert result.exit_code == 1
    assert "not set" in result.stdout


def test_cli_notify_with_a_sink_succeeds(tmp_path: Path) -> None:
    with _Sink() as sink:
        result = runner.invoke(
            app,
            ["notify", "Test title", "Test body"],
            env=_env(tmp_path, MAJORDOMO_NOTIFY_WEBHOOK=sink.url),
        )
        assert result.exit_code == 0
        assert "Notification sent." in result.stdout
        assert sink.requests[0]["json"]["title"] == "Test title"


def test_cli_notify_to_a_dead_webhook_fails_honestly(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["notify", "Hi", "Body"],
        env=_env(tmp_path, MAJORDOMO_NOTIFY_WEBHOOK="http://127.0.0.1:1/hook"),
    )
    assert result.exit_code == 1
    assert "failed" in result.stdout


# -- initiative wiring ------------------------------------------------------------


class StubMail:
    """A mail backend the test controls message by message."""

    name = "stub"

    def __init__(self, messages: list[MailMessage]) -> None:
        self.messages = list(messages)

    def list_messages(self, limit: int = 10) -> list[MailMessage]:
        return self.messages[:limit]

    def read_message(self, message_id: str) -> MailMessage:
        for message in self.messages:
            if message.id == message_id:
                return message
        raise KeyError(message_id)

    def search(self, query: str) -> list[MailMessage]:
        return [m for m in self.messages if query.lower() in m.subject.lower()]

    def send(self, to: str, subject: str, body: str) -> str:
        raise AssertionError("the initiative engine must never send mail")


def _message(message_id: str, subject: str) -> MailMessage:
    return MailMessage(
        id=message_id,
        sender="Ada Lovelace <ada@example.com>",
        to="you@example.com",
        subject=subject,
        date="Tue, 21 Nov 2026 09:00:00 +0000",
        body="(stub message)",
    )


def _engine(tmp_path: Path, backend: StubMail, notify_fn: object) -> InitiativeEngine:
    return InitiativeEngine(
        backend=backend,
        schedules=ScheduleStore(tmp_path / "schedules.json"),
        sessions=SessionStore(tmp_path / "sessions"),
        state_path=tmp_path / "initiative.json",
        now_fn=lambda: T0,
        notify_fn=notify_fn,  # type: ignore[arg-type]
    )


def test_tick_notifies_on_a_new_mail_digest(tmp_path: Path) -> None:
    sent: list[tuple[str, str]] = []
    backend = StubMail([_message("m1", "Old news")])
    engine = _engine(tmp_path, backend, lambda title, body: sent.append((title, body)))
    assert engine.tick(T0) == []  # baseline: no digest, no notification
    assert sent == []

    backend.messages.append(_message("m2", "Fresh off the press"))
    actions = engine.tick(T0 + timedelta(minutes=5))
    assert len(actions) == 1
    assert len(sent) == 1
    title, body = sent[0]
    assert "new mail" in title
    assert "Fresh off the press" in body


def test_tick_notifies_on_an_escalation(tmp_path: Path) -> None:
    sent: list[tuple[str, str]] = []
    backend = StubMail([])
    engine = _engine(tmp_path, backend, lambda title, body: sent.append((title, body)))
    schedules = ScheduleStore(tmp_path / "schedules.json")
    engine.schedules = schedules
    schedules.add("Call the bank", T0 - timedelta(minutes=1))
    fired = schedules.fire_due(T0)
    engine.tick(T0, fired)
    assert sent == []

    engine.tick(T0 + timedelta(hours=2, minutes=30))
    assert len(sent) == 1
    title, body = sent[0]
    assert "needs you" in title
    assert "Call the bank" in body


def test_a_broken_notifier_never_breaks_the_tick(tmp_path: Path) -> None:
    def boom(_title: str, _body: str) -> None:
        raise RuntimeError("webhook exploded")

    backend = StubMail([_message("m1", "Old news")])
    engine = _engine(tmp_path, backend, boom)
    engine.tick(T0)
    backend.messages.append(_message("m2", "Fresh off the press"))
    actions = engine.tick(T0 + timedelta(minutes=5))
    assert len(actions) == 1  # the digest still landed in the inbox


def test_runtime_wires_the_notifier_only_when_configured(tmp_path: Path) -> None:
    plain = build_runtime(
        Settings(data_dir=tmp_path / "a", provider="fake"),
        provider=FakeProvider(),
        offline=True,
    )
    try:
        assert plain.notifier.enabled is False
        assert plain.initiative.notify_fn is None
    finally:
        plain.close()

    wired = build_runtime(
        Settings(
            data_dir=tmp_path / "b",
            provider="fake",
            notify_webhook="http://127.0.0.1:9/hook",
        ),
        provider=FakeProvider(),
        offline=True,
    )
    try:
        assert wired.notifier.enabled is True
        assert wired.initiative.notify_fn is not None
    finally:
        wired.close()


def test_daemon_escalation_reaches_the_webhook(tmp_path: Path) -> None:
    """End to end through the real daemon: a reminder fires on one
    tick; once it has sat unacknowledged past two hours (the state
    file is backdated, as a long afternoon would leave it), the next
    tick escalates — and the escalation lands on the webhook."""
    with _Sink() as sink:
        env = _env(tmp_path, MAJORDOMO_NOTIFY_WEBHOOK=sink.url)
        added = runner.invoke(
            app, ["schedule", "add", "Call the bank", "--in-minutes", "0"], env=env
        )
        assert added.exit_code == 0

        first = runner.invoke(app, ["daemon", "--once"], env=env)
        assert first.exit_code == 0
        assert "Call the bank" in first.stdout
        assert sink.requests == []  # firing alone is not a notification

        state_path = tmp_path / "data" / "initiative.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        (record,) = state["fired"].values()
        fired_at = datetime.fromisoformat(record["fired_at"])
        record["fired_at"] = (fired_at - timedelta(hours=3)).isoformat()
        state_path.write_text(json.dumps(state), encoding="utf-8")

        second = runner.invoke(app, ["daemon", "--once"], env=env)
        assert second.exit_code == 0
        assert "Still waiting" in second.stdout
        assert len(sink.requests) == 1
        payload = sink.requests[0]["json"]
        assert payload["source"] == "majordomo"
        assert "needs you" in payload["title"]
        assert "Call the bank" in payload["body"]
