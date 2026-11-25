// Tests for scripts/mcp/readonly-filter.mjs
// Run: node --test scripts/tests/readonly-filter.test.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { NOTION_READ_ONLY_TOOLS, createFilter } from "../mcp/readonly-filter.mjs";
import { READ_TOOLS, WRITE_TOOLS } from "./fixtures/tool-catalog.mjs";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

const killTree = (pid) => {
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    return;
  }
  try {
    process.kill(-pid, "SIGKILL");
  } catch {
    try {
      process.kill(pid, "SIGKILL");
    } catch {
      // Already gone.
    }
  }
};

function makeFilter() {
  return createFilter({ allow: READ_TOOLS, label: "test-filter" });
}

test("notion allowlist contains every read tool and no write tool", () => {
  assert.equal(NOTION_READ_ONLY_TOOLS.length, READ_TOOLS.length);
  assert.deepEqual([...NOTION_READ_ONLY_TOOLS].sort(), [...READ_TOOLS].sort());
  for (const name of NOTION_READ_ONLY_TOOLS) {
    assert.ok(!WRITE_TOOLS.includes(name), `${name} must not be in the read-only list`);
  }
  assert.equal(new Set(NOTION_READ_ONLY_TOOLS).size, NOTION_READ_ONLY_TOOLS.length);
});

test("createFilter refuses an empty allowlist", () => {
  assert.throws(() => createFilter({ allow: [] }), /allowlist/);
  assert.throws(() => createFilter({}), /allowlist/);
});

test("tools/list is rewritten to hide write tools", () => {
  const filter = makeFilter();
  const listRequest = JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list" });

  const forward = filter.onClientLine(listRequest);
  assert.deepEqual(forward.toChild, [listRequest]);
  assert.deepEqual(forward.toClient, []);

  const serverReply = JSON.stringify({
    jsonrpc: "2.0",
    id: 2,
    result: {
      tools: [...READ_TOOLS, ...WRITE_TOOLS].map((name) => ({ name, inputSchema: { type: "object" } })),
    },
  });

  const { toClient } = filter.onServerLine(serverReply);
  assert.equal(toClient.length, 1);
  const tools = JSON.parse(toClient[0]).result.tools.map((t) => t.name);
  assert.equal(tools.length, READ_TOOLS.length);
  for (const name of WRITE_TOOLS) assert.ok(!tools.includes(name), `${name} should be hidden`);
});

test("tools/call for a write tool is answered locally and never forwarded", () => {
  const filter = makeFilter();
  const request = JSON.stringify({
    jsonrpc: "2.0",
    id: 7,
    method: "tools/call",
    params: { name: "API-delete-a-block", arguments: { block_id: "x" } },
  });

  const { toChild, toClient } = filter.onClientLine(request);
  assert.deepEqual(toChild, []);
  assert.equal(toClient.length, 1);

  const reply = JSON.parse(toClient[0]);
  assert.equal(reply.id, 7);
  assert.equal(reply.error.code, -32601);
  assert.match(reply.error.message, /read-only/);
  assert.deepEqual(filter.blockedCalls(), ["API-delete-a-block"]);
});

test("tools/call for an unknown tool is denied", () => {
  const filter = makeFilter();
  const request = JSON.stringify({
    jsonrpc: "2.0",
    id: 8,
    method: "tools/call",
    params: { name: "Future-write-tool" },
  });

  const { toChild, toClient } = filter.onClientLine(request);
  assert.deepEqual(toChild, []);
  assert.equal(JSON.parse(toClient[0]).error.code, -32601);
});

test("tools/call for a read tool is forwarded untouched", () => {
  const filter = makeFilter();
  const request = JSON.stringify({
    jsonrpc: "2.0",
    id: 9,
    method: "tools/call",
    params: { name: "API-retrieve-a-page", arguments: { page_id: "x" } },
  });

  const { toChild, toClient } = filter.onClientLine(request);
  assert.deepEqual(toChild, [request]);
  assert.deepEqual(toClient, []);
});

test("non-JSON and non-tools traffic passes through unchanged", () => {
  const filter = makeFilter();
  assert.deepEqual(filter.onClientLine("not json").toChild, ["not json"]);
  assert.deepEqual(
    filter.onServerLine('{"jsonrpc":"2.0","method":"notifications/progress"}').toClient,
    ['{"jsonrpc":"2.0","method":"notifications/progress"}'],
  );
});

test("a JSON-RPC batch containing a write call is not forwarded", () => {
  const filter = makeFilter();
  const batch = JSON.stringify([
    { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "API-delete-a-block" } },
    { jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "API-get-self" } },
  ]);

  const { toChild, toClient } = filter.onClientLine(batch);
  assert.deepEqual(toChild, [], "no part of a refused batch may reach the server");
  assert.equal(toClient.length, 1);
  assert.equal(JSON.parse(toClient[0]).error.code, -32601);
  assert.deepEqual(filter.blockedCalls(), ["API-delete-a-block"]);
});

test("a JSON-RPC batch of allowed calls is forwarded unchanged", () => {
  const filter = makeFilter();
  const batch = JSON.stringify([
    { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "API-get-self" } },
    { jsonrpc: "2.0", id: 2, method: "tools/list" },
  ]);

  assert.deepEqual(filter.onClientLine(batch).toChild, [batch]);
  assert.deepEqual(filter.blockedCalls(), []);
});

test("batched tools/list responses are filtered element by element", () => {
  const filter = makeFilter();
  filter.onClientLine(JSON.stringify({ jsonrpc: "2.0", id: 5, method: "tools/list" }));

  const response = JSON.stringify([
    { jsonrpc: "2.0", id: 5, result: { tools: [...READ_TOOLS, ...WRITE_TOOLS].map((name) => ({ name })) } },
    { jsonrpc: "2.0", id: 6, result: { ok: true } },
  ]);

  const emitted = JSON.parse(filter.onServerLine(response).toClient[0]);
  assert.equal(emitted.length, 2);
  assert.equal(emitted[0].result.tools.length, READ_TOOLS.length);
  assert.ok(!emitted[0].result.tools.some((tool) => WRITE_TOOLS.includes(tool.name)));
  assert.deepEqual(emitted[1], { jsonrpc: "2.0", id: 6, result: { ok: true } });
});

test("a refused tools/call notification gets no reply", () => {
  const filter = makeFilter();
  const notification = JSON.stringify({
    jsonrpc: "2.0",
    method: "tools/call",
    params: { name: "API-patch-page" },
  });

  const { toChild, toClient } = filter.onClientLine(notification);
  assert.deepEqual(toChild, []);
  assert.deepEqual(toClient, [], "notifications must not receive a response");
  assert.deepEqual(filter.blockedCalls(), ["API-patch-page"]);
});

test("end to end: proxy advertises reads, forwards reads, blocks writes", async () => {
  const child = spawn(process.execPath, ["scripts/tests/fixtures/run-filter.mjs"], {
    cwd: REPO_ROOT,
    stdio: ["pipe", "pipe", "pipe"],
  });

  const replies = new Map();
  const rl = createInterface({ input: child.stdout, crlfDelay: Infinity });
  const waiters = [];
  rl.on("line", (line) => {
    const msg = JSON.parse(line);
    replies.set(msg.id, msg);
    for (const wake of waiters.splice(0)) wake();
  });

  const waitFor = (id) =>
    new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => rejectPromise(new Error(`no reply for id ${id}`)), 10000);
      const check = () => {
        if (!replies.has(id)) {
          waiters.push(check);
          return;
        }
        clearTimeout(timer);
        resolvePromise(replies.get(id));
      };
      check();
    });

  const send = (payload) => child.stdin.write(`${JSON.stringify(payload)}\n`);

  try {
    send({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} });
    await waitFor(1);

    send({ jsonrpc: "2.0", id: 2, method: "tools/list" });
    const list = await waitFor(2);
    const advertised = list.result.tools.map((t) => t.name);
    assert.equal(advertised.length, READ_TOOLS.length);
    assert.ok(!advertised.includes("API-post-page"));

    send({
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: { name: "API-get-self", arguments: {} },
    });
    const allowed = await waitFor(3);
    assert.equal(allowed.result.content[0].text, "ok:API-get-self");

    send({
      jsonrpc: "2.0",
      id: 4,
      method: "tools/call",
      params: { name: "API-update-page-markdown", arguments: {} },
    });
    const denied = await waitFor(4);
    assert.equal(denied.error.code, -32601);
  } finally {
    child.stdin.end();
    killTree(child.pid);
    rl.close();
  }
});
