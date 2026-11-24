# URL Enumeration

This stage builds the URL list for a program: it collects URLs, cleans them,
keeps only the ones inside scope, and finally keeps only the live HTTP 200 ones.

## What it does

- Collects every URL it can find for the in-scope hosts.
- Merges, normalizes, deduplicates, and scope-filters them.
- Categorizes them and separates static files (images, CSS, fonts).
- Probes the rest with HTTPX and keeps the live HTTP 200 URLs.

## Workflow

1. **Collect** URLs with 5 tools at the same time.
2. **Merge** all raw output into `raw/all.txt`, then keep only lines starting
   with `http://` or `https://` in `raw/all.urls.txt`.
3. **Copy** that into `processed/AllURLs.txt` (unfiltered, duplicates kept).
4. **Normalize** into `processed/normalized.txt`.
5. **Deduplicate** into `processed/UniqueURLs.txt`.
6. **Scope filter** into `processed/ScopedURLs.txt`; anything outside scope goes
   to `rejected/out-of-scope.txt`.
7. **Copy** `ScopedURLs.txt` to `processed/urls.txt`.
8. **Categorize** into `processed/categories/`.
9. **Filter static assets**: testable URLs go to `processed/TestableURLs.txt`,
   static files to `processed/StaticAssetsURLs.txt`.
10. **Probe** `TestableURLs.txt` with HTTPX into
    `processed/httpx-url-only.txt`, then copy it to `processed/LiveURLs.txt`.

## Tools

| Step | Tool | Version | What it does |
| --- | --- | --- | --- |
| Collect (archive) | `waybackurls` | 0.1.0 | URLs from the Wayback Machine |
| Collect (archive) | `gau` | 2.2.4 | URLs from public archives |
| Collect (archive) | `waymore` | 8.9 | More archive URLs and responses |
| Collect (crawl) | `katana` | 1.8.0 | Crawls the live sites |
| Collect (crawl) | `gospider` | 1.1.6 | Crawls sites, sitemaps, robots.txt |
| Probe | `httpx-urls` | 1.12.0 | Checks which URLs are live |

`hakrawler` is still `proposed` in `shared/tools.json`, so it is never run.

## HTTPX output is URL-only

URL Enumeration probes with this command:

```bash
httpx -silent -nc -mc 200 -retries 2 -rl 50 -threads 25 \
  < processed/TestableURLs.txt > processed/httpx-url-only.txt
```

- Output is **one URL per line** — no status code, no title, no content length,
  no technology name.
- `-mc 200` keeps only HTTP 200 responses.
- Every URL in the input is still probed.
- `LiveURLs.txt` is just a copy of `httpx-url-only.txt`.

Older runs (for example `20261112-205941-urls`) still show metadata rows in
`LiveURLs.txt`; new runs do not.

## JavaScript URLs

JavaScript URLs are collected by the crawlers and archive tools, and they are
**not thrown away**:

- They stay in `processed/categories/javascript.txt`.
- The static filter never removes `.js` or `.js.map` files.
- They stay in the HTTPX URL-only output.

They are preserved for the later **JS Analysis** stage (`/js_analysis`).

## Output structure

```text
programs/<program>/recon/urls/<run_id>/
├── inputs/
│   ├── alive.txt                 host list given to the tools
│   └── scheme-https.txt          same hosts as https:// URLs
├── raw/                          untouched output of each tool
│   ├── waybackurls.txt gau.txt katana.txt gospider.txt waymore.txt
│   ├── all.txt                   all raw files merged, unfiltered
│   └── all.urls.txt              only the URL lines from all.txt
├── processed/
│   ├── AllURLs.txt               every URL found, duplicates kept
│   ├── normalized.txt            normalized URLs
│   ├── UniqueURLs.txt            deduplicated URLs
│   ├── ScopedURLs.txt            in-scope URLs only
│   ├── urls.txt                  copy of ScopedURLs.txt
│   ├── TestableURLs.txt          URLs to probe (static files removed)
│   ├── StaticAssetsURLs.txt      static files that were removed
│   ├── httpx-url-only.txt        live HTTP 200 URLs, one per line
│   ├── LiveURLs.txt              copy of httpx-url-only.txt
│   ├── categories/               javascript.txt, api.txt, static.txt, other.txt,
│   │                             with-parameters.txt, parameters.txt
│   └── hosts/                    host counts and liveness labels
├── rejected/
│   ├── out-of-scope.txt          URLs outside the scope file
│   └── ambiguous.txt             URLs that need a human decision
├── logs/                         command logs and errors
└── summary.md                    short summary of this run
```

## Run it

```bash
/urls_enum <program>
```

Or with your own host list:

```bash
/urls_enum /path/to/alive.txt <program>
```

Where to find the results:

```text
programs/<program>/recon/urls/<run_id>/summary.md        short run summary
programs/<program>/recon/urls/<run_id>/processed/        all result files
programs/<program>/recon/runs/<run_id>/run.json          commands, tools, timings
```

## Next stage

`/url_triage <program> <run_id>` — classifies the live URLs and runs the
non-disruptive checks. URL Enumeration never runs triage itself.
