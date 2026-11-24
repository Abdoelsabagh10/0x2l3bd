# Scope — <program name>

> Template. This file is the authoritative source for authorized assets. Do not
> test anything that is not clearly covered here. Replace the example block and
> remove this warning before using the program.

## Machine-readable scope (required)

The first fenced `json` block in this file is parsed by the shared utilities.
If it is missing, invalid, or ambiguous, every automated stage must refuse to
run and ask the operator.

```json
{
  "program": "<program-slug>",
  "in_scope": [],
  "out_of_scope": [],
  "allowed_ports": [],
  "restrictions": [],
  "updated": "YYYY-MM-DD",
  "notes": "Template only. Not a real scope."
}
```

### Field semantics

- `in_scope` entries may be:
  - `example.com` — that exact host only
  - `*.example.com` — `example.com` itself and any subdomain at any depth
  - `https://api.example.com/v1` — scheme, host, and path prefix
  - `203.0.113.10` — exact IP literal
- `out_of_scope` always wins over `in_scope`, including for subdomains of an
  in-scope wildcard.
- `allowed_ports` empty means the scope file does not restrict ports. A non-empty
  list means only those ports may be used.
- `restrictions` are human-readable limits that scripts cannot enforce. They must
  be shown to the operator before every run.
- CIDR ranges and regular expressions are not supported in this version and must
  be expanded by the operator before being added.

## In scope (prose)

Not provided

## Out of scope / exclusions (prose)

Not provided

## Testing restrictions

Not provided

## Ambiguity handling

- An asset that is not clearly covered is out of scope until the operator
  confirms it in writing.
- A hostname that merely contains an in-scope string is not in scope.
- If the prose here and the JSON block disagree, stop and ask the operator.
