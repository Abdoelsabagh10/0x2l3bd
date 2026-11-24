---
description: Run URL enumeration and then URL triage automatically for a program
agent: hunter
subagent: false
---

Run the URL enumeration stage, then URL triage on the same run.

## Arguments

- `$1` — input host list path (`.txt`), a program slug, or a wildcard scope
  declaration such as `*.example.com`
- `$2` — program slug when `$1` is an input path; otherwise an optional input
  path or a run ID

Supported forms:

```text
/urls_enum /path/to/AliveSubs.txt <program>   input file first, program slug second
/urls_enum *.example.com [input.txt]          wildcard scope declaration
/urls_enum <program> [input.txt]              legacy form
```

Resolution order for `$1`:

1. Starts with `*.` → wildcard scope declaration; follow the bootstrap section.
2. Ends with `.txt` (case-insensitive) and the file exists → input host list.
   `$2` is then required as the program slug. If `$2` is missing or empty, stop
   and return `blocked: program slug required when input file is given`.
3. Otherwise `$1` is the program slug.

## Program bootstrap (wildcard first argument)

If `$1` starts with `*.`, it is an operator-declared wildcard scope, not a
program slug. Follow `shared/workflows/program-bootstrap.md` exactly:

1. Run `python scripts/bootstrap_program.py --wildcard "$1"`.
2. On any non-zero exit, stop and report the JSON `error`, `conflicts`, and
   `warnings` verbatim.
3. Use the returned `program`, `program_dir`, and `scope` below.

Bootstrap never edits an existing program, and the script itself proves nothing
about authorization; the operator's wildcard declaration is the authorization
basis. When `$1` is a wildcard, `$2` may only be an input path or a run ID; the
wildcard already fixes the program and scope.

## Resolve inputs yourself

Resolve everything from disk before delegating. Child sessions do not see this
conversation, so pass the resolved values explicitly.

1. Program:
   - bootstrap `program` when `$1` was a wildcard
   - `$2` when `$1` is an existing input path
   - otherwise `$1` is the slug
   If empty, stop and return `blocked: program slug or wildcard required`.
2. Program directory: `programs/<program>`. Required files: `program.md`,
   `scope.md`. Missing either one means `blocked: program context missing`.
3. Scope file: absolute path to `programs/<program>/scope.md`.
4. Input host list, in priority order:
   - `$1` when it is an existing path ending in `.txt`
   - `$2` when it is an existing path ending in `.txt`
   - newest completed `programs/<program>/recon/subdomains/<run_id>/processed/alive.txt`
   - fallback: newest `programs/<program>/recon/subdomains/<run_id>/processed/subdomains.txt`
   If none exist, stop and return
   `blocked: no input host list (run /sub_enum first)`.
5. Output root: `programs/<program>/recon/urls/`.
6. Report the resolved absolute paths in the final block.

## Preconditions

- `scripts/bbh/cli.py` and `scripts/bbh_cli.py` must exist. If either is
  missing, stop and return exactly:
  `blocked: Phase 3 shared utilities not implemented`.
- `shared/tools.json` must contain at least one entry with `stage: urls` and
  `status: approved`. Entries with `status: proposed` are never installed or
  executed. If no approved URL tool exists, stop and return
  `blocked: no approved URL tool`.
- `httpx-urls` must exist with `status: approved`; it is the only live probe
  for this stage and is never run as a collection source. The `stage: alive`
  `httpx` entry is not used here.
- The current agent's `subagent` permission must allow both `urls-enum` and
  `url-triager`. If either is denied, stop and report
  `blocked: subagent permission missing for <agent>`; never run a stage inline
  in this session instead.
- The JSON scope block in `scope.md` must parse. If not, stop and return
  `blocked: invalid scope data`.
- Authorization: the operator's selection of this program and the scope declared
  in `scope.md` is the authorization confirmation. Do not ask for policy URLs,
  documentary proof, or a repeated per-run confirmation. Record the program, the
  scope hash, and that the operator declared the scope in `run.json` notes and
  the stage summary.
- Scope validation, out-of-scope rejection, and technique-specific restrictions
  are unchanged and still apply. If a restriction prohibits a technique, skip
  that source and report why; do not block unrelated sources.

## Execute

Run the two stages in order, one at a time. Each stage runs as a child session
launched with the `subagent` tool. Pass explicit values, because child sessions
do not see this conversation. Never launch the two stages in parallel, and never
run URL triage twice for one URL run.

### Stage 1 - URL enumeration

- Agent: `urls-enum`
- Pass: program slug, absolute program directory, absolute `scope.md` path, the
  input host list resolved above, run ID when resuming, output root
  `programs/<program>/recon/urls/`.
- Wait for completion, then read its `## URL stage - ...` block.
- If the status is not `completed`, stop. Report the URL stage result and the
  cause, and do not run URL triage.

### Stage 2 - URL triage (automatic, same run)

- Agent: `url-triager`
- Run it only when Stage 1 returned `completed`, and reuse the values Stage 1
  returned. Never pick a different run ID and never start a second run.
- Pass: program slug, absolute program directory, absolute `scope.md` path, the
  Stage 1 run ID, input
  `programs/<program>/recon/urls/<run_id>/processed/httpx-url-only.txt` (the
  authoritative URL-only result; `processed/LiveURLs.txt` is an identical copy),
  and output root
  `programs/<program>/recon/urls/<run_id>/processed/url-triage/`.
- The stage's active checks (git exposure, request smuggling, open redirect) run
  automatically on approved hosts; there is no `active` flag and no per-run
  confirmation.
- Wait for completion, then read its `## Triage stage - ...` block.
- Triage needs no run of its own. Never add a `triage` stage to `run.json`:
  `scripts/bbh/runs.py` supports only `subdomains`, `urls`, `javascript`,
  `content`, `target`, `alive`, and `full_recon`, and triage records its own
  `counts.tsv` and `summary.md`.

## Outputs

```text
programs/<program>/recon/urls/<run_id>/{inputs,raw,processed,processed/categories,processed/hosts,rejected,logs}/
programs/<program>/recon/urls/<run_id>/inputs/alive.txt
programs/<program>/recon/urls/<run_id>/inputs/scheme-https.txt
programs/<program>/recon/urls/<run_id>/processed/categories/
programs/<program>/recon/urls/<run_id>/processed/AllURLs.txt
programs/<program>/recon/urls/<run_id>/processed/UniqueURLs.txt
programs/<program>/recon/urls/<run_id>/processed/ScopedURLs.txt
programs/<program>/recon/urls/<run_id>/processed/TestableURLs.txt
programs/<program>/recon/urls/<run_id>/processed/StaticAssetsURLs.txt
programs/<program>/recon/urls/<run_id>/processed/httpx-url-only.txt
programs/<program>/recon/urls/<run_id>/processed/LiveURLs.txt
programs/<program>/recon/urls/<run_id>/processed/url-triage/counts.tsv
programs/<program>/recon/urls/<run_id>/processed/url-triage/summary.md
programs/<program>/recon/urls/<run_id>/summary.md
programs/<program>/recon/runs/<run_id>/run.json
```

## Return

Return one combined block covering both stages:

```md
## URL run - <run_id>
URL enum: <completed|failed|skipped|blocked>   <mm>m <ss>s   Scope hash: <hash>
Triage:   <completed|failed|skipped|blocked|not run>   <mm>m <ss>s
URL tools: <tool> <status> <duration>s | <tool> <status> <duration>s
Counts: AllURLs <n> | Unique <n> | Scoped <n> | Testable <n> | Static <n> | Live(200) <n>
Triage counts: live <n> | parameterized <n> | redirect <n> | origins <n> approved <n>
Checks: git <result> | smuggling <result> | redirect <result>
Candidates: <n> (never confirmed)
Skipped: <stage or check + reason>; <none>
Errors: <tool failure + log path>; <none>
Files: recon/urls/<run_id>/{inputs,raw,processed,processed/categories,processed/hosts,rejected,logs}, processed/url-triage/{counts.tsv,summary.md}, summary.md, runs/<run_id>/run.json
```

Full telemetry stays on disk in `run.json`, `logs/` and `logs/metrics/`; never
paste raw URLs or tool output.

## Next stage

`/js_analysis <program> <run_id>` uses the JavaScript URLs this run kept in
`processed/categories/javascript.txt`. URL enumeration never starts it, and URL
triage never reruns the URL stage.
