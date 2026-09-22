import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  McpError,
} from "@modelcontextprotocol/sdk/types.js";

/** Protocol-only foundation. Future tools must delegate to authoritative APIs. */
export function createServer() {
  const server = new Server(
    { name: "edgeeagle", version: "0.0.0" },
    {
      capabilities: { tools: {} },
      instructions:
        "Foundation only: no research, pricing, portfolio, or execution tools are available.",
    },
  );
  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: [] }));
  server.setRequestHandler(CallToolRequestSchema, async () => {
    throw new McpError(
      ErrorCode.InvalidParams,
      "No tools are available in this foundation.",
    );
  });
  return server;
}
