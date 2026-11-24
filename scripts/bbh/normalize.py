"""Host and URL canonicalization.

Unparseable non-empty lines are preserved verbatim so that the scope stage can
route them to the review output. They are never silently promoted to in scope.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from .scope import canonical_host

DEFAULT_PORTS = {"http": 80, "https": 443}
SCHEMES = ("http", "https")
PERCENT = re.compile(r"%[0-9a-fA-F]{2}")


def extract_host(value: str) -> Optional[str]:
    """Extract a hostname from a URL, host:port, or bare host string."""

    text = value.strip()
    if not text:
        return None
    try:
        if "://" in text:
            return urlsplit(text).hostname
        return urlsplit("//" + text).hostname
    except ValueError:
        return None


def normalize_host_line(line: str) -> Optional[str]:
    """Return a canonical host, or the trimmed original when unparseable."""

    text = line.strip()
    if not text:
        return None
    host = canonical_host(extract_host(text))
    return host if host is not None else text


def canonical_url(value: str) -> Optional[str]:
    """Return a canonical absolute http(s) URL, or None when invalid."""

    text = str(value).strip()
    if not text or "\\" in text:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        return None

    try:
        parts = urlsplit(text)
        scheme = parts.scheme.lower()
        host = canonical_host(parts.hostname)
        port = parts.port
    except ValueError:
        return None

    if scheme not in SCHEMES or host is None:
        return None

    netloc = "[%s]" % host if ":" in host else host
    if port is not None and port != DEFAULT_PORTS[scheme]:
        netloc = "%s:%d" % (netloc, port)

    path = parts.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    if not path.startswith("/"):
        path = "/" + path
    path = PERCENT.sub(lambda match: match.group(0).upper(), path)

    query = parts.query
    if query:
        pairs = sorted(pair for pair in query.split("&") if pair)
        query = "&".join(pairs)

    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_url_line(line: str) -> Optional[str]:
    """Return a canonical URL, or the trimmed original when unparseable."""

    text = line.strip()
    if not text:
        return None
    canonical = canonical_url(text)
    return canonical if canonical is not None else text


def is_ip(value: str) -> bool:
    """Return True when the value is an IP literal."""

    try:
        ipaddress.ip_address(value.strip().strip("[]"))
        return True
    except ValueError:
        return False
