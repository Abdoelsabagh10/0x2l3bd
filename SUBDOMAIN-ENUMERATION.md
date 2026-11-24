# Subdomain Enumeration

Stage 1 of the reconnaissance pipeline. It discovers subdomains for one
authorized program, keeps only the ones inside the program scope, and produces a
clean host list plus a list of live hosts.

This stage **does not test for vulnerabilities**. It only enumerates.

```text
Subdomain Enumeration  ->  URL Enumeration  ->  URL Triage  ->  JS Analysis
        (hosts)                 (URLs)            (candidates)
```

## Purpose

- Turn a program's apex domain into a list of subdomains.
- Enforce scope before anything else touches the data.
- Produce stable, reproducible output that later stages can consume.

## Inputs

- program slug, program directory, and absolute `scope.md` path
- optional apex/target override (a single domain)
- optional run ID to resume
- output root: `programs/<program>/recon/subdomains/`

The enumeration base is the resolved apex: the override when one is given,
otherwise the program scope apex. It is written to `inputs/domains.txt`, one
domain per line, LF-only, and is used only as tool input.

## Prerequisites

- `programs/<program>/program.md` and `programs/<program>/scope.md` exist, and
  the JSON scope block in `scope.md` parses.
- The shared utilities in `scripts/bbh/` are present (`scripts/bbh/cli.py`,
  `scripts/bbh_cli.py`).
- `shared/tools.json` contains approved tools with `stage: subdomains`.

Approved tools that are missing on disk are installed into
`tools/subdomains/<name>`, verified, and registered before use. Tools with
`status: proposed` or `status: blocked` are never installed or executed.

## Workflow

1. **Preflight** - verify program context, parse the scope block, load the tool
   registry.
2. **Initialize the run** -
   `python scripts/bbh_cli.py runs init --program <program> --stage subdomains --scope <scope.md>`
   creates the run directory and `run.json`.
3. **Enumerate** - run each approved source with its registered command
   template, one raw file per tool under `raw/`.
4. **Merge** - concatenate raw candidates into `raw/all.txt`.
5. **Normalize**:

   ```bash
   python scripts/bbh_cli.py normalize --kind host \
     -i <run>/raw/all.txt -o <run>/processed/normalized.txt
   ```

6. **Scope validation**:

   ```bash
   python scripts/bbh_cli.py scope check --scope <scope.md> --kind host \
     -i <run>/processed/normalized.txt \
     --in <run>/processed/in-scope.txt \
     --out <run>/rejected/out-of-scope.txt \
     --review <run>/rejected/ambiguous.txt
   ```

7. **Deduplicate**:

   ```bash
   python scripts/bbh_cli.py dedupe \
     -i <run>/processed/in-scope.txt -o <run>/processed/subdomains.txt
   ```

8. **Alive probing** (only when an approved `alive` tool exists) - probe every
   host in `subdomains.txt`, keep raw output under `raw/alive/`, and write the
   live hosts to `processed/alive.txt`.
9. **Record** - update `run.json` with tools, commands, counts, statuses, and
   paths, then write `summary.md` and append a stage section to
   `programs/<program>/recon/summary.md`.

## Enumeration tools

Versions below are the ones recorded in `shared/tools.json`.

| Tool | Version | Type | Input | Raw output | Role |
| --- | --- | --- | --- | --- | --- |
| `subfinder` | 2.17.0 | passive | `inputs/domains.txt` | `raw/subfinder.txt` | Passive aggregator, `-all -recursive` |
| `assetfinder` | 0.1.1 | passive | `inputs/domains.txt` | `raw/assetfinder.txt` | Certificate transparency and related-domain discovery |
| `findomain` | 10.0.1 | passive | `inputs/domains.txt` | `raw/findomain.txt` | Passive certificate and search sources |
| `chaos` | 0.5.2 | passive | `inputs/domains.txt` | `raw/chaos.txt` | ProjectDiscovery Chaos public dataset |
| `subenum` | git:d83c6e9 | passive | `inputs/domains.txt` | `raw/subenum.txt` | Batch wrapper over wayback, crt, abuseipdb, subfinder, assetfinder |
| `github-subdomains` | git:72a7c41 | passive | `inputs/domains.txt` | `raw/github-subdomains.txt` | Subdomains found in GitHub code (needs `GITHUB_TOKEN`) |
| `jq` | 1.8.2 | helper | - | - | JSON helper, no command template |

Several sources need API credentials. Credentials are supplied through
environment variables and are never written to logs.

### Active DNS tools (gated)

These are active techniques and are **skipped by default**.

| Tool | Version | Requirement |
| --- | --- | --- |
| `dnscan` | git:281721e | Wordlist brute force. Runs only when the program's `program.md` explicitly authorizes active DNS brute force. |
| `dnsx` | 1.3.1 | Wordlist resolution. Needs the same authorization **and** its registered input `raw/wordlist-full.txt`, which is never generated or guessed. |

A wildcard scope, an empty `restrictions` list, or a bootstrap default is never
authorization. Every skip is recorded with its reason in `run.json` and the
stage summary.

### Not active

| Tool | Version | Status | Why |
| --- | --- | --- | --- |
| `puredns` | 2.1.1 | blocked | Linux/macOS assets only |
| `massdns` | 1.1.0 | blocked | No release assets |

## Merging and deduplication

`raw/all.txt` is the literal merge of every raw file, unmodified for debugging.
Normalization standardizes host casing and formatting, scope validation splits
in-scope from rejected, and the shared `dedupe` utility produces the final unique
list. Order matters: normalize, then scope-check, then dedupe, so a host is never
counted twice across scope decisions.

## DNS resolution and alive probing

Alive probing uses the `httpx` entry with `stage: alive` (version 1.12.0). This
is a **different registry entry** from the URL stage probe, and it retains full
metadata:

```bash
httpx -silent -nc -sc -content-length -web-server -title -mc <status_codes> \
  < processed/subdomains.txt > raw/alive/httpx.txt
```

- `raw/alive/httpx.txt` - probe output with status, length, server, and title.
- `raw/alive/httpx-hosts.txt` - the bare host list extracted from that output.
- `processed/alive.txt` - live hosts, normalized.

The command also derives per-status files (`httpx-200.txt`, `httpx-404.txt`,
`httpx-401-403.txt`, `httpx-500-502-503.txt`, `httpx-redirects.txt`) next to its
output. These are debugging aids, not stage inputs.

## Scope validation and filtering

- `scope.md` is authoritative; `program.md` never overrides it.
- `out_of_scope` always wins over `in_scope`.
- A `*.example.com` entry covers the apex and every subdomain.
- Hosts that do not clearly match are written to
  `rejected/out-of-scope.txt` or `rejected/ambiguous.txt`, never silently kept.
- Ambiguous entries need an operator decision. The stage does not guess.

## Output structure

```text
programs/<program>/recon/subdomains/<run_id>/
├── inputs/
│   └── domains.txt              one apex domain per line (LF only)
├── raw/
│   ├── subfinder.txt            one file per source
│   ├── assetfinder.txt
│   ├── findomain.txt
│   ├── chaos.txt
│   ├── subenum.txt
│   ├── github-subdomains.txt
│   ├── all.txt                  merge of every raw file
│   └── alive/
│       ├── httpx.txt            alive probe output with metadata
│       └── httpx-hosts.txt      live hosts extracted from the probe
├── processed/
│   ├── normalized.txt           normalized candidates
│   ├── in-scope.txt             in-scope candidates
│   ├── subdomains.txt           unique subdomains (stage result)
│   └── alive.txt                live hosts (next stage input)
├── rejected/
│   ├── out-of-scope.txt         clearly outside scope
│   └── ambiguous.txt            needs operator review
├── logs/                        per-tool stdout and stderr
└── summary.md                   counts, tools, skips, incidents

programs/<program>/recon/runs/<run_id>/run.json     run metadata
programs/<program>/recon/summary.md                 program-wide stage summary
```

## Execute

```bash
# standard
/sub_enum <program>

# narrow to one in-scope domain
/sub_enum <program> example.com

# declare a wildcard scope (bootstraps a new program workspace)
/sub_enum *.example.com

# resume an existing run
/sub_enum <program> <run_id>
```

A wildcard first argument creates a **new** program workspace through
`shared/workflows/program-bootstrap.md`. It never edits an existing program and
never implies official program authorization.

## What the stage returns

```md
## Stage result
- Stage: subdomains
- Run ID:
- Status: completed | failed | skipped | blocked
- Scope hash:
- Outputs:
- Counts: raw / normalized / in-scope / rejected / ambiguous / alive
- Tools: name@version (path)
- Errors: <log path> - one-line cause
- Blocked/ambiguous: <items needing operator decision>
- Next stage input: <path to subdomains.txt or alive.txt>
```

## Next stage

`/urls_enum <program>` consumes `processed/alive.txt` (falling back to
`processed/subdomains.txt`). In the current implementation `/urls_enum` also
runs URL Triage automatically after a successful URL enumeration, so one command
covers stages 2 and 3.