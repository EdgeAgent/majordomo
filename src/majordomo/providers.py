"""Model providers.

The agent loop talks to one small protocol: ``chat(messages, tools)``
returning text and/or tool calls. Messages are plain dicts in the
OpenAI shape (``role`` / ``content`` / ``tool_calls`` / ``tool_call_id``);
each adapter translates for its own wire format.

Bring any key you have. A preset registry (:data:`PROVIDER_PRESETS`)
maps each provider name to its adapter, endpoint, key setting, and
default model:

- :class:`OpenAIProvider` — one parameterized adapter for every
  OpenAI-compatible chat-completions API: OpenAI, DeepSeek, Gemini,
  OpenRouter, Groq, Mistral, xAI, and Together.
- :class:`AnthropicProvider` — Anthropic's Messages API, whose wire
  shape genuinely differs (top-level system prompt, ``tool_use`` /
  ``tool_result`` blocks), so it gets its own adapter.
- :class:`OllamaProvider` — a local Ollama server (no key).
- :class:`FakeProvider` — scripted and deterministic. It powers the demo
  and the tests, and it is honest about what it is: connect a real
  provider for real answers.

With ``MAJORDOMO_PROVIDER=auto`` (the default), the first hosted key
that is set wins — see :data:`AUTO_PRIORITY` — then a configured local
Ollama, then the fake. ``MAJORDOMO_MODEL`` overrides any preset's
default model. Keys are never logged or printed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

Message = dict[str, Any]
ToolSchema = dict[str, Any]


class ProviderError(RuntimeError):
    """A provider call failed; the message says why, honestly."""


@dataclass
class ToolCall:
    """One tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderResponse:
    """Text and/or tool calls from one provider round trip."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class Provider(Protocol):
    """The contract every provider adapter implements."""

    name: str

    def chat(self, messages: list[Message], tools: list[ToolSchema]) -> ProviderResponse:
        """Send the conversation and tool schemas; return the reply."""
        ...


def _tool_names(tools: list[ToolSchema]) -> set[str]:
    return {t.get("function", {}).get("name", "") for t in tools}


@dataclass(frozen=True)
class ProviderPreset:
    """One selectable provider: adapter, endpoint, key, default model."""

    name: str
    adapter: str  # "openai-compatible" | "anthropic" | "ollama" | "fake"
    base_url: str
    default_model: str
    key_field: str | None  # Settings attribute holding the API key
    key_env: str | None  # environment variable that feeds key_field
    console: str  # where the user gets a key ("" when no key exists)


# Every provider Majordomo knows, in display order. Most hosted APIs
# speak the OpenAI chat-completions shape, so they share one adapter;
# only the endpoint, key, and default model differ.
PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    preset.name: preset
    for preset in (
        ProviderPreset(
            "anthropic",
            "anthropic",
            "https://api.anthropic.com",
            "claude-sonnet-4-5",
            "anthropic_api_key",
            "MAJORDOMO_ANTHROPIC_API_KEY",
            "console.anthropic.com",
        ),
        ProviderPreset(
            "openai",
            "openai-compatible",
            "https://api.openai.com/v1",
            "gpt-4o",
            "openai_api_key",
            "MAJORDOMO_OPENAI_API_KEY",
            "platform.openai.com",
        ),
        ProviderPreset(
            "deepseek",
            "openai-compatible",
            "https://api.deepseek.com",
            "deepseek-chat",
            "deepseek_api_key",
            "MAJORDOMO_DEEPSEEK_API_KEY",
            "platform.deepseek.com",
        ),
        ProviderPreset(
            "gemini",
            "openai-compatible",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            "gemini-2.5-flash",
            "gemini_api_key",
            "MAJORDOMO_GEMINI_API_KEY",
            "Google AI Studio (aistudio.google.com)",
        ),
        ProviderPreset(
            "openrouter",
            "openai-compatible",
            "https://openrouter.ai/api/v1",
            "openai/gpt-4o",
            "openrouter_api_key",
            "MAJORDOMO_OPENROUTER_API_KEY",
            "openrouter.ai",
        ),
        ProviderPreset(
            "groq",
            "openai-compatible",
            "https://api.groq.com/openai/v1",
            "llama-3.3-70b-versatile",
            "groq_api_key",
            "MAJORDOMO_GROQ_API_KEY",
            "console.groq.com",
        ),
        ProviderPreset(
            "mistral",
            "openai-compatible",
            "https://api.mistral.ai/v1",
            "mistral-large-latest",
            "mistral_api_key",
            "MAJORDOMO_MISTRAL_API_KEY",
            "console.mistral.ai",
        ),
        ProviderPreset(
            "xai",
            "openai-compatible",
            "https://api.x.ai/v1",
            "grok-4",
            "xai_api_key",
            "MAJORDOMO_XAI_API_KEY",
            "console.x.ai",
        ),
        ProviderPreset(
            "together",
            "openai-compatible",
            "https://api.together.xyz/v1",
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "together_api_key",
            "MAJORDOMO_TOGETHER_API_KEY",
            "api.together.ai",
        ),
        ProviderPreset(
            "ollama",
            "ollama",
            "http://localhost:11434",
            "llama3.1",
            None,
            None,
            "ollama.com — runs locally, no key",
        ),
        ProviderPreset(
            "fake",
            "fake",
            "",
            "(scripted)",
            None,
            None,
            "built in — the offline demo provider",
        ),
    )
}

# Auto-detection order: the first hosted provider whose key is set
# becomes the active one.
AUTO_PRIORITY: tuple[str, ...] = (
    "anthropic",
    "openai",
    "deepseek",
    "gemini",
    "openrouter",
    "groq",
    "mistral",
    "xai",
    "together",
)


def resolve_provider_name(settings: Any) -> str:
    """The provider that would be active under these settings.

    An explicit ``MAJORDOMO_PROVIDER`` wins. ``auto`` walks
    :data:`AUTO_PRIORITY` for the first set key, then falls back to a
    *configured* Ollama (its endpoint or model was set explicitly —
    the defaults alone don't count), then the offline fake.
    """
    kind = str(getattr(settings, "provider", "auto") or "auto").lower().strip()
    if kind != "auto":
        if kind in PROVIDER_PRESETS:
            return kind
        raise ProviderError(
            f"Unknown provider {kind!r}. Choose one of: {', '.join([*PROVIDER_PRESETS, 'auto'])}."
        )
    for name in AUTO_PRIORITY:
        preset = PROVIDER_PRESETS[name]
        if preset.key_field and getattr(settings, preset.key_field, None):
            return name
    fields_set = getattr(settings, "model_fields_set", set())
    if "ollama_base_url" in fields_set or "ollama_model" in fields_set:
        return "ollama"
    return "fake"


def resolve_model(settings: Any, name: str) -> str:
    """The model that would be used for provider ``name``.

    ``MAJORDOMO_MODEL`` overrides everything; the legacy per-provider
    model settings still win for their own provider when they were set
    explicitly; otherwise the preset's default model.
    """
    override = getattr(settings, "model", None)
    if override:
        return str(override)
    fields_set = getattr(settings, "model_fields_set", set())
    if name == "ollama":
        return str(settings.ollama_model)
    if name == "openai" and "openai_model" in fields_set:
        return str(settings.openai_model)
    return PROVIDER_PRESETS[name].default_model


class FakeProvider:
    """A deterministic, offline provider for demos and tests.

    Two modes: a *script* (a queue of responses returned in order) for
    unit tests that need exact control, and a small intent matcher that
    maps obvious phrasing ("remember that…", "search the web for…",
    "remind me…") onto tool calls, then summarizes tool results. The
    matcher only ever requests tools that were actually offered.
    """

    name = "fake"

    def __init__(self, script: list[ProviderResponse] | None = None) -> None:
        self._script: list[ProviderResponse] = list(script or [])
        self._counter = 0

    def _call(self, name: str, arguments: dict[str, Any]) -> ProviderResponse:
        self._counter += 1
        return ProviderResponse(
            tool_calls=[ToolCall(id=f"fake-{self._counter}", name=name, arguments=arguments)]
        )

    def chat(self, messages: list[Message], tools: list[ToolSchema]) -> ProviderResponse:
        if self._script:
            return self._script.pop(0)

        available = _tool_names(tools)

        # A multi-step chain ("brief me", "look up X and save it") may
        # have a next step — on a fresh user turn (step one) or right
        # after a tool result came back (the following steps).
        chain_call = self._next_chain_call(messages, available)
        if chain_call is not None:
            return chain_call

        # Tool results just came back: summarize everything the tools
        # reported since the user's message, and stop.
        if messages and messages[-1].get("role") == "tool":
            lines = []
            for message in reversed(messages):
                if message.get("role") == "user":
                    break
                if message.get("role") != "tool":
                    continue
                content = str(message.get("content", "")).strip().replace("\n", " ")
                lines.append(f"- {message.get('name', 'tool')}: {content[:240]}")
            lines.reverse()
            return ProviderResponse(text="Here's what the tools reported:\n" + "\n".join(lines))

        user_text = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user_text = str(message.get("content", ""))
                break
        intent = self._intent(user_text)
        if intent is not None and intent[0] in available:
            return self._call(intent[0], intent[1])
        return ProviderResponse(
            text=(
                f'You said: "{user_text}" — I\'m the built-in fake provider, so this is a '
                "canned reply. Connect Ollama or set any provider key for real "
                "answers; ask me to remember, search, fetch, write, schedule, check mail, "
                "brief you, delegate to a teammate, or draw and I'll use the tools instead."
            )
        )

    # -- multi-step chains ----------------------------------------------
    #
    # Two requests need more than one tool: a brief is reminders *and*
    # mail, and "look up X and save it" is a search *then* a write.
    # The agent loop already supports many steps; the fake just has to
    # ask for the steps in order. Progress is read off the history:
    # the tool calls made since the last user message are the steps
    # already done, so the next one is simply the next in the list.

    def _next_chain_call(
        self, messages: list[Message], available: set[str]
    ) -> ProviderResponse | None:
        user_index = -1
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get("role") == "user":
                user_index = index
                break
        if user_index < 0:
            return None
        user_text = str(messages[user_index].get("content", ""))
        steps = self._chain_steps(user_text, messages[user_index + 1 :])
        if steps is None:
            return None
        called: list[str] = []
        for message in messages[user_index + 1 :]:
            for call in message.get("tool_calls") or []:
                called.append(str(call.get("name", "")))
        if called != [name for name, _ in steps[: len(called)]]:
            return None  # some other flow is running; don't hijack it
        if len(called) >= len(steps):
            return None  # chain finished; the caller summarizes
        name, arguments = steps[len(called)]
        if name not in available:
            return None
        return self._call(name, arguments)

    def _chain_steps(
        self, text: str, since_user: list[Message]
    ) -> list[tuple[str, dict[str, Any]]] | None:
        lowered = text.lower()
        brief_phrases = (
            "brief me",
            "morning brief",
            "daily brief",
            "what's on today",
            "whats on today",
            "what is on today",
        )
        if any(phrase in lowered for phrase in brief_phrases):
            return [("list_reminders", {}), ("mail_list", {"limit": 10})]

        save_match = re.search(r"(?i)(?:look up|research)\s+(.+?)\s+and save\b", text)
        if save_match:
            query = save_match.group(1).strip().rstrip(".?!")
            if not query:
                return None
            steps: list[tuple[str, dict[str, Any]]] = [("web_search", {"query": query})]
            result = ""
            for message in since_user:
                if message.get("role") == "tool" and message.get("name") == "web_search":
                    result = str(message.get("content", ""))
            if result:
                steps.append(
                    (
                        "workspace_write",
                        {
                            "path": f"{self._slug(query)}-notes.md",
                            "content": (
                                f"# Research notes: {query}\n\n{result}\n\n"
                                "(Saved by Majordomo's fake provider from the "
                                "web_search result above.)\n"
                            ),
                        },
                    )
                )
            return steps
        return None

    def _intent(self, text: str) -> tuple[str, dict[str, Any]] | None:
        lowered = text.lower()
        url_match = re.search(r"https?://\S+", text)

        # Delegation: "delegate to claude: <task>" or "ask codex to
        # <task>" hands the work to a teammate character. Checked
        # first — it is the most explicit phrasing there is.
        delegate = re.search(
            r"(?is)^\s*(?:delegate to|ask)\s+([a-z][\w-]*)\s*(?::|\bto\b)\s*(.+)$", text
        )
        if delegate and delegate.group(1).lower() != "me":
            task = delegate.group(2).strip()
            if task:
                return "delegate_task", {"agent": delegate.group(1).lower(), "task": task}

        if "remind" in lowered:
            numbers = re.findall(r"\d+", text)
            due = int(numbers[0]) if numbers else 60
            repeat = "daily" if "every day" in lowered else "none"
            body = re.sub(r"(?i)^.*?remind me( to)?\s*", "", text).strip() or text
            body = re.sub(r"(?i)^in \d+ minutes?\s+(to\s+)?", "", body).strip() or body
            return "schedule_reminder", {"text": body, "due_in_minutes": due, "repeat": repeat}

        if "do you remember" in lowered or "what do you remember" in lowered or "recall" in lowered:
            return "memory_recall", {"query": text}

        if lowered.startswith("remember") or " remember " in lowered:
            body = re.sub(r"(?i)^.*?remember( that)?\s*", "", text).strip() or text
            kind = (
                "preference"
                if ("prefer" in lowered or "favourite" in lowered or "favorite" in lowered)
                else "fact"
            )
            return "memory_remember", {"kind": kind, "text": body}

        # Mail intents are phrase-shaped on purpose: a sentence that
        # merely mentions mail ("I sent the mail yesterday") matches
        # none of these and falls through to the canned reply.
        mail_search = re.search(r"(?i)search (?:my )?(?:mail|email|inbox) for (.+)", text)
        if mail_search:
            query = mail_search.group(1).strip().rstrip("?.! ")
            if query:
                return "mail_search", {"query": query}

        mail_list_phrases = (
            "check my mail",
            "check my email",
            "check my inbox",
            "any new mail",
            "any new email",
            "any unread mail",
            "any unread email",
            "show my inbox",
            "read my inbox",
        )
        if any(phrase in lowered for phrase in mail_list_phrases):
            return "mail_list", {"limit": 10}

        if url_match and ("fetch" in lowered or "read" in lowered or "open" in lowered):
            return "web_fetch", {"url": url_match.group(0)}

        if "search the web" in lowered or lowered.startswith("research"):
            query = re.sub(r"(?i)^.*?(search the web for|research:?)\s*", "", text).strip()
            return "web_search", {"query": query or text}

        if "past conversation" in lowered or "we talked about" in lowered or "earlier" in lowered:
            return "search_past_chats", {"query": text}

        if "powerpoint" in lowered or "slides" in lowered or "deck" in lowered:
            title = self._titled(text) or "Briefing"
            return "create_powerpoint", {
                "filename": self._slug(title) + ".pptx",
                "title": title,
                "slides": [
                    {"title": title, "bullets": ["Overview", "Key points", "Next steps"]},
                    {"title": "Next steps", "bullets": ["Review", "Decide", "Schedule"]},
                ],
            }

        if "spreadsheet" in lowered or "excel" in lowered:
            title = self._titled(text) or "Data"
            return "create_spreadsheet", {
                "filename": self._slug(title) + ".xlsx",
                "sheet_name": "Sheet1",
                "rows": [["Item", "Notes"], [title, "Created by Majordomo (fake provider)"]],
            }

        if "word" in lowered or "brief" in lowered or "document" in lowered:
            title = self._titled(text) or "Brief"
            return "create_word_doc", {
                "filename": self._slug(title) + ".docx",
                "title": title,
                "paragraphs": [
                    f"This {title} was drafted by Majordomo's fake provider for the demo.",
                    "Replace this text with the real thing once a live provider is connected.",
                ],
            }

        if "image" in lowered or "picture" in lowered or "draw" in lowered:
            return "generate_image", {"prompt": text, "filename": "image.png"}

        if "list files" in lowered or "in my workspace" in lowered:
            return "workspace_list", {"path": "."}

        return None

    @staticmethod
    def _titled(text: str) -> str | None:
        match = re.search(
            r"(?i)(?:called|titled)\s+['\"]?(.+?)(?:\s+(?:about|on|for)\s+.*)?$",
            text,
        )
        if not match:
            return None
        return match.group(1).strip().strip("'\"") or None

    @staticmethod
    def _slug(title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return slug or "document"


class OllamaProvider:
    """Talk to a local Ollama server's ``/api/chat`` endpoint."""

    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1",
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        # Lazy: constructing a provider never builds an HTTP client.
        self._client = client

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=120.0)
        return self._client

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._get_client().post(f"{self.base_url}/api/chat", json=payload)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    def chat(self, messages: list[Message], tools: list[ToolSchema]) -> ProviderResponse:
        wire: list[dict[str, Any]] = []
        for message in messages:
            item: dict[str, Any] = {"role": message["role"], "content": message.get("content", "")}
            if message.get("tool_calls"):
                item["tool_calls"] = [
                    {"function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in message["tool_calls"]
                ]
            wire.append(item)
        payload: dict[str, Any] = {"model": self.model, "messages": wire, "stream": False}
        if tools:
            payload["tools"] = tools
        try:
            data = self._post(payload)
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Ollama is unreachable at {self.base_url} ({exc}). Is `ollama serve` running?"
            ) from exc
        message = data.get("message", {})
        calls = [
            ToolCall(
                id=f"ollama-{i}",
                name=c.get("function", {}).get("name", ""),
                arguments=c.get("function", {}).get("arguments", {}) or {},
            )
            for i, c in enumerate(message.get("tool_calls") or [])
        ]
        return ProviderResponse(text=str(message.get("content", "")), tool_calls=calls)


class OpenAIProvider:
    """Talk to any OpenAI-compatible chat-completions endpoint.

    One adapter serves every compatible preset — OpenAI, DeepSeek,
    Gemini, OpenRouter, Groq, Mistral, xAI, Together — parameterized
    by ``name``, ``base_url``, ``model``, and ``api_key``.
    """

    name = "openai"

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        client: httpx.Client | None = None,
        name: str = "openai",
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        # Lazy: constructing a provider never builds an HTTP client.
        self._client = client

    def __repr__(self) -> str:
        # The key is never part of any debug output — only set/unset.
        state = "<set>" if self.api_key else "<unset>"
        return (
            f"OpenAIProvider(name={self.name!r}, model={self.model!r}, "
            f"base_url={self.base_url!r}, api_key={state})"
        )

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=120.0)
        return self._client

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        response = self._get_client().post(
            f"{self.base_url}/chat/completions", json=payload, headers=headers
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    def chat(self, messages: list[Message], tools: list[ToolSchema]) -> ProviderResponse:
        wire: list[dict[str, Any]] = []
        for message in messages:
            item: dict[str, Any] = {"role": message["role"], "content": message.get("content", "")}
            if message.get("role") == "tool":
                item["tool_call_id"] = message.get("tool_call_id", "")
                item["name"] = message.get("name", "")
            if message.get("tool_calls"):
                item["tool_calls"] = [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])},
                    }
                    for c in message["tool_calls"]
                ]
            wire.append(item)
        payload: dict[str, Any] = {"model": self.model, "messages": wire}
        if tools:
            payload["tools"] = tools
        try:
            data = self._post(payload)
        except httpx.HTTPError as exc:
            raise ProviderError(f"The {self.name} endpoint failed ({exc}).") from exc
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        calls = []
        for raw in message.get("tool_calls") or []:
            function = raw.get("function", {})
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            calls.append(
                ToolCall(
                    id=str(raw.get("id", "")), name=function.get("name", ""), arguments=arguments
                )
            )
        return ProviderResponse(text=str(message.get("content") or ""), tool_calls=calls)


def _anthropic_tool(tool: ToolSchema) -> dict[str, Any]:
    """Translate one internal (OpenAI-shaped) tool schema for Anthropic."""
    function = tool.get("function", tool)
    return {
        "name": function.get("name", ""),
        "description": function.get("description", ""),
        "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
    }


class AnthropicProvider:
    """Talk to Anthropic's Messages API.

    The wire shape differs from the OpenAI one in three places: the
    system prompt is a top-level field (not a message), tools are
    ``{name, description, input_schema}``, and tool calls / results
    travel as ``tool_use`` / ``tool_result`` content blocks — results
    ride in a *user* message, and parallel results share one.
    """

    name = "anthropic"
    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(
        self,
        base_url: str = "https://api.anthropic.com",
        model: str = "claude-sonnet-4-5",
        api_key: str | None = None,
        max_tokens: int = 4096,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        # Lazy: constructing a provider never builds an HTTP client.
        self._client = client

    def __repr__(self) -> str:
        # The key is never part of any debug output — only set/unset.
        state = "<set>" if self.api_key else "<unset>"
        return (
            f"AnthropicProvider(model={self.model!r}, base_url={self.base_url!r}, api_key={state})"
        )

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=120.0)
        return self._client

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "anthropic-version": self.ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        response = self._get_client().post(
            f"{self.base_url}/v1/messages", json=payload, headers=headers
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    def _wire_messages(self, messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
        """Split the internal history into (system prompt, wire messages)."""
        system_parts: list[str] = []
        wire: list[dict[str, Any]] = []
        pending_results: list[dict[str, Any]] = []

        def flush_results() -> None:
            if pending_results:
                wire.append({"role": "user", "content": list(pending_results)})
                pending_results.clear()

        def append_user(content: Any) -> None:
            # Anthropic wants alternating roles; merge into a trailing
            # user message instead of emitting two in a row.
            if wire and wire[-1].get("role") == "user":
                previous = wire[-1]["content"]
                merged: list[Any] = (
                    list(previous)
                    if isinstance(previous, list)
                    else [{"type": "text", "text": previous}]
                )
                merged.extend(
                    content if isinstance(content, list) else [{"type": "text", "text": content}]
                )
                wire[-1] = {"role": "user", "content": merged}
            else:
                wire.append({"role": "user", "content": content})

        for message in messages:
            role = message.get("role")
            if role == "system":
                text = str(message.get("content", "")).strip()
                if text:
                    system_parts.append(text)
            elif role == "tool":
                pending_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": message.get("tool_call_id", ""),
                        "content": str(message.get("content", "")),
                    }
                )
            elif role == "assistant":
                flush_results()
                blocks: list[dict[str, Any]] = []
                text = str(message.get("content") or "")
                if text:
                    blocks.append({"type": "text", "text": text})
                for call in message.get("tool_calls") or []:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": call["id"],
                            "name": call["name"],
                            "input": call.get("arguments") or {},
                        }
                    )
                wire.append({"role": "assistant", "content": blocks if blocks else text})
            else:  # user
                flush_results()
                append_user(str(message.get("content", "")))
        flush_results()
        return "\n\n".join(system_parts), wire

    def chat(self, messages: list[Message], tools: list[ToolSchema]) -> ProviderResponse:
        system, wire = self._wire_messages(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": wire,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [_anthropic_tool(tool) for tool in tools]
        try:
            data = self._post(payload)
        except httpx.HTTPError as exc:
            raise ProviderError(f"The anthropic endpoint failed ({exc}).") from exc
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            elif block.get("type") == "tool_use":
                calls.append(
                    ToolCall(
                        id=str(block.get("id", "")),
                        name=str(block.get("name", "")),
                        arguments=block.get("input") or {},
                    )
                )
        return ProviderResponse(text="".join(text_parts), tool_calls=calls)


def build_provider(settings: Any) -> Provider:
    """Construct the provider the settings select (see the presets)."""
    name = resolve_provider_name(settings)
    if name == "fake":
        return FakeProvider()
    preset = PROVIDER_PRESETS[name]
    if preset.adapter == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=resolve_model(settings, name),
        )
    key = getattr(settings, preset.key_field, None) if preset.key_field else None
    model = resolve_model(settings, name)
    if preset.adapter == "anthropic":
        return AnthropicProvider(base_url=preset.base_url, model=model, api_key=key)
    base_url = preset.base_url
    if name == "openai" and "openai_base_url" in getattr(settings, "model_fields_set", set()):
        # A legacy explicit endpoint (e.g. a local proxy) still wins.
        base_url = settings.openai_base_url
    return OpenAIProvider(name=name, base_url=base_url, model=model, api_key=key)
