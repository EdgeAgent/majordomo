"""Self-filing memory: the conservative extractor and its wiring.

The positives are the only two shapes the extractor may file. The
negatives matter just as much: questions, commands, and chit-chat
must never become "facts" — the suite proves they don't.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from majordomo.autocapture import extract_facts
from majordomo.config import Settings
from majordomo.providers import FakeProvider
from majordomo.runtime import build_runtime
from majordomo.tools import approve_none


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "remember that the workshop is in London, Ontario",
            ["the workshop is in London, Ontario"],
        ),
        ("Remember my sister's name is Maria", ["my sister's name is Maria"]),
        ("please remember that the gate code is 4419", ["the gate code is 4419"]),
        (
            "my favourite coffee is a double espresso",
            ["my favourite coffee is a double espresso"],
        ),
        ("My name is Kevin.", ["my name is Kevin"]),
        (
            "My dog is named Rex. The weather is nice today.",
            ["my dog is named Rex"],
        ),
    ],
)
def test_extractor_positive_shapes(text: str, expected: list[str]) -> None:
    assert extract_facts(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "What is my favourite coffee?",
        "Do you remember my name?",
        "do you remember what I told you yesterday?",
        "Remind me to buy milk in 10 minutes",
        "remember to lock the door",
        "remember what I said yesterday",
        "don't remember this",
        "search the web for coffee shops",
        "hello, how are you?",
        "I love coffee",
        "is my package here yet",
        "my favourite coffee is",
        "Can you fetch https://example.com for me?",
        "Set a reminder for tomorrow morning",
        "",
    ],
)
def test_extractor_never_files_questions_commands_or_chitchat(text: str) -> None:
    assert extract_facts(text) == []


def _run_message(tmp_path: Path, auto_memory: bool, text: str) -> list[str]:
    settings = Settings(data_dir=tmp_path / "data", provider="fake", auto_memory=auto_memory)
    runtime = build_runtime(settings, provider=FakeProvider(), offline=True)
    try:
        runtime.agent.run(None, text, approver=approve_none)
        return [entry.text for entry in runtime.memory.list("fact")]
    finally:
        runtime.close()


def test_auto_memory_files_a_declaration(tmp_path: Path) -> None:
    facts = _run_message(tmp_path, True, "my favourite coffee is a double espresso")
    assert facts == ["my favourite coffee is a double espresso"]


def test_auto_memory_files_an_explicit_remember_even_when_the_tool_is_declined(
    tmp_path: Path,
) -> None:
    # The fake provider asks for the memory_remember tool; approve_none
    # declines it. Self-filing is the operator's standing opt-in, so
    # the stated fact is still filed — once, as a fact.
    facts = _run_message(tmp_path, True, "remember that the workshop is in London, Ontario")
    assert facts == ["the workshop is in London, Ontario"]


def test_auto_memory_off_by_default(tmp_path: Path) -> None:
    facts = _run_message(tmp_path, False, "my favourite coffee is a double espresso")
    assert facts == []


def test_auto_memory_ignores_questions_and_chitchat(tmp_path: Path) -> None:
    assert _run_message(tmp_path, True, "What is my favourite coffee?") == []
    assert _run_message(tmp_path / "q2", True, "hello, how are you?") == []


def test_auto_memory_does_not_file_twice(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", provider="fake", auto_memory=True)
    runtime = build_runtime(settings, provider=FakeProvider(), offline=True)
    try:
        runtime.agent.run(None, "my favourite coffee is a double espresso", approver=approve_none)
        runtime.agent.run(None, "my favourite coffee is a double espresso", approver=approve_none)
        facts = [entry.text for entry in runtime.memory.list("fact")]
        assert facts == ["my favourite coffee is a double espresso"]
    finally:
        runtime.close()
