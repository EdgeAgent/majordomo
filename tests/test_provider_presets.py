"""Provider presets: any key, any model.

Covers the registry itself, both adapters' wire shapes on mocked
HTTP (no network, no real keys), auto-detection priority, the model
override, runtime construction per preset, and the guarantee that a
key never shows up in reprs or the ``providers`` CLI output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from majordomo.cli import app
from majordomo.config import Settings
from majordomo.providers import (
    AUTO_PRIORITY,
    PROVIDER_PRESETS,
    AnthropicProvider,
    FakeProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderError,
    build_provider,
    resolve_provider_name,
)
from majordomo.runtime import build_runtime

runner = CliRunner()

HOSTED = [name for name in AUTO_PRIORITY]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ambient MAJORDOMO_* variable may leak into these tests."""
    import os

    for key in [k for k in os.environ if k.startswith("MAJORDOMO_")]:
        monkeypatch.delenv(key, raising=False)


def _settings(tmp_path: Path, **kwargs: Any) -> Settings:
    return Settings(data_dir=tmp_path / "data", **kwargs)


def _tools(*names: str) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": n,
                "description": f"The {n} tool",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
        }
        for n in names
    ]


def _mock_client(handler) -> httpx.Client:  # type: ignore[no-untyped-def]
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")


# -- the registry ---------------------------------------------------------


def test_presets_cover_the_major_providers_with_spec_defaults() -> None:
    expected = {
        "openai": ("https://api.openai.com/v1", "gpt-4o"),
        "deepseek": ("https://api.deepseek.com", "deepseek-chat"),
        "anthropic": ("https://api.anthropic.com", "claude-sonnet-4-5"),
        "gemini": (
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            "gemini-2.5-flash",
        ),
        "openrouter": ("https://openrouter.ai/api/v1", "openai/gpt-4o"),
        "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
        "mistral": ("https://api.mistral.ai/v1", "mistral-large-latest"),
        "xai": ("https://api.x.ai/v1", "grok-4"),
        "together": (
            "https://api.together.xyz/v1",
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        ),
    }
    for name, (base_url, model) in expected.items():
        preset = PROVIDER_PRESETS[name]
        assert preset.base_url == base_url
        assert preset.default_model == model
        assert preset.key_field == f"{name}_api_key"
        assert preset.key_env == f"MAJORDOMO_{name.upper()}_API_KEY"
    assert PROVIDER_PRESETS["anthropic"].adapter == "anthropic"
    for name in expected:
        if name != "anthropic":
            assert PROVIDER_PRESETS[name].adapter == "openai-compatible"
    assert PROVIDER_PRESETS["ollama"].key_field is None
    assert PROVIDER_PRESETS["fake"].key_field is None
    assert list(AUTO_PRIORITY) == [
        "anthropic",
        "openai",
        "deepseek",
        "gemini",
        "openrouter",
        "groq",
        "mistral",
        "xai",
        "together",
    ]


# -- OpenAI-compatible adapters, per preset --------------------------------


@pytest.mark.parametrize("name", ["openai", "deepseek", "groq", "gemini"])
def test_compatible_preset_request_shape_and_tool_parsing(name: str) -> None:
    preset = PROVIDER_PRESETS[name]
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
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
            },
        )

    provider = OpenAIProvider(
        name=preset.name,
        base_url=preset.base_url,
        model=preset.default_model,
        api_key="sk-test-key",
        client=_mock_client(handler),
    )
    response = provider.chat([{"role": "user", "content": "hi"}], _tools("web_search"))

    assert captured["url"] == f"{preset.base_url.rstrip('/')}/chat/completions"
    assert captured["auth"] == "Bearer sk-test-key"
    assert captured["payload"]["model"] == preset.default_model
    tool = captured["payload"]["tools"][0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "web_search"
    assert tool["function"]["parameters"]["properties"]["query"] == {"type": "string"}
    assert response.tool_calls[0].name == "web_search"
    assert response.tool_calls[0].arguments == {"query": "rates"}


def test_build_provider_wires_every_hosted_preset(tmp_path: Path) -> None:
    for name in HOSTED:
        preset = PROVIDER_PRESETS[name]
        settings = _settings(tmp_path, provider=name, **{preset.key_field: "sk-dummy"})
        provider = build_provider(settings)
        assert provider.name == name
        assert provider.model == preset.default_model  # type: ignore[attr-defined]
        if name == "anthropic":
            assert isinstance(provider, AnthropicProvider)
        else:
            assert isinstance(provider, OpenAIProvider)
            assert provider.base_url == preset.base_url.rstrip("/")  # type: ignore[attr-defined]


# -- the Anthropic adapter ---------------------------------------------------


def test_anthropic_request_shape() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "Let me look that up. "},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "web_search",
                        "input": {"query": "rates"},
                    },
                ]
            },
        )

    provider = AnthropicProvider(api_key="sk-ant-test", client=_mock_client(handler))
    response = provider.chat(
        [
            {"role": "system", "content": "You are Majordomo."},
            {"role": "user", "content": "search for rates"},
        ],
        _tools("web_search"),
    )

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-ant-test"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    payload = captured["payload"]
    assert payload["model"] == "claude-sonnet-4-5"
    assert payload["max_tokens"] == 4096
    assert payload["system"] == "You are Majordomo."
    assert payload["messages"] == [{"role": "user", "content": "search for rates"}]
    assert payload["tools"] == [
        {
            "name": "web_search",
            "description": "The web_search tool",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        }
    ]
    assert response.text == "Let me look that up. "
    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert (call.id, call.name, call.arguments) == (
        "toolu_1",
        "web_search",
        {"query": "rates"},
    )


def test_anthropic_tool_round_trip_both_directions() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "done"}]})

    provider = AnthropicProvider(api_key="sk-ant-test", client=_mock_client(handler))
    history = [
        {"role": "system", "content": "You are Majordomo."},
        {"role": "user", "content": "search for rates"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "toolu_1", "name": "web_search", "arguments": {"query": "rates"}},
                {"id": "toolu_2", "name": "web_fetch", "arguments": {"url": "https://x.test"}},
            ],
        },
        {"role": "tool", "tool_call_id": "toolu_1", "name": "web_search", "content": "result one"},
        {"role": "tool", "tool_call_id": "toolu_2", "name": "web_fetch", "content": "result two"},
    ]
    response = provider.chat(history, _tools("web_search", "web_fetch"))
    assert response.text == "done"

    messages = captured["payload"]["messages"]
    assert messages[0] == {"role": "user", "content": "search for rates"}
    assistant = messages[1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == [
        {"type": "tool_use", "id": "toolu_1", "name": "web_search", "input": {"query": "rates"}},
        {
            "type": "tool_use",
            "id": "toolu_2",
            "name": "web_fetch",
            "input": {"url": "https://x.test"},
        },
    ]
    # Parallel tool results ride in ONE user message, as tool_result blocks.
    results = messages[2]
    assert results["role"] == "user"
    assert results["content"] == [
        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "result one"},
        {"type": "tool_result", "tool_use_id": "toolu_2", "content": "result two"},
    ]
    assert len(messages) == 3


def test_anthropic_unreachable_is_an_honest_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    provider = AnthropicProvider(api_key="sk-ant-test", client=_mock_client(handler))
    with pytest.raises(ProviderError, match="anthropic"):
        provider.chat([{"role": "user", "content": "hi"}], [])


# -- selection: explicit, auto, override -------------------------------------


def test_auto_prefers_anthropic_over_openai(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path, provider="auto", anthropic_api_key="a-key", openai_api_key="o-key"
    )
    assert resolve_provider_name(settings) == "anthropic"
    assert isinstance(build_provider(settings), AnthropicProvider)


def test_auto_walks_the_priority_order(tmp_path: Path) -> None:
    assert (
        resolve_provider_name(
            _settings(tmp_path, openai_api_key="o", deepseek_api_key="d", groq_api_key="g")
        )
        == "openai"
    )
    assert (
        resolve_provider_name(_settings(tmp_path, deepseek_api_key="d", groq_api_key="g"))
        == "deepseek"
    )
    assert resolve_provider_name(_settings(tmp_path, together_api_key="t")) == "together"


def test_auto_with_no_keys_is_fake(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert settings.provider == "auto"  # the default when unset
    assert resolve_provider_name(settings) == "fake"
    assert isinstance(build_provider(settings), FakeProvider)


def test_auto_with_configured_ollama_uses_ollama(tmp_path: Path) -> None:
    settings = _settings(tmp_path, ollama_base_url="http://192.168.1.10:11434")
    assert resolve_provider_name(settings) == "ollama"
    provider = build_provider(settings)
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://192.168.1.10:11434"


def test_explicit_provider_beats_auto(tmp_path: Path) -> None:
    settings = _settings(tmp_path, provider="deepseek", anthropic_api_key="a", deepseek_api_key="d")
    provider = build_provider(settings)
    assert provider.name == "deepseek"
    assert isinstance(provider, OpenAIProvider)


def test_unknown_provider_is_a_clean_error(tmp_path: Path) -> None:
    with pytest.raises(ProviderError, match="Unknown provider"):
        build_provider(_settings(tmp_path, provider="skynet"))


def test_model_override_beats_preset_default(tmp_path: Path) -> None:
    settings = _settings(tmp_path, provider="openai", openai_api_key="k", model="gpt-4o-mini")
    provider = build_provider(settings)
    assert provider.model == "gpt-4o-mini"  # type: ignore[attr-defined]

    settings = _settings(
        tmp_path, provider="anthropic", anthropic_api_key="k", model="claude-opus-4-5"
    )
    assert build_provider(settings).model == "claude-opus-4-5"  # type: ignore[attr-defined]


def test_preset_default_model_without_override(tmp_path: Path) -> None:
    settings = _settings(tmp_path, provider="openai", openai_api_key="k")
    assert build_provider(settings).model == "gpt-4o"  # type: ignore[attr-defined]


def test_legacy_openai_settings_still_win_when_set(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        provider="openai",
        openai_api_key="k",
        openai_model="gpt-4o-mini",
        openai_base_url="http://localhost:9999/v1",
    )
    provider = build_provider(settings)
    assert provider.model == "gpt-4o-mini"  # type: ignore[attr-defined]
    assert provider.base_url == "http://localhost:9999/v1"  # type: ignore[attr-defined]


# -- runtime construction ------------------------------------------------------


def test_runtime_builds_for_every_hosted_preset(tmp_path: Path) -> None:
    for name in HOSTED:
        preset = PROVIDER_PRESETS[name]
        settings = _settings(tmp_path / name, provider=name, **{preset.key_field: "sk-dummy"})
        runtime = build_runtime(settings)
        try:
            assert runtime.provider.name == name
        finally:
            runtime.close()


def test_runtime_auto_with_a_dummy_anthropic_key(tmp_path: Path) -> None:
    settings = _settings(tmp_path, anthropic_api_key="sk-dummy")
    runtime = build_runtime(settings)
    try:
        assert runtime.provider.name == "anthropic"
        assert isinstance(runtime.provider, AnthropicProvider)
    finally:
        runtime.close()


# -- keys stay secret ------------------------------------------------------------


def test_keys_never_appear_in_provider_reprs() -> None:
    secret = "sk-super-secret-value-123"
    providers = [
        OpenAIProvider(name="deepseek", api_key=secret),
        OpenAIProvider(api_key=secret),
        AnthropicProvider(api_key=secret),
    ]
    for provider in providers:
        assert secret not in repr(provider)
        assert secret not in str(provider)
    assert "<set>" in repr(providers[0])


def test_providers_cli_lists_everything_and_never_a_key(tmp_path: Path) -> None:
    secret = "sk-ant-dummy-12345"
    env = {
        "MAJORDOMO_DATA_DIR": str(tmp_path / "data"),
        "MAJORDOMO_ANTHROPIC_API_KEY": secret,
        "COLUMNS": "220",
    }
    result = runner.invoke(app, ["providers"], env=env)
    assert result.exit_code == 0
    out = result.stdout
    for name in PROVIDER_PRESETS:
        assert name in out
    assert "MAJORDOMO_ANTHROPIC_API_KEY" in out
    assert "key set" in out
    assert "no key" in out
    assert "active" in out
    assert "Active: anthropic" in out
    assert secret not in out


def test_providers_cli_no_keys_means_fake_is_active(tmp_path: Path) -> None:
    env = {"MAJORDOMO_DATA_DIR": str(tmp_path / "data"), "COLUMNS": "220"}
    result = runner.invoke(app, ["providers"], env=env)
    assert result.exit_code == 0
    assert "Active: fake" in result.stdout
