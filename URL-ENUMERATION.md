# URL Enumeration

Stage 2 of the reconnaissance pipeline. It collects every known URL for the
in-scope hosts, cleans and filters them, categorizes them, and probes which URLs
are live.

This stage **does not test for vulnerabilities**. It builds the URL corpus.

```text
Subdomain Enumeration  ->  URL Enumeration  ->  URL Triage  ->  JS Analysis
        (hosts)                 (URLs)            (candidates)
```

## Purpose

- Collect URLs from public archives and from crawling the live sites.
- Normalize, deduplicate, and scope-filter the whole corpus.
- Separate testable URLs from static assets.
- Keep only live HTTP 200 URLs, in URL-only form, for the next stage.
- Preserve JavaScript URLs for JS Analysis.

## Inputs

- program slug, program directory, and absolute `scope.md` path
- an explicit host list, or the newest program
  `recon/subdomains/<run_id>/processed/alive.txt`
  (fallback: `processed/subdomains.txt`)
- optional run ID to resume

The stage copies the host list into `inputs/alive.txt` and derives
`inputs/scheme-https.txt` (the same hosts as `https://` URLs). Both files are
LF-only. The source list is never modified.

## Workflow

1. **Preflight** - verify program context, parse the scope block, load the
   approved `stage: urls` tools.
2. **Prepare inputs** - write `inputs/alive.txt` and `inputs/scheme-https.txt`.
3. **Collect** - run every approved source; at most **3 tools run
   concurrently**, with a `wait` barrier before anything downstream starts. Each
   tool writes its own raw file and keeps its registered timeout. A failing tool
   never discards another tool's output.
4. **Merge**:

   ```bash
   find <run>/raw -maxdepth 1 -name '*.txt' ! -name 'all.txt' -exec cat {} + > <run>/raw/all.txt
   grep -E '^https?://' <run>/raw/all.txt > <run>/raw/all.urls.txt
   ```

   `raw/all.txt` stays the literal merge for debugging. Only URL-shaped lines
   continue.

5. **Preserve the corpus**: copy `raw/all.urls.txt` to `processed/AllURLs.txt`
   (every URL, duplicates kept, never filtered).
6. **Normalize**:

   ```bash
   python scripts/bbh_cli.py normalize --kind url \
     -i <run>/processed/AllURLs.txt -o <run>/processed/normalized.txt
   ```

7. **Deduplicate**:

   ```bash
   python scripts/bbh_cli.py dedupe \
     -i <run>/processed/normalized.txt -o <run>/processed/UniqueURLs.txt
   ```

8. **Scope validation**:

   ```bash
   python scripts/bbh_cli.py scope check --scope <scope.md> --kind url \
     -i <run>/processed/UniqueURLs.txt \
     --in <run>/processed/ScopedURLs.txt \
     --out <run>/rejected/out-of-scope.txt \
     --review <run>/rejected/ambiguous.txt
   ```

   `processed/urls.txt` is a copy of `ScopedURLs.txt` and satisfies the shared
   stage contract.

9. **Host provenance** - list in-scope hosts, and label which of them came from
   the alive input and which were discovered by crawlers but never
   liveness-verified. `inputs/alive.txt` is never expanded.
10. **Categorize**:

    ```bash
    python scripts/bbh_cli.py classify --kind url \
      -i <run>/processed/urls.txt --out-dir <run>/processed/categories
    ```

11. **Filter static assets** - remove the shared `static` category from the
    testable list:

    ```bash
    comm -23 <(sort -u <run>/processed/urls.txt) <(sort -u <run>/processed/categories/static.txt) > <run>/processed/TestableURLs.txt
    comm -12 <(sort -u <run>/processed/urls.txt) <(sort -u <run>/processed/categories/static.txt) > <run>/processed/StaticAssetsURLs.txt
    ```

    `TestableURLs.txt` plus `StaticAssetsURLs.txt` must equal `urls.txt`.
    `.map` files stay in the JavaScript category and are never removed, and
    JavaScript, JSON, XML, and API endpoints are never removed.

12. **Live probe** - one `httpx-urls` pass over `TestableURLs.txt` (see below).
13. **Record** - update `run.json`, write `summary.md`, and append a stage
    section to `programs/<program>/recon/summary.md`.

## Collection tools

Versions are the ones recorded in `shared/tools.json`; `hakrawler` is proposed and inactive.

| Tool | Version | Input | Raw output | Role |
| --- | --- | --- | --- | --- |
| `waybackurls` | 0.1.0 | `inputs/alive.txt` | `raw/waybackurls.txt` | URLs archived by the Wayback Machine |
| `gau` | 2.2.4 | `inputs/alive.txt` | `raw/gau.txt` | URLs from public archives |
| `katana` | 1.8.0 | `inputs/alive.txt` | `raw/katana.txt` | Crawler with JS crawling, known files, depth 5, form extraction |
| `gospider` | 1.1.6 | `inputs/scheme-https.txt` | `raw/gospider.txt` | Crawler covering sitemaps, robots.txt, and other sources |
| `waymore` | 8.9 | `inputs/alive.txt` | `raw/waymore.txt` | Wider archive coverage (mode U, limit 1000) |
| `hakrawler` | git:2.1 | `inputs/scheme-https.txt` | `raw/hakrawler.txt` | **Proposed, not active.** Never installed or executed. |

`waybackurls`, `gau`, and `waymore` are archive sources. `katana` and
`gospider` are live crawlers. `hakrawler` appears in the registry only; it is not
part of the current pipeline.

## Normalization, deduplication, scope filtering

The shared utilities enforce one policy for every stage:

- Normalization lowercases scheme and host, drops default ports, collapses repeated
  slashes in the path, sorts query parameters, and removes the fragment.
- Deduplication is case-sensitive; case-insensitive dedup would merge distinct
  paths and is rejected.
- `out_of_scope` in `scope.md` always wins over `in_scope`.
- Anything not clearly covered goes to `rejected/`, never into the corpus.

## Categorization and static assets

`classify` produces six files plus a parameter list:

| File | Content |
| --- | --- |
| `categories/javascript.txt` | JavaScript URLs and `.map` files |
| `categories/api.txt` | API endpoints |
| `categories/with-parameters.txt` | URLs carrying query parameters |
| `categories/parameters.txt` | Unique parameter names |
| `categories/static.txt` | Images, CSS, fonts, and similar assets |
| `categories/other.txt` | Everything else |

Only `static.txt` is removed from the testable list. JavaScript URLs stay in the
corpus and in the HTTPX output.

## HTTPX probing (URL-only)

The URL stage uses its own registry entry, `httpx-urls` (version 1.12.0). It is
never used as a collection source, and the `stage: alive` `httpx` entry used by
Subdomain Enumeration is not used here.

```bash
httpx -silent -nc -mc 200 -retries 2 -rl 50 -threads 25 \
  < processed/TestableURLs.txt > processed/httpx-url-only.txt
```

| Flag | Purpose |
| --- | --- |
| `-silent -nc` | Plain output, no color |
| `-mc 200` | Keep HTTP 200 responses only (server-side equivalent of the earlier `[200]` grep) |
| `-retries 2` | Retry before dropping a request |
| `-rl 50` | 50 requests per second |
| `-threads 25` | 25 concurrent workers |

The output is **one bare URL per line**: no status code, no content length, no
page title, no technology name. Every URL in the input is still probed, and the
HTTP 200 selection is preserved.

`processed/LiveURLs.txt` is a byte-identical copy of `processed/httpx-url-only.txt`
and is kept for compatibility. Both contain the same HTTP 200 URLs.

Verify before continuing: every line starts with `http://` or `https://`, and no
line contains `[NNN]` metadata.

## JavaScript URL preservation

JavaScript URLs are collected by the crawlers and archive tools, and they are not
discarded:

- They stay in `processed/categories/javascript.txt`, which is the JS Analysis
  input.
- The static filter never removes `.js` or `.js.map`.
- They remain in `httpx-url-only.txt`.

No JavaScript file is downloaded in this stage.

## Output structure

```text
programs/<program>/recon/urls/<run_id>/
├── inputs/
│   ├── alive.txt                 host list given to the tools
│   └── scheme-https.txt          same hosts as https:// URLs
├── raw/
│   ├── waybackurls.txt           one file per source
│   ├── gau.txt
│   ├── katana.txt
│   ├── gospider.txt
│   ├── waymore.txt
│   ├── all.txt                   literal merge of every raw file
│   └── all.urls.txt              only the URL-shaped lines
├── processed/
│   ├── AllURLs.txt               every URL, duplicates kept, unfiltered
│   ├── normalized.txt            normalized URLs
│   ├── UniqueURLs.txt            deduplicated URLs
│   ├── ScopedURLs.txt            in-scope URLs only
│   ├── urls.txt                  copy of ScopedURLs.txt
│   ├── TestableURLs.txt          URLs to probe (static assets removed)
│   ├── StaticAssetsURLs.txt      static assets that were removed
│   ├── httpx-url-only.txt        live HTTP 200 URLs, one per line
│   ├── LiveURLs.txt              copy of httpx-url-only.txt
│   ├── categories/               javascript, api, static, other,
│   │                             with-parameters, parameters
│   ├── hosts/                    in-scope hosts and their provenance
│   └── url-triage/               created by the URL Triage stage
├── rejected/
│   ├── out-of-scope.txt          URLs outside the scope file
│   └── ambiguous.txt             URLs needing an operator decision
├── logs/                         per-tool stdout, stderr, metrics
└── summary.md                    counts, tools, skips, notes

programs/<program>/recon/runs/<run_id>/run.json    run metadata
programs/<program>/recon/summary.md                program-wide stage summary
```

## Execute

```bash
# standard: enumeration, then URL Triage on the same run
/urls_enum <program>

# explicit host list first, program slug second
/urls_enum /path/to/alive.txt <program>

# declare a wildcard scope (bootstraps a new program workspace)
/urls_enum *.example.com
```

### Automatic URL Triage

`/urls_enum` is a two-stage command:

1. It runs URL Enumeration in a child session and waits for completion.
2. If and only if URL Enumeration returns `completed`, it immediately launches
   `url-triager` with the **same** program, scope, and run ID, using
   `processed/httpx-url-only.txt` as input and `processed/url-triage/` as output
   root.

You do not need to run `/url_triage` after `/urls_enum`. If enumeration fails or
is blocked, triage does not run, and the command reports the failure instead.

`/full_recon` is different: it runs URL Enumeration and URL Triage as two
separate stages, so triage still runs exactly once per URL run.

## What the stage returns

`/urls_enum` returns one combined block covering both stages:

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
Files: recon/urls/<run_id>/..., processed/url-triage/{counts.tsv,summary.md}, runs/<run_id>/run.json
```

## Next stage

URL Triage runs automatically as part of `/urls_enum`. JS Analysis remains a
separate command and consumes `processed/categories/javascript.txt`:

```bash
/js-analysis <program> <run_id>
```