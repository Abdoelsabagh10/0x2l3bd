# Notion MCP — two separate connections

Two Notion integrations are configured and they are never collapsed into one:

| Server | Access | Purpose | Token variable |
| --- | --- | --- | --- |
| `notion-main` | Read-only | Personal methodology, security notes, reference material | `NOTION_TOKEN_MAIN` |
| `notion-bb` | Read/write | Program notes, investigation records, findings, updates | `NOTION_TOKEN_BB` |

Both live under `mcp.servers` in `opencode.json` and run through the bridges in
`scripts/mcp/`.

## Setup

1. In Notion, create **two** internal integrations, one per workspace, with the
   access each role needs:
   - `notion-main`: read content only. Do not grant insert or update
     capabilities. This is the outer layer of read-only enforcement.
   - `notion-bb`: read, insert, and update.
2. Share only the specific pages or databases each integration needs. An
   integration cannot see anything that was not shared with it.
3. Put the tokens in `.env` (gitignored):

   ```sh
   NOTION_TOKEN_MAIN=ntn_...
   NOTION_TOKEN_BB=ntn_...
   ```

4. Install the server package under `tools/` (gitignored). The bridges expect:

   ```text
   tools/mcp/notion/node_modules/@notionhq/notion-mcp-server/bin/cli.mjs
   ```

5. Restart OpenCode and confirm both connections:

   ```sh
   opencode mcp list
   ```

## How read-only is enforced

`notion-main` does not connect to the Notion server directly. It runs the
server behind `scripts/mcp/readonly-filter.mjs`, which:

1. rewrites every `tools/list` response so non-read tools are never advertised,
   and
2. refuses any `tools/call` outside the allowlist locally, with a JSON-RPC
   error, so the request never reaches Notion.

The allowlist is default-deny. Of the server's 24 tools, 14 read tools are
allowed and 10 write tools are hidden:

```text
blocked: API-create-a-comment, API-create-a-data-source, API-delete-a-block,
         API-move-page, API-patch-block-children, API-patch-page,
         API-post-page, API-update-a-block, API-update-a-data-source,
         API-update-page-markdown
```

Verify it from a fresh session: `notion-main` should list 14 tools and
`notion-bb` should list 24.

A new upstream tool stays blocked until someone adds it to
`NOTION_READ_ONLY_TOOLS` in `scripts/mcp/readonly-filter.mjs` and the tests in
`scripts/tests/readonly-filter.test.mjs` are updated.

The filter is defence in depth, not a proof of safety. The Notion integration's
own capabilities are the primary control, and neither is a substitute for
reviewing what you store.

## Which connection to use

- Reading methodology, checklists, or your own reference notes → `notion-main`.
- Recording program notes, a recon summary, or a finding → `notion-bb`.
- Reuse existing pages in `notion-bb` when the topic already has one. Create a
  new page only for a genuinely new activity.
- Never write to `notion-main`. If a write is needed, it belongs in `notion-bb`.

## Privacy

Tokens, page contents, and private notes stay out of Git. `.env` is ignored;
`docs/` and `programs/` must not contain exported workspace content. Do not
paste secrets from Notion into reports, commits, or chat.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `no .env at ...` | `.env` is missing, or `NOTION_ENV_FILE` points elsewhere |
| `NOTION_TOKEN_MAIN absent or empty` | The variable is missing or blank |
| `server entry not installed` | The package is not installed under `tools/mcp/notion` |
| A read tool is missing from `notion-main` | It is not in the allowlist; add it deliberately |
