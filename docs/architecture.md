# Architecture

Majordomo is one Python process with five ideas in it. This page is the
map; the code is the territory.

## The turn, end to end

```text
you ──► CLI / web page ──► Agent.run(session, message, approver)
                              │
                              ├─ SessionStore: load history, append your message
                              ├─ Provider.chat(history, tool schemas)
                              │     ├─ tool calls? ──► ToolRegistry.call(...)
                              │     │     ├─ read-only → run
                              │     │     └─ acting → approver? run : decline (reported)
                              │     └─ text? → final reply
                              └─ SessionStore: persist everything
```

The loop runs at most `max_steps` (8) provider round trips per message.
Tool results — successes, declines, and errors alike — are appended to
the conversation as `tool` messages, so the model always works from
what actually happened.

## Components

| Module | Responsibility |
| --- | --- |
| `config.py` | `MAJORDOMO_*` settings; the data-dir layout |
| `providers.py` | The provider protocol, the preset registry, and its adapters (OpenAI-compatible, native Anthropic, Ollama, fake) |
| `self_files.py` | SOUL / IDENTITY / USER / MEMORY: seeding + prompt assembly |
| `mailtools.py` | Mail behind injectable backends (IMAP/SMTP, fake) |
| `autocapture.py` | Opt-in self-filing memory extractor |
| `initiative.py` | Mail watch + escalation, run per tick |
| `teammates.py` | The agent-CLI bridge: character registry, PATH detection, timed subprocess runs, transcripts + notes |
| `company.py` | The company layer: roster (role/goal/budget cap) + task board in `company.json`, heartbeat summary |
| `steprunner.py` | Multi-step plans through one teammate: per-step delegated runs, stop-on-failure, `runs/` journals |
| `writing.py` | Rule-based de-AI text cleaning + voice stats from samples |
| `media.py` | Muse4AI client (stdlib) + the media generation tools |
| `videoproject.py` | Video project specs (JSON scenes): validation against the workspace, ffmpeg rendering |
| `demo.py` | The scripted demo day (fake provider, canned backends) |
| `notify.py` | Outbound webhook notifications (best effort, failures swallowed) |
| `brief.py` | The deterministic morning brief |
| `goals.py` | Goals + next moves, persisted in `goals.json` |
| `mcp_server.py` | Majordomo's own tools served over stdio MCP |
| `agent.py` | The chat loop and the approval gate |
| `tools.py` | The registry: schemas out, dispatch in |
| `coretools.py` | Memory remember/recall + past-chat search tools |
| `memory.py` | Memory as Markdown files (facts / preferences / notes) |
| `sessions.py` | One JSON file per conversation; cross-session token search |
| `filetools.py` | The workspace sandbox (resolve-then-check containment) |
| `webtools.py` | Fetch + search behind injectable backends |
| `doctoolkit.py` | Office documents, lazily imported (the `documents` extra) |
| `imagetools.py` | Image backend protocol: fake PNG + OpenAI-compatible |
| `scheduler.py` | Reminder store + `fire_due(now)` firing engine |
| `mcp_client.py` | stdio MCP client: handshake, tools/list, tools/call |
| `runtime.py` | Assembly — CLI, web app, and demo all build here |
| `webapp.py` | FastAPI app, the one-window UI, the goals/files/brand endpoints, the 30-second scheduler + initiative tick |
| `cli.py` | The `majordomo` commands |

## Providers

The agent speaks one internal message shape (OpenAI-style dicts) and
each provider adapter translates to its wire format. Selection is
`auto` by default: the first hosted key set wins (see the preset
registry in `providers.py`), then a configured local Ollama, then the
offline fake.

- **OpenAI-compatible** — `POST /chat/completions`; tool-call arguments
  arrive as JSON strings and are parsed defensively. One parameterized
  adapter serves every compatible preset (OpenAI, DeepSeek, Gemini,
  OpenRouter, Groq, Mistral, xAI, Together).
- **Anthropic** — a native Messages API adapter, whose wire shape
  genuinely differs (top-level system prompt, `tool_use` /
  `tool_result` blocks).
- **Ollama** — `POST /api/chat`, non-streaming; tool calls arrive as
  structured `message.tool_calls`. Local, keyless.
- **Fake** — scripted responses for tests, plus a small deterministic
  intent matcher for the demo. It labels itself in every fallback reply.

Live adapters retry twice with backoff (tenacity) and convert transport
failures into `ProviderError` with a human explanation, which the agent
reports rather than hides.

## The approval gate

A `Tool` carries `read_only: bool`. The agent's rule is total:

- read-only tools always run;
- acting tools run only if the run's *approver* — a callable
  `(name, arguments) -> bool` — returns true.

Approvers by surface: interactive CLI → a per-call prompt; web API →
the request's `approve` flag; demo → approve-all, safe because every
backend is a fake; tests → explicit fakes. MCP tools inherit the rule:
`readOnlyHint: true` maps to read-only, everything else is acting.

## State

Everything persistent lives under the data directory and is plain
files: Markdown for memory and the self files, JSON for sessions,
schedules, and goals, and the workspace for files the agent makes. There is no database to migrate
and nothing to export — copying the folder copies the agent's life.

## The scheduler

`ScheduleStore.fire_due(now)` is a pure function of the store and the
clock, which is why tests drive it with a fake clock. One-time
reminders fire once and are marked done; daily/weekly reminders fire
and advance by whole intervals until their next due time is in the
future. Two callers fire it: `majordomo schedule run-due` (cron-shaped)
and the web app's background tick, which appends fired reminders to the
`inbox` session.

## Teammates

`teammates.py` is a bridge to the coding-agent CLIs installed on the
machine (Claude Code, Codex, Gemini CLI, OpenCode, Cursor, Copilot,
Aider). Each known CLI is a `AgentCLI` registry entry — a character
(display name, role, avatar initial/colour), a binary name, and a
non-interactive argv template with a `{task}` placeholder. Detection
is `shutil.which`; a run is one `subprocess.run` (never a shell) with
the task as a single argument, the workspace as cwd, captured output
truncated to its last ~8,000 characters, and a hard timeout that
kills the process. Every run is recorded in the character's home
(`teammates/<slug>/`: `character.json`, `transcript.jsonl`,
`notes.md`).

The bridge surfaces to the agent as exactly one tool,
`delegate_task`, classified **acting** — so the approval gate covers
it with no special cases. Registration is conditional (see
`runtime.py`): teammates enabled, and a CLI detected or teammates
explicitly switched on. The teammates run under their own logins;
Majordomo passes no credentials and sets no environment for them.

## Notifications

`notify.py` is the one outbound channel: a JSON POST
(`{"title", "body", "source": "majordomo"}`) to the configured
webhook, best effort. The initiative engine calls it (through an
injected `notify_fn`) for new-mail digests and reminder escalations;
the daemon and the web app tick both inherit that wiring from the
runtime. Nothing listens on the other side — notifications are out
only.

## MCP client

`MCPClient` launches a server process and speaks newline-delimited
JSON-RPC over its stdio: `initialize` (protocol `2025-06-18`),
`notifications/initialized`, then `tools/list` / `tools/call`. A reader
thread queues stdout lines; requests match responses by id and time out
after 30 seconds. `register_mcp_tools` re-registers each remote tool in
the local registry as `<server>__<tool>` with its `inputSchema` and a
read-only flag derived from its annotations.
