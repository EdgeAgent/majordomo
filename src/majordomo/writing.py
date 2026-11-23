"""Writing tools: strip the AI tells, measure a voice.

Two small, honest, rule-based tools (the pattern popularised by
"unslop"-style writing skills — no model calls, no magic):

- ``writing_clean`` runs a text through a fixed set of replacements:
  filler openers ("Certainly!", "It's worth noting that…"), stock
  AI phrases ("in today's fast-paced world"), the delve/leverage/
  utilize class of words, and em-dash overuse. Every rule is a plain
  substitution listed in this file — what it does is exactly what
  you can read here, and it returns the cleaned text only. It is a
  transform, not a send path: nothing is published or mailed.
- ``writing_voice`` measures sample texts: sentence count, average
  sentence length, and contraction rate — the simple stats that
  describe a voice — and, given a draft, reports the draft's stats
  next to the samples' so drift is visible.

Both tools are read-only: cleaning returns text for the owner to
use; it changes nothing on disk.
"""

from __future__ import annotations

import re

from .tools import Tool, ToolRegistry

# Stock openers stripped when they start the text.
_OPENERS = re.compile(
    r"^(?:certainly|absolutely|sure thing|great question|of course)[!.]\s*", re.IGNORECASE
)

# (pattern, replacement) — applied in order, case-insensitively; a
# capitalised match at a sentence start keeps its capital.
_PHRASES: list[tuple[str, str]] = [
    (r"in today's fast-paced world,\s*", ""),
    (r"in the ever-evolving landscape of\s+", "in "),
    (r"it(?:'s| is) worth noting that\s+", ""),
    (r"needless to say,\s*", ""),
    (r"delve into", "dig into"),
    (r"\bdelve\b", "dig"),
    (r"\bleverage\b", "use"),
    (r"\butilize\b", "use"),
    (r"\bfurthermore,\s*", "also, "),
    (r"\bmoreover,\s*", "also, "),
    (r"\bin order to\b", "to"),
    (r"\bdue to the fact that\b", "because"),
    (r"\ba wide range of\b", "many"),
    (r"\bwhen it comes to\b", "for"),
]

_EM_DASH = re.compile(r"\s*(?:—|--)\s*")


def _apply_phrase(text: str, pattern: str, replacement: str) -> str:
    def swap(match: re.Match[str]) -> str:
        found = match.group(0)
        out = replacement
        if out and found[:1].isupper():
            out = out[:1].upper() + out[1:]
        return out

    return re.sub(pattern, swap, text, flags=re.IGNORECASE)


def _tidy(text: str) -> str:
    text = re.sub(r"\s+([,.;!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"(^|[.!?]\s+),\s*", r"\1", text)
    # A removal at a sentence start can leave it lower-case; restore.
    text = re.sub(
        r"(^|[.!?]\s+)([a-z])",
        lambda m: m.group(1) + m.group(2).upper(),
        text.strip(),
    )
    return text


def clean_text(text: str) -> str:
    """Return ``text`` with the stock AI tells stripped out."""
    out = _OPENERS.sub("", text.strip())
    for pattern, replacement in _PHRASES:
        out = _apply_phrase(out, pattern, replacement)
    out = _EM_DASH.sub(", ", out)
    return _tidy(out)


_SENTENCE_SPLIT = re.compile(r"[.!?]+")
_CONTRACTION = re.compile(r"\b\w+'(?:t|s|re|ve|ll|d|m)\b", re.IGNORECASE)
_WORD = re.compile(r"[\w']+")


def style_stats(samples: list[str]) -> dict[str, float | int]:
    """Simple voice stats over the sample texts combined."""
    joined = "\n".join(samples)
    words = _WORD.findall(joined)
    sentences = [s for s in _SENTENCE_SPLIT.split(joined) if s.strip()]
    contractions = _CONTRACTION.findall(joined)
    word_count = len(words)
    sentence_count = len(sentences)
    return {
        "samples": len(samples),
        "words": word_count,
        "sentences": sentence_count,
        "avg_sentence_words": round(word_count / sentence_count, 1) if sentence_count else 0.0,
        "contractions_per_100_words": (
            round(100 * len(contractions) / word_count, 1) if word_count else 0.0
        ),
    }


def _stats_line(label: str, stats: dict[str, float | int]) -> str:
    return (
        f"{label}: {stats['words']} words, {stats['sentences']} sentences, "
        f"avg sentence {stats['avg_sentence_words']} words, "
        f"contractions {stats['contractions_per_100_words']} per 100 words"
    )


def style_report(samples: list[str], text: str = "") -> str:
    """The samples' voice stats, plus a draft's stats when given."""
    if not samples:
        return "No samples given — a voice needs at least one sample text."
    lines = [_stats_line("Samples", style_stats(samples))]
    if text:
        lines.append(_stats_line("Draft", style_stats([text])))
    return "\n".join(lines)


def register_writing_tools(registry: ToolRegistry) -> None:
    """Add writing_clean and writing_voice (both read-only)."""

    def writing_clean(text: str) -> str:
        return clean_text(text)

    def writing_voice(samples: list[str], text: str = "") -> str:
        return style_report([str(s) for s in samples], text)

    registry.register(
        Tool(
            name="writing_clean",
            description=(
                "Clean a text of common AI tells — filler openers, stock phrases, "
                "the delve/leverage/utilize class, em-dash overuse — with fixed, "
                "readable rules. Returns the cleaned text; sends nothing. Read-only."
            ),
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=writing_clean,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="writing_voice",
            description=(
                "Measure a voice from sample texts: word and sentence counts, "
                "average sentence length, contraction rate. Pass a draft as text "
                "to see its stats next to the samples'. Read-only."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "samples": {"type": "array", "items": {"type": "string"}},
                    "text": {"type": "string"},
                },
                "required": ["samples"],
            },
            handler=writing_voice,
            read_only=True,
        )
    )
