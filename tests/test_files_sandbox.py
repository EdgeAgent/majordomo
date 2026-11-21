"""The workspace sandbox: the escapes must all fail."""

from __future__ import annotations

from pathlib import Path

import pytest

from majordomo.filetools import Workspace


@pytest.fixture()
def workspace(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "workspace")


def test_write_read_list_roundtrip(workspace: Workspace) -> None:
    workspace.write("notes/today.md", "hello world")
    assert workspace.read("notes/today.md") == "hello world"
    assert workspace.list(".") == ["notes/"]
    assert workspace.list("notes") == ["today.md"]


def test_dotdot_escape_refused(workspace: Workspace) -> None:
    with pytest.raises(ValueError, match="escapes the workspace"):
        workspace.resolve("../evil.txt")


def test_absolute_path_escape_refused(workspace: Workspace) -> None:
    with pytest.raises(ValueError, match="escapes the workspace"):
        workspace.resolve("/etc/passwd")


def test_nested_dotdot_escape_refused(workspace: Workspace) -> None:
    with pytest.raises(ValueError, match="escapes the workspace"):
        workspace.write("a/../../evil.txt", "nope")


def test_symlink_escape_refused(workspace: Workspace, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = workspace.root / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes the workspace"):
        workspace.write("link/evil.txt", "nope")
    assert not (outside / "evil.txt").exists()


def test_read_missing_file_errors(workspace: Workspace) -> None:
    with pytest.raises(ValueError, match="Not a file"):
        workspace.read("missing.txt")


def test_list_missing_path_errors(workspace: Workspace) -> None:
    with pytest.raises(ValueError, match="No such path"):
        workspace.list("missing")


def test_workspace_root_itself_is_allowed(workspace: Workspace) -> None:
    assert workspace.resolve(".") == workspace.root.resolve()
