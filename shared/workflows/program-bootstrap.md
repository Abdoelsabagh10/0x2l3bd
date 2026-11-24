# Program Bootstrap (wildcard invocation)

Authoritative procedure for `/sub_enum`, `/urls_enum`, `/js-analysis`,
`/full_recon`, and `/target_hunt` when the first argument is a wildcard scope
declaration such as `*.example.com`.

## Trigger

A recon command is a **wildcard invocation** when its first argument starts
with `*.`. That argument is an operator-declared scope, not a program slug.

- `*.example.com` means the apex `example.com` and every subdomain at any
  depth.
- A plain argument that does not start with `*.` keeps the old behavior: it is
  a program slug, and the program must already exist.

Do not ask the operator to run a separate setup command. Bootstrap and continue
with the requested workflow.

## One implementation

Run exactly this from the workspace root:

```bash
python scripts/bootstrap_program.py --wildcard '<wildcard>'
```

`scripts/bootstrap_program.py` is the only place that derives slugs, scans
programs, creates directories, generates `scope.md` / `program.md`, and
validates the generated scope. Do not reimplement it and do not hand-write
program files.

## Result contract

The script prints one JSON object on stdout.

Success (`exit 0`):

```json
{
  "ok": true,
  "status": "created | reused",
  "program": "<directory name and scope.program>",
  "program_dir": "<absolute path>",
  "scope": "<absolute path to scope.md>",
  "scope_sha256": "<hash>",
  "wildcard": "*.example.com",
  "apex": "example.com",
  "in_scope": ["*.example.com"],
  "out_of_scope": [],
  "allowed_ports": [],
  "restrictions": [],
  "narrowed": false,
  "partial_exclusions": [],
  "warnings": []
}
```

Use `program`, `program_dir`, `scope`, and `apex` as the resolved values for the
rest of the command. Never use the raw wildcard as a program slug or directory.

Stop immediately and report the JSON `error`, `conflicts`, and `warnings` when:

| Exit | Meaning |
| --- | --- |
| `2` | Conflict or ambiguity with existing program data. No files changed. |
| `3` | Invalid wildcard argument. |
| `4` | Target directory exists but cannot be used. |
| `5` | Template, input, or I/O failure. |

A wildcard is an operator-declared scope only. It never proves that an official
program, platform entry, or policy authorizes testing.

## What bootstrap creates

For a new program, from `programs/_template/`:

- `programs/<slug>/scope.md` with exactly one in-scope entry, the requested
  wildcard, which also covers the apex. `out_of_scope`, `allowed_ports`, and
  `restrictions` stay empty. The provenance section records that no official
  program authorization was verified.
- `programs/<slug>/program.md` with unknown fields left as `Not provided`.
- `programs/<slug>/recon/summary.md`.
- `recon/{subdomains,urls,javascript,content,runs}/`, `targets/`, `reports/`.

Slug rule: lowercase the apex, replace every run of non-alphanumeric characters
with `-`, trim hyphens. Example: `*.example.com` → `example-com`.

## Reuse and conflict rules

Bootstrap scans `programs/*/scope.md` (never `_template`):

- **Reuse** when exactly one existing program's scope already covers the
  requested wildcard. Coverage means an in-scope wildcard for the same apex or
  a parent apex. Reuse never edits that program.
- **Narrowing is allowed.** Existing `*.example.com`, requested
  `*.sub.example.com` reuses the program with `"narrowed": true`. The existing
  scope stays unchanged; the run only enumerates the requested apex.
- **Stop on conflict** when the requested wildcard would expand an existing
  program's scope, is fully excluded, matches multiple programs, or the derived
  slug directory exists but does not cover the wildcard.
- Exclusions inside a reused scope still apply. Report them before running.

Never delete, rewrite, or "repair" an existing program directory.

## After bootstrap

Common rules:

1. Show the operator one short line: created or reused, program, wildcard,
   exclusions, restrictions, and whether official authorization is unverified.
2. Run the requested workflow with the resolved `program`, `program_dir`, and
   `scope`.
3. Keep using only approved tools from `shared/tools.json` with their existing
   command templates and flags.
4. If program restrictions prohibit a technique, mark that stage `skipped` with
   the reason and continue with unrelated permitted stages. Do not treat an
   unauthorized technique as permission to block everything.
5. Do not ask for information that is already resolved. Ask only when a required
   execution input is genuinely missing (for example a single host for
   `/target_hunt`, or a host list for `/urls_enum`).

Per command:

| Command | Wildcard supplies | Still required |
| --- | --- | --- |
| `/sub_enum` | program, scope, enumeration apex | nothing; `$2` is optional |
| `/urls_enum` | program, scope | a host list; reuse the newest subdomain run or report `blocked: no input host list` |
| `/js-analysis` | program, scope | a JS URL list; reuse the newest URL run or report `blocked: no JavaScript URL list` |
| `/full_recon` | program, scope, stage 1 apex | nothing; `$2` is optional narrowing |
| `/target_hunt` | program, scope | one concrete target host; report `blocked: target required` if absent |

For `/full_recon`, bootstrap once in the parent session and pass the resolved
values to every stage. Child sessions must not bootstrap again.

## Safety

- Never infer official authorization from a wildcard.
- Never invent restrictions, rate limits, or program rules.
- Never widen a scope or add entries the operator did not supply; a wildcard
  already covers its own apex.
- Never run active DNS brute force, content brute force, or exploitation unless
  the operator explicitly authorizes it for that program.
- Never modify `shared/`, `tools/`, `.opencode/`, `opencode.json`, `AGENTS.md`,
  or `scripts/bbh/`.
