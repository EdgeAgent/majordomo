<p align="center">
  <img src="assets/icon.jpg" alt="Majordomo icon — Domo's robot head" width="88" height="88">
</p>

<h1 align="center">Majordomo</h1>

<p align="center">
  <strong>Your self-hosted personal AI agent — lives on your machine, remembers what matters, and gets the work done.</strong>
</p>
<p align="center">
  <img src="assets/banner.jpg" alt="Majordomo — your self-hosted personal AI agent" width="100%">
</p>
<p align="center">
  <img src="assets/dashboard.png" alt="The Majordomo window — one square: chat text at the top, the robot head below it, the type box under the head, the four read buttons, and the step row" width="88%">
  <br>
  <em>The one window, as `majordomo serve` serves it — chat text above the head, the type box below it, everything in one square. A real run on the offline demo provider: with approval ticked, the coffee fact is filed to memory through the real tool loop.</em>
</p>
<p align="center">
  <img src="assets/demo.gif" alt="Majordomo at work — checking mail, filing a fact by himself, recalling it in a new session, noticing new mail on his own, and printing a brief" width="88%">
  <br>
  <em>Domo at work — a real run on the built-in offline demo data: he checks mail, files a fact by himself, recalls it in a brand-new session, notices new mail on his own, and prints his brief.</em>
</p>



<p align="center">
  <a href="https://github.com/EdgeAgent/majordomo/actions/workflows/ci.yml"><img src="https://github.com/EdgeAgent/majordomo/actions/workflows/ci.yml/badge.svg" alt="GitHub Actions CI"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11 or newer"></a>
  <img src="https://img.shields.io/badge/Tests-fakes--first-0E9F6E" alt="Tests run on fakes: no network, no paid calls">
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker ready">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-2E7D32.svg" alt="MIT License"></a>
</p>

**Majordomo is a personal AI agent for one person: you.** It runs on your own machine — a laptop, a home server, a spare box in the corner — and it works like a good majordomo should: it remembers your preferences, keeps your schedule, does the research, drafts the documents, and asks before it does anything that matters. No account, no subscription, no cloud holding your data. Your conversations, your memory, and your files live in one folder on your disk, in formats you can open with any text editor.

It talks to **whatever model you give it a key for** — Anthropic, OpenAI, DeepSeek, Gemini, OpenRouter, Groq, Mistral, xAI, or Together — or to a **local model** (Ollama) when you'd rather nothing leave the machine, and — the party trick — it can **consume MCP servers** — any server that speaks the protocol plugs straight into it.

## Why Majordomo

The hosted personal agents are genuinely impressive, and they all share one property: *your life runs through somebody else's computer.* Your preferences, your half-finished thoughts, your 2 a.m. questions — logged on a server you don't control, under terms that can change. Majordomo takes the other side of that trade:

- **Self-hosted, single-user.** One process, one folder, on a machine you control. No account, no subscription, no cloud holding your data. It stops when you stop it.
- **Any key, any model — or your own agent subscriptions.** Bring a key for any major provider (or run a local model with Ollama), *and* delegate coding work to the agent CLIs you already pay for — Claude Code, Codex, Gemini CLI and friends — through [the team](#meet-the-team).
- **An approval gate on everything that acts.** Anything that writes, creates, schedules, sends, or runs an external program asks first. Looking is free; acting is permitted.
- **Memory in plain files you can read.** Your memory is a folder of Markdown files. Read it, edit it, back it up, delete it. If Majordomo remembers something wrong, you can fix it with a text editor — try that with a cloud profile.
- **MCP both ways.** Plug any MCP server into Majordomo, and Majordomo itself serves its tools over MCP to other agents.
- **Free and open source.** MIT-licensed, no paid tier, no telemetry. It never phones home.

## Meet the team

Domo is the chief of staff — he remembers, schedules, researches, and asks before acting. He is not the only pair of hands in the house. The coding-agent CLIs installed on your machine become **teammates**: named characters with roles, whom Domo can hand a coding task to through the acting `delegate_task` tool.

<p align="center">
  <img src="assets/friends-cast.jpg" alt="The friends — the Majordomo cast portrait: six robot characters in a row on dark navy" width="88%">
  <br>
  <em>The friends, left to right: <strong>Otto</strong> (teal), <strong>Gemini</strong> (orange), <strong>Domo</strong> (blue), <strong>Cursor</strong> (purple), <strong>Codex</strong> (red), and <strong>Claude</strong> (white). Cast art supplied by Kevin. Copilot and Aider aren't in the portrait yet — they're still waiting on their faces, and use their initial avatars until theirs arrive.</em>
</p>

| Face | Name | Who they are | Runs on |
| --- | --- | --- | --- |
| <img src="assets/faces/domo.png" alt="Domo's face — the blue robot" width="64"> | **Majordomo (Domo)** | chief of staff — delegates, remembers, asks first | Majordomo itself (any provider key, or Ollama) |
| <img src="assets/faces/claude.png" alt="Claude's face — the white robot" width="64"> | **Claude** | the senior engineer | `claude` (Claude Code) |
| <img src="assets/faces/codex.png" alt="Codex's face — the red robot" width="64"> | **Codex** | the fast prototyper | `codex` (Codex CLI) |
| <img src="assets/faces/gemini.png" alt="Gemini's face — the orange robot" width="64"> | **Gemini** | the researcher | `gemini` (Gemini CLI) |
| <img src="assets/faces/otto.png" alt="Otto's face — the teal robot" width="64"> | **Otto** | the open-source all-rounder | `opencode` (OpenCode) |
| <img src="assets/faces/cursor.png" alt="Cursor's face — the purple robot" width="64"> | **Cursor** | the editor | `cursor-agent` (Cursor) |
| — | **Copilot** | the pair programmer | `copilot` (GitHub Copilot CLI) |
| — | **Aider** | the focused patcher | `aider` (experimental — its non-interactive flags are the least battle-tested) |

How a delegation works: say *"delegate to Claude: fix the parser"* (or ask the model in your own words). `delegate_task` is an **acting** tool, so it passes the approval gate — nothing runs unapproved. The teammate runs in the sandboxed workspace via its CLI's non-interactive mode (`claude -p`, `codex exec`, `gemini -p`, `opencode run`, `cursor-agent -p`, `copilot -p`, `aider --message … --yes-always`), with a hard timeout (`MAJORDOMO_TEAMMATE_TIMEOUT`, default 600s; a run that overruns is stopped). Its output comes back into the conversation, and the run is recorded in the character's home — `teammates/<name>/` in the data directory: a `character.json` card, a `transcript.jsonl` of every run, and a `notes.md` where each run appends a one-line outcome. Per-character memory, in plain files, like everything else here.

**Honest notes.** The bridge uses each CLI's headless one-shot mode — there is no ACP/session protocol, no shared group chat where the bots talk to each other, and no streaming of a run in progress; a delegation is a task handed over and a result handed back. Teammates run under **their own logins and subscriptions** — Majordomo never sees, stores, or passes their credentials; it only starts the program you already installed. Detection is a PATH lookup: `majordomo agents` shows the cast with installed status and run counts, `majordomo team` prints the roster. Set `MAJORDOMO_TEAMMATES=off` to remove the tool entirely.

## How it compares

Majordomo's teammates were inspired by [Codync](https://github.com/leepokai/Codync), which pioneered turning installed agent CLIs into persistent phone-reachable bots. The longer comparison — and what we borrowed, with credit — lives in [`docs/compare.md`](docs/compare.md).

|  | Majordomo | Codync | Hosted bot apps |
| --- | --- | --- | --- |
| Price | Free (MIT) | Free (Apache-2.0) | Subscription |
| Open source | ✓ | ✓ | ✗ |
| Runs on your machine | ✓ | ✓ | ✗ (their cloud) |
| Brings your own agent CLIs | ✓ (7 known CLIs) | ✓ (~40 CLIs) | ✗ |
| Brings your own model key | ✓ (9 providers + Ollama) | ✗ — it has no brain of its own; it hosts other agents | ✗ (their model) |
| Memory in plain files | ✓ (Markdown you can read and edit) | ✗ | ✗ |
| Native phone apps | ✗ (responsive web window over your private network) | ✓ | ✓ |
| Group chats of bots | ✗ (Domo delegates one task at a time) | ✓ | varies |
| Voice calls | ✗ | ✗ | varies |

## What you can do

- **Chat** in the terminal or in the one-window web UI (it works on your phone too) — ask questions, give jobs, get answers with the tool calls shown, not hidden.
- **Be remembered, explicitly.** Say "remember that my favourite coffee is a double espresso" and it's a line in a file you own. Ask next week, in a *different* conversation, and Majordomo recalls it. Nothing is captured silently — memory is written only through the remember tool or the `memory` CLI, unless you opt in to self-filing (below).
- **Research the web**: search plus readable page fetches, with failures reported as failures — never invented content.
- **Get documents made**: Word briefs, PowerPoint decks, and Excel sheets, created and read back inside a sandboxed workspace the agent cannot escape.
- **Set reminders** — one-time or daily/weekly — that fire into your chat inbox on schedule.
- **Track goals** — the window's Goal read keeps your goals with a next move on each: add one, update its next move, tick it done. They persist in `goals.json` in the data directory.
- **Generate images** through a pluggable backend (a placeholder backend ships; live generation uses your own provider key).
- **Work your inbox** — list, read, and search email, save drafts into the workspace, and send (sending is an acting tool: it asks first). Standard-library IMAP/SMTP behind the `MAJORDOMO_MAIL_*` settings; offline runs get a seeded fake mailbox, and an unconfigured live run says so instead of pretending.
- **Run always-on** — `majordomo daemon` ticks the scheduler forever, firing due reminders into your inbox session with no window open. Service files for systemd and Windows Task Scheduler ship in `deploy/` (see `docs/always-on.md`).
- **File its own facts — only if you opt in.** With `MAJORDOMO_AUTO_MEMORY=true`, simple statements in your own messages ("my favourite coffee is ...", "remember ...") are filed to memory after the turn. The extractor is deliberately narrow: questions, commands, and chit-chat are never filed. Off by default.
- **Delegate to teammates** — hand a coding task to Claude, Codex, Gemini, Otto, Cursor, Copilot, or Aider (whichever CLIs are installed) with the approval-gated `delegate_task` tool; the result comes back into the conversation and lands in that character's transcript and notes. See [Meet the team](#meet-the-team).
- **Plug in MCP servers** — point Majordomo at a JSON config and every tool those servers expose joins the registry, approval gate included. The example config points Majordomo at a second Majordomo — it is an MCP server itself (`majordomo mcp-server`).
- **Make media through Muse4AI** — with the Muse4AI app running on the same machine, ask for an image or a video and Majordomo queues it on your own Muse session through that app's local API, waits for it, and brings back the result (extending a finished video works too). Generations are acting tools: they ask first. See [Media through Muse4AI](#media-through-muse4ai).

## Takes initiative

A majordomo who only answers when spoken to is a search box. While the daemon (or the web app) is running, Majordomo also works the room on its own — deterministically, no model required, and read-only: it never sends mail and never touches an acting tool on its own initiative.

- **Mail watch.** Every tick polls the mailbox. A message that has never been seen before lands in your inbox session as a one-line digest — `📬 New mail from Ada Lovelace: Notes on the Analytical Engine`. The first tick only sets the baseline, so the mail already sitting there isn't "news".
- **Escalation.** A reminder that fired more than two hours ago and is still unacknowledged is surfaced once more — `⏰ Still waiting: ...` — and never again. (Acknowledged, precisely: the reminder left the schedule store because you cancelled or cleared it. Firing alone doesn't count as you having seen it.)
- **The morning brief.** `majordomo brief` assembles today from real state — active reminders with overdue ones called out, how much mail is new plus the latest subjects, and your most recent memory entries — prints it, and saves it to the workspace as `brief-YYYY-MM-DD.md`. No LLM: a template over the same stores, so it works fully offline.

The engine's memory is one small JSON file (`initiative.json` in the data directory): seen mail ids and the reminders it watched fire. Delete it and the next tick simply re-baselines.

**Notifications.** A digest in the inbox session only helps if you open the window. Set `MAJORDOMO_NOTIFY_WEBHOOK` to any URL that accepts a JSON POST and the same "needs you" lines also travel: each new-mail digest and each escalation is sent as `{"title", "body", "source": "majordomo"}` — a shape that works with ntfy-style servers, generic webhook receivers, and automation inboxes (a Make/n8n webhook URL is a fine target). It is outbound only, best effort (a dead webhook is logged, never fatal), and off when the variable is unset. Test yours any time with `majordomo notify "Test" "It works"`. See [`docs/always-on.md`](docs/always-on.md).

## Feature map

| Capability | How it works | Needs |
| --- | --- | --- |
| Chat agent loop | Provider protocol with tool calling; sessions persisted per conversation | Any provider key, or local Ollama |
| Long-term memory | `facts.md` / `preferences.md` / `notes.md` — plain files, explicit writes only | Nothing |
| Cross-session recall | Token search over past conversation files | Nothing |
| Web search + fetch | Injectable backends; live = DuckDuckGo HTML + httpx, tests/demo = fakes | Network for live use |
| Workspace files | List/read/write inside one sandboxed directory; escapes refused and tested | Nothing |
| Office documents | Create + read `.docx` / `.pptx` / `.xlsx` | The `documents` extra |
| Image generation | Backend protocol; fake PNG backend ships, OpenAI-compatible backend included | Your key for live images |
| Reminders | JSON store; `schedule run-due` CLI + the web app's background tick | Nothing |
| Mail | IMAP/SMTP tools (stdlib only) behind a backend protocol; fake mailbox offline, honest "not configured" otherwise | Your mail account for live use |
| Always-on daemon | `majordomo daemon` ticks the scheduler; systemd + Task Scheduler files in `deploy/` | Nothing |
| Initiative | Mail watch digests + one-time escalation of unacknowledged reminders, per tick; state in `initiative.json` | A running daemon or web app |
| Teammates | Installed agent CLIs as named characters; `delegate_task` runs one in the workspace (approval-gated, timed, transcribed) | The CLI itself, logged in by you |
| Media (Muse4AI) | Stdlib client for a locally running Muse4AI app; generate/extend image+video jobs on your own Muse session, polled to completion | Muse4AI installed + running on this machine, its API key |
| Notifications | Initiative digests + escalations POSTed as JSON to your webhook (`MAJORDOMO_NOTIFY_WEBHOOK`) | Any webhook receiver (ntfy-style, Make/n8n, …) |
| Morning brief | `majordomo brief` — reminders, new mail, recent memory, templated from real state | Nothing |
| Self-filing memory | Opt-in (`MAJORDOMO_AUTO_MEMORY`); a narrow extractor files stated facts after a turn | Nothing |
| MCP client | stdio JSON-RPC client; remote tools namespaced `<server>__<tool>`, `readOnlyHint` honoured | Any MCP server |
| Web UI + API | FastAPI, the one window on one self-contained page, `/chat` `/sessions` `/memory` `/goals` `/files` `/brand/*` `/self` `/self-data` `/health` | Nothing |
| Goals | `goals.json` in the data dir; CRUD from the window's Goal read or the `/goals` endpoints | Nothing |
| Phone access | The same web UI over Tailscale Serve (below) | Tailscale on both devices |

## Quick start

### Docker (the front door)

```bash
git clone https://github.com/EdgeAgent/majordomo.git
cd majordomo
docker compose up --build
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). The compose file expects a local Ollama on your host (it reaches it via `host.docker.internal`); pull a model first with `ollama pull llama3.1`. All state persists in the `majordomo-data` volume. To use a hosted model instead, set `MAJORDOMO_PROVIDER` to any preset name (e.g. `anthropic`) and that provider's `MAJORDOMO_*_API_KEY` variable in your shell or a local `.env` file — compose passes every key variable through.

### pip (the side door)

```bash
git clone https://github.com/EdgeAgent/majordomo.git
cd majordomo
python -m pip install -e ".[documents]"
majordomo serve            # web UI + API on http://127.0.0.1:8080
majordomo chat             # or just talk in the terminal
```

No model handy yet? Run the whole thing on the built-in fake provider — no server, no key:

```bash
MAJORDOMO_PROVIDER=fake majordomo demo
```

The demo walks a scripted day — research, a Word brief, a fired reminder, a memory recalled in a new session — and prints the transcript. `python scripts/demo.py` does the same with no install at all.

## Phone via Tailscale

The web UI is one responsive page, so your phone needs no app — it needs a private road to your machine. Tailscale is that road:

1. Install [Tailscale](https://tailscale.com/download) on the computer running Majordomo and on your phone; sign both into the same tailnet.
2. Start Majordomo (`docker compose up` or `majordomo serve`).
3. On the computer, expose it to your tailnet only:

   ```bash
   tailscale serve --bg --http=8081 http://127.0.0.1:8080
   ```

4. Open the URL Tailscale prints (something like `http://your-machine.your-tailnet.ts.net:8081`) in the phone's browser.

Traffic stays inside your encrypted tailnet — nothing is published to the public internet, and there are no certificates to manage. Tick **approve actions** in the page when you want Majordomo to act on a request from the couch; leave it unticked and it can look, but not touch.

## The tools, and the gate

| Tool | Does | Class |
| --- | --- | --- |
| `web_search`, `web_fetch` | Search the web; fetch a page as readable text | Read-only |
| `memory_recall`, `search_past_chats` | Search memory files; search past conversations | Read-only |
| `workspace_list`, `workspace_read`, `read_document` | Look inside the workspace; read Office files | Read-only |
| `list_reminders` | Show active reminders | Read-only |
| `mail_list`, `mail_read`, `mail_search` | List, read, and search the inbox | Read-only |
| `media_status`, `media_list_jobs`, `media_get_job` | Check the local Muse4AI app; list and inspect its generation jobs | Read-only |
| `memory_remember` | Write one entry to long-term memory | **Acting** |
| `mail_draft`, `mail_send` | Save an email draft in the workspace; send an email | **Acting** |
| `workspace_write` | Write a file in the workspace | **Acting** |
| `create_word_doc`, `create_powerpoint`, `create_spreadsheet` | Create Office documents | **Acting** |
| `generate_image` | Generate an image into the workspace | **Acting** |
| `schedule_reminder`, `cancel_reminder` | Set or cancel reminders | **Acting** |
| `delegate_task` | Hand a coding task to a teammate (an installed agent CLI) in the workspace | **Acting** |
| `media_generate_image`, `media_generate_video`, `media_extend_video` | Generate or extend media through the local Muse4AI app, on your Muse session | **Acting** |
| `<server>__<tool>` (MCP) | Whatever the connected server offers | Follows its `readOnlyHint` |

**Acting** tools run only when the run approves them: the interactive CLI asks per call, the web API takes an `approve` flag per message, and the demo auto-approves because every backend behind it is a fake. A declined call is reported to the model as declined — the agent never quietly retries its way around you.

## Memory, in the open

Memory lives in `<data dir>/memory/` as three Markdown files — `facts.md`, `preferences.md`, `notes.md` — one bullet per entry:

```markdown
# Majordomo memory — preferences

- my favourite coffee is a double espresso
```

Inspect and edit it from the CLI:

```bash
majordomo memory list
majordomo memory add fact "The workshop is in London, Ontario"
majordomo memory search coffee
majordomo memory forget preference:1
```

Automatic capture is **off** by default, by design. The write paths are the `memory_remember` tool (approval-gated) and the commands above. One opt-in exists: set `MAJORDOMO_AUTO_MEMORY=true` and a deliberately narrow extractor files simple statements from your own messages after each turn — explicit "remember ..." statements and "my <thing> is <value>" declarations, filed as facts. Questions, commands, and chit-chat are never filed, and a fact already in memory is not filed twice. If it isn't in the files, Majordomo doesn't remember it.

## Soul, identity, memory

![Majordomo's mark — a gold fingerprint](assets/fingerprint.svg)

Majordomo is not a blank chatbot with tools. Four plain files at the top of the data directory give him a soul, an identity, and a curated memory — seeded from templates on first run, never overwritten afterwards, and assembled into his system prompt on **every turn**, ahead of the conversation:

| File | What it is |
| --- | --- |
| `SOUL.md` | The persona: who he is, his voice (capable, concise, a touch formal, warm), and how he behaves — anticipate, verify before claiming, ask before acting. The approval philosophy stated as character; the agent loop still enforces it in code. |
| `IDENTITY.md` | Name (Majordomo — "Domo"), character line, vibe, and his mark: a gold fingerprint, because no two households — and no two Domos — are alike. |
| `USER.md` | The owner: name, timezone, what they care about. Ships as a template with prompts to fill in. |
| `MEMORY.md` | The curated long-term memory — Facts / People / Preferences / Commitments, distilled above the day-to-day entries in `memory/`. |

Edit a file and the next reply comes from a slightly different Majordomo. Inspect the set from the CLI with `majordomo self` (status of every file, plus the full SOUL.md), or tap the gold fingerprint in the window — the same files rendered read-only inside it, under his fingerprint mark (the standalone **`/self`** page serves them too).

### The little window

<p align="center">
  <img src="assets/window.gif" alt="Domo's living window — the robot head in the corner, a thought bubble with his status, reads for Ideas, Feed, Goal and Artifact, and the gold fingerprint opening Soul & Memory" width="72%">
  <br>
  <em>His face: a small living window — tap the head and he answers; the buttons open reads, not chat.</em>
</p>

Domo's face is a little living window in the Pocket Pip style: the robot head floating in the corner (tap him and he bounces; point near him and he leans), one thought bubble carrying his status, and the work along the bottom — Plan · Build · Write · Check · Done. The buttons open **reads**: Ideas, Feed, Goal, and Artifact, each a short briefing-style panel. The gold fingerprint opens **Soul & Memory** — the same files described above, as a read. And the Goal read is writable: type a goal, give it a **next move**, and it stays on his list until it's done.

**The window now ships in this repo.** Since 0.6.0, `majordomo serve` opens the one window as the web UI itself — one square panel with everything inside it: the living face, the chat window (the real agent loop, not a mock-up), the four reads, and Soul & Memory behind the fingerprint. The Artifact read is a files shelf: every file in the workspace, plus his brand images, listed with its type and size and downloadable in one tap. (A companion dashboard Space in the same style also exists in Domo's household — but the window's home is here, in the package.)


## MCP: plug in any server

Majordomo works both sides of MCP. As a *client*, give it a config file (see [`examples/mcp-servers.json`](examples/mcp-servers.json)):

```json
{
  "servers": {
    "majordomo": { "command": "majordomo", "args": ["mcp-server"] }
  }
}
```

```bash
MAJORDOMO_MCP_CONFIG=examples/mcp-servers.json majordomo chat
```

Majordomo launches each server over stdio, does the initialize handshake, and registers its tools as `majordomo__workspace_list` and friends. A server tool annotated `readOnlyHint` runs free; anything else passes the same approval gate as a built-in acting tool. If it speaks MCP, it plugs in.

And as a *server*: `majordomo mcp-server` serves Majordomo's own tools over stdio to any MCP client — another agent can search this one's memory, read its workspace, and use its web tools. The gate holds on this side too: only read-only tools are served unless the operator starts it with `--allow-write`. The example config above points one Majordomo at another; the server side never loads an MCP config itself, so the loop cannot recurse.

## Media through Muse4AI

Majordomo can also make pictures and videos — by asking another local app to do it. [Muse4AI](https://github.com/andrew-babo/muse4ai) (MIT, by Andrew Babo) is a Windows desktop app that queues image and video generations on **your own signed-in Muse session** and serves them over a local REST API. Majordomo's media adapter (`src/majordomo/media.py`, standard library only) talks to that API; no Muse4AI code is in this repository, and Majordomo is not affiliated with Meta or with Muse4AI — Muse4AI is the external engine, credited here and in the module.

The tools: `media_status`, `media_list_jobs`, and `media_get_job` are read-only; `media_generate_image`, `media_generate_video`, and `media_extend_video` are **acting** tools — each one spends a generation of your Muse session, so each passes the approval gate. A generation tool submits its job, polls it to completion (bounded by `MAJORDOMO_MEDIA_TIMEOUT`, default 300s), and returns the job id, the final status, and the output's asset id and signed download link. If the wait runs out, the tool says the job is still running and gives its id — never a made-up success.

Setup: install and run Muse4AI on the same machine, create a key in its **Settings → API & agent** screen, then set `MAJORDOMO_MUSE4AI_KEY` (and `MAJORDOMO_MUSE4AI_URL` if it serves somewhere other than `http://127.0.0.1:47821`). The key is sent only in the `Authorization` header — never logged, printed, or included in a tool result. Honest limits: Muse4AI must be installed and running on the same machine (it is a Windows desktop app), generations run through your Muse session via that app, and with no key set — or the app not running — the media tools say exactly that instead of pretending. `MAJORDOMO_MEDIA=off` removes the tools entirely.

## What runs where

One process does everything; the **data directory** (default `~/.majordomo`, or `/data` in Docker) holds the whole life of the agent:

```text
~/.majordomo/
├── SOUL.md · IDENTITY.md · USER.md · MEMORY.md   the self files (yours to edit)
├── memory/          facts.md · preferences.md · notes.md   (yours to edit)
├── sessions/        one JSON file per conversation         (recall searches these)
├── schedules.json   reminders
├── goals.json       goals and their next moves
├── initiative.json  initiative state: seen mail ids, fired reminders
├── teammates/       one folder per character: character.json, transcript.jsonl, notes.md
└── workspace/       the only folder the file/document tools may touch
    └── images/      generated images land here
```

The **provider** is the only piece that may leave the machine: Ollama stays local; a hosted provider sends your prompts to that provider's endpoint, with your key. Web search/fetch reach the network only when you ask a question that needs them. Architecture details live in [`docs/architecture.md`](docs/architecture.md); adding tools, providers, and MCP servers is covered in [`docs/extending.md`](docs/extending.md).

## Bring your own key

Majordomo is not married to one model company. Give it a key for **any** major provider and it uses that provider's model — just set the one variable:

| Provider | Get a key at | Variable | Default model |
| --- | --- | --- | --- |
| Anthropic | console.anthropic.com | `MAJORDOMO_ANTHROPIC_API_KEY` | `claude-sonnet-4-5` |
| OpenAI | platform.openai.com | `MAJORDOMO_OPENAI_API_KEY` | `gpt-4o` |
| DeepSeek | platform.deepseek.com | `MAJORDOMO_DEEPSEEK_API_KEY` | `deepseek-chat` |
| Gemini | Google AI Studio (aistudio.google.com) | `MAJORDOMO_GEMINI_API_KEY` | `gemini-2.5-flash` |
| OpenRouter | openrouter.ai | `MAJORDOMO_OPENROUTER_API_KEY` | `openai/gpt-4o` |
| Groq | console.groq.com | `MAJORDOMO_GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| Mistral | console.mistral.ai | `MAJORDOMO_MISTRAL_API_KEY` | `mistral-large-latest` |
| xAI | console.x.ai | `MAJORDOMO_XAI_API_KEY` | `grok-4` |
| Together | api.together.ai | `MAJORDOMO_TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| Ollama | ollama.com — runs locally, no key | — | `llama3.1` |
| Fake | built in — the offline demo provider | — | (scripted) |

**Auto-detect is the default** (`MAJORDOMO_PROVIDER=auto`): the first key that is set wins, in the table's order — Anthropic, OpenAI, DeepSeek, Gemini, OpenRouter, Groq, Mistral, xAI, Together. With no key set, a configured local Ollama is used; with neither, Majordomo runs on the fake provider and says so. Pin one provider with `MAJORDOMO_PROVIDER=deepseek` (any table name), and override any default model with `MAJORDOMO_MODEL` (e.g. `MAJORDOMO_MODEL=claude-opus-4-5`).

Run `majordomo providers` to see every provider, the variable that feeds it, and which one is active under your current settings. Keys are never printed or logged — the listing shows only "key set" / "no key", and it is your key and your bill with whichever provider you choose.

Under the hood there are two adapters: one parameterized OpenAI-compatible adapter serves every compatible endpoint (OpenAI, DeepSeek, Gemini, OpenRouter, Groq, Mistral, xAI, Together), and a native adapter speaks Anthropic's Messages API, whose wire shape genuinely differs.

## Configuration

Everything is an environment variable (or a `.env` file) — see [`.env.example`](.env.example) for the full list. The ones that matter:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAJORDOMO_DATA_DIR` | `~/.majordomo` | Where memory, sessions, schedules, and the workspace live |
| `MAJORDOMO_PROVIDER` | `auto` | `auto`, or any provider name from the table above, or `ollama` / `fake` |
| `MAJORDOMO_MODEL` | per provider | Overrides the active provider's default model |
| `MAJORDOMO_OLLAMA_BASE_URL` / `MAJORDOMO_OLLAMA_MODEL` | `http://localhost:11434` / `llama3.1` | Local model endpoint and model |
| `MAJORDOMO_*_API_KEY` | — | One per hosted provider — see [Bring your own key](#bring-your-own-key). (`MAJORDOMO_OPENAI_API_KEY` also feeds live images.) |
| `MAJORDOMO_IMAGE_BACKEND` | `fake` | `fake` (placeholder PNG) or `openai` |
| `MAJORDOMO_MCP_CONFIG` | — | Path to an MCP servers JSON file |
| `MAJORDOMO_TEAMMATES` | on | `off` removes the `delegate_task` tool entirely |
| `MAJORDOMO_TEAMMATE_TIMEOUT` | `600` | Seconds before a delegated run is stopped |
| `MAJORDOMO_NOTIFY_WEBHOOK` | — | Webhook URL for initiative notifications (unset = off) |
| `MAJORDOMO_MEDIA` | on | `off` removes the Muse4AI media tools entirely |
| `MAJORDOMO_MUSE4AI_URL` | `http://127.0.0.1:47821` | Where the local Muse4AI app serves its API |
| `MAJORDOMO_MUSE4AI_KEY` | — | API key from Muse4AI's Settings → API & agent screen (never logged or printed) |
| `MAJORDOMO_MEDIA_TIMEOUT` | `300` | Seconds a generation tool waits on its job before reporting it still running |
| `MAJORDOMO_HOST` / `MAJORDOMO_PORT` | `127.0.0.1` / `8080` | Web app bind |

## Develop and test

```bash
python -m pip install -e ".[dev,documents]"
ruff check .
ruff format --check .
pytest
```

The suite runs entirely on fakes — the fake provider, canned web pages, a fake clock for the scheduler, a placeholder image backend, and a tiny in-repo MCP server fixture — so it needs no network, no keys, and no running model. It covers the approval gate (a declined acting tool *provably* does nothing), memory recall across sessions, sandbox escape attempts, real `.docx`/`.pptx` files created and reopened, and the MCP client speaking the protocol to the fixture server. GitHub Actions runs the same checks on Python 3.11, 3.12, and 3.13.

## FAQ

**Is it free?**
Yes — MIT-licensed, no paid tier, no account. The only bills are yours: a hosted model's API usage if you bring a key, or the agent-CLI subscriptions you already have.

**Which agents and keys does it work with?**
As its brain: any of Anthropic, OpenAI, DeepSeek, Gemini, OpenRouter, Groq, Mistral, xAI, or Together by key, or a local Ollama model — see [Bring your own key](#bring-your-own-key). As teammates: Claude Code, Codex, Gemini CLI, OpenCode, Cursor, Copilot, and Aider — whichever are installed and logged in on the machine. The two are independent: Domo can think with a DeepSeek key and delegate coding to your Claude Code subscription.

**Where does my data live?**
In one folder on your machine — the data directory (`~/.majordomo` by default): Markdown memory, JSON sessions/schedules/goals, the teammates' transcripts, and the workspace. Nothing is stored anywhere else by Majordomo.

**Is Docker verified?**
Honestly: not yet. The Dockerfile and compose file ship and are maintained, but the image has not yet been built and run end-to-end on a Docker machine by the maintainer — treat the pip install as the verified path until that changes.

**Does it phone home?**
No. No telemetry, no analytics, no update checks. The only outbound traffic is what you configure: your model provider's endpoint, web search/fetch when you ask for research, your mail servers if you set them up, and your own notification webhook if you set one.

## What this does — and does not do

Majordomo is a **single-user** agent by design: no accounts, no multi-tenancy, no permission system beyond the approval gate. Run one per person, on their machine.

There is **no browser automation in v1** — no Chromium form-driving, no clicking through websites. Web research is search + readable fetch, and anything richer belongs in an MCP server you connect (that's what the protocol is for). Image generation ships with a placeholder backend; live images need your own provider key and run on your bill. The fake provider is a demo and testing tool — it pattern-matches obvious requests (now including mail checks, briefs, and look-up-and-save research) and answers the rest with a canned line that says what it is. Real conversation needs Ollama or an API key. The initiative engine and the brief are not the fake provider: they are deterministic code over real state, and they work the same with any provider.

Teammates are a bridge, not a hive mind: each delegation is one headless CLI run — no ACP protocol, no live session, no group chat where the characters talk to each other, and no progress streaming; you get the result when the run ends (or the timeout stops it). Notifications are one-way: a webhook POST out, with nothing listening for replies.

Memory recall is honest token search over your files, not embeddings: it finds what shares words with your question, and it returns nothing rather than guessing. The scheduler fires while a Majordomo listener is running: the web app ticks every 30 seconds, `majordomo daemon` ticks forever on its own, and the shipped systemd / Task Scheduler files (see `docs/always-on.md`) make that listener a real always-on service. And the approval gate is a seatbelt, not a vault: it stops the agent from acting unapproved, but the workspace sandbox and your own backups are what protect your files.

## Repository layout

```text
.
├── .github/workflows/ci.yml    # Python matrix tests and package build
├── assets/                     # Icon, banner, dashboard + window images, social preview, fingerprint mark
├── docs/                       # Architecture, the extending guide, always-on setup, the Codync comparison
├── deploy/                     # systemd unit + Windows Task Scheduler installer
├── examples/                   # Example MCP server config
├── scripts/demo.py             # Standalone demo, no install needed
├── src/majordomo/
│   ├── config.py               # MAJORDOMO_* settings
│   ├── providers.py            # Provider presets: Anthropic, OpenAI, DeepSeek, Gemini, OpenRouter, Groq, Mistral, xAI, Together, Ollama, fake
│   ├── agent.py                # The chat loop + approval gate
│   ├── tools.py                # The tool registry
│   ├── coretools.py            # Memory + recall tools
│   ├── memory.py               # Long-term memory as Markdown files
│   ├── self_files.py           # SOUL / IDENTITY / USER / MEMORY: seeding + prompt assembly
│   ├── templates/              # The shipped self-file templates (seeded on first run)
│   ├── sessions.py             # Persisted conversations + cross-session search
│   ├── filetools.py            # The sandboxed workspace
│   ├── webtools.py             # Search + fetch behind injectable backends
│   ├── mailtools.py            # Mail behind injectable backends (IMAP/SMTP, fake)
│   ├── autocapture.py          # Opt-in self-filing memory extractor
│   ├── doctoolkit.py           # Word / PowerPoint / Excel (documents extra)
│   ├── imagetools.py           # Image backends: fake + OpenAI-compatible
│   ├── scheduler.py            # Reminders and the firing engine
│   ├── initiative.py           # Mail watch + escalation, run per tick
│   ├── teammates.py            # The agent-CLI bridge: characters, detection, runs, transcripts
│   ├── media.py                # Muse4AI client (stdlib) + the media tools
│   ├── notify.py               # Outbound webhook notifications (best effort)
│   ├── brief.py                # The deterministic morning brief
│   ├── mcp_client.py           # stdio MCP client
│   ├── runtime.py              # Wiring: settings in, agent out
│   ├── goals.py                # Goals + next moves, persisted in goals.json
│   ├── mcp_server.py           # Majordomo as an MCP server (stdio)
│   ├── static/                 # Brand images served at /brand/*
│   ├── webapp.py               # FastAPI app + the one window
│   ├── cli.py                  # The majordomo CLI
│   └── demo.py                 # The scripted demo day
├── tests/                      # Fakes-first tests for all of it
├── Dockerfile / compose.yaml   # One service, one volume, port 8080
├── PUBLISHING.md               # Repo description + topics for publish time
└── pyproject.toml              # Package metadata and install profiles
```

## Contributing

Install the development profile, run the checks above, and keep the default install lean. New tools and providers follow [`docs/extending.md`](docs/extending.md): one job per tool, backends behind protocols, truthful read-only/acting classification, tests on fakes. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## The series, and the license

Majordomo stands on the Edge Agency AI Automation series: [Step 1 — the starter kit](https://github.com/EdgeAgent/ai-automation-starter) · [Step 2 — agent recipes](https://github.com/EdgeAgent/ai-automation-agents). This repository is not published to PyPI; clone it and use the editable install commands above. Released under the [MIT License](LICENSE). Publishing notes (description, topics, social preview) live in [`PUBLISHING.md`](PUBLISHING.md).
