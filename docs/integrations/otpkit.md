# OTPKit — optional temporary email and SMS

[OTPKit](https://github.com/SecFathy/otpkit) is an MCP server that creates
disposable email addresses and numbers and extracts OTP codes or verification
links from incoming messages. It is **optional and disabled by default**. Most
of this workspace works without it.

## What it provides

| Tool | Purpose |
| --- | --- |
| `create_temp_email` | Create a temporary inbox |
| `wait_for_email` | Wait for a message and return it |
| `wait_for_sms` | Wait for an SMS message |
| `extract_otp_from_text` | Pull a code or verification link out of text |

## Install and enable

OTPKit is a Python package run through `uv`, so nothing is vendored here:

1. Install [uv](https://docs.astral.sh/uv/) and confirm `uvx --version`.
2. In `opencode.json`, remove `"disabled": true` from the `otpkit` server.
3. Restart OpenCode and confirm the connection with `opencode mcp list`.

```json
"otpkit": {
  "type": "local",
  "command": ["uvx", "otpkit"],
  "cwd": ".",
  "disabled": true
}
```

`uvx` runs the package in an isolated environment outside this repository, so
upgrades are a `uvx` concern, not a repo change.

## Providers and environment

The free providers need no key. Paid providers are optional and belong in
`.env` (gitignored), never in `opencode.json`:

```sh
# FIVESIM_API_KEY=
# SMSPOOL_API_KEY=
```

## Privacy — read this before using free numbers

- Free SMS numbers are **public and shared**. Anyone using that provider can
  see the messages sent to the number you were given, including your codes.
- Never use a public shared number for a real account, a personal account, a
  work account, or anything that can be traced back to you or a third party.
- Free email inboxes are also shared infrastructure. Assume anyone can read
  them.
- Codes, inbox contents, temporary credentials, and API keys stay out of Git,
  out of reports, and out of chat. Store only the redacted evidence the test
  actually needs.

## Workflow

1. Read `programs/<program>/scope.md` and the program's restrictions.
2. Confirm that creating a temporary test account is permitted. Many programs
   require it; some forbid it. If the rules are unclear, stop and ask the
   operator.
3. Create a temporary address, or choose an SMS option the program permits.
4. Register through the browser or an approved HTTP request.
5. Retrieve the code or link through OTPKit.
6. Continue only within the requested objective.
7. Redact the evidence before saving it.

OTPKit does not authorize account creation by itself, and it does not change any
scope rule. It is a tool the operator enables for a specific, permitted test.

## Status

Configured, not live-verified in this repository: no account is created on a
third-party target without explicit operator authorization.
