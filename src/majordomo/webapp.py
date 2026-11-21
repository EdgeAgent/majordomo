"""The web app: one chat page plus a small JSON API.

FastAPI serves a single self-contained HTML page (no build step, works
on a phone browser) and four endpoints:

- ``GET  /health``   — liveness, provider name
- ``POST /chat``     — {message, session_id?, approve} → {session_id, reply, events}
- ``GET  /sessions`` — session summaries
- ``GET  /memory``   — long-term memory entries

Approvals ride on the request: ``approve: true`` approves acting tools
for that one message; without it, acting tools are declined and the
agent says so. A background tick fires due reminders into the
``inbox`` session every 30 seconds.

Reach it from a phone with Tailscale Serve — see the README.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

log = structlog.get_logger(__name__)

from . import __version__
from .config import Settings
from .providers import Provider
from .runtime import Runtime, build_runtime
from .tools import approve_all, approve_none

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Majordomo</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; font-family: system-ui, sans-serif; background: #060A14; color: #E8EAF0; }
  header { padding: 14px 18px; border-bottom: 2px solid #E8B84B; display: flex;
           justify-content: space-between; align-items: baseline; }
  header h1 { font-size: 20px; margin: 0; color: #E8B84B; letter-spacing: .04em; }
  header span { color: #2DD4BF; font-size: 12px; }
  #log { padding: 16px 18px 120px; max-width: 760px; margin: 0 auto; }
  .msg { margin: 10px 0; padding: 10px 14px; border-radius: 12px; white-space: pre-wrap;
         line-height: 1.45; }
  .user { background: #111B36; margin-left: 12%; }
  .agent { background: #0D1526; border: 1px solid #22304F; margin-right: 12%; }
  .tool { color: #8FA3C8; font-size: 12px; margin: 2px 0 2px 8px; }
  form { position: fixed; bottom: 0; left: 0; right: 0; background: #0A1120;
         padding: 12px; display: flex; gap: 8px; border-top: 1px solid #22304F; }
  input[type=text] { flex: 1; padding: 12px; border-radius: 10px; border: 1px solid #22304F;
                     background: #111B36; color: #E8EAF0; font-size: 16px; }
  button { padding: 12px 18px; border-radius: 10px; border: 0; background: #E8B84B;
           color: #060A14; font-weight: 700; font-size: 16px; }
  label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #8FA3C8; }
</style>
</head>
<body>
<header><h1>MAJORDOMO</h1><span>self-hosted · on your machine</span></header>
<div id="log"></div>
<form id="composer">
  <input type="text" id="text" placeholder="Ask Majordomo…" autocomplete="off">
  <label><input type="checkbox" id="approve"> approve actions</label>
  <button type="submit">Send</button>
</form>
<script>
  const log = document.getElementById('log');
  let sessionId = null;
  function add(text, cls) {
    const div = document.createElement('div');
    div.className = cls; div.textContent = text;
    log.appendChild(div); window.scrollTo(0, document.body.scrollHeight);
  }
  document.getElementById('composer').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = document.getElementById('text');
    const text = input.value.trim(); if (!text) return;
    add(text, 'msg user'); input.value = '';
    const res = await fetch('/chat', { method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ message: text, session_id: sessionId,
        approve: document.getElementById('approve').checked }) });
    const data = await res.json();
    sessionId = data.session_id;
    for (const ev of data.events) {
      if (ev.kind === 'tool_call') add('⚙ ' + ev.text, 'tool');
      if (ev.kind === 'declined') add('⛔ ' + ev.text, 'tool');
    }
    add(data.reply, 'msg agent');
  });
</script>
</body>
</html>
"""


class ChatRequest(BaseModel):
    """One chat message from the page (or any API client)."""

    message: str
    session_id: str | None = None
    approve: bool = False


def create_app(settings: Settings | None = None, provider: Provider | None = None) -> FastAPI:
    """Build the FastAPI app around one runtime."""
    settings = settings or Settings()
    runtime: Runtime = build_runtime(settings, provider=provider)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async def tick() -> None:
            while True:
                await asyncio.sleep(30)
                try:
                    fired = runtime.schedules.fire_due(datetime.now(UTC))
                    for reminder in fired:
                        runtime.sessions.append(
                            "inbox",
                            {
                                "role": "assistant",
                                "content": f"⏰ Reminder: {reminder.text}",
                            },
                        )
                except Exception:  # the tick must never kill the app; it logs instead
                    log.exception("scheduler.tick_failed")

        task = asyncio.create_task(tick())
        yield
        task.cancel()
        runtime.close()

    app = FastAPI(title="Majordomo", version=__version__, lifespan=lifespan)
    app.state.runtime = runtime

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "provider": runtime.provider.name}

    @app.post("/chat")
    def chat(request: ChatRequest) -> dict[str, Any]:
        result = runtime.agent.run(
            request.session_id,
            request.message,
            approver=approve_all if request.approve else approve_none,
        )
        return {
            "session_id": result.session_id,
            "reply": result.text,
            "events": [{"kind": e.kind, "text": e.text, "tool": e.tool} for e in result.events],
        }

    @app.get("/sessions")
    def sessions() -> list[dict[str, Any]]:
        return runtime.sessions.list_sessions()

    @app.get("/memory")
    def memory() -> list[dict[str, str]]:
        return [{"id": e.id, "kind": e.kind, "text": e.text} for e in runtime.memory.list()]

    return app
