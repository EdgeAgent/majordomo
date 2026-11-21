# Security policy

## The model in one paragraph

Majordomo is a single-user, local-first agent. It is designed to run on
a machine its user controls, bound to `127.0.0.1` by default, and to be
reached remotely only over a private network the user operates (the
README's Tailscale Serve setup). It has no accounts and no multi-user
permission system — do not expose it to the public internet.

## What protects you

- **The approval gate.** Acting tools (writes, document creation,
  scheduling, mail sending, image generation, non-read-only MCP
  tools) run only with the run's approval.
- **The workspace sandbox.** File and document tools resolve every path
  against one workspace directory and refuse escapes; the test suite
  attacks it with `..`, absolute paths, and symlinks.
- **Plain-file state.** Memory, sessions, and schedules are files you
  can inspect, back up, and delete. Secrets are never written to them
  by Majordomo itself.
- **Your keys stay yours.** Provider keys come from your environment
  and are sent only to the endpoint you configured.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository, or contact
the maintainer through the Edge Agency site. Please do not file public
issues for vulnerabilities that could put a running instance at risk.

## Supported versions

Only the latest release line is supported with security fixes.
