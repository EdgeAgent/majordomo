"""The morning brief: today's state, assembled without a model.

``majordomo brief`` builds a short Markdown brief from real state —
active reminders (overdue ones called out), the mail situation (how
many messages are new since the initiative engine's baseline, and
the latest subjects), and the most recent memory entries. It is a
deterministic template over the same stores everything else uses:
no LLM, no invention, and a mail backend that is not configured
says so instead of pretending the inbox is empty.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .initiative import read_seen_mail_ids
from .mailtools import MailBackend
from .memory import MemoryStore
from .scheduler import ScheduleStore


def build_brief(
    *,
    schedules: ScheduleStore,
    backend: MailBackend,
    memory: MemoryStore,
    state_path: Path,
    now: datetime,
) -> str:
    """Assemble the brief text for ``now`` from the given stores."""
    lines = [f"# Majordomo brief — {now:%A, %B %d, %Y}", ""]

    lines.append("## Reminders")
    reminders = schedules.list()
    if not reminders:
        lines.append("Nothing scheduled.")
    else:
        for reminder in reminders:
            due = reminder.due_datetime()
            if due <= now:
                when = f"overdue (was due {due:%Y-%m-%d %H:%M})"
            elif due.date() == now.date():
                when = f"today at {due:%H:%M}"
            else:
                when = f"due {due:%Y-%m-%d %H:%M}"
            repeat = "" if reminder.repeat == "none" else f", repeats {reminder.repeat}"
            lines.append(f"- {reminder.text} — {when}{repeat}")
    lines.append("")

    lines.append("## Mail")
    try:
        messages = backend.list_messages(10)
    except Exception as exc:  # noqa: BLE001 - an unconfigured mailbox is reported, not hidden
        lines.append(f"Mail unavailable: {exc}")
    else:
        if not messages:
            lines.append("The inbox is empty.")
        else:
            seen = read_seen_mail_ids(state_path)
            new_count = (
                len(messages)
                if seen is None
                else sum(1 for message in messages if message.id not in seen)
            )
            lines.append(
                f"{len(messages)} recent message(s), {new_count} new since the last mail watch."
            )
            lines.append("Latest:")
            for message in messages[:3]:
                lines.append(f"- From {message.sender}: {message.subject}")
    lines.append("")

    lines.append("## Memory")
    entries = memory.list()
    if not entries:
        lines.append("Nothing remembered yet.")
    else:
        lines.append("Most recent entries:")
        for entry in entries[-5:]:
            lines.append(f"- [{entry.kind}] {entry.text}")
    lines.append("")
    return "\n".join(lines)
