"""Memory: plain files, explicit writes, honest recall."""

from __future__ import annotations

from pathlib import Path

import pytest

from majordomo.memory import MemoryStore


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "memory")


def test_files_are_created_with_headers(store: MemoryStore, tmp_path: Path) -> None:
    for name in ("facts.md", "preferences.md", "notes.md"):
        path = tmp_path / "memory" / name
        assert path.exists()
        assert "Majordomo memory" in path.read_text(encoding="utf-8")


def test_remember_and_list_roundtrip(store: MemoryStore) -> None:
    entry = store.remember("fact", "The shop is in London, Ontario")
    assert entry.id == "fact:1"
    entries = store.list("fact")
    assert [e.text for e in entries] == ["The shop is in London, Ontario"]


def test_kinds_are_separate(store: MemoryStore) -> None:
    store.remember("fact", "A fact")
    store.remember("preference", "A preference")
    assert len(store.list()) == 2
    assert [e.text for e in store.list("preference")] == ["A preference"]


def test_entries_survive_a_fresh_store(store: MemoryStore, tmp_path: Path) -> None:
    store.remember("note", "Persist me")
    fresh = MemoryStore(tmp_path / "memory")
    assert [e.text for e in fresh.list("note")] == ["Persist me"]


def test_recall_finds_token_overlap(store: MemoryStore) -> None:
    store.remember("preference", "Favourite coffee is a double espresso")
    store.remember("fact", "The dog is named Biscuit")
    hits = store.recall("what coffee do I like")
    assert len(hits) == 1
    assert "espresso" in hits[0].text


def test_recall_without_overlap_returns_nothing(store: MemoryStore) -> None:
    store.remember("fact", "The dog is named Biscuit")
    assert store.recall("quantum chromodynamics lecture") == []


def test_recall_empty_query_returns_recent(store: MemoryStore) -> None:
    store.remember("fact", "One")
    store.remember("fact", "Two")
    hits = store.recall("")
    assert [e.text for e in hits] == ["One", "Two"]


def test_forget_removes_and_renumbers(store: MemoryStore) -> None:
    store.remember("fact", "First")
    store.remember("fact", "Second")
    assert store.forget("fact:1") is True
    remaining = store.list("fact")
    assert [e.text for e in remaining] == ["Second"]
    assert remaining[0].id == "fact:1"


def test_forget_bad_ids(store: MemoryStore) -> None:
    assert store.forget("fact:9") is False
    assert store.forget("bogus:1") is False
    assert store.forget("fact:abc") is False


def test_remember_empty_text_raises(store: MemoryStore) -> None:
    with pytest.raises(ValueError):
        store.remember("fact", "   ")


def test_unknown_kind_raises(store: MemoryStore) -> None:
    with pytest.raises(ValueError, match="Unknown memory kind"):
        store.remember("secret", "nope")


def test_memory_file_is_human_editable(store: MemoryStore, tmp_path: Path) -> None:
    path = tmp_path / "memory" / "facts.md"
    path.write_text(path.read_text(encoding="utf-8") + "- Typed by hand\n", encoding="utf-8")
    assert "Typed by hand" in [e.text for e in store.list("fact")]
