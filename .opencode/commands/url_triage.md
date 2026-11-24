---
description: Run the URL triage and classification stage for a completed URL enumeration run
agent: url-triager
subagent: true
---

Run the URL triage and classification stage.

## Arguments

- `$1` - program slug, or a wildcard scope declaration such as `*.example.com`
- `$2` - run ID of a completed URL enumeration run (for example
  `20261112-205941-urls`); optional, defaults to the newest completed run

## Resolve inputs yourself

Do not rely on the parent conversation. Resolve everything from disk:

1. Program: bootstrap `program` when `$1` is a wildcard, otherwise `$1` is the
   slug. If empty, stop and return `blocked: program slug or wildcard required`.
2. Program directory: `programs/<program>`. Required files: `program.md` and
   `scope.md`. Missing either one means `blocked: program context missing`.
3. Scope file: absolute path to `programs/<program>/scope.md`. The JSON scope
   block must parse or return `blocked: invalid scope data`.
4. Run: `$2` when given; otherwise the newest `programs/<program>/recon/urls/`
   run containing `processed/LiveURLs.txt`. If none exists, stop and return
   `blocked: no completed URL run (run /urls_enum first)`.
5. Input: `programs/<program>/recon/urls/<run_id>/processed/httpx-url-only.txt`
   when present, otherwise `processed/LiveURLs.txt` for older runs. Both contain
   bare HTTP 200 URLs, one per line. Treat the file as read-only.
6. Derive the triage input under the output root:
   - copy the HTTPX result verbatim to `httpx-url-only.txt`
   - remove URLs whose URL **path** ends in `.js`, case-insensitively, after
     stripping the query string and fragment (so `/app.js?v=123` is removed,
     while `js` in a hostname, directory, or query parameter is kept)
   - deduplicate case-sensitively, first occurrence wins
   - write `js-urls.txt` and `non-js-urls.txt`, and use `non-js-urls.txt` for
     every passive classification below
7. Output root: `programs/<program>/recon/urls/<run_id>/processed/url-triage/`.
8. Report the resolved absolute paths at the top of your summary.
## Preconditions

- `shared/tools.json` must contain the triage tools with `status: approved`.
  `status: proposed` and `status: blocked` entries are never installed or
  executed. If no approved triage tool exists, stop and return
  `blocked: no approved triage tool`.
- The stage never installs anything. Tools are installed and registered by the
  operator beforehand.
- The stage never reruns Subdomain Enumeration or URL Enumeration, and never
  modifies their artifacts or historical runs.
- Authorization: the operator's selection of this program and the scope declared
  in `scope.md` is the authorization confirmation. Active checks run
  automatically, with no separate active flag and no per-run confirmation.
  Record that the operator authorized these checks in the stage summary.
- Restrictions and the flagged-host exclusion list still apply. If a restriction
  prohibits a check, skip it and report why; continue with unrelated checks.

## Execute

Follow the workflow in the `url-triager` agent instructions, in this order:

1. Passive classification of `non-js-urls.txt` (derived from the HTTPX URL-only
   output).
2. Verify the passive outputs before any active check.
3. Git exposure candidates and non-disruptive probes.
4. HTTP request smuggling checks on approved hosts.
5. Open redirect checks on candidate endpoints.
6. Summary with counts, durations, tool versions, results, errors, and skipped
   checks.

## Outputs

```text
programs/<program>/recon/urls/<run_id>/processed/url-triage/httpx-url-only.txt
programs/<program>/recon/urls/<run_id>/processed/url-triage/non-js-urls.txt
programs/<program>/recon/urls/<run_id>/processed/url-triage/js-urls.txt
programs/<program>/recon/urls/<run_id>/processed/url-triage/passive/
programs/<program>/recon/urls/<run_id>/processed/url-triage/counts.tsv
programs/<program>/recon/urls/<run_id>/processed/url-triage/summary.md
programs/<program>/recon/urls/<run_id>/processed/url-triage/{cloud,gf-patterns}/
programs/<program>/recon/urls/<run_id>/processed/url-triage/git-exposure/
programs/<program>/recon/urls/<run_id>/processed/url-triage/http-request-smuggling/
programs/<program>/recon/urls/<run_id>/processed/url-triage/redirect/
programs/<program>/recon/urls/<run_id>/processed/url-triage/logs/
```

## Return

Return only the concise block defined in the agent instructions:

```md
## Triage stage - <completed|failed|skipped|blocked> - <run_id>
Time: <mm>m <ss>s   Scope hash: <hash>
Tools: <tool> <status> <duration>s | <tool> <status> <duration>s
Counts: live <n> | php <n> | config <n> | admin-api <n> | parameterized <n> | redirect <n> | origins <n> approved <n>
Checks: git <result> | smuggling <result> | redirect <result>
Candidates: <n> (never confirmed)
Skipped: <check + reason>; <none>
Errors: <tool failure + log path>; <none>
Files: processed/url-triage/{counts.tsv,summary.md,...}
```

Full telemetry stays on disk in `logs/` and the stage summary; never paste raw
URLs or tool output.
