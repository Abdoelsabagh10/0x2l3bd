// Tool catalog shared by the fake MCP server and its tests.
// Pure data: importing this file must have no side effects.

export const WRITE_TOOLS = [
  "API-create-a-comment",
  "API-create-a-data-source",
  "API-delete-a-block",
  "API-move-page",
  "API-patch-block-children",
  "API-patch-page",
  "API-post-page",
  "API-update-a-block",
  "API-update-a-data-source",
  "API-update-page-markdown",
];

export const READ_TOOLS = [
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

export const ALL_TOOLS = [...READ_TOOLS, ...WRITE_TOOLS];
