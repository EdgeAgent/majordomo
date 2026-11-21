"""The self files: seeding, prompt assembly, the CLI, and /self."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from majordomo.agent import Agent
from majordomo.cli import app
from majordomo.config import Settings
from majordomo.providers import FakeProvider, ProviderResponse
from majordomo.runtime import Runtime
from majordomo.self_files import SELF_FILES, SelfStore
from majordomo.sessions import SessionStore
from majordomo.tools import ToolRegistry, approve_none
from majordomo.webapp import create_app

runner = CliRunner()


def test_first_run_seeds_all_four_files(tmp_path: Path) -> None:
    store = SelfStore(tmp_path / "data")
    for name in SELF_FILES:
        assert (tmp_path / "data" / name).exists(), name
    soul = store.read("SOUL.md")
    assert soul is not None and "Ask before acting" in soul
    identity = store.read("IDENTITY.md")
    assert identity is not None and "Majordomo" in identity and "fingerprint" in identity
    memory = store.read("MEMORY.md")
    assert memory is not None
    for heading in ("## Facts", "## People", "## Preferences", "## Commitments"):
        assert heading in memory


def test_seeding_never_overwrites_edits(tmp_path: Path) -> None:
    root = tmp_path / "data"
    SelfStore(root)
    (root / "SOUL.md").write_text("# My own soul\n", encoding="utf-8")
    again = SelfStore(root)
    assert again.read("SOUL.md") == "# My own soul\n"
    assert again.seed() == []  # nothing left to create


def test_status_reports_present_size_and_missing(tmp_path: Path) -> None:
    store = SelfStore(tmp_path / "data")
    by_name = {entry.name: entry for entry in store.status()}
    for name in SELF_FILES:
        assert by_name[name].present
        assert by_name[name].size > 0
    (tmp_path / "data" / "USER.md").unlink()
    by_name = {entry.name: entry for entry in store.status()}
    assert not by_name["USER.md"].present
    assert by_name["USER.md"].size == 0
    assert store.read("USER.md") is None


def test_system_prompt_includes_soul_identity_user_and_memory(runtime: Runtime) -> None:
    prompt = runtime.agent.system_prompt()
    assert "Rules of the house" in prompt  # the base prompt still leads
    assert "Ask before acting" in prompt  # SOUL.md
    assert "Domo" in prompt  # IDENTITY.md
    assert "## Commitments" in prompt  # MEMORY.md
    assert prompt.index("Rules of the house") < prompt.index("## SOUL.md")


def test_system_prompt_picks_up_memory_edits(runtime: Runtime, settings: Settings) -> None:
    memory_path = settings.data_dir / "MEMORY.md"
    memory_path.write_text(
        memory_path.read_text(encoding="utf-8") + "\n- The owner keeps bees.\n",
        encoding="utf-8",
    )
    assert "The owner keeps bees." in runtime.agent.system_prompt()


def test_system_prompt_skips_missing_files(runtime: Runtime, settings: Settings) -> None:
    (settings.data_dir / "USER.md").unlink()
    prompt = runtime.agent.system_prompt()
    assert "## USER.md" not in prompt
    assert "## SOUL.md" in prompt


def test_system_prompt_caps_a_runaway_file(runtime: Runtime, settings: Settings) -> None:
    (settings.data_dir / "SOUL.md").write_text("x" * 50_000, encoding="utf-8")
    prompt = runtime.agent.system_prompt()
    assert "truncated for the prompt" in prompt
    assert len(prompt) < 40_000


class _RecordingProvider:
    """A provider that captures the messages it was given."""

    name = "recording"

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def chat(self, messages: list[dict[str, Any]], tools: list[Any]) -> ProviderResponse:
        self.messages = messages
        return ProviderResponse(text="At your service.")


def test_agent_sends_the_assembled_prompt_to_the_provider(tmp_path: Path) -> None:
    provider = _RecordingProvider()
    agent = Agent(
        provider=provider,  # type: ignore[arg-type]
        registry=ToolRegistry(),
        sessions=SessionStore(tmp_path / "sessions"),
        self_store=SelfStore(tmp_path / "data"),
    )
    result = agent.run(None, "Good morning", approver=approve_none)
    assert result.text == "At your service."
    system = provider.messages[0]
    assert system["role"] == "system"
    assert "Ask before acting" in system["content"]  # SOUL.md reached the model
    assert "## MEMORY.md" in system["content"]


def test_agent_without_a_self_store_uses_the_base_prompt(tmp_path: Path) -> None:
    agent = Agent(
        provider=FakeProvider(),
        registry=ToolRegistry(),
        sessions=SessionStore(tmp_path / "sessions"),
    )
    assert "Your self files" not in agent.system_prompt()


def test_self_cli_lists_files_and_prints_the_soul(tmp_path: Path) -> None:
    env = {"MAJORDOMO_DATA_DIR": str(tmp_path / "data"), "MAJORDOMO_PROVIDER": "fake"}
    result = runner.invoke(app, ["self"], env=env)
    assert result.exit_code == 0
    for name in SELF_FILES:
        assert name in result.stdout
    assert "present" in result.stdout
    assert "Ask before acting" in result.stdout  # SOUL.md content


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:  # type: ignore[misc]
    settings = Settings(data_dir=tmp_path / "data", provider="fake")
    app_ = create_app(settings, provider=FakeProvider())
    with TestClient(app_) as test_client:
        yield test_client  # type: ignore[misc]


def test_self_page_shows_soul_identity_user_and_memory(client: TestClient) -> None:
    response = client.get("/self")
    assert response.status_code == 200
    for heading in ("Soul", "Identity", "User", "Memory"):
        assert heading in response.text
    assert "MEMORY.md" in response.text
    assert "## Commitments" in response.text  # the curated memory skeleton
    assert "fingerprint" in response.text.lower()


def test_index_links_to_the_self_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "/self" in response.text
