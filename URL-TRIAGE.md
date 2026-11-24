# URL Triage

Stage 3 of the reconnaissance pipeline. It classifies the URLs produced by URL
Enumeration and runs a bounded set of non-disruptive checks against approved
hosts.

It **does not exploit, confirm, or submit anything**. Every match is a candidate
for manual verification.

```text
Subdomain Enumeration  ->  URL Enumeration  ->  URL Triage  ->  JS Analysis
        (hosts)                 (URLs)            (candidates)
```

## Purpose

- Reduce a large URL corpus to short, readable candidate lists.
- Identify technologies, sensitive files, interesting endpoints, and parameters.
- Check for exposed Git metadata, HTTP request smuggling, and open redirects
  without disrupting the target.
- Produce evidence an operator can review by hand.

## Inputs

- program slug, program directory, and absolute `scope.md` path
- the URL run ID and its HTTPX result: `processed/httpx-url-only.txt`
  (or `processed/LiveURLs.txt` for older runs)
- output root: `processed/url-triage/`

The HTTPX input is **read-only**. The stage never reruns Subdomain Enumeration or
URL Enumeration and never modifies a historical run. Its hash is reproduced in
the summary.

## Workflow

| Phase | Action |
| --- | --- |
| 0 | Build the triage input: strip JavaScript URLs, deduplicate |
| 1 | Passive classification of the non-JavaScript corpus |
| 2 | Verify passive output before any active check |
| 3 | Git exposure checks on approved origins |
| 4 | HTTP request smuggling checks with Smuggler |
| 5 | Open redirect checks with OpenRedireX |

Deliverables are `counts.tsv` (one path-and-count row per artifact) and
`summary.md` (counts, tool versions and verification, each active check with
duration and result, errors with log paths, skipped checks with reasons, and an
integrity statement for untouched artifacts).

## Phase 0 - build the triage input

The current URL stage emits URL-only output: one bare HTTP 200 URL per line.

1. Copy the HTTPX result verbatim to `httpx-url-only.txt` under the output root.
2. Take the URL **path** only (scheme, host, query string, and fragment
   stripped).
3. Exclude the URL when that path ends in `.js`, case-insensitively, so
   `/app.js?v=123` and `/APP.JS` are excluded.
4. Keep the URL when `js` merely appears in a hostname, a directory name, or a
   query parameter, and keep `.json`, `.jsx`, and `.js.map`.
5. Deduplicate **case-sensitively**, first occurrence wins.
6. Write `js-urls.txt` and `non-js-urls.txt`.

Verification: `js-urls.txt` plus `non-js-urls.txt` must equal the unique URL-only
rows, and no path in `non-js-urls.txt` may end in `.js`.

`processed/categories/javascript.txt` is never modified, regenerated, or
consumed here. It stays the JS Analysis input, and no JavaScript file is
downloaded.

## Phase 1 - passive classification

Classification uses token-boundary matching plus a host-label pass, so a keyword
inside an unrelated path (for example `/order/product` for `prod`) does not
match. Plain substring matching was rejected for exactly that reason.

| Group | Files | What it holds |
| --- | --- | --- |
| Technology extensions | `php.txt`, `asp.txt`, `aspx.txt`, `jsp.txt`, `jspx.txt`, `cfm.txt`, `cgi.txt` | URLs whose path ends in that technology extension |
| Configuration | `config.txt` | Config-like tokens and bundles |
| Admin and API surfaces | `admin-api.txt` | `admin`, `api`, `panel`, `dashboard` in paths or host labels |
| Internal and staging | `internal.txt` | `dev`, `test`, `stage`, `staging`, `prod`, `internal`, `private` |
| Debug surface | `debug-staging.txt` | `debug`, `test`, `dev`, `staging`, `sandbox`, `mock` |
| Sensitive files | `sensitive-file-candidates.txt` | `.env`, `.ini`, `.log`, `.bak`, `.backup`, `.old`, `.db`, `.sql`, `.json`, `.yml`, `.yaml` |
| Parameterized URLs | `parameterized.txt` | URLs carrying a query string |
| Redirect candidates | `redirect-candidates.txt` | `url`, `redirect`, `next`, `dest`, `callback`, `return`, `continue` parameters |
| Cloud | `cloud/cloud-urls.txt` | URLs on known cloud storage hosts |
| | `cloud/cloud-keyword-candidates.txt` | `aws`, `s3`, `bucket`, `gcp`, `azure`, `vault`, `token`, `apikey`, `secret` |
| | `cloud/aws-buckets.txt`, `cloud/gcp-buckets.txt`, `cloud/azure-accounts.txt` | Bucket and account names extracted from cloud URLs |
| GF redirect patterns | `gf-patterns/redirect-patterns.txt`, `gf-patterns/redirect.json` | Registered pattern set used for redirect matching |
| Origins | `git-exposure/origins.txt` | In-scope origins derived from the corpus |

All counts are recalculated from the current input. They are never forced to
match a previous run.

### GF pattern-equivalent matching

The `gf` tool is registered as **blocked** (upstream publishes no release
assets), so it is not installed and not executed. Its behaviour is reproduced
instead with the approved `gf-redirect-patterns` wordlist applied through
`grep -iE -f`, which is equivalent for this flat pattern set because `gf` joins
the patterns with `|` and runs `grep` with the pattern's own flags.

The pattern copy must be BOM-free: a leading BOM silently disables the first
pattern under `grep -f`.

## Phase 2 - verify passive output

Before any active check, confirm the counts are plausible and spot-check samples
of every category. If the passive output looks wrong, fix it and re-verify. No
active check ever runs on unverified data.

## Phase 3 - Git exposure

For each approved origin the stage requests `/.git/config`, `/.git/HEAD`, and
`/.git/index`.

A `200` is **not** evidence. For every `200` it:

1. requests a random nonexistent path and compares status and body length,
2. fetches `/.git/config` and searches for `[core]`,
   `repositoryformatversion`, `filemode`, and `bare =`,
3. stores bodies and headers and classifies the hit as `soft-404`, `catch-all`,
   or `candidate`.

No object enumeration, pack retrieval, or directory brute forcing is performed.

## Phase 4 - HTTP request smuggling

`smuggler` (git version `2be871e`) runs against each approved origin after a
reachability probe. It uses quiet mode, exit on first candidate, the default
configuration, one sequential raw socket, a per-host log, and a bounded timeout.
The target uses a trailing slash so the request line stays valid
(`POST /?cb=... HTTP/1.1`). Exhaustive configurations are skipped. Any PoC files
the tool writes are copied into the stage results directory and removed from the
tool tree.

Per-mutation progress is written to stdout in quiet mode, captured in
`http-request-smuggling/logs/<host>.out`. A header-only log file does not by
itself prove the mutations ran; the `.out` transcript is the evidence.

## Phase 5 - open redirect

The candidate set is the union of the operator keyword set and the registered GF
redirect pattern set. It is deduplicated at **endpoint** level
(`scheme`, `host`, `path`, sorted parameter names), because tracking values
otherwise turn thousands of rows into a handful of endpoints.

`openredirex` (git version `383aea0`) replaces every parameter value when `FUZZ`
is absent, so the input carries `FUZZ` only in redirect-type parameters and
leaves tracking parameters intact. Concurrency is pinned explicitly with `-c 10`
because the tool default is far too high.

`FOUND` means a redirect chain was observed, not a confirmed open redirect.

## Active check scope and exclusions

- Active checks run only against **approved origins** derived from the corpus.
- The flagged customer-owned hosts `admin`, `cp`, `webmail`, `pma`, and
  `intmail` are excluded from every active check while remaining in the passive
  outputs.
- Program `restrictions` are read first. If a restriction prohibits a check, it
  is marked `skipped` with the reason and the others continue.
- Authorization is the operator's selection of the program and its declared
  scope. There is no per-run `active` flag and no repeated confirmation.
- The stage uses conservative concurrency, bounded timeouts, and no large
  bodies. Anything that could affect availability is skipped and reported.

## Output structure and evidence

```text
programs/<program>/recon/urls/<run_id>/processed/url-triage/
├── httpx-url-only.txt              input copy, read-only source
├── js-urls.txt                     excluded JavaScript URLs
├── non-js-urls.txt                 authoritative triage input
├── php.txt, asp.txt, aspx.txt ...  passive classification
├── config.txt
├── admin-api.txt
├── internal.txt
├── debug-staging.txt
├── sensitive-file-candidates.txt
├── parameterized.txt
├── redirect-candidates.txt
├── cloud/
│   ├── cloud-urls.txt
│   ├── cloud-keyword-candidates.txt
│   ├── aws-buckets.txt
│   ├── gcp-buckets.txt
│   └── azure-accounts.txt
├── gf-patterns/
│   ├── redirect-patterns.txt       registered pattern set
│   └── redirect.json
├── git-exposure/
│   ├── origins.txt                 origins derived from the corpus
│   ├── approved-origins.txt        origins allowed for active checks
│   ├── httpx-git.txt               probe results
│   ├── git-200.txt                 every 200 response
│   ├── git-candidates.txt          surviving candidates
│   ├── classification.md           soft-404 / catch-all / candidate
│   └── bodies/                     stored bodies and headers
├── http-request-smuggling/
│   ├── hosts.txt, httpx-hosts.txt, alive-hosts.txt
│   ├── results/<host>.log          per-host tool log
│   └── logs/<host>.out             per-mutation stdout transcript
├── redirect/
│   ├── redirect-candidates.txt
│   ├── gf-redirect-matches.txt
│   ├── candidates-union.txt
│   ├── openredirex-candidates.txt
│   ├── openredirex-input.txt
│   └── openredirex-results.txt
├── logs/                           command logs and errors
├── counts.tsv                      path and count per artifact
└── summary.md                      full stage summary
```

The directory may also contain comparison or baseline subdirectories when the
operator reruns classification for auditing. They are evidence, not inputs.

## Execute

### Standalone

```bash
/url_triage <program> <run_id>
```

`$2` is optional and defaults to the newest URL run that contains
`processed/LiveURLs.txt`.

### Automatic

- **`/urls_enum <program>`** runs URL Enumeration first and then invokes URL
  Triage automatically with the same program, scope, and run ID, reading
  `processed/httpx-url-only.txt` and writing `processed/url-triage/`. Triage is
  skipped if enumeration did not return `completed`.
- **`/full_recon <program>`** runs Subdomain Enumeration, URL Enumeration, URL
  Triage, and JS Analysis as four separate ordered stages. URL Triage is Stage 3
  and runs exactly once per URL run.

The standalone command is preserved and still works for rerunning or resuming
triage on a specific run.

## What the stage returns

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

## Candidates are not vulnerabilities

A candidate file is a list of URLs worth looking at, nothing more:

- A `200` on `/.git/config` is usually a soft-404 or a catch-all route.
- `smuggler` reporting no candidate means no desync was observed in the tested
  mutation set, not a proof of safety.
- `openredirex` `FOUND` means a redirect chain exists, not that it is exploitable.
- Parameterized or admin-looking URLs are leads, not findings.

Anything confirmed is recorded by the operator under
`programs/<program>/targets/<target>/findings/` and only then becomes a
`Confirmed finding`.

## Next stage

```bash
/js-analysis <program> <run_id>
```

JS Analysis consumes `processed/categories/javascript.txt`, which this stage never
touches.