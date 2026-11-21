"""Web tools: fetch a page, search the web.

Both tools sit behind injectable backends. Production uses httpx (and
DuckDuckGo's HTML endpoint for search); tests and the demo use fakes
with canned pages. A failed lookup is an honest error — the tools never
invent content to fill a gap.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qs, urlparse

import httpx

from .tools import Tool, ToolRegistry

_MAX_TEXT_CHARS = 12_000


class FetchError(RuntimeError):
    """A fetch or search failed; the message says why."""


class HttpClient(Protocol):
    """Anything that can GET a URL and return (status, body)."""

    def get(self, url: str) -> tuple[int, str]: ...


class HttpxHttpClient:
    """The real HTTP client (built lazily, on first use)."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def get(self, url: str) -> tuple[int, str]:
        if self._client is None:
            self._client = httpx.Client(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "Majordomo/0.1 (+self-hosted personal agent)"},
            )
        response = self._client.get(url)
        return response.status_code, response.text


class FakeHttpClient:
    """Canned pages for tests and the demo. Unknown URLs are errors."""

    def __init__(self, pages: dict[str, str] | None = None) -> None:
        self.pages = dict(pages or {})

    def get(self, url: str) -> tuple[int, str]:
        if url not in self.pages:
            raise FetchError(f"Fake HTTP client has no canned page for {url}.")
        return 200, self.pages[url]


class _TextExtractor(HTMLParser):
    """Strip markup down to readable text, skipping script/style."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in ("p", "div", "br", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_title:
            self.title += data
        self.parts.append(data)


def extract_text(html: str) -> tuple[str, str]:
    """Return (title, readable text) for an HTML document."""
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return parser.title.strip(), text.strip()[:_MAX_TEXT_CHARS]


def fetch_url(client: HttpClient, url: str) -> str:
    """Fetch one URL and return its title plus readable text."""
    if not url.startswith(("http://", "https://")):
        raise FetchError(f"Refusing non-HTTP URL: {url}")
    try:
        status, body = client.get(url)
    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"Fetch failed for {url}: {exc}") from exc
    if status >= 400:
        raise FetchError(f"Fetch failed for {url}: HTTP {status}.")
    if "<html" in body[:500].lower() or "<!doctype" in body[:500].lower():
        title, text = extract_text(body)
        return f"# {title}\n\n{text}" if title else text
    return body[:_MAX_TEXT_CHARS]


class SearchBackend(Protocol):
    """Anything that can answer a query with result dicts."""

    def search(self, query: str, limit: int = 5) -> list[dict[str, str]]: ...


class FakeSearchBackend:
    """Deterministic canned results, clearly labelled as fake."""

    def __init__(self, results: list[dict[str, str]] | None = None) -> None:
        self._results = results

    def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        if self._results is not None:
            return self._results[:limit]
        return [
            {
                "title": f"Fake result for “{query}”",
                "url": "https://example.com/fake-result",
                "snippet": "(fake search backend) Connect a real search backend for live results.",
            }
        ]


class _DDGParser(HTMLParser):
    """Collect result links from DuckDuckGo's HTML results page."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = dict(attrs)
        if "result__a" not in attr.get("class", ""):
            return
        href = attr.get("href", "")
        parsed = parse_qs(urlparse(href).query)
        url = parsed.get("uddg", [href])[0]
        self._current = {"title": "", "url": url, "snippet": ""}

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["title"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current is not None:
            self._current["title"] = self._current["title"].strip()
            self.results.append(self._current)
            self._current = None


class DuckDuckGoSearchBackend:
    """Live search via DuckDuckGo's HTML endpoint (no key required)."""

    def __init__(self, client: HttpClient | None = None) -> None:
        self._client = client or HttpxHttpClient()

    def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        try:
            status, body = self._client.get(url)
        except Exception as exc:
            raise FetchError(f"Search failed: {exc}") from exc
        if status >= 400:
            raise FetchError(f"Search failed: HTTP {status}.")
        parser = _DDGParser()
        parser.feed(body)
        if not parser.results:
            raise FetchError("Search returned no results.")
        return parser.results[:limit]


def format_results(results: list[dict[str, str]]) -> str:
    lines = []
    for i, result in enumerate(results, 1):
        lines.append(f"{i}. {result['title']}\n   {result['url']}\n   {result['snippet']}")
    return "\n".join(lines)


def register_web_tools(registry: ToolRegistry, http: HttpClient, search: SearchBackend) -> None:
    """Add web_fetch and web_search."""

    def do_fetch(url: str) -> str:
        return fetch_url(http, url)

    def do_search(query: str) -> str:
        try:
            return format_results(search.search(query))
        except FetchError:
            raise
        except Exception as exc:
            raise FetchError(f"Search failed: {exc}") from exc

    registry.register(
        Tool(
            name="web_fetch",
            description="Fetch a web page and return its readable text.",
            parameters={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
            handler=do_fetch,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            name="web_search",
            description="Search the web and return titles, URLs, and snippets.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=do_search,
            read_only=True,
        )
    )
