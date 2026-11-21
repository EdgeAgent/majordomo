"""The web app: page, health, and a full /chat round trip on the fake."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from majordomo.config import Settings
from majordomo.providers import FakeProvider
from majordomo.webapp import create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:  # type: ignore[misc]
    settings = Settings(data_dir=tmp_path / "data", provider="fake")
    app = create_app(settings, provider=FakeProvider())
    with TestClient(app) as test_client:
        yield test_client  # type: ignore[misc]


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["provider"] == "fake"


def test_index_page_is_the_chat_ui(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "MAJORDOMO" in response.text
    assert "/chat" in response.text


def test_chat_round_trip_remember_and_recall(client: TestClient) -> None:
    first = client.post(
        "/chat",
        json={
            "message": "Remember that my favourite coffee is a double espresso",
            "approve": True,
        },
    )
    assert first.status_code == 200
    body = first.json()
    assert body["session_id"]
    assert "memory_remember" in body["reply"] or "Remembered" in body["reply"]

    memory = client.get("/memory")
    assert memory.status_code == 200
    entries = memory.json()
    assert any("espresso" in e["text"] for e in entries)

    second = client.post(
        "/chat",
        json={
            "message": "What do you remember about my coffee?",
            "session_id": body["session_id"],
        },
    )
    assert "espresso" in second.json()["reply"]


def test_chat_acting_tool_declined_without_approve(client: TestClient) -> None:
    response = client.post(
        "/chat",
        json={
            "message": "Remember that the sky is blue",
            "approve": False,
        },
    )
    body = response.json()
    kinds = [e["kind"] for e in body["events"]]
    assert "declined" in kinds
    assert client.get("/memory").json() == []


def test_sessions_endpoint_lists_the_chat(client: TestClient) -> None:
    client.post("/chat", json={"message": "hello there", "approve": True})
    sessions = client.get("/sessions")
    assert sessions.status_code == 200
    assert len(sessions.json()) >= 1
