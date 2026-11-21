"""The ``majordomo`` command line.

    majordomo chat        interactive chat (acting tools ask first)
    majordomo ask "..."   one-shot question
    majordomo memory ...  inspect long-term memory
    majordomo schedule ...  manage reminders
    majordomo serve       the web app (chat page + API)
    majordomo demo        the scripted day on the fake provider
    majordomo version

Configuration comes from the environment / ``.env`` (see
``.env.example``); the interactive chat is the one place approvals are
asked per tool call.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import __version__
from .config import Settings
from .runtime import Runtime, build_runtime
from .tools import approve_all, approve_none

app = typer.Typer(help="Majordomo — your self-hosted personal AI agent.")
memory_app = typer.Typer(help="Inspect and edit long-term memory.")
schedule_app = typer.Typer(help="Manage reminders.")
app.add_typer(memory_app, name="memory")
app.add_typer(schedule_app, name="schedule")

console = Console()


def _runtime() -> Runtime:
    return build_runtime(Settings())


def _interactive_approver(name: str, arguments: dict) -> bool:
    return typer.confirm(f"Allow {name} with {arguments}?")


@app.command()
def version() -> None:
    """Print the Majordomo version."""
    console.print(f"majordomo {__version__}")


@app.command()
def demo() -> None:
    """Run the scripted demo day on the fake provider."""
    from .demo import run_demo

    console.print(run_demo(), markup=False)


@app.command()
def ask(
    question: str,
    approve: bool = typer.Option(False, "--approve", help="Approve acting tools for this one run."),
) -> None:
    """Ask one question and print the reply."""
    runtime = _runtime()
    try:
        result = runtime.agent.run(
            None, question, approver=approve_all if approve else approve_none
        )
        console.print(result.text, markup=False)
    finally:
        runtime.close()


@app.command()
def chat() -> None:
    """Chat interactively. Acting tools ask for approval, per call."""
    runtime = _runtime()
    session_id: str | None = None
    console.print("Majordomo — type 'exit' to stop. Acting tools will ask first.")
    try:
        while True:
            try:
                text = typer.prompt("you")
            except (EOFError, KeyboardInterrupt):
                break
            if text.strip().lower() in ("exit", "quit"):
                break
            result = runtime.agent.run(session_id, text, approver=_interactive_approver)
            session_id = result.session_id
            console.print(f"[bold]majordomo:[/bold] {escape(result.text)}")
    finally:
        runtime.close()


@app.command()
def serve(
    host: str = typer.Option("", help="Bind host (default from settings)."),
    port: int = typer.Option(0, help="Bind port (default from settings)."),
) -> None:
    """Serve the web app: chat page + API."""
    import uvicorn

    from .webapp import create_app

    settings = Settings()
    uvicorn.run(
        create_app(settings),
        host=host or settings.host,
        port=port or settings.port,
    )


@app.command("mcp-server")
def mcp_server(
    allow_write: bool = typer.Option(
        False,
        "--allow-write",
        help="Also expose acting tools (memory/file writes, documents, reminders).",
    ),
) -> None:
    """Run Majordomo as an MCP server on stdio (read-only by default)."""
    import os

    from .mcp_server import serve_stdio

    os.environ.pop("MAJORDOMO_MCP_CONFIG", None)  # a server never consumes servers
    runtime = _runtime()
    try:
        serve_stdio(runtime.registry, allow_write=allow_write)
    finally:
        runtime.close()


@memory_app.command("list")
def memory_list(kind: str = typer.Option("", help="fact, preference, or note.")) -> None:
    """List everything in long-term memory."""
    runtime = _runtime()
    try:
        entries = runtime.memory.list(kind or None)
        if not entries:
            console.print("(memory is empty)")
            return
        table = Table("ID", "Kind", "Text")
        for entry in entries:
            table.add_row(entry.id, entry.kind, entry.text)
        console.print(table)
    finally:
        runtime.close()


@memory_app.command("add")
def memory_add(kind: str, text: str) -> None:
    """Add one memory entry: majordomo memory add fact "..." """
    runtime = _runtime()
    try:
        entry = runtime.memory.remember(kind, text)
        console.print(f"Remembered as {entry.id}.")
    finally:
        runtime.close()


@memory_app.command("search")
def memory_search(query: str) -> None:
    """Search long-term memory."""
    runtime = _runtime()
    try:
        entries = runtime.memory.recall(query)
        if not entries:
            console.print("No matches.")
            return
        for entry in entries:
            console.print(f"{entry.id} [{entry.kind}] {entry.text}")
    finally:
        runtime.close()


@memory_app.command("forget")
def memory_forget(entry_id: str) -> None:
    """Delete one memory entry by id (e.g. fact:2)."""
    runtime = _runtime()
    try:
        gone = runtime.memory.forget(entry_id)
        console.print("Forgotten." if gone else f"No entry {entry_id}.")
    finally:
        runtime.close()


@schedule_app.command("add")
def schedule_add(
    text: str,
    in_minutes: int = typer.Option(60, "--in-minutes"),
    repeat: str = typer.Option("none", "--repeat"),
) -> None:
    """Add a reminder."""
    runtime = _runtime()
    try:
        due = datetime.now(UTC) + timedelta(minutes=in_minutes)
        reminder = runtime.schedules.add(text, due, repeat)
        console.print(f"Reminder {reminder.id} set for {reminder.due_at}.")
    finally:
        runtime.close()


@schedule_app.command("list")
def schedule_list() -> None:
    """List active reminders."""
    runtime = _runtime()
    try:
        reminders = runtime.schedules.list()
        if not reminders:
            console.print("No active reminders.")
            return
        table = Table("ID", "Due (UTC)", "Repeat", "Text")
        for reminder in reminders:
            table.add_row(reminder.id, reminder.due_at, reminder.repeat, reminder.text)
        console.print(table)
    finally:
        runtime.close()


@schedule_app.command("run-due")
def schedule_run_due() -> None:
    """Fire every reminder that is due now, printing each one."""
    runtime = _runtime()
    try:
        fired = runtime.schedules.fire_due(datetime.now(UTC))
        if not fired:
            console.print("Nothing due.")
            return
        for reminder in fired:
            console.print(f"⏰ {reminder.text}")
            runtime.sessions.append(
                "inbox",
                {
                    "role": "assistant",
                    "content": f"⏰ Reminder: {reminder.text}",
                },
            )
    finally:
        runtime.close()


@schedule_app.command("cancel")
def schedule_cancel(reminder_id: str) -> None:
    """Cancel a reminder by id."""
    runtime = _runtime()
    try:
        gone = runtime.schedules.cancel(reminder_id)
        console.print("Cancelled." if gone else f"No reminder {reminder_id}.")
    finally:
        runtime.close()


if __name__ == "__main__":
    app()
