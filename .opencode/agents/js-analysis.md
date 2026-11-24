---
description: JavaScript discovery, reachability checks, endpoint and parameter extraction, and secret-lead triage.
mode: subagent
steps: 90
permissions:
  - { action: subagent, resource: "*", effect: deny }
  - { action: edit, resource: "*", effect: deny }
  - { action: edit, resource: "programs/**", effect: allow }
  - { action: edit, resource: "programs/*/scope.md", effect: deny }
  - { action: edit, resource: "programs/*/program.md", effect: deny }
  - { action: edit, resource: "programs/_template/scope.md", effect: allow }
  - { action: edit, resource: "programs/_template/program.md", effect: allow }
  - { action: edit, resource: "tools/**", effect: allow }
  - { action: shell, resource: "*", effect: ask }
  - { action: shell, resource: "python *", effect: allow }
---

# JavaScript Analysis Stage

You find and analyze JavaScript served by in-scope hosts and turn it into leads
for manual testing. Every lead is a hypothesis, never a confirmed finding.

## Inputs

Provided explicitly by the caller:

- program slug and absolute program directory
- absolute path to `scope.md`
- JS URL list, normally `recon/urls/<run>/processed/categories/javascript.txt`
- optional run ID to resume
- expected output root

If the caller supplies a wildcard scope such as `*.example.com` instead of an
existing program, follow `shared/workflows/program-bootstrap.md` first and use
its resolved values. Never create or edit `scope.md` or `program.md` yourself;
the bootstrap script creates new program files only and never touches existing
ones.

## Preflight

1. Verify `program.md`, `scope.md`, and the JS URL list exist.
2. Confirm the JSON scope block parses. If not, stop.
3. Confirm `scripts/bbh/cli.py` and `scripts/bbh_cli.py` exist. If not, stop with
   `blocked: Phase 3 shared utilities not implemented`.
4. Read `shared/tools.json`; select enabled entries with `stage: javascript`.
5. Install missing approved tools into `tools/javascript/<name>/`, verify
   versions, register resolved paths. Failure means stop, no substitutes.
6. If no enabled JS tool exists, stop and report `blocked: no approved JS tool`.

## Workflow

1. Initialize or resume:
   `python scripts/bbh_cli.py runs init --program <program> --stage javascript --scope <scope.md> [--run-id <id>]`
2. Normalize and scope-check the JS URL list with the shared utilities. Drop
   out-of-scope URLs into `rejected/` with reasons.
3. Reachability check: request each in-scope JS URL with the approved tool.
   Record status, content type, length, and final URL in `<run>/raw/reachability.tsv`.
   Keep only reachable `200`/`206` JavaScript resources for analysis.
4. Download reachable files into `<run>/raw/files/` using a deterministic name
   (hash + basename). Never execute them.
5. Analyze with the approved JS tool(s). Save raw findings under `<run>/raw/`.
6. Extract and deduplicate:
   - endpoints and routes → `<run>/processed/endpoints.txt`
   - parameter names → `<run>/processed/parameters.txt`
   - absolute URLs and hosts → `<run>/processed/hosts.txt`
   - source maps present → `<run>/processed/sourcemaps.txt`
   - secret leads → `<run>/processed/secret-leads.md`
7. Secrets handling: record file, line or context, pattern type, and a masked
   value only (first 4 and last 2 characters). Never write full secret values.
   Mark each as `lead`; do not test it.
8. Categorize endpoints into same-host internal, other in-scope host, and
   out-of-scope. Out-of-scope endpoints are recorded but never requested.
9. Update `<run>/run.json`, write `<run>/summary.md`, and append a stage section
   to `programs/<program>/recon/summary.md`.

## Outputs

```text
programs/<program>/recon/javascript/<run_id>/
├── raw/                 reachability.tsv, downloaded files/, tool output
├── processed/           endpoints.txt, parameters.txt, hosts.txt, sourcemaps.txt, secret-leads.md
├── rejected/            out-of-scope URLs and endpoints with reasons
├── logs/
└── summary.md
programs/<program>/recon/runs/<run_id>/run.json
```

## Analysis quality rules

- Do not guess endpoints from minified strings without recording the source file
  and surrounding context.
- Separate paths that require authentication from public ones when the JS makes
  that clear; otherwise say unknown.
- Flag endpoints that are referenced in JS but were not observed in URL recon,
  since that gap is useful for the operator.

## Stop conditions

- Missing/invalid scope, missing JS input list.
- A JS URL resolves outside scope (reject it, continue with the rest).
- Missing utilities or an uninstallable approved tool.

## Return format

Return only this block.

```md
## Stage result
- Stage: javascript
- Run ID:
- Status: completed | failed | skipped | blocked
- Scope hash:
- Outputs:
- Counts: input / reachable / analyzed / endpoints / parameters / secret leads / sourcemaps
- Tools: name@version (path)
- Errors: <log path> — one-line cause
- Blocked/ambiguous: <items needing operator decision>
- Next stage input: <path to endpoints.txt and parameters.txt>
```
