"""Small filesystem and time helpers shared by the bbh modules."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from . import InputError, OverwriteRefused


def utcnow() -> str:
    """Return an ISO-8601 UTC timestamp with a trailing Z."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_lines(path: str | os.PathLike) -> List[str]:
    """Read a text file as lines, failing closed when it is missing."""

    p = Path(path)
    if not p.is_file():
        raise InputError("input file not found: %s" % p)
    try:
        return p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise InputError("cannot read input file %s: %s" % (p, exc)) from exc


def join_lines(lines: Iterable[str]) -> str:
    """Render lines as LF-terminated text."""

    return "".join(line + "\n" for line in lines)


def write_text(path: str | os.PathLike, text: str) -> str:
    """Write text atomically, refusing to replace different non-empty content.

    Returns ``written`` or ``unchanged``.
    """

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if p.exists():
        try:
            existing = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise OverwriteRefused(
                "cannot read existing output %s: %s" % (p, exc)
            ) from exc
        if existing == text:
            return "unchanged"
        if p.stat().st_size > 0:
            raise OverwriteRefused(
                "refusing to overwrite non-empty output: %s" % p
            )

    tmp = p.with_name(p.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return "written"


def write_lines(path: str | os.PathLike, lines: Iterable[str]) -> str:
    """Write an iterable of lines as LF-terminated text."""

    return write_text(path, join_lines(lines))


def atomic_write_json(path: str | os.PathLike, payload: object) -> None:
    """Write JSON metadata atomically. Metadata updates may replace old data."""

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = p.with_name(p.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
