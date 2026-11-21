# Changelog

All notable changes to Majordomo are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- **The window is a stack.** In the one-window web UI the chat text
  now runs at the top, above the head; Roboto's head sits below the
  chat text with its thought bubble, and the composer (type box,
  approve actions, Send) sits below the head. The read buttons, the
  Plan · Build · Write · Check · Done steps, and the agent dots stay
  along the very bottom. Sections are stacked in the one window —
  the head never floats over the chat.

## [0.6.0] — 2026-11-21

### Added

- **The one window.** The web UI is now a single square window with
  everything inside it — no separate pages. `majordomo serve` opens
  the window: a slim header (head icon, MAJORDOMO wordmark, the gold
  fingerprint, an "On watch" status), the living face (Roboto's robot
  head, byte-identical to the Pocket Pip asset, floating low in the
  window — tap for a bounce and a status line, pointer for a lean,
  an occasional blink; transforms only, the image is never edited),
  one thought bubble carrying only Domo's status lines in sync with
  the Plan · Build · Write · Check · Done steps and the
  Domo · Mail · Memory · Brief · Gate agent dots, and the chat
  window — the real `/chat` agent loop, approve-actions checkbox
  included — all in the one panel.
- Reads inside the window: **Ideas** (a short worth-a-look list),
  **Feed** (recent activity from `/sessions`), **Goal** (goals CRUD,
  below), and **Artifact** — a files shelf where every workspace file
  and brand file is a working download, with the brand images shown
  as thumbnails. The gold fingerprint opens **Soul & Memory** inside
  the window (`GET /self-data`); the standalone `/self` page remains.
- Goals (`src/majordomo/goals.py`): the owner's goals with a next
  move each, persisted in `goals.json` in the data directory.
  Endpoints: `GET /goals`, `POST /goals`, `POST /goals/{id}/next-move`,
  `POST /goals/{id}/done`, `DELETE /goals/{id}`.
- The files shelf endpoints: `GET /files` lists the sandboxed
  workspace (name, size, modified) and `GET /files/{name}` downloads
  one file — resolved through the same workspace path-safety as the
  agent's file tools, so traversal attempts are refused.
- Brand statics shipped in the package (`src/majordomo/static/`,
  served at `/brand/<name>` with correct content types): the real
  `roboto-head.png`, `icon.jpg`, `banner.jpg`, `window.gif`, and
  `fingerprint.svg`.

### Changed

- Version 0.6.0 (package, `__version__`, CLI version output, MCP
  client info).

## [0.5.0] — 2026-11-21

### Added

- A soul, an identity, and a curated memory — the self files
  (`src/majordomo/self_files.py`): `SOUL.md` (the persona: voice and
  behaviour — anticipate, verify before claiming, ask before acting),
  `IDENTITY.md` (Majordomo, "Domo", and the gold fingerprint as his
  mark), `USER.md` (a template for the owner), and `MEMORY.md` (the
  curated long-term memory — Facts / People / Preferences /
  Commitments — above the per-kind entry files). All four live at the
  top of the data directory, are seeded on first run from templates
  shipped in `src/majordomo/templates/`, and are never overwritten.
  The agent assembles its system prompt from them on every turn
  (each file capped at 6,000 characters, missing files skipped),
  ahead of the conversation; `Agent.system_prompt()` exposes the
  assembled prompt.
- `majordomo self`: lists each self file's status and size and
  prints SOUL.md. The web app gains a read-only `/self` page
  rendering Soul, Identity, User, and the Memory section under the
  fingerprint mark, linked from the chat page header.
- `assets/fingerprint.svg`: Majordomo's identity mark — a stylized
  fingerprint in gold (#E8B84B) on a transparent background — also
  inlined in the `/self` page header.
- Any key, any model: a provider preset registry (`PROVIDER_PRESETS`
  in `src/majordomo/providers.py`) covering Anthropic, OpenAI,
  DeepSeek, Gemini, OpenRouter, Groq, Mistral, xAI, and Together,
  plus the local Ollama and the offline fake. Set one
  `MAJORDOMO_<NAME>_API_KEY` and that provider's model answers.
  The OpenAI-compatible adapter is now parameterized (name, base
  URL, model, key) and serves every compatible endpoint; a new
  native `AnthropicProvider` speaks the Messages API — top-level
  system prompt, `tool_use` / `tool_result` blocks, `x-api-key` +
  `anthropic-version` headers.
- Provider auto-detection: `MAJORDOMO_PROVIDER` now defaults to
  `auto` — the first set hosted key wins (Anthropic → OpenAI →
  DeepSeek → Gemini → OpenRouter → Groq → Mistral → xAI →
  Together), then an explicitly configured Ollama, then the fake.
  `MAJORDOMO_MODEL` overrides any preset's default model; the
  legacy `MAJORDOMO_OPENAI_MODEL` / `MAJORDOMO_OPENAI_BASE_URL`
  settings still win for OpenAI when set explicitly. An unknown
  provider name is now a clean `ProviderError`, not a silent
  fallthrough to Ollama. Keys are never logged or printed:
  provider reprs show only `<set>` / `<unset>`.
- `majordomo providers`: lists every provider, the environment
  variable that feeds it, its default model, whether a key is set,
  and which provider is active under the current settings.
- Initiative engine (`src/majordomo/initiative.py`): run by the
  daemon and the web app tick alongside reminder firing. A mail watch
  digests each never-before-seen message into the inbox session as a
  one-line "📬 New mail from …" note (the first tick only establishes
  the baseline), and a reminder still unacknowledged two hours after
  the engine watched it fire is re-surfaced exactly once with a
  "⏰ Still waiting" note. State (seen mail ids, fired reminders)
  lives in `initiative.json` in the data directory. The engine is
  read-only: it never sends mail and never calls an acting tool.
- `majordomo brief`: a morning brief assembled deterministically from
  real state — active reminders (overdue called out), new-mail count
  and latest subjects, and the most recent memory entries — printed
  and saved to the workspace as `brief-YYYY-MM-DD.md`. No model
  involved; works fully offline.
- A smarter fake provider: mail intents ("check my mail", "any new
  email" → `mail_list`; "search my mail for X" → `mail_search`, with
  phrase-shaped matching so mere mentions of mail don't trigger), a
  two-step brief chain ("brief me" / "what's on today" →
  `list_reminders` then `mail_list` in one turn), and a two-step
  research chain ("look up X and save it" → `web_search` then
  `workspace_write` of the result).
- Mail tools: `mail_list` / `mail_read` / `mail_search` (read-only) and
  `mail_draft` / `mail_send` (acting, approval-gated), behind an
  injectable backend — IMAP/SMTP from the standard library via the new
  `MAJORDOMO_MAIL_*` settings, a seeded fake mailbox for offline runs,
  and an honest "not configured" error when a live run has no mail
  settings. Drafts are saved as files in the workspace `drafts/` area.
- Always-on mode: `majordomo daemon` ticks the scheduler forever
  (`--interval` seconds, `--once` for a single tick), firing due
  reminders into the inbox session with no window open. Ships a
  systemd user unit (`deploy/majordomo.service`), a Windows Task
  Scheduler installer (`deploy/install-windows-task.ps1`), and
  `docs/always-on.md`.
- Self-filing memory, opt-in via the new `MAJORDOMO_AUTO_MEMORY`
  setting (off by default): after each turn, a conservative extractor
  files explicit "remember ..." statements and simple "my <thing> is
  <value>" declarations as facts. Questions, commands, and chit-chat
  are never filed, and facts already in memory are not duplicated.
- A built-in MCP server: `majordomo mcp-server` serves Majordomo's own
  tools over stdio to any MCP client. Read-only tools by default;
  `--allow-write` exposes the acting tools, the operator's explicit
  choice. The bundled example MCP config now points Majordomo at a
  second Majordomo.

## [0.1.0] — 2026-11-21

### Added

- The agent loop: provider protocol with Ollama (local default),
  OpenAI-compatible, and scripted fake providers; tool calling with the
  read-only/acting approval gate.
- Long-term memory as plain Markdown files (facts, preferences, notes)
  with explicit writes only, plus cross-session recall over persisted
  conversation files.
- Tools: web search + fetch (injectable backends), sandboxed workspace
  files, Word/PowerPoint/Excel creation and reading (the `documents`
  extra), image generation behind a backend protocol (fake PNG backend
  ships), and one-time/recurring reminders with a fake-clock-testable
  firing engine.
- An MCP client (stdio, JSON-RPC) that registers remote servers' tools
  behind the same approval gate, with an example config for the
  official filesystem reference server.
- Interfaces: the `majordomo` CLI (chat, ask, memory, schedule, serve,
  demo, version) and a FastAPI web app with a single-page chat UI, a
  JSON API, and a background reminder tick.
- Docker: Dockerfile + compose.yaml (one service, one volume, port
  8080), and a scripted demo day that runs entirely on fakes.
