"""The writing tool: strip AI tells, measure a voice."""

from __future__ import annotations

from majordomo.writing import clean_text, style_stats


def test_clean_removes_filler_and_swaps_ai_words() -> None:
    raw = "It's worth noting that we utilize a wide range of tools — each one helps."
    assert clean_text(raw) == "We use many tools, each one helps."


def test_clean_delve_and_in_order_to() -> None:
    assert (
        clean_text("Let's delve into the data in order to win.")
        == "Let's dig into the data to win."
    )


def test_clean_strips_generic_opener() -> None:
    assert clean_text("Certainly! Here is the plan.") == "Here is the plan."


def test_clean_leaves_plain_human_text_alone() -> None:
    text = "The meeting moved to Tuesday. Bring the signed form."
    assert clean_text(text) == text


def test_style_stats_shape() -> None:
    stats = style_stats(["I don't know. It's fine, we'll see."])
    assert stats["sentences"] == 2
    assert stats["words"] == 7
    assert stats["avg_sentence_words"] == 3.5
    assert stats["contractions_per_100_words"] == 42.9


def test_style_stats_empty_samples() -> None:
    stats = style_stats([])
    assert stats["words"] == 0
    assert stats["avg_sentence_words"] == 0.0
