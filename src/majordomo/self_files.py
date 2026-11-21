"""The self files: who Majordomo is, who he serves, what he curates.

Four plain Markdown files live at the top of the data directory:

- ``SOUL.md`` — the persona: voice, character, how he behaves.
- ``IDENTITY.md`` — name, character line, vibe, and his mark (a gold
  fingerprint: no two households alike).
- ``USER.md`` — the owner: name, timezone, what they care about.
- ``MEMORY.md`` — the curated long-term memory, distilled above the
  per-kind entry files in ``memory/`` (see memory.py).

On first run each file is seeded from the template shipped in
``templates/`` beside this module; seeding never overwrites an
existing file, so the owner's edits are the agent's character from
then on. The agent assembles its system prompt from these files on
every turn (see :meth:`SelfStore.system_prompt`), ahead of the
conversation — edit a file and the next turn is a slightly different
Majordomo. Like the memory files, there is no database and no hidden
state: what is in the files is who he is.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SELF_FILES = ("SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md")

# Each file's contribution to the system prompt is capped so a
# runaway edit cannot crowd the conversation out of the context.
MAX_PROMPT_CHARS = 6000

_TEMPLATES = Path(__file__).parent / "templates"

_INTRO = (
    "# Your self files\n\n"
    "The files below are who you are and who you serve. They are plain "
    "files your owner can read and edit; treat them as standing "
    "instructions that shape every reply, under the rules of the house "
    "above."
)


@dataclass
class SelfFile:
    """One self file's status on disk."""

    name: str
    path: Path
    present: bool
    size: int  # bytes; 0 when missing


class SelfStore:
    """Seed, read, and assemble the self files in the data directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.seed()

    def seed(self) -> list[str]:
        """Create any missing self file from its template.

        Returns the names created. Existing files are never touched —
        the owner's edits win over the shipped template, always.
        """
        created: list[str] = []
        for name in SELF_FILES:
            path = self.root / name
            if path.exists():
                continue
            template = _TEMPLATES / name
            if not template.exists():
                continue
            path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
            created.append(name)
        return created

    def _path(self, name: str) -> Path:
        if name not in SELF_FILES:
            raise ValueError(f"Unknown self file {name!r}; use one of {', '.join(SELF_FILES)}.")
        return self.root / name

    def status(self) -> list[SelfFile]:
        """Every self file's presence and size, checked on disk now."""
        result: list[SelfFile] = []
        for name in SELF_FILES:
            path = self.root / name
            present = path.exists()
            result.append(
                SelfFile(
                    name=name,
                    path=path,
                    present=present,
                    size=path.stat().st_size if present else 0,
                )
            )
        return result

    def read(self, name: str) -> str | None:
        """One self file's content, or None when it is missing."""
        path = self._path(name)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def system_prompt(self, base: str) -> str:
        """Assemble the agent's system prompt: base rules, then self.

        Each present, non-empty self file becomes one section under
        its filename, capped at ``MAX_PROMPT_CHARS``. Missing files
        are skipped gracefully — a deleted SOUL.md thins the prompt,
        it never breaks a turn.
        """
        sections = [base.rstrip(), _INTRO]
        for name in SELF_FILES:
            text = self.read(name)
            if text is None or not text.strip():
                continue
            text = text.strip()
            if len(text) > MAX_PROMPT_CHARS:
                text = text[:MAX_PROMPT_CHARS].rstrip() + "\n\n[… truncated for the prompt …]"
            sections.append(f"## {name}\n\n{text}")
        return "\n\n".join(sections)
