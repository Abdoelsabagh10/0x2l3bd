"""Shared deterministic utilities for the bug bounty workspace.

Phase 3 of the agreed architecture. Standard library only.
"""

__version__ = "1.0.0"

__all__ = [
    "BbhError",
    "ScopeError",
    "RunConflict",
    "OverwriteRefused",
    "InputError",
]


class BbhError(Exception):
    """Base class for expected, user-facing failures."""

    exit_code = 1


class ScopeError(BbhError):
    """Invalid, missing, or contradictory scope configuration."""

    exit_code = 2


class RunConflict(BbhError):
    """Run metadata conflict, such as a changed scope hash."""

    exit_code = 3


class OverwriteRefused(BbhError):
    """Refused to overwrite an existing non-empty output file."""

    exit_code = 4


class InputError(BbhError):
    """Missing or unreadable input."""

    exit_code = 5
