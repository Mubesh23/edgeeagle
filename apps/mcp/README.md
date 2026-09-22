# MCP foundation

Local stdio protocol shell using the official MCP TypeScript SDK. It supports
initialization, ping, and an empty tools/list response. All tool calls are rejected
with InvalidParams. No research, portfolio, parlay, or execution tool is implemented.
It opens no HTTP listener and makes no API, provider, model, or cloud calls.

## Build and launch

From repository root:

```sh
scripts/bootstrap
scripts/build
node apps/mcp/dist/main.js
```

The process waits for MCP messages on stdin; an empty terminal is expected.
For a local MCP client, configure the Node executable as its command and the
absolute checkout path to apps/mcp/dist/main.js as its argument. Launch Node
directly, not a package-manager script that may print banners to stdout.
No client configuration is installed automatically.

stdout is reserved for protocol messages. Diagnostics go to stderr without
request payloads. stdin EOF, SIGINT, and SIGTERM close the server. There are no
credentials or environment variables to configure in this increment.

Root checks include ESLint, strict TypeScript, build, and subprocess tests.
The tests use an official SDK client to initialize the actual stdio executable,
ping, discover the empty tool list, reject a future tool call, and ping again.
A separate subprocess test verifies quiet, clean exit on stdin EOF.
Tests do not require a running backend or network services.

Ignored dist/ output is generated from src/ and tsconfig.json by scripts/build.
No generated API-client dependency is added until a real backend capability is
adapted. Future tools must use the authoritative API boundary, not implement
probabilities, prices, risk, settlement, or execution locally.

This is not a remote MCP deployment or production authentication design. HTTP
transport, client authentication, business tools, and agent integrations remain
future work. The choice of stdio here is only a local foundation transport.

Reference: [official TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk/tree/v1.x).
