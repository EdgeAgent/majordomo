"""The scripted demo day.

``majordomo demo`` runs the fake provider through one small day, in a
throwaway data directory, with every backend faked: a research ask, a
Word brief, a reminder set and fired, and a memory saved in one session
and recalled in a brand-new one. It prints a readable transcript and
changes nothing outside its temp folder.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import Settings
from .providers import FakeProvider
from .runtime import build_runtime
from .tools import approve_all


def run_demo() -> str:
    """Run the scripted day and return the transcript.

    Agent log lines are redirected to stderr for the duration (and the
    previous logging configuration restored afterwards), so the
    transcript on stdout stays clean.
    """
    import sys

    import structlog

    previous = structlog.get_config()
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))
    try:
        return _run_demo()
    finally:
        structlog.configure(**previous)


def _run_demo() -> str:
    lines: list[str] = []
    data_dir = Path(tempfile.mkdtemp(prefix="majordomo-demo-"))
    settings = Settings(data_dir=data_dir, provider="fake")
    runtime = build_runtime(settings, provider=FakeProvider(), offline=True)

    def ask(session_id: str | None, text: str) -> str:
        lines.append(f"\n>>> {text}")
        result = runtime.agent.run(session_id, text, approver=approve_all)
        for event in result.events:
            if event.kind in ("tool_call", "declined"):
                lines.append(f"    [{event.kind}] {event.text}")
        lines.append(f"Majordomo: {result.text}")
        return result.session_id

    lines.append("=== Majordomo demo — a scripted day on the fake provider ===")
    lines.append("(Every backend is a fake: no network, no keys, nothing leaves this machine.)")

    session = ask(None, "Search the web for small business AI adoption")
    ask(session, "Fetch https://example.com/ai-adoption and tell me what it says")
    ask(session, "Create a Word brief called Pilot Brief about the findings")
    ask(session, "Remind me in 0 minutes to review the brief")

    fired = runtime.schedules.fire_due(datetime.now(UTC) + timedelta(minutes=1))
    lines.append("\n--- the scheduler ticks ---")
    for reminder in fired:
        lines.append(f"Reminder fired: {reminder.text} (was due {reminder.due_at})")

    session = ask(session, "Remember that my favourite coffee is a double espresso")
    lines.append("\n--- a brand-new session: does it remember? ---")
    ask(None, "What do you remember about my coffee?")

    lines.append("\n=== Demo done. Workspace files: ===")
    for entry in runtime.workspace.list("."):
        lines.append(f"  {entry}")
    lines.append(f"(Demo data lived in {data_dir} and can be deleted.)")
    runtime.close()
    return "\n".join(lines)


def main() -> None:
    print(run_demo())


if __name__ == "__main__":
    main()
