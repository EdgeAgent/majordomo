"""The ``majordomo`` command line.

    majordomo chat        interactive chat (acting tools ask first)
    majordomo ask "..."   one-shot question
    majordomo providers   every model provider, its key var, the active one
    majordomo agents      the teammate characters: who is installed
    majordomo team        the whole cast, chief of staff first
    majordomo notify      send one test notification to the webhook
    majordomo self        the self files: soul, identity, user, memory
    majordomo memory ...  inspect long-term memory
    majordomo schedule ...  manage reminders
    majordomo serve       the web app (the one window + API)
    majordomo daemon      always-on mode: fire due reminders forever
    majordomo brief       today's brief: reminders, mail, memory
    majordomo demo        the scripted day on the fake provider
    majordomo version

Configuration comes from the environment / ``.env`` (see
``.env.example``); the interactive chat is the one place approvals are
asked per tool call.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import __version__
from .config import Settings
from .notify import send_notification
from .providers import PROVIDER_PRESETS, ProviderError, resolve_model, resolve_provider_name
from .runtime import Runtime, build_runtime
from .self_files import SelfStore
from .teammates import AGENT_CLIS, detect_agents, run_count
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
def providers() -> None:
    """List every model provider, its key variable, and the active one.

    Bring any key you have: set one ``MAJORDOMO_*_API_KEY`` and the
    matching provider becomes active (``MAJORDOMO_PROVIDER=auto``,
    the default). Keys themselves are never printed — only whether
    one is set.
    """
    settings = Settings()
    try:
        active = resolve_provider_name(settings)
    except ProviderError as exc:
        console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc
    table = Table("Provider", "Key variable", "Default model", "Status")
    for preset in PROVIDER_PRESETS.values():
        if preset.key_field:
            status = "key set" if getattr(settings, preset.key_field) else "no key"
        elif preset.name == "ollama":
            status = "local, no key"
        else:
            status = "built in"
        if preset.name == active:
            status += " · ◀ active"
        table.add_row(preset.name, preset.key_env or "—", preset.default_model, status)
    console.print(table)
    console.print(
        f"Active: {active} (model {resolve_model(settings, active)}). "
        "MAJORDOMO_PROVIDER pins a provider; MAJORDOMO_MODEL overrides the model.",
        markup=False,
    )


@app.command("self")
def self_command() -> None:
    """Show the self files — soul, identity, user, curated memory.

    Lists each file's status and prints SOUL.md: the persona the
    agent assembles into its system prompt on every turn. The files
    live at the top of the data directory and are seeded from the
    shipped templates on first run; editing one changes who answers.
    There are no secrets in these files, by design.
    """
    store = SelfStore(Settings().data_dir)
    table = Table("File", "Status", "Size")
    for entry in store.status():
        table.add_row(
            entry.name,
            "present" if entry.present else "missing",
            f"{entry.size} B" if entry.present else "—",
        )
    console.print(table)
    soul = store.read("SOUL.md")
    if soul is None:
        console.print("SOUL.md is missing — no persona is loaded.", markup=False)
    else:
        console.print("\nSOUL.md:\n", markup=False)
        console.print(soul, markup=False)


@app.command()
def agents() -> None:
    """List the teammate characters and who is installed.

    Teammates are the coding-agent CLIs on this machine — Claude
    Code, Codex, Gemini CLI, OpenCode, Cursor, Copilot, Aider — each
    a named character Majordomo can delegate coding tasks to with the
    acting ``delegate_task`` tool. Detection is a PATH lookup only;
    nothing is launched. Runs counts come from each character's
    transcript in the data directory.
    """
    settings = Settings()
    table = Table("Character", "Role", "Agent CLI", "Status", "Runs")
    for status in detect_agents():
        spec = status.spec
        runs = run_count(settings.teammates_dir, spec)
        table.add_row(
            f"{spec.initial} · {spec.display_name}",
            spec.role,
            spec.binary + (" (experimental)" if spec.experimental else ""),
            status.path if status.available else "not installed",
            str(runs),
        )
    console.print(table)
    if not settings.teammates:
        console.print(
            "Teammates are switched off (MAJORDOMO_TEAMMATES=off) — "
            "the delegate_task tool is not registered.",
            markup=False,
        )


@app.command()
def team() -> None:
    """Print the whole cast: Domo, chief of staff, and his teammates."""
    console.print(
        "[bold]Majordomo (Domo)[/bold] — chief of staff. He remembers, schedules, "
        "researches, asks before acting — and delegates the coding."
    )
    table = Table("Character", "Who they are", "Runs on")
    detected = {status.spec.key: status for status in detect_agents()}
    for spec in AGENT_CLIS.values():
        status = detected[spec.key]
        runs_on = spec.binary + ("" if status.available else " (not installed here)")
        table.add_row(spec.display_name, spec.role, runs_on)
    console.print(table)
    console.print(
        "Teammates run under their own logins and subscriptions — "
        "Majordomo never sees their credentials.",
        markup=False,
    )


@app.command()
def notify(title: str, body: str) -> None:
    """Send one notification to the configured webhook.

    Uses ``MAJORDOMO_NOTIFY_WEBHOOK``. The exit code is honest: 1
    when no webhook is configured or the send fails, 0 when the
    receiver answered 2xx.
    """
    settings = Settings()
    if not settings.notify_webhook:
        console.print(
            "MAJORDOMO_NOTIFY_WEBHOOK is not set — notifications are off.",
            markup=False,
        )
        raise typer.Exit(code=1)
    if send_notification(title, body, settings.notify_webhook):
        console.print("Notification sent.", markup=False)
    else:
        console.print("Notification failed — the webhook did not accept it.", markup=False)
        raise typer.Exit(code=1)


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
    """Serve the web app: the one window + API."""
    import uvicorn

    from .webapp import create_app

    settings = Settings()
    uvicorn.run(
        create_app(settings),
        host=host or settings.host,
        port=port or settings.port,
    )


@app.command()
def daemon(
    interval: int = typer.Option(30, "--interval", help="Seconds between scheduler ticks."),
    once: bool = typer.Option(False, "--once", help="Run one tick and exit."),
) -> None:
    """Run always-on: fire due reminders into the inbox, forever.

    Each tick is the web app's background loop without the web app:
    fire everything due, print it, and drop it into the ``inbox``
    session — then the initiative engine takes its turn (mail watch
    and reminder escalation; see docs/always-on.md). Run it as a
    service and reminders and new mail land even when no window is
    open.
    """
    runtime = _runtime()
    try:
        while True:
            now = datetime.now(UTC)
            fired = runtime.schedules.fire_due(now)
            for reminder in fired:
                console.print(f"⏰ {reminder.text}")
                runtime.sessions.append(
                    "inbox",
                    {
                        "role": "assistant",
                        "content": f"⏰ Reminder: {reminder.text}",
                    },
                )
            for line in runtime.initiative.tick(now, fired):
                console.print(line, markup=False)
            if once:
                if not fired:
                    console.print("Nothing due.")
                break
            time.sleep(interval)
    finally:
        runtime.close()


@app.command()
def brief() -> None:
    """Print today's brief — reminders, mail, memory — and save it.

    Assembled from real state by a deterministic template (no model):
    active reminders with overdue ones called out, the new-mail count
    and latest subjects, and the most recent memory entries. Saved to
    the workspace as ``brief-YYYY-MM-DD.md``.
    """
    from .brief import build_brief

    runtime = _runtime()
    try:
        now = datetime.now(UTC)
        text = build_brief(
            schedules=runtime.schedules,
            backend=runtime.mail_backend,
            memory=runtime.memory,
            state_path=runtime.settings.initiative_path,
            now=now,
        )
        runtime.workspace.write(f"brief-{now:%Y-%m-%d}.md", text)
        console.print(text, markup=False)
    finally:
        runtime.close()


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
