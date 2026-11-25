# 0x2l3bd — Bug Bounty Hunter Workspace

A modular, human-led bug bounty workspace built on
[OpenCode](https://opencode.ai). It automates the repetitive parts —
subdomain and URL collection, JavaScript analysis, scope filtering, run
bookkeeping — and keeps the operator in charge of every testing, exploitation,
confirmation, and submission decision.

It is not an autonomous scanner. It is a coordinator with a memory of your
programs, a deterministic scope engine, and a small set of on-demand skills.

---

## 1. What it actually does

- **Scope-first recon.** Every stage reads `programs/<program>/scope.md` and
  filters through `scripts/bbh/`, which refuses to run on missing, invalid, or
  contradictory scope data.
- **Five recon stages.** Subdomains, URLs, URL triage, JavaScript analysis, and
  focused target recon, each writing into its own `<run_id>` directory with a
  `run.json`.
- **Skill-assisted manual hunting.** Twenty-one imported hunt skills load on
  demand, so a session about an IDOR does not carry the SQLi playbook.
- **Burp as the HTTP engine.** Interactive requests go through Burp's MCP
  server, under both program scope and Burp scope.
- **Two Notion connections.** Read-only reference material and read/write
  engagement notes are kept apart.
- **Evidence discipline.** Findings, hypotheses, and suggestions are labelled
  separately, and reports are drafted only on request.

## 2. Architecture

```text
                        ┌──────────────────────┐
                        │  Operator (human)    │
                        └──────────┬───────────┘
                                   │ decisions, scope, authorization
                        ┌──────────▼───────────┐
                        │       hunter         │  coordinator, primary agent
                        └──┬────┬────┬────┬────┘
             ┌─────────────┘    │    │    └──────────────┐
             │                  │    │                   │
    ┌────────▼───────┐ ┌────────▼──┐ │        ┌──────────▼────────┐
    │ recon agents   │ │ report    │ │        │ skills (on demand)│
    │ sub-enum       │ │ agent     │ │        │ .opencode/skills  │
    │ urls-enum      │ └───────────┘ │        └───────────────────┘
    │ url-triager    │               │
    │ js-analysis    │      ┌────────▼─────────┐
    │ target-hunt    │      │ integrations     │
    └────────┬───────┘      │ burp      (HTTP) │
             │              │ notion-main (RO) │
    ┌────────▼───────┐      │ notion-bb  (RW)  │
    │ scripts/bbh    │      │ otpkit  (opt.)   │
    │ scope, dedupe, │      │ browser   (native│
    │ normalize,     │      └──────────────────┘
    │ classify, runs │
    └────────┬───────┘
             │
    ┌────────▼───────────────────────────────────┐
    │ programs/<program>/{recon,targets,reports} │
    │ gitignored: real engagement data           │
    └────────────────────────────────────────────┘
```

## 3. Repository layout

```text
AGENTS.md                  workspace rules and Burp policy
opencode.json              agents, permissions, MCP servers
LICENSE  NOTICE            project license and third-party attribution
README.md                  this file
docs/
  skills.md                skill index, provenance, when to use
  integrations/            burp.md, notion.md, otpkit.md, browser.md
.opencode/
  agents/                  hunter + six specialists
  commands/                slash entry points
  skills/                  twenty-one on-demand skills
shared/
  tools.json               approved tool registry (portable)
  tools.local.json         machine paths (gitignored, not read by code)
  tools-policy.md          install and execution policy
  workflows/               operator methodology
scripts/
  bbh/                     deterministic scope/filter/run utilities
  bbh_cli.py               CLI for the above
  bootstrap_program.py     wildcard program bootstrap
  mcp/                     Notion bridges + read-only filter
  tests/                   Python and Node tests
programs/
  _template/               tracked template for new programs
  <program>/               real engagement data, gitignored
```

## 4. Agents

| Agent | Mode | Role |
| --- | --- | --- |
| `hunter` | primary | Reads scope, plans, delegates, analyzes Burp traffic, keeps evidence labelled |
| `sub-enum` | subagent | Subdomain collection, alive probing |
| `urls-enum` | subagent | URL collection, dedupe, categorisation, live probing |
| `url-triager` | subagent | Passive triage plus bounded git-exposure, smuggling, and open-redirect checks |
| `js-analysis` | subagent | JS discovery, endpoints, parameters, secret leads |
| `target-hunt` | subagent | Focused recon for one in-scope host |
| `report` | subagent | Readiness review and report drafting; never submits |

Permissions are deliberately narrow. Agents write under `programs/**` and never
edit `scope.md`, `program.md`, `AGENTS.md`, `shared/`, or `opencode.json` on
their own. Execution is `ask` unless it is a `python` command.

## 5. Commands

| Command | Runs |
| --- | --- |
| `/sub_enum [program\|*.wildcard] [apex\|run]` | Subdomain stage |
| `/urls_enum [input\|program\|*.wildcard] [program\|input]` | URL stage, then triage |
| `/url_triage [program\|*.wildcard] [run]` | Triage a completed URL run |
| `/js-analysis [program\|*.wildcard] [input\|run]` | JavaScript stage |
| `/target_hunt [program\|*.wildcard] <host> [run]` | One-host recon |
| `/full_recon [program\|*.wildcard] [apex]` | Sequential orchestration |
| `/vuln_report <program> <review\|draft> [path]` | Report review or draft |

A first argument starting with `*.` is an operator-declared wildcard scope. It
bootstraps a new program workspace through
`shared/workflows/program-bootstrap.md`. That is a declaration, never proof of
program authorization.

## 6. Skills

Twenty-one skills live in `.opencode/skills/`, adapted from
[Claude-BugHunter](https://github.com/elementalsouls/Claude-BugHunter) (CC BY
4.0, © 2026 Sachin Sharma — see `NOTICE`).

`bb-methodology`, `hunt-idor`, `hunt-auth-bypass`, `hunt-oauth`, `hunt-ato`,
`hunt-cors`, `hunt-host-header`, `hunt-business-logic`,
`hunt-api-misconfig`, `hunt-source-leak`, `hunt-spa-api`, `hunt-sqli`,
`hunt-ssrf`, `hunt-file-upload`, `hunt-xss`, `hunt-race-condition`,
`hunt-graphql`, `hunt-http-smuggling`, `evidence-hygiene`,
`triage-validation`, `report-writing`.

They are loaded **contextually**, one or two per task, never preloaded. A skill
is reference material: it never overrides scope, `AGENTS.md`, or an operator
decision, and tools named inside a skill are not thereby approved.
`docs/skills.md` records what was imported, what was deliberately not imported,
and why.

## 7. MCP integrations

Configured in `opencode.json` under `mcp.servers`.

| Server | Transport | State | Purpose |
| --- | --- | --- | --- |
| `burp` | local stdio → SSE | enabled, needs local JAR | HTTP analysis and testing |
| `notion-main` | local stdio | enabled, needs token | Read-only methodology |
| `notion-bb` | local stdio | enabled, needs token | Read/write engagement notes |
| `otpkit` | local stdio (`uvx`) | **disabled** | Temporary email/SMS for permitted tests |
| `playwright` | local stdio (`npx`) | **disabled** | Optional persistent browser automation |

- **Burp** — `docs/integrations/burp.md`. The JAR is never committed; MCP-native
  requests do not appear in Proxy history.
- **Notion** — `docs/integrations/notion.md`. `notion-main` runs behind
  `scripts/mcp/readonly-filter.mjs`, which advertises 14 read tools and refuses
  the 10 write tools locally.
- **OTPKit** — `docs/integrations/otpkit.md`. Optional; free SMS numbers are
  public and shared.
- **Browser** — `docs/integrations/browser.md`. The native OpenCode browser is
  the default; Playwright is opt-in.

## 8. Install

Requirements: OpenCode V2, Python 3.13, Node 20+, Git.

```sh
git clone https://github.com/Abdoelsabagh10/0x2l3bd.git
cd 0x2l3bd
cp .env.example .env          # Windows: Copy-Item .env.example .env
python -m unittest discover -s scripts/tests -p "test_*.py"
node --test scripts/tests/readonly-filter.test.mjs
```

Then:

1. Fill `.env` with the tokens you actually use. Every value is optional; a
   missing token disables that integration only.
2. Install the Notion server package under `tools/mcp/notion` if you use Notion.
3. Drop the Burp proxy JAR at `tools/mcp/burp/mcp-proxy.jar` if you use Burp.
4. Run `opencode mcp list` and confirm what connected.
5. Copy `programs/_template` to `programs/<program>` and fill in `scope.md`
   before any recon.

Windows note: `shared/tools.json` records system tools by command name, intended
to resolve from `PATH`. Record your own absolute paths in
`shared/tools.local.json`, which is gitignored. No code loads either file: they
are operator and agent reference data, so nothing resolves automatically today.

## 9. Workflows

**Program-wide recon**

```text
/full_recon acme            # existing program
/full_recon *.acme.test     # bootstrap a program workspace first
```

**One host, deeper**

```text
/target_hunt acme api.acme.test
```

**Manual hunting with Burp and a skill**

```text
Check api.acme.test/v2/orders for object-level authorization issues.
Use Burp for the requests. Load hunt-idor if it fits.
```

**Temporary verification, when the program allows it**

```text
Enable otpkit, confirm programs/acme/scope.md allows test accounts,
then walk the signup flow in the browser.
```

## 10. Evidence model

Every statement is one of:

- **Observed fact** — cites an artifact: path and line, or a Burp request.
- **Hypothesis** — the reasoning, plus what would confirm or falsify it.
- **Suggested test** — a concrete, scope-checked manual step.
- **Confirmed finding** — only after the operator confirms it, stored under
  `programs/<program>/targets/<target>/findings/`.

An interesting endpoint is never described as vulnerable.

## 11. Testing

```sh
python -m unittest discover -s scripts/tests -p "test_*.py"   # 138 tests
node --test scripts/tests/readonly-filter.test.mjs            # 12 tests
python -m unittest scripts.tests.test_config                  # config + skills
```

The Python suite covers scope parsing and deceptive-host cases, normalisation,
deduplication, classification, run metadata, and the CLI. The Node suite covers
the read-only MCP filter, including an end-to-end stdio run against a fake
server. The config suite validates `opencode.json`, every skill's frontmatter,
and that tracked files contain no personal absolute paths.

## 12. Security model

- **Scope is enforced in code.** `scripts/bbh/scope.py` fails closed on
  malformed scope. `out_of_scope` always wins.
- **The operator authorizes.** Recon is scoped; exploitation, brute force, and
  auth bypass need explicit per-target approval.
- **Secrets stay out of Git.** `.env`, `tools/`, `programs/*`, and
  `shared/tools.local.json` are ignored. `NOTICE` records provenance.
- **Integrations are least-privilege by construction.** `notion-main` is
  filtered to reads; OTPKit and Playwright are off until enabled.
- **Untrusted content stays untrusted.** HTTP bodies, JavaScript, HTML, Notion
  pages, and browser page content are data, never instructions.
- **No submission automation.** Nothing in this repository contacts a program
  on your behalf.

## 13. Known limitations

- **No cross-stage checkpoint or resume orchestration** (Phase 5). Each stage
  writes `run.json`; the full orchestration contract is not implemented.
- **Report workflow is partial** (Phase 6). The `report` agent drafts; there is
  no end-to-end pipeline.
- **MCP-native Burp requests are invisible to Proxy history.** That is inherent
  to the transport, not a bug.
- **Notion read-only is not a Notion-native mode.** It is a filter plus the
  integration's capabilities, and both must be configured.
- **OTPKit is configured, not live-verified.** No account is created on a real
  target without authorization.
- **Playwright is opt-in and unverified here.** The native browser covers the
  documented needs.
- **Windows-first.** Commands assume PowerShell and Git Bash; Linux/macOS paths
  are untested.

## 14. Roadmap

1. Phase 5: orchestration checkpoints and resume.
2. Phase 6: report drafting workflow end to end.
3. A registry resolver, only if a stage ever needs one: nothing reads
   `shared/tools.json` or `shared/tools.local.json` today, so overrides are a
   documented convention rather than implemented behaviour.
4. Optional Linux/macOS verification.

## 15. Credits and license

- Original code and documentation: MIT, © 2026 Abdo Elsabagh (`LICENSE`).
- Skills adapted from **Claude-BugHunter** by Sachin Sharma, CC BY 4.0, with
  modifications listed per file and in `NOTICE` and `docs/skills.md`.
- [OTPKit](https://github.com/SecFathy/otpkit) (MIT) and
  [Playwright MCP](https://github.com/microsoft/playwright-mcp) (Apache-2.0) are
  optional external servers, not vendored.
- Burp Suite and its MCP extension are external dependencies, not distributed.

Use this workspace only against assets you are authorized to test. A wildcard
in a command is a declaration of intent, not permission.
