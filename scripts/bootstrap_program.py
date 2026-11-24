"""Create or reuse a program workspace from an operator wildcard scope.

This is NOT part of Phase 3 (``scripts/bbh``). It uses the frozen Phase 3
utilities as a library and calls the Phase 3 CLI to validate generated scope.

Guarantees:
- A wildcard argument is treated as an operator-declared scope only.
- An existing program is reused only when its scope already covers the wildcard.
- Existing program files are never modified.
- New program files are created in a staging directory and renamed into place
  only after scope validation succeeds.
- No program rules or restrictions are invented.

Exit codes:
  0  created or reused
  2  conflict or ambiguity; stop and explain
  3  invalid wildcard argument
  4  refused: target directory exists but is unusable
  5  unexpected input, template, or I/O failure
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bbh import BbhError  # noqa: E402
from bbh.scope import canonical_host, load_scope  # noqa: E402

EXIT_OK = 0
EXIT_CONFLICT = 2
EXIT_INVALID = 3
EXIT_REFUSED = 4
EXIT_ERROR = 5

SLUG_SAFE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
JSON_FENCE = re.compile(r"^```json[ \t]*$.*?^```[ \t]*$", re.S | re.M)
TEMPLATE_WARNING = re.compile(r"^> Template\..*?(?=\n\n)", re.S | re.M)


class BootstrapError(Exception):
    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_wildcard(value: str) -> tuple[str, str]:
    """Return (normalized wildcard, apex) or raise EXIT_INVALID."""

    text = (value or "").strip()
    if not text.startswith("*."):
        raise BootstrapError(
            "wildcard scope must start with '*.' (for example *.example.com)",
            EXIT_INVALID,
        )
    if "*" in text[2:] or "/" in text or ":" in text or "?" in text or "#" in text:
        raise BootstrapError("unsupported wildcard scope: %r" % value, EXIT_INVALID)
    if any(char.isspace() for char in text):
        raise BootstrapError("wildcard scope must not contain whitespace", EXIT_INVALID)

    apex = canonical_host(text[2:])
    if apex is None:
        raise BootstrapError(
            "wildcard scope has an invalid apex domain: %r" % value, EXIT_INVALID
        )
    try:
        ipaddress.ip_address(apex)
    except ValueError:
        pass
    else:
        raise BootstrapError("wildcard scope cannot be an IP address", EXIT_INVALID)

    return "*.%s" % apex, apex


def derive_slug(apex: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", apex).strip("-")
    if not slug:
        raise BootstrapError("cannot derive a program slug from %r" % apex, EXIT_ERROR)
    slug = slug[:63].rstrip("-")
    if not slug or not SLUG_SAFE.match(slug):
        raise BootstrapError("derived slug is invalid: %r" % slug, EXIT_ERROR)
    return slug


def program_dirs(root: Path) -> list[Path]:
    base = root / "programs"
    if not base.is_dir():
        raise BootstrapError("programs directory not found: %s" % base, EXIT_ERROR)
    return [
        item
        for item in sorted(base.iterdir())
        if item.is_dir() and item.name != "_template" and not item.name.startswith(".")
    ]


def coverage(scope, apex: str) -> dict:
    """Describe how an existing scope relates to the requested wildcard."""

    covers = False
    exact = False
    overlap = False
    excluded_all = False
    partial_exclusions: list[str] = []

    for entry in scope.in_scope:
        if entry.kind == "wildcard":
            if entry.host == apex:
                covers = True
                exact = True
                overlap = True
            elif apex.endswith("." + entry.host):
                covers = True
                overlap = True
            elif entry.host.endswith("." + apex):
                overlap = True
        elif entry.kind in ("host", "ip", "url") and entry.host == apex:
            overlap = True

    for entry in scope.out_of_scope:
        if entry.kind == "wildcard":
            if entry.host == apex or apex.endswith("." + entry.host):
                excluded_all = True
                overlap = True
            elif entry.host.endswith("." + apex):
                overlap = True
                partial_exclusions.append(entry.raw)
        elif entry.kind in ("host", "ip") and entry.host == apex:
            overlap = True

    return {
        "covers": covers,
        "exact": exact,
        "overlap": overlap,
        "excluded_all": excluded_all,
        "partial_exclusions": partial_exclusions,
    }


def resolve(
    root: Path, wildcard: str, apex: str, slug: str
) -> tuple[Optional[dict], list[dict], list[str]]:
    """Find a reusable program or list conflicts. Never writes."""

    matches: list[dict] = []
    conflicts: list[dict] = []
    warnings: list[str] = []

    for directory in program_dirs(root):
        scope_path = directory / "scope.md"
        if not scope_path.is_file():
            if directory.name == slug:
                conflicts.append(
                    {
                        "program": directory.name,
                        "reason": "program directory exists but has no scope.md",
                    }
                )
            continue

        try:
            scope = load_scope(scope_path)
        except (BbhError, OSError) as exc:
            if directory.name == slug:
                conflicts.append(
                    {
                        "program": directory.name,
                        "reason": "existing scope.md is unreadable or invalid: %s" % exc,
                    }
                )
            else:
                warnings.append(
                    "%s: skipped unreadable scope.md (%s)" % (directory.name, exc)
                )
            continue

        if scope.program != directory.name:
            if directory.name == slug:
                conflicts.append(
                    {
                        "program": directory.name,
                        "reason": (
                            "scope.program %r does not match directory name %r"
                            % (scope.program, directory.name)
                        ),
                    }
                )
            else:
                warnings.append(
                    "%s: scope.program %r does not match directory name; ignored"
                    % (directory.name, scope.program)
                )
            continue

        relation = coverage(scope, apex)

        if relation["excluded_all"]:
            conflicts.append(
                {
                    "program": directory.name,
                    "reason": (
                        "requested wildcard %s is excluded by this program's "
                        "out_of_scope" % wildcard
                    ),
                }
            )
            continue

        if relation["covers"]:
            matches.append(
                {
                    "program": directory.name,
                    "directory": directory,
                    "scope": scope,
                    "exact": relation["exact"],
                    "partial_exclusions": relation["partial_exclusions"],
                }
            )
            continue

        if relation["overlap"] or directory.name == slug:
            conflicts.append(
                {
                    "program": directory.name,
                    "reason": (
                        "existing scope does not cover requested wildcard %s; "
                        "refusing to expand it automatically" % wildcard
                    ),
                }
            )

    exact_matches = [item for item in matches if item["exact"]]
    if len(exact_matches) == 1:
        chosen = exact_matches[0]
    elif len(exact_matches) > 1:
        conflicts.append(
            {
                "program": ", ".join(item["program"] for item in exact_matches),
                "reason": "multiple programs declare the same wildcard %s" % wildcard,
            }
        )
        chosen = None
    elif len(matches) == 1:
        chosen = matches[0]
    elif len(matches) > 1:
        conflicts.append(
            {
                "program": ", ".join(item["program"] for item in matches),
                "reason": "multiple programs cover %s; choose one explicitly" % wildcard,
            }
        )
        chosen = None
    else:
        chosen = None

    return chosen, conflicts, warnings


def render_scope(template: str, apex: str, slug: str, wildcard: str, today: str) -> str:
    data = {
        "program": slug,
        "in_scope": [wildcard],
        "out_of_scope": [],
        "allowed_ports": [],
        "restrictions": [],
        "updated": today,
        "notes": (
            "Operator-declared wildcard scope created automatically on %s from "
            "%s. The wildcard covers the apex %s and every subdomain. No "
            "official program authorization, "
            "platform entry, or policy has been verified; restrictions are "
            "unknown." % (today, wildcard, apex)
        ),
    }
    block = json.dumps(data, indent=2)

    text = template
    text = TEMPLATE_WARNING.sub(
        "> Authoritative source for operator-declared assets. Do not test\n"
        "> anything that is not clearly covered here.",
        text,
        count=1,
    )
    text = JSON_FENCE.sub("```json\n%s\n```" % block, text, count=1)
    text = text.replace("# Scope — <program name>", "# Scope — %s" % apex)
    text = text.replace("<program-slug>", slug).replace("<program name>", apex)
    text = text.replace(
        "## In scope (prose)\n\nNot provided",
        "## In scope (prose)\n\n- `%s` — the apex `%s` and every subdomain "
        "at any depth." % (wildcard, apex),
    )
    text = text.replace(
        "## Out of scope / exclusions (prose)\n\nNot provided",
        "## Out of scope / exclusions (prose)\n\nNot provided.",
    )
    text = text.replace(
        "## Testing restrictions\n\nNot provided",
        "## Testing restrictions\n\nNot provided. Do not run restricted testing "
        "until the operator supplies program rules.",
    )
    text = text.rstrip() + (
        "\n\n## Provenance\n\n"
        "| Item | Value |\n"
        "| --- | --- |\n"
        "| Created by | Automatic program bootstrap, %s |\n"
        "| Source of scope | Operator-declared wildcard `%s` passed on a recon "
        "command. No official program scope, platform entry, or policy has been "
        "verified. |\n"
        "| Apex decision | Included. `%s` is matched by `%s`. |\n"
        "| Structure | Mirrors `programs/_template/scope.md`. |\n"
        % (today, wildcard, apex, wildcard)
    )
    return text


def render_program(template: str, apex: str, slug: str, wildcard: str, today: str) -> str:
    text = template
    text = TEMPLATE_WARNING.sub(
        "> Auto-created from an operator-declared wildcard. Unknown fields stay\n"
        "> `Not provided`; never invent program rules.",
        text,
        count=1,
    )
    text = text.replace("# Program: <program name>", "# Program: %s" % apex)
    text = text.replace("<program-slug>", slug).replace("<program name>", apex)
    text = text.replace("| Date added | Not provided |", "| Date added | %s |" % today)
    text = text.replace(
        "| Handles / assets summary | Not provided |",
        "| Handles / assets summary | `%s` (operator-declared; apex and subdomains) |"
        % wildcard,
    )
    text = text.replace(
        "## Operational notes\n\n- Not provided",
        "## Operational notes\n\n"
        "- Auto-created by wildcard bootstrap on %s from `%s`.\n"
        "- Scope is operator-declared only. No official program authorization, "
        "platform entry, or policy has been verified.\n"
        "- Program rules, rate limits, and prohibited techniques are unknown. "
        "Do not run restricted testing until the operator supplies them."
        % (today, wildcard),
    )
    return text


def validate_scope(scope_path: Path, apex: str, slug: str) -> None:
    """Validate the generated scope with the frozen Phase 3 CLI and library."""

    try:
        scope = load_scope(scope_path)
    except BbhError as exc:
        raise BootstrapError("generated scope failed to parse: %s" % exc, EXIT_ERROR)
    if scope.program != slug:
        raise BootstrapError(
            "generated scope program %r does not match slug %r"
            % (scope.program, slug),
            EXIT_ERROR,
        )

    env = os.environ.copy()
    launcher = SCRIPT_DIR / "bbh_cli.py"
    checks = (
        ("x.%s" % apex, "in_scope"),
        (apex, "in_scope"),
        ("deep.x.%s" % apex, "in_scope"),
    )
    for host, expected in checks:
        process = subprocess.run(
            [
                sys.executable,
                str(launcher),
                "scope",
                "check",
                "--scope",
                str(scope_path),
                "--kind",
                "host",
                "--value",
                host,
            ],
            cwd=str(WORKSPACE),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        verdict = (
            process.stdout.strip().splitlines()[0] if process.stdout.strip() else ""
        )
        if process.returncode != 0 or verdict != expected:
            raise BootstrapError(
                "generated scope validation failed for %r: expected %s, got %r (%s)"
                % (host, expected, verdict, process.stderr.strip()),
                EXIT_ERROR,
            )


def build_program(
    root: Path,
    staging: Path,
    apex: str,
    slug: str,
    wildcard: str,
    today: str,
) -> list[str]:
    template_dir = root / "programs" / "_template"
    for relative in ("scope.md", "program.md", "recon/summary.md"):
        if not (template_dir / relative).is_file():
            raise BootstrapError(
                "template file missing: %s" % (template_dir / relative), EXIT_ERROR
            )

    staging.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    scope_path = staging / "scope.md"
    scope_path.write_text(
        render_scope(
            (template_dir / "scope.md").read_text(encoding="utf-8"),
            apex,
            slug,
            wildcard,
            today,
        ),
        encoding="utf-8",
    )
    created.append("scope.md")

    program_path = staging / "program.md"
    program_path.write_text(
        render_program(
            (template_dir / "program.md").read_text(encoding="utf-8"),
            apex,
            slug,
            wildcard,
            today,
        ),
        encoding="utf-8",
    )
    created.append("program.md")

    summary_source = (template_dir / "recon/summary.md").read_text(encoding="utf-8")
    summary_path = staging / "recon" / "summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        summary_source.replace("<program name>", apex), encoding="utf-8"
    )
    created.append("recon/summary.md")

    for relative in (
        "recon/subdomains",
        "recon/urls",
        "recon/javascript",
        "recon/content",
        "recon/runs",
        "targets",
        "reports",
    ):
        directory = staging / relative
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".gitkeep").write_text("", encoding="utf-8")

    return created


def run(root: Path, wildcard_value: str, dry_run: bool) -> dict:
    wildcard, apex = parse_wildcard(wildcard_value)
    slug = derive_slug(apex)
    today = datetime.date.today().isoformat()

    chosen, conflicts, warnings = resolve(root, wildcard, apex, slug)

    base = {
        "wildcard": wildcard,
        "apex": apex,
        "requested_slug": slug,
        "warnings": warnings,
    }

    if conflicts:
        return {
            **base,
            "ok": False,
            "status": "conflict",
            "error": (
                "requested wildcard conflicts with existing program data; "
                "no files were changed"
            ),
            "conflicts": conflicts,
            "matches": [
                {"program": item["program"], "exact": item["exact"]}
                for item in ([chosen] if chosen else [])
            ],
        }

    if chosen is not None:
        scope = chosen["scope"]
        return {
            **base,
            "ok": True,
            "status": "reused",
            "program": chosen["program"],
            "program_dir": str(chosen["directory"].resolve()),
            "scope": str((chosen["directory"] / "scope.md").resolve()),
            "scope_sha256": scope.sha256,
            "in_scope": list(scope.data.get("in_scope", [])),
            "out_of_scope": list(scope.data.get("out_of_scope", [])),
            "allowed_ports": list(scope.data.get("allowed_ports", [])),
            "restrictions": list(scope.data.get("restrictions", [])),
            "narrowed": not chosen["exact"],
            "partial_exclusions": chosen["partial_exclusions"],
        }

    programs = root / "programs"
    target = programs / slug
    if target.exists():
        return {
            **base,
            "ok": False,
            "status": "refused",
            "error": "target program directory already exists: %s" % target,
        }

    staging = Path(
        tempfile.mkdtemp(prefix=".bootstrap-%s-" % slug, dir=str(programs))
    )
    try:
        created = build_program(root, staging, apex, slug, wildcard, today)
        validate_scope(staging / "scope.md", apex, slug)
        scope_hash = sha256_file(staging / "scope.md")

        if dry_run:
            return {
                **base,
                "ok": True,
                "status": "created",
                "dry_run": True,
                "program": slug,
                "program_dir": str(target.resolve()),
                "scope": str((target / "scope.md").resolve()),
                "scope_sha256": scope_hash,
                "in_scope": [wildcard],
                "out_of_scope": [],
                "allowed_ports": [],
                "restrictions": [],
                "created_files": created,
            }

        try:
            staging.rename(target)
        except OSError as exc:
            raise BootstrapError(
                "cannot move validated program into place: %s" % exc, EXIT_REFUSED
            )
        staging = None

        return {
            **base,
            "ok": True,
            "status": "created",
            "program": slug,
            "program_dir": str(target.resolve()),
            "scope": str((target / "scope.md").resolve()),
            "scope_sha256": scope_hash,
            "in_scope": [wildcard],
            "out_of_scope": [],
            "allowed_ports": [],
            "restrictions": [],
            "created_files": created,
        }
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bootstrap_program",
        description=(
            "Create or reuse a program workspace from an operator wildcard scope"
        ),
    )
    parser.add_argument(
        "--wildcard",
        required=True,
        help="operator-declared wildcard scope, for example *.example.com",
    )
    parser.add_argument(
        "--root",
        default=str(WORKSPACE),
        help="workspace root containing programs/ (default: repository root)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve, render, and validate without creating program files",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        result = run(root, args.wildcard, args.dry_run)
    except BootstrapError as exc:
        emit({"ok": False, "status": "error", "error": str(exc)})
        return exc.exit_code
    except (BbhError, OSError) as exc:
        emit({"ok": False, "status": "error", "error": str(exc)})
        return EXIT_ERROR

    emit(result)
    if not result.get("ok"):
        return EXIT_CONFLICT if result.get("status") == "conflict" else EXIT_REFUSED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
