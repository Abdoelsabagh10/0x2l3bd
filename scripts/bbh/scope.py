"""Scope parsing and matching.

The first fenced ``json`` block in a scope file is authoritative. Missing,
invalid, or contradictory scope data raises ``ScopeError`` and blocks the
operation. Invalid or ambiguous targets are never treated as in scope.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from . import InputError, ScopeError

FENCE_OPEN = re.compile(r"^[ \t]*```json[ \t]*$", re.IGNORECASE)
FENCE_CLOSE = re.compile(r"^[ \t]*```[ \t]*$")
HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
SCHEMES = ("http", "https")


class Check(NamedTuple):
    """Result of a single scope decision."""

    verdict: str  # in_scope | out_of_scope | ambiguous
    reason: str


@dataclass(frozen=True)
class ScopeEntry:
    """One parsed in-scope or out-of-scope entry."""

    kind: str  # host | wildcard | url | ip
    raw: str
    host: str
    scheme: Optional[str] = None
    port: Optional[int] = None
    segments: Tuple[str, ...] = ()


def extract_scope_block(text: str) -> str:
    """Return the body of the first fenced ``json`` block."""

    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if FENCE_OPEN.match(line):
            start = index
            break
    if start is None:
        raise ScopeError(
            "missing machine-readable scope block (first fenced ```json block)"
        )

    end = None
    for index in range(start + 1, len(lines)):
        if FENCE_CLOSE.match(lines[index]):
            end = index
            break
    if end is None:
        raise ScopeError("unterminated machine-readable scope block")
    return "\n".join(lines[start + 1 : end])


def canonical_host(value: Optional[str]) -> Optional[str]:
    """Canonicalize a bare hostname or IP literal. Return None when invalid."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    candidate = text
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    try:
        return ipaddress.ip_address(candidate).compressed
    except ValueError:
        pass

    candidate = candidate.rstrip(".")
    if not candidate:
        return None
    candidate = candidate.lower()
    try:
        candidate = candidate.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        return None

    if len(candidate) > 253:
        return None
    labels = candidate.split(".")
    if len(labels) < 2:
        return None
    if any(not HOST_LABEL.match(label) for label in labels):
        return None
    return candidate


def path_segments(path: str) -> Tuple[str, ...]:
    """Split a URL path into non-empty segments, preserving case."""

    return tuple(part for part in (path or "/").split("/") if part)


def parse_entry(raw: str) -> ScopeEntry:
    """Parse one scope entry, raising ScopeError when it is not supported."""

    text = raw.strip()
    if not text:
        raise ScopeError("empty scope entry")
    if "\\" in text:
        raise ScopeError("unsupported scope entry (backslash): %r" % raw)

    if "://" in text:
        try:
            parts = urlsplit(text)
            scheme = parts.scheme.lower()
            host = canonical_host(parts.hostname)
            port = parts.port
        except ValueError as exc:
            raise ScopeError("invalid scope URL %r: %s" % (raw, exc)) from exc
        if scheme not in SCHEMES:
            raise ScopeError("unsupported scope URL scheme in %r" % raw)
        if host is None:
            raise ScopeError("invalid host in scope URL %r" % raw)
        if parts.username or parts.password:
            raise ScopeError("credentials are not allowed in scope URLs: %r" % raw)
        if parts.query or parts.fragment:
            raise ScopeError("scope URLs must not contain a query or fragment: %r" % raw)
        return ScopeEntry(
            kind="url",
            raw=text,
            host=host,
            scheme=scheme,
            port=port,
            segments=path_segments(parts.path),
        )

    if text.startswith("*."):
        base = canonical_host(text[2:])
        if base is None:
            raise ScopeError("invalid wildcard scope entry: %r" % raw)
        return ScopeEntry(kind="wildcard", raw=text, host=base)

    candidate = text
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        address = None
    if address is not None:
        return ScopeEntry(kind="ip", raw=text, host=address.compressed)

    if ":" in text:
        raise ScopeError("host scope entries must not include a port: %r" % raw)
    if any(char in text for char in "/?#@ "):
        raise ScopeError("unsupported scope entry: %r" % raw)

    host = canonical_host(text)
    if host is None:
        raise ScopeError("invalid host scope entry: %r" % raw)
    return ScopeEntry(kind="host", raw=text, host=host)


def parse_scope_text(text: str) -> dict:
    """Parse and validate the machine-readable scope block."""

    block = extract_scope_block(text)
    try:
        data = json.loads(block)
    except json.JSONDecodeError as exc:
        raise ScopeError("invalid scope JSON: %s" % exc) from exc
    if not isinstance(data, dict):
        raise ScopeError("scope block must be a JSON object")

    program = data.get("program")
    if not isinstance(program, str) or not program.strip():
        raise ScopeError("scope block requires a non-empty 'program' string")

    if "in_scope" not in data:
        raise ScopeError("scope block requires an 'in_scope' list")
    for key in ("in_scope", "out_of_scope"):
        value = data.get(key, [])
        if not isinstance(value, list):
            raise ScopeError("'%s' must be a list" % key)
        for item in value:
            if not isinstance(item, str):
                raise ScopeError("'%s' entries must be strings" % key)

    ports = data.get("allowed_ports", [])
    if not isinstance(ports, list):
        raise ScopeError("'allowed_ports' must be a list")
    for port in ports:
        if isinstance(port, bool) or not isinstance(port, int):
            raise ScopeError("'allowed_ports' entries must be integers")
        if not 1 <= port <= 65535:
            raise ScopeError("'allowed_ports' entries must be 1-65535")

    restrictions = data.get("restrictions", [])
    if not isinstance(restrictions, list) or not all(
        isinstance(item, str) for item in restrictions
    ):
        raise ScopeError("'restrictions' must be a list of strings")

    for key in ("updated", "notes"):
        if key in data and not isinstance(data[key], str):
            raise ScopeError("'%s' must be a string" % key)

    return data


def load_scope(path: str | Path) -> "Scope":
    """Read a scope file and return a validated Scope object."""

    p = Path(path)
    if not p.is_file():
        raise InputError("scope file not found: %s" % p)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise InputError("cannot read scope file %s: %s" % (p, exc)) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScopeError("scope file is not valid UTF-8: %s" % exc) from exc
    data = parse_scope_text(text)
    return Scope(data, path=str(p), sha256=hashlib.sha256(raw).hexdigest())


class Scope:
    """Validated scope configuration with host and URL matching."""

    def __init__(
        self,
        data: dict,
        *,
        path: Optional[str] = None,
        sha256: Optional[str] = None,
    ) -> None:
        self.data = data
        self.path = path
        self.sha256 = sha256
        self.program = data["program"].strip()
        self.in_scope: Tuple[ScopeEntry, ...] = tuple(
            parse_entry(item) for item in data.get("in_scope", [])
        )
        self.out_of_scope: Tuple[ScopeEntry, ...] = tuple(
            parse_entry(item) for item in data.get("out_of_scope", [])
        )
        self.allowed_ports = frozenset(data.get("allowed_ports", []))
        self.restrictions: Tuple[str, ...] = tuple(data.get("restrictions", []))

    # -- host helpers -----------------------------------------------------

    @staticmethod
    def _wildcard_match(host: str, base: str) -> bool:
        """Wildcard entries cover the base domain itself and any depth below."""
        return host == base or host.endswith("." + base)

    def _excluded_host(self, host: str) -> Optional[ScopeEntry]:
        for entry in self.out_of_scope:
            if entry.kind in ("host", "ip") and entry.host == host:
                return entry
            if entry.kind == "wildcard" and self._wildcard_match(host, entry.host):
                return entry
            if entry.kind == "url" and entry.host == host and not entry.segments:
                return entry
        return None

    def _included_host(
        self, host: str
    ) -> Tuple[Optional[ScopeEntry], Optional[ScopeEntry]]:
        matched: Optional[ScopeEntry] = None
        path_scoped: Optional[ScopeEntry] = None
        for entry in self.in_scope:
            if entry.kind in ("host", "ip") and entry.host == host:
                matched = entry
            elif entry.kind == "wildcard" and self._wildcard_match(host, entry.host):
                matched = entry
            elif entry.kind == "url" and entry.host == host:
                if entry.segments:
                    path_scoped = entry
                else:
                    matched = entry
        return matched, path_scoped

    # -- decisions --------------------------------------------------------

    def check_host(self, value: str) -> Check:
        host = canonical_host(value)
        if host is None:
            return Check("ambiguous", "invalid host")

        excluded = self._excluded_host(host)
        if excluded is not None:
            return Check("out_of_scope", "excluded by %s" % excluded.raw)

        matched, path_scoped = self._included_host(host)
        if matched is not None:
            return Check("in_scope", "matched %s" % matched.raw)
        if path_scoped is not None:
            return Check(
                "ambiguous",
                "host is covered only by path-scoped entry %s" % path_scoped.raw,
            )
        return Check("out_of_scope", "not in scope")

    def check_url(self, value: str) -> Check:
        parsed = parse_target_url(value)
        if parsed is None:
            return Check("ambiguous", "invalid or unsupported URL")
        scheme, host, port, segments = parsed

        if self.allowed_ports and port not in self.allowed_ports:
            return Check("out_of_scope", "port %d not allowed" % port)

        for entry in self.out_of_scope:
            if entry.kind == "url":
                if (
                    entry.host == host
                    and (entry.port is None or entry.port == port)
                    and _segments_match(segments, entry.segments)
                ):
                    return Check("out_of_scope", "excluded by %s" % entry.raw)
            elif entry.kind == "wildcard":
                if self._wildcard_match(host, entry.host):
                    return Check("out_of_scope", "excluded by %s" % entry.raw)
            elif entry.kind in ("host", "ip") and entry.host == host:
                return Check("out_of_scope", "excluded by %s" % entry.raw)

        for entry in self.in_scope:
            if entry.kind == "url":
                if (
                    entry.scheme == scheme
                    and entry.host == host
                    and (entry.port is None or entry.port == port)
                    and _segments_match(segments, entry.segments)
                ):
                    return Check("in_scope", "matched %s" % entry.raw)
            elif entry.kind == "wildcard":
                if self._wildcard_match(host, entry.host):
                    return Check("in_scope", "matched %s" % entry.raw)
            elif entry.kind in ("host", "ip") and entry.host == host:
                return Check("in_scope", "matched %s" % entry.raw)

        return Check("out_of_scope", "not in scope")


def _segments_match(segments: Sequence[str], prefix: Sequence[str]) -> bool:
    return len(segments) >= len(prefix) and tuple(segments[: len(prefix)]) == tuple(prefix)


def parse_target_url(
    value: str,
) -> Optional[Tuple[str, str, int, Tuple[str, ...]]]:
    """Parse a concrete URL for scope checking.

    Returns (scheme, host, effective_port, path_segments) or None when the
    value cannot be evaluated safely.
    """

    text = str(value).strip()
    if not text or "\\" in text:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        return None
    try:
        parts = urlsplit(text)
        scheme = parts.scheme.lower()
        host = canonical_host(parts.hostname)
        explicit_port = parts.port
    except ValueError:
        return None
    if scheme not in SCHEMES or host is None:
        return None
    if explicit_port is None:
        explicit_port = 443 if scheme == "https" else 80
    return scheme, host, explicit_port, path_segments(parts.path)
