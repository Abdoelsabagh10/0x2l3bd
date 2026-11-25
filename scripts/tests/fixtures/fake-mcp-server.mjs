#!/usr/bin/env node
// Minimal MCP stdio server used by readonly-filter tests.
// Exposes the same 24 Notion-style tool names: 14 reads and 10 writes.

import { createInterface } from "node:readline";

import { ALL_TOOLS } from "./tool-catalog.mjs";

const send = (payload) => process.stdout.write(`${JSON.stringify(payload)}\n`);

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
rl.on("line", (line) => {
  if (!line.trim()) return;
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }

  if (msg.method === "initialize") {
    send({
      jsonrpc: "2.0",
      id: msg.id,
      result: {
        protocolVersion: "2025-06-18",
        capabilities: { tools: {} },
        serverInfo: { name: "fake-notion", version: "0.0.0" },
      },
    });
    return;
  }

  if (msg.method === "tools/list") {
    send({
      jsonrpc: "2.0",
      id: msg.id,
      result: {
        tools: ALL_TOOLS.map((name) => ({
          name,
          description: `${name} (fixture)`,
          inputSchema: { type: "object" },
        })),
      },
    });
    return;
  }

  if (msg.method === "tools/call") {
    send({
      jsonrpc: "2.0",
      id: msg.id,
      result: {
        content: [{ type: "text", text: `ok:${msg.params?.name}` }],
      },
    });
  }
});
