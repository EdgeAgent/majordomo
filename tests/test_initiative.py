"""The initiative engine: mail watch digests and reminder escalation,
on a fake backend and a fake clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from majordomo.initiative import InitiativeEngine
from majordomo.mailtools import MailMessage, UnconfiguredMailBackend
from majordomo.scheduler import ScheduleStore
from majordomo.sessions import SessionStore

T0 = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)


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


def _engine(
    tmp_path: Path, backend: object
) -> tuple[InitiativeEngine, ScheduleStore, SessionStore]:
    schedules = ScheduleStore(tmp_path / "schedules.json")
    sessions = SessionStore(tmp_path / "sessions")
    engine = InitiativeEngine(
        backend=backend,  # type: ignore[arg-type]
        schedules=schedules,
        sessions=sessions,
        state_path=tmp_path / "initiative.json",
        now_fn=lambda: T0,
    )
    return engine, schedules, sessions


def _inbox_texts(sessions: SessionStore) -> list[str]:
    inbox = sessions.get("inbox")
    assert inbox is not None
    return [str(message.get("content", "")) for message in inbox["messages"]]


def test_first_tick_baselines_the_inbox_silently(tmp_path: Path) -> None:
    backend = StubMail([_message("m1", "Old news"), _message("m2", "Older news")])
    engine, _schedules, _sessions = _engine(tmp_path, backend)
    assert engine.tick(T0) == []


def test_new_mail_is_digested_once_into_the_inbox(tmp_path: Path) -> None:
    backend = StubMail([_message("m1", "Old news")])
    engine, _schedules, sessions = _engine(tmp_path, backend)
    assert engine.tick(T0) == []

    backend.messages.append(_message("m2", "Fresh off the press"))
    actions = engine.tick(T0 + timedelta(minutes=5))
    assert actions == ["📬 New mail from Ada Lovelace <ada@example.com>: Fresh off the press"]
    assert any("Fresh off the press" in text for text in _inbox_texts(sessions))

    # The same message is never digested twice.
    assert engine.tick(T0 + timedelta(minutes=10)) == []


def test_seen_mail_survives_an_engine_restart(tmp_path: Path) -> None:
    backend = StubMail([_message("m1", "Old news")])
    engine, _schedules, _sessions = _engine(tmp_path, backend)
    engine.tick(T0)
    backend.messages.append(_message("m2", "Fresh off the press"))
    assert len(engine.tick(T0)) == 1

    restarted, _s, _sess = _engine(tmp_path, backend)
    assert restarted.tick(T0) == []


def test_unconfigured_mail_is_skipped_not_fatal(tmp_path: Path) -> None:
    engine, _schedules, _sessions = _engine(tmp_path, UnconfiguredMailBackend())
    assert engine.tick(T0) == []


def test_unacknowledged_reminder_escalates_once_after_two_hours(tmp_path: Path) -> None:
    backend = StubMail([])
    engine, schedules, sessions = _engine(tmp_path, backend)
    reminder = schedules.add("Call the bank", T0 - timedelta(minutes=1))
    fired = schedules.fire_due(T0)
    assert [item.id for item in fired] == [reminder.id]

    assert engine.tick(T0, fired) == []
    assert engine.tick(T0 + timedelta(hours=1)) == []
    actions = engine.tick(T0 + timedelta(hours=2, minutes=30))
    assert len(actions) == 1
    assert actions[0].startswith("⏰ Still waiting: Call the bank")
    assert any("Still waiting" in text for text in _inbox_texts(sessions))

    # Exactly once, however long it stays unacknowledged.
    assert engine.tick(T0 + timedelta(hours=5)) == []


def test_cancelled_reminder_never_escalates(tmp_path: Path) -> None:
    backend = StubMail([])
    engine, schedules, _sessions = _engine(tmp_path, backend)
    reminder = schedules.add("Call the bank", T0 - timedelta(minutes=1))
    fired = schedules.fire_due(T0)
    engine.tick(T0, fired)

    # Cancelling is the user's acknowledgement: it leaves the store.
    assert schedules.cancel(reminder.id)
    assert engine.tick(T0 + timedelta(hours=3)) == []
