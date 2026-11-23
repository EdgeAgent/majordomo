# Changelog

All notable changes to Majordomo are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/).

## [0.9.1] — 2026-11-23

The verification release: 0.9.0 was exercised end-to-end for the first
time — Docker image built and run, the MCP server driven over real
stdio, and the v0.9 tools used the way a user would. Four real bugs
fell out; all four are fixed here, each with a regression test.

### Fixed

- **Delegated CLIs no longer inherit Majordomo's stdin.** The teammate
  subprocess ran with the parent's stdin attached; under the MCP
  server that stdin is the protocol pipe, and `codex exec` (which
  reads a non-TTY stdin until EOF) hung a real step run to the
  timeout. Teammate runs now get `stdin=DEVNULL` — the bridge is
  non-interactive by design. ffmpeg render calls get the same fix.
- **The MCP stdio stream stays pure JSON-RPC.** structlog's default
  factory writes to stdout, so any tool that logged mid-call corrupted
  the protocol stream. `serve_stdio` now routes logging to stderr.
- **Codex delegation works outside git repos.** `codex exec` refuses
  a non-git working directory; Majordomo delegates inside its own
  sandbox directory, so every Codex run failed the trust check. The
  Codex argv now passes `--skip-git-repo-check` — Majordomo's
  approval gate and sandbox are the trust boundary.

### Verified

- **Docker**: the image builds from the shipped Dockerfile and runs —
  CLI, `serve` (health/window/goals/chat, approval gate included),
  the MCP server, and the test suite inside the container. Verified
  on Podman/buildah; the stock slim image has no ffmpeg, so video
  projects validate but do not render in it (stated in the FAQ).
- Suite: 296 tests (3 new regression tests), on the host and in the
  container. Still never run, stated plainly: a live-model
  conversation (no API key on the verification machine).

## [0.9.0] — 2026-11-23

### Added

- **The company layer** (`src/majordomo/company.py`, pattern: agent-company
  control planes). A roster and a task board over the teammates, in
  `company.json` in the data directory. Roster entries carry a role, a
  standing goal, and a budget cap — a planning figure the summary reports
  next to the agent's actual run count; Majordomo spends no money itself.
  Board tasks are queued/running/done/blocked. Tools: `company_summary`
  and `company_board` (read-only), `company_set_agent`, `company_add_task`,
  and `company_set_task_status` (acting). Queueing a task runs nothing —
  delegation still goes through the gated `delegate_task`; there is no
  second executor.
- **Step runs** (`src/majordomo/steprunner.py`, pattern: autonomous
  coding agents). The acting `run_task_steps` tool runs a multi-step plan
  through one teammate — each step an ordinary delegated run with the same
  sandbox and timeout — stops at the first failed or timed-out step, and
  writes a JSON journal of every step to `runs/` in the data directory.
- **Writing tools** (`src/majordomo/writing.py`, pattern: "unslop"
  writing skills). `writing_clean` strips stock AI tells with fixed,
  readable rules (filler openers, stock phrases, the delve/leverage/
  utilize class, em-dash overuse) and returns the cleaned text;
  `writing_voice` measures sample texts (sentence count, average sentence
  length, contraction rate) and can report a draft's stats beside the
  samples'. Both read-only; no model calls; nothing is sent anywhere.
- **Video projects** (`src/majordomo/videoproject.py`, pattern:
  programmatic video). A video described as a JSON spec — text, image,
  and audio scenes with durations — validated against the workspace
  (`video_project_validate`, read-only) and rendered to MP4 by the
  machine's ffmpeg (`video_project_render`, acting). Without ffmpeg the
  render tool says so plainly; the spec and validator work regardless.
  Scene media generation stays with the Muse4AI tools; this assembles.

### Fixed

- Documentation gap sweep: the README feature map, tools table, and
  repository layout and the architecture components table now cover every
  registered tool and module (the architecture table was also missing
  `media.py` and `demo.py` from earlier releases).

### Notes

- Still unverified, stated plainly: the Docker image has never been built
  on a Docker machine (the pip path is the verified one), and no live-model
  conversation has been run — the suite runs on the fake provider, as
  before.

## [0.8.0] — 2026-11-21

### Added

- **Media generation through Muse4AI.** Majordomo can now ask a
  locally running [Muse4AI](https://github.com/andrew-babo/muse4ai)
  app (MIT, by Andrew Babo) to generate images and videos on the
  operator's own signed-in Muse session, over that app's local REST
  API. New module `src/majordomo/media.py`: a standard-library-only
  client (`urllib` — no new dependencies) coded against Muse4AI's
  published OpenAPI contract, plus six tools. Read-only:
  `media_status` (is the app running, which Muse accounts and
  capabilities does it report), `media_list_jobs`, `media_get_job`.
  Acting, behind the approval gate like every other write:
  `media_generate_image` and `media_generate_video` (submit a job,
  then poll it to completion — a bounded wait, after which the tool
  reports the job as still running with its id, never as a fake
  success), and `media_extend_video` (extend a finished video in its
  own Muse conversation via its output asset id). The read-only
  tools are exposed by the built-in MCP server by default; the
  acting ones join only with `--allow-write`, as usual.
- **Configuration.** `MAJORDOMO_MUSE4AI_URL` (default
  `http://127.0.0.1:47821`), `MAJORDOMO_MUSE4AI_KEY` (the `msk_…`
  key created in Muse4AI's Settings → API & agent screen — sent
  only in the `Authorization` header, never logged, printed, or
  included in a tool result; a test proves it), and
  `MAJORDOMO_MEDIA_TIMEOUT` (default 300s, the generation poll
  bound). `MAJORDOMO_MEDIA=off` removes the tools entirely. With no
  key set or the app not running, the tools say exactly that —
  the same honest posture as the unconfigured mail backend.
- **Honest limits.** Muse4AI is a separate Windows desktop app and
  must be installed and running on the same machine; Majordomo
  contains none of its code and is not affiliated with Meta or with
  Muse4AI. Generations spend the operator's own Muse session
  through that app, which is why the acting tools sit behind the
  approval gate. The one contract shape Muse4AI's OpenAPI document
  leaves unspecified — the `GET /v1/jobs` list body — is parsed
  defensively (either `{"jobs": […]}` or a bare list).

## [0.7.1] — 2026-11-21

### Added

- **The friends: the team has faces.** Kevin supplied a cast
  portrait of the team — six robot characters in a row on dark
  navy — now in the repository as `assets/friends-cast.jpg`, with a
  tight crop per character under `assets/faces/` (`domo.png`,
  `claude.png`, `codex.png`, `gemini.png`, `otto.png`,
  `cursor.png`). The mapping, left to right in the portrait: teal =
  Otto (OpenCode), orange = Gemini, blue = Domo himself, purple =
  Cursor, red = Codex, white = Claude. Each mapped teammate's spec
  in `teammates.py` gained an `avatar` path (Domo's is the
  module-level `DOMO_AVATAR`), and newly written `character.json`
  cards record it. The README's "Meet the team" section shows the
  cast portrait and a face per row of the cast table.
- **Honest gap:** the portrait holds six of the eight characters —
  Copilot and Aider have no faces yet and keep their initial
  avatars (`avatar=None`) until theirs arrive. The faces are
  repository-side for now: the terminal roster stays text, the web
  window is unchanged, and Domo's canonical Roboto head (the one
  the window serves) is untouched — the portrait crop is his face
  for the repo and future surfaces, not a replacement.

## [0.7.0] — 2026-11-21

### Added

- **Teammates: your agent CLIs, as characters.** The coding-agent
  CLIs installed on the machine — Claude Code, Codex, Gemini CLI,
  OpenCode, Cursor, Copilot, Aider — become named characters with a
  role each (Claude the senior engineer, Codex the fast prototyper,
  Gemini the researcher, Otto the open-source all-rounder, Cursor
  the editor, Copilot the pair programmer, Aider the focused
  patcher), while Domo stays chief of staff. New module
  `src/majordomo/teammates.py`: detection is `shutil.which` on PATH;
  a run is the CLI's non-interactive invocation (`claude -p`,
  `codex exec`, `gemini -p`, `opencode run`, `cursor-agent -p`,
  `copilot -p`, `aider --message … --yes-always` — Aider's entry is
  marked experimental) with the task as a single argument, never a
  shell, in the sandboxed workspace, output captured (tail ~8,000
  chars), and a hard timeout that kills the process. Teammates run
  under their own logins and subscriptions — Majordomo never sees
  their credentials.
- **The `delegate_task` tool (acting).** Hands a task to a teammate
  and returns its output into the conversation. It passes the
  approval gate like every acting tool — a declined delegation runs
  nothing, and the tests prove the binary is never executed. The
  tool is registered when teammates are enabled
  (`MAJORDOMO_TEAMMATES`, default on; `off` removes it) and at least
  one known CLI is detected, or when teammates were explicitly
  switched on. Per-run timeout: `MAJORDOMO_TEAMMATE_TIMEOUT`
  (default 600s). The fake provider understands "delegate to
  <agent>: …" and "ask <agent> to …".
- **Per-character persistence.** Each character keeps a home in
  `teammates/<slug>/` in the data directory: a `character.json` card
  (name, agent, role, created date), a `transcript.jsonl` with one
  entry per run (timestamp, agent, task, exit code, output), and a
  `notes.md` each run appends a one-line outcome to — per-bot
  memory in plain files. Names resolve by registry key or display
  name ("Otto" works).
- **`majordomo agents` and `majordomo team`.** `agents` lists the
  characters with role, binary, installed status, and run counts
  from their transcripts; `team` prints the whole roster, chief of
  staff first.
- **Notifications ("needs you / done").** New module
  `src/majordomo/notify.py`: with `MAJORDOMO_NOTIFY_WEBHOOK` set,
  the initiative engine's new-mail digests and unacknowledged-
  reminder escalations are also POSTed to the webhook as
  `{"title", "body", "source": "majordomo"}` — a shape that works
  with ntfy-style servers and generic receivers. Outbound only,
  best effort (failures are logged and swallowed; a tick can never
  be broken by a dead webhook), off when unset. The daemon and the
  web app tick both inherit the wiring. `majordomo notify "title"
  "body"` sends a test notification and reports honestly (exit 1
  when unset or failed).
- **Repository presentation.** The README is restructured:
  a "Why Majordomo" bullet section, a "Meet the team" cast table,
  an honest "How it compares" table (Majordomo vs Codync vs hosted
  bot apps — including Majordomo's losses: no native apps, no group
  chat, no voice), and an FAQ (including the honest Docker answer:
  the image is not yet verified on a Docker machine). New
  `docs/compare.md` carries the long comparison and a "What we
  borrowed from Codync, with credit" note — the teammates,
  characters, and notifications patterns, re-implemented clean-room
  from the ideas, not the (Rust) code.
- Version 0.7.0 (package, `__version__`, CLI version output, MCP
  client info — the client now reads `__version__` instead of a
  hardcoded copy).

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

- **The window is a stack.** In the one-window web UI the chat text
  runs at the top, above the head; Roboto's head sits below the
  chat text with its thought bubble, and the composer (type box,
  approve actions, Send) sits below the head. The read buttons, the
  Plan · Build · Write · Check · Done steps, and the agent dots stay
  along the very bottom. Sections are stacked in the one window —
  the head never floats over the chat.
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
