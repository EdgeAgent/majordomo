"""Company: a lightweight control plane over the teammates.

The pattern (a roster, a board, a budget — the shape popularised by
agent-company tools like Paperclip) fitted to Majordomo's house: the
teammates are the staff, and this module is the org chart and the
task board pinned to the wall next to them.

- The **roster** gives each teammate a role, a standing goal, and a
  budget cap (a number the owner sets; Majordomo reports it, it does
  not spend money itself, so the cap is a planning figure the summary
  shows next to the agent's run count).
- The **board** is the work queue: tasks with an owner and a status
  (``queued`` / ``running`` / ``done`` / ``blocked``). Adding a task
  to the board does **not** run anything — delegating work still goes
  through the acting ``delegate_task`` tool and its approval gate.
  There is deliberately no second executor here.
- The **summary** is the heartbeat read: roster + board counts + how
  many runs each character has actually done (from their transcripts).

Everything lives in one JSON file, ``company.json`` in the data
directory — plain data the owner owns, like the goals file.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from .teammates import AGENT_CLIS, run_count
from .tools import Tool, ToolError, ToolRegistry

log = structlog.get_logger(__name__)

TASK_STATUSES = ("queued", "running", "done", "blocked")


def _now() -> str:
    return datetime.now(UTC).isoformat()


class CompanyStore:
    """Roster + task board in one JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- storage ------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"agents": [], "tasks": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"agents": [], "tasks": []}
        if not isinstance(data, dict):
            return {"agents": [], "tasks": []}
        return {
            "agents": data.get("agents") if isinstance(data.get("agents"), list) else [],
            "tasks": data.get("tasks") if isinstance(data.get("tasks"), list) else [],
        }

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # -- roster -------------------------------------------------------

    def set_agent(
        self, name: str, role: str = "", goal: str = "", budget: float = 0.0
    ) -> dict[str, Any]:
        """Add or update one roster entry. Returns the entry."""
        name = name.strip()
        if not name:
            raise ToolError("An agent needs a name.")
        if budget < 0:
            raise ToolError("A budget cap cannot be negative.")
        data = self._load()
        for entry in data["agents"]:
            if str(entry.get("name", "")).lower() == name.lower():
                entry.update(
                    {"role": role, "goal": goal, "budget": float(budget), "updated_at": _now()}
                )
                self._save(data)
                return entry
        entry = {
            "name": name,
            "role": role,
            "goal": goal,
            "budget": float(budget),
            "created_at": _now(),
            "updated_at": _now(),
        }
        data["agents"].append(entry)
        self._save(data)
        return entry

    def agents(self) -> list[dict[str, Any]]:
        return list(self._load()["agents"])

    def get_agent(self, name: str) -> dict[str, Any] | None:
        key = name.strip().lower()
        for entry in self._load()["agents"]:
            if str(entry.get("name", "")).lower() == key:
                return entry
        return None

    # -- board --------------------------------------------------------

    def add_task(self, title: str, owner: str = "", notes: str = "") -> dict[str, Any]:
        """Queue one task on the board. Runs nothing — see module docs."""
        title = title.strip()
        if not title:
            raise ToolError("A task needs a title.")
        data = self._load()
        task = {
            "id": max((int(t.get("id", 0)) for t in data["tasks"]), default=0) + 1,
            "title": title,
            "owner": owner.strip(),
            "notes": notes,
            "status": "queued",
            "created_at": _now(),
            "updated_at": _now(),
        }
        data["tasks"].append(task)
        self._save(data)
        return task

    def tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        all_tasks = list(self._load()["tasks"])
        if status is None:
            return all_tasks
        return [t for t in all_tasks if t.get("status") == status]

    def set_task_status(self, task_id: int, status: str) -> dict[str, Any]:
        if status not in TASK_STATUSES:
            raise ToolError(
                f"Unknown task status {status!r}. Use one of: {', '.join(TASK_STATUSES)}."
            )
        data = self._load()
        for task in data["tasks"]:
            if int(task.get("id", 0)) == int(task_id):
                task["status"] = status
                task["updated_at"] = _now()
                self._save(data)
                return task
        raise ToolError(f"No task with id {task_id} on the board.")

    # -- summary ------------------------------------------------------

    def summary(self, teammates_dir: Path | None = None) -> str:
        """The heartbeat read: roster, run counts, board counts."""
        lines = ["Company — roster:"]
        agents = self.agents()
        if not agents:
            lines.append("  (nobody on the roster yet — company_set_agent adds someone)")
        for entry in agents:
            name = str(entry.get("name", "?"))
            line = f"  {name}"
            if entry.get("role"):
                line += f" — {entry['role']}"
            if entry.get("goal"):
                line += f" · goal: {entry['goal']}"
            if entry.get("budget"):
                line += f" · budget cap: {entry['budget']:g}"
            if teammates_dir is not None:
                spec = AGENT_CLIS.get(name.lower())
                if spec is not None:
                    line += f" · runs so far: {run_count(teammates_dir, spec)}"
            lines.append(line)
        counts = {status: len(self.tasks(status=status)) for status in TASK_STATUSES}
        lines.append(
            "Board: "
            + " · ".join(f"{status}: {counts[status]}" for status in TASK_STATUSES)
            + f" · total: {sum(counts.values())}"
        )
        return "\n".join(lines)

    def board_text(self) -> str:
        tasks = self.tasks()
        if not tasks:
            return "The board is empty — no tasks queued, running, or done."
        lines = []
        for task in tasks:
            owner = f" @{task['owner']}" if task.get("owner") else ""
            lines.append(f"#{task['id']} [{task['status']}] {task['title']}{owner}")
        return "\n".join(lines)


def register_company_tools(
    registry: ToolRegistry, store: CompanyStore, *, teammates_dir: Path
) -> None:
    """Add the company_* tools. Writes are acting; reads are free."""

    def company_summary() -> str:
        return store.summary(teammates_dir=teammates_dir)

    def company_board(status: str = "") -> str:
        if status:
            if status not in TASK_STATUSES:
                raise ToolError(
                    f"Unknown task status {status!r}. Use one of: {', '.join(TASK_STATUSES)}."
                )
            tasks = store.tasks(status=status)
            if not tasks:
                return f"No {status} tasks on the board."
            return "\n".join(
                f"#{t['id']} [{t['status']}] {t['title']}"
                + (f" @{t['owner']}" if t.get("owner") else "")
                for t in tasks
            )
        return store.board_text()

    def company_set_agent(name: str, role: str = "", goal: str = "", budget: float = 0.0) -> str:
        entry = store.set_agent(name, role=role, goal=goal, budget=budget)
        return (
            f"Roster updated: {entry['name']} — role: {entry['role'] or '(unset)'} · "
            f"goal: {entry['goal'] or '(unset)'} · budget cap: {entry['budget']:g}"
        )

    def company_add_task(title: str, owner: str = "", notes: str = "") -> str:
        task = store.add_task(title, owner=owner, notes=notes)
        return (
            f"Task #{task['id']} queued on the board: {task['title']} "
            "(queued only — delegating it still goes through delegate_task with approval)."
        )

    def company_set_task_status(task_id: int, status: str) -> str:
        task = store.set_task_status(task_id, status)
        return f"Task #{task['id']} is now {task['status']}: {task['title']}"

    registry.register(
        Tool(
            name="company_summary",
            description=(
                "The company heartbeat: the teammate roster (role, goal, budget cap, "
                "runs so far) and the task-board counts. Read-only."
            ),
            parameters={"type": "object", "properties": {}, "required": []},
            handler=company_summary,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="company_board",
            description="List the task board, optionally filtered by status. Read-only.",
            parameters={
                "type": "object",
                "properties": {"status": {"type": "string"}},
                "required": [],
            },
            handler=company_board,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="company_set_agent",
            description=(
                "Add or update a teammate on the company roster: name, role, standing "
                "goal, and a budget cap (a planning figure Majordomo reports, not "
                "money it spends). Acting tool: needs approval."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "goal": {"type": "string"},
                    "budget": {"type": "number"},
                },
                "required": ["name"],
            },
            handler=company_set_agent,
            read_only=False,
        )
    )
    registry.register(
        Tool(
            name="company_add_task",
            description=(
                "Queue a task on the company board (title, optional owner teammate). "
                "This only writes the board — it runs nothing; delegation still goes "
                "through delegate_task. Acting tool: needs approval."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "owner": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["title"],
            },
            handler=company_add_task,
            read_only=False,
        )
    )
    registry.register(
        Tool(
            name="company_set_task_status",
            description=(
                "Move a board task to queued, running, done, or blocked. "
                "Acting tool: needs approval."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "status": {"type": "string"},
                },
                "required": ["task_id", "status"],
            },
            handler=company_set_task_status,
            read_only=False,
        )
    )
