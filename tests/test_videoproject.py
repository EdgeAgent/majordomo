"""Video projects: a JSON scene spec, validated, rendered with ffmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from majordomo.tools import ToolError
from majordomo.videoproject import (
    parse_project,
    project_from_json,
    render_project,
    total_duration,
    validate_files,
)

SPEC = {
    "title": "Demo",
    "width": 320,
    "height": 240,
    "scenes": [
        {"kind": "text", "text": "Hello", "duration": 0.6},
        {"kind": "image", "image": "pic.png", "duration": 0.6},
    ],
}


def test_parse_and_total_duration() -> None:
    project = parse_project(SPEC)
    assert project.title == "Demo"
    assert total_duration(project) == pytest.approx(1.2)


def test_parse_rejects_bad_specs() -> None:
    with pytest.raises(ValueError):
        parse_project({"scenes": []})
    with pytest.raises(ValueError):
        parse_project({"scenes": [{"kind": "text", "duration": 1}]})
    with pytest.raises(ValueError):
        parse_project({"scenes": [{"kind": "image", "image": "x.png", "duration": 0}]})
    with pytest.raises(ValueError):
        project_from_json("not json")


def test_validate_files_flags_missing_and_escaping(tmp_path: Path) -> None:
    (tmp_path / "pic.png").write_bytes(b"x")
    project = parse_project(SPEC)
    assert validate_files(project, tmp_path) == []
    bad = parse_project({"scenes": [{"kind": "image", "image": "../secret.png", "duration": 1}]})
    problems = validate_files(bad, tmp_path)
    assert problems and "secret.png" in problems[0]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_render_produces_real_mp4(tmp_path: Path) -> None:
    # A 1x1 red PNG as the image scene's source.
    import base64

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    (tmp_path / "pic.png").write_bytes(png)
    project = parse_project(SPEC)
    out = render_project(project, tmp_path, tmp_path / "out.mp4")
    assert out.exists() and out.stat().st_size > 1000
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", str(out)],
        capture_output=True,
        text=True,
        check=True,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    assert duration == pytest.approx(1.2, abs=0.35)


def test_render_without_ffmpeg_is_honest(tmp_path: Path) -> None:
    project = parse_project({"scenes": [{"kind": "text", "text": "Hi", "duration": 1}]})
    with pytest.raises(ToolError, match="ffmpeg"):
        render_project(project, tmp_path, tmp_path / "out.mp4", ffmpeg_path=None)
