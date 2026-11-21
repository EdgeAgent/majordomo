"""Teammates: the coding-agent CLIs on this machine, as characters.

Majordomo is the chief of staff; he is not the only pair of hands in
the house. Machines that run Majordomo often also have one or more
*coding-agent CLIs* installed — Claude Code, Codex, Gemini CLI,
OpenCode, Cursor, Copilot, Aider. Each one is already logged in under
its owner's own subscription. This module turns those CLIs into
**teammates**: named characters with a role, whom Majordomo can hand a
task to through their documented non-interactive mode.

The bridge is deliberately simple and honest:

- Detection is ``shutil.which`` on the PATH — nothing is probed,
  launched, or logged into at detection time.
- A run is one subprocess: the CLI's non-interactive invocation with
  the task as a single argument (never ``shell=True``), the sandboxed
  workspace as its working directory, and a hard timeout
  (``MAJORDOMO_TEAMMATE_TIMEOUT``, default 600 seconds; the process is
  killed when it expires). Stdout and stderr are captured and the
  tail (last ~8,000 characters) is what comes back.
- The agents run under *their own* logins and subscriptions.
  Majordomo never sees, stores, or passes their credentials — it just
  starts the program the owner already installed.
- ``delegate_task`` is an **acting** tool: it runs an external program
  that can change files, so it passes the approval gate like every
  other acting tool. A declined delegation runs nothing.

Each character keeps a small home in the data directory,
``teammates/<slug>/``: a ``character.json`` card (name, agent, role,
created date), a ``transcript.jsonl`` with one JSON line per run
(timestamp, agent, task, exit code, output), and a ``notes.md`` the
character's runs append a one-line outcome summary to — the
character's own memory of what it has done here.

The characters also have faces. Kevin supplied a cast portrait of
the team (``assets/friends-cast.jpg`` in the repository); each mapped
character's crop lives at ``assets/faces/<slug>.png`` and is recorded
on the spec as ``avatar`` (and on the character card). Domo's own
face from the portrait is :data:`DOMO_AVATAR` — his canonical head
elsewhere (the web window's Roboto head) is a separate asset and is
not touched by this. Copilot and Aider are not in the portrait, so
they keep their initial avatars (``avatar=None``) until their faces
arrive. The terminal roster stays text; the faces are for the
repository and future surfaces.

Registration rule: the ``delegate_task`` tool is registered when
teammates are enabled (``MAJORDOMO_TEAMMATES``, default on) **and**
at least one known CLI is detected on the PATH — or when teammates
were explicitly switched on in the settings, in which case the tool
exists and reports "not installed" cleanly for missing binaries.
``MAJORDOMO_TEAMMATES=off`` removes the tool entirely.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog

from .tools import Tool, ToolError, ToolRegistry

log = structlog.get_logger(__name__)

_MAX_OUTPUT_CHARS = 8_000
_TASK_PLACEHOLDER = "{task}"

WhichFn = Callable[[str], str | None]
RunFn = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class AgentCLI:
    """One known coding-agent CLI, as a character.

    ``argv`` is the non-interactive invocation template; the literal
    ``{task}`` element is replaced by the task text (as one argument —
    never through a shell). ``experimental`` marks entries whose
    non-interactive flags are less certain; they work the same way
    but are labelled honestly in the docs and the roster. ``avatar``
    is the character's face — a repository-relative path under
    ``assets/faces/``, cropped from the cast portrait — or ``None``
    for characters who have no face yet and keep their initial.
    """

    key: str  # the name the model and the CLI use ("claude", "cursor")
    display_name: str  # the character's name ("Claude", "Otto")
    role: str  # one line: who this character is
    binary: str  # the executable looked up on PATH
    argv: tuple[str, ...]  # invocation template after the binary
    initial: str  # avatar initial
    colour: str  # avatar colour (Majordomo's navy / gold / teal world)
    avatar: str | None = None  # face file under assets/faces/, if the character has one
    experimental: bool = False

    @property
    def slug(self) -> str:
        return self.key

    def build_argv(self, binary_path: str, task: str) -> list[str]:
        return [binary_path, *[task if part == _TASK_PLACEHOLDER else part for part in self.argv]]


# Domo's own face from the cast portrait. (His canonical head — the
# Roboto head the web window serves — is a separate asset; this crop
# is only his portrait face, for the repository and future surfaces.)
DOMO_AVATAR = "assets/faces/domo.png"

# The cast, in roster order. Domo himself is not in this table — he is
# the chief of staff who delegates; these are the hands he delegates to.
AGENT_CLIS: dict[str, AgentCLI] = {
    spec.key: spec
    for spec in (
        AgentCLI(
            key="claude",
            display_name="Claude",
            role="the senior engineer",
            binary="claude",
            argv=("-p", _TASK_PLACEHOLDER),
            initial="C",
            colour="#E8B84B",
            avatar="assets/faces/claude.png",
        ),
        AgentCLI(
            key="codex",
            display_name="Codex",
            role="the fast prototyper",
            binary="codex",
            argv=("exec", _TASK_PLACEHOLDER),
            initial="X",
            colour="#2DD4BF",
            avatar="assets/faces/codex.png",
        ),
        AgentCLI(
            key="gemini",
            display_name="Gemini",
            role="the researcher",
            binary="gemini",
            argv=("-p", _TASK_PLACEHOLDER),
            initial="G",
            colour="#5EEAD4",
            avatar="assets/faces/gemini.png",
        ),
        AgentCLI(
            key="opencode",
            display_name="Otto",
            role="the open-source all-rounder",
            binary="opencode",
            argv=("run", _TASK_PLACEHOLDER),
            initial="O",
            colour="#F5D67B",
            avatar="assets/faces/otto.png",
        ),
        AgentCLI(
            key="cursor",
            display_name="Cursor",
            role="the editor",
            binary="cursor-agent",
            argv=("-p", _TASK_PLACEHOLDER),
            initial="U",
            colour="#94A3B8",
            avatar="assets/faces/cursor.png",
        ),
        AgentCLI(
            key="copilot",
            display_name="Copilot",
            role="the pair programmer",
            binary="copilot",
            argv=("-p", _TASK_PLACEHOLDER),
            initial="P",
            colour="#0EA5A4",
        ),
        AgentCLI(
            key="aider",
            display_name="Aider",
            role="the focused patcher",
            binary="aider",
            argv=("--message", _TASK_PLACEHOLDER, "--yes-always"),
            initial="A",
            colour="#C9A227",
            experimental=True,
        ),
    )
}


@dataclass
class AgentStatus:
    """One character plus what detection found on this machine."""

    spec: AgentCLI
    path: str | None

    @property
    def available(self) -> bool:
        return self.path is not None


def detect_agents(which: WhichFn | None = None) -> list[AgentStatus]:
    """Detect every known agent CLI on the PATH. Never launches one."""
    which = which or shutil.which
    return [AgentStatus(spec=spec, path=which(spec.binary)) for spec in AGENT_CLIS.values()]


def _resolve(name: str, which: WhichFn | None) -> tuple[AgentCLI, str]:
    """(spec, binary path) for a name, or a clean ToolError.

    Names resolve by registry key ("opencode") or by the character's
    display name ("Otto") — the owner talks about characters, not
    binaries.
    """
    key = name.strip().lower()
    spec = AGENT_CLIS.get(key)
    if spec is None:
        spec = next(
            (item for item in AGENT_CLIS.values() if item.display_name.lower() == key), None
        )
    if spec is None:
        known = ", ".join(sorted(AGENT_CLIS))
        raise ToolError(f"Unknown teammate {name!r}. Known teammates: {known}.")
    which = which or shutil.which
    path = which(spec.binary)
    if path is None:
        raise ToolError(
            f"{spec.display_name} ({spec.binary}) is not installed on this machine — "
            f"`majordomo agents` shows who is available."
        )
    return spec, path


@dataclass
class TeammateResult:
    """The outcome of one delegated run."""

    spec: AgentCLI
    task: str
    exit_code: int | None  # None when the run timed out
    output: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.exit_code == 0

    def outcome_line(self) -> str:
        """The one-line summary appended to the character's notes."""
        if self.timed_out:
            return "timed out"
        return "done" if self.exit_code == 0 else f"failed (exit {self.exit_code})"

    def report(self, timeout: int) -> str:
        """The text the model (and the transcript reader) sees."""
        header = f"{self.spec.display_name} ({self.spec.key}) — {self.outcome_line()}"
        if self.timed_out:
            header = (
                f"{self.spec.display_name} ({self.spec.key}) — timed out after "
                f"{timeout}s and was stopped"
            )
        body = self.output.strip() or "(no output)"
        return f"{header}\n\n{body}"


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _combine(stdout: str, stderr: str) -> str:
    parts = [part for part in (stdout.strip(),) if part]
    if stderr.strip():
        parts.append(f"[stderr]\n{stderr.strip()}")
    combined = "\n".join(parts)
    if len(combined) > _MAX_OUTPUT_CHARS:
        combined = "[… earlier output truncated …]\n" + combined[-_MAX_OUTPUT_CHARS:]
    return combined


def character_dir(teammates_dir: Path, spec: AgentCLI) -> Path:
    return teammates_dir / spec.slug


def ensure_character(teammates_dir: Path, spec: AgentCLI, now: datetime | None = None) -> Path:
    """Create the character's home (card + notes) on first use.

    The card is written once and never overwritten — like the self
    files, it is the character's identity on this machine.
    """
    home = character_dir(teammates_dir, spec)
    home.mkdir(parents=True, exist_ok=True)
    card_path = home / "character.json"
    if not card_path.exists():
        card = {
            "name": spec.display_name,
            "agent": spec.key,
            "binary": spec.binary,
            "role": spec.role,
            "avatar": spec.avatar,
            "created": (now or datetime.now(UTC)).date().isoformat(),
        }
        card_path.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    notes_path = home / "notes.md"
    if not notes_path.exists():
        notes_path.write_text(
            f"# {spec.display_name} — notes\n\n"
            f"{spec.display_name} is {spec.role}. One line per delegated run, "
            "appended by Majordomo.\n\n",
            encoding="utf-8",
        )
    return home


def run_count(teammates_dir: Path, spec: AgentCLI) -> int:
    """How many runs the character's transcript holds (0 if none yet)."""
    transcript = character_dir(teammates_dir, spec) / "transcript.jsonl"
    try:
        return sum(
            1 for line in transcript.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    except OSError:
        return 0


def _record(teammates_dir: Path, result: TeammateResult, when: datetime) -> None:
    """Append the transcript entry and the one-line note for a run."""
    home = ensure_character(teammates_dir, result.spec, now=when)
    entry = {
        "timestamp": when.isoformat(),
        "agent": result.spec.key,
        "task": result.task,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "output": result.output,
    }
    with (home / "transcript.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    task_one_line = " ".join(result.task.split())[:80]
    with (home / "notes.md").open("a", encoding="utf-8") as handle:
        handle.write(f"- {when:%Y-%m-%d %H:%M} — {task_one_line} → {result.outcome_line()}\n")


def run_teammate(
    name: str,
    task: str,
    *,
    cwd: Path,
    timeout: int,
    teammates_dir: Path,
    which: WhichFn | None = None,
    run_fn: RunFn | None = None,
    now: datetime | None = None,
) -> TeammateResult:
    """Run one teammate on one task and record the run.

    Raises :class:`ToolError` for an unknown name or a binary that is
    not installed — clean errors, never a crash. The subprocess runs
    with the task as a single argument (no shell), in ``cwd``, and is
    killed when ``timeout`` seconds expire.
    """
    spec, binary_path = _resolve(name, which)
    run = run_fn or subprocess.run
    argv = spec.build_argv(binary_path, task)
    cwd.mkdir(parents=True, exist_ok=True)
    timed_out = False
    exit_code: int | None
    try:
        completed = run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        exit_code = completed.returncode
        output = _combine(_as_text(completed.stdout), _as_text(completed.stderr))
    except OSError as exc:
        # Detected a moment ago, gone (or unlaunchable) now: a clean
        # error for the model, not a crash.
        raise ToolError(f"Could not start {spec.binary}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        # subprocess.run has already killed the process at this point.
        timed_out = True
        exit_code = None
        output = _combine(_as_text(exc.stdout), _as_text(exc.stderr))
    result = TeammateResult(
        spec=spec, task=task, exit_code=exit_code, output=output, timed_out=timed_out
    )
    _record(teammates_dir, result, now or datetime.now(UTC))
    log.info(
        "teammate.run",
        agent=spec.key,
        exit_code=exit_code,
        timed_out=timed_out,
    )
    return result


def register_teammate_tools(
    registry: ToolRegistry,
    *,
    workspace_root: Path,
    teammates_dir: Path,
    timeout: int,
    which: WhichFn | None = None,
) -> None:
    """Add the acting ``delegate_task`` tool.

    The handler runs the named teammate in the sandboxed workspace.
    Approval is the agent loop's business — this tool is registered
    with ``read_only=False``, so a run without approval executes
    nothing at all.
    """

    def delegate_task(agent: str, task: str) -> str:
        result = run_teammate(
            agent,
            task,
            cwd=workspace_root,
            timeout=timeout,
            teammates_dir=teammates_dir,
            which=which,
        )
        return result.report(timeout)

    cast = ", ".join(
        f"{spec.key} ({spec.display_name}, {spec.role})" for spec in AGENT_CLIS.values()
    )
    registry.register(
        Tool(
            name="delegate_task",
            description=(
                "Hand a coding task to a teammate — a coding-agent CLI installed on "
                f"this machine ({cast}). The teammate runs in the workspace under its "
                "own login and returns its output. Acting tool: needs approval."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Teammate name, e.g. 'claude'"},
                    "task": {"type": "string", "description": "The task, in plain words"},
                },
                "required": ["agent", "task"],
            },
            handler=delegate_task,
            read_only=False,
        )
    )
