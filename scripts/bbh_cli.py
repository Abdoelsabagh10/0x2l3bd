"""Launcher for the frozen Phase 3 CLI.

Lets every command use ``python scripts/bbh_cli.py ...`` from the workspace
root. The Phase 3 package itself is unchanged; this only fixes the entry point
for a directly executed script, which cannot use relative imports.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bbh.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
