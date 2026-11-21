"""Model providers.

The agent loop talks to one small protocol: ``chat(messages, tools)``
returning text and/or tool calls. Messages are plain dicts in the
OpenAI shape (``role`` / ``content`` / ``tool_calls`` / ``tool_call_id``);
each adapter translates for its own wire format.

Three adapters ship:

- :class:`OllamaProvider` — a local Ollama server (the default; no key).
- :class:`OpenAIProvider` — any OpenAI-compatible chat-completions API.
- :class:`FakeProvider` — scripted and deterministic. It powers the demo
  and the tests, and it is honest about what it is: connect a real
  provider for real answers.
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
                "canned reply. Connect Ollama or an OpenAI-compatible provider for real "
                "answers; ask me to remember, search, fetch, write, schedule, check mail, "
                "brief you, or draw and I'll use the tools instead."
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
    """Talk to any OpenAI-compatible chat-completions endpoint."""

    name = "openai"

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        # Lazy: constructing a provider never builds an HTTP client.
        self._client = client

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
            raise ProviderError(f"OpenAI-compatible endpoint failed ({exc}).") from exc
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


def build_provider(settings: Any) -> Provider:
    """Construct the configured provider from settings."""
    kind = str(getattr(settings, "provider", "ollama")).lower()
    if kind == "fake":
        return FakeProvider()
    if kind == "openai":
        return OpenAIProvider(
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            api_key=settings.openai_api_key,
        )
    return OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)
