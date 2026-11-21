# Majordomo, Codync, and the hosted bot apps

Three different answers to the same question — *how do I get AI agents
to do useful work for me, and reach them from my phone?* — compared
honestly, including where Majordomo loses.

## The contenders

- **Majordomo** (this repo) — a self-hosted personal agent with its
  own brain (any provider key, or a local model), plain-file memory,
  an approval gate, and a bridge to the agent CLIs you already have.
- **Codync** ([github.com/leepokai/Codync](https://github.com/leepokai/Codync),
  Apache-2.0, Rust) — turns the coding-agent CLIs installed on your
  computer (Claude Code, Codex, Gemini CLI, Cursor, Copilot,
  OpenCode, and dozens more) into persistent named bots you message
  from your phone. The bots run under your existing subscriptions;
  approvals and "needs you / done" notifications arrive as cards in
  its native apps.
- **Hosted bot apps** — the subscription services: a polished app, a
  hosted model, your data on their servers.

## The long table

|  | Majordomo | Codync | Hosted bot apps |
| --- | --- | --- | --- |
| Price | Free | Free | Subscription |
| License | MIT | Apache-2.0 | Proprietary |
| Open source | ✓ | ✓ | ✗ |
| Runs on your machine | ✓ | ✓ | ✗ |
| Its own model brain | ✓ — any key (9 providers) or local Ollama | ✗ — it has no brain of its own; it hosts other agents | ✓ — theirs, not yours to choose |
| Brings your own agent CLIs | ✓ — 7 known CLIs via `delegate_task` | ✓ — ~40 CLIs, persistent bots | ✗ |
| Brings your own model key | ✓ | ✗ (not applicable — no brain) | ✗ |
| Approval gate | ✓ — every acting tool, delegations included | ✓ — approval cards in the app | varies |
| Memory in plain files | ✓ — Markdown + JSON in one folder, readable and editable | ✗ — bot state lives in its own app data | ✗ |
| Per-bot memory | ✓ — each character keeps `notes.md` + a full transcript | ✓ — persistent bots with their own context | varies |
| Native phone apps | ✗ — a responsive web window over your private network (Tailscale) | ✓ — native apps are its home turf | ✓ |
| Group chats of bots | ✗ — Domo delegates one task to one teammate at a time | ✓ — bots share rooms and threads | varies |
| Notifications | ✓ — webhook out (ntfy-style / any JSON POST receiver) | ✓ — in-app cards and pushes | ✓ |
| Voice calls | ✗ | ✗ | varies |
| MCP | ✓ — client and server | ✗ | ✗ |
| Non-coding life admin (memory, reminders, mail, briefs, documents) | ✓ — that's the core product | ✗ — coding bots only | varies |

## Where each one wins

**Codync wins** if your life is the coding CLIs: it knows far more of
them, its bots are persistent conversationalists in native apps, they
can share group chats, and its approval cards are a nicer phone
experience than a web window. If you want to *chat with Claude Code
from the couch*, Codync is the more direct tool.

**Hosted apps win** on setup: install, subscribe, done. You pay for
that with your data living on their servers and your model being
their choice.

**Majordomo wins** when the job is bigger than coding: remembering
your life in files you own, keeping your schedule, working your
inbox, writing the brief — with a brain you choose, and the coding
CLIs as teammates it can delegate to when code is what's needed. One
agent, one folder, no account.

## What we borrowed from Codync, with credit

Majordomo 0.7's teammates release exists because Kevin — Majordomo's
author — saw Codync and said "add whatever the hell it has." Three
patterns were borrowed, and re-implemented clean-room in Python from
the ideas, not the code (Codync is Rust; no Codync code is in this
repository):

1. **Teammates.** Installed agent CLIs presented as persistent named
   bots you delegate to, running under your own subscriptions.
   Majordomo's version: the `delegate_task` tool + the registry in
   `src/majordomo/teammates.py`.
2. **Characters.** A bot is a *someone* — a name, a role, a home of
   its own with a memory of past runs. Majordomo's version: each
   character keeps `teammates/<name>/` with a character card, a
   transcript, and a `notes.md`. Since 0.7.1 the characters also
   have faces: a cast portrait of the team ("the friends") supplied
   by Kevin lives at `assets/friends-cast.jpg`, with a cropped face
   per character under `assets/faces/` — Copilot and Aider aren't
   in the portrait yet and keep their initial avatars.
3. **"Needs you / done" notifications.** The agent taps your shoulder
   when something needs you instead of waiting for you to check in.
   Majordomo's version: initiative digests and escalations POSTed to
   your own webhook (`src/majordomo/notify.py`).

The differences are deliberate, and listed in the table above:
Majordomo delegates one-shot headless runs (no persistent sessions,
no group chat, no native apps) because its centre of gravity is the
personal-agent side — memory, schedule, mail, documents — with the
coding team on call. Credit where due: the teammates idea is
Codync's, and it's a good one.
