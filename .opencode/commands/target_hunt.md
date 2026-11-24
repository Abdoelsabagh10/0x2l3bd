---
description: Run focused reconnaissance for one in-scope target in a background child session
agent: target-hunt
subagent: true
---

Run focused reconnaissance for a single in-scope target.

## Arguments

- `$1` — program slug, or a wildcard scope declaration such as `*.example.com`
- `$2` — target hostname (required, for example `test.example.com`)
- `$3` — optional run ID to resume

## Program bootstrap (wildcard first argument)

If `$1` starts with `*.`, it is an operator-declared wildcard scope, not a
program slug. Follow `shared/workflows/program-bootstrap.md` exactly:

1. Run `python scripts/bootstrap_program.py --wildcard "$1"`.
2. On any non-zero exit, stop and report the JSON `error`, `conflicts`, and
   `warnings` verbatim.
3. Use the returned `program`, `program_dir`, and `scope` below.

Bootstrap never edits an existing program. A wildcard is not official program
authorization. The wildcard defines scope only; `/target_hunt` still needs one
concrete host in `$2`.

## Resolve inputs yourself

Do not rely on the parent conversation. Resolve everything from disk:

1. Program: bootstrap `program` when `$1` was a wildcard; otherwise `$1` is the
   slug. If empty, stop and return `blocked: program slug or wildcard required`.
2. Target: `$2`. If empty, stop and return
   `blocked: target required (one hostname; a wildcard defines scope only)`.
3. Program directory: `programs/<program>`. Required files: `program.md`,
   `scope.md`. Missing either one means `blocked: program context missing`.
4. Scope file: absolute path to `programs/<program>/scope.md`.
5. Target output root: `programs/<program>/targets/<target>/`.
6. Report the resolved absolute paths at the top of your summary.

## Preconditions

- The target must be a single valid hostname. Reject URLs, wildcards, CIDRs, or
  lists.
- `scripts/bbh/cli.py` and `scripts/bbh_cli.py` must exist. If either is
  missing, stop and return exactly:
  `blocked: Phase 3 shared utilities not implemented`.
- Scope check the target with the shared utility. Use the shared launcher:
  `python scripts/bbh_cli.py scope check --scope <scope> --kind host --value <target>`
  `out_of_scope` or `ambiguous` means stop immediately and report the exact
  result. Do not probe.
- The JSON scope block in `scope.md` must parse. If not, stop and return
  `blocked: invalid scope data`.
- `shared/tools.json` must contain at least one enabled tool with
  `stage: content` or `stage: target`. If not, stop and return
  `blocked: no approved target tool`.
- Show exclusions and restrictions before running. If a restriction prohibits a
  technique, skip that step and report why; do not block unrelated steps.

## Execute

Follow the workflow in the `target-hunt` agent instructions: preflight, reuse
program-level results with their run IDs recorded, technology identification,
content discovery, related in-scope host discovery, URL and parameter discovery,
attack-surface summary, run metadata.

Respect program rate limits and prohibited techniques. No exploitation.

## Outputs

```text
programs/<program>/targets/<target>/recon/<run_id>/{raw,processed,logs}/
programs/<program>/targets/<target>/recon/<run_id>/summary.md
programs/<program>/targets/<target>/recon/runs/<run_id>/run.json
```

Never write into `programs/<program>/recon/`.

## Return

Return only the `Stage result` block defined in the agent instructions. No raw
results or long path lists.
