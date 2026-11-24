---
description: Orchestrate subdomain, URL, and JavaScript reconnaissance sequentially for a program
agent: hunter
subagent: false
---

You are Hunter orchestrating full reconnaissance for the resolved program.

## Arguments

- `$1` — program slug, or a wildcard scope declaration such as `*.example.com`
- `$2` — optional scope narrowing: a single in-scope apex domain or target host

Stay in this session. Do not run reconnaissance yourself, and do not launch the
stages in parallel.

## Program bootstrap (wildcard first argument)

If `$1` starts with `*.`, it is an operator-declared wildcard scope, not a
program slug. Bootstrap exactly once, in this session, before any stage:

1. Run `python scripts/bootstrap_program.py --wildcard "$1"`.
2. On any non-zero exit, stop and report the JSON `error`, `conflicts`, and
   `warnings` verbatim.
3. Use the returned `program`, `program_dir`, `scope`, and `apex` for every
   stage. Child sessions must not bootstrap again.

Bootstrap never edits an existing program. A wildcard is not official program
authorization. When `$1` is a wildcard, the default Stage 1 enumeration apex is
the bootstrap `apex`; `$2` may narrow it to an in-scope host.

## Preflight

1. Resolve the program: bootstrap result when `$1` is a wildcard; otherwise
   `programs/$1`. Require `program.md` and `scope.md`. If either is missing,
   stop and report.
2. Read both files. Confirm the JSON scope block parses. If it does not, stop.
3. If bootstrap was used, report whether the program was created or reused and
   whether official authorization is unverified. Show the operator: in-scope
   roots, exclusions, restrictions that affect rate or technique, and the scope
   hash.
4. If `$2` is present, scope-check it with the shared utility before Stage 1:
   `python scripts/bbh_cli.py scope check --scope <scope> --kind host --value "$2"`
   `out_of_scope` or `ambiguous` means stop and explain.
5. Require `scripts/bbh/cli.py` and `scripts/bbh_cli.py`. If either is missing,
   stop and report exactly:
   `Blocked: Phase 3 shared utilities not implemented.`
6. Create or resume the orchestration run:
   `python scripts/bbh_cli.py runs init --program <program> --stage full_recon --scope <scope>`
   If an incomplete run for this scope hash exists, ask the operator to choose
   **resume**, **fresh**, or **abort** before proceeding. Never resume across a
   scope change without approval.

## Stages

Run these in order, one at a time. Each stage runs as a child session launched
with the `subagent` tool. Pass explicit values; child sessions do not see this
conversation.

### Stage 1 — sub_enum

- Agent: `sub-enum`
- Pass: program slug, absolute program directory, absolute `scope.md` path,
  target override (`$2` if present, otherwise the bootstrap `apex` when `$1` was
  a wildcard), run ID, output root `programs/<program>/recon/subdomains/`.
- Active DNS tools (`dnscan`, `dnsx`) are skipped unless the program's
  `program.md` explicitly authorizes active DNS brute force / wordlist
  resolution; passive sources continue.
- Wait for completion.
- Verify outputs exist and are non-empty:
  `python scripts/bbh_cli.py runs verify --program <program> --run-id <id> --stage subdomains`
- Record stage status in `programs/<program>/recon/runs/<id>/run.json`.

### Stage 2 — urls_enum

- Skip if Stage 1 failed or its host list is empty.
- Agent: `urls-enum`
- Pass: program slug, absolute program directory, scope path, input host list
  (stage 1 `processed/alive.txt`, else `processed/subdomains.txt`), run ID,
  output root `programs/<program>/recon/urls/`.
- Wait, then verify expected outputs. Record status.

### Stage 3 — url_triage

- Skip if Stage 2 failed or no `processed/LiveURLs.txt` was produced.
- Agent: `url-triager`
- Pass: program slug, absolute program directory, scope path, the Stage 2 run ID,
  input `programs/<program>/recon/urls/<id>/processed/LiveURLs.txt`, output root
  `programs/<program>/recon/urls/<id>/processed/url-triage/`.
- The stage's active checks (git exposure, request smuggling, open redirect) run
  automatically on approved hosts; there is no `active` flag and no per-run
  confirmation. Flagged customer-owned hosts are excluded from active checks only.
- Wait, then verify `counts.tsv` and `summary.md` exist and are non-empty. Record
  status.

### Stage 4 — js-analysis

- Skip if Stage 2 failed or no `categories/javascript.txt` was produced.
- Agent: `js-analysis`
- Pass: program slug, absolute program directory, scope path, JS URL list path,
  run ID, output root `programs/<program>/recon/javascript/`.
- Wait, then verify expected outputs. Record status.

## After the stages

1. Update the orchestration run metadata with every stage status, tool versions,
   output paths, and error paths.
2. Append a section to `programs/<program>/recon/summary.md` covering: run ID,
   stages completed/failed/skipped, counts, and where to look next.
3. Report to the operator:

```md
## Full recon — <program>
- Bootstrap: created | reused (operator-declared scope, authorization unverified)
- Run ID / scope hash:
- Stage table: stage | status | outputs | counts
- Failures and causes:
- Blocked items needing a decision:
- Suggested manual focus:
```

## Rules

- No reconnaissance logic here. No filtering, normalization, or deduplication.
- No tool installation or execution in this session.
- Never re-run a completed stage unless the operator asks for a fresh run.
- If a program restriction prohibits a stage or technique, mark it `skipped`
  with the reason and continue with unrelated permitted stages.
- On failure: record it, skip dependents, continue with what is possible, and
  say clearly what is missing.
