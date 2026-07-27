"""The obvious way to start the CLI has to be a way that works.

`pyproject.toml` exposes the CLI as a `level-factory` console script and the
README also documents `python apps/cli/main.py`. Both assume you already know
where the entrypoint lives. Someone standing at the factory root reaches for
`python -m level_factory` instead, and before the root `__main__.py` existed
that produced `No module named level_factory` -- an error that names the thing
you asked for and tells you nothing about the thing you wanted.

These tests pin the two invocations a source checkout can rely on with nothing
installed: running the shim by path, and running the checkout directory as a
module from its parent. The second works for any directory name, because a
directory without `__init__.py` on `sys.path` is a namespace package -- so the
test does not care whether this checkout is called `level_factory`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIM = REPO_ROOT / "__main__.py"


def _run(args, cwd):
    return subprocess.run([sys.executable, *args], cwd=str(cwd),
                          capture_output=True, text=True, timeout=120)


def test_the_factory_root_carries_a_module_entrypoint():
    assert SHIM.is_file(), (
        "level_factory/__main__.py is what makes `python -m level_factory` "
        "work from the factory root; without it the natural command fails "
        "with a bare import error")


def test_running_the_shim_by_path_reaches_the_real_parser():
    done = _run([str(SHIM), "--help"], cwd=REPO_ROOT)
    assert done.returncode == 0, done.stderr
    assert "Level Factory orchestration CLI" in done.stdout
    # Delegation, not a second parser: the subcommands come from apps.cli.main.
    for command in ("run", "validate", "walk", "doctor"):
        assert command in done.stdout, f"{command} missing from {done.stdout}"


def test_the_checkout_runs_as_a_module_from_its_parent():
    done = _run(["-m", REPO_ROOT.name, "--help"], cwd=REPO_ROOT.parent)
    assert done.returncode == 0, done.stderr
    assert "Level Factory orchestration CLI" in done.stdout


def test_a_directory_that_is_not_a_workspace_says_so_instead_of_guessing():
    """-C is the other half of the papercut: it must not search downward."""
    done = _run(["-m", REPO_ROOT.name, "-C", str(REPO_ROOT), "status"],
                cwd=REPO_ROOT.parent)
    assert "no Level Factory workspace found" in (done.stdout + done.stderr)
