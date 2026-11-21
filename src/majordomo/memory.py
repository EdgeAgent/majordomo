"""Long-term memory: plain files on disk.

Memory is one Markdown file per kind — ``facts.md``, ``preferences.md``,
``notes.md`` — inside the data directory. Every entry is a bullet line,
so the user can open the files in any editor, read exactly what the
agent remembers, fix it, or delete it. There is no database and no
hidden state: what is in the files is what the agent knows.

Automatic capture is OFF by default. Entries are written when the agent
calls the ``memory_remember`` tool or the user runs ``majordomo memory
add`` — plus, only when the operator opts in with
``MAJORDOMO_AUTO_MEMORY``, the narrow self-filing extractor in
``autocapture.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

KINDS = ("fact", "preference", "note")
_FILES = {"fact": "facts.md", "preference": "preferences.md", "note": "notes.md"}
_HEADERS = {
    "fact": "# Majordomo memory — facts\n\nThings Majordomo remembers. One bullet per entry; edit freely.\n",
    "preference": "# Majordomo memory — preferences\n\nHow the user likes things done. One bullet per entry; edit freely.\n",
    "note": "# Majordomo memory — notes\n\nFree-form notes. One bullet per entry; edit freely.\n",
}


@dataclass
class MemoryEntry:
    """One remembered line."""

    id: str  # e.g. "fact:2" — kind plus 1-based position in its file
    kind: str
    text: str


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


class MemoryStore:
    """Read and write the memory Markdown files."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        for kind, filename in _FILES.items():
            path = self.root / filename
            if not path.exists():
                path.write_text(_HEADERS[kind], encoding="utf-8")

    def _path(self, kind: str) -> Path:
        if kind not in _FILES:
            raise ValueError(f"Unknown memory kind {kind!r}; use one of {', '.join(KINDS)}.")
        return self.root / _FILES[kind]

    def _read_entries(self, kind: str) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        for line in self._path(kind).read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                entries.append(
                    MemoryEntry(
                        id=f"{kind}:{len(entries) + 1}", kind=kind, text=stripped[2:].strip()
                    )
                )
        return entries

    def _write_entries(self, kind: str, texts: list[str]) -> None:
        body = _HEADERS[kind] + "\n" + "".join(f"- {text}\n" for text in texts)
        self._path(kind).write_text(body, encoding="utf-8")

    def remember(self, kind: str, text: str) -> MemoryEntry:
        """Append one entry and return it (with its new id)."""
        clean = " ".join(text.split())
        if not clean:
            raise ValueError("Nothing to remember — the text was empty.")
        entries = self._read_entries(kind)
        entries.append(MemoryEntry(id=f"{kind}:{len(entries) + 1}", kind=kind, text=clean))
        self._write_entries(kind, [e.text for e in entries])
        return entries[-1]

    def list(self, kind: str | None = None) -> list[MemoryEntry]:
        """All entries, or only one kind's."""
        kinds = [kind] if kind else list(KINDS)
        result: list[MemoryEntry] = []
        for item in kinds:
            result.extend(self._read_entries(item))
        return result

    def recall(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Score entries by token overlap with the query, best first.

        An empty query returns the most recent entries. Entries with no
        overlap are dropped — recall never invents a match.
        """
        entries = self.list()
        query_tokens = _tokens(query)
        if not query_tokens:
            return entries[-limit:]
        scored: list[tuple[int, int, MemoryEntry]] = []
        for position, entry in enumerate(entries):
            overlap = len(query_tokens & _tokens(entry.text))
            if overlap:
                scored.append((overlap, position, entry))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [entry for _, _, entry in scored[:limit]]

    def forget(self, entry_id: str) -> bool:
        """Delete one entry by id (``kind:position``). True if removed."""
        kind, _, raw_index = entry_id.partition(":")
        if kind not in _FILES:
            return False
        try:
            index = int(raw_index)
        except ValueError:
            return False
        entries = self._read_entries(kind)
        if not 1 <= index <= len(entries):
            return False
        del entries[index - 1]
        self._write_entries(kind, [e.text for e in entries])
        return True
