#!/usr/bin/env node
// Bridges NOTION_TOKEN_BB from the project .env into the Notion MCP server.
// Never prints the token; only paths and variable names reach stderr.

import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const SOURCE_VAR = "NOTION_TOKEN_BB";
const TARGET_VAR = "NOTION_TOKEN";
const SERVER_ENTRY = "tools/mcp/notion/node_modules/@notionhq/notion-mcp-server/bin/cli.mjs";

// scripts/mcp/notion-bb.mjs -> project root
const PROJECT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

const fail = (msg) => { process.stderr.write(`[notion-bb] ${msg}\n`); process.exit(78); };

function readToken(envPath) {
  const text = readFileSync(envPath, "utf8").replace(/^\uFEFF/, ""); // strip BOM
  let token = "";
  for (const line of text.split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith("#")) continue;
    const eq = t.indexOf("=");
    if (eq < 1) continue;
    if (t.slice(0, eq).trim() !== SOURCE_VAR) continue;
    let v = t.slice(eq + 1).trim();
    if (v.length > 1 && ((v[0] === '"' && v.endsWith('"')) || (v[0] === "'" && v.endsWith("'"))))
      v = v.slice(1, -1);
    token = v;
  }
  return token;
}

let token;
try {
  const envPath = process.env.NOTION_ENV_FILE || join(PROJECT_ROOT, ".env");
  if (!existsSync(envPath)) fail(`no .env at ${envPath}`);
  token = readToken(envPath);
} catch {
  fail("could not read .env");
}
if (!token) fail(`${SOURCE_VAR} absent or empty in .env`);

const entry = join(PROJECT_ROOT, SERVER_ENTRY);
if (!existsSync(entry)) fail("server entry not installed; see install step");

const child = spawn(process.execPath, [entry], {
  cwd: PROJECT_ROOT,
  stdio: "inherit",
  env: { ...process.env, [TARGET_VAR]: token },
  windowsHide: true,
});

child.on("error", () => fail("could not start server"));

let stopping = false;
const shutdown = (code) => { if (stopping) return; stopping = true; try { child.kill(); } catch {} process.exit(code); };

child.on("exit", (code) => { stopping = true; process.exit(code ?? 0); });
process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
process.on("exit", () => { try { child.kill(); } catch {} });
