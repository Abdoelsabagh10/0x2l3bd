#!/usr/bin/env node
/**
 * Read-only enforcement layer for an MCP stdio server.
 *
 * Wraps a child MCP server and enforces an allowlist in two places:
 *   1. `tools/list` responses are rewritten so write tools are never advertised
 *      to the client or the model.
 *   2. `tools/call` requests for anything outside the allowlist are answered
 *      locally with a JSON-RPC error and never reach the child process.
 *
 * JSON-RPC batches (arrays) are handled too: a batch containing any refused
 * call is not forwarded at all, and batched `tools/list` responses are filtered
 * element by element. Notifications are refused silently, as JSON-RPC requires.
 *
 * Unknown tools are denied. Keep the allowlist in sync with the upstream
 * server; a new upstream read tool stays blocked until it is added here.
 *
 * This is defence in depth, not a security boundary on its own. The upstream
 * credential must also be scoped by the service that issues it.
 */

import { spawn } from "node:child_process";
import { createInterface } from "node:readline";

/**
 * Notion MCP tools that only read. Verified against
 * @notionhq/notion-mcp-server's 24-tool catalog. The other 10 tools
 * (create-a-comment, create-a-data-source, delete-a-block, move-page,
 * patch-block-children, patch-page, post-page, update-a-block,
 * update-a-data-source, update-page-markdown) are write operations.
 */
export const NOTION_READ_ONLY_TOOLS = [
  "API-get-block-children",
  "API-get-self",
  "API-get-user",
  "API-get-users",
  "API-list-data-source-templates",
  "API-post-search",
  "API-query-data-source",
  "API-retrieve-a-block",
  "API-retrieve-a-comment",
  "API-retrieve-a-data-source",
  "API-retrieve-a-database",
  "API-retrieve-a-page",
  "API-retrieve-a-page-property",
  "API-retrieve-page-markdown",
];

function parseLine(line) {
  try {
    return JSON.parse(line);
  } catch {
    return undefined;
  }
}

function rejectCall(id, label) {
  return JSON.stringify({
    jsonrpc: "2.0",
    id: id ?? null,
    error: {
      code: -32601,
      message: `${label} is read-only; this tool call was refused`,
    },
  });
}

/**
 * Build a stateless-per-line filter. Returns handlers plus an audit trail of
 * refused calls (names only, never arguments).
 */
export function createFilter({ allow, label = "readonly" } = {}) {
  if (!Array.isArray(allow) || allow.length === 0) {
    throw new Error("createFilter requires a non-empty allowlist");
  }
  const allowSet = new Set(allow);
  const pendingLists = new Set();
  const blocked = [];

  /** Decide one client message. */
  const processClientMessage = (msg) => {
    if (!msg || typeof msg !== "object" || Array.isArray(msg)) {
      return { forward: true, reply: null, refused: false };
    }

    if (msg.method === "tools/call") {
      const name = msg.params && msg.params.name;
      if (typeof name !== "string" || !allowSet.has(name)) {
        blocked.push(typeof name === "string" ? name : "<unnamed>");
        process.stderr.write(`[${label}] refused tools/call ${blocked.at(-1)}\n`);
        // A notification has no id and must not receive a reply.
        return { forward: false, reply: msg.id === undefined ? null : rejectCall(msg.id, label), refused: true };
      }
      return { forward: true, reply: null, refused: false };
    }

    if (msg.method === "tools/list" && msg.id !== undefined && msg.id !== null) {
      pendingLists.add(msg.id);
    }
    return { forward: true, reply: null, refused: false };
  };

  /** Filter one server message in place; returns the message to emit. */
  const processServerMessage = (msg) => {
    if (!msg || typeof msg !== "object" || Array.isArray(msg)) return msg;

    const isPendingList = msg.id !== undefined && msg.id !== null && pendingLists.has(msg.id);
    if (!isPendingList) return msg;

    pendingLists.delete(msg.id);
    const tools = msg.result && Array.isArray(msg.result.tools) ? msg.result.tools : null;
    if (!tools) return msg;

    const kept = tools.filter((tool) => tool && allowSet.has(tool.name));
    const hidden = tools.length - kept.length;
    if (hidden > 0) {
      process.stderr.write(`[${label}] hid ${hidden} non-read tool(s) from tools/list\n`);
    }
    msg.result.tools = kept;
    return msg;
  };

  return {
    blockedCalls() {
      return blocked.slice();
    },

    /** Client -> server. Returns lines to forward and lines to answer locally. */
    onClientLine(line) {
      const parsed = parseLine(line);
      if (parsed === undefined) return { toChild: [line], toClient: [] };

      if (Array.isArray(parsed)) {
        let reply = null;
        let refused = false;
        for (const item of parsed) {
          const result = processClientMessage(item);
          if (result.refused) {
            refused = true;
            reply = reply ?? result.reply;
          }
        }
        if (refused) {
          // Reject the whole batch: never forward a partially refused batch.
          return { toChild: [], toClient: reply ? [reply] : [] };
        }
        return { toChild: [line], toClient: [] };
      }

      const result = processClientMessage(parsed);
      if (result.reply) return { toChild: [], toClient: [result.reply] };
      return { toChild: result.forward ? [line] : [], toClient: [] };
    },

    /** Server -> client. Rewrites the tools catalog, forwards everything else. */
    onServerLine(line) {
      const parsed = parseLine(line);
      if (parsed === undefined) return { toClient: [line] };

      if (Array.isArray(parsed)) {
        return { toClient: [JSON.stringify(parsed.map(processServerMessage))] };
      }
      return { toClient: [JSON.stringify(processServerMessage(parsed))] };
    },
  };
}

/**
 * Run a child MCP server behind the filter, bridging stdio line by line.
 * Never returns: it exits with the child.
 */
export function runProxy({ command, args = [], env, cwd, allow, label = "readonly" }) {
  const filter = createFilter({ allow, label });
  const child = spawn(command, args, {
    cwd,
    env,
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });

  const emit = (stream, lines) => {
    for (const line of lines) {
      try {
        stream.write(`${line}\n`);
      } catch {
        // Client or child went away; shutdown handles the exit path.
      }
    }
  };

  const client = createInterface({ input: process.stdin, crlfDelay: Infinity });
  client.on("line", (line) => {
    if (!line) return;
    const { toChild, toClient } = filter.onClientLine(line);
    emit(child.stdin, toChild);
    emit(process.stdout, toClient);
  });
  client.on("close", () => {
    try {
      child.stdin.end();
    } catch {
      // Child already exited.
    }
  });

  const server = createInterface({ input: child.stdout, crlfDelay: Infinity });
  server.on("line", (line) => {
    if (!line) return;
    emit(process.stdout, filter.onServerLine(line).toClient);
  });

  child.stderr.on("data", (chunk) => process.stderr.write(chunk));

  child.on("error", () => {
    process.stderr.write(`[${label}] could not start the MCP server\n`);
    process.exit(78);
  });

  child.on("exit", (code) => {
    process.exit(code ?? 0);
  });

  let stopping = false;
  const shutdown = (code) => {
    if (stopping) return;
    stopping = true;
    try {
      child.kill();
    } catch {
      // Already gone.
    }
    process.exit(code);
  };
  process.on("SIGINT", () => shutdown(0));
  process.on("SIGTERM", () => shutdown(0));
  process.on("exit", () => {
    try {
      child.kill();
    } catch {
      // Already gone.
    }
  });
}
