import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { fileURLToPath, URL } from "node:url";
import test from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";

const entry = fileURLToPath(new URL("../dist/main.js", import.meta.url));

test(
  "stdio handshake, ping, empty discovery, and unavailable tools",
  { timeout: 10000 },
  async () => {
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [entry],
      env: {},
      stderr: "pipe",
    });
    const client = new Client({ name: "foundation-test", version: "0.0.0" });
    let diagnostics = "";
    transport.stderr?.on("data", (chunk) => {
      diagnostics += chunk;
    });
    try {
      await client.connect(transport);
      assert.deepEqual(client.getServerVersion(), {
        name: "edgeeagle",
        version: "0.0.0",
      });
      assert.deepEqual(client.getServerCapabilities(), { tools: {} });
      assert.match(client.getInstructions(), /Foundation only/);
      assert.deepEqual(await client.ping(), {});
      assert.deepEqual(await client.listTools(), { tools: [] });
      await assert.rejects(
        client.callTool({ name: "evaluate_parlay", arguments: {} }),
        (error) =>
          error instanceof McpError && error.code === ErrorCode.InvalidParams,
      );
      assert.deepEqual(await client.ping(), {});
      assert.equal(diagnostics, "");
    } finally {
      await client.close();
    }
  },
);

test(
  "stdin EOF exits cleanly without stdout chatter",
  { timeout: 5000 },
  async () => {
    const child = spawn(process.execPath, [entry], {
      env: {},
      stdio: ["pipe", "pipe", "pipe"],
    });
    let output = "";
    let errors = "";
    child.stdout.on("data", (chunk) => {
      output += chunk;
    });
    child.stderr.on("data", (chunk) => {
      errors += chunk;
    });
    const closed = once(child, "close");
    try {
      child.stdin.end();
      const [code, signal] = await closed;
      assert.equal(code, 0);
      assert.equal(signal, null);
      assert.equal(output, "");
      assert.equal(errors, "");
    } finally {
      if (child.exitCode === null) child.kill();
    }
  },
);
