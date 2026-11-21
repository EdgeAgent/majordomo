# Changelog

All notable changes to Majordomo are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
