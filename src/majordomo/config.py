"""Runtime settings.

Everything is configured through the environment (prefix ``MAJORDOMO_``)
or a local ``.env`` file. The defaults are local-first: data lives under
``~/.majordomo`` and the provider defaults to ``auto`` — the first
hosted key found wins, then a configured local Ollama, then the
``fake`` provider, which needs no server and no key and powers the
demo and the test suite.
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

    # Provider selection: "auto" (the default) uses the first hosted
    # key that is set — Anthropic, then OpenAI, DeepSeek, Gemini,
    # OpenRouter, Groq, Mistral, xAI, Together — then a configured
    # local Ollama, then the offline fake. Any preset name ("openai",
    # "anthropic", "deepseek", ...) pins that provider, as do "ollama"
    # and "fake". See providers.py for the preset registry.
    provider: str = "auto"
    # MAJORDOMO_MODEL overrides any preset's default model.
    model: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    # One key per hosted provider; set whichever you have. Keys are
    # never logged or printed — `majordomo providers` shows only
    # "key set" / "no key".
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    deepseek_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    groq_api_key: str | None = None
    mistral_api_key: str | None = None
    xai_api_key: str | None = None
    together_api_key: str | None = None

    # Optional MCP servers config (JSON file, see examples/mcp-servers.json).
    mcp_config: Path | None = None

    # Image generation backend: "fake" (placeholder PNG) or "openai".
    image_backend: str = "fake"

    # Mail tools: IMAP for reading, SMTP for sending, standard library
    # only. With a live provider and no mail settings, the mail tools
    # report "not configured" instead of pretending; the fake provider
    # pairs with a seeded fake mailbox (see mailtools.py).
    mail_address: str | None = None
    mail_username: str | None = None
    mail_password: str | None = None
    mail_imap_host: str | None = None
    mail_smtp_host: str | None = None
    mail_smtp_port: int = 587

    # Self-filing memory: when True, the agent files simple declarative
    # statements from the user's own messages ("my favourite coffee is
    # ...", "remember ...") into long-term memory after each turn. Off
    # by default — capture is the operator's choice, never a surprise.
    auto_memory: bool = False

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

    @property
    def initiative_path(self) -> Path:
        """The initiative engine's state: seen mail ids, fired reminders."""
        return self.data_dir / "initiative.json"

    def ensure_dirs(self) -> None:
        """Create the data tree on first run."""
        for path in (self.data_dir, self.workspace_dir, self.memory_dir, self.sessions_dir):
            path.mkdir(parents=True, exist_ok=True)
