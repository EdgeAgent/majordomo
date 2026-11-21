"""Image tools: the fake backend writes a real, valid PNG."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from majordomo.filetools import Workspace
from majordomo.imagetools import FakeImageBackend, register_image_tools
from majordomo.tools import ToolRegistry


def test_fake_backend_writes_valid_png(tmp_path: Path) -> None:
    out = tmp_path / "pic.png"
    FakeImageBackend().generate("a lighthouse", out)
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    # IHDR width/height are the first fields after the chunk header.
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (640, 360)


def test_generate_image_tool_lands_in_workspace(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "workspace")
    registry = ToolRegistry()
    register_image_tools(registry, workspace, FakeImageBackend(), backend_is_fake=True)
    result = registry.call("generate_image", {"prompt": "a robot butler", "filename": "bot.png"})
    assert "images/bot.png" in result
    assert "fake backend" in result
    assert (workspace.root / "images" / "bot.png").exists()


def test_openai_backend_without_key_is_honest(tmp_path: Path) -> None:
    from majordomo.imagetools import OpenAIImageBackend

    backend = OpenAIImageBackend(api_key=None)
    with pytest.raises(RuntimeError, match="No image API key"):
        backend.generate("x", tmp_path / "x.png")
