# Burp Suite MCP

Burp is the HTTP engine for interactive hunting. It is an external dependency:
this repository does **not** distribute the extension, the proxy JAR, or any
Burp configuration.

## What the integration does

OpenCode starts a local MCP server that talks to Burp's MCP extension, and
exposes tools such as `send_http1_request`, `send_http2_request`, and
`output_project_options` to the agent. Requests sent through those tools go
through Burp's HTTP stack.

## Setup

1. Obtain the Burp MCP extension from its upstream project and load it in Burp
   Suite (Extensions → Add). This repository has no copy and no download URL of
   its own; use the source you trust.
2. Confirm the extension is listening. The current configuration expects the
   SSE endpoint at `http://127.0.0.1:9876/`.
3. Put the stdio↔SSE proxy JAR at `tools/mcp/burp/mcp-proxy.jar`. That path is
   gitignored, so it never reaches Git. Never commit a JAR.
4. Leave the `burp` entry in `opencode.json` enabled. If you have no JAR yet,
   set `"disabled": true` on it so OpenCode does not retry a failing start.
5. Restart OpenCode and check the connection:

   ```sh
   opencode mcp list
   ```

6. Verify scope is readable before relying on it:

   ```js
   const options = JSON.parse(await tools.burp.output_project_options());
   const { include = [], exclude = [] } = options.target.scope ?? {};
   ```

## Config shape

```json
"burp": {
  "type": "local",
  "command": ["java", "-jar", "tools/mcp/burp/mcp-proxy.jar", "--sse-url", "http://127.0.0.1:9876/"],
  "cwd": "."
}
```

The path is relative on purpose. A machine-specific absolute path is local
configuration, not something the repository should carry.

## Scope rules

Two authorizations apply and neither replaces the other:

- `programs/<program>/scope.md` decides which assets may be tested at all.
- Burp's configured scope decides whether an individual request may be sent.

The operator owns Burp scope and maintains it in Burp. Agents never call
`set_project_options` or `set_user_options`. If Burp scope cannot be read or a
match is ambiguous, stop and ask.

## Limitations — stated plainly

- **MCP-native requests do not appear in Proxy history.** They are sent by the
  MCP server, not by the browser or an intercepting proxy listener. Do not
  expect to find them under HTTP history.
- **No programmatic Repeater "Send" is promised.** Whether a Repeater-style
  action exists depends entirely on the extension you installed. Nothing in
  this repository implements it.
- **No automatic scanning.** The agent sends the specific requests an objective
  needs. It does not launch crawls, fuzzing, or broad scans on its own.
- **Protocol is chosen per request.** Use HTTP/2 where the target negotiates
  it, HTTP/1.1 otherwise, and trust the response status line over the tool's
  protocol label.
- **Redirects and secondary hosts need a fresh scope check.** A redirect is not
  a scope extension.

## Evidence

Store exchanges under
`programs/<program>/targets/<target>/notes/http/<YYYYMMDD-HHMMSS>-<METHOD>-<purpose>.md`
and include a line stating that MCP-native sends do not pass through the Proxy
listener. Redact cookies, tokens, and API keys that are not needed to reproduce
the test.
