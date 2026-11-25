#!/usr/bin/env node
// Read-only Notion MCP bridge for the main workspace.
//
// Bridges NOTION_TOKEN_MAIN from the project .env into the Notion MCP server
// and runs it behind scripts/mcp/readonly-filter.mjs, which hides and refuses
// every write tool. Never prints the token; only paths and tool names reach
// stderr.

import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

import { NOTION_READ_ONLY_TOOLS, runProxy } from "./readonly-filter.mjs";

const SOURCE_VAR = "NOTION_TOKEN_MAIN";
const TARGET_VAR = "NOTION_TOKEN";
const LABEL = "notion-main";
const SERVER_ENTRY = "tools/mcp/notion/node_modules/@notionhq/notion-mcp-server/bin/cli.mjs";

// scripts/mcp/notion-main.mjs -> project root
const PROJECT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

const fail = (msg) => {
  process.stderr.write(`[${LABEL}] ${msg}\n`);
  process.exit(78);
};

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
    if (v.length > 1 && ((v[0] === '"' && v.endsWith('"')) || (v[0] === "'" && v.endsWith("'")))) {
      v = v.slice(1, -1);
    }
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
if (!existsSync(entry)) fail("server entry not installed; see docs/integrations/notion.md");

runProxy({
  command: process.execPath,
  args: [entry],
  cwd: PROJECT_ROOT,
  env: { ...process.env, [TARGET_VAR]: token },
  allow: NOTION_READ_ONLY_TOOLS,
  label: LABEL,
});
