"""Image generation behind an injectable backend.

The backend is a protocol: anything with ``generate(prompt, out_path)``.
The shipped fake writes a real PNG — a navy card with a gold frame, drawn
with the standard library — so demos and tests exercise the whole path
without a key. Live generation means wiring a provider backend with the
reader's own API key (an OpenAI-compatible backend ships here).
"""

from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path
from typing import Protocol

import httpx

from .filetools import Workspace
from .tools import Tool, ToolRegistry

# Edge Agency palette for the placeholder card.
_NAVY = (6, 10, 20)
_GOLD = (232, 184, 75)
_TEAL = (45, 212, 191)


def _png_bytes(width: int, height: int) -> bytes:
    """A valid PNG: navy field, gold frame, teal centre stripe."""

    def pixel(x: int, y: int) -> tuple[int, int, int]:
        if x < 6 or y < 6 or x >= width - 6 or y >= height - 6:
            return _GOLD
        if height // 2 - 10 <= y < height // 2 + 10:
            return _TEAL
        return _NAVY

    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: none
        for x in range(width):
            raw.extend(pixel(x, y))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw)))
        + chunk(b"IEND", b"")
    )


class ImageBackend(Protocol):
    """Anything that can turn a prompt into an image file."""

    def generate(self, prompt: str, out_path: Path) -> None: ...


class FakeImageBackend:
    """Writes a labelled placeholder PNG. It never pretends otherwise."""

    def generate(self, prompt: str, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_png_bytes(640, 360))


class OpenAIImageBackend:
    """Live generation via an OpenAI-compatible images endpoint.

    Needs the reader's own API key; nothing here ships one.
    """

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-image-1",
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        # Created lazily on the first live call, so constructing the
        # backend (or hitting the no-key error) never builds an HTTP
        # client it does not need.
        self._client = client

    def generate(self, prompt: str, out_path: Path) -> None:
        if not self.api_key:
            raise RuntimeError("No image API key configured (MAJORDOMO_OPENAI_API_KEY).")
        client = self._client or httpx.Client(timeout=180.0)
        response = client.post(
            f"{self.base_url}/images/generations",
            json={"model": self.model, "prompt": prompt, "size": "1024x1024"},
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        response.raise_for_status()
        data = response.json()
        encoded = (data.get("data") or [{}])[0].get("b64_json")
        if not encoded:
            raise RuntimeError("Image endpoint returned no image data.")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(base64.b64decode(encoded))


def register_image_tools(
    registry: ToolRegistry, workspace: Workspace, backend: ImageBackend, backend_is_fake: bool
) -> None:
    """Add generate_image."""

    def generate(prompt: str, filename: str = "image.png") -> str:
        path = workspace.resolve(f"images/{filename}")
        backend.generate(prompt, path)
        note = " (fake backend — placeholder art)" if backend_is_fake else ""
        return f"Generated image at images/{filename}{note}."

    registry.register(
        Tool(
            name="generate_image",
            description="Generate an image from a prompt into the workspace's images folder.",
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "filename": {"type": "string", "description": "Default image.png"},
                },
                "required": ["prompt"],
            },
            handler=generate,
        )
    )
