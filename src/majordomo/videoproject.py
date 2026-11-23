"""Video projects: a JSON scene spec, validated and rendered.

The pattern — a video described as data (scenes with durations) and
rendered programmatically, the idea behind tools like Remotion —
fitted to what Majordomo already has: no new runtime, no copied
code. A project is a small JSON document:

    {"title": "Launch teaser", "width": 1080, "height": 1920,
     "scenes": [
       {"kind": "text",  "text": "Hello", "duration": 3},
       {"kind": "image", "image": "cover.png", "duration": 4},
       {"kind": "audio", "audio": "voice.mp3", "text": "Caption", "duration": 5}
     ]}

Scene kinds: ``text`` (a title card), ``image`` (a still held for
its duration), ``audio`` (an audio file over a plain card, with an
optional caption in ``text`` and an optional backdrop ``image``).
Referenced files must live inside the workspace — the validator
rejects missing files and paths that escape it.

Rendering is done by the machine's **ffmpeg** (detected on PATH):
each scene becomes a segment (uniform size, frame rate, and audio
track — silent where a scene has no audio), and the segments are
concatenated into one MP4. Where ffmpeg is not installed the render
tool says so plainly and nothing is faked; the validator and the
spec still work everywhere. AI-generated scene media is a separate
step — the Muse4AI tools make images and videos; this module only
assembles a described project.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .tools import Tool, ToolError, ToolRegistry

SCENE_KINDS = ("text", "image", "audio")
_FPS = 30
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)

RunFn = Callable[..., subprocess.CompletedProcess[str]]


@dataclass
class Scene:
    kind: str
    duration: float
    text: str = ""
    image: str = ""
    audio: str = ""


@dataclass
class VideoProject:
    title: str = "Untitled"
    width: int = 1080
    height: int = 1920
    scenes: list[Scene] = field(default_factory=list)


def parse_project(data: Any) -> VideoProject:
    """Build a project from parsed JSON, or raise ValueError/TypeError saying why."""
    if not isinstance(data, dict):
        raise TypeError("A video project must be a JSON object.")
    raw_scenes = data.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ValueError("A video project needs a non-empty 'scenes' list.")
    scenes: list[Scene] = []
    for index, raw in enumerate(raw_scenes, start=1):
        if not isinstance(raw, dict):
            raise TypeError(f"Scene {index} must be an object.")
        kind = str(raw.get("kind", ""))
        if kind not in SCENE_KINDS:
            raise ValueError(
                f"Scene {index}: kind must be one of {', '.join(SCENE_KINDS)} (got {kind!r})."
            )
        try:
            duration = float(raw.get("duration", 0))
        except (TypeError, ValueError):
            raise ValueError(f"Scene {index}: duration must be a number.") from None
        if duration <= 0:
            raise ValueError(f"Scene {index}: duration must be greater than zero.")
        scene = Scene(
            kind=kind,
            duration=duration,
            text=str(raw.get("text", "")),
            image=str(raw.get("image", "")),
            audio=str(raw.get("audio", "")),
        )
        if kind == "text" and not scene.text:
            raise ValueError(f"Scene {index}: a text scene needs 'text'.")
        if kind == "image" and not scene.image:
            raise ValueError(f"Scene {index}: an image scene needs 'image'.")
        if kind == "audio" and not scene.audio:
            raise ValueError(f"Scene {index}: an audio scene needs 'audio'.")
        scenes.append(scene)
    try:
        width = int(data.get("width", 1080))
        height = int(data.get("height", 1920))
    except (TypeError, ValueError):
        raise ValueError("width and height must be integers.") from None
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be greater than zero.")
    return VideoProject(
        title=str(data.get("title", "Untitled")), width=width, height=height, scenes=scenes
    )


def project_from_json(text: str) -> VideoProject:
    """Parse a project from a JSON string."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Not valid JSON: {exc}") from exc
    return parse_project(data)


def total_duration(project: VideoProject) -> float:
    return sum(scene.duration for scene in project.scenes)


def _referenced_files(scene: Scene) -> list[str]:
    return [name for name in (scene.image, scene.audio) if name]


def validate_files(project: VideoProject, root: Path) -> list[str]:
    """Problems with the project's referenced files (empty = valid).

    Every referenced file must exist and resolve inside ``root`` —
    the same sandbox rule the file tools live by.
    """
    root = root.resolve()
    problems: list[str] = []
    for index, scene in enumerate(project.scenes, start=1):
        for name in _referenced_files(scene):
            candidate = (root / name).resolve()
            if not candidate.is_relative_to(root):
                problems.append(f"Scene {index}: {name} is outside the workspace.")
            elif not candidate.exists():
                problems.append(f"Scene {index}: {name} does not exist in the workspace.")
    return problems


def project_summary(project: VideoProject) -> str:
    lines = [
        (
            f"Video project {project.title!r}: {len(project.scenes)} scene(s), "
            f"{total_duration(project):g}s total, {project.width}x{project.height}"
        )
    ]
    for index, scene in enumerate(project.scenes, start=1):
        detail = scene.text or scene.image or scene.audio
        lines.append(f"  {index}. {scene.kind} — {scene.duration:g}s — {detail}")
    return "\n".join(lines)


def _escape_drawtext(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")


def _font_arg() -> str:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return f":fontfile={candidate}"
    return ""


def _segment_command(
    ffmpeg: str, project: VideoProject, scene: Scene, root: Path, segment: Path
) -> list[str]:
    width, height = project.width, project.height
    args = [ffmpeg, "-y"]
    # Video source.
    if scene.kind == "image" or (scene.kind == "audio" and scene.image):
        args += ["-loop", "1", "-i", str((root / scene.image).resolve())]
    else:
        args += ["-f", "lavfi", "-i", f"color=c=0x0B1D33:s={width}x{height}:r={_FPS}"]
    # Audio source.
    if scene.kind == "audio" and scene.audio:
        args += ["-i", str((root / scene.audio).resolve())]
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    filters = [
        f"scale={width}:{height}:force_original_aspect_ratio=decrease",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "setsar=1",
        f"fps={_FPS}",
    ]
    if scene.text:
        filters.append(
            "drawtext="
            f"text='{_escape_drawtext(scene.text)}'"
            f"{_font_arg()}"
            f":fontsize={max(16, width // 16)}:fontcolor=white"
            ":x=(w-text_w)/2:y=(h-text_h)/2"
        )
    args += [
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-t",
        f"{scene.duration:g}",
        "-vf",
        ",".join(filters),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        str(segment),
    ]
    return args


def render_project(
    project: VideoProject,
    root: Path,
    output: Path,
    *,
    ffmpeg_path: Any = ...,
    run_fn: RunFn | None = None,
) -> Path:
    """Render the project to ``output`` (an MP4) with ffmpeg.

    Raises :class:`ToolError` — honestly — when ffmpeg is missing,
    a referenced file is invalid, or a render step fails.
    """
    ffmpeg = shutil.which("ffmpeg") if ffmpeg_path is ... else ffmpeg_path
    if not ffmpeg:
        raise ToolError(
            "ffmpeg is not installed on this machine, so video projects cannot "
            "render here. The spec still validates; install ffmpeg to render."
        )
    problems = validate_files(project, root)
    if problems:
        raise ToolError("Cannot render: " + " ".join(problems))
    run = run_fn or subprocess.run
    root = root.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="majordomo-video-") as tmp:
        tmp_dir = Path(tmp)
        segments: list[Path] = []
        for index, scene in enumerate(project.scenes, start=1):
            segment = tmp_dir / f"segment-{index:03d}.mp4"
            completed = run(
                _segment_command(ffmpeg, project, scene, root, segment),
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0 or not segment.exists():
                tail = (completed.stderr or "").strip().splitlines()
                detail = tail[-1] if tail else "no error output"
                raise ToolError(f"ffmpeg failed on scene {index}: {detail}")
            segments.append(segment)
        listing = tmp_dir / "concat.txt"
        listing.write_text("".join(f"file '{segment}'\n" for segment in segments), encoding="utf-8")
        completed = run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c",
                "copy",
                str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0 or not output.exists():
            tail = (completed.stderr or "").strip().splitlines()
            detail = tail[-1] if tail else "no error output"
            raise ToolError(f"ffmpeg failed joining the scenes: {detail}")
    return output


def register_video_tools(registry: ToolRegistry, *, workspace_root: Path) -> None:
    """Add video_project_validate (read-only) and video_project_render (acting)."""

    def _parse(spec_json: str) -> VideoProject:
        try:
            return project_from_json(spec_json)
        except (ValueError, TypeError) as exc:
            raise ToolError(str(exc)) from exc

    def video_project_validate(spec_json: str) -> str:
        project = _parse(spec_json)
        problems = validate_files(project, workspace_root)
        summary = project_summary(project)
        if problems:
            return summary + "\nProblems: " + " ".join(problems)
        return summary + "\nAll referenced files check out."

    def video_project_render(spec_json: str, output: str = "video-project.mp4") -> str:
        project = _parse(spec_json)
        name = output.strip()
        if not name.endswith(".mp4"):
            raise ToolError("The output must be an .mp4 file name.")
        target = (workspace_root / name).resolve()
        if not target.is_relative_to(workspace_root.resolve()):
            raise ToolError("The output must stay inside the workspace.")
        rendered = render_project(project, workspace_root, target)
        size = rendered.stat().st_size
        return (
            f"Rendered {project.title!r}: {rendered.name} "
            f"({total_duration(project):g}s, {size} bytes) in the workspace."
        )

    registry.register(
        Tool(
            name="video_project_validate",
            description=(
                "Validate a video project spec (JSON: title, width, height, scenes "
                "of text/image/audio with durations) and check its referenced "
                "files exist in the workspace. Read-only."
            ),
            parameters={
                "type": "object",
                "properties": {"spec_json": {"type": "string"}},
                "required": ["spec_json"],
            },
            handler=video_project_validate,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="video_project_render",
            description=(
                "Render a validated video project spec to an MP4 in the workspace "
                "with the machine's ffmpeg (title cards, held images, audio "
                "scenes). Acting tool: needs approval."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "spec_json": {"type": "string"},
                    "output": {"type": "string"},
                },
                "required": ["spec_json"],
            },
            handler=video_project_render,
            read_only=False,
        )
    )
