# Extending Majordomo

Three extension points, three small recipes. Everything here follows
the house rules: backends behind protocols, tools classified honestly,
tests on fakes.

## Add a tool

A tool is a `Tool` (name, description, JSON-schema parameters, handler,
`read_only`) registered in a registry. Handlers take keyword arguments
matching the schema and return the string the model should see.

```python
# src/majordomo/mytool.py
from .tools import Tool, ToolRegistry


def register_my_tools(registry: ToolRegistry) -> None:
    def joke() -> str:
        return "There are only 10 kinds of people: those who read schemas and those who don't."

    registry.register(
        Tool(
            name="tell_joke",
            description="Tell a joke.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=joke,
            read_only=True,  # looking is free; anything that writes is False
        )
    )
```

Then register it in `runtime.build_runtime` next to the other
`register_*` calls, and add a test that calls it through
`registry.call(...)` — plus, if it acts, a test that a declined
approval leaves the world untouched.

**Classification is a promise.** `read_only=True` means the handler
cannot change anything a user would care about: no writes, no sends,
no state. If it can, it is acting — no exceptions for "small" writes.

## Add a provider

Implement the `Provider` protocol from `providers.py`:

```python
class MyProvider:
    name = "mine"

    def chat(self, messages, tools):
        # translate `messages` (OpenAI-shaped dicts) to your wire format,
        # call the model, and return a ProviderResponse with text and/or
        # ToolCall entries. Raise ProviderError with an honest message
        # when the call fails.
        ...
```

Wire it into `build_provider` under a new `MAJORDOMO_PROVIDER` value,
add its settings to `config.py` and `.env.example`, and test it with an
`httpx.MockTransport` client — no live calls in the suite, ever.

## Connect an MCP server

No code: write a config file and point `MAJORDOMO_MCP_CONFIG` at it.

```json
{
  "servers": {
    "my-server": {
      "command": "my-mcp-server",
      "args": ["--some", "flag"],
      "env": { "MY_SERVER_HOME": "/home/you/.my-server" }
    }
  }
}
```

Majordomo starts each server at runtime build, performs the MCP
handshake, and registers its tools as `my-server__<tool>`. Servers that
annotate tools with `readOnlyHint` get read-only treatment; everything
else passes the approval gate. A server that fails to start raises an
`MCPError` naming the server — check the command on your shell first
when that happens.

Majordomo is also a server itself: `majordomo mcp-server` serves its
own tools over stdio (read-only by default, `--allow-write` for the
acting tools), and the bundled example config points one Majordomo at
another. To build your own separate server, start with the MCP
specification and the official reference servers
(modelcontextprotocol/servers on GitHub).
