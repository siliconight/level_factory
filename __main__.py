"""Module entrypoint so `python -m level_factory ...` works from the factory root.

The CLI's real home is `apps/cli/main.py`, and `pyproject.toml` exposes it as a
`level-factory` console script for installed copies. Neither of those helps
someone standing in `gabagool_factory` with a source checkout and no install --
the obvious guess, `python -m level_factory`, used to fail with a bare
`No module named level_factory` and no hint about where the CLI actually lives.

This directory has no `__init__.py`, so Python treats it as a namespace package
and runs this file for `-m level_factory` whenever the factory root is on
`sys.path` (i.e. is the working directory). Everything below is delegation --
argument parsing, exit codes and behaviour stay in `apps.cli.main`.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Running as `-m level_factory` puts the factory root on sys.path, not this
# directory, so `apps.cli.main` is not importable until we say where it is.
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from apps.cli.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
