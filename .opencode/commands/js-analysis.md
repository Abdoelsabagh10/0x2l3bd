---
description: Run the JavaScript analysis stage for a program in a background child session
agent: js-analysis
subagent: true
---

Run the JavaScript analysis stage.

## Arguments

- `$1` — program slug, or a wildcard scope declaration such as `*.example.com`
- `$2` — optional JS URL list path, or a run ID to resume

## Program bootstrap (wildcard first argument)

If `$1` starts with `*.`, it is an operator-declared wildcard scope, not a
program slug. Follow `shared/workflows/program-bootstrap.md` exactly:

1. Run `python scripts/bootstrap_program.py --wildcard "$1"`.
2. On any non-zero exit, stop and report the JSON `error`, `conflicts`, and
   `warnings` verbatim.
3. Use the returned `program`, `program_dir`, and `scope` below.

Bootstrap never edits an existing program. A wildcard is not official program
authorization. When `$1` is a wildcard, `$2` may only be an input path or a run
ID; the wildcard already fixes the program and scope.

## Resolve inputs yourself

Do not rely on the parent conversation. Resolve everything from disk:

1. Program: bootstrap `program` when `$1` was a wildcard; otherwise `$1` is the
   slug. If empty, stop and return `blocked: program slug or wildcard required`.
2. Program directory: `programs/<program>`. Required files: `program.md`,
   `scope.md`. Missing either one means `blocked: program context missing`.
3. Scope file: absolute path to `programs/<program>/scope.md`.
4. JS URL list, in priority order:
   - `$2` when it is a path ending in `.txt` that exists
   - newest `programs/<program>/recon/urls/<run_id>/processed/categories/javascript.txt`
   If none exists, stop and return
   `blocked: no JavaScript URL list (run /urls_enum first)`.
5. Output root: `programs/<program>/recon/javascript/`.
6. Report the resolved absolute paths at the top of your summary.

## Preconditions

- `scripts/bbh/cli.py` and `scripts/bbh_cli.py` must exist. If either is
  missing, stop and return exactly:
  `blocked: Phase 3 shared utilities not implemented`.
- `shared/tools.json` must contain at least one enabled tool with
  `stage: javascript`. If not, stop and return
  `blocked: no approved JavaScript tool`.
- The JSON scope block in `scope.md` must parse. If not, stop and return
  `blocked: invalid scope data`.
- Show exclusions and restrictions before running. If a restriction prohibits a
  technique, skip that step and report why; do not block unrelated steps.

## Execute

Follow the workflow in the `js-analysis` agent instructions: preflight, tool
check and install if approved-but-missing, normalize and scope-check the URL
list, reachability check, download reachable files, analyze, extract endpoints,
parameters, hosts, sourcemaps and masked secret leads, update run metadata, write
summary.

## Outputs

```text
programs/<program>/recon/javascript/<run_id>/{raw,processed,rejected,logs}/
programs/<program>/recon/javascript/<run_id>/summary.md
programs/<program>/recon/runs/<run_id>/run.json
```

## Return

Return only the `Stage result` block defined in the agent instructions. No file
contents, endpoint dumps, or secret values.
