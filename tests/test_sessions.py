"""Sessions: persistence and cross-session recall."""

from __future__ import annotations

from pathlib import Path

import pytest

from majordomo.sessions import SessionStore


@pytest.fixture()
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions")


def test_create_and_get(store: SessionStore) -> None:
    session = store.create("Greetings")
    loaded = store.get(session["id"])
    assert loaded is not None
    assert loaded["title"] == "Greetings"
    assert loaded["messages"] == []


def test_get_missing_returns_none(store: SessionStore) -> None:
    assert store.get("does-not-exist") is None


def test_append_persists(store: SessionStore) -> None:
    session = store.create()
    store.append(session["id"], {"role": "user", "content": "hello"})
    loaded = store.get(session["id"])
    assert loaded is not None
    assert loaded["messages"][0]["content"] == "hello"


def test_get_or_create_with_given_id(store: SessionStore) -> None:
    session = store.get_or_create("inbox")
    assert session["id"] == "inbox"
    assert store.get_or_create("inbox")["id"] == "inbox"


def test_list_sessions_counts_messages(store: SessionStore) -> None:
    session = store.create("One")
    store.append(session["id"], {"role": "user", "content": "hi"})
    summaries = store.list_sessions()
    assert len(summaries) == 1
    assert summaries[0]["message_count"] == 1


def test_search_finds_past_messages(store: SessionStore) -> None:
    first = store.create("Monday")
    store.append(first["id"], {"role": "user", "content": "We discussed the Lisbon trip budget"})
    second = store.create("Tuesday")
    store.append(second["id"], {"role": "user", "content": "Steel order arrives Friday"})
    hits = store.search("Lisbon trip")
    assert len(hits) == 1
    assert hits[0]["session_id"] == first["id"]
    assert "Lisbon" in hits[0]["snippet"]


def test_search_without_tokens_returns_empty(store: SessionStore) -> None:
    store.create("x")
    assert store.search("") == []
    assert store.search("a b") == []


def test_search_no_match(store: SessionStore) -> None:
    session = store.create("s")
    store.append(session["id"], {"role": "user", "content": "apples and oranges"})
    assert store.search("quantum physics") == []
