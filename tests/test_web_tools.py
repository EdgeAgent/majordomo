"""Web tools: extraction, honest failures, fake labelling."""

from __future__ import annotations

import pytest

from majordomo.webtools import (
    DuckDuckGoSearchBackend,
    FakeHttpClient,
    FakeSearchBackend,
    FetchError,
    extract_text,
    fetch_url,
)

PAGE = (
    "<html><head><title>My Page</title><style>body{color:red}</style></head>"
    "<body><h1>Heading</h1><p>First paragraph.</p>"
    "<script>var secret = 1;</script><p>Second paragraph.</p></body></html>"
)


def test_extract_text_strips_script_and_style() -> None:
    title, text = extract_text(PAGE)
    assert title == "My Page"
    assert "First paragraph." in text
    assert "Second paragraph." in text
    assert "secret" not in text
    assert "color:red" not in text


def test_fetch_url_returns_title_and_text() -> None:
    client = FakeHttpClient({"https://example.com/page": PAGE})
    result = fetch_url(client, "https://example.com/page")
    assert result.startswith("# My Page")
    assert "First paragraph." in result


def test_fetch_unknown_url_is_an_honest_error() -> None:
    client = FakeHttpClient({})
    with pytest.raises(FetchError, match="no canned page"):
        fetch_url(client, "https://example.com/nope")


def test_fetch_refuses_non_http() -> None:
    client = FakeHttpClient({})
    with pytest.raises(FetchError, match="non-HTTP"):
        fetch_url(client, "file:///etc/passwd")


def test_fetch_http_error_status() -> None:
    class NotFound:
        def get(self, url: str) -> tuple[int, str]:
            return 404, "missing"

    with pytest.raises(FetchError, match="HTTP 404"):
        fetch_url(NotFound(), "https://example.com/gone")


def test_fake_search_labels_itself() -> None:
    backend = FakeSearchBackend()
    results = backend.search("anything")
    assert len(results) == 1
    assert "fake" in results[0]["snippet"].lower()


def test_fake_search_canned_results() -> None:
    canned = [{"title": "T", "url": "https://x.example", "snippet": "S"}]
    backend = FakeSearchBackend(results=canned)
    assert backend.search("q") == canned


DDG_HTML = """
<html><body>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Result A</a>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fb">Result B</a>
</body></html>
"""


def test_ddg_backend_parses_results() -> None:
    backend = DuckDuckGoSearchBackend(
        client=FakeHttpClient(
            {
                "https://html.duckduckgo.com/html/?q=test+query": DDG_HTML,
            }
        )
    )
    results = backend.search("test query")
    assert [r["title"] for r in results] == ["Result A", "Result B"]
    assert results[0]["url"] == "https://example.com/a"


def test_ddg_backend_no_results_is_an_error() -> None:
    backend = DuckDuckGoSearchBackend(
        client=FakeHttpClient(
            {
                "https://html.duckduckgo.com/html/?q=zzz": "<html><body></body></html>",
            }
        )
    )
    with pytest.raises(FetchError, match="no results"):
        backend.search("zzz")
