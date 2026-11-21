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


# --- v0.6: the one window, goals, the files shelf, and brand statics ---


_STATIC = Path(__file__).parent.parent / "src" / "majordomo" / "static"


def test_index_is_the_one_window(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    page = response.text
    # The chat window: composer wired to the real /chat API, session "window".
    assert 'id="composer"' in page
    assert "/chat" in page
    assert "'window'" in page
    assert 'id="approve"' in page
    # The four read buttons.
    for name in ("ideas", "feed", "goal", "artifact"):
        assert f'data-read="{name}"' in page
    # The fingerprint, the living head, the steps, and the agent dots.
    assert 'id="fingerprint"' in page
    assert "/brand/roboto-head.png" in page
    for step in ("Plan", "Build", "Write", "Check", "Done"):
        assert step in page
    for agent in ("Domo", "Mail", "Memory", "Brief", "Gate"):
        assert agent in page
    # His status lines ride the bubble.
    assert "Watching for mail" in page
    assert "Asking before acting" in page


def test_goals_crud_round_trip(client: TestClient) -> None:
    assert client.get("/goals").json() == []

    created = client.post("/goals", json={"text": "Ship v0.6", "next_move": "Run the tests"})
    assert created.status_code == 201
    goal = created.json()
    assert goal["id"] == 1
    assert goal["text"] == "Ship v0.6"
    assert goal["next_move"] == "Run the tests"
    assert goal["done"] is False

    moved = client.post("/goals/1/next-move", json={"next_move": "Write the changelog"})
    assert moved.status_code == 200
    assert moved.json()["next_move"] == "Write the changelog"

    done = client.post("/goals/1/done", json={"done": True})
    assert done.json()["done"] is True

    listed = client.get("/goals").json()
    assert len(listed) == 1
    assert listed[0]["next_move"] == "Write the changelog"

    assert client.delete("/goals/1").status_code == 200
    assert client.get("/goals").json() == []
    assert client.delete("/goals/1").status_code == 404
    assert client.post("/goals/99/done", json={"done": True}).status_code == 404
    assert client.post("/goals", json={"text": "  "}).status_code == 400


def test_goals_persist_across_restarts(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", provider="fake")
    with TestClient(create_app(settings, provider=FakeProvider())) as first:
        first.post("/goals", json={"text": "Survive a restart", "next_move": "Reload the app"})
    with TestClient(create_app(settings, provider=FakeProvider())) as second:
        goals = second.get("/goals").json()
    assert len(goals) == 1
    assert goals[0]["text"] == "Survive a restart"
    assert goals[0]["next_move"] == "Reload the app"


def test_files_list_and_download(client: TestClient, tmp_path: Path) -> None:
    workspace = tmp_path / "data" / "workspace"
    (workspace / "notes").mkdir(parents=True, exist_ok=True)
    (workspace / "brief.md").write_text("# Brief\n", encoding="utf-8")
    (workspace / "notes" / "list.json").write_text("{}", encoding="utf-8")

    listed = client.get("/files")
    assert listed.status_code == 200
    by_name = {entry["name"]: entry for entry in listed.json()}
    assert set(by_name) == {"brief.md", "notes/list.json"}
    assert by_name["brief.md"]["size"] == len("# Brief\n")
    assert by_name["brief.md"]["modified"]

    downloaded = client.get("/files/brief.md")
    assert downloaded.status_code == 200
    assert downloaded.text == "# Brief\n"
    assert "text/markdown" in downloaded.headers["content-type"]

    nested = client.get("/files/notes/list.json")
    assert nested.status_code == 200
    assert nested.json() == {}

    assert client.get("/files/missing.txt").status_code == 404


def test_files_traversal_is_refused(client: TestClient, tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("not yours", encoding="utf-8")
    for attempt in ("../secret.txt", "..%2Fsecret.txt", "notes/../../secret.txt"):
        response = client.get(f"/files/{attempt}")
        assert response.status_code == 404, attempt
        assert "not yours" not in response.text


def test_brand_head_serves_the_exact_bytes(client: TestClient) -> None:
    response = client.get("/brand/roboto-head.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == (_STATIC / "roboto-head.png").read_bytes()


def test_brand_files_and_404s(client: TestClient) -> None:
    assert client.get("/brand/icon.jpg").headers["content-type"] == "image/jpeg"
    assert client.get("/brand/banner.jpg").headers["content-type"] == "image/jpeg"
    assert client.get("/brand/window.gif").headers["content-type"] == "image/gif"
    assert client.get("/brand/fingerprint.svg").headers["content-type"].startswith("image/svg")
    assert client.get("/brand/nope.png").status_code == 404
    assert client.get("/brand/../webapp.py").status_code == 404


def test_self_data_matches_the_self_files(client: TestClient) -> None:
    response = client.get("/self-data")
    assert response.status_code == 200
    sections = response.json()
    assert [s["title"] for s in sections] == ["Soul", "Identity", "User", "Memory"]
    assert all(s["text"] for s in sections)
    # The standalone /self page still works.
    assert client.get("/self").status_code == 200
