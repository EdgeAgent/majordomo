"""Self-filing memory: conservative capture of stated facts.

Long-term memory is explicit by design — the agent files nothing
silently. An operator can opt in to self-filing
(``MAJORDOMO_AUTO_MEMORY``), and even then the extractor here is
deliberately narrow. It recognises exactly two shapes in the user's
own words:

- explicit statements: ``remember ...`` / ``remember that ...``
- simple declarations: ``my <thing> is <value>``

Everything else yields nothing: questions (including "do you remember
...?" and "what is my ...?"), commands ("remind me to ...",
"remember to lock the door"), and ordinary chit-chat are never filed.
When in doubt, the extractor stays silent — a missed fact can be
repeated; a wrongly filed one quietly becomes the agent's truth.
"""

from __future__ import annotations

import re

# Words that open a question or a command — a sentence starting with
# one of these is never a stated fact.
_QUESTION_OPENERS = (
    "what",
    "who",
    "whom",
    "when",
    "where",
    "why",
    "how",
    "is",
    "are",
    "was",
    "were",
    "do",
    "does",
    "did",
    "can",
    "could",
    "would",
    "should",
    "will",
    "shall",
    "may",
    "don't",
    "dont",
    "never",
)

# A "remember" body starting with one of these is a request or a
# question about remembering, not a fact to file.
_NOT_A_FACT_OPENERS = ("to ", "what", "when", "where", "who", "how", "why", "if ")

_REMEMBER_RE = re.compile(r"(?i)^(?:please\s+)?remember\s+(?:that\s+)?(.+)$")
_DECLARATION_RE = re.compile(r"(?i)\bmy\s+([a-z][a-z0-9'\- ]*?)\s+is\s+(.+)$")
_THING_WORD_RE = re.compile(r"[a-z][a-z0-9'\-]*")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT_RE.split(" ".join(text.split()))
    return [part.strip() for part in parts if part.strip()]


def _opens_with_question(sentence_lowered: str) -> bool:
    first = sentence_lowered.split(" ", 1)[0].strip(",")
    return first in _QUESTION_OPENERS


def _from_remember(sentence: str) -> str | None:
    match = _REMEMBER_RE.match(sentence)
    if match is None:
        return None
    body = match.group(1).strip()
    if not body or body.lower().startswith(_NOT_A_FACT_OPENERS):
        return None
    return body


def _from_declaration(sentence: str) -> str | None:
    match = _DECLARATION_RE.search(sentence)
    if match is None:
        return None
    thing = " ".join(match.group(1).split()).lower()
    value = match.group(2).strip()
    words = thing.split(" ")
    if not 1 <= len(words) <= 5:
        return None
    if any(_THING_WORD_RE.fullmatch(word) is None for word in words):
        return None
    if len(value) < 2 or "?" in value:
        return None
    if value.lower().startswith(("what ", "when ", "where ", "who ", "how ", "why ")):
        return None
    return f"my {thing} is {value}"


def _from_sentence(sentence: str) -> str | None:
    cleaned = sentence.rstrip(".!").strip()
    if not cleaned or cleaned.endswith("?"):
        return None
    lowered = cleaned.lower()
    if _opens_with_question(lowered):
        return None
    return _from_remember(cleaned) or _from_declaration(cleaned)


def extract_facts(text: str) -> list[str]:
    """Candidate facts stated in one user message, in order.

    Returns an empty list for anything that is not an explicit
    "remember ..." statement or a simple "my <thing> is <value>"
    declaration.
    """
    facts: list[str] = []
    for sentence in _sentences(text):
        fact = _from_sentence(sentence)
        if fact is not None and fact not in facts:
            facts.append(fact)
    return facts
