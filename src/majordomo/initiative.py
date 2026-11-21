"""Initiative: the small jobs Majordomo does without being asked.

The daemon (and the web app's background tick) already fire due
reminders. The :class:`InitiativeEngine` runs alongside that firing,
once per tick, and adds two read-only habits:

- **Mail watch.** Poll the mailbox; any message whose id has never
  been seen gets a one-line digest in the ``inbox`` session
  ("📬 New mail from X: subject"). The first tick ever only
  establishes the baseline — the existing inbox is not news.
- **Escalation.** A reminder the engine watched fire, that is still
  sitting unacknowledged more than two hours later, is surfaced once
  more with a "still waiting" note.

Everything the engine does is read-only in spirit: it never sends
mail and never calls an acting tool. Its memory is one small JSON
state file in the data directory — seen mail ids, and the reminders
it watched fire — so nothing is digested or escalated twice, even
across restarts.

The acknowledgement rule, stated plainly because the schedule store
has no ack button: a fired reminder counts as *acknowledged* when it
leaves the schedule store (the user cancelled or cleared it — an
action, taken on purpose). A one-time reminder that merely sits in
the store as done is *not* an acknowledgement — firing marked it
done, the user may never have seen it — so it stays eligible for the
one escalation. Recurring reminders leave the fired list when they
fire again (the new firing restarts their clock).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from pathlib import Path

import structlog

from .mailtools import MailBackend
from .scheduler import Reminder, ScheduleStore
from .sessions import SessionStore

log = structlog.get_logger(__name__)

ESCALATE_AFTER = timedelta(hours=2)
_MAIL_POLL_LIMIT = 25


def _empty_state() -> dict:
    return {"seen_mail_ids": None, "fired": {}}


def load_state(path: Path) -> dict:
    """Read the initiative state file; a missing/corrupt file is empty state."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_state()
    if not isinstance(raw, dict):
        return _empty_state()
    state = _empty_state()
    if isinstance(raw.get("seen_mail_ids"), list):
        state["seen_mail_ids"] = [str(item) for item in raw["seen_mail_ids"]]
    if isinstance(raw.get("fired"), dict):
        state["fired"] = raw["fired"]
    return state


def read_seen_mail_ids(path: Path) -> set[str] | None:
    """The seen-mail id set from the state file, or None before any baseline."""
    seen = load_state(path)["seen_mail_ids"]
    return None if seen is None else set(seen)


class InitiativeEngine:
    """Mail watch + reminder escalation, one tick at a time.

    Fully injectable: hand it a (fake) mail backend, a schedule store,
    a session store, a state path, and a clock, and every behaviour is
    deterministic.
    """

    def __init__(
        self,
        backend: MailBackend,
        schedules: ScheduleStore,
        sessions: SessionStore,
        state_path: Path,
        now_fn: Callable[[], datetime],
    ) -> None:
        self.backend = backend
        self.schedules = schedules
        self.sessions = sessions
        self.state_path = state_path
        self.now_fn = now_fn

    # -- state ---------------------------------------------------------

    def _save(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    # -- the tick --------------------------------------------------------

    def tick(self, now: datetime | None = None, just_fired: Iterable[Reminder] = ()) -> list[str]:
        """Run one initiative tick; return the action lines it produced.

        ``just_fired`` is what ``ScheduleStore.fire_due`` returned for
        this same tick — the engine records those firings so it can
        escalate the ones nobody acknowledges. Every action line is
        also appended to the ``inbox`` session, the same sink fired
        reminders land in.
        """
        now = now or self.now_fn()
        state = load_state(self.state_path)
        self._record_fired(state, just_fired, now)
        actions = self._mail_watch(state)
        actions += self._escalations(state, now)
        self._save(state)
        for line in actions:
            self.sessions.append("inbox", {"role": "assistant", "content": line})
        return actions

    # -- mail watch ------------------------------------------------------

    def _mail_watch(self, state: dict) -> list[str]:
        try:
            messages = self.backend.list_messages(_MAIL_POLL_LIMIT)
        except Exception:  # noqa: BLE001 - an unconfigured/broken mailbox is skipped, not fatal
            log.info("initiative.mail_watch_skipped")
            return []
        current_ids = [message.id for message in messages]
        seen = state["seen_mail_ids"]
        if seen is None:
            # First tick ever: everything already in the inbox is the
            # baseline, not news. Only later arrivals get digested.
            state["seen_mail_ids"] = current_ids
            return []
        known = set(seen)
        actions = [
            f"📬 New mail from {message.sender}: {message.subject}"
            for message in messages
            if message.id not in known
        ]
        state["seen_mail_ids"] = sorted(known | set(current_ids))
        return actions

    # -- escalation --------------------------------------------------------

    def _record_fired(self, state: dict, just_fired: Iterable[Reminder], now: datetime) -> None:
        fired = state["fired"]
        for reminder in just_fired:
            # A (re)firing restarts the clock and clears any old
            # escalation: this firing has not been ignored yet.
            fired[reminder.id] = {
                "text": reminder.text,
                "fired_at": now.isoformat(),
                "escalated": False,
            }

    def _escalations(self, state: dict, now: datetime) -> list[str]:
        fired = state["fired"]
        if not fired:
            return []
        # Acknowledged = gone from the store (cancelled/cleared by the
        # user). Anything else that fired is still waiting on them.
        live_ids = {reminder.id for reminder in self.schedules.list(include_done=True)}
        actions: list[str] = []
        for reminder_id in list(fired):
            record = fired[reminder_id]
            if reminder_id not in live_ids:
                del fired[reminder_id]
                continue
            if record.get("escalated"):
                continue
            try:
                fired_at = datetime.fromisoformat(str(record.get("fired_at", "")))
            except ValueError:
                continue
            if now - fired_at >= ESCALATE_AFTER:
                record["escalated"] = True
                actions.append(
                    f"⏰ Still waiting: {record.get('text', '')} "
                    f"(fired at {fired_at:%H:%M}, not acknowledged yet)"
                )
        return actions
