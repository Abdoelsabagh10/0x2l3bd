# Bug Bounty Hunter Workspace

## 1. Project Goal

Build a simple, modular bug bounty hunting assistant around
**OpenCode**.

The project is intended to support a human-led workflow: - Automate
repetitive reconnaissance and result organization. - Keep program scope
and program-specific requirements available to every agent. - Help
analyze the attack surface and Burp Suite traffic. - Support manual
testing by suggesting useful next steps and comparing evidence. -
Prepare reports only when explicitly requested by the user.

The user remains in control of testing decisions, active testing,
exploitation, finding confirmation, and report submission.

Do not turn this project into a large autonomous platform. Prefer
OpenCode's native capabilities and small reusable scripts over custom
infrastructure.

## 2. Core Design Principles

1.  **Keep it simple.** Add a component only when it solves a real need.
2.  **Human-led hunting.** The main agent assists and coordinates; it
    does not independently decide to exploit targets or submit reports.
3.  **Scope-first.** Every reconnaissance or testing task must use the
    active program's `scope.md`.
4.  **Shared deterministic utilities.** Use scripts for repeatable
    operations such as scope validation, normalization, and
    deduplication. Do not spend LLM tokens asking an agent to perform
    simple deterministic filtering.
5.  **Specialized agents.** Each subagent has a clear responsibility and
    can be invoked independently.
6.  **Orchestration, not duplication.** `/full_recon` coordinates the
    specialized agents rather than reimplementing their workflows.
7.  **Readable outputs.** Save raw and processed results in predictable
    locations.
8.  **Incremental development.** Build and test one component at a time,
    starting with the workspace and `/sub_enum`.
9.  **No unnecessary infrastructure.** No database, RAG system, custom
    Kali integration, Notion integration, or complex memory engine is
    required for the initial version.
10. **Transparent execution.** Record what ran, what completed, what
    failed, and where outputs were saved.

## 3. High-Level Architecture

### Main Agent: `hunter`

The main agent is the user's primary assistant and coordinator. It
should: - Understand the user's request and current active
program/target. - Read the relevant `program.md` and `scope.md` before
reconnaissance or testing. - Delegate suitable work to specialized
subagents. - Communicate with Burp Suite through the configured Burp MCP
connection. - Help inspect requests, responses, endpoints, parameters,
and observed behavior. - Compare information from Burp traffic with
reconnaissance results. - Suggest potential attack surfaces and manual
tests, clearly distinguishing hypotheses from confirmed findings. - Help
organize notes and evidence. - Invoke report preparation only when the
user asks.

The main agent must not claim that a vulnerability is confirmed without
sufficient evidence and user review.

### Specialized Subagents

Create the following specialized agents. Each must have a concise role,
clear inputs, expected outputs, and explicit scope rules.

#### `/sub_enum`

-   Collect subdomains for the authorized program or target.
-   Run the configured subdomain enumeration commands/tools.
-   Normalize and filter candidates through shared utilities.
-   Validate scope using the active program's `scope.md`.
-   Probe discovered hosts for HTTP(S) availability when configured.
-   Save raw candidates, filtered subdomains, out-of-scope/rejected
    entries, and alive-host results.
-   Be callable independently.

#### `/urls_enum`

-   Collect URLs from the supplied in-scope hosts or the program's
    alive-host list.
-   Use the configured URL discovery commands/tools.
-   Normalize, deduplicate, and scope-check URLs through shared
    utilities.
-   Categorize useful results where practical (for example: parameters,
    likely API routes, static assets, and other URL groups).
-   Preserve raw and processed outputs.
-   Be callable independently.

#### `/js-analysis`

-   Work on JavaScript URLs/files discovered during reconnaissance or
    supplied by the user.
-   Identify reachable JS resources and analyze them using the
    configured tools/commands.
-   Extract potentially useful endpoints, routes, parameter names,
    technology clues, and possible exposed secrets for manual review.
-   Treat findings as leads, not confirmed vulnerabilities.
-   Save outputs and a concise summary.
-   Be callable independently.

#### `/target_hunt`

-   Perform focused reconnaissance for one selected in-scope target,
    such as `test.test.com`.
-   Read the program scope before running tools.
-   Gather useful host information, directories/files, content discovery
    results, related in-scope subdomains, URLs, parameters, and
    technology clues using the configured commands/tools.
-   Use tools such as `dirsearch` when configured and appropriate.
-   Reuse existing program-level reconnaissance results where possible
    rather than repeating work unnecessarily.
-   Save target-specific results under that target's folder.
-   Provide a concise attack-surface summary and suggested manual
    investigation areas.
-   Do not perform exploitation or intrusive validation unless the user
    explicitly requests and authorizes it.

#### `/vuln_report`

> Renamed from `/report` on operator request to avoid confusion with
> OpenCode's built-in `report` skill. The specialist agent ID remains
> `report`.

-   Run only when the user asks for report assistance.
-   Use the program's `program.md` and `report-template.md` (if
    provided).
-   Help review the user's description and evidence.
-   Identify missing reproduction steps, impact explanation, and
    supporting evidence.
-   Distinguish confirmed behavior from assumptions.
-   Draft the report in the format required by the relevant
    platform/program.
-   Save the draft under the program's `reports/` directory.
-   Do not submit reports.

### `/full_recon` Orchestration Command

`/full_recon` is an orchestration command, not a separate recon
implementation.

It should invoke the specialized agents in this order: 1. `/sub_enum` 2.
`/urls_enum` 3. `/js-analysis`

Each agent owns its own stage and saves its outputs. The orchestrator
should: - Pass the active program and relevant input/output paths to
each agent. - Wait for a stage to finish before starting the next
dependent stage. - Check whether expected outputs exist before
proceeding. - Record completed, skipped, and failed stages. - Produce or
update a final recon summary. - Avoid rerunning completed work unless
requested or the user chooses a fresh run.

Cloud discovery and broader content discovery may be added as separate
stages later if useful. Do not add more agents or stages without
discussing the need first.

## 4. Shared Utilities

Filtering should initially be implemented as reusable scripts/utilities,
not as a separate LLM subagent.

Expected shared utilities: - `scope_filter`: validate domains/hosts/URLs
against the active program scope. - `normalize`: normalize hostnames and
URLs consistently. - `dedupe`: remove duplicate entries. -
`result_filter`: apply type-specific filtering/categorization when
needed.

All agents should call the same utilities rather than implementing their
own slightly different filtering rules.

### Scope validation requirements

-   Parse the hostname from a URL; do not use naive substring matching.
-   Match exact authorized hosts and valid subdomains only when the
    scope rules permit them.
-   Do not treat `example.com.attacker.test` as belonging to
    `example.com`.
-   Handle ports, paths, query strings, schemes, casing, trailing dots,
    and wildcard scope entries deliberately.
-   Respect exclusions and any program-specific restrictions.
-   When scope is ambiguous or cannot be parsed safely, do not actively
    test the asset; flag it for user review.
-   Keep rejected/out-of-scope results in a separate output where
    useful.
-   Never silently broaden the scope.

Test the filtering utility with positive and negative test cases before
relying on it. The user will provide or approve the exact scope entries
and rules.

## 5. Burp Suite and Tool Execution

-   Burp Suite is connected to OpenCode through the Burp Suite MCP
    extension/connection.
-   The main agent uses Burp MCP to inspect and reason about available
    HTTP traffic and requests/responses.
-   Recon tools are run by the agent in its available execution
    environment, and their outputs are returned and saved to the
    workspace.
-   Do not create a Kali integration, Kali MCP server, or
    Windows-to-Kali bridge as part of the initial design.
-   Do not assume a specific tool is installed. Check tool availability
    when relevant and report missing tools clearly.
-   The user will provide/approve the commands and tools to use. Do not
    invent a large toolchain or silently add tools.
-   Keep tool execution and active testing within the selected program's
    authorized scope.

## 6. Workspace Layout

Use one shared project/workspace for all programs.

Suggested initial structure:

``` text
BugBounty-Hunter/
├── AGENTS.md
├── opencode.json
├── README.md
├── agents/
│   ├── hunter.md
│   ├── sub-enum.md
│   ├── urls-enum.md
│   ├── js-analysis.md
│   ├── target-hunt.md
│   └── report.md
├── commands/
│   └── full-recon.md
├── skills/
│   └── (only add skills when needed)
├── scripts/
│   ├── filtering/
│   ├── normalization/
│   └── utils/
├── shared/
│   └── methodology/
└── programs/
    └── test.com/
        ├── program.md
        ├── scope.md
        ├── report-template.md
        ├── recon/
        │   ├── subdomains/
        │   ├── urls/
        │   ├── javascript/
        │   ├── content/
        │   ├── runs/
        │   └── summary.md
        ├── targets/
        │   └── test.test.com/
        │       ├── recon/
        │       ├── notes/
        │       └── findings/
        └── reports/
```

The actual OpenCode file conventions should be checked against the
installed/current OpenCode version before creating configuration files.
Do not assume unsupported paths or syntax.

### Program-level vs target-level data

-   `programs/<program>/recon/` stores shared, program-wide
    reconnaissance results.
-   `programs/<program>/targets/<target>/` stores work specific to a
    selected target.
-   Target-specific recon must not overwrite program-wide recon.
-   Reuse program-wide results when possible, and record when
    target-specific work supplements or refreshes them.
-   `reports/` is at the program root because reports belong to the
    program and its reporting requirements, not necessarily to one host.

## 7. Program Context Files

Each program should have the following files.

### `program.md`

Describes the program context, separate from technical scope: - Program
name and platform (for example HackerOne, Bugcrowd, or a private
program). - Program URL/reference if the user supplies it. - Short
description and relevant program context. - Report requirements and
expected report structure. - Severity/priority guidance if supplied by
the program. - Special testing rules or operational notes that are not
simply asset scope. - Any program-specific reporting template or
submission requirements.

Do not invent program rules. Mark unknown information as `Not provided`
and ask the user when necessary.

### `scope.md`

The authoritative source for authorized assets and scope restrictions: -
In-scope domains, hosts, IPs, URLs, or other asset identifiers. -
Wildcard entries and their intended meaning. - Out-of-scope assets and
exclusions. - Restrictions on testing methods, rate limits, accounts, or
environments if provided. - Any special conditions that affect whether
an asset may be tested.

The agents must read this file before running reconnaissance or testing
for that program. `program.md` does not override `scope.md`.

### `report-template.md`

Optional program-specific report template. If present, `/vuln_report` should
follow it. If absent, ask the user for the required format or use a
clearly labeled generic draft only after the user approves.

## 8. Recon Run Metadata and Checkpoints

Every reconnaissance run should have a run record, stored under the
relevant program's `recon/runs/` directory. Target-specific runs may be
stored under that target's `recon/runs/` directory if needed.

Suggested record fields: - Run ID. - Start and end timestamps. - Program
name. - Target(s)/input list used. - Scope file/version or a
snapshot/hash where practical. - Agents/stages executed. - Tools and
command names used. - Completion status for each stage: completed,
failed, skipped, or not started. - Output paths. - Error/log paths. -
Whether the run was resumed or started fresh. - Notes about missing
tools or partial results.

Use simple JSON or Markdown metadata; do not introduce a database for
this.

### Resume behavior

-   Before starting, inspect existing outputs and run metadata.
-   If a previous run stopped, report which stages completed and which
    did not.
-   Resume only from a safe, clearly identified checkpoint.
-   Do not assume old outputs are current or valid after the scope
    changes.
-   If scope or input targets changed, flag the previous run as
    potentially stale and ask whether to start fresh when needed.
-   Never overwrite useful previous results silently. Use a new run
    directory or explicit user-approved overwrite behavior.

## 9. Manual Hunting Workflow

The user may ask the main agent to: - Review Burp requests/responses. -
Extract endpoints from Burp traffic. - Compare endpoints observed in
Burp with endpoints discovered in JS files. - Identify endpoints present
in one source but absent in another. - Compare parameters and HTTP
methods. - Review authentication flows or user-provided login
methodology. - Suggest test cases and explain why they may be
relevant. - Organize observations and evidence in target notes/findings.

The agent should be collaborative: the user may test one idea manually
while the agent investigates or organizes another task. Clearly
separate: - Observed facts. - Hypotheses. - Suggested tests. - Confirmed
findings.

Do not claim that an endpoint is vulnerable merely because it looks
interesting.

## 10. Reporting Workflow

-   The user explicitly triggers report work.
-   The user supplies or explains the finding and evidence.
-   The agent helps validate whether the evidence supports the claimed
    impact and identifies gaps.
-   The agent follows the program's reporting requirements/template.
-   Drafts are stored in `programs/<program>/reports/`.
-   No automatic submission.

## 11. Initial Implementation Plan

Implement incrementally in this order:

1.  Inspect the current OpenCode version, its supported
    agent/command/skill conventions, and the existing workspace. Do not
    make assumptions about configuration syntax.
2.  Create the basic workspace and shared instructions.
3.  Create program folder conventions and example `program.md`,
    `scope.md`, and `report-template.md` templates.
4.  Implement the shared scope/normalization/deduplication utilities.
5.  Test the filtering utility thoroughly with in-scope, out-of-scope,
    wildcard, URL, port, and deceptive-substring cases.
6.  Build `/sub_enum` and test it with user-provided commands and a test
    scope.
7.  Build `/urls_enum`.
8.  Build `/js-analysis`.
9.  Build `/target_hunt`.
10. Build `/full_recon` orchestration and run metadata/checkpoint
    behavior.
11. Build `/vuln_report`.
12. Connect and verify Burp MCP behavior with the main agent.

Do not build everything in one pass. At each stage, explain what was
created, how to use it, and how it was tested. Ask the user before
adding tools, integrations, or major architecture changes.

## 12. Out of Scope for the Initial Version

Do not add these unless the user later requests them: - A dedicated
Filter LLM subagent. - SQLite or another database. - RAG
infrastructure. - Notion integration. - Custom Kali
MCP/bridge/integration. - Large autonomous exploitation workflows. -
Automatic vulnerability submission. - Large collections of unused
skills. - Complex memory or learning engines.
