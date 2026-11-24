"""Command line entry point for the shared bbh utilities."""

from __future__ import annotations

import argparse
import json
import sys

from . import BbhError, InputError
from .classify import classify_lines
from .dedupe import dedupe_lines
from .normalize import canonical_url, normalize_host_line, normalize_url_line
from .runs import STAGES, init_run, verify_run
from .scope import canonical_host, load_scope
from .util import read_lines, write_lines

EXIT_OK = 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bbh", description="Deterministic scope, filtering and run utilities"
    )
    parser.add_argument("--version", action="version", version="bbh 1.0.0")
    commands = parser.add_subparsers(dest="command", required=True)

    runs = commands.add_parser("runs", help="run metadata")
    run_actions = runs.add_subparsers(dest="action", required=True)

    run_init = run_actions.add_parser("init", help="create or resume a run")
    run_init.add_argument("--program", required=True)
    run_init.add_argument("--stage", required=True, choices=list(STAGES))
    run_init.add_argument("--scope", required=True)
    run_init.add_argument("--run-id", dest="run_id")

    run_verify = run_actions.add_parser("verify", help="verify stage outputs")
    run_verify.add_argument("--program", required=True)
    run_verify.add_argument("--run-id", dest="run_id", required=True)
    run_verify.add_argument("--stage", required=True, choices=list(STAGES))

    normalize = commands.add_parser("normalize", help="canonicalize hosts or URLs")
    normalize.add_argument("--kind", required=True, choices=["host", "url"])
    normalize.add_argument("-i", "--input", required=True)
    normalize.add_argument("-o", "--output", required=True)

    scope = commands.add_parser("scope", help="scope decisions")
    scope_actions = scope.add_subparsers(dest="action", required=True)
    check = scope_actions.add_parser("check", help="check hosts or URLs")
    check.add_argument("--scope", required=True)
    check.add_argument("--kind", required=True, choices=["host", "url"])
    check.add_argument("-i", "--input")
    check.add_argument("--in", dest="in_output")
    check.add_argument("--out", dest="out_output")
    check.add_argument("--review", dest="review_output")
    check.add_argument("--value")

    dedupe = commands.add_parser("dedupe", help="remove duplicate lines")
    dedupe.add_argument("-i", "--input", required=True)
    dedupe.add_argument("-o", "--output", required=True)

    classify = commands.add_parser("classify", help="categorize URLs")
    classify.add_argument("--kind", required=True, choices=["url"])
    classify.add_argument("-i", "--input", required=True)
    classify.add_argument("--out-dir", dest="out_dir", required=True)

    return parser


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")


def cmd_runs_init(args: argparse.Namespace) -> int:
    result = init_run(args.program, args.stage, args.scope, args.run_id)
    emit(result)
    return EXIT_OK


def cmd_runs_verify(args: argparse.Namespace) -> int:
    result, code = verify_run(args.program, args.run_id, args.stage)
    emit(result)
    return code


def cmd_normalize(args: argparse.Namespace) -> int:
    lines = read_lines(args.input)
    if args.kind == "host":
        output = [normalize_host_line(line) for line in lines]
    else:
        output = [normalize_url_line(line) for line in lines]
    output = [line for line in output if line]

    status = write_lines(args.output, output)
    emit(
        {
            "ok": True,
            "command": "normalize",
            "kind": args.kind,
            "input": args.input,
            "output": args.output,
            "count": len(output),
            "write": status,
        }
    )
    return EXIT_OK


def _scope_decision(scope, kind: str, value: str):
    if kind == "host":
        return scope.check_host(value)
    return scope.check_url(value)


def cmd_scope_check(args: argparse.Namespace) -> int:
    scope = load_scope(args.scope)

    if args.value is not None:
        result = _scope_decision(scope, args.kind, args.value)
        sys.stdout.write(result.verdict + "\n")
        sys.stderr.write("reason: %s\n" % result.reason)
        return EXIT_OK

    missing = [
        name
        for name, value in (
            ("-i/--input", args.input),
            ("--in", args.in_output),
            ("--out", args.out_output),
            ("--review", args.review_output),
        )
        if not value
    ]
    if missing:
        raise InputError("missing required arguments: %s" % ", ".join(missing))

    in_scope = []
    out_of_scope = []
    ambiguous = []

    for line in read_lines(args.input):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        result = _scope_decision(scope, args.kind, text)
        if result.verdict == "in_scope":
            if args.kind == "host":
                in_scope.append(canonical_host(text) or text)
            else:
                in_scope.append(canonical_url(text) or text)
        elif result.verdict == "out_of_scope":
            out_of_scope.append("%s\t%s" % (text, result.reason))
        else:
            ambiguous.append("%s\t%s" % (text, result.reason))

    writes = {
        "in_scope": write_lines(args.in_output, in_scope),
        "out_of_scope": write_lines(args.out_output, out_of_scope),
        "ambiguous": write_lines(args.review_output, ambiguous),
    }

    emit(
        {
            "ok": True,
            "command": "scope check",
            "kind": args.kind,
            "scope": args.scope,
            "counts": {
                "in_scope": len(in_scope),
                "out_of_scope": len(out_of_scope),
                "ambiguous": len(ambiguous),
                "total": len(in_scope) + len(out_of_scope) + len(ambiguous),
            },
            "paths": {
                "in_scope": args.in_output,
                "out_of_scope": args.out_output,
                "ambiguous": args.review_output,
            },
            "write": writes,
        }
    )
    return EXIT_OK


def cmd_dedupe(args: argparse.Namespace) -> int:
    output = dedupe_lines(read_lines(args.input))
    status = write_lines(args.output, output)
    emit(
        {
            "ok": True,
            "command": "dedupe",
            "input": args.input,
            "output": args.output,
            "count": len(output),
            "write": status,
        }
    )
    return EXIT_OK


def cmd_classify(args: argparse.Namespace) -> int:
    result = classify_lines(read_lines(args.input), args.out_dir)
    result["ok"] = True
    result["command"] = "classify"
    emit(result)
    return EXIT_OK


HANDLERS = {
    ("runs", "init"): cmd_runs_init,
    ("runs", "verify"): cmd_runs_verify,
    ("normalize", None): cmd_normalize,
    ("scope", "check"): cmd_scope_check,
    ("dedupe", None): cmd_dedupe,
    ("classify", None): cmd_classify,
}


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse help and usage errors
        return int(exc.code or 0)

    handler = HANDLERS.get((args.command, getattr(args, "action", None)))
    if handler is None:
        emit({"ok": False, "error": "unsupported command", "code": 2})
        return 2

    try:
        return handler(args)
    except BbhError as exc:
        emit({"ok": False, "error": str(exc), "code": exc.exit_code})
        sys.stderr.write("error: %s\n" % exc)
        return exc.exit_code
    except OSError as exc:
        emit({"ok": False, "error": str(exc), "code": 5})
        sys.stderr.write("error: %s\n" % exc)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
