"""Runtime settings.

Everything is configured through the environment (prefix ``MAJORDOMO_``)
or a local ``.env`` file. The defaults are local-first: data lives under
``~/.majordomo`` and the default provider is a local Ollama server. The
``fake`` provider needs no server and no key — it powers the demo and
the test suite.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Majordomo settings, loaded from MAJORDOMO_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="MAJORDOMO_", env_file=".env", extra="ignore")

    # Where state lives. Memory, sessions, schedules, and the workspace
    # all sit under data_dir so one folder is the whole agent's life.
    data_dir: Path = Path.home() / ".majordomo"

    # Provider selection: "ollama" (local, default), "openai"
    # (OpenAI-compatible chat completions), or "fake" (scripted, offline).
    provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None

    # Optional MCP servers config (JSON file, see examples/mcp-servers.json).
    mcp_config: Path | None = None

    # Image generation backend: "fake" (placeholder PNG) or "openai".
    image_backend: str = "fake"

    # Web app bind for `majordomo serve`.
    host: str = "127.0.0.1"
    port: int = 8080

    @property
    def workspace_dir(self) -> Path:
        """The sandboxed workspace the file and document tools may touch."""
        return self.data_dir / "workspace"

    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memory"

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def schedules_path(self) -> Path:
        return self.data_dir / "schedules.json"

    def ensure_dirs(self) -> None:
        """Create the data tree on first run."""
        for path in (self.data_dir, self.workspace_dir, self.memory_dir, self.sessions_dir):
            path.mkdir(parents=True, exist_ok=True)
