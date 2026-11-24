#!/usr/bin/env node
// Test harness: runs the fake MCP server behind the real read-only filter.
// The test spawns this file so the actual stdio bridging code is exercised.

import { runProxy } from "../../mcp/readonly-filter.mjs";
import { READ_TOOLS } from "./tool-catalog.mjs";

runProxy({
  command: process.execPath,
  args: ["scripts/tests/fixtures/fake-mcp-server.mjs"],
  allow: READ_TOOLS,
  label: "test-filter",
});
