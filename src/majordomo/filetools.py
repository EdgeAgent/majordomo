"""Sandboxed workspace files.

The agent may list, read, and write files — but only inside one
workspace directory. Every path is resolved against the workspace root
and checked for containment *after* resolution, so ``..`` segments,
absolute paths, and symlink tricks cannot escape. The tests try to
break out; this module is why they fail.
"""

from __future__ import annotations

from pathlib import Path

from .tools import Tool, ToolRegistry

_MAX_READ_CHARS = 20_000


class Workspace:
    """A directory the agent is allowed to touch, and nothing outside it."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative: str) -> Path:
        """Resolve a workspace-relative path, refusing any escape."""
        root = self.root.resolve()
        candidate = (root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError(f"Path {relative!r} escapes the workspace.")
        return candidate

    def list(self, relative: str = ".") -> list[str]:
        """Entry names under a workspace path, directories suffixed '/'."""
        path = self.resolve(relative)
        if not path.exists():
            raise ValueError(f"No such path in the workspace: {relative!r}.")
        if path.is_file():
            return [path.name]
        return sorted(entry.name + ("/" if entry.is_dir() else "") for entry in path.iterdir())

    def read(self, relative: str) -> str:
        path = self.resolve(relative)
        if not path.is_file():
            raise ValueError(f"Not a file in the workspace: {relative!r}.")
        return path.read_text(encoding="utf-8", errors="replace")[:_MAX_READ_CHARS]

    def write(self, relative: str, content: str) -> Path:
        path = self.resolve(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


def register_file_tools(registry: ToolRegistry, workspace: Workspace) -> None:
    """Add workspace_list / workspace_read / workspace_write."""

    def list_files(path: str = ".") -> str:
        entries = workspace.list(path)
        return "\n".join(entries) if entries else "(empty)"

    def read_file(path: str) -> str:
        return workspace.read(path)

    def write_file(path: str, content: str) -> str:
        written = workspace.write(path, content)
        return f"Wrote {len(content)} characters to {written.name}."

    registry.register(
        Tool(
            name="workspace_list",
            description="List files and folders inside the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path, default '.'"}
                },
                "required": [],
            },
            handler=list_files,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="workspace_read",
            description="Read a text file from the workspace.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=read_file,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="workspace_write",
            description="Write a text file into the workspace (overwrites).",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
            handler=write_file,
            read_only=False,
        )
    )
