"""URL categorization.

Category files are mutually exclusive: each URL lands in exactly one of
``api.txt``, ``static.txt``, ``javascript.txt`` or ``other.txt``.
``with-parameters.txt`` is independent and may overlap any category.
``parameters.txt`` holds unique parameter names.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List, Set
from urllib.parse import unquote_plus, urlsplit

from .util import write_lines

CATEGORIES = ("api", "static", "javascript", "other")
CATEGORY_FILES = {name: name + ".txt" for name in CATEGORIES}
WITH_PARAMETERS = "with-parameters.txt"
PARAMETERS = "parameters.txt"

JS_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".jsx", ".map"})
STATIC_EXTENSIONS = frozenset(
    {
        ".css",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".ico",
        ".bmp",
        ".avif",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".mp4",
        ".webm",
        ".mp3",
        ".wav",
        ".ogg",
        ".m4a",
        ".pdf",
        ".zip",
        ".gz",
        ".tgz",
        ".tar",
        ".rar",
        ".7z",
    }
)
API_SEGMENTS = frozenset(
    {
        "api",
        "apis",
        "graphql",
        "gql",
        "rest",
        "rpc",
        "jsonrpc",
        "webhook",
        "webhooks",
    }
)
API_HOST_LABELS = frozenset({"api", "apis", "gateway", "graphql"})


def url_parameters(url: str) -> List[str]:
    """Return decoded parameter names from a URL query string."""

    try:
        query = urlsplit(url).query
    except ValueError:
        return []
    names: List[str] = []
    for pair in query.split("&"):
        if not pair:
            continue
        name = pair.split("=", 1)[0]
        if name:
            names.append(unquote_plus(name))
    return names


def classify_url(url: str) -> str:
    """Return exactly one category name for a URL."""

    try:
        parts = urlsplit(url)
        path = parts.path or "/"
        host = (parts.hostname or "").lower()
    except ValueError:
        return "other"

    extension = os.path.splitext(path)[1].lower()
    if extension in JS_EXTENSIONS:
        return "javascript"
    if extension in STATIC_EXTENSIONS:
        return "static"

    first_label = host.split(".")[0] if host else ""
    segments = {segment.lower() for segment in path.split("/") if segment}
    if first_label in API_HOST_LABELS or segments & API_SEGMENTS:
        return "api"
    return "other"


def classify_lines(lines: Iterable[str], out_dir: str | Path) -> Dict[str, object]:
    """Classify URLs and write the category files.

    Returns a summary dictionary with counts and written paths.
    """

    buckets: Dict[str, List[str]] = {name: [] for name in CATEGORIES}
    with_parameters: List[str] = []
    parameter_names: Set[str] = set()
    total = 0

    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        total += 1
        buckets[classify_url(text)].append(text)

        names = url_parameters(text)
        if names:
            with_parameters.append(text)
            parameter_names.update(names)

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    written: Dict[str, str] = {}
    for name in CATEGORIES:
        written[CATEGORY_FILES[name]] = write_lines(
            target / CATEGORY_FILES[name], buckets[name]
        )
    written[WITH_PARAMETERS] = write_lines(target / WITH_PARAMETERS, with_parameters)
    written[PARAMETERS] = write_lines(
        target / PARAMETERS, sorted(parameter_names)
    )

    return {
        "total": total,
        "categories": {name: len(buckets[name]) for name in CATEGORIES},
        "with_parameters": len(with_parameters),
        "parameters": len(parameter_names),
        "out_dir": str(target),
        "written": written,
    }
