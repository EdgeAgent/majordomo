"""Step runner: a multi-step plan, executed one teammate run at a time.

The pattern (plan → execute stepwise → journal → stop on failure)
comes from autonomous coding agents like OpenHands; the machinery is
Majordomo's own teammates bridge, reused — each step is one ordinary
:func:`majordomo.teammates.run_teammate` call, with the same rules:
the task as a single argument, never ``shell=True``, the sandboxed
workspace as the working directory, the same per-run timeout
(``MAJORDOMO_TEAMMATE_TIMEOUT``).

A run writes a **journal** — one JSON file per plan in the data
directory's ``runs/`` folder — recording every step's text, exit
code, and output, plus the run's final status (``done``, ``failed``,
or ``timed_out``). The runner stops at the first step that fails or
times out; later steps are never started, and the journal says so by
their absence. ``run_task_steps`` is an acting tool: the whole plan
passes the approval gate once, like any other acting tool.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog

from .teammates import RunFn, TeammateResult, WhichFn, run_teammate
from .tools import Tool, ToolRegistry

log = structlog.get_logger(__name__)

_STEP_PREFIX = re.compile(r"^(?:step\s+\d+\s*[:.)-]\s*|\d+\s*[.)]\s*|[-*•]\s*)", re.IGNORECASE)


def parse_steps(raw: str) -> list[str]:
    """Parse a plain-text plan into steps.

    One step per line; leading numbering (``1.``, ``2)``), bullets
    (``-``, ``*``), and ``Step 3:`` prefixes are stripped; blank
    lines are ignored.
    """
    steps = []
    for line in raw.splitlines():
        text = _STEP_PREFIX.sub("", line.strip()).strip()
        if text:
            steps.append(text)
    return steps


@dataclass
class StepResult:
    """One step of a run: its text and the teammate run it produced."""

    step: str
    result: TeammateResult


@dataclass
class StepRun:
    """A whole plan run: per-step results, final status, journal path."""

    agent: str
    results: list[StepResult] = field(default_factory=list)
    status: str = "done"  # done | failed | timed_out
    journal_path: Path | None = None

    def report(self, timeout: int) -> str:
        lines = [f"Step run for {self.agent}: {self.status} ({len(self.results)} step(s) run)"]
        for index, item in enumerate(self.results, start=1):
            lines.append(f"{index}. {item.step} → {item.result.outcome_line()}")
        if self.journal_path is not None:
            lines.append(f"Journal: {self.journal_path}")
        return "\n".join(lines)


def _journal_id(journal_dir: Path, when: datetime) -> str:
    base = when.strftime("run-%Y%m%d-%H%M%S")
    candidate = base
    counter = 2
    while (journal_dir / f"{candidate}.json").exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def run_steps(
    agent: str,
    steps: list[str],
    *,
    cwd: Path,
    timeout: int,
    teammates_dir: Path,
    journal_dir: Path,
    which: WhichFn | None = None,
    run_fn: RunFn | None = None,
    now: datetime | None = None,
) -> StepRun:
    """Run ``steps`` in order through one teammate; stop on failure.

    Raises :class:`majordomo.tools.ToolError` (via the teammates
    bridge) for an unknown agent or a missing binary — before any
    step runs, so a bad plan leaves no half-journal.
    """
    when = now or datetime.now(UTC)
    journal_dir.mkdir(parents=True, exist_ok=True)
    run = StepRun(agent=agent)
    journal: dict = {
        "id": _journal_id(journal_dir, when),
        "agent": agent,
        "started_at": when.isoformat(),
        "status": "running",
        "steps": [],
    }
    journal_path = journal_dir / f"{journal['id']}.json"
    run.journal_path = journal_path

    def flush() -> None:
        journal_path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")

    flush()
    for step in steps:
        result = run_teammate(
            agent,
            step,
            cwd=cwd,
            timeout=timeout,
            teammates_dir=teammates_dir,
            which=which,
            run_fn=run_fn,
            now=when,
        )
        run.results.append(StepResult(step=step, result=result))
        journal["steps"].append(
            {
                "n": len(run.results),
                "step": step,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "output": result.output,
            }
        )
        if result.timed_out:
            run.status = "timed_out"
            break
        if not result.ok:
            run.status = "failed"
            break
        flush()
    journal["status"] = run.status
    journal["finished_at"] = datetime.now(UTC).isoformat()
    flush()
    log.info("steprun.finished", agent=agent, status=run.status, steps=len(run.results))
    return run


def register_step_tools(
    registry: ToolRegistry,
    *,
    workspace_root: Path,
    teammates_dir: Path,
    journal_dir: Path,
    timeout: int,
    which: WhichFn | None = None,
) -> None:
    """Add the acting ``run_task_steps`` tool."""

    def run_task_steps(agent: str, steps: list[str]) -> str:
        cleaned = [str(step).strip() for step in steps if str(step).strip()]
        if not cleaned:
            return "No steps given — nothing ran."
        run = run_steps(
            agent,
            cleaned,
            cwd=workspace_root,
            timeout=timeout,
            teammates_dir=teammates_dir,
            journal_dir=journal_dir,
            which=which,
        )
        return run.report(timeout)

    registry.register(
        Tool(
            name="run_task_steps",
            description=(
                "Run a multi-step plan through one teammate (a coding-agent CLI on "
                "this machine): steps run in order, each as its own delegated run in "
                "the workspace, stopping at the first failure; a journal of every "
                "step is kept. Acting tool: needs approval."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Teammate name, e.g. 'claude'"},
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The plan's steps, in order",
                    },
                },
                "required": ["agent", "steps"],
            },
            handler=run_task_steps,
            read_only=False,
        )
    )
