"""Runtime assembly: settings in, a ready agent out.

The CLI, the web app, and the demo all build their agent here, so the
tool set is identical everywhere. Backends follow the provider choice:
the ``fake`` provider pairs with fake web/image backends (offline,
deterministic); any other provider gets the live httpx backends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .agent import Agent
from .config import Settings
from .coretools import register_memory_tools
from .doctoolkit import register_document_tools
from .filetools import Workspace, register_file_tools
from .imagetools import FakeImageBackend, OpenAIImageBackend, register_image_tools
from .initiative import InitiativeEngine
from .mailtools import MailBackend, build_mail_backend, register_mail_tools
from .mcp_client import MCPClient, load_mcp_config, register_mcp_tools
from .media import build_media_client, register_media_tools
from .memory import MemoryStore
from .notify import Notifier
from .providers import Provider, build_provider
from .scheduler import ScheduleStore, register_schedule_tools
from .self_files import SelfStore
from .sessions import SessionStore
from .teammates import AgentStatus, detect_agents, register_teammate_tools
from .tools import ToolRegistry
from .webtools import (
    DuckDuckGoSearchBackend,
    FakeHttpClient,
    FakeSearchBackend,
    HttpxHttpClient,
    register_web_tools,
)

# Canned pages for the fake HTTP client (demo and offline runs).
FAKE_PAGES = {
    "https://example.com/ai-adoption": (
        "<html><head><title>Small Business AI Adoption</title></head><body>"
        "<h1>Small Business AI Adoption</h1>"
        "<p>(fake page) A canned stand-in for a research result: small firms adopt AI "
        "first for inbox triage, quoting, and follow-up, and they buy help that runs "
        "the tools for them. Connect a live provider for real research.</p>"
        "</body></html>"
    ),
}


@dataclass
class Runtime:
    """Everything one Majordomo process needs, wired together."""

    settings: Settings
    provider: Provider
    registry: ToolRegistry
    agent: Agent
    memory: MemoryStore
    sessions: SessionStore
    schedules: ScheduleStore
    workspace: Workspace
    mail_backend: MailBackend
    initiative: InitiativeEngine
    self_store: SelfStore
    notifier: Notifier
    teammates: list[AgentStatus] = field(default_factory=list)
    mcp_clients: list[MCPClient] = field(default_factory=list)

    def close(self) -> None:
        for client in self.mcp_clients:
            client.close()


def build_runtime(
    settings: Settings, provider: Provider | None = None, offline: bool | None = None
) -> Runtime:
    """Wire stores, tools, MCP servers, and the agent from settings."""
    settings.ensure_dirs()
    provider = provider or build_provider(settings)
    is_offline = offline if offline is not None else provider.name == "fake"

    self_store = SelfStore(settings.data_dir)
    memory = MemoryStore(settings.memory_dir)
    sessions = SessionStore(settings.sessions_dir)
    schedules = ScheduleStore(settings.schedules_path)
    workspace = Workspace(settings.workspace_dir)

    registry = ToolRegistry()
    register_memory_tools(registry, memory, sessions)
    register_file_tools(registry, workspace)
    register_document_tools(registry, workspace)
    if is_offline:
        register_web_tools(registry, FakeHttpClient(FAKE_PAGES), FakeSearchBackend())
        image_backend: FakeImageBackend | OpenAIImageBackend = FakeImageBackend()
        image_is_fake = True
    else:
        register_web_tools(registry, HttpxHttpClient(), DuckDuckGoSearchBackend())
        if settings.image_backend == "openai":
            image_backend = OpenAIImageBackend(api_key=settings.openai_api_key)
            image_is_fake = False
        else:
            image_backend = FakeImageBackend()
            image_is_fake = True
    register_image_tools(registry, workspace, image_backend, image_is_fake)
    mail_backend = build_mail_backend(settings, is_offline)
    register_mail_tools(registry, mail_backend, workspace)
    register_schedule_tools(registry, schedules, lambda: datetime.now(UTC))

    # Media tools: generation is delegated to a locally running
    # Muse4AI app (see media.py). Registered unless MAJORDOMO_MEDIA
    # is off; with the app down or no key set, the tools report that
    # honestly, the same posture as the unconfigured mail backend.
    if settings.media:
        register_media_tools(registry, build_media_client(settings), timeout=settings.media_timeout)

    # Teammates: the delegate_task tool exists when teammates are on
    # and at least one known agent CLI is detected — or when the
    # operator explicitly switched teammates on (then missing binaries
    # report "not installed" through the tool instead of the tool
    # silently not existing). MAJORDOMO_TEAMMATES=off removes it.
    teammates = detect_agents()
    if settings.teammates and (
        any(status.available for status in teammates) or "teammates" in settings.model_fields_set
    ):
        register_teammate_tools(
            registry,
            workspace_root=settings.workspace_dir,
            teammates_dir=settings.teammates_dir,
            timeout=settings.teammate_timeout,
        )

    notifier = Notifier(settings.notify_webhook)
    initiative = InitiativeEngine(
        backend=mail_backend,
        schedules=schedules,
        sessions=sessions,
        state_path=settings.initiative_path,
        now_fn=lambda: datetime.now(UTC),
        notify_fn=notifier.notify if notifier.enabled else None,
    )

    mcp_clients: list[MCPClient] = []
    if settings.mcp_config is not None:
        for name, spec in load_mcp_config(settings.mcp_config).items():
            client = MCPClient(
                name=name,
                command=str(spec["command"]),
                args=[str(a) for a in spec.get("args", [])],
                env={str(k): str(v) for k, v in (spec.get("env") or {}).items()} or None,
            )
            client.start()
            register_mcp_tools(registry, client)
            mcp_clients.append(client)

    agent = Agent(
        provider=provider,
        registry=registry,
        sessions=sessions,
        memory=memory,
        auto_memory=settings.auto_memory,
        self_store=self_store,
    )
    return Runtime(
        settings=settings,
        provider=provider,
        registry=registry,
        agent=agent,
        memory=memory,
        sessions=sessions,
        schedules=schedules,
        workspace=workspace,
        mail_backend=mail_backend,
        initiative=initiative,
        self_store=self_store,
        notifier=notifier,
        teammates=teammates,
        mcp_clients=mcp_clients,
    )
