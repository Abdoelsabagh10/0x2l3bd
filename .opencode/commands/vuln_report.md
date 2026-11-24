---
description: Review a finding or draft a report in a background child session
agent: report
subagent: true
---

Prepare or review a vulnerability report. Draft only. Never submit.

## Arguments

- `$1` — program slug (required)
- `$2` — finding file path, or `review` to review a finding the operator will
  reference, or `draft` to draft from a path given as `$3`
- `$3` — optional finding path when `$2` is `review` or `draft`

## Resolve inputs yourself

Do not rely on the parent conversation. Resolve everything from disk:

1. Program slug: `$1`. If empty, stop and return `blocked: program slug required`.
2. Program directory: `programs/$1`. Require `program.md`. If missing, stop and
   return `blocked: program context missing`.
3. Scope file: absolute path to `programs/$1/scope.md`.
4. Mode: `review` or `draft`. If unclear, default to `review`.
5. Finding path: `$2` when it is a path, otherwise `$3`. The path must exist.
   If no path is provided, stop and ask the operator for it.
6. Template: `programs/$1/report-template.md` if present. If absent in draft
   mode, ask the operator for the required format before drafting.
7. Report the resolved absolute paths at the top of your summary.

## Preconditions

- The finding must relate to an in-scope asset. Verify with the shared scope
  utility when available; otherwise state that scope was checked manually.
- Never modify `scope.md` or `program.md`.

## Execute

Follow the agent instructions for the selected mode. In review mode, produce a
readiness verdict and a specific list of missing evidence. In draft mode, write
only what the evidence supports and save to
`programs/$1/reports/<YYYY-MM-DD>-<short-slug>.md`.

## Return

Return only the `Stage result` block defined in the agent instructions. Do not
include the full draft text in the parent conversation; return its path.
