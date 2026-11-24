---
description: Run the subdomain enumeration stage for a program in a background child session
agent: sub-enum
subagent: true
---

Run the subdomain enumeration stage.

## Arguments

- `$1` — program slug, or a wildcard scope declaration such as `*.example.com`
- `$2` — optional apex domain override, or a run ID to resume

## Program bootstrap (wildcard first argument)

If `$1` starts with `*.`, it is an operator-declared wildcard scope, not a
program slug. Follow `shared/workflows/program-bootstrap.md` exactly:

1. Run `python scripts/bootstrap_program.py --wildcard "$1"`.
2. On any non-zero exit, stop and report the JSON `error`, `conflicts`, and
   `warnings` verbatim.
3. Use the returned `program`, `program_dir`, `scope`, and `apex` below.

Bootstrap never edits an existing program. A wildcard is not official program
authorization. When `$1` is a wildcard, `$2` may only be a run ID to resume; if
`$2` looks like a hostname, stop and return
`blocked: wildcard bootstrap fixes the apex; pass a run ID or omit $2`.

## Resolve inputs yourself

Do not rely on the parent conversation. Resolve everything from disk:

1. Program: bootstrap `program` when `$1` was a wildcard; otherwise `$1` is the
   slug. If empty, stop and return
   `blocked: program slug or wildcard required`.
2. Program directory: `programs/<program>`. Required files: `program.md`,
   `scope.md`. If either is missing, stop and return
   `blocked: program context missing`.
3. Scope file: absolute path to `programs/<program>/scope.md`.
4. Target override:
   - bootstrap `apex` when `$1` was a wildcard
   - `$2` when it is a hostname (non-wildcard invocation)
   - `$2` when it is a run ID: resume that run instead of creating a new one
5. Output root: `programs/<program>/recon/subdomains/`.
6. Report the resolved absolute paths at the top of your summary.

## Preconditions

- `scripts/bbh/cli.py` and `scripts/bbh_cli.py` must exist. If either does not,
  stop and return exactly:
  `blocked: Phase 3 shared utilities not implemented`.
- `shared/tools.json` must contain at least one enabled tool with
  `stage: subdomains`. If not, stop and return
  `blocked: no approved subdomain tool`.
- The JSON scope block in `scope.md` must parse. If not, stop and return
  `blocked: invalid scope data`.
- Show exclusions and restrictions before running. If a restriction prohibits a
  technique, skip that tool and report why; do not run it and do not block
  unrelated passive sources.
- **Active DNS authorization gate.** `dnscan` and `dnsx` are active DNS
  techniques. Skip both unless the program's `program.md` explicitly authorizes
  active DNS brute force / wordlist resolution for this program. A wildcard
  scope, an empty `restrictions` list, or bootstrap defaults are never
  authorization. Record each skip and its reason in `run.json` and the stage
  summary, then continue with passive sources.
- `dnsx` also requires its registered input `{rawdir}/wordlist-full.txt`. If that
  file is missing, skip `dnsx`; never generate, substitute, or guess a wordlist.

## Execute

Follow the workflow in the `sub-enum` agent instructions: preflight, tool check
and install if approved-but-missing, run approved tools, normalize, scope filter,
deduplicate, optional alive probe, update run metadata, write summary.

## Outputs

```text
programs/<program>/recon/subdomains/<run_id>/{raw,processed,rejected,logs}/
programs/<program>/recon/subdomains/<run_id>/summary.md
programs/<program>/recon/runs/<run_id>/run.json
```

## Return

Return only the `Stage result` block defined in the agent instructions. Do not
include raw results, host lists, or tool output.
