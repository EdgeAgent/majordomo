"""Providers: the fake's determinism, and both live adapters' parsing."""

from __future__ import annotations

import json

import httpx
import pytest

from majordomo.providers import (
    FakeProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderError,
    ProviderResponse,
    ToolCall,
)


def _tools(*names: str) -> list[dict]:
    return [
        {"type": "function", "function": {"name": n, "description": "", "parameters": {}}}
        for n in names
    ]


def test_fake_script_mode_pops_in_order() -> None:
    provider = FakeProvider(script=[ProviderResponse(text="one"), ProviderResponse(text="two")])
    assert provider.chat([], []).text == "one"
    assert provider.chat([], []).text == "two"


def test_fake_remember_intent_prefers_preference_kind() -> None:
    provider = FakeProvider()
    response = provider.chat(
        [{"role": "user", "content": "Remember that my favourite tea is oolong"}],
        _tools("memory_remember"),
    )
    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert call.name == "memory_remember"
    assert call.arguments["kind"] == "preference"
    assert "oolong" in call.arguments["text"]


def test_fake_remind_intent_parses_minutes() -> None:
    provider = FakeProvider()
    response = provider.chat(
        [{"role": "user", "content": "Remind me in 45 minutes to call the bank"}],
        _tools("schedule_reminder"),
    )
    call = response.tool_calls[0]
    assert call.name == "schedule_reminder"
    assert call.arguments["due_in_minutes"] == 45
    assert "call the bank" in call.arguments["text"]


def test_fake_search_intent_extracts_query() -> None:
    provider = FakeProvider()
    response = provider.chat(
        [{"role": "user", "content": "Search the web for steel framing rates"}],
        _tools("web_search"),
    )
    assert response.tool_calls[0].arguments["query"] == "steel framing rates"


def test_fake_only_requests_offered_tools() -> None:
    provider = FakeProvider()
    response = provider.chat([{"role": "user", "content": "Remember that the sky is blue"}], [])
    assert response.tool_calls == []
    assert "fake provider" in response.text


def test_fake_summarizes_tool_results() -> None:
    provider = FakeProvider()
    response = provider.chat(
        [
            {"role": "user", "content": "search"},
            {"role": "tool", "name": "web_search", "content": "1. Result — example.com"},
        ],
        _tools("web_search"),
    )
    assert response.tool_calls == []
    assert "web_search" in response.text
    assert "example.com" in response.text


def test_fake_unknown_prompt_is_honest() -> None:
    provider = FakeProvider()
    response = provider.chat([{"role": "user", "content": "What is the meaning of life?"}], [])
    assert "fake provider" in response.text


# -- mail intents -------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["Check my mail", "check my email please", "Any new email?", "Any unread mail?"],
)
def test_fake_check_mail_intent_lists_mail(text: str) -> None:
    provider = FakeProvider()
    response = provider.chat([{"role": "user", "content": text}], _tools("mail_list"))
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "mail_list"


def test_fake_search_mail_intent_extracts_query() -> None:
    provider = FakeProvider()
    response = provider.chat(
        [{"role": "user", "content": "Search my mail for the moth story"}],
        _tools("mail_search"),
    )
    call = response.tool_calls[0]
    assert call.name == "mail_search"
    assert call.arguments["query"] == "the moth story"


@pytest.mark.parametrize(
    "text",
    [
        "I sent the mail yesterday.",
        "The mailman brought a package today.",
        "Email is my favourite way to write letters.",
        "Please forward the invoice to my accountant when it arrives.",
    ],
)
def test_fake_mail_mentions_are_not_mail_intents(text: str) -> None:
    provider = FakeProvider()
    response = provider.chat(
        [{"role": "user", "content": text}],
        _tools("mail_list", "mail_search", "web_search", "memory_remember"),
    )
    assert response.tool_calls == []
    assert "fake provider" in response.text


# -- multi-step chains ----------------------------------------------------


def test_fake_brief_chain_runs_reminders_then_mail() -> None:
    provider = FakeProvider()
    tools = _tools("list_reminders", "mail_list")
    first = provider.chat([{"role": "user", "content": "Brief me"}], tools)
    assert [call.name for call in first.tool_calls] == ["list_reminders"]

    history = [
        {"role": "user", "content": "Brief me"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "fake-1", "name": "list_reminders", "arguments": {}}],
        },
        {"role": "tool", "name": "list_reminders", "content": "No active reminders."},
    ]
    second = provider.chat(history, tools)
    assert [call.name for call in second.tool_calls] == ["mail_list"]

    history += [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "fake-2", "name": "mail_list", "arguments": {"limit": 10}}],
        },
        {"role": "tool", "name": "mail_list", "content": "fake-1 — From: Ada — Subject: Notes"},
    ]
    final = provider.chat(history, tools)
    assert final.tool_calls == []
    assert "list_reminders" in final.text
    assert "mail_list" in final.text


def test_fake_research_and_save_chain_writes_the_result() -> None:
    provider = FakeProvider()
    tools = _tools("web_search", "workspace_write")
    first = provider.chat(
        [{"role": "user", "content": "Look up steel framing rates and save it"}], tools
    )
    assert [call.name for call in first.tool_calls] == ["web_search"]
    assert first.tool_calls[0].arguments["query"] == "steel framing rates"

    history = [
        {"role": "user", "content": "Look up steel framing rates and save it"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "fake-1", "name": "web_search", "arguments": {"query": "steel framing"}}
            ],
        },
        {"role": "tool", "name": "web_search", "content": "1. Rates — example.com: $X per foot"},
    ]
    second = provider.chat(history, tools)
    assert [call.name for call in second.tool_calls] == ["workspace_write"]
    arguments = second.tool_calls[0].arguments
    assert arguments["path"] == "steel-framing-rates-notes.md"
    assert "$X per foot" in arguments["content"]


def test_fake_brief_me_end_to_end(runtime) -> None:  # type: ignore[no-untyped-def]
    from majordomo.tools import approve_all

    result = runtime.agent.run(None, "Brief me", approver=approve_all)
    called = [event.tool for event in result.events if event.kind == "tool_call"]
    assert called == ["list_reminders", "mail_list"]
    assert "mail_list" in result.text


def test_fake_check_mail_end_to_end(runtime) -> None:  # type: ignore[no-untyped-def]
    from majordomo.tools import approve_none

    result = runtime.agent.run(None, "Check my mail", approver=approve_none)
    called = [event.tool for event in result.events if event.kind == "tool_call"]
    assert called == ["mail_list"]
    assert "Analytical Engine" in result.text


def test_fake_research_and_save_end_to_end(runtime) -> None:  # type: ignore[no-untyped-def]
    from majordomo.tools import approve_all

    result = runtime.agent.run(
        None, "Look up small business AI adoption and save it", approver=approve_all
    )
    called = [event.tool for event in result.events if event.kind == "tool_call"]
    assert called == ["web_search", "workspace_write"]
    saved = runtime.workspace.read("small-business-ai-adoption-notes.md")
    assert "Research notes: small business AI adoption" in saved


def _mock_client(handler) -> httpx.Client:  # type: ignore[no-untyped-def]
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")


def test_openai_provider_parses_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "web_search",
                                    "arguments": json.dumps({"query": "rates"}),
                                },
                            }
                        ],
                    }
                }
            ]
        }
        return httpx.Response(200, json=payload)

    provider = OpenAIProvider(client=_mock_client(handler), api_key="test")
    response = provider.chat([{"role": "user", "content": "hi"}], _tools("web_search"))
    assert response.tool_calls == [
        ToolCall(id="call-1", name="web_search", arguments={"query": "rates"})
    ]


def test_openai_provider_parses_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "hello back", "tool_calls": []}}]}
        )

    provider = OpenAIProvider(client=_mock_client(handler), api_key="test")
    response = provider.chat([{"role": "user", "content": "hi"}], [])
    assert response.text == "hello back"


def test_ollama_provider_parses_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "memory_recall", "arguments": {"query": "coffee"}}}
                    ],
                }
            },
        )

    provider = OllamaProvider(client=_mock_client(handler))
    response = provider.chat([{"role": "user", "content": "hi"}], _tools("memory_recall"))
    assert response.tool_calls[0].name == "memory_recall"
    assert response.tool_calls[0].arguments == {"query": "coffee"}


def test_ollama_unreachable_is_an_honest_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    provider = OllamaProvider(client=_mock_client(handler))
    with pytest.raises(ProviderError, match="Ollama is unreachable"):
        provider.chat([{"role": "user", "content": "hi"}], [])
