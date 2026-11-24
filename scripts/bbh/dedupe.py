"""Order-preserving deduplication."""

from __future__ import annotations

from typing import Iterable, List


def dedupe_lines(lines: Iterable[str]) -> List[str]:
    """Remove duplicates while preserving first-seen order.

    Blank lines and ``#`` comments are dropped.
    """

    seen = set()
    result: List[str] = []
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
