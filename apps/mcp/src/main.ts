import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createServer } from "./server.js";

const server = createServer();
server.onerror = () => {
  // stdout belongs exclusively to MCP. Never log request payloads.
  process.stderr.write("MCP protocol error\n");
};

let stopping = false;
async function stop() {
  if (stopping) return;
  stopping = true;
  await server.close();
  process.stdin.pause();
}

process.once("SIGINT", () => void stop());
process.once("SIGTERM", () => void stop());
process.stdin.once("end", () => void stop());

try {
  await server.connect(new StdioServerTransport());
} catch {
  process.stderr.write("MCP startup failed\n");
  process.exitCode = 1;
  await stop();
}
